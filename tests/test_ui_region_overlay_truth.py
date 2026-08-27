# 疊在影像上的框不能說謊（常駐）。
"""**畫面上的框，就是這張卡真的會量的那幾塊。**

2026-08-27（F39-B4）從 `test_ui_crossing_inspector.py`（當時叫 `test_ui_f8_cross.py`） 切出來的十一條。它們原本混在
交會定位那一輪的驗收裡，但問的其實跟那張卡無關 —— 是**每一張 Region 卡**
都必須成立的四件事：

1. **有幾個框就畫幾個。** 一個名字底下八個框、畫面上只出現一個的話，使用者
   會以為量的是那一塊，而畫面上沒有任何東西透露這件事。
2. **不必按任何鈕就看得到，而且參數一改當場就變。** 定位卡的參數是一邊拖一邊
   看決定的；框只出現在「跑完一批」的另一個視窗裡，等於把調敏感度變成改一次
   跑一次，而那要試十幾次。
3. **「這一顆」落在哪個框裡要標出來**，而且**只畫選著那張卡的框**。
4. **一張卡好幾個區域時，框要分色**，而且顏色跟模板編輯器同一組 ——
   使用者在對話框裡把 ROI1 畫成綠色，到了 patch 上它就要還是綠色。
   ⚠ 名字與框對不起來的時候**寧可不上色**：錯位的顏色比沒有顏色糟得多，
   它會**指錯**區域，而畫面上不會說。

框從跑完的 context 來、名字從 `_overlay_region_names` 來 —— 兩份各自算的話，
區域一多顏色就會指到隔壁那個。這裡守的就是「兩邊走同一個清單」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from tests.region_cards import add_region_step  # noqa: E402

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import region_check as rc_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, rc_mod=rc_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lines_lot(tmp_path_factory):
    """兩軸不同週期的線陣列 —— 多框區域最自然的形狀。"""
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("overlay_lines")), n=6, seed=4,
                    size=128, pitch=18, noise=4.0, pattern="lines")


@pytest.fixture
def cross_window(qapp, lines_lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lines_lot["klarf"], sync=True)
    nid = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.model.set_param(nid, "roi_out", "xing")
    win.model.set_param(nid, "place", "beside_vertical")
    win.select_node(nid)
    yield win
    win.close()


def _view_with(labels, focus=-1):
    from d4t.ui.widgets import ImageView

    v = ImageView()
    v.set_image(np.full((32, 32), 128, np.uint8))
    boxes = [(0.1 * i, 0.1, 0.2, 0.2) for i in range(len(labels))]
    v.set_overlay(boxes, focus, labels)
    return v


def test_every_box_is_drawn_not_just_the_first(qapp, cross_window):
    """畫面上出現一個框、實際上量了八個 —— 這種落差沒有任何提示。"""
    win = cross_window
    results = rc_mod.check_regions(win.model.to_recipe(), win._items()[:6],
                                   win.model.kind, win.selected_node,
                                   ["xing"], 120, "ref")
    drawn = [r for r in results if r["located"] and r["boxes"]]
    assert drawn, "這批應該定位得出來"
    for r in drawn:
        assert len(r["boxes"]) > 4, (
            "只畫了 %d 個框 —— 多框區域被畫成一個了" % len(r["boxes"]))


def test_the_boxes_show_up_on_the_preview_without_opening_another_window(
        qapp, cross_window):
    """使用者原話：「不然都一定按 Check this region across defects… 跑完才能看，
    不能實時調整」。

    定位卡的參數是**一邊拖一邊看**決定的（F7-8）。框只出現在另一個要按鈕、
    要跑完一批的視窗裡，等於把「調敏感度」變成改一次跑一次 —— 而那要試十幾次。
    """
    win = cross_window
    win.refresh_preview(sync=True)

    n = win.image_view.overlay_count()
    assert n > 4, "預覽影像上沒有框（只有 %d 個）" % n
    assert len(win.region_overlay()) == n


def test_the_overlay_follows_the_parameters_live(qapp, cross_window):
    """改一個參數，框當場就要不一樣 —— 這是「即時」的定義。"""
    win = cross_window
    nid = win.selected_node
    win.refresh_preview(sync=True)
    before = list(win.region_overlay())

    win.model.set_param(nid, "place", "between_vertical")
    win.refresh_preview(sync=True)
    after = list(win.region_overlay())

    assert before and after
    assert before != after, "換了放法，畫面上的框卻沒變"


def test_the_box_the_defect_sits_in_is_marked_out(qapp, cross_window):
    """一堆一模一樣的框裡看不出哪個是「這一顆」的。缺陷永遠在 patch 正中心，
    所以離中心最近的那個要畫得不一樣。"""
    win = cross_window
    win.refresh_preview(sync=True)
    boxes = win.region_overlay()
    focus = win._focus_box_index(boxes)

    assert 0 <= focus < len(boxes)
    nx, ny, nw, nh = boxes[focus]
    d = (nx + nw / 2.0 - 0.5) ** 2 + (ny + nh / 2.0 - 0.5) ** 2
    assert all(d <= (b[0] + b[2] / 2.0 - 0.5) ** 2
               + (b[1] + b[3] / 2.0 - 0.5) ** 2 + 1e-9 for b in boxes)
    assert win.image_view._overlay_focus == focus


def test_only_the_selected_card_draws_its_boxes(qapp, cross_window):
    """一份 recipe 常有好幾張 ROI 卡，全部畫出來會變成一團分不清誰是誰的線。
    使用者現在在調的就是手上那一張。"""
    win = cross_window
    first = win.selected_node
    win.refresh_preview(sync=True)
    mine = list(win.region_overlay())
    assert len(mine) > 4

    other = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.model.set_param(other, "roi_out", "second")
    win.model.set_param(other, "place", "crossing")
    win.select_node(other)
    win.refresh_preview(sync=True)
    theirs = list(win.region_overlay())

    assert theirs, "選著第二張卡，畫的該是它自己的框"
    assert theirs != mine, "兩張卡的框應該不一樣（放法不同）"

    win.select_node(first)
    win.refresh_preview(sync=True)
    assert win.region_overlay() == mine, "切回第一張，畫的要是第一張的框"


def test_each_region_gets_its_own_colour(qapp):
    from d4t.ui.theme import REGION_COLORS

    v = _view_with(["epi", "mg", "epi", "poly"])
    legend = v.overlay_legend()
    assert [n for n, _c in legend] == ["epi", "mg", "poly"], "順序照第一次出現"
    assert [c for _n, c in legend] == list(REGION_COLORS[:3])
    assert len({c for _n, c in legend}) == 3


def test_the_colours_are_the_ones_the_template_editor_uses(qapp):
    """使用者在對話框裡認得的綠色 ROI1，到了 patch 上不能變成別的顏色。"""
    from d4t.ui.cell_canvas import region_color
    from d4t.ui.theme import region_hex

    for i in range(4):
        assert region_color(i).name().lower() == region_hex(i).lower()


def test_labels_that_do_not_line_up_switch_colouring_off(qapp):
    """錯位的顏色比沒有顏色糟得多 —— 它會**指錯**區域，而畫面上不會說。"""
    from d4t.ui.widgets import ImageView

    v = ImageView()
    v.set_image(np.full((32, 32), 128, np.uint8))
    v.set_overlay([(0.1, 0.1, 0.2, 0.2), (0.5, 0.1, 0.2, 0.2)], -1, ["epi"])
    assert v.overlay_legend() == []
    assert v.overlay_count() == 2


def test_one_region_gets_no_legend(qapp):
    """只有一個區域的時候那個顏色沒有在跟誰對比，一行字只是擋住影像。"""
    assert _view_with(["epi", "epi", "epi"]).legend_visible() is False
    assert _view_with(["epi", "mg"]).legend_visible() is True
    assert _view_with(["epi", "epi"]).overlay_legend() == [("epi", "#5fd0a0")]


def test_the_names_line_up_with_the_boxes_in_the_studio(qapp, cross_window):
    """框與名字走**同一個清單**（`_overlay_region_names`）。兩份各自算的話，
    區域一多顏色就會指到隔壁那個 —— 而畫面上沒有任何東西透露這件事。"""
    win = cross_window
    nid = win.selected_node
    win.refresh_preview(sync=True)

    boxes = win.region_overlay()
    names = win.region_overlay_names()
    assert boxes and len(names) == len(boxes)
    assert set(names) <= set(win._overlay_region_names(win.model.nodes[nid]))
    assert win.image_view.overlay_count() == len(boxes)


def test_a_card_with_two_regions_shows_two_colours_on_the_patch(qapp):
    """這是使用者回報的那個畫面：兩個區域，以前兩個都是藍的。"""
    v = _view_with(["epi", "mg"])
    assert len(v.overlay_legend()) == 2
    assert v.overlay_legend()[0][1] != v.overlay_legend()[1][1]
