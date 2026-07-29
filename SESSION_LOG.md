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

驗證方式也記一下：本機 PATH 上第一個 `pytest` 是 uv 裝的獨立工具（自己的 venv、
沒有 numpy），跟 CI 的情況不同 —— 要用與 `python -m` 同一個直譯器的那支
（`/usr/local/bin/pytest`）才驗得準。加了 conftest 前後各跑一次確認因果。
