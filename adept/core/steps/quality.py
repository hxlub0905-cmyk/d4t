# ADEPT step-card library — authored 2026-07-28 (M1).
"""focus_quality — 影像品質（對焦）量測卡。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import quality as algo_quality
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step,
)
from ._util import require_image


@register_step
class FocusQualityStep(Step):
    """對焦品質：Laplacian 變異數 / Tenengrad / FFT 高頻比。"""

    key = "focus_quality"
    label = "Focus quality"
    category = CATEGORY_ALGO
    help = ("Measure image sharpness with three metrics — higher is sharper. "
            "Useful for screening out defocused images.")
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  help="Image stream to measure sharpness on."),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["focus_lapvar", "focus_tenengrad", "focus_fft"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        img = require_image(ctx, self.key, p["source"])
        q = algo_quality.compute_quality(img)
        if q.get("error"):
            raise StepError(self.key, f"image quality computation failed: {q['error']}")
        ctx.add_features({
            "focus_lapvar": q["laplacian_var"],
            "focus_tenengrad": q["tenengrad"],
            "focus_fft": q["fft_hf_ratio"],
        })
        return ctx
