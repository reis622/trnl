"""Run with:  pytest tests/   (offline tests need `trnl --setup` data or TRNL_HOME pointing at it)."""
import os
import subprocess
import sys

import pytest

from trnl import core, detect, online
from trnl.cli import main
from trnl.dictdb import DictDB

HAVE_DATA = DictDB().ok


def test_is_word():
    assert core.is_word("hello") and core.is_word("don't") and core.is_word("猫")
    assert not core.is_word("good morning") and not core.is_word("今日はいい天気ですね。")


def test_detect_script_and_chars():
    assert detect.guess("こんにちは")[0] == "ja"
    assert detect.guess("我喜欢学习中文")[0] == "zh"
    assert detect.guess("Bugün hava çok güzel")[0] == "tr"
    assert detect.guess("Wo ist der Bahnhof und das Haus?")[0] == "de"
    assert detect.guess("¿Dónde está la biblioteca?")[0] == "es"
    assert detect.guess("How are you today?")[0] == "en"


def test_target_rule():
    assert core.pick_target("tr", None) == "en"
    assert core.pick_target("de", None) == "tr"
    assert core.pick_target("tr", "ja") == "ja"


def test_google_meanings_dedupe():
    res = {"text": "Merhaba", "bd": [("interjection", [
        ("Merhaba!", ["Hello!", "Hi!", "How do you do?", "Hallo!", "Hullo!"], 0.49),
        ("Selam!", ["Hi!", "Hello!", "How do you do?"], 0.027),   # near-synonym -> dropped
        ("Alo!", ["Hello!", "Halloo!"], 0.019),                   # different sense -> kept
        ("Hey!", ["Hey!"], 0.00001)])]}                            # weak -> dropped
    assert online.google_meanings(res, "hello") == [("Merhaba", "interjection"), ("Alo", "interjection")]


def test_google_meanings_single():
    res = {"text": "elma", "bd": [("noun", [("elma", ["apple"], 0.73)])]}
    assert online.google_meanings(res, "apple") == [("elma", "noun")]


@pytest.mark.skipif(not HAVE_DATA, reason="offline data not installed")
@pytest.mark.parametrize("text,src,tgt", [
    ("How are you?", "en", "tr"), ("Nasılsın?", "tr", "en"), ("Guten Morgen", "de", "tr"),
    ("Buenos días", "es", "tr"), ("おはようございます", "ja", "tr"), ("早上好", "zh", "tr"),
    ("Good morning", "en", "de"), ("Good morning", "en", "es"), ("Good morning", "en", "ja"),
    ("Good morning", "en", "zh"), ("Günaydın", "tr", "de"),
])
def test_offline_pairs(text, src, tgt):
    r = core.translate(text, tgt, "offline")
    assert r.src == src and r.tgt == tgt and r.flat() and r.flat() != text


@pytest.mark.skipif(not HAVE_DATA, reason="offline data not installed")
def test_offline_word_meanings(tmp_path, monkeypatch):
    from trnl.dictdb import UserDB
    monkeypatch.setattr(core, "_udb", UserDB(str(tmp_path / "empty.db")))
    r = core.translate("light", None, "offline")
    assert 2 <= len(r.meanings) <= 3 and r.meanings[0][0] == "ışık"
    r = core.translate("bank", None, "offline")
    assert r.flat() == "banka"  # only one real meaning in the dictionary -> no padding


def test_cli_version(capsys):
    assert main(["-v"]) == 0 and capsys.readouterr().out.strip()
    assert main(["--version"]) == 0


def test_cli_help_lists_short_and_long(capsys):
    main(["--help"])
    out = capsys.readouterr().out
    for s, l in [("-w", "--words"), ("-H", "--history"), ("-s", "--setup"), ("-t", "--to"),
                 ("-o", "--offline"), ("-n", "--online"), ("-v", "--version"), ("-h", "--help")]:
        assert s in out and l in out


@pytest.mark.skipif(not HAVE_DATA, reason="offline data not installed")
def test_cli_pipe_shell():
    p = subprocess.run([sys.executable, "-m", "trnl", "-o"], input="hello\nNasılsın?\n", capture_output=True,
                       text=True, encoding="utf-8", env=dict(os.environ, NO_COLOR="1"))
    assert p.returncode == 0 and "merhaba" in p.stdout and "How" in p.stdout


def test_amp_analyse():
    from trnl.winamp import analyse
    assert analyse("trnl rock & roll", "rock") == "rock & roll"
    assert analyse("C:\\Users\\PC\\bin\\trnl.bat salt & pepper", "salt") == "salt & pepper"
    assert analyse("trnl -t de salt & pepper", "salt") == "salt & pepper"
    assert analyse("trnl rock ^& roll", "rock & roll") is None      # escaped: nothing was cut
    assert analyse('trnl "rock & roll"', '"rock & roll"') is None   # quoted: fine
    assert analyse("trnl hello | clip", "hello") is None            # real pipe
    assert analyse("echo hi & trnl x", "x") is None


def test_kaikki_gloss_cleaning():
    from trnl.dictdb import clean_gloss, kaikki_rows
    assert clean_gloss("tea (the drink made by infusing leaves)") == ["tea"]
    assert clean_gloss("A small river, a brook.") == ["small river", "brook"]
    rows = list(kaikki_rows(['{"word":"çay","pos":"noun","senses":[{"glosses":["tea (plant)"]},'
                             '{"glosses":["plural of x"]},{"glosses":["tea"],"tags":["obsolete"]}]}'], "tr"))
    assert [r[6] for r in rows] == ["tea"]


@pytest.mark.skipif(not HAVE_DATA, reason="offline data not installed")
def test_user_cache_preferred_offline(tmp_path, monkeypatch):
    from trnl.dictdb import UserDB
    u = UserDB(str(tmp_path / "user.db"))
    monkeypatch.setattr(core, "_udb", u)
    u.save("bank", "en", "tr", [("banka", "noun"), ("kıyı", "noun")])
    r = core.translate("bank", None, "offline")
    assert r.how == "cache" and r.flat() == "banka | kıyı"


@pytest.mark.skipif(not HAVE_DATA, reason="offline data not installed")
def test_opus_tr_en_quality():
    from trnl import offline
    if offline.engine("tr", "en") != "opus":
        pytest.skip("OPUS-MT tr->en not installed")
    assert core.translate("Nasılsın, iyi misin?", "en", "offline").flat().lower().startswith("how are you")


# ---------------- glossary / quotes / copy session ----------------
def test_glossary_store(tmp_path, monkeypatch):
    from trnl import glossary
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    glossary.add("mell", "molotov")
    glossary.add("Kerem", "Kerem")
    glossary.add("MELL", "molotof")  # same key (case-insensitive) -> replaced, not duplicated
    assert glossary.load() == [("Kerem", "Kerem"), ("MELL", "molotof")]
    assert glossary.lookup("mell") == "molotof" and glossary.lookup("kerem") == "Kerem"
    assert glossary.remove("Mell") and not glossary.remove("mell")
    assert glossary.parse_entry("kanka naber = hey bro") == ("kanka naber", "hey bro")
    assert glossary.parse_entry("mell") is None and glossary.parse_entry("=x") is None


def test_glossary_substitution():
    from trnl.glossary import prepare, restore
    items = [("mell", "molotov"), ("Kerem", "Kerem")]
    assert prepare("orta koridora mell alma lütfen", items=items).text == "orta koridora molotov alma lütfen"
    assert prepare("Mell'e dikkat", items=items).text == "molotov'e dikkat"
    assert prepare("mellden kaç", items=items).text == "molotovden kaç"
    assert prepare("melleri topla", items=items).text == "molotovleri topla"
    assert prepare("mellow yellow", items=items).text == "mellow yellow"  # not a suffix: untouched
    assert prepare("kamell", items=items).text == "kamell"                # only at word starts
    p = prepare("Kerem'e söyle, KEREM gelsin", items=items)
    assert p.text == "ZZQ0'e söyle, ZZQ1 gelsin" and p.slots == {0: "Kerem", 1: "Kerem"}
    assert p.literal == "Kerem'e söyle, Kerem gelsin"
    assert restore("Tell ZZQ0 that zzq1 should come", p.slots) == "Tell Kerem that Kerem should come"
    assert prepare("Keremle", items=items).text == "ZZQ0'le"
    assert prepare("Kerem", items=items).only == "Kerem"


def test_quote_protection_parsing():
    from trnl.glossary import prepare, split_quotes
    assert split_quotes('Ahmet\'e "Sevgi" dedim') == [("Ahmet'e ", False), ("Sevgi", True), (" dedim", False)]
    assert split_quotes('"rock & roll"') == [("rock & roll", False)]   # whole text quoted: normal sentence
    assert split_quotes('a "b" c "d e"') == [("a ", False), ("b", True), (" c ", False), ("d e", True)]
    assert split_quotes('say "hi') == [('say "hi', False)]               # unbalanced: left alone
    p = prepare('Ahmet\'e "Sevgi" dedim', items=[])
    assert p.text == "Ahmet'e ZZQ0 dedim" and p.slots == {0: "Sevgi"}
    p = prepare('"mell" ve mell', items=[("mell", "molotov")])        # quotes win over the glossary
    assert p.text == "ZZQ0 ve molotov" and p.slots == {0: "mell"}


def test_windows_cmdline_quotes():
    from trnl.winamp import marked_args, split_cmdline
    line = '"C:\\Py\\python.exe" "C:\\Users\\x\\bin\\trnl.exe" Ahmet\'e "Sevgi" dedim'
    assert marked_args(["Ahmet'e", "Sevgi", "dedim"], line) == ["Ahmet'e", '"Sevgi"', "dedim"]
    assert marked_args(["rock & roll"], 'trnl.exe "rock & roll"') == ['"rock & roll"']
    assert marked_args(["x"], 'trnl.exe y') is None                    # mismatch: do not guess
    assert [v for v, _ in split_cmdline('p a\\"b "c d" e\\\\f')] == ["p", 'a"b', "c d", "e\\\\f"]


def test_glossary_translate_shortcuts(tmp_path, monkeypatch):
    from trnl import glossary
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    glossary.add("mell", "molotov")
    glossary.add("Kerem", "Kerem")
    assert core.translate("mell").text == "molotov"        # glossary word alone: no network needed
    assert core.translate("Kerem").text == "Kerem"


def test_translate_restores_tokens(monkeypatch, tmp_path):
    from trnl import glossary
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    glossary.add("Kerem", "Kerem")
    seen = []

    def fake(text, forced=None, mode=None, hint=None):
        seen.append((text, hint))
        return core.Result("tr", "en", text.replace("söyle", "tell"), None, "fake")
    monkeypatch.setattr(core, "_translate", fake)
    monkeypatch.setattr(core, "_src_hint", lambda t, m: "tr")
    r = core.translate('Kerem\'e "Sevgi" söyle')
    assert seen[0] == ("ZZQ0'e ZZQ1 söyle", "tr") and r.text == "Kerem'e Sevgi tell"

    def eats(text, forced=None, mode=None, hint=None):  # engine loses the token -> literal retry
        seen.append((text, hint))
        return core.Result("tr", "en", "lost", None, "fake")
    seen.clear()
    monkeypatch.setattr(core, "_translate", eats)
    core.translate("Kerem'e söyle")
    assert [s[0] for s in seen] == ["ZZQ0'e söyle", "Kerem'e söyle"]


def test_session_find_shell():
    from trnl.session import find_shell
    procs = {100: (50, "python.exe", "t100"), 50: (40, "trnl.exe", "t50"), 40: (30, "cmd.exe", "t40"),
             30: (1, "Hyper.exe", "t30"), 1: (0, "wininit.exe", "t1")}
    info = lambda p: procs.get(p)
    ct = lambda p: procs[p][2] if p in procs else None
    assert find_shell(100, info, ct, platform="linux") == (40, "t40")
    procs[40] = (30, "powershell.exe", "t40")
    assert find_shell(100, info, ct, platform="linux") == (40, "t40")
    # Windows: a parent created after its child is a re-used PID -> stop there
    wprocs = {100: (50, "python.exe", "200"), 50: (40, "trnl.exe", "150"), 40: (30, "cmd.exe", "300")}
    wi = lambda p: wprocs.get(p)
    assert find_shell(100, wi, lambda p: wprocs[p][2] if p in wprocs else None, platform="win32") is None


def test_session_on_off(tmp_path, monkeypatch):
    from trnl import session
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    alive = {(40, "t40"), (41, "t41")}
    is_alive = lambda pid, ct: (pid, ct) in alive
    win_a, win_b = (40, "t40"), (41, "t41")
    assert not session.is_on(win_a, is_alive)                    # new windows start off
    assert session.enable(win_a, is_alive)
    assert session.is_on(win_a, is_alive) and not session.is_on(win_b, is_alive)
    session.enable(win_b, is_alive)
    assert session.is_on(win_b, is_alive)
    session.disable(win_b, is_alive)
    assert session.is_on(win_a, is_alive) and not session.is_on(win_b, is_alive)
    alive.discard(win_a)                                           # window A closed
    assert not session.is_on(win_a, is_alive) and session.read_state() == []
    alive.add((40, "t99"))                                         # PID 40 re-used by another process
    session.enable(win_a, lambda p, c: True)
    assert not session.is_on((40, "t99"), lambda p, c: (p, c) in alive)


def test_cli_glossary_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    assert main(["-a", "mell=molotov"]) == 0 and main(["--add", "Kerem=Kerem"]) == 0
    assert main(["-a", "bozuk"]) == 1
    capsys.readouterr()
    assert main(["-l"]) == 0
    out = capsys.readouterr().out
    assert "mell" in out and "molotov" in out and "Kerem" in out
    assert main(["mell"]) == 0 and capsys.readouterr().out.strip() == "molotov"
    assert main(["-r", "mell"]) == 0 and main(["--remove", "mell"]) == 1
    capsys.readouterr()
    main(["--list"])
    assert "mell" not in capsys.readouterr().out


def test_cli_copy_flags(tmp_path, monkeypatch, capsys):
    from trnl import cli, session
    monkeypatch.setenv("TRNL_HOME", str(tmp_path))
    monkeypatch.setattr(session, "find_shell", lambda *a, **k: (4242, "ct"))
    monkeypatch.setattr(session, "_alive", lambda pid, ct, *a, **k: True)
    copied = []
    import trnl.clip
    monkeypatch.setattr(trnl.clip, "copy", lambda t: copied.append(t) or True)
    assert main(["-c"]) == 0 and "açık" in capsys.readouterr().out
    from trnl import glossary
    glossary.add("mell", "molotov")
    assert main(["mell"]) == 0 and copied == ["molotov"]
    assert main(["--copy", "off"]) == 0 and "kapandı" in capsys.readouterr().out
    assert main(["mell"]) == 0 and copied == ["molotov"]
    for s, l in [("-a", "--add"), ("-r", "--remove"), ("-l", "--list"), ("-c", "--copy")]:
        main(["-h"])
        out = capsys.readouterr().out
        assert s in out and l in out
    assert cli.HELP_TR.count("\n") == cli.HELP_EN.count("\n")
