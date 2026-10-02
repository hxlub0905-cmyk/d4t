# Vendored into d4t on 2026-09-07 (F85).
# Source project: PEAR
#   - pear/core/analysis.py  (uniformity, linear_trend, roi_center,
#     group_positions, jitter_tolerance, cluster_positions, cell_edges,
#     heat_cells, profile_by_position)
# Adaptations:
#   - Everything takes plain ``(x, y, w, h)`` rect tuples instead of PEAR's
#     ``ROI`` dataclass: that is exactly what ``ctx.roi_rects(name, shape)``
#     hands back, so the caller never builds an object to throw away.
#     ``heat_cells`` therefore returns a **list aligned with the rects**
#     rather than a ``{rid: box}`` dict (d4t has no rid), and is renamed
#     ``cell_boxes`` because "heat" is one of its four consumers, not its
#     meaning.
#   - Added ``slope_per_100px`` — see the warning on it.
#   - RENAMED PEAR's ``uniformity()`` to ``uniformity_stats()``: a
#     function with the same name as its own module shadows it in the
#     package namespace (``from .uniformity import uniformity`` in
#     ``algo/__init__`` rebinds the name from the module to the
#     function), so ``from ..algo import uniformity as algo_unif`` hands
#     the caller a function. Caught by the test suite on the first run;
#     the same shape as the ``leaf_hex`` shadowing ruff found in F84.
#   - SKIPPED PEAR's ``cohens_d`` / ``attribute_separability`` (η² and the
#     standardized mean difference between groups): the user ruled the
#     between-group half out of F85 ("不要"). They are 40 lines and would come
#     back from the same file if that changes.
#   - SKIPPED PEAR's ``group_outliers`` (Tukey count per group):
#     ``glv_stats``'s ``glv_boxes_over_k`` (F68) already answers "how many
#     boxes are off", and a second count next to it would use a different
#     notion of "outlier" — see F85 §3.3.
#   - No algorithmic changes.
"""均勻度 —— **這一群框之間差多少、有沒有斜掉** vendored from PEAR.

`glv_stats` 的 ``each box`` 已經逐框量出一串值了；這一支回答的是那一串值
**怎麼收尾**：

======================  ==================================================
:func:`uniformity_stats` 散多開（range / range_pct / cv_pct）
:func:`slope_per_100px` 有沒有斜掉（值 vs 框中心的最小平方斜率）
:func:`profile_by_position` 那條 profile 線（同一欄的框收成一個點）
:func:`cell_boxes`      heat map 上每一格框「代表」的那一塊
======================  ==================================================

**沒有任何一支會 raise。** 空的、只有一格、std ≈ 0 —— 那些在真實操作裡天天
發生（使用者剛放下第一個區域），回 ``None`` 或 0，讓呼叫端決定要不要寫那一格
（F19：「算不出來的那一格不寫」）。

零 Qt、純 numpy（鐵則 1）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    "SLOPE_UNIT_PX", "uniformity_stats", "linear_trend", "slope_per_100px",
    "rect_centers", "jitter_tolerance", "cluster_positions", "cell_edges",
    "cell_boxes", "profile_by_position",
]

#: 斜率報成「**每這麼多 px** 變多少」。
#:
#: ⚠ **這個數字不是化妝品，拿掉它會讓整欄看起來像 0。** 真實影像上的灰階
#: 梯度是每 px 0.00x 那種量級，而特徵表印數字有位數上限 —— 於是一片明顯
#: 左右不均的圖，`slope_x` 那一欄會**整欄印成 0.000**，讀起來是「很平」。
#: 那是這一輪最危險的一種錯：跑得完、有數字、而且是錯的，**沒有任何錯誤訊息**。
#: PEAR 就是報每 100 px 的（README：「slope per 100 px」）。
SLOPE_UNIT_PX = 100.0


def uniformity_stats(values: Sequence[Any]) -> Dict[str, float]:
    """一串值有多平 —— **只給數字，不下判斷**。

    ``range`` 是全距（完全平的時候是 0）；``range_pct`` 與 ``cv_pct`` 把它
    表示成佔平均的百分比，那是灰階均勻度慣用的寫法。

    平均是 0 附近時（`diff` 那條流就會這樣）百分比沒有意義 —— 那兩格回 0.0
    而不是 inf，呼叫端要自己決定寫不寫。
    """
    v = np.asarray(values, dtype=np.float64).ravel()
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "mean": 0.0, "range": 0.0, "range_pct": 0.0,
                "std": 0.0, "cv_pct": 0.0}
    mean = float(v.mean())
    rng = float(v.max() - v.min())
    sd = float(v.std())
    den = abs(mean)
    return {"n": int(v.size), "mean": mean, "range": rng,
            "range_pct": (rng / den * 100.0) if den > 1e-12 else 0.0,
            "std": sd,
            "cv_pct": (sd / den * 100.0) if den > 1e-12 else 0.0}


def linear_trend(x: Sequence[Any], y: Sequence[Any]
                 ) -> Optional[Tuple[float, float]]:
    """y 對 x 的最小平方 ``(斜率, 截距)``，退化時回 ``None``。

    斜率就是「值 vs 位置」那條線的傾角：0 = 平的。**每一個 px 一單位** ——
    要報給人看請走 :func:`slope_per_100px`。
    """
    xa = np.asarray(x, dtype=np.float64).ravel()
    ya = np.asarray(y, dtype=np.float64).ravel()
    if xa.size != ya.size:
        return None
    m = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[m], ya[m]
    if xa.size < 2 or float(xa.std()) < 1e-12:
        return None
    sx, sy = float(xa.mean()), float(ya.mean())
    dx = xa - sx
    denom = float((dx * dx).sum())
    if denom < 1e-12:
        return None
    slope = float((dx * (ya - sy)).sum() / denom)
    return slope, float(sy - slope * sx)


def slope_per_100px(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    """傾斜度，單位是**每 :data:`SLOPE_UNIT_PX` 個 px**（見那一格的警告）。

    只有一格框、所有框擠在同一個座標上、或值全是 NaN 的時候回 ``None`` ——
    那不是「很平」，是「這件事問不出來」，而兩者在報表上必須看得出差別。
    """
    fit = linear_trend(x, y)
    if fit is None:
        return None
    return float(fit[0] * SLOPE_UNIT_PX)


def rect_centers(rects: Sequence[Any]) -> Tuple[np.ndarray, np.ndarray]:
    """``[(x, y, w, h), …]`` → ``(中心 x 陣列, 中心 y 陣列)``。

    順序跟傳進來的一模一樣，所以「第 i 格的值」與「第 i 格的位置」共用索引
    —— 那是所有位置相關的計算的前提。
    """
    cx: List[float] = []
    cy: List[float] = []
    for r in rects or ():
        x, y, w, h = (float(v) for v in tuple(r)[:4])
        cx.append(x + w / 2.0)
        cy.append(y + h / 2.0)
    return (np.asarray(cx, dtype=np.float64),
            np.asarray(cy, dtype=np.float64))


def jitter_tolerance(sorted_unique: Sequence[Any]) -> float:
    """兩個中心差多遠**還算同一排／同一欄**。

    一排八個框，中心其實是八個「小結」不是八個位置 —— 相鄰中心的間距排序
    之後，結內的幾 px 與結間的幾十 px 之間有一個**階梯**，容差就落在那一階
    的中間（取幾何平均：穩穩高過每一個抖動間距，又絕不會吞掉一整個節距）。

    **沒有那一階就回 0** —— 真的散開的分布不是抖動，合併它會把資料改掉。
    兩道門檻都是證據不是品味：階梯要是**真的**階梯（4 倍），而且它下面要有
    一群小間距（``i >= 1``）—— 一堆大間距裡混一個小的是「少放了一個框」，
    不是「抖」。

    ⚠ d4t 的框是卡片產的，看起來應該很整齊 —— 但 `roi_reference` 的
    ``stripes in the image`` 走次像素邊緣定位，中心**本來就不是整數**；
    ``layout layers`` 從 label map 拆矩形，一條 45° 斜帶會拆出五千多個階梯狀
    小塊。兩條路都會踩到，而症狀是「八欄的網格碎成三十幾條細條」。
    """
    a = np.asarray(sorted_unique, dtype=np.float64).ravel()
    if a.size < 3:
        return 0.0
    gaps = np.sort(np.diff(a))
    gaps = gaps[gaps > 0]
    if gaps.size < 2:
        return 0.0
    ratios = gaps[1:] / np.maximum(gaps[:-1], 1e-9)
    i = int(np.argmax(ratios))
    if i < 1 or ratios[i] < 4.0:
        return 0.0
    return float(np.sqrt(gaps[i] * gaps[i + 1]))


def cluster_positions(positions: Sequence[Any], tol: float) -> np.ndarray:
    """相鄰差距 ``<= tol`` 的中心收成一個位置（代表值是那一群的平均）。"""
    a = np.sort(np.asarray(positions, dtype=np.float64).ravel())
    if a.size == 0:
        return np.empty(0)
    if tol <= 0:
        return np.unique(a)
    out: List[float] = []
    start = 0
    for i in range(1, a.size + 1):
        if i == a.size or a[i] - a[i - 1] > tol:
            out.append(float(a[start:i].mean()))
            start = i
    return np.asarray(out, dtype=np.float64)


def cell_edges(positions: Sequence[Any], decimals: int = 3,
               tol: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
    """一個軸上的鋪磚邊界 —— 回 ``(相異中心, 邊界)``。

    邊界有 ``len(中心) + 1`` 個，落在相鄰中心的中線上，最外側兩個往外鏡射
    半個間距。每一格從自己的下邊界畫到上邊界，整條軸**剛好鋪滿**：中心落在
    四捨五入過的像素上不會留髮絲縫，間距不平均也不會疊。

    ``tol=None`` 由資料量（:func:`jitter_tolerance`）；傳 0 保留每一個相異
    中心。只有一個相異中心時沒有鄰居可量，給一個 1 px 的格子 —— 呼叫端拿
    框自己的尺寸去換。
    """
    a = np.asarray(positions, dtype=np.float64).ravel()
    a = a[np.isfinite(a)]
    if a.size == 0:
        return np.empty(0), np.empty(0)
    a = np.round(a, decimals)
    if tol is None:
        tol = jitter_tolerance(np.unique(a))
    c = cluster_positions(a, tol)
    if c.size == 0:
        return np.empty(0), np.empty(0)
    if c.size == 1:
        return c, np.asarray([c[0] - 0.5, c[0] + 0.5])
    mid = (c[:-1] + c[1:]) / 2.0
    return c, np.concatenate(([2.0 * c[0] - mid[0]], mid,
                              [2.0 * c[-1] - mid[-1]]))


def cell_boxes(rects: Sequence[Any], bounds: Optional[Sequence[Any]] = None
               ) -> List[Tuple[float, float, float, float]]:
    """每一格框「代表」的那一塊影像 —— ``[(x0, y0, x1, y1), …]``，順序同 ``rects``。

    量到的只有框裡面，框與框之間是沒有量的。把每一格的值鋪滿「到鄰居中線
    為止」的矩形，那片空白就由**最近的一次真實量測**填起來 —— 於是整片的
    梯度看起來是一片梯度，而不是一排小色塊。``bounds = (w, h)`` 把鋪磚夾回
    影像裡。
    """
    rs = [tuple(float(v) for v in tuple(r)[:4]) for r in (rects or ())]
    if not rs:
        return []
    cx, cy = rect_centers(rs)
    xc, xe = cell_edges(cx)
    yc, ye = cell_edges(cy)

    def step(edges: np.ndarray, fallback: float) -> float:
        # 只有一排（或一欄）時沒有自己的節距 —— 借另一個軸的，兩個都沒有就
        # 只剩框自己的大小
        return float(np.median(np.diff(edges))) if edges.size > 2 else fallback

    sx = step(xe, 0.0)
    sy = step(ye, 0.0)
    out: List[Tuple[float, float, float, float]] = []
    for (_rx, _ry, rw, rh), x, y in zip(rs, cx, cy):
        if xe.size > 2:
            i = int(np.abs(xc - x).argmin())
            x0, x1 = float(xe[i]), float(xe[i + 1])
        else:
            half = (sy if sy > 0 else rw) / 2.0
            x0, x1 = float(x - half), float(x + half)
        if ye.size > 2:
            j = int(np.abs(yc - y).argmin())
            y0, y1 = float(ye[j]), float(ye[j + 1])
        else:
            half = (sx if sx > 0 else rh) / 2.0
            y0, y1 = float(y - half), float(y + half)
        if bounds:
            bw, bh = float(bounds[0]), float(bounds[1])
            x0, x1 = max(0.0, x0), min(bw, x1)
            y0, y1 = max(0.0, y0), min(bh, y1)
        out.append((x0, y0, x1, y1))
    return out


def profile_by_position(positions: Sequence[Any], values: Sequence[Any],
                        decimals: int = 0, tol: Optional[float] = None
                        ) -> Tuple[np.ndarray, np.ndarray]:
    """同一個位置上的框收成一個平均值 —— 回 ``(位置, 平均)``，照位置排序。

    一整欄的框共用一個 X，平均起來才是**那條讀平不平的線**。差幾個 px 的
    中心算同一個位置（``tol=None`` 由資料量），否則一欄會裂成好幾欄，而線上
    每一裂就多一個轉折。
    """
    px = np.asarray(positions, dtype=np.float64).ravel()
    v = np.asarray(values, dtype=np.float64).ravel()
    if px.size != v.size:
        return np.empty(0), np.empty(0)
    m = np.isfinite(px) & np.isfinite(v)
    px, v = px[m], v[m]
    if px.size == 0:
        return np.empty(0), np.empty(0)
    keys = np.round(px, decimals)
    if tol is None:
        tol = jitter_tolerance(np.unique(keys))
    slots = cluster_positions(keys, tol)
    if slots.size == 0:
        return np.empty(0), np.empty(0)
    idx = np.abs(keys[:, None] - slots[None, :]).argmin(axis=1)
    centers: List[float] = []
    means: List[float] = []
    for k in range(slots.size):
        sel = idx == k
        if not sel.any():
            continue
        centers.append(float(px[sel].mean()))
        means.append(float(v[sel].mean()))
    return (np.asarray(centers, dtype=np.float64),
            np.asarray(means, dtype=np.float64))
