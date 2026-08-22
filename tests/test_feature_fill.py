# Algo A1：量不到不是跑錯了（feature_fill）。
"""這一份鎖住的是**「量不到」與「跑到一半炸掉」不再長得一樣**這件事。

在這張卡之前，兩條各自都對的規矩留了一個縫：

* 「算不出來的那一格不寫」（F18／F19）→ `cd_median` 根本不在 features 裡；
* 「變數不存在會 raise」（`expression.py`）→ 分數表達式炸掉；
* `engine._eval_score` 攔下來 → `ok=False`，跟真的跑錯了同一個樣子。

所以測的是五件事：

1. 缺的那一格補得上，而**已經量到的那一格一個位元都不動**；
2. **旗標永遠寫**（0 或 1）—— 沒有它，補進去的 0 跟真的量到 0 分不出來，
   那正是這張卡要修的病換一個地方發作；
3. 端到端：同一條分數表達式，補之前 raise、補之後算得出來；
4. 打錯字**仍然**是跑之前的 error（`unknown-feature-input`）——
   這張卡處理的是「宣告了但這一顆沒寫」，不是「根本沒人算」；
5. 它一張影像都不碰（Algo 段的定義）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step, validate  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.expression import (  # noqa: E402
    ExpressionError, parse_expression,
)
from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.pipeline.step import ParamError, StepError  # noqa: E402

CARD = "feature_fill"


def _ctx(**feats):
    ctx = Context(images={})
    ctx.add_features(feats)
    return ctx


def _run(ctx, features, fill=0.0):
    get_step(CARD)().run(ctx, {"features": features, "fill": fill})
    return ctx


# --------------------------------------------------------------------------- #
# 1. 補得上，而且沒量到的那一格才補
# --------------------------------------------------------------------------- #
def test_a_missing_number_gets_the_stand_in():
    ctx = _run(_ctx(glv_mean=100.0), "cd_median", fill=-1.0)
    assert ctx.features["cd_median"] == pytest.approx(-1.0)


def test_a_measured_number_is_left_exactly_as_it_was():
    """補值只能發生在**沒有**那一格的時候。

    這一條看起來理所當然，而它擋的是最貴的那種 bug：一張「保證欄位在」的卡
    如果順手覆寫已經量到的值，整批的數字會全部變成 fill —— 跑得完、有數字、
    而且是錯的。
    """
    ctx = _run(_ctx(cd_median=6.5), "cd_median", fill=-1.0)
    assert ctx.features["cd_median"] == 6.5


def test_one_card_guards_several_numbers_with_one_stand_in():
    ctx = _run(_ctx(cd_median=6.5), "cd_median, cd_min, cd_max", fill=0.0)
    assert ctx.features["cd_median"] == 6.5
    assert ctx.features["cd_min"] == 0.0 and ctx.features["cd_max"] == 0.0


# --------------------------------------------------------------------------- #
# 2. 旗標永遠寫 —— 這一條才是重點
# --------------------------------------------------------------------------- #
def test_the_flag_is_written_for_every_guarded_number_either_way():
    """0 與 1 都要寫得出來。

    只在缺的時候寫旗標的話，CSV 上那一欄會有空格，而「空白」在報表裡跟
    「這張卡沒跑」是同一個樣子 —— 使用者畫不出那一欄的分布（F19 的規矩：
    卡片自動做的每一個決定，都要變成一個畫得出分布的數字）。
    """
    ctx = _run(_ctx(cd_median=6.5), "cd_median, cd_min")
    assert ctx.features["cd_median_missing"] == 0.0
    assert ctx.features["cd_min_missing"] == 1.0


def test_the_flag_tells_a_filled_zero_from_a_measured_zero():
    """補進去的 0 與真的量到的 0，在數值上一模一樣 —— 分辨它們的是旗標。"""
    filled = _run(_ctx(), "cd_median", fill=0.0)
    real = _run(_ctx(cd_median=0.0), "cd_median", fill=0.0)
    assert filled.features["cd_median"] == real.features["cd_median"] == 0.0
    assert filled.features["cd_median_missing"] == 1.0
    assert real.features["cd_median_missing"] == 0.0


def test_the_flag_name_is_derived_not_configurable():
    """旗標的名字是算出來的（跟 `<name>_center` 同一條規矩），所以它不是一格。

    可設定的話，同一件事在兩份 recipe 裡會有兩個名字 —— 而報表與分數表達式
    那兩個地方沒有別的線索分辨它們是同一件事。
    """
    assert not any(p.name == "suffix" or "suffix" in p.name
                   for p in get_step(CARD).params)
    assert get_step(CARD).resolve_features({"features": "a, b"}) == \
        ["a_missing", "b_missing"]


# --------------------------------------------------------------------------- #
# 3. 端到端：同一條分數表達式，補之前炸、補之後算得出來
# --------------------------------------------------------------------------- #
SCORE = "cd_median * 2"


def test_without_the_card_the_score_expression_raises():
    """這就是這張卡存在的理由，寫成一條會紅的測試。

    `engine._eval_score` 攔下這個例外之後回 `ok=False` —— 於是「這一顆量不到」
    跟「這一顆跑錯了」在結果表上是同一件事。
    """
    ctx = _ctx(glv_mean=100.0)
    with pytest.raises(ExpressionError):
        parse_expression(SCORE).eval(ctx.features)


def test_with_the_card_the_same_expression_gets_a_number():
    ctx = _run(_ctx(glv_mean=100.0), "cd_median", fill=0.0)
    assert parse_expression(SCORE).eval(ctx.features) == pytest.approx(0.0)


def test_the_flag_can_carry_it_into_a_class_of_its_own():
    """「量不到自成一類」不必等多類別 ADC —— 旗標本來就是一個數字。"""
    ctx = _run(_ctx(glv_mean=100.0), "cd_median", fill=0.0)
    got = parse_expression("cd_median * 2 + cd_median_missing * 1000") \
        .eval(ctx.features)
    assert got == pytest.approx(1000.0)


# --------------------------------------------------------------------------- #
# 4. 打錯字仍然是跑之前的 error
# --------------------------------------------------------------------------- #
def _recipe(features, measure_first=True):
    nodes = {"load": RecipeNode("load", "load_patch", {})}
    route = ["load"]
    if measure_first:
        nodes["glv"] = RecipeNode("glv", "glv_stats",
                                  {"source": "test", "metrics": "glv_max"})
        route.append("glv")
    nodes["fill"] = RecipeNode("fill", CARD, {"features": features,
                                              "fill": 0.0})
    route.append("fill")
    return Recipe(recipe_id="t", routes={"ebi_patch": route}, nodes=nodes,
                  score=ScoreSpec(expr="glv_max", threshold=1.0,
                                  bins={"below": 0, "above": 1}))


def test_guarding_a_number_nobody_produces_is_still_an_error():
    """這張卡處理的是「宣告了但這一顆沒寫」，不是「根本沒人算」。

    後者補一個值只會讓一份壞掉的 recipe 安靜地跑完 —— 而那是這整段設計
    （`unknown-feature-input`，F16）當初要擋的東西。
    """
    codes = {i.code for i in validate(_recipe("glv_max", measure_first=False))
             if i.level == "error"}
    assert "unknown-feature-input" in codes, codes


def test_guarding_a_number_someone_declares_is_fine():
    errs = [i for i in validate(_recipe("glv_max")) if i.level == "error"]
    assert not errs, errs


def test_it_does_not_declare_the_number_it_fills():
    """**刻意的不對稱**：`run()` 寫 `<name>`，但只有 `<name>_missing` 被宣告。

    這一條違反 I3（`test_card_invariants` 的「只碰宣告過的東西」）的字面，
    而 I3 講明它要擋的害處是：

    > 它會出現在 feature 表與 score 表達式的自動完成裡，**但沒有任何地方
    > 說得出它從哪來**

    那個害處在這裡不會發生，而且是引擎保證的：`resolve_features_in` 讓
    `unknown-feature-input`（error）擋住「沒有任何卡宣告這個名字」的 recipe
    —— 所以跑得起來的每一份，`<name>` 都已經有一個上游的擁有者。這張卡填的
    是那個名字上的一個洞，不是憑空生一個新名字。

    反過來宣告它的代價是實的：`<name>` 的擁有者（量測卡）不是診斷數字，所以
    `feature-collision` 的「兩邊都是診斷才跳過」不成立 —— 每一份**正確**使用
    這張卡的 recipe 都會多一條警告，而使用者學會忽略一條警告之後，真的那一條
    也一起被忽略了（推廣鐵則、F11 Enhance-3 的原話）。
    """
    card = get_step(CARD)
    assert card.resolve_features({"features": "cd_median"}) == \
        ["cd_median_missing"]
    assert card.resolve_features_in({"features": "cd_median"}) == ["cd_median"]
    warns = {i.code for i in validate(_recipe("glv_max"))}
    assert "feature-collision" not in warns, warns


def test_it_writes_nothing_else_beyond_that():
    """I3 的專屬版本 —— 用**設定好的**參數跑，比那個 harness 問得更嚴。

    `feature_fill` 在 `test_card_invariants.NEEDS_MORE_SETUP` 上（預設沒設定
    完，跟 `feature_math` 一字不差），所以 I3 跳過它。跳過的東西要有人接：
    這一條把「除了 `<name>` 與 `<name>_missing` 之外一個都不准多寫」釘住。
    """
    guarded = {"cd_median", "cd_min"}
    ctx = _ctx(glv_mean=100.0)
    before = set(ctx.features)
    _run(ctx, "cd_median, cd_min", fill=0.0)
    new = set(ctx.features) - before
    assert new == guarded | {n + "_missing" for n in guarded}, sorted(new)
    # 已經在的那幾個一個都沒動
    assert ctx.features["glv_mean"] == 100.0


# --------------------------------------------------------------------------- #
# 5. 設定與界線
# --------------------------------------------------------------------------- #
def test_an_empty_card_says_so_instead_of_running_empty():
    says = get_step(CARD).configuration_issues({"features": "", "fill": 0.0})
    assert says and "Numbers to check" in says[0]
    with pytest.raises(StepError):
        _run(_ctx(), "")


def test_names_are_tidied_and_deduplicated():
    card = get_step(CARD)
    assert card.resolve_features_in({"features": " cd_median ,cd_min, cd_median "}) \
        == ["cd_median", "cd_min"]


def test_a_name_that_cannot_be_an_expression_variable_is_refused():
    """特徵名是分數表達式的變數名 —— `cd median` 在那裡指不到（鐵則 4）。

    擋在 `validate_params`（`ParamSpec.pattern`），不是等它跑進演算法：
    打了空白的那個名字在表達式裡永遠指不到，而症狀會出現在很遠的地方。
    """
    with pytest.raises(ParamError):
        get_step(CARD).validate_params({"features": "cd median", "fill": 0.0})


def test_it_never_touches_an_image():
    assert get_step(CARD).resolve_reads({"features": "cd_median"}) == []
    assert get_step(CARD).resolve_writes({"features": "cd_median"}) == []
