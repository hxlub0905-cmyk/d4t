# F123 期 2：數字線與結果線在畫布上（2026-09-29）。
"""畫布那一半：方埠、拉得出來、接錯講得出為什麼、剪一條就是一條、
「插入數字 ▾」只列接進 Decision 的卡。

core 那一半（lint、Output 寫上游、遷移）在 `tests/test_data_lines.py`。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.ui import card_menu, canvas_edges  # noqa: E402
from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402

RECIPE = REPO / "recipes" / "ebi-die-to-die.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    assert win.load_recipe_path(str(RECIPE), sync=True)
    try:
        yield win
    finally:
        win.close()


def _data_edges(win):
    return [(e.src, e.dst, e.src_out, e.dst_in) for e in win.model.edges
            if e.src_out in ("numbers", "results")]


# --------------------------------------------------------------------------- #
# 埠
# --------------------------------------------------------------------------- #
def test_the_cards_grow_the_data_ports(window):
    view = window.pipeline
    glv, dec, rep = (view.card(n) for n in ("glv", "decision", "report"))
    assert {"name": "numbers", "kind": "numbers"} in glv.out_specs()
    assert {"name": "results", "kind": "results"} in dec.out_specs()
    assert [s["kind"] for s in dec.in_specs()] == ["numbers"]
    assert [s["kind"] for s in rep.in_specs()] == ["results"]
    # 一張不寫數字的卡（Compare）沒有數字埠。
    assert "numbers" not in [s["kind"] for s in view.card("sub").out_specs()]


def test_the_lines_land_on_their_own_ports(window):
    kinds = {(e.src.node_id, e.dst.node_id): e.kind()
             for e in window.pipeline._edges}
    assert kinds[("glv", "decision")] == "numbers"
    assert kinds[("decision", "report")] == "results"


def test_the_decision_card_says_what_flows_through_it(window):
    assert window.pipeline.card("decision").subtitle() == "numbers → results"


def test_a_numbers_line_dropped_on_a_card_lands_on_the_data_port(window):
    """落點取最近的那一顆的話，一張有影像埠也有資料埠的卡會把數字線丟進影像埠。"""
    from PySide6.QtCore import QPointF
    rep = window.pipeline.card("report")
    assert rep.in_param_at(QPointF(0, 0), "numbers") == "results"


# --------------------------------------------------------------------------- #
# 拉線
# --------------------------------------------------------------------------- #
def test_numbers_into_the_decision_is_one_more_line(window):
    before = _data_edges(window)
    canvas_edges.connect(window, "dn", "decision", "numbers", "numbers")
    assert ("dn", "decision", "numbers", "numbers") in _data_edges(window)
    assert set(before) <= set(_data_edges(window)), "資料埠接很多條，不擠掉舊的"
    assert "Connected" in window.status_text()


def test_numbers_straight_into_an_output_is_allowed(window):
    canvas_edges.connect(window, "glv", "report", "numbers", "results")
    assert ("glv", "report", "numbers", "results") in _data_edges(window)


def test_the_wrong_lines_are_refused_with_a_reason(window):
    n = len(window.model.edges)
    canvas_edges.connect(window, "load", "decision", "test", "numbers")
    assert "image or a region" in window.status_text()
    canvas_edges.connect(window, "glv", "sub", "numbers", "a")
    assert "Decision or an Output" in window.status_text()
    assert len(window.model.edges) == n, "擋下來的線不准留下任何痕跡"


def test_cutting_a_data_line_cuts_that_one_line(window):
    params = {n: dict(window.model.nodes[n].params)
              for n in window.model.nodes}
    canvas_edges.on_edge_removed(window, "glv", "decision", "numbers",
                                 "numbers")
    assert ("glv", "decision", "numbers", "numbers") not in _data_edges(window)
    assert ("decision", "report", "results", "results") in _data_edges(window)
    assert params == {n: dict(window.model.nodes[n].params)
                      for n in window.model.nodes}, "剪資料線不動任何參數"


def test_removing_the_decision_offers_no_bridge(window, monkeypatch):
    """資料線不「穿過」一張卡：刪掉 Decision 不該提議把 GLV 直接接到報表。"""
    assert window.model.bridge_plan("decision") == []


def test_the_card_menu_lists_where_a_data_line_can_go():
    keys = ["glv_stats", "decision", "output_report", "output_klarf"]
    assert card_menu.compatible(keys, "numbers") == [
        "decision", "output_report", "output_klarf"]
    assert card_menu.compatible(keys, "results") == [
        "output_report", "output_klarf"]
    assert card_menu.input_param_for("decision", "numbers") == "numbers"
    assert card_menu.input_param_for("output_report", "numbers") == "results"


# --------------------------------------------------------------------------- #
# 判定只問得到接進來的卡
# --------------------------------------------------------------------------- #
def test_the_number_picker_lists_only_the_wired_cards(window):
    names = [x.split("\t")[0] for x in window.model.decision_numbers()]
    assert "glv_max" in names
    assert "n_channels" not in names, "Input 沒接進 Decision"
    canvas_edges.connect(window, "load", "decision", "numbers", "numbers")
    names = [x.split("\t")[0] for x in window.model.decision_numbers()]
    assert "n_channels" in names


def test_cutting_the_numbers_line_puts_a_badge_on_the_decision(window):
    canvas_edges.on_edge_removed(window, "glv", "decision", "numbers",
                                 "numbers")
    window._refresh_pipeline()
    card = window.pipeline.card("decision")
    assert "wired" in card.problem(), card.problem()


def test_a_new_output_card_says_it_has_nothing_to_write(window):
    nid = window.model.add_step("output_report")
    window._refresh_pipeline()
    assert "results port" in window.pipeline.card(nid).problem()


# --------------------------------------------------------------------------- #
# F123 期 3：Output 自己的輸入
# --------------------------------------------------------------------------- #
def test_write_comparison_grows_two_picture_ports(window):
    nid = window.model.add_step("output_char")
    window._refresh_pipeline()
    specs = window.pipeline.card(nid).in_specs()
    assert [(s["label"], s["kind"]) for s in specs] == [
        ("Left picture", "image"), ("Right picture", "image"),
        ("results", "results")]


def test_an_output_cards_number_list_is_what_is_upstream_of_it(window):
    names = [x.split("\t")[0] for x in window.model.labelled_features(
        upto_node="report", include_upto=False)]
    assert "glv_max" in names                   # GLV → Decision → 報表
    canvas_edges.on_edge_removed(window, "glv", "decision", "numbers",
                                 "numbers")
    names = [x.split("\t")[0] for x in window.model.labelled_features(
        upto_node="report", include_upto=False)]
    assert "glv_max" not in names, "GLV 不在報表上游了，清單不該再列它"
