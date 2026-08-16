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

from adept.core.pipeline import (
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    Context,
    REGISTRY,
    Recipe,
    RecipeNode,
    ScoreSpec,
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


def make_recipe(route=("nload", "nalgo"), nodes=None, expr="snr_max * 2",
                threshold=3.0):
    if nodes is None:
        nodes = {
            "nload": RecipeNode("nload", "t_eng_load", {}),
            "nalgo": RecipeNode("nalgo", "t_eng_algo", {}),
            "nfail": RecipeNode("nfail", "t_eng_fail", {}),
            "nnan": RecipeNode("nnan", "t_eng_nan", {}),
        }
    return Recipe(
        recipe_id="engine_test",
        routes={"ebi_patch": list(route)},
        nodes=nodes,
        score=ScoreSpec(expr=expr, threshold=threshold,
                        bins={"below": 0, "above": 1}),
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
    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]
    assert [t.step_key for t in r.traces] == ["t_eng_load", "t_eng_algo"]
    assert all(t.ok for t in r.traces)
    assert all(t.error is None for t in r.traces)
    assert all(isinstance(t.ms, float) and t.ms >= 0.0 for t in r.traces)
    assert r.traces[0].features_added == {}
    assert r.traces[1].features_added == {"snr_max": 5.0, "area": 4.0}
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
    assert r.error.startswith("[score]")
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
    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]


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


# ---------------------------------------------------------------------------
# F9-2：卡片只看得到自己宣告的輸入
# ---------------------------------------------------------------------------
def test_a_card_cannot_see_a_stream_it_did_not_declare():
    """偷讀一條沒宣告的流 → 當場拿到帶說明的錯誤，而不是安靜地讀到。

    這是 F9-2 真正改掉的東西。以前是一個 ``ctx`` 從頭傳到尾，所以每張卡都
    看得到「到目前為止的所有流」——「偷讀」根本不會有症狀：**畫布上不會有那條
    線，使用者於是看不出兩張卡有關係**，而改了上游那張，下游的數字會跟著變。

    這條測試如果被拿掉或改成寬鬆的，F9-5 的分支就會**安靜地錯**：兩條支線
    互相看得到對方的流。
    """
    keys = ["t_f9_load", "t_f9_peeker"]
    for k in keys:
        REGISTRY.pop(k, None)

    @register_step
    class TF9Load(Step):
        key = "t_f9_load"
        label = "測試載入"
        category = CATEGORY_IMAGE
        help = "測試用：寫 test 與 secret 兩條流"
        writes = ["test", "secret"]

        def run(self, ctx: Context, params) -> Context:
            ctx.set_image("test", np.zeros((4, 4), np.float32))
            ctx.set_image("secret", np.ones((4, 4), np.float32))
            return ctx

    @register_step
    class TF9Peeker(Step):
        key = "t_f9_peeker"
        label = "偷看的卡"
        category = CATEGORY_ALGO
        help = "測試用：宣告只讀 test，實際去讀 secret"
        reads = ["test"]                       # ← 宣告
        features_out = ["peeked"]

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature("peeked", float(ctx.require_image("secret").mean()))
            return ctx                          # ← 實際（沒宣告）

    try:
        rec = make_recipe(
            route=("nload", "npeek"),
            nodes={"nload": RecipeNode("nload", "t_f9_load", {}),
                   "npeek": RecipeNode("npeek", "t_f9_peeker", {})},
            expr="0")
        r = run_defect(rec, make_item(), "ebi_patch")

        assert r.ok is False, "偷讀沒宣告的流應該當場失敗"
        assert "secret" in r.error
        # 訊息要講得出「這張卡看得到的是什麼」——而那份清單只有它宣告的 test
        assert "'test'" in r.error and "secret'" in r.error
        assert "peeked" not in (r.features or {}), "失敗的卡不該留下特徵"
    finally:
        for k in keys:
            REGISTRY.pop(k, None)


def test_a_card_still_sees_every_stream_it_did_declare():
    """反面：宣告了的照樣拿得到 —— 隔離不是把卡片餓死。"""
    keys = ["t_f9_load2", "t_f9_honest"]
    for k in keys:
        REGISTRY.pop(k, None)

    @register_step
    class TF9Load2(Step):
        key = "t_f9_load2"
        label = "測試載入"
        category = CATEGORY_IMAGE
        help = "測試用：寫 test 與 ref"
        writes = ["test", "ref"]

        def run(self, ctx: Context, params) -> Context:
            ctx.set_image("test", np.zeros((4, 4), np.float32))
            ctx.set_image("ref", np.full((4, 4), 3.0, np.float32))
            return ctx

    @register_step
    class TF9Honest(Step):
        key = "t_f9_honest"
        label = "老實的卡"
        category = CATEGORY_ALGO
        help = "測試用：宣告讀 test 與 ref，也真的只讀這兩條"
        reads = ["test", "ref"]
        features_out = ["both"]

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature("both", float(ctx.require_image("test").mean()
                                          + ctx.require_image("ref").mean()))
            return ctx

    try:
        rec = make_recipe(
            route=("nload", "nhonest"),
            nodes={"nload": RecipeNode("nload", "t_f9_load2", {}),
                   "nhonest": RecipeNode("nhonest", "t_f9_honest", {})},
            expr="both")
        r = run_defect(rec, make_item(), "ebi_patch")
        assert r.ok is True, r.error
        assert r.features["both"] == 3.0
    finally:
        for k in keys:
            REGISTRY.pop(k, None)
