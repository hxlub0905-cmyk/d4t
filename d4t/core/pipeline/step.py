# d4t pipeline contract — authored 2026-07-27 (M1).
"""Step 介面 + ParamSpec + registry。

一張「卡片」= 一個 Step 子類別：
- 宣告 ``params``（每個參數都要有白話 ``help`` 與合理 ``default`` —— 推廣鐵則）
- 宣告 reads / writes（影像流 key）與 features_out（會產出的特徵名）
- 實作 ``run(ctx, params)``（純函數風格：吃 Context、回 Context）

新算法 = 新 class + ``@register_step``，UI 與引擎零修改。

分類（見 master plan §5）—— **這張卡吐什麼型別**：
- ``CATEGORY_IMAGE``  影像段（把圖變乾淨；寫 images）
- ``CATEGORY_ALGO``   算法段（從圖量出數字；寫 features）
- ``CATEGORY_ADC``    判定段（score / bin）
- ``CATEGORY_BATCH``  整批那一層（跑完全部才跑一次；F17-③）

⚠ **``category`` 不再決定快取邊界**（F17-③，2026-08-20）。以前 checkpoint 問的
是 ``category == CATEGORY_IMAGE``，於是它被當成**定位手段**用：五張 Output 卡
的 category 曾經是 ``CATEGORY_ADC``，而它們跟 ADC 毫無關係 —— 填那個值只是為了
落在 checkpoint 之後。現在快取邊界由 ``resolve_writes``（會不會吐影像流）推導
（`engine._writes_an_image`），category 只剩它字面上的意思。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type

from .context import Context
from .cellrois import CellRoiError, format_cell_rois, parse_cell_rois
from .channels import ChannelMapError, format_channel_map, parse_channel_map
from .curve import CurveError, format_curve, parse_curve

CATEGORY_IMAGE = "image"
CATEGORY_ALGO = "algo"
CATEGORY_ADC = "adc"
#: 一張卡跑的**尺度**（F17-④）：一顆一次，還是整批一次。
#:
#: 以前這件事是一個布林 ``is_batch``，而布林答不出「還有第三種嗎」。宣告成尺度
#: 之後，「一顆」與「整批」是**同一個模型的兩層**：兩層都是同一份 recipe 的
#: DAG，都用同一支 `execution_order` 排序，差別只在餵進去的是一顆 defect 還是
#: 整批的結果表。
#:
#: ⚠ **「試跑不寫」不能因為統一而消失**（使用者 2026-08-20 定調）。統一的是
#: **宣告**，不是**入口**：`run_batch` 只跑、`run_batch_steps` 才寫，而試跑那
#: 條路根本不叫後者。旗標遲早有人忘記關，兩支函式不會。
SCALE_DEFECT = "defect"
SCALE_LOT = "lot"
_SCALES = (SCALE_DEFECT, SCALE_LOT)

#: 整批那一層（F17-③）：跑完全部 defect 之後才跑一次的卡（Output 段那五張）。
#: 它們以前借用 ``CATEGORY_ADC`` —— 不是因為它們在做 ADC，而是因為那個值剛好
#: 讓它們落在快取 checkpoint 之後。現在那件事由宣告推導，這個值可以講實話了。
CATEGORY_BATCH = "batch"

#: 資料型別（route 的 kind）按「一顆 defect 拿到什麼」分兩群（PR-2）：
#: patch 形＝機台以 defect 為中心裁切的小圖（`_center` 有幾何意義）；
#: 單張形＝一顆一張大圖，缺陷可能在任何位置。`Step.kind_issues` 的判準用
#: 這兩張表。⚠ 跟 `ui/scope.py` 的 `SUPPORTED_KINDS` 要合起來剛好蓋滿 ——
#: core 不能 import ui，所以由一條 UI 測試 cross-check（第五種 kind 出現時
#: 兩邊一起紅，而不是安靜地漏掉分群）。
PATCH_KINDS = ("ebi_patch", "tiff_stack")
SINGLE_IMAGE_KINDS = ("rsem", "folder")

# --------------------------------------------------------------------------- #
# 流程階段（F7-3）—— 卡片庫的分組依據
# --------------------------------------------------------------------------- #
#: ``category`` 分的是「這張卡吐什麼型別」（引擎用：快取切點、驗證順序）；
#: ``group`` 分的是「這張卡在解決什麼問題」（**使用者用**：卡片庫的分組）。
#:
#: 兩者是**獨立**的軸。舊 UI 直接拿 category 當分類，於是使用者看到的是
#: 「影像／算法」—— 那描述的是輸出型別，不是意圖，所以被評為「太武斷」。
#:
#: 每一段的規則是機械可判定的（吃什麼、吐什麼），新卡片放哪不需要討論：
#:
#: =============  =========================  ==============================
#: group          規則                       例
#: =============  =========================  ==============================
#: input          （固定頭節點）              load_patch
#: enhance        影像 → 影像                normalize / gamma / denoise
#: region         找出「要看哪裡」            roi_cross / roi_template
#: measure        影像＋區域 → 數字           glv_stats / cd_measure
#: algo           **數字 → 數字**（不碰影像）  （留給外掛；repo 裡零張卡）
#: compare        影像＋影像 → 影像           align / subtract
#: adc            數字 → score → bin         （固定尾節點）
#: output         （固定尾節點，什麼都不吐）   output_csv / output_klarf
#: =============  =========================  ==============================
#:
#: **型別規則是預設的裁決方式，但不是唯一的。** ``snr_map`` 是影像進影像出，
#: 照型別會落在 enhance —— 但它答的是「哪裡突出」，而且它必須跑在 Compare
#: 之後，放在讀起來排第二的 Enhance 裡永遠用不到。所以規則補一條：
#: **一張卡如果只為了餵另一段而存在，就跟著那一段走。**
GROUP_INPUT = "input"
GROUP_ENHANCE = "enhance"
GROUP_REGION = "region"
GROUP_COMPARE = "compare"
GROUP_MEASURE = "measure"
#: ⚠ 字串跟 :data:`CATEGORY_ALGO` 一模一樣，**但它們是兩個不同的軸**
#: （見這一段開頭）：``CATEGORY_ALGO`` 說的是「這張卡吐數字」——
#: 每一張量測卡都是 ``CATEGORY_ALGO``，而它們的 ``group`` 是 ``measure``。
#: ``GROUP_ALGO`` 說的是「這張卡**只**吃數字、不碰影像」（F16，使用者定調：
#: 「measure 是量出數值來，Algo 是拿這些 feature 去做更 custom 的處理」）。
#:
#: ⚠ **這一段已解散**（F24 §5，使用者 2026-08-24 點頭）：算式住進判定的
#: working numbers（`decide.let`）、補值變成那一行的「missing ⇒」屬性、
#: 跨顆換算變成「跟整批比」（`Let.scale`）—— 三件事都比一張卡更靠近它們
#: 服務的判定。這個常數留著給外掛卡相容（`resolve_group` 照認），但它不在
#: :data:`GROUP_ORDER` 裡：卡片庫與 rail 上沒有這一段。
GROUP_ALGO = "algo"
GROUP_ADC = "adc"
#: 這一段的卡是 **end point**：不吐影像流、不吐特徵，只把東西寫出去。
#: 同樣有測試守著（``resolve_writes()`` 與 ``resolve_features()`` 都是空的）。
GROUP_OUTPUT = "output"

#: 卡片庫的顯示順序（讀起來是一句話：
#: Input → Enhance → ROI → Measure → Compare → ADC → Output）。
#:
#: **七段**（F24 §5，2026-08-24）：F16 定的八段少了 Algo —— 那一段解散進
#: 判定（見 :data:`GROUP_ALGO` 的說明），而「段落是使用者 2026-08-20 定的、
#: 動之前要再點一次頭」那條規矩履行過了（使用者：「那三件事接著做」）。
#:
#: **這個順序不決定執行順序。** 執行是 :func:`recipe.execution_order` 的 DAG
#: 拓撲排序 —— 線怎麼拉就怎麼跑。這裡排的是**卡片庫的分區順序**（連帶 rail 的
#: 上下順序與階段顏色），所以「Compare 排在 Measure 後面」不代表 ``diff`` 會
#: 晚一步產生：那件事由線保證。
#:
#: ⚠ 這份順序在 UI 有第二份：``ui/widgets.py`` 的 ``LibraryPanel.GROUPS``
#: （它多帶標題與副標）。兩份要一致，``tests/test_ui_f16_stages.py`` 鎖著。
GROUP_ORDER = (GROUP_INPUT, GROUP_ENHANCE, GROUP_REGION, GROUP_MEASURE,
               GROUP_COMPARE, GROUP_ADC, GROUP_OUTPUT)
_GROUPS = GROUP_ORDER
_CATEGORIES = (CATEGORY_IMAGE, CATEGORY_ALGO, CATEGORY_ADC, CATEGORY_BATCH)

#: ``curve`` 是一個「值是控制點字串」的參數（見 ``pipeline/curve.py``）——
#: 跟 ``image_key`` 一樣，型別上就是 str，但 UI 認得它、會給專用編輯器。
#:
#: ``image_keys``（F7-9）是「一串影像流名」，值仍然是逗號分隔字串 ——
#: **recipe JSON 的格式沒有變**，舊檔照樣讀得進來。差別在 UI：它拿到的是
#: 上游每一條流的一個勾選框，而不是一個要自己打字、打錯只會靜靜警告的輸入框。
#: ``template``（F7-13）是一個「值是一整份資料、不是一句話」的參數 ——
#: 型別上仍是 str，但那個字串有六千多個字元，而且**沒有人能用打的**。
#: 一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。
#: UI 認得這個型別：它給的是「建一個」的按鈕加一行摘要，欄位本身唯讀。
#: ``metric_chips``（F18）是 ``multi_choice`` 的第二種長相，**值的格式一字
#: 不差**（逗號分隔的 id）—— 差別只在 UI：勾選網格換成分群的膠囊，每一顆帶
#: 一個「這個統計量在分布上是哪一段」的小圖。分群與短標籤住在 UI
#: （``widgets.METRIC_GROUPS``），卡片這邊只宣告 ``choices``：
#: **引擎說有哪些，UI 說長什麼樣。**
#: ``"expr"``（F21-B）：值是一個**吃特徵名的算式**（字串）。
#: 儲存格式跟 ``"str"`` 一字不差 —— recipe JSON 完全不變，**差別只在 UI**：
#: 它會配一支「插入數字 ▾」，列出這張卡**之前**算得出來的每一個數字、
#: 各是誰算的。跟 ``image_keys`` 是同一個先例（值的格式一樣，但 UI 認得
#: 它是什麼）。
#:
#: 為什麼要它：F21 實測，第一次真的用 `feature_math` 的時候，**最痛的不是
#: 看不出數字從哪來，是不知道有哪些數字可以用** —— 得跑 Python 呼叫
#: ``resolve_features()`` 才知道 ``cmp_delta_median`` 存在。而目標使用者
#: 不會寫 code（推廣鐵則）。
#: ``"feature_keys"``（F21-B）：值是**一串特徵名**（逗號分隔的字串）。
#: 跟 ``"expr"`` 是同一個家族 —— 儲存格式就是 ``"str"``，而 UI 認得它，
#: 所以那一格配得出同一支「插入數字 ▾」（差別只在插進去的方式：算式插在游標
#: 位置，清單接在後面）。
#: ``metric_choice``（F32）是 ``metric_chips`` 的**單選**長相：值是一個
#: 統計量 id（``glv_median``、手寫的 ``glv_q37`` 也合法 —— 跟 metric_chips
#: 同一條規矩，清單只是「常用的那幾個」，認不認得由卡片的 run() 用它自己的
#: 話說）。儲存格式就是一個字串，差別只在 UI：一排單選的膠囊，
#: 「+ Percentile…」照樣長得出自訂值。
#: ``"feature_key"``（F37）：值是**一個**特徵名（``feature_keys`` 的單數）。
#: 儲存格式一樣是 ``"str"``，加它的理由是**改名遷移**：特徵名住在幾種地方
#: （分數表達式、判定樹、以及 Output 卡的 ``rank_by`` / ``columns`` /
#: ``size_feature`` 這種參數值；`feature_math` 的算式曾經是第三種，那張卡
#: 2026-08-27 刪了），而最後那一種以前沒有人改寫 —— 因為那一格從型別上看
#: 就是一個普通字串，
#: 遷移認不出它裝著一個特徵名。
#:
#: **宣告式的標記，不是一張卡片清單**：加到 :data:`FEATURE_TYPES` 之後，
#: 遷移走的是「每一個 spec 的型別」，所以第五張會用到特徵名的卡不必回來補登記。
#: 抄一張清單的話，漏掉的那一張症狀是「改名之後那張卡指著一個不存在的數字」
#: —— 而它跑得完（Output 卡找不到那個數字就安靜地退回檔案順序）。
PARAM_TYPES = ("int", "float", "bool", "str", "expr",
               "feature_key", "feature_keys",
               "choice", "image_key",
               "image_keys", "curve", "template", "multi_choice",
               "metric_chips", "metric_choice", "channel_map", "cell_rois",
               "region_key", "region_keys", "icon_choice")

#: ``ParamSpec.choices_from`` 認得的鍵：**執行期才知道的選單**（F15-2）。
#:
#: 每一個鍵是「一句 UI 去問得到答案的問題」，而答案跟著現在載了什麼資料變：
#:
#: * ``sources``          —— 現在掛了哪幾份第二 source（代號）
#: * ``source_images``    —— 那一份的一顆 defect 有哪幾張圖
#: * ``source_columns``   —— 那一份的 KLARF 有哪些欄
#: * ``main_columns``     —— **主資料集**的 KLARF 有哪些欄（F16 的 ``carry``）
#:
#: 清單列在 core 而不是 UI，理由跟 `ParamSpec.direction` 一樣：卡片作者打錯
#: 一個鍵的話，那一格會安靜地退化成文字框（看起來只是「這個功能沒做」）。
#: 列在這裡就變成註冊時就擋下來。**UI 認不認得是另一回事**：認不得的鍵一樣
#: 退化成文字框，那是相容行為，不是錯誤。
RUNTIME_CHOICES = ("sources", "source_images", "source_columns",
                   "main_columns")

#: 值是**影像流名**的型別（畫布上的圓埠 + 實線）。
IMAGE_TYPES = ("image_key", "image_keys")

#: 值是**具名區域名**的型別（畫布上的菱形埠 + 虛線；F12）。
#:
#: 兩組分開列，因為畫布上它們是**兩種接不到彼此的東西**：把一條影像線拉進
#: 區域埠，那一格會變成一個沒有人定義的區域名 —— 跑起來是 `unknown-region`，
#: 而畫面上那條線看起來完全正常。
REGION_TYPES = ("region_key", "region_keys")

#: 值裡面裝著**特徵名**的型別（F37）。改名遷移照這一份走。
#:
#: 三種裝法不一樣，所以改寫的方式也不一樣（見
#: `recipe._rename_in_node_params`）：``expr`` 是一條算式（換整個識別字）、
#: ``feature_keys`` 是逗號清單（逐項換）、``feature_key`` 是單獨一個名字
#: （整格比對）。**列在 core 而不是遷移那一支**，理由跟 :data:`IMAGE_TYPES`
#: 一樣：這是「這個型別是什麼」的事實，而遷移只是它的一個消費者。
FEATURE_TYPES = ("expr", "feature_key", "feature_keys")

#: 輸出流的名字可以用哪些字（F10-7）。
#:
#: 這不是潔癖：流名會變成**特徵的前綴**（一張量測卡接兩條流就吐
#: ``diff_glv_max`` / ``test_glv_max``），而特徵名是**分數表達式的變數名**。
#: 取成 ``my stream`` 的話，那個特徵在表達式裡永遠指不到 —— 而使用者要到寫
#: 分數的時候才會發現，那時候他已經不記得問題出在三張卡以前的一個命名。
#: 所以擋在打字的當下（鐵則 4：壞值不准跑到演算法裡）。
STREAM_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"



def cls_name(obj: Any) -> str:
    """給錯誤訊息用的卡片名（有 ``key`` 就用它，那是使用者看得到的字）。"""
    return str(getattr(obj, "key", None) or type(obj).__name__)


class ParamError(ValueError):
    """參數不合法（含參數名與原因，UI 直接顯示）。"""


class StepError(RuntimeError):
    """步驟執行失敗；engine 會攔截並記入該 defect 的結果，不會殺整批。"""

    def __init__(self, step_key: str, msg: str):
        super().__init__(f"[{step_key}] {msg}")
        self.step_key = step_key
        #: 訊息**不含** ``[key]`` 前綴的那一份。
        #:
        #: 一張卡在自己內部攔到另一段的 :class:`StepError` 再往外報的時候
        #: （`output_report` 那六樣各自寫、各自失敗），拿 ``str(e)`` 會把前綴
        #: 疊第二次。而那句話是給使用者看的（推廣鐵則），不是給 log 看的。
        self.detail = msg


def show_when_conditions(show_when: Any) -> List[Tuple[str, Tuple[Any, ...]]]:
    """``show_when`` → 一串 ``(參數名, 允許的值)``，**全部成立才顯示**。

    兩種寫法，因為多數卡片只需要一條：

    * 一條 —— ``("method", ("percentile",))``
    * 好幾條 —— ``(("method", ("profile",)), ("directions", ("both", "flat")))``

    第二種是 F30 加的，而它是被**逼**出來的而不是想出來的：四張 Region 卡收成
    一張之後，``vertical_width`` 那幾格同時屬於「``method`` 是 profile」與
    「``directions`` 含直的」兩個條件。少了 and 的話只剩兩條路 —— 把條件揉進
    卡片自己的程式碼（於是 UI 與引擎各有一份「這一格算不算數」），或者不合併。
    """
    if not show_when:
        return []
    # ``("method", ("a", "b"))`` 的第一格是字串；多條的第一格是一個 tuple。
    if isinstance(show_when[0], str):
        return [(str(show_when[0]), tuple(show_when[1]))]
    return [(str(name), tuple(values)) for name, values in show_when]


def param_visible(show_when: Any, params: Optional[Dict[str, Any]]) -> bool:
    """這一列在這組參數下算不算數 —— **UI 與引擎共用的那一份規則**。

    ⚠ 住在 core 而不是 `ui/widgets.py`：`ParamForm` 拿到的是**序列化過的
    dict**（不是 ParamSpec），所以它以前自己又寫了一次同樣的判斷。兩份就會漂，
    而漂掉的症狀是「設定區看得到某一格，但引擎當它不存在」—— 使用者填了一個
    完全沒有作用的值，而畫面上不會說。
    """
    values = params or {}
    for name, allowed in show_when_conditions(show_when):
        want = {str(v) for v in allowed}
        got = str(values.get(name, ""))
        # **成員比對，不是整串相等**（F37）。多選那幾個型別
        # （`multi_choice` / `metric_chips` / `image_keys` / `region_keys`）
        # 的值是一個逗號清單，而「勾了 pictures 才顯示這一格」問的是
        # **在不在裡面**。整串比對的話 ``"report,pictures"`` 不等於
        # ``"pictures"``，那一格就永遠不出現 —— 而它會有一個預設值照樣生效，
        # 也就是一個使用者看不到卻在作用的設定。
        #
        # 對單值型別（`choice` / `icon_choice` / `bool`）**逐位元組等價**：
        # 沒有逗號的字串切出來就是它自己。2026-08-26 稽核過 registry 裡每一個
        # `show_when`，目標全部是單值型別。
        if not ({tok.strip() for tok in got.split(",")} & want):
            return False
    return True



@dataclass
class ParamSpec:
    """一個參數的完整描述 —— UI 表單由此自動生成。

    ``help`` 必填：一行白話說明（不會寫 code 的人要能看懂）。
    ``type=="choice"`` 需附 ``choices``；``type=="image_key"`` 表示值是影像流名稱，
    UI 會提供下拉（目前 pipeline 上游的 writes 聯集）。

    ``label``（F7-9，選填）是**顯示名**。``name`` 是 recipe JSON 的鍵，改不得；
    但 ``also_apply`` 這種名字對製程工程師來說不是一句話。有 label 就顯示 label，
    沒有就顯示 name —— 既有卡片一張都不用動。
    """

    name: str
    type: str
    default: Any
    help: str
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[str]] = None
    #: ``icon_choice`` 專用：每一個 choice 配一個圖示名（一一對應）。
    #:
    #: 為什麼要一個新型別而不是「choice 加一個旗標」（F11 Region-2）：
    #: 使用者的話是「我不希望 profile 設定頁面那麼多**文字**，能用圖就用圖」。
    #: 而 ``place`` 的五個選項是 ``crossing`` / ``beside_vertical`` /
    #: ``between_horizontal`` … —— 那五個英文詞講的是**五個畫得出來的形狀**，
    #: 用一排小圖就答完了，下拉選單則要求使用者先把詞翻譯成圖再選。
    #:
    #: **只有「不看資料就畫得出來」的選項適用。** ``vertical_select``（最亮的
    #: 那一組是哪一組）看的是這張影像，畫不出通用的圖示 —— 那種要畫在影像上，
    #: 不是畫在按鈕上。
    #:
    #: 圖示名要在 ``ui.widgets.GLYPH_ICONS`` 裡（``core`` 不 import Qt，所以那條
    #: 檢查在 UI 那一側的測試，見 `test_card_invariants`）。
    icons: Optional[List[str]] = None
    #: ``icon_choice`` 專用：每一個 choice 一句 tooltip。圖示看得懂形狀，
    #: 但「為什麼要選它」還是要有地方講 —— 只是那個地方不該佔畫面。
    choice_help: Optional[Dict[str, str]] = None
    unit: str = ""
    label: str = ""
    #: 文字參數的合法格式（正規表達式）。填了就在 ``validate_params`` 擋下來，
    #: 而不是讓壞值跑到演算法裡（鐵則 4）。用在「這個字會變成特徵名的一部分」
    #: 這種地方 —— 打了空白或減號，分數表達式就再也指不到那個特徵。
    pattern: Optional[str] = None
    #: ``pattern`` 不合時給使用者看的白話說明（不要讓他看到正規表達式）。
    pattern_help: str = ""
    #: 只有在另一個參數等於某幾個值時才顯示這一列（F7-20）。
    #: 形如 ``("method", ("percentile", "glv_band"))``。
    #:
    #: 為什麼需要：把四張 Normalize 卡併成一張之後，那張卡有十個參數，
    #: 而任何一個方法只用得到其中兩三個。全部攤出來的話，使用者要自己判斷
    #: 「我選了 CLAHE，那 p_low 還算不算數」—— 而那正是**看得懂**與**看不懂**
    #: 的分界。以前的替代方案是在 help 裡寫「（stripe 方法用不到）」
    #: （見 ``flatten`` 的 ``size``），那是一句道歉，不是一個設計。
    #:
    #: ⚠ 這是**顯示**規則，不是驗證規則：藏起來的參數照樣有預設值、照樣
    #: 通過 ``validate_params``。卡片自己要保證用不到的參數不影響結果
    #: （``resolve_reads`` 也一樣 —— 不要回報一條只有別的方法才讀的流）。
    show_when: Optional[tuple] = None
    #: 這一列屬於哪一個小標題（F8 第三輪）。同一個 section 的參數會被畫在
    #: 一起、上面加一行標題；空字串 = 不屬於任何一組（畫在最前面）。
    #:
    #: 為什麼需要：``roi_cross`` 有 19 個參數，攤成一排的時候使用者的回饋是
    #: 「有些我不知道是什麼功能，也不知道怎麼調」。這些參數其實**回答三個不同
    #: 的問題**（直的條紋在哪、橫的條紋在哪、框放在交會處的哪裡），而攤平的
    #: 清單把那個結構整個藏起來 —— 於是每一列看起來都同等重要、同等神秘。
    #: ``show_when`` 解的是「這一列現在算不算數」，這個解的是「這一列在回答
    #: 哪個問題」，兩者不能互相取代。
    section: str = ""
    #: 這個影像流參數是**接進來的**還是**吐出去的**（F10）。
    #: ``image_key`` / ``image_keys`` 的參數**必填**，其他型別留空。
    #:
    #: 為什麼要一個欄位：``subtract`` 的 ``a`` / ``b``（吃進來的兩條流）與
    #: ``out``（吐出去的那條）**型別一模一樣**，所以在這個欄位出現之前，
    #: 沒有任何人分得出「這一格是一個輸入埠」還是「這一格是輸出流的名字」。
    #: 分不出來的後果是畫布只能猜，而它猜錯的方式是**畫出一顆還沒有來源的
    #: 輸出埠** —— 使用者剛加一張卡，後面就憑空長出一條 ``diff``。
    #:
    #: 用**必填**而不是推導（例如「值有出現在 resolve_reads 裡就算輸入」），
    #: 理由跟 F9 那兩次踩到的一樣：推導看的是**值**，而值是會被清空的
    #: （新卡的輸入本來就該是空的）—— 一清空就推不回來了。宣告看的是**事實**，
    #: 跟值無關。沒宣告的卡直接註冊失敗，所以之後加的每一張卡都躲不掉。
    direction: str = ""
    #: 這一列預設收起來，按「Show advanced settings」才出現（F8 第六輪）。
    #:
    #: 跟 ``section`` 的差別是**軸不一樣**：``section`` 講「這一列在回答哪個
    #: 問題」，這個講「**要不要現在回答**」。判準是一句話 —— 這一格填了預設值
    #: 就能跑得出正確答案的話，它就是進階的；反之（``pitch`` 那種，站點知道
    #: 但程式猜不到的東西）不管多難懂都要留在外面。
    #:
    #: 為什麼不是把它們刪掉：``smooth`` / ``sensitivity`` 這幾個在**調不出來**
    #: 的那一天是唯一的出路，而那一天使用者最需要它們就在手邊。收起來不是
    #: 貶低它們，是承認「第一次打開這張卡的人不該從這裡開始」。
    advanced: bool = False
    #: 這個值是**影像上的一段長度（像素）**，而且畫成一個以缺陷為中心的方框會
    #: 幫助使用者決定它（F11 Enhance-UI-A）。UI 會把那個方框疊在預覽影像上，
    #: 拖滑桿時跟著變。
    #:
    #: 為什麼要一個**明講的旗標**而不是「``unit=="px"`` 就畫」：``unit="px"`` 的
    #: 參數裡有一半不是鄰域範圍（``roi_cross`` 的條紋間距、框線粗細、離邊界的
    #: 留白）。拿一個方框去表示「條紋間距」會讓畫面說謊 —— 那跟 F9/F10 那條
    #: 「畫布不能說謊」是同一件事，只是換到影像上。
    #:
    #: 判準：這個數字是不是一個**鄰域的邊長**（濾波核、結構元素、搜尋窗）。
    #: 是就填，其他長度不要填。
    extent: bool = False
    #: ``channel_map`` 的列**代表什麼**：``"images"``（預設，一列一張圖）或
    #: ``"labels"``（一列一個 GDS layer id）。F11 Region-3。
    #:
    #: 只換三句話（左欄的字、加一列那顆鈕、提示），**資料形狀完全一樣**
    #: —— 兩者都是「整數 → 名字，空的就是不要」。所以是一個旗標而不是第二個
    #: widget：抄第二份出來的那份一定會漂移（這個 repo 記過三次）。
    row_kind: str = "images"
    #: 這一格的選項是**執行期才知道的**（F15-2）：值不是卡片列得出來的一張表，
    #: 而是「現在載了哪幾份第二 source」「那一份的一顆有哪幾張圖」「那一份的
    #: KLARF 有哪些欄」。填一個 :data:`RUNTIME_CHOICES` 裡的鍵，UI 就去問
    #: Studio 要清單。
    #:
    #: 為什麼**不是** ``type="choice"``：`choice` 的 ``validate`` 會把不在清單裡
    #: 的值擋下來，而 recipe 是**在資料掛上來之前**就讀進來的 —— 那時候一份都還
    #: 沒掛，於是每一份存了 source 名字的 recipe 都會在開檔的那一刻爆掉。
    #: 所以型別維持 ``str`` / ``multi_choice``（兩者都不強制值落在清單裡），
    #: 這個欄位只影響**打字還是用選的**。
    #:
    #: 認不得的鍵（例如 UI 還沒實作那一種）→ 就是一個普通的文字框，不會壞。
    choices_from: str = ""

    def visible_for(self, params: Optional[Dict[str, Any]]) -> bool:
        """在這組參數下，這一列該不該顯示（沒有 ``show_when`` 就永遠顯示）。"""
        return param_visible(self.show_when, params)

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ParamError(f"parameter '{self.name}': unknown type '{self.type}' "
                             f"(allowed: {PARAM_TYPES})")
        if not str(self.help).strip():
            raise ParamError(f"parameter '{self.name}': help (a plain-language "
                             f"description) must not be empty")
        if self.type == "icon_choice":
            if len(self.icons or []) != len(self.choices or []):
                raise ParamError(
                    f"parameter '{self.name}': icon_choice needs one icon per "
                    f"choice ({len(self.choices or [])} choices, "
                    f"{len(self.icons or [])} icons)")
        elif self.icons:
            raise ParamError(f"parameter '{self.name}': only icon_choice takes "
                             f"icons")
        if (self.type in ("choice", "icon_choice", "multi_choice",
                          "metric_chips", "metric_choice")
                and not self.choices and not self.choices_from):
            raise ParamError(f"parameter '{self.name}': type '{self.type}' "
                             f"requires choices (or choices_from)")
        if self.choices_from:
            if self.choices_from not in RUNTIME_CHOICES:
                raise ParamError(
                    f"parameter '{self.name}': choices_from="
                    f"'{self.choices_from}' is not one of {RUNTIME_CHOICES}")
            if self.type not in ("str", "multi_choice"):
                # `choice` / `icon_choice` 的 validate 會擋掉不在清單裡的值，
                # 而執行期的清單在讀 recipe 的當下是空的 —— 見 choices_from。
                raise ParamError(
                    f"parameter '{self.name}': choices_from only applies to "
                    f"'str' and 'multi_choice' parameters (this one is "
                    f"'{self.type}')")
        if self.type in IMAGE_TYPES:
            if self.direction not in ("in", "out"):
                raise ParamError(
                    f"parameter '{self.name}': an image-stream parameter must "
                    f"say whether it is an input or an output "
                    f"(direction='in' or direction='out')")
        elif self.type in REGION_TYPES:
            # 區域參數**只有** in（F12）：沒有任何一張卡是用參數把區域「吐出去」
            # 的 —— 產出的區域一律由 ``resolve_regions_out`` 宣告，因為它們的
            # 名字常常是算出來的（``<name>_center``）而不是某一格填的字。
            if self.direction != "in":
                raise ParamError(
                    f"parameter '{self.name}': a region parameter is always an "
                    f"input (direction='in') - it says which upstream region "
                    f"this card works on, and the canvas draws that as a line")
        elif self.direction:
            raise ParamError(
                f"parameter '{self.name}': direction only applies to "
                f"image / region parameters")

    # -- 輸入／輸出（F10；區域是 F12）---------------------------------------
    def is_input(self) -> bool:
        return self.direction == "in"

    def is_output(self) -> bool:
        return self.direction == "out"

    def is_image_input(self) -> bool:
        """吃**影像流**的輸入格（畫布上的圓埠、實線）。"""
        return self.direction == "in" and self.type in IMAGE_TYPES

    def is_region_input(self) -> bool:
        """吃**具名區域**的輸入格（畫布上的菱形埠、虛線；F12）。"""
        return self.direction == "in" and self.type in REGION_TYPES

    def required_input(self, params: Optional[Dict[str, Any]] = None) -> bool:
        """這一格**非有來源不可**嗎（在這組參數下）。

        判準是 ``default``：預設值指得出一條流的（``source="diff"``）是這張卡
        的主要輸入，沒有它就跑不起來；預設是空字串的（``normalize`` 的
        ``range_from`` / ``use_within``）本來就是「要用再接」的選配。

        ``show_when`` 藏起來的那幾格不算 —— ``normalize`` 的 ``reference``
        只有選了 *Match to another stream* 才用得到，方法是 percentile 的時候
        要求它有來源，等於憑空多一個接不完的埠。
        """
        # **只問影像**：區域的輸入一律是選配（沒接就是量整張圖），而
        # ``missing_inputs`` 的下游語意是「這張卡還跑不起來，所以它後面不長
        # 東西」—— 沒挑區域的量測卡跑得起來。
        return (self.is_image_input() and bool(str(self.default or "").strip())
                and self.visible_for(params))

    def validate(self, value: Any) -> Any:
        """coerce + 檢查範圍；失敗拋 ParamError（訊息含參數名）。"""
        try:
            if self.type == "int":
                v: Any = int(value)
            elif self.type == "float":
                v = float(value)
            elif self.type == "bool":
                if isinstance(value, str):
                    v = value.strip().lower() in ("1", "true", "yes", "on")
                else:
                    v = bool(value)
            elif self.type in ("str", "expr", "feature_key", "feature_keys",
                               "image_key", "template"):
                # ``expr`` 跟 ``str`` **存的是同一個東西**（F21-B）——
                # 差別只在 UI 認得它是算式。這一行漏掉 ``expr`` 的話，
                # 每一份用到那張卡的 recipe 都會在 `validate_params` 炸
                # 「unknown type」（`tests/test_ui_f21_expr_picker.py` 擋著）。
                v = str(value)
            elif self.type == "region_key":
                # **一個**區域名（``region_keys`` 是逗號清單）。空字串合法 ——
                # 「還沒挑」由卡片的 configuration_issues 講，不是這裡。
                v = str(value).strip()
                if "," in v:
                    # 直接丟 ParamError —— 下面那個通用的 except 會把
                    # 「為什麼壞」蓋成「converted to region_key」（鐵則 4：
                    # 擋下來的那句話要是白話的）。
                    # ⚠ **卡片的名字從 REGISTRY 問，不要寫死。**
                    # 這一句以前寫死「Gray level」，而 2026-08-25 那張卡改叫
                    # GLV —— 一句擋在使用者面前的錯誤訊息因此指著一張畫面上
                    # 不存在的卡。`tests/test_glv_compare.py` 當場抓到了，
                    # 而它抓得到正是因為它問的是 `label` 而不是那串字。
                    raise ParamError(
                        "parameter '%s' takes one region name, not a list "
                        "(got %r). Use one %s card per pair."
                        % (self.name, str(value), _label_of("glv_stats")))
            elif self.type in ("image_keys", "multi_choice", "metric_chips",
                               "region_keys"):
                # 正規化：去空白、去空項、去重複但保留順序。
                # 手打的 "ref, ref ,, test" 與 UI 勾出來的 "ref,test" 等價，
                # 存進 recipe 的字串才不會因為輸入方式不同而長得不一樣。
                # multi_choice / metric_chips 刻意**不**強制值落在 choices
                # 裡：清單是「常用的那幾個」，手寫 recipe 的自由值（例
                # glv_q37）照樣合法，認不認得由卡片的 run() 用它自己的話說。
                seen: List[str] = []
                for tok in str(value).split(","):
                    tok = tok.strip()
                    if tok and tok not in seen:
                        seen.append(tok)
                v = ",".join(seen)
            elif self.type == "curve":
                # 擋在這裡而不是等 run() 才炸（鐵則 4）。順便正規化：
                # 排序、去空白、統一小數位 —— 手打的字串與 UI 拉出來的一樣。
                v = format_curve(parse_curve(value))
            elif self.type == "cell_rois":
                # 同上：擋在打字的當下，並正規化成「四位小數、去尾數零」——
                # round-trip 要是 identity（見 cellrois.format_cell_rois）。
                v = format_cell_rois(parse_cell_rois(value))
            elif self.type == "channel_map":
                # 同上：擋在打字的當下，並正規化成「依頁碼排序、", " 分隔」
                # —— round-trip 要是 identity（見 channels.format_channel_map）。
                v = format_channel_map(parse_channel_map(value))
            elif self.type == "metric_choice":
                # 單選版 metric_chips：**不**強制值落在 choices（同上面那條
                # 規矩 —— 手寫的 glv_q37 合法，認不認得由卡片的 run() 說），
                # 但一定是**一個** id：逗號進得來的話它就變回多選了。
                v = str(value).strip()
                if "," in v:
                    raise ParamError(
                        f"parameter '{self.name}' takes one statistic id, "
                        f"not a list (got {v!r})")
                if not v:
                    v = str(self.default)
            elif self.type in ("choice", "icon_choice"):
                v = str(value)
                if v not in (self.choices or []):
                    raise ParamError(
                        f"parameter '{self.name}': '{v}' is not one of {self.choices}"
                    )
            else:  # pragma: no cover — 擋在 __post_init__
                raise ParamError(f"parameter '{self.name}': unknown type")
        except ParamError:
            raise
        except (CurveError, ChannelMapError, CellRoiError) as exc:
            # 這兩個的訊息已經是白話的，別被下面的通用訊息蓋掉
            raise ParamError(f"parameter '{self.name}': {exc}") from None
        except (TypeError, ValueError):
            raise ParamError(
                f"parameter '{self.name}': '{value}' cannot be converted "
                f"to {self.type}"
            ) from None
        if self.is_output() and isinstance(v, str):
            # 輸出流的名字是使用者自己取的（`write result to`），所以它是少數
            # 「打錯了要當場說」的欄位 —— 空的沒有意義，怪字元會讓下游的特徵
            # 名指不到（見 STREAM_NAME_PATTERN）。
            if not v.strip():
                raise ParamError(
                    f"parameter '{self.name}': the result stream needs a name "
                    f"(this is what the next card connects to)")
            if not re.match(STREAM_NAME_PATTERN, v.strip()):
                raise ParamError(
                    f"parameter '{self.name}': '{v}' cannot be used as a "
                    f"stream name - use letters, digits and underscores only, "
                    f"and do not start with a digit")
        if self.pattern and isinstance(v, str) and not re.match(self.pattern, v):
            raise ParamError(
                "parameter '%s': '%s' is not allowed here%s"
                % (self.name, v,
                   (" - " + self.pattern_help) if self.pattern_help else ""))
        if self.type in ("int", "float"):
            if self.min is not None and v < self.min:
                raise ParamError(f"parameter '{self.name}': {v} is below the "
                                 f"minimum of {self.min}")
            if self.max is not None and v > self.max:
                raise ParamError(f"parameter '{self.name}': {v} is above the "
                                 f"maximum of {self.max}")
        return v


def qualified_feature_name(prefix: str, name: str) -> str:
    """被蓋掉的特徵改用這個名字保存：``<前綴>_<原名>``。

    定義住在這裡（PR-3 起）：`FeatureSpec.qualified` 要用它，而 engine
    import step —— 反過來就循環了。`engine.qualified_feature_name` 是它的
    re-export，公開名字不變（store / UI / 測試都用那個名字）。

    D1（使用者 2026-08-16 同意）：**特徵掛在產出它的東西上**，所以「這個數字
    從哪來」永遠答得出來。D2：**沒撞名就用原名**，撞名才加前綴 —— 使用者平常
    看到的名字跟以前一模一樣。``prefix`` 優先是流名（`engine.feature_prefix`
    算的），退路是節點 id。
    """
    return "%s_%s" % (prefix, name)


@dataclass(frozen=True)
class FeatureSpec:
    """一個特徵名的**結構化身分**（PR-3）—— 在名字誕生的地方組出來。

    ``name`` 是完整特徵名，**與 `resolve_features` 逐位元組相同**（鐵測試
    守著）：字串仍然是分數表達式的變數、CSV 的欄名、KLARF 的來源 —— 結構是
    補上去的 metadata，不是改名。其餘欄位空字串／-1 = 「這一段不存在」。

    variant 裝的是**名字裡真正存在的變體後綴**（2026-08-27 使用者定調）：
    nm/nm2 孿生、each-box 的 typical/outlier/outlier_box、引擎寫的
    missing/raw、撞名救援名（rescued）。``epi_center`` 那種是**區域名**
    （region + region_role），``glv_worst_score`` 那種是**統計量 id**
    （metric）—— 不是 variant。

    為什麼住在 step.py：命名契約（`resolve_features` / `feature_parts` /
    `full_prefix`）的家在這裡，拆與合只能有一個家（CLAUDE.md §0）。
    """

    name: str
    card: str = ""            #: step key（class 層級）；node_id 由 binder 掛
    base: str = ""            #: 去前綴後的那段（== feature_parts 的 base）
    stream: str = ""          #: 流名前綴（單流 = ""）
    region: str = ""          #: 區域名前綴（單區域 = ""；含後綴全名如 epi_center）
    region_index: int = -1    #: 第幾個區域 —— 決定顏色；無區域 = -1
    region_role: str = ""     #: "" | "all" | "center" | "others"
    own: str = ""             #: 使用者填的 output_prefix
    variant: str = ""         #: "" | nm | nm2 | typical | outlier | outlier_box
                              #:    | missing | raw | rescued
    metric: str = ""          #: 統計量 id（METRIC_GROUPS 的鍵那一層）；無 = ""
    stat: str = ""            #: 只有 cmp_* 用：比的是哪個統計量（stat-free = ""）
    family: str = ""          #: "glv" | "cmp" | "cd" | "region" | "engine" | ""

    def qualified(self, prefix: str) -> "FeatureSpec":
        """撞名救援名的 spec（`engine._rescue_overwritten_features` 那一份）。"""
        from dataclasses import replace
        return replace(self, name=qualified_feature_name(prefix, self.name),
                       variant="rescued")

    def parts(self) -> Dict[str, Any]:
        """`Step.feature_parts` 形狀的相容 dict（`feature_html` 吃這個）。"""
        out: Dict[str, Any] = {"base": self.base or self.name}
        if self.stream:
            out["stream"] = self.stream
        if self.region:
            out["region"] = self.region
            out["region_index"] = int(self.region_index)
        if self.own:
            out["own"] = self.own
        return out


class Step(ABC):
    """所有卡片的基底。子類別必須設定 key/label/category 並實作 run()。"""

    key: ClassVar[str] = ""
    label: ClassVar[str] = ""            # UI 顯示名
    category: ClassVar[str] = ""
    #: 流程階段（卡片庫分組用）。空字串 = 依 category 推一個保守的預設，
    #: 所以舊卡片不宣告也不會壞（見 :meth:`resolve_group`）。
    group: ClassVar[str] = ""
    help: ClassVar[str] = ""             # 一行白話：這張卡做什麼
    params: ClassVar[List[ParamSpec]] = []
    reads: ClassVar[List[str]] = []      # 預設宣告；param 相依時覆寫 resolve_reads
    writes: ClassVar[List[str]] = []
    features_out: ClassVar[List[str]] = []
    requires_ref: ClassVar[bool] = False  # True → rsem 單張資料流不可用（除非上游造出 ref）

    # ---- 參數 -------------------------------------------------------------
    @classmethod
    def validate_params(cls, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """未知參數 → 錯；缺參數 → 帶預設；逐一 coerce/範圍檢查。回傳乾淨 dict。"""
        raw = dict(raw or {})
        spec_by_name = {p.name: p for p in cls.params}
        unknown = sorted(set(raw) - set(spec_by_name))
        if unknown:
            raise ParamError(f"[{cls.key}] unknown parameters: {unknown} "
                             f"(allowed: {sorted(spec_by_name)})")
        out: Dict[str, Any] = {}
        for name, spec in spec_by_name.items():
            out[name] = spec.validate(raw.get(name, spec.default))
        return out

    # ---- I/O 宣告（param 相依的卡片覆寫這三個 classmethod）------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return list(cls.reads)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return list(cls.writes)

    @classmethod
    def resolve_writes_for_kind(cls, params: Dict[str, Any], kind: str) -> List[str]:
        """資料型別相依的 writes 宣告（validate 對 route 首卡使用）。

        預設同 ``resolve_writes``；像 load 卡這種「寫什麼取決於資料型別」的卡
        覆寫此方法（例：ebi_patch → test+ref，rsem → single+test）。
        """
        return cls.resolve_writes(params)

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return list(cls.features_out)

    @classmethod
    def diagnostic_features(cls, params: Dict[str, Any]) -> List[str]:
        """這些特徵在講「**這張卡自己做了什麼**」，不是在量缺陷（F11 Enhance-3）。

        為什麼要分這一類：`validate` 的 `feature-collision` 警告是為了抓
        「兩張量測卡安靜地蓋掉彼此的量測值」。而 Enhance 卡的診斷數字
        （`clip_frac` 之類）是**每一張都會產出**的 —— 一份有兩張 Enhance 卡的
        recipe 因此必然撞名，於是那個警告在每一份正常的 recipe 上都會出現。
        而使用者學會忽略一條警告之後，真的那一條也一起被忽略了（推廣鐵則）。

        撞名的**資訊沒有丟**：engine 的 `_rescue_overwritten_features` 會把前一張
        的值留成 ``<節點名>_clip_frac``（黃金值裡的 `norm_clip_frac` 就是它）。
        所以這裡跳過的只是那句話，不是那個值。
        """
        return []

    @classmethod
    def diagnostic_alarms(cls, params: Dict[str, Any]) -> List[Tuple[str, bool]]:
        """(完整特徵名, 出事時的布林值) —— 這張卡的哪幾個診斷值得亮警示。

        只有列在這裡的名字才可能亮結果表的警示徽章 —— UI **永遠不對數值型
        診斷發明門檻**（``glv_sat_frac`` 多少算高是製程的事，不是軟體的事）。
        極性是明講的資料：``("glv_ok", False)`` 是「0 就出事」、
        ``("cd_touches_edge", True)`` 是「1 就出事」—— 不靠名字後綴猜。

        不變量（有測試守）：這裡的名字 ⊆ :meth:`diagnostic_features`。
        """
        return []

    @classmethod
    def resolve_requires_ref(cls, params: Dict[str, Any]) -> bool:
        """在這組參數下，這張卡是不是真的需要一條 ``ref``（F7-20）。

        以前 ``requires_ref`` 是類別常數，因為一張卡只做一件事。合併之後
        「需不需要 ref」跟著 ``method`` 走：Normalize 選 *Match to another
        stream* 才需要，選 Percentile 不需要。用常數的話，rsem route 上
        只要放了 Normalize 就會被誤判成缺 ref。
        """
        return bool(cls.requires_ref)

    # ---- 輸入／輸出的埠（F10）----------------------------------------------
    #
    # 「一張卡剛被 new add 時，前後應該都是空的乾淨的；連上 source，後面
    # source 才會出來」（使用者定調 2026-08-17）。這三個 classmethod 是那句話
    # 在程式碼裡的形狀 —— 畫布、lint、引擎全部問它們，所以**不會有第二套說法**。
    @classmethod
    def input_specs(cls) -> List[ParamSpec]:
        """吃**影像流**的那幾格（畫布上的圓埠）。

        F12 起這裡明講「影像」—— 區域也變成輸入埠了，而呼叫這一支的每一個地方
        （``missing_inputs`` / ``cleared_inputs`` / ``is_source`` / 畫布拉線的
        落點）問的都是影像。區域的那幾格見 :meth:`region_input_specs`。
        """
        return [p for p in cls.params if p.is_image_input()]

    @classmethod
    def region_input_specs(cls) -> List[ParamSpec]:
        """吃**具名區域**的那幾格（畫布上的菱形埠；F12）。"""
        return [p for p in cls.params if p.is_region_input()]

    @classmethod
    def output_specs(cls) -> List[ParamSpec]:
        """輸出流名字的那幾格（``out`` 這種；改了它畫布上的埠就跟著改名）。"""
        return [p for p in cls.params if p.is_output()]

    @classmethod
    def is_source(cls) -> bool:
        """這張卡是**入口**嗎 —— 沒有輸入埠就是（F11 Input-0）。

        為什麼要這個判斷
        ----------------
        以前「入口」的定義是**位置**：``route`` 上第一張啟用的卡。那是線性
        route 時代的寫法（F9 之前畫布還沒有線），而它同時出現在三個地方
        （``recipe.validate``、``engine._implicit_bindings``、
        ``viewmodel.available_streams``）都寫成 ``first = True`` 這個旗標。

        位置定義的後果是**一份 recipe 只能有一個 image source**：第二張入口卡
        拿不到 kind-aware 的 writes 宣告（``load_patch`` 在 ``channels="auto"``
        下只保守宣告 ``["test"]``），於是它真的會產出的那幾條流在 validate 眼裡
        不存在，下游冒出一片**假的** ``missing-image``。

        現在改成看**事實**：入口就是**不吃任何影像流的卡**，跟它排在第幾個無關。
        所以「patch 的頁 + GLAS 的 sidecar」這種兩個入口的 recipe 才成立，
        而且刪掉第一張卡不會讓整條 route 的檢查換一套語意。

        判準是兩個**宣告**的聯集，不是一個：

        - 沒有輸入埠（``direction="in"`` 的 ``image_key(s)`` 參數，F10 起必填）；
        - **而且**沒有靜態 ``reads``。第二條不是多餘的 —— 一張卡可以宣告
          ``reads = ["diff"]`` 卻沒有讓使用者挑來源的參數（測試裡的假卡就是
          這樣，早期的卡片風格也是）。只看埠的話那種卡會被當成入口，於是
          ``missing-image`` 整條檢查安靜地失效。

        看**宣告**而不看**值**（``resolve_reads(params)``）也是刻意的，理由跟
        F10 那條一樣：值是會被清空的（剛加進畫布的卡輸入本來就是空的），
        用值判斷的話一張還沒接線的卡會變成「入口」而躲過 ``not-connected``。

        **第三條是 F16 加的：入口要真的產出影像流。**
        F16 之前「不吃影像」與「是入口」是同一件事，因為每一張不吃影像的卡都是
        load 卡。Algo 段（`feature_math`：吃數字、吐數字、一張圖都不碰）讓那個
        巧合不成立了 —— 而被當成入口的後果是**整條 lint 對它靜音**：
        ``validate`` 對入口卡會 ``continue``，於是「這張卡指到一個沒人算出來的
        數字」那條 error 根本走不到（實測就是這樣：一條 issue 都沒有）。
        Output 段（什麼都不吐）之後也會落在同一條規則上。

        判準仍然是事實而不是標籤：**入口 = 沒有輸入、而且憑空生出影像流**。
        """
        return bool(cls.writes) and not cls.input_specs() and not cls.reads

    @classmethod
    def missing_inputs(cls, params: Dict[str, Any]) -> List[str]:
        """哪些**必要**的輸入還沒有來源（回參數名，空 list = 接齊了）。

        「沒有來源」就是那一格是空字串。它不是「使用者填錯了」，是
        **這張卡還沒有被接上任何東西** —— 所以它不該有輸出、不該進 lint 的
        其他檢查、更不該安靜地退回「最後一個寫這個名字的人」去拿圖。
        """
        params = dict(params or {})
        return [p.name for p in cls.params
                if p.required_input(params)
                and not str(params.get(p.name, p.default) or "").strip()]

    @classmethod
    def cleared_inputs(cls, params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        """把所有輸入清成空字串的參數 —— **剛加進畫布的卡拿到的就是這個**。

        卡片的 ``default``（``source="diff"``）仍然留著，因為那是**規格的預設
        值**，手寫 recipe 省略它時要有東西可用。清掉的是**這一張卡在畫布上的
        值**：畫布上沒有線，那這張卡就沒有來源，兩邊必須是同一句話。
        """
        out = dict(params or {})
        for spec in cls.input_specs():
            out[spec.name] = ""
        return out

    # ---- 影像上的量測標記（F19）--------------------------------------------
    #: 這張卡的標記是**結構**還是**掃描線**（F33，2026-08-26）。
    #:
    #: `ImageView._paint_marks` 預設「線畫到幾乎看不見（alpha 70）、點畫滿」，
    #: 而那條規矩是為 **CD 的幾十條掃描線**寫的：線只是說「那個判斷是在哪一列
    #: 上做的」，點才是答案，所以線要退到背景去。GLV 也**刻意**靠它 ——
    #: 它的上緣線本來就該看不見（描邊會跟區域框重疊，等於沒畫）。
    #:
    #: 但有些卡交出來的是**少少幾條、而且線本身就是答案**（H2H 的「對到這一塊」
    #: 是一個框、「瞄準這裡」是一個十字）。那時候淡化不是在減少雜訊，
    #: 是在**藏起唯一的資訊** —— 實測就是「看不太出來」。
    #:
    #: 設成 True 的卡，它的標記畫滿（不透明、線粗一點）。預設 False，
    #: 所以既有的卡一張都不用動。
    marks_solid: ClassVar[bool] = False

    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any],
                      stream: Optional[str] = None) -> Any:
        """這張卡要在預覽影像上畫哪些**線段與點**（正規化座標）。

        回 ``(lines, points, focus, labels)``：

        * ``lines`` —— ``[[(x0, y0), (x1, y1)], …]``，一條線段一個
        * ``points`` —— ``[[(x, y), …], …]``，**跟 ``lines`` 等長**，
          ``points[i]`` 是第 i 條線段上的點
        * ``focus`` —— 要畫粗的那一條的索引（``-1`` = 沒有）
        * ``labels`` —— 每一條線段屬於**哪一個具名區域**（跟 ``lines`` 等長）。
          給了就一個區域一個顏色，而且**跟影像上那個區域的框同一個顏色** ——
          兩張卡量同一塊而畫成兩種顏色的話，畫面上沒有東西說得出它們是同一塊
          （`ImageView.set_overlay` 立下的規矩）。

        為什麼是一個 hook 而不是「studio 去讀某張卡的 meta」
        ----------------------------------------------------
        F18 §9.0 把「影像上把正在量的那一塊點出來」列為**整個 Measure 段共用**
        的東西，指名跟 CD 一起做 —— 只給一張卡做一份的話，下一張量測卡進來會有
        第二份長得不一樣的。而 meta 的形狀是**那張卡的事**，所以讀它的程式碼
        要住在那張卡上，不是住在 UI 裡。

        區域框走的是另一條路（`viewmodel.region_overlay`，從 model 推導）——
        **兩者來源不同，不要混**：框是「recipe 說要看哪裡」，標記是「這一顆真的
        量到了什麼」，而後者只有跑過才有。

        ``stream`` 是**畫面現在顯示的那一條影像流**（``None`` = 不知道）。
        一張卡可以在好幾條流上各量一次（``source`` 是複數型別），而那些量測
        **是在不同的影像上做的** —— 全部畫上去的話，你正在看的那張圖上會有
        一半的線是量在另一張圖上的結果，而畫面上沒有任何東西透露那件事。
        所以知道是哪一條時就只交那一條的（2026-08-22）。

        預設什麼都不畫，所以既有的卡一張都不用動。
        """
        return [], [], -1, []

    # ---- 具名區域（F7-9）---------------------------------------------------
    #: 影像流有 reads/writes 可以在 validate 裡模擬，**具名 ROI 以前沒有**。
    #: 於是「量測卡指到一個沒人定義的區域」只有兩種下場：名字打錯 → 每顆
    #: defect 執行到一半才 StepError；上游那張 Region 卡被拿掉 →
    #: **安靜地改量整張圖**，跑得完、有數字、而且是錯的。
    #: 後者是最糟的一種：使用者看不出哪裡不對。所以區域也宣告成契約，
    #: 跟影像流走同一條檢查路徑（``recipe.validate`` 的 unknown-region）。
    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        """這張卡會定義哪些具名區域。"""
        return []

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        """這張卡需要哪些具名區域（空字串 = 整張影像，不算需求）。"""
        return []

    # ---- 吃**特徵**的卡（F16，Algo 段）------------------------------------
    #: 影像流有 ``resolve_reads``、具名區域有 ``resolve_regions_in``，而
    #: **特徵一直沒有對應的宣告** —— 因為在 F16 之前，唯一吃特徵的東西是
    #: recipe 上那個 ``score`` 欄位，而它由 ``validate`` 特別處理。
    #:
    #: Algo 段（「拿這些 feature 去做更 custom 的處理」）讓「吃特徵的卡」變成
    #: 一整類，所以那件事要有自己的宣告 —— 不然「這張卡指到一個沒人算出來的
    #: 數字」要等**每一顆 defect 都失敗**才看得出來，而那正是這個 repo 對
    #: 具名區域做過一次的事（F7-9 的 unknown-region）。
    #:
    #: ⚠ **這個宣告目前在畫布上沒有對應的線。** 特徵是扁平的全域命名空間
    #: （見 docs/ARCHITECTURE.md），而 d4t 從來沒有「特徵從哪一張卡來」的埠 ——
    #: 分數表達式也是這樣。所以 Algo 卡的相依性靠的是 route 上的先後順序，
    #: 而 ``validate`` 的 ``unknown-feature-input`` 是目前唯一擋得住它的東西。
    #: 要讓它變成畫布上的一條線，得先決定第三種埠長什麼樣（見 ROADMAP 的
    #: 「跨顆那一層」——那一段有同一個問題）。
    @classmethod
    def resolve_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """這張卡會讀哪些**已經算出來的特徵**（Algo 段用）。

        少一個 = 這張卡**跑不起來**（`feature_math` 的算式指到一個不存在的
        變數），所以 lint 報的是 error。「少了會退化但跑得完」的那一半在
        :meth:`optional_features_in`。
        """
        return []

    @classmethod
    def feature_parts(cls, params: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """每個宣告出來的名字 → **它是怎麼組出來的**（F37 A4）。

        鍵是完整的特徵名，值是這幾格（沒有的就不放）::

            {"base": "glv_median",   # 去掉前綴之後的那一段
             "stream": "test",       # 影像流（只接一條時沒有這一格）
             "region": "epi",        # 具名區域（只接一個時沒有這一格）
             "region_index": 0,      # 第幾個 —— 決定顏色
             "own": "hot"}           # 使用者自己填的 output_prefix

        為什麼要卡片來答，而不是 UI 拆字串
        ----------------------------------
        **拆不出來。** ``test_epi_glv_median`` 這一串裡，哪一段是流、哪一段是
        區域、哪一段是使用者自己取的名字 —— 三者都是任意的識別字，中間都用
        底線接。UI 只能猜，而猜錯的下場是把一個區域名畫成流名（顏色跟著錯，
        而顏色正是這件事的重點）。

        組名字的規則住在 `MultiSourceStep.full_prefix`，所以**拆的規則要住在
        同一個地方**（`CLAUDE.md` §0）。這一支就是那一支的反向。

        預設回空的：不知道怎麼拆就不拆，UI 照原樣顯示整串。那是對的退化 ——
        少一點資訊，不會是錯的資訊。
        """
        return {}

    @classmethod
    def resolve_feature_specs(cls, params: Dict[str, Any]) -> List["FeatureSpec"]:
        """`resolve_features` 的結構化版本（PR-3）：一個名字一個 `FeatureSpec`。

        預設從 `resolve_features` + `feature_parts` 組退化版 —— 未遷移／
        第三方卡自動拿到 name+card（＋parts 拆得出的欄位）。同 `feature_parts`
        的退化原則：少一點資訊，不會是錯的資訊。

        鐵測試（`tests/test_feature_specs.py`）：每張註冊卡、每組代表參數下
        ``[s.name for s in specs]`` 與 `resolve_features` **逐位元組相同**
        （順序也相同）。`resolve_features` 是相容介面，簽名語意不變。
        """
        parts = cls.feature_parts(params)
        out: List[FeatureSpec] = []
        for n in cls.resolve_features(params):
            p = parts.get(n, {})
            out.append(FeatureSpec(
                name=str(n), card=cls.key,
                base=str(p.get("base", "") or ""),
                stream=str(p.get("stream", "") or ""),
                region=str(p.get("region", "") or ""),
                region_index=(int(p["region_index"])
                              if "region_index" in p else -1),
                own=str(p.get("own", "") or "")))
        return out

    @classmethod
    def optional_features_in(cls, params: Dict[str, Any]) -> List[str]:
        """這張卡會讀、但**少了只會退化不會失敗**的特徵（F37）。

        跟 :meth:`resolve_features_in` 是同一對，分界跟
        :meth:`configuration_issues` / :meth:`configuration_hints` 那一對
        **一字不差**：上面那支是「會失敗」，這一支是「跑得起來，但你八成不是
        這個意思」。所以 lint 對它報 warning，不擋住整份 recipe。

        誰需要它：Output 段那幾張。``rank_by`` 指到一個沒人算出來的數字時，
        出圖卡**排不出順序就安靜地退回檔案順序** —— 使用者拿到 N 張正常的圖，
        而「最值得看的那 N 顆」完全沒有發生（F30 修過一次的那個 bug）。

        它同時是**改名的安全網**（F37 A2）：量測卡的前綴是條件式的，所以在
        既有的卡上多接一條區域線會把它寫的每一個名字都改掉（``glv_median``
        → ``epi_glv_median`` ＋ ``mg_glv_median``），而指著舊名字的地方不會
        跟著改。有了這一支，那件事在**按下去之前**就講得出來，而且講得出
        「是哪一張卡的哪一格」。

        ⚠ 由**卡片自己**決定哪一格算數（例如 KLARF 的 ``size_feature`` 只在
        真的指定了 size 欄位時才有意義）—— lint 那邊照型別掃的話會對一個
        完全沒有在用的預設值報警。
        """
        return []

    # ---- 「還沒設定完」（F7-13）--------------------------------------------
    #: **參數合法 ≠ 設定完成。** ``roi_template`` 的 template 空字串是完全合法的
    #: str，所以 ``validate_params`` 沒話說，lint 也沒話說 —— 但那張卡跑起來
    #: 每一顆都會失敗。以前使用者要跑過一次才知道，而且是在跑完 200 顆之後。
    #:
    #: 這個方法讓卡片自己講「我還缺什麼」，而且是用**這張卡的話**講（模板要去
    #: 按哪顆鈕），不是一句通用的「參數是必填的」。回傳的每一句都會變成一個
    #: lint error，畫布上那張卡也會因此掛上警示標記。
    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """這張卡還缺哪些設定**才跑得起來**（空 list = 沒問題）。

        ⚠ **判準是「這張卡會不會拋 / 會不會什麼都不產出」**，不是「使用者有沒有
        填完」。跑得起來、只是設定得不完整的那種，放 :meth:`configuration_hints`
        —— 它是 warning，不會擋住整份 recipe。
        """
        return []

    # ---- 「跑得起來，但你八成不是這個意思」（F35，2026-08-26）--------------
    #: `configuration_issues` 的**另一半**。上面那一支的契約寫得很明白：
    #: 「那張卡跑起來每一顆都會失敗」—— 而 error 這個級別正是踩在那句話上。
    #:
    #: 有一種設定不符合那個契約：**卡片跑得完，只是它做的事跟使用者想的不一樣。**
    #: F33 的 `pair_source` 就把這種訊息放進了 `configuration_issues`
    #: （「填了 Rank within 但 Rank by 是空的」），於是一份完全跑得動的 recipe
    #: 被 error 擋在 CLI 門外 —— 而那張卡其實只是少寫兩個特徵。
    #:
    #: 兩支分開之後判準是一句話：
    #:
    #: * **error（`configuration_issues`）** —— 這張卡會拋，或什麼都不產出。
    #: * **warning（這一支）** —— 它會跑，但你八成不是這個意思。
    #:
    #: 而 warning 這一級**要講得出使用者接下來看得到什麼**（不然它只是一句
    #: 沒有後果的碎念）。
    @classmethod
    def configuration_hints(cls, params: Dict[str, Any]) -> List[str]:
        """設定得不完整、但**跑得起來**的那些（空 list = 沒問題）。"""
        return []

    @classmethod
    def kind_issues(cls, params: Dict[str, Any],
                    kind: str) -> List[Tuple[str, str, str, str]]:
        """只在某種資料型別上才成立的發現：``(code, level, title, detail)``。

        `configuration_issues` / `configuration_hints` 看不到 route 的 kind
        —— 「這組設定對不對」有時取決於「一顆 defect 拿到的是置中的 patch
        還是一張大圖」（`PATCH_KINDS` / `SINGLE_IMAGE_KINDS`）。這是那一半。
        ``level`` 用 "error" / "warning" / "info"；`validate` 逐 route 呼叫，
        detail 會被冠上 route 名。
        """
        return []

    # ---- 跨顆那一層（F16）--------------------------------------------------
    #: 這張卡是**整批跑完之後跑一次**的嗎（而不是一顆一顆）。
    #:
    #: ``run_defect`` 一顆一顆跑、從不 raise（鐵則 7），所以「要看過整批才算得
    #: 出來」的東西沒有地方放：Output 的 CSV／KLARF（一批一個檔案）、離群旗標
    #: （門檻由整批的分布決定）、F15 欠的那份點對點 report。
    #:
    #: ``is_batch`` 的卡**不實作** :meth:`run`（它拿不到「一顆」），改實作
    #: :meth:`run_batch`。引擎的分工：``run_defect`` 跳過它們，
    #: :func:`batch.run_batch_steps` 在所有結果收齊之後跑它們一次。
    #:
    #: ⚠ **不進影像段快取的簽章**：快取是逐顆的、切點在最後一張影像段卡的下一
    #: 格，而跨顆那一層整個在 checkpoint 之後 —— 它看的是結果表，不是像素。
    #: （鐵則 9 問的是「會影響影像段結果的東西進簽章了嗎」，這裡的答案是「它
    #: 影響不到影像段」。寫在這裡是因為那個問題以後一定會再被問一次。）
    #:
    #: F17-④ 起這是 :attr:`scale` 推導出來的（``scale == SCALE_LOT``），
    #: **不要直接指定它** —— 直接寫 ``is_batch = True`` 仍然認得（舊卡片、外掛），
    #: `__init_subclass__` 會把 ``scale`` 補成 ``SCALE_LOT``。
    is_batch: ClassVar[bool] = False

    #: 這張卡跑的尺度：``SCALE_DEFECT``（一顆一次）或 ``SCALE_LOT``（整批一次）。
    scale: ClassVar[str] = SCALE_DEFECT

    def __init_subclass__(cls, **kw: Any) -> None:
        """讓 ``scale`` 與 ``is_batch`` 永遠是同一句話。

        **兩個方向都要**（鐵則 9 的形狀 —— 判準是「舊東西在不在」）：

        * 新卡片宣告 ``scale = SCALE_LOT`` → ``is_batch`` 跟著變 True；
        * 舊卡片（或外掛）宣告 ``is_batch = True`` 而沒有 ``scale`` →
          ``scale`` 補成 ``SCALE_LOT``。

        只做前者的話，一張還沒遷移的卡會宣告 is_batch 卻被引擎當成逐顆的 ——
        而它的 `run()` 是一句「這張卡不該這樣跑」，於是**每一顆都失敗**。
        """
        super().__init_subclass__(**kw)
        own = cls.__dict__
        if "scale" in own:
            cls.is_batch = str(own["scale"]) == SCALE_LOT
        elif own.get("is_batch"):
            cls.scale = SCALE_LOT

    def run_batch(self, bctx: Any, params: Dict[str, Any]) -> None:
        """整批跑完之後跑一次（``is_batch`` 的卡實作這個，不是 :meth:`run`）。

        ``bctx`` 是 :class:`~d4t.core.pipeline.context.BatchContext`。
        失敗請 raise StepError —— :func:`batch.run_batch_steps` 會接住並記進
        ``bctx.errors``，其他卡照跑（鐵則 7 的跨顆版）。
        """
        raise NotImplementedError(
            "%s declares is_batch but does not implement run_batch()" % cls_name(self))

    # ---- 執行 -------------------------------------------------------------
    @abstractmethod
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        """執行本步驟。可就地修改 ctx 並回傳它。失敗請 raise StepError。"""

    # ---- UI 描述 ----------------------------------------------------------
    @classmethod
    def resolve_group(cls) -> str:
        """這張卡屬於哪個流程階段。

        沒宣告 ``group`` 的卡片依 ``category`` 給一個保守預設 ——
        影像段當 enhance、算法段當 measure、判定段當 adc。
        這樣**新增 group 這個概念不會弄壞任何既有卡片**，
        外掛或還沒遷移的卡照樣列得出來。
        """
        if cls.group:
            return str(cls.group)
        if cls.category == CATEGORY_ALGO:
            return GROUP_MEASURE
        if cls.category == CATEGORY_ADC:
            return GROUP_ADC
        if cls.category == CATEGORY_BATCH:
            return GROUP_OUTPUT
        return GROUP_ENHANCE

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        """給 UI / CLI 列表用的完整卡片描述。"""
        return {
            "key": cls.key,
            "label": cls.label,
            "category": cls.category,
            "scale": cls.scale,
            "group": cls.resolve_group(),
            "help": cls.help,
            "requires_ref": cls.requires_ref,
            "params": [
                {
                    "name": p.name, "type": p.type, "default": p.default,
                    "help": p.help, "min": p.min, "max": p.max,
                    "choices": p.choices, "icons": p.icons,
                    "choice_help": p.choice_help, "unit": p.unit,
                    "label": p.label or p.name,
                    "pattern": p.pattern,
                    # ``("method", ("percentile",))`` → JSON-safe 的**一串
                    # 條件** ``[["method", ["percentile"]], …]``。一律吐多條的
                    # 形狀（F30）：單條也包成一串，於是讀的那一邊只有一種形狀
                    # 要認 —— 而 `param_visible` 兩種都吃，所以序列化過的與
                    # 原生的走的是同一支規則。
                    "show_when": (None if not p.show_when else
                                  [[n, list(v)] for n, v
                                   in show_when_conditions(p.show_when)]),
                    "section": p.section,
                    "advanced": p.advanced,
                    "direction": p.direction,
                    "extent": p.extent,
                    "row_kind": p.row_kind,
                    "choices_from": p.choices_from,
                }
                for p in cls.params
            ],
            "reads": list(cls.reads),
            "writes": list(cls.writes),
            "features_out": list(cls.features_out),
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
REGISTRY: Dict[str, Type[Step]] = {}


def _label_of(key: str) -> str:
    """一張卡**現在**畫面上叫什麼；認不得就退回 key。

    給錯誤訊息用：一句話裡提到另一張卡的時候，名字要跟卡片庫上的一致。
    寫死的話，那張卡改名的那一天這句話就開始指著一個不存在的東西。
    """
    cls = REGISTRY.get(str(key))
    return str(getattr(cls, "label", "") or key)


def register_step(cls: Type[Step]) -> Type[Step]:
    """類別裝飾器：把卡片註冊進全域 registry（key 重複 = 程式錯誤，立刻爆）。"""
    if not cls.key:
        raise ValueError(f"{cls.__name__}: key must not be empty")
    if cls.scale not in _SCALES:
        raise ValueError(f"{cls.__name__}: scale must be one of {_SCALES}, "
                         f"got '{cls.scale}'")
    if cls.category not in _CATEGORIES:
        raise ValueError(f"{cls.__name__}: category must be one of {_CATEGORIES}, "
                         f"got '{cls.category}'")
    if not str(cls.help).strip():
        raise ValueError(f"{cls.__name__}: help (a one-line plain-language "
                         f"description) must not be empty")
    if cls.key in REGISTRY:
        raise ValueError(f"step key '{cls.key}' is already registered by "
                         f"{REGISTRY[cls.key].__name__}")
    REGISTRY[cls.key] = cls
    return cls


def get_step(key: str) -> Type[Step]:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(f"unknown step '{key}'; registered: {sorted(REGISTRY)}") from None


def list_steps(category: Optional[str] = None) -> List[Type[Step]]:
    """卡片庫看到的順序：**先分類，同一類照註冊順序**。

    ⚠ 同一類裡以前是照 ``key`` 排（字母序），而那是 2026-08-25 才發現的一個
    安靜的 bug：使用者說「Measure 的 card 順序幫我改命名&重排：GLV → CD →
    Focus index」，那一輪照著改了 ``steps/__init__.py`` 的 import 順序、還在
    那裡寫下「卡片庫裡看到的先後住在這三行」—— **而畫面上一格都沒有動**
    （字母序是 CD、Focus index、GLV）。整個改動看起來完成了，測試也全綠，
    因為沒有任何一條測試問過「使用者看到的第一張是哪一張」。

    註冊順序 = ``steps/__init__.py`` 的 import 順序 = **pipeline 的順序**
    （load → normalize → denoise → … → measure → output）。對不會寫 code 的
    製程工程師來說，那是唯一一個看得懂的順序：卡片庫由上而下讀就是資料流過的
    先後。字母序把 ``align`` 排在 ``normalize`` 前面，而那是相反的。

    ⚠ **``category`` 不再參與排序**（以前是主鍵）。它跟卡片庫的分區是**兩條
    不同的軸**：分區用的是 ``group``（Input／Enhance／Region／…），而
    ``category``（image／algo／adc／batch）是引擎在用的。兩條軸一起排的結果是
    「import 順序決定看到的先後」**只對了一半** —— Region 段裡 ``roi_mask``
    （category=image）會跳到 ``roi_cross``（category=algo）前面，而那件事在
    import 那幾行上完全看不出來。一個規矩比兩個對，而這裡要的那個規矩是
    「照 import 的順序」。
    """
    return [s for s in REGISTRY.values()
            if category is None or s.category == category]
