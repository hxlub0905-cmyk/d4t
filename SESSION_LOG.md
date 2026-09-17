# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| **2026-09-01 起** | 這個檔案（下面）—— F67 GLV 的「跟誰比」由線決定、F68 GLV 是抓 defect 的主力卡、F69–F72 設定欄／Feature 表／ADC 那一頁／報表打得開、F73 把 F68 的驗收真的跑完、F74 Region 段只剩一張卡、F83 使用者回報的三個 UI bug、F84 ruff 那道關／`align_off` 的症狀／bundle 不再壓縮／救回兩份沒併進來的東西、F85 PEAR 的均勻度（一格參數、四張圖、三個「我原本說錯了」）、F86 使用者拿去用回來的四件（試跑不寫要說出來／Golden Cell 130 s→17 s／recipe 少了 CSV／手冊漏了那排快捷鈕）、F99／F100 UI 評審的二十一件、**2026-09-09 四輪**（working numbers 到處找得到、下拉一張卡一組帶說明、跑與寫拆開＋Re-run、Results 單擊帶主畫面、Output／判定樹的預覽跑到底、卡片寫 img/s、表頭四個變體四種字、縮圖與表格同一份排序／篩選） |
| 2026-08-19 ～ 08-28 | [`docs/history/2026-08b.md`](docs/history/2026-08b.md) —— F42 區域線走 edges、F43–F45 結果表分層／區域接線／FeatureSpec、F46/F47 檔案架構與授權、F48 六個決定、F50 畫布上只剩卡片和線、F51/F52 特徵名與數字只有一種寫法、F53–F57 五件小事、F58–F66 合成資料長成真的那種 layout |
| 2026-08-07 ～ 08-18 | [`docs/history/2026-08.md`](docs/history/2026-08.md) —— F8 純規則 ROI、畫布 n8n 化、Phase 1 收斂、F10、Phase 2 的 Input／Enhance／Region 三段 |
| 2026-07 | [`docs/history/2026-07.md`](docs/history/2026-07.md) —— M0–M7、F7-9…F7-24 前半、兩台機器與搬運通道的成形 |

**切點換過一次。** 前兩份用的是「上一次合併進 main 的那一輪」，而這條分支從
2026-08-19 起就沒有再併回 `main` —— 那條線因此不再切得動任何東西，再等下去這個
檔案只會一直長（第三份封存之前它是 6,380 行 / 392 KB）。所以第三份改用**月份**。

封存不是整理癖：這個檔案**只增不減**，而它跟著整包被複製進公司機
（`docs/history/` 不進搬運包）。包的大小**不是限制**（2026-08-17 使用者確認直接
複製 raw，見 `AGENTS.md` §2）—— 封存是為了 diff 乾淨與公司機用不到的東西不佔
體積，不是為了那道 1 MB 的線。

---

## F104：二維自相關找峰；模板對話框收回一列；Mark one cell 刪掉（2026-09-17）

使用者看過 F102／F103 之後定的三件事（[`docs/history/plans/F104-period2d-and-fewer-buttons.md`](docs/history/plans/F104-period2d-and-fewer-buttons.md)）：

* **二維自相關**（`core/algo/period2d.py`）：交錯 layout 上投影法 X 軸互相抵消（實測
  回 None、Y 回一列的高度），二維自相關沿軸找離原點最近的峰 → 真正的矩形單元 32 × 48。
  分工在 `template._measure_period`：投影法是主，同意就不改（黃金值不動），只在
  「投影量不到而二維量得到」或「二維是投影的整數倍」時接手並講一句。
* **按鈕收回一列**：crop 併進載入（每次載入都先問「哪一塊」，整張是一顆鈕）；
  「Mark one cell」**刪掉**（使用者：不實用）—— `seed.py`、`origin=` 參數、seed 模式、
  三十幾條測試一起拿掉，`GoldenCell.origin` 留著給格線用。
* **Grid 開關**取代「Check on the image…」：開＝格線視窗出現、跟著 re-stack 更新；
  關＝收起來；直接關視窗開關跟著彈回。

---

## F102：疊模板之前先框一塊；cell 週期怎麼算、算錯怎麼知道（2026-09-17）

使用者：「幫我加入 crop 功能，載入 template 的大圖，可以選擇要不要 crop 想要的部分
之後再進行計算。目前計算 cell 方式你覺得還可以添加什麼方法，假設算不對我該怎麼知道？」

**Crop 做了**（[`docs/history/plans/F102-crop-before-stacking.md`](docs/history/plans/F102-crop-before-stacking.md)）：
新模組 `ui/crop_dialog.py`（`CropView` 拉框、`CropDialog` 三選一），`TemplateDialog`
多「Crop first」勾選（挑圖／用畫面上那一張之前先問）與「Crop…」鈕（事後換一塊，
重新量週期）。裁的是原料不是結果：框不進 recipe，摘要講「cropped to W × H px at
(x, y)」；`restack` 走整張＋框。從 recipe 讀回的模板沒有原料，「Crop…」講出來。
`tests/test_ui_crop_dialog.py` 十一條。

**F103 —— 使用者說「好 試試看」，當天做了清單裡的第 1 項與「鋪回原圖」**
（[`docs/history/plans/F103-seed-cell-and-lattice-check.md`](docs/history/plans/F103-seed-cell-and-lattice-check.md)）：
`algo/seed.period_from_seed`（框一格 → NCC 找複本 → 框那一列／那一行剖面的峰間距
＝週期、框的左上角＝原點；平的軸靠「整條剖面都很像」擋掉）、`GoldenCell.origin`
（含錨定捲動的格線原點；`build_golden_cell(origin=)` 不搜相位不錨定）、
`ui/lattice_dialog.py`（`ImageView` 把引擎真的用的格子鋪回原圖）、`TemplateDialog`
的「Mark one cell…」與「Check on the image…」。兩個第一版的坑都有測試：平的軸量到
假週期、沒有週期的軸原點不是 0 就疊出全黑的 cell。

**使用者拿去用回來的三件**（同一天）：① 「使用後跳出 error」——`CropView` 有一個叫
`rect()` 的方法蓋掉了 `QWidget.rect()`，還沒拉框時 `paintEvent` 的 `fillRect(None)`
炸在使用者面前；headless 測試沒抓到是因為視窗從沒真的畫過。改名 `box()`／`set_box()`，
`tests/test_ui_crop_dialog.py` 現在 `grab()` 一次逼三個視窗真的畫。② 「上方按鈕變得
有點多」——那一列有十一個東西，拆成兩列：圖從哪來（還沒有圖就有意義）／cell 怎麼定
（每一顆都要先有圖），第二列排不下橫向捲。③ 「我該怎麼使用」寫在回覆裡。

**cell 計算的替代方法與「算錯怎麼知道」** 寫在回覆裡（摘要）：現在是投影 FFT ＋
自相關（`algo/period`），弱點是投影會把二維結構壓掉、對斜的／非曼哈頓 layout 與
「兩種 cell 混在一張圖」無解。可加的：二維自相關直接找峰（不靠投影）、使用者拉
一格當種子再用 NCC 找相鄰複本量週期（跟 crop 同一種手勢）、GDS 給的 pitch 直接
填（`build_golden_cell` 本來就吃明講的 px/py）。算錯的訊號已經有四個（agreement、
sharpness、k× 提示、諧波修正的 warning），缺的是「把 cell 鋪回去疊在原圖上看」與
「換一塊 crop 重算、兩個答案要一樣」—— 後者現在用 Crop… 就做得到。

---

## `.I01`：副檔名不同的 patch TIFF；Load 卡要不要合回一張（2026-09-17）

使用者：「我想將 load (input) 卡片整合，你覺得呢？同時我要能支援新的圖檔叫做
I01，一樣是跟 klarf 一一配對的」。兩件事，一件做了、一件給了建議等定調。

**`.I01` 做了（F101，[`docs/history/plans/F101-i01-companion.md`](docs/history/plans/F101-i01-companion.md)）**
—— **不是新 kind、不是新卡**：一份 KLARF 配一個檔、裡面是多頁 TIFF，資料形狀跟
`.tif` 逐項相同，所以副檔名只住在「去哪找檔」那一層：

* `klarf_core.PATCH_IMAGE_EXTS = ('.tif', '.tiff', '.I01')`，`tiff_path()` 的同名候選
  多找它（大小寫都試，Linux 分大小寫）；KLARF 的 `TiffFileName` 直接指到 `.I01`
  本來就吃得下。找到之後 kind、卡片、快取簽章都看不到副檔名。
* `dataset._TIFF_EXTS` 多 `.i01`（`Open image…`／`Open folder…` 的「這是多頁檔，去
  開 stack」提醒一視同仁）；Studio 的 stack／image 兩個對話框過濾字串加 `*.I01`；
  CLI `--tiff` 的 help 講明兩種副檔名。
* **真檔當天就看到了**（使用者的另一個 agent 解析 `.001`＋`.I01`，只貼結構不貼
  識別碼）：record 語法 1.8、`ImageFileName` 住在 `WaferRecord`、`.I01` 是 MM 多頁
  TIFF 64×64 8-bit、列尾 `Images 2 {id "30", id "31"}` 的 **id 全檔連號、page = id − 1**
  —— 正是 `defect_image_map` 既有的 imagelist 模式，對映零改動（`FAB-VALIDATION.md`
  #8 當天開、當天結）。使用者接著確認 **`"30"` = test、`"31"` = ref，「以後 pair 的都預設
  第一張為 test」** —— 跟 `Load images` 預設的 `1:test, 2:ref` 一致，零改動。順手補兩件：`defect_image_filename` 不再把 `"30"` 當檔名；
  `.I01` 不在旁邊時 `load_dataset` 講出 KLARF 點名的那個檔名。
* **假設錯的那一天**（`.I01` 內容不是 TIFF）：`load_dataset` 先
  `tiff_index.check_header`（8 個位元組），不是就 warnings 講一次「哪個檔、為什麼、
  跑哪支探測腳本」，defect 進來、沒有影像。以前 `bit_depths` 對非 TIFF 安靜回空
  list（刻意的），後果是載入看起來正常、每一顆各自倒在 `Not a TIFF` 上。
* `tools/make_sample.py --image-ext .I01`：家用機唯一能練這條路的資料；預設產出
  逐位元組不變。兩支 fab_probe 跟著改（`sibling_tiff` 鏡射候選表、`probe_tiff`
  的用法多一行）。守門 `tests/test_i01_companion.py`（十三條：同名找得到、KLARF
  指名找得到、像素跟 `.tif` 那份一模一樣、內容不是 TIFF 時那句話、三處對得上、
  兩支探測腳本讀得動、真檔形狀的三條）。

**Load 卡合併：建議不併（等使用者定調）。** 理由寫在回覆裡，摘要：拆是使用者
2026-08-17 自己定的（「畫布跟實際對不起來」），而拆完之後兩張卡都只看使用者看得到
的值（`channel_map`／`out`）—— 合回一張的話單張資料要靠 `1:single` 這種對照表
才不說謊，等於把「選哪張卡」換成「填對那張表」，沒有比較簡單；代價是一道遷移
（`load_single` → `load_patch`）、兩份出貨 recipe、三十幾支測試、起手卡與 lint
的 kind 分支、黃金值。**`.I01` 不需要它**：格式住 ingest，卡片只看「一顆幾張」。
如果痛點是「不知道該選哪張」，便宜的做法是卡片庫依載入的資料只亮那一張
（`scope` 的機制），不是合併。

---

## 體檢與十四件待辦（2026-09-09 第五輪）

使用者：「給這個專案一些建議（各方面）」→「把它整理成待處理事項，列出解決方法」
→「好 開始修正」。先量再開清單，十四件裡十三件做完，一件做了一半（見末段）。

量到的（都有證據）：`studio.py` 的天花板兩天被調高 17 次（尺變成流水帳）；
`d4t/` 有 203 個 `except Exception`、59 個直接吞掉、零處 `logging`；文件裡
「幾張卡／幾份 recipe」四處三種答案；421 條 `noqa` 標的是沒開的規則；
`test_glv_combinations.py` 在核心批裡開 Qt，沒有 Qt 函式庫的機器核心批紅 34 條；
`pytest` 與 `python -m pytest` 不是同一個直譯器；`docs/plans/` 八份有七份早已出貨。

做了什麼（一件一個 commit）：

* **尺**：`HARD_CAPS` —— `studio.py` 那三格上限本身不准再調高（凍在 logger 那一刀
  之後的 7,753／298／437）。`CLAUDE.md` 也進 `FILE_CEILINGS`。
* **留痕**：`d4t/core/log.py`（一個 logger、預設不寫；`swallowed("模組.函式")`），
  59 處補一行、`ctx.warn` 送一份、CLI `run --log`、Studio 寫進 `crashlog.log_dir()`。
  `tests/test_core_log.py` 用 ast 守「寬的 except 不准再安靜吞掉」。
* **文件對真值**：`tests/test_docs_match_registry.py` 從 registry 與 `recipes/` 數。
  `tests/test_plan_docs.py`：計畫書前 5 行要有「狀態：」，七份已收斂的搬進 history。
* **測試分批**：兩支改名 `test_ui_*`；核心批的 lazy Qt import 一律
  `importorskip("PySide6.QtWidgets", exc_type=ImportError)`（pytest 9 起預設只認
  `ModuleNotFoundError`；dev extra 的 pytest 底線抬到 8.2）；`test_no_qt.py` 兩條守門。
* **工具鏈**：`ruff` 加 `RUF100`、清 352 條沒作用的 `noqa`（有說明的留成註解）；
  `tools/typecheck.py`（pyright basic 掃 core，上限 136）＋ CI job；UI 批只在 3.11 跑；
  `.gitattributes`（KLARF／fixtures／bundle 標 `-text`）；文件一律 `python -m pytest`。
* **doctor**：Qt 開不了視窗是 △，結論分「命令列可以、Studio 不行」兩句；指令用
  `os.sep`。
* **版本**：bundle 檔頭 `BUILD <sha12> <date>`（= `tools/FILELIST.txt` 的 blob SHA），
  `python -m d4t --version` 印同一個數 —— 公司機沒有 git，這是它答得出「哪一版」的
  唯一方式。
* **第三份出貨 recipe**：`recipes/ebi-die-to-die.json`（ref 借 test 的範圍、
  |test − ref|、median 3、GLV 讀最亮那一點；三個 seed 各 24 顆：24／22／23 中）。
  「用範例資料試一次」入口打開（`SHOW_SAMPLE_DATA = True`，`TEMPLATE_RECIPE` 指它）。
* **`CLAUDE.md` 647 → 319 行**：規則留下，故事逐字封存進
  `docs/history/CLAUDE-2026-09-09.md`。

**做了一半的那一件**：`studio.py` 的接線搬成 controller 模組
（`results_wiring` / `decide_wiring` / `canvas_wiring`）。這台容器沒有 Qt 系統函式庫
（`libEGL.so.1`），UI 測試一條都跑不了，盲搬 7,700 行的 god object 不是一個可以
驗收的動作 —— 留給家用機。同一個理由：這一輪改到的 UI 測試
（`test_ui_template_library.py`、`test_ui_welcome.py` 那條「整條路跑到底」、
`test_ui_glv_combinations.py`、`test_ui_guided_condition.py`）**沒有在這裡跑過**，
請先 `python tools/run_tests.py`。核心批（`--ignore-glob="*test_ui_*"`）與黃金值
三份在這裡全綠。

---

## Results 表：四欄一樣的 min、跟 Tiles 一樣的排序與篩選（2026-09-09 第四輪）

使用者：「results 內 table 會有重名的 column，例如中間會有 4 欄一樣的 min
4 欄一樣的 max，同時希望它跟 Tiles 一樣支援排序跟篩選」。

* **重名的欄**：下層表頭只看 metric（`feature_tree.stat_label`），而
  `glv_stats` 開 each box 之後同一個統計量有 typical / outlier / outlier_box /
  worst 四欄。現在名字裡真的有的兩段接上去（``Min · typical``、
  ``Δ · Median``；`VARIANT_WORDS` 一張表），沒有那兩段的一個字不變（既有測試
  `"Median"` 照過）。兩張卡只差 `output_prefix` 的那種（``N_glv_min`` /
  ``M_glv_min``）另一條路：`header_spans` 把前綴當成區域那樣在上層表頭成段
  （淡灰，區域才有顏色）；`group_row_wanted` 是「要不要上層」的唯一判準。
* **排序**：表頭點一下本來就會排（`setSortingEnabled`），缺的是跟縮圖**同一
  個**排序 —— 現在縮圖的下拉換了表格照那欄排、表頭點了下拉跟著
  （`ResultsWindow._on_gallery_sort` / `_on_table_sort`，`_syncing` 擋回彈；
  `GalleryPanel.sort_changed` 只在使用者手勢時發）。
* **篩選**：`ResultsTableModel.set_filter` 吃跟 Gallery 一字不差的
  `make_filter` spec（`_all_rows` 留著，換條件不重餵；排序連篩掉的一起排）。
  宿主改走 `ResultsWindow.set_filter` 一次餵兩邊（判定段點一類、直方圖點一根
  bar），任一邊按掉 chip 另一邊也清。

尺：`test_ui_results_layers.py` 三條（四個變體四種字、cmp 講比的是哪個
統計量、前綴成段而平鋪仍單層）、`test_ui_results_table.py` 三條、
`test_ui_results_sync.py`（新，兩條：一個條件到兩邊、排序來回）。

---

## 跑與寫拆開、Re-run、Results 單擊帶主畫面、卡片上寫 img/s（2026-09-09 第三輪）

使用者點名四件事，全部做了：

1. **Output 卡也看得到 working numbers。** 清單只有一個來源
   （`studio._dynamic_choices_for`），整批一次的卡（`scale == SCALE_LOT`）接上
   `decision_features()`；逐顆的卡**不接**（判定在它們之後才算，列了就是
   `x = x` 那個 bug）。順手抓到 **`feature_key`（單一個名字）從來沒有過下拉**
   —— `param_form._make_editor` 那一行只認 `expr` / `feature_keys`，於是三張
   Output 卡的 `rank_by` 一直是純文字框，而 `output.py` 的 spec 上寫著「UI 會
   給這一格一支」。lint 那一半：`recipe.let_names_written` 是 let 會寫的名字
   的**唯一的家**（`_decide_unknown` 改用它；`validate` 對整批卡的
   `stale-feature-ref` 現在認得 let）。「插入數字 ▾」搬進 `ui/number_picker.py`
   —— `param_form` 也要用，而它反過來 import `decide_panel` 是一個圈。
2. **跑不寫，寫是另一顆鈕。** 使用者問「還是你覺得不適合」—— 適合：
   `run_batch` 與 `run_batch_steps` 本來就是兩支（batch.py 的 docstring 講的
   正是「寫做成旗標遲早有人忘記關」），Studio 只是把它們綁在一個鈕上。現在
   `run_all` 只跑、`write_outputs` 寫（KLARF `inplace` 的確認搬到寫的時候問；
   被停掉的部分結果拒寫並講出來）。Results 那顆「Run all & write」拆成
   **Re-run** 與 **Write outputs**。Re-run 走 `batch.rerun_decision`：每一行
   let 重算（含跟整批比的，錨拔掉重算）、上一次判定失敗的顆救回來
   （`redecide(revive=True)`）、影像一顆不碰；`batch.measurement_signature`
   決定能不能這樣走 —— 量測那一段改了就整批重跑，**不拿舊數字配新量測卡**。
   底稿是 `_last_run["rows"]`（原封不動那一份），不是畫面上那份。
   ⚠ `tests/test_ui_write_only_on_run_all.py` 的契約整份改寫（那條「試跑不寫，
   只有整批才寫」是使用者 F16 定的，這次也是使用者改的）。
3. **Results 單擊（或方向鍵）一顆 → 主畫面帶過去，不搶焦點**
   （`defect_selected`，雙擊仍是 `defect_activated` 會叫主視窗到前面）。
   「ADC 跟 output 段影像預設不顯示？」—— 是，而且是 F11「沒有線就沒有圖」
   那條規矩的假陽性：Output 卡是整批一次的，逐顆引擎跳過它、沒有 trace，
   `_selected_card_ran` 就把影像清掉。現在 `_preview_whole_route`：選的是
   整批一次的卡、或正在編判定樹（`_tree_focus`）→ 預覽跑到底、連判定，
   路徑才亮得起來。
4. **卡片右上角從總耗時改成每秒幾顆**（`canvas.run_text`：``24 ok · 71 img/s``）。
   加總的 ms 是所有 worker 的 CPU 時間，不是牆上時鐘 —— docstring 講了。

尺：`test_rerun_decision.py`（五條，core）、`test_ui_rerun_and_jump.py`（七條）、
`test_ui_number_picker.py`（三條）、`test_rename_fallout.py` 兩條；改契約的
`test_ui_write_only_on_run_all.py`、`test_ui_button_labels.py`、
`test_ui_results.py`、`test_ui_studio_m5.py`、`test_ui_f99_gestures.py`。
`docs/USING-UNIFORMITY.md` §5 跟著改。

---

## 判定樹上找得到 working numbers；「插入數字 ▾」一張卡一組（2026-09-09）

使用者拿一份 recipe 來問「為何我沒法執行，working numbers 設的 attribute QAA
在後面 tree 上也找不到」。兩件事，一件是 recipe 自己的（樹上有一步 `when` 是
空的 → `bad-rule`；ROI 卡沒模板 → `not-configured`），一件是 Studio 的缺口：

* **樹那一步的「pick a number」與「插入數字 ▾」只列卡片宣告的名字**
  （`labelled_features` 走的是 `_declared_specs`），而引擎（`_eval_decision`
  先算 let 再走樹）與 lint（`_decide_unknown`）早就認得 let 的名字。清單少列
  的那一半正好是使用者自己剛取的。⚠ 這一輪先講錯過一次：「下拉會標成
  from Decision」—— 那是畫布上幽靈線的字，不是下拉的。**答一個 UI 問題之前
  把那一格的來源讀完。**

  補在 `RecipeModel.decision_features(upto_let=None)`：名字、`_missing`、
  `_raw` **不再抄一份規則**，由 `verdict_features.bound_specs` 宣告（family
  `engine`、`base` 是 let 名），這裡只按行序過濾 —— 第 n 行 let 只看得到前
  n−1 行（引擎順序，lint 講的同一句話）；樹的問題與 score 看得到全部。
  卡片的 `labelled_features` **不動**：讓一張卡看到判定段的名字就是 F21-B
  那個 `x = x`。
* **「ADC 下拉選單分類可以再做更好一點嗎」** → `decide_panel.fill_number_picker`
  一支填三個下拉（let 行、score、樹那一步的兩種編法）：一張卡一組、組名是
  卡片的 `label`、組名 disabled 點不到、working numbers 永遠第一組；名字裡
  不再重複「— 誰算的」（`glv_stats` 開 each box 一張卡 55 個名字，那半邊
  重複 55 次）。`itemData` / `findData` 仍是裸名，呼叫端一個字沒改。

順手答掉的三句（寫在對話裡，不進 docs）：算式的空格可有可無（tokenizer
跳過空白）；`_typical` 是逐框值的中位數（含自己）、`_outlier` 是離它最遠那格
的值（跟著 `direction`）、`_outlier_box` 是那一格的序號（0 起算）。

**第二輪（同日）：「你覺得 user 會不會混淆 or 看不懂」—— 會。** 證據不是
猜的：作者自己問了三次才分清 `_outlier` 與 `_worst`，而 `glv_stats.py` 的
`FEATURE_HELP` 註解記著 2026-09-02 有人問過一模一樣的「typical 跟 outliner、
worst、score 是指什麼」。四個提案（補說明／`across_boxes` 那格講兩族／
`_outlier` 一族預設收起來／不改名），使用者：「1 跟 2 先做」。

* **每個下拉項目帶 tooltip**（`decide_panel.number_tips`）：卡片算的走
  `feature_gloss` ＋ `feature_unit`（**跟 Feature 表那一欄同一支**，說明只有
  一個家）；working number 講它的算式、fill、scale，`_missing` / `_raw` 各一
  句。`RecipeModel.bound_feature_specs` 是 `bound_specs` 的投影（同
  `feature_owners` / `feature_regions`）。
* **`across_boxes` 的 help 多一段**：兩族常常指到不同格；`_worst` 一族全部來
  自 judge 挑的那一格，`_typical` / `_outlier` / `_outlier_box` 是每個統計量
  各自的。使用者是在那一格決定開 each box 的，那裡是他唯一會讀說明的時候。
* 第 3 項（收起 `_outlier`）**沒做**，等使用者點頭：出貨 recipe 只用
  `_worst`，但使用者手上那份用了 `_outlier`。

尺：`test_viewmodel.py` 三條（列得出、只看上面幾行、沒判定就空）、
`test_ui_tree_edit.py` 四條（導引式列得出、點了寫進 model、算式框那個也列、
分組長相）、`test_ui_f22_decide_panel.py` 一條（第 n 行只看前 n−1 行）；第二輪再加
`test_glv.py` 一條（那一格的 help 兩族都在）、`test_ui_tree_edit.py` 一條
（每一項都有 tooltip，`_outlier_box` 標成 box）。

---

## F99／F100：一份 UI/UX 評審，與它的二十一件修正（2026-09-08）

一份以 UI/UX 設計師角度做的評審（實際開起 Studio、載出貨 recipe、選卡、試跑、
判定、Results，在 1440×900 與 1366×768、light 與 dark 上截圖）。結論：
**引擎與設計系統是 A，畫面組合是 B−，首次使用的可理解度是 C+。**
使用者定調「加入待辦事項後開始修正」，版面配置「按照你的建議改」。
逐項在 [`docs/history/plans/F99-ui-review-fixes.md`](docs/history/plans/F99-ui-review-fixes.md)，
版面在 [`docs/history/plans/F100-workbench-layout.md`](docs/history/plans/F100-workbench-layout.md)。

### 三個 P0 全都符合 F83 那句「UI 的路壞掉不會讓任何測試變紅」

| | 症狀 | 為什麼沒有測試看到 |
|---|---|---|
| P0-1 | 第二次按 fit／1:1／切 Build 丟 `RuntimeError: … QVariantAnimation already deleted` | conftest 把 `ANIMATE` 關掉了；`DeleteWhenStopped` 之後的殼還握在 `_view_anim` 上 |
| P0-2 | GLV 儀表板三張直方圖的標題左右兩段疊在一起 | 兩段畫進同一個矩形而沒有一方讓寬度；沒有人量過寬度 |
| P0-3 | 載入之後 `minimumSizeHint` 1,334、視窗被撐到 1,495 | U1 的 `fit_screen` 只量開窗那一刻 |

所以這一輪每一項都配一條**會真的開視窗或量幾何**的測試，而
`test_ui_workbench.py` 是第一條「在 1366×768 開 Studio、載資料、選卡、量幾何」
的測試。

### F100：畫布橫躺在上面、工作台在下面

三個結構性的毛病：pipeline 橫著流而畫布是一格窄的直立空間（六張卡永遠得縮到
50%，在 LOD 門檻之下）；畫布和設定區綁在同一根 splitter 上互相擠（1366 上
畫布剩 230 px）；右欄預覽影像的硬最小寬度讓整個視窗裝不下。
新版面：畫布吃滿卡片庫右邊整個寬度、工作台三格（設定區｜儀表板｜預覽影像）
並排在下、Verdict 是常駐的結論列。邏輯在新模組 `ui/workbench.py`，
`studio.py` 只留接線。⚠ `params_open` 的意思從「設定區攤開」變成「工作台攤開」
—— 影像住在裡面，所以 Tune 模式**開窗就攤開**、取消選取不收。

**v2（09-09）**：第一版在 1366×768 上截圖之後使用者問「畫布會需要那麼大的
空間嗎」——不需要。畫布要的是寬度不是面積，而且 Tune 裡它是導覽。第一版把
影像、設定區、儀表擠在下面同一列，最高頻的迴圈（調參數）要看的三樣東西全變小。
v2 把影像還給右欄、全高，設定區與儀表在畫布下面；Build 把右欄與工作台都收掉。
F100 §7 有對照表，也寫了「最好」還沒定案、要在那台 1366 的機器上試。

**細線（09-09）**：使用者看 v3 截圖說分隔線「又怪怪的」—— 量像素是直向 5px、
橫向 9px 的實心灰條，v2 那條 QSS 沒有做到「1px 看得見、5px 抓得到」。四種 QSS
寫法都不行（Qt 算把手尺寸不分方向），改成 `ui/splitters.py` 自己畫，配一條數
像素的測試。細節在 F100 §8.1。

**v3（同一天）**：使用者看 v2 的直方圖那一格「給的空間會不會太少」（會），
然後「最一開始的排版最好，儀表換到影像下方」——他是對的：直方圖與設定區要的
都是寬度，v2 讓兩個擠同一列；v3 各給一整欄，只有影像付出高度而那是拖一下就
補得回來的。右欄變成直向 splitter「影像／儀表」，中欄下半只剩設定區。
F100 §8。三版都在 git log 裡（v1 `17ad451`、v2 `568c14a`）。

同一輪兩件小的：**區域之間的細線**（使用者：「建議加入細線去區分區域」）——
線一直在（QSplitter 的握把 1px `border_default`），只是 F81 把 `bg_page` 壓到
#e6e9ee 之後兩者只差 ΔL* 1，看不見；加 `divider` token（取畫布點陣那一級的
深度）、握把 5px 抓得到、中間 1px 看得見，配一條「分隔線看得見但比卡片邊框
淡」的對比測試。**GLV 那排三顆 intent 膠囊**以前是 QHBoxLayout，把設定區最小
寬度撐到 376 px，是 v2 三欄在 1366 上裝不下的最後一根稻草——改 `_ChipFlow`
（最小寬度＝最寬那一顆，塞不下就折行），設定區最小寬度 376 → 187。
⚠ 一個新病：Verdict 列搬進右欄之後，那句不換行的「preview stops at …」把整欄
最小寬度撐到七百多 px，視窗長到 1,680——同一個病的新出口，換行就好；右欄在
Build 是 **hide** 不是 setSizes 到 0（有最小寬度的 widget 會被撐回去，量到 1,993）。

### 順手抓到的兩個測試陷阱（都會讓整套 UI 測試停在一個 modal 上）

* `autosave.offer_restore` 在 pytest 裡會讀、會問、會刪**使用者真正的**草稿。
  一支被中途殺掉的工具（`tools/i18n_todo.py`）留下 `~/.d4t/autosave.json`，
  之後每一條會開 Studio 的測試都停在「Bring back your unsaved pipeline?」上，
  faulthandler 都叫不醒（C++ 的 `exec` 裡 Python 沒有機會跑）。現在 `DIR` 是
  預設而且在 pytest 裡 → 什麼都不碰。
* conftest 那支關掉「要不要存」的 autouse，只在 `d4t.ui.studio` **已經** import
  的時候改得到類別屬性——在 fixture 裡才 import 的測試檔改不到。
  `StudioWindow.__init__` 現在在 pytest 裡預設關掉它。

### 其他

P1：空白處右鍵加卡、拖線到空白處彈相容卡片的選單（`ui/card_menu.py`）、
Verdict 停在中途時說為什麼、Region 卡標題帶區域名、`needs test` →
`needs a “test” stream`、卡片第三行用 `ParamSpec.label`、試跑後每張卡標
`24 ok · 0.3 s`、選到判定樹時儀表板淡掉、Ctrl+C/V/D（`ui/clipboard.py`）。
P2：字級全部走 token（`font_body` 12 → 13 對齊真相；26 處 `setPointSizeF` 改
`font_px`）、顏色漏網收進 token、對比度參數化測試（dark 的 accent 量到 3.33，
釘住配反向測試）、accessible name、i18n 接 library／problems_bar／welcome、
Help 鈕的小箭頭列出開著的視窗（`ui/windows_menu.py`）。

`test_size_ceilings.py` 的五格各調了一次，理由寫在每一格旁邊。

---

## F95–F98：外部檢視清單剩下的十七件（2026-09-08）

P0 六件與 X4／U11／U7／U6 收完之後，這一輪把 P1 與 P2 全部做完。

### F95：意思寫在字上、一句話說完要有下一步

| | |
|---|---|
| **U9** | 階段順序、標題、副標合併進 `step.GROUPS`，`LibraryPanel.GROUPS` 消失。⚠ 那條「兩份要一致」的測試因此變成**恆真的斷言**（F40 那個形狀），換成問它的因：UI 上沒有第二份 |
| **U12** | 十九處 `setStyleSheet()` 自己寫死尺寸 → 一組照角色取名的字級 ＋ `hairline`。三個 `border-radius:8px` 改吃 `radius_md`（6px）—— 它們本來就是「一塊面」，8px 是漂出來的 |
| **U15** | 十一個頂層視窗、零條規則 → 「只有要跟主視窗並排對照的才開頂層視窗」寫進 `docs/ARCHITECTURE.md`，配一支釘住那兩張表的測試 |
| **U13＋X7** | `is_real_style` 會把紅綠對調，而**兩種模式的文字一模一樣** —— 同一個綠色 chip 在兩份 recipe 裡意思相反。現在名字排第一（recipe 自己取的 class name）、`bin N` 退成補充、顏色翻面時字跟著翻面，tone 另外帶一個不靠顏色的通道 |
| **X5＋X6** | 兩個抱怨同一個形狀 → 一個機制（`ui/status_action.py`）。**下一句話一定把它收起來**，而且收在 `_status` 裡不是每個呼叫端 |
| **U21** | Results 鈕帶計數；沒跑過就 disabled 而且 tooltip 講下一步 |
| **U17** | `recipe.describe_migration` 比對前後講成人話，而不是讓 19 道 `_migrate_*` 各自回報 —— 那會是 19 個要維護的字串，而第 20 道一定會忘 |

### F96：鍵盤走得到、抽樣不再說謊、範圍收斂成一句話

**U18** 的關鍵不是加兩個鍵，是**綁在哪裡**：Delete 綁成 window-level 的話，
使用者在參數區的輸入框裡按 Delete 會刪掉一張卡。所以那兩個鍵是
`WidgetWithChildrenShortcut`，掛在畫布上；刪除本身仍然只有一份實作。

**U19** 第一次接線的提示畫在那顆埠旁邊（不是一塊面板）—— 提示要長在它講的那個
東西旁邊，跟 F7-22 那顆「斷開」的 × 同一條規矩。有線之後自己消失。

**U20** 區域線改吃 `region_hex` 那組調色盤。⚠ 講明它**不保證**跟預覽影像上那個
框同色（影像那邊是逐卡編號的）—— 「顏色一樣＝同一個區域」是很自然的猜測，而它
在這裡只是常常成立。

**X3** 新的 `core/pipeline/sampling.py`：`first` 仍然是預設而且**逐顆等於舊的
切片**（這個功能不准是一次無聲的行為改動）。分層那一欄整批是空的時候退成
random **並在紀錄裡說出來** —— 硬分一層的話跑得完、有數字、而紀錄是錯的。

**U10** `fab` / `dev` / `demo`。⚠ 旗標要透過模組讀，不准
`from .scope import SHOW_…`：那拿到的是一份當時的複本。`welcome.py` 本來就是那樣
寫的，這一輪改掉並補了 lint。

**U16** 先量再設門檻（同 F90）：6,000 顆下 Results 開窗 0.024 s、鋪 Gallery
0.026 s、重算判定段 0.009 s，門檻設在約 20 倍 —— 那個倍率抓的是「有人把它寫成
O(n²)」，不是「今天機器慢了一點」。

### F97：一個視窗兩種模式，參數與儀表挨著

**U5** 彈出視窗退場。代價本來是**兩份 `PipelineCanvas` 實體與兩份狀態** ——
每個訊號接兩次、每次重畫記得兩邊都畫，而畫布明明是這個工具的賣點。

⚠ 第一版把「模式」跟 `params_open` 合成一個狀態，而那是錯的：模式是**使用者選
的版面**，`params_open` 是 Tune 裡「選到一張卡就攤開」那個**自動**行為。合在
一起之後開窗的狀態自相矛盾（`mode=tune` 而 `params_open=False`）。

**U8** 儀表搬到參數旁邊。調參數的迴圈是「改一個數字 → 看那個數字怎麼變」，而那
兩件事以前隔著整張影像。新的測試除了問結構，也**真的量一次座標**。

### F98：使用者面的字只有一個進出口

**U14** 的設計選擇是**鍵就是英文原句**（不是 `toolbar.run_trial`）。三個理由，
而第三個是真正的理由：**它讓「之後不必改 38 個檔案」這句話成立** —— 鍵是原句的
話，翻譯層可以擺在共用的那幾支（`_tool_button`、`small_button`、
`_HintLabel.set_full_text`、狀態列），包一次涵蓋幾百句而呼叫端一個字都不用改。

實測：只點過八張卡就有 **155 句**流過 `tr()`，而 `d4t/ui` 只動了四個地方。

⚠ **不翻譯的兩類**：卡片名（`Step.label`）與階段名 —— 它們是 recipe JSON 的鄰居
與廠內的共同語彙，翻掉的話同一份 recipe 在兩台機器上講的是兩個名字。有三條測試
守著這句話，其中一條直接檢查出貨的那份 catalog 裡沒有任何卡片名。

出貨一份 `zh_TW.json`（39 句：工具列、按鈕、狀態列那些高流量的）＋
`tools/i18n_todo.py`。**待翻清單是跑一次收集出來的，不是掃原始碼** —— 翻譯層
擺在共用的那幾支，所以大部分句子在原始碼裡看起來不像要翻的東西。

### 這一輪學到的一件事

**「把兩個看起來一樣的狀態合成一個」踩了兩次。** U5 的
`layout_mode` vs `params_open`（開窗時自相矛盾）、U14 一開始想把卡片名也一起走
翻譯層。兩次的判準都是同一句：**它們是不是同一個人在同一個時候做的同一個決定。**
模式是使用者選的、攤開是軟體自動做的；卡片名是 recipe 的鍵、按鈕上的字是給人看
的。長得像不代表是同一件事。

---

## F94：U6 —— 接線的**決定**搬出視窗，於是它 0.3 秒就答得出來（2026-09-08）

外部檢視清單 U6：「抽出圖編輯語意」，驗收條件是**「接線／換線／剪線的既有
不變量改由不需要 `QApplication` 的測試覆蓋」**。

### 為什麼是這幾支

`_connect` / `_connect_region` / `_drop_conflicting_edges` / `_unpoint_stream`
/ `_unmet_needs` / `_producers_of` 是**引擎正確性的一半** —— F9／F10／F42 那
三輪踩過的七個「跑得完、有數字、而且是錯的」全部發生在這幾支裡（一個輸入埠
兩條線、剪一條連旁邊那條一起剪、區域線被當成影像流…）。

而它們住在 `studio.py` 上，所以**每一條相關的測試都得先開一個視窗**。代價
不是等待本身，是那個等待改變了人的行為：驗一條新的不變量要付 30 秒，於是
它就不會被驗。

### 做了什麼

`d4t/ui/edit_plan.py`（新，**不 import Qt**）：吃 `RecipeModel`，回一個
`ConnectPlan` / `UnpointPlan` —— 「這條線該落在哪一格、要不要擠掉別條、擠掉
哪幾條、還是根本要拒絕（連下一步該怎麼辦一起講）」。

⚠ **它只回答「應該發生什麼」，不動 model。** 真的動的仍然是 `StudioWindow`，
因為那一段的**順序**有意義：`add_edge` 會因為成環而失敗，而失敗的那條線不該
留下任何痕跡 —— 先算好計畫、`add_edge` 成功了才照計畫剪掉舊線，是唯一不會
在失敗路徑上弄髒 model 的寫法。

`tests/test_edit_plan.py`（新，18 條）跑在**核心那一批**裡：**0.27 秒**。

### 帳

| | 前 | 後 |
|---|---|---|
| `studio.py` | 7,198 行 | **7,037**（−161）|
| `StudioWindow` 的 `self.*` | 403 | 400 |
| `StudioWindow` 的方法 | 274 | **275**（+1）|

方法**多**一支不是帳算錯：`_drop_conflicting_edges` 裡「算出誰要被剪」與
「真的剪掉並講一句話」本來黏在一起，前者進了 `edit_plan.conflicting_edges`，
後者留下來變成 `_drop_edges`（`_connect` 與 `_connect_region` 都要用它）。

順手統一了一件事：`_on_slot_wire` 的區域那一支以前直接叫 `_connect_region`，
**繞過了 `_connect` 的守門**。現在兩條路都先過 `plan_connect`。

### U7 的兩個尾巴（同日補完）

U7 的驗收跑完之後有兩支紅的，兩支都是**同一類**問題 —— 一張表寫著模組的
名字，而那個模組搬家了：

* `test_ui_feature_value_format` 的兩張例外表（`_AXIS_LABEL_ALLOWLIST` 的
  「直方圖 x 軸刻度」、`_SHORT_OK` 的 `_paint_heat_bar`）指著 `widgets`，
  而它們現在住在 `histogram.py` 與 `image_view.py`。順便把拆出來的那八支
  **全部加進**「只有一個地方可以挑有效位數」那條的參數列 —— 不然拆一次就
  少一條防線。
* `test_ui_f8_ruler` 讀 `widgets_mod.TOKENS`，而那道門沒有把它轉出去。

第二個值得記下來：U7 的「一個名字都不能少」那條測試，清單只數了拆之前
`widgets.py` 自己 `class`/`def` 出來的 **81 個**，漏掉它 **import 進來的**
那些（`TOKENS` / `theme` / `format_feature_value` / `region_hex`…）——
而屬性存取讀得到它們。所以那條測試**自己是綠的**，紅的是別人。清單補到
141 個，並且加一張刻意不轉出的豁免表（stdlib 與 Qt 自己的名字：`widgets.QColor`
從來不是這道門要給的東西）＋ 一支反向測試守著它。

---

## F93：U7 —— `widgets.py` 7,140 行拆成八支，而一個呼叫端都沒有改（2026-09-08）

`CLAUDE.md` §4 早就指名了這一刀：「切 `widgets.py` 那幾群自繪圖示最好拆、
風險最低」，而它的前置條件（黃金值三份全綠）2026-08-23 就成立了。F90 那把
規模的尺 09-08 把它凍在 **7,140 行、24 個不相干的類別**，等的正是這件事。

### 拆成什麼

| 新模組 | 裝什麼 | 行數 |
|---|---|---|
| `ui/buttons.py` | 最底層：`small_button`、`FilterChip`、「停放不銷毀」 | 103 |
| `ui/icons.py` | **按鈕上**那些自繪的圖（膠囊上的仍在 `glyphs.py`）| 1,081 |
| `ui/image_view.py` | `ImageView` ＋ 記號的角色→顏色 | 922 |
| `ui/fields.py` | 參數表單上一列一列的編輯器 | 1,934 |
| `ui/param_form.py` | `ParamForm` —— 「加一張卡，UI 零修改」的執行機構 | 1,020 |
| `ui/chips.py` | 設定區的膠囊（統計量、`chip_choice`）| 769 |
| `ui/library.py` | 三段式卡片庫 | 762 |
| `ui/histogram.py` | 分數分佈 ＋ 可拖曳的門檻線 | 408 |
| `ui/feature_text.py` | 特徵名怎麼變成人看得懂的字 ＋ `VerdictChip` | 291 |
| **`ui/widgets.py`** | **那道門** —— 純轉出口 | **7,140 → 123** |

### 這一刀的形狀：留一道門

四十幾個模組與上百條測試寫的是 `from .widgets import ImageView`，而那句話
描述的是「我要一個元件」，**不是「那個元件住在哪一支檔案」**。改掉它們會讓
這一刀從「純搬移」變成一個橫跨半個 repo 的 diff —— 而這一刀的驗收條件正是
**「無任何邏輯 diff」**。所以搬家的成本留在 `widgets.py`：一層轉出口。

驗收兩邊都成立：**黃金值三份逐項相同**、既有 UI 測試全綠。

### 兩件學到的

**搬家不要用手抄。** 寫了一支 40 行的腳本吃行號區間，把那幾段**原封**寫進新
檔案再從原檔剪掉 —— 逐行相同是機械保證的，不是「我看過了」。它還擋重疊區間
（重疊會安靜地把同一段搬走兩次）。

**「誰在用這個名字」不能只掃 import。** 第一版的檢查用 `ast` 掃全 repo 的
`from ... import`，回報「41 個名字，一個不缺」—— 然後 `test_ui_widgets` 紅了
四條。原因是測試大量用**屬性存取**（`widgets_mod.METRIC_GROUP_ORDER`），
而那種寫法 grep 與 import 掃描都看不到。改成拿 git 裡拆之前的那一份當清單、
逐個 `hasattr` 問一次，當場多出 10 個缺的。

那份清單現在是一條測試（`test_the_split_did_not_drop_a_single_name`，81 個
名字寫死在測試裡 —— 「拆之前有哪些」是歷史事實，不該隨 HEAD 移動），配一條
反向的：`test_the_front_door_stayed_a_front_door` 問「`widgets.py` 裡是不是
又長出 class / def 了」。**沒有後面那一條，三個月後它會再變成一支 7,000 行
的檔案** —— 那正是 F90 那把尺量到的漂移。

`test_size_ceilings.py` 的 `widgets.py` 那一格 7,140 → **123**，而那一格的
反向測試（「縮小了上限要跟著降」）就是逼我寫下這個數字的東西 —— 它第一次
真的響，而且響對了。

---

## F92：接著那份清單的兩件 P1 —— 都是「機制都在，缺的是入口」（2026-09-08）

P0 六件做完之後的下一批。挑這兩件的理由是同一句話：**它們要的東西都已經在
repo 裡了，少的只有一個使用者按得到的地方。**

### X4 · 範本庫關著的前提已經到期

`SHOW_SAMPLE_ENTRIES` 2026-08-16 關掉的理由是「範例 recipe 全部拿掉了」——
那時候按 Templates… 只會開一個空對話框，而**按了撞牆的鈕比沒有那顆鈕更糟**。

那個理由到期了：`recipes/` 有兩份出貨 recipe，而且 `test_shipped_recipes.py`
逐份真的跑一次。而**動手前先量過**：`welcome.RECIPES_DIR` 指的是
``examples/recipes`` —— 一個 2026-08-16 就刪掉的路徑。「範本庫是空的」不是
一句形容，它有機制。

⚠ **但那不是把旗標翻成 True 就好。** 一個旗標管兩顆鈕，而它們的死法不一樣：

* 範本庫：庫是空的 → `recipes/` 填回來就活了。
* 「用範例資料試一次」：`run_demo` 產得出資料，但 `load_template` 指著一份
  **不存在的 ebi_patch recipe**，所以按完是一批資料配一張空白畫布。而出貨的
  兩份 recipe 是 `rsem` 與 `folder` route —— 補不上。

所以先把旗標拆成 `SHOW_TEMPLATE_LIBRARY` / `SHOW_SAMPLE_DATA`。**一個旗標
描述一個決定**；翻一個共用旗標會順手把一顆仍然撞牆的鈕放回畫面上。
`SHOW_SAMPLE_DATA` 配一支反向測試：那份 recipe 有一天存在了而旗標還關著，
它會紅。

### U11 · 單顆預覽就看得到完整回溯

回溯以前只有一條路：**跑一整批 → Results → 點 score/bin**。而使用者手上明明
就有這一顆的每一個數字 —— 預覽已經算完了，`verdict_trace` 吃的也正是特徵而
不是一批結果。那條路要求他先跑幾分鐘，只為了問一句「這一顆為什麼判成這樣」。

做法是把 Results 那個 `WhyPanel` **同一個 widget** 掛進單顆預覽這一欄，
並讓「Path: …」那一行變成連結。清單說這是相對 YED5 的核心差異點。

### 這一輪學到的三件事

**`isHidden()` 與 `isVisible()` 各自在什麼時候會騙人。** repo 已經記著
「視窗還沒 `show()` 之前每一個 `isVisible()` 都是 False」，所以既有測試一律
問 `isHidden()`。但**工具列上的 widget 反過來**：`QToolBar.addWidget` 把它們
包進 QWidgetAction，Qt 在工具列真的顯示之前把它們**全部**藏著 —— 於是
`btn_examples.isHidden()` 在旗標打開的時候照樣答 True。兩條規則現在都寫在
那幾條測試的 docstring 上：一般子元件問 `isHidden()`，工具列上的先 `show()`
再問 `isVisible()`。

**工具列的餘裕只剩 76 px，而那是量出來的不是猜的。** 加回 Templates… 之後
工具列從 997 px 變成 **1,153 px**，而 1366×768 上視窗是 1,229 px。裝得下 ——
但下一顆鈕會把它推過去，而症狀是「某一顆鈕在那台機器上不見了」，開發機
（1920 寬）上看不到。所以那個餘裕變成一條測試
（`test_the_toolbar_still_fits_the_machine_beside_the_tool`）：不是「不准再
加鈕」，是**加之前會有人看見**。

**RichText 的那一行要跳脫。** 路徑裡有 `>`（`contrast > 120`）—— 不跳脫的話
那一段會被 Qt 當成標籤吃掉，使用者看到的是一句少了半截的話，而**沒有任何
錯誤**。這個 repo 最怕的形狀又一次。

---

## F91：外部檢視那份清單的 P0 六件（2026-09-08）

起點是一份 UI／UX 的外部檢視清單（21 項 UI ＋ 7 項 UX，分 P0/P1/P2）。它給的
施作順序是 **X1 → X2 → U1 → U3 → U4 → U2**，理由寫在清單自己身上：

> X1/X2 決定「這個工具能不能被別人用起來」，U1/U3/U4 決定「別人用壞的時候救
> 不救得回來」—— 前者沒解決，後者根本不會發生。

這一輪做完那六件（＝所有 P0），P1/P2 一項都沒動。**七個新模組，`studio.py`
只加接線**（+158 行，`test_size_ceilings.py` 那三格照規矩調高並附理由）。

### 一句話各是什麼

| | 缺口 | 新模組 |
|---|---|---|
| **X1** | 每按一次 Run trial 就把上一次蓋掉 —— 答得出「現在準不準」，答不出「剛才那一下讓它變好還是變壞」 | `ui/baseline.py` |
| **X2** | `ground_truth.json` 只能用手打，而目標使用者不會寫 code | `ui/truth_marks.py` |
| **U1** | 寫死的視窗尺寸在 1366×768 的機台旁 PC 上放不下 | `ui/fit_screen.py` |
| **U3** | 沒有 excepthook、沒有 log —— 打包成 exe 之後出事＝程式不見 | `ui/crashlog.py` |
| **U4** | 關窗有網，當機沒有 | `ui/autosave.py` |
| **U2** | 紅紅的東西散在三個地方，沒有一處說「一共幾個、先修哪一個」；而狀態列**下一句就把上一句蓋掉**，那一句常常是唯一講出「沒成功」的地方 | `ui/problems_bar.py` ＋ `ui/status_log.py` |

### 這一輪學到／確認的幾件事

**「事後把既有版面搬進捲軸」在 PySide6 上是 segfault。** U1 本來想寫一支
「拿任何一個對話框都能包上捲軸」的通用函式，做法是把 `dialog.layout()` 偷出來
塞進一個新的 content widget。實測直接 **Segmentation fault**（不是例外，是
整個 process 沒了）。所以捲軸只能在**建構時**決定，而那句話寫進了
`fit_screen.py` 的檔頭 —— 下一個人會想到同一個做法。

**測試裡的螢幕尺寸要是假的。** offscreen 平台的螢幕是 800×800 —— 一個誰也
沒有的尺寸；在它上面全綠只證明「在 CI 上放得下」。所以 `fit_screen.FORCE_RECT`
是一個具名的測試鉤子（同 `studio.PROMPT_ON_CLOSE` / `canvas.ANIMATE`），
測試把它設成真正要保證的兩個尺寸（1366×768 與 1024×768）。

抓到的兩個真的：`GcGeneratorWindow` 的內容量出來 **1,144 px 高**（比任何一台
768 的螢幕都高，縮視窗沒有用 —— 撐著的是內容自己的 `minimumSizeHint`），以及
`TemplateDialog` 那一列工具鈕的 `minimumSizeHint` 是 **1,023 px**，
它會頂著**整個對話框**縮不進一台 1024×768 的螢幕 —— 一個在版面樹上完全
看不出來的原因。

**`canvas_column.widget(0)` 就是畫布 —— 那是一條有人靠著的不變量。**
Problems 列第一版包在畫布外面（`[畫布, Problems] → splitter`），而
`canvas.py::_build_header` 的說明裡就寫著「包一層容器會讓
`canvas_column.widget(0)` 不再是畫布，而好幾條測試與彈出視窗的邏輯都靠它」——
`test_ui_f8_ui_polish` 當場紅。現在包的是**整個中欄**
（`[splitter, Problems]`），那條不變量一個字都沒有動。
**一個註解寫下來的不變量真的擋下了一次違反**，那正是它存在的理由。

**Problems 列與狀態列歷史是兩個不同的問題。** 前者答「現在還有什麼擋著」，
而那件事從 recipe 推導得出來（lint 隨時可以重跑）；後者答「剛才發生過什麼」，
而那件事**推不出來** —— 一句「Could not save: PermissionError」被下一句蓋掉
之後再也回不來。所以是兩個模組，不是一塊面板的兩個分頁。

**「我不確定」不是「這是誤報」。** X2 的三個鍵是 R / N / **U**：拿掉標記與
標成 nuisance 在正確率上是兩件完全不同的事（前者不進分母）。少了第三個鍵的
話，使用者唯一能表達「我看不出來」的方式就是隨便按一個。

**測試不准碰使用者真正的那幾個檔案。** 三個新模組都寫磁碟（`~/.d4t/log`、
`~/.d4t/autosave.json`、QSettings），而測試如果寫進真的那一份，開發者下次開
Studio 會被問要不要救回一條測試造出來的 pipeline。所以三個都有具名的覆寫點
（`crashlog.LOG_DIR` / `autosave.DIR` / `BaselineStore(settings)`），而
`StudioWindow` 在 `_running_under_pytest()` 時預設把草稿關掉 —— 有一條測試
專門守那件事。

### 剩下的

P1 九項（UI 七：U5 Build/Tune 兩種模式、U6 抽出圖編輯語意、U7 拆 `widgets.py`、
U8 參數與儀表同欄、U9 階段順序表去掉第二份、U10 scope profile、U11 判定回溯
的入口；UX 二：X3 抽樣試跑、X4 範本庫）與 P2 十三項都沒有動。
**U7 與 U6 是 F90 那把規模的尺正在等的那兩件事** —— 這一輪把六件事放進七支
新模組而不是塞進 `studio.py`，正是因為那把尺在。

---

## F90：三把尺 —— 正確性以外的兩條軸（2026-09-08）

起點是一份專案體檢，而它量出來的診斷是一句話：**這個 repo 的每一道關都在問
「數字對不對」，沒有一道在問「東西多大」或「跑多久」。**

3,442 支測試、三份黃金值、九條卡片不變量、round-trip identity、逐位元組的
決定論 —— 全部長在**正確性**那一條軸上。而另外兩條軸的症狀量得出來：

* `d4t/ui/studio.py` 在 2026-09-02 是 6,761 行、09-08 是 6,942 行，
  **而中間沒有任何一輪是在動它**（`StudioWindow` 同時從 261 個方法 / 386 個
  `self.*` 長到 268 / 393）。沒有人決定要加那些行，它們是漂進來的。
* 「單批 10,000 顆仍然流暢」從 M2 就寫在 README 上，**從來沒有被量過**。
  整條 pipeline 慢三倍，全套測試照樣全綠。

所以這一輪做的不是重構（那被「先把引擎做對」的順序擋著，而且是對的），
是**把兩把缺的尺補上**。三把都是新增檔案，`d4t/` 底下一行都沒動，
**三份黃金值逐項相同**。

### 尺一 · 規模：`tests/test_size_ceilings.py`

天花板的意思不是「不准變大」，是**「變大要有人簽名」**：上限寫在測試裡，
要調高就得在同一個 commit 裡改那個數字並說一句為什麼 —— 而那句話就是 code
review 的內容。凍住五支檔案（`widgets` / `studio` / `recipe` / `inspectors` /
`canvas`）、沒列名的共用 2,200 行，外加四個**不是行數**的指標。

**最有價值的那一格不是行數，是耦合**：`d4t/ui` 裡「按卡片名字分支」的地方
現在是 **23** 個，而它守的是整個專案的賣點 ——「加一張卡，UI 與引擎零修改」。
唯一會安靜殺掉那句話的，就是這個數字慢慢變大。（行數是代理指標：刪一段註解
會讓行數變好看，不會讓 268 / 393 變好看。）

⚠ **指標本身先驗過誠不誠實**：第一版的粗略 grep 量到 49 個，其中有假陽性
（`widgets.py` 的 `setProperty("tone", …)` 是 Qt 屬性、`inspectors.py` 的
`{"subtract": "−"}` 是運算子符號表）。改成 `ast` 只認三種語法位置
（比較、模組級常數、`get_step(...)`）之後是 23 個、零假陽性，而
`INSPECTORS` / `BY_METHOD` 兩張**設計好的註冊表**明確排除 —— 算進去的話這個
指標量到的會是「卡片有幾張」，不是「耦合有多深」。有一條測試守著那個排除
（那兩張表改名的話會紅）。

三個方向都驗過：往 `studio.py` 加 5 行會紅、多一個 `node.step == "cd_measure"`
會紅、**把上限調高而實際值沒動也會紅**（反向測試 —— `CLAUDE.md` 那條
「任何例外清單都要有那支反向的測試」）。

### 尺二 · 時間：`tools/bench.py` ＋ `tests/fixtures/bench_baseline.json`

形狀刻意跟 `freeze_golden.py` 一字不差（工具 ＋ 基準 ＋ `--check` 逐項差異），
理由也一樣：時間欄在 CI runner 上會漂，**一道會隨機變紅的關很快就變成一道
大家學會忽略的關**，所以它是給人跑的工具、不進 CI。

真正的設計重點是**把欄位分成兩種**：

* **寬（時間）** `ms_per_defect_*` —— 容差 2×，只回答「有沒有慢一個數量級」。
* **嚴（結構）** `result_bytes_per_defect` / `cache_files` /
  `cache_bytes_per_defect` —— ±2%。這幾個是**決定性的**：每顆的結果 payload
  變大 20% 講的是「多了一批特徵」，快取存下的份數變了講的是 checkpoint 的位置
  動了。兩件事都跟機器無關，所以它們比時間更值得守。

記憶體刻意量 **payload 不量 RSS**：要回答的問題是「10,000 顆的結果整批留在
記憶體會怎樣」（`run_batch` 回的是一整個 list），而 RSS 量到的是 numpy arena
與行程池，跨 OS 完全不可比 —— 何況家用機是 Windows，連 `resource` 都沒有。

**它跑第一次就推翻了體檢報告裡的兩個數字**：

| | 體檢當時（`recipes/rsem-worst-box.json`）| 這一支（`die_to_die_basic`，有真的影像段）|
|---|---|---|
| 4 workers | 1.45× | **3.75×** |
| 快取 | 零收益（checkpoint 落在 0）| 存下 24 份、每顆 37 KB，但**只換到 1.04×** |
| 10,000 顆 | 沒量過 | **約 8.6 分鐘、結果 payload 約 19 MB** |

所以「平行只有 1.45×」不是引擎的性質，是**那份 rsem recipe 太輕**（影像段只有
一張 load 卡）—— 這正是這支工具刻意挑一份有完整影像段的 recipe 的理由。
留著的新問題：快取結構上是好的（24 份都存下來了）卻只換到 4%，因為這份
recipe 的成本在量測卡（cd / glv）不在影像段。

### 尺三 · I9：藏起來的參數不影響結果

`CLAUDE.md` §3 早就寫著「`show_when` 是**顯示**規則不是驗證規則，卡片自己要
保證用不到的參數不影響結果（`resolve_reads` 也一樣）」—— 而在這之前**沒有
任何東西在守它**。「卡片自己要保證」＝ 人要記得，而 registry 有 91 個參數掛著
`show_when`，光 `roi_reference` 一張卡就 33 個。

現在是自動套用到每一張卡的不變量：26 個 case、7 張卡，兩半都問
（**宣告**不變 —— 藏起來的參數改了 `resolve_reads` 的話畫布會多畫一條使用者
看不到也拉不到的線；**結果**不變 —— feature 與 score 逐項相同）。今天全綠。

⚠ **第一版是空轉的，而且是自己驗出來的**：把「偷讀一個藏起來的參數」這個 bug
放進 `denoise` 去試，**測試照樣全綠** —— 因為影像段的卡根本不產 feature，
`run_defect` 回的 `features` 是空的，於是「結果不變」問的是兩個空 dict 相不
相等。修法是在被測的卡後面接一張 `glv_stats` 讀它吐出來的那條流
（`_recipe_with_probe`），影像變了才會有一個數字跟著變。修完之後同一個 bug
當場變紅，而且訊息指名是哪幾個特徵動了。

（第一次注入還挑錯了地方：`denoise` 預設 `method="median"` 根本不讀
`strength`，所以那個「bug」不是 bug。要驗一條測試會不會紅，注入的東西得先
真的會改變輸出。）

### 順手修掉的四件

1. **`NEEDS_MORE_SETUP` 的兩隻幽靈。** 那張表自己的註解 2026-08-27 就寫著
   「這張表上留一個不存在的 key 沒有任何測試會叫…而這一張目前沒有」——
   補上那支反向測試的當天它就抓到 `roi_template`（F29 併掉）與
   `roi_from_mask`（F74 刪掉）兩列指著不存在的卡。
2. **`test_card_invariants.py` 的檔頭寫著「鎖六條」**，而 I7／I8 早就在檔案裡
   了。改成九條並把三條的說明補上。
3. **`bench.py` 第一版讀錯鍵**：`StageCache.stats()` 回的是磁碟現況
   （`n_files` / `bytes`）不是 hit/miss 計數，於是那兩欄永遠是 0 ——
   而「快取沒在做事」跟「我讀錯鍵」長得一模一樣。
4. **`--check` 以前會先白白量 20 秒**才說「找不到基準」。現在先看基準在不在，
   而且有一條測試用時間證明它沒有先量。

### 這三把尺守不到什麼（明講）

* **分不出好的成長與壞的成長。** 加一張卡讓 `inspectors.py` 多 40 行是健康的，
  `studio.py` 多 40 行通常不是 —— 尺只會說「變大了」，判斷仍然是人的。
* **不會讓設計變好。** 只買到「變大是一個決定」；`studio.py` 真正的拆分還是要
  做，只是不必是現在（而現在它至少不會一邊等一邊長）。
* **反射性上調 ＝ 劇場。** 這是唯一會讓它們失效的方式。

---

## 收尾：F85 / F88 / F89 的計畫書封存，合併回 main（2026-09-08）

三份做完不再改的計畫書搬進 [`docs/history/plans/`](docs/history/plans/)
（CLAUDE.md §4 的規矩），連帶更新十個檔案裡指過去的路徑 ——
`tests/test_docs_links.py` 守的正是那件事。

順手刪掉一個一小時前自己加的死方法：`Frame.label()` 零個呼叫者（挑選器讀的
是 `frame.labels` 那個 dict）。`docs/plans/` 現在只剩真的還在動的那幾份。

**這條分支到此併回 `main`** —— F85 均勻度、F86 使用者回報的四件、F87 圖表
設定十刀、F88 graph builder 六刀、F89 給工程師用的五件。

---

## F89：讓圖表這一塊真的能給工程師用（2026-09-08）

起點是使用者拿去用之後的三句話：「1. 工程師會不會看不懂? 2. Chart setting
預覽圖每次都會太小（不會跟著視窗走）3. Your own charts 可以設計的東西還是
太少」，以及一句「全部一起做」。計畫書 `docs/history/plans/F89-readable-charts.md`。

**1. 預覽：問題不是「太小」，是長寬比是反的。** 量到 390 寬 × 655 高的直條
—— 它會跟著視窗長，但長錯方向。釘住 4:3（`ChartView.ASPECT` 走
`heightForWidth`）、**只有左半捲**（以前拉一個滑桿要往下捲，而捲下去圖就出
畫面了）、右半改成比左半寬、預設尺寸裝得下左半那三塊。

**2. 兩個「會看不懂」的地方。** `box`（一格量測框）跟記號 `Boxes`（盒鬚圖）
撞名 —— 那正是 CLAUDE.md 講的 `bundle`，改成 `Box plot`；選單裡是原始鍵
（`x` 是**框中心的座標**，卻擺在「Across the bottom」旁邊），加一層
`COLUMN_LABELS`，並把量出來的統計量排在幾何欄前面。**只加顯示的字，鍵一個
都不動。**

**3. 規格線。** 製程工程師看任何一張圖的第一個問題是「有沒有超規」，而在這
之前一條線都畫不了。`ref_lines`（`USL=132, LSL=112`），四張預設圖與自己配的
那張共用**一支** `draw_refs`。超出範圍的那一條不畫；熱圖沒有這一格（那張圖
的值是顏色，不是一條軸）。

**4. 跨顆的長表。** `build_lot_frame` —— 一列一顆 defect。這才是真正的天花板
：`build_frame` 是「一顆之內」，所以畫得出來的問題全被鎖在一張影像裡。座標
從 `Dataset.items` 接上來，**`die_x` × `die_y` 配一個統計量當顏色就是 wafer
map**。住在 `Write report`（勾 `lotchart`）。由此掉出來的：`Frame.categories`
從模組層常數變成**每一張表自己的**。

**5. 分面 / 排序 / log 軸。** 分面是 **F88 §8 那句「明確不做」翻案** ——
當時的理由是「會把一張圖變成一頁圖」，而每一格是一個 `<g transform>`，外面
看到的仍然是一張圖、一個檔。共用座標軸是重點。

### 三件 render 出來才看到的

1. **重排在畫刻度之後** —— 長條照新順序擺、標籤照舊順序印。比不排序糟得多。
2. **巢狀 `<svg>` 在 Qt 裡整塊被跳過**（Svg Tiny 1.2 沒有它）。症狀是**寫出去
   的檔案對、Studio 裡的預覽一片空白** —— 正好打破這整個功能的不變量，而且
   是最壞的那個方向。
3. 直方圖的規格線標籤在最右邊有一半跑到框外。

### 既有測試抓到的

* `CUSTOM_BY_MARK` 的雙向測試：`bar_order` 這個名字**在盒鬚圖也讀它的那一刻
  就開始說謊**。改名 `slot_order`（那時它才加上去幾分鐘，代價是零）。
* 逐格試一遍那支：`ref_lines` **有格式**，塞任意字串會被擋下來 → 預覽不動 →
  測試說它沒接上，而那正是它接對了的證據。

---

## F88 第六刀：`Write uniformity` → `Write charts`（2026-09-07）

使用者定調：「改成 write charts」。**動的只有 `label`** —— `key` 仍然是
`output_uniformity`，寫出去的檔名一個字都沒變，所以舊 recipe 照樣開得起來、
不必付任何遷移（CLAUDE.md 那張價目表的最後一列）。

名字該換的理由：F85 的時候它只寫均勻度那四張圖，「uniformity」講得完；F88
之後它還寫一張**使用者自己配的圖**（五種記號、兩條軸自己挑），而那張圖問的
可以是任何一句話。

跟著換的是使用者看得到的字（卡片 help、三條 warning、儀表標題
`Uniformity folder` → `Charts folder`、出貨 recipe 的說明、手冊 12 處）。
手冊最上面加了一行「這張卡以前叫什麼、鍵沒有變」—— 使用者手上可能有寫著舊
名字的筆記。

**沒有動的兩種**：`SESSION_LOG.md` 與 `docs/history/history/plans/F85-uniformity.md`（那是
歷史紀錄，當時就叫那個名字，改掉等於竄改），以及兩處**引用使用者原話**的
註解（「右側 Uniformity folder 直接把預覽的圖放上來好像也很奇怪」）。

手冊的**檔名**也沒改（`USING-UNIFORMITY.md`）：那一份講的是「怎麼看一片區域
均不均勻」，而那件事沒有變 —— 改檔名要動 CLAUDE.md 的索引、目錄樹與守著它們
的測試，換到的只是一個字。

**F88 六刀到這裡走完。**

---

## F88 第五刀：預設起點，以及一支雙向測試抓到的兩個真 bug（2026-09-07）

**§5 那句「打開時一定是一個預設，不是一片空白」做了。** `chart_draw.PRESETS`
五個（住 core 不住 UI —— 它們是「這張圖是什麼」），佔位符 `@metric` 由
`preset_spec(name, frame)` 換成這一顆真的量出來的欄名。

⚠ 這跟第二刀刻意**不**做的「拿第一欄當預設」是兩回事：那個是隨便挑一欄，
畫出來是一團疊在同一點的圓、而且**看起來像設定好了**；這個是一張有名字的圖
（`Two numbers` / `Spread per region` / `Where it is uneven`…），而名字就寫在
那顆膠囊上。一顆都做不出來的時候那幾顆鈕按不下去。

**§14.4 那件補完了：設定的收放要看記號。** `uniformity_charts.applies(key,
kind, mark)` 是唯一的判準，第二層是 `CUSTOM_BY_MARK`（`whiskers` 只有盒子
讀、`map_values` 只有格子讀…）。那張表會跟 `chart_draw` 漂，所以它配著一支
**兩個方向都測**的測試：列了的必須真的改變 SVG，**沒**列的必須不改變。

那支測試當場抓到兩個真的 bug，而它們在那之前**每一條既有測試都是綠的**：

1. `_boxes` 把 `points` 的預設寫死成 `False`，而全域預設是 `True` —— 同一個
   開關對折線有作用、對盒子沒有，而編輯器照樣把那一列顯示出來。
2. `_bars` 沒有走 `fill_attrs`（自己乘了一次 `fill_strength`），於是
   `fill_color` 對長條**完全沒有作用**。

兩個都是「畫面上改不到一個真的會變的東西」。

render 出來才看到的一件：那一排預設用預設的 `ghost` 樣式畫出來是**五個看起來
像標題的字**，不是五顆按得下去的東西 —— 改成 `kind="icon"`（`small_button`
本來就有那個 lever，理由跟 `ColourButton` 的「auto」那一格一字不差）。

**第六刀（卡片改名）停在這裡問**：計畫書寫的是 `Write charts`，但這張卡除了
圖還寫均勻度的摘要數字、`boxes.csv`、疊在影像上的熱圖，而手冊叫
`USING-UNIFORMITY.md`。改 label 是零代價，但挑哪一個名字是使用者的決定
（CLAUDE.md 那張價目表：判準都是「使用者說了哪一句話」）。

---

## F88 第四刀：盒鬚與格子兩種記號；**後半量過之後不做**（2026-09-07）

`box` / `cell` 做了 —— 到這裡「自己配的那一張」的記號字彙就跟四張預設一樣
齊。使用者現在可以拿**自己挑的兩欄**畫盒鬚圖或熱圖（例如 `col` × `region`
的格子，那是四張預設裡沒有的）。

**但這一刀的後半（四張舊圖改走 `chart_draw`）量完之後取消。** 計畫書給它的
價值是「少一份繪圖程式碼」、驗收是「SVG 逐位元組不變」，而那兩件事互斥：

* 把 Box plot 那張跟 `mark=box` 畫的同一份資料拆成 token 比對，相似度
  **0.01** —— `boxplot.py` 用雙引號、屬性順序不同、每個元素換行、標題靠左
  粗體、沒有圖區外框。要逐位元組不變就得把它的序列化原封搬進 `chart_draw`
  再加一個開關，那不是少一份程式碼，是同一份加一個 if。
* 四張圖各自**先算再畫**（分箱／逐欄取平均＋最小平方線／鋪磚）。那幾段是
  資料轉換，不是記號。
* **真正共用的那一半早就共用了**：`_head` / `_frame` / `_xlabels` /
  `_ylabels` / `_nice_ticks` / `_span` / `_axis_names` / `fill_attrs` /
  `_is_dark` —— `chart_draw` 一開始就是 import 它們。

**差點抄成第二份的那條規則**：`_cells` 第一版自己寫了「`t > 0.55` 就印白字」，
而熱圖那邊早就有一條（`_is_dark` ＋ `#ffffff` / `#1f2430` ＋ 粗體 ＋ 放得下
才印）。改成呼叫同一支。順手量到：那條規則在色階中段碰得到 3.2:1 ——
印在連續色階上的字本來就到不了 4.5:1，而色條與 `boxes.csv` 都在，不另外救。

`GLOBAL_APPLIES` 也跟著補：盒子讀 `whiskers` 與填色、格子讀 `map_values`、
線與盒子讀 `points` —— 那幾格在編輯器裡本來對這張圖是收起來的，**而它們在
檔案裡是有作用的**。守著這件事的那條測試（一列說得出它管哪張圖）也從一張
寫死的鍵清單改成直接問規則。

---

## F88 第三刀：折線與長條，外加一次趁還免費的改名（2026-09-07）

`line` / `bar` 兩種記號 ＋ 記號那一排膠囊（`mark_dots` / `mark_line` /
`mark_bars` 三張新圖示）。

**`scatter` → `chart`**（使用者定調「現在改成一個中性的名字」）。加了折線之後
`Scatter` 那個名字就開始說謊 —— 同一格畫得出折線圖，檔名卻寫著 `-scatter.svg`。
而那個鍵**當下還沒有人付過錢**：零份 recipe、零份 fixture 在用它。畫面上現在
叫 `Your own chart`，檔名 `<defect>-chart.svg`。CLAUDE.md 那段 `bundle` 講的正
是反面 —— 名字含糊而改名要付一道遷移，於是拖著，最後混淆的是人。

**測試全綠之後把圖畫出來看，三個 bug 在那一眼裡**（dataviz 的第七步：
驗證器只管顏色，版面要用眼睛看）：

1. **`0` 被當成「沒有值」** —— `row.get(column) or ""`，而 `row` / `col` 的
   第一格就是 0。第 0 列畫出來是灰的，而**圖例上它有顏色**。
   這個 repo 第八個「跑得完、有數字、而且是錯的」。
2. **長條疊在一起畫** —— 只照顏色分群並排，於是同一群落在同一個槽的三格框
   畫在同一個位置，看起來剛好像一張堆疊長條圖（而那正是說明裡寫著不做的）。
3. **數值軸當槽用時 18 個刻度標籤疊成一條黑線**，還印成 `114.81174999999998`。

另外一件搬家：「這種記號用不到的角色不寫出去」從編輯器搬進 `format_spec`
—— 編輯器只是其中一個呼叫端，手寫的 recipe 走的是 `validate_params`。

---

## F88 第一刀 b：區域色不是「重新取步」，是「多取一階」（2026-09-07）

計畫書 §9-4 假設有一組顏色可以同時服務兩件事。量完之後**不成立**：

| 畫在哪 | 要什麼 | 舊那一組對它的底 |
|---|---|---|
| 區域框、模板編輯器、GLV 面板 → **深色的 SEM 影像** | 夠**亮**才看得見 | 全部 ≥ 3:1 ✅ |
| 四張圖 ＋ 散佈圖 → **白紙** | 夠**深**才讀得到 | **八個全部 < 3:1** ❌ |

往下取步救得了紙、**毀掉影像上的框**。所以做法改成跟**深色模式**一模一樣：
同一條色階、不同的一階，各自對著自己的底驗過 —— 不是把一組顏色翻過來。

* `ui.theme.REGION_COLORS`（影像上那一階）**一個字都沒動**。
* `export.uniformity_charts.REGION_COLOURS` 換成白紙上那一階
  （OKLCH L≈0.62、色相位移 ≤ 0.5°）。配色檢查器五項全過。

**身分靠色相與順序，不靠亮度。** 守著兩份不漂的那條測試也跟著換：從「逐字
相等」變成「同色相、同順序、紙上那一階比較深」，另外加一條把「投影機上看得
清楚」寫成數字的（對白底 ≥ 3:1）—— 那正是這一刀要解決的那句抱怨。

順手量過但**沒有動**：`decide_tree.LEAF_PALETTE`（本來就是為紙取的，
3.19～4.75）。看圖時發現、這一刀**沒有修**：盒鬚圖標題靠左＋粗體，另外四張
置中 —— 五張會落在同一頁上，記在計畫書 §12.2。

---

## F88 第二刀：一張圖 = 哪一欄放到哪一個角色上（2026-09-07）

XY 散佈圖 —— 使用者點名要的那一張，也是四張老圖唯一缺的維度（它們每一張都
只問「這**一個**統計量怎麼樣」）。做出來的是三塊：

* `core/pipeline/chart_spec.py` —— **畫什麼**：哪一欄放到 x / y / 顏色 / 大小，
  加一種記號（現在只有 `point`，封閉字彙）。跟 `chart_style`（**長什麼樣**）
  分家，兩支都住在 `pipeline/`、兩支都不 import `export`。
  ⚠ 驗的是**形狀**，不驗欄位存不存在 —— 存 recipe 的時候沒有資料，擋在那裡
  的話使用者換一個 metric 就得先把圖刪掉才存得起來。
* `core/export/chart_draw.py` —— 長表 ＋ 角色配置 → 一張 SVG。類別欄走 band
  軸、數值欄走 linear；類別色**照固定順序發、不循環**（第 9 個併成「其他」，
  因為循環的話兩群同色而圖例上看起來是兩列）；大小跟著**面積**走。
* `ui/graph_builder.py` —— 那一格的編輯器。**選單從資料長出來**
  （`Frame.columns`），不是一張寫死的清單。

**四筆帳**（細節在計畫書 §11）：

1. **預設不勾散佈圖**（新的 `DEFAULT_CHARTS`）。把它加進 `CHARTS` 的那一刻，
   一張全新的卡片預設就會寫一個畫不出來的檔案 —— 三支測試同時紅。
   「可以畫」與「預設要畫」是兩件事，而這個 repo 以前沒有需要分它們的場合。
2. **`ramp` 那一格之前沒有家**（設定編輯器裡漏掉了），而它的值是字串不是
   bool。`chart_settings.CHIP_VALUES` 把那條差別壓成一行，**不另開一張表**。
3. **類別軸不能借 `_xlabels`** —— 那一支把刻度當數字格式化，一個區域名餵進去
   是一句看不懂的 TypeError。兩條軸都要問 scale 自己的 `label()`。
4. **樣本資料要兩個統計量** ＋ 一份 `SAMPLE_SPEC`。少了前者，散佈圖的預覽是
   一條 45° 直線；少了後者，那張分頁永遠停在「pick x and y」，於是每一格設定
   在它上面**看起來都沒有反應**。

**第一版差點犯的那個**：`(pick one)` 而不是拿第一欄當預設。拿第一欄的話，
一張沒有人設定過的圖**看起來像設定好了**，而它畫出來是一團疊在同一點的圓。

---

## F88 第一刀：一列一格框的長表（2026-09-07）

使用者定調方向：「希望他最終能像 JMP 內的 Graph builder 一樣」→「我還是傾向做
graph builder like 的模式」。計畫書 `docs/history/plans/F88-graph-builder.md`。

**這份計畫書的根據是一個觀察**：現在那四張圖已經是那個文法了，只是被寫死成
四個組合 —— 而**熱圖跟散佈圖只差在「顏色綁的是區域還是統計量」**。所以使用者
要的那幾張圖不是新功能，是同一個引擎的三種角色配置。

四個開放問題當場問完（§9）：一張卡一張圖、要 `row`/`col` 兩欄、兩種色階都留但
預設單色、區域色重新取步。

第一刀只做**資料模型**，因為它單獨就有價值：

* `core/export/chart_frame.py` —— 一列一格框的長表。現在 `chart_series` 產的是
  「四張圖各自需要的形狀」（資料跟著圖走），文法要的相反：一份資料、很多種看法。
* **`boxes.csv`**：`defects.csv` 是**一顆 defect 一列**，看不到一張影像裡的那些
  格 —— 這張表現在完全沒有，而它是使用者遲早會要的。
* `row` / `col` 兩欄：每一格框現在只知道自己 `y=270`，不知道自己在第 3 列。
  分群 `cell_edges` 已經在做了（熱圖排格子用的同一支），所以幾乎免費 —— 而有了
  它，「一列一條線」就不是一種新圖，只是「顏色 = row」。

⚠ **列與欄是整張表一起分的，不是一個區域分一次。** 兩個區域擺在同一片場上時，
`epi` 的第 0 列跟 `mg` 的第 0 列要是同一列，不然「顏色 = row」畫出來的線會對不
齊，而畫面上不會說。這一條有測試。

⚠ **算不出來的那一格留白**，不是 0（同 `glv_stats` 的規矩：「0」讀起來是「量到
了而且是零」）；值與位置對不上的那一條**整條跳過**，不畫一半。

---

## F87：圖表設定 —— 一格參數、一個彈出視窗、一個網格編輯器（2026-09-07）

F86 之後跟使用者過了一遍 `Write uniformity` 的面板與產出。他確認六件都要修，
另外問了兩句話，而那兩句話才是這一輪的形狀：

> 「右側 Uniformity folder 直接把預覽的圖放上來好像也很奇怪，有其他建議嗎?」
> 「上面我一開始說的 custom 那些圖表 你有想法該怎麼設計嗎（要向 pear 那樣有
> chart setting）」

後來三個問題的回答是「彈出視窗我 OK」「（外觀那幾列）我覺得要」「投影報告會
需要」，最後一句是「一起排」。

### ① 四個 bug（第一刀）

檔名帶著 `overlay_` 而這幾張不是疊圖；`Which number to plot` 打錯了畫布上
不講；多顆的時候沒有索引頁；報告頁上只有圖沒有數字。第四件最值得記：
**一頁圖回答不了「所以這一顆是多少」** —— 而那個數字早就在 features 裡，
`summary_rows` 只做「找到那一格叫什麼名字」，**不重算**（重算的那一份會跟
CSV 上的分岔，而那一天兩個數字都印得出來）。

### ② 二十五格塞不進一列（第二刀）

使用者要 PEAR 那種 chart settings。攤成 ParamSpec 是二十五列，而 d4t 的參數
面板是一列一格 —— 二十五列排成一條就是一面牆。

`tone` 的 `type="curve"` 是前例：**一個複雜的值裝在一格參數裡，配一個專屬
編輯器**。所以有了 `pipeline/chart_style.py`（parse／format／style_for／
describe，JSON 扁平鍵、**只存跟預設不一樣的**），卡片從 12 格變 7 格。

⚠ 這一刀花最多力氣的地方不在編碼，在**讓四張圖真的吃同一份設定**：盒鬚圖走
`boxplot` 那一支、熱圖的標籤寫死 10px，第一版做完只有兩張吃到 ——
而「字級只對四張裡的兩張有效」是使用者會以為自己按錯的那種 bug。

### ③ 圖搬出儀表（第三刀）

同意使用者那句「好像也很奇怪」，而理由有三個：那個面板窄，四張排成 2×2 每張
只剩約 250×180，**讀不動**；另外三張 Output 儀表都是一份乾淨的「會寫哪幾個
檔」清單，**節奏被打斷**；而那一排儀表回答的是「按下去會發生什麼」，不是
「結果長怎樣」—— **答錯了問題**。

把圖塞進去是繞路不是設計：它們在 UI 裡**沒有別的家**，所以就近放了。
現在那個家是 `ui/uniformity_window.py`（先例：畫布自己的彈出視窗，F8-UI D 案）。
儀表留下讀得動的那一半 —— 檔案清單 ＋ 這一顆每個區域的 CV／斜率 ＋ 一顆
`Preview charts…`。

⚠ 視窗裡**不畫任何一張圖**：`core/export` 產 SVG，`QSvgRenderer` 把**同一個
字串**畫到畫面上。那是 F85 §4.4 的結論，而它是這整個功能最重要的不變量。
搬家的時候順手加了一條**反向**測試（`UniformityPreviewInspector` 的原始碼裡
不准再出現 `build_chart_svg` / `QSvgRenderer`）—— 不然「搬走了」很容易變成
「多了一份」。

### ④ 網格編輯器（第四刀）

`ui/chart_settings.py`。PEAR 那個對話框的價值有一半在**排列方式**：
「刻度上的數字」是一列，它的大小／粗體／顏色**橫著排在同一列上**。攤成三列
的話，讀的人要先在腦裡把它們兜回同一個東西。

所以列怎麼分**住在 core**（`chart_style.ROWS`）—— 那是「這一組設定怎麼分群」，
跟畫面用什麼元件無關（同 `decide_tree.verdict_rows` 的立場）。

兩欄：左邊「四張圖共用的長相」，右邊「這一張自己的字」（一張圖一個分頁）。
一欄疊下來的話右半那一段整個落在摺線底下，而那正是使用者指名要的（標題、軸名）。

做的時候補了 `chart_style.bounds()` —— 檔頭寫著「最小/最大是給 UI 的滑桿與
驗證共用的同一份」，而那句話要成立就得有一個公開的入口，不然 UI 只能自己抄
一份（而抄出來的那一份就是會漂的那一份）。

### ⑤ 「`Profile along` 收起來」原來不需要新機制

這一條在待辦上掛著，理由寫的是「`show_when` 不懂『X 在不在這個 multi_choice
裡』」。**那是錯的**：`param_visible` 從 F37 起對逗號清單做的就是**成員比對**，
註解裡還寫著為什麼。所以那件事是一行 `show_when=("charts", ("profile",))`。

值得記的不是這一行，是**我把一個既有機制記成了一個缺口，然後照那個缺口排了
優先序**（排在最低、標著「可能只改 help 文字」）。

### ⑥ 「你這 heatmap 是否跟原來 PEAR 的不太一樣?」

使用者問的。**是的，四處不一樣**，逐項核對過 `pear/core/analysis.py` 與
`pear/ui/image_view.py`：

| | PEAR | d4t（改之前） |
|---|---|---|
| 每一格畫多大 | `heat_cells()` 鋪到與鄰居的中線 | **一樣**（`cell_boxes` 就是它的移植） |
| 畫在哪 | **疊在影像上**（alpha 178，ROI 框畫在熱色上面） | 白底獨立 SVG |
| 色階 | 藍 `#2563EB` → 琥珀 `#F59E0B` → 紅 `#DC2626` | 六站冷到熱 |
| 多群 | `heat_cells(self._rois, …)` 吃**全部**，共用 vmin/vmax | **只畫第一群** |

**色階那一項是刻意的、而且留著**：PEAR 的規矩是「no group is ever amber」
（琥珀留給趨勢線與色階中點），而 d4t 的 `REGION_COLORS` 第 2 個就是
`#f0b429` —— 照抄的話「第二個區域」跟「中間值」同色。跟趨勢線改成炭黑是
同一個理由。

**多群那一項是我做錯了**，而錯的形狀值得記：我寫在 docstring 裡的理由是
「兩群的框疊在同一張 (x, y) 上，後畫的會蓋掉先畫的」—— 而**那個問題只在
「一群鋪一次」的做法下才存在**。PEAR 是把全部 ROI 丟進同一次 tiling，中線由
全部的框一起決定，於是每一格各佔各的位置，根本不會互相蓋。
**我先製造了一個問題，再用「只畫第一群」去繞開它，還把繞路寫成了設計理由。**

使用者：「都按照 pear 依樣」。於是兩件都做了：

* **一起鋪一次**，色階跨區域共用 —— 而那個代價**圖上要看得到**
  （右下角 `one colour scale across N regions`）：不然兩個區域各自最紅的地方
  會被讀成一樣紅，而它們可能差一整個量級。
* **疊回影像上**：新的 `Step.overlay_heat` hook（跟 `overlay_marks` 同一條
  界線 —— 卡片交、UI 畫）＋ `ImageView.set_heat` 那一層，畫在框與標記
  **底下**（框的用途是「這一塊的顏色是從哪一格量來的」，被蓋掉就沒了）。

⚠ 這一刀最重要的一行是 `export.uniformity_charts.heat_tiles`：**磚與顏色只有
一個出處**，寫出去的 SVG 與疊在影像上的那一層都問它。抽出來之前 `_svg_map`
自己算一份、疊圖再算一份 —— 那正是「畫面上的圖跟報表裡的不一樣，而兩張都畫
得出來」的做法。同理 `_heat_hex` 改成公開的 `heat_hex`（影像上那條色條也問它）。

### ⑦ 即時預覽，以及它一口氣抓出來的四格死設定

使用者：「Chart setting 我是希望能支援即時 preview（在編輯器內就可以預覽）」
「暗色模式下 preview chart box plot 的表示會跟其他人不一樣」。

**暗色那一條的病根是「沒有底」**：另外三張的 `_head()` 會畫一塊
`<rect fill='#fff'/>`，而 `build_boxplot_svg` 沒有 —— 在報表的白色頁面上看不
出來，但圖的視窗用主題色當底，於是暗色主題下那張圖是**透明**的，深灰的字落在
近黑的底上幾乎看不見。補的是**底**不是主題：這四張會被寫進 HTML、貼進投影片，
那些地方是白的，四張一致才是重點。

**預覽本身不難**（每個分頁底下一張 `ChartView`，任何一格改動就重畫），
難的是它逼出來的那條測試：

> `test_every_editor_moves_the_preview` —— **逐格動一下，然後問四張圖有沒有
> 至少一張變了。**

它一口氣抓出**四格會動但什麼都不會發生的設定**：

| 那一格 | 真相 |
|---|---|
| `Name of the value axis` | 預覽直接叫 `chart_style.style_for`，**少了住在卡片上的那一半**（這張圖預設叫什麼、值那一軸的名字落在哪一軸）。也就是**預覽跟輸出走了兩條路** —— 這整個功能最貴的那種 bug，而它就出現在我自己寫了三次「只能有一個出處」的地方 |
| `Whiskers on the box plot` | **沒有任何程式碼讀它**。F87 第二刀的 commit 訊息自己寫著「字級只對四張裡的兩張有效是最難發現的那種不一致」，而我只接了字：線寬、記號大小、鬚，盒鬚圖一個都沒吃到 |
| Box plot 的 `Bottom / Side axis name` | 那張圖根本不畫軸名 |
| Box plot 的 `Ticks across`、熱圖的兩個軸名 | **不適用**（類別軸沒有刻度數；熱圖兩軸是影像位置）—— 照 CLAUDE.md 那條，不適用的要收起來，不是攤在那裡讓人猜 |

前三格補上了（`chart_style_for` 收成 UI 這一側唯一的入口、盒鬚圖吃線寬/記號/
鬚/軸名/yticks，而且**預設值下逐位元組不變**因為是按比例縮放既有常數），
第四類用 `export.uniformity_charts.PER_CHART_APPLIES` 收起來。

值得記的是**這條測試的形狀**：它不問「某一格有沒有效果」（那要一格一格想），
它問「**每一格都有效果嗎**」。前者要人記得補，後者加一格設定就自動守著。
同一個形狀在這個 repo 已經有兩條（`ALLOWED_ERRORS` 的反向測試、卡片庫順序），
這是第三條。

### ⑧ heatmap 的「框大小怪怪的」＝ PEAR 的 `equal cells`

使用者：「不用跟影像一樣大或比例一樣沒關係，他就是示意圖，但目前顯示上會怪怪
的 那個 heatmap 框大小」→「heatmap 裡面的 equal cell（像 pear 那樣）」。

**答案就寫在 PEAR 的 docstring 裡**（`_paint_map_grid`）：

> *Cell edges taken literally sit midway between neighbours, so an uneven
> pitch — or one missing ROI — gives neighbouring cells visibly different
> areas, and **area is not something this chart is measuring**. On the lattice
> every ROI gets an identical tile, which is what a **die map** looks like…*

而 PEAR 那個 `equal cells` 的 checkbox **預設是開的**。我移植的是它關掉時的
那一支，還額外加了等比例置中 —— 兩個決定疊起來就是使用者看到的：格子大小不
一、而且兩側大片空白。

改法：

* `heat_lattice()` —— 回**槽位**（第幾欄第幾列）而不是像素，畫圖那一側把圖區
  切成 `欄數 × 列數` 鋪滿。**刻意不保長寬比**（它是示意圖，不是影像的縮圖）。
* `equal_cells` 進 `chart_style`，**預設 True**；關掉回到照實鋪。
* `map_values` —— 每一格裡印出值，**放得下才印**（印一半的數字比不印糟）。
  兩種鋪法用同一套規矩，不然那一格會「有時候有反應」。
* ⚠ **疊在影像上的那一層永遠照實鋪** —— 它畫在影像上，位置要對得起那張圖。
  拉成格子的話顏色會落在錯的地方，而畫面上看起來完全正常。有一條測試盯著
  `overlay_heat` 裡不准出現 `heat_lattice`。

兩支共用 `_heat_values`（值→顏色、跨區域共用的 lo/hi），所以顏色只有一個出處。

順帶：`test_every_editor_moves_the_preview` 這次沒抓到新的死設定，但抓到兩個
**測試自己**的假陰性（沒 show 的分頁停在最小寬 → 熱圖一格只剩 20 px，於是
「印出值」看起來沒反應；以及樣本 12 欄太密）。樣本因此縮成 3×3 兩群 ——
那也讓真正的預覽變得看得懂。

### ⑨ 「report 的 box plot 跟 Uniformity 能整合嗎」

使用者問的。**合成一張卡不行**（一個點是什麼不一樣：`Write report` 一個點是
一顆 defect、`Write uniformity` 一個點是一格框，而 F50 刪掉 `output_band.py`
就是因為「框的意思是『這幾個是一組』，真相卻是『跑的時間不一樣』」）。

**但「讓兩張圖長得一樣」是現成的缺口**，而且是我自己留下的：兩張卡畫的本來
就是同一支 `build_boxplot_svg`，我在 F87 第二刀給了 `Write uniformity` 一格
`look`，卻沒有給另一張。於是同一份投影片裡兩張盒鬚圖的字級、線寬、鎖定範圍
都不一樣，而畫面上沒有任何線索說為什麼。

* `Write report` 加一格 `look`（同型別、同編輯器、各存各的）。
* **style 的解析搬去 `export.uniformity_charts.resolve_style`** —— 它以前住在
  `OutputUniformityStep._style_for` 上，於是所有人（寫檔的卡片、圖的視窗、
  設定編輯器的預覽、現在還多一張報表卡）都得去 `get_step("output_uniformity")`
  繞一圈。那筆帳已經付過一次：預覽少走了它，`Name of the value axis` 那一格
  在畫面上完全沒有反應。搬完之後繞路就沒有了，而且順手補上盒鬚圖的
  `value_name → ylabel`（以前四張裡只有三張吃到）。
* **編輯器由卡片決定長什麼樣**：`Step.chart_kinds(params)`（要開哪幾個分頁）
  與 `Step.chart_words`（有沒有「每張圖自己的字」）。`Write report` 是
  `[box]` ＋ `False` —— 它一次畫好幾張盒鬚圖，一組標題會套到五張上。
* 同一條規矩再往前一步：`export.GLOBAL_APPLIES` 把**不適用的全域設定也收起來**
  （只畫盒鬚圖的卡片不必看到「直方圖切幾根柱」「熱圖的每一格一樣大」）。
  ⚠ **收起來不等於清掉** —— 值照樣 round-trip，把 Heat map 取消勾選再勾回來，
  設定要還在。

### ⑩ 「底色可以設定嗎」→ 不能，一個都不能

使用者：「histogram 的底色，例如直方圖或盒鬚圖的底 或 Position profile 的圓圈
底顏色可以設定嗎?」查完的答案是**一個都設不到**：`point_color` / `line_color`
管的是**線**，而 profile 的圓圈本來就是空心的（`fill='none'`），所以那一格設了
只改邊；柱子與盒子的填色是區域色配一個寫死的 opacity。

補了三件，跳過背景色（使用者：「背景色不用改沒關係，都預設白色」）：

* **`fill_strength`** —— ⚠ **是一個倍率，不是一個絕對的 opacity。** 每一種圖
  自己那個淡度是設計過的（柱 0.45、盒子 0.18 —— 盒鬚圖上的墨水本來就多），
  一格絕對值會把那個關係抹平，而且**沒有一個值同時等於今天的兩個**。倍率
  1.0 就逐位元組不變（`output_report` 的盒鬚圖沒給 style），有測試盯著。
* **`fill_color`** —— 空 = 跟著區域色（同 `point_color` / `line_color`）。
* **`point_fill`** —— profile 的圓圈填滿。空心在點多時看得到重疊，實心在投影
  片上看得見。

### ⑪ 開關改成一排兩顆膠囊（使用者：「like GLV card」）

使用者：「如果可以也能以膠囊方式呈現(like GLV card)」。這是 F68 那條規矩搬進
這個對話框，而理由一字不差：**勾選框把「另一個選項是什麼」藏起來了**。
`Whiskers` 不打勾會變成什麼樣子？打勾的人心裡要自己補一張圖。

七個開關 × 兩顆 = 14 張新的 chip 圖示（`ui/glyphs.py`，同一套共通文法：
一排裡的每一顆共用同一個底、差別做在形狀不做在粗細）。**兩顆都要說得出自己
是什麼** —— off 那一顆不是「不要」，是它自己那個樣子的名字（`Box only` /
`With whiskers`、`Count` / `Share`、`True to scale` / `Same size`）。有測試守著
這條，包含「`not ` 不准出現在 off 那顆的字裡」。

⚠ 兩個踩到的：

1. **`ChoiceChips.set_text` 不發訊號**（刻意的：載入 recipe 不該被當成使用者
   改了），而 `QCheckBox.setChecked` 會 —— `BoolChips` 要長得像 QCheckBox，
   那條差別就得補平。沒補的症狀是**即時預覽對每一顆膠囊都沒有反應**，而
   `test_every_editor_moves_the_preview` 當場抓到（那條測試這一輪第三次派上
   用場）。
2. **`_ChipFlow.sizeHint` 講的是「最寬的那一顆」**（對一排十幾顆的統計量膠囊
   是對的：它本來就要換行），於是兩顆的那一排被排成兩行 —— 同一個問題的兩個
   答案分成兩行讀起來像兩件事。`BoolChips` 自己把兩顆的寬度加起來當下限。

**例外只有那兩個粗體旗標**（`tick_bold` / `axis_bold`）：它們是「Tick values：
大小｜粗體｜顏色」那一列裡的**一個屬性**，不是一個「要哪一種長相」的問題，
而兩顆膠囊塞進三欄的格子會把整排的對齊撐爛。名字寫死在測試裡，所以新加一個
bool 不會安靜地混進那張例外表。

### ⑫ 「Icon 很漂亮，但有全應用進去嗎」—— 兩個一眼看出來的

使用者兩句話，兩個都中：

**①「有全應用進去嗎」→ 有一格被登記了兩次。** `point_fill` 同時在
`chart_style.ROWS`（「Data points：半徑｜**filled**｜顏色」的勾選框）與
`BOOL_CHIPS`（「Markers：Hollow / Filled」那一排膠囊）。後放的那個把前面的
從 `self.globals` 蓋掉 —— 於是那個勾選框**看得到、按得下、什麼都不會發生**。
我加膠囊的時候忘了把它從網格拿掉。

配一條測試：`ROWS` 與 `BOOL_CHIPS` **不准有交集**，而且兩張表加起來要蓋滿
`GLOBAL_KEYS`（一格設定只能有一個家，而且一定要有一個家）。

**②「不同 chart 可設定的應該要不一樣?」→ 對，而畫面上沒有說。**
`GLOBAL_APPLIES` 早就知道哪一格影響哪幾張（不適用的整列收起來），但四張都
勾著的時候每一列都在 —— 使用者在 Box plot 分頁上看著「Histogram bar height」，
只能自己猜。現在每一列底下掛一行淡的小字說出它影響哪幾張。

⚠ 第一版把那行掛在**每一列**上，結果是「Heat map cells / Heat map」「Box plot /
Box plot」—— **標題已經說了的就不要再說一次**，因為噪音會讓真正需要那行的幾列
（`Markers`、`Ticks across`）也被跳過不讀。現在只有四列有尾巴。

### ⑬ 一張**檔名**的例外清單，放過了它自己要擋的那件事

CI 紅在 `test_the_short_one_is_only_used_on_the_image`：熱圖色條用了
`format_feature_value_short`，而那支的邊界是「只有畫在影像上的標記用它」——
色條就畫在影像上，所以那個用法是對的，把 `widgets.py` 加進清單就好。

**但去查的時候發現清單本身是壞的。** 它比對的是**檔名**：

```python
assert users == ["inspectors.py"]
```

而 `inspectors.py` 早就在表上 —— 於是我這一輪在**同一個檔案裡**新增的那張
**面板小表**也用了短版，測試照樣綠。那正是這條規則明文禁止的事
（「表格與面板一律走 `format_feature_value`」），而且它有實際後果：面板上印
`CV 1.8`、CSV 上是 `1.8342`，同一顆 defect 的同一個數字在兩個地方不一樣。

清單改成**函式**層級（`{檔名: {函式名}}`，走 AST）。
**一個 6,700 行的檔案通過一次審查，不代表它以後每一行都通過。**
（同一個形狀在 CLAUDE.md 裡已經有一條：`ALLOWED_ERRORS` 那張表要配一支反向
測試，不然它就是一張只會變長的紙。這次是另一種爛法 —— 顆粒度太粗。）

### ⑭ 一個把測試掛死的坑

新的 UI 測試檔在 fixture 裡才 `import studio`，而 `conftest` 那支關掉「關閉時
確認存檔」的 autouse fixture 是 `sys.modules.get("d4t.ui.studio")` ——
那時候它還看不到那個模組。於是 `win.close()` 停在一個沒有人按得下去的
QMessageBox 上，測試**永遠跑不完**（不是失敗，是掛住）。
`studio` 一律在模組層 import，理由寫進那支測試的 fixture 了。

---

## F86：使用者拿去用，四件事回來（2026-09-07）

F85 併進去之後使用者實際跑了一遍，回報三件加上我自己欠的兩件。
**四件全部是「畫面上看不出來」的那一類。**

### ① 「output 預覽有，但跑完沒 output」—— 不是 bug，是沒有回音

工具列那顆最大的鈕是 **`Run trial`**，而它**刻意不寫檔案**（F16 Stage 5c，
使用者自己定的：「試跑不寫，只有整批才寫」—— 每拖一下門檻就覆寫一次檔案
是不可逆的）。要寫檔的是它右邊箭頭裡的 `Run all & write`。

那個決定是對的。錯的是**它沒有說**：畫布上有一張 Output 卡、它的儀表列著會
寫哪幾個檔，按下去之後什麼都沒發生，而狀態列只說「Run finished」。

所以行為一個位元都沒改，只多一句話 —— **而且指名那個動作**：

> Run finished: 24 defects … · Trial run - nothing written.
> Use "Run all & write" (the arrow beside Run trial) to run every defect
> and let the 2 Output cards write.

只在**真的有啟用中的 Output 卡**時才講：一句永遠都在的提示會變成沒有人讀的字。

### ② 大圖疊 Golden Cell 卡住 —— 使用者要進度條，量完發現該修的是別的

使用者：「7680*7680 …… 在載入 image 讓他算 golden cell 時很常會卡一陣子才算完
（希望可以加入進度條）」。

量出來是 **130 秒**，而且 `build_golden_cell` 跑在 **UI 執行緒**上
（`template_dialog.load_image`）—— 那不是「卡一陣子」，是視窗死兩分鐘。

**99% 在 `choose_origin` 一支裡**：281 個候選相位 × 把影像整張疊一次。

| 影像 | 幾格 | `choose_origin` |
|---|---|---|
| 1024² | 441 | 0.6 s |
| 4096² | 7 225 | 28 s |
| 7680² | 25 440 | **130 s** |

**做出來、然後拿掉的那一版**：只用中間 1024 格搜相位 —— 2.2 秒，快 60 倍。
但實測**它會改變答案**：2304² 的接觸孔陣列上全搜尋挑 `(42, 24)`、看窗的挑
`(42, 0)`，**y 差半個 cell**；拿整張圖回頭評分，窗選的銳利度低 1.5–2.4%。
那不是平手，是不同的晶格相位 —— 而使用者在 Golden Cell 上標的每一個區域都掛
在那個相位上。**跑得完、有數字、而框落在別的地方。** 拿掉了，理由留在
`period.py` 那個常數的位置上，給下一個想「抽樣就好了吧」的人。

速度改從**兩件逐位元組相同**的地方拿：

1. `golden.stack_cells` 的平均改 reshape —— 原本 `np.stack([每一格])` 的中間
   陣列在 7680² 上是 **469 MB**，配一次 0.33 秒 × 281 次；
2. `choose_origin` 不再先把影像升成 float64 再疊。

**130 s → 16.7 s**，而 `tests/test_period_golden.py` 拿舊寫法當參照實作，
4 種尺寸 × 3 種週期 × 3 個 origin 全部逐位元組相同（黃金值三份也沒動）。

進度條照樣做了 —— 那 17 秒仍然要看得到、停得下來。`build_golden_cell` 收一個
`progress(stage, done, total)` callback（**core 不得 import Qt**，所以畫面長
什麼樣由 UI 決定），回 `False` 就取消。UI 那邊是 `QProgressDialog` +
`setMinimumDuration(400)` —— **不必自己發明「多大張才算慢」的門檻**，快的那些
根本不會跳出來。

三個細節寫進測試：取消**不是失敗**（上一張模板留著，不出紅字）、
`setValue` 會處理事件所以**重入要擋**、取消時回目前為止最好的相位而不是 `(0,0)`。

### ③ 出貨的 recipe 只有圖，拿不到數字

使用者問「結果要在哪看」的時候我才發現：`one-image-uniformity` 只有
`Write uniformity`，四張 SVG 加一頁 HTML，而 `cv_pct` / `slope_x` 那些數字
**沒有任何檔案裝得下**。一份「看均勻度」的 recipe 拿不到均勻度的數字。

加了一張 `Write report`（勾 `table` + `recipe`），**folder 跟圖同一個** ——
分兩個地方等於使用者要找兩次。測試釘住那個相等。

### ④ 手冊漏了使用者第一個會看到的東西

`docs/USING-UNIFORMITY.md` 我只寫了參數格，漏掉卡片**最上面**那排
`What to measure` 的三顆快捷鈕 —— 而正確答案是按 **`Odd box out`**
（它會幫你把 `Boxes in the region` 設成 `each box`，也就是整份手冊
「最重要的一句話」）。順便補上：`Write to` 要填完整路徑（出貨的是相對路徑，
會落在啟動 Studio 的地方旁邊）、新增一節「跑完之後結果在哪」、
以及四條新的「症狀 → 先看哪裡」。

### 這一輪的通則

**「使用者定的行為」與「使用者看得懂」是兩件事，而後者也是驗收標準。**
①③④ 三件的行為都是對的 —— 試跑不該寫檔、圖跟數字本來就分兩張卡、快捷鈕
一直都在。壞掉的全是**它們有沒有說出來**。推廣鐵則那一句「任何讓他們看不懂
的設計都是 bug」在這一輪一天之內兌現了三次。

而 ② 是另一個通則：**使用者說的是症狀，不一定是該修的地方。** 他要進度條，
量完發現 99% 的成本在一支函式配置又丟棄同一塊 469 MB 的記憶體上。進度條也
做了，但如果只做進度條，那就是替 130 秒買了一塊遮羞布。

---

## F85：PEAR 的均勻度搬進來 —— 一格參數、四張圖，以及三個「我原本說錯了」（2026-09-07）

使用者：「我想將 PEAR 專案的功能移植進 d4t studio 讓他成為一張卡片」。
四輪問答把範圍收成：**不用手放 ROI**（接現有的 ROI 卡）、**主要看區域均勻度**、
**要 PEAR 那四種圖**、**外觀設定先做最小的一批**。

### 做出來的東西

| # | 東西 | 代價 |
|---|---|---|
| 1 | `algo/uniformity.py`（vendored from PEAR，~200 行）| 新模組 |
| 2 | `glv_stats` 多**一格** `report`（range / range_pct / cv_pct / slope_x / slope_y，預設後三個）| 一格參數，而且 `show_when` 綁 `each box` —— 用 pooled 的人看到的格數**一格都沒變** |
| 3 | `export/uniformity_charts.py` —— 四種圖的 SVG | 新模組 |
| 4 | `output_uniformity`「Write uniformity」| Output 段第四張卡 |
| 5 | `Open image…` —— 第四個 Input 入口 | `INPUT_SOURCES` 一列 |
| 6 | `recipes/one-image-uniformity.json` | 出貨第二份 recipe |
| 7 | CLI 認得資料夾與單張圖 | 一支 `_open_input` |

### 一、**沒有新開量測卡** —— 而我原本說「結構上做不到」

第一版計畫書（commit `4763e96`）的結論是開一張新的 `uniformity` 卡，理由寫的是
「`MultiSourceStep.run` 的迴圈一次只給子類一個區域，所以跨群比較**結構上做不到**」。

使用者問了一句「**是有必要新開卡嗎**」，而那個理由站不住，兩個錯：

1. **子類可以覆寫 `run()`**，而且乾淨的寫法是「先 `super().run()`，再多跑一段」。
   那是「基底預設不做」，不是「做不到」—— 我把前者寫成了後者。
2. 更嚴重的是**援引錯了規矩**。我用 F19 的「改變『量得出什麼』的選擇是岔路，
   不是 method」，但那條的判準是**「這個參數問的是使用者的樣品，還是問軟體」**
   —— 而 `cv_pct` 問的跟 `glv_stats` 已經在吐的 `_typical` / `_outlier` 是
   **同一個樣品、同一組框、同一批像素**。它不是岔路。

同一輪使用者對兩群比較（η²／Cohen's d）說「不要」——那本來就是我提議的，
而它一走，連覆寫 `run` 的需求都沒有了。

**判準留給下一次**：折進去 vs 新開卡，決定性的一條是「使用者要接幾次線」。
兩張卡＝同一個 ROI 拉兩條線、設兩次 `metrics`，而那兩份**可以設得不一樣、
畫面上看不出來** —— `glv_stats` 自己的 docstring 早就罵過同一件事
（舊 `roi_compare`）。

### 二、**兩份繪圖程式碼收成一份** —— 因為「QtSvg 不是相依」是錯的

計畫書寫著：畫面上一份 QPainter、檔案裡一份 SVG，那是鐵則 1 的直接後果；
而 core 產 SVG、Studio 顯示那條路走不得，理由是「`QtSvg` 不是相依」。

**`QtSvg` 就裝在 `PySide6-Essentials` 裡**（`pip show` 列得出 `QtSvg.abi3.so`），
`requirements.txt` 的 `PySide6>=6.5` 早就帶著它。我把「Qt 的一個獨立模組」
當成了「一個獨立的套件」。

所以現在是一份：core 產 SVG，`UniformityPreviewInspector` 用 `QSvgRenderer`
把**同一個字串**畫到面板上。原本風險表的第一行（「兩份會漂」）因此不存在了。
賠掉的是 hover —— `GlvInspector` 的直方圖本來也沒有。

⚠ 一份帶來一個**新的**坑，當場踩到：每一支 `_svg_*` 把圖區夾在
`max(80, height − 上下留白)`，於是格子不夠高時內容比 viewBox 高，
**SVG 把超出的切掉**。實測 126 px 高的格子把斜率那一行（整張圖唯一的數字）
切掉一半，**而圖看起來完全正常**。解法是 `MIN_WIDTH`/`MIN_HEIGHT`：
**夾住尺寸，不夾內容**。

### 三、圖住在 `Write uniformity` 的儀表，`GlvInspector` 一行沒動

計畫書寫的是「四種圖是 `GlvInspector` 多一排切換」。動手才發現儀表面板只有
**一個**分頁鈕，沒有「同一張卡好幾種看法」的機制；硬加會多一排**只在儀表裡
有意義**的按鈕 —— 那個選擇既不進 recipe、也跟任何一格參數對不起來。

而「畫哪幾張」**本來就是一格參數**（`Write uniformity` 的 `charts`）。
所以圖住在那張卡的儀表上：上半是「會寫哪幾個檔」（Write KLARF 那條硬規則），
下半就是那幾張圖本人。

### 四、測試抓到的六個，每一個都是「跑得完、看起來正常」

| 抓到什麼 | 誰抓的 |
|---|---|
| **函式名跟模組名撞了** —— `from .uniformity import uniformity` 把模組換成函式，26 條同時紅（跟 F84 的 `leaf_hex` 同一種形狀）| 既有測試 |
| **我以為守著 4 倍門檻的那條測試沒有在守** —— 把 4.0 改成 1.0 整份全綠，因為等距那組被 `i < 1` 擋掉了，走不到倍率那一行 | **突變驗證** |
| `configuration_issues` 讀了沒補預設的 params，對一個正常節點說「你什麼都沒勾」| `test_output_convergence`（registry 全掃）|
| 手搭的 Recipe **不會自己水合區域線**，GLV 安靜地退回「量整張圖」| 自己寫的測試（斷言對不上）|
| 插新 Inspector 時**把 `CharPreviewInspector` 的 `_lines` 整段偷走** | `test_ui_panels_pr2` |
| 小面板把圖切掉 | 肉眼看 PNG |

六個突變（斜率的 100、抖動的 4 倍門檻與 `i >= 1`、容差取階梯中間、格子邊界
取中線、丟 NaN）現在全部抓得到。

### 五、順手修掉一個文件漂移

`CLAUDE.md` §6 與 `README.md` 的來源表都寫著 PEAR 提供「η²／Cohen's d」，
而整個 repo **grep 不到** —— 它進來過（`docs/plans/F11` 留著墓碑：
`algo/stats.py`，85 行），因為零個呼叫者被當死碼清掉，兩份文件沒跟上。
第一版計畫書打算搬回來讓表變成真的；使用者說不要，**所以修的是文件那一邊**。

⚠ 反過來的一件事也記著：計畫書原本要把 `uniformity.py` 寫進
`ui/scope.py` 的「不准刪的孤兒模組」表。**做完之後那句話不成立**（它有兩個
真的呼叫者），寫上去會是一句**指著錯東西的說明** —— 那比沒有更糟（F84 的
「搬家的時候理由要跟著搬」的反面）。真正只有兩張圖在用的是
`cell_boxes` / `profile_by_position` / `cluster_positions` / `cell_edges` /
`jitter_tolerance` 那五支，而那句話寫在 `tests/test_uniformity.py`。

### 沒做（講清楚才不會被當成漏掉）

手放 ROI（使用者第 1 點明說不用）、ROI JSON 匯入匯出、η²／Cohen's d
（「不要」）、Tukey 離群格數（`glv_boxes_over_k` 已經在答同一句話，而
`_outlier` 與 `_outliers` 只差一個字母、會在同一份 CSV 上並排）、
外觀設定第二批（字級／粗體／顏色／點半徑／線寬 —— PEAR 那個對話框的價值
有一半在**排版**，而排版要等到知道實際有幾列才排得出來）。

**黃金值三份逐項相同**（既有的 fixture recipe 都走 pooled，連算都不會算）。

---

## F84：一道 lint 關、一個承重假設的症狀、pack 裡的 378 MB，以及兩份沒併進來的東西（2026-09-03）

使用者看完專案體檢之後說「做那 3 件事」。三件都做了，而**每一件都在做的過程中
變成了另一件事**——

### ① ruff：第一次跑就抓到六個真的

這個 repo 有 3,126 支測試與三份黃金值，但**沒有任何東西看過「這個名字存不存在」**。
`ruff check` 掃 `d4t/` `tools/` `fab_probe/` 的第一次就是：

| 抓到什麼 | 為什麼沒有人發現 |
|---|---|
| `algo/template.py` 的 `__all__` 列了一個不存在的 `roi_in_patch` | 沒有人寫過 `import *` |
| `klarf_core` / `step.py` / `_util.py` 三處用了**沒 import 的型別**（`Optional`／`Sequence`／`Any`）| `from __future__ import annotations` 讓它們在執行期不求值 —— 91% 的型別標註**從來沒有被驗證過**，它們是註解不是保證 |
| `ui/tree_scene.py` 的 `leaf_hex` **被自己的舊版本遮蔽** | 兩份的調色盤**現在剛好一樣**。F29 C0 那句「畫面與報表的顏色必須是同一個」因此是死的 —— 而它會在有人動 `LEAF_PALETTE` 的那天才發作 |
| 同一輪留下的 14 行 `OPS` 說明，掛在一個不相干的常數上 | F29 C0 搬了程式碼、沒搬理由。讀的人會以為那段在講顏色 |
| `tests/` 裡一條 `%` 沒跳脫的 assert 訊息 | 那條 assert 一旦成立，使用者看到的是 `ValueError` 不是訊息 |

**通則：搬家的時候，理由要跟著程式碼一起搬。** 留在原地的說明不會變成孤兒 ——
它會變成一句**指著錯東西的說明**，那比沒有更糟。

⚠ **`--fix` 不能盲收。** 它自動刪掉 `ingest/pair_source.py` 一個「這個模組自己
沒用到」的 import，而那是**轉出口**：`studio.py` 與 `__main__.py` 都在用
`pair_ingest.columns_of(...)`。F401 問的是「這個檔案有沒有用到」，答不出
「別人有沒有透過這個檔案用到」。抓到它的是測試，不是我。

設定在 `pyproject.toml` 的 `[tool.ruff]`（**刻意不開 E501 與 UP**，理由寫在那裡），
CI 多一個獨立的 lint job（幾秒，不跟著 3×矩陣跑三次）。`tests/` 不掃 ——
UI 測試刻意 lazy import Qt，ruff 在那裡報 1,217 條誤報，納進來只會得到一道
大家學會忽略的關。

### ② FAB-VALIDATION #7：問不到，但可以讓它出聲

那條假設（EBI patch 是不是以 defect 為中心裁的）我問不到機台工程師。但它真正
的問題不是「還沒問」，是**錯的時候完全沒有症狀** —— 固定格線裁的話
`align_off` 恆為 0，十字與框完美重合，報表**看起來最漂亮**。

所以做的是讓它出聲：`steps/align_to.degenerate_offset_note()` ——
整批的 `align_off_*` 全部貼在 0 上就回一句話，`output_char` 跑完講出來。
判準是**分布不是單顆**（一顆是 0 很正常，幾十顆全是 0 不是），而且那句話
**刻意不說「你的資料壞了」**：同一個分布有兩個解釋（機台每顆都瞄得極準／
固定格線裁），資料上分不開，分得開的只有那一句話。所以它做的事是**把問題
送到使用者眼前**，不是替他猜一個答案。

⚠ 那組測試的最後一條問的是**接線**（`run_batch` 之後那句話真的在
`bctx.warnings` 裡），而不是只問那支純函式 —— F83 那三個 bug 全部是
「model 對了、而那個動作從來沒有被接上去」。驗過它會紅。

### ③ bundle：病根是壓縮，不是產得太勤

08-24 記下的兩條路（① 移到 Releases ② 少產幾次）**一條走不通、一條不必要**。

* **Releases 走不通，而且是測出來的**：`curl -I` 一個公開 repo 的 release 附件，
  回的是 `Content-Disposition: attachment` + `application/octet-stream`，而且
  302 轉去另一個網域。瀏覽器**直接下載**，看不到文字 —— 而下載正是公司機
  擋掉的那件事。使用者的條件只有一句：「我只要能在 github 的網站可以複製
  bundle 的文字就可以」。
* **真正的病根是那個布林值。** 同一次「改一支模組再重產」實測：

  | 格式 | 單份 | 存兩版後 pack | 第二版多花 |
  |---|---|---|---|
  | lzma+base64（舊） | 2,253 KB | 3,404 KB | **1,702 KB** |
  | 純文字（現在） | 7,631 KB | **2,493 KB** | **1 KB** |

  1700 倍，**而且純文字版存進 git 之後還更小** —— git 自己會 zlib 壓 blob，
  「壓過再 base64」剛好把它能壓的都拿掉了。搬運那一端一個字都沒變。

順手發現的第二件事：**AGENTS.md 那個「88 MB / 46%」已經嚴重過期**。直接量：
clone 的 `size-pack` 是 **385.58 MiB**，`filter-repo --path bundle/ --invert-paths`
之後剩 **7.23 MiB** —— **378 MB（98%）**是這一個檔案的歷史副本。曲線是指數的，
所以「先記錄、之後再說」每拖一天都更貴。

第三件：**`docs/NO-GIT-SETUP.md` 上那條公司機的程序已經壞了兩個星期而沒有人知道。**
它寫著「打開 blob 頁 → 按右上角的複製鈕」，而 GitHub 的檔案瀏覽頁在 1 MB 以上
不顯示內容、那顆鈕會消失 —— 這一包 08-19 就超過 1 MB 了。改成 raw 網址。
**一份寫下來的程序，在一台救不了的機器上，可以安靜地失效。**

### ④ 順手救回一份沒進 main 的操作手冊

要跑 G 之前先查了分支，發現一件比 G 更該先處理的事（見下）。而在確認那 3 個
未併入的分支能不能刪的時候，`docs/USING-SIMGEN.md`（215 行、`simgen` 的使用者
操作手冊）**只存在於一個要被刪掉的分支上** —— main 從來沒有它，而 `simgen`
是出貨的功能（`python -m d4t simgen`）。

驗過才收：它引用的 16 個 CLI 旗標**一個不差**、`gc_generator` / `gc_paint` /
`make_lot_from_gc` 都還在、兩個檔案路徑也都在。收進 `docs/`，並補進
`CLAUDE.md` §0 的導覽表與 `ARCHITECTURE.md` 的目錄樹（那兩個地方有測試守著）。

**教訓：刪分支之前要看裡面有什麼。** 32 個分支裡 29 個是完整併入的（零風險），
而剩下 3 個裡有 1 個裝著唯一一份副本。

### ⑤ 再救一支：`tools/run_tests.py`，而它牽出一張漂掉的例外清單

同一批要刪的分支上還有 `tools/run_tests.py`（逐檔一個行程跑測試）。收它的理由
**不是**它 docstring 上寫的那個效能數字，是這個：

> `CLAUDE.md` §4 教的是 `for f in tests/test_ui_*.py; do pytest -q "$f"; done`
> —— 而那是 **bash**，家用機是 Windows（同一節上面就寫著 `.venv\Scripts\activate`）。

**一份寫給某台機器的程序，在那台機器上跑不動。** 跟 `docs/NO-GIT-SETUP.md` 那個
「按 blob 頁的複製鈕」同一類，同一天一起修的。這支是 stdlib-only 的 Python，
兩台都跑得動，而且比 for-loop 多給逐檔計時、最慢的幾個、失敗收集到最後一起印。

它在分支上躺了三週，docstring 累積了**四個假話**（專案名還叫 ADEPT、「CI 跑不加
參數的 `pytest -q`」在 08-24 就不成立了、「25 支 UI 測試檔」現在是 84、引用了一個
已經不存在的 slow marker）—— 收進來時全部訂正。**一份沒併進來的檔案，會安靜地
變成一份說謊的檔案。**

⚠ **而把它接上守門測試的時候，發現 `ALL_TOOLS` 這張手寫名單早就漂了。**
名單上 8 支，而 `tools/` 底下純 stdlib 的其實有 **14 支** —— 漏掉的六支裡有四支
（`show_template.py` / `pair_probe.py` / `load_probe.py` / `check_glas_export.py`）
在 `AGENTS.md` §4.5 上標著**公司機**，也就是「stdlib-only」對它們是**承重**的。
`show_template.py` 的檔頭甚至直接寫著「stdlib-only，所以公司機也跑得動」——
一句從來沒有被驗證過的話。

改成**反過來列**：預設每一支都守，例外具名在 `NEEDS_THIRD_PARTY`（七支產合成
資料的，吃 numpy/cv2），並照 `CLAUDE.md` §1 的規矩配一支**反向測試** ——
某一支哪天不再需要 numpy 卻沒下架的話會紅（驗過會咬）。加新工具從此自動被納入，
不需要有人記得回來改名單。那六支**全部一次通過**，也就是說這張防線本來就該蓋到
它們，只是沒有人接上去。

### ⑥ ③ 錯了，而使用者在公司機上撞到 —— 同一天改第二次

**這一輪最嚴重的錯，值得完整記下來。** ③ 把包改成不壓縮的純文字，只看 git 的
pack 那是對的。使用者拿去公司機，回報兩件事：

> 「我複製 bundle 是可以 可是非常 lag 很卡」
> `SyntaxError: Non-UTF-8 code starting with '\xe5' in file d4t.py on line 78146,
> but no encoding declared`

**同一個病根**：純文字版有 **31% 的位元組是中文**（2,435,014 / 7,848,397）。
公司機拿程式碼的方式是「瀏覽器複製 → 記事本存檔」，而中文 Windows 的記事本
會存成 **ANSI（cp950）** —— 中文變成 Big5 位元組，Python 用 UTF-8 讀就死。
7.6 MB 的全選複製同時也卡到不能用。

⚠ **舊的 base64 版是純 ASCII，所以記事本用什麼編碼都無所謂 —— 而那個保護是
意外得來的，沒有人寫下來。** 於是它被弄丟的時候，沒有任何一條測試發現。
**通則：搬運路徑上「意外成立」的性質，跟功能一樣要有測試。** 那條路上的每一個
環節都在一台我們看不到、也不能除錯的機器上執行。

量了四種格式才定案：

| 格式 | 單份 | 非 ASCII | 每改一次 pack |
|---|---|---|---|
| 整包 lzma+base64（更早） | 2,264 KB | 934 | 1,711 KB |
| 純文字（③，錯的那個） | 7,664 KB | **812,303** | 1 KB |
| **逐檔 lzma+base64（現在）** | **3,447 KB** | **0** | **94 KB** |
| 逐檔 base64（不壓） | 10,108 KB | 0 | 78 KB |

「逐檔」是關鍵：整包壓成一個流的話改一行就整份變樣。三個限制一次滿足 ——
純 ASCII、比 ③ 小 55%、git 每次只多 94 KB。**解包程式的檔頭與訊息也全部改成
英文**（連 SENTINEL 那一行），因為那一段是最不能壞的：它就是解包本身。
舊包照樣解得開（三種格式都認得）。

守門人兩條：`test_the_bundle_is_pure_ascii`（問產出來的東西，不是問程式碼裡
寫了什麼）與 `test_a_bundle_saved_as_ansi_still_unpacks`（**真的用 cp950 存
一次再解**，順便驗 CRLF 與 UTF-8 BOM）。驗過：cp950 存的那份解出來 383 個
檔案逐位元組相同。

### ⑦ CI 的 3.9 job 抓到第三張漂掉的手寫清單

⑤ 把 `ALL_TOOLS` 從手寫名單改成「反過來列例外」之後，**CI 的 3.9 job 紅了三條**
（3.11 / 3.12 全綠）：`check_glas_export.py` 的 `csv` / `zlib`、
`make_text_bundle.py` 的 `lzma`、`show_template.py` 的 `binascii` / `zlib`
被判成「模組層 import 了非標準函式庫」—— 而那**全部都是標準函式庫**。

病根在 `_stdlib_names()`：`sys.stdlib_module_names` 是 **3.10+** 才有的，
而這個 repo 的底線是 3.9（鐵則 2），於是 3.9 退回一張**手抄的 23 個名字的表**
—— `csv` / `zlib` / `lzma` / `binascii` 一個都不在上面。

**今天第三次踩到同一個形狀**（`ALL_TOOLS`、`NEEDS_THIRD_PARTY` 的前身、
這一張），所以這次不再手寫：3.9 那條路改成**問系統** ——
`sys.builtin_module_names` 加上掃一次 stdlib 目錄（含 `lib-dynload` 的
`.so`/`.pyd`）。探測到 **306 個名字**，手抄表是 23 個。

⚠ **這條路在 3.11 的開發機上永遠不會被執行到**，所以它壞掉只有 CI 的 3.9
job 會講，而那要等七分鐘。所以配一支測試：`force_probe=True` 強制在 3.10+ 上
走 3.9 那條路，斷言它蓋得住所有工具真的用到的標準函式庫
（`test_the_python39_stdlib_probe_agrees_with_the_real_list`）。

**通則：一條「只在某個版本上才會執行」的分支，要有辦法在別的版本上被驗。**
不然它的正確性就外包給了 CI 的一個 job，而那個 job 只在你推上去之後才說話。

（順帶：這一輪的三個「手寫清單漂掉」全部是**紅的**才被發現的，算是運氣好 ——
`ALL_TOOLS` 那一張漂了不知道多久，而它漂掉的症狀是**綠的**：少守四支工具。）

### ⏭ 還沒做的那一步：把 378 MB 拿回來（要在這個 PR 併進 main 之後）

使用者選的是「E + G」。E（不壓縮）在這一輪；**G（改寫歷史）刻意留著沒做**，
因為順序不能反：現在改寫，這條分支併回來的時候舊 blob 又全部回來了。

併進 main 之後，在家用機上跑（已在本地 clone 上實測過，440 個 commit、
425 個檔案全部保留）：

⚠ **而 G 有一個前提，漏掉的話它會白做。** repo 上有 33 個分支，其中 **29 個
已經完整併進 main** —— 它們的歷史整段都是 main 舊歷史的子集，**包含全部 217 份
bundle**。只改寫 main、把那些分支留著的話：`git clone` 預設抓所有分支，舊的
commit graph 照樣被釘住，**重新 clone 還是 400 MB**。而 `filter-repo` 會跑完、
會回報成功、本機 `count-objects` 也會顯示 7 MB —— 第八個「跑得完、有數字、
而且是錯的」，只是這次發作在「你以為已經解決之後」。

（`refs/pull/<n>/head` GitHub 會永久保留，所以那些 commit 之後仍然查得到 ——
但一般 clone 不抓那些 ref，不影響 clone 大小。）

所以順序是：**併 PR → 刪掉那 32 個分支 → 才跑 G**。

```bash
# 1. 刪分支（⚠ 這一步從 Claude Code 的 session 做不到：push 新分支可以，
#    刪 ref 被 GitHub 回 403，而 GitHub MCP 沒有刪分支的工具）
git push origin --delete $(git branch -r --merged origin/main \
    | sed 's|origin/||' | grep -vE 'main|project-pros-cons-3tot51')
# 另外三個未併入的（USING-SIMGEN.md 已經救進來了，刪掉零損失）：
#   claude/project-changes-summary-w9814v
#   claude/project-review-kxxmd7            ← 還有 tools/run_tests.py，main 沒有
#   claude/project-review-pros-cons-pyqsek

# 2. 然後才改寫歷史
pip install git-filter-repo
git filter-repo --path bundle/ --invert-paths --force   # 385.58 MiB → 7.23 MiB
python tools/release.py                                 # 現在這一份重新產出來
git add -A && git commit -m "bundle: 純文字版重新放回來（歷史已清）"
git push --force origin main                            # ← 不可逆
```

跑完 **385.58 MiB → 7.84 MiB**。⚠ 所有 commit 的 SHA 都會變，既有的 clone
要重新 clone；單人開發、一台開發機，代價就是這樣。

---

## F83：使用者回報的三個 UI bug（2026-09-03）

使用者一次丟三件，而**三件都是「跑得完、看起來沒事、終端機在噴東西」**：

**① 「Show it on the canvas」點了沒反應**（`AttributeError: 'StudioWindow'
object has no attribute 'canvas'`）。那一支兩個名字都錯 —— 畫布叫
`self.pipeline`（`self.canvas` 從來沒有存在過），而 `show_card_ghosts` 吃的是
一個**圖元**不是節點 id。也就是 F68 加的那一列選單**一次都沒有成功過**，而
那一輪的測試只問了「從插槽挑一個等不等於在畫布上拉那條線」。

現在它走的是 `_on_slot_wire` 找來源的**同一支**（`stream_producer` /
`region_producer`），所以「選單裡挑的那個名字」與「畫布上指的那張卡」永遠是
同一個答案。指的方式是 `PipelineCanvas.reveal_cards`：**捲進視野 + 亮起
hover**，不是選取 —— 選取會把右邊的設定換成那張卡，而使用者按這一條的時候正在
編**下游**那一格。亮著的卡記在 `_ghost_cards` 上（跟幽靈線同一格），所以
`clear_tree_ghosts` 就是它的清潔工：**滑鼠一碰畫布就自己熄掉**，不用計時器。

**② 快速點兩下卡片跳出一張殘影。** 那是 `QDrag` 的 pixmap。`_LibraryItem`
只在 `mousePressEvent` 記起點、**沒有 `mouseReleaseEvent`**，起點因此跨得過
一次點擊；第二下 Qt 送的是 `MouseButtonDblClick`（不是 Press，起點不會更新），
按著的那幾 px 抖動就跟**第一下**的起點湊出了拖曳門檻。放開就把起點作廢。

**③ 拉線／刪卡跳 `RuntimeError: Internal C++ object (_NodeItem) already
deleted`。** `set_nodes` 的 `scene.clear()` 會銷毀選著的那個圖元，Qt 當場送出
`selectionChanged`，而 F78 那支 handler 問的正是 `self._items` 每一張卡選中
沒有 —— 表裡握著的已經是殘骸。**先放掉表再 `clear()`**（空表答得出「沒有東西
被選中」，而那一瞬間那句話剛好是真的），剩下沒有經過我們的拆除路徑（Qt 自己的
teardown）由 `except RuntimeError` 收尾。

**三條都先寫出會紅的測試才修**，而三支都真的重現了使用者貼的那一串：
`test_ui_wiring_slot.py`（第 4 節，含「指給我看不等於換一張卡編」）、
`test_ui_f7_19_wiring.py`（雙擊不拖曳／真的拖仍然拖得動）、
`test_ui_canvas_focus.py`（第 4 節，一支問結構、一支直接抓終端機那一串）。
`docs/PITFALLS.md` 加三列。

⚠ 三件裡有兩件的共同形狀值得記下來：**UI 的路壞掉不會讓任何測試變紅**。
①是一列從來沒被走過的選單，③是一串印在終端機、畫面上看起來沒事的 traceback
—— 兩者都活了好幾輪。

---

## F82：拖曳改成磁吸（2026-09-03）

使用者：「目前在畫布拖動沒有像之前那樣絲滑的感覺（有點是一格一格的），這是我們
哪部改動造成的?」—— 是 F79 的拖曳吸附，而那個描述是**準確的**。
計畫書：[`docs/history/plans/F82-drag-magnet.md`](docs/history/plans/F82-drag-magnet.md)。

F79 的 `_snapped` 是**無條件**量化：每一次滑鼠移動都被 round 到 `GRID`（20）的
倍數 —— 100% 縮放時一步 20 螢幕 px、fit 到 54% 時一步約 11。也就是**卡片從頭到
尾沒有一刻跟著游標走**，它一直在一個晶格上跳。對齊買回來了，跟手賠掉了，而我在
F79 的計畫書裡把它寫成「拖到哪都會吸到最近的點上 —— 那是點陣底存在的理由」，
**完全沒有提到代價那一面**。使用者選了磁吸。

三個決定：半徑用**螢幕**座標（`SNAP_REACH_PX = 4.0`）除以縮放換算回畫布座標
（手感要跟縮放無關）；**上限夾在四分之一格** —— 縮到 40% 時 4 / 0.4 = 10 正好
半個格，磁區會把整條軸蓋滿而退回無條件吸附；**逐軸判斷** —— x 對齊了而 y 還在
中間是合法的狀態，歐氏距離會把兩軸綁在一起。`setPos` 仍然完全不吸（F79 §2.3
的理由沒變）。

**測試的 `_drag` helper 連錯兩次，而兩次在無條件吸附時都看不出來**（結果都被
round 掉了）：① 每一顆事件都從場景座標重算 view 座標，可是拖曳途中 sceneRect
會長大、捲軸跟著位移，同一個場景點對應到另一個 view 點；② 一步跳過去而不是連續
移動 —— 真實滑鼠每一顆 move 都相對當下的捲軸位置，偏移會被下一顆修回來，一步跳
沒有機會收斂（實測 (30,50) 的拖曳停在 (44,50)）。現在是 12 顆 move。

**突變驗證翻出一件我沒設計的事**：把 `SNAP_REACH_PX` 從 4 調到 100 **不會變紅**
—— 因為上限把它夾住了。真正決定行為的是**上限**不是半徑，所以下一個想「讓磁吸
強一點」的人要動的是上限，而那正好是有測試守著的那一個（想放寬吸附就必須先面對
「還剩多少自由行程」）。排列是對的，但它是突變測試指出來的，不是我想到的。

全套測試綠，黃金值三份全綠（這一輪一個數字都沒動）。

---

## F81：真的變成 flat（2026-09-03）

F80 §5 那個決定，使用者在 A/B/C 三張圖裡選了 **B**。
計畫書：[`docs/history/plans/F81-flat-for-real.md`](docs/history/plans/F81-flat-for-real.md)。

**`theme.py` 檔頭那句「全平面 —— 沒有陰影、沒有漸層」從 F7-2 寫到現在，一直是
假的**：節點卡底下一直畫著一塊實心、單一 alpha、有硬邊的偏移方塊（那不是陰影，
是重影）。量出來更有意思 —— **它只在亮色看得見**：alpha 46 的黑疊在亮色底上是
ΔL* 15.7，疊在暗色的 `#16181d` 上只有 2.3。也就是暗色的卡片一直是靠明度差站著
的（ΔL* 6.9），只有亮色在靠那塊重影撐（ΔL* 4.9）。「兩個主題長得一樣」以前是
假的，它們用的是兩個不同的機制。

所以：拿掉陰影、亮色 `canvas_bg` `#f0f1f4` → `#e6e9ee`（ΔL* 7.7，比暗色的 6.9
還多一點）、`canvas_grid` 跟著壓深（不動的話點對底的 ΔL* 會從 10.4 掉到 7.6，
F79 才剛買回來的對齊參考會安靜地淡一階）。**暗色一格都沒動。**

**⚠ 上一輪我講錯一句，這輪補上。** F80 §5 說 B「hover 那一階也一起解得掉」——
`canvas_bg` 動不到按鈕，那句話是錯的。#7 要的是同一個邏輯套在 `bg_page` 上：
亮色白鈕 hover 之後是 L* 95.4，而 `bg_page` 是 96.5（差 **1.1**）、`toolbar`
97.6（2.1）、`bg_panel` 98.6（3.1）—— **只有 `bg_page` 是壞的，所以只動它**，
值刻意跟 `canvas_bg` 相同（app 的地板是同一個顏色）。

門檻 `MIN_HOVER_ON_GROUND` 第一版我寫 3.0，測試當場指著 `light/toolbar ΔL* 2.1`
說話 —— 那會把工具列也一起判死，而它不是這輪要改的。改成從**已經出貨的東西**推：
工具列白鈕平常就是 100.0 坐在 97.6 上（2.4），F7-24 量過並接受了那個薄度，
hover 是同一個薄度的另一側，所以底線 2.0。工具列現在貼著這條線 —— 誰要再動
`hover_warm` 或 `toolbar`，那條測試會先擋下來。

`tests/test_ui_canvas_flat.py`（9 條），四個突變都驗過（陰影回來那條**只有亮色
變紅**，正好就是這輪的重點）。那條「畫一次看卡片外面有沒有比底色暗的東西」踩了
兩個坑：`QGraphicsScene.render` 不呼叫 view 的 `drawBackground`（空白是透明、讀
成純黑），以及加進來的卡片預設是選中的，而選中的卡有一圈畫在邊框外面的 accent
光暈（量到的 ΔL* 42.6 是它不是陰影）。

**還補了 F80 漏掉的一條**：`test_doc_file_tree` 在那一輪就紅了（`focus_visible.py`
不在 `docs/ARCHITECTURE.md` 的目錄樹上），而我用 `tail -4` 看輸出，那一行正好被
截掉 —— 等於推了一個測試沒過的 commit。教訓不是「要仔細一點」，是**不要用 `tail`
看測試結果**，失敗的行數不固定。

全套測試綠，黃金值三份全綠（這一輪一個數字都沒動）。

---

## F80：焦點環、動畫、圓角的家，以及一條空轉的測試（2026-09-03）

接 F78 §5 剩下的五條（使用者：「按照你說的繼續做」）。做了三條，**#7 量完之後
折進 #6**，而 #6 需要使用者選一邊 —— 三個選項已經 render 成圖。
計畫書：[`docs/history/plans/F80-focus-visible-and-motion.md`](docs/history/plans/F80-focus-visible-and-motion.md)。

**① 焦點環只在鍵盤導覽時出現**（`d4t/ui/focus_visible.py`，新模組）。
`QPushButton` 預設是 `StrongFocus`，滑鼠點一下就拿到焦點，而 QSS 的 `:focus` 對
點擊一樣生效 —— 按完「Run trial」那顆鈕留著一圈藍框，看起來像「還在啟用中」。
CSS 有 `:focus-visible`，Qt 沒有；一支裝在 `QApplication` 上的事件過濾器把
`QFocusEvent.reason()` 寫成 `kbFocus` 屬性，QSS 改成 `[kbFocus="true"]:focus`。
**文字輸入刻意不 gate**（點進輸入框卻沒有邊框變化是錯的），裝在 `apply_theme`
裡（樣式表與餵它屬性的東西必須一起到，分開的話焦點環從此不出現而且不報錯），
`ActiveWindowFocusReason` 維持原狀（切視窗不算使用者在移動焦點）。

**② 換視角要看得出「這兩張是同一份 pipeline」**。`fit()` / `reset_zoom()` /
`tidy()` 加了 170ms 的動畫。**終點由原本那支函式自己決定，動畫一個字都不算** ——
先跳到終點量下來、再回起點演，所以 `fit` 的規則以後怎麼改動畫都不會跟它分家；
順便讓「被打斷」變成不用處理的事（任何時刻的真相都已經是終點）。
⚠ 測試裡一律關掉（conftest 多一支 autouse fixture，跟「不准跳 modal」同一種
東西），只有 `test_ui_canvas_animation.py` 自己開著跑。

**③ 圓角有家了**：`theme.radius()`。只收卡片本體那一族（畫布卡與判定樹的卡以前
差 1px），repo 裡另外 20 幾個 2–4px 的裝飾性圓角**刻意不收** —— 綁上來等於宣稱
「改一次 radius_md 全 app 一起變」，而那件事沒有人想要。

**這一輪最值得記住的是①順手翻出來的東西。**
`test_the_focus_ring_does_not_move_the_label` **從一開始就是空轉的**：它比的是
`contentsRect()`，而 QSS 底下那個值的邊界**恆為 (0,0,0,0)**，所以比較永遠相等、
永遠綠。（改成比「文字在按鈕裡的位置」也是空的 —— 按鈕比 sizeHint 寬的時候
`QPushButton` 會把文字置中，padding 差 1px 完全不動它。）真正看得見那 1px 的是
**`sizeHint()`**：環一出現按鈕就變大，而按鈕變大就是把版面上的鄰居推開。
改成問它之後當場抓到一個**真的 bug**：`#cardButton`（Card/Features 那顆切換）
一被 Tab 到就縮 2px。

而修它的時候我又把規則講錯了一次：第一版連 `#galleryChip` 也一起補 padding，
反向驗證那一輪它**不變紅**才發現那是 no-op —— 判準不是「每個 id 規則都要補」，
是「blanket 的 padding 只有在**沒有更具體的規則宣告過 padding** 時才到得了你」。
`#galleryChip` 的 base rule 有宣告，`#cardButton` 刻意沒有（幾何屬於 `[shape]`），
所以只有後者中招。

`tests/test_ui_focus_visible.py`（10 條）＋ `tests/test_ui_canvas_animation.py`
（6 條），`test_ui_f7_23_buttons.py` 改寫一條並把 `#galleryChip` 與 `#cardButton`
的三種 shape 補進 `KINDS`（那四個以前完全沒被問過）。
全套測試綠，黃金值三份全綠（這一輪一個數字都沒動）。

---

## F79：點陣底要說實話（2026-09-03）

接 [F78](docs/history/plans/F78-canvas-focus-and-lod.md) §5 的第 5 條（使用者：「接著做」）。
計畫書：[`docs/history/plans/F79-grid-tells-the-truth.md`](docs/history/plans/F79-grid-tells-the-truth.md)。

**症狀**：畫布上唯一那個說「這裡有一套對齊」的東西，指的是一套不存在的對齊。
背景點陣間距 `GRID` 是 22，而版面用的是另外一組數字 —— 欄距
`NODE_W + COL_GAP` = 320（320 / 22 = 14.55）、列距 105（105 / 22 = 4.77）。
兩組都不整除，所以按了「排整齊」之後卡片左上角落在點與點之間，**而且每一欄／
每一列偏移的量還不一樣**（欄：0, 12, 2, 14 px；列：0, 17, 12, 7 px）。
沒有人看得出「差 12px」，但「每一列差的量不同」在餘光裡讀得出來 —— 讀出來的
結論是「這張圖沒有排好」。**這一條一直被當成配色問題在改。**

**做法**三件：`GRID` 22 → 20（唯一不必動卡片尺寸就成立的值：320 = 16 × 20）並
**搬到模組層**；列距用 `on_grid()` 往上進位（105 → 120，卡片高度是變動的所以不
能寫死）；拖曳時吸附到點上。

搬到模組層是重點的另一半：它以前是 `PipelineCanvas` 自己的私有常數，只有
`drawBackground` 讀得到 —— 於是「背景說的對齊」與「版面做的對齊」是兩套，各自
演化，而沒有任何東西會在它們分家時抱怨。

⚠ **吸附只吸使用者拖的那一下，不吸 `setPos`。** 後者是別的程式碼**重現**一個位
置的路（彈出視窗要跟主畫布同位置、重建畫布要放回拖好的佈局），一旦量化就不再是
identity —— 存 333 讀回 340、再存 340……每重建一次漂一格。跟鐵則 9 是同一種
bug，只是漂的是像素不是分數。這不是推論：把吸附加在所有 `setPos` 上跑一次，
`test_dragged_positions_survive_edits_and_popout` 當場變紅。

**沒做**：卡片右緣仍然不在點上（`NODE_W` 204 不是 20 的倍數）。量過 —— 要收成
200，而那 4px 是 F13-⑤ 花錢買回來的標題寬度。左上角對齊才是「這一排卡有沒有排
好」的判準，右緣那 4px 每張卡都一樣，不會讓卡片之間歪掉。

`tests/test_ui_canvas_grid.py`（7 條），四個突變全部驗過。其中「欄距是格線的整數
倍」那條是**給下一個要改 `NODE_W` / `COL_GAP` / `ROW_GAP` 的人的絆線** —— 欄距一
旦不再整除，畫面上不會有任何錯誤，只會慢慢變得不整齊，而它上一次是怎麼發生的
沒有人知道。

全套測試綠，黃金值三份全綠（這一輪一個數字都沒動）。

---

## F78：畫布的「現在該看哪裡」＋ 主要按鈕的邊框（2026-09-02）

使用者：「我想要針對 Studio 的 UI 細節（畫布跟按鈕）做美觀，請給我建議。」

給了十條，做掉代價最低的四條；另外六條連同代價寫在
[`docs/history/plans/F78-canvas-focus-and-lod.md`](docs/history/plans/F78-canvas-focus-and-lod.md) §5。
**一行都沒有動 `studio.py`。**

1. **選中一張卡 → 接著它的線亮起來，其餘退下去。** 以前選一張卡只有那張卡自己
   有反應，而使用者點它的理由通常正好是「它接了誰」—— 那個問題以前要用眼睛沿
   著線走。亮起來是**同一個色相調濃**（0.5 → 0.9）不是換成 accent 藍：線的顏色
   講的是「它從哪張卡出來」（F13-⑤），換色會蓋掉那個意思。退下去的線往
   `canvas_bg` 混 55% —— **退下去不是消失**，有測試守著對比度。
   接的是 `scene().selectionChanged` 而不是補在 `set_selected` 裡：選取有三條路
   （點卡片、框選、程式呼叫），只補一條的話另外兩條會變成「有時候會亮有時候不
   會」。
2. **hover 一條線時線本身也動**（`canvas_edge_active` + 2.4px）。以前只有中點
   那顆紅 ×，而它離兩端各一百多 px。hover 永遠贏過「退下去」。
3. **縮到 55% 以下，卡片收掉小字**（副標／設定摘要／埠標籤，標題留著並移到中
   線）。背景的點在 0.45 以下就不畫了，卡片一直沒有這條線 —— `fit()` 到 40% 時
   那些 6–7pt 的字是糊在卡片上的灰噪點。字比點更早糊，所以門檻取 0.55。
4. **`#primary` 的邊框跟著填色走。** 它只在一般狀態寫過一次
   `border: 1px solid $accent`，`:hover` / `:pressed` 只換 `background` —— 於是
   hover 時邊框比填色**深**（讀起來像凹下去，與 hover 的意思相反）、pressed 時
   比填色**亮**（像光暈）。工具列與 `QPushButton` 各兩條。

**兩個決定值得記住。**

**其一：把「怎麼畫」從 `paint` 裡拉出來。** 顏色／粗細進 `_EdgeItem.line_pen()`、
收不收小字進 `_NodeItem.terse_at()`。理由跟 `shape()` 與 `cut_hit` 讀同一個
`CUT_GRAB` 一模一樣 —— **看得到的與測得到的必須是同一個定義**。留在 `paint` 裡
的話，驗「選中一張卡，線有沒有真的亮」只剩數像素，而那種測試在下一次改字體時
就會變紅、然後被關掉。

**其二：新的測試全部做過反向驗證，而其中一條第一版是假綠的。** 按鈕那條像素
測試量的是 x=2，可是那一格是**填色**不是邊框 —— 焦點環是畫在按鈕自己的填色上
面的 2px 環（`focus_ring_inverse`，primary 上是白的），把最外面兩格佔掉了。
它的症狀是零：測試綠、畫面對、只是問錯了問題。抓到它的唯一方法就是**把修正
拿掉、看它會不會紅**。改成量 x=0，並且先斷言那顆按鈕沒有焦點。

`:hover` 在離屏平台 render 不出來（`WA_UnderMouse` 與 `QHoverEvent` 都沒讓
`QStyleSheetStyle` 進 hover），所以那一半改用**結構**守：掃 QSS，只要一條
`#primary` 的狀態規則動了 `background`，它就必須同時講出邊框 —— 下一個人加新
狀態時這條會替他問一次。

`tests/test_ui_canvas_focus.py`（11 條）＋ `test_ui_f7_23_buttons.py` 新增 2 條，
全套測試綠，黃金值三份全綠（這一輪一個數字都沒動）。

---

## F77：Focus index 多一個 IQI (OP-301) —— 而三份規格互相矛盾（2026-09-02）

使用者要在 FI 卡加機台的對焦分數，並且說「如果你覺得這算法有問題也可以提出來」。
提出來了三條，**每一條都用實測講**，而其中兩條改變了實作。

### ① 濾波方向：兩份說明看起來相反，其實不是在吵同一件事

* 詳細版：「把**低頻**壓掉（光暈、底色漸變）」→ 高通。
* 投影片／英文版：「filter out **high-frequency noise** in unpatterned areas」→ 低通。

前者要拿掉**背景**（頻譜最低端），後者要拿掉**雜訊**（最高端）—— 唯一讓兩句話
同時成立的是**帶通**，而那也正是對焦指標該有的形狀（邊緣落在中頻）。

而後者指的是一個**真的失效模式**。實測 512×512，空背景 ＋ σ=8 雜訊 vs 銳利
pattern：

| | 純高通 | 帶通（noise=40%）|
|---|---|---|
| 空背景 ＋ 雜訊 | **64.19** | 7.00 |
| 銳利 pattern | 7465.63 | 4167.45 |
| 訊號 ÷ 背景 | 116× | **595×** |

純高通把**雜訊當成清晰度**。預設仍是純高通（詳細版明確描述的行為，先能對上
機台的數字），帶通是一格參數 —— **站點差異封裝進 recipe，不封裝進程式碼**。

### ② 梯度圖：詳細版裡它是一段空轉的程式碼

詳細版把梯度列成獨立的 Step 2、說它「讓你知道哪些塊落在 pattern 區域」，而
Step 4 選前 30% 是照 **energy** 選的 —— **梯度圖沒有任何下游**。四個步驟裡有
一個是空轉的，而它會通過驗收、看起來完全正常。投影片把它放進 Step 1
（「篩選出高圖案密度的區域」），那一份它真的在篩。

兩條路都留（``min_pattern``，預設不篩），而**無論走哪一條，梯度密度都變成一個
看得見的數字**（``focus_iqi_pattern``）—— F19 的規矩：卡片自動做的每一個決定，
都要變成一個使用者畫得出分布的數字。

### ③ iFFT 省得掉（Parseval），而「虛部」是浮點雜訊

``Σ|iFFT(X)|² = (1/N)·Σ|X|²``，所以 Step 3 對最終數字沒有貢獻；而輸入是實數
影像，iFFT 之後虛部 ~1e-16 —— 規格說的「由實部與虛部求得」逐字就是 ``real²``。
仍然做（驗收要四個步驟、空間域那張圖之後要畫在儀表上），但
``test_parseval_says_the_ifft_is_optional`` 把兩條路釘在一起：**哪天嫌慢，
那條測試就是刪掉 Step 3 的許可證**。

### 放在哪

Focus index 卡多一格 ``metrics``（**勾選，不是四選一** —— 這幾個可以同時要，
`CLAUDE.md` §3）。預設仍是原本三個，**既有 recipe 與黃金值一個位元組都不動**；
IQI 勾了才算（一顆 defect 64 次 FFT，不該無條件付這筆錢）。

驗收五條各一支測試（`tests/test_iqi.py`）：單一 scalar、blur 單調下降
（7465 → 2.07）、全灰 = 0、512/1024/2000 差 <5%、四個步驟各自組得回同一個答案。

### ⚠ 使用者跑起來截了圖，三個 bug —— 其中一個是畫面在說謊

**設定區寫「nothing picked yet · 0 picked」，而底下的特徵表列著三個值。**
病根：`METRIC_GROUPS` 加了 `"Sharpness"` 這個群名，但 `METRIC_GROUP_ORDER`
**沒加** —— `MetricChips._build` 是照那張表逐群畫的，漏一個群 = 那一群的膠囊
一顆都不會出現。而引擎照樣拿 `validate_params` 補出來的預設值在算，所以它
**跑得完、有數字、看起來完全正常**。

守著它的有兩支：群名對照（資料層）＋ **掃 registry 真的建一次 widget**
（群名對了但畫的時候被別的條件濾掉，第一支抓不到）。

另外兩個：IQI 根本沒勾、它的滑桿卻擺在畫面上（我在卡片註解裡寫的「`show_when`
用不了，因為 `metrics` 是一串」**是錯的** —— `param_visible` 對逗號清單做的
本來就是成員比對，F37 就是為這件事改的）；以及「Name these results」出現在
「2 · IQI (OP-301)」的標題底下（共用的 `output_prefix_spec` 沒有 section，
掉進了前一格的分節，而那個標題正在說謊）。

### 待 owner 核對

``Also wash out noise above`` 預設 0（＝純高通）。空背景區也會被評分的站點
應該開到 30–40，而那是上面那張表的用途。

---

## F76：Feature 面板要大改版 —— 而那塊面板已經存在了（2026-09-02）

使用者：「目前 feature 顯示面板跟後面帶的數值我覺得好亂」→「我建議大改版，
你可以先瀏覽整個 studio 架構」。**五刀全部做完**，而第一版提案在瀏覽之後
作廢了一刀 —— 我要蓋的那塊面板已經存在。

### ① 第一版提議開一塊新面板。瀏覽完之後那一刀作廢

我要蓋的東西（卡 › 區域 › 統計量的樹、雙層表頭、維度過濾）**`ui/results_table.py`
兩星期前就寫好了**（PR-1／PR-3，`column_tree()` ＋ `verdict_features.bound_specs()`）。
Preview 那一塊走的是另一條弱得多的路（`studio._feature_sections()` 只分到卡）。

兩份說法**已經漂開了**，而症狀是可以量的：同一個區域 `between_columns`，
ROI 卡寫的特徵 `region_index=0`（綠）、GLV 卡寫的 `region_index=1`（琥珀），
**同一張表上兩種顏色**，而影像上那個框只有一種。`CLAUDE.md` §3 的
「顏色指錯區域比沒有顏色糟得多」現在就是這個狀態 —— 鐵則 10。

所以這一輪不是加一塊面板，是**把 Preview 接到已經在跑的那一份上**：
Results 是 *N 顆 × M 特徵*，Preview 是 *一顆*，也就是同一棵樹的轉置。

### ② 量出來的病（`recipes/rsem-worst-box.json`，118 個特徵）

* **36 個**特徵的「What it is」只是把 id 抄一遍（`glv_worst_*` 整族 ——
  正好是使用者當下在問的那幾個字）。`Step.feature_help()` 這條路已經存在，
  GLV 卡沒填而已。
* **97 個**的說明跟別的特徵一字不差：`feature_gloss` 只讀 `spec.metric`、
  **不讀 `spec.variant`**，所以 `_typical` / `_outlier` / `_outlier_box` /
  `_worst` 四胞胎四行相同 —— 而 `_outlier_box` 的值是一個**框號**，說明欄
  卻寫「75th percentile」。
* **四胞胎在畫面上不相鄰**：`glv_q75_worst` 跟 `glv_q75_typical` 差 13 列。
  列序 = `features` dict 的插入序，而 `_worst` 是迴圈最後才寫的 ——
  **排版跟著計算順序走，不是跟著意思走**。
* 沒有判定時 Verdict chip 永遠是 `—`，佔著量測卡最需要的那塊面積。

### ③ `_outlier` 不是沒用，是沒把「那是另一格」講出來

使用者：「outliner 完全沒有用 或者我看不懂? 反而這樣會誤導別人以為他是最
worst 的」。量了 24 顆（judge = `glv_q75`）：

| metric | `<m>_outlier_box == glv_worst_i` |
|---|---|
| `glv_q75`（＝ judge）| **24/24** |
| 其他四個 | 2–5 / 24 |

兩件事同時成立：**judge 那個量的 `_outlier` 是 `_worst` 的重複**（這個 repo
已經為同一種情形立過規矩 —— `WORST_FEATURES` 的註解拒絕開 `score_max`），
而**其他量的 `_outlier` 指的是另一格**。五格的最小例子（judge=median）：
`glv_std_worst = 6.2`（贏家 #4 的 std）vs `glv_std_outlier = 29.8`（#3 的），
兩個不同的格，名字上沒有任何線索。

### ④ 兩份出貨 recipe 刪掉（使用者指定）

留 `rsem-worst-box.json`，刪 `ebi-to-api-characterization.json` 與
`patch-dsnr-by-class.json`。**卡片一張都沒動** —— `pair_source` / `H2H` /
`output_char` / GLV 的 compare 全在。

⚠ 真正要小心的是**文件的連帶**：`docs/USING-CHARACTERIZATION.md` §1 以前寫
「不要自己從零蓋，用 `recipes/ebi-to-api-characterization.json`」，而那份不在了
—— **一份指著不存在檔案的操作手冊，就是文件版的「按了撞牆的鈕」**（推廣鐵則）。
改成「從零蓋」是主路（步驟本來就寫在 §1.1），並在頂上講明白那份檔案什麼時候、
為什麼走的。

`ALLOWED_ERRORS` 隨之變成空的（唯一那條「模板是一張影像、塞不進 JSON」跟著
patch 那份走了），但**機制與那支反向測試留著** —— 下一份 recipe 還要用。

### 做了什麼

| 刀 | |
|---|---|
| 1 | **區域顏色的序由「線」給**（`verdict_features._regions_in_wiring_order`）—— 修掉上面那個 bug |
| 2 | 說明欄看得見 `variant`、數字有單位（`Step.FEATURE_UNITS` / `step.VARIANT_UNITS` / `widgets.VARIANT_GLOSS`）|
| 3 | 卡 › 區域 › 統計量那棵樹搬進 `ui/feature_tree.py`，結果表與 Preview 吃同一份 |
| 4 | 新的 `ui/feature_panel.py`：四胞胎橫過來（GLV 那段 19 列 → 1 標題 + 2 列），`studio._feature_sections/_feature_specs` 退場 |
| 5 | 沒有判定就不畫 Verdict 那一塊，換成一句可以照做的話 ＋ 那顆鈕 |

決定：`<judge>_outlier` **不停產**（先只改顯示）、**開** `glv_worst_baseline`
（「目標格 − 其他格」從此寫得出逐字精確的式子）。
`widgets.FeatureTable` 走完「收起來 → 量代價 → 刪」全程，同一天刪掉。

### 而收工之後還抓到一個

使用者叫我自己造一份 recipe 測（GLV 逐框 ＋ IQI ＋ 兩題判定樹，24 顆跑完）。
跑出來：引擎寫了 52 個特徵，`FeaturePanel.feature_names()` 只回 39 個 ——
少掉的 13 個**全部都在畫面上**，只是刀 4 把它們升格成標題行、或變成
「← #46」那個地址。於是 `value_text("glv_worst_i")` 回 `None`，而那個數字
明明就寫在標題上：**取用口跟畫面說的是兩件事**，而報表、測試、之後的匯出
都走取用口。

（同一天截圖抓到的另外三個在 F77 那一段 —— 它們是 Focus index 卡的事。）

### 留下什麼

* [`docs/history/plans/F76-feature-panel.md`](docs/history/plans/F76-feature-panel.md)
  —— 病的量測、studio 版面全圖、四刀的形狀、收工後那四個。
* 一份可以點的 HTML mock（現在 ⇄ 改版後、有 ⇄ 沒有 ADC，欄名可編可拖）。

---

## F75：文件對齊現況 —— 而最大的問題是「哪些是活的」（2026-09-02）

使用者：「詳細整理一下目前的所有相關 MD 檔案，對齊現況，若可以縮減內容請縮減」。

盤下來 **60 份 MD**，而最大的問題不是內容過期，是**分不出哪些還活著**。

### ① `docs/plans/` 有 19 份，其中 18 份早就做完了

`CLAUDE.md` §4 寫著「做完不再改的計畫書搬進 `docs/history/plans/`」，而那條規矩
**從 F26 之後就沒有人執行過**。於是要找「現在還在做什麼」的人，得逐份打開看
頂上的狀態 —— 而其中三份的狀態自己就是過期的。

18 份搬進封存，`docs/plans/` 只剩 **F11**（Phase 2 的議程，Compare 段還沒收）。

⚠ **搬完檔案自己的相對連結要重算**（深了一層）。`test_docs_links.py` 兩份都抓到
了，但它守的是「指得到」，**不是「指對」** —— 一份搬到 `docs/history/plans/` 之後
寫著 `../plans/F40.md` 的檔案，那條連結照樣指得到某個東西（`docs/history/plans/`
底下真的有 F40），只是換成了另一份。所以我是**把 18 份的每一條連結列出來逐條
看過**，不是靠測試綠。這一條寫進 `docs/history/README.md` 的「什麼時候該往這裡搬」。

### ② `SESSION_LOG.md` 6,380 行 / 392 KB，而它跟著整包進公司機

切點的規矩是「上一次合併進 `main` 的那一輪」—— 而這條分支從 08-19 起就沒有再
併回 main，**那條線因此切不動任何東西**，檔案只會一直長。改用月份：
08-19 ～ 08-28（F42–F66，5,944 行）搬進 `docs/history/2026-08b.md`，
`SESSION_LOG.md` 剩 **438 行**。

搬之前照 `docs/history/README.md` 開頭那條規矩看了一遍頂上的狀態，撿到一個：
**F58 標著「⏸ 等使用者定調放哪裡」，而隔一輪的 F59 早就把那個問題整個換掉了**
（不是「這三件事該併進哪一支」，是「根本不要畫那個圖案，鋪他給的那一張」——
`tools/make_lot_from_gc.py` 因此誕生）。補了一段後記才搬。
一份寫著「等定調」而其實早就結案的紀錄，封存起來就是一句會誤導下一個人的話。

**搬運包因此從 2,354 KB 掉到 2,172 KB（省 182 KB），而一行內容都沒有刪。**

### ③ 對齊現況：八個數字是錯的

| 寫著 | 實際 | 在哪 |
|---|---|---|
| 註冊 19 張卡、可見 18 張 | **18 / 17** | `README.md`、`ARCHITECTURE.md` |
| 出貨 recipe「兩份」 | **三份**（F73 加了 RSEM 那一份）| `CLAUDE.md`、`ROADMAP.md` |
| `StudioWindow` 6,017 行 / 246 方法 | **6,667 / 258 / 382 個 `self.*`** | `CLAUDE.md` |
| 已知的坑「30+ 條」 | **80 條** | `CLAUDE.md`、`README.md` |
| 「以下**兩**件事目前刻意不支援」，底下只列一件 | 另一件（存檔 recipe）F34 就做回來了 | `README.md` |
| 「repo 內未附現成 recipe」 | **附三份** —— 而同一頁上面兩段才剛講過 `recipes/` | `README.md` |
| `region_key` 的例子是 `roi_compare` | 那張卡 F16 折進 `glv_stats` 了；今天唯一那一格是 `glv_stats.reference_region`（跑 registry 確認過）| `CLAUDE.md` 鐵則 10 |
| 已完成表上 `F8` 掛著 🔨 | Region 段 08-18 就收斂了 | `ROADMAP.md` |

⚠ **`README.md` 那兩條是自相矛盾**，不是單純過期 —— 同一份文件裡前後兩段互相
打臉，而它是新來的人讀的第一份。過期看得出來，矛盾看不出來該信哪一邊。

### ④ 縮減：三處，全部是「同一件事講第二次」

* **`CLAUDE.md` 的 bundle 那一節 26 行 → 17 行。** 它警告的那個一字兩義
  **已經不存在了**（F38 把 `output_bundle` 折掉），而它每個 session 都被讀進去。
  留下的是還算數的那兩條規矩（不改 `d4t_bundle.py` 的名字、不要再造第二個）。
* **`CLAUDE.md` 的「這幾支不准刪」從兩支變一張四支的表。** `algo/histmatch.py`
  昨天剛加入那個俱樂部（F74 刪掉它唯一的卡片層消費者），而它跟 `snr.py` /
  `period.py` / `golden.py` 是**同一條規矩**。四段散文收成一張表，還多守了一支。
* **`ROADMAP.md` 的 Region 那一格是 6,152 字元的單一表格儲存格** —— 七步的完整
  歷史塞在一個 cell 裡，讀不了。拆成表格下方的〈Region 段走過的七步〉，
  **一個字都沒有刪**，儲存格剩一句話。

### ⑤ F11 現在有兩種讀法，而它們會互相污染

`F11-phase2-features.md`（2,749 行）是唯一還活著的計畫書，但活的只有**方法**那
一半（「一張卡要回答的四題」）與 Compare 那一段。另一半是六段的逐張討論，
而它們寫的是**當時**的決定 —— 那一份現在還在講 `roi_mask` 與 `use_within`
（昨天刪的）、還把 `roi_cross` / `roi_template` 當成獨立的卡（F30 折掉的）。

沒有搬進封存（前一半還在用），但頂上加了一段講清楚兩種讀法，並寫下那句真正
要緊的話：**要知道某張卡今天長什麼樣，去問 registry，不要問這一份。**

核心 3497 passed、UI 逐檔全綠、黃金值三份逐項相同、`test_docs_links` 82 條全綠。

---

## F74：Region 段只剩一張卡，而它就叫 ROI（2026-09-02）

使用者兩句話：「**Mask from regions 這張 card 以及其相關功能請幫我拿掉（看不到
此功能 card 用處）**，同時 **ROI card 內剩下那一張就改名叫 ROI**」。

**「相關功能」是哪些 —— 量出來只有一個。** `roi_mask` 吐的那條 0/255 mask 影像
流，全 repo 只有一個消費者：`normalize` 的 `use_within`（畫面上「Use only」）。
卡走了就沒有任何一張卡產得出那條流，而那一格的型別是 `image_key` ——
**設定區唯讀、只能靠拉線填**。留著它不是「多一個選配」，是**一個接不到東西的
埠**：使用者看得到、按得到、永遠填不進去。所以兩個一起拿掉（使用者點頭）。

**代價付得起，而這一次真的量了**（CLAUDE.md §5 那張價目表的用法）：

| | 量到什麼 |
|---|---|
| 出貨 recipe（3 份）| 零個 `roi_mask` 節點、零格 `use_within` |
| fixture recipe（2 份）| 同上 |
| **黃金值（3 份）** | **逐項相同** —— 刪之前綠、刪之後綠 |
| 卡片庫 | 18 張 → 17 張 |

跟 `pattern_ref` 那次（rsem route 從 24/24 掉到 12/24）完全不同：那張卡是一條
route 唯一的 ref 來源，這一張沒有任何人在用。

**留下來的三件事，每一件都有理由**

* **`algo/histmatch.py` 的 `mask=` 不刪。** 呼叫者只剩測試 —— 而那正是這種模組
  被當成死碼順手清掉的時候。它是「**量與套用分開**」那個慣例的規範出處，而
  `range_from` 走的是同一套。同一條規矩 `algo/snr.py`、`algo/period.py`、
  `algo/golden.py` 已經寫過三次。
* **`_measure_from` 那一層不收掉。** 三個方法都走它，它是那句話在這張卡上的
  形狀。收掉等於把同一句話拆成三份各自寫一次。
* **`_cycles_with` 那道環的檢查不刪，但**它的證人換了地方（見下）。

**路上撿到一件事：刪一張卡會讓一條防線安靜地消失。**

`test_region_edges_migration` 有一條測「補區域線會成環就不補」。它的證人是
「Profile 吃 roi_mask 吐的 mask，roi_mask 又吃 Profile 定義的區域」—— 而
`roi_mask` 一刪，**能組出那個環的真卡就一張都沒有了**（吃區域的只剩量測卡，
而它們不吐影像流）。那條測試不會紅，它會繼續測「一份壞檔案壞得一樣」然後
**全綠**，而環的那一半已經不見了。

所以把環的那一半移到它真正住的那一層：`_cycles_with` 只看 `src`/`dst`，跟卡片、
參數、型別完全無關（`test_the_cycle_guard_is_graph_level`）。同一個形狀在
`test_ui_inspectors` 也修了一次 —— 「沒登記儀表的卡不會壞掉」那條的證人剩一張，
所以補了一行**反向的**：證人要真的在 `REGISTRY` 裡，不然對一個不存在的 key 問
`inspector_for` 當然回 None，而那證明不了任何事。

**兩個下限跟著降**（`test_card_invariants`：12→11、11→10）。降下限是唯一誠實的
改法 —— 這兩條問的是「這組測試有沒有真的測到東西」，不是「卡片有幾張」。
2026-08-25 刪 `snr_map` 時降過一次，寫法照抄。

**改名的代價是零**：`key` 仍然是 `roi_reference`（recipe 的鍵）、寫出來的 feature
名一個都沒動（那些會被打進分數表達式與判定樹）—— 改的只有畫面上那幾個字，
連同引用它的 `tools/check_glas_export.py` 報告、`scope.py` 的入口說明、
`recipes/README.md` 的三張圖與兩份出貨 recipe 的說明文字。

**舊檔案**：帶 `roi_mask` 節點的開起來是一條 `unknown-step`（同 `pattern_ref` /
`feature_math` 的先例 —— 跑不起來的 recipe 沒有必要幫它接線）；`use_within`
那一格由 `_migrate_drop_use_within` 拿掉。**那一道非做不可**：`validate_params`
對認不得的 key 是硬錯，而使用者看到的會是「unknown parameters」——
那句話的意思是「這份檔案壞了」，真正的情況是「這一格不存在了」。

核心 3496 passed、UI 逐檔全綠、黃金值三份逐項相同。

### 順手：兩條既有的紅（本來就紅，與上面那件事無關），以及它們各自的病根

兩條都**不是程式壞了，是寫下來的東西沒跟上**。

**① `focus` 的契約只寫了一半。** `Step.overlay_marks` 的說明寫著「``focus`` ——
要畫粗的**那一條**的索引」，而 F73 把 GLV 的贏家格改成**四條邊**時，只改了
實作與 UI（`_focus_set` 兩種都吃、`studio.measure_marks` 還寫著「不收窄成
int」），**契約那一行沒動**。於是一條測試照著那一行寫成 `assert focus == 0`，
在 GLV 回一串的那天紅掉 —— 而畫面上一個像素都沒有變。
兩邊一起改：契約寫成「一個索引**或一串**」，測試改成問 UI 真正在用的那支
（`_focus_set(focus) == {0}`）—— **問「哪幾條畫粗」，不要問它是用什麼形狀
表示的**。

**② 一段中文躲在 JS 註解裡。** `core/export/html.py` 的 `_CHUNK_JS` 有一段
`/* … */` 寫著中文，而 `test_ui_english_only` 是對**字串常數**問的，所以它看到
整段 JS 裡有中文。**測試問對了**：那段 JS 會原樣進到寄出去的 HTML 檔，讀原始碼
的人看到的就是那幾行中文。所以搬到 Python 這一側的註解，不是替它開例外。

而搬走的那一刻**它守的規矩就沒人守了** —— 那段註解寫的是「引號用單引號包雙
引號，一個反斜線都不要」，理由是那是 Python 三引號字串、`\"` 會先被吃掉一層
（第一版就是這樣壞的：`SyntaxError: Unexpected string`，而且是**執行期**才炸：
報表產得出來、打得開，只是捲到底之後什麼都不會發生）。所以補了
`test_the_chunk_script_carries_no_backslash_and_no_chinese`。

⚠ **那支測試第一版是錯的，而它綠。** 我原本對**執行期的字串**問「有沒有反斜
線」—— 而被吃掉的正是它自己：把 `\"` 放回去，值裡一個反斜線都沒有，測試照樣
綠，瀏覽器收到的已經是壞的。改成問 **AST 拿到的字面量原文**。兩個 bug 各放回去
一次驗過會紅（中文那半兩種問法都對，因為它不會被吃掉）。

**這一條的形狀值得記住**：規矩寫在被守的東西**自己身上**時，改它的人剛好就是
會把它一起改掉的人。

---

## F73：把 F68 的驗收真的跑完（2026-09-02）

F68 的計畫書最後一行寫著「**真的開起來走一次使用者的情境**」，而那一步一直
沒走。這一輪走了：合成 RSEM（24 顆單張影像，一半是真的）→ 鋪框 → GLV 逐格
挑最異常的那一格 → 判定樹 → 報表。**產出是第三份出貨 recipe**
（`recipes/rsem-worst-box.json`），而路上撿到三件事 —— 三件都不是用讀的
讀得出來的。

**① 一格設定轉一整圈，畫面上與數字上都不會有任何變化。** `roi_reference` 的
`gap`（「離邊界多遠」）對 `place = crossing` 完全沒有作用（那一種只有 `inset`
算數），而那一格照樣顯示得出來。掃 0/1/3 三個值，24 顆的分數**逐位元組相同**。
`box_size` 與 `side` 早就用 `show_when` 藏對了，漏的只有這一格。測試兩半都問：
藏起來的那一種真的沒有作用、**沒藏的那幾種真的有作用**。

**② 報表的琥珀粗框指著錯的地方。** 三個區域接進同一張 GLV 的時候，
`worst_note_for_overlay` 取的是**接線順序第一條 note**（第一個區域）的框與
**它自己的**贏家。於是一顆暗點缺陷的圖上：標題印著 `score=27.753`
（那個數字來自 `between_columns` 正中央那一格），而琥珀粗框畫在 `on_pattern`
左上角一個 **1.3σ** 的框上。**跑得完、有圖、而且是錯的**——第八個。

那段程式碼的註解其實寫著顧慮：「挑一組畫而畫面上不說是哪一組，正是這個 repo
最怕的形狀，所以先只畫第一組，而『第一』是穩定的」。顧慮是對的，解法不是：
穩定地指著錯的地方仍然是指著錯的地方。**改成每一組的框都畫、粗框給分數最高
的那一格** —— 畫全部就沒有「哪一組是誰的」這個問題了（細框的意思是「我量過的
框」，三組長得一樣是因為它們**就是同一件事**）。一個區域的時候逐位元組跟以前
相同，而那是一支測試。

**③ 只鋪在圖案上會漏掉一整類缺陷。** 這是 recipe 長成三張 Region 卡的理由：
暗點掉在兩條之間的溝裡，而只鋪在圖案上的框**正好從它旁邊跨過去**。實測
（同一批資料、同一棵樹，只有「鋪哪裡」不一樣）：只鋪圖案 **75%**、三個都鋪
**96%**。差的那些全部是暗缺陷 —— 每一顆都跑得完、有數字、特徵表上每一格都
正常，而圖上看得見一個黑點。README 那張表配著一支測試，拿掉表就是拿掉測試。

**④「什麼都沒有」要判成 bin 0。** 第一版把三類編成 1/2/3，跑 CLI 出來的是
「正確率 50%、**誤殺率 100%**」—— 而它下面兩行的純度表寫著 bin 1 與 bin 2
各 100% 純。病根是 `export/report._confusion` 的預設判準就是 **`bin != 0`**
（那是 ADC 的慣例，也是這個 repo 自己的），所以「沒有缺陷」用 3 號等於告訴
它每一顆都判成了真缺陷。改成 0 之後同一批資料同一棵樹：**正確率 95.8%、
誤殺率 0%**。一個編號，兩份完全相反的報告。

順手量到的還有兩個，都寫進 `recipes/README.md` 的「要調的幾格」：judge 用
`glv_mean` 比 `glv_std`／`glv_median`／`glv_max` 都好（96% vs 92/83/79），而
**方向選錯比留 `both` 糟得多** —— 這批資料亮暗都有，選 `darker` 從 96% 掉到
71%。那正好是 `direction` 那一格 help 裡寫的那句話（「a layer has both kinds」）
第一次有數字。

**沒有動的一件事**（留給使用者決定）：`rank_by`（「Worst first, by」）決定的是
**哪幾顆有圖**，表格照的是檔案順序。help 講得很清楚（「otherwise the pictures
come out in file order」），但 `limit = 0` 時那句警告寫的是「if you want the
worst at the top」—— 而那件事不會發生。寫進 `test_shipped_recipes.py` 那支測試
的 docstring，不是靠記憶。

核心 3522 passed、黃金值三份逐項相同。

---

## F68：GLV 是抓 defect 的主力卡（2026-09-01）

使用者兩句話定了這一輪：「我希望 GLV 這張卡**遠比現在的功能強大更多**……
因為**抓 defect 就是靠 GLV 吃飯的**」＋「UI 會讓人看不懂，不管是上方畫布設定
跟下方的卡片詳細設定（**尤其是下方**）」。

**動工前逐題問過一輪，而砍掉的比加上的多**（每一條都有使用者的一句話當依據：
逐像素／滑動視窗、位置對位置的像素比對、框跨界、局部基準、框內縮、
Cell-to-cell 當標籤、align 卡、blob——全部不做）。那一輪裡我提的「滑動視窗」
被一句「**框跟缺陷差不多大**」直接砍掉——我在解一個他沒有的問題。

**能力**：方向（最黑／最亮／都要）、贏家那一格的**全套統計量**（`<量>_worst`
——「最黑那格的 Q25」以前只能靠把 judge 改成 q25）、`glv_boxes_over_k`
（一顆髒點 vs 整片漂移）、judge 可以照「跟參照差多少」挑。

**而 judge 那一條第一版是個空包彈，是實測揪出來的**：照 delta／abs_delta／
ratio／contrast／overlap 挑，挑到的格跟照絕對統計量挑**一模一樣**。病根是
參照是一整塊共用的 → `delta` = 這一格的統計量 − **一個常數**，而 leave-one-out
**對整排減同一個數完全免疫**。修法是使用者定調的「**第 i 格對第 i 格**」
（`ref_pairing`，patch 預設）——圖案互相抵消，剩下的才是真的不一樣的地方。
那個限制本身寫成一支測試，不是註解。舊檔案由 `RECIPE_VERSION` 2→3 ＋
`_migrate_glv_ref_pairing` 釘回 `pooled`，數字逐位元組不變。

**版面**：六段（在哪量／跟誰比／怎麼找／要報什麼／哪些像素／輸出），
「跟誰比」排在「怎麼找」之前——因為判準取決於有沒有接參照。膠囊一顆不動。

**接線插槽**（新模組 `ui/wiring_slot.py`）：那四格以前是**唯讀 `QLineEdit`
而且沒有任何專屬樣式**，點下去還會亮 focus 框——看起來就是可以打字。現在
左邊是跟畫布同形狀的符號、中間**沒接線也講後果**（`the whole image` ／
`no reference` ／紅字未接）、右邊挑得動，而**挑了走的是跟畫布拉線同一條路**
（「兩條路存出來的 recipe 逐位元組相同」是一支測試）。

**畫布**：`ParamSpec.role` 讓參照埠畫虛線邊（以前兩顆菱形逐位元組相同）、
標籤接上線之後仍然說得出角色（以前角色的字在最需要時消失）、拖線時接得上的
埠會亮起來（以前完全沒有回饋）、埠距 13→17px。⚠ 要守的不是「抓取圈不重疊」
（就近吸附之下重疊無害），是**瞄得準**。

**設定欄的選項也變成膠囊**（第二輪，使用者：「我希望設定欄這邊也是能像下方
一樣膠囊 icon 配文字，這樣 user 比較會有感覺」）：新型別 `chip_choice`，
這張卡最後三個純下拉沒了。外觀**只有一份**——`_MetricChip` 抽出 `_ChipBase`，
兩族各自只實作「小圖怎麼畫」。判準寫進 `ParamSpec.icons`：意思在圖裡的用
`icon_choice`（字退到 tooltip），意思在字裡的用 `chip_choice`（圖只是錨點）
——所以 CD 那三格一格都不動。值的格式跟 `choice` 一字不差。

**然後套到整張卡片庫**（第三輪，使用者：「同時請整理所有卡片，我認為設定區
都要變成這樣 icon 膠囊 + 文字，並且視覺模型可能要接近會比較好」）：25 格選項
全部變成 `chip_choice`、**61 張新的小圖**住在新模組 `ui/glyphs.py`，共通文法
寫在那份的檔頭（淡的是原本就在那裡的東西、實心的才是這個選項在講的那件事；
一排裡的每一顆共用同一個底）。`icon_choice` **刪掉**；`choice` 留著當退路，
但有一條測試擋著每一張卡。順手修掉兩個 render 出來才看到的：`_spell` 的
`capitalize()` 把「a cell **I** mark myself」改成小寫的 i、長列名把七顆膠囊
擠成五排參差不齊的東西。**而一條既有的測試因此紅了，它是對的** ——
`test_card_invariants` 的「改參數要讓快取失效」只認得 `choice`，
`icon_choice` 從來沒被蓋到；現在三種都算，覆蓋率比這一輪之前還高。

**最上面那一排 preset 也一起**（第四輪，使用者：「最上方的 What do I want to
measure 也是，而且我覺得他有一點太口語」）：三顆鈕變成同一種膠囊，而**圖就是
它們會設成的那幾格的圖**（那一排是捷徑，圖一樣才看得出來；兩張表由一支測試
對起來）。字從帶冠詞的口語短句改成名詞片語，用的是這張卡自己的詞
（`Odd box out` ＝ `Pick the odd one by` 在挑的東西）。膠囊多兩個狀態：灰掉
（線還沒接）與 momentary（preset 不是開關）。⚠ 換過來的時候掉出一個**以前
就在**的 bug：重建那一排只做 `deleteLater()`，而在事件圈跑到之前舊的那幾顆
還在畫面上 —— 以前是按鈕、每次寬度一樣所以完美重疊，看不出來。

**最後使用者從截圖裡揪出一條斜線**（「我看到預覽圖上有 overlay，是框中間有
一條斜線?」）：那本來應該是一個 **X**。`overlay_marks` 從 F32 起就交出兩條
對角線，但 `ImageView` 的 `focus` 只認得一個 index —— 第二條落進 alpha 70、
1 px 那一組，16px 的格子上等於不存在。**而測試把那個形狀寫死了**
（`assert focus == 1  # X 的第一條`）：守的是 bug 的形狀，不是「畫一個 X」
那句話。`focus` 因此放寬成「一個 index 或一串」（一個記號本來就可能不只一條
線），`-1` 仍是「什麼都不畫」的哨兵。**而看了修好的 X 之後使用者說不要畫叉，
要紅粗框** —— F32 不畫框的理由是「跟區域框重疊、**同一個顏色**」，換色加粗就
成立。⚠ 第一版挑琥珀（照抄報表），render 出來幾乎看不出來：`REGION_COLORS` 裡
就有琥珀與橘。由此掉出第二件事：介面的 `danger` 跟第 8 個區域色只差 ΔE 19.9，
而 `!match` 本來就用它 —— 介面的紅是給白底面板用的，這些記號畫的是別人的照片。
所以多兩個權杖 `mark_alert` / `mark_aim`，值跟報表的 `BOX_COLOR` / `AIM_COLOR`
逐位元組相同，兩條測試守著（角色色 vs 每一個區域色 ΔE ≥ 25、兩張表不准漂）。

黃金值三份逐項相同。計畫書：
[`docs/history/plans/F68-glv-defect-hunting.md`](docs/history/plans/F68-glv-defect-hunting.md)。

---

## F69：畫布動了，設定欄要跟著（2026-09-01）

使用者：「在 canvas 上把線切斷時，理論上設定頁也要同步取消（他們是同步的）；
同理，在 canvas 上把線連接時，也要同步設定。」

**model 那一層本來就同步**（剪線 → 那一格真的空掉 —— `_hydrate_regions` 與
`_unpoint_stream` 各自負責）。壞的是**畫面沒有人叫它重讀**：接線／剪線的四條
路裡，只有一條會跟上，而那一條是**碰巧**的 —— 它剛好排在一次預覽前面，而預覽
跑完會順手重建表單。於是同一個動作有時候跟得上、有時候不跟。

修法：`select_node` 裡「把參數畫進設定欄」那一段抽成 `_fill_param_form`，
第二個呼叫端是新的 `_resync_params(dst)` —— 只在**選著的那一張卡**上重畫
（別張卡的線動了就不要重建：重建會丟掉滑桿的拖曳與游標位置）。剪線那一支用
一層外殼把 `finally` 掛上去，因為它底下有五條分支，漏掉一條的症狀正是「大部分
時候會跟上」。

測試對**六個動作**逐一比對「設定欄顯示的」與「線說的」，而且**中間刻意不跑
`processEvents`** —— 讓事件圈跑起來的話，那一次碰巧的預覽會讓這條測試跟著碰巧
變綠。把 `_resync_params` 拿掉驗過會紅。

---

## F72：報表打得開、標註不出界（2026-09-01）

使用者兩件：「html 打開來瀏覽時很卡」＋「patch 上標註的 bin 黑邊會因為 patch
不同 size 導致上方的字彙超出去」。

### 標註（使用者最後選 A —— 只修字，不動尺寸）

字級以前只看**影像寬度**（`w / 320`），完全不看**字有多長** —— 於是字長得比圖
還快：實測 64 px 的 patch 超出 53 px、128 px 超出 27 px、160 px 超出 34 px，
**每一種尺寸都超**。而那條深色底被裁到影像寬、字沒有：超出去那一段是白字直接
壓在樣品上。

現在字級**照字長挑**：由大到小試，塞不下就換更短的寫法（先丟 `score`，再只留
`#id`），最後才截字；底條改成**滿版**，所以那一行在任何底圖上都讀得出來。

⚠ **中途做過另一版又收回來**：先照使用者選的 B 案把標籤移到影像**下面**新加的
一條字幕條上（樣品一個像素都不會被蓋到），render 出來給他看之後定調「算了，
不要改變原尺寸好了」—— 所以蓋回左上角，只留 A 那一半。留這一段是因為那個取捨
下一次還會被問一次：**字幕條不蓋樣品，但輸出尺寸就跟輸入不一樣了**。

### 報表（使用者選 A，**而 A 量出來是錯的**）

我提的 A 案是「不改結構，把版面成本砍掉」。做完一量：**更慢**。

| 版本 | 兩萬顆從打開到可用 |
|---|---|
| 現況 | 6.2 秒（36 萬個 DOM 節點）|
| `table-layout:fixed` ＋ 欄寬 | **11.2 秒** |
| ＋ `content-visibility:auto` | 6.5 秒（＝沒有用）|
| **只寫前 300 列，其餘走 JSON** | **0.42 秒** |

`content-visibility` 對 `tbody tr` 不生效（CSS Containment 不套用在表格內部
元素上）—— 那是我沒查就寫下去的。成本在**節點本身**，不在版面演算法，所以
只有「不要產生那些節點」有用。於是做的是原本排第二的 B：前 300 列照舊寫成
HTML，其餘當一段 JSON 帶著，捲到底接下一批，另有一顆「Show all」。
資料一顆都沒少，檔案還小了一半（6.4 MB → 3.6 MB）。

順手：那個「點一列換圖」的 listener 從**一列一個**（六千個）改成一個委派的
—— 不然後來接上去的列點了沒反應。⚠ 第一版的 JS 在 Python 三引號字串裡寫
`\"`，送到瀏覽器變成 `""` → `SyntaxError`，整段不執行**而畫面看起來只是
「捲到底沒有反應」**。現在引號用「單引號包雙引號」，一個反斜線都沒有。

---

## F71：ADC 那一頁看得懂（2026-09-01）

使用者：「ADC 的設定頁面是不是也加入一些 icon 會比較好（目前的如果沒設定好
空）」—— **那是兩件事**，兩件都做了。

**空狀態**：以前是一行「Nothing sorts the defects yet.」＋一顆鈕，而那顆鈕會
在畫布上長出一棵樹 —— 按之前沒有任何線索知道會發生什麼。現在是三句話配三張
小圖：讀哪些數字 → 每一步問一個問題 → 停在哪個托盤就是哪一類。⚠ **刻意不列
「幾種判定方式」**：二元門檻那個編輯器 2026-08-24 整個拿掉了（使用者：「UI
完全拿掉」），列出不存在的選擇比沒有說明更糟。三張圖畫的是**畫布上真的長那樣
的東西**（菱形＝一個問題、托盤＝一個類別）。

**icon 分三種，判準是那一格有多寬**：

* 「這個數字要怎麼用」（照原值／z／百分位）→ **膠囊**，跟卡片設定區同一套。
  ⚠ 值 `""` 就是「照原值」而不是「沒填」，`ChoiceChips` 認得它。
* 六個比較運算子 → **下拉的每一項帶一張圖**（同一條數線，箭頭往哪、端點實不
  實心）。不做成膠囊是因為那一欄的寬度是使用者拖的（實測預設 437 px），
  六顆擠不進去 —— 而收起來的下拉照樣看得到現在那一顆的圖。
* 特徵下拉 → 每一項前面一顆**那個區域的顏色點**，跟 Feature 表的上標、影像上
  那個框同一個顏色（`RecipeModel.feature_regions`，`bound_specs` 的投影）。

⚠ 順手修掉一個**看不見的**版面 bug：`_ChipFlow` 只設了 `setFixedHeight`，
寬度沒有人講 → `sizeHint` 是 0，放進一個沒有 stretch 的 layout 時整塊被壓成
0 px 寬（膠囊都在、都 `isVisible()`，畫面上什麼都沒有）。ParamForm 那邊看不
出來，因為它是 `addWidget(w, 1)`。

---

## F70：Feature 表上每一列長得一樣（2026-09-01）

使用者：「Feature 這邊顯示有點亂，有些有上綴，有些解釋在中間」＋
「記得就算是不同張 card 得到的 feature 寫法也要一致（增加可閱讀性）」。

**亂在兩件量得出來的事**：

1. **區域名印了兩次**：`region_others_present` 的 base 是**整串**、``region``
   又是 `region_others`，於是畫面上是 `region_others_present`ᵣᵉᵍᶦᵒⁿ_ᵒᵗʰᵉʳˢ。
   量測卡那邊早就是對的（`epi_glv_median` → base `glv_median` ＋ 上標 `epi`）
   —— 同一件事在同一張表上有兩種長相。病根是那個 spec 工廠在三張 Region 卡裡
   **各抄了一份**，三份裡有同一個 bug。收成 `_util.region_spec_maker` 一支，
   規則一句話：**帶區域前綴的名字，base 是前綴後面那一段**。
2. **中間那欄只有 GLV 有字**（`feature_gloss` 只認得 `glv` / `cmp` 兩個
   family），所以 Region 卡那十五列、`cross_*`、`locate_*` 全部空白 ——
   看起來像壞掉，其實是沒人寫過。新的 `Step.FEATURE_HELP` 讓**卡片自己說**
   （在 UI 補一張表最快也最錯：那句話會跟卡片本人的說明漂開，而漂開時畫面
   看起來完全正常）。現在 registry 裡**每一個特徵都答得出那一句**（67/67）。

**跨卡一致**是使用者當場加的第三件事，而它是實際踩到的：`locate_ok` 一張卡寫
「located the pattern」、另一張寫「located the cell」—— 而那兩張正是折進
`roi_reference` 的同兩支，所以兩句話會排在**同一張表上**。同名的一句話因此
住在 `_util.SHARED_FEATURE_HELP`（一份），並補兩支測試：同名不同句就紅、
體例（小寫開頭、不加句號）不一致也紅。

---

## F67：GLV 的「跟誰比」由線決定（2026-09-01）

使用者：「GLV card 這邊的 ROI 接線 我覺得對 user 來說 還是會有點混淆
(Compare against) 跟最上方 What do I want to measure 相關~ 你建議怎麼改會比較好」

**同一個決定在卡上被問了兩次，而且用兩種語言。** 上排那三顆 preset 講樣品
（「The defect's box」）、動的是線；§3 的 `reference` 講拓樸（「another region
on another stream」）、動的是同兩條線的埠在不在。而那一格的五個答案是一張
真值表 —— **參照區域那顆埠有沒有線 × 參照流那顆埠有沒有線** —— 也就是把線
複述了一遍（鐵則 10）。

複述的代價實際存在過三個：兩份說法可以不一致；選回 `none` 時參照那條線
**不會跟著剪掉**（只有 preset 會剪）；而那五個字是軟體的字。

**做法：那一格刪掉，真值表就是那兩顆埠**（`_reference_of` 是唯一出處，
引擎其他地方一行都沒動）。兩顆埠常駐、default 空；`the other regions`
一起走（它就是把 `<n>_others` 接進參照埠，而 F44 的 preset① 教的已經是
接線那一種）；段標題與埠名換成樣品語言（`3 · Compare with` / `Another area`
/ `Another image`）。

**遷移真正的重點是剪線那一半。** 舊檔案裡留下的那條線在 F67 之後**就是
答案** —— 照抄的話，一份只報絕對值的 recipe 會安靜地開始吐 `cmp_*`。所以
`_migrate_reference_into_ports` 對每一種情況都明寫哪一顆留、哪一顆剪。
`the other regions` 是唯一要補線的：一塊的那種**數字與特徵名逐字不變**；
好幾塊的那種以前是逐塊配對，一條線表達不出來 —— 補第一條，而新的一條 lint
對那個形狀講話（同名不同義不准安靜）。**那條 lint 當天訂正過一次**：
它一開始寫在 `configuration_issues`（error，擋住整批跑），而「這兩塊都跟
epi_others 比」是完全合法、有時候正是要的設定 —— 用一條 lint 否決使用者的
意思比不講還糟，所以搬去 `configuration_hints`（warning）。判準是那一句：
**這會不會跑不起來**。

順手做的兩件：`show_when` 多了 `ANY_VALUE`（有值就算數 —— 接線型的參數列不出
允許值）與「一條條件裡的一串名字＝ or」；`ctx.meta["compares"]` 的
`reference_source` 以前只認 `REF_STREAM`，於是「另一塊 @ 另一條流」在面板上
被寫成量測那一條（數字是對的，那行字說錯了它跟哪一張圖比）。

特徵名一個字都沒變、黃金值三份都沒有用到 compare，所以數字不動。
**同一輪的續集：那排 preset 底下那一行字。** 三顆鈕講的是形狀，而卡片上有
兩件事它們不講 —— 量的是哪一塊、以及跟哪一張圖比。所以規矩收成一句不變量：
**鈕 ＋ 那行字 ＝ 這張卡真的在做的事**。對不上時是
`custom - measuring epi_center, compared against mg.`；對得上但接了參照流時，
那行字把整句話說出來（`reference_source` 刻意不進 preset 的偵測 —— 跟另一張圖
比是疊上去的第二個問題，算進去的話最常見的設定會顯示成 custom）。
句子由線組出來，參照那一塊怎麼稱呼問卡片自己（`reference_label`，
從 `_ref_label` 轉正）；**要說什麼住在 model**（`glv_intent_note`），
`studio.py` 只負責畫。

順帶把使用者要的那張排列組合表做成**跑得動的**那一種：四個軸的完整乘積
**80 種**（`tests/test_glv_combinations.py`），逐格斷言鈕、`cmp_*` 出不出來、
參照那一塊叫什麼、那行字、健檢講哪一句。**只有 6 種對得上鈕**，
其餘 74 種是 custom —— 那正是那行字存在的理由。表本身在計畫書裡。

計畫書：[`docs/history/plans/F67-glv-compare-by-wire.md`](docs/history/plans/F67-glv-compare-by-wire.md)。

---
