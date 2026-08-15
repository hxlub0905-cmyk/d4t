# ADEPT step-card library — authored 2026-07-28 (M1).
"""cd_measure — CD 量測卡（M1 簡化版）。

★ M1 簡化說明 ★
CD 的定義是「所指區域的框有多寬 / 多高」：
  cd_x_px = 框寬、cd_y_px = 框高。
這是缺陷尺寸的粗估，不是產線 CD-SEM 等級的線寬量測（真正的
edge-pair / 多取樣線寬量測留待後續 milestone）。refine="subpixel"
時只精修框的上下邊（Y 方向）成次像素，X 方向仍是框寬。

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
    """CD 量測（M1：所指區域的框尺寸；可選次像素上下邊精修）。"""

    key = "cd_measure"
    label = "CD measure"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the width, height and area of a region, in pixels. "
            "Point it at a region defined by an ROI card upstream, or leave "
            "the region empty to measure the whole image. Convert to nm at "
            "export time, where you enter the nm per pixel yourself.")
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="Image stream sampled when refining edges (usually diff)."),
        ParamSpec(name="roi", type="str", default="",
                  help=("Which region to measure — the name given by an ROI "
                        "card upstream. Leave empty for the whole image.")),
        ParamSpec(name="refine", type="choice", default="none",
                  choices=["none", "subpixel"],
                  help=("none = use the bounding box as is; subpixel = refine the "
                        "top and bottom edges to sub-pixel precision (falls back "
                        "to the bounding box on failure).")),
        output_prefix_spec("defect"),
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
        name = str(params.get("roi", "") or "").strip()
        return [name] if name else []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        # 尺寸來源：優先用參數指定的流，否則任何一張都可以。可能一張都沒有 ——
        # 具名區域存的是比例座標，要有影像才展得開，所以這裡不能提早 return。
        shape_src = ctx.images.get(p["source"])
        if shape_src is None:
            shape_src = next(iter(ctx.images.values()), None)

        rect = roi_rect_or_none(ctx, self.key, shape_src, p["roi"])
        if rect is None:
            ctx.warn(f"[{self.key}] there is no image to measure on, so the "
                     f"region could not be turned into pixels; all CD features "
                     f"recorded as 0. Check that the load card upstream ran.")
            ctx.add_features(prefix_features(p["output_prefix"], _ZERO))
            return ctx

        bx, by = float(rect[0]), float(rect[1])
        bw, bh = float(rect[2]), float(rect[3])
        cx = bx + bw / 2.0

        # 面積 = 框的面積。這裡以前會在 ``roi == "blob"`` 時改用
        # ``ctx.meta["blobs"][0]["area"]``（blob 的**真實像素面積**，不是 bbox）——
        # 那個 key 只有 ``blob_segment`` 卡寫，而它在 F8 第五輪被拿掉了，
        # 所以那條分支從那天起永遠走不到。區域現在一律是「框」，面積就是 w*h。
        area_px = bw * bh

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
