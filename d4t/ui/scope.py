# d4t Studio 產品範圍開關 — authored 2026-07-28 (F7-1).
"""Studio 支援哪些輸入型別、哪些卡片會出現在卡片庫。

**2026-08-17（F11 Input-3）：四種輸入全部打開了。** 使用者的話是「目前 d4t
可以支援 patch + 對應 KLARF，我需要他也能支援 **RSEM image + KLARF，或單純
圖片**」，而 Input 段的定位是「**整個輸入 image source 的核心**」。

| kind | 什麼樣的資料 | Studio 的入口 |
|---|---|---|
| ``ebi_patch`` | KLARF + patch TIFF（每顆連續幾頁）| ``Open KLARF…`` |
| ``rsem`` | KLARF + 每顆一個影像檔 | ``Open KLARF…``（自動判別）|
| ``tiff_stack`` | 一個多頁 TIFF、**沒有 KLARF** | ``Open stack…`` |
| ``folder`` | 一個資料夾的單張影像、沒有 KLARF | ``Open folder…`` |

後兩者沒有 KLARF → 沒有座標、**寫不回 KLARF**，而那件事在載入的當下就講
（資料集標籤上常駐 ``· no KLARF``，見 :func:`no_klarf_message`）。

這個檔案還是「產品範圍開關」的家
--------------------------------
F7-1 用它把 Studio 收斂成 patch-only（使用者當時的話是「**暫時**只支援 patch」），
而那一輪的做法是**收起來、不刪掉** —— 於是這一輪要打開時，改的是這裡的兩個常數，
`ingest` / `golden_cell` / `algo/period.py` 一行都不用動。收起來的成本是零、
回復的成本是加一個字串，那個判斷在一年後被驗證了。

⚠ ``algo/period.py`` 仍然不要刪：它的 ``estimate_period`` / ``choose_origin``
（相位搜尋）**是之後做 pattern-frame ROI 的唯一工具**
（見 ``docs/history/plans/F7-canvas-and-taxonomy.md`` §4）。2026-08-18
Golden Cell 那兩張卡刪掉之後它在 ``d4t/core`` 裡已經沒有呼叫者了 ——
那正是它最容易被當成死碼順手刪掉的時候，所以這句話留在這裡，而
``tests/test_ui_input_kinds.py::test_period_module_is_not_orphaned`` 是那張便利貼。

CLI 不受影響
------------
``python -m d4t run`` 一直吃得下每一種 kind —— 這裡只管 GUI。
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Sequence, Tuple

__all__ = [
    "SUPPORTED_KINDS", "HIDDEN_STEPS", "DEFAULT_KIND", "SHOW_SAMPLE_ENTRIES",
    "SHOW_ROUTE_BY",
    "INPUT_SOURCES", "ATTACHMENTS", "InputSource",
    "is_supported_kind", "visible_steps", "recipe_is_supported",
    "unsupported_kind_message",
]

#: Studio 接受的資料集型別（``dataset.kind``）—— 四種，見模組說明的表。
#:
#: **2026-08-17（F11 Input-3）：RSEM 與單張圖片打開了。** 使用者的話是
#: 「目前 d4t 可以支援 patch + 對應 KLARF，我需要他也能支援 **RSEM image +
#: KLARF，或單純圖片**」。四條路對應四種 source，而「一種 source 一個入口」
#: 是使用者定的分類原則 —— 見 `StudioWindow` 工具列的三顆 Open。
SUPPORTED_KINDS: Sequence[str] = ("ebi_patch", "tiff_stack", "rsem", "folder")

#: 只有在不支援的型別下才有意義、因此不列進卡片庫的 step key。
#:
#: **2026-08-17（F11 Input-3）：空了。** 這裡原本收著 ``golden_cell`` 與
#: ``cell_period``。2026-08-18 那兩張卡的下場不一樣，而這一段就是那兩種下場的
#: 對照：
#:
#: * ``cell_period`` —— **刪掉**（使用者：「不需要這功能」）。
#: * ``golden_cell`` —— 先刪，同一天要回來並**改名**成 ``pattern_ref``
#:   「Reference from pattern」（使用者：「那可能要拿回來 不過要改名字
#:   不然會誤會」），當晚收起來，**2026-08-20（F16）刪掉**（使用者：
#:   「完全沒用，請直接拿掉」）。同一張卡走完了四種下場。
#: * ``align`` —— **收起來**（使用者：「之後真需要我再回來」）。
#:
#: **三種處置，判準都是使用者說了哪一句話**，不是我覺得那張卡有沒有用。
#: 收起來＝卡片庫看不到、引擎照認、舊 recipe 照跑；刪掉＝`REGISTRY` 裡沒有，
#: 舊 recipe 開起來是一條 ``unknown-step``；改名＝要一道遷移（見
#: ``recipe._migrate_renamed_cards``，連分數表達式裡的 feature 名一起換）。
#:
#: 機制留著（一個 tuple、一個 `visible_steps()`）：下一次要暫時收起某張卡時，
#: 加一個字串就好。
#: 2026-08-18（F11 Region-1 第三輪）：**`align` 收起來了**。使用者定調
#: 「我不喜歡 align 卡，我反而認為要拿掉這功能，之後真需要我再回來。目前座標系
#: patch 的 test 跟 ref 一樣，有發現如果我拉 align 反而會飄掉 shift」。
#:
#: 那個「飄」有機制，而且是兩個（讀 `algo/align.py` 讀出來的）：
#:
#: 1. **量到的是雜訊 ＋ 缺陷偏移。** 真實位移接近 0 的時候，相關峰的位置由雜訊
#:    決定；而 test 上有缺陷、ref 沒有，缺陷會把峰往自己那邊拉 —— 每一顆的缺陷
#:    都不一樣，所以每一顆的 shift 都不一樣。
#: 2. **只有 ref 被重採樣。** 次像素位移走 `cv2.INTER_LINEAR`（`apply_alignment`），
#:    等於對 ref 過一次低通、test 沒有。`diff` 因此多一層跟缺陷無關的材質差 ——
#:    正好違反 Enhance 段那條 `uneven-treatment`（「兩張圖不再可比」），只是那支
#:    lint 管不到 align，因為它不是 Enhance 卡。
#:
#: **為什麼是收起來不是刪掉**：`tests/fixtures/recipes/dual_route_basic.json`
#: 用了 align，而它撐著三組黃金值裡的兩組。刪掉 = 那份 recipe 開不起來 = 兩組
#: 黃金值要重新定錨，而使用者說的是「之後真需要我再回來」。`HIDDEN_STEPS` 只過濾
#: **卡片庫**：已經在用它的 recipe 照跑、CLI 照跑、黃金值一個字不動。
#: 要回復就是把這個字串拿掉（F7-1 驗證過的那個判斷）。
#:
#: 2026-08-18（F11 Region-5 收尾）：`pattern_ref` 先收起來 ——
#: **2026-08-20（F16）刪掉了**（使用者：「Compare 中 pattern_ref 這項功能完全
#: 沒用，請直接拿掉」）。所以它已經不在這個 tuple 裡。
#:
#: 那一輪把「收起來」與「刪掉」的**價差**真的付了一次，值得留著當參考：
#: 收起來的時候，代價是一個字串；刪掉的時候，`dual_route_basic.json` 的 rsem
#: route 必須重做（它靠那張卡造 ref 才有 diff 可量），一組黃金值重新定錨，
#: 而那條 route 的 24/24 **變成每一顆都判 bin 0**（實測 seed 11/3/21 皆 12/24，
#: 而那 12 正好是沒有缺陷的那 12 顆）。詳見 `tests/test_e2e_dual_route.py`。
#:
#: 所以「不確定的時候先收起來」那句話沒有被推翻 —— 這一次是使用者確定了。
#:
#: ⚠ `feature_math` / `feature_fill` **2026-08-27 刪掉了**（Phase 3，使用者：
#: 「功能已經被 `decide.let` 取代了，刪掉」）。它們 2026-08-24 先收在這裡，
#: 走完了 `CLAUDE.md` §5 那張對照表的「不確定就先收起來，使用者確定之後再刪」
#: —— **這是那條規矩第一次跑完全程**。舊 recipe 用到它們的話開起來是一條
#: `unknown-step`（那就是刪掉要付的錢），沒有遷移：那兩張卡的功能在判定的
#: working numbers 裡，而算式怎麼搬進去是使用者的決定，不是一道機械遷移。
HIDDEN_STEPS: Sequence[str] = ("align",)

#: 沒有資料集時 ``RecipeModel`` 用的 route 名稱。
DEFAULT_KIND: str = SUPPORTED_KINDS[0]

#: 「範例 recipe」的兩個入口要不要出現在畫面上：工具列的 ``Templates…``、
#: 導覽與空白狀態上的「用範例資料試一次」。
#:
#: 2026-08-16：使用者定調「範例 recipe 都先全部拿掉」，``examples/`` 整個移除
#: （原本五份在 39b9fea 就因為依賴被拿掉的卡片而刪了，剩下的一份也不留）。
#: 沒有 recipe 可以載，這兩個入口就是**按了會撞牆的東西**：範本庫開起來是空的，
#: 「用範例資料試一次」產得出資料卻載不到 pipeline。對不會寫 code 的目標使用者，
#: 那比沒有這顆鈕更糟（推廣鐵則）—— 所以連入口一起收起來。
#:
#: 收起來的是**入口，不是能力**：``StudioWindow.run_demo()`` /
#: ``generate_demo_lot()`` / :class:`~d4t.ui.welcome.RecipeLibraryDialog`
#: 一行都沒動，測試照樣直接呼叫得到。範例 recipe 庫回來的那一天，
#: 把這個常數改成 ``True`` 就整組回來 —— 跟 ``SUPPORTED_KINDS`` 同一套辦法。
SHOW_SAMPLE_ENTRIES: bool = False

#: `route_by`（「分流／pre-filter」）的畫布徽章與編輯器入口要不要出現。
#:
#: 2026-08-28（F50）：使用者要把「只跑某幾個 code」做進 Input 卡，並問能不能
#: 順便拿掉 pre-filter。**收起來而不是刪掉，因為那兩件事不是同一件**：
#:
#: * `route_by`：不同的 code 走**不同的卡片組**（全部都跑，走不同路）；
#: * Input 的篩選：**只有指定 code 的才跑**，其他的根本不進來。
#:
#: 新的蓋不掉舊的。而「不同的 Classnumber 走不同的卡片」是使用者
#: 2026-08-24 自己定調的需求（`SESSION_LOG.md` F23 那一段）—— `CLAUDE.md`
#: §5 那張表因此適用：**不確定的時候先收起來**，成本是一個字串。
#:
#: 收起來的是**入口，不是能力**：`recipe.route_by`、`resolve_route`、
#: `route_taken` 特徵、三條 route lint、`ui/route_panel.py` 與
#: `ui/route_badge.py` 一行都沒動 —— 帶著 `route_by` 的 recipe 照樣跑得出
#: 一模一樣的數字（黃金值不動），CLI 照樣認。改回 ``True`` 就整組回來。
SHOW_ROUTE_BY: bool = False


class InputSource(NamedTuple):
    """一個「資料從這裡進來」的入口。

    **一種 source 一個入口，而入口這件事只寫在這一張表上**（2026-08-18，
    使用者：「Input 部分 各種 image source 資料流 是否改成個別入口比較好
    （但同時 UI 一開始進去的地方顯示也要改）」）。

    在這張表出現之前，同一組入口被抄在三個地方：工具列三顆鈕的 tooltip、
    空白狀態上的那一句話、導覽對話框上的那顆鈕。三份會漂 —— 而且已經漂了：
    工具列有三顆 Open，空白狀態只講 KLARF（「Open a KLARF to see your patches
    here.」），於是**帶著一個資料夾的圖片進來的人，在最大的那一塊畫面上找不到
    自己那條路**。第四種（GLAS 匯出）更慘：卡片庫裡有一張 `Load layout labels`，
    而它的入口那一顆鈕根本沒被 `addWidget` 到工具列上（見
    `test_every_button_built_for_the_toolbar_is_actually_on_it`）。

    欄位：

    * ``key``    —— ``StudioWindow`` 上那顆鈕與那個 handler 的名字後綴。
    * ``kinds``  —— 這條路產得出來的 ``dataset.kind``（可能不只一種：一份 KLARF
      是 patch 還是一顆一張，**由檔案本身決定**，不該反過來問使用者）。
    * ``title``  —— 完整的一句（空白狀態上那一列用它）。
    * ``short``  —— 工具列上那顆鈕的字（省略重複的動詞；空的話退回 ``title``）。
    * ``what``   —— 一句白話：**這條路吃的是什麼樣的檔案**。
    * ``icon``   —— 自繪圖示的名字（`widgets.GLYPH_ICONS`）。
    * ``has_klarf`` —— 進來之後寫不寫得回 KLARF。空白狀態上直接寫出來，
      不是等使用者跑完一整批、打開 Export 才發現。
    """

    key: str
    kinds: Tuple[str, ...]
    title: str
    what: str
    icon: str
    has_klarf: bool
    #: 工具列上那顆鈕的字（F13-2）。**同一張表，兩種呈現**：空白狀態要講完整
    #: 的一句（那是使用者第一次找路的地方），工具列只要一個名詞 —— 五顆
    #: 「Open …」排在一起，重複的那個動詞佔掉的寬度比它給的資訊多。
    short: str = ""


#: Studio 的四種資料入口（順序就是畫面上的順序）。
#:
#: KLARF 那一條服務兩種 kind，而那**不是**「一個入口服務兩種 source」的例外：
#: patch 與一顆一張的差別寫在 KLARF 裡（`Images N { … }`），ingest 判得出來。
#: 拆成兩顆鈕等於要使用者回答一個檔案已經回答了的問題，而答錯就是一個錯誤訊息。
INPUT_SOURCES: Tuple[InputSource, ...] = (
    InputSource(
        key="klarf", kinds=("ebi_patch", "rsem"), title="Open KLARF…",
        short="KLARF…",
        what=("A KLARF and its images - either a patch TIFF with several "
              "pages per defect, or one image file per defect. Which one it "
              "is comes from the KLARF, you do not have to say."),
        icon="folder", has_klarf=True),
    InputSource(
        key="stack", kinds=("tiff_stack",), title="Open stack…",
        short="Stack…",
        what=("One multi-page TIFF and nothing else - you say how many pages "
              "there are per defect, and every group of that many becomes "
              "one defect."),
        icon="stack", has_klarf=False),
    InputSource(
        key="folder", kinds=("folder",), title="Open folder…",
        short="Folder…",
        what="A folder of single images: every image file becomes one defect.",
        icon="folder_open", has_klarf=False),
)


class Attachment(NamedTuple):
    """掛在**已經載好的** lot 上的附加檔（不是第五種 source）。"""

    key: str
    title: str
    what: str
    icon: str
    needs: str
    #: 工具列上那顆鈕的字（同 :class:`InputSource`）。
    short: str = ""


#: 附加檔的入口。第一個（也目前唯一的）是 GLAS 的 GDS 匯出。
#:
#: 它跟上面那三個分開，因為它回答的是不同的問題：三個 Open 是「這批資料在哪」，
#: 這一個是「這批資料**還有一份別的程式產的東西**」。合在一起的話，沒有 lot
#: 的時候它是一顆按了沒有意義的鈕。
ATTACHMENTS: Tuple[Attachment, ...] = (
    Attachment(
        key="gds", title="Open GDS export…",
        what=("Layout labels that GLAS exported for this lot: every defect "
              "gets a label map, and the “ROI” card turns each layer "
              "into a named region."),
        # **這一顆不縮寫**：它的名字被三張卡的訊息逐字引用（「Use “Open GDS
        # export…”」），而那條不變量要求引號裡的字跟畫面上的鈕**一字不差**
        # （`test_ui_f7_9_feedback`）。縮寫它等於讓那三句話指向一顆不存在的鈕。
        icon="layers", needs="Load the lot first."),
)


def is_supported_kind(kind: Any) -> bool:
    """這個 ``dataset.kind`` 目前的 Studio 吃不吃得下。"""
    return str(kind or "") in SUPPORTED_KINDS


def visible_steps(steps: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """過掉卡片庫不該顯示的卡（吃 ``Step.describe()`` 的 dict 清單）。"""
    return [d for d in (steps or [])
            if str(d.get("key", "")) not in HIDDEN_STEPS]


def recipe_is_supported(info: Dict[str, Any]) -> bool:
    """範本庫要不要列出這份 recipe。

    判準是「**它至少有一條看得懂的 route**」，不是「它只有看得懂的 route」——
    一份同時定義 ebi_patch 與 rsem 的 recipe，載進來之後
    ``RecipeModel.from_recipe`` 會挑 ``sorted(routes)[0]``（= ebi_patch），
    完全跑得動，沒有理由把它藏起來。只有純 rsem 的才會被濾掉。
    """
    routes = [str(r) for r in (info or {}).get("routes") or ()]
    if not routes:
        return True          # 讀壞的檔案交給對話框顯示紅字，不在這裡吃掉
    return any(is_supported_kind(r) for r in routes)


def unsupported_kind_message(kind: Any) -> str:
    """載到不支援的資料集時，狀態列要說的話（白話 + 講得出替代路徑）。"""
    return ("d4t Studio does not know this kind of input: “%s”. It reads "
            "KLARF datasets (patch pairs or one image per defect), multi-page "
            "image stacks, and folders of single images. The command line can "
            "still run it: python -m d4t run <recipe> <data>."
            % (kind or "unknown"))


def no_klarf_message(kind: Any) -> str:
    """資料集沒有 KLARF 時，載入當下就要講的那一句（F11 Input-2）。

    為什麼要在**載入**時講：沒有 KLARF 就沒有 defect 清單、沒有座標，
    **寫不回 KLARF**。Export 精靈本來就會把那個選項變灰（它看 ``dataset.klarf``），
    但那是使用者跑完一整批、打開輸出精靈才會看到的事 —— 太晚了。
    """
    return ("no KLARF with this data (%s), so the ADC verdict cannot be "
            "written back to a KLARF - CSV and Excel reports still work."
            % (kind or "image stack"))
