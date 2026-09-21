# F120 — Pitch helper（丟一張圖進去，回答它的 cell period）

狀態：**第一版做完，等使用者看過（2026-09-21）** —— `python -m d4t pitch` 開得
起來，四點追加的需求都在（§5／§5.1／§5.2）。⚠ **不寫「已收斂」**：使用者還沒
在真實影像上用過，而這種工具的驗收只有那一件事算數。⚠ §5 那顆「格線」按鈕
**做的時候從「一顆鈕」改成「預設開著」**，理由與它揪出來的那個 bug 在 §10。

使用者 2026-09-21 指定：把「算 repeating pattern 的 cell period」這一件事
**獨立成一個 helper**，原本 ROI 那張卡的功能一個字都不動。形狀照 `simgen`
（自己的 CLI 進入點 ＋ 獨立小視窗）。同一天追加四點：**要能看圖驗證**、
**cell 切點格線預覽**、**純 X／純 Y 也要支援**（今天是 X＋Y 都取最小週期成
GC）、**原有的 crop 也要有**。

---

## 1. 為什麼

使用者的原話：

> 主要是算 Golden cell（應該在 ROI 內那張卡），命名就叫 **pitch helper**，
> 主要功能就是丟一張圖進去，算 repeating pattern 的 cell period
> （可支援 pixels & X(nm)）。

今天這個能力**只存在於一條很長的路的中間**：Studio → `roi_reference`
（`method="template"`）→ `TemplateDialog` → 匯入大圖 → 疊模板。週期是那條路的
**副產品**，而使用者常常只想要那個數字本身 —— 他手上有一張 SEM，他要知道
pitch 是多少。為了那一個數字，今天他得先開 Studio、先有一份 recipe、先加一張
ROI 卡、先接好線，才點得到那個對話框。

**那不是「功能不存在」，是「入口不存在」。** 所以這一份不新增任何演算法。

## 2. 不做什麼（範圍）

* **不動 `roi_reference` / `roi_template` / `TemplateDialog`。** 原功能原封不動，
  黃金值不動、recipe 不動、卡片庫不動。
* **不疊 Golden Cell。** 疊圖（`build_golden_cell`）在 7680² 上要十幾秒，而它
  回答的是「模板長什麼樣」。helper 回答的是「pitch 是多少」，那是
  `template.measure_period` 一支就答得完的事。
* **不猜 nm/px。** 見 §4。

## 3. 核心邏輯不搬家、不抄第二份

量週期的**唯一出處**是 `algo/template._measure_period` —— 三票制（投影法
`period.estimate_period` ＋ 二維自相關 `period2d.estimate_period_2d` ＋
半週期檢查 `period2d.half_period_check`），四個月的實測、諧波修正、交錯晶格的
加倍規則全部長在它身上。

它今天是**私有**的，而 helper 需要一個講得出口的入口。所以：

> `_measure_period` → **`measure_period`**（公開，進 `__all__`）。

⚠ **不留舊名字的別名。** 一件事兩個名字正是 `CLAUDE.md` §0 在擋的東西；
呼叫者只有三處（`build_golden_cell` 一處、兩支測試各一處），一起改。
這一步**不改任何一行演算法**，驗收是 `freeze_golden.py --check` 三份逐項相同。

## 4. 單位：px 是答案，nm 是換算（照既有的那條規矩）

`docs/FAB-VALIDATION.md` 的假設 #2 已經定調：**`nm_per_px` 在 KLARF 裡沒有
來源，所以單位一律 pixel、換算搬到輸出那一刻**。`algo/grid.py` 的檔頭把這件事
講得更白：「這裡收 nm 的話，它會變成第二個恆為 0 的 `cd_x_nm`」。

helper 照抄卡片那一套（`steps/_util.nm_per_px_spec`）：

| | |
|---|---|
| **Pixel size** 一格，單位 nm/px，**預設 0 ＝ 不知道** | 使用者自己填（機台設定裡有） |
| 0 的時候 | 只顯示 px。**不顯示一個 0 nm** —— 那看起來像一個量出來的答案 |
| > 0 的時候 | px 旁邊**同時**顯示 nm（`period × nm_per_px`），兩個都在 |

換算本身是一個乘法，所以它住在畫面那一層；core 不會多一個 nm 的概念。

## 5. 「假設算不對我該怎麼知道」

這是使用者 F103 問過的那一句，而它對一個**只輸出一個數字**的 helper 更尖銳：
一個錯的 pitch 看起來跟對的一模一樣。所以畫面上要有三層證據，而它們都已經
存在，只是搬進同一個視窗：

1. **每一軸的信心值**與 `measure_period` 的 `notes`（換了量法、加倍了、
   諧波鏈不直 —— 每一句都是使用者該知道的決定）。
2. **交錯分數** `stagger`（交錯晶格 ≈ 1、規則晶格 ≈ 0）。
3. **把 cell 的切點格線鋪回原圖**（`lattice_dialog.lattice_boxes`，F103 那一套）
   —— 「每一格框住的東西都一樣就是對的；格線在圖的另一頭漂到別的結構上，
   就是錯的」。一眼的事，不需要懂任何分數。

⚠ **格線預設開著，不是一顆要去找的按鈕**（使用者 2026-09-21 追加：「要能驗證
（看圖）」「cell 切點格線預覽」）。代價是量完之後還要跑一次
`period.choose_origin`（相位搜尋，4096² 實測 5.3 秒）—— 所以它跟量週期**在同一
個 worker 裡一起跑完**，進度條講到哪一步，而不是量完先還一個數字、再讓使用者
按第二顆鈕等第二次。留一個開關是為了「看原圖」，不是為了省那幾秒。

### 5.1 純 X／純 Y（使用者 2026-09-21 追加）

> 「也能支援純 X 純 Y（目前是 X+Y 都取最小週期成 GC）」

一維的 layout 是常態（垂直條紋只有 X 有週期），而自動判斷會在**兩軸都量得到
東西**的時候兩軸都切 —— 使用者要的那個單元卻可能只在一個方向上重複。所以
軸向是一格**使用者說了算**的選擇，四選一（`chip_choice` 的膠囊形狀）：

| 選項 | 意思 |
|---|---|
| **Auto** | 量到哪一軸就用哪一軸（今天的行為，預設） |
| **X only** | 只切直線。Y 那一軸「一格就是整張影像」（`lattice_boxes` 本來就這樣處理沒有週期的軸）|
| **Y only** | 只切橫線 |
| **X + Y** | 兩軸都切，**即使某一軸信心不足**（使用者明講的一律相信 —— 同 `build_golden_cell` 的 `given` 規則）|

⚠ **它不改量出來的數字**，只改「哪幾軸算數」。兩軸的 px／py 一直都量、一直都
顯示，選 X only 只是讓 Y 那一欄變成「not used」而不是消失 —— 藏起來的話使用者
會以為量不到。

### 5.2 Crop（使用者 2026-09-21 追加：「原有的 crop 功能也要有」）

直接用 `ui/crop_dialog.CropDialog` ＋ `crop_array` —— **同一支**，不抄第二份。
它存在的理由在 helper 上一字不差地成立：整張圖裡不只有你要的那種 cell
（缺陷本體、scribe line、機台的量測條），而週期估測看的是整張圖的投影。

兩處接法：

* **載入一張圖之後**跟著問一次（同 `template_dialog`「每次載入大圖都會出現」）；
* 畫面上一顆 **Crop…** 鈕，隨時回去改那一塊，改完自動重量。

⚠ `CropDialog` 的 OK 鈕今天寫死「Stack from this box」（模板那條路的字）。
helper 不疊圖，所以那句話在這裡是假的 —— 加一個 `ok_text` 參數，**不分叉出
第二個對話框**。

## 6. 跑在背景執行緒

實測（這台容器，合成圖）：

| 影像 | `measure_period` | `choose_origin` |
|---|---|---|
| 512² | 160 ms | 113 ms |
| 1024² | 912 ms | 367 ms |
| 2048² | 1.7 s | 1.1 s |
| 4096² | 2.8 s | 5.3 s |

超過一秒的東西跑在 UI 執行緒上，視窗會被 Windows 標成「沒有回應」——
`build_golden_cell` 的 `progress` callback 當初就是為了這件事加的。所以
helper 用 `QThread` worker（形狀照 `gc_generator._GenWorker`）。

## 7. 檔案

| 檔案 | 動作 |
|---|---|
| `d4t/core/algo/template.py` | `_measure_period` → `measure_period`（公開，進 `__all__`）|
| `d4t/ui/pitch_helper.py` | **新**：視窗本體。⚠ 照 `CLAUDE.md` §4「新的面板一律開新模組」|
| `d4t/ui/crop_dialog.py` | `CropDialog` 多一個 `ok_text` 參數（§5.2）|
| `d4t/__main__.py` | `pitch` 子命令（形狀照 `_cmd_simgen`：lazy import，沒有 PySide6 時講人話）|
| `docs/ARCHITECTURE.md` | 目錄樹那行 `# CLI：…` ＋ 一列說明（`test_docs_match_registry` 在守）|
| `README.md` | CLI 那一節 |
| `tests/test_ui_pitch_helper.py` | **新**：要 Qt，所以檔名是 `test_ui_*`（鐵則：核心批在沒有 Qt 的機器上也要綠）|
| `tests/test_measure_period_is_public.py` | **新**：公開入口不准再變回私有 |

## 8. 刻意不放進 Studio 的工具列

同 `gc_generator` 的理由，逐字適用：那條工具列已經滿到把「Results」擠進 Qt 的
overflow 過一次（F48）。這是一個**問一個數字**的工具，不是分析流程的一步。

## 9. 驗收

* `python -m d4t pitch` 開得起來，丟一張合成的週期圖進去，量到的 pitch 與
  產生它的參數相同；
* 填 nm/px 之後 nm 那一欄出現，填回 0 就消失（**不是變成 0 nm**）；
* 量完**自動**畫出切點格線，格子落在同一種結構上；
* 軸向選 X only 時只切直線、Y 那一欄寫「not used」而不是消失；
* Crop 之後重量，量到的是那一塊的週期（用一張「左半邊 40 px、右半邊 24 px」
  的合成圖驗：不裁跟裁一半要給出不同的答案，否則那顆鈕是裝飾）；
* `freeze_golden.py --check` 三份逐項相同（§3 的重新命名沒有動到任何數字）；
* `ruff check` 綠、核心批綠、新測試綠。

---

## 10. 做的時候改掉的事，與預覽揪出來的那個 bug

**§5 的「格線是一顆按鈕」撤回了。** 使用者追加「要能驗證（看圖）」「cell 切點
格線預覽」之後，那顆鈕的前提就不成立了：要人**去找**的驗證等於沒有驗證。
所以格線跟量週期在同一個 worker 裡一起跑完、預設開著，勾勾留給「我要看原圖」。

**預覽揪出一個真的 bug（已修，有回歸測試）。** 第一版按下「X only」之後：

* 表格**立刻**寫 `Down (Y) — not used`；
* 而圖上的**橫線還在**，因為重畫排在 `choose_origin` 後面，要等好幾秒。

畫面同時在說兩件相反的事，**而使用者會相信圖**。修法是軸向一改就當場用舊的
原點重畫（丟掉 Y 軸不會改變 X 的相位），worker 回來再換成重新搜出來的那一個。
守門：`test_ui_pitch_helper.py::test_switching_the_axis_redraws_the_grid_at_once`。

⚠ **那是「畫一張圖看看」買到的，不是讀程式碼讀出來的。** 兩段程式各自都正確
——表格讀的是同步算得出來的 flags，格線讀的是非同步回來的 origin；錯的是
它們**在同一個畫面上**，而畫面沒有「稍等」這個狀態。

**`measure_period` 多了一道空影像的防呆。** 它私有的時候不需要（唯一的呼叫者
更早就擋掉了），公開之後呼叫端是「使用者剛剛丟進來的那個東西」，而
`cv2.Sobel` 對 0×0 是 `cv2.error`。**開放一支函式就要讓它自己站得住。**
驗過 `freeze_golden --check` 三份逐項相同 —— 那條路 `build_golden_cell` 走不到。

## 11. 還沒做

* **沒有 `docs/USING-PITCH.md`**，所以視窗上沒有「Manual →」那個連結
  （`gc_generator` 有）。畫面上的字目前自己撐著；使用者用過一輪、確定流程不
  再變之後再寫，比現在寫完再改兩次省。
* **沒有接進 Studio**（刻意，§8）。
* `tools/typecheck.py` 在這一輪**仍然是 131 條**（上限 128）—— 那 +3 是
  `c325400`（F117 I5／F6）留下的，`main` 的 CI 從 2026-09-19 起就因為它紅著，
  **跟這一輪無關**（量法：在 `eec030c` 上跑同一版 pyright 是 128）。
