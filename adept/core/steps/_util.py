# ADEPT step-card library — authored 2026-07-28 (M1).
"""步驟卡片共用的小工具（非卡片；不註冊任何 step）。

- ``require_image``  向 Context 要影像，缺流時轉成白話 StepError。
- ``to_uint8``       把任何灰階陣列安全轉成 uint8 0–255（[0,1] 浮點自動 ×255）。
- ``parse_key_list`` 逗號字串 → 影像流 key 清單（去空白、忽略空項）。
- ``ensure_gray``    彩色（3 通道）輸入自動轉灰階。
- ``output_prefix_spec`` / ``prefix_*``  量測卡的輸出名前綴（見下方說明）。
"""
from __future__ import annotations

from typing import Dict, List

import cv2
import numpy as np

from ..pipeline.context import Context, ContextError
from ..pipeline.step import ParamSpec, Step, StepError

# --------------------------------------------------------------------------- #
# 輸出名前綴（F7-11）—— 讓同一張量測卡可以用在好幾個區域上
# --------------------------------------------------------------------------- #
#: 特徵名是**扁平的全域命名空間**，而且是分數表達式的變數名。所以前綴只能用
#: 「可以當變數名」的字：開頭是字母或底線，後面接字母／數字／底線。
#: 打了空白或減號的話，`glv mean` 這種名字在表達式裡是指不到的 —— 擋在這裡，
#: 而不是等使用者寫完表達式才發現（鐵則 4）。
FEATURE_PREFIX_PATTERN = r"^$|^[A-Za-z_][A-Za-z0-9_]*$"


# --------------------------------------------------------------------------- #
# 一張卡做一條流（F7-18）
# --------------------------------------------------------------------------- #
#: Enhance 卡的主要參數共用的說明。
#:
#: 以前每張卡是「``target`` + ``also_apply``」兩個參數：主流一個、附帶的一串。
#: 那個形狀把 ``test`` 講成主角、``ref`` 講成附帶 —— 但它們就是兩張不同的
#: 輸入影像，兩張都該可以獨立處理。而「要對哪幾張做」是**畫布上的事**
#: （哪條線接進來），不是控制列上的一組勾選框。
#:
#: 所以現在一張卡就是一條流：要對 ref 也做同一件事，就再放一張卡接到 ref。
#: 畫布上因此看得到兩條各自的處理鏈，而不是一張卡偷偷動了兩條流。
ONE_STREAM_HELP = (
    "Which image stream this card works on; the result is written back to "
    "that same stream. Streams are the named lines on the canvas - test is "
    "the defect image, ref is the reference image. One card works on one "
    "stream: connect a stream to this card on the canvas (or pick it here), "
    "and add a second card if the other image needs the same treatment.")


# --------------------------------------------------------------------------- #
# 一張卡是**一次處理**，可以吃好幾條流（F7-19）
# --------------------------------------------------------------------------- #
#: 多流 Enhance 卡的主要參數說明。
#:
#: F7-18 的「一張卡一條流」保護的不變量是**畫布不能說謊**，而它用的手段是最
#: 保守的那個。代價是一份 recipe 會有一對 Normalize、一對 Denoise，**而它們
#: 必須維持同樣的參數才比得起來** —— 改了一張忘了另一張，是那個形狀帶進來的
#: 新的安靜失敗（見計畫書 §22.7 第一條）。
#:
#: 現在改成：接幾條流進來就處理幾條，**每條流一個埠**，所以第二條流在畫布上
#: 有一條真的線 —— 不變量還在，只是換一個手段達成。要讓兩條流吃不同的處理，
#: 就放兩張卡（那才是它們該長得不一樣的時候）。
STREAMS_HELP = (
    "Which image streams this card processes. Each one is read, processed "
    "with the settings below, and written back to itself - so connecting both "
    "test and ref means both get exactly the same treatment, which is what "
    "keeps them comparable. Streams are the named lines on the canvas. If the "
    "two images need DIFFERENT settings, use two cards instead.")


def streams_spec(default: str = "test") -> ParamSpec:
    """多流 Enhance 卡共用的 ``streams`` 參數。"""
    return ParamSpec(name="streams", type="image_keys", default=default,
                     label="Image streams", help=STREAMS_HELP)


class MultiStreamStep(Step):
    """共用基底：對 ``streams`` 裡的每一條流各做一次同樣的處理。

    卡片只實作 :meth:`build_op`（回傳一個 ``img -> img`` 的函式），迴圈由這裡
    負責 —— **不要在每張卡裡各寫一次迴圈**，那會變成四份會各自長歪的程式碼。

    ``build_op`` 在迴圈**之前**呼叫一次，所以需要「先量再套」的方法
    （``range_from``：借另一條流的拉伸範圍）拿到的一定是**還沒被這張卡改過**
    的原始值。F7-18 那個「借範圍的卡要排在前面、否則借到拉伸後的範圍」的陷阱
    （§22.7 第三條）就是這樣消失的：量與套用發生在同一次執行裡，中間插不進
    別的卡。
    """

    category = None          # 子類指定（CATEGORY_IMAGE）
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    #: 除了 ``streams`` 之外還會讀哪些流（例如借範圍的那條）。子類覆寫。
    @classmethod
    def extra_reads(cls, params: Dict[str, object]) -> List[str]:
        return []

    @classmethod
    def stream_list(cls, params: Dict[str, object]) -> List[str]:
        keys = parse_key_list(params.get("streams", "test"))
        return keys or ["test"]

    @classmethod
    def resolve_writes(cls, params: Dict[str, object]) -> List[str]:
        return cls.stream_list(params)

    @classmethod
    def resolve_reads(cls, params: Dict[str, object]) -> List[str]:
        out = list(cls.stream_list(params))
        for k in cls.extra_reads(params):
            if k and k not in out:
                out.append(k)
        return out

    def build_op(self, ctx: Context, params: Dict[str, object]):
        """回傳 ``img -> img``。迴圈之前呼叫一次（見類別 docstring）。"""
        raise NotImplementedError

    def skip_stream(self, key: str, params: Dict[str, object]) -> bool:
        """這一條流要不要跳過（預設都不跳）。"""
        return False

    def run(self, ctx: Context, params: Dict[str, object]) -> Context:
        p = self.validate_params(params)
        keys = self.stream_list(p)
        op = self.build_op(ctx, p)
        for key in keys:
            if self.skip_stream(key, p):
                continue
            img = require_image(ctx, self.key, key)
            ctx.set_image(key, op(img))
        return ctx


def output_prefix_spec(example: str = "center") -> ParamSpec:
    """量測卡共用的 ``output_prefix`` 參數（每張卡的說明只差一個例子）。"""
    return ParamSpec(
        name="output_prefix", type="str", default="",
        label="Name these results",
        pattern=FEATURE_PREFIX_PATTERN,
        pattern_help=("use letters, digits and underscores only, and do not "
                      "start with a digit"),
        help=("Put a name in front of every number this card produces, so two "
              "of these cards measuring two different regions do not overwrite "
              "each other. For example '%s' turns glv_mean into %s_glv_mean. "
              "Leave it empty if this is the only card of its kind."
              % (example, example)),
    )


def prefix_names(prefix: str, names: List[str]) -> List[str]:
    """把前綴套到一串特徵名上（前綴為空 = 原樣回傳）。"""
    p = str(prefix or "").strip()
    return [f"{p}_{n}" for n in names] if p else list(names)


def prefix_features(prefix: str, feats: Dict[str, float]) -> Dict[str, float]:
    """把前綴套到一組特徵值上（前綴為空 = 原樣回傳）。"""
    p = str(prefix or "").strip()
    return {f"{p}_{k}": v for k, v in feats.items()} if p else dict(feats)


def require_image(ctx: Context, step_key: str, key: str) -> np.ndarray:
    """取出影像流；不存在時拋白話 StepError（不讓 ContextError 直接外洩）。"""
    try:
        return ctx.require_image(key)
    except ContextError as e:
        raise StepError(step_key, f"missing image stream '{key}' ({e})") from None


def roi_rect_or_none(ctx, step_key: str, image, roi_name):
    """把 ``roi`` 參數解成像素矩形 ``(x, y, w, h)``；空字串 = 整張影像。

    ``'blob'`` 是保留名：優先找同名 ROI（``blob_segment`` 會寫），
    找不到才退回 ``meta['blobs']`` 的主 blob —— 這樣舊 recipe 與新 Region 段
    可以並存，而且 ``blob_segment`` 之後也還是同一個名字。
    找不到任何東西時回 ``None``（呼叫端決定要警告還是當成整張圖）。
    """
    import numpy as _np

    name = str(roi_name or "").strip()
    shape = None if image is None else _np.asarray(image).shape[:2]
    if not name:
        # 整張影像 —— 需要知道尺寸
        return None if shape is None else (0, 0, int(shape[1]), int(shape[0]))
    if name in ctx.roi_names():
        # 多框區域（F8）拿不到「一個矩形」。**不要偷偷回第一個** —— 那會給出
        # 一組看起來正常、實際上只描述了其中一塊的數字。要幾何的卡（量 CD、
        # 量框本身）本來就該指名單一的框，而每張多框卡都會另外給一個
        # ``<name>_center``（離 patch 中心最近的那一塊，也就是缺陷所在的那塊）。
        if ctx.roi_count(name) > 1:
            raise StepError(
                step_key,
                "region '%s' is %d separate boxes, and this card needs a "
                "single one. Point it at '%s_center' (the box nearest the "
                "middle of the patch, which is where the defect is), or use a "
                "card that can measure across several boxes."
                % (name, ctx.roi_count(name), name))
        # 具名 ROI 存的是正規化座標，一樣需要尺寸才展得開
        return None if shape is None else ctx.roi_rect(name, shape)
    if name == "blob":
        # blob 的矩形已經是像素座標，**不需要影像**（影像流可能已被下游覆寫掉）
        blobs = ctx.meta.get("blobs") or []
        if blobs:
            b = blobs[0]        # 主 blob = SNR 最強者（segment 已降冪排序）
            return (int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"]))
        # 退回整張圖是刻意的（Blob 卡跑了但這顆沒找到東西是正常的），但
        # **一定要說出來**：不講的話使用者拿到的是一組看起來很正常、實際上
        # 量的是整張圖的數字，而那是最難發現的一種錯。
        ctx.warn(f"[{step_key}] no blob was found on this defect, so region "
                 f"'blob' falls back to the whole image; the numbers from this "
                 f"card describe the whole patch, not a defect.")
        return None
    # 具名 ROI 打錯字要講清楚，不要安靜地量整張圖
    raise StepError(step_key,
                    "region '%s' is not defined; available: %s. Add a Define "
                    "region card upstream, or leave roi empty for the whole "
                    "image." % (name, ctx.roi_names()))


def crop_to_roi(ctx, step_key: str, image, roi_name):
    """依 ``roi`` 參數裁出要量測的像素（找不到 blob 時退回整張圖）。"""
    rect = roi_rect_or_none(ctx, step_key, image, roi_name)
    if rect is None:
        return image
    x, y, w, h = rect
    return image[y:y + h, x:x + w]


def roi_pixels(ctx, step_key: str, image, roi_name) -> np.ndarray:
    """區域裡的**像素本身**（一維），多框就把每一塊接起來（F8）。

    統計量（平均、標準差、百分位）只需要「有哪些像素」，不需要它們排成什麼
    形狀 —— 所以分散的 N 個框對這類卡而言就是一個像素母體。這也讓
    「這一組交界整體長什麼樣」問得出來，而那正是多框區域存在的理由。

    單框與整張圖走同一條路（N=1），所以呼叫端不必先問「這個區域有幾塊」。
    """
    name = str(roi_name or "").strip()
    arr = np.asarray(image)
    if name and name in ctx.roi_names() and ctx.roi_count(name) > 1:
        shape = arr.shape[:2]
        parts = [arr[y:y + h, x:x + w].reshape(-1)
                 for x, y, w, h in ctx.roi_rects(name, shape)
                 if w > 0 and h > 0]
        parts = [p for p in parts if p.size]
        if not parts:
            raise StepError(step_key,
                            "region '%s' has boxes but none of them covers any "
                            "pixel of this image." % name)
        return np.concatenate(parts)
    return np.asarray(crop_to_roi(ctx, step_key, image, name)).reshape(-1)


def ensure_gray(arr: np.ndarray) -> np.ndarray:
    """彩色影像轉單通道灰階；灰階原樣回傳。"""
    a = np.asarray(arr)
    if a.ndim == 3:
        if a.shape[2] == 4:
            return cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    return a


def to_uint8(arr: np.ndarray) -> np.ndarray:
    """任何灰階陣列 → uint8 0–255。

    - uint8 原樣回傳。
    - 浮點且值域看起來是 [0, 1] → ×255。
    - 其他（float 0–255、uint16 已是 0–255 值域…）→ clip 到 0–255 後轉型。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return a
    f = a.astype(np.float32)
    if f.size > 0:
        fmax = float(f.max())
        fmin = float(f.min())
        if 0.0 <= fmin and fmax <= 1.5:
            f = f * 255.0
    return np.clip(f, 0, 255).astype(np.uint8)


def parse_key_list(raw: str) -> List[str]:
    """逗號分隔字串 → key 清單；空白與空項自動忽略。"""
    if not raw:
        return []
    return [tok.strip() for tok in str(raw).split(",") if tok.strip()]
