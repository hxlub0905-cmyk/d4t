# ADEPT step-card library — authored 2026-08-15 (F9 Phase 3a).
"""adc — 判定卡：把特徵算成分數、跟門檻比、給一個 bin。

為什麼判定要變成卡片
--------------------
在這張卡之前，判定是 ``Recipe.score`` 這個**固定欄位**：一份 recipe 只有一條
分數式子、一個門檻，而且它不在畫布上（藏在另一個設定頁）。那個形狀擋住兩件事：

1. **一份 recipe 只能有一套標準。** 而使用者要的是「``CLASSNUMBER=1`` 走 A、
   ``=2`` 走 B」—— 兩條分支的門檻本來就該不一樣（A 是已知的真缺陷要抓乾淨、
   B 是雜訊要濾掉），硬綁成同一個數字等於兩邊都調不好。
2. **判定看不見。** 使用者在畫布上看到流程走到量測就結束了，最後那個決定
   發生在別的地方。

變成卡片之後兩件事都自然：**一張圖可以放好幾張判定卡**，每條分支自己一張，
而且它就在畫布上那條線的末端。

沒有任何一張判定卡跑到的時候
----------------------------
這顆 defect **沒有結論** —— 不是 0 分。這是刻意的：0 分是個看起來很像答案的
答案（它會被排序、被寫進報表、被當成「很乾淨」），而真相是「這條分支上沒有
人做決定」。引擎會把 score/bin 留成 None 並在 warnings 裡講出來。
（跟 ``cd_x_nm`` 恆為 0 那個坑是同一類，見 CLAUDE.md §8。）
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.context import Context
from ..pipeline.expression import ExpressionError, parse_expression
from ..pipeline.step import (
    CATEGORY_ADC, GROUP_ADC, ParamSpec, Step, StepError, register_step,
)

#: 判定結果放在 ``ctx.meta`` 的哪個鍵（引擎讀它）。
VERDICT_KEY = "_verdict"

#: 判定卡的輸出埠名。它是尾節點，但仍然吐一包出去 —— 這樣「判定完還想再做
#: 什麼」（寫回、輸出、再分流）之後就是普通的接線，不必給它特例。
VERDICT_PORT = "verdict"


@register_step
class AdcStep(Step):
    """判定：``score = expr(features)``，跟門檻比，給 bin。"""

    key = "adc"
    label = "Decide"
    category = CATEGORY_ADC
    group = GROUP_ADC
    help = ("Turn the numbers measured upstream into one score, compare it "
            "with a threshold, and put the defect in a bin. Put one of these "
            "at the end of each branch - two branches can use different "
            "thresholds.")
    inputs = ("in",)
    outputs = (VERDICT_PORT,)

    params = [
        ParamSpec(
            name="expr", type="expr", default="",
            label="Score",
            help=("An expression built from the feature names produced "
                  "upstream, for example  snr_max * 2 - glv_std . You can use "
                  "+ - * / ( ) and sqrt / abs / min / max / log / exp.")),
        ParamSpec(
            name="threshold", type="float", default=0.0,
            label="Threshold",
            help="Score at or above this goes in the 'above' bin."),
        ParamSpec(
            name="label", type="str", default="",
            label="Name this decision",
            help=("Optional name for this decision, so a recipe with several "
                  "of them can say which one decided this defect.")),
        # 這兩格**幾乎沒有人會改**（0 / 1 對絕大多數站點就是對的），而它們有
        # 上下界所以會各自配到一支滑桿 —— 一支 0–999 的滑桿拿來挑 bin 編號既
        # 沒有用又是整張表上最搶眼的東西。真正要調的是上面那兩格。
        ParamSpec(
            name="bin_below", type="int", default=0, min=0, max=999,
            label="Bin when below", advanced=True,
            help="Which bin number to write when the score is below the threshold."),
        ParamSpec(
            name="bin_above", type="int", default=1, min=0, max=999,
            label="Bin when at or above", advanced=True,
            help="Which bin number to write when the score reaches the threshold."),
    ]
    reads: List[str] = []
    writes: List[str] = []
    features_out = ["score"]

    # ---- 「還沒設定完」（F7-13 的機制）------------------------------------
    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        expr = str(params.get("expr", "") or "").strip()
        if not expr:
            return ["This card has no score expression yet. Type one in the "
                    "Score box, or pick the names measured upstream from the "
                    "Insert feature ▾ list next to it."]
        try:
            parse_expression(expr)
        except ExpressionError as e:
            return [str(e)]
        return []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        expr_text = str(p["expr"]).strip()
        if not expr_text:
            raise StepError(self.key, "no score expression is set on this card")
        try:
            expr = parse_expression(expr_text)
        except ExpressionError as e:
            raise StepError(self.key, str(e)) from None

        score = expr.eval(ctx.features)
        ctx.features["score"] = score
        thr = float(p["threshold"])
        bin_ = int(p["bin_above"]) if score >= thr else int(p["bin_below"])
        ctx.meta[VERDICT_KEY] = {
            "score": float(score),
            "bin": bin_,
            "by": str(p["label"] or ""),
        }
        return ctx
