# Vendored into d4t on 2026-07-27.
# Source project: PEAR
#   - pear/core/attributes.py  (GLV metric bank: glv_value, glv_stats,
#     metric_label, metric_formula, quantile_of, default_metrics)
#   - pear/core/analysis.py    (roi_patch, roi_metric, group_snr,
#     pixel_hist, summarize + minimal ROI dataclass they depend on)
# Adaptations:
#   - Merged the metric bank and the pure ROI/patch helpers into one module.
#   - SKIPPED PEAR's `snr(target, reference)` function: the canonical SNR
#     primitive lives in `d4t.core.algo.snr` (see comment below).
#   - Vendored the minimal `ROI` dataclass / `Rect` alias (group_snr and
#     roi_metric operate on them); Qt-free in the source already.
#   - Dropped PEAR's Qt-adjacent orchestration (Group/Chart/AnalysisResult,
#     palettes, JSON (de)serialization, compute_analysis) — out of scope.
#   - No algorithmic changes.
"""GLV(灰度值)统计与 ROI 度量 — vendored from PEAR.

Deliberately small: grey-level-value (GLV) statistics of a region plus
per-group SNR. Everything is plain NumPy and every reduction is guarded
so degenerate / tiny patches never raise.

GLV statistic ids are stable strings; custom quantiles use the id form
``glv_q<NN>`` (e.g. ``glv_q90``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

# NOTE: the canonical e-beam SNR primitive `(mean_T - mean_R) / std_R` for
# two raw pixel arrays lives in `d4t.core.algo.snr` (maintained
# separately). It is deliberately NOT imported at module import time to
# avoid import-ordering issues while the algo package is being assembled;
# import it lazily where needed. `group_snr` below keeps its own inline
# (mu_T - mu_R) / sigma_R math, which matches that canonical *signed*
# convention.

# Fixed GLV statistics: id -> display label. Q25/Q75 are quantiles too, but
# are shown by default, so they live in the fixed set.
GLV_STATS: Dict[str, str] = {
    "glv_mean": "GLV mean",
    "glv_median": "GLV median",
    "glv_q25": "GLV Q25",
    "glv_q75": "GLV Q75",
    "glv_std": "GLV std",
    "glv_min": "GLV min",
    "glv_max": "GLV max",
    # -- d4t F18（2026-08-21）：robust 與分布形狀 --------------------------
    # 為什麼要有這一組：e-beam 的影像有 charging、hot pixel 與掃描條紋，
    # 而 mean/std 是對它們最脆的一組 —— 一顆貼在 255 的壞點就能把 std 拉走，
    # 於是「這塊亮不亮」變成「這塊有沒有壞點」。中位數那一路對它們免疫。
    #
    # `glv_bimodality` 不是拿來當分數用的，是拿來**自檢**的：一個區域的灰階
    # 出現兩座山，意思通常是這塊 ROI 裡混了兩種材質 —— 也就是「你量的東西
    # 不對」，而那件事比任何平均值都更早該被知道。
    "glv_mad": "GLV MAD",
    "glv_iqr": "GLV IQR",
    "glv_skew": "GLV skew",
    "glv_kurt": "GLV kurtosis",
    "glv_entropy": "GLV entropy",
    "glv_bimodality": "GLV bimodality",
    "glv_sat_frac": "GLV saturated fraction",
}

# Short formulas, shown as tooltips.
GLV_FORMULAS: Dict[str, str] = {
    "glv_mean": "mean(gray)",
    "glv_median": "median(gray)",
    "glv_q25": "25th percentile",
    "glv_q75": "75th percentile",
    "glv_std": "std(gray)",
    "glv_min": "min(gray)",
    "glv_max": "max(gray)",
    "glv_mad": "median(|gray − median|)",
    "glv_iqr": "Q75 − Q25",
    "glv_skew": "Fisher-Pearson skewness",
    "glv_kurt": "excess kurtosis (normal = 0)",
    "glv_entropy": "Shannon entropy, in bits",
    "glv_bimodality": "(skew² + 1) / kurtosis",
    "glv_sat_frac": "fraction of pixels at 0 or 255",
}

SNR_ID = "snr"
SNR_LABEL = "SNR"
SNR_FORMULA = "|stat_T − stat_R| / std across the reference boxes"

_EPS = 1e-9

Rect = Tuple[int, int, int, int]      # (x, y, w, h) in image pixels


@dataclass
class ROI:
    """A measurement rectangle belonging to one group."""

    rid: int
    gid: str
    rect: Rect
    label: str = ""


def quantile_of(mid: str) -> Optional[int]:
    """Percentile for a quantile metric id (``glv_q90`` -> 90), else None."""
    if mid.startswith("glv_q") and mid[5:].isdigit():
        return int(mid[5:])
    return None


def _number_after(mid: str, prefix: str, hi: int) -> Optional[int]:
    """``glv_trim10`` + ``glv_trim`` -> 10（超出 0..hi 回 None）。

    跟 :func:`quantile_of` 是同一個形狀，而那不是巧合：**帶一個數字的統計量
    一律走 ``<id><數字>``**（d4t 2026-08-21）。理由是 metric 的值是一串逗號
    分隔的 id，多一種語法（例如 ``glv_trim(10)``）等於多一種打錯的方式，
    而這些字串在手寫 recipe 裡是人打出來的。
    """
    if not mid.startswith(prefix):
        return None
    tail = mid[len(prefix):]
    if not tail.isdigit():
        return None
    n = int(tail)
    return n if 0 <= n <= hi else None


def trim_of(mid: str) -> Optional[int]:
    """``glv_trim10`` -> 10（兩端各去掉 10% 之後的平均）。"""
    return _number_after(mid, "glv_trim", 49)


def above_of(mid: str) -> Optional[int]:
    """``glv_above128`` -> 128（灰階高於它的像素佔多少）。"""
    return _number_after(mid, "glv_above", 255)


def metric_label(mid: str) -> str:
    """Human label for any metric id (fixed, parameterised, or SNR)."""
    if mid in GLV_STATS:
        return GLV_STATS[mid]
    if mid == SNR_ID:
        return SNR_LABEL
    q = quantile_of(mid)
    if q is not None:
        return f"GLV Q{q}"
    t = trim_of(mid)
    if t is not None:
        return f"GLV trimmed mean {t}%"
    a = above_of(mid)
    if a is not None:
        return f"GLV fraction above {a}"
    return mid


def metric_formula(mid: str) -> str:
    if mid in GLV_FORMULAS:
        return GLV_FORMULAS[mid]
    if mid == SNR_ID:
        return SNR_FORMULA
    q = quantile_of(mid)
    if q is not None:
        return f"{q}th percentile"
    t = trim_of(mid)
    if t is not None:
        return f"mean(gray), {t}% cut off each end"
    a = above_of(mid)
    if a is not None:
        return f"share of pixels with gray > {a}"
    return "—"


def _moment(f: np.ndarray, order: int) -> float:
    """Standardised central moment; 0.0 when the patch has no spread at all."""
    sd = float(f.std())
    if sd < _EPS:
        return 0.0
    return float((((f - f.mean()) / sd) ** order).mean())


def glv_value(patch: np.ndarray, mid: str) -> float:
    """One GLV statistic of a patch.

    Parameterised ids work too: ``glv_q<NN>`` (percentile), ``glv_trim<NN>``
    (mean after cutting NN% off each end) and ``glv_above<NN>`` (fraction of
    pixels brighter than NN).

    Everything is guarded: a patch with no pixels, or one where every pixel is
    the same value, returns 0.0 rather than a NaN from a 0/0. That guard is why
    the shape statistics can be offered at all — a flat ROI is normal on a
    saturated patch, and it must not poison the whole feature row.
    """
    f = np.asarray(patch, dtype=np.float64).ravel()
    if f.size == 0:
        return 0.0
    if mid == "glv_mean":
        return float(f.mean())
    if mid == "glv_std":
        return float(f.std())
    if mid == "glv_min":
        return float(f.min())
    if mid == "glv_max":
        return float(f.max())
    if mid == "glv_median":
        return float(np.median(f))
    if mid == "glv_mad":
        # **原始的 MAD，不乘 1.4826。** 那個係數是為了讓它估計常態分布的 σ，
        # 而這裡的值要給製程工程師讀 ——「典型偏離中位數幾階灰階」比「換算成
        # 相當於幾個 σ」直觀，而且後者在雙峰的 ROI 上根本沒有意義。
        return float(np.median(np.abs(f - np.median(f))))
    if mid == "glv_iqr":
        return float(np.percentile(f, 75) - np.percentile(f, 25))
    if mid == "glv_skew":
        return _moment(f, 3)
    if mid == "glv_kurt":
        return _moment(f, 4) - 3.0 if f.std() >= _EPS else 0.0
    if mid == "glv_entropy":
        counts = np.bincount(np.clip(np.rint(f), 0, 255).astype(np.int64),
                             minlength=256).astype(np.float64)
        p = counts[counts > 0] / float(f.size)
        # max()：全部同一個值時 -(1*log2 1) 會給 -0.0，而 CSV 上的 "-0.0"
        # 讀起來像個負的量。熵在數學上不會是負的。
        return max(0.0, float(-(p * np.log2(p)).sum()))
    if mid == "glv_bimodality":
        # Bimodality coefficient：(skew² + 1) / kurtosis（未減 3 的那個）。
        # 0.555（均勻分布的值）以上通常代表兩座山。分母恆 ≥ 1，不必再防除零。
        sd = float(f.std())
        if sd < _EPS:
            return 0.0
        return (_moment(f, 3) ** 2 + 1.0) / max(1.0, _moment(f, 4))
    if mid == "glv_sat_frac":
        return float(((f <= 0.0) | (f >= 255.0)).mean())
    q = quantile_of(mid)
    if q is not None:
        return float(np.percentile(f, q))
    t = trim_of(mid)
    if t is not None:
        if t == 0:
            return float(f.mean())
        lo, hi = np.percentile(f, t), np.percentile(f, 100 - t)
        kept = f[(f >= lo) & (f <= hi)]
        # 修剪掉全部是可能的（例如整塊只有兩個值）—— 那時候退回全體平均，
        # 而不是回 0：0 在分數表達式裡看起來像個答案。
        return float(kept.mean()) if kept.size else float(f.mean())
    a = above_of(mid)
    if a is not None:
        return float((f > float(a)).mean())
    return 0.0


def glv_stats(patch: np.ndarray) -> Dict[str, float]:
    """The full fixed GLV statistic set for a patch."""
    return {mid: glv_value(patch, mid) for mid in GLV_STATS}


def default_metrics() -> List[str]:
    """Metrics selected on first run."""
    return ["glv_mean", "glv_median"]


# --------------------------------------------------------------------------- #
# ROI patch + metrics
# --------------------------------------------------------------------------- #
def roi_patch(image: np.ndarray, rect: Rect) -> Optional[np.ndarray]:
    """Clipped ROI patch, or None if it lies fully outside the image."""
    x, y, w, h = rect
    ih, iw = image.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(iw, x + w), min(ih, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1]


def roi_metric(image: np.ndarray, roi: ROI, mid: str) -> float:
    """A per-ROI GLV statistic (SNR is a per-group metric, not per ROI)."""
    p = roi_patch(image, roi.rect)
    return glv_value(p, mid) if p is not None else 0.0


#: 兩塊區域比出來的幾個數字（Gray level 卡的 ``method="compare"``）。
#: key 就是特徵名的字尾，所以順序＝畫面上勾選的順序。
#:
#: **值是英文的**：它們會顯示給使用者（`tests/test_ui_english_only.py` 會擋）。
#: 中文的說明寫在註解與 :func:`compare_pixels` 的 docstring 裡。
COMPARE_METRICS: Dict[str, str] = {
    "delta": "target minus reference, in gray levels",
    "ratio": "target divided by reference",
    "percent": "the difference as a percentage of the reference",
    "snr": ("how far apart they are, in standard deviations of the "
            "reference's own box-to-box variation (never negative - the "
            "direction is what delta is for)"),
    "tstat": "the same, but with how many reference boxes there are taken into account",
}


def compare_pixels(target: np.ndarray, reference: np.ndarray,
                   stat: str = "glv_mean",
                   reference_boxes: Optional[List[float]] = None,
                   ) -> Dict[str, float]:
    """兩塊區域的像素 → 一組比較的數字。

    ``stat`` 決定「拿哪一個統計量來比」（``glv_mean`` / ``glv_median`` /
    ``glv_q90`` …，同 :func:`glv_value`）。

    ``snr`` 與 ``tstat`` 的分母：**框與框之間，不是像素與像素之間**
    ------------------------------------------------------------------
    使用者定調 2026-08-21：「SNR 的定義全線幫我改成是 by box（by pixel 會
    太小），然後 SNR 不會有負值，有負代表亮暗差異而已」。

    ``reference_boxes`` 是**參照那一塊每一格各自算出來的 stat**（一個框一個
    數字）。σ 取自它們之間的散布：

    * per-pixel 的 σ 裡有 shot noise，它比「同材質的格子彼此差多少」大得多，
      於是 SNR 被壓得很小 —— 而那個小不是訊號弱，是分母裝錯東西；
    * 「這一塊比那些格子亮幾個 σ」問的本來就是**格與格之間的變異**。

    格子少於兩個 → σ 沒有定義 → ``snr`` / ``tstat`` 是 ``nan``。
    **不退回 per-pixel**：同一個名字在不同情況下算出不同的東西，是這個 repo
    最怕的那種錯（`snr_map` 的檔頭就在講這件事）。

    ``snr`` **不帶正負號**（``|Δ| / σ``）：方向是 ``delta`` 的事，而 ``delta``
    照樣帶正負 —— 「有負代表亮暗差異而已」。

    ``tstat`` 是它的「格子數也算」版本：σ / √n。格子多的那一邊，同樣的差距更
    值得相信，而 ``snr`` 看不到這件事。

    分母是 0（格子都一樣、或只有一格）時那一項是 ``nan`` —— **不是 0**：
    0 的意思是「沒有差異」，而這裡的事實是「這個問題答不出來」。
    """
    t = np.asarray(target, dtype=np.float64).ravel()
    r = np.asarray(reference, dtype=np.float64).ravel()
    if t.size == 0 or r.size == 0:
        return {k: float("nan") for k in COMPARE_METRICS}

    tv = glv_value(t, stat)
    rv = glv_value(r, stat)
    out: Dict[str, float] = {"delta": float(tv - rv)}
    out["ratio"] = float(tv / rv) if abs(rv) > 1e-12 else float("nan")
    out["percent"] = (float((tv - rv) / rv * 100.0) if abs(rv) > 1e-12
                      else float("nan"))

    boxes = [float(v) for v in (reference_boxes or [])
             if v is not None and np.isfinite(v)]
    if len(boxes) < 2:
        out["snr"] = float("nan")
        out["tstat"] = float("nan")
        return out
    # ddof=1：這幾格是「同類的格子」的一個樣本，不是全部的母體。格子數常常
    # 只有幾十個，那個差別看得出來。
    sd_box = float(np.std(boxes, ddof=1))
    gap = abs(tv - rv)
    out["snr"] = float(gap / sd_box) if sd_box > 1e-9 else float("nan")
    se = sd_box / (len(boxes) ** 0.5)
    out["tstat"] = float(gap / se) if se > 1e-12 else float("nan")
    return out


def group_snr(image: np.ndarray, rois: List[ROI],
              target_rid: Optional[int]) -> Optional[float]:
    """Within-group SNR = (mean_target - mean_reference) / std_reference.

    ``target_rid`` selects the target ROI; every other ROI in the group is
    the reference (their pixels are pooled). Returns None when there is no
    target, no reference, or the reference has no spread.

    The inline (mu_T - mu_R) / sigma_R math matches the canonical *signed*
    e-beam SNR convention (see `d4t.core.algo.snr`).
    """
    tgt = next((r for r in rois if r.rid == target_rid), None)
    refs = [r for r in rois if r.rid != target_rid]
    if tgt is None or not refs:
        return None
    tp = roi_patch(image, tgt.rect)
    if tp is None or tp.size == 0:
        return None
    ref_pix = [roi_patch(image, r.rect).astype(np.float64).ravel()
               for r in refs if roi_patch(image, r.rect) is not None]
    ref_pix = [a for a in ref_pix if a.size]
    if not ref_pix:
        return None
    ref = np.concatenate(ref_pix)
    sd = float(ref.std())
    if sd < 1e-9:
        return None
    return (float(tp.astype(np.float64).mean()) - float(ref.mean())) / sd


def pixel_hist(patch, bins: int = 32):
    """Grey-level histogram of a patch over the full 0–255 range."""
    p = np.asarray(patch).ravel()
    if p.size == 0:
        return np.zeros(bins, dtype=int), np.linspace(0, 255, bins + 1)
    return np.histogram(p, bins=bins, range=(0, 255))


def summarize(values: np.ndarray) -> Dict[str, float]:
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "mean": 0.0, "std": 0.0, "median": 0.0,
                "q25": 0.0, "q75": 0.0, "min": 0.0, "max": 0.0}
    return {"n": int(v.size), "mean": float(v.mean()), "std": float(v.std()),
            "median": float(np.median(v)), "q25": float(np.percentile(v, 25)),
            "q75": float(np.percentile(v, 75)), "min": float(v.min()),
            "max": float(v.max())}
