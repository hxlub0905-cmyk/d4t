# d4t step-card library — authored 2026-08-20 (F16：Output 段).
"""Output 段的卡：整批跑完之後，把結果寫出去。

Output 段是什麼（使用者 2026-08-20 定調）
-----------------------------------------
> Output 我預期要可以產出多種 style（分 card），例如 Report / csv / klarf /
> html 檔案，要單純 output image 也可（**他就是個 end point**）

「end point」寫成一條**自動套用到 registry 每一張卡**的性質：Output 段的卡
``resolve_writes()`` 與 ``resolve_features()`` 都是空的。一旦它吐了東西，下游就
接得上它，而「這一段是最後一段」那句話就不再成立。

四張卡，每一張都薄薄一層包在既有的 `core/export/` 上 —— **演算法一行都沒重寫**，
而那是「換一條路，東西沒變」可以被量出來的原因（見
`tests/test_batch_steps.py` 的逐位元組比對，那是之後拿掉 Export 精靈的前提）。

===============  ==========================================  =================
卡               寫什麼                                      引擎
===============  ==========================================  =================
``output_csv``   一顆一列的明細表（＝ feature vector）        `export/report`
``output_report`` Excel：摘要 / 明細 / 特徵統計三張表         `export/report`
``output_klarf``  寫回 KLARF（三種模式）                      `export/klarf_out`
``output_image``  每顆一張疊圖 PNG                            `export/overlay`
===============  ==========================================  =================

**四張的尺度都是「整批一次」（``scale = SCALE_LOT``），包含 ``output_image``。**
前三張顯然是（一批一個檔案）。第四張看起來是逐顆的 —— 但它如果做成普通 Step，
它就會在 ``run_defect`` 裡跑，而那條路**每切換一顆 defect 就走一次**：使用者
瀏覽 defect 的時候會一直寫 PNG 出來。所以它也是整批跑完之後跑一次，一顆一顆
重跑 pipeline 取影像（那正是 Export 精靈今天做的事）。

規則因此是一句話：**Output 段的卡都是整批一次。**

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

from ..export import html as export_html
from ..export import klarf_out, overlay
from ..export import report as export_report
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_BATCH, GROUP_OUTPUT, SCALE_LOT, ParamSpec, Step, StepError,
    register_step,
)



class _OutputStep(Step):
    """Output 段共用的基底：**end point**，而且整批跑完之後跑一次。

    子類只實作 :meth:`run_batch`。這裡把三件每一張都一樣的事寫一次 ——
    宣告（不吐流、不吐特徵）、``run`` 的那句拒絕、以及「路徑填了沒」。
    四張各寫一份的話，第五張加進來時會漏掉其中一件，而漏掉宣告的那一份
    症狀是「這張卡下面居然接得上東西」。
    """

    # **整批那一層**（F17-③）。以前這裡填 CATEGORY_ADC —— 不是因為這幾張卡
    # 在做 ADC，而是因為那個值剛好讓它們落在快取 checkpoint 之後。
    # 快取邊界改成從宣告推導之後，這一格可以講實話了。
    category = CATEGORY_BATCH
    group = GROUP_OUTPUT
    # **整批一次**（F17-④）。`is_batch` 現在是這一格推導出來的 ——
    # 直接寫 `is_batch = True` 仍然認得（舊卡片、外掛），但新的卡片
    # 請宣告尺度：布林答不出「還有第三種嗎」。
    scale = SCALE_LOT
    reads: List[str] = []
    writes: List[str] = []
    features_out: List[str] = []

    #: 那一格路徑的參數名（子類要換名字的話覆寫）。
    PATH = "path"
    #: `configuration_issues` 講「這裡填什麼」時用的字（子類覆寫）。
    WHAT = "file"

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
        path = str(params.get(cls.PATH, "") or "").strip()
        if not path:
            return ["This card has nowhere to write yet. Put the full path of "
                    "the %s into “Write to”." % cls.WHAT]
        if cls.PATH == "path" and os.path.isdir(path):
            # 指到一個**資料夾**是使用者最容易犯的那一個（貼了路徑忘了加檔名），
            # 而跑起來的症狀是 `IsADirectoryError` —— 那句話對他沒有意義。
            return ["“%s” is a folder, not a file. Add the file name to the "
                    "end of the path." % path]
        return []
        # ⚠ **不檢查「資料夾存不存在」**：`report.write_csv` 那一族會自己建
        # （`_ensure_parent`），而 Export 精靈走的是同一支。在這裡擋的話，
        # 一個完全正常的路徑會被說成設定錯誤。第一版真的這樣寫了，測試抓到。

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        """**不會被呼叫**：整批一次的卡由 `run_batch_steps` 跑。

        留一句明白的話而不是 ``pass``：哪天有人在別的地方照普通 Step 的樣子叫
        它，症狀會是「檔案沒寫出來」而不是一個講得清楚的錯誤。
        """
        raise StepError(
            self.key,
            "this card runs once after the whole lot has been processed, not "
            "once per defect. If you are seeing this, something ran it the "
            "wrong way round.")

    def _path_of(self, p: Dict[str, Any]) -> str:
        path = str(p[self.PATH]).strip()
        if not path:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        return path


@register_step
class OutputCsvStep(_OutputStep):
    """整批的結果 → 一份 CSV（見模組 docstring）。"""

    key = "output_csv"
    label = "Write CSV"
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
    WHAT = "CSV file"

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = self._path_of(p)
        try:
            written = export_report.write_csv(
                bctx.rows, path, include_features=bool(p["include_features"]))
        except OSError as e:
            # 磁碟滿了、沒有權限、路徑不合法 —— 都是使用者修得動的事，所以
            # 訊息要帶原因與路徑，不要只說「寫入失敗」。
            raise StepError(self.key,
                            "could not write %s: %s" % (path, e)) from e
        bctx.add_output(written)


@register_step
class OutputReportStep(_OutputStep):
    """整批的結果 → 一份 Excel 報表（摘要 / 明細 / 特徵統計）。"""

    key = "output_report"
    label = "Write report"
    WHAT = "Excel file"
    help = ("Write an Excel report when the whole lot has run: a summary "
            "sheet (how many, how they split across bins, the score range), "
            "the same table the CSV card writes, and one row per measured "
            "number with its range. If the lot has an answer sheet next to "
            "it, the summary also shows how often the pipeline agreed.")
    params = [
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the .xlsx file to write, including the file "
                  "name. Folders that do not exist yet are created."),
        ),
    ]

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = self._path_of(p)
        try:
            written = export_report.write_excel(bctx.rows, path,
                                                recipe=bctx.recipe)
        except ImportError as e:
            # openpyxl 沒裝 —— 那是**環境**的事，不是 recipe 的事，所以訊息要
            # 指向 `tools/install_offline.py`（公司機裝不了東西，見 AGENTS.md）。
            raise StepError(
                self.key,
                "cannot write Excel here: %s. Install openpyxl (on the fab "
                "machine: tools/install_offline.py), or use the CSV card "
                "instead - it needs nothing extra." % e) from e
        except OSError as e:
            raise StepError(self.key,
                            "could not write %s: %s" % (path, e)) from e
        bctx.add_output(written)


@register_step
class OutputKlarfStep(_OutputStep):
    """整批的結果 → 寫回 KLARF（三種模式）。"""

    key = "output_klarf"
    label = "Write KLARF"
    WHAT = "KLARF file"
    help = ("Write the results back into a KLARF file when the whole lot has "
            "run. “annotate” keeps the original untouched and saves a new "
            "file with the score and class added; “in place” edits the "
            "original, changing only the bytes it has to; “top N” saves a new "
            "file holding just the highest scoring defects.")
    params = [
        ParamSpec(
            name="mode", type="choice", default="annotate",
            choices=list(klarf_out.MODES),
            label="How to write it",
            help=("annotate = a new file with ADCSCORE and ADCCLASS added "
                  "(the original is untouched - start here). inplace = edit "
                  "the original file, changing only the bytes that have to "
                  "change. topn = a new file with only the highest scoring "
                  "defects in it."),
        ),
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the KLARF file to write. Folders that do not "
                  "exist yet are created. For “in place” this is the file "
                  "that gets edited, so point it at the original."),
        ),
        # ---- mode = topn ---------------------------------------------------
        ParamSpec(
            name="top_n", type="int", default=100, min=0, max=1000000,
            show_when=("mode", ("topn",)),
            label="How many to keep",
            help=("How many of the highest scoring defects to write out. Set "
                  "it to 0 to use the score threshold below instead."),
        ),
        ParamSpec(
            name="min_score", type="float", default=0.0, min=-1e9, max=1e9,
            show_when=("mode", ("topn",)),
            label="…or keep everything scoring at least",
            help=("Used only when “How many to keep” is 0: keep every defect "
                  "whose score is this or higher, however many that turns out "
                  "to be."),
        ),
        ParamSpec(
            name="renumber", type="bool", default=True,
            show_when=("mode", ("topn",)),
            label="Renumber the defects 1, 2, 3…",
            help=("On: the defects in the new file are numbered from 1. Off: "
                  "they keep the ids they had in the original, so you can "
                  "still match them up."),
        ),
        ParamSpec(
            name="include_annotations", type="bool", default=True,
            show_when=("mode", ("topn",)),
            label="Also add the score and class columns",
            help=("On: the new file also gets the ADCSCORE and ADCCLASS "
                  "columns, the same as the annotate mode writes."),
        ),
        # ---- mode = inplace --------------------------------------------------
        # 這四格是「寫進**既有**的欄位」—— inplace 的全部意義。一格都不填的話
        # 輸出檔與原檔**逐位元組相同**（`apply_writeback` 的契約），而那正是
        # 使用者第一次按下去時該發生的事。
        ParamSpec(
            name="class_col", type="str", default="",
            show_when=("mode", ("inplace",)),
            label="Write the class into",
            help=("Name of an existing column to write the bin number into "
                  "(CLASSNUMBER is the usual one). Leave it empty to not "
                  "touch it. The column has to be there already - in place "
                  "never adds columns."),
        ),
        ParamSpec(
            name="bin_col", type="str", default="",
            show_when=("mode", ("inplace",)),
            label="…and also into",
            help=("A second existing column for the same bin number "
                  "(ROUGHBINNUMBER or FINEBINNUMBER). Leave it empty to not "
                  "touch it."),
        ),
        ParamSpec(
            name="size_col", type="str", default="",
            show_when=("mode", ("inplace",)),
            label="Write the size into",
            help=("Name of an existing column to write a measured size into "
                  "(DSIZE is the usual one). Leave it empty to not touch it."),
        ),
        ParamSpec(
            name="size_feature", type="str", default="cd_median",
            advanced=True, show_when=("mode", ("inplace",)),
            label="…using this number",
            help=("Which measured number goes into the size column. Only used "
                  "when a size column is named above."),
        ),
        ParamSpec(
            name="size_scale", type="float", default=1.0, min=0.0, max=1e6,
            advanced=True, show_when=("mode", ("inplace",)),
            label="nm per pixel for sizes",
            help=("What to multiply the measured pixel sizes by before "
                  "writing them into the size column. Leave it at 1 to write "
                  "pixels, which is what everything in this pipeline "
                  "measures."),
        ),
    ]

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = self._path_of(p)
        doc = getattr(bctx.dataset, "klarf", None)
        if doc is None:
            # 沒有 KLARF 的兩種輸入（folder / tiff_stack）—— 那件事在載入的當下
            # 就講過了（資料集標籤上常駐 `· no KLARF`），這裡不要假裝是別的問題。
            raise StepError(
                self.key,
                "this data has no KLARF to write back into (it came from a "
                "folder of images or a TIFF stack, which carry no "
                "coordinates). Use the CSV or report card instead.")
        # **每個 mode 吃的選項不一樣**，而 `apply_writeback` 會把多給的那個
        # 當成錯誤（那是對的 —— 悄悄忽略一個使用者填了的值更糟）。
        # `size_scale` 只有 inplace 用得到（它是寫進 DSIZE 欄的那個換算）。
        opts: Dict[str, Any] = {}
        mode = str(p["mode"])
        if mode == "topn":
            # ⚠ 引擎那一邊的關鍵字是 **`n`**（`_build_topn`），不是 `top_n`。
            # 參數名維持 `top_n`（recipe 的鍵，而且 `n` 對使用者不是一句話），
            # 在這裡轉一次。第一版直接送 `top_n` —— 它落進 `**annot_opts`，
            # 於是 **每一次 topn 寫回都失敗**，而測試只覆蓋了 annotate。
            opts["n"] = int(p["top_n"])
            opts["min_score"] = float(p["min_score"])
            opts["renumber"] = bool(p["renumber"])
            opts["include_annotations"] = bool(p["include_annotations"])
        elif mode == "inplace":
            opts["size_scale"] = float(p["size_scale"])
            opts["size_feature"] = str(p["size_feature"]).strip() or "cd_median"
            # **空字串 = 不要碰那一欄**，所以空的不能送進去 —— 送了的話
            # `apply_writeback` 會去找一個叫 "" 的欄位然後報「沒有這個欄位」。
            for name, key in (("class_col", "class_col"),
                              ("bin_col", "bin_col"),
                              ("size_col", "size_col")):
                value = str(p[name]).strip()
                if value:
                    opts[key] = value
        try:
            plan = klarf_out.apply_writeback(doc, bctx.rows, str(p["mode"]),
                                             path, **opts)
        except klarf_out.ExportError as e:
            raise StepError(self.key, str(e)) from e
        except OSError as e:
            raise StepError(self.key,
                            "could not write %s: %s" % (path, e)) from e
        bctx.add_output(path)
        # 寫回是**不可逆**的，所以「到底改了幾列」要講出來 —— 那是 M5 的
        # 「寫回前一定先預覽變更」在 CLI 這一側剩下的那一半。
        bctx.warn("KLARF %s: %d row(s) changed, %d row(s) written."
                  % (str(p["mode"]), int(getattr(plan, "n_rows_changed", 0)),
                     int(getattr(plan, "n_rows_out", 0))))
        # **`plan.notes` 也要帶出來**（B6，2026-08-24）。`klarf_out` 已經把
        # 「為什麼」寫好了，而以前只有計數走得出來 —— 於是 inplace 一格目標
        # 欄位都沒填的時候，使用者看到的是「0 row(s) changed」，
        # 一句答不出「那我該填什麼」的話。那份說明就在手上：
        #
        #   "No target column was given (class_col / bin_col / size_col are
        #    all empty), so the output file will be byte-for-byte identical
        #    to the original."
        #
        # 其他 mode 的 notes 同樣有用（影像參照怎麼處理、幾顆對不到 DEFECTID、
        # DSIZE 那一欄的單位換算）—— 那些以前也全部沒有出口。
        for note in (getattr(plan, "notes", None) or []):
            bctx.warn("KLARF %s: %s" % (str(p["mode"]), note))


def _warn_if_unranked(key: str, bctx: Any, rows: Any,
                      rank_by: str, limit: int) -> None:
    """一顆都排不出來 ⇒ **講出來**（F30）。

    安靜地退回檔案順序正是這一輪要修的那個 bug：使用者拿到 N 張正常的圖，
    而「最值得看的那 N 顆」這件事完全沒有發生。``limit`` 是 0（全部）時順序
    只影響報表上的排列，話還是要講 —— 但語氣不同，所以分開寫。
    """
    if not overlay.rank_is_meaningless(rows, rank_by):
        return
    what = ("no defect has a score - a decision tree classifies without one"
            if rank_by == overlay.RANK_BY_SCORE
            else "no defect has a number called “%s”" % rank_by)
    if limit and len(list(rows or [])) > limit:
        bctx.warn("%s: %s, so “Worst first, by” had nothing to sort on and "
                  "these are simply the first %d defects in the file, not the "
                  "worst %d. Put the name of a number you measure in that box."
                  % (key, what, limit, limit))
    else:
        bctx.warn("%s: %s, so the order is the order they came in. Put the "
                  "name of a number you measure in “Worst first, by” if you "
                  "want the worst at the top." % (key, what))


def rank_by_spec() -> ParamSpec:
    """出圖那兩張卡共用的「照什麼排」（F30，2026-08-25）。

    **兩張卡逐字同一格** —— 同一句話在兩個地方長出兩種意思，是這個 repo 最常
    踩的形狀（`_util.py` 裡那幾個共用 spec 同一個理由）。

    為什麼需要它：**判定樹是一個分類器，多數樹沒有分數表達式**，於是那一批
    一顆分數都沒有 —— 而「取分數最高的前 N 顆」在全部同分（或全部沒有）的時候
    會安靜地退回**檔案順序**。使用者要的排序因此完全沒有發生，而畫面上是 N 張
    正常的圖。
    """
    return ParamSpec(
        name="rank_by", type="str", default=overlay.RANK_BY_SCORE,
        label="Worst first, by", advanced=True,
        help=("Which number decides the order, highest first. Leave it as "
              "“score” if your recipe has a score formula. If you classify "
              "with a decision tree instead, there is no score - put the name "
              "of a number you measure here (for example blob_strength, "
              "cmp_snr_mean or cd_area_px), otherwise the pictures come out "
              "in file order."))


@register_step
class OutputImageStep(_OutputStep):
    """每一顆一張疊圖 PNG（整批跑完之後一顆一顆重跑取影像）。"""

    key = "output_image"
    label = "Write images"
    PATH = "folder"
    WHAT = "folder"
    help = ("Write one PNG per defect when the whole lot has run: the image "
            "the pipeline worked on, side by side with the difference image "
            "when there is one. This is what the machine saw, not the raw "
            "picture - which is the point of looking at it.")
    params = [
        ParamSpec(
            name="folder", type="str", default="",
            label="Write to",
            help=("Folder to write the PNG files into, one per defect, named "
                  "after the defect id. It is created if it does not exist."),
        ),
        ParamSpec(
            name="limit", type="int", default=200, min=1, max=100000,
            label="At most this many",
            help=("Stop after this many images. A lot can have tens of "
                  "thousands of defects, and each one means running the "
                  "pipeline again to get its images."),
        ),
        rank_by_spec(),
        ParamSpec(
            name="montage", type="bool", default=True,
            label="Show the difference beside it",
            help=("On: each PNG is the image and the difference side by "
                  "side. Off: just the image."),
        ),
    ]

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        folder = str(p["folder"]).strip()
        if not folder:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        if os.path.isfile(folder):
            raise StepError(
                self.key,
                "“%s” is a file, not a folder. This card writes one PNG per "
                "defect, so it needs a folder to put them in." % folder)
        items = list(getattr(bctx.dataset, "items", None) or [])
        by_id = {str(getattr(it, "defect_id", "")): it for it in items}
        sources = dict(getattr(bctx.dataset, "sources", None) or {})
        limit = int(p["limit"])
        # **依分數由高到低取前 N**（`overlay.pick_overlay_results`，跟 Export
        # 精靈同一支）。照 `rows` 的順序取的話拿到的是**檔案順序**上的前 N 顆
        # —— 那幾乎一定不是使用者想看的那幾顆，而畫面上看不出差別（都是 N 張
        # PNG）。第一版就是那樣寫的。
        rank_by = str(p["rank_by"]).strip() or overlay.RANK_BY_SCORE
        chosen = overlay.pick_overlay_results(bctx.rows, limit, rank_by)
        _warn_if_unranked(self.key, bctx, bctx.rows, rank_by, limit)
        # **一顆一顆重跑 pipeline** 才拿得到影像（結果表裡只有數字）。那正是
        # Export 精靈今天做的事，所以這裡不是新的成本，只是換了一個地方。
        wrote = 0
        skipped = 0
        for row in chosen:
            item = by_id.get(str(row.get("defect_id", "")))
            if item is None:
                skipped += 1
                continue
            try:
                # **有快取就走快取**（F29 C4）：這一趟的影像段跟剛才那一批
                # 逐位元組相同，所以命中之後只跑算法段。`bctx.rerun` 兩條路的
                # 結果位元級一致，所以這裡完全不必知道有沒有快取。
                r = bctx.rerun(item, sources={k: getattr(v, "items", v)
                                              for k, v in sources.items()})
                ctx = getattr(r, "context", None)
                images = dict(getattr(ctx, "images", {}) or {})
                if not images:
                    skipped += 1
                    continue
                panel = overlay.render_overlay(
                    images, dict(getattr(r, "features", {}) or {}),
                    label=overlay.overlay_label(row),
                    montage=bool(p["montage"]))
                overlay.write_png(
                    panel,
                    os.path.join(folder, overlay.overlay_filename(
                        row.get("defect_id", "x"))))
                wrote += 1
            except Exception:       # noqa: BLE001 — 一顆畫不出來不該殺掉整批
                skipped += 1
        bctx.add_output(folder)
        if skipped:
            # **講出來**：少幾張 PNG 的資料夾跟完整的資料夾長得一模一樣。
            bctx.warn("Images: wrote %d, skipped %d (no image, or the "
                      "pipeline did not run for them)." % (wrote, skipped))
        if len(bctx.rows) > len(chosen):
            bctx.warn("Images: the %d highest scoring of %d defects (the “At "
                      "most this many” setting)."
                      % (len(chosen), len(bctx.rows)))


#: HTML 報表的樣式。**inline，而且只有純文字** —— 這個 repo 是純文字的
#: （`AGENTS.md` §2：唯一的傳輸通道是剪貼簿），而且報表要能單獨寄給別人：
#: 一個外部 .css 檔會在轉寄的那一刻不見。
# ⚠ **HTML 的版面與那幾支小工具搬去 `core/export/html.py` 了**（F29 C2）：
# `output_html` 與 `output_bundle` 產的是同一份東西，差別只在圖放不放得進來 ——
# 抄第二份出來的那一份一定會漂。


@register_step
class OutputBundleStep(_OutputStep):
    """一個資料夾：報表 ＋ 一顆一張的疊圖 ＋ CSV ＋ 產它的那份 recipe。"""

    key = "output_bundle"
    label = "Write report folder"
    PATH = "folder"
    WHAT = "folder"
    help = ("Write everything about this run into one folder: a report you "
            "can open in a browser with a picture of every defect, the same "
            "numbers as a spreadsheet, and the recipe that produced them. "
            "Made for a whole lot - thousands of defects fit, because the "
            "pictures sit beside the report instead of inside it.")
    params = [
        ParamSpec(
            name="folder", type="str", default="",
            label="Write to",
            help=("Folder to write everything into. It is created if it does "
                  "not exist; files with the same names are overwritten."),
        ),
        # **預設 0 = 全部**（使用者定調 2026-08-25：「參數化，預設全部」）。
        # `output_image` 那張卡預設 200，而它們的用途不同：那張是「挑幾顆來
        # 看」，這一張是「這一批的報表」—— 一份少了一半的報表跟完整的長得
        # 一模一樣。
        ParamSpec(
            name="limit", type="int", default=0, min=0, max=1000000,
            label="At most this many pictures",
            help=("Zero means every defect. Set a number to keep only the "
                  "worst that many (highest score first) - the report still "
                  "lists every defect, only the pictures are limited."),
        ),
        ParamSpec(
            name="jpeg_quality", type="int",
            default=overlay.DEFAULT_JPEG_QUALITY, min=40, max=100,
            label="Picture quality", advanced=True,
            help=("How much detail to keep in the pictures, from 40 (small "
                  "files) to 100 (biggest). The pictures are for looking at, "
                  "not for measuring - the numbers in the report come from "
                  "the originals either way."),
        ),
        rank_by_spec(),
        ParamSpec(
            name="montage", type="bool", default=True,
            label="Show the difference beside it",
            help=("On: each picture is the image and the difference side by "
                  "side. Off: just the image."),
        ),
    ]

    #: 資料夾裡那幾個名字（**寫死**：一份 bundle 換一台機器打開還是同一個形狀）。
    REPORT_NAME = "report.html"
    CSV_NAME = "defects.csv"
    RECIPE_NAME = "recipe.json"
    IMAGE_DIR = "images"

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        folder = str(p["folder"]).strip()
        if not folder:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        if os.path.isfile(folder):
            raise StepError(
                self.key,
                "“%s” is a file, not a folder. This card writes several files, "
                "so it needs a folder to put them in." % folder)
        rows = list(bctx.rows)
        items = list(getattr(bctx.dataset, "items", None) or [])
        by_id = {str(getattr(it, "defect_id", "")): it for it in items}
        sources = dict(getattr(bctx.dataset, "sources", None) or {})
        shots = os.path.join(folder, self.IMAGE_DIR)

        # ---- ① 圖（一顆一張，照分數由高到低）-------------------------------
        rank_by = str(p["rank_by"]).strip() or overlay.RANK_BY_SCORE
        chosen = overlay.pick_overlay_results(rows, int(p["limit"]), rank_by)
        _warn_if_unranked(self.key, bctx, rows, rank_by, int(p["limit"]))
        images: Dict[str, str] = {}
        skipped = 0
        for row in chosen:
            did = str(row.get("defect_id", ""))
            item = by_id.get(did)
            if item is None:
                skipped += 1
                continue
            try:
                r = bctx.rerun(item, sources={k: getattr(v, "items", v)
                                              for k, v in sources.items()})
                ctx = getattr(r, "context", None)
                pix = dict(getattr(ctx, "images", {}) or {})
                if not pix:
                    skipped += 1
                    continue
                panel = overlay.render_overlay(
                    pix, dict(getattr(r, "features", {}) or {}),
                    label=overlay.overlay_label(row),
                    montage=bool(p["montage"]))
                name = os.path.splitext(overlay.overlay_filename(did))[0] + ".jpg"
                overlay.write_jpeg(panel, os.path.join(shots, name),
                                   int(p["jpeg_quality"]))
                # **相對路徑**：報表跟圖一起搬走的時候連結還是通的。
                images[did] = "%s/%s" % (self.IMAGE_DIR, name)
            except Exception:       # noqa: BLE001 — 一顆畫不出來不該殺掉整批
                skipped += 1

        # ---- ② 報表（**每一顆都在**，只有圖有上限）-------------------------
        title = str(getattr(bctx.recipe, "recipe_id", "") or "d4t results")
        report_path = os.path.join(folder, self.REPORT_NAME)
        try:
            export_html.write_html(
                export_html.build_report(
                    rows, title, export_report.feature_keys(rows),
                    decide=getattr(bctx.recipe, "decide", None),
                    images=images),
                report_path)
            export_report.write_csv(rows, os.path.join(folder, self.CSV_NAME))
            # ---- ③ 產它的那份 recipe --------------------------------------
            # **沒有它，半年後沒人重現得出這份報表。** 那不是保險，是這份東西
            # 有沒有用的分界：一疊數字沒有配方，等於一句「我們那時候量到這樣」。
            self._write_recipe(bctx, os.path.join(folder, self.RECIPE_NAME))
        except OSError as e:
            raise StepError(self.key,
                            "could not write into %s: %s" % (folder, e)) from e
        bctx.add_output(folder)
        if skipped:
            # **講出來**：少幾張圖的報表跟完整的長得一模一樣。
            bctx.warn("Report folder: %d picture(s) written, %d skipped (no "
                      "image, or the pipeline did not run for them)."
                      % (len(images), skipped))

    def _write_recipe(self, bctx: Any, path: str) -> None:
        """把 recipe 原樣寫進 bundle（atomic，同鐵則 5）。

        走 ``to_json_dict`` 而不是「複製使用者那個檔案」—— 使用者可能在
        Studio 裡改過還沒存，而**報表要對得上真的跑出這些數字的那一份**。
        """
        import json

        recipe = getattr(bctx, "recipe", None)
        to_dict = getattr(recipe, "to_json_dict", None)
        if to_dict is None:
            return
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


@register_step
class OutputHtmlStep(_OutputStep):
    """整批的結果 → 一份可以直接寄出去的 HTML 表。"""

    key = "output_html"
    label = "Write HTML"
    WHAT = "HTML file"
    help = ("Write a single HTML page when the whole lot has run: how the "
            "defects split across bins, and one row per defect with every "
            "number that was measured. It opens in any browser and needs "
            "nothing alongside it, so it can be emailed as is.")
    params = [
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the .html file to write, including the file "
                  "name. Folders that do not exist yet are created."),
        ),
        ParamSpec(
            name="title", type="str", default="",
            label="Heading",
            help=("Heading to put at the top of the page. Leave it empty to "
                  "use the recipe's name."),
        ),
    ]

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = self._path_of(p)
        rows = list(bctx.rows)
        title = (str(p["title"]).strip()
                 or str(getattr(bctx.recipe, "recipe_id", "") or "d4t results"))
        # **版面住 `export/html.py`，兩張卡共用同一支**（F29 C2）。以前整份
        # HTML inline 在這裡，於是 bundle 那張卡要嘛抄一份（兩份會漂），
        # 要嘛長得不一樣（同一批資料兩種報表，而使用者分不出差別）。
        #
        # 這張卡**不放圖**：它的賣點就是單檔可轉寄，而圖要嘛是相對路徑
        # （那就不是單檔了）要嘛 base64（6000 顆是 76 MB 的一個檔案）。
        text = export_html.build_report(
            rows, title, export_report.feature_keys(rows),
            decide=getattr(bctx.recipe, "decide", None))
        try:
            export_html.write_html(text, path)
        except OSError as e:
            raise StepError(self.key,
                            "could not write %s: %s" % (path, e)) from e
        bctx.add_output(path)
