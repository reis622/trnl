"""trnl command line: one-shot, --words, silent shell, --history, --setup."""
import os
import sys
import time

from trnl import __version__
from trnl.paths import config, data_dir

HELP_TR = """trnl - terminal çevirmeni (önce internetten çevirir, internet yoksa çevrimdışı)

ÇEVİRİ
  trnl <metin>                Türkçe yazarsan İngilizceye, başka dil yazarsan Türkçeye çevirir
                              tırnak gerekmez:  trnl hello   /   trnl nasılsın bugün
                              tek kelimede en fazla 3 gerçek anlamı gösterir
  trnl :de <metin>            hedef dili seçer (internetle her dil, internetsiz: en de tr es ja zh)
  trnl -t de <metin>          :de ile aynı                                  (--to de)
  trnl -w hello,but,love      birden çok kelimeyi tek seferde çevirir       (--words)
  trnl -o <metin>             sadece çevrimdışı çevirir                     (--offline)
  trnl -n <metin>             sadece internetten çevirir                    (--online)

SESSİZ KABUK (istediğin dilde başlatılabilir)
  trnl                        kabuğu açar: Türkçe <-> İngilizce çevirir
                              ekranı temizler, yaz + Enter = çeviri; sadece Ctrl+C ile çıkılır
                              ('exit' yazarsan onu da çevirir)
  trnl :ja                    kabuğu Japoncaya çevirecek şekilde açar
  trnl :de                    kabuğu Almancaya çevirecek şekilde açar (:es, :fr, :ru ... her dil)
  trnl -t es                  :es ile aynı, kabuğu İspanyolcaya çevirecek şekilde açar
    içerideyken:
      :ja                     hedef dili Japonca yapar (her dil kodu olur: :de :es :fr ...)
      :auto                   yeniden Türkçe <-> İngilizce
      :de Guten Tag           sadece bu satırı Almancaya çevirir
      yukarı/aşağı ok         önceki yazdıkların
      "tırnak", kişisel sözlük ve panoya kopyalama burada da çalışır

ÇEVRİLMESİN: TIRNAK
  trnl Ahmet'e "Sevgi" dedim  çift tırnak içindeki kelime olduğu gibi kalır -> I said Sevgi to Ahmet
                              (cümlenin tamamı tırnak içindeyse normal çevrilir: trnl "rock & roll")

KİŞİSEL SÖZLÜK (argo, oyun dili, özel isimler)
  trnl -a mell=molotov        kelimeyi sözlüğe ekler, artık hep bu anlamla çevrilir   (--add)
                              trnl orta koridora mell alma lütfen
                              -> Please don't take Molotovs in the middle lane.
                              ekleri de tanır: mell'e, mellden, melleri ...
  trnl -a Kerem=Kerem         özel ismi korur, hiç çevrilmez (Umut -> Hope olmaz)
  trnl -a kanka naber=hey bro birden çok kelime de olur
  trnl mell                   sözlükteki tek kelime: direkt anlamını yazar -> molotov
  trnl -l                     sözlüğü listeler                              (--list)
  trnl -r mell                sözlükten siler                               (--remove)

PANOYA KOPYALAMA (isteğe bağlı)
  trnl -c                     bundan sonra her çevirinin sonucu panoya kopyalanır, Ctrl+V ile yapıştır (--copy)
                              (kelimede ilk anlam kopyalanır, kabukta da her çeviri kopyalanır)
                              SADECE bu terminal penceresi için açılır; pencereyi kapatınca kendiliğinden
                              kapanır, yeni açılan pencerelerde kapalıdır
  trnl -c hello               açar ve hemen çevirir
  trnl -c off                 kapatır                                       (--copy off)

GEÇMİŞ
  trnl -H                     son 50 çeviriyi gösterir                      (--history)
  trnl -H 200                 son 200 çeviriyi gösterir
  trnl -H clear               geçmişi siler                                 (--history clear)

ÇEVRİMDIŞI DİL PAKETLERİ (isteğe bağlı, bir kere indirilir)
  trnl -s                     internetsiz çalışması için tüm paketleri indirir: en tr de es ja zh
                              (çeviri modelleri + sözlükler, toplam ~2 GB, biraz sürer) (--setup)
  trnl -s en,tr               sadece seçtiğin dilleri indirir (çok daha küçük ve hızlı)
  trnl -s -f                  de ve es için de büyük sözlükleri ekler       (--full)
                              yarıda kesilirse aynı komutu tekrar çalıştır, kaldığı yerden devam eder
                              paketler olmadan da trnl internetle normal çalışır

DİĞER
  trnl -v                     sürüm                                         (--version)
  trnl -h                     bu yardım                                     (--help)

NOT: Metinde & (ampersand) kullanacaksanız cümleyi çift tırnak içinde yazın: trnl "rock & roll"

ayarlar: {cfg}
  native=tr foreign=en theme=auto|dark|light color=r;g;b dim=r;g;b timeout=2 mode=auto|online|offline
  ortam değişkenleri: TRNL_THEME, TRNL_COLOR, TRNL_DIM, TRNL_NATIVE, TRNL_FOREIGN, TRNL_MODE, TRNL_HOME, NO_COLOR
"""


HELP_EN = """trnl - terminal translator (online first, offline when there is no internet)

TRANSLATE
  trnl <text>                 Turkish -> English, any other language -> Turkish
                              no quotes needed:  trnl hello   /   trnl how are you today
                              a single word shows up to 3 real meanings
  trnl :de <text>             pick the target language (online: any, offline: en de tr es ja zh)
  trnl -t de <text>           same as :de                                   (--to de)
  trnl -w hello,but,love      translate several words at once               (--words)
  trnl -o <text>              offline only                                  (--offline)
  trnl -n <text>              online only                                   (--online)

SILENT SHELL (can be started in any language)
  trnl                        open the shell: Turkish <-> English
                              clears the screen; type + Enter = translation; only Ctrl+C exits
                              (typing 'exit' just translates it)
  trnl :ja                    open the shell translating to Japanese
  trnl :de                    open the shell translating to German (:es, :fr, :ru ... any language)
  trnl -t es                  same as :es, opens the shell translating to Spanish
    inside the shell:
      :ja                     switch the target to Japanese (any code works: :de :es :fr ...)
      :auto                   back to Turkish <-> English
      :de Guten Tag           translate only this line to German
      up/down arrows          what you typed before
      "quotes", the personal glossary and clipboard copy work here too

KEEP AS IS: QUOTES
  trnl Ahmet'e "Sevgi" dedim  a word in double quotes is not translated -> I said Sevgi to Ahmet
                              (if the whole sentence is quoted it is translated normally: trnl "rock & roll")

PERSONAL GLOSSARY (slang, game words, names)
  trnl -a mell=molotov        add a word; from now on it is translated with this meaning   (--add)
                              trnl orta koridora mell alma lütfen
                              -> Please don't take Molotovs in the middle lane.
                              Turkish suffixes work too: mell'e, mellden, melleri ...
  trnl -a Kerem=Kerem         keep a name exactly as it is (Umut never becomes Hope)
  trnl -a kanka naber=hey bro several words are fine too
  trnl mell                   a glossary word on its own prints its meaning -> molotov
  trnl -l                     list the glossary                             (--list)
  trnl -r mell                remove a word                                 (--remove)

COPY TO CLIPBOARD (optional)
  trnl -c                     from now on every translation is copied to the clipboard, paste with Ctrl+V (--copy)
                              (for a word the first meaning is copied; in the shell every translation is)
                              ONLY for this terminal window; it turns off by itself when the window is
                              closed, new windows start with it off
  trnl -c hello               turn it on and translate right away
  trnl -c off                 turn it off                                   (--copy off)

HISTORY
  trnl -H                     show the last 50 translations                 (--history)
  trnl -H 200                 show the last 200 translations
  trnl -H clear               delete the history                            (--history clear)

OFFLINE LANGUAGE PACKS (optional, downloaded once)
  trnl -s                     download every pack for offline use: en tr de es ja zh
                              (translation models + dictionaries, ~2 GB total, takes a while) (--setup)
  trnl -s en,tr               download only the languages you pick (much smaller and faster)
  trnl -s -f                  also add the big de and es dictionaries       (--full)
                              if it gets interrupted, run the same command again: it resumes
                              without packs trnl still works normally online

OTHER
  trnl -v                     version                                       (--version)
  trnl -h                     this help                                     (--help)

NOTE: if your text contains & (ampersand), put the sentence in double quotes: trnl "rock & roll"

config: {cfg}
  native=tr foreign=en theme=auto|dark|light color=r;g;b dim=r;g;b timeout=2 mode=auto|online|offline
  env: TRNL_THEME, TRNL_COLOR, TRNL_DIM, TRNL_NATIVE, TRNL_FOREIGN, TRNL_MODE, TRNL_HOME, NO_COLOR
"""


def _help_lang():
    """System UI language: Turkish -> tr, anything else -> en."""
    try:
        if sys.platform == "win32":
            import ctypes
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x1F:  # LANG_TURKISH
                return "tr"
        else:
            import locale
            loc = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or (locale.getlocale()[0] or "")
            if loc.lower().startswith("tr"):
                return "tr"
    except Exception:
        pass
    return "en"


def _out():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------- history ----------------
def _hist_file():
    return os.path.join(data_dir(), "history.tsv")


def log(src_text, res):
    if config().get("history", "on").lower() in ("off", "0", "no", "false"):
        return
    try:
        os.makedirs(data_dir(), exist_ok=True)
        clean = lambda s: (s or "").replace("\t", " ").replace("\r", " ").replace("\n", " / ")
        with open(_hist_file(), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{res.src}>{res.tgt}\t{clean(src_text)}\t{clean(res.flat())}\n")
        if os.path.getsize(_hist_file()) > 2_000_000:  # keep it small
            with open(_hist_file(), encoding="utf-8") as f:
                lines = f.readlines()[-5000:]
            with open(_hist_file(), "w", encoding="utf-8") as f:
                f.writelines(lines)
    except OSError:
        pass


def show_history(args, pal):
    if args and args[0].lower() in ("clear", "temizle", "sil"):
        for p in (_hist_file(), os.path.join(data_dir(), "shell_history")):
            try:
                os.remove(p)
            except OSError:
                pass
        return 0
    n = 50
    if args and args[0].isdigit():
        n = int(args[0])
    try:
        with open(_hist_file(), encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return 0
    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 4:
            continue
        print(f"{pal.d}{parts[2]}{pal.r}  {pal.c}{parts[3]}{pal.r}")
    return 0


# ---------------- output ----------------
def render(res, pal, indent=""):
    from trnl.core import pos_label
    lines = []
    if res.meanings and len(res.meanings) > 1:
        for i, (term, pos) in enumerate(res.meanings, 1):
            lab = pos_label(pos)
            tail = f"  {pal.d}{lab}{pal.r}" if lab else ""
            rd = res.readings[i - 1] if res.readings and i - 1 < len(res.readings) else None
            rd = f"  {pal.d}({rd}){pal.r}" if rd else ""
            lines.append(f"{indent}{pal.d}{i}.{pal.r} {pal.c}{term}{pal.r}{rd}{tail}")
    else:
        text = res.meanings[0][0] if res.meanings else (res.text or "")
        for t in text.splitlines() or [""]:
            lines.append(f"{indent}{pal.c}{t}{pal.r}")
        if res.reading:
            lines.append(f"{indent}{pal.d}{res.reading}{pal.r}")
    return "\n".join(lines)


def err(msg, pal):
    sys.stderr.write(f"{pal.d}{msg}{pal.r}\n")


def note(msg, pal):
    print(f"{pal.d}{msg}{pal.r}", flush=True)


# ---------------- clipboard (only in the terminal window that ran `trnl -c`) ----------------
_copy = {"on": False}


def plain(res):
    """What goes to the clipboard: the translation itself (first meaning of a word), no reading/labels."""
    if res.meanings:
        return res.meanings[0][0]
    return (res.text or "").strip()


def to_clipboard(text):
    if not _copy["on"] or not text:
        return
    try:
        from trnl import clip
        clip.copy(text)
    except Exception:
        pass


def copy_cmd(args, pal):
    """trnl -c [on|off] -> (exit code or None to continue, remaining args)."""
    from trnl import session
    a = args[0].lower() if args else ""
    if a in ("off", "kapat", "kapali", "kapalı", "0", "no", "hayir", "hayır"):
        try:
            session.disable()
        except Exception:
            pass
        _copy["on"] = False
        note("Panoya kopyalama kapandı.", pal)
        return 0, []
    if a in ("on", "ac", "aç", "acik", "açık", "1", "yes", "evet"):
        args = args[1:]
    try:
        ok = session.enable()
    except Exception:
        ok = False
    if not ok:
        err("Bu terminal penceresi tanınamadı, panoya kopyalama açılamadı.", pal)
        return (1 if not args else None), args
    _copy["on"] = True
    note("Panoya kopyalama açık: son çeviri panoya kopyalanır (Ctrl+V). Sadece bu terminal penceresi için;"
         " pencereyi kapatınca kendiliğinden kapanır. Kapatmak için: trnl -c off", pal)
    return (0 if not args else None), args


# ---------------- glossary commands ----------------
def glossary_cmd(op, args, pal):
    from trnl import glossary
    try:
        if op == "list":
            items = glossary.load()
            if not items:
                note("Sözlük boş. Eklemek için: trnl -a mell=molotov", pal)
                return 0
            w = max(len(k) for k, _ in items)
            for k, v in items:
                print(f"{pal.c}{k.ljust(w)}{pal.r}  {pal.d}={pal.r}  {pal.c}{v}{pal.r}")
            return 0
        text = " ".join(args).strip()
        if op == "add":
            entry = glossary.parse_entry(text)
            if not entry:
                err("Kullanım: trnl -a kelime=anlam   (örnek: trnl -a mell=molotov   /   trnl -a Kerem=Kerem)", pal)
                return 1
            glossary.add(*entry)
            same = glossary.norm_key(entry[0]) == glossary.norm_key(entry[1])
            note(f"Eklendi: {entry[0]} = {entry[1]}" + ("  (çevrilmeden aynen kalır)" if same else ""), pal)
            return 0
        if op == "remove":
            if not text:
                err("Kullanım: trnl -r kelime   (örnek: trnl -r mell)", pal)
                return 1
            key = text.partition("=")[0].strip()
            if glossary.remove(key):
                note(f"Silindi: {key}", pal)
                return 0
            err(f"Sözlükte yok: {key}   (liste: trnl -l)", pal)
            return 1
    except OSError as e:
        err(f"Sözlük kaydedilemedi: {e}", pal)
        return 1
    return 1


def one(text, forced, mode, pal):
    from trnl import core
    try:
        res = core.translate(text, forced, mode)
    except RuntimeError as e:
        err(str(e), pal)
        return 1
    print(render(res, pal), flush=True)
    log(text, res)
    to_clipboard(plain(res))
    return 0


def words_mode(items, forced, mode, pal):
    from trnl import core, online
    words = [w.strip() for w in ",".join(items).replace("\u3001", ",").replace("\uff0c", ",").split(",") if w.strip()]
    if not words:
        return 1

    def job(w):
        try:
            return w, core.translate(w, forced, mode), None
        except RuntimeError as e:
            return w, None, e

    if mode != "offline" and not online.is_offline() and len(words) > 1:
        import concurrent.futures as cf
        # probe the network with the first word, then fan out
        first = job(words[0])
        with cf.ThreadPoolExecutor(min(8, len(words) - 1)) as ex:
            rest = list(ex.map(job, words[1:]))
        results = [first] + rest
    else:
        results = [job(w) for w in words]
    blocks, rc, copied = [], 0, []
    for w, res, e in results:
        if res is None:
            blocks.append(f"{pal.d}{w}{pal.r}\n  {pal.d}{e}{pal.r}")
            rc = 1
            continue
        blocks.append(f"{pal.d}{w}{pal.r}\n{render(res, pal, '  ')}")
        log(w, res)
        copied.append(plain(res))
    print("\n\n".join(blocks), flush=True)
    to_clipboard(", ".join(c for c in copied if c))
    return rc


# ---------------- shell ----------------
def _readline():
    try:
        import readline  # Linux/macOS builtin; Windows: pyreadline3 provides it
    except Exception:
        return None, None
    path = os.path.join(data_dir(), "shell_history")
    try:
        readline.set_history_length(1000)
        if os.path.exists(path):
            readline.read_history_file(path)
    except Exception:
        pass
    return readline, path


def shell(forced, mode, pal):
    from trnl.core import normalize_lang
    tty = sys.stdin.isatty()
    rl, hpath = (None, None)
    if tty:
        os.makedirs(data_dir(), exist_ok=True)
        rl, hpath = _readline()
        sys.stdout.write("\x1b[2J\x1b[3J\x1b[H\x1b[?25h")  # clear, show cursor
        sys.stdout.flush()
    target = forced
    eofs = []
    try:
        while True:
            try:
                line = input("") if tty else sys.stdin.readline()
                if not tty and line == "":
                    break
            except EOFError:
                if not tty:
                    break
                now = time.time()  # Ctrl+D / Ctrl+Z: ignored (Ctrl+C exits); bail if stdin is dead
                eofs = [t for t in eofs if now - t < 1] + [now]
                if len(eofs) >= 3:
                    break
                continue
            line = line.strip()
            if not line:
                continue
            if rl and hpath:
                try:
                    rl.write_history_file(hpath)
                except Exception:
                    pass
            if line.startswith(":"):
                code, _, rest = line[1:].partition(" ")
                code = normalize_lang(code)
                if not rest.strip():
                    target = None if code in ("auto", "") else code
                    continue
                one(rest.strip(), None if code == "auto" else code, mode, pal)
                continue
            one(line, target, mode, pal)
    except KeyboardInterrupt:
        pass
    if tty:
        sys.stdout.write("\x1b[0m\x1b[2J\x1b[3J\x1b[H")
        sys.stdout.flush()
    return 0


def _first_run_tip(pal):
    """Windows: show the '&' tip once."""
    flag = os.path.join(data_dir(), ".amp_tip_shown")
    if os.path.exists(flag):
        return
    try:
        os.makedirs(data_dir(), exist_ok=True)
        open(flag, "w").close()
    except OSError:
        return
    from trnl import winamp
    err(winamp.AMP_TIP, pal)


def _with_quotes(argv, idx):
    """Windows: cmd hands us `Ahmet'e "Sevgi" dedim` but argv has no quotes left - get them back from the
    real command line so "Sevgi" can be kept as it is. None when unsure."""
    try:
        from trnl import winamp
        if len(argv) != len(sys.argv) - 1:  # argv was edited (e.g. `-c` removed): positions no longer match
            marked = winamp.marked_args(sys.argv[1:])
            if marked is None:
                return None
            # map by value: our argv is a sub-list of sys.argv[1:] in order
            m, j = [], 0
            for a in argv:
                while j < len(sys.argv) - 1 and sys.argv[1 + j] != a:
                    j += 1
                if j >= len(sys.argv) - 1:
                    return None
                m.append(marked[j])
                j += 1
            marked = m
        else:
            marked = winamp.marked_args(argv)
        if not marked:
            return None
        return " ".join(marked[k] for k in idx).strip() or None
    except Exception:
        return None


# ---------------- main ----------------
def main(argv=None):
    _out()
    from trnl.colors import palette
    from trnl.core import normalize_lang
    cfg = config()
    raw_argv = argv is None
    argv = list(sys.argv[1:] if argv is None else argv)
    forced, mode, words, rest = None, None, None, []
    rest_idx = []
    try:
        from trnl import session
        _copy["on"] = os.path.exists(session.state_path()) and session.is_on()
    except Exception:
        _copy["on"] = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-a", "--add") or a.startswith("--add="):
            return glossary_cmd("add", ([a[6:]] if a.startswith("--add=") else []) + argv[i + 1:], palette(cfg))
        if a in ("-r", "--remove") or a.startswith("--remove="):
            return glossary_cmd("remove", ([a[9:]] if a.startswith("--remove=") else []) + argv[i + 1:], palette(cfg))
        if a in ("-l", "--list"):
            return glossary_cmd("list", [], palette(cfg))
        if a in ("-c", "--copy") or a.startswith("--copy="):
            tail = ([a[7:]] if a.startswith("--copy=") else []) + argv[i + 1:]
            rc, left = copy_cmd(tail, palette(cfg))
            if rc is not None and not rest and not words:
                return rc
            argv = argv[:i] + left  # `trnl -c hello`: turn on, then translate
            continue
        if a in ("-h", "--help", "/?"):
            h = HELP_TR if _help_lang() == "tr" else HELP_EN
            print(h.format(cfg=os.path.join(data_dir(), "config.ini")))
            return 0
        if a in ("-v", "--version"):
            print(__version__)
            return 0
        if a in ("-s", "--setup"):
            from trnl import setup_data
            return setup_data.run(argv[i + 1:])
        if a in ("-H", "--history"):
            return show_history(argv[i + 1:], palette(cfg))
        if a in ("-o", "--offline"):
            mode = "offline"
        elif a in ("-n", "--online"):
            mode = "online"
        elif a in ("-t", "--to") and i + 1 < len(argv):
            forced = normalize_lang(argv[i + 1])
            i += 1
        elif a.startswith("--to="):
            forced = normalize_lang(a[5:])
        elif a in ("-w", "--words"):
            words = []
        elif a.startswith("--words="):
            words = [a[8:]]
        elif len(a) > 1 and a[0] == ":" and a[1:].replace("-", "").isalpha() and not rest and words in (None, []):
            forced = normalize_lang(a[1:])
        elif words is not None:
            words.append(a)
        else:
            rest.append(a)
            rest_idx.append(i)
        i += 1
    pal = palette(cfg)
    try:
        if words is not None:
            return words_mode(words + rest, forced, mode, pal)
        text = " ".join(rest).strip()
        if not text:
            return shell(forced, mode, pal)
        if sys.platform == "win32":
            from trnl import winamp
            full = winamp.check(text)
            if full:  # cmd cut the line at '&': translate what was meant, and say how to type it
                err(winamp.AMP_TIP, pal)
                text = full.replace("^", "")
            else:
                _first_run_tip(pal)
                if raw_argv and '"' not in text:
                    text = _with_quotes(argv, rest_idx) or text
        return one(text, forced, mode, pal)
    except KeyboardInterrupt:
        return 130


def entry():
    sys.exit(main())
