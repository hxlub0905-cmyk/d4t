# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄按月封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| 2026-08 起 | 這個檔案（下面） |
| 2026-07 | [`docs/history/2026-07.md`](docs/history/2026-07.md) —— M0–M7、F7-9…F7-24 前半、兩台機器與搬運通道的成形 |

封存不是整理癖：這個檔案**只增不減**，而它跟著整包被複製進公司機。
包的大小**不是限制**（2026-08-17 使用者確認直接複製 raw，見 `AGENTS.md` §2）——
封存現在是為了 diff 乾淨與公司機用不到的東西不佔體積，不再是為了那道 1 MB 的線。

---

## Phase 2：Region 段收斂（2026-08-18，第十五輪 —— 這一輪合併進 main）

### ⏩ 交接：下一個 session 從這裡開始

**Region 段收斂了。** 四種找 ROI 的方法都在，而且輸出契約一致：

| 卡 | 靠什麼找 | 什麼時候用 |
|---|---|---|
| **Profile**（`roi_cross`）| 投影曲線上的條紋 | patch 上看得到地標 |
| **Template**（`roi_template`）| 在一個 golden cell 上畫好的區域 | 兩種都行：**patch**（cell 比它大，落一份）與**單張大圖**（cell 比它小，每一份都畫）|
| **GDS layers**（`roi_from_mask`）| GLAS 匯出的 label map | 非週期性的版圖，而且拿得到 GDS |
| **Mask from regions**（`roi_mask`）| 上面三張的結果 → 一條 0/255 影像流 | 要把區域交給影像段（`normalize` 的 `Use only`）|

每一張對它吐的**每一個**區域都寫同一組五個：`present` / `boxes` / `area_px` /
`clipped` / `edge_dropped`（`_util.REGION_FACTS`）。下游拿一個區域名就問得出五件
事，不必知道是誰找的。

**接下來照 `docs/ROADMAP.md` 走。** Region 段剩的尾巴只有「模板過期健檢」。
真實 GDS 匯出的所有數字都量過了（399 顆、0 fail，見第十一輪），一個參數都不用調。

### 這一輪做了什麼

**`pattern_ref`（Reference from pattern）收進 `HIDDEN_STEPS`。** 使用者：「請拿掉
吧」。它**沒事做了**，不是它壞了 —— 它被期待的「單張影像找 ROI 的第三種方法」，
那件事上一輪量出來 **Template 已經在做**；剩下的唯一能力是「疊一張 ref 去相減」，
而現在的 RSEM 路線是「Region 段圈區域 → Compare regions」，用不到 ref。

**是收起來不是刪掉**，理由是硬的：這張卡刪過一次、代價量過（rsem route
24/24 → 12/24）之後又被要回來；而且 `tests/fixtures/recipes/dual_route_basic.json`
的 rsem route 正用著它、撐著一組黃金值。`HIDDEN_STEPS` 只過濾**卡片庫** ——
那份 recipe 照跑、CLI 照跑、黃金值一個字不動，而
`test_pattern_ref_is_hidden_but_still_runs` 逐項驗那四件事。

要它回來：把 `adept/ui/scope.py` 的 `HIDDEN_STEPS` 裡那個字串拿掉。

順手整理了 `CLAUDE.md` §5（那張「收起來／刪掉／改名」的表補上這一張走完五步的
結局）、`docs/ROADMAP.md`（Region-4／Region-5 與收斂）、計畫書 §3.4 的現況表。

核心 1421 passed、UI 40 檔逐檔全綠、三組黃金值逐項相同。

---

## Phase 2：單張大圖那條路做在 Template 裡（2026-08-18，第十四輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

Region 段四種找 ROI 的方法現在**都到位了**，而且輸出契約一致（上一輪的
`REGION_FACTS`）。剩下的懸而未決只有一件：**`pattern_ref`（Reference from
pattern）要不要留**。它現在唯一的用途是「單張影像合成一張 ref 去相減」，而
使用者要的「用重複結構鋪 ROI」已經是 Template 在做了。要收起來只是
`scope.HIDDEN_STEPS` 加一個字串 —— 等使用者說。

### 這一輪做了什麼

使用者原本要開一張新卡：「他是用在 repeating pattern 的 SEM（單張影像圖），
他鋪 ROI 的方式就是跟 template 很像，只不過他是反向把單 cell 鋪回去」，
接著說「你要直接做在 template 裡也可以，但要想想怎麼設計」。

**量過之後答案是：不必新卡，也不必新的下拉。** 餵一張 1000×1000 的合成 SEM 給
現在的 Template 卡，得到 **625 個框、相位正確、match 1.00、61 ms** ——
`algo/template.roi_boxes_in_patch` 的 docstring 早就明講它同時涵蓋兩種大小關係
（cell 比圖大 / cell 比圖小）。兩種用法的差別**完全在「接哪一條流」**，那正是
F9 的規矩（資料從哪來由線決定），不需要再發明一個模式參數。

擋路的有三個，三個都修掉了：

1. **`max_boxes` 預設 64 會把 625 份安靜留 64 份。** 改成 **8192**（上限 65536）
   —— 跟 `roi_from_mask` 同一組數字，兩張會吐幾千個框的 ROI 卡不該有兩套上限。
   實測不封頂的成本：4 px pitch 的 1000×1000（62500 個框）83 ms，所以那個小數字
   唯一站得住的理由（怕慢）並不存在。
2. ⚠ **`<name>_clipped` 在 Template 上是個恆為 0 的旗標** —— 寫這一輪的測試時抓到
   的。`roi_boxes_in_patch` 自己就會截到你給的長度，所以照 `max_boxes` 去要，
   回來的永遠正好是 `max_boxes` 個，那個 `len(boxes) > max_boxes` 永遠 False。
   **那正是這個旗標存在要擋的那件事本身**（100 份被留成 25 份而卡片說沒被砍）。
   改成多要一個。
3. **對話框只吃磁碟上的檔案。** 單張 SEM 那條路要疊 cell 的圖，就是使用者正在看
   的那一顆 —— 多一顆 `Use the image on screen`。它**只是準備好、不會自己疊**：
   重疊會重算相位，而相位一變使用者標好的框就全部平移了。
   配套把 `_preview_patch_size` / 新的 `_template_source_image` 改成問**卡片自己的
   `source`**，不是寫死 `ref`/`test`（單張那條路的流名是使用者填的）。

`tests/test_roi_template_full_image.py`（7 條）鎖住「不必新卡」這個判斷 ——
它一旦不成立，那裡會紅，而那正是該回來重開一張卡的時候。

核心 1421 passed、UI 40 檔逐檔全綠、三組黃金值逐項相同。

---

## Phase 2：三張 ROI 卡的輸出統一（2026-08-18，第十三輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

**使用者已經在真實資料上跑通 GDS 那條路。** 這一輪把他提的
「各種找／給定 ROI 的方法，輸出的東西要接近」做掉了。

**下一件事是他同時提的：把 `pattern_ref` 改造成一張 ROI 卡**（他的話：
「他是用在 repeating pattern 的 SEM（單張影像圖），他鋪 ROI 的方式就是跟
template 很像，只不過他是反向把單 cell 鋪回去，不過這樣的話他應該就是要放在
ROI 內的，你覺得他要叫什麼名字?」）。名字我建議 **`Repeats`**（key `roi_repeats`），
理由與待量的數字寫在對話裡 —— **還沒動手**，等使用者確認名字。

### 這一輪做了什麼：`_util.REGION_FACTS`

在這之前三張卡各寫各的：**Profile 一個區域數字都沒有**、Template 三個
（`present` / `others_present` / `edge_dropped`）、GDS 四個（`present` / `pieces` /
`area_px` / `clipped`）。於是下游（分數表達式、`Compare regions`、報表）**得先
知道這個區域是誰找的**，才問得出「它有沒有落在這一顆上」。

現在每一張「找 ROI」的卡，對它宣告的**每一個**區域，都寫同一組五個：

| | 答的問題 |
|---|---|
| `<n>_present` | 這一顆上有沒有一個**真的定位到的**它 |
| `<n>_boxes` | 幾個框 |
| `<n>_area_px` | 蓋了多少像素 |
| `<n>_clipped` | 有沒有被框數上限**安靜地**砍掉 |
| `<n>_edge_dropped` | 因為靠邊被丟掉幾塊 |

三個設計決定，每一個都有理由：

1. **前三個從 `ctx` 讀回來，不是卡片自己記一份。** 卡片記的「我放了幾個框」很
   容易跟實際存進去的不一致，而那種 bug 極難發現。
2. **`clipped` / `edge_dropped` 整個家族共用同一個值**（`<n>` / `<n>_center` /
   `<n>_others`）。重複是刻意的：下游手上只有**一個**名字（使用者在
   `Compare regions` 上挑的那一個），它必須不必知道那是不是衍生名。
3. ⚠ **`present` 與 `boxes` 會不一致，而那是它們合起來要講的話。** Profile 與
   Template 定不出位置時會退回「整張圖」當保險 —— 框在、但它不是那個區域。
   於是 `present = 0` 而 `boxes = 1`。寫這一輪時才發現**兩張卡在這件事上原本
   不一致**（Template 有這個語意、Profile 沒有），現在兩張一樣。

沒有統一的是**卡片自己的診斷**（`match_score` / `cross_pitch_x_px` / `layout_ok`）
—— 那些答的是「這一次定位可不可信」，而不同方法的可信度指標本來就不一樣，
硬統一會變成假的。GDS 另外多一個 `<n>_pieces`（連通元件 vs 矩形，只有走 label
map 那條路的卡分得出來）。

`tests/test_region_facts.py`（14 條）鎖住整組，包含一條**掃 registry** 的：任何
吐區域的卡沒宣告那五個就紅 —— 判準是「它吐不吐區域」，不是一張寫死的卡片清單
（寫死的清單在下一張卡加進來時不會叫）。那一條自己也有防空跑的斷言。

黃金值三組逐項相同（fixture 的兩份 recipe 都沒有 ROI 卡）。
核心 1413 passed、UI 40 檔逐檔全綠。

---

## Phase 2：GDS 卡的空白狀態防呆（2026-08-18，第十二輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

使用者拿真實資料跑通了 GDS 那條路（「我吃的到 label 的資料」）。這一輪修的是他
接完線之後看到的第一件事，**而下一輪要討論的是他同時提出的那個大問題**：

> 「我認為各種找／給定 ROI 的方法，理想上輸出的東西要接近⋯⋯現在不是不能用，
>   而是現在有點像大家資料結構不一樣。」

還有一句：`Reference from pattern`「蠻雞肋的」—— 他原本期待它是 RSEM 找 ROI 的
第三種方法，但它吐的是影像不是區域。**這兩件都還沒動手**，我的分析寫在對話裡，
要點：三張 ROI 卡的**區域**契約其實一致（吃一張圖 → 吐具名區域），真正不一致的
是**每個區域的 feature**（Profile 一個都沒有、Template 三個、GDS 四個），
以及 `pattern_ref` 根本不在這張圖上（它是 `影像 → 影像`）。

### 這一輪做了什麼

**這張卡永遠不該是空的。** 使用者：「一開始 layout labels 連過去 GDS layer card
時候，image stream 完全不會顯示任何 overlay，要輸入 region name 才有⋯⋯避免 user
以為沒連到沒 work」。

規則本身沒問題（**某一列空著 = 那一層不要**，使用者要有辦法排除一層）。貴的是
**整張卡都空著**那個狀態：一個區域都不吐、影像上一個框都沒有 —— 而那跟「線沒
接上」「這張卡壞了」在畫面上長得一模一樣。

填名字的優先順序：

1. **掛上來那份匯出的 `label_map`** —— 真層名（`L17/D0` → `L17_D0`）。
2. **這一顆 label 圖上真的出現的 id** → `LayerA` / `LayerB`…（`fallback_layer_names`）。
   走到這裡的情況是 GLAS 匯出時沒勾 label map。名字很爛，但它讓**接線這件事當場
   看得到結果**，而名字使用者本來就會改。

⚠ **字母跟著 id 走，不是跟著順序**：這一顆剛好沒有第 2 層時字母不該整排遞補 ——
`3:LayerB` 讀起來像在講第二層，而換一顆有第 2 層的 defect 又會變成 `3:LayerC`。
（測試裡就長出這一顆：seed 11 的第一顆只有 id 1 和 3。）

觸發點有兩個，因為使用者的順序不只一種：**加卡的時候**（匯出已經掛好）與
**接線的時候**（那正是他期待畫面有反應的那一刻）。兩個都只填空的。

順手：`parse_channel_map` 多一個 `noun` 參數。同一支解析器服務兩張卡，而 GDS 那
張卡上打錯一列時，使用者看到的是「**image** 2 has no name」—— 那張卡上一張圖都
沒有。UI 那一頭早就分開講了（`ChannelMapField._WORDS`），只有錯誤訊息還沒有。

核心 1401 passed、UI 40 檔逐檔全綠、三組黃金值逐項相同。

---

## Phase 2：真實 GDS 匯出量完了（2026-08-18，第十一輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

**Region-3 的最後一個未知數收掉了。** 使用者在公司機跑了
`python tools\check_glas_export.py <匯出資料夾> --samples 2`，399 顆、
**0 fail / 2 warn / 21 checks**。等了兩輪的那個數字（每一層的
`pieces / rectangles`）是：

| 層 | pieces | rectangles |
|---|---|---|
| 1 | 30 | 30 |
| 2 | 100 | 100 |
| 3 | 275 | 275 |

**三層都相等，而且遠小於預期。** 意思是每一塊形狀本來就是一個軸對齊矩形 ——
沒有 L 形、沒有斜邊，**也沒有任何一層被後面畫的層切碎**（那正是原本擔心的事，
因為 GLAS 的 `render_label_image` 是 `lbl[m > 0] = label_id`，後畫的會蓋掉先畫的）。
合成的測試資料是 1014 / 988 / 25，所以那條「被切碎」的路還是測得到 ——
**分解那段程式不要拿掉**，下一個站點不保證一樣乾淨。

`roi_from_mask` 因此**一個參數都不用調**：最大 275 個矩形對上 `max_boxes` 預設
8192，30 倍餘裕。實測同形狀資料 **54 ms／顆**，下游 275 個框量一次 glv **5 ms**，
399 顆單執行緒約 25 秒。

**Region-3 可以收了。** 下一段照 `docs/ROADMAP.md` 走。

### 這一輪改了什麼（都在健檢腳本上）

真實報告上那兩條 WARN 有一條**已經沒有意義了**，而那正是要修的：

1. **框數的門檻比錯了對象。** 它拿 Profile／Template 的 64 去比，於是印出
   「the biggest layer is 275 … so roi_from_mask needs its own much larger cap」
   —— 而那件事上一輪就做完了（`roi_from_mask` 的預設就是 8192）。
   **一條講著已完成工作的 WARN，讀起來跟一個待辦一模一樣。** 改成比
   `GDS_BOX_CAP = 8192`，並印出餘裕倍數；有一條測試核對那個常數跟卡片的預設值
   是同一個，免得它們各走各的。
2. **`pieces` vs `rectangles` 的意思現在寫在報告裡**，不留給讀報告的人自己推：
   相等就說「every shape is already a plain rectangle」，不等就點名是哪幾層。
3. **新增一條「改寫之後還分不分得開」。** 原本只檢查「layer 名需不需要改寫」
   （真實資料三個都要），但真正會咬人的是**碰撞**：`17/D0` 與 `L17-D0` 都會變成
   `L17_D0`，ADEPT 會把後面那個改成 `L17_D0_2`，於是畫面上出現一個誰也認不得的
   名字。真實那一份 PASS。腳本裡的改寫規則是
   `glas_export.region_name_for` 的複本（它要能在只有一個檔案的機器上跑），
   所以另外有一條測試逐字比對兩份對同一批邊界名字的輸出。

其他從報告讀到、不需要動程式的事實：`page` 欄位 399 顆全空（RSEM 沒有頁碼，
ingest 本來就不讀它）、`nm_per_px` 全批都是 1、`id_source = klarf-defectid`、
image_id 不補零且不需要 `_safe_name` 改寫、`fine_dx/dy` 在 ±200 nm 之內
（那是 GLAS **已經套用**的位移，label PNG 是對位後產生的，ADEPT 不用管）。

---

## Phase 2：Golden Cell 改名回來 ＋ 兩段分類定調（2026-08-18，第十輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

**還缺的那個數字沒有變**：真實 label 上每一層的 `pieces / rectangles`，
量法 `python tools\check_glas_export.py <匯出資料夾> --samples 2`（要回公司才量得到）。

### 這一輪做了什麼

**1. `golden_cell` 改名回來成 `pattern_ref`。**
上一輪刪掉它之後我把代價量出來給使用者看（rsem route 24/24 → 12/24），
使用者的回覆是「那可能要拿回來 不過要改名字 不然會誤會」。

新名字：**Reference from pattern**（`steps/pattern_ref.py`）。裡面沒有 golden、
也沒有 cell。第一版是「Reference from **repeating** pattern」，使用者當場說
「名字太長」—— 收成三個字，句型跟隔壁的 `Mask from regions` 一樣（「產出 from
來源」）。「repeating」掉進 help 裡：它是**前提**不是名字，而且圖不重複時這張卡
會直接擋下來並講原因，使用者不必靠名字知道。
`test_the_name_does_not_say_golden_or_cell_anywhere_the_user_looks`
逐一掃卡片名、說明、參數名、參數說明與 feature 名。

改名要換的**不只是 key**：`golden_ghost` / `golden_px` / `golden_py` →
`ref_sharpness` / `ref_px` / `ref_py`，而那三個會被打進**分數表達式**。只換卡片
不換 feature，舊 recipe 打開來是一條 `unknown-feature` 加一個算不出來的分數 ——
也就是那份 recipe 存在的理由。所以 `_migrate_renamed_cards` 與
`_migrate_renamed_features` 是一對；後者用**整個識別字**的邊界比對
（`str.replace` 會把 `my_golden_px_ratio` 打斷，測試裡有這一條）。

**改名沒有動到任何數字**：黃金值 6 顆，除了那三個 feature 換名之外每一個值都跟
刪掉之前逐項相同（程式對過）。`cell_period` 維持刪除，所以週期來源只剩「參數
填死」與「這張卡自己估」——少一條「兩張卡要照順序放」的規矩。

**2. Compare 段裝什麼，定調了**（計畫書 §3.4.1）。使用者問「Compare 這個 你覺得
要放什麼卡片比較合理？」。`step.py` 的機械規則寫「影像＋影像 → 影像」，但那條對
`pattern_ref` 不成立（一張進一張出），而它顯然屬於這裡 —— 所以這一段的定義不是
型別，是一件事：**把「這一顆該跟什麼比」變成一張差異圖**，拆成三步：

| # | | 現在有 |
|---|---|---|
| 1 | 第二張圖從哪來 | `pattern_ref` |
| 2 | 讓兩張真的可比 | `align`（收起來了）|
| 3 | 變成一張差異圖 | `subtract` |

第 1 步是最容易被忽略的一半，而它是**單張影像那條路唯一的入口**。
`roi_compare`（Compare regions）**不屬於這一段**：它吐數字不吐圖，所以在 Measure。
那個對照剛好把界線講清楚 —— **Compare 比兩張圖（出圖），Measure 比兩塊區域（出數字）**。

**3. `roi_mask` 留在 Region**（計畫書 §3.3.18）。使用者問「ROI 內的 region → mask
放在 ROI 內合理嗎？」。它是 Region 段裡唯一吐影像的卡，唯一消費者在 Enhance ——
照「跟著消費者走」那條補充規則看起來該搬。**不搬**，硬理由是第二個：卡片庫是照
Input → Enhance → Region 排的，搬去 Enhance 它就會出現在**任何 Region 卡之前**，
而它沒有 Region 卡完全不能用 —— 使用者第一次讀到它時，它講的東西還不存在。

### 驗收

核心 1373 passed、UI 40 檔逐檔全綠、三組黃金值 `--check` 逐項相同。

---

## Phase 2：入口只寫一份 ＋ 刪掉 Golden Cell（2026-08-18，第九輪）

### 那一輪結束時的位置（交接已由上面那一段接手）

Region-3（GDS）四步做完之後，使用者對著 Studio 的截圖提了四件事，這一輪四件全做完。
**還缺的那個數字沒有變**：真實 label 上每一層的 `pieces / rectangles`，
量法 `python tools\check_glas_export.py <匯出資料夾> --samples 2`（要回公司才量得到）。

### 這一輪做了什麼

**1. `Open GDS export…` 那顆鈕根本沒在工具列上。**
使用者：「Load layout labels 要怎麼 load，好像沒有 load 的地方，UI 左上角也有奇怪
的文字 …Export」。上一輪我把那顆鈕建出來了、文字對、tooltip 對、`_update_action_states`
也會開關它 —— 但漏了 `bar.addWidget(...)`。**Qt 不會為這件事報錯**：它變成主視窗一個
沒有版面的子 widget，被畫在 (0, 0)，也就是工具列左上角，疊在第一顆鈕上。
所有既有測試都綠 —— 沒有一條在問「這顆鈕在工具列上嗎」。

修的是那一整類，不只那一顆：`test_every_button_built_for_the_toolbar_is_actually_on_it`
逐顆掃視窗上的 `btn_*`，要嘛在工具列的 action 清單上、要嘛在工具列上某個容器裡。
（拿掉修正之後它會紅，驗過。）

**2. 入口只寫一份**（Input-5，計畫書 §3.1.15）。
使用者：「Input 部分 各種 image source 資料流 是否改成個別入口比較好（但同時 UI
一開始進去的地方顯示也要改）」。在這一輪之前，同一組入口被抄在四個地方，而四份已經
漂了：工具列有三顆 Open，**空白狀態（畫面上最大的那一塊）只講 KLARF** ——
帶著一個資料夾的圖片進來的人在那裡找不到自己那條路。

`adept/ui/scope.py` 多一張 `INPUT_SOURCES` / `ATTACHMENTS`，工具列與空白狀態都從它
長出來。空白狀態變成**一種 source 一列**（鈕 + 一句「這條路吃什麼樣的檔案」），
底下一行講附加檔要等 lot 載進來 —— 那正是第 1 點「要怎麼 load」的答案。
`load_sidecar` 的 help 與它擋下來的那句話也都點名 `Open GDS export…`，而
`test_the_card_message_points_at_a_button_that_exists` 現在問的是**真的建出來的
那條工具列**（第一版是 grep `studio.py` 的原始碼 —— 那正好對「字在、鈕不在」是綠的）。

KLARF 那一條**刻意仍然服務 `ebi_patch` 與 `rsem` 兩種**：拆成兩顆鈕等於要使用者
回答一個 KLARF 已經回答了的問題，而答錯就是一個錯誤訊息。

**3. `golden_cell` 與 4. `cell_period` 刪掉，`SNR map` → `Z-map`。**
使用者：「Compare 內的 Golden Cell reference 功能幫我完整移除（他就是 template）」、
「Measure 中的 Cell period 幫我移除（不需要這功能），SNR map 幫我改名成 Z-map
（不然兩個 SNR 會被人搞混）」。

`adept/core/steps/golden.py` 整支刪掉。**這一次是刪不是 `HIDDEN_STEPS`** ——
`align` 那一輪使用者說的是「之後真需要我再回來」，這一輪說的是「完整移除」，
而那兩句話對應兩種不同的處置（差別現在有一條測試在鎖）。
`snr_map` 只換 `label`：`key`、影像流名、feature（`snr_max`）全都是 **recipe 的鍵**。

⚠ **代價量過了，而它比使用者想的大**（計畫書 §3.4.1）。Template 吐的是**具名區域**、
`golden_cell` 吐的是**一條合成的 ref 影像流** —— 前者答「這塊材料在哪」，後者答
「這張圖應該長什麼樣」。刪掉之後**單張週期性影像沒有任何辦法產生 ref**，
於是也沒有 diff。實測（`dual_route_basic` 的 rsem route、`make_sample_rsem`
seed 11、24 顆）：

| 那條 route 怎麼量 | 分類正確 |
|---|---|
| 舊：疊 ref → subtract → 量 diff | **24 / 24** |
| 新：量 Z-map | 12 / 24（＝猜銅板）|
| 也試過：`roi_cross` + `roi_compare` | 每個特徵 real 與 nuisance 完全重疊 |

所以那份 fixture 的 rsem 段拿掉了準確率斷言、改凍一組新的黃金值
（`dual_route_basic__make_sample_rsem.json`，53 處變動全部來自這件事），
現在守的是「同一份 recipe 吃得下第二種輸入、而且數字不會偷偷變」。
`test_the_single_image_route_has_no_reference_and_says_so` 把它釘住：
哪一天有人把「單張影像的 ref」補回來，那一條會紅。

**要回來的話**：`git revert` 那一個 commit 就整組回來（卡片、fixture、黃金值）。
演算法從來沒被刪 —— `algo/golden.py` 還被 Template 卡用著，`algo/period.py`
現在在 `adept/core` 裡**一個呼叫者都沒有**（那正是它最容易被順手清掉的時候，
所以 CLAUDE.md §5 的 ⚠ 改寫過，便利貼測試也還在）。

### 驗收

核心 1345 passed（3 個 `test_offline_tools` 的 manifest 過期，`release.py` 跑完就綠）、
UI 40 個檔案一個一個跑全綠、三組黃金值 `--check` 逐項相同（rsem 那組是這一輪重凍的）。

---

## Phase 2：Region —— Template ＋ Profile（2026-08-18）

### 那一輪結束時的位置（交接已由上面那一段接手）

**現在的位置**：Phase 2 的 **Input ✅**、**Enhance ✅**、
**Region-1（Template）✅**、**Region-2（Profile：2a 圖示、2b 點曲線選材質、
2c 單方向）✅**，加上跨兩張卡的「靠邊的框不要」與疊框分色（第八輪）。
下一段是 **Region-3（`roi_from_mask` / GDS）**，**只做 RSEM**（單張 + KLARF；
使用者定調，理由見計畫書 §3.3.13）。健檢跑過真實資料了（第十輪：399 顆、v4 manifest、
0 fail），**欄位已經校準，可以直接開工**。下一步是在 `tools/` 幫
`make_sample_rsem.py` 加一支 label sidecar 產生器（**圖案要刻意非週期**、
照 v4 的欄位寫 manifest）。

⚠ 開工前先讀 `GLAS-INTERFACE.md` §3.4／§3.6：`max_boxes` 的 64 在這條路上會
**安靜地砍掉 95%**（合成同尺寸同覆蓋率測出一層 1014 個矩形），而 layer 名
（`L17/D0` 那種）一定要有一層固定的改寫規則。

**還缺一個數字**（要等使用者回公司才量得到）：真實 label 上每一層的
`pieces / rectangles`。合成的那組是「拆出來的矩形數 = 上千」，但**真實資料上
pieces 跟 rectangles 差多少還不知道** —— 差很大就證實「層被後面畫的層切碎」
在這批資料上真的會發生，而那會影響 `roi_from_mask` 怎麼設計。
量法：`python tools\check_glas_export.py <匯出資料夾> --samples 2`
（v4 之後不必再給 `--klarf` / `--images`）。

**第 1、2 步做完了**（`tools/make_glas_export.py`、`ingest/glas_export.py` ＋
`steps/load_sidecar.py`）。**第 3 步也做完了**（第十三輪）。**Region-3 四步全部做完了**（第十一～十四輪）。

**那張「比較兩個區域」的卡也做完了**（第十五輪，`roi_compare`）。
**Region 三條路 + 那張比較卡 = 這一輪的東西全部收斂了。**

下一段照 `docs/ROADMAP.md` 是 **Measure 段其餘的**，或 **ADC 段**（那一段要先
設計資料結構，不是加一張卡 —— 計畫書 §3.6）。開工前問使用者要哪一個。

還缺一個數字（不擋任何事）：真實 label 上每層的 `pieces / rectangles`，
`python tools\check_glas_export.py <匯出資料夾> --samples 2`。

**開工前讀**：[`AGENTS.md`](AGENTS.md) → [`docs/plans/F11-phase2-features.md`](docs/plans/F11-phase2-features.md)
**§3.3.4**（Template）、**§3.3.11**（Profile 單方向）、
**§3.3.12**（靠邊的框、疊框分色）→ [`CLAUDE.md`](CLAUDE.md) 的鐵則十條。

**Region-1／2 的尾巴都結掉了**，兩件都不是靠「做完」結的：

- **模板過期健檢**（原本 `roi_template` 檔頭承諾了、程式裡沒有的那個）**做完了**
  —— `algo.template.judge_template` ＋ `ui.inspectors.TemplateInspector.health`。
- **「三個框尺寸該在影像上拖」被使用者否決**：「Region2 拖框邊應該沒意義吧～
  你拖這張 其他張怎麼辦」。**通則**：可以用拖的只有「所有 defect 共用的那一個
  物件」上的東西（Template 的 GC、Region-3 的 label map）；Profile 的框是**逐顆
  的結果**，拖它等於改輸出。理由寫在計畫書 §3.3.9。

**還欠的一件（不屬於 Region 段）**：那張「比較兩個區域」的卡（計畫書 §3.3.6 的
最後一段）。它屬於 **Measure** 段，不要插隊。今天比較是發生在分數表達式裡的。

---

### 第十五輪：`roi_compare` —— 把「拿哪兩塊比」變成一張卡（同日）

Region 段出名詞，這張卡出動詞（使用者 2026-08-18 定調的那件事，計畫書 §3.5.1）。

**它不解鎖任何功能** —— 今天沒有它也比得出來，只是比較發生在**分數表達式**裡
（`test_epi_glv_mean - ref_epi_glv_mean`）。而表達式裡的減法：畫布上看不到、
recipe 的 diff 讀不懂、兩邊挑錯區域也沒有人擋得住。價值是那三件變成可見的。

**兩對（流 + 區域），不是一條流兩個區域** —— 使用者列的三種情況裡，中間那一種
兩邊的流不一樣（`epi` @ test vs `epi` @ ref）。一條流配兩個區域表達不出它。

**它撞到兩條既有的不變量，而兩條都是我改對了測試而不是繞過去：**

1. `test_every_measure_card_can_take_more_than_one_source`（量測卡都要是
   `MultiSourceStep`）。這張卡不該是：「多連一」講的是同一件事做在好幾條流上，
   而這張卡的兩條流有**自己的角色**，角色排不成一串（清單答不出「哪一條是
   target」）。加了 `ROLE_PORTS`，而且**驗的東西反過來**：那一類要有兩個以上的
   單一來源埠、不准混用清單型別。**列名字而不是放寬條件**。
2. 「還沒設定完的訊息要指向一顆 `…` 結尾的鈕」。這張卡缺的不是要匯入的檔案，
   是**兩格要挑的值**，而那兩格就在旁邊。所以那條改成認**兩種**形狀，而且
   引號那一種**要驗**（引號裡的字必須真的是這張卡的欄位名）。
   第一版我把舊規則**換掉**而不是加上去，結果 `roi_mask` 那句本來講得很好的
   訊息突然變成違規 —— **用「或」不是「改成」**。

算術只有一個原則：`snr` 用這個 repo 已經有的那個帶正負號的慣例
（`group_snr` / `algo/snr`），**不發明第三種**。分母是 0 時是 **nan 不是 0**
（0 的意思是「沒有差異」，而事實是「這個問題答不出來」）。

實測 8 顆的 lot：兩種失敗各講各的話 ——「這一顆的 label 裡沒有第 2 層」vs
「這一顆根本沒有 label」。20 條新測試。

---

### 第十四輪：Region-3 第 4 步 —— Studio 那一頭（同日）

兩件：`layers` 的表格編輯器、`roi_from_mask` 的儀表。**Region-3 四步做完了。**

**表格是一個旗標，不是第二個 widget。** `ChannelMapField` 原本照「一列一張圖、
左欄是頁碼」設計，但 label id 跟頁碼的**資料形狀完全一樣**（整數 → 名字，空的
就是不要），差的只有三句話 → `ParamSpec.row_kind`。三句話裡最重要的是
**placeholder**：`load_patch` 空著是「用預設名」，這裡空著是**「這一層不要」**。
列數也分開（`set_image_count` / `set_label_count` 互不覆蓋 —— 一張 recipe 上可能
兩個 `channel_map` 都在）。

**儀表刻意不是「label 的上色預覽」。** 第一版想畫那個（label map 幾乎全黑），
但**形狀已經看得到了** —— 每一層都是具名區域，而預覽上的疊框第八輪就一個區域
一個顏色、還帶圖例，而且畫在**真的那張 SEM 影像**上。所以儀表回答那張圖答不出
來的：哪一層沒落在這一顆上、各幾塊幾個框、有沒有砍到上限，以及**在圖裡卻沒有
名字的 id**（匯出多了一層而 recipe 沒跟上 —— 它會安靜地少一個區域）。

**一個自己踩的**：這幾條 UI 測試第一版接在 `test_glas_sidecar.py` 後面，
結果核心那一輪（不含 UI）**整個行程崩掉** —— 那一份不叫 `test_ui_*`，於是 Qt
被拉進「一個行程跑全部」的核心測試裡。`CLAUDE.md` §4 講的就是這件事，只是我從
另一個方向撞上它。**測試檔名在這個 repo 裡不是命名習慣，是跑法的宣告。**

8 條新測試。計畫書 §3.3.17。

---

### 第十三輪：Region-3 第 3 步 —— `roi_from_mask`（同日）

`algo/mask.py` ＋ `steps/roi_from_mask.py`。端到端跑過：`load_single` →
`load_sidecar` → `roi_from_mask` → `glv_stats`，`workers=2`，分數表達式吃
`L17_D0_glv_mean` —— **下游一行都沒改**（出口契約付現了）。

**唯一不能錯的東西：框聯集起來要逐像素等於那一層。** L 形的 bounding box 會框到
別的材質而照樣吐出很正常的數字，所以是精確拆解（Manhattan layout 上那是等價不是
近似）。測試測的是**正規化來回之後**還相同 —— 0–1 座標是為了換尺寸不錯位，
但它同時是一個會偷偷四捨五入掉一個像素的地方。實測：差 0。

**`max_boxes` 的數字是量出來的**，不是猜的。使用者定了方向（「理想上應該會很多，
因為處理的是 RSEM images 等級」），我去量了 1000×1000 上四種真實形狀：
39 / 975 / **5 295**（45° 斜邊，`fillPoly` 沒有 LINE_AA 所以每一列一個矩形）/
5 184（contact 陣列）。下游成本 N=1 000 約 3 ms、10 000 約 60 ms、50 000 約
280 ms，**而且是每張量測卡每顆各一次**。→ 預設 8192、上限 65536。
既有 Region 卡的 64 在這條路上會安靜地砍掉 95%。

順手做的兩件防呆：`MAX_RUNS` 硬線（棋盤格會產生幾十萬個 run，而「跑很久」跟
「當掉」對使用者是同一件事）、以及 layer 名的改寫（`L17/D0` 不能當變數，
而區域名會變成特徵前綴 —— 給一個每次都一樣的預設，名字仍然是使用者的）。

`layers` 參數**重用 `channel_map` 型別**（兩者都是「整數 → 名字」，驗證規則
一模一樣），不發明第二個解析器。但那個**編輯器**是照「一列一張圖、左欄是頁碼」
設計的 —— label id 不是頁碼，widget 要一個變體，那是第 4 步的第一件事。

**Studio 的「Open GDS export…」提前做了**（本來排第 4 步）：因為這張卡的
「還沒設定完」那句話要指向一個**按得下去**的東西，而 `test_ui_f7_9_feedback` 有
一條不變量在擋 —— 指向不存在的東西，那句話本身就是死路。那顆鈕還會把 layer 名
**填進**卡片（對照表就在 manifest 裡，讓使用者自己抄一次是在製造一個可以抄錯的
機會）。

28 + 1 條新測試。計畫書 §3.3.16。

---

### 第十二輪：Region-3 第 2 步 —— sidecar 進 ingest（同日）

`ingest/glas_export.py`（配對）＋ `DefectItem.sidecars`（住哪裡）＋
`steps/load_sidecar.py`（載成一條流），CLI 多一個 `--gds`。

**附加檔不能放進 `DefectItem.images`。** `load_single` 的契約是「一顆一張」，
而且它在一顆有兩張時**拒絕載入**（那個拒絕是對的）。label 混進去的話，每一顆
RSEM defect 都會突然變成兩張而載不進來 —— 而錯誤訊息會**說謊**（「這顆有 2 張
影像」；不，它有 1 張影像跟 1 個附加檔）。

**兩個實測抓到的、會安靜出錯的地方：**

1. **換一份匯出，快取不會失效。** 有 KLARF 的時候 `_dataset_token_for` 只看
   KLARF 的 stat，而換 mask 目錄不會動到 KLARF —— 同一個 lot 換一份匯出，
   token 一模一樣，影像段快取把**上一份算出來的框**餵回來。修法是把 sidecar 的
   路徑 + mtime + size 折進 token，而**沒有 sidecar 時回空字串**，所以既有的
   token 逐字元不變（黃金值與既有快取不受影響）。
2. **`load_raw` 會安靜地把三通道合成灰階。** 對 SEM 影像是對的，對 label map
   是致命的（像素值**是**層號）。而 GLAS 匯出時 `<id>_label.png` 旁邊就放著
   三通道的 `<id>_label_view.png`。實測同一個檔：`load_raw` 給
   `[0, 131, 159, 182]`（id 被混掉、沒有錯誤），`load_exact` 給 `ndim 3`。

   **這一條最值得記**：我原本在卡片裡寫了「`ndim != 2` 就報錯」，而那段是**死的**
   —— 通道早在讀檔那一層就被合掉了。**寫了一個檢查不等於那個檢查會執行。**
   新增 `imageio.load_exact()`（原樣讀），附加檔走它。

掛不上的那幾顆不是錯誤（GLAS 的分數門檻本來就會擋掉一些）：那一顆會失敗、講出
**兩種可能的原因**，整批照跑。實測 8 顆的 lot：7 成功 1 失敗。

20 條新測試。Studio 的「掛上匯出」入口還沒有（CLI 有），跟第 4 步的儀表一起做。
計畫書 §3.3.15。

---

### 第十一輪：Region-3 第 1 步 —— 合成 GLAS 匯出（同日）

`tools/make_glas_export.py`：**掛在既有的 RSEM lot 上**產一份 GLAS 匯出的替身
（`<id>_label.png` + `_gray.png` + `_label_view.png` + v4 manifest + alignment）。

分開一支而不是改 `make_sample_rsem.py`：那一支撐著一組黃金值，而且 **GLAS 本來
就是獨立的程式在消費同一個 lot** —— 合成品跟真實 producer 同形狀，配對那條路
（id 從 KLARF 來、`_safe_name`、檔名慣例）才會被真的走過。

刻意做進去五個難處：非週期的 layout、每層第一塊是 **L 形**、後面的層蓋掉前面的、
`--miss` 缺檔、`--wrong-size` 尺寸不符。layer 名也刻意長成 `L17/D0` 那個形狀 ——
用乾淨的名字產測試資料等於把「怎麼改寫成區域名」那一題藏起來。

**兩個自己踩到的**（都是「假資料太漂亮就驗不到東西」的同一個病）：

1. `--eaten` 第一版是「最後一層蓋滿整張圖」→ 那顆 100% 都是同一個 id，其他層
   **跟背景**一起沒了。它同時不再是一張像樣的 label 圖，也量不出「一層拆成幾個
   矩形」。要吃掉的是**一層**（畫在受害層的形狀上 + 3px），不是整張圖。
2. 壞樣本一開始排在**前面**，而開發跟健檢都是抽前幾顆看（`--samples 2`）——
   每次看到的都是特例。現在固定排在最後：`… 好的 …, eaten, miss, wrong_size`。

17 條新測試，其中最有價值的一條是整合測試：**健檢對這份合成品的判定必須正好是
那幾條刻意壞掉的**，其餘一條都不准紅。兩支工具一起鎖，格式才不會各走各的。

---

### 第十輪：真實匯出跑過健檢，推翻了三件事（同日）

使用者在公司機上跑了一次（399 顆），報告貼回來。**三件事跟我讀 GitHub 上的
GLAS 讀到的不一樣**，而它們全都往好的方向：

1. **廠內那份 GLAS 是 `mmh-gds-overlay-v4`，不是 v3。** `GLAS-INTERFACE.md` §4
   的「建議 3」**已經做完了** —— manifest 逐列帶 `id_source` / `width_px` /
   `height_px` / `nm_per_px`，連「必要 1」的 `page` 欄位都在（RSEM 這批是空的，
   那是對的）。ADEPT 不必再猜 join key、也不必自己去比尺寸。
2. **資料很乾淨。** 399 顆全 `ok`、五種 PNG 都在、label 是 1000×1000 單通道
   8-bit、3 層、`image_id` 是不補零的數字、檔名不需要 `_safe_name` 改寫、沒有
   碰撞、每一層在每張圖上都有像素。我列的四個「安靜的坑」一個都沒踩到。
3. **唯一的 WARN 是 layer 名**（`L17/D0` 那種形式，ADEPT 的區域名規則不收）。
   所以 `roi_from_mask` 一定要有一層改寫，而且規則要固定、要能查碰撞。

健檢跟著升級：讀得懂 v4 的欄位、`id_source` 直接回答 join、id 的長相改成看**整欄
的分佈**而不是第一列（第一列的 id 是 1 個字元、資料夾裡第一個檔案的 stem 是 6 個
字元 —— 兩句話都對，擺在一起像矛盾，我自己就被騙了一下）。

**而且加了一個量測，因為那才是 Region-3 真正缺的設計輸入**：把 label 拆一次，
印出每一層的 **pieces（連通元件）** 與 **rectangles（精確矩形分解）**。
合成一份同尺寸同覆蓋率的來量：**1014 / 988 / 25 個矩形**。

那個數字直接否決了一個預設值：既有 Region 卡的 `max_boxes` 是 **64**，
為「重複結構的幾份」設計的 —— 用在這裡會**安靜地砍掉 95%**。`roi_from_mask`
要有自己的上限。順帶看見另一件事：pieces 跟 rectangles 差很大的時候，
意思是**那一層正被後面畫的層切碎**（`lbl[m > 0] = label_id`）。

（KLARF 那一條 SKIP 是因為使用者跑的是我加「`--klarf` 吃資料夾」之前的版本，
`klarf_core.load()` 拿到資料夾在 Windows 上是 `PermissionError`。不重要了 ——
`id_source` 已經回答了那個問題。）

---

### 第九輪：GDS 開工前，先寫一支健檢（同日）

Region-3 定調成**只做 RSEM**（使用者：GLAS 當初是瞄著 RSEM 大圖對的，
patch 太小、可供對位的 layout 太少，而且 GLAS 那邊 patch 的 module 沒打通；
GDS 的使用時機通常在**非週期性重複區域**）。那一刀砍掉的東西比看起來多 ——
`GLAS-INTERFACE.md` §4 的「必要 1（多頁 TIFF 的 page 對應）」與「必要 2（對位用
第幾頁）」**都不需要了**，一顆一個檔而已。

真實資料在只能複製文字出來的那台機器上，所以第一步不是寫卡片，是寫
**`tools/check_glas_export.py`** —— 把匯出資料夾檢查一遍，印出一份**預設遮蔽、
可以直接貼出來**的報告（layer 名 → `L1`、defect id → `IMG1`、路徑不印，只留
結構與格式）。純標準函式庫，PNG 是自己讀的（`zlib` + IHDR/IDAT），所以不裝
OpenCV 也跑得動 —— 而那正好是要查的問題之一。

**讀 GLAS 的程式碼（commit `bef5492`）讀出四件契約文件裡沒有、而且錯了不會報錯
的事**（全部進了 `GLAS-INTERFACE.md` §3.5）：

1. 檔名不是 `<DEFECTID>_label.png`，是 `<_safe_name(DEFECTID)>_label.png` ——
   非 `[A-Za-z0-9-_.]` 換成底線。而且 `a/b` 與 `a:b` 會折到同一個檔名，
   後匯出的**覆蓋**前一顆，manifest 兩列的 id 仍然不同。
2. `render_label_image` 是 `lbl[m > 0] = label_id`，**後面的層蓋掉前面的層** ——
   一層可能在某些 defect 上被吃光，名字還在 `label_map` 裡。
3. `_label_view.png` 是 3 通道上色預覽，指錯就把 id 混掉；`_gray.png` 有 blur、
   背景是 `bg_glv`（80）不是 0，都不能拿來切區域。
4. `overlay_manifest.csv` 用平台預設編碼寫（Windows 上是 cp950），
   **JSON 那一份才是安全的**（`ensure_ascii=True`）。

寫測試時抓到自己的一個 bug，而它正是這支腳本存在的理由的反例：**沒有 `_raw.png`
又沒給 `--images` 時，尺寸檢查根本沒比到，卻印 PASS。** 那份報告是之後所有設計
決定的依據，一個假綠燈會讓整個 Region-3 蓋在錯的假設上。改成 SKIP，並鎖一條測試
（`test_a_check_that_could_not_run_says_skip_not_pass`）。

---

### 第八輪：靠邊的框不要、疊框分色（同日）

兩件小事，各自踩到一個**安靜出錯**的地方。

**(1) 「靠近邊界 n pixel 內的 ROI box 自動拿掉」（Profile ＋ Template 共用）。**
壓在 patch 邊上的框量到的是半截的那一塊，而它照樣吐得出一個看起來正常的灰階值，
然後混進 `<name>_others` 那個基準。`drop_edge`（勾選）＋ `edge_margin`（px），
兩張卡**同一組參數名**（`_util.drop_edge_specs` 是唯一的那一份）。

三個坑：

- **滿版的那一軸不算「靠邊」** —— 這條是**量出來的**。單方向的 Profile 每一個框
  都是滿版的，照「碰到邊界就算」寫的第一版把 6 個框砍成 1 個（只剩豁免的中心
  那一塊），而畫面上沒有任何錯誤訊息。滿版不是「放在邊上」，是「這一軸整個都要」。
- **缺陷那一塊永遠留著**，而且濾要在**挑出中心之後**：順序反過來，中心會從
  「離缺陷最近的那一塊」變成「留下來的裡面離缺陷最近的那一塊」。`_center` 不是
  母體裡的樣本，它是被量的那個東西。
- **基準被濾光時原本那句話是錯的**（「這張 patch 只有一份」）。兩者的處置相反：
  換張圖 vs 改一個數字。

`edge_margin` 的 max 設 64 不是 1000 —— 有上下界才有滑桿（F7-8），而上界擺在
沒有人會用到的地方等於把滑桿變成裝飾。預設關著，黃金值逐項相同。

**(2) 「Image Stream 顯示上顏色 overlay 重疊會同個顏色（藍色）」。** Region-1 讓
一張卡可以標好幾個區域，但疊框那條路把它們攤平成一串、全部畫 accent 藍。

顏色搬進 `theme.REGION_COLORS`，因為它有兩個使用者：模板編輯器的畫布與 patch 上
的疊框 —— 使用者在對話框裡把 ROI1 畫成綠色的，到了 patch 上它就要還是綠色的。
`region_check` 的縮圖也換成同一組（它的註解本來就寫著「三個一樣的藍框排在一起，
看不出哪個是主角」）。

順帶換掉一個舊決定：**焦點框原本畫紅色**，分色之後紅色會被讀成第三個區域。
改成同色加粗＋四個角標 —— **顏色回答「哪一個區域」，線寬與角標回答「哪一塊是
缺陷那一塊」**，兩個問題兩個維度（跟 Region-2b 的分群色帶同一條原則）。

框與名字走**同一個清單**（`_overlay_region_names`）；長度對不上時整組不分色 ——
錯位的顏色比沒有顏色糟得多，它會指錯區域而畫面上不會說。

使用者中途要過「著色填滿（可以透明點）」又收回，所以維持只畫外框。計畫書 §3.3.12。

---

### 第七輪：Profile「太 custom」—— 交會其實是特例（同日）

使用者收尾 Template 之後留了一句：

> 「template 部份我是沒什麼問題了，主要是 profile 覺得有點太 custom for 我當初
>   舉的例子了⋯⋯（實際上使用的機會偏少）」

他是對的，而**過度貼合的位置是一行**（`algo/grid.locate_crossings`）：

```python
# 兩軸都要有東西可比。**一軸失敗就整張失敗**
```

那是從需求（直的 MG × 橫的 EPI）抄下來的**形狀**，不是演算法的形狀。投影量的是
「這個方向每一根線在哪」—— 一個方向就答得出來。於是一張密集 line/space 的 patch
（只有一個方向有結構，EBI 上很常見）進到這張卡只拿得到「no flat stripes to lock
onto」＋ 每一顆 `locate_ok = 0`。**能力在，被卡片的形狀擋住了。**

**第一直覺（照 `align` 收進 `HIDDEN_STEPS`）是錯的。** `align` 收起來是因為它做
的事本身有問題；這張卡做的事沒有錯，只是多問了一個不必問的問題。收起來會連整套
投影定位（次像素邊界、排名挑材質、已知 pitch 補線、CPODE 的 `skip_clear`、一鍵校
正整批）一起收掉，而那些沒有第二個家。

做法：新參數 `directions`（`both`／`upright`／`flat`，圖示列）。單方向**不是**在
`cross_boxes` 加分支，而是給沒在用的那一軸一個退化的 `StripeSet`
（`open_axis`，`selected = [(0, length)]`）—— 幾何一行都不用改，跟滿版帶子交會出
來的正好就是滿版的框。五種放法 × 兩軸各自可能是被貼住的或當界線的，加分支等於把
那張表變成兩張，而只有走單軸時才會用到的那一半沒有人在看。

於是 39b9fea 刪掉的 `roi_profile`（「每一根線上一條滿版的帶子」）回來了，
而且是**同一段程式碼的一個特例**，不是第二張卡。

**「沒在看 ≠ 找不到」發作了三次**，全部是同一個病 —— 平的曲線在這套 UI 裡一直
代表「這裡沒東西」：閘門（信心 0 會否決一顆算得出來的 defect）、曲線面板（那條
平線讀起來是「去調敏感度」，意思完全相反）、摘要（`flat pitch 0.0 px` 是一個看
起來像量測失敗的假數字）。三個都改成只看**在用的**那幾軸。

另外「只看直的」＋「框放在兩根**橫**條紋之間」是空集合，它安靜地產出零個框 ——
`configuration_issues`（Studio）與 `placement_needs`（CLI）各一份。

`directions` 預設 `both`，舊 recipe 行為逐位元組不變（鐵則 9），三組黃金值逐項
相同。計畫書 §3.3.11。

---

### 第三輪：Target / Reference **不住在 Region 段**（同日）

使用者問「Target ROI box（紅框）跟 Reference ROI box 的差別？」—— 查下去發現
**這個 repo 裡有三個紅框，沒有一個是活的**：vendored 自 Fusi³ 的
`roi_type='target'`（`set_target()` 零呼叫）、`overlay` 的主 blob 紅框
（讀的 `ctx.meta["blobs"]` 沒有生產者）、以及唯一活的 `<name>_center`
（但它是**位置**不是角色）。

接著使用者定調：

> 「以這張 card 的功能（ROI）來說我不太想要去區分 target 跟 reference，原因是
> 會有很多種組合……我傾向這邊 ROI 只 labeled 出區域，之後再給 card 標註 T 跟 R。」

**同意，理由比「情況太多」更硬：角色是「這一次比較」的屬性，不是區域的屬性。**
同一塊 EPI 在一個比較裡是 target、在另一個裡是 reference —— 角色寫進區域的話，
每一種比較都要複製一份區域，而區域是**畫**出來的。這條線 repo 畫過兩次
（F7-17 的「兩條平行的路會腐爛」、§3.3.2 否決 C 的「每個消費端都要處理兩種
形態」），塞進去是第三次踩同一個坑。

所以 **Region 段出名詞、Measure 段出動詞**，而缺的只是第三個名詞：

- `<name>`         全部（**仍然包含**缺陷那一塊）
- `<name>_center`  缺陷所在的那一塊
- `<name>_others`  **其餘 = 同一張圖上同材質的基準** ← 這一輪補的

拿 `<name>` 當基準是有偏的：N 塊時缺陷佔 1/N 的像素，N=4、缺陷偏 50 GLV 就把
基準拉走 12.5 GLV —— 跟要量的量同一個數量級。只有一份時 `_others` **不存在**
（不是空的、也不是退回整張圖），走這一輪做好的 `regions_absent` 那條路。

規則寫在 `_util.set_region_family()`，兩張 Region 卡共用。並鎖一條測試：
**卡片不可以有叫 target/reference 的參數，vendored 的 `roi_type` 是死的、
不要救活。** 完整的理由與那張未來的比較卡長什麼樣，見計畫書 §3.3.6。

---

### 第二輪：試用回報七項（同日）

七項全做，計畫書 §3.3.5 有逐條的對照。**只有第 1 項是 bug，而它壞得很典型**：

> 「沒辦法 multi-add → 按下 Add them 加不進去 region。」

`add_box` / `add_boxes` 開頭有一句「沒有目前區域就 return −1／0」。從 Studio
打開一張**已經有模板、還沒有區域**的卡時，清單是空的 —— 於是畫出來的框跟按下
Add them **都安靜地什麼都沒發生**，沒有任何訊息，因為程式覺得自己沒事。
拖曳新增走的是同一條路，所以它以前也一樣壞著，只是使用者先撞到 multi add。

處置是 `ensure_region()`：「使用者做了一個明確的動作」與「沒有容器可以裝」
之間，該讓步的是後者。

**第 2 項（自訂 cell size）踩到一個反作用，值得記住**：「×2」第一版把兩軸一起
加倍，在一維 layout（Y 上沒有週期）疊出一個**比原圖還高**的 cell；而
`build_golden_cell` 對明講的 `px`/`py` 不做信心檢查（那是使用者說的，不是猜的），
所以那一軸被當成有週期 —— `locate_axis` 從 `x` 變成 `both`，定位開始在一個沒有
相位的方向上搜尋。現在沒有週期的那一軸鎖起來並講出原因。

其餘五項是介面：四支工具改成圖示鈕（drag／click add／multi add／**paint** ——
第四支的名字是我取的，圖示是點亮的方格不是筆刷，因為畫出來的是像素不是筆觸）、
座標一律吸附到整數 cell 像素、把手從 7 縮到 3（命中判定仍然是 7）、右鍵平移、
視窗放大到 1320×880 且數字表收進一顆按鈕後面。

---

### 這一輪的形狀是使用者改的，而且改得比稽核大一級

我原本的計畫是「12 個參數分小標題 + 把 cell 畫在設定區當參照物」。開工前使用者
喊停：

> 「我們 template 會取一張 GC 對吧，我會想要在那張 GC 上就可以標注 ROI（用 drag
> 用 add box 用點的把 ROI 標注出來），同時也要能分 ROI Group —— 同張影像可能會有
> ROI1 ROI2…，而且 ROI 不限一個矩形。總之這個操作面板要很 flexible 好用。
> 目前的 template 界面太難用，請重新設計。」

而他舉的例子決定了資料模型：「一個 layout 是橫向 EPI 跟直向 MG 交錯，假設我想要
的 ROI1 是 EPI 部分扣掉 MG 交集」——**那個形狀用一個矩形表達不出來，用好幾個就
可以**（正是 §3.3.2 第一題的答案 B，只是這次是使用者自己標）。

### 我把一個尺寸關係搞反了，而更正它換掉了一條規則

我問「ROI 在 patch 上有好幾個落點要取哪一個」（還畫了 ①②③④⑤ 的圖）。使用者：

> 「不對，你大小搞錯了。Template 是一定會比 patch 大的。」

模組說明本來就這樣寫（「patch 比週期小也沒關係 —— 是把小 patch 滑進大模板」），
是我沒讀進去。而他接著補的那句才是關鍵：**要框的東西本身是重複的**
（「隊到哪都會有各種 ROI」）。於是有一條同時涵蓋兩種大小關係的規則，
**不必請使用者選**：

> 框標在 cell 上，映到 patch 時**cell 在這張 patch 裡出現幾次就畫幾個框**。

舊行為只取「離缺陷最近的那一份」—— 在 cell 比 patch 小的時候會**只量到一根
EPI，其餘的靜靜漏掉**。那是第七個「跑得完、有數字、而且是錯的」。

### 做了什麼

**引擎**（commit 1）：`pipeline/cellrois.py` 的字串編碼（一行字串不是巢狀 JSON
—— `curve` 定下的規則照用）、`roi_boxes_in_patch` 整片鋪過去、
`roi_x/y/w/h`+`roi_out` 五個參數收成一個 `regions`、每區域一個
`<name>_present`、舊 recipe 的遷移靠「`roi_out` 在不在」判斷（鐵則 9）。

**區域沒落上這一顆時不再退回整張圖** —— 那會安靜地把所有像素都算進去。改成記進
`meta["regions_absent"]`，而量測卡的錯誤訊息照它講出真正的原因，不再叫使用者
「加一張 ROI 卡」（他已經加了）。

**介面**（commit 2）：`ui/cell_canvas.py` 新的標註畫布 + `template_dialog.py`
重寫成「建模板 + 標區域」一個對話框。三個在畫面上必須是真的東西：**cell 鋪成
一片**（原點錨在最強的上升邊，要框的結構常常橫跨接縫）、**畫出一顆 patch 有多大**
（模板比 patch 大，標在窗外的區域在某些顆上根本不在；不知道就不畫）、以及
**multi add**（兩個十字錨點 + W/H + 數量 → 一次長一整排等距的框，間距由端點算，
不是另外輸入一個看不見的 pitch）。

**`roi_mask` 的 `regions` 從自由文字改成勾選**（新型別 `region_keys` +
`RecipeModel.available_regions`）—— §3.3.1 的第 4 項，順手做掉。

### 「在 cell 上可以拖」跟上一輪「⛔ 拖框被否決」不衝突

否決的理由是「我要跑的是**每一顆** defect」—— 在一顆 patch 上拖到好看，第 50 顆
可能整個偏掉。**但 cell 不是一顆 defect**：它是整批共用的同一個模板物件，在它上面
標框跟拖四支滑桿產出的是同一組數字。所以這裡拖的是尺規，不是猜測（同
Enhance-UI-A「核心大小畫在影像上」為什麼成立的那條分界）。

### 環境

這個容器沒有 X，`libEGL` 也不在 —— `apt-get install libegl1 libgl1` 之後 UI 測試
才跑得起來。`tools/doctor.py` 的「Qt 圖形介面」在這裡本來就過不了（乾淨的
checkout 上也一樣），不是這一輪弄壞的。

---

## Phase 2：計畫書 F11、Input 段做齊、Enhance 段收斂（2026-08-17 第三～九輪）

### 交接（當時的；已被最上面那一份取代）

**現在的位置**：Phase 2 的 **Input ✅ 收斂**、**Enhance ✅ 收斂**，下一段是 **Region**。

**開工前讀這三份就夠**（照順序）：

1. [`AGENTS.md`](AGENTS.md) —— 兩台機器、剪貼簿是唯一通道（不知道會把必要的設計
   當成過度設計刪掉）
2. [`docs/plans/F11-phase2-features.md`](docs/plans/F11-phase2-features.md) **§3.3**
   —— Region 段的稽核與三個定調（下面摘要）
3. [`CLAUDE.md`](CLAUDE.md) 的鐵則十條 —— 尤其第 10 條（畫布不能說謊），
   這一輪有三個 bug 都是它的破口

**Region 段的三個階段（使用者定調，照難度爬）**：

| 階段 | mode | 那張卡 | 主要工作 |
|---|---|---|---|
| **Region-1** | Template | `roi_template` | 12 個參數、**0 個小標題**；四個手打的框座標（`roi_x/y/w/h`）**沒有任何地方講它們相對於什麼**（相對於對位到的那一格 cell，不是整張 patch）|
| **Region-2** | Profile | `roi_cross` | **24 個參數**（使用者回報過「有些我不知道是什麼功能」）—— 做減法：哪幾格其實可以自己算出來 |
| **Region-3** | GDS | 新卡 `roi_from_mask` | 吃 GLAS 的 label map。**第一步是先寫合成 label map 產生器**（家用機沒有 GLAS 的輸出，見 `AGENTS.md` §1）|

**兩個已經定調、不必再問的**：

- **形狀走 B**（每個 layer 切成一堆小矩形）。使用者補了關鍵事實：
  「目前區域**基本上都只會是矩形**」→ 所以那是**等價**不是近似。已記進
  `docs/FAB-VALIDATION.md` 的已確認事實 #6。
- **「框可以用滑鼠拖」被否決**，理由要記住：「我要跑的是**每一顆 defect**」——
  拖框只回答「這一顆對不對」，而 ROI 的參數要對整批成立。該加強的是既有的
  跨顆檢視（F7-11 那扇窗）。

**環境提醒**：測試要**一個檔案一個檔案跑** UI（Qt 記憶體會累積）；改完
`git add -A && python tools/release.py && git add -A`；黃金值用
`python tools/freeze_golden.py --check` 驗（三組 22 顆，逐項相同才算過）。

---


Phase 1 收斂之後開 Phase 2 的計畫。這一輪**沒有動任何程式碼** ——
只讀 code、寫計畫書（[`docs/plans/F11-phase2-features.md`](docs/plans/F11-phase2-features.md)）、
順手修兩處會害人做錯事的文件漂移。

### 讀出來的三件事（ROADMAP 上那一行寫的跟實際起點不一樣）

- **有演算法、沒有卡片，而且是看得見的。** `algo/blob.py` 與 `algo/stats.py`
  沒有任何卡片在用，於是三個引用懸空：`cd_measure` 的警告叫使用者
  「run Blob segment first」（那張卡不存在）、它讀的 `ctx.meta["blobs"]` 沒有
  生產者、`overlay` 的「主 blob 紅框」兩條退路都沒有生產者。
  **F10 那個形狀的親戚：文字（與輸出功能）說得出來的東西，引擎做不到。**
- **多通道的機制在，但 recipe 摸不到命名。** `_channel_name` 支援任意頁數，
  可是 `channel_order` 只有測試傳過 —— 一顆五頁的 defect 現在會載成
  `test, ref, img3, img4, img5`，而 recipe 與 Studio 沒有任何地方改得動。
- **GDS 這一項的起點整個變了**（見下）。

### 使用者定調

| 題 | 答 |
|---|---|
| 演算法 | **不照抄 vendored 的，要重寫／優化改良**。範圍（只動沒卡片在用的那兩個，還是連 18 張卡在用的一起）等確認 —— 後者會讓黃金值全部改變，要重新定錨 |
| GDS ROI | **ADEPT 不解析 layout。** GDS/OASIS 留在上游 GLAS，ADEPT 只吃它產的 mask image、與 defect 一一對應（樣本之後提供）。整項從「vendoring 125 KB 的 OASIS streamer」變成「定一個 mask 進來的契約」，而且**可以用合成資料驗證** |
| ML Classify | Phase 2 後半 |
| 多通道 | 使用者反問「是指一張 TIFF 含多張圖（1 BSE + 4 SE，同時收）嗎」→ 是。實際頁數與順序回問使用者（計畫書 §6.1）|

### 第二輪：讀 GLAS repo、計畫書改成「逐段議程」

使用者補了三件事：**多通道是 1 BSE + 4 SE、BSE 固定在 TIFF 第 2 頁**；
**GLAS 的預期產出直接去讀它的 repo**（上游應該要小改一點，而「那邊要怎麼描述」
由我寫）；以及最重要的一句 ——

> 整體 Phase 2 開發週期應該會拉很長。我自己主要看法是就**從左側功能一步一步往下
> 開發**（從 Input 開始到 Enhance 接著 ROI 一路往下到 ADC），每張卡的預期功能與
> UI 介面與核心設定（要放在哪裡、UIUX 要怎麼放 Card Setting）都需要跟你討論過。

所以計畫書從「六個項目的待辦清單」改寫成**六段的議程**：每張卡要回答四題
（做什麼／吃吐什麼／參數怎麼分組／要不要自己的儀表），並把既有的
`section`/`advanced`/`show_when`/滑桿/`label`/`direction` 那幾個機制列成
「設定要放哪」的對照表 —— 那些是既有卡片一路踩出來的，不要重新發明。

**讀 GLAS 讀到的**（`docs/GLAS-INTERFACE.md`，§4 可以直接複製給那邊）：

- GLAS **已經在產** ADEPT 要的東西：`<id>_label.png`（uint8 整數 label map、
  0=背景 1..N、不 blur）、`<id>_gray.png`（模擬 GLV 灰階，可以當合成 ref）、
  manifest 的 `label_map`（label id → layer 名，正是具名區域的名字來源）、
  alignment CSV/JSON（`mmh-gds-alignment-v1`）。
- **join key 兩邊同源**：GLAS 的 `image_id` 與 ADEPT 的 `defect_id` **都是 KLARF 的
  `DEFECTID`**（`sem_loader.py::load_klarf` vs `dataset.py`）。一一對應不必發明新 id。
- **上游必要的一改**：GLAS 的 `SemImage` 沒有 page 欄位、讀圖是 `cv2.imread`
  （只讀第 0 頁），而 EBI patch 是「一個多頁 TIFF 裝一整批 defect」——
  不改的話**每顆 defect 都對到同一張圖**。ADEPT 的
  `klarf_core.defect_image_map` + `tiff_index` 已經做完這件事，可以直接搬。

### 第三輪：Input-0 落地（多入口）＋ 兩條路都寫死 8-bit

使用者定調「先做多 input 入口」，同時要討論「input 要支援什麼檔案、格式」。

**Input-0（做完了）**：`first = True` 那個「入口＝route 上第一張卡」的定義從三個地方
（`recipe.validate`、`engine._implicit_bindings`、`viewmodel.available_streams`）
收成一個 `Step.is_source()`。判準是**沒有輸入埠、而且沒有靜態 `reads`** ——
第一版只看埠，`test_recipe.py` 當場三條紅（早期風格的假卡片宣告 `reads` 卻沒有
挑來源的參數，只看埠的話它們全部變成入口，`missing-image` 整條檢查安靜失效）。

順帶抓到**這一改造出來的新缺口**：`feature-collision` 的檢查以前不對入口卡跑
（入口只有一張，撞不起來），而現在兩張 `load_patch` 都寫 `n_channels`。

**格式那一半：量出來的東西比預期糟。** 兩條載入路徑都寫死 8-bit 假設，而**兩條都
不出聲**。拿一張 12-bit 的圖實測：`ebi_patch` 走 `to_uint8` → **93.8% 的像素飽和成
255**（而那是現在唯一開放的路）；`rsem`/`folder` 走 `imageio.load_gray` → 每張圖
各自 MINMAX 拉伸 → 亮度砍半的圖載進來平均值**一模一樣**（兩張圖之間不再可比，
而那是 `test − ref` 的前提）。所以廠內若是 16-bit patch，現在每一個數字都是垃圾。
`FAB-VALIDATION.md` 因此新增假設 #4（位元深度）與 #5（多於兩頁時的頁序）。

### 第四輪：Input 卡按 source 拆開，然後範圍縮到 patch + RSEM

使用者回報一個具體的畫面：「load 一張 RSEM image 他就是單張的，但其後的 NODE 節點會有
TEST 跟 REF？**這樣畫布跟實際對不起來。**」量出來的實情比回報的更糟 —— 同一個問題
「這張卡吐哪幾條流」有**三個不同的答案**（`resolve_writes` 說 `["test"]`、
`resolve_writes_for_kind("rsem")` 說 `["single","test"]`、畫布畫的是 `["test","ref"]`，
而資料真的只有 `["single"]`）。

第一層是「換 kind 沒重畫」（`model.kind` 直接設、不通知 listener）。第二層是病根：
**一張卡服務四種 source，而它的宣告隨資料型別改變** —— 也就是
`resolve_writes_for_kind` 這個機制本身。照使用者說的拆成兩張卡
（`load_patch` 一顆好幾張 / `load_single` 一顆一張），兩張都只看**使用者看得到的值**，
那個機制因此沒有人覆寫它了（並加一條對整個 registry 跑的測試守著）。

**然後使用者縮小範圍**：「我決定我暫時不做 multi channel（多通道的），暫時 focus 在
patch 跟 RSEM Image。」而多通道正是 `channel_map` 與 `tiff_stack` 的動機 ——
但兩者**都不是多通道專用的**（前者是 `load_patch` 宣告誠實的條件、後者 `per_defect=1`
就是「一疊 RSEM 影像、沒有 KLARF」），所以這幾輪沒有一項要拆掉重做。

### 第五輪：Enhance 段逐張稽核，第一批把「契約」補上

使用者：「先做 A，請先詳列目前 Enhance 各 card 功能以及你覺得可以怎麼添加完善功能」
→ 看了示意圖之後「GO」。四張卡（`normalize` / `tone` / `denoise` / `flatten`）
逐張稽核，做出來的**不是新功能，是四個「跑得完、有數字、而且沒人講出來」的洞**
（計畫書 §3.2）：

- **Enhance 段的輸出沒有值域契約。** 實測 `stripes_h` → **261.5**、
  `background`+`keep_level` → 250.09。那個超界的值會活到後面某個 `to_uint8` 才被
  壓掉 —— 資訊在使用者看不見的地方飽和，而 `keep_level` 的 help 還寫著「讓影像
  留在原本的灰階區間，下游的門檻才還是同一個意思」：**那句話在修正之前是假的**。
  現在 `MultiStreamStep.run` 一律 clip 回 0–255（**不 rescale** —— rescale 會動到
  每一個畫素，那才真的讓下游門檻全部失效），並吐一個 `clip_frac` 特徵，
  超過 1% 就講一句可以照做的話。
- **`denoise` 的 `strength` 有單位了。** 它的單位一直是「這張圖自己的雜訊 σ」，
  而那個 σ 只活在演算法內部 —— 使用者在調一個以他看不到的數字為單位的旋鈕。
  現在逐流量出來放進 `ctx.meta["noise_sigma"]`，儀表面板印
  `(noise σ ≈ 6.1)`。新增 hook `MultiStreamStep.note_stream`：`build_op` 在迴圈
  之前只呼叫一次，所以它看不到「哪一條流、長什麼樣」，而儀表的問題是逐流的。
- **`normalize/match` 補上 `use_within`**（另外三個方法早就有）。`match` 正是最
  需要它的那一個：patch 上「背景」的面積是隨裁切浮動的（64px 的 patch 裡一根 MG
  進出畫面就是 12%），拿整張圖的統計去對齊亮度，同一片 EPI 只因為隔壁多一根 MG
  就對齊成另一個值。`algo/histmatch.py` 三個 method 加選填 `mask=`，
  **量在 mask 內、套用仍是整張圖**（否則 mask 邊界會出現一道人工階梯，而那道階梯
  會被下游當成邊緣訊號）。`mask=None` 與 vendor 那份逐位元組相同，測試釘住。
- **明確不做銳化／unsharp**：它讓影像看起來更清楚，同時把邊緣位置推走 ——
  而下一段就是拿邊緣量 CD。

黃金值：三組 22 顆**逐項相同**，只多了三個特徵（`clip_frac` 與兩個 `norm_*`），
沒有任何既有數字移動 → 重凍一次。

### 第六輪：Enhance 第二批 —— 三個新方法，全部是既有卡片的一個下拉

使用者「好 可以做」。三個都在回答一個實測出來的失敗，而且**一張新卡片都沒有開**：

- **`flatten/background` 的背景估計法多一個 `median`。** 高斯是加權平均，所以
  缺陷**一定**有一部分被算進背景然後被減掉 —— 實測同一張圖同一個 size，
  一顆 60 GLV 的缺陷經高斯背景減完只剩 43 GLV，換中位數是 59。這不是「核心開大
  一點就好」，是加權平均沒有辦法忽略離群值。cv2 的 float 中位數只支援 ksize 3/5，
  所以大核心走 uint8 的 Huang 直方圖法（背景估計量化到動態範圍的 1/255，
  殘差仍用原始浮點值減）。沒有加 `opening`：`img − open(img)` 就是既有的
  `bright_spots`，同一件事不要兩個入口。
- **`denoise` 多一個 `hot_pixels`：一顆都不磨，只換跟鄰居差超過 4σ 的那幾顆。**
  其餘畫素逐位元組不變 —— 那是它跟另外四種方法的全部差別，所以測試就是逐位元組
  比。換掉的比例 `hot_px_frac` 是使用者調門檻時唯一看得到的回饋。
- **`normalize` 多一個 `zscore`，而且是耐離群的那一版。** 這一項是做的時候量出來
  才改的：一顆 60 GLV 的 4x4 缺陷讓 64x64 patch 的標準差從 5.05 變 6.2 ——
  24% 的「這張圖有多抖」是缺陷貢獻的，於是**兩顆大小不同的缺陷會被套上不同的
  縮放**，正是正規化要消除的東西。改用中位數與 1.4826×MAD 之後，三個振幅量到的
  spread 差不到 1 GLV。要 mean/std 版本的話這張卡的 `match`+`linear` 就是。

新機制一個：`MultiStreamStep.after_stream(ctx, key, before, after, params)`
—— 跟 `note_stream` 對稱，但拿得到前後兩張圖，所以「這張卡動了多少」這類診斷是
免費的（不必把演算法再跑一次）。

使用者同時問「UI 操作面板有沒有需要放任何用來輔助的東東（for 每張卡片）」——
按 F7-17 那條標準（**這張卡最常見的失敗，在單顆畫面上看不出來嗎**）列了五項在
計畫書 §3.2.6，建議先做兩個通用機制，使用者「直接做 A+H」：

- **A：核心大小畫在影像上。** `flatten` 的 *Scale to remove* 與 `denoise` 的
  *Filter size* 的 help 裡唯一的規則是跟缺陷比大小，而畫面上原本沒有任何尺度
  參考 —— 使用者只能猜像素數。現在拖滑桿時影像正中央（patch 是以缺陷為中心裁的）
  有一個虛線方框跟著變。**提案時我想錯了一次**：本來要用「`unit="px"` 就畫」，
  但 registry 裡 `unit="px"` 的參數有一半不是鄰域範圍（`roi_cross` 的條紋間距、
  框線粗細、離邊界留白），拿方框表示「條紋間距」會讓**影像**說謊 —— 所以改成
  一個明講的旗標 `ParamSpec.extent`，判準寫在欄位註解裡。
- **H：整批的削平走勢。** 面板底下多一條「一顆一根」的 `clip_frac`，超過 1% 的
  染警示色，摘要那一行講「100 顆之中的 3 顆，螢幕上這一顆不是最糟的」。
  橫軸刻意是「第幾顆」而不是分布直方圖 —— 使用者接下來要做的事是去看那幾顆。

然後使用者「收掉這三個」，把 §3.2.6 剩下的三項一次做完：

- **C：曲線後面墊這張圖的直方圖。** 曲線的橫軸是輸入灰階，而使用者不知道哪一段
  真的有畫素 —— 於是常見兩種白工：在空的區間上把線拉得很陡（畫面完全沒變化），
  或者把所有畫素都在的那一小段壓平（一動就整片糊掉）。資料用**引擎那份**
  `stream_change[流]['before']`（跟儀表左邊那條細線同一組數字），UI 不自己再壓
  一次 —— 畫面上的分布跟真的跑出來的不一樣，比沒有那個背景更糟。
- **E：磨掉的是雜訊還是訊號。** `removed_over_noise = RMS(before−after) / σ`。
  實測同一張有 2px 條紋的圖：`median ksize=7` → **57.7**（條紋被抹平）、
  `bilateral ksize=7` → **0.64**（條紋留著），而**兩者在單顆畫面上都「看起來乾淨
  了」**。分子要處理後才知道、分母要處理前才對 —— 所以 `note_stream` 與
  `after_stream` 兩個 hook 必須成對存在。
- **B：兩條流處理完之後還有多像。** `pair_level_delta`（背景差幾個灰階）與
  `pair_spread_ratio`（起伏差幾倍），面板印
  `“test” vs “ref” now: 0.8 gray levels apart, spread 1.04×`，差太多就補一句
  「還不能比，diff 會把這個落差當成缺陷」。統計同樣用中位數/MAD；大圖等間隔
  取樣到 65536 個畫素（決定性的，所以 `workers=1` 與 `workers=2` 算得一樣 ——
  鐵則 9 那條線）。**原本以為這一項會改動既有 recipe 的特徵集，結果沒有**：
  三組黃金 recipe 的 Enhance 卡每一張都只接一條流。這一輪唯一多出來的欄位是 E 的
  `removed_over_noise`，而它在真實資料上量到 0.96–0.98 —— 既有 recipe 的 denoise
  拿掉的正好是雜訊，算是這個刻度的一次獨立驗證。

### 第七輪：Enhance 段的最後兩支 lint（這一段收完）

兩支都是「跑得完、有數字、而且是錯的」，而且**兩個在畫面上都好看**：

- **`uneven-treatment`**：test 正規化了、ref 沒有 → 兩張圖不再在同一個灰階尺度上，
  而 `subtract` 減出來的整片偏移看起來就是一個大面積的缺陷。不誤報是這支能不能被
  信任的關鍵，所以它比的是**設定**而不是接線（接線一定不一樣，不然就不是兩張卡）：
  一張卡接兩條流、或兩張卡同一組設定 → 安靜；設定不同 → 講，而且指出差在哪一格。
  `diff` 這種中途產生的流不比（來歷本來就不同），量測卡讀兩條流也不算比較
  （只認 `GROUP_COMPARE`）。
- **`card-order`**：`normalize` 排在 `tone` 之後 —— `tone.py` 的 docstring 早就寫了
  這條，但沒有任何人檢查它，而後果是使用者手動調的那一步完全沒有作用。

兩支都出現在畫布上那張卡身上（既有的 `_node_problems`，F7-13），**UI 一行都沒改**
—— 「在按下 Run 之前就講得出來」是它們存在的理由。

順手修掉一個 Enhance-1 帶進來的新噪音：`clip_frac` 是每一張 Enhance 卡都會產出的，
所以兩份參考 recipe 各多出 2–4 條 `feature-collision`。改成讓卡片**宣告哪些數字是
診斷**（`Step.diagnostic_features`），兩邊都是診斷就不報。做完之後兩份參考 recipe
的 `validate()` 回**空清單**。

### 第八輪：使用者試用回報四項（Enhance-4）—— 三件「畫面在說謊」

使用者實際打開 GUI 操作之後回報的，三件都是**同一條規矩的破口**（鐵則 10），
只是這一次破在影像區與畫布的預設狀態，不在接線邏輯：

- **開窗不再預先放 Load 卡。** F7-9 起開窗就有一張 `load_patch`，那時候只有一張
  載入卡所以是純粹的好意；Input-4 拆成兩張之後，預先放一張就是**替使用者決定了他
  還沒決定的事**，而猜錯的那一半在畫布上看起來完全正常（兩顆埠 vs 一顆埠）。
  但**載入資料的那一刻「哪一張」已經不是猜的** —— kind 就是答案，所以空白畫布會
  補上對應的那張並在狀態列講出來。（使用者只說了「開窗時不要有」；補的那一半是我
  加的，記在計畫書 §3.2.7 ①，要嚴格版就把 `_adopt_source_for` 拿掉。）
- **入口卡左邊不畫輸入埠。** 那顆埠以前的註解寫著「沒有輸入的卡仍畫一顆」——
  它看起來可以接線，但入口卡的資料不是從別張卡來的。現在沒有輸入就沒有埠，
  `in_port_at()` 也回 None（連拖過去的動作都不成立）。
- **沒接線的卡不准有畫面。**（回報：「點選 Denoise 為何會有畫面？」）預覽跑的是
  **整條 route**，而入口卡不需要線就跑得起來 —— 它把 test/ref 寫進了 master
  context；Denoise 失敗，而失敗的策略是「把已經算出來的影像留在畫面上」，於是畫面
  上出現的是**入口卡的輸出**，看起來像 Denoise 的結果。判準改成「選取的那張卡自己
  這一次的 trace」：跑成功才顯示；跑了但失敗 → 不顯示、講引擎那句錯誤；沒跑到 →
  不顯示、講怎麼接線；**後面**某張卡失敗 → 照舊顯示（診斷比清空有用那一半保留）。
- **節點第三行不准被切在字中間**（回報：「normalize 的節點文字會被吃掉」）。
  三個原因各修一個：空值不印（`streams=`）、項數改由**畫的人照寬度**決定並把放不下
  的收成 `+N`（`refer…` → `+1`）、兩邊都空時副標講 `(not connected)` 而不是印
  step key（使用者剛在上面一行讀過同一個字）。

### 第九輪：Region 段稽核 + 三個定調（沒有動程式碼）

照 Enhance 的做法，動手之前先讀 code 稽核一遍（計畫書 §3.3）。最重要的一項是
**具名區域只有「矩形」這一種形狀**（`NamedROI.norm_rect`），而 GLAS 的 label map
是任意形狀 —— 在這之前三張 ROI 卡都是自己**產生**框的，所以沒有人碰到這個限制。

三個定調：

- **形狀走 B**（每個 layer 切成一堆小矩形），而使用者補的那句話讓這個選擇從
  「取捨」變成「沒有取捨」：**「目前區域基本上都只會是矩形。」**
  切成小矩形因此是等價的表示法，而不是近似。C（區域帶一張 mask）不是被否決，
  是還不需要 —— 入口留著（NamedROI 多一個選填欄位）。
- **順序改成 template → profile → GDS**（我提的是「新能力先做」，使用者提的是
  **照難度爬**，而他是對的）：Region-1 是「既有功能 + 介面」、Region-2 是
  「既有功能 + 減法」、Region-3 才是「三個沒做過的東西一起上」。
- **「框可以用滑鼠拖」否決。** 我把它列成稽核的第 3 項並建議做成通用互動；
  使用者一句話推翻：「我要跑的是每一顆 defect。」

### 值得記下來的

- **「動機」與「機制」不必同壽。** 多通道擱置了，而為它做的兩個機制留下來，
  因為實作時解的是更基本的問題（宣告要等於使用者看得到的值）。
  設計對了的話，範圍縮小不會變成白做工。
- **兩條 route 可以共用同一個節點。** v1 的雙輸入 recipe 就是那樣寫的，
  而遷移第一版就地換掉那張共用的卡 → **黃金值當場抓到**（另一條 route 全紅）。
  「改一個節點」在有 route 的世界裡不是局部操作。
- **`resolve_*` 拿到的是原始 `node.params`，不是驗證過的。** 「沒有這個鍵」
  與「有鍵但是空的」是兩件事：前者要回卡片預設、後者是使用者真的清空了。
  混成一件事 → 畫布上的 Input 卡一顆埠都不剩。
- **「入口」用位置定義，撐不到第二個入口。** 而那個定義被抄了三份 ——
  收成一個 classmethod 的時候才發現三份的行為其實不一樣（UI 那一份沒有
  `not-connected` 的概念）。**同一句話寫三次，就會有三種意思。**
- **改一個「只是放寬限制」的地方，會讓別的檢查失去前提。** 多入口本身不危險，
  危險的是 `feature-collision`「入口只有一張所以不必檢查」那個**沒寫下來的前提**。
  放寬限制的時候要問一句：有誰是靠這個限制活的？
- **ADC 段一張卡都沒有，而且只分得出兩類。** `GROUP_ADC` 沒有任何 Step 用它、
  畫布上那張 Score 是 UI 造的假節點（`__score__`）、`ScoreSpec.bins` 被 `validate`
  強制只有 `below`/`above`。一個 ADC 工具的本業是分好幾類，而那件事現在連資料結構
  都還沒有 —— 它剛好排在「一路往下」的最後一站，所以要先知道它不是一張卡的工作量。
- **出口契約留對了，上游換掉也不用改下游。** GDS 從「自己解析」變成「吃 GLAS 的
  mask」，而 `ARCHITECTURE.md` 的定位法契約（吐具名區域）一個字都不用改 ——
  量測卡、`roi_mask`、overlay、region check 全部零改動。
- **一個名字回答兩個問題就會壞掉。** 原本要把「削平」做成一個數字，做的時候發現
  「輸出坐在 0/255 的比例」與「算出了值域外的值」是兩件事：前者看得見（直方圖兩端
  的柱子）、後者看不見。合成一個「新增被釘在端點的比例」試過 —— top-hat
  （`bright_spots`/`dark_spots`）的輸出**本來就**有一大片剛好等於 0 的畫素，那是
  它的用途不是失敗，合起來每跑一次就喊一次狼來了。所以 `clip_frac` 只答看不見的
  那一半，而**界線本身要寫成測試**（不然下一個人會把它讀成「這張卡削平了多少」）。
- **「說謊」不只發生在畫布上。** F9/F10 那條「畫布不能說謊」換到影像上是同一件事
  —— 一個表示「條紋間距」的方框，跟一條使用者沒拉過的線一樣糟。所以那個旗標寧可
  一張卡一張卡填（現在只有兩個參數填了），也不要從 `unit` 推導。
  **推導看的是值，宣告看的是事實** —— 這句話這一輪第三次派上用場。
- **一句警告的門檻不能是參數。** `CLIP_WARN_FRAC` 是寫死的 1%：給它一個旋鈕，
  第一件事就是有人把它調高讓警告消失，而警告在講的事情不會因此消失。
- **一個「看起來明顯有用」的互動，可能整個弄反了工作的尺度。** 我建議「框可以用
  滑鼠拖」，使用者一句話推翻：**「我要跑的是每一顆 defect。」** 拖框是對**一顆**
  調到好看，而 ROI 的參數要對**整批**成立 —— 那正是 F7-11 做跨顆檢視的理由。
  對照組是 Enhance-UI-A（把核心大小畫在影像上）：那個畫的是**參數自己的大小**，
  跟哪一顆無關，所以它成立。**同樣是「把參數畫在影像上」，一個是尺規、一個是猜測。**
- **「先幫你放好」會在選項變成兩個的那天變成「替你決定」。** 起手卡在只有一張載入卡
  的世界裡是好意，拆成兩張之後就是猜 —— 而**這種退化沒有任何測試會抓到**，因為
  每一條斷言都還是真的。加第二個選項的時候要回頭問：有哪個「貼心的預設」現在變成
  一個猜測了？
- **「失敗了就把上一張圖留著」在有 `upto_node` 的世界裡是說謊。** 那個策略
  （診斷比清空有用）本身沒錯，錯的是它沒有問「留著的圖是**誰**的」。介面上只要
  出現「看到 X 就以為 Y 做了事」，那就是同一種 bug —— 跟畫布多一條線一模一樣。
- **加一個特徵，會讓一支既有的 lint 開始亂叫。** `clip_frac` 讓「兩張量測卡撞名」
  那支警告在**每一份正常的 recipe** 上都出現 —— 而使用者學會忽略一條警告之後，
  真的那一條也一起被忽略了。所以加診斷數字的時候要順手問：**有誰在數特徵的名字？**
- **懷疑一句訊息在說謊之前，先把整條路讀完。** 我一度認定
  「The earlier one is still available as `<owner>_<f>`」是假的，因為
  `Context.add_feature` 確實只是覆寫 —— 但 engine 在外面包了
  `_rescue_overwritten_features`。差一點「修掉」一句本來就對的話。
- **一對 hook 常常是一個 hook 的兩半。** `removed_over_noise` 的分子只有處理後
  才知道、分母只有處理前才對 —— 少了任何一邊這個數字就是錯的（用濾過的圖量 σ，
  比值會無限膨脹）。所以 `note_stream` / `after_stream` 不是兩個獨立的方便設施，
  是**同一件事的前後兩端**。
- **「不帶前綴」也是一種宣告。** `pair_*` 講的是「這兩條流之間」，掛在其中一條的
  名字下面會是錯的 —— 所以前綴規則不能無腦套在每一個新特徵上。
- **診斷數字要問「它是誰的性質」再決定放哪。** 雜訊 σ 是**影像**的性質（接不接
  Denoise 都一樣），所以進 `meta`；`clip_frac` 是**這張卡幹的事**，所以是特徵
  （進 CSV、可以拿來 gate）。放錯的代價很實際：σ 當特徵的話，「有沒有這個數字」
  取決於使用者有沒有放那張卡 —— 那不能當 gate。
- **文件漂移抓到一處是會害人的**：`FAB-VALIDATION.md` 還叫公司機複製
  `bundle/ADEPT_part1of6.py … part6of6.py`，而那些檔案早就不存在（現在是單檔）。
  照著做的人會什麼都搬不進去。順手連 `SESSION_LOG` 開頭那句 1 MB 一起修。

---

## F10 收尾：剪線／刪卡／改名三個反向操作，加上主動稽核（2026-08-17 第二輪）

第一輪修完三項之後，使用者又回報兩個，而它們跟前面**是同一個形狀**：

> 連接卡片節點後，再把線按 X 清掉 → 後方卡片的 Node 不會跟著清掉。
> 刪掉 Profile 這整個 Card 後，再 add new card profile，DAG 畫布上線還會殘留。

兩個都是「**某個動作的反向操作只做了一半**」：接線會改參數但剪線不會、加卡會
建節點但刪卡不刪線。而刪卡那個更麻煩 —— 殘留的線指著一個不存在的節點，
`_new_id` 又會把同一個編號再發一次，於是新卡被一條使用者從來沒接過的線接上。

### 於是這一輪改成主動稽核，不等下一次回報

寫了兩支稽核腳本，把每個動作與它的反向操作系統性地走一遍（11 項：復原/重做、
改名、刪中間卡、停用、換順序、載入既有 recipe、成環、round-trip、每張卡的
加接剪刪、畫布線數 vs model 線數）。**抓到一個使用者還沒踩到的**：改輸出流的
名字時下游沒有跟著走，於是「幫一條流取個好記的名字」會把整條 pipeline 弄成
`missing-image`，而畫布上線還在（線是照節點畫的）。

接著使用者回報第七項（`Write result to` 不給輸入），修的時候又掃到「空的就
偷偷退回預設」這個暗門的**第三個實例**（`roi_mask`）。所以那件事也升級成一條
對整個 registry 跑的不變量，而不是修完就算。

### 值得記下來的

- **同一類 bug 出現第三次，就該把它變成不變量。** `MultiStreamStep` 的
  `keys or ["test"]`、`_unpoint_stream` 的保留條款、`roi_mask` 的
  `or "test"` —— 三個看起來完全不同的地方，同一個形狀：**宣告出來的東西比
  使用者接的多，而畫布是照宣告畫的**。
- **自己踩了一個，被既有的測試網接住。** 改名那一項第一版用
  `compound("set-param")` 包住，結果繞過 `coalesce`，滑桿拖一次會記幾十步
  復原。`test_one_ctrl_z_undoes_a_whole_slider_drag` 當場紅。
- **Phase 2 與 Phase 3 對調**（使用者定調：「我想優先做好內部的每個功能」）。
  理由跟 Phase 1 先做的理由同一個：對著還會長的東西寫手冊與範例，寫完就得
  重寫。範例 recipe 現在刻意一份都沒有（「還沒打算給人用，就我自己測試」）。

### Phase 1 收斂前的最後一次全面驗證

| 項目 | 結果 |
|---|---|
| 核心測試（含 3.9 語法、core 不得 import Qt、無廠內識別碼） | 1033 passed / 28 skipped |
| UI 測試（34 個檔案逐檔跑） | 全綠 |
| 黃金值 `freeze_golden.py --check` | 三組 22 顆**逐項相同** |
| 稽核腳本（11 項不變量） | 0 問題 |
| CLI 端到端 + `--ground-truth` | 正確率 100%（合成資料）|
| 冷跑 vs 熱跑（`--cache`） | CSV **逐位元組相同** |
| `tools/doctor.py` | 全部通過 |

---

## F10：畫布要符合現實 —— 剛加的卡前後都是空的、埠點得到、量測卡多連一（2026-08-17）

使用者在畫布上實際操作之後回報三件事，並補了一句總綱：**「最重要的是 DAG 畫布
要符合現實。」** 後來又把核心架構講成一句話：

> 一張卡片剛被 new add 時，前後應該都是空的乾淨的，連上 source，後面 source
> 才會出來。

三件事的病根不同，但都是同一句話的反面。逐項的完整紀錄在
[`docs/plans/F10-canvas-tells-the-truth.md`](docs/plans/F10-canvas-tells-the-truth.md)。

### 1. 先確認問題（用探針，不是讀 code 推論）

最重要的一個數字：**一份零條線的 recipe 與一份三條線齊全的 recipe，跑同一批
defect 逐項相同**（glv_mean 6.7626 / glv_max 33.0…），而 lint 全綠。那就是
「畫布不符合現實」的量化版本 —— 畫面上的線與引擎拿到的圖沒有關係。

「一連多點不到」的真相比回報的更糟：`out_port_at` 取「第一個落在半徑內的」而
抓取半徑（15px）比三顆埠的間距（14px）大，所以**線拉得出來，只是接到隔壁那條
流** —— `subtract` 點 `test` 拉到 `diff`、點 `ref` 拉到 `test`，而畫面上那條線
看起來完全正常。

「Measure 卡自動連接」則是兩件事的合成：沒有線也算得出數字（上面那條），加上
一條「沒有埠」的線會被畫成好幾條。加卡本身不會產生線（F9-7 已經修掉）。

### 2. 四個要使用者定調的點

問了四題，答案分別是：**兩層都改**（畫布＝現實）、**空值就是沒接線**（清的是
這一張卡的值不是卡片的 default，所以黃金值不動）、**ParamSpec 加欄位＋測試
強制**（不要用推導 —— 推導看的是值，而新卡的值本來就是空的）、**量測卡開放多
連一並自動加流名前綴**。埠太擠那題選了**只修命中判定**。

期間使用者另外解除一個限制：「舊有範例 recipe 全部刪光光，不要被她限制。」

### 3. 做完之後

- 加一張卡：前後都沒有埠，設定區的來源是空的，lint 說 `not-connected`，畫布
  掛警示，引擎在跑之前就擋下來並講一句可以照做的話。
- `Compare to stream` 接上第一條線時後面**仍然沒有** `diff`；兩條都接上才長
  出來。`write result to` 改成 `GGG`，畫布上那顆埠就叫 `GGG`。
- 每一格輸入一顆埠，線落在哪一格由使用者放開滑鼠的位置決定（以前是 Studio 用
  一張寫死的名單猜，所以 `subtract` 的 a/b 永遠只挑得到同一個）。
- 量測卡接兩條線就吐兩組特徵（`diff_glv_max` / `test_glv_max`），**只接一條時
  名字逐字相同**。

### 4. 值得記下來的三件事

- **`QPainterPath` 預設是奇偶填充。** 把埠的抓取圈加進 `shape()` 之後，圈與
  卡片本體的交集被「抵消」成洞，於是輸入埠的圓心反而不算命中 —— 測試抓到的。
  要 `WindingFill`。
- **`boundingRect` 是 `shape` 的上限。** Qt 先用 boundingRect 粗篩再問 shape，
  所以 shape 伸出去而 boundingRect 沒跟上的那一圈，點下去完全沒有反應。
  這個 repo 在「畫得出去的東西」上踩過三次，這是同一條規則的**命中**版本。
- **27 條既有測試踩到舊契約，其中兩條的前提被推翻。** 前者補上「使用者現在
  真的會做的事」（加完卡要接線 → `conftest.wire_up`）；後者改寫並在 docstring
  裡寫明為什麼那個前提不再成立 —— 直接刪掉的話，下一個人會以為那件事從來沒有
  被想過。

---

## Phase 1 收斂：準確率接進調參迴圈、DAG 的四個洞、卡片不變量補齊（2026-08-16 第四輪）

### 1. 準確率接進調參迴圈（Phase 1 最後一項可在家做的）

「分類準確度」是這個工具的 KPI，但它以前只有 CLI 看得到 —— 而**調門檻是在
Studio 裡一邊拖一邊看的**。使用者拖完滑桿得跳出去跑一次 CLI 才知道剛才那一下
是變好還是變壞，於是實際上沒有人在看準確率。

- `python -m adept run --ground-truth`：跑完直接印正確率／抓漏率／誤殺率；
  沒給就自己找 KLARF 旁邊的 `ground_truth.json`（`--ground-truth none` 關掉）。
- Studio 載資料集時撿同一份答案卷，直方圖旁邊的 bin 摘要跟著門檻**即時**顯示
  準確率。只重算分 bin（`viewmodel.accuracy_at` → `export.summarize`，跟 CLI
  同一份邏輯），**不重跑任何影像**。
- 撿到哪一份掛在直方圖的 tooltip 上。原本寫在狀態列，實測那句話活不過幾毫秒
  —— 載完馬上接著算預覽就蓋掉了。
- 換資料集要**清掉**上一份答案卷：不清的話會拿 A 的答案去對 B 的結果，
  而那個數字看起來完全正常。

順帶抓到一個自己種的坑：`_load_ground_truth_beside` 原本是 bare
`except Exception`，於是 `json` 忘了 import 只表現成「這份資料沒有答案卷」——
**找不到跟寫錯了長得一模一樣**。改成只吞 `OSError/ValueError/UnicodeDecodeError`。

### 2. F9-7：線全部由使用者拉，一個輸入埠只有一條線

使用者回報（附畫布截圖）：**「新增卡 不要自己接線（線都給 user 接）」**，
並問「如上連法會發生什麼事」。截圖上 `Load images` 與 `Denoise` 同時接進
`Adjust tone` 的同一個輸入。

**答案是：只有一條算數，而贏的是 `recipe.edges` 裡排在後面的那條** ——
引擎查來源的 key 是 `(下游節點, 流名)`，`dict` 後寫的贏，而那個順序在畫布上
完全看不出來。症狀是「我明明接了 Denoise，跑出來卻像沒接」。

**病根是自動接線**：那條 `Load → Adjust tone` 使用者從來沒畫過，是舊版
`add_card_after` 加卡時順手接的 —— 畫布上有第二個作者。

做了三件事：加卡不再產生任何線（順序照排）；往同一個輸入埠再拉一條線時舊的
讓位並在狀態列講出換掉了誰；`recipe.validate` 新增 `ambiguous-input` error
擋手寫的雙線。順帶把「拉一條線」收成**一步復原**（以前是三、四步，按一次
Ctrl+Z 會停在「線還在但埠沒了」）。

沒做：沒有把新卡的來源參數清成空字串。清了畫面更誠實，但參數預設值是 recipe
的語意（省略 = 用卡片預設），清空等於 GUI 產出的 recipe 跟手寫的不一樣，
而且每張新卡在接線前都會 lint 失敗 —— 那要連 lint 訊息一起設計。

### 3. F9-8：針對分支路徑的稽核，找到四個會算錯數字的洞

使用者問「引擎段確定沒問題了嗎」。用**可執行的探針**（不是讀 code 推論）把
F9 之後的資料路徑逐條走一遍，找到四個，全部同一個病根：**身分改成
`(節點, 埠)` 了，但快取、停用、以及邊的儲存這三處仍然用全域名字在想事情**。
線性 pipeline 不受任何一個影響（黃金值三組 22 顆逐項相同）。

已修：**改一條線不會讓快取失效**（簽章只算 node + params，而改接線可以完全
不動參數 —— 使用者的體感是「我改了接線、重跑、數字沒動」）；**停用分支中間
那張卡，下游會去吃另一支的資料**（查不到就退回「最後一個寫這個名字的人」）。

未修兩個，各有一個要使用者定調的點（快取檔可以變多大、畫布允不允許兩條
平行的線），寫在 `docs/history/plans/F9-dag-streams.md` §12。

### 4. F9-9：一對節點之間可以有好幾條線

使用者定調：「餵圖是節點跟節點間在處理的，卡片只負責『餵進來的這些 source
要怎麼處理並再把 result 丟出去』，所以理想上可以多連一，也可以一連多。」

那句話把責任切乾淨了 —— 而「一對節點只能有一條線」正好違反前半句。`Edge` 的
「重複」判準從**兩個節點**改成**整條線**（兩個節點 + 兩個埠）；畫布改成照
`model.edge_lines()` 畫，不再從「兩端共用哪幾條流」推（推出來的猜不出使用者
其實只接了其中一條）；剪刀帶著自己那條的流名，剪一條不會剪掉兩條；剪掉之後
那條流也從卡片的參數裡拿掉 —— 否則畫布會反過來說謊。

最後一條線不清空參數：`MultiStreamStep.stream_list` 對空字串是
`keys or ["test"]`，清成空的那張卡會安靜地跑回 test。

### 5. F9-10：分支 + 快取，四個洞收完

最後一個：分支 recipe 跑第二次數字會變（快照只存 `ctx.images` ＝ 名字 → 最後
一個寫它的人，分支之後同一個名字有好幾張圖）。

做法是使用者定的「**選擇性存 + 缺了就重算**」。討論過程值得記下來：直覺的
「只存有人在用的那幾張」單獨用是**不安全的** —— 「誰要用」是由 checkpoint
**之後**的線決定的，而那些線刻意不進簽章（不然改一下量測卡的接線就要整段重算
影像）。於是必然會出現「快取有效、但這次要的那張沒存」，而那時候退回
`ctx.images` 就是安靜地拿錯圖。所以那條防線不是可選的配套，是這個做法成立的
前提。

另外只算**明講的線**：推出來的來源本來就是「最後一個寫這個名字的人」，
退回去拿到的是同一張圖 —— 所以既有的（沒有埠的）recipe 快取大小完全沒變。

### 6. 卡片的數值行為逐張過一次（Phase 1 收斂）

`tests/test_card_invariants.py` 原本鎖兩條（I2 換行程相同、I3 只碰宣告過的
東西），docstring 裡記著「還沒做的：I1／I4／I5／I6」。這一輪補齊，六條全部
**自動套用到 registry 裡每一張卡**。

其中兩件事值得記下來：

- **I4 第一版是假的綠。** 「跑一次全程、跑一次冷、跑一次熱，三者相同」看起來
  很完整，但被測的那張卡落在 checkpoint **之後** —— 它產出的東西根本不必經過
  快照。把「快照不存 rois」那個真的 bug 放回去，測試照樣全綠。修法是在後面補
  一張影像卡把 checkpoint 推過去，而且**卡片有定義具名區域時再補一張量它的
  卡**（那正是那個 bug 的形狀：Region 卡在段內、量測卡在段外）。補完之後放回
  bug 就會紅。
- **I5 的 NaN 那條，我一開始把因果寫反了。** 本來寫「NaN < threshold 是 False
  → 判成真缺陷」。實際跑過才發現 `expression.py` 是 SAFE 語意，nan/inf 一律歸
  0.0，所以下場是 **score=0.0 → 判成 nuisance（漏抓）**。結論不變（NaN 是安靜
  地錯），但方向相反 —— 這種事只能跑一次才知道。

四條都用「把對應的 bug 放回去」驗過會紅：注入非決定性 → I1 紅；快照不存 rois
→ I4 紅；某參數在上界吐 NaN → I5 紅；卡片假設 128² → I6 紅。

現況：70 組極端參數裡 69 組跑得完、1 組被擋下（`snr_map` 的 `exclude_border=100`
會把整張圖挖空，訊息講得出人話），**沒有任何一張卡吐出 NaN／Inf**。

### 7. 收尾

- F9 計畫書封存進 `docs/history/plans/`（十一段全部結案，§15 是收尾清單）。
  最後一條尾巴 F9-11 也收掉了：「還缺什麼上游」的提示以前照 route 的線性順序
  算，畫布上明明有線它卻說還缺 —— 而錯的指示比沒有指示更糟。
- `docs/ROADMAP.md` 的 Phase 1 標成**收斂**，並寫下「數字可信」現在由哪三層
  守著（黃金值、六條卡片不變量、可量化的 KPI）。
- KLARF 變體驗證由使用者定調**遇到再說**，不再擋 Phase 1。

**這一輪一共修掉 6 個會安靜算錯數字的 bug**，全部有迴歸測試，全部驗過「把 bug
放回去會紅」。

### 8. 「功能卡還能勾選影像來源」= 舊版

使用者回報 Enhance 卡的 Image Stream 還可以勾。查過 registry 裡每一張帶
`image_key`/`image_keys` 的卡，設定區給的都是唯讀顯示（F9-6，commit 5628a2f，
已推上分支）。看到勾選框的是**還沒更新的那一份程式**。

---

## 存檔 recipe 退場、一個會算錯數字的遷移、文件收成一主題一個家（2026-08-16 第二輪）

### 找到一個真的 bug：一份 recipe 存檔前後會算出不同的答案

上一輪把 `test_batch_cache` 那兩條紅的歸給「容器裡的套件版本」。**那個判斷是錯的，
它是真的 bug**，逐段追出來的：

- 同一個行程裡跑五次 → 完全一致（不是浮點雜訊）。
- parent 行程 vs subprocess → **每一顆都不同**，`glv_max 50 vs 43`、`score 81 vs 64`。
- 逐張卡比影像流雜湊 → `load` / `norm_ref` / `norm` / `align` 全部逐位元組相同，
  **分歧從 `subtract` 開始**。而 `subtract` 是純 numpy 的 `a - b`，不可能不決定性。

矛盾的解答在 `from_json_dict`：有一道 2026-08-14 的遷移看到 subtract 沒寫 `b`
就補上 `ref_aligned`。於是記憶體裡的 recipe 比 `test - ref`（卡片的新預設），
**繞過 JSON 的那份比 `test - ref_aligned`**。而 `run_batch` 正是用
`to_json_dict → from_json_dict` 把 recipe 送進 worker 的 —— 所以
`workers=1` 與 `workers=2` 算出不同的分數，兩邊都跑得完、都有數字。

**根因是判斷依據，不是那一行**：這個 repo 有四道遷移，另外三道都看「**舊 key／舊值
在不在**」，新 recipe 永遠碰不到。只有這一道看「**新 key 不在**」，而「舊檔案靠舊
預設」跟「新 recipe 靠新預設」從缺一個 key 是分不出來的。

已移除該遷移（兩份 fixture 都明寫 `b`，行為零改變），並把規則寫成**鐵則 9**、
在 `from_json_dict` 留一段註解、加兩條迴歸測試
（`test_a_json_round_trip_changes_nothing`、`test_reading_a_recipe_never_invents_a_parameter`）。
`test_batch_cache` 13 條全綠。

### 使用者定調：存檔 recipe 的功能先拿掉

「先把整個 engine 用好，再來支援」。所以：Studio 沒有 `Save Recipe…`、沒有 Ctrl+S、
`StudioWindow.save_recipe_path` / `_on_save_recipe` 移除，**`Recipe.save()` 也移除**
（移除後只剩兩支測試在用它）。**讀取全部留著** —— CLI `run` 照跑、fixture 照用。

連帶要想的是**關窗提示**（F7-16 的四張安全網之一）：它以前有三個答案，預設是「存檔」。
存檔沒了，那顆鈕就變成做不到自己承諾的東西。現在只剩「丟掉 / 先別關」，**預設改成
先別關**，而且話講得更白：關掉之後沒有任何辦法把這份 pipeline 找回來。

測試那邊有三支是「照樣綠、但測錯東西」（第三次遇到這個樣式了）：
`load_template()` 現在回 False 而沒人檢查回傳值、`Ctrl+S` 的 tooltip 測試改用
`Ctrl+O`、存檔往返改成測 `model → recipe → JSON → recipe` 的 identity（那正是
`run_batch` 走的路，比存檔往返更該被鎖住）。

### 文件：一個主題一個家

使用者要求「以後接手的 agent 不要花太多 token 讀，也不要漂移」。關鍵觀察是
**`CLAUDE.md` 會被讀進每一個 session** —— 它 60 KB，等於每開一次新 session 就付
一次那個 token。所以：

| 搬去哪 | 內容 |
|---|---|
| `docs/ARCHITECTURE.md` | 心智模型（三段式）、資料模型（兩個通道）、目錄結構 |
| `docs/PITFALLS.md` | 30+ 條坑表（10 KB，只增不減） |
| `docs/ROADMAP.md` | 進度 + **Phase 1–4 計畫**（以前這張表在四個地方各一份） |
| `docs/FAB-VALIDATION.md` | 待驗證假設 + 受限機器部署 |

`CLAUDE.md` **60 KB → 12.7 KB**（-79%），只留「不知道就會做錯」的東西：鐵則、
加卡片、開發流程、範圍開關，最上面加一張**路由表**（哪個主題住在哪、什麼時候該去讀）。
README 19 KB → 4.4 KB，也變成門面 + 路由。

順手把 15 處指向 `CLAUDE.md §7 / §2 / §8 / §9.5` 的程式碼註解改指新家 ——
那些正是「搬了文件卻沒跟上」的下一個漂移來源。所有 md 的內部連結掃過，0 個壞掉。

### 1 MB 不是牆（使用者更正）

超過之後還有 raw 連結可以打開複製。所以 `release.py` 的水位警告從「快撞牆了 /
通道斷掉」降級成單純報大小，`--check` 不再因為大小回非零；`AGENTS.md` §2 與
`docs/history/README.md` 的理由也一起改成「哪一種複製法還能用」而不是「搬不搬得進去」。

### 測試

核心 826 passed；UI 受影響的 6 個檔案逐一跑過全綠。**UI 測試不要用一個行程跑整套**
這件事寫進 `CLAUDE.md` 與 README 了（容器裡實測跑不完，一個檔案一個檔案跑各 1–10 秒）。

## 專案整理：文件對齊現況、搬運餘裕、封存、範例入口收起來（2026-08-16）

使用者要求「先讀完整個專案再整理」。盤點出四類問題，四類都做了。

### A. 文件在說一個不存在的專案

最嚴重的一條**會直接害到第一次用的人**：五份教學範例 recipe 在 39b9fea 就刪了
（它們依賴被拿掉的卡片），但 `examples/recipes/README.md` 的對照表仍完整介紹那
五份，README 與 CLAUDE.md 的 CLI 範例也還是 `python -m adept run
examples/recipes/die_to_die_basic.json …` —— **照著打會失敗**。

而它不只在文件裡。`tools/doctor.py` 的端到端試跑也讀那個檔案，找不到時說的是
「原始碼解壓不完整，請重新解壓一次 GitHub 的 zip」——**一個錯的診斷**，而 doctor
存在的唯一理由就是在裝不起來的機器上給出對的診斷。第一次裝的人會照著重解壓一
次，然後看到同一句話。doctor 現在**自己帶著一份最小 pipeline**（`_SMOKE_RECIPE`，
四張卡），不讀 repo 裡任何 recipe 檔。

順帶修掉的過期敘述：README 的目錄樹還是 M0 時代的（把 `tests/`、`docs/`、
`tools/` 畫在 `adept/` 底下，而 `core/` 漏了 `pipeline/`、`steps/`、`store/`、
`export/` 四個現在最重要的目錄）；測試數字三個版本（README「1200+」、CLAUDE.md
「520+」、commit 訊息「726」，實際 1050+）；AGENTS.md 的檔案數與包大小。

### 使用者定調：範例 recipe 全部拿掉，demo 入口收起來

`examples/` 整個移除。連帶地，**沒有 recipe 可載就沒有能按的入口**：範本庫開起來
是空的，「用範例資料試一次」產得出資料卻載不到 pipeline。對不會寫 code 的目標
使用者，**按了撞牆的鈕比沒有那顆鈕更糟**（推廣鐵則）。

所以照 F7-1 那套辦法：`ui/scope.py` 加 `SHOW_SAMPLE_ENTRIES = False`，
把工具列的 `Templates…`、導覽與空白狀態上的「用範例資料試一次」都藏起來。
**收起來的是入口不是能力** —— `run_demo` / `generate_demo_lot` /
`RecipeLibraryDialog` 一行都沒動，範例回來的那天改一個常數就整組回來。

這一輪最容易漏的不是鈕而是**旁邊那兩句話**：空白狀態的「or try the tool with
generated sample data」與導覽底下的「按左邊那顆，一分鐘就看得到分數」。鈕藏起來
了、文案還在推薦它，使用者會去找一顆不在畫面上的鈕。兩句都改了，並且
`test_nothing_on_screen_points_at_a_button_that_is_not_there` 鎖住。

**測試那一半比程式碼那一半難。** 三支測試在改動之後**照樣是綠的，而且測錯了東西**：

- `test_the_shipped_example_recipes_have_no_combination_errors` 掃
  `examples/recipes/*.json` —— `glob` 對不存在的資料夾回空清單、不丟例外，
  於是它「檢查了 0 份 recipe」然後通過。改掃 `tests/fixtures/recipes/`。
- `test_ui_f7_16_safety_net.py` 三處 `window.load_template()` 現在回 `False`，
  但沒人檢查回傳值，而 `run_trial` 用空流程也跑得完 —— 中止鈕的行為在「有東西
  可跑」的前提下才有意義。改成載 fixture recipe 並斷言 `is True`。
- `test_the_empty_panel_offers_the_two_things_you_can_do` 斷言的是
  `btn_empty_sample.text()`，而藏起來的鈕文字沒變。

第三條連著一個踩到的坑：改成問 `isVisible()` 之後測試紅了 —— **視窗還沒
`show()` 之前每一個 widget 的 `isVisible()` 都是 False**（CLAUDE.md §7 早就記了
這條）。要問「有沒有被明確藏起來」得用 `isHidden()`；用 `isVisible()` 的話那條
測試會**永遠是綠的**，包括開關打開的時候。

`tests/test_example_recipes.py` 整支刪掉（庫空了它就沒有東西可測）。
`RecipeLibraryDialog` 的「照資料夾內容列出來」改用測試自己造的暫存庫測 ——
其實比以前準：以前綁著 repo 裡剛好有的那幾份，庫換內容測試就要跟著改。

### B. 搬運包剩 6% 餘裕，而破線沒有任何症狀

`bundle/ADEPT_bundle.py` 量到 **962 KB**，而 GitHub 不顯示超過 1 MB 的檔案 ——
那正是這個包存在的唯一理由。家用機上看不出任何異狀：測試不會紅、`release.py`
不會錯，症狀只會出現在公司機的瀏覽器裡，而那時候人已經站在機台旁邊了。

而且 `make_text_bundle.py` 自己的門檻是 `LIMIT_KB = 900`，**它的 CLI 早就會自動
分批了**，只有 `release.py` 還在無條件寫成一個檔案 —— 兩支工具對同一件事的判斷
已經分家。

做了兩件事：

1. `release.py` 加 `bundle_size_report()`：每次產完報水位，超過 85% 出聲、
   超過 1 MB `--check` 直接回非零。切成純函式才測得到（產一個 1 MB 的包只為了
   驗那段訊息太貴）。
2. `docs/history/` **不進搬運包**（`make_filelist.EXCLUDE_DIRS`，
   `make_text_bundle` 改成 import 同一份定義 —— 兩份各自維護的排除清單一定會
   分家，而分家的下場是公司機解完包永遠報「還缺幾個」）。

把 SESSION_LOG 的 7 月份（125 KB）與**做完的** F7 計畫書（125 KB）封存進去之後：
962 → **888 KB**，回到 `LIMIT_KB` 以下，「1 次複製」的承諾守住了。

要講清楚的是這只是買時間：程式碼與測試本身也在長，而它們**必須**進包。
真正撞牆那天的答案是 `--split` 分批（機制已經在了），代價是複製次數變多。

### C. SESSION_LOG 的順序在說謊

2718 行、三批不同排序拼起來的：前 ~1650 行新→舊，第 1657 行掉回 07-28 那批，
第 2161 行起又變成 F7-9 → F7-17 **舊→新**。要找一件事發生在什麼時候，得先猜
自己在哪一批裡。

封存的時候一起修好：7 月份搬進 `docs/history/2026-07.md` 並統一成新→舊。
**內容一個字都沒有改** —— 用 block 集合逐段比對驗過（38 段，一段不差）。
F7-17 落在 F7-18 後面正好是對的（那是它真正的時序）。

### D. 程式碼結構：只做了確定安全的

- `algo/blob.py` 補上「別當死碼刪掉」的檔頭。它現在沒有任何卡片用到
  （`blob_segment` 在 39b9fea 拿掉了），但被拿掉的是卡片不是演算法 ——
  跟 `algo/period.py` 同一類的陷阱。`algo/profile.py` **不是**孤兒
  （`grid.py` / `template.py` 還在用），別誤刪。
- 根目錄 `conftest.py` 與 `tests/conftest.py` 一開始被我列為「重複」，
  **看完之後確認不是**：前者是 `sys.path` 修正（必須在根目錄，那就是它的作用），
  後者是「測試裡不准跳 modal 對話框」的 fixture。合併會弄壞前者。

**沒有做**：拆 `ui/studio.py`（3347 行）與 `ui/widgets.py`（3400 行）。
理由寫在這裡以免下次又要重想：那是這個 repo 最大的兩塊，而拆它們是**純結構
改動、零行為改變**，唯一的驗收方式就是整套 UI 測試 —— 而 UI 測試在單一行程裡
跑整套會慢到不可用（AGENTS.md §5 已記，這次實測再次確認：跑了半小時沒跑完）。
要做的話得先有分段跑的辦法，那本身是一件獨立的事。

### 這個容器上的兩件事（不是專案的問題）

- `test_batch_cache.py` 兩條在**乾淨的 HEAD 上就是紅的**（serial 與 parallel
  的分數不一致，30 vs 40）。用 `git worktree` 開一份 pristine 確認過，不是這一輪
  造成的。可能是 numpy 2.4 / opencv 5.0 這種版本組合，也可能是真的 —— 沒有追。
- `doctor.py` 的 Qt 那一項在無頭容器裡必紅（開不了視窗），裝了 `libegl1` 等
  系統套件之後其餘都過。

## 第七輪：擬真 BSE 測試資料產生器收進 tools/（2026-08-14）

跟使用者五輪迭代（layout → 擬真 SEM → inner spacer → 梯度與紋理 →
BSE 物理與線寬）收斂出 `tools/make_mgepi_real.py`：MG×EPI×inner-spacer
的擬真 BSE 合成 lot，缺陷（Hf）一律在 spacer 中間亮起，絕對 GLV 與
MG+bloom 重疊 —— **整張圖的 max 挑不出它，只有量 spacer ROI 看得到**。
這批資料的存在理由就是逼出 ROI 流程。`tools/validate_mgepi.py` 是
可分性驗證，也是量測邏輯的參考實作（實測 whole-max 重疊、
spacer test-max gap +6.6、(t−r)+ max gap +3.4，後兩者零重疊）。

被反例逼出來的量測教訓（詳見 validate_mgepi.py 檔頭，接 pipeline 照抄）：

- **GLV band mask 定不出 spacer**：缺陷把 spacer「亮出範圍」之後它就
  不再像 spacer，mask 會把缺陷自己剔除。要用幾何找谷。
- **先選帶、再壓剖面**：整欄平均把 spacer 的谷跟行間更暗的 STI 混在
  一起，找谷會找到行間去 —— 只在 EPI 列上壓欄剖面。
- **在 ref 上定位、在 test/diff 上量**：缺陷會把 test 的谷推亮、定位
  帶偏一欄（實測讓 diff 指標從分得開變成分不開）。
- **ROI 取整段谷底**（~4 px 平底，缺陷可能停在另一端）、**避開 patch
  邊界 ≥4 px**（截斷的 spacer 找谷會挑到 MG 側壁半坡）、**max 前先
  3×3 均值**（匹配濾波）、**diff 只取正向**（Hf 一律亮起；LER 的
  test/ref 不合是雙向的，取正殺掉一半 nuisance）。

產生器自己的坑（都修在檔內並留註解）：梯形覆蓋率的斜坡要**跨在名義
邊緣上**（往帶內吃的寫法 soft 越大線越細 —— 使用者抓到 MG/EPI 都變細）；
spacer 亮度上限要壓在 EPI 下限之下 ≥13 GLV（EPI 抽到暗端的 die 剖面
會整段平掉，找谷變亂挑）。

---

## 第六輪：金色虛線退役、手動佈局不被自動整理（2026-08-14）

- **route 隱含順序的金色虛線整套移除**（使用者：「會混淆」）。F7-10 畫它的
  理由（「沒有線以為互不相干」）由現在的預設行為緩解 —— 從卡片庫加卡與
  拖放都建**顯式**連線。退掉的只有「畫」：引擎依賴（route ∪ edges）與
  排版（分欄）都照舊吃隱含順序。`_EdgeItem` 的 implicit 分支、
  `canvas_edge_implicit` token、相關測試（f7_10 整檔改寫、f7_18 §3）
  一併清掉 —— 死機制不留半套。
- **節點位置保留**（使用者：「不要幫我自動整理」）：`set_nodes` 之前每次
  model 變動都重跑自動排版，拖好的佈局改個參數就沒了。現在既有節點
  保位置、只有新節點拿排版位；彈出視窗開啟時沿用主視窗的位置
  （`copy_positions_from`）；換一份 recipe 才重排（`forget_positions`）。
  「排整齊」仍是明確的整批重排入口。
- **CI 抓到 subtract 預設值改變了舊 recipe 的行為**（dual-route e2e 從
  22/24 掉到 18/24 —— 省略 `b` 的舊檔在新預設下**安靜地跳過 align**）。
  照 `_migrate_also_apply` 的先例加載入遷移：檔案裡沒寫 `b` 的 subtract
  補回舊預設 `ref_aligned`（Studio 存檔一律寫滿參數，省略只會是舊檔）。
  兩份省略的 recipe JSON 也補明確值。**教訓：改預設值 = 改所有省略它的
  檔案的行為，遷移不是可選項。**

驗收：f8_ui_polish +2（位置保留）、test_recipe +1（遷移）、
f7_10/f7_18/f7_19/f7_24 改鎖新行為。

---

## 第五輪：右鍵平移、消失的埠、假的 Align 前置、量測卡的框與勾選（2026-08-14）

使用者實測 D 案版面後的一批回饋（5 項）＋一條假想 flow 的檢視。

- **右鍵拖曳平移畫布**（使用者要求）。右鍵被平移接管後，選單改在
  「原地放開」時開（`show_context_menu` 抽出來共用）；view 的
  `contextMenuEvent` 要吞掉，否則 Linux 在按下的瞬間就彈選單，永遠拖不起來。
- **「有些卡片後方的埠不見了」查出兩個因**：(1) fit 的 0.7 下限讓四欄
  pipeline 塞不進概覽條 —— D 案反轉了前提（主畫布是概覽、細節在設定區與
  彈出視窗），主畫布下限放寬到 0.5、彈出視窗維持 0.7（F7-24 的量測結論
  沒變，變的是誰負責讓人讀）；(2) 卡片拖出 sceneRect 之外那塊**捲不到**
  —— sceneRect 現在跟著拖曳長大（只長不縮，縮回由 set_nodes/tidy 做）。
- **subtract 預設 `b` 從 `ref_aligned` 改 `ref`**（使用者指正：patch 本來
  就對齊，「一定要先 Align」是預設值造出來的假前置）。Align 留給未來
  非 patch 輸入或站點量到殘餘位移時用。連動改了 badge 測試與
  `_unmet_needs` 的例子（改用 snr_map 缺 diff 觸發）。
- **量測卡的 metrics 用勾的不是用打的**：新參數型別 `multi_choice`
  （`MultiChoicePicker`，一列三格的勾選網格）。刻意**不**強制值落在
  choices 裡 —— 手寫 recipe 的 `glv_q37` 照樣合法、照樣列出來勾著。
  目前只有 `glv_stats.metrics` 用它。
- **量測卡也畫框**：`region_overlay()` 除了選著那張卡**定義**的區域
  （F7-11），現在也畫它**引用**的（`resolve_regions_in`）—— 選
  Gray-level stats / Mask from regions 時，預覽直接回答「我在量哪裡」。
  `_center` 只在「定義」那邊跳過；明確引用它的量測卡當然要畫。

驗收集中在 `tests/test_ui_f8_ui_polish.py`（+6 條）。

## D 案：畫布佔中上、設定拿大頭、看全貌用彈出視窗（2026-08-14 第三輪）

**右緣抽屜活了半天就被退掉了** —— 使用者的理由一句話就成立：「n8n 的節點
是向右拉的，右側又出現垂直抽屜，垂直空間反而沒辦法運用。」他拍板的形狀
（他叫它 D 案）：**畫布會 zoom、又有彈出視窗，平面上只需要中上一塊**；
大空間還給設定與影像。左（卡片庫）與右（預覽）不動。

### 改了什麼

- **中欄回到上下切，但比例反過來**：畫布 2 / 設定 3，設定**預設攤開**
  （F7-22 的「雙擊才攤開」退役 —— 雙擊仍可把收起的設定重新攤開）。
  比例在第一次 showEvent 才套（setSizes 要有實際高度，老坑）。
- **畫布 zoom bar 加「彈出視窗」鈕**（新自繪 glyph `popout`）：把 pipeline
  開在自己的視窗全尺寸看。第二個視窗是**另一份 PipelineCanvas 接同一個
  model** —— 訊號走同一批 handler（`_wire_canvas`），所以兩邊拉線、拖卡、
  選取全部互通，不是截圖。彈出視窗裡的那份把彈出鈕關掉（套娃）。
- **彈出時主視窗的設定自動補滿**（使用者追加的：「讓 UI 很 flexible」）：
  畫布已經在別的視窗全尺寸攤開，主視窗那份就把位子讓出來；關窗還原
  **彈出前**的比例（那是使用者自己調的，不是預設值）。
- **`roi_mask` 自動填區域名**（使用者的第二個問題：「不是應該從 Profile
  或 Template 輸出 mask 嗎」）：名字要他重打一次，是這張卡與上游之間
  看得到卻要用手搬的一段。現在加卡時上游定義過的區域名自動填進
  `regions`（只填空的，不蓋使用者打過的字）—— 跟量測卡 `output_prefix`
  的自動填名同一條路。
- 抽屜的程式（`_CanvasColumn`、`paramDrawer` QSS、關閉鈕）全部拆掉。
- （第四輪追加）卡片改名 **Mask from regions**（原「Region → mask」——
  箭頭跟其他卡的命名語言不合），`Size like` 改成 `Same size as`。
  **key `roi_mask` 不動**：那是 recipe JSON 的鍵，改了舊檔就開不起來。

### 驗收

`tests/test_ui_f8_ui_polish.py` 的 3-3 段整段改寫（版面 + 彈出視窗 +
自動填名，9 條）；`test_ui_f7_19_wiring.py` §6 改鎖「預設攤開」。

## 畫布 n8n 化第二批（F8-UI）＋ F8c ROI mask（2026-08-14）

同一天的第二個 session。使用者核准了四項 UI 改善（3-1～3-4），
接著把 F8 §7 排隊中的 (c) 做掉。

### F8-UI：四項（驗收 `tests/test_ui_f8_ui_polish.py`，7 條）

- **3-1 線要像 n8n**：兩件事。前行線的水平推力下限 40 → `COL_GAP*0.67`
  （推力太小時三次貝茲**退化成斜的直線**，縮放 70% 後更明顯）；
  `layout_columns` 同欄列序改 **barycenter**（跟上游的列對齊）——
  大部分的線因此接近水平，交叉不是被畫得更好看，是**根本不發生**。
- **3-2 卡片要回應**：hover 邊框亮一階＋選中加一圈 3px 半透明 accent 光暈。
  踩到一個現成的地雷：卡片 `setAcceptHoverEvents(True)` 會讓 hover 事件
  **不再穿過卡片**，壓在線中點上的卡把「斷開」的 × 悶死
  （`test_ui_canvas_cut_button` 當場紅掉）。改成 **view 層**在
  `mouseMoveEvent` 裡判斷誰在 hover（`_sync_hover_node`），卡片仍然不收
  hover 事件。光暈畫在卡片邊緣之外 → `boundingRect` 跟著加寬（殘影守則）。
- **3-3 設定變成畫布右緣的抽屜（overlay）**：F7-22 的上下切分攤開時把畫布
  砍掉四成高度，而攤開參數正是「一邊調一邊看」的時候。現在畫布**永遠**
  整欄大小，抽屜浮在右緣（寬 320–420px、吃滿高度、有關閉鈕）。
  `middle_splitter` 改名 `canvas_column`（它不再是 splitter，名字不能說謊）。
- **3-4 間距 8px 節奏**：右欄與參數區的 2/4/6px 雜項統一成 8 ——
  「差一點對齊」比沒對齊更亂。

### F8c：`roi_mask` 卡 + Normalize 的 `Use only`

動機（計畫書 §7 原文）：跨 patch 比 EPI 的 GLV 時 **MG 佔多少面積隨 crop
而變**，任何吃整張圖統計的卡都把這個變異灌進 EPI 的數字。

- 新卡 `roi_mask`（`steps/roi_mask.py`，CATEGORY_IMAGE / GROUP_REGION）：
  具名區域 → 0/255 mask 影像流，多名字 = 聯集。`regions` 留空是
  `not-configured`（F7-13 那條路），指到沒人定義的名字走 `unknown-region`。
- Normalize 加 `use_within`（label **Use only**，percentile / glv_band 才
  出現）：範圍只從 mask 內的像素量，**套用仍是整張圖**。mask 尺寸不合 →
  StepError 指名去改 `Size like`；全 0 mask → 退回整張圖 + `ctx.warn`。
- **界線**：mask 給影像段用；量測卡照樣引用 ROI 名字（兩條平行的路會腐爛，
  F7-17 的教訓）。

驗收（`tests/test_roi_mask.py`，10 條）照計畫書原話量，實驗設計時學到的
一課記在計畫書 §7：整張圖 percentile 最痛的不是 MG 面積 12% ↔ 24% 的變動
（p98 兩邊都落在 MG 上，反而穩），是面積**跨過百分位門檻**的那一下 ——
「一根 MG 進出畫面」，p98 從 EPI 的頂翻成 MG 的 230。只用 EPI 之後
分散度收斂到一半以下（實測 ~1/20）。

### 順帶

早上的 tooltip 化（見下一段）在這輪繼續：卡片層級說明也收成一行。
測試在雲端容器跑全套要 20 分鐘以上（家用機 ~30s）——
CLAUDE.md §6 已加「開發迴圈只跑改到的測試檔」。

## 參數說明搬進 tooltip —— 列面上只留「非讀不可」的字（2026-08-14）

使用者的原話：「描述功能的文字太多，而且移過去會顯示、移走又消失，如果我是
user 我會覺得很亂 —— 建議把這些描述文字拿掉，讓下方精簡一點。」

這推翻的是 F7-15 的「一行、hover 攤開」。那一輪修掉了 Enter/Leave 打架的閃爍
（CLAUDE.md §7），但修好之後它**還是**跟著滑鼠此起彼落 —— 滑鼠掃過整張表，
每一列輪流長高又縮回去。技術上沒有 bug，體感上就是亂。F7-15 當時拒絕
tooltip 的理由（「使用者要隨手看得到」）讓位給使用者自己的判斷。

### 改了什麼（全部在 `ui/widgets.py`，引擎零改動）

- **`_ParamRow`**：常駐/hover 攤開的說明整個拿掉（`WA_Hover`、eventFilter、
  enter/leaveEvent、`set_active` 一併刪除）。說明全文設成**整列**的 tooltip
  （名稱、空白處、editor 都感應）。列面上只剩兩種會出現的字，出現就整段攤開：
  - 紅色錯誤（`show_error`）—— 驗證擋下來的原因，非讀不可；
  - 「這一格現在不生效」的調淡註記（`set_dimmed`，例：畫了曲線之後的 gamma）。
  新增 `hint_visible()` 供測試問明確狀態。
- **卡片層級的說明**（ParamForm 頂端那一段）同一個決定：收成一行
  （`_HintLabel` 的 elide，不讓 Qt 硬切字中間）、全文住 tooltip。
- 錯誤與註記的優先序：錯誤 > 註記 > 什麼都不畫（`_dim_note` 追明確狀態）。

### 驗收

`tests/test_ui_f7_15_reading_load.py` 第 1 節改鎖新行為（hint 預設隱藏、
tooltip 有全文、錯誤出現整段且清掉就收乾淨、列高一行）。其餘 API
（`hint_text()`、`show_error()`）不變，`test_ui_widgets.py` 原樣通過。

之後要 release 的話，說明的出口是 SOP／圖解文件，不是畫面 —— 使用者已經
講了方向。tooltip 是過渡期的保底。

## F8：純規則的 ROI 定位 —— 兩組條紋的交會處（2026-08-13）

使用者試用 `Locate region by profile` 之後說「我沒辦法做 ROI 定位」。他有兩招，
兩招都要外部的東西（GDS 要 .oas、Golden Cell 要一張原大圖），而他要的是第三招：
**只看 patch 自己、純規則、訂得出 BOX**。「我本來預期投影要可以的，
但我不知道怎麼跟你描述比較適合。」

### 他的直覺是對的，缺的是最後一步

`roi_profile` 依設計只吐**一條滿版的條紋** —— 程式裡的註解寫得很明白：
「投影只知道沿著這條軸的哪一段，對另一個方向一無所知，硬給一個高度等於憑空
捏造資訊。」那個拒絕對**一次**投影是對的，它擋掉的是**再投影一次就量得到**。

而他要框的是「MG（直的）與 EPI（橫的）的交界，在 EPI 上」，一張 patch 有好幾根
MG 乘好幾根 EPI —— 所以要的不是「X ∩ Y 交出一個框」，是「**X 的每一段 × Y 的
每一段 = 一個網格**，然後挑格子」。

### 刻意不走週期估測

`region.py` 早就指名 pattern-frame 該用 `estimate_period` / `choose_origin`。
這一輪不走，因為他的 patch 是 64–128px：週期估測要 2–3 個完整週期才可靠
（信心門檻 40，雜訊 20.3），pitch 20–30px 時只有 2–4 個週期，**正是最不可靠的
區間**。而投影根本不用估 —— 它直接量到每一根線在哪。他自己還指出這條路
「可能會跟 template 重疊」，也對：GC 的本質就是拿一個 cell 對回相位。

### 他知道 pitch（GDS 給的）——這比想像中值錢

不是用來估週期，是三件事：**驗證**（量到的間距對不對）、**補線**（邊緣只露一半
而漏掉的那幾根）、以及把錨定條件從「要好幾個週期」降成「**要一根條紋**」。
⚠ pitch 一律吃 **px**：GDS 給的是 nm，而 `nm_per_px` 沒有來源（§8），
收 nm 的話它會變成第二個恆為 0 的 `cd_x_nm`。

### 兩個坑

**晶格要排在條紋的中心上，不是排在邊界上。** 一根寬 8、週期 24 的條紋，
**邊界**間距是 8、16、8、16… 交錯的，只有**中心**才是每 24 一次。第一版拿邊界去
對等距晶格，把一根條紋的兩條邊併成一格 —— 條紋寬度整個消失、框落到隨機的地方，
而 `ok=True`、數量合理、位置整齊。是量了每個框的平均灰階才發現一半的框量的是
MG 不是 EPI。

**框要離邊界一點（新參數 `gap`）。** 轉折是在平滑過的曲線上用中央差分找的，
位置會早一格；邊界本身在 SEM 上也糊在好幾個像素上。實測 `gap=0` 時 5px 的框吃
進一欄別種材質，平均 170 → 157.5、框間標準差 12.5；`gap=1` 是 170.0 與 0.3。
**一成多的偏差，而且仍然是個看起來很正常的數字。**

### 做了什麼

`algo/grid.py`（兩軸條紋 → 交叉 → 五種放法）、`steps/roi_cross.py`、
**多框區域**（`Context.set_roi_boxes`；`glv_stats` 改讀 `roi_pixels` 把 N 個框
當一個像素母體，要幾何的卡遇到多框**拋錯並指路**去用 `<name>_center`）、
`CrossInspector`（兩個方向各一條曲線 —— 失敗有兩種，處置完全不同）、
`region_check` 畫**每一個**框（只畫第一個的話畫面會說謊）、
`make_sample.py --pattern lines`（兩軸不同週期的線陣列）、
`examples/recipes/cross_regions.json`。

### 第二輪（同日試用回饋）

**框即時疊在預覽影像上**（`ImageView.set_overlay`）—— 原話「不然都一定按 Check
this region across defects… 跑完才能看，不能實時調整」。只畫**選著那張卡**的
區域（一份 recipe 常有好幾張 Region 卡），離中心最近的那個畫成醒目色（缺陷永遠
在那裡，而一堆一模一樣的框裡看不出哪個是「這一顆」的）。

**三層以上的灰階**：站點的 MG 約 220 最亮、EPI 約 180 次之，而中位數二分法會把
兩者併成同一組。改成**排名**（`brightest` / `second_brightest` / …），分幾群由
排名決定 —— 使用者只要回答「第幾亮」，不必再猜「這張圖有幾種材質」。分群切在
排序後最大的間隙上（自然斷點），不用 k-means：不需要種子，同一張圖每次答案相同
（批次快取的前提）。⚠ **每個方向各自判斷** —— MG 直、EPI 橫，所以兩邊都填
`brightest`；排名是給「同一個方向有三層」用的。舊值由
`recipe._migrate_renamed_values` 換名（相容性是檔案格式的事，不是把兩個意思一樣
的選項留在下拉裡）。

**交錯的 pitch**（`*_pitch_2`）：站點的 EPI 間距有兩種。晶格從錨點往兩邊走、
間距依序取那兩個值；錨點落在哪一相看不出來，所以**每一相都排一次留誤差最小的**。

### 第三輪：框真的左右歪，而且是邊界偵測歪的

使用者說「Box 好像左右會歪歪的」，猜是「致中的 box 在搞鬼」。**不是** ——
`_center` 只是在既有的框裡挑一個，不會移動任何框。真正的原因量出來是：

`|梯度|` 的峰**通常是 2 格寬的平台**（實測 `grad[20] == grad[21]` 位元相同），
而 `find_transitions` 挑局部極大的條件左右不對稱（`> 左鄰` 但 `>= 右鄰`），
於是同一根條紋的兩條邊各挑到平台的不同側 —— **每一根都是左偏 −1、右偏 0**。
段往左胖一格，貼在兩側的框就一邊有縫一邊沒縫。兩個框量的是同一種材質，
**數字上完全看不出來**。

`refine_edges()` 用拋物線內插把峰放回 20.5。連帶兩個坑：Python 的 `round()`
是 banker's rounding（`.5` 有時進有時不進，而精修後每條邊都正好落在 `.5`）；
以及**那個 `.5` 算出來其實是 `20.499997`**，差在最後幾個 bit 卻決定捨上捨下，
而左右兩條邊剛好落在不同邊 —— 加 1e-6 容差還原。邊緣被切窄的框改成丟掉。

**UI 亂**：19 個參數攤平，「有些我不知道是什麼功能」。新增
`ParamSpec.section` —— 同組畫在一起加小標題，順序即操作順序。`show_when` 解
「這列現在算不算數」，`section` 解「這列在回答哪個問題」，兩者不能互相取代。
`smooth` 從「橫的條紋」搬到第一組（它兩個方向共用）。

**那條灰虛線**：是參考線（patch 正中心 = 缺陷位置），不可操作 —— 現在旁邊標
`defect`，tooltip 講明它不是控制項。

### 第四輪：pitch 除不盡、以及線寬（兩個提問各查出一件事）

**「1.5 nm/px 配 44 nm 的 pitch，除不盡怎麼辦？」** 44/1.5 = 29.333 px。答案是
照著填分數（欄位收三位小數），不要自己捨。為了讓這件事真的成立改了兩處：
`_fill_by_pitch` **不再把補出來的段捨成整數格**（晶格是浮點累加的，一算完就捨
等於每根各被推掉最多半格）；**相位改用整排一起定**（所有量到的中心對晶格的偏移
取中位數，被邊界切到的不參加）。實測最大偏差 0.83 → **0.50 px 且不漂移**；
自己捨成 29 的話逐根 0.25/0.08/0.42/0.75/**1.08** —— 越遠越差，而 patch 中央
（缺陷所在）看起來還好好的。

**「MG 自己的寬有假設進去嗎？」** 有，而且是量的 —— 線寬沒有參數，8/12/18 px
都量到 ±1 px 內。**但這一問查出一個真的 bug**：舊版填了 pitch 之後把整排寬度
統一成中位數（真實 [15.3, 7.9, 12.7, 11.1, …] → 全部 11.5）。pitch 講的是
「每隔多遠有一根」，**對線寬一個字都沒說**。抹平不只丟掉 line-width roughness
（那有時就是缺陷），還因為框貼著段的邊界放 —— 線寬異常的那一根，框會被推進 MG
裡好幾個像素，**最需要量準的那一根量得最髒**。改成每根用自己量到的寬度，
只有靠 pitch 補出來的那幾根才借中位數。

### 第七輪：一鍵校正（2026-08-14）

「我可能有 50 張 100 張 patch，直接用這些 calculate 找出最好的設定？Use 彼此
之間還是有 variation。」對 —— pitch 是**設計常數**，每張量的是同一個數字，
單張的 ±0.5 px 雜訊聚合就除掉。`calibrate_axis`（`algo/grid.py`）聚合的是
**原始間距**不是每張的結論：第一版聚合結論，交錯 40/33 的批安靜地錯成 36.5
（單張大多只看得到三根線，而 50 張完全同意那個不存在的平均值）。分群判讀六個
情境全實測：單一 pitch ✓、交錯 ✓（比值非整數＋同張交替）、缺線摺回 ✓（整數倍
＋高群零星）、挑錯組拒填 ✓（整數倍＋兩群一樣多 —— 純度判別被資料打臉，
mixing 0.36，改用豐度）、純雜訊拒 ✓（信心閘門）、混批 ✓。批次不同意就**拒填
並講出兩群**，不硬給中位數。UI：`CrossInspector` 頂上一顆
`Measure pitch & width from this lot`，`CalibrateWorker` 背景跑
`collect_source_images`（跟區域檢視同一條路，量卡片實際看的那條流），填回走
`set_param`（可復原）。順帶修掉「Use」按鈕被 `shape="square"` 的
`max-width: 22px` 切到只剩一半數字。驗收 `test_roi_cross_calibrate.py`（9）+
`test_ui_f8_calibrate.py`（7）。

### 第五輪：量測尺、CPODE、給定線寬（2026-08-14）

**量測尺。** pitch 欄位可以留白，但條紋一髒，那張卡就會要求使用者填一個他不知道
的數字 —— 而畫面上唯一握有這個資訊的東西正是那條曲線。`ProfilePanel` 按住拖曳
量測、放開就結束；讀數除了距離，只要這一段裡有兩根以上的條紋（用**中心**判定，
邊界有升有降會多算一倍）就順便算 pitch —— 量一個週期是所有量法裡最不準的一種，
兩端各差一個像素 pitch 就差兩個，橫跨好幾根再除以根數，誤差被根數除掉。
綠色是刻意跟曲線（墨色）與轉折線（accent）**換一個色相**的：同一家挑色階的話，
「哪一條是我剛剛拉的」就只剩深淺可分。上面那張影像同步標同一段
（`ImageView.set_measure`）—— 曲線上的一段只是「第 40 到第 74 個取樣點」，
而「我量到的是不是兩根 MG 的距離」只有看影像答得出來。

**CPODE：同一個晶格上第三種材質。** 使用者說某側會出現 CPODE（很暗、寬度跟 MG
一樣、**pitch 跟 MG 共用**，一張 patch 可能是 MG-MG-CPODE）。照舊版跑：
`brightest` 抓到 **9** 根、量到的 pitch 是 **12**（實際 24 的一半）—— 三個台階
（MG 216／空隙 133／CPODE 41）分兩群時，最大的間隙落在 CPODE 與空隙之間，
於是「最亮的那群」= MG **加上空隙**。再填 `pitch=24` 更糟：晶格排出一組間距完全
正確的解，但它鎖在**空隙**上，而 `pitch_error` 是 **0.00** —— 安靜的錯答案。
`select_bands` 因此多一個 `kinds`（**這個方向上有幾種條紋**，不是「分幾群」——
使用者答得出前者）。`kinds=3` + `pitch=24` → 6 格，其中兩格是 CPODE，靠共用的
pitch 補回來（`filled`），框在兩種格上離線的距離完全相同。

**給定線寬。** 第四輪的「量的不是假設的」仍然成立（線寬本身可能就是要量的東西），
但它漏了另一半：使用者從 GDS 就知道線寬，他要的不是量它是拿它**當尺**。
新參數 `vertical_width` / `horizontal_width`（0 = 照量到的）真正買到的是**把一個
問題拆成兩個**：線寬固定之後，這條曲線只剩「每一根線的**中心**在哪」要做對，
而中心是整段的重心，比單邊的邊界穩得多。也就是說 sensitivity 從「決定框放在哪」
降級成「決定有沒有找到這根線」—— 而後者面板上看得出來，前者看不出來。
給的是寬度不是位置（中心仍然來自影像）；邊上只露半根的線是**切掉**不是推回去。
合起來正好是使用者描述的流程：profile 定 MG 中心 → 給定 MG 寬度 → 從 MG 邊界
往外長 ROI。

驗收 `tests/test_roi_cross.py`（29）+ `tests/test_roi_cross_lattice.py`（14）
+ `tests/test_ui_f8_cross.py`（14）+ `tests/test_ui_f8_ruler.py`（17）。
計畫書 `docs/plans/F8-rule-based-roi.md`。

---

## 畫布上斷開連線的 × 按不動（2026-08-13）

使用者回報：

> 「我在 n8n like 的 UI 節點做操作時，發現按下字卡間的線的 X 時，
>   **時常會沒有反應**。」

「時常」是客氣了 —— 實測一條手接的四張卡 pipeline，**四條實線的 × 全部是死的**。

### 為什麼看得到卻按不到

`_NodeItem.boundingRect()` 為了讓埠標籤（`test`/`ref`，畫在卡片右緣**之外**）
重繪得到而加寬了 56px —— 那是 §7 那條踩過三次的老規矩，本身沒錯。錯的是
**`QGraphicsItem` 預設的 `shape()` 就是 `boundingRect()`**，於是那 56px 空白
同時變成卡片的滑鼠命中區，而它看起來完全是畫布。

那塊空白正是連線的家：兩欄相距 `COL_GAP`（96px），相鄰欄那條貝茲曲線的中點落在
`(a.x + b.x) / 2`，也就是上游卡右緣 +48px —— 還在 56px 裡面。實測
`load_patch → denoise` 的 × 在 (238, 23.3)，卡片的命中區到 x=246。

**hover 會穿過**不收 hover 事件的圖元（卡片不收），所以 × 照樣畫得出來、
使用者看得到；**按下不會穿過**，z 值大的卡片（0）贏過連線（−1），那一下變成
`node_selected`，選取了上游那張卡。看得到、按得到、然後什麼都沒發生 ——
而畫面上真的有東西動了，只是動的不是使用者盯著的那條線。

第二個獨立的原因：**畫出來的 × 比線的命中區大**。`_EdgeItem.shape()` 只把線
加粗到兩側各 5px，而 × 半徑 8、`cut_hit` 收到 10。圓周那一圈（超過圓面積的
四分之一）落在 shape 外面，而且滑鼠一走進去 hover 就結束、× 當場消失 ——
使用者的描述會是「這顆鈕會躲」。

### 改法

* **`_NodeItem.shape()`**：命中區收成「卡片本體 + 兩側埠的抓取半徑」，不含標籤。
  `boundingRect` **維持原樣**（殘影那條不能破）。新常數 `_PORT_GRAB` 讓
  `shape()` 與 `out_port_at()` 讀同一個數字。
* **`_EdgeItem.shape()`**：把 × 那顆圓 union 進去，半徑用與 `cut_hit`
  **同一個** `CUT_GRAB` —— 兩份定義遲早會分岔，而分岔的症狀正是「時好時壞」。
* **hover 中的那條線抬到卡片之上**（離開放回去，`_Z_EDGE_HOVER`）。節點是拖得
  動的，「中點會不會被某張卡蓋到」不是設計時算得完的事。

### 為什麼既有測試是綠的

F7-22 的 `test_a_line_can_be_cut_where_it_is` 問的是**幾何**：×的圓心在不在
`boundingRect` 裡、`cut_hit(圓心)` 是不是 True。那兩件事從頭到尾都成立。
沒被問到的是**那一下滑鼠到底送給了誰** —— 那是事件派送的問題，量座標量不出來。

所以 `tests/test_ui_canvas_cut_button.py`（8 條）每一條都真的派送一顆滑鼠事件
（移動 → 按下 → 放開，移動那顆不能省，× 只在 hover 時存在），問的是
「使用者做了這個動作，recipe 有沒有改變」。對改之前 **7 條紅**。
含兩條反向的回歸鎖：埠仍然抓得到、`boundingRect` 仍然比命中區大。

**新的不變量：畫得到的範圍與點得到的範圍是兩件事，而且兩邊都要鎖。**
以前只鎖了前者（因為殘影看得見），後者壞掉是安靜的。

## F7-24：版面把空間給對的東西（2026-08-08）

使用者貼了一張跑起來的截圖。四件事都不會讓任何測試變紅 —— 它們是「畫面把空間
與注意力分配錯了」，只有看畫面才看得出來。

### 開一份 recipe 就把它擺好

卡片擠在畫布左下角、上面一大片空白。`fit()` F7-14 就有了，只是**沒有人在載入
之後呼叫它**，於是使用者每次開檔的第一個動作都是自己去按那顆鈕。

放在 `_apply_model`（整份 pipeline 換掉的唯一入口），不放在 `_refresh_all` ——
加一張卡就重新縮放一次，等於每動一下畫面就跳一次。

兩個當場撞到的陷阱：**`fitInView` 要有尺寸才算得準**（viewport 在 `show()` 之前
是預設值，那時候算的倍率會留在畫面上 → 改成 `fit_later()`，下一次
`showEvent`/`resizeEvent` 才消費）；**`fit` 只能縮不能放**（`fitInView` 會把兩張
卡的 pipeline 撐滿成三倍 → 加上限 1.0）。

### 空間給有資訊的那一邊

兩個下拉框都吃 `stretch 1`，於是在寬螢幕上各自變成八百多 px、裡面只寫著「1」
與「diff」的框，而 `ebi_patch · defect 1 / 24` 被擠到最右邊還被切掉。

### 刪掉 `PipelinePanel`

F7-6 的畫布取代了它，之後 `studio.py` 只剩一行 import、從來沒有實例化過。
留著的代價不是那 240 行，是**每一輪主題工作都要繞過它** —— F7-23 第三輪把
元件的 stylesheet 搬進 QSS 時，`nodeCard` / `scoreCard` 被判成「顏色依 category
算出來、該留在 widget」而放過。那個判斷本身沒錯，**錯的是它們根本不在畫面上**。
連同它的兩支測試一起刪（畫布那邊由 `test_ui_canvas.py` 蓋著）。

### 「配色有點單調」

使用者對工具列的評語。查下來**單調的來源不是缺顏色，是缺層次與缺辨識度**：
亮色的 `toolbar` 與 `bg_surface` **都是 `#ffffff`**，那一排按鈕只靠一條 1px 的
淺灰邊框跟背景分開；而五顆文字鈕同寬同灰，只有字不一樣。

所以三件事，沒有一件是「替按鈕各上一個顏色」—— 這個主題的規則是**顏色只表達
語意**，為了熱鬧上色會把那條規則作廢：

1. 亮色 `toolbar` 改成 `bg_elevated`，白按鈕浮在條上（暗色本來就沒這問題）
2. 五顆文字鈕各配一個自繪圖示（`folder`/`document`/`save`/`templates`/`export`）
3. `Export…` 拿 accent **外框**（填滿的是 `Run trial`）—— 整條工具列只有兩顆
   有顏色，而它們正好是使用者真正要按的那兩顆

`save` 與 `export` 刻意畫成一對（箭頭進托盤 vs 出托盤）。`templates` 第一版是
「外框 + 三條橫線」，15px 下三條線的間距比線還細、糊成實心格子，而且跟
`document` 太像 —— 改成一疊卡。**又一次驗證 F7-23 第四輪那條：小圖示要用實際
尺寸看過。**

### 驗收與還沒做

`tests/test_ui_f7_24_layout.py`（8 條），對改之前 7 條紅。量的是版面數字與
token 關係，不是斷言某一行 QSS。

### 同一輪接著做完的兩件

**`Spread` 面板補上軸與圖例。** 三排長條、右邊一個數字、中間一條紅線，而畫面上
沒有一個地方說得出橫軸從哪到哪、紅線是什麼、右邊那數字又是誰的。刻度要畫在
**每一排自己身上** —— `glv_mean` 與 `area_px` 不是同一把尺，不能像 Enhance 的
直方圖那樣共用一句「0 → 255」。圖例畫一次，並明講右邊那欄是**這一顆的值**
（不是整批最大值 —— 第一個會猜錯的就是它）。面板拖矮時兩者都讓位。

**往回走的線不再橫掃畫布。** 埠是固定的（出右進左），所以換行那條線本來就得
往回走；但它跟往前走的線共用同一條式子，控制點水平推 `|Δx| * 0.5` —— 往回走時
Δx 是一整列的寬度，於是一條連兩張卡的線甩了七百多 px，還跑到比第一張卡更左邊。
改成水平只推固定的 46px，量交給垂直方向，線收在兩列之間的帶子裡。

#### 又踩了一次同型的坑

`Spread` 那條測試第一版是「數 `text_hint` 顏色的畫素夠不夠多」，**對著改之前的
程式也通過** —— 抗鋸齒的字邊本來就會經過那個顏色附近。改成把那段程式關掉
（`AXIS_MIN_ROW_H` / `LEGEND_H` 調到不可能達到）再比兩張圖。

這已經是這個系列第三次了（F7-23 第一輪的 disabled 取樣點、第三輪的 pill 輪廓）。
共同點都是**驗收測試一定要對著舊版跑一次** —— 不然不知道它在測什麼。

### 第二輪：對著自己截的圖再看一次

把成果跑起來截圖，看到三件事，**前兩件是第一輪的副作用**。

**自動 fit 縮到讀不出字。** 十張卡的 pipeline 落在 52%，卡片副標
（`norm_ref · ref test → ref`）是一團灰。把同一張圖畫在 52/60/70/80/100%
逐級看過：標題到 60% 還在，副標要到 **70%** 才回來。`MIN_FIT_SCALE` 從憑感覺
的 0.45 改成量出來的 0.7。

**塞不下時靠開頭對齊。** 改完上面那條再截一次：內容比畫面寬了，而
`fitInView` 是置中的 —— 兩端各切一半，**第一張卡跟最後一張同時看不見**。
pipeline 從左往右讀，看不完時該看到的是開頭。加 `_anchor_start`。

> 這條是上一條造出來的。**一輪改動要再截一次圖**，不然修好的那件事會在旁邊
> 長出新的一件。

**`Run trial` 與 `▾` 包成分段控制項**（1px 縫 + 面對面那兩個角拉直）。
它們以前吃工具列的全域 6px 間距，讀起來像兩顆不相干的按鈕，而箭頭是
`Run trial` 的另一種跑法。這跟 F7-23 拆掉 `MenuButtonPopup` 不衝突 ——
剛好相反：那一輪要的是「這半邊的外觀歸我們管」，現在兩個半邊都是真的按鈕，
所以圓角/padding/focus 都設得動。

原本那條「內容有沒有擺在畫面中央」的測試改寫成「**pipeline 的開頭在不在畫面
上**」。斷言換了是因為正確的行為換了，不是為了讓測試變綠。

---

## F7-23 第一輪：按鈕的狀態（2026-08-07）

使用者：「我想針對 UI 按鈕做美觀，請提出你覺得現有不足處與修正建議」。
盤點完分四輪，這次做第一輪 —— **只動 `theme.py`，呼叫端一行都沒改**。

### 三件事裡有兩件是「規則寫了但沒有生效」

**焦點框。** QSS 裡有 `QPushButton:focus`，所以看程式碼會以為這件事做完了。
實際上它只對「沒有 objectName 也沒有 variant」的按鈕生效 —— `#primary` 是 id
選擇器贏過它，`[variant="…"]` 同分但寫在後面也贏，而工具列從頭到尾沒有
`QToolButton:focus`。所以 Run trial、Stop、Try it with sample data、
整條工具列，按 Tab 過去**畫面上零回饋**。

第一個想法是用 `outline` 畫在外面（不吃版面）。**量下來 Qt 什麼都不畫** ——
屬性收下了，Fusion 底下的按鈕就是不畫，加不加 `outline-offset` 都一樣。
所以框只能是 border、畫在裡面，那就會吃掉 1px，必須從自己的 padding 還回去。
`contentsRect()` 前後相同是驗收 —— Tab 過去文字跳一格比沒有框更糟。

**`QToolBar::separator` 寫了兩次**，值不同，而**帶著註解的是死的那一份**。

這兩條的共同點：斷言「QSS 裡有沒有寫那一行」完全問錯問題，所以測試一律量
畫出來的畫素（跟 `test_ui_controls_readable.py` 同一種測法）。

### disabled 的 primary 以前跟一般鈕同一片灰

`#primary:disabled` 與 `:disabled` 是逐項相同的宣告。於是**還沒載資料時整條
工具列是同一片灰**，而那正是使用者最需要「我該按哪一顆」的時刻。現在留著
accent 的淡底、文字仍是 disabled 的灰。

### `Run trial ▾` 的下拉區：量出來 QSS 做不到

想補一塊底色把「點主體 vs 點箭頭」分開。逐項量的結果是：只要給
`::menu-button` 一個盒子（背景、邊框、圓角**任一**），Qt 就把繪製交給
stylesheet，而 stylesheet 沒有 `image` 就不畫箭頭 —— 這個 repo 塞不了圖檔。
**只有 `width` 是安全的。**

這正是 F7-13 在 `QComboBox::drop-down` 上學到的同一件事，這次量到
`::menu-button` 上。結論是它不是 QSS 的問題是結構的問題，第二輪拆成兩顆
真的按鈕。表格在計畫書 §27.5，坑表也補了一列。

### 自己踩了一次「量到的不是自己以為的那一格」

disabled 那條測試原本兩顆鈕放不同的字、取樣點取正中央 —— 一顆落在筆畫上、
一顆落在空白處，顏色本來就不同，於是**對著改之前的 theme 也「通過」**。
改成同一個字、取邊框內側文字以上的那條橫帶取眾數。

驗收測試一定要對著**舊版**跑一次，否則不知道它在測什麼。現在 8 條裡 7 條
對舊版是紅的（剩下那條「文字不准移動」在沒有框的舊版本來就成立，
它是伴隨的不變量不是主張）。

### 第二輪（同一個 session）：尺寸與游標不該是每個人自己記得的事

**六種尺寸收成一種。** 節點卡的 ↑↓✕ 22×22、畫布縮放列 24×22（`1:1` 30×22）、
◀▶ 寬 28、`Add` 寬 40、Card/Features 高 20 —— 同一種視覺語言，沒有兩顆一樣大。
現在呼叫端只說形狀（`small_button(shape="square"/"wide")`），邊長由 QSS 的
`control_sm` 決定。**`#cardButton` 要刻意不再宣告 padding 與高度** ——
id 選擇器贏過 `[shape]`，留著的話 shape 會安靜地不生效（第一輪那條特異性
教訓的第二次應用）。

**游標。** 一半的按鈕滑過去沒有變手指，因為那是每個呼叫端自己記得的事。
改成規則：`apply_button_cursors(root)` 在視窗建好之後掃一次；參數列是選到卡片
才長出來的，所以 `ParamForm.set_step` 每次重建之後再掃一次。

**`Run trial ▾` 拆成兩顆真按鈕。** 箭頭那顆**不設 menu** —— 設了 Qt 會自己再
加一個下拉指示器，等於兩個箭頭。

順手記一條 Qt 的事：QSS 的 `min-height`/`max-height` 管的是**內容框**，
`control_sm` 24px 出來的 `sizeHint()` 是 26px。所以測試問「六種高度收成一種
了沒有」，不去驗「等於 24」—— 把盒模型算式抄進測試只是把同一份知識放兩個地方。

第二輪多五條驗收，其中一條是靜態掃描：`adept/ui` 裡不准再有 `setFixedSize` /
`setFixedWidth` / `setFixedHeight` 出現在按鈕上。尺寸寫死在呼叫端就會慢慢長
回六種。

### 第三輪（同一個 session）：外觀回到 QSS

`_Chip`、`StageButton`、`LibraryItem`（含 badge）以前各自在建構式裡用 `TOKENS`
拼一段 stylesheet 字串。那讓 theme.py 那句「顏色永遠不會兩邊走鐘」**對使用者
看最久的那幾個元件是假的** —— 它只在有人記得換膚時逐顆重套的前提下成立。
而其中一條真的沒被呼叫：卡片庫裡帶「needs diff」badge 的列會留在上一個主題的
灰色。

搬過去的關鍵是 **repolish**：`setProperty` 只是存值，`[active="true"]` 要等
下一次 polish 才生效，少這一步是「狀態改了、畫面沒動」而且不報錯。
新增 `widgets.restyle()`。

順帶三件小的：`pressed` 從「hover 再深一階」（ΔL*≈3.5，等於沒有回饋）改成真的
跳一階（新 token `pressed_bg`）；`#cardButton:hover` 從動三件事收成兩件
（最小的按鈕不該有最大的反應）；`QPushButton` 補上 `:checked`。

#### 差點做出一個叫 pill 的方角

第一輪加 `radius_pill` 時填的是 CSS 慣用的 `999px`。**Qt 不夾範圍** ——
超出去就直接放棄圓角畫矩形，不報錯。量出來 999px 的左緣輪廓與 0px 逐列相同。
改成真的半高 11px。這個 token 到第三輪才第一次進 QSS，所以還沒有人看到過它
畫錯，但那正是這種 bug 的樣子：名字說得斬釘截鐵，畫面沒有任何地方對得起來。

量這條時踩到兩個會讓測試「永遠是綠的」的陷阱（都寫進測試註解）：要畫 host 不能
單獨畫 chip（Qt 先用 widget 自己的底填滿整個矩形再畫圓角框）；host 的底要用 id
選擇器（主 QSS 的 `QMainWindow, QWidget, QDialog` 會贏過型別選擇器）。

#### 看過但沒動

gallery chip 的 `✕`：整顆一起 hover 換底已經把它綁成一個單位，而三個修法都比
現狀差（拆兩顆命中區太擠、拿掉就沒有東西說得出「可移除」、QPushButton 吃不了
rich text）。理由記在計畫書 §27.7，免得下一輪再盤點一次。

#### 一次自己造成的意外

跑「拿掉 restyle 看測試會不會紅」的驗證之後，用 `git checkout -- widgets.py`
還原 —— 那把**整個第三輪還沒 commit 的 widgets.py 改動一起丟了**（那支檔案的
第二輪部分已經 commit，所以 checkout 回到的是第二輪）。重做了一次。
要驗「拿掉某一行測試會不會紅」，改動要走臨時複本或 stash，不要用 checkout。

### 第四輪（同一個 session）：圖示用畫的

按鈕上原本是 `↶ ↷ ◐ ◀ ▶ ⤢ ⌗ ↑ ↓ ✕ ▾`。問題不是它們醜，是**廠內是 Windows，
而 Segoe UI 蓋不到其中好幾個** —— 退到 Segoe UI Symbol 之後同一排按鈕每顆字的
大小與 baseline 都不一樣，最壞是豆腐框。**而開發機看不到那件事。**

新增 `widgets.draw_glyph_icon()`（14 個）與 `IconButton`，走 `draw_group_icon`
同一條路。圖示顏色取 `palette()` 的 `ButtonText`（Qt 從 QSS 的 `color` 解析
出來的），所以換膚與變灰**不必通知任何人** —— 第三輪那條教訓的延續。
主題鈕的實心半邊現在跟著目前主題翻面（以前兩個主題長得一模一樣）。

**刻意不是「所有非 ASCII 都改」**：`−`(U+2212) 與 `←↑→↓` 是 Segoe UI 的基本
覆蓋，`×`(U+00D7) 是 Latin-1 —— 留成文字是安全的。所以 Gallery 排序鈕的
`↓ High to low` 原樣保留，chip 上的 `✕`(U+2715, Dingbats) 只換成 `×`(U+00D7)。
`1:1` 也留成文字。把安全的一起畫掉只是多改動、不換到東西。

#### 小圖示不能照大圖示的比例縮（畫出來才知道）

在 22px 下看起來都好，放到按鈕上的 15px 全糊掉，三個都得重畫：`undo` 的弧用
`size/9` 的線變成一個實心月牙（改 `size/11` + U 形迴轉 + 尾巴）；`fit` 的四個角
括號用 0.26 長度兩臂幾乎接起來變成矩形（改 0.17）；`tidy` 的 2×2 描邊方格線比
空隙還粗（改實心）。**加新圖示要用實際尺寸看過** —— 測試只擋得住「畫出來是
空的」，擋不住「畫出來是一團」。用終端機把 pixmap 印成 ASCII 就夠了。

順帶量到：QSS 樣式下 `contentsRect()` 的**尺寸**扣掉了 padding，但**原點仍是
(0,0)**。所以拿它比對「文字區有沒有移動」是對的（第一輪那條），但拿它定位
「畫在 padding 裡的圖示」是錯的 —— 要用 `rect()`。

### F7-23 收工

四輪，`tests/test_ui_f7_23_buttons.py` 共 25 條。每一輪都對著改之前的程式跑過
一次，確認它們真的在測東西。

---
