# d4t step-card library — authored 2026-07-28 (M1).
"""步驟卡片共用的小工具（非卡片；不註冊任何 step）。

- ``require_image``  向 Context 要影像，缺流時轉成白話 StepError。
- ``to_uint8``       把任何灰階陣列安全轉成 uint8 0–255（[0,1] 浮點自動 ×255）。
- ``parse_key_list`` 逗號字串 → 影像流 key 清單（去空白、忽略空項）。
- ``ensure_gray``    彩色（3 通道）輸入自動轉灰階。
- ``output_prefix_spec`` / ``prefix_*``  量測卡的輸出名前綴（見下方說明）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..pipeline.context import Context, ContextError
from ..pipeline.step import FeatureSpec, ParamSpec, Step, StepError

# --------------------------------------------------------------------------- #
# 輸出名前綴（F7-11）—— 讓同一張量測卡可以用在好幾個區域上
# --------------------------------------------------------------------------- #
#: 特徵名是**扁平的全域命名空間**，而且是分數表達式的變數名。所以前綴只能用
#: 「可以當變數名」的字：開頭是字母或底線，後面接字母／數字／底線。
#: 打了空白或減號的話，`glv mean` 這種名字在表達式裡是指不到的 —— 擋在這裡，
#: 而不是等使用者寫完表達式才發現（鐵則 4）。
FEATURE_PREFIX_PATTERN = r"^$|^[A-Za-z_][A-Za-z0-9_]*$"

#: 一串特徵名（逗號分隔）—— 影像流的 ``image_keys`` 用的是同一種值格式。
#: 空字串合法（卡片自己用 ``configuration_issues`` 講「還沒填」，那句話比
#: 一個正規表達式的錯誤訊息有用得多）。
FEATURE_LIST_PATTERN = (r"^\s*$|^\s*[A-Za-z_][A-Za-z0-9_]*"
                        r"(\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*\s*$")


def feature_list(value) -> list:
    """把逗號分隔的特徵名切成一串（去空白、去重、保留順序）。"""
    out, seen = [], set()
    for part in str(value or "").split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


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


#: 「這張卡把多少比例的像素壓回值域」的特徵名（F11 Enhance-1）。
CLIP_FRAC = "clip_frac"

#: Enhance 那幾張卡共用的一句話（`Step.FEATURE_HELP`，2026-09-01）。
ENHANCE_FEATURE_HELP = {
    CLIP_FRAC: "share of pixels flattened onto 0 or 255 by this card",
    "pair_level_delta": "how far apart the two streams' backgrounds are, "
                        "in gray levels",
    "pair_spread_ratio": "which stream varies more, and by how much",
}


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

    #: 這一族共用的四個數字（`clip_frac` 與兩個 pair 指標）——
    #: 卡片自己再加自己的（例 `denoise` 的 `removed_over_noise`）。
    FEATURE_HELP = ENHANCE_FEATURE_HELP

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

    def after_stream(self, ctx: Context, key: str, before: np.ndarray,
                     after: np.ndarray, params: Dict[str, object]):
        """處理**之後**，這一條流要多報哪些特徵（回 ``None`` = 不報）。

        跟 :meth:`note_stream` 對稱，差別是它拿得到「處理前」與「處理後」兩張圖
        —— 所以「這張卡動了多少」這類診斷是**免費**的（比對兩張圖，不必把演算法
        再跑一次）。前綴由 :meth:`run` 統一套（多流才加流名，同 F10-3 的規則），
        卡片自己不要處理命名。

        報出來的名字**必須**出現在 :meth:`stream_features` 的宣告裡 ——
        `test_card_invariants` 會擋（宣告 ≠ 真的吐出來的話，分數表達式裡就有一個
        指不到的變數名，而那要等使用者寫完表達式才發現）。
        """
        return None

    #: 超過這個比例的像素被壓回值域就講一句話（F11 Enhance-1）。
    #:
    #: 為什麼是固定值而不是一個參數：這不是一個「效果」旋鈕，是一句診斷。
    #: 給它一個參數的話，第一件事就是有人把它調高來讓警告消失 —— 而警告要講的
    #: 事情（這張卡把資訊推到範圍外了）不會因此消失。1% 是「不像雜訊、也還沒
    #: 嚴重到毀掉整張圖」的量。
    CLIP_WARN_FRAC = 0.01

    @classmethod
    def stream_features(cls, params: Dict[str, object]) -> List[str]:
        """**一條流**會吐出哪些特徵的基本名（不含流名前綴）。

        子類要在某些設定下多報一個數字時覆寫這個，不要覆寫
        :meth:`resolve_features` —— 前綴規則只該寫一次。
        """
        return list(cls.features_out) + [CLIP_FRAC]

    @classmethod
    def resolve_feature_specs(cls, params: Dict[str, object]) -> List[FeatureSpec]:
        """這張卡吐的診斷特徵（F11 Enhance-1），PR-3 起帶身分。

        **一條流時逐字是 `clip_frac`**、多條流時加流名前綴 —— 跟量測卡同一條
        規則（F10-3），所以使用者只要學一次。

        兩條以上再多兩個**不帶前綴**的：那一對流處理完之後還有多像
        （:data:`PAIR_FEATURES`）。它們講的是「這兩條之間」，不是「其中某一條」，
        所以掛在流名下面會是錯的 —— spec 的 ``stream`` 因此刻意留空。
        """
        keys = cls.stream_list(params)
        base = cls.stream_features(params)
        if len(keys) > 1:
            out = [FeatureSpec(name=prefix_names(k, [n])[0], card=cls.key,
                               base=str(n), stream=str(k))
                   for k in keys for n in base]
            return out + [FeatureSpec(name=str(n), card=cls.key, base=str(n))
                          for n in PAIR_FEATURES]
        return [FeatureSpec(name=str(n), card=cls.key, base=str(n))
                for n in base]

    @classmethod
    def resolve_features(cls, params: Dict[str, object]) -> List[str]:
        return [s.name for s in cls.resolve_feature_specs(params)]

    @classmethod
    def diagnostic_features(cls, params: Dict[str, object]) -> List[str]:
        """Enhance 卡吐的每一個數字都是診斷（見 `Step.diagnostic_features`）。

        這幾張卡不量缺陷 —— 它們把圖弄乾淨，然後報告自己做了多少
        （壓回值域多少、磨掉幾個 σ、兩條流還有多像）。`features_out` 目前四張卡
        都是空的；哪天有子類在那裡宣告了真正的量測值，它就**不算**診斷。
        """
        keys = cls.stream_list(params)
        measured = list(cls.features_out)
        if len(keys) > 1:
            measured = [n for k in keys for n in prefix_names(k, measured)]
        return [f for f in cls.resolve_features(params) if f not in measured]

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
            feats = {CLIP_FRAC: frac}
            feats.update(self.after_stream(ctx, key, img, out, p) or {})
            ctx.add_features(prefix_features(key if multi else "", feats))
            if frac > self.CLIP_WARN_FRAC:
                ctx.warn(
                    "[%s] %.1f%% of '%s' was pushed outside 0-255 and had to be "
                    "clipped back. Those pixels all became 0 or 255, so whatever "
                    "was in them is gone - try a gentler setting."
                    % (self.key, 100.0 * frac, key))
        if multi:
            ctx.add_features(pair_similarity(ctx.images.get(keys[0]),
                                             ctx.images.get(keys[1])))
        return ctx


#: 兩條流處理完之後**還有多像**（F11 Enhance-UI-B）。
#:
#: - ``pair_level_delta``：兩條流的背景相差幾個灰階（0 = 一樣亮）。
#: - ``pair_spread_ratio``：誰的起伏比較大，比幾倍（1 = 一樣）。
#:
#: 為什麼需要它們：**可比性是 `subtract` 的前提**，而「不可比」在畫面上長得像
#: 「兩張圖本來就不一樣」—— 一張比較亮的 ref 減出來的 diff 整片偏移，而那看起來
#: 就像一個大面積的缺陷。面板已經並排畫兩條流的直方圖，但沒有一個數字說它們有多
#: 像，於是判斷全靠目視兩張分布的形狀。
#:
#: **不帶流名前綴**：它們講的是「這兩條之間」，掛在其中一條的名字下面會是錯的。
PAIR_FEATURES = ("pair_level_delta", "pair_spread_ratio")

#: 算 pair 統計時最多看幾個像素（超過就等間隔取樣）。
#:
#: 為什麼要取樣：這是一個**診斷**，而它要對 2000×2000 的 RSEM 影像也便宜到可以
#: 每顆都算。中位數是 O(n log n)，一對影像四次中位數在大圖上就是幾十毫秒 ——
#: 乘上一萬顆是真的錢。等間隔取樣對「整體亮多少、起伏多大」幾乎沒有影響
#: （而且是決定性的，同一張圖永遠取到同一批像素）。
PAIR_SAMPLE_MAX = 65536


def pair_similarity(a, b) -> Dict[str, float]:
    """兩條流處理完之後還有多像（見 :data:`PAIR_FEATURES`）。

    用中位數與 MAD（`algo.enhance.robust_level_spread`）而不是平均與標準差 ——
    理由跟 ``normalize`` 的 ``zscore`` 一樣：要量的東西就是缺陷本身，而缺陷會把
    平均與標準差帶著跑，於是「這兩張有多像」會隨缺陷大小浮動。

    兩張圖**尺寸不必一樣**（patch 對 RSEM 就是不一樣）：量的是各自的整體統計，
    不是逐像素比對。
    """
    from ..algo.enhance import robust_level_spread     # 迴避 import 迴圈

    def sampled(arr):
        f = np.asarray(arr).reshape(-1)
        if f.size > PAIR_SAMPLE_MAX:
            f = f[::int(np.ceil(f.size / float(PAIR_SAMPLE_MAX)))]
        return f

    if a is None or b is None or np.asarray(a).size == 0 or np.asarray(b).size == 0:
        return {}
    la, sa = robust_level_spread(sampled(a))
    lb, sb = robust_level_spread(sampled(b))
    lo, hi = sorted((abs(sa), abs(sb)))
    # 兩邊都平的話「差幾倍」沒有意義，回 1（一樣）而不是 inf —— inf 會一路活到
    # 某個分數表達式才變成 nan。
    ratio = (hi / lo) if lo > 1e-6 else 1.0
    return {PAIR_FEATURES[0]: abs(float(la - lb)),
            PAIR_FEATURES[1]: float(ratio)}


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


#: **一格 nm/px 長在把那份資料讀進來的那張卡上**（2026-08-20，使用者要求）。
#:
#: 使用者：「在 load image 那邊 source（各種 source），可以輸入 nm/pixel
#: （也可以不輸入）」。它跟 `tiff_stack` 的「一顆幾張」是同一類東西 ——
#: **資料的屬性**，只有把那份資料讀進來的那張卡問得出來。第二份 lot 因此也有
#: 一格（長在 `pair_source` 上），規則才是一句話而不是兩句。
#:
#: 2026-07-30 曾經拿掉 `cd_x_nm` 那一組，理由是「nm/px 沒有來源，所以每一顆都
#: 是 0，而 0 是個看起來很像答案的答案」。這一格正是那個來源 —— 所以那次的
#: 結論沒有被推翻，是被**補完**了。
NM_PER_PX_UNSET = 0.0


def nm_per_px_spec() -> ParamSpec:
    """讀資料那幾張卡共用的 ``nm_per_px``（見 :data:`NM_PER_PX_UNSET`）。"""
    return ParamSpec(
        name="nm_per_px", type="float", default=NM_PER_PX_UNSET,
        min=0.0, max=1e6, unit="nm/px",
        label="Pixel size",
        advanced=True,
        help=("How many nanometres one pixel is, from the tool's settings. "
              "Fill it in and every length this pipeline measures also comes "
              "out in nanometres (cd_median gets a cd_median_nm beside it). "
              "Leave it "
              "at 0 if you do not know it - everything stays in pixels, which "
              "is what it has always been."),
    )


# --------------------------------------------------------------------------- #
# KLARF 的欄位帶成 feature（F16）
# --------------------------------------------------------------------------- #
#: 讀資料那幾張卡共用的 ``carry``。
#:
#: 使用者 2026-08-20 對 ADC 的定調是「利用 feature 內數值資料**跟原始 klarf 帶的
#: 資訊**去做分類」，而在此之前 main 那一份的 KLARF 欄位**進不了 pipeline**
#: （`DefectItem.fields` 只有掛上來的第二份會填）。
#:
#: 做法跟 F15 的 `pair_source.carry` 逐字同一套 —— 那不是巧合，是同一件事：
#: **一份 KLARF 有幾十欄，而其中絕大多數沒有人要**。全帶的話幾十萬顆 × 24 欄
#: 字串是幾百 MB，而且要 pickle 進每一個 worker。所以規則是「點名的才帶」，
#: 兩邊一樣，使用者只要學一次。
#:
#: 型別是 ``multi_choice`` 而不是 ``choice``：`choice` 會擋掉不在清單裡的值，
#: 而 recipe 是在資料載進來**之前**讀的 —— 每一份存了欄名的 recipe 都會在開檔
#: 那一刻爆掉（F15-2 踩過，見 `ParamSpec.choices_from`）。
CARRY_HELP = (
    "KLARF columns to bring into the pipeline as numbers you can use later "
    "(ROUGHBINNUMBER, CLASSNUMBER, …). Each one arrives under its own name, "
    "so the score expression and the report can both refer to it. Columns "
    "that are not numbers are kept for the report but are not usable in the "
    "score. Tick nothing and nothing is carried - which is what every recipe "
    "did before this box existed.")


def carry_spec() -> ParamSpec:
    """讀資料那幾張卡共用的 ``carry``（見 :data:`CARRY_HELP`）。"""
    return ParamSpec(
        name="carry", type="multi_choice", default="",
        label="Carry these columns",
        choices_from="main_columns",
        advanced=True,
        help=CARRY_HELP,
    )


#: 兩張載入卡共用的「只跑這幾個 code」（F50，2026-08-28，使用者：「直接在
#: Input 內加入 input code 的功能（可選，選擇 KLARF 內哪個 column code 的
#: image 才要跑運算）」）。
#:
#: **兩張卡同一組參數名**，理由同 `drop_edge_specs`：使用者心裡這是一件事，
#: 而它在 recipe 裡長什麼樣會被讀、被 diff、被抄。
#:
#: 為什麼是**兩格**而不是一格 ``COLUMN=1,2``：欄名要能從 KLARF 現有的欄
#: 長成一個下拉（`choices_from="main_columns"`），而一格自由文字就得自己
#: 打對欄名 —— 打錯只會安靜地一顆都不符合。
ONLY_CODE_HELP_COL = (
    "Optional. Only run the defects whose value in this KLARF column is in "
    "the list below - everything else is left out of the run entirely. "
    "Leave empty to run every defect."
)
ONLY_CODE_HELP_VAL = (
    "Which values to keep, comma separated (for example '2, 5'). Matching "
    "ignores case and surrounding spaces. Defects that are left out are not "
    "processed at all, and their KLARF rows are never rewritten."
)


def only_code_specs() -> List[ParamSpec]:
    """``only_column`` ＋ ``only_codes`` —— 讀資料那幾張卡共用。

    **兩格都空 = 不篩**（嚴格附加，同 `route_by`）：既有的每一份 recipe
    一個位元都沒變。
    """
    return [
        ParamSpec(
            name="only_column", type="str", default="",
            label="Only run this column",
            choices_from="main_columns",
            advanced=True,
            help=ONLY_CODE_HELP_COL,
        ),
        # ⚠ **沒有 `show_when`，兩格永遠都在。** 想寫的是「填了欄名才顯示
        # 值那一格」，而 `show_when` 比對的是**一組允許的值**，沒有「非空」
        # 這個述詞 —— 欄名是執行期才知道的（`choices_from`），列舉不出來。
        # 兩格一起出現也比較誠實：它們讀起來就是一句話的兩半，而兩格都是
        # `advanced`，本來就收在進階區。
        ParamSpec(
            name="only_codes", type="str", default="",
            label="…with these values",
            advanced=True,
            help=ONLY_CODE_HELP_VAL,
        ),
    ]


def parse_only_codes(params: Dict[str, Any]
                     ) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """`Step.item_filter` 的共用實作：把那兩格讀成 ``(欄名, (值, …))``。

    **任一格空的就回 None**（＝不篩）。只填欄名沒填值的話，字面上的意思是
    「這一欄的值要在一個空清單裡」＝一顆都不跑 —— 那絕對不是使用者的意思，
    而一份跑出零顆的 recipe 看起來就像壞掉。那個狀態由 lint 講話
    （`only-code-no-values`），引擎這邊當成沒填。
    """
    col = str(params.get("only_column", "") or "").strip()
    raw = str(params.get("only_codes", "") or "").strip()
    if not col or not raw:
        return None
    vals = tuple(t.strip() for t in raw.split(",") if t.strip())
    return (col, vals) if vals else None


def only_code_hints(params: Dict[str, Any]) -> List[str]:
    """那兩格填了一半的時候講一句（`Step.configuration_hints` 用）。

    **warning 不是 error**：這張卡照樣跑得完，只是那個篩選沒有作用 ——
    正是 `configuration_hints` 的契約（「跑得起來，但你八成不是這個意思」）。

    只講**填了欄名沒填值**那一邊。反過來（填了值沒填欄名）也是沒作用，而那
    句話比較沒用：使用者八成是打算填欄名的下一步，而下拉就在旁邊。
    """
    col = str(params.get("only_column", "") or "").strip()
    raw = str(params.get("only_codes", "") or "").strip()
    if col and not raw:
        return ["“Only run this column” is set to %r but no values are "
                "listed, so nothing is filtered and every defect runs. "
                "Add the values you want to keep (for example '2, 5'), or "
                "clear the column." % col]
    return []


#: 兩張 Region 卡共用的「靠邊的框不要」開關（F11 Region 第八輪，使用者要求）。
#:
#: 為什麼兩張卡要**同一組參數名**：使用者心裡這是**一件事**（「靠邊的不要」），
#: 而它在 recipe 裡長什麼樣會被讀、被 diff、被抄。兩張卡各發明一個名字的話，
#: 換一種定位法就要重學一次同一個概念。
EDGE_SECTION_TEMPLATE = "5 · Name and limits"


def drop_edge_specs(section: str) -> List[ParamSpec]:
    """``drop_edge``（勾選）＋ ``edge_margin``（幾個 px）。

    為什麼是兩格而不是「``edge_margin = 0`` 代表關掉」：使用者要的是一顆
    **看得到的勾選框**（原話「幫我 gen 一個 checkbox（可勾選要不要使用的）」）。
    用 0 當哨兵的話，「這張 recipe 有沒有在做這件事」要靠看一個數字是不是 0
    來推 —— 而那個推論在畫面上不存在。
    """
    return [
        ParamSpec(
            name="drop_edge", type="bool", default=False, section=section,
            label="Ignore boxes near the edge of the image",
            help=("Leave out any box that comes closer to the edge of the "
                  "image than the distance below. A box at the edge is only "
                  "partly on the image, or sits on a stripe that is itself "
                  "half cut off - the gray level it reports is measured over "
                  "fewer pixels and over the wrong ones, and it still looks "
                  "like a perfectly normal number. A box picked as the "
                  "defect's is always kept (see below)."),
        ),
        ParamSpec(
            name="edge_margin", type="float", default=4.0, min=0.0, max=64.0,
            unit="px", section=section, label="Closer to the edge than",
            show_when=("drop_edge", (True,)),
            help=("How close to the edge of the image is too close, in "
                  "pixels. A box is dropped when any part of it falls inside "
                  "this band. When a box was picked as the defect's "
                  "(<name>_center), that one is never dropped - it is not "
                  "one of the samples, it is the thing being measured, and "
                  "dropping it would quietly point <name>_center at a box "
                  "the defect is not in."),
        ),
    ]


#: 「這一組框裡，哪一塊是缺陷那一塊」—— 剩兩個值（F32，2026-08-25）。
#:
#: ``centre``＝離 patch 正中心最近的那一塊（patch 以 KLARF 座標為中心裁，
#: 缺陷就在正中心）；``none``＝不挑（F31 T4）—— RSEM 大圖上缺陷不在中央，
#: ``_center`` / ``_others`` 是雜訊，挑選交給下游量測卡（GLV 的逐框比較）。
#:
#: **``strongest``（訊號最強的那一塊）於 F32 刪掉了**（使用者：「跟後面量測卡
#: 功能稍微衝突了，我傾向留 centre & none」，在看過收起來的零成本選項後仍
#: 定調直接刪）。代價要看得見：它當初是量出來的 —— F20 在
#: ``0822test/mgepi_real3`` 上（缺陷離正中心中位數 7.1 px），「離中心最近」
#: 只有 **11/24** 顆真的框到缺陷、下游 AUC 0.688，「訊號最強」是 **24/24**、
#: AUC 0.977（數字以 `docs/history/plans/F20-pick-defect-box.md` 為準 ——
#: 這裡曾抄成 14/24→23/24，校正過）。patch 座標偏移的那條路**從此沒有這個
#: 救援**，只剩「離中心最近」；要回來得整支重做（訊號分支、``pick_source``
#: 那條線、``pick_by_signal`` 特徵都一起走了）。
#: 舊 recipe 填過 ``strongest`` 的**明確報錯**（choice 驗證擋），不安靜換成
#: centre —— 換規則等於安靜換一組數字。
PICK_NONE = "none"
PICK_RULES = ("centre", PICK_NONE)


def pick_rule_of(params) -> str:
    """這組參數的挑框規則（不認得的字、沒填的一律當 ``centre``）。

    **不要在別處直接讀 ``params["pick"]`` 來分支**（同 `glv_stats._reference_of`
    的理由）。``none`` 在呼叫端短路 —— :func:`pick_defect_box` 只認得
    「離中心最近」，沒有「不挑」這個概念。
    """
    got = str(params.get("pick", "centre") or "centre").strip()
    return got if got in PICK_RULES else "centre"

def pick_rule_specs(section: str) -> List[ParamSpec]:
    """兩張找 ROI 的卡共用的那兩格（規則 ＋ 在哪一條流上判斷）。

    共用一份的理由跟 ``output_prefix_spec`` 一樣：**同一句話在兩張卡上要
    一字不差**。使用者學一次，而兩張卡的行為不會各自漂走。
    """
    return [
        ParamSpec(
            name="pick", type="chip_choice", default="centre",
            choices=list(PICK_RULES), section=section,
            icons=["pick_centre", "pick_none"],
            label="Which box is the defect in",
            choice_help={
                "centre": "The one nearest the middle of the image. Patches "
                          "are cut around the defect, so the middle one is "
                          "usually it.",
                PICK_NONE: "Do not pick one. On a full-size image the defect "
                           "is not in one particular box, so <name>_center "
                           "and <name>_others are not made - only the plain "
                           "set of boxes, and a measure card (GLV, box by "
                           "box) finds the odd one out.",
            },
            help=("How to tell which of these boxes the defect is in. Pick "
                  "centre and that box becomes <name>_center with every "
                  "other one as the baseline <name>_others; pick none and "
                  "only the plain name is made."),
        ),
    ]


def pick_defect_box(boxes, patch_shape) -> int:
    """哪一塊是缺陷那一塊 → 索引（離 patch 正中心最近的那一塊）。

    ``boxes`` 是像素矩形 ``(x, y, w, h)``。只剩這一種規則：patch 以 KLARF
    座標為中心裁，缺陷就在正中心。訊號挑框（``strongest``）於 F32 刪掉 ——
    來龍去脈與代價見 :data:`PICK_RULES` 上面那一段。
    ``pick="none"`` 的呼叫端**不要叫這一支**（沒有「缺陷那一塊」可言）。
    """
    if not boxes:
        return 0
    h, w = float(patch_shape[0]), float(patch_shape[1])
    cx, cy = w / 2.0, h / 2.0
    return min(range(len(boxes)),
               key=lambda k: ((boxes[k][0] + boxes[k][2] / 2.0 - cx) ** 2
                              + (boxes[k][1] + boxes[k][3] / 2.0 - cy) ** 2))


def drop_edge_boxes(boxes, patch_shape, margin: float, keep: int = -1):
    """丟掉靠邊的框。回傳 ``(留下的框, 丟掉幾個, keep 在新清單的位置)``。

    ``boxes`` 是像素矩形 ``(x, y, w, h)``；``keep`` 是**永遠不丟**的那一個的
    索引（缺陷所在的那一塊）。

    為什麼 ``keep`` 一定要豁免
    --------------------------
    ``<name>_center`` 的定義是「缺陷所在的那一塊」（patch 以缺陷為中心裁切，
    所以就是離正中心最近的那一塊）。它不是母體裡的一個樣本，它是**被量的那個
    東西**。把它丟掉的話 ``_center`` 會安靜地指到另一塊 —— 那一塊裡沒有缺陷，
    而下游每一個數字都會照樣算得出來。丟掉靠邊的框要修的是**基準**
    （``<name>_others``）被半截的框汙染，不是把待測物也一起丟掉。

    ⚠ **橫跨整張圖的那一軸不算「靠邊」。**（實測出來的，不是想出來的）
    Profile 單方向時每一個框都是滿版的（``directions="upright"`` 的框 y=0、
    h=整張高），照「碰到邊界就算」的話**每一個框都會被丟掉**，只剩豁免的中心
    那一塊 —— 6 個框變 1 個，而畫面上不會有任何錯誤訊息。滿版不是「放在邊上」，
    它是「這一軸整個都要」。所以某一軸上框跟影像一樣長的時候，那一軸不判定。
    """
    h, w = float(patch_shape[0]), float(patch_shape[1])
    m = max(0.0, float(margin))
    kept, dropped, new_keep = [], 0, -1
    for i, b in enumerate(boxes):
        x, y, bw, bh = (float(v) for v in b)
        near = ((bw < w and (x < m or x + bw > w - m))
                or (bh < h and (y < m or y + bh > h - m)))
        if near and i != int(keep):
            dropped += 1
            continue
        if i == int(keep):
            new_keep = len(kept)
        kept.append(b)
    return kept, dropped, new_keep


def prefix_names(prefix: str, names: List[str]) -> List[str]:
    """把前綴套到一串特徵名上（前綴為空 = 原樣回傳）。"""
    p = str(prefix or "").strip()
    return [f"{p}_{n}" for n in names] if p else list(names)


def prefix_features(prefix: str, feats: Dict[str, float]) -> Dict[str, float]:
    """把前綴套到一組特徵值上（前綴為空 = 原樣回傳）。"""
    p = str(prefix or "").strip()
    return {f"{p}_{k}": v for k, v in feats.items()} if p else dict(feats)


#: 名字結尾是 ``_px`` 但**意思是面積**的那幾個 —— 換算要平方（nm²）。
#:
#: 為什麼要列出來而不是看名字：``area_px`` 的結尾跟任何一個長度特徵一模一樣，
#: 而它們差一個次方。照結尾一律乘一次的話，面積會安靜地少乘一次 ——
#: 跑得完、有數字、而且是錯的。改名成 ``area_px2`` 也能解，但那會動到既有的
#: recipe 與黃金值，代價比一行表大得多。
#: （``blob_area_px`` 曾在這裡 —— `find_defect` 於 F31 T5 刪除後拿掉。
#:  加一張會吐面積的新卡要記得加回一行，這張表就是為那一刻留的。）
AREA_FEATURES = ("area_px", "cd_area_px")

#: 名字**不是** ``_px`` 結尾、但意思就是一段長度的那幾個（F19）。
#:
#: 跟 :data:`AREA_FEATURES` 是同一張表的另一半，理由也一樣 —— **看名字猜不到**。
#: CD 那張卡吐的是 ``cd_median`` / ``ler_a_std`` 這種名字（``cd_median_px``
#: 在膠囊上又長又醜），而它們每一個都該配一份 nm 的。漏掉的下場不是報錯，是
#: 使用者填了 nm/px 之後**只有一半的長度換得出單位**。
#:
#: 不在這裡、也不以 ``_px`` 結尾的一律不配 —— ``cd_dev_frac``（比例）、
#: ``cd_n``（條數）、``cd_axis_deg``（角度）都不該有 nm 版本。
LENGTH_FEATURES = ("cd_median", "cd_mean", "cd_min", "cd_max", "cd_range",
                   "cd_std", "ler_a_std", "ler_b_std", "cd_dev",
                   # 團那一支（F19 第二批）。``cd_area_px`` **不在這裡** ——
                   # 它結尾是 `_px` 但意思是面積，所以它住 :data:`AREA_FEATURES`
                   # 而且那一張表先比對。少了那一行的話它會被配成 `cd_area_nm`
                   # （少乘一次），而那正是 AREA_FEATURES 上面那段在講的事。
                   "cd_deq", "cd_feret_max", "cd_feret_min")
                   # （``blob_deq`` 曾在這裡 —— `find_defect` 於 F31 T5 刪除
                   #  後拿掉。GLV 逐框比較的 ``glv_worst_x/y/w/h`` 刻意不配 nm：
                   #  它們是「畫在哪」不是「多大」，同 ``cd_box_*`` 的理由；
                   #  ``glv_worst_score`` 是 σ，本來就沒有單位。）


def nm_twins(feats: Dict[str, float],
             nm_per_px: Optional[float]) -> Dict[str, float]:
    """量出來的 pixel 數字**多配一份 nm 的**（2026-08-20）。回沒有前綴的那一份。

    規則只有兩條：``*_px`` → ``*_nm``（×s）、:data:`AREA_FEATURES` → ``*_nm2``
    （×s²）。``nm_per_px`` 沒填（None／0）就一個都不配。

    **為什麼是「多一組」而不是「換單位」**（使用者原本的提案是後者）：
    同一個特徵名在不同資料上是不同單位的話，`score = cd_x > 50` 這一行會在
    填了 nm/px 之後意思整個改變 —— recipe 沒改、資料沒改、bin 卻不一樣，
    而 CSV 上看不出來。名字帶著單位就永遠不必回頭查「那份資料當初填了沒」，
    舊 recipe 也一個字都不用改。
    """
    try:
        scale = float(nm_per_px or 0.0)
    except (TypeError, ValueError):
        return {}
    if scale <= 0:
        return {}
    out: Dict[str, float] = {}
    for name, value in (feats or {}).items():
        if value is None:
            continue
        if name in AREA_FEATURES:
            out[name[:-3] + "_nm2"] = float(value) * scale * scale
        elif name in LENGTH_FEATURES:
            out[name + "_nm"] = float(value) * scale
        elif name.endswith("_px"):
            out[name[:-3] + "_nm"] = float(value) * scale
    return out


def nm_twin_specs(names: Sequence[str]) -> List[Tuple[str, str]]:
    """:func:`nm_twins` 會配出哪幾個名字 → ``[(孿生名, variant), …]``。

    variant 是 ``"nm"`` 或 ``"nm2"``（`FeatureSpec.variant` 的值）——
    宣告與變體標記在同一張表上出生（PR-3），`nm_twin_names` 是它的投影。
    """
    out: List[Tuple[str, str]] = []
    for name in names or ():
        if name in AREA_FEATURES:
            out.append((name[:-3] + "_nm2", "nm2"))
        elif name in LENGTH_FEATURES:
            out.append((str(name) + "_nm", "nm"))
        elif str(name).endswith("_px"):
            out.append((name[:-3] + "_nm", "nm"))
    return out


def nm_twin_names(names: Sequence[str]) -> List[str]:
    """:func:`nm_twins` 會配出哪幾個名字（宣告用；跟值無關）。"""
    return [n for n, _v in nm_twin_specs(names)]


def resize_to(img: np.ndarray, shape) -> np.ndarray:
    """把影像縮放到 ``(高, 寬)``。**只給比對用的那一份**（2026-08-20）。

    縮小用 ``INTER_AREA``、放大用 ``INTER_LINEAR`` —— 兩者都是 OpenCV 對那個
    方向的建議做法（縮小時 AREA 是唯一不會 aliasing 的）。

    ⚠ **量測用的影像不要經過這裡**：重採樣會動到灰階，而下游量的正是灰階
    （`align_to` 只縮放拿去做 NCC 的那一份，裁出來的那一塊原封不動）。
    """
    import cv2

    h, w = int(shape[0]), int(shape[1])
    src = np.asarray(img)
    if src.shape[0] == h and src.shape[1] == w:
        return src
    shrinking = h * w < src.shape[0] * src.shape[1]
    return cv2.resize(src, (w, h),
                      interpolation=cv2.INTER_AREA if shrinking
                      else cv2.INTER_LINEAR)


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
            # ⚠ 分兩種情況講（F31 T4）。以前這句無條件寫著「which is where
            # the defect is」—— 那個假設只在 patch 上成立（以缺陷為中心裁切），
            # 在 RSEM 大圖上是錯的，而錯的解釋會把人推去用一個無意義的名字。
            raise StepError(
                step_key,
                "region '%s' is %d separate boxes, and this card needs a "
                "single one. On a patch cut round a defect, '%s_center' is "
                "the box the defect is in. On a full-size image the defect "
                "is not in the middle - use a card that compares all the "
                "boxes instead (GLV, with “Boxes in the region” set to "
                "each box)."
                % (name, ctx.roi_count(name), name))
        # 具名 ROI 存的是正規化座標，一樣需要尺寸才展得開
        return None if shape is None else ctx.roi_rect(name, shape)
    # 具名 ROI 打錯字要講清楚，不要安靜地量整張圖
    #
    # 但「打錯字」不是唯一的原因：模板定位的區域可能**這一顆剛好沒落上**
    # （模板比 patch 大，這張 patch 只看得到 cell 的一部分）。那時候叫使用者
    # 「加一張 ROI 卡」是把他送去修一個沒有壞的東西 —— 定位卡把真正的原因寫在
    # ``meta["regions_absent"]``，這裡照它說的講。
    absent = (ctx.meta.get("regions_absent") or {}) if hasattr(ctx, "meta") else {}
    if name in absent:
        raise StepError(step_key,
                        "region '%s' is not on this defect: %s. Regions that "
                        "only appear on some defects cannot be measured on all "
                        "of them - use the region's '_present' feature to tell "
                        "those defects apart."
                        % (name, absent[name]))
    raise StepError(step_key,
                    "region '%s' is not defined; available: %s. Add an ROI "
                    "card upstream, or leave roi empty for the whole image."
                    % (name, ctx.roi_names()))


def set_region_family(ctx, step_key: str, name: str, norm_boxes,
                      centre_index: int = 0, edge_dropped: int = 0,
                      pick: bool = True) -> int:
    """一組框 → **三個**具名區域：全部、缺陷那一塊、其餘那些（F11 Region-1）。

    ``pick=False``（``pick="none"``，F31 T4）只放主名字：不寫 ``_center`` /
    ``_others``、也不記 ``regions_absent``（那兩個名字**沒有被宣告**，不是
    「該在而不在」）。宣告端的開關在 :func:`region_family` —— 兩支要一起看。

    為什麼是三個
    ------------
    ADC 常問的是「缺陷那一塊比旁邊同材質的暗多少」。以前只有兩個名字：

    * ``<name>``        —— 全部接起來的像素母體
    * ``<name>_center`` —— **缺陷所在的那一塊**（`pick_defect_box`：離 patch
      正中心最近，因為 patch 是以缺陷為中心裁的）

    少的正是**基準**。拿 ``<name>`` 當基準是有偏的：N 塊的時候缺陷佔 1/N 的
    像素，N=4、缺陷偏 50 GLV 的話基準本身就被拉走 12.5 GLV —— 跟要量的量同一個
    數量級。所以多一個 ``<name>_others``（除了中心那塊以外的每一塊）。

    ⚠ **卡片不指派 target / reference。** 角色是「這一次比較」的屬性不是區域的
    屬性 —— 同一塊 EPI 在一個比較裡是 target、在另一個裡是 reference（使用者
    2026-08-18：「會有很多種組合，要 by 情況討論」）。角色寫進區域的話，每一種
    比較都要複製一份區域，而區域是**畫**出來的。所以 Region 段只出名詞，
    「拿哪兩個比」由下游那張卡的兩個下拉決定（F11 §3.3.6）。

    只有一塊的時候 ``<name>_others`` **不存在**（不是空的、也不是退回整張圖）：
    這張 patch 上就是沒有基準。記進 ``meta["regions_absent"]``，量測卡才報得出
    真正的原因。回傳「其餘」有幾塊。

    ``edge_dropped`` 是「靠邊」那個開關丟掉幾塊（:func:`drop_edge_boxes`）。
    它只影響**那句話**：基準不見的原因是「這張 patch 上只有一份」還是「其餘
    幾份都被你設定的邊界距離濾掉了」，處置完全不同（前者換張圖、後者改一個
    數字），而預設那句話會把後者說成前者。
    """
    boxes = [tuple(float(v) for v in b) for b in norm_boxes]
    if not boxes:
        return 0
    if not pick:
        ctx.set_roi_boxes(name, boxes)
        return 0
    i = max(0, min(int(centre_index), len(boxes) - 1))
    ctx.set_roi_boxes(name, boxes)
    ctx.set_roi(centre_name(name), boxes[i])

    others = [b for k, b in enumerate(boxes) if k != i]
    rest = others_name(name)
    if others:
        ctx.set_roi_boxes(rest, others)
    else:
        ctx.meta.setdefault("regions_absent", {})[rest] = (
            ("every other copy of '%s' on this patch was left out for being "
             "near the edge of the image (%d of them); lower “Closer to the "
             "edge than”, or turn that setting off" % (name, edge_dropped))
            if edge_dropped else
            ("this patch only has one copy of '%s', so there is no other copy "
             "to use as a baseline" % name))
    return len(others)


#: 一個區域名 → 它那一家的另外兩個名字（F11 Region-1；常數是 F37 收的）。
#:
#: 以前這兩個後綴被**拼在四個地方**：`set_region_family` 建區域時兩次、
#: `region_family` 宣告時一次、`glv_stats` 推導「其餘那些」時一次。四份字面值
#: 講同一件事，而改動其中一份不會讓任何測試變紅 —— 那正是 `CLAUDE.md` §0
#: 「一個主題一個家」擋的形狀。
CENTRE_SUFFIX = "_center"
OTHERS_SUFFIX = "_others"


def centre_name(name: str) -> str:
    """``epi`` → ``epi_center``（缺陷所在的那一塊）。"""
    return "%s%s" % (name, CENTRE_SUFFIX)


def others_name(name: str) -> str:
    """``epi`` → ``epi_others``（同一家的其餘那些，也就是基準）。"""
    return "%s%s" % (name, OTHERS_SUFFIX)


def region_role_of(name: str) -> str:
    """區域名 → 角色（PR-3）：``"all" | "center" | "others"``。

    後綴的**唯一產地**是 :func:`region_family`，所以翻譯也住在這裡 ——
    `ui/region_words.role_of` 從 PR-3 起委派這一支（那邊只剩顯示的字）。
    認不得的後綴一律當「全部的框」。
    """
    n = str(name or "")
    if n.endswith(CENTRE_SUFFIX):
        return "center"
    if n.endswith(OTHERS_SUFFIX):
        return "others"
    return "all"


#: **每一張「找 ROI」的卡，對它吐的每一個區域，都寫這五個數字**（F11 Region-4）。
#:
#: 使用者 2026-08-18：「我認為各種找／給定 ROI 的方法，理想上輸出的東西要接近
#: ⋯⋯現在不是不能用，而是現在有點像大家資料結構不一樣。」
#:
#: 在這之前三張卡各寫各的：Profile **一個都沒有**（只有卡自己的 `cross_*`）、
#: Template 三個（`present` / `others_present` / `edge_dropped`）、GDS 四個
#: （`present` / `pieces` / `area_px` / `clipped`）。於是下游（分數表達式、
#: `Gray level` 的 compare、報表）**得先知道這個區域是誰找的**才問得出「它有沒有落
#: 在這一顆上」—— 那正是漏出去的地方。
#:
#: 五個數字對應下游真正會問的五個問題：
#:
#: 1. ``present``      —— 這一顆上有沒有一個**真的定位到的**它（0/1）。
#: 2. ``boxes``        —— 幾個框。
#: 3. ``area_px``      —— 蓋了多少像素。
#: 4. ``clipped``      —— 有沒有被框數上限**安靜地**砍掉（0/1）。
#: 5. ``edge_dropped`` —— 因為靠邊被丟掉幾塊。
#:
#: 後兩個是「有沒有東西被無聲拿掉」，而那是這一類卡最容易騙人的地方：少掉一半
#: 框的區域仍然算得出一個很正常的灰階值。
#:
#: ⚠ ``present`` 與 ``boxes`` **會不一致，而那是它們合起來要講的話**：Profile 與
#: Template 定不出位置時會退回「整張圖」當保險（`locate_ok = 0`）。那時候框在、
#: 但它不是那個區域 —— 於是 ``present = 0`` 而 ``boxes = 1``，正好講出「有東西
#: 可以量，但它不是你要的那個」。一個數字答不了這件事。
REGION_FACTS = ("present", "boxes", "area_px", "clipped", "edge_dropped")

#: 那五個數字**一句話版**（給 UI 的「What it is」那一欄，2026-09-01）。
#:
#: 使用者：「Feature 這邊顯示有點亂……有些解釋在中間。」以前只有 GLV 那一族
#: 答得出那一句（`ui.widgets.feature_gloss` 只認得 ``glv`` / ``cmp``），所以
#: 同一張表上有些列有解釋、有些空白 —— 看起來像壞掉，其實是沒人寫過。
#:
#: **住在這裡而不是 UI**：上面那段長註解才是這五個字的家，抄第二份到 UI 的
#: 那一份一定會漂（`CLAUDE.md` §0）。core 不 import Qt，一句英文字串沒問題。
#: **同一個名字在不同卡上要有同一句話**（使用者 2026-09-01：「記得就算是不同張
#: card 得到的 feature 寫法也要一致（增加可閱讀性）」）。
#:
#: 這張表放的是**好幾張卡都會寫的那些名字**；卡片自己的名字寫在自己的
#: `FEATURE_HELP` 裡。兩張卡各寫一句的下場實際發生過：`locate_ok` 一張說
#: 「located the pattern」、另一張說「located the cell」—— 而它們是同一件事，
#: 而且會**排在同一張表上**（`roi_reference` 是那兩支折進來的門面）。
#:
#: 有一支測試逐一比對每一個 Step 子類，同名不同句就紅
#: （`tests/test_feature_specs.py`）。
SHARED_FEATURE_HELP = {
    "locate_ok": "1 when it locked onto the pattern "
                 "(0 = fell back to the whole image)",
    "locate_conf": "how much of this image is structure rather than noise "
                   "(about 0.7 = flat, 20+ = clear stripes)",
    "edge_dropped": "how many boxes were dropped for touching the edge",
}

REGION_FACT_HELP = {
    "present": "1 when this region was really located on this defect",
    "boxes": "how many boxes it has here",
    "area_px": "how many pixels they cover",
    "clipped": "1 when the box limit silently cut some off",
    "edge_dropped": SHARED_FEATURE_HELP["edge_dropped"],
}


def region_fact_specs(names) -> List[Tuple[str, str, str]]:
    """``["epi", …]`` → ``[(feature 名, 區域名, 哪個 fact), …]``（PR-3）。

    Region 卡的名字文法跟量測卡**相反**：區域名在 base 裡、`output_prefix`
    在最外 —— 所以「這個名字屬於哪個區域」只有組名字的這一行答得出來。
    `region_fact_names` 是它的投影。
    """
    out: List[Tuple[str, str, str]] = []
    for name in names or ():
        n = str(name or "").strip()
        if n:
            out.extend(("%s_%s" % (n, f), n, f) for f in REGION_FACTS)
    return out


def region_spec_maker(card_key: str, own: str, regions):
    """三張 Region 卡共用的 `FeatureSpec` 工廠（2026-09-01）。

    以前這支 closure 在 `roi_cross` / `roi_template` / `roi_reference` 裡各抄
    了一份 —— **而三份裡有同一個 bug**：區域那幾個名字的 ``base`` 是**整串**
    （``region_others_present``），而 ``region`` 又是 ``region_others``，於是
    UI 把區域名印兩次（``region_others_present``ᵣᵉᵍᶦᵒⁿ_ᵒᵗʰᵉʳˢ）。量測卡那邊
    早就是對的（``epi_glv_median`` → base ``glv_median`` ＋ 上標 ``epi``），
    所以同一件事在同一張表上有兩種長相。使用者 2026-09-01：「Feature 這邊顯示
    有點亂，有些有上綴。」

    規則一句話：**帶區域前綴的名字，``base`` 是前綴後面那一段**（也就是
    ``metric``）；不帶的（``cross_count``、``locate_ok``…）整串就是 base。

    ⚠ Region 卡的名字文法跟量測卡**相反**：區域名在裡面、``output_prefix``
    在最外（``gds_epi_center_present``）—— 所以身分只有組名字的這一支答得出來。
    """
    regions = list(regions or [])

    def spec(name, region="", metric="", family="region"):
        region, metric = str(region or ""), str(metric or "")
        return FeatureSpec(
            name=prefix_names(own, [str(name)])[0], card=str(card_key),
            base=(metric if (region and metric) else str(name)),
            region=region,
            region_index=(regions.index(region) if region in regions else -1),
            region_role=(region_role_of(region) if region else ""),
            own=own, metric=metric or str(name), family=family)

    return spec


def region_fact_names(names) -> List[str]:
    """``["epi", "epi_center"]`` → 這些區域會寫出來的 feature 名（供 lint／UI）。"""
    return [n for n, _r, _f in region_fact_specs(names)]


def region_facts(ctx, names, shape, clipped: bool = False,
                 edge_dropped: int = 0,
                 located: Optional[bool] = None) -> Dict[str, float]:
    """算出 :data:`REGION_FACTS`（**照 ctx 裡真的存了什麼算**，不照卡片以為的）。

    前三個從 ``ctx`` 讀回來，因為那才是下游真的會量到的東西 —— 卡片自己記一份
    「我放了幾個框」很容易跟實際存進去的不一致，而那種 bug 極難發現
    （同 `ctx.meta` 那條「UI 畫的就是引擎算的這一份」）。

    ``clipped`` / ``edge_dropped`` 講的是**這一組區域是怎麼建出來的**，所以
    一個家族（``<n>`` / ``<n>_center`` / ``<n>_others``）三個名字拿到同一個值。
    重複是刻意的：下游手上只有**一個**名字（使用者在 `Gray level` 上挑的
    那一個），它必須不必知道那是不是衍生名就問得出全部五件事。

    ``located=False`` 是「框在、但那是退回整張圖的保險，不是這個區域」——
    只有那時候 ``present`` 才會跟 ``boxes`` 對不上（見上面的 ⚠）。
    """
    out: Dict[str, float] = {}
    known = ctx.roi_names()
    for name in names or ():
        n = str(name or "").strip()
        if not n:
            continue
        count = int(ctx.roi_count(n)) if n in known else 0
        area = 0.0
        if count:
            area = float(sum(int(w) * int(h)
                             for _x, _y, w, h in ctx.roi_rects(n, shape)))
        ok = bool(count) if located is None else (bool(count) and located)
        out["%s_present" % n] = 1.0 if ok else 0.0
        out["%s_boxes" % n] = float(count)
        out["%s_area_px" % n] = area
        out["%s_clipped" % n] = 1.0 if clipped else 0.0
        out["%s_edge_dropped" % n] = float(edge_dropped)
    return out


def region_family(name: str, pick: bool = True):
    """一個區域名 → 它實際定義的名字（宣告用；空名字回空）。

    ``pick=True``（``centre``）是三個：全部、缺陷那一塊、其餘那些。
    ``pick=False``（``pick="none"``，F31 T4）只有主名字 —— 大圖上沒有
    「缺陷那一塊」可言，``_center`` / ``_others`` 是雜訊。三張 Region 卡的
    宣告都經過這一支，開關只在這裡。
    """
    n = str(name or "").strip()
    if not n:
        return []
    return [n, centre_name(n), others_name(n)] if pick else [n]


def crop_to_roi(ctx, step_key: str, image, roi_name):
    """依 ``roi`` 參數裁出要量測的像素（找不到那個區域時退回整張圖）。"""
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


#: ``max_boxes`` 的上限 —— **三支共用一個數字**（F30）。
#:
#: 為什麼要共用：四張 Region 卡收成一張之後，使用者調的是合併卡上那一格，
#: 而實作那一邊會再 `validate_params` 一次。兩邊的上限不同的話，畫面上填得
#: 進去的值會在引擎裡被打回來 —— 實測 ``roi_cross`` 的舊上限是 4096、合併卡
#: 是 65536，於是預設值 8192 讓 Profile 那一支**每一顆都失敗**，而症狀是一句
#: 「parameter 'max_boxes': 8192 is above the maximum of 4096」，指著一個
#: 使用者從來沒有打過的數字。
LIMIT_MAX_BOXES = 65536


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

    #: 吃**具名區域**的那個參數名（``""`` = 這張卡不吃區域）。
    #:
    #: 跟 ``SOURCE`` 同一套辦法（F13-⑥，2026-08-19 使用者：「我想將 ROI A 跟
    #: ROI B 的區域線一起接到 GLV stats，但仍然一次只能接一條」）——
    #: 「多連一」講的是**同一件事做在好幾個東西上**，那對區域跟對影像流一樣
    #: 成立：同一組統計量、同一張圖，量在兩個不同的區域上。
    REGION = "roi"

    #: 這張卡**沒有影像也量得下去**嗎（``cd_measure`` 是：區域的矩形已經是
    #: 像素座標，影像只用來做次像素精修）。設 False 的卡拿到的
    #: ``img`` 可能是 ``None``，自己決定怎麼辦。
    REQUIRE_IMAGE = True

    @classmethod
    def source_list(cls, params: Dict[str, object]) -> List[str]:
        return parse_key_list(params.get(cls.SOURCE, ""))

    @classmethod
    def region_list(cls, params: Dict[str, object]) -> List[str]:
        """接了哪幾個區域。**空的回 ``[""]``** —— 那是「量整張圖」。

        回空 list 的話 :meth:`run` 的迴圈會一次都不跑，而「沒挑區域」的意思
        從來就不是「不要量」。
        """
        if not cls.REGION:
            return [""]
        return parse_key_list(params.get(cls.REGION, "")) or [""]

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
    def region_prefix(cls, params: Dict[str, object], name: str) -> str:
        """這一個區域的特徵前綴（**只接一個區域時是空的**）。

        跟 :meth:`stream_prefix` 逐字同一個理由：只接一個時特徵名跟以前一模
        一樣，所以既有的分數表達式不用改寫、黃金值一個數字都不動。
        """
        return str(name) if len(cls.region_list(params)) > 1 and name else ""

    @classmethod
    def full_prefix(cls, params: Dict[str, object], key: str,
                    region: str = "") -> str:
        """流名 ＋ 區域名 ＋ 使用者自己填的 ``output_prefix``（都可能是空的）。

        順序是「流、區域、自己取的名字」：``diff_epi_hot_glv_mean`` 讀起來是
        「diff 這條流、epi 這個區域、我叫它 hot 的那組數字」。
        """
        parts = [cls.stream_prefix(params, key),
                 cls.region_prefix(params, region),
                 str(params.get("output_prefix", "") or "").strip()]
        return "_".join([x for x in parts if x])

    @classmethod
    def feature_names(cls, params: Dict[str, object]) -> List[str]:
        """這張卡**在這組參數下**會產出的特徵基本名（不含任何前綴）。

        PR-3 起是 :meth:`base_specs` 的投影 —— 名字與它的結構身分同一張表
        出生。既有覆寫（GLV/CD）已改覆寫 `base_specs`；還覆寫這一支的第三方
        卡照樣可用（`base_specs` 的預設讀它）。
        """
        return [e[0] for e in cls.base_specs(params)]

    @classmethod
    def base_specs(cls, params: Dict[str, object]
                   ) -> List[Tuple[str, str, str, str, str]]:
        """基本名 ＋ 它的身分：``[(base, metric, stat, variant, family)]``。

        子類在**組名字的那幾行**同時給身分（PR-3 的「誕生處」）；預設從
        `features_out` 來、身分空白（退化不是錯）。⚠ 順序就是宣告順序 ——
        `resolve_features` 由此投影，動順序就是動宣告。
        """
        if cls.feature_names.__func__ is not MultiSourceStep.feature_names.__func__:
            # 第三方卡只覆寫了 feature_names：以它為準（相容退路）。
            return [(str(n), "", "", "", "") for n in cls.feature_names(params)]
        return [(str(n), "", "", "", "") for n in cls.features_out]

    @classmethod
    def resolve_feature_specs(cls, params: Dict[str, object]) -> List[FeatureSpec]:
        """一個雙迴圈產出**帶身分的**宣告（PR-3）。

        `resolve_features` 與 `feature_parts` 都是它的投影 —— 以前那兩支是
        同一個迴圈的兩份手抄，現在只剩一份。名字仍由同一組
        `full_prefix`/`prefix_names` 組出（鐵測試 B 半的字面快照守著）。

        nm 的那一份**一律宣告**（`nm_twins` 只在 nm/px 填了的時候才產出）。
        宣告是「可能會碰到的」，而這張卡看不到 Load 卡上填了什麼 —— 那個數字
        是整份 recipe 的事。畫面上要不要列它由 `RecipeModel.available_features`
        決定（那裡看得到每一張卡）。
        """
        keys = cls.source_list(params) or [""]
        regions = cls.region_list(params)
        entries = [(str(b), str(m), str(s), str(v), str(f))
                   for b, m, s, v, f in cls.base_specs(params)]
        # 孿生接在**整串後面**（同舊 `base + nm_twin_names(base)` 的順序），
        # metric/family 繼承本尊、variant 換成 nm/nm2。
        block = entries + [
            (twin, m, s, var, f)
            for (b, m, s, _v, f) in entries
            for twin, var in nm_twin_specs([b])]
        own = str(params.get("output_prefix", "") or "").strip()
        out: List[FeatureSpec] = []
        for key in keys:
            stream = cls.stream_prefix(params, key)
            for region in regions:
                pfx = cls.full_prefix(params, key, region)
                tag = cls.region_prefix(params, region)
                for base, metric, stat, variant, family in block:
                    out.append(FeatureSpec(
                        name=prefix_names(pfx, [base])[0], card=cls.key,
                        base=base, stream=stream, region=tag,
                        region_index=(regions.index(region) if tag else -1),
                        region_role=(region_role_of(tag) if tag else ""),
                        own=own, variant=variant, metric=metric, stat=stat,
                        family=family))
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, object]) -> List[str]:
        return [s.name for s in cls.resolve_feature_specs(params)]

    @classmethod
    def diagnostic_names(cls, params: Dict[str, object]) -> List[str]:
        """:meth:`feature_names` 裡屬於「量得準不準／卡自己做了什麼」的那幾個
        **基本名**（不含前綴）。子類宣告基本名，前綴交給下面兩支 —— 跟
        :meth:`resolve_features` 走同一條 ``full_prefix`` 迴圈，所以宣告出來的
        名字跟真的產出的名字不可能對不上。"""
        return []

    @classmethod
    def diagnostic_alarm_names(cls, params: Dict[str, object]) -> List[Tuple[str, bool]]:
        """(基本名, 出事時的布林值) —— 見 `Step.diagnostic_alarms`。"""
        return []

    @classmethod
    def diagnostic_features(cls, params: Dict[str, object]) -> List[str]:
        keys = cls.source_list(params) or [""]
        base = cls.diagnostic_names(params)
        return [n for k in keys for r in cls.region_list(params)
                for n in prefix_names(cls.full_prefix(params, k, r), base)]

    @classmethod
    def diagnostic_alarms(cls, params: Dict[str, object]) -> List[Tuple[str, bool]]:
        keys = cls.source_list(params) or [""]
        pairs = cls.diagnostic_alarm_names(params)
        base = [n for n, _ in pairs]
        return [(n, bad)
                for k in keys for r in cls.region_list(params)
                for n, (_, bad) in zip(
                    prefix_names(cls.full_prefix(params, k, r), base), pairs)]

    @classmethod
    def feature_parts(cls, params: Dict[str, object]) -> Dict[str, Dict[str, object]]:
        """見 `Step.feature_parts` —— **`resolve_features` 的反向**。

        PR-3 起兩支都是 :meth:`resolve_feature_specs` 的投影 —— 以前是同一個
        雙迴圈的兩份手抄（各寫一份的話，「這個名字有沒有區域那一段」會有兩個
        答案，而畫面用的是錯的那一個），現在迴圈只剩一份。
        """
        return {s.name: s.parts() for s in cls.resolve_feature_specs(params)}

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, object]) -> List[str]:
        return [r for r in cls.region_list(params) if r]

    #: 迴圈目前跑到哪一條流／哪一個前綴 —— :meth:`run` 塞進交給 :meth:`measure`
    #: 的那份參數裡（F18 第 2 步）。
    #:
    #: 為什麼要有：子類**刻意**不知道「接了幾條流、幾個區域」（那是基底的事），
    #: 但一張卡如果要往 ``ctx.meta`` 留一份給儀表看的東西，它就得說得出「這一份
    #: 是誰的」—— 而畫面上那句話要跟特徵名對得起來，否則兩條流的兩張直方圖在
    #: 面板上是分不出來的兩塊。
    #:
    #: 底線開頭 = 這不是使用者填的參數（`validate_params` 產生的 dict 裡不會有
    #: 它們，是 `run` 事後加的）。
    CURRENT_STREAM = "_stream"
    CURRENT_PREFIX = "_prefix"

    #: 這一輪是**第幾個**區域（``region_list`` 裡的位置）。
    #:
    #: 為什麼非得由基底給：迴圈把 :data:`REGION` 換成了**當前那一個**區域名，
    #: 所以子類再也數不出「這是第幾個」—— 它拿到的 ``roi`` 永遠只有一個值。
    #: 而那個順序有用途：**顏色**。區域框、面板、影像上的標記都照它挑
    #: `theme.REGION_COLORS`，各自從自己那邊數的話，"top,bot" 在一邊是 0/1、
    #: 在另一邊（照名字排序）是 1/0，而顏色指錯區域比沒有顏色糟得多。
    CURRENT_REGION_INDEX = "_region_index"

    def measure(self, ctx: Context, img, params: Dict[str, object]):
        """量一張影像，回 ``{特徵名: 值}``（回 ``None`` = 這條流沒有東西可記）。"""
        raise NotImplementedError

    def run(self, ctx: Context, params: Dict[str, object]) -> Context:
        p = self.validate_params(params)
        regions = self.region_list(p)
        for key in self.source_list(p):
            img = (require_image(ctx, self.key, key) if self.REQUIRE_IMAGE
                   else ctx.images.get(key))
            for region in regions:
                # 每一輪交給 `measure` 的是**一個**區域 —— 子類完全不必知道
                # 「接了幾個」，跟它不必知道接了幾條流是同一件事。
                one = dict(p, **{self.REGION: region}) if self.REGION else dict(p)
                one[self.CURRENT_STREAM] = key
                one[self.CURRENT_PREFIX] = self.full_prefix(p, key, region)
                one[self.CURRENT_REGION_INDEX] = regions.index(region)
                feats = self.measure(ctx, img, one)
                if not feats:
                    continue
                # 量出來的是 pixel；nm/px 填了就**多配一份 nm 的**（不是換掉）。
                feats = dict(feats, **nm_twins(feats, ctx.nm_per_px))
                ctx.add_features(prefix_features(
                    self.full_prefix(p, key, region), feats))
        return ctx
