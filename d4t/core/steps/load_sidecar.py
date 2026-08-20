# d4t step-card library — authored 2026-08-18 (F11 Region-3 第 2 步).
"""load_sidecar —— 把**別的程式產的、跟這顆對應的影像**載成一條流。

現在只有一種：GLAS 的 GDS **label map**（`<DEFECTID>_label.png`，0 = 背景、
1..N = 第 N 個 POI 層）。配對是在 ingest 層做的（`ingest/glas_export.attach`），
所以這張卡的參數裡**沒有目錄、沒有配對規則** —— 它只吃已經掛好的東西。

為什麼是自己一張卡
------------------
`load_single` 的契約是「一顆一張」，而且它在一顆有兩張時會**拒絕載入**
（那個拒絕是對的，見 `steps/load.py`）。把 label 混進 `DefectItem.images` 的話，
每一顆 RSEM defect 都會突然變成「兩張」而載不進來 —— 而錯誤訊息會說謊
（「這顆有 2 張影像」；不，它有 1 張影像跟 1 個附加檔）。所以附加檔住在
`DefectItem.sidecars`，而讀它的是這一張卡。

這也讓畫布維持誠實：**匯出掛上去了，畫布上就多一個埠；沒掛，那張卡跑不動並
講出為什麼。** 一張卡吐哪幾條流仍然只看使用者看得到的值（`out`）。

label 一個像素都不能動
----------------------
它的像素值**是** label id。任何拉伸、正規化、通道平均都會把 1、2、3 混成不存在
的值，**而且不會報錯**。所以這張卡不做 `to_uint8`、不做 `ensure_gray`：
讀進來是什麼就是什麼（`DefectItem.load_sidecar` 只擋非 8-bit）。
三通道的圖在這裡是**錯誤**不是「幫忙轉一下」—— 那多半是指到了
`<id>_label_view.png`（GLAS 給人看的上色版），而那條路的答案永遠是錯的。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..ingest.glas_export import SIDECAR_LABEL
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_INPUT, ParamSpec, Step, StepError, register_step,
)


@register_step
class LoadSidecarStep(Step):
    """GLAS 的 label map → 一條影像流。"""

    key = "load_sidecar"
    label = "Load layout labels"
    category = CATEGORY_IMAGE
    group = GROUP_INPUT
    help = ("Load the layout label map that GLAS exported for this defect - "
            "one image where every pixel value is a layer number (0 is "
            "background). It is not a picture of the wafer, it is a map of "
            "which layer is where, and the Region card turns it into named "
            "regions. There is nothing to pick on this card: open the lot "
            "first, then attach the export folder with the “Open GDS export…” "
            "button on this card. Defects the export has no label for will fail this "
            "card and say so, and the rest of the batch carries on.")
    params = [
        ParamSpec(
            name="out", type="image_key", direction="out",
            default=SIDECAR_LABEL, label="Name this image",
            help=("Name of the image stream this card produces. It is what "
                  "the Region card connects to."),
        ),
    ]
    reads: List[str] = []
    writes = [SIDECAR_LABEL]
    features_out: List[str] = []

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", SIDECAR_LABEL) or "").strip()
        return [name] if name else []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        item = ctx.meta.get("_defect_item")
        if item is None:
            raise StepError(self.key, "no defect data in the Context "
                            "(meta['_defect_item']); this card must be run by "
                            "the engine after a dataset is loaded.")
        cars = getattr(item, "sidecars", None) or {}
        if SIDECAR_LABEL not in cars:
            # **講得出可以照做的下一步。** 「找不到」對不會寫 code 的人是一個
            # 死路 —— 而這裡有兩種完全不同的原因（沒掛匯出 vs 這一顆被 GLAS
            # 的分數門檻擋掉），使用者要分得出自己是哪一種。
            raise StepError(
                self.key,
                "defect %s has no layout label. Either no GLAS export is "
                "attached to this lot - attach one with the “Open GDS export…” "
                "button on this card - or this defect has no label in it (GLAS leaves "
                "out the ones its alignment score rejected). The rest of the "
                "batch is unaffected."
                % getattr(item, "defect_id", "?"))
        try:
            arr = item.load_sidecar(SIDECAR_LABEL)
        except Exception as e:              # 檔案毀損 / 位元深度不對等
            raise StepError(self.key,
                            "could not read the layout label: %s" % e) from e
        a = np.asarray(arr)
        if a.ndim != 2:
            raise StepError(
                self.key,
                "the layout label has %d channels; it must be a single-channel "
                "image because each pixel value IS a layer number. A "
                "three-channel one is almost certainly *_label_view.png, "
                "which is GLAS's coloured preview - point the export at the "
                "*_label.png files instead." % (1 if a.ndim < 3 else a.shape[2]))

        name = str(p["out"]).strip()
        # **原樣寫進去。** 這裡不 to_uint8、不 ensure_gray —— 見模組說明。
        ctx.set_image(name, a)
        ids = sorted(int(v) for v in np.unique(a))
        ctx.meta.setdefault("layout_label", {})[name] = {
            "ids": ids,
            "shape": [int(v) for v in a.shape[:2]],
            # 每個 id 佔多少比例 —— 儀表要畫得出「這一顆對到了哪幾層」，
            # 而「某一層是 0 個像素」跟「沒有那一層」在畫面上長得一樣。
            "share": {int(v): float((a == v).mean()) for v in ids},
        }
        return ctx
