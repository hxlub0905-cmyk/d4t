# d4t step-card library — authored 2026-08-20 (F16：Output 段).
"""Output 段的卡：整批跑完之後，把結果寫出去。

Output 段是什麼（使用者 2026-08-20 定調）
-----------------------------------------
> Output 我預期要可以產出多種 style（分 card），例如 Report / csv / klarf /
> html 檔案，要單純 output image 也可（**他就是個 end point**）

「end point」寫成一條**自動套用到 registry 每一張卡**的性質：Output 段的卡
``resolve_writes()`` 與 ``resolve_features()`` 都是空的。一旦它吐了東西，下游就
接得上它，而「這一段是最後一段」那句話就不再成立。

每一張都薄薄一層包在既有的 `core/export/` 上 —— **演算法一行都沒重寫**，
而那是「換一條路，東西沒變」可以被量出來的原因（見
`tests/test_batch_steps.py` 的逐位元組比對，那是之後拿掉 Export 精靈的前提）。

==================  =======================================  =================
卡                  寫什麼                                   引擎
==================  =======================================  =================
``output_csv``      一顆一列的明細表（＝ feature vector）     `export/report`
``output_report``   Excel：摘要 / 明細 / 特徵統計三張表       `export/report`
``output_klarf``    寫回 KLARF（三種模式）                    `export/klarf_out`
``output_bundle``   一個資料夾：報表／表格／圖／recipe        `export/html` ＋
                    （要哪幾樣是一格勾選，F37）              `export/overlay`
``output_char``     點對點兩張圖的 characterization 報表      `export/html`
``output_boxplot``  一片葉子一個盒子的分布圖                  `export/boxplot`
``output_html``     單檔可轉寄的 HTML 表                      `export/html`
==================  =======================================  =================

**每一張的尺度都是「整批一次」（``scale = SCALE_LOT``），包含會出圖的那幾張。**
寫一個檔案的那些顯然是。出圖的看起來是逐顆的 —— 但它如果做成普通 Step，
它就會在 ``run_defect`` 裡跑，而那條路**每切換一顆 defect 就走一次**：使用者
瀏覽 defect 的時候會一直寫圖出來。所以它也是整批跑完之後跑一次，一顆一顆
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
from typing import Any, Dict, List, Optional

from ..export import boxplot as export_boxplot
from ..export import html as export_html
from ..export import klarf_out, overlay
from ..export import report as export_report
from ..pipeline import decide_tree
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_BATCH, GROUP_OUTPUT, SCALE_LOT, ParamSpec, Step, StepError,
    register_step,
)
from ._util import parse_key_list



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
            name="size_feature", type="feature_key", default="cd_median",
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

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """``size_feature`` —— **只在真的指定了 size 欄位的時候才算數**。

        它有一個非空的預設（``cd_median``），而 inplace 一格目標欄位都沒填是
        完全正常的用法（輸出檔與原檔逐位元組相同）。照型別無條件掃的話，那種
        recipe 會因為一個**沒有在用的預設值**被報一句話。
        """
        if str(params.get("mode", "") or "") != "inplace":
            return []
        if not str(params.get("size_col", "") or "").strip():
            return []
        name = str(params.get("size_feature", "") or "").strip()
        return [name] if name else []

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


def _defect_marks(ctx: Any, pix: Dict[str, Any],
                  main_key: str) -> Dict[str, Any]:
    """左邊那張圖上要畫的兩個記號（F33）→ ``{"box": …, "aim": …}``。

    使用者問的那件事：「名義上 defect 會在 FOV 正中央（機台就是照 KLARF 座標
    移過去拍），但實際可能會拍歪一點點 —— **可是這樣就沒有明確在圖上指出
    defect 位置**。」

    兩個記號各自回答一半：

    * **十字（aim）**＝機台瞄準的那一點。H2H 算過它（``meta["align_to"]``
      的 ``expected``，那正是 ``align_off_*`` 的分母）；沒跑過 H2H 的那一顆
      （配不到 → 那張卡讓路）就是**影像正中央** —— 名義位置本來就是那裡，
      而「該在這裡、而另一份什麼都沒有」正是第三類要講的話。
    * **框（box）**＝小圖真的對到哪。

    ⚠ **框只畫在 H2H 真的搜過的那條流上**（``meta["align_to"]["search"]``）。
    換一條流當左圖時座標的意思就變了，而一個指著錯地方的框比沒有框糟得多
    （同 `_draw_roi_boxes` 的「不猜」）。這也是 `align_to` 要把 ``search``
    記進 meta 的理由。
    """
    arr = pix.get(main_key) if main_key else None
    if arr is None and pix:
        try:
            arr = overlay.pick_base(pix)[1]
        except Exception:              # noqa: BLE001 — 沒圖就沒有記號
            return {}
    if arr is None:
        return {}
    h, w = arr.shape[:2]
    note = dict((getattr(ctx, "meta", None) or {}).get("align_to") or {})
    same = bool(note) and str(note.get("search", "")) == str(main_key or "")
    out: Dict[str, Any] = {}
    if same:
        size = list(note.get("size") or [])
        exp = list(note.get("expected") or [])
        if len(size) == 2:
            out["box"] = (int(round(float(note["x"]))),
                          int(round(float(note["y"]))),
                          int(size[0]), int(size[1]))
        if len(exp) == 2 and len(size) == 2:
            # `expected` 是框的**左上角** —— 十字要畫在它的中心
            out["aim"] = (float(exp[0]) + size[0] / 2.0,
                          float(exp[1]) + size[1] / 2.0)
    if "aim" not in out:
        # 沒有對位（配不到，或左圖不是被搜的那一條）→ **名義位置＝正中央**
        out["aim"] = (w / 2.0, h / 2.0)
    return out


def write_recipe_json(bctx: Any, path: str) -> None:
    """把 recipe 原樣寫進輸出資料夾（atomic，鐵則 5）。

    **沒有它，半年後沒人重現得出這份報表。** 那不是保險，是這份東西有沒有用
    的分界：一疊數字沒有配方，等於一句「我們那時候量到這樣」。

    走 ``to_json_dict`` 而不是「複製使用者那個檔案」—— 使用者可能在 Studio
    裡改過還沒存，而**報表要對得上真的跑出這些數字的那一份**。

    兩張寫資料夾的卡共用這一支（同 `rank_by_spec` 的理由）。
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
        name="rank_by", type="feature_key", default=overlay.RANK_BY_SCORE,
        label="Worst first, by", advanced=True,
        help=("Which number decides the order, highest first. Leave it as "
              "“score” if your recipe has a score formula. If you classify "
              "with a decision tree instead, there is no score - put the name "
              "of a number you measure here (for example glv_worst_score, "
              "cmp_snr_mean or cd_area_px), otherwise the pictures come out "
              "in file order."))
    # ⚠ 型別是 `feature_key` 而不是 `str`（F37）。差別有兩個，而第二個才是
    # 加它的理由：UI 會給這一格一支「插入數字 ▾」（同 `feature_keys`），
    # 而**改名遷移認得出這一格裝著一個特徵名**。以前它是 `str`，於是一次
    # 改名之後這一格會指著一個不存在的數字 —— 而那不會報錯，出圖卡排不出
    # 順序就安靜地退回檔案順序（F30 修過一次的那個 bug）。
    # ``score`` 這個哨兵值不在任何改名表的左邊，所以整格比對不會動到它。


#: 「這個資料夾裡要放什麼」的四個勾（F37，2026-08-26）。
#:
#: 為什麼是勾選而不是四張卡：`output_image`（Write images）的**七格參數一格
#: 不差全部是 `output_bundle` 的子集**，而它寫出來的東西正好是後者少了報表、
#: 表格與 recipe 三個檔案。兩張卡在使用者眼裡因此是同一件事的兩個程度，
#: 而「我要一份報表」時面前有兩個答案（`CLAUDE.md` §3 的「同一個家族的做法
#: 收成一張卡」，前例是 F29 的 `roi_reference` 與 F19 的 CD）。
#:
#: ⚠ **值是穩定的字串 id**，除了相等比較之外沒有人解析它們。
CONTENT_REPORT = "report"
CONTENT_TABLE = "table"
CONTENT_PICTURES = "pictures"
CONTENT_RECIPE = "recipe"
CONTENTS = (CONTENT_REPORT, CONTENT_TABLE, CONTENT_PICTURES, CONTENT_RECIPE)

#: 圖要寫成哪一種檔（F37）。
#:
#: 這一格是**合併的代價**，而它必須存在：`output_image` 寫的是 PNG、
#: `output_bundle` 寫的是 JPEG，所以少了它的話，一份舊的 `output_image`
#: recipe 遷移過來會安靜地換一種檔案格式 —— 而使用者的下游（另一支腳本、
#: 一份報告的插圖）認的是副檔名。
PIC_PNG = "png"
PIC_JPEG = "jpeg"
PIC_FORMATS = (PIC_JPEG, PIC_PNG)


def contents_spec() -> ParamSpec:
    """「這個資料夾裡要放什麼」（見 :data:`CONTENTS`）。"""
    return ParamSpec(
        name="contents", type="multi_choice", default=",".join(CONTENTS),
        choices=list(CONTENTS), label="What to put in the folder",
        help=("Tick what this folder should hold. report is a page you open "
              "in a browser with a picture of every defect; table is the same "
              "numbers as a CSV; pictures is one image per defect; recipe is "
              "the settings that produced them, so the run can be reproduced "
              "later. Tick pictures on its own and you get a plain folder of "
              "images and nothing else."),
    )


def picture_specs() -> List[ParamSpec]:
    """圖的格式與品質（見 :data:`PIC_FORMATS`）。"""
    return [
        ParamSpec(
            name="picture_format", type="choice", default=PIC_JPEG,
            choices=list(PIC_FORMATS), label="Picture files",
            show_when=("contents", (CONTENT_PICTURES,)),
            choice_help={
                PIC_JPEG: "Smaller files. Right for a report you send to "
                          "someone - a few thousand pictures still fit.",
                PIC_PNG: "Every pixel exactly as drawn, and much bigger "
                         "files. Right when something downstream reads these "
                         "images back.",
            },
            help=("What kind of image file to write. The numbers in the "
                  "report come from the originals either way - these "
                  "pictures are for looking at."),
        ),
    ]


def ranked_feature(params: Dict[str, Any]) -> List[str]:
    """``rank_by`` 指著的那個特徵名（``score`` 這個哨兵不算）。

    給 `Step.optional_features_in` 用 —— 出圖那幾張卡共用一份，同
    `rank_by_spec` 的理由：**同一句話不准在兩個地方長出兩種意思**。

    ``score`` 排除掉是因為它不是任何一張卡算出來的東西，它是 recipe 的分數
    （lint 那邊的 ``feats`` 一開始就種著它）。
    """
    name = str((params or {}).get("rank_by", "") or "").strip()
    return [name] if name and name != overlay.RANK_BY_SCORE else []


def roi_draw_specs() -> List[ParamSpec]:
    """出圖那兩張卡共用的「ROI 框怎麼畫」（F31）。**兩張卡逐字同一組**。

    GLV 的逐框比較（each box）在報表上要看得到：贏家（最異常的那一格）粗框、
    其餘細線 —— 其餘的是**參照**，要看得到（比較的分母是什麼）但不能把整張圖
    蓋滿。500 個框全畫就是蓋滿，所以「畫幾個」是使用者的一格，不是程式裡的
    魔術數字；而那個數字同時是 ``all`` 的自動退化門檻與 ``near the winner``
    的數量（`overlay.pick_roi_boxes`）—— 一個數字管兩件事，不必發明第二個。
    """
    return [
        ParamSpec(
            name="draw_boxes", type="choice", default=overlay.DRAW_ALL,
            choices=list(overlay.DRAW_MODES), label="Draw the other boxes",
            help=("When a GLV card compared the region box by box, each "
                  "picture gets the winning box drawn thick - and this "
                  "decides what happens to all the other boxes. all shows "
                  "the whole set as thin lines (best when there are few); "
                  "near the winner keeps only the closest ones; none draws "
                  "just the winner. With thousands of boxes, all quietly "
                  "becomes near the winner at the limit below."),
        ),
        ParamSpec(
            name="draw_boxes_cap", type="int", default=300, min=1, max=100000,
            label="Draw at most", advanced=True,
            help=("The most boxes to draw on one picture. all switches to "
                  "near the winner above this number, and near the winner "
                  "keeps this many (the winner plus its closest "
                  "neighbours)."),
        ),
        ParamSpec(
            name="mark_pixels_k", type="float", default=3.0, min=0.0,
            max=99.0, unit="σ", label="Mark pixels beyond", advanced=True,
            help=("Inside the winning box, tint every pixel that sits more "
                  "than this many robust sigmas from the other boxes' "
                  "baseline - the same baseline and spread the glv_worst_score "
                  "was computed from, so what lights up is exactly what the "
                  "number is talking about. The tint only appears when the "
                  "winning box itself is at least that many sigmas out - a "
                  "quiet image stays quiet. 0 turns the tint off. This only "
                  "draws: it writes no feature and makes no region."),
        ),
    ]


def _roi_overlay_kwargs(ctx: Any, p: Dict[str, Any]):
    """一顆的 ``roi_boxes`` / ``roi_winner`` / ``odd_pixels``
    → ``(kwargs, 有沒有自動退化)``。

    兩張出圖卡逐字同一段（同 `roi_draw_specs` 的理由）。退化（``all`` 超過
    上限退成 ``near the winner``）由呼叫端**整批警告一次** —— 一顆一句的話
    6000 顆就是 6000 句。

    像素標記（T3）的 baseline / spread 來自 GLV 的 `worst` note —— 跟
    `glv_worst_score` 同一次計算；`src` 是量測那條流的**原始**陣列（顯示用那份
    被拉過值域）。拿不到贏家、拿不到那條流、或 k = 0，就不標。
    """
    rects, win, note = (overlay.worst_note_for_overlay(ctx)
                        if ctx is not None else ([], -1, None))
    boxes, drawn_win, degraded = overlay.pick_roi_boxes(
        rects, win, str(p["draw_boxes"]), int(p["draw_boxes_cap"]))
    kwargs: Dict[str, Any] = {"roi_boxes": boxes, "roi_winner": drawn_win}
    k = float(p.get("mark_pixels_k", 0.0) or 0.0)
    worst = (note or {}).get("worst") or {}
    # 染色跟贏家自己的分數綁同一個 k：像素判準的分母是框間統計量的穩健散布
    # （常踩 1 灰階地板），遠小於像素雜訊，所以正常顆的贏家框也會整格過線
    # （實測 2.7σ 的 bin 0 顆整框染色）。「這一格自己至少偏離 k 個 σ」時才
    # 標像素，正常顆整張安靜，而 score 與像素用的本來就是同一組 baseline/spread。
    if (k > 0.0 and 0 <= win < len(rects) and worst
            and float(worst["score"]) >= k):
        src = (getattr(ctx, "images", {}) or {}).get(
            str((note or {}).get("stream") or ""))
        if src is not None:
            kwargs["odd_pixels"] = {
                "box": rects[win], "baseline": float(worst["baseline"]),
                "spread": float(worst["spread"]), "k": k, "src": src,
            }
    return kwargs, degraded


# ⚠ **``output_image``（Write images）於 F37 折進 ``output_bundle`` 了**
# （2026-08-26）。它的七格參數一格不差全部是那張卡的子集，而它寫的東西正好是
# 那張卡少了報表、表格與 recipe —— 也就是同一張卡的一個程度。現在的做法是
# 「只勾 pictures」，而 PNG／子資料夾這兩個差別由 ``picture_format`` 與
# ``nested`` 保住（見 `_migrate_output_image_into_bundle`）。
#
# 舊 recipe 走那道遷移，所以**開得起來、而且寫出來的東西逐位元組一樣**。


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
        contents_spec(),
        *picture_specs(),
        # **預設 0 = 全部**（使用者定調 2026-08-25：「參數化，預設全部」）。
        # 併進來的 `output_image` 預設 200，而它們的用途不同：那個是「挑幾顆
        # 來看」，這一張是「這一批的報表」—— 一份少了一半的報表跟完整的長得
        # 一模一樣。遷移**照舊值搬**，所以既有的 recipe 行為不變。
        ParamSpec(
            name="limit", type="int", default=0, min=0, max=1000000,
            label="At most this many pictures",
            show_when=("contents", (CONTENT_PICTURES,)),
            help=("Zero means every defect. Set a number to keep only the "
                  "worst that many (highest score first) - the report still "
                  "lists every defect, only the pictures are limited."),
        ),
        ParamSpec(
            name="jpeg_quality", type="int",
            default=overlay.DEFAULT_JPEG_QUALITY, min=40, max=100,
            label="Picture quality", advanced=True,
            show_when=("picture_format", (PIC_JPEG,)),
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
        *roi_draw_specs(),
    ]

    #: 資料夾裡那幾個名字（**寫死**：一份 bundle 換一台機器打開還是同一個形狀）。
    REPORT_NAME = "report.html"
    CSV_NAME = "defects.csv"
    RECIPE_NAME = "recipe.json"
    IMAGE_DIR = "images"

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """``rank_by``（見 `ranked_feature`）—— 少了圖照樣寫，順序退回檔案順序。"""
        return ranked_feature(params)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        out = list(super().configuration_issues(params))
        # **「這個鍵不在」＝還沒設過＝預設全勾**，不是「一個都沒勾」。
        # 兩者差很多：前者是每一份合併之前存下來的 recipe（那時候沒有這一格），
        # 而把它們一律說成設定錯誤，等於對著每一份舊檔案喊狼來了。
        if not parse_key_list(params.get("contents", ",".join(CONTENTS))):
            # 一個都沒勾的資料夾**會被建出來、而且是空的** —— 跑得完、
            # 沒有錯誤、什麼都沒有。那是這張卡最容易犯的新錯（合併之前
            # 不存在，因為當時沒有「要寫什麼」這一格）。
            out.append("Nothing is ticked in “What to put in the folder”, so "
                       "this card would make an empty folder. Tick at least "
                       "one thing.")
        return out

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
        want = set(parse_key_list(p["contents"]))

        # **圖放不放進子資料夾，由「有沒有報表」決定**（F37）。子資料夾存在
        # 的理由是報表要用相對路徑連過去；沒有報表的時候它只是多一層要點進去
        # 的東西 —— 而那正是併進來的 `output_image` 的形狀（圖直接躺在資料夾
        # 裡）。所以這不是為了相容湊出來的規則，是那一層本來就有的意思。
        nested = CONTENT_REPORT in want
        shots = os.path.join(folder, self.IMAGE_DIR) if nested else folder

        # ---- ① 圖（一顆一張，照分數由高到低）-------------------------------
        rank_by = str(p["rank_by"]).strip() or overlay.RANK_BY_SCORE
        chosen = (overlay.pick_overlay_results(rows, int(p["limit"]), rank_by)
                  if CONTENT_PICTURES in want else [])
        if CONTENT_PICTURES in want:
            _warn_if_unranked(self.key, bctx, rows, rank_by, int(p["limit"]))
        as_png = str(p["picture_format"]) == PIC_PNG
        images: Dict[str, str] = {}
        skipped = 0
        degraded_any = False
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
                roi_kw, degraded = _roi_overlay_kwargs(ctx, p)
                degraded_any = degraded_any or degraded
                panel = overlay.render_overlay(
                    pix, dict(getattr(r, "features", {}) or {}),
                    label=overlay.overlay_label(row),
                    montage=bool(p["montage"]), **roi_kw)
                stem = os.path.splitext(overlay.overlay_filename(did))[0]
                name = stem + (".png" if as_png else ".jpg")
                if as_png:
                    overlay.write_png(panel, os.path.join(shots, name))
                else:
                    overlay.write_jpeg(panel, os.path.join(shots, name),
                                       int(p["jpeg_quality"]))
                # **相對路徑**：報表跟圖一起搬走的時候連結還是通的。
                images[did] = ("%s/%s" % (self.IMAGE_DIR, name) if nested
                               else name)
            except Exception:       # noqa: BLE001 — 一顆畫不出來不該殺掉整批
                skipped += 1

        # ---- ② 報表（**每一顆都在**，只有圖有上限）-------------------------
        title = str(getattr(bctx.recipe, "recipe_id", "") or "d4t results")
        try:
            if CONTENT_REPORT in want:
                export_html.write_html(
                    export_html.build_report(
                        rows, title, export_report.feature_keys(rows),
                        decide=getattr(bctx.recipe, "decide", None),
                        images=images),
                    os.path.join(folder, self.REPORT_NAME))
            if CONTENT_TABLE in want:
                export_report.write_csv(rows,
                                        os.path.join(folder, self.CSV_NAME))
            # ---- ③ 產它的那份 recipe --------------------------------------
            # **沒有它，半年後沒人重現得出這份報表。** 那不是保險，是這份東西
            # 有沒有用的分界：一疊數字沒有配方，等於一句「我們那時候量到這樣」。
            if CONTENT_RECIPE in want:
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
        if degraded_any:
            bctx.warn("Report folder: more region boxes than “Draw at most” "
                      "(%d), so only the boxes near the winner are drawn."
                      % int(p["draw_boxes_cap"]))

    def _write_recipe(self, bctx: Any, path: str) -> None:
        """見 :func:`write_recipe_json` —— 這裡只是它的舊名字。"""
        write_recipe_json(bctx, path)


@register_step
class OutputCharStep(_OutputStep):
    """characterization 的點對點報表：**一顆一列，兩張圖跟數字在同一列上**。

    為什麼是第二張卡，不是 `output_bundle` 的一格參數
    --------------------------------------------------
    那張卡的每一個取捨都是為 6000 顆做的 —— 表格裡不放縮圖（DOM 會鈍）、
    點一列換圖（整份只有一個 ``<img>``）。characterization 是三十顆，而使用者
    要的是「**我可以一一對應**」：那三項在這個規模全部反過來。

    用一格參數在同一張卡上切換兩種版面的話，「這張卡長什麼樣」就有兩個答案，
    而說明書、help、測試都得同時描述兩種 —— 那正是這個 repo 一再避開的形狀。
    做成第二張卡，**底層共用**（`export/html.py` 的 CSS／跳脫／判定那一段、
    `write_recipe_json`、`overlay` 的檔名消毒與 JPEG）。
    """

    key = "output_char"
    label = "Write characterization report"
    PATH = "folder"
    WHAT = "folder"
    help = ("Write a folder that puts the two lots side by side, one defect "
            "per row: the ground-truth picture, the matching picture from the "
            "second lot, the numbers you pick, and what the recipe decided. "
            "Made for a characterization run of a few dozen defects, where "
            "you want to check every row by eye - for a whole lot use “Write "
            "report folder” instead.")
    params = [
        ParamSpec(
            name="folder", type="str", default="",
            label="Write to",
            help=("Folder to write everything into. It is created if it does "
                  "not exist; files with the same names are overwritten."),
        ),
        ParamSpec(
            name="limit", type="int", default=200, min=1, max=100000,
            label="At most this many rows with pictures",
            help=("This report puts a picture on every row, which is what "
                  "makes it readable at a glance and also what stops it "
                  "scaling. Above this many defects the extra rows are still "
                  "listed, without pictures, and the card says so."),
        ),
        ParamSpec(
            name="main_stream", type="str", default="",
            label="Left picture",
            help=("Which image stream to show on the left - the lot you are "
                  "running (the ground truth, in a characterization). Leave "
                  "it empty to use whichever image the run started from."),
        ),
        ParamSpec(
            name="pair_stream", type="str", default="paired",
            label="Right picture",
            help=("Which image stream to show on the right - what the Pair "
                  "card brought over from the second lot (\"paired\"), or the "
                  "cut-out the H2H card aligned (\"aligned\"). A defect with "
                  "no match has no such image, and that cell is left empty - "
                  "which is the point: it is one of the answers."),
        ),
        ParamSpec(
            name="columns", type="feature_keys",
            default="ncc_score,align_peak_ratio,pair_die_rank,pair_die_total",
            label="Numbers to show",
            help=("Which measured numbers get a column, in this order. The "
                  "first two are here on purpose - they are how a wrong "
                  "pairing shows up. ncc_score is how alike the two pictures "
                  "are. align_peak_ratio is the one that catches a repeating "
                  "pattern: in an array area the second-best position scores "
                  "as well as the best, so a near-1 ratio means the position "
                  "was a guess even when ncc_score looks perfect. Everything "
                  "else is in the spreadsheet beside this report."),
        ),
        ParamSpec(
            name="mark_defect", type="bool", default=True,
            label="Mark where the defect is",
            help=("Draw two marks on the left picture: a green cross where "
                  "the tool aimed (it moved to this defect's coordinate, so "
                  "nominally the defect is right there) and a red box where "
                  "the H2H card actually matched the second lot's picture. "
                  "The gap between them is this defect's stage error - and "
                  "the two sitting on top of each other is what \"these are "
                  "the same defect\" looks like. A defect with no match gets "
                  "the cross only: that is still where it should have been."),
        ),
        rank_by_spec(),
        ParamSpec(
            name="jpeg_quality", type="int",
            default=overlay.DEFAULT_JPEG_QUALITY, min=40, max=100,
            label="Picture quality", advanced=True,
            help=("How much detail to keep in the pictures, from 40 (small "
                  "files) to 100 (biggest). The pictures are for looking at, "
                  "not for measuring."),
        ),
    ]

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """``rank_by`` ＋ ``columns``。

        ``columns`` 少一個的下場是**那一欄整排空白** —— 而一份每一格都空白的
        欄位，跟一份「這一批真的都量不到」長得一模一樣。
        """
        return ranked_feature(params) + parse_key_list(params.get("columns", ""))

    #: 資料夾裡那幾個名字 —— **跟 bundle 逐字相同**（換一台機器打開還是同一個
    #: 形狀，而兩份東西長得一樣就不必記兩套）。
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

        # ---- ① 順序：最值得看的在上面（同兩張出圖卡）-----------------------
        rank_by = str(p["rank_by"]).strip() or overlay.RANK_BY_SCORE
        limit = int(p["limit"])
        ordered = overlay.pick_overlay_results(rows, 0, rank_by)
        _warn_if_unranked(self.key, bctx, rows, rank_by, limit)
        if len(ordered) > limit:
            # **講出來，不要自動換版面**：使用者要知道他拿到的是哪一種報表。
            bctx.warn(
                "Characterization report: %d defects, but this report puts a "
                "picture on every row and is made for a few dozen - only the "
                "first %d rows have pictures. For a whole lot use “Write "
                "report folder”, which lists every defect and shows one "
                "picture at a time." % (len(ordered), limit))

        # ---- ② 圖（一顆兩張：跑的這一份 ＋ 第二份帶過來的那一張）-----------
        main_key = str(p["main_stream"]).strip()
        pair_key = str(p["pair_stream"]).strip()
        thumbs: Dict[str, Dict[str, Optional[str]]] = {}
        skipped = 0
        for row in ordered[:limit]:
            did = str(row.get("defect_id", ""))
            item = by_id.get(did)
            if item is None:
                skipped += 1
                continue
            try:
                r = bctx.rerun(item, sources={k: getattr(v, "items", v)
                                              for k, v in sources.items()})
                pix = dict(getattr(getattr(r, "context", None), "images", {})
                           or {})
                if not pix:
                    skipped += 1
                    continue
                stem = os.path.splitext(overlay.overlay_filename(did))[0]
                marks = (_defect_marks(getattr(r, "context", None), pix,
                                       main_key)
                         if bool(p["mark_defect"]) else {})
                pair = {}
                for side, key in (("main", main_key), ("pair", pair_key)):
                    arr = (pix.get(key) if key
                           else (overlay.pick_base(pix)[1] if pix else None))
                    if arr is None:
                        # 配不到的那一顆沒有第二張圖 —— 那一格留白，
                        # 而留白正是它要講的話（不是破圖、不是 0×0 的框）。
                        continue
                    if side == "main" and marks:
                        panel = overlay.render_overlay(
                            {"_": arr}, {}, base_key="_", montage=False,
                            box=marks.get("box"), aim=marks.get("aim"))
                    else:
                        panel = overlay.to_display_rgb(arr)
                    name = "%s_%s.jpg" % (stem, side)
                    overlay.write_jpeg(panel, os.path.join(shots, name),
                                       int(p["jpeg_quality"]))
                    # **相對路徑**：整個資料夾寄給別人的時候連結還是通的。
                    pair[side] = "%s/%s" % (self.IMAGE_DIR, name)
                if pair:
                    thumbs[did] = pair
            except Exception:       # noqa: BLE001 — 一顆畫不出來不該殺掉整批
                skipped += 1

        # ---- ③ 判定：葉子的名字**不在 rows 裡**，要反查一次 ----------------
        decide = getattr(bctx.recipe, "decide", None)
        verdicts: Dict[str, Dict[str, Any]] = {}
        for entry in decide_tree.verdict_rows(decide, rows):
            for did in entry.get("ids") or []:
                verdicts[str(did)] = entry

        title = str(getattr(bctx.recipe, "recipe_id", "") or
                    "d4t characterization")
        try:
            export_html.write_html(
                export_html.build_char_report(
                    ordered, title, parse_key_list(p["columns"]),
                    thumbs, verdicts, decide=decide),
                os.path.join(folder, self.REPORT_NAME))
            export_report.write_csv(rows, os.path.join(folder, self.CSV_NAME))
            write_recipe_json(bctx, os.path.join(folder, self.RECIPE_NAME))
        except OSError as e:
            raise StepError(self.key,
                            "could not write into %s: %s" % (folder, e)) from e
        bctx.add_output(folder)
        if skipped:
            # **講出來**：少幾張圖的報表跟完整的長得一模一樣。
            bctx.warn("Characterization report: %d defect(s) got no picture "
                      "(no image, or the pipeline did not run for them)."
                      % skipped)


@register_step
class OutputBoxPlotStep(_OutputStep):
    """整批的分布 → 一張 box plot（**一片葉子一個盒子**，F36）。

    為什麼是自己一張卡，不是報表裡的一個區塊
    ----------------------------------------
    使用者要的是「report **然後還有一張** box plot」—— 兩個交付物。而它們回答
    的也是兩個問題：報表是「這一顆長什麼樣」（一顆一列），這張圖是「**這一批**
    的這個數字散得多開，四類分不分得開」。

    合成一張卡的話，「這張卡寫出什麼」就有兩個答案 —— 那是 `output_char` 當初
    沒有做成 `output_bundle` 一格參數的同一個理由。底層仍然共用
    （`export/boxplot.py`、`decide_tree.verdict_rows`）。

    ⚠ **一個盒子是一片葉子，不是一個 bin。** 兩片葉子共用一個 bin 是合法的，
    而它們是使用者眼中兩個不同的類別（`verdict_rows` 的說明）。順序與顏色跟
    畫布上的樹一樣 —— 三個地方講同一件事的時候，長相也該是同一個。
    """

    key = "output_boxplot"
    label = "Write a box plot"
    WHAT = "HTML file"
    help = ("Write one box plot per number you pick, when the whole lot has "
            "run: one box for each class the decision came up with, so you "
            "can see at a glance whether the classes actually separate. It is "
            "a single HTML page that opens in any browser.")
    params = [
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the .html file to write, including the file "
                  "name. Folders that do not exist yet are created."),
        ),
        ParamSpec(
            name="features", type="feature_keys", default="",
            label="Numbers to plot",
            help=("One chart per number, in this order. Leave it empty and "
                  "the card plots whatever the decision itself asked about - "
                  "which is usually exactly what you want to see spread out."),
        ),
        ParamSpec(
            name="title", type="str", default="",
            label="Title", advanced=True,
            help="Heading on the page. Empty uses the recipe name.",
        ),
    ]

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """``features``。**空的不算** —— 那是「畫判定問過的那幾個」。"""
        return parse_key_list(params.get("features", ""))

    #: 判定沒有給出類別時（一份沒有 `decide` 的 recipe），全部畫成一個盒子。
    ALL_LABEL = "the whole lot"

    def _charts(self, bctx: Any, names: List[str],
                groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """``names`` × ``groups`` → 每個特徵一張圖。

        **一顆都沒量到那個數字的特徵整張圖不畫**，而且要在 warn 裡說出來 ——
        一張每一格都寫著「no data」的圖比沒有那張圖更糟（推廣鐵則）。
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        for row in bctx.rows:
            by_id[str(row.get("defect_id", ""))] = dict(
                row.get("features") or {})
        charts: List[Dict[str, Any]] = []
        empty: List[str] = []
        for name in names:
            series = []
            for g in groups:
                vals = [by_id.get(str(d), {}).get(name)
                        for d in (g.get("ids") or [])]
                series.append({"name": g.get("name") or "?",
                               "colour": g.get("colour"),
                               "values": [v for v in vals if v is not None]})
            if not any(s["values"] for s in series):
                empty.append(name)
                continue
            charts.append({"title": name, "series": series,
                           "subtitle": "one box per class - the line is the "
                                       "median, the box is the middle half"})
        if empty:
            bctx.warn(
                "Box plot: no defect has a number called %s, so %s not "
                "plotted. Check the spelling in “Numbers to plot”, or leave "
                "that box empty to plot whatever the decision asks about."
                % (", ".join("“%s”" % n for n in empty),
                   "it was" if len(empty) == 1 else "they were"))
        return charts

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        path = self._path_of(p)
        decide = getattr(bctx.recipe, "decide", None)

        # ---- ① 哪幾個數字 ----------------------------------------------
        names = parse_key_list(p["features"])
        if not names:
            # **判定問過的那幾個** —— 使用者想看的散布，九成是他拿來分類的那些。
            names = decide_tree.features_used(decide) if decide else []
        if not names:
            raise StepError(
                self.key,
                "nothing to plot: “Numbers to plot” is empty and this recipe "
                "has no decision to borrow the numbers from. Put the name of "
                "at least one measured number in that box.")

        # ---- ② 哪幾個盒子（一片葉子一個）--------------------------------
        groups = [g for g in decide_tree.verdict_rows(decide, bctx.rows)
                  if g.get("kind") not in ("failed", "unbinned")
                  and (g.get("ids") or [])]
        if not groups:
            groups = [{"name": self.ALL_LABEL,
                       "ids": [str(r.get("defect_id", ""))
                               for r in bctx.rows if r.get("ok")],
                       "colour": export_boxplot.FALLBACK_COLOUR}]

        charts = self._charts(bctx, names, groups)
        title = (str(p["title"]).strip()
                 or str(getattr(bctx.recipe, "recipe_id", "") or "d4t"))
        export_html.write_html(
            export_boxplot.build_boxplot_page(
                charts, title,
                subtitle="%d defect(s), %d class(es)"
                         % (len(bctx.rows), len(groups)),
                note=("Each box covers the middle half of the defects in that "
                      "class; the whiskers reach the furthest defect within "
                      "1.5 x that spread, and anything beyond is drawn as a "
                      "ring. Classes that do not overlap are classes this "
                      "number can tell apart.")),
            path)
        bctx.add_output(path)


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
