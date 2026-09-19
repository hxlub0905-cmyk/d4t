# F117 A5：面板不准叫人去點看不到的東西（2026-09-20）。
"""判定區的卡片寫 `tree hidden — double-click to show`，而判定面板同時寫
「click a diamond on the canvas」—— **樹收著的時候畫布上一顆菱形都沒有。**

一句叫人去點看不到的東西的提示，比沒有提示糟：他會以為是自己找不到。

⚠ **這一支存在的第二個理由**：第一版的接線寫成
`getattr(self, "canvas", None)`，而那個屬性叫 `pipeline` —— `getattr` 的預設
把它整個吞掉，於是那一版**永遠回 False**：A5 等於沒修，而沒有任何測試會紅。
所以這裡問的是「兩種狀態講出**不同**的話」，不是「那支 setter 被呼叫了」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import studio as studio_mod               # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402

RECIPE = REPO / "recipes" / "ebi-die-to-die.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    w = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert w.load_recipe_path(str(RECIPE), sync=True)
    yield w
    w.close()


def _head(win) -> str:
    win._sync_score_widgets()
    return win.decide_panel.head.text()


def test_the_two_states_do_not_say_the_same_thing(window):
    """⚠ **這就是那個安靜的錯會被抓到的地方。**

    接線壞掉的時候，收著與攤開講的是同一句話 —— 而畫面上看起來完全正常。
    """
    win = window
    collapsed = win.pipeline.tree_collapsed()
    first = _head(win)
    win.pipeline.toggle_tree_collapsed()
    assert win.pipeline.tree_collapsed() is not collapsed, "前提：真的切過去了"
    second = _head(win)
    assert first != second, "收著與攤開講同一句話 —— 那個接線是斷的"


def test_when_the_tree_is_hidden_it_says_how_to_show_it(window):
    """收著的時候不准叫人去點菱形 —— 畫布上一顆都沒有。"""
    win = window
    if not win.pipeline.tree_collapsed():
        win.pipeline.toggle_tree_collapsed()
    said = _head(win)
    assert "double-click" in said, said
    assert "click a diamond there" not in said, \
        "樹收著，而面板還在叫人去點一顆看不到的菱形"


def test_when_the_tree_is_open_it_points_at_the_diamonds(window):
    """攤開的時候那句話就該是原本那一句（菱形真的在那裡）。"""
    win = window
    if win.pipeline.tree_collapsed():
        win.pipeline.toggle_tree_collapsed()
    said = _head(win)
    assert "click a diamond there" in said, said


def test_the_panel_can_be_told_without_a_canvas(qapp):
    """面板自己不認識畫布 —— 它只收一個布林（同 `set_counts` 的界線）。"""
    from d4t.ui.decide_panel import DecidePanel

    p = DecidePanel()
    try:
        p.set_tree_collapsed(True)
        p.set_tree_collapsed(False)          # 不准因為「沒變」就不 refresh
    finally:
        p.deleteLater()
