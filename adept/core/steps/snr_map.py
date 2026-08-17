# ADEPT step-card library — authored 2026-07-28 (M1).
"""snr_map — 區域 SNR 地圖卡。

把 diff 圖轉成「每個位置的訊號有多突出（幾個 sigma）」的地圖：
影像流 out 存正規化後的 float32 地圖（0–1），feature ``snr_max`` 存
正規化前的原始 SNR 峰值（sigma 單位），可直接拿去打分。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import snr as algo_snr
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import require_image


@register_step
class SnrMapStep(Step):
    """區域 SNR 地圖：局部平均對局部標準差的突出程度。"""

    key = "snr_map"
    label = "SNR map"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Turn the difference image into a map of how much the signal "
            "stands out at each position (SNR), and report the peak as "
            "snr_max.")
    params = [
        ParamSpec(name="source", type="image_key", direction="in", default="diff",
                  help=("Input difference image stream (usually the diff "
                        "produced by subtract).")),
        ParamSpec(name="window", type="int", default=31, min=5, max=201,
                  help=("Local statistics window size (odd, 5-201): roughly "
                        "2-4x the defect size you expect.")),
        ParamSpec(name="clip_sigma", type="float", default=3.0, min=0.5, max=20.0,
                  help=("SNR ceiling in sigma: the saturation value for the "
                        "map; anything above is clamped here.")),
        ParamSpec(name="clip_percentile", type="float", default=99.5, min=50.0, max=100.0,
                  help=("Normalisation percentile: the value at this "
                        "percentile becomes 1.0 on the map.")),
        ParamSpec(name="exclude_border", type="int", default=16, min=0, max=100,
                  help=("Border exclusion width in pixels: edge statistics are "
                        "unreliable, so they are zeroed to avoid false peaks.")),
        ParamSpec(name="out", type="image_key", direction="out", default="snr_map",
                  help="Name of the image stream the SNR map is written to (float32, 0-1)."),
    ]
    reads = ["diff"]
    writes = ["snr_map"]
    features_out = ["snr_max"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "diff")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "snr_map")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        window = int(p["window"])
        if window % 2 == 0:
            raise StepError(self.key, f"window must be odd (got {window}); use {window - 1} or "
                        f"{window + 1}.")
        src = require_image(ctx, self.key, p["source"])
        h, w = src.shape[:2]
        if 2 * int(p["exclude_border"]) >= min(h, w):
            raise StepError(self.key, f"exclude_border ({p['exclude_border']}) is too large — it "
                        f"would blank the whole {w}x{h} image; use a smaller value.")
        res = algo_snr.compute_snr_map(
            src,
            window_size=window,
            clip_sigma=float(p["clip_sigma"]),
            clip_percentile=float(p["clip_percentile"]),
            exclude_border=int(p["exclude_border"]),
        )
        ctx.set_image(p["out"], res.map_float)
        ctx.add_feature("snr_max", res.snr_max)
        return ctx
