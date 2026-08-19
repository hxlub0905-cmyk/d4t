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
}

SNR_ID = "snr"
SNR_LABEL = "SNR"
SNR_FORMULA = "(mean_T − mean_R) / std_R"

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


def metric_label(mid: str) -> str:
    """Human label for any metric id (fixed, custom quantile, or SNR)."""
    if mid in GLV_STATS:
        return GLV_STATS[mid]
    if mid == SNR_ID:
        return SNR_LABEL
    q = quantile_of(mid)
    if q is not None:
        return f"GLV Q{q}"
    return mid


def metric_formula(mid: str) -> str:
    if mid in GLV_FORMULAS:
        return GLV_FORMULAS[mid]
    if mid == SNR_ID:
        return SNR_FORMULA
    q = quantile_of(mid)
    if q is not None:
        return f"{q}th percentile"
    return "—"


def glv_value(patch: np.ndarray, mid: str) -> float:
    """One GLV statistic of a patch. Custom quantiles (``glv_q<NN>``) work too."""
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
    q = quantile_of(mid)
    if q is not None:
        return float(np.percentile(f, q))
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


#: 兩塊區域比出來的幾個數字（F11 Measure：Compare regions 卡）。
#: key 就是特徵名的字尾，所以順序＝畫面上勾選的順序。
#:
#: **值是英文的**：它們會顯示給使用者（`tests/test_ui_english_only.py` 會擋）。
#: 中文的說明寫在註解與 :func:`compare_pixels` 的 docstring 裡。
COMPARE_METRICS: Dict[str, str] = {
    "delta": "target minus reference, in gray levels",
    "ratio": "target divided by reference",
    "percent": "the difference as a percentage of the reference",
    "snr": "the difference divided by how much the reference itself varies",
    "tstat": "the same, but with the size of each region taken into account",
}


def compare_pixels(target: np.ndarray, reference: np.ndarray,
                   stat: str = "glv_mean") -> Dict[str, float]:
    """兩塊區域的像素 → 一組比較的數字。

    ``stat`` 決定「拿哪一個統計量來比」（``glv_mean`` / ``glv_median`` /
    ``glv_q90`` …，同 :func:`glv_value`）。``snr`` 與 ``tstat`` 的分母一律是
    **像素的散布**，跟 ``stat`` 挑哪一個無關 —— 「差幾個 σ」問的是散布，
    而中位數沒有自己的 σ。

    為什麼 ``snr`` 的公式是 ``(μ_T − μ_R) / σ_R``
    ---------------------------------------------
    那是 e-beam 這一行**帶正負號**的 SNR 慣例，而這個 repo 已經有兩個地方在用
    它（:func:`group_snr` 與 ``algo/snr``）。這裡不發明第三種寫法 ——
    同一個名字在不同卡片上算出不同的東西，是最難發現的那種錯。

    ``tstat`` 是它的「樣本數也算」版本：兩塊區域的像素數差很多的時候
    （GDS 的一層可能是另一層的十倍大），``snr`` 只看參考那邊的散布，
    而 ``tstat`` 的分母把兩邊的樣本數都算進去。兩個都給，因為它們回答的是
    不同的問題，而使用者要選哪一個取決於他在比什麼。

    分母是 0（區域太小、或整塊同一個值）時那一項是 ``nan`` —— **不是 0**：
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

    sd_r = float(r.std())
    out["snr"] = float((tv - rv) / sd_r) if sd_r > 1e-9 else float("nan")

    # Welch 的標準誤（不假設兩邊變異數相同 —— 兩塊區域的材質不同，
    # 假設它們散布一樣沒有道理）。
    vt, vr = float(t.var(ddof=1)) if t.size > 1 else 0.0, \
        float(r.var(ddof=1)) if r.size > 1 else 0.0
    se = (vt / max(1, t.size) + vr / max(1, r.size)) ** 0.5
    out["tstat"] = float((tv - rv) / se) if se > 1e-12 else float("nan")
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
