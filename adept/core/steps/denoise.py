# ADEPT step-card library — authored 2026-07-28 (M1).
"""denoise — 去雜訊卡（median / gaussian / bilateral / nlm）。"""
from __future__ import annotations

from typing import Any, Dict, List

import cv2
import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_ENHANCE,
)
from ..algo import enhance as algo_enhance
from ._util import MultiStreamStep, streams_spec


def _denoise_one(step_key: str, img: np.ndarray, method: str, ksize: int,
                 strength: float = 1.0, threshold: float = 4.0) -> np.ndarray:
    """五種去雜訊法共用的入口。

    ``bilateral`` / ``nlm`` 是 F7-10 加的**邊緣保留**法。加進這張卡而不是
    另開一張，是因為使用者的問題自始至終是同一個（「這張圖太雜」），
    差別只在願意付多少代價換多少邊緣 —— 那是一個下拉，不是兩張卡。
    它們回傳 float32（見 ``algo/enhance.py`` 的 dtype 慣例）。

    ``hot_pixels``（F11 Enhance-2）是同一條理路再往前一步：**一顆都不磨**，
    只換掉跟鄰居差得離譜的那幾顆。
    """
    if ksize == 1:
        return img.copy()          # ksize=1 等於不濾波
    if method == "hot_pixels":
        return algo_enhance.fix_isolated(img, ksize, threshold)[0]
    if method == "median":
        # cv2.medianBlur：float32 只支援 ksize<=5；uint8 支援到大核
        if img.dtype != np.uint8 and ksize > 5:
            raise StepError(step_key, f"median filtering of float images supports ksize 1/3/5 only "
                        f"(got {ksize}); use a smaller ksize or convert to uint8 first.")
        src = img if img.dtype in (np.uint8, np.float32) else img.astype(np.float32)
        return cv2.medianBlur(src, ksize)
    if method == "bilateral":
        return algo_enhance.bilateral(img, ksize, strength)
    if method == "nlm":
        return algo_enhance.nlm(img, ksize, strength)
    # gaussian
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


#: 「換掉了多少比例的畫素」的特徵名（只有 ``hot_pixels`` 會吐）。
HOT_FRAC = "hot_px_frac"


@register_step
class DenoiseStep(MultiStreamStep):
    """去雜訊：median / gaussian（全平滑）、bilateral / nlm（保留邊緣）、
    hot_pixels（只換孤立壞點）。"""

    key = "denoise"
    label = "Denoise"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Suppress image noise so the measurements that follow are "
            "steadier - either smoothing everything, or smoothing only the "
            "flat areas and leaving edges (and small defects) intact.")
    params = [
        streams_spec("test"),
        ParamSpec(name="method", type="choice", default="median",
                  choices=["median", "hot_pixels", "gaussian", "bilateral",
                           "nlm"],
                  help=("median = suppress isolated bright/dark specks (common "
                        "for SEM); hot_pixels = replace ONLY the few pixels "
                        "that are wildly different from their neighbours and "
                        "leave every other pixel untouched; gaussian = soften "
                        "everything; bilateral = smooth noise but keep edges, "
                        "so small defects are not wiped out with the noise; "
                        "nlm = the same idea but gentler on repeating "
                        "patterns, and much slower.")),
        ParamSpec(name="ksize", type="int", default=3, min=1, max=15,
                  label="Filter size", unit="px", extent=True,
                  help=("Filter kernel size (odd, 1-15; 1 = no filtering, "
                        "larger is smoother). With hot_pixels this is how far "
                        "out the neighbours are taken from; 3 is right for "
                        "single-pixel damage.")),
        ParamSpec(name="strength", type="float", default=1.0, min=0.1, max=5.0,
                  label="Smoothing strength",
                  show_when=("method", ("bilateral", "nlm")),
                  help=("How aggressively bilateral / nlm smooth, measured "
                        "against this image's own noise level - so 1 means "
                        "the same thing on a quiet lot and a noisy one. "
                        "Above about 2, small defects start disappearing "
                        "along with the noise.")),
        ParamSpec(name="threshold", type="float", default=4.0, min=1.0, max=10.0,
                  label="How far off counts as damage",
                  show_when=("method", ("hot_pixels",)),
                  help=("A pixel is replaced when it differs from its "
                        "neighbours by more than this many times the image's "
                        "own noise level - so 4 means the same thing on a "
                        "quiet lot and a noisy one. Lower it and real defects "
                        "start being replaced too; watch the number this card "
                        "reports (hot_px_frac) and keep it small.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    #: 換掉多少比例就講一句話。孤立壞點是**幾顆**的事，0.5% 的 patch（64x64 的
    #: 20 顆）已經不是壞點了 —— 那是門檻設得太低，正在吃真的結構。
    HOT_WARN_FRAC = 0.005

    @classmethod
    def stream_features(cls, params: Dict[str, Any]) -> List[str]:
        """只有 ``hot_pixels`` 多報一個數字。

        為什麼不是永遠都報：另外四種方法動的是**每一個**畫素，「換掉的比例」
        對它們恆等於 1，一個永遠是 1 的欄位只會佔 CSV 的寬度。
        """
        base = super().stream_features(params)
        if str(params.get("method", "median")) == "hot_pixels":
            return base + [HOT_FRAC]
        return base

    def build_op(self, ctx: Context, p: Dict[str, Any]):
        ksize = int(p["ksize"])
        if ksize % 2 == 0:
            raise StepError(self.key, f"ksize must be odd (got {ksize}); an even kernel has no "
                        f"centre pixel — use {ksize - 1} or {ksize + 1}.")
        strength, method = float(p["strength"]), str(p["method"])
        threshold = float(p["threshold"])

        return lambda img: _denoise_one(self.key, img, method, ksize, strength,
                                        threshold)

    def after_stream(self, ctx: Context, key: str, before, after,
                     p: Dict[str, Any]):
        """``hot_pixels`` 換掉了多少（F11 Enhance-2）。

        比對前後兩張圖就有了，**不必把演算法再跑一次** —— 這張卡沒有動到的畫素
        逐位元組不變，那正是它跟其他四種方法的差別，所以這個數字是精確的。

        它是使用者調 ``threshold`` 時唯一看得到的回饋：門檻調低到開始吃真的缺陷
        時，影像上看不出來（少了幾顆亮點），但這個數字會跳。
        """
        if str(p.get("method", "median")) != "hot_pixels":
            return None
        a, b = np.asarray(before), np.asarray(after)
        if a.shape != b.shape or a.size == 0:
            return {HOT_FRAC: 0.0}
        frac = float(np.count_nonzero(a != b)) / float(a.size)
        if frac > self.HOT_WARN_FRAC:
            ctx.warn(
                "[%s] replaced %.2f%% of '%s' as hot/dead pixels. Isolated "
                "damage is a handful of pixels, so this is probably eating "
                "real structure - raise 'How far off counts as damage'."
                % (self.key, 100.0 * frac, key))
        return {HOT_FRAC: frac}

    def note_stream(self, ctx: Context, key: str, img, p: Dict[str, Any]) -> None:
        """**把量到的雜訊 σ 講出來**（F11 Enhance-1）。

        `strength` 的單位就是這個 σ（「濾掉幾個 σ 的擾動」，見
        `algo/enhance.py::noise_sigma`），而在這之前它只活在演算法內部 ——
        使用者在調一個「以某個他看不到的數字為單位」的旋鈕。

        存在 ``meta`` 而不是特徵：σ 是**這張圖的性質**，不是這張卡算出來的結果
        （同一張圖不管接不接 Denoise，σ 都一樣）。要拿它當 gate 的話，
        Measure 段的 `focus_quality` 才是那個特徵該長出來的地方。
        """
        ctx.meta.setdefault("noise_sigma", {})[str(key)] = float(
            algo_enhance.noise_sigma(img))
