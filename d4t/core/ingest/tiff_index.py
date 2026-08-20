# Vendored into d4t on 2026-07-27.
# Source project: KLIP — file: klarf_tif_probe.py (dependency-free TIFF IFD
# walker; only the pure-struct structural reader is vendored, not the CLI /
# probe / report code).
# Adaptations:
#   - added `from __future__ import annotations` (d4t convention)
#   - extracted read_tiff_pages() + helpers (TYPE_SIZE / COMPRESSION /
#     PHOTOMETRIC / TAGS / _read_values / _page_geom) verbatim
#   - added n_pages(path)/count_pages(path): a tag-free IFD walk (dependency-free)
#   - added a cached TiffFile handle for read_page (see _tiff_handle)
#   - added read_page(path, page_index) -> np.ndarray via LAZY
#     `import tifffile` inside the function (pixel decode only there)
#   - Chinese comments kept verbatim.
"""TIFF 結構索引：只讀 IFD（不解碼像素），純標準函式庫。

支援 classic TIFF 與 BigTIFF、兩種 byte order。像素解碼（read_page）
另以 lazy import 的 tifffile 完成。
"""
from __future__ import annotations

import os
import struct
import threading
from collections import OrderedDict


# ---------------------------------------------------------------- TIFF 走訪
# 只讀 IFD 結構（不解碼像素），純標準函式庫。支援 classic TIFF 與 BigTIFF、
# 兩種 byte order。

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}

COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
               32773: "PackBits", 32946: "deflate"}

PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}

TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
        259: "compression", 262: "photometric", 270: "description",
        273: "strip_offsets", 277: "spp", 279: "strip_bytes",
        297: "page_number", 305: "software", 306: "datetime",
        322: "tile_w", 323: "tile_h", 324: "tile_offsets", 325: "tile_bytes"}


def _read_values(f, en, vtype, count, raw, big):
    """把 IFD entry 的 value/offset 解成 python 值 list。"""
    size = TYPE_SIZE.get(vtype)
    if size is None:
        return None
    total = size * count
    inline = 8 if big else 4
    if total <= inline:
        data = raw[:total]
    else:
        off = struct.unpack(en + ('Q' if big else 'I'), raw)[0]
        pos = f.tell()
        f.seek(off)
        data = f.read(total)
        f.seek(pos)
        if len(data) < total:
            return None
    if vtype == 2:                        # ASCII
        return [data.split(b'\x00')[0].decode('latin-1', 'replace')]
    fmt = {1: 'B', 3: 'H', 4: 'I', 6: 'b', 7: 'B', 8: 'h', 9: 'i',
           11: 'f', 12: 'd', 13: 'I', 16: 'Q', 17: 'q'}.get(vtype)
    if fmt is None:
        if vtype in (5, 10):              # rational
            f2 = 'I' if vtype == 5 else 'i'
            vals = struct.unpack(en + f2 * (count * 2), data)
            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
                    for i in range(0, count * 2, 2)]
        return None
    return list(struct.unpack(en + fmt * count, data))


def _open_header(f):
    """讀 TIFF 檔頭，回傳 ``(endian, is_bigtiff, first_ifd_offset)``。"""
    head = f.read(8)
    if len(head) < 8:
        raise ValueError("File too short to be a TIFF.")
    if head[:2] == b'II':
        en = '<'
    elif head[:2] == b'MM':
        en = '>'
    else:
        raise ValueError("Not a TIFF (missing II/MM byte-order mark).")
    magic = struct.unpack(en + 'H', head[2:4])[0]
    big = (magic == 43)
    if magic == 42:
        next_ifd = struct.unpack(en + 'I', head[4:8])[0]
    elif big:
        off_size, zero = struct.unpack(en + 'HH', head[4:8])
        if off_size != 8 or zero != 0:
            raise ValueError("Malformed BigTIFF header.")
        next_ifd = struct.unpack(en + 'Q', f.read(8))[0]
    else:
        raise ValueError(f"Unknown TIFF magic {magic} (expected 42 or 43).")
    return en, big, next_ifd


def count_pages(path) -> int:
    """**只數頁數**：走 IFD 鏈，但完全不解析 tag。

    為什麼要另外寫一支
    ------------------
    ``load_dataset`` 對這個 TIFF 唯一的問題是「有幾頁」（拿去跟 KLARF 的
    defect 數對映），但它以前是呼叫 :func:`read_tiff_pages` —— 那支會**每一頁
    都把所有認得的 tag 讀出來**，而讀 tag 常常要為了 out-of-line 的值再 seek
    一次。實測 4000 頁要 116 ms，而那份資料除了 ``n_pages`` 以外一個欄位都沒被
    用到。

    這一支每頁只做三件事：seek 到 IFD、讀 entry 數、跳過那些 entry 讀下一個
    IFD 位址。同樣是純標準函式庫。

    ⚠ 廠內的 TIFF 可能放在網路碟上，那裡每一次 seek 都是一次來回 —— 少做的
    seek 不只是省 CPU。
    """
    with open(path, 'rb') as f:
        en, big, next_ifd = _open_header(f)
        seen = set()
        n = 0
        while next_ifd:
            _guard_chain(next_ifd, seen, n, path)
            seen.add(next_ifd)
            next_ifd = _ifd_step(f, next_ifd, en, big)
            n += 1
        return n


#: 走一個 IFD 的時候一次讀多少 bytes。
#:
#: 一個 IFD 是 ``2 + 12×tag數 + 4``；廠內那份 KLARF 的 TIFF 有 73 個 tag =
#: 882 bytes，所以 2 KB 幾乎一定一次讀完 → **一頁一次來回**。以前是兩次
#: （先讀 entry 數、再 seek 過去讀下一個位址），而在網路碟上「來回次數」
#: 就是全部的成本：實測 30962 頁走完要 106 秒，同一個檔複製到本機只要 0.25 秒。
_IFD_CHUNK = 2048


def _ifd_step(f, offset, en, big):
    """走一個 IFD，回傳**下一個** IFD 的位址（0 = 這是最後一頁）。

    不解析任何 tag —— 只要 entry 數（才知道要跳多遠）與鏈上的下一個位址。
    先讀一整塊（見 :data:`_IFD_CHUNK`）：多數 IFD 一次就讀完了，
    只有 tag 特別多的才要補第二次。
    """
    esize = 20 if big else 12
    n_off = 8 if big else 4
    count_size = 8 if big else 2
    f.seek(offset)
    chunk = f.read(_IFD_CHUNK)
    if len(chunk) < count_size:
        raise ValueError("TIFF page directory at %d is truncated." % offset)
    n_entries = struct.unpack(en + ('Q' if big else 'H'),
                              chunk[:count_size])[0]
    end = count_size + esize * n_entries
    if end + n_off <= len(chunk):
        return struct.unpack(en + ('Q' if big else 'I'),
                             chunk[end:end + n_off])[0]
    f.seek(offset + end)                       # tag 多到一塊裝不下
    tail = f.read(n_off)
    if len(tail) < n_off:
        raise ValueError("TIFF page directory at %d is truncated." % offset)
    return struct.unpack(en + ('Q' if big else 'I'), tail)[0]


#: IFD 鏈最多走幾頁。**這是「這個檔大得不合理」的界線，不是「壞掉」的界線。**
#:
#: 以前是 10 萬，而且超過就報「IFD chain loops — corrupt TIFF」——
#: 一份 5 萬顆 defect、一顆 2 張圖的 lot 剛好落在那條線上，於是使用者拿到的是
#: 「你的 TIFF 壞了」（它沒壞），而 `load_dataset` 接住那個例外之後
#: **把 kind 退成 rsem、每一顆 0 張圖**：載得進來、有 defect、就是沒有影像。
#: 那是 2026-08-20 使用者回報的「幾萬顆會超級無敵久或直接不載入」的第二半。
#:
#: 100 萬頁 = 25 萬顆 defect × 4 張，比任何真的 lot 都大一個級距；而 `seen`
#: 那個集合在這個上限下最多也才幾十 MB。
MAX_PAGES = 1_000_000


def _guard_chain(next_ifd: int, seen: set, n_done: int, path) -> None:
    """走下一個 IFD 之前的兩道檢查 —— **而且兩句話不一樣**。

    「繞回自己」是真的壞檔；「太多頁」是這個檔太大。以前兩者共用一句
    「corrupt TIFF」，於是一份好好的大 lot 被說成壞檔。
    """
    if next_ifd in seen:
        raise ValueError(
            "This TIFF's page chain loops back on itself, so the file is "
            "damaged (page %d points at somewhere already visited): %s"
            % (n_done + 1, path))
    if n_done >= MAX_PAGES:
        raise ValueError(
            "This TIFF has more than %d pages, which is past what d4t walks "
            "in one go: %s" % (MAX_PAGES, path))


def read_tiff_pages(path, max_pages=None):
    """回傳 (pages, info)。pages = [dict,...]（每頁一筆），info = 檔案層資訊。

    要**完整的每頁資訊**（`fab_probe` 的報告、健檢）才用這支；只要頁數請用
    :func:`count_pages`，它便宜一個數量級。

    ``max_pages`` = 只讀前幾頁就停（``info["n_pages"]`` 因此是**讀到的頁數**，
    不是檔案的頁數）。給「只想看看這個檔長什麼樣」的呼叫者用 —— 這支會把
    每一頁的每一個 tag 都讀出來，而讀 tag 常常要為了 out-of-line 的值再 seek
    一次，在網路碟上那是一頁好幾次來回。
    """
    pages = []
    with open(path, 'rb') as f:
        en, big, next_ifd = _open_header(f)

        seen = set()
        while next_ifd:
            if max_pages is not None and len(pages) >= int(max_pages):
                break                       # 只要前幾頁（見 docstring）
            _guard_chain(next_ifd, seen, len(pages), path)
            seen.add(next_ifd)
            f.seek(next_ifd)
            n = struct.unpack(en + ('Q' if big else 'H'),
                              f.read(8 if big else 2))[0]
            page = {"index": len(pages), "ifd_offset": next_ifd}
            esize = 20 if big else 12
            entries = f.read(esize * n)
            for k in range(n):
                e = entries[k * esize:(k + 1) * esize]
                tag, vtype = struct.unpack(en + 'HH', e[:4])
                if big:
                    count = struct.unpack(en + 'Q', e[4:12])[0]
                    raw = e[12:20]
                else:
                    count = struct.unpack(en + 'I', e[4:8])[0]
                    raw = e[8:12]
                name = TAGS.get(tag)
                if name is None:
                    continue
                vals = _read_values(f, en, vtype, count, raw, big)
                if vals is None:
                    continue
                page[name] = vals[0] if len(vals) == 1 else vals
            b = page.get("strip_bytes", page.get("tile_bytes", 0))
            page["data_bytes"] = sum(b) if isinstance(b, list) else b
            pages.append(page)
            next_ifd = struct.unpack(en + ('Q' if big else 'I'),
                                     f.read(8 if big else 4))[0]

    info = {"byte_order": "little-endian (II)" if en == '<' else "big-endian (MM)",
            "bigtiff": big, "n_pages": len(pages),
            "file_bytes": os.path.getsize(path)}
    return pages, info


def _page_geom(p):
    bits = p.get("bits", "?")
    if isinstance(bits, list):
        bits = "/".join(str(b) for b in bits)
    return (f'{p.get("width", "?")}x{p.get("height", "?")} '
            f'{bits}-bit {COMPRESSION.get(p.get("compression", 1), "compression?")} '
            f'{PHOTOMETRIC.get(p.get("photometric", -1), "")}'.strip())


# ------------------------------------------------------- d4t additions

def n_pages(path) -> int:
    """回傳多頁 TIFF 的頁數（純 IFD 走訪，不解碼像素、不需第三方套件）。"""
    return count_pages(path)


#: `bit_depths` 預設看幾頁。**一份 lot 的 TIFF 是同一台機台一次寫出來的**，
#: 位元深度不會第 3 萬頁才變 —— 而為了那個假設走完整份檔案，在 4 萬頁的合成
#: 資料上實測要 1.0 秒（整個 `load_dataset` 才 1.56 秒），在網路碟上是把整份
#: 檔案的 IFD 連同每個 tag 的 out-of-line 值都拉一遍。
#:
#: 這個檢查本來就只是**提前警告**（把 `require_8bit` 的守門提前到按下 Open 的
#: 那一刻）。真正的守門在每一顆的 `require_8bit`，那裡看的是解出來的像素 ——
#: 所以「看前幾頁」漏掉的那種檔案，仍然會在跑到它的時候被擋下來。
BIT_DEPTH_SAMPLE_PAGES = 8


def bit_depths(path, max_pages=BIT_DEPTH_SAMPLE_PAGES) -> list:
    """這個 TIFF 裡出現過的位元深度（排序、去重）—— **不解碼像素**（F11）。

    ``BitsPerSample`` 就在 IFD 的 tag 裡，所以「這批資料是幾 bit」在**載入的
    時候**就答得出來，不必等跑到某一顆才發現。彩色頁的 tag 是一串（每個 sample
    一個值），這裡把它攤平。

    **只看前 ``max_pages`` 頁**（``None`` = 全部）——理由見
    :data:`BIT_DEPTH_SAMPLE_PAGES`。

    讀不出來（壞檔、非 TIFF）→ 回空 list：位元深度的檢查不該讓載入失敗，
    真正的守門在 ``dataset.require_8bit``（那裡看的是解出來的像素）。
    """
    out = set()
    try:
        pages, _info = read_tiff_pages(str(path), max_pages=max_pages)
    except (OSError, ValueError, struct.error):
        return []
    for p in pages:
        bits = p.get("bits")
        if isinstance(bits, list):
            out.update(int(b) for b in bits)
        elif bits is not None:
            out.add(int(bits))
    return sorted(out)


# --------------------------------------------------------------------------- #
# 開著的 TIFF handle 快取
# --------------------------------------------------------------------------- #
#: ``path -> (TiffFile, stat_key)``。只留少數幾個 —— 一個 lot 通常就一個 TIFF。
_OPEN: "OrderedDict[str, tuple]" = OrderedDict()
_OPEN_MAX = 4
#: RLock：``read_page`` 全程持有，而它會呼叫也要拿鎖的取 handle。
_OPEN_LOCK = threading.RLock()


def _stat_key(path):
    st = os.stat(path)
    # **pid 是版本鍵的一部分**，這不是多餘的。
    #
    # 批次是 fork 出來的（`batch._pool_context`：主執行緒 fork）。fork 會把父
    # 行程開著的檔案描述子複製給每一個子行程，而複製出來的 fd **共用同一個檔案
    # 偏移量** —— 於是四個 worker 各自 seek 再 read，會互相把對方的位置移掉，
    # 讀回來的是別頁的位元組。那不會丟例外、不會變慢，只會讓某幾顆 defect 拿到
    # 錯的影像。
    #
    # 帶上 pid，子行程一進來就發現「這個 handle 不是我的」而重開一個自己的。
    return (os.getpid(), st.st_mtime_ns, st.st_size)


class _PageIndex:
    """一個 TIFF 的 IFD 位置表 —— **用到第幾頁才走到第幾頁**（2026-08-20）。

    為什麼不是一次走完
    ------------------
    以前開檔的當下就 ``len(tf.pages)``，逼 tifffile 把整條 IFD 鏈走完一次
    （見下面 :func:`_tiff_handle_locked` 的說明：那是為了修「讀過像素之後
    再解析下一頁會從錯的位置開始」）。在本機那是幾百毫秒，在**網路碟**上是
    使用者實測的 **106 秒**（30962 頁）—— 而那 106 秒是在他還沒看到任何一張
    圖之前付的。

    但那一趟本來就不必付：Studio 一次看一顆，一顆兩張圖 = 兩個 IFD。
    走到第幾頁記到第幾頁，逐顆瀏覽就是逐頁往前 —— **只有真的跑整批才會走完
    整條鏈，而跑整批本來就要把每一頁的像素都讀過一遍**（那才是 592 MB 的來源）。

    「讀過像素之後位置跑掉」怎麼解：**每次讀都自己 seek 到那一頁的 IFD**
    （位置就在這張表裡），所以不再依賴檔案位置的連續性。那也是不用 tifffile
    走完整條鏈的原因。
    """

    def __init__(self, en, big, first_ifd, path):
        self._en, self._big = en, bool(big)
        self._next = int(first_ifd)
        self._path = str(path)
        self.offsets = []
        self._seen = set()

    @property
    def complete(self):
        return self._next == 0

    def _step(self, fh):
        """再往前走一頁；走完了回 False。"""
        if self._next == 0:
            return False
        off = self._next
        _guard_chain(off, self._seen, len(self.offsets), self._path)
        self._seen.add(off)
        self._next = _ifd_step(fh, off, self._en, self._big)
        self.offsets.append(off)
        return True

    def offset_of(self, index, fh):
        """第 ``index`` 頁的 IFD 位置（不夠就往前走）。超出範圍回 ``None``。"""
        if index < 0:
            return None
        while len(self.offsets) <= index and self._step(fh):
            pass
        return self.offsets[index] if index < len(self.offsets) else None

    def count(self, fh):
        """總頁數 —— **會把鏈走完**，所以只在真的要那個數字時問。"""
        while self._step(fh):
            pass
        return len(self.offsets)


def _tiff_handle_locked(path):
    """拿一個開好的 ``tifffile.TiffFile``（同一個檔就重複使用）。

    **呼叫端必須持有 ``_OPEN_LOCK``**（見 :func:`read_page` 的說明）。

    為什麼要快取
    ------------
    ``read_page`` 以前每次呼叫都 ``with tifffile.TiffFile(path)`` 開一次檔，
    而且用 ``len(tf.pages)`` 檢查範圍 —— **那一行會強迫 tifffile 走完整條 IFD
    鏈**。於是「換下一顆 defect」＝ 兩張圖 ＝ 兩次全檔走訪：實測一個 4000 頁的
    TIFF 每張圖 16 ms，而那張圖本身只有 16 KB。整條 pipeline 才 9 ms，
    所以絕大部分的等待花在重複打開同一個檔案上。

    快取以 ``(mtime_ns, size)`` 當版本：檔案被換掉就重開，不會餵回舊內容。

    行程內共用，所以要鎖 —— 預覽跑在 QThread、批次跑在子行程（各自一份快取）。
    """
    import tifffile  # lazy: pixel decode only; structural code above stays pure-stdlib

    path = str(path)
    key = _stat_key(path)
    with _OPEN_LOCK:                      # RLock：呼叫端通常已經持有
        hit = _OPEN.get(path)
        if hit is not None and hit[1] == key:
            _OPEN.move_to_end(path)
            return hit[0], hit[2]
        if hit is not None:               # 檔案變了：關掉舊的
            try:
                hit[0].close()
            except Exception:             # noqa: BLE001 — 關檔失敗不該擋住讀取
                pass
            _OPEN.pop(path, None)
        tf = tifffile.TiffFile(path)
        # **開檔的當下就把整份頁面清單建起來，一次。**
        #
        # tifffile 的 ``tf.pages`` 是 lazy 的：索引到第 i 頁才去解析那一段 IFD，
        # 而它靠的是「檔案位置停在上一頁結尾」這個內部狀態。問題是
        # ``page.asarray()`` 會為了讀像素移動檔案位置 —— 所以「讀第 0 頁的像素、
        # 再要第 1 頁」在**同一個 handle** 上會從錯的位置開始解析，tifffile 丟出
        # ``suspicious number of tags 8827`` 之類的訊息。
        #
        # 以前每次讀都重開檔，所以碰不到；快取住 handle 之後它每次換 defect 都
        # 會發生（實測第二張圖必失敗）。當時的解法是 ``len(tf.pages)`` —— 逼
        # tifffile 把清單一次走完，之後的索引就只是查表。
        #
        # **2026-08-20 換掉了那個解法。** 走完整條鏈在網路碟上是 106 秒
        # （使用者實測，30962 頁），而且那是在他看到第一張圖之前付的。
        # 現在改成：自己維護一張**用到哪裡才走到哪裡**的 IFD 位置表
        # （:class:`_PageIndex`），每次讀都先 seek 到那一頁的 IFD ——
        # 位置的連續性從此不影響任何東西，而該走的頁數等於真的讀到的頁數。
        fh = tf.filehandle
        fh.seek(0)
        en, big, first = _open_header(fh)
        index = _PageIndex(en, big, first, path)
        _OPEN[path] = (tf, key, index)
        while len(_OPEN) > _OPEN_MAX:
            _old, (old_tf, _k, _i) = _OPEN.popitem(last=False)
            try:
                old_tf.close()
            except Exception:             # noqa: BLE001
                pass
        return tf, index


def close_cached_tiffs() -> None:
    """關掉所有快取的 TIFF handle（換 lot、關視窗、測試收尾時呼叫）。"""
    with _OPEN_LOCK:
        for tf, _key, _index in _OPEN.values():
            try:
                tf.close()
            except Exception:             # noqa: BLE001
                pass
        _OPEN.clear()


def read_page(path, page_index):
    """解碼並回傳第 page_index（0-based）頁的像素 (np.ndarray)。

    像素解碼交給 tifffile（lazy import：只有真的要讀像素才需要它）。
    檔案 handle 會被快取重複使用，見 :func:`_tiff_handle`。

    **整段讀取是序列化的**（鎖從拿 handle 一路持有到 ``asarray()`` 回來）。
    一個 ``TiffFile`` 底下就是一個檔案描述子，而讀一頁像素是「seek 到那一頁、
    讀下去」—— 兩個執行緒共用同一個 handle 就會互相把位置移掉，讀回來的是別頁
    的位元組。Studio 真的會這樣：點一張卡會排一次背景預覽，而使用者可能同時
    觸發另一次，兩個執行緒就同時進來了。實測症狀是 tifffile 丟
    ``suspicious number of tags 13111`` —— 它把像素當成 IFD 在解析。

    這跟 :func:`_stat_key` 裡的 pid 是同一件事的兩半：**fork 出來的子行程共用
    偏移量、同一行程的執行緒共用 handle**。前者用版本鍵擋，後者用鎖擋。

    序列化的代價可以忽略：一次讀 0.4 ms，而預覽本來就有請求合併。
    """
    import tifffile  # lazy: 同 _tiff_handle_locked

    with _OPEN_LOCK:
        tf, index = _tiff_handle_locked(path)
        fh = tf.filehandle
        off = index.offset_of(int(page_index), fh)
        if off is None:
            # **只有真的超出範圍才走完整條鏈**（為了講得出「總共幾頁」）。
            n = index.count(fh)
            raise IndexError(
                f"TIFF page {page_index} out of range (0..{n - 1})")
        # 自己 seek 到那一頁的 IFD，所以「上一次讀像素把位置移到哪」不重要。
        fh.seek(off)
        return tifffile.TiffPage(tf, index=int(page_index)).asarray()
