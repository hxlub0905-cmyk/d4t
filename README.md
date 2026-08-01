# ADEPT — Auto Defect Evaluation Pipeline Tool

> 彈性、多步驟、**任何 Inspection 站點都適用**的 ADC（Auto Defect Classification）工具。
>
> 讀半導體 E-beam Inspection 的 patch 影像（test + ref）或 Review SEM 單張影像 +
> 對應的 KLARF，用「步驟卡片組 pipeline」把腦中的想法變成算法，對每顆 defect 算分、
> 調參看整批分佈、再把結果寫回 KLARF。
>
> **核心理念：站點差異封裝進 recipe，不封裝進程式碼。**
> 傳統 PADC / RADC 每個站點都要工程師重寫一份 code；ADEPT 讓不會寫 code 的人
> 也能用滑鼠把想法組成算法，產出可量化的證據。

| | |
|---|---|
| **輸入** | KLARF + multi-page patch TIFF（EBI）｜KLARF + per-defect 影像（Review SEM）｜純資料夾 |
| **組裝** | 19 張步驟卡片，三段式：影像（把圖變乾淨）→ 算法（量出數字）→ ADC 判定（算分分 bin） |
| **輸出** | 無損寫回 KLARF（class / bin / DSIZE）｜Top-N 新 KLARF｜CSV / Excel 報表｜feature vector（ML 備料） |
| **介面** | PySide6 Studio 視覺化編輯器 ＋ CLI（可排程、可腳本化） |

完整計畫見 [`docs/plans/F0-master-plan.md`](docs/plans/F0-master-plan.md)；
接手開發請先讀 **[`docs/HANDOVER.md`](docs/HANDOVER.md)**（由來、決策理由、來源專案脈絡、
哪些已驗證哪些還是假設）與 [`CLAUDE.md`](CLAUDE.md)（操作手冊）。

## 目前進度：M0–M6 全部完成 ✅（v1 功能齊備）

M0：六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator / Perspective-Combination）
的可重用演算法已 vendoring 進 `adept/core`，全部通過合成影像單元測試、零 Qt 依賴。

M1：pipeline 引擎完成 —— Context/Step 契約、Recipe(DAG) + lint 驗證、score 表達式引擎
（安全語意，不會爆給使用者看）、單顆執行引擎、14 張卡片、合成資料產生器、CLI。
端到端驗收：合成 lot（24 顆、真/假各半）上範例 recipe 分類正確率 ~94%（跨 seed）。

M2：ProcessPool 平行批次（單顆爆不殺整批、progress/abort）、**影像段 checkpoint 快取**
（改算法段參數/門檻只重算後半）、SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）、
feature vector CSV 匯出。實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 →
warm cache 2.2 ms/顆 → rescore 0.17 s；換算 8 核廠內機 10k patch 約 1 分鐘、rescore 秒回。
快取空間約 50 KB/顆（10k ≈ 500 MB，可隨時清）。

M3：**Studio 視覺化介面**（PySide6）—— 卡片庫｜Pipeline｜單顆預覽｜分數直方圖 四區塊，
三段式分色（影像藍／算法橙／ADC 判定紫）。點卡片看該步驟的中間輸出、參數表單自動由
ParamSpec 生成（每格都有白話說明、範圍防呆、錯誤即時紅字）、拖門檻線即時看 bin 數變化。
**全程滑鼠，不用寫一行 code。**

M4：**雙輸入** —— Review SEM 單張影像（KLARF + 每顆一張圖）與 EBI patch（test/ref 配對）
都能吃，ingest 自動判別型別、recipe 自動走對應 route。沒有 ref 影像時由新的
**Golden Cell 卡**把圖上重複的 cell 疊成一張乾淨參考圖（含晶格相位自動搜尋）。
驗收：`examples/recipes/dual_route_basic.json` 一份 recipe、一個門檻，跨 3 seeds ×
2 種輸入共 144 顆合成 defect，分類正確率 95.1%。

M5：**Gallery + 輸出**。Gallery 把整批 defect 以縮圖網格攤開（虛擬捲動，10k 顆不卡），
可按分數或任一特徵排序，**點直方圖的長條就篩出那個分數區間的 defect** —— 調參迴圈
從一顆一顆點，變成一屏一屏掃。輸出精靈支援三種 KLARF 寫回（就地改欄無損／另存含
ADCSCORE+ADCCLASS 欄／Top-N 篩選新檔），**寫回前一定先預覽會改什麼**；另有 CSV /
Excel 報表（給 ground truth 就算抓漏率、誤殺率、混淆矩陣）與 overlay 影像。
另附 `fab_probe/` 三支 stdlib-only 探測腳本，用來在廠內確認格式假設（見下）。

M6：**推廣包**。離線安裝三件套（`fetch_wheels` → `install_offline` → `doctor`，
全部 stdlib-only，因為它們得在套件裝好之前就能跑）讓 pip 連不出去的廠內機器也裝得起來；
Studio 首次開啟有導覽，按一下「用範例資料試一次」就會自己產生合成資料、載入範本、
跑完一批，直接看到有分數的直方圖與 Gallery；範例 recipe 庫有 5 份，
每一份示範一種不同的作法（見 `examples/recipes/README.md`）。

```bash
# 開 Studio：
python -m adept gui

# CLI 試玩（不需真實資料）：
python tools/make_sample.py /tmp/lot --n 100         # 產合成 KLARF + patch TIFF
python -m adept steps                              # 看所有卡片
python -m adept validate examples/recipes/die_to_die_basic.json
python -m adept run examples/recipes/die_to_die_basic.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
python -m adept runs --db /tmp/runs.db             # 批次歷史
python -m adept rescore <run_id> --db /tmp/runs.db --threshold 60 --save   # 秒級調門檻
python -m adept export <run_id> --db /tmp/runs.db --mode annotate \
    --klarf-out out.001 --csv feat.csv --excel report.xlsx   # 寫回 KLARF + 報表
```

```
adept/
├── ui/                  # PySide6 Studio（唯一允許 Qt 的地方）
│   ├── viewmodel.py     #   RecipeModel（Qt-free 編輯模型）+ 直方圖/門檻計算
│   ├── theme.py         #   GLAS 暖色主題 token + 三段分色
│   ├── widgets.py       #   ImageView / ParamForm / LibraryPanel / PipelinePanel
│   │                    #   / HistogramWidget / FeatureTable / VerdictChip
│   ├── workers.py       #   載入 / 預覽（請求合併）/ 試跑 背景執行緒
│   ├── studio.py        #   StudioWindow 四區塊組裝
│   └── app.py           #   進入點（python -m adept gui）
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
├── (fab_probe/)         # 廠內格式探測腳本 —— 尚未建立，見 CLAUDE.md §8
└── tools/               # (M1+) 合成資料產生器、CLI
```

## 廠內格式驗證

開發全程用合成資料，原本有三個假設要用真實檔案確認。2026-07-30 結掉兩個：
**page→channel 對應已確認**（第一張 = test、第二張 = ref），**`nm_per_px` 用設計繞開**
（量測全程用 pixel，nm 換算搬到輸出時由使用者填 nm/px）。剩下 **KLARF 變體**還要確認。
`fab_probe/` 裡三支 stdlib-only 單檔腳本負責這件事，
輸出是**純文字、預設遮蔽 Lot/Wafer/Device 識別碼**，設計成可以直接複製貼出廠區：

```
python fab_probe\probe_klarf.py C:\path\to\file.klarf > report.txt
python fab_probe\probe_tiff.py  C:\path\to\file.tif --with-klarf C:\path\to\file.klarf
python fab_probe\probe_stats.py C:\path\to\file.tif
```

資料外流說明與逐項用途見 [`fab_probe/README.md`](fab_probe/README.md)。

## 沒有 git 的機器？

整個 repo 只有純文字檔（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml`），
不需要 git 也能用：GitHub → **Code** → **Download ZIP** → 解壓 → `pip install -r requirements.txt` → 跑。
完整步驟（含公司擋 pip 時的離線 wheels 作法）見 **[`docs/NO-GIT-SETUP.md`](docs/NO-GIT-SETUP.md)**。

## 開發環境

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt   # 含 PySide6（Studio 用）
pip install pytest
QT_QPA_PLATFORM=offscreen pytest -q   # 全部測試（~6s，不需真實資料；Windows 免設 QT_QPA_PLATFORM）
```

## Vendoring 慣例

- 每個 vendored 模組檔頭註明來源專案/檔案與改動清單。
- `adept/core` 禁止 Qt import（`tests/test_no_qt.py` 守門）。
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

M0 抽庫 ✅ → M1 引擎 ✅ → M2 批次 ✅ → M3 Studio UI ✅ → M4 雙輸入+Golden Cell ✅ →
M5 Gallery+Export ✅ → M6 推廣包 ✅。詳見 master plan。

## 已知修正紀錄（開發過程中抓到的坑）

- **Fusi³ `ecc` 對位 backend 位移正負號**與其他四個 backend 相反 → 已修（`algo/align.py`）。
- **OpenCV IPP 非決定性**：同張圖算兩次會有 ~1e-8 差異（SIMD 路徑依緩衝區位址而變），
  導致快取結果無法 bit-identical → `batch.pin_cv2_deterministic()` 關閉 IPP。
- **fork 死鎖**：Linux 預設 fork 若從非主執行緒（GUI 的 QThread）呼叫，
  ProcessPool 100% 卡死 → `batch._pool_context()` 改為主執行緒 fork、非主執行緒 spawn
  （迴歸測試 `tests/test_batch_thread_safety.py`）。
