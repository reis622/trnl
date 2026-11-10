"""`trnl --setup`: download offline models and dictionaries.

Models (CTranslate2 format):
  * OPUS-MT (Helsinki-NLP) for en->tr, tr->en, ja->en - clearly better than the Argos ones.
    1) pre-converted int8 zip from TRNL_MODELS_URL / the project's GitHub release (small, ~80 MB each), else
    2) the official OPUS-MT Marian zip, converted locally with ctranslate2's own OPUS-MT converter
       (needs only numpy + pyyaml, which ctranslate2 already depends on - no torch), else
    3) the Argos package for that pair.
  * Argos Translate packages for the other pairs.
Dictionaries: WikDict (30 pairs) + kaikki.org English-Wiktionary glosses (tr, ja, zh; de, es with --full).
"""
import concurrent.futures as cf
import gzip
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

from trnl.paths import data_dir, dict_path, models_dir

ARGOS = "https://argos-net.com/v1/translate-{}.argosmodel"
ARGOS_MODELS = {
    "en_tr": "1_5", "tr_en": "1_5", "en_de": "1_3", "de_en": "1_3", "en_es": "1_0", "es_en": "1_0",
    "en_ja": "1_1", "ja_en": "1_1", "en_zh": "1_9", "zh_en": "1_9",
}
OPUS_BASE = "https://object.pouta.csc.fi/"
OPUS_MODELS = {  # pair -> (official Marian zip, target-language token or "")
    "en_tr": ("Tatoeba-MT-models/eng-trk/opus2m-2020-08-01.zip", ">>tur<<"),
    "tr_en": ("OPUS-MT-models/tr-en/opus-2020-01-16.zip", ""),
    "ja_en": ("OPUS-MT-models/ja-en/opus-2019-12-18.zip", ""),
}
# Pre-converted int8 models (made with `python -m trnl.setup_data --export-opus DIR`), hosted on the
# project's GitHub release. Placeholder until published; TRNL_MODELS_URL overrides it.
PRECONVERTED = os.environ.get("TRNL_MODELS_URL",
                              "https://github.com/reis622/trnl/releases/download/models-v1/{pair}-opus-int8.zip")
WIKDICT = "https://download.wikdict.com/dictionaries/sqlite/2/{}-{}.sqlite3"
KAIKKI = "https://kaikki.org/dictionary/{0}/kaikki.org-dictionary-{0}.jsonl.gz"
KAIKKI_NAMES = {"tr": "Turkish", "ja": "Japanese", "zh": "Chinese", "de": "German", "es": "Spanish"}
KAIKKI_DEFAULT = ("tr", "ja", "zh")
ALL = ("en", "tr", "de", "es", "ja", "zh")
UA = {"User-Agent": "trnl-setup/1.1"}


class Progress:
    def __init__(self, label):
        self.label, self.done, self.total, self.lock = label, 0, 0, threading.Lock()
        self.last = 0

    def add_total(self, n):
        with self.lock:
            self.total += n

    def add(self, n):
        with self.lock:
            self.done += n
            now = time.time()
            if now - self.last > 0.25:
                self.last = now
                self.show()

    def show(self, end=False):
        if not self.total:
            return
        mb, tot = self.done / 1e6, self.total / 1e6
        pct = f"{100 * self.done / self.total:5.1f}%" if self.total else ""
        sys.stderr.write(f"\r{self.label}: {mb:7.1f} / {tot:.0f} MB {pct}   ")
        if end:
            sys.stderr.write("\n")
        sys.stderr.flush()


def _download(url, dest, prog, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                size = int(r.headers.get("Content-Length") or 0)
                prog.add_total(size)
                got = 0
                with open(dest + ".part", "wb") as f:
                    while True:
                        b = r.read(1 << 16)
                        if not b:
                            break
                        f.write(b)
                        got += len(b)
                        prog.add(len(b))
                if size and got != size:
                    prog.add_total(-size)
                    prog.add(-got)
                    raise IOError("incomplete download")
            os.replace(dest + ".part", dest)
            return dest
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or i == retries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def _is_opus(target):
    return os.path.exists(os.path.join(target, "trnl.json"))


def _installed(target):
    return os.path.exists(os.path.join(target, "model", "model.bin")) or os.path.exists(
        os.path.join(target, "model.bin"))


def _swap(stage, target):
    shutil.rmtree(target, ignore_errors=True)
    os.replace(stage, target)


def _argos(pair, tmp, prog):
    target = os.path.join(models_dir(), pair)
    zpath = os.path.join(tmp, pair + ".argos.zip")
    _download(ARGOS.format(f"{pair}-{ARGOS_MODELS[pair]}"), zpath, prog)
    stage = target + ".tmp"
    shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            parts = n.split("/", 1)
            if len(parts) < 2 or not parts[1] or n.endswith("/"):
                continue
            rel = parts[1]
            if not (rel == "sentencepiece.model" or rel.startswith("model/")):
                continue  # skip stanza (torch) sentence splitter, README
            out = os.path.join(stage, *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as s, open(out, "wb") as d:
                shutil.copyfileobj(s, d)
    os.remove(zpath)
    if not os.path.exists(os.path.join(stage, "sentencepiece.model")):
        raise RuntimeError(pair + ": unsupported package format")
    _swap(stage, target)
    return "argos"


def _opus_preconverted(pair, tmp, prog):
    url = PRECONVERTED.format(pair=pair)
    if "reis622" in url:
        raise LookupError("no pre-converted host configured")
    target = os.path.join(models_dir(), pair)
    zpath = _download(url, os.path.join(tmp, pair + ".pre.zip"), prog)
    stage = target + ".tmp"
    shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            base = os.path.basename(n)
            if base in ("model.bin", "config.json", "shared_vocabulary.json", "shared_vocabulary.txt",
                        "source_vocabulary.json", "target_vocabulary.json", "source.spm", "target.spm",
                        "trnl.json", "README.md", "LICENSE"):
                os.makedirs(stage, exist_ok=True)
                with z.open(n) as s, open(os.path.join(stage, base), "wb") as d:
                    shutil.copyfileobj(s, d)
    os.remove(zpath)
    if not os.path.exists(os.path.join(stage, "trnl.json")):
        raise RuntimeError("bad pre-converted package")
    _swap(stage, target)
    return "opus (pre-converted)"


def convert_opus(src_dir, out_dir, prefix, source_url=""):
    """Official OPUS-MT Marian dir -> CTranslate2 int8 dir (numpy + pyyaml only)."""
    import ctranslate2
    ctranslate2.converters.OpusMTConverter(src_dir).convert(out_dir, quantization="int8", force=True)
    for f in ("source.spm", "target.spm", "README.md", "LICENSE"):
        if os.path.exists(os.path.join(src_dir, f)):
            shutil.copy(os.path.join(src_dir, f), os.path.join(out_dir, f))
    with open(os.path.join(out_dir, "trnl.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": "opus", "prefix": prefix, "source": source_url}, f)


def _opus_convert(pair, tmp, prog):
    rel, prefix = OPUS_MODELS[pair]
    target = os.path.join(models_dir(), pair)
    zpath = _download(OPUS_BASE + rel, os.path.join(tmp, pair + ".opus.zip"), prog)
    raw = os.path.join(tmp, pair + ".raw")
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            if n.endswith((".log", ".sh", ".mk", ".tcmodel")) or n.endswith("/"):
                continue
            z.extract(n, raw)
    os.remove(zpath)
    stage = target + ".tmp"
    shutil.rmtree(stage, ignore_errors=True)
    convert_opus(raw, stage, prefix, OPUS_BASE + rel)
    shutil.rmtree(raw, ignore_errors=True)
    _swap(stage, target)
    return "opus (converted locally)"


def _install_model(pair, tmp, prog, notes):
    target = os.path.join(models_dir(), pair)
    want_opus = pair in OPUS_MODELS and os.environ.get("TRNL_NO_OPUS") != "1"
    if _installed(target) and (_is_opus(target) or not want_opus):
        return pair, "var"
    if want_opus:
        for fn in (_opus_preconverted, _opus_convert):
            try:
                return pair, fn(pair, tmp, prog)
            except Exception as e:
                notes.append(f"{pair}: {fn.__name__.strip('_')} -> {e.__class__.__name__}: {e}")
        if _installed(target):
            return pair, "argos (eski, OPUS kurulamadi)"
    return pair, _argos(pair, tmp, prog)


# ---------------- dictionaries ----------------
def _meta(con, k):
    try:
        v = con.execute("select v from meta where k=?", (k,)).fetchone()
        return set(v[0].split(",")) if v and v[0] else set()
    except sqlite3.Error:
        return set()


def _build_wikdict(langs, tmp, prog):
    out = dict_path()
    if os.path.exists(out):
        c = sqlite3.connect(out)
        have = _meta(c, "langs")
        c.close()
        if set(langs) <= have:
            return False
    stage = out + ".tmp"
    if os.path.exists(stage):
        os.remove(stage)
    pairs = [(a, b) for a in langs for b in langs if a != b]
    files = {}

    def get(ab):
        a, b = ab
        return ab, _download(WIKDICT.format(a, b), os.path.join(tmp, f"{a}-{b}.sqlite3"), prog)

    with cf.ThreadPoolExecutor(6) as ex:
        for ab, path in ex.map(get, pairs):
            files[ab] = path
    o = sqlite3.connect(stage)
    o.execute("create table t(p TEXT, wl TEXT, w TEXT, pos TEXT, tr TEXT, sc REAL, im REAL)")
    for (a, b), path in files.items():
        c = sqlite3.connect(path)
        rows = c.execute("select written_rep, lexentry, trans_list, score, importance from translation "
                         "where (is_good=1 or is_good is null) and written_rep is not null").fetchall()
        c.close()
        o.executemany("insert into t values(?,?,?,?,?,?,?)",
                      [(f"{a}_{b}", w.lower(), w, (lx.split("__")[1] if lx and "__" in lx else None), tl, sc, im)
                       for w, lx, tl, sc, im in rows])
        os.remove(path)
    o.execute("create index ix on t(p, wl)")
    o.execute("create table meta(k TEXT primary key, v TEXT)")
    o.execute("insert into meta values('langs', ?)", (",".join(langs),))
    # keep kaikki data from an older dict.db
    if os.path.exists(out):
        try:
            o.execute("attach ? as old", (out,))
            if o.execute("select 1 from old.sqlite_master where name='k'").fetchone():
                o.execute("create table k as select * from old.k")
                v = o.execute("select v from old.meta where k='kaikki'").fetchone()
                if v:
                    o.execute("insert or replace into meta values('kaikki', ?)", v)
            o.commit()
            o.execute("detach old")
        except sqlite3.Error:
            pass
    o.commit()
    o.close()
    os.replace(stage, out)
    return True


class _Counting(io.RawIOBase):
    def __init__(self, r, prog):
        self.r, self.prog = r, prog

    def readable(self):
        return True

    def readinto(self, b):
        data = self.r.read(len(b))
        n = len(data)
        b[:n] = data
        self.prog.add(n)
        return n


def _build_kaikki(langs, prog):
    """Stream kaikki.org gz extracts straight into dict.db (nothing big touches the disk)."""
    from trnl.dictdb import kaikki_rows
    out = dict_path()
    con = sqlite3.connect(out)
    con.execute("create table if not exists k(l TEXT, wl TEXT, w TEXT, ent INT, sn INT, pos TEXT, term TEXT, "
                "alts TEXT)")
    con.execute("create table if not exists meta(k TEXT primary key, v TEXT)")
    have = _meta(con, "kaikki")
    todo = [l for l in langs if l not in have]
    for lang in todo:
        req = urllib.request.Request(KAIKKI.format(KAIKKI_NAMES[lang]), headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            prog.add_total(int(r.headers.get("Content-Length") or 0))
            text = io.TextIOWrapper(gzip.GzipFile(fileobj=io.BufferedReader(_Counting(r, prog), 1 << 16)),
                                    encoding="utf-8")
            con.execute("delete from k where l=?", (lang,))
            batch = []
            for row in kaikki_rows(text, lang):
                batch.append(row)
                if len(batch) >= 5000:
                    con.executemany("insert into k values(?,?,?,?,?,?,?,?)", batch)
                    batch = []
            if batch:
                con.executemany("insert into k values(?,?,?,?,?,?,?,?)", batch)
        have.add(lang)
        con.execute("insert or replace into meta values('kaikki', ?)", (",".join(sorted(have)),))
        con.commit()
    con.execute("create index if not exists kx on k(l, wl)")
    con.commit()
    if todo:
        con.execute("vacuum")
    con.close()


def run(args=()):
    args = list(args)
    full = False
    for flag in ("--full", "-f"):
        if flag in args:
            args.remove(flag)
            full = True
    langs = list(ALL)
    if args:
        want = [x.strip().lower() for x in ",".join(args).split(",") if x.strip()]
        langs = [l for l in ALL if l in want] or list(ALL)
        if "en" not in langs:
            langs.insert(0, "en")  # English is the pivot
    os.makedirs(models_dir(), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="trnl-", dir=data_dir())
    notes = []
    try:
        pairs = [p for p in ARGOS_MODELS if p.split("_")[0] in langs and p.split("_")[1] in langs]
        prog = Progress("modeller")
        with cf.ThreadPoolExecutor(4) as ex:
            res = list(ex.map(lambda p: _install_model(p, tmp, prog, notes), pairs))
        prog.show(end=True)
        prog = Progress("sozluk  ")
        _build_wikdict(langs, tmp, prog)
        kl = [l for l in (KAIKKI_NAMES if full else KAIKKI_DEFAULT) if l in langs]
        _build_kaikki(kl, prog)
        prog.show(end=True)
        if os.environ.get("TRNL_SETUP_VERBOSE"):
            for p, how in res:
                sys.stderr.write(f"  {p}: {how}\n")
            for n in notes:
                sys.stderr.write(f"  not: {n}\n")
        sys.stderr.write(f"tamam: {', '.join(langs)} -> {data_dir()}\n")
        if sys.platform == "win32":
            from trnl.winamp import AMP_TIP
            sys.stderr.write(AMP_TIP + "\n")
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("\niptal edildi (tekrar 'trnl --setup' kaldigi yerden devam eder)\n")
        return 130
    except Exception as e:
        sys.stderr.write(f"\nkurulum hatasi: {e}\n(internet baglantisini kontrol edip tekrar 'trnl --setup' calistir)\n")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def export_opus(out_dir):
    """Maintainer helper: build the pre-converted zips to upload to the GitHub release (models-v1)."""
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="trnl-export-")
    try:
        for pair, (rel, prefix) in OPUS_MODELS.items():
            prog = Progress(pair)
            zpath = _download(OPUS_BASE + rel, os.path.join(tmp, pair + ".zip"), prog)
            prog.show(end=True)
            raw = os.path.join(tmp, pair)
            with zipfile.ZipFile(zpath) as z:
                z.extractall(raw)
            conv = os.path.join(tmp, pair + ".ct2")
            convert_opus(raw, conv, prefix, OPUS_BASE + rel)
            dest = os.path.join(out_dir, f"{pair}-opus-int8.zip")
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(os.listdir(conv)):
                    z.write(os.path.join(conv, f), f"{pair}/{f}")
            shutil.rmtree(raw)
            shutil.rmtree(conv)
            os.remove(zpath)
            print(dest, os.path.getsize(dest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export-opus":
        export_opus(sys.argv[2])
    else:
        sys.exit(run(sys.argv[1:]))
