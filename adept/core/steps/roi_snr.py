# ADEPT step-card library — authored 2026-07-28 (M1).
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
    CATEGORY_ALGO, ParamSpec, Step, register_step,
)
from ._util import require_image

_ZERO = {"roi_snr_signed": 0.0, "roi_snr_abs": 0.0, "roi_contrast": 0.0,
         "roi_edge_sharpness": 0.0, "roi_dvi": 0.0}


@register_step
class RoiSnrStep(Step):
    """ROI SNR：缺陷區對周邊背景的訊噪比與對比統計。"""

    key = "roi_snr"
    label = "ROI SNR"
    category = CATEGORY_ALGO
    help = ("Measure the defect region's signal-to-noise against the "
            "surrounding background (signed — dark defects are negative), "
            "plus contrast and edge sharpness.")
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help=("Image stream to measure on (usually diff; leave diff "
                        "unsigned to keep bright/dark direction visible).")),
        ParamSpec(name="mode", type="choice", default="blob",
                  choices=["blob", "center"],
                  help=("blob = use the main blob's bounding box as the ROI "
                        "(run blob_segment first); center = a fixed box at the "
                        "middle of the image.")),
        ParamSpec(name="box_size", type="int", default=24, min=4, max=512,
                  help="Box side length in pixels for center mode."),
        ParamSpec(name="background_margin", type="int", default=20, min=1, max=200,
                  help=("Background sampling width in pixels: the ring outside the "
                        "ROI used for background statistics.")),
    ]
    reads = ["diff"]
    writes: List[str] = []
    features_out = ["roi_snr_signed", "roi_snr_abs", "roi_contrast",
                    "roi_edge_sharpness", "roi_dvi"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "diff")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        img = require_image(ctx, self.key, p["source"])
        h, w = img.shape[:2]

        if p["mode"] == "blob":
            blobs = ctx.meta.get("blobs") or []
            if not blobs:
                ctx.warn(f"[{self.key}] meta['blobs'] is empty (run blob_segment "
                     f"first); all ROI SNR features recorded as 0.")
                ctx.add_features(dict(_ZERO))
                return ctx
            big = blobs[0]  # 主 blob = SNR 最強者（meta["blobs"] 保留 segment 的 snr 降冪排序）
            rect = (int(big["x"]), int(big["y"]), int(big["w"]), int(big["h"]))
        else:
            box = min(int(p["box_size"]), h, w)
            rect = ((w - box) // 2, (h - box) // 2, box, box)

        res = algo_snr.roi_snr(img, rect, background_margin=int(p["background_margin"]))
        if res is None:
            ctx.warn(f"[{self.key}] ROI {rect} is outside the image or invalid; "
                     f"all ROI SNR features recorded as 0.")
            ctx.add_features(dict(_ZERO))
            return ctx

        ctx.add_features({
            "roi_snr_signed": res.snr_signed,
            "roi_snr_abs": res.snr_abs,
            "roi_contrast": res.contrast,
            "roi_edge_sharpness": res.edge_sharpness,
            "roi_dvi": res.dvi,
        })
        return ctx
