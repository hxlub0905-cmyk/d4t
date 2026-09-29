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
三張」）—— 之後多了第四張 ``output_uniformity``（「Write charts」，F85 的均勻度
圖），它不在下面這張表裡是因為它不是從那七張收來的：

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..export import boxplot as export_boxplot
from ..export import chart_frame as export_frame
from ..export import uniformity_charts as export_unif
from ..pipeline import chart_spec
from ..pipeline import chart_style
from ..export import html as export_html
from ..export import klarf_out, overlay
from ..export import report as export_report
from ..pipeline import decide_tree
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_BATCH, GROUP_OUTPUT, SCALE_LOT, ParamSpec, Step, StepError,
    register_step,
)
from ..log import swallowed
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
    #: 「Write to」空著時寫到哪（F122，使用者：「預設寫到資料旁邊」）。相對
    #: 路徑，跟填了相對路徑一樣接在資料旁邊（`_anchor`）。**每張卡一個名字**：
    #: 兩張卡都空著時不會寫進同一個資料夾互蓋。Write KLARF 不用這一格
    #: （它的預設跟著 KLARF 的檔名走，見 `OutputKlarfStep.default_path`）。
    DEFAULT = ""

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
        # **空著不是錯**（F122）：空＝寫到資料旁邊的預設位置。以前這裡是一條
        # error，而 error 會擋住**試跑** —— 試跑根本不寫（鐵則 11），於是新加
        # 一張 Output 卡就什麼都跑不了，直到使用者想出一條路徑。
        path = str(params.get(cls.PATH, "") or "").strip()
        if not path:
            return []
        wrong = cls.path_issue(path)
        return [wrong] if wrong else []
        # ⚠ **不檢查「資料夾存不存在」**：`report.write_csv` 那一族會自己建
        # （`_ensure_parent`），而 Export 精靈走的是同一支。在這裡擋的話，
        # 一個完全正常的路徑會被說成設定錯誤。第一版真的這樣寫了，測試抓到。

    def _folder_of(self, p: Dict[str, Any], bctx: Any = None) -> str:
        """寫資料夾那幾張卡的開場白（**三行一模一樣的東西收成一支**）。"""
        folder = str(p[self.PATH]).strip() or self.DEFAULT
        if not folder:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        folder = _anchor(folder, bctx)
        wrong = self.path_issue(folder)
        if wrong:
            raise StepError(self.key, wrong)
        return folder

    def destination(self, params: Dict[str, Any], dataset: Any) -> str:
        """「Write to」解出來**真的是哪裡**（乾跑用，F122 期 4）。

        跟 `run_batch` 走同一支（`_folder_of` / `_path_of`）：相對路徑接在資料
        旁邊、空著用這張卡的預設。解不出來就 raise `StepError`（那句話就是答案）。
        """
        p = self.validate_params(params)
        where = _DataOnly(dataset)
        return (self._folder_of(p, where) if self.wants_folder()
                else self._path_of(p, where))

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

    def _path_of(self, p: Dict[str, Any], bctx: Any = None) -> str:
        path = str(p[self.PATH]).strip()
        if not path:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        return _anchor(path, bctx)


class _DataOnly:
    """只帶著資料集的替身 —— `_anchor` / `_path_of` 只問 ``.dataset``。"""

    def __init__(self, dataset: Any) -> None:
        self.dataset = dataset


def _anchor(path: str, bctx: Any) -> str:
    """**相對路徑接在資料旁邊，不接在「現在站在哪」**（2026-09-24）。

    出貨的 recipe 寫的是 ``"folder": "ebi_report"`` —— 以前那是相對於行程的
    工作目錄，於是在 repo 根目錄跑一次 CLI 就多一個沒被追蹤的 `ebi_report/`，
    而在 Studio 裡它落在「Studio 從哪裡開的」那個看不見的地方。現在接在
    KLARF 所在的資料夾（沒有 KLARF 的就是影像那個資料夾）旁邊：使用者找
    報表時第一個會去看的地方。絕對路徑、或答不出資料在哪時照原樣。
    """
    if os.path.isabs(path):
        return path
    ds = getattr(bctx, "dataset", None)
    src = ""
    try:
        src = str(ds.source_label() or "") if ds is not None else ""
    except Exception:          # 資料集長得不一樣（測試的替身）→ 照原樣
        swallowed("output._anchor")
    if not src:
        return path
    base = os.path.dirname(src) if os.path.isfile(src) else src
    return os.path.join(base, path)


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
        except Exception:  # 沒圖就沒有記號
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
#: F89-4：**一張跨顆的圖**（一列一顆 defect 的長表 ＋ 使用者自己配的角色）。
#:
#: 為什麼它在這張卡而不是 `Write charts`：那張卡是**一顆一頁**（它的長表是
#: 「一顆之內、一列一格框」），而這一張問的是「這一批 400 顆怎麼散」「哪一個
#: die 特別差」。手冊本來就寫著「跨整批的一列一顆請用 Write report」。
CONTENT_LOTCHART = "lotchart"
#: **勾得到的全部**（＝驗證表）。
CONTENTS = (CONTENT_REPORT, CONTENT_TABLE, CONTENT_PICTURES, CONTENT_RECIPE,
            CONTENT_EXCEL, CONTENT_BOXPLOT, CONTENT_LOTCHART)

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
            CONTENT_LOTCHART: "One chart you build yourself, over the "
                              "whole lot - one point per defect instead of "
                              "one per measurement box. Pick which two "
                              "columns go on the axes beside “Lot chart”. "
                              "With a KLARF you also get the die each defect "
                              "sits in, so die column x die row coloured by "
                              "a number is a wafer map.",
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

#: 為什麼「鎖住尺度」值得兩格參數（F85）。
#:
#: auto 縮放在**看一批**的時候是對的，兩批擺在一起就會騙人：每一張各自挑
#: 各自的範圍，於是兩張圖上一樣高的柱子其實不一樣高、一樣紅的格子其實不
#: 一樣亮。而那件事**圖上沒有任何線索**（軸上的數字要一格一格去讀才發現）。
#: 這是 PEAR `ChartSettingsDialog` 的 docstring 講的同一件事。
_LOCK_WHY = ("Lock it whenever you will put two runs side by side: without "
             "a lock each chart picks its own range, so two bars of the same "
             "height are not the same number.")


def _write_text(text: str, path: str) -> str:
    """一份純文字 → 一個檔（**atomic**：`.tmp` + `os.replace`，鐵則 5）。

    走 `export_html.write_html` 那一支 —— SVG 跟 HTML 在這裡是同一件事
    （UTF-8 的文字檔），而寫入的規矩只該有一份。
    """
    return export_html.write_html(text, path)


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
    DEFAULT = "d4t_report"
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
                  "not exist; files with the same names are overwritten. "
                  "Empty = a folder called “d4t_report” next to your data."),
        ),
        contents_spec(),
        *picture_specs(),
        # **預設 0 = 全部**（使用者定調 2026-08-25：「參數化，預設全部」）。
        # 併進來的 `output_image` 預設 200，而它們的用途不同：那個是「挑幾顆
        # 來看」，這一張是「這一批的報表」—— 一份少了一半的報表跟完整的長得
        # 一模一樣。遷移**照舊值搬**，所以既有的 recipe 行為不變。
        ParamSpec(
            name="limit", type="int", default=0, min=0, max=1000000,
            label="At most this many pictures", min_label="All of them",
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
        # F87 第九刀：**這張卡的盒鬚圖跟 `Write charts` 的是同一支程式碼，
        # 但以前只有後者吃得到設定** —— 於是同一份投影片裡兩張盒鬚圖的字級、
        # 線寬、鎖定範圍都不一樣，而畫面上沒有任何線索說為什麼。
        ParamSpec(
            name="look", type="chart_style", default="",
            label="Chart look", section="Box plot",
            help=("How the charts look: text size and colour, marker and "
                  "line width, whiskers, tick counts, spec limits - and "
                  "whether the value scale is locked. Press “Chart settings…” "
                  "beside this row. It is the same editor the charts card "
                  "uses, so a deck with both kinds of chart can be made to "
                  "match."),
        ),
        ParamSpec(
            name="spec", type="chart_spec", default="",
            label="Lot chart: what goes where", section="Box plot",
            # 沒勾那張圖就別問這件事（同 `Write charts` 的 `spec`）。
            show_when=("contents", (CONTENT_LOTCHART,)),
            help=("The one chart you build yourself over the whole lot - "
                  "**one point per defect**, not per measurement box. Pick "
                  "which measured number runs across the bottom, which one "
                  "runs up the side, and what the colour and marker size "
                  "mean. With a KLARF you also get the die each defect sits "
                  "in: die column across, die row up the side, coloured by a "
                  "number, is a wafer map."),
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
    LOTCHART_NAME = "lot-chart.svg"
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
        except Exception:  # 預覽要容錯，壞參數 validate 會講
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
                (CONTENT_LOTCHART, "the chart you built", cls.LOTCHART_NAME),
                (CONTENT_RECIPE, "the recipe", cls.RECIPE_NAME)):
            if tick in want:
                out.append({"tick": tick, "what": what, "name": name})
        return out

    # ----------------------------------------------------------------- #
    # box plot（併進來的 `output_boxplot`，F38）
    # ----------------------------------------------------------------- #
    #: 一次畫好幾張盒鬚圖（一個數字一張）—— 見 `Step.chart_words`。
    chart_words = False

    @classmethod
    def chart_kinds(cls, params: Dict[str, Any]) -> List[str]:
        # ⚠ 勾了跨顆那張圖，設定編輯器就要多一個分頁 —— 不然它的標題與軸名
        # 改不到（同 `Write charts` 的 `charts`）。
        got = parse_key_list(str(params.get("contents", "") or ""))
        kinds = [export_unif.CHART_BOX]
        if CONTENT_LOTCHART in got:
            kinds.append(export_unif.CHART_CUSTOM)
        return kinds

    def _charts(self, bctx: Any, names: List[str],
                groups: List[Dict[str, Any]],
                style: Optional[Dict[str, Any]] = None
                ) -> List[Dict[str, Any]]:
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
            # **在這裡就畫成 SVG**，因為要把 `look` 套進去；
            # `build_boxplot_page` 本來就認得畫好的 `svg`（F85 那四張圖走的
            # 也是這條路），所以那一支一個字都沒有動。
            #
            # ⚠ **標題強制是特徵名**：這一頁一個數字一張圖，一組共用的標題
            # 會同時套到五張上。那也是這張卡 `chart_words = False` 的理由。
            st = dict(style or {})
            st["title"] = name
            charts.append({
                "title": name, "series": series,
                "subtitle": "one box per class - the line is the "
                            "median, the box is the middle half",
                "svg": export_boxplot.build_boxplot_svg(
                    series, title=name,
                    subtitle="one box per class - the line is the median, "
                             "the box is the middle half", style=st)})
        if empty:
            bctx.warn(
                "Box plot: no defect has a number called %s, so %s not "
                "plotted. Check the spelling in “Numbers to plot”, or leave "
                "that box empty to plot whatever the decision asks about."
                % (", ".join("“%s”" % n for n in empty),
                   "it was" if len(empty) == 1 else "they were"))
        return charts

    def lot_frame(self, bctx: Any) -> Any:
        """這一批的長表：**一列一顆 defect**（F89-4）。

        ⚠ 座標從 `bctx.dataset.items` 接上來 —— 結果那一列裡沒有它們
        （`result_to_json_dict` 只裝 id / ok / score / bin / features）。
        有 KLARF 的話 `die_x` × `die_y` 配一個統計量當顏色就是一張 wafer map。
        """
        return export_frame.build_lot_frame(
            bctx.rows, list(getattr(bctx.dataset, "items", None) or []))

    def _write_lot_chart(self, bctx: Any, p: Dict[str, Any],
                         path: str) -> None:
        """跨整批那一張圖。**畫不出來也要寫一個說得出原因的檔**。

        使用者勾了它就是要一個檔；一個消失的檔案跟「這張卡沒跑到」在資料夾裡
        長得一模一樣（同 `_empty` 那條規矩）。
        """
        svg = export_unif.build_chart_svg(
            {}, export_unif.CHART_CUSTOM,
            export_unif.resolve_style(p.get("look", ""),
                                      export_unif.CHART_CUSTOM),
            frame=self.lot_frame(bctx), spec=p.get("spec", ""))
        _write_text(svg, path)

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
        charts = self._charts(
            bctx, names, groups,
            style=export_unif.resolve_style(p.get("look", ""),
                                            export_unif.CHART_BOX))
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
        folder = self._folder_of(p, bctx)
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
            except Exception:  # 一顆畫不出來不該殺掉整批
                skipped += 1

        # ---- ② 其餘每一樣**各自寫、各自失敗**（F38）-----------------------
        #
        # 合併之前這幾樣是五張卡，所以「Excel 寫不出來」只毀掉 Excel 那張卡。
        # 併成一張之後，一個 raise 會把報表、CSV、圖、recipe 一起丟掉 ——
        # 那是合併帶進來的、以前不存在的壞法。所以規則是：**一樣失敗就是一句
        # 話，不連坐**；勾了的全部失敗才 raise（那時候這張卡真的什麼都沒做，
        # 而「跑完了但資料夾是空的」比一個錯誤訊息糟得多）。
        # 標題：使用者打的字 → recipe 的描述 → recipe id（F117 F6 的前半）。
        # ⚠ **`recipe_id` 排最後**：它是 JSON 的鍵（`ebi_die_to_die`），不是
        # 一份報表的標題 —— 而描述是使用者自己寫的一句話。
        rd = (bctx.recipe.to_json_dict()
              if hasattr(bctx.recipe, "to_json_dict") else {})
        title = (str(p["title"]).strip()
                 or str(rd.get("description") or "").strip()
                 or str(getattr(bctx.recipe, "recipe_id", "") or "d4t results"))
        # **這一次跑的身分**（F117 F2）：HTML 與 xlsx **同源**，所以算一次。
        # 一份報表離開這台電腦之後，這幾行是唯一追得回來的東西。
        ds = getattr(bctx, "dataset", None)
        _label = getattr(ds, "source_label", None)
        run = export_report.run_info(
            bctx.recipe,
            # ⚠ `hasattr` 對型別檢查器什麼都沒講（`ds` 仍然是 `None | Any`），
            # 而 `run_info` 的 `source` 要一個 `str`。拿出來再 `callable`
            # 一次，型別跟實情才是同一件事。
            source=str(_label()) if callable(_label) else "",
            n_rows=len(rows),
            n_source=len(getattr(ds, "items", None) or []) or None)
        # tick → 寫入器。「哪一勾寫哪一個檔、叫什麼」住在 `planned_files`
        # （儀表的預覽跟這裡讀**同一張表** —— 各寫一份的那份會漂，儀表列的
        # 檔名跟真的寫出來的對不上）。這裡只補上寫入的動作。
        writers = {
            CONTENT_REPORT: lambda path: export_html.write_html(
                export_html.build_report(
                    rows, title, export_report.detail_feature_keys(rows),
                    decide=getattr(bctx.recipe, "decide", None),
                    images=images, info=run),
                path),
            CONTENT_TABLE: lambda path: export_report.write_csv(
                rows, path, include_features=bool(p["include_features"])),
            CONTENT_EXCEL: lambda path: export_report.write_excel(
                rows, path, recipe=bctx.recipe, run=run),
            CONTENT_BOXPLOT: lambda path: self._write_boxplot(bctx, p, path),
            CONTENT_LOTCHART: lambda path: self._write_lot_chart(
                bctx, p, path),
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
            except Exception as e:  # 一樣失敗不連坐其他樣
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
            help=("annotate = a new file with ADCCLASS (the bin) added, and "
                  "ADCSCORE when the decision has a score (the original is "
                  "untouched - start here). inplace = edit "
                  "the original file, changing only the bytes that have to "
                  "change. topn = a new file with only the highest scoring "
                  "defects in it."),
        ),
        ParamSpec(
            name="path", type="str", default="",
            label="Write to",
            help=("Full path of the KLARF file to write. Folders that do not "
                  "exist yet are created. For “in place” this is the file "
                  "that gets edited, so point it at the original. Empty = "
                  "next to the original, with “_adc” (top N: “_top”) added "
                  "to its name; for “in place”, the original itself."),
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

    #: 沒有 KLARF 的資料上，這張卡講的那一句（開資料時掛在卡上、寫的時候跳過時
    #: 各講一次 —— 同一句話，所以只寫一份）。
    NO_KLARF = ("This data has no KLARF (a folder of images carries no "
                "coordinates), so there is nothing to write the verdicts back "
                "into - this card is skipped when you write, and the other "
                "outputs are still written. “Write report” puts the same "
                "verdicts in a spreadsheet.")

    @classmethod
    def data_issues(cls, params: Dict[str, Any],
                    data: Any) -> List[Tuple[str, str, str, str]]:
        """沒有 KLARF 的資料 → **開資料的那一刻**就在卡上講（F122）。

        以前這件事要等按下「Write outputs」、整批寫到這張卡才失敗，而那之前
        儀表還顯示「N 顆會改」的估計。warning 不是 error：它不擋跑、也不擋其他
        輸出（使用者：「按寫時跳過並講，其他輸出照寫」）。
        """
        if getattr(data, "has_klarf", True):
            return []
        return [("klarf-out-no-klarf", "warning",
                 "“Write KLARF” has no KLARF to write into", cls.NO_KLARF)]

    #: 「Write to」空著時寫到哪（F122）—— 住在 `klarf_out`（寫 KLARF 的那一層），
    #: 儀表與 Studio 的確認對話框叫同一支。
    default_path = staticmethod(klarf_out.default_output_path)

    def _path_of(self, p: Dict[str, Any], bctx: Any = None) -> str:
        path = str(p[self.PATH]).strip()
        if path:
            return _anchor(path, bctx)
        doc = getattr(getattr(bctx, "dataset", None), "klarf", None)
        path = self.default_path(str(p["mode"]),
                                 str(getattr(doc, "source_path", "") or ""))
        if not path:
            raise StepError(self.key, "nowhere to write - fill in “Write to”.")
        return path

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        doc = getattr(bctx.dataset, "klarf", None)
        if doc is None:
            # **跳過並講，不是失敗**（F122，使用者定的）。這件事開資料時已經
            # 掛在卡上（`data_issues`），資料集標籤上也常駐 `· no KLARF`；
            # 以前這裡是一個 StepError —— CLI 回 1、Studio 跳「Some outputs
            # were not written」，而其他卡明明都寫好了。
            bctx.warn("%s: skipped. %s" % (self.label, self.NO_KLARF))
            return
        path = self._path_of(p, bctx)
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
    #: 這張卡有一本手冊（F117 K1）—— 參數區那一行 "Manual" 打開它。
    manual = "USING-CHARACTERIZATION.md"
    label = "Write comparison"
    PATH = "folder"
    WHAT = "folder"
    DEFAULT = "d4t_comparison"
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
                  "not exist; files with the same names are overwritten. "
                  "Empty = a folder called “d4t_comparison” next to your data."),
        ),
        ParamSpec(
            name="limit", type="int", default=200, min=0, max=100000,
            label="At most this many rows with pictures",
            min_label="All of them",
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
    def optional_streams_in(cls, params: Dict[str, Any]) -> List[str]:
        """左右兩張圖的流名（F122）—— 這張卡沒有埠，打錯了只會是空的那一格。
        左邊空著＝「這一顆跑的起點」，不是一個名字，所以不算。"""
        return [n for n in (str(params.get("main_stream", "") or "").strip(),
                            str(params.get("pair_stream", "") or "").strip())
                if n]

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
        folder = self._folder_of(p, bctx)

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
            except Exception:  # 一顆畫不出來不該殺掉整批
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


@register_step
class OutputUniformityStep(_OutputStep):
    """均勻度的四種圖：**一張影像之內，一格框一個點**（F85）。

    為什麼是第三張寫資料夾的卡，不是 `Write report` 的一格 tick
    ----------------------------------------------------------
    那張卡寫的是「整批跑完**一份總表**」—— 每顆 defect 一列，加上判定結果的
    盒鬚圖（**一個盒子＝一片葉子，一個點＝一顆 defect**）。這裡寫的是
    「**一張影像之內**的分布」（一個盒子＝一個區域，一個點＝一格框）。

    兩者在畫面上長得一模一樣，而「一個點是什麼」是唯一的差別。併成一張卡的
    話，那張卡會有兩種跑法與兩種「一個點是什麼」，而 d4t 踩過這個坑：F50
    刪掉 `ui/output_band.py` 的理由就是**框的意思是「這幾個是一組」，真相
    卻是「跑的時間不一樣」**。

    先例是 `pair_source` ↔ `Write comparison`：一張量測卡配一張輸出卡。
    這裡是 **Gray level（``each box`` ＋ ``How even are the boxes``）↔
    Write charts**。

    一顆寫五個檔
    ------------
    ``<顆>.html``（四張圖一頁）＋ ``<顆>-<圖>.svg``（一張一個檔）。
    後者不是多餘：**一份文件要的是一張圖一個檔**，而從一頁裡把 SVG 剪出來
    是使用者做不到的事（PEAR 的 export 選單也是這樣分的）。

    ⚠ ``limit`` **預設不是 0**（見那一格）。
    """

    key = "output_uniformity"
    #: 這張卡有一本手冊（F117 K1）—— 參數區那一行 "Manual" 打開它。
    manual = "USING-UNIFORMITY.md"
    #: ⚠ **只有 `label` 改過**（F88 第六刀，使用者 2026-09-07：「改成 write
    #: charts」）。`key` 是 recipe 的鍵、資料夾裡的檔名沿用它 —— 兩者都不動，
    #: 所以這一次改名的代價是零（CLAUDE.md 那張價目表的最後一列）。
    #:
    #: 為什麼名字該換：F85 的時候它只寫均勻度那四張圖，「uniformity」講得完；
    #: F88 之後它還寫一張**使用者自己配的圖**（五種記號、兩條軸自己挑），而
    #: 那張圖問的可以是任何一句話。
    label = "Write charts"
    PATH = "folder"
    WHAT = "folder"
    DEFAULT = "d4t_charts"
    help = ("Write a page of charts for each defect - one point per "
            "measurement box. Four of them are ready-made (a box plot, a "
            "histogram, a position profile and a heat map) and one you build "
            "yourself. They come from the Gray level card, so set it "
            "to “each box” and tick something under “How even are the boxes” "
            "first. For one row per defect across the whole lot use “Write "
            "report” instead - these charts are about one image at a time.")

    #: 一顆一頁 ＋ 一張圖一個 SVG。
    PAGE_EXT, FIGURE_EXT = ".html", ".svg"
    #: 好幾顆時的入口（一顆的時候不寫，見 `run_batch`）。
    INDEX_NAME = "index.html"

    params = [
        ParamSpec(
            name="folder", type="str", default="",
            label="Write to",
            help=("Folder to write everything into. It is created if it does "
                  "not exist; files with the same names are overwritten. "
                  "Empty = a folder called “d4t_charts” next to your data."),
        ),
        ParamSpec(
            name="charts", type="multi_choice",
            # ⚠ **不是 `CHARTS` 全部** —— 見 `DEFAULT_CHARTS`。
            default=",".join(export_unif.DEFAULT_CHARTS),
            choices=list(export_unif.CHARTS),
            label="Which charts",
            # **格子上寫 `CHART_LABELS`，不是那個鍵**（F117 B4）。第五格以前
            # 寫著 `chart` —— 那是 `CHART_CUSTOM` 的值（檔名 `-chart.svg` 用
            # 的那個字），而使用者在那排勾選框上讀到的是一個不知道是什麼的字。
            choice_labels=dict(export_unif.CHART_LABELS),
            choice_help={
                export_unif.CHART_BOX:
                    "One box per region, one point per measurement box - how "
                    "spread out each region is, and how the regions compare.",
                export_unif.CHART_HIST:
                    "How the values spread out. Two humps usually mean the "
                    "boxes are sitting on two different materials.",
                export_unif.CHART_PROFILE:
                    "The value against where the box sits. A uniform field "
                    "reads as a flat line; the tilt is printed as a slope "
                    "per 100 pixels.",
                export_unif.CHART_MAP:
                    "The boxes at their own place on the image, coloured by "
                    "value - so you can see WHERE it is uneven, not just "
                    "that it is.",
            },
            help=("Tick the charts to draw. Each one is written twice: on a "
                  "page with the others, and on its own as an SVG you can "
                  "drop straight into a document."),
        ),
        ParamSpec(
            name="metric", type="str", default="",
            label="Which number to plot",
            help=("Which gray level statistic the charts are about, for "
                  "example glv_median. Leave it empty to use the first one "
                  "the Gray level card measured."),
        ),
        ParamSpec(
            name="axis", type="chip_choice", default=export_unif.AXIS_X,
            choices=list(export_unif.AXES), icons=["axis_x", "axis_y"],
            choice_labels={export_unif.AXIS_X: "Left to right",
                           export_unif.AXIS_Y: "Top to bottom"},
            label="Profile along",
            # **沒勾那張圖就別問這件事**（F87）。`param_visible` 對逗號清單
            # 做的是**成員比對**（F37），所以一條普通的 `show_when` 就夠了 ——
            # 這一格的第一版把它攤在那裡，而它對只勾了盒鬚圖的人是一個
            # 「答了也沒用」的問題（推廣鐵則）。
            show_when=("charts", (export_unif.CHART_PROFILE,)),
            choice_help={
                export_unif.AXIS_X: "Plot against the box's X, to see a tilt "
                                    "from one side of the image to the other.",
                export_unif.AXIS_Y: "Plot against the box's Y, to see a tilt "
                                    "from top to bottom.",
            },
            help=("Which way the position profile runs. It only changes that "
                  "one chart."),
        ),
        ParamSpec(
            name="spec", type="chart_spec", default="",
            label="Your own chart: what goes where",
            # 同 `axis` 的理由（F87）：沒勾那張圖就別問這件事。
            show_when=("charts", (export_unif.CHART_CUSTOM,)),
            help=("The one chart you build yourself: which measured number "
                  "runs across the bottom, which one runs up the side, what "
                  "the colour and marker size mean - and whether it is drawn "
                  "as dots, a line or bars. Press \u201cChart\u2026\u201d "
                  "beside this row to pick them. It changes that chart only."),
        ),
        ParamSpec(
            name="boxes_csv", type="bool", default=False,
            label="Also write a table, one row per box",
            help=("A CSV with one row for every measurement box: which "
                  "region it belongs to, where it sits, which row and column "
                  "it is in, and every number measured on it. The lot's own "
                  "defects.csv has one row per defect, so it cannot show you "
                  "the boxes inside one image - this can."),
        ),
        ParamSpec(
            name="look", type="chart_style", default="",
            label="Chart look",
            help=("How the charts look: titles, axis names, tick counts, "
                  "text size and colour, marker and line width - and whether "
                  "the value scale is locked. Press “Chart settings…” "
                  "beside this row to change any of it (the chart window has "
                  "the same button). It travels with the recipe, so a "
                  "reopened recipe draws the charts you left."),
        ),
        ParamSpec(
            name="limit", type="int", default=20, min=0, max=100000,
            label="At most this many defects", min_label="All of them",
            help=("These charts are per image, so a lot of 400 defects would "
                  "write 400 sets of them. The highest scoring this many are "
                  "drawn. %s Set it to 0 for every defect - which is what you "
                  "want when the lot is one big image." % LIMIT_ZERO_HELP),
        ),
        rank_by_spec(),
    ]

    # ---- 預覽（寫出前一定先看得到會寫什麼）----------------------------------
    #: 一列一格框的那張表（F88 第一刀）。
    TABLE_NAME = "boxes.csv"
    #: 那張表的第一欄：**哪一顆**（20 顆的框混在一起而沒有它就沒有意義）。
    TABLE_ID = "defect_id"

    @classmethod
    def planned_files(cls, params: Dict[str, Any]) -> List[Dict[str, str]]:
        """按下 Run 這張卡會寫哪幾個檔（**乾跑**）。

        名字帶 ``<defect>`` 是 pattern —— 哪幾顆要跑完才知道，而那正是這張
        卡跟 Write KLARF 同一條硬規則能守到的極限：**形狀**先講出來。
        """
        try:
            p = cls.validate_params(dict(params or {}))
        except Exception:  # 預覽要容錯，壞參數 validate 會講
            p = dict(params or {})
        kinds = [k for k in parse_key_list(str(p.get("charts") or ""))
                 if k in export_unif.CHARTS]
        out: List[Dict[str, str]] = [{
            "tick": "page", "what": "the charts and the numbers on one page",
            "name": "<defect>%s" % cls.PAGE_EXT}]
        for k in kinds:
            out.append({"tick": k, "what": export_unif.CHART_LABELS[k],
                        "name": "<defect>-%s%s" % (k, cls.FIGURE_EXT)})
        # 索引頁只有**好幾顆**才寫，而「幾顆」跑完才知道 —— 所以這裡講的是
        # 條件，不是一個承諾（同上面那幾列的 `<defect>` pattern）。
        out.append({"tick": "index", "what": "an entry page, when more than "
                                             "one defect is drawn",
                    "name": cls.INDEX_NAME})
        if bool(p.get("boxes_csv")):
            out.append({"tick": "table",
                        "what": "one row per measurement box",
                        "name": cls.TABLE_NAME})
        return out

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        out = list(super().configuration_issues(params))
        # ⚠ **要看補完預設之後的值。** 直接讀 `params` 的話，一份還沒被
        # `validate_params` 走過的 dict（registry 全掃的測試、手寫 recipe 省
        # 略那一格）會讀到空字串，於是這張卡對一個**設定完全正常**的節點
        # 說「你什麼都沒勾」。第一版就是這樣寫的，`test_output_convergence`
        # 抓到 —— 那支測試存在的理由正是這種「每張卡各自寫一遍」的規則。
        kinds = [k for k in parse_key_list(str(
            params.get("charts", ",".join(export_unif.DEFAULT_CHARTS))
            if params.get("charts") is not None
            else ",".join(export_unif.DEFAULT_CHARTS)))
                 if k in export_unif.CHARTS]
        if not kinds:
            # 一張圖都沒勾 ⇒ 這張卡只會寫出四個空白頁面。講在畫布上，
            # 不要等跑完一批。
            out.append("No charts are ticked, so this card would write empty "
                       "pages. Tick at least one under “Which charts”.")
        if export_unif.CHART_CUSTOM in kinds:
            # 這是唯一一張**兩條軸都要使用者自己挑**的圖，所以它是唯一
            # 一張「勾了卻畫不出來」畫得出來的圖。講在畫布上，不要等跑完一批
            # 才發現那個檔案裡是一句「pick x and y」（同上面那條的理由）。
            try:
                need = chart_spec.missing_roles(params.get("spec", ""))
            except Exception:  # 壞掉的值 validate 會講
                need = []
            if need:
                out.append(
                    "“Your own chart” has no %s yet, so it would "
                    "be drawn empty. Press “Chart…” beside "
                    "“Your own chart: what goes where” to pick "
                    "which number goes on each side."
                    % " or ".join(need))
        return out

    # ---- 跑 ----------------------------------------------------------------
    def _style_for(self, kind: str, p: Dict[str, Any],
                   metric: str) -> Dict[str, Any]:
        """一張圖真正要用的那一份設定 —— **一格參數展開來的**（F87）。

        `chart_style.style_for` 是唯一的入口：它把全域那幾格與「這張圖自己的
        覆寫」疊起來，並把鎖定那一組換成畫圖那一側認得的 ``vlock`` / ``hlock``。

        這裡只補兩件 `chart_style` **刻意不知道**的事（它不認識任何一張圖的
        名字 —— 知道的話 `pipeline/` 就開始依賴 `export/`，而那個方向是反的）：

        * 這張圖預設叫什麼；
        * 「值那一軸」的名字要落在**哪一軸** —— 它在直方圖是 X、在 profile
          是 Y，而那是四張圖各自的事。
        """
        return export_unif.resolve_style(p.get("look", ""), kind,
                                         str(p["axis"]), metric)

    def _value_name(self, p: Dict[str, Any], metric: str = "") -> str:
        """值那一軸叫什麼（副標題與摘要表共用 —— 各寫一份的那份會漂）。"""
        got = chart_style.style_for(p.get("look", ""))
        return str(got.get("value_name") or "").strip() or str(metric)

    @classmethod
    def chart_kinds(cls, params: Dict[str, Any]) -> List[str]:
        got = parse_key_list(str(params.get("charts", "") or ""))
        return [k for k in export_unif.CHARTS if k in got]

    @classmethod
    def overlay_heat(cls, ctx: Any, params: Dict[str, Any],
                     stream: Optional[str] = None) -> Any:
        """熱圖**疊回影像上**（F87 第五刀，2026-09-07 使用者：「都按照 PEAR
        一樣」）。

        PEAR 的熱圖從來不是一張白底的獨立圖 —— 它是半透明鋪在影像上、ROI
        外框畫在熱色之上（`pear/ui/image_view.py::_paint_heat_cells`）。
        理由很直接：「不均勻在**哪裡**」這個問題的答案要對得到晶圓上的位置，
        而一張抽掉了影像的圖只剩「有一個角落比較亮」，對不回去。

        ⚠ **磚跟寫出去的 SVG 是同一支** `export.uniformity_charts.heat_tiles`
        —— 包含色階（跨區域共用）與鎖定範圍。各算一份的話，畫面上這一格的顏色
        跟報表裡的會在某一天分岔，而那一天兩張都畫得出來。

        座標正規化要影像尺寸，而 ``spread["rects"]`` 是**像素**的 —— 所以這裡
        問 ``ctx.images`` 拿那條流的大小。拿不到就整組不畫（同 `set_marks` 的
        規矩：錯位的顏色指向錯的地方，而畫面上不會說）。
        """
        notes = (getattr(ctx, "meta", None) or {}).get("glv_hist") or []
        want = str(stream or "").strip()
        mine = [n for n in notes
                if isinstance(n, dict)
                and not (want and str(n.get("stream") or "").strip()
                         and str(n.get("stream")).strip() != want)]
        if not mine:
            return [], [], None
        try:
            pp = cls.validate_params(params)
        except Exception:  # 顯示用，不能擋畫面
            return [], [], None
        if export_unif.CHART_MAP not in parse_key_list(str(pp["charts"])):
            # 沒勾熱圖就不鋪 —— 畫面上的東西要跟「會寫出去什麼」對得起來。
            return [], [], None
        series = export_unif.chart_series(mine,
                                          metric=str(pp["metric"]).strip())
        metric = str(series.get("metric") or "")
        shape = cls._stream_shape(ctx, mine, want)
        if not metric or shape is None:
            return [], [], None
        iw, ih = shape
        st = cls()._style_for(export_unif.CHART_MAP, pp, metric)
        cells, colours, span = export_unif.heat_tiles(series, st,
                                                      bounds=(iw, ih))
        if not cells:
            return [], [], None
        norm = [(x0 / iw, y0 / ih, (x1 - x0) / iw, (y1 - y0) / ih)
                for (x0, y0, x1, y1) in cells]
        return norm, colours, (span[0], span[1], cls()._value_name(pp, metric))

    @staticmethod
    def _stream_shape(ctx: Any, notes: Sequence[Any],
                      stream: str = "") -> Optional[Tuple[int, int]]:
        """那幾份 note 量在哪張影像上 → ``(寬, 高)``。拿不到就 ``None``。"""
        images = dict(getattr(ctx, "images", None) or {})
        names = [stream] if stream else []
        names += [str(n.get("stream") or "") for n in notes
                  if isinstance(n, dict)]
        for name in names:
            arr = images.get(name) if name else None
            if arr is not None and getattr(arr, "ndim", 0) >= 2:
                h, w = arr.shape[:2]
                if w > 0 and h > 0:
                    return int(w), int(h)
        return None


    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        p = self.validate_params(params)
        folder = self._folder_of(p, bctx)
        rows = list(bctx.rows)
        items = list(getattr(bctx.dataset, "items", None) or [])
        by_id = {str(getattr(it, "defect_id", "")): it for it in items}
        sources = dict(getattr(bctx.dataset, "sources", None) or {})
        kinds = [k for k in parse_key_list(str(p["charts"]))
                 if k in export_unif.CHARTS]
        if not kinds:
            raise StepError(self.key,
                            "no charts are ticked, so there is nothing to "
                            "write. Tick at least one under “Which charts”.")

        rank_by = str(p["rank_by"]).strip() or overlay.RANK_BY_SCORE
        chosen = overlay.pick_overlay_results(rows, int(p["limit"]), rank_by)
        _warn_if_unranked(self.key, bctx, rows, rank_by, int(p["limit"]))

        written = 0
        no_spread = 0
        skipped = 0
        index: List[Dict[str, Any]] = []
        # F88 第一刀：**一列一格框**的表。累加每一顆的，最後寫一份 —— 一顆
        # 一個檔的話，20 顆就是 20 份要自己接起來的 CSV。
        table: List[Dict[str, Any]] = []
        table_cols: List[str] = []
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
                notes = (getattr(ctx, "meta", None) or {}).get("glv_hist") or []
                series = export_unif.chart_series(
                    notes, metric=str(p["metric"]).strip())
            except Exception:  # 鐵則 7 的跨顆版
                skipped += 1
                continue
            feats = dict(getattr(r, "features", None) or {})
            if not series.get("groups"):
                # 這一顆量不出「這幾格之間」（走 pooled、沒勾 report、或
                # 只有一格框）。**不寫一張空頁** —— 一張畫得出來但沒有意義的
                # 圖比沒有圖糟，而下面那句 warning 會說出有幾顆這樣。
                no_spread += 1
                continue
            metric = str(series.get("metric") or "")
            # ⚠ **不要用 `overlay_filename`**（F86）：那一支加的 `overlay_`
            # 前綴是給疊圖用的，而這幾張是圖表 —— 借它等於讓檔名說一件錯的事。
            # 要的只有消毒那一半。
            stem = overlay.safe_stem(did)
            # 自己配的那一張吃的是**長表**（一列一格框），不是 series ——
            # 兩條軸是使用者自己挑的欄。⚠ 只在真的要畫的時候建：`build_frame`
            # 要走一遍所有區域的所有框，而兩個都沒勾的人不該付那個錢。
            frame = None
            if export_unif.CHART_CUSTOM in kinds or bool(p["boxes_csv"]):
                frame = export_frame.build_frame(notes)
            try:
                charts = []
                for k in kinds:
                    st = self._style_for(k, p, metric)
                    svg = export_unif.build_chart_svg(
                        series, k, st, frame=frame, spec=p.get("spec", ""))
                    charts.append({"name": export_unif.CHART_LABELS[k],
                                   "svg": svg})
                    _write_text(svg, os.path.join(
                        folder, "%s-%s%s" % (stem, k, self.FIGURE_EXT)))
                # **數字跟圖在同一頁**（F86）。那一頁本來就該是「一顆的
                # 答案」，而在這之前看圖的人得另外開 CSV 才知道 CV% 是多少。
                # ⚠ 數字是從**這一顆的 features** 拿的，不在畫圖那一側重算
                # —— 重算的那一份會漂，而 CSV 與報告頁上出現兩個 CV% 的那天，
                # 沒有人看得出哪一個是對的。
                rows = export_unif.summary_rows(series, feats)
                export_html.write_html(
                    export_boxplot.build_boxplot_page(
                        charts, "Uniformity - %s" % did,
                        subtitle="%s, one point per measurement box"
                                 % self._value_name(p, metric),
                        lead=export_unif.build_summary_html(rows),
                        extra_css=export_unif.SUMMARY_CSS),
                    os.path.join(folder, stem + self.PAGE_EXT))
                index.append({"name": did, "href": stem + self.PAGE_EXT,
                              "rows": rows})
                if bool(p["boxes_csv"]) and frame is not None:
                    for one in frame.rows:
                        # **哪一顆**要在表上 —— 20 顆的框混在一起而沒有這一
                        # 欄的話，那張表回答不了任何問題。
                        one[self.TABLE_ID] = did
                        table.append(one)
                    for c in frame.columns:
                        if c not in table_cols:
                            table_cols.append(c)
            except OSError as e:
                raise StepError(self.key, "could not write into %s: %s"
                                % (folder, e)) from e
            written += 1

        # ---- 好幾顆才寫索引頁（F86）---------------------------------------
        # ⚠ **一顆的時候不寫**：那一顆的頁面本來就是答案，多一個檔只是多一層
        # 要點進去的東西。而 20 顆的時候不寫才是問題 —— 20 個 HTML ＋ 80 個
        # SVG 躺在同一個資料夾裡，沒有入口。
        if len(index) > 1:
            try:
                export_html.write_html(
                    export_unif.build_index_page(
                        index, "Uniformity - %d defects" % len(index),
                        subtitle="click a defect to see its four charts"),
                    os.path.join(folder, self.INDEX_NAME))
            except OSError as e:
                raise StepError(self.key, "could not write into %s: %s"
                                % (folder, e)) from e

        # ---- 一列一格框的表（F88 第一刀）----------------------------------
        if bool(p["boxes_csv"]) and table:
            try:
                # ⚠ 走 `chart_frame.write_csv` 而不是 `_write_text`：
                # 這一份要跟 `defects.csv` **同一套寫法**（`utf-8-sig`），
                # 兩個檔躺在同一個資料夾裡而只有一個 Excel 開得乾淨的話，
                # 使用者沒有線索知道為什麼。
                export_frame.write_csv(
                    export_frame.Frame([self.TABLE_ID] + table_cols, table),
                    os.path.join(folder, self.TABLE_NAME))
            except OSError as e:
                raise StepError(self.key, "could not write into %s: %s"
                                % (folder, e)) from e

        bctx.add_output(folder)
        if not written:
            # **一個檔都沒寫要講**：一個空資料夾跟「這張卡沒被跑到」在畫面上
            # 長得一模一樣，而原因通常是 Gray level 那張卡還停在 pooled。
            bctx.warn(
                "Write charts: nothing was drawn. These charts need the "
                "Gray level card set to “each box” with something ticked "
                "under “How even are the boxes” - that is where the "
                "box-by-box numbers come from.")
        elif no_spread:
            bctx.warn("Write charts: %d defect(s) had no box-by-box "
                      "numbers and were skipped." % no_spread)
        if skipped:
            bctx.warn("Write charts: %d defect(s) could not be redrawn "
                      "(no image, or the pipeline did not run for them)."
                      % skipped)
