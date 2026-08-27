# F13-1：把空白還給畫布 — authored 2026-08-19.
"""**畫面上最大的一塊，不可以是一句「請去別的地方點一個東西」。**

起點是實測（1600×1000 的視窗）：

* 中欄（主要工作區）只有 551px 寬，而預覽欄有 791px；
* 中欄再上下切成 **畫布 368 / 設定 551**，而設定區在沒選卡片時只裝了一行灰字；
* 於是畫布被壓到 **50% 縮放** —— 而卡片的副標（「這張卡吃什麼吐什麼」）
  要到 70% 才讀得回來（`PipelineCanvas.MIN_FIT_SCALE` 的說明量過）。

三個都是空的地方在擠一個不夠用的地方。這一份鎖住兩個修法：

1. **設定區的高度跟著「有沒有東西可以設定」走**；
2. **換行點跟著畫布真的有多寬走**（以前寫死 4，等於要求 1050px）。

沒有動預覽欄的寬度 —— 「影像大一點」是使用者自己要求的（見
`test_ui_results.test_preview_gets_the_widest_column`），不拿它的空間去補。

⚠ **F39-B5（2026-08-27）刪了兩條純重複的**：
``selecting_a_card_opens_it_again`` 與
``the_settings_pane_gives_the_space_back_when_nothing_is_selected``
的斷言**整組**在 ``test_ui_f8_ui_polish.py::test_the_canvas_is_the_top_block_and_settings_get_the_rest``
裡（那一條還多驗了「畫布在上、設定在下」）。驗過：把 ``set_params_open`` 收起
來的那一半改成不還空間給畫布，兩邊都紅 —— 所以留一邊就夠。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from d4t.ui import canvas as canvas_mod             # noqa: E402
from d4t.ui import studio as studio_mod             # noqa: E402
from d4t.ui import theme as theme_mod               # noqa: E402

EXAMPLE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1600, 1000)
    win.show()
    win.load_recipe_path(str(EXAMPLE), sync=True)
    for _ in range(6):
        qapp.processEvents()
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 設定區跟著「有沒有東西可以設定」走
# --------------------------------------------------------------------------- #


def test_editing_a_parameter_does_not_reset_a_split_the_user_dragged(window, qapp):
    """`_refresh_pipeline` 每改一個參數就跑一次 —— 它不可以順手重排版面。"""
    nid = first_source(window)
    window.select_node(nid)
    qapp.processEvents()
    window.canvas_column.setSizes([700, 200])          # 使用者自己拖的
    mine = list(window.canvas_column.sizes())

    window.model.set_param(nid, "channels", "auto")
    qapp.processEvents()
    assert window.canvas_column.sizes() == mine, "使用者拖的分隔線被洗掉了"


# --------------------------------------------------------------------------- #
# 2. 換行點跟著畫布真的有多寬走
# --------------------------------------------------------------------------- #
def test_wrap_follows_the_width_it_actually_has():
    per_card = canvas_mod.NODE_W + canvas_mod.COL_GAP
    assert canvas_mod.wrap_for_width(200) == 1, "放不下第二張就不要排第二欄"
    assert canvas_mod.wrap_for_width(5 * per_card) == canvas_mod.WRAP, \
        "再寬也不排成一條要橫著掃的長列"
    widths = [200, 400, 600, 800, 1000, 1400]
    got = [canvas_mod.wrap_for_width(w) for w in widths]
    assert got == sorted(got), "越寬不可以排得越少：%s" % got


def test_a_canvas_too_narrow_to_be_real_keeps_the_old_layout(qapp):
    """**一張卡都放不下的寬度不是版面，是還沒被 layout 過的 widget。**

    主視窗裡的畫布在 `show()` 之前 viewport 只有 89px（實測）——把它當真的話，
    整份 recipe 會在那一刻被排成一直條，而使用者從來沒有看到過那個寬度。
    所以窄到連一張卡加它的埠標籤都放不下時，退回既有的 :data:`WRAP`。
    """
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    view = canvas_mod.PipelineCanvas(holder)
    try:
        view.setGeometry(0, 0, 120, 200)
        qapp.processEvents()
        assert view.viewport().width() < canvas_mod.NODE_W
        assert view.wrap() == canvas_mod.WRAP
    finally:
        holder.deleteLater()


def test_the_cards_end_up_readable_not_shrunk_to_half(window):
    """整條不變量的出口：**副標讀得出來**。

    50% 是這一輪之前實測到的縮放，而 70% 是副標回得來的那條線。
    """
    assert window.pipeline.zoom_percent() >= 70, \
        "畫布縮到 %d%% —— 卡片的副標讀不出來" % window.pipeline.zoom_percent()
    cols = {round(window.pipeline.card(n).pos().x())
            for n in window.pipeline.node_ids()}
    assert 1 < len(cols) <= canvas_mod.WRAP


# --------------------------------------------------------------------------- #
# 3. 版面記得住，但**測試裡不還原**
# --------------------------------------------------------------------------- #
def test_saved_sizes_are_never_restored_inside_the_tests():
    """還原了的話，某一次手動跑 GUI 拖過的分隔線會漏進下一次的測試 ——
    而版面斷言就開始看人品。"""
    studio_mod._save_sizes(studio_mod.COLUMNS_KEY, [111, 222, 333])
    assert studio_mod._load_sizes(studio_mod.COLUMNS_KEY, 3) is None


def test_the_sizes_do_round_trip_outside_the_tests(monkeypatch):
    monkeypatch.setattr(studio_mod, "_running_under_pytest", lambda: False)
    studio_mod._save_sizes(studio_mod.COLUMNS_KEY, [111, 222, 333])
    assert studio_mod._load_sizes(studio_mod.COLUMNS_KEY, 3) == [111, 222, 333]
    # 數量對不上（欄數改了）→ 當作沒存過，不要拿舊的去套新的版面
    assert studio_mod._load_sizes(studio_mod.COLUMNS_KEY, 2) is None


# --------------------------------------------------------------------------- #
# 4. 卡片本身（F13-⑤）
# --------------------------------------------------------------------------- #
def test_a_port_label_that_does_not_fit_says_so(qapp):
    """靠右對齊的字，Qt 是從**左邊**硬切的。

    `Borrow range from` 因此被畫成 `nge from` —— 讀起來像另一個欄位的名字，
    而畫面上沒有任何東西說它被切過。省略號至少講出「這裡還有字」。
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainter, QPixmap

    pm = QPixmap(200, 40)
    p = QPainter(pm)
    try:
        wide = QRectF(0, 0, 190, 14)
        narrow = QRectF(0, 0, 40, 14)
        assert canvas_mod._draw_elided.__doc__
        # 放得下 → 原字；放不下 → 以 … 結尾（兩種對齊都一樣）
        for align in (Qt.AlignLeft, Qt.AlignRight):
            assert p.fontMetrics().elidedText(
                "Borrow range from", Qt.ElideRight, 40).endswith("…")
            canvas_mod._draw_elided(p, narrow, "Borrow range from", align=align)
            canvas_mod._draw_elided(p, wide, "ref", align=align)
    finally:
        p.end()


def test_the_card_is_big_enough_for_three_lines_of_text(qapp):
    """卡上有三行字（標題／副標／設定摘要），而它們的 y 位置是寫死的 ——
    卡片變矮的話最後一行會被畫到框外面，而 Qt 不會抱怨。"""
    assert canvas_mod.NODE_H >= 43 + 14 + 4
    # 欄距要塞得下**兩側**的埠標籤，否則上游的輸出名與下游的輸入名會疊在
    # 同一塊空白上（F13-⑤ 實測 `layout_label` 疊到 `single`）。
    assert canvas_mod.COL_GAP >= 2 * canvas_mod._PORT_LABEL_W


def test_a_line_carries_the_colour_of_the_card_it_leaves(qapp):
    """十條線的畫布上，「這條是從哪裡出來的」不該只能用眼睛沿著線走。"""
    from d4t.ui import theme as theme_mod

    view = canvas_mod.PipelineCanvas()
    try:
        view.set_nodes(
            [{"node_id": "a", "label": "A", "group": "input",
              "writes": ["test"], "reads": [], "inputs": []},
             {"node_id": "b", "label": "B", "group": "measure",
              "writes": [], "reads": ["test"],
              "inputs": [{"name": "source", "label": "Source", "stream": "test"}]}],
            [("a", "b", "test", "source")])
        edge = view._edges[0]
        assert edge.line_color().name() != theme_mod.TOKENS["canvas_edge"]
        # **調淡一半** —— 線平常畫在卡片底下，它是背景不是主角。
        assert edge.line_color().name() != theme_mod.group_hex("input")
    finally:
        view.deleteLater()
