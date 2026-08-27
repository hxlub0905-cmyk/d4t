# F41 — 刪掉 `feature_math` / `feature_fill`（工作單 Phase 3）

**狀態：收斂（2026-08-27）。兩個問題都定調了，見 §4。**

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

## 4. 兩個問題（使用者 2026-08-27 定調）

### 4.1 `GROUP_ALGO`：一個零張卡的常數 → **留著**

* **現況**：它**不在** `GROUP_ORDER` 裡（F24 §5 就拿掉了），所以卡片庫與 rail
  上沒有這一段；`resolve_group()` 照認，留著是給**外掛卡**相容。
* 這一輪之後 repo 裡掛在它上面的卡是 **0 張**，而守它的那條測試也刪了（§3）。
* **使用者：「留著（外掛相容）」。** 程式碼零改動 —— 那已經是現況。

⚠ 但要知道它現在的狀態：**這個常數沒有任何測試在守**，因為它沒有東西可以套用。
下一次有外掛卡掛上 `GROUP_ALGO` 的時候，「Algo 段的卡不吃影像流」那條不變量
要重新長一支測試出來（原本那支的形狀在 §3）。

### 4.2 `adc` 段：問題的前提是錯的 —— 那一格早就有入口

**使用者選的是「ADC 那一格放一個真的入口」，而它 F25 就做掉了。**

我提這個問題時量錯了一次：直接對 `LibraryPanel` 呼叫
`set_steps(visible_steps(...))`，於是看到 `adc` 段是空的。但**注入那一列的是
`StudioWindow` 不是 `LibraryPanel`**（`studio.py` 的 `_SCORE_LIBRARY_ENTRY`）。
用真的 Studio 量：

```
adc      ADC      ['__score__']        ← Score / Bin
```

而 `_on_add_requested` 第一件事就是把那個 key 轉給 `add_decision()`：

```python
if str(step_key) == _SCORE_LIBRARY_KEY:
    # 「Decision」不是可增刪的卡片 —— 點它就是把它放上畫布並開始編第一步
    self.add_decision()
```

> **量一個 UI 的狀態，要從使用者真的會看到的那個物件量起。** 我量的是元件，
> 而那一列是視窗接上去的 —— 少了一層，答案就整個反過來。這跟 F39-B4 的教訓
> 是同一個形狀（從檔案層級的數字回答測試層級的問題）。

那兩張被刪掉的卡（`feature_math` / `feature_fill`）從來不是判定本身 ——
它們是 F24 解散 Algo 段之後**暫時寄放**在 `adc` 底下的兩張隱藏卡，而且從
2026-08-24 起就在 `HIDDEN_STEPS` 裡（實測刪除前那個 commit，`visible_steps`
回的 `adc` 已經是零）。所以這一輪的刪除**沒有改變任何使用者看得到的東西**。

### 4.3 ⚠ 順帶量到、但沒有動的：那一列的字過期了

| 現在寫的 | 而實際上 |
|---|---|
| label **`Score / Bin`** | 使用者 2026-08-24 之後的說法是「ADC 卡」，程式碼註解裡叫它 **Decision** |
| help「…split into bins **by a threshold** — every pipeline has exactly one; **click to edit it**」 | F24 之後**預設是多類別判定樹**（使用者：「原來的根本不會用到」），二元門檻只留給舊 recipe；而點下去不是「編輯它」，是**把判定區放上畫布並開始編第一步** |

**沒有動** —— 它不在工作單上（「沒有列在上面的，一律不要順手改」）。要改的話是
一列 label ＋ 一段 help，零風險。
