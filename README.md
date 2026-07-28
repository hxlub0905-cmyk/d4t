# Flex-ADC（工作代號）

> Flexible、多步驟、任何 Inspection 站點都適用的 ADC 工具：
> 讀 EBI patch（test+ref）或 RSEM 單張影像 + 對應 KLARF，
> 用「步驟卡片組 pipeline」把腦中想法變成算法，對每顆 defect 算分、
> 調參看整批分佈、寫回 KLARF。**站點差異封裝進 recipe，不封裝進程式碼。**

完整計畫見 [`docs/plans/F0-master-plan.md`](docs/plans/F0-master-plan.md)。

## 目前進度：M0 抽庫 ✅ · M1 引擎 ✅ · M2 批次 ✅

M0：六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator / Perspective-Combination）
的可重用演算法已 vendoring 進 `flexadc/core`，全部通過合成影像單元測試、零 Qt 依賴。

M1：pipeline 引擎完成 —— Context/Step 契約、Recipe(DAG) + lint 驗證、score 表達式引擎
（安全語意，不會爆給使用者看）、單顆執行引擎、14 張卡片、合成資料產生器、CLI。
端到端驗收：合成 lot（24 顆、真/假各半）上範例 recipe 分類正確率 ~94%（跨 seed）。

M2：ProcessPool 平行批次（單顆爆不殺整批、progress/abort）、**影像段 checkpoint 快取**
（改算法段參數/門檻只重算後半）、SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）、
feature vector CSV 匯出。實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 →
warm cache 2.2 ms/顆 → rescore 0.17 s；換算 8 核廠內機 10k patch 約 1 分鐘、rescore 秒回。
快取空間約 50 KB/顆（10k ≈ 500 MB，可隨時清）。

```bash
# 試玩（不需真實資料）：
python tools/make_sample.py /tmp/lot --n 100         # 產合成 KLARF + patch TIFF
python -m flexadc steps                              # 看所有卡片
python -m flexadc validate examples/recipes/die_to_die_basic.json
python -m flexadc run examples/recipes/die_to_die_basic.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
python -m flexadc runs --db /tmp/runs.db             # 批次歷史
python -m flexadc rescore <run_id> --db /tmp/runs.db --threshold 60 --save   # 秒級調門檻
```

```
flexadc/
├── core/
│   ├── ingest/          # KLARF 無損引擎(KLIP) + TIFF page 索引 + Dataset 自動判別
│   │   ├── klarf_core.py    #   KLARF 1.2/1.8 讀寫/健檢/比對 + defect↔page 對應
│   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
│   │   ├── imageio.py       #   CJK-safe 影像讀寫
│   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 → DefectItem
│   ├── algo/            # 純 numpy/cv2 演算法（未來 step 卡片包這些）
│   │   ├── normalize.py     #   percentile / GLV-mask 正規化        (Fusi³)
│   │   ├── histmatch.py     #   直方圖匹配 exact/linear/percentile  (Fusi³)
│   │   ├── align.py         #   5-backend 對位 + robust + template  (Fusi³/GLAS)
│   │   ├── snr.py           #   canonical SNR + ROI SNR + SNR map   (Fusi³/PEAR)
│   │   ├── blob.py          #   defect blob 分割 + 幾何特徵          (Fusi³)
│   │   ├── roi.py           #   正規化座標 MultiROISet               (Fusi³)
│   │   ├── glv.py           #   GLV 統計 metric bank                 (PEAR)
│   │   ├── stats.py         #   Tukey 離群 / Cohen's d / η²          (PEAR)
│   │   ├── period.py        #   cell 週期估測                        (CPE)
│   │   ├── golden.py        #   Golden Cell 堆疊 + ghosting 分數     (CPE)
│   │   ├── quality.py       #   focus/品質三指標                     (MMH)
│   │   └── subpixel.py      #   次像素邊緣定位（CD 用）              (MMH)
│   └── calibration.py   # nm/px 校正 profile 管理                    (MMH)
├── tests/               # 合成影像單元測試 + 零 Qt / py3.9 語法守門
├── docs/plans/          # 開發計畫（F0 = master plan）
├── fab_probe/           # (M1+) 廠內格式探測腳本
└── tools/               # (M1+) 合成資料產生器、CLI
```

## 開發環境

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
pip install pytest
pytest -q          # 全部測試（<1s，不需真實資料）
```

## Vendoring 慣例

- 每個 vendored 模組檔頭註明來源專案/檔案與改動清單。
- `flexadc/core` 禁止 Qt import（`tests/test_no_qt.py` 守門）。
- Python ≥ 3.9 相容（同樣由測試以 `ast.parse(feature_version=(3,9))` 守門）。

## 統一慣例（M0 修正的三個歷史摩擦）

1. **ROI 座標**：正規化座標（`NamedROI`）為正典；像素矩形一律 `(x, y, w, h)` tuple。
2. **SNR 正負號**：`snr_signed = (μ_target − μ_ref) / σ_ref`（e-beam 定義，PEAR 版）
   為唯一正典 primitive（`algo/snr.py`）；`roi_snr` 同時回報 signed 與 abs。
3. **`compute_snr_map`** 改回傳 `SnrMapResult(map_float, snr_max)`（原 Fusi³ 版
   回傳 tuple 與型別註記不符）。

另：vendoring 過程發現並修正原 Fusi³ `ecc` 對位 backend 的位移正負號 bug
（與其他四個 backend 相反），已在 `algo/align.py` 檔頭記錄。

## Roadmap

M0 抽庫 ✅ → M1 引擎（Step/Recipe DAG/表達式）→ M2 批次 → M3 Studio UI →
M4 雙輸入+Golden Cell → M5 Gallery+Export → M6 推廣包。詳見 master plan。
