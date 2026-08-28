# PR-3：三次點擊的回溯（why_panel + 訊號鏈 + 區域點亮）。
"""點 score/bin/class → 面板重放這一顆的判定 → 點一項跳到產出它的卡，
有區域的項把那一塊亮在影像上。鎖**不變量**（資料同源、訊號到得了、狀態
不互相打架），不凍版面。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from tests.region_cards import add_region_step  # noqa: E402

from conftest import first_source, wire_up  # noqa: E402

from d4t.core.pipeline.recipe import DecideSpec, Let, Rule  # noqa: E402
from d4t.core.pipeline.verdict_trace import verdict_trace  # noqa: E402
from d4t.ui import studio as studio_mod  # noqa: E402
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.why_panel import why_rows  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("whylot")), n=8, seed=13)


@pytest.fixture(scope="module")
def window(qapp, lot):
    """load → Region 卡（epi）→ GLV，判定樹問 glv_max 與 epi_present。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    roi = wire_up(win.model, add_region_step(win.model, "roi_cross"))
    win.model.set_param(roi, "roi_out", "epi")
    win._on_add_requested("glv_stats")
    glv = next(n for n in win.model.node_order
               if win.model.nodes[n].step == "glv_stats")
    wire_up(win.model, glv)
    win.model.set_param(glv, "metrics", "glv_max")
    win.model.set_expr("")          # decide 與 score 互斥（ambiguous-decision）
    win.model.decide = DecideSpec(
        let=[Let(name="bright", expr="glv_max")],
        rules=[Rule(when="bright > 222.5", bin=1, label="hot"),
               Rule(when="epi_present > 0", bin=2, label="located")],
        otherwise_bin=0, otherwise_label="rest", score="bright")
    assert win.run_trial(8, workers=1, sync=True) is True
    win._roi_node, win._glv_node = roi, glv
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# why_rows：純函式
# --------------------------------------------------------------------------- #
def test_why_rows_is_a_pure_function(window):
    row = next(r for r in window.trial_results if r["ok"])
    trace = verdict_trace(window.model.to_recipe(), window.model.kind,
                          row["features"])
    rows = why_rows(trace)
    kinds = [r["kind"] for r in rows]
    assert kinds[0] == "head" and "let" in kinds and "step" in kinds \
        and "leaf" in kinds
    heads = [r["text"] for r in rows if r["kind"] == "head"]
    assert heads[0] == "Working numbers"
    let = next(r for r in rows if r["kind"] == "let")
    assert let["name"] == "bright" and "= " in let["text"]
    leaf = next(r for r in rows if r["kind"] == "leaf")
    assert leaf["bin"] == row["bin"], "面板的葉列就是引擎判的那一格（反空洞）"
    # 步列帶「要跳去哪」的名字（那一題最先問到的數字）
    steps = [r for r in rows if r["kind"] == "step"]
    assert steps[0]["name"] == "bright"


def test_why_rows_of_nothing_is_nothing():
    assert why_rows(None) == []


# --------------------------------------------------------------------------- #
# 訊號鏈：點 score 格 → 面板開、內容是那一列
# --------------------------------------------------------------------------- #
def _click_cell(window, did, column):
    pane = window.results.table
    m = pane.table._model
    row = m.row_of(did)
    assert row >= 0
    idx = m.index(row, m.columns().index(column))
    pane.table._on_click(idx)


def test_clicking_the_score_cell_opens_the_panel_with_that_verdict(window):
    window.results.hide_why()
    rows = [r for r in window.trial_results if r["ok"]]
    # 挑兩顆判進不同 bin 的 —— 面板真的跟著列換（反空洞）。
    by_bin = {}
    for r in rows:
        by_bin.setdefault(r["bin"], r)
    assert len(by_bin) > 1, "這一批要真的判出不只一類"
    for r in by_bin.values():
        _click_cell(window, r["defect_id"], "score")
        why = window.results.why
        assert why.isVisibleTo(window.results)
        assert why.defect_id() == str(r["defect_id"])
        leaf = next(x for x in why.rows() if x["kind"] == "leaf")
        assert leaf["bin"] == r["bin"]


def test_a_failed_row_does_not_open_the_panel(window):
    window.results.hide_why()
    bad = next((r for r in window.trial_results if not r["ok"]), None)
    if bad is None:
        pytest.skip("this batch had no failed defect")
    _click_cell(window, bad["defect_id"], "score")
    assert not window.results.why.isVisibleTo(window.results)


# --------------------------------------------------------------------------- #
# 點一項 → 產出卡；區域項 → 那一塊亮起來
# --------------------------------------------------------------------------- #
def test_clicking_an_item_selects_the_producing_card(window):
    did = window.trial_results[0]["defect_id"]
    window._on_why_item(did, "glv_max")
    assert window.selected_node == window._glv_node


def test_a_region_item_lights_that_region_on_the_image(window):
    did = window.trial_results[0]["defect_id"]
    window._on_why_item(did, "epi_present")
    assert window.selected_node == window._roi_node
    assert window.image_view.overlay_emphasis() == ["epi"]
    assert "epi" in window.region_overlay_names(), \
        "亮的那一塊要真的在畫著的框裡（不是空亮）"


def test_the_emphasis_is_cleared_when_the_overlay_changes(window):
    view = window.image_view
    view.set_overlay_emphasis(["epi"])
    assert view.overlay_emphasis() == ["epi"]
    view.set_overlay([(0.1, 0.1, 0.2, 0.2)], -1, ["mg"])
    assert view.overlay_emphasis() == [], \
        "換一組框之後舊的強調可能指著別張卡的區域 —— 要清掉"


def test_an_engine_item_opens_the_decision_editor(window):
    did = window.trial_results[0]["defect_id"]
    window._on_why_item(did, "bright")
    assert window.stack.currentWidget() is window.tree_pane


# --------------------------------------------------------------------------- #
# Esc 關面板、不擋列選取
# --------------------------------------------------------------------------- #
def test_escape_closes_the_panel_and_selection_survives(window):
    rows = [r for r in window.trial_results if r["ok"]]
    did = rows[0]["defect_id"]
    _click_cell(window, did, "score")
    why = window.results.why
    assert why.isVisibleTo(window.results)
    pane = window.results.table
    pane.select_defect(did)
    before = pane.selected_ids()
    QTest.keyClick(why, Qt.Key_Escape)
    assert not why.isVisibleTo(window.results)
    assert pane.selected_ids() == before, "關面板不動列選取"
    other = rows[1]["defect_id"]
    assert pane.select_defect(other) is True, "面板關了還能選別列"
    assert pane.selected_ids() == [other]
