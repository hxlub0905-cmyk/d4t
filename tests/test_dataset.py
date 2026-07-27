"""Tests for flexadc.core.ingest.dataset (KLARF/TIFF/folder -> Dataset)."""
from __future__ import annotations

import numpy as np
import pytest
import tifffile

from flexadc.core.ingest import dataset, imageio

# ---------------------------------------------------------------- synthetic KLARFs

KLARF12_EBI = """FileVersion 1 2;
FileTimestamp 03-14-26 08:00:00;
LotID "LOT001";
SampleSize 1 300;
DeviceID "DEV01";
StepID "STEP01";
OrientationMarkLocation DOWN;
DiePitch 1000.0 1200.0;
WaferID "W01";
TiffFileName LOT001.tif;
TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
InspectionTest 1;
DefectRecordSpec 10 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER IMAGECOUNT IMAGELIST ;
DefectList
 1 100.500 200.500 1 2 0.5 0.5 1 2 1 0 2 0
 2 300.000 400.000 2 3 0.6 0.6 4 3 3 0 4 0 5 0;
SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;
SummaryList
 1 2 1.0000000000e-03 10 2;
EndOfFile;
"""

KLARF18_RSEM = """Record FileRecord  "1.8"
{
  Record LotRecord "LOT.01"
  {
    Record WaferRecord "W01"
    {
      Field DiePitch 2 {23376636, 32874750}

      List DefectList
      {
        Columns 8 { int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,
        int32 YINDEX,  int32 CLASSNUMBER,  int32 IMAGECOUNT,  ImageList IMAGEINFO  }
        Data 3
        {
          1 1000 2000 0 0 1 1 Image 1 { "d1.png" "PNG" 1 "24" } ;
          2 3000 4000 1 -1 2 1 Image 1 { "d2.png" "PNG" 1 "24" } ;
          3 5000 6000 1 1 2 0 ;
        }
      }
    }
  }
}
EndOfFile;
"""

KLARF12_NO_IMAGES = """FileVersion 1 2;
LotID "LOT002";
DiePitch 1000.0 1200.0;
WaferID "W02";
DefectRecordSpec 8 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER ;
DefectList
 1 10.000 20.000 0 0 0.5 0.5 1;
EndOfFile;
"""


def _write_text(path, text):
    with open(str(path), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _write_tiff(path, arrays):
    with tifffile.TiffWriter(str(path)) as tw:
        for arr in arrays:
            tw.write(arr, photometric="minisblack")


# ---------------------------------------------------------------- ebi_patch mode

@pytest.fixture()
def ebi_case(tmp_path):
    rng = np.random.default_rng(1234)
    arrays = [rng.integers(0, 256, size=(20, 30), dtype=np.uint8)
              for _ in range(5)]
    _write_tiff(tmp_path / "LOT001.tif", arrays)
    kpath = tmp_path / "LOT001.klarf"
    _write_text(kpath, KLARF12_EBI)
    return kpath, tmp_path / "LOT001.tif", arrays


def test_ebi_patch_detection_and_channels(ebi_case):
    kpath, tpath, arrays = ebi_case
    ds = dataset.load_dataset(str(kpath))
    assert ds.kind == "ebi_patch"
    assert ds.klarf is not None and ds.klarf.version == "1.2"
    assert len(ds.items) == 2

    # defect 1: image ids 1,2 -> pages 0,1 -> channels test/ref (in order)
    it0 = ds.items[0]
    assert set(it0.images) == {"test", "ref"}
    assert it0.images["test"].page == 0
    assert it0.images["ref"].page == 1
    assert it0.images["test"].path == str(tpath)

    # defect 2: 3 images -> pages 2,3,4 -> test/ref/img3
    it1 = ds.items[1]
    assert set(it1.images) == {"test", "ref", "img3"}
    assert it1.images["test"].page == 2
    assert it1.images["ref"].page == 3
    assert it1.images["img3"].page == 4

    # pixels round-trip through DefectItem.load
    assert np.array_equal(it0.load("test"), arrays[0])
    assert np.array_equal(it1.load("img3"), arrays[4])


def test_ebi_patch_nm_conversion_and_metadata(ebi_case):
    kpath, _tpath, _arrays = ebi_case
    ds = dataset.load_dataset(str(kpath))
    it0, it1 = ds.items
    # KLARF 1.2 coordinates are um; converted to nm (x1000)
    assert it0.xrel_nm == pytest.approx(100500.0)
    assert it0.yrel_nm == pytest.approx(200500.0)
    assert it0.die == (1, 2)
    assert it0.defect_id == "1"
    assert it0.klarf_row == 0
    assert it0.tags["classnumber"] == "1"
    assert it1.die == (2, 3)
    assert it1.tags["classnumber"] == "4"
    assert it0.nm_per_px is None            # not derivable yet (in-fab TBD)


def test_ebi_patch_custom_channel_order(ebi_case):
    kpath, _tpath, _arrays = ebi_case
    ds = dataset.load_dataset(str(kpath), channel_order=("t1",))
    assert set(ds.items[0].images) == {"t1", "img2"}
    assert set(ds.items[1].images) == {"t1", "img2", "img3"}


def test_ebi_patch_explicit_tiff_path(ebi_case, tmp_path):
    kpath, tpath, arrays = ebi_case
    # move the tiff to a non-default name; auto-resolution would fail
    other = tmp_path / "elsewhere.tif"
    _write_tiff(other, arrays)
    ds = dataset.load_dataset(str(kpath), tiff_path=str(other))
    assert ds.kind == "ebi_patch"
    assert ds.items[0].images["test"].path == str(other)


# ---------------------------------------------------------------- rsem mode

@pytest.fixture()
def rsem_case(tmp_path):
    rng = np.random.default_rng(99)
    a1 = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)
    a2 = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)
    imageio.save_gray(str(tmp_path / "d1.png"), a1)
    imageio.save_gray(str(tmp_path / "d2.png"), a2)
    kpath = tmp_path / "rsem.klarf"
    _write_text(kpath, KLARF18_RSEM)
    return kpath, tmp_path, (a1, a2)


def test_rsem_detection_and_paths(rsem_case):
    kpath, tdir, (a1, _a2) = rsem_case
    ds = dataset.load_dataset(str(kpath))
    assert ds.kind == "rsem"
    assert ds.klarf is not None and ds.klarf.version == "1.8"
    assert len(ds.items) == 3

    it0 = ds.items[0]
    assert set(it0.images) == {"single"}
    ref = it0.images["single"]
    assert ref.page is None
    assert ref.path == str(tdir / "d1.png")   # resolved relative to klarf dir
    assert np.array_equal(it0.load("single"), a1)

    # defect without an Image block gets no images
    assert ds.items[2].images == {}


def test_rsem_nm_passthrough_18(rsem_case):
    kpath, _tdir, _arrays = rsem_case
    ds = dataset.load_dataset(str(kpath))
    # KLARF 1.8 coordinates are already nm (x1.0)
    assert ds.items[0].xrel_nm == pytest.approx(1000.0)
    assert ds.items[0].yrel_nm == pytest.approx(2000.0)
    assert ds.items[1].die == (1, -1)
    assert ds.items[1].tags["classnumber"] == "2"


# ---------------------------------------------------------------- fallbacks

def test_imageless_klarf_graceful(tmp_path):
    kpath = tmp_path / "noimg.klarf"
    _write_text(kpath, KLARF12_NO_IMAGES)
    ds = dataset.load_dataset(str(kpath))
    assert ds.kind == "rsem"                  # metadata-only fallback
    assert len(ds.items) == 1
    assert ds.items[0].images == {}
    assert ds.items[0].xrel_nm == pytest.approx(10000.0)   # 10 um -> nm
    assert any("metadata only" in w for w in ds.warnings)


def test_missing_explicit_tiff_warns_and_falls_back(tmp_path):
    kpath = tmp_path / "LOT001.klarf"
    _write_text(kpath, KLARF12_EBI)           # no LOT001.tif written
    ds = dataset.load_dataset(str(kpath), tiff_path=str(tmp_path / "nope.tif"))
    assert ds.kind == "rsem"
    assert any("not found" in w for w in ds.warnings)


# ---------------------------------------------------------------- folder mode

def test_load_folder(tmp_path):
    rng = np.random.default_rng(5)
    a = rng.integers(0, 256, size=(10, 12), dtype=np.uint8)
    imageio.save_gray(str(tmp_path / "a.png"), a)
    _write_tiff(tmp_path / "b.tif",
                [rng.integers(0, 256, size=(8, 8), dtype=np.uint8)])
    (tmp_path / "notes.txt").write_text("not an image")

    ds = dataset.load_folder(str(tmp_path))
    assert ds.kind == "folder"
    assert ds.klarf is None
    assert [it.defect_id for it in ds.items] == ["a", "b"]
    it_a = ds.items[0]
    assert it_a.die is None and it_a.xrel_nm is None and it_a.yrel_nm is None
    assert it_a.images["single"].page is None
    assert np.array_equal(it_a.load("single"), a)


def test_load_folder_not_a_dir(tmp_path):
    ds = dataset.load_folder(str(tmp_path / "missing"))
    assert ds.kind == "folder"
    assert ds.items == []
    assert ds.warnings
