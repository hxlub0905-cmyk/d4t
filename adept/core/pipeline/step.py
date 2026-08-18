# ADEPT pipeline contract — authored 2026-07-27 (M1).
"""Step 介面 + ParamSpec + registry。

一張「卡片」= 一個 Step 子類別：
- 宣告 ``params``（每個參數都要有白話 ``help`` 與合理 ``default`` —— 推廣鐵則）
- 宣告 reads / writes（影像流 key）與 features_out（會產出的特徵名）
- 實作 ``run(ctx, params)``（純函數風格：吃 Context、回 Context）

新算法 = 新 class + ``@register_step``，UI 與引擎零修改。

分類（三段式，見 master plan §5）：
- ``CATEGORY_IMAGE``  影像段（把圖變乾淨；寫 images）
- ``CATEGORY_ALGO``   算法段（從圖量出數字；寫 features）
- ``CATEGORY_ADC``    判定段（score / bin / 輸出）
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Type

from .context import Context
from .cellrois import CellRoiError, format_cell_rois, parse_cell_rois
from .channels import ChannelMapError, format_channel_map, parse_channel_map
from .curve import CurveError, format_curve, parse_curve

CATEGORY_IMAGE = "image"
CATEGORY_ALGO = "algo"
CATEGORY_ADC = "adc"

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
#: region         找出「要看哪裡」            snr_map / blob_segment / roi_define
#: compare        影像＋影像 → 影像           align / subtract
#: measure        影像＋區域 → 數字           glv_stats / cd_measure
#: adc            數字 → score → bin         （固定尾節點）
#: =============  =========================  ==============================
#:
#: **型別規則是預設的裁決方式，但不是唯一的。** ``snr_map`` 是影像進影像出，
#: 照型別會落在 enhance —— 但它的**唯一**消費者是 ``blob_segment``
#: （每一份範例 recipe 都是 snr → blob），而且它必須跑在 Compare 之後，
#: 放在讀起來排第二的 Enhance 裡永遠用不到。所以規則補一條：
#: **一張卡如果只為了餵另一段而存在，就跟著那一段走。**
GROUP_INPUT = "input"
GROUP_ENHANCE = "enhance"
GROUP_REGION = "region"
GROUP_COMPARE = "compare"
GROUP_MEASURE = "measure"
GROUP_ADC = "adc"

#: 卡片庫的顯示順序（讀起來是一句話：
#: Input → Enhance → Region → Compare → Measure → ADC）。
GROUP_ORDER = (GROUP_INPUT, GROUP_ENHANCE, GROUP_REGION,
               GROUP_COMPARE, GROUP_MEASURE, GROUP_ADC)
_GROUPS = GROUP_ORDER
_CATEGORIES = (CATEGORY_IMAGE, CATEGORY_ALGO, CATEGORY_ADC)

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
PARAM_TYPES = ("int", "float", "bool", "str", "choice", "image_key",
               "image_keys", "curve", "template", "multi_choice",
               "channel_map", "cell_rois")

#: 輸出流的名字可以用哪些字（F10-7）。
#:
#: 這不是潔癖：流名會變成**特徵的前綴**（一張量測卡接兩條流就吐
#: ``diff_glv_max`` / ``test_glv_max``），而特徵名是**分數表達式的變數名**。
#: 取成 ``my stream`` 的話，那個特徵在表達式裡永遠指不到 —— 而使用者要到寫
#: 分數的時候才會發現，那時候他已經不記得問題出在三張卡以前的一個命名。
#: 所以擋在打字的當下（鐵則 4：壞值不准跑到演算法裡）。
STREAM_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class ParamError(ValueError):
    """參數不合法（含參數名與原因，UI 直接顯示）。"""


class StepError(RuntimeError):
    """步驟執行失敗；engine 會攔截並記入該 defect 的結果，不會殺整批。"""

    def __init__(self, step_key: str, msg: str):
        super().__init__(f"[{step_key}] {msg}")
        self.step_key = step_key


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

    def visible_for(self, params: Optional[Dict[str, Any]]) -> bool:
        """在這組參數下，這一列該不該顯示（沒有 ``show_when`` 就永遠顯示）。"""
        if not self.show_when:
            return True
        name, values = self.show_when[0], tuple(self.show_when[1])
        return str((params or {}).get(name, "")) in {str(v) for v in values}

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ParamError(f"parameter '{self.name}': unknown type '{self.type}' "
                             f"(allowed: {PARAM_TYPES})")
        if not str(self.help).strip():
            raise ParamError(f"parameter '{self.name}': help (a plain-language "
                             f"description) must not be empty")
        if self.type in ("choice", "multi_choice") and not self.choices:
            raise ParamError(f"parameter '{self.name}': type '{self.type}' "
                             f"requires choices")
        if self.type in ("image_key", "image_keys"):
            if self.direction not in ("in", "out"):
                raise ParamError(
                    f"parameter '{self.name}': an image-stream parameter must "
                    f"say whether it is an input or an output "
                    f"(direction='in' or direction='out')")
        elif self.direction:
            raise ParamError(
                f"parameter '{self.name}': direction only applies to "
                f"image_key / image_keys parameters")

    # -- 輸入／輸出（F10）----------------------------------------------------
    def is_input(self) -> bool:
        return self.direction == "in"

    def is_output(self) -> bool:
        return self.direction == "out"

    def required_input(self, params: Optional[Dict[str, Any]] = None) -> bool:
        """這一格**非有來源不可**嗎（在這組參數下）。

        判準是 ``default``：預設值指得出一條流的（``source="diff"``）是這張卡
        的主要輸入，沒有它就跑不起來；預設是空字串的（``normalize`` 的
        ``range_from`` / ``use_within``）本來就是「要用再接」的選配。

        ``show_when`` 藏起來的那幾格不算 —— ``normalize`` 的 ``reference``
        只有選了 *Match to another stream* 才用得到，方法是 percentile 的時候
        要求它有來源，等於憑空多一個接不完的埠。
        """
        return (self.is_input() and bool(str(self.default or "").strip())
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
            elif self.type in ("str", "image_key", "template"):
                v = str(value)
            elif self.type in ("image_keys", "multi_choice"):
                # 正規化：去空白、去空項、去重複但保留順序。
                # 手打的 "ref, ref ,, test" 與 UI 勾出來的 "ref,test" 等價，
                # 存進 recipe 的字串才不會因為輸入方式不同而長得不一樣。
                # multi_choice 刻意**不**強制值落在 choices 裡：清單是「常用的
                # 那幾個」，手寫 recipe 的自由值（例 glv_q37）照樣合法，
                # 認不認得由卡片的 run() 用它自己的話說。
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
            elif self.type == "choice":
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
        """吃影像流的那幾格（畫布上的輸入埠）。"""
        return [p for p in cls.params if p.is_input()]

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
        """
        return not cls.input_specs() and not cls.reads

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

    # ---- 具名區域（F7-9）---------------------------------------------------
    #: 影像流有 reads/writes 可以在 validate 裡模擬，**具名 ROI 以前沒有**。
    #: 於是「量測卡指到一個沒人定義的區域」只有兩種下場：名字打錯 → 每顆
    #: defect 執行到一半才 StepError；名字剛好是保留字 ``blob`` 而上游又沒有
    #: Blob 卡 → **安靜地改量整張圖**，跑得完、有數字、而且是錯的。
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
        """這張卡還缺哪些設定才跑得起來（空 list = 沒問題）。"""
        return []

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
        return GROUP_ENHANCE

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        """給 UI / CLI 列表用的完整卡片描述。"""
        return {
            "key": cls.key,
            "label": cls.label,
            "category": cls.category,
            "group": cls.resolve_group(),
            "help": cls.help,
            "requires_ref": cls.requires_ref,
            "params": [
                {
                    "name": p.name, "type": p.type, "default": p.default,
                    "help": p.help, "min": p.min, "max": p.max,
                    "choices": p.choices, "unit": p.unit,
                    "label": p.label or p.name,
                    "pattern": p.pattern,
                    # ``("method", ("percentile",))`` → JSON-safe 的兩個 list。
                    "show_when": (None if not p.show_when
                                  else [p.show_when[0], list(p.show_when[1])]),
                    "section": p.section,
                    "advanced": p.advanced,
                    "direction": p.direction,
                    "extent": p.extent,
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


def register_step(cls: Type[Step]) -> Type[Step]:
    """類別裝飾器：把卡片註冊進全域 registry（key 重複 = 程式錯誤，立刻爆）。"""
    if not cls.key:
        raise ValueError(f"{cls.__name__}: key must not be empty")
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
    steps = [s for s in REGISTRY.values() if category is None or s.category == category]
    return sorted(steps, key=lambda s: (_CATEGORIES.index(s.category), s.key))
