# ADEPT step-card library — authored 2026-07-29 (F7-7).
"""tone — 亮度／對比／gamma 調整卡（Enhance 段）。

跟 ``normalize.py`` 的差別（很重要，不要混用）
---------------------------------------------
* ``percentile_norm`` / ``glv_mask_norm`` 是**自動**的：從影像自己算出範圍再拉伸，
  目的是「把兩張圖變成可以比」。
* 這一檔是**手動**的：使用者直接指定要加多少亮度、拉多少對比、套什麼 gamma。
  目的是「讓我看得清楚 / 讓後面的量測落在好用的數值範圍」。

兩者都可以用，順序也隨意 —— 但如果流程裡已經有正規化卡，通常手動調整要放在
它**之後**，否則正規化會把你剛調的東西再拉回去。

為什麼 gamma 值得一張卡
-----------------------
SEM 的暗部細節常常擠在低灰階區。gamma < 1 會把暗部拉開、gamma > 1 壓暗部拉亮部，
這是線性的亮度／對比做不到的 —— 它對灰階是**非線性**重分佈。

運算一律在 float 上做、最後夾回原本的數值範圍：uint8 進 uint8 出，float 進 float 出
（下游的 diff 是 float32，這條規則讓這張卡插在哪裡都不會偷偷改變型別）。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, register_step,
)
from ._util import parse_key_list, require_image

__all__ = ["BrightnessContrastStep", "GammaStep", "apply_brightness_contrast",
           "apply_gamma"]


def _value_range(arr: np.ndarray) -> tuple:
    """這個陣列該被夾在什麼範圍：uint8 -> (0,255)，float -> 依實際內容。

    float 影像（例如 diff）可能有負值，硬夾成 0–255 會把資訊剪掉，
    所以浮點一律保留原本的動態範圍。
    """
    if arr.dtype == np.uint8:
        return 0.0, 255.0
    lo = float(np.nanmin(arr)) if arr.size else 0.0
    hi = float(np.nanmax(arr)) if arr.size else 1.0
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return 0.0, 1.0
    return lo, hi


def apply_brightness_contrast(img: np.ndarray, brightness: float,
                              contrast: float) -> np.ndarray:
    """``out = (img - mid) * contrast + mid + brightness``，繞著中灰旋轉。

    對比以**影像自己的中間值**為支點，不是以 0 為支點 —— 以 0 為支點的話
    拉對比會同時把整張圖變亮，使用者得再回頭調亮度，很難用。
    ``brightness`` 的單位是「原始灰階」（uint8 就是 0–255 的刻度）。
    """
    out = img.astype(np.float64, copy=False)
    lo, hi = _value_range(img)
    mid = (lo + hi) / 2.0
    out = (out - mid) * float(contrast) + mid + float(brightness)
    out = np.clip(out, lo, hi)
    return out.astype(img.dtype, copy=False)


def apply_gamma(img: np.ndarray, gamma: float) -> np.ndarray:
    """先正規化到 0–1、套 ``x ** (1/gamma)``、再映射回原範圍。

    習慣用法：``gamma < 1`` 壓亮部、拉開暗部細節（SEM 常用）；
    ``gamma > 1`` 相反。``gamma == 1`` 原樣回傳。
    """
    g = float(gamma)
    if g <= 0 or g == 1.0:
        return img
    lo, hi = _value_range(img)
    span = hi - lo
    if span <= 0:
        return img
    x = (img.astype(np.float64, copy=False) - lo) / span
    x = np.clip(x, 0.0, 1.0) ** (1.0 / g)
    return (x * span + lo).astype(img.dtype, copy=False)


class _ToneStep(Step):
    """共用：主影像流 + ``also_apply``（同 normalize 卡的慣例）。"""

    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def _targets(cls, params: Dict[str, Any]) -> List[str]:
        keys = [str(params.get("target", "test"))]
        keys += parse_key_list(params.get("also_apply", ""))
        seen, out = set(), []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return cls._targets(params)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return cls._targets(params)

    def _apply_each(self, ctx: Context, params: Dict[str, Any], fn) -> Context:
        primary = str(params.get("target", "test"))
        require_image(ctx, self.key, primary)          # 主流不存在才算錯
        for key in self._targets(params):
            img = ctx.images.get(key)
            if img is None:
                ctx.warn(f"[{self.key}] also_apply stream '{key}' does not "
                         f"exist; skipped.")
                continue
            ctx.set_image(key, fn(img))
        return ctx


@register_step
class BrightnessContrastStep(_ToneStep):
    """手動亮度 / 對比。"""

    key = "brightness_contrast"
    label = "Brightness / Contrast"
    help = ("Manually shift brightness and stretch contrast, so faint defects "
            "become easier to see and to measure.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  help="Main image stream to adjust (overwritten in place)."),
        ParamSpec(name="also_apply", type="str", default="ref",
                  help=("Other image streams to apply the same adjustment to "
                        "(comma separated, may be empty). Keep test and ref "
                        "together or they stop being comparable.")),
        ParamSpec(name="brightness", type="float", default=0.0,
                  min=-255.0, max=255.0,
                  help=("Added to every pixel, in gray levels. Positive "
                        "brightens, negative darkens; 0 leaves it alone.")),
        ParamSpec(name="contrast", type="float", default=1.0,
                  min=0.0, max=10.0,
                  help=("Contrast multiplier around mid gray. 1 = unchanged, "
                        "2 = twice the spread, 0.5 = half.")),
    ]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        b, c = float(p["brightness"]), float(p["contrast"])
        return self._apply_each(
            ctx, p, lambda im: apply_brightness_contrast(im, b, c))


@register_step
class GammaStep(_ToneStep):
    """Gamma 校正（非線性重分佈灰階）。"""

    key = "gamma"
    label = "Gamma"
    help = ("Redistribute gray levels non-linearly: below 1 opens up dark "
            "detail, above 1 pushes it down. Linear brightness and contrast "
            "cannot do this.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  help="Main image stream to adjust (overwritten in place)."),
        ParamSpec(name="also_apply", type="str", default="ref",
                  help=("Other image streams to apply the same gamma to "
                        "(comma separated, may be empty). Keep test and ref "
                        "together or they stop being comparable.")),
        ParamSpec(name="gamma", type="float", default=1.0, min=0.1, max=5.0,
                  help=("Below 1 brings out detail in the dark areas (common "
                        "for SEM); above 1 does the opposite. 1 = unchanged.")),
    ]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        g = float(p["gamma"])
        return self._apply_each(ctx, p, lambda im: apply_gamma(im, g))
