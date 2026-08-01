# ADEPT step-card library — authored 2026-07-28 (M1); merged into one card 2026-07-30 (F7-20).
"""normalize —— **一張** Normalize 卡，四種方法。

為什麼是一張卡而不是四張
------------------------
使用者看著卡片庫說的：

> 「正規化相關功能的就放在一起（我看有好多種 GLV Band、Histogram Match、
>   CLAHE、Percentile）他們都是正規化，放在一起讓 user 勾選用哪一種即可，
>   不要分那麼多。」

他是對的，而且這個 repo 裡已經有先例：``flatten`` 把「背景平坦化／掃描線條紋／
top-hat／black-hat」四種做法收成一張卡的 ``method``，理由一字不差 ——
**卡片庫多三列，使用者就要多讀三段說明才能知道該用哪一個；一張卡的一個下拉，
他只要讀一次。**

四種方法解決的是同一個問題（**把灰階重新映射，好讓兩張圖比得起來 / 讓缺陷看得
出來**），差別只在拉伸的範圍怎麼決定：

===============  ==========================================================
percentile       從整張圖的 P_low–P_high 決定
glv_band         只看落在指定灰階帶裡的像素（鎖定某一種圖案的亮度）
match            不自己決定，直接對齊另一條流的分布
local            不用單一範圍，分格子各自拉（CLAHE）
===============  ==========================================================

參數會跟著方法出現／消失（``ParamSpec.show_when``）。沒有那個機制的話這張卡有
十個參數而任何一個方法只用得到兩三個，使用者得自己判斷「我選了 CLAHE，那 p_low
還算不算數」—— 那正是看得懂與看不懂的分界。

一張卡吃好幾條流（F7-19）
-------------------------
``streams`` 是一串影像流：接 test 也接 ref，兩條就吃**同一組設定**，
而那正是「兩張圖還比得起來」的前提。要讓兩條流吃不同設定就放兩張卡。

``range_from`` 原樣保留（F7-18 §22.5 加的）：留空 = 每條流各自量自己的範圍，
填了 = 大家都用那條流量出來的範圍。而且它的**順序陷阱消失了** ——
基準值在迴圈之前就量好，那時候這張卡還沒改過任何東西。

與 ``tone.py`` 的差別（很重要，不要混用）
-----------------------------------------
這一檔是**自動**的：從影像自己算出範圍再拉伸，目的是「把兩張圖變成可以比」。
``tone.py`` 是**手動**的：使用者直接指定加多少亮度、套什麼 gamma，目的是
「讓我看得清楚」。兩者都可以用，但手動那張通常放在正規化**之後**，
否則正規化會把你剛調的東西再拉回去。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import histmatch as algo_histmatch
from ..algo import normalize as algo_normalize
from ..algo import enhance as algo_enhance
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, StepError, register_step,
)
from ._util import MultiStreamStep, require_image, streams_spec, to_uint8

__all__ = ["NormalizeStep"]

#: 方法值 → 畫面上的字（``choice`` 目前只吃字串清單，所以說明寫在 help 裡）。
METHODS = ("percentile", "glv_band", "match", "local")


def _norm_to_u8(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out01 = algo_normalize.normalize_image_with_range(img.astype(np.float32), lo, hi)
    return (np.clip(out01, 0.0, 1.0) * 255.0).astype(np.uint8)


_RANGE_FROM_HELP = (
    "Leave empty and each stream's stretch range is measured on itself. Name "
    "another stream to measure the range there and use it for every stream "
    "this card processes - that is what keeps test and ref comparable. The "
    "range is read before this card changes anything, so it is always the "
    "original image.")


@register_step
class NormalizeStep(MultiStreamStep):
    """把灰階重新映射，好讓兩張圖比得起來（四種方法，見模組 docstring）。"""

    key = "normalize"
    label = "Normalize"
    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    help = ("Rescale gray levels so brightness drift stops looking like a "
            "defect and the two images can be compared. Pick how the range is "
            "decided below.")
    params = [
        streams_spec("test"),
        ParamSpec(
            name="method", type="choice", default="percentile", choices=list(METHODS),
            label="How to rescale",
            help=("percentile = stretch the P-low to P-high range of the whole "
                  "image to 0-255 (the usual choice); glv_band = measure the "
                  "range using only pixels inside a chosen gray band, which "
                  "locks onto one particular pattern; match = do not decide a "
                  "range at all, just make this stream's brightness "
                  "distribution equal to another stream's; local = stretch "
                  "tile by tile (CLAHE) so a faint defect in a dark area "
                  "still comes up."),
        ),
        # ---- percentile ---------------------------------------------------
        ParamSpec(name="p_low", type="float", default=2.0, min=0.0, max=50.0,
                  label="Low percentile", show_when=("method", ("percentile",)),
                  help=("Lower percentile (0-50): pixels below it are clipped "
                        "to 0.")),
        ParamSpec(name="p_high", type="float", default=98.0, min=50.0, max=100.0,
                  label="High percentile", show_when=("method", ("percentile",)),
                  help=("Upper percentile (50-100): pixels above it are clipped "
                        "to 255.")),
        # ---- glv_band -----------------------------------------------------
        ParamSpec(name="glv_low", type="int", default=0, min=0, max=255,
                  label="Gray band from", show_when=("method", ("glv_band",)),
                  help=("Lower edge of the gray band (0-255): only pixels inside "
                        "the band take part in the range estimate.")),
        ParamSpec(name="glv_high", type="int", default=255, min=0, max=255,
                  label="Gray band to", show_when=("method", ("glv_band",)),
                  help=("Upper edge of the gray band (0-255); must be greater "
                        "than or equal to the lower edge.")),
        # ---- 兩種「量範圍」的方法共用 ---------------------------------------
        ParamSpec(name="range_from", type="image_key", default="",
                  label="Borrow range from",
                  show_when=("method", ("percentile", "glv_band")),
                  help=_RANGE_FROM_HELP),
        # ---- match --------------------------------------------------------
        ParamSpec(name="reference", type="image_key", default="ref",
                  label="Match it to", show_when=("method", ("match",)),
                  help=("Brightness reference stream (never modified). If this "
                        "stream is also in the list above it is left alone - "
                        "matching it to itself would do nothing.")),
        ParamSpec(name="match_method", type="choice", default="linear",
                  choices=["exact", "linear", "percentile"],
                  label="Matching", show_when=("method", ("match",)),
                  help=("linear = align mean and standard deviation (most "
                        "natural); exact = make the histograms identical; "
                        "percentile = align P2-P98 (robust to outliers).")),
        # ---- local (CLAHE) ------------------------------------------------
        ParamSpec(name="clip_limit", type="float", default=2.0, min=0.1, max=40.0,
                  label="Contrast limit", show_when=("method", ("local",)),
                  help=("Ceiling on how much contrast one tile may gain. Raise "
                        "it for more punch; too high and flat areas amplify "
                        "their own noise until it looks like signal.")),
        ParamSpec(name="tiles", type="int", default=8, min=1, max=32,
                  label="Tiles per side", show_when=("method", ("local",)),
                  help=("The image is divided into this many tiles across and "
                        "down. More tiles follow local brightness more closely, "
                        "but a defect larger than one tile starts being treated "
                        "as background and fades out.")),
    ]
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []
    #: 類別層級仍宣告 False —— 只有 ``match`` 方法真的需要 ref，
    #: 而那是 :meth:`resolve_requires_ref` 回答的（見 step.py）。
    requires_ref = False

    # ---- 契約 -------------------------------------------------------------
    @classmethod
    def extra_reads(cls, params: Dict[str, Any]) -> List[str]:
        method = str(params.get("method", "percentile"))
        if method in ("percentile", "glv_band"):
            return [str(params.get("range_from", "") or "").strip()]
        if method == "match":
            return [str(params.get("reference", "ref"))]
        return []

    @classmethod
    def resolve_requires_ref(cls, params: Dict[str, Any]) -> bool:
        return str(params.get("method", "percentile")) == "match"

    def skip_stream(self, key: str, params: Dict[str, Any]) -> bool:
        # 把 reference 對齊到它自己是個 no-op，但那會讓使用者以為它被處理過了。
        return (str(params.get("method", "")) == "match"
                and key == str(params.get("reference", "ref")))

    # ---- 運算 -------------------------------------------------------------
    def build_op(self, ctx: Context, p: Dict[str, Any]):
        method = str(p["method"])
        if method == "percentile":
            return self._range_op(ctx, p, glv=False)
        if method == "glv_band":
            return self._range_op(ctx, p, glv=True)
        if method == "match":
            ref = to_uint8(require_image(ctx, self.key, p["reference"]))
            fn = algo_histmatch.MATCH_FN[p["match_method"]]
            return lambda img: fn(to_uint8(img), ref)
        clip, tiles = float(p["clip_limit"]), int(p["tiles"])
        return lambda img: algo_enhance.clahe(img, clip, tiles)

    def _range_op(self, ctx: Context, p: Dict[str, Any], *, glv: bool):
        """percentile / glv_band 共用：先決定基準影像，再回傳逐張的拉伸函式。

        ``range_from`` 有填就在**迴圈之前**把那條流讀出來 —— 那時候這張卡還沒
        改過任何東西，所以借到的一定是原始值。留空的話 basis 是 None，
        每一條流各自量自己（那是 F7-18 之前就有的行為，沒有變）。
        """
        if glv:
            if p["glv_low"] > p["glv_high"]:
                raise StepError(self.key, f"the gray band lower edge ({p['glv_low']}) "
                                f"cannot be greater than the upper edge "
                                f"({p['glv_high']}).")
        elif p["p_low"] >= p["p_high"]:
            raise StepError(self.key, f"the low percentile ({p['p_low']}) must be "
                            f"smaller than the high percentile ({p['p_high']}).")

        borrow = str(p.get("range_from", "") or "").strip()
        basis = (require_image(ctx, self.key, borrow) if borrow else None)

        def op(img: np.ndarray) -> np.ndarray:
            src = img if basis is None else basis
            if glv:
                lo, hi = algo_normalize.percentile_range_glv_masked(
                    np.asarray(src, dtype=np.float32), p["glv_low"], p["glv_high"])
            else:
                lo, hi = algo_normalize.percentile_range(src, p["p_low"], p["p_high"])
            return _norm_to_u8(img, lo, hi)

        return op
