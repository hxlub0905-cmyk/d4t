# F13-①：特徵表分組 — authored 2026-08-19.
"""**一條平的清單裡，`n_channels` 跟 `glv_median` 長得一模一樣。**

使用者：「目前 feature 的顯示太陽春了不易閱讀，試著將他分類」。而一個是
「這張卡讀了幾頁」、一個是會決定 bin 的量測值 —— 那個差別在畫面上完全看不到。

這一份鎖住的重點是：**分組不是 UI 發明的規則**。引擎本來就記著每個特徵是哪
張卡寫的（`meta["feature_owner"]`），卡片也早就宣告了哪些是診斷數字
（`Step.diagnostic_features`）。UI 只是把已經知道的事顯示出來 —— 自己發明一
份分類的話它會跟引擎漂，而漂掉的症狀是「這個數字被歸到錯的卡底下」，
畫面上完全看不出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication          # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.core.pipeline import get_step              # noqa: E402
from d4t.ui import studio as studio_mod             # noqa: E402
from d4t.ui import theme as theme_mod               # noqa: E402
from d4t.ui.widgets import FeatureTable             # noqa: E402

EXAMPLE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f13")), n=4, seed=7)


@pytest.fixture
def ran(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1500, 950)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    win.select_node(win.model.node_order[-1])
    win.refresh_preview(sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 分組照引擎記的來
# --------------------------------------------------------------------------- #
def test_each_group_is_the_card_that_produced_it(ran):
    """組名 = 卡片的 label，而成員 = 引擎記的 owner —— 兩邊都不是猜的。"""
    ctx = ran._last_result.context
    owner = ctx.meta[studio_mod.FEATURE_OWNER_KEY]
    sections = ran._feature_sections(ran._last_result)
    assert sections, "有跑出特徵就要分得出組"

    by_title = {s["title"]: s for s in sections if s["title"] != "Diagnostics"}
    for title, sec in by_title.items():
        nid = sec["node"]
        assert get_step(ran.model.nodes[nid].step).label in title
        for name in sec["names"]:
            assert owner[name] == nid, "%s 被歸到 %s 底下" % (name, title)


def test_the_diagnostics_are_the_ones_the_card_declared(ran):
    """`clip_frac` 那一類是卡片自己宣告的（`diagnostic_features`）。"""
    sections = ran._feature_sections(ran._last_result)
    diag = next(s for s in sections if s["title"] == "Diagnostics")
    assert diag["collapsed"] is True, "它每張 Enhance 卡都會產出，攤開會擠掉量測值"

    # 救回來那一份的前綴**跟引擎用同一支**（F17-②）—— 測試自己組一份的話，
    # 引擎改了規則它就會漂，而症狀是這條測試紅得莫名其妙。
    from d4t.core.pipeline.engine import feature_prefixes
    from d4t.core.pipeline.step import REGISTRY

    prefixes = feature_prefixes(list(ran.model.node_order),
                                ran.model.to_recipe(), REGISTRY)
    declared = set()
    for nid, node in ran.model.nodes.items():
        for f in get_step(node.step).diagnostic_features(node.params):
            declared.add(f)
            declared.add("%s_%s" % (prefixes.get(nid, nid), f))
    for name in diag["names"]:
        assert name in declared, name


def test_a_rescued_feature_is_still_a_diagnostic(ran):
    """兩張 Enhance 卡都寫 `clip_frac`，engine 把先寫的留成
    `<節點名>_clip_frac`。不算進診斷的話，它會以「量測值」的身分排在最上面 ——
    而它量的是那張卡自己。"""
    sections = ran._feature_sections(ran._last_result)
    diag = next(s for s in sections if s["title"] == "Diagnostics")
    rescued = [n for n in diag["names"] if n.endswith("_clip_frac")
               and n != "clip_frac"]
    assert rescued, "這份 recipe 有兩張 Enhance 卡，應該救回過一個"


def test_two_cards_with_the_same_name_get_their_id(qapp, lot):
    """兩組都叫 `Gray level` 的話，使用者分不出哪一組是哪一張卡。

    只有**重複的時候**才帶 id —— 每一組都掛一個 node id 是在每一份正常的
    recipe 上加噪音（畫布的副標用的是同一條規則）。
    """
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lot["klarf"], sync=True)
        win.load_recipe_path(str(EXAMPLE), sync=True)
        src = win.model.node_order[0]
        for prefix in ("a", "b"):
            nid = win.add_card_after(src, "glv_stats")
            win._on_edge_added(src, nid, "test", "source")
            win.model.set_param(nid, "output_prefix", prefix)
        # 預覽只跑到**選著的那張卡**為止 —— 要看整條 route 的特徵就選最後一張。
        win.select_node(win.model.node_order[-1])
        win.refresh_preview(sync=True)

        titles = [s["title"] for s in win._feature_sections(win._last_result)]
        dupes = [t for t in titles if t.startswith(get_step("glv_stats").label)]
        assert len(dupes) >= 2 and len(set(dupes)) == len(dupes), titles
        assert all(" · " in t for t in dupes), dupes
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 2. 表本身：標題不是特徵、收合看得懂、score 永遠在
# --------------------------------------------------------------------------- #
def test_a_group_header_is_not_a_feature(ran):
    """`feature_names()` 有一堆呼叫端（報表、測試）—— 標題混進去的話，
    它們會拿到一個叫 `▾ GLV · 1` 的「特徵」。"""
    names = ran.feature_panel.feature_names()
    assert names, "表上要有東西"
    assert not any(n.startswith("▾") or n.startswith("▸") for n in names)
    assert set(names) <= set(ran._last_result.features)


def test_clicking_a_header_folds_that_group_only():
    table = FeatureTable()
    try:
        table.set_features(
            {"a": 1.0, "b": 2.0, "c": 3.0, "score": 9.0},
            sections=[{"title": "One", "color": "#5f8f3f", "names": ["a", "b"]},
                      {"title": "Two", "color": "#bf7030", "names": ["c"]}])
        assert table.section_titles() == ["One", "Two"]
        rows = {table.item(r, 0).text(): r for r in range(table.rowCount())}
        assert not table.isRowHidden(rows["a"])

        head = rows["▾ One  ·  2"]
        table.toggle_section(head)
        assert table.isRowHidden(rows["a"]) and table.isRowHidden(rows["b"])
        assert not table.isRowHidden(rows["c"]), "只收自己那一組"
        assert not table.isRowHidden(rows["score"])
        assert table.item(head, 0).text().startswith("▸"), "箭頭要跟著翻面"

        table.toggle_section(head)
        assert not table.isRowHidden(rows["a"])
        assert table.item(head, 0).text().startswith("▾")
    finally:
        table.deleteLater()


def test_the_score_is_never_folded_away():
    """它是這張表的結論 —— 收在某一組底下就找不到了。"""
    table = FeatureTable()
    try:
        table.set_features({"a": 1.0, "score": 4.0},
                           sections=[{"title": "One", "color": "",
                                      "names": ["a", "score"],
                                      "collapsed": True}])
        rows = {table.item(r, 0).text(): r for r in range(table.rowCount())}
        assert table.isRowHidden(rows["a"])
        assert not table.isRowHidden(rows["score"])
    finally:
        table.deleteLater()


def test_a_feature_nobody_claims_still_shows_up():
    """漏掉一個 = 那個數字從畫面上消失，而使用者不會知道它存在過。"""
    table = FeatureTable()
    try:
        table.set_features({"a": 1.0, "orphan": 2.0},
                           sections=[{"title": "One", "color": "",
                                      "names": ["a"]}])
        assert "orphan" in table.feature_names()
        assert "Other" in table.section_titles()
    finally:
        table.deleteLater()


def test_without_sections_it_is_the_old_flat_list():
    """CLI／報表／既有測試都還走這條路。"""
    table = FeatureTable()
    try:
        table.set_features({"a": 1.0, "b": 2.0, "score": 3.0})
        assert table.section_titles() == []
        assert table.feature_names() == ["a", "b", "score"]
    finally:
        table.deleteLater()
