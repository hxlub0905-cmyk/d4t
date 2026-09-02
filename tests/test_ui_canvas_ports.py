# PR-2（2b）：菱形埠的 hover 一句話（view 層的 `_port_tip_at`）。
"""node 故意不收 hover（收了會殺掉邊的 × 鈕，`test_ui_canvas_cut_button`
守著），所以一句話掛在 view 的 mouse-move 上。這裡打純函式 `_port_tip_at`
—— 不擠 QToolTip，斷言的是「哪顆埠拿到哪一句」。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.ui import region_words, studio as studio_mod, theme as theme_mod  # noqa: E402

sys.path.insert(0, str(REPO / "tests"))
from conftest import first_source, wire_up  # noqa: E402
from region_cards import add_region_step  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def test_each_region_out_port_gets_its_own_sentence(window):
    src = first_source(window)
    nid = add_region_step(window.model, "roi_cross")
    window.model.set_param(nid, "roi_out", "cells")
    wire_up(window.model, nid)
    window._refresh_pipeline()
    canvas = window.pipeline
    item = canvas.node_item(nid)
    assert item is not None

    got = {}
    specs = item.out_specs()
    anchors = item.out_anchors_local()
    for spec, local in zip(specs, anchors):
        view_pos = canvas.mapFromScene(item.mapToScene(local))
        got[spec["name"]] = canvas._port_tip_at(view_pos)

    for name in ("cells", "cells_center", "cells_others"):
        assert name in got, (name, sorted(got))
        want = region_words.PORT_HOVER[region_words.role_of(name)]
        assert got[name] == "%s — %s" % (name, want)


def test_image_ports_stay_silent(window):
    src = first_source(window)
    window._refresh_pipeline()
    canvas = window.pipeline
    item = canvas.node_item(src)
    specs = item.out_specs()
    anchors = item.out_anchors_local()
    image_tips = [canvas._port_tip_at(canvas.mapFromScene(item.mapToScene(a)))
                  for s, a in zip(specs, anchors) if s["kind"] == "image"]
    assert image_tips and all(t == "" for t in image_tips), \
        "影像埠沒有這一句 —— 一句到處出現的話等於沒有說"


def test_empty_canvas_space_has_no_tip(window):
    from PySide6.QtCore import QPoint

    assert window.pipeline._port_tip_at(QPoint(-50, -50)) == ""


# --------------------------------------------------------------------------- #
# F68：兩顆同型別的埠要分得出來，而且不准安靜接錯
# --------------------------------------------------------------------------- #
def test_neighbouring_ports_are_far_enough_apart_to_aim_at(window):
    """**這是「拖歪了安靜接到隔壁」的病根**（F68 量出來的）。

    GLV 有四顆輸入埠，其中兩顆是長得一樣的菱形。以前相鄰兩顆相距 **12.8px**，
    而埠畫出來就有 11px 寬 —— 瞄準的餘裕只剩一個像素多，而 `in_param_at`
    是就近吸附：落在隔壁那一顆上時**兩顆都是合法的區域參數**，
    `_connect_region` 攔不到，於是那條線安靜地接錯。
    """
    from d4t.ui import canvas as canvas_mod

    src = first_source(window)
    glv = window.add_card_after(src, "glv_stats")
    window._on_edge_added(src, glv, "test", "source")
    window._refresh_pipeline()
    item = window.pipeline.node_item(glv)
    ys = [a.y() for a in item.in_anchors_local()]
    assert len(ys) >= 4, "GLV 有四顆輸入埠（兩圓兩菱形）"
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert min(gaps) >= canvas_mod._PORT_MIN_GAP, (
        "相鄰兩顆埠只距離 %.1f（下限 %.1f）—— 瞄不準，而接錯了畫面上看不出來"
        % (min(gaps), canvas_mod._PORT_MIN_GAP))

    # 而且**瞄準真的落在該落的那一顆上**：對準每顆埠打一次
    names = [str(sp.get("name")) for sp in item.in_specs()]
    for name, anchor in zip(names, item.in_anchors()):
        assert item.in_param_at(anchor) == name


def test_the_reference_ports_are_drawn_differently(window):
    """兩顆菱形在這之前是**逐位元組相同**的。"""
    src = first_source(window)
    glv = window.add_card_after(src, "glv_stats")
    window._on_edge_added(src, glv, "test", "source")
    window._refresh_pipeline()
    specs = {str(sp.get("name")): sp
             for sp in window.pipeline.node_item(glv).in_specs()}
    assert specs["roi"]["role"] == "measure"
    assert specs["reference_region"]["role"] == "reference"
    assert specs["source"]["role"] == "measure"
    assert specs["reference_source"]["role"] == "reference"


def test_the_label_keeps_saying_which_port_it_is_after_it_is_wired(window):
    """接上線之後角色的字**不可以消失** —— 那正是最需要它的時候（F68）。"""
    from d4t.ui import canvas as canvas_mod

    src = first_source(window)
    roi = add_region_step(window.model, "roi_cross")
    window.model.set_param(roi, "roi_out", "cells")
    wire_up(window.model, roi)
    glv = window.add_card_after(roi, "glv_stats")
    window._on_edge_added(src, glv, "test", "source")
    window._on_edge_added(roi, glv, "cells", "roi")
    window._on_edge_added(roi, glv, "cells_others", "reference_region")
    window._refresh_pipeline()

    specs = {str(sp.get("name")): sp
             for sp in window.pipeline.node_item(glv).in_specs()}
    assert specs["roi"]["stream"] == "cells"
    assert specs["reference_region"]["stream"] == "cells_others"
    # 畫出來的字：量的那一顆是區域名，參照那一顆前面掛著角色
    assert canvas_mod._port_label_text(specs["roi"]) == "cells"
    assert canvas_mod._port_label_text(specs["reference_region"]) \
        == "ref cells_others"


def test_dragging_a_line_lights_up_the_ports_it_can_land_on(window):
    """拖的當下就看得到要接到哪一顆 —— 而且**只有型別對得上的會亮**。"""
    src = first_source(window)
    roi = add_region_step(window.model, "roi_cross")
    window.model.set_param(roi, "roi_out", "cells")
    wire_up(window.model, roi)
    glv = window.add_card_after(roi, "glv_stats")
    window._on_edge_added(src, glv, "test", "source")
    window._refresh_pipeline()

    target = window.pipeline.node_item(glv)
    assert target._ports_to_light() == set(), "沒在拖的時候一顆都不亮"

    roi_item = window.pipeline.node_item(roi)
    region_port = [i for i, k in enumerate(roi_item.out_kinds())
                   if k == "region"][0]
    window.pipeline.begin_link(roi_item, region_port)
    assert target._ports_to_light() == {"roi", "reference_region"}, \
        "拖區域線 → 只有兩顆菱形亮"

    image_port = [i for i, k in enumerate(roi_item.out_kinds())
                  if k == "image"][0]
    window.pipeline.begin_link(roi_item, image_port)
    assert target._ports_to_light() == {"source", "reference_source"}, \
        "拖影像線 → 只有兩顆圓埠亮"
