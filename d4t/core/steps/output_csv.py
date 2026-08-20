# d4t step-card library — authored 2026-08-20 (F16：Output 段第一張卡).
"""output_csv — **Write CSV**：整批跑完之後，把結果寫成一份明細表。

Output 段是什麼（使用者 2026-08-20 定調）
-----------------------------------------
> Output 我預期要可以產出多種 style（分 card），例如 Report / csv / klarf /
> html 檔案，要單純 output image 也可（**他就是個 end point**）

「end point」寫成一條**自動套用到 registry 每一張卡**的性質：Output 段的卡
``resolve_writes()`` 與 ``resolve_features()`` 都是空的。一旦它吐了東西，下游就
接得上它，而「這一段是最後一段」那句話就不再成立。

**這一張是那五張裡的第一張**，而它先做的理由是驗得動：它產的 CSV 要跟 Export
精靈現在產的**逐格相同**（同一支 `core/export/report.write_csv`），所以「換一條
路，東西沒變」這件事是可以量的 —— 那是之後拿掉精靈的前提。

它為什麼是 ``is_batch``
-----------------------
CSV 是**一批一份**（一顆一列），而 ``run_defect`` 一顆一顆跑。所以它不是普通
的 Step：引擎的分工是 ``run_defect`` 跳過它，`batch.run_batch_steps` 在所有結果
收齊之後跑它一次。（``output_image`` 是這一段裡唯一逐顆的那張，之後那張不是
``is_batch``。）

⚠ **試跑不會寫**（使用者定調）
------------------------------
Studio 的 Run trial 是調參數的迴圈 —— 每拖一下門檻就覆寫一次檔案是不可逆的。
機制上那件事不是一個旗標，是**兩支函式**：試跑那條路根本不叫
`run_batch_steps`。規則因此是一句話：**要寫出東西的那條路自己叫它。**

⚠ **路徑存在卡片上**（使用者定調：「卡上存完整路徑」）
------------------------------------------------------
所以一份 recipe 搬到另一台機器上時，這一格要跟著改 —— 而 `configuration_issues`
會在還沒填的時候就講出來（不是等跑完才發現什麼都沒寫出去）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ..export import report as export_report
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ADC, GROUP_OUTPUT, ParamSpec, Step, StepError, register_step,
)


@register_step
class OutputCsvStep(Step):
    """整批的結果 → 一份 CSV（見模組 docstring）。"""

    key = "output_csv"
    label = "Write CSV"
    category = CATEGORY_ADC
    group = GROUP_OUTPUT
    #: 整批跑完之後跑一次（見 `Step.is_batch`）。
    is_batch = True
    help = ("Write one row per defect to a CSV file when the whole lot has "
            "run - the id, whether it worked, the score, the bin and every "
            "number the cards above measured. This is the feature table, so "
            "it is also what you would feed to a classifier later.")
    params = [
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the CSV file to write, including the file "
                  "name (for example C:\\\\work\\\\lot123\\\\defects.csv). Folders "
                  "that do not exist yet are created. A recipe carries this "
                  "path with it, so check it after moving a recipe to another "
                  "machine."),
        ),
        ParamSpec(
            name="include_features", type="bool", default=True,
            label="Include the measured numbers",
            help=("On: one column per number the cards above produced (the "
                  "feature table). Off: only the id, whether it worked, the "
                  "score and the bin."),
        ),
    ]
    #: **end point**：不吐流、不吐特徵。有測試對整段自動驗這件事。
    reads: List[str] = []
    writes: List[str] = []
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return []

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return []

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        path = str(params.get("path", "") or "").strip()
        if not path:
            return ["This card has nowhere to write yet. Put the full path of "
                    "the CSV file into “Write to”."]
        if os.path.isdir(path):
            # 指到一個**資料夾**是使用者最容易犯的那一個（貼了路徑忘了加檔名），
            # 而跑起來的症狀是 `IsADirectoryError` —— 那句話對他沒有意義。
            return ["“%s” is a folder, not a file. Add the file name to the "
                    "end of the path (for example …\\defects.csv)." % path]
        return []
        # ⚠ **不檢查「資料夾存不存在」**：`report.write_csv` 會自己建
        # （`_ensure_parent`），而 Export 精靈走的是同一支。在這裡擋的話，
        # 一個完全正常的路徑會被說成設定錯誤。第一版真的這樣寫了，測試抓到。

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        """**不會被呼叫**：``is_batch`` 的卡由 `run_batch_steps` 跑。

        留一句明白的話而不是 ``pass``：哪天有人在別的地方照普通 Step 的樣子叫
        它，症狀會是「CSV 沒寫出來」而不是一個講得清楚的錯誤。
        """
        raise StepError(
            self.key,
            "this card runs once after the whole lot has been processed, not "
            "once per defect. If you are seeing this, something ran it the "
            "wrong way round.")

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = str(p["path"]).strip()
        if not path:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        try:
            written = export_report.write_csv(
                bctx.rows, path, include_features=bool(p["include_features"]))
        except OSError as e:
            # 磁碟滿了、沒有權限、路徑不合法 —— 都是使用者修得動的事，所以
            # 訊息要帶原因與路徑，不要只說「寫入失敗」。
            raise StepError(self.key,
                            "could not write %s: %s" % (path, e)) from e
        bctx.add_output(written)
