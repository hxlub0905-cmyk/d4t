# ADEPT algorithm library — authored 2026-08-13 (F8).
"""兩組正交條紋的**交會處** → 一組方框。純規則，不需要任何外部檔案。

這在解什麼問題
--------------
站點已經有兩招可以定位 ROI，兩招都要**外部的東西**：GDS（要 .oas）與 Golden
Cell 模板（要一張原大圖）。第三招 —— 只看 patch 自己 —— 目前只到
``algo/profile.py``，而那個依設計只吐**一條滿版的條紋**（單軸投影對另一個
方向一無所知，所以它拒絕猜）。

那個拒絕對**一次**投影是對的。它擋掉的是另一件事：**另一個方向的範圍不需要
猜，再投影一次就量得到。** 兩組正交的條紋交叉出一個格子陣列，要框的東西就
落在格子上 —— 而且**通常不只一個**（一張 patch 上有好幾根直線、好幾根橫線，
交會處自然是分散的好幾塊）。

用實際的話講一次（這是需求的來源）：patch 裡有直的 Metal Gate 與橫的 EPI，
要量的是「MG 與 EPI 的交界、落在 EPI 那一側」的那幾小塊。

為什麼不寫死那兩種材質
----------------------
這裡只認得「**這個方向有一組條紋**」。誰是 MG、誰是 EPI、誰亮誰暗，卡片不
需要知道 —— 使用者回答的是三個對任何 layout 都成立的問題：

1. 哪個方向的條紋（直的／橫的）
2. 要暗的那組還是亮的那組（**相對**亮度，不是絕對灰階 —— 灰階會隨機台漂移）
3. 框放在交會處的哪裡（整格／貼著邊界／兩根之間）

為什麼不用週期估測
------------------
``algo/period.py`` 的 ``estimate_period`` 需要 2–3 個完整週期才可靠
（信心門檻 40，純雜訊約 20），而 EBI patch 常常只有 64–128 px。投影不需要
週期：它是**直接量到**每一根線在哪。少一層假設就少一種失敗方式，pitch 不均、
邊緣缺一根都不影響。

已知 pitch 時（GDS 給的，站點通常知道）
---------------------------------------
知道 pitch 之後**還是不必估週期**，但它有三件事可做，見 :func:`find_stripes`：
驗證（抓到的間距對不對）、補線（邊緣只露一半、對比不足而漏掉的那幾根）、
以及把「需要好幾個週期」降成「**需要一條可靠的邊界**」—— 這在 64 px 的
patch 上是決定性的差別。

⚠ **pitch 一律是像素。** GDS 給的是 nm，而 ``nm_per_px`` 在 KLARF 裡沒有來源
（見 CLAUDE.md §8：單位一律 pixel、換算搬到輸出那一刻）。這裡收 nm 的話，
它會變成第二個恆為 0 的 ``cd_x_nm``。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from . import profile as algo_profile

__all__ = ["StripeSet", "CrossResult", "find_stripes", "select_bands",
           "cross_boxes", "locate_crossings",
           "SELECT_RULES", "PLACEMENTS", "SIDES"]

#: 「要哪一組條紋」。用**相對**亮度（跟這張圖上其他段比），不是絕對灰階 ——
#: 絕對值會隨機台與曝光漂移，一份 recipe 就綁死在一台機器上。
#:
#: **不是只有兩層。** 實際的 layout 常常三層以上（站點回報：MG 最亮約 220、
#: EPI 次之約 180、其餘更暗），而中位數二分法會把 220 跟 180 併成同一組 ——
#: 於是「我要 EPI」講不出來。所以規則是**排名**：分幾群由排名決定
#: （見 :func:`level_groups`），使用者只要回答「第幾亮的那一組」。
#: ``dark`` / ``bright`` 保留為 ``darkest`` / ``brightest`` 的舊名。
SELECT_RULES = ("brightest", "second_brightest", "third_brightest",
                "darkest", "second_darkest", "third_darkest", "all")

#: 舊名 → 新名（F8 第一版只有兩層時用的字）。
_SELECT_ALIASES = {"dark": "darkest", "bright": "brightest"}

#: 框放在交會處的哪裡。``beside_*`` / ``between_*`` 後面接的是**被貼住的那組
#: 條紋**，另一組永遠是限制框長度的那一邊 —— 所以五個值各自說得完自己是什麼，
#: 不需要再配一個「貼哪一軸」的參數。
PLACEMENTS = ("crossing",
              "beside_vertical", "beside_horizontal",
              "between_vertical", "between_horizontal")

#: ``beside_*`` 時要哪一邊。``start`` = 左／上，``end`` = 右／下。
SIDES = ("both", "start", "end")

#: 已知 pitch 時，找到的邊界可以離晶格多遠（pitch 的比例）還算「對得上」。
DEFAULT_PITCH_TOL = 0.25


@dataclass
class StripeSet:
    """一個方向上找到的條紋。

    ``axis="x"`` = 沿 X 走的曲線（每一**欄**一個值）→ 找到的是**直的**條紋。
    """

    axis: str
    profile: np.ndarray
    raw: np.ndarray
    edges: List[int] = field(default_factory=list)
    bands: List[Tuple[int, int]] = field(default_factory=list)
    #: 每一段的平均亮度（跟 ``bands`` 等長）。
    levels: List[float] = field(default_factory=list)
    #: **要的那一組**條紋（暗的或亮的），已套用已知 pitch 的補線。
    selected: List[Tuple[int, int]] = field(default_factory=list)
    #: 從影像上量到的週期 = **同一組條紋**的中心距中位數；量不到是 0。
    pitch_measured: float = 0.0
    #: 實際用來排晶格的 pitch（沒給或對不上就等於 ``pitch_measured``）。
    pitch_used: float = 0.0
    #: 找到的條紋中心離晶格有多遠（像素中位數）。沒給 pitch 是 -1。
    pitch_error: float = -1.0
    #: 實際使用的 pitch 清單（交錯時不只一個）。
    pitches_used: List[float] = field(default_factory=list)
    #: 有幾根條紋是**晶格補上的**（影像上沒抓到，靠已知 pitch 推出來）。
    filled: int = 0
    confidence: float = 0.0

    @property
    def length(self) -> int:
        return int(self.profile.size)


@dataclass
class CrossResult:
    """一次交會定位的完整結果 —— 包含畫得出來所需要的一切。

    UI 面板直接吃這個 dataclass，所以「使用者看到的框」與「真的量下去的框」
    保證是同一次計算（``profile.py`` 同一條規矩）。
    """

    x: StripeSet
    y: StripeSet
    #: 像素矩形 ``(x, y, w, h)``，**依離影像中心遠近排序**（近的在前）。
    boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)
    confidence: float = 0.0
    ok: bool = False
    reason: str = ""

    @property
    def center_box(self) -> Optional[Tuple[int, int, int, int]]:
        """離 patch 正中心最近的那一格 —— 缺陷永遠在那裡（裁切方式保證的）。"""
        return self.boxes[0] if self.boxes else None


# --------------------------------------------------------------------------- #
# 一個方向的條紋
# --------------------------------------------------------------------------- #
#: ``SELECT_RULES`` → ``(從哪一端數, 第幾組)``。0 = 最外面那一組。
_RANKS = {"brightest": ("hi", 0), "second_brightest": ("hi", 1),
          "third_brightest": ("hi", 2), "darkest": ("lo", 0),
          "second_darkest": ("lo", 1), "third_darkest": ("lo", 2)}


def level_groups(levels: Sequence[float], k: int) -> List[int]:
    """把每一段的亮度分成 ``k`` 群，回傳每段的群編號（0 = 最暗那群）。

    切在**排序後最大的 k−1 個間隙**上（一維自然斷點）。為什麼不是等分或
    k-means：材質之間的灰階差本來就是一個個台階，而台階與台階之間的間隙遠大於
    同一種材質內部的起伏 —— 找間隙就是在找台階，而且不需要迭代、不需要種子，
    同一張圖每次跑的答案完全相同（批次快取的前提）。
    """
    lv = [float(v) for v in levels]
    k = max(1, int(k))
    if k <= 1 or len(lv) <= 1:
        return [0] * len(lv)

    order = sorted(range(len(lv)), key=lambda i: lv[i])
    gaps = sorted(range(1, len(order)),
                  key=lambda j: lv[order[j]] - lv[order[j - 1]],
                  reverse=True)[:k - 1]
    cuts = set(gaps)
    group_of = [0] * len(lv)
    g = 0
    for j, i in enumerate(order):
        if j in cuts:
            g += 1
        group_of[i] = g
    return group_of


def select_bands(bands: Sequence[Tuple[int, int]], levels: Sequence[float],
                 rule: str = "brightest") -> List[Tuple[int, int]]:
    """挑出「要哪一組條紋」—— 依**相對**亮度的排名，不是絕對灰階。

    分成幾群由排名決定：要「最亮的」就分兩群，要「第二亮的」就分三群，
    以此類推。這樣使用者只要回答一個問題（第幾亮），不必再猜「這張圖有幾種
    材質」—— 而後者他通常答得出來，但那是**另一個**問題，多問一次就多一次
    填錯的機會。

    只有一段（沒找到任何邊界）時原樣回傳 —— 那不是「挑中了」是「沒得挑」，
    交給上層用段數判斷。
    """
    bands, levels = list(bands), list(levels)
    if not bands:
        return []
    rule = _SELECT_ALIASES.get(str(rule), str(rule))
    if rule == "all" or len(bands) < 2:
        return bands

    end, rank = _RANKS.get(rule, ("hi", 0))
    k = rank + 2
    groups = level_groups(levels, k)
    want = (max(groups) - rank) if end == "hi" else rank
    picked = [b for b, g in zip(bands, groups) if g == want]
    # 段數不夠分那麼多群的時候會挑不到 —— 退回整組比回空的好，
    # 但上層看得到段數，所以不會把「沒得挑」誤認為「挑到了」。
    return picked or bands


def _walk(anchor: float, pitches: Sequence[float], length: int,
          phase: int) -> List[float]:
    """從 ``anchor`` 往兩邊走，間距**依序**取 ``pitches``（循環）。

    一個 pitch 是等距晶格；兩個就是「寬、窄、寬、窄…」那種交錯的排法
    （站點回報 EPI 與 EPI 之間有兩種間距）。``phase`` 決定從 anchor 往右走的
    第一步用哪一個 —— 錨點落在交錯的哪一相是看不出來的，所以呼叫端把每一相
    都試一次，留誤差最小的那個。
    """
    p = [float(v) for v in pitches if float(v) >= 2.0]
    if not p:
        return [anchor]
    span = max(p)
    out = [anchor]

    c, i = anchor, int(phase)
    while c < length + span:
        c += p[i % len(p)]
        i += 1
        out.append(c)

    c, i = anchor, int(phase) - 1
    while c > -span:
        c -= p[i % len(p)]
        i -= 1
        out.append(c)
    return sorted(out)


def _fill_by_pitch(bands: Sequence[Tuple[int, int]], pitch: float, length: int,
                   tol: float = DEFAULT_PITCH_TOL, pitch_2: float = 0.0
                   ) -> Tuple[List[Tuple[int, int]], float, int, bool]:
    """已知 pitch → 把這一組條紋補成完整的一排。回 ``(條紋, 誤差, 補了幾根, 用了嗎)``。

    **晶格排在條紋的中心上，不是排在邊界上。** 這是這裡最容易做錯的一件事：
    一根寬 8、週期 24 的條紋，它的**邊界**間距是 8、16、8、16… 交錯的，
    只有**中心**才是每 24 一次。拿邊界去對一個等距晶格，會把一根條紋的兩條邊
    併成一格 —— 條紋的寬度整個消失，框就落到隨機的地方（而且看起來還很像對的）。

    錨點取**最靠近影像中心**的那一根：patch 是以缺陷為中心裁的，中心附近的
    結構最完整；最強的那一根可能就在邊上，往外推的誤差會被放大。

    寬度取中位數 —— 邊緣只露一半的那幾根不該把整排的寬度拉窄。

    誤差 = 找到的每個中心離最近格點的距離中位數。**對不上就不要用**：
    pitch 是外面（GDS）帶進來的假設，影像是這一顆真的長的樣子，
    兩者衝突時相信影像，並把證據留給上層講出來。
    """
    got = [(int(a), int(b)) for a, b in bands]
    pitches = [float(p) for p in (pitch, pitch_2) if float(p) >= 2.0]
    if not pitches or not got or length <= 0:
        return got, -1.0, 0, False

    centres = [(a + b) / 2.0 for a, b in got]
    width = float(np.median([b - a for a, b in got]))
    mid = length / 2.0
    anchor = min(centres, key=lambda c: abs(c - mid))

    # 交錯的 pitch 有好幾個「相」，而錨點落在哪一相是看不出來的 ——
    # 每一相都排一次，留最貼合影像的那個。
    best, best_err = None, None
    for phase in range(len(pitches)):
        cand = [c for c in _walk(anchor, pitches, int(length), phase)
                if c + width / 2.0 > 0 and c - width / 2.0 < length]
        if not cand:
            continue
        e = float(np.median([min(abs(c - v) for v in cand) for c in centres]))
        if best_err is None or e < best_err:
            best, best_err = cand, e
    if best is None:
        return got, -1.0, 0, False

    lat, err = best, best_err
    if err > min(pitches) * float(tol):
        return got, err, 0, False

    out = []
    for c in lat:
        span = _clip_span(c - width / 2.0, c + width / 2.0, length)
        if span:
            out.append(span)
    return out, err, max(0, len(out) - len(got)), True


def find_stripes(img: Any, axis: str = algo_profile.AXIS_X,
                 select: str = "brightest", sensitivity: float = 0.35,
                 smooth: int = 3, min_gap: int = 4, pitch: float = 0.0,
                 pitch_2: float = 0.0,
                 pitch_tol: float = DEFAULT_PITCH_TOL) -> StripeSet:
    """找出一個方向上的條紋，並挑出要的那一組。

    ``select`` 在這裡而不是在外面，是因為 ``pitch`` 講的是**同一組條紋**的
    週期（MG 每 24px 一根），而不是「所有邊界」的間距 —— 沒有先挑組就沒有
    週期可言（見 :func:`_fill_by_pitch`）。

    ``pitch``（像素，0 = 不知道）給了之後做三件事：
    **驗證**（``pitch_error``：量到的跟給的對不對）、
    **補線**（邊緣只露一半、對比不足而漏掉的那幾根）、
    以及把錨定條件從「要好幾個週期」降成「**要一根條紋**」——
    64px 的 patch 上這是決定性的差別。
    """
    prof, raw = algo_profile.projection(img, axis=axis, smooth=smooth)
    out = StripeSet(axis=str(axis), profile=prof, raw=raw)
    if prof.size == 0:
        return out

    gap = max(1, int(min_gap) or 4)
    out.edges = list(algo_profile.find_transitions(
        prof, sensitivity=sensitivity, min_gap=gap))
    out.confidence = algo_profile.profile_confidence(prof, raw)
    out.bands = algo_profile.bands_from(out.edges, int(prof.size))
    out.levels = [float(prof[a:b].mean()) if b > a else 0.0
                  for a, b in out.bands]

    picked = select_bands(out.bands, out.levels, select)
    centres = sorted((a + b) / 2.0 for a, b in picked)
    if len(centres) >= 2:
        out.pitch_measured = float(np.median(np.diff(np.asarray(centres))))
    out.pitch_used = out.pitch_measured

    filled, err, n_new, used = _fill_by_pitch(picked, float(pitch),
                                              int(prof.size), pitch_tol,
                                              float(pitch_2))
    out.pitch_error = err
    if used:
        given = [float(p) for p in (pitch, pitch_2) if float(p) >= 2.0]
        # 兩種間距交錯時，「pitch 是多少」沒有單一答案 —— 報平均（那是實際的
        # 平均間距），完整的一組留在 ``pitches_used`` 給面板與特徵用。
        out.filled = n_new
        out.pitches_used = given
        out.pitch_used = float(np.mean(given))
    out.selected = filled
    return out


# --------------------------------------------------------------------------- #
# 交會 → 方框
# --------------------------------------------------------------------------- #
def _clip_span(a: float, b: float, limit: int) -> Optional[Tuple[int, int]]:
    lo, hi = int(round(max(0.0, min(a, b)))), int(round(min(float(limit), max(a, b))))
    return (lo, hi) if hi > lo else None


def _spans_between(bands: Sequence[Tuple[int, int]], length: int
                   ) -> List[Tuple[int, int]]:
    """相鄰兩段**之間**的空隙（也就是「沒有被這組條紋蓋到」的地方）。"""
    out: List[Tuple[int, int]] = []
    ordered = sorted(bands)
    for (_, end), (start, _) in zip(ordered, ordered[1:]):
        if start > end:
            out.append((int(end), int(start)))
    return out


def _edge_spans(bands: Sequence[Tuple[int, int]], width: float, side: str,
                gap: float, length: int) -> List[Tuple[int, int]]:
    """貼著每一段的兩側各切一小條（**在那一段外面** —— 那才是「另一種材質上」）。

    ``gap`` 是離邊界多遠才開始。它不是保險係數，是兩件事各要一點：

    * **邊界本身是混合區。** SEM 上一條邊界糊在好幾個像素上，那幾格的灰階是
      兩種材質混出來的，不代表任何一邊 —— 量進去只會讓數字變鈍。
    * **偵測到的邊界位置有系統性偏差。** 轉折是在**平滑過的**曲線上用中央差分
      找的，實測會早一格左右。合成資料上量過：``gap=0`` 時 5px 寬的框有一欄
      是另一種材質，平均值被拉掉 15%（170 → 145）—— 而那看起來完全像個
      正常的數字。

    切到影像邊緣而只剩半條的**丟掉**：一條殘框仍然會進 mask，然後用幾個像素
    的統計去稀釋整組數字，而它代表的不是任何一個完整的交界。
    """
    w = max(1.0, float(width))
    g = max(0.0, float(gap))
    out: List[Tuple[int, int]] = []
    for band in bands:
        a, b = int(band[0]), int(band[1])
        wanted = []
        if str(side) in ("both", "start"):
            wanted.append((a - g - w, a - g))
        if str(side) in ("both", "end"):
            wanted.append((b + g, b + g + w))
        for lo, hi in wanted:
            span = _clip_span(lo, hi, length)
            if span and (span[1] - span[0]) >= w * 0.5:
                out.append(span)
    return out


def _spans_for(placement: str, axis: str, bands: Sequence[Tuple[int, int]],
               box_size: float, side: str, gap: float, inset: float,
               length: int) -> List[Tuple[int, int]]:
    """這一軸貢獻哪些區間 —— 依 ``placement`` 決定它是被貼住的還是當界線的。"""
    place, ax = str(placement), str(axis)
    if place == "beside_%s" % ax:
        return _edge_spans(bands, box_size, side, gap, length)
    if place == "between_%s" % ax:
        return [s for s in (_clip_span(a + gap, b - gap, length)
                            for a, b in _spans_between(bands, length))
                if s is not None]
    # 這一軸只是界線 —— 用整段，並往內縮 inset 避開它自己的邊界
    pad = max(0.0, float(inset))
    out = []
    for a, b in bands:
        span = _clip_span(a + pad, b - pad, length)
        if span:
            out.append(span)
    return out


def cross_boxes(x: StripeSet, y: StripeSet,
                placement: str = "crossing", box_size: float = 4.0,
                side: str = "both", gap: float = 1.0, inset: float = 0.0,
                shape: Optional[Tuple[int, int]] = None
                ) -> List[Tuple[int, int, int, int]]:
    """兩組條紋交會出來的方框（像素座標，**依離影像中心遠近排序**）。

    五種放法（``vertical`` = 直的條紋，由 X 投影找到；``horizontal`` = 橫的）：

    * ``crossing`` —— 整個交會矩形。裡面同時含兩種材質。
    * ``beside_vertical`` —— **貼著直條紋的左右、落在橫條紋段內**的一小條。
      這是「兩種材質的交界，而量在另一種材質上」，一根直條紋左右各一個框。
    * ``beside_horizontal`` —— 同上，貼的是橫條紋的上下。
    * ``between_vertical`` —— 兩根直條紋**之間**（沒有被直條紋蓋到的乾淨區）。
    * ``between_horizontal`` —— 同上，換一軸。

    ``inset`` 往內縮的是**當界線的那一軸**：框同時貼著兩種邊界的話，量到的
    變化是哪一邊造成的就分不出來了。
    """
    h, w = (int(shape[0]), int(shape[1])) if shape else (y.length, x.length)
    if h <= 0 or w <= 0:
        return []

    xb, yb = list(x.selected), list(y.selected)
    if not xb or not yb:
        return []

    x_spans = _spans_for(placement, "vertical", xb, box_size, side, gap, inset, w)
    y_spans = _spans_for(placement, "horizontal", yb, box_size, side, gap, inset, h)

    boxes = [(xa, ya, xb_ - xa, yb_ - ya)
             for ya, yb_ in y_spans for xa, xb_ in x_spans
             if xb_ > xa and yb_ > ya]

    cx, cy = w / 2.0, h / 2.0
    boxes.sort(key=lambda b: ((b[0] + b[2] / 2.0 - cx) ** 2
                              + (b[1] + b[3] / 2.0 - cy) ** 2))
    return boxes


def locate_crossings(img: Any, vertical_select: str = "brightest",
                     horizontal_select: str = "brightest",
                     vertical_sensitivity: float = 0.35,
                     horizontal_sensitivity: float = 0.35,
                     smooth: int = 3, min_gap: int = 4,
                     vertical_pitch: float = 0.0,
                     vertical_pitch_2: float = 0.0,
                     horizontal_pitch: float = 0.0,
                     horizontal_pitch_2: float = 0.0,
                     placement: str = "crossing", box_size: float = 4.0,
                     side: str = "both", gap: float = 1.0, inset: float = 0.0,
                     min_confidence: float = 5.0,
                     max_boxes: int = 64) -> CrossResult:
    """一次做完：兩軸投影 → 條紋 → 交會 → 方框。

    ``vertical_*`` 是**直的**條紋（由 X 投影找到），``horizontal_*`` 是橫的。
    用「直的／橫的」而不是「x 軸／y 軸」：使用者看的是畫面，而「x 投影找到的
    是垂直邊界」這件事每次都要在腦裡轉一次。

    這是 step 卡與 UI 面板共用的**唯一**入口。兩邊必須看到同一次計算，
    不然「畫面上的框」跟「真的量下去的框」會不一樣，而那種 bug 極難發現。
    """
    a = np.asarray(img)
    shape = (int(a.shape[0]), int(a.shape[1])) if a.ndim >= 2 else (0, 0)

    xs = find_stripes(img, axis=algo_profile.AXIS_X, select=vertical_select,
                      sensitivity=vertical_sensitivity, smooth=smooth,
                      min_gap=min_gap, pitch=vertical_pitch,
                      pitch_2=vertical_pitch_2)
    ys = find_stripes(img, axis=algo_profile.AXIS_Y, select=horizontal_select,
                      sensitivity=horizontal_sensitivity, smooth=smooth,
                      min_gap=min_gap, pitch=horizontal_pitch,
                      pitch_2=horizontal_pitch_2)

    conf = min(float(xs.confidence), float(ys.confidence))
    res = CrossResult(x=xs, y=ys, confidence=conf)

    # 兩軸都要有東西可比。**一軸失敗就整張失敗** —— 交會處是兩組條紋共同定義
    # 的，少一組的話另一組只能給滿版的條帶，那不是使用者要的框。
    if conf < float(min_confidence):
        # **講出是哪一個方向沒東西。** 「信心不足」只說得出「失敗了」，
        # 而使用者下一步要做的事（調哪一組參數、還是這種 patch 本來就沒有
        # 橫的條紋）完全取決於是哪一邊。
        weak = ("upright stripes" if xs.confidence <= ys.confidence
                else "flat stripes")
        res.reason = ("no %s to lock onto (confidence %.1f across / %.1f down, "
                      "needs %.1f)" % (weak, xs.confidence, ys.confidence,
                                       float(min_confidence)))
        return res
    if len(xs.bands) < 2 or len(ys.bands) < 2:
        res.reason = ("found %d band(s) across and %d down; both directions "
                      "need at least two so that there is a crossing"
                      % (len(xs.bands), len(ys.bands)))
        return res

    boxes = cross_boxes(xs, ys, placement=placement, box_size=box_size,
                        side=side, gap=gap, inset=inset, shape=shape)
    if not boxes:
        res.reason = "the stripes were found but they produce no usable box"
        return res

    limit = max(1, int(max_boxes))
    res.boxes = boxes[:limit]        # 已依離中心遠近排序 —— 砍掉的是最外圍的
    res.ok = True
    if len(boxes) > limit:
        res.reason = ("kept the %d box(es) nearest the centre out of %d"
                      % (limit, len(boxes)))
    return res
