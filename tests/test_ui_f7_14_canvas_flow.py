# F7-14 驗收：從畫布上就做得完一條 pipeline（F7-18 修訂）。
"""這一輪補的是「n8n 的手感」裡真正有功能的那部分 —— 不是外觀。

**F7-18 拿掉了輸出埠上的「+」**（使用者的原話：那個加號會永久存在，還是從旁邊
的卡片庫手動加就好）。它做對的那兩件事沒有跟著消失，只是換了入口：
`add_card_after` 仍然「接在這一張後面」並且「做在對的那條流上」，而卡片庫在
選著一張卡的時候就走這條路。埠本身照樣拉得動線 —— 拉線現在還會**指定影像流**
（見 `test_ui_f7_18_streams_as_nodes.py`）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, QPointF=QPointF,
             canvas_mod=canvas_mod, studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 輸出埠（F7-18：不再掛一顆常駐的「+」）
# --------------------------------------------------------------------------- #
def test_the_ports_carry_no_permanent_plus(window):
    """使用者的原話：「加號會永久存在」。一張畫布上每個輸出埠各掛一顆，
    等於在主體（節點與連線）旁邊常駐一排跟資料流無關的裝飾。"""
    item = window.pipeline.card(first_source(window))
    assert item.out_names() == ["test", "ref"]
    assert not hasattr(item, "plus_anchors_local")
    assert not hasattr(item, "plus_at")

    # boundingRect 也要跟著縮回來 —— 留著那塊空間會讓節點之間互相吃到點擊。
    right = item.boundingRect().right()
    assert right < canvas_mod.NODE_W + canvas_mod._PORT_LABEL_W + 12


def test_the_ports_themselves_still_start_a_connection(window):
    """拿掉「+」不能連帶把拉線弄丟 —— 那是畫布唯一的輸入方式。"""
    item = window.pipeline.card(first_source(window))
    for i, anchor in enumerate(item.out_anchors_local()):
        assert item.out_port_at(anchor) == i
        assert item.boundingRect().contains(anchor)


# --------------------------------------------------------------------------- #
# 3. 接在哪一張後面、做在哪一條流上
# --------------------------------------------------------------------------- #
def test_the_card_works_on_the_stream_the_line_came_from(window):
    """新卡做在哪一條流上，由**使用者拉的那條線**決定（F9-7）。

    F7-14 時是加卡順手決定的（``add_card_after(..., "ref")``）；2026-08-16
    使用者退掉了那件事 —— 「新增卡 不要自己接線」。線是唯一的作者，所以這一條
    改成問「從 ref 那顆埠拉過來，這張卡是不是就做在 ref 上」。
    """
    src = first_source(window)
    nid = window.add_card_after(src, "denoise")
    window._on_edge_added(src, nid, "ref")
    assert window.model.nodes[nid].params["streams"] == "ref"
    assert "ref" in window.status_text()

    other = window.add_card_after(src, "denoise")
    window._on_edge_added(src, other, "test")
    assert window.model.nodes[other].params["streams"] == "test"


def test_adding_after_a_card_puts_it_after_that_card(window):
    """接在中間，不是接在最後面 —— 使用者指的是「這一張的後面」。"""
    src = first_source(window)
    last = window.add_card_after(src, "align")
    middle = window.add_card_after(src, "denoise")
    order = window.model.node_order
    assert order.index(src) < order.index(middle) < order.index(last)
    # F9-7：**線不會自己出現**。順序是順序，資料從哪來是使用者拉的線。
    assert (src, middle) not in window.model.edge_pairs()


# --------------------------------------------------------------------------- #
# 4. 副標
# --------------------------------------------------------------------------- #
def test_the_subtitle_says_what_the_card_does_not_its_id(window):
    """副標以前印的是 node_id（`roi_template`）—— 那是 recipe JSON 的鍵，
    而卡片名字就在它上面一行，所以那一行等於沒有資訊。"""
    src = first_source(window)
    a = window.add_card_after(src, "align")
    # F10：副標講的是「這張卡吃什麼、吐什麼」，而還沒接線的卡兩者都還不存在
    # —— 所以先把線拉上去，那正是使用者要看到這一行之前會做的事。
    window._on_edge_added(src, a, "ref", "moving")
    window._on_edge_added(src, a, "test", "fixed")
    assert window.pipeline.card(a).subtitle() == "test ref → ref_aligned"

    b = window.add_card_after(a, "subtract")
    window._on_edge_added(src, b, "test", "a")
    window._on_edge_added(a, b, "ref_aligned", "b")
    c = window.add_card_after(b, "roi_template")
    window._on_edge_added(b, c, "diff")        # 來源由線決定（F9-7）
    # 還沒畫任何區域 -> 這張卡真的還沒產出任何東西，副標照實只講輸入
    assert window.pipeline.card(c).subtitle() == "diff"
    # Region 卡不寫影像流，它定義的是具名區域 —— 副標仍然要講得出它產出什麼
    window.model.set_param(c, "regions", "epi: 0.1,0,0.3,1")
    window.select_node(c)
    assert window.pipeline.card(c).subtitle() == "diff → epi epi_center"


def test_a_repeated_card_shows_which_one_it_is(window):
    src = first_source(window)
    window.add_card_after(src, "denoise")
    second = window.add_card_after(src, "denoise")
    assert window.pipeline.card(second).subtitle().startswith("denoise2 · ")


# --------------------------------------------------------------------------- #
# 5. 縮放
# --------------------------------------------------------------------------- #
def test_zoom_is_clamped_at_both_ends(window):
    """沒有下限，滾兩下就把整張圖縮成一個點，而且點陣底每一格都長得一樣 ——
    使用者不知道自己在哪裡，也不知道有哪顆鈕救得回來。"""
    view = window.pipeline
    # 明確從 100% 出發：開一份 recipe 現在會自動 fit（見 canvas.fit_later），
    # 所以「起點一定是 100%」已經不成立 —— 而這條測的是兩端的夾制，不是起點。
    view.reset_zoom()
    assert view.zoom_percent() == 100
    for _ in range(30):
        view.zoom_by(1 / 1.25)
    assert view.zoom_percent() == int(round(view.MIN_SCALE * 100))
    for _ in range(60):
        view.zoom_by(1.25)
    assert view.zoom_percent() == int(round(view.MAX_SCALE * 100))
    view.reset_zoom()
    assert view.zoom_percent() == 100


def test_the_zoom_controls_are_on_screen_and_say_the_current_zoom(window):
    view = window.pipeline
    window.show()
    # 四顆縮放 + 「排整齊」（F7-22）+ 「彈出視窗」（F8-UI D 案）——
    # 都只動「怎麼看」，不動 recipe，所以同一排。
    assert len(view._zoom_buttons) == 6
    assert view._zoom_bar.isVisibleTo(view)
    view.zoom_by(1.25)
    assert view._zoom_label.text() == "%d%%" % view.zoom_percent()
    # 左下角：不擋到節點（節點從左上角開始排）
    assert view._zoom_bar.x() < view.viewport().width() / 2
    assert view._zoom_bar.y() > view.viewport().height() / 2


def test_fit_then_reset_is_a_way_back(window):
    """fit 之後字會變小，這時候要有一顆「回到 100%」—— 不然使用者只能滾回來，
    而滾回來要滾幾下沒有人知道。"""
    view = window.pipeline
    for key in ("align", "subtract", "snr_map", "blob_segment"):
        view.fit()
    view.fit()
    view.reset_zoom()
    assert view.zoom_percent() == 100
