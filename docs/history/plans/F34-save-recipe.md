# F34 — 存檔 recipe ＋ 一份出貨的 characterization recipe

**狀態**：✅ 收斂（2026-08-26）。存檔（`Recipe.save` / `Ctrl+S` / `Ctrl+Shift+S`）
與 `recipes/ebi-to-api-characterization.json` 都上線了；**F35** 的兩支
`configuration_issues` / `configuration_hints` 見 §5。

> **F35 也住在這一份**（§5：「跑不起來」與「你八成不是這個意思」是兩件事）。
> 它是同一輪、被同一個問題逼出來的 —— 拆成兩份文件的話，§3.2 的「為什麼第一版
> 那樣寫」就跟「後來怎麼修」分家了，而那正是這個 repo 最怕的形狀。

> **d4t — defect**　·　2026-08-26
> 使用者：「接下來幫我做一個重要的功能，存 recipe，做完之後幫我建一隻
> Characterization recipe（讓我開啟後載入檔案能直接跑）。另外問一下 output
> 段要怎麼接」
>
> 同一輪的三個追問把 §3.2 整個翻掉了：「Rank within 的意思是?」→
> 「但如果只勾 XINDEX 會發生什麼事?」→「照你建議的做」。**F35（§5）是那三句
> 逼出來的** —— 第一版為了繞開一條放錯地方的 lint，把一個猜得到的設定留空了。

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

### 3.2 `rank_within` 預先填好、`rank_by` 留空（**F35 修正了第一版**）

第一版把**兩格都留空**，理由是 `pair_source.configuration_issues` 會把
「填了 Rank within 但 Rank by 是空的」判成 **error**，而 CLI 看到 error 就整個
不跑 —— 一份為了「打開就能跑」而做的 recipe，打開就跑不動。

那個處置是**繞路，不是修**。使用者當天追問「`Rank within` 的意思是？」與
「但如果只勾 XINDEX 會發生什麼事?」之後，真正的形狀才清楚：

* `rank_within` **猜得到**（`XINDEX`+`YINDEX` 是絕大多數站點的 sample 規則），
  而且**填錯不會有任何人講話** —— 只勾一欄就是把整整一行 die 併成一組，
  跑得完、數字看起來正常。實測 4×3 顆 die、每 die 取前 2 名：只勾 `XINDEX`
  讓「① 抓到了」從 24 顆掉到 8 顆，全部灌進「② 排名太低」，**整份報告的結論
  反過來**。唯一的線索是 `pair_die_total`。
* `rank_by` **猜不到**（每台機台的分數欄名字不一樣）。

所以：**猜得到而且猜錯很貴的那一格要預先填好**，猜不到的那一格留空。
擋路的那條 lint 在 F35 修掉了（見 §5）—— 它一開始就放錯地方。

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
| ~~兩格都留空~~ | **第一版就是這樣，F35 改掉了** —— 見 §3.2。`rank_within` 猜得到，而且猜錯是安靜的 |
| 把 `configuration_issues` **整支**降成 warning | 對 `output_char` 的空資料夾那一條是**對的**（那張卡真的會拋）。F35 的做法是**分成兩支**，不是降級 —— 見 §5 |
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

## 5. F35：那條擋路的 lint 一開始就放錯地方（2026-08-26 同一輪）

`Step.configuration_issues` 的契約寫得很明白（F7-13 的註解）：

> 「空字串的模板是完全合法的 str —— **但那張卡跑起來每一顆都會失敗**」

**error 這個級別就是踩在那句話上。** 而 F33 放進去的那條訊息不符合它：
「填了 Rank within 但 Rank by 是空的」的卡片跑得完，只是少寫兩個特徵。

於是分成兩支，判準是一句話：

| | 契約 | 級別 | lint code |
|---|---|---|---|
| `configuration_issues` | 這張卡**會拋**，或什麼都不產出 | error | `not-configured` |
| **`configuration_hints`** | 它**會跑**，但你八成不是這個意思 | warning | `half-configured` |

而 warning 這一級**要講得出使用者接下來看得到什麼**，不然它只是一句沒有後果
的碎念。`pair_source` 的那句因此多了一段：「Until then every matched defect
answers “no rank” in the decision.」—— 指的正是判定樹上第 9 類那片葉子。

為什麼是兩支方法，不是在同一支上加一個級別欄位：**級別是呼叫端的事**
（lint 決定怎麼呈現），而卡片要回答的是一個它自己答得出來的問題 ——
「這會不會跑不起來」。

⚠ 這是一個**新的擴充點**（`Step` 上多一個 classmethod）。既有的十來張卡一個字
都不用改：預設回空 list。

## 6. 驗收

- 全新：`tests/test_recipe_save.py`（11）、`tests/test_ui_save_recipe.py`（12）、
  `tests/test_shipped_recipes.py`（12）。
- `tests/test_pair_source.py` 加兩條：
  `test_ticking_only_xindex_pools_a_whole_row_of_dies`（分組的語意，
  **而且沒有任何人講話**）與 `test_half_filled_ranking_is_a_hint_not_a_blocker`。
- `tests/test_ui_f7_16_safety_net.py` 的反向斷言（「`_on_save_recipe` 不存在」）
  換成兩支正向的：存得下去才算可以關、存不下去不算可以關。
- 核心全套 + UI 逐檔 + `tools/freeze_golden.py --check` 三份全綠
  （黃金 recipe 一個位元都不該動 —— 這一輪沒有碰演算法）。
