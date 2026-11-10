"""Theme-aware colours. Dark bg: #F9E2AF / #6C7086, light bg: #1E66F5 / #6C6F85."""
import os
import sys

DARK = ("249;226;175", "108;112;134")
LIGHT = ("30;102;245", "108;111;133")


def _enable_vt():
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return True  # not a classic console (pipe / mintty) - assume ok
        k.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return True
    except Exception:
        return True


def _bg_from_colorfgbg():
    v = os.environ.get("COLORFGBG")
    if not v:
        return None
    try:
        bg = int(v.split(";")[-1])
    except ValueError:
        return None
    return "light" if bg in (7, 9, 10, 11, 12, 13, 14, 15) else "dark"


def _bg_from_win_console():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", wintypes._COORD), ("dwCursorPosition", wintypes._COORD),
                        ("wAttributes", wintypes.WORD), ("srWindow", wintypes.SMALL_RECT),
                        ("dwMaximumWindowSize", wintypes._COORD)]
        csbi = CSBI()
        h = ctypes.windll.kernel32.GetStdHandle(-11)
        if not ctypes.windll.kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(csbi)):
            return None
        bg = (csbi.wAttributes >> 4) & 0xF
        # ConPTY (Hyper, Windows Terminal) always reports 0 -> treated as dark
        return "light" if bg in (7, 15, 14, 11) else "dark"
    except Exception:
        return None


def _bg_from_osc11(timeout=0.08):
    """Ask the terminal for its background (xterm OSC 11). POSIX tty only."""
    if sys.platform == "win32" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    if os.environ.get("TERM") in ("linux", "dumb") or os.environ.get("TMUX"):
        return None
    try:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            os.write(sys.stdout.fileno(), b"\x1b]11;?\x07")
            buf = b""
            while True:
                r, _, _ = select.select([fd], [], [], timeout)
                if not r:
                    break
                buf += os.read(fd, 64)
                if buf.endswith(b"\x07") or buf.endswith(b"\x1b\\"):
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, old)
        s = buf.decode("ascii", "ignore")
        if "rgb:" not in s:
            return None
        parts = s.split("rgb:")[1].strip("\x07\x1b\\").split("/")
        rgb = [int(p[:2], 16) for p in parts[:3]]
        lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        return "light" if lum > 140 else "dark"
    except Exception:
        return None


class Palette:
    def __init__(self, main="", dim="", reset=""):
        self.c, self.d, self.r = main, dim, reset


def palette(cfg, stream=None):
    stream = stream or sys.stdout
    fc = os.environ.get("FORCE_COLOR", os.environ.get("CLICOLOR_FORCE", ""))
    force = fc.lower() not in ("", "0", "false", "no")
    if fc.lower() in ("0", "false", "no") and "FORCE_COLOR" in os.environ:
        return Palette()
    if os.environ.get("NO_COLOR") and not force:
        return Palette()
    if not force and not stream.isatty():
        return Palette()
    _enable_vt()
    theme = (cfg.get("theme") or "auto").lower()
    if theme not in ("dark", "light"):
        theme = _bg_from_colorfgbg() or _bg_from_win_console() or _bg_from_osc11() or "dark"
    main, dim = LIGHT if theme == "light" else DARK
    if cfg.get("color"):
        main = cfg["color"].replace(",", ";")
    if cfg.get("dim"):
        dim = cfg["dim"].replace(",", ";")
    e = "\x1b"
    return Palette(f"{e}[38;2;{main}m", f"{e}[38;2;{dim}m", f"{e}[0m")
