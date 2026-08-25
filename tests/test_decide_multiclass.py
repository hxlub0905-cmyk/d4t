# F21-D：多類別判定（decide）
"""這一份鎖住的是**這個 app 第一次分得出兩類以上**。

在這之前 `score.bins` 被強制只有 `below`/`above` —— 一個叫 ADC（Auto Defect
Classification）的工具，只做得到二元判定。

測的是六件事：

1. **由上往下第一個成立的贏**（那是規格，不是實作細節 —— 改順序＝改優先權）；
2. `let` 的中間值是**真的特徵**（會進 CSV，使用者畫得出分布）；
3. `score` 仍然寫進 `features["score"]`，所以 KLARF 的 DSIZE／Top-N／CSV 的
   score 欄都不必知道這一段換過；
4. **`score` 與 `decide` 不能並存**（`ambiguous-decision`）—— 同一件事兩個地方
   存，是這個 repo 最怕的形狀；
5. **沒有 `decide` 的 recipe 一個位元都沒動**（黃金值現在是壞的，見 F21 §6 ——
   所以「改了判定段但數字沒變」只能靠這一條守）；
6. round-trip 是 identity（鐵則 9：`to_json_dict → from_json_dict` 是
   `run_batch` 送 recipe 進 worker 的路）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import validate  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Recipe, RecipeNode, Rule, ScoreSpec,
)

FIXTURE = Path(__file__).parent / "fixtures" / "recipes" / "dual_route_basic.json"


def _recipe(decide=None, score_expr="glv_max"):
    return Recipe(
        recipe_id="t",
        routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr=score_expr, threshold=1.0,
                        bins={"below": 0, "above": 1}),
        decide=decide,
    )


def _ctx(**feats):
    c = Context(images={})
    c.add_features(feats)
    return c


# --------------------------------------------------------------------------- #
# 1. 由上往下,第一個成立的贏
# --------------------------------------------------------------------------- #
DECIDE = DecideSpec(
    let=[Let("contrast", "a * b")],
    rules=[Rule("contrast > 100", 3, "big"),
           Rule("contrast > 30", 2, "small")],
    otherwise_bin=0, otherwise_label="nuisance",
    score="contrast",
)


@pytest.mark.parametrize("a,b,want_bin,want_label", [
    (20.0, 10.0, 3, "big"),        # 200 -> 第一條
    (10.0, 5.0, 2, "small"),       # 50  -> 第二條
    (2.0, 5.0, 0, "nuisance"),     # 10  -> 都不對
])
def test_the_first_rule_that_matches_wins(a, b, want_bin, want_label):
    ctx = _ctx(a=a, b=b)
    score, got = _eval_score(_recipe(DECIDE, score_expr=""), ctx)
    assert got == want_bin
    assert ctx.meta["decide"]["label"] == want_label
    assert score == pytest.approx(a * b)


def test_reordering_the_rules_changes_the_answer():
    """「改順序＝改優先權」—— 那是使用者讀得懂的那一句，所以它是規格。"""
    swapped = DecideSpec(
        let=list(DECIDE.let),
        rules=[Rule("contrast > 30", 2, "small"),
               Rule("contrast > 100", 3, "big")],
        otherwise_bin=0, score="contrast")
    _, got = _eval_score(_recipe(swapped, score_expr=""), _ctx(a=20.0, b=10.0))
    assert got == 2, "順序換了,200 現在先撞上寬的那一條"


def test_a_rule_can_combine_conditions_without_a_second_syntax():
    """比較運算子本來就回 1.0／0.0，所以 `(a > 5) * (b < 2)` 就是 AND。"""
    d = DecideSpec(rules=[Rule("(a > 5) * (b < 2)", 7, "both")],
                   otherwise_bin=0)
    assert _eval_score(_recipe(d, score_expr=""), _ctx(a=9.0, b=1.0))[1] == 7
    assert _eval_score(_recipe(d, score_expr=""), _ctx(a=9.0, b=5.0))[1] == 0


# --------------------------------------------------------------------------- #
# 2 & 3. let 是真的特徵；score 還是 score
# --------------------------------------------------------------------------- #
def test_the_intermediate_values_become_real_features():
    """它們會進 CSV 與報表 —— 那正是 `feature_math` 存在的唯一真理由。"""
    ctx = _ctx(a=4.0, b=5.0)
    _eval_score(_recipe(DECIDE, score_expr=""), ctx)
    assert ctx.features["contrast"] == pytest.approx(20.0)


def test_a_later_let_line_can_use_an_earlier_one():
    d = DecideSpec(let=[Let("x", "a * 2"), Let("y", "x + 1")],
                   rules=[Rule("y > 0", 1, "")], score="y")
    ctx = _ctx(a=3.0)
    score, _ = _eval_score(_recipe(d, score_expr=""), ctx)
    assert ctx.features["x"] == 6.0 and ctx.features["y"] == 7.0
    assert score == 7.0


def test_the_score_still_lands_where_everything_downstream_looks_for_it():
    """KLARF 的 DSIZE、Top-N 排序、CSV 的 score 欄都讀 `features["score"]`。"""
    ctx = _ctx(a=4.0, b=5.0)
    _eval_score(_recipe(DECIDE, score_expr=""), ctx)
    assert ctx.features["score"] == pytest.approx(20.0)


def test_no_score_expression_means_no_score_at_all():
    """**沒有分數表達式 ⇒ 沒有分數**（F30 改的，2026-08-25）。

    這條測試以前叫 `..._and_gives_zero`，斷言的是 ``score == 0.0`` ——
    也就是說**它把那個 bug 鎖住了**。判定樹是一個分類器，多數樹沒有分數
    表達式，於是每一顆都拿到一個假的 0，而後果一個比一個嚴重：

    1. CSV 多一欄全是 0 的 ``score``；
    2. 每一張疊圖左上角寫著 ``score=0.000``（讀起來像「這顆得 0 分」）；
    3. **「照分數排序取前 N 顆」變成「檔案順序的前 N 顆」** —— 全部同分時
       `sorted` 是穩定的，於是它原封不動地回傳輸入順序。

    第 3 點是實跑 6000 顆的報表時看到的，而排序正是使用者要那份報表的理由。
    """
    d = DecideSpec(rules=[Rule("a > 1", 5, "")], score="")
    ctx = _ctx(a=9.0)
    score, got = _eval_score(_recipe(d, score_expr=""), ctx)
    assert (score, got) == (None, 5)
    # 那一格**不寫**（同量測卡的規矩 3）—— 寫一個 None 進 CSV 跟寫 0 一樣糟
    assert "score" not in ctx.features


# --------------------------------------------------------------------------- #
# 4. 兩種寫法不能並存
# --------------------------------------------------------------------------- #
def test_having_both_a_score_and_a_decide_block_is_an_error():
    """同一件事兩個地方存 —— 挑一個贏的話另一份會安靜地漂,而使用者改了
    沒用的那一份時畫面上看不出來。"""
    codes = {i.code for i in validate(_recipe(DECIDE, score_expr="glv_max"))
             if i.level == "error"}
    assert "ambiguous-decision" in codes, codes


def test_a_decide_only_recipe_is_clean():
    issues = validate(_recipe(DECIDE, score_expr=""))
    assert not [i for i in issues if i.level == "error"], issues


def test_an_empty_score_expression_is_not_reported_when_decide_is_there():
    """走多類別時 score.expr 是空字串,而空字串解析不出來 —— 對它報 error
    等於「recipe 是對的,但健檢說它壞了」,而使用者只會相信健檢。"""
    codes = {i.code for i in validate(_recipe(DECIDE, score_expr=""))}
    assert "score-expr" not in codes and "bad-bins" not in codes, codes


@pytest.mark.parametrize("bad,code", [
    (DecideSpec(rules=[Rule("a >", 1, "")]), "bad-rule"),
    (DecideSpec(let=[Let("x", "a +")], rules=[Rule("a > 1", 1, "")]), "bad-let"),
    (DecideSpec(let=[Let("", "a")], rules=[Rule("a > 1", 1, "")]), "bad-let"),
    (DecideSpec(let=[Let("x", "a"), Let("x", "b")],
                rules=[Rule("a > 1", 1, "")]), "bad-let"),
])
def test_a_broken_decide_block_says_which_line(bad, code):
    codes = {i.code for i in validate(_recipe(bad, score_expr=""))}
    assert code in codes, codes


def test_no_rules_at_all_is_a_warning_not_a_crash():
    issues = validate(_recipe(DecideSpec(rules=[]), score_expr=""))
    assert "no-rules" in {i.code for i in issues}
    assert not [i for i in issues if i.level == "error"]


# --------------------------------------------------------------------------- #
# 5. 沒有 decide 的 recipe 一個位元都沒動
# --------------------------------------------------------------------------- #
def test_an_old_recipe_round_trips_without_growing_a_decide_key():
    """**這一條是這一輪唯一的防線。**

    黃金值從 F19 起就是壞的（`docs/plans/F21-algo-and-roi.md` §6），所以
    「改了判定段但既有的數字沒變」這句話沒有別的東西證得了。
    """
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    r = Recipe.from_json_dict(raw)
    assert r.decide is None
    out = r.to_json_dict()
    assert "decide" not in out, "沒有 decide 的 recipe 不准長出這個鍵"
    assert out["score"] == {"expr": raw["score"]["expr"],
                            "threshold": float(raw["score"]["threshold"]),
                            "bins": dict(raw["score"]["bins"])}


def test_the_old_path_still_decides_exactly_as_before():
    ctx = _ctx(glv_max=5.0)
    score, got = _eval_score(_recipe(None, score_expr="glv_max"), ctx)
    assert (score, got) == (5.0, 1)
    ctx2 = _ctx(glv_max=0.5)
    assert _eval_score(_recipe(None, score_expr="glv_max"), ctx2)[1] == 0


# --------------------------------------------------------------------------- #
# 6. round-trip 是 identity（鐵則 9）
# --------------------------------------------------------------------------- #
def test_a_decide_recipe_round_trips_unchanged():
    """`to_json_dict → from_json_dict` 是 `run_batch` 送 recipe 進 worker 的路
    —— 它一旦不是 identity，`workers=1` 與 `workers=2` 就會分出不同的 bin。"""
    r = _recipe(DECIDE, score_expr="")
    once = r.to_json_dict()
    twice = Recipe.from_json_dict(once).to_json_dict()
    assert once == twice
    back = Recipe.from_json_dict(once)
    assert back.decide == DECIDE


def test_a_broken_decide_block_is_refused_at_read_time_not_silently_ignored():
    """安靜地退回老路的話,一份打錯字的多類別 recipe 會跑得完、有數字、
    而且每一顆都是 bin 0。"""
    from d4t.core.pipeline.recipe import RecipeError
    raw = _recipe(DECIDE, score_expr="").to_json_dict()
    raw["decide"]["rules"] = [{"when": "a > 1"}]        # 少了 bin
    with pytest.raises(RecipeError):
        Recipe.from_json_dict(raw)


# --------------------------------------------------------------------------- #
# 判定段指到「沒有人算得出來的數字」要講一句（A2，2026-08-24）
# --------------------------------------------------------------------------- #
def _measuring_recipe(decide: dict) -> Recipe:
    """一份真的會算出東西的 recipe：``load_patch`` → ``glv_stats``。

    這一組測試問的是「validate 分不分得出**哪些名字算得出來**」，所以 recipe
    必須真的有一張量測卡 —— 空的 route 會讓每一個名字都是未知的，那時候測試
    看起來會過，但它什麼都沒有鑑別。
    """
    return Recipe.from_json_dict({
        "version": 1, "recipe_id": "t",
        "nodes": {
            "load": {"step": "load_patch", "params": {}, "enabled": True},
            "g": {"step": "glv_stats",
                  "params": {"source": "test", "metrics": "glv_median,glv_mad"},
                  "enabled": True},
        },
        "routes": {"ebi_patch": ["load", "g"]},
        "edges": [["load", "test", "g", "source"]],
        "score": {"expr": "", "threshold": 0.0, "bins": {"below": 0, "above": 1}},
        "decide": decide,
    })


def _unknown(decide: dict):
    return [i for i in validate(_measuring_recipe(decide))
            if i.code == "unknown-feature"]


def test_a_question_that_names_a_number_nobody_produces_is_reported():
    """**F21-D 漏掉的那一半。**

    `validate` 對舊的 ``score.expr`` 一直有 ``unknown-feature``，而加上
    ``decide`` 之後那一段變成「有 decide 就整個跳過」—— 理由是對的
    （有 decide 時 ``score.expr`` 根本不會跑），但替代的檢查從沒補上。

    後果：打錯一個數字名字 → validate 全綠、畫布正常，而跑起來**每一顆都失敗**。
    F25 把二元門檻的 UI 拿掉之後，``decide`` 是唯一走得到的路 —— 也就是說
    唯一有人用的那條路，lint 覆蓋比沒人用的那條還少。
    """
    issues = _unknown({"let": [],
                       "tree": {"when": "glv_medain > 6.5",   # 打錯字
                                "yes": {"bin": 1}, "no": {"bin": 0}},
                       "score": "glv_median"})
    assert issues, "打錯的數字名字沒有被講出來"
    assert "glv_medain" in issues[0].detail
    assert issues[0].level == "warning"      # 跟舊的那一條同級


def test_a_question_that_names_a_real_number_is_quiet():
    """有鑑別力才算數：正確的名字不可以也被報。"""
    assert not _unknown({"let": [],
                         "tree": {"when": "glv_median > 6.5",
                                  "yes": {"bin": 1}, "no": {"bin": 0}},
                         "score": "glv_median"})


def test_the_working_numbers_are_visible_to_the_lines_below_them():
    """``let`` 是**累加**的：第 n 行看得到前 n−1 行（引擎就是照順序算的）。"""
    assert not _unknown({
        "let": [{"name": "ratio", "expr": "glv_median / glv_mad"}],
        "tree": {"when": "ratio > 2", "yes": {"bin": 1}, "no": {"bin": 0}},
        "score": "ratio"})


def test_a_working_number_cannot_use_one_defined_below_it():
    """反過來就不行 —— 引擎算到那一行時，下面那一行還不存在。

    這一條是上一條的另一半：只驗「看得到前面」而不驗「看不到後面」的話，
    一個永遠回空集合的實作也會過。
    """
    issues = _unknown({
        "let": [{"name": "a1", "expr": "later * 2"},
                {"name": "later", "expr": "glv_median"}],
        "tree": {"when": "a1 > 1", "yes": {"bin": 1}, "no": {"bin": 0}},
        "score": "a1"})
    assert issues and "later" in issues[0].detail


@pytest.mark.parametrize("extra, when", [
    ({"fill": "0"}, "m_missing > 0"),      # F24 ⑤：有 fill 就多一個 _missing
    ({"scale": "z"}, "m_raw > 5"),         # F23 期3：有 scale 就留一個 _raw
], ids=["fill-writes-missing", "scale-keeps-raw"])
def test_the_flags_a_working_number_produces_are_visible_too(extra, when):
    """``fill`` 與 ``scale`` 各自多寫一個名字，而判定樹的第一步常常問的就是它們。

    漏掉的話這條檢查會對一份**完全正確**的 recipe 大叫 —— 那比沒有檢查更糟。
    """
    let = dict({"name": "m", "expr": "glv_median"}, **extra)
    assert not _unknown({"let": [let],
                         "tree": {"when": when, "yes": {"bin": 9},
                                  "no": {"bin": 0}},
                         "score": "m"})


def test_the_score_and_the_old_flat_rules_are_checked_as_well():
    """判定段有三種地方寫得出表達式，三種都要檢查。"""
    bad_score = _unknown({"let": [],
                          "tree": {"when": "glv_median > 1",
                                   "yes": {"bin": 1}, "no": {"bin": 0}},
                          "score": "glv_mdian"})
    assert bad_score and "glv_mdian" in bad_score[0].detail

    bad_rule = _unknown({"let": [], "rules": [{"when": "nosuch > 1", "bin": 1}],
                         "otherwise": {"bin": 0}, "score": "glv_median"})
    assert bad_rule and "nosuch" in bad_rule[0].detail


def test_a_question_that_does_not_even_parse_is_not_reported_twice():
    """語法錯已經由 ``bad-rule`` 講過了 —— 同一件事講兩次是雜訊。"""
    decide = {"let": [], "tree": {"when": "glv_median >", "yes": {"bin": 1},
                                  "no": {"bin": 0}}, "score": "glv_median"}
    issues = validate(_measuring_recipe(decide))
    assert any(i.code == "bad-rule" for i in issues)
    assert not [i for i in issues
                if i.code == "unknown-feature" and "glv_median >" in i.detail]
