# F119 — 哪一個 bin 是好消息（F117 D2 的根因）

狀態：**只有設計，還沒開工（2026-09-20）**。使用者同意走「甲：寫 recipe 的人
自己標」。⚠ 走查把 D2 記成「均勻度那一條」，**實測是三份出貨的 recipe 全反**
—— 範圍比原本寫的大，見 §1。

---

## 1. 為什麼

判定完，畫面右邊那顆**彩色膠囊**（`VerdictChip`）是使用者對「這一顆到底怎麼
樣」唯一的一眼答案。而它的顏色是**看 bin 的號碼**決定的，寫死在
[`feature_text.py:355`](../../d4t/ui/feature_text.py)：

```python
elif b == 1:   tone = "bad" if is_real_style else "good"
elif b == 0:   tone = "good" if is_real_style else "bad"
else:          tone = "neutral"
```

**它從來沒問過 recipe「這個號碼是什麼意思」。** 而三份出貨的 recipe 都是自己
取名字、自己編號的。2026-09-20 實測（跑 `recipes/` 三份，讀 `decide` 的葉子）：

| recipe | 膠囊上的字 | 現在 | 應該是 |
|---|---|---|---|
| `ebi-die-to-die` | nothing stands out（沒找到缺陷）| **紅** | 綠 |
| | a spot stands out（找到缺陷了）| **綠** | 紅 |
| `one-image-uniformity` | measured（量到了、沒異常）| **紅** | 綠 |
| `rsem-worst-box` | nothing stands out | **紅** | 綠 |
| | one box stands out | **綠** | 紅 |
| | more than one box is off（更嚴重）| **灰** | 紅 |

**紅綠是反的，而且三份都反。** 走查只抓到均勻度那一條，是因為那一條的字
（`measured`）跟顏色的矛盾最刺眼；另外兩份剛好「找到缺陷 = 綠」，看起來像
是在慶祝，而沒有人會停下來想那是錯的。

這是推廣鐵則的正中央：**目標使用者不會去讀 bin 的號碼，他只看顏色。**

---

## 2. 分析：畫面上有**兩套顏色**，而它們問的是不同的問題

這是這一輪最重要的一件事，寫在前面免得又被合成一套：

| | 誰 | 問的問題 | 現況 |
|---|---|---|---|
| **身分色** | `decide_tree.leaf_color` | **這是哪一類**（bin 2 跟 bin 3 要分得出來）| ✅ 對的。一個 bin 一個穩定的顏色，樹的畫布、縮圖牆、判定表、報表共用（I1 才剛把縮圖牆接進來）|
| **判斷色** | `VerdictChip` 的 `tone` | **這是好消息還是壞消息** | ❌ 寫死在號碼上 |

⚠ **不要把 `outcome` 塞進 `leaf_color`。** I1 學到的那一課是「同一個問題不准
有兩份答案」，而這裡是**兩個不同的問題** —— 合起來的話，三類都是好消息的
recipe 在畫布上會變成三個一模一樣的綠色，而使用者就分不出那三類了。

### 順手查出來的：`is_real_style` 是一條死路

`VerdictChip.set_verdict(..., is_real_style=False)` 的那個反轉模式
**沒有任何呼叫端** —— [`studio.py:3567`](../../d4t/ui/studio.py) 只傳
`verdict_bin` 與 `label`。所以今天的對應是無條件的「bin 1 綠、bin 0 紅」。

它當初（U13）買到的東西**不能跟著刪**：顏色翻面的時候**字要跟著翻面**
（`real` / `nuisance`），而且有第三個通道（框線樣式 `_TONE_BORDER`）給色覺
缺陷者（男性約 8%）。F119 要做的是**把那一套接到一個真的資料來源上**，
然後把接不上的那個旗標刪掉。

---

## 3. 設計：葉子自己宣告

### 3.1 欄位

```python
@dataclass(frozen=True)
class TreeLeaf:
    bin: int
    label: str = ""
    outcome: str = ""        # "" | "good" | "bad" | "neutral"

@dataclass(frozen=True)
class Rule:
    when: str
    bin: int
    label: str = ""
    outcome: str = ""
# DecideSpec 再加一個 otherwise_outcome: str = ""
```

**三個名字跟 `tone` 的詞彙一比一**（`chip_good_bg` / `chip_bad_bg` /
`chip_neutral_bg` 已經在 `theme.TOKENS` 裡）—— 中間不要再放一張翻譯表，
那種表遲早會漂。

### 3.2 `""` = 未宣告 → **灰**，不是猜一個

這是整份設計裡唯一需要克制的地方。今天的行為是「**很有把握地給一個錯的
顏色**」，而那比沒有顏色糟得多：使用者會相信它。所以沒宣告的時候膠囊是
中性灰（框線 dashed），字照舊顯示 recipe 取的名字。

⚠ **不准補一條「bin 0 一律是好消息」的猜測** —— 這次就是這樣錯的
（`ebi-die-to-die` 的 bin 0 是好消息、`one-image-uniformity` 的 bin 0 也是，
但這兩件事成立是巧合，而 `rsem-worst-box` 的 bin 2「更多格不對」比 bin 1 更
嚴重，任何按號碼排的規則都答不出來）。

### 3.3 不需要遷移（而這件事要寫出來）

鐵則 9 說「遷移只能靠**舊東西在不在**判斷」。這裡**沒有舊欄位** ——
`outcome` 是新加的、預設 `""`，而 `""` 對舊檔案與新 recipe 的意思**完全相同**
（都是「沒宣告」）。所以：

* **`RECIPE_VERSION` 不動**（目前 5），不加遷移道數；
* `to_json_dict → from_json_dict` 仍然是 identity（`workers=1` 與 `workers=2`
  算出同一份結果的那條路不受影響）；
* **空字串不寫進 JSON**（同 `label` 的既有寫法），所以沒標的 recipe 存出來
  一個位元組都沒變。

要動的是**三份出貨的 recipe**：在同一輪把 `outcome` 標好，
`tests/test_shipped_recipes.py` 本來就會真的跑它們。

### 3.4 一個 bin 被兩片葉子宣告成不同的 outcome

**第一個贏**，判準逐字照抄 `DecideSpec.bin_labels()` 的那一段（由上往下讀，
跟判定本身同一個方向）。新增 `bin_outcomes()` 放在它旁邊 —— 兩支同樣是
「葉子上存得下來、只是沒有人拿去畫」的那條缺路，所以它們該住在一起。

⚠ 同一個 bin 被標成一好一壞是**使用者寫錯了**，不是要猜的東西：
加一條 lint（`conflicting-outcome`，warning）。那一條照 F118 的規矩交結構
（`names` = 那個 bin 的兩個名字、`advice` = 怎麼修）。

### 3.5 畫面：葉子上多一格

`tree_panel` 的葉子今天是 `[類別名] [bin ▾]`（`_build_leaf` 與分支那一列各
一份）。多一排膠囊：

```
[類別名]  [bin ▾]  [ 好消息 | 要注意 | 中性 ]
```

* **一格選項＝一排膠囊**（CLAUDE.md §3 的 `chip_choice`），不是下拉；
* 字是使用者的詞不是程式的詞：**好消息／要注意／中性**（不是 good/bad/
  neutral —— 那三個是 JSON 的鍵）。走 `ui/strings.py`；
* 沒選的時候三顆都不亮 —— 「還沒說」要跟「說了是中性」分得出來。

### 3.6 用在哪裡

**這一輪只接判定膠囊那一個**（D2 問的就是它）。接得到而這一輪**不做**的，
列在這裡免得下次又從頭找：

| 還可以接的地方 | 為什麼這一輪不做 |
|---|---|
| Results 表的警示欄 | 那一欄現在講的是「跑失敗了沒」，跟「判成什麼」是兩件事，混進去要先想清楚 |
| HTML 報表的判定表 | `verdict_rows` 已經有 `colour`（身分色）；再加一欄是版面決定，要看過真的報表再說 |
| 縮圖牆 | **不要**。縮圖上要的是「哪一類」（I1 剛修好），不是「好不好」|

---

## 4. 步驟（一步一個 commit，可以停在任何一步）

| 步 | 做什麼 | 買到什麼 | 風險 |
|---|---|---|---|
| **1** | core：三個 `outcome` 欄位 ＋ `DecideSpec.bin_outcomes()` ＋ serde（空字串不寫）| 資料存得下來 | 低 —— 沒有人讀它 |
| **2** | `VerdictChip` 改吃 `outcome`（三個通道：顏色／字／框線都同一個來源），刪掉 `is_real_style`；`studio.py` 的呼叫端傳 `bin_outcomes()` | **D2 的畫面修好**（沒標的變灰）| 中 —— 動到 `studio.py`，⚠ `HARD_CAPS` 只准往下，要一行換一行 |
| **3** | 三份出貨 recipe 標好 outcome | 三份的膠囊都對了 | 低 —— `test_shipped_recipes.py` 會跑 |
| **4** | `tree_panel` 葉子上那一排膠囊 ＋ `viewmodel.set_tree_leaf(outcome=…)` | 使用者自己改得到 | 低 |
| **5** | `conflicting-outcome` lint（照 F118 交結構）| 寫錯講得出來 | 低 |

**第 1～3 步是一組**：做完那三步畫面就對了，第 4 步之前使用者只能用手改
JSON（而三份出貨的已經標好了，所以那段日子不難過）。

---

## 5. 測試

* **一條釘住 D2 本身**：三份出貨 recipe 的每一片葉子，`bin_outcomes()` 查得到
  一個非空的值 —— 這一條會在有人加第四份 recipe 而忘了標的那天紅。
* **一條釘住「未宣告 = 灰」**：沒有 `outcome` 的 recipe → `tone == "neutral"`，
  **而且不是 good 也不是 bad**（擋掉「順手補一條猜測」那條路）。
* **三個通道要一起動**（U13 的原意）：`outcome` 換一個值，顏色、字、框線
  樣式三個都要跟著換 —— 只改顏色的那天這一條要紅。
* **既有的兩支要看過**：`tests/test_ui_verdict_wording.py` 與
  `tests/test_ui_widgets.py` 現在斷言在 `is_real_style` 上，第 2 步會動到。
  ⚠ 照 F118 §5 學到的：斷言改成問**結構**（`outcome`），不是問句子。
* **serde identity**：`to_json_dict → from_json_dict` 對「有標」與「沒標」
  兩種都要是 identity（鐵則 9 的那條路）。

---

## 6. 風險與已知的坑

* ⚠ **`studio.py` 的 `HARD_CAPS` 只准往下**（F116 之後）。第 2 步要往它加東西
  就得先從它手上搬走等量的 —— 或者把那幾行寫成一行換一行（F118 第 2 步就是
  這樣過的，可行）。
* ⚠ **舊 recipe 打開會從「有顏色」變成「灰」。** 那是**刻意的**（§3.2），但
  使用者第一次看到會覺得壞了 —— 所以第 4 步那一排膠囊不要拖太久，而且
  Problems 列值得有一條 `info` 說「這份 recipe 還沒說哪一類是好消息」。
  ⚠ **`info` 不是 warning**：一條每份舊 recipe 都會亮的 warning 會被學會忽略
  （`_feature_collisions` 上面那段說明記過同一件事）。
* **不要碰 `leaf_color`**（§2）。
* 「好消息／壞消息」在多類別上可能不夠用（例如「要人看一眼」）——
  `neutral` 先當那一格用。真的不夠再談，**不要現在就發明第四個值**。

---

## 7. 什麼叫做完

* 三份出貨 recipe 的膠囊顏色，唸給一個不寫 code 的人聽，他點頭。
* `is_real_style` 從 repo 裡消失，而 U13 買到的三個通道一個都沒少。
* 一份沒標的 recipe 是**灰的**，而且畫面上有一句話說它為什麼是灰的。
* F117 的 D2 可以標成關掉。
