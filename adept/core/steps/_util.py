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
    return ParamSpec(name="streams", type="image_keys", direction="in", default=default,
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
        """接進來的那幾條流。**空的就是空的**（F10）。

        以前這裡是 ``keys or ["test"]`` —— 一張沒有接線的卡會安靜地跑回
        ``test``。那個 ``or`` 是「畫布說謊」的一個源頭：畫面上沒有線、參數是
        空的，而它照樣量得出數字，於是使用者沒有任何線索知道自己漏接了。

        現在空的就是沒有來源：畫布不畫輸出埠、lint 報 ``not-connected``、
        引擎在跑之前就擋下來並講一句可以照做的話。
        """
        return parse_key_list(params.get("streams", "test"))

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

    def note_stream(self, ctx: Context, key: str, img: np.ndarray,
                    params: Dict[str, object]) -> None:
        """處理**之前**，這一條流有什麼值得記進 ``ctx.meta`` 的（預設不記）。

        存在的理由：``build_op`` 在迴圈之前只呼叫一次，所以它看不到「哪一條流、
        長什麼樣」。而右下角的儀表要回答的問題常常是**逐流**的（例如 Denoise 的
        「這張圖的雜訊 σ 是多少」——`strength` 的單位就是那個 σ）。

        用 hook 而不是「讓 op 多收一個參數」：op 是使用者程式碼裡最短的那一段
        （`img -> img`），把診斷混進去會讓四張卡各自長出一份。
        """

    #: 超過這個比例的像素被壓回值域就講一句話（F11 Enhance-1）。
    #:
    #: 為什麼是固定值而不是一個參數：這不是一個「效果」旋鈕，是一句診斷。
    #: 給它一個參數的話，第一件事就是有人把它調高來讓警告消失 —— 而警告要講的
    #: 事情（這張卡把資訊推到範圍外了）不會因此消失。1% 是「不像雜訊、也還沒
    #: 嚴重到毀掉整張圖」的量。
    CLIP_WARN_FRAC = 0.01

    @classmethod
    def resolve_features(cls, params: Dict[str, object]) -> List[str]:
        """這張卡吐的診斷特徵（F11 Enhance-1）。

        **一條流時逐字是 `clip_frac`**、多條流時加流名前綴 —— 跟量測卡同一條
        規則（F10-3），所以使用者只要學一次。
        """
        keys = cls.stream_list(params)
        base = list(cls.features_out) + [CLIP_FRAC]
        if len(keys) > 1:
            return [n for k in keys for n in prefix_names(k, base)]
        return base

    def run(self, ctx: Context, params: Dict[str, object]) -> Context:
        p = self.validate_params(params)
        keys = self.stream_list(p)
        op = self.build_op(ctx, p)
        multi = len(keys) > 1
        for key in keys:
            if self.skip_stream(key, p):
                continue
            img = require_image(ctx, self.key, key)
            self.note_stream(ctx, key, img, p)
            out, frac = clip_to_range(op(img))
            ctx.set_image(key, out)
            ctx.add_features(prefix_features(key if multi else "",
                                             {CLIP_FRAC: frac}))
            if frac > self.CLIP_WARN_FRAC:
                ctx.warn(
                    "[%s] %.1f%% of '%s' was pushed outside 0-255 and had to be "
                    "clipped back. Those pixels all became 0 or 255, so whatever "
                    "was in them is gone - try a gentler setting."
                    % (self.key, 100.0 * frac, key))
        return ctx


#: 「這張卡把多少比例的像素壓回值域」的特徵名（F11 Enhance-1）。
CLIP_FRAC = "clip_frac"


def clip_to_range(img: np.ndarray, lo: float = 0.0, hi: float = 255.0):
    """把影像壓回 ``[lo, hi]``，並回報**壓了多少比例**。

    為什麼值域要是一個契約（實測出來的問題）
    ----------------------------------------
    Enhance 段四張卡的輸出實測值域::

        Normalize (percentile) → uint8    0.00 … 255.00   ✓
        Adjust tone            → uint8   40.00 … 255.00   ✓
        Denoise                → uint8    0.00 … 255.00   ✓
        Remove bg (background) → float32 116.36 … 250.09
        Remove bg (stripes_h)  → float32 125.50 … 261.50  ← 超過 255
        Normalize (local)      → float32   8.00 … 255.00

    越界的 261.5 會活到**後面某個** ``to_uint8`` 才被 clip —— 也就是資訊在使用者
    看不見的地方飽和。而 ``keep_level`` 的說明還寫著「讓影像留在原本的灰階區間，
    下游的門檻才還是同一個意思」：那句話在這個修正之前是假的。

    **不做 rescale，只做 clip**：rescale 會改動每一個像素的值，那就違背了
    「留在原本的灰階區間」這個承諾（下游的門檻會全部失效）。clip 只動界外的
    那些，而「動了多少」由 :data:`CLIP_FRAC` 講出來。

    dtype 刻意**不強制統一**：三張卡回 uint8、兩個方法回 float32，而值域一致
    之後那個差別對量測沒有影響（float 少一次量化，鏈起來反而更準）。強制統一會
    讓既有 recipe 的數字整批位移，換到的只有「看起來整齊」。
    """
    a = np.asarray(img)
    if a.size == 0:
        return a, 0.0
    out_of_range = np.count_nonzero((a < lo) | (a > hi))
    if not out_of_range:
        return a, 0.0
    clipped = np.clip(a, lo, hi)
    if a.dtype != clipped.dtype:            # np.clip 可能升型（uint8 + float 界限）
        clipped = clipped.astype(a.dtype)
    return clipped, float(out_of_range) / float(a.size)


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
    # 具名 ROI 打錯字要講清楚，不要安靜地量整張圖
    raise StepError(step_key,
                    "region '%s' is not defined; available: %s. Add an ROI "
                    "card upstream, or leave roi empty for the whole image."
                    % (name, ctx.roi_names()))


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


# --------------------------------------------------------------------------- #
# 量測卡：一格輸入接好幾條線（F10-3）
# --------------------------------------------------------------------------- #
class MultiSourceStep(Step):
    """量測卡的基底：``source`` 可以是**好幾條流**，每條各算一份特徵。

    為什麼（使用者定調 2026-08-17）
    ------------------------------
    「餵圖是節點跟節點間在處理的，卡片只負責『餵進來的這些 source 要怎麼處理
    並再把 result 丟出去』，所以理想上可以多連一，也可以一連多。」

    量測卡以前的 ``source`` 是 ``image_key``（單一角色），於是往它拉第二條線的
    意思是「改接別的」—— 舊線被拿掉。想同時量 test 與 diff 就得放兩張卡，而那
    兩張卡的參數還得逐格對齊（量的統計量、ROI、門檻…），對不齊的時候畫面上
    看不出來。

    命名（使用者定調：**自動加流名前綴**）
    ------------------------------------
    兩條以上才加：``diff_glv_max`` / ``test_glv_max``。**只接一條時名字跟以前
    逐字相同** —— 那是「分數表達式不必改寫」與「黃金值不動」的前提，也是這個
    改動敢動既有 recipe 的唯一理由。

    子類實作 :meth:`measure`（吃一張影像、回一組數字），迴圈與命名交給基底 ——
    跟 Enhance 卡的 :class:`MultiStreamStep` 同一套辦法：**每張卡只寫它自己那
    件事**，「接了幾條」不是每張卡各答一次的問題。
    """

    #: 吃影像流的那個參數名（子類要換名字的話覆寫）。
    SOURCE = "source"

    #: 這張卡**沒有影像也量得下去**嗎（``cd_measure`` 是：``roi="blob"`` 時
    #: 矩形已經是像素座標，影像只用來做次像素精修）。設 False 的卡拿到的
    #: ``img`` 可能是 ``None``，自己決定怎麼辦。
    REQUIRE_IMAGE = True

    @classmethod
    def source_list(cls, params: Dict[str, object]) -> List[str]:
        return parse_key_list(params.get(cls.SOURCE, ""))

    @classmethod
    def resolve_reads(cls, params: Dict[str, object]) -> List[str]:
        return cls.source_list(params)

    @classmethod
    def stream_prefix(cls, params: Dict[str, object], key: str) -> str:
        """這一條流的特徵前綴（**只接一條時是空的**）。

        空的那個情況是這個設計的重點：只接一條線時，特徵名跟以前逐字相同，
        所以既有的分數表達式不用改寫、黃金值一個數字都不動。
        """
        return str(key) if len(cls.source_list(params)) > 1 else ""

    @classmethod
    def full_prefix(cls, params: Dict[str, object], key: str) -> str:
        """流名前綴 ＋ 使用者自己填的 ``output_prefix``（兩個都可能是空的）。"""
        parts = [cls.stream_prefix(params, key),
                 str(params.get("output_prefix", "") or "").strip()]
        return "_".join([x for x in parts if x])

    @classmethod
    def feature_names(cls, params: Dict[str, object]) -> List[str]:
        """這張卡**在這組參數下**會產出的特徵基本名（不含任何前綴）。"""
        return list(cls.features_out)

    @classmethod
    def resolve_features(cls, params: Dict[str, object]) -> List[str]:
        keys = cls.source_list(params) or [""]
        base = cls.feature_names(params)
        return [n for k in keys for n in prefix_names(cls.full_prefix(params, k),
                                                      base)]

    def measure(self, ctx: Context, img, params: Dict[str, object]):
        """量一張影像，回 ``{特徵名: 值}``（回 ``None`` = 這條流沒有東西可記）。"""
        raise NotImplementedError

    def run(self, ctx: Context, params: Dict[str, object]) -> Context:
        p = self.validate_params(params)
        for key in self.source_list(p):
            img = (require_image(ctx, self.key, key) if self.REQUIRE_IMAGE
                   else ctx.images.get(key))
            feats = self.measure(ctx, img, p)
            if not feats:
                continue
            ctx.add_features(prefix_features(self.full_prefix(p, key), feats))
        return ctx
