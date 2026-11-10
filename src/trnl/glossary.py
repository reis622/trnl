"""Personal glossary (slang, proper names) + "quoted" words kept as they are.

How it reaches the translator (tested against Google):
  * key=value with a different value (mell=molotov): the source word is replaced by the value before translating,
    so the engine translates/inflects it naturally ("Please don't take Molotovs ...").
  * key=key (Kerem=Kerem) and "quoted" words: replaced by a placeholder token (ZZQ0, ZZQ1 ...) that Google keeps
    verbatim, then the token is swapped back to the exact text afterwards.
Every function here is defensive: on any error the text goes through untouched.
"""
import os
import re

from trnl.paths import data_dir

TOKEN = "ZZQ{}"
_TOKEN_RE = re.compile(r"Z\s?Z\s?Q\s?(\d{1,2})", re.IGNORECASE)
_L = r"[^\W\d_]"
# Turkish suffix morphemes that may follow a glossary word without an apostrophe (melli, mellden, mellleri ...)
_SUF = (r"(?:l[ae]r|l[ıiuü]k|l[ıiuü]|s[ıiuü]z|n[ıiuü]n|[ıiuü]n|y[ıiuü]|n[ıiuü]|s[ıiuü]|[ıiuü]m|[ıiuü]|y[ae]|n[ae]|[ae]|"
        r"n?[dt][ae]n|n?[dt][ae]|ki|y?l[ae]|c[ıiuü]|ç[ıiuü]|m)")


def _tail(key):
    suf = _SUF
    if key[-1:].lower() == "l":  # mell + ler written "melleri": the l is shared
        suf = _SUF[:-1] + r"|[ae]r)"
    return r"(?P<tail>['\u2019]" + _L + r"*|" + suf + r"{1,4})?(?!\w)"
_TR_PAIRS = {"i": "iİ", "ı": "ıI", "I": "Iı", "İ": "İi"}


def path():
    return os.path.join(data_dir(), "glossary.tsv")


def norm_key(s):
    return " ".join((s or "").replace("İ", "i").replace("I", "ı").lower().split())


def load():
    """-> list of (key, value), file order."""
    out = []
    try:
        with open(path(), encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.rstrip("\r\n").partition("\t")
                if sep and k.strip() and v.strip():
                    out.append((k.strip(), v.strip()))
    except (OSError, UnicodeDecodeError):
        pass
    return out


def _save(items):
    os.makedirs(data_dir(), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for k, v in items:
            f.write(f"{k}\t{v}\n")
    os.replace(tmp, path())


def parse_entry(text):
    """'mell=molotov' / 'kanka naber = hey buddy' -> (key, value) or None."""
    k, sep, v = (text or "").partition("=")
    k, v = " ".join(k.split()).strip('"'), " ".join(v.split()).strip('"')
    if not sep or not k or not v or "\t" in k + v:
        return None
    return k, v


def add(key, value):
    items = [(k, v) for k, v in load() if norm_key(k) != norm_key(key)]
    items.append((key, value))
    _save(items)


def remove(key):
    items = load()
    keep = [(k, v) for k, v in items if norm_key(k) != norm_key(key)]
    if len(keep) == len(items):
        return False
    _save(keep)
    return True


def lookup(word, items=None):
    """Exact glossary hit for a single word/phrase (case-insensitive) -> value or None."""
    n = norm_key(word)
    for k, v in (load() if items is None else items):
        if norm_key(k) == n:
            return v
    return None


def _pattern(key):
    parts = []
    for word in key.split():
        cls = []
        for c in word:
            alts = set(_TR_PAIRS.get(c, "")) | {c, c.lower(), c.upper()}
            alts = {a for a in alts if len(a) == 1}
            cls.append("[" + "".join(re.escape(a) for a in sorted(alts)) + "]" if len(alts) > 1 else re.escape(c))
        parts.append("".join(cls))
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + _tail(key))


# ---------------- quotes ----------------
_QUOTES = {'"': '"', "\u201c": "\u201d", "\u201e": "\u201d", "\u00ab": "\u00bb", "\u300c": "\u300d"}


def split_quotes(text):
    """-> list of (segment, protected). A text that is one quoted block as a whole ("rock & roll") is NOT
    protected - it is just the way to type a sentence with & in cmd."""
    t = text.strip()
    if len(t) >= 2 and t[0] in _QUOTES and t.endswith(_QUOTES[t[0]]) and not any(
            q in t[1:-1] for q in set(_QUOTES) | set(_QUOTES.values())):
        return [(t[1:-1], False)]
    out, buf, i = [], "", 0
    while i < len(text):
        c = text[i]
        if c in _QUOTES:
            j = text.find(_QUOTES[c], i + 1)
            inner = text[i + 1:j] if j > 0 else ""
            if j > 0 and inner.strip():
                if buf:
                    out.append((buf, False))
                    buf = ""
                out.append((inner.strip(), True))
                i = j + 1
                continue
        buf += c
        i += 1
    if buf:
        out.append((buf, False))
    return out


# ---------------- apply / restore ----------------
class Prepared:
    def __init__(self, text, slots, literal):
        self.text = text        # what goes to the translator
        self.slots = slots      # token index -> original text to put back
        self.literal = literal  # same text with values written literally (fallback if a token gets lost)

    @property
    def only(self):
        """The whole input was one protected thing -> that thing, else None."""
        m = re.fullmatch(r"\s*" + _TOKEN_RE.pattern + r"\s*", self.text, re.IGNORECASE)
        return self.slots.get(int(m.group(1))) if m else None


def prepare(text, quotes=True, items=None):
    items = load() if items is None else items
    segs = split_quotes(text) if quotes else [(text, False)]
    slots = {}

    def slot(value):
        n = len(slots)
        slots[n] = value
        return TOKEN.format(n)

    out, lit = [], []
    rules = sorted(items, key=lambda kv: -len(kv[0]))  # longest key first
    for seg, prot in segs:
        if prot:
            out.append(slot(seg))
            lit.append(seg)
            continue
        s, s_lit = seg, seg
        for k, v in rules:
            try:
                pat = _pattern(k)
            except re.error:
                continue
            keep = norm_key(k) == norm_key(v)  # a name: keep it exactly

            def rep(m, lit_mode=False):
                tail = m.group("tail") or ""
                if k[-1:].lower() == "l" and tail[:2].lower() in ("er", "ar"):
                    tail = "l" + tail  # melleri -> molotov + leri
                if keep and not lit_mode:
                    if tail and tail[0] not in "'\u2019":
                        tail = "'" + tail
                    return slot(v) + tail
                return v + tail

            s = pat.sub(rep, s)
            s_lit = pat.sub(lambda m: rep(m, True), s_lit)
        out.append(s)
        lit.append(s_lit)
    return Prepared(_join(out), slots, _join(lit))


def _join(parts):
    return re.sub(r"[ \t]{2,}", " ", "".join(parts)).strip()


def has_all(out, slots):
    found = {int(m.group(1)) for m in _TOKEN_RE.finditer(out or "")}
    return all(i in found for i in slots)


def restore(out, slots):
    if not out or not slots:
        return out
    return _TOKEN_RE.sub(lambda m: slots.get(int(m.group(1)), m.group(0)), out)
