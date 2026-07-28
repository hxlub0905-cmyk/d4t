# ADEPT step-card library — authored 2026-07-28 (M1).
"""align — 對位卡：估計 moving 相對 fixed 的平移並回正。

符號慣例（沿用 algo.align）：moving 內容若在 fixed 的右下方 (dx, dy) 像素，
則回報正的 (dx, dy)，並把 moving 平移 (-dx, -dy) 寫到 out 流。
平坦影像或對位失敗時：警告 + 零位移（原圖照寫到 out），絕不讓整批掛掉。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import align as algo_align
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, register_step,
)
from ._util import require_image


@register_step
class AlignStep(Step):
    """平移對位：phase/hybrid/ncc/ecc/template 後端擇一。"""

    key = "align"
    label = "Align"
    category = CATEGORY_IMAGE
    help = ("Estimate how far ref is shifted from test and move ref back into "
            "alignment, so the later subtraction is not full of false signal.")
    requires_ref = True
    params = [
        ParamSpec(name="moving", type="image_key", default="ref",
                  help="Image stream to be moved into alignment (usually ref)."),
        ParamSpec(name="fixed", type="image_key", default="test",
                  help="Reference stream that stays put (usually test)."),
        ParamSpec(name="method", type="choice", default="phase",
                  choices=["phase", "hybrid", "ncc", "ecc", "template"],
                  help=("Alignment backend: phase = fast and robust (default); "
                        "ncc = exhaustive correlation; ecc = iterative refinement; "
                        "template = central template match; hybrid behaves like phase.")),
        ParamSpec(name="search_radius", type="int", default=8, min=1, max=64,
                  help=("Search radius in pixels: the largest shift you expect. "
                        "Too small and it will not find the shift, too large "
                        "and it gets slow.")),
        ParamSpec(name="out", type="image_key", default="ref_aligned",
                  help="Name of the image stream the aligned result is written to."),
    ]
    reads = ["test", "ref"]
    writes = ["ref_aligned"]
    features_out = ["align_dx", "align_dy", "align_score"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("fixed", "test"), params.get("moving", "ref")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "ref_aligned")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        fixed = require_image(ctx, self.key, p["fixed"])
        moving = require_image(ctx, self.key, p["moving"])
        if fixed.shape[:2] != moving.shape[:2]:
            # 尺寸不合時無法對位：警告 + 零位移，不殺整批
            ctx.warn(f"[{self.key}] '{p['fixed']}' and '{p['moving']}' differ in "
                     f"size ({fixed.shape[:2]} vs {moving.shape[:2]}); "
                     f"using zero shift.")
            res = None
        else:
            try:
                res = algo_align.calculate_alignment(
                    fixed, moving, method=p["method"],
                    search_radius=int(p["search_radius"]))
            except Exception as e:   # 對位絕不讓整批掛掉
                ctx.warn(f"[{self.key}] alignment failed ({e}); using zero shift.")
                res = None

        if res is None or res.status == "fail":
            if res is not None:
                ctx.warn(f"[{self.key}] alignment did not converge "
                         f"(score={res.final_score:.1f}); using zero shift.")
            dx, dy, score = 0.0, 0.0, (res.final_score if res is not None else 0.0)
            aligned = moving.copy()
        else:
            if res.status == "warn":
                ctx.warn(f"[{self.key}] low alignment quality "
                         f"(score={res.final_score:.1f}); treat results with care.")
            dx, dy = float(res.dx_subpixel), float(res.dy_subpixel)
            score = float(res.final_score)
            aligned = algo_align.apply_alignment(moving, dx, dy)

        ctx.set_image(p["out"], aligned)
        ctx.add_features({"align_dx": dx, "align_dy": dy, "align_score": score})
        ctx.meta["align_dx"] = dx
        ctx.meta["align_dy"] = dy
        return ctx
