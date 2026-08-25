# d4t algorithm library — authored 2026-08-21 (F19 第二批).
"""shape — 一塊區域裡那一團東西有多大。**CD「無方向」那一半的數學。**

有方向的那一半（線寬／溝寬：掃描線、LWR/LER）住 :mod:`d4t.core.algo.edge`。
分法不是隨意的：**那裡吃一條剖面，這裡吃一塊區域。**

為什麼顆粒不能用掃描線量
------------------------
掃描線模型要先挑一個方向，而一顆顆粒沒有方向 —— 挑了之後量到的是「這一團在
那一列上有多寬」，而**答案取決於那個挑選**。所以這一支改用旋轉不變的描述：
真實覆蓋面積、等效圓直徑、以及旋轉卡尺量到的最大／最小 Feret。
一條 45° 的刮傷在這裡量得對，在 bounding box 那裡不會。

這不是被砍掉的那張 blob 分割卡
------------------------------
使用者 2026-08-20 定調「Blob 分割不需要 也不要再出現」，2026-08-21 補上界線：
**門檻切割可以做，但只在區域內、且不產生具名區域。**

**2026-08-25 那條界線動過兩次，值得留著看。** F29 先往前挪了一格
（`find_blobs` 去找「有哪些東西」，但「可以找一個框，不可以產生具名區域」）；
同一天稍晚 F31 T5 把那半支**連同 `find_defect` 卡一起刪掉**（使用者：「我覺得
find defect 不需要」）——「這張圖最異常的地方」改由 GLV 的逐框比較回答
（`worst_*`，框就是 ROI 自己），而「不可以產生具名區域」那半句仍然成立，
只是現在沒有任何東西在試探它。

所以這個模組吃一塊裁好的影像、回一組數字，從頭到尾不碰 `Context`、
不吐區域。:func:`measure_blob` 量**使用者指給它的那一塊**，準位與門檻
（:func:`pick_levels`、`edge.threshold_level`、:func:`edge_quality`）跟 CD 卡
是同一句話。

門檻怎麼定（沒有 Otsu、沒有 k-means）
-------------------------------------
那些方法會在**根本沒有前景**的時候照樣把畫面切成兩半 —— 而那正是這個模組最該
拒絕的情況（同 `algo.edge` 的 ``_MIN_QUALITY`` 那一段：沒有訊號的時候，
「最亮的 1%」永遠存在）。這裡改成兩個講得出來的準位：

* ``bg`` —— 區域**外框那一圈**的中位數。patch 是以缺陷為中心裁切的，所以邊框
  就是背景；而中位數對「邊框剛好壓到一點結構」免疫。
* ``fg`` —— 區域經過 3×3 中位數之後的最大（亮）或最小（暗）值。

⚠ **``fg`` 不能用百分位。** 第一版寫的是 p99，理由是「max 是極值統計量，一顆熱
像素就搬得動它」—— 那個理由是對的，但百分位換來了一個更糟的假設：**前景要佔
區域 1% 以上**。一顆直徑 8 px 的缺陷放在 96×96 的區域裡只佔 0.54%，於是 p99
落在**背景**上、對比變成 0，整團被判成「沒有前景」（實測，見
``tests/test_algo_shape.py::test_area_quantisation_table``）。而「區域比缺陷大
很多」正是真實使用的常態。3×3 中位數擋掉熱像素（一顆孤立的亮點過不了中位數），
又完全不管前景佔多少面積。

**代價要講清楚：認得出來的最小一團大約是 3×3。** 比那更小的東西過不了中位數，
於是 ``fg`` 抬不起來，整塊區域讀成 ``"flat"``。那是刻意的 —— 一顆 2×2 的亮點與
兩顆相鄰的熱像素在影像上分不出來，而給它一個面積等於假裝分得出來。

門檻走 :func:`d4t.core.algo.edge.threshold_level` —— **跟線寬那一支同一支函式**，
所以「…at this height」那一格在兩支裡是同一句話。

面積是硬門檻的像素數，**刻意不做次像素**
----------------------------------------
第一批的規矩是「沒有『要不要次像素』的開關」，這裡卻不做次像素面積 ——
因為有一條更硬的規矩：**畫布不能說謊**。輪廓是硬門檻切出來的，畫在影像上的
就是它；面積若來自一個柔性積分，面板上畫的那一圈與 CSV 上那個數字**就不是
同一件事**，而使用者沒有任何辦法發現。

量化誤差有多大：邊界上約 ``πd`` 顆像素各差 ±0.5 且互相抵消，所以相對誤差約
``2/√(πd)`` —— 直徑 10 px 約 3.6%，直徑 30 px 約 2%。比起「圖上一圈、表上另一
個數」，那是便宜的代價。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import cv2
import numpy as np

from .edge import edge_quality, profile_noise, threshold_level
from .snr import snr_signed

__all__ = [
    "BlobResult", "MIN_AREA", "measure_blob",
    "feret", "pick_levels", "ring_is_a_border",
]

#: 小於這麼多像素的連通元件不算一團（預設值；卡片可以改）。
#:
#: 四個像素是「一顆熱像素加上它的鄰居」的大小 —— 比這個小的東西不會有可信的
#: 形狀，而它們會把 ``pieces`` 灌成幾百。
MIN_AREA = 4

#: 對比的絕對地板（GLV）—— 跟 `algo.edge._MIN_CONTRAST` 同一個數字、同一個理由。
#:
#: **相對的那道門檻（``min_quality``）擋不住這一種**：使用者把它調到 0 的時候，
#: ``fg == bg`` 的區域（完全沒有前景）會通過品質檢查，門檻落在背景那一格上，
#: 於是**整塊區域**被切成一團。兩道門檻缺一不可，跟線寬那一支一字不差。
_MIN_CONTRAST = 1.0


class BlobResult(NamedTuple):
    """一塊區域切出來那一團的完整結果 —— **畫得出來所需要的一切都在裡面**。

    ``ok`` 是 ``False`` 時只有 ``reason`` / ``level`` / ``bg`` / ``fg`` /
    ``quality`` 有意義（呼叫端據此決定寫哪幾格）。
    """

    ok: bool
    #: ``""`` = 成功。``"flat"``（沒有夠強的前景）／``"no_blob"``（切出來一團
    #: 都沒有大到算數）／``"too_small"``（區域小到放不下一團）。
    reason: str
    #: 切在哪個灰階（面板的直方圖上那條線畫的就是它）。
    level: float
    bg: float
    fg: float
    #: ``"bright"`` / ``"dark"`` —— ``auto`` 選出來的那一個。
    target: str
    #: 0..1，走 :func:`edge_quality`（**跟線寬那一支同一份公式**）。
    quality: float
    #: 選中那一團的像素數（面積）。
    area: int
    #: 超過 ``min_area`` 的連通元件有幾個 —— 揭露「它挑了哪一團」這個自動決定。
    pieces: int
    #: 選中那一團有沒有碰到區域的邊。碰到 = 面積是**下界**，不是尺寸。
    touches_edge: bool
    #: 外輪廓（block 座標，``(N, 2)`` 的 float 陣列；``ok=False`` 時是空的）。
    contour: np.ndarray
    perimeter: float
    feret_max: float
    feret_min: float
    #: 最大 Feret 的方向（度，0 = 沿 X，逆時針為正，落在 ``[0, 180)``）。
    feret_angle: float
    #: 最長那條弦的兩端（block 座標）—— 畫在影像上的那一條。
    chord: Tuple[Tuple[float, float], Tuple[float, float]]
    #: 區域灰階的直方圖（面板畫的那一張），``(counts, lo, hi)``。
    hist: Tuple[List[int], float, float]
    #: 選中那一團的外接矩形（block 座標，``(x, y, w, h)``；``ok=False`` 時全 0）。
    #:
    #: 這兩格是 F29 加的，而它們**本來就已經算出來了**：``bbox`` 是
    #: ``connectedComponentsWithStats`` 的 stats（原本只拿來判 ``touches_edge``
    #: 就丟掉），``centroid`` 是同一支回傳的 centroids（原本接成 ``_cent``）。
    #: 缺的從來不是計算，是出口 —— 這一團在哪，量到了卻沒有人講得出來。
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    #: 選中那一團的像素質心（block 座標）。**不是外接矩形的中心** ——
    #: 一個 L 形的兩者可以差很遠，而質心才落在東西上。
    centroid: Tuple[float, float] = (0.0, 0.0)


# --------------------------------------------------------------------------- #
# 準位與門檻
# --------------------------------------------------------------------------- #
def _border_median(block: np.ndarray) -> float:
    """區域外框那一圈的中位數 —— 背景的準位。"""
    if min(block.shape[:2]) < 3:
        return float(np.median(block))
    ring = np.concatenate([block[0, :], block[-1, :],
                           block[1:-1, 0], block[1:-1, -1]])
    return float(np.median(ring))


def pick_levels(block: Any, target: str = "auto"
                ) -> Tuple[float, float, str]:
    """``(bg, fg, target)`` —— 背景準位、前景準位、以及實際用的極性。

    ``auto`` 比的是「亮的那一側比背景高多少」與「暗的那一側比背景低多少」，
    大的那個贏。**呼叫端一定要把選出來的極性吐成一個數字**（`cd_bright`）——
    同一批裡逐顆挑到不同極性的話，那一欄會裝著兩種不同的量測。
    """
    arr = np.asarray(block, dtype=np.float64)
    bg = _border_median(arr)
    # 3×3 中位數：擋掉孤立的熱／冷像素，但**不管前景佔多少面積**（見模組說明）。
    smoothed = cv2.medianBlur(arr.astype(np.float32), 3)
    hi, lo = float(smoothed.max()), float(smoothed.min())
    if target == "bright":
        return bg, hi, "bright"
    if target == "dark":
        return bg, lo, "dark"
    return ((bg, hi, "bright") if abs(hi - bg) >= abs(bg - lo)
            else (bg, lo, "dark"))


#: 外框那一圈最多可以佔整塊區域的幾成，才還算是「一圈邊」。
#:
#: 見 :func:`ring_is_a_border`。二分之一是**幾何上的分界**，不是調出來的數字：
#: 超過它，外框的像素就比內部還多。
_RING_IS_A_BORDER_MAX = 0.5


def ring_is_a_border(shape: Any) -> bool:
    """這塊區域夠大，讓「外框那一圈」還算是**一圈邊**嗎。

    ``_region_noise`` 的空間項用外框當**背景的樣本**，而那個前提有一個尺寸下限
    ——它成立的時候外框是一圈細邊，內部才是前景待的地方。

    小到某個程度之後那句話就反過來了：一個 4×8 的框，外框有 20 個像素、內部只有
    12 —— **「外框」已經不是一圈邊，它就是這塊區域本身**。而一團直徑 3 px 的東西
    放在 4 px 寬的框裡**必然碰到外框**，於是它自己被算進「背景起伏」：實測
    （合成 lot 的 spacer 框，48 顆）逐點 σ 是 8.3，外框 MAD 卻是 26.5，取大的
    那一個把品質從 0.60 壓到 0.35，整塊被判成 ``"flat"``。

    ⚠ **症狀是反過來的，所以特別難查**：ROI 框得**越準**越量不到
    （緊框 92% 量不到、整張圖只有 2%）——而框得準正是整個 Region 段存在的目的。

    這**不會**放掉空間項本來擋的那一類（低頻起伏，見 :func:`_region_noise`）：
    起伏的尺度遠大於一個小框，所以在框內它幾乎是常數，製造不出假的前景。
    那條防線守的是大區域，而它的驗收（`test_a_wandering_background_is_not_a_blob`）
    用的是 64×64 —— 外框只佔 6%，一個位元都沒動到。
    """
    try:
        h, w = int(shape[0]), int(shape[1])
    except (TypeError, ValueError, IndexError):
        return False
    if h < 3 or w < 3:
        return False
    ring = 2 * w + 2 * h - 4
    return bool(ring <= _RING_IS_A_BORDER_MAX * (w * h))


def _region_noise(block: np.ndarray) -> float:
    """背景自己起伏多少（GLV）—— **兩種估計取大的那一個**。

    * **逐點的**（``profile_noise`` 逐列再取中位數）—— 一階差分，量的是相鄰
      像素之間的跳動。逐列而不是攤平：攤平之後每一列的結尾接到下一列的開頭，
      那個接縫是一個假的大跳動。
    * **空間的**（外框那一圈的 MAD）—— 量的是背景在**整塊區域上**漂多少。

    ⚠ **只有逐點那一個會漏掉一整類背景。** 一階差分對**低頻起伏是瞎的**：
    實測一塊只有低頻起伏的區域，真實 σ 是 1.56，逐點估計報 0.13（空間估計報
    1.85）。而 ``diff`` 影像上留下來的殘差正好就是低頻的 —— 於是合成 lot 的
    假點拿到「對比 12、雜訊 0.1」＝ 品質 0.72，過關，然後每一顆都吐得出一個
    面積（實測 12/12）。真缺陷的對比是 83–86，本來分得很開。
    白雜訊上兩種估計一致（4.80 vs 4.59），所以取大的那個不會讓乾淨的資料變嚴。

    這跟 `algo.edge` 那邊問的**不是同一個問題**，所以答案不同是對的：那裡問
    「這條邊在雜訊裡站不站得住」（定位用），這裡問「這個峰比背景自己的起伏高
    多少」（偵測用）。兩者共用 :func:`edge_quality` 那個公式，但分母各自算。

    ⚠ **極限：起伏的尺度接近整塊區域的時候，外框就不是內部的代表樣本了。**
    實測（64×64、逐 seed 掃）：起伏尺度 σ≤3 px 穩定擋得住（品質 0.35–0.46），
    σ≥4 px 就在門檻上擺盪。用外框而不是整塊區域的 MAD 是刻意的 —— 整塊的
    MAD 會在「區域框得剛好貼著那一團」時把那一團自己算成雜訊，而框得緊正是
    建議的用法。
    """
    arr = np.asarray(block, dtype=np.float64)
    rows = [profile_noise(r) for r in arr if r.size >= 3]
    pointwise = float(np.median(rows)) if rows else 0.0
    if min(arr.shape[:2]) < 3 or not ring_is_a_border(arr.shape):
        return pointwise
    ring = np.concatenate([arr[0, :], arr[-1, :], arr[1:-1, 0], arr[1:-1, -1]])
    spatial = 1.4826 * float(np.median(np.abs(ring - np.median(ring))))
    return max(pointwise, spatial)


# --------------------------------------------------------------------------- #
# 旋轉卡尺
# --------------------------------------------------------------------------- #
def feret(points: Any) -> Tuple[float, float, float, Tuple[Any, Any]]:
    """凸包上的 ``(max, min, 最大方向°, 最長那條弦的兩端)``。

    * **max** = 凸包上兩點之間最遠的距離（點很少，直接兩兩算）。
    * **min** = 每一條凸包邊的法向上、整個凸包的寬度，取最小的那一個
      （最小寬度一定發生在某一條邊上 —— 這是旋轉卡尺的標準結論）。

    ⚠ **不要拿 ``cv2.minAreaRect`` 的長邊當 max Feret。** 最小面積矩形的長邊
    通常比真正的最大 Feret 大一點（矩形要同時包住兩個方向），而它會安靜地給出
    一個看起來完全正常、但偏大的尺寸。短邊倒是等於 min Feret，但既然這裡兩個
    都要，就走同一條路 —— 一份程式碼比兩份不會不一致。
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] == 0:
        return 0.0, 0.0, 0.0, ((0.0, 0.0), (0.0, 0.0))
    if pts.shape[0] == 1:
        p = (float(pts[0, 0]), float(pts[0, 1]))
        return 0.0, 0.0, 0.0, (p, p)

    diff = pts[:, None, :] - pts[None, :, :]
    dist = np.hypot(diff[:, :, 0], diff[:, :, 1])
    i, j = np.unravel_index(int(np.argmax(dist)), dist.shape)
    fmax = float(dist[i, j])
    a, b = pts[i], pts[j]
    angle = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 180.0

    # 每一條邊的法向 → 投影 → 寬度
    fmin = fmax
    n = pts.shape[0]
    for k in range(n):
        p0, p1 = pts[k], pts[(k + 1) % n]
        ex, ey = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(ex, ey)
        if length < 1e-9:
            continue
        nx, ny = -ey / length, ex / length
        proj = pts[:, 0] * nx + pts[:, 1] * ny
        fmin = min(fmin, float(proj.max() - proj.min()))
    return fmax, fmin, angle, ((float(a[0]), float(a[1])),
                               (float(b[0]), float(b[1])))


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def _fail(reason: str, level: float = 0.0, bg: float = 0.0, fg: float = 0.0,
          target: str = "", quality: float = 0.0,
          hist: Optional[Tuple] = None) -> BlobResult:
    return BlobResult(False, reason, level, bg, fg, target, quality,
                      0, 0, False, np.empty((0, 2), dtype=np.float64),
                      0.0, 0.0, 0.0, 0.0, ((0.0, 0.0), (0.0, 0.0)),
                      hist or ([], 0.0, 1.0))


def _histogram(block: np.ndarray, bins: int = 40) -> Tuple[List[int], float, float]:
    arr = np.asarray(block, dtype=np.float64).ravel()
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        hi = lo + 1.0
    counts, _edges = np.histogram(arr, bins=bins, range=(lo, hi))
    return [int(c) for c in counts], lo, hi


def measure_blob(block: Any, target: str = "auto", frac: float = 0.5,
                 min_quality: float = 0.5, min_area: int = MIN_AREA
                 ) -> BlobResult:
    """一塊裁好的影像 → 裡面那一團的尺寸與形狀。

    挑哪一團：**包含區域中心的那一團**（patch 以缺陷為中心裁切，所以中心就是
    「這一顆」的所在）；中心落在背景上就取最大的那一團。兩種情況下 ``pieces``
    都會說出總共有幾團 —— 那是揭露這個自動決定的唯一線索。
    """
    arr = np.asarray(block, dtype=np.float64)
    if arr.ndim != 2 or min(arr.shape) < 3:
        return _fail("too_small")

    hist = _histogram(arr)
    bg, fg, used = pick_levels(arr, target)
    contrast = abs(fg - bg)
    quality = edge_quality(contrast, _region_noise(arr))
    level = threshold_level(bg, fg, frac)
    # **兩道門檻缺一不可**（見 :data:`_MIN_CONTRAST`）：絕對的擋掉「根本沒有
    # 前景」，相對的擋掉「有起伏但那是雜訊」。
    if contrast < _MIN_CONTRAST or quality < max(0.0, float(min_quality)):
        # 沒有夠強的前景 —— **這正是 Otsu 會照樣切一半的那種情況**。
        return _fail("flat", level, bg, fg, used, quality, hist)

    mask = (arr >= level) if used == "bright" else (arr <= level)
    n_lab, labels, stats, cent = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    keep = [i for i in range(1, n_lab)
            if int(stats[i, cv2.CC_STAT_AREA]) >= max(1, int(min_area))]
    if not keep:
        return _fail("no_blob", level, bg, fg, used, quality, hist)

    h, w = arr.shape
    centre = int(labels[h // 2, w // 2])
    chosen = centre if centre in keep else max(
        keep, key=lambda i: int(stats[i, cv2.CC_STAT_AREA]))

    blob = (labels == chosen)
    area = int(blob.sum())
    x0 = int(stats[chosen, cv2.CC_STAT_LEFT])
    y0 = int(stats[chosen, cv2.CC_STAT_TOP])
    bw = int(stats[chosen, cv2.CC_STAT_WIDTH])
    bh = int(stats[chosen, cv2.CC_STAT_HEIGHT])
    touches = bool(x0 == 0 or y0 == 0 or x0 + bw >= w or y0 + bh >= h)

    contours, _hier = cv2.findContours(blob.astype(np.uint8),
                                       cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
    if not contours:
        return _fail("no_blob", level, bg, fg, used, quality, hist)
    outline = max(contours, key=cv2.contourArea)
    perimeter = float(cv2.arcLength(outline, True))
    hull = cv2.convexHull(outline).reshape(-1, 2).astype(np.float64)
    fmax, fmin, angle, chord = feret(hull)

    return BlobResult(True, "", level, bg, fg, used, quality, area,
                      len(keep), touches,
                      outline.reshape(-1, 2).astype(np.float64),
                      perimeter, fmax, fmin, angle, chord, hist,
                      (x0, y0, bw, bh),
                      (float(cent[chosen][0]), float(cent[chosen][1])))


# --------------------------------------------------------------------------- #
# ``find_blobs`` / ``BlobScan`` / ``BlobHit``（F29 的「找」那一半）已於 F31 T5
# 連同 `find_defect` 卡一起刪除 —— 「這張圖最異常的地方」現在由 GLV 的逐框
# 比較回答（`worst_*`，框就是 ROI 自己），框內細節由疊圖的像素標記畫
# （`export/overlay._mark_odd_pixels`）。`measure_blob` 與兩支共用過的準位
# （`pick_levels` / `edge.threshold_level` / `edge_quality`）**不動** —— CD 在用。
# --------------------------------------------------------------------------- #


def equivalent_diameter(area: float) -> float:
    """跟這個面積一樣大的圓有多寬：``2√(area/π)``。

    為什麼要它：`feret_max` 對一條細長的東西是「有多長」，而使用者常常要問的是
    「這顆有多大」—— 而面積本身的單位（px²）沒辦法直接跟一個線寬門檻比大小。
    """
    a = max(0.0, float(area))
    return 2.0 * math.sqrt(a / math.pi) if a > 0 else 0.0


def roundness(area: float, perimeter: float) -> float:
    """``4π·area / perimeter²`` —— 圓是 1，越細長／越毛躁越小。

    它跟 ``aspect``（長短 Feret 之比）**問的不是同一件事**：一條直的細棒與一團
    毛毛的圓斑可以有一樣的 aspect，而 roundness 分得出來（前者周長短、後者長）。
    兩個都留著就是這個理由。
    """
    p = float(perimeter)
    if p <= 0:
        return 0.0
    return float(min(1.0, 4.0 * math.pi * max(0.0, float(area)) / (p * p)))
