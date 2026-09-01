# -*- coding: utf-8 -*-
"""F55：**線的來源埠要真的存在** —— 而「有哪些埠」是畫布說了算。

健檢十天以來只問過一句話：「這個名字，上游有沒有**任何人**產出？」
（`missing-image` 拿 `avail` 這個累積的集合比對）。它從來沒問過第二句：
「**這條線指的那張卡**，右邊有沒有那顆埠？」

兩句話不一樣，而差別藏得很深：影像流在 `Context` 裡是**照名字**查的，所以
一條指著不存在的埠、標著 `ref` 的線，執行期會安靜地拿到**別張卡**的 `ref`。
跑得完、有數字，而且**數字是對的** —— 只有畫布在說謊。

⚠ 這一支最重要的一段是**它第一版錯在哪**（2026-08-28 同一輪寫的、同一輪
發現的）。第一版拿 `Step.resolve_writes` 當「那張卡有哪些輸出埠」，於是它對
一條**完全正確**的線報錯：使用者那份 recipe 裡有

    ["roi_reference", "ref", "glv_stats", "reference_source"]

而 `roi_reference` 的 `resolve_writes` 是空的（它只產出區域）。看起來像是
一條指著不存在的埠的線 —— 但畫布上那顆 `ref` 埠**真的在**：F9-6「同進同出」
規定接進來的每一條流卡片後面也要接得出去（`writes` ＋ 原樣送出的 `reads`；
區域同理，見 `RecipeModel.region_outputs`），而引擎那邊本來就成立
（`produced[(節點, 名字)]` 是從那張卡的 local Context 收的，輸入本來就在
裡面）。

> **要問「畫布有沒有說謊」，就得用畫布的定義去問。** 拿引擎某一支宣告的
> 定義去問，量到的是兩邊的差別本身 —— 而那個差別正好是這條 lint 要守的
> 東西。第一版的誤報不是邊界沒想到，是**問錯了問題**。

所以下面的第一組測試（會報的那些）用的是**真的不存在**的埠，而第二組
（不准報的那些）第一條就是使用者那份 recipe 的形狀。
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
        edges=[Edge(*e) for e in edges])       # Edge(src, dst, src_out, dst_in)


def _issues(recipe, code="port-not-produced"):
    return [i for i in validate(recipe, "ebi_patch") if i.code == code]


LOAD = ("load", "load_patch", {"channel_map": "1:test, 2:ref"})
DENOISE = ("den", "denoise", {"streams": "test,ref", "method": "gaussian"})
FOCUS = ("focus", "focus_quality", {"source": "test"})
GLV_REF = ("glv", "glv_stats", {"source": "test",
                                "reference_source": "ref"})
WIRED = [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "focus", "test", "source"),
         ("den", "glv", "test", "source")]


# --------------------------------------------------------------------------- #
# 1. 真的不存在的埠
# --------------------------------------------------------------------------- #
def test_a_wire_from_a_stream_the_card_never_sees_is_a_warning():
    """`focus` 只讀 `test` —— 它右邊沒有 `ref`，那條線指著空氣。"""
    r = _recipe([LOAD, DENOISE, FOCUS, GLV_REF],
                WIRED + [("focus", "glv", "ref", "reference_source")])
    got = _issues(r)
    assert len(got) == 1, [i.code for i in validate(r, "ebi_patch")]
    assert got[0].level == "warning"          # 結果是對的 → 不擋
    assert got[0].node_id == "glv"            # 徽章掛在**收到**那條線的卡上
    detail = got[0].detail
    assert "ref" in detail and "focus" in detail
    assert "still runs" in detail             # 要講「它還是會跑」
    assert "“test”" in detail                 # 也要講它**真的有**哪一顆


def test_a_region_wire_from_a_card_with_no_region_port_is_a_warning():
    r = _recipe([LOAD, DENOISE, FOCUS,
                 ("glv", "glv_stats", {"source": "test", "roi": "epi"})],
                WIRED + [("focus", "glv", "epi", "roi")])
    got = _issues(r)
    assert len(got) == 1
    assert "region" in got[0].detail
    assert "diamond" in got[0].detail          # 區域埠是菱形，講對形狀


def test_re_pointing_the_wire_at_a_card_that_has_the_port_clears_it():
    """**反向**：唯一的差別是那條線的來源。"""
    r = _recipe([LOAD, DENOISE, FOCUS, GLV_REF],
                WIRED + [("den", "glv", "ref", "reference_source")])
    assert validate(r, "ebi_patch") == []


# --------------------------------------------------------------------------- #
# 2. 不准誤報
# --------------------------------------------------------------------------- #
def test_a_pass_through_port_is_a_real_port():
    """**第一版就是死在這一條。** 使用者那份 recipe 的形狀，一個字都不准說。

    `roi_reference` 一條影像流都不產出（`resolve_writes` 是空的），但它
    **讀** `ref` —— F9-6「同進同出」讓那條流從它右邊接得出去，而引擎的
    `produced[(節點, 名字)]` 是從那張卡的 local Context 收的，輸入本來就在
    裡面。這條線是對的。
    """
    r = _recipe(
        [LOAD, DENOISE,
         ("roi", "roi_reference", {"source": "ref", "roi_out": "region",
                                   "method": "a cell I mark myself"}),
         ("glv", "glv_stats", {"source": "test",
                               "reference_source": "ref"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "roi", "ref", "source"),
         ("den", "glv", "test", "source"),
         ("roi", "glv", "ref", "reference_source")])   # ← 原樣送出的那顆
    assert _issues(r) == []


def test_a_pass_through_region_port_is_a_real_port():
    """區域同理（F12 第二輪：「區域線應該也要 follow 圖像線一樣，前進後出」）。"""
    r = _recipe(
        [LOAD, DENOISE,
         ("roi", "roi_define", {"roi_out": "epi"}),
         ("a", "glv_stats", {"source": "test", "roi": "epi",
                             "output_prefix": "a"}),
         ("b", "glv_stats", {"source": "test", "roi": "epi",
                             "output_prefix": "b"})],
        [("load", "den", "test", "streams"),
         ("load", "den", "ref", "streams"),
         ("den", "a", "test", "source"),
         ("den", "b", "test", "source"),
         ("roi", "a", "epi", "roi"),
         ("a", "b", "epi", "roi")])            # ← 第二張接第一張原樣送出的
    assert _issues(r) == []


def test_an_ordinary_recipe_says_nothing():
    r = _recipe([LOAD, DENOISE, FOCUS], WIRED[:3])
    assert validate(r, "ebi_patch") == []


def test_a_wire_with_no_ports_is_only_an_ordering_hint():
    """埠空著的線只表達先後順序（見 `Edge`）—— 這裡沒有埠可以檢查。"""
    r = _recipe([LOAD, DENOISE, FOCUS], WIRED[:3] + [("den", "focus")])
    assert _issues(r) == []


def test_a_disabled_source_card_is_left_alone():
    """停用的卡不跑，它的宣告也就不算數 —— 對它報一條只是噪音。"""
    r = _recipe([LOAD, DENOISE, FOCUS, GLV_REF],
                WIRED + [("focus", "glv", "ref", "reference_source")])
    assert _issues(r)                          # 先確定這份**本來**會報
    r.nodes["focus"].enabled = False
    assert _issues(r) == []


def test_a_card_with_no_source_yet_is_left_to_not_connected():
    """還沒接上東西的卡在畫布上前後都是空的 —— 那件事 `not-connected` 在講。"""
    r = _recipe([LOAD, DENOISE, ("dn2", "denoise", {"streams": "", "method": "gaussian"}),
                 GLV_REF],
                [("load", "den", "test", "streams"),
                 ("load", "den", "ref", "streams"),
                 ("den", "glv", "test", "source"),
                 ("dn2", "glv", "ref", "reference_source")])
    codes = [i.code for i in validate(r, "ebi_patch")]
    assert "not-connected" in codes
    assert "port-not-produced" not in codes    # 不要疊第二句話


def test_the_load_card_keeps_its_kind_dependent_ports():
    """load 卡的產出**依資料型別而定** —— 取聯集，不要對別條 route 的線報錯。

    沒有這一段的話，一份同時定義 `ebi_patch` 與 `rsem` 兩條 route 的 recipe
    會在 rsem 那條上被說「load 沒有 ref」（單張影像的 rsem 沒有 ref），
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
