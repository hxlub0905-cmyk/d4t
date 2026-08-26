# -*- coding: utf-8 -*-
"""存檔 recipe（2026-08-26 做回來）。

存檔在 2026-08-16 被拿掉，理由是「先把整個 engine 用好，再來支援」，而
Phase 1 同一天收斂。這一輪把它接回來，而這支測試守的是**那十天裡引擎長出來
的每一樣東西都活得過一趟存檔** —— 帶埠的邊（F9）、判定樹（F24）、分流
（F23）、沒在編的那幾條 route（F23 期2）。

⚠ 這裡最重要的一條不是「檔案寫得出來」，是 **``save`` → ``load`` 之後
算出來的東西一模一樣**。這個 repo 踩過六次「跑得完、有數字、而且是錯的」，
其中一次（`8ffe366`）正是序列化那一對不是 identity —— 而存檔功能把那條路
從「worker 內部」變成「使用者磁碟上的檔案」，賭注更大。
"""
from __future__ import annotations

import json
import os

import pytest

from d4t.core.pipeline import Recipe
from d4t.core.pipeline.recipe import (
    DecideSpec, Edge, RecipeNode, RouteBy, ScoreSpec, TreeLeaf, TreeStep,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "recipes")


def _rich_recipe() -> Recipe:
    """一份**每個新東西都用到**的 recipe（帶埠的邊、樹、分流、兩條 route）。

    刻意不從 fixture 讀：fixture 是舊形狀的（`edges: []`、`score` 那條老路），
    而這支測試要問的正是「新形狀存不存得住」。
    """
    tree = TreeStep(
        when="pair_found < 1",
        yes=TreeLeaf(bin=3, label="not detected"),
        no=TreeStep(
            when="pair_die_rank <= top_n",
            yes=TreeLeaf(bin=1, label="caught"),
            no=TreeLeaf(bin=2, label="detected, not sampled"),
        ),
    )
    return Recipe(
        recipe_id="rich",
        author="測試",
        description="中文說明也要活得過一趟 utf-8",
        routes={"rsem": ["load", "pair", "h2h"], "spare": ["load", "glv"]},
        nodes={
            "load": RecipeNode(id="load", step="load_single",
                               params={"out": "single"}),
            "pair": RecipeNode(id="pair", step="pair_source",
                               params={"source": "ebi", "out": "paired"}),
            "h2h": RecipeNode(id="h2h", step="align_to",
                              params={"template": "paired",
                                      "search": "single"}),
            "glv": RecipeNode(id="glv", step="glv_stats",
                              params={"source": "single"}, enabled=False),
        },
        edges=[Edge(src="load", dst="h2h", src_out="single", dst_in="search"),
               Edge(src="pair", dst="h2h", src_out="paired",
                    dst_in="template"),
               Edge(src="load", dst="glv", src_out="single",
                    dst_in="source")],
        score=ScoreSpec(expr="", threshold=0.5, bins={"below": 0, "above": 1}),
        decide=DecideSpec(let=[], rules=[], tree=tree, score="ncc_score"),
        route_by=RouteBy(column="CLASSNUMBER", map={"7": "spare"},
                         default="rsem"),
    )


# --------------------------------------------------------------------------- #
# 1. 存出來的東西讀回來要一模一樣
# --------------------------------------------------------------------------- #
def test_save_then_load_is_identity(tmp_path):
    """**這一條是整個功能的底線。**

    不成立的話，使用者存的 recipe 與他畫面上調的那一份會算出不同的分數 ——
    而兩邊都跑得完、都有數字（鐵則 9 那個坑的形狀）。
    """
    r = _rich_recipe()
    p = tmp_path / "rich.json"
    r.save(p)
    again = Recipe.load(p)
    assert again.to_json_dict() == r.to_json_dict()


def test_saving_twice_writes_the_same_bytes(tmp_path):
    """存 → 讀 → 再存，磁碟上要**逐位元組相同**。

    identity 只保證物件相等；這一條保證的是「打開一份 recipe 什麼都不改再
    存回去，diff 是空的」—— 那是使用者判斷「我剛才有沒有動到東西」的方式。
    """
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _rich_recipe().save(a)
    Recipe.load(a).save(b)
    assert a.read_bytes() == b.read_bytes()


def test_a_tree_survives_the_trip(tmp_path):
    """判定樹（F24）——**葉子的 bin 與 label 都要在**。

    label 是使用者在報表上看到的那個字（`decide_tree.verdict_rows` 的葉名），
    掉了的話報表上會變成一排「bin 3」，而那正是這份 recipe 要回答的問題。
    """
    p = tmp_path / "t.json"
    _rich_recipe().save(p)
    tree = Recipe.load(p).decide.tree
    assert tree.when == "pair_found < 1"
    assert (tree.yes.bin, tree.yes.label) == (3, "not detected")
    assert tree.no.no.label == "detected, not sampled"


def test_ports_on_the_edges_survive_the_trip(tmp_path):
    """帶埠的邊（F9）。**埠掉了畫布就說謊了** —— 線會接到別的輸入上。"""
    p = tmp_path / "e.json"
    _rich_recipe().save(p)
    got = {(e.src, e.src_out, e.dst, e.dst_in) for e in Recipe.load(p).edges}
    assert ("pair", "paired", "h2h", "template") in got
    assert ("load", "single", "h2h", "search") in got


def test_the_other_routes_and_the_prefilter_survive(tmp_path):
    """沒在編的那條 route（F23 期2）與 `route_by`。

    Studio 一次只編一條 route，另一條是「抱著」的 —— 存檔把它掉了的話，
    使用者存一次就少一條路，而畫面上完全看不出來。
    """
    p = tmp_path / "r.json"
    _rich_recipe().save(p)
    again = Recipe.load(p)
    assert again.routes["spare"] == ["load", "glv"]
    assert again.nodes["glv"].enabled is False
    assert again.route_by.column == "CLASSNUMBER"
    assert again.route_by.map == {"7": "spare"}


def test_utf8_text_is_not_escaped(tmp_path):
    """中文欄位存成真的中文，不是 ``\\uXXXX``。

    使用者會在記事本裡打開這個檔案（`docs/NO-GIT-SETUP.md` 那條路）——
    一份滿是逃脫序列的檔案在那裡是不可讀的。
    """
    p = tmp_path / "u.json"
    _rich_recipe().save(p)
    text = p.read_text(encoding="utf-8")
    assert "中文說明也要活得過一趟 utf-8" in text


# --------------------------------------------------------------------------- #
# 2. 怎麼寫（鐵則 5）
# --------------------------------------------------------------------------- #
def test_the_write_is_atomic(tmp_path):
    """``.tmp`` 不留在旁邊，而且**寫壞的時候原檔還在**。

    半份 recipe 的症狀是「打開來說 JSON 壞了」—— 而使用者這時候已經把
    原檔覆寫掉了。
    """
    p = tmp_path / "atomic.json"
    _rich_recipe().save(p)
    assert not list(tmp_path.glob("*.tmp"))
    before = p.read_bytes()

    # ⚠ 失敗要發生在**寫到一半**，不是在寫之前 —— ``json.dump`` 是邊算邊寫的，
    # 而「半份檔案」正是 atomic 要防的那個狀態。一個 JSON 塞不進去的值
    # （set）會讓它在中途拋 TypeError。
    bad = _rich_recipe()
    bad.nodes["load"].params["out"] = {"not", "json"}
    with pytest.raises(TypeError):
        bad.save(p)
    assert p.read_bytes() == before, "寫失敗了原檔要一個位元都沒動"
    assert not list(tmp_path.glob("*.tmp")), \
        "半份檔案要清掉 —— 它跟使用者要的那個檔名只差三個字元"


def test_it_makes_the_folder_if_it_is_missing(tmp_path):
    """使用者在另存對話框打一個還不存在的資料夾是常態，不是錯誤。"""
    p = tmp_path / "new" / "deeper" / "r.json"
    _rich_recipe().save(p)
    assert p.is_file()


def test_it_saves_a_recipe_that_does_not_validate(tmp_path):
    """**存檔不做健檢。**

    一份還在調、畫布上有紅字的 pipeline 必須存得下來 —— 存檔是「別弄丟我的
    工作」，不是「你做完了嗎」。擋在這裡的話，使用者中途要離開時唯一的選擇
    是丟掉它。
    """
    broken = Recipe(
        recipe_id="half",
        routes={"rsem": ["h2h"]},
        nodes={"h2h": RecipeNode(id="h2h", step="align_to",
                                 params={"template": "", "search": ""})},
        score=ScoreSpec(expr="", threshold=0.5, bins={}),
    )
    p = tmp_path / "half.json"
    broken.save(p)
    assert Recipe.load(p).routes["rsem"] == ["h2h"]


# --------------------------------------------------------------------------- #
# 3. app_version：這個檔案是誰寫的
# --------------------------------------------------------------------------- #
def test_saving_stamps_this_version_not_the_one_it_was_read_from(tmp_path):
    """存檔一律寫**現在這一版**。

    這欄要回答的是「這個檔案是誰寫的」，而 `version_skew` 靠它把「我的程式
    舊了」跟「這份檔案壞了」分開（`docs/PITFALLS.md`）。照抄讀進來的那一版
    等於讓一份被新版改過的檔案自稱是舊版寫的。
    """
    from d4t.core.pipeline.recipe import _app_version

    old = _rich_recipe()
    old.app_version = "0.0.1-ancient"
    p = tmp_path / "v.json"
    old.save(p)
    assert json.loads(p.read_text(encoding="utf-8"))["app_version"] \
        == _app_version()


def test_an_old_file_keeps_working_after_a_save(tmp_path):
    """讀一份舊 fixture、存回去、再讀 —— 節點與 route 一格都不能變。

    ⚠ 這裡**刻意不比整份 dict**：`load` 會多跑一道只在讀檔案時成立的遷移
    （`_migrate_rescued_feature_names`），所以「舊檔案存回去會被換成新形狀」
    是設計，不是 bug（見 `Recipe.save` 的說明）。這支測試守的是**那個換法
    不會弄丟東西**。
    """
    src = os.path.join(FIXTURES, "dual_route_basic.json")
    r = Recipe.load(src)
    p = tmp_path / "again.json"
    r.save(p)
    again = Recipe.load(p)
    assert again.routes == r.routes
    assert sorted(again.nodes) == sorted(r.nodes)
    for nid, node in r.nodes.items():
        assert again.nodes[nid].step == node.step
        assert again.nodes[nid].params == node.params
    assert again.score.expr == r.score.expr
    assert again.score.threshold == pytest.approx(r.score.threshold)
