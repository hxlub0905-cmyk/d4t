# F122 — ADC 與 Output：先修安靜做錯的，再收成一種說法

狀態：**進行中（2026-09-29）—— 期 1（ADC）、期 2（Output）安靜做錯的都修完；期 3／4 照建議做；期 5（畫布上 Output 的位置）等使用者點頭。**
方向使用者同意（「先修會安靜做錯的，接著按照你的建議修」）。

F121（入口簡單化）的續集：使用者說 Input、ADC、Output「這三張比較特別」，F121 做了
Input，這一份做另外兩張。

---

## 1. 使用者定調（2026-09-29，原話）

* 「接下來做 ADC 跟 output 兩張卡（先不要動），先列出想法」
* 「先修會安靜做錯的，接著按照你的建議修」
* 「Output 跟 Input 的地位你覺得是否要一樣（都是同樣一張 CARD），但在畫布上呈現
  好像不大一樣？」—— 回答見 §5 期 5。

五個問題的答案（使用者說照建議）：

| 問題 | 答案 |
|---|---|
| 舊的「一條公式＋門檻」要整條退役嗎 | 要；舊檔案自動轉成樹，黃金值不動 |
| ADC 名字統一成哪一個 | 階段叫 ADC、卡叫 Decision；「Score / Bin」「Verdict」拿掉 |
| Write KLARF 配沒有 KLARF 的資料 | 開資料時卡上講；按寫時**跳過並講**，其他輸出照寫 |
| 「Write to」空白 | 預設寫到資料旁邊，不再是 error |
| Write comparison 併進 Write report | 先不併（`output.py` 寫著「先不合」，有測試守） |

---

## 2. 現況（量出來的，2026-09-29）

* **ADC 不是一張卡**：recipe 最上層的 `decide`（working numbers ＋ 判定樹 ＋ score），
  畫布上一個紫色虛線框「DECISION」，整份 recipe 0 或 1 個、所有 route 共用。
  舊的 `score`（公式＋門檻＋兩個 bin）還活在引擎、CLI rescore、viewmodel、studio。
* **Output 是四張 lot 級的卡**（Write report／KLARF／comparison／charts），沒有埠、
  整批跑完各跑一次；Studio 按「Write outputs」才寫（鐵則 11）。

---

## 3. 期 1 — ADC 安靜做錯的 ✅ 2026-09-29

| # | 做錯的樣子 | 修法 | 守門 |
|---|---|---|---|
| 1 | 還沒加判定的新 recipe：畫面說「every one comes out unclassified」，引擎給每一顆 score 0、bin 1（Studio 塞的佔位值 `"0"`）| **沒有判定＝沒有 bin**：`decide` 與 `score.expr` 都空 → `(None, None)`；Studio 新 recipe 不再塞 `"0"`，打開帶常數分數的舊檔案照畫面改成空的（UI 層遷移，同 `_adopt_threshold_as_a_tree`）| `test_no_decision_means_no_bin.py` |
| 2 | 樹上問 `score`：整批跑答「否」（分數在判定之後才算），Re-run 用上一次的分數答得出來 —— 同一份 recipe 兩種 bin | 分數改在 let 之後、判定之前算；重判前先拿掉上一次的 `score` / `decide_unanswered`；lint 只在真的有分數表達式時讓樹問它 | `test_decide_asks_the_score.py` |
| 3 | 設了「問不出來 → bin N」：引擎放 bin N，判定帶、HTML 報表、box plot 重走樹算在「否」那片葉子 | `decide_tree.diverted` ＋ `verdict_rows` 多一列（`UNANSWERED_KEY`）；畫布托盤仍是「走到這裡的」，旁邊寫「3 → bin 99」 | `test_decide_unanswered_bin.py` |
| 4 | 手寫的規則 recipe 在 Studio 點一下轉成樹，每條規則的 outcome 消失 | `rules_to_tree` 帶 outcome | `test_decide_outcome.py` |
| 5 | 面板說分數「寫進 KLARF DSIZE」「空＝0」；Write KLARF 對沒有分數的判定照插 ADCSCORE 全填 0.0 | 用字改對；**沒有分數就沒有 ADCSCORE 欄**（講一句 note）| `test_export_klarf.py` |
| 6 | 刪一張量測卡，判定還在問它的數字 —— 改參數會講，刪卡不會 | `RecipeModel.removal_fallout`，`remove_card` 講 | `test_rename_fallout.py` |
| 7 | 樹上的題目缺一個數字：warning 說「every defect will fail」（實際是安靜地全部答「否」）；KLARF 欄沒講要去 Input 卡勾；分流時 `route_taken` 被說成沒人算 | 題目與 let 分兩種用字；知道資料時講「勾 Carry these columns」或「這份資料沒有 KLARF」；`route_taken` 進看得到的名字 | `test_decide_asks_the_score.py` |
| 8 | CLI `rescore` 把每一列當 `ok=True` 倒回去：量到一半出錯的顆拿殘缺的 features 得到正常的 bin | 只救判定本身失敗的（`[score] …`），卡片出錯的照舊失敗 | `test_rescore_decide.py` |

順手：`add_rule` 用光 bin 會漏 `StopIteration`（同 `_fresh_bin` 的修法）；三處指向
不存在的函式或過期行號的註解；歡迎頁「splits them into bins by a threshold」。

查過、**不是**問題的：舊的 feature 改名遷移（`_RENAMED_FEATURES`、撞名前綴）只改
`score.expr` 不改 `decide` —— 兩者都比判定段早出生，存得出判定段的檔案一開始就是新名字。

---

## 4. 期 2 — Output 安靜做錯／擋錯的 ✅ 2026-09-29

| # | 做錯的樣子 | 修法 | 守門 |
|---|---|---|---|
| 1 | 新加一張 Output 卡、「Write to」空著 → 一條 error，**連試跑都擋**（試跑根本不寫）| 空著＝資料旁邊的預設：`d4t_report` / `d4t_comparison` / `d4t_charts`（每張卡一個名字）；Write KLARF 是原檔旁邊的 `_adc`（top N `_top`），in place 是原檔本人 | `test_output_defaults_and_collisions.py` |
| 2 | Write KLARF 配沒有 KLARF 的資料：開跑前不講、儀表給「N 顆會改」的估計、按寫才失敗（CLI 回 1、Studio 跳「Some outputs were not written」；訊息還提到已刪的 TIFF stack）| 開資料時卡上一條 warning（`klarf-out-no-klarf`，`Step.data_issues`）；寫的時候**跳過並講**，其他輸出照寫；儀表講「skipped」；in place 的確認對話框不跳 | 同上 ＋ `test_batch_steps.py` |
| 3 | 改了量測卡或判定、沒重跑就按寫：CSV / KLARF 是上一份 recipe 的數字與 bin，報表的圖卻是現在這份重跑的 | `batch.decision_signature` ＋ 量測簽章，Write outputs 對不上就拒寫並講（判定改了：「先按 Re-run」）；底稿搬進 `RunController.snapshot` | `test_ui_write_only_on_run_all.py` |
| 4 | Studio 寫的時候沒帶快取（CLI 有）—— 每張圖整顆重跑 | `OutputWorker` 帶 `DEFAULT_CACHE_DIR` | — |
| 5 | 試跑 N 顆也寫得出去，只有 Write report 標「N of M」 | 寫完的那句話講「These are N of the M defects (a trial run)」 | `test_ui_write_only_on_run_all.py` |
| 6 | 兩張卡指到同一個地方、寫同名的檔 → 安靜互蓋 | lint `output-collision`（error）—— 比**檔名**，出貨的均勻度 recipe 兩張卡共用資料夾但不撞 | `test_output_defaults_and_collisions.py` |
| 7 | CLI 跑 0 顆 → 照樣寫，相對路徑落在 cwd（建資料夾的是 Write report，不是 Write charts）| 0 顆就停（回 2），上面已經講了為什麼是 0 顆 | 同上 |
| 8 | `Write comparison` 的左右兩張圖是自由文字，打錯了那一格安靜地空著 | `Step.optional_streams_in` ＋ lint `stale-stream-ref`（warning）—— 通用的鉤子，不按卡片名字分支 | 同上 |

順手：`batch.run_batch_steps`、`output.py` 模組說明、`step.py` 三處過期的字（「Export
精靈」、「三張卡」、「五張」）；`recipes/README.md` 那一格「相對於你啟動程式的位置」。

## 5. 期 3／4／5 — 方向

* **期 3（ADC）**：舊門檻路整條退役（引擎、rescore、viewmodel、studio 的門檻線；
  舊檔案由遷移轉成樹）；一個名字；判定看資料（問不出來的題目在樹上變紅）；
  「好消息」只用 outcome 一個判準（準確率現在看 `bin ≠ 0`）。
* **期 4（Output）**：「Write to」預設在資料旁邊；Write KLARF 在沒有 KLARF 的資料上
  跳過並講；CLI 的 `export` 也照卡片寫。
* **期 5（畫布，等使用者點頭）**：Input 是起點、Output 是終點，左右對稱 ——
  Output 卡一律排在判定右邊那一欄；判定右緣一個固定的「results →」（字，不是線，
  同判定框左邊的「numbers →」）；副標從「(not connected)」改成講它寫什麼到哪；
  ADC 從虛線框改成一張普通的卡（點開看樹）。**不給 Output 埠**：那條線永遠只有
  一個地方可以接、一定要接（F49 量過：不用）。

## 6. 這一份不做的

* Write comparison 併進 Write report（使用者：先不併）。
* 判定與 Output 變成真的 DAG 節點（F49 量過，結論不變）。
