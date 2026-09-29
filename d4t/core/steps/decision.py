# d4t 卡片 — Decision（F123 期 1，2026-09-29）。
"""**判定是一張卡**：畫布上跟其他卡同一種東西，點開是判定樹。

使用者（2026-09-29）：「我會覺得對畫布來說很奇怪，不管是 ADC card 或者是
Output card 的定位（理論上 input = output）」→「我想直接做 B」。

以前判定不是一張卡：它是 recipe 最上層的 ``decide``，畫布上畫成一個紫色虛線框
（`tree_scene._ZoneItem`），卡片庫裡有一張叫「Decision」的偽卡（``__score__``）。
這一張卡讓它跟 Input、Output 同一種身分 —— 從卡片庫加、在畫布上拖、刪得掉，
下一期（F123 期 2）它會有埠：數字從量測卡接進來、結果接出去給 Output。

**判定的內容仍然住在 ``recipe.decide``**（let ／ 樹 ／ 分數）。這張卡是它在
畫布上的**那一張**：一份 recipe 最多一張（`validate` 的 ``duplicate-decision``），
刪掉這張卡＝拿掉判定（`RecipeModel.remove`）。把整個 ``decide`` 搬進這張卡的
參數要改一百多處引用（F48 §2 量過），而那件事對使用者看得到的東西沒有差別。

**引擎不在這裡判**：判定要等整條 pipeline 的數字都算完（`engine._eval_score`），
而這張卡在執行順序上排在量測卡後面 —— 它的 ``run`` 是 no-op，不是「還沒做」。
"""
from __future__ import annotations

from typing import Any, Dict

from ..pipeline.context import Context
from ..pipeline.step import CATEGORY_ADC, GROUP_ADC, Step, register_step


@register_step
class DecisionStep(Step):
    key = "decision"
    label = "Decision"
    category = CATEGORY_ADC
    group = GROUP_ADC
    help = ("Sorts every defect into a class with a decision tree - questions "
            "about the numbers the cards measured, each class with its own bin. "
            "One per recipe; click the card to open its tree.")
    params = []
    reads = []
    writes = []
    features_out = []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        # 判定在整條 pipeline 跑完之後才算（`engine._eval_score`）——
        # 那時候每一張量測卡的數字都在了。這一張卡是它在畫布上的位置。
        return ctx
