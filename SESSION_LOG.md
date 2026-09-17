# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| **2026-09-09 起** | 這個檔案（下面）—— **09-09 四輪**（判定樹上找得到 working numbers、「插入數字 ▾」一張卡一組帶說明、**跑與寫拆開＋Re-run**（鐵則 11）、Results 單擊帶主畫面、卡片寫 img/s、縮圖與表格同一份排序／篩選、體檢與十四件待辦）、**09-17**（`.I01` 副檔名不同的 patch TIFF、F102 疊模板前先框一塊、F103 標一格量週期、F104 二維自相關找峰、F105 交錯晶格上的小數週期、F107 文件稽核與七道新守門） |
| 2026-09-01 ～ 09-08 | [`docs/history/2026-09.md`](docs/history/2026-09.md) —— F67/F68 GLV 的「跟誰比」由線決定與抓 defect 的主力卡、F69–F72 設定欄／Feature 表／ADC 那一頁／報表打得開、F73 把 F68 的驗收真的跑完、F74 Region 段只剩一張卡、F75 文件對齊現況、F76 Feature 面板、F77 IQI (OP-301)、F78–F82 畫布的視覺那一批、F83 使用者回報的三個 UI bug、F84 ruff 那道關／`align_off` 的症狀／pack 裡的 378 MB、F85 PEAR 的均勻度、F86 使用者拿去用回來的四件、F87–F89 圖表那一塊、**F90 三把尺**、F91–F94 外部檢視的 P0 與 U6/U7、F95–F100 UI 評審的十七件與二十一件 |
| 2026-08-19 ～ 08-28 | [`docs/history/2026-08b.md`](docs/history/2026-08b.md) —— F42 區域線走 edges、F43–F45 結果表分層／區域接線／FeatureSpec、F46/F47 檔案架構與授權、F48 六個決定、F50 畫布上只剩卡片和線、F51/F52 特徵名與數字只有一種寫法、F53–F57 五件小事、F58–F66 合成資料長成真的那種 layout |
| 2026-08-07 ～ 08-18 | [`docs/history/2026-08.md`](docs/history/2026-08.md) —— F8 純規則 ROI、畫布 n8n 化、Phase 1 收斂、F10、Phase 2 的 Input／Enhance／Region 三段 |
| 2026-07 | [`docs/history/2026-07.md`](docs/history/2026-07.md) —— M0–M7、F7-9…F7-24 前半、兩台機器與搬運通道的成形 |

**切點換過一次，而第四份是在同一個月裡再切的。** 前兩份用的是「上一次合併進
main 的那一輪」，而這條分支從 2026-08-19 起就沒有再併回 `main` —— 那條線因此不再
切得動任何東西，再等下去這個檔案只會一直長（第三份封存之前它是 6,380 行 / 392 KB）。
所以第三份改用**月份**。

**第四份（2026-09-17）沒有再換切點，是量到了**：九月前八天的量本身就夠一份 ——
封存前這個檔案是 2,837 行 / 186 KB，搬走 F67 ～ F100 之後剩 363 行 / 28 KB。
留 09-09 起是因為那四輪定的是鐵則 11（跑不寫、寫是另一個動作），還在被引用。

封存不是整理癖：這個檔案**只增不減**，而它跟著整包被複製進公司機
（`docs/history/` 不進搬運包）。包的大小**不是限制**（2026-08-17 使用者確認直接
複製 raw，見 `AGENTS.md` §2）—— 封存是為了 diff 乾淨與公司機用不到的東西不佔
體積，不是為了那道 1 MB 的線。

---

## F108：封存九月上旬 —— 把搬運包的成長按回去 79 KB（2026-09-17）

F107 量到 `bundle/d4t_bundle.py` 兩週從 2,172 KB 長到 **4,243 KB**。那不只是大小：
包是 lzma+base64，每次 commit 整份改變，**git 沒辦法 delta 壓縮** —— F84 直接量過，
repo 378 MB 裡 **98% 是這一個檔案的歷史版本**。而 `docs/history/` **不進搬運包**
（`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 共用同一份定義），
所以封存是一個**不刪任何內容**就按得回去的動作。

* **切點在 09-08／09-09 之間**（使用者定的）。搬走 F99/F100（09-08）一路到 F67（09-01），
  **2,472 行 / 158 KB** → [`docs/history/2026-09.md`](docs/history/2026-09.md)（第四份封存）。
  留下 09-09 那四輪與 09-17 那幾段 —— **09-09 定的是鐵則 11**（跑不寫、寫是另一個動作），
  還在被引用；而 09-09 同時是 `CLAUDE.md` 封存的日子，切在那裡兩份對得上。
  `SESSION_LOG.md` 從 2,837 行 / 186 KB 縮到 **368 行 / 32 KB**。
* **實際省 79 KB**（4,243 → 4,164 KB），比 2026-09-02 那次的 182 KB 少一半 ——
  **那次連 18 份做完的計畫書一起搬，這次 `docs/plans/` 只剩 F11 一份活的，沒得搬。**
  如實記進 `AGENTS.md` §2 的水位表（那張表是下次有人想省的時候唯一的依據）。
* **唯一准改的是相對連結的深度**（`docs/history/README.md` 白紙黑字：「搬完檔案本身的
  相對連結也要重算（深了一層）」）—— **12 條** `](docs/history/plans/…)` → `](plans/…)`，
  逐條核對過，`test_docs_links` 也綠。內容一個字都沒有改。
* **三處指標跟著改**：`SESSION_LOG` 最上方那張表（第一列重寫成「09-09 起」＋補一列指向
  新封存檔 —— 那一列本來就已經漂了，它列到 09-09 為止，完全沒提 F87/F88/F90–F98/F102–F107）、
  `docs/history/README.md` 的開發紀錄表、以及**該檔 F68 那一列**寫著「驗收由 F73 補跑完，
  見 `../../SESSION_LOG.md`」—— **F73 這一輪被搬走了**，改指新檔。
  最後那一條正是 F107 講的那個盲區：**連結指得到，但指錯地方**，`test_docs_links` 抓不到。
* 順手修一條同族的：`docs/history/README.md` 結尾寫著 `release.py`「超過 85% 就會叫」，
  而 `tools/release.py::bundle_size_report` 的 docstring 自己寫著那一級**早就拿掉了**
  （「一句沒有對應動作的警告只會訓練人忽略警告」）。

⚠ F107 加的兩條水位測試**這次都沒叫**，而那是對的：表上的 max 仍是 4,243，
實際 4,164 落在 `[0.8, 1.25]` 之內。反向那條守的是「一次搬走一大塊卻沒記一筆」，
79 KB 不到那個量級 —— **測試沒叫不等於不用補那一列**，慣例比測試寬。

---

## F107：文件稽核 —— 「名字對、說明錯」那個盲區，補七道守門（2026-09-17）

使用者要求「瀏覽專案後，完整的整理專案內容」，順序定為**先稽核修正、再做總覽**。
逐項驗證出 **20 條漂移**，而它們全部落在同一個盲區裡：
`test_docs_links`（指標）、`test_doc_file_tree`（樹上的名字）、`test_docs_match_registry`
（卡片數／recipe 份數）三支的檔頭**都自己寫著「抓不到『名字對、說明錯』」** ——
這一輪量到的就是那一類。

**最貴的一條不是文件，是使用者看得到的那句話**：`roi_reference` 的 `help` 對使用者說
`"Four ways to find them"`，而 `METHODS` 只有三個（`repeating cells` 2026-08-25 就刪了）。
照那句話去找第四個的人找不到 —— 第二原則說那是 bug，不是文件問題。
同一支檔案的註解還寫著「``method`` 的**兩個**值」。一份文件、三個答案。

其餘幾類（完整清單在這一輪的 diff）：

* **同一份文件裡兩個答案**：`ARCHITECTURE.md` 的「Output 段是三張卡」對「Output 段四張」
  （`output_uniformity` 是 F85 加的）、「三個 method」對「四種找法」；
  CLI 清單漏 `simgen`，而同一份文件下面自己在教 `python -m d4t simgen`。
* **事實已變而文件沒動**：`welcome.py` 那一行還寫著「兩個入口目前收起來」（09-08／09-09
  都開了）；結尾那段還教人去改 `SHOW_SAMPLE_ENTRIES`，而 `test_ui_template_library.py`
  有一條斷言那個名字**不存在** —— 兩邊隔著一個月各說各話。
* **抄了第二份的數字**：`widgets.py`「123 行」抄在 `CLAUDE.md` 與 `ARCHITECTURE.md`
  兩處，實際 137（而 `test_size_ceilings` 的 `FILE_CEILINGS` 早就是 137）——
  那一支的設計規則 4 寫的就是「數字只住在這裡，不要在 `CLAUDE.md` 抄第二份」。
  `studio.py`「6,000 行以上」（7,753）、`tests/` 的「179 檔／2,700+ 支」（252／3,832）、
  `HANDOVER` 的「588 tests／30 秒」、`pyproject` 的「3,126 支」、`ci.yml` 的「2,989」同族。
  **全部改成連結，不是改成新數字** —— 那正是 `CLAUDE.md` 給的退路。
* **那張盯水位的表自己過期了**：`AGENTS.md` §2 停在 2026-09-02 / 2,172 KB，
  實際 4,234 KB —— 兩週又翻一倍，而那張表存在的唯一理由就是盯這件事。
* `recipes/README.md` 少了 `one-image-uniformity.json` 那一節（那份 recipe 有測試跑）；
  `README.md` 的文件索引少了兩份 `docs/*.md`；`HANDOVER` 指「加卡片看 `CLAUDE.md` §5」
  而那在 §3（§ 存在，所以 `test_docs_links` 綠 —— 它檔頭就說了自己抓不到這個）。

**七道新守門全部住進 `tests/test_docs_match_registry.py`**（那一支就是這個主題的家）：
Output 卡數（從 registry 的 `GROUP_OUTPUT` 數）、CLI 子命令（從 `__main__.py` 的
`add_parser` 抽）、文件不得提到 `d4t/ui/` 裡不存在的 `SHOW_*`、`recipes/README.md`
每份 recipe 一節、**`roi_reference` 的 help 宣稱的數量 = `len(METHODS)`**、
README 要連到每一份 `docs/*.md`、bundle 水位不得超出 `AGENTS.md` 那張表 1.25 倍。
既有的「目前 N 份」那條加進 `README.md`。
**十條各自驗過「把錯誤放回去會紅」。**

水位那一條**刻意不是相等**而是上限（×1.25，配一條反向 ×0.8）：bundle 每次 `release.py`
都會長幾 KB，要求逐 KB 相符只會逼每個 commit 去改那張表 —— 那是劇場，不是煞車。

⚠ 兩次撞到尺：`studio.py` 的註解改長了 2 行（`HARD_CAPS` 只准往下）、`recipe.py`
多 1 行 —— 兩處都改回等長，**沒有調高任何一格上限**。

---

## F105：交錯晶格＋粗亮線上的週期量測退化 —— 小數週期、半週期陷阱、第一峰規則（2026-09-17）

外部沙盒拿一張真實大圖（交錯晶格、亮線 10 px、人工驗證 41 × 79.5）回報：投影法回 (41, 40)、
F104 的二維回 (10, 30)、仲裁照抄投影、`build_golden_cell` 再把 79.5 截成 79 —— 格線「靠邊會滑」
（[`docs/history/plans/F105-staggered-thick-lines-period.md`](docs/history/plans/F105-staggered-thick-lines-period.md)）。
使用者定的範圍：小數週期**做到疊圖**、加交錯分數（旋轉角另開 F106）、摘要要顯示每一句量測決定。

* **`period2d`**：第一峰門檻 0.5 → 0.85（線寬峰、交錯半格 0.6–0.67 對真週期 0.92）；諧波鏈擬合次像素
  （`px_sub`）；`autocorr2d` 補零成**線性**自相關（環狀的在視窗不是週期整數倍時拉歪遠諧波，318.47 對 318）；
  `half_period_check` 第三票（沿軸 `ac[2q]` 比 `ac[q]` 高 0.1 才加倍）＋交錯分數。
* **`template`**：`_measure_period` → `MeasuredPeriod`（小數、notes、stagger、doubled）；snap 是**漂移界**
  （整張圖 ≤ 0.5 px）不是絕對值；小數疊圖 = `cv2.resize` 成整數 pitch 再走今天的整數機器（一條路徑、F86
  逐位元組照守、相位搜尋成本不變：tile 大小 3.6 s 對 3.7 s）。`GoldenCell` 加 `period_x/y`、`stagger`、
  `doubled`、`notes`；`origin` 可以是小數（格子左上邊 `x'/s`，不是像素中心 —— 那會少畫一列）。
* **UI**：Cell W／H 改 `QDoubleSpinBox` 餵真的週期（否則 Re-stack 安靜用 80）；格線用 `golden.cell_origins`；
  摘要 `cell 41 x 79.5 px` 並列出每一句 notes（F104 的「交錯」以前畫面上看不到）。
* **測試**：`test_period2d_staggered.py` 十九條（解析式 body-centred fixture、fixture 有牙齒、每條例外規則的反向、
  小數疊得比截成 79 的齊 0.995 對 0.932）；F86 逐位元組測試加 float 型整數參數；一條 UI。`typecheck` 上限 136 → 128。
* **PITFALLS 加兩列**：半週期／線寬陷阱；銳利度與鋪回去的 NCC 都不是週期的裁判（錯的反而更高）。

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
