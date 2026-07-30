# ADEPT step-card library — authored 2026-07-28 (M1).
"""load_patch — 載入影像卡。

從 ``ctx.meta["_defect_item"]``（ingest 層的 DefectItem，由引擎放入）讀出
這顆 defect 的各 channel 像素並寫進 ``ctx.images``。

writes 說明：類別層級靜態宣告 ``writes=["test"]`` 只是保守下限——實際會寫哪些
影像流取決於 ``channels`` 參數與資料本身（ebi_patch 通常是 test+ref；rsem 單張
會寫 single 並同時鏡射一份到 test），由 ``resolve_writes`` 在拿到參數後盡力
解析，"auto" 模式下仍以執行期為準。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_INPUT,
)
from ._util import ensure_gray, to_uint8

# "auto" 模式下 channel 的優先順序（其餘 channel 依名稱排序附加在後）
_PREFERRED_ORDER = ("test", "ref", "single")


@register_step
class LoadPatchStep(Step):
    """把 DefectItem 的影像載入成 Context 影像流（一律轉成 uint8 灰階）。"""

    key = "load_patch"
    label = "Load images"
    category = CATEGORY_IMAGE
    group = GROUP_INPUT
    help = ("Load this defect's images (test/ref, or a single image) into the "
            "pipeline, always converted to 8-bit grayscale.")
    params = [
        ParamSpec(
            name="channels", type="str", default="auto",
            help=("Which images to load: auto = whatever is available "
                  "(a single RSEM image is also exposed as test); or a comma "
                  "separated list such as test,ref."),
        ),
    ]
    reads: List[str] = []
    writes = ["test"]            # 保守靜態宣告；實際流以執行期解析為準（見模組 docstring）
    features_out = ["n_channels"]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() == "auto":
            return list(cls.writes)     # auto：靜態下限，實際以執行期為準
        return [tok.strip() for tok in raw.split(",") if tok.strip()] or list(cls.writes)

    @classmethod
    def resolve_writes_for_kind(cls, params: Dict[str, Any], kind: str) -> List[str]:
        """validate 用的 kind-aware 宣告：ebi_patch → test+ref；rsem → single+test。"""
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() != "auto":
            return cls.resolve_writes(params)
        if kind == "ebi_patch":
            return ["test", "ref"]
        if kind == "rsem":
            return ["single", "test"]   # single 會鏡射為 test（見 run()）
        return list(cls.writes)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        item = ctx.meta.get("_defect_item")
        kind = ctx.meta.get("_dataset_kind")
        if item is None:
            raise StepError(self.key, "no defect data in the Context (meta['_defect_item']); this "
                            "card must be run by the engine after a dataset is loaded.")
        images = getattr(item, "images", None)
        if not images:
            raise StepError(self.key, f"defect {getattr(item, 'defect_id', '?')} has no images to load.")

        raw = str(p["channels"]).strip()
        if raw.lower() == "auto":
            avail = list(images.keys())
            wanted = [c for c in _PREFERRED_ORDER if c in avail]
            wanted += sorted(c for c in avail if c not in wanted)
        else:
            wanted = [tok.strip() for tok in raw.split(",") if tok.strip()]
            if not wanted:
                raise StepError(self.key, "the channels parameter is empty; use auto or a comma "
                                "separated list (e.g. test,ref).")

        loaded: List[str] = []
        for ch in wanted:
            if ch not in images:
                raise StepError(
                    self.key,
                    f"defect {getattr(item, 'defect_id', '?')} has no channel "
                    f"'{ch}' (available: {sorted(images)}).")
            try:
                arr = item.load(ch)
            except Exception as e:  # 檔案毀損 / 頁碼超界等
                raise StepError(self.key, f"could not read channel '{ch}': {e}") from e
            arr_u8 = to_uint8(ensure_gray(arr))
            ctx.set_image(ch, arr_u8)
            loaded.append(ch)

        # rsem / folder 單張資料流：把 single 同時鏡射為 test，讓下游卡片
        # 用預設參數（source="test"）就能直接吃到影像。
        if "single" in loaded and "test" not in ctx.images:
            ctx.set_image("test", ctx.images["single"])
            note = (f"single-image input (kind={kind}): 'single' is also "
                    f"exposed as 'test' for downstream cards.")
            ctx.meta.setdefault("notes", []).append(note)

        # 面板用（F7-17）：**每條影像流是從哪一頁來的、載進來長什麼樣**。
        #
        # 這不是裝飾。「每顆 defect 第一張是 test、第二張是 ref」是全專案第一條
        # 待廠內驗證的假設（CLAUDE.md §8），而目前唯一的驗證方式是另外跑
        # fab_probe 腳本。把配對與每一頁的平均灰階直接攤在畫面上，使用者載入
        # 第一份真資料的當下就會看到「咦，第二張比較亮」—— 那就是順序反了的證據。
        pages = []
        for ch in loaded:
            ref = images.get(ch)
            arr = ctx.images.get(ch)
            pages.append({
                "channel": ch,
                "page": None if ref is None else getattr(ref, "page", None),
                "file": "" if ref is None else str(getattr(ref, "path", "")),
                "shape": None if arr is None else [int(v) for v in arr.shape[:2]],
                "mean": None if arr is None else float(arr.mean()),
            })
        ctx.meta["input"] = {
            "kind": str(kind or ""),
            "defect_id": str(getattr(item, "defect_id", "")),
            "die": list(getattr(item, "die", None) or []),
            "xrel_nm": getattr(item, "xrel_nm", None),
            "yrel_nm": getattr(item, "yrel_nm", None),
            "klarf_row": int(getattr(item, "klarf_row", -1)),
            "nm_per_px": getattr(item, "nm_per_px", None),
            "pages": pages,
        }

        ctx.add_feature("n_channels", float(len(loaded)))
        return ctx
