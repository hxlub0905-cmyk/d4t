"""Tests for d4t.core.ingest.tiff_index (structural walker + page decode)."""
from __future__ import annotations

import os

import numpy as np
import pytest
import tifffile

from d4t.core.ingest import tiff_index


def _write_multipage(path, arrays):
    with tifffile.TiffWriter(str(path)) as tw:
        for arr in arrays:
            tw.write(arr, photometric="minisblack")


@pytest.fixture()
def pages4(tmp_path):
    rng = np.random.default_rng(42)
    arrays = [
        rng.integers(0, 256, size=(32, 48), dtype=np.uint8),
        rng.integers(0, 256, size=(32, 48), dtype=np.uint8),
        rng.integers(0, 65536, size=(16, 24), dtype=np.uint16),
        rng.integers(0, 256, size=(16, 24), dtype=np.uint8),
    ]
    p = tmp_path / "multi.tif"
    _write_multipage(p, arrays)
    return p, arrays


def test_read_tiff_pages_counts_and_dims(pages4):
    p, arrays = pages4
    pages, info = tiff_index.read_tiff_pages(str(p))
    assert info["n_pages"] == 4
    assert not info["bigtiff"]
    assert len(pages) == 4
    for k, (page, arr) in enumerate(zip(pages, arrays)):
        assert page["index"] == k
        assert page["width"] == arr.shape[1]
        assert page["height"] == arr.shape[0]
    assert pages[2]["bits"] == 16
    assert pages[0]["bits"] == 8


def test_n_pages(pages4):
    p, _arrays = pages4
    assert tiff_index.n_pages(str(p)) == 4


def test_read_page_pixel_identical(pages4):
    p, arrays = pages4
    for k, arr in enumerate(arrays):
        out = tiff_index.read_page(str(p), k)
        assert out.dtype == arr.dtype
        assert np.array_equal(out, arr)


def test_read_page_out_of_range(pages4):
    p, _arrays = pages4
    with pytest.raises(IndexError):
        tiff_index.read_page(str(p), 4)


def test_bigtiff(tmp_path):
    rng = np.random.default_rng(7)
    arrays = [rng.integers(0, 256, size=(8, 12), dtype=np.uint8)
              for _ in range(2)]
    p = tmp_path / "big.tif"
    with tifffile.TiffWriter(str(p), bigtiff=True) as tw:
        for arr in arrays:
            tw.write(arr, photometric="minisblack")
    pages, info = tiff_index.read_tiff_pages(str(p))
    assert info["bigtiff"]
    assert info["n_pages"] == 2
    assert pages[0]["width"] == 12 and pages[0]["height"] == 8
    assert np.array_equal(tiff_index.read_page(str(p), 1), arrays[1])


def test_not_a_tiff_raises(tmp_path):
    p = tmp_path / "nottiff.bin"
    p.write_bytes(b"PNGnottiff-data!")
    with pytest.raises(ValueError):
        tiff_index.read_tiff_pages(str(p))


# --------------------------------------------------------------------------- #
# 效能那一輪（2026-07-31）：只數頁的走訪 + 快取住的檔案 handle
# --------------------------------------------------------------------------- #
def test_count_pages_agrees_with_the_full_walk(pages4):
    """便宜的那支跟貴的那支**必須give 同一個答案** —— 不然省下來的時間是假的。"""
    p, _arrays = pages4
    _pages, info = tiff_index.read_tiff_pages(str(p))
    assert tiff_index.count_pages(str(p)) == info["n_pages"] == 4


def test_count_pages_handles_bigtiff(tmp_path):
    rng = np.random.default_rng(7)
    arrays = [rng.integers(0, 256, size=(8, 8), dtype=np.uint8) for _ in range(3)]
    p = tmp_path / "big.tif"
    with tifffile.TiffWriter(str(p), bigtiff=True) as tw:
        for arr in arrays:
            tw.write(arr, photometric="minisblack")
    assert tiff_index.count_pages(str(p)) == 3


def test_count_pages_still_rejects_a_non_tiff(tmp_path):
    p = tmp_path / "nope.txt"
    p.write_text("not a tiff", encoding="utf-8")
    with pytest.raises(ValueError):
        tiff_index.count_pages(str(p))


def test_the_file_is_opened_once_not_once_per_page(pages4, monkeypatch):
    """換一顆 defect 要讀兩張圖，以前那是**兩次全檔走訪**。

    一個 4000 頁的 TIFF 實測每張圖 16 ms，而圖本身只有 16 KB —— 整條 pipeline
    才 9 ms，所以等待幾乎都花在重複打開同一個檔上。這條測試鎖住「同一個檔只開
    一次」，因為那個成本在本機小檔上看不出來（而廠內的檔在網路碟上）。
    """
    p, arrays = pages4
    tiff_index.close_cached_tiffs()

    opened = []
    real = tifffile.TiffFile

    class Counting(real):
        def __init__(self, *a, **kw):
            opened.append(a[0] if a else kw.get("arg"))
            super().__init__(*a, **kw)

    monkeypatch.setattr(tifffile, "TiffFile", Counting)
    try:
        for _ in range(5):
            for page in range(4):
                tiff_index.read_page(str(p), page)
    finally:
        monkeypatch.undo()
        tiff_index.close_cached_tiffs()
    assert len(opened) == 1, "20 次讀取只該開一次檔，實際開了 %d 次" % len(opened)


def test_a_replaced_file_is_not_served_from_the_cache(tmp_path):
    """快取最糟的失敗方式：檔案換了還餵回舊像素。

    那不會報錯、不會變慢，只會讓使用者對著一張**上一批的圖**調參數。
    版本鍵是 (mtime, size)，所以換檔就重開。
    """
    p = tmp_path / "swap.tif"
    first = np.full((8, 8), 10, dtype=np.uint8)
    _write_multipage(p, [first])
    tiff_index.close_cached_tiffs()
    assert int(tiff_index.read_page(str(p), 0)[0, 0]) == 10

    second = np.full((8, 8), 200, dtype=np.uint8)
    _write_multipage(p, [second])
    os.utime(str(p), (0, 0))          # 明確改 mtime（同大小也要能分辨）
    assert int(tiff_index.read_page(str(p), 0)[0, 0]) == 200
    tiff_index.close_cached_tiffs()


def test_out_of_range_still_says_the_page_count(pages4):
    """錯誤訊息仍然要講得出「總共幾頁」—— 那一行是使用者唯一的線索。

    只是它現在只在**出錯時**才去問（問一次就要走完整條 IFD 鏈）。
    """
    p, _arrays = pages4
    with pytest.raises(IndexError) as ei:
        tiff_index.read_page(str(p), 99)
    assert "0..3" in str(ei.value)


def test_a_forked_child_does_not_reuse_the_parents_handle(tmp_path):
    """fork 出來的子行程**不可以**沿用父行程開著的 handle。

    fork 複製的 fd 共用同一個檔案偏移量，所以幾個 worker 同時 seek+read 會互相
    把對方的位置移掉，讀回來的是別頁的位元組 —— 不丟例外、不變慢，只是某幾顆
    defect 拿到錯的影像。批次正是主執行緒 fork 出來的（`batch._pool_context`）。

    Windows 沒有 fork（走 spawn，天生各自開檔），所以這條只在有 fork 的平台跑。
    """
    if not hasattr(os, "fork"):
        pytest.skip("no fork on this platform")

    arrays = [np.full((8, 8), v, dtype=np.uint8) for v in (11, 22, 33, 44)]
    p = tmp_path / "forked.tif"
    _write_multipage(p, arrays)

    tiff_index.close_cached_tiffs()
    tiff_index.read_page(str(p), 0)            # 父行程先把 handle 開起來

    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:                               # --- 子行程 ---
        try:
            os.close(r)
            vals = bytes(int(tiff_index.read_page(str(p), i)[0, 0])
                         for i in range(4))
            os.write(w, vals)
            os.close(w)
        finally:
            os._exit(0)
    os.close(w)
    got = os.read(r, 4)
    os.close(r)
    os.waitpid(pid, 0)
    tiff_index.close_cached_tiffs()
    assert list(got) == [11, 22, 33, 44]


def test_two_threads_reading_the_same_file_do_not_corrupt_each_other(tmp_path):
    """同一行程的兩個執行緒共用一個 handle，會互相把檔案位置移掉。

    一個 ``TiffFile`` 底下就是一個檔案描述子，而讀一頁像素是「seek 到那一頁、
    讀下去」。兩個執行緒交錯做這件事，讀回來的是別頁的位元組 —— 實測 tifffile
    會丟 ``suspicious number of tags 13111``（它把像素當成 IFD 在解析）。

    Studio 真的會這樣：點一張卡會排一次背景預覽，同步預覽又跑一次，
    於是兩個執行緒同時進來。這條測試在加鎖之前**必失敗**。

    這跟 fork 那條是同一件事的兩半：子行程共用偏移量、執行緒共用 handle。
    """
    import threading

    arrays = [np.full((16, 16), v, dtype=np.uint8) for v in (10, 60, 110, 160)]
    p = tmp_path / "threads.tif"
    _write_multipage(p, arrays)
    tiff_index.close_cached_tiffs()

    errors = []
    wrong = []

    def hammer(page, want):
        for _ in range(30):
            try:
                got = tiff_index.read_page(str(p), page)
            except Exception as e:                       # noqa: BLE001
                errors.append("%s" % e)
                return
            if int(got[0, 0]) != want:
                wrong.append((page, int(got[0, 0])))
                return

    threads = [threading.Thread(target=hammer, args=(i, v))
               for i, v in enumerate((10, 60, 110, 160))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    tiff_index.close_cached_tiffs()
    assert not errors, errors[:3]
    assert not wrong, "讀到別頁的像素：%r" % wrong[:3]


# --------------------------------------------------------------------------- #
# 「幾萬顆會直接不載入」（2026-08-20 使用者回報）
# --------------------------------------------------------------------------- #
def _tiny_multipage(path, n, loop=False):
    """N 頁的最小 TIFF（每頁 1×1、8-bit）。

    用手寫的而不是 tifffile：這裡要驗的是**IFD 鏈有多長**，而 11 萬頁真的影像
    是 GB 級的檔案。1×1 的頁讓同一條鏈只要 10 MB。``loop=True`` 讓最後一頁的
    next-IFD 指回第一頁 —— 那才是「壞檔」該長的樣子。
    """
    import struct

    tags = [(256, 3, 1), (257, 3, 1), (258, 3, 1), (259, 3, 1), (262, 3, 1),
            (273, 4, 1), (278, 3, 1), (279, 4, 1)]
    ifd_size = 2 + 12 * len(tags) + 4
    data_start, ifd_start = 8, 8 + n
    with open(str(path), "wb") as f:
        f.write(b"II" + struct.pack("<HI", 42, ifd_start))
        f.write(b"\x80" * n)
        for i in range(n):
            here = ifd_start + i * ifd_size
            if i < n - 1:
                nxt = here + ifd_size
            else:
                nxt = ifd_start if loop else 0
            vals = {256: 1, 257: 1, 258: 8, 259: 1, 262: 1,
                    273: data_start + i, 278: 1, 279: 1}
            out = struct.pack("<H", len(tags))
            for tag, vtype, count in tags:
                v = vals[tag]
                raw = (struct.pack("<H", v) + b"\0\0" if vtype == 3
                       else struct.pack("<I", v))
                out += struct.pack("<HHI", tag, vtype, count) + raw
            f.write(out + struct.pack("<I", nxt))
    return str(path)


def test_a_lot_with_more_than_a_hundred_thousand_pages_still_loads(tmp_path):
    """5 萬顆 defect × 一顆 2 張 = 10 萬頁 —— 舊的上限就畫在那裡。

    而它失敗的方式最糟：`load_dataset` 接住那個例外之後**把 kind 退成 rsem、
    每一顆 0 張圖**，於是「載得進來、有 defect、就是沒有影像」，
    而唯一的線索是一句「你的 TIFF 壞了」（它沒壞）。
    """
    p = _tiny_multipage(tmp_path / "many.tif", 110_000)
    assert tiff_index.n_pages(p) == 110_000
    assert tiff_index.bit_depths(p) == [8]


def test_too_many_pages_and_a_damaged_file_do_not_say_the_same_thing(tmp_path,
                                                                    monkeypatch):
    """「太多頁」是這個檔太大，「繞回自己」才是壞檔。

    共用一句話的代價是實際發生過的那一次：一份好好的大 lot 被說成壞檔，
    而使用者照那句話去查檔案，查不出任何東西。
    """
    monkeypatch.setattr(tiff_index, "MAX_PAGES", 20)

    ok = _tiny_multipage(tmp_path / "ok.tif", 20)
    assert tiff_index.n_pages(ok) == 20                  # 剛好在界線上

    too_many = _tiny_multipage(tmp_path / "big.tif", 40)
    with pytest.raises(ValueError) as e:
        tiff_index.n_pages(too_many)
    assert "more than 20 pages" in str(e.value)
    assert "damage" not in str(e.value) and "loop" not in str(e.value)

    looped = _tiny_multipage(tmp_path / "loop.tif", 4, loop=True)
    with pytest.raises(ValueError) as e:
        tiff_index.n_pages(looped)
    assert "loops back" in str(e.value) and "damaged" in str(e.value)


def test_the_bit_depth_check_only_looks_at_the_first_few_pages(tmp_path,
                                                               monkeypatch):
    """位元深度是**提前警告**，不是守門 —— 守門在每一顆的 `require_8bit`。

    為了那個假設走完整份檔案，在 4 萬頁上實測是 1.0 秒（整個 `load_dataset`
    才 1.56 秒），而在網路碟上是把整份檔案的 IFD 連同每個 tag 的 out-of-line
    值都拉一遍。
    """
    seen = {}
    real = tiff_index.read_tiff_pages

    def spy(path, max_pages=None):
        seen["max_pages"] = max_pages
        return real(path, max_pages=max_pages)

    monkeypatch.setattr(tiff_index, "read_tiff_pages", spy)
    p = _tiny_multipage(tmp_path / "many.tif", 500)
    assert tiff_index.bit_depths(p) == [8]
    assert seen["max_pages"] == tiff_index.BIT_DEPTH_SAMPLE_PAGES

    pages, info = tiff_index.read_tiff_pages(p, max_pages=3)
    assert len(pages) == 3 and info["n_pages"] == 3      # 讀到的頁數，不是檔案的
