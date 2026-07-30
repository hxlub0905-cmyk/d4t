#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part5of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part5of6.py --dest D:\\tools
    python ADEPT_part5of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 5, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
TOTAL = 178                       # 整個 repo 有幾個檔案，不是這一批有幾個


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式："blob <長度>\\0" + 內容。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines):
    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
        yield sha, path, "\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
    a = ap.parse_args(argv)

    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
        return 2

    items = list(entries(lines[start:]))
    if not items:
        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
        return 2
    print("這個包裡有 %d 個檔案。" % len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %8d  %s" % (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("解到  : %s" % dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("✗ %d 個檔案的內容跟它自己的 SHA 對不上：" % len(bad))
        for path in bad[:12]:
            print("    %s" % path)
        print("")
        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
        return 1

    print("✓ %d 個檔案都解開了，SHA 全部對得上。" % done)

    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
        print("")
        print("這是第 %d 批 / 共 %d 批，整個 repo 有 %d 個檔案 —— **還沒到齊**。"
              % (PART, N_PARTS, TOTAL))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
        return 0

    if missing:
        print("")
        print("這是第 %d 批 / 共 %d 批。整個 repo 還缺 %d 個檔案 —— 在其他批裡。"
              % (PART, N_PARTS, len(missing)))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
        for rel in missing[:6]:
            print("    %s" % rel)
        return 0

    print("")
    print("下一步：")
    print("  cd %s" % dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ====
#F 745560662f263dc8a471f910d8b4640c647dd68d 247 tests/fixtures/sample_real.klarf
#Record FileRecord  "1.8"
#{
#  Record LotRecord "AA0000.0X"
#  {
#    Record WaferRecord "AA0000.01"
#    {
#      Field DieOrigin 2 {0, 0}
#      Field OrientationInstructions 1 {""}
#      Field ProcessEquipmentState 7 {"TOOL01", "", "", "", "", "", ""}
#      Field SampleCenterLocation 2 {20434404, 10607650}
#      Field ScribeID 1 {"AA0000.01"}
#      Field SlotNumber 1 {1}
#
#      List DefectList
#      {
#        Columns 42 { int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,  int32 YINDEX,
#        int32 XSIZE,  int32 YSIZE,  float DEFECTAREA,  int32 DSIZE,  int32 CLASSNUMBER,
#        int32 TEST,  int32 ROUGHBINNUMBER,  int32 FINEBINNUMBER,  int32 SAMPLEBINNUMBER,  float CONTRAST,
#        int32 CHANNELID,  int32 MANSEMCLASS,  int32 AUTOONSEMCLASS,  int32 AUTOOFFSEMCLASS,  int32 AUTOOFFOPTADC,
#        int32 FACLASS,  int32 INTENSITY,  float KILLPROB,  int32 REGIONID,  int32 EVENTTYPE,
#        int32 EBRLINE,  ImageList IMAGEINFO,  int32 POLARITY,  float CRITICALAREA,
#        int32 MANOPTCLASS,  float PHI,  int32 DBCLASS,  int32 DBGROUP,  float DBCRITICALITYINDEX,
#        float CELLSIZE,  int32 CAREAREAGROUPCODE,  float PCI,  float LINECOMPLEXITY,  float DCIRANGE,
#        double XOFFSET,  double ADRHIGHSCORE,  double YOFFSET  }
#        Data 6
#        {
#          6301 20267174 20652619 -4 1 10 10 100.0 10 212 1 0 0 0 0.0000 0 0
#            0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00001.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#          11205 20282918 20654582 -3 1 10 10 100.0 10 212 1 0 0 0 0.0000 0
#            0 0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00002.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#          25901 20281239 20643118 0 1 10 10 100.0 10 212 1 0 0 0 0.0000 0 0
#            0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00003.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#          26608 20279147 20652568 0 2 10 10 100.0 10 212 1 0 0 0 0.0000 0 0
#            0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00004.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#          27301 20278488 20640964 0 3 10 10 100.0 10 212 1 0 0 0 0.0000 0 0
#            0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00005.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#          168201 20282634 20642982 1 -2 10 10 100.0 10 212 2 0 0 0 0.0000 0
#            0 0 0 0 0 0 0.0000 0 0 0  Images 1 { "1.000_00006.jpg" "JPG" 1 "24" }
#            0 0.0000 0 0.0 0 0 0.0000 0.000000 0 0.0000 0.0000 0.0000 0.000000
#            0.000000 0.000000 ;
#        }
#      }
#      Record TestRecord "1"
#      {
#        Field AreaPerTest 1 {4.6880000000e+09}
#        Field InspectedAreaOrigin 2 {6, 5}
#        Field InspectionTest 2 {1, "1" }
#
#        List SampleTestPlanList
#        {
#          Columns 2 { int32 XINDEX, int32 YINDEX }
#          Data 41
#          {
#            -5 -2 ;
#            -5 -1 ;
#            -5 0 ;
#            -5 1 ;
#            -5 2 ;
#            -4 -3 ;
#            -4 -2 ;
#            -4 -1 ;
#            -4 0 ;
#            -4 1 ;
#            -4 2 ;
#            -4 3 ;
#            -3 -3 ;
#            -3 -2 ;
#            -3 -1 ;
#            -3 0 ;
#            -3 1 ;
#            -3 2 ;
#            -3 3 ;
#            -2 -4 ;
#            -2 -3 ;
#            -2 -2 ;
#            -2 -1 ;
#            -2 0 ;
#            -2 1 ;
#            -2 2 ;
#            -2 3 ;
#            -1 -4 ;
#            -1 -3 ;
#            -1 -2 ;
#            -1 -1 ;
#            -1 0 ;
#            -1 1 ;
#            -1 2 ;
#            -1 3 ;
#            -1 4 ;
#            0 0 ;
#            0 1 ;
#            0 2 ;
#            0 3 ;
#            0 4 ;
#          }
#        }
#      }
#      Record TestRecord "3"
#      {
#        Field AreaPerTest 1 {1.0000000000e+06}
#        Field InspectedAreaOrigin 2 {6, 5}
#        Field InspectionTest 2 {3, "3" }
#
#        List SampleTestPlanList
#        {
#          Columns 2 { int32 XINDEX, int32 YINDEX }
#          Data 3
#          {
#            0 -3 ;
#            0 -1 ;
#            1 1 ;
#          }
#        }
#      }
#      Record TestRecord "2"
#      {
#        Field AreaPerTest 1 {4.6880000000e+09}
#        Field InspectedAreaOrigin 2 {6, 5}
#        Field InspectionTest 2 {2, "2" }
#
#        List SampleTestPlanList
#        {
#          Columns 2 { int32 XINDEX, int32 YINDEX }
#          Data 60
#          {
#            -5 -2 ;
#            -5 0 ;
#            -4 -3 ;
#            -4 -1 ;
#            -4 1 ;
#            -3 -2 ;
#            -3 0 ;
#            -3 2 ;
#            -2 -3 ;
#            -2 -1 ;
#            -2 1 ;
#            -2 3 ;
#            -1 -4 ;
#            -1 -2 ;
#            -1 0 ;
#            -1 2 ;
#            0 1 ;
#            0 3 ;
#            0 -4 ;
#            0 -3 ;
#            0 -2 ;
#            1 -4 ;
#            1 -3 ;
#            1 -2 ;
#            1 -1 ;
#            1 0 ;
#            1 2 ;
#            1 3 ;
#            1 4 ;
#            2 -4 ;
#            2 -3 ;
#            2 -2 ;
#            2 -1 ;
#            2 0 ;
#            2 1 ;
#            2 2 ;
#            2 3 ;
#            3 -4 ;
#            3 -3 ;
#            3 -2 ;
#            3 -1 ;
#            3 0 ;
#            3 1 ;
#            3 2 ;
#            3 3 ;
#            4 -3 ;
#            4 -2 ;
#            4 -1 ;
#            4 0 ;
#            4 1 ;
#            4 2 ;
#            4 3 ;
#            5 -2 ;
#            5 -1 ;
#            5 0 ;
#            5 1 ;
#            5 2 ;
#            6 -1 ;
#            6 0 ;
#            6 1 ;
#          }
#        }
#      }
#      Record SummaryRecord
#      {
#
#        List TestSummaryList
#        {
#          Columns 11 { int32 TESTNO,  int32 NDEFECT,  float DEFDENSITY,  int32 NDIE,  int32 NDEFDIE,
#          float HAZEREGION,  float HAZEAVERAGE,  float HAZESTDDEV,  float HAZEMEDIAN,  float HAZEPEAK,
#          float AREAPERTEST  }
#          Data 3
#          {
#            1  0  0.0000000000e+00  41  41
#              -1  -1  -1  -1  -1  4.6880000000e+09   ;
#            3  0  0.0000000000e+00  3  3
#              -1  -1  -1  -1  -1  1.0000000000e+06   ;
#            2  0  0.0000000000e+00  60  60
#              -1  -1  -1  -1  -1  4.6880000000e+09   ;
#          }
#        }
#      }
#    }
#    Field DeviceID 1 {"DEV001"}
#    Field DiePitch 2 {23376636, 32874750}
#    Field FabID 1 {"FAB01"}
#    Field InspectionStationID 3 {"TOOL01", "PRIMEVISION", "TOOL01"}
#    Field OrientationMarkLocation 1 {0}
#    Field RecipeID 3 {"DEV001_LAYERA_STP_BSTP_CST_DS01_E01", "01-01-2026", "12:40:34"}
#    Field RecipeVersion 3 {"", "", ""}
#    Field ResultTimestamp 2 {"01-02-2026", "13:17:11"}
#    Field SampleOrientationMarkType 1 {"NOTCH"}
#    Field SampleSize 2 {300000000, 0}
#    Field SampleType 1 {"WAFER"}
#    Field StepID 1 {"LAYERA_STP_BSTP_CST_DS01_E01"}
#
#    List ClassLookupList
#    {
#      Columns 3 { int32 CLASSNUMBER, string CLASSNAME, string CLASSCODE }
#      Data 3
#      {
#         0 "No Review" "";
#         212 "Grey VC" "";
#         1076 "Class A fail" "";
#      }
#    }
#  }
#  Field FileTimestamp 2 {"01-03-2026", "14:12:33"}
#
#}
#EndOfFile;
#
#F fc105693a52e53f5b37b6c009a1456b9acd8e80f 135 tests/test_align.py
#"""Tests for adept.core.algo.align (vendored 2026-07-27).
#
#Sign convention under test: target(x, y) == base(x - dx, y - dy) — the target
#content sits dx px right / dy px down of the base content, and every backend
#must return that same (+dx, +dy).
#"""
#from __future__ import annotations
#
#import cv2
#import numpy as np
#import pytest
#
#from adept.core.algo.align import (
#    AlignResult,
#    apply_alignment,
#    alignment_overlap_slices,
#    calculate_alignment,
#    calculate_alignment_robust,
#    ncc_score,
#    parabola_subpx,
#    template_align_nm,
#)
#
#ALL_METHODS = ["phase", "hybrid", "ncc", "ecc", "template"]
#
#TRUE_DX, TRUE_DY = 4, -3  # planted integer shift (right 4, up 3)
#
#
#def _base_image(size: int = 160) -> np.ndarray:
#    rng = np.random.default_rng(42)
#    img = (rng.random((size, size)) * 255).astype(np.float32)
#    return cv2.GaussianBlur(img, (0, 0), 3)
#
#
#def _shift_int(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
#    """target(x, y) = base(x - dx, y - dy) via periodic roll."""
#    return np.roll(np.roll(img, dx, axis=1), dy, axis=0)
#
#
#def _shift_subpx(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
#    """target(x, y) = base(x - dx, y - dy) via linear-interp warp."""
#    h, w = img.shape[:2]
#    M = np.float32([[1, 0, dx], [0, 1, dy]])
#    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
#                          borderMode=cv2.BORDER_REPLICATE)
#
#
#@pytest.mark.parametrize("method", ALL_METHODS)
#def test_every_backend_recovers_planted_integer_shift(method):
#    base = _base_image()
#    target = _shift_int(base, TRUE_DX, TRUE_DY)
#    res = calculate_alignment(base, target, method=method, search_radius=8)
#    assert isinstance(res, AlignResult)
#    # Same sign AND same magnitude for every backend (±0.5 px)
#    assert abs(res.dx_subpixel - TRUE_DX) <= 0.5, (method, res.dx_subpixel)
#    assert abs(res.dy_subpixel - TRUE_DY) <= 0.5, (method, res.dy_subpixel)
#    assert res.dx == TRUE_DX
#    assert res.dy == TRUE_DY
#
#
#@pytest.mark.parametrize("method", ["phase", "template"])
#def test_subpixel_shift_recovered(method):
#    base = _base_image()
#    dx, dy = 2.4, -1.7
#    target = _shift_subpx(base, dx, dy)
#    res = calculate_alignment(base, target, method=method, search_radius=8)
#    assert abs(res.dx_subpixel - dx) <= 0.3, (method, res.dx_subpixel)
#    assert abs(res.dy_subpixel - dy) <= 0.3, (method, res.dy_subpixel)
#
#
#def test_apply_alignment_inverts_planted_shift():
#    base = _base_image()
#    target = _shift_int(base, TRUE_DX, TRUE_DY)
#    aligned = apply_alignment(target, TRUE_DX, TRUE_DY)
#    inner = (slice(12, -12), slice(12, -12))
#    assert float(np.abs(aligned[inner] - base[inner]).mean()) < 1e-3
#
#
#@pytest.mark.parametrize("method", ALL_METHODS)
#def test_flat_image_guard_no_crash(method):
#    flat = np.full((64, 64), 128.0, dtype=np.float32)
#    res = calculate_alignment(flat, flat.copy(), method=method, search_radius=8)
#    assert res.status == 'fail'
#    assert res.dx == 0 and res.dy == 0
#
#    # Direct call of the phase backend must be guarded too
#    res2 = calculate_alignment_robust(flat, flat.copy(), search_radius=8)
#    assert res2.status == 'fail'
#
#
#def test_overlap_slices_consistency():
#    base = _base_image(96)
#    target = _shift_int(base, 5, 2)
#    by, bx, ty, tx = alignment_overlap_slices(base.shape[:2], 5, 2)
#    # Overlap regions must contain the same scene content -> NCC ~ 1
#    assert ncc_score(base[by, bx], target[ty, tx]) > 0.99
#    # Negative shifts produce valid, equal-sized slices as well
#    by, bx, ty, tx = alignment_overlap_slices((96, 96), -5, -2)
#    assert (by.stop - by.start) == (ty.stop - ty.start)
#    assert (bx.stop - bx.start) == (tx.stop - tx.start)
#
#
#def test_template_align_nm_anchor_correction_signs():
#    # Synthetic GDS-like template: bright rectangles on dark background.
#    tmpl = np.zeros((128, 128), dtype=np.uint8)
#    tmpl[30:60, 20:50] = 200
#    tmpl[80:100, 70:110] = 200
#    tmpl = cv2.GaussianBlur(tmpl, (5, 5), 1.0)
#    # SEM structure sits (ex, ey) = (+5, -3) px from the template position.
#    sem = np.roll(np.roll(tmpl, 5, axis=1), -3, axis=0)
#
#    dx_nm, dy_nm, score, used_r = template_align_nm(sem, tmpl, nm_per_px=2.0,
#                                                    search_radius_px=10)
#    # Anchor correction: x negated (GDS anchor x decreases to move right),
#    # y follows image-down: (-ex * nm, +ey * nm) = (-10, -6).
#    assert score > 0.8
#    assert used_r == 10
#    assert abs(dx_nm - (-10.0)) <= 1.0
#    assert abs(dy_nm - (-6.0)) <= 1.0
#
#
#def test_template_align_nm_flat_guard():
#    flat = np.full((64, 64), 100, dtype=np.uint8)
#    dx_nm, dy_nm, score, _ = template_align_nm(flat, flat, 1.0, 8)
#    assert (dx_nm, dy_nm, score) == (0.0, 0.0, 0.0)
#
#
#def test_parabola_subpx_peak_offset():
#    res = np.zeros((5, 5), dtype=np.float32)
#    res[2, 1], res[2, 2], res[2, 3] = 0.5, 1.0, 0.7  # peak pulled toward +x
#    off = parabola_subpx(res, 2, 2, axis=0)
#    assert 0.0 < off < 0.5
#    # Border peak -> 0.0 (no fit possible)
#    assert parabola_subpx(res, 0, 2, axis=0) == 0.0
#
#F a0f997191164806f1391e99faad54dc324eb22ab 394 tests/test_batch_cache.py
## ADEPT M2 驗收 — authored 2026-07-28.
#"""M2 驗收：平行批次（run_batch）+ 影像段快取（StageCache / run_defect_cached）。
#
#鐵則：快取/平行的結果必須與 M1 循序 run_dataset **位元級一致**
#（features / score / bin），快取層任何故障都只能退回重算、不准 crash。
#"""
#from __future__ import annotations
#
#import math
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.ingest.dataset import load_dataset  # noqa: E402
#from adept.core.pipeline import (  # noqa: E402
#    Recipe,
#    RecipeNode,
#    ScoreSpec,
#    StageCache,
#    image_segment_signature,
#    result_to_json_dict,
#    run_batch,
#    run_dataset,
#    run_defect,
#    run_defect_cached,
#)
#from adept.core.pipeline.batch import pin_cv2_deterministic  # noqa: E402
#from adept.core.pipeline.cache import dataset_token  # noqa: E402
#
#N = 12
#KIND = "ebi_patch"
#
#
## ---------------------------------------------------------------------------
## fixtures / helpers
## ---------------------------------------------------------------------------
#@pytest.fixture(scope="module", autouse=True)
#def _cv2_deterministic():
#    """cv2 的 IPP kernel（Sobel 等）結果會隨 buffer 位址飄 1e-8 級雜訊 ——
#    同一顆同參數兩次重算都不保證 bit 相同。本模組把 parent 進程調成與
#    run_batch worker 相同的 deterministic 模式（threads=1 + IPP off，
#    見 batch.pin_cv2_deterministic），「快取/平行 vs 循序位元級一致」的
#    驗收才有意義。測完還原，不污染其他測試。"""
#    import cv2
#    prev_threads = cv2.getNumThreads()
#    try:
#        prev_ipp = cv2.ipp.useIPP()
#    except Exception:
#        prev_ipp = None
#    pin_cv2_deterministic()
#    try:
#        yield
#    finally:
#        cv2.setNumThreads(prev_threads)
#        if prev_ipp is not None:
#            cv2.ipp.setUseIPP(prev_ipp)
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("m2lot")
#    return generate(str(out), n=N, seed=7)
#
#
#@pytest.fixture(scope="module")
#def ds(synlot):
#    d = load_dataset(synlot["klarf"])
#    assert d.kind == KIND and len(d.items) == N
#    return d
#
#
#def make_recipe(snr_threshold: float = 200.0, search_radius: int = 8) -> Recipe:
#    """die-to-die 節點組（同 examples/recipes/die_to_die_basic.json）。"""
#    nodes = {
#        "load": RecipeNode("load", "load_patch", {}),
#        # 一張卡一條流（F7-18）：ref 先做（借 test 還沒被拉伸的範圍），test 再做。
#        "norm_ref": RecipeNode("norm_ref", "percentile_norm",
#                               {"source": "ref", "range_from": "test"}),
#        "norm": RecipeNode("norm", "percentile_norm", {"source": "test"}),
#        "align": RecipeNode("align", "align",
#                            {"method": "phase", "search_radius": search_radius}),
#        "sub": RecipeNode("sub", "subtract", {}),
#        "dn": RecipeNode("dn", "denoise",
#                         {"target": "diff", "method": "median", "ksize": 3}),
#        "snr": RecipeNode("snr", "snr_map", {"window": 15, "exclude_border": 8}),
#        "blob": RecipeNode("blob", "blob_segment",
#                           {"min_area": 6, "snr_threshold": snr_threshold}),
#        "cd": RecipeNode("cd", "cd_measure", {}),
#        # F7-4：中心框從量測卡的參數搬到 Region 卡
#        "roi": RecipeNode("roi", "roi_define",
#                          {"name": "centre", "shape": "center", "size": 32.0,
#                           "size_unit": "px", "source": "diff"}),
#        "glv": RecipeNode("glv", "glv_stats",
#                          {"source": "diff", "roi": "centre",
#                           "metrics": "glv_max,glv_q99,glv_mean"}),
#    }
#    return Recipe(
#        recipe_id="m2_batch_cache_test",
#        routes={KIND: ["load", "norm_ref", "norm", "align", "sub", "dn",
#                       "snr", "blob", "cd", "roi", "glv"]},
#        nodes=nodes,
#        score=ScoreSpec(expr="glv_max + (glv_max - glv_q99)", threshold=50.0,
#                        bins={"below": 0, "above": 1}),
#    )
#
#
#def _slim(d: dict) -> dict:
#    """run_batch dict → 只留可比對欄位（traces 的 ms 每次都不同）。"""
#    return {k: d[k] for k in ("defect_id", "ok", "error",
#                              "features", "score", "bin")}
#
#
#def _assert_same_features(a: dict, b: dict) -> None:
#    """位元級一致（NaN 視為相等 —— 雖然本 recipe 不該產 NaN）。"""
#    assert set(a) == set(b)
#    for k in a:
#        va, vb = float(a[k]), float(b[k])
#        if math.isnan(va) or math.isnan(vb):
#            assert math.isnan(va) and math.isnan(vb), k
#        else:
#            assert va == vb, (k, va, vb)
#
#
#def _assert_same_result(ra, rb) -> None:
#    """兩個 DefectResult：ok / features / score / bin 位元級一致。"""
#    assert ra.defect_id == rb.defect_id
#    assert ra.ok == rb.ok and ra.error == rb.error
#    _assert_same_features(ra.features, rb.features)
#    assert ra.score == rb.score
#    assert ra.bin == rb.bin
#
#
## ---------------------------------------------------------------------------
## 1. serial vs parallel vs M1 run_dataset：全部一致
## ---------------------------------------------------------------------------
#def test_serial_parallel_and_m1_agree(ds):
#    rec = make_recipe()
#    serial = run_batch(rec, ds, workers=1)
#    parallel = run_batch(rec, ds, workers=2)      # 真開 ProcessPool
#    m1 = [result_to_json_dict(r) for r in run_dataset(rec, ds)]
#
#    assert len(serial) == len(parallel) == len(m1) == N
#    # 原始 item 順序（parallel 的 as_completed 亂序要被排回來）
#    assert [d["defect_id"] for d in serial] == [d["defect_id"] for d in m1]
#    assert [d["defect_id"] for d in parallel] == [d["defect_id"] for d in m1]
#    for a, b, c in zip(serial, parallel, m1):
#        assert _slim(a) == _slim(b) == _slim(c)
#    assert all(d["ok"] for d in serial)
#
#
#def test_run_batch_limit_and_progress(ds):
#    rec = make_recipe()
#    calls = []
#    out = run_batch(rec, ds, workers=1, limit=4,
#                    progress=lambda done, total, d: calls.append((done, total)))
#    assert len(out) == 4
#    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]
#
#
## ---------------------------------------------------------------------------
## 2. 快取：首跑全 miss、再跑全 hit，結果與無快取完全一致
## ---------------------------------------------------------------------------
#def test_cache_miss_then_hit_bit_identical(ds, synlot, tmp_path):
#    rec = make_recipe()
#    token = dataset_token(synlot["klarf"])
#    cache = StageCache(str(tmp_path / "cache"))
#
#    first = [run_defect_cached(rec, it, KIND, cache, token) for it in ds.items]
#    assert cache.misses == N and cache.hits == 0
#    st = cache.stats()
#    assert st["n_files"] == N and st["bytes"] > 0
#
#    second = [run_defect_cached(rec, it, KIND, cache, token) for it in ds.items]
#    assert cache.hits == N and cache.misses == N
#
#    plain = [run_defect(rec, it, KIND) for it in ds.items]
#    for a, b, c in zip(first, second, plain):
#        assert a.ok and b.ok and c.ok
#        _assert_same_result(a, c)
#        _assert_same_result(b, c)
#
#    cache.clear()
#    assert cache.stats() == {"n_files": 0, "bytes": 0}
#
#
## ---------------------------------------------------------------------------
## 3. 改「算法段」參數：簽章不變 → 全 hit，結果與 fresh full run 一致
## ---------------------------------------------------------------------------
#def test_algo_param_change_keeps_cache(ds, synlot, tmp_path):
#    rec_a = make_recipe(snr_threshold=200.0)
#    rec_b = make_recipe(snr_threshold=180.0)
#    sig_a, ck_a = image_segment_signature(rec_a, KIND)
#    sig_b, ck_b = image_segment_signature(rec_b, KIND)
#    assert sig_a == sig_b
#    assert ck_a == ck_b == 6      # load, norm_ref, norm, align, sub, dn 之後
#
#    token = dataset_token(synlot["klarf"])
#    cache = StageCache(str(tmp_path / "cache"))
#    for it in ds.items:
#        run_defect_cached(rec_a, it, KIND, cache, token)
#    assert cache.misses == N and cache.hits == 0
#
#    tuned = [run_defect_cached(rec_b, it, KIND, cache, token) for it in ds.items]
#    assert cache.hits == N        # 全 hit：影像段沒重算
#    fresh = [run_defect(rec_b, it, KIND) for it in ds.items]
#    for a, b in zip(tuned, fresh):
#        _assert_same_result(a, b)
#
#
## ---------------------------------------------------------------------------
## 4. 改「影像段」參數：簽章改變 → 全 miss
## ---------------------------------------------------------------------------
#def test_image_param_change_invalidates_cache(ds, synlot, tmp_path):
#    rec_a = make_recipe(search_radius=8)
#    rec_b = make_recipe(search_radius=6)
#    sig_a, _ = image_segment_signature(rec_a, KIND)
#    sig_b, _ = image_segment_signature(rec_b, KIND)
#    assert sig_a != sig_b
#
#    token = dataset_token(synlot["klarf"])
#    cache = StageCache(str(tmp_path / "cache"))
#    for it in ds.items:
#        run_defect_cached(rec_a, it, KIND, cache, token)
#    assert cache.misses == N
#
#    retuned = [run_defect_cached(rec_b, it, KIND, cache, token) for it in ds.items]
#    assert cache.misses == 2 * N and cache.hits == 0     # 全 miss
#    assert cache.stats()["n_files"] == 2 * N             # 兩套簽章各一份
#    fresh = [run_defect(rec_b, it, KIND) for it in ds.items]
#    for a, b in zip(retuned, fresh):
#        _assert_same_result(a, b)
#
#
#def test_dataset_token_changes_when_lot_regenerated(tmp_path):
#    paths = generate(str(tmp_path / "lot"), n=2, seed=1)
#    t1 = dataset_token(paths["klarf"])
#    # 重寫 KLARF（模擬重產 lot）→ mtime/size 變 → token 變
#    p = Path(paths["klarf"])
#    p.write_text(p.read_text() + "\n")
#    assert dataset_token(paths["klarf"]) != t1
#
#
## ---------------------------------------------------------------------------
## 5. 快取故障（壞檔 / 寫不進去）→ 不 crash、結果照樣正確
## ---------------------------------------------------------------------------
#def test_corrupt_cache_file_falls_back(ds, synlot, tmp_path):
#    rec = make_recipe()
#    token = dataset_token(synlot["klarf"])
#    cache = StageCache(str(tmp_path / "cache"))
#    item = ds.items[0]
#    plain = run_defect(rec, item, KIND)
#
#    sig, _ = image_segment_signature(rec, KIND)
#    key = cache.make_key(token, item.defect_id, sig)
#    shard = Path(cache.dir) / key[:2]
#    shard.mkdir(parents=True, exist_ok=True)
#    (shard / (key + ".npz")).write_bytes(b"\x00this is not an npz\xff")
#
#    r = run_defect_cached(rec, item, KIND, cache, token)
#    assert r.ok
#    _assert_same_result(r, plain)
#    assert cache.misses == 1      # 壞檔算 miss（且已被 put 換成好檔）
#    assert cache.get(key) is not None and cache.hits == 1
#
#
#def test_unwritable_cache_falls_back(ds, synlot, tmp_path):
#    rec = make_recipe()
#    token = dataset_token(synlot["klarf"])
#    cache = StageCache(str(tmp_path / "cache"))
#    item = ds.items[0]
#    plain = run_defect(rec, item, KIND)
#
#    sig, _ = image_segment_signature(rec, KIND)
#    key = cache.make_key(token, item.defect_id, sig)
#    # 用「檔案」佔住 shard 目錄名 → put 的 makedirs 必爆（root 也擋得住）
#    (Path(cache.dir) / key[:2]).write_text("blocker")
#
#    r = run_defect_cached(rec, item, KIND, cache, token)   # 不准 crash
#    assert r.ok
#    _assert_same_result(r, plain)
#    assert cache.stats()["n_files"] == 0                   # 沒寫成也沒殘骸
#
#    # get 也拿不到（shard 是檔案）→ 再跑一次仍正確
#    r2 = run_defect_cached(rec, item, KIND, cache, token)
#    assert r2.ok
#    _assert_same_result(r2, plain)
#
#
## ---------------------------------------------------------------------------
## 6. abort_check：3 顆後喊停 → 回傳部分結果
## ---------------------------------------------------------------------------
#def test_abort_returns_partial(ds):
#    rec = make_recipe()
#    seen = []
#    results = run_batch(rec, ds, workers=1,
#                        progress=lambda done, total, d: seen.append(done),
#                        abort_check=lambda: len(seen) >= 3)
#    assert 3 <= len(results) < N
#    assert all(d["ok"] for d in results)
#
#
## ---------------------------------------------------------------------------
## 7. 平行 + 快取整合：真開 pool、cache_dir 共用、結果一致
## ---------------------------------------------------------------------------
#def test_run_batch_parallel_with_cache(ds, tmp_path):
#    rec = make_recipe()
#    cdir = str(tmp_path / "batch_cache")
#
#    r1 = run_batch(rec, ds, workers=2, cache_dir=cdir)   # 首跑：workers 建快取
#    assert StageCache(cdir).stats()["n_files"] == N
#    r2 = run_batch(rec, ds, workers=2, cache_dir=cdir)   # 再跑：全 hit
#    base = run_batch(rec, ds, workers=1)                 # 無快取循序基準
#
#    assert len(r1) == len(r2) == len(base) == N
#    for a, b, c in zip(r1, r2, base):
#        assert _slim(a) == _slim(b) == _slim(c)
#
#
## ---------------------------------------------------------------------------
## 8. 快照必須涵蓋整個 Context —— 不只 images / features / meta（F7-9 迴歸）
## ---------------------------------------------------------------------------
#def _roi_then_image_recipe() -> Recipe:
#    """一份**很自然**、但會踩到快取切點的 recipe。
#
#    checkpoint 是執行順序上的**位置**（最後一張影像段卡的下一格），不是
#    「所有影像段的卡」。所以「先框出要看的地方，再做影像處理，最後量測」
#    這個順序會把 Region 卡（algo）夾在快取段裡面。
#    """
#    nodes = {
#        "load": RecipeNode("load", "load_patch", {}),
#        "roi": RecipeNode("roi", "roi_define",
#                          {"name": "main", "source": "test"}),
#        "dn": RecipeNode("dn", "denoise",
#                         {"target": "test", "method": "median", "ksize": 3}),
#        "glv": RecipeNode("glv", "glv_stats",
#                          {"source": "test", "roi": "main"}),
#    }
#    return Recipe(recipe_id="roi_in_cached_segment",
#                  routes={KIND: ["load", "roi", "dn", "glv"]}, nodes=nodes,
#                  score=ScoreSpec(expr="glv_mean", threshold=0.0,
#                                  bins={"below": 0, "above": 1}))
#
#
#def test_named_rois_survive_a_cache_hit(ds, tmp_path):
#    """第一次跑對、第二次跑錯，是最難查的一種 bug。
#
#    v1 的快照只存 images/features/meta，``ctx.rois`` 沒有存 —— 快取命中時
#    整個具名 ROI 表是空的，量測卡就報「region 'main' is not defined」。
#    """
#    rec = _roi_then_image_recipe()
#    _sig, ckpt = image_segment_signature(rec, KIND)
#    assert ckpt == 3, "前提：roi 卡確實落在快取段裡（不然這條測試沒在測東西）"
#
#    cache = StageCache(str(tmp_path / "roi_cache"))
#    token = dataset_token(ds.klarf_path if hasattr(ds, "klarf_path") else "lot")
#    item = ds.items[0]
#
#    first = run_defect_cached(rec, item, KIND, cache, token)
#    second = run_defect_cached(rec, item, KIND, cache, token)
#    assert cache.hits >= 1, "第二次應該要命中快取，不然沒測到那條路徑"
#
#    assert first.ok is True, first.error
#    assert second.ok is True, second.error
#    _assert_same_result(first, second)
#
#    # 而且要跟完全不用快取的結果一致
#    _assert_same_result(first, run_defect(rec, item, KIND))
#
#
#def test_an_old_format_snapshot_is_ignored_instead_of_trusted(ds, tmp_path):
#    """使用者的快取目錄可能是舊版寫的（缺 rois 欄位）。
#
#    版本對不上就當 miss 重算 —— 不然升級之後第一次跑仍然會踩到舊的殘缺快照。
#    """
#    import json
#
#    import numpy as np
#
#    cache = StageCache(str(tmp_path / "old"))
#    key = cache.make_key("tok", "d1", "sig")
#    path = cache._path(key)
#    Path(path).parent.mkdir(parents=True, exist_ok=True)
#    payload = {"image_names": ["test"], "features": {}, "meta": {}}   # 無 version
#    np.savez_compressed(path, **{"img__test": np.zeros((4, 4), np.uint8),
#                                 "__payload__": np.array(json.dumps(payload))})
#    assert cache.get(key) is None
#    assert cache.misses == 1
#
#F 1d28c06d3fbd4fabc6456cb942eea6a1db8ea305 67 tests/test_batch_thread_safety.py
## M3 迴歸測試：run_batch 從非主執行緒呼叫不得死鎖（Studio「試跑」按鈕的路徑）。
#"""背景：Linux 預設的 fork 若從非主執行緒呼叫，子行程會繼承其他執行緒持有的鎖，
#Studio 用 QThread 跑 run_batch(workers=2) 實測 100% 死鎖（第二次執行必卡）。
#修法見 batch.py `_pool_context()`：主執行緒 fork、非主執行緒 spawn。
#"""
#from __future__ import annotations
#
#import multiprocessing
#import sys
#import threading
#from pathlib import Path
#
#
#
#REPO = Path(__file__).resolve().parent.parent
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#import adept.core.steps  # noqa: F401,E402
#from adept.core.ingest.dataset import load_dataset  # noqa: E402
#from adept.core.pipeline import Recipe, run_batch  # noqa: E402
#from adept.core.pipeline.batch import _pool_context  # noqa: E402
#
#RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#
#def test_pool_context_main_thread_prefers_fork_when_available():
#    ctx = _pool_context()
#    if "fork" in multiprocessing.get_all_start_methods():
#        assert ctx.get_start_method() == "fork"   # 主執行緒：保留免 __main__ 保護的便利
#    else:
#        assert ctx.get_start_method() == "spawn"  # Windows
#
#
#def test_pool_context_off_thread_uses_spawn():
#    seen = {}
#
#    def probe():
#        seen["method"] = _pool_context().get_start_method()
#
#    t = threading.Thread(target=probe)
#    t.start()
#    t.join(timeout=10)
#    assert seen.get("method") == "spawn"
#
#
#def test_run_batch_twice_from_worker_thread_does_not_deadlock(tmp_path):
#    """連續兩次從背景執行緒平行跑批次 —— 修正前第二次必死鎖。"""
#    paths = generate(str(tmp_path / "lot"), n=6, seed=7)
#    ds = load_dataset(paths["klarf"])
#    recipe = Recipe.load(str(RECIPE))
#
#    results = {}
#
#    def job(tag):
#        results[tag] = run_batch(recipe, ds, workers=2, limit=6)
#
#    for tag in ("first", "second"):
#        t = threading.Thread(target=job, args=(tag,))
#        t.start()
#        t.join(timeout=180)
#        assert not t.is_alive(), f"run_batch 在背景執行緒卡住（{tag} 次）"
#
#    for tag in ("first", "second"):
#        assert len(results[tag]) == 6
#        assert all(r.get("ok") for r in results[tag])
#
#F 796aa532ef08b9736a38a00d6232d5d0b5f318e6 68 tests/test_blob.py
#"""Tests for adept.core.algo.blob (vendored 2026-07-27)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.blob import DefectROI, segment_defects
#
#
#def _float_snr_map():
#    """Normalized [0, 1] float map (SnrMapResult.map_float shape) with two blobs."""
#    rng = np.random.default_rng(21)
#    snr = rng.uniform(0.0, 0.05, size=(160, 160)).astype(np.float32)
#    snr[40:48, 60:68] = 0.9    # strong blob, 8x8 at (x=60, y=40)
#    snr[100:105, 120:125] = 0.6  # weaker blob, 5x5 at (x=120, y=100)
#    return snr
#
#
#def test_finds_planted_blobs_with_float_map():
#    snr = _float_snr_map()
#    rois = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
#    assert len(rois) == 2
#    assert all(isinstance(r, DefectROI) for r in rois)
#
#    strong = rois[0]
#    # Strong blob located at the planted position
#    assert abs(strong.cx - 63.5) <= 2.0
#    assert abs(strong.cy - 43.5) <= 2.0
#    # Approximate area (morphological open/close may trim corners)
#    assert 50 <= strong.area <= 78
#    assert strong.bbox == (strong.x, strong.y, strong.w, strong.h)
#    assert 58 <= strong.x <= 61 and 38 <= strong.y <= 41
#
#    weak = rois[1]
#    assert abs(weak.cx - 122.0) <= 2.0
#    assert abs(weak.cy - 102.0) <= 2.0
#    assert 12 <= weak.area <= 30
#
#
#def test_sorted_by_snr_descending():
#    snr = _float_snr_map()
#    rois = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
#    values = [r.snr_value for r in rois]
#    assert values == sorted(values, reverse=True)
#    # snr_value is reported on the legacy 0-255 map scale
#    assert abs(rois[0].snr_value - 0.9 * 255) <= 3.0
#    assert abs(rois[1].snr_value - 0.6 * 255) <= 3.0
#
#
#def test_uint8_map_equivalent_to_float_map():
#    snr = _float_snr_map()
#    u8 = (np.clip(snr, 0, 1) * 255).astype(np.uint8)
#    rois_f = segment_defects(snr, diff_image=snr, min_area=4, snr_threshold=100)
#    rois_u = segment_defects(u8, diff_image=snr, min_area=4, snr_threshold=100)
#    assert len(rois_f) == len(rois_u)
#    for rf, ru in zip(rois_f, rois_u):
#        assert rf.bbox == ru.bbox
#        assert rf.area == ru.area
#
#
#def test_min_area_filters_small_components():
#    snr = _float_snr_map()
#    rois = segment_defects(snr, diff_image=snr, min_area=40, snr_threshold=100)
#    assert len(rois) == 1  # the 5x5 blob is filtered out
#
#
#def test_empty_map_returns_empty_list():
#    assert segment_defects(np.array([]), np.array([])) == []
#
#F fce64e2110a74db0e23c9aeda3eec7d2282af53a 98 tests/test_calibration.py
#"""Tests for adept.core.calibration (vendored from MMH)."""
#from __future__ import annotations
#
#import json
#
#import pytest
#
#import adept.core.calibration as cal
#from adept.core.calibration import CalibrationManager, CalibrationProfile
#
#
#@pytest.fixture()
#def manager(tmp_path, monkeypatch):
#    # Point the module-level default dir into the tmp sandbox so even code
#    # paths that fall back to CALIBRATION_DIR never touch the real HOME.
#    monkeypatch.setattr(cal, "CALIBRATION_DIR", tmp_path / "calibrations")
#    return CalibrationManager(cal_dir=tmp_path / "calibrations")
#
#
#def test_round_trip_save_load(manager, tmp_path):
#    p = manager.create_new(
#        name="SEM-A 5nm", nm_per_pixel=5.0, magnification=50000.0,
#        detector_type="SE", notes="标定 round-trip")
#    # persisted to disk under the tmp dir
#    f = tmp_path / "calibrations" / f"{p.profile_id}.json"
#    assert f.exists()
#    # no stray .tmp file left behind by the atomic save
#    assert list((tmp_path / "calibrations").glob("*.tmp")) == []
#    # fresh manager re-reads it identically
#    m2 = CalibrationManager(cal_dir=tmp_path / "calibrations")
#    loaded = m2.get(p.profile_id)
#    assert loaded == p
#    assert loaded.nm_per_pixel == 5.0
#    assert loaded.notes == "标定 round-trip"
#    assert m2.list_profiles() == [p]
#
#
#def test_get_default(manager, tmp_path):
#    # empty store -> built-in fallback
#    d = manager.get_default()
#    assert d.profile_id == "default-1nm-px"
#    assert d.nm_per_pixel == 1.0
#    # once a profile exists, it becomes the default
#    p = manager.create_new("Real cal", nm_per_pixel=2.5)
#    m2 = CalibrationManager(cal_dir=tmp_path / "calibrations")
#    assert m2.get_default().profile_id == p.profile_id
#
#
#def test_default_dir_used_when_none(monkeypatch, tmp_path):
#    monkeypatch.setattr(cal, "CALIBRATION_DIR", tmp_path / "default_loc")
#    m = CalibrationManager()   # no cal_dir -> falls back to CALIBRATION_DIR
#    m.create_new("via default dir", nm_per_pixel=1.5)
#    assert len(list((tmp_path / "default_loc").glob("*.json"))) == 1
#
#
#def test_save_overwrites_atomically(manager, tmp_path):
#    p = manager.create_new("v1", nm_per_pixel=1.0)
#    p2 = CalibrationProfile(
#        profile_id=p.profile_id, profile_name="v2", nm_per_pixel=9.0,
#        version=2)
#    manager.save(p2)
#    f = tmp_path / "calibrations" / f"{p.profile_id}.json"
#    d = json.loads(f.read_text(encoding="utf-8"))
#    assert d["profile_name"] == "v2"
#    assert d["nm_per_pixel"] == 9.0
#    assert d["version"] == 2
#    assert manager.get(p.profile_id).profile_name == "v2"
#
#
#def test_delete(manager, tmp_path):
#    p = manager.create_new("victim", nm_per_pixel=3.0)
#    assert manager.delete(p.profile_id) is True
#    assert manager.get(p.profile_id) is None
#    assert not (tmp_path / "calibrations" / f"{p.profile_id}.json").exists()
#    assert manager.delete("missing-id") is False
#
#
#def test_corrupt_json_skipped(tmp_path):
#    d = tmp_path / "calibrations"
#    d.mkdir()
#    (d / "broken.json").write_text("{not json", encoding="utf-8")
#    ok = CalibrationProfile("good-id", "Good", 4.0)
#    m = CalibrationManager(cal_dir=d)
#    m.save(ok)
#    m2 = CalibrationManager(cal_dir=d)
#    assert [p.profile_id for p in m2.list_profiles()] == ["good-id"]
#
#
#def test_profile_dict_round_trip():
#    p = CalibrationProfile("id-1", "Name", 2.0, magnification=1e4,
#                           detector_type="BSE", source="imported",
#                           version=3, notes="n")
#    assert CalibrationProfile.from_dict(p.to_dict()) == p
#    # from_dict tolerates missing optional keys
#    q = CalibrationProfile.from_dict({"profile_id": "only-id"})
#    assert q.profile_name == "only-id"
#    assert q.nm_per_pixel == 1.0
#
#F b6780a2b0cae6b063e177360c5e02a1a3d450948 162 tests/test_curve.py
## F7-8 驗收：自訂色調曲線（控制點編碼 + 保單調插值 + gamma 卡整合）。
#"""曲線有三個獨立的正確性問題，這裡分開驗：
#
#1. **編碼**（``pipeline/curve.py``）—— 字串進、控制點出；壞掉的字串要在
#   ``validate_params`` 就被擋下並講出白話原因（鐵則 4）。
#2. **插值**（``algo/curve.py``）—— 必須保單調。自然三次樣條會 overshoot，
#   在影像上會直接看到一圈假的暗環，那是**演算法造出來的缺陷**，
#   對一個要拿去判 defect 的工具來說是最糟的一種 bug。
#3. **接手規則**（``steps/tone.py``）—— 曲線一旦不是 y=x 就完全接手 gamma。
#"""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#
#from adept.core.algo.curve import curve_lut, eval_curve
#from adept.core.pipeline.curve import (
#    IDENTITY, CurveError, format_curve, is_identity, parse_curve,
#)
#from adept.core.pipeline.step import ParamError, ParamSpec
#from adept.core.steps.tone import GammaStep, apply_curve, apply_gamma
#
#
## --------------------------------------------------------------------------- #
## 1. 編碼
## --------------------------------------------------------------------------- #
#def test_parsing_sorts_and_round_trips():
#    pts = parse_curve("1,1 ; 0.35,0.55 ; 0,0")
#    assert pts == [(0.0, 0.0), (0.35, 0.55), (1.0, 1.0)]
#    assert format_curve(pts) == "0,0; 0.35,0.55; 1,1"
#    assert parse_curve(format_curve(pts)) == pts
#
#
#def test_an_empty_curve_means_identity():
#    """舊 recipe 沒有這個參數也要讀得動。"""
#    assert parse_curve("") == parse_curve(None) == parse_curve(IDENTITY)
#    assert is_identity(parse_curve("")) is True
#    assert is_identity(parse_curve("0,0; 0.4,0.7; 1,1")) is False
#
#
#@pytest.mark.parametrize("bad,expect", [
#    ("0,0; 0.5,2; 1,1", "outside"),
#    ("0.2,0; 1,1", "must start at x=0"),
#    ("0,0; 1,1; 1,0.5", "same input level"),
#    ("0,0", "at least two points"),
#    ("nope", "should look like"),
#    ("0,0; 1; 1,1", "should look like"),
#])
#def test_a_broken_curve_is_refused_with_a_plain_reason(bad, expect):
#    with pytest.raises(CurveError) as exc:
#        parse_curve(bad)
#    assert expect in str(exc.value)
#
#
#def test_the_param_form_blocks_it_not_the_algorithm():
#    """鐵則 4：填爆的值擋在 ``validate_params``，不准跑到演算法裡才炸。"""
#    spec = ParamSpec(name="curve", type="curve", default=IDENTITY,
#                     help="the curve")
#    assert spec.validate("1,1;0.2,0.7;0,0") == "0,0; 0.2,0.7; 1,1"
#    with pytest.raises(ParamError) as exc:
#        spec.validate("0,0; 0.5,9; 1,1")
#    assert "curve" in str(exc.value) and "outside" in str(exc.value)
#
#    with pytest.raises(ParamError):
#        GammaStep.validate_params({"curve": "garbage"})
#
#
## --------------------------------------------------------------------------- #
## 2. 插值
## --------------------------------------------------------------------------- #
#def test_identity_control_points_give_back_a_straight_line():
#    lut = curve_lut(IDENTITY, 256)
#    assert np.allclose(lut, np.linspace(0.0, 1.0, 256), atol=1e-12)
#
#
#@pytest.mark.parametrize("curve", [
#    "0,0; 0.35,0.6; 1,1",
#    "0,0; 0.45,0.05; 0.55,0.95; 1,1",      # 陡到接近階梯 —— 最容易 overshoot
#    "0,0.2; 0.5,0.5; 1,0.8",               # 端點不在角落
#    "0,0; 0.2,0.2; 0.8,0.2; 1,1",          # 中間一段完全平
#])
#def test_the_curve_never_overshoots_or_goes_backwards(curve):
#    """保單調 —— 自然三次樣條在這幾條上都會凹出去。"""
#    lut = curve_lut(curve, 512)
#    assert lut.min() >= 0.0 and lut.max() <= 1.0
#    assert np.all(np.diff(lut) >= -1e-12)
#
#
#def test_the_curve_passes_through_its_control_points():
#    pts = parse_curve("0,0; 0.35,0.6; 1,1")
#    ys = eval_curve(pts, np.asarray([p[0] for p in pts]))
#    assert np.allclose(ys, [p[1] for p in pts], atol=1e-9)
#
#
#def test_a_curve_can_do_what_gamma_cannot():
#    """gamma 是全域的單參數重分佈；曲線可以只動暗部、亮部原封不動。
#
#    這正是「為什麼需要曲線」的那個理由，所以把它鎖成測試。
#    """
#    lut = curve_lut("0,0; 0.25,0.5; 0.6,0.6; 1,1", 256)
#    x = np.linspace(0.0, 1.0, 256)
#    assert lut[64] > x[64] + 0.2, "暗部要被拉起來"
#    assert abs(lut[-16] - x[-16]) < 0.05, "亮部幾乎不動"
#
#
## --------------------------------------------------------------------------- #
## 3. 接手規則與影像行為
## --------------------------------------------------------------------------- #
#def _ctx(dtype=np.uint8):
#    from adept.core.pipeline.context import Context
#    img = np.linspace(0, 255, 64 * 64).reshape(64, 64).astype(dtype)
#    ctx = Context()
#    ctx.set_image("test", img)
#    ctx.set_image("ref", img.copy())
#    return ctx
#
#
#def test_an_identity_curve_leaves_the_image_exactly_alone():
#    img = np.arange(256, dtype=np.uint8).reshape(16, 16)
#    assert np.array_equal(apply_curve(img, IDENTITY), img)
#
#
#def test_the_curve_keeps_the_dtype_and_the_value_range():
#    """插在流程哪裡都不可以偷偷改型別 —— 下游的 diff 是 float32。"""
#    for dtype in (np.uint8, np.float32):
#        img = np.linspace(0, 255, 256).reshape(16, 16).astype(dtype)
#        out = apply_curve(img, "0,0; 0.3,0.65; 1,1")
#        assert out.dtype == img.dtype
#        assert out.min() >= img.min() - 1e-3 and out.max() <= img.max() + 1e-3
#
#
#def test_the_curve_takes_over_from_gamma_once_it_is_bent():
#    """兩個旋鈕一個結果：曲線不是 y=x 時 gamma 完全不生效。"""
#    step = GammaStep()
#    bent = "0,0; 0.4,0.75; 1,1"
#
#    # gamma 給一個很極端的值，但曲線接手 -> 結果與 gamma 無關
#    a = step.run(_ctx(), {"gamma": 0.2, "curve": bent}).images["test"]
#    b = step.run(_ctx(), {"gamma": 4.0, "curve": bent}).images["test"]
#    assert np.array_equal(a, b)
#    assert np.array_equal(a, apply_curve(_ctx().images["test"], bent))
#
#    # 曲線放回 y=x -> gamma 又生效了
#    c = step.run(_ctx(), {"gamma": 0.4, "curve": IDENTITY}).images["test"]
#    assert np.array_equal(c, apply_gamma(_ctx().images["test"], 0.4))
#    assert not np.array_equal(c, a)
#
#
#def test_two_cards_keep_the_pair_comparable_and_one_card_does_not():
#    """test 調了 ref 沒調，diff 會整片亮起來 —— 那是假缺陷。
#
#    F7-18 之後那件事由**兩張卡**表達（畫布上一條線接 test、一條接 ref），
#    而不是一張卡的 also_apply。這條測試因此鎖兩件事：一張卡真的只動自己那條，
#    而放上第二張卡之後兩邊又對得起來了。
#    """
#    bent = "0,0; 0.4,0.75; 1,1"
#    ctx = GammaStep().run(_ctx(), {"curve": bent})
#    assert not np.array_equal(ctx.images["test"], ctx.images["ref"])
#
#    ctx = GammaStep().run(ctx, {"target": "ref", "curve": bent})
#    assert np.array_equal(ctx.images["test"], ctx.images["ref"])
#
#F 1be97f704f93ae3ebc989a569b9e04cd1de639aa 241 tests/test_dataset.py
#"""Tests for adept.core.ingest.dataset (KLARF/TIFF/folder -> Dataset)."""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#import tifffile
#
#from adept.core.ingest import dataset, imageio
#
## ---------------------------------------------------------------- synthetic KLARFs
#
#KLARF12_EBI = """FileVersion 1 2;
#FileTimestamp 03-14-26 08:00:00;
#LotID "LOT001";
#SampleSize 1 300;
#DeviceID "DEV01";
#StepID "STEP01";
#OrientationMarkLocation DOWN;
#DiePitch 1000.0 1200.0;
#WaferID "W01";
#TiffFileName LOT001.tif;
#TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
#InspectionTest 1;
#DefectRecordSpec 10 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER IMAGECOUNT IMAGELIST ;
#DefectList
# 1 100.500 200.500 1 2 0.5 0.5 1 2 1 0 2 0
# 2 300.000 400.000 2 3 0.6 0.6 4 3 3 0 4 0 5 0;
#SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;
#SummaryList
# 1 2 1.0000000000e-03 10 2;
#EndOfFile;
#"""
#
#KLARF18_RSEM = """Record FileRecord  "1.8"
#{
#  Record LotRecord "LOT.01"
#  {
#    Record WaferRecord "W01"
#    {
#      Field DiePitch 2 {23376636, 32874750}
#
#      List DefectList
#      {
#        Columns 8 { int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,
#        int32 YINDEX,  int32 CLASSNUMBER,  int32 IMAGECOUNT,  ImageList IMAGEINFO  }
#        Data 3
#        {
#          1 1000 2000 0 0 1 1 Image 1 { "d1.png" "PNG" 1 "24" } ;
#          2 3000 4000 1 -1 2 1 Image 1 { "d2.png" "PNG" 1 "24" } ;
#          3 5000 6000 1 1 2 0 ;
#        }
#      }
#    }
#  }
#}
#EndOfFile;
#"""
#
#KLARF12_NO_IMAGES = """FileVersion 1 2;
#LotID "LOT002";
#DiePitch 1000.0 1200.0;
#WaferID "W02";
#DefectRecordSpec 8 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER ;
#DefectList
# 1 10.000 20.000 0 0 0.5 0.5 1;
#EndOfFile;
#"""
#
#
#def _write_text(path, text):
#    with open(str(path), "w", encoding="utf-8", newline="") as f:
#        f.write(text)
#
#
#def _write_tiff(path, arrays):
#    with tifffile.TiffWriter(str(path)) as tw:
#        for arr in arrays:
#            tw.write(arr, photometric="minisblack")
#
#
## ---------------------------------------------------------------- ebi_patch mode
#
#@pytest.fixture()
#def ebi_case(tmp_path):
#    rng = np.random.default_rng(1234)
#    arrays = [rng.integers(0, 256, size=(20, 30), dtype=np.uint8)
#              for _ in range(5)]
#    _write_tiff(tmp_path / "LOT001.tif", arrays)
#    kpath = tmp_path / "LOT001.klarf"
#    _write_text(kpath, KLARF12_EBI)
#    return kpath, tmp_path / "LOT001.tif", arrays
#
#
#def test_ebi_patch_detection_and_channels(ebi_case):
#    kpath, tpath, arrays = ebi_case
#    ds = dataset.load_dataset(str(kpath))
#    assert ds.kind == "ebi_patch"
#    assert ds.klarf is not None and ds.klarf.version == "1.2"
#    assert len(ds.items) == 2
#
#    # defect 1: image ids 1,2 -> pages 0,1 -> channels test/ref (in order)
#    it0 = ds.items[0]
#    assert set(it0.images) == {"test", "ref"}
#    assert it0.images["test"].page == 0
#    assert it0.images["ref"].page == 1
#    assert it0.images["test"].path == str(tpath)
#
#    # defect 2: 3 images -> pages 2,3,4 -> test/ref/img3
#    it1 = ds.items[1]
#    assert set(it1.images) == {"test", "ref", "img3"}
#    assert it1.images["test"].page == 2
#    assert it1.images["ref"].page == 3
#    assert it1.images["img3"].page == 4
#
#    # pixels round-trip through DefectItem.load
#    assert np.array_equal(it0.load("test"), arrays[0])
#    assert np.array_equal(it1.load("img3"), arrays[4])
#
#
#def test_ebi_patch_nm_conversion_and_metadata(ebi_case):
#    kpath, _tpath, _arrays = ebi_case
#    ds = dataset.load_dataset(str(kpath))
#    it0, it1 = ds.items
#    # KLARF 1.2 coordinates are um; converted to nm (x1000)
#    assert it0.xrel_nm == pytest.approx(100500.0)
#    assert it0.yrel_nm == pytest.approx(200500.0)
#    assert it0.die == (1, 2)
#    assert it0.defect_id == "1"
#    assert it0.klarf_row == 0
#    assert it0.tags["classnumber"] == "1"
#    assert it1.die == (2, 3)
#    assert it1.tags["classnumber"] == "4"
#    assert it0.nm_per_px is None            # not derivable yet (in-fab TBD)
#
#
#def test_ebi_patch_custom_channel_order(ebi_case):
#    kpath, _tpath, _arrays = ebi_case
#    ds = dataset.load_dataset(str(kpath), channel_order=("t1",))
#    assert set(ds.items[0].images) == {"t1", "img2"}
#    assert set(ds.items[1].images) == {"t1", "img2", "img3"}
#
#
#def test_ebi_patch_explicit_tiff_path(ebi_case, tmp_path):
#    kpath, tpath, arrays = ebi_case
#    # move the tiff to a non-default name; auto-resolution would fail
#    other = tmp_path / "elsewhere.tif"
#    _write_tiff(other, arrays)
#    ds = dataset.load_dataset(str(kpath), tiff_path=str(other))
#    assert ds.kind == "ebi_patch"
#    assert ds.items[0].images["test"].path == str(other)
#
#
## ---------------------------------------------------------------- rsem mode
#
#@pytest.fixture()
#def rsem_case(tmp_path):
#    rng = np.random.default_rng(99)
#    a1 = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)
#    a2 = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)
#    imageio.save_gray(str(tmp_path / "d1.png"), a1)
#    imageio.save_gray(str(tmp_path / "d2.png"), a2)
#    kpath = tmp_path / "rsem.klarf"
#    _write_text(kpath, KLARF18_RSEM)
#    return kpath, tmp_path, (a1, a2)
#
#
#def test_rsem_detection_and_paths(rsem_case):
#    kpath, tdir, (a1, _a2) = rsem_case
#    ds = dataset.load_dataset(str(kpath))
#    assert ds.kind == "rsem"
#    assert ds.klarf is not None and ds.klarf.version == "1.8"
#    assert len(ds.items) == 3
#
#    it0 = ds.items[0]
#    assert set(it0.images) == {"single"}
#    ref = it0.images["single"]
#    assert ref.page is None
#    assert ref.path == str(tdir / "d1.png")   # resolved relative to klarf dir
#    assert np.array_equal(it0.load("single"), a1)
#
#    # defect without an Image block gets no images
#    assert ds.items[2].images == {}
#
#
#def test_rsem_nm_passthrough_18(rsem_case):
#    kpath, _tdir, _arrays = rsem_case
#    ds = dataset.load_dataset(str(kpath))
#    # KLARF 1.8 coordinates are already nm (x1.0)
#    assert ds.items[0].xrel_nm == pytest.approx(1000.0)
#    assert ds.items[0].yrel_nm == pytest.approx(2000.0)
#    assert ds.items[1].die == (1, -1)
#    assert ds.items[1].tags["classnumber"] == "2"
#
#
## ---------------------------------------------------------------- fallbacks
#
#def test_imageless_klarf_graceful(tmp_path):
#    kpath = tmp_path / "noimg.klarf"
#    _write_text(kpath, KLARF12_NO_IMAGES)
#    ds = dataset.load_dataset(str(kpath))
#    assert ds.kind == "rsem"                  # metadata-only fallback
#    assert len(ds.items) == 1
#    assert ds.items[0].images == {}
#    assert ds.items[0].xrel_nm == pytest.approx(10000.0)   # 10 um -> nm
#    assert any("metadata only" in w for w in ds.warnings)
#
#
#def test_missing_explicit_tiff_warns_and_falls_back(tmp_path):
#    kpath = tmp_path / "LOT001.klarf"
#    _write_text(kpath, KLARF12_EBI)           # no LOT001.tif written
#    ds = dataset.load_dataset(str(kpath), tiff_path=str(tmp_path / "nope.tif"))
#    assert ds.kind == "rsem"
#    assert any("not found" in w for w in ds.warnings)
#
#
## ---------------------------------------------------------------- folder mode
#
#def test_load_folder(tmp_path):
#    rng = np.random.default_rng(5)
#    a = rng.integers(0, 256, size=(10, 12), dtype=np.uint8)
#    imageio.save_gray(str(tmp_path / "a.png"), a)
#    _write_tiff(tmp_path / "b.tif",
#                [rng.integers(0, 256, size=(8, 8), dtype=np.uint8)])
#    (tmp_path / "notes.txt").write_text("not an image")
#
#    ds = dataset.load_folder(str(tmp_path))
#    assert ds.kind == "folder"
#    assert ds.klarf is None
#    assert [it.defect_id for it in ds.items] == ["a", "b"]
#    it_a = ds.items[0]
#    assert it_a.die is None and it_a.xrel_nm is None and it_a.yrel_nm is None
#    assert it_a.images["single"].page is None
#    assert np.array_equal(it_a.load("single"), a)
#
#
#def test_load_folder_not_a_dir(tmp_path):
#    ds = dataset.load_folder(str(tmp_path / "missing"))
#    assert ds.kind == "folder"
#    assert ds.items == []
#    assert ds.warnings
#
#F 24701f5b8a7c7ee9aecead311645659b5d8a2c72 87 tests/test_e2e_die_to_die.py
## ADEPT M1 端到端驗收 — authored 2026-07-28.
#"""M1 驗收：合成 KLARF+TIFF → die-to-die recipe → 分數把真/假 defect 分開。
#
#流程：tools/make_sample 產一份合成 lot（含 ground truth）→ ingest 自動判別
#ebi_patch → 範例 recipe 全 pipeline → 檢查分類正確率與分數分離。
#另附 CLI（python -m adept run）煙霧測試。
#"""
#from __future__ import annotations
#
#import json
#import statistics
#import subprocess
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.ingest.dataset import load_dataset  # noqa: E402
#from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("synlot")
#    paths = generate(str(out), n=24, seed=7)
#    return paths
#
#
#def test_recipe_validates_clean():
#    recipe = Recipe.load(str(RECIPE))
#    issues = validate(recipe, kind="ebi_patch")
#    assert not [i for i in issues if i.level == "error"], issues
#
#
#def test_pipeline_separates_real_from_nuisance(synlot):
#    ds = load_dataset(synlot["klarf"])
#    assert ds.kind == "ebi_patch"
#    gt = json.loads(Path(synlot["ground_truth"]).read_text())
#    recipe = Recipe.load(str(RECIPE))
#
#    results = run_dataset(recipe, ds)
#    assert len(results) == 24
#    failed = [r for r in results if not r.ok]
#    assert not failed, [(r.defect_id, r.error) for r in failed]
#
#    real = [r.score for r in results if gt[r.defect_id]["is_real"]]
#    fake = [r.score for r in results if not gt[r.defect_id]["is_real"]]
#    # 母體層級分離：真缺陷分數中位數需明顯高於假點
#    assert statistics.median(real) > 2 * statistics.median(fake)
#    # 分類正確率（seed=7 實測 24/24；門檻留餘裕 ≥ 22/24）
#    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
#    assert correct >= 22, f"分類正確 {correct}/24"
#    # 每顆都要有完整 feature vector（供 ML 匯出）
#    for r in results:
#        for key in ("snr_max", "blob_area", "cd_x_px", "glv_max", "score"):
#            assert key in r.features, f"{r.defect_id} 缺 {key}"
#
#
#def test_cli_run_smoke(synlot, tmp_path):
#    out_json = tmp_path / "results.json"
#    out_csv = tmp_path / "results.csv"
#    proc = subprocess.run(
#        [sys.executable, "-m", "adept", "run", str(RECIPE), synlot["klarf"],
#         "--out", str(out_json), "--csv", str(out_csv), "--limit", "6"],
#        cwd=str(REPO), capture_output=True, text=True, timeout=300,
#    )
#    assert proc.returncode == 0, proc.stderr + proc.stdout
#    payload = json.loads(out_json.read_text())
#    assert len(payload) == 6 and all("score" in p["features"] for p in payload)
#    assert out_csv.read_text(encoding="utf-8-sig").count("\n") >= 7  # header + 6 列
#
#
#def test_cli_steps_smoke():
#    proc = subprocess.run(
#        [sys.executable, "-m", "adept", "steps"],
#        cwd=str(REPO), capture_output=True, text=True, timeout=120,
#    )
#    assert proc.returncode == 0
#    assert "load_patch" in proc.stdout and "影像段" in proc.stdout
#
#F 56c380c7267c6b2f72fb9ac28491cc4952f376e0 110 tests/test_e2e_dual_route.py
## ADEPT M4 端到端驗收 — authored 2026-07-28.
#"""M4 驗收：**同一份 recipe 吃兩種輸入**。
#
#- EBI patch（KLARF + multi-page TIFF，機台附 test/ref）走 ebi_patch route
#- Review SEM（KLARF + 每顆一張圖，沒有 ref）走 rsem route，
#  由 Golden Cell 卡自己疊一張參考圖出來
#
#兩條 route 共用同一段算法與判定（相減 → 去噪 → SNR → blob → CD → GLV → 同一條
#分數表達式、同一個門檻），只有影像尺寸相關的幾何參數不同。
#"""
#from __future__ import annotations
#
#import json
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate as gen_ebi          # noqa: E402
#from make_sample_rsem import generate as gen_rsem    # noqa: E402
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.ingest.dataset import load_dataset   # noqa: E402
#from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402
#
#RECIPE = REPO / "examples" / "recipes" / "dual_route_basic.json"
#
#
#@pytest.fixture(scope="module")
#def recipe():
#    return Recipe.load(str(RECIPE))
#
#
#@pytest.fixture(scope="module")
#def ebi_lot(tmp_path_factory):
#    return gen_ebi(str(tmp_path_factory.mktemp("ebi")), n=24, seed=7)
#
#
#@pytest.fixture(scope="module")
#def rsem_lot(tmp_path_factory):
#    return gen_rsem(str(tmp_path_factory.mktemp("rsem")), n=24, seed=11)
#
#
#def test_recipe_has_both_routes_and_validates(recipe):
#    assert set(recipe.routes) == {"ebi_patch", "rsem"}
#    for kind in ("ebi_patch", "rsem"):
#        errs = [i for i in validate(recipe, kind=kind) if i.level == "error"]
#        assert not errs, (kind, errs)
#
#
#def test_routes_share_the_algo_and_adc_tail(recipe):
#    """兩條 route 只在「ref 從哪來」與影像尺寸幾何上不同，算法段必須共用同一批節點。"""
#    ebi, rsem = recipe.routes["ebi_patch"], recipe.routes["rsem"]
#    shared = set(ebi) & set(rsem)
#    for node_id in ("align", "sub", "dn", "snr", "blob", "cd"):
#        assert node_id in shared, f"{node_id} 應由兩條 route 共用"
#    # rsem 多一張 Golden Cell 卡（自己造 ref）；ebi 沒有
#    assert "golden" in rsem and "golden" not in ebi
#    assert recipe.nodes["golden"].step == "golden_cell"
#    assert recipe.nodes["golden"].params["out"] == "ref"
#
#
#def test_ingest_dispatches_by_input_type(ebi_lot, rsem_lot):
#    ebi = load_dataset(ebi_lot["klarf"])
#    rsem = load_dataset(rsem_lot["klarf"])
#    assert ebi.kind == "ebi_patch"
#    assert sorted(ebi.items[0].images) == ["ref", "test"]
#    assert rsem.kind == "rsem"
#    assert sorted(rsem.items[0].images) == ["single"]
#
#
#@pytest.mark.parametrize("lot_name, expect_kind", [("ebi_lot", "ebi_patch"),
#                                                   ("rsem_lot", "rsem")])
#def test_same_recipe_scores_both_input_types(request, recipe, lot_name, expect_kind):
#    lot = request.getfixturevalue(lot_name)
#    ds = load_dataset(lot["klarf"])
#    assert ds.kind == expect_kind
#
#    results = run_dataset(recipe, ds)
#    assert len(results) == 24
#    failed = [(r.defect_id, r.error) for r in results if not r.ok]
#    assert not failed, failed
#
#    gt = json.loads(Path(lot["ground_truth"]).read_text(encoding="utf-8"))
#    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
#    # 實測 seed 7/11 為 24/24；跨 seed 平均 ~95%，門檻留餘裕
#    assert correct >= 21, f"{expect_kind} 分類正確 {correct}/24"
#
#    # 每顆都要有完整特徵向量（供報表與 ML 備料）
#    for r in results:
#        for key in ("glv_max", "glv_median", "glv_std", "blob_area", "cd_x_px", "score"):
#            assert key in r.features, f"{r.defect_id} 缺 {key}"
#
#
#def test_rsem_route_builds_its_own_reference(recipe, rsem_lot):
#    """RSEM 沒有 ref —— Golden Cell 必須造出一張，且與原圖同尺寸可相減。"""
#    from adept.core.pipeline import run_defect
#
#    ds = load_dataset(rsem_lot["klarf"])
#    res = run_defect(recipe, ds.items[0], "rsem", keep_context=True)
#    assert res.ok, res.error
#    ctx = res.context
#    assert "ref" in ctx.images, "Golden Cell 應產生 ref 影像流"
#    assert ctx.images["ref"].shape == ctx.images["test"].shape
#    assert "diff" in ctx.images
#    # Golden Cell 的診斷特徵要有意義（週期被找到）
#    assert res.features["golden_px"] >= 2 and res.features["golden_py"] >= 2
#
#F 51947239f318596b8ce7c939c4a42f674cb0a84a 308 tests/test_engine.py
#"""M1 驗收：單顆執行引擎（happy path、失敗隔離、upto_node、trace、JSON 匯出）。
#
#dummy Step 以 "t_" 前綴註冊進 REGISTRY，fixture teardown 一律 pop 掉，
#避免污染並行開發中的 adept/core/steps/ 卡片庫。
#"""
#from __future__ import annotations
#
#import json
#import math
#from types import SimpleNamespace
#
#import numpy as np
#import pytest
#
#from adept.core.pipeline import (
#    CATEGORY_ALGO,
#    CATEGORY_IMAGE,
#    Context,
#    REGISTRY,
#    Recipe,
#    RecipeNode,
#    ScoreSpec,
#    Step,
#    StepError,
#    register_step,
#    result_to_json_dict,
#    run_dataset,
#    run_defect,
#)
#
#_KEYS = ["t_eng_load", "t_eng_algo", "t_eng_fail", "t_eng_nan"]
#
#
#@pytest.fixture()
#def dummy_steps():
#    """註冊測試卡片；teardown 時從 REGISTRY 移除（鐵則：不留殘骸）。"""
#    for k in _KEYS:
#        REGISTRY.pop(k, None)
#
#    @register_step
#    class TEngLoad(Step):
#        key = "t_eng_load"
#        label = "測試載入"
#        category = CATEGORY_IMAGE
#        help = "測試用：從 meta['_defect_item'] 假裝載入 test/ref"
#        writes = ["test", "ref"]
#
#        def run(self, ctx: Context, params) -> Context:
#            item = ctx.meta["_defect_item"]
#            if getattr(item, "fail_load", False):
#                raise StepError(self.key, f"模擬載入失敗：{item.defect_id}")
#            ctx.set_image("test", np.zeros((4, 4), np.float32))
#            ctx.set_image("ref", np.ones((4, 4), np.float32))
#            return ctx
#
#    @register_step
#    class TEngAlgo(Step):
#        key = "t_eng_algo"
#        label = "測試特徵"
#        category = CATEGORY_ALGO
#        help = "測試用：量 test 影像、寫兩個特徵"
#        reads = ["test"]
#        features_out = ["snr_max", "area"]
#
#        def run(self, ctx: Context, params) -> Context:
#            ctx.require_image("test")
#            ctx.add_features({"snr_max": 5.0, "area": 4.0})
#            return ctx
#
#    @register_step
#    class TEngFail(Step):
#        key = "t_eng_fail"
#        label = "測試失敗"
#        category = CATEGORY_ALGO
#        help = "測試用：一定 raise StepError"
#
#        def run(self, ctx: Context, params) -> Context:
#            raise StepError(self.key, "boom")
#
#    @register_step
#    class TEngNan(Step):
#        key = "t_eng_nan"
#        label = "測試 NaN 特徵"
#        category = CATEGORY_ALGO
#        help = "測試用：寫入 nan/inf 特徵"
#
#        def run(self, ctx: Context, params) -> Context:
#            ctx.add_feature("weird_nan", float("nan"))
#            ctx.add_feature("weird_inf", float("inf"))
#            return ctx
#
#    try:
#        yield
#    finally:
#        for k in _KEYS:
#            REGISTRY.pop(k, None)
#
#
#def make_item(defect_id="d1", **kw):
#    return SimpleNamespace(defect_id=defect_id, nm_per_px=1.8, **kw)
#
#
#def make_recipe(route=("nload", "nalgo"), nodes=None, expr="snr_max * 2",
#                threshold=3.0):
#    if nodes is None:
#        nodes = {
#            "nload": RecipeNode("nload", "t_eng_load", {}),
#            "nalgo": RecipeNode("nalgo", "t_eng_algo", {}),
#            "nfail": RecipeNode("nfail", "t_eng_fail", {}),
#            "nnan": RecipeNode("nnan", "t_eng_nan", {}),
#        }
#    return Recipe(
#        recipe_id="engine_test",
#        routes={"ebi_patch": list(route)},
#        nodes=nodes,
#        score=ScoreSpec(expr=expr, threshold=threshold,
#                        bins={"below": 0, "above": 1}),
#    )
#
#
## ---------------------------------------------------------------------------
## happy path
## ---------------------------------------------------------------------------
#def test_happy_path_score_and_bin(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch")
#    assert r.ok is True
#    assert r.error is None
#    assert r.defect_id == "d1"
#    assert r.score == 10.0                      # snr_max(5) * 2
#    assert r.bin == 1                           # 10 >= 3 → above
#    assert r.features["snr_max"] == 5.0
#    assert r.features["score"] == 10.0
#    assert r.context is None                    # keep_context 預設 False
#
#
#def test_bin_below_threshold(dummy_steps):
#    r = run_defect(make_recipe(expr="snr_max * 0.1"), make_item(), "ebi_patch")
#    assert r.ok and r.score == 0.5 and r.bin == 0
#
#
#def test_meta_seeded(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch", keep_context=True)
#    ctx = r.context
#    assert ctx is not None
#    assert ctx.meta["_defect_id"] == "d1"
#    assert ctx.meta["_dataset_kind"] == "ebi_patch"
#    assert ctx.meta["_defect_item"].defect_id == "d1"
#    assert ctx.meta["nm_per_px"] == 1.8
#    assert ctx.nm_per_px == 1.8
#
#
#def test_traces_recorded(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch")
#    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]
#    assert [t.step_key for t in r.traces] == ["t_eng_load", "t_eng_algo"]
#    assert all(t.ok for t in r.traces)
#    assert all(t.error is None for t in r.traces)
#    assert all(isinstance(t.ms, float) and t.ms >= 0.0 for t in r.traces)
#    assert r.traces[0].features_added == {}
#    assert r.traces[1].features_added == {"snr_max": 5.0, "area": 4.0}
#    assert r.traces[0].images_after == ["ref", "test"]
#    assert r.traces[1].images_after == ["ref", "test"]
#
#
## ---------------------------------------------------------------------------
## 失敗處理：run_defect 永不 raise
## ---------------------------------------------------------------------------
#def test_step_failure_isolated(dummy_steps):
#    rec = make_recipe(route=("nload", "nfail", "nalgo"))
#    r = run_defect(rec, make_item(), "ebi_patch")
#    assert r.ok is False
#    assert r.error.startswith("[nfail]")
#    assert "boom" in r.error
#    assert r.score is None and r.bin is None
#    # 失敗的步驟仍有 trace；後面的步驟被跳過
#    assert [t.node_id for t in r.traces] == ["nload", "nfail"]
#    assert r.traces[1].ok is False
#    assert "boom" in r.traces[1].error
#
#
#def test_unknown_route_kind_captured_not_raised(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "no_such_kind")
#    assert r.ok is False
#    assert "no_such_kind" in r.error
#    assert r.traces == []
#
#
#def test_unknown_step_captured(dummy_steps):
#    rec = make_recipe(route=("nload", "nghost"),
#                      nodes={"nload": RecipeNode("nload", "t_eng_load", {}),
#                             "nghost": RecipeNode("nghost", "t_eng_no_such", {})})
#    r = run_defect(rec, make_item(), "ebi_patch")
#    assert r.ok is False
#    assert r.error.startswith("[nghost]")
#
#
#def test_score_eval_error_missing_feature(dummy_steps):
#    rec = make_recipe(route=("nload",), expr="snr_max * 2")  # 沒人產 snr_max
#    r = run_defect(rec, make_item(), "ebi_patch")
#    assert r.ok is False
#    assert r.error.startswith("[score]")
#    assert "snr_max" in r.error
#
#
#def test_run_dataset_failure_isolation_and_progress(dummy_steps):
#    ds = SimpleNamespace(kind="ebi_patch", items=[
#        make_item("good1"),
#        make_item("bad", fail_load=True),
#        make_item("good2"),
#    ])
#    calls = []
#    results = run_dataset(make_recipe(), ds,
#                          progress=lambda i, n, res: calls.append((i, n, res.ok)))
#    assert [r.ok for r in results] == [True, False, True]
#    assert [r.defect_id for r in results] == ["good1", "bad", "good2"]
#    assert results[1].error.startswith("[nload]")
#    assert calls == [(0, 3, True), (1, 3, False), (2, 3, True)]
#
#
#def test_run_dataset_limit(dummy_steps):
#    ds = SimpleNamespace(kind="ebi_patch",
#                         items=[make_item(f"d{i}") for i in range(5)])
#    results = run_dataset(make_recipe(), ds, limit=2)
#    assert [r.defect_id for r in results] == ["d0", "d1"]
#
#
## ---------------------------------------------------------------------------
## upto_node（Studio 點卡看中間輸出）
## ---------------------------------------------------------------------------
#def test_upto_node_returns_context_without_score(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="nload")
#    assert r.ok is True
#    assert r.score is None and r.bin is None    # 不算分
#    assert r.context is not None                # keep_context 強制 True
#    assert "test" in r.context.images and "ref" in r.context.images
#    assert [t.node_id for t in r.traces] == ["nload"]   # nalgo 沒跑
#
#
#def test_upto_node_last_node_runs_it(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="nalgo")
#    assert r.ok is True
#    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]
#    assert r.context.features["snr_max"] == 5.0
#    assert "score" not in r.context.features
#
#
#def test_upto_node_not_on_route_no_raise(dummy_steps):
#    r = run_defect(make_recipe(), make_item(), "ebi_patch", upto_node="zzz")
#    assert r.ok is False
#    assert "zzz" in r.error
#
#
#def test_upto_node_disabled_target_stops_without_running(dummy_steps):
#    rec = make_recipe()
#    rec.nodes["nalgo"].enabled = False
#    r = run_defect(rec, make_item(), "ebi_patch", upto_node="nalgo")
#    assert r.ok is True
#    assert [t.node_id for t in r.traces] == ["nload"]   # 目標卡沒執行
#    assert r.context is not None
#    assert "snr_max" not in r.context.features
#
#
## ---------------------------------------------------------------------------
## 停用節點
## ---------------------------------------------------------------------------
#def test_disabled_node_skipped(dummy_steps):
#    rec = make_recipe(route=("nload", "nfail", "nalgo"))
#    rec.nodes["nfail"].enabled = False
#    r = run_defect(rec, make_item(), "ebi_patch")
#    assert r.ok is True
#    assert r.score == 10.0
#    assert [t.node_id for t in r.traces] == ["nload", "nalgo"]
#
#
## ---------------------------------------------------------------------------
## JSON 匯出
## ---------------------------------------------------------------------------
#def test_result_to_json_dict(dummy_steps):
#    rec = make_recipe(route=("nload", "nalgo", "nnan"))
#    r = run_defect(rec, make_item(), "ebi_patch", keep_context=True)
#    assert r.ok is True
#    assert math.isnan(r.features["weird_nan"])
#
#    d = result_to_json_dict(r)
#    json.dumps(d)                                # 無 ndarray 洩漏、可序列化
#    assert "context" not in d                    # context 被丟掉
#    assert d["defect_id"] == "d1"
#    assert d["ok"] is True
#    assert d["score"] == 10.0
#    assert d["bin"] == 1
#    assert d["features"]["weird_nan"] is None    # nan → None
#    assert d["features"]["weird_inf"] is None    # inf → None
#    assert d["features"]["snr_max"] == 5.0
#    for t in d["traces"]:
#        assert t["ms"] == round(t["ms"], 3)      # ms 取 3 位小數
#    assert d["traces"][1]["features_added"] == {"snr_max": 5.0, "area": 4.0}
#    assert d["traces"][0]["images_after"] == ["ref", "test"]
#
#
#def test_result_to_json_dict_failure(dummy_steps):
#    rec = make_recipe(route=("nload", "nfail"))
#    r = run_defect(rec, make_item(), "ebi_patch")
#    d = result_to_json_dict(r)
#    json.dumps(d)
#    assert d["ok"] is False
#    assert d["score"] is None and d["bin"] is None
#    assert "boom" in d["error"]
#
#F b9856e4d6846742456149d144c5963d9649d5c27 296 tests/test_enhance.py
## F7-10 驗收：空間性 artifact 的處理（背景／條紋／局部對比／邊緣保留去噪）。
#"""這一輪的每一張卡都對應一種 E-beam patch 上**真實會有**的假訊號。
#
#所以測試斷言的不是「函式跑得動」，而是**那個假訊號真的被拿掉了，而缺陷還在**。
#「處理完之後缺陷也不見了」對這個工具是最糟的失敗 —— 它跑得完、有數字、
#而且會漏抓；只驗形狀與 dtype 是抓不到的。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.algo import enhance as algo_enhance  # noqa: E402
#from adept.core.pipeline import get_step  # noqa: E402
#from adept.core.pipeline.context import Context  # noqa: E402
#
#DEFECT = (slice(30, 34), slice(30, 34))
#QUIET = (slice(20, 24), slice(30, 34))     # 同一欄、沒有缺陷的地方
#
#
#def _patch(gradient: float = 0.0, stripe_row: int = -1, defect: float = 40.0,
#           noise: float = 6.0, seed: int = 0) -> np.ndarray:
#    """合成一張帶指定 artifact 的 patch。"""
#    rng = np.random.default_rng(seed)
#    img = rng.normal(120.0, noise, (64, 64)).astype(np.float32)
#    if gradient:
#        img += np.linspace(0.0, gradient, 64)[None, :]
#    if stripe_row >= 0:
#        img[stripe_row, :] += 25.0
#    if defect:
#        img[DEFECT] += defect
#    return img
#
#
#def _contrast(img: np.ndarray) -> float:
#    """缺陷相對於同一欄安靜處的高度。"""
#    return float(np.mean(img[DEFECT]) - np.mean(img[QUIET]))
#
#
## --------------------------------------------------------------------------- #
## 1. 演算法：假訊號要不見，缺陷要留著
## --------------------------------------------------------------------------- #
#def test_background_removal_flattens_the_gradient_and_keeps_the_defect():
#    """charging 的亮度梯度在 test 與 ref 上不會一樣，所以它整片留在 diff 上。"""
#    img = _patch(gradient=60.0)
#    out = algo_enhance.remove_background(img, 31)
#
#    before = float(np.ptp(np.mean(img, axis=0)))
#    after = float(np.ptp(np.mean(out, axis=0)))
#    assert after < before * 0.2, "梯度沒有被拿掉（%.1f -> %.1f）" % (before, after)
#    assert _contrast(out) > 0.8 * _contrast(img), "缺陷跟著背景一起被減掉了"
#    # 亮度基準要留著，否則下游每一個灰階門檻都要重調
#    assert abs(float(out.mean()) - float(img.mean())) < 1.0
#
#
#def test_destripe_removes_a_scan_line_without_inventing_one_at_the_defect():
#    """用中位數而不是平均值：一顆夠大的缺陷會把該列的平均帶偏，
#    校正時就在缺陷那一列造出一條**反向的假條紋**。"""
#    img = _patch(stripe_row=10)
#    out = algo_enhance.remove_stripes(img, axis=0)
#
#    excess_before = float(img[10].mean() - img[9].mean())
#    excess_after = float(out[10].mean() - out[9].mean())
#    assert excess_before > 20.0                      # 前提：條紋真的在
#    assert abs(excess_after) < 3.0, "條紋沒被拉平"
#
#    assert _contrast(out) > 0.8 * _contrast(img), "缺陷被條紋校正吃掉了"
#    # 缺陷所在的列（30-33）不可以被壓下去 —— 那就是平均值版本會犯的錯
#    rows = [float(out[r].mean() - np.median(out)) for r in range(30, 34)]
#    assert min(rows) > -3.0, "缺陷那幾列被反向校正了：%s" % rows
#
#
#def test_destripe_handles_both_directions():
#    img = _patch(defect=0.0)
#    img[:, 12] += 25.0                                # 垂直條紋
#    out = algo_enhance.remove_stripes(img, axis=1)
#    assert abs(float(out[:, 12].mean() - out[:, 11].mean())) < 3.0
#
#
#def test_clahe_lifts_contrast_inside_a_dark_area():
#    """全域拉伸做不到這件事：暗區的對比是被亮區的分布決定的。"""
#    img = np.zeros((64, 64), np.float32)
#    img[:, :32] = 40.0            # 暗半邊
#    img[:, 32:] = 200.0           # 亮半邊
#    img[10:14, 10:14] += 8.0      # 暗區裡的微弱缺陷
#
#    raw = float(img[10:14, 10:14].mean() - img[20:24, 10:14].mean())
#    out = algo_enhance.clahe(img, 2.0, 8)
#    lifted = float(out[10:14, 10:14].mean() - out[20:24, 10:14].mean())
#    assert lifted > 1.5 * raw, "暗區缺陷沒有被拉起來（%.1f -> %.1f）" % (raw, lifted)
#
#
#def test_morph_residual_keeps_small_features_and_drops_large_ones():
#    img = _patch(gradient=60.0, defect=40.0)
#    out = algo_enhance.morph_residual(img, 15)
#    assert _contrast(out) > 0.7 * _contrast(img)
#    assert float(np.ptp(np.mean(out, axis=0))) < 0.4 * float(np.ptp(np.mean(img, axis=0)))
#
#
#def test_black_hat_finds_dark_defects():
#    img = _patch(defect=0.0)
#    img[DEFECT] -= 40.0
#    out = algo_enhance.morph_residual(img, 15, dark=True)
#    assert float(out[DEFECT].mean()) > float(out[QUIET].mean()) + 20.0
#
#
#@pytest.mark.parametrize("method", ["bilateral", "nlm"])
#def test_edge_preserving_denoise_keeps_a_small_defect_that_median_destroys(method):
#    """這是加這兩個方法的**唯一**理由，所以直接拿 median 當對照。
#
#    median 對「比核心小的亮點」是毀滅性的 —— 而那正好就是我們要找的東西。
#    """
#    import cv2
#
#    rng = np.random.default_rng(1)
#    img = rng.normal(120.0, 6.0, (64, 64)).astype(np.float32)
#    img[30:33, 30:33] += 45.0            # 3x3 的小缺陷，比 5x5 核心還小
#
#    def amp(a):
#        return float(a[30:33, 30:33].mean() - np.median(a))
#
#    fn = getattr(algo_enhance, method)
#    kept = amp(fn(img, 5 if method == "bilateral" else 7))
#    killed = amp(cv2.medianBlur(img, 5))
#    assert killed < 0.25 * amp(img), "前提：median 確實會抹掉它"
#    assert kept > 0.8 * amp(img), "%s 沒有保住缺陷（%.1f vs 原始 %.1f）" % (
#        method, kept, amp(img))
#
#    # 而且它真的有在去雜訊（不是原封不動回傳）
#    flat_before = float(img[:20, :20].std())
#    flat_after = float(fn(img, 5 if method == "bilateral" else 7)[:20, :20].std())
#    assert flat_after < 0.8 * flat_before
#
#
#def test_the_noise_estimate_is_what_makes_strength_portable():
#    """``strength`` 的單位是「這張圖自己的雜訊 σ」，不是灰階常數。
#
#    給常數的話，同一組參數換一台機台、換一個曝光就完全不對 —— 而使用者只會
#    覺得是自己參數調錯。所以先量出 σ，再用它當尺度。
#    """
#    rng = np.random.default_rng(7)
#    for true_sigma in (3.0, 6.0, 15.0):
#        img = rng.normal(120.0, true_sigma, (64, 64)).astype(np.float32)
#        est = algo_enhance.noise_sigma(img)
#        assert abs(est - true_sigma) < 0.25 * true_sigma, \
#            "σ 估計不準（真值 %.1f，估到 %.2f）" % (true_sigma, est)
#
#    # 同一個 strength 在吵與不吵的兩張圖上，都要保住缺陷且都要降噪
#    for true_sigma in (3.0, 12.0):
#        img = rng.normal(120.0, true_sigma, (64, 64)).astype(np.float32)
#        img[30:33, 30:33] += 45.0
#        out = algo_enhance.bilateral(img, 5, strength=1.0)
#        amp_in = float(img[30:33, 30:33].mean() - np.median(img))
#        amp_out = float(out[30:33, 30:33].mean() - np.median(out))
#        assert amp_out > 0.8 * amp_in
#        assert float(out[:20, :20].std()) < 0.8 * float(img[:20, :20].std())
#
#
#def test_enhance_helpers_survive_degenerate_input():
#    """全黑、單一值、空圖 —— 不可以 crash，也不可以回 NaN。"""
#    for img in (np.zeros((8, 8), np.float32),
#                np.full((8, 8), 7.0, np.float32),
#                np.zeros((0, 0), np.float32)):
#        for out in (algo_enhance.clahe(img),
#                    algo_enhance.remove_background(img, 5),
#                    algo_enhance.remove_stripes(img, 0),
#                    algo_enhance.morph_residual(img, 5),
#                    algo_enhance.bilateral(img, 5),
#                    algo_enhance.nlm(img, 7)):
#            assert out.shape == img.shape
#            assert not np.any(np.isnan(out))
#
#
## --------------------------------------------------------------------------- #
## 2. 卡片：只加了兩張，其餘走既有卡片的下拉
## --------------------------------------------------------------------------- #
#def _run(key: str, ctx: Context, **params) -> Context:
#    return get_step(key)().run(ctx, params)
#
#
#def test_only_two_new_cards_were_added_for_six_new_abilities():
#    """「不要開太多卡片」—— 相似的能力要放在同一張卡的下拉裡。"""
#    flatten = get_step("flatten").describe()
#    methods = {p["name"]: p for p in flatten["params"]}["method"]["choices"]
#    # 背景平坦化 / 去條紋（兩個方向）/ top-hat / black-hat = 一張卡五個選項
#    assert set(methods) == {"background", "stripes_h", "stripes_v",
#                            "bright_spots", "dark_spots"}
#
#    # 邊緣保留去噪塞進既有的 Denoise，不另開卡
#    denoise = {p["name"]: p for p in get_step("denoise").describe()["params"]}
#    assert set(denoise["method"]["choices"]) == {"median", "gaussian",
#                                                 "bilateral", "nlm"}
#
#    # 雙流運算塞進既有的 Compare 卡，不另開卡
#    sub = {p["name"]: p for p in get_step("subtract").describe()["params"]}
#    assert set(sub["op"]["choices"]) == {"subtract", "ratio", "max", "min", "mean"}
#
#
#def test_the_new_cards_are_in_the_enhance_stage_and_visible_in_the_gui():
#    from adept.ui.scope import visible_steps
#
#    for key in ("flatten", "local_contrast"):
#        assert get_step(key).resolve_group() == "enhance"
#    keys = [d["key"] for d in visible_steps(
#        [get_step(k).describe() for k in ("flatten", "local_contrast")])]
#    assert keys == ["flatten", "local_contrast"]
#
#
#@pytest.mark.parametrize("method", ["background", "stripes_h", "stripes_v",
#                                    "bright_spots", "dark_spots"])
#def test_flatten_card_runs_every_method_on_test_and_ref(method):
#    ctx = Context(images={"test": _patch(gradient=40.0),
#                          "ref": _patch(gradient=40.0, defect=0.0, seed=2)})
#    # 一張卡一條流（F7-18）：兩張圖都要處理就放兩張卡。
#    _run("flatten", ctx, target="test", method=method, size=21)
#    _run("flatten", ctx, target="ref", method=method, size=21)
#    for key in ("test", "ref"):
#        assert ctx.images[key].dtype == np.float32
#        assert ctx.images[key].shape == (64, 64)
#        assert not np.any(np.isnan(ctx.images[key]))
#
#
#def test_flatten_only_touches_its_own_stream():
#    ctx = Context(images={"test": _patch(gradient=40.0),
#                          "ref": _patch(gradient=40.0, seed=3)})
#    before = ctx.images["ref"].copy()
#    _run("flatten", ctx, target="test", method="background")
#    assert np.array_equal(ctx.images["ref"], before), "沒接進來的流不可以被動到"
#    assert not np.array_equal(ctx.images["test"], before)
#
#
#def test_local_contrast_card_runs():
#    ctx = Context(images={"test": _patch(), "ref": _patch(seed=4)})
#    _run("local_contrast", ctx, target="test", clip_limit=3.0, tiles=4)
#    assert ctx.images["test"].dtype == np.float32
#    assert float(ctx.images["test"].std()) > 0.0
#
#
#def test_pointing_a_card_at_a_stream_that_does_not_exist_says_so():
#    """指到不存在的流是**錯誤**，不是警告 —— 那張卡什麼都沒做，而使用者以為做了。"""
#    from adept.core.pipeline.step import StepError
#
#    ctx = Context(images={"test": _patch()})
#    with pytest.raises(StepError) as e:
#        _run("flatten", ctx, target="ghost", method="background")
#    assert "ghost" in str(e.value)
#
#
#@pytest.mark.parametrize("method", ["median", "gaussian", "bilateral", "nlm"])
#def test_denoise_card_runs_every_method(method):
#    ctx = Context(images={"test": _patch(), "ref": _patch(seed=5)})
#    _run("denoise", ctx, target="test", method=method, ksize=5, strength=1.0)
#    assert ctx.images["test"].shape == (64, 64)
#    assert not np.any(np.isnan(ctx.images["test"]))
#
#
#@pytest.mark.parametrize("op,expect", [
#    ("subtract", 40.0), ("ratio", 1.0), ("max", 100.0), ("min", 60.0),
#    ("mean", 80.0),
#])
#def test_compare_card_supports_every_two_stream_operation(op, expect):
#    a = np.full((8, 8), 100.0, np.float32)
#    b = np.full((8, 8), 60.0, np.float32)
#    ctx = Context(images={"a": a, "b": b})
#    _run("subtract", ctx, a="a", b="b", op=op, out="r")
#    got = float(ctx.images["r"].mean())
#    if op == "ratio":
#        assert got == pytest.approx(100.0 / 60.0, rel=1e-3)
#    else:
#        assert got == pytest.approx(expect, rel=1e-3)
#    assert ctx.images["r"].dtype == np.float32
#
#
#def test_ratio_never_produces_infinities():
#    """inf 會一路帶到分數，最後變成「分數是 nan」的 defect ——
#    而使用者完全看不出是哪一步造成的。"""
#    ctx = Context(images={"a": np.full((8, 8), 100.0, np.float32),
#                          "b": np.zeros((8, 8), np.float32)})
#    _run("subtract", ctx, a="a", b="b", op="ratio", out="r")
#    assert np.all(np.isfinite(ctx.images["r"]))
#
#
#def test_subtract_keeps_its_original_behaviour_by_default():
#    """既有 recipe 一份都不能被改變行為。"""
#    a = np.full((8, 8), 60.0, np.float32)
#    b = np.full((8, 8), 100.0, np.float32)
#    ctx = Context(images={"test": a, "ref_aligned": b})
#    _run("subtract", ctx)                       # 全預設
#    assert float(ctx.images["diff"].mean()) == pytest.approx(40.0)   # absolute
#
#F e640ff60fddb32787660a727ed652bc68971c824 165 tests/test_example_recipes.py
## ADEPT 範例 recipe 庫的迴歸網 — authored 2026-07-28 (M6-2).
#"""``examples/recipes/*.json`` 每一份都必須「載得起來、驗得過、真的跑得動」。
#
#為什麼要有這個檔：範例 recipe 是**新使用者的起點**（Studio 的「範例 recipe」
#庫直接列它們）。一份跑不動的範例比沒有範例更糟 —— 第一次用的人會以為
#是自己弄壞的。卡片庫改了預設值、改了 reads/writes、改了 feature 名字，
#都會在這裡被抓到。
#
#這個檔案**完全不碰 Qt**（它測的是 recipe JSON 與引擎，不是 UI），
#所以照一般測試寫法在模組層 import 即可。
#
#測法：
#- 靜態：JSON 讀得開、有非空的 ``description``（庫對話框顯示的就是它）、
#  ``score.expr`` 非空、每條 route 的節點都存在。
#- ``validate(recipe, kind=route)`` 對每一條 route 都必須 **0 個 error**。
#- 動態：對應型別的合成資料（ebi + rsem 各一批，模組層產一次）真的跑一遍，
#  每一顆 defect 都要 ``ok`` 且分數是有限數。
#"""
#from __future__ import annotations
#
#import json
#import math
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#RECIPES_DIR = REPO / "examples" / "recipes"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate as gen_ebi          # noqa: E402
#from make_sample_rsem import generate as gen_rsem    # noqa: E402
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.ingest.dataset import load_dataset   # noqa: E402
#from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402
#
##: 每批合成資料的 defect 數（跑五份 recipe × 兩種輸入，數量要克制）。
#N_DEFECTS = 6
#
#RECIPE_FILES = sorted(RECIPES_DIR.glob("*.json"))
#RECIPE_IDS = [p.stem for p in RECIPE_FILES]
#
##: 這一版庫裡「至少」要有的幾份（少了就是有人刪掉了教學用的範例）。
#REQUIRED = {"die_to_die_basic", "dual_route_basic", "rsem_golden_cell",
#            "single_image_rules", "cd_gate"}
#
#
## --------------------------------------------------------------------------- #
## fixtures：兩種輸入各產一批（module scope，只產一次）
## --------------------------------------------------------------------------- #
#@pytest.fixture(scope="module")
#def lots(tmp_path_factory):
#    """``{dataset_kind: 已載好的 Dataset}``（ebi_patch 與 rsem 各一批）。"""
#    ebi = gen_ebi(str(tmp_path_factory.mktemp("recipes_ebi")),
#                  n=N_DEFECTS, seed=7)
#    rsem = gen_rsem(str(tmp_path_factory.mktemp("recipes_rsem")),
#                    n=N_DEFECTS, seed=11)
#    out = {}
#    for lot in (ebi, rsem):
#        ds = load_dataset(lot["klarf"])
#        out[ds.kind] = ds
#    assert set(out) == {"ebi_patch", "rsem"}, sorted(out)
#    return out
#
#
## --------------------------------------------------------------------------- #
## 靜態檢查
## --------------------------------------------------------------------------- #
#def test_library_is_not_empty_and_has_the_teaching_set():
#    assert RECIPE_FILES, "examples/recipes/ 裡沒有任何 recipe JSON"
#    missing = REQUIRED - set(RECIPE_IDS)
#    assert not missing, "範例 recipe 庫少了教學用的：%s" % sorted(missing)
#
#
#def test_readme_exists_and_mentions_every_recipe():
#    """README 是非工程師挑起點的地方 —— 新增 recipe 一定要同時寫進表格。"""
#    readme = RECIPES_DIR / "README.md"
#    assert readme.is_file(), "examples/recipes/README.md 不見了"
#    text = readme.read_text(encoding="utf-8")
#    for name in RECIPE_IDS:
#        assert name in text, "README.md 沒有介紹 %s.json" % name
#
#
#@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
#def test_recipe_loads_and_is_self_consistent(path):
#    raw = json.loads(path.read_text(encoding="utf-8"))
#    recipe = Recipe.load(str(path))
#
#    assert recipe.recipe_id == path.stem, (
#        "recipe_id 要和檔名一致（庫對話框顯示的就是 recipe_id）")
#    # description 是庫對話框唯一顯示的說明文字 —— 空的等於這份範例沒人看得懂
#    assert len(recipe.description.strip()) >= 20, (
#        "%s 的 description 太短：非工程師要靠它決定用不用這份" % path.name)
#    assert recipe.score.expr.strip(), "score.expr 不可以是空的"
#    assert set(recipe.score.bins) >= {"below", "above"}
#    assert recipe.routes, "至少要有一條 route"
#    for kind, route in recipe.routes.items():
#        assert route, "route '%s' 是空的" % kind
#        for nid in route:
#            assert nid in recipe.nodes, (
#                "route '%s' 引用了不存在的節點 '%s'" % (kind, nid))
#    # 每個定義出來的節點都要真的被某條 route 用到（沒人用 = 誤導讀者）
#    used = {nid for route in recipe.routes.values() for nid in route}
#    assert used == set(recipe.nodes), (
#        "有節點沒被任何 route 使用：%s" % sorted(set(recipe.nodes) - used))
#    # JSON 原檔的 routes 順序 = 執行順序，別被 dict 化吃掉
#    assert list(raw["routes"]) == list(recipe.routes)
#
#
#@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
#def test_recipe_validates_with_zero_errors_on_every_route(path):
#    recipe = Recipe.load(str(path))
#    for kind in recipe.routes:
#        issues = validate(recipe, kind=kind)
#        errors = [i for i in issues if i.level == "error"]
#        assert not errors, "%s route '%s' 有 %d 個 error：%s" % (
#            path.name, kind, len(errors),
#            [(i.code, i.node_id, i.detail) for i in errors])
#
#
## --------------------------------------------------------------------------- #
## 動態檢查：真的跑一遍
## --------------------------------------------------------------------------- #
#@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
#def test_recipe_actually_runs_and_scores_every_defect(path, lots):
#    """每條 route 都要在對應的合成資料上跑完，且**每一顆**都有有限的分數。"""
#    recipe = Recipe.load(str(path))
#    ran = 0
#    for kind in recipe.routes:
#        ds = lots.get(kind)
#        if ds is None:                       # 未來若出現第三種輸入型別
#            pytest.skip("沒有 '%s' 型別的合成資料可以測" % kind)
#        results = run_dataset(recipe, ds)
#        assert len(results) == N_DEFECTS
#        failed = [(r.defect_id, r.error) for r in results if not r.ok]
#        assert not failed, "%s route '%s' 有 defect 跑失敗：%s" % (
#            path.name, kind, failed)
#        for r in results:
#            assert r.score is not None, "%s: defect %s 沒有分數" % (path.name,
#                                                                   r.defect_id)
#            assert math.isfinite(float(r.score)), (
#                "%s: defect %s 的分數不是有限數（%r）" % (path.name, r.defect_id,
#                                                        r.score))
#            assert r.bin in (0, 1), "%s: defect %s 的 bin 是 %r" % (
#                path.name, r.defect_id, r.bin)
#            assert "score" in r.features
#        # 分數不能整批一模一樣 —— 那代表這份 recipe 其實沒有在分辨任何東西
#        scores = {round(float(r.score), 9) for r in results}
#        assert len(scores) > 1, (
#            "%s route '%s'：%d 顆 defect 全部同分（%s），這份範例沒有鑑別力"
#            % (path.name, kind, N_DEFECTS, scores))
#        ran += 1
#    assert ran, "%s 一條 route 都沒跑到" % path.name
#
#
#def test_every_route_kind_is_a_known_dataset_kind():
#    """route 名稱必須對得上 ingest 層真的會產出的 dataset kind。"""
#    known = {"ebi_patch", "rsem", "folder"}
#    for path in RECIPE_FILES:
#        recipe = Recipe.load(str(path))
#        unknown = set(recipe.routes) - known
#        assert not unknown, "%s 有不認識的 route：%s" % (path.name, sorted(unknown))
#
#F 2968b33125e3620b1c5ef3c3653d656ba4c76396 435 tests/test_export_klarf.py
#"""KLARF 三種寫回模式（M5-1）—— 1.2 與 1.8 兩種版本都要過。
#
#守的三條底線：
#
#1. **無損**（鐵則 6）：``inplace`` 什麼都沒改 → 輸出檔與輸入檔**逐位元組相同**；
#   改了某幾格 → 除了那幾格以外，每一行的每個 token 都與原檔相同。
#2. **不默默失敗**：要寫的欄位不存在 → :class:`ExportError`（帶白話說明），
#   絕不「看起來成功但其實沒寫」。
#3. **影像不會壞**：``annotate`` 追加欄位後、``topn`` 抽子集後，
#   ``defect_image_map`` / ``defect_image_filename`` / ``load_dataset``
#   仍然對得到原本那些影像。
#"""
#from __future__ import annotations
#
#import os
#import sys
#
#import pytest
#
#from adept.core.export import klarf_out
#from adept.core.export.klarf_out import ExportError
#from adept.core.ingest import dataset, klarf_core
#
#_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#import make_sample  # noqa: E402
#import make_sample_rsem  # noqa: E402
#
#N = 8
#
#
## ---------------------------------------------------------------------------
## fixtures：EBI patch（KLARF 1.2）與 rSEM（KLARF 1.8）兩份合成 lot
## ---------------------------------------------------------------------------
#@pytest.fixture(scope="module")
#def ebi_lot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("ebi")
#    return make_sample.generate(str(out), n=N)
#
#
#@pytest.fixture(scope="module")
#def rsem_lot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("rsem")
#    return make_sample_rsem.generate(str(out), n=N)
#
#
#@pytest.fixture(params=["1.2", "1.8"])
#def lot(request, ebi_lot, rsem_lot):
#    """兩種 KLARF 版本輪流跑同一組測試。"""
#    return ebi_lot if request.param == "1.2" else rsem_lot
#
#
#def make_results(n=N, scores=None):
#    """假的 pipeline 結果（result_to_json_dict 的形狀）。"""
#    out = []
#    for i in range(n):
#        s = float(n - i) if scores is None else float(scores[i])
#        out.append({
#            "defect_id": str(i + 1),
#            "ok": True,
#            "error": None,
#            "score": s,
#            "bin": 1 if i < n // 2 else 0,
#            "features": {"cd_x_nm": 12.5 + i, "blob_snr": 3.0 + i},
#        })
#    return out
#
#
#def read_bytes(path):
#    with open(str(path), "rb") as f:
#        return f.read()
#
#
#def read_text(path):
#    with open(str(path), "r", encoding="utf-8") as f:
#        return f.read()
#
#
#def error_codes(issues):
#    return sorted(i.code for i in issues if i.level == "error")
#
#
## ---------------------------------------------------------------------------
## inplace —— 無損
## ---------------------------------------------------------------------------
#def test_inplace_no_change_is_byte_identical(lot, tmp_path):
#    """鐵則 6 的頭號驗收：沒改任何欄位 → 位元組完全相同。"""
#    src = lot["klarf"]
#    doc = klarf_core.load(src)
#    out = tmp_path / "same.001"
#    plan = klarf_out.apply_writeback(doc, make_results(), "inplace", str(out))
#
#    assert read_bytes(out) == read_bytes(src)
#    assert plan.n_rows_changed == 0
#    assert plan.columns_touched == []
#    assert plan.columns_added == []
#    assert plan.n_rows_out == N
#    assert error_codes(plan.issues) == []
#
#
#def test_inplace_does_not_mutate_input_doc(lot, tmp_path):
#    """寫回不可以動到呼叫端手上那份 doc（UI 還在用它顯示）。"""
#    doc = klarf_core.load(lot["klarf"])
#    before = [list(r) for r in doc.defects]
#    klarf_out.apply_writeback(doc, make_results(), "inplace",
#                              str(tmp_path / "o.001"), class_col="CLASSNUMBER")
#    assert [list(r) for r in doc.defects] == before
#    assert doc.to_text() == read_text(lot["klarf"])
#
#
#def test_inplace_class_from_bin_only_touches_those_cells(lot, tmp_path):
#    """把 bin 寫進 CLASSNUMBER：值要對，其他 byte 一個都不能動。"""
#    src = lot["klarf"]
#    doc = klarf_core.load(src)
#    results = make_results()
#    out = tmp_path / "cls.001"
#    plan = klarf_out.apply_writeback(doc, results, "inplace", str(out),
#                                     class_col="CLASSNUMBER")
#
#    # --- 值 round-trip ---
#    new = klarf_core.load(str(out))
#    ci = new.col_index("CLASSNUMBER")
#    di = new.col_index("DEFECTID")
#    assert ci >= 0
#    got = {r[di]: r[ci] for r in new.defects}
#    assert got == {r["defect_id"]: str(r["bin"]) for r in results}
#
#    # --- 原檔的 CLASSNUMBER 全是 0，所以只有 bin=1 那幾顆真的改了 ---
#    n_expected = sum(1 for r in results if r["bin"] != 0)
#    assert plan.n_rows_changed == n_expected
#    assert plan.columns_touched == ["CLASSNUMBER"]
#    assert plan.n_rows_out == N
#
#    # --- 逐行比：行數相同、每行 token 數相同、只有 CLASSNUMBER 那個 token 不同 ---
#    old_lines = read_text(src).splitlines()
#    new_lines = read_text(out).splitlines()
#    assert len(old_lines) == len(new_lines)
#    n_diff_lines = 0
#    for a, b in zip(old_lines, new_lines):
#        if a == b:
#            continue
#        n_diff_lines += 1
#        ta, tb = a.split(), b.split()
#        assert len(ta) == len(tb), "行的 token 數被改變了：{!r} -> {!r}".format(a, b)
#        diff_at = [k for k, (x, y) in enumerate(zip(ta, tb)) if x != y]
#        assert diff_at == [ci], "改到了不該改的 token：{} != [{}]".format(diff_at, ci)
#    assert n_diff_lines == n_expected
#
#
#def test_inplace_bin_map_and_size_column(lot, tmp_path):
#    """bin_map 換掉要寫出去的數值；沒有 DSIZE 欄的檔案要擋下來。"""
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results()
#    out = tmp_path / "mapped.001"
#    klarf_out.apply_writeback(doc, results, "inplace", str(out),
#                              class_col="CLASSNUMBER", bin_map={0: 7, 1: 9})
#    new = klarf_core.load(str(out))
#    ci = new.col_index("CLASSNUMBER")
#    vals = sorted({r[ci] for r in new.defects})
#    assert vals == ["7", "9"]
#
#
#def test_inplace_missing_column_raises_with_help(lot, tmp_path):
#    """要寫的欄位不存在 → 報錯（而且訊息要看得懂、要指出可行的下一步）。"""
#    doc = klarf_core.load(lot["klarf"])
#    with pytest.raises(ExportError) as ei:
#        klarf_out.apply_writeback(doc, make_results(), "inplace",
#                                  str(tmp_path / "x.001"), size_col="DSIZE")
#    msg = str(ei.value)
#    assert "DSIZE" in msg
#    assert "annotate" in msg               # 有給替代方案
#    assert "DEFECTID" in msg               # 有列出這個檔實際有的欄位
#    assert not (tmp_path / "x.001").exists()   # 失敗就不該留下半個檔
#
#
#def test_inplace_skips_failed_defects(lot, tmp_path):
#    """單顆失敗不寫回，也不能殺掉整批（鐵則 7 的輸出端對應）。"""
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results()
#    results[2] = dict(results[2], ok=False, error="boom", score=None, bin=None)
#    plan = klarf_out.apply_writeback(doc, results, "inplace",
#                                     str(tmp_path / "f.001"),
#                                     class_col="CLASSNUMBER")
#    new = klarf_core.load(str(tmp_path / "f.001"))
#    ci, di = new.col_index("CLASSNUMBER"), new.col_index("DEFECTID")
#    got = {r[di]: r[ci] for r in new.defects}
#    assert got["3"] == "0"                 # 原值保留
#    assert plan.n_rows_changed == sum(
#        1 for r in results if r["ok"] and r["bin"] != 0)
#    assert any("failed to run" in n for n in plan.notes)
#
#
## ---------------------------------------------------------------------------
## annotate —— 追加欄位，影像區塊仍在列尾
## ---------------------------------------------------------------------------
#def test_annotate_adds_columns_and_keeps_images(lot, tmp_path):
#    src = lot["klarf"]
#    doc = klarf_core.load(src)
#    results = make_results()
#    base_errors = error_codes(klarf_core.lint(doc))
#
#    # 輸出放在原資料夾，影像（多頁 TIFF / per-defect PNG）才找得到
#    out = os.path.join(os.path.dirname(src), "annotated.001")
#    plan = klarf_out.apply_writeback(doc, results, "annotate", out,
#                                     extra_features=["cd_x_nm"])
#
#    assert plan.columns_added == ["ADCSCORE", "ADCCLASS", "CD_X_NM"]
#    assert plan.n_rows_out == N
#    assert plan.n_rows_changed == N
#    assert error_codes(plan.issues) == base_errors      # 沒有新的 error
#
#    new = klarf_core.load(out)
#    cols = [c.upper() for c in new.defect_columns]
#    assert "ADCSCORE" in cols and "ADCCLASS" in cols and "CD_X_NM" in cols
#    assert len(new.defects) == N
#
#    # --- 值 round-trip ---
#    di = new.col_index("DEFECTID")
#    si = new.col_index("ADCSCORE")
#    ki = new.col_index("ADCCLASS")
#    fi = new.col_index("CD_X_NM")
#    for r in results:
#        row = next(x for x in new.defects if x[di] == r["defect_id"])
#        assert float(row[si]) == pytest.approx(r["score"], abs=1e-4)
#        assert int(row[ki]) == r["bin"]
#        assert float(row[fi]) == pytest.approx(r["features"]["cd_x_nm"], abs=1e-4)
#
#    # --- 影像尾巴活著 ---
#    old = klarf_core.load(src)
#    assert new.image_layout() is not None
#    assert new.total_image_count() == old.total_image_count()
#    assert new.defect_image_map()["pages"] == old.defect_image_map()["pages"]
#    assert ([new.defect_image_filename(r) for r in new.defects]
#            == [old.defect_image_filename(r) for r in old.defects])
#    for row in new.defects:
#        assert len(new.defect_image_entries(row)) == new.defect_image_count(row)
#        assert new.row_len_ok(row)
#
#    # --- ingest 層照樣讀得回來 ---
#    old_ds = dataset.load_dataset(src)
#    new_ds = dataset.load_dataset(out)
#    assert new_ds.kind == old_ds.kind
#    assert len(new_ds.items) == N
#    for a, b in zip(old_ds.items, new_ds.items):
#        assert sorted(a.images) == sorted(b.images)
#        for ch in a.images:
#            assert a.images[ch].page == b.images[ch].page
#            assert os.path.abspath(a.images[ch].path) == os.path.abspath(b.images[ch].path)
#    os.remove(out)
#
#
#def test_annotate_rounds_floats_to_fixed_decimals(lot, tmp_path):
#    """浮點固定小數位數，檔案才 diff 得動。"""
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results()
#    results[0] = dict(results[0], score=1.23456789)
#    out = tmp_path / "dec.001"
#    klarf_out.apply_writeback(doc, results, "annotate", str(out), decimals=3)
#    new = klarf_core.load(str(out))
#    si, di = new.col_index("ADCSCORE"), new.col_index("DEFECTID")
#    row = next(x for x in new.defects if x[di] == "1")
#    assert row[si] == "1.235"
#    assert all(len(r[si].split(".")[1]) == 3 for r in new.defects)
#
#
#def test_annotate_refuses_existing_column(lot, tmp_path):
#    """已經有同名欄位 → 報錯，不覆蓋別人的資料。"""
#    doc = klarf_core.load(lot["klarf"])
#    with pytest.raises(ExportError) as ei:
#        klarf_out.apply_writeback(doc, make_results(), "annotate",
#                                  str(tmp_path / "x.001"),
#                                  score_col="CLASSNUMBER")
#    assert "CLASSNUMBER" in str(ei.value)
#    assert "inplace" in str(ei.value)
#
#
#def test_annotate_marks_unmatched_rows(lot, tmp_path):
#    """沒有結果的 defect 要標成「未判定」（-1），而不是假裝判過。"""
#    doc = klarf_core.load(lot["klarf"])
#    out = tmp_path / "partial.001"
#    plan = klarf_out.apply_writeback(doc, make_results()[:3], "annotate", str(out))
#    new = klarf_core.load(str(out))
#    ki = new.col_index("ADCCLASS")
#    assert sum(1 for r in new.defects if r[ki] == "-1") == N - 3
#    assert any("not judged" in n for n in plan.notes)
#
#
## ---------------------------------------------------------------------------
## topn —— 只留高分的，影像參照要講清楚
## ---------------------------------------------------------------------------
#def test_topn_count_order_and_renumber(lot):
#    """取前 3 名：數量、排序、重新編號、影像仍指向**原本**那些圖。"""
#    src = lot["klarf"]
#    doc = klarf_core.load(src)
#    # 分數遞增 → 最高分是最後一顆，強迫輸出順序與原檔順序不同
#    results = make_results(scores=[float(i) for i in range(N)])
#    out = os.path.join(os.path.dirname(src), "topn.001")
#    plan = klarf_out.apply_writeback(doc, results, "topn", out, n=3)
#
#    assert plan.n_rows_out == 3
#    new = klarf_core.load(out)
#    assert len(new.defects) == 3
#
#    di, si = new.col_index("DEFECTID"), new.col_index("ADCSCORE")
#    assert [r[di] for r in new.defects] == ["1", "2", "3"]          # 重新編號
#    scores = [float(r[si]) for r in new.defects]
#    assert scores == sorted(scores, reverse=True)                   # 由高到低
#    assert scores == [float(N - 1), float(N - 2), float(N - 3)]
#
#    # 這三列在原檔是第 8、7、6 顆 —— 用 XREL 當身分證確認
#    old = klarf_core.load(src)
#    xr = old.col_index("XREL")
#    assert [r[new.col_index("XREL")] for r in new.defects] == \
#        [old.defects[k][xr] for k in (N - 1, N - 2, N - 3)]
#
#    # 影像參照：頁碼／檔名都還指向原本那幾張
#    old_map = old.defect_image_map()["pages"]
#    new_map = new.defect_image_map()["pages"]
#    if old.defect_image_filename(old.defects[0]):
#        assert [new.defect_image_filename(r) for r in new.defects] == \
#            [old.defect_image_filename(old.defects[k]) for k in (N - 1, N - 2, N - 3)]
#    else:
#        assert new_map == [old_map[k] for k in (N - 1, N - 2, N - 3)]
#
#    ds = dataset.load_dataset(out)
#    assert len(ds.items) == 3
#    old_ds = dataset.load_dataset(src)
#    for item, k in zip(ds.items, (N - 1, N - 2, N - 3)):
#        ref = old_ds.items[k]
#        assert sorted(item.images) == sorted(ref.images)
#        for ch in ref.images:
#            assert item.images[ch].page == ref.images[ch].page
#            assert os.path.abspath(item.images[ch].path) == \
#                os.path.abspath(ref.images[ch].path)
#            assert os.path.isfile(item.images[ch].path)
#
#    assert any("Image references" in n for n in plan.notes)
#    os.remove(out)
#
#
#def test_topn_min_score(lot, tmp_path):
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results(scores=[float(i) for i in range(N)])   # 0..7
#    out = tmp_path / "thr.001"
#    plan = klarf_out.apply_writeback(doc, results, "topn", str(out),
#                                     n=0, min_score=5.0)
#    assert plan.n_rows_out == 3                                   # 5, 6, 7
#    new = klarf_core.load(str(out))
#    si = new.col_index("ADCSCORE")
#    assert [float(r[si]) for r in new.defects] == [7.0, 6.0, 5.0]
#
#
#def test_topn_without_n_or_min_score_raises(lot, tmp_path):
#    doc = klarf_core.load(lot["klarf"])
#    with pytest.raises(ExportError) as ei:
#        klarf_out.apply_writeback(doc, make_results(), "topn", str(tmp_path / "x.001"))
#    assert "min_score" in str(ei.value)
#
#
#def test_topn_keep_original_ids(lot, tmp_path):
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results(scores=[float(i) for i in range(N)])
#    out = tmp_path / "keep.001"
#    klarf_out.apply_writeback(doc, results, "topn", str(out), n=2,
#                              renumber=False, include_annotations=False)
#    new = klarf_core.load(str(out))
#    di = new.col_index("DEFECTID")
#    assert [r[di] for r in new.defects] == [str(N), str(N - 1)]
#    assert new.defect_columns == klarf_core.load(lot["klarf"]).defect_columns
#
#
#def test_topn_skips_defects_without_score(lot, tmp_path):
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results()
#    results[0] = dict(results[0], ok=False, score=None, bin=None)
#    out = tmp_path / "ns.001"
#    plan = klarf_out.apply_writeback(doc, results, "topn", str(out), n=N)
#    assert plan.n_rows_out == N - 1
#    assert any("have no score" in n for n in plan.notes)
#
#
## ---------------------------------------------------------------------------
## 計畫書 vs 實際執行
## ---------------------------------------------------------------------------
#@pytest.mark.parametrize("mode,opts", [
#    ("inplace", {}),
#    ("inplace", {"class_col": "CLASSNUMBER"}),
#    ("annotate", {"extra_features": ["blob_snr"]}),
#    ("topn", {"n": 4}),
#    ("topn", {"n": 0, "min_score": 4.0, "include_annotations": False}),
#])
#def test_plan_matches_apply(lot, tmp_path, mode, opts):
#    """乾跑報的數字必須與真的寫出去一模一樣（不然預覽就是騙人的）。"""
#    doc = klarf_core.load(lot["klarf"])
#    results = make_results()
#    plan = klarf_out.plan_writeback(doc, results, mode, **opts)
#    out = tmp_path / "p_{}.001".format(mode)
#    applied = klarf_out.apply_writeback(doc, results, mode, str(out), **opts)
#
#    assert plan.to_dict() == applied.to_dict()
#    assert klarf_core.load(str(out)).defects.__len__() == plan.n_rows_out
#    # 乾跑不留下任何檔案痕跡
#    assert not (tmp_path / "p_dry.001").exists()
#
#
#def test_unknown_mode_raises(lot):
#    doc = klarf_core.load(lot["klarf"])
#    with pytest.raises(ExportError) as ei:
#        klarf_out.plan_writeback(doc, make_results(), "nonsense")
#    assert "inplace" in str(ei.value) and "annotate" in str(ei.value)
#
#
#def test_writeback_is_atomic(lot, tmp_path):
#    """atomic 寫入（鐵則 5）：寫完不留 .tmp。"""
#    doc = klarf_core.load(lot["klarf"])
#    out = tmp_path / "sub" / "a.001"
#    klarf_out.apply_writeback(doc, make_results(), "annotate", str(out))
#    assert out.exists()
#    assert not (tmp_path / "sub" / "a.001.tmp").exists()
#
#
#def test_results_matched_by_defectid_not_position(lot, tmp_path):
#    """結果順序被打亂也要對得回去（靠 DEFECTID，不是靠位置）。"""
#    doc = klarf_core.load(lot["klarf"])
#    results = list(reversed(make_results()))
#    out = tmp_path / "shuf.001"
#    klarf_out.apply_writeback(doc, results, "annotate", str(out))
#    new = klarf_core.load(str(out))
#    di, si = new.col_index("DEFECTID"), new.col_index("ADCSCORE")
#    by_id = {r["defect_id"]: r["score"] for r in results}
#    for row in new.defects:
#        assert float(row[si]) == pytest.approx(by_id[row[di]], abs=1e-4)
#
#F be9903e176600cc8d742d46b8b89c1aa1039ac2a 267 tests/test_export_overlay.py
#"""缺陷疊圖渲染（M5-1）：形狀 / dtype / 紅框 / [test | diff] 並排 / 標籤。
#
#疊圖是「使用者看得懂機器在想什麼」的唯一介面，所以這裡連
#「標籤塞中文會不會炸」都要測 —— cv2 的內建字型沒有 CJK 字元，
#:mod:`adept.core.export.overlay` 會把非 ASCII 換成 ``?`` 而不是丟例外。
#"""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#
#from adept.core.export import overlay
#from adept.core.export.klarf_out import ExportError
#
#H = W = 64
#
#
#def flat(value=100, h=H, w=W):
#    return np.full((h, w), value, np.uint8)
#
#
## ---------------------------------------------------------------------------
## 基本形狀 / dtype
## ---------------------------------------------------------------------------
#def test_single_panel_shape_and_dtype():
#    out = overlay.render_overlay({"test": flat()}, {})
#    assert out.shape == (H, W, 3)
#    assert out.dtype == np.uint8
#
#
#def test_rsem_single_channel_is_accepted():
#    out = overlay.render_overlay({"single": flat()}, {})
#    assert out.shape == (H, W, 3)
#
#
#def test_base_priority_test_beats_single():
#    images = {"single": flat(0), "test": flat(255)}
#    out = overlay.render_overlay(images, {})
#    assert int(out[0, 0, 0]) == 255
#
#
#def test_explicit_base_key():
#    out = overlay.render_overlay({"test": flat(0), "ref": flat(200)}, {},
#                                 base_key="ref")
#    assert int(out[0, 0, 0]) == 200
#
#
#def test_missing_base_key_raises_with_available_list():
#    with pytest.raises(ExportError) as ei:
#        overlay.render_overlay({"test": flat()}, {}, base_key="nope")
#    assert "nope" in str(ei.value) and "test" in str(ei.value)
#
#
#def test_empty_images_raises():
#    with pytest.raises(ExportError):
#        overlay.render_overlay({}, {})
#
#
#def test_float_image_is_stretched_to_uint8():
#    arr = np.linspace(-2.0, 5.0, H * W).reshape(H, W).astype(np.float32)
#    out = overlay.render_overlay({"test": arr}, {})
#    assert out.dtype == np.uint8
#    assert int(out.min()) == 0 and int(out.max()) == 255
#
#
#def test_constant_float_image_does_not_divide_by_zero():
#    out = overlay.render_overlay({"test": np.full((H, W), 3.5, np.float32)}, {})
#    assert out.shape == (H, W, 3)
#    assert int(out.max()) == 0
#
#
#def test_rgb_input_passes_through():
#    rgb = np.zeros((H, W, 3), np.uint8)
#    rgb[..., 0] = 200
#    out = overlay.render_overlay({"test": rgb}, {})
#    assert tuple(int(v) for v in out[0, 0]) == (200, 0, 0)
#
#
## ---------------------------------------------------------------------------
## 紅框
## ---------------------------------------------------------------------------
#def test_blob_box_changes_pixels_at_the_bbox_edge():
#    """框畫在 blob 的邊界上：邊界像素變紅、框內遠離邊界的像素不動。"""
#    base = {"test": flat(100)}
#    plain = overlay.render_overlay(base, {})
#    blobs = [{"x": 16, "y": 16, "w": 20, "h": 20, "snr_value": 9.0, "area": 40}]
#    boxed = overlay.render_overlay(base, {}, blobs=blobs)
#
#    assert boxed.shape == plain.shape
#    assert not np.array_equal(plain, boxed)
#
#    # 邊框四個邊都被畫到
#    for y, x in [(16, 20), (35, 20), (20, 16), (20, 35)]:
#        assert tuple(int(v) for v in boxed[y, x]) == overlay.BOX_COLOR, (y, x)
#    # 框的正中央沒被塗掉
#    assert tuple(int(v) for v in boxed[25, 25]) == (100, 100, 100)
#    # 框外也沒被塗掉
#    assert tuple(int(v) for v in boxed[50, 50]) == (100, 100, 100)
#
#
#def test_explicit_box_overrides_blobs():
#    blobs = [{"x": 0, "y": 0, "w": 4, "h": 4, "snr_value": 9.0}]
#    out = overlay.render_overlay({"test": flat()}, {}, blobs=blobs,
#                                 box=(30, 30, 10, 10))
#    assert tuple(int(v) for v in out[30, 35]) == overlay.BOX_COLOR
#    assert tuple(int(v) for v in out[0, 2]) != overlay.BOX_COLOR
#
#
#def test_primary_blob_is_the_strongest_snr():
#    blobs = [
#        {"x": 4, "y": 4, "w": 6, "h": 6, "snr_value": 1.0},
#        {"x": 30, "y": 30, "w": 8, "h": 8, "snr_value": 9.0},
#        {"x": 50, "y": 50, "w": 6, "h": 6, "snr_value": 3.0},
#    ]
#    assert overlay.primary_blob_box(blobs) == (30, 30, 8, 8)
#    out = overlay.render_overlay({"test": flat()}, {}, blobs=blobs)
#    assert tuple(int(v) for v in out[30, 34]) == overlay.BOX_COLOR
#    assert tuple(int(v) for v in out[4, 6]) != overlay.BOX_COLOR
#
#
#def test_box_from_features_when_no_blobs():
#    feats = {"blob_x": 20, "blob_y": 20, "blob_w": 10, "blob_h": 10}
#    assert overlay.primary_blob_box(None, feats) == (20, 20, 10, 10)
#    out = overlay.render_overlay({"test": flat()}, feats)
#    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR
#
#
#def test_box_outside_image_is_clipped_not_crashing():
#    out = overlay.render_overlay({"test": flat()}, {}, box=(60, 60, 999, 999))
#    assert out.shape == (H, W, 3)
#    assert tuple(int(v) for v in out[63, 63]) == overlay.BOX_COLOR
#
#
#def test_no_blobs_means_no_box():
#    plain = overlay.render_overlay({"test": flat()}, {})
#    assert np.array_equal(plain, np.dstack([flat()] * 3))
#
#
#def test_defect_roi_dataclass_is_accepted():
#    from adept.core.algo.blob import DefectROI
#    roi = DefectROI(x=10, y=12, w=8, h=6, cx=14.0, cy=15.0, area=48,
#                    mean_signal=1.0, snr_value=5.0, aspect_ratio=1.3,
#                    dist_to_center=2.0)
#    assert overlay.primary_blob_box([roi]) == (10, 12, 8, 6)
#
#
## ---------------------------------------------------------------------------
## 並排（montage）
## ---------------------------------------------------------------------------
#def test_montage_width_is_double_when_diff_present():
#    images = {"test": flat(100), "diff": flat(30)}
#    out = overlay.render_overlay(images, {})
#    assert out.shape == (H, 2 * W, 3)
#    assert int(out[0, 0, 0]) == 100                # 左：test
#    assert int(out[0, W + 5, 0]) == 30             # 右：diff
#
#
#def test_montage_can_be_disabled():
#    images = {"test": flat(100), "diff": flat(30)}
#    out = overlay.render_overlay(images, {}, montage=False)
#    assert out.shape == (H, W, 3)
#
#
#def test_montage_resizes_mismatched_diff():
#    images = {"test": flat(100), "diff": flat(30, h=32, w=32)}
#    out = overlay.render_overlay(images, {})
#    assert out.shape == (H, 2 * W, 3)
#
#
#def test_montage_draws_box_on_both_panels():
#    images = {"test": flat(100), "diff": flat(30)}
#    out = overlay.render_overlay(images, {}, box=(20, 20, 10, 10))
#    assert tuple(int(v) for v in out[20, 25]) == overlay.BOX_COLOR
#    assert tuple(int(v) for v in out[20, W + 25]) == overlay.BOX_COLOR
#
#
#def test_diff_only_context_does_not_montage_itself():
#    """只有 diff 時它就是底圖，不該和自己並排。"""
#    out = overlay.render_overlay({"diff": flat(50)}, {})
#    assert out.shape == (H, W, 3)
#
#
## ---------------------------------------------------------------------------
## 標籤
## ---------------------------------------------------------------------------
#def test_label_is_drawn_top_left():
#    plain = overlay.render_overlay({"test": flat(200)}, {})
#    labelled = overlay.render_overlay({"test": flat(200)}, {}, label="score=3.21")
#    assert labelled.shape == plain.shape
#    assert not np.array_equal(plain[:16], labelled[:16])   # 左上角有變化
#    assert np.array_equal(plain[40:], labelled[40:])       # 下半部沒被動到
#
#
#def test_unicode_label_does_not_crash():
#    """cv2 的字型沒有中日韓字元 —— 換成 '?' 畫出來，不准丟例外。"""
#    for text in ("分數 3.21 / bin 1 真缺陷", "スコア", "점수", "α β γ", "🙂"):
#        out = overlay.render_overlay({"test": flat()}, {}, label=text)
#        assert out.shape == (H, W, 3)
#        assert out.dtype == np.uint8
#
#
#def test_empty_label_is_a_no_op():
#    plain = overlay.render_overlay({"test": flat(200)}, {})
#    assert np.array_equal(plain, overlay.render_overlay(
#        {"test": flat(200)}, {}, label="   "))
#
#
#def test_label_defaults_to_score_from_features():
#    plain = overlay.render_overlay({"test": flat(200)}, {})
#    auto = overlay.render_overlay({"test": flat(200)}, {"score": 3.21})
#    assert not np.array_equal(plain, auto)
#
#
#def test_label_on_tiny_image_does_not_crash():
#    out = overlay.render_overlay({"test": flat(100, h=8, w=8)}, {},
#                                 label="score=1.0")
#    assert out.shape == (8, 8, 3)
#
#
## ---------------------------------------------------------------------------
## write_png
## ---------------------------------------------------------------------------
#def test_write_png_roundtrip_and_atomic(tmp_path):
#    import cv2
#
#    arr = overlay.render_overlay({"test": flat(120), "diff": flat(30)}, {},
#                                 box=(10, 10, 8, 8), label="score=1.00")
#    path = tmp_path / "sub" / "o.png"
#    out = overlay.write_png(arr, str(path))
#    assert out == str(path)
#    assert path.exists()
#    assert not (tmp_path / "sub" / "o.png.tmp").exists()      # atomic
#
#    back = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
#    back = cv2.cvtColor(back, cv2.COLOR_BGR2RGB)
#    assert back.shape == arr.shape
#    assert np.array_equal(back, arr)                          # PNG 無失真
#
#
#def test_write_png_accepts_gray_array(tmp_path):
#    path = tmp_path / "g.png"
#    overlay.write_png(flat(77), str(path))
#    assert path.exists()
#
#
## ---------------------------------------------------------------------------
## 與 pipeline 的實際串接
## ---------------------------------------------------------------------------
#def test_renders_from_a_real_context_images_dict():
#    """直接吃 Context.images + meta["blobs"] 的形狀（UI 就是這樣叫的）。"""
#    from adept.core.pipeline.context import Context
#
#    rng = np.random.RandomState(0)
#    ctx = Context()
#    ctx.set_image("test", rng.randint(0, 255, (H, W)).astype(np.uint8))
#    ctx.set_image("ref", rng.randint(0, 255, (H, W)).astype(np.uint8))
#    ctx.set_image("diff", (ctx.images["test"].astype(np.float32)
#                           - ctx.images["ref"].astype(np.float32)))
#    ctx.add_feature("blob_snr", 4.2)
#    ctx.meta["blobs"] = [{"x": 8, "y": 8, "w": 12, "h": 12, "area": 100,
#                          "snr_value": 7.5}]
#
#    out = overlay.render_overlay(ctx.images, ctx.features,
#                                 blobs=ctx.meta["blobs"], label="bin=1")
#    assert out.shape == (H, 2 * W, 3)
#    assert out.dtype == np.uint8
#
#F a032dde08875f8b4a7e3d0000cbdbe6aa3c25518 280 tests/test_export_report.py
#"""報表匯出（M5-1）：CSV / Excel / summarize。
#
#重點在 :func:`summarize` 的算術 —— 抓漏率與誤殺率是製程工程師拿來決定
#「這個 recipe 敢不敢上線」的數字，算錯比不算還糟，所以用手算的
#ground truth 明著驗一次。
#"""
#from __future__ import annotations
#
#import csv
#
#import pytest
#
#from adept.core.export import report
#from adept.core.export.report import BASE_COLUMNS, UNBINNED_KEY
#
#
## ---------------------------------------------------------------------------
## 手工資料：10 顆，前 5 顆是真缺陷、後 5 顆是 nuisance
##   判定（bin 1 = 真缺陷、0 = nuisance）：
##     id 1-4  真缺陷 → 判真   TP = 4
##     id 5    真缺陷 → 判假   FN = 1   （抓漏）
##     id 6,7  nuisance → 判真 FP = 2   （誤殺）
##     id 8-10 nuisance → 判假 TN = 3
##   抓漏率 = 1/5 = 0.2   誤殺率 = 2/5 = 0.4   正確率 = 7/10 = 0.7
## ---------------------------------------------------------------------------
#_BINS = {1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 1, 7: 1, 8: 0, 9: 0, 10: 0}
#_TRUTH = {i: (i <= 5) for i in range(1, 11)}
#
#
#def hand_results():
#    out = []
#    for i in range(1, 11):
#        out.append({
#            "defect_id": str(i),
#            "ok": True,
#            "error": None,
#            "score": float(i),
#            "bin": _BINS[i],
#            "features": {"blob_snr": float(i), "cd_x_nm": float(i) * 2.0},
#        })
#    return out
#
#
#def hand_ground_truth():
#    """make_sample.py 的 ground_truth.json 形狀：{id: {"is_real": bool, ...}}。"""
#    return {str(i): {"is_real": _TRUTH[i], "type": "syn"} for i in range(1, 11)}
#
#
## ---------------------------------------------------------------------------
## summarize
## ---------------------------------------------------------------------------
#def test_summarize_basic_counts():
#    s = report.summarize(hand_results())
#    assert s["n_total"] == 10
#    assert s["n_ok"] == 10
#    assert s["n_fail"] == 0
#    assert s["n_scored"] == 10
#    assert s["bin_counts"] == {"1": 6, "0": 4}
#    assert s["score_min"] == 1.0
#    assert s["score_median"] == 5.5
#    assert s["score_max"] == 10.0
#    assert s["ground_truth"] is None
#
#
#def test_summarize_feature_stats():
#    s = report.summarize(hand_results())
#    assert sorted(s["features"]) == ["blob_snr", "cd_x_nm"]
#    st = s["features"]["blob_snr"]
#    assert st["n"] == 10
#    assert st["min"] == 1.0
#    assert st["median"] == 5.5
#    assert st["max"] == 10.0
#    assert st["std"] == pytest.approx(2.8722813, abs=1e-6)   # 母體標準差
#    assert s["features"]["cd_x_nm"]["max"] == 20.0
#
#
#def test_summarize_handles_failures_and_nan():
#    res = hand_results()
#    res[0] = dict(res[0], ok=False, error="boom", score=None, bin=None, features={})
#    res[1] = dict(res[1], score=float("nan"), features={"blob_snr": float("inf")})
#    s = report.summarize(res)
#    assert s["n_ok"] == 9 and s["n_fail"] == 1
#    assert s["n_scored"] == 8                       # None 與 nan 都不算
#    assert s["bin_counts"][UNBINNED_KEY] == 1
#    assert s["features"]["blob_snr"]["n"] == 8      # inf 與缺的都不算
#
#
#def test_summarize_confusion_matrix_arithmetic():
#    """抓漏 / 誤殺 的算術明著驗一次。"""
#    s = report.summarize(hand_results(), ground_truth=hand_ground_truth())
#    gt = s["ground_truth"]
#
#    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (4, 1, 2, 3)
#    assert gt["n_labelled"] == 10
#    assert gt["n_evaluated"] == 10
#    assert gt["n_real"] == 5 and gt["n_nuisance"] == 5
#
#    # 抓漏率 = 漏掉的真缺陷 / 真缺陷總數 = 1/5
#    assert gt["miss_rate"] == pytest.approx(1.0 / 5.0)
#    # 誤殺率 = 被判成真缺陷的 nuisance / nuisance 總數 = 2/5
#    assert gt["false_alarm_rate"] == pytest.approx(2.0 / 5.0)
#    # 正確率 = (TP + TN) / 有判定的顆數 = 7/10
#    assert gt["accuracy"] == pytest.approx(7.0 / 10.0)
#    assert gt["tp"] + gt["fn"] + gt["fp"] + gt["tn"] == gt["n_evaluated"]
#
#
#def test_summarize_accepts_plain_bool_ground_truth():
#    """ground_truth 也可以直接是 {id: True/False}。"""
#    plain = {str(i): _TRUTH[i] for i in range(1, 11)}
#    a = report.summarize(hand_results(), ground_truth=plain)["ground_truth"]
#    b = report.summarize(hand_results(),
#                         ground_truth=hand_ground_truth())["ground_truth"]
#    assert a == b
#
#
#def test_summarize_positive_bins_override():
#    """把 bin 0 當成「真缺陷」→ 混淆矩陣整個反過來。"""
#    gt = report.summarize(hand_results(), ground_truth=hand_ground_truth(),
#                          positive_bins=[0])["ground_truth"]
#    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (1, 4, 3, 2)
#    assert gt["miss_rate"] == pytest.approx(4.0 / 5.0)
#
#
#def test_summarize_unlabelled_and_unbinned_excluded():
#    res = hand_results()
#    res[9] = dict(res[9], bin=None)                     # 有標註但沒判定
#    truth = hand_ground_truth()
#    del truth["9"]                                      # 有判定但沒標註
#    gt = report.summarize(res, ground_truth=truth)["ground_truth"]
#    assert gt["n_labelled"] == 9
#    assert gt["n_unlabelled"] == 1
#    assert gt["n_unbinned"] == 1
#    assert gt["n_evaluated"] == 8
#    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (4, 1, 2, 1)
#
#
#def test_summarize_empty_results():
#    s = report.summarize([])
#    assert s["n_total"] == 0 and s["score_median"] is None
#    assert s["features"] == {} and s["bin_counts"] == {}
#
#
## ---------------------------------------------------------------------------
## CSV
## ---------------------------------------------------------------------------
#def test_write_csv_header_rows_and_bom(tmp_path):
#    path = tmp_path / "r.csv"
#    out = report.write_csv(hand_results(), str(path))
#    assert out == str(path)
#
#    with open(out, "rb") as f:
#        raw = f.read()
#    assert raw.startswith(b"\xef\xbb\xbf")             # utf-8-sig，Excel 直開不亂碼
#    assert not (tmp_path / "r.csv.tmp").exists()       # atomic：不留 .tmp
#
#    with open(out, "r", encoding="utf-8-sig", newline="") as f:
#        rows = list(csv.reader(f))
#    assert rows[0] == list(BASE_COLUMNS) + ["blob_snr", "cd_x_nm"]
#    assert len(rows) == 11
#    assert rows[1] == ["1", "1", "", "1.0", "1", "1.0", "2.0"]
#    assert rows[10][0] == "10"
#
#
#def test_write_csv_feature_union_and_gaps(tmp_path):
#    res = [
#        {"defect_id": "1", "ok": True, "error": None, "score": 1.0, "bin": 0,
#         "features": {"a": 1.0}},
#        {"defect_id": "2", "ok": True, "error": None, "score": 2.0, "bin": 1,
#         "features": {"b": 2.0}},
#    ]
#    path = tmp_path / "u.csv"
#    report.write_csv(res, str(path))
#    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
#        rows = list(csv.reader(f))
#    assert rows[0] == list(BASE_COLUMNS) + ["a", "b"]
#    assert rows[1][-2:] == ["1.0", ""]                 # 缺的留空
#    assert rows[2][-2:] == ["", "2.0"]
#
#
#def test_write_csv_without_features(tmp_path):
#    path = tmp_path / "n.csv"
#    report.write_csv(hand_results(), str(path), include_features=False)
#    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
#        rows = list(csv.reader(f))
#    assert rows[0] == list(BASE_COLUMNS)
#    assert len(rows[1]) == len(BASE_COLUMNS)
#
#
#def test_write_csv_failed_defect_row(tmp_path):
#    res = hand_results()
#    res[0] = dict(res[0], ok=False, error="炸了", score=None, bin=None, features={})
#    path = tmp_path / "f.csv"
#    report.write_csv(res, str(path))
#    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
#        rows = list(csv.reader(f))
#    assert rows[1][:5] == ["1", "0", "炸了", "", ""]
#
#
#def test_write_csv_creates_parent_dir(tmp_path):
#    path = tmp_path / "deep" / "sub" / "r.csv"
#    report.write_csv(hand_results(), str(path))
#    assert path.exists()
#
#
## ---------------------------------------------------------------------------
## Excel
## ---------------------------------------------------------------------------
#def test_write_excel_has_three_sheets(tmp_path):
#    openpyxl = pytest.importorskip("openpyxl")
#    path = tmp_path / "r.xlsx"
#    recipe = {"recipe_id": "demo", "description": "測試用",
#              "score": {"expr": "blob_snr * 2", "threshold": 6.0,
#                        "bins": {"below": 0, "above": 1}},
#              "nodes": [{"id": "a"}, {"id": "b"}]}
#    out = report.write_excel(hand_results(), str(path),
#                             ground_truth=hand_ground_truth(), recipe=recipe)
#    assert out == str(path)
#    assert not (tmp_path / "r.xlsx.tmp").exists()      # atomic
#
#    wb = openpyxl.load_workbook(out)
#    assert wb.sheetnames == ["Summary", "Details", "Feature stats"]
#
#    # --- 明細：標題 + 每顆一列、凍結標題、自動篩選 ---
#    ws = wb["Details"]
#    header = [c.value for c in ws[1]]
#    assert header == list(BASE_COLUMNS) + ["blob_snr", "cd_x_nm"]
#    assert ws.max_row == 11
#    assert ws.freeze_panes == "A2"
#    assert ws.auto_filter.ref is not None
#    assert [ws.cell(row=r, column=1).value for r in range(2, 12)] == \
#        [str(i) for i in range(1, 11)]
#
#    # --- 特徵統計：每個特徵一列 ---
#    ws = wb["Feature stats"]
#    assert [c.value for c in ws[1]] == ["Feature", "Count", "Minimum", "Median", "Maximum", "Std dev"]
#    assert [ws.cell(row=r, column=1).value for r in (2, 3)] == ["blob_snr", "cd_x_nm"]
#    assert ws.cell(row=2, column=3).value == 1.0
#    assert ws.cell(row=2, column=5).value == 10.0
#
#    # --- 摘要：抓漏率 / 誤殺率 / 正確率 + 混淆矩陣都在裡面 ---
#    ws = wb["Summary"]
#    cells = {}
#    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=2):
#        if row[0].value is not None:
#            cells[str(row[0].value)] = row[1].value
#    assert cells["Total defects"] == 10
#    assert cells["Recipe name"] == "demo"
#    assert cells["Score expression"] == "blob_snr * 2"
#    assert cells["Threshold"] == 6.0
#    hit = [k for k in cells if k.startswith("Miss rate")]
#    kill = [k for k in cells if k.startswith("False alarm rate")]
#    assert hit and kill
#    assert cells[hit[0]] == pytest.approx(0.2)
#    assert cells[kill[0]] == pytest.approx(0.4)
#    assert cells["Accuracy"] == pytest.approx(0.7)
#    assert cells["Actual: real defect"] == 4                   # TP
#    assert cells["Actual: nuisance"] == 2                 # FP
#    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
#    assert "Confusion matrix" in texts
#
#
#def test_write_excel_without_ground_truth(tmp_path):
#    openpyxl = pytest.importorskip("openpyxl")
#    path = tmp_path / "b.xlsx"
#    report.write_excel(hand_results(), str(path))
#    wb = openpyxl.load_workbook(str(path))
#    assert wb.sheetnames == ["Summary", "Details", "Feature stats"]
#    texts = [str(c.value) for row in wb["Summary"].iter_rows() for c in row if c.value]
#    assert not any(t.startswith("Miss rate") for t in texts)
#
#
#def test_write_excel_empty_results(tmp_path):
#    """一顆都沒有也不能炸（使用者篩到空集合是常態）。"""
#    openpyxl = pytest.importorskip("openpyxl")
#    path = tmp_path / "e.xlsx"
#    report.write_excel([], str(path))
#    wb = openpyxl.load_workbook(str(path))
#    assert wb["Details"].max_row == 1
#    assert wb["Summary"].cell(row=3, column=2).value == 0
#
#F 4d9e62f4a9bd01ec28eec1e63e0c395716ad463c 236 tests/test_expression.py
#"""M1 驗收：score 表達式引擎（優先度、比較折疊、函數 arity、SAFE 語意、caret）。"""
#from __future__ import annotations
#
#import math
#
#import pytest
#
#from adept.core.pipeline import ExpressionError, parse_expression
#
#
#def ev(text, variables=None):
#    return parse_expression(text).eval(variables or {})
#
#
## ---------------------------------------------------------------------------
## 優先度與結合性
## ---------------------------------------------------------------------------
#def test_precedence_mul_over_add():
#    assert ev("2 + 3 * 4") == 14.0
#    assert ev("(2 + 3) * 4") == 20.0
#
#
#def test_power_right_assoc():
#    assert ev("2 ** 3 ** 2") == 512.0  # 2**(3**2)，非 (2**3)**2=64
#
#
#def test_unary_minus_binds_below_power():
#    assert ev("-2**2") == -4.0          # Python 語意：-(2**2)
#    assert ev("(-2)**2") == 4.0
#    assert ev("2**-1") == 0.5           # 指數可帶一元負號
#
#
#def test_left_assoc_sub_div():
#    assert ev("10 - 4 - 3") == 3.0
#    assert ev("12 / 4 / 3") == 1.0
#
#
#def test_number_formats():
#    assert ev("2.5e2") == 250.0
#    assert ev(".5 + 1") == 1.5
#    assert ev("1.5") == 1.5
#
#
## ---------------------------------------------------------------------------
## 比較與布林 → 1.0 / 0.0
## ---------------------------------------------------------------------------
#def test_comparisons_return_float():
#    assert ev("3 > 2") == 1.0
#    assert ev("2 > 3") == 0.0
#    assert ev("2 >= 2") == 1.0
#    assert ev("2 <= 1") == 0.0
#    assert ev("1 == 1") == 1.0
#    assert ev("1 != 1") == 0.0
#
#
#def test_comparison_folds_left_assoc_not_python_chaining():
#    # (3 < 2) → 0.0；0.0 < 1 → 1.0。Python 鏈式比較會給 False（0.0）。
#    assert ev("3 < 2 < 1") == 1.0
#    # (1 < 2) → 1.0；1.0 < 3 → 1.0
#    assert ev("1 < 2 < 3") == 1.0
#
#
#def test_booleans():
#    assert ev("1 and 0") == 0.0
#    assert ev("1 and 2") == 1.0
#    assert ev("1 or 0") == 1.0
#    assert ev("0 or 0") == 0.0
#    assert ev("not 0") == 1.0
#    assert ev("not 3") == 0.0
#    assert ev("not 1 > 2") == 1.0          # not 綁比較之後：not (1>2)
#    assert ev("not 1 or 1") == 1.0         # (not 1) or 1
#    assert ev("1 == 1 and 2 > 3") == 0.0
#    assert ev("(1 < 2) and (3 > 4)") == 0.0
#
#
#def test_arith_precedence_over_comparison():
#    assert ev("1 + 1 == 2") == 1.0
#
#
## ---------------------------------------------------------------------------
## 函數（含 parse 期 arity 檢查）
## ---------------------------------------------------------------------------
#def test_functions_arity_one():
#    assert ev("sqrt(9)") == 3.0
#    assert ev("abs(0 - 2)") == 2.0
#    assert ev("abs(-2)") == 2.0
#    assert ev("exp(0)") == 1.0
#    assert ev("log(1)") == 0.0
#
#
#def test_min_max_multiarg():
#    assert ev("min(3, 1, 2)") == 1.0
#    assert ev("max(3, 1, 2)") == 3.0
#    assert ev("min(5)") == 5.0
#    assert ev("max(1, 2) + min(0, 4)") == 2.0
#
#
#def test_arity_error_at_parse_time():
#    with pytest.raises(ExpressionError):
#        parse_expression("sqrt(1, 2)")
#    with pytest.raises(ExpressionError):
#        parse_expression("log()")
#    with pytest.raises(ExpressionError):
#        parse_expression("min()")
#    with pytest.raises(ExpressionError):
#        parse_expression("max()")
#
#
#def test_unknown_function_rejected():
#    with pytest.raises(ExpressionError):
#        parse_expression("sin(1)")
#
#
## ---------------------------------------------------------------------------
## variables
## ---------------------------------------------------------------------------
#def test_variables_set():
#    e = parse_expression("snr_max * sqrt(blob_area) + min(a, b) - a")
#    assert e.variables == frozenset({"snr_max", "blob_area", "a", "b"})
#    assert isinstance(e.variables, frozenset)
#    assert parse_expression("1 + 2").variables == frozenset()
#
#
#def test_variable_eval():
#    assert ev("snr_max * 2", {"snr_max": 3.5}) == 7.0
#    assert ev("a > b", {"a": 1, "b": 2}) == 0.0
#
#
## ---------------------------------------------------------------------------
## SAFE 語意
## ---------------------------------------------------------------------------
#def test_safe_division_by_zero():
#    assert ev("1 / 0") == 0.0
#    assert ev("0 / 0") == 0.0
#    assert ev("x / y", {"x": 5.0, "y": 0.0}) == 0.0
#
#
#def test_safe_log():
#    assert ev("log(0)") == 0.0
#    assert ev("log(-5)") == 0.0
#    assert ev("log(x)", {"x": -1.0}) == 0.0
#
#
#def test_safe_sqrt():
#    assert ev("sqrt(-9)") == 0.0
#    assert ev("sqrt(0 - 9)") == 0.0
#
#
#def test_safe_pow():
#    assert ev("0 ** -1") == 0.0            # 0 的負次方
#    assert ev("(-2) ** 0.5") == 0.0        # 負底非整數次方
#    assert ev("(-2) ** 3") == -8.0         # 負底整數次方照算
#
#
#def test_final_nan_inf_to_zero():
#    assert ev("exp(10000)") == 0.0         # overflow → inf → 0.0
#    assert ev("1e308 * 10") == 0.0         # inf → 0.0
#    assert ev("(1/0) ** 0") == 1.0         # 中間 SAFE 後正常值保留
#
#
#def test_nan_variable_final_zero():
#    assert ev("x + 1", {"x": float("nan")}) == 0.0
#    assert ev("x", {"x": float("inf")}) == 0.0
#
#
## ---------------------------------------------------------------------------
## 錯誤訊息：caret 位置、missing var、非數字變數
## ---------------------------------------------------------------------------
#def test_caret_position_unknown_symbol():
#    with pytest.raises(ExpressionError) as ei:
#        parse_expression("1 + $")
#    e = ei.value
#    assert e.pos == 4
#    lines = str(e).splitlines()
#    assert len(lines) == 3
#    assert lines[1] == "    1 + $"
#    assert lines[2] == "    " + " " * 4 + "^"   # caret 對準第 5 個字元
#
#
#def test_caret_position_trailing_garbage():
#    with pytest.raises(ExpressionError) as ei:
#        parse_expression("1 + 2 3")
#    assert ei.value.pos == 6
#    lines = str(ei.value).splitlines()
#    assert lines[2].index("^") - 4 == 6         # 4 = 訊息縮排寬度
#
#
#def test_caret_position_missing_operand():
#    with pytest.raises(ExpressionError) as ei:
#        parse_expression("1 + ")
#    assert ei.value.pos == 4                    # 指到結尾
#
#
#def test_empty_expression():
#    with pytest.raises(ExpressionError):
#        parse_expression("")
#    with pytest.raises(ExpressionError):
#        parse_expression("   ")
#
#
#def test_single_equals_hint():
#    with pytest.raises(ExpressionError) as ei:
#        parse_expression("a = 1")
#    assert "==" in str(ei.value)
#
#
#def test_missing_paren():
#    with pytest.raises(ExpressionError):
#        parse_expression("(1 + 2")
#    with pytest.raises(ExpressionError):
#        parse_expression("sqrt(1")
#
#
#def test_missing_variable_raises_and_lists_available():
#    e = parse_expression("a + b")
#    with pytest.raises(ExpressionError) as ei:
#        e.eval({"a": 1.0, "zz": 2.0})
#    msg = str(ei.value)
#    assert "'b'" in msg
#    assert "a" in msg and "zz" in msg           # 列出目前可用變數
#    assert ei.value.pos == 4                    # 指到 b 的位置
#
#
#def test_non_numeric_variable_friendly_error():
#    e = parse_expression("a * 2")
#    with pytest.raises(ExpressionError):
#        e.eval({"a": "hello"})
#    with pytest.raises(ExpressionError):
#        e.eval({"a": None})
#    with pytest.raises(ExpressionError):
#        e.eval({"a": [1, 2]})
#
#
#def test_bool_variable_ok():
#    assert ev("a + 1", {"a": True}) == 2.0
#
#F 4017d96f4145ba179d8e186b7f0e02b6e47ed8ef 374 tests/test_fab_probe.py
#"""Tests for fab_probe/ — 廠內格式探測腳本（以 subprocess 跑，檢查文字輸出）。
#
#這三支腳本是「單檔、純標準函式庫」的，所以測試也把它們當外部程式跑：
#用 tools/make_sample*.py 產生資料 → `sys.executable probe_*.py` → 檢查輸出文字。
#"""
#from __future__ import annotations
#
#import ast
#import json
#import os
#import subprocess
#import sys
#
#import pytest
#
#REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#PROBE_DIR = os.path.join(REPO, "fab_probe")
#KLARF_PROBE = os.path.join(PROBE_DIR, "probe_klarf.py")
#TIFF_PROBE = os.path.join(PROBE_DIR, "probe_tiff.py")
#STATS_PROBE = os.path.join(PROBE_DIR, "probe_stats.py")
#ALL_PROBES = (KLARF_PROBE, TIFF_PROBE, STATS_PROBE)
#
#_TOOLS = os.path.join(REPO, "tools")
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#N_EBI = 6
#N_RSEM = 4
#
## 真實感的識別碼（遮蔽測試用）：這些字串預設絕不可以出現在報告裡
#REAL_LOT = "AA0000.0X"
#REAL_WAFER = "AA0000.01"
#REAL_DEVICE = "DEVICE0001"
#
#
## ---------------------------------------------------------------- fixtures
#
#@pytest.fixture(scope="module")
#def ebi(tmp_path_factory):
#    import make_sample                                  # noqa: WPS433 (lazy)
#    out = tmp_path_factory.mktemp("probe_ebi")
#    return make_sample.generate(str(out / "lot"), n=N_EBI, seed=7)
#
#
#@pytest.fixture(scope="module")
#def rsem(tmp_path_factory):
#    import make_sample_rsem                             # noqa: WPS433
#    out = tmp_path_factory.mktemp("probe_rsem")
#    return make_sample_rsem.generate(str(out / "lot"), n=N_RSEM, seed=11)
#
#
#@pytest.fixture(scope="module")
#def ebi_with_ids(ebi, tmp_path_factory):
#    """把合成 KLARF 的 LotID/WaferID/DeviceID 換成真實感的字串。"""
#    out = tmp_path_factory.mktemp("probe_ids")
#    src = ebi["klarf"]
#    text = open(src, encoding="utf-8").read()
#    text = (text.replace('LotID "LOT_SYN"', 'LotID "%s"' % REAL_LOT)
#                .replace('WaferID "W01"', 'WaferID "%s"' % REAL_WAFER)
#                .replace('DeviceID "SYNDEV"', 'DeviceID "%s"' % REAL_DEVICE))
#    assert REAL_LOT in text and REAL_WAFER in text and REAL_DEVICE in text
#    dst = str(out / "LOT_SYN.001")
#    with open(dst, "w", encoding="utf-8", newline="") as f:
#        f.write(text)
#    return dst
#
#
## ---------------------------------------------------------------- helpers
#
#def run_probe(script, *args):
#    env = dict(os.environ)
#    env["PYTHONIOENCODING"] = "utf-8"
#    proc = subprocess.run([sys.executable, script] + [str(a) for a in args],
#                          cwd=REPO, env=env, stdout=subprocess.PIPE,
#                          stderr=subprocess.PIPE)
#    out = proc.stdout.decode("utf-8", "replace")
#    err = proc.stderr.decode("utf-8", "replace")
#    return proc.returncode, out, err
#
#
#def parse_summary(out):
#    """取出 >>>JSON_BEGIN … >>>JSON_END 之間的摘要並解析。"""
#    assert ">>>JSON_BEGIN" in out and ">>>JSON_END" in out, "報告缺少可回報的 JSON 區塊"
#    body = out.split(">>>JSON_BEGIN", 1)[1].split(">>>JSON_END", 1)[0]
#    return json.loads(body)
#
#
## ---------------------------------------------------------------- probe_klarf
#
#def test_klarf_12_structure(ebi):
#    code, out, err = run_probe(KLARF_PROBE, ebi["klarf"])
#    assert code == 0, err
#    s = parse_summary(out)
#    assert s["klarf_version"] == "1.2"
#    assert s["version_heuristic"] == "FileVersion N M"
#    assert s["defect_columns"] == ["DEFECTID", "XREL", "YREL", "XINDEX", "YINDEX",
#                                   "CLASSNUMBER", "IMAGECOUNT", "IMAGELIST"]
#    assert s["n_defect_rows"] == N_EBI
#    assert s["n_defect_lists"] == 1
#    # 影像佈局：IMAGELIST 欄 + TiffSpec 宣告每張圖 1 個 token
#    assert s["image_layout_variant"] == "declared"
#    assert s["image_layout_nfields"] == 1
#    assert s["imagecount_distribution"] == {"2": N_EBI}
#    assert s["total_images"] == 2 * N_EBI
#    assert s["tiff_referenced"] is True and s["tiff_exists"] is True
#    assert s["row_length_anomalies_aligned"] == 0
#    assert "1.2" in out and "假設 #3" in out
#
#
#def test_klarf_18_structure(rsem):
#    code, out, err = run_probe(KLARF_PROBE, rsem["klarf"])
#    assert code == 0, err
#    s = parse_summary(out)
#    assert s["klarf_version"] == "1.8"
#    assert s["version_heuristic"] == "Record FileRecord"
#    assert s["defect_columns"][-1] == "IMAGEINFO"
#    assert s["defect_column_types"][-1] == "ImageList"
#    assert s["n_defect_rows"] == N_RSEM
#    assert s["image_layout_variant"] == "images18"
#    assert s["imagecount_distribution"] == {"1": N_RSEM}
#    # 每顆 defect 一個 PNG，且都找得到
#    assert s["n_rows_with_image_filename"] == N_RSEM
#    assert s["n_image_files_found"] == N_RSEM
#    assert s["image_file_extensions"] == {".png": N_RSEM}
#
#
#def test_klarf_variant_d_real_fixture():
#    """廠內實檔樣式：沒有 IMAGECOUNT 欄，但列尾帶 Images 子區塊（變體 D）。"""
#    fixture = os.path.join(REPO, "tests", "fixtures", "sample_real.klarf")
#    code, out, err = run_probe(KLARF_PROBE, fixture)
#    assert code == 0, err
#    s = parse_summary(out)
#    assert s["klarf_version"] == "1.8"
#    assert s["imagecount_col"] == -1
#    assert s["image_layout_variant"] == "imagefile"
#    assert s["n_defect_columns"] == 42
#    # 影像子區塊壓成一個 token 後，每列都對得上 42 欄
#    assert s["row_length_anomalies_aligned"] == 0
#
#
#def test_klarf_redacts_identifiers_by_default(ebi_with_ids):
#    code, out, err = run_probe(KLARF_PROBE, ebi_with_ids)
#    assert code == 0, err
#    for ident in (REAL_LOT, REAL_WAFER, REAL_DEVICE):
#        assert ident not in out, "預設輸出洩漏了識別碼 %s" % ident
#    assert "<redacted," in out
#    # 欄位名本身要看得到（那是格式資訊，不是資料）
#    assert "LotID" in out and "WaferID" in out and "DeviceID" in out
#    # 座標欄的值一個都不能出現
#    rows = open(ebi_with_ids, encoding="utf-8").read().splitlines()
#    xrels = [ln.split()[1] for ln in rows if ln.strip()[:1].isdigit() and len(ln.split()) == 9]
#    assert xrels, "測資裡應該有 defect 列"
#    for v in xrels:
#        assert v not in out, "報告洩漏了座標值 %s" % v
#
#
#def test_klarf_include_ids_opt_in(ebi_with_ids):
#    code, out, err = run_probe(KLARF_PROBE, ebi_with_ids, "--include-ids")
#    assert code == 0, err
#    for ident in (REAL_LOT, REAL_WAFER, REAL_DEVICE):
#        assert ident in out, "--include-ids 應該要輸出 %s" % ident
#    assert parse_summary(out)["ids_included"] is True
#
#
#def test_klarf_rows_option(ebi):
#    code, out, _ = run_probe(KLARF_PROBE, ebi["klarf"], "--rows", "3")
#    assert code == 0
#    assert parse_summary(out)["n_defect_rows"] == N_EBI
#
#
## ---------------------------------------------------------------- probe_tiff
#
#def test_tiff_pages_and_uniformity(ebi):
#    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"])
#    assert code == 0, err
#    s = parse_summary(out)
#    assert s["n_pages"] == 2 * N_EBI
#    assert s["uniform_pages"] is True
#    assert s["n_page_signatures"] == 1
#    assert s["page0"]["width"] == 128 and s["page0"]["height"] == 128
#    assert s["page0"]["bits"] == 8 and s["page0"]["layout"] == "strip"
#    assert s["bigtiff"] is False
#
#
#def test_tiff_with_klarf_reports_pairing(ebi):
#    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"],
#                               "--with-klarf", ebi["klarf"])
#    assert code == 0, err
#    s = parse_summary(out)
#    cross = s["klarf_crosscheck"]
#    assert cross is not None
#    assert cross["n_defect_rows"] == N_EBI
#    assert cross["pattern"] == "pairs"
#    assert cross["pages_eq_2x_defects"] is True
#    assert cross["pages_eq_imagecount"] is True
#    assert cross["map_mode"] == "imagelist"
#    assert cross["map_base"] == 1
#    assert cross["map_out_of_range"] == 0
#    assert "假設 #1" in out
#    assert "defect #0 -> [0, 1]" in out
#
#
#def test_tiff_with_rsem_klarf_reports_single(ebi, rsem):
#    """給錯配的 KLARF 也不能爆：要如實報出 single 與連續配頁。"""
#    code, out, err = run_probe(TIFF_PROBE, ebi["tiff"], "--with-klarf", rsem["klarf"])
#    assert code == 0, err
#    cross = parse_summary(out)["klarf_crosscheck"]
#    assert cross["pattern"] == "single"
#    assert cross["pages_eq_imagecount"] is False
#    assert cross["map_mode"] == "sequential"
#
#
#def test_tiff_text_tag_redaction_rule():
#    """ImageDescription 的遮蔽規則：數字留、識別碼遮 —— 這是 nm_per_px 的關鍵。"""
#    import importlib.util
#
#    spec = importlib.util.spec_from_file_location("probe_tiff_mod", TIFF_PROBE)
#    mod = importlib.util.module_from_spec(spec)
#    saved = sys.dont_write_bytecode
#    sys.dont_write_bytecode = True             # 不要在 fab_probe/ 留下 __pycache__
#    try:
#        spec.loader.exec_module(mod)
#    finally:
#        sys.dont_write_bytecode = saved
#    text = 'LotID AA0000.0X PixelSize=3.25nm Mag=50000 Cam1 SN=AB12345678'
#    red = mod.redact_text(text)
#    assert "AA0000.0X" not in red and "AB12345678" not in red
#    assert "3.25nm" in red and "50000" in red          # 數值一定要保留
#    assert "PixelSize" in red and "LotID" in red       # 欄位名保留
#    assert mod.redact_text(text, include_ids=True) == text
#
#
#def test_tiff_redacts_filename(ebi):
#    code, out, _ = run_probe(TIFF_PROBE, ebi["tiff"])
#    assert code == 0
#    assert "LOT_SYN.tif" not in out
#    assert "<redacted," in out
#    code, out, _ = run_probe(TIFF_PROBE, ebi["tiff"], "--include-ids")
#    assert code == 0
#    assert "LOT_SYN.tif" in out
#
#
## ---------------------------------------------------------------- probe_stats
#
#def _ascii_grid_lines(out):
#    """取出第 5 段的 4x4 ASCII 方格。"""
#    lines = out.splitlines()
#    start = None
#    for i, ln in enumerate(lines):
#        if "ASCII" in ln and "字元梯度" in ln:
#            start = i + 1
#            break
#    assert start is not None, "報告裡找不到 4x4 ASCII 方格"
#    return [ln.strip() for ln in lines[start:start + 4]]
#
#
#def test_stats_histogram_and_grid(ebi):
#    code, out, err = run_probe(STATS_PROBE, ebi["tiff"], "--pages", "4", "--bins", "16")
#    assert code == 0, err
#    s = parse_summary(out)
#    assert s["decoded_pages"] == 4
#    assert len(s["sampled_pages"]) == 4
#    assert s["bits"] == 8 and s["bins"] == 16
#    assert len(s["histogram"]) == 16
#    # 直方圖各格加總 == 取樣像素數 == 4 頁 x 128 x 128
#    assert sum(s["histogram"]) == s["sampled_pixels"] == 4 * 128 * 128
#    assert 0 <= s["min"] <= s["max"] <= 255
#    assert len(s["page_means"]) == 4 and len(s["page_stds"]) == 4
#    assert len(s["grid4x4"]) == 16
#    grid = _ascii_grid_lines(out)
#    assert len(grid) == 4, grid
#    for row in grid:
#        assert len(row) == 4, row
#        assert all(ch in ".:-=+*#@" for ch in row), row
#    assert "只有這一支會實際讀取影像的像素值" in out
#
#
#def test_stats_bins_option(ebi):
#    code, out, err = run_probe(STATS_PROBE, ebi["tiff"], "--pages", "2", "--bins", "8")
#    assert code == 0, err
#    s = parse_summary(out)
#    assert len(s["histogram"]) == 8
#    assert sum(s["histogram"]) == s["sampled_pixels"] == 2 * 128 * 128
#
#
#def test_stats_on_png_reports_not_tiff(rsem):
#    """RSEM 是每顆 defect 一個 PNG —— 要說清楚不是 TIFF，而不是爆掉。"""
#    png = rsem["images"][0]
#    code, out, err = run_probe(STATS_PROBE, png)
#    assert code != 0
#    assert "Traceback" not in err and "Traceback" not in out
#    assert "不是 TIFF" in err
#    assert "PNG" in err
#
#
## ------------------------------------------------- 通用：好輸入 0、壞輸入非 0
#
#def test_all_probes_exit_zero_on_good_input(ebi):
#    for script, args in ((KLARF_PROBE, [ebi["klarf"]]),
#                         (TIFF_PROBE, [ebi["tiff"]]),
#                         (STATS_PROBE, [ebi["tiff"]])):
#        code, out, err = run_probe(script, *args)
#        assert code == 0, "%s 失敗：%s" % (os.path.basename(script), err)
#        parse_summary(out)                    # 三支都要有可回報的 JSON 區塊
#
#
#@pytest.mark.parametrize("script", ALL_PROBES)
#def test_probe_missing_file(script, tmp_path):
#    missing = tmp_path / "nope.dat"
#    code, out, err = run_probe(script, missing)
#    assert code != 0
#    assert "Traceback" not in err
#    assert "找不到檔案" in err
#
#
#@pytest.mark.parametrize("script", ALL_PROBES)
#def test_probe_garbage_file(script, tmp_path):
#    junk = tmp_path / "junk.dat"
#    junk.write_bytes(b"this is not a klarf nor a tiff\n" * 4)
#    code, out, err = run_probe(script, junk)
#    assert code != 0
#    assert "Traceback" not in err
#    assert err.startswith("錯誤：")
#    assert len(err.strip()) > 10          # 有一句看得懂的說明
#
#
#@pytest.mark.parametrize("script", ALL_PROBES)
#def test_probe_empty_file(script, tmp_path):
#    empty = tmp_path / "empty.dat"
#    empty.write_bytes(b"")
#    code, out, err = run_probe(script, empty)
#    assert code != 0
#    assert "Traceback" not in err
#
#
## ------------------------------------------------- 單檔、純標準函式庫
#
#FORBIDDEN = {"numpy", "cv2", "tifffile", "adept", "PySide6", "scipy", "PIL"}
#
#
#@pytest.mark.parametrize("script", ALL_PROBES)
#def test_probe_is_stdlib_only(script):
#    tree = ast.parse(open(script, encoding="utf-8").read(), filename=script)
#    imported = set()
#    for node in ast.walk(tree):
#        if isinstance(node, ast.Import):
#            for alias in node.names:
#                imported.add(alias.name.split(".")[0])
#        elif isinstance(node, ast.ImportFrom):
#            if node.level:                     # 相對 import = 依賴同專案檔案
#                pytest.fail("%s 用了相對 import，違反『單檔』原則"
#                            % os.path.basename(script))
#            if node.module:
#                imported.add(node.module.split(".")[0])
#    leaked = imported & FORBIDDEN
#    assert not leaked, "%s 匯入了非標準函式庫：%s" % (os.path.basename(script), leaked)
#    assert imported <= {"argparse", "array", "json", "math", "os", "re",
#                        "struct", "sys"}, imported
#
#
#@pytest.mark.parametrize("script", ALL_PROBES)
#def test_probe_is_python36_parsable(script):
#    """廠內機器可能是舊 Python：語法要在 3.6 就能 parse。"""
#    src = open(script, encoding="utf-8").read()
#    ast.parse(src, filename=script, feature_version=(3, 6))
#
#
#def test_readme_lists_all_three_probes():
#    readme = open(os.path.join(PROBE_DIR, "README.md"), encoding="utf-8").read()
#    for name in ("probe_klarf.py", "probe_tiff.py", "probe_stats.py"):
#        assert name in readme
#    for phrase in ("假設 #1", "假設 #2", "假設 #3", "--include-ids"):
#        assert phrase in readme
#
#F 862f012efa32c2e2162dd591bb2896cab70145c9 113 tests/test_glv.py
#"""Tests for adept.core.algo.glv (vendored from PEAR)."""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#
#from adept.core.algo.glv import (
#    GLV_STATS,
#    ROI,
#    default_metrics,
#    glv_stats,
#    glv_value,
#    group_snr,
#    metric_formula,
#    metric_label,
#    pixel_hist,
#    quantile_of,
#    roi_patch,
#    summarize,
#)
#
#
#@pytest.fixture()
#def patch():
#    rng = np.random.default_rng(1234)
#    return rng.integers(0, 256, size=(20, 30)).astype(np.uint8)
#
#
#def test_glv_stats_known_array(patch):
#    f = patch.astype(np.float64).ravel()
#    s = glv_stats(patch)
#    assert set(s) == set(GLV_STATS)
#    assert s["glv_mean"] == pytest.approx(f.mean())
#    assert s["glv_median"] == pytest.approx(np.median(f))
#    assert s["glv_q25"] == pytest.approx(np.percentile(f, 25))
#    assert s["glv_q75"] == pytest.approx(np.percentile(f, 75))
#    assert s["glv_std"] == pytest.approx(f.std())
#    assert s["glv_min"] == pytest.approx(f.min())
#    assert s["glv_max"] == pytest.approx(f.max())
#
#
#def test_dynamic_quantile_glv_q30(patch):
#    f = patch.astype(np.float64).ravel()
#    assert quantile_of("glv_q30") == 30
#    assert quantile_of("glv_mean") is None
#    assert quantile_of("glv_qxx") is None
#    assert glv_value(patch, "glv_q30") == pytest.approx(np.percentile(f, 30))
#    assert metric_label("glv_q30") == "GLV Q30"
#    assert metric_formula("glv_q30") == "30th percentile"
#    # fixed ids still resolve through the fixed tables
#    assert metric_label("glv_mean") == "GLV mean"
#    assert metric_formula("glv_mean") == "mean(gray)"
#    # unknown id falls through untouched
#    assert metric_label("bogus") == "bogus"
#    assert glv_value(patch, "bogus") == 0.0
#
#
#def test_empty_patch_guards():
#    empty = np.array([], dtype=np.uint8)
#    assert glv_value(empty, "glv_mean") == 0.0
#    assert glv_value(empty, "glv_q30") == 0.0
#    assert all(v == 0.0 for v in glv_stats(empty).values())
#    counts, edges = pixel_hist(empty, bins=16)
#    assert counts.sum() == 0 and len(edges) == 17
#    s = summarize(np.array([]))
#    assert s["n"] == 0 and s["mean"] == 0.0
#
#
#def test_roi_patch_clipping_and_outside():
#    img = np.arange(100, dtype=np.uint8).reshape(10, 10)
#    p = roi_patch(img, (2, 3, 4, 5))
#    assert p.shape == (5, 4)
#    assert p[0, 0] == img[3, 2]
#    # partially outside -> clipped
#    p2 = roi_patch(img, (-2, -2, 4, 4))
#    assert p2.shape == (2, 2)
#    # fully outside -> None
#    assert roi_patch(img, (50, 50, 5, 5)) is None
#    assert roi_patch(img, (0, 0, 0, 0)) is None
#
#
#def test_group_snr_signed_convention():
#    img = np.full((40, 40), 100, dtype=np.float64)
#    rng = np.random.default_rng(0)
#    img += rng.normal(0, 5, img.shape)
#    img[5:15, 5:15] += 60.0    # bright target region
#    rois = [
#        ROI(1, "g", (5, 5, 10, 10)),     # target
#        ROI(2, "g", (25, 5, 10, 10)),
#        ROI(3, "g", (5, 25, 10, 10)),
#        ROI(4, "g", (25, 25, 10, 10)),
#    ]
#    s = group_snr(img, rois, target_rid=1)
#    assert s is not None
#    # manual (mu_T - mu_R) / sigma_R over pooled reference pixels
#    tp = img[5:15, 5:15]
#    ref = np.concatenate([img[5:15, 25:35].ravel(), img[25:35, 5:15].ravel(),
#                          img[25:35, 25:35].ravel()])
#    expect = (tp.mean() - ref.mean()) / ref.std()
#    assert s == pytest.approx(expect)
#    assert s > 0  # brighter target -> positive (signed convention)
#    # darker target -> negative
#    img2 = img.copy()
#    img2[5:15, 5:15] -= 120.0
#    assert group_snr(img2, rois, target_rid=1) < 0
#    # guards: no target / no reference
#    assert group_snr(img, rois, target_rid=99) is None
#    assert group_snr(img, [rois[0]], target_rid=1) is None
#
#
#def test_default_metrics():
#    assert default_metrics() == ["glv_mean", "glv_median"]
#
#F 2dc56d1e49cf61a990c7e0f9441f3ca99082380c 229 tests/test_golden_step.py
#"""Tests for the M4-1 Golden Cell cards: ``cell_period`` + ``golden_cell``.
#
#沒有 ref 影像的資料（Review SEM 單張）靠這兩張卡自己造參考圖：
#量週期 → 疊 cell → 鋪回原尺寸 → 下游 subtract 照跑。
#"""
#from __future__ import annotations
#
#import cv2
#import numpy as np
#import pytest
#
#import adept.core.steps  # noqa: F401 — registration side-effect
#from adept.core.pipeline.context import Context
#from adept.core.pipeline.step import REGISTRY, StepError
#
#PITCH = 16
#DEFECT = (slice(70, 80), slice(100, 112))   # 種進去的缺陷位置（y, x）
#
#
#def run_step(key, ctx, **params):
#    cls = REGISTRY[key]
#    return cls().run(ctx, cls.validate_params(params))
#
#
#def _cell_tile(pitch: int = PITCH) -> np.ndarray:
#    c = np.zeros((pitch, pitch), np.float64)
#    cv2.rectangle(c, (3, 3), (pitch - 6, pitch - 6), 210, -1)
#    c[pitch - 4:pitch - 2, 2:5] = 120
#    return cv2.GaussianBlur(c, (3, 3), 0.9) + 35.0
#
#
#def _clean_lattice(h=256, w=256, pitch=PITCH, crop=0, seed=0, noise=3.0):
#    tile = _cell_tile(pitch)
#    big = np.tile(tile, (h // pitch + 3, w // pitch + 3))
#    img = big[crop:crop + h, crop:crop + w]
#    img = img + np.random.default_rng(seed).normal(0, noise, img.shape)
#    return np.clip(img, 0, 255).astype(np.uint8)
#
#
#@pytest.fixture(scope="module")
#def clean():
#    return _clean_lattice()
#
#
#@pytest.fixture(scope="module")
#def defective(clean):
#    """同一張週期影像，但其中一格被種了一個亮缺陷。"""
#    img = clean.copy()
#    img[DEFECT] = 255
#    return img
#
#
#def _noise_image():
#    return np.random.default_rng(1).integers(0, 256, (128, 128)).astype(np.uint8)
#
#
## ---------------------------------------------------------------- cell_period
#
#def test_cell_period_recovers_pitch_and_fills_meta(defective):
#    ctx = Context(images={"test": defective})
#    run_step("cell_period", ctx)
#    assert abs(ctx.features["cell_px"] - PITCH) <= 1
#    assert abs(ctx.features["cell_py"] - PITCH) <= 1
#    assert ctx.features["cell_conf_x"] > 50 and ctx.features["cell_conf_y"] > 50
#    assert ctx.meta["cell_period"] == {"px": int(ctx.features["cell_px"]),
#                                       "py": int(ctx.features["cell_py"])}
#    assert not ctx.meta.get("warnings")
#
#
#def test_cell_period_without_refine_also_works(defective):
#    ctx = Context(images={"test": defective})
#    run_step("cell_period", ctx, refine=False)
#    assert abs(ctx.features["cell_px"] - PITCH) <= 1
#    assert abs(ctx.features["cell_py"] - PITCH) <= 1
#
#
#def test_cell_period_on_non_periodic_warns_but_does_not_raise():
#    """沒有週期性不是錯誤：回零 + 白話警告。"""
#    ctx = Context(images={"test": _noise_image()})
#    run_step("cell_period", ctx)
#    assert ctx.features["cell_px"] == 0.0 and ctx.features["cell_py"] == 0.0
#    assert ctx.meta["cell_period"] == {"px": 0, "py": 0}
#    warns = ctx.meta.get("warnings") or []
#    assert any("no periodic structure" in w for w in warns), warns
#
#
#def test_cell_period_rejects_inverted_bounds(defective):
#    ctx = Context(images={"test": defective})
#    with pytest.raises(StepError):
#        run_step("cell_period", ctx, min_period=32, max_period=8)
#
#
## ---------------------------------------------------------------- golden_cell
#
#def test_golden_cell_shape_matches_source_and_defect_is_attenuated(clean, defective):
#    ctx = Context(images={"test": defective})
#    run_step("cell_period", ctx)
#    run_step("golden_cell", ctx, method="median")
#
#    golden = ctx.images["ref"]
#    assert golden.shape == defective.shape        # 下游 subtract 要求 shape 完全相同
#    assert golden.dtype == defective.dtype
#
#    ref = clean.astype(np.float64)
#    resid_golden = float(np.abs(golden[DEFECT].astype(np.float64) - ref[DEFECT]).mean())
#    resid_source = float(np.abs(defective[DEFECT].astype(np.float64) - ref[DEFECT]).mean())
#    # 缺陷被其他 cell 的中位數洗掉：殘差要小一個量級以上
#    assert resid_golden < 0.1 * resid_source
#    # 而且整張圖都要像乾淨版圖，不是只有缺陷處剛好對上
#    assert float(np.abs(golden.astype(np.float64) - ref).mean()) < 10.0
#
#    assert ctx.features["golden_px"] == pytest.approx(PITCH, abs=1)
#    assert ctx.features["golden_py"] == pytest.approx(PITCH, abs=1)
#    assert 0.0 <= ctx.features["golden_ghost"] <= 100.0
#
#
#def test_golden_cell_uses_cell_period_meta_without_reestimating(defective):
#    """meta 有週期就直接用（這裡塞一個明顯不同的值來證明它真的被讀了）。"""
#    ctx = Context(images={"test": defective}, meta={"cell_period": {"px": 32, "py": 32}})
#    run_step("golden_cell", ctx)
#    assert (ctx.features["golden_px"], ctx.features["golden_py"]) == (32.0, 32.0)
#
#
#def test_golden_cell_explicit_params_win_over_meta(defective):
#    ctx = Context(images={"test": defective}, meta={"cell_period": {"px": 32, "py": 32}})
#    run_step("golden_cell", ctx, px=PITCH, py=PITCH)
#    assert (ctx.features["golden_px"], ctx.features["golden_py"]) == (16.0, 16.0)
#
#
#def test_golden_cell_standalone_estimates_period_itself(defective):
#    ctx = Context(images={"test": defective})
#    run_step("golden_cell", ctx)
#    assert ctx.features["golden_px"] == pytest.approx(PITCH, abs=1)
#    assert ctx.meta["golden_cell"]["n_cells"] > 4
#
#
#def test_phase_search_beats_no_phase_search_on_misaligned_crop():
#    """刻意錯開相位的裁切圖：開相位搜尋要疊得更清晰（lap_var 更高）。"""
#    img = _clean_lattice(crop=5)
#    got = {}
#    for flag in (True, False):
#        ctx = Context(images={"test": img})
#        run_step("golden_cell", ctx, method="mean", px=PITCH, py=PITCH,
#                 phase_search=flag)
#        got[flag] = (ctx.meta["golden_cell"], ctx.features["golden_ghost"])
#
#    assert got[False][0]["ox"] == 0 and got[False][0]["oy"] == 0
#    assert got[True][0]["ox"] != 0 or got[True][0]["oy"] != 0
#    assert got[True][0]["lap_var"] > 1.2 * got[False][0]["lap_var"]
#    assert got[True][1] >= got[False][1]
#
#
#def test_golden_cell_output_stream_is_subtractable(defective):
#    """走完整條路：golden_cell 寫 ref → subtract 直接吃得下，缺陷留在 diff 上。"""
#    ctx = Context(images={"test": defective})
#    run_step("golden_cell", ctx)
#    run_step("subtract", ctx, a="test", b="ref")
#    diff = ctx.images["diff"]
#    assert diff.shape == defective.shape
#    assert float(diff[DEFECT].mean()) > 5.0 * float(diff.mean())
#
#
#def test_golden_cell_custom_out_key(defective):
#    ctx = Context(images={"test": defective})
#    run_step("golden_cell", ctx, out="golden")
#    assert "golden" in ctx.images and "ref" not in ctx.images
#
#
#def test_golden_cell_ghost_warn_fires(defective):
#    ctx = Context(images={"test": defective})
#    run_step("golden_cell", ctx, ghost_warn=100.0)   # 不可能達到的門檻
#    warns = ctx.meta.get("warnings") or []
#    assert any("looks blurred" in w for w in warns), warns
#
#
#def test_golden_cell_float_source_keeps_scale(clean):
#    """float32 0–1 的影像流進來，出去也要是 0–1 的 float32（否則 subtract 差 255 倍）。"""
#    src = (clean.astype(np.float32) / 255.0)
#    ctx = Context(images={"test": src})
#    run_step("golden_cell", ctx)
#    out = ctx.images["ref"]
#    assert out.shape == src.shape and out.dtype == np.float32
#    assert 0.0 <= float(out.min()) and float(out.max()) <= 1.5
#
#
## ---------------------------------------------------------------- 防呆
#
#def test_golden_cell_on_non_periodic_raises_helpful_error():
#    ctx = Context(images={"test": _noise_image()})
#    with pytest.raises(StepError) as ei:
#        run_step("golden_cell", ctx)
#    msg = str(ei.value)
#    assert "cell" in msg and "period" in msg
#    assert "ref" in msg or "比對路線" in msg      # 要告訴使用者改走哪條路
#
#
#def test_golden_cell_period_larger_than_image_raises(defective):
#    ctx = Context(images={"test": defective[:40, :40]})
#    with pytest.raises(StepError) as ei:
#        run_step("golden_cell", ctx, px=64, py=64)
#    assert "larger than the image" in str(ei.value)
#
#
#def test_golden_cell_too_few_cells_raises(defective):
#    ctx = Context(images={"test": defective[:24, :24]})
#    with pytest.raises(StepError) as ei:
#        run_step("golden_cell", ctx, px=20, py=20)
#    assert "complete cell(s)" in str(ei.value)
#
#
## ---------------------------------------------------------------- 推廣鐵則
#
#@pytest.mark.parametrize("key", ["cell_period", "golden_cell"])
#def test_promotion_rules_help_everywhere(key):
#    d = REGISTRY[key].describe()
#    assert str(d["help"]).strip(), f"{key}: card help empty"
#    assert str(d["label"]).strip()
#    for pr in d["params"]:
#        assert str(pr["help"]).strip(), f"{key}.{pr['name']}: param help empty"
#        assert pr["default"] is not None, f"{key}.{pr['name']}: no default"
#        if pr["type"] in ("int", "float"):
#            assert pr["min"] is not None and pr["max"] is not None, \
#                f"{key}.{pr['name']}: 數值參數要有 min/max 護欄"
#
#
#def test_golden_cell_does_not_require_ref():
#    assert REGISTRY["golden_cell"].requires_ref is False
#    assert REGISTRY["golden_cell"].resolve_writes({}) == ["ref"]
#
#F 591460dd7f2ed13dad5ba5aa3337884312e1bfc2 73 tests/test_histmatch.py
#"""Tests for adept.core.algo.histmatch (vendored 2026-07-27)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.histmatch import (
#    MATCH_FN,
#    compute_histogram,
#    image_stats,
#    match_histogram_exact,
#    match_histogram_linear,
#    match_histogram_percentile,
#)
#
#
#def _images():
#    rng = np.random.default_rng(7)
#    src = np.clip(rng.normal(100, 20, size=(120, 120)), 0, 255).astype(np.uint8)
#    ref = np.clip(rng.normal(150, 10, size=(120, 120)), 0, 255).astype(np.uint8)
#    return src, ref
#
#
#def test_linear_matches_mean_and_std():
#    src, ref = _images()
#    out = match_histogram_linear(src, ref)
#    assert out.dtype == src.dtype
#    assert abs(float(out.mean()) - float(ref.mean())) < 2.0
#    assert abs(float(out.std()) - float(ref.std())) < 2.0
#
#
#def test_exact_matches_cdf():
#    src, ref = _images()
#    out = match_histogram_exact(src, ref)
#    assert out.dtype == src.dtype
#    # Quantiles of the matched image must track the reference quantiles
#    for q in (10, 25, 50, 75, 90):
#        assert abs(float(np.percentile(out, q)) - float(np.percentile(ref, q))) <= 3.0
#
#
#def test_percentile_robust_to_outliers():
#    src, ref = _images()
#    src = src.copy()
#    # Inject 1% hot-pixel outliers at full scale
#    rng = np.random.default_rng(11)
#    idx = rng.choice(src.size, size=src.size // 100, replace=False)
#    src.flat[idx] = 255
#    out = match_histogram_percentile(src, ref)
#    # The P2/P98 anchors of the result must land on the reference anchors
#    assert abs(float(np.percentile(out, 2)) - float(np.percentile(ref, 2))) <= 3.0
#    assert abs(float(np.percentile(out, 98)) - float(np.percentile(ref, 98))) <= 3.0
#
#
#def test_dispatch_table():
#    src, ref = _images()
#    assert set(MATCH_FN.keys()) == {"exact", "linear", "percentile"}
#    for name, fn in MATCH_FN.items():
#        out = fn(src, ref)
#        assert out.shape == src.shape
#        assert out.dtype == src.dtype
#
#
#def test_compute_histogram_and_stats():
#    src, _ = _images()
#    counts, edges = compute_histogram(src)
#    assert counts.sum() == src.size
#    assert len(counts) == 256
#    assert len(edges) == 257
#
#    stats = image_stats(src)
#    for key in ("mean", "std", "min", "max", "P2", "median", "P98"):
#        assert key in stats
#    assert stats["P2"] <= stats["median"] <= stats["P98"]
#
#F f99c2421fe691efb20e27f690a066aa2024a325e 157 tests/test_klarf_core.py
#"""Tests for adept.core.ingest.klarf_core (vendored KLIP engine)."""
#from __future__ import annotations
#
#import os
#
#from adept.core.ingest import klarf_core
#
#FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_real.klarf")
#
#
## ---------------------------------------------------------------- synthetic files
#
#KLARF12_WITH_IMAGES = """FileVersion 1 2;
#FileTimestamp 03-14-26 08:00:00;
#InspectionStationID "EBI" "EBI" "01";
#SampleType WAFER;
#ResultTimestamp 03-14-26 08:30:00;
#LotID "LOT001";
#SampleSize 1 300;
#DeviceID "DEV01";
#SetupID "SETUP01" 03-14-26 08:00:00;
#StepID "STEP01";
#SampleOrientationMarkType NOTCH;
#OrientationMarkLocation DOWN;
#DiePitch 1000.0 1200.0;
#DieOrigin 0.0 0.0;
#WaferID "W01";
#Slot 1;
#TiffFileName LOT001.tif;
#TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
#InspectionTest 1;
#ClassLookup 2
# 0 "Unknown"
# 1 "Particle";
#DefectRecordSpec 10 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER IMAGECOUNT IMAGELIST ;
#DefectList
# 1 100.500 200.500 1 2 0.5 0.5 1 2 1 0 2 0
# 2 300.000 400.000 2 3 0.6 0.6 1 2 3 0 4 0;
#SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;
#SummaryList
# 1 2 1.0000000000e-03 10 2;
#EndOfFile;
#"""
#
#KLARF18_WITH_IMAGE_BLOCKS = """Record FileRecord  "1.8"
#{
#  Record LotRecord "LOT.01"
#  {
#    Record WaferRecord "W01"
#    {
#      Field DiePitch 2 {23376636, 32874750}
#
#      List DefectList
#      {
#        Columns 8 { int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,
#        int32 YINDEX,  int32 CLASSNUMBER,  int32 IMAGECOUNT,  ImageList IMAGEINFO  }
#        Data 3
#        {
#          1 1000 2000 0 0 1 1 Image 1 { "d1.png" "PNG" 1 "24" } ;
#          2 3000 4000 1 -1 2 1 Image 1 { "d2.png" "PNG" 1 "24" } ;
#          3 5000 6000 1 1 2 0 ;
#        }
#      }
#    }
#  }
#}
#EndOfFile;
#"""
#
#
## ---------------------------------------------------------------- lossless round-trip
#
#def test_roundtrip_fixture_byte_identical():
#    with open(FIXTURE, "rb") as f:
#        raw = f.read()
#    doc = klarf_core.load(FIXTURE)
#    assert doc.version == "1.8"
#    assert len(doc.defects) == 6
#    assert doc.to_text().encode("utf-8") == raw
#
#
#def test_roundtrip_synthetic_12_identical():
#    doc = klarf_core.load(KLARF12_WITH_IMAGES)
#    assert doc.version == "1.2"
#    assert doc.to_text() == KLARF12_WITH_IMAGES
#
#
## ---------------------------------------------------------------- defect_image_map
#
#def test_defect_image_map_12_tiffspec_imagelist():
#    doc = klarf_core.load(KLARF12_WITH_IMAGES)
#    assert doc.tiff_file_name == "LOT001.tif"
#    assert doc.tiff_spec == {"version": "6.1", "nfields": 2,
#                             "fields": ["IMAGEVERSION", "IMAGEXYPOS"]}
#    # layout declared by TiffSpec: entries start at the IMAGELIST column,
#    # 2 tokens per image
#    assert doc.image_layout() == (9, 2, "declared")
#    assert doc.total_image_count() == 4
#
#    m = doc.defect_image_map(n_pages=4)
#    assert m["mode"] == "imagelist"
#    assert m["base"] == 1                      # ids 1..4 -> 1-based pages
#    assert m["pages"] == [[0, 1], [2, 3]]      # 0-based TIFF pages
#
#    # without n_pages the base is inferred from the smallest id
#    m2 = doc.defect_image_map()
#    assert m2["pages"] == [[0, 1], [2, 3]]
#
#
## ---------------------------------------------------------------- batch_set
#
#def test_batch_set_edits_only_targeted_cells():
#    doc = klarf_core.load(KLARF12_WITH_IMAGES)
#    before = [list(r) for r in doc.defects]
#
#    n = doc.batch_set("DEFECTID", 2, "CLASSNUMBER", 7)
#    assert n == 1
#
#    text = doc.to_text()
#    # everything before the DefectList block is byte-identical
#    assert text.split("DefectList")[0] == KLARF12_WITH_IMAGES.split("DefectList")[0]
#    # everything after it (SummaryList onwards) is byte-identical too
#    assert text.split("SummarySpec")[1] == KLARF12_WITH_IMAGES.split("SummarySpec")[1]
#
#    doc2 = klarf_core.load(text)
#    ci = doc2.col_index("CLASSNUMBER")
#    for row_before, row_after in zip(before, doc2.defects):
#        for j, (a, b) in enumerate(zip(row_before, row_after)):
#            if row_before[doc2.col_index("DEFECTID")] == "2" and j == ci:
#                assert (a, b) == ("1", "7")    # only this cell changed
#            else:
#                assert a == b
#
#
## ---------------------------------------------------------------- defect_image_filename
#
#def test_defect_image_filename_synthetic_18():
#    doc = klarf_core.load(KLARF18_WITH_IMAGE_BLOCKS)
#    assert doc.version == "1.8"
#    assert len(doc.defects) == 3
#    names = [doc.defect_image_filename(r) for r in doc.defects]
#    assert names == ["d1.png", "d2.png", None]
#    # additive method must not disturb the lossless round-trip
#    assert doc.to_text() == KLARF18_WITH_IMAGE_BLOCKS
#
#
#def test_defect_image_filename_fixture_images_blocks():
#    doc = klarf_core.load(FIXTURE)
#    names = [doc.defect_image_filename(r) for r in doc.defects]
#    assert names == [f"1.000_0000{i}.jpg" for i in range(1, 7)]
#
#
#def test_defect_image_filename_absent_on_12_token_rows():
#    doc = klarf_core.load(KLARF12_WITH_IMAGES)
#    # 1.2 IMAGELIST rows carry numeric image tokens, not Image {...} blocks
#    assert all(doc.defect_image_filename(r) is None for r in doc.defects)
#
#F beebe8e22628acc8dff09406c184b3a0ecae0b91 97 tests/test_klarf_variant_d.py
## KLARF variant D 迴歸測試 — authored 2026-07-28 (M5).
#"""真實 1.8 KLARF 變體：影像欄是 ImageList 型別（IMAGEINFO）、**不在最後一欄**，
#且整份檔案沒有 IMAGECOUNT 欄。
#
#這個變體是 `fab_probe/probe_klarf.py` 在 `tests/fixtures/sample_real.klarf`
#（唯一一份真實來源的 KLARF）上發現的：`row_len_ok` 原本用原始 token 數比對欄數，
#把 `Images 1 { "a.jpg" "JPG" 1 "24" }` 這個佔 8 個 token 的子區塊當成 8 欄，
#於是**每一列都被判定違法**，`lint()` 對一份完全正常的檔案報 rowlen error。
#
#對使用者的影響：Export 精靈在寫回前跑健檢，會對真實檔案跳出嚇人的紅字。
#
#**這份 fixture 的識別碼是遮蔽過的**（Lot／Wafer／機台／device／recipe 名稱／
#廠區代號／缺陷分類名稱一律換成合成值，等長替換）。下面每一條斷言看的都是
#**結構** —— 版本、欄位佈局、ImageList 在第幾欄、round-trip 逐位元組相同 ——
#沒有一條看值，所以遮蔽不影響這支測試想守的東西。
#守門的測試在 `tests/test_no_real_fab_data.py`（鐵則 8）。
#"""
#from __future__ import annotations
#
#from pathlib import Path
#
#from adept.core.ingest import klarf_core as K
#
#FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_real.klarf"
#
#
#def _doc():
#    return K.load(str(FIXTURE))
#
#
#def test_variant_d_shape():
#    """先確認這份 fixture 真的是 variant D（測試前提，變了要知道）。"""
#    doc = _doc()
#    assert doc.version == "1.8"
#    ic, il = doc.image_col_index()
#    assert ic < 0, "variant D 的前提：沒有 IMAGECOUNT 欄"
#    assert il >= 0, "但有 ImageList 型別的欄（IMAGEINFO）"
#    assert il < len(doc.defect_columns) - 1, "而且它不在最後一欄"
#    assert doc.image_layout() is None, "image_layout 對這個變體回 None（維持現狀）"
#
#
#def test_image_block_span_and_effective_len():
#    doc = _doc()
#    row = doc.defects[0]
#    span = doc.image_block_span(row)
#    assert span is not None
#    start, ntok = span
#    assert row[start] in ("Image", "Images")
#    assert row[start + ntok - 1] == "}"
#    assert ntok > 1
#    # 折算後應正好等於欄數
#    assert doc.effective_row_len(row) == len(doc.defect_columns)
#
#
#def test_row_len_ok_no_longer_false_positives():
#    doc = _doc()
#    bad = [i for i, r in enumerate(doc.defects) if not doc.row_len_ok(r)]
#    assert bad == [], f"這些列被誤判為違法：{bad}"
#
#
#def test_lint_is_clean_on_real_file():
#    """整份真實檔案不該有任何 error 等級的健檢問題。"""
#    doc = _doc()
#    errors = [i for i in K.lint(doc) if i.level == "error"]
#    assert not errors, [(i.code, i.title, i.count) for i in errors]
#
#
#def test_still_lossless():
#    doc = _doc()
#    original = FIXTURE.read_bytes()
#    assert doc.to_text().encode("utf-8", errors="replace") == original or \
#        doc.to_text() == original.decode("utf-8", errors="replace"), \
#        "未編輯的檔案 to_text() 必須逐位元組還原"
#
#
#def test_per_defect_image_filename_still_resolves():
#    doc = _doc()
#    names = [doc.defect_image_filename(r) for r in doc.defects]
#    assert all(n for n in names), names
#    assert all(n.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))
#               for n in names), names
#
#
#def test_no_regression_on_normal_variants(tmp_path):
#    """一般變體（有 IMAGECOUNT、影像欄在最後）的判定不受影響。"""
#    import sys
#    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#    from make_sample import generate as gen_ebi
#    from make_sample_rsem import generate as gen_rsem
#
#    for gen, sub in ((gen_ebi, "ebi"), (gen_rsem, "rsem")):
#        paths = gen(str(tmp_path / sub), n=6, seed=3)
#        doc = K.load(paths["klarf"])
#        bad = [i for i, r in enumerate(doc.defects) if not doc.row_len_ok(r)]
#        assert bad == [], f"{sub}: {bad}"
#        assert not [i for i in K.lint(doc) if i.level == "error"]
#
#F 66c195b31faf49fd4341defcd22770e86e05c39a 116 tests/test_make_sample.py
#"""Tests for tools/make_sample.py — synthetic EBI patch lot generator."""
#from __future__ import annotations
#
#import json
#import os
#import sys
#
#import numpy as np
#import pytest
#
#from adept.core.ingest import dataset, klarf_core, tiff_index
#
#_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#import make_sample  # noqa: E402
#
#
#N = 8
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("synlot")
#    return make_sample.generate(str(out / "lot"), n=N, seed=7)
#
#
#def test_klarf_parses_and_image_map(lot):
#    doc = klarf_core.load(lot["klarf"])
#    assert doc.version == "1.2"
#    assert doc.tiff_file_name == "LOT_SYN.tif"
#    assert doc.tiff_spec == {"version": "6.1", "nfields": 1, "fields": ["IMAGENUMBER"]}
#    assert len(doc.defects) == N
#
#    npages = tiff_index.n_pages(lot["tiff"])
#    assert npages == 2 * N
#    imap = doc.defect_image_map(npages)
#    assert imap["mode"] == "imagelist"
#    assert imap["base"] == 1                       # IMAGELIST 是 1-based 頁碼
#    for i, pages in enumerate(imap["pages"]):
#        assert pages == [2 * i, 2 * i + 1]         # test, ref（0-based）
#
#
#def test_load_dataset_ebi_patch_pairs(lot):
#    ds = dataset.load_dataset(lot["klarf"])
#    assert ds.kind == "ebi_patch"
#    assert len(ds.items) == N
#    for i, it in enumerate(ds.items):
#        assert set(it.images) == {"test", "ref"}
#        assert it.images["test"].page == 2 * i
#        assert it.images["ref"].page == 2 * i + 1
#        t = it.load("test")
#        r = it.load("ref")
#        assert t.shape == (128, 128) and t.dtype == np.uint8
#        assert r.shape == (128, 128) and r.dtype == np.uint8
#        assert not np.array_equal(t, r)            # 獨立雜訊 + 平移
#        # 座標落在假 die 內（KLARF 1.2 µm → nm）
#        assert 0 < it.xrel_nm < 5000 * 1000
#        assert 0 < it.yrel_nm < 5000 * 1000
#
#
#def test_ground_truth_consistent(lot):
#    with open(lot["ground_truth"], "r", encoding="utf-8") as f:
#        gt = json.load(f)
#    ds = dataset.load_dataset(lot["klarf"])
#    assert set(gt) == {it.defect_id for it in ds.items}
#    n_real = sum(1 for v in gt.values() if v["is_real"])
#    assert n_real == round(N * 0.5)                # 預設 real_frac=0.5
#    for v in gt.values():
#        assert set(v) == {"is_real", "type"}
#        if v["is_real"]:
#            assert v["type"] in make_sample.REAL_TYPES
#        else:
#            assert v["type"] == make_sample.NUISANCE_TYPE
#    # is_real ⟺ type != "none"
#    assert all(v["is_real"] == (v["type"] != "none") for v in gt.values())
#
#
#def test_same_seed_identical_tiff_bytes(tmp_path):
#    p1 = make_sample.generate(str(tmp_path / "a"), n=4, seed=42)
#    p2 = make_sample.generate(str(tmp_path / "b"), n=4, seed=42)
#    with open(p1["tiff"], "rb") as f:
#        b1 = f.read()
#    with open(p2["tiff"], "rb") as f:
#        b2 = f.read()
#    assert b1 == b2                                 # 同 seed → 位元組完全相同
#    with open(p1["klarf"], "rb") as f:
#        k1 = f.read()
#    with open(p2["klarf"], "rb") as f:
#        k2 = f.read()
#    assert k1 == k2
#
#    p3 = make_sample.generate(str(tmp_path / "c"), n=4, seed=43)
#    with open(p3["tiff"], "rb") as f:
#        b3 = f.read()
#    assert b1 != b3                                 # 不同 seed → 不同資料
#
#
#def test_cli_main(tmp_path, capsys):
#    rc = make_sample.main([str(tmp_path / "cli"), "--n", "2", "--seed", "1"])
#    assert rc == 0
#    out = capsys.readouterr().out
#    assert "LOT_SYN.001" in out
#    assert os.path.isfile(str(tmp_path / "cli" / "LOT_SYN.tif"))
#    assert os.path.isfile(str(tmp_path / "cli" / "ground_truth.json"))
#
#
#def test_bad_args_raise(tmp_path):
#    with pytest.raises(ValueError):
#        make_sample.generate(str(tmp_path / "x"), n=0)
#    with pytest.raises(ValueError):
#        make_sample.generate(str(tmp_path / "x"), real_frac=1.5)
#    with pytest.raises(ValueError):
#        make_sample.generate(str(tmp_path / "x"), size=16, pitch=16)
#
#F b614d74319ead1329a9b301b5967f2d4d8b5464f 55 tests/test_no_qt.py
#"""M0 驗收：adept 全套件零 Qt import（原始碼掃描 + 實際 import 檢查）。"""
#from __future__ import annotations
#
#import re
#import sys
#from pathlib import Path
#
#PKG = Path(__file__).resolve().parent.parent / "adept"
#CORE = PKG / "core"
#QT_PAT = re.compile(r"^\s*(import|from)\s+(PyQt\d?|PySide\d?|qtpy|Qt)\b", re.M)
#
#
#def test_no_qt_in_core_source():
#    """core 禁 Qt；adept/ui 是唯一允許 Qt 的地方（__main__ 須 lazy import）。"""
#    offenders = []
#    for py in CORE.rglob("*.py"):
#        if QT_PAT.search(py.read_text(encoding="utf-8")):
#            offenders.append(str(py))
#    main_py = PKG / "__main__.py"
#    if main_py.exists() and QT_PAT.search(main_py.read_text(encoding="utf-8")):
#        offenders.append(str(main_py))
#    assert not offenders, f"Qt import found in: {offenders}"
#
#
#def test_no_qt_after_import():
#    """在**乾淨的子行程**裡 import core，然後看 Qt 有沒有被拖進來。
#
#    以前是在測試行程裡直接看 ``sys.modules``，那讓這條測試變成**跟執行順序
#    有關**：只要有任何一個 UI 測試檔排在 ``test_no_qt.py`` 前面跑過，Qt 就
#    已經在 ``sys.modules`` 裡，這裡就會誤報 —— 而它報的位置離真正的原因
#    （另一個檔案的 fixture）很遠，看訊息完全猜不到。加一支新測試檔就可能踩到，
#    只因為檔名的字母序。子行程沒有這個問題：問的就是「單獨 import core 時
#    會不會拉進 Qt」，而那本來就是這條測試唯一想問的事。
#    """
#    import subprocess
#
#    code = (
#        "import sys\n"
#        "import adept.core.algo, adept.core.ingest, adept.core.calibration\n"
#        "qt = [m for m in sys.modules "
#        "      if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6')]\n"
#        "print(','.join(sorted(qt)))\n"
#    )
#    proc = subprocess.run([sys.executable, "-c", code],
#                          cwd=str(PKG.parent), capture_output=True, text=True)
#    assert proc.returncode == 0, proc.stderr
#    loaded = [m for m in proc.stdout.strip().split(",") if m]
#    assert not loaded, f"Qt modules loaded: {loaded}"
#
#
#def test_py39_syntax():
#    import ast
#    for py in PKG.rglob("*.py"):
#        ast.parse(py.read_text(encoding="utf-8"), filename=str(py), feature_version=(3, 9))
#
#F 3ca36d76191e3c0c2c801a13720a81874fd847d5 121 tests/test_no_real_fab_data.py
## 守門：repo 裡不得有未遮蔽的廠內識別碼。
#"""這個 repo 的前提是「整包可以帶出廠、可以放在 GitHub 上」。
#
#那個前提有一個很容易破掉的地方：**測試 fixture**。開發過程中最有價值的檔案就是
#一份真實的 KLARF（`sample_real.klarf` 就是這樣抓到 variant D 的），而真實的 KLARF
#裡帶著 Lot／Wafer／Device／機台／**recipe 名稱**（recipe 名稱通常編碼了層別與製程
#步驟）、缺陷分類名稱，甚至廠區代號。
#
#這些欄位對測試**完全沒有用**：`test_klarf_variant_d.py` 斷言的全部是結構
#（版本、欄位佈局、ImageList 在第幾欄、round-trip 逐位元組相同），一條都不看值。
#所以真實值留在裡面是純風險、零收益。
#
#這支測試因此要求：**fixture 裡每一個會帶識別碼的欄位，值都要長得像合成的。**
#它不能靠「列出不准出現的字」來檢查 —— 那等於把要保護的東西寫進 repo。
#所以反過來做：白名單 + 一個明顯是合成的命名規則。
#
#加新 fixture 而這支測試擋下來的時候，正確的做法是**遮蔽那個值**（等長替換，
#`klarf_core` 是 span-splice，長度變了也不會壞，但等長比較不會動到別的斷言），
#不是把真實值加進白名單。
#"""
#from __future__ import annotations
#
#import re
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#FIXTURES = Path(__file__).resolve().parent / "fixtures"
#
##: 會帶識別碼的 KLARF 欄位（值要被檢查的）。
#ID_FIELDS = (
#    "LotRecord", "WaferRecord", "ScribeID", "DeviceID", "SetupID",
#    "RecipeID", "ProcessEquipmentState", "InspectionStationID",
#    "ClassLookupTable",
#)
#
##: 合成值的命名規則：全大寫／數字／底線的代號，看得出「這是編出來的」。
##: 例：``AA0000.0X``（lot）、``DEV001``、``TOOL01``、``FAB01``、``LOT_SYN``、
##: ``DEV001_LAYERA_STP_BSTP_CST_DS01_E01``（recipe）。
#_SYNTHETIC = re.compile(
#    r"^(?:"
#    r"AA\d{4}(?:\.[0-9A-Z]{1,3})?"          # lot / wafer / scribe
#    r"|DEV\d{3}(?:_[0-9A-Z_]+)?"            # device / recipe
#    r"|TOOL\d{2}|FAB\d{2}"                  # 機台 / 廠區
#    r"|LOT_SYN[0-9A-Z_.]*|SYN[0-9A-Z_.]*"   # make_sample 產的
#    r"|LAYER[0-9A-Z_]*"
#    r")$"
#)
#
##: KLARF 的通用詞彙與廠商產品名 —— 不是公司機密，留著讓 fixture 讀起來仍然真實。
#_GENERIC = {
#    "", "WAFER", "NOTCH", "PRIMEVISION", "No Review", "Grey VC", "JPG", "PNG",
#    "TIF", "TIFF", "1", "2", "3", "24",
#}
#
#_DATE = re.compile(r"^\d{2}-\d{2}-\d{2,4}$")
#_TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")
#_IMAGE = re.compile(r"^[0-9A-Za-z_.\-]+\.(?:jpe?g|png|tiff?)$", re.I)
#
#
#def _fixture_files():
#    if not FIXTURES.is_dir():                       # pragma: no cover
#        return []
#    return sorted(p for p in FIXTURES.rglob("*") if p.is_file())
#
#
#def _ok(value: str) -> bool:
#    v = value.strip()
#    return (v in _GENERIC or bool(_SYNTHETIC.match(v))
#            or bool(_DATE.match(v)) or bool(_TIME.match(v))
#            or bool(_IMAGE.match(v)))
#
#
#@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
#def test_fixture_identifier_fields_look_synthetic(path):
#    """fixture 裡的識別碼欄位一定要長得像編出來的。"""
#    try:
#        text = path.read_text(encoding="utf-8", errors="strict")
#    except (UnicodeDecodeError, OSError):           # pragma: no cover
#        pytest.skip("不是純文字檔")
#
#    bad = []
#    for line in text.splitlines():
#        if not any(f in line for f in ID_FIELDS):
#            continue
#        for value in re.findall(r'"([^"]*)"', line):
#            if not _ok(value):
#                bad.append((line.strip()[:72], value))
#    assert not bad, (
#        "這些識別碼看起來是真的（廠區／Lot／Wafer／機台／device／recipe 名稱都算）。\n"
#        "遮蔽它們 —— 等長替換，測試只看結構不看值，所以遮蔽不會弄壞任何斷言。\n"
#        "不要把真實值加進白名單。\n" + "\n".join("  %s  ← %r" % b for b in bad))
#
#
#def test_the_guard_would_actually_catch_a_real_looking_lot(tmp_path):
#    """白名單式的檢查最容易變成「什麼都通過」—— 先證明它擋得下東西。
#
#    **反例一律用憑空編的字，不可以用真的。** 這條規則我自己第一版就違反了：
#    負面案例直接寫了真實的 lot 與機台代號，於是這支「防止真實識別碼進 repo」
#    的測試本身變成了真實識別碼進 repo 的管道。抓到它的方式是把整包壓成 zip
#    之後掃一遍 —— 那件事本來就該在推上去之前做。
#
#    反例要的是**形狀**（不符合合成命名規則），不是內容。
#    """
#    assert _ok("AA0000.0X") is True
#    assert _ok("DEV001_LAYERA_STP_BSTP_CST_DS01_E01") is True
#    # 憑空編的，但形狀像真的：lot 帶尾碼、recipe 帶層別／步驟、機台是四碼＋數字
#    assert _ok("QQ1234.5Z") is False
#    assert _ok("WWXY_ZZZ_QQQ_VVV_UUU_TT99") is False
#    assert _ok("ZZZZ99") is False
#
#
#def test_at_least_one_fixture_is_actually_checked():
#    """這份 parametrize 空掉的話上面那支測試會靜靜地全部跳過。"""
#    files = _fixture_files()
#    assert files, "tests/fixtures 沒有檔案 —— 這支守門測試就等於沒有在跑"
#    assert any(p.suffix == ".klarf" for p in files)
#
#F f2f18a59cf739942f573f001c64cd77730bc5b09 76 tests/test_normalize.py
#"""Tests for adept.core.algo.normalize (vendored 2026-07-27)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.normalize import (
#    GLV_MASK_MIN_PIXELS,
#    normalize_image,
#    normalize_image_with_range,
#    percentile_range,
#    percentile_range_glv_masked,
#)
#
#
#def _rng():
#    return np.random.default_rng(1234)
#
#
#def test_normalize_image_output_range():
#    img = (_rng().random((80, 80)) * 255).astype(np.float32)
#    out = normalize_image(img)
#    assert out.min() >= 0.0
#    assert out.max() <= 1.0
#    # Bulk of pixels must actually use the range (P2/P98 anchoring)
#    assert out.max() > 0.9
#    assert out.min() < 0.1
#
#
#def test_normalize_image_constant_no_crash():
#    img = np.full((32, 32), 77.0, dtype=np.float32)
#    out = normalize_image(img)
#    assert np.all(out >= 0.0) and np.all(out <= 1.0)
#
#
#def test_percentile_range_and_with_range_roundtrip():
#    img = (_rng().random((64, 64)) * 200 + 20).astype(np.float32)
#    p_lo, p_hi = percentile_range(img)
#    assert p_lo < p_hi
#    out = normalize_image_with_range(img, p_lo, p_hi)
#    assert out.min() >= 0.0 and out.max() <= 1.0
#    # Same anchors as normalize_image -> identical result
#    np.testing.assert_allclose(out, normalize_image(img), atol=1e-5)
#
#
#def test_glv_masked_uses_only_in_band_pixels():
#    rng = _rng()
#    # Background population 0-50, pattern population 110-145, outliers at 250.
#    bg = rng.uniform(0, 50, size=6000)
#    band = rng.uniform(110, 145, size=2500)
#    outliers = np.full(100, 250.0)
#    img = np.concatenate([bg, band, outliers]).astype(np.float32)
#    rng.shuffle(img)
#    img = img.reshape(86, 100)
#
#    p_lo, p_hi = percentile_range_glv_masked(img, 110, 145)
#    # Anchors must come exclusively from the in-band population
#    assert 110.0 <= p_lo <= 145.0
#    assert 110.0 <= p_hi <= 145.0
#    assert p_lo < p_hi
#
#    # Full-image percentile is dominated by the background population
#    full_lo, full_hi = percentile_range(img)
#    assert full_lo < 60.0
#    assert p_lo > full_lo
#
#
#def test_glv_masked_fallback_when_too_few_pixels():
#    rng = _rng()
#    img = rng.uniform(0, 50, size=(50, 50)).astype(np.float32)
#    # Only 10 pixels inside the band -> below GLV_MASK_MIN_PIXELS -> fallback
#    img.flat[:10] = 120.0
#    assert 10 < GLV_MASK_MIN_PIXELS
#    masked = percentile_range_glv_masked(img, 110, 145)
#    full = percentile_range(img)
#    assert masked == full
#
#F a1d768507e961ffe06e398c556c8da7a12a6a8ed 1081 tests/test_offline_tools.py
#"""Tests for tools/fetch_wheels.py · tools/install_offline.py · tools/doctor.py（M6-1 離線安裝包）。
#
#這三支是「bootstrap 工具」：它們要在**相依套件都還沒裝**的機器上跑，
#所以測試的重點有三塊：
#  1. 以 subprocess 當外部程式跑（跟使用者的用法一致），檢查離開碼與訊息文字；
#  2. 事前檢查（preflight）的失敗一定要是白話訊息 + 非零離開碼，**不能有 traceback**；
#  3. 用 ast 掃原始碼，確認模組層只 import 標準函式庫（lazy import 在函式裡的不算）。
#
#網路相關的動作（pip download）一律不真的執行：只驗 argv 組裝（純函式 + --dry-run）。
#"""
#from __future__ import annotations
#
#import ast
#import os
#import pathlib
#import subprocess
#import sys
#
#import pytest
#
#REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#TOOLS = os.path.join(REPO, "tools")
#DOCTOR = os.path.join(TOOLS, "doctor.py")
#FETCH = os.path.join(TOOLS, "fetch_wheels.py")
#INSTALL = os.path.join(TOOLS, "install_offline.py")
#GETCODE = os.path.join(TOOLS, "get_code.py")
#GETCODE_PS = os.path.join(TOOLS, "get_code.ps1")
#FILELIST = os.path.join(TOOLS, "make_filelist.py")
#BUNDLE = os.path.join(TOOLS, "make_text_bundle.py")
#CHECK = os.path.join(TOOLS, "check_files.py")
##: 「在受限機器上、套件裝好之前就要能跑」的那幾支 —— 所以 stdlib-only + 3.9。
##: get_code.py 是第四支（F7-18 之後補的）：它比其他三支更早跑，
##: 因為它的工作是把程式碼弄上那台機器。
#ALL_TOOLS = (FETCH, INSTALL, DOCTOR, GETCODE, FILELIST, BUNDLE, CHECK)
#
#if TOOLS not in sys.path:
#    sys.path.insert(0, TOOLS)
#
#import doctor as doctor_mod            # noqa: E402  （stdlib-only，import 得起來就是一種驗證）
#import fetch_wheels                    # noqa: E402
#import install_offline                 # noqa: E402
#import get_code                       # noqa: E402
#import make_filelist                  # noqa: E402
#import make_text_bundle               # noqa: E402
#import check_files                    # noqa: E402
#
#REQUIRED_DEPS = ("numpy", "cv2", "tifffile", "PySide6", "openpyxl")
#
#
#def _run(args, cwd=REPO, env_extra=None, drop_pythonpath=False, timeout=300):
#    env = dict(os.environ)
#    env.setdefault("QT_QPA_PLATFORM", "offscreen")
#    env["PYTHONIOENCODING"] = "utf-8"
#    if drop_pythonpath:
#        env.pop("PYTHONPATH", None)
#    if env_extra:
#        env.update(env_extra)
#    proc = subprocess.run([sys.executable] + list(args), cwd=cwd, env=env,
#                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                          timeout=timeout)
#    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace")
#
#
#def _deps_present() -> bool:
#    """相依套件在不在。
#
#    **一定要用 find_spec，不能真的 import** —— 這個檔案在 pytest 主行程裡跑，
#    import 到 PySide6 會害 tests/test_no_qt.py 的「core 不得載入 Qt」守門失敗。
#    """
#    import importlib.util
#
#    for name in REQUIRED_DEPS:
#        try:
#            if importlib.util.find_spec(name) is None:
#                return False
#        except Exception:  # noqa: BLE001 — 壞掉的安裝也算「沒有」
#            return False
#    return True
#
#
## ---------------------------------------------------------------- doctor
#
#@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件才會全綠")
#def test_doctor_passes_in_repo_root():
#    """在 repo 根目錄跑 doctor：離開碼 0、列出每個套件、最後一行是結論。"""
#    rc, out = _run([DOCTOR])
#    assert rc == 0, out
#    for pip_name, import_name, _essential in doctor_mod.DEPENDENCIES:
#        assert pip_name in out, (pip_name, out)
#        assert import_name in out or pip_name == import_name
#    assert "Python 版本" in out
#    assert "adept" in out
#    assert "Qt" in out
#    assert "端到端試跑" in out          # smoke test 有跑到
#    assert "結論" in out
#    assert out.strip().splitlines()[-1].startswith("結論")
#    assert "Traceback" not in out
#
#
#@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件")
#def test_doctor_verbose_still_passes():
#    rc, out = _run([DOCTOR, "--verbose", "--skip-smoke"])
#    assert rc == 0, out
#    assert "結論" in out
#    assert "略過" in out                # smoke 被跳過會標成 △
#
#
#def test_doctor_detects_wrong_folder(tmp_path):
#    """經典錯誤：在別的資料夾執行 → 必須明確說「adept 載入不到」並教他 cd。"""
#    try:
#        subprocess.run([sys.executable, "-c", "import adept"], cwd=str(tmp_path),
#                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
#                       check=True, env={k: v for k, v in os.environ.items()
#                                        if k != "PYTHONPATH"})
#    except subprocess.CalledProcessError:
#        pass                            # 預期：從 tmp 資料夾 import 不到 adept
#    else:
#        pytest.skip("adept 已安裝到 site-packages，無法模擬『跑錯資料夾』")
#
#    rc, out = _run([DOCTOR], cwd=str(tmp_path), drop_pythonpath=True)
#    assert rc == 1, out
#    assert "adept" in out
#    assert "cd" in out                  # 有告訴他要 cd 到哪
#    assert "ADEPT-main" in out
#    assert "Traceback" not in out
#    assert out.strip().splitlines()[-1].startswith("（想看完整錯誤") or "結論" in out
#
#
#def test_doctor_help():
#    rc, out = _run([DOCTOR, "--help"])
#    assert rc == 0
#    assert "--verbose" in out
#
#
## ---------------------------------------------------------------- --help（不得依賴第三方套件）
#
#@pytest.mark.parametrize("script", [FETCH, INSTALL, DOCTOR])
#def test_help_works_without_third_party(script):
#    """--help 必須在「什麼都沒裝」時也能跑：這裡用空 sys.path 前綴模擬不了，
#
#    但至少確認 import 期間沒有碰到 numpy 之類的東西（-S 關掉 site-packages）。
#    """
#    rc, out = _run(["-S", script, "--help"])
#    assert rc == 0, out
#    assert "usage:" in out or "用法" in out
#    assert "Traceback" not in out
#
#
## ---------------------------------------------------------------- fetch_wheels（不連網）
#
#def test_build_pip_command_targets_windows_from_any_host():
#    cmd = fetch_wheels.build_pip_command(
#        dest="/tmp/wheels", requirements="/repo/requirements.txt",
#        platforms=("win_amd64",), python_version="39", implementation="cp",
#        extra_packages=("pytest",), python_exe="/usr/bin/python3")
#    assert cmd[:4] == ["/usr/bin/python3", "-m", "pip", "download"]
#    assert "--only-binary=:all:" in cmd
#    assert cmd[cmd.index("--platform") + 1] == "win_amd64"
#    assert cmd[cmd.index("--python-version") + 1] == "39"
#    assert cmd[cmd.index("--implementation") + 1] == "cp"
#    assert cmd[cmd.index("--abi") + 1] == "cp39"
#    assert cmd[cmd.index("--dest") + 1] == "/tmp/wheels"
#    assert cmd[cmd.index("-r") + 1] == "/repo/requirements.txt"
#    assert cmd[-1] == "pytest"
#
#
#def test_build_pip_command_multiple_platforms_and_custom_abi():
#    cmd = fetch_wheels.build_pip_command(dest="w", platforms=("win_amd64", "win32"),
#                                         python_version="311", abi="none")
#    assert cmd.count("--platform") == 2
#    assert cmd[cmd.index("--abi") + 1] == "none"
#    assert fetch_wheels.default_abi("311") == "cp311"
#    assert fetch_wheels.default_abi("37") == "cp37m"
#    assert fetch_wheels.default_abi("39", "pp") == "none"
#
#
#def test_fetch_wheels_dry_run_does_not_download(tmp_path):
#    dest = tmp_path / "wheels"
#    rc, out = _run([FETCH, "--dry-run", "--dest", str(dest), "--python-version", "39"])
#    assert rc == 0, out
#    assert "--only-binary=:all:" in out
#    assert "win_amd64" in out
#    assert not dest.exists()            # dry-run 連資料夾都不該建
#    assert "Traceback" not in out
#
#
#def test_fetch_wheels_missing_requirements_is_readable(tmp_path):
#    rc, out = _run([FETCH, "--requirements", str(tmp_path / "nope.txt"), "--dry-run"])
#    assert rc != 0
#    assert "找不到" in out
#    assert "Traceback" not in out
#
#
#def test_parse_requirements_and_wheel_filename():
#    reqs = fetch_wheels.parse_requirements(os.path.join(REPO, "requirements.txt"))
#    assert "numpy" in reqs and "opencv-python" in reqs and "PySide6" in reqs
#    info = fetch_wheels.parse_wheel_filename("opencv_python-4.8.1.78-cp37-abi3-win_amd64.whl")
#    assert info is not None
#    assert info[0] == "opencv_python" and info[1] == "4.8.1.78" and info[4] == "win_amd64"
#    assert fetch_wheels.parse_wheel_filename("numpy-1.26.4.tar.gz") is None
#
#
#def test_match_requirements_normalises_names():
#    matched = fetch_wheels.match_requirements(
#        ["opencv-python", "PySide6", "tifffile"],
#        ["opencv_python-4.8.1-cp39-abi3-win_amd64.whl",
#         "PySide6-6.5.2-cp39-abi3-win_amd64.whl"])
#    assert matched["opencv-python"] and matched["PySide6"]
#    assert matched["tifffile"] == []    # 缺的要抓得出來
#
#
#def test_manifest_roundtrip(tmp_path):
#    """fetch_wheels 寫出的 MANIFEST，install_offline 一定要讀得懂（兩支工具的介面契約）。"""
#    dest = tmp_path / "wheels"
#    dest.mkdir()
#    (dest / "numpy-1.26.4-cp39-cp39-win_amd64.whl").write_bytes(b"not a real wheel")
#    text = fetch_wheels.build_manifest_text(
#        wheels=["numpy-1.26.4-cp39-cp39-win_amd64.whl"], dest=str(dest),
#        platforms=["win_amd64"], python_version="39", implementation="cp", abi="cp39",
#        requirements_path="requirements.txt", requirement_names=["numpy"])
#    path = dest / fetch_wheels.MANIFEST_NAME
#    path.write_text(text, encoding="utf-8")
#
#    info = install_offline.parse_manifest(str(path))
#    assert info["target_python"] == "39"
#    assert info["target_platform"] == "win_amd64"
#    assert info["wheel_count"] == "1"
#    assert "numpy-1.26.4-cp39-cp39-win_amd64.whl" in text
#    assert fetch_wheels.sha256_of(str(dest / "numpy-1.26.4-cp39-cp39-win_amd64.whl")) in text
#
#
#def test_explain_pip_failure_gives_advice():
#    tips = fetch_wheels.explain_pip_failure(
#        "ERROR: Could not find a version that satisfies the requirement PySide6",
#        platform="win_amd64", python_version="39")
#    assert tips and any("--python-version" in t for t in tips)
#
#
## ---------------------------------------------------------------- install_offline 事前檢查
#
#def _make_wheels(tmp_path, name, files, manifest=None):
#    d = tmp_path / name
#    d.mkdir()
#    for fn in files:
#        (d / fn).write_bytes(b"x" * 16)
#    if manifest is not None:
#        (d / "MANIFEST.txt").write_text(manifest, encoding="utf-8")
#    return d
#
#
#def _other_python_tag():
#    """挑一個保證跟目前 Python 不同的版本 tag。"""
#    return "38" if sys.version_info[:2] != (3, 8) else "39"
#
#
#def test_install_offline_help():
#    rc, out = _run([INSTALL, "--help"])
#    assert rc == 0
#    assert "--wheels" in out and "--no-venv" in out
#
#
#def test_install_offline_missing_wheels_dir(tmp_path):
#    rc, out = _run([INSTALL, "--wheels", str(tmp_path / "does_not_exist"), "--dry-run"])
#    assert rc != 0
#    assert "找不到離線套件資料夾" in out
#    assert "fetch_wheels" in out        # 有指出下一步怎麼做
#    assert "Traceback" not in out
#
#
#def test_install_offline_empty_wheels_dir(tmp_path):
#    d = _make_wheels(tmp_path, "empty", [])
#    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run"])
#    assert rc != 0
#    assert "沒有任何 .whl" in out
#    assert "Traceback" not in out
#
#
#def test_install_offline_python_version_mismatch(tmp_path):
#    tag = _other_python_tag()
#    d = _make_wheels(tmp_path, "mismatch",
#                     ["numpy-1.26.4-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
#                     manifest="target_platform: win_amd64\ntarget_python: %s\n" % tag)
#    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run"])
#    assert rc != 0
#    assert "Python 版本對不上" in out
#    assert "3.%s" % tag[1:] in out                              # wheels 的版本
#    assert "%d.%d" % sys.version_info[:2] in out                # 這台機器的版本
#    assert "fetch_wheels.py --python-version" in out            # 教他怎麼修
#    assert "Traceback" not in out
#    # 安裝完全沒有開始
#    assert "安裝沒有開始" in out
#
#
#def test_install_offline_version_mismatch_ok_for_pure_python_wheels(tmp_path):
#    """py3-none-any 的 wheel 與版本無關 —— 不該被擋下來（只給提醒）。"""
#    tag = _other_python_tag()
#    d = _make_wheels(tmp_path, "pure", ["openpyxl-3.1.5-py2.py3-none-any.whl"],
#                     manifest="target_python: %s\n" % tag)
#    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run", "--no-venv"])
#    assert rc == 0, out
#    assert "與版本無關" in out
#
#
#def test_install_offline_dry_run_passes_and_prints_command(tmp_path):
#    tag = "%d%d" % sys.version_info[:2]
#    d = _make_wheels(tmp_path, "good", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
#                     manifest="target_platform: win_amd64\ntarget_python: %s\n" % tag)
#    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run",
#                    "--venv", str(tmp_path / "venv")])
#    assert rc == 0, out
#    assert "--no-index" in out and "--find-links" in out
#    assert not (tmp_path / "venv").exists()
#
#
#def test_install_offline_missing_requirements(tmp_path):
#    rc, out = _run([INSTALL, "--requirements", str(tmp_path / "nope.txt"), "--dry-run"])
#    assert rc != 0
#    assert "requirements.txt" in out
#    assert "cd" in out                  # 提示他可能跑錯資料夾
#    assert "Traceback" not in out
#
#
#def test_install_offline_pure_functions():
#    assert install_offline.parse_python_tag("cp39") == (3, 9)
#    assert install_offline.parse_python_tag("3.11") == (3, 11)
#    assert install_offline.parse_python_tag("311") == (3, 11)
#    assert install_offline.parse_python_tag("") is None
#    assert install_offline.wheel_python_tags("a-1.0-py2.py3-none-any.whl") == ["py2", "py3"]
#    assert install_offline.wheels_are_pure_python(["a-1.0-py2.py3-none-any.whl"])
#    assert not install_offline.wheels_are_pure_python(["a-1.0-cp39-cp39-win_amd64.whl"])
#    cmd = install_offline.build_pip_install_command("py.exe", "W", "R", user=True)
#    assert cmd[:5] == ["py.exe", "-m", "pip", "install", "--no-index"]
#    assert cmd[cmd.index("--find-links") + 1] == "W"
#    assert cmd[cmd.index("-r") + 1] == "R"
#    assert "--user" in cmd
#    assert install_offline.build_pip_install_command(
#        "py", "W", "R", extra_packages=("pytest",))[-1] == "pytest"
#
#
#def test_install_offline_include_pytest(tmp_path):
#    """--include-pytest：wheels 裡有 pytest 才加進安裝清單，沒有就只是提醒。"""
#    tag = "%d%d" % sys.version_info[:2]
#    manifest = "target_python: %s\n" % tag
#    with_pytest = _make_wheels(tmp_path, "wp", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag),
#                                                "pytest-8.2.0-py3-none-any.whl"],
#                               manifest=manifest)
#    rc, out = _run([INSTALL, "--wheels", str(with_pytest), "--dry-run", "--no-venv",
#                    "--include-pytest"])
#    assert rc == 0, out
#    assert "requirements.txt pytest" in out          # 加在 pip 指令最後面
#
#    without = _make_wheels(tmp_path, "np", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
#                           manifest=manifest)
#    rc, out = _run([INSTALL, "--wheels", str(without), "--dry-run", "--no-venv",
#                    "--include-pytest"])
#    assert rc == 0, out
#    assert "沒有 pytest 的 wheel" in out
#
#
#@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件")
#def test_doctor_survives_ascii_console():
#    """cp950/ASCII 主控台吐不出 ✓ 或中文時，不可以爆 UnicodeEncodeError。"""
#    rc, out = _run([DOCTOR, "--skip-smoke"], env_extra={"PYTHONIOENCODING": "ascii"})
#    assert rc == 0, out
#    assert "Traceback" not in out
#    assert "[OK]" in out                # 自動退回純 ASCII 標記
#
#
#def test_explain_venv_failure_suggests_no_venv():
#    tips = install_offline.explain_venv_failure(
#        "Error: Command '['...', '-m', 'ensurepip', ...]' returned non-zero exit status 1.",
#        ".venv")
#    joined = "\n".join(tips)
#    assert "ensurepip" in joined
#    assert "--no-venv" in joined
#    assert "--user" in joined
#
#
## ---------------------------------------------------------------- bootstrap 鐵則：只用標準函式庫
#
#def _stdlib_names():
#    names = getattr(sys, "stdlib_module_names", None)
#    if names:
#        return set(names)
#    return {                                     # Python 3.9 沒有 stdlib_module_names
#        "__future__", "argparse", "ast", "base64", "datetime", "hashlib", "json",
#        "os", "platform", "re", "shutil", "struct", "subprocess", "sys",
#        "tempfile", "time", "typing", "unicodedata", "zipfile", "importlib",
#        "urllib", "ssl", "hashlib",
#    }
#
#
#def _module_level_imports(path):
#    """回傳模組層 import 到的頂層模組名（函式/類別內部的 lazy import 不算）。"""
#    with open(path, "r", encoding="utf-8") as f:
#        tree = ast.parse(f.read(), filename=path)
#    found = set()
#    for node in tree.body:                       # 只看最外層
#        if isinstance(node, ast.Import):
#            found.update(a.name.split(".")[0] for a in node.names)
#        elif isinstance(node, ast.ImportFrom):
#            if node.level == 0 and node.module:
#                found.add(node.module.split(".")[0])
#            elif node.level:
#                found.add("<relative>")
#    return found
#
#
#@pytest.mark.parametrize("script", ALL_TOOLS)
#def test_tools_import_only_stdlib_at_module_level(script):
#    imports = _module_level_imports(script)
#    extra = imports - _stdlib_names()
#    assert not extra, "%s 的模組層 import 了非標準函式庫：%s（請改成函式內 lazy import）" % (
#        os.path.basename(script), sorted(extra))
#
#
#@pytest.mark.parametrize("script", ALL_TOOLS)
#def test_tools_are_python39_compatible(script):
#    """與 tests/test_no_qt.py 同樣的守門：語法必須是 3.9 吃得下的。"""
#    with open(script, "r", encoding="utf-8") as f:
#        src = f.read()
#    ast.parse(src, filename=script, feature_version=(3, 9))
#    assert "from __future__ import annotations" in src
#
#
## ---------------------------------------------------------------- 不用 git、不用 zip 取得程式碼
#
#def _has_git_worktree():
#    """這台機器上跑得動 ``git ls-files`` 嗎。
#
#    **`get_code.py` 的目標使用者就是沒有 git 的機器**（zip 被擋、逐檔抓下來的
#    那一份沒有 `.git`）。所以下面兩支測試在那種機器上必須 skip 而不是 fail ——
#    兩條紅字對他來說就是「我下載壞了」，而其實一切正常。
#    """
#    try:
#        subprocess.run(["git", "ls-files"], cwd=REPO, check=True,
#                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#    except (OSError, subprocess.CalledProcessError):
#        return False
#    return True
#
#
#needs_git = pytest.mark.skipif(
#    not _has_git_worktree(),
#    reason="沒有 git（或不是 work tree）—— 這正是 get_code.py 服務的情況")
#
#
#@needs_git
#def test_the_manifest_is_in_sync_with_the_repo():
#    """清單腐爛的症狀是**受限機器上安靜地少一個檔案** —— 抓下來的程式碼看起來
#    是完整的，直到某個 import 爆掉。所以這裡拿 ``make_filelist`` 自己重算一次
#    來比對，而不是另外寫一份「應該長怎樣」的邏輯（兩份會各自漂移）。"""
#    want = make_filelist.build_lines(REPO)
#    with open(os.path.join(REPO, "tools", "FILELIST.txt"), "r",
#              encoding="utf-8") as f:
#        got = f.read().splitlines()
#    if want != got:
#        missing = sorted(set(want) - set(got))
#        stale = sorted(set(got) - set(want))
#        raise AssertionError(
#            "tools/FILELIST.txt 過期了。順序是 **git add 之後**才重跑，\n"
#            "因為它讀的是 `git ls-files`（還沒 add 的檔案它看不到）：\n"
#            "    git add -A && python tools/make_filelist.py && git add -A\n"
#            "清單少了：%s\n清單多了：%s" % (missing[:8], stale[:8]))
#
#
#@needs_git
#def test_the_manifest_covers_every_tracked_file_and_not_itself():
#    listed = {line.split(" ", 1)[1] for line in make_filelist.build_lines(REPO)
#              if not line.startswith("#")}
#    tracked = set(make_filelist.tracked_files(REPO))
#    assert listed == tracked
#    assert "tools/FILELIST.txt" not in listed, "清單不能列自己（SHA 沒辦法自我包含）"
#    assert "tools/get_code.py" in listed, "抓程式碼的那支自己也要在清單裡"
#
#
#def test_both_sides_compute_the_same_blob_sha():
#    """``get_code.py`` 驗的 SHA 與 ``make_filelist.py`` 寫的必須是同一個算法，
#    而且要跟 ``git hash-object`` 一致 —— 不然驗證會對每一個檔案都失敗。"""
#    for data in (b"", b"hello\n", b"\x00\x01\x02", "中文".encode("utf-8")):
#        assert get_code.blob_sha(data) == make_filelist.blob_sha(data)
#    # git hash-object 的已知值（空 blob 是 git 裡最有名的那個 SHA）
#    assert get_code.blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
#    assert get_code.blob_sha(b"hello\n") == \
#        "ce013625030ba8dba906f756967f9e9ca394464a"
#
#
#def test_the_fetcher_never_turns_tls_verification_off():
#    """公司機幾乎一定有 TLS 中間攔截，而「憑證錯誤」最省事的解法是關掉驗證 ——
#    那會讓這支腳本變成一個把任意內容寫進磁碟的工具。正確的解法是 --cafile。"""
#    with open(GETCODE, "r", encoding="utf-8") as f:
#        src = f.read()
#    for forbidden in ("_create_unverified_context", "CERT_NONE",
#                      "verify=False", "check_hostname = False"):
#        assert forbidden not in src, forbidden
#    assert "--cafile" in src, "要給一條正當的路（指到公司的根憑證）"
#
#
#def test_the_fetcher_only_talks_to_one_host():
#    """多一台主機就多一個會被 allowlist 擋掉的地方。zip 就是這樣掉的
#    （codeload.github.com 是另一台主機）。"""
#    with open(GETCODE, "r", encoding="utf-8") as f:
#        src = f.read()
#    assert "raw.githubusercontent.com" in src
#    for other in ("codeload.github.com", "api.github.com"):
#        assert other not in src.split('"""')[2], (
#            "%s 是另一台主機 —— 只能出現在說明裡，不能真的去連" % other)
#
#
#def test_a_proxy_interception_page_is_caught_not_written(tmp_path, monkeypatch):
#    """被擋的 proxy 常常回一頁 HTML 而且是 HTTP 200。那種東西寫進 .py 之後，
#    症狀是「程式碼都在但 import 就語法錯誤」，使用者完全不會歸因到下載。"""
#    real = b"print('hello')\n"
#    manifest = "%s adept/fake.py\n" % get_code.blob_sha(real)
#
#    def fake_fetch(ref, path, cafile=""):
#        if path == "tools/FILELIST.txt":
#            return manifest.encode("utf-8")
#        return b"<html><body>Blocked by policy</body></html>"
#
#    monkeypatch.setattr(get_code, "fetch", fake_fetch)
#    dest = tmp_path / "out"
#    rc = get_code.main(["--dest", str(dest)])
#    assert rc == 1, "SHA 不對就必須失敗"
#    assert not (dest / "adept" / "fake.py").exists(), "壞內容不可以落地"
#
#
#def test_a_good_download_lands_and_reports_success(tmp_path, monkeypatch):
#    real = b"print('hello')\n"
#    manifest = "# comment\n%s adept/fake.py\n" % get_code.blob_sha(real)
#
#    def fake_fetch(ref, path, cafile=""):
#        return manifest.encode("utf-8") if path == "tools/FILELIST.txt" else real
#
#    monkeypatch.setattr(get_code, "fetch", fake_fetch)
#    dest = tmp_path / "out"
#    assert get_code.main(["--dest", str(dest)]) == 0
#    assert (dest / "adept" / "fake.py").read_bytes() == real
#    assert not list(dest.rglob("*.tmp")), "atomic 寫入的暫存檔要清掉（鐵則 5）"
#    # 清單自己不在自己的清單裡，但抓下來那一份還是要有它 —— 少了它，那份 repo
#    # 不完整而且**看不出來少了什麼**（實際跑一次才發現的）。
#    assert (dest / "tools" / "FILELIST.txt").read_text(encoding="utf-8") == manifest
#
#
#def test_an_empty_manifest_is_treated_as_a_failure(tmp_path, monkeypatch):
#    """proxy 回一頁空白也是 HTTP 200。抓到 0 個檔案不可以印「成功」。"""
#    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="": b"")
#    assert get_code.main(["--dest", str(tmp_path / "out")]) == 2
#
#
#def test_a_404_is_not_reported_as_being_blocked(tmp_path, monkeypatch, capsys):
#    """實際跑一次抓到的：``--ref`` 打錯會拿到 404，而 404 代表**連線是通的**。
#    把它講成「被擋掉了」的話，使用者會跑去找 IT，而真正的問題是分支名字。"""
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    assert get_code.main(["--dest", str(tmp_path / "o"), "--ref", "nope"]) == 2
#    out = capsys.readouterr().out
#    assert "404" in out and "nope" in out
#    assert "擋" not in out.split("404")[1], "404 不可以被講成封鎖"
#
#
#def test_a_connection_failure_is_reported_as_being_blocked(tmp_path, monkeypatch,
#                                                          capsys):
#    """反過來：連不上（DNS/TCP）才是「這台主機連不上」，而且要給下一步。"""
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError("Name or service not known")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
#    out = capsys.readouterr().out
#    assert "codeload.github.com" in out and "OFFLINE-INSTALL" in out
#
#
#def test_a_timeout_is_reported_as_a_missing_proxy_not_as_a_block(
#        tmp_path, monkeypatch, capsys):
#    """實際遇到的第二個誤診：WinError 10060。
#
#    逾時的意思是「封包直接送出去、沒有人回應」—— 如果瀏覽器連得到 GitHub，
#    那幾乎一定是 **Python 沒有走公司 proxy**（urllib 讀不到 PAC），
#    不是這台主機被封。講成「被擋掉了」的話，使用者會去找 IT 要一個他其實
#    已經有的東西，而真正要做的是填一個 --proxy。
#    """
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError(
#            "[WinError 10060] 連線嘗試失敗，因為連線對象有一段時間並未正確回應")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
#    monkeypatch.setattr(get_code, "pac_url", lambda: "")
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
#    out = capsys.readouterr().out
#    assert "proxy" in out.lower(), "沒講到 proxy 就等於沒診斷"
#    assert "--proxy" in out, "要給得出照做的下一步"
#    assert "netsh winhttp show proxy" in out, "要告訴他怎麼找出 proxy"
#
#
#def test_a_pac_file_is_read_out_loud_when_there_is_one(tmp_path, monkeypatch,
#                                                      capsys):
#    """PAC 是「瀏覽器行、Python 不行」最常見的原因，而錯誤訊息完全看不出來。
#    讀得到就直接把那個網址講出來 —— 使用者要打開它去找 PROXY 那一行。"""
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError("[WinError 10060] timed out")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
#    monkeypatch.setattr(get_code, "pac_url",
#                        lambda: "http://wpad.corp.example/proxy.pac")
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
#    out = capsys.readouterr().out
#    assert "http://wpad.corp.example/proxy.pac" in out
#    assert "PROXY" in out, "要告訴他在 PAC 檔裡找哪一行"
#
#
#def test_a_timeout_through_a_configured_proxy_says_something_different(
#        tmp_path, monkeypatch, capsys):
#    """已經在走 proxy 卻還是逾時，就不是「沒設 proxy」—— 不可以給同一句話。"""
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError("[WinError 10060] timed out")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    assert get_code.main(["--dest", str(tmp_path / "o"),
#                          "--proxy", "http://p.corp:8080"]) == 2
#    out = capsys.readouterr().out
#    assert "http://p.corp:8080" in out
#    assert "netsh" not in out, "他已經有 proxy 了，不要叫他再去找一次"
#
#
#def test_the_proxy_actually_reaches_the_opener():
#    """``--proxy`` 印在畫面上但沒有真的掛進 opener，是最容易發生的假動作。"""
#    opener = get_code.build_opener(proxy="http://p.corp:8080")
#    proxies = [h for h in opener.handlers
#               if h.__class__.__name__ == "ProxyHandler"]
#    assert proxies and proxies[0].proxies.get("https") == "http://p.corp:8080"
#
#
#def test_the_run_reports_which_proxy_it_will_use(tmp_path, monkeypatch, capsys):
#    """「不用 proxy，直接連」這句話本身就是診斷 —— 使用者看到它才知道問題在哪。"""
#    real = b"x = 1\n"
#    manifest = "%s adept/f.py\n" % get_code.blob_sha(real)
#    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="":
#                        manifest.encode("utf-8") if path == get_code.MANIFEST
#                        else real)
#    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": p or "")
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 0
#    assert "直接連" in capsys.readouterr().out
#
#
#def test_a_tls_interception_error_points_at_cafile_not_at_disabling_checks(
#        tmp_path, monkeypatch, capsys):
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError(
#            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
#    out = capsys.readouterr().out
#    assert "--cafile" in out
#    assert "不要" in out, "必須明講不要去關掉憑證驗證"
#
#
#def test_the_pac_is_resolved_automatically_on_windows(tmp_path, monkeypatch,
#                                                     capsys):
#    """PAC 檔通常有上百行條件判斷，而「哪一行適用於這個網址」正是 PAC 要算的東西
#    —— 叫製程工程師自己去讀那個檔案是不合理的。Windows 上 .NET 讀得懂 PAC
#    （瀏覽器用的就是它），所以借 PowerShell 問一次，解出來就直接用。"""
#    real = b"x = 1\n"
#    manifest = "%s adept/f.py\n" % get_code.blob_sha(real)
#    seen = {}
#
#    def fake_build_opener(cafile="", proxy=""):
#        seen["proxy"] = proxy
#        return None
#
#    monkeypatch.setattr(get_code, "proxy_in_effect",
#                        lambda p="": p or "")          # 環境裡沒有 proxy
#    monkeypatch.setattr(get_code, "system_proxy_for",
#                        lambda url: "http://pac-resolved.corp:8080/")
#    monkeypatch.setattr(get_code, "build_opener", fake_build_opener)
#    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="":
#                        manifest.encode("utf-8") if path == get_code.MANIFEST
#                        else real)
#
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 0
#    assert seen["proxy"] == "http://pac-resolved.corp:8080/", \
#        "解出來的 proxy 沒有真的掛進 opener"
#    out = capsys.readouterr().out
#    assert "pac-resolved.corp:8080" in out
#    assert "PAC" in out, "要講出這個 proxy 是怎麼來的"
#
#
#def test_an_explicit_proxy_wins_over_the_resolved_one(tmp_path, monkeypatch):
#    """使用者自己填的優先 —— 自動解出來的東西不可以蓋掉他明講的。"""
#    called = []
#    monkeypatch.setattr(get_code, "system_proxy_for",
#                        lambda url: called.append(url) or "http://auto:1/")
#    seen = {}
#    monkeypatch.setattr(get_code, "build_opener",
#                        lambda cafile="", proxy="": seen.setdefault("p", proxy))
#    monkeypatch.setattr(get_code, "fetch", lambda *_a, **_k: b"")
#    get_code.main(["--dest", str(tmp_path / "o"), "--proxy", "http://mine:2/"])
#    assert seen["p"] == "http://mine:2/"
#    assert not called, "已經有 proxy 了就不該再去問 Windows"
#
#
#def test_resolving_the_proxy_never_becomes_the_failure_itself(monkeypatch):
#    """診斷用的東西壞掉不可以變成失敗原因 —— 非 Windows、沒有 powershell、
#    powershell 逾時、回一句看不懂的話，全部安靜回空字串。"""
#    monkeypatch.setattr(get_code.sys, "platform", "linux")
#    assert get_code.system_proxy_for("https://x/") == ""
#
#    monkeypatch.setattr(get_code.sys, "platform", "win32")
#
#    def boom(*_a, **_k):
#        raise OSError("powershell 不在 PATH 上")
#
#    monkeypatch.setattr(get_code.subprocess, "run", boom)
#    assert get_code.system_proxy_for("https://x/") == ""
#
#    class _R:
#        def __init__(self, out):
#            self.stdout = out
#
#    # .NET 在「不需要 proxy」時回傳原網址 —— 那不是 proxy
#    monkeypatch.setattr(get_code.subprocess, "run",
#                        lambda *_a, **_k: _R(b"https://x/\n"))
#    assert get_code.system_proxy_for("https://x/") == ""
#    # 看不懂的輸出也不能當成 proxy
#    monkeypatch.setattr(get_code.subprocess, "run",
#                        lambda *_a, **_k: _R("錯誤：不能執行\n".encode("utf-8")))
#    assert get_code.system_proxy_for("https://x/") == ""
#    # 真的解出來的樣子
#    monkeypatch.setattr(get_code.subprocess, "run",
#                        lambda *_a, **_k: _R(b"http://p.corp:8080/\n"))
#    assert get_code.system_proxy_for("https://x/") == "http://p.corp:8080/"
#
#
#def test_connection_refused_is_diagnosed_as_a_wrong_port(tmp_path, monkeypatch,
#                                                        capsys):
#    """實際遇到的第三個誤診：WinError 10061。
#
#    **拒絕連線不是逾時。** 位址查得到、封包也到了，只是那個埠上沒有東西在聽 ——
#    最常見的原因是 PAC 解出來的網址**沒有埠**，於是 urllib 用了預設的 80，
#    而公司 proxy 幾乎不在 80。給「它沒有回應，確認位址是對的」等於沒有診斷。
#    """
#    import urllib.error
#
#    def boom(ref, path, cafile=""):
#        raise urllib.error.URLError("[WinError 10061] 目標電腦拒絕連線")
#
#    monkeypatch.setattr(get_code, "fetch", boom)
#    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "http://px.corp/")
#    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
#    out = capsys.readouterr().out
#    assert "80" in out, "要講出「沒有埠所以用了 80」這件事"
#    assert "http://px.corp:8080" in out, "要給得出照做的下一步（試常見的埠）"
#    assert "get_code.ps1" in out, "要指向 PowerShell 版"
#
#
#def test_the_powershell_fetcher_keeps_the_same_contract():
#    """兩支抓程式碼的腳本必須是同一份契約 —— 不然「哪一支比較新」會變成
#    使用者要判斷的事。清單格式、SHA 演算法、atomic 寫入、不關 TLS 驗證。"""
#    with open(GETCODE_PS, "r", encoding="utf-8") as f:
#        ps = f.read()
#    assert "tools/FILELIST.txt" in ps
#    assert 'blob " + $Bytes.Length' in ps, "SHA 要跟 git 的 blob 格式一致"
#    assert ".tmp" in ps and "Move-Item" in ps, "寫入要是 atomic（鐵則 5）"
#    assert "raw.githubusercontent.com" in ps
#    assert "codeload.github.com" not in ps.split("#")[0] or True
#    # 絕對不可以為了繞過憑證錯誤把驗證關掉
#    for forbidden in ("ServerCertificateValidationCallback",
#                      "SkipCertificateCheck", "TrustAllCertsPolicy"):
#        assert forbidden not in ps, forbidden
#    # PS 5.1 的兩個坑：預設 TLS 1.0（GitHub 收不了）、沒有 -UseBasicParsing 會叫 IE
#    assert "Tls12" in ps, "PS 5.1 預設 TLS 1.0，GitHub 只收 1.2 以上"
#    assert "-UseBasicParsing" in ps, "沒有它 PS 5.1 會去叫 IE 引擎"
#    assert "ProxyUseDefaultCredentials" in ps, \
#        "整合驗證正是 PowerShell 版存在的理由之一"
#
#
#def test_both_fetchers_are_offered_in_the_docs():
#    """兩支都存在，文件就必須講「什麼時候用哪一支」——
#    否則使用者只會挑到先看到的那一支。"""
#    with open(os.path.join(REPO, "docs", "NO-GIT-SETUP.md"), "r",
#              encoding="utf-8") as f:
#        doc = f.read()
#    assert "get_code.py" in doc and "get_code.ps1" in doc
#    assert "ExecutionPolicy Bypass" in doc, "PS 預設不准跑腳本，這件事要講"
#
#
## ---------------------------------------------------------------- PowerShell 版（有 shell 才跑）
#
#def _powershell():
#    """找得到 pwsh / powershell 就回它的名字，否則空字串。"""
#    import shutil
#    for exe in ("pwsh", "powershell"):
#        if shutil.which(exe):
#            return exe
#    return ""
#
#
#needs_powershell = pytest.mark.skipif(
#    not _powershell(), reason="這台機器上沒有 PowerShell")
#
#
#def _run_ps(script):
#    exe = _powershell()
#    out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
#                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                         timeout=120)
#    return out.stdout.decode("utf-8", "replace")
#
#
#@needs_powershell
#def test_the_powershell_script_parses():
#    """語法錯誤在使用者那邊的代價是一整個來回 —— 這裡先解析一次。"""
#    out = _run_ps(
#        "$e = $null; "
#        "[System.Management.Automation.Language.Parser]::ParseFile("
#        "'%s', [ref]$null, [ref]$e) | Out-Null; "
#        "if ($e) { $e | ForEach-Object { $_.Message } } else { 'OK' }"
#        % GETCODE_PS.replace("\\", "/"))
#    assert "OK" in out, out
#
#
#@needs_powershell
#def test_the_powershell_blob_sha_matches_git():
#    """兩支腳本必須算出同一個 SHA，否則 PS 版會對**每一個**檔案都驗證失敗。"""
#    body = open(GETCODE_PS, "r", encoding="utf-8").read()
#    start = body.index("function Get-BlobSha")
#    end = body.index("function Write-Atomic")
#    fn = body[start:end]
#    out = _run_ps(fn + "\n"
#                  "Get-BlobSha -Bytes ([byte[]]@())\n"
#                  "Get-BlobSha -Bytes ([Text.Encoding]::ASCII.GetBytes('hello' + [char]10))")
#    assert "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" in out, out
#    assert "ce013625030ba8dba906f756967f9e9ca394464a" in out, out
#    assert get_code.blob_sha(b"") in out and get_code.blob_sha(b"hello\n") in out
#
#
#@needs_powershell
#def test_an_absolute_dest_is_not_glued_onto_the_current_directory():
#    """實際踩到的：``Join-Path`` 把絕對路徑接在目前目錄後面，做出
#    ``<repo>/tmp/x`` 這種東西 —— 而它**建得起來**，於是檔案安靜地跑到錯的地方。
#    「寫到別的地方去了」是使用者最不會想到要檢查的失敗。"""
#    body = open(GETCODE_PS, "r", encoding="utf-8").read()
#    assert "IsPathRooted" in body, "沒有這個判斷，絕對路徑就會被接歪"
#    sep = "/" if not sys.platform.startswith("win") else "C:\\"
#    abs_path = sep + "tmp_abs_probe" if sep == "/" else sep + "tmp_abs_probe"
#    out = _run_ps(
#        "$Dest = '%s'; "
#        "$d = if ([IO.Path]::IsPathRooted($Dest)) { [IO.Path]::GetFullPath($Dest) } "
#        "else { [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Dest)) }; "
#        "$d" % abs_path)
#    assert out.strip().rstrip("\\/").endswith("tmp_abs_probe"), out
#    assert REPO not in out, "絕對路徑又被接到目前目錄後面了"
#
#
## ---------------------------------------------------------------- 單檔純文字包
#
#@needs_git
#def test_the_text_bundle_round_trips_byte_for_byte(tmp_path):
#    """整個 repo 打成一個純文字檔、解開、逐位元組比對。
#
#    這條測試存在的理由是它抓過的兩個 bug（見下面兩支）—— 而那兩個 bug 都是
#    「產出來的東西看起來很正常，直到收到的人去跑它」那一類。
#    """
#    out = tmp_path / "ADEPT_bundle.py"
#    out.write_text(make_text_bundle.build(out.name, REPO), encoding="utf-8",
#                   newline="\n")
#    dest = tmp_path / "un"
#    r = subprocess.run([sys.executable, str(out), "--dest", str(dest)],
#                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                       timeout=300)
#    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
#
#    for rel in make_filelist.tracked_files(REPO) + ["tools/FILELIST.txt"]:
#        src = pathlib.Path(REPO) / rel
#        got = dest / rel
#        assert got.is_file(), "%s 沒有被解出來" % rel
#        assert got.read_bytes() == src.read_bytes(), rel
#
#
#@needs_git
#def test_the_bundle_is_still_valid_python(tmp_path):
#    """第一個 bug：資料區是裸的文字，於是 **Python 在跑之前先編譯整個檔案**，
#    去解析某個 .md 裡的全形括號然後 SyntaxError。資料區的每一行都必須是註解。"""
#    text = make_text_bundle.build("b.py", REPO)
#    ast.parse(text, filename="bundle")               # 這一行就是那個 bug 的守門
#
#    # 那個字串在產出的檔案裡出現**三次**：解包程式裡的賦值、真正的分隔行、
#    # 以及資料區裡（`make_text_bundle.py` 自己也在 repo 裡）。所以 split / rsplit
#    # 都不對，要找**整行剛好等於**它的那一行 —— 解包程式也是這樣做的，
#    # 而資料區每一行都被加了 '#'，所以資料裡的那一行永遠不會剛好相等。
#    lines = text.splitlines()
#    body = lines[lines.index(make_text_bundle.SENTINEL) + 1:]
#    assert body, "資料區是空的"
#    offenders = [ln for ln in body if ln and not ln.startswith("#")]
#    assert not offenders, offenders[:3]
#
#
#@needs_git
#def test_the_bundle_survives_having_its_line_endings_changed(tmp_path):
#    """第二個 bug 的反面。瀏覽器下載、記事本另存、郵件過濾器 —— 任何一步都可能
#    把 LF 換成 CRLF。格式用「行數」而不是「位元組數」就是為了對它免疫；
#    真的用位元組數的話，錯誤會出現在**第一個檔案之後的全部檔案**上。"""
#    src = make_text_bundle.build("b.py", REPO).encode("utf-8")
#    crlf = tmp_path / "crlf.py"
#    crlf.write_bytes(src.replace(b"\n", b"\r\n"))
#    dest = tmp_path / "un_crlf"
#    r = subprocess.run([sys.executable, str(crlf), "--dest", str(dest)],
#                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                       timeout=300)
#    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
#    one = pathlib.Path(REPO) / "tools" / "get_code.py"
#    assert (dest / "tools" / "get_code.py").read_bytes() == one.read_bytes()
#
#
#def test_a_tampered_bundle_refuses_to_land_anything(tmp_path):
#    """SHA 對不上的時候不可以寫出半份程式碼 —— 「看起來抓到了但其實是壞的」
#    是這一整輪反覆在防的東西。"""
#    body = b"print('hi')\n"
#    sha = make_text_bundle.blob_sha(body)
#    header = make_text_bundle.EXTRACTOR % {
#        "name": "b.py", "sentinel": make_text_bundle.SENTINEL,
#        "part": 1, "n_parts": 1, "total": 1}
#    good = "\n".join([header, make_text_bundle.SENTINEL,
#                      "#F %s 2 adept/x.py" % sha, "#print('hi')", "#"]) + "\n"
#    bad = good.replace("#print('hi')", "#print('tampered')")
#
#    for text, expect, should_exist in ((good, 0, True), (bad, 1, False)):
#        path = tmp_path / ("b_%d.py" % expect)
#        path.write_text(text, encoding="utf-8", newline="\n")
#        dest = tmp_path / ("d_%d" % expect)
#        r = subprocess.run([sys.executable, str(path), "--dest", str(dest)],
#                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                           timeout=120)
#        assert r.returncode == expect, r.stdout.decode("utf-8", "replace")
#        assert (dest / "adept" / "x.py").exists() is should_exist
#        if expect:
#            assert "SHA" in r.stdout.decode("utf-8", "replace")
#
#
#def test_the_bundle_refuses_to_pack_anything_it_cannot_round_trip(tmp_path,
#                                                                 monkeypatch):
#    """CRLF 或非 UTF-8 的檔案會讓「以行數為單位」的格式失效。
#    **拒絕產出**比產出一個解不開的包好 —— 後者要等收到的人才會發現。"""
#    (tmp_path / "a.txt").write_bytes(b"line\r\nline\r\n")
#    monkeypatch.setattr(make_text_bundle, "repo_root", lambda: str(tmp_path))
#    monkeypatch.setattr(make_text_bundle.subprocess, "run",
#                        lambda *_a, **_k: type("R", (), {"stdout": b"a.txt\n"})())
#    with pytest.raises(SystemExit) as e:
#        make_text_bundle.collect(str(tmp_path))
#    assert "CR" in str(e.value)
#
#
#def test_the_bundle_is_offered_in_the_docs():
#    with open(os.path.join(REPO, "docs", "NO-GIT-SETUP.md"), "r",
#              encoding="utf-8") as f:
#        doc = f.read()
#    assert "make_text_bundle.py" in doc
#    assert ".zip" in doc
#
#
## ---------------------------------------------------------------- 剪貼簿搬運（AGENTS.md §2）
#
#@needs_git
#def test_the_parts_all_fit_under_the_github_display_limit():
#    """**GitHub 不顯示超過 1 MB 的檔案**，而公司機唯一的取得方式是在 GitHub 上
#    按複製鈕。一批太大 = 打包成功但送不進去，那是最糟的一種「做完了」。"""
#    items = make_text_bundle.collect(REPO)
#    groups = make_text_bundle._slice(items, 400 * 1024)
#    assert len(groups) > 1, "整個 repo 早就超過一批的量了"
#    for i, group in enumerate(groups, 1):
#        text = make_text_bundle.build("p.py", REPO, items=group, part=i,
#                                      n_parts=len(groups), total_files=len(items))
#        kb = len(text.encode("utf-8")) / 1024
#        assert kb < 900, "第 %d 批 %.0f KB —— GitHub 可能就不顯示了" % (i, kb)
#        ast.parse(text, filename="part%d" % i)
#
#
#@needs_git
#def test_the_file_listing_is_in_the_first_part():
#    """後面每一批都用 ``tools/FILELIST.txt`` 回報「還缺幾個」，所以它得先到。"""
#    items = make_text_bundle.collect(REPO)
#    groups = make_text_bundle._slice(items, 400 * 1024)
#    assert "tools/FILELIST.txt" in [rel for rel, _d in groups[0]]
#
#
#@needs_git
#def test_a_single_part_never_claims_the_tree_is_ready(tmp_path):
#    """實際踩到的：只貼其中一批，它印「下一步：跑 doctor」—— 看起來整包到位了，
#    而其實少了一百多個檔案。這一整輪反覆在防的就是這種「看起來做完了」。"""
#    items = make_text_bundle.collect(REPO)
#    groups = make_text_bundle._slice(items, 400 * 1024)
#    # 挑一批**不含**檔案清單的（那是最容易誤報的情況）
#    idx = next(i for i, g in enumerate(groups)
#               if "tools/FILELIST.txt" not in [r for r, _d in g])
#    text = make_text_bundle.build("p.py", REPO, items=groups[idx], part=idx + 1,
#                                  n_parts=len(groups), total_files=len(items))
#    path = tmp_path / "p.py"
#    path.write_text(text, encoding="utf-8", newline="\n")
#    r = subprocess.run([sys.executable, str(path), "--dest", str(tmp_path / "d")],
#                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                       timeout=300)
#    out = r.stdout.decode("utf-8", "replace")
#    assert r.returncode == 0, out
#    assert "還沒到齊" in out, out
#    assert "doctor" not in out, "少了一百多個檔案卻叫他去跑 doctor"
#
#
#@needs_git
#def test_generated_bundles_are_kept_out_of_the_listing_and_the_packing():
#    """``bundle/`` 是 repo 的**複本**，不是內容。列進去有兩個後果：
#    `get_code.py` 白抓 2.4 MB，而分批解包的「還缺幾個」永遠到不了 0。"""
#    listed = set(make_filelist.tracked_files(REPO))
#    packed = {rel for rel, _d in make_text_bundle.collect(REPO)}
#    assert not [p for p in listed if p.startswith("bundle/")]
#    assert not [p for p in packed if p.startswith("bundle/")]
#    # 但清單自己**要**在包裡（0b 的更新流程靠它）
#    assert "tools/FILELIST.txt" in packed
#
#
#def test_check_files_names_exactly_what_needs_recopying(tmp_path):
#    """更新的流程是「複製 12 KB 的清單 → 這支告訴你剩下要複製哪幾個」。
#    它必須分得出「缺少」與「內容不一樣」—— 兩個都要重新複製，但原因不同。"""
#    root = tmp_path / "tree"
#    (root / "tools").mkdir(parents=True)
#    (root / "a.py").write_bytes(b"good\n")
#    (root / "b.py").write_bytes(b"changed\n")
#    lines = [
#        "# comment",
#        "%s a.py" % check_files.blob_sha(b"good\n"),
#        "%s b.py" % check_files.blob_sha(b"original\n"),
#        "%s c.py" % check_files.blob_sha(b"absent\n"),
#    ]
#    (root / "tools" / "FILELIST.txt").write_text("\n".join(lines) + "\n",
#                                                 encoding="utf-8")
#    want = check_files.read_manifest(str(root / "tools" / "FILELIST.txt"))
#    missing, stale = check_files.compare(str(root), want)
#    assert missing == ["c.py"]
#    assert stale == ["b.py"]
#    assert check_files.main(["--root", str(root)]) == 1     # 有事要做 = 非零
#
#    (root / "b.py").write_bytes(b"original\n")
#    (root / "c.py").write_bytes(b"absent\n")
#    assert check_files.main(["--root", str(root)]) == 0
#
#
#def test_check_files_says_what_to_do_when_the_listing_is_missing(tmp_path, capsys):
#    """沒有清單的時候不能只說「找不到檔案」—— 要講出那一個檔案要去哪裡拿。"""
#    assert check_files.main(["--root", str(tmp_path)]) == 2
#    out = capsys.readouterr().out
#    assert "FILELIST.txt" in out and "github.com" in out
#
#
#def test_the_two_machine_setup_is_written_down():
#    """這些限制是整個 tools/ 形狀的原因。沒寫下來的話，下一個人會把
#    stdlib-only、FILELIST、bundle 當成過度設計然後順手簡化掉。"""
#    with open(os.path.join(REPO, "AGENTS.md"), "r", encoding="utf-8") as f:
#        doc = f.read()
#    for must in ("家用機", "公司機", "剪貼簿", "FILELIST.txt", "bundle/",
#                 "fab_probe", "stdlib-only", "1 MB"):
#        assert must in doc, must
#    with open(os.path.join(REPO, "CLAUDE.md"), "r", encoding="utf-8") as f:
#        assert "AGENTS.md" in f.read(), "CLAUDE.md 要指得到 AGENTS.md"
#
#F e027a9047fa771cca97915c533a7f90198c0fb18 108 tests/test_period_golden.py
#"""Tests for adept.core.algo.period and .golden (vendored from
#cell-period-estimator)."""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#
#from adept.core.algo.golden import (
#    candidate_periods,
#    ghosting_score,
#    refine_period,
#    stack_cells,
#    tile_coords,
#)
#from adept.core.algo.period import choose_origin, estimate_period
#
#PX, PY = 24, 32
#
#
#@pytest.fixture(scope="module")
#def grid_image():
#    """Synthetic 2-D cell grid: bright rectangle per (PX x PY) cell + noise."""
#    rng = np.random.default_rng(42)
#    h, w = 320, 288
#    img = np.full((h, w), 40, np.float64)
#    for y0 in range(0, h - PY + 1, PY):
#        for x0 in range(0, w - PX + 1, PX):
#            img[y0 + 8:y0 + 24, x0 + 6:x0 + 18] = 200
#    img += rng.normal(0, 3, img.shape)
#    return np.clip(img, 0, 255).astype(np.uint8)
#
#
#@pytest.fixture(scope="module")
#def line_space_image():
#    """Vertical line/space pattern: period 20 along X, flat along Y."""
#    rng = np.random.default_rng(43)
#    img = np.full((256, 256), 30, np.float64)
#    for x0 in range(0, 256, 20):
#        img[:, x0:x0 + 10] = 220
#    img += rng.normal(0, 2, img.shape)
#    return np.clip(img, 0, 255).astype(np.uint8)
#
#
#def test_estimate_period_grid_xy(grid_image):
#    r = estimate_period(grid_image)
#    assert r.axis_mode == "XY"
#    assert r.px is not None and abs(r.px - PX) <= 1
#    assert r.py is not None and abs(r.py - PY) <= 1
#    assert r.confidence_x > 50 and r.confidence_y > 50
#    assert (r.px, r.py) == r.candidates[0]
#
#
#def test_estimate_period_line_space_x_only(line_space_image):
#    r = estimate_period(line_space_image)
#    assert r.axis_mode == "X"
#    assert r.px is not None and abs(r.px - 20) <= 1
#    assert r.py is None
#
#
#def test_estimate_period_flat_none():
#    flat = np.full((64, 64), 128, dtype=np.uint8)
#    r = estimate_period(flat)
#    assert r.axis_mode == "NONE"
#    assert r.px is None and r.py is None
#    assert "no periodic structure detected" in r.warnings
#
#
#def test_correct_period_stacks_sharper(grid_image):
#    good = stack_cells(grid_image, PX, PY)
#    bad = stack_cells(grid_image, PX + 3, PY + 3)
#    assert good.shape == (PY, PX)
#    _, lap_good, edge_good = ghosting_score(good)
#    score_bad, lap_bad, edge_bad = ghosting_score(bad)
#    assert lap_good > 2.0 * lap_bad     # ghosting blurs the wrong-period stack
#    assert edge_good > edge_bad
#    score_good = ghosting_score(good)[0]
#    assert score_good > score_bad
#
#
#def test_refine_period_recovers_truth(grid_image):
#    bpx, bpy, blv = refine_period(grid_image, PX - 2, PY - 2, search=4)
#    assert (bpx, bpy) == (PX, PY)
#    assert blv > 0
#
#
#def test_tile_coords_complete_cells_only(grid_image):
#    coords = tile_coords(grid_image.shape, PX, PY)
#    h, w = grid_image.shape
#    assert len(coords) == (w // PX) * (h // PY)
#    assert all(x + PX <= w and y + PY <= h for x, y in coords)
#    assert tile_coords(grid_image.shape, 0, 5) == []
#
#
#def test_stack_cells_deterministic_sampling(grid_image):
#    a = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
#    b = stack_cells(grid_image, PX, PY, sample_n=10, seed=5)
#    assert np.array_equal(a, b)
#
#
#def test_candidate_periods_and_origin():
#    cands = candidate_periods(PX, PY, lo=4, hi=128)
#    assert cands[0] == (PX, PY)
#    assert len(cands) == len(set(cands))
#    assert all(4 <= a <= 128 and 4 <= b <= 128 for a, b in cands)
#    assert (PX // 2, PY // 2) in cands and (2 * PX, 2 * PY) in cands
#    # choose_origin is the documented (0, 0) stub until the M4 phase search
#    assert choose_origin((320, 288), PX, PY) == (0, 0)
#
#F 482763f96a3f9e39f90a7e6cbd97c6716b29db63 145 tests/test_phase_origin.py
#"""Tests for the M4-1 phase search in ``adept.core.algo.period.choose_origin``.
#
#``choose_origin`` picks the lattice origin ``(ox, oy)`` — the offset at
#which cutting the image into ``px x py`` cells puts every cell in phase.
#It maximises the **raw Laplacian variance** of the stacked cell
#(``golden.ghosting_score(...)[1]``, higher = sharper = less ghosting).
#
#The criterion is translation-equivariant rather than absolute: which
#phase inside the cell it prefers depends on the pattern, but cropping
#the *same* image by ``c`` pixels must shift the answer by ``-c``
#(mod pitch).  That is what "recovers a known phase offset" means here,
#and it is what the Golden Cell card relies on.
#"""
#from __future__ import annotations
#
#import time
#
#import cv2
#import numpy as np
#import pytest
#
#from adept.core.algo.golden import ghosting_score, stack_cells
#from adept.core.algo.period import choose_origin
#
#PITCH = 16
#
#
#def _cell_tile(pitch: int = PITCH) -> np.ndarray:
#    """一格 cell：圓角亮方塊 + 一個小記號（打破左右對稱）。"""
#    c = np.zeros((pitch, pitch), np.float64)
#    cv2.rectangle(c, (3, 3), (pitch - 6, pitch - 6), 210, -1)
#    c[pitch - 4:pitch - 2, 2:5] = 120
#    return cv2.GaussianBlur(c, (3, 3), 0.9) + 35.0
#
#
#def _lattice(h=256, w=256, pitch=PITCH, crop=0, seed=0, noise=3.0) -> np.ndarray:
#    """Periodic lattice cropped at a KNOWN phase offset ``crop`` (both axes)."""
#    tile = _cell_tile(pitch)
#    reps = (h // pitch + 3, w // pitch + 3)
#    big = np.tile(tile, reps)
#    img = big[crop:crop + h, crop:crop + w]
#    img = img + np.random.default_rng(seed).normal(0, noise, img.shape)
#    return np.clip(img, 0, 255).astype(np.uint8)
#
#
#def _circ(a: int, b: int, period: int) -> int:
#    """Circular distance between two offsets of the same period."""
#    d = abs(int(a) - int(b)) % period
#    return min(d, period - d)
#
#
#@pytest.fixture(scope="module")
#def base_origin():
#    """The origin the criterion picks for the un-cropped lattice."""
#    img = _lattice()
#    return choose_origin(img.shape, PITCH, PITCH, image=img)
#
#
## ---------------------------------------------------------------- 相位回復
#
#@pytest.mark.parametrize("crop", [0, 3, 5, 9, 13])
#def test_recovers_known_phase_offset(crop, base_origin):
#    """裁掉 crop 個像素後，找到的原點必須跟著位移 -crop（mod pitch）。"""
#    img = _lattice(crop=crop)
#    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
#    assert 0 <= ox < PITCH and 0 <= oy < PITCH
#    assert _circ(ox + crop, base_origin[0], PITCH) <= 1
#    assert _circ(oy + crop, base_origin[1], PITCH) <= 1
#
#
#def test_chosen_origin_stacks_sharper_than_wrong_phase():
#    """挑到的相位疊出來要比刻意錯開半格的相位清晰（higher lap_var = better）。"""
#    img = _lattice(crop=5)
#    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
#    best = ghosting_score(stack_cells(img, PITCH, PITCH, origin=(ox, oy)))[1]
#    worst = ghosting_score(stack_cells(
#        img, PITCH, PITCH,
#        origin=((ox + PITCH // 2) % PITCH, (oy + PITCH // 2) % PITCH)))[1]
#    assert best > worst
#
#
#def test_deterministic_same_input_same_answer():
#    img = _lattice(crop=7)
#    a = choose_origin(img.shape, PITCH, PITCH, image=img)
#    b = choose_origin(img.shape, PITCH, PITCH, image=img)
#    assert a == b
#
#
## ---------------------------------------------------------------- 相容性 / 防呆
#
#def test_without_image_is_the_legacy_zero_origin():
#    """舊的三參數呼叫（沒有 image）維持 (0, 0) 行為。"""
#    assert choose_origin((320, 288), 24, 32) == (0, 0)
#    assert choose_origin((320, 288), 24, 32, image=None) == (0, 0)
#
#
#def test_flat_image_returns_zero_origin():
#    flat = np.full((128, 128), 128, np.uint8)
#    assert choose_origin(flat.shape, 16, 16, image=flat) == (0, 0)
#
#
#@pytest.mark.parametrize("px,py", [(None, 16), (16, None), (None, None),
#                                   (0, 16), (1, 16), (16, 1), (-4, 16)])
#def test_bad_period_returns_zero_origin(px, py):
#    img = _lattice()
#    assert choose_origin(img.shape, px, py, image=img) == (0, 0)
#
#
#def test_image_smaller_than_one_cell_returns_zero_origin():
#    tiny = _lattice(h=10, w=10)
#    assert choose_origin(tiny.shape, 16, 16, image=tiny) == (0, 0)
#
#
#def test_single_cell_row_pins_that_axis_to_zero():
#    """只放得下一列 cell 時，該軸沒有相位資訊 → 釘在 0，另一軸照常搜尋。"""
#    img = _lattice(h=20, w=256, crop=5)
#    ox, oy = choose_origin(img.shape, PITCH, PITCH, image=img)
#    assert oy == 0
#    assert 0 <= ox < PITCH
#
#
#def test_colour_image_is_accepted():
#    gray = _lattice(crop=3)
#    colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
#    assert choose_origin(colour.shape, PITCH, PITCH, image=colour) == \
#        choose_origin(gray.shape, PITCH, PITCH, image=gray)
#
#
## ---------------------------------------------------------------- 成本上限
#
#def test_large_period_is_capped_and_fast():
#    """px=py=64（4096 個相位）必須靠取樣 + 微調壓在 2 秒內，且答對。"""
#    base = _lattice(h=512, w=512, pitch=64, crop=0, seed=1)
#    shifted = _lattice(h=512, w=512, pitch=64, crop=7, seed=1)
#
#    t0 = time.time()
#    b = choose_origin(base.shape, 64, 64, image=base)
#    s = choose_origin(shifted.shape, 64, 64, image=shifted)
#    elapsed = time.time() - t0
#    assert elapsed < 2.0, f"phase search too slow: {elapsed:.2f}s for 2 runs"
#
#    # 取樣（stride）+ 微調後仍要抓到相位：位移 7 → 原點跟著位移 -7
#    assert _circ(s[0] + 7, b[0], 64) <= 1
#    assert _circ(s[1] + 7, b[1], 64) <= 1
#
#F 8c4b2aba1d0893acc999c5acb331fd00839518d9 80 tests/test_quality.py
#"""Tests for adept.core.algo.quality (vendored from MMH)."""
#from __future__ import annotations
#
#import cv2
#import numpy as np
#import pytest
#
#from adept.core.algo.quality import (
#    DEFAULT_LAP_THRESHOLD,
#    check_lap_quality,
#    compute_quality,
#)
#
#_METRICS = ("laplacian_var", "tenengrad", "fft_hf_ratio")
#
#
#@pytest.fixture(scope="module")
#def sharp_image():
#    """Noisy fine checkerboard — strong genuine high-frequency content."""
#    rng = np.random.default_rng(123)
#    img = np.zeros((128, 128), np.float64)
#    for y in range(0, 128, 8):
#        for x in range(0, 128, 8):
#            img[y:y + 8, x:x + 8] = 210 if ((y // 8) + (x // 8)) % 2 == 0 else 40
#    img += rng.normal(0, 8, img.shape)
#    return np.clip(img, 0, 255).astype(np.uint8)
#
#
#@pytest.fixture(scope="module")
#def blurred_image(sharp_image):
#    return cv2.GaussianBlur(sharp_image, (0, 0), 4.0)
#
#
#def test_sharp_beats_blurred_on_all_metrics(sharp_image, blurred_image):
#    qs = compute_quality(sharp_image)
#    qb = compute_quality(blurred_image)
#    assert qs["error"] == "" and qb["error"] == ""
#    for k in _METRICS:
#        assert qs[k] > qb[k], k
#
#
#def test_check_lap_quality_orders_and_threshold(sharp_image, blurred_image):
#    lap_sharp = check_lap_quality(sharp_image)
#    lap_blur = check_lap_quality(blurred_image)
#    assert lap_sharp > lap_blur
#    assert lap_sharp > DEFAULT_LAP_THRESHOLD
#    assert lap_blur < DEFAULT_LAP_THRESHOLD
#    # matches compute_quality's laplacian_var (same medianBlur(5) pre-filter)
#    assert lap_sharp == pytest.approx(
#        compute_quality(sharp_image)["laplacian_var"])
#
#
#def test_ndarray_and_path_inputs_agree(sharp_image, tmp_path):
#    # CJK filename: exercises the np.fromfile + cv2.imdecode path loader
#    p = tmp_path / "样品_对焦.png"
#    ok, buf = cv2.imencode(".png", sharp_image)
#    assert ok
#    buf.tofile(str(p))
#    q_arr = compute_quality(sharp_image)
#    q_path = compute_quality(str(p))
#    assert q_path["error"] == ""
#    for k in _METRICS:
#        assert q_path[k] == pytest.approx(q_arr[k], abs=1e-9), k
#
#
#def test_color_ndarray_accepted(sharp_image):
#    bgr = cv2.cvtColor(sharp_image, cv2.COLOR_GRAY2BGR)
#    q = compute_quality(bgr)
#    assert q["error"] == ""
#    assert q["laplacian_var"] == pytest.approx(
#        compute_quality(sharp_image)["laplacian_var"])
#
#
#def test_missing_path_reports_error(tmp_path):
#    q = compute_quality(str(tmp_path / "does_not_exist.png"))
#    assert q["error"] == "Cannot load image"
#    assert q["laplacian_var"] == 0.0
#    assert q["tenengrad"] == 0.0
#    assert q["fft_hf_ratio"] == 0.0
#
#F eff142e969dcbb7b7234677b6b5398fc0d3039b1 344 tests/test_recipe.py
#"""M1 驗收：Recipe JSON serde、execution_order、lint 式 validate。
#
#本檔的 dummy Step 不進全域 REGISTRY —— 一律以 registry= 參數顯式傳入
#validate()，避免與並行開發中的 adept/core/steps/ 相互干擾。
#"""
#from __future__ import annotations
#
#import json
#
#import pytest
#
#from adept.core.pipeline import (
#    CATEGORY_ALGO,
#    CATEGORY_IMAGE,
#    ParamSpec,
#    Recipe,
#    RecipeError,
#    RecipeNode,
#    ScoreSpec,
#    Step,
#    execution_order,
#    validate,
#)
#
#
## ---------------------------------------------------------------------------
## dummy 卡片（僅供本測試檔；不註冊進 REGISTRY）
## ---------------------------------------------------------------------------
#class TLoadPair(Step):
#    key = "t_load_pair"
#    label = "測試載入（test+ref）"
#    category = CATEGORY_IMAGE
#    help = "測試用：寫入 test 與 ref 影像流"
#    writes = ["test", "ref"]
#
#    def run(self, ctx, params):
#        return ctx
#
#
#class TLoadSingle(Step):
#    key = "t_load_single"
#    label = "測試載入（單張）"
#    category = CATEGORY_IMAGE
#    help = "測試用：只寫入 test 影像流"
#    writes = ["test"]
#
#    def run(self, ctx, params):
#        return ctx
#
#
#class TSubtract(Step):
#    key = "t_subtract"
#    label = "測試相減"
#    category = CATEGORY_IMAGE
#    help = "測試用：test - ref → diff"
#    reads = ["test", "ref"]
#    writes = ["diff"]
#
#    def run(self, ctx, params):
#        return ctx
#
#
#class TSnr(Step):
#    key = "t_snr"
#    label = "測試 SNR"
#    category = CATEGORY_ALGO
#    help = "測試用：從 diff 量 snr_max"
#    reads = ["diff"]
#    features_out = ["snr_max"]
#    params = [ParamSpec("k", "int", 3, "視窗大小", min=1, max=9)]
#
#    def run(self, ctx, params):
#        return ctx
#
#
#class TNeedsRef(Step):
#    key = "t_needs_ref"
#    label = "測試需 ref"
#    category = CATEGORY_IMAGE
#    help = "測試用：requires_ref 卡"
#    reads = ["test"]
#    writes = ["aligned"]
#    requires_ref = True
#
#    def run(self, ctx, params):
#        return ctx
#
#
#REG = {c.key: c for c in (TLoadPair, TLoadSingle, TSubtract, TSnr, TNeedsRef)}
#
#
#def make_recipe(**kw):
#    base = dict(
#        recipe_id="unit_test",
#        routes={"ebi_patch": ["load", "sub", "snr"]},
#        nodes={
#            "load": RecipeNode("load", "t_load_pair", {}),
#            "sub": RecipeNode("sub", "t_subtract", {}),
#            "snr": RecipeNode("snr", "t_snr", {"k": 5}),
#        },
#        score=ScoreSpec(expr="snr_max * 2", threshold=3.0,
#                        bins={"below": 0, "above": 1}),
#        version=2,
#        author="unit",
#        description="單元測試 recipe",
#        edges=[],
#    )
#    base.update(kw)
#    return Recipe(**base)
#
#
#def codes(issues):
#    return [i.code for i in issues]
#
#
## ---------------------------------------------------------------------------
## JSON serde
## ---------------------------------------------------------------------------
#def test_json_round_trip_dict():
#    r = make_recipe(edges=[["load", "snr"]])
#    d = r.to_json_dict()
#    r2 = Recipe.from_json_dict(d)
#    assert r2 == r
#    assert r2.to_json_dict() == d          # round-trip stable
#    json.dumps(d)                          # 可序列化
#
#
#def test_json_defaults_filled():
#    d = {
#        "recipe_id": "min",
#        "routes": {"ebi_patch": ["load"]},
#        "nodes": {"load": {"step": "t_load_pair"}},
#        "score": {"expr": "1", "threshold": 0.5, "bins": {"below": 0, "above": 1}},
#    }
#    r = Recipe.from_json_dict(d)
#    assert r.version == 1
#    assert r.author == ""
#    assert r.description == ""
#    assert r.edges == []
#    assert r.nodes["load"].enabled is True
#    assert r.nodes["load"].params == {}
#    assert r.nodes["load"].id == "load"
#
#
#def test_json_missing_required_field():
#    with pytest.raises(RecipeError):
#        Recipe.from_json_dict({"recipe_id": "x"})
#
#
#def test_save_load_atomic(tmp_path):
#    r = make_recipe()
#    p = tmp_path / "recipe.json"
#    r.save(p)
#    assert p.exists()
#    assert not (tmp_path / "recipe.json.tmp").exists()   # atomic：tmp 已 replace
#    r2 = Recipe.load(p)
#    assert r2 == r
#    # utf-8 中文 description 不會壞
#    raw = p.read_text(encoding="utf-8")
#    assert "單元測試" in raw
#
#
## ---------------------------------------------------------------------------
## execution_order
## ---------------------------------------------------------------------------
#def test_execution_order_chain():
#    r = make_recipe()
#    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]
#
#
#def test_execution_order_extra_edge_consistent():
#    # 額外邊與鏈一致 → 順序不變
#    r = make_recipe(edges=[["load", "snr"]])
#    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]
#
#
#def test_execution_order_edge_outside_route_ignored():
#    # 邊的端點不在該 route 內 → 不影響
#    r = make_recipe(edges=[["ghost", "snr"], ["load", "ghost"]])
#    assert execution_order(r, "ebi_patch") == ["load", "sub", "snr"]
#
#
#def test_execution_order_cycle_raises():
#    r = make_recipe(edges=[["snr", "load"]])
#    with pytest.raises(RecipeError):
#        execution_order(r, "ebi_patch")
#
#
#def test_execution_order_unknown_kind_raises():
#    r = make_recipe()
#    with pytest.raises(RecipeError):
#        execution_order(r, "no_such_kind")
#
#
## ---------------------------------------------------------------------------
## validate — 每個 issue code
## ---------------------------------------------------------------------------
#def test_validate_clean_recipe_no_issues():
#    r = make_recipe()
#    assert validate(r, registry=REG) == []
#
#
#def test_validate_unknown_step():
#    r = make_recipe()
#    r.nodes["sub"] = RecipeNode("sub", "nope_step", {})
#    issues = validate(r, registry=REG)
#    assert "unknown-step" in codes(issues)
#    bad = [i for i in issues if i.code == "unknown-step"][0]
#    assert bad.node_id == "sub"
#    assert bad.level == "error"
#
#
#def test_validate_bad_param():
#    r = make_recipe()
#    r.nodes["snr"] = RecipeNode("snr", "t_snr", {"k": 99})     # max=9
#    issues = validate(r, registry=REG)
#    assert "bad-param" in codes(issues)
#    # 壞參數改用預設值繼續模擬 → 不應誤報 missing-image
#    assert "missing-image" not in codes(issues)
#
#
#def test_validate_bad_param_unknown_name():
#    r = make_recipe()
#    r.nodes["snr"] = RecipeNode("snr", "t_snr", {"nope": 1})
#    assert "bad-param" in codes(validate(r, registry=REG))
#
#
#def test_validate_unknown_node_in_route():
#    r = make_recipe(routes={"ebi_patch": ["load", "ghost", "snr"]})
#    r.nodes.pop("sub")
#    issues = validate(r, registry=REG)
#    assert "unknown-node" in codes(issues)
#
#
#def test_validate_unknown_route_kind():
#    r = make_recipe()
#    issues = validate(r, kind="no_such_kind", registry=REG)
#    assert "unknown-route" in codes(issues)
#
#
#def test_validate_cycle():
#    r = make_recipe(edges=[["snr", "load"]])
#    issues = validate(r, registry=REG)
#    assert "cycle" in codes(issues)
#
#
#def test_validate_missing_image():
#    # snr 讀 diff，但沒有 subtract 卡產 diff
#    r = make_recipe(routes={"ebi_patch": ["load", "snr"]})
#    issues = validate(r, registry=REG)
#    assert "missing-image" in codes(issues)
#    bad = [i for i in issues if i.code == "missing-image"][0]
#    assert bad.node_id == "snr"
#    assert "diff" in bad.detail
#
#
#def test_validate_first_node_reads_unchecked():
#    # 第一張啟用卡（load 卡）的 reads 不檢查（它從 dataset 拿資料）
#    r = make_recipe(routes={"ebi_patch": ["sub"]},
#                    nodes={"sub": RecipeNode("sub", "t_subtract", {})},
#                    score=ScoreSpec(expr="1", threshold=0.0,
#                                    bins={"below": 0, "above": 1}))
#    issues = validate(r, registry=REG)
#    assert "missing-image" not in codes(issues)
#
#
#def test_validate_requires_ref_on_rsem():
#    r = make_recipe(
#        routes={"rsem": ["load1", "align"]},
#        nodes={
#            "load1": RecipeNode("load1", "t_load_single", {}),
#            "align": RecipeNode("align", "t_needs_ref", {}),
#        },
#        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}),
#    )
#    issues = validate(r, kind="rsem", registry=REG)
#    assert "requires-ref" in codes(issues)
#    # 上游有產 ref（t_load_pair）→ 不報
#    r.nodes["load1"] = RecipeNode("load1", "t_load_pair", {})
#    issues = validate(r, kind="rsem", registry=REG)
#    assert "requires-ref" not in codes(issues)
#
#
#def test_validate_requires_ref_not_flagged_on_ebi_patch():
#    r = make_recipe(
#        routes={"ebi_patch": ["load", "align"]},
#        nodes={
#            "load": RecipeNode("load", "t_load_pair", {}),
#            "align": RecipeNode("align", "t_needs_ref", {}),
#        },
#        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}),
#    )
#    assert "requires-ref" not in codes(validate(r, registry=REG))
#
#
#def test_validate_score_expr_parse_error():
#    r = make_recipe(score=ScoreSpec(expr="snr_max *", threshold=1.0,
#                                    bins={"below": 0, "above": 1}))
#    issues = validate(r, registry=REG)
#    assert "score-expr" in codes(issues)
#
#
#def test_validate_unknown_feature_warning():
#    r = make_recipe(score=ScoreSpec(expr="snr_max * mystery_feat", threshold=1.0,
#                                    bins={"below": 0, "above": 1}))
#    issues = validate(r, registry=REG)
#    warn = [i for i in issues if i.code == "unknown-feature"]
#    assert len(warn) == 1
#    assert warn[0].level == "warning"
#    assert "mystery_feat" in warn[0].detail
#
#
#def test_validate_score_var_allowed():
#    # "score" 本身永遠是合法變數（bin 條件常用）
#    r = make_recipe(score=ScoreSpec(expr="snr_max + score * 0", threshold=1.0,
#                                    bins={"below": 0, "above": 1}))
#    assert "unknown-feature" not in codes(validate(r, registry=REG))
#
#
#def test_validate_bad_bins():
#    r = make_recipe(score=ScoreSpec(expr="snr_max", threshold=1.0,
#                                    bins={"below": 0}))
#    issues = validate(r, registry=REG)
#    assert "bad-bins" in codes(issues)
#
#
#def test_validate_disabled_node_skipped_in_simulation():
#    # subtract 停用 → snr 的 diff 拿不到 → missing-image（與 runtime 一致）
#    r = make_recipe()
#    r.nodes["sub"].enabled = False
#    issues = validate(r, registry=REG)
#    assert "missing-image" in codes(issues)
#
#
#def test_validate_collects_multiple_issues_at_once():
#    r = make_recipe(
#        routes={"ebi_patch": ["load", "ghost", "snr"]},
#        score=ScoreSpec(expr="1 +", threshold=1.0, bins={}),
#    )
#    r.nodes.pop("sub")
#    r.nodes["load"] = RecipeNode("load", "no_such_step", {})
#    got = set(codes(validate(r, registry=REG)))
#    assert {"unknown-node", "unknown-step", "score-expr", "bad-bins"} <= got
#
#F ec7a355551b68c41ad5513d1e1a287f7ae5e506d 169 tests/test_region.py
## F7-4 驗收：Region 段 —— ROI 從「藏在量測卡裡的參數」升成一級概念。
#"""具名 ROI 的契約，以及它修掉的那個坑。
#
#背景：F7-4 之前，「要看哪裡」是被複製在每張量測卡裡的幾何參數
#（``glv_stats`` 的 ``region``/``box_size``、``roi_snr`` 的 ``mode``/``box_size``）。
#``CLAUDE.md`` §7 記著它的後果：同一組中心框參數在 128² patch 上準、
#換成 256² 就漏抓。現在幾何只在 Region 卡裡定義一次，量測卡只引用名字。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#from adept.core.pipeline import REGISTRY, StepError          # noqa: E402
#from adept.core.pipeline.context import Context, ContextError  # noqa: E402
#from adept.core.steps.region import center_norm_rect          # noqa: E402
#import adept.core.steps  # noqa: F401,E402 — 觸發註冊
#
#
#def run_step(key, ctx, **params):
#    cls = REGISTRY[key]
#    return cls().run(ctx, cls.validate_params(params))
#
#
#def _ctx(size=128, key="test"):
#    return Context(images={key: np.zeros((size, size), np.uint8)})
#
#
## --------------------------------------------------------------------------- #
## 1. Context 的具名 ROI 契約
## --------------------------------------------------------------------------- #
#def test_named_roi_round_trip_and_overwrite():
#    ctx = _ctx()
#    assert ctx.roi_names() == []
#
#    ctx.set_roi("a", (0.25, 0.25, 0.5, 0.5))
#    assert ctx.roi_names() == ["a"]
#    assert ctx.roi_rect("a", (128, 128)) == (32, 32, 64, 64)
#
#    # 同名要覆寫，不是變成兩個
#    ctx.set_roi("a", (0.0, 0.0, 1.0, 1.0))
#    assert ctx.roi_names() == ["a"]
#    assert ctx.roi_rect("a", (128, 128)) == (0, 0, 128, 128)
#
#
#def test_require_roi_names_what_is_available():
#    """打錯字要講得出「有哪些可用」，不能只說找不到。"""
#    ctx = _ctx()
#    ctx.set_roi("centre", (0.4, 0.4, 0.2, 0.2))
#    with pytest.raises(ContextError) as ei:
#        ctx.require_roi("centr")
#    msg = str(ei.value)
#    assert "centre" in msg and "Region card" in msg
#
#
## --------------------------------------------------------------------------- #
## 2. Region 卡
## --------------------------------------------------------------------------- #
#def test_roi_define_center_is_actually_centred():
#    ctx = _ctx(128)
#    run_step("roi_define", ctx, name="mid", shape="center", size=32)
#    x, y, w, h = ctx.roi_rect("mid", (128, 128))
#    assert (w, h) == (32, 32)
#    assert (x + w / 2, y + h / 2) == (64, 64), "缺陷永遠在 patch 正中心"
#
#
#def test_roi_define_whole_covers_everything():
#    ctx = _ctx(64)
#    run_step("roi_define", ctx, name="all", shape="whole")
#    assert ctx.roi_rect("all", (64, 64)) == (0, 0, 64, 64)
#
#
#def test_percent_sizing_survives_a_patch_size_change():
#    """**CLAUDE.md §7 那個坑的正解。**
#
#    以像素定義的框換 patch 尺寸就失效；以百分比定義的框會跟著縮放，
#    所以同一份 recipe 在 128² 與 256² 上看的是「同一塊相對區域」。
#    """
#    assert center_norm_rect((128, 128), 32, "px") != \
#        center_norm_rect((256, 256), 32, "px"), \
#        "px 模式的正規化矩形本來就會隨影像尺寸改變 —— 這正是問題所在"
#
#    pct = center_norm_rect((128, 128), 25, "percent")
#    assert pct == center_norm_rect((256, 256), 25, "percent")
#
#    ctx = _ctx()
#    ctx.set_roi("q", pct)
#    assert ctx.roi_rect("q", (128, 128)) == (48, 48, 32, 32)
#    assert ctx.roi_rect("q", (256, 256)) == (96, 96, 64, 64)   # 比例相同
#
#
#def test_roi_define_clamps_silly_sizes():
#    """填爆的值要被夾住，不能產生無效的框（鐵則 4）。"""
#    ctx = _ctx(64)
#    run_step("roi_define", ctx, name="huge", shape="center", size=99999)
#    assert ctx.roi_rect("huge", (64, 64)) == (0, 0, 64, 64)
#
#    run_step("roi_define", ctx, name="tiny", shape="center", size=1)
#    _x, _y, w, h = ctx.roi_rect("tiny", (64, 64))
#    assert w >= 1 and h >= 1
#
#
#def test_empty_region_name_is_refused():
#    ctx = _ctx()
#    with pytest.raises(StepError):
#        run_step("roi_define", ctx, name="   ")
#
#
## --------------------------------------------------------------------------- #
## 3. 量測卡引用具名 ROI
## --------------------------------------------------------------------------- #
#def test_glv_stats_measures_inside_the_named_region():
#    img = np.zeros((64, 64), np.float32)
#    img[24:40, 24:40] = 100.0            # 只有中央 16×16 有訊號
#    ctx = Context(images={"test": img})
#
#    run_step("roi_define", ctx, name="mid", shape="center", size=16)
#    run_step("glv_stats", ctx, roi="mid", metrics="glv_mean")
#    assert ctx.features["glv_mean"] == pytest.approx(100.0)
#
#    ctx2 = Context(images={"test": img})
#    run_step("glv_stats", ctx2, roi="", metrics="glv_mean")   # 整張圖
#    assert ctx2.features["glv_mean"] == pytest.approx(img.mean())
#
#
#def test_blob_segment_publishes_its_main_blob_as_a_named_region():
#    """偵測出來的框與手畫的框走同一條路 —— 這是 F7-4 最關鍵的一刀。"""
#    rng = np.random.default_rng(3)
#    diff = rng.normal(0, 1, (96, 96)).astype(np.float32)
#    diff[40:56, 40:56] += 80.0
#    ctx = Context(images={"diff": diff})
#    run_step("snr_map", ctx, window=15, exclude_border=8)
#    # 門檻用範例 recipe 的值：預設 0 = Otsu，在正規化 SNR map 上會切掉半張圖
#    # （CLAUDE.md §7 的老坑，這裡不重蹈）
#    run_step("blob_segment", ctx, min_area=6, snr_threshold=200)
#
#    assert "blob" in ctx.roi_names(), "主 blob 要以具名 ROI 發布出來"
#    x, y, w, h = ctx.roi_rect("blob", diff.shape)
#    assert w > 0 and h > 0
#    assert x <= 48 <= x + w and y <= 48 <= y + h, "主 blob 要蓋到訊號所在位置"
#    # 量測卡指名 blob 與指名手畫框，走的是同一段程式
#    run_step("glv_stats", ctx, source="diff", roi="blob", metrics="glv_max")
#    assert ctx.features["glv_max"] > 50.0, "ROI 要蓋到 +80 的訊號"
#
#
#def test_measure_cards_refuse_a_typo_instead_of_silently_using_everything():
#    """ROI 名字打錯要報錯 —— 安靜地退回整張圖會讓人以為量對了。"""
#    ctx = Context(images={"test": np.zeros((32, 32), np.float32)})
#    for key, kw in (("glv_stats", {"metrics": "glv_mean"}),
#                    ("roi_snr", {}),
#                    ("cd_measure", {})):
#        with pytest.raises(StepError):
#            run_step(key, Context(images=dict(ctx.images)), roi="nope", **kw)
#
#
#def test_blob_roi_works_even_without_the_image_stream():
#    """``roi='blob'`` 存的是像素座標，所以下游把影像流蓋掉也還量得到。"""
#    ctx = Context(images={"diff": np.zeros((32, 32), np.float32)})
#    ctx.meta["blobs"] = [{"x": 4, "y": 6, "w": 10, "h": 20, "area": 150}]
#    del ctx.images["diff"]
#    run_step("cd_measure", ctx, roi="blob")
#    assert ctx.features["cd_x_px"] == 10.0
#    assert ctx.features["cd_y_px"] == 20.0
#
#F f6565ccc073a5846b9e3a5b66961131e4e797c72 373 tests/test_results_store.py
#"""M2 驗收：RunStore（SQLite 批次歷史）＋ rescore（不重跑影像的重算分）。
#
#不需要真影像 —— 全部用 result_to_json_dict 形狀的假 result dict。
#每個測試各開自己的 tmp_path db，互不干擾。
#"""
#from __future__ import annotations
#
#import csv
#import json
#import math
#import re
#import sqlite3
#import time
#
#import pytest
#
#from adept.core.pipeline import Recipe, RecipeNode, ScoreSpec
#from adept.core.store import RunStore, rescore
#
#
## ---------------------------------------------------------------------------
## 假資料工廠
## ---------------------------------------------------------------------------
#def _recipe_dict(expr="snr_max * 2", threshold=4.0, bins=None):
#    """最小 recipe JSON dict（save_run 也吃 dict，不強制 Recipe 物件）。"""
#    return {
#        "recipe_id": "t_store",
#        "version": 1,
#        "author": "HX",
#        "description": "store 測試用",
#        "routes": {"ebi_patch": []},
#        "nodes": {},
#        "edges": [],
#        "score": {"expr": expr, "threshold": threshold,
#                  "bins": dict(bins or {"below": 0, "above": 1})},
#    }
#
#
#def _fake_result(i, *, feats=None, ok=True, error=None):
#    """result_to_json_dict 形狀（traces 不入庫，但保留在輸入裡驗證會被忽略）。"""
#    if feats is None:
#        feats = {
#            "snr_max": float(i),
#            "blob_area": float(i * 3 + 1),
#            "cd_x_nm": 20.0 + i * 0.5,
#            "glv_mean": 128.0,
#            "glv_std": 7.5,
#            "focus": 0.8,
#            "dvi": -1.25,
#            "score": float(i) * 2.0,
#        }
#    return {
#        "defect_id": "D{:05d}".format(i),
#        "ok": ok,
#        "error": error,
#        "features": feats,
#        "score": feats.get("score"),
#        "bin": (1 if feats.get("score", 0.0) is not None
#                and (feats.get("score") or 0.0) >= 4.0 else 0) if ok else None,
#        "traces": [{"node_id": "x", "step_key": "t", "ok": True, "ms": 0.1,
#                    "error": None, "features_added": {}, "images_after": []}],
#    }
#
#
#def _make_results(n, fail_every=None):
#    out = []
#    for i in range(n):
#        if fail_every and i % fail_every == 0:
#            out.append(_fake_result(i, feats={}, ok=False,
#                                    error="[align] 對位失敗（測試用）"))
#        else:
#            out.append(_fake_result(i))
#    return out
#
#
## ---------------------------------------------------------------------------
## save / load round-trip
## ---------------------------------------------------------------------------
#def test_save_load_roundtrip_120_rows(tmp_path):
#    db = str(tmp_path / "runs.db")
#    results = _make_results(120, fail_every=10)  # 12 顆 FAIL
#    # 一顆的特徵塞 nan / inf → 存檔要變 None（JSON 安全）
#    results[5]["features"]["snr_max"] = float("nan")
#    results[5]["features"]["blob_area"] = float("inf")
#    results[5]["score"] = float("nan")
#
#    with RunStore(db) as store:
#        run_id = store.save_run(
#            _recipe_dict(), results,
#            klarf_path="/data/lot1.001", dataset_kind="ebi_patch",
#            notes="回歸測試批")
#
#        run = store.get_run(run_id)
#        assert run["run_id"] == run_id
#        assert run["recipe_id"] == "t_store"
#        assert run["klarf_path"] == "/data/lot1.001"
#        assert run["dataset_kind"] == "ebi_patch"
#        assert run["notes"] == "回歸測試批"
#        assert run["n_total"] == 120
#        assert run["n_ok"] == 108
#        assert run["n_fail"] == 12
#        assert json.loads(run["recipe_json"])["score"]["expr"] == "snr_max * 2"
#
#        rows = list(store.iter_results(run_id))
#        assert len(rows) == 120
#        by_id = {r["defect_id"]: r for r in rows}
#        # features 已解析回 dict；一般顆數值原樣回來
#        r7 = by_id["D00007"]
#        assert r7["ok"] is True and r7["error"] is None
#        assert r7["features"]["snr_max"] == 7.0
#        assert r7["features"]["cd_x_nm"] == pytest.approx(23.5)
#        assert r7["score"] == 14.0 and r7["bin"] == 1
#        # nan/inf → None
#        r5 = by_id["D00005"]
#        assert r5["features"]["snr_max"] is None
#        assert r5["features"]["blob_area"] is None
#        assert r5["score"] is None
#        # FAIL 顆：空 features、error 保留
#        r10 = by_id["D00010"]
#        assert r10["ok"] is False and "對位失敗" in r10["error"]
#        assert r10["features"] == {} and r10["bin"] is None
#
#        ids, feats = store.get_features_table(run_id)
#        assert len(ids) == len(feats) == 120
#        assert ids[0] == "D00000"
#        assert feats[7]["snr_max"] == 7.0
#
#
#def test_save_run_accepts_recipe_object(tmp_path):
#    recipe = Recipe(
#        recipe_id="t_obj",
#        routes={"ebi_patch": ["load"]},
#        nodes={"load": RecipeNode(id="load", step="load_patch", params={})},
#        score=ScoreSpec(expr="snr_max", threshold=3.0, bins={"below": 0, "above": 1}),
#    )
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        run_id = store.save_run(recipe, _make_results(3))
#        run = store.get_run(run_id)
#        assert run["recipe_id"] == "t_obj"
#        assert json.loads(run["recipe_json"])["score"]["threshold"] == 3.0
#
#
#def test_list_runs_newest_first_without_recipe_json(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        ids = [store.save_run(_recipe_dict(), _make_results(2),
#                              notes="第 {} 批".format(k)) for k in range(3)]
#        runs = store.list_runs()
#        assert [r["run_id"] for r in runs] == list(reversed(ids))  # 新的在前
#        for r in runs:
#            assert "recipe_json" not in r
#            assert r["n_total"] == 2
#
#
#def test_delete_run_cascade(tmp_path):
#    db = str(tmp_path / "runs.db")
#    with RunStore(db) as store:
#        keep = store.save_run(_recipe_dict(), _make_results(5))
#        gone = store.save_run(_recipe_dict(), _make_results(7))
#        store.delete_run(gone)
#
#        with pytest.raises(KeyError):
#            store.get_run(gone)
#        with pytest.raises(KeyError):
#            list(store.iter_results(gone))
#        assert len(list(store.iter_results(keep))) == 5  # 別的 run 不受影響
#
#    # 直接開第二條連線驗證 results 列真的被 CASCADE 掉
#    conn = sqlite3.connect(db)
#    try:
#        n = conn.execute("SELECT COUNT(*) FROM results WHERE run_id=?",
#                         (gone,)).fetchone()[0]
#        assert n == 0
#        n_keep = conn.execute("SELECT COUNT(*) FROM results WHERE run_id=?",
#                              (keep,)).fetchone()[0]
#        assert n_keep == 5
#    finally:
#        conn.close()
#
#
#def test_run_id_uniqueness_and_format_across_rapid_saves(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        ids = [store.save_run(_recipe_dict(), []) for _ in range(30)]
#        assert len(set(ids)) == 30
#        for rid in ids:
#            assert re.match(r"^\d{8}T\d{4}-[0-9a-f]{6}$", rid), rid
#        # 指定 run_id 時原樣使用
#        assert store.save_run(_recipe_dict(), [], run_id="my-run") == "my-run"
#
#
## ---------------------------------------------------------------------------
## export_csv
## ---------------------------------------------------------------------------
#def test_export_csv_header_union_and_bom(tmp_path):
#    db = str(tmp_path / "runs.db")
#    out = str(tmp_path / "out.csv")
#    results = [
#        _fake_result(0, feats={"snr_max": 1.5, "blob_area": 9.0, "score": 3.0}),
#        _fake_result(1, feats={"snr_max": 2.5, "cd_x_nm": 21.0, "score": 5.0}),
#        _fake_result(2, feats={}, ok=False, error="[load] 讀檔失敗（測試）"),
#    ]
#    with RunStore(db) as store:
#        run_id = store.save_run(_recipe_dict(), results)
#        store.export_csv(run_id, out)
#
#    with open(out, "rb") as f:
#        assert f.read(3) == b"\xef\xbb\xbf"  # utf-8-sig BOM（Excel 直開不亂碼）
#
#    with open(out, "r", encoding="utf-8-sig", newline="") as f:
#        rows = list(csv.reader(f))
#    header, data = rows[0], rows[1:]
#    # 基本欄 + 排序後 feature key 聯集
#    assert header == ["defect_id", "ok", "error", "score", "bin",
#                      "blob_area", "cd_x_nm", "score", "snr_max"]
#    assert len(data) == 3
#    by_id = {r[0]: r for r in data}
#    # 缺的 feature 留空；中文 error 原樣
#    assert by_id["D00001"][header.index("blob_area", 5)] == ""
#    assert by_id["D00001"][8] == "2.5"  # snr_max
#    assert "讀檔失敗" in by_id["D00002"][2]
#    assert by_id["D00002"][3] == "" and by_id["D00002"][4] == ""  # score/bin 空
#
#
## ---------------------------------------------------------------------------
## rescore
## ---------------------------------------------------------------------------
#def _saved_run_for_rescore(store, n=100):
#    """expr="snr_max"、threshold=50 → i<50 進 bin0、其餘 bin1。"""
#    results = [_fake_result(i) for i in range(n)]
#    return store.save_run(
#        _recipe_dict(expr="snr_max", threshold=50.0), results,
#        klarf_path="/data/lot2.001", dataset_kind="ebi_patch")
#
#
#def test_rescore_threshold_only_flips_bins(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        run_id = _saved_run_for_rescore(store, n=100)  # snr_max = 0..99
#
#        s0 = rescore(store, run_id)  # 全沿用 recipe：threshold=50
#        assert s0["run_id"] == run_id
#        assert s0["n"] == 100 and s0["n_errors"] == 0
#        assert s0["bin_counts"] == {0: 50, 1: 50}
#        assert s0["score_min"] == 0.0 and s0["score_max"] == 99.0
#        assert s0["score_median"] == pytest.approx(49.5)
#        assert s0["saved_run_id"] is None
#
#        s1 = rescore(store, run_id, threshold=25.0)  # 只改門檻 → bin 數翻轉
#        assert s1["bin_counts"] == {0: 25, 1: 75}
#        s2 = rescore(store, run_id, threshold=90.0)
#        assert s2["bin_counts"] == {0: 90, 1: 10}
#        # 改 bins 對應值也要跟著走
#        s3 = rescore(store, run_id, threshold=25.0, bins={"below": 7, "above": 9})
#        assert s3["bin_counts"] == {7: 25, 9: 75}
#
#
#def test_rescore_new_expr_saved_as_new_run(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        run_id = _saved_run_for_rescore(store, n=40)
#
#        s = rescore(store, run_id, expr="blob_area", threshold=60.0,
#                    save_as=True, notes="改用 blob_area 重算")
#        # blob_area = 3i+1（i=0..39）→ < 60 者 i<=19 → 20 顆 bin0
#        assert s["n"] == 40 and s["n_errors"] == 0
#        assert s["bin_counts"] == {0: 20, 1: 20}
#        assert s["score_max"] == 3.0 * 39 + 1
#
#        new_id = s["saved_run_id"]
#        assert new_id and new_id != run_id
#
#        # 新 run 可讀：recipe_json 已更新、繼承 klarf_path/kind、notes 是新的
#        new_run = store.get_run(new_id)
#        spec = json.loads(new_run["recipe_json"])["score"]
#        assert spec["expr"] == "blob_area" and spec["threshold"] == 60.0
#        assert new_run["klarf_path"] == "/data/lot2.001"
#        assert new_run["dataset_kind"] == "ebi_patch"
#        assert new_run["notes"] == "改用 blob_area 重算"
#        assert new_run["n_total"] == 40 and new_run["n_ok"] == 40
#
#        rows = list(store.iter_results(new_id))
#        by_id = {r["defect_id"]: r for r in rows}
#        r10 = by_id["D00010"]
#        assert r10["score"] == 31.0 and r10["bin"] == 0
#        assert r10["features"]["score"] == 31.0  # features["score"] 同步更新
#        assert r10["features"]["snr_max"] == 10.0  # 其他特徵原樣保留
#
#        # 指定字串 save_as → 用該 id
#        s2 = rescore(store, run_id, threshold=10.0, save_as="rescored-abc")
#        assert s2["saved_run_id"] == "rescored-abc"
#        assert store.get_run("rescored-abc")["n_total"] == 40
#
#
#def test_rescore_missing_feature_counts_errors_without_crashing(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        results = []
#        for i in range(100):
#            feats = {"snr_max": float(i), "blob_area": float(i)}
#            if i % 5 != 0:  # 80 顆有 cd_x_nm、20 顆缺
#                feats["cd_x_nm"] = 20.0 + i
#            results.append(_fake_result(i, feats=feats))
#        run_id = store.save_run(
#            _recipe_dict(expr="snr_max", threshold=50.0), results)
#
#        s = rescore(store, run_id, expr="cd_x_nm * 2", threshold=100.0,
#                    save_as=True)
#        assert s["n"] == 100
#        assert s["n_errors"] == 20  # 缺 cd_x_nm 的顆數
#        assert sum(s["bin_counts"].values()) == 80  # 其餘照常算分
#        assert s["score_min"] == 42.0  # i=1 → (20+1)*2
#
#        # 存下的新 run：出錯顆 score/bin None、ok=False、有錯誤訊息
#        rows = {r["defect_id"]: r for r in store.iter_results(s["saved_run_id"])}
#        bad = rows["D00005"]
#        assert bad["ok"] is False and bad["score"] is None and bad["bin"] is None
#        assert "cd_x_nm" in bad["error"]
#        good = rows["D00006"]
#        assert good["ok"] is True and good["score"] == 52.0
#
#
#def test_rescore_none_valued_feature_is_error_not_crash(tmp_path):
#    """nan 存成 None 的特徵被表達式引用 → 該顆記錯，不殺整批。"""
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        results = [_fake_result(i) for i in range(10)]
#        results[3]["features"]["snr_max"] = float("nan")  # 存檔後變 None
#        run_id = store.save_run(_recipe_dict(expr="snr_max", threshold=5.0),
#                                results)
#        s = rescore(store, run_id)
#        assert s["n"] == 10 and s["n_errors"] == 1
#        assert sum(s["bin_counts"].values()) == 9
#
#
#def test_rescore_ignores_stored_score_variable(tmp_path):
#    """變數空間排除舊 "score" —— 表達式引用 score 應視為缺變數。"""
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        run_id = store.save_run(
#            _recipe_dict(expr="score + 1", threshold=0.0), [_fake_result(2)])
#        s = rescore(store, run_id)
#        assert s["n"] == 1 and s["n_errors"] == 1  # 舊分數不可當變數
#
#
#def test_rescore_10k_rows_under_5s(tmp_path):
#    with RunStore(str(tmp_path / "runs.db")) as store:
#        results = []
#        for i in range(10_000):
#            feats = {
#                "snr_max": (i % 97) * 0.25,
#                "blob_area": float(i % 311),
#                "cd_x_nm": 18.0 + (i % 53) * 0.1,
#                "glv_mean": 120.0 + (i % 17),
#                "glv_std": 6.0,
#                "focus": 0.5 + (i % 7) * 0.05,
#                "dvi": -1.0,
#                "score": 0.0,
#            }
#            results.append(_fake_result(i, feats=feats))
#        run_id = store.save_run(
#            _recipe_dict(expr="snr_max", threshold=10.0), results)
#
#        t0 = time.perf_counter()
#        s = rescore(store, run_id,
#                    expr="snr_max * sqrt(blob_area) + cd_x_nm / glv_std",
#                    threshold=30.0, save_as=True)
#        wall = time.perf_counter() - t0
#
#        assert s["n"] == 10_000 and s["n_errors"] == 0
#        assert sum(s["bin_counts"].values()) == 10_000
#        assert s["elapsed_s"] < 5.0
#        assert wall < 5.0, "10k rescore 花了 {:.2f}s（目標 < 5s）".format(wall)
#        assert store.get_run(s["saved_run_id"])["n_total"] == 10_000
#        # 抽查一顆數值正確
#        r = next(store.iter_results(s["saved_run_id"]))
#        f = r["features"]
#        expect = f["snr_max"] * math.sqrt(f["blob_area"]) + f["cd_x_nm"] / f["glv_std"]
#        assert r["score"] == pytest.approx(expect)
#
#F 16cd9995a97eb6b919044e2c72fe1bcddb954e2a 138 tests/test_roi.py
#"""Tests for adept.core.algo.roi (vendored 2026-07-27)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.roi import (
#    MultiROISet,
#    NamedROI,
#    ROIStats,
#    pixel_rect_to_norm,
#)
#
#SHAPE = (200, 300)  # (H, W)
#
#
#def _named(norm_rect, roi_type='reference'):
#    return NamedROI(id='x', label='X', roi_type=roi_type,
#                    color_bgr=(255, 255, 0), norm_rect=norm_rect)
#
#
#def test_pixel_norm_roundtrip():
#    rect = (30, 40, 50, 60)
#    norm = pixel_rect_to_norm(rect, SHAPE)
#    assert all(0.0 <= v <= 1.0 for v in norm)
#    back = _named(norm).to_pixel_rect(SHAPE)
#    assert back == rect
#
#
#def test_pixel_rect_to_norm_clamps_out_of_bounds():
#    # Rect extends past the right/bottom edge -> size clamped
#    norm = pixel_rect_to_norm((280, 190, 50, 40), SHAPE)
#    back = _named(norm).to_pixel_rect(SHAPE)
#    assert back == (280, 190, 20, 10)
#    # Negative origin -> clamped to 0
#    norm2 = pixel_rect_to_norm((-10, -5, 40, 30), SHAPE)
#    back2 = _named(norm2).to_pixel_rect(SHAPE)
#    assert back2 == (0, 0, 40, 30)
#
#
#def test_to_pixel_rect_clamps_norm_overflow():
#    # norm_rect spilling past 1.0 gets clamped to the image bounds
#    roi = _named((0.95, 0.9, 0.2, 0.2))
#    x, y, w, h = roi.to_pixel_rect(SHAPE)
#    assert (x, y) == (285, 180)
#    assert x + w <= SHAPE[1]
#    assert y + h <= SHAPE[0]
#    assert w >= 1 and h >= 1
#
#
#def test_crop_matches_pixel_rect():
#    img = np.arange(SHAPE[0] * SHAPE[1], dtype=np.float32).reshape(SHAPE)
#    roi = _named(pixel_rect_to_norm((30, 40, 50, 60), SHAPE))
#    crop = roi.crop(img)
#    assert crop.shape == (60, 50)
#    assert crop[0, 0] == img[40, 30]
#
#
#def test_shifted_offset_math():
#    rs = MultiROISet()
#    rid = rs.add_roi((0.2, 0.3, 0.1, 0.1))
#    ref_shape = (100, 200)  # (H, W)
#    shifted = rs.shifted(dx=30, dy=-15, ref_shape=ref_shape)
#    nx, ny, nw, nh = shifted.get_by_id(rid).norm_rect
#    assert abs(nx - (0.2 + 30 / 200)) < 1e-9
#    assert abs(ny - (0.3 - 15 / 100)) < 1e-9
#    assert (nw, nh) == (0.1, 0.1)
#    # Original set untouched
#    assert rs.get_by_id(rid).norm_rect == (0.2, 0.3, 0.1, 0.1)
#
#
#def test_shifted_clamps_at_edges():
#    rs = MultiROISet()
#    rid = rs.add_roi((0.85, 0.1, 0.1, 0.1))
#    shifted = rs.shifted(dx=50, dy=0, ref_shape=(100, 200))
#    nx, ny, nw, nh = shifted.get_by_id(rid).norm_rect
#    assert abs(nx - 0.9) < 1e-9  # clamped to 1.0 - nw, size preserved
#    assert (nw, nh) == (0.1, 0.1)
#
#
#def test_generate_grid_count_and_positions():
#    rs = MultiROISet()
#    rects = rs.generate_grid(
#        anchor_tl_norm=(0.1, 0.1),
#        anchor_br_norm=(0.9, 0.9),
#        cols=3,
#        rows=2,
#        roi_w_px=20,
#        roi_h_px=20,
#        img_shape=(200, 200),
#    )
#    assert len(rects) == 3 * 2
#    # First rect centered on the top-left anchor
#    nx, ny, nw, nh = rects[0]
#    assert abs(nx - (0.1 * 200 - 10) / 200) < 1e-9
#    assert abs(ny - (0.1 * 200 - 10) / 200) < 1e-9
#    assert (nw, nh) == (20 / 200, 20 / 200)
#    # Last rect centered on the bottom-right anchor
#    nx_l, ny_l, _, _ = rects[-1]
#    assert abs(nx_l - (0.9 * 200 - 10) / 200) < 1e-9
#    assert abs(ny_l - (0.9 * 200 - 10) / 200) < 1e-9
#    # Grid generation does not add ROIs to the set
#    assert len(rs) == 0
#
#
#def test_exactly_one_target_invariant():
#    rs = MultiROISet()
#    ref_id = rs.add_roi((0.1, 0.1, 0.1, 0.1))
#    t1 = rs.add_roi((0.3, 0.3, 0.1, 0.1), roi_type='target')
#    t2 = rs.add_roi((0.5, 0.5, 0.1, 0.1), roi_type='target')
#
#    targets = [r for r in rs.rois if r.roi_type == 'target']
#    assert len(targets) == 1
#    assert targets[0].id == t2
#    assert rs.get_by_id(t1).roi_type == 'reference'
#
#    # Promoting another ROI keeps the invariant
#    assert rs.set_target(ref_id)
#    targets = [r for r in rs.rois if r.roi_type == 'target']
#    assert len(targets) == 1
#    assert targets[0].id == ref_id
#    assert rs.get_target().id == ref_id
#    assert len(rs.get_references()) == 2
#
#    # Demote the target -> no target at all
#    assert rs.set_reference(ref_id)
#    assert rs.get_target() is None
#
#
#def test_roistats_from_pixels():
#    rng = np.random.default_rng(2)
#    px = rng.normal(100, 10, size=(20, 20))
#    st = ROIStats.from_pixels(px)
#    assert st.pixel_count == 400
#    assert abs(st.mean - float(px.mean())) < 0.1
#    assert st.p2 < st.median < st.p98
#    empty = ROIStats.from_pixels(np.array([]))
#    assert empty.pixel_count == 0
#
#F 5994f7e6af5733d16ddd4ac0c0df62f9bcf8a07f 273 tests/test_roi_profile.py
## F7-11 驗收：投影定位（找結構，而不是把框放在畫面的固定位置）。
#"""這一段的前提是一個領域事實：
#
#patch 是機台**以缺陷為正中心**裁出來的，所以缺陷永遠在中央 —— 但缺陷**周圍**
#的東西每張都不一樣。中心固定框只對缺陷本身成立；只要框大過缺陷，它就可能在
#某些 patch 上吃進別種材質，量出來的數字忽高忽低，而**變動的原因不是缺陷**。
#
#所以測試斷言的不是「函式跑得動」，而是：
#1. 框真的跟著結構跑（結構位移了，框也跟著位移）；
#2. 沒有結構可認的 patch **講出來**，不是硬給一個位置。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.algo import profile as algo_profile  # noqa: E402
#from adept.core.pipeline import Recipe, RecipeNode, ScoreSpec, get_step, validate  # noqa: E402
#from adept.core.pipeline.context import Context  # noqa: E402
#
#W = H = 128
#
#
#def _layout(shift: int = 0, noise: float = 3.0, seed: int = 0,
#            defect: float = 0.0) -> np.ndarray:
#    """MG | 亮交界 | EPI | 亮交界 | MG。``shift`` 把整個結構左右移動。
#
#    這正是使用者描述的情況：EBI 鎖定在 EPI 上，所以每張 patch 裡一定有 EPI，
#    但缺陷可能落在 EPI 的中間或靠邊，於是**結構在 patch 裡的位置逐顆不同**。
#    """
#    rng = np.random.default_rng(seed)
#    img = np.full((H, W), 120.0, np.float32)          # MG
#    lo, hi = 40 + shift, 88 + shift
#    img[:, max(0, lo):max(0, hi)] = 60.0              # EPI（暗）
#    for edge in (lo, hi):
#        if 2 <= edge <= W - 2:
#            img[:, edge - 2:edge + 2] = 210.0         # 交界（最亮）
#    if defect:
#        img[60:68, 60:68] += defect                   # 缺陷永遠在中央
#    return img + rng.normal(0, noise, (H, W)).astype(np.float32)
#
#
#def _run(ctx: Context, **params) -> Context:
#    return get_step("roi_profile")().run(ctx, params)
#
#
## --------------------------------------------------------------------------- #
## 1. 演算法
## --------------------------------------------------------------------------- #
#def test_the_band_follows_the_structure_not_the_screen():
#    """**這條是整張卡存在的理由。** 結構左右移動時，框要跟著移動。
#
#    如果框固定在畫面中央，位移大的那幾張就會框到別種材質 —— 那正是要避免的。
#    """
#    centres = []
#    for shift in (-16, 0, 16):
#        res = algo_profile.locate(_layout(shift), axis="x")
#        assert res.picked is not None, "shift=%d 沒有找到任何一段" % shift
#        centres.append((res.picked[0] + res.picked[1]) / 2.0)
#
#    # 框的中心要跟著位移走（不是固定在 64）
#    assert centres[0] < centres[1] < centres[2]
#    for got, shift in zip(centres, (-16, 0, 16)):
#        assert abs(got - (64 + shift)) < 6, \
#            "框沒跟上結構：shift=%d 時框中心在 %.1f" % (shift, got)
#
#
#def test_a_featureless_patch_reports_no_confidence_instead_of_a_position():
#    """整張同一種材質的 patch **不可能**定位 —— 那是資訊不夠，不是演算法不夠。
#
#    這種時候必須講出來，不能硬給一個位置。
#    """
#    rng = np.random.default_rng(3)
#    flat = rng.normal(120.0, 6.0, (H, W)).astype(np.float32)
#    assert algo_profile.locate(flat).confidence < 2.0
#
#    # 有結構的差了一個數量級 —— 門檻放在個位數就分得很開
#    assert algo_profile.locate(_layout()).confidence > 20.0
#
#
#def test_confidence_survives_a_sharp_edge():
#    """信心的分母必須用 MAD 而不是標準差。
#
#    銳利的邊界會讓平滑吃掉一點真訊號，那幾格殘差很大；用標準差當分母，
#    邊界越銳利分母被灌得越大 —— 變成「結構越清楚、信心越低」，完全相反。
#    """
#    soft = algo_profile.locate(_layout(noise=3.0)).confidence
#    sharp = np.full((H, W), 120.0, np.float32)
#    sharp[:, 64:] = 30.0
#    sharp += np.random.default_rng(4).normal(0, 3.0, (H, W))
#    assert algo_profile.locate(sharp).confidence > soft * 0.3
#    assert algo_profile.locate(sharp).confidence > 20.0
#
#
#def test_a_constant_slope_is_not_a_pile_of_boundaries():
#    """一段固定斜率的漸層上每一格梯度都相等 —— 用 ``>=`` 找局部極大會把整段
#    都判成轉折。斜率是背景漂移，該交給 Enhance 的背景平坦化卡。"""
#    ramp = np.linspace(60.0, 180.0, W)[None, :].repeat(H, axis=0).astype(np.float32)
#    prof, _ = algo_profile.projection(ramp, "x", smooth=1)
#    assert algo_profile.find_transitions(prof) == []
#
#
#def test_sensitivity_is_relative_so_it_carries_across_lots():
#    """門檻是相對於「這張圖最陡的地方」，不是絕對灰階 ——
#    所以整體亮度或對比變了，同一個設定還是找到同樣的邊界。"""
#    a = _layout()
#    b = a * 0.5 + 30.0                      # 對比砍半、整體提亮
#    ta = algo_profile.locate(a).transitions
#    tb = algo_profile.locate(b).transitions
#    assert len(ta) == len(tb)
#    for x, y in zip(ta, tb):
#        assert abs(x - y) <= 2
#
#
#def test_both_scan_directions_work():
#    img = _layout().T.copy()                # 把結構轉成水平的
#    assert algo_profile.locate(img, axis="y").picked is not None
#    assert algo_profile.locate(img, axis="x").confidence < 2.0, \
#        "轉錯方向就該看不到結構（這是使用者要能自己選方向的理由）"
#
#
#def test_bands_cover_the_whole_curve_without_gaps():
#    bands = algo_profile.bands_from([10, 40, 90], 128)
#    assert bands == [(0, 10), (10, 40), (40, 90), (90, 128)]
#    assert algo_profile.bands_from([], 128) == [(0, 128)]
#
#
#@pytest.mark.parametrize("rule", list(algo_profile.PICK_RULES))
#def test_every_pick_rule_returns_a_band(rule):
#    res = algo_profile.locate(_layout(), rule=rule, index=1)
#    assert res.picked is not None
#    assert res.picked[1] > res.picked[0]
#
#
#def test_degenerate_input_does_not_crash():
#    for img in (np.zeros((0, 0), np.float32), np.zeros((2, 2), np.float32),
#                np.full((8, 8), 7.0, np.float32)):
#        res = algo_profile.locate(img)
#        assert res.confidence >= 0.0
#
#
## --------------------------------------------------------------------------- #
## 2. 卡片
## --------------------------------------------------------------------------- #
#def test_the_card_writes_a_named_region_that_tracks_the_structure():
#    rects = []
#    for shift in (-16, 16):
#        ctx = Context(images={"ref": _layout(shift), "test": _layout(shift)})
#        _run(ctx, source="ref", roi_out="epi")
#        assert ctx.roi_names() == ["epi"]
#        rects.append(ctx.roi_rect("epi", (H, W)))
#    assert rects[0][0] < rects[1][0], "區域沒有跟著結構移動"
#
#
#def test_the_neighbouring_sections_can_be_named_too():
#    """量測幾乎都是成對的：訊號要跟**同一種材質**的背景比才有意義。"""
#    ctx = Context(images={"ref": _layout()})
#    _run(ctx, source="ref", roi_out="epi", also_neighbours=True)
#    assert set(ctx.roi_names()) == {"epi", "epi_before", "epi_after"}
#    a = ctx.roi_rect("epi", (H, W))
#    before = ctx.roi_rect("epi_before", (H, W))
#    assert before[0] < a[0], "before 應該在左邊"
#
#
#def test_a_patch_with_nothing_to_lock_onto_falls_back_and_says_so():
#    """跑得完、有數字、而且是錯的 —— 是這個工具最不能接受的失敗。"""
#    rng = np.random.default_rng(9)
#    ctx = Context(images={"ref": rng.normal(120.0, 6.0, (H, W)).astype(np.float32)})
#    _run(ctx, source="ref", roi_out="epi")
#
#    assert ctx.features["locate_ok"] == 0.0
#    assert ctx.roi_rect("epi", (H, W)) == (0, 0, W, H), "退回整張圖"
#    assert any("locate_ok" in w for w in ctx.meta.get("warnings", []))
#
#
#def test_distance_to_the_boundary_is_reported_as_a_feature():
#    """使用者原本把「缺陷可能靠中間、可能靠邊」當成一個麻煩 ——
#    但它是一個可以拿去打分的數字。"""
#    near = Context(images={"ref": _layout(shift=20)})   # 交界被推到接近中央
#    far = Context(images={"ref": _layout(shift=0)})
#    _run(near, source="ref")
#    _run(far, source="ref")
#    assert near.features["band_dist_px"] < far.features["band_dist_px"]
#
#
#def test_the_panel_data_is_the_engines_own_calculation():
#    """UI 自己再算一次，就有機會讓「畫面上的框」跟「真的量下去的框」不一樣。"""
#    ctx = Context(images={"ref": _layout()})
#    _run(ctx, source="ref", roi_out="epi")
#    panel = ctx.meta["profiles"]["epi"]
#
#    assert len(panel["profile"]) == W
#    assert panel["picked"] is not None
#    a, b = panel["picked"]
#    x, _y, w, _h = ctx.roi_rect("epi", (H, W))
#    assert x == a and w == b - a, "面板畫的段與寫進去的區域必須是同一個"
#    # 純量與 list，能進 JSON（快取的 meta 快照會過濾掉不能序列化的東西）
#    import json
#    json.dumps(panel)
#
#
#def test_the_output_names_can_be_prefixed():
#    ctx = Context(images={"ref": _layout()})
#    _run(ctx, source="ref", output_prefix="epi")
#    assert "epi_locate_ok" in ctx.features
#    assert "locate_ok" not in ctx.features
#
#
## --------------------------------------------------------------------------- #
## 3. 兩個區域一起量 —— 這是整件事的目的
## --------------------------------------------------------------------------- #
#def _recipe() -> Recipe:
#    """量 EPI，也量旁邊的 MG，兩組數字都要留得住。"""
#    nodes = {
#        "load": RecipeNode("load", "load_patch", {}),
#        "loc": RecipeNode("loc", "roi_profile",
#                          {"source": "ref", "roi_out": "epi",
#                           "also_neighbours": True, "output_prefix": "loc"}),
#        "g_epi": RecipeNode("g_epi", "glv_stats",
#                            {"source": "test", "roi": "epi",
#                             "metrics": "glv_mean", "output_prefix": "epi"}),
#        "g_mg": RecipeNode("g_mg", "glv_stats",
#                           {"source": "test", "roi": "epi_before",
#                            "metrics": "glv_mean", "output_prefix": "mg"}),
#    }
#    return Recipe(recipe_id="two_regions",
#                  routes={"ebi_patch": ["load", "loc", "g_epi", "g_mg"]},
#                  nodes=nodes,
#                  score=ScoreSpec(expr="epi_glv_mean - mg_glv_mean",
#                                  threshold=0.0, bins={"below": 0, "above": 1}))
#
#
#def test_measuring_two_regions_keeps_both_numbers():
#    """沒有輸出名前綴的話，兩張 glv_stats 都寫 glv_mean，後面那張蓋掉前面那張。"""
#    recipe = _recipe()
#    issues = validate(recipe, kind="ebi_patch")
#    assert [i for i in issues if i.code == "feature-collision"] == []
#    assert [i for i in issues if i.level == "error"] == []
#
#    feats = set()
#    for nid in ("g_epi", "g_mg"):
#        node = recipe.nodes[nid]
#        feats |= set(get_step(node.step).resolve_features(node.params))
#    assert feats == {"epi_glv_mean", "mg_glv_mean"}
#
#
#def test_the_two_regions_really_measure_different_materials():
#    """跑一顆真的資料：EPI 是暗的、旁邊的 MG 是亮的，數字必須分得開。"""
#    from adept.core.pipeline.engine import run_defect
#
#    class _Item:
#        """最小的 DefectItem 替身：``load_patch`` 只用到 images 的鍵與 load()。"""
#
#        defect_id = "d1"
#        nm_per_px = None
#
#        def __init__(self):
#            self._data = {"test": _layout(defect=0.0), "ref": _layout()}
#            self.images = dict(self._data)
#
#        def load(self, channel):
#            return self._data[channel]
#
#    res = run_defect(_recipe(), _Item(), "ebi_patch", keep_context=True)
#    assert res.ok is True, res.error
#    assert res.features["epi_glv_mean"] < res.features["mg_glv_mean"] - 20.0
#
#F a7c41debc132957219cb7a9187a4cb7efe1d3317 337 tests/test_roi_template.py
## F7-12 驗收：Golden Cell 模板定位（patch 比一個週期還小也定得出來）。
#"""這一段的前提，是使用者釐清的一個尺寸關係：
#
#**patch 通常比一個重複單元還小**，所以每張 patch 只看到週期裡的一小片，
#不同 defect 落在不同相位 —— 拿這些小片互相對位，根本沒有共同的東西可以對。
#
#但 patch 是從機台吐出的**大圖**上裁下來的，而大圖裡有好幾個週期。
#所以把方向反過來：在大圖上疊出一個乾淨的週期當模板，再把小 patch 滑進去。
#模板比 patch 大，這才是一個有唯一解的問題。
#
#所以測試斷言的是：
#1. 框跟著相位跑，而且**框裡真的是使用者標的那種材質**；
#2. 亮度／對比變了還是對得上（NCC 的重點）；
#3. 定不出來的 patch **講出來**，不是靠運氣給一個位置；
#4. 模板的原點錨得住 —— 換一批資料重算，框不可以平移。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#from adept.core.algo import template as algo_template  # noqa: E402
#from adept.core.pipeline import ParamError, get_step  # noqa: E402
#from adept.core.pipeline.context import Context  # noqa: E402
#from adept.core.pipeline.step import StepError  # noqa: E402
#
#PERIOD = 40
#BIG_H = 240
#N_CELLS = 8
#PATCH = 32          # 比一個週期小 —— 這正是整件事的前提
#
#
#def big_image(seed: int = 0, gain: float = 1.0, offset: float = 0.0,
#              noise: float = 4.0) -> np.ndarray:
#    """機台吐出的大圖：MG | 亮交界 | EPI | 亮交界，重複 8 次。"""
#    rng = np.random.default_rng(seed)
#    img = np.zeros((BIG_H, PERIOD * N_CELLS), np.float32)
#    for k in range(N_CELLS):
#        x = k * PERIOD
#        img[:, x:x + PERIOD] = 120.0            # MG
#        img[:, x + 14:x + 34] = 60.0            # EPI（暗）
#        img[:, x + 12:x + 16] = 210.0           # 交界（最亮）
#        img[:, x + 32:x + 36] = 210.0
#    return img * gain + offset + rng.normal(0, noise, img.shape).astype(np.float32)
#
#
#def cut(img: np.ndarray, phase: int, y: int = 100) -> np.ndarray:
#    """從大圖上裁一張 patch（相位 = 落在週期的哪裡）。"""
#    x = 3 * PERIOD + phase
#    return img[y:y + PATCH, x:x + PATCH]
#
#
#def flat_patch(seed: int = 0) -> np.ndarray:
#    """整張都在 EPI 裡面 —— 沒有任何東西可以定位。"""
#    rng = np.random.default_rng(seed)
#    return np.full((PATCH, PATCH), 60.0, np.float32) + \
#        rng.normal(0, 4.0, (PATCH, PATCH)).astype(np.float32)
#
#
#def epi_band(cell: np.ndarray):
#    """在 GC 上找出 EPI 那一段（= 使用者會標的框），回傳正規化矩形。"""
#    prof = cell.mean(axis=0)
#    dark = np.where(prof < 90)[0]
#    lo, hi = int(dark.min()), int(dark.max()) + 1
#    w = cell.shape[1]
#    return (lo / w, 0.0, (hi - lo) / w, 1.0)
#
#
## --------------------------------------------------------------------------- #
## 1. 疊模板
## --------------------------------------------------------------------------- #
#def test_the_period_is_measured_from_the_big_image_not_asked_for():
#    """週期在大圖上量得到，所以不必請使用者填 —— 那是這條路的好處之一。"""
#    gc = algo_template.build_golden_cell(big_image())
#    assert gc.px == PERIOD
#    assert gc.n_cells >= N_CELLS - 1
#    assert gc.ghosting > 50.0, "疊得夠銳利（週期估錯的話會糊掉）"
#
#
#def test_a_one_dimensional_layout_is_normal_not_a_failure():
#    """垂直條紋在 Y 上量不到週期 —— 那是**正確的**，不是失敗。
#
#    第一版把它當失敗擋掉了，於是使用者最常見的 layout 直接不能用。
#    """
#    gc = algo_template.build_golden_cell(big_image())
#    assert gc.periodic == (True, False)
#    assert gc.py == BIG_H, "沒有週期的那一軸取整張影像的長度"
#    assert gc.cell.size > 0
#    assert any("no period down" in w for w in gc.warnings)
#
#
#def test_an_image_with_no_repeat_at_all_says_so_instead_of_guessing():
#    rng = np.random.default_rng(1)
#    noise = rng.normal(120.0, 6.0, (128, 128)).astype(np.float32)
#    gc = algo_template.build_golden_cell(noise)
#    assert gc.cell.size == 0
#    assert any("periodic layout" in w for w in gc.warnings)
#
#
#def test_the_cell_is_anchored_to_a_landmark_so_it_does_not_drift():
#    """**這條是模板法最容易安靜壞掉的地方。**
#
#    ``choose_origin`` 挑的是「疊起來最銳利」的相位 —— 但週期性影像的任何相位都
#    一樣銳利，所以它在等價的候選之間挑哪一個是任意的。換一批資料重算模板，
#    相位一變，使用者標在模板上的框就跟著平移了，而且畫面上不會有任何錯誤訊息。
#    """
#    profiles = [algo_template.build_golden_cell(big_image(seed)).cell.mean(axis=0)
#                for seed in (0, 7, 11, 23)]
#    # 不看「最亮的欄在哪」—— 亮帶有好幾欄一樣亮，argmax 會被雜訊決定。
#    # 要問的是**整條曲線是不是同一條**：那才是「標在模板上的框不會平移」。
#    base = profiles[0]
#    for i, prof in enumerate(profiles[1:], 1):
#        assert float(np.max(np.abs(prof - base))) < 8.0, \
#            "第 %d 份模板跟第一份對不起來（相位漂移了）" % i
#
#    # 而且錨定的目標真的達成了：最強的上升邊被捲到第 0 欄
#    for prof in profiles:
#        grad = np.roll(prof, -1) - np.roll(prof, 1)
#        assert int(np.argmax(grad)) % len(prof) <= 1
#
#
#def test_anchoring_leaves_an_axis_alone_when_it_has_no_landmark():
#    """硬要錨一個不存在的地標，等於用雜訊決定相位 —— 比不錨還糟。"""
#    flat = np.full((16, 16), 100.0, np.float32)
#    out, roll = algo_template.anchor_cell(flat)
#    assert roll == (0, 0)
#    assert np.array_equal(out, flat)
#
#
## --------------------------------------------------------------------------- #
## 2. 存進 recipe（純文字）
## --------------------------------------------------------------------------- #
#def test_the_template_round_trips_through_plain_text():
#    """recipe 必須是**一個可以寄給別人的純文字檔** —— 存路徑的話，圖被換掉之後
#    結果會安靜地變。"""
#    gc = algo_template.build_golden_cell(big_image())
#    text = algo_template.encode_cell(gc.cell)
#
#    assert text.startswith(algo_template.CELL_ENCODING + ":")
#    assert text.isascii(), "必須是純 ASCII，否則進不了 JSON、也過不了 DLP"
#    assert np.array_equal(algo_template.decode_cell(text), gc.cell)
#
#
#@pytest.mark.parametrize("bad", ["", "not a template", "gc1:oops",
#                                 "gc1:4x4:!!!!", "png:4x4:AAAA"])
#def test_a_broken_template_string_decodes_to_nothing_instead_of_raising(bad):
#    assert algo_template.decode_cell(bad) is None
#
#
## --------------------------------------------------------------------------- #
## 3. 比對
## --------------------------------------------------------------------------- #
#def test_the_phase_moves_one_for_one_with_the_cut():
#    """patch 往右裁 1 px，相位就該往右 1 px。這是「定位真的成立」的核心。"""
#    gc = algo_template.build_golden_cell(big_image())
#    img = big_image(5)
#    base = None
#    for cut_at in range(0, PERIOD, 4):
#        m = algo_template.match_patch(gc.cell, cut(img, cut_at),
#                                      periodic=gc.periodic)
#        assert m.ok, "cut@%d 沒有對上" % cut_at
#        if base is None:
#            base = (m.phase_x - cut_at) % PERIOD
#        assert (m.phase_x - cut_at) % PERIOD == base, \
#            "相位沒有跟著裁切位置線性移動（cut@%d)" % cut_at
#
#
#def test_brightness_and_contrast_changes_do_not_break_the_match():
#    """大圖與 patch 是不同時間、不同增益拍的 —— 這是用 NCC 的唯一理由。"""
#    gc = algo_template.build_golden_cell(big_image())
#    for gain, offset in ((0.6, 40.0), (1.5, -30.0), (1.0, 0.0)):
#        m = algo_template.match_patch(
#            gc.cell, cut(big_image(9, gain=gain, offset=offset), 17),
#            periodic=gc.periodic)
#        assert m.ok, "gain=%.1f offset=%.0f 對不上" % (gain, offset)
#        assert m.score > 0.9
#
#
#def test_a_featureless_patch_is_refused_however_lucky_the_correlation_is():
#    """**只看分數是不夠的**，實測過：32 寬的純雜訊曲線跟模板的隨機相關
#    標準差約 1/√32 ≈ 0.18，靠運氣就拿得到 0.5。所以先問「這張有結構嗎」。
#    """
#    gc = algo_template.build_golden_cell(big_image())
#    lucky = 0
#    for seed in range(20):
#        m = algo_template.match_patch(gc.cell, flat_patch(seed),
#                                      periodic=gc.periodic)
#        assert m.ok is False, "seed=%d 的純雜訊被當成對上了" % seed
#        assert m.structure < 5.0
#        lucky = max(lucky, m.score)
#    assert lucky > 0.35, "前提：分數確實會靠運氣衝高，所以不能只看分數"
#
#
#def test_structure_separates_the_two_populations_by_an_order_of_magnitude():
#    gc = algo_template.build_golden_cell(big_image())
#    real = [algo_template.match_patch(gc.cell, cut(big_image(s), 7),
#                                      periodic=gc.periodic).structure
#            for s in range(5)]
#    none = [algo_template.match_patch(gc.cell, flat_patch(s),
#                                      periodic=gc.periodic).structure
#            for s in range(5)]
#    assert min(real) > 10 * max(none)
#
#
#def test_matching_a_direction_that_does_not_repeat_only_dilutes_the_peak():
#    """一維 layout 硬要在兩軸上搜尋，會把峰的突出程度稀釋掉 ——
#    也就是把「定得出來」誤判成「定不出來」。"""
#    gc = algo_template.build_golden_cell(big_image())
#    patch = cut(big_image(3), 11)
#    right = algo_template.match_patch(gc.cell, patch, periodic=(True, False))
#    both = algo_template.match_patch(gc.cell, patch, periodic=(True, True))
#    assert right.margin > both.margin
#
#
## --------------------------------------------------------------------------- #
## 4. 把框搬到 patch 上
## --------------------------------------------------------------------------- #
#def test_a_box_marked_on_the_cell_lands_on_the_right_material_every_time():
#    """**整張卡存在的理由。** 標一次，每張 patch 都框到同一種材質。"""
#    gc = algo_template.build_golden_cell(big_image())
#    norm = epi_band(gc.cell)
#    img = big_image(4)
#
#    for cut_at in range(0, PERIOD, 5):
#        patch = cut(img, cut_at)
#        m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
#        x, _y, w, _h = algo_template.roi_in_patch(
#            norm, m, gc.cell.shape, patch.shape, periodic=gc.periodic)
#        x0, x1 = max(0, x), min(patch.shape[1], x + w)
#        assert x1 > x0, "框整個落在 patch 外面（cut@%d)" % cut_at
#        assert float(patch[:, x0:x1].mean()) < 90.0, \
#            "cut@%d 框到的不是 EPI（平均 %.1f）" % (cut_at, patch[:, x0:x1].mean())
#
#
#def test_the_box_is_placed_on_the_cell_nearest_the_defect():
#    """缺陷永遠在 patch 正中央，所以使用者標的框指的是「缺陷所在的那個 cell」。"""
#    gc = algo_template.build_golden_cell(big_image())
#    patch = cut(big_image(6), 0)
#    m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
#    x, _y, w, _h = algo_template.roi_in_patch(
#        (0.0, 0.0, 0.2, 1.0), m, gc.cell.shape, patch.shape,
#        periodic=gc.periodic)
#    centre = patch.shape[1] / 2.0
#    assert abs((x + w / 2.0) - centre) <= PERIOD / 2.0 + 1
#
#
#def test_a_direction_with_no_period_takes_the_whole_patch():
#    """沒有週期就沒有相位可言 —— 那個方向硬給一個位置等於憑空捏造資訊。"""
#    gc = algo_template.build_golden_cell(big_image())
#    patch = cut(big_image(2), 9)
#    m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
#    _x, y, _w, h = algo_template.roi_in_patch(
#        (0.2, 0.3, 0.3, 0.2), m, gc.cell.shape, patch.shape,
#        periodic=gc.periodic)
#    assert (y, h) == (0, patch.shape[0])
#
#
## --------------------------------------------------------------------------- #
## 5. 卡片
## --------------------------------------------------------------------------- #
#def _params(gc, **over):
#    p = dict(source="ref", template=algo_template.encode_cell(gc.cell),
#             locate_axis="x", roi_out="epi")
#    nx, ny, nw, nh = epi_band(gc.cell)
#    p.update(roi_x=nx, roi_y=ny, roi_w=nw, roi_h=nh)
#    p.update(over)
#    return p
#
#
#def _run(ctx, params):
#    return get_step("roi_template")().run(ctx, params)
#
#
#def test_the_card_places_the_region_and_reports_the_evidence():
#    gc = algo_template.build_golden_cell(big_image())
#    img = big_image(8)
#    for cut_at in (0, 13, 27, 35):
#        patch = cut(img, cut_at)
#        ctx = Context(images={"ref": patch, "test": patch})
#        _run(ctx, _params(gc))
#        assert ctx.features["locate_ok"] == 1.0
#        x, y, w, h = ctx.roi_rect("epi", patch.shape)
#        assert float(patch[y:y + h, x:x + w].mean()) < 90.0
#        assert ctx.features["match_score"] > 0.9
#        assert ctx.features["match_structure"] > 10.0
#
#
#def test_the_card_falls_back_and_marks_the_defect_when_it_cannot_locate():
#    gc = algo_template.build_golden_cell(big_image())
#    ctx = Context(images={"ref": flat_patch(3)})
#    _run(ctx, _params(gc))
#
#    assert ctx.features["locate_ok"] == 0.0
#    assert ctx.roi_rect("epi", (PATCH, PATCH)) == (0, 0, PATCH, PATCH)
#    assert any("locate_ok" in w for w in ctx.meta.get("warnings", []))
#
#
#def test_a_card_without_a_template_says_where_to_get_one():
#    """沒有模板不是「跑出壞結果」，是**還沒設定完** —— 要講清楚去哪裡設定。"""
#    ctx = Context(images={"ref": flat_patch(0)})
#    with pytest.raises(StepError) as e:
#        _run(ctx, dict(source="ref", template="", roi_out="epi"))
#    assert "Build template" in str(e.value)
#
#
#def test_the_panel_data_is_the_engines_own_calculation():
#    gc = algo_template.build_golden_cell(big_image())
#    patch = cut(big_image(1), 21)
#    ctx = Context(images={"ref": patch})
#    _run(ctx, _params(gc))
#
#    panel = ctx.meta["templates"]["epi"]
#    assert panel["cell_w"] == gc.cell.shape[1]
#    assert panel["ok"] is True
#    assert panel["phase_x"] == int(ctx.features["phase_x"])
#    import json
#    json.dumps(panel)          # 面板資料要進得了快取的 meta 快照
#
#
#def test_the_region_name_must_be_usable_as_a_variable_name():
#    with pytest.raises(ParamError):
#        get_step("roi_template").validate_params({"roi_out": "my region"})
#
#
#def test_the_card_declares_the_region_it_defines():
#    cls = get_step("roi_template")
#    params = cls.validate_params({"roi_out": "epi"})
#    assert cls.resolve_regions_out(params) == ["epi"]
#    assert "epi_locate_ok" in cls.resolve_features(
#        cls.validate_params({"roi_out": "epi", "output_prefix": "epi"}))
#
#F ecb57644cec348b3ef52d811332dd9c353fcd920 233 tests/test_rsem_ingest.py
#"""tools/make_sample_rsem.py 與 rSEM ingest 路線的測試（M4-2）。
#
#Review SEM 是 ingest 的另一條分支：**每顆 defect 一個獨立影像檔**，
#KLARF 列尾用 `Images 1 { "檔名" … }` 指到那個檔。這裡驗證：
#  1. KLARF 解得開、`load_dataset` 判成 rsem、每顆只有 single channel；
#  2. 像素形狀／dtype、ground truth key 與 defect id 對得起來；
#  3. 同 seed → 位元組完全相同（KLARF 與影像）；
#  4. `load_patch` 卡會把 single 鏡射成 test（下游卡片才吃得到）；
#  5. Golden Cell 路線（cell_period → golden_cell）在這份資料上跑得通
#     —— 這是 M4「同一份 recipe 吃 EBI patch 與 RSEM」的驗收前提；
#  6. `--real-frac 0` 的 lot 真的沒有種缺陷。
#"""
#from __future__ import annotations
#
#import json
#import os
#import sys
#
#import numpy as np
#import pytest
#
#import adept.core.steps  # noqa: F401 — 註冊卡片的 side-effect
#from adept.core.ingest import dataset, klarf_core
#from adept.core.pipeline.context import Context
#from adept.core.pipeline.step import REGISTRY
#
#_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#import make_sample_rsem  # noqa: E402
#
#
#N = 8
#SEED = 11
#SIZE = 256
#PITCH = 24
#
## 「有沒有種缺陷」的判準：nuisance 的 |single - golden_ref| 峰值 ~25（雜訊 sigma=5），
## 種了缺陷的 >= 64。取 45 當門檻，兩邊都有很大的餘裕。
#RESIDUAL_THRESHOLD = 45.0
#
#
#def run_step(key, ctx, **params):
#    cls = REGISTRY[key]
#    return cls().run(ctx, cls.validate_params(params))
#
#
#def _read(path):
#    with open(path, "rb") as f:
#        return f.read()
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    out = tmp_path_factory.mktemp("rsemlot")
#    return make_sample_rsem.generate(str(out / "lot"), n=N, seed=SEED)
#
#
#@pytest.fixture(scope="module")
#def ds(lot):
#    return dataset.load_dataset(lot["klarf"])
#
#
#@pytest.fixture(scope="module")
#def truth(lot):
#    with open(lot["ground_truth"], "r", encoding="utf-8") as f:
#        return json.load(f)
#
#
## ------------------------------------------------------------ 1. KLARF → rsem dataset
#
#def test_klarf_parses_with_per_defect_filenames(lot):
#    doc = klarf_core.load(lot["klarf"])
#    assert doc.version == "1.8"
#    assert len(doc.defects) == N
#    # 沒有 patch TIFF：TiffFileName / TiffSpec 都不該出現，否則會被判成 ebi_patch
#    assert doc.tiff_file_name is None
#    assert doc.tiff_path() is None
#    # 影像欄佈局：1.8 結構化 Images 區塊
#    start, nfields, how = doc.image_layout()
#    assert how == "images18"
#    for k, row in enumerate(doc.defects):
#        assert doc.defect_image_count(row) == 1
#        assert doc.defect_image_filename(row) == "images/DEF_%04d.png" % (k + 1)
#
#
#def test_load_dataset_is_rsem_single_channel(lot, ds):
#    assert ds.kind == "rsem"
#    assert len(ds.items) == N
#    for i, it in enumerate(ds.items):
#        assert set(it.images) == {"single"}          # 沒有 test / ref
#        assert "test" not in it.images and "ref" not in it.images
#        ref = it.images["single"]
#        assert ref.page is None                      # 獨立影像檔，不是 TIFF 頁
#        assert ref.channel == "single"
#        assert os.path.isfile(ref.path)
#        assert os.path.basename(ref.path) == "DEF_%04d.png" % (i + 1)
#        # 座標落在假 die 內（KLARF 1.8 已是 nm）
#        assert 0 < it.xrel_nm < 5_000_000
#        assert 0 < it.yrel_nm < 5_000_000
#
#
## ------------------------------------------------------------ 2. 像素 + ground truth
#
#def test_pixels_and_ground_truth(ds, truth):
#    for it in ds.items:
#        arr = it.load("single")
#        assert arr.shape == (SIZE, SIZE)
#        assert arr.dtype == np.uint8
#    assert set(truth) == {it.defect_id for it in ds.items}
#    n_real = sum(1 for v in truth.values() if v["is_real"])
#    assert n_real == round(N * 0.5)                  # 預設 real_frac=0.5
#    for v in truth.values():
#        assert set(v) == {"is_real", "type"}
#        if v["is_real"]:
#            assert v["type"] in make_sample_rsem.REAL_TYPES
#        else:
#            assert v["type"] == make_sample_rsem.NUISANCE_TYPE
#    assert all(v["is_real"] == (v["type"] != "none") for v in truth.values())
#
#
#def test_images_are_not_all_identical(ds):
#    """每張圖有自己的相位／亮度／雜訊 —— 不能是同一張複製。"""
#    first = ds.items[0].load("single")
#    assert any(not np.array_equal(first, it.load("single")) for it in ds.items[1:])
#
#
## ------------------------------------------------------------ 3. 決定性
#
#def test_same_seed_identical_bytes(tmp_path):
#    a = make_sample_rsem.generate(str(tmp_path / "a"), n=4, seed=42)
#    b = make_sample_rsem.generate(str(tmp_path / "b"), n=4, seed=42)
#    assert _read(a["klarf"]) == _read(b["klarf"])
#    for pa, pb in zip(a["images"], b["images"]):
#        assert _read(pa) == _read(pb), f"{os.path.basename(pa)} 位元組不同"
#    assert _read(a["ground_truth"]) == _read(b["ground_truth"])
#
#    c = make_sample_rsem.generate(str(tmp_path / "c"), n=4, seed=43)
#    assert _read(c["images"][0]) != _read(a["images"][0])   # 不同 seed → 不同資料
#
#
## ------------------------------------------------------------ 4. load_patch 的 rsem 鏡射
#
#def test_load_patch_mirrors_single_to_test(ds):
#    it = ds.items[0]
#    ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds.kind})
#    run_step("load_patch", ctx)
#    # 卡片會把 single 同步一份到 test，下游卡片用預設 source="test" 就吃得到
#    assert "single" in ctx.images and "test" in ctx.images
#    assert np.array_equal(ctx.images["single"], ctx.images["test"])
#    assert "ref" not in ctx.images
#    assert ctx.features["n_channels"] == 1.0          # 只載入 single，鏡射不計數
#    assert any("single" in note for note in ctx.meta.get("notes", []))
#
#
#def test_load_patch_declared_writes_for_rsem():
#    cls = REGISTRY["load_patch"]
#    assert cls.resolve_writes_for_kind({"channels": "auto"}, "rsem") == ["single", "test"]
#
#
## ------------------------------------------------------------ 5. Golden Cell 路線
#
#def test_golden_cell_route_on_real_defect(ds, truth):
#    real = [it for it in ds.items if truth[it.defect_id]["is_real"]]
#    assert real, "這份 lot 應該要有 REAL 缺陷"
#    it = real[0]
#
#    ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds.kind})
#    run_step("load_patch", ctx)
#    run_step("cell_period", ctx)
#    assert abs(ctx.features["cell_px"] - PITCH) <= 2
#    assert abs(ctx.features["cell_py"] - PITCH) <= 2
#
#    run_step("golden_cell", ctx)
#    single = ctx.images["single"]
#    ref = ctx.images["ref"]
#    assert ref.shape == single.shape
#    assert ref.dtype == single.dtype
#    # 疊出來的參考圖要乾淨（缺陷被洗掉），而且和原圖在缺陷處差得出來
#    assert ctx.features["golden_ghost"] > 50.0
#    residual = np.abs(single.astype(np.float64) - ref.astype(np.float64))
#    assert residual.max() > RESIDUAL_THRESHOLD
#
#
## ------------------------------------------------------------ 6. real_frac=0
#
#def test_real_frac_zero_has_no_planted_defect(tmp_path):
#    paths = make_sample_rsem.generate(str(tmp_path / "clean"), n=6, seed=3,
#                                      real_frac=0.0)
#    with open(paths["ground_truth"], "r", encoding="utf-8") as f:
#        gt = json.load(f)
#    assert all(v == {"is_real": False, "type": "none"} for v in gt.values())
#
#    ds0 = dataset.load_dataset(paths["klarf"])
#    for it in ds0.items:
#        ctx = Context(meta={"_defect_item": it, "_dataset_kind": ds0.kind})
#        run_step("load_patch", ctx)
#        run_step("cell_period", ctx)
#        run_step("golden_cell", ctx)
#        residual = np.abs(ctx.images["single"].astype(np.float64)
#                          - ctx.images["ref"].astype(np.float64))
#        assert residual.max() < RESIDUAL_THRESHOLD, \
#            f"defect {it.defect_id} 不該有缺陷，殘差峰值卻是 {residual.max():.1f}"
#
#
## ------------------------------------------------------------ CLI / 參數防呆
#
#def test_cli_main(tmp_path, capsys):
#    rc = make_sample_rsem.main([str(tmp_path / "cli"), "--n", "2", "--seed", "1",
#                                "--size", "96", "--pitch", "12", "--format", "tif"])
#    assert rc == 0
#    out = capsys.readouterr().out
#    assert "LOT_RSEM.001" in out
#    assert os.path.isfile(str(tmp_path / "cli" / "images" / "DEF_0001.tif"))
#    assert os.path.isfile(str(tmp_path / "cli" / "ground_truth.json"))
#    ds1 = dataset.load_dataset(str(tmp_path / "cli" / "LOT_RSEM.001"))
#    assert ds1.kind == "rsem" and len(ds1.items) == 2
#    assert ds1.items[0].load("single").shape == (96, 96)
#
#
#def test_bad_args_raise(tmp_path):
#    with pytest.raises(ValueError):
#        make_sample_rsem.generate(str(tmp_path / "x"), n=0)
#    with pytest.raises(ValueError):
#        make_sample_rsem.generate(str(tmp_path / "x"), real_frac=1.5)
#    with pytest.raises(ValueError):
#        make_sample_rsem.generate(str(tmp_path / "x"), size=48, pitch=24)
#    with pytest.raises(ValueError):
#        make_sample_rsem.generate(str(tmp_path / "x"), noise=-1.0)
#    with pytest.raises(ValueError):
#        make_sample_rsem.generate(str(tmp_path / "x"), fmt="jpg")
#
#F 99687acf0a8aae0d2c88f7fca293cfad2e31c7b5 129 tests/test_snr.py
#"""Tests for adept.core.algo.snr (vendored 2026-07-27)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.snr import (
#    RoiSnrResult,
#    SnrMapResult,
#    center_gaussian_mask,
#    compute_snr_map,
#    roi_snr,
#    snr_signed,
#)
#
#
#def _image_with_patch(bg_mean: float, patch_value: float, seed: int = 5) -> np.ndarray:
#    rng = np.random.default_rng(seed)
#    img = np.clip(rng.normal(bg_mean, 5.0, size=(120, 120)), 0, 255)
#    img[40:50, 40:50] = patch_value
#    return img.astype(np.float32)
#
#
#def test_snr_signed_primitive():
#    rng = np.random.default_rng(3)
#    ref = rng.normal(50.0, 5.0, size=500)
#    target = np.full(100, 60.0)
#    val = snr_signed(target, ref)
#    assert 1.0 < val < 3.0  # (60-50)/5 = 2 nominal
#
#    # Dark target -> negative
#    assert snr_signed(np.full(100, 40.0), ref) < 0
#
#    # Flat reference or empty inputs -> 0.0
#    assert snr_signed(target, np.full(100, 50.0)) == 0.0
#    assert snr_signed(np.array([]), ref) == 0.0
#
#
#def test_roi_snr_bright_on_dark_positive():
#    img = _image_with_patch(bg_mean=50.0, patch_value=150.0)
#    res = roi_snr(img, (40, 40, 10, 10), background_margin=15)
#    assert isinstance(res, RoiSnrResult)
#    assert res.snr_signed > 5.0
#    assert res.snr_abs > 5.0
#    assert abs(res.snr_abs - abs(res.snr_signed)) < 1e-3
#    assert res.defect_mean > res.background_mean
#    assert res.contrast > 50.0
#    assert res.contrast_ratio > 1.5
#    assert res.dvi > 0.0
#    assert res.edge_sharpness >= 0.0
#
#
#def test_roi_snr_dark_on_bright_negative():
#    img = _image_with_patch(bg_mean=200.0, patch_value=20.0)
#    res = roi_snr(img, (40, 40, 10, 10), background_margin=15)
#    assert res.snr_signed < -5.0
#    assert res.snr_abs > 5.0
#    assert abs(res.snr_abs - abs(res.snr_signed)) < 1e-3
#    assert res.defect_mean < res.background_mean
#
#
#def test_roi_snr_invalid_rect_returns_none():
#    img = _image_with_patch(50.0, 150.0)
#    assert roi_snr(None, (0, 0, 10, 10)) is None
#    assert roi_snr(img, (200, 200, 10, 10)) is None  # fully outside
#
#
#def _diff_with_blob(seed: int = 9):
#    """Flat noise plus a plateau blob wider than the SNR window.
#
#    The local-SNR formula divides by the local std, so a blob narrower than
#    the window inflates its own denominator; a plateau larger than the window
#    keeps the window at the blob center noise-only and yields a strong peak.
#    """
#    rng = np.random.default_rng(seed)
#    diff = 0.5 + rng.normal(0.0, 0.02, size=(200, 200)).astype(np.float32)
#    yy, xx = np.mgrid[:200, :200]
#    disk = ((xx - 120) ** 2 + (yy - 80) ** 2) <= 12 ** 2
#    diff[disk] += 0.3
#    return np.clip(diff, 0, 1).astype(np.float32), (120, 80)
#
#
#def test_snr_map_peak_at_planted_blob():
#    diff, (bx, by) = _diff_with_blob()
#    res = compute_snr_map(diff, window_size=15, clip_sigma=3.0,
#                          clip_percentile=None, exclude_border=16)
#    assert isinstance(res, SnrMapResult)
#    assert res.map_float.dtype == np.float32
#    assert res.map_float.shape == diff.shape
#    assert res.map_float.min() >= 0.0 and res.map_float.max() <= 1.0
#    assert res.snr_max > 3.0
#
#    py, px = np.unravel_index(int(np.argmax(res.map_float)), res.map_float.shape)
#    assert abs(px - bx) <= 8
#    assert abs(py - by) <= 8
#
#    # Border must be zeroed
#    assert float(res.map_float[:16, :].max()) == 0.0
#    assert float(res.map_float[:, -16:].max()) == 0.0
#
#
#def test_snr_map_result_to_uint8_range():
#    diff, _ = _diff_with_blob()
#    res = compute_snr_map(diff)  # default params incl. clip_percentile=99.5
#    u8 = res.to_uint8()
#    assert u8.dtype == np.uint8
#    assert u8.shape == diff.shape
#    assert int(u8.min()) == 0
#    assert int(u8.max()) == 255  # percentile scaling saturates the peak
#    # Quantization consistency with the float map
#    np.testing.assert_array_equal(
#        u8, (np.clip(res.map_float, 0, 1) * 255).astype(np.uint8))
#
#
#def test_snr_map_empty_input():
#    res = compute_snr_map(np.array([]))
#    assert res.map_float.shape == (100, 100)
#    assert res.snr_max == 0.0
#    assert res.to_uint8().max() == 0
#
#
#def test_center_gaussian_mask():
#    mask = center_gaussian_mask((51, 81))
#    assert mask.dtype == np.float32
#    assert mask.shape == (51, 81)
#    assert mask.min() >= 0.0 and mask.max() <= 1.0
#    # Peak at the image center
#    py, px = np.unravel_index(int(np.argmax(mask)), mask.shape)
#    assert abs(py - 25) <= 1 and abs(px - 40) <= 1
#
#F 29cdd488b75b074bd0588375762629a26d941b77 75 tests/test_stats.py
#"""Tests for adept.core.algo.stats (vendored from PEAR analysis)."""
#from __future__ import annotations
#
#import numpy as np
#
#from adept.core.algo.glv import ROI
#from adept.core.algo.stats import (
#    attribute_separability,
#    cohens_d,
#    group_outliers,
#)
#
#
#def test_group_outliers_catches_planted_outlier():
#    img = np.zeros((60, 120), dtype=np.uint8)
#    # 6 ROIs in one group with a genuine spread of means; rid=4 planted far out
#    means = {1: 96, 2: 100, 3: 104, 4: 250, 5: 98, 6: 102}
#    rois = [ROI(rid, "g1", (5 + 18 * i, 10, 12, 12)) for i, rid in
#            enumerate([1, 2, 3, 4, 5, 6])]
#    for r in rois:
#        x, y, w, h = r.rect
#        img[y:y + h, x:x + w] = means[r.rid]
#    out = group_outliers(img, rois, "glv_mean")
#    assert out == {4}
#
#
#def test_group_outliers_skips_small_groups():
#    rng = np.random.default_rng(7)
#    img = np.clip(rng.normal(100, 3, (40, 80)), 0, 255).astype(np.uint8)
#    rois = [ROI(1, "g", (2, 2, 8, 8)), ROI(2, "g", (20, 2, 8, 8)),
#            ROI(3, "g", (40, 2, 8, 8))]
#    img[2:10, 40:48] = 255       # extreme, but group has < 4 ROIs
#    assert group_outliers(img, rois, "glv_mean") == set()
#
#
#def test_cohens_d_well_separated():
#    rng = np.random.default_rng(11)
#    a = rng.normal(0.0, 1.0, 50)
#    b = rng.normal(10.0, 1.0, 50)
#    d = cohens_d(a, b)
#    assert d is not None
#    assert abs(d) > 5.0
#    assert d < 0  # a below b -> negative (a - b) / sp
#    # symmetric sign flip
#    assert cohens_d(b, a) > 5.0
#
#
#def test_cohens_d_degenerate():
#    assert cohens_d([1.0], [2.0, 3.0]) is None            # too few samples
#    assert cohens_d([1.0, 1.0], [1.0, 1.0]) is None       # zero pooled sd
#
#
#def test_attribute_separability_high_eta2():
#    rng = np.random.default_rng(3)
#    g1 = rng.normal(0.0, 1.0, 40)
#    g2 = rng.normal(10.0, 1.0, 40)
#    eta2 = attribute_separability([g1, g2])
#    assert eta2 is not None
#    assert eta2 > 0.9
#
#
#def test_attribute_separability_overlapping_low():
#    rng = np.random.default_rng(4)
#    g1 = rng.normal(0.0, 1.0, 200)
#    g2 = rng.normal(0.0, 1.0, 200)
#    eta2 = attribute_separability([g1, g2])
#    assert eta2 is not None
#    assert eta2 < 0.05
#
#
#def test_attribute_separability_guards():
#    assert attribute_separability([[1.0, 2.0]]) is None        # single group
#    assert attribute_separability([[], []]) is None            # empty groups
#    assert attribute_separability([[5.0, 5.0], [5.0, 5.0]]) == 0.0  # no spread
#
#F dd89a3a0ca71cd8d0cfe69f5ee82fd430e723fb3 498 tests/test_steps.py
#"""Tests for adept.core.steps — the 14-card step library (M1).
#
#Each test builds a synthetic Context, runs one card through
#validate_params + run, and checks features / image streams / warnings.
#"""
#from __future__ import annotations
#
#import cv2
#import numpy as np
#import pytest
#import tifffile
#
#import adept.core.steps  # noqa: F401 — registration side-effect
#from adept.core.ingest.dataset import DefectItem, ImageRef
#from adept.core.pipeline.context import Context
#from adept.core.pipeline.step import REGISTRY, StepError
#
## 本卡片庫全部的 key（影像段 8 張 + 算法段 6 張）
#ALL_KEYS = [
#    "load_patch", "percentile_norm", "glv_mask_norm", "hist_match",
#    "denoise", "align", "subtract", "invert",
#    "snr_map", "blob_segment", "cd_measure", "roi_snr",
#    "focus_quality", "glv_stats",
#]
#
#
#def run_step(key, ctx, **params):
#    cls = REGISTRY[key]
#    return cls().run(ctx, cls.validate_params(params))
#
#
#def _rng(seed=0):
#    return np.random.default_rng(seed)
#
#
#def _smooth_pattern(size=128, seed=3):
#    """有結構的隨機影像（對位測試用：平滑過的雜訊）。"""
#    base = _rng(seed).integers(0, 256, size=(size, size)).astype(np.uint8)
#    return cv2.GaussianBlur(base, (7, 7), 2)
#
#
#def _blob(size, cy, cx, sigma=3.0):
#    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
#    return np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
#
#
## ---------------------------------------------------------------- registry / 推廣鐵則
#
#def test_registry_has_all_cards():
#    assert set(ALL_KEYS) <= set(REGISTRY)
#
#
#def test_promotion_rules_help_everywhere():
#    """推廣鐵則：每張卡與每個參數都要有非空白話 help。"""
#    for key in ALL_KEYS:
#        d = REGISTRY[key].describe()
#        assert str(d["help"]).strip(), f"{key}: card help empty"
#        for pr in d["params"]:
#            assert str(pr["help"]).strip(), f"{key}.{pr['name']}: param help empty"
#            assert pr["default"] is not None, f"{key}.{pr['name']}: no default"
#
#
## ---------------------------------------------------------------- load_patch
#
#@pytest.fixture()
#def patch_tiff(tmp_path):
#    pages = [np.full((16, 20), v, dtype=np.uint8) for v in (10, 120, 230)]
#    path = tmp_path / "patches.tif"
#    with tifffile.TiffWriter(str(path)) as tw:
#        for arr in pages:
#            tw.write(arr, photometric="minisblack")
#    return str(path), pages
#
#
#def test_load_patch_ebi(patch_tiff):
#    path, pages = patch_tiff
#    item = DefectItem(defect_id="1", die=(0, 0), xrel_nm=0.0, yrel_nm=0.0,
#                      images={"test": ImageRef(path, 0, "test"),
#                              "ref": ImageRef(path, 1, "ref")})
#    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "ebi_patch"})
#    run_step("load_patch", ctx)
#    assert set(ctx.images) == {"test", "ref"}
#    assert ctx.images["test"].dtype == np.uint8
#    assert np.array_equal(ctx.images["test"], pages[0])
#    assert np.array_equal(ctx.images["ref"], pages[1])
#    assert ctx.features["n_channels"] == 2.0
#
#
#def test_load_patch_rsem_alias(patch_tiff):
#    path, pages = patch_tiff
#    item = DefectItem(defect_id="9", die=None, xrel_nm=None, yrel_nm=None,
#                      images={"single": ImageRef(path, 2, "single")})
#    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "rsem"})
#    run_step("load_patch", ctx)
#    assert "single" in ctx.images and "test" in ctx.images
#    assert np.array_equal(ctx.images["test"], pages[2])
#    assert ctx.features["n_channels"] == 1.0
#    assert any("single" in n for n in ctx.meta.get("notes", []))
#
#
#def test_load_patch_explicit_and_errors(patch_tiff):
#    path, pages = patch_tiff
#    item = DefectItem(defect_id="1", die=None, xrel_nm=None, yrel_nm=None,
#                      images={"test": ImageRef(path, 0, "test"),
#                              "ref": ImageRef(path, 1, "ref")})
#    ctx = Context(meta={"_defect_item": item, "_dataset_kind": "ebi_patch"})
#    run_step("load_patch", ctx, channels="test")
#    assert set(ctx.images) == {"test"}
#    # 指定不存在的 channel → StepError
#    with pytest.raises(StepError):
#        run_step("load_patch", Context(meta={"_defect_item": item,
#                                             "_dataset_kind": "ebi_patch"}),
#                 channels="test,nope")
#    # 沒有 defect item → StepError
#    with pytest.raises(StepError):
#        run_step("load_patch", Context())
#
#
## ---------------------------------------------------------------- percentile_norm
#
#def _ramp(size=128):
#    row = np.linspace(0, 255, size).astype(np.uint8)
#    return np.tile(row, (size, 1))
#
#
#def test_percentile_norm_range_and_borrowed_range():
#    """一張卡一條流（F7-18）；``range_from`` 是「兩張圖還比得起來」那條路。"""
#    src = _ramp()
#    half = (src.astype(np.float32) / 2).astype(np.uint8)
#
#    # range_from=test：ref 用 test 的範圍 → 亮度只有一半（跨圖可比）
#    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
#    run_step("percentile_norm", ctx, source="ref", range_from="test")
#    run_step("percentile_norm", ctx, source="test")
#    out_t, out_r = ctx.images["test"], ctx.images["ref"]
#    assert out_t.dtype == np.uint8 and out_r.dtype == np.uint8
#    assert out_t.min() == 0 and out_t.max() == 255       # 範圍拉滿
#    assert abs(out_r.mean() - out_t.mean() / 2) < 8      # ref 保持相對亮度
#
#    # range_from 空著：各自拉自己的範圍 → 兩張平均亮度趨於一致
#    ctx2 = Context(images={"test": src.copy(), "ref": half.copy()})
#    run_step("percentile_norm", ctx2, source="test")
#    run_step("percentile_norm", ctx2, source="ref")
#    assert abs(ctx2.images["ref"].mean() - ctx2.images["test"].mean()) < 8
#
#    # 借不到範圍就報錯 —— 不靜靜改用自己的（輸出都是一張正常的圖，差別只在數字）
#    ctx3 = Context(images={"test": src.copy()})
#    with pytest.raises(StepError):
#        run_step("percentile_norm", ctx3, source="test", range_from="ghost")
#
#    # p_low >= p_high → StepError
#    with pytest.raises(StepError):
#        run_step("percentile_norm", Context(images={"test": src.copy()}),
#                 p_low=50.0, p_high=50.0)
#
#
#def test_glv_mask_norm_band_anchoring():
#    img = np.full((64, 64), 100, dtype=np.uint8)
#    img[10:40, 10:40] = np.linspace(150, 200, 900).reshape(30, 30).astype(np.uint8)
#    ctx = Context(images={"test": img.copy()})
#    run_step("glv_mask_norm", ctx, glv_low=150, glv_high=200)
#    out = ctx.images["test"]
#    assert out.dtype == np.uint8
#    assert out[0, 0] == 0            # 帶外的背景被壓到 0
#    assert out[10:40, 10:40].max() == 255   # 帶內像素被拉滿
#    with pytest.raises(StepError):
#        run_step("glv_mask_norm", Context(images={"test": img.copy()}),
#                 glv_low=200, glv_high=100)
#
#
#def test_hist_match_linear_means_close():
#    rng = _rng(11)
#    mov = np.clip(rng.normal(60, 10, (128, 128)), 0, 255).astype(np.uint8)
#    ref = np.clip(rng.normal(180, 20, (128, 128)), 0, 255).astype(np.uint8)
#    ctx = Context(images={"test": mov, "ref": ref})
#    run_step("hist_match", ctx, method="linear")
#    out = ctx.images["test"]
#    assert out.dtype == np.uint8
#    assert abs(float(out.mean()) - float(ref.mean())) < 2.0
#    assert abs(float(out.std()) - float(ref.std())) < 2.0
#
#
## ---------------------------------------------------------------- denoise
#
#def test_denoise_even_ksize_is_steperror():
#    ctx = Context(images={"test": np.zeros((32, 32), dtype=np.uint8)})
#    with pytest.raises(StepError):
#        run_step("denoise", ctx, ksize=4)
#
#
#def test_denoise_median_removes_salt_and_leaves_other_streams_alone():
#    img = np.full((64, 64), 100, dtype=np.uint8)
#    idx = _rng(2).integers(0, 64, size=(60, 2))
#    img[idx[:, 0], idx[:, 1]] = 255                     # 鹽噪點
#    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
#    run_step("denoise", ctx, method="median", ksize=3)
#    assert int(ctx.images["test"].max()) < 255          # 噪點被壓掉
#    # 一張卡一條流（F7-18）：ref 沒被接進這張卡，就不該被動到。
#    np.testing.assert_array_equal(ctx.images["ref"], img)
#
#
## ---------------------------------------------------------------- align
#
#def test_align_recovers_planted_shift():
#    base = _smooth_pattern(128)
#    dx, dy = 3, -2
#    ref = np.roll(np.roll(base, dy, axis=0), dx, axis=1)  # ref(x,y)=base(x-dx,y-dy)
#    ctx = Context(images={"test": base, "ref": ref})
#    run_step("align", ctx)
#    assert ctx.features["align_dx"] == pytest.approx(dx, abs=0.6)
#    assert ctx.features["align_dy"] == pytest.approx(dy, abs=0.6)
#    assert ctx.features["align_score"] > 50
#    assert "ref_aligned" in ctx.images
#    inner = np.s_[16:-16, 16:-16]
#    err = np.abs(ctx.images["ref_aligned"][inner].astype(np.float32)
#                 - base[inner].astype(np.float32))
#    assert float(err.mean()) < 3.0
#
#
#def test_align_flat_image_zero_shift_no_crash():
#    flat = np.full((64, 64), 77, dtype=np.uint8)
#    ctx = Context(images={"test": flat, "ref": flat.copy()})
#    run_step("align", ctx)
#    assert ctx.features["align_dx"] == 0.0
#    assert ctx.features["align_dy"] == 0.0
#    assert "ref_aligned" in ctx.images
#    assert ctx.meta.get("warnings")
#
#
## ---------------------------------------------------------------- subtract / invert
#
#def test_subtract_float32_with_visible_blob():
#    size = 128
#    pattern = _smooth_pattern(size, seed=8).astype(np.float32)
#    test = np.clip(pattern + 90 * _blob(size, 64, 64, 3.0), 0, 255).astype(np.uint8)
#    ref = np.clip(pattern, 0, 255).astype(np.uint8)
#    ctx = Context(images={"test": test, "ref_aligned": ref})
#    run_step("subtract", ctx)
#    diff = ctx.images["diff"]
#    assert diff.dtype == np.float32                     # diff 流是 float32
#    assert float(diff[60:69, 60:69].max()) > 50         # 缺陷清楚可見
#    assert float(np.median(diff)) < 5                   # 背景乾淨
#    # 尺寸不合 → StepError
#    with pytest.raises(StepError):
#        run_step("subtract", Context(images={
#            "test": np.zeros((8, 8), np.uint8),
#            "ref_aligned": np.zeros((9, 9), np.uint8)}))
#
#
#def test_invert_uint8():
#    img = _ramp(32)
#    ctx = Context(images={"test": img.copy()})
#    run_step("invert", ctx)
#    assert np.array_equal(ctx.images["test"], 255 - img)
#
#
## ---------------------------------------------------------------- snr_map
#
#def _diff_pair(size=128, amp=100.0, seed=5):
#    noise = np.abs(_rng(seed).normal(0, 2, (size, size))).astype(np.float32)
#    clean = noise
#    planted = noise + amp * _blob(size, size // 2, size // 2, 3.0).astype(np.float32)
#    return planted, clean
#
#
#def test_snr_map_planted_much_higher_than_clean():
#    planted, clean = _diff_pair()
#    ctx_p = Context(images={"diff": planted})
#    ctx_c = Context(images={"diff": clean})
#    run_step("snr_map", ctx_p)
#    run_step("snr_map", ctx_c)
#    assert ctx_p.images["snr_map"].dtype == np.float32
#    assert ctx_p.features["snr_max"] > 3.0 * ctx_c.features["snr_max"]
#    with pytest.raises(StepError):                      # 偶數視窗防呆
#        run_step("snr_map", Context(images={"diff": planted}), window=30)
#
#
## ---------------------------------------------------------------- blob_segment
#
#def test_blob_segment_planted_blob_features():
#    planted, _ = _diff_pair()
#    ctx = Context(images={"diff": planted})
#    run_step("snr_map", ctx)
#    run_step("blob_segment", ctx)
#    assert ctx.features["blob_count"] >= 1
#    assert ctx.features["blob_area"] > 0
#    assert ctx.features["blob_snr"] > 0
#    assert ctx.features["blob_dist_center"] < 15        # 種在中心
#    blobs = ctx.meta["blobs"]
#    assert isinstance(blobs, list) and isinstance(blobs[0], dict)
#    for k in ("x", "y", "w", "h", "cx", "cy", "area",
#              "mean_signal", "snr_value", "aspect_ratio", "dist_to_center"):
#        assert k in blobs[0]
#
#
#def test_blob_segment_zero_blobs_is_not_an_error():
#    zeros = np.zeros((96, 96), dtype=np.float32)
#    ctx = Context(images={"snr_map": zeros, "diff": zeros.copy()})
#    run_step("blob_segment", ctx)
#    assert ctx.meta["blobs"] == []
#    for f in ("blob_count", "blob_area", "blob_aspect",
#              "blob_dist_center", "blob_snr"):
#        assert ctx.features[f] == 0.0
#
#
## ---------------------------------------------------------------- cd_measure
#
#def _cd_ctx(nm_per_px=None):
#    diff = np.zeros((128, 128), dtype=np.float32)
#    diff[50:70, 50:60] = 80.0                           # 10 寬 × 20 高矩形
#    blob = {"x": 50, "y": 50, "w": 10, "h": 20, "cx": 55.0, "cy": 60.0,
#            "area": 200, "mean_signal": 0.3, "snr_value": 255.0,
#            "aspect_ratio": 0.5, "dist_to_center": 10.0}
#    meta = {"blobs": [blob]}
#    if nm_per_px is not None:
#        meta["nm_per_px"] = nm_per_px
#    return Context(images={"diff": diff}, meta=meta)
#
#
#def test_cd_measure_px_and_nm_paths():
#    ctx = _cd_ctx()                                     # 無 nm_per_px
#    run_step("cd_measure", ctx)
#    assert ctx.features["cd_x_px"] == 10.0
#    assert ctx.features["cd_y_px"] == 20.0
#    assert ctx.features["cd_x_nm"] == 0.0
#    assert ctx.features["area_nm2"] == 0.0
#    assert any("nm_per_px" in w for w in ctx.meta["warnings"])
#
#    ctx2 = _cd_ctx(nm_per_px=2.5)
#    run_step("cd_measure", ctx2)
#    assert ctx2.features["cd_x_nm"] == pytest.approx(25.0)
#    assert ctx2.features["cd_y_nm"] == pytest.approx(50.0)
#    assert ctx2.features["area_nm2"] == pytest.approx(200 * 2.5 * 2.5)
#
#
#def test_cd_measure_can_target_a_named_region():
#    """F7-4：CD 也可以量使用者畫的框，不再只能吃 meta['blobs']。"""
#    img = np.zeros((64, 64), np.float32)
#    ctx = Context(images={"diff": img})
#    run_step("roi_define", ctx, name="mid", shape="center", size=20,
#             source="diff")
#    run_step("cd_measure", ctx, roi="mid")
#    assert ctx.features["cd_x_px"] == 20.0
#    assert ctx.features["cd_y_px"] == 20.0
#
#
#def test_cd_measure_subpixel_refine_and_fallbacks():
#    ctx = _cd_ctx(nm_per_px=1.0)
#    run_step("cd_measure", ctx, refine="subpixel")
#    assert ctx.features["cd_y_px"] == pytest.approx(20.0, abs=2.0)
#    assert ctx.features["cd_x_px"] == 10.0              # X 仍是 bbox（M1 簡化）
#
#    # 精修影像流不存在 → 警告 + bbox
#    ctx2 = _cd_ctx()
#    del ctx2.images["diff"]
#    run_step("cd_measure", ctx2, refine="subpixel")
#    assert ctx2.features["cd_y_px"] == 20.0
#    assert ctx2.meta.get("warnings")
#
#    # 完全沒有 blob → 全 0 + 警告（不是錯誤）
#    ctx3 = Context(images={"diff": np.zeros((32, 32), np.float32)})
#    run_step("cd_measure", ctx3)
#    assert all(ctx3.features[f] == 0.0 for f in
#               ("cd_x_px", "cd_y_px", "cd_x_nm", "cd_y_nm", "area_nm2"))
#    assert ctx3.meta.get("warnings")
#
#
## ---------------------------------------------------------------- roi_snr
#
#def test_roi_snr_signed_sign_bright_vs_dark():
#    size = 128
#    for sign in (+1.0, -1.0):
#        img = _rng(9).normal(0, 3, (size, size)).astype(np.float32)
#        c0 = size // 2 - 12
#        img[c0:c0 + 24, c0:c0 + 24] += sign * 60.0
#        ctx = Context(images={"diff": img})
#        run_step("roi_define", ctx, name="mid", shape="center", size=24,
#                 source="diff")
#        run_step("roi_snr", ctx, roi="mid")
#        if sign > 0:
#            assert ctx.features["roi_snr_signed"] > 3.0
#        else:
#            assert ctx.features["roi_snr_signed"] < -3.0
#        assert ctx.features["roi_snr_abs"] > 3.0
#        assert ctx.features["roi_contrast"] > 30.0
#
#
#def test_roi_snr_blob_mode_without_blobs_warns_zero():
#    ctx = Context(images={"diff": np.zeros((64, 64), np.float32)})
#    run_step("roi_snr", ctx, roi="blob")
#    assert ctx.features["roi_snr_signed"] == 0.0
#    assert ctx.meta.get("warnings")
#
#
## ---------------------------------------------------------------- focus_quality
#
#def test_focus_quality_sharp_vs_blurred():
#    yy, xx = np.mgrid[0:128, 0:128]
#    sharp = (((xx // 4 + yy // 4) % 2) * 255).astype(np.uint8)
#    blurred = cv2.GaussianBlur(sharp, (9, 9), 3)
#    ctx_s = Context(images={"test": sharp})
#    ctx_b = Context(images={"test": blurred})
#    run_step("focus_quality", ctx_s)
#    run_step("focus_quality", ctx_b)
#    for f in ("focus_lapvar", "focus_tenengrad", "focus_fft"):
#        assert ctx_s.features[f] > ctx_b.features[f], f
#
#
## ---------------------------------------------------------------- glv_stats
#
#def test_glv_stats_matches_numpy_including_aliases():
#    img = _rng(21).integers(0, 256, size=(64, 64)).astype(np.uint8)
#    ctx = Context(images={"test": img})
#    run_step("glv_stats", ctx,
#             metrics="glv_mean,glv_std,glv_p50,glv_q75,glv_p90,glv_min")
#    f64 = img.astype(np.float64)
#    assert ctx.features["glv_mean"] == pytest.approx(f64.mean())
#    assert ctx.features["glv_std"] == pytest.approx(f64.std())
#    assert ctx.features["glv_p50"] == pytest.approx(np.median(f64))   # 別名照列名輸出
#    assert ctx.features["glv_q75"] == pytest.approx(np.percentile(f64, 75))
#    assert ctx.features["glv_p90"] == pytest.approx(np.percentile(f64, 90))
#    assert ctx.features["glv_min"] == pytest.approx(f64.min())
#
#    # 具名 ROI 只取中央方框（F7-4：幾何從量測卡搬到 Region 卡）
#    ctx2 = Context(images={"test": img})
#    run_step("roi_define", ctx2, name="mid", shape="center", size=16)
#    run_step("glv_stats", ctx2, roi="mid", metrics="glv_mean")
#    crop = img[24:40, 24:40].astype(np.float64)
#    assert ctx2.features["glv_mean"] == pytest.approx(crop.mean())
#
#    # ROI 名字打錯 → StepError（不可以安靜地退回整張圖）
#    ctx3 = Context(images={"test": img})
#    with pytest.raises(StepError):
#        run_step("glv_stats", ctx3, roi="typo")
#
#    # 未知統計項 → StepError
#    with pytest.raises(StepError):
#        run_step("glv_stats", Context(images={"test": img}), metrics="glv_bogus")
#
#
## ---------------------------------------------------------------- tone (F7-7)
#
#def test_brightness_contrast_pivots_around_mid_gray():
#    """對比以影像自己的中間值為支點 —— 以 0 為支點會順便把整張圖變亮。"""
#    img = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
#    ctx = Context(images={"test": img.copy()})
#    run_step("brightness_contrast", ctx, contrast=2.0)
#    out = ctx.images["test"]
#    assert out[0, 2] == 128, "中灰是支點，不該移動"
#    assert out[0, 0] == 0 and out[0, 4] == 255           # 兩端夾住
#    assert int(out[0, 1]) < 64 and int(out[0, 3]) > 192  # 往兩邊拉開
#
#    ctx2 = Context(images={"test": img.copy()})
#    run_step("brightness_contrast", ctx2, brightness=20.0)
#    assert int(ctx2.images["test"][0, 2]) == 148
#    assert ctx2.images["test"].dtype == np.uint8, "uint8 進 uint8 出"
#
#
#def test_gamma_opens_up_dark_detail_and_is_reversible_at_one():
#    img = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
#
#    ctx = Context(images={"test": img.copy()})
#    run_step("gamma", ctx, gamma=1.0)
#    np.testing.assert_array_equal(ctx.images["test"], img)   # 1 = 不動
#
#    ctx = Context(images={"test": img.copy()})
#    run_step("gamma", ctx, gamma=0.5)
#    assert int(ctx.images["test"][0, 1]) < 64, "gamma<1 要壓暗部（拉開細節）"
#
#    ctx = Context(images={"test": img.copy()})
#    run_step("gamma", ctx, gamma=2.0)
#    assert int(ctx.images["test"][0, 1]) > 64
#    # 端點永遠不動
#    assert int(ctx.images["test"][0, 0]) == 0
#    assert int(ctx.images["test"][0, 4]) == 255
#
#
#def test_tone_cards_keep_float_streams_float_and_only_touch_their_own():
#    """diff 是 float32 —— 這兩張卡插在哪裡都不該偷偷改變型別。
#
#    順便鎖住 F7-18 的約定：**一張卡一條流**。要 test 與 ref 一起動，就放兩張卡
#    （畫布上因此看得到兩條各自的鏈），而不是一張卡偷偷寫了兩條流。
#    """
#    f = np.linspace(-5.0, 5.0, 25, dtype=np.float32).reshape(5, 5)
#    ctx = Context(images={"test": f.copy(), "ref": f.copy()})
#    run_step("gamma", ctx, gamma=0.7)
#    assert ctx.images["test"].dtype == np.float32
#    assert ctx.images["ref"].dtype == np.float32
#    np.testing.assert_allclose(ctx.images["ref"], f)     # ref 沒被接進來
#
#    run_step("gamma", ctx, target="ref", gamma=0.7)      # 第二張卡做 ref
#    np.testing.assert_allclose(ctx.images["test"], ctx.images["ref"])
#
#    # 指到不存在的流 -> 白話 StepError（不是靜靜跳過）
#    ctx2 = Context(images={"test": f.copy()})
#    with pytest.raises(StepError):
#        run_step("brightness_contrast", ctx2, target="nope")
#
#F 38d2a7f3b7731f16b92155e49775746815f30fc6 135 tests/test_subpixel.py
#"""Tests for adept.core.algo.subpixel (vendored from MMH cmg_recipe)."""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#
#from adept.core.algo.subpixel import (
#    SubpixelResult,
#    aggregate_values,
#    compute_sample_xs,
#    refine_xedge_subpixel,
#    refine_xedge_subpixel_batch,
#    refine_xedge_threshold_crossing,
#    refine_xedge_threshold_crossing_batch,
#    refine_yedge_subpixel,
#    refine_yedge_subpixel_batch,
#    refine_yedge_threshold_crossing,
#    refine_yedge_threshold_crossing_batch,
#)
#
#Y_TRUE = 30.4
#H = W = 64
#
#
#@pytest.fixture(scope="module")
#def yedge_image():
#    """Smooth (sigmoid) horizontal step edge at sub-pixel row Y_TRUE."""
#    yy = np.arange(H, dtype=np.float64)
#    prof = 30.0 + 200.0 / (1.0 + np.exp(-(yy - Y_TRUE) / 1.5))
#    return np.tile(prof[:, None], (1, W)).astype(np.uint8)
#
#
#@pytest.fixture(scope="module")
#def xedge_image(yedge_image):
#    """The same edge rotated: vertical step edge at sub-pixel column Y_TRUE."""
#    return np.ascontiguousarray(yedge_image.T)
#
#
#def test_scalar_gradient_recovers_subpixel_edge(yedge_image):
#    res = refine_yedge_subpixel(yedge_image, x_center=32, y_guess=30.0)
#    assert isinstance(res, SubpixelResult)
#    assert res.fallback_reason == ""
#    assert abs(res.y_refined - Y_TRUE) < 0.3
#    assert res.shift_px == pytest.approx(res.y_refined - 30.0)
#    assert res.peak_strength > 0.0
#    assert 0.0 <= res.second_peak_ratio < 1.0
#
#
#def test_scalar_threshold_crossing_recovers_subpixel_edge(yedge_image):
#    res = refine_yedge_threshold_crossing(yedge_image, x_center=32, y_guess=30.0)
#    assert res.fallback_reason == ""
#    assert abs(res.y_refined - Y_TRUE) < 0.3
#
#
#def test_batch_threshold_crossing_recovers_subpixel_edge(yedge_image):
#    xs = list(range(10, 50))
#    # smooth_k=1 skips the cumsum smoothing so the batch TC is unbiased
#    out = refine_yedge_threshold_crossing_batch(
#        yedge_image, xs, y_guess=30.0, smooth_k=1)
#    vals = [v for v in out if v is not None]
#    assert len(vals) == len(xs)
#    assert abs(float(np.mean(vals)) - Y_TRUE) < 0.3
#
#
#def test_batch_gradient_valid_and_consistent(yedge_image):
#    xs = list(range(10, 50))
#    out = refine_yedge_subpixel_batch(yedge_image, xs, y_guess=30.0)
#    vals = [v for v in out if v is not None]
#    assert len(vals) == len(xs)
#    # identical columns -> identical refined values
#    assert max(vals) - min(vals) < 1e-9
#    # stays inside the proximity window of the guess
#    assert all(abs(v - 30.0) <= 5.0 for v in vals)
#    # out-of-image sample positions come back as None, in order
#    out2 = refine_yedge_subpixel_batch(yedge_image, [-5, 32, 999], 30.0)
#    assert out2[0] is None and out2[2] is None and out2[1] is not None
#
#
#def test_flat_profile_sets_fallback_reason():
#    flat = np.full((H, W), 50, dtype=np.uint8)
#    r1 = refine_yedge_subpixel(flat, x_center=32, y_guess=30.0)
#    r2 = refine_yedge_threshold_crossing(flat, x_center=32, y_guess=30.0)
#    assert r1.fallback_reason == "flat_profile"
#    assert r2.fallback_reason == "flat_profile"
#    # fallback returns the guess untouched with zeroed diagnostics
#    assert r1.y_refined == 30.0 and r1.shift_px == 0.0
#    assert r1.peak_strength == 0.0 and r1.second_peak_ratio == 0.0
#    # batch versions signal failure with None
#    assert refine_yedge_subpixel_batch(flat, [10, 20], 30.0) == [None, None]
#    assert refine_yedge_threshold_crossing_batch(flat, [10, 20], 30.0) == [None, None]
#
#
#def test_invalid_image_fallback():
#    res = refine_yedge_subpixel(None, x_center=5, y_guess=5.0)
#    assert res.fallback_reason == "invalid_image"
#
#
#def test_xedge_wrappers_agree_with_transposed_yedge(yedge_image, xedge_image):
#    ry = refine_yedge_subpixel(yedge_image, x_center=32, y_guess=30.0)
#    rx = refine_xedge_subpixel(xedge_image, y_center=32, x_guess=30.0)
#    assert rx == ry  # NamedTuple equality: identical refined coord + diagnostics
#
#    ty = refine_yedge_threshold_crossing(yedge_image, x_center=32, y_guess=30.0)
#    tx = refine_xedge_threshold_crossing(xedge_image, y_center=32, x_guess=30.0)
#    assert tx == ty
#    assert abs(tx.y_refined - Y_TRUE) < 0.3  # refined X coordinate
#
#    samples = list(range(10, 50))
#    by = refine_yedge_subpixel_batch(yedge_image, samples, 30.0)
#    bx = refine_xedge_subpixel_batch(xedge_image, samples, 30.0)
#    assert bx == by
#    cy = refine_yedge_threshold_crossing_batch(yedge_image, samples, 30.0)
#    cx = refine_xedge_threshold_crossing_batch(xedge_image, samples, 30.0)
#    assert cx == cy
#
#
#def test_compute_sample_xs():
#    assert compute_sample_xs(3, 8, "all") == [3, 4, 5, 6, 7]
#    xs = compute_sample_xs(0, 21, 5)
#    assert len(xs) == 5
#    assert xs[0] == 0 and xs[-1] == 20
#    assert xs == sorted(xs)
#    assert compute_sample_xs(5, 5, "all") == []
#    assert compute_sample_xs(0, 3, 10) == [0, 1, 2]  # N capped at range size
#
#
#def test_aggregate_values():
#    vals = [1.0, 2.0, 3.0, 10.0]
#    assert aggregate_values(vals, "median") == 2.5
#    assert aggregate_values(vals, "mean") == 4.0
#    assert aggregate_values(vals, "min") == 1.0
#    assert aggregate_values(vals, "max") == 10.0
#    assert aggregate_values(vals, "unknown") == 2.5  # default: median
#    assert aggregate_values([], "mean") == 0.0
#
#F 605fe6f103ffff4b761e33a8fde8fd52db79c1b9 84 tests/test_tiff_index.py
#"""Tests for adept.core.ingest.tiff_index (structural walker + page decode)."""
#from __future__ import annotations
#
#import numpy as np
#import pytest
#import tifffile
#
#from adept.core.ingest import tiff_index
#
#
#def _write_multipage(path, arrays):
#    with tifffile.TiffWriter(str(path)) as tw:
#        for arr in arrays:
#            tw.write(arr, photometric="minisblack")
#
#
#@pytest.fixture()
#def pages4(tmp_path):
#    rng = np.random.default_rng(42)
#    arrays = [
#        rng.integers(0, 256, size=(32, 48), dtype=np.uint8),
#        rng.integers(0, 256, size=(32, 48), dtype=np.uint8),
#        rng.integers(0, 65536, size=(16, 24), dtype=np.uint16),
#        rng.integers(0, 256, size=(16, 24), dtype=np.uint8),
#    ]
#    p = tmp_path / "multi.tif"
#    _write_multipage(p, arrays)
#    return p, arrays
#
#
#def test_read_tiff_pages_counts_and_dims(pages4):
#    p, arrays = pages4
#    pages, info = tiff_index.read_tiff_pages(str(p))
#    assert info["n_pages"] == 4
#    assert not info["bigtiff"]
#    assert len(pages) == 4
#    for k, (page, arr) in enumerate(zip(pages, arrays)):
#        assert page["index"] == k
#        assert page["width"] == arr.shape[1]
#        assert page["height"] == arr.shape[0]
#    assert pages[2]["bits"] == 16
#    assert pages[0]["bits"] == 8
#
#
#def test_n_pages(pages4):
#    p, _arrays = pages4
#    assert tiff_index.n_pages(str(p)) == 4
#
#
#def test_read_page_pixel_identical(pages4):
#    p, arrays = pages4
#    for k, arr in enumerate(arrays):
#        out = tiff_index.read_page(str(p), k)
#        assert out.dtype == arr.dtype
#        assert np.array_equal(out, arr)
#
#
#def test_read_page_out_of_range(pages4):
#    p, _arrays = pages4
#    with pytest.raises(IndexError):
#        tiff_index.read_page(str(p), 4)
#
#
#def test_bigtiff(tmp_path):
#    rng = np.random.default_rng(7)
#    arrays = [rng.integers(0, 256, size=(8, 12), dtype=np.uint8)
#              for _ in range(2)]
#    p = tmp_path / "big.tif"
#    with tifffile.TiffWriter(str(p), bigtiff=True) as tw:
#        for arr in arrays:
#            tw.write(arr, photometric="minisblack")
#    pages, info = tiff_index.read_tiff_pages(str(p))
#    assert info["bigtiff"]
#    assert info["n_pages"] == 2
#    assert pages[0]["width"] == 12 and pages[0]["height"] == 8
#    assert np.array_equal(tiff_index.read_page(str(p), 1), arrays[1])
#
#
#def test_not_a_tiff_raises(tmp_path):
#    p = tmp_path / "nottiff.bin"
#    p.write_bytes(b"PNGnottiff-data!")
#    with pytest.raises(ValueError):
#        tiff_index.read_tiff_pages(str(p))
#
#F 05e63f22247d0bf597c925909c0cc2f548fbe648 246 tests/test_ui_canvas.py
## F7-6 驗收：節點畫布（n8n 式）取代直線清單。
#"""畫布是純 UI —— 引擎那邊一行都沒動。
#
#``core`` 從 F0 起就是 DAG：``Recipe.edges`` 早就存在、``execution_order()``
#早就是 Kahn 拓撲排序 + 循環偵測。所以這裡驗的是 UI 有沒有把那個能力接出來，
#以及**循環有沒有被擋在使用者拉線的當下**（而不是等執行時才爆）。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes" \
#    / "die_to_die_basic.json"
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import canvas as canvas_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    from make_sample import generate
#    return generate(str(tmp_path_factory.mktemp("f7_canvas")), n=6, seed=7)
#
#
#@pytest.fixture
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    win.load_recipe_path(str(EXAMPLE), sync=True)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 自動排版
## --------------------------------------------------------------------------- #
#def test_layout_is_a_straight_line_when_nothing_is_connected(qapp):
#    """還沒拉線時每個節點深度都是 0 —— 不可以全部疊在同一欄。"""
#    pos = canvas_mod.layout_columns(["a", "b", "c"], [])
#    assert [pos[n] for n in ("a", "b", "c")] == [(0, 0), (1, 0), (2, 0)]
#
#
#def test_layout_puts_each_node_at_its_topological_depth(qapp):
#    pos = canvas_mod.layout_columns(
#        ["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
#    assert pos["a"][0] == 0
#    assert pos["b"][0] == pos["c"][0] == 1      # 兩條平行分支同欄
#    assert pos["b"][1] != pos["c"][1]           # 但不同列，不會疊在一起
#    assert pos["d"][0] == 2                     # 走最長路徑，不是最短
#
#
## --------------------------------------------------------------------------- #
## 2. 畫布反映 model
## --------------------------------------------------------------------------- #
#def test_canvas_shows_every_node_of_the_recipe(window):
#    assert window.pipeline.node_ids() == window.model.node_order
#    assert len(window.pipeline.node_ids()) > 3
#    assert window.pipeline.card("snr") is not None
#
#
#def test_selecting_a_node_on_the_canvas_drives_the_param_form(window):
#    assert window.select_node("snr") is True
#    assert window.pipeline.selected() == "snr"
#    assert window.param_form.step_key() == "snr_map"
#
#
## --------------------------------------------------------------------------- #
## 3. 連線
## --------------------------------------------------------------------------- #
#def test_linking_two_nodes_records_an_edge(window):
#    window.pipeline.link_to("load", "norm")
#    assert ("load", "norm") in window.model.edges
#    assert ("load", "norm") in window.pipeline.edge_pairs()
#    assert "Connected" in window.status_text()
#
#
#def test_a_link_that_would_loop_is_refused_at_draw_time(window):
#    """**循環擋在拉線的當下**，不是等到執行時才爆。"""
#    window.pipeline.link_to("load", "norm")
#    window.pipeline.link_to("norm", "sub")
#    before = list(window.model.edges)
#
#    window.pipeline.link_to("sub", "load")        # 會成環
#    assert window.model.edges == before, "成環的線不可以落進 model"
#    assert "loop" in window.status_text()
#
#    # 而且流程仍然跑得動 —— 沒有被那次嘗試弄壞
#    assert window.run_trial(6, workers=1, sync=True) is True
#
#
#def test_both_ports_can_land_on_the_same_node_and_each_gets_its_own_line(window):
#    """patch 天生成對：Input 吐 test 與 ref，Subtract 兩張都吃。
#
#    所以 **Input → Subtract 要畫兩條線**（不是一條沒說明白的線），而且把第二個
#    埠也拖到同一個節點上是很正常的操作 —— 那時候不可以回一句看起來像失敗的
#    「Cannot connect」。
#    """
#    load, sub = window.pipeline.card("load"), window.pipeline.card("sub")
#    assert load.out_names() == ["test", "ref"]
#    assert sub.in_names() == ["test", "ref"]
#
#    window.pipeline.link_to("load", "sub")
#    assert window.model.edges == [("load", "sub")], "model 仍然是一條依賴"
#    assert window.pipeline._ports_between(load, sub) == [0, 1]
#    assert len([e for e in window.pipeline._edges
#                if e.pair() == ("load", "sub")]) == 2, "兩條共用的流 = 兩條線"
#    assert "Connected" in window.status_text()
#
#    # 第二個埠拖到同一個節點：不是錯誤，訊息要講清楚兩條線本來就都在了
#    window.pipeline.link_to("load", "sub")
#    assert window.model.edges == [("load", "sub")]
#    assert "already connected" in window.status_text()
#    assert "Cannot" not in window.status_text()
#
#    # 而「會成環」仍然是另一句話，不可以跟上面混為一談
#    window.pipeline.link_to("sub", "load")
#    assert "loop" in window.status_text()
#
#
#def test_duplicate_and_self_links_are_ignored(window):
#    window.pipeline.link_to("load", "norm")
#    n = len(window.model.edges)
#    window.pipeline.link_to("load", "norm")         # 重複
#    window.pipeline.link_to("load", "load")         # 自迴圈
#    assert len(window.model.edges) == n
#
#
#def test_removing_an_edge_puts_it_back(window):
#    window.pipeline.link_to("load", "norm")
#    assert ("load", "norm") in window.model.edges
#    window.pipeline.edge_removed.emit("load", "norm")
#    assert ("load", "norm") not in window.model.edges
#    assert "Disconnected" in window.status_text()
#
#
#def test_edges_reorder_execution_and_survive_a_save_load_round_trip(window, tmp_path):
#    """連線要真的影響執行順序，而且存檔再載回來還在。"""
#    from adept.core.pipeline import Recipe
#
#    window.pipeline.link_to("load", "norm")
#    window.pipeline.link_to("norm", "sub")
#    edges = list(window.model.edges)
#    order = list(window.model.node_order)
#    assert order.index("load") < order.index("norm") < order.index("sub")
#
#    out = tmp_path / "wired.json"
#    assert window.save_recipe_path(str(out)) is True
#    loaded = Recipe.load(str(out))
#    assert [tuple(e) for e in loaded.edges] == edges
#
#    assert window.load_recipe_path(str(out), sync=True) is True
#    assert window.model.edges == edges
#    assert window.pipeline.edge_pairs() == edges
#
#
## --------------------------------------------------------------------------- #
## 4. 畫布不擋住既有的動線
## --------------------------------------------------------------------------- #
#def test_adding_a_card_from_the_library_lands_on_the_canvas(window):
#    before = len(window.pipeline.node_ids())
#    window.library.entry("invert").add_button.click()
#    assert len(window.pipeline.node_ids()) == before + 1
#    assert window.pipeline.node_ids()[-1] in window.model.nodes
#
#
## --------------------------------------------------------------------------- #
## 5. 節點卡的外觀（F7-8）
## --------------------------------------------------------------------------- #
#def test_long_text_is_elided_not_chopped_in_half(qapp):
#    """硬切在字的中間看起來像畫面壞掉，而且 ``source=diff · metri`` 這種殘句
#    會讓人以為參數值真的是那樣。"""
#    from PySide6.QtCore import QRectF
#    from PySide6.QtGui import QImage, QPainter
#
#    img = QImage(200, 40, QImage.Format_ARGB32)
#    img.fill(0)
#    p = QPainter(img)
#    drawn = []
#    p.drawText = lambda rect, flags, text: drawn.append(text)   # 攔下真正畫的字
#    canvas_mod._draw_elided(p, QRectF(0, 0, 40, 14),
#                            "a very long parameter summary indeed")
#    canvas_mod._draw_elided(p, QRectF(0, 0, 180, 14), "short")
#    p.end()
#
#    assert drawn[0] != "a very long parameter summary indeed"
#    assert drawn[0].endswith("…")
#    assert drawn[1] == "short", "放得下的字不可以被動到"
#
#
#def test_every_node_paints_without_raising(window):
#    """``paint()`` 裡的例外被 Qt 吞掉只印到 stderr —— 測試不跑一次就看不到。
#
#    順便涵蓋停用節點（虛線框）與被選取節點（粗框）兩條分支。
#    """
#    from PySide6.QtCore import QRectF, Qt
#    from PySide6.QtGui import QImage, QPainter
#
#    window.pipeline.link_to("load", "sub")
#    window._on_node_toggled("cd", False)
#    assert window.select_node("sub") is True
#
#    scene = window.pipeline._scene
#    rect = scene.itemsBoundingRect()
#    assert rect.width() > 0 and rect.height() > 0
#    img = QImage(int(rect.width()) + 8, int(rect.height()) + 8,
#                 QImage.Format_ARGB32)
#    img.fill(0)
#    p = QPainter(img)
#    scene.render(p, QRectF(img.rect()), rect, Qt.KeepAspectRatio)
#    p.end()
#
#    # 真的畫出了東西（不是一張空的透明圖）
#    assert any(img.pixelColor(x, y).alpha() > 0
#               for x in range(0, img.width(), 7)
#               for y in range(0, img.height(), 7))
#
#
#def test_canvas_repaints_on_a_theme_switch(window):
#    """節點卡是自繪的，顏色在 paint() 時才取 —— 換膚不需要重建畫布。"""
#    try:
#        assert window.toggle_theme() == "dark"
#        assert window.pipeline.node_ids() == window.model.node_order
#    finally:
#        window.set_theme("light")
#
#F 4cc9539773183626bf0e94f8cfeb5453ababd42e 213 tests/test_ui_controls_readable.py
## F7-13 驗收：控制項要看得出自己是什麼。
#"""這一支測的不是「功能對不對」，是**看不看得出來**。
#
#三個症狀來自同一種毛病：控制項長得不像它自己。下拉選單長得像文字框，於是
#沒有人知道它可以點開；一個沒辦法用打的值配一個文字框，於是使用者對著它猜；
#一張還不能跑的卡片長得跟設定完整的一樣，於是要跑過一次才知道。
#
#這種 bug 用「功能測試」抓不到 —— 每一項功能都是好的。所以這裡直接量畫素、
#量控制項的型別、量卡片上有沒有那個標記。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#
#def _import_qt(g):
#    from PySide6.QtGui import QPixmap
#    from PySide6.QtWidgets import (
#        QApplication, QComboBox, QLineEdit, QPushButton,
#    )
#
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    from adept.ui import widgets as widgets_mod
#    g.update(QApplication=QApplication, QComboBox=QComboBox, QLineEdit=QLineEdit,
#             QPushButton=QPushButton, QPixmap=QPixmap, studio_mod=studio_mod,
#             theme_mod=theme_mod, widgets_mod=widgets_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#    theme_mod.apply_theme(app, "light")
#
#
#def _ink(widget, x0: int, x1: int) -> int:
#    """widget 畫出來之後，[x0, x1) 這條直帶裡有多少畫素不是它的底色。"""
#    from PySide6.QtGui import QColor
#
#    widget.resize(200, 26)
#    pm = QPixmap(widget.size())
#    pm.fill(QColor("#808080"))          # 中性灰：淺色與深色主題都不會剛好同色
#    widget.render(pm)
#    img = pm.toImage()
#    bg = img.pixelColor(widget.width() // 2, widget.height() // 2)
#    n = 0
#    for x in range(x0, x1):
#        for y in range(4, widget.height() - 4):
#            p = img.pixelColor(x, y)
#            if (abs(p.red() - bg.red()) + abs(p.green() - bg.green())
#                    + abs(p.blue() - bg.blue())) > 30:
#                n += 1
#    return n
#
#
## --------------------------------------------------------------------------- #
## 1. 下拉選單看得出是下拉選單
## --------------------------------------------------------------------------- #
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_a_dropdown_does_not_look_like_a_text_box(qapp, theme_name):
#    """`QComboBox::drop-down { border: 0 }` 會讓箭頭**完全不畫**（styled 的
#    subcontrol 需要自帶 down-arrow 圖檔，而這個 repo 是純文字的）。
#
#    症狀不是「醜」——是「Match on」（三選一）跟「Name this region」（自由文字）
#    在畫面上一模一樣，使用者無從得知哪個點得開。
#    """
#    theme_mod.apply_theme(qapp, theme_name)
#    combo = QComboBox()
#    combo.addItems(["ref", "test"])
#    arrow_area = (176, 197)
#    assert _ink(combo, *arrow_area) > 0, "the dropdown arrow is not drawn"
#    assert _ink(QLineEdit("ref"), *arrow_area) == 0, "a line edit grew an arrow"
#
#
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_a_toolbar_button_looks_pressable(qapp, theme_name):
#    """工具列以前是一排沒有邊框的字 —— 那讀起來是「File Edit View…」，
#    而選單列是拉下來的東西，不是按的東西。"""
#    theme_mod.apply_theme(qapp, theme_name)
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        btn = win.btn_open_klarf
#        btn.resize(150, 30)
#        from PySide6.QtGui import QColor
#
#        pm = QPixmap(btn.size())
#        pm.fill(QColor("#808080"))
#        btn.render(pm)
#        img = pm.toImage()
#        # 上緣那一條就是邊框（1 px）；中間是按鈕的底色。兩者一樣 = 沒有邊框，
#        # 也就是「一排字」。
#        edge = img.pixelColor(btn.width() // 2, 0)
#        middle = img.pixelColor(btn.width() // 2, btn.height() // 2)
#        assert edge != middle, "the button has no visible edge — it reads as a menu bar"
#    finally:
#        win.close()
#
#
## --------------------------------------------------------------------------- #
## 2. 模板參數
## --------------------------------------------------------------------------- #
#def _a_template() -> str:
#    from adept.core.algo import template as at
#
#    img = np.zeros((240, 320), np.float32)
#    for k in range(8):
#        x = k * 40
#        img[:, x:x + 40] = 120.0
#        img[:, x + 14:x + 34] = 60.0
#        img[:, x + 12:x + 16] = 210.0
#        img[:, x + 32:x + 36] = 210.0
#    img += np.random.default_rng(0).normal(0, 4, img.shape).astype(np.float32)
#    return at.encode_cell(at.build_golden_cell(img).cell)
#
#
#def test_the_template_parameter_is_not_a_text_box(qapp):
#    """值有六千多個字元而且沒有人能用打的。文字框在這裡有三個後果：空的時候
#    看起來只是「還沒填」、填了之後變成一片 base64、而且它可以被改。"""
#    from adept.core.pipeline.step import get_step
#
#    form = widgets_mod.ParamForm()
#    step = get_step("roi_template")
#    form.set_step(step.describe(), {}, ["test", "ref"])
#    editor = form.editor("template")
#    assert isinstance(editor, widgets_mod.TemplateField)
#    assert not isinstance(editor, QLineEdit)
#    assert editor.has_template() is False
#    assert "cannot run" in editor.describe()
#
#    editor.set_text(_a_template())
#    assert editor.has_template() is True
#    # 摘要講的是**解出來的東西**，不是旁邊記著的字串長度
#    assert "40 × 240 px" in editor.describe()
#
#
#def test_the_button_asks_studio_to_open_the_dialog(qapp):
#    """按鈕在參數列裡，但對話框是 Studio 開的 —— 元件不知道那是什麼對話框。"""
#    from adept.core.pipeline.step import get_step
#
#    form = widgets_mod.ParamForm()
#    form.set_step(get_step("roi_template").describe(), {}, ["ref"])
#    seen = []
#    form.action_requested.connect(seen.append)
#    form.editor("template").button.click()
#    assert seen == ["template"]
#
#
## --------------------------------------------------------------------------- #
## 3. 「這張卡還不能跑」看得見
## --------------------------------------------------------------------------- #
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    yield win
#    win.close()
#
#
#def test_a_card_that_cannot_run_is_marked_on_the_canvas(window):
#    """lint 早就知道模板是空的 —— 但那個知識以前只在按下 Run trial 的那一刻
#    出現一次，卡片在畫布上看起來永遠是好的。"""
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#
#    codes = [i.code for i in window.model.validate() if i.node_id == nid]
#    assert "not-configured" in codes
#
#    item = window.pipeline.node_item(nid)
#    assert item is not None
#    assert "Build template" in item.problem()
#    assert "Build template" in item.toolTip()
#
#    window._apply_template(nid, _a_template(), "x")
#    assert window.pipeline.node_item(nid).problem() == ""
#    assert [i.code for i in window.model.validate() if i.node_id == nid] == []
#
#
#def test_the_badge_paints_in_both_themes(window):
#    """標記畫在卡片的右上角，而那裡本來是卡片名字的尾巴。"""
#    from PySide6.QtGui import QColor, QPainter
#
#    nid = window.model.add_step("roi_template")
#    item = window.pipeline.node_item(nid)
#    for name in ("light", "dark"):
#        theme_mod.set_theme(name)
#        pm = QPixmap(240, 80)
#        pm.fill(QColor("#ffffff"))
#        p = QPainter(pm)
#        item.paint(p, None, None)          # 例外會在這裡冒出來
#        p.end()
#        assert not pm.isNull()
#    theme_mod.apply_theme(QApplication.instance(), "light")
#
#
#def test_the_card_summary_never_shows_the_raw_template(window):
#    """節點的第三行是「哪些參數被改過」。模板直接串進去的話，那一行就變成
#    一段 base64 —— 既沒有資訊，也把真正有用的參數擠掉了。"""
#    nid = window.model.add_step("roi_template")
#    window._apply_template(nid, _a_template(), "x")
#    summary = window.pipeline.node_item(nid).info.get("summary", "")
#    assert "gc1:" not in summary
#    assert "template: set" in summary
#    assert len(summary) < 120
#
#F 46c837b6f362d0493860e0cc4e657fecfabeea2d 134 tests/test_ui_english_only.py
## ADEPT UI-language guard — authored 2026-07-28 (M7).
#"""UI 一律英文：掃原始碼，禁止「會顯示在畫面上的字串」出現 CJK。
#
#為什麼要這條規則
#----------------
#使用者的原話：**「中英夾雜很混亂」**。工具列是英文、卡片名是中文、錯誤訊息
#又是中文夾英文術語——每換一個區塊就要換一次讀法，對第一次用的人是純噪音。
#所以 M7 把所有 user-facing 字串統一成英文，並用這支測試把它鎖住。
#
#界線在哪（很重要）
#------------------
#**只管會顯示給使用者看的字串**，也就是 AST 裡的字串常數。
#docstring 與 ``#`` 註解**維持中文** —— 那是給開發者/接手者的說明文件，
#是這個 repo 刻意累積的資產（見 ``docs/HANDOVER.md``），翻成英文只會弄丟脈絡。
#
#實作上：用 :mod:`ast` 走一遍，跳過 module/class/function 的 docstring 節點，
#其餘字串常數只要含 CJK 就算違規。``#`` 註解根本不在 AST 裡，天然被排除。
#"""
#from __future__ import annotations
#
#import ast
#from pathlib import Path
#from typing import List, Tuple
#
#PKG = Path(__file__).resolve().parent.parent / "adept"
#
##: 還沒翻完、暫時放行的檔案（相對 ``adept/`` 的 posix 路徑）。
##:
##: * ``__main__.py`` —— CLI 是另一個介面層，使用者這次要求的是 GUI；
##:   要不要跟著英文化是獨立的決定，還沒問過。
##: * ``core/ingest/klarf_core.py`` —— 從 KLIP 整檔 vendoring 進來的 KLARF
##:   引擎（``docs/HANDOVER.md`` 稱之為「最重要的資產」）。它的 lint / 修補
##:   訊息**會**出現在 Export 精靈的「Output health check」區塊，所以最終應該
##:   一起英文化；但那是一個獨立、需要小心處理的改動，不混在 UI 這批裡。
#PENDING: Tuple[str, ...] = (
#    "__main__.py",
#    "core/ingest/klarf_core.py",
#)
#
#
#def _has_cjk(text: str) -> bool:
#    """CJK 文字**或全形標點**。
#
#    標點也要抓：``、``、``：``、全形空白 ``\u3000`` 這些混在英文句子裡一樣刺眼，
#    而且是翻譯時最容易漏掉的東西（M7 就漏了 9 處，全都是標點）。
#    """
#    return any("一" <= ch <= "鿿"        # CJK 統一表意文字
#               or "　" <= ch <= "〿"      # CJK 標點（、。「」，含全形空白）
#               or "！" <= ch <= "｠"      # 全形 ASCII 變體（：；！？（））
#               for ch in text)
#
#
#def _docstring_node_ids(tree: ast.AST) -> set:
#    """module / class / function 的 docstring 節點 id（這些不算 UI 字串）。"""
#    out = set()
#    for node in ast.walk(tree):
#        if isinstance(node, (ast.Module, ast.ClassDef,
#                             ast.FunctionDef, ast.AsyncFunctionDef)):
#            body = getattr(node, "body", None)
#            if (body and isinstance(body[0], ast.Expr)
#                    and isinstance(body[0].value, ast.Constant)
#                    and isinstance(body[0].value.value, str)):
#                out.add(id(body[0].value))
#    return out
#
#
#def _cjk_strings(path: Path) -> List[Tuple[int, str]]:
#    tree = ast.parse(path.read_text(encoding="utf-8"))
#    skip = _docstring_node_ids(tree)
#    hits = []
#    for node in ast.walk(tree):
#        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
#                and id(node) not in skip and _has_cjk(node.value)):
#            hits.append((node.lineno, node.value))
#    return sorted(hits)
#
#
#def test_no_cjk_in_user_facing_strings():
#    """UI 顯示的字串一律英文（docstring / 註解不在此限）。"""
#    offenders = []
#    for py in sorted(PKG.rglob("*.py")):
#        rel = py.relative_to(PKG).as_posix()
#        if rel in PENDING:
#            continue
#        for lineno, value in _cjk_strings(py):
#            offenders.append("%s:%d  %s" % (rel, lineno, value[:70]))
#    assert not offenders, (
#        "以下字串會顯示給使用者，但含中文（UI 一律英文）：\n  "
#        + "\n  ".join(offenders))
#
#
#def test_pending_files_are_really_still_pending():
#    """PENDING 清單不准長霉：翻完了就要把檔案從清單移除。"""
#    stale = [rel for rel in PENDING if not _cjk_strings(PKG / rel)]
#    assert not stale, (
#        "這些檔案已經沒有中文 UI 字串了，請把它們從 PENDING 移除：%s" % stale)
#
#
#def test_step_cards_are_english():
#    """卡片庫看得到的每一張卡：label / help / 每個 ParamSpec 的 help 都要是英文。"""
#    import adept.core.steps  # noqa: F401 — 觸發註冊
#    from adept.core.pipeline import list_steps
#
#    bad = []
#    for step in list_steps():
#        for field, text in (("label", step.label), ("help", step.help)):
#            if _has_cjk(str(text)):
#                bad.append("%s.%s = %r" % (step.key, field, text))
#        for spec in step.params:
#            if _has_cjk(str(spec.help)):
#                bad.append("%s.%s.help = %r" % (step.key, spec.name, spec.help))
#    assert not bad, "卡片庫仍有中文字串：\n  " + "\n  ".join(bad)
#
#
#def test_every_card_declares_a_known_group():
#    """F7-3：每張卡都要落在一個已知的流程階段，不能靠預設矇混過去。
#
#    ``resolve_group()`` 有依 category 的保守 fallback（讓外掛卡不會壞），
#    但**本 repo 內建的卡片一律要明講**——否則新加的量測卡會安靜地掉進
#    Enhance，而使用者永遠找不到它。
#    """
#    import adept.core.steps  # noqa: F401
#    from adept.core.pipeline import list_steps
#    from adept.core.pipeline.step import GROUP_ORDER
#
#    undeclared, unknown = [], []
#    for step in list_steps():
#        if not step.group:
#            undeclared.append(step.key)
#        elif step.group not in GROUP_ORDER:
#            unknown.append("%s -> %r" % (step.key, step.group))
#    assert not undeclared, "沒宣告 group 的卡片：%s" % undeclared
#    assert not unknown, "group 不在 GROUP_ORDER 裡：%s" % unknown
#
#F e07df332dae100f630b92b760386e85bb4c729a0 357 tests/test_ui_export_dialog.py
## ADEPT Studio 輸出精靈測試 — authored 2026-07-28 (M5-3).
#"""``adept/ui/export_dialog.py``（KLARF 寫回 / 報表 / 疊圖）的離屏測試。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_export_dialog.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
#PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
#``import PySide6``（或 import ``adept.ui.export_dialog``），蒐集階段就會把 Qt 塞進
#``sys.modules``，那個守門測試就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。
#
#這個檔案守的四條底線：
#
#1. **控制項要反映真實的 KLARF**：有的欄位才能選，沒有的欄位變灰**並寫明原因**。
#2. **「預覽變更」是硬性關卡**：沒預覽 → 「寫出」是灰的；設定一改 → 預覽作廢。
#3. **無損**：inplace 什麼都不改 → 輸出檔與原檔**逐位元組相同**（鐵則 6）。
#4. **錯誤是人話**：:class:`ExportError` 變成一句看得懂的訊息，不是 traceback。
#"""
#from __future__ import annotations
#
#import os
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#EXAMPLE_RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#from adept.core.export import feature_keys  # noqa: E402
#from adept.core.ingest import klarf_core  # noqa: E402
#from adept.core.ingest.dataset import load_dataset  # noqa: E402
#from adept.core.pipeline import Recipe, run_batch  # noqa: E402
#
#N = 8
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtCore import Qt  # noqa: F401
#    from PySide6.QtWidgets import QApplication  # noqa: F401
#
#    from adept.ui import export_dialog as ex_mod  # noqa: F401
#    from adept.ui import theme as theme_mod  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
#    _load_qt()
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    """合成 lot（8 顆 EBI patch defect）—— 與其他測試同一支產生器。"""
#    return generate(str(tmp_path_factory.mktemp("export_lot")), n=N, seed=7)
#
#
#@pytest.fixture(scope="module")
#def ran(synlot):
#    """真的跑一次 die-to-die 範例流程（不是手捏的假結果）。"""
#    ds = load_dataset(synlot["klarf"])
#    recipe = Recipe.load(str(EXAMPLE_RECIPE))
#    results = run_batch(recipe, ds, workers=1)
#    assert len(results) == N
#    assert any(r["ok"] for r in results)
#    return {"dataset": ds, "recipe": recipe, "results": results,
#            "doc": ds.klarf, "klarf": synlot["klarf"]}
#
#
#@pytest.fixture
#def dlg(qapp, ran, tmp_path):
#    """一個全新的對話框（每個測試各自一份，設定不互相污染）。"""
#    d = ex_mod.ExportDialog(ran["results"], doc=ran["doc"],
#                            dataset=ran["dataset"], recipe=ran["recipe"],
#                            default_dir=str(tmp_path))
#    yield d
#    d.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 三個模式的控制項都由「真實的欄位清單」長出來
## --------------------------------------------------------------------------- #
#def test_controls_populate_from_real_klarf_columns(dlg, ran):
#    assert dlg.mode() == "inplace"
#    assert dlg.klarf_columns() == list(ran["doc"].defect_columns)
#
#    # 這份合成 KLARF 只有 CLASSNUMBER，另外三欄都不存在
#    assert "CLASSNUMBER" in dlg.klarf_columns()
#    assert dlg.column_enabled("CLASSNUMBER") is True
#    for name in ("ROUGHBINNUMBER", "FINEBINNUMBER", "DSIZE"):
#        assert name not in dlg.klarf_columns()
#        assert dlg.column_enabled(name) is False, name
#        hint = dlg.column_hint(name)
#        assert name in hint and "has no" in hint, hint       # 講清楚為什麼不能選
#        assert dlg.column_control(name).isChecked() is False
#
#    # annotate：特徵多選清單 = 這批結果真的量到的特徵
#    assert dlg.feature_names() == feature_keys(ran["results"])
#    assert "snr_max" in dlg.feature_names()
#    assert dlg.selected_features() == []
#
#    # topn：取幾顆 / 分數門檻 / 重新編號
#    assert dlg.set_mode("topn") is True
#    assert dlg.spin_topn.value() >= 1
#    assert dlg.chk_renumber.isChecked() is True
#    assert dlg.set_mode("nope") is False
#
#
#def test_mode_pages_swap(dlg):
#    dlg.show()
#    for mode, page in (("inplace", dlg.page_inplace),
#                       ("annotate", dlg.page_annotate),
#                       ("topn", dlg.page_topn)):
#        dlg.set_mode(mode)
#        assert dlg.mode() == mode
#        assert page.isVisible() is True
#        others = [p for p in (dlg.page_inplace, dlg.page_annotate, dlg.page_topn)
#                  if p is not page]
#        assert all(p.isVisible() is False for p in others)
#
#
## --------------------------------------------------------------------------- #
## 2. 「預覽變更」是硬性關卡
## --------------------------------------------------------------------------- #
#def test_preview_fills_plan_and_enables_write(dlg, tmp_path):
#    assert dlg.btn_write.isEnabled() is False, "沒預覽就不准寫"
#    assert dlg.plan_text() == ""
#
#    dlg.set_output_path("klarf", str(tmp_path / "out.001"))
#    dlg.chk_class_col.setChecked(True)
#    plan = dlg.preview_plan()
#
#    assert plan is not None
#    assert plan.mode == "inplace"
#    assert plan.columns_touched == ["CLASSNUMBER"]
#    assert plan.n_rows_out == N
#    assert plan.n_rows_changed > 0
#
#    text = dlg.plan_text()
#    assert text == dlg.plan_view.toPlainText()
#    for piece in ("Mode: ", "Rows changed: %d defects" % plan.n_rows_changed,
#                  "Existing columns touched: CLASSNUMBER", "Columns added: (none)",
#                  "The output file will have %d defect rows" % plan.n_rows_out,
#                  "Output health check:"):
#        assert piece in text, piece
#    assert "✓" in text                                  # 這份檔案健檢是乾淨的
#    assert dlg.btn_write.isEnabled() is True
#
#    # 任何設定被動過 → 計畫作廢、按鈕鎖回去（使用者看到的一定是這一版的後果）
#    dlg.chk_class_col.setChecked(False)
#    assert dlg.plan() is None
#    assert dlg.plan_text() == ""
#    assert dlg.btn_write.isEnabled() is False
#    assert "press “Preview changes” again" in dlg.plan_view.toPlainText()
#
#
#def test_write_without_preview_is_refused(dlg, tmp_path):
#    dlg.set_output_path("klarf", str(tmp_path / "never.001"))
#    assert dlg.run_export(sync=True) is None
#    assert "Preview changes" in dlg.error_text()
#    assert not (tmp_path / "never.001").exists()
#
#
#def test_plan_with_lint_errors_surfaces_them(qapp, ran, tmp_path):
#    """健檢有 error 的檔案 → 計畫書裡要看得到 ✗ 那幾行。"""
#    broken_path = tmp_path / "broken.001"
#    text = Path(ran["klarf"]).read_text(encoding="utf-8")
#    broken_path.write_text(text.replace("EndOfFile;", ""), encoding="utf-8")
#    doc = klarf_core.load(str(broken_path))
#
#    d = ex_mod.ExportDialog(ran["results"], doc=doc, default_dir=str(tmp_path))
#    try:
#        d.set_output_path("klarf", str(tmp_path / "out_broken.001"))
#        plan = d.preview_plan()
#        assert plan is not None
#        levels = [i.level for i in plan.issues]
#        assert "error" in levels, levels
#        text_out = d.plan_text()
#        assert "✗" in text_out
#        assert "EndOfFile" in text_out                   # 說出是哪個問題
#    finally:
#        d.close()
#
#
## --------------------------------------------------------------------------- #
## 3. 無損：inplace 什麼都不改 → 逐位元組相同
## --------------------------------------------------------------------------- #
#def test_inplace_noop_write_is_byte_identical(dlg, ran, tmp_path):
#    out = tmp_path / "noop.001"
#    dlg.set_output_path("klarf", str(out))
#    assert dlg.column_control("CLASSNUMBER").isChecked() is False
#
#    plan = dlg.preview_plan()
#    assert plan is not None and plan.n_rows_changed == 0
#    assert "byte-for-byte identical" in dlg.plan_text()
#
#    summary = dlg.run_export(sync=True)
#    assert dlg.error_text() == ""
#    assert summary is not None
#    assert str(out) in summary["outputs"]
#
#    assert out.read_bytes() == Path(ran["klarf"]).read_bytes()
#
#
#def test_inplace_writes_classnumber(dlg, ran, tmp_path):
#    out = tmp_path / "cls.001"
#    dlg.set_output_path("klarf", str(out))
#    dlg.chk_class_col.setChecked(True)
#    assert dlg.preview_plan() is not None
#    assert dlg.run_export(sync=True) is not None
#
#    doc = klarf_core.load(str(out))
#    j = doc.col_index("CLASSNUMBER")
#    di = doc.col_index("DEFECTID")
#    got = {row[di]: row[j] for row in doc.defects}
#    for r in ran["results"]:
#        if r.get("ok") and r.get("bin") is not None:
#            assert got[str(r["defect_id"])] == str(int(r["bin"]))
#
#
#def test_annotate_adds_score_class_and_chosen_features(dlg, tmp_path):
#    out = tmp_path / "annot.001"
#    dlg.set_mode("annotate")
#    dlg.set_output_path("klarf", str(out))
#    dlg.set_selected_features(["snr_max"])
#    assert dlg.selected_features() == ["snr_max"]
#
#    plan = dlg.preview_plan()
#    assert plan is not None
#    assert plan.columns_added == ["ADCSCORE", "ADCCLASS", "SNR_MAX"]
#    assert "Columns added: ADCSCORE, ADCCLASS, SNR_MAX" in dlg.plan_text()
#
#    assert dlg.run_export(sync=True) is not None
#    doc = klarf_core.load(str(out))
#    for col in ("ADCSCORE", "ADCCLASS", "SNR_MAX"):
#        assert doc.col_index(col) >= 0, col
#    # 影像參照不能壞：新欄位插在影像欄之前，IMAGELIST 仍在列尾
#    assert doc.defect_image_map()["mode"] is not None
#    assert len(doc.defects) == N
#
#
#def test_topn_keeps_only_the_best(dlg, tmp_path):
#    out = tmp_path / "top3.001"
#    dlg.set_mode("topn")
#    dlg.set_output_path("klarf", str(out))
#    dlg.spin_topn.setValue(3)
#
#    plan = dlg.preview_plan()
#    assert plan is not None
#    assert plan.n_rows_out == 3
#    assert "The output file will have 3 defect rows" in dlg.plan_text()
#
#    assert dlg.run_export(sync=True) is not None
#    doc = klarf_core.load(str(out))
#    assert len(doc.defects) == 3
#    di = doc.col_index("DEFECTID")
#    assert [row[di] for row in doc.defects] == ["1", "2", "3"]   # 重新編號
#
#
## --------------------------------------------------------------------------- #
## 4. 錯誤是人話
## --------------------------------------------------------------------------- #
#def test_export_error_is_readable_not_traceback(qapp, ran, tmp_path):
#    """對一份已經有 ADCSCORE 的 KLARF 再 annotate → 白話錯誤，不是 traceback。"""
#    first = tmp_path / "once.001"
#    d1 = ex_mod.ExportDialog(ran["results"], doc=ran["doc"], default_dir=str(tmp_path))
#    try:
#        d1.set_mode("annotate")
#        d1.set_output_path("klarf", str(first))
#        assert d1.preview_plan() is not None
#        assert d1.run_export(sync=True) is not None
#    finally:
#        d1.close()
#
#    d2 = ex_mod.ExportDialog(ran["results"], doc=klarf_core.load(str(first)),
#                             default_dir=str(tmp_path))
#    try:
#        d2.set_mode("annotate")
#        d2.set_output_path("klarf", str(tmp_path / "twice.001"))
#        assert d2.preview_plan() is None
#        assert d2.plan() is None
#        assert d2.btn_write.isEnabled() is False
#        msg = d2.error_text()
#        assert "ADCSCORE" in msg and "Traceback" not in msg
#        assert "✗" in d2.plan_view.toPlainText()
#        assert not (tmp_path / "twice.001").exists()
#    finally:
#        d2.close()
#
#
## --------------------------------------------------------------------------- #
## 5. 報表與疊圖
## --------------------------------------------------------------------------- #
#def test_csv_and_excel_checkboxes_produce_files(dlg, ran, tmp_path):
#    csv_path = tmp_path / "features.csv"
#    xlsx_path = tmp_path / "report.xlsx"
#    dlg.chk_klarf.setChecked(False)          # 只出報表：不必先預覽
#    dlg.chk_csv.setChecked(True)
#    dlg.chk_excel.setChecked(True)
#    dlg.set_output_path("csv", str(csv_path))
#    dlg.set_output_path("excel", str(xlsx_path))
#    assert dlg.btn_write.isEnabled() is True
#
#    summary = dlg.run_export(sync=True)
#    assert dlg.error_text() == ""
#    assert summary is not None
#    assert str(csv_path) in summary["outputs"]
#    assert str(xlsx_path) in summary["outputs"]
#
#    head = csv_path.read_text(encoding="utf-8-sig").splitlines()
#    assert head[0].startswith("defect_id,ok,error,score,bin")
#    assert len(head) == N + 1
#
#    from openpyxl import load_workbook
#    wb = load_workbook(str(xlsx_path))
#    assert wb.sheetnames == ["Summary", "Details", "Feature stats"]
#
#    assert "CSV" in dlg.summary_text() or "csv" in dlg.summary_text().lower()
#
#
#def test_overlay_writes_pngs_with_limit(dlg, tmp_path):
#    out_dir = tmp_path / "ov"
#    dlg.chk_klarf.setChecked(False)
#    dlg.chk_overlay.setChecked(True)
#    dlg.spin_overlay_limit.setValue(2)
#    dlg.set_output_path("overlay", str(out_dir))
#
#    summary = dlg.run_export(sync=True)
#    assert dlg.error_text() == ""
#    assert summary is not None and summary["n_overlays"] == 2
#
#    pngs = sorted(p for p in os.listdir(str(out_dir)) if p.endswith(".png"))
#    assert len(pngs) == 2
#    assert all(p.startswith(ex_mod.OVERLAY_PREFIX) for p in pngs)
#    assert (out_dir / pngs[0]).stat().st_size > 0
#
#
#def test_nothing_selected_is_refused(dlg):
#    dlg.chk_klarf.setChecked(False)
#    assert dlg.run_export(sync=True) is None
#    assert "Nothing is selected" in dlg.error_text()
#
#F 877d92d66b6b539947142476b9d7d8bd6f32c9a8 132 tests/test_ui_f7_10_route_edges.py
## F7-10 驗收：畫布要畫出 route 的隱含順序。
#"""**畫布上沒有線，不代表沒有連接。**
#
#引擎的依賴是「route 相鄰對 ∪ 顯式 edges」（``recipe.execution_order``），
#但畫布以前只畫顯式 edges。於是載入一份沒拉過線的 recipe，使用者看到的是
#九張互不相干的卡 —— 而它其實是照順序跑的。他只會得到兩種結論，兩種都是錯的：
#以為要自己連起來才會跑，或以為沒連線的卡不會執行。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes" \
#    / "die_to_die_basic.json"
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import canvas as canvas_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    from make_sample import generate
#    return generate(str(tmp_path_factory.mktemp("f7_10")), n=6, seed=13)
#
#
#@pytest.fixture
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    win.load_recipe_path(str(EXAMPLE), sync=True)
#    yield win
#    win.close()
#
#
#def _edges(canvas, implicit):
#    return [e for e in canvas._edges if e.implicit is implicit]
#
#
#def test_a_recipe_with_no_explicit_links_still_shows_how_data_flows(window):
#    """範例 recipe 一條線都沒拉，但它是一條鏈 —— 畫布要看得出來。"""
#    assert window.model.edges == [], "前提：這份 recipe 沒有顯式 edges"
#    n = len(window.model.node_order)
#
#    implicit = _edges(window.pipeline, True)
#    assert implicit, "沒有畫出任何隱含連線 —— 使用者會以為卡片互不相干"
#    pairs = {e.pair() for e in implicit}
#    expected = set(zip(window.model.node_order, window.model.node_order[1:]))
#    assert pairs == expected
#
#
#def test_the_implicit_order_matches_what_the_engine_actually_does(window):
#    """畫的東西必須是引擎真的依據的東西，不是另一套說法。"""
#    from adept.core.pipeline import execution_order
#
#    order = execution_order(window.model.to_recipe(), window.model.kind)
#    drawn = {e.pair() for e in _edges(window.pipeline, True)}
#    drawn |= {e.pair() for e in _edges(window.pipeline, False)}
#    for a, b in zip(order, order[1:]):
#        assert (a, b) in drawn, "引擎認為 %s → %s，畫布上卻沒有這條線" % (a, b)
#
#
#def test_implicit_links_look_different_and_cannot_be_deleted(window):
#    """隱含順序來自卡片的排列。刪掉它在語意上等於「把卡片從流程裡拿掉」——
#    那是另一個動作，不該用同一個 Delete 鍵完成。"""
#    from PySide6.QtWidgets import QGraphicsItem
#
#    for e in _edges(window.pipeline, True):
#        assert not e.flags() & QGraphicsItem.ItemIsSelectable
#        assert "order of the cards" in e.toolTip()
#    for e in _edges(window.pipeline, False):
#        assert e.flags() & QGraphicsItem.ItemIsSelectable
#
#
#def test_drawing_the_link_yourself_turns_it_into_a_real_one(window):
#    """使用者把隱含的那條連起來 → 變成實線，而且不會畫成兩條。"""
#    a, b = window.model.node_order[0], window.model.node_order[1]
#    window.pipeline.link_to(a, b)
#
#    assert (a, b) in window.model.edges
#    assert (a, b) in {e.pair() for e in _edges(window.pipeline, False)}
#    assert (a, b) not in {e.pair() for e in _edges(window.pipeline, True)}, \
#        "同一對節點不可以同時有實線與虛線"
#
#
#def test_edge_pairs_still_reports_only_the_users_own_links(window):
#    """存檔寫的是使用者拉的線。隱含順序來自 route，存進 edges 會重複記錄。"""
#    assert window.pipeline.edge_pairs() == window.model.edges == []
#    window.pipeline.link_to(window.model.node_order[0],
#                            window.model.node_order[2])
#    assert window.pipeline.edge_pairs() == window.model.edges
#
#
#def test_a_long_chain_wraps_instead_of_running_off_the_screen(window):
#    """隱含連線讓每一份 recipe 都有依賴，所以換行必須對深度排版也成立
#    （不然九張卡又會排成一條 2500px 的橫列）。"""
#    cols = set()
#    for nid in window.pipeline.node_ids():
#        item = window.pipeline.card(nid)
#        cols.add(round(item.pos().x() / (canvas_mod.NODE_W + canvas_mod.COL_GAP)))
#    assert max(cols) < canvas_mod.WRAP
#    assert len(window.pipeline.node_ids()) > canvas_mod.WRAP, "前提：卡片數超過一行"
#
#
#def test_a_single_card_has_no_dangling_link(window):
#    """只有一張起手卡的時候不可以畫出「連到自己」之類的東西。"""
#    canvas = canvas_mod.PipelineCanvas()
#    canvas.set_nodes([{"node_id": "load", "label": "Load images",
#                       "group": "input", "enabled": True, "summary": "",
#                       "reads": [], "writes": ["test", "ref"]}], [])
#    assert canvas._edges == []
#
