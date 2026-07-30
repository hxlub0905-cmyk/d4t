# ADEPT step-card library — authored 2026-07-29 (F7-12).
"""roi_template —— 用 Golden Cell 模板把每張 patch 對回版圖的相位，再放框。

跟投影定位（``roi_profile``）的分工
-----------------------------------
兩張卡解的是同一個問題（結構在每張 patch 裡的位置不一樣），差別在**資訊從哪來**：

* **投影定位**只看 patch 自己。便宜、不需要任何額外檔案，但只有在 patch 裡看得到
  地標時才定得出來。
* **模板定位**（這張）用大圖疊出來的一個完整週期當模板。patch 比週期小也沒關係
  —— 是把小 patch 滑進大模板，不是把小片互相對位。

模板長什麼樣、為什麼原點要錨在地標上、信心值為什麼看的是「峰有多突出」而不是
分數本身 —— 全部寫在 ``algo/template.py`` 的模組說明裡。

模板存在 recipe 裡（不是存路徑）
--------------------------------
``template`` 參數存的是**模板本身**（base64 純文字）。存路徑的話，圖被搬走、
被換掉、下個月有人用了另一張大圖，結果會安靜地變 —— 而 recipe 是要交接給別人的
東西，它必須自己就是完整的。

跨 lot 共用是刻意的：同一支 inspection recipe 掃同一塊 scan area，圖案是一樣的。
換一批資料要不要重算模板，是 Studio 在設定時提供的健檢，不是每一顆的執行期行為。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import template as algo_template
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    FEATURE_PREFIX_PATTERN, output_prefix_spec, prefix_features, prefix_names,
    require_image,
)

#: ``locate_axis`` -> 哪幾軸要做定位。一維的 layout（垂直條紋）只有 X 有相位，
#: 硬要在另一軸上搜尋只會把峰的突出程度稀釋掉，把「定得出來」誤判成「定不出來」。
_AXES = {"x": (True, False), "y": (False, True), "both": (True, True)}


@register_step
class RoiTemplateStep(Step):
    """模板定位：把 patch 對回 Golden Cell 的相位，再把標好的框搬過來。"""

    key = "roi_template"
    label = "Locate region by template"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Match each patch against one repeating cell of the layout, so a "
            "region marked once on that cell lands in the right place on every "
            "patch - even when the patch is smaller than one cell.")
    params = [
        ParamSpec(
            name="source", type="image_key", default="ref",
            label="Match on",
            help=("Which image stream to match against the template. Use ref: "
                  "it has no defect on it, so nothing is interfering with the "
                  "match, and the pair is already aligned so the answer applies "
                  "to test as well."),
        ),
        ParamSpec(
            name="template", type="template", default="",
            label="Template",
            help=("The repeating cell this card matches against, stored inside "
                  "the recipe as text so the recipe stays a single file you can "
                  "hand to someone else. Build it from a full-size image in "
                  "Studio - there is nothing useful to type here by hand."),
        ),
        ParamSpec(
            name="locate_axis", type="choice", default="x",
            choices=["x", "y", "both"],
            label="Locate across",
            help=("Which direction the layout repeats in. x = vertical stripes "
                  "(the usual case); y = horizontal stripes; both = a cell that "
                  "repeats in two directions. Searching a direction that does "
                  "not repeat only makes the match less certain."),
        ),
        ParamSpec(name="roi_x", type="float", default=0.0, min=0.0, max=1.0,
                  label="Region left",
                  help="Left edge of the region on the cell, 0 = the cell's left edge."),
        ParamSpec(name="roi_y", type="float", default=0.0, min=0.0, max=1.0,
                  label="Region top",
                  help="Top edge of the region on the cell."),
        ParamSpec(name="roi_w", type="float", default=1.0, min=0.01, max=1.0,
                  label="Region width",
                  help="Width of the region as a fraction of one cell."),
        ParamSpec(name="roi_h", type="float", default=1.0, min=0.01, max=1.0,
                  label="Region height",
                  help="Height of the region as a fraction of one cell."),
        ParamSpec(
            name="roi_out", type="str", default="cell",
            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help="Name for the region. Measure cards refer to it by this name.",
        ),
        ParamSpec(
            name="min_score", type="float", default=0.3, min=-1.0, max=1.0,
            label="Minimum match",
            help=("How well the patch must match the template at all. This is "
                  "brightness-independent, so it does not need retuning when "
                  "the gain changes."),
        ),
        ParamSpec(
            name="min_margin", type="float", default=0.05, min=0.0, max=2.0,
            label="Minimum certainty",
            help=("How much better the best position must be than the next "
                  "best one. A patch with nothing distinctive on it matches "
                  "every position equally well - that scores near 0 here, and "
                  "is the signal that this defect cannot be located."),
        ),
        ParamSpec(
            name="min_structure", type="float", default=5.0, min=0.0, max=200.0,
            label="Give up below",
            help=("How much structure the patch itself must have. A patch that "
                  "sits entirely inside one material has nothing to match, and "
                  "no threshold on the match score can tell that apart from "
                  "luck - pure noise scores surprisingly well against any "
                  "template. Measured: a featureless patch scores about 1, "
                  "anything with structure scores 20 or more."),
        ),
        output_prefix_spec("cell"),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = ["match_score", "match_margin", "match_structure",
                    "phase_x", "phase_y", "locate_ok"]

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi_out", "cell") or "").strip()
        return [name] if name else []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return prefix_names(params.get("output_prefix", ""), cls.features_out)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """沒有模板 = 還沒設定完，而不是「參數填錯」。

        空字串是完全合法的 str，所以參數檢查沒話說 —— 但這張卡跑起來**每一顆**
        都會失敗。使用者以前要跑過一次才知道，而且那時已經等完 200 顆了。
        """
        if str(params.get("template", "") or "").strip():
            return []
        return ["This card has no template yet. Select it and use “Build "
                "template from a full-size image…” — a template is an image, "
                "it cannot be typed in."]

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        name = str(p["roi_out"]).strip()
        if not name:
            raise StepError(self.key, "the region name must not be empty.")

        cell = algo_template.decode_cell(str(p["template"]))
        if cell is None or cell.size == 0:
            # 沒有模板不是「跑不出好結果」，是**還沒設定完**。講清楚要去哪裡設，
            # 不要讓使用者對著一個空白參數猜。
            raise StepError(
                self.key,
                "no template yet. Select this card in Studio and use “Build "
                "template from a full-size image…” — the template cannot be "
                "typed in by hand.")

        img = require_image(ctx, self.key, p["source"])
        axes = _AXES[str(p["locate_axis"])]
        match = algo_template.match_patch(
            cell, img, min_score=float(p["min_score"]),
            min_margin=float(p["min_margin"]),
            min_structure=float(p["min_structure"]), periodic=axes)

        norm = (float(p["roi_x"]), float(p["roi_y"]),
                float(p["roi_w"]), float(p["roi_h"]))
        shape = np.asarray(img).shape[:2]

        # panel 用（跟 roi_profile 同一個慣例）：UI 畫的就是引擎算的這一份
        ctx.meta.setdefault("templates", {})[name] = {
            "cell_w": int(cell.shape[1]), "cell_h": int(cell.shape[0]),
            "phase_x": int(match.phase_x), "phase_y": int(match.phase_y),
            "score": float(match.score), "margin": float(match.margin),
            "structure": float(match.structure),
            "ok": bool(match.ok), "norm": [float(v) for v in norm],
            "axis": str(p["locate_axis"]),
        }

        if not match.ok:
            ctx.warn(
                f"[{self.key}] could not place '{name}' on this defect "
                f"(match {match.score:.2f}, certainty {match.margin:.2f}); "
                f"the region falls back to the whole image and this defect is "
                f"marked locate_ok = 0.")
            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
            ctx.add_features(prefix_features(p["output_prefix"], {
                "match_score": float(match.score),
                "match_margin": float(match.margin),
                "match_structure": float(match.structure),
                "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
                "locate_ok": 0.0,
            }))
            return ctx

        x, y, w, h = algo_template.roi_in_patch(
            norm, match, cell.shape, shape, periodic=axes)

        # 落在 patch 外面的部分裁掉。一個 cell 可能有一半在框外 —— 那是正常的
        # （缺陷靠邊時本來就會這樣），但剩下的必須還有東西可以量。
        ph, pw = int(shape[0]), int(shape[1])
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(pw, int(x) + int(w)), min(ph, int(y) + int(h))
        if x1 <= x0 or y1 <= y0:
            ctx.warn(f"[{self.key}] region '{name}' lands completely outside "
                     f"this patch; falling back to the whole image "
                     f"(locate_ok = 0).")
            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
            ctx.add_features(prefix_features(p["output_prefix"], {
                "match_score": float(match.score),
                "match_margin": float(match.margin),
                "match_structure": float(match.structure),
                "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
                "locate_ok": 0.0,
            }))
            return ctx

        ctx.set_roi(name, (x0 / pw, y0 / ph, (x1 - x0) / pw, (y1 - y0) / ph))
        ctx.add_features(prefix_features(p["output_prefix"], {
            "match_score": float(match.score),
            "match_margin": float(match.margin),
            "match_structure": float(match.structure),
            "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
            "locate_ok": 1.0,
        }))
        return ctx
