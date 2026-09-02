# F41 — 刪掉 `feature_math` / `feature_fill`（工作單 Phase 3）

**狀態：程式碼收斂（2026-08-27）。§4 的兩個問題 2026-08-28 定調 —— 見 §5。**

使用者：「功能已經被 `decide.let` 取代了，刪掉。」
以及：**`align` 維持收起來，一個字都不要動**（那句「之後真需要我再回來」還算數）。

---

## 1. 這是那張對照表第一次跑完全程

`CLAUDE.md` §5 那張「收起來／刪掉／改名」的表寫著：

> **不確定的時候先收起來**：成本是零，回復的成本是拿掉一個字串。使用者確定之後
> 再刪 —— 上面那張表就是「確定」值多少錢。

這兩張卡 2026-08-24（F24 ④）先**收起來**、2026-08-27 使用者確定之後**刪掉**。
中間隔了三天，而那三天裡使用者真的用了判定樹 —— 那正是「收起來」要買到的東西。

## 2. 刪掉的代價（實際付了什麼）

| 動到 | 內容 |
|---|---|
| 卡片 | `d4t/core/steps/feature_math.py`、`feature_fill.py`（353 行）|
| 註冊 | `steps/__init__.py` 的 import ＋ `__all__`（順手把檔頭那張已經過期的 Output 卡清單一起改對）|
| 範圍開關 | `ui/scope.py` 的 `HIDDEN_STEPS` → 只剩 `("align",)`。**`align` 一個字都沒動** |
| 遷移 | `recipe.py` 拿掉「改寫 `feature_math` 節點算式」那一條。**理由：帶著那張卡的舊 recipe 現在是一條 `unknown-step`，跑不起來 —— 跑不起來的 recipe 不需要有人幫它改名。** 判定段的算式（`let` / 樹）走 `_migrate_decide_renames`，那條路還在 |
| 測試 | 刪 `test_feature_math.py`、`test_feature_fill.py`、`test_ui_f21_expr_picker.py`；改 5 支 |
| 黃金值 | **零** —— 三份 fixture recipe 都沒用到它們，`--check` 三份逐項相同 |

**沒有寫遷移**：那兩張卡的功能在判定的 working numbers 裡，而**算式怎麼搬進去是
使用者的決定，不是一道機械遷移**（`expr` 是使用者寫的字，`let` 的結構不一樣）。
舊 recipe 開起來會拿到一條講得出來的 `unknown-step`，那就是刪掉要付的錢。

## 3. 兩條測試要跟著翻面，不是跟著刪

| 測試 | 處置 | 為什麼 |
|---|---|---|
| `test_ui_tree_edit::algo_cards_are_shelved_not_deleted` | **翻面**成 `the_algo_cards_are_gone_for_good` | 「收起來」與「刪掉」的證據**剛好相反**。翻面之後它守的是：舊 recipe 帶著那兩張卡開起來要拿到一條 `unknown-step`，不是一個 `KeyError` |
| `test_ui_f16_stages::the_absorbed_algo_cards_never_read_an_image_stream` | **刪掉** | 它掃「那兩張卡，以及任何掛在 `GROUP_ALGO` 上的卡」。兩張卡刪掉、而 `GROUP_ALGO` **本來就零張卡** —— 那個迴圈的本體再也不會執行一次，而測試照樣綠 |

第二條正是 F40 那支恆綠零斷言測試的形狀，只是這一次是我們**自己親手做出來的**。
**一條永遠不會執行的斷言比沒有斷言更糟**：它讓下一個人以為那條規矩有人在守。

`test_ui_f21_expr_picker` 整支刪掉之前，先把
`test_a_card_does_not_offer_its_own_output` 救進 `tests/test_viewmodel.py`
（`include_upto=False` 全 repo 唯一的守門人，改用 `glv_stats` 的第二個節點觸發，
問的是同一件事）。驗過：把 `include_upto` 的效果關掉，它在新家會紅。

## 4. ⚠ 兩個問題，使用者定調（工作單指名不要自己決定）

### 4.1 `GROUP_ALGO`：一個零張卡的常數

* **現況**：它**不在** `GROUP_ORDER` 裡（F24 §5 就拿掉了），所以卡片庫與 rail
  上沒有這一段；`resolve_group()` 照認，留著是給**外掛卡**相容。
* 這一輪之後 repo 裡掛在它上面的卡是 **0 張**，而守它的那條測試也刪了（§3）。
* **選項**：(a) 留著（外掛相容，成本是一個常數 ＋ `step.py` 幾行說明）；
  (b) 連同 `resolve_group` 裡認它的那一段一起刪（外掛若用了它會變成
  `unknown group`）。

### 4.2 `adc` 段：卡片庫上一個永遠空白的抽屜

* **現況**：`feature_math` / `feature_fill` 的 `group` **是 `adc`**（不是 `algo`）。
  刪掉之後 **`adc` 段零張卡**，而它**在** `GROUP_ORDER` 與
  `LibraryPanel.GROUPS` 裡 —— 畫面上會是一列「ADC」標題底下寫著
  `(no cards in this section)`。
* **這件事有前例，而且理由就寫在程式碼裡**：F24 §5 把 Algo 那一列從 `GROUPS`
  拿掉時的註解是「**這一段清空之後留著只是一個永遠空白的抽屜**」。
* 但 ADC 跟 Algo 不一樣：**ADC 這件事本身沒有消失**，它只是不由卡片表達
  （score / bin / 判定樹住在下方的判定面板與 verdict band）。所以留著那一列
  也可以讀成「這一段在別的地方做」。
* **選項**：(a) 照 Algo 的前例拿掉那一列（`GROUP_ORDER` ＋ `GROUPS` ＋
  `test_ui_f16_stages` 那條七段清單一起改，變六段）；(b) 留著空的一列；
  (c) 留著，但那一段的空白文字改成指路（例：「這一段在下面的判定面板」）。

**使用者 2026-08-27 定調：Phase 3 開始時再決定 —— 現在開始了。**

---

## 5. §4 的兩個問題：使用者 2026-08-28 定調

### 5.1 `GROUP_ALGO` → **(b) 刪掉**（已執行，F48）

使用者：「1 刪掉」。做掉的：`step.py` 的常數本身、`widgets.GroupIcon` 那一支
再也走不到的 `elif g == "algo"`（Σ 圖示），以及兩條測試的**翻面**
（`test_ui_f16_stages` 與 `test_docs_links` 以前問的是「它不在 `GROUP_ORDER`
裡」＝收起來的證據，現在問「它不存在」＝刪掉的證據 —— §3 那一課的第三、
第四條）。

**代價寫在常數原本的位置上**：外掛卡若宣告 `group = "algo"`，
`resolve_group()` 會照樣回那個字串，而卡片庫沒有那一段 —— 那張卡列不出來，
要改宣告成 `GROUP_MEASURE`。

⚠ 順手守住兩個**很容易被一起清掉的鄰居**（新測試
`test_the_algo_group_is_gone_for_good` 的後半）：`CATEGORY_ALGO` 是另一個軸
（「這張卡吐數字」，每一張量測卡都是它），三段式心智模型裡的 `"algo"` 段
（`welcome._SEG_LINES`、`theme.seg_color`）也還活著。

### 5.2 `adc` 段 → **問題的前提是錯的，回到使用者手上**

使用者答「2 拿掉」，而那是根據 §4.2 寫的「**刪掉之後 `adc` 段零張卡**」。
2026-08-28 實機查證之後那句話**不成立**：

```
adc       ADC       ['__score__']
```

`studio._SCORE_LIBRARY_ENTRY` 釘了一張 `Score / Bin` 偽卡進那一段（點它 =
`add_decision()`，把判定放上畫布並開始編第一步）。§4.2 是**從 registry 的
角度**數的 —— 那個角度看不到這一張，因為它不是註冊出來的 step。

所以那一段不是「永遠空白的抽屜」，而是「有一張卡，只是那張卡不在 registry
裡」。這是一個**不一樣的問題**，決定因此退回去重問（使用者的反問：「為何
不能讓它就變成一張真的卡片?」—— 代價量在 F48 的計畫書裡）。

> **這一條本身是這一輪最值得記的東西**：§4.2 的兩個選項寫得很清楚、理由也
> 對，而它們踩在一個沒有人去畫面上確認過的前提上。**「零張卡」是查 registry
> 查出來的，不是看畫面看出來的** —— 而使用者按的是畫面。
> 這跟 F42 B4 記下的那條是同一個形狀：*一個決定寫下理由的時候，要順便寫下
> 它踩在哪個前提上*，這裡再加半句：**而那個前提要從使用者看得到的那一面量。**
