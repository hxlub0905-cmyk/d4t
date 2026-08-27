# d4t step-card library — authored 2026-07-28 (M1).
"""focus_quality — 影像品質（對焦）量測卡。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import quality as algo_quality
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import MultiSourceStep, output_prefix_spec


@register_step
class FocusQualityStep(MultiSourceStep):
    """對焦品質：Laplacian 變異數 / Tenengrad / FFT 高頻比。"""

    key = "focus_quality"
    # ⚠ 只有 `label` 換掉（同 `glv_stats`）—— `key`（`focus_quality`）與
    # `focus_*` 那三個特徵名是 recipe 與分數表達式的鍵，不動。
    label = "Focus index"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure image sharpness with three metrics — higher is sharper. "
            "Useful for screening out defocused images.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="test",
                  help="Image stream to measure sharpness on."),
        output_prefix_spec("test"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["focus_lapvar", "focus_tenengrad", "focus_fft"]

    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        q = algo_quality.compute_quality(img)
        if q.get("error"):
            raise StepError(self.key, f"image quality computation failed: {q['error']}")
        # 儀表用（PR-2）：同一份數字順手留在 meta，面板**選到卡就有**（單顆
        # 立即顯示），不必等跑完一批 —— 跟 `glv_stats._note_distribution` 同
        # 一條路。批次的分布照舊由 trial_results 補。
        ctx.meta.setdefault("focus", []).append({
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "prefix": str(p.get(self.CURRENT_PREFIX, "") or ""),
            "lapvar": float(q["laplacian_var"]),
            "tenengrad": float(q["tenengrad"]),
            "fft": float(q["fft_hf_ratio"]),
        })
        return {
            "focus_lapvar": q["laplacian_var"],
            "focus_tenengrad": q["tenengrad"],
            "focus_fft": q["fft_hf_ratio"],
        }
