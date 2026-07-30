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
               "image_keys", "curve", "template")


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

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ParamError(f"parameter '{self.name}': unknown type '{self.type}' "
                             f"(allowed: {PARAM_TYPES})")
        if not str(self.help).strip():
            raise ParamError(f"parameter '{self.name}': help (a plain-language "
                             f"description) must not be empty")
        if self.type == "choice" and not self.choices:
            raise ParamError(f"parameter '{self.name}': type 'choice' requires choices")

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
            elif self.type == "image_keys":
                # 正規化：去空白、去空項、去重複但保留順序。
                # 手打的 "ref, ref ,, test" 與 UI 勾出來的 "ref,test" 等價，
                # 存進 recipe 的字串才不會因為輸入方式不同而長得不一樣。
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
        except CurveError as exc:
            # CurveError 的訊息已經是白話的，別被下面的通用訊息蓋掉
            raise ParamError(f"parameter '{self.name}': {exc}") from None
        except (TypeError, ValueError):
            raise ParamError(
                f"parameter '{self.name}': '{value}' cannot be converted "
                f"to {self.type}"
            ) from None
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
