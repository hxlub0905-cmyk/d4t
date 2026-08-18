# ADEPT step-card library — authored 2026-07-29 (F7-12); regions reworked 2026-08-18 (F11 Region-1).
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

一張卡標**好幾個區域**，一個區域**好幾個矩形**（F11 Region-1）
--------------------------------------------------------------
以前是四個手打的數字（``roi_x/y/w/h``）加一個名字，也就是一張卡只框得出一個
矩形、一個區域。但站點要的東西不長那樣 —— 使用者的原話：

    「一個 layout 是橫向 EPI 跟直向 MG 交錯，我要的 ROI1 是 EPI 部分扣掉 MG
     交集。」

那個形狀用一個矩形表達不出來，用好幾個就可以（半導體 layout 幾乎都是曼哈頓的
—— F11 §3.3.2 的答案 B）。所以現在是一個 ``regions`` 參數，值是
``ROI1: 0.1,0,0.25,1; 0.62,0,0.25,1 | ROI2: …``（編碼與規則見
``pipeline/cellrois.py``），而框是在 Studio 的模板編輯器上**畫**出來的
—— 四個 0–1 的數字沒有一個地方講得清楚它們相對於什麼，一張圖講得清楚。

框是**整片鋪過去**的，不是只放一份
----------------------------------
使用者標的是重複結構上的一塊，所以那塊在 patch 裡有幾份就量幾份
（``algo/template.roi_boxes_in_patch``）。只取「離缺陷最近的那一份」在
cell 比 patch 小的時候會只量到一根 EPI，其餘的靜靜漏掉。

模板存在 recipe 裡（不是存路徑）
--------------------------------
``template`` 參數存的是**模板本身**（base64 純文字）。存路徑的話，圖被搬走、
被換掉、下個月有人用了另一張大圖，結果會安靜地變 —— 而 recipe 是要交接給別人的
東西，它必須自己就是完整的。

跨 lot 共用是刻意的：同一支 inspection recipe 掃同一塊 scan area，圖案是一樣的。
換一批資料要不要重算模板，是 Studio 在設定時提供的健檢，不是每一顆的執行期行為。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ..algo import template as algo_template
from ..pipeline.cellrois import CellRoiError, parse_cell_rois, region_names
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    output_prefix_spec, prefix_features, prefix_names, require_image,
)

#: ``locate_axis`` -> 哪幾軸要做定位。一維的 layout（垂直條紋）只有 X 有相位，
#: 硬要在另一軸上搜尋只會把峰的突出程度稀釋掉，把「定得出來」誤判成「定不出來」。
_AXES = {"x": (True, False), "y": (False, True), "both": (True, True)}

def _prefix_in_section() -> ParamSpec:
    """``output_prefix`` 是共用的那一顆，只差要掛在哪一個小標題底下。"""
    spec = output_prefix_spec("cell")
    spec.section = "4 · Name and limits"
    spec.advanced = True          # 只有同型別的量測卡撞名時才要動它
    return spec


#: 每個區域固定會有的幾個數字（區域自己的 ``<name>_present`` 另外加）。
_MATCH_FEATURES = ["match_score", "match_margin", "match_structure",
                   "phase_x", "phase_y", "locate_ok"]


@register_step
class RoiTemplateStep(Step):
    """模板定位：把 patch 對回 Golden Cell 的相位，再把標好的框搬過來。"""

    key = "roi_template"
    label = "Template"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Match each patch against one repeating cell of the layout, so "
            "regions marked once on that cell land in the right place on every "
            "patch - even when the patch is smaller than one cell.")
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in", default="ref",
            section="1 · Which image",
            label="Match on",
            help=("Which image stream to match against the template. Use ref: "
                  "it has no defect on it, so nothing is interfering with the "
                  "match, and the pair is already aligned so the answer applies "
                  "to test as well."),
        ),
        ParamSpec(
            name="template", type="template", default="",
            section="2 · The repeating cell",
            label="Template",
            help=("The repeating cell this card matches against, stored inside "
                  "the recipe as text so the recipe stays a single file you can "
                  "hand to someone else. Build it from a full-size image in "
                  "Studio - there is nothing useful to type here by hand."),
        ),
        ParamSpec(
            name="locate_axis", type="choice", default="x",
            choices=["x", "y", "both"],
            section="2 · The repeating cell",
            label="Locate across",
            help=("Which direction the layout repeats in. x = vertical stripes "
                  "(the usual case); y = horizontal stripes; both = a cell that "
                  "repeats in two directions. Searching a direction that does "
                  "not repeat only makes the match less certain, and a region's "
                  "position along that direction is not used at all - the boxes "
                  "span the whole patch that way."),
        ),
        ParamSpec(
            name="regions", type="cell_rois", default="",
            section="3 · The regions marked on it",
            label="Regions",
            help=("The regions you marked on the cell, and where each one sits "
                  "on it. A region can be several rectangles - that is how a "
                  "shape like 'the EPI minus where the MG crosses it' is "
                  "expressed. Draw them on the cell in Studio; the positions "
                  "are fractions of one cell, not of the patch."),
        ),
        _prefix_in_section(),
        ParamSpec(
            name="max_boxes", type="int", default=64, min=1, max=4096,
            section="4 · Name and limits",
            label="At most this many boxes per region",
            help=("A guard for patterns that repeat very finely: one region can "
                  "land many times on one patch. The boxes nearest the middle "
                  "are kept, because that is where the defect is."),
            advanced=True,
        ),
        ParamSpec(
            name="min_score", type="float", default=0.3, min=-1.0, max=1.0,
            section="5 · When a defect cannot be located",
            label="Minimum match",
            help=("How well the patch must match the template at all. This is "
                  "brightness-independent, so it does not need retuning when "
                  "the gain changes."),
            advanced=True,
        ),
        ParamSpec(
            name="min_margin", type="float", default=0.05, min=0.0, max=2.0,
            section="5 · When a defect cannot be located",
            label="Minimum certainty",
            help=("How much better the best position must be than the next "
                  "best one. A patch with nothing distinctive on it matches "
                  "every position equally well - that scores near 0 here, and "
                  "is the signal that this defect cannot be located."),
            advanced=True,
        ),
        ParamSpec(
            name="min_structure", type="float", default=5.0, min=0.0, max=200.0,
            section="5 · When a defect cannot be located",
            label="Give up below",
            help=("How much structure the patch itself must have. A patch that "
                  "sits entirely inside one material has nothing to match, and "
                  "no threshold on the match score can tell that apart from "
                  "luck - pure noise scores surprisingly well against any "
                  "template. Measured: a featureless patch scores about 1, "
                  "anything with structure scores 20 or more."),
            advanced=True,
        ),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = list(_MATCH_FEATURES)

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        """每個區域一個名字，多框的再加一個 ``<name>_center``。

        ``_center`` 跟 ``roi_cross`` 是同一個約定：要**幾何**的卡（量 CD、量框
        本身）拿不到「一個矩形」時該指名單一的框，而那一塊就是離 patch 正中心
        最近的一塊 —— 缺陷所在的那一塊。兩張卡對這件事的說法要一致。
        """
        out: List[str] = []
        for name in region_names(params.get("regions", "")):
            out.extend([name, "%s_center" % name])
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        names = list(_MATCH_FEATURES)
        for name in region_names(params.get("regions", "")):
            names.append("%s_present" % name)
        return prefix_names(params.get("output_prefix", ""), names)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """還沒設定完 ≠ 參數填錯。

        空字串是完全合法的值，所以參數檢查沒話說 —— 但這張卡跑起來**每一顆**
        都會失敗。使用者以前要跑過一次才知道，而且那時已經等完 200 顆了。
        """
        out: List[str] = []
        if not str(params.get("template", "") or "").strip():
            out.append("This card has no template yet. Select it and use "
                       "“Edit template & regions…” — a template is an image, "
                       "it cannot be typed in.")
        elif not region_names(params.get("regions", "")):
            out.append("This card has a template but no regions marked on it. "
                       "Select it, open “Edit template & regions…” and draw at "
                       "least one region on the cell.")
        return out

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        try:
            regions = parse_cell_rois(p["regions"])
        except CellRoiError as e:                       # pragma: no cover
            raise StepError(self.key, str(e)) from None
        if not regions:
            raise StepError(
                self.key,
                "no regions are marked on the cell yet. Select this card in "
                "Studio and use “Edit template & regions…” — the regions are "
                "drawn on the cell, they cannot be typed in by hand.")

        cell = algo_template.decode_cell(str(p["template"]))
        if cell is None or cell.size == 0:
            # 沒有模板不是「跑不出好結果」，是**還沒設定完**。講清楚要去哪裡設，
            # 不要讓使用者對著一個空白參數猜。
            raise StepError(
                self.key,
                "no template yet. Select this card in Studio and use “Edit "
                "template & regions…” — the template cannot be typed in by "
                "hand.")

        img = require_image(ctx, self.key, p["source"])
        axes = _AXES[str(p["locate_axis"])]
        match = algo_template.match_patch(
            cell, img, min_score=float(p["min_score"]),
            min_margin=float(p["min_margin"]),
            min_structure=float(p["min_structure"]), periodic=axes)

        shape = np.asarray(img).shape[:2]
        ph, pw = int(shape[0]), int(shape[1])
        feats: Dict[str, float] = {
            "match_score": float(match.score),
            "match_margin": float(match.margin),
            "match_structure": float(match.structure),
            "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
            "locate_ok": 1.0 if match.ok else 0.0,
        }

        for name, norm_boxes in regions:
            boxes = self._place(ctx, name, norm_boxes, match, cell.shape,
                                (ph, pw), axes, int(p["max_boxes"]))
            feats["%s_present" % name] = 1.0 if boxes else 0.0
            # panel 用（跟 roi_cross 同一個慣例）：**UI 畫的就是引擎算的這一份**。
            # UI 自己再算一次很容易變成「畫面上的框」與「真的量下去的框」不一樣，
            # 那種 bug 極難發現。
            ctx.meta.setdefault("templates", {})[name] = {
                "cell_w": int(cell.shape[1]), "cell_h": int(cell.shape[0]),
                "phase_x": int(match.phase_x), "phase_y": int(match.phase_y),
                "score": float(match.score), "margin": float(match.margin),
                "structure": float(match.structure),
                "ok": bool(match.ok), "axis": str(p["locate_axis"]),
                "norm": [[float(v) for v in b] for b in norm_boxes],
                "boxes": [[int(v) for v in b] for b in boxes],
            }

        ctx.add_features(prefix_features(p["output_prefix"], feats))
        return ctx

    # ---- 一個區域 -----------------------------------------------------------
    def _place(self, ctx: Context, name: str,
               norm_boxes: List[Tuple[float, float, float, float]],
               match: Any, cell_shape: Tuple[int, int],
               patch_shape: Tuple[int, int], axes: Tuple[bool, bool],
               max_boxes: int) -> List[Tuple[int, int, int, int]]:
        """一個區域的框搬到這張 patch 上，並寫進 ``ctx``。回傳實際放下的框。"""
        ph, pw = patch_shape
        if not match.ok:
            # 相位定不出來就沒有「哪一格」可言 —— 退回整張圖，並把這一顆標記
            # 起來（``locate_ok`` = 0）。這不是猜一個位置，是明講「這一顆的
            # 區域沒有意義」，下游才有機會把它挑掉。
            ctx.warn(
                "[%s] could not place '%s' on this defect (match %.2f, "
                "certainty %.2f); the region falls back to the whole image and "
                "this defect is marked locate_ok = 0."
                % (self.key, name, match.score, match.margin))
            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
            ctx.set_roi("%s_center" % name, (0.0, 0.0, 1.0, 1.0))
            return []

        boxes: List[Tuple[int, int, int, int]] = []
        for norm in norm_boxes:
            boxes.extend(algo_template.roi_boxes_in_patch(
                norm, match, cell_shape, patch_shape, periodic=axes,
                max_boxes=max_boxes))
        # 一個區域的每一塊各自鋪出去之後總數才封頂 —— 留中間的那些（缺陷在
        # 正中央，同 ``roi_cross`` 的 max_boxes）。
        if len(boxes) > max_boxes:
            cx, cy = pw / 2.0, ph / 2.0
            boxes.sort(key=lambda b: ((b[0] + b[2] / 2.0 - cx) ** 2
                                      + (b[1] + b[3] / 2.0 - cy) ** 2))
            boxes = boxes[:max_boxes]

        if not boxes:
            # 模板比 patch 大的時候這是**正常**的：這一顆的窗剛好沒蓋到這個
            # 區域。不要退回整張圖 —— 那會安靜地量到全部的像素，而那是錯的。
            # 講出來、記進 ``regions_absent``，量測卡才報得出真正的原因。
            ctx.warn("[%s] region '%s' does not land on this defect (the "
                     "template is larger than the patch, so this patch only "
                     "sees part of the cell); nothing is measured in it here."
                     % (self.key, name))
            ctx.meta.setdefault("regions_absent", {})[name] = (
                "it is marked on a part of the cell that this patch does not "
                "cover")
            return []

        ctx.set_roi_boxes(name, [(x / pw, y / ph, w / pw, h / ph)
                                 for x, y, w, h in boxes])
        cx, cy = pw / 2.0, ph / 2.0
        centre = min(boxes, key=lambda b: ((b[0] + b[2] / 2.0 - cx) ** 2
                                           + (b[1] + b[3] / 2.0 - cy) ** 2))
        x, y, w, h = centre
        ctx.set_roi("%s_center" % name, (x / pw, y / ph, w / pw, h / ph))
        return boxes

