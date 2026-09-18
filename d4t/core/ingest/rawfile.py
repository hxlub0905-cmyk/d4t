# d4t ingest — authored 2026-09-18 (F113).
"""headerless／帶固定檔頭的 **`.raw`** 影像。

`.raw` 裡**沒有任何一個 byte 在講寬、高或位元深度** —— 它就是一串像素。所以這
一支要的東西比別的格式多，而那不是設計上的疏忽：那些數字**只有使用者知道**
（或者從檔案大小推得出來，見 :func:`guess_layouts`）。

⚠ **這句話有一個例外，而它值錢**（2026-09-18，廠外驗證兩批真檔逐位元組確認）：
使用者機台那一種 `.raw` **的 64 KiB 檔頭第一段就是寬高** —— 開頭四個
little-endian u16 是 ``W, 0, H, 0``，接著 ``W × H × 2`` 個 byte 的像素
（3584²：65536 + 3584 × 3584 × 2 = 25,755,648，跟檔案大小逐位元組吻合；
7680² 同樣成立）。所以 :func:`guess_layouts` **先讀檔頭、讀不懂才回頭猜大小**：
讀得懂的時候使用者連確認都不必做，而「猜」這個動作本身就不再發生。
**那仍然不是一個白名單** —— 檔頭對不上就退回原本那條路，不會硬套。

⚠ **猜錯的代價是每一個像素都錯，而且不會報錯。** 寬度差一個 pixel，整張圖就
變成一條斜線；位元深度猜錯，亮度差 16 倍或 256 倍。所以這裡的原則跟
`dataset.require_8bit` 一樣：**推得出來就建議、推不出來就問，絕不安靜地硬套**。

16-bit → 8-bit：**整批用同一個位移**
------------------------------------
整條 pipeline 是 8-bit 的，而 16-bit 的資料要降下來。這裡**不做逐張拉伸** ——
那正是 `imageio.load_gray` 對非 8-bit 做的事，而 `require_8bit` 的說明逐字寫著
它為什麼是錯的：每張圖各自拉伸之後，兩張圖之間就不再可比，而「比」是這個工具
的全部。

所以 :class:`RawSpec` 帶一個 ``shift``，**整批共用**：位移多少在載入的當下決定
一次（量第一張的實際最大值，見 :func:`suggest_shift`），之後每一張都用同一個。
決定了什麼會講出來，不會安靜地發生。
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

#: 副檔名（小寫比對）。**只住在這裡一份** —— `dataset._IMAGE_EXTS` 與 Studio 的
#: 檔案對話框都從這裡拿（同 `_TIFF_EXTS` 那條規矩）。
RAW_EXTS = (".raw",)

#: 檔案大小反推版面時，會試的那幾種檔頭長度（bytes）。
#:
#: 0 是「沒有檔頭」；其餘幾個是機台常見的固定長度。⚠ 這是**建議**用的，
#: 不是白名單 —— 使用者填得進任何數字。
COMMON_HEADERS = (0, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536)

#: 試哪幾種位元深度。
COMMON_BITS = (16, 8)

#: 檔頭裡真的寫著寬高的那一種 `.raw`：檔頭長度、以及檔頭開頭那四個
#: little-endian u16 的意思（``W, 0, H, 0``）。實測見模組說明。
HEADER_BYTES = 65536

#: 檔頭讀出來的寬高要落在這個範圍才當真。
#:
#: **這一對數字是防呆，不是規格**：`.raw` 的前 8 個 byte 本來就可能是像素，
#: 而像素湊巧長成 ``W, 0, H, 0`` 的機率不是 0。下界擋掉「前幾個像素剛好很小」
#: （一張 3×0 的圖不存在），上界擋掉離譜的大數 —— 而真正的判準是下面那一句：
#: **算出來的檔案大小要逐位元組吻合**。
MIN_SIDE, MAX_SIDE = 1024, 16384


@dataclass(frozen=True)
class RawSpec:
    """一個 `.raw` 檔要怎麼讀。

    ``shift``：16-bit 降成 8-bit 時右移幾位（``None`` = 還沒決定）。
    12-in-16 的資料是 4、滿量程 16-bit 是 8、本來就 8-bit 的是 0。
    **整批共用一個值**，理由見模組說明。

    ``from_header``：這組寬高是**從檔案自己的檔頭讀出來的**，不是從檔案大小
    猜的。只影響 :meth:`describe` 說哪一句話 —— 而那句話是使用者判斷「要不要
    再確認一次」的全部依據，所以它不能跟一個猜出來的答案長得一樣。
    """
    width: int
    height: int
    header: int = 0
    bits: int = 16
    big_endian: bool = False
    shift: Optional[int] = None
    from_header: bool = False

    @property
    def dtype(self) -> str:
        if int(self.bits) == 8:
            return "u1"
        return (">" if self.big_endian else "<") + "u2"

    def nbytes(self) -> int:
        """這個版面**應該**佔多少 byte（含檔頭）。"""
        return int(self.header) + int(self.width) * int(self.height) * (
            1 if int(self.bits) == 8 else 2)

    def describe(self) -> str:
        """一句白話 —— 給對話框與警告訊息用。

        ⚠ 檔頭讀出來的那一種**要講出來**：使用者在對話框上看到的如果是同一句
        話，他就分不出「這是量出來的」與「這是猜的」，而那兩者要做的事不一樣
        （前者確認一下就好，後者要去問機台）。
        """
        head = ("no header" if not self.header
                else "%d-byte header" % int(self.header))
        out = "%d x %d, %d-bit, %s" % (self.width, self.height,
                                       self.bits, head)
        if self.from_header:
            out += " - read %d x %d from the file header" % (self.width,
                                                             self.height)
        return out


def layout_from_header(path: str,
                       nbytes: Optional[int] = None) -> Optional[RawSpec]:
    """檔案自己的檔頭有沒有寫寬高 —— 有就回那一組，沒有回 ``None``。

    三道關**全部**要過（少一道就會開始把像素當成寬高）：

    1. 開頭 8 個 byte 是四個 little-endian u16 ``W, 0, H, 0``
       —— 中間那兩個 0 是這個格式的簽名，它們才是「這不是像素」的證據；
    2. ``W`` 與 ``H`` 落在 :data:`MIN_SIDE`–:data:`MAX_SIDE`；
    3. ``HEADER_BYTES + W × H × 2`` **逐位元組等於**檔案大小。

    ``nbytes`` 給了就不再去 stat 一次（呼叫端通常已經量過）。
    """
    p = str(path)
    try:
        with open(p, "rb") as f:
            head = f.read(8)
        size = int(nbytes) if nbytes is not None else os.path.getsize(p)
    except OSError:
        return None
    if len(head) < 8:
        return None
    words = np.frombuffer(head, dtype="<u2", count=4)
    w, z1, h, z2 = (int(v) for v in words)
    if z1 or z2:
        return None
    if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
        return None
    spec = RawSpec(width=w, height=h, header=HEADER_BYTES, bits=16,
                   from_header=True)
    return spec if spec.nbytes() == size else None


def guess_layouts(nbytes: int,
                  headers: Tuple[int, ...] = COMMON_HEADERS,
                  bits: Tuple[int, ...] = COMMON_BITS,
                  path: Optional[str] = None) -> List[RawSpec]:
    """**先讀檔頭、讀不懂才從檔案大小反推**「哪些方形版面說得通」。

    ``path`` 給了就先問 :func:`layout_from_header`。**讀得懂就只回那一個** ——
    那不是一個候選，是檔案自己講的答案，跟其他猜出來的東西擺在同一張清單上
    只會讓使用者以為他還要做一個選擇。

    ⚠ 那一條**不能**做成「猜完再排序」：3584² 那個大小本來就只有一組正方形解，
    兩條路答案一樣 —— 而非正方形的機台（7680×4320 那種）大小推不出任何東西，
    卻讀得出檔頭。先後順序就是這兩種檔案的差別。

    退回來的那條路只回**正方形**的答案，而那是刻意的：非正方形有無限多組解
    （任何一組因數都行），列出來只會讓使用者在一堆數字裡挑，而那不是幫忙。
    正方形的解通常只有 0 或 1 個 —— 有 1 個就是很強的建議，有 0 個就老實說
    推不出來，請他填。

    實測（使用者的機台，2026-09-18）：25,755,648 bytes 只有**一組**正方形解 ——
    64 KiB 檔頭 ＋ 16-bit ＋ 3584×3584，而同一個檔案的檔頭也是這樣寫的。
    """
    n = int(nbytes)
    if path is not None:
        from_head = layout_from_header(path, n)
        if from_head is not None:
            return [from_head]
    out: List[RawSpec] = []
    for hdr in headers:
        body = n - int(hdr)
        if body <= 0:
            continue
        for b in bits:
            per = 1 if b == 8 else 2
            if body % per:
                continue
            px = body // per
            side = math.isqrt(px)
            if side >= 2 and side * side == px:
                out.append(RawSpec(width=side, height=side, header=int(hdr),
                                   bits=int(b)))
    return out


def suggest_shift(arr: np.ndarray, bits: int = 16) -> int:
    """這批資料**實際用到幾位元** → 降成 8-bit 要右移幾位。

    量的是最大值，不是「檔案說它是 16-bit」：12-bit 裝在 16-bit 容器裡與滿量程
    16-bit **在檔案裡長得一模一樣**（`require_8bit` 的說明就是在講這件事），
    唯一分得出來的線索是像素值真的到了哪裡。

    ⚠ 回傳的是**建議**，而且呼叫端要把它記下來、整批共用 —— 逐張量的話兩張圖
    之間就不再可比。
    """
    if int(bits) == 8:
        return 0
    a = np.asarray(arr)
    top = int(a.max()) if a.size else 0
    used = max(1, int(top).bit_length())
    return max(0, used - 8)


def read_raw(path: str, spec: RawSpec) -> np.ndarray:
    """讀一個 `.raw` → ``(h, w)`` 的陣列。

    ``spec.shift`` 有值時降成 uint8（右移那幾位再 clip），否則**原樣回傳**
    （呼叫端要自己處理位元深度 —— `dataset.require_8bit` 會擋）。

    檔案大小跟版面對不上時**當場報錯並講出差多少**：那是「參數填錯了」最常見
    的樣子，而讀下去的話會得到一張斜掉的圖而不是一個錯誤。
    """
    p = str(path)
    want = spec.nbytes()
    try:
        got = os.path.getsize(p)
    except OSError as e:
        raise IOError("could not read %s: %s" % (p, e)) from None
    if got != want:
        raise IOError(
            "%s is %d bytes but %s needs %d - the size, the bit depth or the "
            "header length is not what this file actually is. Reading it "
            "anyway would give a skewed picture, not an error."
            % (os.path.basename(p), got, spec.describe(), want))
    count = int(spec.width) * int(spec.height)
    arr = np.fromfile(p, dtype=np.dtype(spec.dtype), count=count,
                      offset=int(spec.header))
    if arr.size != count:
        raise IOError("%s: read %d pixels, expected %d"
                      % (os.path.basename(p), arr.size, count))
    img = arr.reshape(int(spec.height), int(spec.width))
    if spec.shift is None:
        return img
    if int(spec.shift) <= 0:
        return np.clip(img, 0, 255).astype(np.uint8)
    return np.clip(np.right_shift(img, int(spec.shift)), 0, 255).astype(np.uint8)
