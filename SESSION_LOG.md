# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

---

## 2026-07-28 · M6 推廣包（514 → 588 tests）· v1 功能齊備

### 離線安裝三件套（對主要使用者最關鍵的一塊）
使用情境是**沒有 git、pip 連不出去、DLP 擋含二進位壓縮檔**的公司機。
`tools/fetch_wheels.py`（有網路的機器抓 Windows wheels，產 MANIFEST 含 sha256）→
帶 `wheels\` 過去 → `tools/install_offline.py`（建 venv、`--no-index` 安裝）→
`tools/doctor.py`（環境自檢）。三支都 **stdlib-only**，因為它們要在套件裝好之前就能跑
（有測試用 ast 掃 module-level import 把這條約束鎖住）。

`install_offline.py` 的八道 pre-flight 全部是「在 pip 之前就攔下來並講清楚」：
最常見的失敗是 **wheels 的 Python 版本與機器上的不符**（cp39 輪子配 py3.12），
它會讀 MANIFEST 比對、指出兩邊版本、給兩個選項。其餘涵蓋 requirements 找不到
（→「你可能不在 ADEPT 資料夾裡」）、wheels 資料夾空的（→ 提示 DLP 可能吃掉了 zip）、
磁碟空間、寫入權限，以及 `ensurepip` 被企業映像檔關掉時的 `--no-venv` 逃生路徑。

`doctor.py` 逐項 ✓/✗/△ 並在每個沒過的項目附一行「怎麼修」，包含一個常見錯誤的
專門偵測：**在錯的資料夾執行**（有 `adept\` 但 import 不到 → 直接叫他 cd）。
Qt 能不能開視窗是在 **subprocess** 裡測的，這樣壞掉的 PySide6 不會把 doctor 一起帶走。

### 首啟導覽
`adept/ui/welcome.py`。核心是那顆**「用範例資料試一次」**按鈕：一按就自己產生合成資料、
載入範本、跑完一批，使用者一分鐘內看到有分數的直方圖與 Gallery ——
不需要先有真實資料、不需要先懂任何概念。導覽本身用三段式配色講清楚
影像 → 算法 → ADC 判定 的心智模型。

modal 不能污染測試，用了三層防護：constructor kwarg 自動偵測 `PYTEST_CURRENT_TEST`、
`QTimer.singleShot(0, …)` 讓建構子永不阻塞、對話框一律 `show()` 不用 `exec()`。

### 範例 recipe 庫（5 份，每份教一種作法）
| recipe | 教什麼 |
|---|---|
| `die_to_die_basic` | 最典型：機台給 ref，對位相減 |
| `dual_route_basic` | 一份 recipe 兩條 route，吃兩種輸入 |
| `rsem_golden_cell` | 沒有 ref 就自己疊一張（且**不需要 norm 與 align** —— 自己減自己，增益偏移自動抵銷）|
| `single_image_rules` | 完全沒有參考圖的保底流程：把口語規則寫成一條乘法算式 + 比較運算子當閘 |
| `cd_gate` | 分數可以有物理單位：閘門確認真假、CD 決定重要性，門檻直接填「你在意的最小缺陷尺寸」|

Agent 是**實測迭代**出這些算式的，不是照抄我給的建議 —— 例如原本建議 RSEM 用
`blob_snr`，實測只有 ~55%，因為 `blob_snr` 在 uint8 SNR 地圖上會飽和在 255；
改用 GLV 殘差才是誠實的贏家。`tests/test_example_recipes.py` 會確認每一份都能載入、
validate 無 error、且真的能在合成資料上跑出有限分數 —— 這是防止範例庫腐爛的網子。

### 暫緩
快速參考卡 PDF 移到 backlog（使用者當下不需要）。

### 狀態
v1 規劃的六個 milestone 全部完成，588 tests。

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

---

## 2026-07-28 · M7 UI/UX 檢討（Claude Code session）

接手 session：先讀 `docs/HANDOVER.md`，然後做 UI/UX 體檢。使用者的實際感受是
**「東西太多、太像玩具」**，逐條拆解後根因只有一個：
**v1 的 UI 是按引擎的結構長出來的，不是按使用者的工作流程長出來的。**

### 已完成：A 組（新手第一分鐘會撞到的四件事）+ UI 全英文

- **A1 動作可用性**：前置條件不滿足的按鈕改成**變灰 + tooltip 說明原因**。
  舊行為是全部亮著、按下去才在狀態列抱怨 —— 狀態列在螢幕最下角，
  第一次用的人只會覺得「我按了，沒反應」。新增 `_update_action_states()` 單一決策點。
- **A2 游標讀數搬家**：`ImageView.cursor_info` 原本直接接到狀態列，
  滑鼠飄過影像就把「試跑完成：100 顆…」洗掉。改成預覽區自己的標籤，
  狀態列只留事件訊息。
- **A3 工具列去重**：「載入範本（die-to-die）」與「範例 recipe」做的是同一件事
  （都在載 `examples/recipes/` 的 JSON），且 die-to-die 對目標使用者是行話。
  合併成單一入口「Templates…」。
- **A4 主要動作只留一顆**：「全跑」收進「▶ Run trial」的下拉。
  試跑筆數改成跟著資料集走（24 顆的 lot 不再顯示「First 200」）。
- **UI 全英文**：使用者原話「中英夾雜很混亂」。工具列、面板、對話框、
  卡片 label/help、ParamSpec help、參數與 recipe 驗證錯誤、score 表達式錯誤、
  KLARF 寫回計畫書、CSV/Excel 報表標題全部英文化。
  **docstring 與註解維持中文** —— 那是開發文件，是這個 repo 刻意累積的資產。
  新增 `tests/test_ui_english_only.py` 走 AST 把不變量鎖住（只管字串常數，
  docstring 節點跳過）；`__main__.py`（CLI 是另一個介面層）與 vendored 的
  `klarf_core.py` 列在 PENDING 並註明理由，另有一個測試防止清單發霉。

595 tests 綠。

### 討論定案：F7（見 `docs/plans/F7-canvas-and-taxonomy.md`）

三輪來回之後定下的方向：

- **patch-only 收斂**（RSEM 先關掉但**不刪 code**）。刪掉等於丟掉整個 M4；
  而且 `algo/period.py` 的相位搜尋是之後做 pattern-frame ROI 的唯一工具。
- **卡片改依流程階段分類**：Input → Enhance → Region → Compare → Measure → ADC → Output，
  每段附一條型別規則（吃什麼、吐什麼），新卡片放哪不用討論。
  舊的「影像／算法」分的是**輸出型別**，不是**使用者意圖** —— 那是「太武斷」的根因。
- **ROI 升成一級概念**。查證後發現 `Context.rois` / `Context.labels` 與
  `algo/roi.py` 的 `NamedROI` / `MultiROISet` **早就存在但從來沒有人寫過**
  （`context.py:33` 的註解寫著「M3 起由 ROI 卡填入」，那張卡沒做出來）。
  ROI 現在是散在各量測卡裡的 `region=` / `box_size` 參數，正是 CLAUDE.md §7
  那個「中心框幾何與影像尺寸綁死」的坑。
- **但 Region 段先不照搬**：使用者指出機台的裁切是「以 defect 為正中心裁 x×x」，
  所以 patch 裡有兩個座標系 —— **defect frame**（中心固定，穩定）與
  **pattern frame**（晶格相位逐顆不同，不穩定）。v1 只做 defect frame 的 ROI。
- **Align 降級**：使用者的領域知識 —— 機台輸出的 patch 兩兩對應本來就是
  defect & reference，不需要對位。卡片保留但不進預設範本。
  驗證方法已記在計畫書：`align_dx` / `align_dy` / `align_score` 都是 feature，
  拿真實 lot 跑一次看 CSV 的分佈就知道。
- **視覺目標是 n8n / KLIP 的語言**（中性灰、全平面、顏色只表達語意）。
  現在的暖奶油 + 琥珀是 vendoring 自 CPE 的；使用者自己的 KLIP 已經是想要的風格。
- **Output 是固定尾節點但底下仍是 Export 精靈** —— ADC 是 per-defect、
  Export 是 per-batch，不該真的變成流程節點。

### 下一步

F7-1 patch-only 收斂 → F7-2 主題換色 → F7-3 卡片分類 → F7-4 Region 段 +
量測卡遷移（破壞性 schema）→ F7-5 Results 視窗 → F7-6 畫布。

`fab_probe/` 的三個原始假設仍然全部未驗證，優先度不因這次重構而降低。

### F7-1 patch-only 收斂（603 tests）

新增 `adept/ui/scope.py` —— **一個檔案就是整個開關**：

```python
SUPPORTED_KINDS = ("ebi_patch",)                 # 加 "rsem" 就整條路線回來
HIDDEN_STEPS = ("golden_cell", "cell_period")    # 清空就出現在卡片庫
```

GUI 側的三個切點：
- 卡片庫過濾（17 列 → 15 列，掉的正好是最難懂的兩張）
- 載到 rsem 資料集 → **擋下並講清楚原因 + 給替代路徑**（CLI 仍跑得動），
  而且**不動既有狀態** —— 開錯一個檔不會把使用者正在調的東西弄丟
- 範本庫過濾：判準是「至少有一條看得懂的 route」而不是「只有看得懂的 route」，
  所以 `dual_route_basic` 照列（載進來走 ebi_patch），只有純 rsem 的被收起來

`tests/test_ui_patch_only.py` 鎖兩件事，第二件才是重點：
1. GUI 真的收斂了
2. **core 一行都沒少**，而且「打開開關就回得來」是有測試保護的事實 ——
   那支測試會 monkeypatch 兩個常數再驗一次整條 RSEM 路線

裡面有一條 `test_period_module_is_not_orphaned`，作用是一張便利貼：
`algo/period.py` 現在只被 Golden Cell 用到，看起來像可以陪葬，
但它是之後做 pattern-frame ROI 的唯一工具。

順手補完英文化漏掉的東西：**9 處全形標點**（`、`、`：`、全形空白 `　`）。
`_has_cjk` 已擴到涵蓋 CJK 標點與全形 ASCII 變體 —— 標點是翻譯時最容易漏的。

### F7-2 主題換色 + 平面化（607 tests）

`TOKENS` 的**鍵名一個都沒改**，只換值 —— 所有顏色本來就集中在這裡
（同時餵 QSS 與自繪 widget），所以換膚零呼叫端改動。
暖奶油 `#f7f4ef` + 琥珀 `#f29f4b` + 填滿色塊 → 中性灰 + 克制的藍 + 細色條。
新增 `PALETTES` 的 light/dark 兩組（鍵名逐一比對），`set_theme` **就地更新**
`TOKENS`（不能換掉物件，各模組都 import 過它了）。工具列一顆 `◐` 切換，
偏好存 QSettings。

三個舊測試把暖色 hex 寫死了，改成斷言**性質**：大面積底色中性（RGB 極差 ≤ 8）、
QSS 無陰影無漸層、雙色盤鍵名一致、`set_theme` 就地且可逆。這樣微調配色不會一直打壞測試。

### F7-3 卡片分類重整（611 tests）

`Step` 新增 `group`（與 `category` **獨立的軸**）：
`category` 是引擎用的（快取切點、驗證順序），`group` 是使用者用的（卡片庫分組）。
舊 UI 直接拿 category 當分類，於是使用者看到「影像／算法」—— 那描述輸出型別，
不是意圖，這就是「太武斷」的根因。

新分段：**Input → Enhance → Region → Compare → Measure → ADC**，
每段附一條機械可判定的規則（吃什麼、吐什麼）寫在 `step.py` 的常數旁邊。
`resolve_group()` 有依 category 的 fallback（外掛卡不會壞），但另一支測試要求
**本 repo 內建的卡片一律明講** —— 否則新加的量測卡會安靜地掉進 Enhance。

另外兩件讓 15 列不再瑣碎的事：搜尋框（比對名稱/key/說明/group）、
前置條件 badge（`needs diff`，調淡但**仍可加入** —— 卡片庫順序不是執行順序）。
區塊標題從填滿色塊改成 **QPainter 畫的 icon + 標題**（不加任何圖檔，
顏色吃 token 所以跟著換膚）。

踩到一個坑：`isVisible()` 在視窗 `show()` 之前一律是 False，
headless 測試會全部誤判 —— 可見性與 badge 一律改用明確狀態。

### F7-4 Region 段 + 量測卡遷移（623 tests，破壞性 schema）

**ROI 從「藏在量測卡裡的參數」升成一級概念。**
`Context.rois` / `algo/roi.py` 的 `NamedROI`/`MultiROISet` 從 M0 就存在、
但從來沒有人寫過（`context.py:33` 註解寫著「M3 起由 ROI 卡填入」，那張卡沒做出來）。
現在 `Context` 包了一層**以名字為鍵**的 API（`set_roi`/`require_roi`/`roi_rect`），
底層仍用 MultiROISet 的 `label`，不另外發明資料結構。

- 新卡 `roi_define`：`shape=center|whole`、`size` + **`size_unit=px|percent`**
- `blob_segment` 的主 blob 也發布成具名 ROI（預設 `blob`）——
  偵測出來的框與手畫的框走同一條路，這是最關鍵的一刀
- `glv_stats`：`region`/`box_size` → `roi=<名字>`
- `roi_snr`：`mode`/`box_size` → `roi=<名字>`
- `cd_measure`：新增 `roi`（預設 `blob`）
- 5 份範例 recipe 自動遷移（插入 `roi_define` 節點）

**`percent` 修掉 CLAUDE.md §7 那個坑**：同一份 recipe 在 128² 與 256² 上
看的是同一塊相對區域（`(48,48,32,32)` vs `(96,96,64,64)`）。

驗收：`die_to_die_basic` 跑 100 顆合成 patch，分數分佈與重構前**逐項相同**
（min 21 / median 45 / max 171、bin 0=52 · bin 1=48），對照 ground truth 98%。
行為完全保持。

`roi='blob'` 存的是像素座標，所以**不需要影像**就取得到 —— 下游把影像流蓋掉
之後 CD 還是量得到（有測試鎖）。

### F7-5 Results 視窗（632 tests）

主視窗一直是四區塊 + 底部全寬直方圖，「編流程」與「看整批」擠在同一個畫面。
拆的界線是「這個東西要不要先跑過一批才有意義」：

- 主視窗 Workspace：編流程 · 看單顆 · 調參數（三欄，**預覽拿最寬的一欄**）
- Results 視窗：分數分佈 · Gallery · 輸出

`ResultsWindow` 沿用 `WelcomeDialog` 的慣例（自己不驅動任何東西，只發訊號）。
非 modal，關掉不丟結果。

**這個改動最容易弄壞的東西已經用測試鎖住**：拖門檻線仍然走
`viewmodel.rebin()` 的純計算路徑（拖曳中不寫 model、放開才 commit）。
那是調參迴圈一半的價值，換視窗時最容易被接成「每動一次就重跑」。

兩個測試環境的坑：`QSplitter.sizes()` 在視窗 show 之前沒有意義（欄寬測試改斷言
設定常數 `COLUMN_SIZES`）；`_maybe_request_thumbs` 對相同可視範圍會提早 return，
而這批全部塞得進畫面 —— 縮圖測試要重置那個備忘，不是硬去改視窗大小。

### F7-6 節點畫布（643 tests）

`core` 從 F0 起就是 DAG（`Recipe.edges`、Kahn 拓撲排序 + 循環偵測都在），
當初就寫著「之後上自由畫布時引擎零改動」——**這次證實了**：
`adept/ui/canvas.py` 是純 UI，core 一行沒動。

- `RecipeModel` 新增 `edges`；`node_order` 改由拓撲排序算出（同層維持原相對順序，
  拉一條線不該讓別的節點亂跳）
- `PipelineCanvas` 的公開 API 與訊號**刻意與舊的 `PipelinePanel` 對齊**，
  所以 Studio 的接線幾乎沒動 —— 換 UI 不要順便變成重寫主視窗
- **循環擋在 `add_edge`**：會成環的線直接回 False 不落地。
  使用者看到「這條線拉不起來」，而不是「拉起來之後跑的時候才爆」
- 排版是自動的（拓撲深度分欄）。位置**不寫進 recipe** ——
  為了存座標而改 JSON 格式會讓每份既有 recipe 都要遷移，代價和收益不成比例

M7 至此完成。643 tests 綠。

### CI 修正：`pytest` vs `python -m pytest`（643 tests）

PR #1 開起來之後 CI 三個 job 全紅，錯誤是 `ModuleNotFoundError: No module named 'adept'`
—— **收集階段就中斷，一個測試都沒真的跑到**。

根因與這次的改動無關，是 pre-existing：

| 指令 | CWD 進 `sys.path` 嗎 | 結果 |
|---|---|---|
| `python -m pytest -q` | 會 | 找得到 adept ✓ |
| `pytest -q` | **不會** | ModuleNotFoundError ✗ |

CI（`.github/workflows/ci.yml`）跑的是後者，本機開發（以及這整個 session）用的是前者，
所以這件事從 CI 加進來（commit `de387c5`）之後一直沒被發現。

修法：新增根目錄 `conftest.py`（pytest 載入 conftest 時會把它所在的目錄插進
`sys.path`），裡面再明確補一次 repo 根與 `tools/`，讓意圖看得出來、
也不依賴 pytest 的 import-mode 細節。

**沒有選 `pip install -e .`** 的理由：廠內機器是解壓 zip 直接跑
（見 `docs/NO-GIT-SETUP.md`），「從 repo 根目錄直接跑得動」是這個專案要維持的性質。

修好之後 CI 終於跑到底，露出第二個問題：**636 passed, 6 skipped, 1 failed** ——
workflow 手寫的 pip 清單漏了 `openpyxl`（它在 `pyproject.toml` 與 `requirements.txt`
都是硬相依）。三支 Excel 報表測試用 `pytest.importorskip` 安靜跳過，
所以這個缺口一直藏著，直到有一支測試真的斷言匯出要成功才爆出來。

除了補上套件，workflow 多一步：裝完之後逐項確認 `requirements.txt` 的東西
都 import 得到，漏了就指名報錯。安裝清單不能直接寫 `-r requirements.txt`，
因為 CI 刻意把 `opencv-python` 換成 headless 版 —— 而那種「刻意的分歧」正是
會安靜漂移的東西，所以用測試守住而不是靠人記得。

結果：3.9 / 3.11 / 3.12 三個 job 全綠，**643 passed、零 skip**。
註腳：在此之前所有「N tests 綠」都只在 `python -m pytest` 下成立；現在兩種都成立。

驗證方式也記一下：本機 PATH 上第一個 `pytest` 是 uv 裝的獨立工具（自己的 venv、
沒有 numpy），跟 CI 的情況不同 —— 要用與 `python -m` 同一個直譯器的那支
（`/usr/local/bin/pytest`）才驗得準。加了 conftest 前後各跑一次確認因果。

### F7-7 / F7-8：試用回饋兩輪（679 tests 綠）

使用者實際開起來用之後提的事情，分兩批做完。

#### F7-8 之一：數字參數配滑桿 + 自訂色調曲線

> 「調亮度 對比可以放在一起，然後是用搖桿調整（不是輸入），同理 gamma 也是。
> 然後下方要支援 custom curve 可以自己畫 gamma 曲線（預設 y=x）」

滑桿是**資料驅動**的：ParamSpec 有 `min`/`max` 就自動配一支，沒有就不配。
新卡片把上下界填好（本來就是鐵則 4 的要求）就自動有滑桿，UI 零登記。
數字框刻意留著 —— 滑桿負責「找到大概的位置」，數字框負責「記錄與重現」，
recipe 是要交接給別人的。

曲線存成字串（`"0,0; 0.35,0.6; 1,1"`）：ParamSpec 的值一律是純量，
UI 表單 / rescore / CLI `--set` 全靠這條規則；而且 recipe 的 git diff
仍然一眼看得出「使用者把暗部拉起來了」。

**插值用保單調三次 Hermite（Fritsch–Carlson），不是自然三次樣條。**
自然樣條會 overshoot —— 使用者把中間點往上拉，曲線在旁邊先往下凹一段，
影像上就是一圈**演算法自己造出來的暗環**。對一個要拿去判 defect 的工具來說，
那是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住。
沒有引進 scipy（廠內離線機，相依愈少愈好）。

曲線與 gamma 是**接手**不是疊加：疊加的話「我把曲線拉平了怎麼還是暗」
會非常難 debug。UI 因此在曲線生效時把 gamma 那列**調淡並說明原因** ——
但不 disable，使用者可能只是想比較兩種做法。

編輯器畫的線就是影像上套的線（同一個 `algo.curve.curve_lut`）。
UI 自己再實作一份插值太容易發生，那會讓看到的和跑出來的不一樣。

#### F7-8 之二：畫布殘影、成對的線、並排看兩張圖

殘影的原因是 `boundingRect()` 沒涵蓋畫在節點右緣**之外**的埠標籤 ——
Qt 只重繪你宣告的範圍。已記進 CLAUDE.md §7。

Input → Subtract 現在畫**兩條**線（test 一條、ref 一條）。這是從兩端共用的
影像流**推導**出來的，不是存起來的：recipe JSON 的 edge 仍然是 `[from, to]`，
格式不用改，重新載入不掉資訊。

**並排比對預設關著。** 使用者問「還是你覺得秀一張比較好」——
F7-5 把 Gallery 與直方圖搬走就是為了讓右欄的影像變大（原話「影像最好大一點」），
預設並排等於把剛爭取到的寬度再砍一半。真正需要並排的時機很明確：
**調 Enhance 卡的時候**，確認 test 與 ref 被調成一樣的。那是一次點擊。
開了之後兩張圖的縮放與平移**連動** —— 沒有連動的並排，使用者得自己把兩邊
拖到同一個位置才比得起來，那還不如切換一張。

#### F7-8 之三、四、五：直式 rail、Normalize、畫布視覺

左側六個階段的大 icon 由上而下排成一條工作列；卡片區收起來時整欄只剩 rail，
寬度真的還給工作區。**搜尋框住在卡片區裡**，所以 rail 底部必須留一顆放大鏡 ——
不然卡片區收起來之後搜尋就再也叫不出來了（差點漏掉這件事）。

Normalise → Normalize，三張卡改成共同前綴（`Normalize · Percentile` / `· GLV band`
/ `· Histogram match`），在清單裡自然排在一起。

畫布視覺：n8n 之所以一眼認得出來，靠的是**左邊那顆有顏色的圖示磚**，
不是細色條 —— 細條太安靜，遠看還是一排一模一樣的方框。所以加了圖示磚
（淡色底 + 與 rail 完全相同的圖形）、投影、**點陣底而不是格線底**
（格線跟連線同一種筆觸，「哪條是資料流」要看第二眼）、連線中點的方向箭頭、
停用節點畫虛線框。過長的文字一律 elide —— 硬切在字中間的
`source=diff · metri` 會讓人以為參數值真的是那樣。

#### 一個自己造的坑

`s.replace('self._scroll = QScrollArea(self)', ...)` 沒有加錨點，
把 `LibraryPanel` 以外的兩個類別（`ParamForm`、`PipelinePanel`）一起改了。
全域字串取代改 Python 原始碼要先確認那行字在檔案裡是唯一的。

計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §12。

---

## F7-9 —— 試用回饋第三輪（2026-07-29）

使用者提的四件事 + 一個提問。最後那句話才是真正的目標：
**「希望兩張 patch 可以一起，或經過不同的工作流做設定」**。
前四件事看起來各自是小毛病，但都指向同一個缺口 ——
**「影像流」這個概念在畫面上幾乎是隱形的**，而「兩張要一起還是分開」
正好是一件純粹關於影像流的事。

### 1. 六個階段六個顏色

以前是 `group → category → 顏色`，category 只有三個，所以六個階段三種色
（Input／Enhance／Compare 全是藍的）。圖示分得出來、顏色分不出來。
新的 `theme.group_hex()` 每階段一個色相，挑色條件是**可驗證的性質**：
兩兩 CIE Lab ΔE ≥ 25（看得出是兩個顏色，不是同色深淺）、
同主題內明度 L\* 差 ≤ 15（像一套色票）。兩條都有測試鎖，色碼還可以再調。
`seg_hex()` 沒被取代 —— 需要講「這是哪一段」的地方仍然用它。

### 2. 一個 bug，兩個症狀

「移動 Load images 有殘點」與「新增的節點只有前面有圓框、後面沒有」
**是同一個 bug**：`paint()` 拿場景座標去畫本地座標的東西。
節點在原點時看起來正常 —— 而第一欄的 Input 剛好在原點，所以症狀才會長成
「Load 有埠，後面的卡沒有」。

F7-8 修過一次殘影，改的是 `boundingRect` 的大小。那是對症狀動刀，所以它又回來了。
真正的不變量是**畫的座標系＝宣告的座標系**：現在分成 `out_anchors_local()`
（繪製、命中判定）與 `out_anchors()`（連線），測試直接鎖「拖到哪裡，
每個埠與標籤都要在 `boundingRect` 裡」。

順手：輸入埠空心、輸出埠實心；**每個輸出埠都標上流名**（以前只有多埠才標）。

### 3. 起手卡

空白畫布對不會寫 code 的人是一道關卡，而答案永遠是同一個。
`RecipeModel.starter()` 開窗就放好 Input 卡並選起來，`dirty=False`
（什麼都還沒做，不該被問「要存檔嗎」）。

### 3b. 還沒拉線的畫布會換行

截圖檢查時發現的（不在回饋清單上）：九張還沒拉線的卡排成一列超過 2500px，
`fit()` 只能縮到看不出字 —— 而它有下限，所以結果是「一排讀不出來的小方塊
**加上** 一條捲軸」，兩邊都輸。退化排版現在每 4 張換一行。

### 4. target / also apply

提問本身就是答案：使用者在畫布上想的是**節點**，這兩個參數講的是**影像流** ——
流是節點之間的**線**。以前畫面上沒有任何東西說出這件事。
所以：`ParamSpec.label`（顯示名，`name` 仍是 JSON 的鍵）、
新型別 `image_keys`（值的格式沒變、舊 recipe 照讀，但 UI 給勾選框）、
說明改寫成「流就是畫布上那些有名字的線」、每個輸出埠標上流名。

於是使用者要的那件事變成一個看得見的動作：
**ref 勾著＝兩張一起；取消＝分開**。

### 5. 點卡片跳到 ref

`_default_stream()` 取「這張卡寫過的最後一條流」，而 Enhance 卡的 writes 是
`[target] + also_apply` —— 最後一項永遠是 `ref`。改成先看主要參數
（`target`/`source`）。另外加一條保險：左右算出同一條流時右邊讓步 ——
兩張一模一樣的圖是並排唯一沒有意義的狀態。

### 6. 卡片組合的稽核（使用者的提問）

把 19 張卡的 reads/writes/features/具名區域全部攤開跑過，兩個真的會咬到：

- **具名 ROI 完全沒被檢查。** 影像流有 reads/writes 可以在 `validate()` 裡模擬，
  ROI 沒有。`cd_measure` 預設 `roi="blob"`，少了上游 Blob 卡就**安靜地改量整張
  圖** —— 跑得完、有數字、而且是錯的。這是最糟的一種：看不出哪裡不對。
  修法是讓區域走同一條路（`resolve_regions_in/out` + `unknown-region`），
  退回整張圖時 `ctx.warn`。
- **Studio 從來沒跑過 lint。** 同一份檢查 CLI 從 M1 就在用。加上「單顆出錯不殺
  整批」的契約，接錯的卡片會**跑完 200 顆、每顆都失敗**。現在試跑前先 lint。

**沒有動 `subtract` 的預設值**（它吃 `ref_aligned`，所以 Load 之後直接放
Subtract 一定缺上游）。改成 `ref` 會讓它立刻能跑，但接著會產生一個更難發現的
反向陷阱：加了 Align 卻沒重新接線 → **安靜地減掉沒對位的 ref**。
用一個看得見的錯誤換一個看不見的錯誤，不划算。改成在加卡片時把話講完：
「還缺 ref_aligned（先加 Align），或指到現有的 test / ref」。

### 7. 一個順手清掉的地雷

`test_no_qt_after_import` 以前在測試行程裡看 `sys.modules`，所以它**跟檔名的
字母序有關** —— 新增一支排在它前面的 UI 測試檔就會誤報，而訊息指不到真正的
原因。改成在乾淨的子行程裡 import core 再問。

計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §13。測試：`tests/test_ui_f7_9_feedback.py`。

### 8. 卡片組合稽核挖出的兩個 bug（同一個 session）

**快取只存了 Context 的一部分。** checkpoint 是執行順序上的**位置**（最後一張
影像段卡的下一格），不是「所有影像段的卡」，所以「載入 → 先框出要看的地方 →
再做影像處理 → 量測」這個**很自然**的順序，會把 Region 卡（algo）夾進快取段。
v1 快照只存 images/features/meta，`ctx.rois` 沒存 —— 於是**第一次跑對、第二次
跑錯**（`region 'main' is not defined`）。先寫出重現再修。快照現在涵蓋 rois 與
labels，並帶 `FORMAT_VERSION`：版本不合當 miss，既有快取目錄不會把殘缺快照
餵回來。迴歸測試刻意先斷言「checkpoint 真的吞掉了那張 Region 卡」，
免得哪天切點改了、測試還在綠但已經沒測到那條路。

**特徵是扁平的全域命名空間。** 兩張同型別的量測卡寫同一組名字，
所以「量中心 + 量整片」這個一定會做的事，跑完只剩後面那張的值，
而且前面那個**完全沒有辦法**從分數表達式指到。lint 以前說這份 recipe 是乾淨的。
現在是 `feature-collision` warning，Studio 跑完在狀態列講出來（跑之前講會被
「Running: 3 / 200」洗掉）。不擋執行 —— 同名覆寫有時是刻意的。
根治要讓量測卡能自訂輸出名，那件事跟 ROI 段一起做。

---

## F7-10 —— 隱含順序 + Enhance 空間性 artifact（2026-07-29）

### 1. 畫布上「沒有線」不代表「沒有連接」

引擎的依賴從 M1 起就是「route 相鄰對 ∪ 顯式 edges」，但畫布只畫後者。
載入沒拉過線的 recipe 看到的是九張互不相干的卡，而它其實照順序在跑。
現在 route 相鄰對畫成虛線、半透明、**不可選取**（刪掉它等於「把卡片從流程裡
拿掉」，那是另一個動作）。使用者親手連同一對時換成實線，不會變兩條。

副作用：每份 recipe 現在都有依賴，所以 F7-9 只做在退化排版上的換行要對深度排版
也成立 —— 不然九張卡又排成一條 2500px 的橫列。

### 2. Enhance：六項能力，兩張新卡

使用者的要求是「不要開太多卡片，類似的放一起」。所以：
`flatten`（背景／條紋／top-hat／black-hat 五個方法一張卡）、
`local_contrast`（CLAHE，掛進既有的 `Normalize ·` 家族）；
邊緣保留去噪塞進既有 `denoise` 的 method 下拉；
雙流運算塞進既有 `subtract` 的 op 下拉。19 → 21 張卡。

`flatten` 的五個方法看起來是五種東西，其實是同一個結構：估一個大尺度成分再減掉，
差別只在怎麼估。這種時候就是同一張卡的一個下拉。

**兩個實作決定值得記：**

去條紋用**中位數**不用平均 —— 一顆夠大的缺陷會把該列平均帶偏，校正時就在缺陷
那一列造出反向假條紋。演算法自己造缺陷，跟 F7-8 的曲線 overshoot 同一類。

保留邊緣的去噪，強度以**這張圖自己的雜訊 σ** 為單位（Immerkær 估計），不是灰階
常數。給常數的話換台機台就不對，而使用者只會覺得是自己參數調錯。實測 h≈1σ 雜訊
掉九成、3×3 缺陷完好；2σ 起缺陷開始消失，所以預設停在 1。

加 bilateral/nlm 的唯一理由是 median 對「比核心小的亮點」是毀滅性的 —— 而那正好
是要找的東西。測試拿 median 當對照：同一顆缺陷 median(5) 從 46 抹到 5，
bilateral 與 nlm 都留在 46 以上。

計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §14。

---

## F7-11 —— ROI 定位第一批（2026-07-29）

### 起點：一個把我原本設計推翻的領域事實

patch 是 EBI 機台以缺陷位置為正中心裁出來的，所以**缺陷永遠在中央**；
而 EBI 的檢測本來就鎖定在某一種 pattern 上，所以**每張 patch 裡一定有那個結構**。
但缺陷可能落在結構中間、也可能靠邊 —— **結構在 patch 裡的位置逐顆不同**。

所以「中心固定框一定準」只對了一半：缺陷本身在中央沒錯，但缺陷**周圍**的東西
每張都不一樣。框只要大過缺陷就可能吃進別種材質，數字忽高忽低，而變動的原因
不是缺陷。拿來當背景的區域更糟。

問題因此不是「把框放在畫面的哪裡」，是**「把框放在結構的哪裡」**。

### 做了什麼

1. **量測卡自訂輸出名**（`output_prefix`，前置）。沒有它，兩張量測卡的特徵會
   互相蓋掉，多區域整件事不成立。Studio 在使用者挑了區域之後**自動填成區域的
   名字** —— 命名空間是工具的問題，不是製程工程師該懂的事。只在空著時填。
   順帶給 `ParamSpec` 加了 `pattern`，把「不能當變數名的前綴」擋在驗證層。
2. **投影定位卡** `roi_profile`：把影像壓成曲線 → 找轉折 → 挑一段當具名區域，
   可以一次吐出選中的那段與左右鄰段（訊號要跟**同一種材質**的背景比才有意義）。
3. **曲線面板**：曲線、轉折線、選中的段、中心線、信心值。

### 幾個想清楚才寫下去的決定

**找轉折，不分材質。** 第一版想「EPI 暗、MG 中、交界最亮 → 分三種灰階」，
被使用者一句話擋掉：這個工具是泛用的，之後的資料不會只有這幾種 layout。
分材質要先知道有幾種、每種多亮，而灰階會隨機台漂移 —— 等於把 recipe 綁死在
一種 layout 上。找轉折只問「哪裡在變」，使用者只要回答「我要哪一段」。

**在 ref 上找，不在 test 上。** test 上有一顆缺陷正在破壞結構。

**定不出來就講出來。** 整張同一種材質的 patch 不可能定位 —— 那是資訊不夠，
不是演算法不夠。但它也不需要定位（整張量就是對的）。所以退回整張圖並標記
`locate_ok=0`，讓使用者事後分得清哪些顆是定位過的。

**信心的分母要用 MAD 不是標準差。** 銳利的邊界會讓平滑吃掉一點真訊號，
用標準差當分母會變成「結構越清楚、信心越低」，完全相反。
實測：均勻約 0.7，有結構的都在 20 以上。

**固定斜率的漸層要擋掉。** 每一格梯度都相等，不防的話浮點誤差決定邊界畫在哪，
而且每格都被判成邊界。要求最陡處至少比一般處陡 1.2 倍
（漸層 1.00、正弦 1.41、方波極大）。

**面板畫的是引擎算的那一份**（走 `ctx.meta["profiles"]`），UI 不自己再算 ——
不然「畫面上的框」跟「真的量下去的框」有機會不一樣。

### 面板揭出來的一個舊 bug

`PreviewWorker` 只合併「還沒開跑」的請求；已經在跑的那筆照樣會發 ready。
所以「先送背景預覽、接著跑同步預覽」時舊的那筆會**後到**，把新畫面蓋掉，
而且不會再更新。以前的症狀是「影像閃一下」，不容易歸因；曲線面板讓它變成
「面板整個空白」才浮出來。修法：預覽加世代編號，過期的整筆丟掉。

計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §15。
下一批：Golden Cell 模板比對（零件 period/golden/align 都已在 repo）。

### F7-11 第三批：區域跨顆檢視

區域設定對不對是一個**關於整批**的問題 —— 在第 1 顆剛好的框，第 50 顆可能整個
偏掉，而看單顆永遠看不出來。所以 Region 卡旁邊多了一顆按鈕，把區域畫到前 N 顆
的縮圖上一次看完，失敗的用外框標出來，並且可以**只看失敗的**（那些才是要看的：
可能本來就沒結構可認，也可能是參數太緊，只有看圖分得出來）。

按鈕對**任何**會定義區域的卡片都出現，不是只給投影定位卡。

一個容易腐爛的地方先鎖起來：縮圖的 letterbox 偏移 (`thumb_placement`) 與
`make_thumb` 放在同一個檔案，而且測試拿兩者對照 —— 分開放的話，改了縮圖的縮放
規則而忘了改另一邊，框會整批偏掉，但畫面上只看得出「框好像有點歪」。

---

## F7-12 —— Golden Cell 模板定位（ROI 定位第二批）（2026-07-29）

投影定位只看 patch 自己，patch 裡沒地標就定不出來 —— 而 patch **普遍小於一個
重複單元**，那不是例外是常態。這一輪補上另一條路：把資訊從外面帶進來。

### 使用者自己提出的解法（而且是對的）

「patch 比 cell 小，對得起來嗎？」→「匯入一張原大圖，用 cell period 疊出 Golden
Cell 當模板。」

對的，理由值得記：**模板法不是把兩張小 patch 互相對位，是把一張小 patch 滑進一
張大模板。** 小的那張只要比雜訊多一點結構就有唯一解；patch 小於 cell 反而有利。

前提是大圖拿得到 —— 使用者確認 patch 就是從大圖裁的（同 rcp、同 beam、像素尺寸
一樣）、大圖每次掃描都有、而 GC **可以跨 lot 共用**（同一支 rcp 掃同一塊 scan
area）。所以模板**凍進 recipe**（base64 純文字），不是存路徑：存路徑的話圖被搬
走或換掉，結果會安靜地變，而 recipe 是要交接給別人的東西。

### 我講錯的一件事

我說過「有了大圖，非週期 layout 也能定位」。使用者擋掉：**知道 patch 在大圖的
哪裡，不等於知道要量哪一塊。** 非週期 layout 沒有「標一次就套用到所有地方」的
單元，那是 GDS 的事。GC 法的前提是 layout 有週期 —— 這句寫進卡片 help。

### 做了什麼

- `core/algo/template.py`：`build_golden_cell` / `anchor_cell` / `match_patch` /
  `roi_in_patch` / `encode_cell` / `decode_cell`。
- `core/steps/roi_template.py`：新卡 **Locate region by template**（Region 段），
  吐 `match_score` / `match_margin` / `match_structure` / `phase_x` / `phase_y` /
  `locate_ok`，定不出來退回整張圖 —— 跟投影定位同一個約定。
- `ui/template_dialog.py`：匯入大圖 → 量週期 → 疊模板 → 看證據 → 寫進 recipe。
- 測試：`tests/test_roi_template.py`（25）＋`tests/test_ui_f7_12_template.py`（11）。

### 三道閘門，因為分數本身會騙人

比對用 NCC（對亮度／增益免疫，換機台不必重調），但分數單獨看不可信：

1. **一維 layout 不要在另一軸上搜尋** —— 峰的突出程度會被稀釋，「定得出來」被判
   成「定不出來」。`locate_axis` 讓不重複的那一軸整段吃掉。
2. **margin 要折回一個週期再算** —— 不折的話相鄰週期的次高峰讓 margin 恆為 0，
   週期性把自己打敗了。
3. **先問 patch 自己有沒有東西可比**（`min_structure`）—— 純雜訊對任何模板都能
   拿到 0.44（門檻 0.3 → 過關）。**沒有任何分數門檻分得出「對得準」與「碰巧」**，
   因為兩者分數重疊；要問的是另一個問題。實測無結構約 1、有結構 20 以上，
   20 顆無結構 patch 全數擋下。

### 原點必須錨在地標上

疊出來的 cell 第 0 欄預設是大圖上的任意切點；切點一飄，同一份 recipe 在不同時間
建的模板會指到不同的地方，而且畫面上看不出來。`anchor_cell()` 旋轉到**最強的
上升邊**在第 0 欄 —— 用最大正梯度而不是 `abs`，否則一個週期的兩個相反邊界會
競爭，錨點在兩者之間跳。三個 seed、三個切點鎖進測試。

### 兩個順帶擋掉的安靜失敗

- 一維 layout（垂直條紋）以前在 `py` 量不到週期時直接放棄 —— 而那是最常見的情況。
  現在兩軸各自判斷，不重複的那一軸取整個影像高度／寬度。
- 純雜訊上 `estimate_period` 會回一個**看似合理**的週期（實測 py=48、信心 20.3）。
  信心門檻拉到 40 ——「疊出一個沒有意義的模板」比「說我做不到」糟得多。

### 對話框把判斷材料全部攤開

整條路唯一會**安靜壞掉**的地方是週期估錯：估錯 → 模板糊 → 每顆都對錯 → 畫面上
沒有錯誤訊息，只有一批看起來很正常、其實量錯位置的數字。所以對話框顯示週期、
疊了幾格、疊出來長什麼樣、銳利度分數，而且糊掉時**用白話再講一次**後果。

計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §16。

### 還沒做（下一批）

**用當次掃描的大圖對凍在 recipe 裡的 GC 做健檢。** 跨 lot 共用的前提是圖案沒變，
這個前提會失效（rcp 改過、換 scan area、機台調整），而失效時同樣是安靜的。
零件都在（`build_golden_cell` + NCC），缺的是 Studio 的一個入口。

---

## F7-13 —— 控制項要看得出自己是什麼（試用回饋第四輪 A 組）（2026-07-29）

使用者看了跑起來的畫面：「我先打磨 UI，你覺得目前 UI 有什麼需要改進的？」
我列了三類，這一輪做的是**不是品味問題**的那一類 —— 三個症狀來自同一種毛病：
**控制項長得不像它自己**。功能測試抓不到，因為每一項功能都是好的。

### 1. 下拉選單長得像文字框（0 個畫素的箭頭）

`Match on`（擇一）跟 `Name this region`（自由文字）在畫面上一模一樣。
兇手是一行 QSS：`QComboBox::drop-down { border: 0; ... }` —— styled 的 subcontrol
要自己提供 down-arrow 圖檔，否則箭頭**完全不畫**，而這個 repo 是純文字的。
拿掉 `border: 0` 讓它留在 base style 上。

量出來的證據：修之前箭頭區 **0** 個非底色畫素，修之後 20 個，同尺寸的 QLineEdit
仍然是 0。淺色深色各鎖一次。

### 2. 模板參數不再是文字框

值有六千多個字元、而且是一張影像的內容。文字框讓它「看起來只是還沒填」、
填了之後變成一片 base64、而且可以被改。新增參數型別 `template`：
**按鈕就在這一列** + 一行摘要，值唯讀。

按鈕從預覽面板搬回參數列 —— 它是那個參數的值從哪來，不是預覽動作。
摘要是 `decode_cell` 解出來的，不是另存一個欄位（存旁邊會跟值走散，而走散時
畫面上完全正常）。

順帶：節點第三行的參數摘要會把模板串成 `template=gc1:iVBOR…`，現在只講
`template: set`。

### 3. 「這張卡還不能跑」現在看得見

**參數合法 ≠ 設定完成。** 空模板是合法的 str，所以誰都沒話說 —— 但那張卡跑起來
每一顆都失敗，而使用者是跑完 200 顆才知道的。

新增 `Step.configuration_issues(params)`：卡片自己講缺什麼，而且用**這張卡的話**
講（要去按哪一顆鈕）。變成 lint error `not-configured`，畫布上的卡片右上角掛
警示標記，滑鼠停上去講原因。

既有的「每張卡都要有可行組合」測試因此出現一個新分類：路是通的，只是還沒設定完
—— 不算死路，但**訊息必須指得出路在哪**，那支測試改成這樣要求。

### 4. 按鈕看起來要像按鈕

工具列本來是一排沒有邊框的字 = 讀起來像選單列，而選單列是拉下來的、不是按的。
現在每顆有自己的表面與邊框，主要動作維持強調色。`First [200]` 加上 ` defects`
後綴 —— 沒有單位的 200 可以是任何東西。

新測試 `tests/test_ui_controls_readable.py`（9 個）。計畫書 §17。

### 還沒做（使用者清單上的 B / C 組）

B：輸出埠的 `+`（n8n 最核心的操作）、畫布縮放控制、節點副標印關鍵參數。
C：參數說明只在焦點列展開、空面板給一顆「Open KLARF…」、狀態列的錯誤要有顏色。

---

## F7-14 —— 從畫布上就做得完一條 pipeline（B 組）（2026-07-29）

使用者清單裡「n8n 的手感」那三項。看起來像外觀，其實都是功能。

### 1. 輸出埠上的「+」

以前加一張卡要回卡片庫，從 22 張裡自己判斷哪一張接得上。卡片庫的作法是「全部
列出來、接不上的標 `needs diff`」—— 那個 badge 對不會寫 code 的人沒有動作可做。

**但「接得上」引擎本來就知道。** 埠上的「+」跳出來的清單只列現在就成立的卡，
依流程階段排序（那是使用者腦中的順序，不是字母序）。

三個決定：**每個輸出埠一顆**（一顆共用的表達不出「我要對 ref 做」）、
**按的那個埠的影像流會帶進新卡的主要輸入**（不帶的話，從 ref 接出來的 Denoise
卻做在 test 上 —— 那顆「+」就只是一個比較短的「新增卡片」）、
**接出來的線是實線**（使用者的動作是意圖，不只是順序）。

「+」畫在埠標籤之外 → `boundingRect` 跟著長。這是同一條不變量的第三次應用
（F7-8 殘影、F7-9 座標系）：**畫得出去的東西 boundingRect 一定要涵蓋**。
測試直接斷言每顆「+」的中心都在 boundingRect 裡。

### 2. 縮放控制

滾輪縮放本來就有，但畫面上沒有任何東西說得出這件事 —— 而且滾過頭之後沒有路
回來：點陣底縮小之後每一格都一樣，使用者不知道自己在哪裡。左下角四顆固定的鈕
＋百分比，縮放夾在 25%–300%。

### 3. 節點副標

以前印 node_id（`roi_template`）—— 那是 JSON 的鍵，而卡片名字就在上面一行。
現在印 `吃什麼 → 吐什麼`（`test ref → ref_aligned`）。Region 卡不寫影像流，
取 `resolve_regions_out()`（`diff → cell`），否則它看起來什麼都不產出。
重複的卡才把 id 帶出來（`denoise2 · ref → ref`）—— 那時候那個 id 才有意義。

新測試 `tests/test_ui_f7_14_canvas_flow.py`（12 個）。計畫書 §18。

### 還沒做（使用者清單的 C 組）

參數說明只在焦點那一列展開（現在 11 個參數 × 每個 2–3 行灰字＝一定要捲）、
空面板給一顆「Open KLARF…」、狀態列的錯誤要有顏色。

---

## F7-15 —— 畫面上的字要能被讀完（C 組）（2026-07-29）

清單最後一組。三件都不是「功能不對」，是**讀不完／看不到／分不出來**。

### 1. 參數說明收成一行，用到才攤開

11 個參數 × 2–3 行灰字 = 一面牆，一定要捲，而且真正要緊的事（這張卡還沒有模板）
淹在裡面。現在平常一行（自己算 `elidedText`，不讓 Qt 硬切在字中間），滑鼠移上去
或欄位拿到焦點才整段攤開。**錯誤永遠攤開** —— 那是他現在最需要讀完的一句話。

`hint_text()` 回的是**全文**不是畫面上那一段：收起來只是畫面上的事。全文也在
tooltip 裡。不做成「只留 tooltip」是因為那等於把說明藏起來。

Qt 的坑：滑鼠從列的空白處移進**這一列自己的**輸入框時，Qt 先送 Leave 給列、
再送 Enter 給子元件 —— 照字面處理就是收起來又立刻攤開，看起來閃一下。
`leaveEvent` 改成直接問游標還在不在這一列的矩形裡。

### 2. 沒資料時最大的那一塊要說得出下一步

以前是一片黑 + 正中央一行 `(no image)` + 角落一行更小的 `(no dataset loaded)`。
首啟導覽關掉之後就沒有任何東西說得出下一步。現在那塊是 QStackedWidget：
沒資料 → 「No data loaded yet」＋ **Open KLARF…** ＋ **Try it with sample data**。

### 3. 「沒成功」不能跟「做好了」長得一樣

狀態列是唯一會講「這件事沒成功」的地方，而它跟「Added denoise」用一模一樣的
灰字，在畫面最左下角。`_status(msg, "error")` 掛屬性，QSS 變紅字粗體。

測試不比對顏色值（會綁死主題），而是**同一句話渲染兩次、只有 level 不同**，
比畫素 —— 「屬性設了但 QSS 沒規則」正是要擋的情況。哪些訊息算 error 是逐條
列舉的，不是字串比對（規則比對會把「No results to export yet」也染紅）。

新測試 `tests/test_ui_f7_15_reading_load.py`（9 個）。計畫書 §19。

---

## F7-16 —— 四張安全網（2026-07-29）

使用者看完畫面之後問「還有什麼可以改」。我列了三類，這四項排在功能面
（Feature 面板）前面 —— 因為它們損失的是**已經做完的工作**，不是方便性。

### 1. 復原（Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y）

`RecipeModel` 每個變動之前存一份**整個編輯狀態的快照**，不是反向操作。
理由：這個 model 有連帶效果（`add_edge` 會重排 `node_order`、`set_param` 會補上
相依預設值），反向操作要為每一種各寫一次「怎麼倒回去」，漏一個就是「復原之後
跟原本不一樣」，而那種 bug 使用者看不出來。recipe 很小，存整份是幾十 KB 的事。

**滑桿合併成一步**：拖一次會發幾十次 `set_param`，每次各記一步的話按一次 Ctrl+Z
只退回一個畫素。鍵在換節點／存檔／復原時清掉 ——「調 A → 做別的 → 再調 A」
是兩件事。

### 2. 快捷鍵

以前一個都沒有。Ctrl+O / Ctrl+Shift+O / Ctrl+S / Ctrl+R / Ctrl+Z / Ctrl+Shift+Z /
Ctrl+Y / Ctrl+0 / Ctrl+± / Ctrl+Shift+F / Ctrl+F / Ctrl+←→，全部照作業系統慣例。

坑：`_update_action_states()` 每次 refresh 都會重寫那幾顆的 tooltip，所以
「建構時附加一次」第一次 refresh 就沒了。改成**設 tooltip 的動作自己補上快捷鍵**。

### 3. 關窗前問一次

`model.dirty` 一直有維護但沒有人讀它。三個答案：存檔／不存／取消，而**存檔失敗
或在存檔對話框按取消不算可以關**（那是「我改變主意了」）。`_on_save_recipe()`
從回 None 改成回「真的存下去了嗎」。

`tests/conftest.py` 在測試裡一律關掉這個對話框 —— modal 對話框不會讓 headless
測試失敗，它會讓測試**永遠停在那裡**，那種卡住最難查。

### 4. 跑到一半可以停

引擎本來就支援（`run_batch` 的 `abort_check`、`TrialWorker.abort()`），只是畫面上
按不到，使用者唯一的中止方式是關掉整個視窗。進度條旁邊加一顆 Stop。

**已經跑完的留著**（按停止是「不要再等了」，不是「丟掉剛才那五分鐘」），而且
**不能講 finished** —— 被中止那批的數字描述的是「你叫我停的時候跑到哪」，
不是整批的結果。差一個字，後面的抓漏率／誤殺率就都建立在錯的前提上。

新測試 `tests/test_ui_f7_16_safety_net.py`（22 個）。計畫書 §20。

### 下一步

Feature 面板（使用者說「右下原 Feature 那一塊還可以拿來利用」）—— 討論中。
候選：每一列加「這顆在整批裡站哪裡」的分布 + 百分位、點一個特徵就讓它變成
直方圖/門檻的主角、分數表達式的逐項拆解。資料都已經在 `trial_results` 裡。
