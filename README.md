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
| **組裝** | 17 張步驟卡片、n8n 式節點畫布（拉線、拖卡、雙視窗）；使用者視角六階段：Input → Enhance → Region → Compare → Measure → ADC |
| **輸出** | 無損寫回 KLARF（class / bin / DSIZE）｜Top-N 新 KLARF｜CSV / Excel 報表｜feature vector（ML 備料） |
| **介面** | PySide6 Studio 視覺化編輯器 ＋ CLI（可排程、可腳本化） |

完整計畫見 [`docs/plans/F0-master-plan.md`](docs/plans/F0-master-plan.md)；
接手開發請先讀 **[`docs/HANDOVER.md`](docs/HANDOVER.md)**（由來、決策理由、來源專案脈絡、
哪些已驗證哪些還是假設）與 [`CLAUDE.md`](CLAUDE.md)（操作手冊）。

## 目前進度：M0–M7 完成 ✅（v1 功能齊備 + UI/UX 大改版）；F8 進行中

M0：六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator / Perspective-Combination）
的可重用演算法已 vendoring 進 `adept/core`，全部通過合成影像單元測試、零 Qt 依賴。

M1：pipeline 引擎完成 —— Context/Step 契約、Recipe(DAG) + lint 驗證、score 表達式引擎
（安全語意，不會爆給使用者看）、單顆執行引擎、14 張卡片、合成資料產生器、CLI。
端到端驗收：合成 lot（24 顆、真/假各半）上 die-to-die recipe 分類正確率 ~94%（跨 seed）。

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
驗收：一份 recipe、一個門檻，跨 3 seeds × 2 種輸入共 144 顆合成 defect，
分類正確率 95.1%（當時用的 `dual_route_basic.json` 現在留在
`tests/fixtures/recipes/`，e2e 測試仍在跑它）。

M5：**Gallery + 輸出**。Gallery 把整批 defect 以縮圖網格攤開（虛擬捲動，10k 顆不卡），
可按分數或任一特徵排序，**點直方圖的長條就篩出那個分數區間的 defect** —— 調參迴圈
從一顆一顆點，變成一屏一屏掃。輸出精靈支援三種 KLARF 寫回（就地改欄無損／另存含
ADCSCORE+ADCCLASS 欄／Top-N 篩選新檔），**寫回前一定先預覽會改什麼**；另有 CSV /
Excel 報表（給 ground truth 就算抓漏率、誤殺率、混淆矩陣）與 overlay 影像。
另附 `fab_probe/` 三支 stdlib-only 探測腳本，用來在廠內確認格式假設（見下）。

M6：**推廣包**。離線安裝三件套（`fetch_wheels` → `install_offline` → `doctor`，
全部 stdlib-only，因為它們得在套件裝好之前就能跑）讓 pip 連不出去的廠內機器也裝得起來；
Studio 首次開啟有導覽。

> ⚠ **範例 recipe 庫已於 2026-08-16 全部移除**（見上面 CLI 那段）。連帶地，
> 導覽上的「用範例資料試一次」與工具列的「Templates…」兩個入口也**收起來了** ——
> 沒有 recipe 可載，那兩顆按下去是死路。程式碼原封不動留著，
> 開關在 `adept/ui/scope.py` 的 `SHOW_SAMPLE_ENTRIES`，範例回來時改一個常數即可。

M7 / F7：**UI/UX 大改版**（使用者試用回饋累計九輪）。UI 全英文、中性平面主題
（亮/暗雙色盤）、**n8n 式節點畫布**取代直線清單 —— 卡片是節點、影像流是線、
從輸出埠拉線接卡、線上 hover 出「斷開」×、右鍵拖曳平移、手動佈局保留
（「排整齊」才整批重排）。版面是「D 案」：畫布佔中欄上側一條（它會 zoom、
可**彈出成獨立視窗**全尺寸編輯，兩個視窗即時互通），設定拿大頭、右欄影像/儀表。
每張卡有自己的右下角儀表（before/after 直方圖、整批分布、對位散佈…），
選卡片時預覽影像直接疊上它定義或引用的**區域框**。

F8：**純規則 ROI 定位**（`roi_cross`：兩組條紋的交會處自動放框、一鍵從整批量
pitch）與 **ROI mask 影像流**（`roi_mask` + Normalize 的 Use only：正規化的
範圍只從指定 pattern 量、套用整張圖）。資料模型見下一節。

```bash
# 開 Studio：
python -m adept gui

# CLI 試玩（不需真實資料）：
python tools/make_sample.py /tmp/lot --n 100         # 產合成 KLARF + patch TIFF
python -m adept steps                              # 看所有卡片
python -m adept validate my_recipe.json            # recipe 在 Studio 裡組出來再存檔
python -m adept run my_recipe.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
python -m adept runs --db /tmp/runs.db             # 批次歷史
python -m adept rescore <run_id> --db /tmp/runs.db --threshold 60 --save   # 秒級調門檻
python -m adept export <run_id> --db /tmp/runs.db --mode annotate \
    --klarf-out out.001 --csv feat.csv --excel report.xlsx   # 寫回 KLARF + 報表
```

> **repo 裡目前沒有現成的 recipe。** 舊的五份教學範例依賴已經被拿掉的卡片，
> 使用者決定「等 APP 完成再給範例」，所以 `examples/` 整個移除了（2026-08-16）。
> recipe 請在 Studio 裡組好再存檔；只是想確認引擎跑得動的話，
> `python tools/doctor.py` 會用**內建的**最小 pipeline 端到端跑一顆。
> （`tests/fixtures/recipes/` 底下那兩份是測試用的，不是教學範例。）

## 資料模型：兩個通道（影像流 vs 具名區域）

每顆 defect 跑 pipeline 時，所有卡片共用一個 **Context**，裡面有三層資料：

| 層 | 裝什麼 | 例子 | 特性 |
|---|---|---|---|
| **影像流 images** | 真正的像素陣列 | `test`、`ref`、`diff`、`mask` | 綁尺寸（H×W）、佔記憶體 |
| **具名區域 rois** | 名字 → 一串框 | `cross` = 64 個框，每框 (x,y,w,h) 用 **0–1 比例** | 不綁尺寸、帶**結構**（幾個框、各在哪、邊界在哪） |
| **特徵 features** | 名字 → 數字 | `roi_snr_abs = 5.2` | 進 score 表達式、寫回 KLARF |

```
影像流通道（像素）   Load ──→ Denoise ──→ Compare ──→ 'diff' ─────────┐
                                                                     ├─→ 量測卡 ──→ 特徵 ──→ score / bin
區域通道（哪裡）     Profile ／ GC Template ／ GDS(未來)               │    source='diff'（流）
                        └──→ 具名區域 'cross'（64 個框，0–1 座標）─────┘    roi='cross'（名字）
                                └─→ Mask from regions ──→ 'mask' 流 ──→ Normalize 的 Use only（影像段）
```

**規則一句話：量測卡吃區域「名字」，影像卡吃 mask「影像流」。**

- **量測卡**（glv_stats / ROI SNR / CD）要的是「哪裡」的**結構**：幾個框、
  框的邊界、框外一圈背景（ROI SNR 的背景取樣）、哪一框最靠中心。一張 0/255
  的 mask 圖把 64 個框壓扁成一坨像素，這些結構全部丟失 —— 所以量測卡的
  `roi` 欄填**名字**，引擎在量測當下才把名字換成「這顆 patch 上的那群像素」。
- **影像卡**（目前只有 Normalize 的 Use only）只需要「哪些像素參與統計」——
  那正是 mask 影像流的全部內容。`roi_mask` 卡把具名區域畫成 0/255 的流，
  在畫布上是一條看得見的線。
- 兩條路都從同一個 `Context.rois` 衍生 —— 一個來源、兩種視圖，不會分家。

**為什麼存「名字 + 正規化座標」，不是存 mask 圖：**

1. **patch 是以 defect 為中心裁的，晶格相位逐顆不同。** 存死的 mask 圖只對
   裁下那一瞬間的那一顆有效。所以 recipe 存的是「**怎麼找**」（規則／模板），
   定位卡**每顆 patch 重新定位**、每顆重寫這顆自己的框。
2. **尺寸無關。** 框存 (0.10, 0.20, 0.35, 0.60) 這種比例：128² 的 EBI patch
   落在 (13,26,45,77)px，之後 512² 的新 source 自動落在 (51,102,179,307)px ——
   **同一份 recipe 直接用**。

**ROI 定位的三種方法，同一個出口（契約）：**

| 定位法 | 怎麼找 | 需要什麼 |
|---|---|---|
| **Profile**（`roi_cross`，現有） | 純規則：投影找條紋 → 交會處放框，每顆 patch 自己算 | 不用外部資料 |
| **Golden Cell Template**（`roi_template`，現有） | 建模板時凍一個完整 cell 進 recipe；每顆用 NCC 對回相位、把標好的框搬過來 | 一張原大圖（建模板用一次） |
| **GDS**（未來） | 設計座標 → 多邊形 → 框 | .oas 檔 + 對位 + nm/px |

三者的出口**完全相同：吐具名區域**。所以新定位法加進來，下游的量測卡、
mask 卡、overlay、region check 一行都不用改。

**新 image source 進來時要動什麼（checklist）：**

1. Load 層：讓新格式讀進來變成具名影像流（尺寸不同沒關係）。
2. 定位層：挑一個在那種影像上找得到的定位法 → 吐具名區域。
3. 下游：**零改動**。量測照名字、mask 照流。

```
ADEPT/
├── adept/
│   ├── ui/                  # PySide6 Studio（唯一允許 Qt 的地方）
│   │   ├── studio.py        #   StudioWindow 組裝（D 案版面：畫布/設定/預覽）
│   │   ├── canvas.py        #   n8n 式節點畫布（拉線/拖卡/右鍵平移/彈出視窗）
│   │   ├── widgets.py       #   ImageView / ParamForm / LibraryPanel 等元件
│   │   ├── viewmodel.py     #   RecipeModel（Qt-free 編輯模型）+ 直方圖/門檻計算
│   │   ├── inspectors.py    #   每張卡自己的右下角儀表（依 Step.key 註冊）
│   │   ├── theme.py         #   中性平面主題 token（亮/暗雙色盤）+ 六階段分色
│   │   ├── gallery.py       #   同屏比多顆（虛擬捲動，撐 10k+）
│   │   ├── results.py       #   Results 視窗（直方圖 + Gallery + 輸出）
│   │   ├── export_dialog.py #   輸出精靈（寫回前一定先預覽變更）
│   │   ├── region_check.py  #   ROI 跨顆檢視（框畫在 N 顆縮圖上）
│   │   ├── template_dialog.py # 從大圖疊 Golden Cell 模板
│   │   ├── welcome.py       #   首啟導覽 + 範本庫對話框
│   │   ├── workers.py       #   載入 / 預覽（請求合併）/ 試跑 背景執行緒
│   │   ├── scope.py         #   產品範圍開關（patch-only、範例入口）
│   │   └── app.py           #   進入點（python -m adept gui）
│   ├── core/                # 純運算，**禁止任何 Qt import**
│   │   ├── ingest/          # KLARF 無損引擎(KLIP) + TIFF page 索引 + 型別自動判別
│   │   │   ├── klarf_core.py    #   KLARF 1.2/1.8 讀寫/健檢/比對 + defect↔page 對應
│   │   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
│   │   │   ├── imageio.py       #   CJK-safe 影像讀寫
│   │   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 → DefectItem
│   │   ├── algo/            # 純 numpy/cv2 演算法（step 卡片包這些）
│   │   │   ├── normalize.py     #   percentile / GLV-mask 正規化        (Fusi³)
│   │   │   ├── histmatch.py     #   直方圖匹配 exact/linear/percentile  (Fusi³)
│   │   │   ├── align.py         #   5-backend 對位 + robust + template  (Fusi³/GLAS)
│   │   │   ├── snr.py           #   canonical SNR + ROI SNR + SNR map   (Fusi³/PEAR)
│   │   │   ├── blob.py          #   defect blob 分割 + 幾何特徵          (Fusi³)
│   │   │   ├── roi.py           #   正規化座標 MultiROISet               (Fusi³)
│   │   │   ├── grid.py          #   條紋晶格偵測 + pitch 校正（F8 的主力）
│   │   │   ├── profile.py       #   投影曲線 / 轉折偵測
│   │   │   ├── template.py      #   Golden Cell 模板比對（NCC + 三道閘門）
│   │   │   ├── enhance.py       #   去噪 / 去背景 / 局部對比
│   │   │   ├── curve.py         #   保單調色調曲線（Fritsch–Carlson）
│   │   │   ├── glv.py           #   GLV 統計 metric bank                 (PEAR)
│   │   │   ├── stats.py         #   Tukey 離群 / Cohen's d / η²          (PEAR)
│   │   │   ├── period.py        #   cell 週期估測 + 相位搜尋             (CPE)
│   │   │   ├── golden.py        #   Golden Cell 堆疊 + ghosting 分數     (CPE)
│   │   │   ├── quality.py       #   focus/品質三指標                     (MMH)
│   │   │   └── subpixel.py      #   次像素邊緣定位（CD 用）              (MMH)
│   │   ├── pipeline/        # 引擎：Context / Step / Recipe(DAG) / 表達式 / 批次 / 快取
│   │   ├── steps/           # 17 張步驟卡片（每檔一類，import 即註冊）
│   │   ├── store/           # SQLite 批次歷史 + rescore
│   │   ├── export/          # KLARF 三種寫回 + CSV/Excel 報表 + overlay
│   │   └── calibration.py   # nm/px 校正 profile 管理                    (MMH)
│   └── __main__.py          # CLI（run / steps / validate / runs / rescore / export / gui）
├── tests/               # 1250+ 條合成影像測試 + 零 Qt / py3.9 / 無廠內資料守門
├── tools/               # 合成資料產生器、離線安裝三件套、FILELIST/bundle 工具
├── fab_probe/           # 廠內格式探測腳本（stdlib-only、輸出遮蔽識別碼）
├── docs/                # HANDOVER / 離線安裝 / 無 git 取得；plans/ 是開發計畫
└── bundle/              # 搬進廠內用的單檔壓縮包（產生物，見 AGENTS.md）
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
QT_QPA_PLATFORM=offscreen pytest -q   # 全套（家用機；不需真實資料；Windows 免設 QT_QPA_PLATFORM）
# 開發迴圈只跑改到的測試檔（pytest -q tests/test_xxx.py），全套留到 commit 前
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
M5 Gallery+Export ✅ → M6 推廣包 ✅ → M7/F7 UI/UX 大改版 ✅ → F8 純規則 ROI（進行中）。
詳見 master plan 與 `SESSION_LOG.md`（每輪的決策與理由）。

## 已知修正紀錄（開發過程中抓到的坑）

- **Fusi³ `ecc` 對位 backend 位移正負號**與其他四個 backend 相反 → 已修（`algo/align.py`）。
- **OpenCV IPP 非決定性**：同張圖算兩次會有 ~1e-8 差異（SIMD 路徑依緩衝區位址而變），
  導致快取結果無法 bit-identical → `batch.pin_cv2_deterministic()` 關閉 IPP。
- **fork 死鎖**：Linux 預設 fork 若從非主執行緒（GUI 的 QThread）呼叫，
  ProcessPool 100% 卡死 → `batch._pool_context()` 改為主執行緒 fork、非主執行緒 spawn
  （迴歸測試 `tests/test_batch_thread_safety.py`）。
