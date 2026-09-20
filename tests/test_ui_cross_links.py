# F117 I6：畫布、Features、Results 互相指得到（2026-09-20）。
"""這三塊講的是同一顆 defect 的三個面向 —— 畫布是**怎麼算的**、Features 是
**算出什麼**、Results 是**一整批算出什麼**。在這之前，從一個數字回頭找到算它
的那張卡，靠的是使用者自己記得。

兩條路，而**它們刻意不一樣**：

* **滑過 Features 的一段** → `reveal_cards`（hover 那一套）。只是看一眼，
  所以不動右邊的設定；滑鼠一離開就熄掉。
* **Results 欄名的右鍵選單** → `select_node`（真的選取）。那是「帶我去」，
  點下去就是要動手改。

⚠ **右鍵不是左鍵**：表頭的左鍵已經是排序，搶走它等於把一個每天都在用的手勢
換成一個偶爾用的。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent                        # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame       # noqa: E402

from d4t.core import steps as _steps                     # noqa: E402,F401
from d4t.core.pipeline.verdict_features import bound_specs   # noqa: E402
from d4t.ui import cross_links                           # noqa: E402
from d4t.ui import theme as theme_mod                    # noqa: E402
from d4t.ui.feature_panel import FeaturePanel, panel_model    # noqa: E402

RECIPE = str(REPO / "recipes" / "ebi-die-to-die.json")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert win.load_recipe_path(RECIPE) is True
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 誰算出這個數字
# --------------------------------------------------------------------------- #
def test_it_finds_the_card_that_measures_a_feature(window):
    assert cross_links.node_of_feature(window, "glv_mean") == "glv"


def test_the_engine_columns_belong_to_nobody(window):
    """⚠ `score` / `bin` 不是任何一張卡量出來的 —— 它們是判定段寫的。

    答「沒有」比答一個最像的好：指去一張沒有在算它的卡，使用者會照著改，
    而畫面上什麼都不會變。
    """
    assert cross_links.node_of_feature(window, "score") == ""
    assert cross_links.node_of_feature(window, "bin") == ""


def test_a_name_nobody_writes_is_not_guessed(window):
    assert cross_links.node_of_feature(window, "nope_at_all") == ""
    assert cross_links.node_of_feature(window, "") == ""


def test_it_never_raises_on_a_broken_model(qapp):
    """⚠ 這是顯示層 —— 問不出來就當作沒有，**不准把畫面炸掉**。"""
    class _Broken:
        model = None

    assert cross_links.node_of_feature(_Broken(), "glv_mean") == ""


# --------------------------------------------------------------------------- #
# 滑過 Features → 畫布指給我看
# --------------------------------------------------------------------------- #
def _sections(panel):
    return [f for f in panel.findChildren(QFrame) if f.property("d4tNode")]


def test_hovering_a_block_says_which_card_it_came_from(qapp, window):
    b = bound_specs(window.model.to_recipe(), "ebi_patch")
    panel = window.feature_panel
    panel.set_model(panel_model({x.spec.name: 1.0 for x in b}, b))
    said = []
    panel.card_hovered.connect(said.append)
    secs = _sections(panel)
    assert secs, "沒有任何一段掛著 node id —— 這條測試沒在測東西"
    qapp.sendEvent(secs[0], QEvent(QEvent.Enter))
    assert said and said[-1], said


def test_leaving_says_so_too(qapp, window):
    """⚠ **離開要送空字串，不是不送。**

    不送的話，滑鼠移出面板之後那張卡會一直亮著，而使用者早就不在看它了。
    """
    b = bound_specs(window.model.to_recipe(), "ebi_patch")
    panel = window.feature_panel
    panel.set_model(panel_model({x.spec.name: 1.0 for x in b}, b))
    said = []
    panel.card_hovered.connect(said.append)
    sec = _sections(panel)[0]
    qapp.sendEvent(sec, QEvent(QEvent.Enter))
    qapp.sendEvent(sec, QEvent(QEvent.Leave))
    assert said[-1] == "", said


def test_a_block_with_no_card_stays_quiet(qapp):
    """判定段那一群（`score` / `bin`）沒有 node id —— 滑過去不該指任何人。"""
    panel = FeaturePanel()
    try:
        panel.set_model([{"node_id": "", "label": "Score / Bin", "region": "",
                          "region_index": -1, "kind": "card", "headline": [],
                          "grid": {"columns": [], "rows": []},
                          "flat": [{"name": "score", "value": 1.0, "unit": "",
                                    "gloss": "", "kind": "", "verdict": False,
                                    "html": "score"}]}])
        assert _sections(panel) == []
    finally:
        panel.deleteLater()


def test_hovering_reveals_and_does_not_select(window):
    """⚠ **`reveal_cards` 不是 `select_card`。**

    選取會把右邊的設定換成那張卡，而使用者現在只是在讀數字 —— 他要的是眼睛
    找到來源，不是換一張卡編。
    """
    before = window.selected_node
    cross_links.hover_card(window, "glv")
    assert window.selected_node == before, "滑過去就把選取換掉了"
    assert window.pipeline._ghost_cards, "畫布上沒有指出任何一張卡"
    cross_links.hover_card(window, "")
    assert not window.pipeline._ghost_cards, "滑鼠離開了，那張卡還亮著"


# --------------------------------------------------------------------------- #
# Results 欄名 → 跳到那張卡
# --------------------------------------------------------------------------- #
def test_going_to_a_feature_really_selects_it(window):
    """⚠ 這一條跟滑過去刻意不同：**點下去是「帶我去」，所以真的選取。**"""
    cross_links.go_to_feature(window, "glv_mean")
    assert window.selected_node == "glv"


def test_a_column_nobody_measures_says_so(window):
    """⚠ 一個點下去什麼都沒發生的選單項，會讓使用者以為是自己點錯了。"""
    cross_links.go_to_feature(window, "nope_at_all")
    assert "nope_at_all" in window.status_text(), window.status_text()


def test_the_engine_columns_have_no_menu_entry(qapp):
    """⚠ `defect_id` / `bin` / `score` 那幾欄不是任何一張卡量出來的。

    給它們一個只會說「找不到」的選單項，比沒有那一項更傷。
    """
    from d4t.ui.results_table import _NOT_MEASURED

    for name in ("defect_id", "bin", "score", "ok", "error"):
        assert name in _NOT_MEASURED, name
    assert "glv_mean" not in _NOT_MEASURED


def test_the_left_click_on_the_header_is_still_sorting(qapp):
    """⚠ **右鍵不是左鍵。**

    表頭的左鍵已經是排序（`setSortingEnabled`）—— 搶走它等於把一個每天都在
    用的手勢換成一個偶爾用的。
    """
    from PySide6.QtCore import Qt

    from d4t.ui.results_table import ResultsTablePane

    pane = ResultsTablePane()
    try:
        assert pane.table.isSortingEnabled()
        head = pane.table.horizontalHeader()
        assert head.contextMenuPolicy() == Qt.CustomContextMenu
    finally:
        pane.deleteLater()


def test_the_signal_reaches_the_window(qapp):
    """訊號要一路轉出去：`ResultsTable` → pane → `ResultsWindow`。"""
    from d4t.ui.results import ResultsWindow

    win = ResultsWindow()
    try:
        got = []
        win.card_requested.connect(got.append)
        win.table.table.card_requested.emit("glv_mean")
        assert got == ["glv_mean"], got
    finally:
        win.close()


def test_the_wiring_does_not_add_a_studio_method():
    """⚠ **`StudioWindow` 的方法數是 `HARD_CAPS`（只准往下）。**

    所以這兩條接線接的是 `partial(cross_links.…, win)`，不是兩個新方法 ——
    而內容住在 `cross_links` 也比較好測（測試直接叫那一支，不必開視窗）。
    """
    import ast

    src = (REPO / "d4t" / "ui" / "studio.py").read_text(encoding="utf-8")
    names = {n.name for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.FunctionDef)}
    assert "_on_feature_card_hovered" not in names
    assert "_on_feature_card_requested" not in names
