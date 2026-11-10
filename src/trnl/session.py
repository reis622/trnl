"""'Copy to clipboard' that lives only as long as the terminal window that turned it on.

State file (data_dir()/copy_session) = "<pid> <creation time>" of the owning shell (cmd.exe, powershell, bash ...).
On every run we find our own shell the same way; copying is on only if it is that same, still-running process
(the creation time guards against Windows / Linux re-using a PID). Close the window -> the shell dies -> off.
"""
import os
import sys

from trnl.paths import data_dir

# processes between the shell and us that are not "the session": launchers, interpreters, wrappers
SKIP = {"trnl", "trnl.exe", "python", "python.exe", "pythonw.exe", "python3", "python3.exe", "py.exe", "py",
        "conhost.exe", "openconsole.exe", "winpty-agent.exe", "winpty.exe", "timeout", "env", "sudo", "uv", "uv.exe",
        "pipx", "pipx.exe"}
SHELLS = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe", "zsh.exe", "fish.exe", "nu.exe",
          "wsl.exe", "hyper.exe", "windowsterminal.exe", "bash", "zsh", "sh", "fish", "dash", "ksh", "tcsh", "csh",
          "nu", "pwsh", "elvish", "xonsh"}


def _base(name):
    return os.path.basename((name or "").replace("\\", "/")).lower()


def _skip(name):
    n = _base(name)
    return n in SKIP or n.startswith("python")


def state_path():
    return os.path.join(data_dir(), "copy_session")


# ---- process info: pid -> (ppid, name, creation time) or None ----
def _proc_linux(pid):
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read().decode("utf-8", "replace")
        name = raw[raw.index("(") + 1: raw.rindex(")")]
        rest = raw[raw.rindex(")") + 2:].split()
        return int(rest[1]), name, rest[19]  # ppid, comm, starttime (clock ticks since boot)
    except (OSError, ValueError, IndexError):
        return None


def _proc_ps(pid):  # macOS / BSD
    try:
        import subprocess
        out = subprocess.run(["ps", "-o", "ppid=", "-o", "lstart=", "-o", "comm=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=2).stdout.strip()
        if not out:
            return None
        parts = out.split()
        return int(parts[0]), _base(" ".join(parts[6:])), " ".join(parts[1:6])
    except Exception:
        return None


def _win_snapshot():
    """{pid: (ppid, exe)} for all processes (one Toolhelp snapshot)."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.Process32FirstW.restype = wintypes.BOOL
    k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.Process32NextW.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    out = {}
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out[int(e.th32ProcessID)] = (int(e.th32ParentProcessID), e.szExeFile)
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return out


def _win_ctime(pid):
    """Creation time (FILETIME as int) of a live process, or None if it is gone."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k.GetProcessTimes.restype = wintypes.BOOL
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetExitCodeProcess.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        code = wintypes.DWORD()
        if k.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:  # != STILL_ACTIVE
            return None
        c, x, kt, ut = (wintypes.FILETIME() for _ in range(4))
        if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(kt), ctypes.byref(ut)):
            return None
        return str((c.dwHighDateTime << 32) | c.dwLowDateTime)
    finally:
        k.CloseHandle(h)


def find_shell(pid=None, info=None, ctime=None, platform=None):
    """-> (pid, creation time) of the terminal session that runs us, or None.
    info(pid) -> (ppid, name, ctime-or-None); injectable for tests."""
    platform = platform or sys.platform
    if info is None:
        if platform == "win32":
            snap = _win_snapshot()
            info = lambda p: (snap[p][0], snap[p][1], None) if p in snap else None
            ctime = _win_ctime
        elif os.path.exists("/proc/self/stat"):
            info = _proc_linux
        else:
            info = _proc_ps
    ctime = ctime or (lambda p: (info(p) or (0, 0, None))[2])
    me = os.getpid() if pid is None else pid
    cur = info(me)
    if not cur:
        return None
    child_ct = ctime(me)
    seen = {me}
    candidate = None
    for _ in range(16):
        ppid = cur[0]
        if not ppid or ppid in seen:
            break
        seen.add(ppid)
        nxt = info(ppid)
        if not nxt:
            break
        ct = ctime(ppid)
        if ct is None:
            break
        if platform == "win32" and child_ct is not None and _num(ct) > _num(child_ct):
            break  # stale parent PID re-used by a newer process
        name = _base(nxt[1])
        if not _skip(name):
            if name in SHELLS or candidate is None:
                candidate = (ppid, ct)
            if name in SHELLS:
                return candidate
            # not a known shell (e.g. some IDE): keep the first one, but look a bit higher for a real shell
        cur, child_ct = nxt, ct
    return candidate


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _alive(pid, ct, ctime=None, platform=None):
    platform = platform or sys.platform
    try:
        if ctime is None:
            if platform == "win32":
                ctime = _win_ctime
            elif os.path.exists("/proc/self/stat"):
                ctime = lambda p: (_proc_linux(p) or (0, 0, None))[2]
            else:
                ctime = lambda p: (_proc_ps(p) or (0, 0, None))[2]
        return ctime(pid) == ct
    except Exception:
        return False


def read_state():
    """-> list of (pid, ctime) sessions that turned copying on (several windows may)."""
    out = []
    try:
        with open(state_path(), encoding="utf-8") as f:
            for line in f:
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    out.append((int(parts[0]), parts[1].strip()))
    except (OSError, UnicodeDecodeError):
        pass
    return out


def _write(items):
    os.makedirs(data_dir(), exist_ok=True)
    if not items:
        try:
            os.remove(state_path())
        except OSError:
            pass
        return
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for pid, ct in items:
            f.write(f"{pid} {ct}\n")
    os.replace(tmp, state_path())


def _live(items, alive):
    return [it for it in items if (alive or _alive)(it[0], it[1])]


def enable(shell=None, alive=None):
    """Turn copying on for this terminal window. -> False if the window could not be identified."""
    shell = shell or find_shell()
    if not shell:
        return False
    shell = (int(shell[0]), str(shell[1]))
    items = [it for it in _live(read_state(), alive) if it != shell] + [shell]
    _write(items)
    return True


def disable(shell=None, alive=None):
    shell = shell or find_shell()
    items = _live(read_state(), alive)
    if shell:
        items = [it for it in items if it != (int(shell[0]), str(shell[1]))]
    _write(items)


def is_on(shell=None, alive=None):
    """Copying is on only inside a terminal session that turned it on and is still running."""
    try:
        items = read_state()
        if not items:
            return False
        live = _live(items, alive)
        if len(live) != len(items):
            _write(live)  # closed windows: forget them
        if not live:
            return False
        cur = shell or find_shell()
        return bool(cur) and (int(cur[0]), str(cur[1])) in live
    except Exception:
        return False
