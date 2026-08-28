# -*- coding: utf-8 -*-
"""F55：**線的來源埠要真的存在。**

健檢十天以來只問過一句話：「這個名字，上游有沒有**任何人**產出？」
（`missing-image` 拿 `avail` 這個累積的集合比對）。它從來沒問過第二句：
「**這條線指的那張卡**，產不產出它？」

兩句話不一樣，而差別藏得很深：影像流在 `Context` 裡是**照名字**查的，所以
一條從「一張影像都不產出的卡」拉出來、標著 `ref` 的線，執行期會安靜地拿到
**別張卡**的 `ref`。跑得完、有數字，而且**數字是對的** —— 只有畫布在說謊。

這一支是踩出來的。2026-08-28 使用者帶了一份真實 recipe 進來，裡面有
``["roi_reference", "ref", "glv_stats", "reference_source"]``，而
`roi_reference` 的 `resolve_writes` 是空的（它只產出區域）。當時的健檢
**零條訊息**。把來源改成真正產出 `ref` 的那張卡之後，兩份 CSV 逐位元組相同
—— 也就是說這條線今天不痛，但畫面上它指著錯的地方，而下一個人會照著那條線
去理解資料從哪來（鐵則 9）。

所以這一支要守的不是「會不會算錯」，是**畫布不能說謊**。
"""
from __future__ import annotations

import pytest

from d4t.core.pipeline.recipe import (
    Edge, Recipe, RecipeNode, ScoreSpec, validate,
)
import d4t.core.steps  # noqa: F401 - 註冊卡片


def _recipe(nodes, edges, kind: str = "ebi_patch") -> Recipe:
    return Recipe(
        recipe_id="port_test",
        routes={kind: [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2])) for n in nodes},
        score=ScoreSpec(expr="0", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="lint",
        edges=[Edge(*e) for e in edges])


def _issues(recipe, code="port-not-produced"):
    return [i for i in validate(recipe, "ebi_patch") if i.code == code]


LOAD = ("load", "load_patch", {"channel_map": "1:test, 2:ref"})
DENOISE = ("den", "denoise", {"streams": "test,ref", "method": "gaussian"})
FOCUS = ("focus", "focus_quality", {"source": "test"})


# --------------------------------------------------------------------------- #
# 1. 使用者那份 recipe 的形狀
# --------------------------------------------------------------------------- #
def test_a_wire_from_a_card_that_makes_no_images_is_a_warning():
    """量測卡不產出影像流 —— 從它拉一條 `test` 出來就是一句謊話。"""
    r = _recipe(
        [LOAD, DENOISE, FOCUS,
         ("glv", "glv_stats", {"source": "test", "reference": "another stream",
                               "reference_source": "ref"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "glv", "test", "source"),
         # ↓ 這條就是那個形狀：focus_quality 一張影像都不產出
         ("focus", "glv", "ref", "reference_source")])
    got = _issues(r)
    assert len(got) == 1, [i.code for i in validate(r, "ebi_patch")]
    assert got[0].level == "warning"          # 結果是對的 → 不擋
    assert got[0].node_id == "glv"            # 徽章掛在**收到**那條線的卡上
    # 訊息要講出三件事：哪個名字、哪張卡、以及「它其實還是會跑」
    detail = got[0].detail
    assert "ref" in detail and "focus" in detail
    assert "still runs" in detail


def test_re_pointing_the_same_wire_at_the_real_producer_clears_it():
    """**反向**：唯一的差別是那條線的來源，而它就是修法。"""
    r = _recipe(
        [LOAD, DENOISE, FOCUS,
         ("glv", "glv_stats", {"source": "test", "reference": "another stream",
                               "reference_source": "ref"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "glv", "test", "source"),
         ("den", "glv", "ref", "reference_source")])
    assert _issues(r) == []
    assert validate(r, "ebi_patch") == []


# --------------------------------------------------------------------------- #
# 2. 區域線走同一條路
# --------------------------------------------------------------------------- #
def test_a_region_wire_from_a_card_that_defines_no_region_is_a_warning():
    r = _recipe(
        [LOAD, DENOISE, FOCUS,
         ("glv", "glv_stats", {"source": "test", "roi": "epi"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "glv", "test", "source"),
         ("focus", "glv", "epi", "roi")])      # focus 不定義任何區域
    got = _issues(r)
    assert len(got) == 1
    assert "region" in got[0].detail
    assert "diamond" in got[0].detail          # 區域埠是菱形，講對形狀


# --------------------------------------------------------------------------- #
# 3. 不准誤報的三種線
# --------------------------------------------------------------------------- #
def test_an_ordinary_recipe_says_nothing():
    r = _recipe(
        [LOAD, DENOISE, FOCUS],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source")])
    assert validate(r, "ebi_patch") == []


def test_a_wire_with_no_ports_is_only_an_ordering_hint():
    """埠空著的線只表達先後順序（見 `Edge`）—— 這裡沒有埠可以檢查。"""
    r = _recipe(
        [LOAD, DENOISE, FOCUS],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "focus")])                    # Edge(src, dst)：兩個埠都空
    assert _issues(r) == []


def test_a_disabled_source_card_is_left_alone():
    """停用的卡不跑，它的宣告也就不算數 —— 對它報一條只是噪音。"""
    r = _recipe(
        [LOAD, DENOISE, FOCUS,
         ("glv", "glv_stats", {"source": "test", "reference": "another stream",
                               "reference_source": "ref"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "glv", "test", "source"),
         ("focus", "glv", "ref", "reference_source")])
    assert _issues(r)                          # 先確定這份**本來**會報
    r.nodes["focus"].enabled = False
    assert _issues(r) == []


def test_the_load_card_keeps_its_kind_dependent_ports():
    """load 卡的產出**依資料型別而定** —— 取聯集，不要對別條 route 的線報錯。

    沒有這一段的話，一份同時定義 `ebi_patch` 與 `rsem` 兩條 route 的 recipe
    會在 rsem 那條上被說「load 不產出 ref」（單張影像的 rsem 沒有 ref），
    而那條線在 ebi_patch 上完全正確。
    """
    r = Recipe(
        recipe_id="port_test",
        routes={"ebi_patch": ["load", "den"], "rsem": ["load", "den"]},
        nodes={"load": RecipeNode("load", "load_patch",
                                  {"channel_map": "1:test, 2:ref"}),
               "den": RecipeNode("den", "denoise",
                                 {"streams": "test", "method": "gaussian"})},
        score=ScoreSpec(expr="0", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="lint",
        edges=[Edge("load", "den", "ref", "streams")])
    assert [i for i in validate(r) if i.code == "port-not-produced"] == []
