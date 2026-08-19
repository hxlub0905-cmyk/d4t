# d4t algorithm module — authored 2026-07-29 (F7-8).
"""Tone curve 求值：控制點 → 查表 → 套用到影像。

單調三次 Hermite（Fritsch–Carlson）
-----------------------------------
控制點之間用**保單調**的三次插值，不是直線也不是自然三次樣條：

* 直線：拉三個點就看得到折角，而 gamma 曲線本來就該是平滑的；
* 自然三次樣條：會 overshoot —— 使用者把中間點往上拉，曲線可能在旁邊
  先往下凹一段。對「調亮」這個意圖來說那是錯的，而且在影像上會直接看到
  一圈假的暗環。

Fritsch–Carlson 限制斜率，保證「控制點單調上升 → 曲線也單調上升」。
沒有 scipy —— 這是廠內離線機，相依愈少愈好（`docs/OFFLINE-INSTALL.md`）。

UI 的曲線編輯器畫的就是 :func:`curve_lut` 的輸出，所以**畫面上看到的線就是
影像上套的線**（WYSIWYG，不是各畫各的）。
"""
from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from ..pipeline.curve import parse_curve

__all__ = ["curve_lut", "eval_curve", "apply_curve_01"]

Point = Tuple[float, float]

#: LUT 的取樣數。256 對 uint8 是一格一階；float 影像也夠細
#: （再細的差異會被下游的 diff/量測吃掉）。
LUT_SIZE = 256


def eval_curve(points: Sequence[Point], xs: np.ndarray) -> np.ndarray:
    """在 ``xs``（0–1）上求曲線值，回傳同 shape 的 float64（已夾在 0–1）。"""
    pts = [(float(x), float(y)) for x, y in points]
    x = np.asarray([p[0] for p in pts], dtype=np.float64)
    y = np.asarray([p[1] for p in pts], dtype=np.float64)
    n = x.size
    if n < 2:
        return np.clip(np.asarray(xs, dtype=np.float64), 0.0, 1.0)

    h = np.diff(x)
    delta = np.diff(y) / h                      # 各段割線斜率

    # 端點取單邊割線、內點取兩側平均，再用 Fritsch–Carlson 收斂到保單調的範圍
    m = np.empty(n, dtype=np.float64)
    m[0] = delta[0]
    m[-1] = delta[-1]
    if n > 2:
        m[1:-1] = (delta[:-1] + delta[1:]) / 2.0
    for i in range(n - 1):
        if delta[i] == 0.0:                     # 平段：兩端斜率都必須是 0
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / delta[i], m[i + 1] / delta[i]
        s = a * a + b * b
        if s > 9.0:                             # 落在單調區之外 → 等比例縮回來
            t = 3.0 / float(np.sqrt(s))
            m[i] = t * a * delta[i]
            m[i + 1] = t * b * delta[i]

    q = np.clip(np.asarray(xs, dtype=np.float64), 0.0, 1.0)
    idx = np.clip(np.searchsorted(x, q, side="right") - 1, 0, n - 2)
    hi = h[idx]
    t = (q - x[idx]) / hi
    t2, t3 = t * t, t * t * t
    out = ((2 * t3 - 3 * t2 + 1) * y[idx]
           + (t3 - 2 * t2 + t) * hi * m[idx]
           + (-2 * t3 + 3 * t2) * y[idx + 1]
           + (t3 - t2) * hi * m[idx + 1])
    return np.clip(out, 0.0, 1.0)


def curve_lut(curve, size: int = LUT_SIZE) -> np.ndarray:
    """曲線（字串或控制點）→ ``size`` 個等距取樣的查表（float64，0–1）。"""
    pts = parse_curve(curve) if isinstance(curve, str) else list(curve)
    n = max(2, int(size))
    return eval_curve(pts, np.linspace(0.0, 1.0, n))


def apply_curve_01(x01: np.ndarray, curve, size: int = LUT_SIZE) -> np.ndarray:
    """把已經正規化到 0–1 的陣列套上曲線。

    走 LUT + ``np.interp`` 而不是每個像素解一次 Hermite ——
    一張 128² patch 只要 256 次多項式求值，其餘是一次線性內插。
    """
    lut = curve_lut(curve, size)
    grid = np.linspace(0.0, 1.0, lut.size)
    return np.interp(np.clip(x01, 0.0, 1.0), grid, lut)
