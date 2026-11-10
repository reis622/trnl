"""Translation logic: online first, offline fallback, word meanings vs. sentence."""
import re
import threading

from trnl import detect, online
from trnl.paths import config

SUPPORTED_OFFLINE = detect.LANGS
_db = None
_udb = None
_dblock = threading.Lock()


def userdb():
    global _udb
    if _udb is None:
        with _dblock:
            if _udb is None:
                from trnl.dictdb import UserDB
                _udb = UserDB()
    return _udb


def db():
    global _db
    if _db is None:
        with _dblock:
            if _db is None:
                from trnl.dictdb import DictDB
                _db = DictDB()
    return _db


_PUNCT = ".,!?;:\u00a1\u00bf\"'\u201c\u201d\u2018\u2019()[]\u3002\uff01\uff1f\u3001\u300c\u300d"


def core_word(text):
    return text.strip().strip(_PUNCT).strip()


def is_word(text):
    t = core_word(text)
    if not t or re.search(r"\s", t):
        return False
    if detect.script_lang(t) in ("ja", "zh"):
        return len(t) <= 6 and not re.search(r"[\u3001\u3002\uff01\uff1f\uff0c.,!?]", t)
    return bool(re.fullmatch(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", t))


def normalize_lang(code):
    code = (code or "").lower()
    return {"zh-cn": "zh", "cn": "zh", "jp": "ja", "zh-hans": "zh", "ger": "de", "tur": "tr", "eng": "en",
            "esp": "es", "sp": "es"}.get(code, code)


class NoOfflineData(RuntimeError):
    pass


class Result:
    def __init__(self, src, tgt, text=None, meanings=None, how=""):
        self.src, self.tgt, self.text, self.meanings, self.how = src, tgt, text, meanings or [], how
        self.reading, self.readings = None, None

    def flat(self):
        if self.meanings:
            return " | ".join(m[0] for m in self.meanings)
        return self.text or ""


def pick_target(src, forced):
    cfg = config()
    if forced:
        return forced
    return cfg["foreign"] if src == cfg["native"] else cfg["native"]


def translate(text, forced=None, mode=None, protect=True, quotes=True):
    """protect: apply the personal glossary; quotes: keep "quoted" words as they are."""
    prep = None
    if protect:
        try:
            from trnl import glossary
            hit = glossary.lookup(core_word(text))
            if hit is not None:  # a glossary word on its own: just its value
                return Result("", forced or "", hit, None, "glossary")
        except Exception:
            pass
    if protect or quotes:
        try:
            from trnl import glossary
            prep = glossary.prepare(text, quotes=quotes, items=None if protect else [])
            if prep.text == text.strip() and not prep.slots:
                prep = None
        except Exception:
            prep = None
    if prep is None:
        return _finish(_translate(text, forced, mode))
    from trnl import glossary
    only = prep.only
    if only is not None:  # the whole input is a kept name / quoted word
        return Result("", forced or "", only, None, "glossary")
    if not prep.text.strip():
        return _finish(_translate(text, forced, mode))
    hint = _src_hint(prep.literal, mode) if prep.slots else None
    res = _translate(prep.text, forced, mode, hint)
    if prep.slots:
        outs = [res.text] + [m[0] for m in res.meanings]
        if not any(glossary.has_all(o, prep.slots) for o in outs if o):
            res = _translate(prep.literal, forced, mode)  # the engine ate a token: send the words literally
        else:
            try:
                res.text = glossary.restore(res.text, prep.slots)
                res.meanings = [(glossary.restore(t, prep.slots), p) for t, p in res.meanings]
                if getattr(res, "_rm", None):
                    res._rm = glossary.restore(res._rm, prep.slots)
            except Exception:
                pass
    return _finish(res)


def _src_hint(text, mode):
    """Source language of the real text. Placeholders confuse Google's auto-detect, so ask once with the
    real words (only when something is protected)."""
    d, confident = detect.guess(text)
    if confident or (mode or config().get("mode", "auto")) == "offline" or online.is_offline():
        return d
    try:
        timeout = float(config().get("timeout") or 2)
    except ValueError:
        timeout = 2.0
    try:
        return online.google(text, "en" if d != "en" else "tr", "auto", timeout=timeout)["src"] or d
    except Exception:
        return d


def _finish(res):
    if config().get("reading", "on").lower() not in ("off", "0", "no", "false"):
        from trnl import reading
        on = res.how.startswith("google") and not online.is_offline()
        reading.attach(res, on, 2.0, getattr(res, "_rm", None))
    return res


def _translate(text, forced=None, mode=None, hint=None):
    cfg = config()
    mode = mode or cfg.get("mode", "auto")
    try:
        timeout = float(cfg.get("timeout") or 2)
    except ValueError:
        timeout = 2.0
    text = text.strip()
    word = is_word(text) and not text.endswith(("?", "\uff1f"))  # "Nasılsın?" is a question, not a lookup
    raw = text
    if word:
        text = core_word(text)
    dbo = db() if (word or mode == "offline") else None
    src, confident = detect.guess(text, dbo if word else None)
    if hint:
        src, confident = hint, True
    tgt = pick_target(src, forced)
    err = None
    if mode != "offline" and not online.is_offline():
        try:
            return _online(text, src, confident, tgt, forced, word, timeout, bool(hint))
        except online.NetDown as e:
            online.mark_offline(30)
            err = e
        except online.Refused as e:
            err = e
    if mode == "online":
        raise RuntimeError("çevrimiçi çeviri yapılamadı: %s" % err)
    try:
        return _offline(text, src, tgt, word, raw)
    except NoOfflineData:
        if err is not None:  # online failed and nothing is installed offline: say what really happened
            raise RuntimeError("internetten çeviri alınamadı (bağlantı yavaş ya da yok), tekrar dene."
                               " İnternetsiz kullanım için: trnl -s")
        raise


def _online(text, src, confident, tgt, forced, word, timeout, pin=False):
    cfg = config()
    sl = src if ((word or pin) and confident) else "auto"
    try:
        res = online.google(text, tgt, sl, word=word, timeout=timeout)
        gsrc = res["src"] or src
        if not forced and gsrc == tgt:  # e.g. we guessed English but it is Turkish
            tgt = cfg["foreign"] if gsrc == cfg["native"] else cfg["native"]
            res = online.google(text, tgt, sl if sl != "auto" else "auto", word=word, timeout=timeout)
            gsrc = res["src"] or gsrc
        if word and sl == "auto" and not res["bd"] and gsrc and gsrc != "auto":
            try:  # dictionary block often needs an explicit source language
                r2 = online.google(text, tgt, gsrc, word=True, timeout=timeout)
                if r2["bd"]:
                    res = r2
            except online.Refused:
                pass
        if word:
            means = online.google_meanings(res, text)
            if text[:1].islower() and tgt not in ("de",):
                means = [((t[:1].lower() + t[1:]) if t[:1].isupper() and not t.isupper() else t, p)
                         for t, p in means]
            if len(means) < 2 and gsrc in SUPPORTED_OFFLINE and tgt in SUPPORTED_OFFLINE and db().ok:
                # Google has no dictionary for this pair (e.g. es->tr): try the bundled one
                from trnl.dictdb import norm
                local = db().lookup(text, gsrc, tgt)
                first = norm(means[0][0] if means else res["text"] or "")
                if len(local) >= 2 and any(first == norm(t) for m in local for t in m[2]):
                    for i, m in enumerate(local):
                        if any(first == norm(t) for t in m[2]):
                            local.insert(0, local.pop(i))
                            break
                    r = Result(gsrc, tgt, res["text"], [(m[0], m[1]) for m in local], "google+dict")
                    r._rm = res.get("rm")
                    return r
            if means:
                if gsrc in SUPPORTED_OFFLINE and tgt in SUPPORTED_OFFLINE:
                    userdb().save(text, gsrc, tgt, means)  # remember for offline use
                r = Result(gsrc, tgt, res["text"], means, "google")
                r._rm = res.get("rm")
                return r
        r = Result(gsrc, tgt, res["text"], None, "google")
        r._rm = res.get("rm")
        return r
    except online.Refused:
        res = online.mymemory(text, src if src in SUPPORTED_OFFLINE else "en", tgt, timeout)
        return Result(src, tgt, res["text"], None, "mymemory")


def _pivot_meanings(text, src, tgt):
    from trnl import offline
    from trnl.dictdb import _strip_to
    out, seen = [], set()
    for i, (term, pos, alts) in enumerate(db().kaikki(text, src)):
        en = term[3:] if term.startswith("to ") else term
        if len(en.split()) > 2:
            continue  # long glosses do not pivot well
        hit = db().wikdict(en, "en", tgt)
        if hit:
            t = hit[0][0]
        elif not out:  # MT only for the first (main) meaning
            try:
                t = offline.translate_word(en, "en", tgt)
            except Exception:
                continue
        else:
            continue
        k = _strip_to(t)
        if k and k not in seen:
            seen.add(k)
            out.append((t, pos, [t]))
    return out


def _offline(text, src, tgt, word, raw=None):
    from trnl import offline
    if src not in SUPPORTED_OFFLINE:
        src = "en"
    if tgt not in SUPPORTED_OFFLINE:
        raise RuntimeError(f"çevrimdışı '{tgt}' yok (sadece en, de, tr, es, ja, zh)")
    if src == tgt:
        return Result(src, tgt, text, None, "same")
    if offline.route(src, tgt) is None:
        raise NoOfflineData("çevrimdışı veri yok: önce 'trnl -s' çalıştır (internet gerekir)")
    if word and src == "zh" and db().ok and not db().kaikki(text, "zh") and db().kaikki(text, "ja"):
        src = "ja"  # kanji-only word that only Japanese knows
        if tgt == "ja":
            tgt = config()["native"]
    if word:
        cached = userdb().get(text, src, tgt)  # 1) meanings learnt online earlier
        if cached:
            return Result(src, tgt, None, [(m[0], m[1]) for m in cached], "cache")
        means = db().lookup(text, src, tgt) if db().ok else []  # 2) Wiktionary (kaikki + WikDict)
        if not means and src != "en" and tgt != "en" and db().ok:
            means = _pivot_meanings(text, src, tgt)  # e.g. ja/zh -> en glosses -> tr
        if len(means) >= 2:
            try:  # put the MT's choice first when it is one of the dictionary senses
                from trnl.dictdb import _strip_to
                mt = _strip_to(offline.translate_word(text, src, tgt))
                for i, m in enumerate(means):
                    if mt and any(_strip_to(t) == mt for t in m[2]):
                        means.insert(0, means.pop(i))
                        break
            except Exception:
                pass
        if means:
            return Result(src, tgt, None, [(m[0], m[1]) for m in means], "dict")
        if raw and raw != text:  # "Nasılsın?" - the punctuation helps the sentence model
            return Result(src, tgt, offline.translate(raw, src, tgt), None, "argos")
        return Result(src, tgt, offline.translate_word(text, src, tgt), None, "argos-word")
    return Result(src, tgt, offline.translate(text, src, tgt), None, "argos")


# ---- part-of-speech labels (Wiktionary + Google names -> short label) ----
_POS_TR = [
    (("proper_noun", "özel_ad", "專有名詞", "专有名词", "固有名詞", "sustantivo_propio", "name", "eigenname"), "özel isim"),
    (("noun", "substantiv", "sustantivo", "名詞", "名词", "ad", "isim", "adjectivenoun"), "isim"),
    (("verb", "eylem", "verbo", "動詞", "动词", "fiil"), "fiil"),
    (("adjective", "adjektiv", "adjetivo", "sıfat", "ön_ad", "形容詞", "形容词", "adj"), "sıfat"),
    (("adv",), "zarf"),
    (("intj",), "ünlem"),
    (("num",), "sayı"),
    (("postp",), "edat"),
    (("pron",), "zamir"),
    (("conj",), "bağlaç"),
    (("det",), "belirleyici"),
    (("adverb", "belirteç", "adverbio", "副詞", "副词", "lokaladverb", "temporaladverb"), "zarf"),
    (("interjection", "ünlem", "interjektion", "interjección", "感動詞", "感嘆詞", "感叹词"), "ünlem"),
    (("pronoun", "adıl", "pronomen", "personalpronomen", "indefinitpronomen", "pronombre", "代名詞", "代词"), "zamir"),
    (("preposition", "präposition", "preposición", "edat", "ilgeç"), "edat"),
    (("conjunction", "konjunktion", "subjunktion", "conjunción", "bağlaç"), "bağlaç"),
    (("numeral", "number", "numerale", "sayı", "numeral_cardinal"), "sayı"),
    (("phrase", "locución", "redewendung", "wortverbindung", "idiom", "deyim", "成語"), "deyim"),
    (("abbreviation", "abkürzung", "kısaltma"), "kısaltma"),
    (("prefix", "suffix", "sufijo", "prefijo", "ek"), "ek"),
    (("article", "artikel", "artículo", "tanımlık"), "tanımlık"),
    (("particle", "partikel", "助詞"), "edat"),
]
_POS_EN = {"belirleyici": "det", "özel isim": "proper noun", "isim": "noun", "fiil": "verb", "sıfat": "adj", "zarf": "adv",
           "ünlem": "interj", "zamir": "pron", "edat": "prep", "bağlaç": "conj", "sayı": "num", "deyim": "phrase",
           "kısaltma": "abbr", "ek": "affix", "tanımlık": "article"}


def pos_label(pos):
    if not pos:
        return ""
    p = pos.lower().replace(" ", "_")
    for keys, label in _POS_TR:
        for k in keys:
            if p == k or p.startswith(k + "_") or (len(k) > 3 and p.startswith(k)):
                return label if config()["native"] == "tr" else _POS_EN[label]
    return ""
