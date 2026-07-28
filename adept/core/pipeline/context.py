# ADEPT pipeline contract — authored 2026-07-27 (M1).
"""Context — pipeline 步驟間傳遞的執行狀態。

設計原則（見 docs/plans/F0-master-plan.md §3.2）：
- ``images``   命名影像流（"test"、"ref"、"ref_aligned"、"diff"、"snr_map"…）。
- ``rois``     MultiROISet（正規化座標；M3 起由 ROI 卡填入）。
- ``labels``   整數 ROI label map（0=背景, 1..N；GLAS 契約 gray[labels==k]）。
- ``features`` 扁平特徵區 —— **score 表達式的唯一變數空間**。
  任何卡塞進來的數字（CD、SNR、GLV、focus…）一視同仁。
- ``meta``     診斷與雜項（nm_per_px、對位 dx/dy、fallback_reason、blob 清單…）。

慣例：
- Step 對同名影像流做 in-place 覆寫（linear 鏈的預設行為）；要保留舊圖就寫新 key。
- feature 覆寫允許，但會記錄在 ``meta["feature_overwrites"]`` 供 lint/UI 提示。
- 引擎在執行前會把當前 DefectItem 放進 ``meta["_defect_item"]``、Dataset kind 放進
  ``meta["_dataset_kind"]``（Load 卡讀這兩個 key）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


class ContextError(RuntimeError):
    """步驟向 Context 要不存在的資源時拋出（訊息需列出現有 keys）。"""


@dataclass
class Context:
    images: Dict[str, np.ndarray] = field(default_factory=dict)
    rois: Optional[Any] = None            # adept.core.algo.roi.MultiROISet
    labels: Optional[np.ndarray] = None
    features: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    # ---- images -----------------------------------------------------------
    def require_image(self, key: str) -> np.ndarray:
        try:
            return self.images[key]
        except KeyError:
            raise ContextError(
                f"image stream '{key}' does not exist; available: "
                f"{sorted(self.images)}"
            ) from None

    def set_image(self, key: str, arr: np.ndarray) -> None:
        if not isinstance(arr, np.ndarray):
            raise ContextError(f"set_image('{key}') needs a numpy array, got "
                               f"{type(arr).__name__}")
        self.images[key] = arr

    # ---- features ---------------------------------------------------------
    def add_feature(self, name: str, value: Any) -> None:
        """寫入一個特徵值（強制轉 float；NaN/inf 允許，由表達式層做安全處理）。"""
        v = float(value)
        if name in self.features:
            self.meta.setdefault("feature_overwrites", []).append(name)
        self.features[name] = v

    def add_features(self, mapping: Dict[str, Any]) -> None:
        for k, v in mapping.items():
            self.add_feature(k, v)

    # ---- misc -------------------------------------------------------------
    @property
    def nm_per_px(self) -> Optional[float]:
        return self.meta.get("nm_per_px")

    def warn(self, msg: str) -> None:
        self.meta.setdefault("warnings", []).append(str(msg))

    def summary(self) -> Dict[str, Any]:
        """輕量摘要（不含像素資料），供 trace / debug 輸出。"""
        return {
            "images": {k: tuple(v.shape) for k, v in self.images.items()},
            "features": dict(self.features),
            "warnings": list(self.meta.get("warnings", [])),
        }
