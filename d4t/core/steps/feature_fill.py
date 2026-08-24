# d4t step-card library — authored 2026-08-22 (Algo A1：量不到不是跑錯了).
"""feature_fill — **Missing numbers**：量不到的那一格，變成一個講得出來的狀態。

它解掉的是一個現成的洞，不是新增一個能力
----------------------------------------
專案有兩條各自都對的規矩，加起來留了一個縫：

* **「算不出來的那一格不寫」**（F18／F19 明講：不是 0、也不是 NaN）——
  所以一顆 CD 量不到的 defect，``cd_median`` 根本不在 ``ctx.features`` 裡。
* **「變數不存在會 raise」**（``pipeline/expression.py`` 的檔頭）—— 因為那通常
  是 recipe 打錯字，安靜給 0 會把使用者送去查一個沒有問題的地方。

縫在這裡：``engine._eval_score`` 攔到那個 raise 之後回 ``ok=False``，於是
**「量不到」跟「跑到一半炸掉」在結果表上長得一模一樣**。而在 fab 裡「量不到」
本身常常就是一種缺陷型態的訊號（結構整個被填掉、對比消失）—— 它應該分得進
某一類，不是被丟出批次。

為什麼不是「讓表達式容忍缺變數」
--------------------------------
因為那條 raise 要擋的是**打錯字**，而打錯字 ``validate`` 已經先擋掉了：

* ``unknown-feature-input``（error）—— 吃特徵的卡指到沒人產出的名字（F16）
* ``unknown-feature``（warning）—— ``score.expr`` 用到這條 route 不產出的名字

換句話說，**跑到執行期還缺的那一個，一定是「宣告了、但這一顆沒寫」**，也就是
資料，不是 recipe 寫錯。兩件事引擎已經分開了，所以這張卡只處理後者 —— 而讓
表達式一律容忍缺變數會把前者也一起吞掉。

⚠ 這同時是為什麼**沒有**「量不到」與「沒接線」兩種狀態（設計時問過的一題）：
沒接線在跑之前就是一條 error，執行期不可能遇到它。

寫出去的是兩個東西，而第二個才是重點
------------------------------------
* ``<name>`` —— 補上 ``fill``（讓下游的式子跑得完）
* ``<name>_missing`` —— **1 = 這一顆沒量到、0 = 量到了**，而且**永遠寫**

第二個是 F19 那條規矩的直接套用（「卡片自動做的每一個決定，都要變成一個使用者
畫得出分布的數字」）。少了它，CSV 上那 12 個 ``cd_median = 0`` 跟真的量到 0 的
那幾顆分不出來 —— 那正是這張卡本來要修的病，只是換一個地方發作。

旗標本身可以進分數表達式，而那是「量不到自成一類」的做法：
``cd_missing * 1000 + glv_mean`` —— 不必等多類別 ADC 就先有一條路。

⚠ 跨顆的卡要看那個旗標
----------------------
``lot_stats``（Algo 段的下一批）對一整欄取中位數時，**補進去的值要排除掉**
—— 12% 的假 0 會把中位數整個拉走。判斷「哪幾列算數」是**算中位數的那張卡**
的事，不是這一張的事。

所以這裡刻意**沒有**「只掛旗標、不補值」的模式：那個模式解不掉 raise，
也就解不掉這張卡存在的理由，而它會讓使用者以為自己選了一個安全的預設。

一張卡一個 ``fill``（F7-18 的規矩）
-----------------------------------
列在同一張卡上的每一個名字吃**同一個** ``fill`` —— 要讓兩個數字補不同的值就
放兩張卡。跟 Enhance 卡「要讓兩條流吃不同設定才放兩張卡」是同一條。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_ALGO, ParamSpec, Step, StepError, register_step,
)
from ._util import FEATURE_LIST_PATTERN, feature_list

#: 旗標的字尾。**不是參數**：它跟 ``<name>_center`` 一樣是算出來的名字，
#: 不是某一格填的字 —— 讓它可設定的話，同一件事在兩份 recipe 裡會有兩個名字，
#: 而報表與分數表達式那兩個地方沒有別的線索分辨它們是同一件事。
MISSING_SUFFIX = "_missing"


def _names(params: Dict[str, Any]) -> List[str]:
    return feature_list(params.get("features", ""))


@register_step
class FeatureFillStep(Step):
    """量不到的那一格補一個明講的值，並記下它本來沒量到（見模組 docstring）。"""

    key = "feature_fill"
    label = "Missing numbers"
    category = CATEGORY_ALGO
    group = GROUP_ALGO
    help = ("Decide what happens when a card above could not measure "
            "something on this defect. Without this, one unmeasurable defect "
            "is reported the same way as one that crashed.")
    params = [
        ParamSpec(
            # ``feature_keys`` 不是 ``str``：值的格式一字不差（逗號分隔），
            # 但 UI 認得它是一串數字名，於是那一格配得出「插入數字 ▾」——
            # 跟 `feature_math` 的算式共用同一支（F21-B）。
            name="features", type="feature_keys", default="",
            label="Numbers to check",
            pattern=FEATURE_LIST_PATTERN,
            pattern_help=("write the names separated by commas, for example "
                          "cd_median, cd_min"),
            help=("The numbers that may be missing on some defects - for "
                  "example cd_median. Separate several with commas. They all "
                  "get the same stand-in value; use a second card if you want "
                  "a different one."),
        ),
        ParamSpec(
            name="fill", type="float", default=0.0,
            min=-1e9, max=1e9,
            label="Use this instead",
            help=("The number to use when it is missing. This is a stand-in, "
                  "not a measurement - every defect also gets a "
                  "<name>_missing number that is 1 when the value was filled "
                  "in here and 0 when it was really measured."),
        ),
    ]
    #: **一張影像都不碰** —— Algo 段的定義（`tests/test_ui_f16_stages.py` 對
    #: registry 裡每一張 Algo 卡自動驗這件事）。
    reads: List[str] = []
    writes: List[str] = []
    features_out: List[str] = []

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        """只宣告旗標。

        ``<name>`` 本來就在命名空間裡（上游那張量測卡宣告的）—— 這張卡**保證
        它在**，不是**產出**它。把它也宣告出來的話 `validate` 會報一條
        ``feature-collision``，而那條警告要抓的是「兩張量測卡安靜地蓋掉彼此的
        量測值」：在這裡它是假警報，而使用者學會忽略一條警告之後，真的那一條
        也一起被忽略了（推廣鐵則）。
        """
        return [n + MISSING_SUFFIX for n in _names(params)]

    @classmethod
    def resolve_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """守的那幾個名字 —— 走 ``unknown-feature-input``（F16）。

        指到一個**沒有任何卡宣告**的名字仍然是 error，而那是刻意的：
        這張卡處理的是「宣告了但這一顆沒寫」，不是「根本沒人算」。
        後者補一個值只會讓一份壞掉的 recipe 安靜地跑完。
        """
        return _names(params)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        if not _names(params):
            return ["This card is not guarding anything yet. Type the name of "
                    "a number that can be missing into “Numbers to "
                    "check” - for example cd_median."]
        return []

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        names = _names(p)
        if not names:
            raise StepError(self.key,
                            "this card is not guarding anything - type a "
                            "number's name into “Numbers to check” "
                            "(e.g. cd_median).")
        fill = float(p["fill"])
        for name in names:
            if name in ctx.features:
                ctx.add_feature(name + MISSING_SUFFIX, 0.0)
            else:
                ctx.add_feature(name, fill)
                ctx.add_feature(name + MISSING_SUFFIX, 1.0)
        return ctx
