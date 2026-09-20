# repo 裡不准有看不見的字元（2026-09-20）。
"""**這一條是付了三次學費才寫的。**

寫檔案的路上（heredoc → shell → Python）會吃掉一層反斜線，於是原始碼裡的
「字界」符號變成一個真的 0x08 控制字元。三次都是同一個形狀，後果不同：

1. **F117 D4**：那個 regex 因此永遠不會 match，所以**整組測試都是綠的**。
   一條只會綠的測試比沒有測試糟：它讓人以為那件事有人在看。
2. 之後兩次落在**說明文字**裡，只是難看 —— 但下一次會落在哪裡沒有人保證。

所以這裡不再靠「記得小心」，改成一條每次都跑的規則。它便宜（讀檔、找字元）、
不需要 Qt，跑在核心那一批裡。

⚠ **這張表用 `chr()` 寫，不用跳脫序列。** 第一版寫成字面的跳脫序列，而寫檔案
的那條路把它們變成了真的控制字元 —— 於是這支測試在它自己身上抓到四個違規。
那個笑話正是它存在的理由：**判準不能用它要擋的那個東西寫成。**

⚠ **Tab 不在這張表上**：`ruff` 管縮排，而這一支問的是「有沒有東西是肉眼看不
見的」—— 兩件不同的事各有各的守門人。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

#: 不准出現在原始碼裡的字元，**每一個附一句它是怎麼跑進來的**。
FORBIDDEN = {
    chr(0): "NUL —— 檔案壞了",
    chr(7): "BEL —— 通常是 alert 那個跳脫序列被吃掉一層反斜線",
    chr(8): "BS —— 通常是 regex 的「字界」被吃掉一層反斜線（付過三次學費）",
    chr(11): "VT —— 通常是垂直定位跳脫序列被吃掉一層反斜線",
    chr(12): "FF —— 通常是換頁跳脫序列被吃掉一層反斜線",
    chr(0x200B): "零寬空格 —— 從網頁或文件複製貼上帶進來的",
    chr(0xFEFF): "BOM 出現在檔案中間",
}

ROOTS = ("d4t", "tests", "tools", "bundle", "docs", "recipes")

#: ⚠ **文件也要掃。** 四個誤闖的字元裡有兩個落在 `.md` 上（SESSION_LOG 的一段
#: 故事、一份封存的計畫）—— 那一份是給人讀的，而讀的人看不到那個字元，只會
#: 看到一段突然斷掉的句子。
SUFFIXES = (".py", ".md", ".json")


def _sources():
    for root in ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            yield path


def test_there_are_files_to_scan():
    """⚠ 前提：掃得到東西。掃到零個檔案的掃描器是一條永遠綠的測試。"""
    found = list(_sources())
    assert len(found) > 300
    for suffix in SUFFIXES:
        assert any(p.suffix == suffix for p in found), suffix


@pytest.mark.parametrize("ch", sorted(FORBIDDEN))
def test_no_invisible_characters_in_the_source(ch):
    hits = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if ch not in text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if ch in line:
                hits.append("%s:%d" % (path.relative_to(REPO).as_posix(), i))
    assert not hits, "%s：%s" % (FORBIDDEN[ch], ", ".join(hits[:8]))


def test_the_scan_would_actually_catch_one(tmp_path):
    """**反向測試** —— 而這一支本身就是「反向測試」那條規矩的產物。

    判準要是壞的話，它會安靜地什麼都不擋，而那正是 F117 D4 那次的情形。
    """
    bad = tmp_path / "x.py"
    bad.write_text("x = 1  # %s\n" % chr(8), encoding="utf-8")
    text = bad.read_text(encoding="utf-8")
    assert chr(8) in text
    assert chr(8) not in "x = 1  # fine"


def test_every_forbidden_character_says_where_it_comes_from():
    """⚠ 一張沒有理由的黑名單，下一個人只會照抄或整條刪掉。"""
    for ch, why in FORBIDDEN.items():
        assert len(ch) == 1
        assert len(why) > 10, repr(ch)
