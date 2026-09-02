# F76 — Feature 面板大改版

**狀態：做完，合併回 `main`（2026-09-02）。這一份是紀錄，不再改。**

| 刀 | 狀態 |
|---|---|
| 1 區域顏色的序 | ✅ `verdict_features._regions_in_wiring_order` —— 序由區域線給 |
| 2 說明欄 ＋ 單位 | ✅ `Step.FEATURE_UNITS` / `VARIANT_UNITS` / `VARIANT_GLOSS` |
| 3 抽 `ui/feature_tree.py` | ✅ 純搬家，`results_table` 吃同一份 |
| 4 新 `ui/feature_panel.py` | ✅ Preview 換過去，`studio._feature_sections/_feature_specs` 退場 |
| 5 沒判定就不畫 ADC | ✅ `studio._sync_verdict_block` —— 換成一句話 ＋ 那顆鈕 |
| A `<judge>_outlier` 停產 | ❌ 不停產（使用者定調：先只改顯示） |
| B `glv_worst_baseline` | ✅ 開了 |
| C 欄名 | 暫定 `typical of them all` / `the odd one out` / `furthest on this stat`（`feature_panel.VARIANT_COLUMN_LABELS` 一處改字） |

`widgets.FeatureTable` **同一天刪掉了**（使用者定調）。它走完了 §5 那張價目表
的全程：先收起來（Preview 換成新面板、舊表沒有呼叫端）→ 量代價（零個生產
呼叫端、零份 recipe、零個黃金值）→ 刪。

⚠ **刪的過程救回一個真的 bug**：那張表守著四條不變量，其中「沒人認領的特徵
仍然要出現」在 `panel_model` 第一版被違反了 —— `bound_specs` 沒宣告的名字被
安靜地丟掉。四條全部搬到 `tests/test_ui_feature_panel.py`。

### 收工之後又抓到的四個（都在同一天）

使用者跑起來截了圖、又叫我自己造一份 recipe 測 —— 兩件事各抓到東西：

| # | 病 | 病根 |
|---|---|---|
| 1 | 設定區寫「nothing picked yet · 0 picked」，特徵表卻列著三個值 | `METRIC_GROUPS` 加了 `"Sharpness"`，`METRIC_GROUP_ORDER` 沒加 → 那一群的膠囊一顆都不畫，而引擎照樣拿預設值在算 |
| 2 | IQI 沒勾，它的滑桿還擺在那 | 我以為 `show_when` 對逗號清單用不了 —— **是錯的**，`param_visible` 本來就做成員比對（F37）|
| 3 | 「Name these results」出現在 IQI 的標題底下 | 共用的 `output_prefix_spec` 沒有 section，掉進前一格的分節 |
| 4 | `value_text("glv_worst_i")` 回 `None`，而那個數字就寫在標題行上 | 升格到標題／變成「← #46」地址的 13 個名字沒有進 `_values` —— **取用口跟畫面說的是兩件事** |

四個都配了測試。第 1 個尤其值得記：它**跑得完、有數字、看起來完全正常**，
而畫面說 0 個、引擎算 3 個。

---

**原始提案（2026-09-02 上午）。**

使用者：「目前 feature 顯示面板跟後面帶的數值我覺得好亂」→
「feature 面板我建議大改版，你可以先瀏覽整個 studio 架構 我們再來重新設計」。

> **這一份的第一版提了四刀。瀏覽完 studio 之後有一刀作廢了** —— 我當時要開的
> 那個新面板（卡 › 區域 › 統計量的樹、雙層表頭、維度過濾），**`ui/results_table.py`
> 兩個星期前就寫好了**。詳見 §4。

---

## 0. 先量一次

出貨的 `recipes/rsem-worst-box.json` 攤在 `FeatureTable` 上：

| | 數字 |
|---|---|
| 特徵總數 | **118**（GLV 一張卡佔 **75**）|
| 「What it is」**只是把 id 抄一遍**的 | **36** |
| 說明**跟別的特徵一字不差**的 | **97** |
| 同一區域被畫成**兩種顏色** | 2 個 |

實際畫面（單區域的簡化版，19 列的 GLV 那一段）：

```
## GLV · 19
   glv_q75_typical          189      75th percentile
   glv_q75_outlier          191      75th percentile
   glv_q75_outlier_box       21      75th percentile      ← 這是框號，不是灰階
   glv_median_typical       186      median(gray)
   glv_median_outlier       188      median(gray)
   glv_median_outlier_box    46      median(gray)
   glv_worst_i               21      glv_worst_i
   glv_worst_x              140      glv_worst_x
   glv_worst_y              185      glv_worst_y
   glv_worst_w                9      glv_worst_w
   glv_worst_h                9      glv_worst_h
   glv_worst_score        1.349      glv_worst_score
   glv_worst_value          191      glv_worst_value
   glv_worst_score_median     0      glv_worst_score_median
   glv_worst_score_spread     0      glv_worst_score_spread
   glv_q75_worst            191      75th percentile      ← 跟它的三個兄弟隔了 13 列
   glv_median_worst         187      median(gray)
   glv_boxes_over_k           0      glv_boxes_over_k
   glv_boxes_over_k_frac      0      glv_boxes_over_k_frac
```

---

## 1. 六個病

### ① 顏色指錯區域（**bug**，跟版面無關，先修）

```
between_columns  由 ROI 卡寫的特徵 → region_index 0 → 綠
between_columns  由 GLV 卡寫的特徵 → region_index 1 → 琥珀
```

同一塊、同一張表、兩種顏色，而影像上那個框只有一種。`CLAUDE.md` §3：
「**顏色指錯區域比沒有顏色糟得多**」。原因是 `region_index` 由**每張卡各自算**
（ROI 卡一次只定義一塊，自己的序永遠 0；GLV 卡接三條線是 0/1/2）。
兩份說法 —— 鐵則 10 擋的正是這個。序要由**區域線**給，一份出處。

### ② 說明欄看不見 `variant`

`feature_gloss` 只讀 `spec.metric`，所以 `_typical` / `_outlier` /
`_outlier_box` / `_worst` 四胞胎的說明四行相同，而 `_outlier_box`
（值 21，一個框號）也寫「75th percentile」。

### ③ 36 列的說明只是把 id 抄一遍

`glv_worst_*` 整族 ＋ `glv_boxes*`。`metric_formula` 不認得它們（它們不是統計
量），`_ABS_GLOSS` 只有兩條。而 `Step.feature_help()` 這條路**已經存在**
（2026-09-01 建的），GLV 卡沒填而已 —— 這是最便宜的一刀。

### ④ 四胞胎不相鄰

上面那段 dump 裡 `glv_q75_worst` 跟 `glv_q75_typical` 差 13 列。因為列序 =
`features` dict 的插入序，而 `_worst` 是迴圈最後才寫的。**排版跟著計算順序
走，不是跟著意思走。**

### ⑤ `_outlier` 指的是另一格，而畫面上沒有任何東西說

實測（24 顆合成 rsem，judge = `glv_q75`）：

| metric | `<m>_outlier_box == glv_worst_i` |
|---|---|
| `glv_q75`（＝ judge）| **24/24** |
| `glv_median` | 4/24 |
| `glv_mean` | 5/24 |
| `glv_std` | 5/24 |
| `glv_max` | 2/24 |

兩件事同時成立，而現在的表一件都講不出來：

* **judge 那個量的 `_outlier` 是 `_worst` 的重複**（24/24 相同 ——
  數學上不保證，但兩者只差「中位數含不含自己」與一個幾乎是常數的分母）。
  這個 repo 已經為同一種情形立過規矩：`WORST_FEATURES` 的註解拒絕開
  `score_max`，理由是「同一個數字兩個名字，CSV 上沒有任何線索說它們是同一個」。
* **其他量的 `_outlier` 指的是另一格**（79–92% 的情況），
  而名字讀起來像「最糟的那個」。使用者原話：「反而這樣會誤導別人以為他是最
  worst 的」。

⚠ **它有真的用途**：`_outlier` 回答的是「**這一欄自己**最極端的是哪一格」，
而那跟 judge 挑的贏家常常不同格。五格的最小例子（judge = `glv_median`）：

```
      第 i 格   median   std
        #0        100      5
        #1        101      5
        #2         99      5
        #3        100     30   ← std 這一欄最極端
        #4        160      6   ← median 這一欄最極端 → judge 挑它當贏家

judge 是 median  →  glv_worst_i = 4（整張卡只有一個贏家）

glv_median_worst    = 159.9   #4 的 median
glv_median_outlier  = 159.9   median 這欄最極端 → 也是 #4（同一格）
glv_std_worst       =   6.2   #4 的 std          ← 贏家的身分證
glv_std_outlier     =  29.8   std 這欄最極端 → #3  ← 另一個人
glv_std_outlier_box =     3
```

`6.2` 與 `29.8` 是**兩個不同的格**，而名字上沒有任何線索。

（2026-09-02 起連唯一用它的那份出貨 recipe 也走了 —— `patch-dsnr-by-class`
的判定樹用著 `cmp_snr_mean_outlier`，而那份被使用者刪掉了。所以停產它的代價
比 §7 A 寫的時候更低，只剩使用者自己手上的 recipe。）

### ⑥ ADC 那一塊在還沒有 ADC 的時候佔著位子

實測（同一份 recipe，把 decide 拿掉）：

```
沒有 ADC:  Verdict chip = '—'   Path = ''   score 那一列不存在
有 ADC  :  Verdict chip = 'bin 1 · ≥ threshold'   Path = 'bright_score >= 200 ? yes'
```

使用者：「大部分人應該建立 Pipeline 時 ADC 不會放到第一個」。對 —— 而在那段
時間裡，Preview 欄最底下永遠是一個寫著 `—` 的 chip 加一片空白。**它不是壞的，
它是「什麼都沒說」**，而那塊面積正好是量測卡最需要的地方。

另外 `score` 這個字在同一欄裡有兩個意思（ADC 分數 vs `glv_worst_score` 的
σ），而 `glv_worst_score_median` 讀起來像「分數的中位數」。`CLAUDE.md` §0 的
**bundle** 故事講的就是這件事。

---

## 2. Studio 架構（瀏覽的結果）

```
StudioWindow (studio.py, 6,667 行 / 258 方法)
└ root QSplitter ──────────────────────────────────────────────────────────
  ├ 左  LibraryPanel                    widgets.py        卡片庫
  ├ 中  QSplitter(vertical)
  │     ├ 上  PipelineCanvas            canvas.py         畫布（卡＋線）
  │     └ 下  QStackedWidget
  │           ├ 0 ParamForm             widgets.py        這張卡的設定
  │           ├ 1 RouteByBox+DecidePanel route_panel/decide_panel.py
  │           └ 2 TreePanel             tree_panel.py     判定樹的一步
  └ 右  preview_pane（單顆）            studio._build_preview_pane
        ├ column_header "Preview"
        ├ nav      ◀ ▶ [defect ▾]  ebi_patch · defect 1 / 24
        ├ stream   Image stream [test ▾]  ☐ Compare        x,y,gray
        ├ image_stack  empty_state | ImageView (×2)
        ├ btn_region_check
        ├ tabs     [ Card ][ Features ]
        ├ bottom_stack
        │    ├ 0 inspector_host   inspectors.py（每張卡一個儀表）
        │    └ 1 feature_table    widgets.FeatureTable   ← 要改的那一塊
        └ verdict row   Verdict [chip]   Path: …          ← 病 ⑥

ResultsWindow (results.py) ── 跑完才開
  ├ toolbar summary + Run all
  ├ view_stack   0 GalleryPanel (gallery.py) | 1 ResultsTablePane (results_table.py)
  ├ WhyPanel     why_panel.py     這顆為什麼判成這樣
  └ HistogramWidget                分數分布
```

**特徵值在六個地方出現**，而它們對「怎麼分組」有**兩套**說法：

| 在哪 | 分組依據 | 誰算的 |
|---|---|---|
| Preview 的 `FeatureTable` | 卡（一層） | `studio._feature_sections()` 讀 `meta["feature_owner"]` |
| Results 的 `ResultsTablePane` | **卡 › 區域 › 統計量**（三層） | `verdict_features.bound_specs()` ＋ `results_table.column_tree()` |
| `WhyPanel` | 判定樹的一步 | `verdict_trace` |
| `GalleryPanel` | 一顆一個數字 | — |
| `inspectors` | 一張卡一個儀表 | 卡片自己的 meta |
| CSV / report | 同 Results | `core/export/report.feature_keys` |

---

## 3. ⚠ 我原本要開的那個新面板已經存在了

`ui/results_table.py` 的模組說明寫著（PR-1／PR-3，2026-08-27）：

* **兩層欄位**，分層**自動由 recipe 推導**，唯一出處 `verdict_features.py`；
* **判定層預設可見** ＝ 徽章欄 ＋ base ＋ class ＋ 判定引用的特徵；
* 其餘照產出卡分組摺疊，一顆「All measurements (N)」＋ 欄位搜尋框；
* **診斷欄兩層都不出現**，除非判定引用了它；
* 警示**只**來自 `diagnostic_alarms`（UI 不對數值型診斷發明門檻）；
* `column_tree()` 把欄位排成**卡 → 區域 → 統計量**，摺疊順序／雙層表頭／
  維度過濾**共用同一份**；
* 表頭上半是**區域**（`theme.region_hex` 同一組顏色），下半是統計量短標籤
  （`widgets.metric_face`）；
* 三顆維度下拉（Region / Statistic / Card）＋ chips。

**這正是第一版提案要蓋的東西。** 而 Preview 那一塊走的是另一條、弱得多的路
（`_feature_sections` 只分到卡）。兩份說法已經漂開了 —— 病 ① 的顏色就是漂的
第一個症狀（`bound_specs` 那條路的 `region_index` 是對的）。

所以這一輪**不是加一塊面板，是把 Preview 接到已經在跑的那一份上**。
Results 是 *N 顆 × M 特徵*，Preview 是 *一顆*，所以 Preview 是那張表的
**轉置**：同一棵樹、同一組標籤、同一組顏色，換一個方向畫。

---

## 4. 新面板的形狀（要拍板的就是這一張）

```
┌ Features ─────────────────────────  [搜尋…]  [只看判定用的 ▾] ┐
│                                                                │
│ ▾ GLV › cell                                        100 boxes  │
│      最異常的一格  #21   1.35 σ   ·   0 格超過 3σ              │
│                                                                │
│      統計量      這批典型     #21 那格     自己最極端          │
│      ─────────────────────────────────────────────  gray       │
│      Q75            189          191        191  = 同一格      │
│      median         186          187        188  ← #46         │
│                                                                │
│ ▾ ROI › cell                       定位成功 · 100 格 · 掉邊 10 │
│ ▸ Load one image  ·  1                                         │
│ ▸ Diagnostics  ·  2                                            │
└────────────────────────────────────────────────────────────────┘
```

### 六個決定

1. **一列一個統計量，四胞胎變四欄。** 這是唯一誠實的排法：它們本來就是同一個
   量的四種身分。19 列 → 1 個標題 + 2 列。病 ②④⑤ 一次解決。
2. **`_outlier` 那一欄叫「自己最極端」，而且框號永遠貼著值。**
   跟 judge 同一格時寫 `= 同一格`，不同格時寫 `← #46`。使用者第 1 題的答案：
   **不刪它（有 recipe 在用），改成讓「它是另一格」在畫面上跑不掉。**
3. **`glv_worst_*` 那 13 個升成標題那一行**（`#21 · 1.35σ · 0 格超過 3σ`）——
   它們回答的是「這一區的結論」，而那是打開這一段的第一個問題。
   x/y/w/h 收進 tooltip（它們是給疊圖用的座標，不是給人讀的）。
4. **單位跟著「列」走，不跟著「格」走**（列尾一個 `gray`）。一列四個值同單位，
   所以寫一次。σ / box / px / count / ratio / flag 同理。
5. **沒有判定就沒有 ADC 那一塊。** Verdict chip 與 Path 整塊不畫，換成一句
   可以照做的話 ＋ 一顆跳到 Decide 欄的鈕。有判定才長出來。（病 ⑥）
6. **`score` 這個字在畫面上只留給 ADC。** `glv_worst_score` 顯示為
   「異常度 1.35 σ」；原始名字在懸停與複製時逐字不變（它是分數表達式的變數，
   **不改名**）。

### 一份出處

`bound_specs()` / `column_tree()` 從 `results_table.py` 搬到中性的
`ui/feature_tree.py`，兩個面板都吃它；`studio._feature_sections()` **刪掉**。
新面板依 `CLAUDE.md` §4 開新模組 `ui/feature_panel.py`（`widgets.py` 已 6,928
行）—— 而 F50 的「先問那一塊該不該是一塊」在這裡答得出來：**該**，因為分組的
依據是引擎本來就記著的事，不是畫上去的框。

---

## 5. 動工順序

| # | 做什麼 | 動到 | 風險 |
|---|---|---|---|
| 0 | `freeze_golden.py --check` 三份綠 | — | — |
| 1 | 修 `region_index` 的序（病 ①）| 區域線 → index 那一支 | 低，要跑黃金值 |
| 2 | `FeatureSpec` 加 `unit`；`feature_gloss` 吃 `variant`；GLV 卡補 `feature_help()`（病 ②③）| core + widgets | 低，數字不動 |
| 3 | 抽 `ui/feature_tree.py`（`bound_specs`＋`column_tree` 搬家，Results 照舊吃它）| results_table.py | 低，純搬家＋既有測試守著 |
| 4 | 新 `ui/feature_panel.py`（§4 那張圖），Preview 換過去 | 新模組 + studio 接線 | 中 |
| 5 | ADC 那一塊改成「有判定才長出來」（病 ⑥）| studio 的 verdict row | 低 |

1 與 2 彼此獨立、也跟 3–5 獨立 —— **先做這兩把，畫面就已經不說謊了**。

驗收要加的測試：

* 同一個區域名在同一份 recipe 的任兩張卡底下拿到同一個 `region_index`；
* **任何特徵的說明欄不得等於它自己的 id**（配一支反向測試 —— 例外清單修好了
  沒拿掉的話那份 recipe 從此少一條防線，`CLAUDE.md` §1 的規矩）；
* 四胞胎在畫面上相鄰（病 ④ 的回歸）；
* 沒有判定時 Verdict 那一塊不佔位。

---

## 6. 那幾個字是什麼（要搬進 GLV 卡的 `feature_help()`）

開 `Boxes in the region = each box` 才有這一族。這個模式問的是
**「這幾百格裡哪一格跟別人不一樣」**。

| 名字 | 一句話 | 單位 |
|---|---|---|
| `<量>_typical` | 每格各自算完之後**取中位數** —— 這批單元長什麼樣 | 同該統計量 |
| `<量>_outlier` | **這一欄自己**最極端那格的值 —— 每一欄各自一格，跟 judge 挑的贏家常常不同格 | 同上 |
| `<量>_outlier_box` | 上一格是**第幾格**（0 起算） | box |
| `<量>_worst` | **judge 挑的那一格**的這個量 | 同上 |
| `glv_worst_score` | 贏家那格的異常度，**單位是 σ**：`\|v − 鄰居中位數\| ÷ (1.4826 × 鄰居 MAD)`，鄰居 = 除自己外所有格（leave-one-out）| σ |
| `glv_worst_value` | 贏家那格的 **judge 統計量**值（judge 預設 `glv_median`）| 同 judge |
| `glv_worst_i / x / y / w / h` | 贏家是第幾格、在整張影像的哪裡（就是那格 ROI 自己）| box / px |
| `glv_worst_score_median` / `_spread` | **逐框異常度那條分布**的中心與寬 ——「一格特別怪」vs「500 格都一樣怪」靠它分 | σ |
| `glv_boxes_over_k` / `_frac` | 超過 `over_k` 個 σ 的有幾格 / 佔幾成 | count / ratio |
| `glv_boxes` | 真的量得出來的有幾格（太小的格跳過，不是寫 0）| count |
| `score`（裸的）| **ADC 分數表達式的結果**，跟上面整族無關 | — |

---

## 7. 待使用者決定的三件事

1. **`<judge>_outlier` 要不要停止產出？** 實測 24/24 跟 `<judge>_worst` 相同，
   但**數學上不保證**，所以停產是行為改變、要一道遷移。
   ⚠ **注意這一格 2026-09-02 變便宜了**：唯一用 `_outlier` 的出貨 recipe
   （`patch-dsnr-by-class`）當天被刪掉，所以現在只剩使用者手上的 recipe。
   §4 決定 2 的顯示修法仍然不必付這筆錢 —— 先做顯示，之後再看還會不會混。
2. **要不要開 `glv_worst_baseline`？**（leave-one-out 的基準值本身）
   現在算了、留在 meta、沒變成特徵。開了之後
   「目標格 − 其他格」的分數可以寫成
   `(glv_worst_value - glv_worst_baseline) * 100`，逐字就是使用者要的那句話；
   現在只能用 `_typical`（**含自己**的中位數）近似。
3. **§4 那張圖的欄名用什麼字**（「這批典型 / #21 那格 / 自己最極端」）——
   這是製程工程師要讀的四個字，值得挑一次挑對。

---

## 8. 沒有選的路

* **在 UI 拆特徵字串把 variant 猜回來** —— F51 剛清掉這種猜法，`spec` 上有。
* **`_outlier` 改名** —— 要遷移，而顯示層已經講得清楚。名字是 recipe 的鍵。
* **在 `widgets.py` 加第四欄** —— 那份 6,928 行，`CLAUDE.md` §4 就是為這刻寫的。
* **`glv_worst_*` 收進 `diagnostic_features`** —— 它們不是診斷，是 F68 那張卡
  的主要輸出。標題行才是它們的位置。
* **替 Preview 另外寫一棵樹** —— Results 已經有一棵，兩棵一定會漂（病 ① 就是）。
