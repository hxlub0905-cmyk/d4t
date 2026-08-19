# d4t algorithm library — authored 2026-07-29 (F7-11).
"""一維投影定位：把影像壓成一條曲線，在曲線上找「轉折」，轉折之間就是一段結構。

為什麼是找轉折，不是分材質
--------------------------
最初的想法是「EPI 暗、MG 中等、交界最亮 → 分三種灰階」。那對某一種 layout 是
對的，但這個工具是泛用的：換一個 layer 就不是三種、也不一定誰亮誰暗，而且灰階
本來就會隨機台與曝光漂移。**用絕對灰階分類，等於把一份 recipe 綁死在一種 layout
和一台機台上。**

轉折（曲線上斜率大的地方）沒有這個問題：它只問「哪裡在變」，不問「變成什麼」。
幾種材質、誰亮誰暗都不用先知道，而使用者只要回答一個對任何 layout 都成立的
問題 —— **「我要哪一段」**（包含中心的那一段、最寬的那一段、從左邊數第幾段）。

為什麼在 ref 上做
------------------
test 上有一顆缺陷正在破壞結構，拿它找結構等於讓缺陷去干擾定位。ref 沒有缺陷，
而且成對的 patch 本來就對齊，所以在 ref 上找到的位置直接可以用在 test 上。
（這是卡片的預設值，不是這個模組的事 —— 這裡只管算。）

什麼時候會失敗（很重要）
------------------------
patch 通常比一個重複單元還小，所以有些 patch 整張都落在同一種材質裡面，
曲線是平的。那種 patch **不可能**定位 —— 它裡面就是沒有可以辨識的東西，
這是資訊不夠，不是演算法不夠。

但那種 patch 也**不需要**定位：整張都是同一種材質，整張量就是對的。
所以 :func:`locate` 回報的 ``confidence`` 是給呼叫端做這個判斷用的 ——
低於門檻就退回整張圖，並且**把那顆標記出來**，不要安靜地用一個沒對準的框去量。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np

__all__ = ["ProfileResult", "projection", "profile_confidence",
           "find_transitions", "bands_from", "pick_band", "locate",
           "distance_to_nearest_transition", "AXIS_X", "AXIS_Y", "PICK_RULES"]

#: ``axis="x"`` = 沿著 X 走的曲線（每一**欄**一個值），用來找垂直的結構邊界。
AXIS_X = "x"
AXIS_Y = "y"

#: 「我要哪一段」的規則。對任何 layout 都成立，不需要先知道有幾種材質。
PICK_RULES = ("center", "widest", "darkest", "brightest", "index")

#: 「最陡的地方」至少要比「一般的地方」陡幾倍，才算這條曲線上有邊界。
#: 見 :func:`find_transitions` 裡的說明與實測數字。
_MIN_PEAK_RATIO = 1.2


@dataclass
class ProfileResult:
    """一次定位的完整結果 —— 包含**畫得出來**所需要的一切。

    UI 的 panel 直接吃這個 dataclass（曲線、轉折線、選中的段），
    所以「使用者看到的」跟「引擎算出來的」保證是同一份東西，不會兩邊走鐘。
    """

    axis: str
    profile: np.ndarray                     # 平滑後的曲線（畫出來的就是這條）
    raw: np.ndarray                         # 平滑前的曲線（淡色畫在後面當對照）
    transitions: List[int] = field(default_factory=list)
    bands: List[Tuple[int, int]] = field(default_factory=list)   # [start, end)
    picked: Optional[Tuple[int, int]] = None
    confidence: float = 0.0
    #: 影像中心落在第幾段（畫 panel 時要標出來；找不到 = -1）
    center_band: int = -1

    @property
    def length(self) -> int:
        return int(self.profile.size)


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    """一維移動平均。雜訊不先壓掉的話，梯度上到處都是假的轉折。"""
    w = max(1, int(window))
    if w <= 1 or values.size == 0:
        return values.astype(np.float32, copy=True)
    if w % 2 == 0:
        w += 1
    pad = w // 2
    padded = np.pad(values.astype(np.float32), pad, mode="edge")
    kernel = np.ones(w, dtype=np.float32) / float(w)
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def projection(img: Any, axis: str = AXIS_X, smooth: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """把影像壓成一條曲線。回傳 ``(平滑後, 原始)``。

    ``axis="x"``：每一欄取平均（曲線長度 = 影像寬度），用來找**垂直**的邊界。
    ``axis="y"``：每一列取平均，用來找水平的邊界。

    取**平均**而不是中位數是刻意的：這裡要的是「材質的整體亮度」，
    而缺陷只佔一欄裡的幾個像素，對平均的影響很小；反而中位數會把
    「一欄裡有一半是另一種材質」這種真實的轉折壓掉。
    """
    a = np.asarray(img, dtype=np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.ndim != 2 or a.size == 0:
        empty = np.zeros(0, dtype=np.float32)
        return empty, empty
    raw = a.mean(axis=0) if str(axis) == AXIS_X else a.mean(axis=1)
    return _smooth(raw, smooth), raw.astype(np.float32)


def profile_confidence(smoothed: np.ndarray, raw: np.ndarray) -> float:
    """「這條曲線上有多少是真的結構，而不是雜訊」。

    定義是 ``曲線的起伏 / 雜訊的尺度``：分子取平滑後曲線的標準差，
    分母取「平滑前減平滑後」的**穩健**尺度（MAD，不是標準差）。

    為什麼分母要用 MAD
    ------------------
    銳利的邊界會讓平滑吃掉一點真訊號，那幾格的殘差很大。用標準差當分母，
    邊界越銳利、分母被灌得越大 —— 結果是「結構越清楚、信心越低」，完全相反。
    MAD 只看中位數附近，那幾格灌不進去。

    量過的實際數字（合成與真實 patch 都試過）：整張同一種材質約 **0.7**，
    任何有結構的情況都在 **20 以上**，中間差了一個數量級 ——
    所以門檻放在個位數就分得很開，不需要逐個 layer 調。

    注意它問的**不是**「有沒有邊界」，是「有沒有訊號」。一片平緩的亮度漸層
    信心也會很高（那確實是訊號），但它一條邊界都沒有 ——
    那種情況由「找不到轉折」那條路處理，而漸層本身該交給 Enhance 的
    背景平坦化卡去除。
    """
    sm = np.asarray(smoothed, dtype=np.float32)
    rw = np.asarray(raw, dtype=np.float32)
    if sm.size == 0 or rw.size != sm.size:
        return 0.0
    resid = rw - sm
    med = float(np.median(resid))
    mad = 1.4826 * float(np.median(np.abs(resid - med)))
    return float(np.std(sm)) / max(mad, 1e-6)


def find_transitions(profile: np.ndarray, sensitivity: float = 0.35,
                     min_gap: int = 4) -> List[int]:
    """找曲線上的轉折（回傳位置清單）。

    ``sensitivity`` 0–1：要多陡才算一個轉折，**相對於這條曲線上最陡的地方**。
    用相對值而不是絕對灰階，是為了讓同一個設定換一個 layer、換一台機台還能用。

    ``min_gap`` 是兩個轉折至少要隔多遠（像素）—— 一個邊界在梯度上會佔好幾格，
    沒有這個的話一條邊界會被算成好幾條。

    局部極大用的是 ``g[i] > g[i-1]``（嚴格大於）而不是 ``>=``：一段**固定斜率**
    的漸層上每一格的梯度都相等，用 ``>=`` 會把整段都判成轉折。
    """
    p = np.asarray(profile, dtype=np.float32)
    if p.size < 3:
        return []
    grad = np.abs(np.gradient(p))
    peak = float(grad.max())
    if peak <= 0.0:
        return []

    # 「最陡的地方」必須真的比「一般的地方」陡，否則這條曲線上根本沒有邊界。
    # 固定斜率的漸層每一格梯度都相等（比值 = 1.00），剩下的差異只是浮點誤差 ——
    # 沒有這一關的話，浮點誤差會決定邊界畫在哪，而且每一格都會被判成邊界。
    # 量過的比值：漸層 1.00、正弦 1.41、方波 極大 —— 門檻放 1.2 兩邊都安全。
    if peak < _MIN_PEAK_RATIO * max(float(np.median(grad)), 1e-9):
        return []

    thr = float(np.clip(sensitivity, 0.0, 1.0)) * peak
    gap = max(1, int(min_gap))

    cand = [i for i in range(1, p.size - 1)
            if grad[i] >= thr and grad[i] > grad[i - 1] and grad[i] >= grad[i + 1]]
    cand.sort(key=lambda i: -grad[i])       # 強的先佔位
    kept: List[int] = []
    for i in cand:
        if all(abs(i - j) >= gap for j in kept):
            kept.append(i)
    return sorted(kept)


def bands_from(transitions: List[int], length: int) -> List[Tuple[int, int]]:
    """轉折之間就是一段。影像的兩端也算邊界（半段仍然是段）。"""
    if length <= 0:
        return []
    edges = [0] + [int(t) for t in sorted(transitions) if 0 < int(t) < length] + [int(length)]
    out: List[Tuple[int, int]] = []
    for a, b in zip(edges, edges[1:]):
        if b > a:
            out.append((int(a), int(b)))
    return out


def _band_level(profile: np.ndarray, band: Tuple[int, int]) -> float:
    a, b = band
    seg = profile[a:b]
    return float(seg.mean()) if seg.size else 0.0


def pick_band(bands: List[Tuple[int, int]], profile: np.ndarray,
              rule: str = "center", index: int = 0) -> Optional[Tuple[int, int]]:
    """依規則挑一段。``center`` 是預設 —— 缺陷永遠在 patch 正中央。"""
    if not bands:
        return None
    rule = str(rule)
    if rule == "widest":
        return max(bands, key=lambda b: b[1] - b[0])
    if rule == "darkest":
        return min(bands, key=lambda b: _band_level(profile, b))
    if rule == "brightest":
        return max(bands, key=lambda b: _band_level(profile, b))
    if rule == "index":
        i = int(index)
        return bands[i] if -len(bands) <= i < len(bands) else None
    mid = profile.size / 2.0            # center（預設）
    for a, b in bands:
        if a <= mid < b:
            return (a, b)
    return None


def locate(img: Any, axis: str = AXIS_X, sensitivity: float = 0.35,
           smooth: int = 3, min_gap: int = 4, rule: str = "center",
           index: int = 0) -> ProfileResult:
    """一次做完：投影 → 找轉折 → 分段 → 挑一段。

    這是 step 卡與 UI panel 共用的唯一入口 —— 兩邊看到的必須是同一次計算，
    不然「畫面上的框」跟「真的量下去的框」會不一樣，而那種 bug 很難發現。
    """
    prof, raw = projection(img, axis=axis, smooth=smooth)
    if prof.size == 0:
        return ProfileResult(axis=str(axis), profile=prof, raw=raw)

    trans = find_transitions(prof, sensitivity=sensitivity, min_gap=min_gap)
    conf = profile_confidence(prof, raw)
    bands = bands_from(trans, int(prof.size))
    picked = pick_band(bands, prof, rule=rule, index=index)

    mid = prof.size / 2.0
    center_band = next((i for i, (a, b) in enumerate(bands) if a <= mid < b), -1)
    return ProfileResult(axis=str(axis), profile=prof, raw=raw,
                         transitions=trans, bands=bands, picked=picked,
                         confidence=float(conf), center_band=center_band)


def distance_to_nearest_transition(res: ProfileResult) -> float:
    """影像中心（= 缺陷）離最近的一條轉折有多遠，單位是像素。

    這個數字本身就是一個特徵：缺陷落在結構正中間，跟落在兩種材質的交界上，
    通常不是同一回事。沒有任何轉折時回 ``inf``（呼叫端自行決定怎麼記）。
    """
    if not res.transitions:
        return float("inf")
    mid = res.profile.size / 2.0
    return float(min(abs(mid - t) for t in res.transitions))
