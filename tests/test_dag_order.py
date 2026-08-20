# F17-①：執行順序只有一個家 —— 線。
"""在此之前 `execution_order` 把 **route 上相鄰的每一對**也當成一條邊：

    for a, b in zip(route, route[1:]):     # 沒有人拉過的線
        pair_edges.add((a, b))

那串隱含邊構成一條走遍全部節點的鏈，所以執行順序**恆等於 route 順序** ——
而 route 順序在畫布上就是卡片的左右位置。於是**兩張沒有任何線相連的卡，誰先跑
由使用者把它拖到哪裡決定**，而畫面上完全看不出來。

鐵則 9 那句「資料從哪來由線決定，而畫布上每一條線都是使用者拉的」是真的，
但**執行順序的邊有一半不是線**：UI 照純 DAG 畫，引擎不照純 DAG 跑。

這一份鎖住的是拿掉之後的四條性質：

1. 沒有線的時候，順序仍然是 route 順序（**既有 recipe 一個字都不會變**）；
2. 有線的時候，**線說了算** —— 包括線與 route 順序相反的那種（今天是 cycle）；
3. **拖動卡片不改變有線那幾張卡的相對順序**（這一條是這一輪真正買到的東西）；
4. 自迴圈與真正的循環仍然報得出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeError, RecipeNode, ScoreSpec, execution_order,
)

KIND = "ebi_patch"


def _recipe(order, edges=()):
    """`order` 是 route 的排列；`edges` 是使用者拉的線。"""
    return Recipe(
        recipe_id="t", routes={KIND: list(order)},
        edges=[Edge(*e) if not isinstance(e, Edge) else e for e in edges],
        nodes={n: RecipeNode(n, "glv_stats",
                             {"source": "test", "metrics": "glv_mean"})
               for n in order},
        score=ScoreSpec(expr="glv_mean", threshold=1.0, bins={}))


# --------------------------------------------------------------------------- #
# 1. 沒有線 → 順序仍然是 route 順序（既有 recipe 不會變）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("order", [
    ["a", "b", "c"],
    ["c", "b", "a"],
    ["load", "norm", "align", "glv"],
])
def test_with_no_lines_the_order_is_still_the_route_order(order):
    """**這一條是「敢動」的理由。**

    手寫的 recipe（測試 fixture 裡就有幾份）一條 `edges` 都沒有，全靠隱含邊
    在跑。拿掉隱含邊之後它們照樣按原順序跑 —— 因為 route 位置仍然是 Kahn 的
    平手依據。黃金值因此一個數字都不會動。
    """
    assert execution_order(_recipe(order), KIND) == order


# --------------------------------------------------------------------------- #
# 2. 有線 → 線說了算
# --------------------------------------------------------------------------- #
def test_a_line_that_runs_against_the_route_order_now_wins():
    """route 排 [a, b]、線卻是 b → a。

    **今天這是 cycle**（隱含邊 a→b ＋ 線 b→a），一份完全合理的 recipe 開不
    起來。拿掉隱含邊之後它照線跑 —— 而那正是「資料從哪來由線決定」的意思。
    """
    order = execution_order(_recipe(["a", "b"], [("b", "a")]), KIND)
    assert order == ["b", "a"]


def test_lines_order_the_cards_they_touch():
    order = execution_order(
        _recipe(["a", "b", "c"], [("c", "a"), ("a", "b")]), KIND)
    assert order.index("c") < order.index("a") < order.index("b")


# --------------------------------------------------------------------------- #
# 3. 拖動卡片不改變有線那幾張的相對順序（這一輪買到的東西）
# --------------------------------------------------------------------------- #
def test_moving_a_card_does_not_change_what_the_lines_say():
    """同一組線，route 的排列換三種 —— 有線那幾張的先後**一次都不能變**。

    以前每換一種排列就換一種執行順序（route 相鄰對是邊），所以「把卡片往左拖
    一格」是一個會改變分數的動作，而畫布上沒有任何東西提示這件事。
    """
    lines = [("load", "norm"), ("norm", "glv")]
    for order in (["load", "norm", "glv", "solo"],
                  ["solo", "load", "norm", "glv"],
                  ["load", "solo", "norm", "glv"],
                  ["glv", "norm", "load", "solo"]):
        got = execution_order(_recipe(order, lines), KIND)
        assert got.index("load") < got.index("norm") < got.index("glv"), order


def test_an_unconnected_card_still_has_a_deterministic_place():
    """沒有線的那張卡仍然要有一個**固定**的位置（不能每次跑都不一樣）——
    否則 `workers=1` 與 `workers=2` 會算出不同的東西（鐵則 9 的那個坑）。"""
    lines = [("load", "glv")]
    a = execution_order(_recipe(["load", "solo", "glv"], lines), KIND)
    b = execution_order(_recipe(["load", "solo", "glv"], lines), KIND)
    assert a == b == ["load", "solo", "glv"]


# --------------------------------------------------------------------------- #
# 4. 循環仍然報得出來
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("edges", [
    [("a", "a")],                       # 自迴圈
    [("a", "b"), ("b", "a")],           # 兩張互指
    [("a", "b"), ("b", "c"), ("c", "a")],
])
def test_a_real_cycle_is_still_an_error(edges):
    with pytest.raises(RecipeError) as e:
        execution_order(_recipe(["a", "b", "c"], edges), KIND)
    assert "cycle" in str(e.value)


def test_an_unknown_kind_says_which_ones_exist():
    with pytest.raises(RecipeError) as e:
        execution_order(_recipe(["a"]), "rsem")
    assert KIND in str(e.value)
