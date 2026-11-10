# trnl

**[Türkçe](#türkçe) · [English](#english)**

```
$ trnl hello                 $ trnl nasılsın bugün        $ trnl :ja merhaba
1. merhaba  ünlem            How are you today            こんにちは
2. alo  ünlem                                             Kon'nichiwa
```

---

## Türkçe

Terminal çevirmeni. Önce internetten (Google) çevirir, internet yoksa kendi çevrimdışı modelleriyle çalışır
(en, tr, de, es, ja, zh). Türkçe yazarsan İngilizceye, başka bir dil yazarsan Türkçeye çevirir. Tek kelimede en
fazla 3 gerçek anlamı gösterir. Windows, macOS ve Linux'ta çalışır.

### Kurulum (tek komut)

| | |
|---|---|
| **Windows** (PowerShell) | `irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 \| iex` |
| **Windows** (cmd / Hyper) | `powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 \| iex"` |
| **macOS / Linux** | `curl -fsSL https://raw.githubusercontent.com/reis622/trnl/main/install.sh \| sh` |
| pipx (her sistem) | `pipx install git+https://github.com/reis622/trnl` |

Aynı komutu tekrar çalıştırmak trnl'yi günceller. Python 3.9+ gerekir; Windows kurucusu Python yoksa winget ile
kurar. Kurulumdan sonra terminali kapatıp aç. Çevrimdışı dil paketleri kurulumda indirilmez, istersen sonra:
`trnl -s`.

### Kullanım

```
trnl hello                     çeviri (tırnak gerekmez)
trnl :ja merhaba               hedef dil seç (:de, :es, :ja ... ya da -t ja)
trnl -w hello,but,love         birden çok kelime
trnl                           sessiz kabuk: yaz + Enter = çeviri, çıkış Ctrl+C
trnl :ja                       kabuğu Japoncaya çevirecek şekilde açar; içeride :de ile değiştir, :auto ile TR<->EN
trnl -H                        geçmiş (trnl -H clear siler)
trnl -s                        çevrimdışı dil paketlerini indirir (~2 GB; sadece en,tr: trnl -s en,tr)
trnl -a mell=molotov           kişisel sözlük: argo kelimeye anlam ver
trnl -a Kerem=Kerem            özel ismi hiç çevirme
trnl -l / trnl -r mell         sözlüğü listele / sil
trnl Ahmet'e "Sevgi" dedim     tırnak içindeki kelime aynen kalır
trnl -c                        çevirileri panoya kopyala (sadece bu terminal penceresinde; trnl -c off)
trnl -h                        tüm seçenekler
```

Metinde `&` varsa cmd'de cümleyi çift tırnak içine yaz: `trnl "rock & roll"`.

### Kaldırma

- **Windows:** `%USERPROFILE%\trnl` klasörünü ve `%USERPROFILE%\bin\trnl.exe` dosyasını sil. Veriler (geçmiş,
  sözlük, dil paketleri): `%LOCALAPPDATA%\trnl`.
- **macOS / Linux:** `rm -rf ~/.local/share/trnl ~/.local/bin/trnl` (pipx ile kurduysan: `pipx uninstall trnl`).
  macOS'ta veriler: `~/Library/Application Support/trnl`.

---

## English

A terminal translator. It translates online first (Google) and falls back to its own offline models
(en, tr, de, es, ja, zh) when there is no internet. Turkish goes to English, everything else goes to Turkish. A
single word shows up to 3 real meanings. Works on Windows, macOS and Linux.

### Install (one command)

| | |
|---|---|
| **Windows** (PowerShell) | `irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 \| iex` |
| **Windows** (cmd) | `powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 \| iex"` |
| **macOS / Linux** | `curl -fsSL https://raw.githubusercontent.com/reis622/trnl/main/install.sh \| sh` |
| pipx (any OS) | `pipx install git+https://github.com/reis622/trnl` |

Run the same command again to update. Needs Python 3.9+ (the Windows installer gets it with winget if missing).
Open a new terminal afterwards. Offline language packs are not downloaded at install time; get them any time with
`trnl -s`. (`pipx install trnl` from PyPI is planned, not published yet.)

### Usage

```
trnl hello                     translate (no quotes needed)
trnl :ja merhaba               pick the target (:de, :es, :ja ... or -t ja)
trnl -w hello,but,love         several words
trnl                           silent shell: type + Enter = translation, Ctrl+C exits
trnl :ja                       shell translating to Japanese; inside, :de switches, :auto = TR<->EN
trnl -H                        history (trnl -H clear deletes it)
trnl -s                        download offline packs (~2 GB; only en,tr: trnl -s en,tr)
trnl -a mell=molotov           personal glossary: give slang a meaning
trnl -a Kerem=Kerem            never translate a name
trnl -l / trnl -r mell         list / remove glossary entries
trnl Ahmet'e "Sevgi" dedim     a word in double quotes is kept as is
trnl -c                        copy translations to the clipboard (this terminal window only; trnl -c off)
trnl -h                        all options
```

In cmd, quote text that contains `&`: `trnl "rock & roll"`.

Config: `<data dir>/config.ini` (`native=tr`, `foreign=en`, `theme`, `color`, `timeout`, `mode`, ...; see `trnl -h`).
Data dir: Windows `%LOCALAPPDATA%\trnl`, macOS `~/Library/Application Support/trnl`, Linux `~/.local/share/trnl`
(override with `TRNL_HOME`).

### Uninstall

- **Windows:** delete `%USERPROFILE%\trnl` and `%USERPROFILE%\bin\trnl.exe`; data is in `%LOCALAPPDATA%\trnl`.
- **macOS / Linux:** `rm -rf ~/.local/share/trnl ~/.local/bin/trnl` (or `pipx uninstall trnl`).

### Offline engines

OPUS-MT (Helsinki-NLP, CC-BY 4.0) int8 models for en->tr, tr->en, ja->en (pre-converted copies in the
[`models-v1`](https://github.com/reis622/trnl/releases/tag/models-v1) release), Argos Translate for the other
directions, WikDict + kaikki.org Wiktionary dictionaries. Online: Google Translate, MyMemory as a fallback.

License: MIT.
