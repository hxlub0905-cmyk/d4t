# F7 — 畫布、卡片分類重整、patch-only 收斂

> 把 UI 從「直線鏈 + 兩種輸入」收斂成 **「單一輸入型別（EBI patch）+ n8n 式自由畫布」**，
> 並把卡片分類從「影像／算法」（描述卡片**吐什麼**）改成依**流程階段**分類
> （描述卡片**在解決什麼問題**）。
>
> 版本：v1.0 · 2026-07-28 · **F7-1 ~ F7-6 全數完成**（643 tests 綠）

---

## 1. 為什麼要做

M6 之後 v1 功能完整，但實際打開 Studio 的第一印象是「東西太多、不知道從哪開始」。
逐條拆解使用者的回饋：

| 回饋 | 根因 |
|---|---|
| 「字卡功能太瑣碎」 | 17 列平鋪，沒有階層、沒有搜尋 |
| 「影像／算法分得太武斷」 | 那是依**輸出型別**分（吐圖 vs 吐數字），不是依**使用者的意圖**分 |
| 「一次做 SEM image 跟 patch 太複雜」 | 雙 route 讓每個概念都要講兩次 |
| 「UI 太像玩具」 | 暖奶油底 + 琥珀 accent + 填滿的彩色區塊（配色 vendoring 自 CPE） |
| 「影像太小」 | 右欄 620px 寬且與特徵表 3:2 分高；底部直方圖再吃掉 190px |
| 「直方圖不該在這」 | 它是**跑完一批才有意義**的東西，卻常駐在編輯流程的畫面上 |

共同的根因只有一個：**v1 的 UI 是按「引擎的結構」長出來的，不是按「使用者的工作流程」長出來的。**

---

## 2. 已定案的決策

| # | 決策 | 理由 |
|---|---|---|
| D1 | **RSEM 輸入先關掉，但不刪 code** | 使用者說的是「暫時」。刪掉等於丟掉整個 M4 + M0 vendoring 的 `algo/golden.py`、`algo/period.py`。關掉的成本是零，回復的成本是一個開關 |
| D2 | **卡片改依流程階段分類**（見 §3） | 分類要回答「我想幹嘛」，不是「這張卡吐什麼型別」 |
| D3 | **`blob_segment` 從量測段移到 Region 段** | 它做的事是「產生 ROI」，不是量測。搬過去之後手畫的框與偵測出來的框走同一條路 |
| D4 | **`snr_map` 留在 Enhance** | 依型別規則（影像進、影像出）。破例會讓「看型別就知道放哪」這條規則失效 |
| D5 | **Align 降級：卡片保留，但不進預設範本** | 機台輸出的 patch 兩兩對應本來就是 defect & reference，不需要對位（使用者的領域知識，見 §5） |
| D6 | **Output 是固定尾節點，但底下仍是 Export 精靈** | 畫布視覺完整（Input → … → ADC → Output），但 Export 是 per-batch、ADC 是 per-defect，不該真的變成流程節點。引擎不動 |
| D7 | **Region 段先只做「defect 座標系」的 ROI** | pattern 座標系的 ROI 有真實難題，見 §4 |

---

## 3. 新的卡片分類

每一段附一條**機械可判定的規則**（吃什麼、吐什麼），這樣「新卡片放哪一段」不需要討論。

| 段 | 規則 | 現有卡 | 待補 |
|---|---|---|---|
| **Input** | *(固定頭節點)* | `load_patch` | — |
| **Enhance** | 影像 → 影像 | `percentile_norm` `glv_mask_norm` `hist_match` `denoise` `invert` `snr_map` | Brightness/Contrast、Gamma、CLAHE |
| **Region** | 影像 → 區域 | `blob_segment`（搬過來） | Whole image、Centre box、Annulus |
| **Compare** | 影像＋影像 → 影像 | `subtract`、`align`（不進預設） | ratio / log-ratio |
| **Measure** | 影像＋區域 → 數字 | `glv_stats` `roi_snr` `cd_measure` `focus_quality` | Custom metric |
| **ADC** | 數字 → score → bin | Score / Bin *(固定)* | — |
| **Output** | 整批 → 檔案 | Export *(固定尾節點)* | — |

### 命名（左側 rail 用 icon + 短標題）

| 段 | 採用 | 也考慮過 | 為什麼選這個 |
|---|---|---|---|
| 1 | **Input** | Source, Load | 固定節點，n8n 的 trigger 位置 |
| 2 | **Enhance** | Preprocess, Adjust, Image Ops | 使用者自己的用詞 |
| 3 | **Region** | ROI, Where | 標題用 Region，副標寫 ROI（業界通用語但仍是縮寫） |
| 4 | **Compare** | Difference, Combine | 涵蓋未來的 ratio；Difference 綁死在減法 |
| 5 | **Measure** | Metrics, Quantify | 最短、最白話 |
| 6 | **ADC** | Score, Decide | **使用者最熟悉的字**，比任何翻譯都好懂 |
| 7 | **Output** | Export, Write | 固定節點 |

讀起來是一句話：**Input → Enhance → Region → Compare → Measure → ADC → Output**。

### 因為畫布，分類不再需要編碼順序

Region 段排在 Compare 前面，但 `blob_segment` 必須跑在 `subtract` 之後（它吃 diff）。
在直線 UI 裡這是矛盾；在自由畫布上不是 —— **順序由使用者拉的線決定，
左側清單只回答「這張卡在做什麼」**。靜態 ROI 接前面、偵測型 ROI 接後面，
兩者仍同屬 Region 群組。

### icon 的實作限制

repo 有「只有純文字檔」的不變量（公司機 DLP 擋二進位，見 HANDOVER §5）。
`.png` 不行；`.svg` 是純文字可以。**但建議用 `QPainter` 直接畫**：
七段各十幾行幾何，顏色吃 `theme.py` 的 token，換主題時 icon 自動跟著變，
而且完全不用新增檔案。

---

## 4. Region 段的真實難題（**這一段先不照搬**）

### 問題

機台的裁切邏輯是：**以 defect 座標為正中心，裁 x×x 像素**。這帶來兩個座標系：

| 座標系 | 原點 | ROI 在這裡穩不穩定 |
|---|---|---|
| **defect frame** | patch 正中心 | **穩定** —— 缺陷永遠在中心，這是裁切方式保證的 |
| **pattern frame** | 版圖晶格 | **不穩定** —— 裁切中心是 defect 而不是晶格，所以晶格相位逐顆不同 |

也就是說「中心 32×32 框」這種 defect frame 的 ROI 一直都是對的（現有
`glv_stats(region=center)` 之所以有效就是因為這個）；但「量線寬內部」「量 space」
這類 pattern frame 的 ROI，**每顆 patch 都要先認出晶格在哪**。

使用者的原話：*「我要在有限的 patch pattern 中認出位置」* —— 這就是那個難題。
再加上 patch 很小、defect 靠近版圖邊界時 patch 內容會不一樣（*「邊界不一樣」*），
pattern frame 的 ROI 可能整個落在框外。

### v1 只做穩定的那些

| ROI 種類 | 座標系 | v1 | 備註 |
|---|---|---|---|
| Whole image | — | ✅ | |
| Centre box | defect | ✅ | 大小同時支援 px 與 **% of patch**（見下） |
| Annulus / ring | defect | ✅ | 中心框外一圈，當背景統計用 |
| Detected blobs | 影像 | ✅ | `blob_segment` 搬過來 |
| Line / space / cell-aligned | **pattern** | ❌ 延後 | 需要相位偵測，見下 |

**「% of patch」順手修掉一個已知的坑**：CLAUDE.md §7 記載「同一組 `glv_stats`
中心框參數在 128² 上準、在 256² 上漏抓」。ROI 尺寸支援百分比之後，
同一份 recipe 換 patch 尺寸不會失效。

### pattern frame ROI 要用的工具已經在 repo 裡

`adept/core/algo/period.py`：

- `estimate_period(img)` → X/Y 週期 **＋ `confidence_x` / `confidence_y`**
- `choose_origin(shape, px, py, image=)` → 晶格相位（M4 補完的相位搜尋，
  原 CPE 專案裡是永遠回 `(0,0)` 的 stub）

這正是「在 patch 裡認出晶格位置」需要的東西。

> ⚠ **這是 D1「關掉但不刪」最重要的理由。**
> `algo/period.py` 目前只被 RSEM 的 Golden Cell 用到，看起來像是可以跟著 RSEM
> 一起砍掉的東西 —— 但它是之後做 pattern frame ROI 的唯一工具。**不要刪。**

設計方向（之後做）：相位信心低於門檻時，**退回 defect frame ROI 並標記該顆**，
而不是安靜地量錯位置。`estimate_period` 已經回報信心值，`cell_conf_x` /
`cell_conf_y` 也早就是 feature，所以這條路是通的。

---

## 5. Align：卡片留著，但要用真實資料裁決

使用者的領域知識：**機台輸出時兩兩對應的 patch 就是 defect & reference，不需要對位。**

處理方式：卡片保留在 Compare 段，但**不進預設範本**。

要把「不需要」從判斷變成事實，有一個現成的量法：

1. 拿一份真實 lot，跑一次**有** align 的 recipe，加 `--csv features.csv`
2. 看 `align_dx` / `align_dy` 兩欄的分佈 —— 它們是 **feature**（`align.py:49`），
   不只是 meta，所以直接就在 CSV 裡，開 Excel 拉個直方圖就看得到
3. 分佈集中在 0 → 永久拿掉；不集中 → 留著並依實際範圍設 `search_radius`

順帶一提 `align_score` 也是 feature，可以同時看對位品質，
判斷「位移是 0」和「根本沒對上」的差別。

### 一個要一起決定的副作用

`tools/make_sample.py` 預設 `--shift-max 3`，**刻意在 ref 上加隨機平移**來模擬對位誤差。
現有 94–95% 的分類正確率是在「有位移 + 有 align」的條件下量到的。

若真實 patch 本來就對齊，合成資料應該把預設改成 `--shift-max 0` 才符合現實 ——
但那會改變 demo 的數字。**這是一個待決策點，不要順手改。**

---

## 6. 卡片遷移清單（破壞性 schema 變更）

Region 段成立之後，量測卡要從「自己帶一組幾何參數」改成「引用一個具名 ROI」：

| 卡片 | 現在 | 改成 |
|---|---|---|
| `glv_stats` | `region=full\|center` + `box_size` | `roi=<ROI 名稱>` |
| `roi_snr` | `mode=blob\|center` + `box_size` | `roi=<ROI 名稱>` |
| `cd_measure` | 讀 `meta["blobs"]` | 讀具名 ROI |
| `blob_segment` | 寫 `meta["blobs"]`、category=algo | 寫 `ctx.rois`、category 改 Region 段 |

`Context.rois` / `Context.labels` 欄位**早就存在但從來沒有人寫過**
（`context.py:33-34`，註解寫著「M3 起由 ROI 卡填入」—— 那張卡沒做出來）。
`adept/core/algo/roi.py` 的 `NamedROI` / `MultiROISet`（vendoring 自 Fusi³）也是現成的。
這次是把它們接上。

**連帶要改**：5 份範例 recipe、`test_example_recipes.py`、端到端測試。
建議與 patch-only 收斂做在同一批，一次痛完。

---

## 7. Measure 段：metric bank，不要一個 metric 一張卡

使用者預期「這邊要花滿多時間 setup 量測工具」。若每個 metric 一張卡，
會做出 30 張卡然後回到「太瑣碎」的原點。

`adept/core/algo/glv.py` 已經有現成的 metric bank（vendoring 自 PEAR）：

```
GLV_STATS                     metric id → 顯示名
glv_value(patch, mid)         算單一 metric
roi_metric(image, roi, mid)   在 ROI 內算
metric_label / metric_formula 給 UI 顯示名稱與公式
```

所以 Measure 段應該是**少數幾張卡，各自被「ROI + 勾選 metric」參數化**：

- **GLV metrics** — 選 ROI + 勾 mean / std / median / max / q90 / …
- **Signal metrics** — dSNR、對比、邊緣銳利度
- **Geometry metrics** — CD、面積、長寬比、離中心距離
- **Custom metric** — 使用者自己的算式，變數是同一個 ROI 的像素統計

**加一個新量測 = 在 metric bank 加一個 id，UI 零修改。**

---

## 8. 畫布（最大的一塊）

好消息：**core 本來就是 DAG**，這是 F0 就決定的（「UI v1 只呈現直線，
之後上自由畫布時引擎零改動」）。現成的：

- `Recipe` JSON 已有 `edges` 欄位（目前都是空陣列）
- `execution_order()` 已是 Kahn 拓撲排序 + 循環偵測
- `validate()` 已會報「這條 route 有循環」

要做的純粹是 UI：

1. `QGraphicsScene` 節點畫布：節點卡、輸入/輸出 port、貝茲連線、拖曳連接、平移縮放、框選、刪除
2. 左側點一下 → 節點出現在畫布空位
3. `RecipeModel` 從線性 `node_order` 改成 `nodes` + `edges`，順序交給 `execution_order()`
4. 固定頭尾節點（Input / Output），使用者不能刪

規模估計：**800–1200 行新 UI + `RecipeModel` 改寫**。風險不在引擎（不動），
在 UI 的互動細節。

**patch-only 讓這件事簡單很多**：`routes` 只剩一條 = 畫布上只有一張圖要編輯。
雙 route 的話得處理「同一組節點、兩種執行順序」，是完全不同等級的複雜度。

---

## 9. 版面與視覺

### 版面

```
┌ 左 rail（icon+標題，可收合）┬─ 中央 Workspace ─────────┬─ 右 Inspector ─┐
│ Input                      │ 畫布（節點流程）           │ 參數表單        │
│ Enhance                    │ ─────────────────────────  │ 特徵表（可收合）│
│ Region                     │ 影像（置中、佔滿剩餘空間）  │ ~300px         │
│ Compare / Measure / ADC    │                           │                │
└────────────────────────────┴───────────────────────────┴────────────────┘

直方圖 + Gallery → 搬進「Results」視窗（按 Run 之後才開）
```

**直方圖與 Gallery 都是「跑完一批才有意義」的東西**，跟「編流程 + 看單顆」
是兩種模式。分開之後主視窗才乾淨。

⚠ 搬家時**不能弄丟秒回**：拖門檻線目前走 `viewmodel.rebin()` 純計算路徑
（不重跑影像），Results 視窗必須沿用同一條。

### 視覺

現在的配色 vendoring 自 cell-period-estimator：底 `#f7f4ef`、accent 琥珀 `#f29f4b`、
三段式用**填滿的彩色底塊**。暖色 + 高飽和 + 大色塊 = 玩具感。

目標是 n8n / KLIP 的語言：**中性灰階、全平面（無陰影漸層）、顏色只表達語意、
小圓角、一致的 4/8px 間距**。

`theme.py` 當初就把所有顏色集中成 `TOKENS`（同時餵 QSS 與自繪 widget），
所以這是**換一組 token + QSS 掃一遍**，不是重寫。段落色降級成 3px 左側色條或小圓點。

> 參考點就在手邊：使用者自己的 **KLIP** 已經是這個視覺語言（平面、中性、
> 藍色 accent、頂部 tab、密而不擠）。ADEPT 應該向 KLIP 靠齊，而不是繼續繼承 CPE 的暖色。

---

## 10. 執行順序

| 階段 | 內容 | 風險 | 為什麼是這個順序 |
|---|---|---|---|
| **F7-1** | ✅ patch-only 收斂 —— `adept/ui/scope.py` 一個檔就是整個開關 | 低 | 先把世界變簡單 |
| **F7-2** | ✅ 中性色 + 平面化 + 暗色主題（token swap，呼叫端零改動） | 低 | 早做，判斷版面才不會被暖色帶偏 |
| **F7-3** | ✅ `Step.group` + icon 分組 + 搜尋 + 前置條件 badge | 中 | 引擎不動 |
| **F7-4** | ✅ Region 段（具名 ROI）+ 四張量測卡遷移 + 5 份範例 recipe | 中高 | 分數分佈與重構前逐項相同 |
| **F7-5** | ✅ Results 視窗（直方圖 + Gallery 搬家），預覽拿最寬一欄 | 中 | 秒回路徑有測試鎖 |
| **F7-6** | ✅ 節點畫布 —— 純 UI，core 一行沒動 | 高 | 印證了 F0 「引擎零改動」的設計 |

### 完成後的實測

- 643 tests 綠（F7 之前是 595）
- `die_to_die_basic` 跑 100 顆合成 patch：分數分佈與 F7 之前**逐項相同**
  （min 21 / median 45 / max 171、bin 0=52 · bin 1=48），對照 ground truth 98%
- 卡片庫 17 列 → 15 列，分成 6 段（Input / Enhance / Region / Compare / Measure / ADC）

---

## 11. 待決策 / 待驗證

| # | 項目 | 誰決定 |
|---|---|---|
| Q1 | `make_sample.py` 的 `--shift-max` 預設要不要改成 0（見 §5） | 等真實 patch 的對位分佈 |
| Q2 | pattern frame ROI 的相位信心門檻怎麼訂 | 等真實資料 |
| Q3 | Enhance 段要不要再細分（photometric vs 其他） | 等卡片數量長到會痛再說 |
| Q4 | 畫布要不要支援分支（一個節點餵多個下游） | 引擎支援，UI v1 要不要開放待定 |
| Q5 | RSEM 什麼時候（或是否）回來 | 使用者 |

`fab_probe/` 的三個原始假設（page→channel 對應、`nm_per_px` 來源、KLARF 變體）
**仍然全部未驗證**，與本計畫獨立，優先度不因為這次重構而降低。
