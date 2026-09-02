# F76 刀 4：Preview 欄的特徵面板 —— 四胞胎橫過來。
"""測的是 `feature_panel.panel_model`（**純函式**，沒有 Qt）。

「畫成什麼樣」測得起來、不必開一個視窗，是這個 repo 對顯示層的一貫立場
（同 `widgets.feature_html` 與 `why_panel.why_rows`）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
from d4t.core.pipeline import get_step
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.recipe import Recipe
from d4t.core.pipeline.verdict_features import bound_specs, diagnostic_columns

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def measured():
    """真的跑一次 GLV 的逐框模式 —— 面板吃的是引擎寫出來的那一份。"""
    import numpy as np

    n = 5
    img = np.zeros((40, 200), np.float32)
    rng = np.random.default_rng(0)
    for i, (mid, sd) in enumerate([(100, 5), (101, 5), (99, 5),
                                   (100, 30), (160, 6)]):
        img[:, i * 40:(i + 1) * 40] = mid + rng.normal(0, sd, (40, 40))
    ctx = Context(images={"test": img})
    ctx.set_roi_boxes("cells", [(i / n, 0.0, 1.0 / n, 1.0) for i in range(n)])
    card = get_step("glv_stats")
    params = {"source": "test", "roi": "cells", "across_boxes": "each box",
              "judge": "glv_median", "metrics": "glv_median,glv_std"}
    card().run(ctx, params)
    specs = card.resolve_feature_specs(card.validate_params(params))
    return dict(ctx.features), specs


class _Bound:
    """`BoundSpec` 的最小替身（面板只讀這三個欄位）。"""

    def __init__(self, spec):
        self.node_id, self.label, self.spec = "glv", "GLV", spec


def _model(measured, **kw):
    from d4t.ui.feature_panel import panel_model

    feats, specs = measured
    return panel_model(feats, [_Bound(s) for s in specs], **kw)


# --------------------------------------------------------------------------- #
# 1. 四胞胎橫過來
# --------------------------------------------------------------------------- #
def test_the_four_variants_become_columns_not_rows(measured):
    """19 列 → 一個標題 + 兩列。**這就是這一刀的全部**。"""
    sec = [s for s in _model(measured) if s["grid"]["rows"]][0]
    assert sec["grid"]["columns"] == ["typical", "worst", "outlier"], \
        "順序是「先講常態，再講嫌疑人」"
    assert [r["label"] for r in sec["grid"]["rows"]] == ["Median", "Std dev"]


def test_outlier_box_is_an_address_not_a_row(measured):
    """``_outlier_box`` 的值是**框號**，所以它貼在 outlier 那一格旁邊。

    以前它自己佔一列，而那一列的說明欄寫著「median(gray)」、值是 46 ——
    一個框的序號被當成灰階讀。
    """
    from d4t.ui.feature_panel import VARIANT_COLUMNS

    sec = [s for s in _model(measured) if s["grid"]["rows"]][0]
    assert "outlier_box" not in sec["grid"]["columns"]
    assert "outlier_box" not in VARIANT_COLUMNS
    for row in sec["grid"]["rows"]:
        assert row["outlier_box"] is not None
    # 而它一列都不佔
    flat = {r["name"] for r in sec["flat"]}
    assert not [n for n in flat if n.endswith("_outlier_box")]


def test_the_row_says_whether_the_outlier_is_the_same_box_as_the_winner(measured):
    """**這一欄唯一沒有的資訊就是「那是哪一格」**，所以它一定要在。

    造的五格：judge 是 median，所以贏家是 #4（median 160）；而 std 那一欄
    最極端的是 #3（std 30）—— 兩個不同的格，名字上沒有任何線索。
    使用者 2026-09-02：「反而這樣會誤導別人以為他是最 worst 的」。
    """
    sec = [s for s in _model(measured) if s["grid"]["rows"]][0]
    by = {r["label"]: r for r in sec["grid"]["rows"]}
    assert by["Median"]["same_box"] is True
    assert by["Std dev"]["same_box"] is False
    assert by["Std dev"]["outlier_box"] == 3
    # 而兩個值真的不一樣（6.2 vs 29.8）—— 這才是它值得講的理由
    assert by["Std dev"]["cells"]["worst"]["value"] \
        != by["Std dev"]["cells"]["outlier"]["value"]


# --------------------------------------------------------------------------- #
# 2. 標題那一行 = 那張卡自己說的（通用掛鉤）
# --------------------------------------------------------------------------- #
def test_the_headline_comes_from_the_card_not_from_the_panel(measured):
    """`Step.panel_headline` 是掛鉤 —— UI 不認得 `glv_worst_*` 這些名字。"""
    sec = [s for s in _model(measured) if s["headline"]][0]
    labels = [str(a) for a, _v, _u in sec["headline"]]
    units = [str(u) for _a, _v, u in sec["headline"]]
    assert "odd one out" in labels
    assert "σ" in units, "異常度的單位是 σ，不是一個裸數字"


def test_the_winner_family_leaves_the_list_once_the_headline_has_it(measured):
    """``glv_worst_i/score`` 升格成標題就不再佔一列（同一個數字不講兩遍）。

    座標 ``x/y/w/h`` 也一起收起來 —— 它們是給疊圖用的，不是給人讀的。
    """
    sec = [s for s in _model(measured) if s["headline"]][0]
    flat = {r["name"] for r in sec["flat"]}
    for gone in ("glv_worst_i", "glv_worst_score",
                 "glv_worst_x", "glv_worst_y", "glv_worst_w", "glv_worst_h"):
        assert gone not in flat, gone
    # 而不是整族消失：judge 那一格的值與逐框分布還在
    assert "glv_worst_value" in flat
    assert "glv_worst_score_median" in flat


def test_a_card_with_no_headline_just_gets_a_list():
    """**沒有 variant、沒有標題的卡就是以前那張清單** —— 一欄，不是四欄。

    這一條守的是「這一份沒有一行是 GLV 專屬的」：模板一樣，只是那張卡沒有
    東西可以填。
    """
    from d4t.ui.feature_panel import panel_model

    card = get_step("load_single")
    specs = card.resolve_feature_specs(card.validate_params({}))
    bounds = [type("B", (), {"node_id": "load", "label": "Load one image",
                             "spec": s})() for s in specs]
    model = panel_model({"n_channels": 1.0}, bounds)
    assert len(model) == 1
    assert model[0]["headline"] == []
    assert model[0]["grid"]["rows"] == []
    assert [r["name"] for r in model[0]["flat"]] == ["n_channels"]


# --------------------------------------------------------------------------- #
# 3. 分組跟結果表同一棵樹
# --------------------------------------------------------------------------- #
def test_the_sections_are_card_then_region_and_the_colour_agrees():
    """一段 = 一張卡 × 一個區域，而**同一個區域一個顏色**（F76 刀 1）。"""
    from d4t.ui.feature_panel import panel_model

    recipe = Recipe.load(REPO / "recipes" / "rsem-worst-box.json")
    bounds = bound_specs(recipe, "rsem")
    feats = {str(b.spec.name): 1.0 for b in bounds}
    model = panel_model(feats, bounds,
                        diagnostics=diagnostic_columns(recipe, "rsem"))
    by_region = {}
    for sec in model:
        if sec["region"]:
            by_region.setdefault(sec["region"], set()).add(sec["region_index"])
    assert by_region, "這份 recipe 有三個區域，抓不到就是這條測試空轉了"
    assert all(len(v) == 1 for v in by_region.values()), by_region


def test_diagnostics_land_in_their_own_section_unless_the_verdict_asks(measured):
    """規矩跟結果表同一條：**判定引用 > 診斷隱藏**。"""
    feats, specs = measured
    diag = ["glv_pixels", "glv_boxes"]
    plain = _model(measured, diagnostics=diag)
    assert plain[-1]["label"] == "Diagnostics"
    assert {r["name"] for r in plain[-1]["flat"]} == set(diag)

    asked = _model(measured, diagnostics=diag, highlight=["glv_pixels"])
    names = {r["name"] for s in asked if s["label"] != "Diagnostics"
             for r in s["flat"]}
    assert "glv_pixels" in names, "判定引用了它就不准藏"


def test_a_feature_this_defect_never_wrote_takes_no_row(measured):
    """算不出來的那一格**不寫**（F19），所以面板上也不該有一列空的。"""
    feats, specs = measured
    from d4t.ui.feature_panel import panel_model

    thin = {k: v for k, v in feats.items() if k != "glv_worst_value"}
    model = panel_model(thin, [_Bound(s) for s in specs])
    assert "glv_worst_value" not in {r["name"] for s in model
                                     for r in s["flat"]}


# --------------------------------------------------------------------------- #
# 4. F76 刀 5：沒有判定就不畫 Verdict 那一塊
# --------------------------------------------------------------------------- #
def test_the_verdict_block_is_not_there_until_there_is_a_decision(tmp_path):
    """使用者 2026-09-02：「大部分人應該建立 Pipeline 時 ADC 不會放到第一個」。

    在那段時間裡這一塊永遠是一個寫著 ``—`` 的 chip 加一片空白 —— 它不是壞的，
    它是**什麼都沒說**，而那塊面積正好是量測卡最需要的地方。

    判準用 **model**（recipe 有沒有判定），不用「這一顆有沒有 bin」：後者在
    還沒預覽、或這一顆量不出來的時候也是空的，而那兩件事的下一步完全不同
    （一個是「去加一棵樹」，另一個是「先跑一次」）。
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from d4t.ui import studio as studio_mod, theme as theme_mod

    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    recipe = Recipe.load(REPO / "recipes" / "rsem-worst-box.json")

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.show()
        path = tmp_path / "with.json"
        recipe.save(path)
        assert win.load_recipe_path(path, sync=True)
        app.processEvents()
        assert win.has_decision(), "這份 recipe 有一棵樹"
        assert not win.verdict_empty.isVisibleTo(win)

        # 拿掉判定 → 那一塊換成「怎麼加一個」，而不是一個說不出話的 chip
        from dataclasses import replace

        naked = tmp_path / "without.json"
        recipe.decide = replace(recipe.decide, tree=None, rules=(), score="")
        recipe.score = type(recipe.score)(expr="", threshold=0.0, bins={})
        recipe.save(naked)
        assert win.load_recipe_path(naked, sync=True)
        app.processEvents()
        assert not win.has_decision()
        assert win.verdict_empty.isVisibleTo(win)
        assert not win.verdict_live.isVisibleTo(win)
        # 而那句話要**講得出下一步**，並且那一步就在旁邊
        assert win.btn_add_decision.isEnabled()
    finally:
        win.close()
