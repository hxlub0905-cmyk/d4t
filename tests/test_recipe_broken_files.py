# 手改壞的 recipe 要講人話 — authored 2026-08-24（全專案 review 的 F8）。
"""**這個 repo 沒有存檔功能**（2026-08-16 拿掉），所以手改 JSON 是編輯 recipe
的唯一方式 —— 而手改就會打錯。

打錯的時候使用者看到什麼，是推廣鐵則的事：目標使用者是不會寫 code 的製程／
設備工程師，而 ``could not convert string to float: 'abc'`` 沒有講出是**哪一個
欄位**，也沒有講出該填什麼。

這一份鎖住三件事：

1. **每一種壞法都是 `RecipeError`**，而且訊息裡有欄位名（不是原始的
   ``ValueError`` / ``RecursionError``）；
2. **`score` 只有在沒有 `decide` 的時候才是必填** —— 兩者是二選一的契約，
   硬性要求等於逼一份判定樹 recipe 帶一個它不用的區塊；
3. **改完之後 round-trip 仍然是 identity**（鐵則 9）—— 這是最重要的一條，
   因為 ``to_json_dict → from_json_dict`` 是 ``run_batch`` 送 recipe 進 worker
   的路，它一旦不是 identity，``workers=1`` 與 ``workers=2`` 就會算出不同的分數。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.expression import (  # noqa: E402
    MAX_DEPTH, ExpressionError, parse_expression,
)
from d4t.core.pipeline.recipe import MAX_TREE_DEPTH, Recipe, RecipeError  # noqa: E402


def _score_recipe() -> dict:
    """走老路（單一門檻）的最小 recipe。"""
    return {"version": 1, "recipe_id": "t", "nodes": {},
            "routes": {"ebi_patch": []}, "edges": [],
            "score": {"expr": "0", "threshold": 1.0,
                      "bins": {"below": 0, "above": 1}}}


def _decide_recipe() -> dict:
    """走判定樹的最小 recipe —— **沒有 score 區塊**。"""
    return {"version": 1, "recipe_id": "t", "nodes": {},
            "routes": {"ebi_patch": []}, "edges": [],
            "decide": {"let": [],
                       "tree": {"when": "a > 1",
                                "yes": {"bin": 7, "label": "big"},
                                "no": {"bin": 3, "label": "small"}},
                       "score": "a"}}


# --------------------------------------------------------------------------- #
# 1. 每一種壞法都要講人話
# --------------------------------------------------------------------------- #
def _broken(mutate):
    d = _score_recipe()
    mutate(d)
    return d


def _mut_threshold(d):
    d["score"]["threshold"] = "abc"


def _mut_bins(d):
    d["score"]["bins"] = {"below": "x"}


def _mut_version(d):
    d["version"] = "1.0"


def _mut_params(d):
    d["nodes"] = {"n1": {"step": "normalize", "params": "nope"}}


def _mut_route_is_a_string(d):
    d["routes"] = {"ebi_patch": "abc"}


def _mut_nodes_is_a_string(d):
    d["nodes"] = "abc"


def _mut_rule_bin(d):
    d.pop("score")
    d["decide"] = {"let": [], "rules": [{"when": "a > 1", "bin": "x"}],
                   "otherwise": {"bin": 0}, "score": "a"}


def _mut_tree_bin(d):
    d.pop("score")
    d["decide"] = {"let": [], "score": "a",
                   "tree": {"when": "a > 1", "yes": {"bin": "abc"},
                            "no": {"bin": 0}}}


@pytest.mark.parametrize("mutate, must_mention", [
    (_mut_threshold, "score.threshold"),
    (_mut_bins, "score.bins"),
    (_mut_version, "version"),
    (_mut_params, "params"),
    (_mut_route_is_a_string, "route"),
    (_mut_nodes_is_a_string, "nodes"),
    (_mut_rule_bin, "decide.rules[0].bin"),
    (_mut_tree_bin, "decide.tree.yes.bin"),
], ids=lambda x: getattr(x, "__name__", x))
def test_a_broken_field_says_which_field_it_is(mutate, must_mention):
    """壞掉的欄位要在訊息裡指名道姓。

    在這之前這幾個是直接 ``int()`` / ``float()`` 下去，所以漏出來的是原始的
    ``ValueError``：``invalid literal for int() with base 10: '1.0'``。
    UI 與 CLI 都有攔（不會 traceback），但顯示給使用者的就是那句話。
    """
    with pytest.raises(RecipeError) as err:
        Recipe.from_json_dict(_broken(mutate))
    assert must_mention in str(err.value), str(err.value)


def test_a_true_false_value_where_a_number_belongs_is_a_typo_not_a_number():
    """``bool`` 是 ``int`` 的子類，所以 ``int(True)`` 會安靜地回 1。

    一個 ``"bin": true`` 的欄位如果變成 bin 1，那是**跑得完、有數字、而且是
    錯的**那個家族 —— 所以擋在讀檔。
    """
    d = _score_recipe()
    d["score"]["bins"] = {"below": True}
    with pytest.raises(RecipeError) as err:
        Recipe.from_json_dict(d)
    assert "true/false" in str(err.value)


def test_a_route_that_is_a_string_does_not_silently_become_three_steps():
    """字串是可迭代的 —— ``"abc"`` 以前會安靜地變成 ``["a", "b", "c"]``。

    三個不存在的節點 id，而錯誤要到跑起來才出現（而且講的是別的事）。
    """
    d = _score_recipe()
    d["routes"] = {"ebi_patch": "abc"}
    with pytest.raises(RecipeError):
        Recipe.from_json_dict(d)


# --------------------------------------------------------------------------- #
# 2. 巢狀太深 → RecipeError / ExpressionError，不是 RecursionError
# --------------------------------------------------------------------------- #
def test_a_tree_nested_past_the_limit_is_a_damaged_file_not_a_crash():
    """`_tree_from_json` 是遞迴的，而 ``RecursionError`` 不是 ``RecipeError``
    —— 讀檔那條路 ``except RecipeError`` 接不住它，使用者看到 traceback。"""
    node = {"bin": 0}
    for _ in range(MAX_TREE_DEPTH + 50):
        node = {"when": "a > 1", "yes": {"bin": 1}, "no": node}
    d = _decide_recipe()
    d["decide"]["tree"] = node
    with pytest.raises(RecipeError) as err:
        Recipe.from_json_dict(d)
    msg = str(err.value)
    assert "nested" in msg
    # 訊息不可以是 200 段 ".no"
    assert len(msg) < 400, msg


def test_a_tree_just_under_the_limit_still_reads():
    """上限是「這一定是壞檔」的線，不是「正常的樹會撞到」的線。"""
    node = {"bin": 0}
    for _ in range(MAX_TREE_DEPTH - 2):
        node = {"when": "a > 1", "yes": {"bin": 1}, "no": node}
    d = _decide_recipe()
    d["decide"]["tree"] = node
    assert Recipe.from_json_dict(d).decide.tree is not None


@pytest.mark.parametrize("text", [
    "(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1),
    "min(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1),
], ids=["brackets", "nested-calls"])
def test_an_expression_nested_past_the_limit_is_an_expression_error(text):
    """同上，但在遞迴下降的 parser 那一邊（實測 400 層括號就會撞）。"""
    with pytest.raises(ExpressionError) as err:
        parse_expression(text)
    assert "nests brackets" in str(err.value)


def test_an_expression_just_under_the_limit_still_parses():
    text = "(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH
    assert parse_expression(text).eval({"a": 3.0}) == 3.0


# --------------------------------------------------------------------------- #
# 3. score 與 decide 的二選一契約
# --------------------------------------------------------------------------- #
def test_a_decide_recipe_does_not_need_a_score_block():
    """``score`` 與 ``decide`` 是二選一（見 `DecideSpec` 的說明），所以硬性
    要求 ``score`` 等於逼一份判定樹 recipe 帶一個它根本不用的區塊。

    以前手寫一份 decide recipe 會拿到
    ``missing required fields: ['score']`` —— 對使用者是死路。
    """
    r = Recipe.from_json_dict(_decide_recipe())
    assert r.decide is not None
    assert r.score.expr == ""          # 空的老路，validate 不會判 ambiguous
    assert r.decide.tree.yes.bin == 7


def test_a_recipe_with_neither_score_nor_decide_still_complains():
    """放寬的是「有 decide 就不用 score」，不是「兩個都不用」。"""
    d = _score_recipe()
    d.pop("score")
    with pytest.raises(RecipeError) as err:
        Recipe.from_json_dict(d)
    assert "score" in str(err.value)


# --------------------------------------------------------------------------- #
# 4. 鐵則 9：上面每一條都不准動到 round-trip
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("make", [_score_recipe, _decide_recipe],
                         ids=["score", "decide"])
def test_a_json_round_trip_still_changes_nothing(make):
    """``to_json_dict → from_json_dict`` 必須是 identity。

    這是 ``run_batch`` 送 recipe 進 worker 的路，不是 identity 的話
    ``workers=1`` 與 ``workers=2`` 會算出不同的分數（2026-08-16 真的發生過，
    glv_max 50 vs 43）。
    """
    a = Recipe.from_json_dict(make()).to_json_dict()
    b = Recipe.from_json_dict(a).to_json_dict()
    assert a == b
