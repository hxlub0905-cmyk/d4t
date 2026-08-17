# ADEPT step-card library — authored 2026-07-28 (M1).
"""cd_measure — CD 量測卡（M1 簡化版）。

★ M1 簡化說明 ★
v1 的 CD 定義是「最大 blob 的 bounding box 寬 / 高」：
  cd_x_px = bbox 寬、cd_y_px = bbox 高。
這是缺陷尺寸的粗估，不是產線 CD-SEM 等級的線寬量測（真正的
edge-pair / 多取樣線寬量測留待後續 milestone）。refine="subpixel"
時只精修 bbox 的上下邊（Y 方向）成次像素，X 方向仍是 bbox 寬。

★ 單位：一律 pixel（2026-07-30 決定）★
這張卡只吐 px。以前它會在 ``meta["nm_per_px"]`` 存在時同步吐
``cd_x_nm`` / ``cd_y_nm`` / ``area_nm2``，但那個值**從來沒有來源**
（KLARF 裡找不到、TIFF 標籤也還沒確認），所以實際上每一顆都是 0 ——
而 0 是個看起來很像答案的答案：它進得了分數表達式、寫得進 DSIZE 欄，
一路安靜到最後。

現在的分工是：**pipeline 全程用 pixel 算，換算只發生在輸出的那一刻，
而且由使用者自己填 nm/px**（Export 精靈的 DSIZE 那一列，見
``adept.core.export.klarf_out`` 的 ``size_scale``）。這樣「這個數字是
幾奈米」這件事有人負責，而不是靠一個猜不到來源的欄位。

舊 recipe 若在分數表達式裡引用了 ``cd_x_nm``，``Recipe.validate()`` 會出
``unknown-feature`` warning 指名那個變數 —— 那正是要看到的（它以前恆為 0）。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import subpixel as algo_subpixel
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, register_step, GROUP_MEASURE,
)
from ._util import (
    output_prefix_spec, prefix_features, prefix_names, roi_rect_or_none,
)

_ZERO = {"cd_x_px": 0.0, "cd_y_px": 0.0, "area_px": 0.0}


@register_step
class CdMeasureStep(Step):
    """CD 量測（M1：最大 blob 的 bbox 尺寸；可選次像素上下邊精修）。"""

    key = "cd_measure"
    label = "CD measure"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the width, height and area of the main defect blob, in "
            "pixels. Currently a bounding-box estimate. Convert to nm at "
            "export time, where you enter the nm per pixel yourself.")
    params = [
        ParamSpec(name="source", type="image_key", direction="in", default="diff",
                  help="Image stream sampled when refining edges (usually diff)."),
        ParamSpec(name="roi", type="str", default="",
                  help=("Which region to measure — the name given by an ROI "
                        "card upstream. Leave empty for the whole image.")),
        ParamSpec(name="refine", type="choice", default="none",
                  choices=["none", "subpixel"],
                  help=("none = use the bounding box as is; subpixel = refine the "
                        "top and bottom edges to sub-pixel precision (falls back "
                        "to the bounding box on failure).")),
        output_prefix_spec("blob"),
    ]
    reads = ["diff"]
    writes: List[str] = []
    features_out = ["cd_x_px", "cd_y_px", "area_px"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "diff")]

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return prefix_names(params.get("output_prefix", ""), cls.features_out)

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi", "blob") or "").strip()
        return [name] if name else []

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
            ctx.add_features(prefix_features(p["output_prefix"], _ZERO))
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

        # 全部 pixel。要 nm 的話在 Export 精靈填 nm/px（見模組 docstring）。
        feats = {"cd_x_px": float(cd_x_px), "cd_y_px": float(cd_y_px),
                 "area_px": float(area_px)}
        ctx.add_features(prefix_features(p["output_prefix"], feats))
        return ctx
