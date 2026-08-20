# d4t step-card library — authored 2026-07-28 (M1).
"""roi_snr — ROI SNR 量測卡。

在指定影像流上對一個 ROI（最大 blob 的 bbox，或影像中央固定方框）量
訊噪比與相關統計。roi_snr_signed 沿用 e-beam 正負號慣例：比背景暗的
缺陷是負值。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import snr as algo_snr
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, register_step, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, output_prefix_spec, roi_rect_or_none,
)

_ZERO = {"roi_snr_signed": 0.0, "roi_snr_abs": 0.0, "roi_contrast": 0.0,
         "roi_edge_sharpness": 0.0, "roi_dvi": 0.0}


@register_step
class RoiSnrStep(MultiSourceStep):
    """ROI SNR：缺陷區對周邊背景的訊噪比與對比統計。"""

    key = "roi_snr"
    label = "ROI SNR"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the defect region's signal-to-noise against the "
            "surrounding background (signed — dark defects are negative), "
            "plus contrast and edge sharpness.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="diff",
                  help=("Image stream to measure on (usually diff; leave diff "
                        "unsigned to keep bright/dark direction visible).")),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same statistics measured in both, and every "
                        "number gets its region's name in front of it. "
                        "No line means the whole image.")),
        ParamSpec(name="background_margin", type="int", default=20, min=1, max=200,
                  help=("Background sampling width in pixels: the ring outside the "
                        "ROI used for background statistics.")),
        output_prefix_spec("blob"),
    ]
    reads = ["diff"]
    writes: List[str] = []
    features_out = ["roi_snr_signed", "roi_snr_abs", "roi_contrast",
                    "roi_edge_sharpness", "roi_dvi"]

    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        rect = roi_rect_or_none(ctx, self.key, img, p["roi"])
        if rect is None:
            ctx.warn(f"[{self.key}] no blob found (run Blob segment first, or "
                     f"point roi at a Define region card); all ROI SNR "
                     f"features recorded as 0.")
            return dict(_ZERO)

        res = algo_snr.roi_snr(img, rect, background_margin=int(p["background_margin"]))
        if res is None:
            ctx.warn(f"[{self.key}] ROI {rect} is outside the image or invalid; "
                     f"all ROI SNR features recorded as 0.")
            return dict(_ZERO)

        return {
            "roi_snr_signed": res.snr_signed,
            "roi_snr_abs": res.snr_abs,
            "roi_contrast": res.contrast,
            "roi_edge_sharpness": res.edge_sharpness,
            "roi_dvi": res.dvi,
        }
