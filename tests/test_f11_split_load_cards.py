# F11 Input-4 驗收 — authored 2026-08-17.
"""**一種 source 一張卡** —— 因為一張卡服務四種 source 的時候，畫布會說謊。

使用者回報：

> 我還是傾向不同資料流（IMAGE SOURCE）卡片要拆分不要放在一起耶，這樣放在一起
> 反而變得很複雜。例如我現在 load 一張 RSEM image 他就是單張的～但其後的 NODE
> 節點會有 TEST 跟 REF？但實際上是 Single。**這樣畫布跟實際對不起來。**

量出來的實情比回報的更糟 —— 同一個問題「這張卡吐哪幾條流」有**三個不同的答案**：

| 誰回答 | 對 rsem 資料的答案 |
|---|---|
| `resolve_writes`（靜態宣告）| `["test"]` |
| `resolve_writes_for_kind("rsem")` | `["single", "test"]`（`single` 鏡射成 `test`）|
| 畫布真的畫出來的 | `["test", "ref"]` ← 使用者看到的 |
| 資料真的有的 | `["single"]` |

病根是 **`resolve_writes_for_kind`** 這個機制本身：一張卡對不同資料型別宣告不同的
東西，而「資料型別」是使用者在畫布上看不到的東西。拆成兩張卡之後，兩張的宣告都
只看**使用者看得到的值**（`channel_map` 的表格／`out` 的名字），那個機制就沒有人
覆寫它了。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps                                          # noqa: F401,E402
from d4t.core.ingest.dataset import load_dataset                # noqa: E402
from d4t.core.pipeline import (                                 # noqa: E402
    Recipe, RecipeNode, ScoreSpec, get_step, run_defect, validate,
)
from d4t.core.pipeline.step import REGISTRY                     # noqa: E402


@pytest.fixture(scope="module")
def rsem_lot(tmp_path_factory):
    from make_sample_rsem import generate
    out = tmp_path_factory.mktemp("f11_rsem")
    paths = generate(str(out), n=4, seed=17)
    return load_dataset(paths["klarf"])


# ---------------------------------------------------------------------------
# 1. 宣告不再看資料型別
# ---------------------------------------------------------------------------
def test_no_card_declares_different_streams_for_different_kinds():
    """**registry 裡沒有一張卡覆寫 `resolve_writes_for_kind`。**

    這是這一輪換來的不變量，而它是對整個 registry 跑的 —— 下一次有人想用
    「這個 kind 給這幾條、那個 kind 給那幾條」解決問題時，這條測試會叫。
    """
    from d4t.core.pipeline.step import Step
    base = Step.resolve_writes_for_kind.__func__
    offenders = [k for k, c in REGISTRY.items()
                 if c.resolve_writes_for_kind.__func__ is not base]
    assert offenders == [], (
        "%s 對不同資料型別宣告不同的流 —— 那是「畫布跟實際對不起來」的來源，"
        "改成看使用者看得到的參數（見 steps/load.py 的模組說明）" % offenders)


def test_the_two_input_cards_declare_exactly_what_they_produce():
    patch = get_step("load_patch")
    single = get_step("load_single")
    assert patch.resolve_writes(patch.validate_params({})) == ["test", "ref"]
    assert single.resolve_writes(single.validate_params({})) == ["single"]
    # 名字是使用者的：改了 `out`，宣告（＝畫布上的埠）就跟著改
    assert single.resolve_writes({"out": "rsem_img"}) == ["rsem_img"]


# ---------------------------------------------------------------------------
# 2. 單張資料：一條流，而且是那一張圖
# ---------------------------------------------------------------------------
def test_single_image_data_gives_exactly_one_stream(rsem_lot):
    assert rsem_lot.kind == "rsem"
    rec = Recipe(
        recipe_id="one", routes={"rsem": ["load"]},
        nodes={"load": RecipeNode("load", "load_single", {"out": "single"})},
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    for item in rsem_lot.items:
        res = run_defect(rec, item, "rsem", keep_context=True)
        assert res.ok, res.error
        assert list(res.context.images) == ["single"], res.context.images


def test_lint_is_clean_for_a_single_image_pipeline(rsem_lot):
    """`load_single` → 量測卡：lint 一句話都不該說。"""
    rec = Recipe(
        recipe_id="one", routes={"rsem": ["load", "m"]},
        nodes={"load": RecipeNode("load", "load_single", {"out": "single"}),
               "m": RecipeNode("m", "glv_stats", {"source": "single"})},
        score=ScoreSpec(expr="glv_mean", threshold=0.0,
                        bins={"below": 0, "above": 1}))
    issues = [i for i in validate(rec, kind="rsem") if i.level == "error"]
    assert not issues, [(i.code, i.detail) for i in issues]


# ---------------------------------------------------------------------------
# 3. 舊 recipe 的遷移 —— 行為逐項相同
# ---------------------------------------------------------------------------
def test_an_old_rsem_recipe_migrates_to_the_single_image_card():
    """舊檔的 rsem route 靠「`single` 鏡射成 `test`」活著；遷移換卡並保住行為。

    判準是「**舊東西在不在**」（鐵則 9）：route 的 kind 是單張影像的那幾種，
    而它上面有一張 `load_patch`。
    """
    d = {
        "recipe_id": "old",
        "routes": {"ebi_patch": ["load", "m"], "rsem": ["load", "m"]},
        "nodes": {"load": {"step": "load_patch", "params": {}},
                  "m": {"step": "glv_stats", "params": {"source": "test"}}},
        "score": {"expr": "glv_mean", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    # **兩條 route 共用那張 load 卡**（v1 的雙輸入 recipe 就是這樣寫的），
    # 所以 rsem 那條拿到一張**自己的**新卡，ebi_patch 那條不受影響。
    assert r.routes["ebi_patch"][0] == "load"
    assert r.nodes["load"].step == "load_patch"
    new_id = r.routes["rsem"][0]
    assert new_id != "load"
    assert r.nodes[new_id].step == "load_single"
    assert r.nodes[new_id].params == {"out": "test"}
    # 遷移是**一次性**的：遷移過的那份再讀一次不會再變（節點逐項相同）
    again = Recipe.from_json_dict(r.to_json_dict())
    assert {k: (n.step, n.params) for k, n in again.nodes.items()} == \
           {k: (n.step, n.params) for k, n in r.nodes.items()}


def test_a_recipe_whose_only_route_is_single_image_is_migrated_in_place():
    """沒有跟別條 route 共用 → 就地換掉那張卡（不必多開節點）。"""
    d = {
        "recipe_id": "rsem_only",
        "routes": {"rsem": ["load"]},
        "nodes": {"load": {"step": "load_patch", "params": {}}},
        "score": {"expr": "1", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    assert r.routes["rsem"] == ["load"]
    assert r.nodes["load"].step == "load_single"


def test_a_patch_only_recipe_is_not_migrated():
    """只有 ebi_patch 的 recipe 一個字都不該動。"""
    d = {
        "recipe_id": "patch",
        "routes": {"ebi_patch": ["load"]},
        "nodes": {"load": {"step": "load_patch", "params": {}}},
        "score": {"expr": "1", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    assert r.nodes["load"].step == "load_patch"
    assert r.nodes["load"].params == {}


def test_the_migrated_rsem_route_runs_and_gives_the_same_numbers(rsem_lot):
    """遷移之後的 recipe 跑得動，而且與「手寫成新形狀」的那份逐項相同。"""
    fixture = REPO / "tests" / "fixtures" / "recipes" / "dual_route_basic.json"
    r = Recipe.load(str(fixture))
    assert r.nodes[r.routes["rsem"][0]].step == "load_single"   # 遷移過了
    assert r.nodes[r.routes["ebi_patch"][0]].step == "load_patch"
    hand = Recipe.from_json_dict(r.to_json_dict())    # 已經是新形狀的那份
    for item in rsem_lot.items:
        a = run_defect(r, item, "rsem")
        b = run_defect(hand, item, "rsem")
        assert a.ok and b.ok, (a.error, b.error)
        assert a.features == b.features and a.score == b.score


def test_an_omitted_map_falls_back_to_the_card_default(rsem_lot):
    """**參數沒寫 ≠ 空的對照表。**

    recipe JSON 省略預設值是合法的（`test_a_subtract_without_an_explicit_b_keeps_
    the_card_default`），而這幾個 `resolve_*` 拿到的是**原始** `node.params`。
    第一版把「沒這個鍵」與「空字串」混成一件事，畫布上的 Input 卡當場一顆埠都
    不剩 —— 兩支 UI 測試抓到的。
    """
    patch = get_step("load_patch")
    assert patch.resolve_writes({}) == ["test", "ref"]            # 沒寫 → 預設
    assert patch.resolve_writes({"channel_map": ""}) == []        # 清空 → 真的空
    assert patch.resolve_writes({"channel_map": "1:bse"}) == ["bse"]


def test_which_load_card_the_data_wants(rsem_lot):
    """一種 source 一張卡 → 「哪一張」也跟著資料走。

    F11 Enhance-4 起**開新檔是空白畫布**（使用者要自己挑），所以這個答案的用處
    從「起手卡放哪一張」變成「載入資料時要補哪一張」
    （`studio._adopt_source_for`）—— 但那個對照表本身一個字都沒變。
    """
    from d4t.ui.viewmodel import RecipeModel
    assert RecipeModel.starter_step_for("ebi_patch") == "load_patch"
    assert RecipeModel.starter_step_for("tiff_stack") == "load_patch"
    assert RecipeModel.starter_step_for("rsem") == "load_single"
    assert RecipeModel.starter_step_for("folder") == "load_single"
    m = RecipeModel.starter("rsem")
    assert m.node_order == [], "開新檔不預先放載入卡"
    assert m.dirty is False
