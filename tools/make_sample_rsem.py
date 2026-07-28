#!/usr/bin/env python3
# ADEPT synthetic sample generator (Review SEM) — authored 2026-07-28 (M4-2).
"""合成 Review SEM（rSEM）測試 lot 產生器 —— ingest 的另一條分支。

和 `make_sample.py`（EBI patch：一份多頁 TIFF，每顆 defect 兩頁 test/ref）
相反，這裡走的是 **每顆 defect 一個獨立影像檔** 的 Review SEM 佈局：

  OUT_DIR/images/DEF_0001.png  每顆 defect 一張（預設 PNG，可 --format tif）
  OUT_DIR/LOT_RSEM.001         KLARF 1.8（defect 列尾帶 `Images 1 { "檔名" … }`）
  OUT_DIR/ground_truth.json    {defect_id: {"is_real": bool, "type": str}}

`dataset.load_dataset()` 讀這份 KLARF 會回 ``kind == "rsem"``、
每顆 defect 只有 ``images["single"]``（沒有 ref）——
正是 Golden Cell 卡（`cell_period` + `golden_cell`）要處理的情境。

影像內容（比 EBI patch 大、解析度高，預設 256²／cell pitch 24）：
  - 嚴格週期的圓角方格晶格，**每張圖隨機相位**（相位是裁切位移，不是重取樣，
    所以晶格仍然嚴格週期 → Golden Cell 的相位搜尋才有事情可做）；
  - 每張圖各自的亮度／對比微擾（模擬 SEM 每次取像的條件差異）；
  - 高斯雜訊；
  - REAL 缺陷在影像中心附近種一個異常（亮點／暗點／橋接線，振幅 >= 50）；
  - NUISANCE 只有晶格 + 雜訊，沒有真缺陷。

用法：
  python3 tools/make_sample_rsem.py OUT_DIR [--n 24] [--real-frac 0.5] [--size 256]
                                    [--pitch 24] [--noise 5] [--seed 11] [--format png]
也可 import：generate(out_dir, ...) -> {"out_dir","klarf","images_dir","images",
"ground_truth"}。同一組參數（含 seed）產出的每個檔案位元組完全相同（可重現）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import cv2
import numpy as np

# 讓 `python3 tools/make_sample_rsem.py` 不裝套件也能 import adept（與同層的 _synth）
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from adept.core.ingest import dataset, klarf_core  # noqa: E402

# 圖案／缺陷合成的共用零件（與 make_sample.py 共用同一組數值行為）
from _synth import (  # noqa: E402
    NUISANCE_TYPE, REAL_TYPES, pattern, plant_anomaly, rounded_square_tile,
)

LOT_NAME = "LOT_RSEM"
IMAGES_DIRNAME = "images"
FORMATS = ("png", "tif")

# KLARF 1.8 的座標單位是 nm（整數）：假 die 5 mm × 5 mm
_DIE_PITCH_NM = 5_000_000

# PNG 壓縮等級寫死 → 不同機器／不同 OpenCV 預設值都產出相同位元組
_PNG_PARAMS = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]

# 固定時間戳（KLARF 內容必須可重現，不能用 now()）
_TIMESTAMP = "07-28-26 00:00:00"


# ---------------------------------------------------------------- 影像寫出

def _encode(arr: np.ndarray, ext: str) -> np.ndarray:
    """把 uint8 灰階圖編碼成位元組緩衝（固定參數 → 可重現）。"""
    params = _PNG_PARAMS if ext == ".png" else []
    ok, buf = cv2.imencode(ext, arr, params)
    if not ok:
        raise IOError(f"影像編碼失敗（格式 {ext}）")
    return buf


def _write_image(path: str, arr: np.ndarray) -> None:
    """CJK 路徑安全的寫檔（同 imageio._encode_and_write 的 imencode + tofile 手法）。"""
    _encode(arr, os.path.splitext(path)[1]).tofile(path)


# ---------------------------------------------------------------- KLARF 產生

def _make_klarf_text(rows: List[str]) -> str:
    """組出 KLARF 1.8 文字（LF 換行、固定 timestamp → 位元組可重現）。

    每顆 defect 的影像檔名放在 ``ImageList IMAGEINFO`` 欄，語法與廠內實檔
    （tests/fixtures/sample_real.klarf）相同：

        <欄位…> IMAGECOUNT Images 1 { "images/DEF_0001.png" "PNG" 1 "24" } ;

    `klarf_core.defect_image_filename()` 取區塊內第一個帶引號字串當檔名；
    `image_layout()` 也認得這種 'images18' 佈局（欄位起點正好落在 IMAGEINFO）。
    """
    body = "\n".join("          " + r for r in rows)
    return f"""Record FileRecord  "1.8"
{{
  Field FileTimestamp 1 {{"{_TIMESTAMP}"}}
  Field InspectionStationID 3 {{"SYN", "SYN", "ADEPT"}}

  Record LotRecord "{LOT_NAME}"
  {{
    Field DeviceID 1 {{"SYNDEV"}}
    Field StepID 1 {{"SYNSTEP"}}
    Field SampleType 1 {{"WAFER"}}
    Field ResultTimestamp 1 {{"{_TIMESTAMP}"}}

    Record WaferRecord "W01"
    {{
      Field DieOrigin 2 {{0, 0}}
      Field DiePitch 2 {{{_DIE_PITCH_NM}, {_DIE_PITCH_NM}}}
      Field OrientationMarkLocation 1 {{"DOWN"}}
      Field SlotNumber 1 {{1}}

      List DefectList
      {{
        Columns 9 {{ int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,
        int32 YINDEX,  int32 CLASSNUMBER,  int32 TEST,  int32 IMAGECOUNT,
        ImageList IMAGEINFO  }}
        Data {len(rows)}
        {{
{body}
        }}
      }}
    }}
  }}
}}
EndOfFile;
"""


def _defect_row(defect_id: str, xrel: int, yrel: int, xindex: int, yindex: int,
                rel_name: str, fmt: str) -> str:
    """一列 defect（列尾帶 Images 區塊；`,` 不可出現在檔名內）。"""
    return (f"{defect_id} {xrel} {yrel} {xindex} {yindex} 0 1 1 "
            f'Images 1 {{ "{rel_name}" "{fmt.upper()}" 1 "24" }} ;')


# ---------------------------------------------------------------- 主產生器

def generate(out_dir, n: int = 24, real_frac: float = 0.5, size: int = 256,
             pitch: int = 24, noise: float = 5.0, seed: int = 11,
             fmt: str = "png") -> Dict[str, Any]:
    """產生合成 rSEM lot 並自我驗證 ingest 層讀得回來。回傳輸出檔路徑 dict。"""
    if n < 1:
        raise ValueError(f"n 至少要 1（收到 {n}）")
    if not (0.0 <= real_frac <= 1.0):
        raise ValueError(f"real_frac 必須在 0–1 之間（收到 {real_frac}）")
    if pitch < 4:
        raise ValueError(f"pitch 至少要 4（收到 {pitch}），否則疊不出 cell")
    if size < 4 * pitch:
        raise ValueError(f"size（{size}）至少要是 pitch（{pitch}）的 4 倍，圖案才有週期性")
    if noise < 0:
        raise ValueError(f"noise 不可為負（收到 {noise}）")
    fmt = str(fmt).lower().lstrip(".")
    if fmt not in FORMATS:
        raise ValueError(f"format 只支援 {'/'.join(FORMATS)}（收到 {fmt!r}）")

    out_dir = str(out_dir)
    img_dir = os.path.join(out_dir, IMAGES_DIRNAME)
    os.makedirs(img_dir, exist_ok=True)
    klarf_path = os.path.join(out_dir, LOT_NAME + ".001")
    gt_path = os.path.join(out_dir, "ground_truth.json")

    rng = np.random.default_rng(int(seed))
    tile = rounded_square_tile(pitch)

    # 哪些 defect 是 REAL
    n_real = int(round(n * real_frac))
    real_idx = set(rng.choice(n, size=n_real, replace=False).tolist()) if n_real else set()

    rows: List[str] = []
    img_paths: List[str] = []
    truth: Dict[str, Dict[str, Any]] = {}

    for i in range(n):
        # 每張圖自己的晶格相位（裁切位移 → 仍然嚴格週期）
        ox = int(rng.integers(0, pitch))
        oy = int(rng.integers(0, pitch))
        img = pattern(size, pitch, ox, oy, tile)

        # 每張圖的亮度／對比微擾（在種缺陷之前做，缺陷振幅才不會被 gain 縮掉）
        gain = float(rng.uniform(0.90, 1.10))
        bias = float(rng.uniform(-10.0, 10.0))
        img = (img - 128.0) * gain + 128.0 + bias

        is_real = i in real_idx
        if is_real:
            kind = str(REAL_TYPES[int(rng.integers(0, len(REAL_TYPES)))])
            plant_anomaly(img, kind, rng, pitch)
        else:
            kind = NUISANCE_TYPE

        img = img + rng.normal(0.0, noise, img.shape)
        u8 = np.clip(img, 0, 255).astype(np.uint8)

        defect_id = str(i + 1)
        name = f"DEF_{i + 1:04d}.{fmt}"
        path = os.path.join(img_dir, name)
        _write_image(path, u8)
        img_paths.append(path)

        truth[defect_id] = {"is_real": bool(is_real), "type": kind}

        xrel = int(rng.integers(100_000, _DIE_PITCH_NM - 100_000))
        yrel = int(rng.integers(100_000, _DIE_PITCH_NM - 100_000))
        rows.append(_defect_row(defect_id, xrel, yrel,
                                int(rng.integers(-2, 3)), int(rng.integers(-2, 3)),
                                IMAGES_DIRNAME + "/" + name, fmt))

    # ---- 寫 KLARF 1.8 ----
    with open(klarf_path, "w", encoding="utf-8", newline="") as f:
        f.write(_make_klarf_text(rows))

    # ---- 寫 ground truth ----
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2, sort_keys=True)

    # ---- 自我驗證 1：影像編碼是決定性的（同輸入 → 同位元組）----
    with open(img_paths[0], "rb") as f:
        first = f.read()
    again = _encode(cv2.imdecode(np.frombuffer(first, np.uint8),
                                 cv2.IMREAD_GRAYSCALE),
                    os.path.splitext(img_paths[0])[1]).tobytes()
    assert again == first, (
        f"影像編碼不是決定性的（{os.path.basename(img_paths[0])} 重編後位元組不同）；"
        "同 seed 產出將無法重現。")

    # ---- 自我驗證 2：KLARF 解得開、每顆 defect 都指到存在的檔案 ----
    doc = klarf_core.load(klarf_path)
    assert doc.version == "1.8", f"KLARF 版本判定錯誤：{doc.version}"
    assert len(doc.defects) == n, f"KLARF 解出 {len(doc.defects)} 列 defect（應為 {n}）"
    layout = doc.image_layout()
    assert layout is not None and layout[2] == "images18", \
        f"影像欄佈局判定錯誤：{layout}（應為 images18）"
    for k, row in enumerate(doc.defects):
        fname = doc.defect_image_filename(row)
        assert fname, f"defect {k + 1} 的列尾沒解出影像檔名：{' '.join(row)}"
        assert os.path.isfile(os.path.join(out_dir, fname)), \
            f"defect {k + 1} 指到不存在的影像：{fname}"
        assert len(doc.defect_image_entries(row)) == 1, \
            f"defect {k + 1} 的 Images 區塊解出 {len(doc.defect_image_entries(row))} 條（應為 1）"

    # ---- 自我驗證 3：dataset 層必須判成 rsem 且讀得出像素 ----
    ds = dataset.load_dataset(klarf_path)
    assert ds.kind == "rsem", f"dataset kind 應為 rsem，得到 {ds.kind}（warnings={ds.warnings}）"
    assert len(ds.items) == n, f"dataset 有 {len(ds.items)} 顆 defect（應為 {n}）"
    for i, it in enumerate(ds.items):
        assert set(it.images) == {"single"}, \
            f"defect {it.defect_id} 的 channel 應只有 single，得到 {sorted(it.images)}"
        ref = it.images["single"]
        assert ref.page is None, f"defect {it.defect_id} 的 single 不該是 TIFF 頁（page={ref.page}）"
        assert os.path.isfile(ref.path), f"defect {it.defect_id} 的影像不存在：{ref.path}"
        assert os.path.abspath(ref.path) == os.path.abspath(img_paths[i]), \
            f"defect {it.defect_id} 對到的檔案不對：{ref.path} != {img_paths[i]}"
        arr = it.load("single")
        assert arr.shape == (size, size) and arr.dtype == np.uint8, \
            f"defect {it.defect_id} 像素讀回來是 {arr.shape}/{arr.dtype}（應為 {(size, size)}/uint8）"

    return {"out_dir": out_dir, "klarf": klarf_path, "images_dir": img_dir,
            "images": img_paths, "ground_truth": gt_path}


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="產生 ADEPT 合成 Review SEM lot（KLARF 1.8 + 每顆 defect 一張影像 + ground truth）。")
    ap.add_argument("out_dir", help="輸出資料夾（不存在會建立）")
    ap.add_argument("--n", type=int, default=24, help="defect 數量（預設 24）")
    ap.add_argument("--real-frac", type=float, default=0.5,
                    help="REAL 缺陷比例 0–1（預設 0.5，其餘為 nuisance）")
    ap.add_argument("--size", type=int, default=256, help="影像邊長（預設 256）")
    ap.add_argument("--pitch", type=int, default=24, help="圖案 cell 週期（預設 24）")
    ap.add_argument("--noise", type=float, default=5.0, help="高斯雜訊 sigma（預設 5）")
    ap.add_argument("--seed", type=int, default=11, help="隨機種子（同 seed 產出相同位元組）")
    ap.add_argument("--format", dest="fmt", default="png", choices=list(FORMATS),
                    help="影像檔格式（預設 png）")
    args = ap.parse_args(argv)
    paths = generate(args.out_dir, n=args.n, real_frac=args.real_frac,
                     size=args.size, pitch=args.pitch, noise=args.noise,
                     seed=args.seed, fmt=args.fmt)
    print("Generated synthetic rSEM lot:")
    for k in ("klarf", "images_dir", "ground_truth"):
        print(f"  {k:12s} {paths[k]}")
    print(f"  {'images':12s} {len(paths['images'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
