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
        blobs = ctx.meta.get("blobs") or []
        if not blobs:
            ctx.warn(f"[{self.key}] meta['blobs'] is empty (run blob_segment "
                     f"first); all CD features recorded as 0.")
            ctx.add_features(dict(_ZERO))
            return ctx

        big = blobs[0]  # 主 blob = SNR 最強者（meta["blobs"] 保留 segment 的 snr 降冪排序）
        bx, by = float(big["x"]), float(big["y"])
        bw, bh = float(big["w"]), float(big["h"])
        cx = float(big.get("cx", bx + bw / 2.0))

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
            feats["area_nm2"] = float(big.get("area", 0)) * npp * npp
        else:
            ctx.warn(f"[{self.key}] meta['nm_per_px'] is not set; nm sizes "
                     f"recorded as 0 (pixel values only).")
        ctx.add_features(feats)
        return ctx
