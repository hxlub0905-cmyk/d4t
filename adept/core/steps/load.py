# ADEPT step-card library — authored 2026-07-28 (M1; F9 Phase 3d 拆成兩張卡).
"""Input 卡：把這顆 defect 的影像載進 pipeline。

**一種資料型別一張卡**（F9 Phase 3d）
--------------------------------------
以前只有一張 ``load_patch``，它同時吃 EBI patch（test + ref 兩頁）與 RSEM
單張，靠 ``channels="auto"`` 在**執行期**看資料長什麼樣才決定寫出哪幾條流。
那個設計有兩個代價：

1. **它吐什麼要等跑起來才知道。** 而畫布上的埠、lint 的「這條流誰產的」、
   快取的簽章都得在跑之前就答得出來 —— 所以 ``Step`` 一度需要一個
   ``resolve_writes_for_kind(params, kind)`` 的特例，把 dataset kind 一路傳到
   埠的計算裡。埠因此算了兩次而且兩邊答案可能不一樣（計畫書 §5d.3 那個坑：
   線接到 ``load.single``、執行期卻吐在 ``load.test`` 上，整條下游安靜地不跑）。
2. **使用者看不出這份 recipe 是給什麼資料用的。** 那件事以前寫在 ``routes``
   的鍵上，而 ``routes`` 不在畫布上。

拆成兩張卡之後兩件事都消失：每張卡吐什麼是**寫死的**（不必問 kind），
而「這條 pipeline 吃什麼」就是圖上第一張卡的名字 —— 看得到、選得掉、換得掉。

``accepts_kinds`` 是 Input 卡跟其他卡唯一的差別：引擎靠它決定「這批資料要從
哪一張卡開始跑」（見 ``recipe.execution_order``）。
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


class _LoadStep(Step):
    """兩張 Input 卡共用的實作（**不註冊**，卡片庫裡看不到它）。

    子類別只要說三件事：``key`` / ``label`` / ``accepts_kinds``，
    以及 ``auto_writes`` —— ``channels="auto"`` 時**一定**會有的那幾條流。
    """

    category = CATEGORY_IMAGE
    group = GROUP_INPUT
    params = [
        ParamSpec(
            name="channels", type="str", default="auto",
            help=("Which images to load: auto = the ones this input normally "
                  "has; or a comma separated list such as test,ref."),
        ),
    ]
    reads: List[str] = []
    features_out = ["n_channels"]

    #: ``channels="auto"`` 會寫出哪幾條影像流（**不看資料、不看 kind**）。
    auto_writes: List[str] = []

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() == "auto":
            return list(cls.auto_writes)
        return ([tok.strip() for tok in raw.split(",") if tok.strip()]
                or list(cls.auto_writes))

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

        # 單張資料流：把 single 同時鏡射為 test，讓下游卡片用預設參數
        # （source="test"）就能直接吃到影像。
        if "single" in loaded and "test" not in ctx.images:
            ctx.set_image("test", ctx.images["single"])
            note = (f"single-image input (kind={kind}): 'single' is also "
                    f"exposed as 'test' for downstream cards.")
            ctx.meta.setdefault("notes", []).append(note)

        # 面板用（F7-17）：**每條影像流是從哪一頁來的、載進來長什麼樣**。
        #
        # 「第一張是 test、第二張是 ref」已於 2026-07-30 由使用者確認，所以這裡
        # 不再是「驗證假設」的工具。留著是因為配對關係在別的地方都看不到：一顆
        # 出三頁以上、單頁鏡射成 test、或 channel_order 被改過的資料集，只有這份
        # meta 講得出實際載進來的是什麼。平均灰階則是拿來判「這兩張比得起來嗎」。
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


@register_step
class LoadPatchStep(_LoadStep):
    """EBI patch：一顆 defect 兩頁，第一頁 test、第二頁 ref。"""

    key = "load_patch"
    label = "Load patch pair"
    help = ("Start here for EBI patch data: load this defect's test and "
            "reference images, always converted to 8-bit grayscale.")
    accepts_kinds = ("ebi_patch",)
    writes = ["test", "ref"]
    auto_writes = ["test", "ref"]


@register_step
class LoadSingleStep(_LoadStep):
    """RSEM / 資料夾：一顆 defect 一張圖，沒有天生的 ref。"""

    key = "load_single"
    label = "Load single image"
    help = ("Start here for one image per defect (RSEM, or a folder of "
            "images): there is no reference, so build one upstream of any "
            "card that needs it.")
    accepts_kinds = ("rsem", "folder")
    #: ``single`` 會再鏡射一份成 ``test``（見 :meth:`_LoadStep.run`），所以
    #: 下游卡片用預設參數就吃得到影像。
    writes = ["single", "test"]
    auto_writes = ["single", "test"]
