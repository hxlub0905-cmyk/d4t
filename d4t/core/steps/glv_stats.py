# d4t step-card library — authored 2026-07-28 (M1).
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
    MultiSourceStep, output_prefix_spec, parse_key_list, roi_pixels,
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
class GlvStatsStep(MultiSourceStep):
    """GLV 統計：整張或中央方框的灰階統計量。"""

    key = "glv_stats"
    label = "Gray-level stats"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Compute gray-level statistics (mean, standard deviation, "
            "percentiles…) inside a region, and write each one out as a "
            "feature.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="test",
                  help="Image stream to compute statistics on."),
        ParamSpec(name="roi", type="region_key", direction="in", default="",
                  label="Region",
                  help=("Which region to measure in - drag a line from the "
                        "Region card that defines it. No line means the "
                        "whole image.")),
        # 勾選而不是用打的（2026-08-14 使用者要求）。清單是常用的那幾個；
        # 手寫 recipe 仍可以放任何 glv_q<0-100>（清單外的值會列出來並勾著）。
        ParamSpec(name="metrics", type="multi_choice",
                  default="glv_mean,glv_std,glv_p50",
                  label="Statistics",
                  choices=["glv_mean", "glv_std", "glv_p50", "glv_min",
                           "glv_max", "glv_q25", "glv_q75", "glv_q90",
                           "glv_q99"],
                  help=("Tick the statistics to output - each becomes a "
                        "feature with the same name. glv_p50 is the median; "
                        "hand-written recipes may also use any percentile "
                        "like glv_q37.")),
        output_prefix_spec("center"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["glv_mean", "glv_std", "glv_p50"]

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi", "") or "").strip()
        return [name] if name else []

    @classmethod
    def feature_names(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", "glv_mean,glv_std,glv_p50"))
        return mids or list(cls.features_out)

    def measure(self, ctx: Context, img, p: Dict[str, Any]):
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
        return feats
