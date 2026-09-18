# F115：IQI 的兩種**區域型態**，合成出來 — authored 2026-09-18.
"""兩張合成影像：**logic 區**與**重複 array 區**。（不是測試檔，是共用工具。）

為什麼要兩張而不是一張
----------------------
2026-09-18 的廠外驗證量到一件事：OP-301 這個指標**在兩種區域上的表現差一個
數量級**，而差別不在參數，在**區域型態**（完整那一份與每一個數字見
`docs/USING-FOCUS.md`）。那一輪的資料不能進這個 repo（鐵則 8），所以這裡把
那兩種區域**各自的形狀**合成出來 —— 斷言的是結構，不是那些相關係數。

* :func:`logic_blocks` —— 一半的塊有東西（階梯邊、細棋盤），一半是空的。
  這是前 30% 那一刀**有作用**的樣子：它要把空的那一半擋在外面。
* :func:`array_blocks` —— 64 塊長得一模一樣。這是前 30% 那一刀與梯度預篩
  **兩個都是 no-op** 的樣子：留 19 塊跟留 40 塊算出來是同一個數字。

⚠ **兩張都固定種子**：`tests/test_card_invariants.py` I1 問的是「同一份輸入
跑兩次答案要一樣」，而一張每次都不同的測試影像會讓任何一條斷言變成擲骰子。

⚠ **不要在這裡調 `NOISE` 或 `PITCH` 來讓某一條斷言變綠。** 它們是這兩張圖
「長得像那種區域」的一部分：雜訊拿掉的話空背景塊的能量會變成 0（真實影像
不是那樣），pitch 調小的話模糊到 3 px 以上圖案就整個消失、分數開始跟著雜訊
底噪亂跳（實測過：pitch 4 在 blur≥3 之後不再單調）。
"""
from __future__ import annotations

import numpy as np

#: 棋盤的格子邊長（px）。見檔頭那條「不要調」。
PITCH = 8

#: 感測器顆粒。空背景塊的能量來源就是它 —— 真實影像上那一塊也不是 0。
NOISE = 2.0

#: 亮／暗兩階。跟 `tests/test_iqi.py` 的 ``_checker`` 同一個量級。
DARK, BRIGHT = 120.0, 200.0


def box_blur(img, radius: int):
    """半徑 ``radius`` 的方框模糊（``0`` = 原樣回傳）—— **失焦的替身**。

    自己寫而不是拉 cv2：這兩張圖是 `d4t/core/algo/iqi.py` 的測試資料，而那一支
    是純 numpy 的（它連 Sobel 都自己寫）。測試側多拉一個相依，只是讓「這張圖
    到底長什麼樣」多一層看不見的東西。
    """
    if not radius:
        return img
    n = int(radius) * 2 + 1
    h, w = img.shape[:2]
    pad = np.pad(np.asarray(img, dtype=np.float64), n // 2, mode="edge")
    out = np.zeros((h, w), dtype=np.float64)
    for dy in range(n):
        for dx in range(n):
            out += pad[dy:dy + h, dx:dx + w]
    return out / float(n * n)


def _checker(h: int, w: int, pitch: int = PITCH):
    yy, xx = np.mgrid[0:h, 0:w]
    return DARK + (BRIGHT - DARK) * (((yy // pitch) + (xx // pitch)) % 2)


def logic_blocks(size: int = 512, blur: int = 0, seed: int = 0):
    """**logic 區**：64 塊裡的 32 塊有圖案，另外 32 塊是空背景。

    有圖案的那些交錯放兩種東西（一道階梯邊、一片細棋盤），因為 logic 區不是
    一種紋理 —— 它是好幾種擠在一起，而那正是「哪幾塊要算進去」這個問題存在
    的理由。

    ``blur`` 是失焦的替身（方框模糊的半徑，0 = 對焦準）。

    **偶數編號的塊有圖案**（``i % 2 == 0``，row-major 與
    :func:`d4t.core.algo.iqi.slice_blocks` 同一個順序）—— 要斷言「前 30% 挑的
    是不是都是有圖案的那些」時，那張真值表就是這一句話。
    """
    rng = np.random.default_rng(int(seed))
    img = np.full((int(size), int(size)), DARK, dtype=np.float64)
    step = int(size) // 8
    for i in range(64):
        r, c = divmod(i, 8)
        if i % 2:
            continue                       # 一半留白
        y0, x0 = r * step, c * step
        if (r + c) % 4 == 0:               # 一道階梯邊
            img[y0:y0 + step, x0 + step // 2:x0 + step] = BRIGHT
        else:                              # 一片細棋盤
            img[y0:y0 + step, x0:x0 + step] = _checker(step, step)
    img = box_blur(img, blur)
    return np.clip(img + rng.normal(0, NOISE, img.shape), 0.0, 255.0)


def logic_textured_blocks() -> np.ndarray:
    """:func:`logic_blocks` 的哪幾塊有圖案 —— 64 個 bool，row-major。"""
    return np.array([i % 2 == 0 for i in range(64)])


def array_blocks(size: int = 512, blur: int = 0, seed: int = 0):
    """**重複 array 區**：整張圖一片棋盤，所以 64 塊**長得一模一樣**。

    那個同質性就是這張圖的全部意思：前 30% 那一刀在挑的是 64 個一樣的東西，
    梯度預篩在篩的也是 64 個一樣的東西 —— 兩個都沒有東西可以做。
    """
    rng = np.random.default_rng(int(seed))
    img = box_blur(_checker(int(size), int(size)), blur)
    return np.clip(img + rng.normal(0, NOISE, img.shape), 0.0, 255.0)
