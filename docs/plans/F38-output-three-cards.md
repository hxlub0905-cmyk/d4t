# F38 — Output 卡七張收成三張

**狀態：收斂（2026-08-26）。**

| # | 題目 | 狀態 |
|---|---|---|
| 1 | 四張報表卡 ＋ Excel 折進 `output_report` | ✅ |
| 2 | `output_char` 只改 label（`Write comparison`） | ✅ |
| 3 | 遷移：內容逐位元組相同、路徑依對照表位移 | ✅ |
| 4 | `docs/ARCHITECTURE.md` 的三段分色（過期一年的一句話） | ✅ |

使用者交辦的工作單有四個 Phase，規矩是**一件一個 PR**。這一份是 Phase 1
（Output 收斂）＋ Phase 4（文件修正，工作單明說可以併進任一個 PR）。
Phase 2（F 編號測試審一輪）與 Phase 3（刪 `feature_math` / `feature_fill`）
另外開。

---

## 0. 使用者的原話與這一輪定調的兩件事

> 七張裡有五張在回答同一個問題，收成三張。

動手之前有兩件事工作單沒有定，而它們會改變做出來的東西，所以先問了：

| 題目 | 定調 |
|---|---|
| 合併後的產物形狀 | **一律資料夾**（`PATH="folder"`） |
| `output_csv` 的 `include_features` | **跟著進來，列為 advanced** |

### 0.1 第一題為什麼一定要問

合併之前七張卡分成**兩種形狀**：

| 形狀 | 哪幾張 |
|---|---|
| 一格路徑＝**一個檔案**（`PATH="path"`） | `output_csv`、`output_html`、`output_boxplot`、`output_report`(Excel)、`output_klarf` |
| 一格路徑＝**一個資料夾**（`PATH="folder"`） | `output_bundle`、`output_char` |

而 `wants_folder()` 是**類別層級的常數**（`_OutputStep:133`）。五張折成一張，
這兩種形狀必須併成一種 —— 沒有「兩個都保留」這個選項，除非加一格開關。

**代價因此是使用者取的檔名。** 工作單原本的驗收條件寫著「跑得出跟改動前**逐
位元組相同**的輸出」，而那在「一律資料夾」之下不可能成立：資料夾裡那幾個名字
是寫死的（F37 的理由：一份報表換一台機器打開還是同一個形狀）。所以那一條改寫
成 **「內容逐位元組相同，路徑依一張明列的對照表位移」**，而那張表是回報項目。

### 0.2 第二題推翻了 F37 剛寫下的結論，而變的不是理由是題目

F37 B2 §1 查證後決定**不要**把 `include_features` 補到寫資料夾的卡上，理由是
「`output_csv` 是交付物、資料夾裡那份是報表的隨附檔」，還特地寫下
「下一個看到這裡的人會想統一它，而那是加旋鈕不是收斂」。

**那個理由現在仍然成立，變的是題目。** `output_csv` 這張卡不存在了，所以問題
從「要不要**加**一格」變成「那一格要不要**跟著它的卡一起消失**」—— 而讓它消失
會拿掉一個真的有用的用途（乾淨的交付物），代價比多一格大。

> **一個「查證後不動」的結論失效，不一定是因為當初算錯了。** 它可能是因為它
> 依賴的那個事實（有兩張卡）沒了。所以回去改那段註解的時候，要寫的是**題目
> 換了**，不是「以前想錯了」。

---

## 1. 合併後的 `output_report`

`key` 留 `output_report`（工作單指定），而它**意思換了**：以前是「寫一個
Excel 檔」，現在是「寫一個資料夾，Excel 是裡面的一個勾」。

`contents` 從四個勾長成六個，多了 `excel` 與 `boxplot`。

### 1.1 `CONTENTS` 與 `DEFAULT_CONTENTS` 是兩份，而那不是整齊癖

「勾得到什麼」（＝驗證表）與「預設勾什麼」寫成同一份的話，加進那兩個新選項的
那一刻，每一份**沒有寫 `contents` 這個鍵**的舊 `output_bundle` recipe（出貨那
份就是）都會安靜地多寫兩個檔案 —— 因為「鍵不在」的解讀是「還沒設過＝用預設」。

同一個形狀 F18 踩過一次（`COMPARE_METRICS` 同時是清單與驗證表，
`docs/PITFALLS.md` 第 75 列：「列什麼」與「算得出什麼」要是兩份）。

另外兩個不預設勾，各自還有一個自己的理由：

* **Excel 要 `openpyxl`**，而公司機不一定裝得起來（`AGENTS.md` §1）。預設開啟
  等於把一個環境問題變成每一份 recipe 都會看到的一句警告。
* **box plot 要有判定樹或一份指定的清單**，兩個都沒有時它講一句話 —— 預設開啟
  等於對每一份沒有樹的 recipe 喊狼來了（推廣鐵則）。

### 1.2 `features` → `plot_features`：改的是鍵，不是使用者看到的字

box plot 的 `features` 跟併進來的 `include_features` 在同一張卡上，兩個名字都
以「features」開頭而意思完全不同。`label` 逐字沒變（`Numbers to plot`），所以
**畫面上一個字都沒動** —— 那正是 `ParamSpec.label` 存在的理由（F7-9）。

⚠ 型別必須留著 `feature_keys`：特徵改名走的是**型別**不是卡片清單
（`_rename_in_node_params`，F37 A2 建的第四條路）。改成 `str` 的話那一格會安靜
地漏掉，症狀是「圖照畫，只是畫的不是你在判的那個數字」。

### 1.3 合併帶進來一個以前不存在的壞法

分成五張卡的時候「Excel 寫不出來」只毀掉 Excel 那張卡。併成一張之後，
**一個 `raise` 會把報表、CSV、圖、recipe 一起丟掉** —— 使用者少的不是一個檔案，
是整份報表。

規則因此是：**一樣失敗就是一句話，不連坐**；勾了的全部失敗才 raise（那時候這
張卡真的什麼都沒做，而「跑完了但資料夾是空的」比一個錯誤訊息糟得多）。

而 raise 的訊息要帶著**那一樣自己的理由**。只勾了一樣的時候（＝每一份從舊的單
檔卡遷移過來的 recipe），那句話跟合併之前逐字相同 —— 包一層
「something went wrong」上去的話，使用者拿到的是一句**沒有下一步**的話。
為此 `StepError` 多了一個 `.detail`（訊息不含 `[key]` 前綴的那一份）：
一張卡在自己內部攔到另一段的 `StepError` 再往外報時，`str(e)` 會把前綴疊第二次。

---

## 2. 遷移

`_migrate_folded_output_cards`，接在 `_migrate_output_image_into_bundle`
之後 —— **遷移鏈要一段一段接**：`output_image` → （F37）`output_bundle` →
（F38）`output_report`。寫一條 `output_image` 直達的捷徑只有舊檔案會走到，
永遠不會有人在上面測試。

也**必須在 `_compare_feature_renames` 之前**：特徵改名是靠
`REGISTRY.get(node.step)` 找型別的，留在舊 key 上的節點對它是隱形的。

### 2.1 判準：兩種節點的「舊東西」不一樣

| 節點 | 判準 | 換完之後 |
|---|---|---|
| 被折的四張 | `node.step` 是舊 key | 不再命中 ✓ |
| `output_report` 自己 | key 沒變 → 問**舊的參數名還在不在**（`"path" in params`） | `path` pop 掉了 ✓ |

第二列是唯一能用的判準（同 `_FOLDED_CARD_RENAMES["roi_reference"]` 那一支）。
**不准**寫成「`folder` 不在就補」—— 那分不出「舊檔案」與「新 recipe 剛好還沒填
路徑」，而 `to_json_dict → from_json_dict` 一旦不是 identity，`workers=1` 與
`workers=2` 會算出不同的分數（`docs/PITFALLS.md` 第 71 列，實測 glv_max 50 vs 43）。

> ⚠ **量過一件事，而它改了一句註解。** 把判準換成錯的那個寫法之後，
> `test_a_recipe_already_on_the_new_card_is_left_alone` **照樣綠**（它填了
> `folder`）—— 紅的是
> `test_an_unconfigured_new_card_does_not_get_a_folder_invented`。
> 第一版的 docstring 寫著「這支會紅」，而那是假的。
> **「把 bug 放回去會紅」要指名是哪一支，而那句話本身要驗過。**

### 2.2 路徑對照表

| 舊 | 新 | 實際寫出 |
|---|---|---|
| `output_csv path=/x/my.csv` | `folder=/x, contents=table` | `/x/defects.csv`（**檔名換了**）|
| `output_html path=/x/page.html` | `folder=/x, contents=report` | `/x/report.html`（**檔名換了**）|
| `output_boxplot path=/x/spread.html` | `folder=/x, contents=boxplot` | `/x/spread.html`（**一樣**）|
| `output_report path=/x/book.xlsx` | `folder=/x, contents=excel` | `/x/report.xlsx`（**檔名換了**）|
| `output_bundle folder=/x` | key 換掉 | `/x`（一個字都沒動）|

`os.path.dirname(path) or "."` 的 `or "."` 不能省：`path="report.html"`（沒有
目錄的相對路徑）的 dirname 是空字串，而空字串在那張卡上的意思是「還沒填」——
一份跑得動的 recipe 會變成一條設定錯誤。

### 2.3 `contents` 一律明寫

被折的四張各自寫死自己那一個值；`output_bundle` 沒寫過那一格的也補上當時的四
個。理由是把**「舊檔案的行為」跟「新卡片的預設」脫鉤** —— 之後有人動了預設，
那些 recipe 不會跟著改。

---

## 3. 驗收

### 3.1 逐位元組：一支工具，五張舊卡，七個案例

寫了一支 `--before` / `--after` / `--diff` 的工具，在**改動之前**先跑一次舊
code 留下每個檔案的內容雜湊。七個案例（五張卡＋`include_features` 開關兩種＋
`title` 有無）、15 個檔案，全部相同。

兩樣東西要先正規化掉，**而兩樣都不是這次改動造成的**：

* **`.xlsx` 比每一格的值，不比 bytes。** openpyxl 把寫檔當下的時間戳寫進
  `docProps/core.xml`，同一份資料連跑兩次 bytes 就不一樣了
  （`test_export_parity.py` 為了同一件事也是比 cell）。
* **`recipe.json` 記的是產生這一批的 recipe，而 recipe 真的被遷移換掉了**
  —— 所以它「應該」不一樣。要問的是**只有遷移那一段不一樣**，所以 before 那份
  也送進 `from_json_dict` 走一次遷移再比。

> 第二點第一版寫成字串比對（把工作目錄的路徑 replace 掉），而它**漏了**：
> before 的路徑是絕對的、重算 digest 時傳進去的 root 是相對的。改成抹掉
> **參數值**之後就對了。**要抹掉的是一個值的話，不要用字串比對去抹。**

### 3.2 把 bug 放回去會紅 —— 六個，逐一驗過

| # | 放回去的 bug | 紅的是 |
|---|---|---|
| ① | 判準改成「新東西不在」 | `test_an_unconfigured_new_card_does_not_get_a_folder_invented` |
| ② | `DEFAULT_CONTENTS = CONTENTS` | `..._gets_the_old_four_written_in` ＋ `..._not_on_by_default` |
| ③ | `features → plot_features` 的改名漏掉 | `test_the_box_plot_numbers_move_to_their_new_box` |
| ④ | `or "."` 拿掉 | `test_a_bare_file_name_does_not_become_nowhere_to_write` |
| ⑤a | 泛用 `except` 改回 `raise` | `test_an_ordinary_write_failure_does_not_connect_either` |
| ⑤b | `ImportError` 那一支改回 `raise` | `test_one_thing_failing_does_not_take_the_rest_of_the_folder_with_it` |
| ⑥ | `.detail` 換回 `str(e)` | `test_when_everything_asked_for_fails_the_card_says_why` |

> ⚠ **⑤ 一開始只有一支測試，而它抓不到 ⑤a。** 那支測試用 monkeypatch 讓
> `write_excel` 丟 `ImportError`，於是它走的是**專門那一支 except**；把泛用的
> 那一支改回 `raise`，它照樣綠。補了一支走 `OSError` 的才蓋到。
> **一條規則有兩個實作分支的時候，一支測試只證明得了一支。**

### 3.3 `test_card_invariants.py` 碰不到 Output 卡

工作單第 5 點寫著「那六條會自動套用到新卡上，不必手動加」。**那不成立**：
`CARDS` 過濾的是 `not c.is_batch`（`:199`），而每一張 Output 卡都是 `is_batch`
—— I5（參數推到上下界不炸也不吐 NaN）走的是 `run_defect`，而這張卡根本不在那
條路上。所以那件事在 `tests/test_output_fold.py` 裡自己問了一次，走
`run_batch_steps`，六個勾全開、每個有界參數各推到它宣告的兩個端點。

### 3.4 反空轉的下限下修了兩個

`test_batch_steps::test_the_whole_output_section_is_end_points` 的
`len(section) >= 5` 與 `test_ui_output_band` 的 `>= 4`，在三張卡之下是假的。
**下修並寫下為什麼**，不是拿掉 —— 同 `test_card_invariants` 在 `snr_map` 刪掉
那天把 12 改成 11 的做法。拿掉的話，那支測試哪天一張卡都沒有也會是綠的。

---

## 4. Phase 4：一句過期一年的話

`docs/ARCHITECTURE.md:79` 寫著「UI 三段分色（影像=藍／算法=橙／判定=紫）」，
而它在 **F7-9 就過期了**（試用回饋：「圖示很不錯，但太多都同個顏色」）。
改成描述現況並指向 `theme.group_hex` 的 docstring 當唯一出處。

⚠ **工作單說 `README.md` 也有這一句，實際上沒有。** grep 過了：那句話只在
`ARCHITECTURE.md` 出現一次。`README.md:49` 講的是**引擎**分三段（快取切點與驗證
順序），那句話仍然正確，所以沒有動它。

> **交辦單上的一個「兩處都要改」，值得先確認真的有兩處。** 照著改的話，這裡
> 會多出一段描述現況的文字掛在一句本來就對的話旁邊。
