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

import math
from dataclasses import dataclass, field
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

from . import profile as algo_profile

__all__ = ["StripeSet", "CrossResult", "find_stripes", "select_bands",
           "cross_boxes", "locate_crossings",
           "SELECT_RULES", "PLACEMENTS", "SIDES", "FILL_RULES",
           "measure_pitches"]

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

#: 晶格上「應該有一根、但影像上沒有」的位置怎麼處置。
#:
#: 這個選擇存在是因為那句話有**兩種**成因，而它們的正確處置相反：
#:
#: * 那根線太淡／被邊界切掉 —— 它其實在，補上是對的。
#: * 那個位置根本是**另一種材質**（站點的 CPODE：MG 被挖掉換成很暗的東西，
#:   位置與寬度都在同一個晶格上）—— 補上就是在無中生有。
#:
#: pitch 分不出這兩者（它只說「每隔多遠有一根」），但**亮度分得出來**：
#: 太淡的線仍然落在背景與目標之間，換了材質的那個會跑到背景的**另一邊**。
#: 所以判斷用的是那個位置實際的灰階，不是額外再問使用者一次。
FILL_RULES = ("fill", "skip", "skip_clear")

#: 兩個 pitch 交錯時，贏的那個相要比第二名好上「兩個 pitch 差距」的多少比例，
#: 才算真的分得出來。見 :func:`_fill_by_pitch`。
_PHASE_MARGIN = 0.15


class _Fill(NamedTuple):
    """``_fill_by_pitch`` 的結果。

    用具名的而不是六個一組的 tuple：這個回傳值一路長到六項，而中間四項都是
    數字 —— 呼叫端拆錯一個位置不會有任何錯誤訊息，只會安靜地把「補了幾根」
    當成「線寬」。
    """

    bands: List[Tuple[float, float]]
    error: float
    invented: int
    used: bool
    width: float
    #: 為什麼沒用（空字串 = 用了，或者根本沒給 pitch）。**要講出來**：
    #: 「我分不出來」是一個有用的答案，「我猜一個」不是。
    note: str


@dataclass
class StripeSet:
    """一個方向上找到的條紋。

    ``axis="x"`` = 沿 X 走的曲線（每一**欄**一個值）→ 找到的是**直的**條紋。
    """

    axis: str
    profile: np.ndarray
    raw: np.ndarray
    edges: List[int] = field(default_factory=list)
    #: 精修到次像素的轉折位置（段的幾何用這個，見 :func:`refine_edges`）。
    edges_sub: List[float] = field(default_factory=list)
    bands: List[Tuple[float, float]] = field(default_factory=list)
    #: 每一段的平均亮度（跟 ``bands`` 等長）。
    levels: List[float] = field(default_factory=list)
    #: **要的那一組**條紋（暗的或亮的），已套用已知 pitch 的補線。
    selected: List[Tuple[int, int]] = field(default_factory=list)
    #: 從影像上量到的週期 = **同一組條紋**的中心距中位數；量不到是 0。
    pitch_measured: float = 0.0
    #: 間距看起來是**交錯**的時候，第二個量到的值（不交錯就是 0）。
    #: 有這個才答得出使用者的「有辦法自動量好填進左邊那兩格嗎」。
    pitch_measured_2: float = 0.0
    #: 實際用來排晶格的 pitch（沒給或對不上就等於 ``pitch_measured``）。
    pitch_used: float = 0.0
    #: 找到的條紋中心離晶格有多遠（像素中位數）。沒給 pitch 是 -1。
    pitch_error: float = -1.0
    #: 實際使用的 pitch 清單（交錯時不只一個）。
    pitches_used: List[float] = field(default_factory=list)
    #: 有幾根條紋是**晶格補上的**（影像上沒抓到，靠已知 pitch 推出來）。
    filled: int = 0
    #: 晶格上被**擋掉**的位置：那裡的灰階說它是另一種材質（例：CPODE）。
    #: 它們不在 ``selected`` 裡，但框的產生要看得到它們 —— 「不要在它上面放框」
    #: 與「不要放面向它的框」是兩件事，後者需要知道它在哪。
    blocked: List[Tuple[float, float]] = field(default_factory=list)
    #: ``blocked`` 的位置要不要連**面向它的框**一起去掉（``skip_clear``）。
    #: 跟 ``blocked`` 分開是因為「那一格沒有條紋」本身是資訊，面板要講；
    #: 「連隔壁的框也不要」是使用者的選擇。
    clear_neighbours: bool = False
    #: 實際用的線寬（使用者給了就是那個值，沒給就是量到的中位數）。
    width_used: float = 0.0
    #: 線寬是使用者給的（True）還是量出來的（False）。
    width_fixed: bool = False
    #: 給了 pitch 卻沒有用的原因（空字串 = 用了，或者沒給）。
    pitch_note: str = ""
    #: 晶格把條紋**搬了多遠**（找到的中心 → 它變成的格點，取最大值）。
    #: 使用者看到的「藍框跟藍線對不齊」就是這個數字 —— 它是刻意的
    #: （次像素精修 + 對齊到你給的 pitch），但沒講出來就只是「怪」。
    snap_shift: float = 0.0
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
                 rule: str = "brightest", kinds: int = 0
                 ) -> List[Tuple[int, int]]:
    """挑出「要哪一組條紋」—— 依**相對**亮度的排名，不是絕對灰階。

    分成幾群預設由排名決定：要「最亮的」就分兩群，要「第二亮的」就分三群。
    這樣使用者只要回答一個問題（第幾亮），不必再猜「這張圖有幾種材質」。

    ``kinds`` 是那個預設**不夠用**的時候的出口
    ------------------------------------------
    「分兩群」隱含了一個假設：畫面上只有兩種東西（線，跟線之間的空隙）。
    多一種材質就會破功，而且是**安靜地**破功。實例（使用者的 CPODE）：
    一排 MG 裡有一根被挖掉換成很暗的 CPODE，於是這條曲線上有三個台階 ——
    亮的 MG（216）、中間的空隙（133）、很暗的 CPODE（41）。分兩群時最大的
    間隙落在 CPODE 與空隙之間，於是「最亮的那一群」= MG **加上空隙**，
    挑到的條紋是實際的兩倍、量到的 pitch 是實際的一半。
    更糟的是給了 pitch 之後：晶格照樣排得出一組間距完全正確的解，只是它鎖在
    **空隙**上而不是 MG 上 —— ``pitch_error`` 是 0.0，看起來完美。

    所以這個參數的問法是「這個方向上有幾種條紋」，不是「分幾群」。
    同一個晶格上多一種材質就加一，預設 0 = 照排名推（也就是舊行為）。

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
    # 排名要求的群數是**下限**：要挑「第三亮」至少得分四群，使用者說有三種
    # 材質也不能少分。兩者取大的那個。
    k = max(rank + 2, int(kinds or 0))
    groups = level_groups(levels, k)
    want = (max(groups) - rank) if end == "hi" else rank
    picked = [b for b, g in zip(bands, groups) if g == want]
    # 段數不夠分那麼多群的時候會挑不到 —— 退回整組比回空的好，
    # 但上層看得到段數，所以不會把「沒得挑」誤認為「挑到了」。
    return picked or bands


def refine_edges(prof: Any, edges: Sequence[int]) -> List[float]:
    """把整數的轉折位置精修到**次像素**（拋物線內插梯度峰）。

    為什麼非做不可 —— 這是 F8 第二輪抓到的「框左右歪一點」
    ------------------------------------------------------
    邊界在影像上是糊的，所以 ``|梯度|`` 的峰**通常是一個 2 格寬的平台**：一根
    真實起點在 21 的條紋，量到的是 ``grad[20] == grad[21]``（實測完全相等）。
    而 ``find_transitions`` 挑局部極大的條件左右不對稱
    （``> 左鄰`` 但 ``>= 右鄰``），於是同一根條紋的兩條邊會**各挑到平台的不同
    側** —— 實測左邊界一律 −1、右邊界 0，段寬 8 變成 9。

    後果不是「差一格」而已：``beside_*`` 的框是貼著段的兩側放的，段往左胖了
    一格，**左邊那個框就往外挪一格、右邊那個沒有** —— 兩個框到 MG 的距離不一樣，
    畫面上看起來就是「一邊貼著、一邊有縫」。而且它們量的是同一種材質，
    所以數字上完全看不出來。

    拋物線內插對稱地把峰放回 20.5 —— 那正是真實邊界（第 21 格是第一格亮的，
    所以邊界在 20 與 21 之間）。實測：平台 ``(12.079, 17.855, 17.855)`` →
    偏移 +0.5，與真值一致。
    """
    p = np.asarray(prof, dtype=np.float64)
    if p.size < 3:
        return [float(e) for e in edges]
    g = np.abs(np.gradient(p))
    out: List[float] = []
    for e in edges:
        i = int(e)
        if i <= 0 or i >= g.size - 1:
            out.append(float(i))
            continue
        a, b, c = float(g[i - 1]), float(g[i]), float(g[i + 1])
        denom = a - 2.0 * b + c
        # 平坦（denom≈0）時內插沒有意義 —— 原樣回傳比外插到天邊好。
        delta = 0.0 if abs(denom) < 1e-9 else 0.5 * (a - c) / denom
        out.append(float(i) + max(-1.0, min(1.0, delta)))
    return out


def _bands_from(edges: Sequence[float], length: int
                ) -> List[Tuple[float, float]]:
    """轉折之間就是一段（**保留次像素**）。影像兩端也算邊界。"""
    if length <= 0:
        return []
    inner = sorted(float(e) for e in edges if 0.0 < float(e) < float(length))
    marks = [0.0] + inner + [float(length)]
    return [(a, b) for a, b in zip(marks, marks[1:]) if b > a]


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


def _fixed_width(bands: Sequence[Tuple[float, float]], width: float,
                 length: int) -> List[Tuple[float, float]]:
    """把每一段換成「原本的中心 ± 給定線寬的一半」，超出影像的部分切掉。

    切掉而不是整根平移：一根只露出半根的線就是只有半根，把它推回影像裡等於
    捏造一個不存在的位置，而框正是貼著它放的。
    """
    out: List[Tuple[float, float]] = []
    w = float(width)
    for a, b in bands:
        c = (float(a) + float(b)) / 2.0
        lo, hi = max(0.0, c - w / 2.0), min(float(length), c + w / 2.0)
        if hi - lo >= 1.0:
            out.append((lo, hi))
    return out


def measure_pitches(centres: Sequence[float]) -> Tuple[float, float]:
    """從一排條紋的中心量出間距。回 ``(pitch, 第二個 pitch)``，不交錯時第二個 0。

    使用者的問題是「不知道 pitch 的時候怎麼辦」，而畫面上的曲線其實已經知道了。
    這個函式就是那個答案的來源（量測尺是手動版，這是自動版）。

    兩件事會把天真的「相鄰間距取中位數」弄錯，而它們要用**相反**的方法處理：

    * **交錯的間距**（寬、窄、寬、窄）—— 中位數落在兩者之間，兩個都不對。
      認法：把間距按奇偶位置分兩組，**兩組都要至少兩個**（看過它重複一次）
      而且中位數差得夠開。少於兩個的話「一寬一窄」跟「其中一個是雜訊」
      分不開，而後者常見得多。
    * **中間缺了幾根**（太淡、或者那裡是別的材質）—— 缺一根就多一個
      「兩倍」的間距，而中位數會被它拉走。認法：每個間距除以它最接近的
      整數倍，再取中位數。

    順序不能反：先問交錯，因為「除以整數倍」會把交錯的寬間距當成窄的兩倍，
    然後兩個答案都毀掉。
    """
    cs = sorted(float(c) for c in centres)
    if len(cs) < 2:
        return 0.0, 0.0
    diffs = [b - a for a, b in zip(cs, cs[1:]) if b - a > 1e-6]
    if not diffs:
        return 0.0, 0.0

    even = [d for i, d in enumerate(diffs) if i % 2 == 0]
    odd = [d for i, d in enumerate(diffs) if i % 2 == 1]
    if len(even) >= 2 and len(odd) >= 2:
        a, b = float(np.median(even)), float(np.median(odd))
        # 兩組**各自**還要是齊的。少了這一關，一排等距的線中間缺一根就會被
        # 當成交錯：間距 [24, 24, 48, 24] 的奇偶兩組是 [24, 48] 與 [24, 24]，
        # 中位數 36 與 24 差得夠開 —— 但 [24, 48] 自己根本不成一組。
        even_ok = (max(even) - min(even)) <= max(a, 1e-6) * 0.15
        odd_ok = (max(odd) - min(odd)) <= max(b, 1e-6) * 0.15
        if even_ok and odd_ok and abs(a - b) > max(a, b) * 0.15:
            return a, b

    # 缺了幾根的情況：最小的那個間距當單位，其餘除以最接近的整數倍。
    unit = min(diffs)
    steps = [d / max(1.0, float(_half_up(d / unit))) for d in diffs]
    return float(np.median(steps)), 0.0


def _pitch_list(*pitches: float) -> List[float]:
    """收下的 pitch 裡真的是 pitch 的那幾個（0 = 沒給，1 px 沒有意義）。"""
    return [float(p) for p in pitches if float(p) >= 2.0]


def _band_level(prof: Any, a: float, b: float) -> float:
    lo, hi = _half_up(a), _half_up(b)
    seg = np.asarray(prof)[max(0, lo):max(lo + 1, hi)]
    return float(seg.mean()) if seg.size else 0.0


#: 要判定「這裡是別的材質」，那個位置得比背景再**過去**多少
#: （條紋與背景反差的比例）。見 :func:`_split_by_material`。
MATERIAL_MARGIN = 0.25


def _split_by_material(prof: Any, lattice: Sequence[Tuple[float, float]],
                       found: Sequence[Tuple[float, float]],
                       target: float, background: float, want_bright: bool,
                       near: float
                       ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """把晶格點分成「留下」與「擋掉」—— 依那個位置**實際的**灰階。

    只審**補出來的**那幾格。影像上真的抓到的那幾根是靠亮度排名挑出來的，
    它們依定義已經是對的材質，再審一次只會多一種誤判。

    判準刻意設計成「**要有正面證據才擋**」
    --------------------------------------
    只有落在**背景的另一邊、而且超過一個邊際**才算換了材質。三種位置：

    * 太淡而漏抓的線 —— 仍然在背景與目標之間 → **留**（補線本來就是為了它）
    * 整根不見、那裡就是背景 —— 沒有任何證據說它是別的東西 → **留**
    * CPODE 那種被挖掉的 —— 掉到背景**以下**一大截 → **擋**

    邊際不能省。第二種（那格就是背景）沒有邊際的話就變成擲硬幣：實測把一根
    MG 抹成背景之後，那一格的灰階與背景只差雜訊，補不補得回來由 seed 決定。
    邊際取「條紋與背景反差」的比例而不是固定灰階值 —— 反差會隨機台漂移，
    固定值等於把 recipe 綁在一台機器上（跟 ``select`` 用排名同一個道理）。
    """
    keep: List[Tuple[float, float]] = []
    blocked: List[Tuple[float, float]] = []
    centres = [(a + b) / 2.0 for a, b in found]
    margin = abs(float(target) - float(background)) * MATERIAL_MARGIN
    for a, b in lattice:
        c = (a + b) / 2.0
        if centres and min(abs(c - v) for v in centres) <= near:
            keep.append((a, b))          # 影像上真的看到了，不必審
            continue
        lvl = _band_level(prof, a, b)
        ok = (lvl >= background - margin) if want_bright \
            else (lvl <= background + margin)
        (keep if ok else blocked).append((a, b))
    return keep, blocked


def _fill_by_pitch(bands: Sequence[Tuple[int, int]], pitch: float, length: int,
                   tol: float = DEFAULT_PITCH_TOL, pitch_2: float = 0.0,
                   width_fixed: float = 0.0) -> "_Fill":
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
    got = [(float(a), float(b)) for a, b in bands]
    pitches = [float(p) for p in (pitch, pitch_2) if float(p) >= 2.0]
    fixed = float(width_fixed) if float(width_fixed) > 0 else 0.0
    if not got or length <= 0:
        return _Fill(got, -1.0, 0, False, fixed, "")
    measured = float(np.median([b - a for a, b in got]))
    width = fixed or measured
    if not pitches:
        return _Fill(got, -1.0, 0, False, width, "")

    centres = [(a + b) / 2.0 for a, b in got]
    # 被影像邊界切到的那幾根**量到的中心是偏的**（只露出一半），所以凡是拿
    # 中心當證據的地方都要排除它們。
    inside = [c for (a, b), c in zip(got, centres)
              if a > 0.5 and b < float(length) - 0.5]
    mid = length / 2.0
    anchor = min(centres, key=lambda c: abs(c - mid))

    # 交錯的 pitch 有好幾個「相」，而錨點落在哪一相是看不出來的 ——
    # 每一相都排一次，留最貼合影像的那個。
    scored = []
    for phase in range(len(pitches)):
        cand = [c for c in _walk(anchor, pitches, int(length), phase)
                if c + width / 2.0 > 0 and c - width / 2.0 < length]
        if not cand:
            continue
        d = [min(abs(c - v) for v in cand) for c in centres]
        # **挑相位用平均，判合不合用中位數 —— 兩個問題，兩把尺。**
        # 中位數對「其中一根對不上」是免疫的，而那正是相位錯掉的**唯一**症狀：
        # 實測（間距 24/36、三根線）錯的那個相有一根差 12 px，另外兩根 0，
        # 中位數是 0.000，跟正確的相一模一樣 —— 於是兩個相看起來一樣好。
        # 判「這個 pitch 對不對」時中位數仍然是對的（一根被缺陷撐大的線不該
        # 讓整份 recipe 失效），所以下面的 err 沒有跟著改。
        scored.append((float(np.mean(d)), float(np.median(d)), phase, cand))
    if not scored:
        return _Fill(got, -1.0, 0, False, width, "")
    scored.sort(key=lambda t: t[0])
    best_rank, best_err, _phase, best = scored[0]

    # **相位定不出來就不要定。**（F8 第六輪，使用者回報「y 方向常常錯位」）
    #
    # 「寬、窄、寬、窄」的排法有兩個相，而分辨它們**唯一**的證據是相鄰兩根線
    # 之間的距離 —— 也就是說，至少要有兩根**沒有被邊界切到**的線才問得出來。
    # 少於兩根時兩個相一樣貼合（實測 64px 的 patch 配 40/33：只有一根完整的線，
    # 兩個相的誤差都是 0.00），程式照樣挑一個，然後**把那根看得見的線搬到錯的
    # 位置** —— 實測搬了 33 px，而 pitch_error 回報 0.00。
    #
    # 兩根以上還要分得夠開：贏的那個相要比第二名好上「兩個 pitch 差距」的一定
    # 比例，否則那只是雜訊在決定。差不出來時**退回影像自己量到的**，並講出來 ——
    # 「我分不出來」是一個有用的答案，「我猜一個」不是。
    if len(pitches) > 1:
        spread = abs(pitches[0] - pitches[1])
        if len(inside) < 2:
            return _Fill(got, -1.0, 0, False, width,
                         "two spacings need at least two whole stripes to tell "
                         "them apart, and this patch has %d" % len(inside))
        if len(scored) > 1 and (scored[1][0] - best_rank) < spread * _PHASE_MARGIN:
            return _Fill(got, -1.0, 0, False, width,
                         "cannot tell which of the two spacings comes first "
                         "(they fit equally well here)")

    lat, err = best, best_err
    if err > min(pitches) * float(tol):
        return _Fill(got, err, 0, False, width, "")

    # **相位用整排一起定，不要只靠錨點那一根。** 錨點自己也是量出來的，它的誤差
    # 會原封不動地平移整個晶格；而每一根的量測誤差彼此獨立，取中位數就洗掉了。
    # 實測（1.5 nm/px 配 44 nm 的 pitch = 29.333 px）：最大偏差 0.63 → 0.25 px。
    # 用中位數而不是平均：一根被缺陷撐大的線不該把整排推走。
    # 被影像邊界切到的那幾根**不能參加** —— 它們只露出一半，量到的「中心」
    # 依定義就是偏的，放進來等於用一個已知有偏差的樣本去校正整排。
    if inside:
        shift = float(np.median([c - min(lat, key=lambda v: abs(c - v))
                                 for c in inside]))
        lat = [v + shift for v in lat]
        err = float(np.median([min(abs(c - v) for v in lat) for c in inside]))

    # **保留次像素**，不要在這裡就捨成整數格。pitch 常常除不盡（實例：EBI 的
    # 1.5 nm/px 配 44 nm 的 pitch = 29.333 px），而晶格是一路累加出來的 ——
    # 每算一根就捨一次的話，每一根各自被推掉最多半格，而那半格正是框貼不貼得住
    # 邊界的差別。捨入留到最後做框的時候一次做完（``_clip_span``）。
    #
    # **寬度用每一根自己量到的，只有補出來的那幾根才用中位數。**
    # pitch 講的是「每隔多遠有一根」，它對**線寬**一個字都沒說。早期版本把整排
    # 的寬度統一成中位數，於是線寬本來就有變化的地方（line-width roughness，
    # 而那有時候正是缺陷本身）被抹平 —— 更糟的是框是貼著段的邊界放的，所以在
    # **線寬異常的那一根**上，框會被推進 MG 裡面幾個像素。也就是說：最需要量準
    # 的那一根，量得最髒。
    near = float(min(pitches)) * 0.5
    out: List[Tuple[float, float]] = []
    for c in lat:
        own = min(got, key=lambda b: abs((b[0] + b[1]) / 2.0 - c))
        w = (fixed if fixed else
             ((own[1] - own[0]) if abs((own[0] + own[1]) / 2.0 - c) <= near
              else measured))
        lo = max(0.0, c - w / 2.0)
        hi = min(float(length), c + w / 2.0)
        if hi - lo >= 1.0:
            out.append((lo, hi))
    return _Fill(out, err, max(0, len(out) - len(got)), True, width, "")


def find_stripes(img: Any, axis: str = algo_profile.AXIS_X,
                 select: str = "brightest", sensitivity: float = 0.35,
                 smooth: int = 3, min_gap: int = 4, pitch: float = 0.0,
                 pitch_2: float = 0.0,
                 pitch_tol: float = DEFAULT_PITCH_TOL,
                 kinds: int = 0, width: float = 0.0,
                 fill_rule: str = "skip") -> StripeSet:
    """找出一個方向上的條紋，並挑出要的那一組。

    ``select`` 在這裡而不是在外面，是因為 ``pitch`` 講的是**同一組條紋**的
    週期（MG 每 24px 一根），而不是「所有邊界」的間距 —— 沒有先挑組就沒有
    週期可言（見 :func:`_fill_by_pitch`）。

    ``pitch``（像素，0 = 不知道）給了之後做三件事：
    **驗證**（``pitch_error``：量到的跟給的對不對）、
    **補線**（邊緣只露一半、對比不足而漏掉的那幾根）、
    以及把錨定條件從「要好幾個週期」降成「**要一根條紋**」——
    64px 的 patch 上這是決定性的差別。

    ``kinds``：這個方向上有幾種條紋（見 :func:`select_bands`）。同一個晶格上
    多一種材質（例：CPODE）就加一，0 = 照排名推。

    ``width``（像素，0 = 照量到的）：**線寬改由使用者給定**。

    為什麼要有這個出口 —— 它把一個問題拆成兩個
    ------------------------------------------
    給了線寬之後，這條曲線只剩一件事要做對：**每一根線的中心在哪**。中心是
    整段的重心，比單邊的邊界穩得多（邊界靠梯度的峰，糊掉一點就飄），而
    sensitivity 調的正是邊界。線寬一旦固定，敏感度就從「決定框放在哪」降級成
    「決定有沒有找到這根線」—— 而後者面板上看得出來，前者看不出來。

    什麼時候**不要**給：線寬本身就是要量的東西（line-width roughness，
    而它有時候正是缺陷）。這兩種用法互斥 —— 把線當尺，還是把線當待測物。

    ``fill_rule``：晶格上「該有一根卻沒有」的位置怎麼辦（見 :data:`FILL_RULES`）。
    ``"skip"``（預設）會去看那個位置實際是什麼材質，不對就不放條紋。
    """
    prof, raw = algo_profile.projection(img, axis=axis, smooth=smooth)
    out = StripeSet(axis=str(axis), profile=prof, raw=raw)
    if prof.size == 0:
        return out

    gap = max(1, int(min_gap) or 4)
    rough = list(algo_profile.find_transitions(
        prof, sensitivity=sensitivity, min_gap=gap))
    out.edges = list(rough)                    # 面板畫線用（整數就夠）
    # 段的幾何用**精修過的**位置 —— 差半格會讓框的左右不對稱，見 refine_edges。
    out.edges_sub = refine_edges(prof, rough)
    out.confidence = algo_profile.profile_confidence(prof, raw)
    out.bands = _bands_from(out.edges_sub, int(prof.size))
    out.levels = [float(prof[_half_up(a):_half_up(b)].mean())
                  if _half_up(b) > _half_up(a) else 0.0
                  for a, b in out.bands]

    picked = select_bands(out.bands, out.levels, select, kinds)
    # 量間距只用**沒有被影像邊界切到**的那幾根 —— 只露一半的線量到的中心
    # 依定義就是偏的，而這個數字是要拿去填回參數格的。
    whole = [(a + b) / 2.0 for a, b in picked
             if a > 0.5 and b < float(prof.size) - 0.5]
    centres = sorted(whole if len(whole) >= 3
                     else [(a + b) / 2.0 for a, b in picked])
    out.pitch_measured, out.pitch_measured_2 = measure_pitches(centres)
    out.pitch_used = out.pitch_measured

    given = _pitch_list(pitch, pitch_2)
    fit = _fill_by_pitch(picked, float(pitch), int(prof.size), pitch_tol,
                         float(pitch_2), float(width))
    filled, err, used = list(fit.bands), fit.error, fit.used
    out.pitch_error = err
    out.pitch_note = fit.note
    out.width_used = fit.width
    out.width_fixed = float(width) > 0
    # 晶格沒排（沒給 pitch，或給的跟影像對不上）時線寬照樣要照給的來 ——
    # 這是兩件事：一個講「每隔多遠有一根」，一個講「一根多寬」。
    if out.width_fixed and not used:
        filled = _fixed_width(filled, float(width), int(prof.size))

    # **補出來的位置要對得起影像。** 補線是靠 pitch 推的，而 pitch 對「那裡
    # 是什麼材質」一個字都沒說 —— 站點的 CPODE 正好落在同一個晶格上，於是
    # 「這根線太淡沒抓到」與「這裡根本沒有線」被補成同一件事。
    if used and str(fill_rule) in ("skip", "skip_clear"):
        end = _RANKS.get(_SELECT_ALIASES.get(str(select), str(select)),
                         (None, 0))[0]
        outside = [lv for b, lv in zip(out.bands, out.levels)
                   if b not in picked]
        inside = [lv for b, lv in zip(out.bands, out.levels) if b in picked]
        if end is not None and outside and inside:
            filled, out.blocked = _split_by_material(
                prof, filled, picked, float(np.median(inside)),
                float(np.median(outside)), end == "hi",
                float(min(given)) * 0.5)
            out.clear_neighbours = str(fill_rule) == "skip_clear"

    if used:
        # 兩種間距交錯時，「pitch 是多少」沒有單一答案 —— 報平均（那是實際的
        # 平均間距），完整的一組留在 ``pitches_used`` 給面板與特徵用。
        # ``filled`` 在擋掉之後才數：被擋掉的那幾格不是「補上的」，是「沒補」。
        out.filled = max(0, len(filled) - len(picked))
        out.pitches_used = given
        out.pitch_used = float(np.mean(given))
    out.selected = filled
    # 晶格把每一根搬了多遠 —— 使用者看到的「藍框跟藍線對不齊」就是這個。
    if used and picked:
        found = [(a + b) / 2.0 for a, b in picked]
        moved = [min(abs(c - (a + b) / 2.0) for a, b in filled)
                 for c in found] if filled else []
        out.snap_shift = float(max(moved)) if moved else 0.0
    return out


# --------------------------------------------------------------------------- #
# 交會 → 方框
# --------------------------------------------------------------------------- #
#: 捨入前先吃掉的浮點雜訊（像素）。次像素邊界算出來是 ``20.499997`` 而不是
#: ``20.5`` —— 差在最後幾個 bit，但那決定了捨上還是捨下，**而一根條紋的左右
#: 兩條邊剛好會落在不同邊**：實測左邊的框離 MG 兩格、右邊只有一格。
#: 1e-6 px 沒有任何幾何意義，只是把「數學上是 .5」還原成 .5。
_ROUND_EPS = 1e-6


def _half_up(v: float) -> int:
    """四捨五入，**一律往上**（含浮點雜訊的容差）。

    Python 內建的 ``round()`` 是 banker's rounding：``round(14.5) == 14`` 但
    ``round(15.5) == 16``。次像素邊界精修之後每一條邊都正好落在 ``.5`` 上，
    於是同一個框的左右兩邊會用不同的規則進位 —— 框的寬度時而 5 時而 6，
    而使用者填的是 5。
    """
    return int(math.floor(float(v) + 0.5 + _ROUND_EPS))


def _clip_span(a: float, b: float, limit: int) -> Optional[Tuple[int, int]]:
    lo = _half_up(max(0.0, min(a, b)))
    hi = _half_up(min(float(limit), max(a, b)))
    return (lo, hi) if hi > lo else None


def _spans_between(bands: Sequence[Tuple[float, float]], length: int
                   ) -> List[Tuple[int, int]]:
    """相鄰兩段**之間**的空隙（也就是「沒有被這組條紋蓋到」的地方）。"""
    out: List[Tuple[int, int]] = []
    ordered = sorted(bands)
    for (_, end), (start, _) in zip(ordered, ordered[1:]):
        if start > end:
            span = _clip_span(end, start, length)
            if span:
                out.append(span)
    return out


def _faces_blocked(centre: float, direction: int,
                   bands: Sequence[Tuple[float, float]],
                   blocked: Sequence[Tuple[float, float]]) -> bool:
    """從 ``centre`` 往 ``direction``（-1 左／上，+1 右／下）看過去，
    最近的東西是不是一個**被擋掉的**晶格位置。

    為什麼不是「離某個被擋掉的位置多近」
    ------------------------------------
    距離門檻要嘛跟 pitch 綁死（那就多一個要調的數字），要嘛在 pitch 變動時
    失效。「往那個方向看，先碰到誰」不需要任何門檻，而且正好就是使用者要問的
    那件事 —— 這個框的對面是不是那個不該量的東西。
    """
    def nearest(items: Sequence[Tuple[float, float]]) -> Optional[float]:
        cand = [(a + b) / 2.0 for a, b in items
                if ((a + b) / 2.0 - centre) * direction > 0.5]
        return min(cand, key=lambda c: abs(c - centre)) if cand else None

    bad = nearest(blocked)
    if bad is None:
        return False
    kept = nearest(bands)
    return kept is None or abs(bad - centre) < abs(kept - centre)


def _edge_spans(bands: Sequence[Tuple[int, int]], width: float, side: str,
                gap: float, length: int,
                blocked: Sequence[Tuple[float, float]] = ()
                ) -> List[Tuple[int, int]]:
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
        a, b = float(band[0]), float(band[1])
        centre = (a + b) / 2.0
        wanted = []
        # 面向被擋掉的那一格的框不做 —— 它量到的那一小條 EPI 的對面不是 MG，
        # 而「MG 旁邊的 EPI」跟「CPODE 旁邊的 EPI」不是同一個東西。
        if (str(side) in ("both", "start")
                and not _faces_blocked(centre, -1, bands, blocked)):
            wanted.append((a - g - w, a - g))
        if (str(side) in ("both", "end")
                and not _faces_blocked(centre, +1, bands, blocked)):
            wanted.append((b + g, b + g + w))
        for lo, hi in wanted:
            span = _clip_span(lo, hi, length)
            # **切到影像邊緣而窄掉的丟掉。** 這幾個框的意義是「同一種東西的
            # 同一種取樣」，一個只有六成寬的殘框戴著同一個名字進 mask，
            # 統計上是稀釋，畫面上是那一排框裡突然有一個比較短 —— 兩種都是
            # 在說謊。沒切到的時候寬度一定剛好等於使用者填的值（兩端用同一個
            # 捨入規則、相差整數個 w），所以這一關只會擋到真的被切掉的。
            if span and (span[1] - span[0]) >= w - 0.5:
                out.append(span)
    return out


def _spans_for(placement: str, axis: str, bands: Sequence[Tuple[int, int]],
               box_size: float, side: str, gap: float, inset: float,
               length: int, blocked: Sequence[Tuple[float, float]] = ()
               ) -> List[Tuple[int, int]]:
    """這一軸貢獻哪些區間 —— 依 ``placement`` 決定它是被貼住的還是當界線的。"""
    place, ax = str(placement), str(axis)
    if place == "beside_%s" % ax:
        return _edge_spans(bands, box_size, side, gap, length, blocked)
    if place == "between_%s" % ax:
        return [s for s in (_clip_span(a + gap, b - gap, length)
                            for a, b in _spans_between(bands, length))
                if s is not None]
    # 這一軸只是界線 —— 用整段，並往內縮 inset 避開它自己的邊界
    pad = max(0.0, float(inset))
    out = []
    for a, b in bands:
        span = _clip_span(float(a) + pad, float(b) - pad, length)
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

    x_spans = _spans_for(placement, "vertical", xb, box_size, side, gap, inset,
                         w, x.blocked if x.clear_neighbours else ())
    y_spans = _spans_for(placement, "horizontal", yb, box_size, side, gap,
                         inset, h, y.blocked if y.clear_neighbours else ())

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
                     vertical_kinds: int = 0, horizontal_kinds: int = 0,
                     vertical_width: float = 0.0,
                     horizontal_width: float = 0.0,
                     fill_rule: str = "skip",
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
                      pitch_2=vertical_pitch_2, kinds=vertical_kinds,
                      width=vertical_width, fill_rule=fill_rule)
    ys = find_stripes(img, axis=algo_profile.AXIS_Y, select=horizontal_select,
                      sensitivity=horizontal_sensitivity, smooth=smooth,
                      min_gap=min_gap, pitch=horizontal_pitch,
                      pitch_2=horizontal_pitch_2, kinds=horizontal_kinds,
                      width=horizontal_width, fill_rule=fill_rule)

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
