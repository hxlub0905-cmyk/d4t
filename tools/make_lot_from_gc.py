#!/usr/bin/env python3
# d4t: build a whole lot out of one Golden Cell — authored 2026-08-28 (F58).
"""**拿一張 Golden Cell，鋪成整批擬真資料**：RSEM 大圖 ＋ 從大圖切下來的 patch。

跟 `make_sample*.py` / `make_mgepi_real.py` 的差別只有一句話：**這一支不畫
圖案，它鋪你給的那一張。** 圖案長什麼樣不是參數，是輸入 —— 所以站點換一個
layer、換一個世代，這支工具一行都不用改（最高指導原則：站點差異封裝進資料，
不封裝進程式碼）。

    python3 tools/make_lot_from_gc.py OUT --recipe my_recipe.json
    python3 tools/make_lot_from_gc.py OUT --gc golden_cell.png \\
            --images 50 --size 1000 --defects 3000 --patch 81

產出兩份 lot，各自都是 d4t 直接讀得動的：

    OUT/rsem/images/IMG_0001.png   1000×1000，一顆 defect 一張（KLARF 1.8）
    OUT/rsem/LOT_RSEM.001
    OUT/patch/LOT_SYN.tif          81×81，一顆兩頁（test, ref），KLARF 1.2
    OUT/patch/LOT_SYN.001
    OUT/{rsem,patch}/ground_truth.json

⚠ **GC 可能是廠內圖案，所以產出來的東西也是。** 這支工具進版控，
它吃的那張圖與吐出來的那批資料**都不進**（`CLAUDE.md` 鐵則 8）。

怎麼鋪
------
GC 的週期用**次像素**估（自相關取最小平均差，步進 0.02 px）—— 整數週期會
讓接縫每鋪一次累積一點偏移，鋪滿 1000 px 之後那個偏移看得出來。取樣是雙線性
的，所以非整數週期也接得準。**每張大圖自己的相位**，patch 才切得出不同的相位
（那是這類資料的本質：patch 以缺陷為中心裁，不是以晶格為中心）。

缺陷種在哪
----------
**inner space** —— MG 與 space 的交界，而且只在 EPI 亮帶上（使用者
2026-08-28：「EPI 跟 MG 交界比較暗的地方就是 inner space，defect 都在這邊」）。
位置不是寫死的，是**從 GC 量出來的**：列平均的極大值給 EPI 亮帶，那幾列上的
欄平均給 MG 亮條，亮條的左右緣就是交界。GC 換一張，位置自己跟著換。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import (
    Any, Callable, Dict, List, NamedTuple, Optional, Tuple,
)

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import cv2  # noqa: E402
import tifffile  # noqa: E402

import make_sample as _ms  # noqa: E402
import make_sample_rsem as _mr  # noqa: E402

#: 缺陷型別。**全部都在 inner space 上**（使用者 2026-08-28：「defect 都在
#: 這邊」）—— 所以這裡沒有 `missing_line`：一整根 MG 不見是**版圖**層級的事，
#: 不是一顆 defect。第一版有它，而 3000 顆 / 50 張＝一張 60 顆的密度下，
#: 那些貫穿整張圖的寬條紋把圖案整個吃掉了（看圖才發現的）。
REAL_TYPES = ("bright_blob", "dark_blob", "bridge")
NUISANCE_TYPE = "none"


# --------------------------------------------------------------------------- #
# 讀 GC
# --------------------------------------------------------------------------- #
def load_gc(gc_path: str = "", recipe_path: str = "") -> np.ndarray:
    """把 Golden Cell 讀成 uint8 2D。``--gc`` 是影像檔，``--recipe`` 是 JSON。"""
    if recipe_path:
        from show_template import decode_template, templates_in
        with open(recipe_path, encoding="utf-8") as f:
            found = templates_in(json.load(f))
        if not found:
            raise SystemExit("這份 recipe 裡沒有模板（沒有 gc1:/gc2: 開頭的參數）")
        got = decode_template(found[0][1])
        if got is None:
            raise SystemExit("模板字串解不開（格式不對，或內容被截斷）")
        px, w, h, _ = got
        return np.frombuffer(px, dtype=np.uint8).reshape(h, w).copy()
    img = cv2.imread(str(gc_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"讀不到 GC 影像：{gc_path}")
    return img


# --------------------------------------------------------------------------- #
# 量週期（次像素）
# --------------------------------------------------------------------------- #
def _mismatch(a: np.ndarray, s: float, axis: int) -> float:
    """把 ``a`` 沿 ``axis`` 次像素平移 ``s``，回重疊區的平均絕對差。"""
    i0 = int(np.floor(s))
    f = s - i0
    if axis == 1:
        n = a.shape[1] - i0 - 1
        if n < 8:
            return 1e9
        b = (1 - f) * a[:, i0:i0 + n] + f * a[:, i0 + 1:i0 + 1 + n]
        return float(np.abs(a[:, :n] - b).mean())
    n = a.shape[0] - i0 - 1
    if n < 8:
        return 1e9
    b = (1 - f) * a[i0:i0 + n, :] + f * a[i0 + 1:i0 + 1 + n, :]
    return float(np.abs(a[:n, :] - b).mean())


def _period_1d(g: np.ndarray, axis: int, step: float = 0.02) -> float:
    """一個軸上的週期（次像素）：**整個重疊區的平均絕對差最小的那個位移**。

    ⚠ **比對的視窗不能固定成一小塊。** 為了消掉「位移越大重疊越少越容易對
    上」的偏差，第一版改用固定寬度的視窗 —— 而那個視窗（205 px 的 GC 上只剩
    40 px）**裝不下「第三根缺席」那個地標**，於是量到 87.82（真值 175.96），
    正好是三根。用整個重疊區比反而乾淨：實測那張 GC 的諧波
    29/59/88/117/147 是 38/41/24/37/17，而 176 是 **6.01** —— 真正的週期贏得
    非常明顯，那個偏差根本不是問題。

    ⚠ **「第一個夠好的位移」對不對，全看容差有多緊。** 1.6 倍的時候真 GC 上
    lag 147（五根，不是週期）是 8.00、176 是 6.00，它挑 147 —— 那一版是錯的。
    但改成純粹取最小值也錯：乾淨的週期圖上一個週期與三個週期的平均差**都是
    0**，誰贏由浮點誤差決定（實測一張 1000² 的圖回了五個週期）。
    1.15 倍 ＋ 絕對下限 0.5 兩種情況都對。

    ⚠ **不到兩個週期寬的 GC 量不準是原理上的事** —— 見 :func:`periods`。
    知道答案就用 ``period_x`` 明講，不要賭。
    """
    n = g.shape[1] if axis == 1 else g.shape[0]
    hi = int(max(12, n - max(16, n * 0.12)))
    lags = list(range(8, hi + 1))
    if not lags:
        return float(n)
    ms = [_mismatch(g, float(s), axis) for s in lags]
    best = min(ms)
    # **基頻 = 好得跟最好的一樣的那些位移裡最小的那一個。**
    #
    # 只取最小值不行：一張乾淨的週期圖上，位移一個週期與位移三個週期的平均差
    # **都是 0**，誰贏由浮點誤差決定（實測一張 1000² 的圖回了 5 個週期）。
    #
    # 而容差不能鬆：真 GC 上 lag 147（五根，**不是**週期）是 8.00、176 是
    # 6.00，容差 1.6 倍的話 147 會贏。1.15 倍剛好把它擋在外面，而乾淨圖上
    # 那些真的倍數差在 0.0x，靠 +0.5 的絕對下限一起進來。
    tol = max(best * 1.15, best + 0.5)
    coarse = float(next(s for s, m in zip(lags, ms) if m <= tol))

    fine = np.arange(max(8.0, coarse - 1.0), coarse + 1.0 + step, step)
    return float(min(fine, key=lambda s: _mismatch(g, float(s), axis)))


def periods(gc: np.ndarray, step: float = 0.02) -> Tuple[float, float]:
    """``(水平週期, 垂直週期)``，次像素。見 :func:`_period_1d`。

    ⚠ **一張不到兩個週期寬的 GC，量不準是原理上的事，不是演算法不夠好。**
    這個 layout 的週期靠「哪一根缺席」定義，而位移五根的時候缺席的那一根
    剛好落在重疊區外面 —— 兩個窗口都只有正常的根，**逐點相同**。要分得出來
    得看到**兩個**缺席的位置，也就是 GC 至少要兩個多週期寬。

    使用者那張 205 px（1.16 個週期）量出 175.96 是對的，但那是**真實影像的
    雜訊打破了平手**，不是因為資訊夠。所以 :func:`generate` 收得下明講的
    ``period_x`` / ``period_y`` —— 知道答案的時候就不要賭。

    ⚠ **回的可能是真正週期的整數倍，而那不影響鋪圖。** 次像素位移要靠線性
    插值，插值本身在高對比的圖上就要付約 1 GLV —— 於是**整數**位移（不必
    插值）永遠比非整數的漂亮一點。實測一張 1000² 的乾淨圖，垂直真週期 34.0，
    而它回 170（五倍）：34 要插值、170 剛好整數。

    這件事**沒有修**，因為對這支工具而言它不是問題：**倍數也是週期，鋪出來
    的圖一模一樣**（`test_whatever_it_returns_tiles_seamlessly` 守的就是這一
    句）。真正該保證的是「鋪得準」，不是「數字最小」。要那個數字好看就用
    ``period_x`` 明講。
    """
    g = gc.astype(np.float32)
    # **大圖先抽樣再量。** 粗掃是「每一個候選位移都比一次整張圖」，成本
    # 隨邊長平方成長 —— 一張貼進來的 1000² GC 要跑幾十秒，而使用者按下
    # 「貼上」之後只會看到畫面卡住。抽樣到 ~400 px 量完再乘回去，最後在
    # 原解析度上細修 ±k，答案一樣是次像素的。
    if max(g.shape) <= 400:
        return _period_1d(g, 1, step), _period_1d(g, 0, step)
    # ⚠ **縮小要用面積平均，不能用抽樣（``g[::k, ::k]``）。** 抽樣會把
    # 非整數的週期**別名**掉：34 px 的週期抽樣 3 倍之後，位移 11 列對不齊
    # （相位每次差 0.33），對得齊的最小整數位移是 34 列 —— 也就是**三個**
    # 週期。實測一張 1000² 的圖因此量到 102。面積平均之後圖案仍然連續，
    # 週期就照著縮放比例縮，非整數也活得下來。
    f = 400.0 / float(max(g.shape))
    small = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    out = []
    for axis in (1, 0):
        # ⚠ 這裡**不要**放寬 step：候選的除數（``coarse / k``）是靠次像素
        # 細修才對得上的，step 0.25 落不到 13.6 那種值上，於是它被容差
        # 擋掉、粗掃的倍數就贏了（實測 1000² 的圖回 5 個週期）。
        coarse = _period_1d(small, axis, step) / f
        pad = 2.0 / f
        fine = np.arange(max(8.0, coarse - pad), coarse + pad + step, step)
        out.append(float(min(fine, key=lambda s: _mismatch(g, float(s), axis))))
    return out[0], out[1]


# --------------------------------------------------------------------------- #
# 鋪
# --------------------------------------------------------------------------- #
def tile(gc: np.ndarray, h: int, w: int, px: float, py: float,
         phase_x: float = 0.0, phase_y: float = 0.0,
         warp: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> np.ndarray:
    """把 GC 鋪成 ``h × w``（雙線性取樣，float32）。

    ``warp``（``(dx, dy)``，跟輸出同尺寸）在**取樣的時候**加進座標，不是先鋪
    好再 remap 一次 —— 兩次插值會把邊緣糊掉，而這份資料的重點正是邊緣
    （`algo/edge` 的次像素定位靠它）。
    """
    g = gc.astype(np.float32)
    gh, gw = g.shape
    yy, xx = np.mgrid[0:int(h), 0:int(w)].astype(np.float64)
    if warp is not None:
        xx = xx + np.asarray(warp[0], dtype=np.float64)
        yy = yy + np.asarray(warp[1], dtype=np.float64)
    u = np.clip(np.mod(xx + float(phase_x), px), 0, gw - 1.001)
    v = np.clip(np.mod(yy + float(phase_y), py), 0, gh - 1.001)
    x0 = u.astype(np.int32)
    y0 = v.astype(np.int32)
    fx = (u - x0).astype(np.float32)
    fy = (v - y0).astype(np.float32)
    return ((1 - fx) * (1 - fy) * g[y0, x0] + fx * (1 - fy) * g[y0, x0 + 1]
            + (1 - fx) * fy * g[y0 + 1, x0] + fx * fy * g[y0 + 1, x0 + 1]
            ).astype(np.float32)


# --------------------------------------------------------------------------- #
# 從 GC 量出 inner space 在哪
# --------------------------------------------------------------------------- #
def _peaks(sig: np.ndarray, frac: float = 0.5) -> List[int]:
    """局部極大，而且要高過 ``lo + frac × (hi − lo)``。"""
    lo, hi = float(sig.min()), float(sig.max())
    thr = lo + frac * (hi - lo)
    return [i for i in range(1, len(sig) - 1)
            if sig[i] >= sig[i - 1] and sig[i] > sig[i + 1] and sig[i] > thr]


def inner_space_sites(gc: np.ndarray) -> List[Tuple[int, int]]:
    """GC 上每一個 inner space 的 ``(x, y)``（MG 亮條的左右緣 × EPI 亮帶）。

    ⚠ 這裡**不寫死任何幾何** —— 量出來的。GC 換一張，位置自己跟著換，
    而那正是這支工具存在的理由。
    """
    g = gc.astype(np.float32)
    rows = g.mean(axis=1)
    bands = _peaks(rows, 0.5) or [int(np.argmax(rows))]
    band = g[max(0, bands[0] - 3):bands[0] + 4, :].mean(axis=0)
    lo, hi = float(band.min()), float(band.max())
    bright = band > lo + 0.66 * (hi - lo)          # MG 亮條

    # 亮的**連續段**，而且要夠寬才算一根 MG。
    #
    # ⚠ 不篩寬度的話 space 正中央那條細亮芯也會被當成一根線，它的左右緣
    # 因此各生一個「交界」—— 使用者那張 GC 上量到 50 個而不是 14 個，
    # 而多出來的那些**落在 space 中間**，不是 MG↔space 的交界。
    runs: List[Tuple[int, int]] = []
    x0 = None
    for x in range(len(bright)):
        if bright[x] and x0 is None:
            x0 = x
        elif not bright[x] and x0 is not None:
            runs.append((x0, x))
            x0 = None
    if x0 is not None:
        runs.append((x0, len(bright)))
    # 判準用**最寬的那一段**當尺，不是中位數：亮條與亮芯的數量差不多
    # （一個週期各六段），所以中位數落在兩者中間，篩不掉細的那一半。
    widest = max([b - a for a, b in runs] or [4])
    wide = max(4.0, 0.45 * float(widest))
    keep = [r for r in runs if (r[1] - r[0]) >= wide] or runs
    edges = sorted({e for a, b in keep for e in (a, b)})
    return [(x, y) for x in edges for y in bands]


def sites_from_mask(mask: np.ndarray) -> List[Tuple[int, int]]:
    """一張**畫在 GC 上**的遮罩 → 候選落點 ``[(x, y), …]``（F61）。

    使用者 2026-08-28：「使用者可以利用 GC 的方式（反正都是回推），畫出
    defect 可能在的位置，UI 去隨機產生。」

    ⚠ **這一支存在的理由是它讓後面完全不用改。** `generate` 本來就是
    「從一串 GC 座標裡隨機挑一個，再隨機挑一格 tile」——
    :func:`inner_space_sites` 量出來的清單與這裡畫出來的遮罩，
    對它來說是同一種東西。所以「自動找」與「手畫」不是兩條路，是同一條路的
    兩個入口，而**畫布上的一個點會出現在每一個重複上**（回推）。

    塗到的每一個畫素都是一個候選，所以塗得越大那一塊被抽中的機會越高 ——
    那正是「這一帶比較容易出事」該有的行為，不必另外做權重。
    """
    m = np.asarray(mask)
    if m.ndim != 2 or not m.any():
        return []
    ys, xs = np.nonzero(m.astype(bool))
    return [(int(x), int(y)) for x, y in zip(xs, ys)]


def _into_range(v: int, period: float, lo: int, hi: int) -> int:
    """把 ``v`` 沿著週期搬進 ``[lo, hi]``，**不離開晶格**。

    搬不進去（週期比可用的範圍還大）才退回夾住 —— 那時候本來就沒有第二個
    選擇，而它會發生只可能是 patch 幾乎跟大圖一樣大。
    """
    step = max(1, int(round(period)))
    while v < lo:
        v += step
    while v > hi:
        v -= step
    return int(min(max(v, lo), hi))


class Realism(NamedTuple):
    """**把鋪出來的完美圖案弄回像真的**（F64）。

    使用者 2026-08-28：「GC 合成的那張大圖，我覺得還是要有點雜訊…因為實際不會
    這麼好看（想想 GC 是如何被做出來的），MG 可能會扭一點點，GLV 也不會每區
    每個 layout 都一樣。」

    **他說的那句括號是關鍵**：GC 是**疊出來的**（很多個 cell 平均），所以它比
    任何一個真的 cell 都乾淨 —— 直接鋪開等於把一張「平均臉」複製一百次。真的
    影像跟它差在三件事，而三件都不是加高斯雜訊能補的：

    ============  ==================================  =======================
    差在哪          真實世界的原因                        這裡怎麼做
    ============  ==================================  =======================
    線會扭          LER ＋ 曝寫/蝕刻的低頻彎曲              取樣座標上加一個平滑的隨機位移場
    每格不一樣       每個 cell 的線寬／材質厚度都有分布        **每一個重複**自己的 gain/bias
    大範圍明暗       照明不均、充電、掃描漂移                很低頻的乘法場
    ============  ==================================  =======================

    ⚠ **能獨立變化的最小單位是「一個重複」**，不是「一根線」—— 因為從一張 GC
    只看得出週期，看不出裡面哪一塊是哪一根線的。想要更細的話那是另一件事
    （`make_mgepi_real.py` 那條路是**參數化**畫出來的，它知道每一根線在哪）。

    ``shot`` 是**訊號相依**的雜訊（σ ∝ √訊號）—— SEM 的雜訊本來就是這樣，
    亮的地方比暗的地方吵。跟 `generate` 的 ``noise``（固定 σ 的讀出雜訊）是
    兩回事，兩個都留著。
    """
    # ⚠ ``bend`` 是位移場的**標準差**，而一根線沿著它自己的長度會走過好幾個
    # 相關長度 —— 所以線看起來扭多少大約是 3.5–4 倍。0.45 → 一根線 p-p 約
    # 1.6 px，也就是使用者要的「扭一點點」；第一版寫 0.9，量出來一根線
    # p-p 3–4 px，那是明顯的波浪不是一點點。
    #
    # ⚠ 而**量的時候要量場本身**。第一版拿產出來的影像去估線的位置，量到
    # 0.88 px —— 那個估計量在窗口邊界會夾住，於是把 4 px 說成 0.9 px。
    # 場是沒有歧義的那一份。
    bend: float = 0.45         # 低頻彎曲的振幅（位移場的 σ，px）
    bend_len: float = 140.0    # 彎曲的相關長度（px）
    ler: float = 0.35          # 邊緣抖動的振幅（px）
    ler_len: float = 9.0       # 抖動沿線的相關長度（px）
    cell_gain: float = 0.035   # 每個重複的對比差異（比例）
    cell_bias: float = 3.0     # 每個重複的亮度差異（GLV）
    shade: float = 0.06        # 大範圍照明不均（比例）
    shot: float = 0.55         # 訊號相依雜訊的係數（σ = shot·√訊號）


#: 預設的「不那麼好看」。全部設 0 就回到 F59–F63 的完美鋪圖。
REALISM = Realism()
FLAT = Realism(bend=0.0, bend_len=1.0, ler=0.0, ler_len=1.0, cell_gain=0.0,
               cell_bias=0.0, shade=0.0, shot=0.0)


def _smooth_field(h: int, w: int, length: float,
                  rng: "np.random.Generator") -> np.ndarray:
    """一張平滑的隨機場（單位變異數），相關長度約 ``length`` 個畫素。

    做法是「低解析度的白雜訊 → 三次內插放大」。直接對整張圖模糊的話，模糊
    半徑一大就慢得離譜（1000² 要好幾秒），而先在小圖上生成再放大是等價的。

    ⚠ **放大之後不再多模糊一次。** 原本這裡跟 `make_mgepi_real._mottle` 一樣
    接了一個 `GaussianBlur`，而量過之後它只把相鄰畫素的最大落差從 0.86 壓到
    0.70（三次內插從粗網格放大本來就是帶限的）—— 而那個差距寫不出一條不靠
    seed 運氣的測試。**寫不出測試的守衛就是沒有被驗過的守衛**，所以拿掉。
    振幅由下面那個 std 正規化自動補回來。
    """
    n = max(2, int(round(max(h, w) / max(2.0, float(length)))))
    small = rng.normal(0.0, 1.0, (n, n)).astype(np.float32)
    big = cv2.resize(small, (int(w), int(h)), interpolation=cv2.INTER_CUBIC)
    sd = float(big.std())
    return big / sd if sd > 1e-6 else big


def warp_field(h: int, w: int, px: float, rng: "np.random.Generator",
               spec: Realism = REALISM):
    """``(dx, dy)`` —— 取樣座標要偏多少（見 :class:`Realism`）。

    ⚠ **只偏 x。** 直的是 MG，它扭的是左右；把 y 也偏一樣多的話整張圖會像
    水波，那不是這個 layout 會發生的事。橫的 EPI 由 ``bend`` 那一項的低頻
    成分順帶帶到（位移場本來就兩個方向都連續）。
    """
    dx = np.zeros((int(h), int(w)), dtype=np.float32)
    if spec.bend > 0.0:
        dx += float(spec.bend) * _smooth_field(h, w, spec.bend_len, rng)
    if spec.ler > 0.0:
        dx += float(spec.ler) * _smooth_field(h, w, spec.ler_len, rng)
    return dx, np.zeros_like(dx)


def roughen(img: np.ndarray, px: float, py: float, phase_x: float,
            phase_y: float, rng: "np.random.Generator",
            spec: Realism = REALISM) -> np.ndarray:
    """鋪好之後的明暗變化：**每個重複自己的 GLV** ＋ 大範圍照明不均。

    幾何（線扭）不在這裡 —— 它在 :func:`warp_field`，因為要在取樣的時候做。
    """
    h, w = img.shape
    out = img
    if spec.cell_gain > 0.0 or spec.cell_bias > 0.0:
        # 每一個**重複**一個值：先算每個畫素落在第幾格，再照格子查表。
        ix = np.floor((np.arange(w) + phase_x) / px).astype(np.int64)
        iy = np.floor((np.arange(h) + phase_y) / py).astype(np.int64)
        ix -= ix.min()
        iy -= iy.min()
        gain = rng.normal(1.0, float(spec.cell_gain),
                          (int(iy.max()) + 1, int(ix.max()) + 1))
        bias = rng.normal(0.0, float(spec.cell_bias), gain.shape)
        out = (out - 128.0) * gain[np.ix_(iy, ix)] + 128.0 + bias[np.ix_(iy, ix)]
    if spec.shade > 0.0:
        out = out * (1.0 + float(spec.shade)
                     * _smooth_field(h, w, max(h, w) / 2.5, rng))
    return out.astype(np.float32)


def grain(img: np.ndarray, read_sigma: float, rng: "np.random.Generator",
          spec: Realism = REALISM) -> np.ndarray:
    """雜訊：固定 σ 的讀出雜訊 ＋ **訊號相依**的 shot noise。

    SEM 的雜訊本來就是亮的地方比暗的地方吵（電子數的 Poisson 統計）。
    只加固定 σ 的話，暗區看起來會比真的乾淨，而那正是「量得準不準」最容易
    被高估的地方。
    """
    out = rng.normal(0.0, float(read_sigma), img.shape)
    if spec.shot > 0.0:
        out = out + rng.normal(0.0, 1.0, img.shape) * (
            float(spec.shot) * np.sqrt(np.clip(img, 0.0, None)))
    return out.astype(np.float32)


# --------------------------------------------------------------------------- #
# 種缺陷
# --------------------------------------------------------------------------- #
class DefectSpec(NamedTuple):
    """**缺陷長什麼樣**（F62）。使用者：「可以選 defect size、亮、暗、隨機」。

    三個旋鈕，各自是一個**範圍** —— 因為真實的一批缺陷不會長得一模一樣，
    而一批一模一樣的合成缺陷會讓任何門檻都好調得不真實。

    * ``diameter`` —— **半高全寬**（FWHM，px）。內部轉成高斯的 σ
      （= 直徑 / 2.355），所以**填的是量得到的東西**，不是一個統計參數。
      「寬度＝FWHM」是這個 repo 既有的定義（見 `make_mgepi_real.py` 檔頭）。
    * ``contrast`` —— 比周圍亮／暗多少 GLV。
    * ``polarity`` —— ``bright`` / ``dark`` / ``both``（每顆各自擲）。
    * ``bridge`` —— 「把兩根 MG 接起來」那一種**佔幾成**（0–1）。它不是一個
      點，所以任何只看局部對比的做法都抓不到 —— 留著它是為了那條路測得到。

    ⚠ **``bridge`` 是比例不是開關**（F65）。原本是 `True`／`False`，而
    `True` 的時候三種等機率抽 —— 於是 bridge 佔了 **1/3**。實跑 60 顆量到
    16/35 是 bridge，比 blob 還多，而真實世界通常反過來。使用者：
    「改成可以調的」。
    """
    diameter: Tuple[float, float] = (4.0, 9.0)
    contrast: Tuple[float, float] = (55.0, 95.0)
    polarity: str = "both"
    bridge: float = 0.15       # bridge 佔幾成（0 = 不做）

    def kinds(self) -> Tuple[str, ...]:
        """這組設定**可能**產出哪幾種缺陷（不含比例）。"""
        pol = str(self.polarity)
        out = (("bright_blob",) if pol == "bright" else
               ("dark_blob",) if pol == "dark" else
               ("bright_blob", "dark_blob"))
        return out + (("bridge",) if float(self.bridge) > 0.0 else ())

    def pick(self, rng: "np.random.Generator") -> str:
        """擲一顆出來 —— **比例照 ``bridge`` 走**，剩下的按極性分。

        ⚠ 不要用「把 bridge 塞進清單再等機率抽」那個寫法：那正是 F62 的
        做法，而它讓 bridge 佔了 1/3（`both` 的時候清單是三個）。比例要是
        比例，就得自己擲。
        """
        if float(self.bridge) > 0.0 and float(rng.random()) < float(self.bridge):
            return "bridge"
        pol = str(self.polarity)
        if pol == "bright":
            return "bright_blob"
        if pol == "dark":
            return "dark_blob"
        return "bright_blob" if float(rng.random()) < 0.5 else "dark_blob"


#: 預設的樣子。⚠ **缺陷比 F59/F60 略大**：那時候 σ 寫死 1.4–2.6，現在
#: 直徑 4–9 換算是 σ 1.70–3.82。故意不去湊回原值 —— 這批資料不進版控、
#: 也不是黃金值，而「4–9 px 的點」比「σ 1.4–2.6」對使用者是一句話。
DEFECT = DefectSpec()


def plant(img: np.ndarray, kind: str, cx: float, cy: float,
          rng: np.random.Generator, px: float,
          spec: DefectSpec = DEFECT,
          mask: Optional[np.ndarray] = None) -> Dict[str, float]:
    """在 ``(cx, cy)`` 種一個缺陷（就地），樣子由 ``spec`` 決定。

    回傳**這一顆實際上長什麼樣**（種類、位置、對比、尺寸）—— 那是訓練用的
    regression target，也是「這一顆為什麼沒被抓到」查得下去的唯一依據。

    ``mask`` 給了的話，把這一顆的**足跡**蓋進去（就地 ``|=``）。足跡的判準是
    **半高**，跟 `DefectSpec.diameter` 是同一個定義 —— 兩邊用不同判準的話，
    「填 6 px」與「mask 裡有幾個畫素」會對不起來，而那正是拿去訓練的人第一個
    會去對的東西。
    """
    h, w = img.shape
    amp = float(rng.uniform(*spec.contrast))
    y0, y1 = max(0, int(cy) - 20), min(h, int(cy) + 21)
    x0, x1 = max(0, int(cx) - 20), min(w, int(cx) + 21)
    if y1 <= y0 or x1 <= x0:
        return {}
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)

    def _apply(contrib: np.ndarray, size: float) -> Dict[str, float]:
        img[y0:y1, x0:x1] += contrib
        if mask is not None:
            mask[y0:y1, x0:x1] |= np.abs(contrib) >= amp * 0.5
        return {"kind": kind, "x": float(cx), "y": float(cy),
                "contrast": float(amp), "size": float(size)}

    if kind == "bridge":
        # 橫跨 space 把兩根 MG 接起來 —— 所以長度是**半個 space**，不是半個
        # 週期。第一版寫 ``px / 12``（≈ 一整根的 pitch），畫出來是一條 29 px
        # 的白棒，橫跨兩根線，看圖才發現。
        length = max(2.0, px / 24.0)
        along = np.clip(np.abs(xx - cx) - length, 0.0, None)
        dist = np.hypot(along, np.abs(yy - cy))
        return _apply(amp * np.clip(1.0 - (dist - 1.2), 0.0, 1.0),
                      2.0 * length + 2.4)
    # **填的是直徑，用的是 σ，而換算走 FWHM。**
    #
    # ⚠ 第一版寫 σ = 直徑 / 4（「看得到的大約是 ±2σ」）—— 那條測試當場紅：
    # 填 12 量到 7。±2σ 那一圈只剩峰值的 13%，量不到；**半高**才是量得到的
    # 地方，而 FWHM = 2.355σ。
    #
    # 這也不是這一輪自己挑的定義：`make_mgepi_real.py` 的檔頭早就寫著
    # 「線寬是 **FWHM** 定義」。同一個 repo 裡「寬度」只能有一個意思。
    d = float(rng.uniform(*spec.diameter))
    sigma = d / 2.355
    bump = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma ** 2))
    return _apply((amp if kind == "bright_blob" else -amp) * bump, d)


# --------------------------------------------------------------------------- #
# 主產生器
# --------------------------------------------------------------------------- #
def generate(out_dir: str, gc: np.ndarray, images: int = 50, size: int = 1000,
             defects: int = 3000, patch: int = 81, real_frac: float = 0.5,
             noise: float = 6.0, seed: int = 11, fmt: str = "png",
             period_x: float = 0.0, period_y: float = 0.0,
             sites: Optional[List[Tuple[int, int]]] = None,
             defect: DefectSpec = DEFECT, pairs: bool = False,
             realism: Realism = REALISM,
             progress: Optional[Callable[[int, int], bool]] = None
             ) -> Dict[str, Any]:
    """產 RSEM 大圖 lot ＋ 從大圖切下來的 patch lot。回傳路徑 dict。

    ``pairs=True``（F63）多寫三份**配對**資料：同一張圖的乾淨版、缺陷足跡的
    遮罩、以及每一顆實際的位置／對比／尺寸。⚠ 乾淨版與缺陷版**只差在缺陷**
    —— 雜訊產一次兩邊都加，各自抽一次的話訓出來的模型學的是「去雜訊」。

    ``sites``（GC 座標的一串點）給了就照它種缺陷 —— 那是 UI 上畫出來的
    那一塊（:func:`sites_from_mask`）。沒給就自己量 inner space。

    ``period_x`` / ``period_y`` 給 0 就自己量（:func:`periods`）。**知道答案
    的時候請填** —— 見那一支的說明：不到兩個週期寬的 GC 量不準是原理上的事。

    ``progress(做完幾張, 總共幾張)`` 每張大圖叫一次；**回 False 就停下來**
    （UI 的「停止」）。停下來的時候**兩份 lot 都不寫** —— 半份 KLARF 配著
    半份影像比什麼都不產更糟（同 `run_all` 的老規矩：中途停止就不寫）。
    """
    if images < 1 or defects < 1:
        raise ValueError("images 與 defects 都至少要 1")
    if size < max(gc.shape) * 2:
        raise ValueError(f"size（{size}）至少要是 GC 邊長的兩倍，才鋪得出重複")
    if patch < 16 or patch >= size:
        raise ValueError(f"patch（{patch}）要在 16 與 size 之間")

    out_dir = str(out_dir)
    rsem_dir = os.path.join(out_dir, "rsem")
    patch_dir = os.path.join(out_dir, "patch")
    img_dir = os.path.join(rsem_dir, _mr.IMAGES_DIRNAME)
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(patch_dir, exist_ok=True)
    # 配對輸出（F63）：同一張圖的**乾淨版**與**缺陷足跡**。
    clean_dir = os.path.join(rsem_dir, "clean")
    mask_dir = os.path.join(rsem_dir, "masks")
    clean_pages: List[np.ndarray] = []
    mask_pages: List[np.ndarray] = []
    if pairs:
        os.makedirs(clean_dir, exist_ok=True)
        os.makedirs(mask_dir, exist_ok=True)

    mx, my = periods(gc)
    px = float(period_x) if period_x else mx
    py = float(period_y) if period_y else my
    # ``sites`` 給了就用給的（UI 上畫出來的那一塊，見 :func:`sites_from_mask`）；
    # 沒給就自己量。兩者對下面那個迴圈**完全一樣** —— 它只需要一串 GC 座標。
    sites = list(sites) if sites else inner_space_sites(gc)
    if not sites:
        raise ValueError("在這張 GC 上量不到 inner space（亮條找不到邊），"
                         "而且也沒有畫出任何可能的位置")

    rng = np.random.default_rng(int(seed))
    half = patch // 2
    per_img = int(np.ceil(defects / float(images)))

    rsem_rows: List[str] = []
    rsem_truth: Dict[str, Dict[str, Any]] = {}
    rsem_paths: List[str] = []
    pages: List[np.ndarray] = []
    patch_rows: List[List[str]] = []
    patch_truth: Dict[str, Dict[str, Any]] = {}

    made = 0
    for i in range(int(images)):
        ph_x = float(rng.uniform(0.0, px))
        ph_y = float(rng.uniform(0.0, py))
        # **線會扭**（F64）：位移場加在取樣座標上，不是鋪好再 remap。
        big = tile(gc, size, size, px, py, ph_x, ph_y,
                   warp=warp_field(size, size, px, rng, realism))
        # **每個重複自己的 GLV ＋ 大範圍照明不均**（F64）。
        big = roughen(big, px, py, ph_x, ph_y, rng, realism)
        # 每張圖自己的亮度／對比微擾（模擬每次取像的條件差異）
        big = (big - 128.0) * float(rng.uniform(0.93, 1.07)) + 128.0 \
            + float(rng.uniform(-8.0, 8.0))

        # **配對輸出（F63）：乾淨版與缺陷版只能差在缺陷。**
        #
        # ⚠ 所以雜訊要**產一次、兩邊都加**。各自 `rng.normal` 一次的話兩張圖
        # 每一個畫素都不一樣，而那種資料訓出來的模型學的是「去雜訊」，
        # 不是「把缺陷拿掉」—— 看起來完全正常，量出來的 loss 也會下降。
        # ⚠ **不論有沒有 `pairs` 都留一份乾淨的**：shot noise 的 σ 要取自
        # 乾淨版的訊號（見下面），而不是取自已經種了缺陷的那一張。
        clean = big.copy()
        dmask = (np.zeros((size, size), dtype=bool) if pairs else None)

        # 這張圖上要種幾顆、種在哪（一律落在 inner space 上）
        k = min(per_img, int(defects) - made)
        spots: List[Tuple[int, int, str]] = []
        marks: List[Dict[str, float]] = []
        for _ in range(k):
            sx, sy = sites[int(rng.integers(0, len(sites)))]
            gx = int(rng.integers(0, max(1, int((size - patch) / px))))
            gy = int(rng.integers(0, max(1, int((size - patch) / py))))
            # ⚠ **不要 ``% size``。** 大圖的邊長不是週期的整數倍（900 / 34 =
            # 26.47），所以那個取餘數會把位置甩到晶格外 —— 一批裡剛好繞回來的
            # 那幾顆就不在使用者畫的地方了。往內搬交給 `_into_range`，
            # 它走的是**週期**。
            cx = int(round(gx * px + sx - ph_x))
            cy = int(round(gy * py + sy - ph_y))
            # 太靠邊就**整個週期整個週期地往內搬**，不要 clip。
            #
            # ⚠ 這一段本來是 `np.clip`，而那是錯的：clip 把缺陷推到一個
            # **不在晶格上**的位置，也就是使用者根本沒有畫的地方。一批裡只有
            # 貼邊的那幾顆會這樣，每一顆看起來都正常，而「缺陷都在 inner
            # space 上」這個前提被安靜地打破。抓到它的是
            # `test_defects_only_land_where_the_mask_says`。
            cx = _into_range(cx, px, half + 2, size - half - 3)
            cy = _into_range(cy, py, half + 2, size - half - 3)
            is_real = rng.random() < real_frac
            kind = defect.pick(rng) if is_real else NUISANCE_TYPE
            info: Dict[str, float] = {}
            if is_real:
                info = plant(big, kind, cx, cy, rng, px, defect, dmask)
            spots.append((cx, cy, kind))
            marks.append(info)

        # ⚠ 雜訊仍然**產一次、兩邊都加**（F63 的那條不變量）——`speckle` 是
        # 同一個陣列，兩邊都加它。
        #
        # σ 取自**乾淨版**的訊號。⚠ 這一行原本的註解說「取自缺陷版的話配對就
        # 壞了」，而那是**假的**：兩邊加的是同一個 speckle，所以配對怎麼樣都
        # 成立（突變測試證實了 —— 換成缺陷版，35 條測試全綠）。真正的理由小
        # 得多：取自乾淨版，雜訊的分布就跟「這裡有沒有缺陷」無關，於是
        # 遮罩之外的統計量對兩張圖是同一份。物理上取缺陷版也說得通（更亮 =
        # 更多電子 = 更吵），兩種都不算錯。
        speckle = grain(clean, noise, rng, realism)
        big = big + speckle
        u8 = np.clip(big, 0, 255).astype(np.uint8)
        if pairs:
            clean_u8 = np.clip(clean + speckle, 0, 255).astype(np.uint8)
            _mr._write_image(os.path.join(clean_dir, f"DEF_{i + 1:04d}.{fmt}"),
                         clean_u8)
            _mr._write_image(os.path.join(mask_dir, f"DEF_{i + 1:04d}.png"),
                         (dmask.astype(np.uint8) * 255))

        # ---- RSEM 那一份：一張圖一顆代表 defect ----
        name = f"IMG_{i + 1:04d}.{fmt}"
        path = os.path.join(img_dir, name)
        _mr._write_image(path, u8)
        rsem_paths.append(path)
        rid = str(i + 1)
        rsem_rows.append(_mr._defect_row(
            rid, int(spots[0][0]) * 1000, int(spots[0][1]) * 1000, 1, 1,
            f"{_mr.IMAGES_DIRNAME}/{name}", fmt))
        rsem_truth[rid] = {"is_real": spots[0][2] != NUISANCE_TYPE,
                           "type": spots[0][2],
                           "defects": [dict(m) for m in marks if m]}

        # ---- patch 那一份：從**同一張大圖**切下來 ----
        # ref 取「往旁邊一個完整週期」的同一個位置 —— 那正是 die-to-die /
        # cell-to-cell 的做法：同樣的圖案、沒有這顆缺陷。
        for (cx, cy, kind), info in zip(spots, marks):
            made += 1
            rx = cx - int(round(px))
            if rx - half < 0:
                rx = cx + int(round(px))
            rx = int(np.clip(rx, half, size - half - 1))
            test = u8[cy - half:cy + half + 1, cx - half:cx + half + 1]
            ref = u8[cy - half:cy + half + 1, rx - half:rx + half + 1]
            if test.shape != (patch, patch) or ref.shape != (patch, patch):
                made -= 1
                continue
            pages.append(test)
            pages.append(ref)
            if pairs:
                # **頁序跟主檔逐頁對齊**：主檔一顆兩頁（test, ref），所以這裡
                # 也是兩頁。ref 那一頁本來就沒有缺陷，所以它的乾淨版等於它
                # 自己、遮罩全黑 —— 寫下來不是浪費，是讓「第 n 頁對第 n 頁」
                # 這句話**沒有例外**。少寫那一頁的話兩邊差一倍，而拿去訓練的
                # 人會照著 index 取，取到的是別顆。
                clean_pages.append(
                    clean_u8[cy - half:cy + half + 1, cx - half:cx + half + 1])
                clean_pages.append(
                    clean_u8[cy - half:cy + half + 1, rx - half:rx + half + 1])
                mask_pages.append(
                    (dmask[cy - half:cy + half + 1,
                           cx - half:cx + half + 1].astype(np.uint8) * 255))
                mask_pages.append(np.zeros((patch, patch), dtype=np.uint8))
            did = str(len(patch_rows) + 1)
            patch_rows.append([did, f"{cx * 0.001:.4f}", f"{cy * 0.001:.4f}",
                               "1", "1", "0", "2",
                               f"{len(pages) - 1} {len(pages)}"])
            # **每一顆實際上長什麼樣**（F63）：位置、對比、尺寸。分類標籤之外
            # 還有 regression target，而「這顆為什麼沒被抓到」查得下去。
            patch_truth[did] = {"is_real": kind != NUISANCE_TYPE, "type": kind,
                                "x": int(cx), "y": int(cy)}
            if info:
                patch_truth[did]["contrast"] = round(float(info["contrast"]), 2)
                patch_truth[did]["size"] = round(float(info["size"]), 2)
        if progress is not None and not progress(i + 1, int(images)):
            raise KeyboardInterrupt("使用者停止")
        if made >= defects:
            break

    # ---- 寫 RSEM lot ----
    rsem_klarf = os.path.join(rsem_dir, _mr.LOT_NAME + ".001")
    with open(rsem_klarf, "w", encoding="ascii", newline="\n") as f:
        f.write(_mr._make_klarf_text(rsem_rows))
    rsem_gt = os.path.join(rsem_dir, "ground_truth.json")
    with open(rsem_gt, "w", encoding="utf-8") as f:
        json.dump(rsem_truth, f, indent=2, sort_keys=True)

    # ---- 寫 patch lot ----
    patch_tif = os.path.join(patch_dir, _ms.LOT_NAME + ".tif")
    tifffile.imwrite(patch_tif, np.stack(pages), photometric="minisblack")
    patch_klarf = os.path.join(patch_dir, _ms.LOT_NAME + ".001")
    with open(patch_klarf, "w", encoding="ascii", newline="\n") as f:
        f.write(_ms._make_klarf_text(len(patch_rows), patch_rows))
    patch_gt = os.path.join(patch_dir, "ground_truth.json")
    with open(patch_gt, "w", encoding="utf-8") as f:
        json.dump(patch_truth, f, indent=2, sort_keys=True)

    out = {"out_dir": out_dir, "period": (px, py),
           "measured": (mx, my), "sites": len(sites),
           "rsem_klarf": rsem_klarf, "rsem_images": rsem_paths,
           "rsem_ground_truth": rsem_gt,
           "patch_klarf": patch_klarf, "patch_tiff": patch_tif,
           "patch_ground_truth": patch_gt, "patch_count": len(patch_rows)}
    if pairs:
        # patch 的配對走**另外兩份 TIFF**，頁序跟主檔**逐頁**對齊
        # （第 n 頁對第 n 頁，含 ref 那幾頁）。塞進主檔的話 KLARF 的
        # `IMAGELIST` 就得跟著改，而那會讓這批資料在 d4t 自己的 ingest 上
        # 變成「一顆四張」。
        out["patch_clean_tiff"] = os.path.join(patch_dir, "clean.tif")
        out["patch_mask_tiff"] = os.path.join(patch_dir, "masks.tif")
        tifffile.imwrite(out["patch_clean_tiff"], np.stack(clean_pages),
                         photometric="minisblack")
        tifffile.imwrite(out["patch_mask_tiff"], np.stack(mask_pages),
                         photometric="minisblack")
        out["rsem_clean_dir"] = clean_dir
        out["rsem_mask_dir"] = mask_dir
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--gc", default="", help="Golden Cell 影像檔（PNG／TIF）")
    ap.add_argument("--recipe", default="",
                    help="改從 recipe JSON 裡的模板取 GC")
    ap.add_argument("--images", type=int, default=50, help="RSEM 大圖幾張")
    ap.add_argument("--size", type=int, default=1000, help="大圖邊長")
    ap.add_argument("--defects", type=int, default=3000, help="patch 幾顆")
    ap.add_argument("--patch", type=int, default=81, help="patch 邊長")
    ap.add_argument("--real-frac", type=float, default=0.5)
    ap.add_argument("--noise", type=float, default=6.0)
    ap.add_argument("--bridge-frac", type=float, default=None,
                    help="bridge 佔幾成（0–1，預設 %.2f）"
                         % DEFECT.bridge)
    ap.add_argument("--polarity", default=None,
                    choices=("both", "bright", "dark"),
                    help="缺陷是亮的、暗的、還是隨機（預設 %s）" % DEFECT.polarity)
    ap.add_argument("--flat", action="store_true",
                    help="關掉擬真（線不扭、每格 GLV 一樣）—— 回到 F63 的完美鋪圖")
    ap.add_argument("--pairs", action="store_true",
                    help="也寫出乾淨版與缺陷足跡（配對資料，給訓練用）")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--format", dest="fmt", default="png",
                    choices=list(_mr.FORMATS))
    ap.add_argument("--period-x", type=float, default=0.0,
                    help=("水平週期（px）。留空就自己量 —— 但**不到兩個週期寬"
                          "的 GC 量不準是原理上的事**，知道答案就填"))
    ap.add_argument("--period-y", type=float, default=0.0,
                    help="垂直週期（px）。留空就自己量")
    args = ap.parse_args(argv)
    if not (args.gc or args.recipe):
        ap.error("--gc 或 --recipe 至少要給一個")

    gc = load_gc(args.gc, args.recipe)
    print("GC %d×%d" % (gc.shape[1], gc.shape[0]))
    out = generate(args.out_dir, gc, images=args.images, size=args.size,
                   defects=args.defects, patch=args.patch,
                   real_frac=args.real_frac, noise=args.noise,
                   seed=args.seed, fmt=args.fmt,
                   period_x=args.period_x, period_y=args.period_y,
                   pairs=bool(args.pairs),
                   realism=FLAT if args.flat else REALISM,
                   defect=DEFECT._replace(
                       bridge=(DEFECT.bridge if args.bridge_frac is None
                               else float(args.bridge_frac)),
                       polarity=(DEFECT.polarity if args.polarity is None
                                 else str(args.polarity))))
    note = ("" if (args.period_x or args.period_y)
            else "（量的；不到兩個週期寬的 GC 請用 --period-x 明講）")
    print("週期 x=%.2f y=%.2f%s，量到 %d 個 inner space"
          % (out["period"][0], out["period"][1], note, out["sites"]))
    print("RSEM  %d 張 → %s" % (len(out["rsem_images"]), out["rsem_klarf"]))
    print("patch %d 顆 → %s" % (out["patch_count"], out["patch_klarf"]))
    print("\n⚠ GC 可能是廠內圖案，這批資料跟原始影像一樣敏感 —— 不要 commit。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
