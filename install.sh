#!/bin/sh
# trnl installer / updater for macOS and Linux.
#   curl -fsSL https://raw.githubusercontent.com/reis622/trnl/main/install.sh | sh
# Uses pipx if you have it, otherwise a private venv in ~/.local/share/trnl/venv linked to ~/.local/bin/trnl.
# Running it again updates trnl. Offline language packs are downloaded later, on demand: trnl -s
set -eu

REPO="reis622/trnl"
SRC_ZIP="https://github.com/$REPO/archive/refs/heads/main.zip"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/trnl"
VENV="$DATA/venv"
BIN="$HOME/.local/bin"

say() { printf '%s\n' "$*"; }
die() { printf 'trnl: %s\n' "$*" >&2; exit 1; }

# everything runs from main() so a half-downloaded script (curl | sh) never runs partially
main() {
    # ---- python 3.9+ ----
    PY=""
    for c in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
        if command -v "$c" >/dev/null 2>&1 &&
           "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PY=$(command -v "$c"); break
        fi
    done
    [ -n "$PY" ] || die "Python 3.9+ bulunamadi / not found. macOS: brew install python  -  Debian/Ubuntu: sudo apt install python3 python3-venv"

    # ---- what to install: latest release wheel, else the source zip ----
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t trnl)
    trap 'rm -rf "$TMP"' EXIT INT TERM
    PKG=""
    API="https://api.github.com/repos/$REPO/releases/latest"
    if command -v curl >/dev/null 2>&1; then curl -fsSL -o "$TMP/rel.json" "$API" 2>/dev/null || true; fi
    URL=$("$PY" - "$API" "$TMP/rel.json" <<'PYEOF' 2>/dev/null || true
import json, os, re, sys, urllib.request
if os.path.getsize(sys.argv[2]) if os.path.exists(sys.argv[2]) else 0:
    rel = json.load(open(sys.argv[2], encoding="utf-8"))
else:  # no curl: python's own https (may lack CA certs on some macOS Pythons -> source zip fallback)
    req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "trnl-installer"})
    rel = json.load(urllib.request.urlopen(req, timeout=20))
for a in rel.get("assets", []):
    if re.match(r"^trnl-\d[^-]*-py3-none-any\.whl$", a["name"]):
        print(a["browser_download_url"]); break
PYEOF
    )
    if [ -n "$URL" ]; then
        WHL="$TMP/${URL##*/}"
        if command -v curl >/dev/null 2>&1; then curl -fsSL -o "$WHL" "$URL" && PKG="$WHL"
        elif command -v wget >/dev/null 2>&1; then wget -q -O "$WHL" "$URL" && PKG="$WHL"
        else "$PY" -c 'import sys,urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$URL" "$WHL" && PKG="$WHL"
        fi
    fi
    [ -n "$PKG" ] || { say "GitHub release okunamadi, kaynak koddan kuruluyor..."; PKG="$SRC_ZIP"; }
    say "trnl kuruluyor ($PKG)..."

    if command -v pipx >/dev/null 2>&1 && [ -z "${TRNL_NO_PIPX:-}" ]; then
        pipx install --force "$PKG" </dev/null || die "pipx install basarisiz / failed"
        WHERE="pipx"
    else
        mkdir -p "$DATA" "$BIN"
        if [ ! -x "$VENV/bin/python" ]; then
            "$PY" -m venv "$VENV" </dev/null 2>/dev/null || {
                rm -rf "$VENV"
                die "venv olusturulamadi / could not create a venv. Debian/Ubuntu: sudo apt install python3-venv"
            }
        fi
        "$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip </dev/null || true
        "$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade "$PKG" </dev/null || die "pip install basarisiz / failed"
        # same version number but new files (update): reinstall trnl itself, keep the dependencies
        "$VENV/bin/python" -m pip install --disable-pip-version-check -q --force-reinstall --no-deps "$PKG" </dev/null || true
        ln -sf "$VENV/bin/trnl" "$BIN/trnl"
        WHERE="$BIN/trnl"
    fi

    say ""
    say "Kurulum tamam / installed ($WHERE). Dene / try:  trnl hello"
    say "Internetsiz kullanim icin dil paketleri / offline packs (optional):  trnl -s   (only en,tr: trnl -s en,tr)"
    case ":$PATH:" in
        *":$BIN:"*) ;;
        *)
            if [ "$WHERE" = pipx ]; then
                say "trnl bulunamazsa / if trnl is not found:  pipx ensurepath   (then open a new terminal)"
            else
                say ""
                say "$BIN PATH'te degil / is not on your PATH. Ekle / add it:"
                say "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.profile   (zsh: ~/.zshrc)  then open a new terminal"
            fi
            ;;
    esac
}

main "$@"
