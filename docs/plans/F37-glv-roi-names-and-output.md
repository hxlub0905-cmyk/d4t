# F37 — GLV↔ROI 的名字與接線、Output 的收斂

**狀態：討論中（一行 code 都還沒動）。** 使用者 2026-08-26 提出兩塊：

> 第一是 GLV 跟 ROI card 的連動問題……GLV card 目前有很多種接 ROI 方式，
> 量測的 GLV 跟相關的數值也很多，會讓人混淆，尤其是在看 feature 內的數值。
> 第二是 output 相關。

追問之後定調的範圍（四＋二項）：

| # | 題目 | 使用者原話 |
|---|---|---|
| A1 | 名字太多、看不懂是誰的 | ✔ |
| A2 | 前綴是條件式的太危險 | ✔ |
| A3 | 接 ROI 的方式太多種 | ✔ |
| A4 | 值用上下標＋顏色 | 「值可否用上下標　更清楚　配合顏色」 |
| B1 | Output 卡片數收斂 | ✔ |
| B2 | Output 產物內容收斂 | ✔ |

**這份是議程，不是待辦清單**（同 F11 的規矩）—— 每一項要先討論過才動手。

---

## 0. 先量出來的四件事（不是推測，是跑出來的）

動手之前先確認「混淆」具體長什麼樣。四項都在這一輪實測過。

### 0.1 `<region>_boxes` 由兩張卡各寫一次，而且意思不同

一張 GLV 接兩個區域（`roi="epi,mg"`、`across_boxes="each box"`）宣告出來的是：

```
epi_glv_median_typical   epi_glv_median_outlier   epi_glv_median_outlier_box
epi_boxes                epi_worst_i … epi_worst_value
epi_score_median         epi_score_spread         epi_glv_pixels
（mg_ 同上一份）
```

而上游 Region 卡對同一個區域寫的是 `_util.REGION_FACTS`：

```
epi_present   epi_boxes   epi_area_px   epi_clipped   epi_edge_dropped
```

**`epi_boxes` 兩邊都有，而它們是兩個數字**：Region 卡說的是「這個區域有幾個
框」，GLV 說的是「其中幾個框真的量得出來」（像素太少的會被跳過）。

好消息是它**不是安靜的**：`recipe.validate` 的 `feature-collision` 會報 warning，
engine 也會把先寫的那一份救成 `<節點名>_epi_boxes`。壞消息是這個撞名**由構造
決定**——只要接兩個區域就一定發生，使用者再小心也躲不掉，而「每一份正常
recipe 上都會出現的警告會被學會忽略」正是 `_feature_collisions` 自己寫下的話
（F11 Enhance-3 為 `clip_frac` 開的那個例外，就是同一個形狀）。

### 0.2 `worst_*` / `score_*` 是唯一沒有家族標記的一族

`glv_` 是這一塊自己的灰階、`cmp_` 是比出來的（F18 立的規矩），而 F31 加進來的
`worst_i/x/y/w/h/score/value`、`score_median`、`score_spread`、`boxes` **一個
tag 都沒有**。它們跟 CD 的 `cd_*`、Region 的 `<n>_present` 排在同一份 CSV 上，
而 `score_median` 這個裸名在有分數表達式的 recipe 上特別容易被讀成「分數的
中位數」——它其實是「逐框異常度的中位數」。

### 0.3 條件式前綴：接第二條線 = 安靜地把每一個名字改掉

`MultiSourceStep.stream_prefix` / `region_prefix` 只在「超過一個」時才加前綴。
所以在既有的一張 GLV 卡上**多接一條區域線**，它寫出的每一個名字都會改：

```
glv_median          →   epi_glv_median   +   mg_glv_median
cmp_delta_mean      →   epi_cmp_delta_mean + mg_cmp_delta_mean
```

而分數表達式、判定樹的規則、Output 卡的 `rank_by` / `columns` / `features`
裡指著 `glv_median` 的那幾個字**不會跟著改**。畫布上使用者只做了一個動作
（拉一條線），下游三個地方同時失效。

當初的理由寫在 `MultiSourceStep.stream_prefix` 的 docstring 上（「只接一條時
名字跟以前逐字相同，所以既有的分數表達式不用改寫、黃金值一個數字都不動」）——
那是 2026-08-17 一次**遷移**的論證，不是一個設計論證，而它變成永久的了。

### 0.4 唯一沒有線的那個區域參照，正好是 lint 檢查不到的那一個

`reference = "the other regions"` 靠命名慣例推導 `<name>_others`，
**刻意不宣告**（`resolve_regions_in` 的註解：「畫布上那條線已經在了」）。
後果實測：

```python
roi="epi_center", reference="the other regions"
→ configuration_issues() == []        # 跑之前一句話都沒有
→ 執行時每一顆 defect 各失敗一次：the region to compare against
  ('epi_center_others') is not on this defect
```

錯誤訊息本身是好的，但它出現在**跑完一批之後**。而 `recipe.validate` 有
`unknown-region` 這條 lint —— 它檢查不到這一個，正因為這個區域沒有被宣告。
**F12 那條規矩（用到的每一個區域都要有一條線）在這裡反過來證明了自己。**

---

## 1. A1 — 一個家族一個開頭 tag

### 提案

| 現在 | 改成 | 為什麼 |
|---|---|---|
| `boxes` | `glv_boxes` | 解掉 §0.1 的構造性撞名 |
| `worst_i/x/y/w/h/score/value` | `glv_worst_*` | CSV 上看得出是誰算的（§0.2）|
| `score_median` / `score_spread` | `glv_worst_score_median` / `glv_worst_score_spread` | 它們是 **worst 那個分數**的分布，不是另一種 score |
| `glv_pixels` / `glv_ok` | **不動** | 已經有 tag |
| `_typical` / `_outlier` / `_outlier_box` | **不動** | 位置是對的（最後一級：這是逐框分布的哪一端）|
| `cmp_*` | **不動** | F18 立的規矩，還成立 |

規則因此一句話講得完，而且**每一個名字都答得出前三個問題**：

```
[流][區域][自己取的名]  glv_ / cmp_  <統計量>  [_typical|_outlier|_outlier_box]
                        └ 這一塊自己的 / 跟參照比的
```

### 代價（量過的，很小）

改名要**連同它的引用一起搬**，而引用有四種，不是一種：

| 引用在哪 | 現在有幾處 | 誰負責搬 |
|---|---|---|
| 分數表達式 | fixture recipe 3 份 | `Step.legacy_feature_renames`（**已經存在**，F18 為 `cmp_` 建的）|
| 判定樹的 rule / let | `recipes/patch-dsnr-by-class.json` | ⚠ **現有遷移沒有覆蓋，要補** |
| Output 卡的 `rank_by` / `columns` / `features` | `output.py` 的 help 例子、`recipes/README.md` | ⚠ **同上，要補** |
| 黃金值 | 3 份（`tests/fixtures/golden/`）| 重凍 |

> ⚠ **中間那兩列是這一項真正的工作量。** `legacy_feature_renames` 今天只改寫
> 分數表達式；判定樹與 Output 卡的參數值裡也住著特徵名，而它們是 F24／F30
> 之後才長出來的。只搬一半 = 換了名字而判定樹指著一個不存在的變數，
> **跑得完、每一顆掉進同一個 bin、畫面上沒有線索**（F36 §① 那個形狀）。

---

## 2. A2 — 前綴是條件式的

三條路，代價差很多。**這一項需要使用者定調。**

| | (i) 一律帶前綴 | (ii) 維持條件式，但把改名講出來 | (iii) 前綴由使用者明講 |
|---|---|---|---|
| 名字 | `test_epi_glv_median` 永遠這樣 | 不變 | 使用者填什麼就是什麼 |
| 接第二條線 | 名字不變（本來就有前綴）| 名字改，**但 UI 當場說「這會改掉 12 個名字，其中 3 個你的判定樹在用，要幫你改嗎」** | 名字不變 |
| 既有 recipe | **全部要遷移**（recipe 有 `app_version`，遷移接得住）| 零 | 要遷移 |
| 黃金值 | 3 份全部重凍 | **零** | 3 份重凍 |
| 短名的好處 | 沒了（`glv_median` 這種好讀的名字消失）| 留著 | 留著 |

**我的建議：先做 (ii)。** 危險的不是條件式本身，是**改名是安靜的、而下游的
引用不會跟著改**——(ii) 正好只修那一件事，成本零遷移零重凍。做完之後如果
你仍然覺得「名字的意思會隨接線而變」本身就不能接受，(i) 再做，而那時候
(ii) 建的那套「找出所有引用並改寫」的機器正好就是 (i) 需要的。

反過來的論證也要說清楚：(i) 的好處是**一份 CSV 的欄名永遠自我解釋**，
而那是你這一輪抱怨的起點（「尤其是在看 feature 內的數值」）。如果你要的是
那個，就直接走 (i)，(ii) 會變成半途。

---

## 3. A3 — 五種接 ROI 的方式

今天一張 GLV 卡上，「量哪裡」有五個互不相同的機制：

| # | 機制 | 畫布上長什麼樣 | 問題 |
|---|---|---|---|
| 1 | `roi`（`region_keys`，清單埠）| 一條虛線，可以接很多條 | — |
| 2 | `reference_region`（`region_key`，角色埠）| 第二條虛線 | — |
| 3 | `reference = "the other regions"` | **什麼都沒有** | §0.4：lint 檢查不到 |
| 4 | `across_boxes = "each box"` | 什麼都沒有（是設定，不是線）| 合理，但它讓 #1 的一個區域變成 N 個母體 |
| 5 | Region 卡吐三個名字（`<n>` / `<n>_center` / `<n>_others`）| 三個埠，使用者挑一個接 | 挑錯了 #3 就壞（§0.4）|

### 提案

**只動 #3。** 把 `the other regions` 從「靠命名慣例推導」改成**一個真的埠**：

- `reference_region` 那一格在 `reference = "the other regions"` 時**自動填**
  `<roi>_others` 並顯示出來（唯讀，跟其他 `region_key` 一樣），畫布上因此
  **長出一條線**。
- 於是 `resolve_regions_in` 宣告得出它 → `unknown-region` 這條 lint 立刻
  涵蓋 §0.4 那個 case，錯誤從「跑完一批之後每顆各報一次」變成「還沒跑就講」。
- 使用者的操作**一步都沒有增加**（他還是只選那個下拉）。

#4 與 #5 建議**不動**：#4 答的是不同的問題（一個母體 vs N 個母體），#5 是
Region 段的既有契約（F11 Region-1，三張卡共用）。動它們的代價遠大於收益。

---

## 4. A4 — 值用上下標＋顏色

### 現況

`ui/widgets.feature_gloss()` 已經把名字翻成 (絕對量/相對量, 一句話)，
`FeatureTable` 已經用顏色分那兩類。缺的是**結構**：`epi_cmp_delta_median`
在畫面上仍然是一整串字。

### 提案

加一支 `parse_feature_name()`，把名字拆成有名字的幾層，UI 用 rich text 畫：

```
epi_cmp_delta_median   →   Δmedian ᵉᵖⁱ  vs mg
                           ───────  ───     ──
                           統計量   區域    參照（來自 meta["compares"]）

test_epi_glv_median_outlier  →  median ᵉᵖⁱ 𝚝𝚎𝚜𝚝  · 最不一樣的那一格
```

- **區域名畫成上標，顏色用 `theme.region_hex(index)`** —— 那正好是
  ROI 框在影像上的顏色、也是畫布上區域埠的顏色。**三個地方同一個顏色，
  而顏色的來源只有一份**（`theme.REGION_COLORS` 已經在了，這一項是免費的
  一致性）。
- **流名畫成下標**，用該流在畫布上的顏色。
- 原始名字**不消失**：滑鼠停留顯示完整字串，因為那才是打進分數表達式的字。

### ⚠ 這一項有順序相依

`parse_feature_name` 只有在**名字本身是結構化的**時候才寫得出來。今天
`epi_boxes` 這個名字，你無法從字串判斷 `epi` 是區域還是某個 metric 的一部分
——那正是 §0.1 撞名的另一面。

**所以 A4 排在 A1 之後**，而 A1 不做的話 A4 只能做半套（`glv_` / `cmp_`
那一層拆得出來，前綴那一層拆不出來）。

---

## 5. B1 — Output 卡片數收斂

### 現況：八張卡，四種產物，重疊得很厲害

| 產物 | csv | report | klarf | image | bundle | char | boxplot | html |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| CSV 明細 | ✔ | ✔(sheet) | | | ✔ | ✔ | | |
| HTML 表 | | | | | ✔ | ✔ | | ✔ |
| 每顆一張圖 | | | | ✔ | ✔ | ✔(兩張) | | |
| `recipe.json` | | | | | ✔ | ✔ | | |
| box plot | | | | | | | ✔ | |
| KLARF 寫回 | | | ✔ | | | | | |

**CSV 有四張卡寫得出來、HTML 三張、圖三張。** 而重複的參數各有各的預設：

| 參數 | 在哪幾張 | 預設 |
|---|---|---|
| `rank_by` | image / bundle / char | 三張一致（共用 `rank_by_spec()`）|
| `limit` | image / bundle / char | **200 / 0 / 200** ← 不一致 |
| `jpeg_quality` | bundle / char | 一致 |
| `montage` | image / bundle | 一致 |
| `roi_draw_specs()` | image / bundle | ⚠ **char 沒有**，但 char 也畫圖 |
| 路徑那一格 | 全部 | `path` vs `folder` 兩個名字 |

### 提案：八 → 四，切法是「產物的形狀」不是「檔案格式」

| 卡 | 是什麼 | 取代 |
|---|---|---|
| **Write results** | 一份結果表。勾要哪幾種格式：CSV／Excel／HTML（單檔可寄）| `output_csv` + `output_report` + `output_html` |
| **Write report folder** | 一個資料夾：報表＋圖＋CSV＋recipe。`layout` 二選一：一顆一列（整批）／點對點兩張圖（characterization）| `output_bundle` + `output_char` + `output_image` |
| **Write a box plot** | 不動 | — |
| **Write KLARF** | 不動 | — |

### ⚠ 第二列推翻了一個寫在 code 裡的既有結論，要一起重新決定

`steps/output.py` 的 `OutputCharStep` docstring 明寫**為什麼不做成 bundle 的
一格參數**：

> 用一格參數在同一張卡上切換兩種版面的話，「這張卡長什麼樣」就有兩個答案，
> 而說明書、help、測試都得同時描述兩種 —— 那正是這個 repo 一再避開的形狀。

那個論證**現在仍然成立**。變的是它周圍的事實：當時是兩張卡，現在是**三張**
寫資料夾的卡，共用同樣四個檔名（`report.html` / `defects.csv` / `recipe.json`
/ `images/`）與九成相同的參數。所以這一列不是「我覺得可以合」，是
**「當初的取捨在三張卡的規模下要重算一次」**，而算的人是你。

兩個選項：
- **(a) 合**（上表）：卡片庫少三列，代價是那張卡的 help 要講兩種版面。
- **(b) 不合，只合 `output_image` 進 `output_bundle`**（它幾乎就是「bundle
  但不寫報表」）：八 → 六，char 保持獨立，既有結論完全不動。

---

## 6. B2 — 產物內容收斂

不管 B1 選哪一種，這幾項都該做（**它們不改卡片數，只改「同一批資料不會有
四種讀法」**）：

1. **一份 CSV 的規則**：四張卡都走 `export_report.write_csv`（已經是了），
   但 `output_csv` 有 `include_features` 開關而資料夾那兩張沒有 → 統一。
2. **一份 HTML 版面**：`export_html.build_report` 與 `build_char_report` 是
   兩支，共用 CSS 與跳脫。收成一支 + 版面參數（這是 B1(a) 的前置，也是
   B1(b) 下仍然值得做的）。
3. **`limit` 的意思統一**：現在 `0` 在 bundle 是「全部」、在 image 是**不合法**
   （`min=1`）。同一個數字兩種意思。
4. **`roi_draw_specs()` 補進 char**：它畫圖但畫不出 ROI 框，而 GLV 逐框比較
   的贏家框正是報表上最該看到的東西。
5. **路徑那一格統一叫法**：`path`（單一檔案）／`folder`（資料夾）已經是規則，
   但 `_OutputStep.PATH` 的 `configuration_issues` 只對 `PATH == "path"` 檢查
   「指到資料夾」→ 寫資料夾的卡沒有對應的「指到檔案」檢查（`output_image`
   自己寫了一份、`bundle`／`char` 各自又寫了一份 = 三份會漂）。

---

## 7. 建議的順序

```
A1（名字加 tag）
 └→ A4（上下標＋顏色，需要結構化的名字）
A2(ii)（接線改名要講出來）        ← 與 A1 獨立，可並行
A3（the other regions 長出一條線）  ← 最小，可以先做暖身
B2（產物內容收斂）
 └→ B1（卡片數收斂）             ← 需要先決定 (a) 還是 (b)
```

---

## 8. 需要使用者定調的四件事

1. **A2 走哪一條？** (i) 一律帶前綴（要遷移＋重凍黃金值）／(ii) 維持條件式但
   把改名講出來（零成本）／(iii) 前綴由使用者明講。
2. **B1 走 (a) 還是 (b)？** 也就是 `output_char` 要不要併進 `output_bundle`
   ——那會推翻一個寫在 code 裡、而且論證仍然成立的既有結論。
3. **A1 的改名要不要一次做完？** 包含把遷移補到判定樹與 Output 卡的參數值
   （§1 那張表的中間兩列），那是這一項真正的工作量。
4. **A4 的上標／下標怎麼配？** 提案是「區域＝上標、流＝下標」，兩者都用畫布
   上既有的顏色。反過來也成立，只是要挑一個並且從此不變。
