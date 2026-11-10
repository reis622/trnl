"""cmd.exe splits `trnl a & b` before trnl runs. We cannot stop that, but on Windows we can see the
line the user really typed (conhost keeps cmd.exe's command history) and warn - and translate the whole text."""
import sys

AMP_TIP = "Not: Metinde & (ampersand) kullanacaksanız cümleyi çift tırnak içinde yazın: trnl \"rock & roll\""


def split_operator(line):
    """Return (before, after) at the first '&' / '&&' that is not quoted or ^-escaped, or None.
    ('|' is left alone: `trnl hello | clip` is a real pipe.)"""
    q = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            q = not q
        elif c == "^" and not q:
            i += 2
            continue
        elif c == "|" and not q:
            return None  # a pipe before any '&': not our business
        elif c == "&" and not q:
            j = i
            while j < len(line) and line[j] == "&":
                j += 1
            return line[:i], line[j:]
        i += 1
    return None


def _strip_cmd_name(part):
    s = part.strip()
    low = s.lower()
    if low.startswith('"'):
        end = low.find('"', 1)
        name, rest = low[1:end], s[end + 1:]
    else:
        sp = low.find(" ")
        name, rest = (low, "") if sp < 0 else (low[:sp], s[sp:])
    base = name.replace("/", "\\").rsplit("\\", 1)[-1]
    for ext in (".bat", ".cmd", ".exe"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    return base, rest.strip()


def _drop_options(s):
    toks = s.split(" ")
    out, skip = [], False
    for i, t in enumerate(toks):
        if skip:
            skip = False
            continue
        if not out and t in ("-t", "--to"):
            skip = True
            continue
        if not out and (t.startswith("-") or (t.startswith(":") and len(t) > 1) or t == ""):
            continue
        out.append(t)
    return " ".join(out)


def analyse(line, argv_text):
    """If `line` is `trnl <argv_text> & more`, return the full text the user meant, else None."""
    if not line:
        return None
    sp = split_operator(line)
    if not sp:
        return None
    name, rest = _strip_cmd_name(sp[0])
    if name != "trnl":
        return None
    if " ".join(_drop_options(rest).split()).strip('"') != " ".join(argv_text.split()).strip('"'):
        return None
    _, full_rest = _strip_cmd_name(line.strip())
    return _drop_options(" ".join(full_rest.split())).strip()


def last_cmd_line():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        f_len = k.GetConsoleCommandHistoryLengthW
        f_get = k.GetConsoleCommandHistoryW
        f_len.argtypes = [wintypes.LPCWSTR]
        f_len.restype = wintypes.DWORD
        f_get.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.LPCWSTR]
        f_get.restype = wintypes.DWORD
        n = f_len("cmd.exe")  # bytes
        if not n:
            return None
        buf = ctypes.create_unicode_buffer(n // 2 + 2)
        got = f_get(buf, n, "cmd.exe")
        if not got:
            return None
        entries = [e for e in buf[: got // 2].split("\0") if e.strip()]
        return entries[-1] if entries else None
    except Exception:
        return None


def check(argv_text):
    """-> full text if the user's cmd line was cut at an '&', else None."""
    return analyse(last_cmd_line(), argv_text)


# ---------------- raw command line (to see "quotes" that cmd / the C runtime strip from argv) ----------------
def split_cmdline(line, first=True):
    """MSVCRT-style split -> list of (value, marked). `marked` is the argument with its quoting kept as plain '"'
    characters (escaped \\" become a plain quote too), so 'Ahmet'e "Sevgi" dedim' stays visible."""
    out, i, n = [], 0, len(line)
    while i < n:
        while i < n and line[i] in " \t":
            i += 1
        if i >= n:
            break
        val, mark = [], []
        if first and not out:  # program name: no backslash rules
            if line[i] == '"':
                j = line.find('"', i + 1)
                j = n if j < 0 else j
                val.append(line[i + 1:j])
                i = j + 1
            while i < n and line[i] not in " \t":
                val.append(line[i])
                i += 1
            out.append(("".join(val), "".join(val)))
            continue
        q = False
        while i < n:
            c = line[i]
            if c == "\\":
                j = i
                while j < n and line[j] == "\\":
                    j += 1
                cnt = j - i
                if j < n and line[j] == '"':  # 2n backslashes + " -> n backslashes, quote toggles; 2n+1 -> literal "
                    val.append("\\" * (cnt // 2))
                    mark.append("\\" * (cnt // 2))
                    if cnt % 2:
                        val.append('"')
                        mark.append('"')
                        i = j + 1
                    else:
                        i = j  # the quote is handled by the branch below
                    continue
                val.append("\\" * cnt)
                mark.append("\\" * cnt)
                i = j
                continue
            if c == '"':
                if q and i + 1 < n and line[i + 1] == '"':
                    val.append('"')
                    mark.append('"')
                    i += 2
                    continue
                q = not q
                mark.append('"')
                i += 1
                continue
            if c in " \t" and not q:
                break
            val.append(c)
            mark.append(c)
            i += 1
        out.append(("".join(val), "".join(mark)))
    return out


def marked_args(argv, line=None):
    """argv (sys.argv[1:]) with the user's quotes restored, from the real command line; None if unsure."""
    try:
        if line is None:
            if sys.platform != "win32":
                return None
            import ctypes
            k = ctypes.windll.kernel32
            k.GetCommandLineW.restype = ctypes.c_wchar_p
            line = k.GetCommandLineW()
        toks = split_cmdline(line or "")
        if not argv:
            return []
        if len(toks) < len(argv):
            return None
        tail = toks[-len(argv):]
        if [v for v, _ in tail] != list(argv):
            return None  # the launcher rewrote something: do not guess
        return [m for _, m in tail]
    except Exception:
        return None
