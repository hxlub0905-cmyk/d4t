# d4t algorithm library — authored 2026-09-17 (F104).
"""二維自相關找峰：**交錯排列**（每隔一列錯半格）的 layout，投影法答不出來的那種。

投影法（`period.estimate_period`）把整張圖沿一軸取平均。交錯的 layout 上，相鄰兩列
的相位差半格，平均之後互相抵消 —— 實測合成的交錯晶格（32 × 24，隔列錯 16）：
投影法 X 軸**量不到週期**（回 None），Y 軸回 24，而真正的矩形重複單元是 32 × 48
（兩列才重複一次）。拿 24 去疊，兩列疊在一起就是一團糊。

二維自相關不投影：整張圖跟自己平移 ``(dx, dy)`` 之後有多像，是一張以 lag 為座標的
面。矩形重複單元就是這張面上**沿 X 軸**（dy = 0）與**沿 Y 軸**（dx = 0）離原點
最近的那個峰 —— 交錯的 layout 在 (16, 24) 也有峰，但那不在軸上，矩形單元用不到它。
實測：交錯 → 32 × 48；規則晶格與條紋 → 跟投影法一模一樣；純雜訊 → 沒有峰。

跟投影法的分工（`template.build_golden_cell`）
---------------------------------------------
兩個都算，**同意的時候不改任何東西**（黃金值不動）。只有兩種情況採用這一支：

* 投影法量不到那一軸、這一支量得到；
* 這一支量到的是投影法的**整數倍**（交錯的特徵：投影看到的是半格的重複）。

其餘一律照投影法 —— 它有諧波修正與四個月的實測，這一支才一天。

成本
----
FFT 自相關在中央 1536² 的視窗上 ~5 ms（合成 1000² 是 3 ms）；7680² 的圖只看中央
那一塊，週期超過視窗一半的 layout 本來就不是「重複」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

__all__ = ["Period2D", "estimate_period_2d", "MAX_SIDE", "FLAT_ABOVE"]

#: 只看中央這麼大的視窗（每邊）。
MAX_SIDE = 1536
#: 自相關軸線上 > 0.9 的比例超過這個＝那一軸是平的（條紋的另一軸）—— 沒有週期。
FLAT_ABOVE = 0.5
#: 峰要多高才算（相對於那條線上最高的峰；另有絕對下限 0.3）。
PEAK_REL = 0.5
PEAK_ABS = 0.3


@dataclass
class Period2D:
    """`estimate_period_2d` 的答案。``None`` ＝ 那一軸沒有週期（或平的）。"""

    px: Optional[int] = None
    py: Optional[int] = None
    confidence_x: float = 0.0      # 0–100，那個峰的自相關值
    confidence_y: float = 0.0
    flat_x: bool = False
    flat_y: bool = False
    warnings: List[str] = field(default_factory=list)


def _to_gray_f32(image: Any) -> np.ndarray:
    a = np.asarray(image)
    if a.ndim == 3:
        a = a.mean(axis=2)
    return a.astype(np.float32)


def autocorr2d(gray: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    """正規化的二維自相關（``[dy, dx]``，原點在 ``[0, 0]``，值 ≤ 1）。

    先減掉大尺度背景（高斯模糊當低通）：亮度漸層會讓整張面往一邊翹，軸線上的
    峰就分不出來。中央視窗、零均值、FFT。
    """
    g = np.asarray(gray, np.float32)
    h, w = g.shape[:2]
    hh, ww = min(h, int(max_side)), min(w, int(max_side))
    y0, x0 = (h - hh) // 2, (w - ww) // 2
    g = g[y0:y0 + hh, x0:x0 + ww]
    g = g - float(g.mean())
    sigma = max(3.0, min(hh, ww) / 16.0)
    g = g - cv2.GaussianBlur(g, (0, 0), sigma)
    spec = np.fft.rfft2(g)
    ac = np.fft.irfft2(np.abs(spec) ** 2, s=g.shape)
    return ac / max(float(ac[0, 0]), 1e-9)


def _axis_period(line: np.ndarray, lo: int) -> Tuple[Optional[int], float, bool]:
    """一條自相關軸線 → ``(週期, 信心 0–100, 平不平)``。

    取 lag ≥ ``lo`` 之後**第一個**夠高的局部極大（夠高 = 那條線上最高峰的一半，
    且 ≥ 0.3）。再做一次諧波修正：2p 的值明顯比 p 高，p 就是次諧波。
    """
    v = np.asarray(line, dtype=np.float64)
    n = v.size
    if n < lo + 3:
        return None, 0.0, False
    if float(np.mean(v[lo:] > 0.9)) > FLAT_ABOVE:
        return None, 0.0, True
    inner = v[lo:n - 1]
    idx = np.nonzero((inner >= v[lo - 1:n - 2]) & (inner >= v[lo + 1:n]))[0] + lo
    if idx.size == 0:
        return None, 0.0, False
    top = float(v[idx].max())
    thr = max(PEAK_ABS, PEAK_REL * top)
    good = idx[v[idx] >= thr]
    if good.size == 0:
        return None, 0.0, False
    p = int(good[0])
    if 2 * p < n and v[2 * p] > 1.15 * v[p]:
        p = 2 * p
    return p, float(np.clip(v[p], 0.0, 1.0)) * 100.0, False


def estimate_period_2d(image: Any, min_period: int = 4,
                       max_side: int = MAX_SIDE) -> Period2D:
    """矩形重複單元 ``(px, py)``：二維自相關沿 X 軸／Y 軸離原點最近的峰。"""
    g = _to_gray_f32(image)
    out = Period2D()
    if g.ndim != 2 or g.size == 0 or min(g.shape) < 2 * max(4, int(min_period)) + 3:
        out.warnings.append("the image is too small to look for a repeat")
        return out
    if float(g.std()) < 0.5:
        out.warnings.append("the image is flat; nothing repeats")
        return out
    ac = autocorr2d(g, max_side=max_side)
    h, w = ac.shape
    lo = max(2, int(min_period))
    out.px, out.confidence_x, out.flat_x = _axis_period(ac[0, :w // 2], lo)
    out.py, out.confidence_y, out.flat_y = _axis_period(ac[:h // 2, 0], lo)
    if out.px is None and out.py is None:
        out.warnings.append("no repeat found along either axis")
    return out
