# -*- coding: utf-8 -*-
"""v1（區域存在**參數**裡）→ v2（存在**線**裡）（F42 方案 B 的 B3）。

判準是**版本號**
----------------
``version < RECIPE_VERSION`` 才跑，跑完寫成 ``RECIPE_VERSION``。
**不是**「有參數但沒有線」—— 那是鐵則 9 明文禁止的「靠新東西不在判斷」，
而這個 repo 為它付過一次 ``workers=1`` 與 ``workers=2`` 算出不同分數的錢
（`docs/ROADMAP.md` Phase 1 的第一列）。

四種情形，每一種一條測試
------------------------
① 上游找得到 → 補線。
② 指到一個沒有人產出的名字 → 不補線，**那個字留著**（`unknown-region`
   才問得到它）。
③ 產出它的那張卡排在**下游** → **補線**，順序因此被排對 ——
   一個**刻意的行為改變**，見 `_migrate_region_params_into_edges` 的說明。
④ 補上去會**成環** → 不補，由 `region-has-no-line` 講出來。
   一份今天跑得動的 recipe 不可以因為遷移而打不開。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import (  # noqa: E402
    RECIPE_VERSION, Recipe, execution_order, is_region_edge, validate,
)

KIND = "rsem"


def _doc(route, glv_roi="epi", version=1, edges=None, nodes=None):
    """`load_single → load_sidecar → roi_reference(GDS) → glv_stats` 的 v1 檔。"""
    base = {
        "load": {"step": "load_single", "params": {"out": "test"}},
        "lbl": {"step": "load_sidecar", "params": {}},
        "roi": {"step": "roi_reference",
                "params": {"method": "layout layers", "layers": "1:epi",
                           "label_source": "layout_label"}},
        "glv": {"step": "glv_stats",
                "params": {"source": "test", "roi": glv_roi}},
    }
    base.update(nodes or {})
    return {"recipe_id": "t", "version": version,
            "routes": {KIND: list(route)},
            "nodes": {n: base[n] for n in route},
            "edges": list(edges if edges is not None
                          else [["load", "test", "glv", "source"]]),
            "score": {"expr": "1", "threshold": 0.0,
                      "bins": {"below": 0, "above": 1}}}


def _region_edges(rec):
    return [e for e in rec.edges if is_region_edge(e, rec.nodes)]


def _codes(rec):
    return [i.code for i in validate(rec, kind=KIND)]


UPSTREAM = ["load", "lbl", "roi", "glv"]
DOWNSTREAM = ["load", "lbl", "glv", "roi"]      # Region 卡在量測卡右邊


# --------------------------------------------------------------------------- #
# ① 上游找得到 → 補線
# --------------------------------------------------------------------------- #
def test_an_old_recipe_gets_a_real_edge():
    rec = Recipe.from_json_dict(_doc(UPSTREAM))
    assert rec.version == RECIPE_VERSION
    assert [(e.src, e.src_out, e.dst, e.dst_in) for e in _region_edges(rec)] \
        == [("roi", "epi", "glv", "roi")]
    # 那一格的值一個字都沒變（線推回來的）。
    assert rec.nodes["glv"].params["roi"] == "epi"
    assert not [c for c in _codes(rec) if c == "unknown-region"]


def test_the_migrated_recipe_still_writes_the_parameter_out_of_the_edge():
    """遷移完之後那一格是**線管的**，所以 JSON 裡不再寫它（B2 §序列化）。"""
    rec = Recipe.from_json_dict(_doc(UPSTREAM))
    doc = rec.to_json_dict()
    assert "roi" not in doc["nodes"]["glv"]["params"]
    assert ["roi", "epi", "glv", "roi"] in doc["edges"]
    assert doc["version"] == RECIPE_VERSION


def test_the_round_trip_after_migrating_is_identity():
    """鐵則 9：``to_json_dict → from_json_dict`` 是 `run_batch` 送進 worker
    的路。遷移過的 recipe 在那條路上再跑一次遷移的話，版本號會再動一次 ——
    所以遷移必須**跑第二次是 no-op**，而版本號就是那個保證。"""
    rec = Recipe.from_json_dict(_doc(UPSTREAM))
    d = rec.to_json_dict()
    again = Recipe.from_json_dict(json.loads(json.dumps(d)))
    assert again.edges == rec.edges
    assert again.nodes["glv"].params == rec.nodes["glv"].params
    assert again.to_json_dict() == d


def test_a_recipe_already_on_the_new_version_is_left_alone():
    """**判準是版本號，不是「有參數但沒有線」。**

    一份宣稱自己是 v2、卻帶著沒有線的區域參數的檔案 —— 遷移**不准碰它**。
    這一條就是那個判準的證據：換成「沒有線就補」的話，這裡會冒出一條線。
    """
    rec = Recipe.from_json_dict(_doc(UPSTREAM, version=RECIPE_VERSION))
    assert _region_edges(rec) == []
    assert rec.nodes["glv"].params["roi"] == "epi", "那個字仍然留著"


# --------------------------------------------------------------------------- #
# ② 沒有人產出那個名字 → 不補線，而且那個字要留著
# --------------------------------------------------------------------------- #
def test_a_name_nobody_produces_keeps_its_name_and_its_error():
    """**壞的 recipe 遷移完仍然要壞，而且訊息不准變差。**

    ⚠ 工作單 B3-② 原本寫的是「讓埠空著，錯誤從 `unknown-region` 變
    `not-connected`」。實作選了**把名字留著**，因為同一句話還寫著「訊息不得
    變差」—— 而 `glv_stats` 根本長不出 `not-connected`：空的 ``roi`` 是完全
    合法的「量整張圖」，清掉之後那條路的終點是**安靜地算錯**。
    """
    rec = Recipe.from_json_dict(_doc(UPSTREAM, glv_roi="nope"))
    assert _region_edges(rec) == []
    assert rec.nodes["glv"].params["roi"] == "nope"
    bad = [i for i in validate(rec, kind=KIND) if i.code == "unknown-region"]
    assert len(bad) == 1 and bad[0].level == "error"
    assert "nope" in bad[0].detail
    # 訊息重寫過：現在講的是「拉一條線」，不是「把 roi 那一格清掉」——
    # 那一格在 F12 之後就是唯讀的了（B3-⑥）。
    assert "line" in bad[0].detail and "diamond" in bad[0].detail


# --------------------------------------------------------------------------- #
# ③ 產出它的那張卡排在下游 → 補線，順序因此被排對
# --------------------------------------------------------------------------- #
def test_a_region_card_to_the_right_gets_wired_and_the_order_is_fixed():
    """**這是一個刻意的行為改變，也是這一輪存在的理由。**

    遷移之前：那兩張卡在引擎眼裡毫無關係，量測卡先跑、`ctx.rois` 是空的，
    於是它安靜地量整張圖 —— 跑得完、有數字、而且是錯的。

    遷移之後：線把順序排對，一份原本算錯的 recipe 開始算對的數字。
    """
    before = Recipe.from_json_dict(_doc(DOWNSTREAM, version=RECIPE_VERSION))
    assert execution_order(before, KIND).index("glv") \
        < execution_order(before, KIND).index("roi"), "遷移前：量測卡先跑"

    rec = Recipe.from_json_dict(_doc(DOWNSTREAM))
    assert len(_region_edges(rec)) == 1
    order = execution_order(rec, KIND)
    assert order.index("roi") < order.index("glv"), "遷移後：線說了算"


# --------------------------------------------------------------------------- #
# ④ 補上去會成環 → 不補，而且不准安靜
# --------------------------------------------------------------------------- #
def _looping_doc(version=1):
    """工作單點名的那一種環：**Profile 吃 roi_mask 吐的 mask，roi_mask 又吃
    Profile 定義的區域。**

    ⚠ 查下來，這個形狀**今天就是壞的**（`unknown-region`），而且它不可能不壞：
    要讓那條區域線成環，就得先有一條 ``consumer → producer`` 的線，而那條線
    會把 consumer 排在 producer 前面 —— 於是 consumer 跑的時候那個區域還不
    存在。所以「今天跑得動、補了線就成環」的 recipe **不存在**。

    那這道環的檢查還有什麼用：讓一份**壞的** recipe 維持**壞得一樣**。
    沒有它的話 `execution_order` 會 raise，於是一條講得出話的 lint error
    變成「這個檔案打不開」—— 而遷移沒有資格把病情升級。
    """
    return {
        "recipe_id": "loop", "version": version,
        "routes": {KIND: ["load", "prof", "mask"]},
        "nodes": {
            "load": {"step": "load_single", "params": {"out": "test"}},
            "prof": {"step": "roi_reference",
                     "params": {"method": "stripes in the image",
                                "source": "mask", "roi_out": "epi"}},
            "mask": {"step": "roi_mask",
                     "params": {"regions": "epi", "source": "test",
                                "out": "mask"}},
        },
        "edges": [["load", "test", "mask", "source"],
                  ["mask", "mask", "prof", "source"]],
        "score": {"expr": "1", "threshold": 0.0,
                  "bins": {"below": 0, "above": 1}}}


def test_a_line_that_would_loop_is_not_added_and_loading_does_not_raise():
    """**遷移沒有資格把病情升級。**

    補上去就成環，而成環的 recipe `execution_order` 會 raise —— 一條講得出話
    的 lint error 於是變成「這個檔案打不開」。所以那條線不補，而這一份 recipe
    遷移前後**壞得一模一樣**（同一條 `unknown-region`，同一個節點）。
    """
    old = Recipe.from_json_dict(_looping_doc(version=RECIPE_VERSION))
    rec = Recipe.from_json_dict(_looping_doc())      # 不准炸
    assert _region_edges(rec) == []
    assert rec.nodes["mask"].params["regions"] == "epi", "那個字要留著"
    assert execution_order(rec, KIND) == execution_order(old, KIND)
    assert [(i.code, i.node_id) for i in validate(rec, kind=KIND)] \
        == [(i.code, i.node_id) for i in validate(old, kind=KIND)] \
        == [("unknown-region", "mask")]


def test_a_hand_written_recipe_with_a_box_but_no_line_is_reported():
    """**CLI 手寫 recipe 從此要寫 edges** —— 這是那句話的安全網。

    一份宣稱自己是 v2、卻只寫了 ``roi="epi"`` 而沒有那條線的檔案：遷移不碰它
    （判準是版本號），而它跑起來是對的（`ctx.rois` 是全域的，順序由 route
    的排列決定）—— 所以這是 warning，不是 error。

    但它不可以安靜：畫布上兩張卡看起來互不相干，而其中一張真的在量另一張畫的
    框 —— 那正是 F12 一開始要修的那句「畫布不能說謊」。
    """
    rec = Recipe.from_json_dict(_doc(UPSTREAM, version=RECIPE_VERSION))
    said = [i for i in validate(rec, kind=KIND)
            if i.code == "region-has-no-line"]
    assert len(said) == 1 and said[0].level == "warning"
    assert said[0].node_id == "glv"
    assert "epi" in said[0].detail and "line" in said[0].detail
    # 而遷移過的同一份**不會**拿到它 —— 線補上去了。
    assert "region-has-no-line" not in _codes(Recipe.from_json_dict(_doc(UPSTREAM)))


def test_a_properly_wired_recipe_does_not_get_that_warning():
    """在每一份正常的 recipe 上都出現的 warning 會被學會忽略 ——
    連同真的那一條一起被忽略。"""
    rec = Recipe.from_json_dict(_doc(UPSTREAM))
    assert "region-has-no-line" not in _codes(rec)
    for path in sorted((REPO / "recipes").glob("*.json")):
        shipped = Recipe.load(path)
        for kind in shipped.routes:
            assert "region-has-no-line" not in [
                i.code for i in validate(shipped, kind=kind)], path.name


def test_a_name_nobody_produces_gets_only_the_error_not_both():
    """②（沒有人產出）與 ④（補不上去）是**兩種不同的病**，不准同時報 ——
    一句話講兩次，使用者會以為有兩個問題。"""
    rec = Recipe.from_json_dict(_doc(UPSTREAM, glv_roi="nope"))
    assert "region-has-no-line" not in _codes(rec)


# --------------------------------------------------------------------------- #
# ⑤ 遷移不改變任何一份**已經對的** recipe 算出來的東西
# --------------------------------------------------------------------------- #
def test_migrating_changes_nothing_a_correct_recipe_computes():
    """驗收那一句：「v1 檔案載入 → 跑 → 輸出與遷移前逐位元組相同」。

    「遷移前」寫成**同一份檔案宣稱自己是 v2**（於是遷移不跑）—— 那是這一輪
    之後唯一還說得出「遷移前」的方式，而它問的正是同一件事：這兩份 recipe
    的每一張卡拿到的每一個參數都一樣嗎。
    """
    old = Recipe.from_json_dict(_doc(UPSTREAM, version=RECIPE_VERSION))
    new = Recipe.from_json_dict(_doc(UPSTREAM))
    assert set(old.nodes) == set(new.nodes)
    for nid in old.nodes:
        assert old.nodes[nid].params == new.nodes[nid].params, nid
    assert old.routes == new.routes
    # 差別**只有**那條線（以及它帶來的順序）。
    assert [e for e in new.edges if e not in old.edges] == _region_edges(new)


def test_the_shipped_recipes_are_on_the_new_version():
    """出貨的 recipe 重存成新版了（B3-⑤）—— 不然使用者每次打開都在遷移。"""
    for path in sorted((REPO / "recipes").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["version"] == RECIPE_VERSION, path.name
