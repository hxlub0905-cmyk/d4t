# d4t step-card library — authored 2026-07-28 (M1); merged into one card 2026-07-30 (F7-20).
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
METHODS = ("percentile", "zscore", "glv_band", "match", "local")

#: ``zscore`` 與 ``percentile`` / ``glv_band`` 共用「先量再套」那條路。
_MEASURED = ("percentile", "zscore", "glv_band")


def _norm_to_u8(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out01 = algo_normalize.normalize_image_with_range(img.astype(np.float32), lo, hi)
    return (np.clip(out01, 0.0, 1.0) * 255.0).astype(np.uint8)


_RANGE_FROM_HELP = (
    "Leave empty and each stream measures itself. Name another stream to "
    "measure there instead - the stretch range, or the average and spread - "
    "and use those numbers for every stream this card processes; that is what "
    "keeps test and ref comparable. They are read before this card changes "
    "anything, so it is always the original image.")


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
            name="method", type="chip_choice", default="percentile",
            choices=list(METHODS),
            icons=["norm_percentile", "norm_zscore", "norm_band", "norm_match",
                   "norm_local"],
            choice_labels={"zscore": "Z-score", "glv_band": "GLV band"},
            label="How to rescale",
            help=("percentile = stretch the P-low to P-high range of the whole "
                  "image to 0-255 (the usual choice); zscore = put the average "
                  "brightness and the spread on fixed values, so one gray "
                  "level always means the same number of noise levels; "
                  "glv_band = measure the "
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
        # ---- zscore -------------------------------------------------------
        ParamSpec(name="target_level", type="int", default=128, min=0, max=255,
                  label="Put the background at",
                  show_when=("method", ("zscore",)),
                  help=("Where the background of every image ends up (gray "
                        "levels). 128 is the middle of the scale, which leaves "
                        "the most room on both sides for defects that are "
                        "brighter and darker than the background.")),
        ParamSpec(name="target_spread", type="float", default=32.0,
                  min=1.0, max=96.0,
                  label="Put one noise level at",
                  show_when=("method", ("zscore",)),
                  help=("How many gray levels one noise level of this image "
                        "becomes. With 32, a pixel sitting 2 noise levels "
                        "above the background is always 64 gray levels "
                        "brighter - on every image and every lot, which is "
                        "what lets a fixed threshold downstream mean "
                        "something. Raise it for more visible contrast, but "
                        "above about 60 the bright and dark tails start "
                        "hitting the ends of the scale and flattening. Both "
                        "numbers are measured with medians, so a big defect in "
                        "the crop cannot move the scale.")),
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
        ParamSpec(name="range_from", type="image_key", direction="in", default="",
                  label="Borrow range from",
                  show_when=("method", _MEASURED),
                  help=_RANGE_FROM_HELP),
        ParamSpec(name="use_within", type="image_key", direction="in", default="",
                  label="Use only",
                  show_when=("method", _MEASURED + ("match",)),
                  help=("Leave empty to measure from every pixel. Name a mask "
                        "stream (from a Mask-from-regions card) and only the "
                        "pixels inside the mask are measured - the result is "
                        "still applied to the whole image. Use it when how much "
                        "of each pattern is in the crop changes from patch to "
                        "patch. (With Match to another stream, the brightness "
                        "statistics are taken inside the mask on both images.)")),
        # ---- match --------------------------------------------------------
        ParamSpec(name="reference", type="image_key", direction="in", default="ref",
                  label="Match it to", show_when=("method", ("match",)),
                  help=("Brightness reference stream (never modified). If this "
                        "stream is also in the list above it is left alone - "
                        "matching it to itself would do nothing.")),
        ParamSpec(name="match_method", type="chip_choice", default="linear",
                  choices=["exact", "linear", "percentile"],
                  icons=["hist_exact", "hist_linear", "hist_pct"],
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
        if method in _MEASURED:
            return [str(params.get("range_from", "") or "").strip(),
                    str(params.get("use_within", "") or "").strip()]
        if method == "match":
            # mask 也是一條**接進來的線**（F11 Enhance-1）：宣告漏了它，
            # 畫布上就不會有那條線，而使用者看不出這兩張卡有關係。
            return [str(params.get("reference", "ref")),
                    str(params.get("use_within", "") or "").strip()]
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
        if method == "zscore":
            return self._zscore_op(ctx, p)
        if method == "match":
            ref = to_uint8(require_image(ctx, self.key, p["reference"]))
            fn = algo_histmatch.MATCH_FN[p["match_method"]]
            within = str(p.get("use_within", "") or "").strip()
            if not within:
                return lambda img: fn(to_uint8(img), ref)
            # 只用 mask 內的像素量亮度統計，**套用仍是整張圖**（見
            # `algo/histmatch.py::_masked`：不然 mask 邊界會出現一道人工階梯）。
            mask = require_image(ctx, self.key, within)
            if mask.shape[:2] != ref.shape[:2]:
                raise StepError(
                    self.key,
                    "the mask '%s' is %dx%d but '%s' is %dx%d - point the "
                    "Mask-from-regions card's 'Same size as' at the same "
                    "stream this card processes."
                    % (within, mask.shape[1], mask.shape[0],
                       p["reference"], ref.shape[1], ref.shape[0]))
            return lambda img: fn(to_uint8(img), ref, mask=mask)
        clip, tiles = float(p["clip_limit"]), int(p["tiles"])
        return lambda img: algo_enhance.clahe(img, clip, tiles)

    def _measure_from(self, ctx: Context, p: Dict[str, Any]):
        """「先量再套」三個方法共用的兩件事：**量哪一張**、**量哪些畫素**。

        回傳 ``(basis, pixels_for)``：``basis`` 是 ``range_from`` 指的那張圖
        （沒填就是 None＝每條流量自己），``pixels_for(src)`` 是把 ``use_within``
        的 mask 套上去之後、真正拿來量的那群畫素。

        兩件事都在**迴圈之前**發生（`build_op` 只呼叫一次），所以量到的一定是
        這張卡還沒改過的原始值 —— F7-18 那個「借範圍的卡要排在前面」的陷阱
        就是這樣消失的。
        """
        borrow = str(p.get("range_from", "") or "").strip()
        basis = (require_image(ctx, self.key, borrow) if borrow else None)
        within = str(p.get("use_within", "") or "").strip()
        mask = (require_image(ctx, self.key, within) if within else None)

        def pixels_for(src: np.ndarray) -> np.ndarray:
            """量用的那群畫素（套用永遠是整張 ``img``，不在這裡）。"""
            if mask is None:
                return src
            if mask.shape[:2] != np.asarray(src).shape[:2]:
                raise StepError(
                    self.key,
                    f"the mask '{within}' is {mask.shape[1]}x{mask.shape[0]} "
                    f"but the image is {src.shape[1]}x{src.shape[0]} - point "
                    f"the Mask-from-regions card's 'Same size as' at the same "
                    f"stream this card processes.")
            sel = np.asarray(src)[np.asarray(mask) > 0]
            if sel.size == 0:
                # 全 0 的 mask（區域落在影像外）：退回整張圖，但要講 ——
                # 安靜地退回去，使用者會以為「只用 EPI」一直在生效。
                ctx.warn(f"normalize: mask '{within}' selects no pixels; "
                         f"measuring from the whole image instead.")
                return src
            return sel

        return basis, pixels_for

    def _zscore_op(self, ctx: Context, p: Dict[str, Any]):
        """把平均與標準差搬到固定值（F11 Enhance-2）。

        跟 ``percentile`` 差在**用什麼定錨**：percentile 釘的是兩個端點
        （P2→0、P98→255），所以輸出的一個灰階代表多少「實際的變異」逐張都不同；
        zscore 釘的是背景的位置與**一個 σ 的寬度**，所以輸出上「偏離背景 2 個 σ」
        永遠是同樣的灰階差 —— 那正是讓下游一個固定門檻跨批有意義的條件。

        **量的方式是中位數與 MAD，不是平均與標準差**（見
        ``algo/enhance.py::robust_level_spread``）：要量的東西就是缺陷本身，
        而平均／標準差會被缺陷帶著跑 —— 那會讓兩顆大小不同的缺陷被套上不同的
        縮放，正是正規化要消除的東西。要平均／標準差版本的話，這張卡的 ``match``
        ＋ ``linear`` 就是（它對齊的是另一條流的 mean/std）。

        代價：亮暗尾巴會撞到 0 / 255 而被削平（``target_spread`` 開太大時尤其），
        而那件事由基底的 ``clip_frac`` 講出來。
        """
        level = float(p["target_level"])
        spread = float(p["target_spread"])
        basis, pixels_for = self._measure_from(ctx, p)

        def op(img: np.ndarray) -> np.ndarray:
            src = img if basis is None else basis
            centre, sigma = algo_enhance.robust_level_spread(pixels_for(src))
            gain = spread / sigma if sigma > 1e-6 else 1.0
            # sigma 是 0 的話（完全平的圖）就只搬位置、不縮放：除以 0 會吐 inf，
            # 而 inf 會一路活到某個量測卡才變成 nan。
            #
            # **這裡刻意不 clip**：壓回 0–255 是基底的事（F11 Enhance-1），
            # 而它會順便把「被壓掉多少」算成 clip_frac。自己先 clip 掉的話那個
            # 數字永遠是 0 —— 削平的代價就又變回「只有直方圖看得到」。
            return (np.asarray(img, dtype=np.float32) - centre) * gain + level

        return op

    def _range_op(self, ctx: Context, p: Dict[str, Any], *, glv: bool):
        """percentile / glv_band 共用：先決定基準影像，再回傳逐張的拉伸函式。

        ``range_from`` 有填就在**迴圈之前**把那條流讀出來 —— 那時候這張卡還沒
        改過任何東西，所以借到的一定是原始值。留空的話 basis 是 None，
        每一條流各自量自己（那是 F7-18 之前就有的行為，沒有變）。

        ``use_within``（F8c）：範圍只從 mask 內的像素量，**套用仍是整張圖**。
        動機：MG 佔多少面積是隨 crop 變的（64px 的 patch 一根 MG 進出畫面就是
        12%），整張圖的 percentile 因此逐顆漂 —— 同一片 EPI，隔壁多一根 MG，
        正規化完就變一個值。mask 讓「拿來定範圍的那群像素」跨 patch 是同一種
        圖案。

        兩件事都由 :meth:`_measure_from` 提供，跟 ``zscore`` 共用同一份 ——
        「量哪一張、量哪些畫素」的規則寫兩次就會有兩種意思。
        """
        if glv:
            if p["glv_low"] > p["glv_high"]:
                raise StepError(self.key, f"the gray band lower edge ({p['glv_low']}) "
                                f"cannot be greater than the upper edge "
                                f"({p['glv_high']}).")
        elif p["p_low"] >= p["p_high"]:
            raise StepError(self.key, f"the low percentile ({p['p_low']}) must be "
                            f"smaller than the high percentile ({p['p_high']}).")

        basis, pixels_for_range = self._measure_from(ctx, p)

        def op(img: np.ndarray) -> np.ndarray:
            src = img if basis is None else basis
            sel = pixels_for_range(src)
            if glv:
                lo, hi = algo_normalize.percentile_range_glv_masked(
                    np.asarray(sel, dtype=np.float32), p["glv_low"], p["glv_high"])
            else:
                lo, hi = algo_normalize.percentile_range(sel, p["p_low"], p["p_high"])
            return _norm_to_u8(img, lo, hi)

        return op
