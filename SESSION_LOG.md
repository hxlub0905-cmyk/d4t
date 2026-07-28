# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

---

## 2026-07-28 · M5 Gallery + Export（347 → 514 tests）

### Gallery（同屏比多顆）
`adept/ui/gallery.py`：整個網格是**一個**自繪 widget（`QAbstractScrollArea`），
只畫可視範圍 + 1 列 overscan，10 顆與 10,000 顆的 widget tree 完全相同
（`set_items(10k)` 約 0.05 s）。QPixmap 轉換走 512 筆上限的 LRU。
縮圖在背景執行緒解碼：gallery 發 `thumbs_requested(ids)` → Studio 的 `ThumbWorker`
只解可視範圍那批（每批上限 48），in-flight 的 id 不重算。

**直方圖點 bar → Gallery 篩選**是這一版的關鍵串接（調參迴圈的另一半）。
難處在於同一個 widget 既要拖門檻又要點長條：解法是**在放開時才判定** ——
按下時照舊記錄狀態，放開時若位移 > 3px 或按在門檻把手上就當拖曳，
否則把門檻還原（並補發一次 `threshold_changed` 讓即時 bin 統計回捲）再發 `bar_clicked`。
所以點長條保證不會動到門檻，兩種行為都有測試鎖住。

### Export（三種 KLARF 寫回）
`adept/core/export/`：
- **inplace**：只走 `set_cell`，且值相同就不寫 —— 沒改到任何東西時輸出**逐位元組相同**（有測試）。
  要求的欄位不存在時直接拋 `ExportError` 說明，不靜默略過。
- **annotate**：1.2 改寫 `DefectRecordSpec`、1.8 改寫 `Columns N { … }`，
  新欄位插在影像 token 起始欄之前，**影像區塊仍在列尾**；輸出重新解析後
  `defect_image_map` / `load_dataset` 都仍正常。
- **topn**：分數排序取前 N、DEFECTID 重新編號。**page 編號刻意不重映射**
  （那需要一併重寫 TIFF），輸出檔必須與原 TIFF 放在一起 —— 這點寫進 plan 的 notes。

UI 上最重要的設計是**「預覽變更」按鈕**：先跑 `plan_writeback` 乾跑，
用白話列出會改幾列、動到哪些欄、新增哪些欄、健檢結果，預覽成功才解鎖「寫出」。
任何控制項一改動就作廢重鎖。

### fab_probe（廠內格式探測）
三支 stdlib-only 單檔腳本，輸出純文字、預設遮蔽 Lot/Wafer/Device 識別碼，
設計成可以複製貼出廠區。對應 CLAUDE.md §8 的三個假設。
`probe_stats.py` 自己寫了 TIFF 解碼（未壓縮 / PackBits，8 與 16 bit，
含 BigTIFF 與 big-endian），與 numpy 逐位元組比對驗證過；遇到解不了的壓縮
會明講並跳過該頁而不是整支掛掉。

### 順帶抓到並修掉一個真實資料上的 bug
`probe_klarf.py` 跑在 `tests/fixtures/sample_real.klarf`（專案裡唯一一份真實來源的
KLARF）上時發現**第四種變體**：`ImageList` 型別欄（IMAGEINFO）**不在最後一欄**，
而且整份檔案沒有 IMAGECOUNT 欄。`row_len_ok` 原本用原始 token 數比對欄數，
把佔 8 個 token 的 `Images 1 { … }` 當成 8 欄 → **每一列都被判違法**，
`lint()` 對一份完全正常的檔案報 rowlen error。使用者會看到的症狀是：
Export 精靈在寫回真實檔案前跳出嚇人的紅字。

修法是加 `image_block_span()` / `effective_row_len()`，把子區塊折算成一欄。
**刻意沒動 `image_layout()`** —— 它對這個變體回 None，而 export 的插欄位置
正好因此落在最後，對這個變體來說是對的；「順手修好」它反而會把新欄位插錯位置。
這點寫進 CLAUDE.md 的坑表了。迴歸測試 `tests/test_klarf_variant_d.py`。

### 下一步
M6 推廣包（離線 wheels 安裝、首啟導覽、範例 recipe 庫、快速參考卡）。

---

## 2026-07-28 · M4 雙輸入 + Golden Cell（341 → 356 tests）

驗收目標：**同一份 recipe 吃 EBI patch 與 Review SEM 兩種輸入**。達成，
`examples/recipes/dual_route_basic.json` 跨 3 seeds × 2 種輸入共 144 顆合成 defect，
分類正確率 95.1%（同一條分數表達式、同一個門檻）。

### 補完 `period.choose_origin` 相位搜尋
原本是回傳 `(0,0)` 的 stub。改為掃描 `[0,px) x [0,py)` 的候選原點，用
`stack_cells` + `ghosting_score` 的**原始 Laplacian 變異數**（非 0–100 分數，
後者在乾淨圖上會飽和而失去排序）挑最銳利的相位；候選數上限 ~256 再 ±2 微調，
512² / pitch 64 約 0.5 s。誠實的但書寫進 docstring：對完美週期圖，重建本身
與相位無關，所以這個準則是**平移等變**而非絕對 —— 它鎖定的是「cell 邊界對齊
圖案最強邊緣」的相位。測試據此驗證等變性（裁切 c 像素 → 原點位移 −c mod pitch）。

### 兩張新卡片
- **`cell_period`**（算法段）：量出 X/Y 週期，寫進 `ctx.meta["cell_period"]` 供下游用。
  沒有週期性是 warning 不是 error。
- **`golden_cell`**（影像段）：疊出參考圖，預設寫入 `out="ref"` ——
  **這個預設是關鍵設計**：下游所有吃 ref 的卡片完全不用改，
  rsem route 只是多插一張卡就能重用整條 EBI 的算法段。
  輸出會平鋪回原尺寸/dtype/通道數，確保能直接相減。

### RSEM 合成資料產生器
`tools/make_sample_rsem.py`：每顆 defect 一張 PNG + KLARF 1.8 的
`Images N { "path" "PNG" 1 "24" }` 區塊（語法是讀 `klarf_core` 反推並 round-trip
驗證出來的，不是猜的）。256²、pitch 24、每張隨機相位。`tools/_synth.py` 抽出
與 EBI 產生器共用的晶格/植入缺陷程式碼，`make_sample.py` 輸出維持位元組相同。

### 調 recipe 時撞到的兩件事（都寫進 CLAUDE.md 的坑表）
1. **幾何參數與影像尺寸綁死**：同一組 `glv_stats` 中心框在 128² patch 上準，
   在 256² RSEM 上漏抓六顆 —— 缺陷散佈範圍（±10% 影像寬）超出固定框。
   解法：幾何類參數隨 route 走（兩條 route 各自一個 glv 節點）。
2. **共用門檻需要無量綱分數**：兩條 route 的絕對 GLV 尺度不同，
   `glv_max + (glv_max - glv_q99)` 各自能分開但沒有共用門檻窗。
   改用穩健 z 分數 `(glv_max - glv_median) / (glv_std + 0.5)`
   （「最強殘差高出典型殘差幾個 sigma」）後，兩邊共用門檻 4.2 成立。

### 下一步
M5 Gallery + Export（見 CLAUDE.md §9）。`fab_probe/` 廠內探測腳本從 M4 順延到 M5。

---

## 2026-07-28 · M0–M3 + 專案命名（Claude Cowork session）

從零建立整個專案。原工作代號 FlexADC，完成 M3 後定名 **ADEPT**。

### M0 抽庫（117 tests）
盤點六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator /
Perspective-Combination），把可重用演算法 vendoring 進 `adept/core`。
決策：**vendoring 而非共用 library** —— 新工具完全獨立、不動現有專案。

統一了三個歷史摩擦：
1. ROI 座標 → 正規化座標（`NamedROI`）為正典，像素矩形一律 `(x,y,w,h)`。
2. SNR 正負號 → `snr_signed = (μ_target − μ_ref)/σ_ref` 為唯一正典 primitive。
3. `compute_snr_map` → 改回傳 `SnrMapResult(map_float, snr_max)`（原版回傳 tuple 與型別註記不符）。

順手抓到 **Fusi³ `ecc` 對位 backend 位移正負號與其他四個相反**的 bug（原專案可回頭修）。

### M1 引擎（223 tests）
- `Context` / `Step` / `ParamSpec` / registry 契約（MMH recipe 架構的一般化：
  寫死 6 stage → 任意 DAG 節點，並補上 MMH 缺的參數驗證）。
- `Recipe`(DAG) + lint 式 `validate`（10 種 issue code，一次列出所有問題）。
- score 表達式引擎：自寫 tokenizer → recursive-descent parser → AST → evaluator，
  **不用 Python eval**；安全語意（除以零/log 負數/nan → 0.0，不爆給使用者看）。
- 14 張步驟卡片、合成資料產生器、CLI。
- **端到端驗收**：合成 lot（24 顆、真假各半）分類正確率 ~94%（跨 seed）。
  調出這份範例 recipe 的過程本身就是工具價值的實證 —— 第一版完全分不開
  （Otsu 在正規化 SNR map 上把半張圖切成 blob），靠 feature 表診斷 →
  主 blob 選取從「面積最大」改「SNR 最強」→ 加 Denoise 卡 →
  score 改用 diff 中心區 GLV 峰值，三輪迭代從 50% 拉到 94%。

### M2 批次（245 tests）
- ProcessPool 平行批次（單顆爆不殺整批、progress/abort）。
- **影像段 checkpoint 快取**：快取邊界切在三段式的「影像段結尾」，
  與 UI 心智模型對齊 —— 改算法段/判定段的任何東西都是秒級回饋。
- SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）。
- 實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 → warm cache 2.2 ms/顆 →
  rescore 0.17 s。換算 8 核廠內機 10k patch 約 1 分鐘。
- 過程中發現 **OpenCV IPP 非決定性**（同圖算兩次差 ~1e-8，SIMD 路徑依緩衝區位址而變），
  導致快取無法 bit-identical → `pin_cv2_deterministic()` 關閉 IPP。

### M3 Studio UI（291 tests）
- PySide6 四區塊：卡片庫｜Pipeline｜單顆預覽｜分數直方圖，三段式分色。
- `RecipeModel` 是 Qt-free 的編輯模型（可 headless 測試），UI 元件只做顯示與轉發。
- ParamForm 由 ParamSpec 自動生成，每格都有白話說明、範圍防呆、錯誤即時紅字。
- PreviewWorker 請求合併（改參數狂發請求只跑最新那個）。
- 拖門檻線即時看 bin 數變化（走 rescore 的純計算路徑，不碰影像）。
- **修掉一個會讓工具在廠內「看起來當掉」的 bug**：`run_batch` 從 QThread fork
  ProcessPool 在 Linux 上第二次必定死鎖（進度條不動也不報錯）。
  修法：`batch._pool_context()` 主執行緒 fork（CLI/腳本免寫 `if __name__ == "__main__"`）、
  非主執行緒 spawn。補迴歸測試 `tests/test_batch_thread_safety.py`。
- 補上卡片庫「ADC 判定」段的固定 Score/Bin 項目，讓三段式故事在 UI 上完整。

### 命名
候選過水果系（PEACH/FIG/PLUM，與 PEAR 成家族）與非水果系，最後選
**ADEPT = Auto Defect Evaluation Pipeline Tool** —— 縮寫精準對應功能，
而 adept（熟練、得心應手）正是要給不寫 code 同事的承諾。
套件 `flexadc` → `adept`、CLI `python -m adept`、設定目錄 `~/.adept/`。

### 下一步
M4 雙輸入 + Golden Cell（見 CLAUDE.md §9）。
