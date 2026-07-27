"""Tests for flexadc.core.ingest.tiff_index (structural walker + page decode)."""
from __future__ import annotations

import numpy as np
import pytest
import tifffile

from flexadc.core.ingest import tiff_index


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
