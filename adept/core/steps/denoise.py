# ADEPT step-card library — authored 2026-07-28 (M1).
"""denoise — 去雜訊卡（median / gaussian）。"""
from __future__ import annotations

from typing import Any, Dict, List

import cv2
import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step,
)
from ._util import parse_key_list, require_image


def _denoise_one(step_key: str, img: np.ndarray, method: str, ksize: int) -> np.ndarray:
    if ksize == 1:
        return img.copy()          # ksize=1 等於不濾波
    if method == "median":
        # cv2.medianBlur：float32 只支援 ksize<=5；uint8 支援到大核
        if img.dtype != np.uint8 and ksize > 5:
            raise StepError(step_key, f"median 濾波對浮點影像只支援 ksize 1/3/5（收到 {ksize}）；請改小 ksize 或先轉 uint8。")
        src = img if img.dtype in (np.uint8, np.float32) else img.astype(np.float32)
        return cv2.medianBlur(src, ksize)
    # gaussian
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


@register_step
class DenoiseStep(Step):
    """去雜訊：median（抑制點狀噪點）或 gaussian（整體平滑）。"""

    key = "denoise"
    label = "去雜訊"
    category = CATEGORY_IMAGE
    help = "用中值或高斯濾波壓掉影像雜訊，讓後面的量測更穩定。"
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  help="要去雜訊的主影像流（就地覆寫）。"),
        ParamSpec(name="also_apply", type="str", default="",
                  help="同時套用的其他影像流（逗號清單，可留空；不存在的流只警告不報錯）。"),
        ParamSpec(name="method", type="choice", default="median",
                  choices=["median", "gaussian"],
                  help="median=抑制孤立亮暗點（SEM 常用）；gaussian=整體柔化。"),
        ParamSpec(name="ksize", type="int", default=3, min=1, max=15,
                  help="濾波核大小（1–15 的奇數；1=不濾波，越大越平滑）。"),
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
            raise StepError(self.key, f"ksize 必須是奇數（收到 {ksize}）；偶數核沒有中心像素，請改用 {ksize - 1} 或 {ksize + 1}。")
        tgt = require_image(ctx, self.key, p["target"])
        ctx.set_image(p["target"], _denoise_one(self.key, tgt, p["method"], ksize))
        for k in parse_key_list(p["also_apply"]):
            if k not in ctx.images:
                ctx.warn(f"[{self.key}] also_apply 的影像流 '{k}' 不存在，略過。")
                continue
            ctx.set_image(k, _denoise_one(self.key, ctx.images[k], p["method"], ksize))
        return ctx
