# ADEPT algorithm library — authored 2026-07-29 (F7-10).
"""局部對比、背景/條紋移除、邊緣保留去噪 —— E-beam patch 常見 artifact 的處理。

為什麼這三件事值得放進來
------------------------
既有的 Enhance 卡都是**全域**的（percentile / gamma / curve / 亮度對比）：
它們對整張圖套同一條轉換曲線。但 E-beam patch 上最常見的三種假訊號都是
**空間性**的，全域轉換一個都處理不掉：

1. **charging 造成的大範圍亮度梯度** —— 一角亮一角暗。全域拉伸只會把梯度
   一起拉大；而 test 與 ref 的梯度不會一樣，於是它整片留在 diff 上。
2. **掃描線條紋（line-scan artifact）** —— 逐行或逐列的增益漂移。
   在 diff 上會變成一條一條的假缺陷，而且 blob 分割抓得到它。
3. **局部暗區裡的小缺陷** —— 全域 percentile 用的是整張圖的分布，
   暗區裡的對比再怎麼拉都還是被亮區決定。

三者的共通結構是「先估一個**大尺度**的成分，再把它拿掉」，所以下面的函式
都長成同一個形狀：估計 → 相減 → 還原亮度基準。

dtype 慣例
----------
一律 float32 進、float32 出（`clahe` 例外：CLAHE 只吃整數，內部轉 uint8），
由呼叫端（step 卡）決定要不要轉回原 dtype —— 跟 `algo/normalize.py` 同慣例。
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

__all__ = [
    "clahe", "remove_background", "remove_stripes", "morph_residual",
    "bilateral", "nlm", "noise_sigma", "median_blur_f32", "fix_isolated",
    "robust_level_spread", "BG_ESTIMATORS",
]


def _as_f32(img: Any) -> np.ndarray:
    return np.asarray(img).astype(np.float32, copy=False)


def _odd(n: int) -> int:
    """把核心大小修成奇數（偶數核沒有中心像素）。"""
    n = max(1, int(n))
    return n if n % 2 == 1 else n + 1


#: Immerkær 的拉普拉斯遮罩（雜訊估計用）。
_NOISE_MASK = np.array([[1.0, -2.0, 1.0],
                        [-2.0, 4.0, -2.0],
                        [1.0, -2.0, 1.0]], dtype=np.float32)


def noise_sigma(img: Any) -> float:
    """估計影像的雜訊標準差（Immerkær 1996），單位是灰階值。

    為什麼保留邊緣的去噪一定要先估這個
    ----------------------------------
    ``bilateral`` / ``nlm`` 的強度參數單位是**灰階值**：它要回答的是
    「差多少以內算同一塊」。直接給常數的話，同一組參數換一台機台、換一個
    曝光條件就完全不對 —— 而使用者會以為是自己參數調錯。

    以雜訊為尺度就穩定了：``strength=1`` 的意思固定是「濾掉一個 σ 的擾動」，
    不管這個 lot 的訊號有多亮、動態範圍有多寬。

    這個估計法用拉普拉斯遮罩對雜訊的響應算，對影像**內容**（邊緣、圖樣）
    幾乎免疫，而且只要一次卷積。
    """
    f = _as_f32(img)
    if f.ndim != 2 or f.shape[0] < 3 or f.shape[1] < 3:
        return float(np.std(f)) if f.size else 0.0
    h, w = f.shape
    conv = cv2.filter2D(f, -1, _NOISE_MASK, borderType=cv2.BORDER_REPLICATE)
    sigma = np.sqrt(np.pi / 2.0) * float(np.sum(np.abs(conv))) \
        / (6.0 * (w - 2) * (h - 2))
    return float(max(sigma, 1e-3))


def robust_level_spread(values: Any):
    """回 ``(背景在哪, 抖多少)`` = ``(中位數, 1.4826 × MAD)``。

    為什麼不用平均與標準差（F11 Enhance-2）
    --------------------------------------
    因為**要量的東西就是缺陷本身**。一顆比背景亮 60 GLV、佔 16 個畫素的缺陷，
    在 64×64 的 patch 上讓標準差從 5.0 變成 6.2 —— 也就是「這張圖有多抖」這個
    量測值有 24% 是缺陷貢獻的，而缺陷越大貢獻越多。用它去正規化的話，
    **兩顆大小不同的缺陷會被套上不同的縮放**，那正是正規化要消除的東西。

    中位數與 MAD 對「少於一半的畫素長得不一樣」完全免疫，所以量到的是背景本身。
    這跟 ``remove_stripes`` 用逐列中位數而不是平均是同一個理由。

    ``1.4826`` 是把 MAD 換算成常態分布標準差的係數（一致性因子），所以回傳值的
    單位跟 σ 一樣 —— 呼叫端不必知道裡面用的是哪一種估計法。

    MAD 為 0（超過一半的畫素完全相同，例如二值 mask 或一大片飽和）時退回標準差
    —— 那時候「一半以上一樣」是真的，但圖上仍然有變異，回 0 會讓呼叫端除以 0。
    """
    f = np.asarray(values, dtype=np.float32).reshape(-1)
    f = f[np.isfinite(f)]
    if f.size == 0:
        return 0.0, 0.0
    med = float(np.median(f))
    spread = 1.4826 * float(np.median(np.abs(f - med)))
    if spread <= 1e-6:
        spread = float(np.std(f))
    return med, spread


def clahe(img: Any, clip_limit: float = 2.0, tiles: int = 8) -> np.ndarray:
    """CLAHE（限制對比的自適應直方圖等化）。回傳 float32（值域 0–255）。

    每個 tile 各自做直方圖等化，所以**暗區裡的小缺陷也拉得起來** ——
    這正是全域 percentile 做不到的事。``clip_limit`` 是對比上限：
    沒有它，平坦區域的雜訊會被放大到跟訊號一樣強（這也是為什麼不用
    普通的 histogram equalization）。

    ``tiles`` 是格子數（8 = 8×8）。格子越小越貼合局部，但也越容易把
    **缺陷本身**當成局部背景吃掉 —— 缺陷比一個 tile 大的時候要調小格數。
    """
    # CLAHE 只吃 8/16-bit 整數；先把值域壓到 0–255 再轉 uint8
    f = _as_f32(img)
    if f.size == 0:
        return f.copy()
    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return f.copy()
    u8 = np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)

    n = max(1, int(tiles))
    op = cv2.createCLAHE(clipLimit=max(0.01, float(clip_limit)),
                         tileGridSize=(n, n))
    return op.apply(u8).astype(np.float32)


def median_blur_f32(img: Any, size: int = 31) -> np.ndarray:
    """中位數濾波，**任何核心大小都吃得下**（cv2 的 float 路只支援 3 / 5）。

    大核心走 uint8：把影像線性映到 0–255、``cv2.medianBlur``、再映回來。
    代價是**背景估計**量化到動態範圍的 1/255；殘差仍然是用原始的浮點值減出來的，
    所以訊號本身沒有被量化。這個代價換到的是 O(1) 的大核心中位數
    （Huang 的直方圖法），不然 31×31 的中位數在 float 上是跑不動的。
    """
    f = _as_f32(img)
    if f.ndim != 2 or f.size == 0:
        return f.copy()
    k = _odd(size)
    if k <= 5:
        return cv2.medianBlur(f, k)
    lo = float(np.nanmin(f))
    hi = float(np.nanmax(f))
    if not np.isfinite(lo) or not np.isfinite(hi) or (hi - lo) < 1e-9:
        return f.copy()                        # 全平的圖，中位數就是它自己
    span = hi - lo
    u8 = np.clip(np.rint((f - lo) / span * 255.0), 0, 255).astype(np.uint8)
    bg = cv2.medianBlur(u8, k).astype(np.float32)
    return (bg / 255.0) * span + lo


#: ``remove_background`` 支援的背景估計法。
BG_ESTIMATORS = ("gaussian", "median")


def remove_background(img: Any, size: int = 31, keep_level: bool = True,
                      estimator: str = "gaussian") -> np.ndarray:
    """大尺度背景移除：``img - 背景估計``（+ 原本的平均值）。

    ``size`` 是背景估計的核心。**它必須明顯大於缺陷** ——
    核心太小的話，缺陷自己會被算進背景裡然後被減掉（訊號消失）。
    經驗值：抓 patch 邊長的 1/4 ~ 1/2。

    ``keep_level=True`` 會把原影像的平均值加回去，讓輸出仍然落在原本的
    亮度區間 —— 不然後面每一張看灰階絕對值的卡（glv_stats、門檻）都要重調。

    兩種估計法，差別是**缺陷有多容易被算進背景裡**（F11 Enhance-2）
    -----------------------------------------------------------------
    ``gaussian``（原本唯一的一種）是加權平均，所以缺陷**一定**有一部分被算進
    背景：一顆比背景亮 60 GLV 的缺陷，在它自己的位置上把背景估計抬高，減完之後
    振幅就少了那一塊。核心開得夠大可以緩解，但緩解不掉 —— 平均值沒有辦法忽略
    離群值。

    ``median`` 可以。中位數只看排序中間那一個，所以只要缺陷佔核心面積的**不到
    一半**，它對背景估計的影響是零 —— 缺陷的振幅完整留在殘差裡。代價是它比較貴，
    而且背景本身有平滑梯度時會有輕微的階梯（中位數是離散的）。

    背景**不平滑**（圖樣邊緣、不規則亮塊）的時候兩種都不對，那是 top-hat 的場合
    —— 見 :func:`morph_residual`（卡片上的 bright_spots / dark_spots）。
    """
    f = _as_f32(img)
    if f.size == 0:
        return f.copy()
    k = _odd(size)
    if str(estimator) == "median":
        bg = median_blur_f32(f, k)
    else:
        bg = cv2.GaussianBlur(f, (k, k), 0, borderType=cv2.BORDER_REPLICATE)
    out = f - bg
    if keep_level and f.size:
        out = out + float(np.nanmean(f))
    return out.astype(np.float32)


def fix_isolated(img: Any, size: int = 3, threshold: float = 4.0):
    """換掉**孤立的**過亮／過暗畫素（hot / dead pixel），其餘一個都不動。

    回傳 ``(輸出, 換掉的比例)``。

    為什麼這不是「再一種去雜訊」（F11 Enhance-2）
    --------------------------------------------
    median / gaussian 會把**整張圖**磨過一遍：只有幾顆壞點的時候那是拿大砲打
    蚊子，而被磨掉的邊緣正是下一段要拿來量 CD 的東西。這一個只動「跟鄰居差得
    離譜」的那幾顆 —— 其餘畫素逐位元組不變。

    判準是**以這張圖自己的雜訊 σ 為單位**（同 ``bilateral`` / ``nlm`` 的
    ``strength``）：``|img - 鄰居中位數| > threshold × σ``。所以 4.0 在安靜的
    lot 與吵的 lot 上是同一件事 —— 那正是常數門檻做不到的。

    σ 本身會被壞點稍微抬高（拉普拉斯遮罩對單點的響應很大），所以真的壞點很多時
    這個判準會偏保守。那是刻意的方向：寧可漏換，不要去動真的缺陷。
    """
    f = _as_f32(img)
    if f.ndim != 2 or f.size == 0:
        return f.copy(), 0.0
    med = median_blur_f32(f, _odd(size))
    sigma = noise_sigma(f)
    # 1 GLV 的地板：合成的無雜訊影像 σ ≈ 0，沒有地板的話門檻會變成 0 而整張圖
    # 都算「跟鄰居不一樣」。
    limit = max(1.0, float(threshold) * sigma)
    bad = np.abs(f - med) > limit
    if not np.any(bad):
        return f.copy(), 0.0
    out = np.where(bad, med, f).astype(np.float32)
    return out, float(np.count_nonzero(bad)) / float(f.size)


def remove_stripes(img: Any, axis: int = 0, strength: float = 1.0) -> np.ndarray:
    """掃描線去條紋：把每一列（或每一行）的中位數拉齊到全域中位數。

    ``axis=0`` 移除**水平**條紋（逐列校正，適合逐行掃描的 SEM）；
    ``axis=1`` 移除垂直條紋。

    用**中位數**而不是平均值是關鍵：一顆夠大的缺陷會把該列的平均值整個帶偏，
    校正時就會在缺陷所在的那一列造成一條反向的假條紋。中位數對它免疫。

    ``strength`` 0–1 是校正比例（1 = 完全拉齊）。留這個旋鈕是因為真實條紋
    通常不是純加性的；全量校正偶爾會過頭。
    """
    f = _as_f32(img)
    if f.ndim != 2 or f.size == 0:
        return f.copy()
    a = 0 if int(axis) == 0 else 1
    # axis=0（水平條紋）-> 每一列一個中位數
    prof = np.nanmedian(f, axis=1 - a)
    global_med = float(np.nanmedian(f))
    delta = (prof - global_med) * float(np.clip(strength, 0.0, 1.0))
    if a == 0:
        return (f - delta[:, None]).astype(np.float32)
    return (f - delta[None, :]).astype(np.float32)


def morph_residual(img: Any, size: int = 15, dark: bool = False) -> np.ndarray:
    """形態學殘差：white top-hat（亮）或 black-hat（暗）。

    top-hat = ``img - open(img)``：留下**比核心小的亮物**，把大尺度背景
    （不管形狀多不規則）整個拿掉。比高斯背景移除更適合「背景不平滑、
    但缺陷很小」的情況 —— 圖樣邊緣不會被算成背景梯度。

    ``dark=True`` 走 black-hat（``close(img) - img``），對應暗缺陷。
    ``size`` 同樣要**大於缺陷**，否則缺陷會被開運算吃掉。
    """
    f = _as_f32(img)
    if f.size == 0:
        return f.copy()
    k = _odd(size)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    op = cv2.MORPH_BLACKHAT if dark else cv2.MORPH_TOPHAT
    return cv2.morphologyEx(f, op, kernel,
                            borderType=cv2.BORDER_REPLICATE).astype(np.float32)


def bilateral(img: Any, size: int = 5, strength: float = 1.0) -> np.ndarray:
    """雙邊濾波：平滑雜訊但**保留邊緣**。

    median 與 gaussian 都會把小缺陷連同雜訊一起抹掉（median 對「比核心小的
    亮點」尤其致命 —— 那正是我們要找的東西）。雙邊濾波只平滑**灰階相近**的
    鄰居，所以缺陷與圖樣的邊界留得住。

    ``strength`` 以**這張圖自己的雜訊 σ** 為單位（見 :func:`noise_sigma`）：
    ``1`` = 只抹掉大約一個 σ 的擾動，換一個 lot 也還是同一個意思。
    """
    f = _as_f32(img)
    if f.size == 0:
        return f.copy()
    d = _odd(size)
    sigma_color = max(1.0, 1.5 * noise_sigma(f) * float(max(0.01, strength)))
    return cv2.bilateralFilter(f, d, sigma_color, float(d)).astype(np.float32)


def nlm(img: Any, size: int = 7, strength: float = 1.0) -> np.ndarray:
    """Non-local means：拿整張圖裡「長得像」的區塊來平均。

    比雙邊濾波更會保留**紋理**（重複圖樣的 patch 正好有很多相似區塊可用），
    代價是慢一個數量級。整批跑之前先在單顆預覽上確認值得。

    只吃 uint8（OpenCV 的限制），所以內部會把值域壓到 0–255 再還原。
    """
    f = _as_f32(img)
    if f.size == 0:
        return f.copy()
    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return f.copy()
    # ``h`` 的單位是**灰階值**，所以轉 uint8 時能不拉伸就不拉伸：
    # 一張 100–165 的圖如果先被拉滿 0–255，雜訊也跟著放大 4 倍，
    # 同一個 h 就從「剛好」變成「幾乎沒有作用」——
    # 使用者會看到「strength 拉到底還是很雜」，而原因跟他的參數無關。
    if lo >= -0.5 and hi <= 255.5:
        u8 = np.clip(f, 0.0, 255.0).astype(np.uint8)
        scale, offset = 1.0, 0.0
        sigma = noise_sigma(f)
    else:
        u8 = np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
        scale, offset = (hi - lo) / 255.0, lo
        sigma = noise_sigma(u8.astype(np.float32))   # σ 要跟 h 同一個尺度
    # h ≈ 一個雜訊 σ 就已經把雜訊壓掉九成而缺陷完好；再往上（2σ 起）
    # 小缺陷會開始跟著消失，所以預設 strength=1 就停在這裡。
    h = max(1.0, sigma * float(max(0.01, strength)))
    out = cv2.fastNlMeansDenoising(u8, None, h, 7, _odd(size) + 2 * 3)
    return (out.astype(np.float32) * scale + offset).astype(np.float32)
