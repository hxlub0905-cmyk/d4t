# F53：空白的 working number 當成沒填（2026-08-28）。
"""判定面板上按一下「+ Add a line」就會多一列空的 —— 而在這之前，**那一列
立刻讓整份 recipe 跑不動**。

真實案例（使用者 2026-08-28 拿一份 recipe 來問為什麼跑不動）：

    Cannot run — A 'let' line has no name: decide.let[0] must have a name
    - that name is what the rules below refer to. (and 5 more problems)

六條 error，而它們**全部是同一件事**：三列空白的 let，每列各報兩條（沒有
名字 ＋ 算式空的）。工具列只講「and 5 more problems」，看起來像六個不同的
毛病。那份 recipe 其餘的部分（八條線、兩條區域線、樹裡的每一個特徵名）
一條警告都沒有。

所以：**整行都沒填的當成沒填**（同載入卡那兩格篩選的處理）。

⚠ **填了一半仍然要講話** —— 寫了算式沒取名字是真的錯（那個值誰都指不到），
取了名字算式空的也是（每一顆都會失敗）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Recipe, RecipeNode, ScoreSpec, TreeLeaf, TreeStep,
    validate,
)
from d4t.core.pipeline.verdict_features import bound_specs  # noqa: E402

BLANK = Let(name="", expr="")


def _recipe(lets) -> Recipe:
    return Recipe(
        recipe_id="f53",
        routes={"ebi_patch": ["load", "glv"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats", {"source": "test"})},
        score=ScoreSpec(expr="", threshold=0.5, bins={"below": 0, "above": 1}),
        decide=DecideSpec(
            let=list(lets),
            tree=TreeStep(when="glv_median > 1",
                          yes=TreeLeaf(bin=1), no=TreeLeaf(bin=0)),
            score="glv_median"))


# --------------------------------------------------------------------------- #
# 1. 空白的當成沒填
# --------------------------------------------------------------------------- #
def test_a_blank_line_is_blank():
    assert BLANK.is_blank is True
    assert Let(name="  ", expr="\t").is_blank is True


def test_three_blank_lines_do_not_stop_the_run():
    """使用者那份 recipe 的形狀 —— 三列空白，六條 error。"""
    lets = [BLANK, BLANK, BLANK]
    errs = [i for i in validate(_recipe(lets)) if i.level == "error"]
    assert not errs, [i.detail for i in errs]


def test_the_engine_skips_them_too():
    """**引擎跟 lint 要同一句話。**

    只改 lint 的話，畫面上綠燈而每一顆在引擎裡失敗 —— 那比原本的錯誤訊息
    更難查（跑得完、有數字…不，是跑不完而畫面說沒問題）。
    """
    ctx = Context()
    ctx.features["glv_median"] = 5.0
    score, chosen = _eval_score(_recipe([BLANK, BLANK, BLANK]), ctx)
    assert chosen == 1 and score == 5.0


def test_they_produce_no_feature():
    names = {b.spec.name for b in bound_specs(_recipe([BLANK]), "ebi_patch")}
    assert "" not in names


# --------------------------------------------------------------------------- #
# 2. 填了一半仍然要講話
# --------------------------------------------------------------------------- #
def test_an_expression_with_no_name_is_still_an_error():
    """寫了算式沒取名字 —— 那個值誰都指不到。"""
    errs = [i for i in validate(_recipe([Let(name="", expr="glv_median * 2")]))
            if i.level == "error"]
    assert any("no name" in (i.title or "") for i in errs), errs


def test_a_name_with_no_expression_is_still_an_error():
    """取了名字算式空的 —— 每一顆都會在那一行失敗。"""
    errs = [i for i in validate(_recipe([Let(name="x", expr="")]))
            if i.level == "error"]
    assert any("parse" in (i.title or "") for i in errs), errs


def test_a_blank_line_next_to_a_real_one_changes_nothing():
    """空白行不准影響它旁邊那一行 —— 順序、名字、值都一樣。"""
    real = Let(name="doubled", expr="glv_median * 2")
    a = _recipe([real])
    b = _recipe([BLANK, real, BLANK])
    for r in (a, b):
        assert not [i for i in validate(r) if i.level == "error"]

    def run(rec):
        ctx = Context()
        ctx.features["glv_median"] = 5.0
        _eval_score(rec, ctx)
        return dict(ctx.features)
    assert run(a) == run(b)


# --------------------------------------------------------------------------- #
# 3. 「什麼叫空白」只有一個家
# --------------------------------------------------------------------------- #
def test_every_place_that_walks_the_lets_uses_the_same_rule():
    """走 `decide.let` 的有四個地方 —— 抄四份的話遲早有一個說得不一樣。

    ⚠ 掃的是**會執行的那幾行**（濾掉註解與 docstring）：這一輪已經有三條
    測試抓到自己寫的說明，那個形狀不要再來第四次。
    """
    import ast

    want = {
        "d4t/core/pipeline/engine.py": "_eval_decision",
        "d4t/core/pipeline/verdict_features.py": "bound_specs",
    }
    for path, _fn in want.items():
        tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
        uses = [n for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and n.attr == "is_blank"]
        assert uses, "%s 沒有用 Let.is_blank —— 它自己判斷了什麼叫空白" % path

    src = (REPO / "d4t" / "core" / "pipeline" / "recipe.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    uses = [n for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "is_blank"]
    assert len(uses) >= 2, "recipe.py 的兩支 lint 都要問同一支（找到 %d 處）" % len(uses)
