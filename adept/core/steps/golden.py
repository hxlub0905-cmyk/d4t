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
    CATEGORY_ALGO, CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step,
)
from ._util import ensure_gray, require_image, to_uint8

# 週期參數的共用上限：超過這個值的 cell 在 patch 影像上根本疊不出幾格。
_MAX_PERIOD = 512


def _opt(value: Any) -> Optional[int]:
    """參數的 0 = 「自動」→ None；其餘轉 int。"""
    v = int(value)
    return v if v > 0 else None


@register_step
class CellPeriodStep(Step):
    """量出圖上重複 cell 的 X/Y 週期（像素）。"""

    key = "cell_period"
    label = "Cell 週期估測"
    category = CATEGORY_ALGO
    help = "量出圖上重複 cell 的 X/Y 週期（像素），供 Golden Cell 卡使用；順便回報這個週期有多可信。"
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  help="要量週期的影像流（通常是 test）。"),
        ParamSpec(name="min_period", type="int", default=0, min=0, max=_MAX_PERIOD,
                  unit="px",
                  help="最小週期（像素）；0 = 自動。知道 cell 至少多大時填，可避免抓到雜訊的小週期。"),
        ParamSpec(name="max_period", type="int", default=0, min=0, max=_MAX_PERIOD,
                  unit="px",
                  help="最大週期（像素）；0 = 自動（影像的一半）。知道 cell 最大多大時填。"),
        ParamSpec(name="refine", type="bool", default=True,
                  help="是否做 ±2 像素的微調搜尋：用實際疊圖的清晰度挑最好的週期，較準但稍慢。"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["cell_px", "cell_py", "cell_conf_x", "cell_conf_y"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("source", "test")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        lo, hi = _opt(p["min_period"]), _opt(p["max_period"])
        if lo is not None and hi is not None and hi < lo:
            raise StepError(self.key,
                            f"max_period（{hi}）不可小於 min_period（{lo}）；請把兩個值對調或改成 0（自動）。")
        img = to_uint8(ensure_gray(require_image(ctx, self.key, p["source"])))

        res = algo_period.estimate_period(img, min_period=lo, max_period=hi)
        px, py = res.px, res.py

        # 微調：用實際疊出來的清晰度在 ±2 像素內挑最好的週期（兩軸都有值才做）。
        if p["refine"] and px is not None and py is not None:
            px, py, _ = algo_golden.refine_period(img, px, py, search=2)

        if px is None or py is None:
            if px is None and py is None:
                why = "這張圖看起來沒有週期性結構（X、Y 兩軸都量不到重複的 cell）"
            else:
                axis = "X" if px is not None else "Y"
                other = "Y" if px is not None else "X"
                why = (f"這張圖只有 {axis} 軸看得到週期性結構，{other} 軸量不到"
                       f"（可能是 line/space 之類的單向版圖）")
            ctx.warn(f"[{self.key}] {why}，量不出完整的 cell 週期；"
                     "Golden Cell 這條路線在這一站可能不適用（可改走有 ref 的比對路線）。")
        ctx.meta["cell_period"] = {"px": int(px or 0), "py": int(py or 0)}
        ctx.add_features({
            "cell_px": float(px or 0),
            "cell_py": float(py or 0),
            "cell_conf_x": float(res.confidence_x),   # PeriodResult.confidence_x（0–100）
            "cell_conf_y": float(res.confidence_y),   # PeriodResult.confidence_y（0–100）
        })
        return ctx


@register_step
class GoldenCellStep(Step):
    """Golden Cell：把重複的 cell 疊成一張乾淨參考圖，再鋪回原尺寸。

    輸出影像與 ``source`` **同尺寸、同 dtype**（下游 subtract 要求兩張圖
    shape 完全相同）；彩色輸入會先轉灰階再複製回同樣的通道數。
    """

    key = "golden_cell"
    label = "Golden Cell 參考圖"
    category = CATEGORY_IMAGE
    help = "把圖上重複的 cell 疊起來合成一張乾淨的參考圖 —— 沒有 ref 影像時（例如 Review SEM 單張）用這張當比對基準。"
    requires_ref = False          # 這張卡是「製造 ref」的人，自己不需要 ref
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  help="要拿來疊 cell 的影像流（通常是 test）。"),
        ParamSpec(name="out", type="image_key", default="ref",
                  help="合成參考圖要寫入的影像流名稱；維持預設 'ref' 的話，後面的對位／相減卡完全不用改。"),
        ParamSpec(name="method", type="choice", default="median",
                  choices=["mean", "median"],
                  help="疊圖方式：median（中位數）比較不會被缺陷污染，推薦；mean（平均）比較快也比較平滑。"),
        ParamSpec(name="px", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
                  help="X 方向 cell 週期（像素）；0 = 自動（先用 cell_period 卡的結果，沒有就自己估）。"),
        ParamSpec(name="py", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
                  help="Y 方向 cell 週期（像素）；0 = 自動（先用 cell_period 卡的結果，沒有就自己估）。"),
        ParamSpec(name="phase_search", type="bool", default=True,
                  help="自動找晶格相位（要從哪一格開始切），避免切錯位置疊出來糊掉；除非很趕時間否則建議開著。"),
        ParamSpec(name="ghost_warn", type="float", default=0.0, min=0.0, max=100.0,
                  help="疊圖品質（golden_ghost，0–100 越高越清晰）低於此值就發警告；0 = 不檢查。"),
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
                "找不到重複的 cell 結構（X/Y 至少一軸量不到週期），無法合成 Golden Cell 參考圖。"
                "這一站的影像可能本來就不是週期性版圖 —— 請改用有 ref 影像的比對路線"
                "（die-to-die / cell-to-cell），或在參數裡直接填入已知的 px / py。")
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
                f"cell 週期（{px}x{py} px）比影像（{w}x{h} px）還大，一格都疊不出來。"
                "請確認週期參數，或改用有 ref 影像的比對路線。")

        origin = (0, 0)
        if p["phase_search"]:
            origin = algo_period.choose_origin(gray.shape, px, py, image=gray)

        n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))
        if n_cells < 2:
            raise StepError(
                self.key,
                f"影像只切得出 {n_cells} 格完整 cell（週期 {px}x{py} px），疊不出有意義的參考圖。"
                "這一站的影像可能不夠大或不是週期性版圖 —— 請改用有 ref 影像的比對路線。")

        stacked = algo_golden.stack_cells(gray, px, py, method=p["method"],
                                          origin=origin)
        if stacked.shape[:2] != (py, px):   # 理論上不會發生；防呆
            raise StepError(self.key, f"疊圖失敗（得到 {stacked.shape} 而非 {(py, px)}）。")

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
            ctx.warn(f"[{self.key}] 疊出來的參考圖偏糊（golden_ghost={score:.1f} < {warn_at:g}）："
                     "週期或相位可能沒抓對，比對結果請當心。")

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
