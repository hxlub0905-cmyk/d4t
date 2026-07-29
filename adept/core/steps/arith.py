# ADEPT step-card library — authored 2026-07-28 (M1).
"""影像算術卡：subtract / invert。

注意：subtract 產出的 diff 流是 **float32**（可能含負值，取決於 absolute），
下游卡（snr_map / blob_segment / roi_snr…）都吃得下 float32。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE, GROUP_ENHANCE,
)
from ._util import require_image


@register_step
class SubtractStep(Step):
    """影像相減：out = a - b（float32；absolute=True 時取絕對值）。"""

    key = "subtract"
    label = "Compare two streams"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Combine two image streams into one - normally test minus the "
            "aligned ref, which is what makes defects stand out. The result "
            "stream is float32.")
    requires_ref = True
    params = [
        ParamSpec(name="a", type="image_key", default="test",
                  label="First stream",
                  help="The image being judged (usually test)."),
        ParamSpec(name="b", type="image_key", default="ref_aligned",
                  label="Second stream",
                  help=("What to compare it against (usually the aligned "
                        "ref_aligned - add an Align card to produce that "
                        "stream, or point this at ref to skip alignment).")),
        # op 是 F7-10 加的。差分之外的四種組合以前得靠外部工具做，但它們跟
        # 相減是同一個問題的不同答案（「這兩張哪裡不一樣」），所以是同一張卡的
        # 一個下拉 —— 不是四張新卡片。
        ParamSpec(
            name="op", type="choice", default="subtract",
            choices=["subtract", "ratio", "max", "min", "mean"],
            label="How to combine",
            help=("subtract = a minus b, the normal die-to-die difference; "
                  "ratio = a divided by b, which stays meaningful when the "
                  "two images have different overall brightness; max / min = "
                  "take the brighter or darker pixel of the two; mean = "
                  "average them (useful for building a cleaner reference)."),
        ),
        ParamSpec(name="absolute", type="bool", default=True,
                  label="Ignore the sign",
                  help=("True = absolute value (bright and dark defects both become "
                        "positive signal); False = keep the sign so bright and dark "
                        "defects stay distinguishable. Only used by subtract.")),
        ParamSpec(name="out", type="image_key", default="diff",
                  label="Write result to",
                  help="Name of the image stream the result is written to (float32)."),
    ]
    reads = ["test", "ref_aligned"]
    writes = ["diff"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("a", "test"), params.get("b", "ref_aligned")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "diff")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        a = require_image(ctx, self.key, p["a"])
        b = require_image(ctx, self.key, p["b"])
        if a.shape != b.shape:
            raise StepError(self.key, f"'{p['a']}' and '{p['b']}' differ in size "
                            f"({a.shape} vs {b.shape}); cannot subtract.")
        fa, fb = a.astype(np.float32), b.astype(np.float32)
        op = str(p["op"])
        if op == "ratio":
            # 0 除法：分母補一個極小值而不是讓它變 inf —— inf 會一路帶到
            # 特徵與分數，最後變成一顆「分數是 nan」的 defect，而使用者
            # 完全看不出是哪一步造成的。
            out = fa / np.maximum(np.abs(fb), 1e-6) * np.sign(np.where(fb == 0, 1.0, fb))
        elif op == "max":
            out = np.maximum(fa, fb)
        elif op == "min":
            out = np.minimum(fa, fb)
        elif op == "mean":
            out = (fa + fb) * 0.5
        else:
            out = fa - fb
            if p["absolute"]:
                out = np.abs(out)
        ctx.set_image(p["out"], out.astype(np.float32))
        return ctx


@register_step
class InvertStep(Step):
    """影像反相：亮暗顛倒（uint8：255-x；[0,1] 浮點：1-x）。"""

    key = "invert"
    label = "Invert"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Flip bright and dark, so dark defects become bright signal for "
            "the steps that follow.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  label="Apply to",
                  help=("Which image stream to invert; the result is written "
                        "back to that same stream. Streams are the named lines "
                        "on the canvas - test is the defect image, ref is the "
                        "reference image.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("target", "test")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("target", "test")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        img = require_image(ctx, self.key, p["target"])
        if img.dtype == np.uint8:
            out = (255 - img).astype(np.uint8)
        else:
            f = img.astype(np.float32)
            if f.size > 0 and float(f.min()) >= 0.0 and float(f.max()) <= 1.5:
                out = (1.0 - np.clip(f, 0.0, 1.0)).astype(np.float32)
            else:
                out = (255.0 - np.clip(f, 0.0, 255.0)).astype(np.float32)
        ctx.set_image(p["target"], out)
        return ctx
