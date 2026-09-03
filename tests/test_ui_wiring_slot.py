# F68：設定區那一格「接線插槽」（2026-09-01）。
"""鎖三件事：

1. **沒接線不是空白** —— 三種空狀態各講一件不同的事（跑不起來／量整張圖／不比）。
2. **插槽自己一個字都不改** —— 它只發訊號，動線的是 Studio。
3. **從插槽挑一個，跟在畫布上拉那條線，存出來的 recipe 逐位元組相同** ——
   那是「沒有走後門」的可執行證明（照 F44 preset 那支測試的形狀）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

from conftest import first_source                   # noqa: E402
from d4t.ui import studio as studio_mod             # noqa: E402
from d4t.ui import theme as theme_mod               # noqa: E402
from d4t.ui.wiring_slot import (                    # noqa: E402
    IMAGE, REGION, WiringSlot, slot_words,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    return app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 空狀態講的是後果，不是空白
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("kind", "ref", "required", "says"), [
    (IMAGE, False, True, "not connected"),      # 這張卡跑不起來
    (REGION, False, False, "the whole image"),  # 合法，而且是預設行為
    (REGION, True, False, "no reference"),      # 合法：只報絕對值
    (IMAGE, True, False, "no reference"),
])
def test_an_empty_slot_says_what_happens(kind, ref, required, says):
    main, note, bad = slot_words(kind, "", is_reference=ref, required=required)
    assert main == says
    assert bad is (kind == IMAGE and required), "只有跑不起來的那一種是紅字"
    assert note or not required


def test_a_wired_region_slot_says_which_role_it_is():
    """角色那句話跟畫布上那顆埠的 hover **同一份字典**（F44 的 region_words）。"""
    from d4t.ui.region_words import PORT_HOVER, ROLE_CENTER

    main, note, _bad = slot_words(REGION, "epi_center",
                                  is_reference=False, required=False)
    assert main == "epi_center"
    assert note == PORT_HOVER[ROLE_CENTER]


def test_two_regions_say_they_are_measured_one_by_one():
    main, note, _ = slot_words(REGION, "epi,mg",
                               is_reference=False, required=False)
    assert main == "epi, mg" and "one by one" in note


# --------------------------------------------------------------------------- #
# 2. 插槽不改東西，它只發訊號
# --------------------------------------------------------------------------- #
def test_the_slot_changes_nothing_by_itself(qapp):
    slot = WiringSlot(REGION, "epi")
    slot.set_choices(["epi", "mg"])
    seen = []
    slot.wire_requested.connect(seen.append)
    slot.wire_requested.emit("mg")
    assert seen == ["mg"]
    assert slot.text_value() == "epi", "值要等線真的改了才會變"


# --------------------------------------------------------------------------- #
# 3. 插槽挑一個 == 在畫布上拉那條線（逐位元組）
# --------------------------------------------------------------------------- #
def _gds_card(window):
    """`load_single → roi_reference(GDS) → glv_stats`，只接了必要的影像線。"""
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi, 2:mg")
    window._on_edge_added(src, glv, "single", "source")
    return gds, glv


def _snapshot(window):
    return json.dumps(window.model.to_recipe().to_json_dict(),
                      sort_keys=True, ensure_ascii=False, indent=1)


def test_picking_in_the_slot_is_the_same_as_dragging_the_line(window):
    """**沒有走後門的可執行證明**：兩條路存出來的 recipe 逐位元組相同。"""
    gds, glv = _gds_card(window)

    window.select_node(glv)
    window.param_form.wire_requested.emit("roi", "epi")
    by_slot = _snapshot(window)

    window.model.remove_edge(gds, glv, "epi", "roi")
    window._on_edge_added(gds, glv, "epi", "roi")
    by_drag = _snapshot(window)

    assert by_slot == by_drag
    assert window.model.nodes[glv].params["roi"] == "epi"


def test_the_slot_menu_only_offers_what_upstream_really_produces(window):
    """列一個排在自己後面才算出來的東西，選下去就是一份跑不動的 recipe。"""
    _gds, glv = _gds_card(window)
    window.select_node(glv)

    slots = {n: r.editor for n, r in window.param_form._rows.items()
             if isinstance(r.editor, WiringSlot)}
    assert set(slots) >= {"source", "roi", "reference_region",
                          "reference_source"}
    assert "epi" in slots["roi"]._choices
    assert "epi_center" in slots["roi"]._choices, "家族的三個名字都要在"
    assert "single" in slots["source"]._choices
    assert "epi" not in slots["source"]._choices, "區域不可以出現在影像那一格"


# --------------------------------------------------------------------------- #
# 4. 「Show it on the canvas」真的指得出來（2026-09-03）
# --------------------------------------------------------------------------- #
# 使用者回報：按下去畫面上什麼都沒發生，終端機一串
# `AttributeError: 'StudioWindow' object has no attribute 'canvas'`。
# 選單這一列從來沒有被測過 —— 兩個名字都錯（畫布叫 `pipeline`，而
# `show_card_ghosts` 吃的是圖元不是 id），所以它一次都沒有成功過。
def test_show_it_on_the_canvas_points_at_the_card_that_feeds_the_slot(window):
    gds, glv = _gds_card(window)
    window.select_node(glv)
    window.param_form.wire_requested.emit("roi", "epi")

    window.param_form.wire_show_requested.emit("roi")

    lit = window.pipeline.card(gds)
    assert lit is not None and lit._hover, "指的是定義那個區域的那張卡"
    assert window.pipeline.card(glv)._hover is False, "不是使用者正在編的這張"
    assert window.selected_node == glv, "指給我看不等於換一張卡編"


def test_showing_an_image_slot_points_at_the_card_that_produces_the_stream(window):
    _gds, glv = _gds_card(window)
    src = first_source(window, "load_single")
    window.select_node(glv)

    window.param_form.wire_show_requested.emit("source")

    assert window.pipeline.card(src)._hover, "影像流走的是同一條路"


def test_showing_an_unwired_slot_does_nothing_instead_of_raising(window):
    _gds, glv = _gds_card(window)
    window.select_node(glv)
    window.param_form.wire_show_requested.emit("reference_region")
    assert not window.pipeline.ghost_items()


def test_the_light_goes_out_by_itself_when_the_mouse_touches_the_canvas(window):
    """亮著的卡是**幽靈**（`_ghost_cards`）—— 使用者一動就清掉，不會留一張
    永遠亮著的卡在畫布上。"""
    gds, glv = _gds_card(window)
    window.select_node(glv)
    window.param_form.wire_requested.emit("roi", "epi")
    window.param_form.wire_show_requested.emit("roi")
    assert window.pipeline.card(gds)._hover

    window.pipeline.clear_tree_ghosts()          # `_sync_hover_node` 做的第一件事
    assert window.pipeline.card(gds)._hover is False
