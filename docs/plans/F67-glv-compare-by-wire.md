# F67 — GLV 的「跟誰比」由線決定

2026-09-01。

## 問題（使用者原話）

> 「GLV card 這邊的 ROI 接線 我覺得對 user 來說 還是會有點混淆 (Compare
> against) 跟最上方 What do I want to measure 相關~ 你建議怎麼改會比較好」

同一個決定在卡上被問了**兩次**，而且用兩種語言：

| | 上排（F44 2a 的三顆鈕） | §3 「Compare against」 |
|---|---|---|
| 字 | 樣品語言：「The defect's box」 | 拓樸語言：「another region on another stream」 |
| 是什麼 | 不是參數，是 preset | 是參數 `reference` |
| 動到什麼 | roi / reference_region **兩條線** | 同樣那兩條線的**埠在不在** |

而 §3 那一格的五個答案本質上是「**參照區域那顆埠有沒有線 × 參照流那顆埠有
沒有線**」的真值表 —— 它是線的複述。複述的代價實際存在過三個：

1. 兩份說法可以不一致（引擎讀那一格，使用者看的是線）—— 鐵則 10 擋的正是這個。
2. 「跟誰比」選回 `none`，參照那條線**不會跟著剪掉**（只有 preset 會剪，
   手改的路徑不會），畫布上留一條指向不存在的埠的線。
3. 五個答案的字是拓樸，而使用者問的是樣品 —— 這張卡自己的 docstring 罵過舊
   `method` 的同一句話（「還沒開始量，就先被問了一個關於軟體架構的問題」）。

## 做了什麼

**① `reference` 那一格刪掉，真值表 = 兩顆埠**（`glv_stats._reference_of` 是
唯一出處；引擎其他地方一行都沒動 —— 它們本來就只問那一支）。

- `reference_region` / `reference_source` 兩顆埠**常駐**、default 空。以前它們
  跟著 `reference` 的 `show_when` 長出來，於是使用者得先在設定區選一個拓樸的
  字，才有東西可以拉線。
- `REF_OTHERS`（`the other regions`）一起走：它就是把 `<n>_others` 接進參照
  那顆埠，而 F44 的 preset①「量缺陷那格」教的**已經**是接線那一種。
- 「Compare their / Report」兩列跟著「有沒有在比」走 —— 兩顆埠任一有線就顯示。
- 名字換成樣品語言：段標題 `3 · Compare with`、兩顆埠 `Another area` /
  `Another image`（以前是 `That region` / `That stream`，而段標題與 `reference`
  的 label 同字，畫面上像重複了一列）。

**② `show_when` 兩個新寫法**（`core/pipeline/step.py`，UI 與引擎共用那一份規則）

- `ANY_VALUE`（`"*"`）＝「這一格有值就算數」。接線型的參數列不出允許值：
  它的值是使用者拉了哪一條線。
- 一條條件的參數名可以是**一串名字**＝ or（條件與條件之間仍然是 and）。
  「Compare their / Report」問的是有沒有在比，問其中任何一顆埠都答不完整。

**③ 遷移 `_migrate_reference_into_ports`**（鐵則 9：判準是舊 key 在不在）

`roi_compare` → `method="compare"` → `reference` → **兩顆埠**，四段的最後一段。
真正的重點是**剪線那一半**：舊檔案裡「選回 none／改成另一條流」之後留下的
那條線，在 F67 之後**就是答案** —— 照抄過來的話，一份只報絕對值的 recipe 會
安靜地開始吐 `cmp_*`。所以每一種情況都明寫哪一顆留、哪一顆剪。

`the other regions` 是唯一要**補**東西的：一個區域的那種補一條 `<roi>_others`
的線（**數字與特徵名逐字不變**）；量好幾個區域的那種以前是逐塊配對，一條線
表達不出來 —— 補第一塊的，而新的一條 lint 對那個形狀講話（見下）。

**④ 一條新 lint ＋ 一個訂正**

- 量好幾塊、而參照接的是其中一塊的 `_others` → 講出「這幾塊**全部**跟它比；
  要逐塊配對請一塊一張卡」。同名不同義的東西不准安靜。
- 訂正：`ctx.meta["compares"]` 的 `reference_source` 以前只認 `REF_STREAM`，
  於是「另一塊 @ 另一條流」在面板上被寫成量測那一條 —— 數字是對的，
  旁邊那行字說錯了它是跟哪一張圖比出來的。

## 沒有動到的

- **特徵名一個字都沒變**（`cmp_*` 那一族），所以既有的分數表達式不必改寫。
- 黃金值三份**都沒有用到 compare**，數字不動。
- 上排那三顆 preset 的行為不變 —— 它現在只做一件事（拉線），而那正是它一直
  在做的事。

## 驗收

核心全綠（`--ignore-glob="*test_ui_*"`）、UI 一個檔案一個檔案全綠、
出貨 recipe `patch-dsnr-by-class.json` 更新並由 `test_shipped_recipes` 真的跑過。
新／改的測試：`test_glv_compare.py`（真值表就是兩顆埠、那一格不存在了、
遷移的剪線與補線、新 lint）、`test_steps.py`（`ANY_VALUE` 與 or）、
`test_ui_canvas_invariants.py`（兩顆埠常駐、下面兩列跟著線走）、
`test_ui_glv_intent.py`、`test_ui_region_hydration.py`（`_others` 現在是一條線）。
