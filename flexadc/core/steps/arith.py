# FlexADC step-card library — authored 2026-07-28 (M1).
"""影像算術卡：subtract / invert。

注意：subtract 產出的 diff 流是 **float32**（可能含負值，取決於 absolute），
下游卡（snr_map / blob_segment / roi_snr…）都吃得下 float32。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step,
)
from ._util import require_image


@register_step
class SubtractStep(Step):
    """影像相減：out = a - b（float32；absolute=True 時取絕對值）。"""

    key = "subtract"
    label = "影像相減"
    category = CATEGORY_IMAGE
    help = "test 減 ref（對齊後）得到差異圖 diff，缺陷會在 diff 上凸顯出來；diff 流是 float32。"
    requires_ref = True
    params = [
        ParamSpec(name="a", type="image_key", default="test",
                  help="被減數影像流（通常是 test）。"),
        ParamSpec(name="b", type="image_key", default="ref_aligned",
                  help="減數影像流（通常是對齊後的 ref_aligned）。"),
        ParamSpec(name="absolute", type="bool", default=True,
                  help="True=取絕對值（亮暗缺陷都變正訊號）；False=保留正負號（可分辨亮/暗缺陷）。"),
        ParamSpec(name="out", type="image_key", default="diff",
                  help="差異圖要寫入的影像流名稱（float32）。"),
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
            raise StepError(self.key, f"'{p['a']}' 與 '{p['b']}' 尺寸不同（{a.shape} vs {b.shape}），無法相減。")
        diff = a.astype(np.float32) - b.astype(np.float32)
        if p["absolute"]:
            diff = np.abs(diff)
        ctx.set_image(p["out"], diff.astype(np.float32))
        return ctx


@register_step
class InvertStep(Step):
    """影像反相：亮暗顛倒（uint8：255-x；[0,1] 浮點：1-x）。"""

    key = "invert"
    label = "影像反相"
    category = CATEGORY_IMAGE
    help = "亮暗顛倒（黑變白、白變黑），讓暗缺陷變成亮訊號方便後續處理。"
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  help="要反相的影像流（就地覆寫）。"),
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
