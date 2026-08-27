# -*- coding: utf-8 -*-
"""同一條 route 上兩張卡定義同一個區域名 → **error**（F42 方案 B 的 B0）。

為什麼這一條要先做，而且要是 error
----------------------------------
方案 B 把區域依賴存進 ``recipe.edges``，而**一條線指著一個特定的節點**。
引擎那一頭沒有節點的概念 —— ``Context.set_roi`` 是**同名覆寫**，量測卡拿到的
永遠是「上游最後一張寫 ``epi`` 的卡」畫的框。

名字唯一的時候這兩件事是同一件事：線指的那張卡 ＝ 引擎真的給的那個框。
撞名的時候不是 —— 畫布可以指著第一張，引擎給的是第二張的，而**兩邊都跑得完、
都有數字**。所以擋掉撞名讓引擎的身分模型一行都不用改（使用者定調的 P1-a，
P1-b 明確不做）。

跟 ``feature-collision``（warning）差在哪
----------------------------------------
特徵被蓋掉時引擎會把前一份救成 ``<節點名>_<特徵>``，所以那句話是「你可能不是
故意的」。區域沒有那條救援 —— 前一張卡畫的框就是不見了。
"""
from __future__ import annotations

import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
from d4t.core.pipeline.recipe import (
    Recipe, RecipeNode, ScoreSpec, validate,
)
from d4t.core.pipeline.step import REGISTRY

#: 最省事的「會產出區域」的一張卡：Profile（stripes）＋ 一個名字。
PROFILE = "stripes in the image"
GDS = "layout layers"


def _profile(name: str, source: str = "test", **extra):
    p = {"method": PROFILE, "roi_out": name, "source": source}
    p.update(extra)
    return RecipeNode("", "roi_reference", p)


def _recipe(nodes, routes, edges=None) -> Recipe:
    return Recipe(
        recipe_id="t", routes=routes,
        nodes={nid: RecipeNode(nid, n.step, dict(n.params), n.enabled)
               for nid, n in nodes.items()},
        edges=list(edges or []),
        score=ScoreSpec(expr="1", threshold=0.0,
                        bins={"below": 0, "above": 1}))


def _issues(rec, code="duplicate-region"):
    return [i for i in validate(rec, registry=REGISTRY) if i.code == code]


# --------------------------------------------------------------------------- #
# 1. 撞到就擋
# --------------------------------------------------------------------------- #
def test_two_cards_defining_the_same_region_is_an_error():
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "a": _profile("epi"),
         "b": _profile("epi")},
        {"ebi_patch": ["load", "a", "b"]})
    bad = _issues(rec)
    assert bad, "兩張卡都定義 'epi' —— 後面那張會蓋掉前面那張的框"
    assert all(i.level == "error" for i in bad)
    # 訊息要指得出**兩張卡**（只講一張的話使用者不知道去哪裡改名）。
    one = bad[0]
    assert "a" in one.detail and "b" in one.detail
    assert one.node_id == "b", "報在後面那張卡上 —— 蓋掉別人的是它"
    assert "rename" in one.detail.lower() or "different region name" in one.detail


def test_the_center_and_others_names_collide_too():
    """``region_family`` 展開出來的三個名字都在檢查範圍。

    兩張 Profile 都吐 ``epi`` 的時候撞的不是一個名字，是三個 ——
    而 ``epi_center`` 正是量測卡最常指的那一個（缺陷在正中央的那一塊）。
    """
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "a": _profile("epi"),
         "b": _profile("epi")},
        {"ebi_patch": ["load", "a", "b"]})
    names = {i.title.split("'")[1] for i in _issues(rec)}
    assert names == {"epi", "epi_center", "epi_others"}


def test_a_name_that_collides_with_someone_elses_family_member():
    """第二張卡叫 ``epi_center`` 也是撞 —— 家族名不是保留字，是真的名字。"""
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "a": _profile("epi"),
         "b": _profile("epi_center")},
        {"ebi_patch": ["load", "a", "b"]})
    names = {i.title.split("'")[1] for i in _issues(rec)}
    assert names == {"epi_center"}


def test_a_gds_card_and_a_profile_card_collide_across_methods():
    """撞名跟兩張卡用哪個 method 無關 —— 撞的是 ``resolve_regions_out``。"""
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "sidecar": RecipeNode("", "load_sidecar", {}),
         "g": RecipeNode("", "roi_reference",
                         {"method": GDS, "layers": "1:epi, 2:mg",
                          "label_source": "layout_label"}),
         "a": _profile("mg")},
        {"ebi_patch": ["load", "sidecar", "g", "a"]})
    names = {i.title.split("'")[1] for i in _issues(rec)}
    assert names == {"mg", "mg_center", "mg_others"}


# --------------------------------------------------------------------------- #
# 2. 不准誤報（每一條都是這支 lint 會被學會忽略的形狀）
# --------------------------------------------------------------------------- #
def test_one_card_on_its_own_is_fine():
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "a": _profile("epi"),
         "b": _profile("mg")},
        {"ebi_patch": ["load", "a", "b"]})
    assert _issues(rec) == []


def test_the_same_name_on_two_different_routes_is_not_a_collision():
    """兩條 route 各有一張叫 ``epi`` 的 Region 卡是**常態**。

    `ebi_patch` 與 `rsem` 各走各的，兩張卡永遠不會在同一次執行裡碰面 ——
    對它報 error 等於逼使用者把第二條 route 的區域改名，而那會讓分數表達式
    在兩條路上長出兩個名字。
    """
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "load2": RecipeNode("", "load_single", {"out": "test"}),
         "a": _profile("epi"),
         "b": _profile("epi")},
        {"ebi_patch": ["load", "a"], "rsem": ["load2", "b"]})
    assert _issues(rec) == []


def test_a_disabled_card_does_not_collide():
    """停用的卡不跑，所以它不定義任何東西 —— 跟引擎一致。"""
    nodes = {"load": RecipeNode("", "load_patch", {}),
             "a": _profile("epi"),
             "b": _profile("epi")}
    nodes["b"].enabled = False
    rec = _recipe(nodes, {"ebi_patch": ["load", "a", "b"]})
    assert _issues(rec) == []


def test_passing_a_region_through_is_not_a_second_definition():
    """畫布上量測卡右邊也有 ``epi`` 這個埠（「同進同出」，F12 §7-①），
    但它送出去的是**別人的框**，不是第二份定義。

    這一條看的是 ``resolve_regions_out``（引擎的宣告），而
    ``viewmodel.region_outputs``（畫布的埠）刻意跟它分家。兩者混為一談的話，
    每一份「一張 Region 卡 ＋ 兩張量測卡」的正常 recipe 都會冒出紅字 ——
    而在每一份 recipe 上都出現的 error 會被學會忽略。
    """
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "a": _profile("epi"),
         "g1": RecipeNode("", "glv_stats", {"source": "test", "roi": "epi"}),
         "g2": RecipeNode("", "glv_stats", {"source": "test", "roi": "epi",
                                            "output_prefix": "second"})},
        {"ebi_patch": ["load", "a", "g1", "g2"]})
    assert _issues(rec) == []


def test_the_same_card_listed_once_is_not_a_collision_with_itself():
    """一張 GDS 卡吐兩層是一張卡的事，不是兩張卡撞名。"""
    rec = _recipe(
        {"load": RecipeNode("", "load_patch", {}),
         "sidecar": RecipeNode("", "load_sidecar", {}),
         "g": RecipeNode("", "roi_reference",
                         {"method": GDS, "layers": "1:epi, 2:mg",
                          "label_source": "layout_label"})},
        {"ebi_patch": ["load", "sidecar", "g"]})
    assert _issues(rec) == []


# --------------------------------------------------------------------------- #
# 3. 出貨的 recipe 與 fixture 都要過得去
# --------------------------------------------------------------------------- #
def test_the_shipped_recipes_have_no_duplicate_regions():
    """B0 是一條**新的 error**，所以它可能把既有的東西弄紅 —— 明著問一次。

    （`test_shipped_recipes.py` 也會抓到，但那支的訊息是「有一條 error」，
    這一支的訊息是「哪兩張卡撞了哪個名字」。）
    """
    import pathlib
    repo = pathlib.Path(__file__).resolve().parent.parent
    files = sorted((repo / "recipes").glob("*.json")) + \
        sorted((repo / "tests" / "fixtures" / "recipes").glob("*.json"))
    assert files, "沒有檔案可測 —— 這支測試會空轉"
    for path in files:
        rec = Recipe.load(path)
        for kind in rec.routes:
            bad = [i for i in validate(rec, kind=kind)
                   if i.code == "duplicate-region"]
            assert not bad, f"{path.name} ({kind}): {[i.detail for i in bad]}"
