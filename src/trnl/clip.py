"""Put text on the system clipboard. Never raises: -> True/False."""
import os
import shutil
import subprocess
import sys
import time


def _win(text):
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.OpenClipboard.restype = wintypes.BOOL
    u.EmptyClipboard.restype = wintypes.BOOL
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u.SetClipboardData.restype = wintypes.HANDLE
    u.CloseClipboard.restype = wintypes.BOOL
    k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k.GlobalAlloc.restype = wintypes.HGLOBAL
    k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k.GlobalUnlock.restype = wintypes.BOOL
    k.GlobalFree.argtypes = [wintypes.HGLOBAL]
    k.GlobalFree.restype = wintypes.HGLOBAL
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002

    data = text.replace("\r\n", "\n").replace("\n", "\r\n")
    buf = ctypes.create_unicode_buffer(data)  # NUL-terminated UTF-16
    size = ctypes.sizeof(buf)
    # a hidden owner window: with OpenClipboard(NULL) SetClipboardData may fail (documented)
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                  wintypes.HINSTANCE, wintypes.LPVOID]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DestroyWindow.argtypes = [wintypes.HWND]
    try:
        hwnd = u.CreateWindowExW(0, "STATIC", "trnl", 0, 0, 0, 0, 0, None, None, None, None)
    except Exception:
        hwnd = None
    try:
        for _ in range(15):  # another app may hold the clipboard for a moment
            if u.OpenClipboard(hwnd):
                break
            time.sleep(0.03)
        else:
            return False
        return _win_put(u, k, buf, size, CF_UNICODETEXT, GMEM_MOVEABLE)
    finally:
        if hwnd:
            u.DestroyWindow(hwnd)


def _win_put(u, k, buf, size, CF_UNICODETEXT, GMEM_MOVEABLE):
    import ctypes
    try:
        h = k.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            return False
        p = k.GlobalLock(h)
        if not p:
            k.GlobalFree(h)
            return False
        ctypes.memmove(p, buf, size)
        k.GlobalUnlock(h)
        u.EmptyClipboard()
        if not u.SetClipboardData(CF_UNICODETEXT, h):
            k.GlobalFree(h)  # still ours only if SetClipboardData failed
            return False
        return True
    finally:
        u.CloseClipboard()


def _run(cmd, text):
    try:
        p = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=3)
        return p.returncode == 0
    except Exception:
        return False


def copy(text):
    if not text:
        return False
    try:
        if sys.platform == "win32":
            try:
                if _win(text):
                    return True
            except Exception:
                pass
            try:  # fallback: Windows' own clip.exe (UTF-16 with BOM keeps Turkish / Japanese characters)
                p = subprocess.run(["clip"], input=b"\xff\xfe" + text.encode("utf-16-le"), timeout=3,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                return p.returncode == 0
            except Exception:
                return False
        if sys.platform == "darwin":
            return _run(["pbcopy"], text)
        cands = []
        if os.environ.get("WAYLAND_DISPLAY"):
            cands.append(["wl-copy"])
        if os.environ.get("DISPLAY"):
            cands += [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
        cands.append(["termux-clipboard-set"])
        for c in cands:
            if shutil.which(c[0]) and _run(c, text):
                return True
    except Exception:
        pass
    return False
