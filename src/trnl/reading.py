"""Latin-alphabet readings for results written in another script (ja, zh, ru, ko, ar, ...)."""
import concurrent.futures as cf
import unicodedata

_kks = None


def needs(text):
    """True when the text has letters that are not Latin."""
    for ch in text or "":
        if ch.isalpha():
            try:
                if not unicodedata.name(ch).startswith("LATIN"):
                    return True
            except ValueError:
                return True
    return False


def local(text, lang):
    """Offline reading: Japanese (pykakasi) and Chinese (pypinyin) only."""
    global _kks
    try:
        if lang == "ja":
            if _kks is None:
                import pykakasi
                _kks = pykakasi.kakasi()
            return " ".join(x["hepburn"] for x in _kks.convert(text) if x["hepburn"].strip()).replace(" ,", ",").strip() or None
        if lang == "zh":
            from pypinyin import pinyin
            return " ".join(p[0] for p in pinyin(text)).strip() or None
    except Exception:
        return None
    return None


def one(text, lang, online_ok=True, timeout=2.0):
    if not needs(text):
        return None
    if online_ok:
        from trnl import online
        try:
            r = online.romanize(text, lang, timeout)
            if r:
                return r
        except Exception:
            pass
    return local(text, lang)


def attach(res, online_ok=True, timeout=2.0, main_reading=None):
    """Fill res.reading (sentence / single meaning) and res.readings (one per meaning)."""
    try:
        if res.meanings and len(res.meanings) > 1:
            terms = [m[0] for m in res.meanings]
            if not any(needs(t) for t in terms):
                return res
            known = {res.text: main_reading} if (res.text and main_reading) else {}
            with cf.ThreadPoolExecutor(len(terms)) as ex:
                res.readings = list(ex.map(
                    lambda t: known.get(t) or one(t, res.tgt, online_ok, timeout), terms))
        else:
            text = res.meanings[0][0] if res.meanings else (res.text or "")
            if not needs(text):
                return res
            if main_reading and (not res.meanings or text == res.text):
                res.reading = main_reading
            else:
                res.reading = one(text, res.tgt, online_ok, timeout)
    except Exception:
        pass
    return res
