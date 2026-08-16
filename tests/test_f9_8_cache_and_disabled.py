# F9-8／F9-10：快取看得見線、快照存得下身分、停用的卡沿線讓路 — 2026-08-16.
"""分支之下，三個「跑得完、有數字、而且是錯的」的路徑。

同一個病根：F9 把影像流的身分改成 ``(節點, 埠)`` 了，但**快取的簽章**、
**快取的內容**與**停用節點的退路**這三處仍然用「全域名字」在想事情。

1. **改一條線不會讓快取失效**（F9-8）。簽章只算 node + params，而在畫布上把線
   從 A 改接到 B 可以完全不動任何參數（兩邊都叫 ``ref``）。使用者的體感是
   「我改了接線、重跑、數字沒動」—— 而他會以為是自己改錯了。
2. **同一份分支 recipe 跑第二次，數字會變**（F9-10）。快照存的是 ``images``
   ＝「名字 → 最後一個寫它的人」，分支之後同一個名字有好幾張圖。
3. **停用分支中間那張卡，下游會去吃另一支的資料**（F9-8）。被停用的節點沒有
   產出，而以前查不到就退回「最後一個寫這個名字的人」＝ 隔壁那一支。

全部用「一支 ×3、一支 ×5」的假卡片驗 —— 乘法讓「這一支到底吃到誰的輸出」
一眼看得出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from adept.core.pipeline import (                          # noqa: E402
    CATEGORY_ALGO, CATEGORY_IMAGE, Context, Edge, ParamSpec, REGISTRY, Recipe,
    RecipeNode, ScoreSpec, Step, register_step, run_defect,
)
from adept.core.pipeline.cache import StageCache           # noqa: E402
from adept.core.pipeline.engine import (                   # noqa: E402
    image_segment_signature, run_defect_cached,
)

_KEYS = ["t8_load", "t8_scale", "t8_measure"]


@pytest.fixture()
def cards():
    for k in _KEYS:
        REGISTRY.pop(k, None)

    @register_step
    class T8Load(Step):
        key = "t8_load"
        label = "載入"
        category = CATEGORY_IMAGE
        help = "測試用：寫一條值全是 1 的 ref"
        writes = ["ref"]

        def run(self, ctx: Context, params) -> Context:
            ctx.set_image("ref", np.ones((4, 4), np.float32))
            return ctx

    @register_step
    class T8Scale(Step):
        key = "t8_scale"
        label = "乘一個數"
        category = CATEGORY_IMAGE          # 影像段 → 會落在 checkpoint 之前
        help = "測試用：把指定的流乘上 factor，就地寫回同一條流"
        params = [ParamSpec("streams", "image_keys", "ref", "要處理的影像流"),
                  ParamSpec("factor", "float", 2.0, "乘數")]

        @classmethod
        def resolve_reads(cls, params):
            return [s.strip() for s in str(params.get("streams", "")).split(",")
                    if s.strip()]

        resolve_writes = resolve_reads

        def run(self, ctx: Context, params) -> Context:
            for name in self.resolve_reads(params):
                ctx.set_image(name,
                              ctx.require_image(name) * float(params["factor"]))
            return ctx

    @register_step
    class T8Measure(Step):
        key = "t8_measure"
        label = "量平均"
        category = CATEGORY_ALGO           # 算法段 → checkpoint 之後
        help = "測試用：量指定影像流的平均值"
        features_out = ["mean"]
        params = [ParamSpec("source", "image_key", "ref", "要量哪條流")]

        @classmethod
        def resolve_reads(cls, params):
            return [str(params.get("source", "ref"))]

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature("mean",
                            float(ctx.require_image(params["source"]).mean()))
            return ctx

    yield
    for k in _KEYS:
        REGISTRY.pop(k, None)


class _Item:
    defect_id = "1"


def _recipe(route, nodes, edges):
    return Recipe(recipe_id="f9_8", routes={"ebi_patch": list(route)},
                  nodes=nodes, edges=list(edges),
                  score=ScoreSpec("0", 0.0, {"below": 0, "above": 1}))


def _branch(disabled=()):
    """load ─┬─ x3 ─ m3      兩支互不干擾，各自被量。"""
    def n(nid, step, params):
        return RecipeNode(nid, step, params, enabled=nid not in disabled)
    return {"load": n("load", "t8_load", {}),
            "x3": n("x3", "t8_scale", {"factor": 3.0}),
            "x5": n("x5", "t8_scale", {"factor": 5.0}),
            "m3": n("m3", "t8_measure", {}),
            "m5": n("m5", "t8_measure", {})}


_BRANCH_EDGES = [Edge("load", "x3", src_out="ref", dst_in="streams"),
                 Edge("load", "x5", src_out="ref", dst_in="streams"),
                 Edge("x3", "m3", src_out="ref", dst_in="source"),
                 Edge("x5", "m5", src_out="ref", dst_in="source")]
_ROUTE = ["load", "x3", "x5", "m3", "m5"]


# --------------------------------------------------------------------------- #
# 1. 快取的簽章要看得見線
# --------------------------------------------------------------------------- #
def test_moving_a_line_changes_the_cache_signature(cards):
    """把 x5 的輸入從 load 改接到 x3 —— **一個參數都沒動**（兩邊都叫 ref）。

    簽章沒跟著變的話，快取會直接回舊影像：改了接線、重跑、數字沒動。
    """
    base = [Edge("load", "x3", src_out="ref", dst_in="streams")]
    a = _recipe(["load", "x3", "x5"], _branch(),
                base + [Edge("load", "x5", src_out="ref", dst_in="streams")])
    b = _recipe(["load", "x3", "x5"], _branch(),
                base + [Edge("x3", "x5", src_out="ref", dst_in="streams")])

    assert a.nodes["x5"].params == b.nodes["x5"].params, \
        "這條測試的前提是「參數完全一樣，只有線不同」"
    assert (image_segment_signature(a, "ebi_patch")[0]
            != image_segment_signature(b, "ebi_patch")[0])


def test_the_cached_run_follows_the_new_line(cards, tmp_path):
    """簽章只是手段，要的是**數字跟著線走**（帶著舊快取也一樣）。"""
    base = [Edge("load", "x3", src_out="ref", dst_in="streams"),
            Edge("x5", "m5", src_out="ref", dst_in="source")]
    route = ["load", "x3", "x5", "m5"]
    nodes = {k: v for k, v in _branch().items() if k in route}
    a = _recipe(route, nodes,
                base + [Edge("load", "x5", src_out="ref", dst_in="streams")])
    b = _recipe(route, nodes,
                base + [Edge("x3", "x5", src_out="ref", dst_in="streams")])

    cache = StageCache(str(tmp_path))
    assert run_defect_cached(a, _Item(), "ebi_patch", cache,
                             "tok").features["mean"] == 5.0
    # 1 → x3 → 3 → x5 → 15。舊快取還在，但線變了，答案就要跟著變。
    assert run_defect_cached(b, _Item(), "ebi_patch", cache,
                             "tok").features["mean"] == 15.0


def test_a_line_after_the_checkpoint_does_not_invalidate_the_image_cache(cards):
    """算法段的線改了不必重算影像 —— 過度失效等於沒有快取。"""
    a = _recipe(_ROUTE, _branch(), _BRANCH_EDGES)
    b = _recipe(_ROUTE, _branch(),
                [e for e in _BRANCH_EDGES if e.dst != "m3"]
                + [Edge("x5", "m3", src_out="ref", dst_in="source")])
    assert (image_segment_signature(a, "ebi_patch")[0]
            == image_segment_signature(b, "ebi_patch")[0])


# --------------------------------------------------------------------------- #
# 1b. 分支 + 快取：冷跑要等於熱跑（F9-10）
# --------------------------------------------------------------------------- #
def test_a_branching_recipe_gives_the_same_numbers_hot_and_cold(cards, tmp_path):
    """**同一份 recipe 跑第二次，數字不可以變。**

    快照以前只存 ``images``（名字 → 最後一個寫它的人）。分支之後同一個名字有
    好幾張圖，快照只留得下最後那張，於是熱跑時指向快取段內某個節點的線查不到，
    退回最後寫者 ＝ 隔壁那一支：``m3_mean`` 冷跑 3.0、熱跑 5.0，兩邊都跑得完。
    """
    r = _recipe(_ROUTE, _branch(), _BRANCH_EDGES)
    cache = StageCache(str(tmp_path))
    cold = run_defect_cached(r, _Item(), "ebi_patch", cache, "tok").features
    warm = run_defect_cached(r, _Item(), "ebi_patch", cache, "tok").features

    assert cold["m3_mean"] == 3.0 and cold["mean"] == 5.0
    assert warm == cold, "同一份 recipe 跑第二次算出不一樣的數字"


def test_a_stream_the_cache_did_not_keep_is_a_miss_not_a_guess(cards, tmp_path):
    """**「缺了就重算」那條防線。**

    快照只存「當時有人要的那幾張」，而「誰要」是由 checkpoint **之後**的線決定
    的 —— 那些線刻意不進簽章（不然改一下量測卡的接線就要整段重算影像）。
    所以會出現「快取有效、但這次要的那張沒存」：那時候**一定要當 miss 重算**，
    退回 ``ctx.images`` 就是安靜地拿到隔壁那一支。
    """
    a = _recipe(_ROUTE, _branch(), _BRANCH_EDGES)
    # 只把 m5 的線從 x5 改接到 x3 —— 那是算法段的線，簽章一個字都不會變
    b = _recipe(_ROUTE, _branch(),
                [e for e in _BRANCH_EDGES if e.dst != "m5"]
                + [Edge("x3", "m5", src_out="ref", dst_in="source")])
    assert (image_segment_signature(a, "ebi_patch")[0]
            == image_segment_signature(b, "ebi_patch")[0]),         "這條測試的前提是「簽章一樣」—— 不然它驗不到那條防線"

    cache = StageCache(str(tmp_path))
    assert run_defect_cached(a, _Item(), "ebi_patch", cache,
                             "tok").features["mean"] == 5.0
    assert run_defect_cached(b, _Item(), "ebi_patch", cache,
                             "tok").features["mean"] == 3.0,         "拿了快取裡沒有的那張圖去頂替 —— 應該當 miss 重算"


def test_an_unported_recipe_stores_nothing_extra(cards, tmp_path):
    """既有（沒有埠的）recipe **一張都不必多存** —— 快取大小完全沒變。

    推出來的來源就是「最後一個寫這個名字的人」，那正好等於快照裡的 `images`。
    只有真的在畫布上拉了線的地方才付這個代價。
    """
    from adept.core.pipeline.engine import _streams_needed_across_checkpoint
    from adept.core.pipeline.recipe import execution_order

    r = _recipe(_ROUTE, _branch(),
                [Edge("load", "x3"), Edge("x3", "x5"), Edge("x5", "m3")])
    order = execution_order(r, "ebi_patch")
    _sig, ckpt = image_segment_signature(r, "ebi_patch")
    assert _streams_needed_across_checkpoint(
        r, order, ckpt, REGISTRY, "ebi_patch") == set()


# --------------------------------------------------------------------------- #
# 2. 停用的卡沿線讓路（不是讓下游去吃隔壁那一支）
# --------------------------------------------------------------------------- #
def test_disabling_a_card_in_one_branch_does_not_leak_the_other_branch(cards):
    """停用 x3 → m3 應該量到 load 的 1.0（它那條線的上游），**不是 x5 的 5.0**。"""
    r = _recipe(_ROUTE, _branch(disabled=("x3",)), _BRANCH_EDGES)
    f = run_defect(r, _Item(), "ebi_patch").features
    assert f["m3_mean"] == 1.0, "停用一支的中間卡，下游吃到了另一支的資料"
    assert f["mean"] == 5.0, "另一支不該被影響"


def test_disabling_the_whole_upstream_is_a_missing_image_not_someone_elses(cards):
    """整條線的上游都關掉 = 這條線上沒有這條流 → 卡片要**報缺**。

    退回「最後一個寫這個名字的人」的話，它會安靜地拿到隔壁那一支的圖 ——
    跑得完、有數字、而且是錯的。
    """
    r = _recipe(_ROUTE, _branch(disabled=("load", "x3")), _BRANCH_EDGES)
    res = run_defect(r, _Item(), "ebi_patch")
    assert res.ok is False
    assert "ref" in str(res.error)


def test_a_straight_line_still_behaves_exactly_as_before(cards):
    """安全帶：沒有分支時，停用中間那張卡的行為**一個字都不能變**。

    這是既有 recipe 唯一會走到的形狀，而它從 F9 之前就是「跳過那張卡、
    資料直接從上游流過來」。
    """
    nodes = {"load": RecipeNode("load", "t8_load", {}),
             "x3": RecipeNode("x3", "t8_scale", {"factor": 3.0}, enabled=False),
             "m": RecipeNode("m", "t8_measure", {})}
    r = _recipe(["load", "x3", "m"], nodes,
                [Edge("load", "x3", src_out="ref", dst_in="streams"),
                 Edge("x3", "m", src_out="ref", dst_in="source")])
    assert run_defect(r, _Item(), "ebi_patch").features["mean"] == 1.0
