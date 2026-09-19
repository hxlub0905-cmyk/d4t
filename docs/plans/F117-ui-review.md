# F117 — UI 檢視：待改事項（2026-09-19，已複查）

狀態：**進行中（2026-09-19）** —— F116 拆完了，開始做。第一批挑的是**「一改多條」的根因群**（不是照 P1/P2/P3 走）：
已完成 **A3＋J2**（選到的卡捲進視野）、**I1**（縮圖 bin 顏色走共用調色盤）、**F6＋I5**（報表的數字跟畫面同一條規則）。
中文化（H5）這一輪**不碰**（使用者決定：那一條要先有 2–3 位目標使用者試用）。

⚠ **做的時候查出兩條跟原本寫的不一樣**，已改在下面：**D2** 不是 I1 的同一個病根（撤回它的推測）、**D3** 撤回（那個位數是算過的）。

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
| J1 | **錯誤訊息是給開發者看的**（同 I11／J5／J6 —— 同一個病根）| **設計寫好了：[`F118-user-facing-wording.md`](F118-user-facing-wording.md)**，還沒開工。一句話：`Issue` 加選配的結構化欄位（預設空，所以 63 個產地可以一個一個搬），UI 新增 `ui/wording.py` 組句子；`detail` 不刪，CLI 照舊。⚠ 查出來 **`StepError` 那一半已經有結構了**（`step_key` ＋ 不含前綴的 `detail`），UI 只是沒用它 | ✅ 真的跑出一句來看過（`route 'ebi_patch': the variables ['nosuch_feature'] … (['cd_axis_deg', …20 幾個…])`）|
| F2 | `report.html` 沒有執行資訊：只有 recipe id 與 bin 計數，沒有日期、來源 KLARF、recipe 版本、d4t 版本／build id、取樣方式。檔案一離開電腦就追不回是哪一次跑的（`report.xlsx` 的摘要頁有 recipe 資訊，HTML 沒有） | HTML 報表頭加一塊 metadata，與 xlsx 摘要頁同源 | ✅ 讀過輸出檔全文 |
| G1 | ✅ **做完** —— 而且不只一處：`welcome.py:111` 那一句、`btn_open` 的 tooltip（`the other three kinds`，也點名了 multi-page TIFF）、還有頁尾那句 **`the four kinds of data it reads`**（`INPUT_SOURCES` 是**三**條）| **改法不是「改字」**：`InputSource` 的說明寫著那張表存在的理由是「同一組入口被抄在三個地方…三份會漂」—— **導覽這一段就是那第三份**，從來沒被改成從表上長。所以導覽**不再列清單**（留給真的一種一列的空白狀態），數量一律數出來（`ways_in()`）。`_FOOTER_HINT` 常數改成函式 —— 它在 import 那一刻算，換 profile 之後會停在舊分支（U10 漏網的那一個）| ✅ 三條測試：不准再列清單、數字要用數的、以及一根釘死 `tiff_stack` 的回歸釘 |
| A3 | ✅ **做完** —— 在 Tune 模式選取一張卡，畫布不會把它捲進視野 | 新增 `canvas.ensure_card_visible()`（**只捲，不亮** —— `reveal_cards` 那一套的 hover 高亮是給「指給我看」用的），`select_node` 叫它。⚠ **沒有接進 `set_selected`**：那一支在重建路徑上也會被叫到，接上去使用者每拖一次參數畫布就把他捲回去 | ✅ 附帶發現：`_on_problem_activated` 的說明從 U2 起就寫著「選中那張卡並捲到它」—— **那句話描述的行為一直不存在** |

## P2

| # | 問題 | 建議 | 查證 |
|---|---|---|---|
| A4 | Tune 模式畫布只剩約 300 px 高，7 張卡就縮到 50%，副標與埠名讀不到；而沒選卡時下方參數區只有一行 `(Pick a card…)` 卻占一半以上。**Build 模式下同一份 recipe 在 61% 是讀得到的**，所以問題在 Tune 的空間分配 | 沒選卡時收起參數區；或讓 Tune 的畫布最小高度大一點 | ✅ 兩種模式截圖比對 |
| C1 | Features 面板的**數值被長說明擠到可視範圍外**：值在最右欄，面板預設寬度要水平捲 ~270 px 才看得到，第一眼只看到名字與說明 | 值放在名字旁邊（第二欄），說明放第三欄或 tooltip | ✅ 捲到最右截圖確認值存在 |
| E1 | 有 ground truth 時上方寫 `missed 4`，但**縮圖沒有任何標記**、表格有 `truth` 欄卻沒有把「判定≠答案」的列標出來，要自己逐列比 | 判錯的格子／列加紅框；篩選加「只看判錯的」 | ✅ `gallery._paint_tile` 只看 ok/bin；`results_table` 的 truth 只有文字 |
| F1 | ✅ **做完** —— 而且**三個輸出檔都有**這個坑：CSV、xlsx 的「明細」頁、以及 HTML 報表（它自己寫 `defect/ok/score/bin` 再接特徵欄）| 新增 `detail_feature_keys()`（= `feature_keys` 扣掉 `BASE_COLUMNS`），三個寫檔的地方都用它。⚠ **`feature_keys` 本身沒有動** —— Features 面板與特徵統計要的是「這批跑出了哪些數字」，`score` 是其中之一；扣掉是**明細表**的事。原本的建議是改 `feature_keys()`，那會讓畫面上少一列 | ✅ 三條測試：CSV 表頭不重複、HTML 表頭不重複、`feature_keys` 沒變 |
| G3 | Recipe 範本庫：清單顯示 recipe id（`ebi_die_to_die`）與 `route: ebi_patch`；右邊整塊說明；`score = (no score expression)` 會讓人以為沒有判定（判定其實在樹上） | 顯示名稱＋一句摘要；`route` 換成資料類型白話；score 那行在有判定樹時改寫或拿掉 | ✅ 截圖 |
| G4 | Template 對話框工具列下方那排說明字被截、還壓著一條捲軸 | 說明改 tooltip 或換行 | ✅ 截圖 |
| I1 | ✅ **做完** —— `bin_hex()` 改走 `leaf_color`（失敗＝紅、未判定＝中性沒有被吃掉）。多類別時更明顯：bin 1/2/3 在樹上是三色、在縮圖牆上曾是同一個綠 | 測試**不釘色碼**（釘了換主題就紅然後被關掉），問的是「縮圖色 ＝ 樹的色」 | ✅ ⚠ **verdict chip 沒有跟著改** —— 見 D2 |
| J2 | ✅ **做完**（同 A3 那一行）—— 點問題清單會 `select_node`，所以 A3 修好它就跟著好了 | — | ✅ |
| J5 | 問題清單一行一條、要水平捲動才讀得完；狀態列紅字被截斷 | 換行；每條前面放卡片名＋「帶我去」 | ✅ 截圖 ｜ **併進 [F118](F118-user-facing-wording.md)**（同 J1 的病根）|
| K1 | App 內沒有連到 `docs/USING-*.md` 的入口；手冊只在 repo 裡，廠內使用者不會去翻 | 卡片／視窗的「?」打開對應章節（離線、本機） | ✅ `d4t/ui` 內沒有任何開啟手冊的程式 |
| K3 | 整批跑沒有剩餘時間估計；`.I01` 一批可到 6 萬顆 | 進度加 ETA；可暫停；跑完通知 | ✅ 找不到 ETA 相關程式 |
| H5 | **中文化策略（待使用者決定）**：機制已在（`strings.tr()`、`zh_TW.json` 39 句），卡片名與階段名依既定規則不翻 | 術語留英文、說明翻中文；先依 `_seen` 曝光數翻前 100 句；先請 2–3 位目標使用者試用確認需求 | — |
| I3 | ❓ 改了參數之後，**Results 視窗**裡的舊數字是否標示過期 | 先重現；若沒有，Results 鈕加過期點、`Run trial` 發亮 | ❓ 預覽區有處理（刪卡後會清成 `—`），Results 視窗沒查到 |

## P3

| # | 問題 | 建議 | 查證 |
|---|---|---|---|
| A5 | 判定區卡片寫 `tree hidden — double-click to show`，判定面板卻寫「click a diamond on the canvas」—— 樹收著時看不到菱形 | 面板那句在樹收起時改成「雙擊判定區展開」 | ✅ `tree_scene.py:328` |
| A6 | 深色模式：深色卡片配深色底、連線細灰，對比比淺色低 | 畫布納入 `test_ui_contrast` | ✅ 截圖（主觀程度中） |
| B1 | GLV 最上面「What to measure」三顆在沒接 Region 時都灰掉，第一眼是一排不能按的東西；停用與未選的差別不大 | 未啟用時收成一行提示；停用的樣式再明顯一點 | ✅ 截圖 |
| B2 | 均勻度 GLV 的「How even are the boxes」直接用 feature 名當選項（`range`、`range_pct`、`cv_pct`、`slope_x`） | 顯示白話 label，key 不變 | ✅ 截圖 |
| B3 | 卡片說明一行截斷，沒有展開方式 | 兩行＋more | ✅ |
| B4 | `Write charts` 卡：`At most this many defects 0`（0＝無上限？）、第五格勾選框叫 `chart`、`Enabled` 當 label | 0 顯示 `All`；`Your own chart`；具體動詞 | ✅ |
| C2 | Features 同名多列：`clip_frac` 三列、`peak` 兩列。說明文字有寫「kept under this name because a later card wrote over it」，但要讀完那句才懂 | 名字後面直接帶來源卡（`clip_frac · Normalize(ref)`） | ✅（屬既有設計的呈現問題）|
| D1 | 「preview stops at "norm" — press Esc to run the decision too」：Esc 是「取消選取」，句子是對的，但很難被想到 | 旁邊放一顆 `Run to the end` | ✅ |
| D2 | 均勻度 verdict `measured · bin 0` 是紅色 chip，讀起來像「壞」 | **原因查出來了，而原本的推測不成立**：`VerdictChip` 是**二元 pass/fail**（bin 1 = good、其餘 = bad），那是 U13 刻意的設計 —— `is_real_style` 會把紅綠對調，而且對調時 chip 自己的字跟著翻面（`real`／`nuisance`），還有第三個通道（框線樣式）給色覺缺陷者。改成 `leaf_color` 會把那整套拆掉。**真正的問題是語意**：均勻度那份 recipe 裡 `bin 0` 是「量到了、沒有異常」＝好消息。⚠ **需要使用者決定**：「哪一個 bin 是好消息」該由誰說 —— recipe？還是照 `is_real_style` 那樣由判定段宣告？ | ✅ `feature_text.py:356`（`tone = "good" if is_real_style else "bad"`）|
| ~~D3~~ | ~~`score 0.27895` 小數位多~~ | **撤回** —— 它**已經**走 `numbers.py`，而那 5 位是 F52 算過的：`%.4g` 會把 `99.995` 印成 `100`，於是同一顆在 Results 是 100、點進去是 99.995。縮短它等於把 F52 修掉的 bug 放回來。（移到下面的撤回表）| ✅ `core/numbers.py` 的模組說明 |
| D4 | Decision / Verdict / bin / class / score 多種叫法 | 一張詞彙表 | ✅ |
| E2 | 縮圖第一行是類別名（R5 的刻意設計），但 M 尺寸下被截成 `a spot stands …`；色條沒有圖例 | 截斷時用 tooltip；Results 放 bin 色圖例 | ✅ |
| E3 | 縮圖沒有標出 defect 位置 | 疊量測標記或中心十字 | ✅ |
| E4 | Results 分布圖只有 min/max 刻度、沒有圖例、沒畫判定門檻 | 補刻度與圖例；判定樹用到這個數字時畫出那一刀 | ✅ 截圖 |
| E6 | Results 頂端一條很寬的灰色空條 | 沒在跑時收起 | ✅ |
| E7 | `12% real` 要想一下才懂 | `4 real (missed)` | ✅ |
| F3 | CSV／報表預設不帶 KLARF 座標與原始欄位（機制 `carry_klarf_columns` 已有，是 recipe 沒開） | 出貨的 recipe 預設打開 | ✅ |
| F5 | 均勻度 CSV 欄名 `cells_cells_area_px` —— 區域剛好叫 `cells`，又疊上 ROI 卡自己的 `cells_` 前綴 | 前綴規則遇到同名不疊，或出貨 recipe 換區域名 | ✅ |
| F6 | `report.html` 標題用 recipe id；`glv_pixels` 顯示 `1.638e+04`；表格太寬 | 標題用檔名或描述；整數不用科學記號 | ✅ |
| F7 | `field.html` 四張圖單欄，寬頁右半空白 | 2×2 | ✅ |
| F8 | 熱圖刻度 `27.50`；Box plot 標題靠左、其他置中；Position profile 虛線／點線無圖例；摘要表 `range` 為 `-` | 刻度取整；對齊統一；補圖例 | ✅ |
| G2 | 歡迎頁畫三段（引擎軸），卡片庫是七段（使用者軸）。README 說兩軸刻意並存 | 歡迎頁加一句說明兩者關係即可 | ✅（既有設計，只是第一次見面沒講）|
| G5 | Simgen 區塊順序 1、2 左，3 右，4 左；週期欄顯示 `4.00`（是 setRange 的下限，不是預設值） | 閱讀順序調整；沒有 Golden Cell 時欄位空白 | ✅ |
| G6 | Graph builder 沒資料時 preset 灰掉像普通字；`facet`（`chart_spec.ROLE_FACET`）沒有白話 label | 加說明；`Split into panels by` | ✅ |
| G4b | Template 對話框主按鈕寫死 `Rebuild from image…`，第一次打開也是 | 沒有模板時叫 `Build from image…` | ✅ `template_dialog.py:246` |
| H2 | 底部兩條狀態列；`Run only – nothing written yet…` 在 Results 又出現一次 | 合併 | ✅（主觀）|
| H3 | 空白狀態三種資料說明太長，第三種被截 | 一句話＋更多 | ✅ |
| I2 | 兩個強調色（藍、橘棕） | 收成一個 | ✅（主觀）|
| I5 | ✅ **做完**（含 F6 的數字那一半）—— 但病灶比記的更深：`core/export/html.py` 的 `number()` 用的是 `%.4g`，**正是 F52 算過之後否決掉的那一個**。除了 `1.638e+04`，它還讓 `99.995` 在報表上變成 `100`（**沒有人回報過，但那就是 F52 第 1 條的危害**）| 規則搬進 `d4t/core/numbers.py`（Qt-free），畫面與報表共用；NaN 的收尾各自保留（報表空白、畫面 `NaN`）。**core 不 import ui**，所以是往下放不是往上借 | ✅ 測試逐值比對兩邊，另加一條「core 不准 import ui」|
| I6 | 畫布、Features、Results 之間可以互相指：滑過 Features 一列亮起來源卡、點 Results 欄名跳到那張卡（`reveal_cards` 已有，可沿用） | 延伸既有機制 | 建議 |
| I7 | 每張卡都印 `20 ok · 2051 img/s` | 只在失敗或特別慢時顯示 | 主觀 |
| I8 | 參數區段標題（`1 · Where to measure`）比欄位名小 | 調字級 | ✅ |
| I11 | 刪卡後狀態列只寫 `Removed "dn"`，沒有復原提示 | `已移除 Denoise · 復原（Ctrl+Z）` | ✅ ｜ **併進 [F118](F118-user-facing-wording.md)**（同 J1 的病根）|
| I12 | 對話框主按鈕樣式不一（範本庫 `Load` 藍、Chart settings `OK` 白） | 統一 | ✅ |
| I13 | 符號混用：`—`、` - `、`->`、`→`（歡迎頁 `Score -> bin -> write back`） | 統一 | ✅ |
| I15 | Results 表格橫向捲動時 defect 欄會跑掉（表頭本來就固定） | 凍結第一欄 | ✅ |
| I16 | Results、Chart settings、範本庫不記得視窗大小位置（`d4t/ui` 內沒有 `saveGeometry`） | QSettings 記住並經過 `keep_on_screen` | ✅ |
| J4 | 刪掉中間的卡，上下游斷開 | 型別對得上時提供一鍵補線 | 建議 |
| J6 | warning 太長 | 先講結論 | ✅ ｜ **併進 [F118](F118-user-facing-wording.md)**（同 J1 的病根）|
| K2 | Recipe 差異比較（兩份或存檔前後） | 逐卡逐參數 diff | 建議 |
| K4 | 介面字級可調 | 90／100／115% | 建議 |
| G8 | ❓ 選著 GLV 卡開均勻度圖表視窗是空白（從 `Write charts` 卡開正常） | 先重現；空狀態要說明 | ❓ |
| G9 | ❓ Region check 視窗打開是空的；結束時有 `QThread: Destroyed while thread is still running` | 先重現；載入中要有提示；關窗停執行緒 | ❓ |

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
