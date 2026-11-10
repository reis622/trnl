"""Offline source-language guess for en/de/tr/es/ja/zh (+ script hints for others)."""
import re

LANGS = ("en", "tr", "de", "es", "ja", "zh")

_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_CYR = re.compile(r"[\u0400-\u04ff]")
_ARAB = re.compile(r"[\u0600-\u06ff]")
_GREEK = re.compile(r"[\u0370-\u03ff]")
_WORD = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)

_STOP = {
    "en": set("the a an is are was were be been to of and in on at for with this that it you i he she we they "
              "my your what how why where when who not do does did have has can will would there here "
              "hello hi please thanks yes no".split()),
    "tr": set("ve bir bu şu o ne nasıl neden nerede kim ben sen biz siz onlar mı mi mu mü değil var yok "
              "için ile gibi çok daha en ama fakat evet hayır merhaba selam teşekkür ederim günaydın iyi "
              "hiç her şey da de ki ya".split()),
    "de": set("der die das ein eine einen dem den des ist sind war und oder nicht ich du er sie wir ihr "
              "mit von zu auf für ist bin bist hat haben wie was wo warum guten morgen tag danke bitte "
              "ja nein hallo auch noch schon sehr".split()),
    "es": set("el la los las un una unos es son está están y o no yo tú él ella nosotros con de del por "
              "para que qué cómo dónde por porque muy hola gracias sí buenos buenas días mi tu su "
              "pero también".split()),
}
_TR_SUFFIX = re.compile(r"(yor|yorum|yorsun|iyor|ıyor|uyor|üyor|mak|mek|lar|ler|ları|leri|sın|sin|sun|sün|"
                        r"sınız|siniz|dır|dir|dur|dür|mış|miş|muş|müş|acak|ecek|ım|im|um|üm|dan|den|tan|ten)$")


def script_lang(text):
    if _KANA.search(text):
        return "ja"
    if _HAN.search(text):
        return "zh"
    if _HANGUL.search(text):
        return "ko"
    if _CYR.search(text):
        return "ru"
    if _ARAB.search(text):
        return "ar"
    if _GREEK.search(text):
        return "el"
    return None


def guess(text, dictdb=None):
    """Return (lang, confident). lang is never None (defaults to en)."""
    s = script_lang(text)
    if s:
        return s, True
    low = text.lower()
    words = _WORD.findall(low)
    score = {"en": 0.0, "tr": 0.0, "de": 0.0, "es": 0.0}
    # characters
    score["tr"] += 3 * sum(low.count(c) for c in "ğış") + 3 * text.count("İ")
    score["tr"] += sum(low.count(c) for c in "ç")
    score["de"] += 3 * sum(low.count(c) for c in "äß")
    for c in "öü":
        n = low.count(c)
        score["tr"] += n
        score["de"] += n
    score["es"] += 3 * sum(low.count(c) for c in "ñ¿¡") + 2 * sum(low.count(c) for c in "áéíóú")
    confident = any(v >= 3 for v in score.values())
    # function words
    for w in words:
        for lang, st in _STOP.items():
            if w in st:
                score[lang] += 2
    # Turkish suffixes
    for w in words:
        if len(w) > 4 and _TR_SUFFIX.search(w):
            score["tr"] += 0.6
    # dictionary membership
    if dictdb is not None and words:
        hits = dictdb.membership(words[:12])
        for lang, n in hits.items():
            score[lang] += n
        if len(words) == 1 and hits:
            # single word: first language (en > tr > de > es) that knows it, unless chars disagree
            known = [l for l in ("en", "tr", "de", "es") if hits.get(l)]
            if known and not confident:
                return known[0], True
    best = max(("en", "tr", "de", "es"), key=lambda l: (score[l], l == "en"))
    if score[best] == 0:
        return "en", False
    return best, confident or score[best] >= 2
