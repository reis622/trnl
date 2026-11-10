"""Offline neural MT: CTranslate2 + SentencePiece on Argos/OPUS models (pivot via English)."""
import os
import re
import threading

from trnl.paths import models_dir

_cache = {}
_lock = threading.Lock()
_SENT = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+|(?<=[\u3002\uff01\uff1f])")


def pair_dir(src, tgt):
    return os.path.join(models_dir(), f"{src}_{tgt}")


def have(src, tgt):
    d = pair_dir(src, tgt)
    return os.path.exists(os.path.join(d, "model", "model.bin")) or os.path.exists(os.path.join(d, "model.bin"))


def engine(src, tgt):
    """'opus' (OPUS-MT converted, source/target spm) or 'argos'."""
    return "opus" if os.path.exists(os.path.join(pair_dir(src, tgt), "trnl.json")) else "argos"


def route(src, tgt):
    if src == tgt:
        return []
    if have(src, tgt):
        return [(src, tgt)]
    if src != "en" and tgt != "en" and have(src, "en") and have("en", tgt):
        return [(src, "en"), ("en", tgt)]
    return None


def _load(src, tgt):
    key = (src, tgt)
    if key in _cache:
        return _cache[key]
    with _lock:
        return _load_locked(src, tgt, key)


class _Model:
    __slots__ = ("sp_src", "sp_tgt", "tr", "prefix", "norm")


_OPUS_NORM = str.maketrans({"\uff0c": ",", "\u3002": ".", "\u3001": ",", "\u201d": '"', "\u201c": '"',
                            "\uff1a": ":", "\uff1f": "?", "\uff01": "!", "\uff08": "(", "\uff09": ")",
                            "\uff1b": ";"})


def _load_locked(src, tgt, key):
    if key not in _cache:
        import ctranslate2
        import sentencepiece as spm
        d = pair_dir(src, tgt)
        threads = max(1, min(4, os.cpu_count() or 1))
        m = _Model()
        if engine(src, tgt) == "opus":
            import json
            with open(os.path.join(d, "trnl.json"), encoding="utf-8") as f:
                meta = json.load(f)
            m.sp_src = spm.SentencePieceProcessor(model_file=os.path.join(d, "source.spm"))
            m.sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(d, "target.spm"))
            m.prefix = meta.get("prefix") or ""
            m.norm = True
            mdir = d
        else:
            m.sp_src = m.sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(d, "sentencepiece.model"))
            m.prefix, m.norm = "", False
            mdir = os.path.join(d, "model")
        m.tr = ctranslate2.Translator(mdir, device="cpu", compute_type=_compute_type(), inter_threads=1,
                                      intra_threads=threads)
        _cache[key] = m
    return _cache[key]


def _compute_type():
    try:
        from trnl.paths import config
        ct = (config().get("compute") or "auto").strip().lower()
    except Exception:
        ct = "auto"
    return ct if ct in ("auto", "int8", "int8_float32", "int16", "float32") else "auto"


def _clean(s):
    s = s.replace("\u2581", " ").replace(" \u2047 ", " ").replace("\u2047", "").replace("<unk>", "")
    return re.sub(r"\s+", " ", s).strip()


def _run(src, tgt, sentences, beam=4, nhyp=1, short=False):
    m = _load(src, tgt)
    with _lock:
        return _run_locked(m, sentences, beam, nhyp, short)


def _run_locked(m, sentences, beam, nhyp, short):
    if m.norm:
        sentences = [s.translate(_OPUS_NORM) for s in sentences]
    toks = [m.sp_src.encode(s, out_type=str) for s in sentences]
    if m.prefix:
        toks = [[m.prefix] + t for t in toks]
    longest = max(len(t) for t in toks)
    kw = dict(beam_size=beam, num_hypotheses=nhyp, return_scores=False)
    if short:
        kw["max_decoding_length"] = longest * 2 + 4
        kw["no_repeat_ngram_size"] = 2
    else:  # length cap + n-gram block stop the "早,早,早,..." loops on short inputs
        kw["max_decoding_length"] = min(512, longest * 3 + 12)
        kw["repetition_penalty"] = 1.05
        kw["no_repeat_ngram_size"] = 4
    res = m.tr.translate_batch(toks, **kw)
    return [[_clean(m.sp_tgt.decode(h)) for h in r.hypotheses] for r in res]


def split_sentences(text):
    parts = [p.strip() for p in _SENT.split(text) if p and p.strip()]
    return parts or [text]


def translate(text, src, tgt):
    steps = route(src, tgt)
    if steps is None:
        raise LookupError(f"{src}->{tgt}")
    lines = text.splitlines() or [text]
    out_lines = []
    for line in lines:
        if not line.strip():
            out_lines.append("")
            continue
        sents = split_sentences(line)
        for a, b in steps:
            sents = [h[0] for h in _run(a, b, sents)]
        joiner = "" if steps[-1][1] in ("ja", "zh") else " "
        out_lines.append(joiner.join(sents))
    return "\n".join(out_lines)


def _dedupe_words(s):
    out = []
    for w in s.split():
        if out and out[-1].lower() == w.lower():
            continue
        out.append(w)
    return " ".join(out)


def translate_word(word, src, tgt):
    """Single word: models loop on bare words, so feed 'Word.' and strip the period."""
    steps = route(src, tgt)
    if steps is None:
        raise LookupError(f"{src}->{tgt}")
    cur = word
    for a, b in steps:
        cjk = a in ("ja", "zh")
        inp = cur if cjk else (cur[:1].upper() + cur[1:] + ".")
        hyps = _run(a, b, [inp], beam=5, nhyp=5, short=True)[0]
        pick = None
        for h in hyps:
            h2 = h.strip().rstrip(".\u3002!\uff01").strip(" \"'\u201c\u201d\u300c\u300d")
            if h2 and h2.lower() != cur.lower():
                pick = h2
                break
        if pick is None:  # fallback: bare word, collapse "x x x"
            hyps = _run(a, b, [cur], beam=5, nhyp=5, short=True)[0]
            pick = _dedupe_words(hyps[0]) if hyps else cur
        if (not cur[:1].isupper() and pick[:1].isupper() and b not in ("de",)
                and not (b == "en" and (pick == "I" or pick.startswith(("I ", "I'", "I\u2019"))))):
            pick = pick[:1].lower() + pick[1:]
        cur = pick
    return cur
