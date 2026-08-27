# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄按月封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| **2026-08-19 起**（第十六輪～）| 這個檔案（下面）—— 改名 d4t、F12 區域線、F13 UI、F14 入口搬進卡片、F15 配對分析、F16 畫布的八段、F17 純 DAG 引擎、F18 GLV、F19 CD、F20–F25 多類別 ADC 與判定樹、F26/F27 判定與 Results 面板、F28–F30 位置／報表／Region 收卡、F31/F32 逐框比較、**F33 EBI↔API characterization、F34/F35 存檔 recipe 與出貨的 recipe、F36 box plot** |
| 2026-08-07 ～ 08-18（第十五輪以前）| [`docs/history/2026-08.md`](docs/history/2026-08.md) —— F8 純規則 ROI、畫布 n8n 化、Phase 1 收斂、F10、Phase 2 的 Input／Enhance／Region 三段 |
| 2026-07 | [`docs/history/2026-07.md`](docs/history/2026-07.md) —— M0–M7、F7-9…F7-24 前半、兩台機器與搬運通道的成形 |

**這一次的切點不是月份，是「上一次合併進 main 的那一輪」**（第十五輪）——
所以封存的那一份等於「main 到那時為止的紀錄」，這裡留下的正好是這條分支做的事。

封存不是整理癖：這個檔案**只增不減**，而它跟著整包被複製進公司機。
包的大小**不是限制**（2026-08-17 使用者確認直接複製 raw，見 `AGENTS.md` §2）——
封存現在是為了 diff 乾淨與公司機用不到的東西不佔體積，不再是為了那道 1 MB 的線。

---

## F39-B1：六支常駐測試改掉 F 編號的檔名（2026-08-27）

F39 清單的第一批。A 組那六支**不是**當初那一輪的驗收快照，是常駐的不變量套件
（逐張套用到 registry、`inspectors.py` 唯一的守門人、`ambiguous-input` 全 repo
獨家……），只是檔名帶著 F 編號 —— 於是每一次「這支還要嗎」的判斷都要重讀一次
檔案。改名把「哪些是常駐」變成**看得出來的**。

| 舊 | 新 |
|---|---|
| `test_ui_f10_canvas_reality.py` | `test_ui_canvas_invariants.py` |
| `test_ui_f7_17_inspectors.py` | `test_ui_inspectors.py` |
| `test_ui_f7_16_safety_net.py` | `test_ui_undo_close_and_stop.py` |
| `test_ui_f16_run_all.py` | `test_ui_write_only_on_run_all.py` |
| `test_ui_f20_panel_truth.py` | `test_ui_panel_truth.py` |
| `test_ui_f9_7_user_draws_the_lines.py` | `test_ui_canvas_one_line_per_input.py` |

測試程式碼一行沒動（113 條逐檔全過）。動的是每一支開頭那行 F 編號註記 ——
換成「常駐 ＋ 從哪個舊名改來的」，這樣 `SESSION_LOG` 裡那些用舊名寫的紀錄還
grep 得回來。使用者定調「改名時一起改文件」，所以 `docs/PITFALLS.md:41`、
`docs/ROADMAP.md:69`、`docs/plans/F11-phase2-features.md:2674` 與
`tests/conftest.py`／`tests/test_ui_save_recipe.py` 兩處 docstring 交叉引用同一
批改掉。

### ⚠ 清單上有兩個新名字是錯的，而錯法只有動手時看得到

F39 §3 A 寫的是 `test_canvas_invariants.py` 與 `test_canvas_one_line_per_input.py`
—— **少了 `test_ui_` 前綴**。那兩支都 `QApplication()` ＋ `StudioWindow()`，
而 **CI 就是照那個前綴分批的**（`ci.yml:72` 核心批 `--ignore-glob="*test_ui_*"`、
`:82` UI 批 `tests/test_ui_*.py` 逐檔一個行程）。照清單改下去，它們會同時掉出
UI 批、掉進那個跑 2,400 條的核心行程 —— 正是 `AGENTS.md` §5 量過的 Qt 記憶體
累積（整套一個行程 1:39:09 vs 逐檔 7 分鐘）。

> **在這個 repo 裡「只是改個名字」不是零風險的操作，因為檔名是 CI 的分批依據。**
> 而這條約束沒有任何測試在守 —— B1 之後也還是沒有，它靠的是動手的人知道那個
> glob。清單上寫「風險 0」的那一批，風險不是 0。

---

## F40：把「疊得準不準」量對 —— 一支空測試底下的演算法問題（2026-08-27）

F39 的清單裡有一支恆綠、零斷言的測試，使用者定調「現在修」。**動手量之後，
那支測試底下是一個演算法問題，而 F39 §4.4 對它的描述有兩處是錯的。**
使用者：「以你發現，你認為對的做～計畫書可能會錯。」

計畫書：[`docs/plans/F40-stack-agreement.md`](docs/plans/F40-stack-agreement.md)。

### ① 一個絕對門檻掛在一個沒有正規化的量上

`TemplateDialog` 的「疊出來糊掉了」警示掛在 `ghosting < 40`，而 `ghosting` 是
`cv2.Laplacian(疊完那張圖).var()` 的飽和映射 —— 它量的是「這一張圖有多少邊緣
能量」，看不到疊進去的那幾格，而且跟著對比、雜訊、格子大小一起動。

實測（條紋圖，真值 40）：對比 0.25 時**正確**的週期只拿 6.8 分（被說 blurred），
高雜訊下**錯**的週期拿 76.1 比正確的 68.4 還高（被放行）。而最能說明問題的一個
數字：**純雜訊（完全沒有東西可疊）σ=60 拿 99.4 / 100。**

> **看起來像百分比的東西不一定是百分比。** 要跟固定門檻比之前，先問「這個量
> 換一張圖還是同一個意思嗎」。

修法是加一個真的無量綱的量（`golden.stack_agreement` ＝
`var(疊完)/mean(var(單格))`，扣掉 `1/n` 的地板），**不是**去調那個 40。
`ghosting_score` 一行都沒動 —— 它老實在量銳利度，錯的是「銳利 ⇒ 對得準」那句
推論。所以 `test_period_golden` 與 `test_roi_template:91` 一條都沒紅。

### ② 那個公式我驗了兩次，而第一版是錯的

第一版把 `tile_coords` 回的 `(x, y)` 拆成 `(y, x)`，於是「零雜訊 ＋ 正確週期」
只拿到 **0.049** 而錯的拿 0.119。抓到它的是那條「完美週期應該 ≈ 1.0」的健全性
控制。

> **提出一個指標之前，要先有一個它必須通過的已知答案。** 沒有那條控制，一個
> 反過來的指標就會被當成修好了交出去 —— 而它會比原本那個更難發現。

### ③ 三種壞法，三個機制 —— 而我第一版的門檻是從單一圖案推出來的

計畫書第一版寫「所有錯的週期都是 0.000」。那是**只在正弦條紋上量的**；換成
方波條紋，半週期是 **0.69**。對稱性高的圖案上，半週期的格子彼此真的蠻像 ——
0.69 是誠實的回答，不是漏抓。

量完之後分工是清楚的：`stack_agreement` 抓「不成比例的週期」與「沒有東西可
疊」；`cell_self_period` 的 k× 提示抓「cell 是 k 倍」（而 2× 的 cell 是**合法
的**，使用者要得到）；半／1.5 倍屬於 `estimate_period` 的諧波修正那一層。

> **一個從單一合成圖案推出來的門檻，換一種圖案就不成立。** 門檻的說明裡要寫
> 它「抓什麼、不抓什麼、不抓的那些誰抓」。

### ④ F39 §4.4 錯在哪（兩處，都往相反方向）

* 「`period.py:445` 排的是**週期候選**，所以週期估測本身照銳利度在挑」——
  **不是**。那一行在 `choose_origin` 裡，週期是呼叫端固定的，它排的是**相位**。
  `estimate_period` 走自相關，`golden.py` 一行都沒碰（擬真圖上實測 px=28 正確）。
* 「建議只修對話框，因為 `period.py` 風險大」—— **範圍對、理由錯**。該放過
  `choose_origin` 的真正理由是它的目標函數**構造上就近乎平的**（週期固定時換
  相位＝疊出來的圖循環位移，而 Laplacian 變異數對循環位移幾乎不變），而且
  `anchor_cell` 事後用地標重新決定相位。`template.py:18-23` 早就寫著。

> **一個「先問再做」的判斷，理由錯了照樣會得到對的範圍 —— 但下一次就不會了。**

### ⑤ 順手量到、先不動、然後使用者說刪掉

`refine_period` / `candidate_periods` **零個 production 呼叫者**，而
`refine_period` 實測會從 26 走到 20（真值 28）—— 真的壞，但是死碼。
收起來／刪掉是**使用者的決定**（`CLAUDE.md` §5），所以那一輪寫進回報不動手。

**回報之後使用者說「刪掉」，刪了。** 代價這次是零 —— `CLAUDE.md` §5 那張表
說刪掉要付「依賴它的 fixture／黃金值」，而沒有呼叫者就沒有那些東西。
但**留下兩樣比程式碼有用的**：`golden.py` 原地一段註解寫著它為什麼壞
（照銳利度排週期候選，而銳利不等於對得準 —— 不然下一個人會從 CPE 再
vendor 一次同一支），以及 `docs/HANDOVER.md`「尚未回報給原專案的問題」
多了第 4 條（上游大概還在用它，而那是一個安靜的錯誤）。
見 `docs/plans/F40-stack-agreement.md` §8。

**驗收**：核心 2412 passed、UI 64 檔逐檔全過、黃金值三份逐項相同；
三個新不變量各驗過「把 bug 放回去會紅」。**F40 到此收斂。**

---

## F39：F 編號測試審一輪 —— 清單，以及清單底下的一個演算法問題（2026-08-27）

工作單 Phase 2。規矩是「**不要直接動手刪**，先產出一份清單交給使用者」，
所以這一輪的產物是清單本身：36 支 F 檔、605 條測試逐條看過。

清單：[`docs/plans/F39-f-test-audit.md`](docs/plans/F39-f-test-audit.md)。
判定 605 條 → 留 ~323、刪 ~282。

### ① 「F 編號」不是可靠的訊號 —— 六支其實是常駐不變量套件

`docs/plans/F11-phase2-features.md:50` 早就寫著「**F10 的 20 條畫布不變量**會
自動套用到新註冊的卡」。`f10` 是逐張套用到 registry 的性質測試，只是檔名帶
F 編號；`f7_16`／`f7_17`／`f16_run_all`／`f20`／`f9_7` 同樣。
**對它們正確的動作是改名，不是刪。**

> 拿檔名當分類是最省事的判準，而它在這裡是錯的。逐條讀才問得出
> 「這句話是不變量還是那一輪的收據」。

### ② 六條 pitfall 指名了它的守門人 —— 那是契約

`docs/PITFALLS.md` 有六條直接寫著某支 F 測試的路徑（`f7_23` 一支就守三條 Qt
坑）。刪掉那支＝讓一份活文件說謊。所以 B1 改名要**連文件一起改**（使用者
2026-08-27 定調）。

### ③ 找到一支恆綠、零斷言的測試 —— 而它底下是一個演算法問題

`f7_12::test_a_blurred_stack_is_called_out_not_just_scored` 的斷言全在
`if dlg.cell.ghosting < 40.0:` 裡，而實測 `ghosting = 90.27` —— 條件恆為
False、整支零斷言。它守的正是那個檔案 docstring 點名的災難（週期估錯 → 疊出來
糊掉 → 每一顆都對錯，而畫面上不會有錯誤訊息）。

**使用者定調「現在修」，動手之後發現修不動，而理由比那支測試重要得多。**

`golden.ghosting_score` 算的是疊完那張圖的 Laplacian 變異數（「這張圖銳不銳
利」），不是「那些格子有沒有對齊」—— 而 `template.py` 的註解寫的是後者。實測
（合成條紋圖，週期 40）：

| 對比 | 正確 px=40 | **半週期錯 px=60** |
|---:|---:|---:|
| 1.00 | 99.99 | **100.00** |
| 0.25 | 56.76 | **78.35** |
| 0.12 | **31.54**（會被說 blurred）| 48.97（說沒事）|

**不只是不敏感，是反過來的**：錯得最離譜的偏移分數比正確的高；對比低的正確
模板反而被說「the stack looks blurred, which usually means the period was
measured wrong」。那個分數其實在量**對比**。純雜訊得 22.21。

而它餵兩個地方：使用者看得到的那句警示，以及 **`period.py:445` 的週期候選
排序** —— 也就是說週期估測本身是照「哪個看起來最銳利」在挑。

> **一支空轉的測試不只是少一條防線，它是那個 bug 活下來的原因。**
> Phase 2 的價值不在刪掉幾條，在於逐條讀的時候會撞到這種東西。

沒有自己修：那是演算法改動，會動到 `estimate_period`，而出貨的
`patch-dsnr-by-class.json` 走 templateGC。黃金值不受影響（三份 fixture recipe
都沒有 `roi_template`），但工作單說**拿不準的就問**。三個選項寫在計畫書 §4.4，
建議是只修使用者看得到的那一半。

### ④ Phase 3 會讓另一支變成同樣的空轉

`f16_stages::test_the_absorbed_algo_cards_never_read_an_image_stream` 的迴圈
只靠 `key in ("feature_math","feature_fill")` 在跑（實測 `GROUP_ALGO` 現在
**已經零張卡**）。那兩張刪掉之後迴圈本體再也不會執行，而測試照樣綠 ——
跟 ③ 同一個形狀，要在 Phase 3 一起刪。

**Phase 2 的清單到此完成，等使用者確認再分批動手。**

---

## F38：Output 卡七張收成三張（2026-08-26）

使用者交辦的工作單四個 Phase，一件一個 PR。這一輪是 **Phase 1（Output 收斂）
＋ Phase 4（文件修正）**。原話：「七張裡有五張在回答同一個問題，收成三張。」

計畫書：[`docs/plans/F38-output-three-cards.md`](docs/plans/F38-output-three-cards.md)。

結果：`output_report`「Write report」（一個資料夾，六個勾）／`output_klarf`／
`output_char`（只改 label：「Write comparison」）。`output_char` **沒有合**
—— F37 §5.1 那個決定與守著它的測試都原封不動。

### ① 動手之前有兩件工作單沒定的事，而它們會改變做出來的東西

問了才動。兩件都不是「要不要做」，是「做出來長什麼樣」：

* **產物的形狀**：合併之前七張卡分成兩種（`PATH="path"` 一個檔案 / `"folder"`
  一個資料夾），而 `wants_folder()` 是**類別層級的常數** —— 五張折成一張，兩種
  形狀必須併成一種。使用者定調**一律資料夾**。
* **`include_features`**：跟著進來，列為 advanced。

### ② 「逐位元組相同」在這個定調之下不可能成立，所以驗收條件要改寫

工作單寫著「跑得出跟改動前逐位元組相同的輸出」。資料夾裡那幾個名字是寫死的
（F37 的理由：換一台機器打開還是同一個形狀），所以舊的單檔卡遷移過來
**檔名一定會換**（`/x/my.csv` → `/x/defects.csv`）。

改寫成「**內容**逐位元組相同，**路徑**依一張明列的對照表位移」，而那張表進了
遷移的 docstring 與回報。七個案例、15 個檔案，全部相同。

> **驗收條件跟定調衝突的時候，要改的是驗收條件，而且要當場說。** 悄悄放寬成
> 「差不多一樣」的話，那條線就再也回不來了。

### ③ 推翻 F37 一個「查證後不動」的結論 —— 而變的不是理由，是題目

F37 B2 §1 決定不要把 `include_features` 補到寫資料夾的卡上，還特地寫下
「下一個看到這裡的人會想統一它，而那是加旋鈕不是收斂」。

**那個理由現在仍然成立。** 變的是 `output_csv` 這張卡不存在了，所以問題從
「要不要**加**一格」變成「那一格要不要**跟著它的卡一起消失**」—— 而讓它消失會
拿掉一個真的有用的用途（乾淨的交付物）。

> 回去改那段註解的時候寫的是**題目換了**，不是「以前想錯了」。一個查證過的
> 結論失效，多半是因為它依賴的那個事實沒了。

### ④ 合併帶進來一個以前不存在的壞法

五張卡的時候「Excel 寫不出來」只毀掉 Excel 那張卡。併成一張之後，一個 `raise`
會把報表、CSV、圖、recipe **一起丟掉**。

規則：一樣失敗就是一句話、不連坐；勾了的全部失敗才 raise，而訊息帶著那一樣
**自己的理由**（只勾一樣的時候＝每一份遷移過來的舊 recipe，那句話跟合併之前
逐字相同）。為此 `StepError` 多了 `.detail` —— 一張卡在內部攔到另一段的
`StepError` 再往外報時，`str(e)` 會把 `[key]` 前綴疊第二次。

### ⑤ 「把 bug 放回去會紅」驗了六個，而其中兩個的第一版是假的

* **⑤a**：一條規則有兩個 except 分支，而測試只走得到專門那一支。把泛用的改回
  `raise`，那支測試**照樣綠**。補了一支走 `OSError` 的才蓋到。
  > **一條規則有兩個實作分支的時候，一支測試只證明得了一支。**
* **①**：docstring 寫著「把判準寫成『新東西不在』的話，這支會紅」。實測紅的是
  **另一支** —— 這一支填了 `folder`，所以錯的判準碰不到它。
  > **「把 bug 放回去會紅」要指名是哪一支，而那句話本身要驗過。**

### ⑥ 工作單上的三個前提，實際上兩個不成立

照著做的話會做出錯的東西，所以逐一查了：

| 工作單寫的 | 實際 |
|---|---|
| `test_card_invariants.py` 那六條會自動套用到新卡上 | **不會**：`CARDS` 過濾 `not c.is_batch`，而 Output 卡全是 batch。I5 走 `run_defect`，這張卡不在那條路上 —— 自己在 `test_output_fold.py` 問了一次，走 `run_batch_steps` |
| `README.md` 也寫著三段分色 | **沒有**。那句話只在 `docs/ARCHITECTURE.md:79`（而且從 F7-9 起就過期了）。README:49 講的是引擎分三段，仍然正確 |
| 黃金值不准動 | 成立，而且跑過了（三份逐項相同）|

> **交辦單上的一個「兩處都要改」，值得先確認真的有兩處。**

### ⑦ 兩個反空轉的下限下修了

`>= 5`（Output 段幾張卡）與 `>= 4`（畫布的 Output 框）在三張之下是假的。
**下修並寫下為什麼**，不是拿掉 —— 同 `test_card_invariants` 在 `snr_map` 刪掉
那天把 12 改成 11。拿掉的話，那支測試哪天一張卡都沒有也會是綠的。

**驗收**：核心 2394 passed、UI 64 檔逐檔全過、黃金值三份逐項相同、
七個舊 key 案例的 15 個檔案內容逐位元組相同；六個新不變量各驗過
「把 bug 放回去會紅」。

**Phase 1 ＋ Phase 4 到此收斂。Phase 2 / Phase 3 另開 PR。**

---

## F37：GLV↔ROI 的名字、Output 的收斂（2026-08-26）

使用者：「GLV card 目前有很多種接 ROI 方式，量測的 GLV 跟相關的數值也很多，
會讓人混淆，尤其是在看 feature 內的數值」＋「output 的收斂問題」。

計畫書：[`docs/history/plans/F37-glv-roi-names-and-output.md`](docs/history/plans/F37-glv-roi-names-and-output.md)。

### ① 動手之前先把「混淆」量出來 —— 四項，全部跑得出來

寫計畫書那一輪一行 code 都沒動，先確認抱怨的具體形狀。四項後來都成了改動的
理由，而其中兩項跟我原本以為的不一樣：

* **`<region>_boxes` 由兩張卡各寫一次**，意思不同（Region 卡：這個區域有幾個
  框；GLV：其中幾格量得出來）。我原本以為它是安靜的 —— **不是**：lint 報得
  出來、engine 也把先寫的救成 `<節點名>_epi_boxes`。真正的問題是它**由構造
  決定**：只要接兩個區域就一定發生，而每一份正常 recipe 上都會出現的警告會
  被學會忽略（`_feature_collisions` 自己寫下的話）。
* **`reference="the other regions"` 刻意不宣告**，理由是「那條線已經在了」。
  那句話**對線是對的、對埠是錯的**：`roi=epi_center` 時 `configuration_issues()`
  回空的、`unknown-region` 也沉默，而跑起來每一顆 defect 各失敗一次。
  F12 那條「用到的每一個區域都要有一條線」在這裡反過來證明了自己。

> **量出來的形狀跟猜的不一樣，而修法會跟著換。** 那兩項如果照猜的寫，第一項
> 會做成「加一條 lint」（已經有了），第二項會做成「改錯誤訊息」（訊息本來
> 就是好的，問題是它出現的**時機**）。

### ② 改名的第四條路：參數值

`worst_*` → `glv_worst_*` 這種改名，遷移本來只走三條路（分數表達式、判定段、
`feature_math` 的算式）。第四條沒有人走 —— **Output 卡的參數值**
（`rank_by` / `columns` / `features` / `size_feature` 每一格都裝著特徵名）。

漏掉它的症狀特別壞，因為**它跑得完**：`rank_by` 指到不存在的數字時，出圖卡
排不出順序就安靜地退回檔案順序，於是使用者拿到 N 張正常的圖，而「最值得看的
那 N 顆」完全沒有發生（F30 修過一次的 bug，只是這次的來源是遷移）。

做法是**宣告式的**：新增 param 型別 `feature_key` 與 `step.FEATURE_TYPES`，
遷移照型別走。抄一張卡片清單的話，第五張會用到特徵名的卡不會有人記得回來
登記，而漏掉的那一張是安靜的。

### ③ 黃金值全綠，但那個綠比看起來弱

`freeze_golden.py --check` 三份逐項相同 —— **而三份 fixture recipe 都沒用到
`each box`**，所以它們一開始就不含被改名的那些特徵。真正覆蓋這次改名的是
`tests/test_shipped_recipes.py`（改之前紅、改完綠）。

> **尺量得到的範圍要講出來。** 「三份全綠」在這一輪是真的，但拿它當「改名
> 驗過了」的證據是錯的 —— 那把尺沒有伸到這裡。

### ④ 條件式前綴：修「安靜」，不修前綴

多接一條區域線會把量測卡寫的每一個名字都改掉（`glv_median` →
`epi_glv_median` ＋ `mg_glv_median`），而下游指著舊名字的地方不會跟著改。

使用者選了 (ii)：**前綴不動，但改名不再是安靜的**。兩層 —— 當下（狀態列，
`RecipeModel.set_param` 回一串話）與一直（新 lint `stale-feature-ref`，
畫布上那張卡掛著標記）。狀態列的字會被下一個動作蓋掉，所以第一層不能是
唯一防線。

level 用 warning 而不是 error，分界照既有契約（`configuration_issues` 是
「會失敗」、`hints` 是「跑得起來但你八成不是這個意思」）。

### ⑤ 上下標的顏色沒有第二份

使用者：「值可否用上下標　更清楚　配合顏色」。拆解**由卡片給**
（`Step.feature_parts`，跟 `resolve_features` 走同一個迴圈），不是 UI 拆字串
—— `test_epi_hot_glv_median` 裡哪一段是流、哪一段是區域、哪一段是使用者自己
取的名字，三者都是任意識別字，UI 只能猜，而猜錯會把區域畫成流，顏色跟著錯。

顏色取 `theme.region_hex(index)`，**同時**是影像上 ROI 框與畫布上區域埠的
顏色。三個地方一個顏色，來源一份 —— 各自挑的話 `"top,bot"` 在一邊是 0/1、
在另一邊是 1/0，而**顏色指錯區域比沒有顏色糟得多**。

### ⑥ 合併 Output 卡：先量參數，再決定

`Write images` 的七格參數**一格不差全部是** `Write report folder` 的子集，
寫出來的東西正好是後者少了三個檔案 —— 量完才敢說它們是同一張卡的兩個程度。
`output_char` 那一半沒有合（使用者：「B 我們再討論」），而我第一版把它說成
「推翻一個仍然成立的結論」太保守了：翻回 `CLAUDE.md` §3，repo 自己的判例
（F19 的 CD、F29 的 `roi_reference`）一面倒站在合併那邊，char 那段註解擔心的
是文件成本而不是正確性。

兩個差別要用參數保住，否則遷移會**安靜地換掉輸出格式**：`picture_format`
（PNG vs JPEG）、以及「圖放不放進 `images/` 由有沒有報表決定」—— 那一層存在
的理由本來就是報表要相對路徑連過去，所以那不是相容湊出來的規則。

### ⑦ 兩個順手的

* `param_visible` 是整串相等比對，對多選型別會讓那一格**永遠不出現、而它的
  預設值照樣生效**。改成成員比對之前先稽核了 registry 裡每一個 `show_when`，
  目標全部是單值型別 → 逐位元組等價。
* `_center` / `_others` 這兩個後綴被拼在**四個地方**，而改動其中一份不會讓
  任何測試變紅。收成 `_util.centre_name` / `others_name`。

### ⑧ 一個踩到自己文件的

UI 測試用一個行程跑整套，跑不完 —— 而 `CLAUDE.md` §4 早就寫著「Qt 記憶體會
累積，在容器裡實測從 100 秒變成跑不完」。改回逐檔跑，63 個檔案全過。

### ⑨ B2 做完之後，合併那一題的答案變了

B1 的第二半（`output_char` 併不併進 `output_bundle`）當初提議的理由是
「三張寫資料夾的卡共用九成參數與同樣四個檔名」。**B2 把那個「九成」真的收
掉了** —— 報表開頭、CSS、ROI 框那三格、`rank_by`、`limit` 的 `0 ＝ 全部`、
路徑檢查現在全部只有一份。

於是合併能再省下的只剩「卡片庫少一列」，而代價沒變小（那張卡的 help 與測試
要同時描述兩種版面，而版面的差別是真的：6000 顆點一列換圖 vs 30 顆圖排在
列上）。**使用者定調「先不合」。**

> **重複要先量，而量的時機會改變答案。** 同一個提議在 B2 之前與之後成本效益
> 不同 —— 因為中間那一步把「重複」本身拿掉了。**先收共用的部分，再決定要不要
> 合併卡片**；順序反過來會多做工，而且會用一個已經不成立的理由做決定。

那個「不要合」的決定有一支測試守著
（`test_output_convergence.py::test_the_two_layouts_are_still_two_functions`）
—— 哪天真的要合，先回來刪它並寫下為什麼。

### ⑩ 我自己踩的兩個

* **UI 測試用一個行程跑整套，跑不完** —— 而 `CLAUDE.md` §4 早就寫著那件事
  （「Qt 記憶體會累積，在容器裡實測從 100 秒變成跑不完」）。改回逐檔跑。
* **反向驗證時用 `git checkout <file>` 復原**，把那個檔案**所有未提交的改動**
  一起還原掉了（`output.py` 與 `html.py` 的 B2 工作全沒）。前兩步用的是精準
  反向替換，第三步偷懶。重做之後改回精準替換。
  > **「把 bug 放回去」要用跟放進去時同一把工具**，不要用一把作用範圍更大的。

**驗收**：核心 2357 passed、UI 63 檔逐檔全過、黃金值三份逐項相同；
九個新不變量各驗過「把 bug 放回去會紅」。

**F37 到此收斂。**

---

## F36：整批的分布有地方畫了 ＋ patch dSNR 的 recipe（2026-08-26）

使用者：「幫我建一份 recipe 是 for patch 專用，要用來比較這一整筆 patch 內的
dSNR 分布 …… 輸出預期要有 report 然後還有一張 box plot。**如果需要新增功能
(請通知我~) 看不懂得也問我**」

計畫書：[`docs/history/plans/F36-boxplot-and-patch-recipe.md`](docs/history/plans/F36-boxplot-and-patch-recipe.md)。

### ① 「照字面實作」會做出一個永遠不成立的門檻

規格裡有一句「GLV contrast 超過 40 編一」。而這個 repo 的 `contrast` 是
**Michelson**（`(T−R)/(T+R)`，範圍 **−1..1**）—— **40 不可能是它**。

照字面寫進判定樹的話：跑得完、每一顆都掉進 bin 2、而畫面上沒有任何線索。
那正是這個 repo 那六個「跑得完、有數字、而且是錯的」的形狀，只是這一次它會
從**規格**進來而不是從程式進來。

所以問回去了（使用者答：灰階差 `delta`）。同一輪還問了「dSNR 是 delta 還是
snr」與「box plot 一個盒子代表什麼」。

> **一般形狀：規格裡的一個數字對不上它那個量的量綱時，那不是筆誤，是兩個人
> 對同一個字有不同的定義 —— 而定義的差別會安靜地活到報表上。**

### ② `_outlier` 兩個方向都算，而 `delta` 帶正負號

`each box` 的 `<n>_outlier` 是「離典型最遠的那一格」，**兩個方向都算**。
配上帶正負號的 `delta`，`> 40` 就是一條**只抓亮缺陷**的規則 —— 暗缺陷是負的
（合成資料上實測 **−18.6**）。

第一版照使用者指定的走 `delta`；但逃生口要一直在：`compare_metrics` 一起量
`abs_delta`，並且把代價寫進 README 與一支叫得出名字的測試。

**他看完之後說「把 abs_delta 換上去」。** 換的成本正好是**一個名字** ——
`abs_delta` 早就在量了，影像段一格都不用重跑。

> **做他要的、把代價講清楚、把改回來的路留著 —— 三件都要。**
> 沒講的話他不會問；沒留路的話換回來是一次重跑。少一件，這一輪就不會有
> 這個結果。

順帶一件測試上的：那支端對端測試**問樹要哪幾個名字**
（`decide_tree.features_used`），不抄一份清單 —— 換名字的時候它自己就跟上了。
抄一份的那個版本當場紅，而那正是「一個主題一個家」在測試裡的樣子。

### ③ 新功能：box plot（手寫 SVG，零新相依）

整包沒有 matplotlib，而公司機是用複製檔案更新的 —— 多一個套件就是多一件會
裝不起來的事。box plot 的幾何就是幾條線與幾個矩形，前例也在
（`klarf_core._svg_wafer` 畫 die 熱力圖）。

三個決定值得記：

* **一個盒子是一片葉子，不是一個 bin。** 使用者選的是後者，而在他的 recipe
  上兩者是同一件事 —— 但葉子多三個免費的好處：盒子上的字就是他自己寫的那一句、
  順序跟畫布上的樹一樣、顏色也一樣。兩片葉子共用一個 bin 是合法的，那時候
  「一個 bin 一個盒子」會把兩個他眼中不同的類別畫成一個。
* **`Numbers to plot` 留空 = 判定問過的那幾個**（新的
  `decide_tree.features_used`）。寫死一份清單的話，樹改了而清單沒改的那一天，
  圖上畫的就不是在判的東西了。
* **鬚停在真實資料點**，不是 `q1 − 1.5·IQR` 那個算出來的邊界 —— 後者會畫出
  一段伸進沒有資料的地方的鬚，而讀圖的人會以為那裡有東西。

### ④ 例外表要有一支反向的測試

patch 這份 recipe 有一格**塞不進 JSON**：templateGC 要一張模板**影像**。
所以 `test_shipped_recipes.py` 多了一張 `ALLOWED_ERRORS` —— **明列**那兩條
error（同一個原因、兩句話），而不是「這份 recipe 跳過檢查」。

外加一支反向的 `test_the_allowed_errors_are_all_still_happening`：例外修好了
卻沒從表上拿掉的話，這份 recipe 從此少一條防線，**而測試照樣綠**。
那是「例外表」這種東西唯一會爛的方式，所以它要有自己的守門人。

### ⑤ 塞不進 recipe ≠ 不能測

模板是一張影像，出貨的 JSON 帶不了它。但**測試造得出來**：合成 lot 的圖案就是
一個週期性晶格，切一格 `encode_cell` 就是模板。於是「這份 recipe 到底跑不跑得
出那三個數字」沒有藉口不驗 —— 補上模板之後要求**零 error**，跑 12 顆、49 個框，
三個特徵都在，報表與 box plot 都寫得出來。

**「這個沒辦法測」多半是「我還沒想到怎麼造那份資料」。**

### 驗收

核心全套 + UI 逐檔 + `freeze_golden --check` 三份全綠（沒碰演算法）。
新增 `tests/test_output_boxplot.py`（16）；`test_shipped_recipes.py` 12 → 22。

---

## F34：存檔回來了 ＋ 一份出貨的 characterization recipe（2026-08-26）

使用者：「接下來幫我做一個重要的功能，存 recipe，做完之後幫我建一隻
Characterization recipe（讓我開啟後載入檔案能直接跑）。另外問一下 output 段
要怎麼接」

計畫書：[`docs/history/plans/F34-save-recipe.md`](docs/history/plans/F34-save-recipe.md)。
這裡記三件計畫書裝不下的。

### ① 拿掉一個功能的理由，會比那個功能活得久

存檔 2026-08-16 被拿掉，commit 訊息寫的是「先把整個 engine 用好，再來支援」。
**而 Phase 1 收斂也是同一天、同一個 commit。** 那個前提在寫下的當下就已經到期。

十天裡沒有人回頭看它，於是它長出了下游：`CLAUDE.md`／`README.md`／
`docs/ROADMAP.md` 三處寫著「不支援」，而 `studio.py` 裡有**兩段註解拿「反正
存不了檔」當論證**：

* `_adopt_threshold_as_a_tree`：「而 Studio 現在又存不了檔，所以磁碟上的東西
  不會被改寫」—— 存檔回來的第一秒這句話就是假的，而且它守著的是一個真的行為
  （打開一份門檻 recipe、按 `Ctrl+S`，磁碟上那份會變成判定樹）。
* `unsaved_changes`：「**沒有任何辦法保住這份 pipeline**」。

兩段都不是錯的 —— 它們在被寫下的那天是對的。**它們錯在把一個暫時狀態寫成了
論證**。這一輪把兩段都換成「當時為什麼那樣寫 / 現在是什麼」，跟 F33 那一輪
處理 `F15 §4.4` 的辦法一樣。

> **下一次拿掉功能時**：把「什麼時候可以回來」寫成一個**看得出到期**的條件，
> 而不是一句理由。「Phase 1 收斂之後」寫在 commit 訊息裡沒有人會再讀到它。

### ② 「載入後能直接跑」跟站點資料是有衝突的，而衝突有個誠實解

出貨的 recipe 有三格永遠不能寫死：第二份 lot 的**路徑**（F15 的規矩）、
**排名欄位的名字**（每台機台不一樣）、**輸出資料夾**。

第一版把 `rank_within` 填了 `XINDEX,YINDEX`、`rank_by` 留空 —— 結果
`configuration_issues` 判成 **error**（「填了 Rank within 但 Rank by 是空的」），
CLI 直接不跑。**一份為了「打開就能跑」而做的 recipe，打開就跑不動。**

當下的改法是**兩格都留空**，並且讓「還沒設定」變成判定樹上一片**說得出原因
的葉子**：

```
let die_rank = pair_die_rank    missing ⇒ 用 -1      ← F24 ⑤ 的 Let.fill
② die_rank_missing > 0 ?  yes → bin 9「no ranking column picked yet」
```

於是不改一個字就跑得完，而報表第一眼就在告訴他還有哪一格沒填 ——
出現在他真的會看的地方，不是一個跑之前的紅字。

**這件事的一般形狀**：一個設定沒填時，不要在「擋住不讓跑」與「安靜地算錯」
之間選 —— 讓它變成一個**輸出裡看得見的類別**。這一條站得住。

⚠ **但「兩格都留空」那一半在同一輪被推翻了** —— 見 ④。留空 `rank_within`
是為了繞開一條 lint，而那條 lint 一開始就放錯地方。

### ③ 那句假訊息只在它最該講實話的時候出現

`unknown-feature` 警告一律接一句「every defect will fail on this line at run
time」。對帶 `fill` 的 `let` 那是**假的** —— 那一行的意思正是「這個數字可能
不在」。

而它剛好只在 `fill` 真的派上用場的時候出現。這支 lint 本來就**看得見**
`fill`（下面兩行拿它來登記 `<name>_missing`），只是沒有拿它來講話。
這一輪出貨的 recipe 正好是那個形狀，於是它被撞出來了。

跟 F33 那三個「有數字而且是錯的」是同一族：**不是算錯，是講錯**。
而講錯的代價一樣 —— 使用者照著那句話去修一個根本沒壞的東西。

### ④ F35：為了繞開一條 lint 而留空的那一格，其實是 lint 放錯地方

**這一段是三個追問逼出來的**，而它推翻了我自己四小時前寫下的設計。

出貨的 recipe 第一版把 `Rank within` 與 `Rank by` **兩格都留空**，理由寫在
計畫書 §3.2：填了前者沒填後者會被 `configuration_issues` 判成 error，CLI
直接不跑。那個處置**繞過了症狀**，而我當時把它寫成了一個設計決定。

使用者接著問「`Rank within` 的意思是？」，然後問「**但如果只勾 XINDEX 會發生
什麼事?**」。第二句把真正的形狀翻出來了 —— 我量了一次（4 欄 × 3 列 die、
每 die 6 筆、每 die 取前 2 名）：

| `Rank within` | 組數 | `pair_die_total` | ① 抓到了 | ② 排名太低 |
|---|---|---|---|---|
| `XINDEX, YINDEX` | 12 | 6 | **24** | 48 |
| 只勾 `XINDEX` | 4 | 18 | **8** | **64** |

只勾一欄＝整整一行 die 併成一組。**不報錯、不警告、跑得完、數字看起來正常**，
而整份報告的結論反過來（看起來像「sample 門檻設太緊」，其實是分組錯了）。
唯一的線索是 `pair_die_total`。

於是兩格的性質根本不同：

* `rank_within` **猜得到**（逐 die 是絕大多數站點的規則），而且**猜錯是安靜的**
  → 要預先填好。
* `rank_by` **猜不到**（每台機台的欄位名不一樣）→ 留空。

而擋路的那條 lint —— 回頭看 `configuration_issues` 的契約（F7-13 寫的）：

> 「空字串的模板是完全合法的 str —— **但那張卡跑起來每一顆都會失敗**」

**error 這個級別就是踩在那句話上**，而 F33 放進去的訊息不符合它（那張卡跑得完，
只是少寫兩個特徵）。所以分成兩支：

| | 契約 | 級別 | code |
|---|---|---|---|
| `configuration_issues` | 這張卡**會拋**或什麼都不產出 | error | `not-configured` |
| `configuration_hints`（新）| 它**會跑**，但你八成不是這個意思 | warning | `half-configured` |

> **這一輪學到的一句話：當你為了繞開一條 lint 而改設計時，先問那條 lint
> 是不是放錯地方了。** 我當時甚至在計畫書裡把「不降級 lint」寫成被否決的方案
> —— 而正確答案不是降級，是**它從一開始就不屬於那一支**。

### ⑤ 出貨的 recipe 這次帶著測試一起來

上一批範例 recipe（`examples/`）死於**沒有人測**：卡片改名、參數換了，
五份載不進來，而畫面上還留著兩個按了會撞牆的入口。

`tests/test_shipped_recipes.py` 對 `recipes/` 裡每一份問三種問題 ——
載得進來且 `validate` 沒有 error、**線在該在的埠上**（Output 卡沒有任何線）、
**真的跑一次**（不改字跑得完；填上排名欄位之後 ① ② ③ 三類都數得出來；
報表裡配不到的那一格是空的不是破圖）。

### 「output 段要怎麼接」

**不接。** Output 卡沒有輸入埠（`resolve_reads` 回空清單），在 route 上就會跑
—— `run_batch_steps` 是整批跑完之後照 `execution_order` 各跑一次。畫布上它在
自己的虛線區塊裡，副標 `(not connected)` 是正常的。拉線進去會落在一個不存在的
埠上。要看哪一條流是**打字**填的（`str` 而不是 `image_key`，因為那種欄位是
唯讀的、只由畫布上的線決定，而這張卡不上畫布接線）。
⚠ **`Run trial` 不寫檔**，要 `Run all`。

### 驗收

核心全套 + UI 逐檔 + `freeze_golden --check` 三份全綠（沒碰演算法，黃金值
一個位元不該動）。新測試 37 條（`test_recipe_save` 11、`test_ui_save_recipe` 12、
`test_shipped_recipes` 12，`test_pair_source` +2）；
`test_ui_f7_16_safety_net` 的反向斷言（「`_on_save_recipe` 不存在」）換成
兩支正向的。

---

## F33 續：四個使用者的問題，挖出三個「有數字而且是錯的」（2026-08-26）

C1–C4 做完之後，使用者連續問了四個問題。**每一個都不是要求，是懷疑** ——
而三個懷疑底下真的有東西。這一段記的是那個過程，因為結論本身在
[`docs/history/plans/F33-ebi-characterization.md`](docs/history/plans/F33-ebi-characterization.md)
§8.5–§8.7，而**「為什麼沒被測試抓到」只有這裡寫得下**。

操作手冊另立一家：[`docs/USING-CHARACTERIZATION.md`](docs/USING-CHARACTERIZATION.md)
（線接哪、每格填什麼、報表怎麼讀、出事了照什麼順序查）。

### ①「UI 畫面或 report 長怎樣？畫面怎麼接？」

截圖回答的時候發現：我手寫的示範 recipe **沒有 `edges`**。CLI 跑起來完全正確
（引擎照流名解析 + route 順序），但在 Studio 裡打開是**四張沒有線的卡**。

實務上不會踩到（使用者是在畫布上拉線建 recipe，Studio 自己會寫 edges），但
**手寫的 recipe 一定要補 edges，否則畫布會說謊**。那份示範在 scratchpad、
沒進 repo，所以沒有東西要修 —— 記在這裡是給下一個手寫 recipe 的人。

### ②「RSEM 1000² vs patch 100²，ground truth 落在某一處，對得到嗎？」

**問對了。** 實測（1000×1000 空拍、100×100 patch、非週期紋理）：

| defect 在哪 | 預設 15% 框 | `search_within=0` |
|---|---|---|
| 正中央 | ✓ (449,449) NCC=1.00 | ✓ NCC=1.00 |
| 偏左上 (150,200) | **⚠ (307,383) NCC=0.43** | ✓ NCC=1.00 |
| 角落 (820,780) | **⚠ (304,366) NCC=0.30** | ✓ NCC=1.00 |

**它不會失敗** —— 對的那一塊不在搜尋範圍裡，於是在中間挑「矮子裡的高個」，
回一個錯的位置加 0.30–0.43 的分數，而 `min_score` 預設正是 **0.3**。

根因：`search_within` 預設 15% 編碼的是 **Review SEM**（移到座標才拍），
而問題描述的是**空拍**（defect 落在它剛好在的地方）。**兩個模型，一個預設值。**
沒有改預設（Review SEM 那條路 15% 是對的），把它寫在**卡片的 help 上** ——
使用者會讀到的地方。

順帶推翻任務書的一句話：「`ncc_score` 是唯一的擋板」。陣列區實測
**NCC 0.98 而位置每一顆都錯**（第二名跟第一名一樣好），抓得到的只有
`align_peak_ratio` —— F15 §14.2 早就量過那個數字，只是沒有人把它放進報表。
`output_char` 的預設欄位因此補上它。

### ③「不太理解你怎麼量得出來 —— 你要看得到圖才知道偏多少」

這一題的答案跟直覺相反：**不需要在 RSEM 上看到 defect，EBI patch 本身就是尺。**
patch 以 defect 為中心裁，所以 NCC 找的是「這一小塊圖案落在大圖的哪裡」
（整塊紋理，不做缺陷偵測）；落點的中心即 defect。實測五組子像素吻合。

**而追問逼出了一個承重假設**，同一組實驗只換 patch 怎麼裁就塌：

| patch 怎麼裁 | `align_off` |
|---|---|
| 以 defect 為中心 | (+18.0, −12.0) ✓ |
| 中心偏了 (+20,+15) | (+38.0, +3.0) |
| **固定格線裁** | **(−0.0, +0.0) 恆為 0** |

最後一列是最危險的形狀：十字與框完美重合、報表看起來「每顆都對得剛剛好」，
而那個數字跟 defect 無關。列進 `FAB-VALIDATION.md` 的假設 7。

圖上因此畫兩個記號（`output_char` 的 `mark_defect`）：綠十字＝瞄準哪、
紅框＝對到哪，**間距就是 stage 偏移**。配不到的那一顆只有十字。

⚠ **這一輪唯一一個真的 bug 是端對端跑出來的，不是測試跑出來的**：
`align_to` 的讓路判斷只問了 `search` 埠，而 characterization 那條 recipe 把第二份
接在 **`template`** 上（小圖是 EBI patch）。八顆裡的三顆因此照樣 `ok=False`
—— 正是要數的那一類。測試全綠，因為我測的時候接的是 `search`。
**便利貼：兩個輸入埠的卡，讓路判斷要問兩個埠。**

### ④「H2H 的 UI 可以像 GLV CD 那樣嗎？Image stream 會提供 overlay 嗎？」

overlay 的機制（`Step.overlay_marks`，F19）**本來就有而且跟著 Image stream 走**
—— 只是全 repo 只有 CD 與 GLV 實作它，而 H2H 做的事偏偏是「位置」。
補上框與十字（只畫在被搜的那條流上），加一個專屬面板
（`MeasureInspector` 的**子類** —— 分布是調參數要看的，留著）。

**圖示不做**，而且理由是硬的：CD 的 `shape`/`axis`/`target` 適合圖示是因為它們
在選「一種樣子」（一條線 vs 一團東西，畫得出來）。H2H 的參數是數字與影像流，
沒有一格是在選樣子。硬配圖示只會多一排看不懂的方塊。

### ④-b「預覽框太不明顯」→ 挖出一條**別人的**規矩

`_paint_marks` 預設把非 focus 的線畫成 alpha 70、1px。那條規矩的理由寫在
程式碼裡，而且是為 **CD 的幾十條掃描線**寫的：「點比線重要…所以線畫到幾乎
看不見」。H2H 的形狀相反 —— **只有 6 條線，而線本身就是答案**。

**沒有去改畫法**，因為 GLV 刻意靠那個淡化（「用線描的外框會跟區域框完全重疊、
等於沒畫」，2026-08-22 截圖才看到；F32 又踩了一次）。改掉會讓那個坑回來。
所以做成卡片自己宣告的 `Step.marks_solid`（預設 False，既有的卡一張都不用動）。

再一輪「預覽也分」→ 兩個記號分色。**沒有發明第五個回傳值**：`labels` 本來就是
逐條的顏色來源，`!` 開頭的是**角色**而不是區域名（沿用 `decide_tree` 的
`!failed` / `!unbinned` 慣例）。**卡片說角色、UI 挑顏色** —— core 不得 import
Qt，而「紅色是什麼紅」是主題的事（light/dark 兩套）。報表跟預覽因此是同一組
語言：紅的永遠是「對到哪」、綠的永遠是「瞄準哪」。

### ⑤「Pair 卡不用帶 XREL YREL 嗎」→ 手冊寫錯了一格

寫完手冊之後的追問，而**手冊那一列是錯的**（我寫「EBI 的分數欄（必填）」）。
實測兩件事：

* **座標配對完全不需要 carry** —— `XREL` / `YREL` / `XINDEX` / `YINDEX` 在
  **載檔那一刻**就被讀成 `DefectItem.xrel_nm / yrel_nm / die`
  （`ingest/dataset._base_item`），跟 `fields` 是兩條路。carry 一欄都不填，
  `position` 照樣配得到、`match_dist_nm` 照樣是 126.49。
* **排名也不需要** —— `rank_within` / `rank_by` 指名的欄位由
  `columns_for_source` 自動加進複製清單（重複填也不會帶兩次）。

所以 `carry` **不是機制的必要條件**，它是「你想在報表與判定樹裡看到什麼」。
真正該 carry 的是：`DEFECTID`（回去原始資料找得到那一筆）、
`XINDEX`/`YINDEX`（**報表的固定欄沒有 die** —— 這是唯一把 EBI 那邊的 die 帶進
輸出的路），以及判定樹要直接用原始分數時的那一欄。`XREL`/`YREL` 通常不必，
`match_dist_nm` 已經講了兩邊差多遠。

**而錯的不只手冊**：`pair_source` 的模組說明與 `carry` 的 help 都還停在 F15
（「必須把 KLARF 欄位帶成 feature，否則第一列與第二列長得一模一樣」）——
那句話在 `rank_by` 出現之前是對的，之後就漂了。同一件事寫在三個地方，
而這一次是**使用者**發現漂掉的那一份。三處一起改，並鎖上兩條測試。

### ⑥「layout 是重複區域的話會有很大機率認錯，有什麼方法」

**量出來了，而且解法只有一條。**（週期 25 px、patch 96 px、30 次不同雜訊）

| 情境 | 整張搜 | 15%（±60px）| 3%（±12px，< 半週期）|
|---|---|---|---|
| patch 裡有 defect，FOV 另有 5 顆 | 30/30 | 30/30 | 30/30 |
| **patch 裡沒有獨特的東西** | **0/30** | **3/30** | **30/30** |

第二列才是會出事的那種，而它**不會失敗** —— 給你一個位置加 0.98 的 NCC。
第一列則說：**只要 patch 中間真的有那顆 defect，它就是錨**，附近有別的 defect
也不影響（先前 exp5 的 3/6 是我把六顆 defect 種在同一張圖上造成的，不是常態）。

規則掉出來是一條不等式：

    stage 誤差 ≤ 窗半寬 < 晶格週期 / 2

右邊那半：窗內只放得下**一個**晶格位置，週期性就失去作用。左邊那半：窗要蓋得住
機台真的拍歪的量。`stage 誤差 > 週期/2` 的話這條路走不通 —— 要先用
`expect_dx_px` 把系統性偏移吃掉，剩下的隨機量才有機會小於半週期。

**根本原因值得寫下來**：陣列區裡「這塊 patch 屬於哪一格」有 N 個一樣好的答案。
那不是演算法不夠聰明，是**影像內容真的重複** —— 所以資訊一定得從影像以外來，
而那就是 KLARF 座標。

### ⑥-b 順手抓到一個「假的自信」

查上面那條的時候發現：`align_peak_ratio` 在窗縮小之後會變成**假的 0.00**。

第二名是「把最高峰周圍蓋掉之後剩下的最大值」，遮罩半徑 = 模板的一半。窗縮到
比遮罩還小時**整張回應圖都被蓋掉**，而 `locate_template_peaks` 把那個情況寫成
`second = 0.0`（註解寫著「整張都被蓋掉 = 沒有第二個地方」）。

那句話在「搜尋影像本來就只比模板大一點」時是對的，**在「使用者把窗縮小」時是
反的** —— 第二個地方在窗外。實測模板 96 px、窗 ±32 px：回應圖 65×65、遮罩半徑
48，全被蓋掉 → ratio 0.00 → 讀起來「第一名遙遙領先」。

**而它發生的時機正好是最不該樂觀的那一個**：陣列區裡照建議把窗縮小之後。
改成回 `NaN`，`align_to` 據此**不寫那一格**（算不出來的不寫）。

代價要講清楚：縮小窗之後那個擋板就沒有了 —— **擋板從「每顆一個數字」換成
「那個參數設對了」**。所以操作手冊把順序定死：週期性這件事要在**寬窗**的時候
先問清楚（`align_peak_ratio` 的分布），再去縮窗。

### 這一輪學到的三件事

1. **一個預設值可能編碼著一個未言明的模型**（`search_within` 的 15%）。
   換一種資料來源，那個模型就不成立 —— 而它不會報錯，它會給你一個數字。
2. **「唯一的擋板」要驗證**。任務書說 ncc_score 是，實測不是。
3. **端對端跑一次會抓到測試抓不到的東西** —— 因為測試是我照我的理解接的線，
   而真實 recipe 接法不同。
4. **加了新機制，舊說明會漂**（`rank_by` 讓 `carry` 從必要條件變成選配，而
   三個地方的文字都還寫著舊的）。⑤ 那一題是使用者替我發現的 —— 寫手冊的時候
   **要回頭讀一次卡片自己的 help**，不然就是把漂掉的那句話又抄了一份。
5. **一個「安全的預設值」可能在另一個情境變成謊話**（`second = 0.0` 那一行）。
   判準是問「**這個 0 是量出來的，還是因為沒量到？**」—— 後者要回 NaN，
   讓呼叫端決定不寫。這一輪兩次踩到同一個形狀（另一次是 `match_dist_nm`
   的 NaN），值得當成一條檢查項。

---

## F33：EBI ↔ API characterization —— 把三類分開，並且看得見（2026-08-25）

計畫書：[`docs/history/plans/F33-ebi-characterization.md`](docs/history/plans/F33-ebi-characterization.md)。
接的是 F15 §16 停下來的那一段（使用者 2026-08-20：「太快了」）—— 這一輪把它
**停下來的理由滿足掉**再續做：缺的那份「點對點包含圖的 report」就是 C3，
而它需要的兩個資料缺口是 C2 與 C1。

要回答的是「EBI 這台機台的這個 recipe 表現如何」。拿 RSEM 的 API 空拍當答案卷，
每一顆分三類：① 抓到了、② **配到但排名太低沒被 sample**（藏在 raw data 內）、
③ 根本沒偵測到。②③ 的處置完全不同（sample 門檻 vs 偵測條件）而資料上長得很像
—— **分開它們是這個功能存在的全部理由**。

### C2：③ 是一個結論，不是一個錯誤

`pair_source` 配不到就 `raise`，於是那一顆 `ok=False`、沒有分數也沒有 bin，
**走不到判定樹**。整個功能的結論正是 ③ 的顆數，所以它被當成錯誤處理，等於問
不出自己的答案 —— 而 CSV 上看不出來：少了幾列，跟「本來就沒那幾顆」長得一模
一樣。現在 `pair_found = 0`（一律寫）、不吐流、這一顆繼續走。

F15 當時的理由是「跟 `load_sidecar` 遇到沒有 label 的那一顆是同一個行為，不發明
第二套」。那個類比**只在缺的東西是輸入時成立** —— 這裡缺的東西就是答案。
（舊決定連同它為什麼是錯的都留在 F15 §4.4，刪掉的話下一個人會再推導一次。）

順帶挖出兩個坑：

* **配不到不再寫 `match_dist_nm`（原本是 NaN）。** 判定樹問問題是
  `expr.eval(feats) != 0.0`，而 **`NaN != 0.0` 是 True** —— `match_dist_nm > X`
  會對一顆根本沒配到的 defect 答「是」。這不是理論：它跟「算不出來的不寫」
  指向同一個修法，而少了後面那一句就想不到前面這件事。
* **改名遷移本來只做了一半。** `paired` 撞了預設流名，改成 `pair_found` 走
  `legacy_feature_renames`（F18）—— 但那條遷移**只改寫 `score.expr`**，而
  F30 之後問問題的地方是判定樹。樹上的 `when` 沒跟著換，開起來就是一題
  **永遠答「否」**的問題（問不到的特徵算否），而畫面上它跟一條正常的規則長得
  一模一樣。補了 `_rename_in_decide`（`let` / `rules` / `tree` / `decide.score`）。

**而端對端跑抓到一個單元測試沒抓到的洞**：`align_to` 的讓路判斷只問了 `search`
埠，但 characterization 那條 recipe 把第二份接在 **`template`** 上（小圖是 EBI
patch、大圖是 RSEM 空拍）。八顆裡的三顆因此照樣 `ok=False` —— 正是要數的那一類。
測試只接了 `search`，所以全綠。現在兩個埠都問，測試也 parametrize 成兩種接線。
**這一條值得記住**：這輪唯一一個「跑得完、有數字、而且是錯的」是端對端跑出來的，
不是測試跑出來的。

### C1：排名的母體是那一份的完整清單

「分數低到沒被 sample」問的是**名次**，而母體是第二份的完整 defect list
（幾千筆）。判定段有現成的「跟整批比」（`Let.scale`）—— 用在這裡是錯的，因為
它看得到的只有跑過 pipeline 的那三十顆，答出來的是「這顆在我挑出來看的 30 顆裡
排第幾」，對 sample 門檻沒有意義。整份只有掛上來的那一層看得到，而排名是**資料
的屬性**不是判定的中間值 —— 放在讀資料那一層才對（同「一格 nm/px 長在把那份
資料讀進來的那張卡上」）。

三格參數（都 `choices_from="source_columns"`，打錯欄名在掛載那一刻就擋）：
Rank within（分組，可留空；**不預設 XINDEX/YINDEX** —— 那是這個 lot 剛好有）、
Rank by（排序欄，使用者自己選）、Highest first。吐 `pair_die_rank` 與
`pair_die_total` —— total 不是湊數的：**「第 7 名」在 10 筆裡跟在 3000 筆裡是
兩件事**，而 rank 那一格看起來一模一樣。

備忘掛在 `DefectItem` 物件上（一組設定一個 key），所以一份資料算一次而不是逐顆
算，重掛一份 lot 會產生全新的 item —— 過期不了。tie-break 是 DEFECTID（測試把
items 反過來擺再跑一次）。轉不成數字要點名欄位、值與 DEFECTID：安靜地全部並列
第一的話，每一顆都拿到 rank 1，而它跟「真的是第一名」在報表上長得一模一樣。

### C3：`output_char` —— 圖跟數字在同一列上

使用者要的是「我可以一一對應這樣子」。`output_bundle` 答不出那句話：它的每一個
取捨都是為 6000 顆做的（表格裡不放縮圖、點一列換圖、整份只有一個 `<img>`），
而點一列換圖的版面在任何一個時刻畫面上只有一顆。三十顆的規模那三項全部反過來
—— 所以是**第二張卡**，不是第一張卡的一格參數（一格參數的話「這張卡長什麼樣」
就有兩個答案）。底層共用 `export/html.py` 的 CSS／跳脫／判定那一段、抽成模組層
的 `write_recipe_json`、以及改成公開的 `overlay.pick_base`（「沒有指名時這一顆
的圖是哪一張」兩個地方都要問，而答案只能有一個）。

沒有第二張圖的那一格**完全不產生 `<img>`**：破圖示講的是「載入失敗」，而那一格
要講的是「這一顆在另一份資料裡不存在」。超過 limit 就講出來並指名
`Write report folder`，**但版面不換** —— 使用者要知道他拿到的是哪一種報表。
`ncc_score` 預設就在表格裡：沒有量測卡，配對是唯一的風險，而它是唯一的擋板。

### C4：montage 可以指定哪幾條流、橫排還是直疊

`render_overlay` 加 `panes` 與 `stack`，預設路徑一個位元都沒動（測試直接比
「不給參數」與「明確給 `panes=None, stack='h'`」逐位元組相同）。
⚠ **目前沒有正式呼叫者**，而那是刻意的（C3 的表格本來就兩欄兩張圖，使用者也把
這件標成可選）—— 寫進計畫書 §8 是為了下一個人不要把它當成順手可清的死碼。

### 驗收

黃金值三份全綠（沒填排名參數＝一個位元不變）。端對端 8 顆 API × 5 顆 EBI：
8 成功 / 0 失敗，5 顆 caught、3 顆 not detected，三類加總等於 8；③ 那三顆
`ok=1`、`bin=3`，rank 與 ncc 那幾格是**空的**（不是 0）；報表 5.9 KB、
13 張外部 JPEG、路徑全部相對。

---

## F32 收尾：像素染色只在「真的有異常」的顆上出現（2026-08-25）

實測的第二個發現收掉：正常顆（#10，`worst_score` 2.7σ、bin 0）的疊圖上
贏家框也**整格**染色。原因不是 bug 是尺度 —— 像素判準的分母是框間統計量的
穩健散布（一批安靜的框常踩 1 灰階地板），遠小於像素雜訊（σ≈5 灰階），
所以 3σ 門檻在**任何**框裡都有一堆像素過線。

**做法：染色跟贏家自己的分數綁同一個 k**（`_roi_overlay_kwargs` 的條件多一項
`worst["score"] >= k`）。`Mark pixels beyond k σ` 的語意變成一句完整的話：
「這一格自己至少偏離 k 個 σ 時，把推它過線的像素標出來」—— 不新增參數、
不新增概念，而 score 跟染色本來就是同一組 baseline/spread 算的（T1 的
meta note），語意天然一致。實測：#2（47.9σ）照染、#10（2.7σ）整張安靜。

否決的兩個候選：**調高預設 k** —— 發明一個跟影像相依的魔術數字，還安靜地
弱化真缺陷的染色；**綁到 bin** —— F25 之後 bin 是判定樹的任意類別，
「哪個 bin 算 flagged」沒有定義。

驗收時逐像素對 PNG，又抓到一個藏在下面的：**贏家的粗描邊把小框整格塗滿**
（cv2 的線騎在邊上畫、往內外各長一半 —— 5×9 px 的框配 3 px 四條邊就是
實心色塊），染色畫在框底下所以 32 個像素一個都看不見；前一輪截圖裡
「正常顆也整格染色」其實看到的是這個。修法：贏家描邊的粗細讓路給框的
內部（`(min(w,h)−1)//3` 封頂），大框照舊是粗的。修完 #2 的框內染 15 px
看得見、#10 的框內乾淨 —— 兩顆終於長得不一樣。

順手把相關 md 對齊現況：ROADMAP 的 Measure 列補 F31/F32 一句、
F0 草圖裡的 `blob_area` 範例加「曾在這裡」註記。這一輪整批 merge 回 main
（使用者定調）。

## F32 實測：端到端跑一輪，抓到一個「畫了等於沒畫」（2026-08-25）

使用者：「實測跑一次，看截圖結果。」合成 RSEM lot（384²、12 顆、一半有真缺陷）
＋手寫 recipe：`load_single` → `roi_reference`（stripes、`pick="none"`）→
`glv_stats`（each box、judge=median）→ score=`worst_score` →
`output_image`／`output_bundle`（rank_by=worst_score、draw all、mark 3σ）。

### 量出來的

* 12/12 跑完、51 ms/顆。每顆 ~500 個框（stripes 交會），`Draw at most` 的
  自動退化警告如預期出現。
* **照 `worst_score` 排序，前四名全是真缺陷**：bridge 47.9σ、bright_blob
  29.0σ／6.7σ／4.7σ；九顆正常的擠在 2.7–4.1σ。兩顆 dark_blob 沒浮上來 ——
  一小塊暗點動不了那格的 median，**這是 judge 的選擇不是機制的錯**（合成的
  暗點太弱，換 q05 也拉不起來）。
* 自訂 judge 端到端通：`glv_q05`（清單外的手寫 id）從 recipe 一路到 CSV 與
  meta 都對。
* 報表 bundle：贏家琥珀粗框＋像素染色正落在 bridge 上、鄰近細藍框、
  `report.html` 的判定條／表格／點一列換圖都對。Studio offscreen 實跑：
  GLV 面板 `typical box #401 of 527 · worst #439 at 4.7σ (median)`、
  1–5 段設定區、單選膠囊，全部在畫面上。

### 抓到的：贏家描邊跟區域框完全重疊 —— 畫了等於沒畫

W2 的預覽把贏家描**四邊**。`overlay_marks` 的 docstring 自己寫著典型格為什麼
用角點：「用線描的外框會跟區域框完全重疊、同一個顏色，等於沒畫」——
我在贏家上原樣踩了一次，527 個綠框的截圖裡完全認不出哪一格是贏家。
改成畫**一個 X（兩條對角線）**：不跟任何框的邊重合，再小的格子也認得出。
測試跟著改並多一條「對角線的兩端 x、y 都不同（描邊做不到）」。

一個看到但**不改**的：正常顆的疊圖上贏家框也整格染色（分數 2.7σ 也有像素過
3σ）—— 那是任務書指定的像素判準（分母是框間統計量的散布，比像素雜訊小）
照做的結果，而標籤上的 `score=2.698 bin=0` 讓讀圖的人分得出來。要更安靜可以
把 `Mark pixels beyond` 調高，或哪天把染色綁到 bin 上 —— 等使用者真的被吵到
再說。

驗收：core 2203 過、黃金值三份全綠、f20_panel_truth／f19_cd／widgets 逐檔
全綠。截圖（overlay ×2、report.html、Studio 全窗＋放大）都交給使用者了。

---

## F32 W3：GLV 設定區整理（2026-08-25）

使用者：「GLV measure UI 介面（左側設定區）要做好看一點。」先 offscreen 截了
一張現況（before/after 兩張都貼給使用者了），照截圖上看得到的問題逐條修：

* **段落編號補齊成 1–5**：以前只有「3 · Compare against」與「4 · Which
  pixels count」，前面四格是一塊沒名字的區。現在 `1 · What to measure`
  （Statistics）、`2 · Boxes in the region`（across_boxes ＋ judge ——
  逐框那兩格終於有自己的家）、3、4 不動、`5 · Output`（Name these results
  以前因為沒有段，畫面上黏在第 4 段裡）。
* **段標題下不再重複同名列標籤**：`_ParamRow` 的 echo 抑制以前只認逐字相等
  （CD 的 "Report"）—— 帶編號的段（"3 · Compare against" vs 列標籤
  "Compare against"）抓不到。改成先剝掉 `"N · "` 再比。掃過全 registry：
  新規則只多吃掉 GLV 那兩列（across_boxes、reference），沒有誤傷。
* `source` 那列補 `label="Measure on"`（原本顯示小寫的參數名 `source`，
  跟其他 Title Case 的標籤不一致）。
* judge 那列的裸下拉在 W2 已換成跟 Statistics 一致的單選膠囊。

驗收：受影響 UI 檔逐檔全綠（widgets 58、f8_ui_polish、f8_advanced、
controls_readable、f20_panel_truth、f19_cd、f7_9_feedback）、core 2203 過。
黃金值不看（純 UI／label／section，引擎路徑零改動 —— label 與 section 不進
recipe 的鍵）。

---

## F32 W2：judge 可自訂 ＋ 贏家框即時預覽（2026-08-25）

使用者：「Pick the odd one by 除了 median 當 index 外，希望可以 custom 參數
（可選或自定義）」＋「接上後 image stream 可以預覽 overlay 嗎（在還沒跑 batch
之前，當下就看 outlier）」。

### 自訂：清單只是常用的那幾個

引擎其實**早就吃**任何 `_canonical` 認得的 id（glv_qNN／trim／above）——
是 `judge` 的 `type="choice"` 嚴格驗證把它擋住了（驗證比 runtime 窄）。做法
不是放鬆 choice，是新 ParamSpec 型別 **`metric_choice`**（`metric_chips` 的
**單選**長相，同一條規矩：不強制值落在 choices，認不認得由卡片的 run() 說）：

* 新 widget `MetricPick`（`MetricChips` 的子類）：同一種帶小圖的膠囊、同一顆
  「+ Percentile…」，差別只有三件 —— 值是一個 id、點一顆關掉其他、**恆有一顆
  選著**（取消最後一顆會留下空值，看起來像「取消沒生效」，不如不准）。
  judge 那格從「顯示原始 id 的裸下拉」變成跟 Statistics 一致的膠囊 ——
  這同時是 W3（好看）的一半。
* 值格式不變（一個 id 字串）—— 舊 recipe 逐位元組相容，鐵則 9 不觸。
* **打錯的 id 當場報錯**：`_judge_of` 以前安靜退回預設 —— 那是安靜換值
  （使用者以為照 glv_q97 挑、整批其實照 median 挑，每顆都吐得出正常數字）。
  改成 `measure` 裡用跟 `metrics` 同一句話 raise。

### 即時預覽：不用等 batch

預覽管線本來就每顆自動跑（切一顆 defect 就重跑一次 preview、marks 跟著刷），
缺的只是 `overlay_marks` 沒讀 `worst`。現在：贏家那一格描**完整四邊**＋角點、
`focus` 指著它（滿 alpha —— 它才是主角；典型那一格退成淡的，沒有 worst 時
照舊聚焦典型格）。GLV 面板標題列加 `· worst #12 at 4.3σ (median)`，
`summary()` 帶一句 —— 讀的都是 T1 的 `worst` note，跟 `worst_*` 特徵同一次
計算。

驗收：`test_glv_compare` 63 條（+5：custom id 端到端、爛 id 報錯、單值不收
清單、預覽形狀 1+4 條線與 focus、無 worst 的退路）、`test_ui_widgets` +4
（單選、不准空、手寫 id 顯示且選著、judge 列真的是 MetricPick）、
UI 批 163 條全綠、core 2203 過、黃金值三份全綠。

---

## F32 W1：刪掉 pick 的 `strongest`（2026-08-25）

使用者：「Which box is the defect in 這邊選 strongest 好像就跟後面量測卡功能
稍微衝突了，我傾向留 centre & none。」**攤過代價之後仍定調直接刪**（有問過
「收起來」的零成本選項 —— F20 量過 strongest 在 patch 座標偏移時是
11/24→24/24、AUC 0.688→0.977 的差距）：大圖上「找最異常」現在整件事歸 GLV
的逐框比較，patch 座標偏移那條路**從此沒有訊號救援**，只剩「離中心最近」。

### 刪了什麼

* `PICK_RULES` 剩 `("centre", "none")`；`pick_source`（Judge on 那條線）、
  `pick_defect_box` 的訊號分支與 `PICK_SMOOTH_PX`（3×3 匹配濾波）、
  `pick_by_signal`／`cross_pick_by_signal` 特徵（宣告＋寫出）全部一起走。
  `pick_defect_box` 簡化成 `(boxes, shape) -> 索引`。
* 三張 Region 卡的 `resolve_reads` 不再因 pick 多宣告一條流；
  `_pick`／`_place` 的 judge 佈線拆掉。`cross_dist_px` 留著（離中心距離，
  centre 之下仍有意義）。
* 舊 recipe 填過 `strongest` 的**明確報錯**（choice 驗證），不遷移 ——
  安靜換成 centre 等於安靜換一組數字（3c748a0 的規矩）。有測試鎖。

### 順手校正一份漂掉的數字

F20 的實測在 repo 裡有兩份且互相矛盾（`_util.py` 寫 14/24→23/24、
`test_pick_defect_box.py` 寫 11/24→24/24）。以
`docs/history/plans/F20-pick-defect-box.md` 為準（**11/24→24/24、
AUC 0.688→0.977**），留下來的史料註解（`_util.PICK_RULES` 上那一段 ——
照 F28「例子沒了寫進去」的樣子，把代價與「要回來得整支重做」寫明）用的是
正確的那一份。

驗收：core 2199 過、黃金值三份全綠（fixture 無 pick 鍵）、受影響 UI 檔
逐檔全綠。`tests/test_pick_defect_box.py` 改寫成 11 條（含「strongest 不准
安靜長回來」與「舊 recipe 報得出讀得懂的錯」）。

---

## F31 T5：刪掉 find_defect（2026-08-25）

使用者：「我覺得 find defect 不需要。」T1–T3 做完之後它的三類輸出全部有了
替代：位置＝GLV 逐框比較的 `worst_x/y/w/h`（框就是 ROI 自己）、突出度＝
`worst_score`、框內細節＝疊圖的像素標記（只畫，不吐數字）。

### 直接刪，不進 HIDDEN_STEPS

「先收後刪」那條規矩（CLAUDE.md §5 那張表）服務的是「舊 recipe 還在用」——
這張卡今天早上才進 main（F29），零 recipe、零 fixture、零黃金值在用。收起來
只會留下一張沒人用、卻要一直維護的卡。這跟 `pattern_ref` 那次（rsem 準確率
24/24 → 12/24）完全不同：這次的代價量出來是**零**。

### 刪了什麼、留了什麼

* 刪：`steps/find_defect.py`、`tests/test_find_defect.py`、
  `steps/__init__.py` 的 import；`algo/shape.py` 的 `find_blobs` /
  `BlobScan` / `BlobHit` / `_scan_fail`（**唯一呼叫者就是這張卡** ——
  `cd.py` 用的是 `measure_blob`，`test_algo_shape.py` 也全是）。
* 留：`measure_blob` 與兩支共用過的準位（`pick_levels`、
  `edge.threshold_level`、`edge_quality`、`_MIN_CONTRAST`）—— CD 在用。
* 連帶清（照 F28 刪 Z-map 的樣子，把「例子沒了」寫進去而不是放寬斷言）：
  * `overlay._BOX_FEATURE_SETS` 的 `blob_*` 那組（產者沒了）；**連
    `blobs=` 那個參數一起**（`ctx.meta["blobs"]` 的 richer path —— 全 repo
    沒有任何東西在寫那個鍵，它是更早被刪的 blob 分割的遺跡）。
    `primary_blob_box` 只剩 features 一個參數。
  * `_util.AREA_FEATURES` 的 `blob_area_px`、`LENGTH_FEATURES` 的
    `blob_deq` —— 各留一行「曾在這裡」的註記（加會吐面積的新卡時那張表
    就是為那一刻留的）。
  * `rank_by` help 的例子 `blob_strength` → `worst_score`（被鎖的
    `"decision tree"`/`"file order"` 兩個子字串不動）。
  * 卡片庫順序測試：Measure 斷言改成**正好三張** GLV → CD → Focus index。
  * README 能力表（今天早上才寫上 Find defect 的那格）、卡片數 25/22 →
    **24/21**。
* 新的一條守門：`test_blob_features_are_gone_and_stay_gone` —— 哪天有一張卡
  又吐 `blob_x` 這組名字它會紅，而那正是它要講的話。

驗收：core 2205 過、黃金值三份全綠、Measure 段剩三張、受影響 UI 檔逐檔跑過
（f7_9_feedback、input_kinds、f10_canvas_reality、f16_stages、widgets）全綠。

---

## F31 T3：贏家框內標出異常像素 —— 只進 overlay（2026-08-25）

視覺上這件事等同被刪掉的 find_defect，所以**界線先寫死**（任務書原文）：
只進 overlay —— 不吐特徵、不生具名區域、不寫 `ctx.meta["blobs"]`。一旦它開始
吐 `blob_x` 那一族，find_defect 就從後門長回來，而整個 F31 的設計是為了
**只有一種框**。有一條測試守著「render 前後特徵表零新增」。

### 判準不另外算一次

`|pixel − baseline| / spread > k` 的 baseline / spread **逐字是 T1 算
`worst_score` 用的那兩個數字**（GLV 留在 meta 的 `worst` note；spread 已含
地板）。畫面跟數字各自算的話，遲早出現「圖上標紅但數字說正常」——
Results R1 那個 bug 的形狀。所以改 GLV 的判準統計量，標出來的東西跟著變
（測試：同一張圖、兩組 baseline/spread → 標記不同；spread 夠大 → 逐位元組
等於不標的那張）。

* 像素吃**量測那條流的原始陣列**，不是顯示用被 `to_display_rgb` 拉過值域的
  那份 —— 判準跟數字同一份輸入。拿不到那條流、幾何對不上 → 不標（不猜）。
* 疊層順序：像素標記最底、ROI 框中間、量測框最上。
* `k` 是兩張出圖卡共用的一格（`Mark pixels beyond`，單位 σ，預設 3.0，
  0 = 關）—— 跟 T2 的兩格同一份 spec。
* 抽取重構成 `worst_note_for_overlay`（回 note 本身），
  `roi_boxes_for_overlay` 變薄包裝 —— 「哪一條 note」的判斷仍然只有一份。

驗收：`test_export_overlay.py` 52 條（+5）、`test_output_bundle.py` 的
`_roi_overlay_kwargs` 測試補 odd_pixels（k>0 才帶、數字逐字是 meta 的
worst、k=0 不帶）、core 2245 過。

---

## F31 T4：pick 加「none」—— `_center` 從唯一解法變成一個選項（2026-08-25）

使用者：「可以把 pick 換成在影像上挑，但 centre / strongest 還是可以自己選」、
「我覺得只有在 patch 有用，但我想把它完全拿掉（或自己可以選）」。選項名
使用者定了 `none`。

### 開關只有一個家

三張 Region 卡的家族宣告都經過 `_util.region_family`、執行都經過
`set_region_family` —— 兩支各加一個 `pick` 旗標，off 只留主名字（不寫
`_center`/`_others`、也不記 `regions_absent`：那兩個名字**沒有被宣告**，
不是「該在而不在」）。單一出處 reader `_util.pick_rule_of`（照
`glv_stats._reference_of` 的樣子）——**必要**而不只是整潔：`pick_defect_box`
對不認得的 rule 會**安靜退回「離中心最近」**，`none` 必須在三個呼叫端短路。

跟著挑選一起走的：`pick_by_signal`／`cross_pick_by_signal`（「有沒有真的用
訊號挑」在不挑之下不存在）、`cross_dist_px`（「挑中那塊離中心多遠」同理）——
宣告與執行同步拿掉，`test_what_it_declares_is_what_it_writes` 那條逐字相等
照綠。`drop_edge_boxes` 的 `keep` 傳 -1（沒有受保護的框 —— 函式本來就安全）。

### 錯誤訊息分兩種情況講

`roi_rect_or_none` 那句「'<name>_center'（the box nearest the middle of the
patch, **which is where the defect is**）」在 RSEM 大圖上是錯的解釋，會把人
推去用一個無意義的名字。改成兩條路：patch 上 `_center` 是缺陷那一塊；大圖上
「pick the box by signal … or use a card that compares all the boxes」。
同族的無條件斷言一起改：`drop_edge`/`edge_margin` 的 help、兩張卡 `roi_out`
的 help。加了一條 grep 式測試：三個模組的原始碼裡**不准再出現**那句話。

### 畫布跟著宣告走

* 埠數走 `resolve_regions_out` 自動 3→1（`_NodeItem.height` 自動縮）——
  新 UI 測試：五層 × `none` = 1+5 顆埠、名字正好是五個主名。
  `_MAX_REGION_PORTS` 不動（它數的是埠）。
* `studio._focus_box_index` 的「離中心最近」退路在 `none` 的卡上是說謊
  （引擎明講沒有哪一格特別，畫布卻畫一個醒目的）→ 新 `_picks_a_center()`：
  宣告裡沒有 `_center` 就不畫。

### 下游斷線要吵、舊 recipe 一個位元不變

* `pick=none` ＋ 下游還指 `epi_center` → 現有 `unknown-region` lint 響
  （新測試證明，而 `centre` 之下不響）。
* 遷移**不需要**：預設仍 `centre`，舊 recipe 缺鍵補同一個預設（鐵則 9 的
  形狀完全沒動到），全部既有測試不改一條斷言照綠。

這一輪起容器裡裝得動 PySide6（＋ libegl1）—— UI 測試**逐檔**跑過
region_edges（19）、f7_11_roi、gds_panel、f7_9_feedback、f10_canvas_reality、
controls_readable，全綠。core 2240 過、黃金值三份全綠。

---

## F31 T2：overlay 畫 ROI 框 —— 報表上圈出最異常的那一格（2026-08-25）

使用者：「我說的把它框出來，只是最終在 final report 要用 overlay 把它框出來。」
`render_overlay` 自己的註解早就寫著答案：「兩個都在時畫兩個才誠實，**等疊圖
畫得下第二個框再說**」—— 這一輪就是那一天。

### 做了什麼

* `render_overlay` 多 `roi_boxes`（**正規化** 0..1）與 `roi_winner` 兩個
  kwarg：贏家粗琥珀框（`ROI_WINNER_COLOR`）、其餘細鋼青線（`ROI_BOX_COLOR`
  —— 它們是**參照**，要看得到比較的分母是什麼，但不能跟主角搶畫面）。量測框
  （紅）**後畫** —— 疊到的地方「量到的東西在哪」在最上面。montage 兩個面板
  都畫。預設 `None` 逐位元組不變（有測試逐位元組比）。
* 來源 `overlay.roi_boxes_for_overlay(ctx)`：讀 **T1 留在
  `ctx.meta["glv_hist"]` 的 note**（`boxes >= 1` 的是 each box 跑的），贏家
  就是 `worst["i"]` —— **跟 `worst_*` 特徵同一次計算**，不在疊圖端重挑一次。
  拿不到贏家 → 全部細線，**不猜**（猜錯的框比沒有框糟得多）。好幾個區域都有
  框時先只畫第一組（挑一組畫而畫面上不說是哪一組，正是最怕的形狀 ——
  等疊圖說得清「哪組框是誰的」再開）。
* 「框太多」是使用者的一格不是魔術數字：兩張出圖卡共用
  `Draw the other boxes`＝`all / none / near the winner` ＋ `Draw at most`
  （預設 300）。**一個數字管兩件事**：它同時是 `all` 的自動退化門檻與
  `near the winner` 的數量 —— 不必發明第二個。退化發生時整批**警告一次**
  （一顆一句的話 6000 顆就是 6000 句）。
* 沒有贏家又超過上限 → 一個都不畫：畫不下又挑不出來，誠實的答案是不畫。
* 贏家永遠畫得出來（`near` 的名單先放贏家再補最近的 —— 第一版
  `sorted(...)[:cap]` 在「另一格跟贏家同心」時會把贏家自己擠掉）。

### 兩條既有的逐位元組防線都還綠

`test_export_parity`（卡 vs 精靈）與 `test_the_cached_pass_produces_the_same_pictures`
（快取 vs 直跑）：fixture recipe 沒有 each box 的 GLV → 抽取回空 → 一個位元
不變。新畫的路徑只讀 meta 與 rois，無隨機源，快取重放照樣逐位元組相同。

驗收：`test_export_overlay.py` 47 條（+14）、`test_output_bundle.py` +2
（兩卡逐字同一組、`_roi_overlay_kwargs` 吃真的 each box ctx）、黃金值三份
全綠、core 2122 過。

---

## F31 T1：GLV 逐框比較 —— 「這張圖最異常的地方」有座標、有分數（2026-08-25）

使用者換了方向（取代前一份「擴充 find_defect」的任務書）：「原來的 GLV 跟 CD
這方面可能就做得到，接 ROI 卡，但要能自動算多框，找最異常去比較。然後下游可以
就把這個 ROI 框（因為它本身就是異常點）給 draw 出來。」三條原則：**只有一種框**
（ROI 的框既是輸入也是報表上畫的框）、**挑選的家在量測卡**（ROI 卡跑在量測卡
之前，不可能用還沒算出來的統計量挑）、**特徵表固定欄位**。

### 不是蓋新的，是把既有的 each box 模式補完

讀 code 讀出來：`glv_stats` **已經有**逐框模式（F18 第 6 步的
`across_boxes="each box"`，吐 `_typical`/`_outlier`/`_outlier_box`）。缺的是
「總冠軍」—— `_outlier` 那三個後綴是**每個統計量各自**的極端格，而使用者要的
是照**他挑的那一個**判準選出唯一的贏家，帶座標、帶分數。同一件事不開第二個家。

### 做了什麼

* **`algo/glv.odd_box_scores(values)`**：每一格跟「其他所有格」比 ——
  `baseline = median(others)`、`spread = 1.4826 × MAD(others)`、
  `score = |v − baseline| / max(spread, 1)`。基準用 median 不用 mean 的理由
  寫在 docstring：**平均數會被異常格自己拉走，而我們正在找的就是那個異常格**。
  1.4826 跟 `Let.scale` 的 robust z 同一個係數（`batch.py:476`）；地板 1 灰階
  跟 `algo/shape._MIN_CONTRAST` 同一個數字同一個理由。回傳的 spread **已含
  地板**，所以 `score == |v−baseline|/spread` 逐位元組成立 —— 讀這三個數字的
  人（T3 的像素標記）不必自己知道地板的存在。
* **leave-one-out 是 O(N log N) 不是 O(N²)**：拿掉一個元素的中位數對每一格
  只有 ≤3 個候選值 → 按候選值分組、每組排一次偏差陣列。正確性對 `np.delete`
  的暴力版**逐位元組**驗證（`test_glv.py`，含重複值／奇偶長度／常數陣列）。
* **`judge` 參數**（label `Pick the odd one by`，`show_when` 綁 each box，
  選項＝現有 `METRIC_CHOICES` 那份來源）：判準是使用者的樣品問題（median 看
  不見的一顆亮點，max 看得見），獨立於 Statistics 那格勾了什麼。
* **特徵**：贏家組 `worst_i / worst_x / worst_y / worst_w / worst_h /
  worst_score / worst_value`（座標＝整張影像像素，**逐位元組就是
  `ctx.roi_rects()[worst_i]` 那一格** —— 只有一種框，位置不另外量）＋分布組
  `score_median / score_spread`（「一個框特別怪」跟「500 框都一樣怪」只看
  worst 分不出來，而那兩件事的處置完全相反）。單框或算不出 → **一格都不寫**。
* **meta**：`glv_hist` 的 note 多一份 `worst`（i/rect/score/value/baseline/
  spread/judge）—— 疊圖畫框（T2）與像素標記（T3）讀**這一份**，跟特徵同一次
  計算，不是第二份。

### 兩處刻意偏離任務書（否決理由）

* `boxes_n` 不另開 —— 既有的 `boxes` 特徵就是它，同一件事第二個名字會漂。
* `score_max` 不另開 —— 它逐字等於 `worst_score`；同一個數字兩個名字排在同
  一份 CSV 裡，沒有任何線索說它們是同一個（F18 名字分家族那條規矩擋的正是
  這個）。表達式直接用 `worst_score`。

### 順手修掉一個宣告與寫出對不上的洞

`_each_box` 以前寫 `roi_count > 1`：**單框的區域安靜地退回 pooled**，於是同
一格參數有兩種意思，而且宣告（`feature_names` 只看參數，吐帶後綴的名字）跟
實際寫出的（pooled 裸名）對不上 —— 既有的宣告測試沒抓到，因為 fixture 是
25 格的網格。使用者這次明文定調「不要偷偷退回 pooled」，改成 `>= 1`：單框
照走逐框路，吐 `boxes = 1` 與那一格自己的 `_typical`，只是沒有 worst。
`== 0`（區域在這顆上不存在）仍走 pooled，讓 `roi_pixels` 用既有訊息報錯。

### 先量再改（效能，1000×1000 合成圖、glv_median+glv_mad）

| 框數 | each box | pooled 對照 |
|---:|---:|---:|
| 50 | 39 ms | 47 ms |
| 500 | 68 ms | 46 ms |
| 5000 | **343 ms** | 50 ms |

5000 框是基準（`glv_stats` 在 5,295 框上 105 ms）的 3.3 倍 —— 沒超過一個
數量級，**不做抽樣**（抽樣要多發明一個數字，`_others` 那次已經判過一次不值得）。

驗收：`test_glv_compare.py` 58 條（+7 新）、`test_glv.py` +4 條（暴力版逐位元
組）、黃金值三份全綠（沒有 golden recipe 用 each box）、core 2186 過。

---

## 文件追上程式碼：README、四個沒進紀錄的 commit、計畫書歸檔（2026-08-25）

使用者：先把整個專案與最近幾次的修改讀一遍列出來，然後「三個都先幫我做」——
指的是讀完之後回報的那三條漂移。**這一輪一行程式邏輯都沒動**，動的是文件與
檔案位置（`.py` 只改到指向計畫書的那幾行路徑）。

### 一、README 講的是三個星期前的 app

`CLAUDE.md` §0 那條「同一件事只寫在一個地方」擋的正是這個，而 README 是唯一
一份沒有人在改的入口文件。逐項對過程式碼之後改掉五處：

| README 說 | 實際上 |
|---|---|
| 26 張卡、可見 23 張 | `REGISTRY` 是 **25 張**、扣掉 `HIDDEN_STEPS` 可見 **22 張** |
| 量測有「SNR map、blob 分割」 | 兩個都不在了 —— Z-map 2026-08-25 刪（F28）、blob 分割使用者定調「不需要 也不要再出現」。改成寫**現在真的有的**：GLV／CD（同一趟給 LWR／LER）／Focus index／Find defect |
| 使用者看到的是**八**階段（含 Algo）| **七**段 —— Algo 在 F24 §5 解散進判定，唯一出處是 `GROUP_ORDER` |
| 「ADC 判定不是卡片，而是 score 運算式與 bin 規則」| 那是 F22 以前的語言。現在是 recipe 頂層的 `decide` 區塊＝一棵**判定樹**，畫布上有自己的判定區，另有 `route_by` 分流 |
| 「`roi_snr` 同時回報 signed 與 abs」| 那張卡與那支函式 2026-08-21 就刪了。`algo/snr.py` 留著的理由要寫出來：它是**正負號慣例的規範出處** |

輸出那一列也補齊了（六張 Output 卡，含 F29 的報表資料夾），文件索引補上
`docs/USING-CD.md`。

### 二、`CLAUDE.md` §4 那條擋路的警語，理由已經過期

它寫著「現在不要動 `studio.py`，因為那把尺（黃金值）是壞的」。查下去：
**黃金值 2026-08-23 就重凍了、三份全綠**（見本檔「黃金值重凍」那一段）——
也就是那條警語自己引用的前提，在寫下它之後兩天就解除了。

沒有把警語拿掉（使用者定的順序仍然是「先把引擎做對，再回頭產品化」），但
**把理由換成真的那一個**，並把前置條件寫成做得到的動作：動之前先
`freeze_golden.py --check` 三份全綠。同一段的數字也重量了 ——
`StudioWindow` 從 5,244 行長到 **6,017 行**（三天 773 行），而那正是這一段
存在的理由。

### 三、十份做完的計畫書還住在 `docs/plans/`

`docs/history/README.md` 寫著判準：「標成 ✅ 而且不再有人往裡面寫東西」。
照它搬了八份（F20…F25、F28、F29），留下五份還在寫的：`F0`（原始總計畫）、
`F11`（Phase 2 的議程）、`F15`（⏸ 使用者叫停）、`F26`／`F27`（各有一條等使用者
定調的版面決定）。

**搬之前先把狀態改對** —— 四份頂上寫的是當時的話，而它們早就上線了：

| | 頂上寫著 | 實際 |
|---|---|---|
| F22 | 「畫布那一半還沒做，有一個開放問題」| 開放問題 08-24 定稿（有線，而且是一整個判定區），畫布那一半由 F24 接手 |
| F23 | 「期2、期3 未動」| 三期全部完成（08-24）|
| F24 | 「方向已定稿，**未動工**」| ①②③④⑤ 全數完成，判定區 08-25 補上拖曳與移除 |
| F29 | 「C 未開始」| A／B／C 全完成，可選的 D（Output 段的視覺）當天也做了 |

一份寫著「未動工」而其實已經上線的計畫書，封存起來就是一句會誤導下一個人的
話 —— 所以 `docs/history/README.md` 那句「內容一個字都不改」補成
**「搬的時候不改，要改的是搬之前那一步」**。F21 §6（黃金值是壞的）加了一條
指向重凍的後記；索引表補上 F18／F19（它們早就搬過來了但沒進表）與這八份。

引用路徑一起改（`grep -rn "docs/plans/<名字>"`）：`CLAUDE.md`、`SESSION_LOG.md`、
`d4t/` 四個模組、`tests/` 五個檔案、`tools/make_mgext.py`。
`tests/test_docs_links.py` 59 條全綠 —— 這一輪唯一一把有意義的尺。

---

## 補記：兩個假數字、Region 卡收成一張、Output 段上畫布（2026-08-25）

底下四個 commit 當時沒有寫進 SESSION_LOG（`CLAUDE.md` 開頭那句「每次 session
結束請更新最上方」漏掉的正好是它們），補在這裡。

### 兩個假數字（`c100565`）

**① 沒有分數表達式 ⇒ 沒有分數（不是 0）。** `_eval_decision` 以前寫
`score = expr.eval(...) if expr else 0.0`，而判定樹是一個**分類器**，多數樹根本
沒有分數表達式 —— 於是每一顆拿到一個假的 0，最嚴重的後果是
**「照分數排序取前 N 顆」變成「檔案順序的前 N 顆」**（全部同分時 `sorted` 是
穩定的）。而排序正是使用者要那份報表的理由。改成 `None` 且那一格不寫；三個
不擋 `None` 的下游各自處理：`pick_overlay_results` 多一格 `rank_by` 並在排不
出來時明講、KLARF top-N 的「the run failed」拆成兩句話、Gallery 不再畫出
`None` 那四個字。⚠ 既有測試 `test_no_score_expression_is_allowed_and_gives_zero`
**鎖住的正是這個 bug**。

**② 判定樹問到一個「量不到所以沒寫」的特徵時，整顆算失敗。** 可是那一顆跑得
好好的 —— CD 卡正確地什麼都沒量到所以什麼都沒寫（規矩 3），而「什麼都沒量到」
正是使用者最想看到的那一類之一。使用者定調：**那一題答「否」，繼續走**，而且
不可以是安靜的（`decide_unanswered` 進 features、缺的名字進 meta 與一條警告）。
判準抽成 `decide_tree.answer()` / `walk()` —— 引擎與畫布的分支流量以前是兩段
各自寫的迴圈，而後者的說明寫著「判準跟引擎一字不差」。

回歸測試的第一版**是假的**：隨機樹只生 `x > k`（k ≥ 0），於是「問不出來 → 答否」
與「缺值當 0」在每一題上給同一個答案，200 棵樹一棵都沒抓到。加上 `<` 與負門檻
才有鑑別力。

### 四張 Region 卡收成一張（`e8bb9f2`，F30）

使用者：「把 Profile / Template 也折進 `roi_reference`」。四張卡回答的是同一句話
——「哪些地方應該長得一樣」—— 所以是一張卡的四個 method（`CLAUDE.md` §3）。
**參數定義沒有第二份**：`_folded()` 從實作類別上取 `params` 再加一條「method 要
是它」的條件；那兩個模組留在原地、不再自己 `@register_step`（要合的是**使用者
看到的那張卡**，不是檔案）。

四件事是被這個合併逼出來的，每一件都比合併本身重要：`show_when` 要能 and、
那條可見性規則只能有一份（`ParamForm` 以前自己寫了兩次 → 抽成
`step.param_visible`）、表單要用預設值補沒填的格子（否則新加的卡每一格都被判定
為不該顯示，整張看起來是空的）、儀表與兩個入口要改看 method 不看 key。

遷移照 `_migrate_roi_compare_into_glv_stats` 抄（鐵則 9）。兩件不做就會**安靜換
一組值跑**：舊預設逐字寫進參數（三支互相衝突，`max_boxes` 64 → 8192 不報錯，
它會多量一百個框），撞名而意思不同的那一格改名（`min_confidence` 在 Profile 是
條紋信心 0..200、在 cells 是週期強度 0..1）。既有測試改成指向合併卡
（`tests/region_cards.py` 的 `BoundRegionCard`）而**一條斷言都沒有改** —— 那個
shim 綁的正是遷移寫進舊 recipe 的那三樣，所以那幾十條問的就是「舊 recipe 行為
有沒有變」。

### `repeating cells` 走人，而打錯的層號表要講出來（`3c748a0`）

使用者：「repeating cell 跟 a cell I mark myself 應該一樣，而且後者完整很多，
請把前者刪掉」。確實在回答同一句話，差別只在那一格 cell 是**量**出來的還是
**標**出來的，而標的那條路多了三道閘門與一個看得到的編輯器。method 四個變三個、
預設改 `stripes in the image`。⚠ **舊 recipe 明確報錯，不安靜換一支跑**（`method`
是 choice，值進不了 `validate_params`）—— 那個 method 是同一天早上才進 main 的，
沒有第二個使用者。`algo/period.py` 與 `algo/golden.py` **不動**（`CLAUDE.md` §5
的便利貼：`algo/template.py` 還在用，而「自己標的那一格 cell」正是靠它們疊出來的）。

第二件是使用者在畫布上看到的：「選 layout layers 之後沒有出口可以輸出區域線」。
查下去是一個安靜的錯 —— `_layers_of` 把 `ChannelMapError` 吞掉回空 list（打到
一半不准拋，那是對的），於是一個寫成 `17=epi` 的層號表（正確是 `17:epi`）產不出
任何區域埠，而畫面上沒有任何東西說為什麼。`configuration_issues` 現在分得出三種
狀態：表格是空的、表格讀不懂（錯在哪 ＋ 正確寫法）、表格沒問題。

### 畫布上的 Output 段：這幾張整批只跑一次（`9b913cc`）

畫布上其他每一張卡都是「一顆 defect 跑一次」，Output 段那幾張是整批跑完之後
只跑一次（`Step.scale == SCALE_LOT`）—— 而畫面上沒有任何東西說得出那件事。
給它跟判定區同一套視覺（虛線框、`OUTPUT / once per lot`），**不加埠、不加線**
（進去的是整批的結果表，那不是一條影像流）。新模組 `ui/output_band.py`
（`CLAUDE.md` §4），`canvas.py` 只負責接線；哪幾張算數看的是**卡片自己宣告的
group**，不是一份寫死的 key 清單。

三件是實際畫出來才發現的：**一個大框會說謊**（畫布會換行，四張卡的外接矩形把
上一列的 Normalize 與 GLV 一起框進去）→ 改成一列一串、中間夾到別人就不畫
（消失的框只是少一個提示，說謊的框是錯的）；框要用卡片**看得見**的那塊，不是
`sceneBoundingRect()`；那行字改放左邊走廊，否則相鄰兩列的框實測疊 42px。

---

## 量到了，然後丟掉：那一團在哪（2026-08-25）

使用者要的是「跑完一整筆 image，缺陷被框出來、照分數排序、6000 顆出成報表」。
計畫書：[`docs/history/plans/F29-detect-and-report.md`](docs/history/plans/F29-detect-and-report.md)。

### 計畫被退了兩次，而第二次的理由是對的

第一版寫「像素級的位置沒有 → 要做一張新的偵測卡」。使用者連問兩次：

> 「Q3 你還是沒回答我，GLV CD 在 Measurements 就已經量出這顆 defect 或位置的
> 一些資訊了（這些資訊不能拿來用嗎）」

去讀程式碼之後 —— **他是對的**。`cd_measure` 的團那一支早就算出整條輪廓與
最長那條弦、存進 `ctx.meta["cd"]`、面板上也畫出來了；再往下一層，
`algo/shape.py::measure_blob` 的 `connectedComponentsWithStats` 連外接矩形與
質心都算好了（`stats` 只拿來判 `touches_edge` 就丟、`centroids` 接成 `_cent`）。
**26 個 `cd_*` 特徵沒有一個在講「在哪」。**

缺的從來不是計算，是出口。整個 Phase A 因此從「做一個偵測器」變成「把已經
量到的接出來」。

「Detect 你要 detect 什麼？數字？」的答案也跟著清楚了：**不是數字，只欠一個
框** —— 排序已經有了（就是使用者自己寫的 `score`，`pick_overlay_results`
現在就照它排），多大與長什麼樣也有了（CD），哪一塊不一樣也有了
（`glv_stats` 的 `the other regions`）。

### A1／A3：位置有了出口

* `BlobResult` 多 `bbox` / `centroid`；`ALWAYS_BLOB` 多 `cd_box_x/y/w/h` 與
  `cd_cx`/`cd_cy`，**整張影像的像素**（區域偏移在卡片裡加回去，換算只做一次）。
* 一律吐而不是 `size_report` 的一個選項：**位置不是「要不要量」的選擇，
  是「我剛才量在哪」**。量不到就一格都不寫（0 會讓疊圖在左上角畫一個 0×0 的框）。
* **不配 nm 版**：框是「畫在哪」不是「多大」。這沒有把 F19 翻過來 ——
  那次刪 `cd_x_px` 的理由是「舊值是 bbox，跟新值不是同一種量測」，
  是在防名字換意思，所以位置用**新名字**回來。
* `primary_blob_box` 的退路寫成一張表：`blobs` → `blob_*` → `cd_box_*`。
  只認沒有前綴的那一份 —— 接兩個區域時「主 blob」有兩個答案。

### A2：`find_defect`（Measure 段第四張）

在一條流（可再指定區域）裡找出最突出的那一團，給框與強度。演算法
（`algo/shape.py::find_blobs`）跟 `measure_blob` **共用同一組準位與門檻**，
所以兩張卡的「…at this height」是同一句話。

**界線移動了，而移的是哪一格寫下來了**（使用者 2026-08-20：「Blob 分割不需要
也不要再出現」）：

> **可以找一個框，不可以產生具名區域。**

具名區域是下游每一張卡的輸入（`roi=`），自動長出一個等於畫布上出現一條沒有人
拉過的線 —— F9 那六個「跑得完、有數字、而且是錯的」全部長那個樣子。
一個框只是一組數字，要有人接才會被用到。

### A0：卡片庫的順序一直是字母序（順手抓到的真 bug）

2026-08-25 使用者說「Measure 的 card 順序幫我改命名&重排：GLV → CD →
Focus index」。那一輪改了 `steps/__init__.py` 的 import 順序、還在那裡寫下
「卡片庫裡看到的先後住在這三行」——**而畫面上一格都沒有動**：`list_steps` 是照
`key` 的字母序排的（CD、Focus index、GLV）。改動看起來完成了，全套測試也全綠，
因為沒有任何一條測試問過「使用者看到的第一張是哪一張」。

改成**純註冊順序**（`category` 不再參與排序 —— 它跟卡片庫的分區是兩條不同的
軸，兩條一起排的結果是「import 順序決定看到的先後」只對了一半，
Region 段的 `roi_mask` 會跳到 `roi_cross` 前面）。每一段現在讀起來就是資料流過
的順序。便利貼：`tests/test_card_library_order.py`，而它有一條專門證明自己不是
同義反覆（Enhance 段的字母序與註冊序是不同的答案）。

### 一個沒被抓到的話會很安靜的錯

`find_defect` 剛寫好時宣告出來的 nm 版叫 `blob_area_nm` —— **少乘一次**。
`nm_twins` 的規則是「`_px` 結尾 → ×s」，而面積要 ×s²，所以面積住在一張
名單上（`_util.AREA_FEATURES`）。加一張會吐面積的新卡就要記得加一行。

### B：Reference regions —— golden cell 與 GDS 收成同一張卡

使用者：「我不同意 GDS 為主力，應該說 golden cell 跟 GDS 同樣重要而且他們要能
在同張 card 裡（都是接區域 ROI 卡）」。收下 —— 而且這正是 repo 自己的規矩
（`CLAUDE.md` §3），也已經做過一次一模一樣的事（`roi_compare` → `glv_stats` ＋
`method="compare"`），連遷移的寫法都照抄得到。

`roi_from_mask` →**`roi_reference`「Reference regions」**，兩個 method：

* `repeating cells`（預設）—— `algo/period.estimate_period` 量週期 →
  `choose_origin` 定相位 → `algo/golden.tile_coords` 每一格一個框。
  **不合成任何影像**，那正是它跟被刪掉的 `pattern_ref` 的差別：那張卡把幾百格
  疊成一張參照圖再相減（對不齊就吐一張糊的 ref，畫面上看不出來），這裡只是把
  晶格切成區域，比的是統計量。
* `layout layers` —— 原本 GDS 那一支，一層一塊，形狀照 GLAS 給的。

**GDS 那一支現在也吐 `_center` / `_others`**，而當初不吐的理由**沒有被推翻**：
幾何的 `_center`（缺陷在正中央）在一張 RSEM 大圖上仍然沒有意義。變的是有了
`pick="strongest"` —— 它不假設缺陷在哪，**它去找**。被推翻的只有那句
「所以不能有 `_center`」。

接完之後**不需要任何新卡**就有區域級 detect：
`roi_reference(pick=strongest)` → `glv_stats(roi=..._center, reference="the
other regions")` → `cmp_snr_mean` → 判定樹 → `cd_measure` / `find_defect` 給框。

三件跟計畫不同的：

1. **`_others` 不必抽樣。** 計畫要求先量：`set_region_family` 在實測最壞的
   5 295 個矩形上是 **36 ms／顆**，只有下游 `glv_stats` 在同一組框上（105 ms）
   的三分之一。抽樣要多一個發明出來的數字，換到的時間比使用者自己接的那張
   量測卡還少。
2. **`source` 拆成兩格**（`source` / `label_source`）—— 一張晶圓的照片，跟一張
   「每個像素值就是層號」的圖，是兩種東西。共用一格的話，畫布上那條線會在切換
   method 之後指著一個意思完全不同的東西。
3. **`cells_confidence` 報 `peak_strength`（0..1）不是 `confidence`（0..100）**
   —— 使用者那一格擋的就是前者。報另一個刻度的話，「我設 0.18，它說 85」這句話
   沒有人解得開。

順手又抓到一個安靜的：**畫布的區域埠上限數的是「埠」不是「區域」。**
`_MAX_REGION_PORTS = 6` 原本剛好等於「六個區域」（那時候 GDS 卡一層只吐一個
名字）；一層變三個名字之後，6 就等於**兩層** —— 第三層開始的每一個區域在畫布上
都沒有出口，而 `_NodeItem.height` 的 docstring 自己寫著「截掉的那幾個⋯⋯畫布上
看不到它們就是說謊」。改成 18。

### C：報表 bundle —— 6000 顆一次出得完

使用者：「我是想 output 報表（包含很多顆 >6000 的把每一張圖分數都算出來
有 overlay 等等）但你說 html 這樣會很大 → 有替代方案嗎」。

有：**圖擺在報表旁邊，不是嵌在裡面**。新的 `output_bundle`「Write report
folder」寫出一個資料夾：`report.html` ＋ `images/<id>.jpg` ＋ `defects.csv`
＋ **`recipe.json`**（沒有它，半年後沒人重現得出這份報表 —— 一疊數字沒有配方，
等於一句「我們那時候量到這樣」）。

實際量到的（120 顆合成 lot）：

| | 值 |
|---|---|
| `report.html` | 47 KB → 6000 顆推估 **2.3 MB** |
| `images/*.jpg` | 平均 **13.6 KB／張** → 6000 顆推估 **80 MB** |
| 第二趟（出圖）| **cache hits 120 / misses 0** —— 影像段一次都沒重跑 |

對照：6000 顆**嵌進** HTML 是 566 MB（PNG）／約 80 MB（JPEG base64）而且是
**一個檔案**。那是「打不開」與「寄得出去」的差別。

四件事：

* **C0 判定樹的走訪搬進 core**（`core/pipeline/decide_tree.py`）。報表要寫
  「每一類幾顆」，而 core 不得 import Qt（鐵則 1）—— 只剩兩條路：搬進去，
  或在 core 再寫一份。第二條是這個 repo 踩過最多次的形狀。
  `verdict_rows` 也一起搬（計畫書只寫了四支）：報表的「每一類幾顆」要跟畫面上
  那一條**是同一支函式**算的。留在 UI 的只有主題的那兩個顏色，變成參數。
  ⚠ `CELL_W`/`CELL_H` **留在 UI** —— `layout_cells` 回的是 col/row，
  幾何是無單位的格子，一格幾個像素是畫面的事。第一版連它們一起帶走，
  `tests/test_ui_results.py` 當場抓到。
* **C1 `overlay.write_jpeg`**，跟 `write_png` 共用同一個 atomic 寫法
  （抽成 `_write_encoded`）。JPEG 只給「拿來看的」那一份 —— 壓縮痕跡會在平坦
  區域造成幾個灰階的起伏，而這個 repo 有一整族「幾個灰階」等級的判斷。
* **C2 版面抽成 `core/export/html.py::build_report`**，`output_html` 與
  `output_bundle` 共用。順序照 Results 三段（判定 → 哪幾顆 → 憑什麼）——
  以前第一眼就是一張 6000 列的表，那是從細節開始。
  **表格裡不放縮圖**：6000 個 `<tr>` 各一個 `<img>`，光是 DOM 節點就會讓瀏覽器
  很鈍 —— 改成點一列換圖，整份報表只有**一個** `<img>`。
* **C4 第二趟吃快取。** 出圖那幾張卡要重跑一次 pipeline 才拿得到像素，而那一趟
  的影像段跟剛才那一批逐位元組相同。快取本來就在，只是三個地方沒接上：
  `run_batch_steps` 沒有這個參數、`output_*` 叫的是 `run_defect`、CLI 手上有
  `--cache` 也沒有傳。接起來走 `bctx.rerun(item)` —— 那個 `None` 檢查漏在任何
  一張出圖卡上，症狀都是「報表慢了十倍」而不是一個錯誤。

`<img src>` 那一條測試第一版有個洞：`Path(out) / "/abs/x.jpg"` 在 pathlib 底下
直接變成那個絕對路徑，所以只檢查 `is_file()` 的話，絕對路徑也會過 ——
而那正是「把資料夾寄給別人」的那一刻會破的東西。現在先問「它是相對的嗎」。

### 下一步

Phase D（畫布上的 Output 段：給那五張卡跟判定區同一套視覺）是可選的，沒做。

---

## Results 面板：跑完之後那一頁（2026-08-24）

使用者：「目前的 results panel 太簡略了」。計畫書：
[`docs/plans/F27-results-panel.md`](docs/plans/F27-results-panel.md)。

### R1（真 bug）：畫面上兩個互相矛盾的答案

同一個視窗、相隔約 150px：每一張縮圖說 `bin 3`（樹真的判出來的），而底下的
圖例說 **`bin 1=24`**，還附一行 `accuracy 50% missed 0 false alarms 12` ——
那是用一條**沒有人在用的門檻**算出來的。

成因是「這份 recipe 有沒有門檻在決定事情」這個判斷**散在四個地方，其中三個
沒判**：`_on_decide_mode(True)` 把門檻線關掉，而 `_refresh_spread`、
`_refresh_all`、`_refresh_pipeline`、`_apply_trial_results` 各自無條件設回去。
修法不是補那三個，是把判斷收成一支（`_uses_a_threshold` ＋
`_sync_threshold_line`），四個呼叫端都走它。

F25 之後**每一份 recipe 一打開就是一棵樹**，所以那是所有人都會看到的畫面。

### 三段：判定 → 哪幾顆 → 憑什麼

以前的順序是「縮圖牆 → 一張圖」，而那是從細節開始。兩個新模組
（`CLAUDE.md` §4）：

* **`ui/verdict_band.py`** —— 一列一類：類別名 · bin · 顆數條 · 顆數 · 純度。
  **顆數變成寬度**（沿用 F26 的分流條）。數字全部來自 `tree_scene`，
  跟畫布的分支流量是同一份 —— 不自己數第二份。
  一列是**一片葉子不是一個 bin**（兩片葉子共用一個 bin 是合法的），
  所以點一列的篩選走 defect_id。
* **`ui/results_table.py`** —— 一顆一列、一個數字一欄，欄位跟 CLI 的
  `--csv` 同一份來源。200 顆的時候縮圖牆掃不動，而「照 `cd_median` 排一下」
  「哪幾顆算不出來、為什麼」縮圖答不出來。唯讀。

縮圖的說明文字改成兩行，第一行是**使用者自己取的類別名**（以前整張說明是
`#1 · bin 3 · 0`，而「bright blob」一次都沒出現）；算不出來的那一顆是紅框。

分布圖**預設不再開在「Score」**（樹的 recipe 沒有分數表達式 → 整批落在 0 →
一根柱子），改成「你的第一個問題問的那個數字」；**柱子照類別上色** ——
一根單色的長條答不出「這一段裡是哪一類」，而那才是看這張圖的人在問的事。

### 同一件事不要講兩次

狀態列那句 `Run finished: 24 defects (24 ok, 0 failed) in 0.1 s` 跟工具列上面
30px 是同一件事（只留工具列沒講的那一半，`results.extra_only`）；
Gallery 的 `Sort: score ↓ ×` chip 跟正上方 24px 的下拉是同一件事
（**篩選的 chip 留著** —— 那是判定段點一列之後唯一的退路）。

### 自己種的兩個坑

* **分布圖染的是上一批的類別**：判定段當初排在分布圖後面才更新。
  抓得到它的關鍵是**改變顏色本身**（換 bin），不是只跑第二次 —— 連跑兩次
  一樣的東西，錯的順序也會通過。
* **畫布上的顆數靠別人的副作用更新**：分支流量與分流徽章跟著
  `_refresh_bin_summary` 一起被順手更新，而那一支是「直方圖底下那行字」的事。
  預設不再開在 Score 之後那條路就走不到 —— 徽章顆數整個變 None。
  既有的 `test_the_badge_counts_come_from_route_taken` 當場抓到。
  **一件事要有自己的呼叫。**

### 驗收

`tests/test_ui_verdict_band.py`（14 條，新）＋ `tests/test_ui_results_table.py`
（12 條，新）＋ `tests/test_ui_results.py`（12 → 24 條），另有四個既有 UI 檔
跟著改。core 2117 過、每一個 UI 檔逐一跑過。每一條迴歸測試都做過「把 bug
放回去 → 它變紅」。

三件等使用者定調：Results 要不要變成主視窗的分頁（＝ F26 草案 7）、
純度那一欄要不要留、表格能不能就地改 bin。

---

## 同一個動作，工具列上兩顆鈕（2026-08-24）

使用者：「UI 上有兩個相同功能的鍵 Run all _write 跟 Run trial (run all) 差別在哪
若沒差或差不多 請留一個即可（傾向 trial）」。

**沒差。** 工具列的 `btn_run_all` 與 `Run trial ▾` 選單裡的 `act_run_all`
兩邊都是 `StudioWindow.run_all()`，一個位元的差別都沒有。兩個決定各自都對，
只是沒有互相看到：

* **M7** 把「全跑」收進 `Run trial` 的下拉（理由寫在 `_build_toolbar` 的
  docstring 裡：「兩顆長得一樣的 ▶ 鈕擺在一起，新手分不出差別」）；
* **F16 Stage 5c** 把「Export…」精靈拿掉，空出來的那一格改成整批入口。

拿掉工具列那一顆。留下的是下拉裡那一項 —— 而「跑完之後要做的那件事」搬到它
真的會發生的地方：**Results 視窗**（使用者正在看試跑結果，下一步才是整批）。
工具列因此只剩一顆有顏色的鈕，而那正是這個畫面唯一的主要動作。

### 順手抓到的：`&` 被 Qt 吃掉

使用者叫它「Run all **_write**」—— 那個名字不是打錯，是**畫面上真的長那樣**。
Qt 把單一個 `&` 當成助憶鍵的記號吃掉，於是 `"Run all & write"` 畫出來少一個
`&`、多一條底線。全 repo 有三處中招（`results.py`、`widgets.py` 兩個
`template & regions`），另外三處看起來像但**不是**（視窗標題、`drawText`、
tooltip 都不做助憶鍵處理 —— 那裡寫 `&&` 反而會畫出兩個 `&`）。

所以尺是兩把：一把在**執行期**掃主視窗與 Results 視窗上每一顆鈕與選單項，
一把掃原始碼但**只認會被當成標籤畫出來的呼叫**（白名單，不是黑名單 ——
同一個 `&` 在別的地方是對的）。

### 自己種的兩個坑

* **空的那一段還留著分隔線**：`Templates…` 平常是藏著的，而它那一段本來靠
  `Run all & write` 撐著 —— 那顆走了之後工具列上出現兩條連在一起的線。
* 修的第一版**把整段 `addWidget` 一起跳掉**了，於是 `Templates…` 建了卻沒進
  工具列（會以工具列為 parent 疊在左上角）—— repo 既有的
  `test_every_button_built_for_the_toolbar_is_actually_on_it` 當場抓到。
* 第二版用 `isHidden()` 判斷「這一段看不看得見」，而 **`addWidget` 會把
  widget 包進 QWidgetAction 並在工具列顯示之前把它們全部藏起來** ——
  那時候每一顆都答 hidden，一條分隔線都不會加。要問的是「**我們**有沒有
  明講要藏它」（`WA_WState_ExplicitShowHide` ＋ `WA_WState_Hidden`）。

`isHidden()` / `isVisible()` 這一族在這兩輪裡總共騙過三次 —— 每一次的形狀
都是**「量的東西跟畫出來的東西不是同一個」**。

### 驗收

`tests/test_ui_button_labels.py`（7 條，新）＋ 六個既有 UI 檔跟著改
（`act_run_all` 取代 `btn_run_all`、選單那一項的名字、工具列的顏色分級）。
core 全過、每一個 UI 檔逐一跑過。每一條迴歸測試都做過「把 bug 放回去 → 變紅」。

---

## ADC 上畫布、Measure 段改名，Z-map 走人（2026-08-25）

使用者一次給了四件事，這一輪做掉動手的兩件（另外兩件是問看法，見回覆）。
計畫書：[`docs/history/plans/F28-canvas-and-measure.md`](docs/history/plans/F28-canvas-and-measure.md)。

### ADC 判定區：拖得動、拿得掉

判定區以前**全部唯讀**。加的不是「每個菱形各自拖」——**整區當一個東西拖**
（把手是外框），因為一個一個拖會讓畫面長出樹上沒有的形狀。右上角一顆 ✕ ＝
拿掉整個判定，**先問過**、復原回得來。

**位置不進 recipe**（跟卡片的位置同一個待遇），**樹的形狀一個位元沒變**。
拖的時候就地搬、不重建 —— 重建會把滑鼠從把手上搶走（F26 同一條）。

### Measure 段：GLV → CD → Focus index

只改 `label`（`key` 與特徵名都是 recipe／表達式的鍵，不動）；順序住在
`steps/__init__.py` 的 import 序。**連帶抓到一個漂移**：`step.py` 有一句擋在
使用者面前的錯誤訊息寫死「Use one Gray level card per pair」，改名之後它指著
一張不存在的卡 —— 改成從 REGISTRY 問。

### Z-map 刪掉，而這次的代價很小

沒有任何下游的卡讀 `snr_map` 那條流，兩份 recipe 的 score 也不含 `snr_max`
—— 三份黃金值各少一個欄，**分數與 bin 一個都沒動**。跟 `pattern_ref` 那次
（rsem 準確率 24/24 → 12/24）完全不同。
`algo/snr.py` **不刪**：`snr_signed` 是帶正負號慣例的規範出處，GLV 卡照它做。

### 刪掉之後少了兩個「活例子」

Z-map 是卡片庫裡唯一同時具備這兩個性質的卡：**`category=algo` 卻會寫影像流**
（F17-③ checkpoint 規則的例子）、**key 等於自己吐的流名**（round-trip 對抗
案例的例子）。它走了之後兩條規則還在、但卡片庫裡示範不出來 —— 兩條都不是
改測試蓋過去，是把話寫進去：checkpoint 的數字從 7 變 6 並註明「規則沒變，
是例子沒了」；round-trip 那條改成**斷言現在沒有**，哪天又出現一張它會紅。

第三個同族的：**現在沒有任何一張卡預設讀 `diff`**，兩條「缺上游時要講出是誰
產的」的測試改用 `align_to`（預設吃 `paired`）。

### 驗收

`tests/test_ui_adc_on_canvas.py`（10 條，新）＋ 14 個既有測試檔跟著改 ——
每一條都是換一張還在的卡當例子、或把「例子沒了」寫進去，**沒有一條是放寬
斷言**。core 2099 過、每一個 UI 檔逐一跑過。

---

## 判定面板：一個假問題，與六條草案（2026-08-24）

使用者：「1. ADC Classifier 的 UI 介面 有辦法做得更好嗎（請從 UI/UX 方面提供
設計建議）」→「修 U1 BUG 之後開始動草案」。計畫書：
[`docs/plans/F26-decide-panel-ux.md`](docs/plans/F26-decide-panel-ux.md)。

**這一輪的來源不是讀程式碼**：把 Studio 開起來、載 24 顆、接線、試跑，
再把判定段的每一個狀態截下來 —— 螢幕上看得到的每一個問題各一條。

### U1（bug）：起手的問題是一句假話

按下「Add the decision」之後，第一個菱形寫著 **`0 >= 0`**，而右欄沒有導引式
編輯器。`use_decide(True)` 在還沒有分數表達式時仍然造
`Rule(when="%s >= %g" % ("", 0))`，而 `add_decision` 只在葉子時才問建議 ——
那條恆真的假規則已經把根變成「有 when 的步驟」，所以建議不會被問到。

修法是一支共用的判準 `viewmodel.is_a_constant_expression()`，判的是
**「用不用得到至少一個量出來的數字」**（`parse_expression(...).variables`
是不是空的），不是「是不是字串 `"0"`」。三個呼叫端共用它：`use_decide`、
`add_decision`、`_adopt_threshold_as_a_tree`。

⚠ **解析不出來的表達式不算常數** —— 那是使用者打到一半的東西，不是雜訊。

### 草案 1–6（做了；7 等定調）

新模組 `d4t/ui/threshold_view.py`（`CLAUDE.md` §4：一塊新的面板元件＝一個新模組）：

* **滑桿 → 分布圖**。以前是一根**沒有刻度**的滑桿，拖的時候不知道自己在 60
  還是 200 —— 而這個專案的 Gray level 面板早就在畫分布了（F18），真正在挑
  門檻的地方反而沒有。門檻是圖上一條拖得動的線，兩側染成 yes／no。
  **拖得出資料範圍是刻意的**：「大於 12」在這批最大只有 9 的時候仍然是一條
  完全合法的規則。
* **兩句重複的話 → 一條分流條**（寬度就是顆數）。「幾顆說 yes」以前在一個
  550px 的面板裡出現**三次**。
* **麵包屑**：`Decision tree · step 2 · the no side of “glv_max > 42” ·
  8 defects reach here`。三件事全部都是現成的。
* **類別名是主角，bin 降成它的編號**；**Yes／No 兩邊帶自己的顆數、視覺對稱**
  （沒跑過就不帶數字 —— `Yes 0` 比 `Yes` 更糟）。
* **用詞**：`Split` → `↳ Ask another question`；六個運算子剪短
  （`is greater than` → `greater than`）—— 它們的差別正好在會被截掉的那幾個字。

### 三個我自己種的坑，與兩把量錯的尺

坑：建議出來的第二步跟第一步問了**一模一樣**的問題（切出 0 yes / 13 no）；
草案 6 的長標籤讓那一列橫向溢位（**高度是免費的、寬度不是**）；分布圖每重建
一次漏一個看不見的 widget（`clear_layout_parked` 清的是**版面裡**的東西）。

尺：**`isVisible()` 對一個沒有 `show()` 過的面板永遠是 `False`** —— 於是
「有沒有畫分布」跟「沒資料時不要畫」兩條都通過，而其中一條什麼都沒驗；
**「控制項的右邊在哪」抓不到溢位** —— 多出來的 5px 會變成一根捲軸，而那根
捲軸正是要擋的東西。第三把也是同一個形狀（數字框寬度用「猜出來的 26px」，
而實際文字區少 1px），它把正在畫錯的版面判成通過。

**這一輪每一條迴歸測試都做過「把 bug 放回去 → 它變紅」。**

### 驗收

`tests/test_ui_decide_panel_redesign.py`（24 條，新）＋
`tests/test_decide_tree.py` 的 U1 四條 ＋ `tests/test_ui_tree_edit.py` 改寫五條
（THIS BATCH 只剩葉子、滑桿變分布圖、運算子的字剪短）。
core 全過、每一個 UI 檔逐一跑過。

---

## ADC 判定段：三個「我們自己發明的上限」（2026-08-24）

使用者：「ADC Classifier 幫我仔細查察有沒有什麼 Bug or 可優化地方，
例如 我知道搖桿只能填最大 1」。那一句是入口，而底下是同一個形狀的三件事。

### A1：導引式問題的數字框被夾在 −1…1

`tree_panel._range_for` 在沒有分布時**自己編一個範圍**（`value ± max(|value|, 1)`），
而剛加進來的一步 `value` 是 0 → 範圍是 −1…1。**數字框跟滑桿共用同一組上下界**，
所以想問「`cd_median` 大於 6.5」的人，那個 6.5 打不進去。

實測比使用者說的更廣，三種情況都卡：

1. **還沒試跑**（新加的一步）→ −1…1；
2. **試跑過，但那個數字每顆都一樣**（或整批只有一顆）→ 一樣 −1…1，
   而**量到的 6.5 就在手上**，只是被丟掉了；
3. **就算有分布**，數字框也被夾在觀測範圍 ±5% —— 而「大於 12」在這批最大只有 9
   的時候仍然是一條完全合法的規則（那正是怎麼寫一條今天抓不到、明天出事才抓得到
   的規則）。

修法分兩件事，因為它們本來就是兩件事：

* **數字框不夾人**。門檻的合理範圍隨卡片天差地遠（灰階 0–255、CD 幾個 px、
  面積上萬 px²、z 分數是負的、百分位 0–100）—— 沒有通用的上下界，不要假裝有。
* **滑桿只在真的有分布時出現**（`_slider_range` 沒資料回 `None`），
  而且沒有它的時候要說出為什麼、指向拿得回它的動作。
  資料只有一個值時**用那個值撐開範圍**，不要退回憑空的 ±1。

### A2：判定段的表達式沒有 unknown-feature 檢查

`validate` 對舊的 `score.expr` 一直有這道檢查，而 F21-D 加上 `decide` 之後那一段
變成「有 decide 就整段跳過」—— 理由是對的（有 decide 時 `score.expr` 根本不會跑），
但**替代的檢查從來沒有補上**。

於是打錯一個數字名字的下場是：**validate 全綠、畫布正常，跑起來每一顆都失敗**。
而 F25 把二元門檻的 UI 整個拿掉之後，`decide` 是使用者唯一走得到的路 ——
也就是說唯一有人用的那條路，lint 覆蓋比沒人用的那條還少。

新的 `_decide_unknown` 跟 `engine._eval_decision` 逐項對齊：`let` 是**累加**的
（第 n 行看得到前 n−1 行、看不到後面）、有 `fill` 的多一個 `<名字>_missing`、
有 `scale` 的多一個 `<名字>_raw`。少了後面那兩條，它會對一份**完全正確**的
recipe 大叫 —— 那比沒有檢查更糟。

### A3：bin 的數字框寫死 0–999

四個數字框各自 `setRange(0, 999)`，而**引擎與 KLARF 寫回都沒有這個上限**
（`CLASSNUMBER` 就是一個整數欄）。廠內的分類碼四五位數很常見 ——
打 1200 進去安靜地變成 999，而寫回是不可逆的。
順帶修掉 `_fresh_bin` 的 `next()` 沒有預設值（用光了會漏出 `StopIteration`，
而它是在一顆按鈕的 handler 裡被叫的）。

### 這三件的共同形狀

**都是我們自己發明、而且擋得住真實用法的上限。** 值得記下來當一條判準：
一個輸入的上下界，如果不是由**這個東西本身**決定的（像 ParamSpec 的 min/max
是那張卡的演算法決定的），就不要發明一個 —— 尤其不要拿「這一批剛好量到什麼」
去夾住「使用者想問什麼」。

### 掃過但沒問題的

滑桿旁邊那一行的分母**是誠實的**（量不出那個數字的顆根本走不到這一步，
`rows_reaching` 與 `count_yes` 對得起來）；`let` 那幾格是自由文字沒有夾人；
判定樹的四支編輯操作對過期路徑都是安靜的 no-op（B4 那一輪修過）。

### 驗收

核心 2,095 passed / 63 skipped、UI 逐檔全綠。三條都驗過「把 bug 放回去會紅」
（A1 四條、A2 三條、A3 兩條）。

---

## Bug 獵捕：一個真的、五個疑似，全部修掉（2026-08-24）

使用者：「有沒有BUG或疑似BUG 列出來」→「修復bug並寫性質測試」。
跟上一輪的結構體檢不同，這一輪只找「會算錯」的東西。

**grep 在這個 repo 收穫很低** —— 程式碼很小心，明顯的模式幾乎沒有。所以主力是
**性質測試**：先寫下「這裡的正確答案是什麼」，再讓機器去撞。1,600+ 組動態測試，
七個面。下面每一條都是撞出來的，不是讀出來的。

### B1：接一條新線，會順手剪掉同一個來源餵到「別的埠」的線

`_drop_conflicting_edges` **挑**線挑得很精確（比對 `dst_in`），**剪**的時候卻只帶
`src_out` —— 而 `remove_edge` 的語意是「符合這個 src_out 的**全部**」。於是
`load.test → subtract.a` 與 `load.test → subtract.b` 兩條並存時，把別的卡接到 `b`
會**連 `a` 那條一起剪掉**。而 `a` 的參數還留著 `test`：畫布上沒有線、卡片卻還指著
那條流，引擎退回「執行順序上最後一個寫它的人」用猜的。

線性時猜得中、分岔時猜錯，而且跑得完、有數字 —— **F9／F10 整整兩輪在防的形狀，
而在這之前沒有任何測試在守它。**

`or None` 是第二階：空字串在 `remove_edge` 裡本來就是「精確比對空埠」，
`or None` 把它變成「全部」。

### 那把尺：`tests/test_ui_canvas_truth.py`

不變量一句話：**一張卡的某一格輸入指著一條影像流 ⇔ 畫布上有一條線落在那一格。**
兩個方向都要成立，而兩個方向壞掉的樣子不一樣（參數有線沒有 → 引擎用猜的；
線有參數空 → 那張卡根本不處理它）。

400 組隨機的接線／剪線序列 × 25 步，每一步之後檢查。B1 就是它抓到的 ——
六種不同的重現路徑，涵蓋 `subtract.a/.b`、`glv_stats.source`、`align_to.search`、
`normalize.streams`、`roi_cross.pick_source`。

⚠ **第一版的 fuzzer 有兩個自己的 bug，而它們的形狀值得記住：**

1. `Edge` 的建構式是 `(src, dst, src_out, dst_in)`，JSON 是 `[src, src_out, dst, dst_in]`
   （檔案裡寫明是刻意不同的）。我按 JSON 順序傳，於是每一條線的 `dst` 都是一個
   不存在的節點 → 全部被忽略 → 引擎退回隱含綁定 → 我以為分岔壞了。**測試腳本
   自己錯的時候，它會非常有說服力地指控別人。**
2. 剪線的方法叫 `_on_edge_removed` 不叫 `_disconnect`，而我 `except AttributeError: break`
   —— 於是**剪線那條路根本沒被掃到**，掃了 400 組等於只掃了一半。

第三個是收斂條件：接對之後 fuzzer「抓到」十幾個違反，全部是**拿剪刀去剪空氣**
（剪一條不存在的線）。剪刀是畫在線上的，那不是使用者做得到的動作。
**一條抓得到不存在的問題的測試，跟一條什麼都抓不到的測試一樣沒用。**

### 另外五條

* **B2** `KlarfDoc.save()` 是整個 `core/` 裡唯一非 atomic 的寫檔（違反鐵則 5）。
  今天零呼叫者，但它是 `KlarfDoc` 上一個叫 `save` 的公開方法 —— 下一個要寫檔的人
  很自然會用它，然後在最重要的資產上得到一個非 atomic 的寫入。改成
  `.tmp` + `os.replace`，vendoring 檔頭記下這是 d4t 對上游唯一的行為改動。
* **B5** 剪線的退路：沒有流名時 `stream and …` 整條短路，直接跳到「拿掉整對」——
  兩張卡之間有兩條並排的線時按一把剪刀會斷兩條。埠問得出來就用埠。
* **B6** `plan.notes` 一句都沒有出口。inplace 一格都不填是**刻意的安全預設**
  （寫回不可逆），但使用者看到的只有「0 row(s) changed」，答不出「那我該填什麼」。
  `klarf_out` 早就把理由寫好了。
* **B3** `set_edge_ports` 沒有呼叫者，而 `studio.py` 的 docstring 還在描述那條
  F9-9 就不存在的流程 —— 而且它就寫在那段程式碼的正上方。
* **B4** 樹的路徑定址「非 y 一律當 n」：壞路徑不是回 None，是安靜地指到一個
  **真實但錯的**節點。今天碰不到（四支編輯操作都先用 `tree_node` 檢查），
  但「壞輸入指到一個合法的東西」是這個 repo 最怕的形狀。

### 第二把尺：`test_card_invariants.py` 的 I7

I4 問的是「同一份 recipe，冷跑與熱跑一不一樣」。**缺的是另一半**：改了參數之後，
帶著舊快取跑出來的還是不是對的答案。I7 對每一張卡的每一個造得出第二個值的參數
各問一次（68 組），把「簽章看不見參數」那個洞放回去會紅 33 條。

### 掃過、撞不出問題的

26 張卡 × 5 種病態影像（全黑／飽和／常數／單一亮點／極端梯度）零難看例外零 NaN ·
引擎資料路由對著解析解全中 · KLARF 三種寫回模式未變動區塊逐位元組相同 ·
`RecipeModel` 600 組 × 60 步隨機操作零違反 · 輸出層對付得了欄位不齊／NaN／inf／
1e308／中文欄名／失敗顆 · algo 130 支公開函式的退化輸入掃描（會 raise 的逐一追過，
都不在真實路徑上）· route_by 的欄位型別疑慮已排除（`klarf_core` 存原始 token）。

**沒掃到的三塊**：TIFF page 對應、KLARF 變體、真正的畫面 —— 都要真實資料或截圖。

### 順帶

repo 自己的守門測試當場抓到我寫的 `Path.write_text(newline=…)`（3.10+，而公司機
的版本不由我們決定）。那條守門是掃原始碼文字的，連我解釋它的那段註解都抓 ——
對這種事寧可過度警覺。

### 驗收

核心 2,086 passed / 63 skipped、UI 逐檔全綠，新增 4 份測試共 82 條。
**每一條新的迴歸測試都驗過「把 bug 放回去會紅」**（B1 兩條、B5 一條、
B2 兩條、B4 兩條、B6 兩條、I7 三十三條）。

---

## 全專案 review：八條發現，全部修掉（2026-08-24）

使用者：「請review這整個專案」→「全都一起修一修」。**不是新功能，是把
已經在那裡但沒有人盯著的三個角落補上。** 三個角落有同一個形狀：它們都不在
「改完之後會跑到的那條路」上 —— 而這個 repo 最擅長防守的，正好是那些路。

先講**沒有壞的**（實跑驗過，不是讀 code 推論的）：workers=1 vs 4 逐項相同、
冷熱快取逐項相同、KLARF 逐位元組無損、recipe round-trip identity、UI viewmodel
對 decide/tree/route_by 無損、表達式 parser 六萬次亂數輸入零逃逸、沒有
eval/exec/pickle/shell=True。**引擎是健康的，問題全在邊界。**

### CI 紅了三週，而 commit 訊息裡記的原因已經過期

`docs/plans/F19` 那一輪記著「CI 全紅是 Actions 拿不到 runner（3 秒結束、沒有
log）」—— 那個判讀當時對。但最近幾次 runner 有拿到、跑了 **1:39:09**、然後掛在
**一條真的斷言**上，而沒有人再去看，因為結論已經下過了。

病根：`theme.TOKENS` 是**就地**更新的模組層 dict（刻意的 —— 各模組都 import 過
它），而 `test_theme_is_neutral_and_flat` 斷言的是「現在裝著的那一組」，不是
「light 那一組」。`test_ui_gds_panel.py` 的 module fixture 切成 dark 沒還原、
字母序排在前面 —— **一個檔案一個行程跑（開發者的做法）全綠，一個行程跑整套
（CI 的做法）紅**。本機 24 秒重現得出來。

兩個 bug 分開修：fixture 洩漏（conftest autouse ＋ gds_panel 自己還原），
以及斷言本身讀了環境狀態（改讀 `PALETTES["light"]`）。
**dark 盤的冷色調是刻意的**（使用者定調）—— 實測感知彩度 C*ab：light 0–1.1、
dark 3.8–5.1、被否決的暖奶油 3.7–7.5，**dark 與「玩具」在這把尺上分不開**，
所以不去調寬容差讓它同時涵蓋兩組（調寬之後它就再也擋不住暖奶油了）。

順手把 `ci.yml` 拆成核心 + UI 逐檔 —— `AGENTS.md` §5 早就寫了原因，而 CI 是
唯一還在單一行程跑整套的地方。2078 + 911 = 2989，跟 collect-only 逐項相符。

### 判定邏輯有兩份，而第二份已經漂了

`store.rescore` **自己實作了一次判定**：讀 `recipe.score`、比 `threshold`、
分 below/above —— 它從來沒有看過 `decide`。F21–F25 把整個判定段搬進
`DecideSpec`（F25 更把二元門檻的 UI 整個拿掉）之後，那一份就漂了：

* 正規的 decide recipe → 「the expression is empty」。使用者做的是一棵樹。
* 兩個區塊都有值的過渡期 recipe → **安靜地**用廢棄的 `score` 算完、回報
  `n_errors: 0`、每一顆 bin 0，而 `--save-as` 把那份錯的**存成一個新 run**。

這正是 `ARCHITECTURE.md` 開頭那句「複製出來的那份會漂移」的形狀。
修法是抽一支 `batch.redecide()`（走引擎的 `_eval_score`，它自己會分流），
`apply_lot_scaling` 與 `rescore` 都叫它。

順著這條抓到 `apply_lot_scaling` 不冪等：`<name>_raw` 被無條件覆寫，跑第二次
寫進去的是已經 z 化過的值 —— **原始量測值就此消失**。今天炸不出來（各只叫
一次），但它是公開 API，而上面那個修法就是第二個呼叫點。

### 文件漂移：唯一沒有測試守的那條規矩

`CLAUDE.md` §0 第一句話就是「同一件事只寫在一個地方」，而這個 repo 用測試守住了
不得 import Qt、不得有廠內識別碼、搬運清單不得過期、每張卡都要有 help、3.9 語法
—— **唯獨沒有任何東西守著文件之間的交叉引用**。於是：`HIDDEN_STEPS` 少兩張卡
（而 `CLAUDE.md` 每個 session 都會被讀進去）、`ARCHITECTURE`／`ROADMAP` 還畫著
F24 §5 解散掉的八段、README 說 20 張卡（實際 26）、8 條指向不存在章節的 §ref。

`tests/test_docs_links.py` 補上這一層。它抓不到「章節存在、內容不對」那種
（`AGENTS.md` 寫「開發流程見 §6」而那是 vendoring 對照表，開發流程在 §4）——
所以它是**下限**，不是保證。

### 記錄但不動作的兩件

* **`studio.py` 5,244 行 / 229 方法 / 344 屬性**。拆分壓力已經在影響新功能該放
  哪裡（F22 的 commit 訊息就寫著「不塞進已經 5000 多行的 studio.py」）。
  但**現在不動它** —— 黃金值是壞的（F21 §6），沒有那把尺就證不了「改了但數字
  沒變」。只把已經在實行的止血做法（新面板開新模組）寫成明文規矩。
* **bundle 佔掉 pack 的 88 MB / 46%**（328 個版本），而且 888 KB → 1712 KB
  只花了八天。兩條解法都會改到公司機的搬運流程，使用者定調「先不動，我再想」
  —— 所以 `AGENTS.md` 只記下實測水位，把「包的大小不是限制」那句話標註成
  「2026-08-17 在 888 KB 上確認的」。

### 驗收

核心 2012 passed / 63 skipped、UI 逐檔全綠、offline tools 86 passed、
新增三份測試共 37 條。**每一條新測試都驗過「把 bug 放回去會紅」**。
四條不變量重驗、表達式 fuzz 重跑、CLI 端到端正確率 100%、3.9 語法零違規。

---

## F25：判定段要有人會用（2026-08-24）

使用者看過 F24 的成品之後的四句話，全部是同一件事的四個面 ——
**引擎做完了，但入口是一格空白**。計畫書：[`docs/history/plans/F25-adc-usable.md`](docs/history/plans/F25-adc-usable.md)。

* **閃退（最優先）**：`widgets.clear_layout_parked()`。面板是「改一格就整段
  重建」的，而改那一格的訊號**還在被拆掉的那個 widget 的堆疊上** ——
  `setParent(None)` 讓 Python 成為唯一持有者，layout item 一丟就當場解構，
  那是 use-after-free。offscreen 重現不出來（跟真實平台的事件流有關，
  所以是「有機會」閃退），因此**從結構上移除**而不是猜：拆下來的 widget
  藏起來、參考留著，解構排到下一輪 event loop。三個面板共用同一支，
  迴歸測試驗的是「拆完之後還碰得到它」與「按鈕在自己的 clicked 裡把整個
  版面拆掉不會爆」。
* **加 ADC 卡＝畫布上直接有樹**（不用勾任何東西）：`add_decision()` ——
  現有門檻變成樹的第一個問題（不丟東西）、只有一片葉子就給一個起手問題、
  右欄跳到那一步、**最後 `fit()`**（判定區長在卡片右邊，不 fit 的話使用者
  按了鈕畫面上什麼都沒發生）。「Sort into several classes」勾選框拿掉，
  多類別成為預設；二元門檻只留在舊 recipe 上，配一顆換過去的按鈕。
* **問題不用打的**（核心）：`[哪個數字 ▾][比什麼 ▾][多少] ＋ 滑桿`，
  滑桿範圍取自**流到這一步的那些顆**的分布，底下一行即時的
  「34 of the 48 defects that reach here say yes」拖的時候就地更新
  （不重建 —— 重建會把滑桿從手上搶走，所以 `_typing` 的範圍加上滑桿與下拉）。
  複合條件拆不成三格就**誠實地**回算式框（`parse_simple_condition` 認不得
  就說認不得，猜錯會安靜地改掉使用者的判定）。
* **新的一步不是空白**：`suggest_condition` 挑這一批分得最開的數字、門檻放
  中位數（使用者自己的 working numbers 優先）。沒跑過就不填 —— 沒有分布的
  時候硬猜比留白更糟。
* **裁字**：規則列拆兩行 —— 實測 437 px 的欄要塞 590 px，名字那一格被壓成
  92 px，**`not measurable` 在畫面上變成 `measurable`**（意思相反的字）。
  導引式那一列固定比較與數值的寬度；按鈕不再撐滿整列（撐滿讀起來像標題）。
* **分流上畫布（F25-B，使用者定調「繼續做 B」）**：`ui/route_badge.py` ——
  站在所有卡片**前面**的徽章（不可拖、不可選、沒有埠、一條虛線箭頭指進第一
  張卡）。上面三件事：看哪一欄、對照表、**現在這一顆走哪一條**（粗體，跟著
  換 defect 動）；試跑後每條路的顆數**從 `route_taken` 讀**（F19 當初就是為
  了這件事寫它）。
  使用者接著問「pre-filter 需不需要獨立一張 card」「放進 ADC card 裡是否
  合理」——**兩個都是不要，理由是同一條：時間順序**。pre-filter 在任何卡跑
  之前、ADC 在全部跑完之後，是同一條 pipeline 的兩端；把最先發生的事畫進
  最後發生的框裡就是畫布把順序講反了。編輯器裡它們**本來就在一起**
  （`RouteByBox` 在判定欄最上面，由上往下讀正好是時間順序）——
  要分開的只有畫布。兩者因此共用同一套視覺語言（虛線框、大寫標題、不是
  卡片、點了去同一欄），tooltip 互相指認。
* 測試：`test_guided_condition.py`（26）＋ `test_ui_tree_edit.py` 改寫成
  驗導引式（19）＋ `test_ui_route_by.py` 補徽章 7 條（不是卡片、站在最前面、
  點了發訊號、顆數來自 route_taken、沒有分流就沒有徽章）。
  core 1839 過、每一個 UI 檔逐一跑過、黃金值不動。

---

## 收尾三件：routes-drift、七段、missing ⇒（2026-08-24）

使用者對前一輪留下的三個問號一句「那三件事接著做」全數放行：

* **`routes-drift` lint**（F23 §5 選項 A 的配套）：warning ——「刻意不同
  正是分流的目的」。誤報的顧慮用三道收窄解掉：只在 `route_by` 存在時看
  （kind 選路的多 route 不同設定是常態）、影像流／區域參數不比（兩條路
  各接各的流）、一對 route 一張卡講一次。detail 講**差在哪幾格**
  （`metrics is glv_max on route 'a' but glv_mean on route 'b'`）。
* **八段變七段**（F16 的段落，使用者點頭）：Algo 從 `GROUP_ORDER` 與
  `LibraryPanel.GROUPS` 拿掉 —— 算式、補值、跨顆換算全部住進判定，那一段
  清空之後留著只是一個永遠空白的抽屜。`GROUP_ALGO` 常數留給外掛相容；
  被吸收的兩張卡（仍收在 `HIDDEN_STEPS`）改掛 `GROUP_ADC`（它們的功能
  現在就是判定段的一部分）。「Algo 卡不吃影像流」那條界線的測試改成
  點名那兩張卡＋外掛的 GROUP_ALGO 卡，繼續守著。
* **`Let.fill`（missing ⇒ 用 __，F24 ⑤ 的後一半）**：working number 一行
  的第三個屬性。非空時，這一行用到的數字缺了就用 fallback 頂著、
  `<name>_missing` 旗標寫 1（**有 fill 的行每顆都寫旗標**，0 或 1 ——
  CSV 那一欄才完整；判定樹第一步問 `<name>_missing > 0` 就是它的形狀）；
  留空＝照舊整顆失敗（嚴格附加，serde 有才寫）。壞的 fallback 是
  `bad-let` error。「跟整批比」的統計**也排除這一行自己補過值的顆**。
  面板的 let 行改成**兩行**（算式一行、`if missing → __ · 跟整批比` 一行
  —— F22 量過七個元件擠一行會互相切字）。F24 ⑤ 至此全部完成，
  `feature_fill` / `feature_math` 只剩「使用者確認夠了再刪」那一步。
* 順手修兩個現撈的 UI 蟲：工具列的 Route 下拉在單 route 時藏不掉
  （QToolBar 的顯示要走 addWidget 回傳的 QAction，不是 widget）；
  「+ Add a line / rule」被 `shape="square"` 的 QSS 釘死寬度切字。
* 測試：`test_let_fill.py`（8 條）＋ `test_route_by.py` 補 4 條 drift ＋
  `test_ui_f16_stages.py` 改鎖七段。全套 core 1812 過、黃金值不動。

---

## F23 期3：「跟整批比」的兩趟判定（2026-08-24）

§8 的 lot_stats **不是一張卡** —— F24 §5 定的家：它是 working number 一行的
屬性（`Let.scale`）。跨顆的數字（「這一顆比整批亮多少」）在單顆的
`run_defect` 裡根本不存在，所以是兩趟：

* **`Let.scale`**：`""`（照算）／`"z"`（robust z：(值−整批中位數)/(1.4826×
  MAD)，跟 `algo/enhance.py` 同一個係數）／`"percentile"`（0–100 midrank）。
  serde **有才寫**（嚴格附加）；打錯的值是 `bad-let` error（安靜當成照算＝
  「看起來在跟整批比、其實沒有」）。
* **`batch.apply_lot_scaling(recipe, rows)`**：`run_batch` 兩條路徑（循序／
  平行）都在回傳前呼叫 —— CLI、Studio 試跑、測試拿到同一份數字，
  workers=1/2 逐項相同免費。原始值改名 `<name>_raw` 留著（F19）；
  **`feature_fill` 補過值的顆不進整批統計**（`<變數>_missing == 1`，A1 的
  規矩），但自己仍拿到換算值；然後**用換算後的值重算判定**（rescore 那條
  路：`_eval_decision` 跑在只有數字的 Context 上，不重跑影像；換算過的行
  不重算、沒換算的行照原順序重算 —— 用到換算值的拿到新值）。
  失敗的顆一根手指都不碰（鐵則 7）。
* **UI**：判定面板每一行 working number 多一格下拉
  （as measured / z vs the batch / percentile in batch），tooltip 講明
  「整批換算要跑過整批，預覽顯示的是原始值」。
* 測試：`tests/test_lot_scaling.py`（9 條：嚴格附加、serde、z 與 percentile
  的數學、補值不進統計、失敗顆不碰、未換算行跟著新值、run_batch 兩路徑
  逐項相同）。

---

## F23 期2：分流的 UI（2026-08-24）

§6 的三件照計畫落地，外加一件計畫書沒點名但**不做就全錯**的：

* **model 抱得住整份分流 recipe**。`RecipeModel` 仍然一次編一條 route
  （§6 第一期不動的那條），但 `from_recipe` 把其他 route 的排列／專屬節點／
  線與 `route_by` 原樣收著，`to_recipe` 合併回去（共用節點以正在編的版本
  為準）；快照／undo 也帶著。少了這個，載入分流 recipe 再試跑，**其他
  route 會安靜地消失**（舊 `to_recipe` 只寫得出正在編的那一條）。
  round-trip 對 `to_json_dict` 是 identity（測試釘住）。
* **route 切換器**（工具列 `Route [b_route ▾]`，單 route 收起來）：切＝
  「收回去再拿出來」（`to_recipe → from_recipe`），畫布整個跟著換；
  代價是 undo 堆疊重來（兩段不同的編輯歷史）。
* **預覽跟著這一顆走**（§6-2）：`set_defect_index` 逐顆
  `resolve_route`（跟引擎同一支），走的 route 跟畫布不同就自動切；
  資料集標籤**常駐**寫出 `CLASSNUMBER=2 → route "b_route"` ——
  畫布剛剛為什麼跳，答案就在眼前。route_by 的欄位在載資料／載 recipe 時
  自動補進 `fields`（同 `run_batch` 的規矩：缺才補、補「現有 ∪ 這一欄」）。
* **`RouteByBox` 編輯區塊**（`ui/route_panel.py`，判定欄**上方** ——
  它在跑之前決定，判定在跑完之後，由上往下正好是時間順序）：欄位下拉吃
  這份 KLARF 的欄名、值→route 對照表、「Everything else →」含
  `(fail that defect)`（default 留空＝失敗，站點政策的另一半）。
  整包寫回 `model.set_route_by`（一次改動一步 undo）。
* 預覽的 `kind` 修正：route_by 存在時 model.kind 是 route 鍵
  （"particle_route"），把它當 kind 傳給 `run_defect` 會讓 load 卡把資料
  認成不存在的型別 —— 預覽改傳 `dataset.kind`（kind 是資料的身分，route
  由引擎逐顆解）。`load_recipe_path` 那句「no '%s' route」的警告對分流
  recipe 不再誤報。
* 測試：`tests/test_ui_route_by.py`（11 條：round-trip identity、改 A 路
  不動 B 路、undo 不丟另一條、切 route 無損、預覽自動切＋標籤、編輯區塊
  讀寫、toggle 清掉可 undo）。截圖：`f23_route_ui.png`。

---

## F24 ③④：判定樹的編輯互動＋幽靈線（2026-08-24）

* **點菱形／托盤 → 右欄變成那一步的編輯面板**（`ui/tree_panel.py`，跟點卡片
  同一條路）：Question ＋ Insert a number ▾（F21-B 第四個使用者）、Yes/No
  各自是「一個類別（名字＋bin＋Split…）」或「另一步（摘要＋Edit 跳過去）」、
  THIS BATCH（47 arrive here → 11 yes · 36 no，沒跑過一個字不畫）、
  Insert step above／Remove step。
* **`rules` 模式在第一次點菱形時無損轉樹**（`RecipeModel.ensure_tree`，
  rules 清空 —— 兩個都在是 `ambiguous-decision`）；`DecidePanel` 在樹模式
  收起規則清單，指去畫布（同一件事不擺兩個編輯入口）。
* **樹的編輯 op 全在 viewmodel**（路徑當身分、整棵 immutable 重建、一動作
  一步 undo）：`set_tree_when/set_tree_leaf/split_tree_leaf/
  insert_tree_step_above/remove_tree_step`。加一步＝新問題的 yes 掛新類、
  原本那類留在 no（同「在 otherwise 前插一條規則」的形狀）；拿掉一步＝no 邊
  接回上游，yes 邊掛著子樹時先問過使用者。
* **雙擊入口卡收合整棵樹**成一張小卡（檢視狀態，不進 recipe）。
* **幽靈線**：滑鼠停在菱形上 → 它用到的每個數字畫一條**臨時**點線回產出它
  的卡（卡片同時亮 hover 框），`let` 中間值指回入口卡。來源從**宣告**推
  （`RecipeModel.feature_owners`，第一個宣告的人贏）—— 所以它不說謊。
  樣式跟資料流的線刻意不同（點線＋`contrast · from Gray level` 標籤），
  移開就消失、從不存檔。
* **Preview 的 Path**（F24 §8）：Verdict 旁一行
  `Path: cd_deq_missing > 0 ? no → contrast > 120 ? yes`（樹模式；rules 模式
  講第幾條規則對上），同時那條路**在樹上亮起來**（沿路分支加粗全彩）。
  資料是引擎記的 `meta["decide"]["path"]`，人話由 `tree_scene.path_text`
  沿樹重走組出來。
* **`feature_math` / `feature_fill` 收進 `HIDDEN_STEPS`**（F24 §5 定調：
  算式住進 working numbers、補值是樹第一步的形狀）。收不是刪：registry 照認、
  舊 recipe 照跑、F21 的測試直接從 registry 拿。卡片庫的 Algo 段因此清空 ——
  **GROUP_ORDER 沒動**（F16 的八段是使用者定的，動之前要再點一次頭）。
* 測試：`test_ui_tree_edit.py`（15 條：轉樹清 rules、路徑尋址、split 保留
  原類、remove 接回 no、undo 逐步、面板讀寫 model、HIDDEN_STEPS 收不是刪）＋
  `test_ui_tree_canvas.py` 補 6 條（收合、幽靈線出現與消失、路徑亮起、
  path_text）。截圖：`f24_edit_step.png`、`f24_ghost_path.png`。

---

## F24 ②：判定樹上畫布 —— 唯讀渲染（2026-08-24）

判定區照 mockup 定稿長進畫布（`d4t/ui/tree_scene.py` ＋
`PipelineCanvas.set_decision`）：

* **判定區**是畫布右側一塊淡紫底虛線框（`seg_adc_bg`，跟著平移縮放）；
  量測卡到它之間**刻意沒有存的線**，只有一句淡淡的 `numbers →`。
* **入口小卡**（funnel ＋ Decision ＋ ƒ working numbers ＋試跑後的「N in」）
  永遠恰好一個、不可拖不可刪；點了跳到判定編輯（`decision_clicked` →
  `show_score_page`，跟 score 那條路同一個 handler）。
* **菱形＝一步一問、yes 往右 no 往下**；`rules` 模式畫成等價鏈狀樹
  （`rules_to_tree`，F24 ① 證過無損）——樓梯狀，`(anything else)` 虛線框。
* **分支流量拿每一顆的特徵把樹重走一遍**（`flow_counts`）——
  `meta["decide"]["path"]` 刻意不進結果 JSON（動 schema 動到黃金值），而
  F24 ① 的 path-replay 測試證明「拿 features 重走＝引擎走的那條」。
  守恆是構造上的：走到 p 就把 p 的每個前綴 +1，菱形 in ≡ yes+no。
  表達式走不動的顆整顆不計（記半條路會把守恆弄破）。
* **托盤**：類別色條（`leaf_hex`，bin 0 灰、其餘輪調色盤）＋名字＋顆數＋
  「x/y real」＋微型純度條（有 ground truth 才畫）。
* **未試跑：數字誠實地不在**（F18）——`counts=None` 時整區一個數字都不畫；
  走二元 score 的 recipe 沒有判定區（那條路的判定住在門檻滑桿）。
* 純函式（layout／counts／stats）與圖元分開 —— 流量守恆、樓梯佈局、
  「沒跑不畫 0」全部 headless 測得到（`tests/test_ui_tree_canvas.py`，14 條）。
* 截圖：`scratchpad/f24_tree_before.png`（形狀在、數字不在）與
  `f24_tree_after.png`（48 → 1/47 → 11/36 → 16/20 → 20/0，跟 F22 那批
  實跑逐項一致）。

---

## F23 期1：route_by 引擎（2026-08-24）

四題使用者一句「照提案著做」全數定調（default 兩種都支援、第一期選項 A、
預覽自動切 route、lot_stats 併第 3 期），期1 當天做完。

* **`RouteBy{column, map, default}`** 是 recipe 頂層的嚴格附加區塊（不在就
  一個位元不動；round-trip identity）。欄名讀進來就正規化成大寫，值先 strip
  再比字串。
* **route 在 `run_defect`／`run_defect_cached` 裡自己解**（`resolve_route`），
  不是叫呼叫端解 —— batch、Studio 預覽、CLI 自動拿到同一個答案，「預覽跟批次
  走不同路」從結構上長不出來。`kind` 只剩資料身分（`meta["_dataset_kind"]`）。
* **快取簽章吃 route 鍵**（`image_segment_signature(recipe, route)`）：
  兩條路各自一份條目，換 route 不會拿到隔壁那條路的影像。
* `route_taken` 特徵（sorted routes 的索引）＋ `meta["route"]`，**只在
  route_by 存在時寫**（黃金值三份不動的前提）。對不上而沒 default 的那一顆
  `ok=False`，訊息講出值 X 不在對照表裡（`route_miss_message`）。
* `run_batch` 開跑前自動補欄 —— 但**只在有顆缺這一欄時**，而且補的是
  「現有欄位 ∪ 這一欄」（`fill_fields` 是整份換掉，只補一欄會把 carry 進來的
  其他欄洗掉；每顆都有＝一個位元不動，測試靠這個手排路線）。
* `run_batch_steps`：route_by 存在時走 map/default 指到的**每一條** route 的
  跨顆卡，同一個節點只跑一次（Output 寫檔不可逆，寫兩次是覆寫不是保險）。
* **兩條 error lint**（`bad-route-by`：空欄名/空 map/指到不存在的 route）＋
  `route-not-reachable` warning；route_by 存在時 validate 檢查**全部** route、
  不再對 kind 報 `unknown-route`（route_by 覆蓋 kind 選路，§4.2）。
* CLI：開跑前查欄位在不在（`missing_columns_of`，手上有 KlarfDoc 答得出
  「它有哪些欄」）；跑完印分流結果＋**掉進 default 的顆數**＋一顆都沒走的
  route（寫了沒人走的路最容易爛）。
* `make_sample.py --class-by-truth`（**選配**，預設逐位元組不變 ——
  `test_export_klarf` 倚著「原檔 CLASSNUMBER 全 0」在算改動列數）：
  REAL=1、NUISANCE=2，分流的合成資料一行指令就有。
* 驗收全過（`tests/test_route_by.py`，27 條）：走對路 24/24、B 路的顆**沒有**
  A 路的特徵、workers=1/2 逐項相同、快取冷跑＝熱跑、兩條 route 簽章不同、
  黃金值與全套 core 測試不動。

---

## F23 計畫書：分流（route_by）—— 議程，未動工（2026-08-24）

使用者定調 pre-filter 的真正需求：「**不同的 Classnumber 走不同的『卡片』**」
—— 不是判定段的條件（那個每顆還是全跑），是 Class 2 根本不跑 A 組卡。
計畫書在 [`docs/history/plans/F23-route-by.md`](docs/history/plans/F23-route-by.md)，
照 Phase 2 規矩先討論再動手。要點：

* **機制八成在**（多 route、`fill_fields`、快取簽章含鍵），卡住的只有
  `run_batch` 把 route 鍵當一批一個常數 —— 改成逐顆算。
* `route_by` 是 recipe 頂層區塊（跑之前決定，不能是卡也不能是 decide 條件），
  **嚴格附加**（不在就一個位元不動，同 F22 的 decide）。
* 三個必須跟著出生的：`route_taken` 特徵（F19 規矩）、default 顆數看得見、
  三條 lint（欄不存在／route 不存在／有 route 沒人走）。
* **前置是 F17-⑤ 的取捨**：第一期提案用「不同節點 id ＋ routes-drift lint」，
  一份 recipe 一個圖等症狀出現再做。
* `lot_stats` ＋ 兩趟判定提案併第 3 期（動同一段批次程式）。
* 驗收先寫好：走對路 100%、B 路的顆**沒有** A 路的特徵（證明真的沒跑）、
  workers=1/4 逐位元組相同、無 route_by 的黃金值不動。

**留了四題等定調**：default 行為、route 模型選項、預覽自動切 route、
lot_stats 併不併。

---

## F24 ①：判定樹引擎（2026-08-24）

F24 的第一期做完：`decide` 從清單長成樹。**畫布是第 ② 期，這一輪只有引擎。**

* **資料結構**：`TreeStep(when, yes, no)`（二叉 —— 一步一問是流程圖語言；多叉
  要在一顆節點上排好幾個互斥條件，而互斥在畫面上驗不了）＋ `TreeLeaf(bin,
  label)`。`DecideSpec.tree` 是嚴格附加的第三層（score → decide.rules →
  decide.tree），每一層不在就完全不動下一層。
* **`rules_to_tree`**：平面規則清單＝鏈狀樹，轉換無損 —— 值網格逐點同 bin
  同 label 的測試釘住「F24 是 F22 的一般化，不是取代」。
* **引擎**：`_eval_decision` 走樹並記 `path`（一串 yes/no，進
  `ctx.meta["decide"]`）—— Preview 的 Path 與畫布的分支流量都吃它。
* **serde 只寫在用的那一種**（樹模式不寫 rules/otherwise）：兩個都寫出去，
  讀回來就是 `ambiguous-decision` —— 一份自己存的檔案不該把自己弄壞。
* **三條 lint**：rules+tree 並存（error）、樹太深 >16（warning）、
  步驟的問題解析不了（`bad-rule`）。寫壞的樹在**讀檔當場擋**。
* **undo 快照帶得動樹**（`viewmodel._decide_snapshot`）—— 漏掉的話一份樹
  recipe 在 Studio 按一次 undo，樹就安靜地消失。

**驗收（計畫書 §10，實跑）**：48 顆合成 lot，rules recipe vs 等價鏈狀樹
（走過 serde 一圈）—— **bin 相同 48/48、score 相同 48/48**；路徑分布
1/11/16/20 加總 = 48（流量守恆）。F22 的 21 條測試一條沒動、黃金值三份全綠。

新測試 `tests/test_decide_tree.py` 31 條；核心 1841 passed、UI 逐檔全綠。

---

## F24：判定樹上畫布 —— 分揀槽定稿（2026-08-24）

使用者問「ADC 跟 Algo 畫布上要怎麼呈現（畫布不能說謊），跳脫框架你有什麼建議」。
討論 → mockup → 兩輪修訂 → 拍板。定稿在
[`docs/history/plans/F24-decision-tree.md`](docs/history/plans/F24-decision-tree.md)，
mockup（四個 artboard）在
https://claude.ai/code/artifact/adfed023-6280-4acf-b6c0-749c9f299767 。

### 心智模型（病根與定稿）

所有「畫布說謊」的病根是同一個：**硬把數字塞進線的隱喻**。定稿一句話：

> 畫布管「圖與區域怎麼流」，表格管「數字」，判定樹管「怎麼分」。

### 定稿的四件事

* **判定整棵住在畫布上**（使用者：「ADC 也在畫布上呈現」「多步驟判定
  decision tree like」）：淡紫判定區、funnel 入口小卡（永遠恰好一個、不能刪、
  可收合）、**步驟＝菱形**（流程圖語言）、**葉子＝托盤**（顆數＋x/y real）、
  試跑後**每條分支標流過幾顆**（48 → 1/47 → 11/36 → …）。
* **`decide` 從清單長成樹**：`rules`（第一個成立的贏）就是一條鏈狀樹，
  遷移無損；`tree` 節點＝`when`＋`yes`＋`no`，兩邊各是步驟或葉子；
  每顆記 `path`，Preview 顯示走過的路。
* **Algo 段解散**：`feature_math`→working numbers（`let`）、`feature_fill`→
  樹的第一步＋「missing ⇒」屬性、`lot_stats`→「跟整批比」勾選。兩張卡先收
  `HIDDEN_STEPS`。**ADC 入口保留但特別化**（使用者補充定調：「左側 ADC card
  不要拿掉，但不要跟畫布 card 放在一起／讓它特別一點」）—— rail 底部分隔線下
  一顆紫框 funnel、庫底部淡紫常駐入口（`1 of 1` 徽章，點了跳到樹，不是生卡）。
* **幽靈線**：滑鼠停在數字名上→產出它的卡發亮＋臨時點線拉回去，移開消失。
  從 `feat_owner` 推導所以不說謊；樣式刻意不像資料線 ——「它是答案，不是連接」。

F22 §6 的開放問題（ADC 要不要有線）標為已定稿、F23 §6 的 UI 期改引用 F24。
分期五期寫在 F24 §9，驗收先寫好（含「rules 舊 recipe＝等價鏈狀樹，48 顆逐顆
bin 相同」與「分支流量守恆」）。

---

## cp950：CLI 在廠內 console 上炸在成功的那一刻（2026-08-24 修）

F20 §5 記下的那一條。廠內機器的 console 是 cp950，而 CLI 印 ✓ / ✗ / △ / →
（cp950 沒有這幾個字）—— 症狀特別壞：**跑完 48 顆、CSV 也寫好了**，使用者
看到的卻是一條 `UnicodeEncodeError` 的 traceback，在成功的那一刻。

修法一小段：`main()` 開頭對 stdout / stderr `reconfigure(errors="replace")`
—— 印不出的字換成 `?`，中文照常（cp950 本來就有中文），檔案輸出全部自帶
`encoding="utf-8"` 不受影響。

迴歸測試用 **subprocess ＋ `PYTHONIOENCODING=cp950`**（不是 monkeypatch
sys.stdout）—— 子行程的 stdout 真的是 strict cp950，跟廠內那台一模一樣。
驗過「把 bug 放回去會紅」。

---

## F22-UI：多類別在 Studio 上真的能編輯了（2026-08-23）

在這之前 `decide` 只能手寫 JSON。做完的是**方案 B 的前兩步**（純度報表 → 面板），
第三步（節點上列來源）撞到一件事，見下面 §4。

### 1. 純度報表：多類別唯一量得出來的東西

`report.summarize` 多一個 `bin_purity`，CLI 在**真的分出兩類以上時**才印：

```
  每一個 bin 裡有幾顆是真的：
    bin 9      1 顆　真缺陷   0　假點   1　純度 0%
    bin 3     11 顆　真缺陷  11　假點   0　純度 100%
    bin 2     16 顆　真缺陷  13　假點   3　純度 81%
    bin 1     20 顆　真缺陷   0　假點  20　純度 0%
```

**為什麼是純度不是「多類別正確率」**：正確率要先知道「這一顆應該落在哪個 bin」，
而手上的 ground truth 只標了 `is_real`（二元）。硬算就得先假造一份對照。
純度不需要那個假設 —— 它問「我判進這一類的，有幾顆真的是缺陷」，而那正是調規則
的人一條一條在看的東西。⚠ `bin 0` 的純度要反過來讀（那裡的真缺陷是**漏抓**），
所以每一列同時給 `n_real` 與 `n_nuisance`，不只給一個比例。

### 2. 判定面板（新模組 `ui/decide_panel.py`）

一個切換：**一個門檻（兩類）** 或 **一串規則（多類別）**。切成多類別時
**現有的門檻會被翻成第一條規則** —— 使用者調了半天的那個數字是他的工作成果。
兩者不能並存（照引擎的 `ambiguous-decision`）。

規則列有 ▲▼（**換順序就是換優先權**，所以它跟改門檻同一級）、bin、名字，
下面一行是**這一批的顆數與純度**（跟 F18 的灰階面板同一個立論：調規則的人是
一邊改一邊看的）。中間值與分數都配 F21-B 的「插入數字 ▾」。

**開新模組而不是塞進 `studio.py`**：那個檔案已經 5000 多行，而這一欄現在有兩種
樣子、規則是逐列生出來的。

### 3. 四個只有真的做／真的跑才會抓到的

* **打字會被重建搶走游標。** 面板不訂閱 model 的 listener，只有**結構性改動**
  （加／刪／換順序）才重建；外面餵進來的重建請求（試跑跑完）遇到有人在打字就
  記著、等焦點離開再補。
* **`_typing()` 的判準一開始寫錯**：`self.focusWidget() is not None` 幾乎永遠是
  True（Qt 顯示視窗時會自動把焦點給第一個可聚焦元件），於是**每一次重建都被
  擋掉** —— 症狀是「拖完門檻放開，那一格還是 0.0」。判準要是 `w.hasFocus()`。
* **換 recipe 會換掉整個 `self.model`**，而面板抓著參考 → 它會安靜地繼續編輯
  上一份 recipe 的判定段。`_apply_model` 要跟著 `set_model`。
* **UI 一律英文**（`test_ui_english_only`）—— 我第一版把面板的字寫成中文，
  32 條全部翻掉。docstring 與註解維持中文，那是刻意的。

**版面也是截圖抓的**：第一版一列八個東西，而這一欄的寬度是使用者拖的 ——
實測預設 437 px、內容要 592 px，於是**最有價值的那一格（顆數與純度）變成要捲
才看得到**。改成兩行（顆數是規則的註腳）之後 459 px，再加一個捲動區當保險。
另外 `small_button` 的邊長由 QSS 給，**沒套主題時會撐開**（獨立截圖實測三顆
▲▼✕ 各佔 90 px，把條件欄壓成裝得下 `> 0` 的小框）—— 元件不該靠外面有沒有套
QSS 才排得對。

### 4. 方案 B 的第三步卡住了（要先決定一件事）

「節點上列出它吃哪幾個數字」需要畫布上**有一個 ADC 節點** —— 而查了之後：
**畫布上根本沒有。** `set_score_summary` 有設一個字串，但它從來沒有被畫出來；
ADC 只是卡片庫裡一個「點了會開面板」的項目（`_SCORE_LIBRARY_ENTRY`）。

所以那一步比估的大：要造一個**不在 `recipe.nodes` 裡的終點節點**（位置怎麼定、
點它做什麼、怎麼跟 F17 記的「end point 的畫法」對上）。而 F17 當時記的正是
使用者的「再看看」。

**建議先看過面板再決定**：面板做完之後，「那個節點該顯示什麼」的答案不一樣了。

驗收：`tests/test_ui_f22_decide_panel.py` 16 條；核心 1806 passed、UI 逐檔全綠、
**黃金值三份全綠**；面板與整個視窗都實際開 Studio 截圖看過。

---

## 黃金值重凍 —— 那條「只能在家用機凍」的規矩是錯的（2026-08-23）

使用者問「黃金值你應該也可以凍吧」。**量了一次，答案是可以，而且那條規矩擋掉的
風險不存在。**

`ROADMAP.md` 寫著「那些是浮點數，在別台機器上重凍會把每一個特徵的基準線都換掉」。
實測（容器裡，**numpy 2.4.6 / opencv 5.0** —— 比 pin 的 1.24 / 4.8 新兩個 major）：

| | |
|---|---|
| `FLOAT_FORMAT` | `%.17g`（完整雙精度） |
| 共有特徵的數值差異 | **0** |
| bin / score / ok / error 差異 | **0** |
| 22 條差異的內容 | **全部**是「特徵名不同」 |

推論是硬的：**現在的黃金值是在家用機凍的**，而在這台機器上每一個共有特徵都
逐位元組相同 —— 那就是跨機器的證明，而且跨了兩個 major 版本。

重凍之後 `--check` 三份全綠、`D4T_GOLDEN=1` 的 4 條測試全過。diff 逐項對得上
F19（`area_px` / `cd_x_px` / `cd_y_px` → `cd_*` 那一批）與 F17-②
（`test_clip_frac` → `norm_clip_frac`）。

**這條規矩的代價**：它從 F19（08-21）擋到現在，也就是「重構的驗收＝跟改動前
逐項相同」那條防線兩天沒有在守 —— 而 F21 的 blob 修法與 F22 的判定段都是在那
兩天做的。（兩者都另外有自己的迴歸測試，而且這次重凍證實了它們沒有動到既有
的數字。）

**留下來的那一半**：重凍是「把現在的值當成新基準」，所以**看差異那一步不能跳過**。
`ROADMAP.md` 那一段改成講這件事，而不是講機器。

---

## F22：多類別 ADC 的引擎（2026-08-23）

整個 app 最大的功能缺口 —— 一個叫 Auto Defect **Classification** 的工具，
`score.bins` 卻被強制只有 `below`/`above`。設計與量測全部在
[`docs/history/plans/F22-adc-multiclass.md`](docs/history/plans/F22-adc-multiclass.md)。

### 形狀：一張由上往下讀的篩子

`decide` = `let`（中間值）＋ `rules`（第一個成立的贏）＋ `otherwise` ＋ `score`。

實跑 48 顆（F21 那份 recipe，把 `Feature math` 拔掉、算式搬進判定段）：

| bin | 類別 | 總數 | 真缺陷 | 假的 |
|---:|---|---:|---:|---:|
| 9 | not measurable | 1 | 0 | 1 |
| 3 | big particle | 11 | **11** | 0 |
| 2 | particle | 16 | 13 | 3 |
| 1 | faint | 20 | 0 | 20 |

**這個 app 第一次分出兩類以上。**

### 四個決定

* **由上往下第一個成立的贏**，不是「每條算分取最高」。理由是使用者讀得懂
  「改順序＝改優先權」；算分取最高要他想像好幾條分數線的相對高度，而那件事
  畫不出來。
* **`let` 的中間值是真的特徵**（寫進 `ctx.features` → 進 CSV → 畫得出分布）。
  這正是 `feature_math` 存在的唯一真理由，而在這裡它不必是一張卡 ——
  F21 §5.3 留的那個題目，**引擎這一半成立了**。
* **不用學第二套語法**：比較運算子本來就回 1.0／0.0，所以
  `(a > 5) * (b < 2)` 就是 AND。判準是「非 0 就是成立」。
* **`score` 還是 `score`**：寫進 `features["score"]`，所以 KLARF 的 DSIZE、
  Top-N、CSV 的 score 欄都不必知道這一段換過。

### 嚴格附加，而且理由不是保守

`decide` 不在 → `_eval_score` 第一行就分岔，老路一個位元都沒動；`to_json_dict`
也不會長出那個鍵。**因為黃金值從 F19 起就是壞的** —— 沒有那條防線的時候，
「改了判定段但既有的數字沒變」這句話沒有人證得了。目前唯一守著它的是
`test_an_old_recipe_round_trips_without_growing_a_decide_key`。

**兩種寫法不能並存**（`ambiguous-decision` 是 error，不是挑一個贏）：同一件事
兩個地方存是這個 repo 最怕的形狀。

### 還沒做的四件（見計畫書 §4）

UI 的判定面板、`label` 進 CSV（會動序列化，黃金值壞著不動）、多類別的
ground-truth 比對（要先定義「對」是什麼）、舊 recipe 的自動遷移。

⚠ **還不能刪 `feature_math`**：`let` 在引擎上取代得了它，但 UI 還沒有 `let` 的
編輯器（現在只能手寫 JSON），而 F21-B 的挑選器也還沒做到那幾行上。

### 開放問題：ADC 要不要有線

使用者：「**我覺得 ADC 也可以有線啦（但我們再來討論）**」。F21 §5.3 我主張
「ADC 吃全部所以不需要埠」—— **多類別之後那個論證有漏洞**：每條規則吃的是
特定幾個數字，不是全部。這一題要在 UI 那一輪一起決定，不是先做完面板再補。

驗收：`tests/test_decide_multiclass.py` 21 條；核心 1805 passed / 63 skipped、
UI 逐檔全綠。

---

## F21-B：算式那一格說得出「有哪些數字、誰算的」（2026-08-23）

F21 實測掉出來**最痛的那一項**：第一次真的用 `feature_math` 的時候，我得跑
Python 呼叫 `resolve_features()` 才知道 `cmp_delta_median` 存在。而目標使用者
不會寫 code（推廣鐵則）。痛的順序跟先前猜的相反 —— 「看不出數字從哪來」反而
是最不痛的那一項（只有一張 glv 卡時一次都沒混淆過）。

### 兩個新型別，儲存格式一個位元都沒變

`expr`（一個算式）與 `feature_keys`（一串數字名）。**存的就是 `str`** ——
recipe JSON 完全不變，差別只在 UI 認得它是什麼。這是 `image_keys` 的先例
（「值的格式一樣（逗號分隔字串），但 UI 認得它是接線的結果」）。

兩格共用同一支「插入數字 ▾」，差別只在**送進去的方式**：算式插在**游標位置**
（式子中間常常要補一個名字），一串名字**接在後面**並補逗號（插在中間會把別人
的名字剖成兩半）。那個差別由型別決定，不由使用者記得。

清單的每一項說得出**誰算的**（`cd_median   —   CD`），因為一份 recipe 可以有
兩張 `Gray level`（量兩個區域）—— 名字自帶前綴的只有撞名被蓋掉的那一份
（F17-②），沒撞名時仍然只有一個短名，光看名字選不出要哪一個。
分數那一格（`score.expr`）本來就有下拉，這一輪讓它也講得出來源。

### 兩個只有「真的跑起來」才會抓到的

* **`expr` 進了 `PARAM_TYPES` 卻沒進 coerce** —— `validate_params` 會丟
  「unknown type」，也就是**每一份用到那張卡的 recipe 都會炸**。測試當場抓到。
* **`Feature math` 的清單裡有 `defect_score`** —— 它自己要寫出去的名字，點下去
  就是 `defect_score = defect_score`。這是把 Studio 跑起來、把選單印出來才看到
  的（元件測試看不到，因為清單是 Studio 填的）。引擎擋得住
  （`unknown-feature-input`），但**讓使用者點一個保證壞掉的選項本身就是 bug**。
  修法：`labelled_features(..., include_upto=False)`。

### 順手補的一致性

`feature_fill`（A1 那張卡）的「守哪幾個數字」有**一模一樣**的痛點，卻沒有挑選器
—— 昨天做的卡如果不補，等於我一邊修這個痛點一邊留一個。所以它換成
`feature_keys`，共用同一支。

驗收：`tests/test_ui_f21_expr_picker.py` 12 條；核心 1783 passed、UI 逐檔全綠；
兩張卡的面板都實際開 Studio 截圖看過。

---

## F21：照著用一次 Algo 段，掉出「框越準越量不到」（2026-08-23）

使用者問「algo 這張 card 有沒有存在的必要」。查 repo 得到的事實是**三個收斂過的
段落零使用**：`feature_math` 0 次、任何 ROI 卡 0 次、F18 的 compare 0 次。
所以先串起來跑一次，再談要不要為 Algo 段加東西。全部在
[`docs/history/plans/F21-algo-and-roi.md`](docs/history/plans/F21-algo-and-roi.md)。

### 1. ROI 是槓桿，實測 +0.35

同一批資料（48 顆，24 真 24 假）：正確率 **50.0% → 93.8%**、誤殺率
**95.8% → 12.5%**、`glv_max` 的 AUC **0.632 → 0.944**。

### 2. 修掉：**ROI 框得越準，blob 越量不到**（症狀是反過來的）

`algo/shape._region_noise` 的空間項拿「外框那一圈」當背景樣本。4×8 的框，外框有
20 個像素、內部只有 12 —— 而一團 3 px 的東西在 4 px 寬的框裡**必然碰到外框**，
於是它自己被算成背景起伏（逐點 σ 8.3 vs 外框 MAD 26.5，取大的 → 品質 0.35 →
判 `flat`）。

| | 量不到 | `cd_deq` 的 AUC |
|---|---|---|
| 緊框（預設 `min_edge=0.5`） | **92%** | 0.514 |
| 整張圖 | 2% | 0.564 |
| 緊框，修好之後 | **12%** | **0.901** |

修法 `ring_is_a_border(shape)`：外框像素超過整塊一半時它就不是一圈邊，那時只用
逐點估計。判準是**幾何**不是調出來的數字。低頻那條防線一個位元都沒動（它守大
區域，驗收用 64×64、外框佔 6%），並加了一條測試釘住這件事。

### 3. A1 第一次真用就救了場

第一次跑 **44/48 顆失敗** —— `cd_deq` 這一格量不到，`feature_math` raise，
整顆 `ok=False`。插進 `feature_fill` 之後 48/48 跑完。那張卡昨天做對了。

### 4. Algo 段的決定（§5）

* **保留 `feature_math`，現在不做特徵線。** 它值 +0.012（576 對多排對 7 對）；
  而畫布缺口比想像小 —— 11 個節點只有 2 個沒線，且它們的上游已經被**區域線**
  綁在一起。加上**特徵不跟線跑**（`_local_view` 只有 `images` 是每張卡自己的），
  現在畫的線會是「說明」不是資料流。重啟條件寫在計畫書。
* **錢花在真正的痛點**：實際用過之後，最痛的是**不知道有哪些數字可以用**
  （我得跑 Python 才知道 `cmp_delta_median` 存在），最不痛的反而是「看不出從
  哪來」。所以做「可以點的數字清單」，而且**做在 `expression` 編輯器上**——
  `score.expr` 痛點一模一樣。
* **判準寫死**：式子寫得出來 → 不開卡；要看整批 → 才開卡。Algo 段最終三張。
* **留給 ADC 的題目**：把「算式子」搬進 ADC（好幾行的計算表），讓 `feature_math`
  被吸收。理由：F17 對 Output 卡說的「吃的是全部，所以不需要埠」對 ADC 一字不差
  —— **ADC 沒有線不是說謊，`feature_math` 站在中間卻沒有線才是。**

### 5. 順手發現：黃金值從 F19 起就是壞的

`freeze_golden.py --check` 現在會紅，而且**跟這一輪無關**（把 `shape.py` 暫存
起來再跑一樣紅）。差異是 F19 改名留下的（少了 `cd_x_px`、多了 `cd_axis_deg` …）。
也就是說「重構的驗收＝跟改動前逐項相同」這條防線**從 2026-08-21 起就沒在守**，
而它擋在任何後續重構前面。⚠ 只能在家用機重凍。

### 6. 一個不採信的數字

`cross_dist_px` AUC 0.922、加進任何組合都變 1.000 —— **不採信**：這批資料的假點
是 `type:"none"`（完全沒有缺陷），所以「最強訊號離中心很遠」幾乎就是 ground
truth 本身。所有結論都排除了它。

---

## Algo A1：量不到不是跑錯了（2026-08-22）

Algo 段從一張卡（`feature_math`）開始往下做。**第一件事不是加能力，是補一個
現成的洞** —— 而那個洞是兩條各自都對的規矩留下來的：

* 「算不出來的那一格不寫」（F18／F19：不是 0、也不是 NaN）
* 「變數不存在會 raise」（`expression.py`：那通常是打錯字，安靜給 0 會把
  使用者送去查一個沒有問題的地方）

實跑證實過：`parse_expression("cd_median * 2").eval({"glv_mean": 100.0})` 丟
`ExpressionError`，`engine._eval_score` 攔下來之後回 `ok=False`。於是
**「這一顆量不到」跟「這一顆跑到一半炸掉」在結果表上是同一件事** —— 而在 fab
裡「量不到」常常就是一種缺陷型態的訊號（結構被填掉、對比消失），它該分得進
某一類，不是被丟出批次。

### 新卡 `feature_fill`（Missing numbers）

兩格：守哪幾個數字（逗號分隔）、補什麼值。寫出去的是兩個東西，**第二個才是
重點**：`<name>` 補上值讓下游跑得完，`<name>_missing` **永遠寫**（0／1）——
沒有它，CSV 上那 12 個 `cd_median = 0` 跟真的量到 0 的那幾顆分不出來，
那正是這張卡要修的病換一個地方發作（F19 的規矩：卡片自動做的每一個決定，
都要變成一個使用者畫得出分布的數字）。

旗標本身可以進分數表達式（`cd_median * 2 + cd_median_missing * 1000`），
所以**「量不到自成一類」不必等多類別 ADC**。

### 三個設計問題的答案（都是從既有機制推出來的，不是選的）

* **要不要讓表達式一律容忍缺變數** —— 不要。那條 raise 要擋的是打錯字，而打錯字
  `validate` 已經先擋掉了（`unknown-feature-input` error ＋ `unknown-feature`
  warning）。所以**跑到執行期還缺的那一個，一定是「宣告了但這一顆沒寫」**。
  兩件事引擎已經分開，讓表達式一律容忍會把前者也吞掉。
* **「量不到」要不要跟「沒接線」分兩種狀態** —— 不要，而且是同一個理由：
  沒接線在跑之前就是一條 error，執行期不可能遇到它。
* **要不要「只掛旗標、不補值」的模式** —— 不要。那個模式解不掉 raise，也就解不掉
  這張卡存在的理由，而它會讓使用者以為自己選了一個安全的預設。
  ⚠ 但它指出一件**下一批要記得的事**：`lot_stats` 對一整欄取中位數時要排除
  補進去的值（12% 的假 0 會把中位數拉走）。判斷「哪幾列算數」是**算中位數的
  那張卡**的事。

### 一個刻意的宣告不對稱（違反 I3 的字面，理由寫在三個地方）

`run()` 寫 `<name>`，但 `resolve_features` 只宣告 `<name>_missing`。

I3（`test_card_invariants` 的「只碰宣告過的東西」）講明它要擋的害處是
「它會出現在自動完成裡，但沒有任何地方說得出它從哪來」—— 而那在這裡**不會
發生，且是引擎保證的**：`resolve_features_in` 讓 `unknown-feature-input` 擋住
「沒有任何卡宣告這個名字」的 recipe，所以跑得起來的每一份，`<name>` 都已經有
一個上游的擁有者。這張卡填的是那個名字上的一個洞，不是憑空生一個新名字。

反過來宣告它的代價是實的：`<name>` 的擁有者（量測卡）不是診斷數字，所以
`feature-collision` 的「兩邊都是診斷才跳過」不成立 —— **每一份正確使用這張卡的
recipe 都會多一條警告**，而使用者學會忽略一條警告之後真的那一條也一起被忽略
（推廣鐵則、F11 Enhance-3 的原話）。

卡片跟 `feature_math` 一樣進 `NEEDS_MORE_SETUP`（預設沒設定完是刻意的，F7-13），
所以 I3 跳過它 —— **跳過的東西有人接**：
`test_feature_fill.py::test_it_writes_nothing_else_beyond_that` 是 I3 的專屬版，
用**設定好的**參數跑，比那個 harness 問得更嚴。

驗收：`tests/test_feature_fill.py` 18 條；核心 1779 passed / 66 skipped，
UI 測試逐檔全綠。黃金值零變動（這張卡不在任何一份黃金 recipe 上）。

---

## F19 之後照著量一次：一個安靜的平滑 bug、一組新資料、一格新參數（2026-08-22）

使用者拿 MG × EPI 的合成資料問「凸出量怎麼量」。整輪都是**照著真的量一次**
掉出來的東西，沒有一件是靠讀程式碼找到的。

### 1. 量法本身：兩種缺陷要接不同的流

* `mgepi_real3`（spacer 裡冒出一顆 **異材** Hf）→ 量 `diff`。CD 卡 help 上那句
  「不要接 diff」**在這個場合是錯的**：差影像上剩下的正是缺陷本身，而它有方向，
  所以它是一個合法的「一條線」量測。實測 AUC 0.985 / 正確率 93.8%。
* `mgext`（**MG 自己**從側壁竄出，同材質）→ 量 `test`。凸出物是 MG 平台的延伸，
  末端有一條乾淨的邊；diff 上訊號反而是漸層的。
* 判準因此不是「哪一條流比較好」，是**缺陷跟結構是不是同一種材質**。help 該改。
* 量**暗的 inner spacer 剩多寬**是死路：掃過 384 組參數，成功率最高 1%。
  除了「缺陷會把暗縫整條填掉」之外還有一個硬的：暗縫兩側對比極不對稱
  （62 vs 29 GLV）而剖面雜訊 11.5，弱的那一側 `edge_quality` = 0.39 < 預設 0.5，
  **永遠**被丟掉。

### 2. `gaussian_filter1d` 在剖面兩端補零 → 真的邊被安靜地丟掉

`np.convolve(..., mode='same')` 補零，於是頭尾兩格被拉向 0，在梯度上是一道假的、
而且通常是全剖面最強的轉折。`find_edges` 的偵測門檻是**相對的**
（`0.35 × 該剖面最大梯度`），所以那道假梯度把門檻整個墊高 —— 剖面兩端的材質
對比越強，被丟掉的真邊越多。症狀是那幾列回 `open_edge`，而
**`open_edge` 看起來完全像「結構被框切掉了」**。

實測（`mgext`，凸出量對設計值的回歸）：**斜率 0.079 / R² 0.030 → 0.917 / 0.792**。

改成 `mode='edge'`。同一份檔案裡 `smooth_strip_2d` 一直都是 edge padding，
MMH 那幾支則是用一個 `k//2+1` 的 margin 把被汙染的樣本排除掉（`refine_yedge_gradient_peak`
的 Step 7，註解就明寫著這個 artifact）—— **這個 repo 早就知道，只有這一支漏掉，
而 `algo.edge` 沒有那個 margin。**
代價：兩份黃金 recipe 24 顆逐欄比對**零變動**。新增兩條回歸測試，還原修法都會紅。

### 3. 新產生器 `tools/make_mgext.py`：凸出量是**設計值**

`mgepi_real3` 只答得出「分不分得開」，答不出「量得準不準」—— 那顆 Hf 沒有一個
叫做凸出量的真值可以對。新的一組每一顆帶 `extrusion_px`（1.0–8.0 px 等距鋪開），
所以量測結果可以直接回歸。實測分段誤差中位數：

| L | 0（乾淨） | 1–3 | 3–5 | 5–6.5 | 6.5–8 |
|---|---|---|---|---|---|
| 誤差 | **+0.11 px** | −1.15 | −1.75 | −0.49 | **−0.11 px** |

**可用下限約 5 px（7.5 nm）。** 3 px 以下的低估不是參數問題：MG 自己的側壁就糊在
2–3 px 上，比凸出物還寬，50% 門檻的等高線幾乎不動。

缺陷位置**不隨機灑**（跟 `mgepi_real3` 相反）：這一組要問的是量測，
把「框有沒有放對」這個變因拿掉，兩件事才分得開。

**資料不進版控**（`0822test/` 已加進 `.gitignore`）—— 2 MB 的 TIFF，而且
`python tools/make_mgext.py <目錄>` 隨時重產得出來、**逐位元組相同**
（`tests/test_make_mgext.py` 鎖住那句話）。進版控的是「怎麼產」。
`tools/make_mgepi_real.py` 本來就在，所以兩批資料現在是同一個規矩。

### 4. F20：一格「哪一塊是缺陷那一塊」

見 [`docs/history/plans/F20-pick-defect-box.md`](docs/history/plans/F20-pick-defect-box.md)。
`<name>_center` 原本寫死是「離 patch 正中心最近」，那句話假設缺陷在正中心。
在 `mgepi_real3` 上實測 **11/24**；換成「diff 訊號最強的那一塊」是 **24/24**，
端到端正確率 **72.9% → 97.9%**。預設值不動，黃金值零變動。

### 4.5 把 Studio 跑起來截圖，掉出四件「畫面在說謊」

引擎改完之後**實際開 Studio 截圖**（offscreen ＋ 載入字型），四件都不是讀程式碼
找到的：CD 面板兩列都標 `mg_center`（接了兩條流）、疊圖上醒目的框不是卡片真的
量的那一塊（F20 自己造成的回歸）、**ref 的量測線畫在 test 的影像上**、
以及 GLV 面板寫 `typical box #7 of 20` 而影像上找不到第 7 格。

第四件的第一版是「再描一圈外框」，**截圖出來才發現等於沒畫** ——
`_paint_marks` 的規矩是「線畫到幾乎看不見、點畫滿」，那圈外框跟區域框完全重疊。
改成四個角點。詳見 F20 計畫書 §4.5。

### 5. 順手掉出來、還沒解決的

* **`roi_cross` 放不出「中心落在交界上」的框。** `beside_vertical` 從邊界往外長、
  `crossing` 正好等於條紋本身，而 CD 的錨點就是框心。兩次都是靠**謊報
  `vertical_width`** 才把框推到該去的地方（25 撐開、4.33 推進去）。
  `gap` 只能往外、`inset` 只能往內，沒有一格能把框往條紋裡面推。見 F20 §5。
* **`python -m d4t run` 在 cp950 console 上會 crash**（印 `✓` 的
  `UnicodeEncodeError`）。廠內機器的 console 就是 cp950。

---

## 收尾：兩個「照著真的用一次」才掉出來的 bug（2026-08-21）

使用者拿一張 MG × EPI 的合成 SEM 圖來問「從 MG 凸出到 EPI 上的亮點怎麼量」。
照著設一份 recipe、實跑 24 顆 —— 兩個 bug 是在那個過程裡自己掉出來的，
不是靠讀程式碼找到的。

* **`d4t run` 炸在最後一行。** 一批**全是真缺陷**時誤殺率的分母是 0，
  `report._ground_truth` 回 `None`，而 CLI 寫 `g.get('false_alarm_rate', 0):.1%`
  —— **`.get` 的預設值擋得住「鍵不在」，擋不住「鍵在、值是 None」**。
  跑完、算完、CSV 也寫了，使用者看到的卻是一個 traceback。改成模組層的
  `_pct()`，None 印 `—`：**沒有分母不等於一個都沒誤殺**，印 `0.0%` 是說謊。
* **沒接區域的那一顆，面板與影像又是兩個顏色。** 影像上的標記畫 accent
  （沒有 labels 就整組 accent），面板卻畫 `region_hex(0)` 的綠。病根是
  `region_index` 預設 0，而 **0 是一個合法的區域索引** —— 分不出「第一個區域」
  與「根本沒有區域」。判準改成看 `note["region"]` 是不是空字串。

順帶量出來的東西寫進了 `docs/USING-CD.md` 與 `PITFALLS`：diff 上要用**團**那一支
（線那一支在每一列都問「離中間最近的那一對邊」，而 diff 上沒有結構可以鋪線 ——
實測真假兩群完全重疊）、`Normalize(ref)` 的 borrow range 要接**原圖**的 test
（接了已經拉過的那一張，整個圖案會留在 diff 上，正確率 75% → 100%）、
以及 diff 上**不要**再框小區域（框會切到凸出物，12/12 掉到 4/12）。

---

## CD 的標記跟著區域的顏色走（2026-08-21）

使用者：「顏色都一樣？」。查下去發現問題跟直覺相反 —— **不是顏色不夠多，是 CD
沒有跟既有的那條規矩**：一個具名區域擁有一個顏色，影像上的框、模板編輯器、GLV
面板全部共用（`theme.region_hex` / `REGION_COLORS`）。`CdInspector` 卻把每一條
資料線都畫成 `TOKENS["accent"]` 那個藍 —— 於是同一個區域在 GLV 是綠的、在影像
的框上是綠的，一到 CD 就變藍。接兩個區域的時候更糟：兩份剖面、兩條輪廓、整批
分布上的兩根針，全都是同一個藍，畫面上沒有任何線索說哪一份是哪一個。

* **卡片把「這一輪是第幾個區域」記進 note**，面板與影像標記都從那裡取色。
* **`MultiSourceStep` 多注入一個 `CURRENT_REGION_INDEX`** —— 基底迴圈會把
  `roi` 換成當輪的那一個區域，所以卡片自己**看不到**它在整串裡的位置。第一版
  就踩了這個：每一個區域算出來的 index 都是 0，兩份剖面照樣同色。
* **`overlay_marks` 多回一個 `labels`**（每條線屬於哪個區域），而
  `ImageView.set_marks` 上色時**重用畫框那一份 `_overlay_order`** —— 不是自己
  數一遍。標記與框因此不可能各說各話。

`Step.overlay_marks` 的合約從三元組變成四元組，預設 `[], [], -1, []`。

**而顏色做完才看得出下一件事**（使用者：「試看一下」）：面板一次只畫
`notes()[0]`，所以兩個區域接進來的時候，影像上兩塊都有標記、面板卻只講其中一塊，
另一塊去了哪畫面上沒有任何線索。最糟的形狀是被留下的那一塊剛好量不到 ——
截圖裡就是它：**輪廓畫在 B 區，面板在講 A 區的「什麼都沒有」**。

* **接了幾個區域就畫幾列**（上限 3，跟 `GlvInspector.MAX_ROWS` 同一個理由）。
  每一列自己的第一格小標題換成**區域名、畫成那個區域的顏色**；第二、三格的
  小標題只畫在最上面那一列 —— 它們是欄位名，一列一份只是噪音。
* **列的順序照接線的順序**（`region_index`），不是照名字。照名字排的話
  `top,bot` 會畫成「橘的在上、綠的在下」，跟影像上的框正好相反 —— 而使用者
  正是拿顏色在兩邊之間認位置的。
* **摘要那一行每一個區域都講**（`top: … | bot: no width here — …`）。
  以前是「第一個 ＋ `+1 more`」，而「+1 more」說不出那一個是量到了還是量不到。
* 小標題那一行改成**照字型高度**留：寫死 13 px 會把底線切掉，
  `band_a_center` 在畫面上變成「band a center」，而那不是 CSV 上那個欄名。

一個區域的時候一個畫素都沒變（小標題、整列高度、摘要格式全部照舊）。

---

## F19 收尾：把 CD 的面板與參數表照著截圖修一輪（2026-08-21）

使用者：「UI 跟 UX 可以再漂亮精進一點嗎」。做法是**先把 Studio 真的帶起來截圖**，
再照著畫面上讀不順的地方修 —— 六件裡有五件是 headless 斷言看不到的。

* **同一個字不要出現兩次。** CD 的膠囊那一格 `label` 與 `section` 都是
  "Report"，而一整塊的編輯器那一列的名字是**垂直置中**的 —— 於是那個字落在
  群組區塊的中間那一列旁邊，畫面上讀起來像是一個叫「Report」的群（Size 的第二
  排看起來屬於它）。兩條規矩都做成通用的：**重複自己小標題的名字收起來**、
  **一整塊的編輯器名字對齊到最上面**（`_BLOCK_EDITORS`）。
* **剖面圖只畫量到的那一段前後。** 一張 128 px 的 patch 上有八個一模一樣的
  週期，整條畫出來的話那兩個交點淹在裡面 —— 而這一格的唯一工作就是「邊被判
  在哪」。兩側各留 1.1 倍寬度，因為「邊的外面長什麼樣」正是判斷配對對不對的
  依據。
* **量到多寬那一行從曲線正中間搬到底下**，變成一條有擋頭的量測線。
* **「Each line」多一條 ±σ 的淡帶**：橫軸是自動縮放的，沒有它，一條很齊的線
  跟一條很糙的線長得一模一樣。
* **兩行被截掉的字**：`22.85 - 25.76 px · band = 1 sigma` 在兩百像素寬的格子裡
  畫出來是「85 … sig」—— 兩端截掉的正好是最該讀的數字。說明搬到標題。
* **三格之間補上分隔線**，而且**每一格都要說自己的軸跨多少**（整批那一格
  以前沒有 —— 「這一顆在整批的哪裡」沒有尺就只是一條線的位置）。

前一輪截圖也修過兩件（面板無條件印 `area 0 px`、那一行緊貼隔壁格的標題）。
六件全部有測試釘住，`tests/test_ui_f19_cd.py` 現在 28 支。

---

## F19 第二批：CD 的無方向那一支（2026-08-21）

顆粒與孔洞沒有方向，硬挑一個方向去量，答案就取決於那個挑選。計畫書：
[`docs/history/plans/F19-cd.md`](docs/history/plans/F19-cd.md) §11。

* **卡片最上面多一個岔路**（`shape` = 一條線／一團東西）。它問的是**樣品**，
  而且它真的決定了後面哪幾格算數 —— 方向對一團東西沒有意義，那一列就收起來。
  `threshold_pct` **兩支共用同一格、同一支函式**，那正是第一批「邊界判準是一個
  軸，不是一個 method」兌現的地方；反過來 `gradient` / `fit` 是一維剖面的構造，
  二維沒有對應物，所以那一格只有線那一支有 —— **不假裝三個判準兩支都有**。
* **新的 `algo/shape.py`**：真實覆蓋面積、等效圓直徑、旋轉卡尺的最大／最小
  Feret，全部旋轉不變。實測一個 L 形的 bbox 是它真實面積的 **1.9 倍**，而那個
  數字看起來完全正常 —— 那就是這一支存在的理由。門檻**不用 Otsu**（沒有前景時
  它照樣切一半），Feret **不用 `minAreaRect` 的長邊**（正方形上差 30%）。
* **面積刻意不做次像素**：輪廓是硬門檻切出來的，畫在影像上的就是它；面積若來自
  柔性積分，圖上那一圈與 CSV 上那個數字就不是同一件事。量化誤差實測 ≤2.5%。
* **三個坑**（全部進 `PITFALLS.md`）：百分位藏著「前景要佔 1% 以上」的假設
  （8 px 的缺陷放在 96×96 裡整團判成沒有前景）；兩道門檻只抄了一道（把
  `min_edge` 調到 0 就把整塊區域切成一團）；**一階差分的雜訊估計對低頻起伏是
  瞎的**。
* **第三個只有實跑一批資料才炸得出來** —— 跟第一批的 `cd_bright` 同一個教訓。
  合成 lot 的 `diff` 上，修之前**假點 12/12 都量得出面積**（品質分 0.72 看起來
  很健康），加上空間那一項之後**假點 0/12、真缺陷 11/12**，而 `cd_edge_score`
  真 0.69–0.88、假 0.34–0.48。
* **UI 一個新原語都沒加**：輪廓就是一串線段、最長的弦是第 N+1 條，第一批那個
  「Measure 段共用」的 `set_marks` 原封不動就夠了 —— 那是當初不把它做成 CD 專用
  的回報。面板第一格按 `shape` 換成**灰階直方圖 ＋ 判準那條線**（剖面圖的同義
  詞，一樣回答「為什麼是這個數字」）。
* `_util.AREA_FEATURES` 那條「面積換算乘平方」的規則**重新有了生產者**
  （`cd_area_px`）—— 第一批之後它空窗了一輪，靠一支測試釘著沒被當死碼清掉。

兩個明講的極限：認得出來的最小一團約 3×3 px；起伏尺度接近整塊區域時，外框就
不是內部的代表樣本（實測 σ≤3 px 穩定擋得住、σ≥4 px 在門檻上擺盪）。

⚠ **黃金值仍然沒有動** —— 家用機跑 `tools/freeze_golden.py`。

---

## F19：CD 整張重做（2026-08-21）

使用者：「基本上要全部砍掉」＋「就得完全刪掉 以新的為主」。計畫書：
[`docs/history/plans/F19-cd.md`](docs/history/plans/F19-cd.md)。

* **原子單位換掉**：一個區域的 bbox → 一堆量測線。bbox 是極值統計量（一顆離群
  像素 100% 傳進答案，而且圖再大也不會變準），換成 N 條線之後 **σ 就是 LWR**、
  min 是頸縮、max 是橋接 —— 粗糙度是同一趟的副產品，不是另外加的功能。
  數學全部在新的 `d4t/core/algo/edge.py`。
* **四個正交的問題取代四個 method**（在哪量 × 沿哪個方向 × 邊界怎麼定義 ×
  怎麼收）。判準是一句話：這個參數問的是使用者的樣品，還是問軟體。
* **判準的預設被實測推翻。** 設計時主張 `fit`（「擬合吃整段爬升 → √N」），
  第 1 步的實測表量出來是 `threshold` 的 σ 最小、`gradient` 的偏差最小。
  原因兩個：預設的 1 px 平滑已經替穿越法做完了雜訊平均；單邊 erf 模型在有限
  寬度的線上被隔壁那條邊污染。**兩份說法都留在檔頭。**
* **四個坑**（全部進 `PITFALLS.md`）：平台取樣跨過隔壁那條邊（6.0 量成 7.9）；
  門檻高度從左邊平台算起 → 一個看起來有在動、實際上沒作用的旋鈕
  （25% 對 75% 量出 `12.2348106481077` vs `12.234810648107693`）；雜訊估計用
  平台 MAD → 乾淨影像也只有 0.88 分；**候選邊的門檻沒有相對於雜訊 → 128 條線
  128 條「成功」，量到的是雜訊**。
* **`cd_bright` 是實跑合成 lot 才發現要有的**：`target="auto"` 逐顆挑了不同的
  極性，於是 `cd_median` 那一欄同時裝著兩群數字。規矩因此明講：**卡片自動做的
  每一個決定，都要變成一個使用者畫得出分布的數字。**
* **UI**：`ImageView.set_marks` ＋ `Step.overlay_marks`（**整個 Measure 段共用**，
  F18 §9.0 指名的那一件）＋ `CdInspector`（剖面圖／每條線的寬度／整批分布）。
  剖面圖是主角 —— CD 是「數字錯了看不出來、圖上一眼看得出來」的那種量測。
* **舊的 `cd_x_px` / `cd_y_px` / `area_px` 刪掉**，`size_feature` 的預設改成
  `cd_median`。舊 recipe 的分數表達式會拿到 `unknown-feature` warning ——
  那正是要看到的（舊值是 bbox，跟新值不是同一種量測）。

⚠ **黃金值沒有動，要在家用機跑 `tools/freeze_golden.py` 重凍** —— 那些是浮點
數，在別台機器上重凍等於把每一個特徵的基準線都換成那台機器的值。

---

## F18 第五件：cmp_ 命名、Compare their 可複選、面板疊上參照（2026-08-21）

使用者三句話（追問過一輪才動手，見計畫書 §8.8）：「絕對量的跟相對量的還是要
分類好」「Compare their 只能單參數嗎」「Feature 左側的 histogram 我還是沒有很
滿意（相對／絕對？）」。

* **命名**：相對量一律 `cmp_<metric>[_<stat>]`（`epi_cmp_delta_median`），
  絕對量維持 `glv_*`。規則一句話講得完，而舊 recipe 的分數表達式由
  `recipe._compare_feature_renames` 自動改寫 —— 對照表住在卡片上
  （`legacy_feature_renames`），因為改名的規則是那張卡的事。判準是「舊名字在
  不在表達式裡」，第二次跑是 no-op（鐵則 9）。
* **Compare their** 從下拉變成膠囊（可複選、有「+ Percentile…」）。
  **鍵沒有改名**，所以不必遷移：舊值 `"glv_mean"` 本來就是一個合法的一元素
  清單。參照那些格子的 stat 一個統計量一份，而且整張卡只算一次。
* **特徵表多一欄「What it is」**（使用者：「目前只有縱向空間被用到，橫向空間
  幾乎沒有」）。內容從名字翻出來，絕對量走 `metric_formula`、相對量走
  `METRIC_GROUPS` 的短標籤 —— 都不是在 UI 裡新發明的。兩種量用顏色分，
  同一張卡底下絕對量在前。「跟誰比」由 `meta["compares"]["names"]` 帶進來。
* **面板疊上參照那條分布**：虛線外框 + 很淡的底，兩條各自正規化（橫軸是共用
  的尺、縱軸不是），中間那一段就是 `delta` 在圖上的長度。圖上那一行相對量
  （`Δ +26 · SNR 66 · overlap 0.06`）寫在座標軸那一列的中間 —— 第一版寫在
  右上角，跟 Δ 撞在一起。

計畫書：[`docs/history/plans/F18-glv.md`](docs/history/plans/F18-glv.md) §8.8。

---

## F18 第四件：收起四顆、Report 從五個變九個（2026-08-21）

使用者先要一份「每個 Statistic 跟 Report 的定義」，說「因為我可能會認為，
有些不需要」。列完之後兩句話：**收起 Trimmed mean / Kurtosis / Entropy /
Percent**、**「Report 要有更多統計量可以量」**。

* **收起來 ≠ 刪掉**（`CLAUDE.md` §5）。Statistics 那三顆直接離開
  `METRIC_CHOICES` 就成立 —— 那一份本來就不是「全部合法的 id」。
  `percent` 不行：`COMPARE_METRICS` 同時是清單**與驗證表**，從它拿掉等於
  舊 recipe 會炸。所以多了一份 `COMPARE_CHOICES`（列什麼），驗證仍看
  `COMPARE_METRICS`（算得出什麼）—— 跟 Statistics 那邊一字不差。
* **多的五個分成三群**：Difference（`abs_delta`、`contrast`）、
  Vs boxes（`pct_rank`）、Distributions（`overlap`、`spread_ratio`）。
  分群不是排版偏好：九顆排成一列的時候，「哪幾個需要參照有好幾格」在畫面上
  看不出來，而那正是「為什麼我的 snr 是空的」的答案。
* `overlap` 是 Report 裡**唯一不看 `Compare their`** 的數字（它比的是整條
  分布）—— 兩塊平均一樣、一塊卻是雙峰的時候，只有它看得出來。bin 走
  `pixel_hist` 的 0–255 固定格，因為這個數字要跟一個固定門檻比大小。
* 順手修掉一個只有做了才看得到的版面 bug：群名那一欄寬度寫死 46 px，
  Report 分三群之後畫面上是「ifference」「ributions」。改成由最長的群名算，
  而字級 QFont 與 QSS **兩邊都要設**（`* { font-size: 13px }` 會蓋掉
  `setFont`，只設一邊的話量到的跟畫出來的不同尺寸）。
* 另外把 `glv_stats` 檔頭那段還在寫 `(μ_T − μ_R) / σ_R` 的 SNR 說明改掉 ——
  昨天改公式時只改了 `compare_pixels` 那一份，同一件事兩份說法。

計畫書：[`docs/history/plans/F18-glv.md`](docs/history/plans/F18-glv.md) §8.7。

---

## F18 收尾三件（2026-08-21，使用者用起來之後問出來的）

### ① 「另一塊 @ 另一條流」沒有家 —— 而且它是**安靜地**錯

使用者問「test 取 EPI_center、ref 則是 EPI_others 要怎麼拉線」。答案是拉不
出來：第 5 步把 `method` 二選一拆成「跟誰比」時，我把四個獨立的角色參數壓成
一個下拉，而下拉只有兩種「另一個」。更糟的是 `another stream` 那條路**安靜地
忽略 `reference_region`** —— 跑得完、有數字，而那個數字答的是另一個問題；
遷移也照著同一個漏洞轉舊 recipe。

補上第四格，遷移改成完整的真值表。**這一格為什麼會漏值得記住**：我是從
「三個獨立的問題」那個漂亮的模型往下推的，而推出來的選項少了一個組合。
舊卡片那四個參數醜，但它們是**兩個獨立的座標軸**，所以表達得完；下拉是一條
線，要表達二維就得把格子列滿。

### ② SNR 全線改成 by box，而且不帶正負號

使用者：「by pixel 會太小」「SNR 不會有負值，有負代表亮暗差異而已」。

σ 從「參照那一塊像素之間」換成「參照那一塊**框與框之間**」（ddof=1）——
per-pixel 的 σ 裡有 shot noise，它比同材質格子彼此的差大得多，於是 SNR 被壓得
很小，**而那個小不是訊號弱，是分母裝錯東西**。`tstat` 的 n 跟著變成格數。

參照少於兩格 → `snr` / `tstat` **不寫**（外加一句話）：不退回 per-pixel
（同一個名字算出兩種東西是最難發現的錯），也不寫 NaN（§6.1 那張表）。

### ③ `roi_snr` 整張刪掉，Report 那一格變成膠囊

刪卡的代價這次很低 —— **沒有任何 fixture recipe 或黃金值用到它**（跟
`pattern_ref` 那次的價差正好是 CLAUDE.md 那張表在講的事）。連同
`algo.snr.roi_snr` 一起（那張卡走了之後它一個呼叫者都沒有）。

刪完才發現的產品問題：**卡片庫搜尋「snr」找不到 Gray level**，而它現在是唯一
產出 SNR 的卡 —— 那個字補進卡片的 `help`。

Report 那一格改用同一個 `MetricChips`（使用者：「Compare 跟 absolute 一樣重要，
而且它的 UI 沒有 Statistics 那麼漂亮」）。五個新小圖：Δ / ÷ / % 直接畫那個運算
的符號，`snr` / `tstat` 畫「差距 ÷ 散布」那個比例本身。

### 這一輪自己踩到的一個工具坑

用 `s[i:j]` 取一段再 `s.replace(old, new)` 的時候，兩個 anchor 的**順序反了**，
於是 `old` 是空字串 —— `replace("", new)` 會把 new 插進**每一個字元之間**，
一個 834 行的檔案變成 200 萬行。`git checkout` 救回來，然後改成逐段
`assert s.count(old) == 1`。

---

## F18 第 2、4、5、6 步：Gray level 收斂（2026-08-21，第三十二輪續）

使用者：「繼續到完成」。計畫書 [`docs/history/plans/F18-glv.md`](docs/history/plans/F18-glv.md)
六步做完，剩下的只有明確排在後面的兩件（`lot baseline` 的 two-pass、CD 重做）。

### 第 2 步：儀表換人，Spread 搬家

`glv_stats` 往 `ctx.meta["glv_hist"]` 留每一塊的 64-bin 直方圖，`GlvInspector`
畫它 —— **預覽就有，永遠不空**，整批縮成底下一條 8 px 的帶子。Spread 搬去
Results，多一個「Spread of ▾」的選擇列。

**最容易說謊的地方是標記**：三種統計量在灰階軸上不是同一件事 —— 位置畫線、
**寬度畫成中心兩側的淡帶**、單位不是灰階的不畫。第一版把 `glv_mad = 65` 畫在
灰階 65 的地方，而那裡什麼都沒有。寬度沒有中心可以掛的時候（只勾 MAD、沒勾
中位數）**不畫**：「這個數字沒有畫得出來的位置」是一個誠實的答案。

Spread 那邊也多學到一條**沒寫進計畫但不寫就會錯**的：**門檻是「分數」的門檻**，
所以看別的特徵時整張圖唯讀。計畫原本寫「直接在分布上拖門檻」—— 在
`glv_median` 的分布上拖門檻會拿一個跟畫面無關的值改掉 bin。

### 第 4 步：哪些像素算數，以及量不出來的時候寫什麼

三個旋鈕（全部預設不作用）＋ `glv_pixels` / `glv_ok`。

**計畫寫「量不出來吐 NaN」，而 repo 自己的守門測試當場否決了它 —— 它是對的**：
`NaN < threshold` 是 False，那顆 defect 會被**安靜地判成真缺陷**。NaN 比 0 更糟，
因為它看起來比較誠實。改成**不寫那幾格**：沒有人引用就什麼都不會發生，有人引用
就當場失敗並指名那個變數。

### 第 5 步：compare 不是另一個 method

`method = stats | compare` 的二選一拆成「跟誰比」的一格（四個答案）。整張卡只剩
一條路，四個 `resolve_*` 不再分岔。**相對值的特徵名逐字不變**，兩道遷移串起來
（`roi_compare` → `method="compare"` → `reference`），走第二次是 identity。

一條舊不變量跟著改：`ROLE_PORTS` 原本鎖「不准混用清單來源與角色埠」。新設計是
**故意混用**的 —— 主埠是清單（多連一），參考埠是單數（一次只跟一個比）而且只在
說要比的時候才長出來。舊規矩防的是「同一個概念輸入有兩種形狀」，那件事沒有回來。

### 第 6 步：計畫的前提是錯的，去看資料模型才發現

計畫假設 RSEM 上會接到「幾百個區域」，然後靠**區域數量**自動切換成聚合。
資料模型不是那樣：**一個名字底下就是好幾個框**（`roi_from_mask` 的一層是一個
名字配幾千個矩形）。所以該切換的不是「接了幾個區域」，是「這個區域裡的框要
一起量還是一格一格量」—— 而那是使用者答得出來的問題，所以它是一個參數
（`across_boxes`），不是一條猜出來的規則。

一格一格量之後每個數字變成 `_typical` / `_outlier` / `_outlier_box`
（那個 box index 就是缺陷定位的答案），外加一個 `boxes`。逐格吐特徵是寫不出
宣告的 —— 框的數量隨影像而異。

### 這一輪的形狀

**四次「計畫寫的跟落地的不一樣」，每一次都是 repo 或資料模型把我糾正的**：
預覽帶的位置（設定區拿不到引擎的資料）、NaN（守門測試）、拖門檻（門檻是誰的）、
以及第 6 步整個前提。四次都記在計畫書對應的小節裡，而不是默默改掉。

⚠ **`glv_pixels` 讓每張 Gray level 卡多一個特徵**，`tests/fixtures/golden/`
的特徵名集合因此對不上（值一個都沒動）—— 請在家用機重跑
`python tools/freeze_golden.py`。

---

## F18 第 1 步：Gray level 的統計量與它的選法（2026-08-21，第三十二輪續）

計畫書：[`docs/history/plans/F18-glv.md`](docs/history/plans/F18-glv.md)（§10.1 是這一步的落地
紀錄）。使用者：「1,2 都做」「3 好」「METRIC 部分的 UI 我希望更漂亮一點」。

### 計畫寫「第 1 步純 UI」，落地時把引擎那一半一起做了

那不是範圍蔓延：**晶片上列得出來的每一顆，引擎都要真的算得出來**。只做 UI 的
話那是一排按了沒事的鈕，比原本的勾選網格更糟。所以 `algo/glv.py` 補上
`glv_mad` / `glv_iqr` / `glv_skew` / `glv_kurt` / `glv_entropy` /
`glv_bimodality` / `glv_sat_frac`，加上兩種帶數字的 id `glv_trim<NN>`
與 `glv_above<NN>` —— 形狀跟既有的 `glv_q<NN>` 一模一樣，因為**多一種語法就是
多一種打錯的方式**，而這些字串在手寫 recipe 裡是人打出來的。

每一顆都防呆：整塊同一個值（飽和的 patch 上很常見）與空的 patch 一律回 0.0，
不回 NaN —— 一個 NaN 進了分數表達式就是「跑得完、有數字、而且是錯的」。

### 預設換成 robust，而它換得掉是有前提的

`glv_mean,glv_std,glv_p50` → `glv_median,glv_mad,glv_min,glv_max`。
換之前先查了那個前提：`add_step` 走 `validate_params(cleared_inputs())`，
**每一格都會被寫進 recipe**，所以既有檔案帶著自己那一份 metrics（兩份 fixture
recipe 也都明寫了）。新加一條測試把那個前提本身鎖起來 —— 預設一旦沒有被寫進
params，改預設就會安靜地改掉舊 recipe 的數字。

三支既有測試跟著改：兩支拿預設當前提（改成明寫 `metrics`，它們測的是快取與
多入口）、一支問 `epi_glv_mean`（改問 `epi_glv_median`，它測的是**前綴**）。

### 晶片：分群的膠囊，每顆帶一個「它在分布上是哪一段」的小圖

共通語言是**「淡的那條線是分布本身，實的那一筆才是這個統計量在講的東西」**：
median 是把面積切一半的線、mean 是天平的支點、MAD 是中位數兩側的一段、
IQR 是箱形圖的箱子、bimodality 是兩座山中間的谷。十五張圖的差別只在「實的那
一筆標在哪」—— 而那正好就是這些統計量彼此唯一的差別。

**第一版有六顆是廢的**，而那是 render 出來逐顆看才發現的：`mean` 只是
「`median` 沒填色」、`trimmed` 的虛線在 19 px 下整條不見、`skew` 的箭頭搶戲
而不對稱的山根本看不出來、`percentile` 跟 `median` 幾乎一樣。最後那一顆的修法
是把它拆成兩個圖形：`percentile`（一條線 + 左半填滿）給真的分位數，`plus`
（一個 ＋）給「再加一顆」那種**動作**膠囊 —— 它們會並排在同一列上。

還有一個只有畫出來才看得到的坑：QSS 的 `* { font-size: 13px }` 會**蓋掉
`setFont`**，於是「量寬度用的字」與「畫出來的字」不是同一個 —— 症狀是膠囊右邊
被切掉半個字母（`Trimmed mean` 少了半個 n）。字級改成 px 並同時寫進 stylesheet。

`+ Percentile…` 與 `+ Above…` 做成**同一種膠囊**（虛線框）而不是按鈕：那一列
上混一顆長得不一樣的鈕，讀起來像是它跟旁邊那些不是同一件事。

### 預覽帶搬去儀表（第 2 步），不在設定區

計畫書畫的 mockup 裡，晶片上方有一條「這一顆的直方圖 + 標記」。落地時它搬到
儀表 —— 理由不是工程方便：設定區（`ParamForm`）拿不到引擎算出來的東西，要在
那裡畫分布只能畫一條**假的**，而「畫面不能說謊」是這個 repo 花了六個坑換來的
規矩。儀表本來就吃 `ctx.meta`，那才是它的家。

驗收：`tests/test_glv.py`（+5）、`tests/test_steps.py`（+2）、
`tests/test_ui_widgets.py`（+5，含十五張小圖在 19 px 下兩兩比畫素）。

---

## 左側 rail：三個階段共用一個打勾，以及卡片區的高度會飄（2026-08-21，第三十二輪）

使用者兩句話，兩個都是「畫面在說謊」那一類：

### ① 「Algo ADC Output 都是一樣重複的」

`draw_group_icon` 明寫了 input / enhance / region / compare / measure 五段，
其餘**落在 `else` 的那個打勾**。F16 加進來的 Algo 與 Output 沒有人補圖，於是
最後三顆（Algo / ADC / Output）畫出來逐畫素相同 —— 而顏色也救不了：F16 那兩段
的階段色刻意比前六個淡（`theme.py` 有寫理由），三個打勾裡有兩個是低彩度的。

三顆新的圖，每一顆都講得出自己那一段在做什麼：

| 段 | 圖 | 為什麼是它 |
|---|---|---|
| Algo | **Σ** | 這一段一張影像都不碰，所以圖裡刻意**沒有任何方框** —— 其他七顆全是某種框或版圖。Σ 是試算表裡「這一格是算出來的」那顆鈕，而 `feature_math` 做的正是那件事 |
| ADC | **標籤**（尖頭 + 孔）| 產物是 score + **bin**，「貼上一個分類」就是標籤。尖的那一頭讓輪廓在 15 px 下不像任何一個方框 |
| Output | **敞口托盤 + 往外的箭頭** | 跟 Input 是**一對**（同 glyph 的 save / export）：一樣是托盤加箭頭，差別在箭頭往哪走。托盤敞口 —— Input 那個是封起來的方匣（東西掉進去），Output 是東西離開的地方 |

打勾**留著**，但降級成「沒見過的 group」的保底，不再代表任何一段。

新測試 `test_every_stage_icon_is_a_different_shape`：把八顆都畫在 15 px 上
（區塊標題與畫布節點磚的尺寸，會先在小的這一邊糊掉），兩兩比差幾個畫素，
低於 24（≈ 一成）就紅。最接近的一對是刻意相像的 Input / Output（35 個）。
斷言「有沒有寫 elif」沒有用 —— 兩段各寫各的、畫出同一個形狀也會過。

### ② 「點 Input 出來的選擇 card，跟點 output 的高度不一樣」

卡片庫的八段是「標題 + 一個巢狀 QVBoxLayout」排在同一個 `_body` 裡，收起來時
只把**標題**藏起來。而**一個藏起來的 widget 在父層 layout 裡是零，一個空的
巢狀 layout 不是** —— 它的 `contentsMargins`（下緣 8 px）照算。於是排第八的
Output 被前面七段各推 8 px，標題落在 y=58，Input 在 y=2：點不同的段，卡片區
就從不同的高度開始，上面留一條會變長變短的空白。

修法是給每一段的卡片列一個自己的容器 widget（`#libSection`），跟標題一起顯示、
一起隱藏。八段現在一律從 y=2 開始。`test_every_stage_opens_at_the_same_height`
量的是「標題離捲動區頂端多遠」而不是某一段的實作，所以之後卡片區怎麼重排都還
擋得住這件事。

（兩件事都只動 `d4t/ui/widgets.py`；引擎、recipe、黃金值一個字都沒動。）

### ③ 同一輪談定了 GLV 量測卡的重做（設計，還沒動工）

計畫書：[`docs/history/plans/F18-glv.md`](docs/history/plans/F18-glv.md)。三個定案：
**`compare` 併進 `reference` 維度**（絕對值與相對值同一張卡同時吐）、
**預設 metrics 換成 robust**（median/MAD）、**Spread 搬去 Results 並且可以拖
門檻**。

第三件事使用者的原話是「他在 run 之前都是空的」，而那句話有程式碼上的證據：
`EnhanceInspector` 讀 `ctx.meta`（預覽就有）、`MeasureInspector` 讀
`trial_results`（跑完才有）—— 同一塊面板、同一個位置、兩種資料生命週期。
量測卡的儀表要換成**這一顆的直方圖**，整批的資訊縮成底下一條 8 px 的帶子。

Metric 的選法從勾選網格改成**分群的膠囊晶片，每顆帶一個「它在分布上是哪一段」
的小圖**（median 是把面積切一半的線、mean 是天平的支點、MAD 是中位數兩側的
一段、bimodality 是兩座山中間的谷）。mockup 是用專案自己的 theme token 真的
畫出來的 —— 十六顆小圖在 19 px 下逐顆看過，改了六顆才分得開（第一版的 mean
只是「median 沒填色」，trimmed 的虛線在那個尺寸下整條不見）。

---

## F17：讓 DAG 引擎名實相符（2026-08-20，第三十一輪）

這一輪從一個小問題開始 ——「特徵要不要開第三種埠」—— 然後一路查到引擎，
翻出一個比原題大得多的東西。

### 使用者兩次把我的前提推翻，兩次都對

**第一次**：我端出「做／不做／延後」三個選項，他問「一定要多阜嗎? 多一種阜
可能就會有多的學習成本」。我當場翻盤說他對 —— 而他接著說「**你確定我是對的嗎?
請客觀分析? 我不一定是對的**，而是要提出優劣（不要我反駁你就說你是錯的）」。
那句話是這一輪最有價值的一句：**反駁不等於我錯**，要重新分析而不是換邊站。
客觀分析之後的結論是「他的學習成本論點是關於**形式**的，不是關於**要不要看得
見**的 —— 兩者我都混在一起了」。

**第二次**：我說「特徵跟著影像走有缺點」，他說「以目前給的資訊我沒看到實質性
的缺點（**或者你必須舉例給我看**）」。舉例的結果是兩個具體的東西：

* 分岔 recipe 上，接在 test 那支的 Algo 卡拿到的是 **ref 那支的值**
  （107.2712 vs 107.2673，差 0.0039，兩個都是 107.27 —— 看不出來）；
* 更硬的一條：`feature_math` 的**影像輸入埠、影像輸出、區域埠都是 0**
  —— Algo 段的卡按定義不在影像的 DAG 上，要「跟著影像走」得給它兩顆假埠。

而他的第三點（「沒辦法跟區域走，因為並不是每次都需要 ROI」）我確認是對的，
而且理由比他講的更硬：區域埠是**參數宣告**出來的，加一個 ROI 參數等於強迫每份
用到 Algo 的 recipe 都要有一張 Region 卡。

### 真正的診斷：這不是純 DAG 引擎

`recipe.py` 的 `execution_order` 除了 `edges` 之外，還把 **route 上相鄰的每一對
也當成一條邊**。那串隱含邊構成一條走遍全部節點的鏈，所以執行順序**恆等於
route 順序** —— 而 route 順序在畫布上就是卡片的左右位置。

**兩張沒有任何線相連的卡，誰先跑由使用者把它拖到哪裡決定，而畫面上看不出來。**

鐵則 9 那句「資料從哪來由線決定，而畫布上每一條線都是使用者拉的」是真的，但
**執行順序的邊有一半不是線**：UI 照純 DAG 畫，引擎不照純 DAG 跑。那個落差正是
「特徵沒有線」「Output 卡沒有埠」的共同根源。

### 四件事，一件一個 commit，每件都先過黃金值

**① 順序只有一個家。** 拿掉隱含邊。這一項最值得記的是它**可以證明無害**：
隱含邊是一條 Hamiltonian path → 舊順序唯一等於 route 順序；跑得起來的 recipe
其線必然往前走 → Kahn 用位置當 tiebreak 出來還是 route 順序。黃金值不動，
實測與證明一致。唯一的行為改變是「一條往回的線」以前是 cycle 錯誤，現在照線跑。

**③ 快取邊界從宣告推導。** 症狀早就出現了而我沒看見：五張 Output 卡的
`category` 是 `CATEGORY_ADC`，而它們跟 ADC 毫無關係 —— 填那個值只是為了落在
checkpoint 之後（**那是我上一輪自己做的**）。改成問「這張卡吐不吐影像流」。
實作時漏了 `validate_params`，測試當場抓到：recipe 只存使用者填過的鍵，缺鍵時
`resolve_writes` 回空 → 一張正常的 Enhance 卡被判成不吐影像 → checkpoint 縮到
只剩 Load，症狀會是「改接線、重跑、數字沒動」（F9-8 那個坑的重演）。

**② 特徵的擁有者是結構。** 使用者一直看不懂我的舉例，最後我直接跑給他看：

```
做法一 ── 一張 Gray level 卡，test 跟 ref 都接進來
      test_glv_mean = 107.2673      ref_glv_mean = 107.2712
做法二 ── 兩張 Gray level 卡，各接一條
      glv_A_glv_mean = 107.2673     glv_mean = 107.2712
      ↑ glv_A 是節點 id，對使用者等於 node_3
```

**同兩個數字、同一件事，只因為用一張卡還是兩張卡做，名字一種看得懂一種看不懂。**
這一項把下面那一種的前綴補成流名。**跑出來比講道理有效** —— 前面我用文字解釋
了三次都沒說清楚。

分支測試抓到一個我沒想到的問題：**流名不足以分辨分支**。同一條 ref 分岔成兩支
之後兩支都叫 ref（身分是 `(節點, 埠)` 不是名字），所以兩支各自的 `mean` 都叫
`ref_mean` 會比原本的 `m3_mean` **更不清楚**。修法是整份 recipe 一起算前綴再
去重，撞在一起的全部退回節點 id。**一張一張獨立算看不到這件事。**

黃金值這一項動了，而**「動了要先查清楚」那條規則救了一次**：查完確認只有兩個
被蓋掉的診斷數字換名字，值、score、bin 逐項相同，才重凍。

還有一個 `CLAUDE.md` §0 的實例：`studio._feature_sections` 也在用節點 id 自己組
那個名字，兩份說法一改就漂 —— 症狀是救回來的診斷數字**以「量測值」的身分排到
最上面**，而那正是那段註解當初警告的事。

**④ 一顆與整批是兩個尺度。** `Step.scale` 取代布林（布林答不出「還有第三種
嗎」），`is_batch` 變成推導的，**而且兩個方向都通** —— 舊卡片直接寫
`is_batch = True` 仍然認得，否則一張沒遷移的卡會被當成逐顆的，而它的 `run()`
是一句「這張卡不該這樣跑」＝ 每一顆都失敗。
順手把「Output 是 end point」從「這幾張卡的 writes 剛好是空的」變成一條 lint
（`batch-card-has-downstream`）。

⚠ **「試跑不寫」沒有因為統一而消失**：統一的是**宣告**不是**入口**，
`run_batch` 只跑、`run_batch_steps` 才寫，那兩條守門測試原封不動。

### 合併前的引擎審查：三個發現，最嚴重的是這一輪自己加的

使用者說「先瀏覽整個 engine 看看有沒有奇怪的地方，沒有的話就 merge 回 main」。
有東西。

**🔴 A. F17-② 那道遷移在 worker 那條路上不是 identity（違反鐵則 9）。**
它跑在 `from_json_dict` 裡，而**它不冪等**：一份 recipe 裡有一個節點叫 `test`
時，`norm_clip_frac` 第一次被換成 `test_clip_frac`、**第二次又被換成**
`diff_clip_frac`。而那條路正是 `run_batch` 送 recipe 進 worker 走的 ——
後果就是鐵則 9 的原句：`workers=1` 與 `workers=2` 算出不同的分數。

**可達性不是理論的**：節點 id ＝ step key（`viewmodel._new_id`），而 `snr_map`
既是 step key 也是那張卡吐出來的流名。

修法值得記住它的形狀：**其他幾道遷移冪等是「構造上的」**（`also_apply` pop 掉
就不在了、改名的卡換成新 key 就不再符合舊 key），而這一道**換出來的新名字與它
要換掉的舊名字活在同一個命名空間裡**。所以它不能靠「寫得夠小心」冪等，要靠
**根本不會跑第二次** —— 搬進 `Recipe.load()`。查過三個入口：Studio 與 CLI 走
`load`，而 `from_json_dict` 唯一的另一個呼叫者就是 worker。
一句話：**遷移屬於「讀一個檔案」，不屬於「重建一個物件」。**

**🟠 B. 遷移跟執行時各算一次「同一件事」。** 執行時的前綴表是**那一條 route**
的 order 算的，遷移卻拿**整份 nodes** 算 —— 去重的池子不一樣。實測兩條 route
各一張 `normalize`：執行時兩邊都是 `test`，遷移判成撞名 → **一個字都不遷移**。
通則：**一個函式如果「答案取決於餵給它的清單」，兩個呼叫端就必須餵一樣的清單。**

**🟡 C. 三處註解在 F17-① 之後變成假的**（`canvas.py` ×2、`viewmodel.py`），
都還寫著「引擎的依賴是 route 相鄰對 ∪ edges」。行為不用改（排版照排列擺仍然
忠實，因為那是 Kahn 的平手依據），錯的是解釋。

**⚪ D. 一個重複記帳，刻意不改** —— `add_feature` 記一次、`_rescue` 用宣告再
覆寫一次。今天不會不一致，拆掉要重驗 F9-3 整條而收益是零。記進 PITFALLS，
並寫明「會不一致的那一天長什麼樣」。

守門測試 `tests/test_recipe_roundtrip.py`：每一份 fixture ＋ 對抗案例（節點 id
等於流名）連續 round-trip 三次都要是不動點。**先把修法拿掉確認它真的紅**，
再放回去 —— 既有那條真的開 `workers=2` 的測試抓不到，因為它跑的是一份沒有那個
形狀的 recipe。

### 結論：不開新埠

特徵既不需要埠也不需要線 —— **名字就是線**。`test_glv_mean` 自己就說了它從哪來，
而那是 ② 的自然產物，不是另外加的東西。

---

## F16：畫布的八段（2026-08-20，第三十輪）

使用者一次講完了八件事，而它們合起來是同一件：**把畫布的形狀變成他心裡的形狀**。

```
Input → Enhance → ROI → Measure → Algo → Compare → ADC → Output
```

### 先更正我上一輪講錯的一句話

我說「Measure 排在 Compare 前面跟 diff 要先產生是衝突的」。使用者：「不太懂為
何會衝突? 我畫布上的線，也不一定要有 Measure 對吧 (硬限制在哪?)」——**他是對
的**。追下去：`GROUP_ORDER` 只影響卡片庫分區順序、rail 上下順序、階段顏色；
執行是 `recipe.execution_order()` 的 DAG 拓撲排序，畫布排版吃的是
`layout_columns(self._order)`＝節點順序。`core` 裡只有兩處讀 `resolve_group()`
（`uneven-treatment` 只對 Compare 卡發動、`card-order` 只記 Enhance 卡的歷史），
兩處都跟**位置**無關。我把「排版順序」跟「資料流順序」混成一件事了。

### 這一輪做完的四段

**Stage 1 —— 段落、改名、刪卡、清 blob。** 加了 `GROUP_ALGO` / `GROUP_OUTPUT`
並重排；階段色 6 → 8（新那兩個刻意比較淡：六個色相已經把圓周分掉了，硬塞兩個
一樣濃的進去，最近的一對會掉到 ΔE 25 的線上）。四張卡改名（`CD` / `SNR` /
`H2H` / `Image Combination`）—— 只動 `label`，`key` 與 feature 名一個字都沒改。

**刪掉 `pattern_ref` 的代價這一次真的付了。** rsem route 靠它造 ref 才有 diff
可量（24/24）。拿掉之後那條 route 重做成「直接量單張影像」，實測 seed 11/3/21
三次都是 **12/24，而且是因為它把每一顆都判成 bin 0**（那 24 顆裡正好 12 顆沒有
缺陷）—— 分數尺度從 5–30 掉到 2.5，而門檻是 4.2。所以 e2e 的 rsem 斷言從準確率
改成「跑得完、算得出分數」，並在 docstring 寫明那個證據為什麼沒了。

順帶：`docs/PITFALLS.md` 最後一列寫著「分支+快取：冷跑≠熱跑（**未修**）」，
而它在 F9-10 就修好了。**一列說「未修」的已修坑，會讓人去追一個不存在的鬼。**

**Stage 2 —— 兩張 GLV 卡收成一張 `Gray level`。** 使用者說它們「應該是做同樣
的事」；讀完之後**不是** —— `stats` 吐絕對值、`compare` 吐差異，而 compare 的
`stat` 從不輸出那個絕對值。所以是收成一個下拉，不是刪掉一張。
唯一特別的地方是**兩種 method 的接線方式不同**（清單 vs 角色埠），埠因此隨
method 變形；`ROLE_PORTS` 那條不變量改成「在**這組參數下**是哪一類」，兩邊都驗。

**Stage 3 —— Algo 段第一張卡 `feature_math`，而它逼出兩個引擎缺口。**
① 吃「特徵」的卡一直沒有宣告（影像有 `resolve_reads`、區域有
`resolve_regions_in`）→ 新增 `resolve_features_in` ＋ lint `unknown-feature-input`。
② `is_source()` 把它當成入口卡 —— 判準是「沒有輸入埠、也沒有靜態 reads」，而在
F16 之前每一張符合的卡都是 load 卡，所以那個巧合一直成立。被當成入口的後果是
**整條 lint 對它靜音**（validate 對入口卡會 `continue`），於是①那條 error 根本
走不到。判準加第三條：**入口 = 沒有輸入、而且憑空生出影像流**。

⚠ **明講沒解決的**：畫布上沒有線指進 Algo 卡。特徵是扁平的全域命名空間，
d4t 從來沒有「這個數字是哪張卡算的」這種埠（分數表達式也是這樣），所以相依性
靠 route 順序。要變成一條線得先決定**第三種埠**長什麼樣 —— 那跟「跨顆那一層」
是同一個題目。

**Stage 4 —— main lot 的 KLARF 欄位帶成 feature。** ADC 的前置（使用者：
「利用 feature 內數值資料跟原始 klarf 帶的資訊去做分類」）。做法沿用 F15 的
`carry`：只帶點名的那幾欄、打錯欄名擋在跑之前、非數字的欄位進 meta 不進
features。`columns_of` / `fill_fields` 搬回 `ingest/dataset.py`（它們問的是一份
Dataset 的事，跟配不配對無關），`pair_source` 仍然 re-export。

踩到一個安靜的 bug：`recipe.nodes` 是 `{id: RecipeNode}`，**直接迭代它拿到的是
id 字串**，於是 `columns_for_main` 回空清單、一欄都不填，而症狀是「這份 KLARF
沒有那個欄位」（那句話是錯的 —— 欄位在，只是沒複製）。只有 CLI 那條路踩得到，
所以補了兩條 subprocess 的端到端測試。

### 黃金值

**只有 Stage 1 動了一次**（rsem route 重做），Stage 2–4 三組逐項相同 ——
合併、開新段、加 `carry` 都沒有動到任何既有的數字，那是每一步的定義。

**Stage 5 —— 跨顆那一層 ＋ Output 段五張卡。** 使用者定了三件事：**試跑不寫、
只有整批才寫**、**路徑存在卡片上**、**先做引擎，畫布那一半下一輪**。

機制：`Step.is_batch` ＋ `BatchContext` ＋ `pipeline.run_batch_steps`。
三條規矩各有測試：跨顆卡不在 `run_defect` 裡跑（而且**跳過不是報錯** —— 一份含
Output 卡的 recipe 在單顆預覽上要跑得完，那是調參數的畫面）、一張跨顆卡出錯不
影響其他卡（鐵則 7 的跨顆版）、**試跑不寫**。

最後那一條的做法值得記住：它**不是一個旗標，是兩支函式**。`run_batch` 只跑，
`run_batch_steps` 才寫，而試跑那條路根本不叫後者。旗標遲早有人忘記關，而症狀是
不可逆的覆寫（拖一下門檻就覆寫一次 KLARF）。有一條掃原始碼的測試守著 `d4t/ui`
底下沒人叫它。

五張卡：`output_csv` / `output_report`（Excel）/ `output_klarf`（三種寫回模式）/
`output_html`（自帶樣式，可以直接寄出去）/ `output_image`（每顆一張疊圖）。
**五張都是 `is_batch`，包含 `output_image`** —— 它看起來是逐顆的，但做成普通
Step 的話它會在 `run_defect` 裡跑，而那條路每切換一顆 defect 就走一次。

實測 CLI（六顆的合成 lot）：五個產出都出現，KLARF 走 annotate **原檔一個位元組
都沒動**，新檔多了 ADCSCORE / ADCCLASS 兩欄。

### Stage 5c —— Studio 的整批入口，然後精靈真的走了

上一輪那句「⏸ Export 精靈還在，而那是順序問題不是漏掉」這一輪結案了。順序照著
走完：**先有入口，逐位元組驗過，才刪。**

**① 入口。** 在此之前「Run all defects」跟「Run trial」是**同一支函式、同一條
路**，差別只有 `limit` —— 所以「試跑不寫、整批才寫」在程式裡根本沒有地方成立。
現在 `run_all()` 是自己的入口：旗標**跟著那一次執行走**（按了之後可以馬上去改
別的東西）、**中途按停止不寫而且講出來**（部分結果寫進 KLARF 是不可逆的錯，
而安靜地不寫跟安靜地寫一樣糟）、寫檔走 `OutputWorker`（`output_image` 一顆一顆
重跑 pipeline，在 GUI 執行緒做會僵住幾十秒）。

工具列那一格從「Export…」變成「**Run all & write**」—— 同一個位子、同一件事
（把結果寫出去），差別是寫什麼、寫去哪現在看得見。它的前提也跟著換了：以前那顆
鈕開的是一個**吃結果**的對話框，所以「先跑一次才會亮」；現在它自己就是那一次跑。

**② 寫回前一定先預覽**（M5 的硬性規則）不能因為精靈消失就消失。精靈的做法是把
「寫出」鈕鎖住直到按過預覽；乾跑一個位元組都不寫，所以它其實**不需要那顆鈕**：
搬成 `output_klarf` 的 inspector 之後，選到那張卡就看得到會改幾列、寫去哪、原檔
動不動 —— 比精靈**更早**。確認對話框只在 `inplace` 跳（使用者定調），判準是
**會不會動到原檔**不是是不是 KLARF：每次都問的話那個確認很快就變成閉著眼睛按掉
的東西，而它要擋的正是那一種。停用的卡不跳 —— 不會跑的東西跳確認就是騙人。

**③ 那份逐位元組的比對是刪精靈的許可證，而它真的抓到東西。** 同一批結果兩條路
各產一次：CSV、KLARF 三種模式（topn 兩種填法）、疊圖 PNG 全部**逐位元組相同**，
Excel 逐格相同（`.xlsx` 是 zip、檔頭有時間戳，比位元組會是一條每次都紅的測試）。
抓到的是兩件**精靈有、卡片沒有**的事，而兩件都看不出來：

* 疊圖左上角少了 `score=` / `bin=` —— 一疊沒有分數的 PNG 跟完整的長得一模一樣，
  而使用者正是拿它們來挑門檻的；
* 檔名沒有消毒 —— id 裡有 `/` 或 `:` 的那一顆會讓那張卡失敗，而鐵則 7 把例外
  吃掉之後症狀只是「少了幾張 PNG」。

兩支（`overlay_label` / `overlay_filename`）都搬進了 `core/export/overlay.py`，
跟上一輪的 `pick_overlay_results` 同一個理由：**它們問的不是畫面的問題**。
形狀是重複的 —— 精靈裡每有一件「順手做了、沒人知道」的小事，就是卡片將來會少的
一件事，而它只有在逐位元組比對之下才會現形。

**④ 刪掉。** `d4t/ui/export_dialog.py`（1213 行）、工具列的 `Export…`、
`results.export_requested` 接線、`open_export_dialog`、`tests/test_ui_export_dialog.py`。
**`core/export/` 一行都沒刪** —— `klarf_out` / `report` / `overlay` 是 Output 卡
的引擎，精靈只是曾經的呼叫端之一。CLI 的 `d4t export` 子命令保留（使用者定調
「下一輪再看」）：它跑的是「已經跑完的結果重新匯出」（從 SQLite 歷史），
跟 Output 卡不完全重疊。

**⑤ 那條掃原始碼的守門測試收窄了，不是刪掉。** 它原本斷言「`d4t/ui` 底下沒有人
叫 `run_batch_steps`」，而它自己的 docstring 早就寫著「那一天這條測試要改成
『只有那一個入口叫得到』」。現在它斷言只有 `workers.py` 叫得到，並且**再往內一
層**（`ast`）確認那個呼叫者是 `OutputWorker` 而不是同一個檔案裡的 `TrialWorker`
—— 檔案層級的名單擋不住「有人在試跑那條路的 job 裡多加一行」。

黃金值三組逐項相同（Stage 5c 一個數字都沒動）。

---

## F15 停在這裡：太快了（2026-08-20，第二十九輪）

使用者叫停，而且指出的問題比「操作步驟多」深一層：

> 我說的難操作是 **我看不出來有沒有對好、對到，有沒有把 data 整理好（一一對應）**
> …現有的功能只是告訴我有對到（**但是不是不知道**）→ 這功能最終是想要產出一個
> 類似**點對點包含圖的 report**，但我覺得現在做這邊「**太快了**」

### 這一句是對的，而它推翻的是我上一輪的診斷

我上一輪的診斷是「14 步太多」。那是**累**，不是**不能用**。真正的問題是
**這個功能不產生證據**：它吐 `paired=1`、`ncc_score=0.99`、`match_dist_nm=170`，
而那些數字全都在說「有對到」——**沒有一個在說「對得對不對」**。

而「對得對不對」對這件事來說是唯一重要的問題（EBI ↔ RSEM characterization 的
結論會拿去下判斷）。一個只會說「我配好了」的配對工具，跟沒有是一樣的 ——
使用者仍然要自己一顆一顆開圖確認，那正是他想省掉的事。

**它缺的東西有名字：那份 report。** 一顆一列、左右兩張圖、加上那幾個數字，
讓人**一眼掃過去就看得出哪幾顆可疑**。`pair_probe` 的分布是給調參數的人看的，
不是給「檢查這批對得對不對」的人看的 —— 那是兩件事，而我只做了前面那一件。

### 而且順序錯了

`docs/ROADMAP.md` 的 Compare 那一列本來就寫著「**配對機制也在這一段**（使用者：
配對是之後的事）」。F15 從那一列裡挑了最下面那一項先做，而**它上面的東西
（patch ↔ RSEM 對位的其他部分、Compare 段本身）都還沒做好**。使用者：
「我目前 Compare 下面段都還沒做好」。

### 使用者對 Studio 的段落藍圖（記下來，這是第一次講完整）

> Input · Enhance · ROI · Compare · Measure · **Algo** · ADC · **Output**
> 然後再加給幾個 **for Custom 的設計**（幫助工程師，像上面這個就是）

對照現在的 `GROUP_ORDER`（`Input → Enhance → Region → Compare → Measure → ADC`）：

| 段 | 現況 |
|---|---|
| Input / Enhance / ROI(=Region) | ✅ 已收斂 |
| Compare | 做到一半（F15 是它的一小塊，而且是最後那一塊）|
| Measure | 缺 Blob 分割等（見 ROADMAP）|
| **Algo** | **不存在** —— 目前 `algo` 是卡片的 *category* 不是畫布上的一段 |
| ADC | 一張卡都沒有（最大的缺口）|
| **Output** | **不在畫布上** —— 目前 Export 是一個精靈，不是一段 |
| **Custom 這一層** | 新概念：F15 是第一個，但它現在跟主段落混在同一個卡片庫裡 |

最後那兩列是新資訊：**畫布上少了兩段，而且「Custom」是一個還沒有形狀的層級。**

### F15 的處置

**不刪、不收起來、停在原地。** 引擎那一半是對的而且有測試（配對、對圖、尺度、
搜尋框、stage offset、`pair_probe`）；缺的是產品化那一半（證據 + report）。
等 Compare 段做完再回來接它 —— 那時候「一一對應看不看得出來」會跟 Compare 段
其他卡的答案長成同一個形狀，而不是我現在硬掰一個。

---

## 按了鈕、畫面沒事發生（2026-08-20，第二十八輪）

使用者：「Pair with another source 將 klarf+圖片 load 進去時 → 右側 image stream
會有 image 嗎？」

實測之後：**掛完之後預覽沒有重跑**，所以影像流的下拉裡沒有 `paired`，要再去點
一張卡才會出現。而「按了鈕、畫面沒事發生」讀起來就是「載不進來」—— 那正是前面
連續兩次回報的那句話的第三種形狀。

掛上第二份 = **這條 pipeline 的產出變了**，所以 `_on_pair_source_loaded` 現在
會 `_schedule_preview()`。（載主資料集、改參數都會，就這一條漏了。）

順帶釘住一件**看起來很像壞掉、其實是刻意的**事：預覽只跑到**選中的那張卡**為止，
所以停在 `Pair` 上是看不到 `aligned` 的 —— 要點到 `Align` 那張卡。
`tests/test_ui_f15_pair_source.py::test_the_aligned_image_needs_the_align_card_selected`

---

## 儀表畫不出來，症狀出現在別的地方（2026-08-20，第二十七輪）

使用者：「現在是 Pair with another source 的圖就載不出來」，終端機一直丟
`ZeroDivisionError: float division by zero` 指著 `inspectors.py` 的
`row_h = body.height() / float(len(names))`。

**壞的地方跟看到的地方不一樣**：`PairInspector` 手上有配對資訊（所以說「有資
料」），但整批的數字要跑一批才有 —— 於是 `MeasureInspector.paint_body` 拿到
0 列，那一行是除以零。而 Qt 的 `paintEvent` 一丟例外就留下一個沒收尾的 painter
（`QBackingStore::endPaint() called with active painter`），接著每一次重繪都
再失敗一次，於是使用者看到的是**影像區**壞掉。

而「只跑過一顆（預覽）」在這張卡上是**常態**，不是邊角 —— 切一顆 defect 就會走
到那裡。

兩層修法：

1. **`Inspector.paintEvent` 不准把例外往外丟** —— 鐵則 7 的 UI 版：一個面板畫
   不出來，只准變成那個面板的一行字。例外照樣 `traceback.print_exc()`（不要藏），
   painter 一定收尾。
2. `MeasureInspector.paint_body` 沒有任何一列就畫「空的理由」而不是除以零；
   而 `PairInspector` 的那句話要分得出**配到了**（「跑一批才看得到分布」）與
   **還沒配到**（「用這張卡上的 Open data…」）——兩句不同的話。

---

## 第二份只送進了一半的路（2026-08-20，第二十六輪）

使用者：「Pair with another source，我載入 image（RSEM 的 GT，23 顆），不會有圖
（是不是因為我用的是 PNG 檔案）　拉過去 Align to stream 也沒有圖」。

**不是 PNG**（`.png/.tif/.tiff/.jpg/.jpeg/.bmp` 都吃）。是 F15-A 的我漏了一半：
`run_batch` 那條路把 `sources` 送進 worker 了，**單顆預覽那條沒有**。於是
`pair_source` 說「no lot is loaded as 'X'」，而症狀是「沒有圖」——
同一份 pipeline **按「試跑」有圖、切換 defect 沒圖**。

那個形狀是這個 repo 記過好幾次的那一種：**同一件事有兩條路，而只有一條被想到**。
單顆的路其實有四條，我當時只想到 0 條：

* `PreviewWorker`（切換 defect／改參數）
* `RegionCheckWorker`（區域檢查）
* `CalibrateWorker`（一鍵校正）
* Export 的疊圖（它是跑一次 pipeline 畫出來的）

修法：答案只有一份 —— `StudioWindow.sources_for_run()` —— 而每一條路都問它。
便利貼是一條**掃原始碼**的測試：`d4t/ui` 底下每一個 `run_defect(...)` 呼叫都要
帶 `sources=`，漏掉的那一條會被指名。掃字串是刻意的，它擋得住「新加一條路而忘
了傳」——而這個 bug 的形狀正是那個。

---

## 怎麼驗證：tools/pair_probe.py（2026-08-20，第二十五輪）

使用者：「我該怎麼驗證呢」。

F15 那條鏈有**四個猜不出來的數字**，而它們全都是**分布**不是單一數值 ——
容差要設多少、兩邊的 nm/px 比例對不對、stage offset 是多少（**以及 KLARF 的
y 軸與影像列方向誰正誰負**）、FOV 的 15% 夠不夠。一顆一顆看是看不出來的。

所以照 `load_probe.py` 那條路再寫一支：跑一批、印分布、**直接講出建議值**，
輸出預設遮蔽可以貼出來。

**工具自己要先是對的。** `tests/test_pair_probe.py` 自己造一份「大圖裡真的藏著
主 lot 那一塊 patch」的第二份 lot（stage offset 是我們放的 (12, −7)），驗報告
有沒有把它讀出來 —— 含尺度錯的那一種：報告要說「那通常不是配錯顆，是 nm/px
比例錯了」，因為前一句話會讓人往完全錯的方向查（去調容差、去看座標，而問題在
別的地方）。

合成資料證明不了真實資料會怎樣；它證明的是**這支工具沒有在說謊**。

讀報告的順序寫在計畫書 §15.2：**由上往下，前面的沒過就不要看後面的** ——
配對率 → 對圖分數 → stage offset → 散布 → peak_ratio，它們是串起來的。

---

## 只在該找的地方找（F15-4，2026-08-20，第二十四輪）

使用者把最關鍵的一句話講出來了：「RSEM 基本上就是移到 KLARF 座標（defect 在
中間），不置中的原因是機台 stage 移動的 offset」＋「可以抓 FOV ~15% 左右」。

那句話把「大海撈針」變成「量一個小偏移」：

* **`search_within`（預設 15% of FOV）** —— 只在圖中心附近那一塊裡做 NCC。
  快，而且**不會對到影像另一端那個長得一模一樣的結構上**（後者才是重點）。
  0 = 整張圖，那是這張卡單獨使用時的樣子。
* **`align_off_x_px` / `align_off_y_px`** —— 偏離預期位置多少，也就是**這一顆
  的 stage offset**。整批取中位數 = 這台機系統性的那一份，填回
  `expect_dx_px` / `expect_dy_px` 之後框就可以縮小；而每一顆偏離中位數多少，
  本身就是「這一顆配對可不可信」的指標。
* **`align_peak_ratio`（第一名 ÷ 第二名）** —— 陣列區裡同一個模板在好幾個地方
  都拿得到一樣高的分數，而峰值本身完全看不出這件事。實測：隨機紋理峰值 1.00
  / ratio 0.05；20×20 週期性圖案峰值也是 1.00，但 ratio **1.00** —— 兩者的
  峰值一模一樣，而後者的位置是猜的。

**框把對的那一塊排除掉時，錯誤訊息會講出框的存在**（「只找了中間 15%、
184×184 of 400×400」），不會謊稱「這兩張不像」—— 那句話是錯的，而且會讓人往
完全錯的方向查。

明講沒做：用兩份 KLARF 的**座標差**把預期位置算得更準。KLARF 的 y 軸與影像列
方向誰正誰負還沒在真實資料上驗過，猜錯的話框會往反方向移、把對的那一塊排除掉。
先讓 `align_off_*` 把它量出來（中位數的正負號會直接寫在數字上），量過再做 ——
跟 GLAS 那條路一樣。

---

## 像素大小：一格 nm/px ＋ align_to 的尺度（F15-3，2026-08-20，第二十三輪）

使用者：「像素尺寸不同，可以預設一樣，或給 user 輸入」＋「在 load image 那邊
source（各種 source），可以輸入 nm/pixel（也可以不輸入）」。

* **一格 nm/px 長在把那份資料讀進來的那張卡上**（`load_patch` / `load_single` /
  `pair_source`，預設 0 = 不知道，收在進階裡）。規則是一句話不是三句。
* **多一組，不是換掉**：`cd_x_px` 旁邊多一個 `cd_x_nm`（面積是 `area_nm2`，
  乘平方）。使用者原本的提案是換單位，但那會讓同一個特徵名在不同資料上是不同
  單位 —— `score = cd_x > 50` 這一行的意思會隨著「那份資料當初填了沒」改變，
  而 CSV 上看不出來。單位寫在名字上就永遠不必回頭查，舊 recipe 也一個字不用改。
* 2026-07-30 拿掉 `cd_x_nm` 的理由是「nm/px 沒有來源，每一顆都是 0」——
  **這一格正是那個來源**，所以那次的結論沒有被推翻，是被補完了。
* 沒填就一個 `_nm` 都不產出，而且**下拉裡也不列**
  （`RecipeModel.available_features`：量測卡看不到 Load 卡上填了什麼，
  但那張表看得到每一張卡）。
* **nm/px 掛在「流」上不是一個全域數字**（`Context.stream_nm_per_px`）：
  一份 pipeline 可以同時吃兩份資料，而兩台機台的像素大小不一樣。
* **`align_to` 的 `Size ratio`**：預設 0 = 自動（兩條流的 nm/px 相除），
  算出來的值變成 `align_scale` 這個特徵 —— 它影響每一顆的結果，不可以只活在
  某個人的腦子裡。實測同一塊區域、1.5 倍像素差：不處理 NCC 0.03，
  自動算出 0.667 之後 0.93 而且位移完全正確。
  **只有拿去比對的那一份被重採樣**，裁出來的那一塊原封不動（重採樣會動到灰階，
  而下游量的正是灰階），所以 `out` 帶的是大圖的 nm/px。

---

## 載入大 lot：一個硬上限 ＋ 兩趟不必要的 IFD 走訪（2026-08-20，第二十二輪）

使用者：「幾萬顆 defect 的 klarf+tif 會超級無敵久或直接不載入」。
先寫 `tools/load_probe.py`（公司機、輸出遮蔽可貼），拿真實資料量出來：

```
15481 顆 · 73 欄 · 30962 頁 · 592 MB（網路碟）
klarf_core.load             2.3 s
tiff_index.n_pages        106.1 s   ← 這裡
load_dataset（整段）         4.8 s
--copy 之後：n_pages（本機那份）0.25 s
```

**同一個檔複製到本機只要 0.25 秒** —— 所以慢的不是演算法，是**來回次數**：
30962 頁 × 2 次小 read，每一次都是一趟網路來回。

### 三件事

1. **頁數的硬上限（這是「直接不載入」）** —— IFD 走訪在 10 萬頁報
   `IFD chain loops — corrupt TIFF`，而 5 萬顆 ×2 張剛好落在那條線上。
   `load_dataset` 接住那個例外之後把 kind 退成 `rsem`、每一顆 0 張圖 ——
   載得進來、有 defect、就是沒有影像，而唯一的線索是「你的 TIFF 壞了」（它沒壞）。
   上限提到 `MAX_PAGES = 100 萬`，而且「太多頁」與「繞回自己」是兩句不同的話。

2. **不要為了「幾 bit」走完整份檔案** —— `bit_depths` 把每一頁的每一個 tag 都
   讀出來（4 萬頁 1.0 秒，而整個 `load_dataset` 才 1.56 秒）。它只是**提前
   警告**，守門在每一顆的 `require_8bit`，所以只看前 8 頁。

3. **用到第幾頁才走到第幾頁**（`tiff_index._PageIndex`）—— 這一刀最大。
   以前有**兩趟**全鏈走訪：`load_dataset` 的 `n_pages`，以及開 handle 時的
   `len(tf.pages)`（那是為了修「讀過像素之後解析下一頁會從錯的位置開始」）。
   現在：
   * 每次讀都**自己 seek 到那一頁的 IFD**（位置記在表裡）→ 位置的連續性不再
     影響任何東西 → 不需要 `len(tf.pages)`；
   * `load_dataset` **根本不問頁數**：`defect_image_map` 拿頁數只做兩件事，
     決定 0-based/1-based（**給不給頁數的結論一模一樣**）與「ids 裝不裝得下」
     （改由 `read_page` 在真的讀到那一頁時回答，而且更明確）；
   * 走一個 IFD 從**兩次來回變一次**（先讀 2 KB，多數 IFD 一次就讀完）。

   合成 lot（2 萬顆 / 4 萬頁、冷快取）實測：開檔 0.35 s、看第 1 顆 0.02 s、
   下一顆 0.00 s、跳到第 1 萬顆 0.70 s（走 2 萬個 IFD）、跳完之後又是 0.00 s。

### 代價講清楚

**跳到很後面的那一顆，第一次仍然要往前走過去**（那是 lazy 的本質）。但它是
增量的：走過就記著，逐顆瀏覽等於逐頁往前，而**跑整批本來就要把每一頁的像素
都讀過一遍** —— 那才是 592 MB 的來源，走訪跟它混在一起攤掉了。

---

## 配對卡拿真實資料用了一次（F15-2，2026-08-19，第二十一輪）

使用者回報六件事，這一輪做**前兩件**（其餘排進 `docs/history/plans/F15-pair-sources.md`
§12）：「用 Pair 開 EBI raw data 應用程式會無法回應一陣子」與「卡片太不方便，
要自己填（希望可以自動帶出來用選的）」。

### 第二份也走背景執行緒

同一件事有兩種做法，而慢的那一種是使用者會遇到的那一種：main 早就在背景載了
（`dataset_worker` + 進度條），第二份走的卻是 `run_sync` —— 直接卡住 UI 執行緒。
現在第二份有**自己的** `pair_worker`（跟 main 是兩件可以同時發生的事），
`attach_pair_source(..., sync=True)` 留給測試與 headless。

### 只複製 `carry` 要的那幾欄

`fill_fields` 本來每一顆的每一欄都複製。raw data 幾十萬顆 ×24 欄字串是幾百 MB，
而其中 22 欄從來沒有人 `carry` —— 而且那幾欄還要 pickle 進每一個 worker。
要哪幾欄由 `steps/pair_source.columns_for_source(nodes, sid)` 回答（指著那個代號
的每一張卡的 `carry` **聯集**），`carry` 改了就 `refill_fields`。

⚠ 這裡冒出一個新的說謊點：卡片跑起來時手上只有複製過去的那幾欄，所以它那句
「Its columns are: …」會把「你要的那幾欄」講成「那一份有的那幾欄」。拆成兩句，
各自只講自己答得出來的 —— **掛上來的當下**（doc 還在手上）講「這一份有的是
A, B, C」，卡片跑起來只講「帶過來的是哪幾欄」。CLI 也改成 attach 完就擋，
整批跑完才發現「那一欄根本不存在」是最貴的一種發現方式。

### 三格用選的：`ParamSpec.choices_from`

`Source name` / `Which image` / `Carry these columns` 的答案程式都知道，只是
**執行期才知道**（掛了哪幾份、那一份有哪幾張圖、有哪些欄）。所以不是
`ParamSpec.choices`（卡片列得出來的表），而是新的 `choices_from` ——
填一個 `RUNTIME_CHOICES` 的鍵，UI 去問 Studio。這是
`stream_choices` / `region_choices` 的第三次：**程式知道的名字不該讓使用者用打的。**

* **不是 `type="choice"`**：`choice` 會擋掉不在清單裡的值，而 recipe 是在資料
  掛上來**之前**讀進來的 —— 每一份存了 source 名字的 recipe 都會在開檔那一刻
  爆掉。型別維持 `str` / `multi_choice`，`choices_from` 只影響「打字還是用選的」。
* **換清單不重建表單**（`set_dynamic_choices`）：重建會搶走游標，而那件事最常
  發生的時機正是「使用者剛在 Source name 那一格打字」。有游標的那一格整格跳過
  —— 只保住文字不夠，`clear()+addItems()` 會把游標推到字尾。
* **空清單要講話**：「還沒掛第二份」是正常狀態，畫出來卻是一塊空白。
* **指著沒掛上來的代號 → 兩格都空的**，不拿「唯一掛著的那一份」頂替：
  那一格印的欄位就會是另一份的，而畫面說謊比空白糟。

驗收：`tests/test_pair_source.py`（27）、`tests/test_ui_f15_pair_source.py`（21，
含背景載入真的有轉 event loop、以及「打到一半的字不會被吃掉」）。

---

## 配對分析：兩筆資料逐顆對起來（F15，2026-08-19，第二十輪）

使用者要的場景是 **EBI to API Characterization**：RSEM 的 API 空拍（拍滿、直接
對影像抓 defect）是 ground truth，拿它回疊 EBI 掃過的位置，答的是三個問題不是
兩個 —— 抓到了 / **偵測到但分數太低沒被 sample（藏在 raw data 內）** / 根本沒
偵測到。中間那一列是整件事的重點。

定調的那句話是：**「我只想把它做成一個小功能 card，這張 card 會 load 自己的
source」** —— 主流程什麼 ROI／GLV／measure 都照舊，要做配對分析才放這張卡。

計畫書：[`docs/history/plans/F15-pair-sources.md`](docs/history/plans/F15-pair-sources.md)。
A／B／C 一次做完。

### 兩張卡，不是一張

* **`pair_source`（Input 段）** —— 「這一顆在另一份裡是哪一顆」，把它的圖帶進
  來。配對用 wafer 座標（`position`，容差 `tol_nm`）／`id`／`order`；
  `carry` 把配到那一顆的 KLARF 欄位帶成 feature（`pair_ROUGHBINNUMBER`）——
  **少了它，「偵測到但分數太低」跟「根本沒偵測到」在資料上長得一模一樣**。
* **`align_to`（Compare 段）** —— 圖對圖。EBI 的 patch 小、RSEM 的視野大，
  所以是「小圖在大圖裡找位置」（NCC + 拋物線次像素），裁出來的那一塊給下游量。
  **裁在整數格上不重採樣** —— 重採樣會動到灰階，而下游量的正是灰階。

兩張分開是因為**它們分得開**：只要座標配對＋帶欄位（不比圖）就只放第一張；
兩張圖本來就對齊（同機台重掃）就只放第二張。上一版草案的兩張卡永遠只能成對
出現，那是同一張卡被切成兩半。

### 卡片不自己 `open()`

第二份是 Studio／CLI 載成 `Dataset` 掛在 `Dataset.sources[代號]` 上的
（`core/ingest/pair_source.attach`），卡片只從掛好的那一份裡挑一顆，
**路徑不進 recipe**（同一份 recipe 才跑得動下一批）。理由是快取簽章：卡片偷偷
讀檔的話，換一份第二 source 而簽章看不見 → 回舊影像（鐵則 9，F9 踩過兩次）。
`_dataset_token_for` 多了一段 `+src:`，而**沒掛的時候那一段逐字元不存在** ——
既有的快取目錄與黃金值不受影響。

* Studio：`Open data…` 就在那張卡上（沿用 F14-1），代號沒打就從檔名推一個。
* CLI：`python -m d4t run … --source 代號=第二份.001`（可以重複）。

### 三個「跑得完、有數字、而且是錯的」

1. **`carry` 打錯欄位名安靜地沒事** → 少一欄的 CSV 跟成功的 CSV 一模一樣。
   現在擋下來，訊息裡有打錯的那個、真的有的那幾個、要改哪一格。
2. **循序路徑沒有 pin cv2**（鐵則 9 的洞，F15 讓它現形）→ NCC 的分數在
   `workers=1` 與 `workers=2` 差 1e-7，而 **Studio 的試跑走的就是循序那條**，
   所以「畫面上的數字」跟「批次的數字」不一樣。修法：循序路徑也 pin。
3. **配對卡是 `is_source()`，畫布本來會在它身上印 main 的檔名** ——
   它讀的不是那一份。現在印的是掛在它代號上的第二份。

### 沒做的（明講）

第二份不寫回 KLARF、不進 defect 導覽、不進 Export（它只是圖與座標）；
一張卡一份（要第三份就再放一張卡）；route 仍由 main 的 `kind` 決定；
兩份 KLARF 的座標系對齊先不做 —— 先讓 `match_dist_nm` 把它**量出來**。

驗收：`tests/test_pair_source.py`（23 條，含 `workers=1` 對 `workers=2` 與
「跟 KLIP 的那一支不准漂」）、`tests/test_ui_f15_pair_source.py`（11 條）。

---

## Input 的入口搬進卡片（F14-1，2026-08-19，第十九輪）

使用者：「關於 Input 我想改成統一從卡片內 Input⋯⋯如果按照目前從 UI 上方，
使用者會錯亂而且沒辦法多開」，接著定調：**「工具列拿掉吧（會混淆）」**。

那跟這幾輪一直在講的是同一條規矩：以前檔案在**工具列**上選，而畫布上那張
Load 卡完全不會說它讀的是哪個檔案 —— 同一件事兩個地方，而畫布是說謊的那一個。

### 做了什麼

* 工具列上**拿掉四顆**（KLARF / Stack / Folder / GDS export）。剩 `Open recipe…`
  （它不是資料，是這份 pipeline 本身）。
* 入口長在**讀那份資料的那張卡**上（`ParamForm.set_source_action`）：
  * `load_patch` / `load_single` → `Open data…`，按下去是一張選單，
    **每一列都是 `scope.INPUT_SOURCES` 的一列**（那張表仍然是入口的唯一定義）；
  * `load_sidecar` → `Open GDS export…`（它只有一條路，直接開）。
  * 判準是 **`Step.is_source()`**（沒有影像輸入的卡），不是一張寫死的名單 ——
    下一張入口卡不必記得回來註冊。
* 鈕旁邊那句話講**現在載的是哪一份**（`LOT_SYN.001 · ebi_patch · 12 defects`）。
* **畫布也跟著說得出來**：入口卡的第一項摘要就是那個檔名，否則搬家只搬了一半。

### 入口沒有變少，只是搬家

畫面最大的那一塊（沒有資料時的空白狀態）仍然**一種 source 一列**，而那是第一次
進來的人真的會看的地方。`Ctrl+O` 的 tooltip 跟著搬到那顆鈕上 —— 快捷鍵要在
**還看得到的**那顆鈕上講出來，不然它就只活在原始碼裡。

### 一條不變量長出第三種形狀

「還沒設定完的訊息必須指向一個按得到的東西」以前認兩種：一顆 `…` 結尾的鈕、
或這張卡自己的一格。現在多一種：**另一張卡的名字**（`roi_from_mask` 現在說
「Use “Open GDS export…” on the “Load layout labels” card」）。它一樣要驗 ——
引的必須真的有那張卡，不然「指向一個東西」又退化成「寫一句看起來像樣的話」。

同理，`test_the_card_message_points_at_a_button_that_exists` 現在找的是
**工具列 ∪ 選著那張卡的入口鈕**。

### ⚠ 這一輪沒有動的

**「一份 recipe 一個 dataset」那個前提一個字都沒改。** 多 source 是第二步，
而它要先定配對規則（顆數不同怎麼辦、靠什麼配、route 的 kind 怎麼選、
KLARF 寫回誰、快取簽章）—— 使用者說「第二步我們再討論」。
這一輪只是把入口搬到對的地方，而那天到了，入口已經在了。

新增 `tests/test_ui_f14_input_on_the_card.py`（8 條）。改到六份舊測試，
全部是「那顆鈕搬家了」。

## 多連一（區域那一半）＋ 數字不要網底（2026-08-19，第十八輪之五）

使用者驗收後的兩件事。

### 「區域線仍然只能拉一條」—— 我上一輪把限制當成結論了

他要的是**多連一**：ROI A 與 ROI B 一起接到同一張 Gray-level stats。那件事對
區域跟對影像流一樣成立（F10-3 對 `source` 做過同一件事），所以規則直接沿用，
一字不改：

| 型別 | 第二條線 | 誰 |
|---|---|---|
| `region_keys` | **累加** | `glv_stats` / `roi_snr` / `cd_measure` 的 `roi` |
| `region_key` | **取代** | `roi_compare` 的 target / reference（角色） |

命名照抄 `stream_prefix`：**只接一個時特徵名跟以前逐字相同**（分數表達式不必
改寫、黃金值不動），兩個以上才自動帶區域名。流 × 區域相乘：
`test_hot_glv_mean` / `ref_cold_glv_mean`。

迴圈住在 `MultiSourceStep.run`（`REGION` 類別屬性說哪一格是區域），子類的
`measure` **完全不必知道接了幾個**。順帶關掉 `_autofill_output_prefix` 在多區域
時的自動命名 —— 不然會變成 `epi_mg_epi_glv_mean`。

**上一輪的測試改掉了**：`test_a_second_line_replaces_the_first...` 換成
`test_a_measure_card_takes_more_than_one_region`，而「取代」那一半移到
`roi_compare` 的角色埠上（那裡它才是對的）。

### 數字不要網底

使用者：「不要有網底色，單純數字的顏色即可」。`count_badge_colors` →
`count_color`，字色直接算在 rail 的底色上（淺色推 1–2 格到 4.5–4.9，
深色原樣 5.9–7.9）。

## 畫布收尾（F13-⑤，2026-08-19，第十八輪之四）

五點裡的最後一個。四件事，全部量過：

1. **卡片放大一號**：190×56 → **204×64**。標題可用寬度只有 `NODE_W` 減掉左邊
   圖示磚（40）與右邊界（8），190 只剩 142px —— `Compare two streams` 剛好卡
   在邊上。**只加 14 不是 20**：卡片變寬會讓 `fit` 縮得更小，而那正是 F13-1
   剛買回來的東西（實測 210 會掉到 70%，204 是 71%）。
2. **欄距 96 → 116**：埠標籤畫在卡片**外面**，左右各 52px —— 96 塞不下兩個 52，
   於是上游的輸出名與下游的輸入名疊在同一塊空白上（實測 `layout_label` 疊到
   `single`）。
3. **連線帶來源的階段色**（混一半灰）。全灰的時候，一張擠了十條線的畫布上
   「這條是從哪裡出來的」只能用眼睛沿著線走。**調淡一半**是重點：線平常畫在
   卡片**底下**，它是背景不是主角。
4. **深色的點陣底 1.44 → 1.9**：對齊的參考看不見就等於沒有。

順手修掉一個真的 bug：**靠右對齊的埠標籤是從左邊硬切的**。
`Borrow range from` 因此畫成 `nge from` —— 讀起來像另一個欄位的名字，而畫面上
沒有任何東西說它被切過。`_draw_elided` 現在收 `align`，兩側都走它。

一條舊測試改了算式：`WRAP * (NODE_W + COL_GAP)` 多算了一個欄距（欄距是欄與欄
**之間**的），F13-⑤ 放大卡片之後它紅了，但畫面其實塞得下。順便把那條不變量
改成對**每一種寬度**都驗（F13-1 之後換行點是跟著寬度走的）。

## 特徵表分組（F13-①，2026-08-19，第十八輪之三）

使用者：「目前 feature 的顯示太陽春了不易閱讀，試著將他分類」。

一條平的 name/value 清單裡，`n_channels` 跟 `snr_max` 長得一模一樣 —— 而一個是
「這張卡讀了幾頁」、一個是會決定 bin 的量測值。

### 關鍵：**分組不是 UI 發明的規則**

兩份資料早就在了，只是 UI 沒用：

* `ctx.meta["feature_owner"]` —— 每個特徵是**哪張卡**寫的（engine 在救援撞名
  那一段順手記的）；
* `Step.diagnostic_features()` —— 哪幾個是「這張卡自己做了什麼」。

自己發明一份分類的話它會跟引擎漂，而漂掉的症狀是「這個數字被歸到錯的卡底下」，
畫面上完全看不出來。

```
▾ Load images  ·  1        ← 組名是卡片的 label、底色是它的階段色
    n_channels        2
▾ Z-map  ·  1
    snr_max       0.674
▾ CD measure  ·  3
    cd_x_px / cd_y_px / area_px
▾ Gray-level stats  ·  3
    glv_max / glv_q99 / glv_mean
▸ Diagnostics  ·  4        ← 預設收起來
    score        30.0      ← 永遠在最底、粗體，而且**收不掉**
```

三個踩到的細節：

1. **救回來的那一份也是診斷**：兩張 Enhance 卡都寫 `clip_frac`，engine 把先寫
   的留成 `<節點名>_clip_frac`。不算進來的話它會以「量測值」的身分排在最上面。
2. **同名的卡才帶 node id**（畫布副標用的是同一條規則）——每一組都掛 id
   是在每一份正常的 recipe 上加噪音。
3. **沒有人認領的特徵歸 `Other`**，不是丟掉：漏掉一個 = 那個數字從畫面上消失，
   而使用者不會知道它存在過。

`feature_names()` 現在會跳過標題列（它有一堆呼叫端），而**不給 `sections`
就是舊的平清單** —— CLI、報表、既有測試都還走那條路。

新增 `tests/test_ui_f13_features.py`（9 條）。

## 對比、層級、地標（F13-2/3/4，2026-08-19，第十八輪之二）

使用者一次提了五點，我照「調現有的東西 → 需要新資料結構」排序：③ → ② → ④ →
① → ⑤。這一段是前三個。

### ③ 卡片數的顏色 —— 病根是**用錯 token**

`QLabel#stageCount` 吃 `$text_disabled`，而那個 token 的意思是「這東西停用
了」；那個數字沒有停用，它是次要資訊。量出來（WCAG AA 小字要 4.5）：

| | 以前 | 現在 |
|---|---|---|
| 深色 | 2.90 ❌ | 4.58–5.22 ✅ |
| 淺色 | **1.89** ❌❌ | 4.57–4.79 ✅ |

使用者說的是深色不明顯，而**淺色其實更糟**。改成階段色的小藥丸（淡底 + 同
色系深字），兩個顏色由 `theme.count_badge_colors()` **算**出來 ——
`readable_on()` 把字往離底色更遠的方向推到過關為止，方向由底色決定，
所以色相留得住。淺色那六個要推 4–6 格，深色原樣就過。

新增 `theme.relative_luminance / contrast_ratio / mix_hex / readable_on`
（純函式、免 Qt），而測試**逐個階段 × 逐個主題**驗 —— 下一次調色盤的人
不必記得回來算。

### ② 工具列的三級

以前六顆等權重的框，只有 Run trial 是藍的。現在：

```
OPEN [KLARF…][Stack…][Folder…][Recipe…] │ [Open GDS export…] │ [Export…] │ ↶ ↷
     └─ 名詞，動詞提到前面當小標題 ─┘                            └─ 純圖示、無框
```

* `InputSource` / `Attachment` 多一個 `short` 欄位 —— **同一張表兩種呈現**：
  空白狀態用完整的一句（那是第一次找路的地方），工具列只要名詞。
* **`Open GDS export…` 不縮寫**：它的名字被三張卡的訊息逐字引用，而
  `test_ui_f7_9_feedback` 要求引號裡的字跟畫面上的鈕一字不差。
* 第三級（`variant="ghost"`）只給**純圖示**的那三顆。theme.py 那條「沒框的字
  讀起來是選單列」沒有被推翻 —— 它們沒有字。

### ④ 每一欄說得出自己是什麼

`LIBRARY` / `PIPELINE` / `PREVIEW` 三個很輕的地標（10px、大寫、字距）。
畫布那一個是**浮在上面的子 widget**（跟 zoom bar 同一種做法）：包一層容器會讓
`canvas_column.widget(0)` 不再是畫布，而好幾條測試與彈出視窗靠著它。

新增 `tests/test_ui_f13_chrome.py`（9 條）。改到兩處舊測試（stack 那顆鈕的字、
QSS 註解不能有中文 —— `test_ui_english_only` 掃得到 QSS 字串裡）。

## 版面：把空白還給畫布（F13-1，2026-08-19，第十八輪）

使用者：「我接著想做 UI/UX 美觀，你有什麼建議嗎?」→ 我把 Studio 跑起來截圖、
量了版面，第一件事不是配色是**空間分配**。1600×1000 上量到的：

```
卡片庫 256 │ 中欄 551 │ 預覽 791      中欄再上下切：畫布 368 / 設定 551
              ↑ 主要工作區 34%          而設定區沒選卡片時只裝一行灰字
```

結果畫布被壓到 **50% 縮放**，而卡片的副標（「這張卡吃什麼吐什麼」）要到
**70%** 才讀得回來（`MIN_FIT_SCALE` 的說明早就量過這個數字）。
**三個都是空的地方在擠一個不夠用的地方。**

兩個修法（都沒有動預覽欄的寬度 —— 「影像大一點」是使用者自己要求的）：

1. **設定區的高度跟著「有沒有東西可以設定」走**（`_sync_params_pane`）。
   沒選卡片 → 收起來，畫布拿整欄；選了 → 攤開，而且**設定仍然拿大頭**
   （D 案的比例那一半沒有變）。只在狀態真的翻面時動 —— 使用者自己拖過的
   分隔線不可以被下一次 `_refresh_pipeline` 洗掉（那件事每改一個參數發生一次）。
2. **換行點跟著畫布真的有多寬走**（`canvas.wrap_for_width`）。`WRAP = 4` 是
   寫死的，等於**要求畫布有 1050px 寬**。現在窄就早一點換行、排得高一點。
   兩個邊界：一張卡都放不下的寬度（未 show 的 widget 實測 89px）退回舊行為；
   `fit_later` 那一刻用真寬度重排一次，而使用者自己拖好的佈局不重排。

實測：50% → **83%**，八張卡全部讀得到標題、副標與埠名。

順帶：**欄寬與中欄比例記進 QSettings**（跟主題、導覽旗標同一組），
而 `_load_sizes` 在 `_running_under_pytest()` 時一律回 `None` ——
還原了的話，某一次手動跑 GUI 拖過的分隔線會漏進下一次的測試。

新增 `tests/test_ui_f13_layout.py`（8 條）。改到三處舊測試，都是同一條規則的
另一半：`params_open` 的預設（兩處）、跨列的線改用 `pipeline.wrap()`。

## 區域也有線了（F12，2026-08-19，第十七輪）

### ⏩ 交接：下一個 session 從這裡開始

**畫布上現在有兩種線**：影像是實線 + 圓埠，**具名區域是虛線 + 菱形埠**
（Region 段的綠色）。量測卡的 `roi` 不再是一個打得進去的文字框 —— 跟影像來源
一樣，**來源只在畫布上決定**（F9-6 的規則套到區域上）。

引擎一行都沒動、recipe JSON 格式一個欄位都沒有變、黃金值不動。

### 這一輪的起點是使用者的一句話

他在讀「GDS 的某個 layer 要怎麼量 GLV」時問：「線沒連上不就代表資料流沒往下
走?」我解釋完「跑起來是對的」（順序由 route 相鄰對保證，`execution_order` 的邊
是 **route 相鄰對 ∪ 顯式 edges**），他說：**「但我還是這樣怪怪的」**。

那個怪是對的，而且它指的不是 bug：畫布上有**兩套規則**（影像拉線、區域打字），
而它會說謊 —— 拿掉上游那張 Region 卡，量測卡不報錯，它**安靜地改量整張圖**。

### 關鍵決定：區域線**推導**，不存

`roi="epi"` 那個參數就是唯一的儲存，線是它的呈現（`RecipeModel.region_lines()`）。
理由：區域名在 `ctx.rois` 裡全域唯一（`set_roi` 明文同名覆寫），所以「誰定義了
epi」推得出來而且跟引擎逐字相同；影像流沒有這個性質（同一條 `ref` 分岔成兩支），
那才是 F9 把身分換成 `(節點, 埠)` 的原因。存第二份的話兩份會漂 —— F9 那六個
「跑得完、有數字、而且是錯的」有一半是這個形狀。

**副作用是好的**：舊 recipe 打開就有線，不必遷移。

### 動到的東西

* `core/pipeline/step.py` —— `IMAGE_TYPES` / `REGION_TYPES`；`is_image_input()`
  / `is_region_input()`；`input_specs()` 收斂成「影像輸入」，新增
  `region_input_specs()`。區域參數**必須**宣告 `direction="in"`（註冊時擋）。
* `steps/{glv_stats,roi_snr,cd}.py` —— `roi`：`str` → `region_key`。
* `steps/{roi_compare,roi_mask}.py` —— 既有的區域參數補 `direction="in"`。
* `ui/widgets.py` —— 區域那一格改成唯讀的接線顯示（原本是下拉／勾選）。
* `ui/viewmodel.py` —— `region_producer()` / `region_lines()`。
* `ui/studio.py` —— 區域埠、連線／剪線／刪卡走區域那條路。
* `ui/canvas.py` —— 菱形埠、虛線、**埠多的卡片會長高**（`_NodeItem.height()`；
  疊在一起的埠是點不到的）。

### 順手拿掉的一個「幫忙」

`_autofill_regions`（F8-UI：加一張 `roi_mask` 就把上游每個區域名填進去）
**刪掉了**。區域變成線之後，那等於自動幫他畫了六條他沒有拉過的線 —— 正是鐵則
10 擋的那件事。他不再需要抄名字：埠就在旁邊。

（`_autofill_gds_layers` 留著 —— 那是一張**對照表**（層號 → 名字）不是接線。）

### 測試

新增 `tests/test_ui_region_edges.py`（14 條）。其中兩條是 registry-wide 的
不變量，**下一張卡的作者不必記得回來補**：

* 每一個 `region_key` / `region_keys` 都要 `direction="in"`；
* **沒有任何一格用 `str` 指區域** —— 判準是把一個記號塞進那一格，
  看它會不會出現在 `resolve_regions_in`（問卡片自己，不是猜名字）。

### 第二輪（同日驗收之後）

* **同進同出**：接進來的區域，卡片後面也接得出去（`region_outputs()`）——
  跟影像的 `writes`（埠）／`produces`（副標）同一個形狀，所以副標仍然只印
  「真的產出什麼」，量測卡不會在畫布上讀起來像 Region 卡。
* **一個區域埠一條線**：`region_key` 那一格只放得下一個名字，所以第二條線就是
  取代（結構性的，不是靠檢查）。`region_keys` 是清單 → 累加，同 `image_keys`。

改到的舊測試三處，都是「同一件事換了做法」：`test_ui_f7_11_roi`（下拉 → 唯讀）、
`test_ui_f8_ui_polish`（自動填 → 拉一條線）、`test_ui_f10_canvas_reality`
（`direction` 的不變量擴到區域型別）。

## 改名 ADEPT → d4t，並且有圖示了（2026-08-19，第十六輪）

### ⏩ 交接：下一個 session 從這裡開始

**這個專案現在叫 `d4t`（唸 D-four-T），全稱一律跟著寫：`d4t — defect`。**
`python -m d4t gui` / `python -m d4t run …`，套件目錄是 `d4t/`。

引擎一行都沒動 —— 這一輪只有名字與品牌資產。**接下來照
[`docs/ROADMAP.md`](docs/ROADMAP.md) 走**，Region 段剩的尾巴仍然是「模板過期健檢」。

**三件跟名字有關、之後會踩到的事：**

1. **GitHub 上的 repo 也改名了**（`hxlub0905-cmyk/d4t`，2026-08-19 同日）。
   `tools/get_code.py`、`get_code.ps1`、`check_files.py` 裡的 slug 已經跟上 ——
   那是沒有 git 的那台機器**唯一**拿得到程式碼的網址，所以改 repo 名稱的時候
   這三個字串一定要一起改。GitHub 雖然會從舊名轉址，但只要有人新建一個叫
   `ADEPT` 的 repo，轉址就會失效，不要讓搬運通道靠轉址活著。
2. **快取／設定目錄變成 `~/.d4t`。** 舊的 `~/.adept` 不會自動搬，裡面只有主題
   偏好與影像快取，重建成本是零，所以沒寫遷移。使用者第一次開會回到預設主題。
3. **環境變數大寫慣例保留**：`D4T_GOLDEN`、`D4T_DOCTOR_JSON`。
   如果你手邊的筆記還寫著 `ADEPT_GOLDEN`，那是舊的。

### 為什麼改名

舊名字的 **P = Pipeline 已經跟現況不符**。F9 之後的核心不變量是「資料從哪來
由**線**決定」、影像流的身分是 `(節點, 埠)`、一個輸入埠只能有一條線、
`validate` 會報 `ambiguous-input` —— 這是 DAG 與畫布，不是一條流水線。
名字裡留著 Pipeline，每一個新接手的人都要先被誤導一次再自己修正。

`d4t` 是 *defect* 的 **numeronym**（頭字母 + 中間字數 + 尾字母），跟
i18n / k8s / n8n 同一套慣例 —— 使用者要的就是「像 n8n 那樣，英文加數字」。
挑選過程與被排除的候選（WIRE / GRAFT / DEFT / i8n…）記在
[`docs/HANDOVER.md`](docs/HANDOVER.md) §2「名稱由來」，那一段現在記錄的是
**兩次**改名（FlexADC → ADEPT → d4t）而不是一次。

### 這一輪做了什麼

**圖示（`d4t/ui/assets/d4t.svg`）：那個 4 是用接線畫的。** 兩個開口是進來的
影像流、橫豎交會的那一點是算法、往下走出去的是判定 —— 一顆圖示說完三段式。
它同時回答「為什麼叫 d4t」：被數字代掉的中間那一段，在這個工具裡本來就是
**使用者自己拉出來的**。

**四顆點的顏色不是用眼睛調的，是逐字抄 `theme.PALETTES["dark"]` 的
`seg_image` / `seg_algo` / `seg_adc`**，而 `tests/test_ui_branding.py` 斷言
渲染出來的像素跟那三個值**完全相等**。改了分段色卻忘了改圖示會在這裡紅 ——
畫布跟圖示講不同語言，對不寫 code 的使用者就是兩個看起來無關的東西。

那支測試還鎖兩件事：SVG 是合法的、而且 **Qt 真的畫得出來**。第二件是重點 ——
我們直接餵向量檔給 `QIcon`（PySide6 帶 Qt 的 SVG image plugin，一份檔案在任何
DPI 上都銳利），萬一哪天那個 plugin 沒被打包進去，會在測試裡紅，而不是等
使用者在廠內開起來看到一個空白圖示。

**`d4t/ui/branding.py` 是品牌資產的唯一出處**，找不到檔案時回**空的** `QIcon`
而不是拋例外：受限機器是用「複製檔案」部署的，少一個檔案是真的會發生的事，
而少一顆圖示不該讓 Studio 開不起來。圖示設在 `QApplication` 上而不是每個視窗
上，之後開新視窗不必記得補一行。`pyproject.toml` 補了 package-data ——
不加那一段，pip 裝出來的 `d4t.ui` 底下沒有 `assets/`，Studio 會**安靜地**開一個
沒有圖示的視窗。

**改名本身是機械的，但有三個地方刻意沒有機械替換**（上面「交接」的第 1 點是
其中之一）：`docs/HANDOVER.md` 的名稱由來改寫成記錄兩次改名，而
`docs/history/2026-07.md` **保留當時的用字**只加一則後記 —— 歷史記的是當時的
事實，把「當初為什麼叫 ADEPT」改寫掉，那個決定的理由就查不到了。

核心 1425 passed / 42 skipped；UI 41 檔逐檔全綠（663 passed）；
`python -m d4t --help` / `steps`、`tools/doctor.py` 端到端（score=33.000）都正常。

---
