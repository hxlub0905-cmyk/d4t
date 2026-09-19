# F119 第 4 步：葉子上那一排「這一類是好消息嗎」（2026-09-20）。
"""判定膠囊的顏色以前是**看 bin 的號碼**猜的，而三份出貨的 recipe 全反了。

F119 把答案搬進 recipe（`TreeLeaf.outcome`），而這一支守**使用者改得到它**
那一半：葉子的托盤上有一排膠囊，按了就寫進 model。

core 那一半在 `tests/test_decide_outcome.py`，膠囊怎麼畫在
`tests/test_ui_verdict_wording.py`。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.core.pipeline.recipe import OUTCOMES, TreeLeaf  # noqa: E402
from d4t.ui import theme as theme_mod                    # noqa: E402
from d4t.ui.chips import ChoiceChips                     # noqa: E402
from d4t.ui.tree_panel import (                          # noqa: E402
    OUTCOME_CHOICES, OUTCOME_HELP, OUTCOME_ICONS, OUTCOME_LABELS, TreePanel,
)
from d4t.ui.viewmodel import RecipeModel                  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def panel(qapp):
    """一棵剛分好岔的樹，停在 yes 那一片葉子上。"""
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True)
    m.ensure_tree()
    m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel()
    p.resize(431, 551)
    p.set_model(m)
    p.show_path("y")
    yield p, m
    p.deleteLater()


def _chips(panel) -> ChoiceChips:
    got = panel.findChildren(ChoiceChips)
    assert got, "葉子的托盤上沒有那一排膠囊"
    return got[-1]


# --------------------------------------------------------------------------- #
# 1. 改得到
# --------------------------------------------------------------------------- #
def test_picking_a_chip_writes_it_into_the_recipe(panel):
    """按一顆 → 寫進 model。**這一格決定判定膠囊的顏色。**"""
    p, m = panel
    chips = _chips(p)
    assert chips.text() == "", "新葉子預設是「還沒說」"

    chips._on_toggled("bad", True)         # ＝使用者點下去那一顆
    node = m.tree_node("y")
    assert isinstance(node, TreeLeaf)
    assert node.outcome == "bad"

    chips._on_toggled("good", True)
    assert m.tree_node("y").outcome == "good"


def test_nothing_is_lit_until_the_user_says_something(panel):
    """⚠ **一顆都沒亮 = 還沒說**，而那時候判定膠囊是中性灰。

    「還沒說」與「說了是中性」要分得出來：前者畫面上該多講一句，後者不必。
    一個很有把握的錯顏色比沒有顏色糟得多 —— 使用者會相信它。
    """
    p, _ = panel
    chips = _chips(p)
    assert chips.text() == ""
    assert all(not c.is_checked() for c in chips._chips), \
        "還沒說的時候不准亮一顆 —— 那就是在猜"


def test_the_tray_says_out_loud_that_nothing_has_been_answered(panel):
    """沒答的時候要有一句話，不然「灰色」看起來像壞掉了。"""
    from PySide6.QtWidgets import QLabel
    p, m = panel
    texts = [w.text() for w in p.findChildren(QLabel)]
    assert any("Not answered yet" in t for t in texts), texts

    m.set_tree_leaf("y", outcome="good")
    p.show_path("y")
    texts = [w.text() for w in p.findChildren(QLabel)]
    assert not any("Not answered yet" in t for t in texts)


# --------------------------------------------------------------------------- #
# 2. 那一排本身
# --------------------------------------------------------------------------- #
def test_the_choices_are_the_recipe_words_and_nothing_else():
    """值**就是 recipe 裡的那個字** —— 中間不放第二張「值 → 顯示名」的表。

    ⚠ ``""``（還沒說）**不是一個選項**：它是「一顆都沒亮」，講的是使用者還
    沒回答，不是一個他選得出來的答案。
    """
    assert OUTCOME_CHOICES == tuple(x for x in OUTCOMES if x)
    assert set(OUTCOME_LABELS) == set(OUTCOME_CHOICES)
    assert set(OUTCOME_HELP) == set(OUTCOME_CHOICES)
    assert len(OUTCOME_ICONS) == len(OUTCOME_CHOICES)


def test_every_icon_is_drawn_not_typed(qapp):
    """⚠ **打勾是畫出來的，不是字**（F7-23 的同一條規矩）。

    廠內的 Segoe UI 蓋不到 ``✓``／``✕`` 那一族，退字型的下場是大小與
    baseline 都不一樣，最壞是豆腐框 —— 而我們在開發機上看不到。這一條問的是
    那三個名字真的在向量圖表裡（畫不出來的名字 `draw_chip_icon` 會丟例外）。
    """
    from d4t.ui.glyphs import CHIP_ICONS
    for name in OUTCOME_ICONS:
        assert name in CHIP_ICONS, name
    for text in OUTCOME_LABELS.values():
        assert not [c for c in text if c in "●○◐◀▶▾△✓✗✕■□"], text


def test_each_choice_says_what_it_does_to_the_chip():
    """三句說明都要講出**畫面上會變成什麼顏色** —— 那是使用者按下去的理由。"""
    for name, colour in (("good", "green"), ("bad", "red"),
                         ("neutral", "grey")):
        assert colour in OUTCOME_HELP[name], (name, OUTCOME_HELP[name])
