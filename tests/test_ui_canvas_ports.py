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
