# F36 — 整批的分布（box plot）＋ 一份 patch dSNR 的 recipe

> **d4t — defect**　·　2026-08-26
> 使用者：「幫我建一份 recipe 是 for patch 專用，要用來比較這一整筆 patch 內
> 的 dSNR 分布 … 輸出預期要有 report 然後還有一張 box plot。
> 如果需要新增功能(請通知我~) 看不懂得也問我」

---

## 0. 盤點：要的東西有幾樣已經在了

| 使用者寫的 | 現況 | 對應 |
|---|---|---|
| deNoise Gaussian=3 | ✅ | `denoise`，`method=gaussian`、`ksize=3` |
| ROI templateGC | ✅ | `roi_reference` 的 `method = "a cell I mark myself"` |
| focus | ✅ | 特徵叫 **`focus_lapvar`**（不是 `focus_laplacian`）—— `algo/quality.py` 的 `DEFAULT_LAP_THRESHOLD` 就是 145，使用者的 150 在同一個尺度上 |
| SNR：T = test 內最強的 ROI，R = ref 的其他 ROI | ✅ | `glv_stats` 的 `each box` ＋ `reference = "another region on another stream"` |
| report | ✅ | `output_bundle` |
| **box plot** | ❌ **完全沒有** | 見 §2 |

## 1. 三個問回去的問題（照使用者的話：「看不懂得也問我」）

| 問的 | 為什麼要問 | 答案 |
|---|---|---|
| 「GLV contrast 超過 40」是哪一個數字 | 這個 repo 的 `contrast` 是 **Michelson**（`(T−R)/(T+R)`，範圍 −1..1）—— **40 不可能是它**。照字面實作等於做出一個永遠不成立的門檻 | **灰階差 `delta`** |
| 「dSNR」 | `compare_metrics` 同時有 `delta` 與 `snr`，而 `d` 兩邊都讀得通 | 就是 **`snr`** |
| box plot 一個盒子代表什麼 | 這決定卡片長什麼樣（要不要一格「分組欄」） | **一個 bin 一個盒子** |

⚠ **不要照著一個不可能的門檻做下去**。這一輪如果直接把 `contrast > 40` 寫進樹，
使用者會拿到一份跑得完、每一顆都判 bin 2 的 recipe —— 而畫面上沒有任何線索。
這就是這個 repo 那六個「跑得完、有數字、而且是錯的」的形狀。

---

## 2. 新功能：`output_boxplot`「Write a box plot」

### 2.1 為什麼是手寫 SVG，不是 matplotlib

相依只有 numpy / opencv / tifffile / PySide6 / openpyxl，而公司機是**用複製檔案
更新的**（`AGENTS.md`）—— 多一個套件就是多一件在受限機器上會裝不起來的事。
而 box plot 的幾何就是幾條線與幾個矩形。

前例已經在了：`ingest/klarf_core._svg_wafer` 用同一套辦法畫 die 熱力圖。
新模組 `core/export/boxplot.py` 是 Qt-free 的（鐵則 1），顏色是**參數** ——
跟 `decide_tree.verdict_rows` 同一個理由。

### 2.2 一個盒子是**一片葉子**，不是一個 bin

使用者選的是「一個 bin 一個盒子」，而實作走 `verdict_rows`，它回的是葉子。
兩者在使用者的 recipe 上是同一件事（四個 bin 四片葉子），但葉子多三個免費的
好處：**盒子上的字就是他自己寫的那一句**、順序跟畫布上的樹一樣、顏色也一樣。
而且兩片葉子共用一個 bin 是合法的 —— 那時候「一個 bin 一個盒子」會把兩個
使用者眼中不同的類別畫成一個。

### 2.3 `Numbers to plot` 留空 = **判定問過的那幾個**

不是「全部的特徵」（一批 patch 有幾十欄，畫出來沒人看），也不是一份寫死的
清單 —— 寫死的那一份總有一天跟樹漂掉，而那時候圖上畫的就不是在判的東西了。

為此在 `decide_tree` 加了 `features_used(decide)`：走樹上的每一題，收集變數，
**扣掉 `let` 自己的名字**（把 `snr_min` 這種常數畫成盒子只會得到一條平線），
但**算進 `let` 算式裡用到的**（否則一份全靠 working number 判定的 recipe 會
答「什麼都沒問」）。

住在 `decide_tree` 而不是那張卡上：它問的是 `DecideSpec` 的形狀。

### 2.4 三個「不要安靜」

* **打錯的特徵名** → 那張圖**不畫**，並在 warn 裡點名。畫一張每一格都是
  `no data` 的圖的話，使用者會以為是資料的問題（推廣鐵則）。
* **某一類沒有那個數字** → 那一格寫 `no data`，不是留白（留白讀起來是
  「這一類不存在」）。
* **一顆都沒有** → `box_stats` 回 `None` 不是 0。一個高度為零的盒子讀起來是
  「量了，而且全部都是 0」。

### 2.5 鬚停在真實資料點

Tukey 1.5×IQR，但鬚的端點是**落在柵欄之內的真實資料點**，不是
`q1 − 1.5·IQR` 那個算出來的邊界 —— 後者會畫出一段伸進沒有資料的地方的鬚。

---

## 3. `recipes/patch-dsnr-by-class.json`

```
Load images ──test,ref──> Denoise (gaussian,3) ─┬─test──> Reference regions (templateGC)
                                                 ├─test──> Focus index
                                                 ├─test──> GLV (source)
                                                 └─ref───> GLV (reference source)
Output（不接線）：Write report folder ＋ Write a box plot
```

判定：`focus_lapvar >= 150` → `cmp_snr_mean_outlier > 4` →
`cmp_delta_mean_outlier > 40`，三個門檻是 `let`（改數字不動樹）。
**問不到的題目一律答「否」**（F30），所以量不到 focus 的那一顆落在 bin 99 ——
方向是安全的那一邊，而那是排題目順序時就決定的。

### 3.1 模板塞不進 JSON（唯一沒得繞的那一格）

templateGC 要一張**模板影像**＋畫在它上面的框。卡片自己的話：「a template is
an image, it cannot be typed in」。所以這份 recipe 載進去有**兩條** error，
而它們是**同一個原因**：`not-configured @roi`（沒有模板）與
`unknown-region @glv`（沒有模板就產不出區域名）。第一條指名了那顆按鈕。

`tests/test_shipped_recipes.py` 因此有一張 `ALLOWED_ERRORS` 表 ——
**明列**這兩條，而不是「這份 recipe 跳過檢查」：長出別的 error 照樣要紅。
外加一支反向的 `test_the_allowed_errors_are_all_still_happening`：例外修好了
卻沒從表上拿掉的話，這份 recipe 從此少一條防線而測試照樣綠 —— 那是「例外表」
唯一會爛的方式。

### 3.2 ⚠ 帶正負號的 delta 是一條「只抓亮缺陷」的規則

`_outlier` 挑的是「離典型最遠」的那一格 —— **兩個方向都算** —— 而 `delta`
帶正負號。所以暗缺陷的 `cmp_delta_mean_outlier` 是負的（合成資料上實測
**−18.6**），`> 40` 對它永遠不成立。

**照使用者指定的走**（他選的是 delta），但：

* `compare_metrics` 一起量 **`abs_delta`** —— 逃生口一直在，樹上換一個名字
  就是兩種都抓，**不必重跑影像段**；
* 這件事寫進 `recipes/README.md` 與一支叫得出名字的測試
  （`test_the_signed_delta_is_a_bright_defect_rule_and_abs_is_measured_too`）。

### 3.3 不會爛掉

模板塞不進出貨的 recipe，但**測試造得出來**：合成 lot 的圖案就是一個週期性
晶格，切一格 `encode_cell` 就是模板。所以「這份 recipe 到底跑不跑得出那三個
數字」沒有藉口不驗 —— `test_the_patch_recipe_measures_and_classifies_end_to_end`
補上模板之後**要求零 error**，跑完 12 顆、49 個框，三個特徵都在，兩個輸出檔
都寫得出來。

外加一支不必跑資料的：`test_the_patch_recipe_asks_about_numbers_its_own_cards_measure`
—— 樹問的每一個名字，都要有一張卡在**宣告層**寫得出來。它抓的正是
`focus_laplacian` vs `focus_lapvar` 這種打錯，而那種錯跑起來的症狀是
「每一顆都判成同一類」。

---

## 4. 驗收

- 全新：`d4t/core/export/boxplot.py`、`OutputBoxPlotStep`、
  `decide_tree.features_used`、`tests/test_output_boxplot.py`（16）、
  `recipes/patch-dsnr-by-class.json`。
- `tests/test_shipped_recipes.py` 12 → 21。
- 核心全套 + UI 逐檔 + `freeze_golden --check` 三份全綠（沒碰演算法）。
