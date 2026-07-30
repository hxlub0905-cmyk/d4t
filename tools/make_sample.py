#!/usr/bin/env python3
# ADEPT synthetic sample generator — authored 2026-07-28 (M1).
"""合成 EBI patch 測試 lot 產生器。

產出一個 ingest 層可以直接吃的迷你 lot：
  OUT_DIR/LOT_SYN.tif          多頁 TIFF（頁序：test0, ref0, test1, ref1, …）
  OUT_DIR/LOT_SYN.001          KLARF 1.2（TiffFileName + TiffSpec + IMAGELIST）
  OUT_DIR/ground_truth.json    {defect_id: {"is_real": bool, "type": str}}

每顆 defect 一組 test+ref uint8 影像對：
  - 共用的週期性圓角方格圖案（cell pitch 可調），每對隨機整體相位；
  - ref 額外帶 |dx|,|dy| <= shift_max 的隨機平移（**預設 0**：機台輸出的
    test/ref patch 本來就兩兩對應，不需要對位。要測對位就把它調大）；
  - 兩張各自加獨立高斯雜訊；
  - REAL 缺陷只種在 test（亮點 / 暗點 / 橋接線，振幅 >= 50、靠近中心）；
  - NUISANCE 只有雜訊 + 平移，沒有真缺陷。

用法：
  python3 tools/make_sample.py OUT_DIR [--n 24] [--real-frac 0.5] [--size 128]
                               [--pitch 16] [--noise 6] [--seed 7] [--shift-max 3]
也可 import：generate(out_dir, ...) -> {"out_dir","klarf","tiff","ground_truth"}。
同一組參數（含 seed）產出的 TIFF 位元組完全相同（可重現）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

import numpy as np
import tifffile

# 讓 `python3 tools/make_sample.py` 不裝套件也能 import adept（與同層的 _synth）
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from adept.core.ingest import dataset, klarf_core, tiff_index  # noqa: E402

# 圖案／缺陷合成的共用零件（與 make_sample_rsem.py 共用，數值行為完全相同）
from _synth import (  # noqa: E402
    NUISANCE_TYPE, REAL_TYPES,
    pattern as _pattern,
    plant_anomaly as _plant_anomaly,
    rounded_square_tile as _rounded_square_tile,
)

LOT_NAME = "LOT_SYN"

# KLARF 1.2 die pitch（µm）：XREL/YREL 會落在這個假 die 裡
_DIE_PITCH_UM = 5000.0


# ---------------------------------------------------------------- KLARF 產生

def _make_klarf_text(n: int, rows) -> str:
    """組出 KLARF 1.2 文字（LF 換行、固定 timestamp → 位元組可重現）。"""
    lines = [
        "FileVersion 1 2;",
        "FileTimestamp 07-28-26 00:00:00;",
        'InspectionStationID "SYN" "SYN" "ADEPT";',
        "SampleType WAFER;",
        "ResultTimestamp 07-28-26 00:00:00;",
        f'LotID "{LOT_NAME}";',
        "SampleSize 1 300;",
        'DeviceID "SYNDEV";',
        'SetupID "SYN" 07-28-26 00:00:00;',
        'StepID "SYNSTEP";',
        "SampleOrientationMarkType NOTCH;",
        "OrientationMarkLocation DOWN;",
        f"DiePitch {_DIE_PITCH_UM:.1f} {_DIE_PITCH_UM:.1f};",
        "DieOrigin 0.0 0.0;",
        'WaferID "W01";',
        "Slot 1;",
        f"TiffFileName {LOT_NAME}.tif;",
        'TiffSpec 6.1 1 "IMAGENUMBER";',
        "InspectionTest 1;",
        "DefectRecordSpec 8 DEFECTID XREL YREL XINDEX YINDEX CLASSNUMBER"
        " IMAGECOUNT IMAGELIST ;",
        "DefectList",
    ]
    body = "\n".join(" " + " ".join(r) for r in rows) + ";"
    lines.append(body)
    lines += [
        "SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;",
        "SummaryList",
        f" 1 {n} 1.0000000000e-03 25 {n};",
        "EndOfFile;",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主產生器

def generate(out_dir, n: int = 24, real_frac: float = 0.5, size: int = 128,
             pitch: int = 16, noise: float = 6.0, seed: int = 7,
             shift_max: int = 0) -> Dict[str, str]:
    """產生合成 lot 並自我驗證 ingest 層讀得回來。回傳輸出檔路徑 dict。"""
    if n < 1:
        raise ValueError(f"n 至少要 1（收到 {n}）")
    if not (0.0 <= real_frac <= 1.0):
        raise ValueError(f"real_frac 必須在 0–1 之間（收到 {real_frac}）")
    if size < 4 * pitch:
        raise ValueError(f"size（{size}）至少要是 pitch（{pitch}）的 4 倍，圖案才有週期性")
    if shift_max < 0:
        raise ValueError(f"shift_max 不可為負（收到 {shift_max}）")

    out_dir = str(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    tiff_path = os.path.join(out_dir, LOT_NAME + ".tif")
    klarf_path = os.path.join(out_dir, LOT_NAME + ".001")
    gt_path = os.path.join(out_dir, "ground_truth.json")

    rng = np.random.default_rng(int(seed))
    tile = _rounded_square_tile(pitch)

    # 哪些 defect 是 REAL
    n_real = int(round(n * real_frac))
    real_idx = set(rng.choice(n, size=n_real, replace=False).tolist()) if n_real else set()

    pages = []          # test0, ref0, test1, ref1, ...
    rows = []           # KLARF defect rows
    truth: Dict[str, Dict[str, Any]] = {}

    for i in range(n):
        # 共用圖案 + 每對隨機整體相位；ref 相位再偏 (-dx, -dy) →
        # ref(x, y) == test_clean(x - dx, y - dy)（algo.align 的正向慣例）
        ox = int(rng.integers(0, pitch))
        oy = int(rng.integers(0, pitch))
        dx = int(rng.integers(-shift_max, shift_max + 1))
        dy = int(rng.integers(-shift_max, shift_max + 1))
        test_f = _pattern(size, pitch, ox, oy, tile)
        ref_f = _pattern(size, pitch, ox - dx, oy - dy, tile)

        is_real = i in real_idx
        if is_real:
            kind = str(REAL_TYPES[int(rng.integers(0, len(REAL_TYPES)))])
            _plant_anomaly(test_f, kind, rng, pitch)    # 只種在 test
        else:
            kind = NUISANCE_TYPE

        test_f = test_f + rng.normal(0.0, noise, test_f.shape)
        ref_f = ref_f + rng.normal(0.0, noise, ref_f.shape)
        pages.append(np.clip(test_f, 0, 255).astype(np.uint8))
        pages.append(np.clip(ref_f, 0, 255).astype(np.uint8))

        defect_id = str(i + 1)
        truth[defect_id] = {"is_real": bool(is_real), "type": kind}

        xrel = float(rng.uniform(100.0, _DIE_PITCH_UM - 100.0))
        yrel = float(rng.uniform(100.0, _DIE_PITCH_UM - 100.0))
        xindex = int(rng.integers(-2, 3))
        yindex = int(rng.integers(-2, 3))
        # IMAGELIST：TiffSpec 每張圖 1 個 token（1-based TIFF 頁碼）
        rows.append([defect_id, f"{xrel:.3f}", f"{yrel:.3f}",
                     str(xindex), str(yindex), "0",
                     "2", str(2 * i + 1), str(2 * i + 2)])

    # ---- 寫 TIFF（多頁；同 seed → 位元組完全相同）----
    with tifffile.TiffWriter(tiff_path) as tw:
        for arr in pages:
            tw.write(arr, photometric="minisblack")

    # ---- 寫 KLARF 1.2 ----
    with open(klarf_path, "w", encoding="utf-8", newline="") as f:
        f.write(_make_klarf_text(n, rows))

    # ---- 寫 ground truth ----
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2, sort_keys=True)

    # ---- 自我驗證：ingest 層必須讀得回來 ----
    doc = klarf_core.load(klarf_path)
    assert doc.version == "1.2", f"KLARF 版本判定錯誤：{doc.version}"
    npages = tiff_index.n_pages(tiff_path)
    assert npages == 2 * n, f"TIFF 頁數不對：{npages} != {2 * n}"
    imap = doc.defect_image_map(npages)
    assert imap["mode"] is not None, f"defect_image_map 解不出來：{imap['notes']}"
    assert len(imap["pages"]) == n, f"對到 {len(imap['pages'])} 顆 defect（應為 {n}）"
    for i, pg in enumerate(imap["pages"]):
        assert pg == [2 * i, 2 * i + 1], f"defect {i + 1} 對到的頁不對：{pg}"

    ds = dataset.load_dataset(klarf_path)
    assert ds.kind == "ebi_patch", f"dataset kind 應為 ebi_patch，得到 {ds.kind}（warnings={ds.warnings}）"
    assert len(ds.items) == n, f"dataset 有 {len(ds.items)} 顆 defect（應為 {n}）"
    for i, it in enumerate(ds.items):
        assert "test" in it.images and "ref" in it.images, \
            f"defect {it.defect_id} 缺 test/ref ImageRef：{sorted(it.images)}"
        assert it.images["test"].page == 2 * i and it.images["ref"].page == 2 * i + 1, \
            f"defect {it.defect_id} 頁碼不對：test={it.images['test'].page} ref={it.images['ref'].page}"

    return {"out_dir": out_dir, "klarf": klarf_path, "tiff": tiff_path,
            "ground_truth": gt_path}


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="產生 ADEPT 合成 EBI patch lot（KLARF 1.2 + 多頁 TIFF + ground truth）。")
    ap.add_argument("out_dir", help="輸出資料夾（不存在會建立）")
    ap.add_argument("--n", type=int, default=24, help="defect 數量（預設 24）")
    ap.add_argument("--real-frac", type=float, default=0.5,
                    help="REAL 缺陷比例 0–1（預設 0.5，其餘為 nuisance）")
    ap.add_argument("--size", type=int, default=128, help="影像邊長（預設 128）")
    ap.add_argument("--pitch", type=int, default=16, help="圖案 cell 週期（預設 16）")
    ap.add_argument("--noise", type=float, default=6.0, help="高斯雜訊 sigma（預設 6）")
    ap.add_argument("--seed", type=int, default=7, help="隨機種子（同 seed 產出相同位元組）")
    ap.add_argument("--shift-max", type=int, default=0,
                    help="ref 相對 test 的最大平移（像素，預設 3）")
    args = ap.parse_args(argv)
    paths = generate(args.out_dir, n=args.n, real_frac=args.real_frac,
                     size=args.size, pitch=args.pitch, noise=args.noise,
                     seed=args.seed, shift_max=args.shift_max)
    print("Generated synthetic lot:")
    for k in ("klarf", "tiff", "ground_truth"):
        print(f"  {k:12s} {paths[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
