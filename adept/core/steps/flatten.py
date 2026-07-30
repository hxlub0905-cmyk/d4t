# ADEPT step-card library — authored 2026-07-29 (F7-10).
"""flatten —— 處理**空間性**假訊號的 Enhance 卡。

為什麼是一張卡而不是四張
------------------------
「背景平坦化」「去掃描線條紋」「top-hat」「black-hat」看起來是四種不同的東西，
但它們的結構完全一樣：**估一個大尺度的成分，然後把它減掉**。差別只在怎麼估
（高斯模糊／逐列中位數／形態學開閉運算）。所以它們是同一張卡的 ``method``，
不是四張卡 —— 卡片庫多四列，使用者要多讀四段說明才能知道該用哪一個；
一張卡的一個下拉，他只要讀一次。

CLAHE 以前放在這一檔（它不是「減掉什麼」而是「局部重新拉伸」），F7-20 已經
併進 ``normalize`` 卡的 ``local`` 方法 —— 它本來就跟那個家族同名
（``Normalize · Local contrast``），現在名實相符。

輸出 dtype
----------
這張卡輸出 float32。既有的 Enhance 卡多半維持 uint8，但這幾種運算會產生
負值（背景移除）或需要小數精度（CLAHE 後再做別的），硬轉回 uint8 會在
量測之前就先截掉資訊。下游的量測卡與 ``subtract`` 都吃得下 float32
（``diff`` 流本來就是 float32）。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import enhance as algo_enhance
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, register_step,
)
from ._util import MultiStreamStep, streams_spec


@register_step
class FlattenStep(MultiStreamStep):
    """移除大尺度的假訊號：亮度梯度、掃描線條紋、不平的背景。"""

    key = "flatten"
    label = "Remove background / stripes"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Remove large-scale artifacts that are not defects - charging "
            "brightness gradients, scan-line stripes, or an uneven background "
            "- so they stop showing up in the difference image.")
    params = [
        streams_spec("test"),
        ParamSpec(
            name="method", type="choice", default="background",
            choices=["background", "stripes_h", "stripes_v",
                     "bright_spots", "dark_spots"],
            label="Remove",
            help=("background = a smooth brightness gradient (charging); "
                  "stripes_h / stripes_v = scan-line stripes running across "
                  "or down the image; bright_spots / dark_spots = keep only "
                  "features smaller than the size below and drop everything "
                  "larger, whatever shape the background is."),
        ),
        ParamSpec(
            name="size", type="int", default=31, min=3, max=999, unit="px",
            label="Scale to remove",
            show_when=("method", ("background", "bright_spots", "dark_spots")),
            help=("How large the artifact is, in pixels. It must be clearly "
                  "BIGGER than your defects - anything smaller than this "
                  "survives, anything larger is removed. A quarter to a half "
                  "of the patch width is a good starting point."),
        ),
        ParamSpec(
            name="strength", type="float", default=1.0, min=0.0, max=1.0,
            label="Strength", show_when=("method", ("stripes_h", "stripes_v")),
            help=("How much of the estimated artifact to take out; 1 = all of "
                  "it. Real stripes are not always purely additive, so full "
                  "correction can overshoot."),
        ),
        ParamSpec(
            name="keep_level", type="bool", default=True,
            label="Keep original brightness",
            help=("Add the original average brightness back, so the image "
                  "stays in the gray range it started in and the thresholds "
                  "downstream still mean the same thing."),
        ),
    ]

    def build_op(self, ctx: Context, p: Dict[str, Any]):
        method = str(p["method"])
        size = int(p["size"])
        strength = float(p["strength"])
        keep = bool(p["keep_level"])

        def fn(img: Any) -> np.ndarray:
            if method == "background":
                return algo_enhance.remove_background(img, size, keep_level=keep)
            if method in ("stripes_h", "stripes_v"):
                return algo_enhance.remove_stripes(
                    img, axis=0 if method == "stripes_h" else 1,
                    strength=strength)
            out = algo_enhance.morph_residual(
                img, size, dark=(method == "dark_spots"))
            if keep:
                # top-hat / black-hat 的輸出以 0 為基準；把原本的亮度加回去，
                # 讓「輸出仍落在原本的灰階區間」這件事對五種方法都成立。
                out = out + float(np.nanmean(np.asarray(img, dtype=np.float32)))
            return out

        return lambda img: np.asarray(fn(img), dtype=np.float32)
