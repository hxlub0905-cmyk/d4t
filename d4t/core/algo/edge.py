# d4t algorithm library — authored 2026-08-21 (F19).
"""edge — 一條剖面上的次像素邊緣定位與配對。**CD「有方向」那一半的數學。**

無方向的那一半（顆粒／孔洞：門檻切割、Feret、面積）住 :mod:`d4t.core.algo.shape`。
分法不是隨意的：**這裡吃一條剖面，那裡吃一塊區域。** 兩支共用三樣東西 ——
:func:`threshold_level`（門檻的高度）、:func:`profile_noise`（雜訊）與
:func:`edge_quality`（品質），所以 ``cd_edge_score`` 在兩支之間仍然可以互相比較。

為什麼原子單位是「一條量測線」，不是「一個區域」
------------------------------------------------
以前 CD 量的是區域的 bounding box。bbox 是**極值統計量** —— 邊界上任何一顆離群
像素 100% 傳進答案，而且圖再大、雜訊平均得再好都不會改善（它的變異數不隨樣本數
下降）。對一個要拿去跟門檻比大小、逐顆比較的量測，那是結構性的問題。

換成「一條線量一個寬度、N 條線收成一個分布」之後：

* 平均是 CD，而 **σ 就是 LWR** —— 粗糙度不是另外加的功能，是同一趟的副產品；
* ``min`` 是頸縮、``max`` 是橋接，而**殺死良率的是最窄的那一段**，不是平均；
* 兩條邊**各自**的 σ 是 LER。兩邊一起晃（LER 有、LWR 沒有）是載台或對位在漂，
  各自晃才是結構本身粗糙 —— 這兩個不同的製程故障，bbox 那條路連問都問不出來。

三個判準（``criterion``）—— 以及一個被實測推翻的預設
-----------------------------------------------------
邊在哪裡沒有唯一的答案 —— **CD 是操作型定義**，數字取決於判準。所以判準是使用者
選的，而且卡片會把「實際用了哪一個」記下來。

===================  ==========================================
判準                 怎麼定位
===================  ==========================================
``threshold``（預設） 局部平台的 ``frac`` 高度處線性內插（50% 是業界慣例）
``gradient``          |梯度| 峰值的二次內插（＝反曲點）
``fit``               整段爬升線性化後**加權**最小平方擬合一條 erf
===================  ==========================================

⚠ **設計時主張的預設是 ``fit``，實測把它推翻了。** 當時的推論是「穿越法只吃跨過
門檻的兩顆像素（誤差 ≈ σ/斜率），擬合吃整段爬升（≈ σ/斜率/√N）」。那個推論在
這個問題上不成立，量出來是這樣（真值 12.00 px、雜訊 σ=5、400 次；
完整的表見 ``tests/test_algo_edge.py::test_criterion_noise_table``）：

============  ==================  ==================  ==================
邊的糊度      ``threshold``       ``gradient``        ``fit``
============  ==================  ==================  ==================
blur 1.0      +0.024 / **0.119**  **+0.002** / 0.118  +0.049 / 0.127
blur 1.5      +0.059 / **0.151**  **+0.006** / 0.225  +0.084 / 0.152
============  ==================  ==================  ==================

（格式：偏差 / 標準差，單位 px）

兩個原因，都是量出來才知道的：

1. **預設的 1 px 平滑已經替穿越法做完了雜訊平均。** 擬合想賺的那個 √N，平滑器
   先賺走了；關掉平滑（``smooth=0``）兩者的 σ 一起變差，擬合也沒有變好。
2. **單邊 erf 模型在有限寬度的線上會被隔壁那條邊污染。** 爬升段的內側樣本裡摻
   了另一條邊的尾巴，於是擬合看到的曲線提早飽和，位置被往外拉 —— 那就是
   ``fit`` 那一欄偏差恆為正的來源。50% 穿越點落在爬升的正中間，污染最小。

所以預設是 ``threshold``（σ 最小），而 ``gradient`` 是**偏差**最小的那一個：
對稱的平滑不會移動反曲點，所以它是唯一在 ``smooth`` 開大時仍然不偏的判準
（實測 ``smooth=2.0``：threshold +0.295、fit +0.355、gradient −0.001）。
要跨批次比絕對 CD 的時候選它。

**這一段留著不刪，是因為「當初為什麼那樣想」跟「後來量到什麼」一樣重要** ——
下一個人很可能會再推論一次同樣的 √N，然後再改一次預設。

``fit`` 怎麼做（沒有 scipy）
----------------------------
不迭代。先由平台估出 ``lo`` / ``hi``，把爬升段正規化成 ``u = (I−lo)/(hi−lo)``，
再用 ``erfinv(2u−1) = (x − pos) / (√2·blur)`` 把 S 形拉成**直線**，對它做一次
加權最小平方（權重見 :func:`_refine_fit`）—— 位置是回歸係數，閉式解。

樣本不足 3 個（很銳的邊本來就只有一兩個過渡像素）就**退回 ``threshold``**，
並在 :class:`EdgePoint` 的 ``method`` 上講出來 —— 退回不是失敗，但它不該是隱形的。

``open_edge``：畫面邊界不是一條邊
---------------------------------
patch 是以缺陷為中心裁切的，結構被切掉一半是常態。一側找不到邊的時候，正確的
行為是**拒絕量並講出來**，不是拿框或畫面當成那條邊 —— 後者會吐出一個等於區域
寬度的數字，看起來完全正常（重做之前的那張卡正是如此，見計畫書 §Context）。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

from .subpixel import gaussian_filter1d

__all__ = [
    "CRITERIA", "TARGETS", "AXES", "AXIS_X", "AXIS_Y", "MIN_QUALITY",
    "EdgePoint", "ScanLine", "ScanResult",
    "find_edges", "pair_across", "measure_line", "scan", "choose_axis",
    # 兩支共用的三個（見模組說明）
    "threshold_level", "profile_noise", "edge_quality",
]

#: 邊界判準。順序 = UI 下拉的順序（預設在最前面）。
CRITERIA = ("threshold", "gradient", "fit")

#: 要量的是亮的那條結構還是暗的那條 —— 這問的是**樣品**，不是軟體。
TARGETS = ("auto", "bright", "dark")

AXIS_X = "x"
AXIS_Y = "y"
#: ``auto`` 由 :func:`choose_axis` 決定，不會出現在 :class:`ScanResult` 裡
#: （那裡一定是已經決定好的 x 或 y —— 「自動選了什麼」要吐成一個數字）。
AXES = ("auto", AXIS_X, AXIS_Y)

#: ``fit`` 只用正規化強度落在這一段的樣本（見模組說明）。放得比直覺寬，是因為
#: 回歸有加權（見 :func:`_refine_fit`）—— 遠端樣本自己的份量就很小了。
FIT_CORE = (0.02, 0.98)

#: 候選邊至少要有這麼陡（相對於這條剖面上最陡的地方）。
_REL_GRAD = 0.35

#: 對比的絕對地板（GLV）。合成的無雜訊影像上任何一點起伏都會變成「一條邊」，
#: 而 1 GLV 是量化的下限 —— 同 `F11` 給 ``hot_pixels`` 門檻加地板的理由。
_MIN_CONTRAST = 1.0

#: :func:`edge_quality` 的分母權重（見那支函式）。
_QUALITY_K = 4.0

#: 一條邊至少要有這個品質分才算數（``品質 = 對比/(對比 + 4×雜訊)``，
#: 所以 0.5 等於「對比至少是雜訊的四倍」）。
#:
#: ⚠ **這個地板不能只用絕對 GLV。** 第一版只有 :data:`_MIN_CONTRAST`（1 GLV），
#: 而候選邊的門檻是「這條線上最陡的地方的 35%」—— 在一條**完全沒有結構、只有
#: 雜訊**的線上，最陡的地方就是最大的那一顆雜訊，於是 35% 之上有一堆「邊」，
#: 配得出對子、量得出寬度。實測：拿合成 lot 的 diff（一顆小 blob ＋ 雜訊）去量，
#: 128 條線裡有 128 條「成功」，真缺陷與假點都吐出 8–10 px 的寬度 ——
#: 跑得完、有數字、每一顆都有、而且量的是雜訊。
_MIN_QUALITY = 0.5

#: 給卡片當預設值用的公開名字（引擎說有哪些，卡片說預設是多少）。
MIN_QUALITY = _MIN_QUALITY


class EdgePoint(NamedTuple):
    """一條剖面上的一條邊。

    ``reason`` 是 ``""`` 表示成功；非空的那些**不會**進到配對裡。
    ``method`` 是**實際**用到的判準 —— ``fit`` 在樣本不足時會退回
    ``threshold``，而那件事不該只有寫這段程式的人知道。
    """

    pos: float
    #: ``+1`` = 由暗轉亮，``-1`` = 由亮轉暗（沿剖面由左往右看）。
    polarity: int
    #: 這條邊兩側平台的高度差（GLV，恆正）。
    contrast: float
    #: 邊有多糊（px，erf 的 σ），由 20–80% 上升距離量 —— **三個判準都有**。
    blur: float
    #: 0..1，見 :func:`edge_quality`。
    quality: float
    reason: str
    method: str


class ScanLine(NamedTuple):
    """一條量測線的結果。``reason`` 非空 = 這一條不計入任何統計量。"""

    index: int
    #: 沿**堆疊**軸的位置（block 座標，一格的中心）。
    offset: float
    #: 邊 A / 邊 B 沿**量測**軸的位置（block 座標）。失敗時是 ``nan``。
    a: float
    b: float
    width: float
    quality: float
    reason: str
    #: 這一條線量到的是亮的還是暗的那一條（``target="auto"`` 時**逐條**決定）。
    target: str = ""


class ScanResult(NamedTuple):
    """一個區域掃完的全部結果 —— **畫得出來所需要的一切都在裡面**。

    面板要畫的（每條線的位置、找到的邊、代表那一條的剖面）與引擎要算的（寬度的
    分布）是同一份東西，所以「使用者看到的」跟「數字算出來的」不會走鐘 ——
    這是 `algo/profile.ProfileResult` 立下的規矩。
    """

    axis: str
    target: str
    lines: List[ScanLine]
    #: 只含成功的那些（跟 ``lines`` 不等長）。
    widths: np.ndarray
    a_positions: np.ndarray
    b_positions: np.ndarray
    offsets: np.ndarray
    #: 失敗碼 → 幾條線。成功的那些不在裡面。
    reasons: Dict[str, int]
    #: 有幾條邊的 ``fit`` 退回了 ``threshold``。
    fallbacks: int
    #: 代表那一條線（寬度取中位數的那一條）在 ``lines`` 裡的索引；沒有就是 ``-1``。
    median_line: int
    #: 代表那一條線的剖面取樣值（畫剖面圖用）。
    profile: Optional[np.ndarray]
    #: ``threshold`` 判準在代表那一條線上的水平線高度（畫圖用）；其他判準是 ``None``。
    level: Optional[float]


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _erfinv(y: np.ndarray) -> np.ndarray:
    """``erf`` 的反函數（Winitzki 近似，相對誤差約 2e-3）。

    為什麼是近似就夠：它的下游是一條**對十來個帶雜訊的樣本**做的回歸，而那些
    樣本的雜訊比這個近似大兩三個數量級。numpy 沒有 ``erfinv``，scipy 不在
    相依裡（stdlib-only，見 `AGENTS.md`）。
    """
    a = 0.147
    y = np.clip(np.asarray(y, dtype=np.float64), -0.999999, 0.999999)
    ln = np.log(1.0 - y * y)
    t = 2.0 / (math.pi * a) + ln / 2.0
    return np.sign(y) * np.sqrt(np.sqrt(t * t - ln / a) - t)


def _mad(values: np.ndarray) -> float:
    """中位數絕對離差（耐離群的散布量）。"""
    v = np.asarray(values, dtype=np.float64).ravel()
    if v.size == 0:
        return 0.0
    return float(np.median(np.abs(v - np.median(v))))


def profile_noise(raw: np.ndarray) -> float:
    """這條剖面的雜訊 σ（GLV），由**一階差分**估計。

    為什麼不用平台自己的 MAD（第一版的做法）：一條 10 px 的線，內側「平台」其實
    還在爬升，MAD 量到的是**訊號**不是雜訊 —— 於是完全乾淨的合成影像也只拿到
    0.88 的品質分。差分把任何**平滑**的成分消掉，留下的才是逐點跳動的那一份；
    ``/√2`` 是因為相鄰兩點的差含兩份獨立雜訊。

    用**原始**剖面而不是平滑過的：平滑會把雜訊壓下去，那時候量到的是「平滑器有
    多強」，不是「這張圖有多吵」。
    """
    v = np.asarray(raw, dtype=np.float64).ravel()
    if v.size < 3:
        return 0.0
    return float(1.4826 * _mad(np.diff(v)) / math.sqrt(2.0))


def edge_quality(contrast: float, noise: float) -> float:
    """這條邊有多可信：``對比 / (對比 + k×雜訊)``，夾在 0..1。

    **整個 repo 只有這一份定義**（同一個名字在不同地方算出不同的東西，是這裡
    最怕的那種錯）。雜訊為 0 時是 1；對比等於 k 倍雜訊時是 0.5。
    三個判準共用它，所以 ``cd_edge_score`` 換判準之後仍然可以互相比較。
    """
    c = max(0.0, float(contrast))
    n = max(0.0, float(noise))
    if c <= 0.0:
        return 0.0
    return float(min(1.0, c / (c + _QUALITY_K * n)))


def _plateaus(profile: np.ndarray, peak: int, left_half: int,
              right_half: int) -> Tuple[float, float]:
    """邊兩側的平台高度 ``(left, right)``。

    只取**外側**那一段（離邊 ``half/3`` 以外）—— 靠近邊的樣本正在爬升，把它們
    算進平台會讓對比被低估，而對比是門檻與品質共用的分母。

    兩側的半寬**分開給**，因為它們被隔壁那條邊限制的程度不一樣（見
    :func:`find_edges` 的 ``_neighbour_halves``）：一條 6 px 寬的線，兩條邊
    相距 6，而預設視窗是 9 —— 左邊的「右側平台」會整個越過右邊那條邊，取到的
    是**背景**而不是線的內部。對比因此被低估，門檻的高度就跟著錯，而它吐出來的
    仍然是一個看起來很正常的寬度（實測 6.0 量成 7.9）。
    """
    n = int(profile.size)
    inner_l = max(1, left_half // 3)
    inner_r = max(1, right_half // 3)
    lo_seg = profile[max(0, peak - left_half):max(1, peak - inner_l + 1)]
    hi_seg = profile[min(n - 1, peak + inner_r):min(n, peak + right_half + 1)]
    if lo_seg.size == 0:
        lo_seg = profile[:1]
    if hi_seg.size == 0:
        hi_seg = profile[-1:]
    return float(np.median(lo_seg)), float(np.median(hi_seg))


def _local_maxima(mag: np.ndarray, thresh: float) -> List[int]:
    """``mag`` 上超過 ``thresh`` 的局部極大值索引（兩端不算）。"""
    out: List[int] = []
    for i in range(1, int(mag.size) - 1):
        v = mag[i]
        if v >= thresh and v >= mag[i - 1] and v > mag[i + 1]:
            out.append(i)
    return out


def _neighbour_halves(peaks: Sequence[int], i: int, half: int) -> Tuple[int, int]:
    """第 ``i`` 條邊的視窗半寬 ``(左, 右)`` —— **不准跨過隔壁那條邊**。

    兩條邊之間的樣本一人一半（``//2``）。不夾住的話，一條 6 px 寬的線在預設
    視窗 9 之下，左邊那條邊的「右側平台」會取到線**外面**的背景，於是對比被
    低估、門檻的高度跟著錯 —— 而吐出來的仍然是一個看起來正常的寬度。

    地板是 2：平台至少要有一個樣本，否則對比恆為 0，整條邊會被當成平的丟掉。
    """
    peak = int(peaks[i])
    left = half if i == 0 else max(2, (peak - int(peaks[i - 1])) // 2)
    right = (half if i == len(peaks) - 1
             else max(2, (int(peaks[i + 1]) - peak) // 2))
    return min(half, left), min(half, right)


def _parabola(y0: float, y1: float, y2: float) -> float:
    """三點拋物線頂點相對中間那一點的位移（夾在 ±1）。"""
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (y0 - y2) / denom, -1.0, 1.0))


# --------------------------------------------------------------------------- #
# 三個判準
# --------------------------------------------------------------------------- #
def threshold_level(lo: float, hi: float, frac: float) -> float:
    """門檻的高度：**一律從暗算到亮**，跟掃描方向無關。

    ⚠ 這裡是整張卡最容易寫錯的一行，而寫錯了完全看不出來。第一版是
    ``lo + frac×(hi−lo)``，也就是「從**左邊**那個平台算起」—— 於是一條亮線的
    左邊（上升）邊量在 25% 高度，右邊（下降）邊量在 75% 高度。兩條邊因此**同向**
    移動，寬度紋風不動：實測 ``threshold_pct`` 從 25 拉到 75，量出來的寬度是
    12.2348106481077 對 12.234810648107693 —— 一個**看起來有在動、實際上完全沒
    作用的旋鈕**，而且它每一顆都吐得出正常的數字。

    改成由暗到亮之後，這個參數的意思是一句畫得出來的話：0% 貼著暗的那一側、
    100% 貼著亮的那一側。亮線拉高會變窄、暗溝拉高會變寬，兩者都是單調的。

    **只有這一份定義** —— 找邊、畫在面板上的那條橫線、量糊度的 20/80 都走它。
    """
    dark, bright = (lo, hi) if lo <= hi else (hi, lo)
    return float(dark + frac * (bright - dark))


def _refine_threshold(profile: np.ndarray, peak: int, left_half: int,
                      right_half: int, lo: float, hi: float,
                      frac: float) -> Optional[float]:
    """:func:`threshold_level` 的穿越點（離 ``peak`` 最近的那一個）。

    ``lo`` / ``hi`` 是**這條邊自己的**局部平台，不是整條剖面的 min/max ——
    全域的話，剖面上任何一顆最亮的雜訊像素會把每一條邊都移動一點點。
    """
    level = threshold_level(lo, hi, frac)
    n = int(profile.size)
    left, right = max(0, peak - left_half), min(n - 1, peak + right_half)
    best: Optional[float] = None
    for i in range(left, right):
        y0, y1 = float(profile[i]), float(profile[i + 1])
        if (y0 - level) * (y1 - level) > 0.0:
            continue                       # 這一段沒有跨過門檻
        if abs(y1 - y0) < 1e-12:
            pos = float(i)
        else:
            pos = i + (level - y0) / (y1 - y0)
        if best is None or abs(pos - peak) < abs(best - peak):
            best = pos
    return best


#: 20–80% 上升距離換算成 erf 的 σ 的係數：``Δx = 2·erfinv(0.6)·√2·σ``。
_RISE_TO_BLUR = 1.0 / (2.0 * 0.5951160 * math.sqrt(2.0))


def _edge_blur(profile: np.ndarray, peak: int, left_half: int, right_half: int,
               lo: float, hi: float) -> float:
    """這條邊有多糊（px，換算成 erf 的 σ），由 **20–80% 上升距離**量。

    為什麼不是從 ``fit`` 的回歸係數拿（第一版的做法）：那樣只有選了 ``fit``
    的人才有這個數字，而「邊糊不糊」是**這張影像的性質**，跟使用者挑了哪個判準
    無關 —— 同一條邊在三個判準下該糊得一樣多。兩個穿越點是閉式解，也不必多跑
    一次擬合。

    ⚠ 量到的糊度**含平滑器那一份**（``smooth`` 越大越糊），因為它量的是
    「進到判準裡的那條曲線」長什麼樣 —— 那正是位置誤差真正取決於的東西。
    """
    p20 = _refine_threshold(profile, peak, left_half, right_half, lo, hi, 0.2)
    p80 = _refine_threshold(profile, peak, left_half, right_half, lo, hi, 0.8)
    if p20 is None or p80 is None:
        return 0.0
    return float(abs(p80 - p20) * _RISE_TO_BLUR)


def _refine_gradient(mag: np.ndarray, peak: int) -> float:
    """|梯度| 峰值的二次內插。"""
    if peak <= 0 or peak >= int(mag.size) - 1:
        return float(peak)
    return peak + _parabola(float(mag[peak - 1]), float(mag[peak]),
                            float(mag[peak + 1]))


def _refine_fit(profile: np.ndarray, peak: int, left_half: int,
                right_half: int, lo: float, hi: float
                ) -> Optional[Tuple[float, float]]:
    """erf 線性化最小平方 → ``(pos, blur)``；樣本不足回 ``None``。

    ``erfinv(2u−1) = (x − pos)/(√2·blur)`` 對 ``x`` 是一條直線，所以整段爬升
    只要一次回歸就同時給出位置與模糊度 —— 不迭代、沒有初始值的問題。
    """
    span = float(hi - lo)
    if abs(span) < 1e-9:
        return None
    n = int(profile.size)
    left, right = max(0, peak - left_half), min(n, peak + right_half + 1)
    xs = np.arange(left, right, dtype=np.float64)
    u = (profile[left:right].astype(np.float64) - lo) / span
    core = (u > FIT_CORE[0]) & (u < FIT_CORE[1])
    if int(np.count_nonzero(core)) < 3:
        return None                        # 很銳的邊 —— 呼叫端退回 threshold
    xs, u = xs[core], u[core]
    z = _erfinv(2.0 * u - 1.0)
    # z = (x - pos) / (√2·blur)  →  對 x 回歸，slope = 1/(√2·blur)
    #
    # **一定要加權。** ``erfinv`` 的斜率在 u→0 與 u→1 是無窮大，所以爬升兩端的
    # 一點點雜訊被放大成很大的 z 誤差。等權重回歸等於讓最不可信的樣本說話最大聲
    # —— 實測（見計畫書的表）等權重版本的 σ 跟 threshold 一樣，也就是「用整段
    # 爬升換 √N」那個唯一的理由整個不見了。
    #
    # 權重 = 1/σ_z，而 σ_z = σ_u·dz/du，其中 du/dz = exp(−z²)/√π ——
    # 常數在最小平方裡會約掉，所以 ``w = exp(−z²)`` 就是答案。
    # 有了權重之後 :data:`FIT_CORE` 才敢放寬：遠端的樣本自己就沒有份量了。
    slope, intercept = np.polyfit(xs, z, 1, w=np.exp(-z * z))
    if not np.isfinite(slope) or abs(slope) < 1e-9:
        return None
    pos = float(-intercept / slope)
    blur = float(abs(1.0 / (slope * math.sqrt(2.0))))
    if not (np.isfinite(pos) and np.isfinite(blur)):
        return None
    if pos < left - 1.0 or pos > right:
        return None                        # 回歸把邊丟到視窗外了
    return pos, blur


# --------------------------------------------------------------------------- #
# 找邊
# --------------------------------------------------------------------------- #
def find_edges(profile: Any, criterion: str = "threshold", threshold_frac: float = 0.5,
               window: int = 9, smooth: float = 1.0,
               min_contrast: float = _MIN_CONTRAST,
               min_quality: float = _MIN_QUALITY) -> List[EdgePoint]:
    """一條剖面上的所有邊（由左而右）。

    ``window`` 是每條邊的**局部視窗半寬**（px）：平台從它的外側取、擬合在它裡面
    做。太小會量不到平台，太大會把隔壁的結構算進來。
    """
    prof = np.asarray(profile, dtype=np.float64).ravel()
    if prof.size < 5:
        return []
    noise = profile_noise(prof)           # **原始**的那一份，見那支函式
    work = gaussian_filter1d(prof, smooth) if smooth > 0 else prof
    grad = np.gradient(work)
    mag = np.abs(grad)
    peak_max = float(mag.max()) if mag.size else 0.0
    if peak_max <= 0.0:
        return []
    half = max(2, int(window))
    peaks = _local_maxima(mag, _REL_GRAD * peak_max)
    out: List[EdgePoint] = []
    for i, peak in enumerate(peaks):
        left_half, right_half = _neighbour_halves(peaks, i, half)
        lo, hi = _plateaus(work, peak, left_half, right_half)
        contrast = abs(hi - lo)
        polarity = 1 if hi >= lo else -1
        if contrast < max(min_contrast, 0.0):
            continue                       # 平的地方不是邊
        quality = edge_quality(contrast, noise)
        if quality < min_quality:
            continue                       # 雜訊裡的起伏不是邊（見 _MIN_QUALITY）
        blur = _edge_blur(work, peak, left_half, right_half, lo, hi)
        pos: Optional[float] = None
        method = criterion
        if criterion == "fit":
            got = _refine_fit(work, peak, left_half, right_half, lo, hi)
            if got is not None:
                pos = got[0]
            else:
                method = "threshold"       # 退回，而且看得出來退了
                pos = _refine_threshold(work, peak, left_half, right_half,
                                        lo, hi, threshold_frac)
        elif criterion == "threshold":
            pos = _refine_threshold(work, peak, left_half, right_half,
                                    lo, hi, threshold_frac)
        elif criterion == "gradient":
            pos = _refine_gradient(mag, peak)
        else:
            raise ValueError("unknown criterion %r; one of %s"
                             % (criterion, list(CRITERIA)))
        if pos is None or not np.isfinite(pos):
            out.append(EdgePoint(float(peak), polarity, contrast, blur,
                                 quality, "fit_failed", method))
            continue
        out.append(EdgePoint(float(pos), polarity, contrast, blur, quality,
                             "", method))
    return out


# --------------------------------------------------------------------------- #
# 配對
# --------------------------------------------------------------------------- #
def _pair_one(edges: Sequence[EdgePoint], anchor: float,
              want_left: int) -> Optional[Tuple[EdgePoint, EdgePoint]]:
    """錨點兩側各找**第一條**極性正確的邊。"""
    left = [e for e in edges if e.pos <= anchor and e.polarity == want_left]
    right = [e for e in edges if e.pos > anchor and e.polarity == -want_left]
    if not left or not right:
        return None
    return max(left, key=lambda e: e.pos), min(right, key=lambda e: e.pos)


def pair_across(edges: Sequence[EdgePoint], anchor: float,
                target: str = "auto") -> Tuple[Optional[EdgePoint],
                                               Optional[EdgePoint], str, str]:
    """把錨點所在的那個結構包起來的兩條邊 → ``(a, b, reason, target_used)``。

    亮的結構 = 左邊由暗轉亮（``+1``）、右邊由亮轉暗（``-1``）；暗的相反。

    ``auto`` 兩種都試，取**較窄**的那一組 —— 兩種都配得出來時，內側那一個才是
    錨點所在的結構，外側那個是包著它的那一層。

    一側找得到、另一側找不到 = ``open_edge``：**結構被畫面或框切掉了**，
    而拿那條邊界當成邊會吐出一個看起來完全正常的假數字（見模組說明）。
    """
    good = [e for e in edges if not e.reason]
    if not good:
        return None, None, "flat_profile", target
    if target == "bright":
        wants = [(1, "bright")]
    elif target == "dark":
        wants = [(-1, "dark")]
    else:
        wants = [(1, "bright"), (-1, "dark")]

    best: Optional[Tuple[EdgePoint, EdgePoint]] = None
    best_name = target
    half_open = False
    for want_left, name in wants:
        got = _pair_one(good, anchor, want_left)
        if got is None:
            # 這個極性有沒有「一側有、一側沒有」？那是結構被切掉，不是沒有結構。
            side_l = any(e.pos <= anchor and e.polarity == want_left for e in good)
            side_r = any(e.pos > anchor and e.polarity == -want_left for e in good)
            half_open = half_open or (side_l != side_r)
            continue
        if best is None or (got[1].pos - got[0].pos) < (best[1].pos - best[0].pos):
            best, best_name = got, name
    if best is None:
        return None, None, ("open_edge" if half_open else "no_pair"), target
    return best[0], best[1], "", best_name


def measure_line(profile: Any, anchor: Optional[float] = None,
                 criterion: str = "threshold", target: str = "auto",
                 threshold_frac: float = 0.5, window: int = 9,
                 smooth: float = 1.0, min_contrast: float = _MIN_CONTRAST,
                 min_quality: float = _MIN_QUALITY
                 ) -> Tuple[Optional[EdgePoint], Optional[EdgePoint], str, str]:
    """一條剖面 → 一組邊（:func:`find_edges` ＋ :func:`pair_across`）。"""
    prof = np.asarray(profile, dtype=np.float64).ravel()
    if anchor is None:
        anchor = (prof.size - 1) / 2.0
    edges = find_edges(prof, criterion=criterion, threshold_frac=threshold_frac,
                       window=window, smooth=smooth, min_contrast=min_contrast,
                       min_quality=min_quality)
    return pair_across(edges, float(anchor), target)


# --------------------------------------------------------------------------- #
# 掃一個區域
# --------------------------------------------------------------------------- #
def choose_axis(block: Any, smooth: float = 1.0) -> Tuple[str, float, float]:
    """自動選方向 → ``(axis, score_x, score_y)``：轉折訊號比較強的那一軸。

    分數是「投影曲線上最陡的地方相對於它自己的散布」，兩軸用同一把尺。
    **呼叫端一定要把選出來的方向吐成一個特徵**（`cd_axis_deg`）—— 方向若在整批
    裡逐顆翻轉，那一欄 CSV 混著兩種不同的量測，而除了那個數字之外沒有任何線索。
    """
    arr = np.asarray(block, dtype=np.float64)
    if arr.ndim != 2 or arr.size == 0:
        return AXIS_X, 0.0, 0.0

    def _score(profile: np.ndarray) -> float:
        """這條投影曲線上最陡的地方有多陡（GLV / px）。

        ⚠ 不要拿它除以曲線自己的散布 —— 那會**獎勵平坦**：完全沒有結構的那一軸
        散布趨近 0，分數就趨近無窮大，於是方向永遠選錯（第一版正是如此）。
        絕對值是對的尺：沿著結構方向平均會把邊保下來，跨過結構方向平均會把邊
        抹平，而這個數字直接量的就是那件事。兩軸都是平均出來的，單位相同。
        """
        if profile.size < 5:
            return 0.0
        work = gaussian_filter1d(profile, smooth) if smooth > 0 else profile
        if float(np.ptp(work)) < _MIN_CONTRAST:
            return 0.0
        return float(np.abs(np.gradient(work)).max())

    # 沿 X 量 → 看的是**每一欄**的平均組成的曲線（垂直的邊界在這條曲線上最陡）。
    score_x = _score(arr.mean(axis=0))
    score_y = _score(arr.mean(axis=1))
    return (AXIS_X if score_x >= score_y else AXIS_Y), score_x, score_y


def scan(block: Any, axis: str = AXIS_X, criterion: str = "threshold",
         target: str = "auto", threshold_frac: float = 0.5, window: int = 9,
         smooth: float = 1.0, line_step: int = 1, line_bin: int = 1,
         min_contrast: float = _MIN_CONTRAST, min_quality: float = _MIN_QUALITY,
         max_lines: int = 512) -> ScanResult:
    """在一塊已經裁好的影像上鋪量測線，每條量一個寬度。

    ``axis="x"`` = 沿 X 量、沿 Y 堆疊（一列一條）。``"y"`` 走轉置，同一份程式碼
    —— 兩個方向各寫一份的話，兩份遲早會不一樣。

    ``line_bin`` 把相鄰幾列平均起來再量：**降雜訊，但也把粗糙度抹掉**
    （相鄰列的起伏被平均掉了），所以預設是 1，而且卡片的 help 要講明這件事。

    ``max_lines`` 只是效能上限；砍掉的話 ``reasons["too_many"]`` 會講出來 ——
    安靜的截斷會讓「量了全部」與「量了前 512 條」在畫面上長得一模一樣。
    """
    arr = np.asarray(block, dtype=np.float64)
    if arr.ndim != 2 or arr.size == 0:
        return ScanResult(axis, target, [], np.empty(0), np.empty(0),
                          np.empty(0), np.empty(0), {"empty": 1}, 0, -1, None, None)
    work = arr.T if axis == AXIS_Y else arr
    n_lines_avail, n_cols = work.shape
    step = max(1, int(line_step))
    bin_ = max(1, int(line_bin))
    anchor = (n_cols - 1) / 2.0

    starts = list(range(0, max(1, n_lines_avail - bin_ + 1), step))
    reasons: Dict[str, int] = {}
    if len(starts) > max_lines:
        reasons["too_many"] = len(starts) - max_lines
        starts = starts[:max_lines]

    lines: List[ScanLine] = []
    fallbacks = 0
    for i, start in enumerate(starts):
        rows = work[start:start + bin_]
        profile = rows.mean(axis=0) if bin_ > 1 else rows[0]
        offset = start + (bin_ - 1) / 2.0
        edges = find_edges(profile, criterion=criterion,
                           threshold_frac=threshold_frac, window=window,
                           smooth=smooth, min_contrast=min_contrast,
                           min_quality=min_quality)
        fallbacks += sum(1 for e in edges if not e.reason and e.method != criterion)
        a, b, reason, used = pair_across(edges, anchor, target)
        if reason or a is None or b is None:
            reasons[reason] = reasons.get(reason, 0) + 1
            lines.append(ScanLine(i, offset, float("nan"), float("nan"),
                                  float("nan"), 0.0, reason, ""))
            continue
        lines.append(ScanLine(i, offset, a.pos, b.pos, b.pos - a.pos,
                              min(a.quality, b.quality), "", used))

    ok = [ln for ln in lines if not ln.reason]
    widths = np.array([ln.width for ln in ok], dtype=np.float64)
    a_pos = np.array([ln.a for ln in ok], dtype=np.float64)
    b_pos = np.array([ln.b for ln in ok], dtype=np.float64)
    offsets = np.array([ln.offset for ln in ok], dtype=np.float64)

    median_line, profile_out, level = -1, None, None
    if ok:
        # 代表那一條 = 寬度最接近中位數的那一條（不是平均那一條 —— 平均可能
        # 落在兩條線之間，而面板上要畫的是**真的量過**的一條）。
        target_w = float(np.median(widths))
        pick = min(ok, key=lambda ln: abs(ln.width - target_w))
        median_line = pick.index
        start = starts[pick.index]
        rows = work[start:start + bin_]
        profile_out = (rows.mean(axis=0) if bin_ > 1 else rows[0]).astype(np.float64)
        if criterion == "threshold":
            smoothed = (gaussian_filter1d(profile_out, smooth) if smooth > 0
                        else profile_out)
            # 畫在圖上的那條橫線用**左邊那條邊**的平台算 —— 它就是這張圖上
            # 「判準判在哪個高度」那條線，而使用者要對照的正是左邊那個交點。
            peak = int(np.clip(round(pick.a), 0, int(smoothed.size) - 1))
            span = max(2, min(int(window), int(round(abs(pick.b - pick.a))) // 2))
            lo, hi = _plateaus(smoothed, peak, int(window), span)
            level = threshold_level(lo, hi, threshold_frac)
    return ScanResult(axis, target, lines, widths, a_pos, b_pos, offsets,
                      reasons, fallbacks, median_line, profile_out, level)
