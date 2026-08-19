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
def test_the_settings_pane_gives_the_space_back_when_nothing_is_selected(window):
    assert window.selected_node is None
    assert window.params_open() is False
    assert window.canvas_column.sizes()[1] == 0, "那一塊要整個還給畫布"


def test_selecting_a_card_opens_it_again(window, qapp):
    window.select_node(first_source(window))
    qapp.processEvents()
    assert window.params_open() is True
    top, bottom = window.canvas_column.sizes()
    assert bottom > top, "設定拿大頭（D 案的比例沒有變）"


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
