# ADEPT step-card library — authored 2026-07-28 (M1).
"""denoise — 去雜訊卡（median / gaussian）。"""
from __future__ import annotations

from typing import Any, Dict, List

import cv2
import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_ENHANCE,
)
from ._util import parse_key_list, require_image


def _denoise_one(step_key: str, img: np.ndarray, method: str, ksize: int) -> np.ndarray:
    if ksize == 1:
        return img.copy()          # ksize=1 等於不濾波
    if method == "median":
        # cv2.medianBlur：float32 只支援 ksize<=5；uint8 支援到大核
        if img.dtype != np.uint8 and ksize > 5:
            raise StepError(step_key, f"median filtering of float images supports ksize 1/3/5 only "
                        f"(got {ksize}); use a smaller ksize or convert to uint8 first.")
        src = img if img.dtype in (np.uint8, np.float32) else img.astype(np.float32)
        return cv2.medianBlur(src, ksize)
    # gaussian
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


@register_step
class DenoiseStep(Step):
    """去雜訊：median（抑制點狀噪點）或 gaussian（整體平滑）。"""

    key = "denoise"
    label = "Denoise"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Suppress image noise with a median or Gaussian filter so the "
            "measurements that follow are steadier.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  label="Apply to",
                  help=("Which image stream this card works on; the result is "
                        "written back to that same stream. Streams are the "
                        "named lines on the canvas - test is the defect image, "
                        "ref is the reference image.")),
        ParamSpec(name="also_apply", type="image_keys", default="",
                  label="Also apply to",
                  help=("Other streams that get exactly the same denoising. "
                        "Tick ref as well if you want test and ref to stay "
                        "comparable.")),
        ParamSpec(name="method", type="choice", default="median",
                  choices=["median", "gaussian"],
                  help=("median = suppress isolated bright/dark specks (common "
                        "for SEM); gaussian = soften everything.")),
        ParamSpec(name="ksize", type="int", default=3, min=1, max=15,
                  help=("Filter kernel size (odd, 1-15; 1 = no filtering, "
                        "larger is smoother).")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("target", "test")] + parse_key_list(params.get("also_apply", ""))

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return cls.resolve_reads(params)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        ksize = int(p["ksize"])
        if ksize % 2 == 0:
            raise StepError(self.key, f"ksize must be odd (got {ksize}); an even kernel has no "
                        f"centre pixel — use {ksize - 1} or {ksize + 1}.")
        tgt = require_image(ctx, self.key, p["target"])
        ctx.set_image(p["target"], _denoise_one(self.key, tgt, p["method"], ksize))
        for k in parse_key_list(p["also_apply"]):
            if k not in ctx.images:
                ctx.warn(f"[{self.key}] also_apply stream '{k}' does not "
                         f"exist; skipped.")
                continue
            ctx.set_image(k, _denoise_one(self.key, ctx.images[k], p["method"], ksize))
        return ctx
