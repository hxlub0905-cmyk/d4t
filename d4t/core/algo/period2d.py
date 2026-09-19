# d4t algorithm library — authored 2026-09-17 (F104).
"""二維自相關找峰：**交錯排列**（每隔一列錯半格）的 layout，投影法答不出來的那種。

投影法（`period.estimate_period`）把整張圖沿一軸取平均。交錯的 layout 上，相鄰兩列
的相位差半格，平均之後互相抵消 —— 實測合成的交錯晶格（32 × 24，隔列錯 16）：
投影法 X 軸**量不到週期**（回 None），Y 軸回 24，而真正的矩形重複單元是 32 × 48
（兩列才重複一次）。拿 24 去疊，兩列疊在一起就是一團糊。

二維自相關不投影：整張圖跟自己平移 ``(dx, dy)`` 之後有多像，是一張以 lag 為座標的
面。矩形重複單元就是這張面上**沿 X 軸**（dy = 0）與**沿 Y 軸**（dx = 0）離原點
最近的**夠高的**峰 —— 交錯的 layout 在 (16, 24) 也有峰，但那不在軸上，矩形單元用不到它。
實測：交錯 → 32 × 48；規則晶格與條紋 → 跟投影法一模一樣；純雜訊 → 沒有峰。

「夠高」是多高（F105，2026-09-17）
----------------------------------
F104 放的是「那條線上最高峰的一半」。一張真實的 3200 × 4000 大圖（交錯晶格、亮線
約 10 px 寬、人工驗證的單元 41 × 79.5）把它打穿了：X 軸線上的局部極大是
10.4（0.67）、20.7（0.61）、30.7（0.66）、41.0（0.92）—— 線寬造成的 10.4 那個峰
輕鬆過 0.46 的門檻，迴圈就停在 10；Y 軸同理停在 30。F104 的合成 fixture 沒有這種
強的子結構峰，所以這條路從來沒被走過。

現在門檻是最高峰的 **0.85**（`PEAK_REL`）：真的週期在環狀自相關上跟自己的諧波
幾乎等高（差的只是視窗衰減），而子結構、線寬、交錯的半格都明顯矮一截
（那張圖上 0.61–0.67 對 0.92；半格 0.60 對 0.825）。仍然取**最小的**那個 lag ——
不取 argmax，因為 p、2p、3p 等高時 argmax 是擲銅板。

峰找到之後再沿諧波鏈（p、2p、3p…各做三點拋物線）過原點最小平方一次，得到**次像素**
的週期（``px_sub``）：79.5 對 79 在 4000 px 上差 25 px，格線就是這樣「靠邊會滑」的。

半週期陷阱（`half_period_check`）
--------------------------------
交錯晶格上「錯半格」的平移跟真的週期幾乎一樣像（那張圖 0.908 對 0.941），投影法
一定回半週期、而它的 ``v[2p] > 1.15 v[p]`` 永遠不會觸發。所以仲裁之後再問一次
「量到的是不是真週期的一半」：沿軸比 ``ac[2q]`` 與 ``ac[q]``，前者高出 0.1 以上
就加倍。規則晶格上 q 與 2q 都是晶格點、只差衰減，0.1 的餘量就是它不亂開的原因。
交錯分數 ``ac[q/2, p/2] / ac[q, p]`` 從同一張面算出來給人看（交錯 ≈ 1、規則 ≈ 0）。

跟投影法的分工（`template.build_golden_cell`）
---------------------------------------------
兩個都算，**同意的時候不改任何東西**（黃金值不動）。只有兩種情況採用這一支：

* 投影法量不到那一軸、這一支量得到；
* 這一支量到的是投影法的**整數倍**（交錯的特徵：投影看到的是半格的重複）。

其餘一律照投影法 —— 它有諧波修正與四個月的實測，這一支才一天。

成本
----
FFT 自相關只看中央 1536² 的視窗；7680² 的圖只看中央那一塊，週期超過視窗一半的
layout 本來就不是「重複」。F105 補零到兩倍（線性自相關），沙盒實測 3200 × 4000 的
圖 0.6 s → 0.8 s（F104 的「~5 ms」是另一台機器上 1000² 合成圖的數字）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from . import period as algo_period

__all__ = ["Period2D", "HalfPeriodCheck", "estimate_period_2d", "half_period_check",
           "autocorr2d", "fmt_px", "MAX_SIDE", "FLAT_ABOVE", "PEAK_REL", "PEAK_ABS",
           "HALF_PERIOD_GAIN"]

#: 只看中央這麼大的視窗（每邊）。
MAX_SIDE = 1536
#: 自相關軸線上 > 0.9 的比例超過這個＝那一軸是平的（條紋的另一軸）—— 沒有週期。
FLAT_ABOVE = 0.5
#: 峰要多高才算（相對於那條線上最高的峰；另有絕對下限 0.3）。
#: F104 是 0.5，F105 改 0.85 —— 見模組說明「夠高是多高」。
PEAK_REL = 0.85
PEAK_ABS = 0.3
#: 半週期檢查：``ac[2q]`` 要比 ``ac[q]`` 高出這麼多才加倍（規則晶格上兩者只差衰減）。
HALF_PERIOD_GAIN = 0.1
#: 諧波鏈上任一個峰離直線超過這麼多像素 = 鏈不是直的（漂移／畸變），退回單峰。
CHAIN_RESIDUAL_PX = 0.5


@dataclass
class Period2D:
    """`estimate_period_2d` 的答案。``None`` ＝ 那一軸沒有週期（或平的）。"""

    px: Optional[int] = None
    py: Optional[int] = None
    #: 次像素的週期（諧波鏈擬合；F105）。``px`` 就是它四捨五入。
    px_sub: Optional[float] = None
    py_sub: Optional[float] = None
    confidence_x: float = 0.0      # 0–100，那個峰的自相關值
    confidence_y: float = 0.0
    flat_x: bool = False
    flat_y: bool = False
    warnings: List[str] = field(default_factory=list)
    #: 算過的那張自相關面（給 `half_period_check` 省一次 FFT；不進 repr／比較）。
    ac: Optional[np.ndarray] = field(default=None, repr=False, compare=False)


@dataclass
class HalfPeriodCheck:
    """`half_period_check` 的答案：（可能加倍了的）週期、每一軸的增益、交錯分數。"""

    px: float
    py: float
    #: ``ac[2p] - ac[p]``：正得夠多就是「量到的是一半」。沒看那一軸就是 0。
    gain_x: float = 0.0
    gain_y: float = 0.0
    doubled_x: bool = False
    doubled_y: bool = False
    #: ``ac[q/2, p/2] / ac[q, p]``：交錯（body-centred）≈ 1，規則晶格 ≈ 0。
    #: 兩軸都有週期才算得出來，否則 0。
    stagger: float = 0.0
    notes: List[str] = field(default_factory=list)


def fmt_px(v: float) -> str:
    """79.5 → ``"79.5"``、80.0 → ``"80"``（給人看的像素數；``%d`` 會安靜截斷小數）。"""
    f = float(v)
    if abs(f - round(f)) < 1e-6:
        return "%d" % int(round(f))
    return ("%.2f" % f).rstrip("0").rstrip(".")


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
    # **補零到兩倍 = 線性自相關，不是環狀的**（F105）。F104 是環狀的：視窗不是
    # 週期的整數倍時尾巴會繞回來拉歪每一個峰 —— 合成的 41 × 79.5 晶格在 800 px
    # 高的視窗上，四個 Y 諧波的次像素位置是 79.59、159.17、238.92、318.47
    # （真值 79.5、159、238.5、318），鏈擬合出 79.62；補零之後 79.509、159.003、
    # 238.511、318.004。整數 pitch 的 fixture 峰位置不變（本來就整除）。
    # 重疊面積歸一化讓遠 lag 的值不被三角形衰減壓低，平軸判定（> 0.9）才成立。
    spec = np.fft.rfft2(g, s=(2 * hh, 2 * ww))
    ac = np.fft.irfft2(np.abs(spec) ** 2, s=(2 * hh, 2 * ww))[:hh, :ww]
    overlap = np.outer(hh - np.arange(hh), ww - np.arange(ww)).astype(np.float64)
    ac = ac * (float(hh * ww) / overlap)
    return ac / max(float(ac[0, 0]), 1e-9)


def _local_maxima(v: np.ndarray, lo: int) -> np.ndarray:
    """lag ≥ ``lo`` 的局部極大（不含最後一點）。"""
    n = v.size
    inner = v[lo:n - 1]
    return np.nonzero((inner >= v[lo - 1:n - 2]) & (inner >= v[lo + 1:n]))[0] + lo


def _chain_fit(v: np.ndarray, peaks: np.ndarray, p0: int) -> Tuple[float, bool]:
    """沿諧波鏈 p0、2p0、3p0… 擬合次像素週期 → ``(週期, 鏈是直的嗎)``。

    每個諧波附近（``± max(2, min(3%, p0/3))``；不設上限的話 k ≥ 11 會吸到鄰近的
    諧波）取最近的局部極大做三點拋物線，連續兩個 k 找不到就停。過原點最小平方
    ``p = Σ k·lag / Σ k²`` —— 物理模型沒有截距，而精度在遠的諧波上。
    任一點離直線超過 ``CHAIN_RESIDUAL_PX`` 就退回 p0 自己的拋物線：那不是一條
    直線的鏈（漂移／畸變），硬擬合出來的斜率是假的。
    """
    n = v.size
    ks: List[float] = []
    lags: List[float] = []
    k, misses = 1, 0
    while k * p0 < n - 1 and misses < 2:
        target = k * p0
        tol = max(2.0, min(0.03 * target, p0 / 3.0))
        near = peaks[np.abs(peaks - target) <= tol]
        if near.size:
            best = int(near[np.argmin(np.abs(near - target))])
            lag, _val = algo_period._parabolic(v, best)
            ks.append(float(k))
            lags.append(float(lag))
            misses = 0
        else:
            misses += 1
        k += 1
    if not ks:
        return algo_period._parabolic(v, p0)[0], True
    ka, la = np.asarray(ks), np.asarray(lags)
    p = float((ka * la).sum() / (ka * ka).sum())
    if np.any(np.abs(la - ka * p) > CHAIN_RESIDUAL_PX):
        return algo_period._parabolic(v, p0)[0], False
    return p, True


def _axis_period(line: np.ndarray, lo: int
                 ) -> Tuple[Optional[int], Optional[float], float, bool, bool]:
    """一條自相關軸線 → ``(週期, 次像素週期, 信心 0–100, 平不平, 鏈直不直)``。

    取 lag ≥ ``lo`` 之後**最小的**夠高的局部極大（夠高 = 那條線上最高峰的
    ``PEAK_REL`` 倍，且 ≥ ``PEAK_ABS``），再沿諧波鏈擬合次像素的週期。
    F104 的 ``v[2p] > 1.15 v[p]`` 加倍規則拿掉了：門檻 0.85 之下它只可能在
    0.85–0.87 這一格觸發，等於死碼。
    """
    v = np.asarray(line, dtype=np.float64)
    n = v.size
    if n < lo + 3:
        return None, None, 0.0, False, True
    if float(np.mean(v[lo:] > 0.9)) > FLAT_ABOVE:
        return None, None, 0.0, True, True
    idx = _local_maxima(v, lo)
    if idx.size == 0:
        return None, None, 0.0, False, True
    top = float(v[idx].max())
    thr = max(PEAK_ABS, PEAK_REL * top)
    good = idx[v[idx] >= thr]
    if good.size == 0:
        return None, None, 0.0, False, True
    p0 = int(good[0])
    p_sub, straight = _chain_fit(v, idx, p0)
    conf = float(np.clip(v[p0], 0.0, 1.0)) * 100.0
    return int(round(p_sub)), float(p_sub), conf, False, straight


def _line_at(line: np.ndarray, lag: float) -> float:
    """軸線在小數 lag 上的值（線性內插）；超出範圍回 -1。"""
    if lag < 0 or lag > line.size - 1:
        return -1.0
    i0 = int(np.floor(lag))
    i1 = min(i0 + 1, line.size - 1)
    f = lag - i0
    return float((1.0 - f) * line[i0] + f * line[i1])


def _ac_at(ac: np.ndarray, dy: float, dx: float) -> float:
    """二維自相關面在小數 lag ``(dy, dx)`` 上的值（雙線性）；超出範圍回 -1。"""
    h, w = ac.shape
    if dy < 0 or dx < 0 or dy > h - 1 or dx > w - 1:
        return -1.0
    y0, x0 = int(np.floor(dy)), int(np.floor(dx))
    y1, x1 = min(y0 + 1, h - 1), min(x0 + 1, w - 1)
    fy, fx = dy - y0, dx - x0
    return float((1 - fy) * ((1 - fx) * ac[y0, x0] + fx * ac[y0, x1])
                 + fy * ((1 - fx) * ac[y1, x0] + fx * ac[y1, x1]))


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
    out.ac = ac
    h, w = ac.shape
    lo = max(2, int(min_period))
    out.px, out.px_sub, out.confidence_x, out.flat_x, ok_x = _axis_period(ac[0, :w // 2], lo)
    out.py, out.py_sub, out.confidence_y, out.flat_y, ok_y = _axis_period(ac[:h // 2, 0], lo)
    for axis, ok in (("across", ok_x), ("down", ok_y)):
        if not ok:
            out.warnings.append("the repeats %s do not line up on a straight "
                                "harmonic chain; the period was taken from the "
                                "first peak alone" % axis)
    if out.px is None and out.py is None:
        out.warnings.append("no repeat found along either axis")
    return out


def half_period_check(image: Any, px: float, py: float, *,
                      ac: Optional[np.ndarray] = None,
                      skip: Tuple[bool, bool] = (False, False),
                      max_side: int = MAX_SIDE) -> HalfPeriodCheck:
    """量到的 ``(px, py)`` 是不是真週期的**一半** → 該加倍的軸加倍（F105 報告 5.2）。

    沿軸比 ``ac[2q]`` 與 ``ac[q]``：交錯晶格上 q 是子列的間距、不是晶格向量，
    平移 q 之後只對到一半（那張圖 0.61），平移 2q 才整個對上（0.90）；規則晶格上
    兩個都是晶格點、只差衰減，所以要高出 ``HALF_PERIOD_GAIN`` 才算。不比聯合
    lag ``ac[q, p]``：q 不是晶格向量時它 ≈ ``ac[q, 0]``，只是多了雜訊。

    不看的軸：``skip`` 標的（使用者明講的週期一律相信）、沒量到的（< 2）、
    2q 超出視窗一半取不到的。兩軸各自獨立，所以一軸加倍不影響另一軸的判定。
    ABAB 兩列交替的 layout 會真的觸發 —— 那是對的，它的週期就是 2q。

    ``ac`` 可以把 `estimate_period_2d` 算過的那張傳進來省一次 FFT（1536² 是幾十 ms），
    也免得兩張視窗不一樣。交錯分數在加倍**之後**算、兩軸都有週期才算。
    """
    out = HalfPeriodCheck(px=float(px or 0.0), py=float(py or 0.0))
    if ac is None:
        g = _to_gray_f32(image)
        if g.ndim != 2 or g.size == 0 or min(g.shape) < 16 or float(g.std()) < 0.5:
            return out
        ac = autocorr2d(g, max_side=max_side)
    h, w = ac.shape
    lines = (ac[0, :w // 2], ac[:h // 2, 0])
    words = ("across", "down")
    periods = [out.px, out.py]
    gains = [0.0, 0.0]
    doubled = [False, False]
    for i in range(2):
        p = periods[i]
        line = lines[i]
        if skip[i] or p < 2.0 or 2.0 * p > line.size - 2:
            continue
        v1, v2 = _line_at(line, p), _line_at(line, 2.0 * p)
        gains[i] = v2 - v1
        if v2 >= PEAK_ABS and v2 - v1 >= HALF_PERIOD_GAIN:
            # 加倍之後把峰對準：2p 附近最近的局部極大做三點拋物線
            peaks = _local_maxima(np.asarray(line, np.float64), 2)
            new = 2.0 * p
            if peaks.size:
                near = peaks[np.abs(peaks - 2.0 * p) <= max(2.0, 0.03 * 2.0 * p)]
                if near.size:
                    best = int(near[np.argmin(np.abs(near - 2.0 * p))])
                    new = float(algo_period._parabolic(np.asarray(line, np.float64), best)[0])
            out.notes.append("the period %s was doubled after the half-period "
                             "check (%s → %s px); rows are probably staggered"
                             % (words[i], fmt_px(p), fmt_px(new)))
            periods[i] = new
            doubled[i] = True
    out.px, out.py = periods[0], periods[1]
    out.gain_x, out.gain_y = gains[0], gains[1]
    out.doubled_x, out.doubled_y = doubled[0], doubled[1]
    if out.px >= 2.0 and out.py >= 2.0 and out.py <= h // 2 - 1 and out.px <= w // 2 - 1:
        full = _ac_at(ac, out.py, out.px)
        half = _ac_at(ac, out.py / 2.0, out.px / 2.0)
        if full > 1e-6:
            out.stagger = float(max(0.0, half) / full)
    return out
