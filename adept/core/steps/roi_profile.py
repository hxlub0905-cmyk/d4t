# ADEPT step-card library — authored 2026-07-29 (F7-11).
"""roi_profile —— 用一維投影找出結構，再從結構上切出具名區域。

這張卡在解什麼問題
------------------
patch 是機台**以缺陷為正中心**裁出來的，所以缺陷永遠在中央 —— 但缺陷**周圍**
的東西每張都不一樣：同一批裡有的缺陷落在結構正中間，有的靠邊，有的旁邊就是
另一種材質。於是「中心固定框」只對缺陷本身成立；只要框大過缺陷，它就可能在
某些 patch 上吃進別種材質，量出來的數字忽高忽低，而**變動的原因不是缺陷**。

所以要先找到結構在哪，再把框放在**結構的**某個位置上，而不是畫面的某個位置。

做法與取捨都寫在 ``algo/profile.py`` 的模組說明裡（為什麼找轉折而不是分材質、
為什麼在 ref 上做、什麼時候一定會失敗）。這裡只負責把它接成一張卡。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import profile as algo_profile
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
)
from ._util import (
    FEATURE_PREFIX_PATTERN, output_prefix_spec, prefix_features, prefix_names,
    require_image,
)


def _band_rect(band, length: int, axis: str):
    """一段（沿投影方向的 [start, end)）→ 正規化矩形 (nx, ny, nw, nh)。

    另一個方向取滿：投影只知道「沿著這條軸的哪一段」，對另一個方向一無所知，
    硬給一個高度等於憑空捏造資訊。
    """
    a, b = int(band[0]), int(band[1])
    n = max(1, int(length))
    lo, span = a / n, max(1, b - a) / n
    if str(axis) == algo_profile.AXIS_X:
        return (lo, 0.0, span, 1.0)
    return (0.0, lo, 1.0, span)


@register_step
class RoiProfileStep(Step):
    """投影定位：把影像壓成曲線、找轉折、挑一段當作具名區域。"""

    key = "roi_profile"
    label = "Locate region by profile"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Find the structure in the image by flattening it into a curve and "
            "looking for the places where it changes, then use one of those "
            "sections as the region to measure - so the region follows the "
            "pattern instead of sitting at a fixed spot on the screen.")
    params = [
        ParamSpec(
            name="source", type="image_key", default="ref",
            label="Find the structure in",
            help=("Which image stream to look for the structure in. Use ref: "
                  "it has no defect on it, so nothing is interfering with the "
                  "search, and the pair is already aligned so the answer "
                  "applies to test as well."),
        ),
        ParamSpec(
            name="axis", type="choice", default="x", choices=["x", "y"],
            label="Scan direction",
            help=("x = flatten each column into one value, which finds "
                  "structure boundaries running up and down; y = the other way "
                  "round, for boundaries running left to right."),
        ),
        ParamSpec(
            name="sensitivity", type="float", default=0.35, min=0.0, max=1.0,
            label="Edge sensitivity",
            help=("How steep a change counts as a boundary, compared with the "
                  "steepest change in this image. Lower finds more boundaries, "
                  "higher finds only the strongest. Watch the curve panel and "
                  "drag until the lines land where you expect."),
        ),
        ParamSpec(
            name="smooth", type="int", default=3, min=1, max=99, unit="px",
            label="Curve smoothing",
            help=("Smooth the curve before looking for boundaries. Too little "
                  "and image noise becomes false boundaries; too much and real "
                  "boundaries get rounded away."),
        ),
        ParamSpec(
            name="min_gap", type="int", default=4, min=1, max=500, unit="px",
            label="Minimum spacing",
            help=("How far apart two boundaries must be. One real boundary "
                  "spans several pixels, so without this it gets counted "
                  "several times."),
        ),
        ParamSpec(
            name="rule", type="choice", default="center",
            choices=list(algo_profile.PICK_RULES),
            label="Which section",
            help=("center = the section the defect sits in (the defect is "
                  "always at the middle of the patch, so this is the usual "
                  "choice); widest / darkest / brightest = pick by that "
                  "property; index = count sections from the left."),
        ),
        ParamSpec(
            name="index", type="int", default=0, min=-99, max=99,
            label="Section number",
            help=("Only used when the rule above is 'index'. 0 is the leftmost "
                  "section; negative counts from the right."),
        ),
        ParamSpec(
            name="roi_out", type="str", default="band",
            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Name for the section that was picked. Measure cards refer "
                  "to it by this name."),
        ),
        ParamSpec(
            name="also_neighbours", type="bool", default=False,
            label="Also name the sections either side",
            help=("Also produce <name>_before and <name>_after for the "
                  "sections next to the chosen one. Measuring a defect against "
                  "the neighbouring material is usually more meaningful than "
                  "measuring it against a fixed box that may contain anything."),
        ),
        ParamSpec(
            name="min_confidence", type="float", default=5.0, min=0.0, max=200.0,
            label="Give up below",
            help=("How much of the curve must be real signal rather than "
                  "noise. Some patches sit entirely inside one material and "
                  "have nothing to lock onto - those cannot be located by any "
                  "method, so this card falls back to the whole image and "
                  "marks the defect instead of guessing. A featureless patch "
                  "scores about 1; anything with structure scores 20 or more."),
        ),
        output_prefix_spec("band"),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = ["band_center_px", "band_width_px", "band_dist_px",
                    "band_count", "locate_conf", "locate_ok"]

    # ---- 宣告（給 lint / UI）------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("roi_out", "band") or "").strip()
        if not name:
            return []
        out = [name]
        if bool(params.get("also_neighbours", False)):
            out += [f"{name}_before", f"{name}_after"]
        return out

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
        res = algo_profile.locate(
            img, axis=str(p["axis"]), sensitivity=float(p["sensitivity"]),
            smooth=int(p["smooth"]), min_gap=int(p["min_gap"]),
            rule=str(p["rule"]), index=int(p["index"]))

        # panel 用的原始資料。**UI 畫的就是引擎算的這一份** —— UI 自己再算一次
        # 很容易變成「畫面上的框」與「真的量下去的框」不一樣，那種 bug 極難發現。
        ctx.meta.setdefault("profiles", {})[name] = {
            "axis": res.axis,
            "profile": [float(v) for v in res.profile],
            "raw": [float(v) for v in res.raw],
            "transitions": [int(t) for t in res.transitions],
            "bands": [[int(a), int(b)] for a, b in res.bands],
            "picked": None if res.picked is None else [int(res.picked[0]),
                                                      int(res.picked[1])],
            "confidence": float(res.confidence),
        }

        located = (res.picked is not None
                   and res.confidence >= float(p["min_confidence"]))
        length = res.length

        if not located:
            # 定位不出來就退回整張圖，**而且說出來**。整張都是同一種材質的 patch
            # 本來就不需要定位（整張量是對的），但那跟「有結構卻沒找到」是兩件事，
            # 使用者必須分得出來自己拿到的是哪一種。
            ctx.warn(f"[{self.key}] no clear boundary in '{p['source']}' "
                     f"(confidence {res.confidence:.1f} < "
                     f"{float(p['min_confidence']):.1f}); region '{name}' falls "
                     f"back to the whole image and this defect is marked "
                     f"locate_ok = 0.")
            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
            if bool(p["also_neighbours"]):
                ctx.set_roi(f"{name}_before", (0.0, 0.0, 1.0, 1.0))
                ctx.set_roi(f"{name}_after", (0.0, 0.0, 1.0, 1.0))
            ctx.add_features(prefix_features(p["output_prefix"], {
                "band_center_px": length / 2.0,
                "band_width_px": float(length),
                "band_dist_px": -1.0,
                "band_count": float(len(res.bands)),
                "locate_conf": float(res.confidence),
                "locate_ok": 0.0,
            }))
            return ctx

        a, b = res.picked
        ctx.set_roi(name, _band_rect((a, b), length, res.axis))

        if bool(p["also_neighbours"]):
            i = res.bands.index(res.picked)
            before = res.bands[i - 1] if i > 0 else res.picked
            after = res.bands[i + 1] if i + 1 < len(res.bands) else res.picked
            ctx.set_roi(f"{name}_before", _band_rect(before, length, res.axis))
            ctx.set_roi(f"{name}_after", _band_rect(after, length, res.axis))

        dist = algo_profile.distance_to_nearest_transition(res)
        ctx.add_features(prefix_features(p["output_prefix"], {
            "band_center_px": (a + b) / 2.0,
            "band_width_px": float(b - a),
            # 缺陷離最近一條邊界多遠 —— 落在結構正中間跟落在交界上，
            # 通常不是同一回事，所以這本身就是一個可以拿去打分的數字。
            "band_dist_px": -1.0 if dist == float("inf") else float(dist),
            "band_count": float(len(res.bands)),
            "locate_conf": float(res.confidence),
            "locate_ok": 1.0,
        }))
        return ctx
