# FlexADC step-card library — authored 2026-07-28 (M1).
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
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step,
)
from ._util import parse_key_list, require_image

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
    label = "灰階統計"
    category = CATEGORY_ALGO
    help = "算影像（整張或中央方框）的灰階統計量（平均、標準差、分位數…），逐項寫成 feature。"
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  help="要統計的影像流。"),
        ParamSpec(name="region", type="choice", default="full",
                  choices=["full", "center"],
                  help="full=整張影像；center=只算中央方框（大小由 box_size 決定）。"),
        ParamSpec(name="box_size", type="int", default=32, min=2, max=1024,
                  help="center 模式的方框邊長（像素）。"),
        ParamSpec(name="metrics", type="str", default="glv_mean,glv_std,glv_p50",
                  help="要輸出的統計項（逗號清單）：glv_mean/glv_std/glv_median/glv_min/glv_max/glv_q25/glv_q75，分位數可寫 glv_q90 或 glv_p90（glv_p50=中位數）。"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["glv_mean", "glv_std", "glv_p50"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", "glv_mean,glv_std,glv_p50"))
        return mids or list(cls.features_out)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        img = require_image(ctx, self.key, p["source"])
        mids = parse_key_list(p["metrics"])
        if not mids:
            raise StepError(self.key, "metrics 是空的；請至少列一個統計項（例：glv_mean）。")

        if p["region"] == "center":
            h, w = img.shape[:2]
            box = min(int(p["box_size"]), h, w)
            y0 = (h - box) // 2
            x0 = (w - box) // 2
            patch = img[y0:y0 + box, x0:x0 + box]
        else:
            patch = img
        patch = np.asarray(patch)

        feats: Dict[str, float] = {}
        for mid in mids:
            canon = _canonical(mid)
            if not canon:
                raise StepError(
                    self.key,
                    f"看不懂的統計項 '{mid}'；可用：{sorted(algo_glv.GLV_STATS)} 或 glv_q<0-100> / glv_p<0-100>。")
            feats[mid] = algo_glv.glv_value(patch, canon)   # feature 名照使用者列的寫
        ctx.add_features(feats)
        return ctx
