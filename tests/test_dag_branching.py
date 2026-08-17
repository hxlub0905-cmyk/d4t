# F9-5a 驗收：同一條流分岔成兩支互不干擾的支線 — authored 2026-08-16.
"""**這是整個 F9 要換來的東西。**

F9 之前影像流的身分是「一個全域的名字」，所以兩條分支各自處理 ``ref`` 時，
寫回的是同一個格子 —— 後寫的蓋掉先寫的，結果不是分支是**串聯**：

    ref ─┬─ denoise A (ksize=3) ─▶ 寫回 ref
         └─ denoise B (ksize=9) ─▶ 寫回 ref     ← 蓋掉 A，而且 B 吃的是 A 的輸出

F9-5a 之後身分是 ``(哪個節點, 哪個輸出埠)``，所以 ``(dn_soft, "ref")`` 與
``(dn_hard, "ref")`` 是兩份不同的東西，兩支互不干擾。

**線沒有明講埠的時候，語意跟 F9 之前逐位元組相同**（照「執行順序上最後一個寫
這條流的人」推）—— 那是這一段敢動資料流的唯一理由，也是下面第一條測試在鎖的事。
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

_KEYS = ["t_br_load", "t_br_scale", "t_br_measure"]


@pytest.fixture()
def cards():
    """三張最小卡片：載入 → 乘一個常數 → 量平均值。

    用假卡片而不是真的 denoise/glv_stats：這一支要驗的是**資料往哪走**，
    不是某個演算法算得對不對。乘法讓「這一支到底吃到誰的輸出」一眼看得出來。
    """
    for k in _KEYS:
        REGISTRY.pop(k, None)

    @register_step
    class TBrLoad(Step):
        key = "t_br_load"
        label = "載入"
        category = CATEGORY_IMAGE
        help = "測試用：寫一條值全是 1 的 ref"
        writes = ["ref"]

        def run(self, ctx: Context, params) -> Context:
            ctx.set_image("ref", np.ones((4, 4), np.float32))
            return ctx

    @register_step
    class TBrScale(Step):
        key = "t_br_scale"
        label = "乘一個數"
        category = CATEGORY_IMAGE
        help = "測試用：把指定的流乘上 factor，就地寫回同一條流"
        # 參數形狀刻意跟真的 Enhance 卡一樣（``streams`` 是 image_keys）——
        # 邊綁的是**參數名**，所以假卡片沒有這個參數的話就測不到綁定。
        params = [ParamSpec("streams", "image_keys", "ref", "要處理的影像流"),
                  ParamSpec("factor", "float", 2.0, "乘數")]

        @classmethod
        def resolve_reads(cls, params):
            return [s.strip() for s in str(params.get("streams", "")).split(",")
                    if s.strip()]

        resolve_writes = resolve_reads     # 就地改寫：寫出去的等於接進來的

        def run(self, ctx: Context, params) -> Context:
            for name in self.resolve_reads(params):
                ctx.set_image(name,
                              ctx.require_image(name) * float(params["factor"]))
            return ctx

    @register_step
    class TBrMeasure(Step):
        key = "t_br_measure"
        label = "量平均"
        category = CATEGORY_ALGO
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


def _nodes():
    return {
        "load": RecipeNode("load", "t_br_load", {}),
        "x3": RecipeNode("x3", "t_br_scale", {"factor": 3.0}),
        "x5": RecipeNode("x5", "t_br_scale", {"factor": 5.0}),
        "m3": RecipeNode("m3", "t_br_measure", {}),
        "m5": RecipeNode("m5", "t_br_measure", {}),
    }


ROUTE = ["load", "x3", "x5", "m3", "m5"]


def _run(edges):
    rec = Recipe(recipe_id="branching",
                 routes={"ebi_patch": ROUTE},
                 nodes=_nodes(),
                 edges=list(edges),
                 score=ScoreSpec("0", 0.0, {"below": 0, "above": 1}))
    r = run_defect(rec, object(), "ebi_patch")
    assert r.ok, r.error
    return r.features


def test_without_explicit_ports_it_still_chains_exactly_like_before(cards):
    """埠沒填 = 舊語意：後面那張吃前面那張的輸出，兩張量測卡量到同一個值。

    這條是 F9-5a 的安全帶。UI 目前拉出來的線就是這種（F9-5b 才會帶埠），
    所以它一旦破，**每一份既有 recipe 的分數都會變**。
    """
    f = _run([])
    # 1 → x3 → 3 → x5 → 15；兩張量測卡看到的都是最後那份
    assert f["mean"] == 15.0
    assert f["m3_mean"] == 15.0, "串聯時兩張量測卡量到的是同一個值"


def test_two_branches_off_the_same_stream_do_not_touch_each_other(cards):
    """**F9 的目的**：同一條 ref 分岔成兩支，各做各的，互不干擾。

    load 的 ref 同時餵給 x3 與 x5（都從 load 分岔，不是串起來），
    然後每支各自被量。
    """
    f = _run([
        Edge("load", "x3", src_out="ref", dst_in="streams"),
        Edge("load", "x5", src_out="ref", dst_in="streams"),
        Edge("x3", "m3", src_out="ref", dst_in="source"),
        Edge("x5", "m5", src_out="ref", dst_in="source"),
    ])
    # x5 那支：1 × 5 = 5（**不是** 15 —— 它沒有吃到 x3 的輸出）
    assert f["mean"] == 5.0, "x5 這支吃到了 x3 的輸出，分支沒有成立"
    # x3 那支：1 × 3 = 3
    assert f["m3_mean"] == 3.0, "x3 這支的值不對"


def test_a_branch_can_be_measured_without_disturbing_the_other(cards):
    """兩支的數字必須不同 —— 相同就代表它們其實還是同一條流。

    分開寫一條，是因為上一條就算兩邊都錯成同一個值也可能碰巧通過某些斷言；
    「兩支不一樣」是這件事最直接的證據。
    """
    f = _run([
        Edge("load", "x3", src_out="ref", dst_in="streams"),
        Edge("load", "x5", src_out="ref", dst_in="streams"),
        Edge("x3", "m3", src_out="ref", dst_in="source"),
        Edge("x5", "m5", src_out="ref", dst_in="source"),
    ])
    assert f["m3_mean"] != f["mean"], "兩支量到一樣的值 = 還是同一條流"


def test_an_explicit_edge_beats_the_one_that_merely_comes_before(cards):
    """明講的線贏過「剛好排在前面的那張卡」。

    這是使用者在畫布上拉線的意義：**我要的是這一條**，不是「執行順序上最近的
    那一條」。沒有這條規則，畫布上的線就只是裝飾。
    """
    f = _run([
        # m5 明講要吃 x3 的輸出，即使 x5 排在它前面而且也寫 ref
        Edge("x3", "m5", src_out="ref", dst_in="source"),
    ])
    assert f["mean"] == 3.0, "m5 沒有吃到它明講的那條線（x3 的輸出）"
