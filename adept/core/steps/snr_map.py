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
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step,
)
from ._util import require_image


@register_step
class SnrMapStep(Step):
    """區域 SNR 地圖：局部平均對局部標準差的突出程度。"""

    key = "snr_map"
    label = "SNR 地圖"
    category = CATEGORY_ALGO
    help = "把差異圖換算成每個位置的訊號突出度（SNR）地圖，並回報全圖峰值 snr_max。"
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="輸入差異圖的影像流（通常是 subtract 產出的 diff）。"),
        ParamSpec(name="window", type="int", default=31, min=5, max=201,
                  help="局部統計視窗大小（5–201 的奇數）：約為預期缺陷大小的 2–4 倍。"),
        ParamSpec(name="clip_sigma", type="float", default=3.0, min=0.5, max=20.0,
                  help="SNR 上限（sigma）：地圖顯示用的飽和值，超過就壓在這裡。"),
        ParamSpec(name="clip_percentile", type="float", default=99.5, min=50.0, max=100.0,
                  help="正規化基準百分位：用此百分位的值當作地圖的 1.0。"),
        ParamSpec(name="exclude_border", type="int", default=16, min=0, max=100,
                  help="邊框排除寬度（像素）：影像邊緣統計不可靠，先清零避免假峰值。"),
        ParamSpec(name="out", type="image_key", default="snr_map",
                  help="SNR 地圖要寫入的影像流名稱（float32、0–1）。"),
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
            raise StepError(self.key, f"window 必須是奇數（收到 {window}）；請改用 {window - 1} 或 {window + 1}。")
        src = require_image(ctx, self.key, p["source"])
        h, w = src.shape[:2]
        if 2 * int(p["exclude_border"]) >= min(h, w):
            raise StepError(self.key, f"exclude_border（{p['exclude_border']}）太大，會把 {w}x{h} 的整張圖清空；請改小。")
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
