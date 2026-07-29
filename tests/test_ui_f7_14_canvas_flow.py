# F7-14 驗收：從畫布上就做得完一條 pipeline。
"""這一輪補的是「n8n 的手感」裡真正有功能的那部分 —— 不是外觀。

以前要加一張卡，使用者得回左邊的卡片庫，從 22 張裡自己判斷哪一張接得上目前
這條流。但**「接得上」這件事引擎本來就知道**（`Step.resolve_reads`）。
所以「+」跳出來的清單只列現在就成立的卡，而且會把使用者按的那個埠的影像流
帶進新卡的主要輸入 —— 否則那顆「+」只是一個比較短的「新增卡片」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
# 1. 輸出埠上的「+」
# --------------------------------------------------------------------------- #
def test_every_output_port_has_its_own_plus(window):
    """兩個輸出埠（test / ref）= 兩顆「+」。一顆共用的「+」沒辦法表達
    「我要對 ref 做這件事」。"""
    item = window.pipeline.card(window.model.node_order[0])
    assert item.out_names() == ["test", "ref"]
    assert len(item.plus_anchors_local()) == 2

    for i, centre in enumerate(item.plus_anchors_local()):
        assert item.plus_at(centre) == i
        assert item.boundingRect().contains(centre), (
            "「+」畫在 boundingRect 外面 —— 拖動節點會留殘影（F7-8/F7-9 的老坑）")
    # 埠本身仍然拉得動線：兩個命中區不能互相吃掉
    assert item.plus_at(item.out_anchors_local()[0]) is None
    assert item.out_port_at(item.out_anchors_local()[0]) == 0


def test_pressing_the_plus_asks_for_that_port(window):
    seen = []
    window.pipeline.add_after_requested.connect(
        lambda nid, port: seen.append((nid, port)))
    nid = window.model.node_order[0]
    item = window.pipeline.card(nid)

    class _Ev:                       # 只要 button() 與 pos() 兩個方法
        def __init__(self, pos):
            self._p = pos

        def button(self):
            from PySide6.QtCore import Qt
            return Qt.LeftButton

        def pos(self):
            return self._p

        def accept(self):
            pass

    item.mousePressEvent(_Ev(item.plus_anchors_local()[1]))
    assert seen == [(nid, 1)]


# --------------------------------------------------------------------------- #
# 2. 清單只列接得上的
# --------------------------------------------------------------------------- #
def test_the_menu_only_offers_cards_that_can_connect_right_now(window):
    """Load 之後直接放 Subtract 一定缺上游（它吃 diff 之前的 ref_aligned）——
    那張卡不該出現在「接下來」的清單裡，因為那是使用者現在做不到的事。"""
    src = window.model.node_order[0]
    keys = [c["key"] for c in window.cards_addable_after(src)]
    assert "align" in keys
    assert "subtract" not in keys, "Subtract 還缺 ref_aligned"
    assert "blob_segment" not in keys
    assert "load_patch" not in keys, "一條 pipeline 只有一張 Input 卡"

    a = window.add_card_after(src, "align")
    keys_after = [c["key"] for c in window.cards_addable_after(a)]
    assert "subtract" in keys_after, "Align 產出 ref_aligned 之後就接得上了"


def test_the_menu_is_ordered_by_stage(window):
    """清單順序照流程階段（Input→Enhance→Region→Compare→Measure→ADC），
    不是照字母 —— 使用者腦中的順序是流程。"""
    from adept.core.pipeline.step import GROUP_ORDER

    cards = window.cards_addable_after(window.model.node_order[0])
    seen = [c["group"] for c in cards]
    ranks = [GROUP_ORDER.index(g) for g in seen]
    assert ranks == sorted(ranks)


def test_the_menu_says_which_stream_it_is_about(window):
    nid = window.model.node_order[0]
    window._on_add_after(nid, 1)
    try:
        texts = [a.text() for a in window._add_after_menu.actions() if a.text()]
        assert "ref" in texts[0], texts[0]
        assert "Align" in texts
    finally:
        window._add_after_menu.close()


# --------------------------------------------------------------------------- #
# 3. 按哪個埠是有意義的
# --------------------------------------------------------------------------- #
def test_the_new_card_works_on_the_stream_you_pressed(window):
    """從 ref 的埠接出一張 Denoise，結果那張卡做在 test 上 —— 那顆「+」就只是
    一個比較短的「新增卡片」，而使用者以為他已經講了「對 ref 做」。"""
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise", "ref")
    assert window.model.nodes[nid].params["target"] == "ref"
    assert "ref" in window.status_text()

    other = window.add_card_after(src, "denoise", "test")
    assert window.model.nodes[other].params["target"] == "test"


def test_adding_after_a_card_puts_it_after_that_card(window):
    """接在中間，不是接在最後面 —— 使用者指的是「這一張的後面」。"""
    src = window.model.node_order[0]
    last = window.add_card_after(src, "align")
    middle = window.add_card_after(src, "denoise", "test")
    order = window.model.node_order
    assert order.index(src) < order.index(middle) < order.index(last)
    assert (src, middle) in window.model.edges, "使用者的動作是「接」，線要是實線"


# --------------------------------------------------------------------------- #
# 4. 副標
# --------------------------------------------------------------------------- #
def test_the_subtitle_says_what_the_card_does_not_its_id(window):
    """副標以前印的是 node_id（`roi_template`）—— 那是 recipe JSON 的鍵，
    而卡片名字就在它上面一行，所以那一行等於沒有資訊。"""
    src = window.model.node_order[0]
    a = window.add_card_after(src, "align", "test")
    assert window.pipeline.card(a).subtitle() == "test ref → ref_aligned"

    b = window.add_card_after(a, "subtract")
    c = window.add_card_after(b, "roi_template", "diff")
    # Region 卡不寫影像流，它定義的是具名區域 —— 副標仍然要講得出它產出什麼
    assert window.pipeline.card(c).subtitle() == "diff → cell"


def test_a_repeated_card_shows_which_one_it_is(window):
    src = window.model.node_order[0]
    window.add_card_after(src, "denoise", "test")
    second = window.add_card_after(src, "denoise", "ref")
    assert window.pipeline.card(second).subtitle().startswith("denoise2 · ")


# --------------------------------------------------------------------------- #
# 5. 縮放
# --------------------------------------------------------------------------- #
def test_zoom_is_clamped_at_both_ends(window):
    """沒有下限，滾兩下就把整張圖縮成一個點，而且點陣底每一格都長得一樣 ——
    使用者不知道自己在哪裡，也不知道有哪顆鈕救得回來。"""
    view = window.pipeline
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
    assert len(view._zoom_buttons) == 4
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
