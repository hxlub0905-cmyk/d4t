# PR-1：結果表分層 + 診斷徽章（2026-08-27）。
"""五六十欄平鋪找不到重點 → 判定層預設可見、其餘摺疊、診斷欄離開表格。

這一份鎖的是**不變量**（集合、字樣、資料同源），不凍版面：

* 預設可見集合 = 徽章 + base + class + 判定引用的特徵（含被判定引用的診斷
  —— 使用者 2026-08-27 定調「判定引用 > 診斷隱藏」）；
* 展開後全可見、收回還原；搜尋命中會現身、清空還原、無命中不加欄；
* 沒被引用的診斷欄**兩層都不出現**，但資料還在（匯出照舊 —— 匯出不走這個
  模組，`feature_keys` 仍然看得到它）；
* 警示只來自卡宣告的布林與 ``error`` —— 數值再大 UI 也不亮（不發明門檻）；
* 徽章明細（名字、值、來自哪張卡）由該列的 ``traces`` 歸戶 —— 引擎真相，
  不是 UI 猜的。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from d4t.core.export.report import BASE_COLUMNS, feature_keys  # noqa: E402
from d4t.core.pipeline.step import FeatureSpec  # noqa: E402
from d4t.core.pipeline.verdict_features import BoundSpec  # noqa: E402
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.results_table import (  # noqa: E402
    BADGE_COLUMN, CLASS_COLUMN, ResultsTablePane, column_tree, header_spans,
    row_warnings, visible_columns,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _results():
    return [
        {"defect_id": "1", "ok": True, "bin": 2, "score": 0.42,
         "features": {"glv_median": 90.0, "glv_pixels": 4000.0,
                      "glv_ok": 1.0, "cd_median": 6.5, "mad": 1.2},
         "traces": [{"node_id": "m1", "step_key": "glv_stats", "ok": True,
                     "features_added": ["glv_median", "glv_pixels", "glv_ok"]},
                    {"node_id": "m2", "step_key": "cd_measure", "ok": True,
                     "features_added": ["cd_median"]}]},
        {"defect_id": "2", "ok": True, "bin": 0, "score": 0.10,
         "features": {"glv_median": 10.0, "glv_pixels": 12.0,
                      "glv_ok": 0.0, "cd_median": 9.4, "mad": 0.4},
         "traces": [{"node_id": "m1", "step_key": "glv_stats", "ok": True,
                     "features_added": ["glv_median", "glv_pixels", "glv_ok"]},
                    {"node_id": "m2", "step_key": "cd_measure", "ok": True,
                     "features_added": ["cd_median"]}]},
        {"defect_id": "3", "ok": False, "bin": None, "score": None,
         "error": "subtract: shapes differ", "features": {}, "traces": []},
    ]


#: 判定引用了 `glv_median`（量測）、`ghost`（沒人產出 —— 要是一個空欄）。
VERDICT = ("glv_median", "ghost")


def _spec(name, node, label, **kw):
    return BoundSpec(node, label, FeatureSpec(name=name, **kw))


#: PR-3 起分組吃 BoundSpec（`verdict_features.bound_specs` 的形狀）。
SPECS = (
    _spec("glv_median", "m1", "GLV", base="glv_median",
          metric="glv_median", family="glv"),
    _spec("glv_pixels", "m1", "GLV", base="glv_pixels"),
    _spec("glv_ok", "m1", "GLV", base="glv_ok"),
    _spec("cd_median", "m2", "CD", base="cd_median",
          metric="cd_median", family="cd"),
)
#: 卡片宣告的診斷。`glv_ok`/`glv_pixels` 沒被判定引用 → 兩層都不出現。
DIAGNOSTICS = ("glv_pixels", "glv_ok")
ALARMS = {"glv_ok": False}


def _pane(qapp, verdict=VERDICT, diagnostics=DIAGNOSTICS, alarms=ALARMS,
          specs=SPECS, results=None):
    rows = _results() if results is None else results
    pane = ResultsTablePane()
    pane.set_results(
        rows, {"1": "bright", "2": "nuisance"},
        layout=column_tree(rows, verdict, specs, diagnostics),
        alarms=alarms)
    return pane


def _base_visible():
    fixed = [BADGE_COLUMN]
    for c in BASE_COLUMNS:
        if c == "ok":
            continue
        fixed.append(c)
        if c == "defect_id":
            fixed.append(CLASS_COLUMN)
    return fixed


# --------------------------------------------------------------------------- #
# 分層
# --------------------------------------------------------------------------- #
def test_default_visible_set_is_base_plus_verdict_features(qapp):
    """預設可見 = 徽章 + base + class + 判定引用的特徵，一欄不多。

    ``ghost`` 沒人產出**也在** —— 判定指著一個空欄是使用者要看見的錯，
    默默消失才是說謊。
    """
    pane = _pane(qapp)
    assert pane.visible_column_names() == _base_visible() + ["glv_median",
                                                            "ghost"]


def test_expanding_shows_every_column_and_collapsing_restores(qapp):
    pane = _pane(qapp)
    before = pane.visible_column_names()
    pane.set_expanded(True)
    assert pane.visible_column_names() == pane.columns(), "展開＝全部"
    pane.set_expanded(False)
    assert pane.visible_column_names() == before, "收回要還原"


def test_search_reveals_a_folded_column_and_clearing_restores(qapp):
    pane = _pane(qapp)
    before = pane.visible_column_names()
    assert "cd_median" not in before
    pane.search.setText("cd_")
    assert "cd_median" in pane.visible_column_names(), "命中的摺疊欄要現身"
    pane.search.setText("")
    assert pane.visible_column_names() == before, "清空要還原"
    pane.search.setText("no_such_column")
    assert pane.visible_column_names() == before, "沒命中不加欄（反空洞）"


def test_unreferenced_diagnostics_are_in_neither_layer(qapp):
    """診斷欄離開表格 —— 但**資料還在**：匯出不走這個模組，
    `feature_keys` 照樣看得到它（資料同源，不是刪資料）。"""
    pane = _pane(qapp)
    pane.set_expanded(True)
    for name in DIAGNOSTICS:
        assert name not in pane.columns(), name
    assert set(DIAGNOSTICS) <= set(feature_keys(_results()))


def test_a_diagnostic_the_verdict_asks_about_stays_visible(qapp):
    """判定引用 > 診斷隱藏（使用者 2026-08-27 定調）：樹裡真的比了
    ``glv_ok`` 的話，「這顆為什麼判 NG」要看得到比的那個值。"""
    pane = _pane(qapp, verdict=("glv_ok", "glv_median"))
    vis = pane.visible_column_names()
    assert "glv_ok" in vis
    assert "glv_pixels" not in vis, "沒被引用的那個照樣藏"


def test_the_button_counts_the_folded_columns(qapp):
    pane = _pane(qapp)
    n = len(pane.columns()) - len(pane.visible_column_names())
    assert pane.more.text() == "All measurements (%d)" % n
    assert n > 0, "反空洞：這個佈局要真的有摺疊欄"


def test_a_flat_layout_hides_the_button(qapp):
    pane = ResultsTablePane()
    pane.set_results(_results(), {})       # 沒給 layout ＝ 平鋪
    assert not pane.more.isVisibleTo(pane)
    assert pane.visible_column_names() == pane.columns()


# --------------------------------------------------------------------------- #
# 徽章
# --------------------------------------------------------------------------- #
def test_a_declared_boolean_warns_and_a_numeric_does_not(qapp):
    """警示只來自卡宣告的布林（極性也是宣告的）與 ``error``。

    ``glv_pixels`` 再大、再小都不亮 —— UI 沒有它自己的門檻可以發明。
    """
    rows = _results()
    assert row_warnings(rows[1], ALARMS) == [("glv_ok", 0.0)], \
        "glv_ok=0 落在宣告的壞值上，要警示"
    assert row_warnings(rows[0], ALARMS) == [], \
        "glv_ok=1 正常；glv_pixels=4000 是數值型，不准亮"
    assert row_warnings(rows[2], ALARMS) == \
        [("error", "subtract: shapes differ")]
    assert row_warnings(rows[1], {}) == [], "沒有宣告就沒有警示"


def test_the_badge_cell_shows_only_for_warned_rows(qapp):
    pane = _pane(qapp)
    m = pane.table._model
    col = pane.columns().index(BADGE_COLUMN)
    marks = {m.defect_id_at(i): m.data(m.index(i, col), Qt.DisplayRole)
             for i in range(m.rowCount())}
    assert marks["2"] == "⚠" and marks["3"] == "⚠"
    assert marks["1"] == ""


def test_badge_details_say_name_value_and_card(qapp):
    """明細由該列的 ``traces`` 歸戶 —— 畫的就是引擎算的那一份。"""
    pane = _pane(qapp)
    m = pane.table._model
    row = m.row_of("2")
    assert ("glv_ok", 0.0, "m1") in m.diagnostic_details(row)
    assert ("glv_pixels", 12.0, "m1") in m.diagnostic_details(row)


# --------------------------------------------------------------------------- #
# 既有行為不變
# --------------------------------------------------------------------------- #
def test_a_search_revealed_column_sorts_and_selection_survives(qapp):
    pane = _pane(qapp)
    pane.search.setText("cd_")
    cols = pane.columns()
    pane.table._model.sort(cols.index("cd_median"), Qt.DescendingOrder)
    assert pane.cell_text(0, "cd_median") == "9.4"
    assert pane.select_defect("1") is True
    assert pane.selected_ids() == ["1"]


def test_visible_columns_is_a_pure_function():
    """展開/搜尋的全部邏輯在一支純函式上 —— widget 只是把答案套上去。"""
    cols = ["!warn", "defect_id", "a", "b"]
    verdict = ["!warn", "defect_id", "a"]
    assert visible_columns(cols, verdict, True, "") == cols
    assert visible_columns(cols, verdict, False, "") == verdict
    assert visible_columns(cols, verdict, False, "B") == \
        ["!warn", "defect_id", "a", "b"], "搜尋不分大小寫"
    assert visible_columns(cols, verdict, False, "zzz") == verdict


# --------------------------------------------------------------------------- #
# PR-3：卡 → 區域 → 統計量、雙層表頭、維度過濾
# --------------------------------------------------------------------------- #
REGION_SPECS = (
    _spec("epi_glv_median", "m1", "GLV", base="glv_median", region="epi",
          region_index=0, region_role="all", metric="glv_median",
          family="glv"),
    _spec("epi_glv_mad", "m1", "GLV", base="glv_mad", region="epi",
          region_index=0, region_role="all", metric="glv_mad", family="glv"),
    _spec("mg_glv_median", "m1", "GLV", base="glv_median", region="mg",
          region_index=1, region_role="all", metric="glv_median",
          family="glv"),
    _spec("mg_glv_mad", "m1", "GLV", base="glv_mad", region="mg",
          region_index=1, region_role="all", metric="glv_mad", family="glv"),
    _spec("cd_median", "m2", "CD", base="cd_median", metric="cd_median",
          family="cd"),
)


def _region_pane(qapp, verdict=("epi_glv_median", "mg_glv_median")):
    return _pane(qapp, verdict=verdict, diagnostics=(), specs=REGION_SPECS)


def test_the_tree_is_card_then_region_then_statistic(qapp):
    """`column_tree` 只算一次的那棵樹：卡 → 區域 → 統計量，摺疊區照它排
    （同區域的欄相鄰 —— 表頭的跨欄靠這一條）。"""
    tree = column_tree(_results(), (), REGION_SPECS, ())
    g = next(x for x in tree["groups"] if x["label"] == "GLV")
    assert [r["region"] for r in g["regions"]] == ["epi", "mg"]
    assert [c["name"] for c in g["regions"][0]["columns"]] == \
        ["epi_glv_median", "epi_glv_mad"]
    assert [c["stat_label"] for c in g["regions"][0]["columns"]] == \
        ["Median", "MAD"]
    cols = tree["columns"]
    assert cols.index("epi_glv_mad") == cols.index("epi_glv_median") + 1
    assert cols.index("mg_glv_mad") == cols.index("mg_glv_median") + 1


def test_header_spans_merge_contiguous_same_region_columns():
    """跨欄段是純函式：同卡同區域的連續欄一段；固定欄（沒 spec）不成段。"""
    tree = column_tree(_results(), (), REGION_SPECS, ())
    spans = header_spans(tree["columns"], tree["spec_of"])
    assert [(s["region"], s["count"], s["region_index"]) for s in spans] == \
        [("epi", 2, 0), ("mg", 2, 1)]
    assert [tree["columns"][s["start"]] for s in spans] == \
        ["epi_glv_median", "mg_glv_median"]


def test_the_header_shows_the_statistic_and_the_tooltip_the_raw_name(qapp):
    """下層表頭是統計量短標籤，但**原始欄名永遠在懸停第一行** ——
    它是分數表達式的變數名、CSV 的欄名，短標籤不能把它藏死。"""
    pane = _region_pane(qapp)
    m = pane.table._model
    col = pane.columns().index("epi_glv_median")
    assert m.headerData(col, Qt.Horizontal, Qt.DisplayRole) == "Median"
    tip = str(m.headerData(col, Qt.Horizontal, Qt.ToolTipRole))
    assert tip.splitlines()[0] == "epi_glv_median"
    assert "epi" in tip and "GLV" in tip


def test_a_region_chip_narrows_both_layers(qapp):
    pane = _region_pane(qapp)
    assert "mg_glv_median" in pane.visible_column_names()
    pane.add_dim("region", "epi")
    vis = pane.visible_column_names()
    assert "mg_glv_median" not in vis, "判定層的非 epi 欄也要藏（反空洞）"
    assert "epi_glv_median" in vis
    assert "defect_id" in vis and CLASS_COLUMN in vis, "固定欄不受限縮"


def test_removing_the_chip_restores(qapp):
    pane = _region_pane(qapp)
    before = pane.visible_column_names()
    pane.add_dim("region", "epi")
    assert pane.visible_column_names() != before
    assert len(pane._chips) == 1
    pane.remove_dim("region", "epi")
    assert pane.visible_column_names() == before
    assert pane._chips == [] and pane.dims() == []


def test_a_chip_and_the_search_box_coexist(qapp):
    """搜尋命中 > 維度限縮：指名要看的欄就算不符合 chip 也要現身。"""
    pane = _region_pane(qapp, verdict=("epi_glv_median",))
    pane.add_dim("region", "epi")
    assert "mg_glv_mad" not in pane.visible_column_names()
    pane.search.setText("mg_glv")
    vis = pane.visible_column_names()
    assert "mg_glv_mad" in vis and "mg_glv_median" in vis
    pane.search.setText("")
    assert "mg_glv_mad" not in pane.visible_column_names(), "清空要還原"


def test_dim_menus_offer_only_existing_values(qapp):
    pane = _region_pane(qapp)
    region = [a.text() for a in pane.dim_buttons["region"].menu().actions()]
    assert region == ["epi", "mg"]
    stat = [a.text() for a in pane.dim_buttons["stat"].menu().actions()]
    assert stat == ["Center · Median", "Spread · MAD", "Width · Median"], \
        "metric id 去重、分群消歧（GLV 與 CD 的 Median 是兩個 id）"
    card = [a.text() for a in pane.dim_buttons["card"].menu().actions()]
    assert card == ["GLV", "CD"]
    # 沒有區域值的表（平鋪那組 spec）整顆 Region 鈕收起來。
    flat = _pane(qapp)
    assert not flat.dim_buttons["region"].isVisibleTo(flat)
    assert flat.dim_buttons["stat"].isVisibleTo(flat)


def test_flat_specs_keep_a_single_row_header(qapp):
    """沒有任何欄帶區域 → 表頭退回單層（平鋪與舊 recipe 一個像素不變）。"""
    flat = _pane(qapp)
    tall = _region_pane(qapp)
    assert not flat.table.horizontalHeader()._has_region_row()
    assert tall.table.horizontalHeader()._has_region_row()
    assert tall.table.horizontalHeader().sizeHint().height() > \
        flat.table.horizontalHeader().sizeHint().height()


def test_visible_columns_dims_are_pure_too():
    spec_of = {b.spec.name: b for b in REGION_SPECS}
    cols = ["!warn", "defect_id", "epi_glv_median", "mg_glv_median",
            "cd_median"]
    verdict = ["!warn", "defect_id", "epi_glv_median", "mg_glv_median"]
    dims = [("region", "epi")]
    assert visible_columns(cols, verdict, False, "", spec_of, dims) == \
        ["!warn", "defect_id", "epi_glv_median"]
    # 同維 OR：兩顆 region chip = 兩個區域都留
    both = [("region", "epi"), ("region", "mg")]
    assert visible_columns(cols, verdict, False, "", spec_of, both) == verdict
    # 跨維 AND：epi ∩ CD 卡 = 交集是空的（固定欄照留）
    cross = [("region", "epi"), ("card", "CD")]
    assert visible_columns(cols, verdict, False, "", spec_of, cross) == \
        ["!warn", "defect_id"]
    # 搜尋命中 > 維度限縮
    assert visible_columns(cols, verdict, False, "mg", spec_of, dims) == \
        ["!warn", "defect_id", "epi_glv_median", "mg_glv_median"]
