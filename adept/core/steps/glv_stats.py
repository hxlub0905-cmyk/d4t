# ADEPT step-card library — authored 2026-07-28 (M1).
"""glv_stats — 灰階（GLV）統計卡。

metrics 參數是逗號清單，每個 id 產生一個同名 feature：
- 固定集：glv_mean / glv_median / glv_std / glv_min / glv_max / glv_q25 / glv_q75
- 動態分位數：glv_q<NN>（例 glv_q90）
- 別名：glv_p50 = glv_median；glv_p<NN> = glv_q<NN>
feature 名稱「照使用者列的寫」（別名不改名），數值一致。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import numpy as np

from ..algo import glv as algo_glv
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import (
    output_prefix_spec, parse_key_list, prefix_features, roi_pixels,
    prefix_names, require_image,
)

_P_ALIAS = re.compile(r"^glv_p(\d+)$")
_Q_FORM = re.compile(r"^glv_q(\d+)$")


def _canonical(mid: str) -> str:
    """把使用者寫的 metric id 轉成 algo.glv 認得的 id；不認得回傳空字串。"""
    if mid in algo_glv.GLV_STATS:
        return mid
    if mid == "glv_p50":
        return "glv_median"          # 慣用別名：P50 = 中位數
    m = _P_ALIAS.match(mid)
    if m and 0 <= int(m.group(1)) <= 100:
        return f"glv_q{m.group(1)}"  # glv_pNN → glv_qNN
    m = _Q_FORM.match(mid)
    if m and 0 <= int(m.group(1)) <= 100:
        return mid
    return ""


@register_step
class GlvStatsStep(Step):
    """GLV 統計：整張或中央方框的灰階統計量。"""

    key = "glv_stats"
    label = "Gray-level stats"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Compute gray-level statistics (mean, standard deviation, "
            "percentiles…) inside a region, and write each one out as a "
            "feature.")
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  help="Image stream to compute statistics on."),
        ParamSpec(name="roi", type="str", default="",
                  help=("Which region to measure in — the name given by a "
                        "Define region card upstream. Leave empty for the "
                        "whole image.")),
        ParamSpec(name="metrics", type="str", default="glv_mean,glv_std,glv_p50",
                  help=("Statistics to output (comma separated): glv_mean / "
                        "glv_std / glv_median / glv_min / glv_max / glv_q25 / "
                        "glv_q75. Percentiles can be written glv_q90 or glv_p90 "
                        "(glv_p50 = median).")),
        output_prefix_spec("center"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["glv_mean", "glv_std", "glv_p50"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi", "") or "").strip()
        return [name] if name else []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", "glv_mean,glv_std,glv_p50"))
        return prefix_names(params.get("output_prefix", ""),
                            mids or list(cls.features_out))

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        img = require_image(ctx, self.key, p["source"])
        mids = parse_key_list(p["metrics"])
        if not mids:
            raise StepError(self.key, "metrics is empty; list at least one statistic (e.g. glv_mean).")

        # ``roi_pixels`` 而不是 ``crop_to_roi``：統計量只要「有哪些像素」，
        # 所以分散的多個框（F8 的交會處）也答得出來 —— 那正是
        # 「這一組交界整體長什麼樣」這個問題。單框走同一條路。
        patch = roi_pixels(ctx, self.key, img, p["roi"])

        feats: Dict[str, float] = {}
        for mid in mids:
            canon = _canonical(mid)
            if not canon:
                raise StepError(
                    self.key,
                    f"unknown statistic '{mid}'; available: "
                    f"{sorted(algo_glv.GLV_STATS)} or glv_q<0-100> / glv_p<0-100>.")
            feats[mid] = algo_glv.glv_value(patch, canon)   # feature 名照使用者列的寫
        ctx.add_features(prefix_features(p["output_prefix"], feats))
        return ctx
