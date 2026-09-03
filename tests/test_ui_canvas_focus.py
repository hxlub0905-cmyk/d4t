# 畫布的「現在該看哪裡」（F78）。
"""三件事，全部是**回饋**不是功能：

1. **選中一張卡 → 接著它的線要跟著講話。** 以前選一張卡只有那張卡自己有
   反應，而使用者點它的理由通常正好是「它接了誰」—— 那個問題在畫面上要用
   眼睛沿著線走才答得出來，一張擠了十條線的畫布上根本走不完。
2. **滑鼠移到線上 → 線本身要動。** 以前只有中點長出那顆紅 ×，而線可以很長：
   × 離兩端各一百多 px，餘光裡「我現在瞄到的是哪一條」沒有答案。
3. **縮很小 → 卡片收掉小字。** 背景的點陣底早就有這條線（`drawBackground`
   在 0.45 以下不畫點），卡片沒有 —— 於是 `fit()` 到 40% 的時候，副標、設定
   摘要與左右兩排埠標籤全部變成糊在卡片上的灰噪點。

**為什麼這些驗得到而不是只能用眼睛看**：顏色／粗細的決定住在
`_EdgeItem.line_pen`、收不收小字住在 `_NodeItem.terse_at` —— 都不在 `paint`
裡。那是這個 repo 在 `shape()` / `cut_hit` 上學過的同一課：看得到的與測得到
的必須是同一個定義，不然驗它只剩下數像素，而數像素的測試在下一次改字體時
就會變紅、然後被關掉。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtGui import QTransform
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QTransform=QTransform, QApplication=QApplication,
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
    win.show()
    yield win
    win.close()


def _chain(window):
    """接出 ``source → a → b`` 兩條線，回 ``(ids, edges)``。

    要**兩**條線才問得出這一輪的問題：一條線的畫布上「哪一條該亮」沒有選擇。
    F9-7 起加卡不會自己接線，所以線要自己拉。
    """
    src = first_source(window)
    a = window.add_card_after(src, "denoise")
    window._on_edge_added(src, a, "test")
    b = window.add_card_after(a, "denoise")
    window._on_edge_added(a, b, "test")
    edges = {e.pair(): e for e in window.pipeline._edges}
    assert (src, a) in edges and (a, b) in edges
    return (src, a, b), edges


# --------------------------------------------------------------------------- #
# 1. 選中一張卡 → 它的線亮，其他的退下去
# --------------------------------------------------------------------------- #
def test_with_nothing_selected_every_line_is_drawn_the_same(window):
    """沒選任何東西的時候不准有「主角」—— 那時候整張圖就是主角。"""
    _ids, edges = _chain(window)
    window.pipeline.set_selected(None)

    assert window.pipeline.has_node_selection() is False
    assert {e.focus_state() for e in edges.values()} == {"flat"}


def test_selecting_a_card_lights_the_lines_that_touch_it(window):
    """選中間那張卡：兩條線都接著它，兩條都要亮。"""
    (src, a, b), edges = _chain(window)
    window.pipeline.set_selected(a)

    assert edges[(src, a)].focus_state() == "near"
    assert edges[(a, b)].focus_state() == "near"


def test_the_lines_that_do_not_touch_it_step_back(window):
    """選最後那張卡：只有進到它的那一條該亮，另一條要退下去。"""
    (src, a, b), edges = _chain(window)
    window.pipeline.set_selected(b)

    assert edges[(a, b)].focus_state() == "near"
    assert edges[(src, a)].focus_state() == "far", (
        "跟選中的卡無關的線沒有退下去 —— 那樣「它接了誰」還是要用眼睛走")


def test_a_line_that_stepped_back_is_still_visible(window):
    """**退下去不是消失。**

    那些線仍然是這張圖的骨架，只是這一刻不是使用者在問的東西。混到跟畫布
    底色一樣的話，選一張卡等於把 recipe 的其餘部分擦掉 —— 而使用者下一個
    動作往往正是「那我上一張接的是什麼」。
    """
    (src, a, b), edges = _chain(window)
    window.pipeline.set_selected(b)

    faded = edges[(src, a)].line_pen().color()
    bg = theme_mod.TOKENS["canvas_bg"]
    assert theme_mod.contrast_ratio(faded.name(), bg) > 1.15, (
        "退下去的線跟畫布底色混在一起了：%s vs %s" % (faded.name(), bg))


def test_lighting_up_means_the_same_colour_louder_not_a_new_colour(window):
    """亮起來要**調濃同一個色相**，不是換成藍色。

    換色的話使用者得學「藍色 = 被選中的線」這第二層意思，而線的顏色現在講
    的是「它從哪張卡出來」（F13-⑤）—— 那個意思會被蓋掉。
    """
    (src, a, b), edges = _chain(window)
    edge = edges[(a, b)]

    window.pipeline.set_selected(None)
    flat = edge.line_pen()
    window.pipeline.set_selected(b)
    near = edge.line_pen()

    assert near.color().name() != flat.color().name(), "亮起來但顏色沒變"
    assert near.widthF() > flat.widthF(), "亮起來但沒有加粗"
    assert near.color().name() != theme_mod.TOKENS["canvas_edge_active"], (
        "亮起來變成了 accent 藍 —— 那會蓋掉「這條線從哪張卡出來」的意思")


def test_selecting_a_line_does_not_dim_the_other_lines(window):
    """選的是**線**的時候，其他線不該退下去。

    `has_node_selection` 問的是卡片而不是 `scene().selectedItems()`，這條
    測試守的就是那個差別 —— 線自己也是可選的。
    """
    _ids, edges = _chain(window)
    window.pipeline.set_selected(None)
    edge = next(iter(edges.values()))
    edge.setSelected(True)

    assert window.pipeline.has_node_selection() is False
    others = [e for e in edges.values() if e is not edge]
    assert {e.focus_state() for e in others} == {"flat"}


def test_selecting_a_card_the_qt_way_also_works(window):
    """框選／點卡片走的是 Qt 自己的選取，不經過 `set_selected`。

    這一條守的是「接的是 scene 的 selectionChanged，不是補在 set_selected
    裡」—— 只補後者的話，框選出來的卡片線不會亮，而那是「有時候會亮有時候
    不會」這種找不到的 bug。
    """
    (src, a, b), edges = _chain(window)
    window.pipeline.set_selected(None)
    window.pipeline.node_item(a).setSelected(True)

    assert window.pipeline.has_node_selection() is True
    assert edges[(src, a)].focus_state() == "near"


# --------------------------------------------------------------------------- #
# 2. 滑鼠移到線上 → 線本身要動
# --------------------------------------------------------------------------- #
def test_hovering_a_line_changes_the_line_and_not_just_the_cut_button(window):
    """× 只在中點，而線可以橫過大半個畫布。"""
    _ids, edges = _chain(window)
    edge = next(iter(edges.values()))

    before = edge.line_pen()
    edge._hover = True
    after = edge.line_pen()

    assert after.widthF() > before.widthF()
    assert after.color().name() != before.color().name()


def test_a_hovered_line_stays_loud_even_when_it_is_the_one_stepping_back(window):
    """滑鼠壓著的那一條**永遠**是主角，即使它跟選中的卡無關。

    不然會出現「滑過去了、× 也出現了，可是線還是灰的」—— 使用者會以為自己
    瞄的是別條。
    """
    (src, a, b), edges = _chain(window)
    window.pipeline.set_selected(b)
    edge = edges[(src, a)]
    assert edge.focus_state() == "far"

    edge._hover = True
    assert edge.line_pen().color().name() == theme_mod.TOKENS["canvas_edge_active"]


# --------------------------------------------------------------------------- #
# 3. 縮很小 → 卡片收掉小字
# --------------------------------------------------------------------------- #
def test_cards_stop_drawing_the_small_print_before_the_dots_stop(window):
    """字比點更早糊，所以卡片的門檻不能比背景的鬆。"""
    canvas = window.pipeline
    item = canvas.node_item(first_source(window))

    assert item.terse_at(1.0) is False
    assert item.terse_at(0.4) is True
    assert canvas_mod._LOD_TERSE >= 0.45, (
        "卡片的小字撐得比背景的點還久 —— 那正是 fit() 之後那層灰噪點")


def test_zoomed_out_a_card_keeps_its_title_and_drops_the_rest(window):
    """**真的畫一次**，數 `_draw_elided` 被呼叫了幾次、畫的是什麼。

    問的不是「旗標對不對」而是「畫面上少了哪幾行」，而標題必須留著 ——
    那是這張卡的身分，也是縮小之後唯一還讀得出輪廓的一行。
    """
    from PySide6.QtGui import QImage, QPainter

    (src, a, _b), _edges = _chain(window)
    item = window.pipeline.node_item(a)
    label = str(item.info.get("label", a))

    drawn = []
    real = canvas_mod._draw_elided

    def spy(p, rect, text, align=None):
        drawn.append(str(text))
        return real(p, rect, text) if align is None else real(p, rect, text, align)

    canvas_mod._draw_elided = spy
    try:
        seen = {}
        for scale in (1.0, 0.4):
            drawn.clear()
            img = QImage(400, 200, QImage.Format_ARGB32)
            img.fill(0)
            painter = QPainter(img)
            painter.setTransform(QTransform().scale(scale, scale))
            item.paint(painter, None)
            painter.end()
            seen[scale] = list(drawn)
    finally:
        canvas_mod._draw_elided = real

    assert label in seen[1.0] and label in seen[0.4], "縮小之後連標題都不見了"
    assert len(seen[0.4]) == 1, (
        "縮到 40% 還在畫 %d 行字：%r" % (len(seen[0.4]), seen[0.4]))
    assert len(seen[1.0]) > len(seen[0.4]), (
        "100% 跟 40% 畫的東西一樣多 —— LOD 沒有生效")


# --------------------------------------------------------------------------- #
# 4. 重建畫布的那一瞬間，選取問得出答案（2026-09-03）
# --------------------------------------------------------------------------- #
# 使用者回報：拉一條線就跳
# `RuntimeError: Internal C++ object (_NodeItem) already deleted`，
# 出處正是上面第 1 節那支 handler。`set_nodes` 的 `scene.clear()` 會銷毀選著
# 的圖元，Qt 當場送出 `selectionChanged` —— 而那時候 `_items` 還握著剛被銷毀
# 的那一批。不是「選取壞了」，是**問的時機在拆除的半路上**。
def _selection_probe(canvas):
    """每一次 `selectionChanged` 都問一次「表上的圖元還活著嗎」。"""
    alive = []

    def probe():
        try:
            [it.isSelected() for it in canvas._items.values()]
            [e.isVisible() for e in canvas._edges]
        except RuntimeError:
            alive.append(False)
        else:
            alive.append(True)

    canvas._scene.selectionChanged.connect(probe)
    return alive


def test_a_rebuild_never_asks_the_selection_about_dead_items(window):
    (src, _a, b), _edges = _chain(window)
    window.pipeline.set_selected(b)
    alive = _selection_probe(window.pipeline)

    window._on_edge_added(src, b, "test")      # 加一條線 = 整張畫布重建

    assert alive, "重建過程真的送出了 selectionChanged（不然這支測試是空的）"
    assert all(alive), "表上還留著被 clear() 銷毀的圖元"


def test_wiring_a_line_while_a_card_is_selected_prints_no_traceback(window,
                                                                    capfd):
    """使用者看到的是**終端機那一串**，所以就照那個看。"""
    (src, _a, b), _edges = _chain(window)
    window.pipeline.set_selected(b)
    capfd.readouterr()

    window._on_edge_added(src, b, "test")

    assert "already deleted" not in capfd.readouterr().err
