# -*- coding: utf-8 -*-
"""F57：撞名這句話要**看得見有沒有人在讀那個名字**，而且要對兩張卡講。

`feature-collision` 一直都在（F7-11），而 F51 §6 把「要不要讓它變吵」留給
使用者。這一輪定調了。**變吵的方式不是升級別** —— 是把兩件說不通的事修好：

① **同樣一次撞名，句子對兩種處境逐字相同。** 判定樹正拿 `glv_max` 問問題，
   跟沒有人讀它，是兩種處境；而舊訊息甚至在沒有人讀的時候也宣稱
   「`glv_max` 在分數表達式裡指的是這張卡」。
② **只有後面那張卡拿得到訊息。** 而畫面上真正說不通的是**前**面那張：
   它的 `glv_median` 從此叫 `a_glv_median`，它自己那張卡上一個字都沒有。

⚠ **兩件事這一輪特意**沒有**做，理由都是量過的**：

* **不升成 error。** 判準寫在 `_region_collisions` 上：差別不是嚴重程度，
  是「有沒有第二條路拿得到被蓋掉的那一份」。特徵有（引擎救成
  `<節點名>_<特徵>`），區域沒有。
* **兩邊都是診斷數字仍然完全不講。** 第一版把它降成 `info`（「不畫琥珀點，
  但寫下來」）—— 而 `info` 一樣進卡片的 tooltip，於是
  `test_the_reference_recipes_stay_completely_clean` 紅了。**那條測試鎖的
  「每一份正常的 recipe 一條訊息都沒有」是一個有人選過的不變量**，
  換成「每一份都多兩行不痛不癢的話」就是把它丟掉。
"""
from __future__ import annotations

import pytest

from d4t.core.pipeline.recipe import (
    DecideSpec, Edge, Let, Recipe, RecipeNode, ScoreSpec, TreeLeaf, TreeStep,
    referenced_features, validate,
)
import d4t.core.steps  # noqa: F401 - 註冊卡片


LOAD = ("load", "load_patch", {"channel_map": "1:test, 2:ref"})
DEN = ("den", "denoise", {"streams": "test,ref", "method": "gaussian"})
WIRES = [("load", "den", "test", "streams"), ("load", "den", "ref", "streams"),
         ("den", "a", "test", "source"), ("den", "b", "ref", "source")]


def _two_measure(expr="0", decide=None, metrics="glv_max"):
    """兩張都吐 `glv_max` 的量測卡 —— 最短的撞名。"""
    nodes = [LOAD, DEN,
             ("a", "glv_stats", {"source": "test", "metrics": metrics}),
             ("b", "glv_stats", {"source": "ref", "metrics": metrics})]
    return Recipe(
        recipe_id="t", routes={"ebi_patch": [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2])) for n in nodes},
        score=ScoreSpec(expr=expr, threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="", decide=decide,
        edges=[Edge(*e) for e in WIRES])


def _of(recipe, code):
    return [i for i in validate(recipe, "ebi_patch") if i.code == code]


# --------------------------------------------------------------------------- #
# 1. 有沒有人在讀那個名字
# --------------------------------------------------------------------------- #
def test_it_says_so_when_the_decision_is_the_one_reading_the_name():
    got = _of(_two_measure(expr="glv_max"), "feature-collision")
    assert len(got) == 1
    d = got[0].detail
    assert "the decision reads 'glv_max'" in d
    assert "'a' first, then 'b'" in d          # 誰先誰後要講出來
    assert "a_glv_max" in d                    # 想要前面那張的話打什麼


def test_it_says_nothing_reads_it_when_nothing_does():
    got = _of(_two_measure(expr="0"), "feature-collision")
    assert len(got) == 1
    d = got[0].detail
    assert "Nothing reads 'glv_max'" in d
    # 舊訊息在這個情況下也宣稱「在分數表達式裡指的是這張卡」——**那是假的**
    assert "in the score expression means" not in d


def test_a_decision_tree_counts_as_reading_it():
    """走判定樹的 recipe 沒有 `score.expr` —— 名字住在樹的問句裡。"""
    tree = TreeStep(when="glv_max > 3",
                    yes=TreeLeaf(bin=1, label="a"), no=TreeLeaf(bin=2, label="b"))
    r = _two_measure(expr="", decide=DecideSpec(let=[], tree=tree))
    got = _of(r, "feature-collision")
    assert len(got) == 1
    assert "the decision reads 'glv_max'" in got[0].detail


def test_a_working_number_counts_as_reading_it():
    """`let` 那幾行也是讀 —— 判定樹常常只問 `let` 算出來的名字。"""
    tree = TreeStep(when="m > 0", yes=TreeLeaf(bin=1, label="a"),
                    no=TreeLeaf(bin=2, label="b"))
    r = _two_measure(expr="",
                     decide=DecideSpec(let=[Let(name="m", expr="glv_max * 2")],
                                       tree=tree))
    assert "the decision reads 'glv_max'" in _of(r, "feature-collision")[0].detail


# --------------------------------------------------------------------------- #
# 2. 被蓋掉的那一張卡
# --------------------------------------------------------------------------- #
def test_the_card_that_lost_the_name_is_told_what_its_number_is_called_now():
    got = _of(_two_measure(), "feature-renamed")
    assert len(got) == 1
    assert got[0].node_id == "a"               # **前**面那張
    assert got[0].level == "info"              # 不畫第二顆琥珀點
    assert "a_glv_max" in got[0].detail


def test_three_cards_rename_down_the_chain():
    """a → a_f、b → b_f、c 留住裸名 —— 每一段都要有人講。"""
    nodes = [LOAD, DEN] + [
        (n, "glv_stats", {"source": "test", "metrics": "glv_max"})
        for n in ("a", "b", "c")]
    r = Recipe(
        recipe_id="t", routes={"ebi_patch": [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2])) for n in nodes},
        score=ScoreSpec(expr="0", threshold=0.0, bins={"below": 0, "above": 1}),
        version=2, author="unit", description="",
        edges=[Edge("load", "den", "test", "streams"),
               Edge("load", "den", "ref", "streams")]
        + [Edge("den", n, "test", "source") for n in ("a", "b", "c")])
    renamed = {(i.node_id, "b_glv_max" in i.detail, "a_glv_max" in i.detail)
               for i in _of(r, "feature-renamed")}
    assert ("a", False, True) in renamed       # a 被 b 蓋 → a_glv_max
    assert ("b", True, False) in renamed       # b 被 c 蓋 → b_glv_max


# --------------------------------------------------------------------------- #
# 3. 沒有變的那兩件事（各一條反向測試）
# --------------------------------------------------------------------------- #
def test_it_is_still_a_warning_even_when_the_decision_reads_it():
    """不擋 —— 被蓋掉的值救得回來（`_region_collisions` 的判準）。"""
    assert _of(_two_measure(expr="glv_max"), "feature-collision")[0].level \
        == "warning"


def test_two_diagnostic_numbers_still_say_absolutely_nothing():
    """`glv_pixels` 是診斷數字，兩張 GLV 卡必然撞它 —— 一條訊息都不准有。

    這是 F57 第一版真的踩到的：把它降成 `info` 讓
    `test_the_reference_recipes_stay_completely_clean` 紅了。
    """
    r = _two_measure(metrics="glv_max")        # glv_pixels 一定跟著出來
    for i in validate(r, "ebi_patch"):
        assert "glv_pixels" not in i.detail, i.detail


# --------------------------------------------------------------------------- #
# 4. `referenced_features` 自己
# --------------------------------------------------------------------------- #
def test_referenced_features_ignores_a_broken_expression():
    """語法錯有自己那條 lint —— 在這裡再炸一次會蓋掉別的檢查。"""
    assert referenced_features(_two_measure(expr="glv_max +")) == set()


def test_referenced_features_skips_blank_let_lines():
    """空白的 working number 當成沒填（F53）—— 這裡也要一致。"""
    r = _two_measure(expr="", decide=DecideSpec(
        let=[Let(name="", expr=""), Let(name="m", expr="glv_max")],
        tree=TreeStep(when="m > 0", yes=TreeLeaf(bin=1, label="a"),
                      no=TreeLeaf(bin=2, label="b"))))
    assert referenced_features(r) == {"glv_max", "m"}
