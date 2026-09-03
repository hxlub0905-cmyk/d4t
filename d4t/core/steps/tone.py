# d4t step-card library — authored 2026-07-29 (F7-7); merged into one card 2026-07-30 (F7-20).
"""tone —— **一張** Adjust tone 卡：亮度／對比／gamma／曲線／反相。

為什麼是一張卡而不是三張
------------------------
Brightness/Contrast、Gamma/Curve、Invert 全都是**同一件事**：拿一條轉移曲線
把灰階重新映射，逐像素、跟鄰居無關。它們在卡片庫佔三列，但使用者的問題只有
一個 ——「我要把這張圖調得看得清楚一點」。

跟 ``normalize.py`` 的 ``method`` 下拉不同，這裡**不是四選一**：亮度、gamma、
反相是可以**同時**做的，而且常常要同時做（先提亮、再拉暗部、最後反相）。
所以它們是同一張卡上的幾個旋鈕，全部預設不作用（0 / 1 / 恆等曲線 / 關）。
`gamma` 卡本來就是這個形狀（gamma 與 curve 兩個旋鈕一個結果），這一輪只是把
另外兩張也收進來。

**套用順序固定：亮度/對比 → gamma 或曲線 → 反相。** 順序不可調 ——
可調的話同一組數字會有六種結果，而畫面上看不出來是哪一種。要別的順序就放兩張卡
（那時候順序在畫布上看得見）。

跟 ``normalize.py`` 的差別（很重要，不要混用）
---------------------------------------------
* ``normalize`` 是**自動**的：從影像自己算出範圍再拉伸，目的是「把兩張圖變成
  可以比」。
* 這一檔是**手動**的：使用者直接指定要加多少亮度、套什麼 gamma。目的是
  「讓我看得清楚 / 讓後面的量測落在好用的數值範圍」。

兩者都可以用，但如果流程裡已經有正規化卡，通常手動調整要放在它**之後**，
否則正規化會把你剛調的東西再拉回去。

為什麼 gamma 要留一個旋鈕
-------------------------
SEM 的暗部細節常常擠在低灰階區。gamma < 1 會把暗部拉開、gamma > 1 壓暗部拉亮部，
這是線性的亮度／對比做不到的 —— 它對灰階是**非線性**重分佈。

運算一律在 float 上做、最後夾回原本的數值範圍：uint8 進 uint8 出，float 進 float 出
（下游的 diff 是 float32，這條規則讓這張卡插在哪裡都不會偷偷改變型別）。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo.curve import apply_curve_01
from ..pipeline.context import Context
from ..pipeline.curve import IDENTITY, is_identity, parse_curve
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, register_step,
)
from ._util import MultiStreamStep, streams_spec

__all__ = ["ToneStep", "apply_brightness_contrast", "apply_gamma",
           "apply_curve", "apply_invert"]


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


def apply_curve(img: np.ndarray, curve) -> np.ndarray:
    """套用自訂色調曲線（控制點字串或 ``[(x, y), …]``）。

    跟 :func:`apply_gamma` 走完全相同的正規化 / 反正規化流程 ——
    差別只在中間那條轉移函數是使用者自己拉的，而不是 ``x ** (1/gamma)``。
    所以兩者可以互換，換過去不會連帶改變亮度基準或數值型別。
    """
    pts = parse_curve(curve) if isinstance(curve, str) else list(curve)
    if is_identity(pts):
        return img
    lo, hi = _value_range(img)
    span = hi - lo
    if span <= 0:
        return img
    x = (img.astype(np.float64, copy=False) - lo) / span
    return (apply_curve_01(x, pts) * span + lo).astype(img.dtype, copy=False)


def apply_invert(img: np.ndarray) -> np.ndarray:
    """亮暗顛倒。uint8：``255-x``；落在 [0,1] 的浮點：``1-x``；其餘浮點：``255-x``。

    浮點分兩種是刻意的：``diff`` 這類流可能是 0–255 的浮點，也可能是 0–1 的
    正規化結果，而「反相」對兩者的正確答案不同。判斷用實際的數值範圍，
    不是用 dtype。
    """
    if img.dtype == np.uint8:
        return (255 - img).astype(np.uint8)
    f = img.astype(np.float32)
    if f.size > 0 and float(f.min()) >= 0.0 and float(f.max()) <= 1.5:
        return (1.0 - np.clip(f, 0.0, 1.0)).astype(np.float32)
    return (255.0 - np.clip(f, 0.0, 255.0)).astype(np.float32)


@register_step
class ToneStep(MultiStreamStep):
    """手動色調調整：亮度／對比／gamma／曲線／反相，一張卡。

    幾個旋鈕、一個結果
    ------------------
    每個旋鈕的預設值都是「不作用」，所以只調你要的那個。順序固定
    **亮度/對比 → gamma 或曲線 → 反相**（見模組 docstring）。

    **曲線一旦不是 y=x 就完全接手，gamma 被忽略。** 選「兩個都套」會很難
    debug：使用者把曲線拉平了卻還是暗，因為 gamma 還壓在那裡。
    這條規則寫在 ``curve`` 的 help 裡，UI 也會在曲線生效時把 gamma 那列調淡。
    """

    key = "tone"
    label = "Adjust tone"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Manually adjust brightness, contrast, gamma or a custom curve, "
            "and optionally flip bright and dark - so faint defects become "
            "easier to see and to measure.")
    params = [
        streams_spec("test"),
        ParamSpec(name="brightness", type="float", default=0.0,
                  min=-255.0, max=255.0, label="Brightness",
                  help=("Added to every pixel, in gray levels. Positive "
                        "brightens, negative darkens; 0 leaves it alone.")),
        ParamSpec(name="contrast", type="float", default=1.0,
                  min=0.0, max=10.0, label="Contrast",
                  help=("Contrast multiplier around mid gray. 1 = unchanged, "
                        "2 = twice the spread, 0.5 = half.")),
        ParamSpec(name="gamma", type="float", default=1.0, min=0.1, max=5.0,
                  label="Gamma",
                  help=("Below 1 brings out detail in the dark areas (common "
                        "for SEM); above 1 does the opposite. 1 = unchanged.")),
        ParamSpec(name="curve", type="curve", default=IDENTITY,
                  label="Custom curve",
                  help=("Custom tone curve: input gray level across, output "
                        "up. Drag a point to bend it. While it is a straight "
                        "y = x line the gamma slider above is used instead; "
                        "as soon as you bend it, the curve takes over.")),
        ParamSpec(name="invert", type="bool", default=False, label="Invert",
                  help=("Flip bright and dark, so dark defects become bright "
                        "signal for the steps that follow. Applied last, "
                        "after everything above.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    def build_op(self, ctx: Context, p: Dict[str, Any]):
        b, c = float(p["brightness"]), float(p["contrast"])
        pts = parse_curve(p["curve"])
        curved = not is_identity(pts)
        g = float(p["gamma"])
        inv = bool(p["invert"])

        def op(img: np.ndarray) -> np.ndarray:
            out = img
            if b != 0.0 or c != 1.0:
                out = apply_brightness_contrast(out, b, c)
            if curved:
                out = apply_curve(out, pts)
            elif g != 1.0:
                out = apply_gamma(out, g)
            if inv:
                out = apply_invert(out)
            return out

        return op
