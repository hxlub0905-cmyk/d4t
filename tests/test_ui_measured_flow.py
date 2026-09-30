# F124 期 2：畫布的樣子（2026-09-30）。
"""畫布上看得到的那一半（core 那一半在 `tests/test_data_lines.py`）：

1. 資料埠寫畫面上的字 —— ``measured`` / ``classified``；recipe 的鍵不動。
2. 原樣送出、沒有線接出去的輸出埠**畫小、畫淡**（`info["quiet_out"]`）。
3. 埠名放得下：欄距 156（使用者選的 A）、兩邊各 74、小一號字。
4. 問題清單上「Connect ＿」那顆鈕：走跟手拉的線同一條路、一步復原。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtGui import QFont, QFontMetricsF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.ui import canvas as canvas_mod, canvas_edges, wording  # noqa: E402
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


# --------------------------------------------------------------------------- #
# 1. 畫面上的字
# --------------------------------------------------------------------------- #
def test_the_data_ports_say_what_stage_the_data_is_at():
    assert wording.port_word("numbers") == "measured"
    assert wording.port_word("results") == "classified"
    assert wording.port_word("diff") == "diff", "影像流、區域名原樣"


def test_the_ports_keep_their_recipe_keys_and_show_the_words(window):
    dec = window.pipeline.card("decision")
    assert [(s["name"], s["label"]) for s in dec.in_specs()] == [
        ("numbers", "measured")]
    assert window.pipeline.card("report").subtitle() == "report · classified"
    assert ["glv", "numbers", "decision", "numbers"] in [
        e.to_json() for e in window.model.to_recipe().edges], "recipe 的鍵不動"


def test_a_refused_line_speaks_the_screen_words(window):
    canvas_edges.connect(window, "dn", "decision", "numbers", "numbers")
    text = window.status_text()
    assert "measured" in text and "numbers port" not in text, text


# --------------------------------------------------------------------------- #
# 2. 原樣送出、沒接線的埠畫小畫淡
# --------------------------------------------------------------------------- #
def test_passed_through_ports_without_a_line_are_quiet(window):
    quiet = {n: set(window.pipeline.card(n).info.get("quiet_out") or ())
             for n in ("sub", "glv", "norm_ref", "load")}
    assert quiet["sub"] == {"test", "ref"}, "Compare 真的產出的是 diff"
    assert quiet["glv"] == {"diff"}
    assert quiet["norm_ref"] == {"test"}, "ref 是它處理過的；test 只是借來的"
    assert quiet["load"] == set(), "Input 產出的每一條都不是原樣送出"


def test_a_passed_through_port_with_a_line_is_not_quiet(window):
    canvas_edges.connect(window, "sub", "dn", "test", "streams")
    window._refresh_pipeline()
    assert "test" not in (window.pipeline.card("sub").info.get("quiet_out") or ())


# --------------------------------------------------------------------------- #
# 3. 埠名放得下
# --------------------------------------------------------------------------- #
def test_the_two_labels_in_a_column_gap_never_meet():
    w = canvas_mod._PORT_LABEL_W
    assert 4 + w <= canvas_mod.COL_GAP - 4 - w, "右邊那塊與下一張卡左邊那塊相疊"
    assert (canvas_mod.NODE_W + canvas_mod.COL_GAP) % canvas_mod.GRID == 0


@pytest.mark.parametrize("text", ["Ref image", "Ref region", "Left picture",
                                  "Right picture", "Search inside",
                                  "Small image", "measured", "classified"])
def test_the_port_names_that_used_to_be_cut_now_fit(qapp, text):
    """F124 之前這幾個一律被切成 `Re…ge` 那種讀不出來的字。"""
    f = QFont(qapp.font())
    f.setPixelSize(theme_mod.font_px("font_tiny"))
    assert QFontMetricsF(f).horizontalAdvance(text) <= canvas_mod._PORT_LABEL_W


# --------------------------------------------------------------------------- #
# 4. 「Connect ＿」
# --------------------------------------------------------------------------- #
def _cut_glv(window):
    canvas_edges.on_edge_removed(window, "glv", "decision", "numbers", "numbers")
    window._refresh_all()


def test_the_problem_list_offers_to_connect_the_card(window):
    _cut_glv(window)
    rows = [r for r in window.problems.rows() if r["code"] == "decision-not-wired"]
    assert rows and rows[0]["connect"] == ["glv"]
    assert rows[0]["connect_text"] == "Connect “GLV”"
    assert [b.text() for b in window.problems.connect_buttons()] == [
        "Connect “GLV”"]


def test_the_button_draws_the_line_like_a_hand_would(window):
    _cut_glv(window)
    window.problems.connect_buttons()[0].click()
    edges = [e.to_json() for e in window.model.to_recipe().edges]
    assert ["glv", "numbers", "decision", "numbers"] in edges
    window._refresh_all()
    assert not [r for r in window.problems.rows()
                if r["code"] == "decision-not-wired"]
    window.model.undo()
    edges = [e.to_json() for e in window.model.to_recipe().edges]
    assert ["glv", "numbers", "decision", "numbers"] not in edges, "一步復原"


# --------------------------------------------------------------------------- #
# 5. 期 3：線不從卡背後穿過、「整理」照流排
# --------------------------------------------------------------------------- #
def _stroke_hits(view, edge):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainterPathStroker, QPen
    line = QPainterPathStroker(QPen(Qt.black, 2.0)).createStroke(edge.path())
    hits = []
    for nid, card in view._items.items():
        if nid in (edge.src.node_id, edge.dst.node_id):
            continue
        body = QRectF(card.scenePos().x(), card.scenePos().y(),
                      canvas_mod.NODE_W, card.height())
        if line.intersects(body):
            hits.append(nid)
    return hits


def test_a_line_does_not_run_behind_the_card_between_its_ends(qapp):
    """rsem-worst-box：Input → GLV 以前從 ROI · on_pattern 背後穿過去，看起來像
    是 ROI 吐出來的。⚠ 比的是描邊之後的外形（`QPainterPath.intersects` 看的是
    填滿的面積）。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.resize(2000, 1100)
        win.show()
        assert win.load_recipe_path(
            str(REPO / "recipes" / "rsem-worst-box.json"), sync=True)
        view = win.pipeline
        view.tidy()
        edge = next(e for e in view._edges if e.pair() == ("load", "glv"))
        on_pattern = next(n for n in view._items if "on_pattern" in n)
        assert view.card(on_pattern).scenePos().y() == \
            view.card("load").scenePos().y(), "前提：夾在同一列中間"
        assert _stroke_hits(view, edge) == []
    finally:
        win.close()


def test_a_card_with_no_inputs_is_a_start_not_the_next_step():
    """Pair source 沒有入口：以前被補一個「route 前一張」的依賴，排到 Input 右邊，
    讀起來像 Input 餵給它。"""
    from d4t.ui.layout import layout_columns
    order = ["load", "pair", "h2h", "decision", "cmp"]
    lines = [("load", "h2h"), ("pair", "h2h"), ("load", "cmp"), ("h2h", "cmp"),
             ("h2h", "decision"), ("decision", "cmp")]
    pos = layout_columns(order, lines, 4)
    assert pos["pair"][0] == pos["load"][0] == 0


def test_the_starts_are_not_chained_on_the_canvas(window):
    nid = window.model.add_step("pair_source")
    window._refresh_pipeline()
    assert (window.pipeline._order.index(nid) > 0
            and not [p for p in window.pipeline._implicit if p[1] == nid])


def test_an_output_left_alone_on_the_last_row_sits_under_its_source():
    """ebi-die-to-die 在三欄寬的畫布上：Write report 以前孤零零換到下一列的
    第 0 欄，那條線從最右邊繞回最左邊。"""
    from d4t.ui.layout import layout_columns
    order = ["load", "norm_ref", "norm", "sub", "dn", "glv", "decision", "report"]
    lines = [("load", "norm"), ("load", "norm_ref"), ("norm", "sub"),
             ("norm_ref", "sub"), ("sub", "dn"), ("dn", "glv"),
             ("glv", "decision"), ("decision", "report")]
    pos = layout_columns(order, lines, 3)
    col, row = pos["decision"]
    assert pos["report"] == (col, row + 1)


def test_a_last_row_that_still_flows_on_wraps_as_before():
    from d4t.ui.layout import layout_columns
    pos = layout_columns(["a", "b", "c", "d"], [("a", "b"), ("b", "c"),
                                                ("c", "d")], 2)
    assert pos == {"a": (0, 0), "b": (1, 0), "c": (0, 1), "d": (1, 1)}


def test_two_routed_lines_into_one_card_keep_their_own_lanes():
    from d4t.ui import edge_route
    lanes = [edge_route.lane(80.0, i) for i in range(3)]
    assert len(set(lanes)) == 3 and lanes == sorted(lanes), \
        "越下面的埠離卡越遠：它的垂直那段才不切過上面那幾顆埠"
    assert canvas_mod._EdgeItem.SIDE > canvas_mod._PORT_LABEL_W, \
        "繞行的垂直那段落在埠名外面"
