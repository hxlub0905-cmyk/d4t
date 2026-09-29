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

⚠ **F121 期 2（2026-09-24）又合回一張「Input」**（`load_patch`；使用者：入口
簡單化）。這一份守的不變量一條都沒變 —— 宣告只看使用者看得到的值（名字表）、
單張資料只吐一條流、舊檔遷移之後行為逐項相同、遷移是一次性的 —— 只是「看得到
的值」剩下名字表一種：`load_single(out="x")` 由遷移換成 `load_patch("1:x")`，
而名字表在開資料時照資料填（`RecipeModel.add_starter_input`）。
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


def test_the_input_card_declares_exactly_what_it_produces():
    patch = get_step("load_patch")
    assert patch.resolve_writes(patch.validate_params({})) == ["test", "ref"]
    assert patch.resolve_writes({"channel_map": "1:single"}) == ["single"]
    # 名字是使用者的：改了名字表，宣告（＝畫布上的埠）就跟著改
    assert patch.resolve_writes({"channel_map": "1:rsem_img"}) == ["rsem_img"]
    assert "load_single" not in REGISTRY, "F121 期 2 併回 Input 了"


# ---------------------------------------------------------------------------
# 2. 單張資料：一條流，而且是那一張圖
# ---------------------------------------------------------------------------
def test_single_image_data_gives_exactly_one_stream(rsem_lot):
    assert rsem_lot.kind == "rsem"
    rec = Recipe(
        recipe_id="one", routes={"rsem": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch",
                                  {"channel_map": "1:single"})},
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    for item in rsem_lot.items:
        res = run_defect(rec, item, "rsem", keep_context=True)
        assert res.ok, res.error
        assert list(res.context.images) == ["single"], res.context.images


def test_lint_is_clean_for_a_single_image_pipeline(rsem_lot):
    """一列的 Input → 量測卡：lint 一句話都不該說。"""
    rec = Recipe(
        recipe_id="one", routes={"rsem": ["load", "m"]},
        nodes={"load": RecipeNode("load", "load_patch",
                                  {"channel_map": "1:single"}),
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
    而它上面有一張 `load_patch` —— **而且檔案是第 1 版**（F121 期 2 起「單張
    route 上的 `load_patch`」也是新檔案的正常樣子）。F11 那一道先換成
    `load_single(out="test")`，F121 那一道接著換成一列的 Input ``1:test``。
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
    assert r.nodes[new_id].step == "load_patch"
    assert r.nodes[new_id].params == {"channel_map": "1:test"}
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
    # 第 6 版那一道會替舊分數補一張 Decision 卡（F123）—— 這一條問的是 Input 卡。
    assert [n for n in r.routes["rsem"]
            if r.nodes[n].step != "decision"] == ["load"]
    assert r.nodes["load"].step == "load_patch"
    assert r.nodes["load"].params == {"channel_map": "1:test"}


def test_a_current_single_image_input_card_is_left_alone():
    """**反向**（F121 期 2）：第 2 版以上的檔案裡，單張 route 上的 Input 卡是
    正常樣子 —— F11 那一道不准再碰它。碰了的話 ``1:single`` 會被換成
    ``1:test``，下游指著 `single` 的線全斷，而且每存一次變一次（鐵則 9）。"""
    d = {
        "recipe_id": "rsem_now", "version": 5,
        "routes": {"rsem": ["load"]},
        "nodes": {"load": {"step": "load_patch",
                           "params": {"channel_map": "1:single"}}},
        "score": {"expr": "1", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    r = Recipe.from_json_dict(d)
    assert r.nodes["load"].params == {"channel_map": "1:single"}
    assert Recipe.from_json_dict(r.to_json_dict()).to_json_dict() == \
        r.to_json_dict()


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
    first = r.nodes[r.routes["rsem"][0]]                        # 遷移過了
    assert (first.step, first.params.get("channel_map")) == ("load_patch", "1:test")
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


def test_the_input_card_the_data_gets(rsem_lot, tmp_path):
    """載入資料時補的那一張（`studio._adopt_source_for`）：**名字表照資料填**。

    F11 那時是「一種 source 一張卡」，由資料型別決定補哪一張；F121 期 2 起只有
    一張，由資料決定**名字表**—— 一顆一張就是一列，畫布上因此只有一顆埠
    （F11 那句「這樣畫布跟實際對不起來」要守的正是這件事）。
    """
    from make_sample import generate

    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel.starter("rsem")
    nid = m.add_starter_input(rsem_lot.items[0])
    assert m.nodes[nid].step == "load_patch"
    assert m.nodes[nid].params["channel_map"] == "1:single"
    assert get_step("load_patch").resolve_writes(m.nodes[nid].params) == \
        ["single"]

    paths = generate(str(tmp_path / "patch"), n=2, seed=3)
    patch = load_dataset(paths["klarf"], paths["tiff"])
    p = RecipeModel.starter()
    pid = p.add_starter_input(patch.items[0])
    assert p.nodes[pid].params["channel_map"] == "1:test, 2:ref"

    m = RecipeModel.starter("rsem")
    assert m.node_order == [], "開新檔不預先放載入卡"
    assert m.dirty is False
