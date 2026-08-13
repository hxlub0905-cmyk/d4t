# ADEPT step-card library — authored 2026-08-13 (F8).
"""roi_cross —— 兩組正交條紋的交會處 → 一組方框。純規則，不需要外部檔案。

這張卡在解什麼問題
------------------
站點原有兩招定位 ROI，兩招都要外部的東西：GDS（要 .oas）與 Golden Cell
模板（要一張原大圖）。第三招 —— 只看 patch 自己 —— 之前只到 ``roi_profile``，
而那張依設計只吐**一條滿版的條紋**（單軸投影對另一個方向一無所知）。

要框的東西通常在**兩組條紋交會的地方**（直的 Metal Gate × 橫的 EPI），
而且一張 patch 上不只一處。演算法與取捨都寫在 ``algo/grid.py`` 的模組說明裡
（為什麼晶格要排在條紋**中心**而不是邊界、為什麼不用週期估測、
已知 pitch 能做什麼）。這裡只負責把它接成一張卡。

一個名字，好幾個框
------------------
交會處的數量隨影像而異，所以這張卡寫的是**多框區域**（``set_roi_boxes``）。
量統計的卡（``glv_stats``）把它當一個像素母體；要幾何的卡指
``<name>_center`` —— 離 patch 正中心最近的那一塊，也就是**缺陷所在的那一塊**。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import grid as algo_grid
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    FEATURE_PREFIX_PATTERN, output_prefix_spec, prefix_features, prefix_names,
    require_image,
)

_BESIDE = ("beside_vertical", "beside_horizontal")


def _norm(rect, shape) -> tuple:
    """像素矩形 → 正規化 (nx, ny, nw, nh)。"""
    h, w = float(shape[0]), float(shape[1])
    x, y, bw, bh = rect
    return (x / w, y / h, bw / w, bh / h)


@register_step
class RoiCrossStep(Step):
    """交會定位：兩組條紋交叉出格子，在格子上放一組框。"""

    key = "roi_cross"
    label = "Locate regions where patterns cross"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Find the upright stripes and the flat stripes in the image, then "
            "put a box wherever they cross - so the boxes follow the pattern "
            "instead of sitting at fixed spots on the screen. One patch "
            "usually has several crossings, and you get a box on each of them.")
    params = [
        ParamSpec(
            name="source", type="image_key", default="ref",
            label="Find the pattern in",
            help=("Which image stream to look for the pattern in. Use ref: it "
                  "has no defect on it, so nothing interferes with the search, "
                  "and the pair is already aligned - so one set of boxes is "
                  "correct for both images. Locating on test and on ref "
                  "separately would put the boxes in different places, and "
                  "then the difference between them is no longer only the "
                  "defect."),
        ),
        # ---- 直的那組條紋 -------------------------------------------------
        ParamSpec(
            name="vertical_select", type="choice", default="dark",
            choices=list(algo_grid.SELECT_RULES),
            label="Upright stripes are the",
            help=("Which of the up-and-down stripes to use: the darker ones or "
                  "the brighter ones. This is relative to the rest of this "
                  "image, not an absolute gray level, so the same recipe still "
                  "works when the tool drifts."),
        ),
        ParamSpec(
            name="vertical_pitch", type="float", default=0.0, min=0.0,
            max=10000.0, unit="px", label="Upright stripe pitch",
            help=("How far apart the up-and-down stripes are, in pixels. Leave "
                  "0 to measure it from the image. Filling it in (you know it "
                  "from the layout) lets the card check what it found, fill in "
                  "stripes that were too faint or half off the edge, and lock "
                  "on from a single stripe instead of needing several."),
        ),
        ParamSpec(
            name="vertical_sensitivity", type="float", default=0.35, min=0.0,
            max=1.0, label="Upright edge sensitivity",
            help=("How steep a change counts as the edge of an up-and-down "
                  "stripe, compared with the steepest change in this image. "
                  "Lower finds more edges. Watch the panel and drag until the "
                  "lines land where you expect."),
        ),
        # ---- 橫的那組條紋 -------------------------------------------------
        ParamSpec(
            name="horizontal_select", type="choice", default="bright",
            choices=list(algo_grid.SELECT_RULES),
            label="Flat stripes are the",
            help="Same as above, for the stripes that run left to right.",
        ),
        ParamSpec(
            name="horizontal_pitch", type="float", default=0.0, min=0.0,
            max=10000.0, unit="px", label="Flat stripe pitch",
            help=("How far apart the left-to-right stripes are, in pixels. "
                  "Leave 0 to measure it from the image."),
        ),
        ParamSpec(
            name="horizontal_sensitivity", type="float", default=0.35, min=0.0,
            max=1.0, label="Flat edge sensitivity",
            help="Same as above, for the stripes that run left to right.",
        ),
        ParamSpec(
            name="smooth", type="int", default=3, min=1, max=99, unit="px",
            label="Curve smoothing",
            help=("Smooth both curves before looking for edges. Too little and "
                  "image noise becomes false edges; too much and real edges "
                  "get rounded away."),
        ),
        # ---- 框放哪 --------------------------------------------------------
        ParamSpec(
            name="place", type="choice", default="beside_vertical",
            choices=list(algo_grid.PLACEMENTS), label="Put the box",
            help=("crossing = the whole overlap, which contains both "
                  "materials; beside_vertical = a thin box hugging the side of "
                  "each up-and-down stripe, inside a left-to-right stripe - "
                  "that is the boundary between the two, measured on the other "
                  "material; beside_horizontal = the same the other way round; "
                  "between_vertical = the clear gap between two up-and-down "
                  "stripes; between_horizontal = the same the other way round."),
        ),
        ParamSpec(
            name="box_size", type="float", default=5.0, min=1.0, max=1000.0,
            unit="px", label="Box thickness",
            show_when=("place", _BESIDE),
            help=("How thick the box beside the stripe is. Thicker averages "
                  "more pixels but reaches further away from the boundary you "
                  "are actually interested in."),
        ),
        ParamSpec(
            name="side", type="choice", default="both",
            choices=list(algo_grid.SIDES), label="Which side",
            show_when=("place", _BESIDE),
            help=("both = a box on each side of every stripe; start = only the "
                  "left (or upper) side; end = only the right (or lower) side."),
        ),
        ParamSpec(
            name="gap", type="float", default=1.0, min=0.0, max=100.0,
            unit="px", label="Keep clear of the edge",
            help=("How far to stay away from the edge itself. An edge is "
                  "blurred over a few pixels and the gray level there belongs "
                  "to neither material, so measuring it only makes the numbers "
                  "duller. On synthetic data a 5 px box with no clearance took "
                  "one column of the wrong material and read 15% low - and "
                  "that still looks like a perfectly normal number."),
        ),
        ParamSpec(
            name="inset", type="float", default=2.0, min=0.0, max=100.0,
            unit="px", label="Keep clear of the other stripes",
            help=("How far to stay inside the stripe that limits the length of "
                  "the box. A box touching both kinds of edge cannot tell you "
                  "which one caused a change."),
        ),
        # ---- 產出 ----------------------------------------------------------
        ParamSpec(
            name="roi_out", type="str", default="cross",
            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Name for the boxes. Measure cards refer to it by this name. "
                  "You also get <name>_center, which is the single box nearest "
                  "the middle of the patch - that is where the defect is, and "
                  "cards that measure shape rather than statistics need a "
                  "single box."),
        ),
        ParamSpec(
            name="max_boxes", type="int", default=64, min=1, max=4096,
            label="At most this many boxes",
            help=("A guard for images with very fine patterns. The boxes "
                  "nearest the middle are kept, because that is where the "
                  "defect is."),
        ),
        ParamSpec(
            name="min_confidence", type="float", default=5.0, min=0.0,
            max=200.0, label="Give up below",
            help=("How much of each curve must be real signal rather than "
                  "noise. Some patches sit entirely inside one material and "
                  "have nothing to lock onto - those cannot be located by any "
                  "method, so this card falls back to the whole image and "
                  "marks the defect instead of guessing. A featureless patch "
                  "scores about 1; anything with structure scores 20 or more."),
        ),
        output_prefix_spec("cross"),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = ["cross_count", "cross_pitch_x_px", "cross_pitch_y_px",
                    "cross_filled", "cross_dist_px", "locate_conf", "locate_ok"]

    # ---- 宣告（給 lint / UI）------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi_out", "cross") or "").strip()
        return [name, "%s_center" % name] if name else []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return prefix_names(params.get("output_prefix", ""), cls.features_out)

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        name = str(p["roi_out"]).strip()
        if not name:
            raise StepError(self.key, "the region name must not be empty.")

        img = require_image(ctx, self.key, p["source"])
        shape = img.shape[:2]
        res = algo_grid.locate_crossings(
            img,
            vertical_select=str(p["vertical_select"]),
            horizontal_select=str(p["horizontal_select"]),
            vertical_sensitivity=float(p["vertical_sensitivity"]),
            horizontal_sensitivity=float(p["horizontal_sensitivity"]),
            smooth=int(p["smooth"]),
            vertical_pitch=float(p["vertical_pitch"]),
            horizontal_pitch=float(p["horizontal_pitch"]),
            placement=str(p["place"]), box_size=float(p["box_size"]),
            side=str(p["side"]), gap=float(p["gap"]), inset=float(p["inset"]),
            min_confidence=float(p["min_confidence"]),
            max_boxes=int(p["max_boxes"]))

        # panel 用的原始資料。**UI 畫的就是引擎算的這一份** —— UI 自己再算一次
        # 很容易變成「畫面上的框」與「真的量下去的框」不一樣，那種 bug 極難發現。
        ctx.meta.setdefault("crossings", {})[name] = {
            "boxes": [[int(v) for v in b] for b in res.boxes],
            "x": _stripe_meta(res.x),
            "y": _stripe_meta(res.y),
            "confidence": float(res.confidence),
            "ok": bool(res.ok),
            "reason": str(res.reason),
        }

        if not res.ok:
            # 定位不出來就退回整張圖，**而且說出來**。整張都是同一種材質的
            # patch 本來就不需要定位，但那跟「有結構卻沒找到」是兩件事，
            # 使用者必須分得出來自己拿到的是哪一種。
            ctx.warn("[%s] %s; region '%s' falls back to the whole image and "
                     "this defect is marked locate_ok = 0."
                     % (self.key, res.reason or "could not locate the pattern",
                        name))
            whole = (0.0, 0.0, 1.0, 1.0)
            ctx.set_roi_boxes(name, [whole])
            ctx.set_roi("%s_center" % name, whole)
            ctx.add_features(prefix_features(p["output_prefix"], {
                "cross_count": 0.0,
                "cross_pitch_x_px": float(res.x.pitch_measured),
                "cross_pitch_y_px": float(res.y.pitch_measured),
                "cross_filled": 0.0,
                "cross_dist_px": -1.0,
                "locate_conf": float(res.confidence),
                "locate_ok": 0.0,
            }))
            return ctx

        ctx.set_roi_boxes(name, [_norm(b, shape) for b in res.boxes])
        centre = res.center_box
        ctx.set_roi("%s_center" % name, _norm(centre, shape))
        if res.reason:
            ctx.warn("[%s] %s." % (self.key, res.reason))

        cx, cy = shape[1] / 2.0, shape[0] / 2.0
        dist = ((centre[0] + centre[2] / 2.0 - cx) ** 2
                + (centre[1] + centre[3] / 2.0 - cy) ** 2) ** 0.5
        ctx.add_features(prefix_features(p["output_prefix"], {
            "cross_count": float(len(res.boxes)),
            "cross_pitch_x_px": float(res.x.pitch_used),
            "cross_pitch_y_px": float(res.y.pitch_used),
            # 有幾根條紋是靠已知 pitch 補上的（影像上沒抓到）。0 = 每一根都
            # 真的看得到。這個數字大起來時，框仍然對，但「憑什麼對」變成了
            # 那個 pitch —— 使用者有權知道自己站在哪一邊。
            "cross_filled": float(res.x.filled + res.y.filled),
            # 缺陷（永遠在正中心）離最近那個交會有多遠。落在交界上跟落在
            # 兩個交界中間，通常不是同一回事，所以這本身就是可以打分的數字。
            "cross_dist_px": float(dist),
            "locate_conf": float(res.confidence),
            "locate_ok": 1.0,
        }))
        return ctx


def _stripe_meta(s: "algo_grid.StripeSet") -> Dict[str, Any]:
    """一個方向的結果攤成純量與清單（要進 meta，所以不留 numpy 陣列）。"""
    return {
        "axis": s.axis,
        "profile": [float(v) for v in s.profile],
        "raw": [float(v) for v in s.raw],
        # ``transitions`` 是 UI 曲線面板讀的鍵（``roi_profile`` 用同一個名字）。
        # 兩張卡共用同一個面板，所以資料的形狀也要一樣 —— 不然那個面板就得
        # 認得兩種 dict，而那正是「兩條平行的路」的開頭。
        "edges": [int(e) for e in s.edges],
        "transitions": [int(e) for e in s.edges],
        "bands": [[int(a), int(b)] for a, b in s.bands],
        "selected": [[int(a), int(b)] for a, b in s.selected],
        "pitch_measured": float(s.pitch_measured),
        "pitch_used": float(s.pitch_used),
        "pitch_error": float(s.pitch_error),
        "filled": int(s.filled),
        "confidence": float(s.confidence),
    }
