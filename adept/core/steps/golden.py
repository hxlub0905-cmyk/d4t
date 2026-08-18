# ADEPT step-card library — authored 2026-07-28 (M4-1).
"""Golden Cell 兩張卡：cell_period（週期估測）+ golden_cell（參考圖合成）。

用途：Review SEM 這類**只有一張圖、沒有 ref**的資料，靠「圖上的 cell 會重複」
這件事自己造一張參考圖 —— 把所有 cell 疊起來，缺陷只出現在其中一格，
疊完就被平均/中位數洗掉，剩下乾淨的「標準 cell」。再把它鋪回原尺寸，
就得到一張可以直接拿去 subtract 的 ref。

兩張卡分開的原因：週期只跟「這一站的版圖」有關，一個 lot 內不會變，
量一次（cell_period）寫進 ``ctx.meta["cell_period"]``，golden_cell 直接拿來用，
不必每顆 defect 重算 FFT。單獨使用 golden_cell 也可以（它會自己估）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..algo import golden as algo_golden
from ..algo import period as algo_period
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, ensure_gray, output_prefix_spec, require_image, to_uint8,
)

# 週期參數的共用上限：超過這個值的 cell 在 patch 影像上根本疊不出幾格。
_MAX_PERIOD = 512


def _opt(value: Any) -> Optional[int]:
    """參數的 0 = 「自動」→ None；其餘轉 int。"""
    v = int(value)
    return v if v > 0 else None


@register_step
class CellPeriodStep(MultiSourceStep):
    """量出圖上重複 cell 的 X/Y 週期（像素）。

    多連一（F11 Input-3）
    --------------------
    這張卡在 F7-1 期間被 ``scope.HIDDEN_STEPS`` 收著（它存在的唯一理由是幫**單張
    影像**疊 ref，而那時 Studio 只吃兩兩成對的 patch）。Input-3 把單張那條路打開，
    它也跟著回到卡片庫 —— 而「量測卡都接得了好幾條來源」那條不變量
    （``test_ui_f10_canvas_reality.py``）**當場對它紅了**：它從來沒有做過 F10-3
    的處理。這正是那條不變量存在的理由 —— 它逐張套用到 registry，所以一張卡
    重新可見的時候不會安靜地少一半功能。
    """

    key = "cell_period"
    label = "Cell period"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure the X/Y period of the repeating cells in the image (in "
            "pixels) for the Golden Cell card, and report how trustworthy that "
            "period is.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="test",
                  help="Image stream to measure the period on (usually test)."),
        ParamSpec(name="min_period", type="int", default=0, min=0, max=_MAX_PERIOD,
                  unit="px",
                  help=("Minimum period in pixels; 0 = automatic. Set it when you "
                        "know how small a cell can be, to avoid locking onto a "
                        "small noise period.")),
        ParamSpec(name="max_period", type="int", default=0, min=0, max=_MAX_PERIOD,
                  unit="px",
                  help=("Maximum period in pixels; 0 = automatic (half the image). "
                        "Set it when you know how large a cell can be.")),
        ParamSpec(name="refine", type="bool", default=True,
                  help=("Whether to run a +/-2 pixel refinement search, picking the "
                        "period that actually stacks sharpest. More accurate, "
                        "slightly slower.")),
        output_prefix_spec("cell"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["cell_px", "cell_py", "cell_conf_x", "cell_conf_y"]

    def measure(self, ctx: Context, img, params: Dict[str, Any]):
        p = params
        lo, hi = _opt(p["min_period"]), _opt(p["max_period"])
        if lo is not None and hi is not None and hi < lo:
            raise StepError(self.key,
                            f"max_period ({hi}) cannot be smaller than min_period "
                            f"({lo}); swap the two values or set them to 0 (automatic).")
        img = to_uint8(ensure_gray(img))

        res = algo_period.estimate_period(img, min_period=lo, max_period=hi)
        px, py = res.px, res.py

        # 微調：用實際疊出來的清晰度在 ±2 像素內挑最好的週期（兩軸都有值才做）。
        if p["refine"] and px is not None and py is not None:
            px, py, _ = algo_golden.refine_period(img, px, py, search=2)

        if px is None or py is None:
            if px is None and py is None:
                why = ("this image shows no periodic structure (no repeating "
                       "cell found on either the X or the Y axis)")
            else:
                axis = "X" if px is not None else "Y"
                other = "Y" if px is not None else "X"
                why = (f"this image is periodic along {axis} only, with nothing "
                       f"measurable along {other} (it may be a one-directional "
                       f"layout such as line/space)")
            ctx.warn(f"[{self.key}] {why}, so a full cell period cannot be "
                     "measured. The Golden Cell route may not suit this layer — "
                     "consider a comparison route that has a real ref image.")
        # ``golden_cell`` 讀這個 key 當「已經量好的週期」。接了好幾條流時，
        # **第一條就定案**（後面的不覆寫）—— Golden Cell 是對某一條流疊 ref，
        # 讓最後一條無聲地決定它的週期，會變成「畫面上看不出來的相依」。
        ctx.meta.setdefault("cell_period", {"px": int(px or 0), "py": int(py or 0)})
        return {
            "cell_px": float(px or 0),
            "cell_py": float(py or 0),
            "cell_conf_x": float(res.confidence_x),   # PeriodResult.confidence_x（0–100）
            "cell_conf_y": float(res.confidence_y),   # PeriodResult.confidence_y（0–100）
        }


@register_step
class GoldenCellStep(Step):
    """Golden Cell：把重複的 cell 疊成一張乾淨參考圖，再鋪回原尺寸。

    輸出影像與 ``source`` **同尺寸、同 dtype**（下游 subtract 要求兩張圖
    shape 完全相同）；彩色輸入會先轉灰階再複製回同樣的通道數。
    """

    key = "golden_cell"
    label = "Golden Cell reference"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Stack the repeating cells into one clean reference image — use it "
            "as the comparison baseline when there is no ref image (a single "
            "Review SEM frame, for instance).")
    requires_ref = False          # 這張卡是「製造 ref」的人，自己不需要 ref
    params = [
        ParamSpec(name="source", type="image_key", direction="in", default="test",
                  help="Image stream whose cells are stacked (usually test)."),
        ParamSpec(name="out", type="image_key", direction="out", default="ref",
                  help=("Name of the image stream the synthetic reference goes "
                        "to. Leave it at 'ref' and the align/subtract cards "
                        "downstream need no changes at all.")),
        ParamSpec(name="method", type="choice", default="median",
                  choices=["mean", "median"],
                  help=("Stacking method: median resists contamination by defects "
                        "and is recommended; mean is faster and smoother.")),
        ParamSpec(name="px", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
                  help=("Cell period along X in pixels; 0 = automatic (uses the "
                        "cell_period card's result, or estimates its own).")),
        ParamSpec(name="py", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
                  help=("Cell period along Y in pixels; 0 = automatic (uses the "
                        "cell_period card's result, or estimates its own).")),
        ParamSpec(name="phase_search", type="bool", default=True,
                  help=("Find the lattice phase automatically (where to start "
                        "cutting cells) so the stack does not come out blurred. "
                        "Leave it on unless you are in a hurry.")),
        ParamSpec(name="ghost_warn", type="float", default=0.0, min=0.0, max=100.0,
                  help=("Warn when stack quality (golden_ghost, 0-100, higher is "
                        "sharper) falls below this value; 0 = do not check.")),
    ]
    reads = ["test"]
    writes = ["ref"]
    features_out = ["golden_ghost", "golden_px", "golden_py"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "ref")]

    # ---- 週期來源：參數 → cell_period 卡的 meta → 自己估 ----------------------
    def _resolve_period(self, ctx: Context, p: Dict[str, Any],
                        img: np.ndarray) -> Tuple[int, int]:
        px, py = int(p["px"]), int(p["py"])
        if px > 1 and py > 1:
            return px, py

        cached = ctx.meta.get("cell_period") or {}
        if isinstance(cached, dict):
            cx, cy = int(cached.get("px", 0) or 0), int(cached.get("py", 0) or 0)
            if cx > 1 and cy > 1:
                return (px if px > 1 else cx), (py if py > 1 else cy)

        res = algo_period.estimate_period(img)
        ex, ey = res.px, res.py
        if px > 1:
            ex = px
        if py > 1:
            ey = py
        if ex is None or ey is None:
            raise StepError(
                self.key,
                "no repeating cell structure found (at least one axis has no "
                "measurable period), so a Golden Cell reference cannot be built. "
                "This layer may simply not be a periodic layout — use a comparison "
                "route with a real ref image (die-to-die / cell-to-cell), or enter "
                "the known px / py in the parameters.")
        return int(ex), int(ey)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        src = require_image(ctx, self.key, p["source"])
        gray = to_uint8(ensure_gray(src))
        h, w = gray.shape[:2]

        px, py = self._resolve_period(ctx, p, gray)
        if px > w or py > h:
            raise StepError(
                self.key,
                f"the cell period ({px}x{py} px) is larger than the image "
                f"({w}x{h} px), so not a single cell can be stacked. Check the "
                f"period parameters, or use a comparison route with a real ref "
                f"image.")

        origin = (0, 0)
        if p["phase_search"]:
            origin = algo_period.choose_origin(gray.shape, px, py, image=gray)

        n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))
        if n_cells < 2:
            raise StepError(
                self.key,
                f"the image fits only {n_cells} complete cell(s) (period "
                f"{px}x{py} px), which is not enough for a meaningful reference. "
                f"The image may be too small or not a periodic layout — use a "
                f"comparison route with a real ref image.")

        stacked = algo_golden.stack_cells(gray, px, py, method=p["method"],
                                          origin=origin)
        if stacked.shape[:2] != (py, px):   # 理論上不會發生；防呆
            raise StepError(self.key, f"stacking failed (got {stacked.shape} instead of {(py, px)}).")

        score, lap_var, edge_contrast = algo_golden.ghosting_score(stacked)

        # 鋪回原尺寸：out[y, x] = stacked[(y - oy) % py, (x - ox) % px]
        # → 與 source 同尺寸，且鋪出來的晶格與 source 同相位，可直接相減。
        ox, oy = origin
        xi = (np.arange(w) - ox) % px
        yi = (np.arange(h) - oy) % py
        tiled = stacked[np.ix_(yi, xi)]
        ctx.set_image(p["out"], _match_source(tiled, src))

        warn_at = float(p["ghost_warn"])
        if warn_at > 0 and score < warn_at:
            ctx.warn(f"[{self.key}] the stacked reference looks blurred "
                     f"(golden_ghost={score:.1f} < {warn_at:g}): the period or "
                     f"phase may be wrong, so treat the comparison with care.")

        ctx.meta["golden_cell"] = {
            "px": int(px), "py": int(py), "ox": int(ox), "oy": int(oy),
            "method": str(p["method"]), "n_cells": int(n_cells),
            "lap_var": float(lap_var), "edge_contrast": float(edge_contrast),
        }
        ctx.add_features({
            "golden_ghost": float(score),   # 0–100，越高越清晰（ghosting 越少）
            "golden_px": float(px),
            "golden_py": float(py),
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
