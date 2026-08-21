# F11 Input-0 驗收 — authored 2026-08-17.
"""**一份 recipe 可以有好幾個 image source 入口。**

使用者的話：「Input (image source) 入口，我覺得不該只有一條。」

以前「入口」的定義是**位置** —— `route` 上第一張啟用的卡（線性 route 時代的
寫法，F9 之前畫布還沒有線）。那個定義同時出現在三個地方，寫法都是
`first = True`：`recipe.validate`、`engine._implicit_bindings`、
`viewmodel.available_streams`。後果是**第二張入口卡拿不到 kind-aware 的 writes
宣告**（`load_patch` 在 `channels="auto"` 下只保守宣告 `["test"]`），於是它真的
會產出的那幾條流在 validate 眼裡不存在，下游冒出一片**假的** `missing-image`。

現在定義改成看宣告：**不吃任何影像流的卡就是入口**（`Step.is_source`）。
這一支驗的是那句話在引擎上真的成立 —— 不只是 lint 過得去，而是**兩個入口與
一個入口算出來的數字逐項相同**。

（lint 層的驗收在 `test_recipe.py` 的三條；那邊用假卡片，這邊用真的。）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from make_sample import generate                                # noqa: E402

import d4t.core.steps                                         # noqa: F401,E402
from d4t.core.ingest.dataset import load_dataset              # noqa: E402
from d4t.core.pipeline import (                               # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, run_defect, validate,
)
from d4t.core.pipeline.engine import run_defect_cached        # noqa: E402
from d4t.core.pipeline.cache import StageCache                # noqa: E402


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("f11lot")
    paths = generate(str(out), n=4, seed=11)
    return load_dataset(paths["klarf"])


def _score():
    return ScoreSpec(expr="glv_mean", threshold=1.0, bins={"below": 0, "above": 1})


def _one_entry() -> Recipe:
    """基準線：一張 load 卡載兩個通道（現在的做法）。"""
    return Recipe(
        recipe_id="one_entry",
        routes={"ebi_patch": ["load", "sub", "measure"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {"channels": "test,ref"}),
            "sub": RecipeNode("sub", "subtract",
                              {"a": "test", "b": "ref", "out": "diff"}),
            # metrics 明寫（F18 起預設是 robust 的那一組）—— 這條測的是
            # 「兩個入口跟一個入口算出同樣的數字」，不是預設值。
            "measure": RecipeNode("measure", "glv_stats",
                                  {"source": "diff", "metrics": "glv_mean"}),
        },
        score=_score(),
        edges=[Edge("load", "sub", src_out="test", dst_in="a"),
               Edge("load", "sub", src_out="ref", dst_in="b"),
               Edge("sub", "measure", src_out="diff", dst_in="source")],
    )


def _two_entries() -> Recipe:
    """**兩個入口**：一張載 test、另一張載 ref，會合到 subtract。

    這正是五通道資料（1 BSE + 4 SE）想要的形狀 —— 每個 image source 在畫布上
    是自己的節點、自己的線，而不是一張卡把所有東西攤出來。
    """
    return Recipe(
        recipe_id="two_entries",
        routes={"ebi_patch": ["load_t", "load_r", "sub", "measure"]},
        nodes={
            "load_t": RecipeNode("load_t", "load_patch", {"channels": "test"}),
            "load_r": RecipeNode("load_r", "load_patch", {"channels": "ref"}),
            "sub": RecipeNode("sub", "subtract",
                              {"a": "test", "b": "ref", "out": "diff"}),
            # metrics 明寫（F18 起預設是 robust 的那一組）—— 這條測的是
            # 「兩個入口跟一個入口算出同樣的數字」，不是預設值。
            "measure": RecipeNode("measure", "glv_stats",
                                  {"source": "diff", "metrics": "glv_mean"}),
        },
        score=_score(),
        edges=[Edge("load_t", "sub", src_out="test", dst_in="a"),
               Edge("load_r", "sub", src_out="ref", dst_in="b"),
               Edge("sub", "measure", src_out="diff", dst_in="source")],
    )


def test_two_entries_lint_clean():
    issues = [i for i in validate(_two_entries(), kind="ebi_patch")
              if i.level == "error"]
    assert not issues, [(i.code, i.node_id, i.detail) for i in issues]


def test_two_entries_give_the_same_numbers_as_one(lot):
    """**量出來的數字逐項相同。** 入口的數量是畫布上的事，不是數字的事。

    唯一不同的是 `n_channels` —— 它問的是「**這張卡**載了幾條流」，所以兩個
    入口各自回 1，而一張卡載兩條回 2。那不是誤差，是那個特徵的定義；
    見下一條測試。
    """
    one, two = _one_entry(), _two_entries()
    for item in lot.items:
        a = run_defect(one, item, lot.kind)
        b = run_defect(two, item, lot.kind)
        assert a.ok and b.ok, (a.error, b.error)
        measured = lambda f: {k: v for k, v in f.items()      # noqa: E731
                              if "n_channels" not in k}
        assert measured(a.features) == measured(b.features), item.defect_id
        assert a.score == b.score and a.bin == b.bin


def test_each_entry_reports_its_own_channel_count(lot):
    """`n_channels` 是**每張入口卡自己的**，撞名由既有機制處理。

    兩張 load 卡都寫 `n_channels`，後面那張的值會贏（`Context.add_feature`
    允許覆寫），而前面那張仍然拿得到 —— 名字是 **`<那張卡吐的那條流>_n_channels`**
    （F17-②；以前是 `<節點id>_n_channels`，而節點 id 對使用者等於 `node_3`）。
    這一條把那個語意鎖住，因為它是分數表達式指得到的東西。

    lint 會為此發一個 `feature-collision` **警告**（不是 error）：同名覆寫
    有時是刻意的，但它必須看得見。
    """
    res = run_defect(_two_entries(), lot.items[0], lot.kind)
    assert res.ok, res.error
    assert res.features["n_channels"] == 1.0            # 後面那張（load_r）
    assert res.features["test_n_channels"] == 1.0       # 前面那張仍然指得到

    warns = [i for i in validate(_two_entries(), kind="ebi_patch")
             if i.code == "feature-collision"]
    assert [i.node_id for i in warns] == ["load_r"], warns


def test_the_second_entry_really_is_the_source_of_its_own_stream(lot):
    """第二張入口卡**不是裝飾**：停用它，下游就拿不到 ref。

    這一條擋的是「兩個入口看起來會動，其實資料全從第一張來」——
    那種情形上面那條「逐項相同」也會過。
    """
    r = _two_entries()
    r.nodes["load_r"].enabled = False
    res = run_defect(r, lot.items[0], lot.kind)
    assert not res.ok
    assert "ref" in (res.error or ""), res.error


def test_two_entries_survive_the_image_stage_cache(lot, tmp_path):
    """冷跑與熱跑逐項相同（鐵則 9：影響影像段結果的東西都要進簽章）。

    多一個入口就是多一組來源檔案，所以這一條是「快取簽章看得見第二個入口」
    的驗收 —— F9 那六個安靜算錯的 bug 有兩個就是簽章少看了一樣東西。
    """
    cache = StageCache(str(tmp_path / "cache"))
    r = _two_entries()
    item = lot.items[0]
    cold = run_defect_cached(r, item, lot.kind, cache, "tok")
    hot = run_defect_cached(r, item, lot.kind, cache, "tok")
    assert cold.ok and hot.ok, (cold.error, hot.error)
    assert cold.features == hot.features
    assert hot.features == run_defect(r, item, lot.kind).features
