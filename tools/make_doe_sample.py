#!/usr/bin/env python3
# d4t synthetic sample generator (DOE conditions) — authored 2026-09-18 (F112).
"""合成一個 **DOE** 測試 lot —— 一個子目錄一顆 defect、裡面每個檔案一個 condition。

DOE（使用者定調 2026-09-17）：同一顆 defect、**位置固定在 FOV 正中間、FOV 相同**，
用不同的 E-beam condition（Landing energy／電流）各拍一張，對齊之後在**同一組
target／ref box** 上比 SNR。對標公司內的 imageY 流程。

  OUT_DIR/defect_0001/le300.png   一顆一個資料夾，裡面每個檔案是一個 condition
  OUT_DIR/defect_0001/le500.png
  OUT_DIR/defect_0001/le800.png
  OUT_DIR/ground_truth.json       {defect_id: {"best": 最佳 condition, "noise": {...}}}

`dataset.load_doe_folder()` 讀它會回 ``kind == "doe_folder"``，每顆 defect 有 N 條
影像流（檔名排序 → `test` / `ref` / `img3`…，真正的名字由 `load_patch` 的
``channel_map`` 給）。

為什麼不沿用 `make_sample.py`（F112 量過才決定的）
------------------------------------------------
那一份的 patch **整張都是高對比的晶格**：實測任何一個 16×16 的框，灰階標準差都在
62 以上，而整張圖是 63.7。DOE 量的 ``snr_px = |μT − μR| / σR`` 的分母正是**參照那
一塊自己的像素標準差** —— 拿一塊全是圖案的地方當參照，σR 由圖案決定而不是由雜訊
決定，於是「哪一個 condition 訊噪比比較好」這個問題**在那份資料上根本問不出來**
（三個 condition 的 σR 差不到 3%）。

所以這裡的圖長得不一樣，而那不是偷懶是**照著 DOE 真的長什麼樣**做：

  - 背景是**低對比**的週期圖案（±``contrast`` 灰階，預設 6）—— 有結構（模板比對
    要得到一個峰）但不會淹掉雜訊；
  - **正中央**一顆缺陷（比背景亮 ``defect`` 灰階，預設 28）——
    DOE 的前提就是位置固定在中間；
  - 每個 condition 各自的高斯雜訊 σ（預設 18 / 8 / 2）—— 這才是 condition 之間
    真正的差別，而 ``snr_px`` 要排得出它們的順序。

同一組參數（含 seed）產出的每個檔案位元組完全相同（可重現）。

用法：
  python3 tools/make_doe_sample.py OUT_DIR [--n 6] [--size 128] [--pitch 16]
                                   [--contrast 6] [--defect 28] [--seed 3]
也可 import：``generate(out_dir, ...) -> {"out_dir", "defects", "ground_truth"}``。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from d4t.core.ingest import imageio

#: ``(condition 名, 那個 condition 的雜訊 σ)`` —— 越後面越安靜 = 訊噪比越好。
#:
#: 名字刻意長這樣（``le`` = landing energy）：DOE 的 condition 名是**使用者取的**，
#: 而 `load_patch` 的 ``channel_map`` 就是取名字的地方。這裡給的是檔名，
#: 不是流名 —— 分組是資料層的事、命名是 recipe 的事。
CONDITIONS: Tuple[Tuple[str, float], ...] = (
    ("le300", 18.0), ("le500", 8.0), ("le800", 2.0))


def _frame(size: int, pitch: int, contrast: float, defect: float,
           defect_px: int) -> np.ndarray:
    """一張乾淨的 DOE 畫面：低對比週期背景 ＋ **正中央**一顆缺陷。"""
    yy, xx = np.mgrid[0:size, 0:size]
    base = 118.0 + contrast * (np.sin(2 * np.pi * xx / float(pitch))
                               + np.sin(2 * np.pi * yy / float(pitch)))
    half = defect_px // 2
    c = size // 2
    base[c - half:c + half, c - half:c + half] += defect
    return base


def generate(out_dir, n: int = 6, size: int = 128, pitch: int = 16,
             contrast: float = 6.0, defect: float = 28.0,
             defect_px: int = 12, seed: int = 3) -> Dict[str, Any]:
    """產生合成 DOE lot 並自我驗證 ingest 層讀得回來。回傳輸出路徑 dict。"""
    d = str(out_dir)
    os.makedirs(d, exist_ok=True)
    rng = np.random.default_rng(int(seed))
    truth: Dict[str, Any] = {}
    made: List[str] = []
    for i in range(int(n)):
        did = "defect_%04d" % (i + 1)
        sub = os.path.join(d, did)
        os.makedirs(sub, exist_ok=True)
        # 每一顆的缺陷強度略有不同 —— 一批裡每顆都一樣強是不真實的，而
        # 「每一顆都算得出數字」比「每一顆的數字都一樣」有意義。
        amp = float(defect) * float(rng.uniform(0.7, 1.3))
        clean = _frame(int(size), int(pitch), float(contrast), amp, int(defect_px))
        for name, sigma in CONDITIONS:
            noisy = clean + rng.normal(0.0, float(sigma), clean.shape)
            imageio.save_gray(os.path.join(sub, "%s.png" % name),
                              np.clip(noisy, 0, 255).astype(np.uint8))
        truth[did] = {"best": CONDITIONS[-1][0], "defect_amplitude": round(amp, 2),
                      "noise": {k: v for k, v in CONDITIONS}}
        made.append(sub)

    gt = os.path.join(d, "ground_truth.json")
    with open(gt + ".tmp", "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=1, ensure_ascii=False, sort_keys=True)
    os.replace(gt + ".tmp", gt)          # 鐵則 5：檔案寫入一律 atomic

    # **自我驗證**：產完馬上用 ingest 讀一次（同 `make_sample.generate` 的慣例）
    # —— 產出一批讀不回來的資料，症狀會出現在很遠的地方。
    from d4t.core.ingest.dataset import load_doe_folder

    ds = load_doe_folder(d)
    if len(ds.items) != int(n):
        raise RuntimeError("wrote %d defects but ingest read %d back: %s"
                           % (n, len(ds.items), ds.warnings))
    return {"out_dir": d, "defects": made, "ground_truth": gt}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--pitch", type=int, default=16)
    ap.add_argument("--contrast", type=float, default=6.0)
    ap.add_argument("--defect", type=float, default=28.0)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args(argv)
    got = generate(a.out_dir, n=a.n, size=a.size, pitch=a.pitch,
                   contrast=a.contrast, defect=a.defect, seed=a.seed)
    print("%d defects x %d conditions -> %s"
          % (len(got["defects"]), len(CONDITIONS), got["out_dir"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
