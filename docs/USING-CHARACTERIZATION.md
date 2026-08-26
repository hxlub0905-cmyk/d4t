# 怎麼做 EBI ↔ API characterization

> **d4t — defect**　·　`Pair with another source` ＋ `H2H` ＋ 判定樹 ＋
> `Write characterization report`
> 這一份是**給使用者的操作手冊**：每一格填什麼、線接在哪、報表怎麼讀。
> 設計上的來龍去脈在
> [`docs/plans/F33-ebi-characterization.md`](plans/F33-ebi-characterization.md)，
> 那一份不必讀。

---

## 0. 這在回答什麼

拿 **RSEM 的 API 空拍當答案卷**，回頭去對 EBI 掃過的結果。每一顆分三類：

| | 意思 | 代表什麼 | 調哪裡 |
|---|---|---|---|
| ① | 配到、排名夠前面、有被 sample 去 review | EBI 做對的部分 | — |
| ② | **配到、但排名太低沒被 sample**（藏在 raw data 內）| 偵測能力夠，是 **sample 門檻**設錯 | 調得動 |
| ③ | 沒配到 —— EBI 的 raw KLARF 裡連這筆都沒有 | **偵測條件**有問題 | 另一個層級 |

②③ 的處置完全不同，而它們在資料上長得很像 —— 分開它們就是這條 recipe 的全部目的。

---

## 1. 一分鐘上手

1. **`Open KLARF…`** 載 **API（RSEM）那一份**當 main。⚠ 不是 EBI —— 理由見 §2。
2. 卡片庫 → Input 段 → 加一張 **`Pair with another source`**。
3. 在那張卡上按 **`Open data…`** 選 **EBI 那一份**。代號會從檔名自動取一個。
4. 卡片庫 → Compare 段 → 加一張 **`H2H`**。
5. **拉兩條線**（見 §3）。
6. 判定段畫三片葉子的樹（見 §5）。
7. 卡片庫 → Output 段 → 加一張 **`Write characterization report`**，填資料夾。
8. `Run all`。

---

## 2. ⚠ main 一定要掛 API，不是 EBI

ground truth 是 API，所以要**走遍的是 API 的清單**。

從 EBI 出發的話，**③ 那一類根本走不到** —— EBI 的清單裡沒有那一顆，就不會有
一列去描述它。而 ③ 的顆數正是這份分析的結論。

這不是偏好，是邏輯上的必然。所以**不要**把方向做成一個選項。

---

## 3. 畫布怎麼接

```
Load one image ──single──────────────┐
   （API 空拍，main）                 ├──> H2H ──> [OUTPUT] Write characterization report
Pair with another source ──paired────┘
   （EBI，第二份）
```

| 從哪 | 到哪 | 意思 |
|---|---|---|
| `Load one image` 的 `single` | **H2H 的 `Search inside`** | 大圖（要在裡面找） |
| `Pair…` 的 `paired` | **H2H 的 `Small image`** | 小圖（拿去找的那一塊） |

**小的當模板、大的當搜尋範圍** —— EBI 的 patch 是 128²、RSEM 是 1000²，
反過來接會直接報「小圖放不進大圖」。

> `Pair with another source` **沒有影像輸入** —— 它是 Input 段的卡，
> 圖是從第二份 lot 撈出來的，不是從上游接來的。所以它左邊沒有埠。

> Output 卡副標寫 `(not connected)` 是**正常的**：Output 段每一張卡都這樣
> （它們是終點，不吐流也不吐特徵）。

---

## 4. 三張卡各填什麼

### 4.1 `Pair with another source`

| 格子 | 填什麼 |
|---|---|
| **Source name** | 按 `Open data…` 之後自動填，通常不用動 |
| **Match by** | `position`（wafer 座標，主力）／`id`（兩邊 DEFECTID 相同時）／`order`（只拿來打通管線）|
| **Within** | 座標容差（nm）。太大會配到鄰居 —— `match_dist_nm` 會告訴你該往哪邊調 |
| **Keep this many candidates** | >1 時多留幾顆給 H2H 用 NCC 挑。座標最近的不一定是對的 |
| **Carry these columns** | **證據**用的（見 §4.1.1）—— 建議 `XINDEX` `YINDEX` `DEFECTID`。清單是那一份真的有的欄位 |
| **Rank within** | 挑 `XINDEX` ＋ `YINDEX` = 每個 die 各自排。留空 = 整份排一組 |
| **Rank by** | **EBI 自己的分數欄**。這一格是 ② 答得出來的關鍵 |
| **Highest first** | 分數欄就開著（最大值第 1 名）|

> **排名的母體是那一份的完整清單**（幾千筆），不是這一批的三十顆。
> 判定段的「跟整批比」在這裡是錯的 —— 它只看得到跑過 pipeline 的那幾十顆。

### 4.1.1 `Carry` 到底要填什麼（**不是你以為的那些**）

最容易誤會的一格。**配對與排名都不需要它** ——

* **座標配對不用**。`XREL` / `YREL` / `XINDEX` / `YINDEX` 在**載檔那一刻**就被
  讀成 `DefectItem` 的座標與 die 了（`ingest/dataset._base_item`），跟 `carry`
  是兩條路。實測：`carry` 一欄都不填，`position` 照樣配得到、`match_dist_nm`
  照樣是對的。**所以不必為了配對去 carry `XREL`/`YREL`。**
* **排名也不用**。`Rank within` 與 `Rank by` 指名的欄位會**自動**加進掛載時要
  複製的清單，不必再手動 carry 一次。

那 `carry` 是給誰的？**給你看的** —— 它決定哪些 EBI 的欄位會變成
`pair_<欄位名>` 出現在 CSV、報表與判定樹裡。所以照「我要在報表上看到什麼」來填：

| 想要 | carry 什麼 | 為什麼 |
|---|---|---|
| **回去 raw data 找得到那一顆** | `DEFECTID` | 沒有它，你只知道「有配到」，不知道配到哪一筆 |
| **確認配對沒有跨 die** | `XINDEX` `YINDEX` | ⚠ **CSV 的固定欄沒有 die** —— 這是唯一把 EBI 那邊的 die 帶進輸出的方法 |
| **判定樹想直接用原始分數**（例：`pair_PMSCORE > 20`）| 那個分數欄 | 只用 `pair_die_rank` 判定的話就不必 |
| EBI 那邊的座標 | `XREL` `YREL` | **通常不必** —— `match_dist_nm` 已經告訴你兩邊差多遠了 |

> 帶不動的欄位（`DEFECTID` 那種字串）**不會變成特徵**（feature 是數字的地盤），
> 它會出現在卡片的面板上。打錯欄位名會在**掛上來的那一刻**就被擋下來。

### 4.2 `H2H`

| 格子 | 填什麼 |
|---|---|
| **Small image** | 拉線決定（`paired`）|
| **Search inside** | 拉線決定（`single`）|
| **Accept above** | 配錯的擋板。預設 0.3 **偏鬆** —— 真資料上對得好應該 0.9 以上，先跑一批看分布再收 |
| **Look this far from the middle** | **維持 15**（Review SEM 移到座標才拍，defect 在中心附近）。⚠ 影像**不是**以這一顆為中心拍的（整片空拍）就要設 **0** —— 見 §7 |
| **Expected shift across / down** | 進階。跑一批取 `align_off_*` 的**中位數**填回來，搜尋框就能再縮小 |
| **Size ratio** | 進階。0 = 自動（從兩張讀資料的卡上的 `Pixel size` 相除）。**兩台機台的像素大小不一樣時一定要有**，差幾個百分比就對不起來了 |

### 4.3 `Write characterization report`

| 格子 | 填什麼 |
|---|---|
| **Write to** | 輸出資料夾（會產 `report.html` / `defects.csv` / `recipe.json` / `images/`）|
| **At most this many rows with pictures** | 預設 200。超過會**講出來**並建議改用 `Write report folder`，但版面不會自動換 |
| **Left picture** | 留空 = 自動挑（rsem 那條路就是 `single`）。要看整片 FOV 就留空或填 `single`；要「兩張圖同一塊區域」填 `aligned` |
| **Right picture** | `paired`（EBI 帶過來那一張）|
| **Numbers to show** | 預設已含兩個擋板 —— **`ncc_score` 與 `align_peak_ratio`**。再加上你 carry 的分數欄與 `pair_die_rank` / `pair_die_total` |
| **Mark where the defect is** | 開著：左圖上畫 **紅框（對到哪）＋ 綠十字（瞄準哪）** |

---

## 5. 判定樹（三片葉子）

**第一步一定要問 `pair_found`**：

```
第一步   pair_found < 1 ?
         Yes → ● 沒偵測到                 （③）
         No  → ◇ 第二步

第二步   pair_die_rank <= <你的 sample 名次門檻> ?
         Yes → ● 抓到了                   （①）
         No  → ● 偵測到但沒被 sample       （②）
```

`<sample 名次門檻>` 就是你們每個 die 取前幾名去 review 的那個數字。

> **為什麼第一步非得是 `pair_found`**：樹只會評「走得到的那條路」。先問它，
> 第三類那一支就永遠問不到 ncc / 分數那幾題，`decide_unanswered` 維持 0。
> 反過來排的話那幾顆會累積一堆「問不出來」的題目。

> **配不到的那一顆不會失敗**：`pair_found = 0`、其餘 `pair_*` 一格都不寫、
> 下游的 H2H 安靜讓路，而這一顆照樣走到判定樹。**那正是要數的東西。**

---

## 6. 報表怎麼讀

一顆一列：

```
defect | ground truth 縮圖 | second lot 縮圖 | 數字欄… | verdict
```

* **上半段**是三類各幾顆（顆數就是橫條寬度）—— 那就是結論。
* **沒配到的那幾顆**：右邊那格是一個破折號（不是破圖），數字欄是**空的**
  （不是 0）。
* **左圖上的兩個記號**：紅框＝EBI patch 對到哪、綠十字＝機台瞄準哪。
  **兩者的間距就是這一顆拍歪了多少**（＝`align_off_*`）。重合 = 對得好。
* 圖是資料夾裡的獨立檔案、路徑是相對的 —— **整個資料夾寄給別人，連結還是通的**。

畫面上（選著 H2H 那張卡時）是同一組語言：同樣的紅框綠十字，加上一行
`matched at (x, y) · off by (±N, ±N) px · score 0.94 (runner-up 12%)`。

---

## 7. 出事了怎麼查（**照這個順序**）

| 症狀 | 先看 | 通常是 |
|---|---|---|
| 一半以上 `pair_found = 0` | `match_dist_nm` 的分布 | **Within** 太小，或兩份 KLARF 的座標系不同。先把它開大 10 倍看配對率會不會跳上來 |
| `ncc_score` 中位數 < 0.3 | `Size ratio` 與 `Pixel size` | **不是配錯**，是兩台機台的像素大小沒對上 |
| `ncc_score` 高（0.9+）但圖看起來不對 | **`align_peak_ratio`** | 接近 1 = **陣列區**，第二名跟第一名一樣好，這個位置是猜的。⚠ 只看 ncc_score 會被騙 —— 解法見 **§7.5** |
| `align_peak_ratio` 整欄都是空的 | `Look this far from the middle` | 窗比遮罩半徑還小 → 那一格**答不出來所以不寫**（見 §7.5 最後一段）。不是壞掉 |
| 綠十字與紅框差很遠 | `align_off_*` | 這一顆 stage 偏移大；整批的中位數填回 `Expected shift` |
| `align_off_*` 每一顆都接近 0，好得可疑 | **EBI patch 怎麼裁的** | 見下面那一則 ⚠ |

### ⚠ 一個要跟機台工程師確認的假設

「拍歪多少」是這樣量的：EBI 的 patch **以 defect 為中心**裁，所以 NCC 找到
patch 落在大圖的哪裡，那個落點的中心就是 defect。

**patch 不是以 defect 為中心裁的話，這個數字的意思就變了**：

| patch 怎麼裁 | `align_off` 量到 |
|---|---|
| 以 defect 為中心（常態）| = defect 離中心多遠 ✓ |
| 中心偏了 (+20,+15) | 多算了那個偏移 |
| **固定格線裁、不管 defect** | **恆為 0** —— 十字與框完美重合，看起來每顆都對得剛剛好，而那個數字跟 defect 無關 |

最省事的確認：問一句「patch 是怎麼裁的」。

---

## 7.5 ⚠ 陣列區（週期性 layout）—— 認錯率與唯一有效的解法

**先講結論：搜尋窗要小於半個晶格週期。** 那一條做到了，週期性就傷不到你；
沒做到，任何比對方法都救不了。

### 為什麼影像本身救不了

陣列區裡「這塊 patch 屬於哪一格」有 **N 個一樣好的答案** —— 那不是演算法不夠
聰明，是**影像內容真的重複**。所以資訊一定得從影像**以外**來，而你手上就有：
KLARF 的座標（機台是照它移過去拍的）。

### 實測的認錯率（週期 25 px、patch 96 px、30 次不同雜訊）

| 情境 | 整張搜 | 15%（±60 px）| **3%（±12 px，< 半週期）** |
|---|---|---|---|
| patch 裡有一顆 defect，FOV 裡另外還有 5 顆 | 30/30 | 30/30 | **30/30** |
| **patch 裡沒有獨特的東西**（純陣列）| **0/30** | **3/30** | **30/30** |

第二列是真正會出事的那一種 —— 而且它**不會失敗**，它會給你一個位置加一個
0.98 的 NCC。第一列告訴你另一件事：**只要 patch 中間真的有那顆 defect，
它就是錨**，附近有別的 defect 也不影響。

### 那個數字怎麼定

```
stage 誤差  ≤  窗半寬  <  晶格週期 / 2
```

* **窗半寬** = `Look this far from the middle` ÷ 100 × FOV 邊長
* 左邊那個不等式：窗要蓋得住機台實際拍歪的量，不然對的那一塊在窗外
* 右邊那個：窗內只放得下**一個**晶格位置，週期性才失去作用

**`stage 誤差 > 週期 / 2` 的話這條路走不通** —— 那時候要先把系統性的偏移吃掉
（見下面的步驟 2），剩下的隨機量才有機會小於半週期。

### 照這個順序做

1. **先用寬窗跑一批**（`search_within = 0` 或 30），看 `align_peak_ratio`
   的分布。**接近 1 = 這一區是週期性的**，接下來的步驟才有必要。
2. 看 `align_off_x_px` / `align_off_y_px` 的**中位數** → 那是這台機器**系統性**
   的偏移，填進 `Expected shift across / down`。填完之後 `align_off_*` 會重新
   以那個點為原點，剩下的散布才是真正的隨機量。
3. 量一次晶格週期（在影像上量兩個相同結構的間距就好）。
4. 把 `Look this far from the middle` 設成
   「**蓋得住步驟 2 的殘餘散布，但半寬小於週期的一半**」。
5. 重跑，確認 `ncc_score` 上去了。

### ⚠ 縮小窗之後，`align_peak_ratio` 會**不見**（這是對的）

第二名是「把最高峰周圍蓋掉之後剩下的最大值」，而遮罩半徑是模板的一半。
窗縮到比遮罩還小的時候，**整張回應圖都被蓋掉** —— 那不是「沒有第二名」，
是「**看不夠遠，答不出來**」。

所以那一格**不寫**（算不出來的不寫）。以前它會寫成 `0.00`，讀起來是
「第一名遙遙領先」—— 而它剛好發生在陣列區、剛好在你最需要它講實話的時候。

**意思是你的擋板換了位置**：從「每一顆一個數字」變成「**那個參數設對了**」。
所以步驟 1 不能跳 —— 週期性這件事要在**寬窗**的時候問清楚。

### 窗小不下來的時候還有什麼

| 做法 | 什麼時候用 | 現況 |
|---|---|---|
| **不要對位，直接用座標裁** | 座標夠準，只需要「同一塊區域並排看」 | 把 `Accept above` 設成 -1（不擋），`ncc_score` 就從「定位工具」變成「驗證數字」|
| **判定樹裡把可疑的分出來** | 想留下全部，但標記哪些不可信 | 樹上加一題 `align_peak_ratio > 0.9`，那一支不採信影像比對，只用座標與排名判 |
| **先扣掉週期背景再對** | 陣列區的正規解 | ⏳ **還沒做**。`core/algo/period.py` 的 `estimate_period` / `choose_origin` 與 `golden.py` 的 `stack_cells` 就是為這件事留著的（`CLAUDE.md` 註明不准刪）—— 疊出 golden cell、相減，剩下的只有 defect，那時候比對就不再多解 |

---

## 8. 不開 Studio 也跑得動

```bash
python -m d4t run char.json <API的.001> --source ebi=<EBI的.001> \
    --csv features.csv --workers 4
```

`--source 代號=路徑` 可以重複。**路徑不進 recipe** —— 同一份 recipe 換一批
資料照跑，第二份每次在命令列指定。

打錯欄位名會在**掛上來的那一刻**就擋下來（那時候還答得出「那它有哪些欄」），
不是等整批跑完才發現。
