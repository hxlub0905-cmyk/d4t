# FlexADC step-card library — authored 2026-07-28 (M1).
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
    label = "ROI 訊噪比"
    category = CATEGORY_ALGO
    help = "量缺陷區域相對周邊背景的訊噪比（含正負號：暗缺陷為負）與對比、邊緣銳利度。"
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="量測用的影像流（通常是 diff；用未取絕對值的 diff 才看得出亮暗方向）。"),
        ParamSpec(name="mode", type="choice", default="blob",
                  choices=["blob", "center"],
                  help="blob=用最大 blob 的 bbox 當 ROI（需先跑 blob_segment）；center=影像正中央固定方框。"),
        ParamSpec(name="box_size", type="int", default=24, min=4, max=512,
                  help="center 模式的方框邊長（像素）。"),
        ParamSpec(name="background_margin", type="int", default=20, min=1, max=200,
                  help="背景取樣寬度（像素）：ROI 外圍這圈拿來當背景統計。"),
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
                ctx.warn(f"[{self.key}] meta['blobs'] 沒有任何區塊（請先跑 blob_segment），ROI SNR 全部記 0。")
                ctx.add_features(dict(_ZERO))
                return ctx
            big = blobs[0]  # 主 blob = SNR 最強者（meta["blobs"] 保留 segment 的 snr 降冪排序）
            rect = (int(big["x"]), int(big["y"]), int(big["w"]), int(big["h"]))
        else:
            box = min(int(p["box_size"]), h, w)
            rect = ((w - box) // 2, (h - box) // 2, box, box)

        res = algo_snr.roi_snr(img, rect, background_margin=int(p["background_margin"]))
        if res is None:
            ctx.warn(f"[{self.key}] ROI {rect} 落在影像外或無效，ROI SNR 全部記 0。")
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
