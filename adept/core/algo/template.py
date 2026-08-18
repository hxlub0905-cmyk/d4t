# ADEPT algorithm library — authored 2026-07-29 (F7-12).
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

import base64
import math
import zlib
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from . import golden as algo_golden
from . import period as algo_period

__all__ = [
    "GoldenCell", "MatchResult", "build_golden_cell", "anchor_cell",
    "encode_cell", "decode_cell", "tile_cell", "match_patch", "roi_in_patch",
    "patch_structure", "MIN_PERIOD_CONFIDENCE",
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


@dataclass
class GoldenCell:
    """從大圖疊出來的一個週期，以及疊得好不好的證據。"""

    cell: np.ndarray                    # (py, px) uint8
    px: int
    py: int
    ghosting: float = 0.0               # 0–100，越高越銳利（疊得越準）
    lap_var: float = 0.0                # 未飽和的原始值（要比較大小時用這個）
    confidence_x: float = 0.0
    confidence_y: float = 0.0
    anchor: Tuple[int, int] = (0, 0)    # 為了錨定地標捲動了多少
    n_cells: int = 0
    #: 這一軸上真的量到週期了嗎。**一維的 layout 是常態**（垂直條紋只有 X 有
    #: 週期），那時候另一軸不做定位 —— 它上面沒有東西可以定位。
    periodic_x: bool = True
    periodic_y: bool = True
    warnings: List[str] = field(default_factory=list)

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
def build_golden_cell(image: Any, px: Optional[int] = None,
                      py: Optional[int] = None, method: str = "mean",
                      anchor: bool = True) -> GoldenCell:
    """從大圖疊出一個 Golden Cell。

    ``px`` / ``py`` 留空就從影像自己量（``period.estimate_period``）。
    量不到週期時回一個空的 cell 並在 ``warnings`` 說明 —— 不猜。
    """
    gray = _gray_u8(image)
    warnings: List[str] = []
    if gray.size == 0:
        return GoldenCell(cell=np.zeros((0, 0), np.uint8), px=0, py=0,
                          warnings=["the image is empty"])

    # 使用者自己指定的週期一律相信（信心檢查只針對「量出來的」那一軸）
    given_x, given_y = px is not None, py is not None
    conf_x = 100.0 if given_x else 0.0
    conf_y = 100.0 if given_y else 0.0
    if not (given_x and given_y):
        est = algo_period.estimate_period(gray)
        if not given_x:
            px, conf_x = int(est.px or 0), float(est.confidence_x)
        if not given_y:
            py, conf_y = int(est.py or 0), float(est.confidence_y)
        warnings.extend(list(est.warnings or []))

    px, py = int(px or 0), int(py or 0)
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
        return GoldenCell(cell=np.zeros((0, 0), np.uint8), px=px, py=py,
                          confidence_x=conf_x, confidence_y=conf_y,
                          periodic_x=False, periodic_y=False,
                          warnings=warnings + [
                              "no repeating period could be measured in this "
                              "image; a Golden Cell needs a periodic layout"])
    if not periodic_x:
        px = w
        warnings.append("no period across the image; the cell spans the full "
                        "width and no region is located along that direction")
    if not periodic_y:
        py = h
        warnings.append("no period down the image; the cell spans the full "
                        "height and no region is located along that direction")

    origin = algo_period.choose_origin(gray.shape, px, py, image=gray)
    cell = algo_golden.stack_cells(gray, px, py, method=method, origin=origin)
    n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))

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
    return GoldenCell(cell=cell, px=px, py=py, ghosting=float(score),
                      lap_var=float(lap_var), confidence_x=conf_x,
                      confidence_y=conf_y, anchor=roll, n_cells=int(n_cells),
                      periodic_x=periodic_x, periodic_y=periodic_y,
                      warnings=warnings)


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
    except Exception:                       # noqa: BLE001 — 壞字串一律當沒有
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
