"""Tests for d4t.core.ingest.klarf_core (vendored KLIP engine)."""
from __future__ import annotations

import os

from d4t.core.ingest import klarf_core

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_real.klarf")


# ---------------------------------------------------------------- synthetic files

KLARF12_WITH_IMAGES = """FileVersion 1 2;
FileTimestamp 03-14-26 08:00:00;
InspectionStationID "EBI" "EBI" "01";
SampleType WAFER;
ResultTimestamp 03-14-26 08:30:00;
LotID "LOT001";
SampleSize 1 300;
DeviceID "DEV01";
SetupID "SETUP01" 03-14-26 08:00:00;
StepID "STEP01";
SampleOrientationMarkType NOTCH;
OrientationMarkLocation DOWN;
DiePitch 1000.0 1200.0;
DieOrigin 0.0 0.0;
WaferID "W01";
Slot 1;
TiffFileName LOT001.tif;
TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
InspectionTest 1;
ClassLookup 2
 0 "Unknown"
 1 "Particle";
DefectRecordSpec 10 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER IMAGECOUNT IMAGELIST ;
DefectList
 1 100.500 200.500 1 2 0.5 0.5 1 2 1 0 2 0
 2 300.000 400.000 2 3 0.6 0.6 1 2 3 0 4 0;
SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;
SummaryList
 1 2 1.0000000000e-03 10 2;
EndOfFile;
"""

KLARF18_WITH_IMAGE_BLOCKS = """Record FileRecord  "1.8"
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


# ---------------------------------------------------------------- lossless round-trip

def test_roundtrip_fixture_byte_identical():
    with open(FIXTURE, "rb") as f:
        raw = f.read()
    doc = klarf_core.load(FIXTURE)
    assert doc.version == "1.8"
    assert len(doc.defects) == 6
    assert doc.to_text().encode("utf-8") == raw


def test_roundtrip_synthetic_12_identical():
    doc = klarf_core.load(KLARF12_WITH_IMAGES)
    assert doc.version == "1.2"
    assert doc.to_text() == KLARF12_WITH_IMAGES


# ---------------------------------------------------------------- defect_image_map

def test_defect_image_map_12_tiffspec_imagelist():
    doc = klarf_core.load(KLARF12_WITH_IMAGES)
    assert doc.tiff_file_name == "LOT001.tif"
    assert doc.tiff_spec == {"version": "6.1", "nfields": 2,
                             "fields": ["IMAGEVERSION", "IMAGEXYPOS"]}
    # layout declared by TiffSpec: entries start at the IMAGELIST column,
    # 2 tokens per image
    assert doc.image_layout() == (9, 2, "declared")
    assert doc.total_image_count() == 4

    m = doc.defect_image_map(n_pages=4)
    assert m["mode"] == "imagelist"
    assert m["base"] == 1                      # ids 1..4 -> 1-based pages
    assert m["pages"] == [[0, 1], [2, 3]]      # 0-based TIFF pages

    # without n_pages the base is inferred from the smallest id
    m2 = doc.defect_image_map()
    assert m2["pages"] == [[0, 1], [2, 3]]


# ---------------------------------------------------------------- batch_set

def test_batch_set_edits_only_targeted_cells():
    doc = klarf_core.load(KLARF12_WITH_IMAGES)
    before = [list(r) for r in doc.defects]

    n = doc.batch_set("DEFECTID", 2, "CLASSNUMBER", 7)
    assert n == 1

    text = doc.to_text()
    # everything before the DefectList block is byte-identical
    assert text.split("DefectList")[0] == KLARF12_WITH_IMAGES.split("DefectList")[0]
    # everything after it (SummaryList onwards) is byte-identical too
    assert text.split("SummarySpec")[1] == KLARF12_WITH_IMAGES.split("SummarySpec")[1]

    doc2 = klarf_core.load(text)
    ci = doc2.col_index("CLASSNUMBER")
    for row_before, row_after in zip(before, doc2.defects):
        for j, (a, b) in enumerate(zip(row_before, row_after)):
            if row_before[doc2.col_index("DEFECTID")] == "2" and j == ci:
                assert (a, b) == ("1", "7")    # only this cell changed
            else:
                assert a == b


# ---------------------------------------------------------------- defect_image_filename

def test_defect_image_filename_synthetic_18():
    doc = klarf_core.load(KLARF18_WITH_IMAGE_BLOCKS)
    assert doc.version == "1.8"
    assert len(doc.defects) == 3
    names = [doc.defect_image_filename(r) for r in doc.defects]
    assert names == ["d1.png", "d2.png", None]
    # additive method must not disturb the lossless round-trip
    assert doc.to_text() == KLARF18_WITH_IMAGE_BLOCKS


def test_defect_image_filename_fixture_images_blocks():
    doc = klarf_core.load(FIXTURE)
    names = [doc.defect_image_filename(r) for r in doc.defects]
    assert names == [f"1.000_0000{i}.jpg" for i in range(1, 7)]


def test_defect_image_filename_absent_on_12_token_rows():
    doc = klarf_core.load(KLARF12_WITH_IMAGES)
    # 1.2 IMAGELIST rows carry numeric image tokens, not Image {...} blocks
    assert all(doc.defect_image_filename(r) is None for r in doc.defects)


# ---------------------------------------------------------------- atomic save
def test_save_is_atomic_and_lossless(tmp_path):
    """鐵則 5：檔案寫入一律 atomic（``.tmp`` + ``os.replace``）。

    ``KlarfDoc.save`` 曾經是整個 ``core/`` 裡唯一的例外 —— 直接
    ``open(path, 'w')`` 寫進去（那是上游 KLIP 的寫法）。這個檔案上那條規矩
    特別重：KLARF 寫回不可逆，而寫到一半斷掉留下的是一份**截斷的 KLARF**，
    它蓋掉的是廠內唯一的一手資料。
    """
    src = tmp_path / "in.001"
    # ⚠ 用內建的 open 而不是 pathlib 的 write_text —— 後者的 newline 關鍵字
    # 是 **3.10+**，而公司機的 Python 版本不由我們決定（`AGENTS.md` §3）。
    # `tests/test_offline_tools.py` 有一條在守這件事，它當場抓到了第一版
    # （而且連我這段註解裡的字面寫法都抓 —— 那個守門是掃原始碼文字的，
    #  對這種事寧可過度警覺）。
    with open(str(src), "w", encoding="utf-8", newline="") as f:
        f.write(KLARF12_WITH_IMAGES)
    doc = klarf_core.load(str(src))

    out = tmp_path / "out.001"
    doc.save(str(out))

    # 什麼都沒改 → 逐位元組相同（span-splice 的承諾）
    assert out.read_bytes() == src.read_bytes()
    # 而且不留下 .tmp
    assert not (tmp_path / "out.001.tmp").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.001", "out.001"]


def test_save_leaves_the_old_file_intact_when_writing_fails(tmp_path,
                                                            monkeypatch):
    """atomic 要換來的正是這件事：**沒有中間態**。

    寫到一半炸掉的時候，目標路徑上要嘛是舊的完整檔案、要嘛是新的完整檔案。
    非 atomic 的版本在這裡會留下一份被截斷的 KLARF。
    """
    target = tmp_path / "keep.001"
    with open(str(target), "w", encoding="utf-8", newline="") as f:
        f.write(KLARF12_WITH_IMAGES)
    before = target.read_bytes()

    doc = klarf_core.load(str(target))
    monkeypatch.setattr(doc, "to_text",
                        lambda: (_ for _ in ()).throw(RuntimeError("disk full")))
    try:
        doc.save(str(target))
    except RuntimeError:
        pass

    assert target.read_bytes() == before, "原檔被寫壞了"
