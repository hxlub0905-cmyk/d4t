# d4t step-card library — authored 2026-07-28 (M1).
"""cd_measure — CD 量測卡（M1 簡化版）。

★ M1 簡化說明 ★
CD 的定義是「接進來的那個區域的 bounding box 寬 / 高」：
  cd_x_px = bbox 寬、cd_y_px = bbox 高。
這是缺陷尺寸的粗估，不是產線 CD-SEM 等級的線寬量測。refine="subpixel"
時只精修 bbox 的上下邊（Y 方向）成次像素，X 方向仍是 bbox 寬。

★ 這張卡之後會重做（F16，2026-08-20）★
使用者定調「CD Measurement 部分我們之後獨立一個 session 來重新討論與設計」，
所以這一輪只把它的**名字**（`CD`）與**訊息**修對，演算法一行都沒動。
同一輪也確定**不做 blob 分割** —— 以前這裡的說明與警告都假設上游有一張
「Blob segment」卡，而那張卡從來沒有存在過。

★ 單位：一律 pixel（2026-07-30 決定）★
這張卡只吐 px。以前它會在 ``meta["nm_per_px"]`` 存在時同步吐
``cd_x_nm`` / ``cd_y_nm`` / ``area_nm2``，但那個值**從來沒有來源**
（KLARF 裡找不到、TIFF 標籤也還沒確認），所以實際上每一顆都是 0 ——
而 0 是個看起來很像答案的答案：它進得了分數表達式、寫得進 DSIZE 欄，
一路安靜到最後。

現在的分工是：**pipeline 全程用 pixel 算，換算只發生在輸出的那一刻，
而且由使用者自己填 nm/px**（Export 精靈的 DSIZE 那一列，見
``d4t.core.export.klarf_out`` 的 ``size_scale``）。這樣「這個數字是
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
    MultiSourceStep, output_prefix_spec, roi_rect_or_none,
)

_ZERO = {"cd_x_px": 0.0, "cd_y_px": 0.0, "area_px": 0.0}


@register_step
class CdMeasureStep(MultiSourceStep):
    """CD 量測（M1：接進來那個區域的 bbox 尺寸；可選次像素上下邊精修）。"""

    key = "cd_measure"
    #: ``key`` 不動（recipe 的鍵）。短名是使用者要的（F16）。
    label = "CD"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the width, height and area of the region you point it at, "
            "in pixels. Currently a bounding-box estimate. Convert to nm at "
            "export time, where you enter the nm per pixel yourself.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="diff",
                  help="Image stream sampled when refining edges (usually diff)."),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same statistics measured in both, and every "
                        "number gets its region's name in front of it. "
                        "No line means the whole image.")),
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

    #: 影像不是必要的（見 ``_util.MultiSourceStep.REQUIRE_IMAGE``）。
    REQUIRE_IMAGE = False

    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        # 尺寸來源：優先用接進來的那條流，否則任何一張都可以。
        shape_src = img
        if shape_src is None:
            shape_src = next(iter(ctx.images.values()), None)

        rect = roi_rect_or_none(ctx, self.key, shape_src, p["roi"])
        if rect is None:
            # ⚠ 這句話以前寫「run Blob segment first」，而那張卡**從來沒有存在
            # 過**（F16 使用者定調不做）。叫使用者去按一個不存在的東西，比不講
            # 更糟 —— 所以只留還走得通的那一條路。
            ctx.warn(f"[{self.key}] no region to measure: drag a line from a "
                     f"Region card into “Region”, or leave it empty to measure "
                     f"the whole image; all CD features recorded as 0.")
            return dict(_ZERO)

        bx, by = float(rect[0]), float(rect[1])
        bw, bh = float(rect[2]), float(rect[3])
        cx = bx + bw / 2.0

        # 面積 = 框的面積。以前這裡還有一條「如果 roi 叫 blob 就改讀
        # ctx.meta["blobs"] 的真實像素面積」—— 那份 meta **沒有任何生產者**
        # （F16 清掉），所以那條路每一次都走不到，而它讓人以為有東西在寫它。
        area_px = bw * bh

        cd_x_px = bw
        cd_y_px = bh

        if p["refine"] == "subpixel":
            if img is None:
                ctx.warn(f"[{self.key}] no image on that input; cannot refine "
                         f"to sub-pixel, using the bounding box.")
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
        return feats
