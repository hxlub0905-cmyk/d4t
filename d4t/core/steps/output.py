# d4t step-card library — authored 2026-08-20 (F16：Output 段).
"""Output 段的卡：整批跑完之後，把結果寫出去。

⚠ **``output_bundle`` 這個 key 於 F38（2026-08-26）退休了**，折進
``output_report``。它以前跟 ``bundle/d4t_bundle.py``（搬程式碼進公司機的那個
單檔包）共用「bundle」這個字，而那件事混淆過人 —— 現在 repo 裡「bundle」只剩
一個意思。**不要再造第二個**（`CLAUDE.md` §0 記著那次的代價）。

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

**三張卡**（F38，2026-08-26。使用者：「七張裡有五張在回答同一個問題，收成
三張」）：

==================  =======================================  =================
卡                  寫什麼                                   引擎
==================  =======================================  =================
``output_report``   一個資料夾。要哪幾樣是一格勾選：報表／     `export/html` ＋
                    表格／圖／Excel／box plot／recipe        `export/report` ＋
                                                             `export/overlay` ＋
                                                             `export/boxplot`
``output_klarf``    寫回 KLARF（三種模式）                    `export/klarf_out`
``output_char``     點對點兩張圖的 characterization 報表      `export/html`
                    （畫面上叫 “Write comparison”）
==================  =======================================  =================

收掉的四張與它們現在的樣子（遷移在 `recipe._migrate_folded_output_cards`）：

=================  ==================================================
``output_csv``     ``output_report`` 只勾 ``table``
``output_html``    ``output_report`` 只勾 ``report``
``output_boxplot`` ``output_report`` 只勾 ``boxplot``
``output_bundle``  ``output_report``（勾選照舊）
=================  ==================================================

⚠ ``output_report`` 這個 key **留著但意思換了**：它以前是「寫一個 Excel 檔」，
現在是「寫一個資料夾，Excel 是裡面的一個勾」。舊的那一格路徑（``path``）因此
也要遷移成 ``folder``。

**每一張的尺度都是「整批一次」（``scale = SCALE_LOT``），包含會出圖的那幾張。**
寫一個檔案的那些顯然是。出圖的看起來是逐顆的 —— 但它如果做成普通 Step，
它就會在 ``run_defect`` 裡跑，而那條路**每切換一顆 defect 就走一次**：使用者
瀏覽 defect 的時候會一直寫圖出來。所以它也是整批跑完之後跑一次，一顆一顆
重跑 pipeline 取影像（那正是 Export 精靈今天做的事）。

規則因此是一句話：**Output 段的卡都是整批一次。**

CSV 只有一種，而 ``include_features`` 跟著卡片走（F37 → F38）
------------------------------------------------------------
寫得出 CSV 的卡走的是同一支 `export/report.write_csv`，欄位逐字相同。
差別只有一格 ``include_features``（關掉只留 id／ok／score／bin）。

**F37 B2 查證後的結論是「不要把那一格補到寫資料夾的卡上」**，理由是：
``output_csv`` 是一份**交付物**（餵給下一支程式、貼進報告），所以「要不要那
幾百欄」是使用者的一格；資料夾裡那份 ``defects.csv`` 是**報表的隨附檔**，
關掉特徵之後幾乎是空的 —— 一格沒有人會打開的開關。當時還特地寫下「下一個
看到這裡的人會想統一它，而那是加旋鈕不是收斂」。

**F38 這一輪那個答案變了，而變的不是理由，是題目。** ``output_csv`` 這張卡
不存在了，所以問題從「要不要**加**一格」變成「那一格要不要**跟著它的卡一起
消失**」—— 而讓它消失會拿掉一個真的有人在用的用途（乾淨的交付物），代價比
多一格大。使用者 2026-08-26 定調：**跟著進來，列為 advanced**。

所以現在它在 ``output_report`` 上，``advanced=True`` 且
``show_when=("contents", ("table",))`` —— 沒勾表格的人根本看不到它。

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
# `align_off_*` 是那張卡的產出，「它什麼時候不能讀」的判準因此也住在
# 那張卡上 —— 這裡只負責把它講到使用者眼前（同 `overlay_marks` 的分工）。
from .align_to import degenerate_offset_note



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

    #: 這張卡的 ``PATH`` 那一格指的是**資料夾**嗎（子類用 ``PATH = "folder"``
    #: 宣告，這裡推導）。兩種卡的「填錯了」是**相反的兩句話**，而以前只有
    #: 一半住在基底：寫檔案的那一句在這裡，寫資料夾的那一句被兩張卡各抄了
    #: 一份到 `run_batch` 裡（F37 B2 收成一份）。
    #:
    #: 抄兩份的代價不是重複本身，是**時機**：`run_batch` 那一份要等使用者按下
    #: 去、跑完一整批之後才講，而這裡這一份在畫布上就掛得出警示標記。
    @classmethod
    def wants_folder(cls) -> bool:
        return cls.PATH == "folder"

    @classmethod
    def path_issue(cls, path: str) -> str:
        """這條路徑填錯了嗎（沒問題回空字串）—— **兩種卡共用的那一份**。"""
        if cls.wants_folder():
            if os.path.isfile(path):
                return ("“%s” is a file, not a folder. This card writes "
                        "several files, so it needs a folder to put them in."
                        % path)
            return ""
        if os.path.isdir(path):
            # 指到一個**資料夾**是使用者最容易犯的那一個（貼了路徑忘了加檔名），
            # 而跑起來的症狀是 `IsADirectoryError` —— 那句話對他沒有意義。
            return ("“%s” is a folder, not a file. Add the file name to the "
                    "end of the path." % path)
        return ""

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        path = str(params.get(cls.PATH, "") or "").strip()
        if not path:
            return ["This card has nowhere to write yet. Put the full path of "
                    "the %s into “Write to”." % cls.WHAT]
        wrong = cls.path_issue(path)
        return [wrong] if wrong else []
        # ⚠ **不檢查「資料夾存不存在」**：`report.write_csv` 那一族會自己建
        # （`_ensure_parent`），而 Export 精靈走的是同一支。在這裡擋的話，
        # 一個完全正常的路徑會被說成設定錯誤。第一版真的這樣寫了，測試抓到。

    def _folder_of(self, p: Dict[str, Any]) -> str:
        """寫資料夾那幾張卡的開場白（**三行一模一樣的東西收成一支**）。"""
        folder = str(p[self.PATH]).strip()
        if not folder:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        wrong = self.path_issue(folder)
        if wrong:
            raise StepError(self.key, wrong)
        return folder

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
#: F38 併進來的兩樣（原 ``output_report`` 的 Excel 與 ``output_boxplot``）。
CONTENT_EXCEL = "excel"
CONTENT_BOXPLOT = "boxplot"
#: **勾得到的全部**（＝驗證表）。
CONTENTS = (CONTENT_REPORT, CONTENT_TABLE, CONTENT_PICTURES, CONTENT_RECIPE,
            CONTENT_EXCEL, CONTENT_BOXPLOT)

#: **預設勾哪幾個** —— 跟 :data:`CONTENTS` 是**兩份**，這一點很要緊。
#:
#: 「列得出什麼」與「預設是什麼」寫成同一份的話，F38 加進 Excel 與 box plot
#: 的那一刻，每一份**沒有寫 ``contents`` 這個鍵**的舊 ``output_bundle``
#: recipe（出貨那份就是）都會安靜地多寫兩個檔案 —— 因為「鍵不在」的解讀是
#: 「還沒設過＝用預設」。同一個形狀 F18 踩過一次（`COMPARE_METRICS` 同時是
#: 清單與驗證表，見 `docs/PITFALLS.md`）。
#:
#: 另外兩個不預設勾，各自還有一個自己的理由：
#:
#: * **Excel 要 `openpyxl`**，而公司機不一定裝得起來（`AGENTS.md` §1）。
#:   預設開啟等於把一個環境問題變成每一份 recipe 都會看到的一句警告。
#: * **box plot 要有判定樹或一份指定的清單**，兩個都沒有的時候它講一句話 ——
#:   預設開啟等於對每一份沒有樹的 recipe 喊狼來了（推廣鐵則）。
DEFAULT_CONTENTS = (CONTENT_REPORT, CONTENT_TABLE, CONTENT_PICTURES,
                    CONTENT_RECIPE)

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
    """「這個資料夾裡要放什麼」（見 :data:`CONTENTS` 與 :data:`DEFAULT_CONTENTS`）。"""
    return ParamSpec(
        name="contents", type="multi_choice",
        default=",".join(DEFAULT_CONTENTS),
        choices=list(CONTENTS), label="What to put in the folder",
        choice_help={
            CONTENT_REPORT: "A page you open in a browser: how the lot split "
                            "across the classes, then one row per defect. "
                            "Tick pictures too and you can click a row to "
                            "see that defect.",
            CONTENT_TABLE: "The same numbers as a CSV, for opening in Excel "
                           "or feeding to something else.",
            CONTENT_PICTURES: "One image per defect, in an images folder "
                              "beside the report.",
            CONTENT_EXCEL: "An .xlsx workbook: a summary sheet, the same "
                           "table again, and the range of every measured "
                           "number. Needs openpyxl installed.",
            CONTENT_BOXPLOT: "One box plot per number, with a box for each "
                             "class the decision came up with - so you can "
                             "see at a glance whether the classes separate.",
            CONTENT_RECIPE: "The settings that produced all of this, so the "
                            "run can be reproduced later.",
        },
        help=("Tick what this folder should hold. Everything else on this "
              "card is about the things you tick here. Tick pictures on its "
              "own and you get a plain folder of images and nothing else."),
    )


def picture_specs() -> List[ParamSpec]:
    """圖的格式與品質（見 :data:`PIC_FORMATS`）。"""
    return [
        ParamSpec(
            name="picture_format", type="chip_choice", default=PIC_JPEG,
            choices=list(PIC_FORMATS), icons=["fmt_jpeg", "fmt_png"],
            choice_labels={PIC_JPEG: "JPEG", PIC_PNG: "PNG"},
            label="Picture files",
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


#: 「``0`` ＝ 全部」這句話**兩張卡逐字同一句**（F37 B2）。
#:
#: 以前它們不一致：報表資料夾那張是 ``min=0`` 而且 0 代表全部，
#: characterization 那張是 ``min=1`` —— 於是同一個數字在兩張卡上，一張是
#: 「不限」、另一張是**填不進去**。使用者學一次那個約定，然後在第二張卡上
#: 被打回來。
#:
#: 兩張卡的 ``label`` 與**預設值**仍然不同，而那是對的：報表資料夾預設 0
#: （一整批的報表，少一半跟完整的長得一模一樣），characterization 預設 200
#: （它為幾十顆設計，每一列都掛圖正是它讀得下去的理由）。**約定共用，
#: 取捨各自保留。**
LIMIT_ZERO_HELP = "Zero means every defect."


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
            name="draw_boxes", type="chip_choice", default=overlay.DRAW_ALL,
            choices=list(overlay.DRAW_MODES),
            icons=["drawn_all", "drawn_none", "drawn_near"],
            label="Draw the other boxes",
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


@register_step
class OutputReportStep(_OutputStep):
    """整批的結果 → 一個資料夾（**Output 段那五張報表卡收成的這一張**，F38）。

    為什麼是一張卡加一排勾，不是五張卡
    ----------------------------------
    使用者 2026-08-26：「七張裡有五張在回答同一個問題，收成三張」。而那句話
    量得出來 —— 合併之前：

    * ``output_html`` 與 ``output_bundle`` 的報表**已經是同一支函式**
      （`export/html.py::build_report`），差別只有一個關鍵字參數 ``images=``；
    * ``output_csv`` / ``output_bundle`` / ``output_char`` 三張走同一支
      `export_report.write_csv`，欄位逐字相同；
    * Excel 的 ``Details`` 分頁就是 CSV 那張表（`export/report.py`）；
    * 當時出貨的 patch recipe 裡，box plot 的路徑本來就寫著
      ``patch_report/spread.html`` —— 它**早就寫進報表資料夾裡**。
      （那份 recipe 2026-09-02 刪了；這裡留著的是當時查帳的依據。）

    所以在使用者眼裡它們不是五件事，是「我要一份報表，裡面要有什麼」的五個
    程度（`CLAUDE.md` §3 的「同一個家族的做法收成一張卡」，前例 F19 的 CD、
    F29 的 `roi_reference`、F37 的 `output_image`）。

    ⚠ **`output_char` 沒有併進來**，而那是查過帳的決定（F37 §5.1，使用者
    「先不合」）：兩種版面的取捨在 6000 顆與 30 顆是**反過來的**，共用的部分
    F37 B2 已經抽乾淨了。守著那個決定的是
    `tests/test_output_convergence.py::test_the_two_layouts_are_still_two_functions`。

    ⚠ **產物的形狀一律是資料夾**（使用者 2026-08-26 定調）。合併之前
    ``output_csv`` / ``output_html`` / ``output_boxplot`` / Excel 那四張各自
    是「一格路徑＝一個檔案」，所以舊 recipe 遷移過來**檔名會換成底下那幾個
    寫死的名字**（`/x/my.csv` → `/x/defects.csv`）。內容逐位元組相同、路徑會
    位移，對照表寫在 `recipe._migrate_folded_output_cards` 的 docstring 裡。
    """

    key = "output_report"
    label = "Write report"
    PATH = "folder"
    WHAT = "folder"
    help = ("Write this run into one folder: a report you can open in a "
            "browser, the same numbers as a spreadsheet, a picture of every "
            "defect, and the recipe that produced them. Tick what you want in "
            "“What to put in the folder” - everything else on this card is "
            "about the things you ticked. Made for a whole lot: thousands of "
            "defects fit, because the pictures sit beside the report instead "
            "of inside it.")
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
            help=("%s Set a number to keep only the worst that many (highest "
                  "score first) - the report still lists every defect, only "
                  "the pictures are limited." % LIMIT_ZERO_HELP),
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
        # 從 `output_html` 併進來的那一格。**box plot 那一頁共用它** ——
        # 兩張卡以前各有一格 `title`，而它們問的是同一句話（這一頁的標題，
        # 空的就用 recipe 的名字）。兩格留著的話，同一個資料夾裡兩份東西會
        # 掛著兩個不同的抬頭，而使用者沒有理由要它們不一樣。
        ParamSpec(
            name="title", type="str", default="",
            label="Heading",
            help=("Heading to put at the top of the pages this card writes. "
                  "Leave it empty to use the recipe's name."),
        ),
        # 從 `output_boxplot` 併進來的 `features`，**改名了**（F38）。
        #
        # 它跟底下那格 `include_features` 擺在同一張卡上，兩個名字都以
        # 「features」開頭而意思完全不同（這一格是「畫哪幾個數字」，那一格是
        # 「CSV 要不要帶特徵欄」）。`label` 逐字沒變，所以**畫面上一個字都
        # 沒動** —— 換的只有 recipe 的鍵（`ParamSpec.label` 存在的理由，F7-9）。
        #
        # ⚠ 型別必須留著 `feature_keys`：特徵改名走的是**型別**不是卡片清單
        # （`recipe._rename_in_node_params`），改成 `str` 的話這一格會安靜地
        # 漏掉，而症狀是「圖照畫，只是畫的不是你在判的那個數字」。
        ParamSpec(
            name="plot_features", type="feature_keys", default="",
            label="Numbers to plot",
            show_when=("contents", (CONTENT_BOXPLOT,)),
            help=("One chart per number, in this order. Leave it empty and "
                  "the box plot shows whatever the decision itself asked "
                  "about - which is usually exactly what you want to see "
                  "spread out."),
        ),
        # 從 `output_csv` 併進來的那一格（使用者 2026-08-26 定調：跟著進來，
        # 列為 advanced）。**這推翻了 F37 B2 §1 的結論**，見模組說明。
        ParamSpec(
            name="include_features", type="bool", default=True,
            label="Include the measured numbers", advanced=True,
            show_when=("contents", (CONTENT_TABLE,)),
            help=("On: the spreadsheet gets one column per number the cards "
                  "above produced (the feature table). Off: only the id, "
                  "whether it worked, the score and the bin."),
        ),
    ]

    #: 資料夾裡那幾個名字（**寫死**：一份報表換一台機器打開還是同一個形狀）。
    REPORT_NAME = "report.html"
    CSV_NAME = "defects.csv"
    RECIPE_NAME = "recipe.json"
    EXCEL_NAME = "report.xlsx"
    PLOT_NAME = "spread.html"
    IMAGE_DIR = "images"

    #: 判定沒有給出類別時（一份沒有 `decide` 的 recipe），全部畫成一個盒子。
    ALL_LABEL = "the whole lot"

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """``rank_by`` ＋ ``plot_features``。

        兩格都是「指到一個不存在的數字也跑得完」的那種（排不出順序就退回檔案
        順序、畫不出來就少一張圖），所以是 optional 不是 required。
        """
        return (ranked_feature(params)
                + parse_key_list(params.get("plot_features", "")))

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        out = list(super().configuration_issues(params))
        # **「這個鍵不在」＝還沒設過＝預設那幾個**，不是「一個都沒勾」。
        # 兩者差很多：前者是每一份合併之前存下來的 recipe（那時候沒有這一格），
        # 而把它們一律說成設定錯誤，等於對著每一份舊檔案喊狼來了。
        if not parse_key_list(params.get("contents",
                                         ",".join(DEFAULT_CONTENTS))):
            # 一個都沒勾的資料夾**會被建出來、而且是空的** —— 跑得完、
            # 沒有錯誤、什麼都沒有。那是這張卡最容易犯的新錯（合併之前
            # 不存在，因為當時沒有「要寫什麼」這一格）。
            out.append("Nothing is ticked in “What to put in the folder”, so "
                       "this card would make an empty folder. Tick at least "
                       "one thing.")
        return out

    @classmethod
    def planned_files(cls, params: Dict[str, Any]) -> List[Dict[str, str]]:
        """按下 Run 這張卡會寫哪幾個檔（**乾跑**：不碰磁碟、不猜大小）。

        照寫入順序回 ``[{"tick", "what", "name"}, …]``。它是 `run_batch` 的
        那張表本人（run_batch 用它決定要寫什麼）—— 跟 Write KLARF 的
        `plan_writeback` 同一條硬規則：寫出前一定先預覽，而預覽跟真跑共用
        同一份計畫才不會漂。圖那一列給的是 pattern（一顆一張，名字跑了才
        知道）；圖放不放進 ``images/`` 由「有沒有報表」決定（F37 的規則，
        跟 run_batch 同一個式子）。
        """
        try:
            p = cls.validate_params(dict(params or {}))
        except Exception:  # noqa: BLE001 — 預覽要容錯，壞參數 validate 會講
            p = dict(params or {})
        want = set(parse_key_list(str(
            p.get("contents") or ",".join(DEFAULT_CONTENTS))))
        out: List[Dict[str, str]] = []
        if CONTENT_PICTURES in want:
            ext = (".png" if str(p.get("picture_format", PIC_JPEG)) == PIC_PNG
                   else ".jpg")
            nested = CONTENT_REPORT in want
            out.append({"tick": CONTENT_PICTURES, "what": "the pictures",
                        "name": ("%s/<defect>%s" % (cls.IMAGE_DIR, ext)
                                 if nested else "<defect>%s" % ext)})
        for tick, what, name in (
                (CONTENT_REPORT, "the report", cls.REPORT_NAME),
                (CONTENT_TABLE, "the spreadsheet", cls.CSV_NAME),
                (CONTENT_EXCEL, "the Excel report", cls.EXCEL_NAME),
                (CONTENT_BOXPLOT, "the box plot", cls.PLOT_NAME),
                (CONTENT_RECIPE, "the recipe", cls.RECIPE_NAME)):
            if tick in want:
                out.append({"tick": tick, "what": what, "name": name})
        return out

    # ----------------------------------------------------------------- #
    # box plot（併進來的 `output_boxplot`，F38）
    # ----------------------------------------------------------------- #
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

    def _write_boxplot(self, bctx: Any, p: Dict[str, Any], path: str) -> None:
        """一片葉子一個盒子（原 `output_boxplot`，行為逐字不變）。

        ⚠ **一個盒子是一片葉子，不是一個 bin。** 兩片葉子共用一個 bin 是合法
        的，而它們是使用者眼中兩個不同的類別（`verdict_rows` 的說明）。順序與
        顏色跟畫布上的樹一樣 —— 三個地方講同一件事的時候，長相也該是同一個。
        """
        decide = getattr(bctx.recipe, "decide", None)
        names = parse_key_list(p["plot_features"])
        if not names:
            # **判定問過的那幾個** —— 使用者想看的散布，九成是他拿來分類的那些。
            names = decide_tree.features_used(decide) if decide else []
        if not names:
            raise StepError(
                self.key,
                "nothing to plot: “Numbers to plot” is empty and this recipe "
                "has no decision to borrow the numbers from. Put the name of "
                "at least one measured number in that box, or untick the box "
                "plot.")
        groups = [g for g in decide_tree.verdict_rows(decide, bctx.rows)
                  if g.get("kind") not in ("failed", "unbinned")
                  and (g.get("ids") or [])]
        if not groups:
            groups = [{"name": self.ALL_LABEL,
                       "ids": [str(r.get("defect_id", ""))
                               for r in bctx.rows if r.get("ok")],
                       "colour": export_boxplot.FALLBACK_COLOUR}]
        charts = self._charts(bctx, names, groups)
        # ⚠ 這一頁的 fallback 是 ``"d4t"``，報表那一頁是 ``"d4t results"``
        # —— 合併之前兩張卡就是這樣，而它只在「recipe 沒有名字」時看得出差別。
        # 統一成一個的話，那幾份 recipe 的輸出會安靜地換一個抬頭。
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

    # ----------------------------------------------------------------- #
    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        folder = self._folder_of(p)
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

        # ---- ② 其餘每一樣**各自寫、各自失敗**（F38）-----------------------
        #
        # 合併之前這幾樣是五張卡，所以「Excel 寫不出來」只毀掉 Excel 那張卡。
        # 併成一張之後，一個 raise 會把報表、CSV、圖、recipe 一起丟掉 ——
        # 那是合併帶進來的、以前不存在的壞法。所以規則是：**一樣失敗就是一句
        # 話，不連坐**；勾了的全部失敗才 raise（那時候這張卡真的什麼都沒做，
        # 而「跑完了但資料夾是空的」比一個錯誤訊息糟得多）。
        title = (str(p["title"]).strip()
                 or str(getattr(bctx.recipe, "recipe_id", "") or "d4t results"))
        # tick → 寫入器。「哪一勾寫哪一個檔、叫什麼」住在 `planned_files`
        # （儀表的預覽跟這裡讀**同一張表** —— 各寫一份的那份會漂，儀表列的
        # 檔名跟真的寫出來的對不上）。這裡只補上寫入的動作。
        writers = {
            CONTENT_REPORT: lambda path: export_html.write_html(
                export_html.build_report(
                    rows, title, export_report.feature_keys(rows),
                    decide=getattr(bctx.recipe, "decide", None),
                    images=images),
                path),
            CONTENT_TABLE: lambda path: export_report.write_csv(
                rows, path, include_features=bool(p["include_features"])),
            CONTENT_EXCEL: lambda path: export_report.write_excel(
                rows, path, recipe=bctx.recipe),
            CONTENT_BOXPLOT: lambda path: self._write_boxplot(bctx, p, path),
            # **沒有它，半年後沒人重現得出這份報表。** 那不是保險，是這份東西
            # 有沒有用的分界：一疊數字沒有配方，等於一句「我們那時候量到這樣」。
            CONTENT_RECIPE: lambda path: write_recipe_json(bctx, path),
        }
        asked = 0
        done = 0
        why: List[str] = []
        for planned in self.planned_files(p):
            tick, what, name = planned["tick"], planned["what"], planned["name"]
            write = writers.get(tick)
            if write is None:
                continue        # 圖那一列（上面 ① 已經寫了，不在這個迴圈）
            asked += 1
            try:
                write(os.path.join(folder, name))
                done += 1
                continue
            except ImportError as e:
                # openpyxl 沒裝 —— 那是**環境**的事，不是 recipe 的事，所以
                # 訊息要指向 `tools/install_offline.py`（公司機裝不了東西，
                # 見 AGENTS.md）。
                said = ("could not write %s: %s. Install openpyxl (on the "
                        "fab machine: tools/install_offline.py), or untick "
                        "Excel - the spreadsheet tick needs nothing extra."
                        % (what, e))
            except StepError as e:
                # 那一樣自己講得出**下一步**（box plot 的「Numbers to plot」
                # 是空的那一句）。包一層「something went wrong」上去的話，
                # 使用者拿到的是一句沒有下一步的話（推廣鐵則）。
                said = str(getattr(e, "detail", "") or e)
            except Exception as e:  # noqa: BLE001 — 一樣失敗不連坐其他樣
                said = "could not write %s: %s" % (what, e)
            why.append(said)
            bctx.warn("Report folder: %s" % said)
        if asked and not done:
            # **勾了的全部失敗 ⇒ 這張卡真的什麼都沒做**，那不是一句警告。
            # 訊息帶著每一樣自己的理由 —— 只勾了一樣的時候（＝每一份從舊的
            # 單檔卡遷移過來的 recipe），那句話跟合併之前逐字相同。
            raise StepError(self.key, " ".join(why))

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
            name="mode", type="chip_choice", default="annotate",
            choices=list(klarf_out.MODES),
            icons=["klarf_inplace", "klarf_annotate", "klarf_topn"],
            choice_labels={"inplace": "In place", "topn": "Top N"},
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
                "coordinates). Use the report card instead.")
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
    label = "Write comparison"
    PATH = "folder"
    WHAT = "folder"
    help = ("Write a folder that puts the two lots side by side, one defect "
            "per row: the ground-truth picture, the matching picture from the "
            "second lot, the numbers you pick, and what the recipe decided. "
            "Made for a characterization run of a few dozen defects, where "
            "you want to check every row by eye - for a whole lot use “Write "
            "report” instead.")
    params = [
        ParamSpec(
            name="folder", type="str", default="",
            label="Write to",
            help=("Folder to write everything into. It is created if it does "
                  "not exist; files with the same names are overwritten."),
        ),
        ParamSpec(
            name="limit", type="int", default=200, min=0, max=100000,
            label="At most this many rows with pictures",
            help=("This report puts a picture on every row, which is what "
                  "makes it readable at a glance and also what stops it "
                  "scaling. Above this many defects the extra rows are still "
                  "listed, without pictures, and the card says so. %s"
                  % LIMIT_ZERO_HELP),
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
        # **框怎麼畫跟報表資料夾那張逐字同一組**（F37 B2）。這張卡以前**畫圖
        # 卻畫不出框** —— 而 GLV 逐框比較的贏家框正是報表上最該看到的東西
        # （「這一顆為什麼被判成這一類」的答案就在那個框裡）。
        *roi_draw_specs(),

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

    @classmethod
    def planned_files(cls, params: Dict[str, Any]) -> List[Dict[str, str]]:
        """會寫哪幾個檔（乾跑）—— 這張卡沒有勾選，**固定四樣**。

        同 `OutputReportStep.planned_files` 的契約：不碰磁碟、不猜大小；
        圖那一列是 pattern（一顆兩張：main / pair）。
        """
        return [
            {"tick": "pictures", "what": "the pictures",
             "name": "%s/<defect>_main.jpg + _pair.jpg" % cls.IMAGE_DIR},
            {"tick": "report", "what": "the report", "name": cls.REPORT_NAME},
            {"tick": "table", "what": "the spreadsheet",
             "name": cls.CSV_NAME},
            {"tick": "recipe", "what": "the recipe", "name": cls.RECIPE_NAME},
        ]

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        folder = self._folder_of(p)

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
        # 這份報表的每一列都建在 `align_off_*` 上，而那一欄踩著一個廠內還沒
        # 驗證過的前提（`docs/FAB-VALIDATION.md` 假設 #7）。前提不成立的時候
        # 報表**看起來最漂亮**（每一顆都對得剛剛好）—— 所以這句話要在這裡講。
        note = degenerate_offset_note(rows)
        if note:
            bctx.warn("Characterization report: %s" % note)
        # ``0`` ＝ 全部（見 :data:`LIMIT_ZERO_HELP`）。``ordered[:0]`` 會是
        # **一張圖都沒有**，而那正好是「不限」的相反 —— 所以要轉成 None。
        cut = limit if limit > 0 else None
        if limit and len(ordered) > limit:
            # **講出來，不要自動換版面**：使用者要知道他拿到的是哪一種報表。
            bctx.warn(
                "Characterization report: %d defects, but this report puts a "
                "picture on every row and is made for a few dozen - only the "
                "first %d rows have pictures. For a whole lot use “Write "
                "report”, which lists every defect and shows one "
                "picture at a time." % (len(ordered), limit))

        # ---- ② 圖（一顆兩張：跑的這一份 ＋ 第二份帶過來的那一張）-----------
        main_key = str(p["main_stream"]).strip()
        pair_key = str(p["pair_stream"]).strip()
        thumbs: Dict[str, Dict[str, Optional[str]]] = {}
        skipped = 0
        degraded_any = False
        for row in ordered[:cut]:
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
                ctx = getattr(r, "context", None)
                marks = (_defect_marks(ctx, pix, main_key)
                         if bool(p["mark_defect"]) else {})
                # ROI 框（F37 B2）—— **只畫在真的被量的那條流上**。
                # 換一條流當背景時框的座標就沒有意義了，而一個指著錯地方的框
                # 比沒有框糟得多（同 `_defect_marks` 的「不猜」）。
                roi_kw, degraded = _roi_overlay_kwargs(ctx, p)
                degraded_any = degraded_any or degraded
                measured = str((overlay.worst_note_for_overlay(ctx)[2] or {})
                               .get("stream") or "")
                pair = {}
                for side, key in (("main", main_key), ("pair", pair_key)):
                    arr = (pix.get(key) if key
                           else (overlay.pick_base(pix)[1] if pix else None))
                    if arr is None:
                        # 配不到的那一顆沒有第二張圖 —— 那一格留白，
                        # 而留白正是它要講的話（不是破圖、不是 0×0 的框）。
                        continue
                    boxes = roi_kw if key and key == measured else {}
                    if (side == "main" and marks) or boxes:
                        panel = overlay.render_overlay(
                            {"_": arr}, {}, base_key="_", montage=False,
                            box=marks.get("box") if side == "main" else None,
                            aim=marks.get("aim") if side == "main" else None,
                            **boxes)
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
        if degraded_any:
            # 安靜退化的圖跟全畫的圖看起來都「有框」—— 要講一次（同另外那張）。
            bctx.warn("Characterization report: more region boxes than “Draw "
                      "at most” (%d), so only the boxes near the winner are "
                      "drawn." % int(p["draw_boxes_cap"]))
