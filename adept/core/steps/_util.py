# ADEPT step-card library — authored 2026-07-28 (M1).
"""步驟卡片共用的小工具（非卡片；不註冊任何 step）。

- ``require_image``  向 Context 要影像，缺流時轉成白話 StepError。
- ``to_uint8``       把任何灰階陣列安全轉成 uint8 0–255（[0,1] 浮點自動 ×255）。
- ``parse_key_list`` 逗號字串 → 影像流 key 清單（去空白、忽略空項）。
- ``ensure_gray``    彩色（3 通道）輸入自動轉灰階。
"""
from __future__ import annotations

from typing import List

import cv2
import numpy as np

from ..pipeline.context import Context, ContextError
from ..pipeline.step import StepError


def require_image(ctx: Context, step_key: str, key: str) -> np.ndarray:
    """取出影像流；不存在時拋白話 StepError（不讓 ContextError 直接外洩）。"""
    try:
        return ctx.require_image(key)
    except ContextError as e:
        raise StepError(step_key, f"missing image stream '{key}' ({e})") from None


def ensure_gray(arr: np.ndarray) -> np.ndarray:
    """彩色影像轉單通道灰階；灰階原樣回傳。"""
    a = np.asarray(arr)
    if a.ndim == 3:
        if a.shape[2] == 4:
            return cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    return a


def to_uint8(arr: np.ndarray) -> np.ndarray:
    """任何灰階陣列 → uint8 0–255。

    - uint8 原樣回傳。
    - 浮點且值域看起來是 [0, 1] → ×255。
    - 其他（float 0–255、uint16 已是 0–255 值域…）→ clip 到 0–255 後轉型。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return a
    f = a.astype(np.float32)
    if f.size > 0:
        fmax = float(f.max())
        fmin = float(f.min())
        if 0.0 <= fmin and fmax <= 1.5:
            f = f * 255.0
    return np.clip(f, 0, 255).astype(np.uint8)


def parse_key_list(raw: str) -> List[str]:
    """逗號分隔字串 → key 清單；空白與空項自動忽略。"""
    if not raw:
        return []
    return [tok.strip() for tok in str(raw).split(",") if tok.strip()]
