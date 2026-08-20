# F16 Algo-1：Algo 段第一張卡（feature_math）。
"""這一份鎖住的是**把算術從分數表達式搬上畫布**這件事。

今天沒有這張卡也算得出來 —— 只是加減乘除只能發生在 `score.expr` 裡，而那裡：
畫布上看不到、recipe 的 diff 讀不懂、算錯了也沒有人擋得住，而且一份 recipe
只有**一條**表達式，所以中間值沒有地方放。

所以測的是四件事：

1. 它真的算得出來，而且**用的是既有的 parser**（SAFE 語意一併繼承）；
2. **指到一個沒人算出來的數字**要在跑之前就擋（`unknown-feature-input`）——
   沒有這一條的話它要等每一顆 defect 都失敗才看得出來；
3. 錯誤訊息講的是**這張卡的話**（不是「分數表達式」——使用者填的不是分數）；
4. 它一張影像都不碰（Algo 段的定義，`test_ui_f16_stages.py` 對整個 registry
   自動驗，這裡驗這一張真的做得到）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step, validate  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import StepError  # noqa: E402

CARD = "feature_math"


def _ctx(**feats):
    ctx = Context(images={})
    ctx.add_features(feats or {"glv_max": 200.0, "glv_median": 120.0,
                               "glv_std": 8.0})
    return ctx


def _run(ctx, expr, out="value"):
    get_step(CARD)().run(ctx, {"expr": expr, "out": out})
    return ctx


# --------------------------------------------------------------------------- #
# 1. 它算得出來
# --------------------------------------------------------------------------- #
def test_it_works_out_a_new_number_from_the_old_ones():
    ctx = _run(_ctx(), "glv_max - glv_median", out="contrast")
    assert ctx.features["contrast"] == pytest.approx(80.0)
    # 原本的數字一個都沒動
    assert ctx.features["glv_max"] == 200.0


def test_it_inherits_the_safe_semantics_of_the_existing_parser():
    """除以 0 → 0.0，而不是把整批殺掉（`expression.py` 的 SAFE 語意）。

    這是「接既有的 parser」而不是自己寫一個的價值：一份調參到一半的 recipe
    不該因為某一顆的分母剛好是 0 就整批停下來。
    """
    ctx = _run(_ctx(glv_max=5.0, zero=0.0), "glv_max / zero")
    assert ctx.features["value"] == 0.0


def test_it_is_not_eval():
    """`expression.py` 是手寫 parser —— Python 的語法在這裡不該通。"""
    with pytest.raises(StepError) as e:
        _run(_ctx(), "__import__('os').getcwd()")
    assert "expression" in str(e.value).lower()


def test_the_functions_the_help_promises_are_really_there():
    ctx = _ctx(a=9.0, b=-4.0)
    for expr, want in (("sqrt(a)", 3.0), ("abs(b)", 4.0),
                       ("min(a, b)", -4.0), ("max(a, b)", 9.0)):
        assert _run(_ctx(a=9.0, b=-4.0), expr).features["value"] == \
            pytest.approx(want), expr


# --------------------------------------------------------------------------- #
# 2. 指到一個沒人算出來的數字 —— 在跑之前就擋
# --------------------------------------------------------------------------- #
def _recipe(expr, out="value", measure_first=True):
    nodes = {"load": RecipeNode("load", "load_patch", {})}
    route = ["load"]
    if measure_first:
        nodes["glv"] = RecipeNode("glv", "glv_stats",
                                  {"source": "test", "metrics": "glv_max"})
        route.append("glv")
    nodes["math"] = RecipeNode("math", CARD, {"expr": expr, "out": out})
    route.append("math")
    return Recipe(recipe_id="t", routes={"ebi_patch": route}, nodes=nodes,
                  score=ScoreSpec(expr=out, threshold=1.0,
                                  bins={"below": 0, "above": 1}))


def test_a_number_nobody_produces_is_an_error_before_the_run():
    issues = [i for i in validate(_recipe("glv_max * 2", measure_first=False))
              if i.level == "error"]
    codes = {i.code for i in issues}
    assert "unknown-feature-input" in codes, codes
    said = next(i for i in issues if i.code == "unknown-feature-input")
    assert "glv_max" in said.detail
    # 訊息要講得出**怎麼修**，不是只講壞了
    assert "spelling" in said.detail or "move this card" in said.detail


def test_the_same_expression_is_fine_once_something_measures_it():
    errs = [i for i in validate(_recipe("glv_max * 2")) if i.level == "error"]
    assert not errs, errs


def test_the_declaration_is_what_the_expression_actually_uses():
    card = get_step(CARD)
    p = {"expr": "sqrt(glv_max) - glv_median / 2", "out": "v"}
    # 函數名不算變數
    assert card.resolve_features_in(p) == ["glv_max", "glv_median"]
    assert card.resolve_features(p) == ["v"]


def test_a_broken_expression_does_not_pretend_to_read_something():
    """解析不出來的時候該講的話是「語法錯」，不是「你指到一個不存在的數字」
    —— 後者會把使用者送去查一個沒有問題的地方。"""
    assert get_step(CARD).resolve_features_in({"expr": "glv_max +"}) == []
    says = get_step(CARD).configuration_issues({"expr": "glv_max +", "out": "v"})
    assert says and "does not parse" in says[0]


# --------------------------------------------------------------------------- #
# 3. 訊息講的是這張卡的話
# --------------------------------------------------------------------------- #
def test_the_parse_error_does_not_call_it_a_score():
    """`ExpressionError` 的訊息寫死是「Problem in the score expression」——
    在這張卡上那句話是錯的（使用者填的不是分數）。"""
    with pytest.raises(StepError) as e:
        _run(_ctx(), "glv_max +")
    text = str(e.value)
    assert "score" not in text.lower(), text
    assert "^" in text, "caret 指位要留著（那是這個 parser 最有用的地方）"


def test_a_missing_number_at_run_time_lists_what_this_defect_has():
    with pytest.raises(StepError) as e:
        _run(_ctx(glv_max=1.0), "glv_max + nope")
    text = str(e.value)
    assert "nope" in text and "glv_max" in text


def test_nothing_configured_yet_points_at_the_field():
    says = get_step(CARD).configuration_issues({"expr": "", "out": "value"})
    assert says and "Work out" in says[0]
    says = get_step(CARD).configuration_issues({"expr": "1+1", "out": ""})
    assert says and "Call the answer" in says[0]
    assert not get_step(CARD).configuration_issues({"expr": "1+1", "out": "v"})


def test_a_name_that_cannot_be_a_variable_is_refused():
    """輸出名會變成分數表達式的變數名 —— 打了空白就永遠指不到（鐵則 4）。"""
    from d4t.core.pipeline.step import ParamError

    with pytest.raises(ParamError):
        get_step(CARD).validate_params({"expr": "1+1", "out": "my value"})


# --------------------------------------------------------------------------- #
# 4. 它一張影像都不碰
# --------------------------------------------------------------------------- #
def test_it_never_reads_an_image():
    """Algo 段的定義。這裡驗這一張真的做得到 —— 整個 registry 的版本在
    `tests/test_ui_f16_stages.py::test_algo_cards_never_read_an_image_stream`。
    """
    card = get_step(CARD)
    assert card.resolve_reads({"expr": "glv_max", "out": "v"}) == []
    assert card.resolve_writes({"expr": "glv_max", "out": "v"}) == []
    # 而且真的跑得起來 —— Context 裡一張圖都沒有
    ctx = Context(images={})
    ctx.add_features({"glv_max": 4.0})
    _run(ctx, "sqrt(glv_max)")
    assert ctx.features["value"] == pytest.approx(2.0)
