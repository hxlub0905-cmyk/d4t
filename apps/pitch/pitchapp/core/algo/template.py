# d4t algorithm library — authored 2026-07-29 (F7-12).
"""Golden Cell 模板定位：從大圖疊出一個週期，再把每張 patch 對回那個週期。

為什麼要從大圖疊
----------------
patch 通常**比一個重複單元還小**，所以每張 patch 看到的只是週期裡的一小片，
不同 defect 落在不同相位 —— 拿這些小片互相對位，其實沒有共同的東西可以對。

但 patch 是從 EBI 機台吐出的**大圖**上裁下來的，而大圖裡看得到好幾個週期。
所以順序反過來：先在大圖上量週期、疊出一個乾淨的 Golden Cell（GC），
再把小 patch **滑進**這個比它大的模板裡找位置。這是有唯一解的問題，
而「小片互相對位」不是。

週期也因此不必請使用者填 —— 大圖上量得到。

原點必須錨在看得見的地標（這條最容易被忽略）
--------------------------------------------
疊 GC 之前要決定「一個週期從哪裡開始」。``period.choose_origin`` 挑的是
**讓疊出來最銳利**的相位 —— 但對一張週期性影像來說，任何相位疊出來都一樣銳利，
所以它在數個幾乎等價的候選之間選哪一個，實務上是任意的。

後果很嚴重而且很安靜：換一批資料重算 GC，相位一變，**使用者標在 GC 上的框就
跟著平移了**，而畫面上不會有任何錯誤訊息 —— 框還在、數字還有，只是量錯地方。

所以 :func:`build_golden_cell` 疊完之後會再**捲動**一次，把「最強的上升邊」
（暗→亮的轉折）擺到第 0 欄。那是影像上認得出來的同一個物理特徵，
換一批資料仍然指向同一個地方。用**上升**邊而不是「最強的邊」是因為一個週期裡
通常有一對方向相反的邊，強度相近時「最強」會在兩者之間跳。

比對用 NCC
----------
大圖與 patch 是不同時間、不同增益拍的，整體亮度不會一樣。
``cv2.TM_CCOEFF_NORMED`` 對線性的亮度／對比變化免疫，直接比灰階差則會被
亮度差主導。

「定得出來嗎」要過三關
----------------------
比對一定會回一個「最像的位置」，就算那張 patch 根本沒有特徵。所以三關都要過：

1. **這張 patch 上有結構嗎**（``patch_structure``）。這一關做的是最重的工，
   而且它是唯一問對問題的一關 —— 沒有結構就是定不出來，跟門檻調得多好無關。
2. **分數**（NCC 的最高值）。
3. **峰有多突出**（最高分與次高分的差，摺回一個週期之後才比）。

只靠 2、3 是不夠的，實測過：一張純雜訊的 32 寬 patch 收窄成曲線之後，跟模板的
隨機相關標準差大約 ``1/√32 ≈ 0.18``，**靠運氣就拿得到 0.5 的分數**。門檻拉高
只是把問題推遲 —— 真實資料的分數本來就比合成的低，拉高會開始殺掉真的。

實測的分佈（合成資料，20 個雜訊種子）：
有結構的 structure 38–86、margin 0.36–0.60；均勻的 structure 0.5–1.2、
margin 0.01–0.24。**structure 這一關差了一個數量級**，另外兩關會重疊。
"""
from __future__ import annotations
from pitchapp.core.log import swallowed

import base64
import math
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import golden as algo_golden
from . import period as algo_period
from . import period2d as algo_period2d

__all__ = [
    "GoldenCell", "MatchResult", "MeasuredPeriod", "measure_period",
    "build_golden_cell", "anchor_cell",
    "encode_cell", "decode_cell", "tile_cell", "match_patch",
    "patch_structure", "period_text", "MIN_PERIOD_CONFIDENCE", "SNAP_DRIFT_PX",
    "CELL_ENCODING",
]

#: 模板在 recipe 裡的編碼：``"gc1:<w>x<h>:<base64(zlib(raw uint8))>"``。
#:
#: 為什麼是 base64 而不是外部檔案：recipe 必須是**一個可以寄給別人的純文字檔**。
#: 存路徑的話，圖被搬走、被換掉、下個月用了另一張大圖，結果會安靜地變。
#: base64 是 ASCII，所以 repo 與 recipe 的「只有純文字」不變量仍然成立
#: （公司機的 DLP 擋的是二進位壓縮檔，見 docs/HANDOVER.md §5）。
#: 先過 zlib：SEM 的 cell 有雜訊、壓不了太多（實測約剩七成），
#: 但一個週期本來就小，這個大小塞進 recipe JSON 完全沒問題。
CELL_ENCODING = "gc2"

#: 「這個 cell 自己重複幾次」的判準：把 cell 捲動 1/k 之後跟自己的 NCC。
#: 實測（合成資料）：真的自週期 0.995–0.998，其餘的除數 ≤ 0.75 —— 中間的空隙
#: 很大，門檻放 0.9 兩邊都安全。
SELF_PERIOD_NCC = 0.9

#: 真的週期與「這一軸是平的」要分得開：捲半個週期至少要掉這麼多 NCC。
#: 實測 0.998 vs 0.52（差 0.48）對上平軸的 ≈ 0（兩個都 ≈ 1）。
SELF_PERIOD_MARGIN = 0.15

#: 自週期最多找到 1/k 為止。使用者手動放大的 cell 是 2×、3× 這種量級 ——
#: 往下找到 1/32 只會開始撿到雜訊。
MAX_SELF_REPEAT = 8

#: 一軸上的週期信心要多少才算數（``period.estimate_period`` 的 0–100 分）。
#: 實測：純雜訊約 20，真的有週期的約 87 —— 門檻放中間兩邊都安全。
#: 呼叫端自己指定 ``px``/``py`` 時不套用（那是使用者明說的，不是猜的）。
MIN_PERIOD_CONFIDENCE = 40.0

#: 量到的週期離整數很近時回整數 —— 判準是**漂移**不是絕對值（F105）：
#: ``|p − round(p)| × 這一軸有幾格 ≤ 0.5 px`` 才 snap。「snap 不會讓任何一格移超過
#: 半個像素」是讀者驗得了的一句；絕對門檻 0.1 px 在 78 格上會漂 7.8 px，正是 F105
#: 要拿掉的那種。合成 fixture（8–12 格、鏈誤差 ~0.01）都 snap，所以整數 pitch 的
#: 影像走的每一個 byte 都跟 F104 一樣；真實大圖 79.5 × 50 列 = 25 px 不 snap。
SNAP_DRIFT_PX = 0.5


@dataclass
class GoldenCell:
    """從大圖疊出來的一個週期，以及疊得好不好的證據。"""

    cell: np.ndarray                    # (py, px) uint8
    px: int
    py: int
    #: 疊完那張圖有多**銳利**，0–100。
    #:
    #: ⚠ **它不是「疊得多準」**（F40 改掉了這句話）。它只看疊完的那一張圖，
    #: 看不到疊進去的那幾格，所以分不出「因為對齊了所以銳利」與「因為兩個
    #: 鬼影各帶一組邊所以銳利」；而且它跟著對比、雜訊、格子大小一起動 ——
    #: 純雜訊在 σ=60 拿 99.4。**只能拿來比同一張圖的兩個 stack，不准跟固定
    #: 門檻比。** 要問「疊得準不準」看 :attr:`agreement`。
    ghosting: float = 0.0
    lap_var: float = 0.0                # 未飽和的原始值（要比較大小時用這個）
    #: 那幾格**彼此**對得多齊，0–1（`golden.stack_agreement`，F40）。
    #: 無量綱、跨影像可比，所以**這一個**才是拿去跟門檻比的那個。
    agreement: float = 0.0
    confidence_x: float = 0.0
    confidence_y: float = 0.0
    anchor: Tuple[int, int] = (0, 0)    # 為了錨定地標捲動了多少
    n_cells: int = 0
    #: 格線的原點（影像像素，``0 <= ox < px``），**已經把錨定的捲動算進去**：
    #: 從 ``origin`` 起每 ``px``／``py`` 一格，格子裡的東西就是 ``cell``。
    #: 「把 cell 鋪回原圖」（F103 的格線檢視）與「使用者標的那一格就是原點」
    #: 都靠它；沒有它，畫面上鋪的格線跟疊進去的格子會差一個錨定量。
    #: 小數週期時它是**原圖座標的小數**（F105）；整數 pitch 時仍是整數。
    origin: Tuple[float, float] = (0, 0)
    #: 這一軸上真的量到週期了嗎。**一維的 layout 是常態**（垂直條紋只有 X 有
    #: 週期），那時候另一軸不做定位 —— 它上面沒有東西可以定位。
    periodic_x: bool = True
    periodic_y: bool = True
    warnings: List[str] = field(default_factory=list)
    #: **真正的**週期，可以是小數（F105：79.5 對 79 在 4000 px 上差 25 px）。
    #: ``px``／``py`` 仍然是 cell 陣列的尺寸（= round）；整數 pitch 時兩者相等。
    #: 格線檢視、Cell W／H 那兩格、摘要都要讀這一組，不是 ``px``／``py``。
    period_x: float = 0.0
    period_y: float = 0.0
    #: 交錯分數 ``ac[q/2, p/2] / ac[q, p]``：交錯（body-centred）≈ 1、規則晶格 ≈ 0。
    stagger: float = 0.0
    #: 半週期檢查有沒有把那一軸加倍（`period2d.half_period_check`）。
    doubled: Tuple[bool, bool] = (False, False)
    #: 量週期時自動做的**決定**（換了量法、加倍了）—— 每一句都要讓使用者看到
    #: （`ui/template_dialog.summary`）。它們同時也在 ``warnings`` 裡（F104 的相容）。
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # 位置參數建出來的舊呼叫（`GoldenCell(cell=…, px=8, py=8)`）沒給週期：
        # 那就是整數 pitch，週期 = 陣列尺寸。
        if self.period_x <= 0.0:
            self.period_x = float(self.px)
        if self.period_y <= 0.0:
            self.period_y = float(self.py)

    @property
    def shape(self) -> Tuple[int, int]:
        return (int(self.py), int(self.px))

    @property
    def periodic(self) -> Tuple[bool, bool]:
        return (bool(self.periodic_x), bool(self.periodic_y))


@dataclass
class MatchResult:
    """一張 patch 對回 GC 的結果。"""

    phase_x: int = 0                    # patch 左上角落在 cell 的哪一格
    phase_y: int = 0
    score: float = 0.0                  # 最高的 NCC 分數（-1..1）
    margin: float = 0.0                 # 最高分與鄰域外次高分的差 = 峰有多突出
    structure: float = 0.0              # 這張 patch 自己有沒有結構（見 patch_structure）
    ok: bool = False


def _gray_u8(img: Any) -> np.ndarray:
    a = np.asarray(img)
    if a.ndim == 3:
        a = a.mean(axis=2)
    f = a.astype(np.float32)
    if f.size == 0:
        return np.zeros((0, 0), np.uint8)
    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(f.shape, np.uint8)
    if lo >= -0.5 and hi <= 255.5:
        return np.clip(f, 0, 255).astype(np.uint8)
    return np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# 原點錨定
# --------------------------------------------------------------------------- #
def _rising_edge_index(profile: np.ndarray) -> Optional[int]:
    """一條週期性曲線上「最強的上升邊」在哪（找不到明確的邊回 None）。

    用 ``np.gradient`` 的**最大正值**。取正值而不是絕對值，是因為一個週期裡
    通常有一對方向相反的邊，強度相近時「最強的邊」會在兩者之間跳 ——
    而那正是我們要避免的那種安靜的漂移。
    """
    p = np.asarray(profile, dtype=np.float32)
    if p.size < 3:
        return None
    # 週期性訊號要用環狀梯度，否則兩端的邊會被截掉
    grad = np.roll(p, -1) - np.roll(p, 1)
    peak = float(grad.max())
    if peak <= 0.0:
        return None
    # 上升邊要真的比一般的地方陡，否則這條曲線上沒有邊（同 algo/profile.py）
    if peak < 1.2 * float(np.median(np.abs(grad)) or 1e-9):
        return None
    return int(np.argmax(grad))


def anchor_cell(cell: np.ndarray,
                axes: Tuple[bool, bool] = (True, True),
                ) -> Tuple[np.ndarray, Tuple[int, int]]:
    """把 GC 捲動到「最強的上升邊在第 0 欄／第 0 列」。回傳 ``(cell, (dx, dy))``。

    捲動用 ``np.roll`` —— 對一個週期來說捲動是無損的（它本來就是環狀的）。

    某一軸上沒有明確的邊時**那一軸不動**：硬要錨一個不存在的地標，
    等於用雜訊決定相位，比不錨還糟。
    """
    a = np.asarray(cell)
    if a.ndim != 2 or a.size == 0:
        return a, (0, 0)
    dx = _rising_edge_index(a.mean(axis=0)) if axes[0] else None
    dy = _rising_edge_index(a.mean(axis=1)) if axes[1] else None
    out = a
    if dx:
        out = np.roll(out, -int(dx), axis=1)
    if dy:
        out = np.roll(out, -int(dy), axis=0)
    return out, (int(dx or 0), int(dy or 0))


# --------------------------------------------------------------------------- #
# 建模板
# --------------------------------------------------------------------------- #
@dataclass
class MeasuredPeriod:
    """`measure_period` 的答案：兩軸的週期（可以是小數）、信心、講給人聽的決定。"""

    px: float = 0.0
    py: float = 0.0
    conf_x: float = 0.0
    conf_y: float = 0.0
    notes: List[str] = field(default_factory=list)
    stagger: float = 0.0
    doubled: Tuple[bool, bool] = (False, False)

    # ---- 三票各自的答案（F120，2026-09-21）--------------------------------
    #
    # 使用者：「我可以看到每個方法的分數嗎？（顯示細節）」
    #
    # 它們本來就**算出來了，然後被丟掉** —— 只有仲裁完的那一組活下來。而
    # 三票不一致正是「這張圖有點特別」的信號：投影法看到 30、二維看到 60，
    # 答案是 60，而「投影法看到 30」是關於這個 layout 的一個**事實**
    # （相鄰列交錯），不是雜訊。留下來給畫面上的 Details 用。
    #
    # ⚠ **全部選填、全部有預設值。** 這個 dataclass 不進 recipe、不進 feature、
    # 不進黃金值，所以加欄位不會動到任何一個數字 —— 但它有第二個呼叫者
    # （`build_golden_cell`），而那一支只讀 px/py/conf/notes/stagger/doubled。
    #: 投影法（`period.estimate_period`）自己的答案。``None`` ＝ 那一軸沒找到。
    proj_px: Optional[float] = None
    proj_py: Optional[float] = None
    proj_conf_x: float = 0.0
    proj_conf_y: float = 0.0
    #: 二維自相關（`period2d.estimate_period_2d`）自己的答案（次像素）。
    ac_px: Optional[float] = None
    ac_py: Optional[float] = None
    ac_conf_x: float = 0.0
    ac_conf_y: float = 0.0
    #: 半週期檢查的增益（`ac[2q] - ac[q]`，正得夠多就加倍）。
    half_gain_x: float = 0.0
    half_gain_y: float = 0.0
    #: 諧波上的其他可能（`estimate_period` 本來就會算）—— 「取錯怎麼辦」的答案。
    candidates: List[Tuple[Optional[int], Optional[int]]] = field(
        default_factory=list)


def period_text(px: float, py: float) -> str:
    """``"40 x 240"`` 或 ``"41 x 79.5"``（``%d`` 對小數會安靜截斷，所以要有這一支）。"""
    return "%s x %s" % (algo_period2d.fmt_px(px), algo_period2d.fmt_px(py))


def _snap(p: float, span: int) -> float:
    """離整數近到整張影像漂不到 ``SNAP_DRIFT_PX`` 就回整數（見常數說明）。"""
    p = float(p)
    r = float(round(p))
    if p < 1.0 or r < 1.0:
        return p
    cells = float(span) / p
    return r if abs(p - r) * cells <= SNAP_DRIFT_PX else p


def measure_period(gray: np.ndarray,
                   given: Tuple[bool, bool] = (False, False)) -> MeasuredPeriod:
    """三種量法對一次 → :class:`MeasuredPeriod`（0 ＝ 那一軸量不到）。

    ⚠ **這一支是「這張圖的 cell period 是多少」的唯一出處**，所以它是公開的
    （F120，2026-09-21 從 ``_measure_period`` 改名）。`build_golden_cell` 疊模板
    之前問它，`ui/pitch_helper.py`（丟一張圖進去只問那個數字）也問它 —— 第二個
    呼叫者出現的那一天，選擇只有「開放這一支」與「抄一份三票制出去」，
    而後者一定會漂（`CLAUDE.md` §0）。改名**沒有留舊名字的別名**：一件事兩個
    名字正是那一節在擋的東西。

    投影法（`period.estimate_period`）是主：四個月的實測與諧波修正都在它身上。
    二維自相關（`period2d.estimate_period_2d`，F104）在兩種情況接手，
    **兩個同意的時候整數不改**（黃金值不動）：

    * 投影法那一軸量不到（信心不夠）、二維量得到 —— 交錯 layout 的 X 軸就是這樣
      （相鄰列相位差半格，投影互相抵消）；
    * 二維量到的是投影法的**整數倍**（±1 px）—— 投影看到的是半格的重複，
      真正的矩形單元要兩列才重複一次。

    F105 加的三件事：

    * **次像素**：採用二維的軸拿它的諧波鏈擬合值；兩者同意的軸也拿它當小數修正
      （投影法只出整數）。離整數近到整張圖漂不到半個像素就 snap 回整數（`_snap`）。
    * **第三票**（`period2d.half_period_check`）：仲裁完的答案是不是真週期的一半 ——
      投影法在交錯晶格上一定回半週期，而它自己的加倍規則在那裡永遠不會觸發。
      ``given`` 標的軸（使用者明講的）不看。
    * **交錯分數**進答案（一個可以畫分布的數字），加倍與否也進答案。

    每一次接手或加倍都在 notes 講一句：換了量法、改了數字是使用者該知道的事。

    ⚠ **空的／小到沒有意義的影像回一個空答案，不丟例外**（F120）。它私有的
    時候這一關不必在這裡 —— 唯一的呼叫者 `build_golden_cell` 更早就擋掉了。
    公開之後呼叫端是「使用者剛剛丟進來的那個東西」，而 `cv2.Sobel` 對 0×0
    的陣列是 `cv2.error`。**開放一支函式就要讓它自己站得住**，不是要求每一個
    新呼叫者都記得先擋一次。這一關擋掉的路 `build_golden_cell` 走不到，
    所以任何一份跑得動的 recipe 算出來的數字**一個 byte 都沒有變**。
    """
    g = np.asarray(gray)
    if g.ndim != 2 or g.size == 0 or min(g.shape) < 4:
        return MeasuredPeriod(notes=["the image is too small to look for a repeat"])
    est = algo_period.estimate_period(gray)
    two = algo_period2d.estimate_period_2d(gray)
    notes: List[str] = list(est.warnings or [])
    if two.px is not None or two.py is not None:
        notes.extend(two.warnings or [])       # 鏈不直那一句；「都量不到」由呼叫端講
    h, w = gray.shape[:2]
    out: List[Tuple[float, float]] = []
    for axis, span, p1, c1, p2, p2s, c2 in (
            ("across", w, est.px, est.confidence_x, two.px, two.px_sub, two.confidence_x),
            ("down", h, est.py, est.confidence_y, two.py, two.py_sub, two.confidence_y)):
        p1i, c1f = int(p1 or 0), float(c1 or 0.0)
        p2i, c2f = int(p2 or 0), float(c2 or 0.0)
        # 先 snap 再講：notes 裡的數字要跟最後用的那個一樣（48.01 → 48）。
        p2f = _snap(float(p2s), span) if p2s else float(p2i)
        ok1 = p1i >= 2 and c1f >= MIN_PERIOD_CONFIDENCE
        ok2 = p2i >= 2 and c2f >= MIN_PERIOD_CONFIDENCE
        if ok2 and not ok1:
            out.append((p2f, c2f))
            notes.append("period %s measured by 2-D autocorrelation (%s px); "
                         "the projection found none - rows are probably "
                         "staggered" % (axis, algo_period2d.fmt_px(p2f)))
        elif ok2 and ok1 and p2i > p1i + 1 and \
                min(abs(p2i - k * p1i) for k in range(2, 9)) <= 1:
            out.append((p2f, c2f))
            notes.append("the projection saw a repeat every %d px %s, but the "
                         "layout only repeats every %s px (staggered rows); "
                         "using %s" % (p1i, axis, algo_period2d.fmt_px(p2f),
                                       algo_period2d.fmt_px(p2f)))
        elif ok2 and ok1 and abs(p2i - p1i) <= 1:
            out.append((p2f, c1f))             # 同意：整數不變，小數從諧波鏈來
        else:
            out.append((float(p1i), c1f))
    (px, cx), (py, cy) = out
    hp = algo_period2d.half_period_check(gray, px, py, ac=two.ac, skip=given)
    fx, fy = _snap(hp.px, w), _snap(hp.py, h)
    # 加倍那一句自己寫（不用 `hp.notes`）：數字要是 snap 之後真的用的那個。
    for axis, was, doubled, now in (("across", px, hp.doubled_x, fx),
                                    ("down", py, hp.doubled_y, fy)):
        if doubled:
            notes.append("the period %s was doubled after the half-period check "
                         "(%s → %s px); rows are probably staggered"
                         % (axis, algo_period2d.fmt_px(was), algo_period2d.fmt_px(now)))
    return MeasuredPeriod(
        px=fx, py=fy, conf_x=cx, conf_y=cy,
        notes=notes, stagger=float(hp.stagger),
        doubled=(bool(hp.doubled_x), bool(hp.doubled_y)),
        # 三票各自的答案（見 `MeasuredPeriod` 那幾個欄位的說明）。
        proj_px=(float(est.px) if est.px else None),
        proj_py=(float(est.py) if est.py else None),
        proj_conf_x=float(est.confidence_x or 0.0),
        proj_conf_y=float(est.confidence_y or 0.0),
        ac_px=(float(two.px_sub) if two.px_sub else
               (float(two.px) if two.px else None)),
        ac_py=(float(two.py_sub) if two.py_sub else
               (float(two.py) if two.py else None)),
        ac_conf_x=float(two.confidence_x or 0.0),
        ac_conf_y=float(two.confidence_y or 0.0),
        half_gain_x=float(hp.gain_x or 0.0),
        half_gain_y=float(hp.gain_y or 0.0),
        candidates=list(est.candidates or []))


def build_golden_cell(image: Any, px: Optional[float] = None,
                      py: Optional[float] = None, method: str = "mean",
                      anchor: bool = True,
                      progress: Optional[Callable[[str, int, int], Any]] = None
                      ) -> GoldenCell:
    """從大圖疊出一個 Golden Cell。

    ``px`` / ``py`` 留空就從影像自己量（``period.estimate_period`` 投影法，再拿
    ``period2d.estimate_period_2d`` 二維自相關對一次 —— 見 :func:`measure_period`）。
    量不到週期時回一個空的 cell 並在 ``warnings`` 說明 —— 不猜。

    小數週期（F105）
    ----------------
    週期可以是 79.5。疊圖的做法是**把影像重採樣一次成整數 pitch**（``cv2.resize``
    雙線性，80/79.5 = 1.0063 倍），然後 `choose_origin`／`stack_cells`／
    `stack_agreement` 在那張圖上**照整數的程式碼跑**：一條路徑、F86 的
    「逐位元組相同」照守、相位搜尋的成本不變（自寫一個 remap 的小數疊圖器要
    281 次 × 0.12 s ≈ 35 s，比今天慢十倍，而 `period.choose_origin` 的說明
    明白寫過為了速度改搜尋答案的代價）。整數 pitch 時 ``resize`` 根本不叫，
    每一個 byte 都跟以前一樣。

    出來的 ``cell`` 是 round(週期) 個像素寬、代表一個真的週期；``period_x``／
    ``period_y`` 記真的週期，``origin`` 換回**原圖座標**（``x = x' / s``，
    格子的左上邊），格線檢視就是靠它們不滑。

    ``progress``（F86，2026-09-07）
    ------------------------------
    ``fn(stage, done, total)``，``stage`` 是給人看的一句話。回 ``False``
    就**取消**：這一支會盡快回一個空的 cell（``warnings`` 說是取消的）。

    為什麼需要它：這一支在 7680×7680 上要十幾秒，而呼叫它的
    `ui/template_dialog.load_image` 跑在 UI 執行緒上 —— 沒有回報的話那段時間
    視窗是死的（Windows 會標「沒有回應」）。**core 不得 import Qt**（鐵則 1），
    所以這裡給的是一個 callback，畫面長什麼樣由 UI 決定。
    """
    def _say(stage: str, done: int, total: int) -> bool:
        return progress is None or progress(stage, done, total) is not False

    cancelled = GoldenCell(cell=np.zeros((0, 0), np.uint8), px=0, py=0,
                           warnings=["cancelled"])
    gray = _gray_u8(image)
    warnings: List[str] = []
    if gray.size == 0:
        return GoldenCell(cell=np.zeros((0, 0), np.uint8), px=0, py=0,
                          warnings=["the image is empty"])

    # 使用者自己指定的週期一律相信（信心檢查只針對「量出來的」那一軸）
    given_x, given_y = px is not None, py is not None
    conf_x = 100.0 if given_x else 0.0
    conf_y = 100.0 if given_y else 0.0
    notes: List[str] = []
    stagger, doubled = 0.0, (False, False)
    if not (given_x and given_y):
        if not _say("Measuring the period\u2026", 0, 1):
            return cancelled
        m = measure_period(gray, given=(given_x, given_y))
        if not given_x:
            px, conf_x = m.px, m.conf_x
        if not given_y:
            py, conf_y = m.py, m.conf_y
        notes, stagger, doubled = list(m.notes), m.stagger, m.doubled
        warnings.extend(notes)

    px, py = float(px or 0.0), float(py or 0.0)
    h, w = gray.shape[:2]
    # 一維的 layout 是常態：垂直條紋只有 X 有週期，Y 上量不到東西**是正確的**。
    # 那一軸就取整張影像的長度當「一格」——反正它上面沒有相位可言。
    #
    # 但「量到一個數字」不等於「真的有週期」：純雜訊也會被找出一個假週期
    # （實測 confidence 20 上下，而真的有週期的是 87）。所以信心不夠的那一軸
    # 一律當成沒有週期 —— 拿假週期疊出來的模板會糊掉，而糊掉的模板會讓後面
    # 每一顆都對錯。
    periodic_x = px >= 2 and conf_x >= MIN_PERIOD_CONFIDENCE
    periodic_y = py >= 2 and conf_y >= MIN_PERIOD_CONFIDENCE
    if not periodic_x and not periodic_y:
        return GoldenCell(cell=np.zeros((0, 0), np.uint8),
                          px=int(round(px)), py=int(round(py)),
                          confidence_x=conf_x, confidence_y=conf_y,
                          periodic_x=False, periodic_y=False,
                          warnings=warnings + [
                              "no repeating period could be measured in this "
                              "image; a Golden Cell needs a periodic layout"],
                          period_x=px, period_y=py, notes=notes)
    if not periodic_x:
        px = float(w)
        warnings.append("no period across the image; the cell spans the full "
                        "width and no region is located along that direction")
    if not periodic_y:
        py = float(h)
        warnings.append("no period down the image; the cell spans the full "
                        "height and no region is located along that direction")

    # 小數週期 → 重採樣成整數 pitch（見 docstring）。整數時 `work is gray`。
    ix, iy = int(round(px)), int(round(py))
    sx, sy = ix / px, iy / py
    fractional = not (px.is_integer() and py.is_integer())
    work = gray
    if fractional:
        work = cv2.resize(gray, (int(round(w * sx)), int(round(h * sy))),
                          interpolation=cv2.INTER_LINEAR)

    # **相位搜尋是這一支的全部成本**（281 個候選 × 整張圖）—— 進度就報它。
    stop = [False]

    def _phase(done: int, total: int) -> bool:
        if not _say("Finding the phase\u2026", done, total):
            stop[0] = True
            return False
        return True

    origin = algo_period.choose_origin(work.shape, ix, iy, image=work,
                                       progress=_phase)
    if stop[0]:
        return cancelled
    cell = algo_golden.stack_cells(work, ix, iy, method=method, origin=origin)
    n_cells = len(algo_golden.tile_coords(work.shape, ix, iy, origin))

    roll = (0, 0)
    if anchor:
        cell, roll = anchor_cell(cell, axes=(periodic_x, periodic_y))
        if roll == (0, 0) and (periodic_x or periodic_y):
            # 沒有地標可錨 -> 相位是任意的 -> 換一批資料框會平移。
            # 這是**必須說出來**的事，不是可以吞掉的細節。
            warnings.append(
                "no clear landmark to anchor the cell on; the phase of this "
                "Golden Cell is arbitrary, so a region marked on it may shift "
                "if the cell is rebuilt from different data")

    score, lap_var, _edge = algo_golden.ghosting_score(cell)
    # ⚠ **一致性要用原圖算，不是用疊完的那一張**（F40）：問的是「那幾格彼此
    # 對得齊嗎」，而疊完之後那幾格已經不在了。用 `choose_origin` 挑的那個
    # origin —— 也就是真正被疊起來的那一組格子；`anchor_cell` 之後的捲動是
    # 整張一起移，不影響格子之間的一致性。
    agreement = algo_golden.stack_agreement(work, ix, iy, origin=origin)
    # 錨定把 cell 往左（上）捲了 roll，等於格線原點往右（下）移 roll。
    eff_i = ((int(origin[0]) + int(roll[0])) % max(1, ix),
             (int(origin[1]) + int(roll[1])) % max(1, iy))
    eff: Tuple[float, float] = eff_i
    if fractional:
        # 重採樣座標 → 原圖座標。格線畫的是格子的**左上邊**，所以用像素邊的對應
        # ``x = x' / s``（不是像素中心的 ``(x'+0.5)/s − 0.5``：那會把原點 0 換成
        # −0.003，再 mod 週期就繞成 79.499 —— 整整少畫一列格子）。
        eff = ((eff_i[0] / sx) % px, (eff_i[1] / sy) % py)
    return GoldenCell(cell=cell, px=ix, py=iy, ghosting=float(score),
                      lap_var=float(lap_var), agreement=float(agreement),
                      confidence_x=conf_x,
                      confidence_y=conf_y, anchor=roll, n_cells=int(n_cells),
                      periodic_x=periodic_x, periodic_y=periodic_y,
                      warnings=warnings, origin=eff,
                      period_x=px, period_y=py, stagger=float(stagger),
                      doubled=doubled, notes=notes)


# --------------------------------------------------------------------------- #
# 存進 recipe（純文字）
# --------------------------------------------------------------------------- #
def _roll_ncc(cell: np.ndarray, shift: int, axis: int) -> float:
    """把 cell 捲動 ``shift`` 之後跟自己有多像（NCC，對亮度變化免疫）。"""
    a = cell.astype(np.float64).ravel()
    b = np.roll(cell, shift, axis=axis).astype(np.float64).ravel()
    a = a - a.mean()
    b = b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den else 0.0


def cell_self_period(cell: Any) -> Tuple[int, int]:
    """這個 cell **自己**重複的單元有多大 ``(sx, sy)``（不重複就回 cell 尺寸）。

    為什麼需要它（使用者 2026-08-18）
    ---------------------------------
    使用者可以把 cell 取成量到的週期的 2×（「有時候會需要 2X 大 cell」）。那時候
    影像其實仍然以 1× 重複，於是 :func:`match_patch` 的相關面**摺回一個 cell**
    之後，一個週期裡有兩個一模一樣的峰 —— 最高 ＝ 次高 → ``margin`` 歸零。
    實測：1× 的 cell margin 0.37–0.61，2× 與 3× 都是 **0.000**，而 score 仍然
    1.00。比對是完美的，它只是**不唯一**，但預設 ``min_margin`` 會把每一顆都
    判成定不出來。

    為什麼是「驗證除數」而不是「估週期」
    ------------------------------------
    拿 ``period.estimate_period`` 量這個 cell 會得到**假的**答案：實測那張
    MG/EPI 的 cell 回 20 px，因為兩條亮邊剛好間隔 20 —— 但圖案在 20 px 上並不
    重複（中間一段是 MG、另一段是 EPI）。估週期看的是「哪個間距有起伏」，
    而這裡要問的是**捲過去之後整張圖對不對得起來**，那是一個可以直接驗的問題。

    所以只試 ``1/k``（k = 2…8，且要整除），取通過的最小單元。實測分得很開：
    真的自週期 NCC 0.995–0.998，其餘除數 ≤ 0.75。

    ⚠ **平的那一軸對任何位移都相似**，而那不是週期。一維 layout 的 Y 軸就是平的
    （cell 高 = 整張影像），第一版因此回報「自週期 30 px」—— 一個純粹的假答案。
    所以還要過一關：捲動**半個**候選週期必須明顯**不**像。真的週期分得開
    （實測 0.998 vs 0.52），平的軸分不開（兩個都 ≈ 1）→ 判定沒有自週期。
    """
    c = np.asarray(cell)
    if c.ndim != 2 or c.size == 0:
        return (0, 0)
    h, w = int(c.shape[0]), int(c.shape[1])
    out = [w, h]
    for axis, span in ((1, w), (0, h)):
        for k in range(MAX_SELF_REPEAT, 1, -1):          # 先試最小的單元
            if span % k or span // k < 2:
                continue
            d = span // k
            hit = _roll_ncc(c, d, axis)
            if hit < SELF_PERIOD_NCC:
                continue
            # 捲半個週期要**明顯不像** —— 不然那一軸只是平的（見 docstring）
            if hit - _roll_ncc(c, max(1, d // 2), axis) < SELF_PERIOD_MARGIN:
                continue
            out[1 - axis] = d
            break
    return (int(out[0]), int(out[1]))


def encode_cell(cell: np.ndarray, self_period: Optional[Tuple[int, int]] = None
                ) -> str:
    """``(h, w)`` uint8 → ``"gc2:<w>x<h>:<sx>x<sy>:<base64>"``。

    ``sx``/``sy`` 是這個 cell **自己**重複的單元（見 :func:`cell_self_period`）。
    存進字串而不是每一顆重算：它是模板的性質，一份模板只有一個答案，而
    ``run_defect`` 是逐顆呼叫的。留空就當場量。

    舊的 ``gc1:``（沒有自週期）照樣讀得動 —— 那時候自週期視同 cell 尺寸，
    也就是**跟以前完全一樣的行為**（黃金值不動）。
    """
    a = np.asarray(cell)
    if a.ndim != 2 or a.size == 0:
        return ""
    u8 = _gray_u8(a)
    h, w = u8.shape
    sx, sy = self_period if self_period else cell_self_period(u8)
    blob = base64.b64encode(zlib.compress(u8.tobytes(), 6)).decode("ascii")
    return "%s:%dx%d:%dx%d:%s" % (CELL_ENCODING, w, h, int(sx), int(sy), blob)


def decode_template(text: str) -> Optional[Tuple[np.ndarray, Tuple[int, int]]]:
    """字串 → ``(cell, (sx, sy))``；格式不對回 ``None``（絕不 raise）。

    讀得懂兩種標籤：``gc2`` 帶自週期，``gc1``（舊的）沒有 —— 那時候自週期視同
    cell 尺寸，行為與以前逐位元組相同。
    """
    s = str(text or "").strip()
    if not s:
        return None
    try:
        parts = s.split(":")
        tag = parts[0]
        if tag == "gc1" and len(parts) == 3:
            size, self_size, blob = parts[1], None, parts[2]
        elif tag == "gc2" and len(parts) == 4:
            size, self_size, blob = parts[1], parts[2], parts[3]
        else:
            return None
        w, h = (int(v) for v in size.split("x"))
        raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
        if w < 1 or h < 1 or len(raw) != w * h:
            return None
        cell = np.frombuffer(raw, dtype=np.uint8).reshape(h, w).copy()
        if self_size is None:
            return cell, (w, h)
        sx, sy = (int(v) for v in self_size.split("x"))
        if not (1 <= sx <= w and 1 <= sy <= h):
            return cell, (w, h)
        return cell, (sx, sy)
    except Exception:  # 壞字串一律當沒有
        swallowed("template.decode_template")
        return None


def decode_cell(text: str) -> Optional[np.ndarray]:
    """:func:`decode_template` 的方便版：只要 cell 那張圖。"""
    got = decode_template(text)
    return None if got is None else got[0]


# --------------------------------------------------------------------------- #
# 比對
# --------------------------------------------------------------------------- #
def tile_cell(cell: np.ndarray, min_w: int, min_h: int) -> np.ndarray:
    """把一個週期接成至少 ``min_w`` × ``min_h`` 的畫布。

    **一定要接**：有些 patch 剛好跨在週期的接縫上，只拿一個週期當模板，
    那些 patch 永遠比對不到。
    """
    a = np.asarray(cell)
    if a.ndim != 2 or a.size == 0:
        return a
    h, w = a.shape
    ny = int(np.ceil(max(1, min_h) / float(h))) + 1
    nx = int(np.ceil(max(1, min_w) / float(w))) + 1
    return np.tile(a, (ny, nx))


def patch_structure(patch: Any, axis_x: bool = True) -> float:
    """這張 patch 上有沒有東西可以定位（同 ``algo/profile.profile_confidence``）。

    為什麼相關分數本身不夠
    ----------------------
    比對一定會回一個「最像的位置」。一張**沒有特徵**的 patch 收窄成 32 個樣本的
    曲線之後，跟模板隨機相關的標準差大約是 ``1/√32 ≈ 0.18`` —— 也就是說
    **純雜訊靠運氣就可以拿到 0.4 以上的分數**，實測過。門檻拉高只是把這件事
    推遲，不是解決它：真實資料的分數本來就比合成的低，門檻拉高會開始殺掉真的。

    所以先問一個相關性完全回答不了的問題：**這張 patch 上有結構嗎？** 沒有的話
    它就是定不出來 —— 那是資訊不夠，不是門檻沒調好。這跟投影定位用的是同一個
    量（曲線的起伏 ÷ 雜訊尺度），所以兩張卡對「哪些 patch 定得出來」的判斷一致。
    """
    from . import profile as algo_profile

    axis = algo_profile.AXIS_X if axis_x else algo_profile.AXIS_Y
    smoothed, raw = algo_profile.projection(patch, axis=axis, smooth=3)
    return algo_profile.profile_confidence(smoothed, raw)


def match_patch(cell: np.ndarray, patch: Any,
                min_score: float = 0.3,
                min_margin: float = 0.05,
                min_structure: float = 5.0,
                periodic: Tuple[bool, bool] = (True, True),
                self_period: Optional[Tuple[int, int]] = None) -> MatchResult:
    """把 ``patch`` 對回 ``cell`` 的相位。

    ``margin``（峰的突出程度）是判斷「這張定得出來嗎」的依據 ——
    見模組說明。門檻兩個都要過。

    **非週期的那一軸會被壓成一維再比對。** 垂直條紋的 layout 在 Y 上沒有相位
    可言，硬要在 Y 上搜尋只會讓相關面變平、把峰的突出程度稀釋掉 ——
    也就是把「定得出來」誤判成「定不出來」。壓成一維之後，這條路剛好就退化成
    投影定位在做的事（``algo/profile.py``），兩個方法在這裡是一致的。

    ``self_period``：這個 cell **自己**重複的單元（見 :func:`cell_self_period`）。
    留空 = 視同 cell 尺寸，也就是與以前逐位元組相同的行為。

    **位置與確定度摺在不同的週期上，這是刻意的**：

    * **位置**（``phase_x``/``phase_y``）摺在 **cell** 上 —— 框是標在整個 cell 上
      的，所以要知道 patch 對到 cell 的哪裡。
    * **確定度**（``margin``）摺在**自週期**上 —— 一個 2× 的 cell 裡那兩個峰是
      **同一個答案的複本**，不是「另一個答案」。摺在 cell 上的話最高 ＝ 次高、
      margin 歸零（實測 1× 是 0.37–0.61，2×／3× 都是 0.000），而預設門檻會把
      每一顆都判成定不出來。
    """
    c = np.asarray(cell)
    p = _gray_u8(patch)
    if c.ndim != 2 or c.size == 0 or p.size == 0:
        return MatchResult()

    structure = patch_structure(p, axis_x=bool(periodic[0]))

    if not periodic[1]:                     # Y 沒有週期 -> 只比 X
        c = c.mean(axis=0, keepdims=True).astype(np.float32)
        p = p.mean(axis=0, keepdims=True).astype(np.float32)
    elif not periodic[0]:                   # X 沒有週期 -> 只比 Y
        c = c.mean(axis=1, keepdims=True).astype(np.float32)
        p = p.mean(axis=1, keepdims=True).astype(np.float32)

    ph, pw = p.shape
    canvas = tile_cell(c, pw + c.shape[1], ph + c.shape[0])
    if canvas.shape[0] < ph or canvas.shape[1] < pw:
        return MatchResult()

    surface = cv2.matchTemplate(canvas.astype(np.float32),
                                p.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    if surface.size == 0:
        return MatchResult()

    # 相關面上每隔一個週期就有一個一模一樣的峰 —— 那些**不是**「另一個答案」，
    # 是同一個答案的複本。所以先把整個面**摺**回一個週期（同相位取最大），
    # 問題才變成它真正該問的那一個：**在所有可能的相位裡，最好的那個比次好的
    # 好多少？** 整張均勻的 patch 摺完之後是平的 —— 差值接近 0。
    cy, cx = c.shape
    folded = _fold_to_period(surface, cx, cy)
    peak_idx = int(np.argmax(folded))
    fy, fx = np.unravel_index(peak_idx, folded.shape)

    # 確定度摺在**自週期**上（見 docstring）。壓成一維的那一軸沒有自週期可言，
    # 所以夾在目前的 c.shape 裡。
    sx, sy = self_period if self_period else (cx, cy)
    sx = max(1, min(int(sx), cx))
    sy = max(1, min(int(sy), cy))
    conf = folded if (sx, sy) == (cx, cy) else _fold_to_period(surface, sx, sy)
    cidx = int(np.argmax(conf))
    ky, kx = np.unravel_index(cidx, conf.shape)
    best_folded = float(conf[ky, kx])

    # 遮掉峰的鄰域（環狀，因為相位是環狀的）再取次高
    rest = conf.copy()
    rx = max(2, conf.shape[1] // 16)
    ry = max(2, conf.shape[0] // 16)
    for dy in range(-ry, ry + 1):
        for dx in range(-rx, rx + 1):
            rest[(ky + dy) % conf.shape[0], (kx + dx) % conf.shape[1]] = -1.0
    runner = float(rest.max()) if rest.size else -1.0
    margin = best_folded - runner

    _mn, best, _mnloc, _bl = cv2.minMaxLoc(surface)
    ok = bool(structure >= float(min_structure)
              and best >= float(min_score)
              and margin >= float(min_margin))
    return MatchResult(phase_x=int(fx % cx), phase_y=int(fy % cy),
                       score=float(best), margin=float(margin),
                       structure=float(structure), ok=ok)


@dataclass
class TemplateHealth:
    """整批的比對結果長什麼樣，以及**這個模板還能不能用**。

    為什麼需要它（``roi_template`` 的檔頭承諾了它，而它一直不存在）
    ----------------------------------------------------------------
    模板是**凍進 recipe** 的：同一支 inspection recipe 掃同一塊 scan area，
    圖案一樣，所以跨 lot 共用是刻意的。但「換一批資料之後它還對不對」沒有人在
    問 —— 而模板對不上的時候，畫面上看到的是**每一顆都定不出來**，那跟「這批
    patch 本來就沒有結構」長得一模一樣。

    兩者的處置**完全相反**：前者要重建模板，後者什麼都不用做（沒有結構的
    patch 本來就該退回整張圖）。分不出來的使用者會一直去調門檻。

    分辨的依據就是三道閘門**各自**倒在哪裡（見 :func:`judge_template`）。
    """

    checked: int = 0
    located: int = 0
    #: 各自沒過的顆數（一顆可能同時掛在好幾關）
    failed_score: int = 0
    failed_margin: int = 0
    failed_structure: int = 0
    #: 中位數（比平均耐得住幾顆爛的）
    score: float = 0.0
    margin: float = 0.0
    structure: float = 0.0
    #: ``ok`` / ``stale`` / ``no-structure`` / ``too-tight`` / ``unknown``
    verdict: str = "unknown"
    message: str = ""

    @property
    def rate(self) -> float:
        return self.located / float(self.checked) if self.checked else 0.0


#: 定位成功率低於這個就要說話。
HEALTH_OK_RATE = 0.8


def judge_template(scores: Sequence[float], margins: Sequence[float],
                   structures: Sequence[float], min_score: float,
                   min_margin: float, min_structure: float) -> TemplateHealth:
    """整批的三個數字 → 「這個模板還能不能用」。

    **吃的是已經算好的特徵**（``match_score`` / ``match_margin`` /
    ``match_structure``），不再跑一次比對 —— 那些數字每一顆都吐了，再算一次
    只會多一份會漂的答案。

    判準（照「處置不同」分，不是照分數高低分）：

    * 大部分**沒有結構** → ``no-structure``：這批 patch 本身沒東西可比。
      不是模板的問題，也不是門檻的問題，退回整張圖就是對的答案。
    * 有結構、但**比對分數低** → ``stale``：patch 不像這個模板。八成是模板
      不是從這批資料（這一層）建的 —— 這就是那個健檢要抓的東西。
    * 有結構、分數也夠、只是**峰不夠突出** → ``too-tight``：圖案週期性強，
      或門檻設太緊。
    """
    n = min(len(scores), len(margins), len(structures))
    if not n:
        return TemplateHealth(message="Run a trial to check this template "
                                      "against the batch.")

    def med(v: Sequence[float]) -> float:
        return float(np.median(np.asarray(list(v)[:n], dtype=np.float64)))

    bad_s = [i for i in range(n) if structures[i] < min_structure]
    bad_c = [i for i in range(n) if scores[i] < min_score]
    bad_m = [i for i in range(n) if margins[i] < min_margin]
    failed = set(bad_s) | set(bad_c) | set(bad_m)
    located = n - len(failed)

    h = TemplateHealth(
        checked=n, located=located, failed_score=len(bad_c),
        failed_margin=len(bad_m), failed_structure=len(bad_s),
        score=med(scores), margin=med(margins), structure=med(structures))

    if h.rate >= HEALTH_OK_RATE:
        h.verdict = "ok"
        h.message = ("%d of %d defects located. This template fits this batch."
                     % (located, n))
        return h

    # 沒過的那些是**倒在哪一關**——處置完全不同，所以要分開講。
    only_structure = [i for i in failed if i in bad_s]
    with_structure = [i for i in failed if i not in bad_s]
    if len(only_structure) >= len(with_structure):
        h.verdict = "no-structure"
        h.message = ("%d of %d defects have nothing to match (median structure "
                     "%.1f, needs %.1f). That is the patches, not the "
                     "template - those regions fall back to the whole image, "
                     "which is the right answer. No setting will change it."
                     % (len(only_structure), n, h.structure, min_structure))
    elif len([i for i in with_structure if i in bad_c]) >= len(with_structure) / 2.0:
        h.verdict = "stale"
        h.message = ("%d of %d defects have structure but do not look like "
                     "this template (median match %.2f, needs %.2f). The "
                     "template was probably not built from this data - "
                     "rebuild it from a full-size image of this batch."
                     % (len(with_structure), n, h.score, min_score))
    else:
        h.verdict = "too-tight"
        h.message = ("%d of %d defects match well but not uniquely (median "
                     "certainty %.2f, needs %.2f). The pattern repeats "
                     "strongly, or “Minimum certainty” is set too tight."
                     % (len(with_structure), n, h.margin, min_margin))
    return h


def _fold_to_period(surface: np.ndarray, px: int, py: int) -> np.ndarray:
    """把相關面摺回一個週期（同相位取最大值）。"""
    s = np.asarray(surface, dtype=np.float32)
    h, w = s.shape
    px, py = max(1, min(int(px), w)), max(1, min(int(py), h))
    out = np.full((py, px), -1.0, dtype=np.float32)
    for y0 in range(0, h, py):
        for x0 in range(0, w, px):
            blk = s[y0:y0 + py, x0:x0 + px]
            out[:blk.shape[0], :blk.shape[1]] = np.maximum(
                out[:blk.shape[0], :blk.shape[1]], blk)
    return out


def roi_boxes_in_patch(norm_rect: Tuple[float, float, float, float],
                       match: MatchResult, cell_shape: Tuple[int, int],
                       patch_shape: Tuple[int, int],
                       periodic: Tuple[bool, bool] = (True, True),
                       max_boxes: int = 64,
                       ) -> List[Tuple[int, int, int, int]]:
    """一個標在 cell 上的框 → 這張 patch 上**每一個**落點（裁進 patch）。

    為什麼是「每一個」而不是「離缺陷最近的那一個」
    ----------------------------------------------
    使用者標的是**重複結構上的一塊**（原話：「一個 layout 是橫向 EPI 跟直向 MG
    交錯，我要的 ROI1 是 EPI 部分扣掉 MG 交集」）。那種東西在 patch 裡有幾份就
    該量幾份 —— 只取離缺陷最近的一份，會在「cell 比 patch 小」的時候**只量到
    一根 EPI，其餘的靜靜漏掉**。而那正是「跑得完、有數字、而且是錯的」。

    這條規則同時涵蓋兩種大小關係，所以不必請使用者選：

    * **cell 比 patch 大**（模板法的常態）—— 最多一份落得進來，可能還一份都沒有
      （框標在 cell 的另一頭）。「一份都沒有」是正常的答案，不是失敗。
    * **cell 比 patch 小** —— 每一份都畫，統計量因此問的是「這張圖上所有的
      EPI」而不是「剛好在中間的那一根」。

    相位以外的兩件事
    ----------------
    * **沒有週期的那一軸沒有相位可言** —— 框在那個方向取滿整張 patch，
      硬給一個位置等於憑空捏造資訊（同 ``roi_profile`` 的 ``_band_rect``）。
      所以 ``locate_axis="x"`` 的時候，框的 y／h **本來就不算數**。
    * 超過 ``max_boxes`` 時留下**離 patch 中心最近**的那些 —— 缺陷在正中央
      （同 ``roi_cross`` 的同名參數，兩張卡對這件事的說法要一致）。
    """
    cy, cx = int(cell_shape[0]), int(cell_shape[1])
    ph, pw = int(patch_shape[0]), int(patch_shape[1])
    nx, ny, nw, nh = (float(v) for v in norm_rect)
    cap = max(1, int(max_boxes))

    xs = (_copies(nx, nw, int(match.phase_x), cx, pw, cap)
          if periodic[0] else [(0, pw)])
    ys = (_copies(ny, nh, int(match.phase_y), cy, ph, cap)
          if periodic[1] else [(0, ph)])

    out: List[Tuple[int, int, int, int]] = []
    for y, h in ys:
        for x, w in xs:
            # 落在 patch 外面的部分裁掉。一份可能有一半在框外 —— 那是正常的
            # （缺陷靠邊時本來就會這樣），但剩下的必須還有像素可以量。
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(pw, x + w), min(ph, y + h)
            if x1 > x0 and y1 > y0:
                out.append((x0, y0, x1 - x0, y1 - y0))

    cxp, cyp = pw / 2.0, ph / 2.0
    out.sort(key=lambda b: ((b[0] + b[2] / 2.0 - cxp) ** 2
                            + (b[1] + b[3] / 2.0 - cyp) ** 2))
    return out[:cap]


def _copies(lo: float, span_frac: float, phase: int, period: int,
            patch_len: int, cap: int) -> List[Tuple[int, int]]:
    """一個軸上，這個框在 patch 裡的每一份 ``(起點, 長度)``。

    ``base`` 是第 0 份的位置：``lo`` 講的是「從這一格的百分之幾開始」，而
    ``phase`` 是這張 patch 的第 0 格從哪裡開始 —— 兩者相減就是像素座標。
    """
    period = max(1, int(period))
    span = max(1, int(round(float(span_frac) * period)))
    base = float(lo) * period - float(phase)

    # 重疊條件：``base + k*period + span > 0`` 且 ``base + k*period < patch_len``。
    # 邊界用 floor/ceil 各放寬一格再過濾，省得跟浮點的邊界情況纏鬥。
    k_lo = int(math.floor((-span - base) / period)) - 1
    k_hi = int(math.ceil((patch_len - base) / period)) + 1
    hits = []
    for k in range(k_lo, k_hi + 1):
        start = int(round(base + k * period))
        if start + span > 0 and start < patch_len:
            hits.append((start, span))

    if len(hits) > cap:
        # 細到放不下的時候留中間那些 —— 缺陷在正中央（同 ``roi_cross``）。
        centre = patch_len / 2.0
        hits.sort(key=lambda t: abs(t[0] + t[1] / 2.0 - centre))
        hits = sorted(hits[:cap])
    return hits
