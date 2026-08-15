"""M1 驗收：單顆執行引擎（happy path、失敗隔離、upto_node、trace、JSON 匯出）。

dummy Step 以 "t_" 前綴註冊進 REGISTRY，fixture teardown 一律 pop 掉，
避免污染並行開發中的 adept/core/steps/ 卡片庫。
"""
from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

# 判定卡（``adc``）住在 ``adept.core.steps``，而 registry 是 import 的副作用填的。
# 不明講的話，這個檔案裡的假卡片是唯一註冊過的東西，用到 adc 的測試會拿到
# 「unknown step 'adc'」—— 一句指不到真正原因的錯誤訊息。
import adept.core.steps  # noqa: F401

from adept.core.pipeline import (
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    Context,
    REGISTRY,
    Recipe,
    RecipeNode,
    Step,
    StepError,
    register_step,
    result_to_json_dict,
    run_dataset,
    run_defect,
)

_KEYS = ["t_eng_load", "t_eng_algo", "t_eng_fail", "t_eng_nan"]


@pytest.fixture()
def dummy_steps():
    """註冊測試卡片；teardown 時從 REGISTRY 移除（鐵則：不留殘骸）。"""
    for k in _KEYS:
        REGISTRY.pop(k, None)

    @register_step
    class TEngLoad(Step):
        key = "t_eng_load"
        label = "測試載入"
        category = CATEGORY_IMAGE
        help = "測試用：從 meta['_defect_item'] 假裝載入 test/ref"
        # 這是一張 Input 卡（F9 Phase 3d）：引擎靠 accepts_kinds 決定
        # 「這批資料要從哪一張卡開始跑」，取代了以前 routes 的鍵。
        accepts_kinds = ("ebi_patch",)
        writes = ["test", "ref"]

        def run(self, ctx: Context, params) -> Context:
            item = ctx.meta["_defect_item"]
            if getattr(item, "fail_load", False):
                raise StepError(self.key, f"模擬載入失敗：{item.defect_id}")
            ctx.set_image("test", np.zeros((4, 4), np.float32))
            ctx.set_image("ref", np.ones((4, 4), np.float32))
            return ctx

    @register_step
    class TEngAlgo(Step):
        key = "t_eng_algo"
        label = "測試特徵"
        category = CATEGORY_ALGO
        help = "測試用：量 test 影像、寫兩個特徵"
        reads = ["test"]
        features_out = ["snr_max", "area"]

        def run(self, ctx: Context, params) -> Context:
            ctx.require_image("test")
            ctx.add_features({"snr_max": 5.0, "area": 4.0})
            return ctx

    @register_step
    class TEngFail(Step):
        key = "t_eng_fail"
        label = "測試失敗"
        category = CATEGORY_ALGO
        help = "測試用：一定 raise StepError"

        def run(self, ctx: Context, params) -> Context:
            raise StepError(self.key, "boom")

    @register_step
    class TEngNan(Step):
        key = "t_eng_nan"
        label = "測試 NaN 特徵"
        category = CATEGORY_ALGO
        help = "測試用：寫入 nan/inf 特徵"

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature("weird_nan", float("nan"))
            ctx.add_feature("weird_inf", float("inf"))
            return ctx

    try:
        yield
    finally:
        for k in _KEYS:
            REGISTRY.pop(k, None)


def make_item(defect_id="d1", **kw):
    return SimpleNamespace(defect_id=defect_id, nm_per_px=1.8, **kw)


def decide_node(node_id="ndecide", expr="snr_max * 2", threshold=3.0):
    """一張判定卡（F9 Phase 3d：分數不再是 recipe 上的固定欄位）。"""
    return RecipeNode(node_id, "adc", {
        "expr": expr, "threshold": threshold,
        "bin_below": 0, "bin_above": 1, "label": ""})


def make_recipe(route=("nload", "nalgo"), nodes=None, expr="snr_max * 2",
                threshold=3.0, decide=True):
    if nodes is None:
        nodes = {
            "nload": RecipeNode("nload", "t_eng_load", {}),
            "nalgo": RecipeNode("nalgo", "t_eng_algo", {}),
            "nfail": RecipeNode("nfail", "t_eng_fail", {}),
            "nnan": RecipeNode("nnan", "t_eng_nan", {}),
        }
    nodes = dict(nodes)
    route = list(route)
    if decide:
        nodes["ndecide"] = decide_node(expr=expr, threshold=threshold)
        route.append("ndecide")
    return Recipe(
        recipe_id="engine_test",
        order=route,
        nodes=nodes,
    )


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------
def test_happy_path_score_and_bin(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch")
    assert r.ok is True
    assert r.error is None
    assert r.defect_id == "d1"
    assert r.score == 10.0                      # snr_max(5) * 2
    assert r.bin == 1                           # 10 >= 3 → above
    assert r.features["snr_max"] == 5.0
    assert r.features["score"] == 10.0
    assert r.context is None                    # keep_context 預設 False


def test_bin_below_threshold(dummy_steps):
    r = run_defect(make_recipe(expr="snr_max * 0.1"), make_item(), "ebi_patch")
    assert r.ok and r.score == 0.5 and r.bin == 0


def test_meta_seeded(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch", keep_context=True)
    ctx = r.context
    assert ctx is not None
    assert ctx.meta["_defect_id"] == "d1"
    assert ctx.meta["_dataset_kind"] == "ebi_patch"
    assert ctx.meta["_defect_item"].defect_id == "d1"
    assert ctx.meta["nm_per_px"] == 1.8
    assert ctx.nm_per_px == 1.8


def test_traces_recorded(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch")
    assert [t.node_id for t in r.traces] == ["nload", "nalgo", "ndecide"]
    assert [t.step_key for t in r.traces] == ["t_eng_load", "t_eng_algo", "adc"]
    assert all(t.ok for t in r.traces)
    assert all(t.error is None for t in r.traces)
    assert all(isinstance(t.ms, float) and t.ms >= 0.0 for t in r.traces)
    assert r.traces[0].features_added == {}
    assert r.traces[1].features_added == {"snr_max": 5.0, "area": 4.0}
    assert r.traces[2].features_added == {"score": 10.0}
    assert r.traces[0].images_after == ["ref", "test"]
    assert r.traces[1].images_after == ["ref", "test"]


# ---------------------------------------------------------------------------
# 失敗處理：run_defect 永不 raise
# ---------------------------------------------------------------------------
def test_step_failure_isolated(dummy_steps):
    rec = make_recipe(route=("nload", "nfail", "nalgo"))
    r = run_defect(rec, make_item(), "ebi_patch")
    assert r.ok is False
    assert r.error.startswith("[nfail]")
    assert "boom" in r.error
    assert r.score is None and r.bin is None
    # 失敗的步驟仍有 trace；後面的步驟被跳過
    assert [t.node_id for t in r.traces] == ["nload", "nfail"]
    assert r.traces[1].ok is False
    assert "boom" in r.traces[1].error


def test_unknown_route_kind_captured_not_raised(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "no_such_kind")
    assert r.ok is False
    assert "no_such_kind" in r.error
    assert r.traces == []


def test_unknown_step_captured(dummy_steps):
    rec = make_recipe(route=("nload", "nghost"),
                      nodes={"nload": RecipeNode("nload", "t_eng_load", {}),
                             "nghost": RecipeNode("nghost", "t_eng_no_such", {})})
    r = run_defect(rec, make_item(), "ebi_patch")
    assert r.ok is False
    assert r.error.startswith("[nghost]")


def test_score_eval_error_missing_feature(dummy_steps):
    rec = make_recipe(route=("nload",), expr="snr_max * 2")  # 沒人產 snr_max
    r = run_defect(rec, make_item(), "ebi_patch")
    assert r.ok is False
    # 訊息現在指得出**是哪一張判定卡**（F9 Phase 3d：分數不再是全域欄位）
    assert r.error.startswith("[ndecide]")
    assert "snr_max" in r.error


def test_run_dataset_failure_isolation_and_progress(dummy_steps):
    ds = SimpleNamespace(kind="ebi_patch", items=[
        make_item("good1"),
        make_item("bad", fail_load=True),
        make_item("good2"),
    ])
    calls = []
    results = run_dataset(make_recipe(), ds,
                          progress=lambda i, n, res: calls.append((i, n, res.ok)))
    assert [r.ok for r in results] == [True, False, True]
    assert [r.defect_id for r in results] == ["good1", "bad", "good2"]
    assert results[1].error.startswith("[nload]")
    assert calls == [(0, 3, True), (1, 3, False), (2, 3, True)]


def test_run_dataset_limit(dummy_steps):
    ds = SimpleNamespace(kind="ebi_patch",
                         items=[make_item(f"d{i}") for i in range(5)])
    results = run_dataset(make_recipe(), ds, limit=2)
    assert [r.defect_id for r in results] == ["d0", "d1"]


# ---------------------------------------------------------------------------
# upto_node（Studio 點卡看中間輸出）
# ---------------------------------------------------------------------------
def test_upto_node_returns_context_without_score(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="nload")
    assert r.ok is True
    assert r.score is None and r.bin is None    # 不算分
    assert r.context is not None                # keep_context 強制 True
    assert "test" in r.context.images and "ref" in r.context.images
    assert [t.node_id for t in r.traces] == ["nload"]   # nalgo 沒跑


def test_upto_node_last_node_runs_it(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="nalgo")
    assert r.ok is True
    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]
    assert r.context.features["snr_max"] == 5.0
    assert "score" not in r.context.features


def test_upto_node_not_on_route_no_raise(dummy_steps):
    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="zzz")
    assert r.ok is False
    assert "zzz" in r.error


def test_upto_node_disabled_target_stops_without_running(dummy_steps):
    rec = make_recipe()
    rec.nodes["nalgo"].enabled = False
    r = run_defect(rec, make_item(), "ebi_patch", upto_node="nalgo")
    assert r.ok is True
    assert [t.node_id for t in r.traces] == ["nload"]   # 目標卡沒執行
    assert r.context is not None
    assert "snr_max" not in r.context.features


# ---------------------------------------------------------------------------
# 停用節點
# ---------------------------------------------------------------------------
def test_disabled_node_skipped(dummy_steps):
    rec = make_recipe(route=("nload", "nfail", "nalgo"))
    rec.nodes["nfail"].enabled = False
    r = run_defect(rec, make_item(), "ebi_patch")
    assert r.ok is True
    assert r.score == 10.0
    assert [t.node_id for t in r.traces] == ["nload", "nalgo", "ndecide"]


# ---------------------------------------------------------------------------
# JSON 匯出
# ---------------------------------------------------------------------------
def test_result_to_json_dict(dummy_steps):
    rec = make_recipe(route=("nload", "nalgo", "nnan"))
    r = run_defect(rec, make_item(), "ebi_patch", keep_context=True)
    assert r.ok is True
    assert math.isnan(r.features["weird_nan"])

    d = result_to_json_dict(r)
    json.dumps(d)                                # 無 ndarray 洩漏、可序列化
    assert "context" not in d                    # context 被丟掉
    assert d["defect_id"] == "d1"
    assert d["ok"] is True
    assert d["score"] == 10.0
    assert d["bin"] == 1
    assert d["features"]["weird_nan"] is None    # nan → None
    assert d["features"]["weird_inf"] is None    # inf → None
    assert d["features"]["snr_max"] == 5.0
    for t in d["traces"]:
        assert t["ms"] == round(t["ms"], 3)      # ms 取 3 位小數
    assert d["traces"][1]["features_added"] == {"snr_max": 5.0, "area": 4.0}
    assert d["traces"][0]["images_after"] == ["ref", "test"]


def test_result_to_json_dict_failure(dummy_steps):
    rec = make_recipe(route=("nload", "nfail"))
    r = run_defect(rec, make_item(), "ebi_patch")
    d = result_to_json_dict(r)
    json.dumps(d)
    assert d["ok"] is False
    assert d["score"] is None and d["bin"] is None
    assert "boom" in d["error"]
