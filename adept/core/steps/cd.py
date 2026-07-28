# ADEPT step-card library — authored 2026-07-28 (M1).
"""cd_measure — CD 量測卡（M1 簡化版）。

★ M1 簡化說明 ★
v1 的 CD 定義是「最大 blob 的 bounding box 寬 / 高」：
  cd_x_px = bbox 寬、cd_y_px = bbox 高。
這是缺陷尺寸的粗估，不是產線 CD-SEM 等級的線寬量測（真正的
edge-pair / 多取樣線寬量測留待後續 milestone）。refine="subpixel"
時只精修 bbox 的上下邊（Y 方向）成次像素，X 方向仍是 bbox 寬。

meta["nm_per_px"] 存在時同步輸出 nm 尺寸（cd_x_nm / cd_y_nm / area_nm2），
否則這三個 feature 為 0 並記警告。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import subpixel as algo_subpixel
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, register_step, GROUP_MEASURE,
)
from ._util import roi_rect_or_none

_ZERO = {"cd_x_px": 0.0, "cd_y_px": 0.0,
         "cd_x_nm": 0.0, "cd_y_nm": 0.0, "area_nm2": 0.0}


@register_step
class CdMeasureStep(Step):
    """CD 量測（M1：最大 blob 的 bbox 尺寸；可選次像素上下邊精修）。"""

    key = "cd_measure"
    label = "CD measure"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the width and height of the main defect blob in pixels "
            "(also in nm when nm_per_px is known). Currently a bounding-box "
            "estimate.")
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="Image stream sampled when refining edges (usually diff)."),
        ParamSpec(name="roi", type="str", default="blob",
                  help=("Which region to measure — the name given by a Blob "
                        "segment or Define region card upstream.")),
        ParamSpec(name="refine", type="choice", default="none",
                  choices=["none", "subpixel"],
                  help=("none = use the bounding box as is; subpixel = refine the "
                        "top and bottom edges to sub-pixel precision (falls back "
                        "to the bounding box on failure).")),
    ]
    reads = ["diff"]
    writes: List[str] = []
    features_out = ["cd_x_px", "cd_y_px", "cd_x_nm", "cd_y_nm", "area_nm2"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "diff")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        # 尺寸來源：優先用參數指定的流，否則任何一張都可以。可能一張都沒有 ——
        # roi="blob" 不需要影像（矩形已是像素座標），所以這裡不能提早 return。
        shape_src = ctx.images.get(p["source"])
        if shape_src is None:
            shape_src = next(iter(ctx.images.values()), None)

        rect = roi_rect_or_none(ctx, self.key, shape_src, p["roi"])
        if rect is None:
            ctx.warn(f"[{self.key}] no blob found (run Blob segment first, or "
                     f"point roi at a Define region card); all CD features "
                     f"recorded as 0.")
            ctx.add_features(dict(_ZERO))
            return ctx

        bx, by = float(rect[0]), float(rect[1])
        bw, bh = float(rect[2]), float(rect[3])
        cx = bx + bw / 2.0

        # 面積：blob 有真實的像素面積（不是 bbox 面積），使用者畫的框則是 w*h。
        blobs = ctx.meta.get("blobs") or []
        area_px = (float(blobs[0].get("area", bw * bh))
                   if (blobs and str(p["roi"]).strip() == "blob") else bw * bh)

        cd_x_px = bw
        cd_y_px = bh

        if p["refine"] == "subpixel":
            img = ctx.images.get(p["source"])
            if img is None:
                ctx.warn(f"[{self.key}] image stream '{p['source']}' does not "
                          f"exist; cannot refine to sub-pixel, using the "
                          f"bounding box.")
            else:
                try:
                    top = algo_subpixel.refine_yedge_subpixel(
                        np.asarray(img), x_center=cx, y_guess=by)
                    bot = algo_subpixel.refine_yedge_subpixel(
                        np.asarray(img), x_center=cx, y_guess=by + bh)
                    if (top.fallback_reason == "" and bot.fallback_reason == ""
                            and bot.y_refined > top.y_refined):
                        cd_y_px = float(bot.y_refined - top.y_refined)
                    else:
                        reason = (top.fallback_reason or bot.fallback_reason
                                  or "edges came out in the wrong order")
                        ctx.warn(f"[{self.key}] sub-pixel refinement did not "
                                     f"succeed ({reason}); using the bounding-box "
                                     f"height.")
                except Exception as e:   # 精修絕不讓量測掛掉
                    ctx.warn(f"[{self.key}] sub-pixel refinement errored "
                             f"({e}); using the bounding-box height.")

        feats = {"cd_x_px": float(cd_x_px), "cd_y_px": float(cd_y_px),
                 "cd_x_nm": 0.0, "cd_y_nm": 0.0, "area_nm2": 0.0}
        npp = ctx.nm_per_px
        if npp is not None and float(npp) > 0:
            npp = float(npp)
            feats["cd_x_nm"] = cd_x_px * npp
            feats["cd_y_nm"] = cd_y_px * npp
            feats["area_nm2"] = area_px * npp * npp
        else:
            ctx.warn(f"[{self.key}] meta['nm_per_px'] is not set; nm sizes "
                     f"recorded as 0 (pixel values only).")
        ctx.add_features(feats)
        return ctx
