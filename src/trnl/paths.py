"""Per-user data dir + tiny config reader (no heavy imports)."""
import os
import sys

APP = "trnl"


def data_dir():
    env = os.environ.get("TRNL_HOME")
    if env:
        return env
    try:
        from platformdirs import user_data_dir
        return user_data_dir(APP, appauthor=False)
    except Exception:  # platformdirs missing: same layout by hand
        home = os.path.expanduser("~")
        if sys.platform == "win32":
            return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), APP)
        if sys.platform == "darwin":
            return os.path.join(home, "Library", "Application Support", APP)
        return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), APP)


def models_dir():
    return os.path.join(data_dir(), "models")


def dict_path():
    return os.path.join(data_dir(), "dict.db")


def config_path():
    return os.path.join(data_dir(), "config.ini")


DEFAULTS = {
    "native": "tr",      # text in this language is translated to `foreign`
    "foreign": "en",     # everything else is translated to `native`
    "theme": "auto",     # auto | dark | light
    "color": "",         # r;g;b  main colour override
    "dim": "",           # r;g;b  secondary colour override
    "timeout": "2",      # seconds for online requests
    "mode": "auto",      # auto | online | offline
    "history": "on",     # on | off  (translation log)
    "compute": "auto",   # auto | int8 | float32  (offline precision; float32 is slower, use only if output looks garbled)
}

_cfg = None


def config():
    """key=value lines, '#' comments. Env TRNL_<KEY> wins."""
    global _cfg
    if _cfg is not None:
        return _cfg
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line[0] in "#;[" or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip().lower()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    for k in list(DEFAULTS):
        v = os.environ.get("TRNL_" + k.upper())
        if v is not None:
            cfg[k] = v
    if os.environ.get("TRNL_OFFLINE") in ("1", "true", "yes"):
        cfg["mode"] = "offline"
    _cfg = cfg
    return cfg
