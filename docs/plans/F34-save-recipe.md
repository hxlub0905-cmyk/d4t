# F34 — 存檔 recipe ＋ 一份出貨的 characterization recipe

> **d4t — defect**　·　2026-08-26
> 使用者：「接下來幫我做一個重要的功能，存 recipe，做完之後幫我建一隻
> Characterization recipe（讓我開啟後載入檔案能直接跑）。另外問一下 output
> 段要怎麼接」

---

## 0. 為什麼是現在

存檔在 **2026-08-16**（`8ffe366`）被拿掉，理由寫得很清楚：

> 「先把整個 engine 用好，再來支援」

而 **Phase 1「讓數字可信」也在同一天收斂**。那個前提從那天起就已經到期，只是
沒有人回來看它 —— 十天裡 `CLAUDE.md`、`README.md`、`docs/ROADMAP.md` 三處
都還在說「不支援」，`d4t/ui/studio.py` 裡有兩段註解拿「反正存不了檔」當論證。

這一輪把它接回來，並且**把那三處＋兩段註解一起改掉**。這件事本身是這個 repo
的老問題（`CLAUDE.md` §0：同一件事寫在兩個地方，抄出來的那份一定會漂）。

---

## 1. 引擎：`Recipe.save()`

一支函式、十幾行，形狀跟 2026-08-16 拿掉的那一支幾乎一樣（utf-8、`indent=2`、
`.tmp` + `os.replace`），加了兩件當時沒有的：

| 加的 | 為什麼 |
|---|---|
| 父目錄不存在就建 | 使用者在另存對話框打一個還不存在的資料夾是常態，不是錯誤 |
| 失敗時清掉 `.tmp` | `json.dump` **邊算邊寫**，中途失敗會留下半份檔案 —— 而它跟使用者要的檔名只差三個字元 |

### 1.1 `save` 與 `load` 是**不對稱**的一對（而那是刻意的）

* `save` 寫的永遠是**現在這一版的形狀**（`to_json_dict` 會把 `app_version`
  蓋成現在這一版 —— 這一欄要回答的是「這個檔案是誰寫的」）。
* `load` 會多跑一道**只在讀檔案時才成立**的遷移
  （`_migrate_rescued_feature_names`，它不冪等，理由見那支的說明）。

合起來的後果是這個功能真正的行為改變：

> **打開一份舊檔案再存回去，磁碟上的東西會被換成新形狀。**

那是對的 —— 使用者看到的就是新形狀，存出跟畫面不一樣的東西才是說謊 ——
但它**不是 no-op**，所以要寫下來。

### 1.2 存檔**不做驗證**

一份還在調、`validate` 有紅字的 pipeline 必須存得下來。存檔是「別弄丟我的
工作」，不是「你做完了嗎」；擋在這裡的話，使用者中途要離開時唯一的選擇是丟掉它。
健檢在畫布上一直都在講話，不必在這裡再擋一次。
迴歸測試：`test_it_saves_a_recipe_that_does_not_validate`。

---

## 2. Studio

| 東西 | 行為 |
|---|---|
| 工具列 **`Save recipe…`** | 接的是 `Ctrl+S` 那一支（按鈕的意思是「存起來」，不是「我要選路徑」）|
| **`Ctrl+S`** | **存回原檔**；沒有原檔才問路徑 |
| **`Ctrl+Shift+S`** | 一定問路徑；沒打副檔名就補 `.json` |
| 標題列 **`*`** | 「還沒存」的常駐訊號 |
| 按鈕變灰 | pipeline 是空的時候，tooltip 講原因（推廣鐵則）|
| tooltip | 有原檔時講**存回哪一個檔案** —— `Ctrl+S` 不再問，所以那件事要在按下去**之前**看得到 |
| 關窗提示 | 第三個答案「存」回來了，預設仍然不是「丟掉」|

### 2.1 兩個被推翻的舊論證

1. `_adopt_threshold_as_a_tree` 的 docstring 寫著「而 Studio 現在又存不了檔
   （2026-08-16 拿掉），所以磁碟上的東西不會被改寫」。**那句話現在是假的**：
   按一下 `Ctrl+S`，磁碟上那份門檻 recipe 就變成一份判定樹 recipe。
   不會安靜發生（載入時狀態列已經講過一次），而且照畫面存才是對的 ——
   但論證要換掉。測試：`test_a_threshold_recipe_saves_as_the_tree_the_user_is_looking_at`。
2. `unsaved_changes` 的 docstring 寫著「**沒有任何辦法保住這份 pipeline**」。
   那在那十天裡是真的（「還沒存」恆真，講了等於沒講），現在回到原本的意思：
   有一個辦法，而他還沒用。

### 2.2 一個順手修掉的假訊息

`_decide_unknown` 的 `unknown-feature` 警告一律接一句
「every defect will fail on this line at run time」。對**帶 `fill` 的 `let`**
那是假的 —— 那一行的意思正是「這個數字可能不在」。這支 lint 本來就看得見
`fill`（它拿它來登記 `<name>_missing`），只是沒有拿來講話。

它剛好只在 `fill` 真的派上用場的時候出現，而這一輪出貨的 recipe 正是那個形狀。

---

## 3. `recipes/ebi-to-api-characterization.json`

### 3.1 「載入後能直接跑」的**誠實版本**

有兩格永遠不可能寫進出貨的 recipe，而它們是不同的東西：

| 格子 | 為什麼不能寫死 | 這一輪的處置 |
|---|---|---|
| 第二份 lot 的**路徑** | 路徑不進 recipe（F15）—— 同一份 recipe 換一批資料照跑 | 沒得處置。載進去狀態列就講：「Open one with “Open data…” on this card」|
| **`Rank by`**（機台自己的分數欄）| 每一台機台那一欄叫的名字不一樣 = 站點資料 | 見 §3.2 |
| 輸出**資料夾** | 同上 | 預設 `char_report`（相對路徑）—— 給一個值而不是留空，`configuration_issues` 才不會判 error |

### 3.2 為什麼 `rank_within` 也留空（被否決的方案）

第一版填了 `rank_within = "XINDEX,YINDEX"`、`rank_by = ""`。
結果是 `pair_source.configuration_issues` 判成 **error**（「填了 Rank within
但 Rank by 是空的」），而 CLI 看到 error 就整個不跑 —— **跟這份 recipe 要做的事
正好相反**。

改成兩格都留空。填一格 `Rank by` 就開始有排名（整份排一組），再填
`Rank within` 才變成每個 die 各自排 —— 那也是比較好的上手順序。

**而「還沒設定」不是安靜的**，靠的是 `Let.fill`（F24 ⑤）：

```
let  sample_top = 200
let  die_rank   = pair_die_rank        missing ⇒ 用 -1     → 每顆都有 die_rank_missing
```

```
① pair_found < 1 ?            yes → bin 3  EBI never detected it
② die_rank_missing > 0 ?      yes → bin 9  no ranking column picked yet
③ die_rank <= sample_top ?    yes → bin 1  caught
                              no  → bin 2  detected, ranked too low to sample
```

第 9 類那片葉子就是**報表在告訴使用者還有哪一格沒填** —— 出現在他真的會看的
地方，而不是一份看起來很正常、其實每一顆都判錯的結果。
`decide_unanswered` 全程維持 0（第一問就是 `pair_found`，③ 那一支問不到別的）。

### 3.3 被否決的其他方案

| 方案 | 為什麼不 |
|---|---|
| `rank_by` 填一個常見欄位（`DEFECTAREA` / `DEFECTID`）| 那是**替使用者決定他的 sample 準則**，而且欄位不存在時是掛載當下的硬錯 |
| 把 `configuration_issues` 降成 warning | 對 `output_char` 的空資料夾那一條是**對的**（那張卡真的會拋）。為了一張卡把整個機制降級，就是為了省事把擋板拆掉 |
| 樹上不問「有沒有排名」，讓缺值答「否」| 缺值走 no 的話全部落在 bin 1 或 bin 2 —— 一份看起來正常的錯結論，正是這個 repo 最怕的形狀 |
| 放回 `examples/` 並打開 `SHOW_SAMPLE_ENTRIES` | 範本庫是另一件事（一個列表 UI）。使用者要的是「一個檔案，打開就能跑」|

### 3.4 不會爛掉（`tests/test_shipped_recipes.py`）

上一批範例 recipe 死於**沒有人測**。這一次三種問題都問：

1. 載得進來、`validate` 沒有 error、round-trip identity、有 `app_version`；
2. **線在該在的埠上**（小圖 → `template`、大圖 → `search`），
   而 Output 卡**沒有任何線**；
3. **真的跑一次**：不改一個字跑得完（全部 bin 9）；填上排名欄位之後
   ① ② ③ 三類都數得出來；報表、CSV、圖、recipe 複本都寫得出來，
   而配不到的那一格是 `<td class='none'>` 不是破圖。

---

## 4. 「output 段要怎麼接」

**不接。** Output 卡沒有輸入埠：

```python
class _OutputStep(Step):
    scale = SCALE_LOT
    @classmethod
    def resolve_reads(cls, params):  return []
    @classmethod
    def resolve_writes(cls, params): return []
```

它只要**在 route 上**就會跑 —— `run_batch_steps` 是整批跑完之後照
`execution_order` 各跑一次。畫布上它待在自己的虛線區塊裡（`OUTPUT` /
「once per lot」），副標寫 `(not connected)`，那是**正常的**。

由此來的三件事：

* **拉一條線進去**的話那條線落在一個不存在的埠上 → 畫布說謊。
* 它要看哪一條影像流，是**打字**填的（`Left picture` / `Right picture`），
  型別是 `str` 不是 `image_key` —— 因為 `image_key` 的欄位在設定區是唯讀的
  （F9-6：來源只在畫布上拉線決定），而這張卡不上畫布接線。
* **試跑不寫檔**（使用者 2026-08-20 定調）：`run_trial` 根本不叫
  `run_batch_steps`。要寫出東西請按 **Run all**（或 CLI）。

測試：`test_the_output_card_is_wired_to_nothing_on_purpose`。

---

## 5. 驗收

- `tests/test_recipe_save.py`（11）、`tests/test_ui_save_recipe.py`（12）、
  `tests/test_shipped_recipes.py`（11）全新。
- `tests/test_ui_f7_16_safety_net.py` 的反向斷言（「`_on_save_recipe` 不存在」）
  換成兩支正向的：存得下去才算可以關、存不下去不算可以關。
- 核心全套 + UI 逐檔 + `tools/freeze_golden.py --check` 三份全綠
  （黃金 recipe 一個位元都不該動 —— 這一輪沒有碰演算法）。
