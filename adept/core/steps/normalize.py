# ADEPT step-card library — authored 2026-07-28 (M1).
"""亮度正規化卡片：percentile_norm / glv_mask_norm / hist_match。

三張卡都是「把圖的亮度拉到可以互相比較」的影像段工具：
- percentile_norm：百分位拉伸（P2–P98 → 0–255）。
- glv_mask_norm  ：只用指定灰階帶（GLV band）內的像素估計拉伸範圍。
- hist_match     ：把 moving 影像的直方圖對齊到 reference 影像。

輸出一律 uint8 0–255。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import histmatch as algo_histmatch
from ..algo import normalize as algo_normalize
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_ENHANCE,
)
from ._util import ONE_STREAM_HELP, require_image, to_uint8


def _norm_to_u8(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """套用範圍正規化並轉 uint8 0–255。"""
    out01 = algo_normalize.normalize_image_with_range(img.astype(np.float32), lo, hi)
    return (np.clip(out01, 0.0, 1.0) * 255.0).astype(np.uint8)


#: ``range_from`` 的說明（``source`` 用共用的 :data:`ONE_STREAM_HELP`）。
#:
#: 這兩張卡以前是「主流 + also_apply 清單 + anchor」三個參數擠在控制列上，
#: 而使用者在畫布上想的是節點：**一張卡做一條流**，要對 ref 也做就再放一張卡。
#: 唯一會掉的能力是 ``anchor="source"``（ref 借 test 量出來的範圍，這是
#: 「兩張圖還比得起來」的關鍵），所以那件事升成一個看得見的參數 ``range_from``
#: —— 它是**一條影像流的名字**，在畫布上就是接進這張卡的第二條線。
_RANGE_FROM_HELP = (
    "Leave empty and the stretch range is measured on this card's own stream. "
    "Name another stream to reuse that stream's range instead - that is what "
    "keeps test and ref comparable when each one is normalized by its own "
    "card. Put this card BEFORE the card that normalizes the stream you are "
    "borrowing from, so the range is measured on the original image.")


def _stream_reads(params: Dict[str, Any]) -> List[str]:
    """這張卡讀哪幾條流：自己那條，加上（有填的話）借範圍的那條。"""
    keys = [str(params.get("source", "test"))]
    borrow = str(params.get("range_from", "") or "").strip()
    if borrow and borrow not in keys:
        keys.append(borrow)
    return keys


def _range_basis(ctx: Context, step_key: str, params: Dict[str, Any],
                 src: np.ndarray) -> np.ndarray:
    """量拉伸範圍要看哪一張圖：預設是自己，填了 ``range_from`` 就是那一條。

    借不到（那條流不存在）就**報錯**，不靜靜改用自己的範圍 —— 兩者的輸出都
    是一張看起來很正常的圖，差別只在數字，而那正是使用者看不出來的那種錯。
    """
    borrow = str(params.get("range_from", "") or "").strip()
    if not borrow or borrow == str(params.get("source", "")):
        return src
    return require_image(ctx, step_key, borrow)


@register_step
class PercentileNormStep(Step):
    """百分位正規化：P_low–P_high 拉伸到 0–255。"""

    key = "percentile_norm"
    label = "Normalize · Percentile"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Stretch image brightness over a percentile range (P2-P98 by "
            "default) to 0-255, removing brightness drift.")
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  label="Image stream", help=ONE_STREAM_HELP),
        ParamSpec(name="range_from", type="image_key", default="",
                  label="Borrow range from", help=_RANGE_FROM_HELP),
        ParamSpec(name="p_low", type="float", default=2.0, min=0.0, max=50.0,
                  help=("Lower percentile (0-50): pixels below it are clipped "
                        "to 0.")),
        ParamSpec(name="p_high", type="float", default=98.0, min=50.0, max=100.0,
                  help=("Upper percentile (50-100): pixels above it are clipped "
                        "to 255.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return _stream_reads(params)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "test"))]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        if p["p_low"] >= p["p_high"]:
            raise StepError(self.key, f"p_low ({p['p_low']}) must be smaller than p_high "
                            f"({p['p_high']}).")
        src = require_image(ctx, self.key, p["source"])
        basis = _range_basis(ctx, self.key, p, src)
        lo, hi = algo_normalize.percentile_range(basis, p["p_low"], p["p_high"])
        ctx.set_image(p["source"], _norm_to_u8(src, lo, hi))
        return ctx


@register_step
class GlvMaskNormStep(Step):
    """GLV 帶正規化：只用指定灰階範圍內的像素估計拉伸範圍。"""

    key = "glv_mask_norm"
    label = "Normalize · GLV band"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Estimate the brightness range from pixels inside a chosen gray "
            "band only, then stretch to 0-255 — this locks onto the brightness "
            "of one particular pattern.")
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  label="Image stream", help=ONE_STREAM_HELP),
        ParamSpec(name="range_from", type="image_key", default="",
                  label="Borrow range from", help=_RANGE_FROM_HELP),
        ParamSpec(name="glv_low", type="int", default=0, min=0, max=255,
                  help=("Lower edge of the gray band (0-255): only pixels inside "
                        "the band take part in the range estimate.")),
        ParamSpec(name="glv_high", type="int", default=255, min=0, max=255,
                  help=("Upper edge of the gray band (0-255); must be greater "
                        "than or equal to glv_low.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return _stream_reads(params)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "test"))]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        if p["glv_low"] > p["glv_high"]:
            raise StepError(self.key, f"glv_low ({p['glv_low']}) cannot be greater than "
                            f"glv_high ({p['glv_high']}).")
        src = require_image(ctx, self.key, p["source"])
        basis = _range_basis(ctx, self.key, p, src)
        lo, hi = algo_normalize.percentile_range_glv_masked(
            basis.astype(np.float32), p["glv_low"], p["glv_high"])
        ctx.set_image(p["source"], _norm_to_u8(src, lo, hi))
        return ctx


@register_step
class HistMatchStep(Step):
    """直方圖匹配：把 moving 的亮度分布對齊到 reference。"""

    key = "hist_match"
    label = "Normalize · Histogram match"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Match the moving image's brightness distribution to the reference "
            "image so the two can be subtracted directly.")
    requires_ref = True
    params = [
        ParamSpec(name="moving", type="image_key", default="test",
                  label="Adjust this stream",
                  help=("Image stream whose brightness is adjusted (the result "
                        "overwrites the same stream).")),
        ParamSpec(name="reference", type="image_key", default="ref",
                  label="Match it to",
                  help="Brightness reference stream (never modified)."),
        ParamSpec(name="method", type="choice", default="linear",
                  choices=["exact", "linear", "percentile"],
                  help=("Matching method: linear = align mean/standard deviation "
                        "(most natural); exact = identical histograms; "
                        "percentile = align P2-P98 (robust to outliers).")),
    ]
    reads = ["test", "ref"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("moving", "test"), params.get("reference", "ref")]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("moving", "test")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        mov = to_uint8(require_image(ctx, self.key, p["moving"]))
        ref = to_uint8(require_image(ctx, self.key, p["reference"]))
        fn = algo_histmatch.MATCH_FN[p["method"]]
        ctx.set_image(p["moving"], fn(mov, ref))
        return ctx
