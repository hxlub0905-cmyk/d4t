# d4t step-card library — authored 2026-07-28 (M4-1)；2026-08-18 改名重生。
"""pattern_ref —— **從這張圖自己的重複 pattern 疊出一張「沒有缺陷的版本」**。

這張卡的身世（讀之前先知道，不然會覺得名字很怪）
--------------------------------------------------
它以前叫 ``golden_cell`` / 「Golden Cell reference」，2026-08-18 被刪掉，
同一天又被要回來 —— 使用者的話是「那可能要拿回來 不過要改名字 不然會誤會」。

會誤會的是這個：**Template 卡（`roi_template`）的設定對話框裡也在疊 golden
cell**（`algo/template.py` 用同一支 `algo/golden.py`）。畫面上兩個地方都叫
Golden Cell，於是它看起來像同一個功能做了兩次。它們共用演算法，但**吐出來的
東西不同**，而那才是分類的依據：

======================  ======================  ==============================
卡                      吐什麼                  答的問題
======================  ======================  ==============================
Template（Region 段）   具名**區域**（框）      這塊材料在這張圖的哪裡
這一張（Compare 段）    一條**影像流**          這張圖沒有缺陷時該長什麼樣
======================  ======================  ==============================

所以新名字裡沒有 golden、也沒有 cell。第一版叫「Reference from repeating
pattern」，使用者的下一句話是「名字太長」—— 於是收成三個字，句型跟隔壁的
``Mask from regions`` 一樣：**「產出 from 來源」**。卡片庫是一列一張卡讀下去的，
名字長到要換行，那一列就不再是一眼的事。

「repeating」那個字掉進 ``help`` 裡了，不是掉了：它是**前提**（pattern 要真的
重複），而前提屬於說明，不屬於名字 —— 何況這張卡在不重複的圖上會直接擋下來
並講出原因，使用者不會靠名字才知道。

它在做什麼
----------
單張影像（Review SEM、一個資料夾的圖）**沒有 ref**，而 ADC 的主幹是
``test − ref = diff``。這張卡是這個 repo 裡唯一補得出那張 ref 的東西：
把圖上所有重複的 cell 疊起來取中位數 —— 缺陷只出現在其中一格，疊完就被洗掉 ——
得到一個乾淨的「標準 cell」，再照原本的相位鋪回原尺寸。輸出與 ``source``
**同尺寸、同 dtype**（下游 subtract 要求 shape 完全相同），彩色輸入先轉灰階
再複製回同樣的通道數。

**沒有這張卡的代價量過**（見 `docs/plans/F11-phase2-features.md` §3.4.1）：
合成 RSEM lot 上，有它是 24/24，改量 Z-map 是 12/24（＝猜銅板）。

為什麼週期是自己估的
--------------------
以前旁邊還有一張 ``cell_period`` 卡，量一次週期寫進 meta 給這張卡用。使用者
2026-08-18 把它刪掉了（「不需要這功能」），所以週期的來源只剩兩個：
**參數填死**，或**這張卡自己估**。少一張卡、少一條「兩張卡要照順序放」的規矩，
而代價只是每顆多跑一次 rFFT。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ..algo import golden as algo_golden
from ..algo import period as algo_period
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_COMPARE, ParamSpec, Step, StepError, register_step,
)
from ._util import ensure_gray, require_image, to_uint8

__all__ = ["PatternRefStep"]

#: 週期的共用上限：超過這個值的 cell 在一張圖上根本疊不出幾格。
_MAX_PERIOD = 512


@register_step
class PatternRefStep(Step):
    """重複的 cell → 一張乾淨的參考圖（同尺寸、可直接相減）。"""

    key = "pattern_ref"
    label = "Reference from pattern"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Build the reference image out of this image's own repeating "
            "pattern: every repeat is stacked on top of the others and the "
            "middle value kept, so a defect - which only sits in one of them - "
            "washes out. Use it when there is no ref image to compare against, "
            "which is the normal case for a single Review SEM frame. It needs "
            "the pattern to actually repeat; on a layout that does not, it "
            "stops and says so.")
    requires_ref = False          # 這張卡是「製造 ref」的人，自己不需要 ref
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in", default="test",
            section="1 · Which image", label="Build it from",
            help="Image stream whose repeats are stacked (usually test)."),
        ParamSpec(
            name="out", type="image_key", direction="out", default="ref",
            section="1 · Which image", label="Name the result",
            help=("Name of the image stream the reference goes to. Leave it "
                  "at 'ref' and the Align / Compare two streams cards "
                  "downstream need no changes at all.")),
        ParamSpec(
            name="method", type="choice", default="median",
            choices=["median", "mean"],
            section="2 · How to stack", label="Combine the repeats by",
            help=("median ignores the one repeat that has the defect in it "
                  "and is the right default; mean is faster and smoother, but "
                  "a strong defect leaves a trace of itself in the reference "
                  "- and that trace lands on the difference image as a hole.")),
        ParamSpec(
            name="phase_search", type="bool", default=True,
            section="2 · How to stack", label="Find where a repeat starts",
            help=("Work out where to start cutting the repeats so the stack "
                  "does not come out blurred. Leave it on unless you are in "
                  "a hurry.")),
        ParamSpec(
            name="px", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
            section="3 · The repeat size", label="Repeat width",
            help=("How wide one repeat is, in pixels. 0 = measure it from the "
                  "image. Fill it in when you already know the layout pitch "
                  "and the measurement keeps getting it wrong."),
            advanced=True),
        ParamSpec(
            name="py", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
            section="3 · The repeat size", label="Repeat height",
            help=("How tall one repeat is, in pixels. 0 = measure it from the "
                  "image."),
            advanced=True),
        ParamSpec(
            name="sharp_warn", type="float", default=0.0, min=0.0, max=100.0,
            section="4 · When to complain", label="Warn below sharpness",
            help=("Warn when the stacked reference comes out blurred "
                  "(ref_sharpness, 0-100, higher is sharper); 0 = do not "
                  "check. A blurred reference means the repeat size or the "
                  "phase is wrong, and everything measured off it is then "
                  "wrong too - quietly."),
            advanced=True),
    ]
    reads = ["test"]
    writes = ["ref"]
    features_out = ["ref_sharpness", "ref_px", "ref_py"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "ref")]

    # ---- 週期：參數填死 → 否則自己估 ----------------------------------------
    def _resolve_period(self, p: Dict[str, Any],
                        img: np.ndarray) -> Tuple[int, int]:
        px, py = int(p["px"]), int(p["py"])
        if px > 1 and py > 1:
            return px, py

        res = algo_period.estimate_period(img)
        ex, ey = res.px, res.py
        if px > 1:
            ex = px
        if py > 1:
            ey = py
        if ex is None or ey is None:
            raise StepError(
                self.key,
                "no repeating pattern found (at least one direction has no "
                "measurable repeat), so a reference cannot be built from this "
                "image. The layout here may simply not repeat - compare "
                "against a real ref image instead, or type the repeat size "
                "into this card if you know it.")
        return int(ex), int(ey)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        src = require_image(ctx, self.key, p["source"])
        gray = to_uint8(ensure_gray(src))
        h, w = gray.shape[:2]

        px, py = self._resolve_period(p, gray)
        if px > w or py > h:
            raise StepError(
                self.key,
                "one repeat (%dx%d px) is larger than the image (%dx%d px), "
                "so not a single one can be stacked. Check the repeat size, "
                "or compare against a real ref image instead."
                % (px, py, w, h))

        origin = (0, 0)
        if p["phase_search"]:
            origin = algo_period.choose_origin(gray.shape, px, py, image=gray)

        n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))
        if n_cells < 2:
            raise StepError(
                self.key,
                "the image fits only %d complete repeat(s) (repeat size %dx%d "
                "px), which is not enough to average anything out. The image "
                "may be too small, or the layout may not repeat - compare "
                "against a real ref image instead." % (n_cells, px, py))

        stacked = algo_golden.stack_cells(gray, px, py, method=p["method"],
                                          origin=origin)
        if stacked.shape[:2] != (py, px):   # 理論上不會發生；防呆
            raise StepError(self.key, "stacking failed (got %s instead of %s)."
                            % (stacked.shape, (py, px)))

        score, lap_var, edge_contrast = algo_golden.ghosting_score(stacked)

        # 鋪回原尺寸：out[y, x] = stacked[(y - oy) % py, (x - ox) % px]
        # → 與 source 同尺寸，且鋪出來的晶格與 source 同相位，可直接相減。
        ox, oy = origin
        xi = (np.arange(w) - ox) % px
        yi = (np.arange(h) - oy) % py
        tiled = stacked[np.ix_(yi, xi)]
        ctx.set_image(p["out"], _match_source(tiled, src))

        warn_at = float(p["sharp_warn"])
        if warn_at > 0 and score < warn_at:
            ctx.warn("[%s] the reference came out blurred (ref_sharpness=%.1f "
                     "< %g): the repeat size or the phase is probably wrong, "
                     "so treat the comparison with care."
                     % (self.key, score, warn_at))

        ctx.meta["pattern_ref"] = {
            "px": int(px), "py": int(py), "ox": int(ox), "oy": int(oy),
            "method": str(p["method"]), "n_cells": int(n_cells),
            "lap_var": float(lap_var), "edge_contrast": float(edge_contrast),
        }
        ctx.add_features({
            "ref_sharpness": float(score),   # 0–100，越高越清晰（ghosting 越少）
            "ref_px": float(px),
            "ref_py": float(py),
        })
        return ctx


def _match_source(tiled: np.ndarray, src: np.ndarray) -> np.ndarray:
    """把 uint8 的鋪圖還原成與 ``src`` 相同的 dtype／值域／通道數。

    疊圖一律在 uint8 0–255 的值域做（週期分析的前提），但上游可能餵進
    float32 0–1 的影像流；直接輸出 uint8 會讓下游 subtract 兩張圖差一個
    255 倍。這裡照 ``_util.to_uint8`` 的相反規則還原。
    """
    out = tiled
    if src.ndim == 3:
        out = np.repeat(out[:, :, None], src.shape[2], axis=2)
    if src.dtype == np.uint8:
        return out.astype(np.uint8)
    f = np.asarray(src, dtype=np.float32)
    if f.size > 0 and float(f.min()) >= 0.0 and float(f.max()) <= 1.5:
        return (out.astype(np.float32) / 255.0)
    return out.astype(np.float32)
