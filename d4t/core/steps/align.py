# d4t step-card library — authored 2026-07-28 (M1); reshaped 2026-09-17 (F109).
"""align —— 對位卡：把幾條流對齊到同一條基準上。

**這張卡只做一件字面上的事：讓幾張圖對得起來。** 「跟誰比」不是它的問題 ——
那由畫布上的線決定（F9）。

形狀：``streams``（N 條，含基準）＋ ``fixed``（哪一條是基準）→ 每條各自對齊，
**寫回原名**（``suffix`` 非空時寫成 ``<名字><suffix>``）。加幾條 condition 都只有
一張卡，這是 DOE 要的：同一顆 defect、位置固定在 FOV 中間、FOV 相同，用不同
E-beam condition 各拍一張，對齊之後在同一組 target／ref box 上比 SNR。

⚠ **對齊不動灰階**（F109，2026-09-17）
--------------------------------------
位移**只取整數**，並把所有流**裁成共同重疊區**；次像素的那一點點留在
``align_dx`` / ``align_dy`` 裡。理由與代價寫在 ``algo/align.common_crop``
的說明裡，一句話版本：**量的是灰階，所以對齊不准重採樣。**

這同時修掉 2026-08-18 使用者回報的「拉 align 反而會飄掉 shift」的第二個機制
（只有被移動的那一條被過了一次低通）。第一個機制 —— 缺陷把相關峰往自己那邊拉
—— 這一輪**沒有**修：要修它得讓對位只看一塊不含缺陷的區域，那是另一件事。

⚠ 裁切會改變正規化座標的意義，所以 **ROI 卡要接在這張卡之後**。

尺寸不符時**報錯**，不是零位移
------------------------------
以前是「警告 ＋ 零位移」，而 ``align_dx=0 / align_dy=0 / align_score=0`` 三個數字
照樣流進分數表達式 —— 一件做不到的事看起來像做完了。單顆報錯只讓那一顆
``ok=False``，整批照跑（鐵則 7）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..algo import align as algo_align
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE,
)
from ._util import parse_key_list, prefix_features, require_image

#: 這張卡自己的三個數字（每一條被移動的流各一組）。
_PER_STREAM = ("align_dx", "align_dy", "align_score")

#: 兩個 key 的預設值住在這裡，`ParamSpec` 與底下三支 `_*_of` 共用。
#:
#: ⚠ **`resolve_*` 會拿到「還沒填過任何東西」的 params** —— 畫布上剛拉出來的
#: 節點就是那樣（預設值是 `validate_params` 當下才套的，不會存進 recipe）。
#: 所以這裡不能寫 ``params.get("streams", "")``：那會讓一張剛加上去的 align
#: 宣告自己不讀任何流、不吐任何位移，而畫布是照宣告畫的。
DEFAULT_STREAMS = "test,ref"
DEFAULT_FIXED = "test"


def _streams_of(params: Dict[str, Any]) -> List[str]:
    raw = params.get("streams", None)
    if raw is None:
        raw = DEFAULT_STREAMS
    return parse_key_list(str(raw or ""))


def _fixed_of(params: Dict[str, Any]) -> str:
    raw = params.get("fixed", None)
    if raw is None:
        raw = DEFAULT_FIXED
    return str(raw or "").strip()


def _moving_of(params: Dict[str, Any]) -> List[str]:
    """要被移動的那幾條 —— ``streams`` 扣掉基準。"""
    fixed = _fixed_of(params)
    return [s for s in _streams_of(params) if s != fixed]


def shift_feature_names(params: Dict[str, Any]) -> List[Tuple[str, str]]:
    """這組參數下，位移那兩個數字各自叫什麼 —— ``[(dx 的名字, dy 的名字), ...]``。

    儀表板要畫整批的位移散佈圖，而**三條以上的流時特徵名帶著流名前綴**。
    名字由這裡給而不是讓 UI 拼：拼的那一份會在下一次改前綴規則時安靜地畫出
    一張空圖，而空圖上寫的是「跑一次試跑就看得到」——那句話是假的，
    而「畫面說謊」是這個 repo 最貴的那一種 bug。
    """
    moving = _moving_of(params)
    if not moving:
        return [("align_dx", "align_dy")]
    out: List[Tuple[str, str]] = []
    for name in moving:
        p = _prefix_for(moving, name)
        out.append(("%s_align_dx" % p if p else "align_dx",
                    "%s_align_dy" % p if p else "align_dy"))
    return out


def _prefix_for(moving: List[str], name: str) -> str:
    """只有一條要移動時不加前綴 —— 跟量測卡的 ``stream_prefix`` 同一條規矩。

    這讓「一條 ref 對一條 test」那個最常見的用法，特徵名跟 F109 之前**逐字相同**。
    """
    return "" if len(moving) <= 1 else name


@register_step
class AlignStep(Step):
    """平移對位：phase/hybrid/ncc/ecc/template 後端擇一，整數平移 + 裁共同重疊區。"""

    key = "align"
    label = "Align"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Line these image streams up on the same one, so the cards after "
            "this measure the same place on every one. Only whole pixels are "
            "moved and nothing is resampled - grey levels stay exactly as they "
            "came in, which is what makes comparing brightness between them "
            "honest. They all come out cropped to the part they share.")
    params = [
        ParamSpec(name="streams", type="image_keys", direction="in",
                  default=DEFAULT_STREAMS,
                  help=("Which image streams to line up. Include the one you "
                        "are lining the others up on - it gets cropped the "
                        "same way, so they all end up the same size.")),
        ParamSpec(name="fixed", type="image_key", direction="in",
                  default=DEFAULT_FIXED,
                  help=("The one that stays put; everything else moves onto it. "
                        "It has to be one of the streams above.")),
        ParamSpec(name="method", type="chip_choice", default="phase",
                  choices=["phase", "hybrid", "ncc", "ecc", "template"],
                  icons=["al_phase", "al_hybrid", "al_ncc", "al_ecc",
                         "al_template"],
                  choice_labels={"ncc": "NCC", "ecc": "ECC"},
                  help=("Alignment backend: phase = fast and robust (default); "
                        "ncc = exhaustive correlation; ecc = iterative refinement; "
                        "template = central template match; hybrid behaves like phase.")),
        ParamSpec(name="search_radius", type="int", default=8, min=1, max=64,
                  extent="radius",
                  help=("Search radius in pixels: the largest shift you expect. "
                        "Too small and it will not find the shift, too large "
                        "and it gets slow.")),
        ParamSpec(name="suffix", type="str", default="", pattern=r"^[A-Za-z0-9_]*$",
                  help=("Leave this empty and each stream is written back under "
                        "its own name. Give it something like _aligned and the "
                        "results are written beside the originals instead.")),
    ]
    reads = ["test", "ref"]
    writes = ["test", "ref"]
    features_out = ["align_dx", "align_dy", "align_score", "align_valid_frac"]
    FEATURE_HELP = {
        "align_dx": "how far it moved, px (left/right)",
        "align_dy": "how far it moved, px (up/down)",
        # ⚠ 值域是 0–100，不是 0–1：`algo/align` 的每個 backend 都 `* 100`。
        # 這一行以前寫 "0 to 1"，而這個數字進得了分數表達式 —— help 是使用者
        # 唯一讀得到的說明，寫錯就是把人帶到錯的門檻上（F109 修）。
        "align_score": "how sure the match was, 0 to 100",
        "align_valid_frac": "how much of the frame survived the crop, 0 to 1",
    }

    @classmethod
    def _out_name(cls, params: Dict[str, Any], name: str) -> str:
        return name + str(params.get("suffix", "") or "")

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        streams = _streams_of(params)
        fixed = _fixed_of(params)
        if fixed and fixed not in streams:
            streams = streams + [fixed]
        return streams

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [cls._out_name(params, s) for s in _streams_of(params)]

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        moving = _moving_of(params)
        if not moving:
            # 還沒接線（畫布上剛拉出來的卡，`streams` 是空字串）—— 宣告**不帶
            # 前綴**的那一組，跟 `glv_stats` 在同樣情況下的做法一致。
            # 宣告空的話，剛加上去的卡在「插入數字 ▾」裡整個看不見。
            return list(_PER_STREAM) + ["align_valid_frac"]
        out: List[str] = []
        for name in moving:
            p = _prefix_for(moving, name)
            out.extend(f"{p}_{f}" if p else f for f in _PER_STREAM)
        out.append("align_valid_frac")
        return out

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """基準不在清單裡 = 它不會被裁，於是出去的幾條尺寸對不起來。"""
        streams, fixed = _streams_of(params), _fixed_of(params)
        if not streams or not fixed:
            return []
        if fixed not in streams:
            return ["'%s' is not one of the streams being lined up, so it would "
                    "not be cropped with them and they would come out different "
                    "sizes. Add it to the list above." % fixed]
        if len(streams) < 2:
            return ["only one stream is listed, so there is nothing to line it "
                    "up against. Add the other one."]
        return []

    def _shift_for(self, ctx: Context, fixed, moving, name: str,
                   p: Dict[str, Any]) -> Tuple[int, int, float, float, float]:
        """量一條流相對基準的位移 → ``(dx, dy, dx_sub, dy_sub, score)``。"""
        if fixed.shape[:2] != moving.shape[:2]:
            raise StepError(
                self.key,
                "'%s' is %s and '%s' is %s - this card lines up streams of the "
                "same size. Use H2H when one image sits inside a bigger one."
                % (p["fixed"], fixed.shape[:2], name, moving.shape[:2]))
        try:
            res = algo_align.calculate_alignment(
                fixed, moving, method=p["method"],
                search_radius=int(p["search_radius"]))
        except Exception as e:                       # 對位絕不讓整批掛掉
            ctx.warn(f"[{self.key}] '{name}': alignment failed ({e}); "
                     f"using zero shift.")
            return 0, 0, 0.0, 0.0, 0.0
        if res.status == "fail":
            ctx.warn(f"[{self.key}] '{name}': alignment did not converge "
                     f"(score={res.final_score:.1f}); using zero shift.")
            return 0, 0, 0.0, 0.0, float(res.final_score)
        if res.status == "warn":
            ctx.warn(f"[{self.key}] '{name}': low alignment quality "
                     f"(score={res.final_score:.1f}); treat results with care.")
        # ⚠ 裁切用**整數**（相關峰真的落在的那一格），回報用次像素。
        return (int(res.dx), int(res.dy), float(res.dx_subpixel),
                float(res.dy_subpixel), float(res.final_score))

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        streams, fixed_key = _streams_of(p), _fixed_of(p)
        if fixed_key and fixed_key not in streams:
            streams = streams + [fixed_key]
        if len(streams) < 2:
            raise StepError(self.key, "list at least two image streams to line up.")
        fixed = require_image(ctx, self.key, fixed_key)

        shifts: Dict[str, Tuple[int, int]] = {fixed_key: (0, 0)}
        reported: Dict[str, Tuple[float, float, float]] = {}
        images = {fixed_key: fixed}
        for name in streams:
            if name == fixed_key:
                continue
            img = require_image(ctx, self.key, name)
            dx, dy, dx_sub, dy_sub, score = self._shift_for(ctx, fixed, img, name, p)
            shifts[name] = (dx, dy)
            reported[name] = (dx_sub, dy_sub, score)
            images[name] = img

        try:
            windows = algo_align.common_crop(fixed.shape[:2], shifts)
        except ValueError as e:
            raise StepError(self.key, "%s - the streams do not overlap after "
                                      "alignment." % e) from None

        for name, img in images.items():
            ctx.set_image(self._out_name(p, name),
                          algo_align.crop(img, windows[name]))

        moving = [s for s in streams if s != fixed_key]
        for name in moving:
            dx_sub, dy_sub, score = reported[name]
            ctx.add_features(prefix_features(_prefix_for(moving, name), {
                "align_dx": dx_sub, "align_dy": dy_sub, "align_score": score}))
        y0, y1, x0, x1 = windows[fixed_key]
        kept = float((y1 - y0) * (x1 - x0)) / float(fixed.shape[0] * fixed.shape[1])
        ctx.add_feature("align_valid_frac", kept)

        # 儀表用：整批的位移散佈圖讀這兩個（只記第一條被移動的流）。
        if moving:
            ctx.meta["align_dx"] = reported[moving[0]][0]
            ctx.meta["align_dy"] = reported[moving[0]][1]
        return ctx
