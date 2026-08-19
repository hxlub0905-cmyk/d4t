# d4t step-card library — authored 2026-08-18 (F11 Region-3).
"""roi_from_mask —— GLAS 的 **label map** → 一組具名區域。ROI 定位的第三條路。

三條路，三種前提
----------------
| 卡 | 靠什麼定位 | 前提 |
|---|---|---|
| **Template** | Golden Cell 的相位 | layout 有**週期** |
| **Profile** | 影像自己的條紋 | 看得到**條紋** |
| **這一張** | GLAS 匯出的 label map | 有 **GDS** 對好位 |

使用者定調（2026-08-18）：**GDS 的使用時機通常在非週期性重複區域** ——
也就是前兩條路的前提都不成立的地方。所以這張卡**不准借另外兩張的任何東西**：
不做週期估測、不找條紋。那兩套工具就在隔壁，很容易「順手拿來補洞」。

它也不做對位：GLAS 產的 mask 已經是對位完的（使用者原話「我們產的那些 png
mask，都是在已經對位完 no shift 情況下產生」）。所以這張卡沒有搜尋半徑、
沒有分數門檻 —— 它把 label 圖上的形狀原樣搬成區域。

**只吐 ``<name>``，不吐 ``<name>_center`` / ``<name>_others``**
---------------------------------------------------------------
另外兩張卡的 ``_center`` 是「缺陷所在的那一份」，而那是**幾何保證**的
（patch 以缺陷為中心裁切，那些形狀是同一個重複結構的複本）。這條路上兩個前提
都不成立：形狀不是複本、缺陷也不保證在正中央（RSEM 大圖）。硬給的話使用者會
照 Template 的直覺寫 ``epi_center - epi_others`` —— 在一張卡上有意義、在另一張
上是噪音，**而畫面上不會說**。

方向是不對稱的：**之後加一個區域名是免費的，之後拿掉一個會弄壞已經寫好的
recipe。** 所以從窄的開始。要「缺陷所在的那一塊」的那一天，正解是把 KLARF 座標
換算成影像位置（而那會同時影響三張卡），不是在這裡先湊一個。

一層 = 好幾個矩形，而數量比另外兩張卡大一個數量級
------------------------------------------------
幾何在 ``algo/mask.py``（那裡有實測表）。重點：一層**精確**拆出來的矩形數，
實際範圍是幾十到約五千 —— 而既有 Region 卡的 ``max_boxes`` 預設是 **64**，
那是為「重複結構的幾份」設計的，用在這裡會**安靜地砍掉 95%**。

使用者：「max boxes 理想上應該會很多，原因是處理的會是 **RSEM images**
（不是之前的 patch）等級。」對 —— 而「很多」量出來是這樣（1000×1000）：

| 形狀 | pieces | rectangles |
|---|---|---|
| 密集 line/space | 39 | 39 |
| 同上，被另一層橫向切碎 | 975 | 975 |
| 45° 斜帶（`fillPoly` 的 1px 階梯邊）| 10 | **5 295** |
| contact 陣列 6×6/14 | 5 184 | 5 184 |

下游的成本（同一天量的，**每張量測卡每顆各一次**）：
N=1 000 約 3 ms、N=10 000 約 60 ms、N=50 000 約 280 ms、N=200 000 約 1 s。
所以預設 **8192**（蓋得住實測的最壞 5 295 還有餘裕），上限 **65536**
（再上去就是每顆每卡 0.3 s 起跳，400 顆 × 幾張卡會變成用分鐘算的）。

**砍到上限一定要講出來**（`<name>_clipped`）—— 一個少掉一半框的區域仍然
算得出一個很正常的灰階值。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ..algo import mask as algo_mask
from ..ingest.glas_export import SIDECAR_LABEL
from ..pipeline.channels import ChannelMapError, parse_channel_map
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    output_prefix_spec, prefix_features, prefix_names, region_fact_names,
    region_facts, require_image,
)

#: 這張卡**多**寫的那一個（`_util.REGION_FACTS` 的五個之外）。
#:
#: ``pieces`` 是連通元件的個數，而 ``boxes`` 是矩形分解出幾個 —— 只有走 label
#: map 這一條路的卡分得出這兩者（另外兩張卡的框本來就是一塊一個）。兩者差很大
#: 的意思是「這一層正被後面畫的層切碎」，而那是使用者要看得到的事實
#: （真實資料上兩者相等，見 `docs/GLAS-INTERFACE.md` §3.6）。
_EXTRA_REGION_FEATURES = ["pieces"]

#: 這張卡自己的（跟區域無關）。
_CARD_FEATURES = ["layout_ok", "layout_layers"]

#: ``max_boxes`` 的預設與上限 —— 兩個數字都是量出來的，理由見模組說明。
DEFAULT_MAX_BOXES = 8192
LIMIT_MAX_BOXES = 65536


def _layers_of(params: Dict[str, Any]) -> List[Tuple[int, str]]:
    """``layers`` 參數 → ``[(label id, 區域名), …]``。打到一半不准拋。"""
    try:
        return parse_channel_map(params.get("layers", ""), noun="layer")
    except ChannelMapError:
        return []


@register_step
class RoiFromMaskStep(Step):
    """GDS 定位：把 label map 上的每一層變成一個具名區域。"""

    key = "roi_from_mask"
    label = "GDS layers"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Turn the layout label map into named regions - one region per "
            "layer, shaped exactly like the layer is. Use this where the "
            "pattern does not repeat, which is where the other two Region "
            "cards have nothing to lock onto. Nothing is searched for or "
            "aligned here: GLAS already did that, so the shapes land exactly "
            "where the export says they are.")
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in",
            default=SIDECAR_LABEL, section="1 · Which image",
            label="Layout labels",
            help=("The label map stream, from the “Load layout labels” card. "
                  "Every pixel value in it is a layer number - it is not a "
                  "picture of the wafer."),
        ),
        ParamSpec(
            name="layers", type="channel_map", default="", row_kind="labels",
            section="2 · Which layers, and what to call them",
            label="Layer number → region name",
            help=("Which layer numbers to turn into regions, and what to call "
                  "each one. The export knows the layout's own names for them "
                  "(things like L17/D0) and Studio fills those in for you - "
                  "but rename them to something you will recognise, because "
                  "the name becomes the prefix on every number measured in "
                  "that region (epi_glv_mean reads better than "
                  "L17_D0_glv_mean). Layers you leave out simply produce no "
                  "region."),
        ),
        ParamSpec(
            name="min_area", type="int", default=0, min=0, max=1_000_000,
            unit="px", section="2 · Which layers, and what to call them",
            label="Ignore pieces smaller than", advanced=True,
            help=("Drop any separate piece of a layer smaller than this many "
                  "pixels. A layer clipped by the edge of the image can leave "
                  "a sliver a few pixels across, and averaging over it gives a "
                  "number that looks fine and means nothing. Zero keeps "
                  "everything. Whole pieces are dropped, never part of one - "
                  "cutting a corner off a region would change the answer "
                  "without changing how it looks."),
        ),
        output_prefix_spec("gds"),
        ParamSpec(
            name="max_boxes", type="int", default=DEFAULT_MAX_BOXES, min=1,
            max=LIMIT_MAX_BOXES, section="3 · Limits", advanced=True,
            label="At most this many boxes per layer",
            help=("A guard, not a setting you should need to touch. A layer is "
                  "stored as its exact set of rectangles, and a real layer on "
                  "a Review SEM image comes to anywhere from a few dozen to "
                  "about five thousand of them - a diagonal edge alone costs "
                  "one rectangle per row. Past about ten thousand every "
                  "measure card starts costing real time on every defect. If "
                  "this limit ever bites, the boxes nearest the middle are "
                  "kept and <name>_clipped is set to 1 for that defect."),
        ),
    ]
    reads = [SIDECAR_LABEL]
    writes: List[str] = []
    features_out = list(_CARD_FEATURES)

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", SIDECAR_LABEL))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        """**只有 ``<name>``** —— 沒有 ``_center`` / ``_others``（見模組說明）。"""
        return [name for _lid, name in _layers_of(params)]

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        regions = cls.resolve_regions_out(params)
        names = list(_CARD_FEATURES) + region_fact_names(regions)
        for name in regions:
            names.extend("%s_%s" % (name, f) for f in _EXTRA_REGION_FEATURES)
        return prefix_names(params.get("output_prefix", ""), names)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """還沒填名字 ≠ 參數填錯（空字串是合法的值）。"""
        if not _layers_of(params):
            return ["This card has no layers yet. Use “Open GDS export…” on "
                    "the “Load layout labels” card — attaching the export "
                    "fills in the layer numbers and the layout's own names "
                    "for them; then rename them to something you will "
                    "recognise."]
        return []

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        try:
            layers = parse_channel_map(p["layers"], noun="layer")
        except ChannelMapError as e:
            raise StepError(self.key, str(e)) from None
        if not layers:
            raise StepError(
                self.key,
                "no layers are named yet. Use “Open GDS export…” on the "
                "“Load layout labels” card - "
                "attaching the export fills in the layer numbers and names "
                "from it. On the command line, pass --gds <export folder>.")

        img = require_image(ctx, self.key, p["source"])
        arr = np.asarray(img)
        if arr.ndim != 2:
            raise StepError(
                self.key,
                "the layout labels have %d channels; each pixel value IS a "
                "layer number, so this must be a single-channel image."
                % arr.shape[2])
        shape = arr.shape[:2]
        present_ids = set(algo_mask.layer_ids(arr))
        cap = int(p["max_boxes"])

        feats: Dict[str, float] = {}
        found = 0
        for lid, name in layers:
            try:
                rects, piece_of = algo_mask.decompose(arr, lid)
            except algo_mask.MaskError as e:
                raise StepError(self.key, str(e)) from None
            rects, piece_of, dropped = algo_mask.drop_small_pieces(
                rects, piece_of, int(p["min_area"]))
            clipped = len(rects) > cap
            if clipped:
                # 依離中心遠近排序過了（`algo/mask.decompose`），砍掉的是最外圍
                # 的那些。**而且要講出來** —— 少掉一半框的區域仍然算得出一個
                # 很正常的灰階值。
                ctx.warn("[%s] layer %d (%s) has %d boxes, more than the %d "
                         "limit; kept the ones nearest the middle. Raise “At "
                         "most this many boxes per layer”, or raise “Ignore "
                         "pieces smaller than”."
                         % (self.key, lid, name, len(rects), cap))
                rects, piece_of = rects[:cap], piece_of[:cap]
            if dropped:
                ctx.warn("[%s] layer %d (%s): left out %d piece(s) smaller "
                         "than %d px." % (self.key, lid, name, dropped,
                                          int(p["min_area"])))

            if rects:
                ctx.set_roi_boxes(name, algo_mask.to_normalised(rects, shape))
                found += 1
            else:
                # **不退回整張圖。** 那會安靜地量到全部的像素，而那是錯的
                # （同 roi_template 的「區域沒落在這一顆上」）。
                why = ("layer %d is not in this defect's label map at all"
                       % lid) if lid not in present_ids else (
                    "every piece of layer %d was smaller than the %d px "
                    "minimum" % (lid, int(p["min_area"])))
                ctx.warn("[%s] region '%s' is empty on this defect: %s; "
                         "nothing is measured in it here."
                         % (self.key, name, why))
                ctx.meta.setdefault("regions_absent", {})[name] = why

            # 五個數字，跟另外兩張 ROI 卡同一組（`_util.REGION_FACTS`）＋
            # 這張卡多的那一個。這張卡沒有「靠邊丟掉」那個開關，所以
            # `edge_dropped` 恆為 0 —— 那也是一個答案，而下游不必問它是誰找的。
            feats.update(region_facts(ctx, [name], shape, clipped=clipped))
            feats["%s_pieces" % name] = float(len(set(piece_of)))

        feats["layout_ok"] = 1.0 if found else 0.0
        feats["layout_layers"] = float(found)
        ctx.add_features(prefix_features(p["output_prefix"], feats))

        # 儀表用（跟另外兩張 Region 卡同一個慣例）：**UI 畫的就是引擎算的這一份**。
        ctx.meta.setdefault("gds_layers", {})[str(p["source"])] = {
            "shape": [int(v) for v in shape],
            "ids_in_image": sorted(present_ids),
            "layers": [{"id": lid, "name": name,
                        "boxes": int(feats["%s_boxes" % name]),
                        "pieces": int(feats["%s_pieces" % name]),
                        "area_px": int(feats["%s_area_px" % name]),
                        "clipped": bool(feats["%s_clipped" % name])}
                       for lid, name in layers],
        }
        return ctx
