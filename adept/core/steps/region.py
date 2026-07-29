# ADEPT step-card library — authored 2026-07-28 (F7-4).
"""region — Region 段：決定「要看哪裡」。

為什麼 ROI 值得升成一級概念
---------------------------
在 F7-4 之前，ROI 是**藏在每張量測卡裡的參數**（``glv_stats`` 有
``region`` / ``box_size``、``roi_snr`` 有 ``mode`` / ``box_size``）。同一個
「要看哪裡」被複製在好幾張卡上，各自有自己的幾何參數 —— 這正是
``CLAUDE.md`` §7 記載的坑：同一組中心框參數在 128² patch 上準、
換成 256² 就漏抓。

現在改成：Region 卡把 ROI 寫進 ``ctx.rois``（具名），量測卡只說「我要量
哪一個 ROI」。改一次框，所有量測跟著動。

patch 的兩個座標系（重要）
--------------------------
機台的裁切是「**以 defect 座標為正中心，裁 x×x 像素**」，於是：

* **defect frame** —— 原點在 patch 正中心。缺陷永遠在這裡（裁切方式保證的），
  所以中心框、整張圖這類 ROI **跨 defect 穩定**。本卡只做這個座標系。
* **pattern frame** —— 原點在版圖晶格。裁切中心是 defect 而不是晶格，
  所以晶格相位逐顆不同，「量線寬內部」這種 ROI 得先認出晶格在哪。
  那要靠 ``algo/period.py`` 的 ``estimate_period`` / ``choose_origin``，
  **尚未實作**（見 ``docs/plans/F7-canvas-and-taxonomy.md`` §4）。

尺寸單位可以選 ``percent``
--------------------------
``size_unit="percent"`` 時框的大小是**影像邊長的百分比**，所以同一份 recipe
換 patch 尺寸不會失效 —— 那是上面那個坑的正解。預設仍是 ``px``，
因為使用者腦中想的通常是像素。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import require_image

__all__ = ["RegionDefineStep", "center_norm_rect"]


def center_norm_rect(shape: Any, size: float, unit: str = "px") -> tuple:
    """置中方框的正規化矩形 ``(nx, ny, nw, nh)``。

    ``unit="px"`` -> ``size`` 是像素邊長；``unit="percent"`` -> 影像邊長的百分比。
    邊長會夾在 1 像素與整張影像之間，所以參數填爆也不會產生無效的框。
    """
    h, w = int(shape[0]), int(shape[1])
    if str(unit) == "percent":
        pw = w * float(size) / 100.0
        ph = h * float(size) / 100.0
    else:
        pw = ph = float(size)
    pw = max(1.0, min(pw, float(w)))
    ph = max(1.0, min(ph, float(h)))
    nx = max(0.0, (w - pw) / 2.0 / w)
    ny = max(0.0, (h - ph) / 2.0 / h)
    return (nx, ny, pw / w, ph / h)


@register_step
class RegionDefineStep(Step):
    """定義一個具名 ROI（defect 座標系）。"""

    key = "roi_define"
    label = "Define region"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Mark the part of the image that later Measure cards should look "
            "at, and give it a name.")
    params = [
        ParamSpec(name="name", type="str", default="main",
                  help=("Name for this region. Measure cards refer to it by "
                        "this name.")),
        ParamSpec(name="shape", type="choice", default="center",
                  choices=["center", "whole"],
                  help=("center = a box in the middle of the patch, which is "
                        "where the tool put the defect; whole = the entire "
                        "image.")),
        ParamSpec(name="size", type="float", default=32.0, min=1.0, max=100000.0,
                  help="Side length of the centre box (ignored when shape = whole)."),
        ParamSpec(name="size_unit", type="choice", default="px",
                  choices=["px", "percent"],
                  help=("px = size is in pixels; percent = size is a "
                        "percentage of the image side, so the same recipe "
                        "still works when the patch size changes.")),
        ParamSpec(name="source", type="image_key", default="test",
                  help=("Which image stream sets the geometry. Any stream of "
                        "the same size will do; this only decides the size.")),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "test"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("name", "") or "").strip()
        return [name] if name else []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        name = str(p["name"]).strip()
        if not name:
            raise StepError(self.key, "the region name must not be empty.")

        img = require_image(ctx, self.key, p["source"])
        shape = img.shape[:2]
        if str(p["shape"]) == "whole":
            rect = (0.0, 0.0, 1.0, 1.0)
        else:
            rect = center_norm_rect(shape, float(p["size"]), str(p["size_unit"]))

        ctx.set_roi(name, rect)
        x, y, w, h = ctx.roi_rect(name, shape)
        ctx.meta.setdefault("regions", {})[name] = {
            "shape": str(p["shape"]), "rect_px": [int(x), int(y), int(w), int(h)],
        }
        return ctx
