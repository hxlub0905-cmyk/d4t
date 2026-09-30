# F124 — 畫布是一條從頭接到尾的資料流

狀態：**做完（2026-09-30）—— 期 1～4 都做完；搬進 `docs/history/plans/` 之前等使用者用過。**
前一份：[`F123`](../history/plans/F123-decision-and-output-cards.md)（Decision 與 Output
變成真的卡）。這一份修 F123 期 2 的規則，F123 其餘三期照留。

---

## 1. 使用者定調（2026-09-29）

一路問下來的五句話，每一句都推翻了前一版的一部分：

| 使用者 | 推掉了什麼 |
|---|---|
| 「我現在又覺得有數字線很奇怪」 | F123 期 2 的原樣 |
| 「也許不要分什麼線，USER 就統一拉線即可 … user 不能有太多的學習成本」 | 線分四種、要瞄準那一顆埠 |
| 「畫布描述的是資料流（資料怎麼走、做到哪步會變成怎樣），有 input 就要有 output；之前的版本（Output 沒有線）對 user 來說會非常突兀」 | 「數字和結果都不拉線」 |
| 「還是很怪，這樣為何要有數字線？Feature 就可以處理了，而且可用的參數更多（可以在 ADC card 當作 attribute）」 | 「線決定判定問得到哪些數字」 |
| 「Decision 前面沒接線也很怪 … 希望 user 看得懂、講得出來畫布在幹嘛，不然中間突然斷掉會很奇怪」 | 「Decision 不接線、靠位置排在後面」 |

然後看了六張示意圖（ebi-die-to-die、rsem-worst-box、one-image-uniformity、
characterization、「用到沒接過來的數字」的提醒、拉線跳出的小選單）：「可以」。

## 2. 一句話

**線只講「資料流到哪裡」，不講「准你用哪些數字」。** 量測卡把量完的 defect 送進
Decision，Decision 把分好類的 defect 送進 Output —— 一條從 Input 接到 Output、
中間不斷的流。流過去的是**整顆 defect**：它身上每一個 feature（量測卡的、上游每一張
卡順手記的、Input 帶進來的 KLARF 欄位）都跟著走，判定樹可以全部拿來當 attribute。

**驗收標準**：使用者看著畫布，能用一句話講完它在做什麼，而且句子裡每一段剛好是
畫布上的一條線。例（ebi-die-to-die）：

> Input 讀進 test 和 ref → 兩張各自 Normalize → 相減得到 diff → 去雜訊 → GLV 量灰階
> → 量完送進 Decision → 分好類寫成報表。

## 3. 跟 F123 比

| | F123 做完的樣子 | F124 |
|---|---|---|
| 誰有送去判定的埠 | 任何一張記了數字的卡（Input、Normalize、Denoise、ROI 都有）| **只有量測卡**：GLV、CD、Focus index、H2H |
| 判定問得到哪些數字 | 只有**直接**接進 Decision 的卡的 | **流進 Decision 的一切**＝沿線往回走得到的每一張卡的 feature |
| 問到一張沒流進來的卡的數字 | error，不能跑 | **提醒**（warning）＋一顆「Connect ＿」；照常跑 |
| 「插入數字 ▾」 | 只列接進來的卡 | 全部列出，照卡片分組；沒流進來的排在後面並註明 |
| Output 寫什麼 | 只寫上游卡片的數字（排除式）| **整張表**；Decision 在它上游就加上類別 |
| Write charts 畫哪些框 | 只畫上游那幾張 GLV 的 | 每一張 GLV 的（回到 F123 之前）|
| 埠上的字 | `numbers` / `results` | `measured` / `classified`（只是顯示；recipe 裡的鍵不變）|
| Decision／Output 完全沒有東西流進來 | error | error（照舊 —— 那就是畫布斷掉）|

照留的：Decision 是真的卡、判定樹掛在它下面（F123 期 1）；Write comparison 的左圖右圖
是影像埠（期 3）；線照資料種類上色、停上去整條路徑亮、換行的線繞著走（期 4）。

## 4. 逐張卡看過的結果（2026-09-29）

| 卡 | 左邊（收）| 右邊（吐）| 有沒有「送去判定」的埠 | 丟上去會不會問（§5 期 4）|
|---|---|---|---|---|
| Input | — | `test`、`ref`，或自己命名的 channel | 沒有（`n_channels`、KLARF 欄位跟著流）| — |
| layout(GDS) | — | `layout_label` | 沒有 | — |
| Pair source | — | `paired` | 沒有（`pair_found` 跟著流）| — |
| Normalize | 要處理的流（多條）＋ Borrow range from／Match it to | 處理過的流 | 沒有（`clip_frac`）| **會**：兩格角色不同 |
| Denoise、Adjust tone、Flatten | 要處理的流（多條）| 同名 | 沒有 | 不會 |
| Align | 要對齊的流（多條）＋ …on this one | 對齊後的流 | 沒有（`align_*` 跟著流）| **會** |
| Compare | First、Second | `diff`（＋原樣送出）| 沒有 | **會**：a、b 反過來正負號反 |
| Image Combination | 要合併的流（多條）| `merged` | 沒有 | 不會 |
| H2H | Small image、Search inside | `aligned` | **有**（`ncc_score` 是它的產出）| **會** |
| ROI | Image 或 Layout labels（依 method 一次一格）| 區域（每個三個名字）＋原樣送出 | 沒有 | 不會 |
| GLV | Measure on（多條）、Ref image；Region（多條）、Ref region | 原樣送出 | **有** | **會**：量測 vs 參考 |
| CD、Focus index | 圖（多條）、Region（多條）| 原樣送出 | **有** | 不會 |
| Decision | `measured`（多條）| `classified` | — | 不會 |
| Write report／KLARF／charts | `classified` 或 `measured` | — | — | 不會 |
| Write comparison | Left picture、Right picture、`classified` | — | — | 圖會問左還是右 |

characterization 那條流因此是 Pair source → H2H → Decision：判定第一題問的
`pair_found` 跟著 defect 經過 H2H 流進來，不用從 Pair source 跳過 H2H 拉一條線。

## 5. 分期

每一期結束：`ruff check`、`python tools/typecheck.py`、`python tools/freeze_golden.py
--check`（引擎的數字一個都不准動）、`python tools/run_tests.py`、SESSION_LOG。

### 期 1 — core：流進 Decision 的東西

* `Step.measures: ClassVar[bool] = False`；GLV、CD、Focus index、H2H 設 `True`。
  `Step.data_output` 只在 `measures` 而且這張卡真的寫數字時回 `NUMBERS`。
* **判定問得到什麼＝Decision 的上游**（`recipe_schema.upstream_of`，沿所有線）。
  `decision-not-wired` 改成 warning、判準改成「那個數字的卡不在上游」；Issue 帶上
  「接哪一張卡就好」的結構（新的選配欄位，給期 2 那顆按鈕用），`advice` 照 F118 寫。
  `output-number-not-upstream` 同一套判準與結構。
* `data_lines.rows_for_output`：寫整張表；`decided`＝上游有一張啟用的 Decision；沒有
  Decision 時判定自己寫的數字照舊不寫。**⚠ 這一條不改的話，報表會安靜地少掉量測
  欄位**（逐張看卡時發現的：F123 的排除式判準碰到「量測卡沒有數字埠」就把它的數字
  全排掉）。
* Write charts：`output._upstream_notes`、`charts-need-each-box`、`unknown-chart-metric`
  回到看每一張 GLV。
* 「插入數字 ▾」：`RecipeModel.decision_numbers` 與 Output 卡的 `labelled_features`
  列全部，照卡片分組，沒流進來的排後面並註明。
* **第 8 版遷移**（`version < 8`，判準是「舊東西在」：從不再有數字埠的卡拉出來的
  數字線）：拿掉；拿掉之後那張 Decision／Output 一條資料線都不剩的話，改接它下游
  最近的量測卡；沒有就留給 lint 講。`to_json → from_json` 必須是 identity（鐵則 9）。
  `RECIPE_VERSION` 7 → 8、`tools/doctor.py` 跟著；三份出貨 recipe 存成第 8 版（它們都
  只有 GLV → Decision，線不變）。
* one-image-uniformity 那張 Write report 的 id 叫 `numbers` —— 副標會印成
  「numbers · classified」，看起來像數字線。改名（先 grep 誰在用）。
* 測試：`test_data_lines.py`、`test_output_lines.py`、`test_ui_data_lines.py` 裡
  跟「必要」「只列接進來的」「只寫上游」有關的改寫；新增：只有四張卡有數字埠、
  上游卡的附帶數字不提醒、另一條支線上的卡會提醒、遷移。

### 期 2 — 畫布的樣子

* 埠上的字：`measured` / `classified`，走 `ui/strings.py`（recipe 的鍵 `numbers` /
  `results` 不動 —— CLAUDE.md §3「參數名是 recipe 的鍵，不是給人看的字」）。
  Decision 副標「measured → classified」，Output 副標寫它收到什麼。
* **原樣送出、沒接線的埠**畫小、畫淡；有接線的照常畫。判準用畫布的定義（`produces`
  ／`regions_produced` 以外的就是原樣送出 —— `docs/PITFALLS.md` 的「那張卡有哪些
  輸出埠有兩個答案」）。
* **埠名不截斷**：左右兩側的字寬 52 → 約 80 px、小一號字；`boundingRect`、欄距、
  數像素的那幾條測試跟著調。示意圖上「Ref image」「Ref region」「Left picture」都
  放得下；「Borrow range from」仍會切 —— 要不要改短字另外問。
* **提醒的那顆鈕**：Decision 的在判定面板頂端（點 Decision 卡時右邊那一塊）、
  Output 的在它的設定區。按下去走 `canvas_edges.connect` —— 跟手拉的線同一條路
  （`bridge` 的理由），一步復原。

### 期 3 — 線不從卡背後穿過、「整理」照流排

* **同一列的線**：直直的那條曲線會壓到夾在中間的卡時（rsem-worst-box 的
  Input → GLV 從 ROI · on_pattern 背後穿過去，看起來像是 ROI 吐出來的），改走列上方
  的空隙，跟期 4（F123）換行的線同一種折法。放新模組（`canvas.py` 在規模尺上）。
  測試照 F123 期 4 那條：**用描邊比**，不用 `QPainterPath.intersects`。
* **「整理」**：characterization 那幾張卡現在會排成 Pair source 在 Input 右邊、Decision
  換到下一列、線交叉；目標是示意圖 ④ 那種（Input、Pair source 疊在第一欄，H2H、
  Decision、Write comparison 往右）。先查 `layout_columns` 為什麼沒照深度排，再決定
  怎麼改。

### 期 4 — 拉線：丟在卡上就好

* 現在「丟在卡上沒丟準埠」會**安靜地挑高度最近的那一格**（`canvas.in_param_at` 的
  退路）—— 丟在 Compare 偏上面就接 a、偏下面就接 b，使用者看不出來。改成：
  * 丟在埠上 → 接那一顆（跟現在一樣）。
  * 丟在卡上、只有一格接得上 → 直接接。
  * 兩格以上 → 在放手的地方跳小選單，只列接得上的那幾格；單一格已經有線的寫明
    「會取代 ＿ 那條」。
  * 一格都接不上 → 不接，一句白話說為什麼（`edit_plan` 本來就講得出）。
* 放新模組（`ui/link_drop.py`）。選單要有關得掉的旗標（CLAUDE.md §4 F91：headless
  測試會永遠停在 modal 上）。

### 文件（跟著各期）

* `docs/USING-CHARACTERIZATION.md` §3／§3.1 還寫著「Output 段不用接線、副標寫
  `(not connected)` 是正常的」—— F123 之後就不對了，期 1 一起改。
* `docs/ARCHITECTURE.md`（`data_lines.py` 那一行）、ROADMAP、CLAUDE.md 鐵則 10 若有
  需要補一句「線講流到哪裡；判定問得到的是流進它的」。

## 6. 不變的

* 引擎算出來的數字、黃金值（每一期都跑 `freeze_golden --check`）。
* 判定的內容仍在 `recipe.decide`；recipe 裡線的存法（`recipe.edges`、埠名 `numbers`
  ／`results`）。
* 鐵則 10：每一條線都是使用者拉的 —— 提醒那顆鈕是使用者按的，遷移補的線只給舊檔案。
* 鐵則 11：Studio 跑不寫。

## 7. 示意圖

2026-09-29 在對話裡給使用者看的六張，是用當時的程式碼加一支臨時腳本改畫法截的
（repo 沒動）：① ebi-die-to-die ② rsem-worst-box ③ one-image-uniformity
④ characterization（手動排版）⑤ 判定問到另一條支線上的 CD 時的提醒 ⑥ 從 Denoise
丟到 Write comparison 時的小選單。⑤ 的提醒框、⑥ 的虛線與選單是手畫的。

## 8. 期 1 的紀錄（2026-09-30）

* `Step.measures`（GLV、CD、Focus index、H2H）；`Step.data_output` 只給它們 ``numbers``。
* `data_lines`：`feeder`（要接哪一張卡，這個數字才流得進來 —— 它自己，或它下游
  第一張量測卡）、`_not_flowing`；`decision-not-wired` 與 `output-number-not-upstream`
  共用 `_not_flowing_issue`：warning、判準是「不在上游」、`Issue.connect` 帶接誰
  （新的選配欄位）。`needs-decision` 也帶 `connect`（那張 Decision）。
* `output-not-connected`：**一份沒有任何東西接得進 Output 的 recipe 不講**（只有影像
  卡、整理圖片那種）—— 量測卡以外的卡沒有送出去的埠之後，那一條在那種 recipe 上是
  修不好的紅字。任何一條線（含 Write comparison 的左圖右圖）都算流進來。
* `rows_for_output` 寫整張表；Write charts 與 `charts-need-each-box` /
  `unknown-chart-metric` 回到看每一張 GLV（`output._upstream_notes` 刪掉）。
* 「插入數字 ▾」：`decision_numbers` 與 Output 卡的 `labelled_features` 全部列出，
  流進來的排前面，沒流進來的那一組標題加「· not connected」。判定面板的「建議一題」
  避開確定沒流進來的（`decision_numbers_not_flowing` —— 問「確定沒流進來」不問
  「確定流進來」：宿主餵的名字可能 model 不認得來歷）。
* **第 8 版遷移** `_migrate_measured_lines` 取代第 7 版那一道（`version < 8` 一道
  跑完）：拿掉從不量東西的卡拉出來的數字線、判定問到但沒流進來的從 `feeder` 補、
  一條線都沒有的 Output 補（有 Decision 從 Decision，沒有從每一張量測卡）。第 7 版
  那道給每一張「以前寫得出去」的卡補的直接線不補了（報表寫整張表）。
  `describe_migration` 講得出「took off N wires from cards that do not measure」。
* 出貨 recipe 存成第 8 版（線不變）；one-image-uniformity 的 `numbers` 改名 `report`。
* 文件：`USING-CHARACTERIZATION.md` 的步驟與 §3／§3.1（「不用接線」拿掉，`pair_found`
  不用另外拉線）；ARCHITECTURE 那一行。
* 黃金值三份逐項相同；pyright 128（第一版 +2：Write charts 的 `notes` 可能是 None ——
  刪掉的那一支以前順手把它變成 list）。

## 9. 期 2 的紀錄（2026-09-30）

* **畫面上的字**：`wording.port_word`（``numbers`` → ``measured``、``results`` →
  ``classified``）—— 埠名、Decision／Output 的副標、拉錯線時那句話、剪線的狀態列。
  recipe 裡的鍵不動（`recipe.edges` 上照舊是 ``numbers`` / ``results``）。
* **埠名放得下**（使用者選 A）：欄距 116 → 156、埠名寬 52 → 74、所有埠名小一號字。
  ``NODE_W + COL_GAP`` = 360 仍是格線的倍數。放得下 `Ref image`、`Ref region`、
  `Left/Right picture`、`Search inside`、`Small image`；`Borrow range from`、
  `Second stream` 與很長的區域名照舊切中間。`WRAP` 的四欄因此是 1,284px（那條
  測試的門檻 1,200 → 1,300，寫了理由）。
* **原樣送出、沒有線接出去的輸出埠**畫小、畫淡：`canvas_edges.data_ports` 算
  `info["quiet_out"]`（畫布的定義：`writes` 減 `produces`、`regions_out` 減
  `regions_produced`，再減掉有線接出去的），`canvas._draw_port(quiet=)` 畫。
* **「Connect ＿」**：放在問題清單（`problems_bar`）那一條底下，不另開第二個地方
  —— 那是「現在有什麼問題」唯一的家（U2）。按下去走 `canvas_edges.connect_into`
  → `bridge` → `connect`，跟手拉的線同一條路、一步復原。計畫書原本寫「Decision
  的在判定面板頂端、Output 的在設定區」，改成這一個地方。
* 規模尺：`canvas.py` 3,263 → 3,278（+15，簽了）。

## 10. 期 3 的紀錄（2026-09-30）

* **線不從卡背後穿過**：`ui/edge_route.forward_detour` —— 往前走的曲線（取 32 個點）
  壓到夾在中間的卡，就改走那幾張卡上方（或下方）的空隙，跟換行的線同一種折法。
  rsem-worst-box 與 one-image-uniformity 的 Input → GLV 以前從 ROI 卡背後穿過。
* **一顆輸入埠一條道**（`edge_route.lane`）：繞行的線最後那段垂直的，越下面的埠
  離卡越遠；而且整段落在埠名外面（`_EdgeItem.SIDE` ＝ 埠名寬 ＋ 8）。換行的線也照
  這一條（F7-24 那條「甩太遠」的測試放寬到這兩個數，寫了理由）。
* **「整理」照流排**（排版搬進 `ui/layout.py`，純函式）：
  * **沒有入口、也不讀東西的卡是起點**（Input、Pair source、layout(GDS)）—— 不替它
    補「route 前一張」的依賴。characterization 的 Pair source 因此疊在 Input 下面，
    不再排在 Input 右邊（讀起來像 Input 餵給它）。
  * **最後一帶只剩終點就不換行**（`_tuck_the_tail`）：Output 排在它最深的那張上游
    那一欄、最下面。ebi-die-to-die 的 Write report 以前孤零零換到下一列第 0 欄，
    那條線從最右邊繞回最左邊；characterization 的 Write comparison 三條線疊成一束。
* 「停一張卡在線的中點上」那條測試：線現在會繞開，所以拆成兩條 —— 一條驗「會
  繞開」，一條把繞行關掉、照舊驗「被蓋住時 × 按得到」（換行的線還是可能被蓋）。
* 規模尺：`canvas.py` 3,278 → 3,245（排版與繞行的幾何搬出去）。

## 11. 期 4 的紀錄（2026-09-30）

* `ui/link_drop.py`：線丟在卡上，接到哪一格 —— 丟在埠上接那一顆；只有一格接得上
  就直接接；兩格以上在放手的地方跳小選單（只列接得上的；單一格已經有線的寫
  「replaces the line from ＿」；取消＝不接）；一格都接不上照舊交給 `edit_plan`
  講為什麼。以前的退路（`in_param_at` 挑高度最近的那一格）只留給 headless 測試。
* 選單是 modal 的：`link_drop.ASK`（`tests/conftest.py` 關掉）與 `link_drop.CHOOSE`
  （要驗選單的測試代替使用者挑）—— CLAUDE.md §4 F91 那條。
* `accepts`（一顆埠收不收這種線）從 `canvas.py` 搬進 `link_drop`，畫布轉用。
* 整套 311 個檔案一次全綠；黃金值三份逐項相同。
