# d4t algo — OP-301 的對焦清晰度分數（IQI / Focus Index），authored 2026-09-02.
"""**IQI (OP-301)：切 64 塊、去背景、算能量、取前 30% 平均。**

直覺一句話：對焦準 → 邊緣銳利、對比強 → 分數高；失焦 → 邊緣糊、對比弱 →
分數低。四個步驟各一支函式，逐支對應規格的 Step 1–4：

============  ==========================================  ==================
Step 1        切成 ``blocks × blocks`` 塊 ＋ 梯度密度      :func:`slice_blocks`
                                                          :func:`pattern_density`
Step 2        每塊 FFT，兩端各壓一段（背景／雜訊）        :func:`fft_denoise`
Step 3        iFFT 還原回空間域                            :func:`ifft_block`
Step 4        每塊算能量、排序、取前 30% 平均              :func:`block_energy`
                                                          :func:`focus_index`
============  ==========================================  ==================

⚠⚠ 兩份規格互相矛盾的地方（**ASSUMPTION，等 owner 核對**）
============================================================

使用者給了兩份說明，而它們在**兩件事上不一致**。下面每一條都寫出「我選了
哪一個、為什麼、以及要改的話改哪一格」——這比選一個然後不講糟得多，因為
兩種選法**都跑得完、都有數字**，而畫面上看不出差別。

**① 濾波方向：壓低頻，還是壓高頻？—— 答案是兩端都壓**

三份說明講了兩件看起來相反的事：

* 詳細版：「把**低頻**部分壓掉（低頻 = 緩慢變化的背景，如光暈、底色漸變），
  只留高頻訊號」→ 高通。
* 投影片／英文版：「FFT ... to **filter out high-frequency noise** in
  unpatterned background areas」→ 低通。

**它們不是在吵同一件事。** 前者要拿掉的是**背景**（照明不均），後者要拿掉的
是**雜訊**（空背景區的感測器顆粒）—— 一個在頻譜的最低端、一個在最高端。
唯一讓兩句話同時成立的濾波器是**帶通**，而那也正好是對焦指標該有的形狀：
pattern 的邊緣落在中頻。

而後者指出的是一個**真的失效模式**，不是措辭問題。實測（512×512，
空背景 + σ=8 的高斯雜訊 vs 同尺寸的銳利 pattern）：

=====================  ==============  =========================
                       純高通          帶通（``noise_percent=40``）
=====================  ==============  =========================
空背景 ＋ 雜訊           **64.19**       7.00
銳利 pattern            7465.63         4167.45
訊號 ÷ 背景             116×            **595×**
=====================  ==============  =========================

純高通把**雜訊當成了清晰度**：一塊什麼都沒有的背景拿到 64 分。壓掉最高頻
之後它掉到 7，而 pattern 只掉 1.8 倍 —— 對比度提高了五倍。

**預設仍然是 ``noise_percent = 0``（純高通）**，因為那是詳細版**明確描述**
的行為，而這張卡要先能對得上機台的數字；帶通是一格參數，**要不要開由站點
決定**（`CLAUDE.md` 的最高指導原則：站點差異封裝進 recipe，不封裝進程式碼）。
上面那張表就是那一格的說明書。

**實測的答案（2026-09-18，廠外驗證）：``noise_percent`` 是一格站點參數，
而預設的 0 在 logic 區是對的。** 兩台機台各一批真實 raw、每張帶機台自己的
F.I. 真值（機台 A ＝ 高密度重複圖案（array）區、機台 B ＝ logic（不重複）區
—— **代號與層別一律遮蔽**，鐵則 8；數字一律照抄，完整那一份與校正流程見
`docs/USING-FOCUS.md`）：

* **機台 B（logic 區、u16）**：預設那一組（``noise=0``、``cutoff=10``、8×8、
  前 30%）對機台 F.I. 的 Pearson **r = 0.959**、Spearman **rho = 0.989**。
  把 ``noise`` 開到 20，r **崩到 0.06** —— 在 logic 區，高頻是**真的訊號**，
  壓掉它等於把要量的東西量掉。所以那一格在這種站點要留 0。
* HD／u8 那一類的機台仍然需要壓（上面那張合成資料的表就是它的形狀），
  **但先讀 ② 的實測答案** —— array 區有一個更前面的問題。

**② 梯度圖是「篩選塊」還是「只是知道一下」？**

* 詳細版把它列成獨立的 Step 2，說是「讓你知道哪些塊落在 pattern 區域」，
  然後 **Step 4 選前 30% 是照 energy 選的，梯度圖沒有任何下游** ——
  四個步驟裡有一個是空轉的。
* 投影片把它放進 Step 1：「利用梯度演算法**篩選出**具有較高圖案密度的區域」
  → 它真的在篩。

**這裡兩個都留，而預設是「不篩」**（``min_pattern=0.0``）：

* 預設不篩 → 分數逐位元組是詳細版描述的那一個（前 30% 由 energy 決定，
  而那一刀**本來就已經**把空背景塊擋掉了 —— 空背景的能量天然低）；
* ``min_pattern`` 調上去 → 走投影片那一條（先用梯度密度篩掉沒有 pattern
  的塊，再在剩下的裡面取前 30%）；
* 而**無論走哪一條，梯度密度都變成一個看得見的數字**
  （:func:`focus_index` 回的 ``pattern_frac``）。那是 F19 的規矩：
  **卡片自動做的每一個決定，都要變成一個使用者畫得出分布的數字**。
  一個算了卻沒有人讀的步驟，是這個 repo 記過六次的那種形狀。

**實測的答案（2026-09-18，廠外驗證）：在重複 array 區，前 30% 那一刀與梯度
預篩兩個都是 no-op —— 因為 64 塊是同質的。** 把留下來的塊數從 19 掃到 40，
兩台機台的 r **一動都不動**。那不是 bug，是**前提不成立**：這兩步的設計前提
是「有些塊有 pattern、有些塊是空背景」，而 array 區每一塊長得一樣。分數照樣
算得出來，只是它的**鑑別力有限**（機台 A 上每一種量得出來的方法都卡在
r ≈ 0.5：整張帶通 0.29、pattern 諧波能量 0.16、十七個古典對焦指標最高 0.51、
整份 OP-301 參數網格最高 0.31；局部最好的是梯度域的 0.49，那就是
``domain="gradient"`` 的由來）。

順帶把規格措辭的一個歧義也結掉了：投影片寫「前 30」、詳細版寫「前 30%」——
既然塊數從 19 掃到 40 分數不動，**兩種讀法在實務上沒有差別**。

其餘照詳細版的預設：Sobel、cutoff = Nyquist × 10%、能量除以像素數、
前 30% 取 floor、不乘 scale 不加 offset。

⚠ iFFT 其實省得掉（Parseval）
==============================

``Σ|iFFT(X)|² = (1/N)·Σ|X|²``，所以 Step 4 的能量在頻域直接算得出來，
Step 3 的逆轉換**對最終數字沒有貢獻**（64 塊 × 一次多餘的轉換）。而且輸入
是實數影像，iFFT 之後**虛部是浮點雜訊**（~1e-16）—— 規格說的「由實部與虛部
求得」逐字就是 ``real²``。

這裡仍然做 iFFT，兩個理由：規格的驗收標準要四個獨立步驟；而空間域那張圖
是之後要畫在儀表上的東西。``test_parseval_says_the_ifft_is_optional``
把兩條路的數值釘在一起 —— 哪天嫌慢，那條測試就是刪掉 Step 3 的許可證。

四個步驟跑在**哪一張圖**上（``domain``，2026-09-18）
=====================================================

``domain="pixel"``（預設）＝ 跑在影像本身，逐位元組就是上面描述的那一個。
``domain="gradient"`` ＝ 先把影像換成梯度強度 ``G = √(Gx² + Gy²)``
（:func:`gradient_magnitude`），**四個步驟一個字都不改**地跑在 G 上。

為什麼是一格參數而不是一個 ``method``：`CLAUDE.md` §3 那條「**改變『量得出
什麼』的選擇是岔路，不是 method**」。這一格問的是**樣品**（你的區域是重複的
array 還是 logic），不是問軟體要用哪個公式。

⚠ **它不是一個「比較好的預設」，是 array 區的一個起點。** 廠外實測
（2026-09-18）：機台 A（array 區）r 0.31 → **0.49**，是那台機台上量到的局部
最好；機台 B（logic）0.9593 → **0.9596**，也就是**沒有變差**。而 0.49 仍然
不是一個可以出貨的相關 —— array 區真正的問題（機台 A 的 F.I. 是在哪一個影像
階段算的、它的正規化會不會跟同批其他張有關）要機台方回答，那個答案可能會把
整條路換掉。

⚠ **梯度只有一份定義。** G 就是 :func:`pattern_density` 拿去數「哪裡有
pattern」的那一張圖（同一組 Sobel 核、同一次卷積）—— 同一個模組裡有兩個
「梯度」的話，那兩個遲早會不一樣。廠外那一輪用的是 ``cv2.Sobel(CV_32F)``
（邊界 reflect），這裡是 float64 ＋ edge padding：差別只落在最外面那一圈
像素，而不為了對齊一個小數點多養一支 Sobel。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np

__all__ = ["slice_blocks", "pattern_density", "gradient_magnitude",
           "fft_denoise", "ifft_block",
           "block_energy", "focus_index", "DEFAULT_BLOCKS",
           "DEFAULT_KEEP_PERCENT", "DEFAULT_CUTOFF_PERCENT",
           "DEFAULT_NOISE_PERCENT", "DOMAIN_PIXEL", "DOMAIN_GRADIENT",
           "DOMAINS", "DEFAULT_DOMAIN"]

#: 每邊切幾塊。**固定 64 塊（8×8）不隨影像大小改變** —— 那是規格的重點設計：
#: 1024 的圖與 2000 的圖都是「64 塊取前 30%」，所以分數互相比較得起來。
DEFAULT_BLOCKS = 8

#: 取分數最高的前幾成。64 × 30% = 19.2 → **19**（floor）。
#: 為什麼不是全部平均：有些塊是空背景、沒 pattern，分數天生低，全部平均會被
#: 它們拖低，量到的就不是「有 pattern 的地方清不清晰」。
DEFAULT_KEEP_PERCENT = 30.0

#: 壓掉多少低頻（佔 Nyquist 的百分比）。高斯高通的 σ 就是這個頻率。
DEFAULT_CUTOFF_PERCENT = 10.0

#: 壓掉多少**高**頻（佔 Nyquist 的百分比）—— 感測器雜訊那一段。
#: **預設 0 = 不壓**，見模組說明 ①：那是詳細版規格描述的行為，而它跟投影片
#: 的「filter out high-frequency noise」差在哪，測試量得出來
#: （`test_a_noisy_blank_block_scores_like_a_sharp_one_until_you_denoise`）。
DEFAULT_NOISE_PERCENT = 0.0

#: 四個步驟跑在影像本身。**預設**，逐位元組是規格描述的那一個。
DOMAIN_PIXEL = "pixel"

#: 四個步驟跑在梯度強度 ``√(Gx² + Gy²)`` 上（見模組說明最後一節）。
DOMAIN_GRADIENT = "gradient"

#: 兩條路。**順序就是 UI 上那一排膠囊的順序**（預設排第一個）。
DOMAINS = (DOMAIN_PIXEL, DOMAIN_GRADIENT)

DEFAULT_DOMAIN = DOMAIN_PIXEL


# --------------------------------------------------------------------------- #
# Step 1：切塊 ＋ 圖案密度
# --------------------------------------------------------------------------- #
def slice_blocks(img: Any, blocks: int = DEFAULT_BLOCKS) -> List[Any]:
    """**Step 1** —— 把整張圖切成 ``blocks × blocks`` 塊等大的小圖。

    寬或高不能被 ``blocks`` 整除時**先裁掉多餘的邊緣**再切（規格明講），
    所以每一塊逐像素等大 —— 不等大的塊會讓「除以像素數」的歸一化失去意義。

    回傳照 row-major（由上到下、由左到右），所以第 ``i`` 塊的位置是
    ``(i // blocks, i % blocks)``。
    """
    arr = np.asarray(img)
    if arr.ndim != 2:
        raise ValueError("IQI needs a single-channel image, got shape %r"
                         % (arr.shape,))
    n = max(1, int(blocks))
    h, w = arr.shape[:2]
    bh, bw = h // n, w // n
    if bh < 2 or bw < 2:
        raise ValueError(
            "%d×%d blocks on a %d×%d image leaves %d×%d pixels per block - "
            "too small to measure. Use fewer blocks or a bigger image."
            % (n, n, w, h, bw, bh))
    cropped = arr[:bh * n, :bw * n]
    return [cropped[r * bh:(r + 1) * bh, c * bw:(c + 1) * bw]
            for r in range(n) for c in range(n)]


#: Sobel 的兩個核（規格的預設運算子）。**整張圖做一次**，不是每塊各做。
_SOBEL_X = np.array([[-1.0, 0.0, 1.0],
                     [-2.0, 0.0, 2.0],
                     [-1.0, 0.0, 1.0]])
_SOBEL_Y = _SOBEL_X.T


def _convolve3(arr: Any, kernel: Any) -> Any:
    """3×3 相關（邊緣用 edge padding）—— 只給 Sobel 用，所以不做成通用的。

    自己寫而不是拉 scipy：`tools/` 以外的執行時相依要付授權與離線安裝的代價
    （`docs/LICENSING.md`），而這裡只需要九個乘加。
    """
    padded = np.pad(np.asarray(arr, dtype=np.float64), 1, mode="edge")
    out = np.zeros(np.asarray(arr).shape, dtype=np.float64)
    for dy in range(3):
        for dx in range(3):
            k = float(kernel[dy, dx])
            if k:
                out += k * padded[dy:dy + out.shape[0], dx:dx + out.shape[1]]
    return out


def gradient_magnitude(img: Any) -> Any:
    """整張圖的梯度強度 ``√(Gx² + Gy²)``（Sobel）—— **這個模組唯一的一份**。

    兩個下游讀它，而它們必須讀到同一張圖：:func:`pattern_density` 拿它數
    「哪裡有 pattern」，``domain="gradient"`` 拿它當四個步驟的輸入
    （見模組說明最後一節）。梯度大 = 灰階變化劇烈 = 那裡是 pattern 邊緣；
    梯度小 = 平坦 = 空背景。

    回傳的是 ``float64``、跟輸入同尺寸（``_convolve3`` 邊緣用 edge padding，
    所以最外面那一圈也有值）。
    """
    arr = np.asarray(img, dtype=np.float64)
    gx, gy = _convolve3(arr, _SOBEL_X), _convolve3(arr, _SOBEL_Y)
    return np.sqrt(gx * gx + gy * gy)


def pattern_density(img: Any, blocks: int = DEFAULT_BLOCKS,
                    threshold: float = 0.0) -> Tuple[Any, Any]:
    """**Step 1 的第二半** —— 哪些地方有 pattern。

    梯度圖由 :func:`gradient_magnitude` 算（同一份，不在這裡抄第二次）。

    回 ``(每一塊的密度, 整張圖的梯度圖)``。密度 = 那一塊裡梯度超過門檻的像素
    佔幾成；``threshold=0`` 時門檻取**整張圖梯度的中位數**（一個不必使用者
    發明數字的自適應門檻 —— 而它同時保證「全灰的圖」密度是 0，因為那時候
    整張圖的梯度都是 0）。
    """
    mag = gradient_magnitude(img)
    cut = float(threshold) if threshold > 0 else float(np.median(mag))
    hot = mag > max(cut, 1e-12)
    return (np.array([float(np.mean(b)) for b in slice_blocks(hot, blocks)],
                     dtype=np.float64),
            mag)


# --------------------------------------------------------------------------- #
# Step 2：每塊 FFT，兩端各壓一段（低頻＝背景、高頻＝雜訊）
# --------------------------------------------------------------------------- #
def fft_denoise(block: Any, cutoff_percent: float = DEFAULT_CUTOFF_PERCENT,
                noise_percent: float = DEFAULT_NOISE_PERCENT) -> Any:
    """**Step 2** —— 這一塊轉到頻域，兩端各壓一段，回**頻域的複數陣列**。

    兩段各自對應一份規格說的一件事（見模組說明 ①，它們一度看起來互相矛盾）：

    ==================  =============================  ========================
    ``cutoff_percent``  壓掉**低頻**（緩慢變化的背景   詳細版：「低頻 = 光暈、
                        ＝光暈、底色漸變）             底色漸變」
    ``noise_percent``   壓掉**最高頻**（感測器雜訊）   投影片／英文版：
                                                       「filter out high-frequency
                                                       noise in unpatterned areas」
    ==================  =============================  ========================

    兩個都是高斯，頻率用**歸一化**的（Nyquist = 0.5 cycles/px）：

        H(f) = [1 − exp(−f²/2σ_lo²)] × exp(−f²/2σ_hi²)

    σ 是百分比 × Nyquist，所以同一組設定在 128×128 與 250×250 的塊上壓掉的是
    **同一段相對頻率** —— 那正是「圖大小不影響算法」成立的原因。

    ``noise_percent = 0`` = 不壓高頻（純高通，詳細版那條路，也是預設）。
    ``cutoff_percent = 0`` = 不壓低頻（純低通）。
    """
    arr = np.asarray(block, dtype=np.float64)
    spec = np.fft.fft2(arr)
    h, w = arr.shape[:2]
    # 歸一化頻率（fftfreq 回的就是 cycles/sample，Nyquist = 0.5）。
    fy = np.fft.fftfreq(h).reshape(-1, 1)
    fx = np.fft.fftfreq(w).reshape(1, -1)
    r2 = fy * fy + fx * fx
    gain = np.ones(r2.shape, dtype=np.float64)
    if float(cutoff_percent) > 0:
        lo = max(1e-9, float(cutoff_percent) / 100.0 * 0.5)
        gain = gain * (1.0 - np.exp(-r2 / (2.0 * lo * lo)))
    if float(noise_percent) > 0:
        hi = max(1e-9, float(noise_percent) / 100.0 * 0.5)
        gain = gain * np.exp(-r2 / (2.0 * hi * hi))
    return spec * gain


# --------------------------------------------------------------------------- #
# Step 3：iFFT 還原回空間域
# --------------------------------------------------------------------------- #
def ifft_block(spectrum: Any) -> Any:
    """**Step 3** —— 逆轉換回空間域，回**複數**陣列（實部就是那張圖）。

    ⚠ 輸入是實數影像，所以虛部是浮點雜訊（~1e-16）。規格說能量「由實部與
    虛部求得」—— 那句話**逐字就是 `real²`**，不是有兩個獨立的東西在相加。
    保留複數是為了讓 :func:`block_energy` 照規格的字面寫得出來。
    """
    return np.fft.ifft2(np.asarray(spectrum))


# --------------------------------------------------------------------------- #
# Step 4：每塊算能量、排序、取前 30% 平均
# --------------------------------------------------------------------------- #
def block_energy(restored: Any) -> float:
    """**Step 4 的前半** —— 一塊的分數 = ``mean(real² + imag²)``。

    **除以像素數**（規格待確認項的預設）：不同塊大小下分數才比較得起來 ——
    不除的話 2000×2000 的圖分數天生是 1024 那張的四倍，而它們量的是同一件事。
    """
    arr = np.asarray(restored)
    return float(np.mean(arr.real ** 2 + arr.imag ** 2))


def focus_index(img: Any, blocks: int = DEFAULT_BLOCKS,
                keep_percent: float = DEFAULT_KEEP_PERCENT,
                cutoff_percent: float = DEFAULT_CUTOFF_PERCENT,
                min_pattern: float = 0.0,
                noise_percent: float = DEFAULT_NOISE_PERCENT,
                domain: str = DEFAULT_DOMAIN) -> Dict[str, Any]:
    """**Step 4 的後半** —— 排序、取前 ``keep_percent``%、平均。

    回一個 dict 而不是一個裸數字，因為**這支自動做的每一個決定都要看得見**
    （F19）：

    ===================  =====================================================
    ``iqi``              最終的 focus index（前 30% 的平均能量）
    ``pattern_frac``     整張圖有多少地方有 pattern（梯度密度的平均）
    ``blocks``           真的參與平均的有幾塊（``min_pattern`` 篩掉之後）
    ``scores``           每一塊的分數（給儀表畫分布用）
    ===================  =====================================================

    ``min_pattern > 0`` 時先用梯度密度篩掉沒有 pattern 的塊（投影片那條路，
    見模組說明 ②）。篩到一塊都不剩就**退回不篩** —— 那時候的答案是「這張圖
    沒有 pattern」，而那件事由 ``pattern_frac`` 講，不該變成一個錯誤。

    ``domain`` 決定四個步驟跑在哪一張圖上（見模組說明最後一節）。
    ⚠ **``pattern_frac`` 兩條路上是同一個數字**：它講的是「這張**影像**有多少
    地方有 pattern」，那是影像的性質，不是這一格選了什麼的性質。
    """
    if str(domain) not in DOMAINS:
        raise ValueError("unknown IQI domain %r - it is one of %s"
                         % (domain, ", ".join(DOMAINS)))
    density, mag = pattern_density(img, blocks)
    # ⚠ 梯度那條路吃的正是 `pattern_density` 剛剛算完的那一張圖 —— 不多算一次，
    # 也**不可能**跟它不一樣（模組說明最後一節：梯度只有一份定義）。
    pieces = slice_blocks(mag if str(domain) == DOMAIN_GRADIENT else img, blocks)
    scores = np.array(
        [block_energy(ifft_block(fft_denoise(b, cutoff_percent, noise_percent)))
         for b in pieces], dtype=np.float64)

    keep_mask = density >= float(min_pattern) if min_pattern > 0 \
        else np.ones(scores.shape, dtype=bool)
    if not np.any(keep_mask):
        keep_mask = np.ones(scores.shape, dtype=bool)
    eligible = scores[keep_mask]

    k = int(math.floor(len(eligible) * float(keep_percent) / 100.0))
    k = max(1, min(k, len(eligible)))
    top = np.sort(eligible)[::-1][:k]
    return {"iqi": float(np.mean(top)),
            "pattern_frac": float(np.mean(density)),
            "blocks": int(k),
            "scores": [float(v) for v in scores]}
