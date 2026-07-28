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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Type

from .context import Context

CATEGORY_IMAGE = "image"
CATEGORY_ALGO = "algo"
CATEGORY_ADC = "adc"
_CATEGORIES = (CATEGORY_IMAGE, CATEGORY_ALGO, CATEGORY_ADC)

PARAM_TYPES = ("int", "float", "bool", "str", "choice", "image_key")


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
    """

    name: str
    type: str
    default: Any
    help: str
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[str]] = None
    unit: str = ""

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ParamError(f"參數 '{self.name}'：未知型別 '{self.type}'（允許：{PARAM_TYPES}）")
        if not str(self.help).strip():
            raise ParamError(f"參數 '{self.name}'：help（白話說明）不得為空 —— 推廣鐵則")
        if self.type == "choice" and not self.choices:
            raise ParamError(f"參數 '{self.name}'：choice 型別需提供 choices")

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
            elif self.type in ("str", "image_key"):
                v = str(value)
            elif self.type == "choice":
                v = str(value)
                if v not in (self.choices or []):
                    raise ParamError(
                        f"參數 '{self.name}'：'{v}' 不在選項 {self.choices} 中"
                    )
            else:  # pragma: no cover — 擋在 __post_init__
                raise ParamError(f"參數 '{self.name}'：未知型別")
        except ParamError:
            raise
        except (TypeError, ValueError):
            raise ParamError(
                f"參數 '{self.name}'：'{value}' 無法轉成 {self.type}"
            ) from None
        if self.type in ("int", "float"):
            if self.min is not None and v < self.min:
                raise ParamError(f"參數 '{self.name}'：{v} 低於下限 {self.min}")
            if self.max is not None and v > self.max:
                raise ParamError(f"參數 '{self.name}'：{v} 高於上限 {self.max}")
        return v


class Step(ABC):
    """所有卡片的基底。子類別必須設定 key/label/category 並實作 run()。"""

    key: ClassVar[str] = ""
    label: ClassVar[str] = ""            # UI 顯示名（可中文）
    category: ClassVar[str] = ""
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
            raise ParamError(f"[{cls.key}] 未知參數：{unknown}（允許：{sorted(spec_by_name)}）")
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

    # ---- 執行 -------------------------------------------------------------
    @abstractmethod
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        """執行本步驟。可就地修改 ctx 並回傳它。失敗請 raise StepError。"""

    # ---- UI 描述 ----------------------------------------------------------
    @classmethod
    def describe(cls) -> Dict[str, Any]:
        """給 UI / CLI 列表用的完整卡片描述。"""
        return {
            "key": cls.key,
            "label": cls.label,
            "category": cls.category,
            "help": cls.help,
            "requires_ref": cls.requires_ref,
            "params": [
                {
                    "name": p.name, "type": p.type, "default": p.default,
                    "help": p.help, "min": p.min, "max": p.max,
                    "choices": p.choices, "unit": p.unit,
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
        raise ValueError(f"{cls.__name__}: key 不得為空")
    if cls.category not in _CATEGORIES:
        raise ValueError(f"{cls.__name__}: category 必須是 {_CATEGORIES}，收到 '{cls.category}'")
    if not str(cls.help).strip():
        raise ValueError(f"{cls.__name__}: help（一行白話說明）不得為空 —— 推廣鐵則")
    if cls.key in REGISTRY:
        raise ValueError(f"step key '{cls.key}' 已被 {REGISTRY[cls.key].__name__} 註冊")
    REGISTRY[cls.key] = cls
    return cls


def get_step(key: str) -> Type[Step]:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(f"未知的 step '{key}'；已註冊：{sorted(REGISTRY)}") from None


def list_steps(category: Optional[str] = None) -> List[Type[Step]]:
    steps = [s for s in REGISTRY.values() if category is None or s.category == category]
    return sorted(steps, key=lambda s: (_CATEGORIES.index(s.category), s.key))
