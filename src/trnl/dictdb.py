"""Offline dictionaries.

Lookup order for a single word (offline):
  1. user.db   - meanings cached from earlier online (Google dictionary) lookups
  2. kaikki    - English Wiktionary glosses for tr/ja/zh(/de/es) words (sense order = common first)
  3. wikdict   - WikDict translation tables (all 30 pairs)
Callers fall back to machine translation when nothing is found.
"""
import os
import re
import sqlite3
import threading
import time

from trnl.paths import data_dir, dict_path

# source dictionaries used to decide which language a word belongs to
_MEMBER = {"en": "en_tr", "tr": "tr_en", "de": "de_en", "es": "es_en"}


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum() or ch == " ").strip()


def _strip_to(s):
    s = norm(s)
    return s[3:] if s.startswith("to ") else s


class DictDB:
    def __init__(self, path=None):
        path = path or dict_path()
        self.ok = os.path.exists(path)
        self.con = None
        self.lock = threading.Lock()
        self.has_k = False
        if self.ok:
            self.con = sqlite3.connect(path, check_same_thread=False)
            self.has_k = bool(self.con.execute(
                "select 1 from sqlite_master where type='table' and name='k'").fetchone())

    def _q(self, sql, args):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def membership(self, words):
        if not self.con:
            return {}
        out = {}
        for lang, pair in _MEMBER.items():
            n = sum(1 for w in set(words) if self._q("select 1 from t where p=? and wl=? limit 1", (pair, w)))
            if n:
                out[lang] = n
        return out

    # ---- WikDict ----
    def wikdict(self, word, src, tgt):
        """[(term, pos, all_terms)] ranked, distinct, max 3."""
        if not self.con:
            return []
        rows = self._q("select w, pos, tr, sc, im from t where p=? and wl=?", (f"{src}_{tgt}", word.lower()))
        if not rows:
            return []
        exact = [r for r in rows if r[0] == word]
        if exact and len(exact) != len(rows) and word != word.lower():
            rows = exact
        rows.sort(key=lambda r: (-(r[3] or 0), -(r[4] or 0)))
        top = rows[0][3] or 0
        limit = max(50.0, top * 0.45)
        out, seen = [], set()
        for w, pos, tl, sc, im in rows:
            if out and ((sc or 0) < limit or (im is not None and im < 0.01)):
                continue  # weak / rare sense: never pad
            terms = [t.strip() for t in (tl or "").split("|") if t.strip()]
            if not terms:
                continue
            key = norm(terms[0])
            if key in seen or key == norm(word):
                if key == norm(word) and len(terms) > 1 and norm(terms[1]) not in seen:
                    terms = terms[1:]
                    key = norm(terms[0])
                else:
                    continue
            seen.update(norm(t) for t in terms)
            out.append((terms[0], pos, terms))
            if len(out) == 3:
                break
        return out

    # ---- kaikki (English Wiktionary glosses, X -> en) ----
    def kaikki(self, word, src):
        if not (self.con and self.has_k):
            return []
        rows = self._q("select w, ent, sn, pos, term, alts from k where l=? and wl=?", (src, word.lower()))
        if not rows:
            return []
        exact = [r for r in rows if r[0] == word]
        if exact and len(exact) != len(rows):
            rows = exact
        rows.sort(key=lambda r: (r[2], r[1]))  # first sense of every entry, then second senses, ...
        out, seen = [], set()
        for w, ent, sn, pos, term, alts in rows:
            al = [a for a in (alts or term).split("|") if a]
            keys = {_strip_to(a) for a in al}
            if keys & seen:
                continue
            seen |= keys
            out.append((term, pos, al))
            if len(out) == 3:
                break
        return out

    def lookup(self, word, src, tgt):
        """Best offline meanings: kaikki (when target is English) merged with WikDict."""
        k = self.kaikki(word, src) if tgt == "en" else []
        w = self.wikdict(word, src, tgt)
        if not k:
            return w
        if len(k) >= 2:
            return k
        seen = {_strip_to(a) for m in k for a in m[2]}
        for m in w:
            if len(k) >= 2:
                break
            if not ({_strip_to(a) for a in m[2]} & seen):
                k.append(m)
                seen |= {_strip_to(a) for a in m[2]}
        return k


class UserDB:
    """Meanings learnt from online lookups, so they also show up offline later."""

    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "user.db")
        self.con = None
        self.lock = threading.Lock()

    def _open(self):
        if self.con is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.con = sqlite3.connect(self.path, check_same_thread=False, timeout=2)
            self.con.execute("create table if not exists g(src TEXT, tgt TEXT, wl TEXT, ord INT, term TEXT, "
                             "pos TEXT, ts INT)")
            self.con.execute("create index if not exists gi on g(src, tgt, wl)")
        return self.con

    def save(self, word, src, tgt, means):
        if not means:
            return
        try:
            with self.lock:
                c = self._open()
                wl = word.lower()
                c.execute("delete from g where src=? and tgt=? and wl=?", (src, tgt, wl))
                c.executemany("insert into g values(?,?,?,?,?,?,?)",
                              [(src, tgt, wl, i, t, p, int(time.time())) for i, (t, p) in enumerate(means[:3])])
                c.commit()
        except sqlite3.Error:
            pass

    def get(self, word, src, tgt):
        if not os.path.exists(self.path):
            return []
        try:
            with self.lock:
                rows = self._open().execute("select term, pos from g where src=? and tgt=? and wl=? order by ord",
                                            (src, tgt, word.lower())).fetchall()
        except sqlite3.Error:
            return []
        return [(t, p, [t]) for t, p in rows]


# ---- kaikki import (used by --setup) ----
_SKIP_TAGS = {"form-of", "alt-of", "obsolete", "archaic", "rare", "dated", "historical", "dialectal",
              "misspelling", "nonstandard", "obsolete-form", "romanization"}
_SKIP_POS = {"name", "character", "symbol", "punct", "romanization", "suffix", "prefix", "infix", "affix",
             "soft-redirect", "syllable"}
_FORMISH = re.compile(r"^(plural|inflection|alternative|obsolete|archaic|romanization|definite|indefinite|"
                      r"first|second|third|nominative|accusative|dative|genitive|ablative|locative|past|present|"
                      r"misspelling|abbreviation|initialism|synonym|form) .*\bof\b", re.I)
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def clean_gloss(g):
    g = _PAREN.sub("", g or "").strip()
    parts = []
    for chunk in re.split(r"[;,]", g):
        c = chunk.strip().rstrip(".").strip()
        c = re.sub(r"^(a|an|the) ", "", c, flags=re.I)
        if c[:1].isupper() and not c.isupper() and c[1:2].islower():
            c = c[:1].lower() + c[1:]
        if c and len(c) <= 40 and c.lower() not in [p.lower() for p in parts]:
            parts.append(c)
    return parts


_ZH_DIALECT = {"Hokkien", "Cantonese", "Teochew", "Hakka", "Wu", "Min-Nan", "Min-Dong", "Gan", "Xiang", "Jin",
               "Zhangzhou-Hokkien", "Xiamen-Hokkien", "Taiwanese-Hokkien", "Classical-Chinese", "Shanghainese",
               "literary", "Puxian-Min", "Teochew-Min", "Leizhou-Min", "Hainanese", "Taishanese"}


def kaikki_rows(lines, lang):
    """Yield (l, wl, w, ent, sn, pos, term, alts) from kaikki.org JSONL lines."""
    import json
    ent_count = {}
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        w, pos = d.get("word"), d.get("pos")
        if not w or len(w) > 40 or pos in ("counter", "classifier") or (
                pos in _SKIP_POS and not (lang == "zh" and pos == "character")):
            continue
        keys = [w]
        if lang == "zh":  # traditional headword -> also index its simplified spelling
            keys += [f["form"] for f in d.get("forms") or []
                     if "Simplified-Chinese" in (f.get("tags") or []) and f.get("form") and f["form"] != w]
        ent = ent_count.get(w, 0)
        ent_count[w] = ent + 1
        sn = 0
        for s in d.get("senses") or []:
            gl = s.get("glosses") or []
            tags = set(s.get("tags") or [])
            if len(gl) != 1 or tags & _SKIP_TAGS or s.get("form_of") or s.get("alt_of"):
                continue
            if lang == "zh" and tags & _ZH_DIALECT:
                continue
            if _FORMISH.match(gl[0]):
                continue
            parts = clean_gloss(gl[0])
            if not parts:
                continue
            term = next((x for x in parts if len(x.split()) <= 3), parts[0])
            for kw in keys:
                yield (lang, kw.lower(), kw, ent, sn, pos, term, "|".join(parts))
            sn += 1
            if sn >= 6:
                break
