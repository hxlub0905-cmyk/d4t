"""Tests for adept.core.ingest.tiff_index (structural walker + page decode)."""
from __future__ import annotations

import os

import numpy as np
import pytest
import tifffile

from adept.core.ingest import tiff_index


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
