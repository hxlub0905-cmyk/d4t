# ADEPT step-card library — authored 2026-07-28 (M1).
"""影像算術卡：subtract。

``invert`` 已於 F7-20 併進 ``tone`` 卡（它跟亮度/gamma 一樣是逐像素的
色調映射，使用者的問題只有一個「把這張圖調得看得清楚」）。

注意：subtract 產出的 diff 流是 **float32**（可能含負值，取決於 absolute），
下游卡（snr_map / blob_segment / roi_snr…）都吃得下 float32。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE,
)
from ._util import require_image


@register_step
class SubtractStep(Step):
    """影像相減：out = a - b（float32；absolute=True 時取絕對值）。"""

    key = "subtract"
    label = "Compare two streams"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Combine two image streams into one - normally test minus ref, "
            "which is what makes defects stand out. The result stream is "
            "float32.")
    requires_ref = True
    params = [
        ParamSpec(name="a", type="image_key", default="test",
                  label="First stream",
                  help="The image being judged (usually test)."),
        # 預設 ``ref`` 而不是 ``ref_aligned``（2026-08-14 使用者指正）：
        # patch 是機台以 defect 為中心裁切的，**本來就對齊**，「一定要先
        # Align」是這個預設造出來的假前置。Align 留給之後非 patch 的輸入、
        # 或站點真的量到殘餘位移時用 —— 那時候把這一格改指 ref_aligned。
        ParamSpec(name="b", type="image_key", default="ref",
                  label="Second stream",
                  help=("What to compare it against (usually ref - patches "
                        "already arrive centred on the defect, so no "
                        "alignment step is needed). If your images do need "
                        "registration first, add an Align card and point "
                        "this at ref_aligned.")),
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
    reads = ["test", "ref"]
    writes = ["diff"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("a", "test"), params.get("b", "ref")]

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
