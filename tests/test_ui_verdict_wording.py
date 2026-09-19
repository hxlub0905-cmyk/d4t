# U13 / X7：判定的意思寫在字上，不寄生在顏色與編號上 — authored 2026-09-08.
"""**同一個綠色 chip 在兩份 recipe 裡意思相反。**

`VerdictChip` 以前有一個 `is_real_style` —— 它為真時紅綠對調（bin 1 = 抓到
真缺陷 = 壞消息）。而在那一輪之前，**兩種模式的文字一模一樣**，只有顏色換邊：
畫面上沒有任何東西講得出現在是哪一種。再加上紅綠對色覺缺陷者不可分辨（男性約
8%），整張 chip 的意思等於押在一個有些人看不見、而且會反轉的通道上。

⚠ **F119（2026-09-20）把那個旗標刪了，而這幾條一條都沒有失效。** 刪的理由是
它從來沒有呼叫端，而且它要解的「同一個綠色在兩份 recipe 裡意思相反」在
`outcome`（寫 recipe 的人自己標）之後從根上不存在了。這一節守的東西沒有變：
**顏色說了什麼，字就要說得出同一件事。**

X7 是同一個根的另一半：使用者腦中的字彙是 **class**，不是 bin —— 而那些名字
（`Rule.label` / `TreeLeaf.label` / `otherwise_label`）從 F21-D／F24 起就存得
下來，只是沒有人拿去畫。

所以這一份守三件事：名字排第一、顏色翻面時字跟著翻面、tone 有第二個不靠顏色
的通道。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# --------------------------------------------------------------------------- #
# 1. 名字從 recipe 收上來（不 import Qt 的那一半）
# --------------------------------------------------------------------------- #
def test_the_names_come_off_the_rules_and_the_otherwise():
    from d4t.core.pipeline.recipe import DecideSpec, Rule
    d = DecideSpec(rules=[Rule(when="s > 3", bin=1, label="real")],
                   otherwise_bin=0, otherwise_label="nuisance")
    assert d.bin_labels() == {1: "real", 0: "nuisance"}


def test_an_unnamed_bin_is_simply_absent():
    """沒取名的不要編一個出來 —— chip 那邊才有辦法退回門檻關係。"""
    from d4t.core.pipeline.recipe import DecideSpec, Rule
    d = DecideSpec(rules=[Rule(when="s > 3", bin=1)], otherwise_bin=0)
    assert d.bin_labels() == {}


def test_the_first_name_wins():
    """同一個 bin 被取兩個名字：由上往下第一個贏，跟判定本身同一個方向。

    挑最長的或接起來的話，畫面上的字會隨著一條不相干的規則改動而變 ——
    而使用者記住的是他自己打的第一個。
    """
    from d4t.core.pipeline.recipe import DecideSpec, Rule
    d = DecideSpec(rules=[Rule(when="a", bin=1, label="particle"),
                          Rule(when="b", bin=1, label="scratch")])
    assert d.bin_labels()[1] == "particle"


def test_the_tree_leaves_are_read_too():
    """F24 之後判定住在樹上，而樹的葉子也帶名字 —— 只讀 rules 會漏掉整份。"""
    from d4t.core.pipeline.recipe import DecideSpec, TreeLeaf, TreeStep
    tree = TreeStep(when="s > 3",
                    yes=TreeLeaf(bin=1, label="real"),
                    no=TreeLeaf(bin=0, label="nuisance"))
    assert DecideSpec(tree=tree).bin_labels() == {1: "real", 0: "nuisance"}


# --------------------------------------------------------------------------- #
# 2. chip 上那一行字
# --------------------------------------------------------------------------- #
def test_the_name_comes_first_and_the_bin_is_the_footnote(qapp):
    from d4t.ui.widgets import VerdictChip
    chip = VerdictChip()
    try:
        chip.set_verdict(1, label="particle")
        assert chip.text() == "particle · bin 1"
    finally:
        chip.deleteLater()


def test_when_the_colour_flips_the_word_flips_with_it(qapp):
    """**這是 U13 的整條命。**

    顏色說了什麼，字就要說得出同一件事 —— 不然色覺缺陷者（男性約 8%）手上
    只剩一條看不見的通道。

    ⚠ **F119 改了顏色的來源，沒有改這條命。** 以前紅綠是 `is_real_style`
    在翻（而那個旗標從來沒有呼叫端），現在是寫 recipe 的人自己標的
    `outcome`。所以這一條問的變成：**同一個名字、同一個 bin，只有 `outcome`
    不同的時候，字要不一樣。**
    """
    from d4t.ui.widgets import VerdictChip
    chip = VerdictChip()
    try:
        chip.set_verdict(1, label="a spot stands out", outcome="good")
        as_good = chip.text()
        chip.set_verdict(1, label="a spot stands out", outcome="bad")
        as_bad = chip.text()
        assert as_good != as_bad, \
            "只有顏色不一樣的話，顏色又變回唯一的通道了"
        assert chip.tone() == "bad"
        # 中性是**說了**沒有主張，所以它跟那兩個都不一樣（而且不加字）。
        chip.set_verdict(1, label="a spot stands out", outcome="neutral")
        assert chip.text() not in (as_good, as_bad)
    finally:
        chip.deleteLater()


def test_without_a_name_it_says_only_what_it_knows(qapp):
    """沒名字、也不知道 bin 1 是不是真缺陷 —— 那時候唯一知道的是門檻關係。

    這一格不該假裝知道更多（不要預設 bin 1 就叫 real —— 有些 recipe 反過來，
    而那正是 F119 的 `outcome` 存在的理由）。
    """
    from d4t.ui.widgets import VerdictChip
    chip = VerdictChip()
    try:
        chip.set_verdict(1)
        assert chip.text() == "bin 1 · ≥ threshold"
        chip.set_verdict(0)
        assert chip.text() == "bin 0 · < threshold"
        chip.set_verdict(None)
        assert chip.text() == "—"
    finally:
        chip.deleteLater()


def test_a_name_beats_the_real_wording(qapp):
    """使用者自己打的字**排在最前面**（X7）。

    好壞那個詞接在後面而不是搶在前面：他要找的是「這一顆被判成什麼」，
    而那是他自己取的名字。
    """
    from d4t.ui.widgets import VerdictChip
    chip = VerdictChip()
    try:
        chip.set_verdict(1, label="killer particle", outcome="bad")
        assert chip.text().startswith("killer particle")
        assert chip.text().endswith("review")
    finally:
        chip.deleteLater()


# --------------------------------------------------------------------------- #
# 3. 顏色以外的第二個通道
# --------------------------------------------------------------------------- #
def test_each_tone_looks_different_without_colour(qapp):
    """把顏色拿掉之後三個 tone 還要分得出來（紅綠對男性約 8% 不可分辨）。"""
    from d4t.ui.widgets import VerdictChip
    from d4t.ui.feature_text import _TONE_BORDER
    shapes = {t: _TONE_BORDER[t] for t in ("good", "bad", "neutral")}
    assert len(set(shapes.values())) == 3, \
        "兩個 tone 的框線長得一樣 —— 那個通道等於沒有：%s" % shapes
    chip = VerdictChip()
    try:
        seen = set()
        for b, out in ((1, "good"), (1, "bad"), (None, "")):
            chip.set_verdict(b, outcome=out)
            style = chip.styleSheet()
            seen.add(style[style.index("border:"):style.index("border-radius")])
        assert len(seen) == 3, "chip 真的畫出來的框線沒有三種：%s" % seen
    finally:
        chip.deleteLater()


def test_the_chip_does_not_lean_on_a_font_the_fab_may_not_have(qapp):
    """框線是 QSS 畫的，跟字型無關 —— 不要用 `●`/`○` 那種當形狀通道。

    那兩個在 Geometric Shapes 區，廠內的 Segoe UI 要退到 Segoe UI Symbol
    （`test_ui_f7_23_buttons` 那條規則的同一個理由），而退字型的下場是大小與
    baseline 都不一樣，最壞是豆腐框。
    """
    from d4t.ui.widgets import VerdictChip
    risky = "●○◐◀▶▾△✓✗✕■□"
    chip = VerdictChip()
    try:
        for b, out, label in ((1, "", ""), (0, "good", ""), (1, "bad", "x"),
                              (None, "", ""), (7, "neutral", "")):
            chip.set_verdict(b, label=label, outcome=out)
            hit = [ch for ch in chip.text() if ch in risky]
            assert not hit, "chip 的字用了不保證有字型的字元：%s" % hit
    finally:
        chip.deleteLater()
