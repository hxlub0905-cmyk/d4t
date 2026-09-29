# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| **2026-09-09 起** | 這個檔案（下面）—— **09-09 四輪**（判定樹上找得到 working numbers、「插入數字 ▾」一張卡一組帶說明、**跑與寫拆開＋Re-run**（鐵則 11）、Results 單擊帶主畫面、卡片寫 img/s、縮圖與表格同一份排序／篩選、體檢與十四件待辦）、**09-17**（`.I01` 副檔名不同的 patch TIFF、F102 疊模板前先框一塊、F103 標一格量週期、F104 二維自相關找峰、F105 交錯晶格上的小數週期、F107 文件稽核與七道新守門）、**09-18～09-19**（F110 第五顆 Open 鈕、F114 拿掉 stack、**F116 拆 `studio.py` 六步**、F117 UI 走查開跑）、**09-19～09-20**（**F117 走完 58 條裡的 53**，十九群；其中 F118 使用者面的字、F119 哪一個 bin 是好消息各自獨立成一份） |
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

## F122 期 3：ADC 的方向（2026-09-29）

使用者：「繼續期3」。表在計畫書 §5。

* **舊門檻那條路退役**。沒有做成「讀檔時遷移成樹」—— 那會讓幾十支用舊格式
  當填充的測試的來回比對全部改寫，而**要退役的是算法不是格式**：磁碟上那個
  `score` 區塊永遠要讀得進來。所以做成「引擎在判定那一刻換成一模一樣的一題樹」
  （`recipe_schema.legacy_decision`：`score >= 門檻`；分數在判定之前算，期 1
  那一刀正好讓這一題問得到它）。CLI rescore 的第三份門檻比法、Studio 開檔的轉換
  （以前是 `use_decide` 出來的 `expr >= thr` 規則，跟引擎不同形狀）、宣告層都叫
  同一支。
* **黃金值重凍了一次，而且要講清楚**：分數、bin、每一個量測數字逐項相同；每一顆
  多一欄 `decide_unanswered = 0`（兩份 fixture recipe 是舊格式，現在走判定樹，而
  判定樹一定寫那一欄）。當初答使用者的是「黃金值不動」—— 數字沒動，欄位多一格。
* Studio 分數直方圖上的門檻線整族拿掉（`studio.py` 4,293 → 4,236、方法 197 → 192、
  `self.*` 266 → 261）。它在期 1 之後只剩「還沒有判定」的 recipe 走得到，而那時候
  拖一條線什麼都不決定。
* 一個名字：「Score / Bin」→「Decision」、「Verdict」→「Class」、名詞表收成四個字。
* 紅色菱形：那一題用到沒有人產出的數字。
* 「判成真的」看 outcome（`decide_tree.called_real`；沒標的照舊 `bin != 0`）。
* 沒做：CLI `export` 照卡片寫（期 4）；畫布上 Output 的位置（期 5，等使用者）。

---

## F122 期 2：Output 安靜做錯／擋錯的八件（2026-09-29）

使用者：「繼續」。表在計畫書 §4，這裡記決定與沒想到的。

* **「Write to」空著＝資料旁邊的預設**（每張卡一個名字：`d4t_report` /
  `d4t_comparison` / `d4t_charts`；Write KLARF 是原檔旁的 `_adc` / `_top`，in place
  是原檔）。以前那是一條 error，**擋住試跑** —— 而試跑根本不寫。
* **Write KLARF 在沒有 KLARF 的資料上**：開資料時卡上一條 warning、寫的時候跳過並講、
  其他輸出照寫（使用者定的）。預設路徑的規則住 `klarf_out.default_output_path`：
  第一版寫成 `get_step("output_klarf").default_path(...)`，規模尺抓到「UI 按卡片名字
  分支」多了兩處 —— 改成問 export 那一層就一處都不多。
* **Write outputs 對簽章**：量測改了（「Run again」）或判定改了（「先按 Re-run」）
  就拒寫。底稿搬進 `RunController.snapshot`，`studio.py` 因此 −9。
* Studio 寫的時候帶快取；試跑子集寫完講「N of M」。
* lint：`output-collision`（error，比檔名不比資料夾）、`stale-stream-ref`
  （warning，通用鉤子 `Step.optional_streams_in`）。
* CLI 0 顆就停（`uniformity_charts/` 落在 cwd 那一個 —— 建資料夾的其實是 Write report）。
* 規模尺：`inspectors.py` 1,733 → 1,745（簽了，Write KLARF 儀表的兩件內容）；
  `studio.py` 4,302 → 4,293（兩格一起降）。
* 黃金值三份逐項相同；typecheck 128；ruff 乾淨。

---

## F122 期 1：ADC 安靜做錯的八件（2026-09-29）

使用者：「接下來做 ADC 跟 output 兩張卡（先不要動），先列出想法」→「先修會安靜做錯
的，接著按照你的建議修」。計畫書 `docs/plans/F122-adc-and-output.md`（五個問題的答案
與期 5 的畫布提案都在那裡）。

* **沒有判定＝沒有 bin**：`decide` 與 `score.expr` 都空 → `(None, None)`。Studio 新
  recipe 不再塞佔位值 `"0"`（那是一條真的判定：每一顆 bin 1、分數 0，而畫面說
  「unclassified」）；打開帶常數分數的舊檔案照畫面改成空的（UI 層遷移）。
* **樹上問 `score`**：分數改在 let 之後、判定之前算；重判前拿掉上一次的 `score` /
  `decide_unanswered`。以前整批跑答「否」、Re-run 答得出來 —— 同一份 recipe 兩種 bin。
* **「問不出來 → bin N」**：`verdict_rows` 多一列（判定帶、HTML 報表、box plot 以前把
  它們算在「否」那片葉子）；畫布托盤旁寫「3 → bin 99」。
* `rules_to_tree` 帶 outcome（Studio 點一下規則 recipe 就把好／壞消息丟掉）。
* 分數的說明改對（ADCSCORE 不是 DSIZE、空＝沒有分數）；**沒有分數就沒有 ADCSCORE
  欄**（以前全填 0.0）。
* 刪卡也講「誰還指著它的數字」（`RecipeModel.removal_fallout`）。
* 判定 lint：題目缺數字講「答『否』」而不是「會失敗」；知道資料時講「去 Input 卡勾
  Carry these columns」或「這份資料沒有 KLARF」；`route_taken` 不再被說成沒人算。
* CLI `rescore`：卡片出錯的那一顆不再拿殘缺的 features 重判。
* 順手：`add_rule` 的 `StopIteration`、三處過期的註解、歡迎頁的「by a threshold」。
* 查過不是問題的：舊的 feature 改名遷移不改 `decide` —— 那兩張表比判定段早出生。
* 黃金值三份逐項相同；typecheck 128（上限 128）；ruff 乾淨。

---

## F121 期 4：一顆 Open（2026-09-29）

使用者：「繼續做期4」。入口簡單化的最後一期 —— **F121 五期都做完了**，計畫書留在
`docs/plans/` 等使用者試用後說收。

* **一顆「Open data…」**：`scope.INPUT_SOURCES` 剩一列，工具列、空白畫面、Input 卡
  上是同一個字。卡上那顆以前先跳一張「你要開哪一種」的選單，現在直接是對話框
  （非原生，檔案與資料夾都挑得到）。`open_dialogs` 的 `ask_klarf` / `ask_images` /
  `raw_folder_for` 換成 `ask_data` ＋ `open_path`；`studio.py` 拿掉那張選單
  （4,347 → 4,302，HARD_CAPS 與一般上限一起降）。
* **「這條路徑是什麼」只有一個家**：`ingest.dataset.plan_open` → `klarf` / `folder` /
  `image` / `raw`，CLI 的 `_open_input` 叫同一支。認 KLARF 看檔頭
  （`looks_like_klarf`），不看副檔名。
* **做的時候量出來的**：EBI 的 lot 資料夾裡 KLARF 旁邊躺著它的 patch `.tif`，第一版
  把整個 lot 資料夾判成「影像資料夾」。改成**正好一份 KLARF 就開那份**；兩份以上
  不替人挑，`load_folder` 講「挑一份」並列名字（`_KLARFS_ONLY_WARNING`）。
* **CLI 行為變了兩處**（往「跟 Studio 一樣」）：只有一份 KLARF 的資料夾開那份
  KLARF；直接給 `.raw` 檔案走 raw。
* 畫面上六處「use “Open KLARF…” first」改成 “Open data…”；歡迎頁的字從表上讀
  （`welcome.open_title`）。反向測試 `test_ui_one_open.py` 用 ast 掃 `d4t/ui` 的字串
  擋退役的三個鈕名。文件（CLAUDE.md §5、USING-*、recipes/README、
  `one-image-uniformity.json` 的說明）一起改；USING-SIMGEN 那一格本來就寫錯
  （Golden Cell 視窗的鈕叫 `Open image…`），順手對上。
* 黃金值三份逐項相同；typecheck 128（上限 128）；ruff 乾淨。

---

## F121 期 3：Input 卡看資料（2026-09-24）

使用者回報的那一個到這裡收尾：EBI 的 recipe 開在沒有 KLARF 的 RSEM 影像上，
**開資料的那一刻** Input 卡上就有兩句話、按跑在第一顆之前擋下、名字表旁一顆鈕
一按就對齊。

* `ingest.dataset.DataProfile` / `data_profile`：一顆幾張（整批最少／最多）、第一顆
  的影像名、有沒有 KLARF、有哪幾欄。「第幾張」的排法搬進 `images_in_order`（只有
  一個家，Input 卡與 profile 共用）。
* `Step.data_issues(params, data)` ＋ `validate(recipe, data=…)`：Input 卡講三件 ——
  名字表要的張數比資料多（error）、比資料少（info）、`carry` / `only_*` 要 KLARF 或
  那一欄而資料沒有（error；`only_*` 以前講的是「篩選沒對上」）。呼叫點排在入口卡的
  `continue` 之前（第一版排在後面，入口卡一句都問不到）。
* Studio 的健檢與開跑前那兩道、CLI `run` 都餵資料（`RecipeModel.validate(dataset)`）。
* 名字表編輯器的「Match this data's images」：`steps/load.fit_channel_map` ——
  **線能留的就留**（資料有的位置留原名）。第一版照字面填 `1:single`，連 `test` 那一條
  也斷了；改完之後 EBI 在 RSEM 上是 `1:test`，只有吃 `ref` 的卡變紅。知道一顆幾張之後
  名字表只排那麼多列（一顆一張不再多一列寫著 ref）。
* 沒做：KLARF 那幾格整塊變灰（理由在計畫書期 3）。

---

## F121 期 2：一張 Input 卡（2026-09-24）

使用者：「繼續做」（四項已同意：合卡、一顆 Open、名字少於張數就讀第一張並警告、
舊 recipe 自動升級）。

* `load_single`「SEM image」併回 `load_patch`，**label 改成「Input」**（key 沒動，
  出貨 recipe 與黃金值裡的 `load_patch` 一個字都不變）。開資料時補在空白畫布上的
  那一張，**名字表照資料填**（`steps/load.channel_map_for`、
  `RecipeModel.add_starter_input`）：一顆一張 → `1:single`，畫布上一顆埠。
* 遷移 `_migrate_single_into_input`：`load_single(out="x")` → `load_patch("1:x")`，
  節點 id 與流名不變、線一條都不用動。**F11 拆卡那一道加了版本閘（只對第 1 版）**
  —— 不加的話合卡之後每存一次，`1:single` 就被換成 `1:test`（鐵則 9）。
* 升級提示講使用者看過的名字：「renamed “SEM image” → “Input”」，而且不再因為檔案
  是目前版本就不講（`describe_migration`）。
* 兩份出貨 recipe 改成新格式；卡片庫只剩一張載入卡（README／ARCHITECTURE 的卡數
  20 → 19）。
* 黃金值三份逐項相同；typecheck 128（上限 128）；規模尺：遷移 22 → 23、`recipe.py`
  648 → 650、UI 按卡片名分支 23 → 20。
* 留給期 3：資料開著時從卡片庫**手動**加的 Input 卡，名字表是預設的 test/ref。

---

## F121 期 1：recipe 不再以資料型別當鑰匙（2026-09-24）

使用者回報的那一句（`unknown input-type route 'folder'; this recipe only defines
['ebi_patch']`）從這一期起不會再出現在單 route 的 recipe 上。

* **一個判準一個家**：`recipe_schema.route_for(recipe, kind)` —— 只有一條 route 就是
  那一條（不管資料），好幾條才挑同名的。引擎（`resolve_route`）、整批那一層
  （`run_batch_steps`）、`validate`、CLI、Studio 都叫它。型別與鍵名對得上時選到的
  跟以前逐字相同 → 黃金值三份逐項相同。
* `validate` 的 kind 相依 lint（GLV `_center` 那兩條）問的是**資料**的型別，不是鍵名。
* Studio：開資料**只在空白畫布**時改 `model.kind`（先開 recipe 再開資料不再默默改名、
  不再讓存檔改寫原檔）；健檢（Problems 列、畫布警示點、開跑前兩道關）傳
  `dataset.kind`；預覽、區域檢查、校正傳資料的型別。
* **沒照計畫的一件**：`model.kind` 沒改名成 `model.route`（理由在計畫書期 1）。
* 反向還在：手寫的多型別 recipe 碰到沒有的那一種 → 開跑**之前**擋下（以前是跑完
  每一顆都錯）。
* 還沒解的（期 3）：一條 Patch 的 pipeline 開在單張影像上，還是每一顆報「Patch 要 ≥2
  張」—— 講的是真正的原因了，但要提前到開跑之前、掛在 Input 卡上。

---

## F121 期 0：拿掉 DOE 入口（2026-09-24）

使用者：「DOE 的相關都先拿掉……（我當初設計錯了）。DOE 更像是一個資料夾內有多張
圖片但沒有 KLARF 的情況（單張 image）」→「好 開始做」。

* 刪（不是收起來 —— 設計錯了）：`doe_folder` kind、`Open conditions…` 鈕與它的
  `folder_stack` 圖示、`ingest.load_doe_folder`、CLI「資料夾裡只有資料夾 → DOE」那條
  判別、`tools/make_doe_sample.py`、`tests/test_doe_folder.py`。
* **留著**（DOE 那一輪帶出來、但本身通用）：`align` 卡、`combine`、`snr_px`、三條以上
  的流時特徵名帶流名前綴。
* 只有子資料夾的資料夾現在會講「影像在下一層」（CLI 與 Studio 同一句）。
* 黃金值三份逐項相同；全套 `run_tests.py`。
* ⚠ 順手看到、沒修、也還沒查原因：CLI 跑一批 **0 顆**（例：只有子資料夾的
  資料夾）時，`Write charts` 把 `uniformity_charts/` 寫進**目前的工作目錄**。
  跟 DOE 無關，記在這裡。

---

## F121 開案：沒有 KLARF 的 RSEM 影像每一顆都 card error（2026-09-24）

使用者回報：跑沒有 KLARF 的 RSEM 影像，每一顆都報
`unknown input-type route 'folder'; this recipe only defines ebi_patch`。
使用者定調「先查出原因，不要急著動手」—— **這一輪只查、只寫計畫書，程式沒動。**

* **原因**：recipe 用資料型別當鑰匙（`routes = {"ebi_patch": …}`），沒有 KLARF 的影像
  是 `folder`（不是 `rsem`）。三條走得到的路都在 headless Studio 重現過（先有
  pipeline 再開影像／先開影像再開 recipe／先開 recipe 再開影像 —— 最後一條會**默默把
  route 改名**，存檔就改寫原檔）。
* **為什麼沒擋下**：開跑前健檢 `model.validate()` 拿 pipeline 自己的 kind 去比，
  `unknown-route` 那條 lint 寫好了卻餵錯型別。
* **改名也救不了**：實測三份出貨 recipe 硬改成 `folder` —— die-to-die 要兩張圖、
  rsem-worst-box 要 KLARF 欄。卡能不能用看「一顆幾張、有沒有 KLARF」，不看型別名。
* **SEM image ＝ 名字表一列的 Patch**：在 folder／rsem 上像素與特徵逐一相同。
* 使用者：「我想要一勞永逸的改法，Input 跟 Output 和 ADC card 這三張比較特別」、
  「先從 input 開始」、「我想把入口簡單化」；同意合卡（推翻 F11 Input-4）、一顆 Open、
  名字少於張數就讀第一張並警告、舊 recipe 自動升級；**DOE 先拿掉**（「我當初設計錯了」）。
* 計畫書：[`docs/plans/F121-simple-input.md`](docs/plans/F121-simple-input.md)
  —— 期 0 拿掉 DOE、期 1 recipe 不認型別（一條 route 就跑那條，不改格式）、
  期 2 一張 Input 卡（key 留 `load_patch`）、期 3 Input 卡看資料、期 4 一顆 Open。

---

## 專案評價之後的「嚴重～高」那一批（2026-09-24）

使用者：「7 先不要做，按順序做 4 5 6 2 1，6 要有一個切換的按鈕」。#3 量過之後撤回
（出貨的兩份 recipe 早就有 80% 下限的測試，實測 92.5%／93.3%；掉到 12/24 的是
測試用的舊 fixture，不是出貨的東西 —— 評價時寫錯了）。

* **#4 例外型別名不上畫面**：`wording.exception_text(e)`／`wording.failure(where, e)`
  —— 檔案不在／沒權限（「是不是被 Excel 開著」）／是資料夾／記憶體不夠／StepError／
  KeyError 各一句人話，原始 traceback 進 `d4t.log`。UI 十幾個出口全換；反向守門
  `tests/test_wording_exceptions.py`（crashlog 以外不准再拼 `type(e).__name__`）。
* **#5 對話框**：`ui/failure_dialog.py`（`SHOW` 旗標）。只有 Run all 與寫出失敗升級
  成對話框（使用者按下去通常走開了）；`_running_all` 只活到真的開跑。studio 那段
  lambda 收進 `run_ctl._on_trial_failed`（studio.py −2 行）。
* **#6 語言鈕**：`ui/language.py`，工具列主題鈕旁、寫「按下去會切到的那一種」的自稱。
  存 QSettings，`app.py` 建視窗前 `apply_saved()`；切換＝存＋問要不要重開（先照常
  問存檔、關成了才 `startDetached`；`python -m d4t` 啟動的改回 `-m`）。⚠ 全套跑出
  **`test_ui_english_only` 紅**：第一版把中文寫在 .py 裡 —— M7 的規則是 UI 字串一律
  英文、中文只准住翻譯檔。改成英文原句＋`zh_TW.json`，對話框用「要切過去的那一種」
  的譯文講（`language.said_in`），鈕上的自稱是翻譯檔裡的一列（`NAME_KEY`）。
* **#2 bin × 真正類別**：`report._bin_by_class`，ground truth 標了 `type` 才出；
  CLI `run --ground-truth` 與 Excel 摘要頁。合成資料一跑就看得出 EBI 漏抓的 4 顆全是
  `dark_blob`。HTML 報表本來就不吃 ground truth，沒動。
* **#1 問不出來的送去 bin N**（使用者選「警告＋選配設定」）：`DecideSpec.unanswered_bin`
  ／`unanswered_label`，JSON `decide.unanswered` **沒設不寫**（嚴格附加 → 舊檔
  round-trip 不變、不需要遷移、不升 `RECIPE_VERSION`）。沒設＝F30 照舊答「否」。
  判定區一格勾選、CLI 與 Results 工具列常駐「N 顆有題目答不出來」、回溯面板講真正
  去的 bin。黃金值三份逐項相同。
  ⚠ **順帶查出一個舊 bug**：undo 快照（`_decide_snapshot`）從來沒帶規則／otherwise
  的 `outcome`（F119）—— 按一次 undo「好消息／壞消息」就安靜地不見。一起補上。

---

## 專案評價之後的「中等」那一批（2026-09-24）

使用者：「接著做中等部分」。清單上的 #8–#13，做了五項，#11 留著等決定。

* **#8 核心批碰到 Qt**：`test_doe_folder.py` 在函式裡 import `d4t.ui.open_dialogs`
  （模組層就拉 PySide6），沒有 `libEGL` 的機器上核心批紅一條，而兩條既有守門都沒叫
  —— 它們只看「直接寫 PySide6」。補 `importorskip`，並在 `test_no_qt.py` 加一條：
  靜態算出 `d4t/ui` 裡哪幾支會遞移地拉進 Qt，非 `test_ui_*` 檔 import 它們的那個
  函式（或模組層）要有 `importorskip("PySide6.QtWidgets", exc_type=ImportError)`。
* **#9 相對的「Write to」**：以前相對於行程的工作目錄（在 repo 根目錄跑一次 CLI
  就多一個 `ebi_report/`）。現在接在資料旁邊：KLARF 所在資料夾，沒有 KLARF 就是
  影像那個資料夾（`output._anchor`，四張 Output 卡共用）。`recipes/README.md` 與
  `USING-UNIFORMITY.md` 的說法跟著改。
* **#12 `inspectors.py` 3,669 → 1,733**：基底與共用 header → `inspector_base.py`，
  GLV／CD／Enhance 各一支。註冊表不動、`inspectors` 轉出口；`studio_surface` 前後相同。
* **#10 `recipe.py` 4,522 → 648**：`recipe_schema.py`（資料模型）、
  `recipe_migrations.py`（22 道遷移；**呼叫順序仍在 `Recipe.from_json_dict`**）、
  `recipe_validate.py`（lint，延遲 import `Recipe`／`execution_order` 以免繞圈）。
  `recipe.py` 是對外唯一入口、全部轉出口。驗收：`freeze_golden --check` 三份全綠、
  核心批 3801 passed、pyright 128 → 128。讀原始碼的四條測試改讀新檔。
* **#13 範例資料／範本找 repo 路徑**：沒有搬進套件 —— 公司機是整包複製，搬
  `recipes/`（64 個檔案引用）換不到什麼。範本庫本來就會在資料夾不在時回空清單；
  範例資料那一顆改成講白話（「複製整個 d4t 資料夾」），不再印例外型別名。
* **#11 `StudioWindow` 的狀態收進 viewmodel**：**沒做**。量過：controller 對
  window 的直接存取 run_controller 65 處／gallery 62／attach_sources 47／
  gauge_panel 93／studio_layout 362。這是一個要先寫計畫書（F116 §6 的六個坑）
  的工程，不是一輪順手的事 —— 留給使用者決定。
* 另：上一輪拿掉 Help 鈕漏改了三條測試（`f7_19_wiring`／`f7_24_layout`／
  `strings`）、新對話框沒在視窗規則與 `mark_primary` 上表態 —— 全套跑完才抓到，已修。

---

## 專案評價之後的「輕微」那一批（2026-09-24）

使用者請我先評價整個專案、列出從嚴重到輕微的修改清單，然後說「先做輕微部分
（.16 不要做，help 的按鈕跟功能幫我拿掉）」。

* **工具列的 Help 鈕拿掉**（使用者選「只拿工具列 Help 鈕」）—— 連同它掛著的
  「開著哪些視窗」小箭頭，`ui/windows_menu.py` 因此成了孤兒而刪掉。Welcome
  導覽本身、卡片上的「Manual →」都還在；`show_welcome(force=True)` 留著給測試。
  ⚠ 代價：勾過「不再顯示」的人再也叫不回 Welcome（範例資料那一顆在空狀態上還有）。
* **`.raw` 的版面改成一張表單＋即時預覽**（新模組 `ui/raw_dialog.py`）。以前
  選「Something else」之後是連跳四個小對話框（寬 → 高 → 檔頭 → 位元深度），
  填錯一格就從頭來。現在四格一起填，底下常駐講「對不對得上檔案大小、差多少」，
  對上了才准按 OK，並畫出照這組設定讀出來的縮圖（只讀縮圖要的那幾列，`memmap`）。
  另有一顆「Height from file size」。推得出唯一解時的那一步選單照舊。
* **提示字放大一號**：`font_tiny` 10 → 11、`font_small` 11 → 12（theme token）。
* **用字**：設定區空狀態與狀態列上把管線上的卡叫 step 的兩句改成 card
  （判定樹上的 step 是「一題」，那是對的，不動）。
* **`engine.py` 的 `except Exception`**：`_roi_snapshot` 收窄到
  `(TypeError, ValueError, AttributeError)`；其餘是刻意的退路（`feature_prefix`
  「一定要有退路」、快取層出包當 miss），**不收窄**（收窄會讓 `run_defect`
  有機會 raise，違反鐵則 7），改成補上 `swallowed()` —— 至少 `--log` 看得到。
* **`strings.py` 檔頭說謊**（還寫著「沒有 tr() 也沒有 catalog」）→ 改成現況：
  機制在、`install()` 還沒有人叫。

---

## F120 收尾：Pitch helper 搬去自己的 repo，d4t 這邊移除乾淨（2026-09-23）

使用者 2026-09-23：「我之後帶走後 d4t 會把 pitch helper 移除，就等於 pitch
helper 直接開新 repo，原來 d4t 不會有殘留」，然後開了 repo
（<https://github.com/hxlub0905-cmyk/pitch-helper>，public）並說「幫我做 d4t -B」。
simgen 那一支**不搬**（使用者同一天決定），所以 `apps/` 整個跟著刪 —— 它本來
就只是搬家的箱子。

**A（開新 repo）**：48 個檔、`ruff` 全綠、141 條測試全綠、量到 60×44 信心
92.4／92.6。⚠ 照著交接檔做才發現改 import 的 `sed` **不夠**：三條測試驗的東西
在新 repo 裡本來就不存在（讀 `d4t/__main__.py` 原始碼那條、`BLURRED_BELOW`
指向沒被抽出來的 `template_dialog` 那條、從 Studio 原始碼反查 `Cell W`／`Cell H`
那條）。另外補了 `pyproject.toml`（ruff 沒設定會報一大片誤報）、`.gitignore`、CI。

**B（從 d4t 移除）**：整支刪 8 個（含 `apps/`、`tools/extract_app.py`、交接檔
自己）、逐行改 11 個、5 處註解改字不改行為。`docs/plans/F120-*.md` 搬進
`docs/history/plans/`。`confidence_at` 跟著走了 —— 它唯一的呼叫者是 helper 本人
（早期版本誤把它列進「不要刪」）。

**這一輪唯一值得記下來的事**：**刪的時候真正的風險不是「刪不乾淨」，是「刪到
不該刪的」。** 那幾條為了抽取才剪的解耦，d4t 自己也受益，而它們在移除之後看
起來就像死碼 —— `core/export/ramps.py`（色階的家，讓 `ui/image_view.py` 不再為
了一個顏色函式 import 報表產生器：省 10 支模組、7,672 行）、四行不走 `widgets`
轉出口的 import、`algo/golden.BLURRED_BELOW`（門檻住在演算法旁邊）、
`algo/template.measure_period` 公開（量週期只有一個家）。所以這一輪**沒有只刪
東西**：每一條的理由都改寫成「為什麼它現在還在」，指向
`docs/history/plans/F120-pitch-helper.md`，而不是指向一支不存在的模組。

⚠ 另外兩次 CI 紅燈都是同一個形狀 ——「我把『受影響』想成程式碼」：新增一支模組
沒畫上 ARCHITECTURE 的目錄樹、改一行 `.md` 沒重跑 `tools/release.py`（搬運檔是
從 `git ls-files` 產的）。收斂成一句：**動到版控裡任何一個檔案就跑那一行**。

## F120 Pitch helper：七輪，而第七輪才發現前三輪沒生效（2026-09-21）

使用者要把「算 repeating pattern 的 cell period」獨立成一個 helper（原本 ROI
那張卡一個字不動），形狀照 `simgen`：`python -m d4t pitch`。七輪回饋全部在
[`docs/history/plans/F120-pitch-helper.md`](docs/history/plans/F120-pitch-helper.md)。

**這一輪唯一值得記下來的事**：使用者連著三輪說「Period 答案要清楚一點」，而
**我每一輪都改了、每一輪都沒有生效**。程式碼寫的是
`f.setPointSizeF(f.pointSizeF() * 2.6)` —— 這個 app 的 QSS 用**像素**設字級，
所以 `pointSizeF()` 回 **-1**，乘出來是負數，Qt **安靜地忽略**；而且就算改成
`setPixelSize` 也沒用，因為 QSS 的 `* { font-size }` 贏過 per-widget 的
`setFont()`。量出來答案的字一直是 13 px，跟旁邊的說明一模一樣。

> **一個沒有生效的視覺改動，看起來跟沒有被聽見一模一樣。**
> 使用者第三次講同一句話的時候，該懷疑的是「它到底有沒有發生」，不是「要放多大」。

修法是走 QSS 的 objectName（`theme` 新增 `font_answer` token ＋ 三條規則），
而守門的測試**量渲染出來的 `fontMetrics().height()`**，不是「我們設了什麼」
—— 已驗證把 objectName 換掉它會紅。⚠ 測試裡要先 `ensurePolished()`：QSS 是
polish 的時候才套上去的。

同一輪的另外六點：自定義 period 也有 confidence 了（`period.confidence_at`
—— 不是新演算法，是 `_analyze_axis` 的尾巴在呼叫者指定的 lag 上求值，所以跟
引擎報的分數同尺度：打 45 對一張 60 的圖得 0.0，長條當場變紅）、換算後的單位
改 µm、Copy 搬到答案正下方（「copy 是 copy 誰？」）、`X + Y` 改名
`Force both`、打字中途不重算、疊圖那一行三句收成一句。連帶修掉 `Bar` 的
「0 分畫成空軌道」（跟「沒有被評分過」長得一樣）與 `_fill_try` 的孤兒候選鈕
（`removeWidget` 不會讓它從畫面上消失，實拍到它疊在最大的那個答案上）。

⚠ **更正我自己上一輪講錯的數字**：`main` 的 pyright 不是 128 而是 **131**
（同容器、同版 pyright，用 `git worktree` 開 `origin/main` 量的），也就是
`main` 自己就超過它自己的上限，而 F120 這條分支一條都沒有加（兩份清單逐行
相同）。這一輪把那 3 條修掉了，現在 128 = 上限，沒有調高任何天花板。

---

## F117 I6：畫布、Features、Results 互相指（2026-09-20）

走查 52/58 → 53/58。這三塊講的是同一顆 defect 的三個面向 —— 畫布是**怎麼算
的**、Features 是**算出什麼**、Results 是**一整批算出什麼**。在這之前，從一個
數字回頭找到算它的那張卡，靠的是**使用者自己記得**。

兩條路，而**它們刻意不一樣**：

| 手勢 | 做什麼 | 為什麼 |
|---|---|---|
| 滑過 Features 的一段 | `reveal_cards`（hover 那一套） | 只是看一眼 —— 不動右邊的設定，滑鼠一離開就熄掉 |
| Results 欄名的右鍵選單 | `select_node`（真的選取） | 那是「帶我去」，點下去就是要動手改 |

⚠ **右鍵不是左鍵。** 表頭的左鍵已經是排序（`setSortingEnabled`）—— 搶走它等
於把一個每天都在用的手勢，換成一個偶爾用的。

⚠ **滑過去是一「段」不是一「列」。** 一段就是一張卡，而一列屬於它所在的那一
段。逐列發訊號的話，同一張卡在手往下移的路上會被指十幾次，而畫布那邊每一次都
要清掉再亮一次。用 `enterEvent`／`leaveEvent`（Qt 本來就算好了「還在不在同一
段裡」），不自己追座標。

⚠ **離開要送空字串，不是不送。** 沒有那一半的話，滑鼠移出面板之後那張卡會一
直亮著，而使用者早就不在看它了。

⚠ **引擎那幾欄沒有那一項**（`score`／`bin`／`defect_id`／`ok`／`error`）——
它們不是任何一張卡量出來的，而一個點下去只會說「找不到」的選單項，比沒有那一
項更傷。找不到的時候**要講**：那通常表示那一欄是上一批跑出來的，recipe 已經
改過了。

⚠ 「誰算出這個數字」**問 `bound_specs`，不自己拆字串** —— `test_epi_hot_glv_median`
裡哪一段是流、哪一段是區域、哪一段是使用者自己取的名字，三者都是任意識別碼，
而「誰產出它」那份宣告本來就在。

### 那兩條接線沒有變成 `StudioWindow` 的方法

內容住新模組 `ui/cross_links.py`（`studio.py` 留給接線，CLAUDE.md §4）。
第一版寫成三個 `StudioWindow` 方法，而**行數與方法數兩格都是 `HARD_CAPS`**
—— 行數那一格 +34、方法數那一格 +3，兩條同時紅。

所以接線接的是 `partial(cross_links.hover_card, win)`。那不只是為了過尺：
內容住在模組層**也比較好測** —— 測試直接叫那一支，不必先開一個視窗。

---

## F117 第八批：講得出「哪一個」（2026-09-20）

**C2／E3／G2／G5**（走查 48/58 → 52/58）。四條的共通點：**畫面上有東西，但它
沒說自己是哪一個。**

### C2：不是「說明文字太長」，是名字本身少畫了兩段

走查記的是「`clip_frac` 三列、`peak` 兩列，說明文字有寫但要讀完那句才懂」，
建議「名字後面直接帶來源卡」。量過之後看到的是更根本的事：

`ref_clip_frac` 的 `base` 還是 `clip_frac`，而 `feature_html` 畫的是 **base**
—— 於是三個被救回來的值在畫面上**長得一模一樣**。`peak` 與 `peak_missing`
同理（base 都是 `peak`）。救援用的前綴與 variant **都沒有被畫出來**。

修法：`FeatureSpec` 多一格 `qualifier`（撞名救援時加在前面的那一段），
`parts()` 把它與 `variant` 一起帶出去，名字上畫成下標。

⚠ **`rescued` 這個字不畫** —— 前綴已經把它分出來了，再寫一次沒有多講任何
東西（「為什麼它還在」那句話住在 gloss）。

⚠ **順帶把 `VARIANT_COLUMNS` 從 `feature_panel` 搬到 `feature_text`。**
`feature_html` 要知道「這個 variant 有沒有別人在畫」才不會畫兩次，而
`feature_panel` import 那一支 —— 反過來是循環。第一版在低層**抄了一份**，
而那一份當場就漏了 `worst`：測試一跑就紅。**那是「抄第二份」最好的結局** ——
它通常要等到有人看到畫面上兩個一樣的字才會被發現。

### E3：做完一半，而另一半講得出為什麼沒做

patch 與 RSEM 的影像**就是繞著那一顆切出來的**，所以 defect 在正中間 ——
縮圖標一個中心十字（`mark_aim`，theme 裡「畫在別人照片上」那一組；中間留白，
不蓋住要看的那幾個像素）。

⚠ **`folder` / `doe_folder` 不標。** 那兩種沒有 KLARF、也沒有「defect 在哪」
這回事（整張圖就是那一顆）—— 畫一個十字是**憑空指一個地方**，而使用者會以為
那裡真的有東西。

⚠ **量測卡標出來的框沒有畫。** 那要知道原圖的長寬才映得回縮圖
（`thumb_placement` 要 shape），而縮圖那條鏈（`load_thumb` → `ThumbWorker`）
只回一個陣列。那是另一輪的事，不是這一輪沒做完。

### G2：兩邊對不上是對的，缺的只是一句話

歡迎頁三段底下加一句：那三段是**引擎在做什麼**，卡片庫分七群是**使用者要找
什麼**，同一批卡片兩個入口。

⚠ **群數是數出來的不是打上去的**（`axes_note()` 去問 `step.GROUPS`）。寫死一
個 7 的話，加一群的那天它會變成一句安靜的假話 —— 畫面上寫七群、卡片庫裡是
八群，而沒有任何測試會紅。

### G5：編號照眼睛走的路；沒量到的週期不要寫一個數字

以前是 1、2 在左，3 在右，4、5 又回左，6 在右 —— 讀一次要橫跨畫面三趟。現在
左欄由上到下是 1～4、右欄是 5、6。

⚠ **換的是編號不是位置**：那一塊畫布（「缺陷可能出現在哪」）需要高度，它只
放得下右欄。

週期欄的 `4.00` 是 `setRange` 的下限、不是任何人量出來的數字 —— 下限改成 0
並用 `setSpecialValueText` 寫成 `—`。⚠ **0 不是合法的週期**，所以拿它當特殊
值沒有歧義（同 F117 B4 的 `min_label`：那裡的 0 是「全部」，這裡的 0 是
「還沒有」）。

⚠ 順帶補一道關：**週期是 0 就不准按 Generate** —— `tile(..., 0, 0)` 會除以
零，而以前那一格永遠有一個「值」，所以這道關從來沒有人需要。

---

## F117 第七批：同一件事只有一種長相（2026-09-20）

**H2／H3／I12／I2／A6**（走查 43/58 → 48/58）。五條都是「樣式一致性」，而
**其中三條量過之後發現走查的描述不完整或方向相反** —— 這一輪最值得記的是那
三次。

### H2：兩條狀態列 —— 沒有併成一條，而那是刻意的

量出來畫面最底下真的是兩條 26 px ＋ 35 px 的橫條，兩條都是「一行字 ＋ 右邊一
顆鈕」。但它們**確實是兩件事**：問題列講的是**常駐的狀態**（現在能不能跑），
狀態列講的是**剛剛發生了什麼**。併成一條的話，一句 `Run finished` 會把一條擋
著跑的錯誤洗掉。

真正的毛病是 `Nothing is blocking a run.` —— 一句**永遠不會帶來消息**的話，
卻常駐佔著 26 px。收掉之後第二條只在它真的有話要說時出現，那時候它帶著 ✕／⚠
與顏色，跟狀態列一眼分得開。這也是這個 repo 自己的規矩：**一條常駐的 warning
會被學會忽略，而真的那一條也跟著被忽略**（`Issue` 的 `info` 那一級寫著同一句）。

另一半：「跑完了還沒寫」那句話在 Results 裡又出現一次 —— 而讀到它的人**就在
Results**，那顆 `Write outputs` 就在他上面，tooltip 還寫著同一件事。那句話在
Studio 是唯一講得出這件事的地方（留著），在 Results 是叫他去他已經在的地方
（剪掉）。⚠ 順手把剪完留下的孤兒分隔點也清掉 —— 一個孤零零的 `·` 在句首讀起
來像畫面壞了。

### H3：走查說第三列被切，實際上三列全部被切

那三段說明各 115～169 字，在那一欄折成 7～9 行、整塊 **623 px** 高；而
1366×768 上那一塊看得到的只有 **160 px**。所以不是第三列被切 —— 是**第一列
從第 160 px 起就沒了**。

改成**一句話 ＋ 全文進 tooltip**，並拿掉一列兩側的彈簧（那一欄只有 509 px
寬，兩邊各留一份等於把 159 px 讓給空白，說明因此從兩行變三行、三列一起多 70
px 高）。量出來 **623 → 337 px**，前兩列不必捲就看得到。

⚠ **第三列仍然要捲一下**，而我停在這裡：要三列全進 160 px 就得砍掉標題那一
塊，那是另一個決定。那一塊本來就在 `fit_screen.scrolled` 裡，所以東西沒有不
見，只是要捲。

⚠ 「第一句」那支 helper 從 `welcome._headline` 搬進 `ui/wording.py`
（`headline`）—— 範本庫那一行與這三列共用。**兩份的那一天，其中一份會學會留
問號而另一份不會。**

### I12：不是有人選了兩種樣式，是兩種來路

自己 `QPushButton` 再 `setObjectName("primary")` 的都是藍的，而
`QDialogButtonBox` 生出來的那一顆**沒有人去標**。新增
`buttons.mark_primary(box)`，四個對話框各叫一次。

⚠ **只標 Accept 那一顆**：一排只有 `Close` 的 box **沒有主要動作**，硬標一顆
藍的等於把「離開」講成「完成」。反向測試列出那兩支例外並各附一句為什麼。

⚠ **改了 `objectName` 要 `unpolish` / `polish`** —— Qt 的 QSS 是在 polish 的
時候比對 selector 的，而那顆鈕早就 polish 過了。不重算的話它會留在白色，而
程式碼看起來完全正確。

### I2：那「兩個強調色」其實是三組沒有人決定過的東西

量過之後：

* `max_accent*`（藍）是 `accent*` 的**逐位元組複本**，而且**零個呼叫者**；
* `min_accent_bg` / `_border` / `_text` 也是零個；
* `min_accent`（橘棕）只有**一個**用處 —— 畫在使用者影像上的去雜訊核心框。

⚠ **兩個名字指同一個顏色，就是調色盤開始漂的樣子**：改了一個，另一個安靜地
留在原地。處置：前兩組刪掉，`min_accent` 改名 `mark_kernel` 並搬去「畫在影像
上的記號」那一段 —— 它本來就不是強調色，而放錯段落正是它多年沒人看見的原因。

### A6：走查的判斷是反的

| 量到的（修之前） | dark | light |
|---|---|---|
| 連線 vs 畫布底 | 2.99 | **2.10** |
| 卡片框 vs 畫布底 | 1.51 | **1.03** |

走查寫的是「深色模式對比比淺色低」。**兩套都不及格，而淺色是比較糟的那一
個** —— 淺色的卡片框只有 **1.03**，等於那條框不存在，卡片全靠底色差 1.22 跟
畫布分開。

修法：`canvas_edge` 兩套都拉過 3.0（WCAG 1.4.11 對非文字的門檻），卡片框改用
新的 `canvas_card_border`。⚠ **不動 `border_default`** —— 那一個是配面板底色
調的，整批改會波及每一塊面板；畫布有自己的底色，就該有自己的框色。

⚠ **格線刻意不拉**：它是背景的紋理，不是承載意思的東西。拉到 3.0 畫布會變成
一張點陣紙，而卡片與線要跟那些點搶注意力。有一條反向測試釘住「格線要看得見，
但要比卡片框淡」。

那張對照表寫進 `test_ui_contrast.py` 的註解裡 —— **下一個人會再從那份走查讀到
「深色比較糟」那句話**，而那句話是錯的。

---

## F117 第六批：離開這個工具的那些檔案（2026-09-20）

**F5／F3／F8／F7**（走查 39/58 → 43/58）。這一群的共通點跟前幾批不同：
**使用者會把它寄給別人。** 畫面上的毛病他自己能繞過，寄出去的 CSV 與報表不能
—— 而收到的人沒有這個工具可以回頭問。

### F5：兩條建議都沒照做，因為真相是第三件事

走查記的是均勻度 CSV 的欄名 `cells_cells_area_px`，附了兩條建議（改前綴規則、
或換區域名）。**兩條都沒照做**，因為量過之後看到的是：

ROI 卡的 base 名**本來就帶著區域名**（`cells_area_px` ＝ 區域 `cells` 的面
積），而出貨的 recipe 又填了一個一模一樣的 `output_prefix`。那一格的 help 明
寫著「只有這一張卡的話就留空」—— **它是多餘的。** 拿掉就好。

⚠ **沒有改組名字的規則**（「遇到同名不疊」）。那條規則改一個字，全 repo 的特
徵名就換一批：分數表達式要遷移、黃金值要重錄 —— 而換來的是一個**看不見的**
行為（下一個人讀 `full_prefix` 不會知道有這回事）。

改成一條 lint（`doubled-prefix`，warning）。它便宜，而且擋得住**每一張卡**，
不只被走查點到的那一張。⚠ 只看**相鄰**的重複：`epi_center_epi` 那種講的是
兩件不同的事。⚠ 只在使用者**填了** `output_prefix` 的時候查 —— 那是他唯一改
得動的東西，而一條給不出動作的提醒會把真的那一條一起教成雜訊。

### F3：機制早就有，而路上還有第四份手抄的 writer

兩份走 KLARF 的出貨 recipe 打開 `carry: "XREL,YREL"`。

⚠ **只點名座標。** 少一欄就整批失敗（`load._carry_features` 故意拋 —— 那是
對的，打錯欄名不可以安靜地沒事）。`XREL`／`YREL` 是「一顆 defect 在哪裡」，
沒有它們的 KLARF 不成立；`CLASSNUMBER` 這種**刻意不填**：一份沒有分類的檢測
結果可以完全合法地沒有那一欄，而那會讓一份出貨的 recipe 在對方的機器上一顆都
跑不出來。`one-image-uniformity` 走 `folder`、**根本沒有 KLARF**，所以它一欄
都不帶。

**順帶查出一件事**：`d4t run --csv` 有一份**手抄的 CSV writer**。F117 F1 修
「表頭裡 `score` 出現兩次」的時候數到三個寫檔的地方（`write_csv`、xlsx 的明細
頁、HTML 報表）—— 而這是**第四份**，它沒有被數到，所以那個 bug 在那條路上一直
活到今天。改走 `report.write_csv`，順便拿到另外三份早就有的東西（`ok` 是 1/0、
非有限的數字寫成空格）。CLAUDE.md §0 那句話的第 N 次：**抄第二份出來的那份一定
會漂。**

**打開 carry 的那一刻，三個地方同時紅了 —— 而它們是三件不同的事。**

1. **`test_shipped_recipes` 走的不是產品走的那條路。** `run_batch` 自己不填那
   幾欄；CLI 與 Studio 各自在跑之前填，而直接叫 `run_batch` 的人（這支測試、
   `tools/bench.py`）得自己來。訊息是「這份 KLARF 沒有那個欄位，它有的是：
   (nothing)」—— 看起來像 recipe 壞了。這一輪先讓測試走對門（`_carry` 那支的
   docstring 記著），把「搬進引擎」開成一張待辦。
2. **`test_ui_template_library` 抓到的是一個真的產品 bug。** Studio 只在
   「換一份資料」與「改那一格」時重填 —— **換一份 recipe 不會**。於是「先開
   lot、再開一份有勾 `carry` 的 recipe」那條路上，那幾欄從來沒有被填過，而
   症狀是每一顆都失敗。`load_recipe_path` 補上一行。
   ⚠ 這個洞在這一輪之前**一直都在**，只是沒有一份出貨的 recipe 勾過 `carry`
   所以沒有人走到。
3. **`test_output_uniformity` 的 fixture 跟出貨的 recipe 犯同一個錯**（也填了
   一個跟區域同名的 `output_prefix`）—— 新的 lint 當場咬住它。一起拿掉。

### F8：四件事，四種不同的錯

* **熱圖刻度 `24.50`** —— 框中心落在半個像素上是真的，但**它不是資訊**。
  取整。⚠ 取整之後兩個刻度撞在一起就不取整：框只有幾個像素寬的時候，印兩個
  一樣的數字比印 `24.50` 糟得多，因為它看起來像畫錯了。
* **標題一個靠左三個置中** —— 兩種對齊在同一頁上就是不對，眼睛會以為那是兩類
  東西。統一靠左：盒鬚圖的副標就在標題正下方而且靠左（置中會把那一對拆開），
  而那一頁是一疊全部靠左的東西。
* **Position profile 三種線沒有圖例** —— 實線是 profile（**讀平不平的就是
  它**）、粗虛線是趨勢、細點線是那一群的平均，而以前只有趨勢有一句話。
  ⚠ 圖例**畫一小段真的線，不是色塊**：要分的正好就是虛實。斜率那個數字留著
  —— 它是一個數字，圖例講的是「哪一條是哪一條」，兩件事。
* **摘要表 `range` 整欄是 `-`** —— 那兩欄空著是因為使用者在 GLV 卡上**已經
  回答過了**（沒勾 range）。印一欄他答過「不要」的問題，等於把那個答案當成一個
  沒填的空格。整欄沒量到就不印。⚠ **有一格有值就整欄留著**：那時候的 `-` 是
  真的資訊（別的區域量得到，這一個量不到）。兩種 `-` 長得一樣而意思差很遠。

### F7：寬頁排兩欄

四張圖問的是同一張影像的四個面向，而使用者是拿它們**互相對照**的 —— 一張在螢
幕上、一張要捲下去，等於沒有並排。

⚠ **`auto-fit` 而不是寫死兩欄**：窄的頁面（筆電、投影、印出來的 A4）自己收回
一欄，不必判斷誰在看。一張圖的那一頁也走同一條路 —— 兩種版型就是兩種要維護的
東西。560px 是那幾張 SVG 縮到還讀得出刻度的寬度：**讀不到刻度的兩張圖不如一張
讀得到的。**

---

## F117 第五批：畫布與卡片上那一群（2026-09-20）

**B1／B4／J4／I7**（走查 35/58 → 39/58）。四條都在畫布與卡片上，而它們問的
是同一件事的四種變形：**畫面上這個東西，使用者讀得出它在說什麼嗎。**

### B1：一排按不下去的東西

GLV 最上面「What to measure」三顆，在沒接 Region 的時候全灰。**現在整排不
畫**，只留標題與那句 `Wire a Region card into “Region” first.`。

三顆灰膠囊是純噪音：它們佔著一張卡最顯眼的位置，卻只能重複一次「現在不行」
—— 而那句話底下那一行本來就說得出該做什麼。

⚠ **不是 `title=""`。** 標題留著，因為它講的是「接好線之後這裡會有一個選
擇」—— 整段收掉的話，使用者不會知道自己少了什麼。

順帶把舊的那條規則升級了：以前有一條測試說「灰掉的東西按了不可以生效」
（Qt 只擋得住滑鼠，鍵盤與直接呼叫擋不到）。**不存在的東西沒有這個問題。**

### B4：一張卡上的三件事，是三種不同的錯

* **`At most this many defects 0`** —— 一個**沒有名字的特殊值**。新增
  `ParamSpec.min_label`（Qt 的 `specialValueText`）。⚠ 三張卡上寫著
  `LIMIT_ZERO_HELP` 的那一格**都**補上，不只被走查點到的那一張 ——
  同一個約定在三個地方長得不一樣，下一個人讀到的是「有的有、有的沒有」。
* **第五格勾選框叫 `chart`** —— **recipe 的鍵漏到畫面上**。`CHART_LABELS`
  裡早就寫著 `Your own chart`，只是沒有人把它接上去。⚠ **存進 recipe 的值一字
  未動**：改值要付一道遷移，而且檔名 `-chart.svg` 也要跟著改。
* **`Enabled` 當 label** —— 一個**通用詞**佔著那一格（`param_form` 寫死給所有
  bool 的字）。字搬到勾選框上，名字欄由 `_label_is_echo` 收起來。

十一個 bool 的 label 一個都不用改 —— 它們讀起來本來就正好是一句「勾了會發生
什麼」（`Also write a table, one row per box`）。**那個通用詞從來沒有資訊，
它只是佔著位置。**

### I7：那一行重複七次之後就不是資訊了

卡片上的 `20 ok · 2051 img/s` 現在只留給**失敗**（永遠講）與**瓶頸**。

⚠ 門檻是一句話：**它一張比其他所有卡加起來還久**（`SLOW_SHARE = 0.5`）。
第一版寫三分之一，而它在**兩張卡**的批次上當場破功：兩張一樣快的各佔 50%，
於是其中一張被指成瓶頸 —— 而那兩張一模一樣。**一個跟卡片張數有關的門檻，
要嘛跟著張數算，要嘛就用一句跟張數無關的話。**

⚠ **不是把數字丟掉。** 每一張卡的速率照樣量得到，它搬進 tooltip
（`Last run: …`）—— 丟掉一個量得到的數字，跟把它印七遍一樣糟，只是錯的方向
不同。

### J4：斷開是對的，重拉才是問題

刪掉中間的卡，上下游斷開 —— 而**斷開本身是對的**：`remove` 連同碰到它的每一
條線一起拿掉，因為殘留的線會接到一張使用者從來沒接過的新卡（F10-5 那個使用者
回報過的 bug）。真正的問題是**接回來要重拉一次**，而他剛剛做的只是「把中間這
張換掉」。

⚠ **是提議，不是自動補線**（鐵則 10：畫布上每一條線都是使用者拉的）。刪完狀
態列掛一顆 `Reconnect`，按下去才成真 —— 而整批算**一步復原**。

⚠ **哪一條是「穿過去」的那一條**：一條就是它；好幾條的時候只認**複數那一格**
（`image_keys`）—— CLAUDE.md 的單複數規矩：`*_keys` 是「這張卡處理的東西」，
`*_key` 是「順便參考的另一條流」（`normalize` 的 `range_from` 就是後者）。
兩個都問不出來（`subtract` 的 `a` 與 `b` 一樣重要）就**不提議**：
**猜錯一條線會安靜地算出一批看起來很正常的數字。**

⚠ 按下去走的是**跟手拉線同一條路**（`canvas_edges.connect`），不是
`model.add_edge` 的捷徑 —— 不然補出來的線跟手拉的線不一樣，而畫布上看起來會
一模一樣。有一條測試用 `ast` 守著那條捷徑不存在。

**那顆鈕讓 `studio.py` 長了 12 行，而它那一格是 `HARD_CAPS`（只准往下）。**
所以整支 `_on_remove_requested` 搬進 `canvas_edges.py` —— 那件事從頭到尾都是
線的事（剪掉它餵出去的每一條、把下游那幾格空出來、算一份補線的提議），
`studio.py` 上只剩兩行門面。那條尺本來就是這樣用的：**要往它加東西，先從它
手上搬走等量的東西。**

### 第三次踩同一個坑，所以這次做了一個守門的

寫檔案的路上（heredoc → shell → Python）會吃掉一層反斜線，於是原始碼裡的
「字界」符號變成一個真的 0x08 控制字元。這是第三次：

1. **F117 D4**：`re.search` 的判準因此永遠不 match —— **整組測試都是綠的**。
2. 這一輪兩次，都落在說明文字裡（只是難看）—— 但下一次會落在哪裡沒有人保證。

`tests/test_source_hygiene.py` 每次都跑，掃 `d4t`／`tests`／`tools`／`bundle`。

⚠ **那張表用 `chr()` 寫，不用跳脫序列。** 第一版寫成字面的跳脫序列，而寫檔案
的那條路把它們變成了真的控制字元 —— 於是這支測試在它自己身上抓到四個違規。
那個笑話正是它存在的理由：**判準不能用它要擋的那個東西寫成。**

---

## F117 第四批：範本庫的字、剩餘時間、手冊（2026-09-20）

**G3／G4／K3／K1**（走查 31/58 → 35/58）。

這一批的共通點是**「東西在，而使用者
不知道」** —— 四條都不是功能壞了，是功能沒被講出來。

### G3：清單上寫的是 recipe JSON 的鍵

範本庫的第一行是 `ebi_die_to_die`、第二行是 `route: ebi_patch`。兩個都是 JSON
的鍵，而使用者在那個清單上要決定的是「**哪一份最接近我的層**」。

改成：第一行是**作者自己寫的那一句**（截到 72 字、問句保留問號 —— 出貨那三份
的第一句有 150～400 個字，整句放進清單就變成一面牆），第二行把 `ebi_patch`
換成 `patch images`。白話住在 `scope.KIND_WORDS`（入口長什麼樣的唯一去處）。

⚠ **認不得的 kind 原樣回去**。猜一個漂亮名字會把線索蓋掉 —— 那一格如果寫著
一個沒見過的字，使用者能拿它去問；寫著一句瞎掰的白話，他只會以為自己看錯。

右邊那一塊寫著 `score = (no score expression)`，而那句話**讀起來像「這一份
不會判定」** —— 它其實是用判定樹判定的。改成
`Sorts with a decision tree on the canvas (3 classes)`；門檻跟著 score 走，
一樣不印（不然像是跟一個數字比大小）。

⚠ 數類別讀的是**生的 JSON**，不是 `DecideSpec`。`read_recipe_info` 的規矩是
「不驗證、不炸」：壞掉的檔案要變成一列紅字，不是讓整個庫開不起來。

### G4：兩種相反的處理待在同一個容器裡

Template 對話框工具列底下那句說明被切、還壓著一條橫向捲軸。**原因在版面樹上
看不出來**：那句話被包進了 `fit_screen.scroll_row`，而那一支把高度鎖成
「一列鈕 ＋ 捲軸」。

> **鈕排不下要橫向捲，說明排不下要換行 —— 兩種相反的處理不能待在同一個容器
> 裡。** 這是這一條真正的教訓，不是「那句話太長」。

### K3：六萬顆的批次，答不出「我現在要不要走開」

`Running: 3 / 60000` 是一個誠實但沒有用的句子。三分鐘跟三小時是兩種完全不同
的決定，而那個分數答不出來。現在是
`Running: 20000 / 60000  ·  about 20 min left`。

⚠ **頭幾顆不算數。** 第一顆要載影像、暖快取、開 worker，它比後面每一顆都慢
好幾倍 —— 拿它去乘六萬，畫面上會出現一個大到荒謬的數字，而**一個一看就知道
是假的估計，會讓使用者連後面真的那個也不信**。所以 5 顆 ＋ 2 秒之前一個字都
不講（`ETA_MIN_DONE` / `ETA_MIN_SECONDS`）。

用**整批的平均**而不是瞬時速度：平均自己會平滑。秒取整到 5，買到的是
「同一句話要站得住幾秒」—— 進度每跑一顆就回報一次，而六萬顆的批次一秒會回報
好幾次。

**「可暫停」與「跑完通知」沒做**，走查那一列的另外兩半留著：暫停要動 worker
的協定、通知要碰系統匣，兩件都不是這一輪的範圍。

### K1：手冊在 repo 裡，而廠內使用者不會去翻

那句話底下是**兩個**不同的問題，而兩個都要答：

1. **他不知道有這份東西。** 入口長在**用得到它的那張卡上** —— 選了 CD 卡的人
   才需要 `USING-CD.md`。工具列上一顆「Help」對他沒有意義。
2. **他打不開。** 那是 Markdown，而公司機上不保證有任何一個看得懂 `.md` 的
   程式。所以 d4t 自己畫（`QTextBrowser.setMarkdown`，`d4t/ui/manual.py`）。

⚠ **不准把檔案交給作業系統去開**（`QDesktopServices.openUrl`）。那一步會把一個
本機檔案交給一個我們不知道是什麼的程式，而在一台受限的機器上那是一件會失敗得
很難看的事 —— **失敗的時候畫面上什麼都不會發生**。手冊裡指向原始碼與外部網址
的連結一律不跟；指向另一份手冊的才跟（同一個視窗換內容）。

⚠ **哪張卡配哪一份，寫在卡片自己身上**（`Step.manual`），不在 UI 的一張對照
表上。那張表會變成「按卡片名字分支」的第 N 處（`test_size_ceilings.py` 數
著），而且它跟卡片隔了一個目錄 —— **卡片改名的那天沒有人會想到去改它**。
`USING-SIMGEN.md` 不屬於任何一張卡（它講的是產模擬資料那個視窗），所以那個
視窗上有一個 `MANUAL` 常數 —— **它是唯一的例外，而測試指得出它的名字**。

⚠ **`docs/` 沒跟著裝過去的機器上不給連結**：一個點下去說「找不到」的連結比
沒有連結更糟，它每一次都在提醒使用者這個工具少了一塊。

反向測試是這一支裡最重要的一條：**`docs/` 裡每一份 `USING-*.md` 都要有人連得
到**。新加一份而沒有任何入口的話，它會跟走查抱怨的那一刻一模一樣。

### 又一次：一條會誤報的測試

「不准呼叫 `openUrl`」第一版寫成 `assert "openUrl" not in src` —— 而這個模組的
**註解裡就寫著為什麼不准呼叫它**，於是那條測試咬了自己的說明。改用 `ast` 掃
屬性名。跟 F117 D4 那次 `grade` 咬 `upgraded` 是同一件事的第二次：
**substring 不是判準，結構才是。**

---

## F117 第三批：讀得到（2026-09-20）

**A4／C1／I8／B3**（走查 27/58 → 31/58）。四條走查、同一個病灶：**畫面上最
重要的那個東西被次要的東西擠掉了。**

### A4：Tune 的畫布只分到 40%

同一份 recipe 在 Build 縮到 61% 讀得到副標與埠名，在 Tune 是 50% ——
`CANVAS_SHARE_TUNE` 0.40 → 0.50（縮放大致跟受限的那一邊成正比，
`0.40 × 1.22 ≈ 0.49`）。

⚠ **改完當場被另一條測試抓到。** `test_ui_layout_modes` 那條真的去量座標，
它發現儀表整塊掉到設定區下面去了 —— 儀表的上緣＝影像的高度，設定區的上緣＝
畫布的高度，**影像佔得比畫布多的那一刻，U8 的「左右相鄰、同一條視線」就碎
了**。所以 `IMAGE_SHARE_TUNE` 跟著 0.50 → 0.45，並補一條便條測試說這兩個數字
是綁在一起的。

⚠ `CANVAS_MIN_PX` **沒有跟著動**：它是小螢幕的最後一道防線，而這一輪問的是
「預設分得夠不夠」，不是「最壞能多壞」。

### C1：數字是那個面板存在的理由

Features 面板的**值**被一段可長可短的說明推到可視範圍外 —— 要橫捲 270 px 才
看得到。一列改成 `名字 | 值 | 單位 | 說明`，說明收在最後、最小寬度 0。

⚠ 名字的寬度是**最小**不是固定：截名字比讓值跳更糟，而名字是使用者要打進
分數表達式的那個字。

### I8：一個比內容小的標題

參數區的段標比它底下的欄位名**小**（`$font_tiny` → `$font_body`）。比內容小
的標題讀起來像註腳，眼睛會從它上面滑過去。

### B3：一行的省略號看不出後面還有多少

卡片說明一行截斷。改成兩行 —— 而 Qt 兩邊都不給：`elidedText` 只認一行，而
`wordWrap=True` 的 QLabel **不會省略**（它會一直長高，把底下的參數推出畫面）。
所以自己折（`fields._wrap_elided`）。

⚠ **切在字之間，不切在字中間**：Qt 硬切的結果看起來像畫面壞掉
（`canvas._draw_elided` 記過同一件事）。⚠ 兩行**不是**「全部都看得到」——
放不下的還是要有省略號，不然被切掉的那半句看起來像作者只寫了半句。

---

## F117 第二批：兩條 ❓ ＋ 用詞與 Results 那兩群（2026-09-20）

一口氣關掉 **14 條**（走查從 13/58 到 27/58，**P1 全關**）。挑法跟第一批一樣：
先驗那兩條 ❓（可能是 bug），再做整群改得動的。

| 群 | 條目 |
|---|---|
| **可能是 bug** | G9、G8 |
| **用詞與符號** | I13、B2、A5、G6、D1、D4 |
| **Results 面板** | E7、I16、I15、E1、E2、E4 |

**E6／I3 沒做**：重現不出來（只有一條 `QToolBar`，看不到走查說的那條灰色
空條），使用者定調「沒重現出來就算了」。

### 兩條 ❓ 查出來都是真的 bug

**G9 —— `QThread: Destroyed while thread is still running`。** `closeEvent`
列了一張**六個** worker 的表，而視窗身上有**八個**：`region_check_worker` 與
`calibrate_worker` 從來沒被停過。那是未定義行為，而且只在那兩個功能真的被
按過的那一次出現 —— 所以平常看不到。**修法不是補名字，是讓那張表不可能再
漏**（`workers.shutdown_window()` 自己去找；測試問「找到的每一個都停了嗎」）。

**G8 —— 走查記的是比較不危險的那一件。** 「空白」是還沒跑試跑；而更危險的
是：圖的視窗只有 `Charts folder` 餵得動，`_refresh_charts_window` 對別的
inspector **安靜地 return** —— 於是選了別張卡之後視窗還畫著上一張卡的數字，
而畫面上一個字都沒說。

### 三個「句子本身就是假的」

這一批最值得記的不是修了幾條，是**走查說「句子是對的」的地方有三個並不對**：

1. **D1**：`press Esc to run the decision too` —— `Esc` 只放掉**畫布**那一份
   選取，而預覽停在哪裡看的是 `win.selected_node`。按了 Esc 框不見了，預覽
   照樣停在同一張卡上。那是一句**承諾了不會發生的事**的提示。
2. **E2**：「色條沒有圖例」—— 圖例一直都在（判定列就在同一個視窗最上面），
   I1 之後兩邊顏色也真的一樣了。缺的是**盯著它不漂**的那條測試。
3. **D4**：「多種叫法」—— 掃過整個畫面**沒有亂用的同義詞**。缺的是沒有任何
   地方說那五個字怎麼串起來。

### 我自己種的三個安靜的錯（都被抓到了）

* **A5 的第一版是空的**：寫成 `getattr(self, "canvas", ...)`，而那個屬性叫
  `pipeline` —— `getattr` 的預設把它吞掉，那一版**永遠回 False**，而沒有任何
  測試會紅。補了一條真的問「兩種狀態講不同的話」的測試。
* **D4 那條掃描的第一版是綠的、而且是假的**：regex 的「字界」符號在編輯的路上被吃成一個
  backspace 字元，regex 永遠不會 match。現在配著一條反向測試。
* **E2 的探針量錯對象**：叫的是 core 那一份 `verdict_rows`，量出「兩邊顏色
  不一樣」—— 而真正在畫面上跑的是 UI 那一份（它會補主題那兩個顏色）。
  **量錯對象的探針會給出一個很有說服力的錯誤答案。**

### 兩支新模組（都進了 `ARCHITECTURE.md` 的樹）

* `ui/geometry.py` —— 子視窗記得上次多大、在哪。⚠ 還原完一定過一次
  `keep_on_screen`（拔掉第二個螢幕之後，存下來的位置會落在沒有螢幕的地方，
  而那是一個按了沒反應的按鈕）；⚠ 它是**第四個會寫磁碟的東西**，所以照
  CLAUDE.md §4 先做出覆寫點。
* `ui/frozen_column.py` —— 表格第一欄不跟著橫捲走（Qt 官方那個做法）。
  ⚠ 共用 model **與 selection model**；⚠ 主表那一欄照樣留著不藏；
  ⚠ 接法是包住 `resizeEvent`，不是叫呼叫端記得呼叫 `sync()`。

### 三把尺

`studio.py` 4,347（沒有超過那格 HARD_CAP —— D1 的內容因此住在
`studio_layout`，那裡才是接線的家）。`_AXIS_LABEL_ALLOWLIST` 的 histogram
從 2 **降到 1** —— 例外清單的數字掉下去也要跟著改。

---

## F117 F2：報表講得出「這是哪一次跑的」（2026-09-20）

走查記的原話：**「檔案一離開電腦就追不回是哪一次跑的」。** `report.html` 以前
只有 recipe id 與 bin 計數 —— 沒有日期、沒有來源 KLARF、沒有 d4t 的版本／
build id，也看不出這一批是不是只跑了一部分。報表頭現在是：

```
Run at       2026-09-20 14:33
Source       D:/lots/LOT.001/defects.001
Defects      60 of 6000 (not the whole lot)
Recipe file  ebi_die_to_die (format v5)
Made with    d4t 0.1.0.dev0 (build ac9092788c9e)
```

**HTML 與 xlsx 同源**（`export/report.run_info()`）—— 各算一份的那天，它們會
對同一次跑講出兩個答案，而沒有人知道哪一個是對的。

### 三件寫進去的判斷

**一、「跑了幾顆」不是一個數字，是一句話。** 一份只跑了 60 顆的報表看起來跟
跑完 6 萬顆的一模一樣，而使用者拿它去講「這個 lot 的情況」—— 那是這個工具
最容易誤導人的地方。跑完整批就只印數字（每一份都掛一句「not the whole lot」
的話，那句話就沒有人看了）。

**二、算不出來的那一列不寫**（不是空字串、不是 `unknown`）。一列寫著
`Source: unknown` 比沒有那一列更像「我知道，只是弄丟了」。

**三、`d4t export` 蓋的是那一次跑的時間，不是現在**（從批次歷史的
`created_utc`）。對一份三個月前的 run 蓋上今天的日期，比沒有日期更糟。順手
查出那條路徑**連 `recipe=` 都沒傳** —— CLI 匯出的 xlsx 以前連 recipe 那一段
都沒有。

順手關掉 **F6 的前半**：報表標題從「recipe id」改成「使用者打的字 → recipe
的描述 → recipe id」。`recipe_id` 是 JSON 的鍵（`ebi_die_to_die`），不是一份
報表的標題。F6 剩下「表格太寬」那一半（數字那一半 I5 已經做完）。

⚠ `test_export_parity` 那條「卡片產的 == 直接叫引擎產的」**放寬了一格**：
卡片手上有 `BatchContext`，引擎沒有，所以卡片那一份多一段 `This run`。
放寬的同時補了一條反向的（`test_the_card_stamps_which_run_this_was`）——
拿掉一段再比，等於對那一段完全不問。

**F117 的 P1 到此全部關掉。**

---

## F119：哪一個 bin 是好消息（2026-09-20）

走查（F117 D2）記的是「均勻度那份 recipe 的判定膠囊 `measured · bin 0` 是
紅的，讀起來像壞掉」。查下去**三份出貨的 recipe 全反**：

| recipe | 膠囊上的字 | 改之前 |
|---|---|---|
| `ebi-die-to-die` | nothing stands out（沒找到缺陷）| **紅** |
| | a spot stands out（找到缺陷了）| **綠** |
| `one-image-uniformity` | measured（量到了、沒異常）| **紅** |
| `rsem-worst-box` | more than one box is off（更嚴重）| **灰** |

病根一句話：**膠囊的顏色是看 bin 的號碼決定的，寫死在程式裡** ——
`bin 1` 綠、`bin 0` 紅、其他灰，而它從來沒問過 recipe 那個號碼是什麼意思。
走查只抓到均勻度那一條，因為那一條的字跟顏色矛盾得最刺眼；另外兩份剛好
「找到缺陷 = 綠」，看起來像在慶祝，沒有人會停下來想那是錯的。

使用者選「甲：寫 recipe 的人自己標」。五步都做完了，計畫書
[`docs/history/plans/F119-which-bin-is-good-news.md`](docs/history/plans/F119-which-bin-is-good-news.md)。

### 四件記下來的事

**一、畫面上有兩套顏色，問的是不同的問題。** 身分色（`leaf_color`：這是哪
一類）是對的，判斷色（好消息還是壞消息）才是壞的。**不准把 `outcome` 塞進
`leaf_color`** —— 合起來的話，三類都是好消息的 recipe 在畫布上會變成三個
一樣的綠，而使用者就分不出那三類了。I1 剛學到的是另一個方向的同一課。

**二、沒標 = 灰，不准猜。** 今天的行為是「**很有把握地給一個錯的顏色**」，
而那比沒有顏色糟得多：使用者會相信它。特別擋掉「bin 0 一律是好消息」那種
補丁 —— `rsem-worst-box` 的 bin 2（更多格不對）比 bin 1 更嚴重，**任何按
號碼排的規則都答不出來**。

**三、不需要遷移，而這件事要寫出來。** 鐵則 9 的反面：沒有舊欄位可看，而
`""` 對新舊檔案的意思相同（都是「還沒說」）。所以 `RECIPE_VERSION` 不動、
空字串不寫進 JSON、沒標的 recipe 存出來一個位元組都沒變 —— 有一條測試就是
那句話的證據。

**四、「還沒說」刻意不做成一條 lint**（對自己計畫書 §6 的修正）。去做的時候
量到它會踩壞 `test_the_reference_recipes_stay_completely_clean`（那兩份參考
檔案就是沒標的），而那條鎖的「每一份正常的 recipe 一條訊息都沒有」是一個
**有人選過的不變量**。「還沒說」改成講在判定樹的托盤上，就在那一排膠囊旁邊
—— 那裡是使用者真的會去改它的地方。

### 順手查出來、順手修掉的

* **`is_real_style` 是一條死路**（U13 那個紅綠對調的旗標從來沒有呼叫端）。
  刪掉了，但 U13 買到的**三個通道一個都沒少**：顏色、字（`good` / `review`）、
  框線樣式，三條吃同一個 `outcome`。⚠ 是 `review` 不是 `bad` —— 廠內對
  「這一顆要人看一眼」講的就是 review，而 `bad` 讀起來像在罵那片晶圓。
* **打勾是畫出來的，不是字**：新的三張小圖走 `glyphs.py` 的向量路線
  （F7-23 擋的是拿 `✓`／`✕` 當圖示 —— 廠內的 Segoe UI 蓋不到那一族）。
* `bin_labels` / `bin_outcomes` 與兩條新 lint 的走訪**收成一支 `entries()`**
  —— 四個地方各走一次的那天，它們對「哪一片葉子排在前面」會有四個答案，
  而「第一個贏」整條規則就是靠那個順序。

天花板：`recipe.py` 4,342 → 4,471（三次，每次都簽了理由）；
**`studio.py` 4,347 → 4,345（−2）**。

---

## F118：使用者面的字 —— 訊息不准講開發者的話（2026-09-19）

F117 走查的 **J1／I11／J5／J6 是同一個病根**：內部識別碼漏到使用者面。
真的跑出來的那一句（把分數表達式寫成 `glv_max + nosuch_feature`）：

```
route 'ebi_patch': the variables ['nosuch_feature'] are not among the features
this route produces (['cd_axis_deg', 'cd_bright', … 還有 20 幾個 …])
```

現在是 `“nosuch_feature” — Check the spelling, or add the card that
measures it - the score may not be computable at run time.`

設計與五個步驟在
[`docs/history/plans/F118-user-facing-wording.md`](docs/history/plans/F118-user-facing-wording.md)
（做完了，所以搬進 history）。**四條都關掉了。**

| 步 | 做了什麼 |
|---|---|
| 1 | `d4t/ui/wording.py`（Qt-free）：`card` / `card_of_step` / `field` / `name_list` / `trace_error_text` / `step_error_text`，接四個呼叫端 |
| 2 | `Issue` 加**選配**欄位（預設空）＋ `issue_line()`：有結構就用、沒有就退回 `detail`。接上 Problems 列、畫布警示點、判定徽章、兩句「不能跑」 |
| 3 | 最常出現的六條 lint 交結構；core 多 `card_name()` 與 `closest()` |
| 4 | 問題清單兩行（結論／細節）、換行不橫捲、常駐一句「點一列會跳到那張卡」 |
| 5 | 掃完剩下的 41 個產地：**27 個填了、14 個量出來不需要填** ＋ 一條擋回頭的測試 |

### 這一輪學到的三件事

**一、`Issue` 有兩個，不是一個。** 設計文件寫「63 個產地」，實際是 **48**
—— `klarf_core.Issue` 是另一個 class（欄位不同、不經過 Problems 列），它那
15 個是 KLARF 健檢的結果，不在這個題目裡。**數字要自己數一次**。

**二、畫面只該拿它才答得出來的那幾件。** 第一版做了一個 `nodes` 欄位讓畫面
把 node id 翻成卡片名，結果是 `“A” · “B”` 這種**沒有動詞**的句子：那兩張卡
之間是什麼關係每一條 lint 都不一樣，通用的組句器造不出那個動詞。收回 core
（`Step.label` 本來就住在那裡，而 CLI 的讀者一樣讀不懂 `'dn'`）。畫面留著的
只有兩件：**這份 recipe 有幾條 route**（單 route 就不要講）、**一串名字列到
第幾個就夠**（CLI 要全部）—— 跟 `numbers.py` 那條界線一模一樣。

**三、`detail` 不能直接接在結構後面。** 它正是把同樣這些東西攤平成一句話的
版本，接上去那一行會**同時**有「“nosuch_feature”」跟「the variables
nosuch_feature are not among…」。所以多一個 `advice`（那句「所以你該怎麼
辦」），**兩邊共用同一個字串**，話只寫一次。

§5 估的「84 條文字斷言」**實際只動到 8 條**，而且四條都變成更好的斷言：
從句子裡剖字（`i.title.split("'")[1]`）改成讀 `i.names[0]`、從斷言 node id
在句子裡改成斷言卡片名 ＋ `node_id` 指著哪一張。剩下的落在第 1 類 ——
`detail` 照舊是一句完整的話，只是裡面不再有 node id 與 Python 的 repr。

**四、48 條不是都要填 —— 而「不填」要有測試說出來。** 第 5 步掃完：
**34 個交結構、14 個量出來本來就乾淨**（判定段的語法錯、卡片自己的「還沒設定
完」、分數表達式 parse 不過）。對它們填欄位買不到任何東西，`issue_line()` 退回
`detail` 就是對的答案。所以這一輪**沒有把 48 填滿，而那是刻意的**。

### 真正買到的是一條不准回頭的關

`test_no_lint_writes_an_internal_id_into_its_sentence` 掃 `recipe.py` 每一個
`Issue(...)`，把 node id 插進句子就紅。**白名單是空的**：`card_name()` 一行就
答得出卡片叫什麼，所以那個動作沒有正當理由。唯一非印 node id 不可的那一條
（`unknown-node`：那張卡根本不在 `recipe.nodes` 裡）寫成 `"…'%s'" % (k, nid)`
並留一句為什麼 —— **多打幾個字正是重點**，它讓「我是故意的」在 review 看得見。
配一條反向的（`test_the_lints_that_carry_no_structure_are_the_plain_ones`）：
哪天有人機械地把欄位填滿，那一條會紅。

順手修掉的三個真 bug：`decide.let[3]`（程式裡的路徑，面板上那幾行是從 1 數
的）、「“GLV” first, then “GLV”」（兩張同型別的卡等於沒講）、
`%s take input from it`（一張卡要是 `takes`）。

守門：`tests/test_ui_wording.py`（`issue_line()` 對**每一個** `code` 都給得出
一句話，名冊是 ast 從 `recipe.py` 數出來的；唯一一個轉手 `Step.kind_issues`
的地方寫死成 1，第二個出現時會紅）。天花板：`recipe.py` 4,101 → 4,342，
`studio.py` **沒變**（4,347，`HARD_CAPS` 只准往下 —— 三處都一行換一行）。

---

## F117 第一批：UI 走查的「一改多條」那幾群（2026-09-19）

走查文件 [`docs/plans/F117-ui-review.md`](docs/plans/F117-ui-review.md) 有 57 條
live item，但 **P1/P2/P3 不是它真正的結構** —— 很多條是同一個病灶的不同症狀。
這一批挑的是**根因群**：四個改動關掉 8 條，而且用的全是 repo 裡已經有的機制。

| 改動 | 關掉的條目 |
|---|---|
| `canvas.ensure_card_visible()`／`select_card()` | A3、J2 |
| `gallery.bin_hex()` 走 `decide_tree.leaf_color` | I1 |
| 數字規則搬進 `d4t/core/numbers.py`，畫面與 HTML 報表共用 | F6、I5 |
| 歡迎頁不再列資料種類、數量改成數出來的 | G1 |
| `detail_feature_keys()` —— 明細表扣掉 `BASE_COLUMNS` | F1 |

中文化（H5）這一批**不碰**（使用者決定：要先有 2–3 位目標使用者試用）。

### 走查寫的跟查出來的不一樣：三條

**D2 不是 I1 的同一個病根**（走查推測「改用 `leaf_color` 後應一併解決」）。
`VerdictChip` 是**二元 pass/fail**，而那是 U13 刻意的設計：`is_real_style` 會把
紅綠對調，**對調時 chip 自己的字跟著翻面**（`real`／`nuisance`），還有第三個通道
（框線樣式）給色覺缺陷者。改成 `leaf_color` 會把那整套拆掉。真正的問題是語意 ——
均勻度那份 recipe 裡 `bin 0` 是好消息。**待使用者決定**：「哪個 bin 是好消息」
該由誰說。

**D3 撤回。** `score 0.27895` **本來就走** `numbers.py` —— 那 5 位是 F52 算過的：
`%.4g` 會把 `99.995` 印成 `100`。縮短它等於把 F52 修掉的 bug 放回來。
教訓：**「看起來太長」不等於「沒走共用的那一支」**。

**F6 比走查記的更深。** `core/export/html.py` 的 `number()` 用的正是 F52 否決掉的
`%.4g` —— 除了 `1.638e+04`，它還讓 `99.995` 在報表上變成 `100`。**沒有人回報過**，
因為它躲在報表裡。F52 把畫面的六份收成一份，而**報表是第七份**。

同一種形狀還有兩個：G1 的歡迎頁是 `InputSource` 那張表想消滅的**第三份拷貝**
（而它從來沒被改成從表上長，所以 F114 拿掉 stack 之後它還在介紹一種打不開的
東西，連「three kinds」「four kinds」兩個數字也是錯的）；F1 的欄名重複**三個
輸出檔都有**，不只走查記的 CSV。

### 兩次被天花板擋下來，兩次都擋對了

`CLAUDE.md` 那一格擋下 +16 行、`studio.py` 那一格擋下 **+1** 行 —— 兩次都是
**我把故事寫進了規則的位置**。後者更有意思：`studio.py` 在 `HARD_CAPS` 裡，
**簽名這條路不存在**，只能「先從它手上搬走等量的東西」。照做之後得到的是
`canvas.select_card()`（選一張卡在畫布上是**一件事**：畫成選中、清掉樹的選取、
捲進視野），`studio.py` 三行變一行 —— **比動手之前還低**。

天花板在替人分辨「規則」與「故事」，而那比它擋住的行數值錢。

---

## F116：拆 `studio.py` —— 六步走完（2026-09-19）

`CLAUDE.md` §4 早就寫著「`studio.py` 留給接線，不留給內容」，而 `HARD_CAPS` 讓那
一格只准往下。F110／F114 各往下搬過一小塊，證明路走得通；這一輪照
[`docs/history/plans/F116-split-studio.md`](docs/history/plans/F116-split-studio.md)
把它**有計畫地走完**，一步一個 commit、一步一次全套驗收。

| | 起點 | 六步之後 |
|---|---|---|
| `d4t/ui/studio.py` | 7,686 行 | **4,347**（−3,339，**−43%**）|
| `StudioWindow` 方法 | 293 | **197**（−96）|
| `StudioWindow` 的 `self.*` | 433 | **266**（−167）|

| 步 | 搬的是什麼 | 去哪 |
|---|---|---|
| 1a／1b／1c | 右下角的卡片儀表 ＋ 特徵表；影像流選擇與畫在圖上的東西；區域跨顆檢視 | `gauge_panel.py`、`preview_overlays.py`、**既有的** `region_check.py` |
| 2 | 介面組裝（工具列、主體三欄、預覽區、進度列、快捷鍵） | `studio_layout.py` |
| 3 | Gallery／Results／回溯 ＋ 縮圖那一條鏈 | `gallery_controller.py` |
| 4 | 掛第二份東西（第二份 lot ＋ GLAS 匯出）；recipe 的開／存 | `attach_sources.py`、**既有的** `open_dialogs.py` |
| 5 | 怎麼發動一次執行、怎麼把結果寫出去（鐵則 11 整條） | `run_controller.py` |
| 6 | 畫布上拉一條線／剪一條線在 model 上是什麼意思（鐵則 10 主場） | `canvas_edges.py` |

`studio.py` 現在只剩**組裝、`model → UI`、signal 接線、狀態列、門面**。

### 三次跟計畫書不一樣，每一次都是量完才改的

**1b：`feature_pane.py` 沒有出現。** 判準是「>600 行就分」，搬之前量是 609 行剛好
踩線 —— 回頭問「先問那一塊該不該是一塊」，答案是**照畫面上的位置分，不是照行數
分**：跨顆檢視那顆按鈕住在預覽區，而它用的每一個東西本來就在 `region_check.py`
裡。所以**少開**了一個模組。

**5：計畫說發 signal，量完之後沒有發。** 讀完 `_apply_trial_results` 那 115 行之後
前提不成立 —— **那不是一串可以搬出來的 refresh**，它跟「這批數字怎麼變成一句話」
「要不要寫出去」是交織的，每一段前面都釘著一句「順序反過來就會畫出上一批的
顏色」。刀改切在別處：**`_apply_trial_results` 留在視窗**，controller 只留「怎麼
發動、怎麼寫」，往外因此只剩**一個**呼叫 —— 那正是計畫想用 signal 換到的東西。
連那一個也沒做成 signal：Qt 的 direct connection 雖然同步，**例外會被 Qt 的 hook
吃掉**，而測試大量用 `run_trial(sync=True)` 靠例外當場紅。

**6：計畫猜「本質上就是接線」，量出來 65% 是規則**（437 行裡六支規則型的方法佔
284 行，handler 只有 67 行）。而計畫把它列為最危險（191 處引用）—— **反了**。

### 六步下來真正學到的一課

**測試密度是安全係數，不是風險係數。** 這一輪真正咬人的全是**沒有測試按過的那顆
鈕**：第 4 步用字串拼出來的 `_on_open_gds` 分派、第 3 步 `region_check.py` 那兩行
接線 —— ruff 綠、import 綠、`--check` 綠，只有使用者真的按下去才炸。而
`_on_edge_added` 有 191 處／21 個測試檔，每個錯誤都當場紅。

搬家沒有新邏輯，所以 bug 只有一種形狀：**import 過、開得起來、在一條沒有人走過的
路上才炸**。踩到六種，清單在計畫書 §6：① 單獨當參數傳出去的 `self`（controller 是
QObject 不是 QWidget）② `@property` 掉在原地（`ast` 的 `lineno` 指著 `def`）
③ 字串形式的 `monkeypatch.setattr` ④ 門面的簽章憑印象寫 ⑤ **別的 UI 模組還在叫那個
名字**（接線，測試大多不會碰）⑥ **組出來的名字**（`getattr(self, "_on_open_%s" % k)`，
任何掃描都找不到）。

新工具 `tools/studio_surface.py` 守得住 ①③⑤，三輪演進每一次都是被一個真的漏掉的
東西逼出來的。它在第 4 步**第一次派上用場就賺回自己**：在跑任何測試之前就列出
`studio_layout.py` 那 5 行還在叫 `win._on_save_recipe`。

### ⚠ 家用機上的黃金值：`align_score` 那一格

前置檢查一跑就紅，而**不是行為變了** —— 判準、證據與做法寫進
[`docs/PITFALLS.md`](docs/PITFALLS.md) 了（摘要：`align_dx`/`align_dy` 17 位相同、
下游全部相同、`algo/align.py` 一個位元沒動 ⇒ 剩下的變數只有 OpenCV build）。
repo 裡那三份**沒有動**，基準凍在暫存區，每一步都逐項對過。

### 驗收（每一步都做）

258 個測試檔逐檔跑，紅的 **10 個檔案全部是既有的**（用 git worktree 開一份起點
commit 的樹逐檔對過）；第 6 步另外單獨跑那 21 個引用 `_on_edge_added` 的檔案全綠；
鐵則 11 的兩支守門 15 條全綠。**每一步都真的開一次 Studio 走過那一塊**，最後長到
**41 條**檢查，而且是「在起點的樹上跑同一支、`diff` 空的」那種驗收 ——
「測試全綠而畫面壞掉」是這種搬家最常見的死法。

### 計畫書的兩個結論改掉了

* **§8 的「≤ 4,000 行」沒有達成（4,347），而那個數字要重估**：剩下的裡面有 927 行
  是 `model → UI`（計畫書 §2 自己寫的「這就是接線本身」）。建議改成
  「`model → UI` 以外沒有一段超過 300 行」—— 那是這六步真正在守的東西，現在成立。
* **§5 的 `StudioState` 評估完了：不做。** 六步下來因為 `self.w.<名字>` 出過的錯是
  **0 次**；真正出錯的都是「名字搬走之後沒人跟上」，那是接線，`StudioState` 一條都
  擋不到。

### 順手修掉的一個（獨立 commit，不屬於 F116）

`tools/doctor.py` 的子行程沒設 `QT_ASSUME_STDERR_HAS_CONSOLE` —— Qt 開不了 platform
plugin 是 fatal，而 **Windows 上的 fatal 預設是一個跳出來的對話框**。那條故意用
不存在 platform 的測試因此每跑一次就在家用機上留一個按不完的視窗，而那一項還要等滿
timeout（修完 7 秒）。這是 `CLAUDE.md` §4 F91「會跳 modal 的東西要有一個關得掉的
旗標」的**子行程版**。

## F115：OP-301 廠外驗證的結果 —— noise、區域型態、以及 16→8 bit（2026-09-18）

使用者在一個隔離環境裡拿**兩批真實機台檔**（23 張，每張帶著機台自己算的 F.I.
真值）跑了一次 d4t 的 CLI，回來一份驗證報告。這一輪把那份報告裡**能落成程式碼
與文件的部分**做掉。計畫書（含兩處刻意跟提案不一樣的地方）直接進封存：
[`docs/history/plans/F115-iqi-external-validation.md`](docs/history/plans/F115-iqi-external-validation.md)。

⚠ **那些影像不能進 repo，這台機器上也沒有它們。** 所以這一輪的紀律是：報告裡
每一個相關係數都當成**唯讀的事實**照抄進文件（不四捨五入、不改好看），而**每一行
新程式碼的驗收都是合成資料**。重驗只有資料的擁有者做得到。

### 量到的三件事（完整那一份在 [`docs/USING-FOCUS.md`](docs/USING-FOCUS.md)）

| | logic 區的那台 | 重複 array 區的那台 |
|---|---|---|
| 現在的預設（`noise=0`、`cutoff=10`、8×8、前 30%）| Pearson **r = 0.959**、Spearman 0.989 | 整份參數網格最高 **0.31** |
| `noise` 開到 20 | r **崩到 0.06** —— 那一區的高頻是**真的訊號** | — |
| 取高 8 位 vs 逐張拉伸 | 0.96 vs 0.78（取高位贏）| **0.03** vs 0.31（拉伸贏；像素只用到滿量程的 77%）|
| 四個銳利度指標 | 0.918 ～ 0.959，四個都好 | 四個都 ≤ 0.444 |

**第三件事最反直覺：16→8 bit 怎麼降，比挑哪一個指標更要緊。** 同一個
`focus_tenengrad` 在對的降位法下是 0.92，換成逐張拉伸是 **0.008**。

### 落成了什麼

1. **`iqi.py` 的兩個 ASSUMPTION 有實測答案了。** `noise_percent` 是一格**站點
   參數**（logic 區要留 0）；而「前 30% 取平均」與「梯度預篩」在 array 區
   **兩個都是 no-op** —— 64 塊長得一模一樣，把留下來的塊數從 19 掃到 40 相關
   係數一動都不動。**那不是 bug，是前提不成立**（順帶結掉了規格「前 30」與
   「前 30%」的措辭歧義：兩種讀法沒有差別）。
2. **`focus_quality` 多一格 `Measure on`**（`The image` / `Its edges`，預設不動）。
   它是**岔路不是 method**：問的是你的樣品是 array 還是 logic，不是問軟體用哪個
   公式。array 區 0.31 → 0.49（那台機台上的局部最好），logic 區 0.9593 → 0.9596
   （沒有變差）。⚠ **0.49 不是可以出貨的相關**，它是一個起點。
3. **`.raw` 先讀檔頭再猜大小。** 那個格式的 64 KiB 檔頭開頭四個 LE u16 就是
   `W, 0, H, 0`，而 `65536 + 3584² × 2 = 25,755,648` 逐位元組吻合。三道關全過才
   當真（簽名、邊長範圍、大小相符），過不了就退回原本那條猜大小的路。
4. **校正流程寫成文件，而且不必加卡**：`GT = a × FI + b` 擬合完，兩個常數寫進
   判定面板的 `Working numbers` 一行就好（分數表達式本來就吃乘法與常數）。
   ⚠ **常數與設定都不跨機台**：把一台的原封不動套到另一台，量到的 r 是 **0.03**。

### 兩處刻意跟提案不一樣（理由寫在程式碼裡）

* **梯度不拉 `cv2.Sobel`**：`pattern_density` 本來就在算同一張梯度圖，抽成
  `gradient_magnitude()` 兩個下游共用 —— 同一個模組裡兩個「梯度」遲早會不一樣。
  代價講出來了：廠外那 0.49 / 0.9596 量的是**另外兩個變體**，所以**出貨這條路
  在真資料上還沒有人量過**（`USING-FOCUS.md` §2 有這句話）。
* **合成產生器放 `tests/iqi_fixtures.py`**，不放 `tests/fixtures/` —— 後者是
  資料，共用工具的家是 `tests/region_cards.py` 那個位置。

### 還沒問到的那一句話（**這一輪最重要的產出**）

> **機台 A 的 F.I. 是在哪一個影像階段算的？它的正規化會不會跟同一批的其他張
> 有關？**

只有機台方答得出來，而答案可能會把 array 區那條路整條換掉。在那之前
**不要再盲調參數、不要為那一種區域另外加一張量測卡**。

---

## F114-3：文件收尾 —— 這幾輪的改動在 md 上留下的漂移（2026-09-18）

使用者：「整理相關 md 檔案後 merge 回 Main」。合併前把 F109～F114-2 在文件上
留下的**每一處對不上**掃掉。

### 掃出來的（全部是「數字或名字已經不是現在這樣」）

| 哪 | 說的 | 現在 |
|---|---|---|
| `docs/ARCHITECTURE.md` | `dataset.py` = **五種** source | 四種（`tiff_stack` F114 拿掉）|
| `docs/ARCHITECTURE.md` | `open_dialogs.py` = **五顆** Open | 三顆（F114-2）|
| `docs/ARCHITECTURE.md` | docs 樹少畫 `USING-UNIFORMITY.md` | **這一份從來沒被畫上去過** |
| `docs/USING-UNIFORMITY.md`／`USING-SIMGEN.md` | `Open image…` | `Open images…` |
| `docs/ROADMAP.md` Input 那列 | `tiff_stack` 做齊了 | 補一句「F114 從產品面拿掉」|
| `scope.py`／`dataset.py`／兩支測試 | 「不是**第五種** source／kind」 | 改成不帶數字 |

⚠ **有數字的句子分兩種，只改其中一種**：講**現在**的（「五種 source」）要改；
講**那一天**的（F110 的「第五種 kind 出現時…」、`test_size_ceilings` 裡
「第五顆 Open 鈕要加，所以先搬走等量的東西」）是**紀錄**，一個字都不動。

### `docs/plans/` 空了，資料夾也拿掉了

`docs/plans/F11-phase2-features.md` 的檔頭寫著**狀態：七段裡六段已收斂，
只剩 Compare**，而 Compare **2026-09-18（F110）收掉了** —— 那一份自己的字
就寫著「這一份不搬進封存正是因為那前一半還在用。**Phase 2 收斂的那天連同它
一起搬**」。那一天到了，所以它搬進 `docs/history/plans/`。

搬完 `docs/plans/` 是空的 —— `test_plan_docs::test_there_are_plans_or_the_folder_is_gone`
要的正是「有計畫書，或資料夾不在」（空資料夾會讓底下兩條變成「什麼都沒測
而且是綠的」），所以資料夾一起拿掉。下一個新功能照 `CLAUDE.md` §4 開回來就好。

跟著要動的四處：`docs/ROADMAP.md` 與 `docs/FAB-VALIDATION.md`（兩處）指向舊位置
的連結、`docs/history/README.md` 的「只剩一份活的」那句話與新的一列、
以及**搬過去那一份自己的相對連結**（從 `docs/plans/` 到 `docs/history/plans/`
深了一層，`../GLAS-INTERFACE.md` 這種要變成 `../../`）——
`tests/test_docs_links.py` 兩邊都抓得出來，這一輪就是它抓的。

## F114-2：五顆入口併成三顆（2026-09-18）

使用者：「目前的 input 入口搞得我很亂（**user 可能會被嚇掉**）…可否整合?」
→ 看完我列的表之後定調：**「入口整合成 3 顆」**。

### 判準：使用者答不答得出那個問題

五顆變三顆，併掉的是 `folder` / `image` / `raw`。它們**本來就是同一種 kind**
（`folder`）—— 只差在「一個檔還是一疊檔」與「byte 要怎麼變成像素」，而那兩件事
**看一眼那條路徑就知道**。**看得出來的事不該拿去問人**（推廣鐵則），而在這之前
使用者得在**還沒看到資料之前**先回答它。

沒併的兩顆是因為**看不出來**：

* `Open KLARF…` 服務兩種 kind，而 patch 與一顆一張的差別寫在 KLARF 裡
  （`Images N { … }`）—— 拆成兩顆等於要使用者回答一個檔案已經回答了的問題。
* `Open conditions…` 與 `Open images…` 都可以指向一個目錄，而**選錯不會報錯**：
  `folder` 會把每一個 condition 當成一顆 defect，得到一批看起來完全正常的
  錯資料。那種時候多一顆鈕是便宜的。

```
Open KLARF…      ebi_patch / rsem     形狀由 KLARF 自己講
Open images…     folder               資料夾**或**單一檔案，.raw 也在這裡
Open conditions… doe_folder           資料夾裡還有資料夾
```

### 併得起來的關鍵：Qt 的一個組合

本來以為「選檔案」與「選資料夾」在 Qt 是兩個對話框（`getOpenFileName` /
`getExistingDirectory`），所以一顆鈕吃兩種形狀做不到。**實際量過**：
`FileMode.Directory` **加上 `ShowDirsOnly` 關掉**（再配 `DontUseNativeDialog`）
的組合裡，`selectedFiles()` **檔案與目錄都回得出來**。所以 `ask_images` 是
一個對話框、回一條路徑，分岔在 `_open_picked` 看那條路徑。

⚠ **原生對話框不行**：各平台的原生目錄選擇器只給目錄，那正是要擺脫的限制。

### 那條規則現在有兩份實作，所以釘了一條測試

「是哪一種看路徑就知道」這件事，CLI 的 `__main__._open_input` 早就在做了 ——
於是同一條規則有了 UI 與 CLI 兩份實作，而兩份實作一定會漂（§0 第一句話）。
`test_the_one_button_that_takes_a_file_or_a_folder_routes_like_the_cli` 把兩邊
釘在一起，釘的是最容易漂的那一格：**`.raw` 認不認得**（它解不開，所以不在
`dataset._IMAGE_EXTS` 裡，兩邊都得自己多問一次；少問的那一邊會把 `.raw` 當成
「沒有影像的資料夾」而給出一個空的 lot）。**咬合驗過**：把「指到一個 `.raw`
檔」那一行改成 `return None`，它當場紅。

### 又一次：把具體對象抄進測試裡

`test_the_image_entry_is_on_the_one_table_that_grows_the_buttons` 寫死
`key == "image"`，併完當場紅 —— 而壞掉的不是「入口從一張表長出來」這個機制。
改成 `test_every_entry_is_on_the_one_table_...`：表上**每一個** entry 都要
kinds 被支援、有標題與說明、`open_source` 認得、圖示各不相同。
**這是這幾輪第四次付同一筆錢**（F109 `test_ui_scope_profiles`、F114 的
`test_all_four_kinds_are_supported` 與 `test_steps` 那一條）。

### 兩個字形變成沒人用的

`stack`（F114 拿掉入口）與 `raw`（這一輪併掉入口）現在沒有任何 `icon=` 指到
它們。**留著並在旁邊寫清楚為什麼**：畫一個字形的成本在「想清楚它跟隔壁那顆
怎麼分辨」，不在那幾行 —— 而 `folder_stack` 的說明正是拿這兩個當對照。
順手修掉那一帶**數字已經不對**的註解（「六顆 Open 並排」「五顆 Open 並排」）。

⚠ `CLAUDE.md` 的行數天花板擋了一次（324 > 323）。**這一輪是在拿掉東西，
那一份不該變長** —— 所以是把我加的註解縮回去，不是把上限調高。

## F114：Align 的格子變成人話、DOE 的 recipe 刪掉、stack 拿掉、載入卡改名（2026-09-18）

使用者四句話，四件事。

### 1. 「目前 DOE 的 rcp 要怎麼操作?」→ check 出三個問題

回頭驗一次操作流程，撞到三件**文件與畫面對不起來**的事：

* **Align 卡的每一格在畫面上都是 recipe 的鍵，不是人話。** 全庫 8 個沒有
  `label` 的參數裡，**5 個在 `align` 上** —— 使用者看到的是 `streams`、`fixed`、
  `method`、`search_radius`、`suffix`。`CLAUDE.md` §3 寫著「參數名是 recipe 的鍵，
  不是給人看的字 —— 顯示用 `label`」，而 F109 重寫這張卡時沒補。
  補成 `Line these up` / `…on this one` / `Find the shift by` /
  `Largest shift to expect` / `Add to the names`（`…` 開頭那個接續式是
  ROI 卡 `…and every other one is` 的既有慣例）。
* **`recipes/README.md` 指了一個畫面上不存在的欄位名**（`Line these up on`）——
  那句話是從卡片的 `help` 第一句抄來的。隨第 2 件一起走了。
* **ROI 的 `Find them by` 說明停在只有兩個選項的年代**（開頭 "Both answer the
  same question"，但現在有三個，而那句話描述的兩個不含 DOE 走的
  `a cell I mark myself`）。**這一件沒動** —— 使用者選的範圍只有第一件。

### 2. 「出貨的那隻 rcp 你先幫我刪掉好了，我自己先接好再丟上來給你」

`recipes/doe-conditions.json` 刪掉，**出貨的 recipe 四份回到三份**。

刪的理由是使用者的：出貨的那一份要從**真的資料**長出來。F112 那一份的模板與
兩個框是從 `tools/make_doe_sample.py` 的範例資料來的 —— 拿去套真資料的第一件事
就是整組重畫，那它作為「出貨」的價值只剩下接線的形狀。

⚠ **跟著走的與留著的**：四條 F112 的行為測試隨那份檔案一起刪（它們斷言的是
那份檔案）；`tools/make_doe_sample.py`、`tests/test_doe_folder.py`、`doe_folder`
這條 kind、`snr_px` 這個 metric **一個都沒動** —— 刪掉的是那一份接線，不是那條路。

### 3. 「stack 功能請幫我拿掉 我們用不到」

`tiff_stack` 從**產品面**拿掉：`scope.SUPPORTED_KINDS` 與 `INPUT_SOURCES` 各少
一格，`ask_stack`／`open_source` 的分岔／`OPENABLE`／`StudioWindow.load_stack_path`
／`DatasetLoadWorker.start_stack`＋`run_sync_stack` 全部拿掉。
**`d4t/core/ingest/dataset.load_tiff_stack` 一個位元都沒動** —— CLI 讀得動，
要回來只是把字串加回那兩張表。六個入口對使用者太多，是同一則訊息的另一半。

`step.PATCH_KINDS` 也拿掉 `tiff_stack`：那兩張表分的是**支援的** kind，
留一個沒人載得進來的字串只會讓 `test_doe_folder` 那條 cross-check 永遠紅。

**兩支測試紅得有道理，而修的是測試本身**：

* `test_ui_input_kinds::test_all_four_kinds_are_supported` 把
  `("ebi_patch","rsem","tiff_stack","folder")` 抄進測試裡了。改成問機制：
  **`SUPPORTED_KINDS` 上的每一種都要 (a) 被認得、(b) 有一個入口打得開它**。
  （`test_ui_scope_profiles.py` F109 付過同一筆錢 —— 把具體對象抄進測試，
  那個對象一被拿掉，紅的理由就跟壞掉的東西無關。）
* `test_i01_companion` 斷言 `len(filters) >= 2`，而少一顆 Open 鈕就只剩一條。
  數量不是重點，改成**還在的每一條都要認得 `.I01`**。

**`test_ui_f11_tiff_stack.py` 沒有刪掉，是改寫。** 它守的三件事裡只有第一件
（「多一顆 `Open stack…`」）是 stack 自己的；另外兩件 ——
**「沒有 KLARF」那句話要常駐在資料集標籤上、不能只在狀態列講一次**（載完就被
"Computing preview…" 蓋掉）與**命名表格的列數來自資料** —— 對
`folder`／`doe_folder`／`raw` 一字不差。改接在 `doe_folder` 上，檔名改成
`tests/test_ui_no_klarf_label.py`。

### 4. 「Load image 改成 Patch、Load images 改成 SEM image、Load layout 改成 layout(GDS)」

⚠ **字面讀起來是反的，所以先問了再改。** 使用者寫「Load image → Patch、
Load images → SEM image」，而現在的兩張卡是 `load_patch`「Load images」
（一顆好幾張）與 `load_single`「Load one image」（一顆一張）。照字面對的話，
**一顆好幾張那張會叫 SEM image、一顆一張那張會叫 Patch** —— 跟兩張卡實際做的事
正好相反。問了，使用者選「按意思對」：

| key | 舊 | 新 |
|---|---|---|
| `load_patch`（一顆好幾張）| `Load images` | **`Patch`** |
| `load_single`（一顆一張）| `Load one image` | **`SEM image`** |
| `load_sidecar` | `Load layout` | **`layout(GDS)`** |
| `pair_source` | `Pair source` | 不變 |

**只改 `label`，代價是零**（`CLAUDE.md` §5 那張表最後一列）：`key`、feature 名、
recipe JSON 一個位元都沒動，舊檔案照開。

**跟著改的是「一張卡的 help 指名另一張卡」那幾句** —— 那是使用者讀完會去卡片庫
裡找的名字，不改就是指向一張不存在的卡（`load.py` 四處、`roi_reference.py`
三處）。`tests/test_card_invariants.py` 有一條正是在守這個（help 裡引號括起來的
卡片名要真的存在），所以它會自己抓。

⚠ **`tests/test_steps.py` 有一條把 `"Load images"` 抄進斷言裡**，改名當場紅。
紅得沒道理 —— 壞掉的不是「錯誤訊息講得出該用哪一張卡」這件事。改成
`get_step("load_patch").label in str(e.value)`：**問機制，不問那一個字串**
（這一輪第三次付同一筆錢，見上面第 3 件）。

歷史紀錄裡的舊名字**一律不動**：`docs/plans/F11-phase2-features.md`、
`studio.py`／`viewmodel.py` 裡逐字引述使用者原話的那幾段 —— 那是「他當時說了什麼」，
改掉就不是紀錄了。

### 三把尺

`studio.py` 那三格**往下**（只准往下的那三格）：行 7,717 → 7,686、
方法 294 → 293、`self.*` 434 → 433。**刪掉東西也要把尺調下來** ——
留著那段餘裕就是留給下一個人偷偷用掉的空間（反向測試在守）。
pyright 停在 128（上限 128），**黃金值三份逐項相同**。

## F113：讀得了 `.raw` —— 第六個入口，一種 kind（2026-09-18）

使用者：「目前讀的圖檔 input 也要能讀取 `.raw` 的原始圖檔」，接著定調
**「你先把它做成新入口好了（16bit image）」**。

### `.raw` 跟別的格式差在哪（為什麼這一支特別）

**`.raw` 裡沒有任何一個 byte 在講寬、高或位元深度。** 它就是一串像素。別的
格式（TIFF／PNG）自己會講，所以 `imageio` 那條路只要「打開、讀」；`.raw`
要多拿三個數字，而那三個數字**只有使用者知道**。

⚠ **猜錯的代價是每一個像素都錯，而且不會報錯**：寬度差一個 pixel，整張圖變成
一條斜線；位元深度猜錯，亮度差 16 倍或 256 倍。所以 `read_raw` 的原則跟
`require_8bit` 一樣 —— **推得出來就建議、推不出來就問，絕不安靜地硬套**：
檔案大小跟版面對不上的時候當場報錯，而且訊息裡直接寫著「讀下去會得到一張斜掉
的圖而不是一個錯誤」。

### 從檔案大小反推：只回正方形的解

使用者給的是 `3584*3584`、`25,755,648 bytes`。算一下：3584² × 2 = 25,690,112，
差 65,536 —— **剛好 64 KiB 檔頭**，而且 16-bit。`guess_layouts` 就是把這個算式
反過來跑：試幾種常見檔頭長度 × 兩種位元深度，看哪一組讓剩下的 byte 數是一個
完全平方數。

**只回正方形是刻意的。** 非正方形有無限多組解（任何一組因數都行），列出來只是
讓使用者在一堆數字裡挑，那不是幫忙。正方形通常只有 0 或 1 個解 —— 有 1 個就是
很強的建議（使用者那個檔案正是唯一解），有 0 個就老實說推不出來、請他填。

### 16→8 bit：整批共用一個位移

整條 pipeline 是 8-bit，而 16-bit 的資料要降下來。這裡**不做逐張拉伸** ——
那正是 `imageio.load_gray` 對非 8-bit 做的事，而 `require_8bit` 的說明逐字寫著
它為什麼是錯的：**每張圖各自拉伸之後，兩張圖之間就不再可比，而「比」是這個
工具的全部。**

所以 `RawSpec.shift` 在**載入的當下決定一次**（量第一張的最大值 →
12-in-16 是 4、滿量程是 8），之後整個資料夾都用同一個。而且**決定了什麼要
講出來**：`load_raw_folder` 會吐一句警告，說它讀成什麼版面、最亮的像素用到
幾位元、因此整批右移了幾位。

### 新的是入口，不是 kind

`load_raw_folder` 回的是 **`kind="folder"`**。`.raw` 跟 PNG 的差別只在「怎麼把
byte 變成像素」，而那件事在 ingest 就做完了 —— 一顆一張、沒有 KLARF、寫不回
KLARF，這些**形狀**跟 `folder` 逐字相同。開第六種 kind 的話
`SINGLE_IMAGE_KINDS`／起手卡／每一條 kind lint 都要多一格，而每一格的答案都會
跟 `folder` 一樣 —— 那是抄第二份出來，而抄出來的那份會漂（§0 的第一句話）。
先例本來就有：`folder` 與 `image` 早就是**兩個入口共用一個 kind**。

所以加的是 `scope.INPUT_SOURCES` 的一列（`CLAUDE.md` §5：「加一列就好」），
分岔在 `open_dialogs.open_source`。CLI 那一面是 `--raw WxH[+header][@bits]`。

### 付掉的兩件事

* **`studio.py` 的天花板又擋了一次**（那三格只准往下）。`.raw` 的載入流程本來
  寫成 `StudioWindow.load_raw_folder_path`，而它讓方法數 +1。搬進
  `open_dialogs._load_raw` —— 那一支本來就住著另外五個入口的載入。
  **`studio.py` 留給接線，不留給內容**，而這條規矩每次都在同一個地方生效。
* **pyright 從 128 變成 129**：`getattr(ref, "raw", None) is not None` 不會讓
  pyright 收窄 `ref.raw` 的型別。改成先綁一個區域變數再判 `is not None`
  —— 這不是為了討好工具，那個 `getattr` 本來就多餘（`ImageRef` 有那個欄位）。
  上限**不動**。

### 驗收

`tests/test_raw_input.py`（15 條）。核心的三條：
使用者那個檔案大小**只有一組**正方形解、暗很多的第二張圖載進來要**還是比較暗**
（各自拉伸的話兩張會一樣亮 —— 那正是 `load_gray` 做錯的事）、版面填錯時
`read_raw` 要 raise 而且訊息裡有 `skewed`。

## F112：DOE 的出貨 recipe —— `recipes/doe-conditions.json`（2026-09-18）

F111 更正完「DOE 缺一張卡」那句錯話，這一輪把那份 recipe 真的寫出來。
**出貨的 recipe 從三份變四份。**

```
Load images ─┬─le300─┐
             ├─le500─┼──> Align ─┬─le800──> ROI (a cell I mark myself) ┄target┄┐
             └─le800─┘  （整數平移） └─三條全部──────────────────────> GLV <┄ref┄┘
                                                                        └─> Write report
```

一張 GLV 卡吃**全部**的 condition，同一組 target／ref box 套在每一條流上，
每個 condition 各出一份 `<condition>_cmp_snr_px` 與 `<condition>_cmp_contrast_mean`。
那就是 imageY 的動作。**一行產品程式碼都沒改** —— 卡片本來就夠了（F111 的結論）。

### 三個實測才知道的東西

**① ROI 與 Align 都要接**最安靜的那個 condition**。**
相關性是拿訊號去找的，而雜訊最大的那一張訊號最少。實測拿 `le300`（σ=18）定位：
模板比對的 `structure` 只有 3.89（門檻 5）、分數 0.304（門檻 0.3），**兩道閘都在
邊緣** → 區域退回整張圖 → target 與 ref 變成同一塊 → `snr_px` 整批是 0
**而且每一顆都 `ok=True`**。接 `le800`（σ=2）之後分數 1.000、structure 11.74。

⚠ 那個失敗形狀正是這個 repo 最怕的那一種，所以它有自己一條測試
（`test_the_doe_recipe_really_places_its_two_boxes`）：盯 `locate_ok` 與兩個框的
**面積**，不是只看有沒有數字。驗它有沒有牙齒的時候看得很清楚 —— 把 ROI 接回
`le300`，「順序排得對嗎」那一條**照樣綠**（`sorted([0,0,0]) == [0,0,0]`），
只有這一條紅。

**② 範例資料不能沿用 `make_sample.py`，而那是量出來的。**
那一份的 patch **整張都是高對比晶格**：實測任何一個 16×16 的框標準差都在 62 以上、
整張圖 63.7。而 `snr_px = |μT − μR| / σR` 的分母正是**參照那一塊自己的像素標準差**
—— 拿一塊全是圖案的地方當參照，σR 由圖案決定而不是由雜訊決定，於是「哪一個
condition 訊噪比比較好」**在那份資料上根本問不出來**（三個 condition 的 σR 差不到 3%）。

所以新增 `tools/make_doe_sample.py`：低對比週期背景（有結構讓模板比對得到峰，
但不淹掉雜訊）＋**正中央**一顆缺陷 ＋ 每個 condition 各自的雜訊 σ（18／8／2）。
換過來之後 `snr_px` 是 0.37 / 0.83 / 1.25 —— 順序乾淨、而且最好的那個 > 1。

**③ 判定段要用 `decide` 不是 `score`。**
`score.expr` 空著會讓每一顆 `ok=False`（「the expression is empty」）。
量測型的 recipe 沒有門檻可言，所以照 `one-image-uniformity.json` 的形狀走判定樹：
`best_snr = max(每個 condition 的 snr_px)`，`< 0`（一個都沒量到，`fill` 補 −1）
→ bin 9「nothing to measure」，其餘 → bin 0「measured」。

### 一個自己咬到自己的錯

改 ROI 的來源時我只改了**節點的參數**，沒改**線**。而**資料從哪來由線決定**
（鐵則 10）—— 參數上寫著 `le800`、線上接的還是 `le300`，跑出來的仍然是壞的那一版。
那條鐵則在 `CLAUDE.md` 上讀過很多次，真的踩到才知道它擋的就是這個。

### 守門

`tests/test_shipped_recipes.py` 四條（那支測試的結構檢查 glob 到就自動跑，
這四條是**真的跑一批**的）：
* 每個 condition 都有自己的 `snr_px`，而且**雜訊越小的排越前面** —— 那是這份
  recipe 存在的理由，「跑得完、有數字」不算通過；
* 兩個框**真的放下去了**（`locate_ok` ＋ 面積，見上面 ①）；
* **一張 GLV 卡**吃全部的 condition，不是一個 condition 一張卡；
* **沒有 `normalize`** —— N 張之間的亮度差異正是要量的東西，一正規化就抹掉了。
  這一條守的不只是那份檔案：沒有它，下一個人會「順手加一張 Normalize 讓圖好看
  一點」，然後每一個 `snr_px` 都變小而沒有人知道為什麼。

`recipes/README.md` 加一節（含「拿去用在自己的資料上先做這兩件」：重畫那兩個框、
改 condition 的名字）。`tools/make_doe_sample.py` 進 `AGENTS.md` 的機器對照表與
`NEEDS_THIRD_PARTY`（它要 numpy，所以是家用機那一組）。

---

## F111：更正 —— DOE 的 recipe 不缺卡，是我把 `template` 讀錯了（2026-09-18）

F110 收尾我寫了一句「還差第四種 ROI method（或一張新卡）才出得了 DOE 的 recipe」，
**而那是錯的**。使用者一句話就戳破：

> 「其實固定位置的框在 ROI 內就有現成的，因為 defect 都會置中阿，ROI card 內就有
> 一個這選項」
> 「ROI reference 方法請用 a cell I mark myself」
> 「就丟其中一張的 template 給他讓他算，然後在上面框 ROI(Bbox)」

### 錯在哪 —— 前提，不是推論

那一段的每一步推論都對：三種 method 確實都要有東西可以鎖、DOE 的 defect 確實置中、
`pick="centre"` 確實只是從既有的框裡挑一個而不是造一個。**錯的是前提**：
我把「要有東西可以鎖」當成**卡片要自己去找一個可重複的 pattern**，於是
「DOE 的影像未必有 pattern」就變成一道過不去的牆。

但 `a cell I mark myself` 的 `template` **不是卡片要去猜的東西，是使用者自己挑的
那一張圖**。使用者裁一塊當 template、在上面把 target 與 ref 的 bbox 框出來
（`regions`，型別 `cell_rois`，存的就是那幾個矩形）—— 那正是 imageY 的動作：
**設一組 box**，不是叫軟體去找什麼。我讀過那一格的 help（「Draw them on the cell
in Studio」），卻沒有把「誰提供 template」這件事想清楚。

⚠ 第二條路我也讀到了卻沒認出來：`pick` 那一格**預設就是 `centre`**，吐
`<name>_center` / `<name>_others`，而它的說明逐字寫著「Patches are cut around the
defect, so the middle one is usually it」—— 那句話講的正是 DOE 的事實。

### 這一輪只改文件

`docs/ROADMAP.md` 的 Compare 那一列與 `SESSION_LOG.md` 的 F110 那一段。
F110 那一段**逐字留著並標成已更正** —— 它是紀錄，不能假裝沒發生過，而更正一句
錯話的前提是看得到錯的那一句。

**一行程式碼都沒有改**，那正是「判斷錯了」的意思：DOE 的出貨 recipe 還沒寫，
但它不缺任何卡。

### 留給下一個人的那一課

**「做不到」是一個比「還沒做」貴很多的結論**，因為下一個人會照著它去開一張新卡。
這一次的教訓很具體：**下這種結論之前，先問「這個輸入是誰給的」** ——
我把一個使用者提供的東西當成程式要自己產生的東西，整條推論就往錯的方向走完了。

---

## F110：Compare 段收斂 —— 拆卡、第五種 kind、流的內容型別（2026-09-18）

使用者說「**全部**」：F109 之後定案但沒做的六件一次做完。Compare 是 Phase 2 七段裡
最後一段，這一輪之後**七段全部收斂**。

**Compare 段現在四張卡**：`align`（Align）、`subtract`（Compare two images）、
**`combine`（Image Combination，新）**、`align_to`（H2H）。註冊 19 → 20 張。

### ① Image Combination 拆成兩張

`subtract` 的五個 `op` 是**兩個問題**擠在一張卡上，而判準是 F109 定的那條 ——
**訊號形狀**：`subtract`/`ratio` 問「這兩張哪裡不一樣」（2 條進 1 條出），
`max`/`min`/`mean` 問「把這幾張併成一張」（N 條進 1 條出）。

擠在一起的代價實際看得見：那張卡只有 `a` 與 `b` **兩顆埠**，所以想把三張 condition
併成一張 reference 的人得放兩張卡串起來，而畫布上那兩張卡看起來是在比較兩次。

* **比較卡**留著 `subtract` 這個 key（使用者定的 —— 出貨的三份與 fixture 都只用
  `op: "subtract"`，所以那一邊一個字都不用遷移），label 換成 `Compare two images`。
  ⚠ 名字換過兩次而**兩次的理由是同一個**：F16 從 `Compare two streams` 改叫
  `Image Combination`（「五個 op 只有一個是相減」），F110 又改回去 —— 因為那四個
  「不是相減」的裡有三個已經搬走了。名字跟著卡片真的在做的事走。
* 比較卡加兩個 op：`normalized`（`(a−b)/(a+b)`，參照接近黑時不會爆）與
  `over_sigma`（`(a−b)/σ(b)`，讓門檻在安靜的圖與有顆粒的圖上意思一樣）。
* `absolute`（bool）→ `sign`（`abs`／`signed`／**`split`**）。兩個值的格子答不出
  第三種答案，而第三種是使用者真的要的：**亮的缺陷與暗的缺陷分兩條流出去**
  （`<out>_bright` / `<out>_dark`），讓下游各給一個門檻。
* **融合卡** `combine` 拿走 `max`/`min`/`mean` 並加 `median`/`trimmed`。
  **median 是預設**：它是唯一拿得掉「只有一張有」的那個東西的，而那正是缺陷 ——
  「用好幾張造一張乾淨的 reference」是這張卡最常見的用途。

### ② DOE 的輸入：第五種 kind

`folder` 是「一個檔案一顆」，DOE 要的是**正好相反**的「一個子目錄一顆、裡面每個
檔案一個 imaging condition」。使用者選了**開第五種 kind**（`doe_folder`），而那是
對的：同一個 kind 兩種形狀會讓畫布說謊 —— `SINGLE_IMAGE_KINDS` 裡寫著 `folder`，
而 DOE 一顆有好幾張，畫布上那張預設的 `load_single` 對它一定報錯。

⚠ **流的順序是檔名排序，而那是一個契約**：這些 `ImageRef` 的 `page` 是 `None`，
所以 `_in_defect_order` 退回 dict 插入順序 —— 也就是 `sorted()` 的順序，而
`load_patch` 的 `channel_map`（1-based）正是照它數的。湊不成一顆的空目錄與撞名的
目錄**不吞掉**，進 `warnings`（同 `load_tiff_stack` 對零頭的處置）。

CLI 那一條**由內容判斷不是多一個旗標**：一個目錄裡裝的是影像檔還是資料夾是看得
出來的事實，而使用者在命令列重打一次那個事實沒有道理（推廣鐵則）。

### ③ `snr_px` —— DOE 真正要的那個數字

現有 `snr` 的分母是**框與框之間**（使用者 2026-08-21：「SNR 全線改成 by box，
by pixel 會太小」），而**參照少於兩格時整格不寫**。DOE 只有一個 target box、
一個 ref box —— 所以 `snr` 對它永遠是空的，而那正是 `snr_px` 存在的理由。

`snr_px = |μT − μR| / σR`，直接用 `algo/snr.snr_signed`（這個 repo 帶正負號慣例的
**規範出處**，而它到今天為止只有一個 `hasattr` 測試在守 —— 現在它有第一個真的
呼叫者）。⚠ 算在 `if len(boxes) < 2: return out` 那個提前返回的**上面**，否則它在
唯一需要它的情況下被安靜地丟掉。**現有 `snr` 一個位元組都沒動。**

畫面上它自己一群（`Vs pixels`），不掛在 `Vs boxes` 底下：那個群名講的正是 `snr`
的分母，而**分母是這兩個數字唯一的差別**。⚠ 新群名沒加進 `METRIC_GROUP_ORDER` 的
下場是那一群的膠囊**安靜地不畫**（F77 真的踩過）。

### ④ 流的「內容型別」（Q1）

**把 layout label map 接進 Normalize，今天是一條完全合法的線**，而 lint／畫布／
引擎三層都沒擋。它的像素值就是層號，正規化會把 1、2、3 混成 1.7 —— 跑得完、
不報錯、預覽上那張圖看起來還變漂亮了，而下游每一個區域都是錯的。
`load_sidecar.py` 從 2026-08-18 起就逐字寫著這件事，但那句話擋不住一條線。

`ParamSpec.content`（`gray`／`label`）由產出那一格宣告、沿著線傳下去，
只收灰階的輸入格吃到 label 就是一條 **`wrong-content`**（error 級）。
**沒宣告 = 只收灰階**，保守的預設是刻意的：加新卡的人不必想這件事就受保護。

順手刪掉 **`Context.labels`** —— 量過了：**沒有任何一張卡寫過它**，只有引擎與快取
快照在搬運它。一個沒有人寫的欄位不是「還沒用到」，是一條**看起來存在的第二條路**：
下一個要傳 label 的人會挑它，而它不進快取簽章、畫布上也沒有線。
快照欄位集合改了 → `cache.FORMAT_VERSION` 4 → 5。

### ⑤ `focus_quality` 吃區域（Q4）＋ ⑥ 三個 label 剪短（Q5）

`MultiSourceStep` **本來就有整個區域迴圈**（`REGION = "roi"`），所以前者是加一格
參數。⚠ 裁的必須是**二維的一塊**（`crop_to_roi`）不是 `roi_pixels`：銳利度量的是
相鄰像素之間的變化，攤平之後「相鄰」是假的，而四個數字照樣算得出來。
多框區域走既有那條路（報錯並指名 `<name>_center`，CD 卡同一條），不自己發明規矩。

label：`Remove background / stripes` → `Flatten`、`Pair with another source` →
`Pair source`、`Load layout labels` → `Load layout`。天花板跟著從 27 降到 17，
外加一條**反向**測試把「上限＝真的最大值」釘住。

### `studio.py` 那三格只准往下的 —— 這一輪是往下

第五顆 Open 鈕要加，而規矩是「先從它手上搬走等量的東西」。搬的是**五顆 Open 的
對話框與那個「按下去要做什麼」的分岔**（→ `ui/open_dialogs.py`）：
行 7,753 → **7,717**、方法 298 → **294**、`self.*` 437 → **434**，三格一起往下。

**順便讓一句話變成真的**：`CLAUDE.md` §5 寫著「加／改一個入口＝改 `INPUT_SOURCES`，
不要動 UI」，而在這之前加一列就得同時在 `studio.py` 上長一支 `_on_open_<key>`
出來，不然那顆鈕按下去是 `AttributeError`。現在五種共用
`open_dialogs.open_source`，那句話第一次成立。

### 黃金值：這一輪的驗收是「**沒有變**」

跟 F109 相反（那一輪是行為真的改了）。`freeze_golden.py --check` 三份全綠**而且
沒有重凍** —— 兩道新遷移必須跑出逐位元組相同的數字，變了就是遷移寫錯。

⚠ **一個被測試當場擋下來的錯誤**：`absolute → sign` 那一道第一版寫成版本閘
（照抄 F109 的 align），而 `test_reading_a_recipe_never_invents_a_parameter` 立刻紅了。
它是對的 —— 舊的 `absolute=True` 跟新的 `sign="abs"` **是同一件事**，所以檔案裡
沒寫就什麼都不該寫進去。三道遷移三種判準，差別在**預設值的意思有沒有變**：

| 遷移 | 判準 | 為什麼 |
|---|---|---|
| align（F109）| 版本號 | 舊預設與新預設是兩種行為，從「缺一個 key」分不出來 |
| `subtract` 拆卡 | 舊的**值**（`op` 是不是 max/min/mean）| 鐵則 9 正牌 |
| `absolute` → `sign` | 舊**鍵**在不在 | 同上，而且預設值的意思沒變 |

### 沒做完的那一件 —— ⚠ **而這個判斷是錯的（F111 更正）**

> 下面這一段是當時寫的，**逐字留著**：它是「我當時怎麼想的」，而更正一句錯話的
> 前提是看得到錯的那一句。正確的版本在下一段。

> **`recipes/doe-conditions.json` 出不了貨**，而理由不是時間：三種找 ROI 的方法
> （條紋／我標的 cell ＋ 模板比對／GDS label map）**都要有東西可以鎖**，而 DOE
> **不需要找** —— defect 本來就固定在 FOV 正中間，要的是「把框放在這個固定位置」。
> 那是第四種 method（或一張新卡），是**卡片層的決定**，不是一份 recipe 寫得出來的。
> 硬用 `roi_template` 的話要在 recipe 裡塞一張模板圖，而 DOE 的影像未必有可重複的
> pattern 給它鎖 —— 那份 recipe 會在 `test_shipped_recipes` 裡真的跑，然後真的失敗。

**更正見下一輪（F111）**：那一段的每一句推論都對，只有**前提**是錯的 ——
「要有東西可以鎖」不是卡片要去猜，那一張 template 本來就是使用者自己挑的。
DOE 的出貨 recipe **不缺任何卡**。

### 天花板

`recipe.py` 3,949 → 4,101（兩批：`wrong-content` 的兩支 ＋ 第 21、22 道遷移），
遷移道數 20 → 22，`RECIPE_VERSION` 4 → 5，`cache.FORMAT_VERSION` 4 → 5，
卡片 label 上限 27 → 17（往下），`studio.py` 三格往下（見上）。

---

## F109：align 重做並拿回卡片庫 —— **對齊不動灰階**（2026-09-17）

使用者定調把 `align` 拿回來，而且講清楚了用途：**DOE**。同一顆 defect、位置固定在
FOV 正中間、FOV 相同，用**不同 E-beam condition**（Landing energy／電流）各拍一張，
對齊之後在**同一組 target／ref box** 上比 SNR 與 contrast。對標公司內的 imageY 流程
（一次載入許多條件的圖、設一組 box、對齊、一起量）。輸入是**一個資料夾的圖片、
沒有 KLARF、一顆就是一張圖**。

2026-08-18 收起它的時候使用者說的是「**之後真需要我再回來**」—— DOE 就是那個「之後」。
`CLAUDE.md` §5 那張表（收起來／刪掉／改名）第五次被驗證：**收起來的成本是零，
回復的成本是改一個字串**。

### 它當初做錯的那件事這一輪修掉了

收起來的理由是「拉 align 反而會飄掉 shift」，而那有兩個機制：

1. 真實位移接近 0 時，相關峰的位置由雜訊決定；test 有缺陷、ref 沒有，**缺陷把峰往
   自己那邊拉**。
2. **只有被移動的那一條被重採樣**（次像素走 `cv2.INTER_LINEAR`）—— 等於對它過一次
   低通、對基準那條沒有。

**DOE 讓第 2 個從副作用變成致命傷**：量的就是 SNR，而 SNR 就是灰階。對其中幾張各過
一次不一樣的低通，再去比它們的 SNR，那個比較是假的。

而 `align_to`（H2H）早就解出正解（`align_to.py`：「次像素的那一點點留在數字裡 ——
不要為了對齊而重採樣」）。這一輪就是把那條紀律套到 align 上：**位移只取整數，
所有流一起裁成共同重疊區**，次像素仍然寫進 `align_dx` / `align_dy`。
第 1 個機制**沒有**修：要修它得讓對位只看一塊不含缺陷的區域，那是另一件事。

### 形狀：一張卡、N 條流、就地對齊

| 參數 | 型別 | |
|---|---|---|
| `streams` | `image_keys` | 要對齊的那幾條（**含基準**） |
| `fixed` | `image_key` | 基準（不在 `streams` 裡 → lint 報錯：它不會被裁，出去的尺寸就對不起來） |
| `method` | `chip_choice` | 五個 backend 沿用 |
| `search_radius` | `int` | 沿用，**補了 `extent`** |
| `suffix` | `str` | 空 = **寫回原名**（遷移就是把舊檔案帶到這裡）；填了才寫在旁邊 |

加幾個 condition 都只有一張卡。特徵：一條對一條**不加前綴**（舊 recipe 的分數表達式
寫的是 `align_dx`，改名等於讓每一份舊 recipe 都算錯）；三條以上才帶流名前綴。
新增 `align_valid_frac`（裁完剩原來的幾成）—— 照「卡片自動做的每一個決定都要變成一個
畫得出分布的數字」。

⚠ **裁切會改變正規化座標的意義，所以 ROI 卡要接在 align 之後**（`Load → Align → ROI → GLV`）。

### 順便修掉三個「看起來像做完了」

* **`align_score` 的 help 值域是錯的**：寫著 `0 to 1`，而 `algo/align` 每個 backend
  都 `* 100` → 實際 0–100。那個數字**進得了分數表達式**，而 help 是使用者唯一讀得到
  的說明 —— 寫錯就是把人帶到一個差 100 倍的門檻上（`score < 0.8` 會是「全部都過」）。
* **尺寸不符時回 `dx=0, dy=0, score=0` 而三個數字照樣流進 features** → 改成**報錯**，
  訊息指名該用 `H2H`。單顆報錯只讓那一顆 `ok=False`，整批照跑（鐵則 7）。
* **`search_radius` 是半徑，而 UI 那個框畫的是邊長** —— 填 `extent=True` 的話畫面上
  那個框只有真實搜尋範圍的**一半**，而「一個小一半的搜尋窗」看起來完全正常。
  新增 `ParamSpec.extent` 的 `"radius"` 值與 `ParamSpec.extent_px()`：換算住在
  `ParamSpec` 上而不是 UI，因為「半徑還是邊長」是**參數自己的性質** ——
  放進 UI 就變成一張要跟著 `ParamSpec` 走的對照表，而那種表會漂。

### 黃金值變了，而每一格都解釋得出來

第 20 道遷移（`_migrate_align_into_streams`，`RECIPE_VERSION` 3 → 4）：
`moving`/`fixed`/`out` → `streams`/`fixed`/`suffix`。判準照鐵則 9 看**舊鍵在不在**，
但 fixture 那一份**一個舊參數都沒寫**（全靠預設值），所以實際的閘是
`version < RECIPE_VERSION`。這道遷移比前 19 道都長，理由是 align 的舊 `out` 是一個
**下游看得見的名字**（`ref_aligned`）—— 換掉它還要改每一張指著那個名字的 `image_key`
參數與 `recipe.edges` 上的 `src_out`。少改任何一邊，舊 recipe 開起來就是一條斷掉的線。

**而 `dual_route_basic.json` 的準確率從 24/24 掉到 18/24 —— 追下去發現舊的那個數字
才是假的。** 把 align **整張停用**也是 18/24：舊的 24/24 靠的是「ref 被一個雜訊驅動的
次像素重採樣過了一次」。`tools/make_sample.py` 的 `shift_max` 預設是 **0**（機台出的
patch 本來就對好了），所以量到的 0.1–0.36 px 全是雜訊，那次重採樣沒有在修正任何東西
—— 它**就是**使用者回報的那個「飄」。

拿掉之後分數反而變乾淨：seed 7 上 nuisance 最高 5.38、真缺陷最低 5.81，兩類完全分得
開，而**舊門檻 4.2 落在 nuisance 範圍裡面**。跨四個 seed（7/3/11/21）掃門檻：
4.2 → 73/96、5.4 → 87/96、6.0 → 88/96。取 **5.4**（平台的左端，不是掃描的 argmax ——
取 argmax 是對掃描過擬合）。

⚠ 中途有一個**被自己的實驗推翻的假設**：我猜「那層意外的低通本身在幫忙」。實測對
ref 顯式加模糊：gaussian k=3 → 13/24、median k=3 → 14/24、gaussian k=5 → 16/24 ——
**全部更差**。真正的原因是那個沒跟著搬的門檻。

### 守門（每一條都先驗過「把錯誤放回去會紅」）

新檔 `tests/test_align_card.py`（21 條）：

* **對齊不動灰階** —— `ref` 是 `test` 整數平移過的同一張圖，所以裁完之後兩張必須
  `np.array_equal`。**這不是「差很小」，是那個等號** —— 它就是這張卡的承諾。
* **出去的每一個灰階值都是進來那張圖上真的有的值**（`INTER_LINEAR` 會造出原圖沒有的
  中間值）。兩條都對五個 backend 各跑一次。
* N 條流裁完尺寸一致；`align_valid_frac` 對得上實際裁掉的比例。
* 尺寸不符報錯、單一條流報錯、`fixed` 不在 `streams` 裡是 lint error。
* **反向**：`align_score` 的 help 宣稱的值域**從 help 裡讀出來**，跟五個 backend 實際
  跑出來的分數比（上界還要「貼著真值」—— 寫 `0 to 1000` 也會紅）。

`tests/test_recipe.py` 三條守那道遷移（換參數、**改下游**、`out == moving` 時不要順手
改壞它的線），外加「遷完之後 `to_json_dict → from_json_dict` 仍然是 identity」——
那一對正是 `run_batch` 送 recipe 進 worker 的路（鐵則 9）。

### 儀表板那一塊也要跟著，不然 DOE 上它是一張空圖

`AlignInspector` 畫的是**整批的位移散佈圖**（對位失敗在單顆上看不出來 —— 演算法一定會
回一個位移，真正的訊號是「點貼在搜尋框的邊上」）。它以前寫死 `align_dx` / `align_dy`
兩個名字，而**三條以上的流時特徵名帶著流名前綴** —— 也就是說 DOE（一次 N 個 condition，
正是這張圖最有用的時候）會得到一張空圖，而空圖上寫的是「跑一次試跑就看得到」。
使用者照做之後還是空的，然後去懷疑資料。

名字改成跟卡片要（`align.shift_feature_names`），並加一條測試守著它跟
`resolve_features` **不准漂開** —— 那是兩支各自算前綴的函式，而那種對子會漂。

`tests/test_ui_scope_profiles.py` 兩條改寫過：它們本來斷言 `HIDDEN_STEPS == ("align",)`
與 `"align" not in fab_keys`，而這一輪把 align 拿回來就紅了。**紅得沒有道理** ——
壞掉的不是「一句話設一組開關」那個機制，只是那組開關的內容換了。改成問機制本身：
用哨兵值驗「每一格都真的被寫過」、當場塞一張卡進 `HIDDEN_STEPS` 驗「`visible_steps`
真的讀得到現在的值」（**空的清單過濾不掉任何東西，那正是這種測試最危險的時候**）。
另外加一條把「現在沒有收起任何卡」釘住：**收起來是使用者說出口的決定**，悄悄多一個
字串 = 有一張卡從畫面上消失而沒有人做過那個決定。

天花板兩格簽了名：`recipe.py` 3,870 → 3,949（第 20 道遷移），`recipe_migrations`
19 → 20（那一格問的「舊到哪一版可以不再自動轉」這次有答案：不寫這道遷移，
帶著舊參數的檔案開起來是一張參數全空的卡，**跑得完、有數字、而且是錯的**）。
`inspectors.py` 3,660 → 3,669（散佈圖跟卡片要名字）。
`studio.py` 的只往下那一格**沒有動** —— `extent_px` 的換算搬進 `ParamSpec`，
UI 那一行只是換了呼叫對象，淨值 0。

⚠ 一個**連帶的名字變化**：撞名時被蓋掉的那份 `align_dx` 以前叫 `ref_aligned_align_dx`
（F17-② 的規則：前綴用「那張卡寫出去的那條流」），現在退回節點 id 叫
`align_align_dx`。那是照 `feature_prefix` 自己寫著的退路走的 —— 新的 align 寫 N 條、
讀 N 條，**兩邊都不是剛好一條**，而且兩條以上時沒有任何一條流名說得出 `align_dx` 是誰的
位移（它講的是被移動的那一條，不是基準）。F17-② 那條規則本身由
`tests/test_feature_owner_prefix.py` 守著，那一份一個字都沒改。

### 這一輪同時收斂的：Compare 段是什麼

使用者問「Compare 段要放什麼」，並且指定**不要從既有程式碼回答**。討論出的判準是
**訊號形狀，不是意圖**：

* **Enhance** = 1 條流 → 1 條流
* **Compare** = 2 條以上 → 一條流
* **Measure** = 流（＋區域）→ 數字

用「意圖」當判準的話 Enhance 整段都會被吞進來 —— 每一張 Enhance 卡都是為了讓後面
比得準。而**「跟誰比」不該是任何一張卡的參數**：那由畫布上的線決定（鐵則 10）。

⚠ 討論中我說「手畫框是個缺口」，**使用者當場糾正**：`roi_template` 的 `regions`
（型別 `cell_rois`）就是手畫的矩形。已經有的東西不要當成缺口。

Compare 段剩下三件（**這一輪沒做，已定案，寫進 `docs/ROADMAP.md` 那一列**）：
① DOE 的輸入形狀（`load_folder` 今天是「一個檔案 = 一顆」，DOE 要的是「一個資料夾 =
一顆、裡面每個檔案 = 一個 condition」）；② 新 metric `snr_px` = `|μT − μR| / σR`
（⚠ **不能改現有 `snr`**，它是框與框之間的 σ —— 同一個名字兩種算法是這個 repo 最
明文反對的）；③ `Image Combination` 拆成**比較卡**與**融合卡**。①② 做完配一份
`recipes/doe-conditions.json`，README 要寫一句：**DOE recipe 裡不要放 `normalize`**
—— N 張的亮度差異正是你要量的東西，一正規化就抹掉了。

另外三個卡片位置的問題也定案了（都**不在這一輪**）：**label map** 要加「流的內容型別」
（gray／label）並刪掉死的 `ctx.labels`（今天把 label map 接進 Normalize 是一條
**完全合法**的線，而 lint／畫布／引擎三層都沒擋）；**`focus_quality` 要吃區域**
（三張 Measure 卡裡唯一沒有 `region_keys` 的）；**三個 label 太長**
（`Flatten`、`Pair source`、`Load layout` —— 27／24／18 字元，中位數 11，
太長的在「Add ▾」裡會被截掉）。

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
