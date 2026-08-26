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
| **Carry these columns** | **EBI 的分數欄**（必填）＋ `XINDEX` `YINDEX` `DEFECTID`。清單是那一份真的有的欄位 |
| **Rank within** | 挑 `XINDEX` ＋ `YINDEX` = 每個 die 各自排。留空 = 整份排一組 |
| **Rank by** | **EBI 自己的分數欄**。這一格是 ② 答得出來的關鍵 |
| **Highest first** | 分數欄就開著（最大值第 1 名）|

> **Carry 是 ②③ 分得開的關鍵。** 少了它，「偵測到但分數太低」跟「根本沒偵測到」
> 在資料上長得一模一樣。

> **排名的母體是那一份的完整清單**（幾千筆），不是這一批的三十顆。
> 判定段的「跟整批比」在這裡是錯的 —— 它只看得到跑過 pipeline 的那幾十顆。

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
| `ncc_score` 高（0.9+）但圖看起來不對 | **`align_peak_ratio`** | 接近 1 = **陣列區**，第二名跟第一名一樣好，這個位置是猜的。⚠ 只看 ncc_score 會被騙 |
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

## 8. 不開 Studio 也跑得動

```bash
python -m d4t run char.json <API的.001> --source ebi=<EBI的.001> \
    --csv features.csv --workers 4
```

`--source 代號=路徑` 可以重複。**路徑不進 recipe** —— 同一份 recipe 換一批
資料照跑，第二份每次在命令列指定。

打錯欄位名會在**掛上來的那一刻**就擋下來（那時候還答得出「那它有哪些欄」），
不是等整批跑完才發現。
