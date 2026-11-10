"""Online translation: Google (gtx, then dict-chrome-ex client), MyMemory as a last resort."""
import json
import threading
import time
from urllib.parse import quote

import os
GOOGLE_HOST = os.environ.get("TRNL_GOOGLE_HOST", "translate.googleapis.com")  # override for tests
_tls = threading.local()
_state = {"offline_until": 0.0, "google_client": None}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


class NetDown(Exception):
    """No connectivity (DNS / connect / timeout) - go offline right away."""


class Refused(Exception):
    """Server answered but not usefully (captcha page, 429, bad JSON)."""


def _gcode(lang):
    return {"zh": "zh-CN", "zt": "zh-TW"}.get(lang, lang)


def _norm(lang):
    if not lang:
        return lang
    lang = lang.lower()
    return "zh" if lang.startswith("zh") else lang.split("-")[0]


def _get(host, path, timeout):
    import http.client
    import socket
    import ssl
    _conns = getattr(_tls, "conns", None)
    if _conns is None:
        _conns = _tls.conns = {}
    for attempt in (0, 1):
        conn = _conns.get(host)
        if conn is None:
            conn = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
            _conns[host] = conn
        try:
            conn.request("GET", path, headers={"User-Agent": UA, "Accept": "*/*", "Connection": "keep-alive"})
            r = conn.getresponse()
            body = r.read()
            if r.getheader("Connection", "").lower() == "close":
                conn.close()
                _conns.pop(host, None)
            return r.status, body
        except (http.client.RemoteDisconnected, http.client.CannotSendRequest, BrokenPipeError,
                ConnectionResetError, http.client.BadStatusLine) as e:
            conn.close()
            _conns.pop(host, None)
            if attempt:
                raise NetDown(str(e))
        except socket.gaierror as e:  # no DNS: really offline
            conn.close()
            _conns.pop(host, None)
            raise NetDown(str(e))
        except (socket.timeout, OSError) as e:  # slow first connection: one more try, a bit longer
            conn.close()
            _conns.pop(host, None)
            if attempt:
                raise NetDown(str(e))
            timeout = max(timeout * 2, 4.0)


def is_offline():
    return time.time() < _state["offline_until"]


def mark_offline(seconds=30):
    _state["offline_until"] = time.time() + seconds


def google(text, tgt, src="auto", word=False, timeout=2.0):
    """-> dict(text=..., src=..., bd=[(pos, [(term, [reverse...], score)])])"""
    dt = ("&dt=t&dt=bd" if word else "&dt=t") + "&dt=rm"
    q = quote(text, safe="")
    clients = [_state["google_client"]] if _state["google_client"] else ["gtx", "dict-chrome-ex"]
    last = None
    for client in clients:
        path = (f"/translate_a/single?client={client}&sl={_gcode(src)}&tl={_gcode(tgt)}"
                f"&hl=en&ie=UTF-8&oe=UTF-8{dt}&q={q}")
        status, body = _get(GOOGLE_HOST, path, timeout)
        try:
            if status != 200:
                raise ValueError(status)
            j = json.loads(body.decode("utf-8"))
        except ValueError as e:
            last = Refused(f"google {client}: {e}")
            continue
        _state["google_client"] = client
        segs = j[0] or []
        out = "".join(s[0] for s in segs if s and isinstance(s[0], str))
        rm = "".join(s[2] for s in segs if s and s[0] is None and len(s) > 2 and isinstance(s[2], str))
        bd = []
        if len(j) > 1 and j[1]:
            for blk in j[1]:
                try:
                    pos = blk[0]
                    ents = []
                    for e in blk[2] or []:
                        sc = e[3] if len(e) > 3 and isinstance(e[3], (int, float)) else 0.0
                        ents.append((e[0], e[1] or [], float(sc)))
                    bd.append((pos, ents))
                except (IndexError, TypeError):
                    continue
        return {"text": out, "src": _norm(j[2] if len(j) > 2 else None), "bd": bd, "rm": rm.strip()}
    if len(clients) == 1:  # remembered client stopped working: retry both next time
        _state["google_client"] = None
    raise last or Refused("google")


def romanize(text, lang, timeout=2.0):
    """Latin reading of text written in lang (Google's transliteration), or ''."""
    path = (f"/translate_a/single?client={_state['google_client'] or 'dict-chrome-ex'}&sl={_gcode(lang)}&tl=en"
            f"&hl=en&ie=UTF-8&oe=UTF-8&dt=rm&q={quote(text, safe='')}")
    status, body = _get(GOOGLE_HOST, path, timeout)
    if status != 200:
        return ""
    j = json.loads(body.decode("utf-8"))
    return "".join(s[3] for s in (j[0] or []) if s and len(s) > 3 and isinstance(s[3], str)).strip()


def mymemory(text, src, tgt, timeout=2.0):
    path = f"/get?q={quote(text, safe='')}&langpair={_gcode(src)}|{_gcode(tgt)}"
    status, body = _get("api.mymemory.translated.net", path, timeout)
    try:
        j = json.loads(body.decode("utf-8"))
        t = j["responseData"]["translatedText"]
    except (ValueError, KeyError, TypeError):
        raise Refused("mymemory")
    if status != 200 or not t or "MYMEMORY WARNING" in t or "INVALID LANGUAGE PAIR" in t.upper():
        raise Refused("mymemory")
    return {"text": t, "src": src, "bd": []}


def google_meanings(res, word):
    """Pick up to 3 genuinely different meanings from Google's dictionary block."""
    from trnl.dictdb import norm
    main = (res.get("text") or "").strip()
    cands = []
    for pos, ents in res.get("bd") or []:
        for i, (term, rev, sc) in enumerate(ents):
            cands.append({"t": term.strip().rstrip("!").strip(), "pos": pos, "sc": sc, "i": i,
                          "rev": {norm(r) for r in rev if norm(r) != norm(word)}})
    scored = any(c["sc"] > 0 for c in cands)
    if scored:
        rank = {"noun": 0, "verb": 1, "adjective": 2, "adverb": 3}
        cands.sort(key=lambda c: (-c["sc"], rank.get(c["pos"], 9)))
        top = cands[0]["sc"] if cands else 0
        strong = [c for c in cands if c["sc"] >= top * 0.02]
        weak = [c for c in cands if c not in strong and c["sc"] >= 0.0005]
    else:  # no scores: first entry of every part of speech, plus the 2nd of the first one
        strong = [c for c in cands if c["i"] == 0]
        weak = [c for c in cands if c["i"] == 1][:1]
    out = []

    def add(c):
        k = norm(c["t"])
        if not k or k == norm(word):
            return False
        for o in out:
            if norm(o["t"]) == k:
                return False
            a, b = o["rev"], c["rev"]
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.5:
                return False  # near-synonym of an already listed meaning
        out.append(c)
        return True

    # Google's own main translation goes first
    if main:
        m = next((c for c in cands if norm(c["t"]) == norm(main)), None)
        if m:
            add(m)
        else:
            add({"t": main.rstrip("!").strip(), "pos": None, "sc": 1.0, "i": 0, "rev": set()})
    for c in strong:
        if len(out) >= 3:
            break
        add(c)
    for c in weak:
        if len(out) >= 2:
            break
        add(c)
    return [(c["t"], c["pos"]) for c in out[:3]]
