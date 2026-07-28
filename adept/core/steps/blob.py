# ADEPT step-card library — authored 2026-07-28 (M1).
"""blob_segment — Blob 分割卡。

在 SNR 地圖上做門檻 + 連通元件分割，找出候選缺陷區塊：
- meta["blobs"]：全部區塊（plain dict 清單，可序列化）。
- features：blob_count 與「主 blob」（SNR 最強者）的 blob_area /
  blob_aspect / blob_dist_center / blob_snr；一顆都沒有時全部為 0（不算錯誤）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import blob as algo_blob
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_REGION,
)
from ._util import require_image


def _roi_to_dict(r: "algo_blob.DefectROI") -> Dict[str, Any]:
    return {
        "x": int(r.x), "y": int(r.y), "w": int(r.w), "h": int(r.h),
        "cx": float(r.cx), "cy": float(r.cy),
        "area": int(r.area),
        "mean_signal": float(r.mean_signal),
        "snr_value": float(r.snr_value),
        "aspect_ratio": float(r.aspect_ratio),
        "dist_to_center": float(r.dist_to_center),
    }


@register_step
class BlobSegmentStep(Step):
    """Blob 分割：SNR 地圖 → 門檻 → 連通元件 → 候選缺陷清單。"""

    key = "blob_segment"
    label = "Blob segment"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Cut candidate defect blobs out of the SNR map and record the main "
            "blob's area, aspect ratio, distance from centre and SNR.")
    params = [
        ParamSpec(name="source", type="image_key", default="snr_map",
                  help="Input SNR map image stream."),
        ParamSpec(name="diff_source", type="image_key", default="diff",
                  help=("Matching difference image stream, used to measure each "
                        "blob's mean signal.")),
        ParamSpec(name="min_area", type="int", default=4, min=1, max=10000,
                  help=("Minimum area in pixels: anything smaller is treated as "
                        "noise and dropped.")),
        ParamSpec(name="roi_out", type="str", default="blob",
                  help=("Name given to the main blob's region, so Measure "
                        "cards can point at it (leave as 'blob' unless you "
                        "run two Blob segment cards).")),
        ParamSpec(name="snr_threshold", type="float", default=0.0, min=0.0, max=255.0,
                  help=("Segmentation threshold on the 0-255 map scale; "
                        "0 = decide automatically by Otsu (recommended).")),
    ]
    reads = ["snr_map", "diff"]
    writes: List[str] = []
    features_out = ["blob_count", "blob_area", "blob_aspect",
                    "blob_dist_center", "blob_snr"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "snr_map"), params.get("diff_source", "diff")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        snr_img = require_image(ctx, self.key, p["source"])
        diff_img = require_image(ctx, self.key, p["diff_source"])
        if snr_img.shape[:2] != diff_img.shape[:2]:
            raise StepError(self.key, f"'{p['source']}' and '{p['diff_source']}' differ in "
                                      f"size ({snr_img.shape[:2]} vs "
                                      f"{diff_img.shape[:2]}); cannot segment.")
        thr = None if float(p["snr_threshold"]) <= 0.0 else float(p["snr_threshold"])
        rois = algo_blob.segment_defects(
            snr_img, diff_img, min_area=int(p["min_area"]), snr_threshold=thr)

        ctx.meta["blobs"] = [_roi_to_dict(r) for r in rois]
        # F7-4：主 blob 也寫成具名 ROI，讓它跟使用者畫的框走同一條路。
        # meta["blobs"] 保留（overlay 與舊 recipe 還在讀）。
        name = str(p["roi_out"]).strip()
        if name and rois:
            big0 = rois[0]
            h0, w0 = snr_img.shape[:2]
            ctx.set_roi(name, (big0.x / w0, big0.y / h0,
                               max(1, big0.w) / w0, max(1, big0.h) / h0))
        feats = {"blob_count": float(len(rois)),
                 "blob_area": 0.0, "blob_aspect": 0.0,
                 "blob_dist_center": 0.0, "blob_snr": 0.0}
        if rois:
            big = rois[0]     # 主 blob = SNR 最強者（segment_defects 已按 snr 降冪排序）
            feats.update({
                "blob_area": float(big.area),
                "blob_aspect": float(big.aspect_ratio),
                "blob_dist_center": float(big.dist_to_center),
                "blob_snr": float(big.snr_value),
            })
        ctx.add_features(feats)
        return ctx
