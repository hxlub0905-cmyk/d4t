# F39 — F 編號測試審一輪（清單）

**狀態：清單完成，等使用者確認。B0 撞到一個比測試大的東西，見 §4。**

工作單 Phase 2。規矩：

> **不要直接動手刪。** 先產出一份清單交給使用者……清單確認之後再分批改，
> 一批一個 PR。

**所以這一份就是產物。** 36 支 F 檔、605 條測試逐條看過。

---

## 1. 量出來的規模

| | 檔 | 條 | 行 | 逐檔跑的秒數 |
|---|---:|---:|---:|---:|
| UI 測試全部 | 64 | 1,020 | 22,960 | 244 |
| **其中 F 編號** | **36** | **605** | **13,128** | **162** |
| 非 F 編號（常駐） | 28 | 415 | 9,832 | 83 |

F 編號佔全部測試的 24.4%、佔 UI **牆鐘時間的 66%**；36 支裡 **30 支要建
`StudioWindow`**，那才是時間的來源（`f19_cd` 40 條純 API 只要 0.9 秒，
`f7_15` 8 條要 12.7 秒）。

**判定：605 條 → 留 ~323、刪 ~282。**

---

## 2. 判準與三個先撞到的事實

逐條問工作單那一句：

> 這條斷言講的是「不管怎麼改，這件事都必須成立」，還是「當初那一輪交付了」？

### 2.1 「F 編號」不是可靠的訊號

`docs/plans/F11-phase2-features.md:50` 已經寫著「**F10 的 20 條畫布不變量**會
自動套用到新註冊的卡」。`test_ui_f10_canvas_reality.py`（B1 已改名，見 §3 A）
是逐張套用到 registry
的性質測試，只是檔名帶 F 編號。`f7_16`（undo／關窗／停止）、`f7_17`
（inspector）、`f16_run_all`（試跑不寫）、`f20`（面板不能說謊）、`f9_7`
（一個輸入埠一條線）同樣如此。**對這六支，正確的動作是改名，不是刪。**

### 2.2 這件事做過一次，而且留下了做法

`tests/test_ui_canvas_truth.py` 開頭：

> **這是 F9／F10 那兩輪換來的東西，而在這一份之前沒有任何測試在守它。**

F9／F10 的驗收檔**並沒有真的守住**那條不變量 —— 它們只測了想得到的那幾個
組合，真正的守門人是後來寫的那支**隨機接線／剪線的性質測試**（400 組序列，
第一輪就抓到 B1）。

> **樣板**：救出來的不變量不一定是「把那幾條搬過去」，有時候是「把它重寫成
> 一條機器撞得到的性質」，然後那一整批寫死的案例才真的可以刪。

### 2.3 三種硬約束

**(a) 六條 pitfall 指名了它的守門人**（`docs/history/` 是檔案館可以過期，
這幾份是活的）：

| 活文件 | 指名的測試 | 守的是什麼 |
|---|---|---|
| `PITFALLS.md:43,45,46` | `f7_23_buttons` | **三條** Qt 坑：QSS 特異性讓 `:focus` 被安靜蓋掉、小圖示不能照比例縮、Qt 不夾 `border-radius` |
| `PITFALLS.md:16` | `f15_pair_source` | 第二份 lot 只送進一半的路 |
| `PITFALLS.md:27,28` | `f7_9` / ~~`f7_14`~~ | `boundingRect()` 沒涵蓋畫到節點外的東西；`paint()` 用場景座標。⚠ **那條 pitfall 指的守門人已經過期**：它說 `f7_14` 會斷言「`+` 的中心在 `boundingRect` 裡」，而那顆 `+` 在 F7-18 就撤了。B2 刪掉 `f7_14` 時把它改指向真的還在守的三支（`test_ui_canvas_invariants` 對每一張卡、`f7_9_feedback`、`test_ui_canvas_cut_button`）|
| `PITFALLS.md:41` | `f7_16` | `_update_action_states` 蓋掉 tooltip |
| `PITFALLS.md:56` | `f7_18` | 拆卡片時的順序陷阱 |
| `ARCHITECTURE.md:71`、`ROADMAP.md:199` | `f16_stages` | `GROUP_ORDER` 與 `LibraryPanel.GROUPS` 綁在一起 |

**一條 pitfall 指名了守門人，那就是一個契約。**

**(b) 四個 UI 模組只有 F 檔碰得到**（常駐測試零覆蓋）：
`cell_canvas.py`（1,086 行，只有 `f7_12`／`f8_cross`）、
`region_check.py`（341 行，只有 `f7_11`／`f7_12`／`f8_calibrate`／`f8_cross`）、
`template_dialog.py`（1,047 行，只有 `f7_12`）、
`inspectors.py`（2,917 行，12 支 F ＋ 2 支常駐）。

**(c) grep 過的獨家覆蓋**（刪掉就零覆蓋）：
`ambiguous-input` → 只有 `f9_7`；`_explicit_bindings` / `_unmet_needs` → 只有
`f9_9`；`"advanced" in spec` → 只有 `f8_advanced`；`_migrate_also_apply` →
只有 `f7_18`（＋`f7_9`）。

---

## 3. 清單

### A. 改名留下（6 支，110 條 → 留 92）

| 檔 | 條 | 留 | 為什麼不是驗收快照 | 新名 |
|---|---:|---:|---|---|
| `f10_canvas_reality` | 21 | 15 | 7 條逐張套用到 registry；文件已稱它「F10 的 20 條畫布不變量」 | `test_ui_canvas_invariants.py` |
| `f7_17_inspectors` | 41 | 33 | inspector 機制的行為套件；`inspectors.py` 幾乎只有它在守 | `test_ui_inspectors.py` |
| `f7_16_safety_net` | 21 | 18 | undo／關窗／停止；`test_ui_save_recipe.py` 的 docstring 自己指過來 | `test_ui_undo_close_and_stop.py` |
| `f16_run_all` | 12 | 12 | 「試跑不寫、只有整批才寫」是使用者定調的規則，唯一守門人 | `test_ui_write_only_on_run_all.py` |
| `f20_panel_truth` | 8 | 8 | 面板不能說謊；`row_labels` / `_focus_box_index` 別處沒有 | `test_ui_panel_truth.py` |
| `f9_7_user_draws...` | 7 | 6 | 鐵則 10 的正典；`ambiguous-input` 獨家 | `test_ui_canvas_one_line_per_input.py` |

> ⚠ **上面兩個名字在 B1 動手時修正過**（2026-08-27）。清單第一版寫的是
> `test_canvas_invariants.py` 與 `test_canvas_one_line_per_input.py` —— **少了
> `test_ui_` 前綴**。這兩支都會 `QApplication()` ＋ `StudioWindow()`，而 CI 就
> 是照那個前綴分批的（`ci.yml:72` 核心批跑 `--ignore-glob="*test_ui_*"`、`:82`
> 的 UI 批跑 `tests/test_ui_*.py` 逐檔一個行程）。照第一版的名字改下去，這兩支
> 會**同時**掉出 UI 批、掉進核心批那個跑 2,400 條的行程 —— 那正是
> `AGENTS.md` §5 量過的 Qt 記憶體累積（整套一個行程 1:39:09 vs 逐檔 7 分鐘）。
>
> **「改個名字」在這個 repo 裡不是零風險的操作，因為檔名是 CI 的分批依據。**
> 這一條沒有測試在守（B1 之後也還是沒有）—— 它靠的是動手的人知道那個 glob。

### B. 大部分留下（5 支，61 條 → 留 45）

| 檔 | 條 | 留 | 說明 |
|---|---:|---:|---|
| `f7_23_buttons` | 22 | 14 | ⚠ **真的不變量檔**：三條 pitfall 說「規則寫了但畫面沒變」，量畫素是唯一看得見的儀器。刪的是「釘住哪一個顏色」那幾條 → `test_ui_button_contract.py` |
| `f11_canvas_truth` | 15 | 13 | 一條被 f10 的 registry 版蓋掉 |
| `f13_features` | 9 | 8 | → `test_ui_feature_table_truth.py` |
| `f9_9_two_lines...` | 10 | 7 | 三條被 f10 的 registry 版蓋掉 |
| `f16_stages` | 5 | 3 | ⚠ **Phase 3 才動**（見 §5）|

### C. 分家：救出不變量再刪其餘（12 支，301 條 → 留 ~150）

| 檔 | 條 | 留 | 救出來要去哪 |
|---|---:|---:|---|
| `f7_12_template` | 56 | ~19 | **不可整支刪**（`template_dialog`／`cell_canvas` 唯一覆蓋）→ 新 `test_ui_template_dialog.py`；三條 algo 測試 → `test_roi_template.py` |
| `f19_cd` | 40 | ~26 | 面板↔疊圖一致 8 條 → `test_ui_panel_truth.py`；metric-face 2 條 → `test_ui_widgets.py` |
| `f15_pair_source` | 35 | ~26 | §8／§9 → `test_ui_canvas_truth.py` ＋ 新 `test_ui_marks_truth.py` |
| `f8_cross` | 35 | 12 | 「畫面要顯示卡片真的用到的每一個東西」9 條 → 新 `test_ui_region_overlay_truth.py` |
| `f7_9_feedback` | 25 | 13 | 階段色 3 → `test_ui_widgets.py`；埠幾何 3 → `test_ui_canvas.py`；lint 5 → `test_card_invariants.py` |
| `f11_card_aids` | 21 | 11 | 「背景分布來自引擎不是 UI 重算」→ `f7_17` |
| `f8_ruler` | 17 | 5 | 與 `f8_advanced`／`f8_calibrate` 的「切換卡片要清乾淨」合成一支參數化的 `test_ui_stale_state.py` |
| `f7_11_roi` | 16 | 9 | region-check 一組 → 新 `test_ui_region_check.py` |
| `f11_enhance_panel` | 16 | 7 | 七條「面板不能捏造數字」→ `f7_17` |
| `f22_decide_panel` | 16 | 11 | 四條純 `summarize()`（`bin_purity` 別處沒有）→ `test_export_report.py` |
| `f8_ui_polish` | 14 | 6 | 拖動位置存活 2、場景長大 1 → `test_ui_canvas.py` |
| `f8_advanced` | 10 | 5 | `test_every_card_can_declare_advanced_rows` → **`test_card_invariants.py`** |

### D. 大部分刪（10 支，106 條 → 留 33）

`f7_19_wiring`(22→5)、`f7_18_streams_as_nodes`(14→5)、`f7_24_layout`(12→2)、
`f13_layout`(11→4)、`f11_channel_map`(10→2)、`f13_chrome`(7→3)、
`f11_tiff_stack`(7→2)、`f14_input_on_the_card`(8→3)、`f7_15_reading_load`(8→3)、
`f8_calibrate`(7→4)。

共同形狀：釘住一輪設計的像素／文字／widget 存在性。`f13_layout` 的 docstring
自己就是驗收紀錄（「起點是實測（1600×1000 的視窗）：中欄只有 551px 寬」）。

⚠ `f13_layout` 有一條**測試衛生**的不變量必須留：
`test_saved_sizes_are_never_restored_inside_the_tests` —— 少了它，一次手動拖過
的分隔線會漏進 CI，版面斷言從此時好時壞。

### E. 整支刪（3 支，27 條 → 留 3）

| 檔 | 條 | 為什麼 |
|---|---:|---|
| `f7_10_route_edges` | 6 | **它驗收的功能已經被撤掉了**（docstring：「使用者實測半個月後退掉它：『會混淆』」）。剩下六條只是再宣告一次它不在，而另外三個檔案也都這麼做 |
| `f7_14_canvas_flow` | 9 | 同上：F7-18 拿掉了輸出埠的「+」，而 `plus_at`／`plus_anchors_local` **在 `d4t/` 裡根本不存在** —— 那條斷言不可證偽。留 1 條（zoom 夾住上下界）搬去 `test_ui_canvas.py` |
| `f21_expr_picker` | 12 | 12 條裡 10 條會隨 Phase 3 死掉（見 §5）|

> ⚠ **`f7_14` 要救的是兩條，不是一條**（B2 動手時量到的，2026-08-27）。
> 除了 zoom，`test_a_repeated_card_shows_which_one_it_is`（同一張卡加第二次，
> 副標帶出 `denoise2 · …`）**也是全 repo 唯一的守門人**：把 `canvas.py` 的
> `if step_key and self.node_id != step_key` 關掉，64 支 UI 測試裡只有它會紅。
> 這一份第一版憑 grep 判斷「重複的卡片副標」有別人蓋到 —— **沒有**。
>
> **一條測試該不該刪，grep 說了不算。** 唯一算數的證據是把 bug 放回去看誰紅，
> 而那件事只有動手那一批做得到。所以 B3–B5 的每一條「刪」都要在動手時重驗，
> 這一份的 keep 數字是**下限不是答案**。

---

## 4. ⚠ B0：那支空轉的測試背後是一個**演算法**問題

使用者定調「現在修（獨立一個小 PR）」。動手之後發現**修不動**，理由要寫下來。

### 4.1 症狀：一支恆綠、零斷言的測試

`f7_12::test_a_blurred_stack_is_called_out_not_just_scored`：

```python
    dlg.cell = algo_template.build_golden_cell(big_image(), px=PERIOD + 7, py=240)
    if dlg.cell.ghosting < 40.0:          # ← 實測 ghosting = 90.27
        assert "blurred" in dlg.summary()  # ← 從來沒執行過
```

它守的正是那個檔案 docstring 點名的災難：**週期估錯 → 疊出來糊掉 → 每一顆都
對錯，而畫面上不會有錯誤訊息**。

### 4.2 修不動的原因：那個分數量的不是「疊得準不準」

`template.py:110` 的註解說 `ghosting` 是「0–100，越高越銳利（**疊得越準**）」。
但 `golden.ghosting_score` 算的是**疊完那張圖的 Laplacian 變異數** —— 也就是
「這張圖銳不銳利」，跟「那些格子有沒有對齊」是兩件事。

實測（合成條紋圖，週期 40）：

| 對比 | 正確 px=40 | **半週期錯 px=60** | 38–61 全掃的最低分 |
|---:|---:|---:|---:|
| 1.00 | 99.99 | **100.00** | 65.40 |
| 0.50 | 92.91 | **96.67** | 36.55 |
| 0.25 | 56.76 | **78.35** | 25.74 |
| 0.12 | **31.54** ← 會被說「blurred」 | 48.97 ← 被說沒事 | 22.30 |
| 純雜訊（完全沒結構）| — | — | **22.21** |

**它不只是不敏感，在這份內容上是反過來的**：錯得最離譜的半週期偏移分數**比
正確的高**；而對比低的正確模板反而會拿到「the stack looks blurred, which
usually means the period was measured wrong」這句話。分數其實在量**對比**。

> 這正是這個 repo 一直在獵的那個形狀：**跑得完、有數字、而且是錯的**。
> 而那支空轉的測試就是沒有人發現它的原因。

### 4.3 ⚠ 這一節原本寫錯了兩處 —— F40 量完之後改寫

**原文說「`period.py:445` 是週期候選的排序，所以週期估測本身照銳利度在挑」。
那是錯的**，而且錯在兩個方向。留著原本的判斷會做出一個範圍太大的改動，
所以把量到的東西寫在這裡（完整版見
[`F40-stack-agreement.md`](F40-stack-agreement.md)）：

| 原本寫的 | 實測 |
|---|---|
| `period.py:445` 排的是**週期** | **不是。** 那一行在 `choose_origin` 裡，週期是呼叫端固定的，它排的是**相位**。`estimate_period` 走自相關，`golden.py` 一行都沒碰 —— 擬真圖上實測它給的 px=28 是對的 |
| 所以「`estimate_period` 的行為會變」 | **不會。** 兩者沒有呼叫關係 |
| （沒提到）| `refine_period` / `candidate_periods` **零個 production 呼叫者**。而 `refine_period` 實測會從 26 走到 20（真值 28）—— 真的壞，但是死碼。**使用者定調「刪掉」，2026-08-27 刪了**（`docs/plans/F40-stack-agreement.md` §8）|
| （沒提到）| `choose_origin` 的目標函數**構造上就近乎平的**：週期固定時換相位＝疊出來的圖循環位移，而 Laplacian 變異數對循環位移幾乎不變。`template.py:18-23` 早就寫著，而 `anchor_cell` 事後用地標重新決定相位 |

所以真正活著的缺陷**只有** `template_dialog.py:760` 那個絕對門檻。

### 4.4 結論（原本的三個選項有兩個是錯的）

原本列了 (a) 連 `period.py` 一起改／(b) 只修對話框／(c) 只記錄，並建議 (b)
「因為 `period.py` 風險大」。**範圍的結論對，理由是錯的** —— `period.py` 那一半
根本不在週期估測的路徑上，而該放過 `choose_origin` 的真正理由是它的目標函數
本來就近乎平的。

實際做的（F40）：新增 `golden.stack_agreement`（無量綱、扣掉 `1/n` 地板），
對話框的警示改掛在它上面，`ghosting_score` / `choose_origin` /
`estimate_period` **一行都沒動** —— 所以 `test_period_golden` 與
`test_roi_template:91` 一條都沒紅。

> **一個「先問再做」的判斷，理由錯了照樣會得到對的範圍 —— 但下一次就不會了。**
> 寫下來的是量出來的東西，不是當時的直覺。

---

## 5. 與 Phase 3 的相依

Phase 3 要刪 `feature_math` / `feature_fill`：

1. **`f21_expr_picker` 12 條裡 10 條會死**（`_form()`／`_fill_form()` 直接
   `get_step("feature_math")`）。先把
   `test_a_card_does_not_offer_its_own_output`（`include_upto=False` 的唯一
   守門人）救去 `test_viewmodel.py`。
2. **`f16_stages::test_the_absorbed_algo_cards_never_read_an_image_stream`
   會變成安靜的空轉。** 實測：`GROUP_ALGO` **現在已經零張卡**，整個迴圈只靠
   `key in ("feature_math","feature_fill")` 在跑；那兩張刪掉之後迴圈本體再也
   不會執行，而測試照樣綠。**跟 §4.1 同一個形狀，要在 Phase 3 一起刪。**
3. `f16_stages::test_the_stages_are_in_the_order` 把 `"adc"` 釘在七段清單裡，
   而 Phase 3 之後那一段零張卡。**留不留目前只有這條斷言寫著答案** ——
   使用者 2026-08-27 定調：**Phase 3 開始時再決定**，跟 `GROUP_ALGO` 一起問。

---

## 6. 批次（一批一個 PR）

| 批 | 內容 | 條數 | 風險 |
|---|---|---:|---|
| **B0** | ⚠ **卡住了，等 §4.4 的決定** | — | — |
| **B1** | ✅ **2026-08-27 做完。** A 組六支改名 ＋ 一起改文件。測試程式碼一行不動（只有每一支開頭那行 F 編號註記換成「常駐 ＋ 從哪個舊名改來的」）。動手時修正了兩個少了 `test_ui_` 前綴的新名（見 §3 A 底下那一段）| 0 | 低。先做，它把「哪些是常駐」變成看得出來的 |
| **B2** | ✅ **2026-08-27 做完 E 組那一半**：`f7_10`（6 條）與 `f7_14`（9 條）整支刪，救兩條進 `test_ui_canvas.py`。**D 組那一半退回去了** —— 見下 | 15 刪、2 救 | 低（逐條驗過「把 bug 放回去誰紅」）|
| **B2b** | ✅ **2026-08-27 做完。** D 組裡**純重複**的 —— 逐條找到蓋掉它的那一支才刪。實得 **8 條，不是 ~25**（見 §8）| 8 | 低 |
| **B3** | C 組的「搬進 `test_card_invariants.py`／`test_ui_widgets.py`／`test_ui_canvas.py`」 | ~30 搬 | 中 |
| **B4** | C 組新開的三個常駐檔 ＋ 對應刪除 | ~120 | 中高（碰到四個零覆蓋模組）|
| **B5** | D 組其餘刪除 ＋ 文件收尾 | ~80 | 中 |

**B4 之前不要動 `f7_12`／`f8_cross`**：它們是 `cell_canvas`／`region_check`
的唯一覆蓋。

### 為什麼 B2 拆成兩半

原本的 B2 是「E 組整支刪 ＋ D 組裡**純重複的**」。動手時發現這一份**沒有留下
「哪幾條是純重複的」那張表** —— §3 D 只有每一支的 keep 數字（`f7_19_wiring`
22→5……），而數字不是清單。照數字刪等於挑自己看得順眼的那幾條刪，那不是
「確認它保護的行為沒有被別的測試蓋到」（§7）。

而 `f7_14` 那一條剛好證明了憑印象刪的代價：這一份憑 grep 判斷「重複的卡片副
標」有別人蓋到，**實測只有它自己**。D 組 106 條要逐條驗，那是一批的工作量，
不是一批的尾巴。所以拆成 B2b。

## 7. 驗收

- **清單先過使用者** ← 這個 PR 停在這裡
- 之後每一批：核心＋UI 兩批測試全綠
- CI 時間不變差（目前 UI 逐檔 244 秒）
- 刪掉一條之前，確認它保護的行為**沒有**被別的測試蓋到
- **每一批都要跑一次「把 bug 放回去會紅」** —— 搬過去的不變量要在新家證明
  它還在守

---

## 8. B2b 的結果：「純重複」只有 8 條，不是 ~25

§6 估 D 組裡有 ~25 條純重複的。**逐條找蓋掉它的那一支之後，實得 8 條。**

| 刪掉的 | 蓋掉它的（都是會活下來的檔） |
|---|---|
| `f7_19::the_second_line_actually_appears_on_the_canvas` | `f9_9::the_canvas_draws_one_line_per_edge`（多問了每條線的 `out_name()`）|
| `f7_19::wiring_the_same_stream_twice_changes_nothing` | `f9_9::the_same_line_twice_is_still_a_no_op`（多問了狀態列）|
| `f7_19::route_order_has_no_lines_at_all` | `canvas_truth::the_canvas_never_lies_about_where_a_card_gets_its_data`（400 組隨機接／剪的性質測試）|
| `f7_19::a_line_can_be_cut_where_it_is` | `test_ui_canvas_cut_button.py` 整支八條 |
| `f7_18::dragging_from_the_ref_port_wires_ref_into_the_card` | `f7_19::wiring_a_second_stream_adds_it_instead_of_replacing`（它的 docstring 自己指過去）|
| `f7_18::a_second_line_between_the_same_two_cards_is_not_refused` | 同上 |
| `f7_18::adding_from_the_library_lands_after_the_selected_card` | `canvas_one_line_per_input::the_new_card_still_lands_after_the_selected_one` |
| `f13_chrome::the_data_entries_are_not_on_the_toolbar_any_more` | `f14::the_toolbar_carries_no_data_entry` ＋ `f14::the_empty_state_still_offers_every_source` |

四個「把 bug 放回去」都驗過，而且**紅的是活下來的那一支**：

| 放回去的 bug | 誰紅 |
|---|---|
| `cut_hit` 永遠回 False | `canvas_cut_button` 4 條 |
| `add_card_after` 排到最後面 | `canvas_one_line_per_input` 1 條 |
| `image_keys` 的第二條線改成取代 | `f9_9` 2 條、`f7_19` 5 條 |
| 副標的 id 前綴關掉（B2 那條）| `test_ui_canvas` 1 條 |

### 為什麼差這麼多

**D 組的共同形狀是「釘住一輪設計的像素／文字／widget 存在性」，而那種斷言多半
是獨一無二的** —— 它該走是因為它是**驗收快照**，不是因為有人重複。「重複」與
「快照」是兩個不同的理由，B2b 只做得了第一種。剩下的 ~70 條屬於 B5，而那一批
要一條一條回答「這是不變量還是那一輪交付了」，不是找對照。

### ⚠ 留給 B3／B5 的一個地雷

`f13_layout::selecting_a_card_opens_it_again` 與
`f13_layout::the_settings_pane_gives_the_space_back_when_nothing_is_selected`
的斷言**整組**在 `f8_ui_polish::the_canvas_is_the_top_block_and_settings_get_the_rest`
裡。三條都不在 B2b 裡刪，因為 `f8_ui_polish` 是 C 組、而它那一條不在 §3 C 的
救援清單上 —— **兩邊各自照自己的清單刪，這個行為就一起消失了。**
B3／B5 動到這兩支任何一支時，先確認另一邊還在。

### 方法：逐條測試的行覆蓋（B3–B5 可以再用）

`pip install coverage pytest-cov`（**家用機的開發工具，不進 `requirements.txt`**
—— 公司機那條 stdlib-only 的線不動），然後逐檔一個行程收：

```bash
for f in tests/test_ui_*.py; do
  COVERAGE_FILE=cov/.coverage.$(basename $f .py) QT_QPA_PLATFORM=offscreen \
    python -m pytest -q "$f" --cov=d4t --cov-context=test --cov-report=
done
python -m pytest -q --ignore-glob="*test_ui_*" --cov=d4t --cov-context=test  # 核心批也要
coverage combine        # 合起來之後 CoverageData.contexts_by_lineno() 問「這一行誰踏過」
```

**只有一條測試踏過的行 = 刪掉就沒人踏了**，那是「先看一眼」的清單。

⚠ **行覆蓋不是斷言覆蓋。** 跑到那一行不代表有問它對不對 —— 這個 repo 有過一支
恆綠零斷言的測試（§4.1），它的行覆蓋很漂亮。所以覆蓋只當篩子，判決仍然是
「把 bug 放回去誰紅」。
