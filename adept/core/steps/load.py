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

from ..pipeline.channels import (
    highest_image_number, mapped_names, parse_channel_map,
)
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_INPUT,
)
from ._util import ensure_gray, to_uint8

# "auto" 模式下 channel 的優先順序（其餘 channel 依名稱排序附加在後）
_PREFERRED_ORDER = ("test", "ref", "single")


def _in_defect_order(images: Dict[str, Any]) -> List[str]:
    """這一顆的影像**依「第幾張」排序**的 ingest channel 名。

    多頁 TIFF 的每一張都帶 ``page``（0-based 絕對頁號），同一顆的幾張是連續的，
    所以照 page 排就是「這一顆的第 1、2、3… 張」。沒有 page 的（每顆一個檔案的
    資料集）就照 ingest 放進 dict 的順序 —— 那也是它給的順序。
    """
    keys = list(images)
    pages = [getattr(images[k], "page", None) for k in keys]
    if keys and all(p is not None for p in pages):
        return [k for _p, k in sorted(zip(pages, keys), key=lambda t: t[0])]
    return keys


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
            name="channel_map", type="channel_map", default="",
            label="Name the images",
            help=("Name this defect's images by position: 1 is the first "
                  "image, 2 the second, and so on (for example "
                  "'1:se1, 2:bse, 3:se2'). Leave empty to use the default "
                  "names (test, ref, img3...). The names become the streams "
                  "on the canvas and the prefix on this image's features."),
        ),
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
        mapped = mapped_names(parse_channel_map(params.get("channel_map", "")))
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() == "auto":
            # 有對照表就用它的名字 —— 那是使用者**自己命名**的結果，比
            # 「靜態下限」精確得多，畫布也才畫得出正確數量、正確名字的輸出埠。
            return mapped or list(cls.writes)
        wanted = [tok.strip() for tok in raw.split(",") if tok.strip()]
        return wanted or mapped or list(cls.writes)

    @classmethod
    def resolve_writes_for_kind(cls, params: Dict[str, Any], kind: str) -> List[str]:
        """validate 用的 kind-aware 宣告：ebi_patch → test+ref；rsem → single+test。

        **對照表優先於資料型別的預設**：使用者填了名字，那些就是這張卡會產出的流
        （F11 Input-1）。沒填才回到「這個 kind 通常有哪幾條」。
        """
        mapped = mapped_names(parse_channel_map(params.get("channel_map", "")))
        raw = str(params.get("channels", "auto")).strip()
        if raw.lower() != "auto":
            return cls.resolve_writes(params)
        if mapped:
            return mapped
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

        # ---- 通道對照表（F11 Input-1）：第幾張 → 叫什麼 ----------------------
        #
        # 對照表在 **recipe** 裡（使用者定調），所以同一份 recipe 拿到頁序不同的
        # 資料時**必須擋下來**：宣告了第 5 張的名字而這顆只有 2 張，照順序硬套的
        # 後果是「BSE 的數字寫在 SE 的名字上」—— 跑得完、有數字、而且是錯的。
        pairs = parse_channel_map(p.get("channel_map", ""))
        order = _in_defect_order(images)
        #: 流名 → **ingest 給的 channel 名**。改名只改「流叫什麼」，讀圖仍然要
        #: 用資料自己的 key（`item.load()` 只認得它自己那一份）。
        src_of = {k: k for k in order}
        if pairs:
            need = highest_image_number(pairs)
            if need > len(order):
                raise StepError(
                    self.key,
                    "the image names say there are at least %d images per "
                    "defect, but defect %s has %d (%s). Fix “Name the images” "
                    "or open the data this recipe was written for."
                    % (need, getattr(item, "defect_id", "?"), len(order),
                       ", ".join(order)))
            src_of = {name: order[page - 1] for page, name in pairs}
            unnamed = [k for k in order if k not in set(src_of.values())]
            if unnamed:
                # 沒被命名的那幾張**不載入**，但要講一句 —— 資料比 recipe 命名的
                # 多是使用者該知道的事（少講的話他會以為每一張都算進去了）。
                # 講的是「哪幾張」而不只是「幾張」：中間跳號也要看得見。
                ctx.warn("[%s] defect %s has %d images but only %d are named; "
                         "the rest (%s) are not loaded."
                         % (self.key, getattr(item, "defect_id", "?"),
                            len(order), len(src_of), ", ".join(unnamed)))
            images = {name: images[src] for name, src in src_of.items()}

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
                arr = item.load(src_of.get(ch, ch))
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
