# ADEPT step-card library — authored 2026-07-28 (M1).
"""snr_map — 區域 z 地圖卡（畫面上叫 **Z-map**）。

把 diff 圖轉成「每個位置的訊號有多突出（幾個 sigma）」的地圖：
影像流 out 存正規化後的 float32 地圖（0–1），feature ``snr_max`` 存
正規化前的原始峰值（sigma 單位），可直接拿去打分。

為什麼畫面上不叫 SNR（2026-08-18，使用者定調）
----------------------------------------------
「SNR map 幫我改名成 Z-map（不然兩個 SNR 會被人搞混）」。這個 repo 裡有兩個
不同的東西都叫 SNR：

* **這一張**：逐像素的局部 z 值（``(x − 局部平均) / 局部標準差``）—— 輸出是
  一張**圖**，答的是「哪裡突出」。
* **`roi_snr` 與 `roi_compare` 的 `snr`**：兩塊區域之間的
  ``(μ_T − μ_R) / σ_R`` —— 輸出是一個**數字**，答的是「這一塊比那一塊亮幾個 σ」。

兩個都對，但擺在同一個卡片庫裡，使用者沒有辦法從名字分出來自己要的是哪一個。
z 值是逐像素那一個在統計上的名字，所以畫面上用它。

**只有 `label` 換掉。** ``key``（`snr_map`）、影像流的預設名字（`snr_map`）與
feature（`snr_max`）都是 **recipe 的鍵**：改了，既有的 recipe 與分數表達式當場
壞掉，而三組黃金值也要重新定錨。使用者要的是「不要搞混」，不是「換一個鍵」。
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
    """區域 z 地圖：局部平均對局部標準差的突出程度（畫面上叫 Z-map）。"""

    key = "snr_map"                 # recipe 的鍵 —— **不改**（見模組說明）
    label = "Z-map"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Turn the difference image into a map of how far each position "
            "stands out from its own surroundings, counted in standard "
            "deviations (a z-map), and report the peak as snr_max. This is a "
            "picture of where something is unusual - not the single "
            "region-against-region number that the ROI SNR and Compare "
            "regions cards report.")
    params = [
        ParamSpec(name="source", type="image_key", direction="in", default="diff",
                  help=("Input difference image stream (usually the diff "
                        "produced by subtract).")),
        ParamSpec(name="window", type="int", default=31, min=5, max=201,
                  help=("Local statistics window size (odd, 5-201): roughly "
                        "2-4x the defect size you expect.")),
        ParamSpec(name="clip_sigma", type="float", default=3.0, min=0.5, max=20.0,
                  help=("Ceiling in standard deviations: the saturation value "
                        "for the map; anything above is clamped here.")),
        ParamSpec(name="clip_percentile", type="float", default=99.5, min=50.0, max=100.0,
                  help=("Normalisation percentile: the value at this "
                        "percentile becomes 1.0 on the map.")),
        ParamSpec(name="exclude_border", type="int", default=16, min=0, max=100,
                  help=("Border exclusion width in pixels: edge statistics are "
                        "unreliable, so they are zeroed to avoid false peaks.")),
        ParamSpec(name="out", type="image_key", direction="out", default="snr_map",
                  help=("Name of the image stream the z-map is written to "
                        "(float32, 0-1).")),
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
