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
``<name>_center`` —— 離 patch 正中心最近的那一塊，也就是**缺陷所在的那一塊**；
``<name>_others`` —— 其餘那幾塊，也就是**同一張圖上同材質的基準**
（為什麼要第三個名字、以及為什麼這張卡不指派 target/reference，
見 ``_util.set_region_family``）。

「這一顆有沒有基準」不必另外給一個數字：``cross_count > 1`` 就是。
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
    region_family, require_image, set_region_family,
)

_BESIDE = ("beside_vertical", "beside_horizontal")

#: ``place`` 的五個選項 —— 順序就是圖示列由左到右的順序，所以它跟 ``icons``
#: 那一串必須逐項對齊（``ParamSpec`` 會擋長度不一樣）。
_PLACE = ("crossing", "beside_vertical", "beside_horizontal",
          "between_vertical", "between_horizontal")


def _prefix_in_section() -> ParamSpec:
    """``output_prefix`` 是共用的那一顆，只差要掛在哪一個小標題底下。"""
    spec = output_prefix_spec("cross")
    spec.section = "5 · Name and limits"
    spec.advanced = True          # 只有同型別的量測卡撞名時才要動它
    return spec


def _norm(rect, shape) -> tuple:
    """像素矩形 → 正規化 (nx, ny, nw, nh)。"""
    h, w = float(shape[0]), float(shape[1])
    x, y, bw, bh = rect
    return (x / w, y / h, bw / w, bh / h)


@register_step
class RoiCrossStep(Step):
    """交會定位：兩組條紋交叉出格子，在格子上放一組框。"""

    key = "roi_cross"
    label = "Profile"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Find the upright stripes and the flat stripes in the image, then "
            "put a box wherever they cross - so the boxes follow the pattern "
            "instead of sitting at fixed spots on the screen. One patch "
            "usually has several crossings, and you get a box on each of them.")
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in", default="ref",
            section="1 · Which image",
            label="Find the pattern in",
            help=("Which image stream to look for the pattern in. Use ref: it "
                  "has no defect on it, so nothing interferes with the search, "
                  "and the pair is already aligned - so one set of boxes is "
                  "correct for both images. Locating on test and on ref "
                  "separately would put the boxes in different places, and "
                  "then the difference between them is no longer only the "
                  "defect."),
        ),
        ParamSpec(
            name="smooth", type="int", default=3, min=1, max=99, unit="px",
            section="1 · Which image",
            label="Curve smoothing (both directions)",
            help=("Smooth both curves before looking for edges. Too little and "
                  "image noise becomes false edges; too much and real edges "
                  "get rounded away. This one is shared - it is about how the "
                  "image is read, not about either set of stripes."),
            advanced=True,
        ),
        # ---- 直的那組條紋 -------------------------------------------------
        ParamSpec(
            name="vertical_select", type="choice", default="brightest",
            section="2 · The up-and-down stripes",
            choices=list(algo_grid.SELECT_RULES),
            label="Take the up-and-down stripes that are",
            help=("Which of the up-and-down stripes to use, by rank: brightest "
                  "= the brightest group in this image, second_brightest = the "
                  "next group in, and the same from the dark end. This is "
                  "relative to the rest of this image, not an absolute gray "
                  "level, so the same recipe still works when the tool drifts. "
                  "Use the ranks when the image has more than two materials - "
                  "for example brightest for the metal and second_brightest "
                  "for the layer under it."),
        ),
        ParamSpec(
            name="vertical_kinds", type="int", default=0, min=0, max=6,
            section="2 · The up-and-down stripes",
            label="How many kinds of upright stripe",
            help=("How many different materials run up and down in this image. "
                  "Leave 0 unless the rank above picks up too much. 0 means "
                  "the card assumes just the one kind of stripe plus the space "
                  "between them. Raise it when another material sits on the "
                  "same grid - for example a dark CPODE where a metal gate "
                  "would otherwise be makes it 3 (the gate, the space, the "
                  "CPODE). Getting this wrong is quiet: with two assumed, the "
                  "brightest group takes in the spaces as well, so the card "
                  "finds twice as many stripes at half the pitch."),
        ),
        ParamSpec(
            name="vertical_width", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="Upright stripe width",
            help=("How wide each up-and-down stripe is, in pixels. Leave 0 to "
                  "use the width measured on this image. Filling it in (you "
                  "know it from the layout) means the card only has to find "
                  "the middle of each stripe, and puts the boxes the same "
                  "distance from the drawn edge on every patch - the edge "
                  "sensitivity then decides whether a stripe is found at all, "
                  "not where the box lands. Leave it 0 when the width of the "
                  "stripe is the thing you are measuring."),
        ),
        ParamSpec(
            name="vertical_pitch", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="Upright stripe pitch",
            help=("How far apart the up-and-down stripes are, in pixels. Leave "
                  "0 to measure it from the image. Filling it in (you know it "
                  "from the layout) lets the card check what it found, fill in "
                  "stripes that were too faint or half off the edge, and lock "
                  "on from a single stripe instead of needing several."),
        ),
        ParamSpec(
            name="vertical_pitch_2", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="…and every other one is",
            help=("Only when the spacing alternates between two values - put "
                  "the second spacing here and leave it 0 otherwise. Some "
                  "layouts repeat as wide, narrow, wide, narrow rather than at "
                  "one steady pitch, and a single pitch cannot describe that."),
            advanced=True,
        ),
        ParamSpec(
            name="vertical_sensitivity", type="float", default=0.35, min=0.0,
            section="2 · The up-and-down stripes",
            max=1.0, label="Upright edge sensitivity",
            help=("How steep a change counts as the edge of an up-and-down "
                  "stripe, compared with the steepest change in this image. "
                  "Lower finds more edges. Watch the panel and drag until the "
                  "lines land where you expect."),
            advanced=True,
        ),
        # ---- 橫的那組條紋 -------------------------------------------------
        ParamSpec(
            name="horizontal_select", type="choice", default="brightest",
            section="3 · The left-to-right stripes",
            choices=list(algo_grid.SELECT_RULES),
            label="Take the left-to-right stripes that are",
            help="Same as above, for the stripes that run left to right.",
        ),
        ParamSpec(
            name="horizontal_kinds", type="int", default=0, min=0, max=6,
            section="3 · The left-to-right stripes",
            label="How many kinds of flat stripe",
            help="Same as above, for the stripes that run left to right.",
        ),
        ParamSpec(
            name="horizontal_width", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="Flat stripe width",
            help=("How wide each left-to-right stripe is, in pixels. Leave 0 "
                  "to use the width measured on this image."),
        ),
        ParamSpec(
            name="horizontal_pitch", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="Flat stripe pitch",
            help=("How far apart the left-to-right stripes are, in pixels. "
                  "Leave 0 to measure it from the image."),
        ),
        ParamSpec(
            name="horizontal_pitch_2", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="…and every other one is",
            help=("Only when the spacing alternates between two values - put "
                  "the second spacing here and leave it 0 otherwise."),
            advanced=True,
        ),
        ParamSpec(
            name="horizontal_sensitivity", type="float", default=0.35, min=0.0,
            section="3 · The left-to-right stripes",
            max=1.0, label="Flat edge sensitivity",
            help="Same as above, for the stripes that run left to right.",
            advanced=True,
        ),
        # ---- 框放哪 --------------------------------------------------------
        ParamSpec(
            name="place", type="icon_choice", default="beside_vertical",
            choices=list(_PLACE),
            icons=["place_crossing", "place_beside_v", "place_beside_h",
                   "place_between_v", "place_between_h"],
            choice_help={
                "crossing": "The whole overlap — it contains both materials.",
                "beside_vertical": "A thin box hugging each side of an "
                                   "up-and-down stripe, inside a left-to-right "
                                   "one: the boundary between them, measured on "
                                   "the other material.",
                "beside_horizontal": "The same the other way round.",
                "between_vertical": "The clear gap between two up-and-down "
                                    "stripes.",
                "between_horizontal": "The same the other way round.",
            },
            section="4 · Where the box goes",
            label="Put the box",
            help=("Where the box sits relative to the two sets of stripes. "
                  "The pictures show it: the faint bars are the stripes, the "
                  "solid ones are where the box goes."),
        ),
        ParamSpec(
            name="fill_rule", type="icon_choice", default="skip",
            choices=["fill", "skip", "skip_clear"],
            icons=["fill_fill", "fill_skip", "fill_skip_clear"],
            choice_help={
                "fill": "Assume the stripe is there and box it anyway — for "
                        "when a spot is missing only because the stripe was "
                        "too faint to find.",
                "skip": "Look at what is actually there and leave the spot out "
                        "if it is a different material: a dark CPODE sitting "
                        "where a metal gate would be gets no box.",
                "skip_clear": "The same, and also drop the box on the face of "
                              "each neighbouring stripe that looks at it — the "
                              "material next to a CPODE is not the same thing "
                              "as the material next to a gate.",
            },
            section="4 · Where the box goes",
            label="Where a stripe is missing",
            help=("What to do at a spot where the pitch says a stripe should "
                  "be but the image has none. The dotted bar in each picture "
                  "is that missing stripe. Only has an effect when you filled "
                  "in a pitch."),
        ),
        ParamSpec(
            name="box_size", type="float", default=5.0, min=1.0, max=1000.0,
            section="4 · Where the box goes",
            unit="px", label="Box thickness",
            show_when=("place", _BESIDE),
            help=("How thick the box beside the stripe is. Thicker averages "
                  "more pixels but reaches further away from the boundary you "
                  "are actually interested in."),
        ),
        ParamSpec(
            name="side", type="icon_choice", default="both",
            choices=["both", "start", "end"],
            icons=["side_both", "side_start", "side_end"],
            choice_help={
                "both": "A box on each side of every stripe.",
                "start": "Only the left (or upper) side.",
                "end": "Only the right (or lower) side.",
            },
            section="4 · Where the box goes",
            label="Which side",
            show_when=("place", _BESIDE),
            help="Which side of the stripe the box goes on.",
        ),
        ParamSpec(
            name="gap", type="float", default=1.0, min=0.0, max=100.0,
            section="4 · Where the box goes",
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
            section="4 · Where the box goes",
            unit="px", label="Keep clear of the other stripes",
            help=("How far to stay inside the stripe that limits the length of "
                  "the box. A box touching both kinds of edge cannot tell you "
                  "which one caused a change."),
        ),
        # ---- 產出 ----------------------------------------------------------
        ParamSpec(
            name="roi_out", type="str", default="cross",
            section="5 · Name and limits",
            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Name for the boxes. Measure cards refer to it by this name. "
                  "You also get <name>_center - the single box nearest the "
                  "middle of the patch, which is where the defect is - and "
                  "<name>_others, the rest of them, which is the baseline of "
                  "the same material on the same image."),
        ),
        ParamSpec(
            name="max_boxes", type="int", default=64, min=1, max=4096,
            section="5 · Name and limits",
            label="At most this many boxes",
            help=("A guard for images with very fine patterns. The boxes "
                  "nearest the middle are kept, because that is where the "
                  "defect is."),
            advanced=True,
        ),
        ParamSpec(
            name="min_confidence", type="float", default=5.0, min=0.0,
            section="5 · Name and limits",
            max=200.0, label="Give up below",
            help=("How much of each curve must be real signal rather than "
                  "noise. Some patches sit entirely inside one material and "
                  "have nothing to lock onto - those cannot be located by any "
                  "method, so this card falls back to the whole image and "
                  "marks the defect instead of guessing. A featureless patch "
                  "scores about 1; anything with structure scores 20 or more."),
            advanced=True,
        ),
        _prefix_in_section(),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = ["cross_count", "cross_pitch_x_px", "cross_pitch_y_px",
                    "cross_filled", "cross_dist_px", "cross_pitch_ratio_x",
                    "cross_pitch_ratio_y", "locate_conf", "locate_ok"]

    # ---- 宣告（給 lint / UI）------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        return region_family(params.get("roi_out", "cross"))

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
            vertical_pitch_2=float(p["vertical_pitch_2"]),
            horizontal_pitch=float(p["horizontal_pitch"]),
            horizontal_pitch_2=float(p["horizontal_pitch_2"]),
            vertical_kinds=int(p["vertical_kinds"]),
            horizontal_kinds=int(p["horizontal_kinds"]),
            vertical_width=float(p["vertical_width"]),
            horizontal_width=float(p["horizontal_width"]),
            fill_rule=str(p["fill_rule"]),
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
            set_region_family(ctx, self.key, name, [whole])
            ctx.add_features(prefix_features(p["output_prefix"], {
                "cross_count": 0.0,
                "cross_pitch_x_px": float(res.x.pitch_measured),
                "cross_pitch_y_px": float(res.y.pitch_measured),
                "cross_filled": 0.0,
                "cross_dist_px": -1.0,
                "cross_pitch_ratio_x": float(res.x.pitch_ratio),
                "cross_pitch_ratio_y": float(res.y.pitch_ratio),
                "locate_conf": float(res.confidence),
                "locate_ok": 0.0,
            }))
            return ctx

        norm_boxes = [_norm(b, shape) for b in res.boxes]
        centre = res.center_box
        centre_norm = _norm(centre, shape)
        idx = min(range(len(norm_boxes)),
                  key=lambda k: sum((a - b) ** 2 for a, b
                                    in zip(norm_boxes[k], centre_norm)))
        set_region_family(ctx, self.key, name, norm_boxes, idx)
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
            # **量到的間距 ÷ 填進去的**。1.0 = 一致；0.5 = 挑錯組；0.75 = pitch
            # 本身填錯（例如換了一台 pixel size 不同的機台）。0/1 的
            # ``locate_ok`` 答不出「錯得多嚴重」，而那兩種的下一步不一樣。
            "cross_pitch_ratio_x": float(res.x.pitch_ratio),
            "cross_pitch_ratio_y": float(res.y.pitch_ratio),
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
        # ``edges`` 是還沒精修的整數位置（除錯用）。
        "edges": [int(e) for e in s.edges],
        # ``transitions`` 是曲線面板畫線用的鍵，而它畫的必須是**幾何真的用的
        # 那一組**（精修到次像素的）。以前這裡給的是整數版，於是畫面上的線與
        # 塗色的方塊差半格 —— 使用者的原話是「藍線跟藍框應該要 fit，會不重合
        # 的原因是什麼」。答案的一部分就是「面板畫錯了」。
        "transitions": [float(e) for e in (s.edges_sub or s.edges)],
        "bands": [[int(a), int(b)] for a, b in s.bands],
        "selected": [[int(a), int(b)] for a, b in s.selected],
        "pitch_measured": float(s.pitch_measured),
        # 量到的第二個間距（不交錯就是 0）。面板的「量給我填」讀這兩個。
        "pitch_measured_2": float(s.pitch_measured_2),
        # 給了 pitch 卻沒有用的原因，以及晶格把條紋搬了多遠 —— 後者就是
        # 使用者看到的「藍框跟藍線對不齊」。
        "pitch_note": str(s.pitch_note),
        "snap_shift": float(s.snap_shift),
        "pitch_used": float(s.pitch_used),
        "pitches_used": [float(v) for v in s.pitches_used],
        "pitch_error": float(s.pitch_error),
        # 量到的 ÷ 填進去的。1.0 = 一致；0.5 = 典型的「挑錯組」。
        "pitch_ratio": float(s.pitch_ratio),
        # 有多少比例的線明顯對不上晶格，以及**為什麼這個方向不能信**。
        "misfit": float(s.misfit),
        "trust_note": str(s.trust_note),
        "pitch_disagrees": bool(s.pitch_disagrees),
        "filled": int(s.filled),
        # 晶格上被擋掉的位置（那裡是別的材質）。面板要畫得出來 —— 「這一格
        # 我故意不放」跟「這一格我沒找到」在畫面上看起來一模一樣。
        "blocked": [[float(a), float(b)] for a, b in s.blocked],
        "width_used": float(s.width_used),
        "width_fixed": bool(s.width_fixed),
        "confidence": float(s.confidence),
    }
