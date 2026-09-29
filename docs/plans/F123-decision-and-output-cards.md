# F123 — Decision 與 Output 變成真的卡（做法 B）

狀態：**進行中（2026-09-29）—— 期 1（Decision 變成一張卡）做完；期 2～4 未開始。**
使用者定調：「我想直接做 B」；三個問題的答案見 §1。

F122 期 5 的續集。那一期原本要把 Output 排在固定的一欄、判定旁邊加一行「results →」
的字；使用者：「我會覺得對畫布來說很奇怪，不管是 ADC card 或者是 Output card 的定位
（理論上 input = output）」。先看了做法 A（數字線一直畫著、拉不動）的截圖，然後選 B：
**Decision、Output 跟 Input 一樣是真的卡，線由使用者拉。**

---

## 1. 使用者定調（2026-09-29）

| 問題 | 答案 |
|---|---|
| 數字線（量測卡 → Decision）要不要是必要的 | **必要** —— 判定樹只能問「有線接進 Decision 的那幾張卡」的數字 |
| Output 的結果線只能從 Decision 來嗎 | 「其實我認為不一定要有 Decision（在大多數情況下要），但我又不想要綁死」→ 照建議：**Output 寫的是接進來那條線上游的東西**；接 Decision 有類別，直接接量測卡沒有類別，可以接好幾條 |
| 線的顏色 | **照資料種類**：影像一個中性色、區域綠色虛線、數字／結果 ADC 紫 |

## 2. 形狀

```
Input ━image━▶ … ━image━▶ GLV ═numbers═▶ Decision ═results═▶ Write report
                           ║                                ▲
                           ╚═══════ boxes ══════════════════╝ Write charts
```

## 3. 分期

* **期 1 — Decision 變成一張卡。** 註冊一張 `decision`（CATEGORY_ADC／GROUP_ADC，
  沒有參數、`run` 是 no-op —— 判定照舊在整條 pipeline 跑完之後由引擎算）。判定的內容
  仍住在 `recipe.decide`；卡與內容同生同滅（`RecipeModel.add_step` / `remove`）。
  第 6 版遷移：有判定的舊檔案補一張卡，排在第一張 Output 卡前面。一份 recipe 最多一張
  （`duplicate-decision`）；停用那張卡＝不判。畫布：虛線框、入口小卡、`__score__` 偽卡
  拿掉；Decision 是一張普通的卡，點開看樹。
* **期 2 — 數字線與結果線。** 量測卡一顆「numbers」出埠；Decision「numbers」入埠
  （很多條）與「results」出埠；Output「results」入埠（很多條）。必要性由 lint 守、
  「插入數字」只列接進來的卡；Output 寫的是線上游的東西。遷移補線。
* **期 3 — Output 自己的輸入。** Write comparison 左右兩張圖改成真的影像埠；Write charts
  接 GLV 的「boxes」。
* **期 4 — 線的顏色照資料種類。**

## 4. 不變的

* 引擎算出來的數字、黃金值（每一期都跑 `freeze_golden --check`）。
* 判定的內容仍在 `recipe.decide`（搬進卡的參數要改一百多處引用，F48 §2 量過，而那件事
  對使用者看得到的東西沒有差別）。

## 5. 期 1 的紀錄

* core：`steps/decision.py`；`recipe_migrations._migrate_decision_into_a_card`；
  `RECIPE_VERSION` 5 → 6，版本閘拆成 `< 5` / `< 6`（第 5 版以前那三道**不能**對第 5 版的
  檔案再跑一次）；引擎：停用的 Decision 卡不判；lint `duplicate-decision`。
* model：`RecipeModel.decision_node`；加卡時沒有判定就給一個空的（同一步復原），
  刪卡時拿掉判定。
* 規模尺：`recipe.py` 650 → 653、遷移道數 23 → 24（簽了）。
* 名詞表那一格改成「Decision」（它現在是卡片名；小寫的 `"decision"` 撞到卡片的 key，
  被「UI 按卡片名字分支」那把尺誤算）。
* 畫布：虛線框（`_ZoneItem`）、入口小卡（`_EntryItem`）、`__score__` 偽卡拿掉。樹掛在
  Decision 卡底下（`tree_scene.build_tree` 收 ``anchor``；沒有那張卡的手寫 recipe
  樹站在卡片右邊）；拖卡樹跟著走（`PipelineCanvas.follow_decision`，就地搬）；雙擊
  收合；單擊右邊是判定面板；刪卡先問（`canvas_edges._drop_the_tree`）。
* 卡與內容同生同滅只在 model：`add_step` / `remove` / `use_decide`；開檔時沒有判定
  就不留那張卡（`RecipeModel._drop_decision_cards`）。
* 判定的 lint 掛到那張卡（`_node_problems`），另抄的那一份拿掉。
* 出貨 recipe 存成第 6 版；`doctor.RECIPE_VERSION` 5 → 6。
