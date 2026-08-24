# d4t step-card library — authored 2026-08-20 (F16：Algo 段第一張卡).
"""feature_math — **Feature math**：拿算出來的數字再算一個數字。

Algo 段是什麼（使用者 2026-08-20 定調）
--------------------------------------
> measure 是量出數值來，但 **Algo 是拿這些 feature 內去做更 custom 的處理**

寫成一條**自動套用到 registry 每一張卡**的性質：Algo 段的卡 ``resolve_reads()``
恆為空 —— 它一張影像都不碰。沒有那一條的話 Algo 會慢慢長成第二個 Measure，
而使用者要在兩個看起來一樣的段落裡猜他的卡在哪一段。

它解掉的是一個舊問題，不是新增一個能力
--------------------------------------
今天沒有這張卡也算得出來 —— 只是加減乘除**只能發生在分數表達式裡**
（``score.expr``）。而那裡：畫布上看不到、recipe 的 diff 讀不懂、算錯了也沒有
人擋得住，而且一份 recipe 只有**一條**表達式，所以中間值沒有地方放。

這正是 `Gray level` 的 compare 當初的立論（「這張卡不解鎖任何功能，它的價值是
那三件事變成可見的」）的一般化。

引擎的那一半本來就寫好了
------------------------
``pipeline/expression.py``：手寫 tokenizer + 遞迴下降 parser（**不是 eval**）、
SAFE 語意（除以 0 → 0.0、log(≤0) → 0.0、結果是 nan/inf → 0.0）、
**變數不存在會 raise**（那是 recipe 寫錯，要讓使用者看到，不是安靜給 0）、
錯誤訊息帶 caret 指出出錯的字元。這張卡一行都沒改它。

⚠ 已知的缺口：**畫布上沒有線指進這張卡**
-----------------------------------------
特徵是扁平的全域命名空間（見 docs/ARCHITECTURE.md），而 d4t 從來沒有「這個數字
是哪一張卡算的」這種埠 —— 分數表達式也是這樣。所以這張卡的相依性靠的是
**route 上的先後順序**，而畫布上看不出來。

擋在跑之前的是 ``Step.resolve_features_in()`` ＋ ``validate`` 的
``unknown-feature-input``（F16 一起加的）：指到一個沒人算出來的數字會是一條
error，而不是「每一顆 defect 都失敗」。那不等於畫布說了實話 —— 要讓它變成一條
線，得先決定**第三種埠**長什麼樣，而那個題目跟「跨顆那一層」是同一個
（見 docs/ROADMAP.md）。這裡明講，免得下一個人以為它已經解決了。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.context import Context
from ..pipeline.expression import ExpressionError, parse_expression
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_ALGO, ParamSpec, Step, StepError, register_step,
)
from ._util import FEATURE_PREFIX_PATTERN

#: 空的表達式是完全合法的 str，所以 ``validate_params`` 沒話說 —— 但那張卡跑起來
#: 每一顆都會失敗。這是 `configuration_issues` 存在的理由（F7-13）。
_DEFAULT_OUT = "value"


def _parsed(expr: str):
    """解析，失敗時把訊息改寫成**這張卡的話**。

    `ExpressionError` 的訊息開頭寫死是「Problem in the score expression」——
    那句話在這張卡上是錯的（使用者填的不是分數）。它把 ``desc`` / ``text`` /
    ``pos`` 都留著，所以重組一次就好，不必動 parser。
    """
    try:
        return parse_expression(str(expr))
    except ExpressionError as e:
        raise StepError(
            "feature_math",
            "problem in this card's expression (near character %d): %s\n"
            "    %s\n    %s^" % (e.pos + 1, e.desc, e.text, " " * e.pos))


@register_step
class FeatureMathStep(Step):
    """吃已經算出來的特徵，算一個新的（見模組 docstring）。"""

    key = "feature_math"
    label = "Feature math"
    category = CATEGORY_ALGO
    group = GROUP_ALGO
    help = ("Work out a new number from the numbers the cards above already "
            "measured - for example “glv_max - glv_median”. Use it to keep "
            "the arithmetic on the canvas instead of hiding it inside the "
            "score expression.")
    params = [
        ParamSpec(
            # ``expr`` 不是 ``str``：值的格式一字不差，但 UI 認得它是算式，
            # 於是那一格會配一支「插入數字 ▾」（F21-B）。
            name="expr", type="expr", default="",
            label="Work out",
            help=("The sum to work out. The names in it are the numbers the "
                  "cards above produce (glv_max, roi_snr_signed, …). You can "
                  "use + - * / ( ) and sqrt / abs / log / exp / min / max. "
                  "Comparisons work too and give 1 or 0, so "
                  "(cd_median > 5) * 100 turns a rule into a number. "
                  "Dividing by zero gives 0 rather than stopping the batch."),
        ),
        ParamSpec(
            name="out", type="str", default=_DEFAULT_OUT,
            label="Call the answer",
            pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Name for the number this card works out. It joins the "
                  "other numbers, so the score expression and the report can "
                  "both use it."),
        ),
    ]
    #: **一張影像都不碰** —— 那是 Algo 段的定義，`tests/test_ui_f16_stages.py`
    #: 對 registry 裡每一張 Algo 卡自動驗這件事。
    reads: List[str] = []
    writes: List[str] = []
    features_out = [_DEFAULT_OUT]

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", _DEFAULT_OUT) or "").strip()
        return [name] if name else []

    @classmethod
    def resolve_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """表達式裡用到的每一個變數（`validate` 的 unknown-feature-input）。

        **解析不出來就回空的**：那時候該講的話是「這個式子有語法錯」
        （`configuration_issues`），不是「你指到一個不存在的數字」——
        後者會把使用者送去查一個沒有問題的地方。
        """
        try:
            return sorted(parse_expression(str(params.get("expr", "") or "")).variables)
        except ExpressionError:
            return []

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        expr = str(params.get("expr", "") or "").strip()
        out = str(params.get("out", "") or "").strip()
        issues: List[str] = []
        if not expr:
            issues.append("This card has nothing to work out yet. Type a sum "
                          "into “Work out” - for example glv_max - glv_median.")
        else:
            try:
                parse_expression(expr)
            except ExpressionError as e:
                issues.append("“Work out” does not parse (near character %d): "
                              "%s" % (e.pos + 1, e.desc))
        if not out:
            issues.append("Give the answer a name in “Call the answer” - "
                          "without one there is nothing for the score "
                          "expression to refer to.")
        return issues

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        expr = str(p["expr"]).strip()
        out = str(p["out"]).strip()
        if not expr:
            raise StepError(self.key, "nothing to work out - type a sum into "
                                      "“Work out” (e.g. glv_max - glv_median).")
        if not out:
            raise StepError(self.key, "the answer needs a name - fill in "
                                      "“Call the answer”.")
        parsed = _parsed(expr)
        missing = sorted(v for v in parsed.variables if v not in ctx.features)
        if missing:
            # `Expression.eval` 也會擋，但它的訊息是通用的。這一句講得出
            # **這一顆手上有哪些數字**，而那正是使用者要拿來比對拼字的東西。
            raise StepError(
                self.key,
                "this defect has no number called %s. It has: %s."
                % (", ".join(missing), ", ".join(sorted(ctx.features)) or "none"))
        ctx.add_feature(out, parsed.eval(ctx.features))
        return ctx
