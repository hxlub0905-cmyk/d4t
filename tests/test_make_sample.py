"""Tests for tools/make_sample.py — synthetic EBI patch lot generator."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

from d4t.core.ingest import dataset, klarf_core, tiff_index

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import make_sample  # noqa: E402


N = 8


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("synlot")
    return make_sample.generate(str(out / "lot"), n=N, seed=7)


def test_klarf_parses_and_image_map(lot):
    doc = klarf_core.load(lot["klarf"])
    assert doc.version == "1.2"
    assert doc.tiff_file_name == "LOT_SYN.tif"
    assert doc.tiff_spec == {"version": "6.1", "nfields": 1, "fields": ["IMAGENUMBER"]}
    assert len(doc.defects) == N

    npages = tiff_index.n_pages(lot["tiff"])
    assert npages == 2 * N
    imap = doc.defect_image_map(npages)
    assert imap["mode"] == "imagelist"
    assert imap["base"] == 1                       # IMAGELIST 是 1-based 頁碼
    for i, pages in enumerate(imap["pages"]):
        assert pages == [2 * i, 2 * i + 1]         # test, ref（0-based）


def test_load_dataset_ebi_patch_pairs(lot):
    ds = dataset.load_dataset(lot["klarf"])
    assert ds.kind == "ebi_patch"
    assert len(ds.items) == N
    for i, it in enumerate(ds.items):
        assert set(it.images) == {"test", "ref"}
        assert it.images["test"].page == 2 * i
        assert it.images["ref"].page == 2 * i + 1
        t = it.load("test")
        r = it.load("ref")
        assert t.shape == (128, 128) and t.dtype == np.uint8
        assert r.shape == (128, 128) and r.dtype == np.uint8
        assert not np.array_equal(t, r)            # 獨立雜訊 + 平移
        # 座標落在假 die 內（KLARF 1.2 µm → nm）
        assert 0 < it.xrel_nm < 5000 * 1000
        assert 0 < it.yrel_nm < 5000 * 1000


def test_ground_truth_consistent(lot):
    with open(lot["ground_truth"], "r", encoding="utf-8") as f:
        gt = json.load(f)
    ds = dataset.load_dataset(lot["klarf"])
    assert set(gt) == {it.defect_id for it in ds.items}
    n_real = sum(1 for v in gt.values() if v["is_real"])
    assert n_real == round(N * 0.5)                # 預設 real_frac=0.5
    for v in gt.values():
        assert set(v) == {"is_real", "type"}
        if v["is_real"]:
            assert v["type"] in make_sample.REAL_TYPES
        else:
            assert v["type"] == make_sample.NUISANCE_TYPE
    # is_real ⟺ type != "none"
    assert all(v["is_real"] == (v["type"] != "none") for v in gt.values())


def test_same_seed_identical_tiff_bytes(tmp_path):
    p1 = make_sample.generate(str(tmp_path / "a"), n=4, seed=42)
    p2 = make_sample.generate(str(tmp_path / "b"), n=4, seed=42)
    with open(p1["tiff"], "rb") as f:
        b1 = f.read()
    with open(p2["tiff"], "rb") as f:
        b2 = f.read()
    assert b1 == b2                                 # 同 seed → 位元組完全相同
    with open(p1["klarf"], "rb") as f:
        k1 = f.read()
    with open(p2["klarf"], "rb") as f:
        k2 = f.read()
    assert k1 == k2

    p3 = make_sample.generate(str(tmp_path / "c"), n=4, seed=43)
    with open(p3["tiff"], "rb") as f:
        b3 = f.read()
    assert b1 != b3                                 # 不同 seed → 不同資料


def test_cli_main(tmp_path, capsys):
    rc = make_sample.main([str(tmp_path / "cli"), "--n", "2", "--seed", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "LOT_SYN.001" in out
    assert os.path.isfile(str(tmp_path / "cli" / "LOT_SYN.tif"))
    assert os.path.isfile(str(tmp_path / "cli" / "ground_truth.json"))


def test_bad_args_raise(tmp_path):
    with pytest.raises(ValueError):
        make_sample.generate(str(tmp_path / "x"), n=0)
    with pytest.raises(ValueError):
        make_sample.generate(str(tmp_path / "x"), real_frac=1.5)
    with pytest.raises(ValueError):
        make_sample.generate(str(tmp_path / "x"), size=16, pitch=16)
