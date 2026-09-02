# d4t step-card library — authored 2026-07-28 (M1).
"""focus_quality — 影像品質（對焦）量測卡。"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import iqi as algo_iqi
from ..algo import quality as algo_quality
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import MultiSourceStep, output_prefix_spec, parse_key_list

#: 這張卡量得出來的四個銳利度數字。**前三個是預設**（既有 recipe 一個位元組
#: 都不動）；``focus_iqi`` 是 F77 加的 OP-301 指標，勾了才算 —— 它一顆 defect
#: 要做 64 次 FFT，不該無條件付這筆錢。
METRIC_CHOICES = ("focus_lapvar", "focus_tenengrad", "focus_fft", "focus_iqi")
DEFAULT_METRICS = "focus_lapvar,focus_tenengrad,focus_fft"

#: ``focus_iqi`` 勾了才會跟著出現的兩個。它們是 IQI **自己做的決定**變成的
#: 數字（F19：卡片自動做的每一個決定，都要變成一個使用者畫得出分布的數字）：
#: 這張圖有多少地方真的有 pattern、以及最後平均了幾塊。
IQI_EXTRA = ("focus_iqi_pattern", "focus_iqi_blocks")


#: IQI 那幾格的顯示條件 —— 勾了 ``focus_iqi`` 才出現。
IQI_WHEN = ("metrics", ("focus_iqi",))


def _named(spec, section: str):
    """把共用的 `output_prefix_spec` 放進這張卡自己的分節。

    不放的話它會掉進**前一格的分節**（畫面上「Name these results」出現在
    「2 · IQI (OP-301)」的標題底下）—— 而那個標題正在說謊。
    """
    from dataclasses import replace
    return replace(spec, section=str(section))


def _metrics_of(params) -> list:
    got = parse_key_list((params or {}).get("metrics", DEFAULT_METRICS))
    return got or list(parse_key_list(DEFAULT_METRICS))


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
                  section="1 · What to measure",
                  help="Image stream to measure sharpness on."),
        ParamSpec(name="metrics", type="metric_chips", default=DEFAULT_METRICS,
                  label="Sharpness numbers", section="1 · What to measure",
                  choices=list(METRIC_CHOICES),
                  help=("Which sharpness numbers to output - each becomes a "
                        "feature with the same name. The first three are quick "
                        "whole-image measures. IQI is the OP-301 method: it "
                        "cuts the image into 64 blocks, washes the background "
                        "out of each one and averages the sharpest 30% - "
                        "slower, but it does not get fooled by an empty "
                        "corner.")),
        # ---- IQI 的旋鈕（F77）—— **勾了才出現** ----------------------------
        # `param_visible` 對逗號清單做的是**成員比對**（F37），所以
        # ``metrics`` 這種多選格拿來當條件是成立的：問的是「focus_iqi 在不在
        # 裡面」，不是「整串等不等於 focus_iqi」。
        # 沒有這一條的下場實測過：IQI 根本沒勾，畫面上卻擺著它的兩支滑桿。
        ParamSpec(name="iqi_blocks", type="int", default=algo_iqi.DEFAULT_BLOCKS,
                  min=2, max=32, label="Blocks per side",
                  section="2 · IQI (OP-301)", show_when=IQI_WHEN,
                  help=("How many blocks to cut each side into - 8 means the "
                        "64 blocks OP-301 uses. It is deliberately fixed "
                        "rather than tied to the image size, so a 1024 image "
                        "and a 2000 image give scores you can compare.")),
        ParamSpec(name="iqi_keep_percent", type="float",
                  default=algo_iqi.DEFAULT_KEEP_PERCENT, min=1.0, max=100.0,
                  unit="%", label="Average the sharpest",
                  show_when=IQI_WHEN,
                  section="2 · IQI (OP-301)",
                  help=("How many of the blocks go into the final average. "
                        "30% of 64 is 19. Averaging all of them would let the "
                        "empty-background blocks - which score low because "
                        "there is nothing there, not because it is out of "
                        "focus - drag the number down.")),
        ParamSpec(name="iqi_cutoff_percent", type="float",
                  default=algo_iqi.DEFAULT_CUTOFF_PERCENT, min=0.0, max=50.0,
                  unit="%", label="Wash out background below",
                  show_when=IQI_WHEN,
                  section="2 · IQI (OP-301)", advanced=True,
                  help=("Slow shading - uneven lighting, a bright corner - is "
                        "not sharpness, so it is removed before the score is "
                        "taken. The number is a share of the finest detail "
                        "the image can hold, so it means the same thing on "
                        "any image size. 0 leaves the shading in.")),
        ParamSpec(name="iqi_noise_percent", type="float",
                  default=algo_iqi.DEFAULT_NOISE_PERCENT, min=0.0, max=100.0,
                  unit="%", label="Also wash out noise above",
                  show_when=IQI_WHEN,
                  section="2 · IQI (OP-301)", advanced=True,
                  help=("Grain in an empty area is not sharpness either, but "
                        "it does carry energy - measured on a blank noisy "
                        "image, leaving it in scores 64 where washing it out "
                        "scores 7. Turn this up if empty corners come out "
                        "looking sharp. 0 leaves the grain in, which is what "
                        "the OP-301 write-up describes.")),
        ParamSpec(name="iqi_min_pattern", type="float", default=0.0,
                  min=0.0, max=1.0, label="Skip blocks with less pattern than",
                  show_when=IQI_WHEN,
                  section="2 · IQI (OP-301)", advanced=True,
                  help=("Blocks whose edges cover less than this share of "
                        "their pixels are left out before the sharpest ones "
                        "are averaged. 0 keeps every block - the sharpest-30% "
                        "cut already pushes empty blocks out on its own. "
                        "Raise it when a lot of the image is blank.")),
        _named(output_prefix_spec("test"), "3 · Output"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["focus_lapvar", "focus_tenengrad", "focus_fft"]
    FEATURE_HELP = {
        "focus_lapvar": "sharpness: variance of the Laplacian",
        "focus_tenengrad": "sharpness: mean gradient energy",
        "focus_fft": "sharpness: share of high frequencies",
        "focus_iqi": ("sharpness the OP-301 way: the sharpest 30% of 64 "
                      "blocks, after the background is washed out of each"),
        "focus_iqi_pattern": ("how much of the image has pattern at all "
                              "(edges, not flat background)"),
        "focus_iqi_blocks": "how many blocks went into that average",
    }
    FEATURE_UNITS = {
        "focus_iqi_pattern": "ratio", "focus_iqi_blocks": "count",
    }

    @classmethod
    def base_specs(cls, params: Dict[str, Any]):
        """基本名＋身分（PR-3）：勾了幾個銳利度值就幾個，metric = 名字本人。"""
        mids = _metrics_of(params)
        names = list(mids)
        if "focus_iqi" in mids:
            names += list(IQI_EXTRA)
        return [(str(n), str(n), "", "", "") for n in names]

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
        mids = _metrics_of(p)
        out = {"focus_lapvar": q["laplacian_var"],
               "focus_tenengrad": q["tenengrad"],
               "focus_fft": q["fft_hf_ratio"]}
        out = {k: v for k, v in out.items() if k in mids}
        if "focus_iqi" in mids:
            out.update(self._iqi(ctx, img, p))
        return out

    # ---- IQI (OP-301) ------------------------------------------------------
    def _iqi(self, ctx: Context, img, p: Dict[str, Any]) -> Dict[str, float]:
        """OP-301 的對焦分數（F77）—— 演算法在 `algo/iqi.py`，這裡只接線。

        ⚠ **打不進去的圖要當場講**（鐵則 4）：8 塊在一張 12 px 的 patch 上，
        每塊只剩 1 px —— `slice_blocks` 會拋，而那句話已經寫得夠白話（它講
        每塊剩幾個像素、以及兩條出路），所以原樣轉成 StepError。
        """
        try:
            got = algo_iqi.focus_index(
                img,
                blocks=int(p.get("iqi_blocks") or algo_iqi.DEFAULT_BLOCKS),
                keep_percent=float(p.get("iqi_keep_percent")
                                   or algo_iqi.DEFAULT_KEEP_PERCENT),
                cutoff_percent=float(p.get("iqi_cutoff_percent") or 0.0),
                noise_percent=float(p.get("iqi_noise_percent") or 0.0),
                min_pattern=float(p.get("iqi_min_pattern") or 0.0))
        except ValueError as e:
            raise StepError(self.key, str(e)) from None
        # 逐塊的分數留給儀表（同上面那份 `focus` note 的理由）—— 面板要畫
        # 「哪幾塊被算進去了」時，讀的必須是**引擎真的算過的那一份**。
        ctx.meta.setdefault("iqi", []).append({
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "prefix": str(p.get(self.CURRENT_PREFIX, "") or ""),
            "blocks": int(p.get("iqi_blocks") or algo_iqi.DEFAULT_BLOCKS),
            "scores": list(got["scores"]),
            "kept": int(got["blocks"]),
        })
        return {"focus_iqi": float(got["iqi"]),
                "focus_iqi_pattern": float(got["pattern_frac"]),
                "focus_iqi_blocks": float(got["blocks"])}
