# F117 — UI 檢視：待改事項（2026-09-19，已複查）

狀態：**進行中（2026-09-19）** —— F116 拆完了，開始做。第一批挑的是**「一改多條」的根因群**（不是照 P1/P2/P3 走）：
已完成 **A3＋J2**（選到的卡捲進視野）、**I1**（縮圖 bin 顏色走共用調色盤）、**F6＋I5**（報表的數字跟畫面同一條規則）、
**G1**（歡迎頁不介紹打不開的東西）、**F1**（輸出檔的 score 欄不重複）、
**J1＋I11＋J5＋J6**（使用者面的字 —— 整群走 [F118](../history/plans/F118-user-facing-wording.md)）、
**D2**（哪一個 bin 是好消息 —— [F119](../history/plans/F119-which-bin-is-good-news.md)）、
**F2**（報表講得出這是哪一次跑的）＋ **F6 的前半**（標題不再用 recipe id）。
**P1 到此全部關掉。**

之後照「一次修一群相鄰的東西」往下走（2026-09-20，四批）：
**G9＋G8**（關窗要收乾淨、圖表視窗講得出是誰的）、**用詞與符號**（E7／I13／I14／I16）、
**Results 面板**（I15 凍住第一欄、G6 記住視窗大小）、
**E1／E2／E4／D4**（判錯的格子自己說、色階、直方圖上的樹切點、五個字的對照表）、
**A4／C1／I8／B3**（讀得到：畫布分得到高度、數值看得到、段標不比內容小、卡片說明兩行）、
**G3／G4／K3／K1**（範本庫上寫給人看的字、說明不被捲軸壓住、剩餘時間、手冊在 app 裡打得開）、
**B1／B4／J4／I7**（畫布與卡片上那一群：灰掉的按鈕、`Write charts` 的三格、刪卡之後的補線、每張卡的 img/s）。

⚠ **E6 與 I3 沒重現出來**，原樣留著（走查是在 Linux／Noto Sans CJK 上做的，這兩條可能是環境）。
中文化（H5）這一輪**不碰**（使用者決定：那一條要先有 2–3 位目標使用者試用）。

⚠ **做的時候查出兩條跟原本寫的不一樣**，已改在下面：**D2** 不是 I1 的同一個病根（撤回它的推測）、**D3** 撤回（那個位數是算過的）。

## 0-a. 那個分母是 58

表上有 **69 列**，其中 **11 列複查後撤回**（最底下那一節，不要再提）。真正的
待辦是 **58** 條 —— SESSION_LOG 裡 `n/58` 的分母就是這個數。

⚠ 寫在這裡是因為它一度**只活在 SESSION_LOG 裡**，而一個在來源文件上數不出來的
分母，過幾輪就會有人（包括我）把它當成寫錯的數字「修好」。

## 0. 這份紀錄怎麼來的、可信到哪

- 環境：Linux、Qt offscreen、Noto Sans CJK；視窗 1440×900 與 1366×768。**Windows 的字型與 DPI 不同**，字級相關的條目要在公司機上再看一眼。
- 資料：`tools/make_sample.py`（60 顆 EBI patch）、`tools/make_sample_rsem.py` 取一張當均勻度影像；recipe 用 `ebi-die-to-die.json` 與 `one-image-uniformity.json`。
- 程式快照是 **F116 第 1 步進行中**的工作目錄（已有 `ui/gauge_panel.py`）。
- 只看靜態畫面，沒有測拖拉、接線手感。
- 標記：✅ 已對過程式碼或重現 · ❓ 未確認（可能是開的方式不對，要先重現）。
- 優先：**P1** 會讓人看錯或追不回來；**P2** 明顯但不擋路；**P3** 打磨／建議。
- 第一版有 11 條複查後**撤回**（是既有設計或我看錯），理由列在最後一節，避免之後再被提出來。

---

## P1

| # | 問題 | 建議 | 查證 |
|---|---|---|---|
| J1 ✅ | **錯誤訊息是給開發者看的**（同 I11／J5／J6 —— 同一個病根）| **做完了：[`F118`](../history/plans/F118-user-facing-wording.md) 五步全做完。**`Issue` 加選配的結構化欄位（預設空，所以 48 個產地一條一條搬），UI 新增 `ui/wording.py` 組句子；`detail` 不刪，CLI 照舊。⚠ 查出來 **`StepError` 那一半已經有結構了**（`step_key` ＋ 不含前綴的 `detail`），UI 只是沒用它。⚠ 產地是 **48 不是 63**：`klarf_core.Issue` 是另一個 class | ✅ 真的跑出一句來看過（`route 'ebi_patch': the variables ['nosuch_feature'] … (['cd_axis_deg', …20 幾個…])`）|  **已關（F118）**
| F2 ✅ | **做完** —— 而且不只 HTML：`d4t export` 產的 xlsx 以前連 recipe 那一段都沒有（沒傳 `recipe=`），現在兩個路徑都蓋上 `run_info()` 那一塊，**HTML 與 xlsx 同源**。⚠ `d4t export` 蓋的是**那一次跑的時間**（從批次歷史的 `created_utc`），不是現在 —— 對一份三個月前的 run 蓋上今天的日期比沒有日期更糟。原本記的：`report.html` 沒有執行資訊：只有 recipe id 與 bin 計數，沒有日期、來源 KLARF、recipe 版本、d4t 版本／build id、取樣方式。檔案一離開電腦就追不回是哪一次跑的（`report.xlsx` 的摘要頁有 recipe 資訊，HTML 沒有） | HTML 報表頭加一塊 metadata，與 xlsx 摘要頁同源 | ✅ 讀過輸出檔全文 |
| G1 | ✅ **做完** —— 而且不只一處：`welcome.py:111` 那一句、`btn_open` 的 tooltip（`the other three kinds`，也點名了 multi-page TIFF）、還有頁尾那句 **`the four kinds of data it reads`**（`INPUT_SOURCES` 是**三**條）| **改法不是「改字」**：`InputSource` 的說明寫著那張表存在的理由是「同一組入口被抄在三個地方…三份會漂」—— **導覽這一段就是那第三份**，從來沒被改成從表上長。所以導覽**不再列清單**（留給真的一種一列的空白狀態），數量一律數出來（`ways_in()`）。`_FOOTER_HINT` 常數改成函式 —— 它在 import 那一刻算，換 profile 之後會停在舊分支（U10 漏網的那一個）| ✅ 三條測試：不准再列清單、數字要用數的、以及一根釘死 `tiff_stack` 的回歸釘 |
| A3 | ✅ **做完** —— 在 Tune 模式選取一張卡，畫布不會把它捲進視野 | 新增 `canvas.ensure_card_visible()`（**只捲，不亮** —— `reveal_cards` 那一套的 hover 高亮是給「指給我看」用的），`select_node` 叫它。⚠ **沒有接進 `set_selected`**：那一支在重建路徑上也會被叫到，接上去使用者每拖一次參數畫布就把他捲回去 | ✅ 附帶發現：`_on_problem_activated` 的說明從 U2 起就寫著「選中那張卡並捲到它」—— **那句話描述的行為一直不存在** |

## P2

| # | 問題 | 建議 | 查證 |
|---|---|---|---|
| A4 ✅ | **做完** —— `CANVAS_SHARE_TUNE` 0.40 → **0.50**（畫布 263 → 328 px）。那個數字是**評審給的**：Build 的 61% 讀得到、Tune 的 50% 讀不到，縮放大致跟受限的那一邊成正比，`0.40 × 1.22 ≈ 0.49`。⚠ `CANVAS_MIN_PX` **沒有跟著動**（小螢幕的最後一道防線）。⚠ 連帶 `IMAGE_SHARE_TUNE` 0.50 → 0.45 —— 影像佔得比畫布多的那一刻，儀表整塊掉到設定區下面（U8 的「同一條視線」，`test_ui_layout_modes` 當場抓到）。原本記的：Tune 模式畫布只剩約 300 px 高，7 張卡就縮到 50%，副標與埠名讀不到；而沒選卡時下方參數區只有一行 `(Pick a card…)` 卻占一半以上。**Build 模式下同一份 recipe 在 61% 是讀得到的**，所以問題在 Tune 的空間分配| 沒選卡時收起參數區；或讓 Tune 的畫布最小高度大一點 | ✅ 兩種模式截圖比對 |
| C1 ✅ | **做完** —— 一列改成 `名字 | 值 | 單位 | 說明`。說明以前是 `Expanding` 的，它把值一路推到可視範圍外，而**數字正是那個面板存在的理由**；現在說明收在後面、最小寬度 0（窄的時候先被擠掉，全文在 tooltip）。名字有最小寬度，值才排得成一欄（⚠ 是**最小**不是固定：截名字比讓值跳更糟，名字是要打進分數表達式的字）。原本記的：Features 面板的**數值被長說明擠到可視範圍外**：值在最右欄，面板預設寬度要水平捲 ~270 px 才看得到，第一眼只看到名字與說明| 值放在名字旁邊（第二欄），說明放第三欄或 tooltip | ✅ 捲到最右截圖確認值存在 |
| E1 ✅ | **做完** —— 判錯的那一格自己說出來：`real · called nuisance`（⚠ **字也要講**，U13：紅色對色覺缺陷者不可分辨），底色是第二個通道，表頭寫 `truth (2 wrong)`。⚠ 判準**跟正確率那一行同一條**（`bin != 0` 算判定為真缺陷）—— 各訂一套的那天，紅著的列數會跟上面的數字對不起來。⚠ 跑失敗／沒標答案的那幾顆**不算判錯**（沒得比）。原本記的：有 ground truth 時上方寫 `missed 4`，但**縮圖沒有任何標記**、表格有 `truth` 欄卻沒有把「判定≠答案」的列標出來，要自己逐列比| 判錯的格子／列加紅框；篩選加「只看判錯的」 | ✅ `gallery._paint_tile` 只看 ok/bin；`results_table` 的 truth 只有文字 |
| F1 | ✅ **做完** —— 而且**三個輸出檔都有**這個坑：CSV、xlsx 的「明細」頁、以及 HTML 報表（它自己寫 `defect/ok/score/bin` 再接特徵欄）| 新增 `detail_feature_keys()`（= `feature_keys` 扣掉 `BASE_COLUMNS`），三個寫檔的地方都用它。⚠ **`feature_keys` 本身沒有動** —— Features 面板與特徵統計要的是「這批跑出了哪些數字」，`score` 是其中之一；扣掉是**明細表**的事。原本的建議是改 `feature_keys()`，那會讓畫面上少一列 | ✅ 三條測試：CSV 表頭不重複、HTML 表頭不重複、`feature_keys` 沒變 |
| G3 ✅ | **做完** —— 清單第一行改成**作者自己寫的那一句**（截到 72 字，問句保留問號），第二行 `route: ebi_patch` → `patch images`（白話住 `scope.KIND_WORDS`，認不得的 kind **原樣回去**：猜一個漂亮名字會把線索蓋掉）。右邊那塊：走判定樹的 recipe 不再印 `score = (no score expression)`（那句話讀起來像**這一份不會判定**），改成 `Sorts with a decision tree on the canvas (N classes)`；門檻跟著 score 走，一樣不印。⚠ 數類別讀的是**生的 JSON**，不是 `DecideSpec` —— 壞掉的檔案要變成一列紅字，不是讓整個庫開不起來。原本記的：清單顯示 recipe id 與 `route: ebi_patch`；`score = (no score expression)` 會讓人以為沒有判定 | 顯示名稱＋一句摘要；`route` 換成資料類型白話；score 那行在有判定樹時改寫或拿掉 | ✅ 截圖 ｜ 守門：`tests/test_ui_template_words.py`（8 條）|
| G4 ✅ | **做完** —— 病灶在版面樹上看不出來：那句說明被包進了 `fit_screen.scroll_row`，而那一支把高度鎖成「一列鈕 ＋ 捲軸」。⚠ **鈕排不下要橫向捲，說明排不下要換行 —— 兩種相反的處理不能待在同一個容器裡。** 現在它是捲軸外面一個會換行的 label | 說明改 tooltip 或換行 | ✅ 截圖 ｜ 守門：`tests/test_ui_template_words.py`（2 條，含「長說明會長高」）|
| I1 | ✅ **做完** —— `bin_hex()` 改走 `leaf_color`（失敗＝紅、未判定＝中性沒有被吃掉）。多類別時更明顯：bin 1/2/3 在樹上是三色、在縮圖牆上曾是同一個綠 | 測試**不釘色碼**（釘了換主題就紅然後被關掉），問的是「縮圖色 ＝ 樹的色」 | ✅ ⚠ **verdict chip 沒有跟著改** —— 見 D2 |
| J2 | ✅ **做完**（同 A3 那一行）—— 點問題清單會 `select_node`，所以 A3 修好它就跟著好了 | — | ✅ |
| J5 ✅ | 問題清單一行一條、要水平捲動才讀得完；狀態列紅字被截斷 | 換行；每條前面放卡片名＋「帶我去」 | ✅ 截圖 ｜ **併進 [F118](../history/plans/F118-user-facing-wording.md)**（同 J1 的病根）|  **已關（F118 第 3～4 步）**
| K1 ✅ | **做完** —— 那句話底下是**兩個**問題：他不知道有這份東西、而且他打不開（公司機上不保證有任何一個看得懂 `.md` 的程式）。所以入口長在**用得到它的那張卡上**（六張卡 ＋ simgen 視窗），內容由 d4t 自己畫（`QTextBrowser.setMarkdown`，`d4t/ui/manual.py`）。⚠ **不准把檔案交給作業系統開**（`QDesktopServices.openUrl`）：那是一台受限的機器上會失敗得很難看的一步，而失敗的時候畫面上什麼都不會發生 —— 手冊裡指向原始碼與外部網址的連結一律不跟。⚠ 哪張卡配哪一份寫在**卡片自己身上**（`Step.manual`），不在 UI 的對照表上：那會變成「按卡片名字分支」的第 N 處，而且卡片改名那天沒有人會想到去改它 | 卡片／視窗的「?」打開對應章節（離線、本機） | ✅ `d4t/ui` 內沒有任何開啟手冊的程式 ｜ 守門：`tests/test_ui_manual.py`（13 條，含**反向測試**：`docs/` 裡每一份手冊都要有人連得到）|
| K3 ⚠ | **做了 ETA 那一半**（`run_controller.eta_text`）：`Running: 20000 / 60000  ·  about 20 min left`。⚠ **頭幾顆不算數** —— 第一顆要載影像、暖快取、開 worker，拿它去乘六萬會生出一個大到荒謬的數字，而一個一看就知道是假的估計會讓使用者連後面真的那個也不信（門檻：5 顆 ＋ 2 秒，不到就**一個字都不講**）。用整批平均而不是瞬時速度（平均自己會平滑），秒取整到 5（同一句話要站得住幾秒）。**「可暫停」與「跑完通知」沒做** —— 暫停要動 worker 的協定、通知要碰系統匣，兩件都不是這一輪的範圍 | 進度加 ETA；可暫停；跑完通知 | ✅ 找不到 ETA 相關程式 ｜ 守門：`tests/test_ui_eta.py`（12 條）|
| H5 | **中文化策略（待使用者決定）**：機制已在（`strings.tr()`、`zh_TW.json` 39 句），卡片名與階段名依既定規則不翻 | 術語留英文、說明翻中文；先依 `_seen` 曝光數翻前 100 句；先請 2–3 位目標使用者試用確認需求 | — |
| I3 | ❓ 改了參數之後，**Results 視窗**裡的舊數字是否標示過期 | 先重現；若沒有，Results 鈕加過期點、`Run trial` 發亮 | ❓ 預覽區有處理（刪卡後會清成 `—`），Results 視窗沒查到 |

## P3

| # | 問題 | 建議 | 查證 |
|---|---|---|---|
| A5 ✅ | **做完** —— 面板拿得到畫布的收合狀態（`set_tree_collapsed`），樹收著時改講「double-click the Decision card on the canvas to show the tree, then click a diamond」。原本記的：判定區卡片寫 `tree hidden — double-click to show`，判定面板卻寫「click a diamond on the canvas」—— 樹收著時看不到菱形| 面板那句在樹收起時改成「雙擊判定區展開」 | ✅ `tree_scene.py:328` |
| A6 | 深色模式：深色卡片配深色底、連線細灰，對比比淺色低 | 畫布納入 `test_ui_contrast` | ✅ 截圖（主觀程度中） |
| B1 ✅ | **做完** —— 沒接線的時候**那一排不畫**，只留標題與那句 `Wire a Region card into “Region” first.`。⚠ **不是 `title=""`**：標題留著，因為它講的是「接好線之後這裡會有一個選擇」—— 整段收掉的話，使用者不會知道自己少了什麼。順帶把舊的那條規則變成結構上的保證：灰掉的東西 Qt 只擋得住滑鼠，鍵盤與直接呼叫擋不到，而**不存在的東西沒有這個問題**。原本記的：三顆在沒接 Region 時都灰掉，第一眼是一排不能按的東西 | 未啟用時收成一行提示；停用的樣式再明顯一點 | ✅ 截圖 ｜ 守門：`tests/test_ui_glv_intent.py`（含反向：接好線那三顆要回來）|
| B2 ✅ | **做完** —— `multi_choice` 也收 `choice_labels`，格子上寫 `Gap (gray levels)` / `Spread (%)` / `Tilt across`，**值還是鍵**（跟著 box 的屬性走，不跟著 `box.text()` 走 —— 讀字的那一版會把白話名字存進 recipe）。原本記的：均勻度 GLV 的「How even are the boxes」直接用 feature 名當選項（`range`、`range_pct`、`cv_pct`、`slope_x`）| 顯示白話 label，key 不變 | ✅ 截圖 |
| B3 ✅ | **做完** —— 卡片說明改成**兩行**（`_HintLabel(max_lines=2)`），放不下的還是有省略號、全文照舊在 tooltip。⚠ 自己折行：Qt 的 `elidedText` 只認一行，而 `wordWrap=True` 的 QLabel **不會省略** —— 它會一直長高，把底下的參數推出畫面。⚠ 切在字之間，不切在字中間。原本記的：卡片說明一行截斷，沒有展開方式| 兩行＋more | ✅ |
| B4 ✅ | **做完，而三件事是三種不同的錯**。(1) `0` 是一個**沒有名字的特殊值** → 新增 `ParamSpec.min_label`（Qt 的 `specialValueText`），三張卡上寫著 `LIMIT_ZERO_HELP` 的那一格**都**補上，不只被點到的那張。(2) 第五格 `chart` 是 **recipe 的鍵漏到畫面上** → 接上早就寫好的 `CHART_LABELS`；⚠ **存進 recipe 的值一字未動**（不然要付一道遷移，檔名 `-chart.svg` 也要跟著改）。(3) `Enabled` 是 `param_form` 寫死給所有 bool 的**通用詞** → 字搬到勾選框上（十一個 bool 的 label 讀起來都正好是一句「勾了會發生什麼」），名字欄由 `_label_is_echo` 收起來 | 0 顯示 `All`；`Your own chart`；具體動詞 | ✅ ｜ 守門：`tests/test_ui_card_fields.py`（12 條，含兩條反向）|
| C2 | Features 同名多列：`clip_frac` 三列、`peak` 兩列。說明文字有寫「kept under this name because a later card wrote over it」，但要讀完那句才懂 | 名字後面直接帶來源卡（`clip_frac · Normalize(ref)`） | ✅（屬既有設計的呈現問題）|
| D1 ✅ | **做完 —— 而且句子本身也不是對的。** `Esc` 走的是 `pipeline.clear_selection()`，那一支只放掉**畫布**那一份選取，而預覽停在哪裡看的是 `win.selected_node`（`_run_preview` 的 `upto`）—— 按了 Esc 框不見了，預覽照樣停在同一張卡上。修了兩件事：①`studio_layout.clear_selection()` 兩份一起放並重跑預覽；②最後那幾個字做成**連結**（同 `decide_path` 的先例 U11），Esc 照樣有效、寫在 tooltip 上。原本記的：「preview stops at "norm" — press Esc to run the decision too」：Esc 是「取消選取」，句子是對的，但很難被想到| 旁邊放一顆 `Run to the end` | ✅ |
| D2 ✅ | 均勻度 verdict `measured · bin 0` 是紅色 chip，讀起來像「壞」 | **原因查出來了，而原本的推測不成立**：`VerdictChip` 是**二元 pass/fail**（bin 1 = good、其餘 = bad），那是 U13 刻意的設計 —— `is_real_style` 會把紅綠對調，而且對調時 chip 自己的字跟著翻面（`real`／`nuisance`），還有第三個通道（框線樣式）給色覺缺陷者。改成 `leaf_color` 會把那整套拆掉。**真正的問題是語意**：均勻度那份 recipe 裡 `bin 0` 是「量到了、沒有異常」＝好消息。⚠ **需要使用者決定**：「哪一個 bin 是好消息」該由誰說 —— recipe？還是照 `is_real_style` 那樣由判定段宣告？ | ✅ `feature_text.py:356`（`tone = "good" if is_real_style else "bad"`）|  **已關（[F119](../history/plans/F119-which-bin-is-good-news.md) 五步）**：葉子自己標 `outcome`，膠囊的顏色／字／框線三條都吃它。⚠ **實測是三份出貨 recipe 全反**，不只均勻度那一條
| ~~D3~~ | ~~`score 0.27895` 小數位多~~ | **撤回** —— 它**已經**走 `numbers.py`，而那 5 位是 F52 算過的：`%.4g` 會把 `99.995` 印成 `100`，於是同一顆在 Results 是 100、點進去是 99.995。縮短它等於把 F52 修掉的 bug 放回來。（移到下面的撤回表）| ✅ `core/numbers.py` 的模組說明 |
| D4 ✅ | **做完，而且原本的推測要修正** —— 掃過整個畫面：**沒有亂用的同義詞**（`grade`／`bucket`／`judgement` 一個都沒有），五個字各自都很一致。缺的是**沒有任何地方說它們怎麼串起來**。所以加的不是一次重新命名，是歡迎頁上**一張看得到的表**（順序是使用者遇到它們的順序：score → decision → class → bin → verdict），配一條「不准長出第六種叫法」的掃描。原本記的：Decision / Verdict / bin / class / score 多種叫法| 一張詞彙表 | ✅ |
| E2 ✅ | **複查：圖例已經有了** —— 判定列（`VerdictBand`）就在同一個視窗最上面、而且不在 splitter 裡（拖不掉），一列一個類別帶著顏色。I1 之後兩邊顏色真的一樣了，而 `tests/test_ui_tile_legend.py` 盯著它不漂（bin 0 那一格的顏色是呼叫端給的，少傳一個參數圖例就開始說謊）。縮圖名字的截斷**維持原樣**：省略＋停上去讀全（F99 P0-4）＋三段尺寸，寬度不是免費的。原本記的：縮圖第一行是類別名（R5 的刻意設計），但 M 尺寸下被截成 `a spot stands …`；色條沒有圖例| 截斷時用 tooltip；Results 放 bin 色圖例 | ✅ |
| E3 | 縮圖沒有標出 defect 位置 | 疊量測標記或中心十字 | ✅ |
| E4 ✅ | **做完** —— ①x 軸從兩端兩個刻度變成五格；②**判定樹切在這個數字的哪裡**畫出來了（`decide_tree.cuts_on`，細點線＋條件文字）。⚠ 看「Score」時不畫那幾刀：那一格有自己**拖得動**的門檻線，兩種線混在一起會讓人以為樹上那幾刀也拖得動。⚠ 複合條件**不猜位置**（猜一條畫上去比不畫糟得多）。圖例見 E2。原本記的：Results 分布圖只有 min/max 刻度、沒有圖例、沒畫判定門檻| 補刻度與圖例；判定樹用到這個數字時畫出那一刀 | ✅ 截圖 |
| E6 | Results 頂端一條很寬的灰色空條 | 沒在跑時收起 | ✅ |
| E7 ✅ | **做完** —— `12% real` → `4/12 real`（畫面與判定面板兩處）。百分比沒有分母就要人心算：`12% 的什麼`？這一類可能只有 8 顆，標過答案的可能只有 3 顆。原本記的：`12% real` 要想一下才懂| `4 real (missed)` | ✅ |
| F3 | CSV／報表預設不帶 KLARF 座標與原始欄位（機制 `carry_klarf_columns` 已有，是 recipe 沒開） | 出貨的 recipe 預設打開 | ✅ |
| F5 | 均勻度 CSV 欄名 `cells_cells_area_px` —— 區域剛好叫 `cells`，又疊上 ROI 卡自己的 `cells_` 前綴 | 前綴規則遇到同名不疊，或出貨 recipe 換區域名 | ✅ |
| F6 | ~~標題用 recipe id~~（**做完**：改成「使用者打的字 → recipe 的描述 → recipe id」）、~~`glv_pixels` 顯示 `1.638e+04`~~（**I5 做完了**）；**剩下：表格太寬** | 標題用檔名或描述；整數不用科學記號 | ✅ |
| F7 | `field.html` 四張圖單欄，寬頁右半空白 | 2×2 | ✅ |
| F8 | 熱圖刻度 `27.50`；Box plot 標題靠左、其他置中；Position profile 虛線／點線無圖例；摘要表 `range` 為 `-` | 刻度取整；對齊統一；補圖例 | ✅ |
| G2 | 歡迎頁畫三段（引擎軸），卡片庫是七段（使用者軸）。README 說兩軸刻意並存 | 歡迎頁加一句說明兩者關係即可 | ✅（既有設計，只是第一次見面沒講）|
| G5 | Simgen 區塊順序 1、2 左，3 右，4 左；週期欄顯示 `4.00`（是 setRange 的下限，不是預設值） | 閱讀順序調整；沒有 Golden Cell 時欄位空白 | ✅ |
| G6 ✅ | **做完** —— `facet` → 「Split into panels by」；preset 一顆都按不動時多一句「Run a trial first…」（⚠ 停用的 widget 收不到 tooltip，所以那句話要寫在畫面上）。原本記的：Graph builder 沒資料時 preset 灰掉像普通字；`facet`（`chart_spec.ROLE_FACET`）沒有白話 label| 加說明；`Split into panels by` | ✅ |
| G4b | Template 對話框主按鈕寫死 `Rebuild from image…`，第一次打開也是 | 沒有模板時叫 `Build from image…` | ✅ `template_dialog.py:246` |
| H2 | 底部兩條狀態列；`Run only – nothing written yet…` 在 Results 又出現一次 | 合併 | ✅（主觀）|
| H3 | 空白狀態三種資料說明太長，第三種被截 | 一句話＋更多 | ✅ |
| I2 | 兩個強調色（藍、橘棕） | 收成一個 | ✅（主觀）|
| I5 | ✅ **做完**（含 F6 的數字那一半）—— 但病灶比記的更深：`core/export/html.py` 的 `number()` 用的是 `%.4g`，**正是 F52 算過之後否決掉的那一個**。除了 `1.638e+04`，它還讓 `99.995` 在報表上變成 `100`（**沒有人回報過，但那就是 F52 第 1 條的危害**）| 規則搬進 `d4t/core/numbers.py`（Qt-free），畫面與報表共用；NaN 的收尾各自保留（報表空白、畫面 `NaN`）。**core 不 import ui**，所以是往下放不是往上借 | ✅ 測試逐值比對兩邊，另加一條「core 不准 import ui」|
| I6 | 畫布、Features、Results 之間可以互相指：滑過 Features 一列亮起來源卡、點 Results 欄名跳到那張卡（`reveal_cards` 已有，可沿用） | 延伸既有機制 | 建議 |
| I7 ✅ | **做完** —— 卡片上那一行只留給**失敗**（永遠講）與**瓶頸**（`loud_nodes`）。⚠ 門檻是一句話：**它一張比其他所有卡加起來還久**（`SLOW_SHARE = 0.5`）。第一版寫三分之一，而它在兩張卡的批次上破功：兩張一樣快的各佔 50%，於是其中一張被指成瓶頸 —— 而那兩張一模一樣。⚠ **不是把數字丟掉**：每一張卡的速率照樣量得到，它搬進 tooltip（`Last run: …`）—— 丟掉一個量得到的數字，跟把它印七遍一樣糟 | 只在失敗或特別慢時顯示 | 主觀 ｜ 守門：`tests/test_ui_quiet_canvas.py`（13 條，含「反向：數字不准弄丟」）|
| I8 ✅ | **做完** —— `paramSection` 從 `font_tiny`（10px）改成 `font_body`（13px）。它底下的欄位名就是 13px —— 一個**比內容小**的標題讀起來像註腳，眼睛會從它上面滑過去。它仍然是招牌（較淡的顏色＋底線），只是不再比自己的內容小。原本記的：參數區段標題（`1 · Where to measure`）比欄位名小| 調字級 | ✅ |
| I11 ✅ | 刪卡後狀態列只寫 `Removed "dn"`，沒有復原提示 | `已移除 Denoise · 復原（Ctrl+Z）` | ✅ ｜ **併進 [F118](../history/plans/F118-user-facing-wording.md)**（同 J1 的病根）|  **已關（F118 第 1 步）**
| I12 | 對話框主按鈕樣式不一（範本庫 `Load` 藍、Chart settings `OK` 白） | 統一 | ✅ |
| I13 ✅ | **做完** —— `->` 全部改成 `→`（8 處；`→` 在 WGL4 裡，Segoe UI 蓋得到，而 repo 本來就有 25 處在用它）。`tests/test_ui_symbols.py` 擋回頭，配一條反向測試（把走查看到的那句話餵回去，確認判準會咬它）。原本記的：符號混用：`—`、` - `、`->`、`→`（歡迎頁 `Score -> bin -> write back`）| 統一 | ✅ |
| I15 ✅ | **做完** —— 新的 `ui/frozen_column.py`：疊第二個 view 上去（Qt 官方那個 frozen-column 的做法），**共用 model 與 selection model**（各自一份的話，點左邊選到的列跟右邊亮起來的不是同一列）。⚠ 主表那一欄照樣留著不藏 —— 藏起來的話它的寬度就不再參與版面，右邊的內容會滑到凍結欄底下。⚠ 接法是包住 `resizeEvent`，不是叫呼叫端記得呼叫 `sync()`。原本記的：Results 表格橫向捲動時 defect 欄會跑掉（表頭本來就固定）| 凍結第一欄 | ✅ |
| I16 ✅ | **做完** —— 新的 `ui/geometry.py`（`remember`／`restore`），三個視窗都接上。⚠ 還原完一定過一次 `keep_on_screen`（拔掉第二個螢幕之後，存下來的位置會落在沒有螢幕的地方 —— 那是一個按了沒反應的按鈕）。⚠ 最小化／全螢幕時**不存**。⚠ 它是「第四個會寫磁碟的東西」，所以先做出覆寫點 `geometry.SETTINGS`（CLAUDE.md §4）。原本記的：Results、Chart settings、範本庫不記得視窗大小位置（`d4t/ui` 內沒有 `saveGeometry`）| QSettings 記住並經過 `keep_on_screen` | ✅ |
| J4 ✅ | **做完 —— 而斷開本身是對的**（F10-5：殘留的線會接到一張使用者從來沒接過的新卡）。真正的問題是接回來要重拉一次。⚠ **是提議，不是自動補線**（鐵則 10：畫布上每一條線都是使用者拉的）—— 刪完狀態列掛一顆 `Reconnect`，按下去才成真，而且整批算**一步復原**。⚠ 哪一條是「穿過去」的那一條：一條就是它，好幾條的時候只認**複數那一格**（`image_keys`，CLAUDE.md 的單複數規矩）；兩個都問不出來（`subtract` 的 `a`／`b`）就**不提議** —— 猜錯一條線會安靜地算出一批看起來很正常的數字。⚠ 按下去走的是**跟手拉線同一條路**（`canvas_edges.connect`），不是 `model.add_edge` 的捷徑。順帶：那顆鈕讓 `studio.py` 長了 12 行，而它那一格是 `HARD_CAPS` —— 整支 `_on_remove_requested` 因此搬進 `canvas_edges.py`（那件事從頭到尾都是線的事），`studio.py` 上只剩兩行門面 | 型別對得上時提供一鍵補線 | 建議 ｜ 守門：`tests/test_ui_bridge_after_delete.py`（13 條）|
| J6 ✅ | warning 太長 | 先講結論 | ✅ ｜ **併進 [F118](../history/plans/F118-user-facing-wording.md)**（同 J1 的病根）|  **已關（F118 第 4 步）**
| K2 | Recipe 差異比較（兩份或存檔前後） | 逐卡逐參數 diff | 建議 |
| K4 | 介面字級可調 | 90／100／115% | 建議 |
| G8 ✅ | **做完** —— 重現之後是**兩件事**：①空狀態只寫 `Nothing to plot yet`，沒講下一步（現在補「run a trial first」）；②這個視窗只有 `Charts folder` 那張卡餵得動，選了別張卡之後 `_refresh_charts_window` **安靜地 return**，視窗還畫著上一張卡的數字而一個字都沒說（現在講「from “Charts folder” — select that card to follow along」）。⚠ 走查寫的「空白」是①，而②更危險 | 先重現；空狀態要說明 | ❓ |
| G9 ✅ | **做完，而且是真的 bug** —— `closeEvent` 列了一張**六個** worker 的表，而視窗身上有**八個**：`region_check_worker` 與 `calibrate_worker` 從來沒有被停過（`QThread: Destroyed…` 是未定義行為，最壞是當掉）。名單改成 `workers.owned_workers()` 自己找，`tests/test_ui_shutdown.py` 問的是「找到的每一個都停了嗎」。順手：子視窗也讀 `_open_windows()` 那一份，不再抄第二份 | 先重現；載入中要有提示；關窗停執行緒 | ❓ |

---

## 撤回（複查後不成立，不要再提）

| 原編號 | 原本說的 | 為什麼撤回 |
|---|---|---|
| A1 | 畫布縮小後字讀不到 | 只在 Tune 模式成立，併入 A4；Build 模式 61% 讀得到 |
| A2 | 版面兩欄、線繞回，應改成由左到右分層 | **已經是分層排版**（`layout_columns`：欄＝拓撲深度），兩欄是刻意的換行（F7-9：一排太長會縮到讀不到字）；還有 `tidy()` |
| C1（原）| Features 只有名字沒有值 | 值存在，只是被擠到右邊（改寫成新的 C1） |
| C3 | 內部欄位露出來 | 已有 `Diagnostics` 分組是既有設計 |
| E5 | `All measurements (7)` 卻只看到一欄 | 那是刻意的分層表：判定欄預設可見，按鈕整批展開其餘 |
| F4 | CSV 照字母排、全精度 | 刻意的（「這張表就是 feature vector，可直接餵 ML」）；資料檔本來就該保留全精度 |
| H1 | `First ▾` 看不懂 | 跟旁邊的數字框連讀是「First 60 defects」，下拉每一項有 tooltip |
| I9 | 預覽沒有像素資訊 | 已有：滑過發 `cursor_info`，可平移、雙擊 fit |
| I14 | 快捷鍵看不到 | `_set_tip` 會自動把快捷鍵補進 tooltip |
| J3 | 刪卡後預覽還顯示舊判定 | 我截圖太快；等預覽跑完會清成 `—` 並顯示問題 |
| K5 | 在分布圖上拖門檻線 | 判定樹編輯器已有可拖的門檻線（`threshold_view.ThresholdHistogram`） |
| D3 | `score 0.27895` 小數位多 | **它已經走 `numbers.py` 了。** 那 5 位有效數字是 F52 算過的決定：`%.4g` 會把 `99.995` 印成 `100`，於是同一顆在 Results 是 100、點進單顆是 99.995 —— 縮短它等於把 F52 修掉的 bug 放回來。⚠ 這一條的教訓值得留著：**「看起來太長」不等於「沒走共用的那一支」** —— 先去讀那一支為什麼選這個位數 |

## 做得好的（改的時候不要改掉）

- 判定用白話（`a spot stands out · bin 1`）＋判定路徑。
- 主動提醒（「這張卡把 2.5% 像素壓到頭尾…」、`cells under 400 pixels — spread statistics are not reliable`）。
- Results：分類摘要＋準確度＋`Pin as baseline`＋只重判的 `Re-run`；分層表格。
- 參數區 `Change ▾`／`Connect ▾` 與「absolute numbers only」這種說明後果的小字。
- tooltip 自動帶快捷鍵；預覽滑過有像素資訊；判定樹有可拖的門檻線。
- 均勻度四張圖、Chart settings 的即時預覽。1366×768 放得下。
