# `recipes/` — 出貨的 recipe

> **d4t — defect**

打開 Studio → **`Open recipe…`**（`Ctrl+Shift+O`）→ 選這裡的檔案。
命令列是 `python -m d4t run recipes/<檔名>.json <資料>`。

**這裡的每一份都有測試守著**（`tests/test_shipped_recipes.py`）：載得進來、
`validate` 沒有 error、接線在該在的埠上、而且**真的跑得出它承諾的東西**。
上一批範例 recipe（`examples/`）2026-08-16 被整個刪掉，原因不是「不需要範例」，
是**沒有人測它們，於是它們爛了**——五份載不進來，而畫面上還留著兩個按了會撞牆
的入口。加一份新的 recipe 到這裡，就在那支測試裡加一段。

---

## `ebi-to-api-characterization.json`

拿 **RSEM 的 API 空拍當答案卷**，回頭對 EBI 掃出來的結果，把每一顆分三類：
① 抓到了、② **偵測到但排名太低沒被 sample**、③ 根本沒偵測到。

完整操作手冊：**[`docs/USING-CHARACTERIZATION.md`](../docs/USING-CHARACTERIZATION.md)**。
這裡只講「打開之後要動哪幾格」。

### 載進去之後要填的（其他都接好了）

| 填哪裡 | 為什麼不能寫在檔案裡 |
|---|---|
| **Pair 卡上的 `Open data…`** → 選 EBI 那一份 | **路徑不進 recipe**（F15）—— 同一份 recipe 換一批資料照跑 |
| **Pair 卡的 `Rank by`** → 你機台自己的分數欄 | 每一台機台那一欄叫的名字不一樣 = 站點資料 |
| **輸出卡的 `Write to`** | 同上。預設 `char_report` 是**相對於你啟動程式的位置** |

`Rank by` 沒填**不會擋著你跑**：每一顆會落在一片叫
**`no ranking column picked yet`** 的葉子上 —— 那是報表在告訴你還有哪一格
沒填，不是一份看起來正常、其實每顆都判錯的結果。填了之後 ① 與 ② 才分得開。

### 已經填好的：`Rank within = XINDEX, YINDEX`

= **每顆 die 各自排名**，也就是絕大多數站點的 sample 規則（「每個 die 取前
N 名去 review」）。判定段的 `sample_top` 就是那個 N，預設 200。

⚠ **這一格不留給你猜是有原因的**：只勾一欄（例如只勾 `XINDEX`）會把整整
一行 die 併成一組，而它**不會報錯、跑得完、數字看起來正常** —— 只有
`pair_die_total` 看得出來。實測會讓「① 抓到了」掉到三分之一、全部灌進
「② 排名太低」。細節見手冊 §4.1.2。

要改的情況只有一種：**你們的取樣規則不是逐 die 分組的**（例如每個
`CLASSNUMBER` 各取前 N 名）。判準是那一句 —— 取樣規則照什麼分組，這裡就填什麼。

### 命令列

```bash
python -m d4t run recipes/ebi-to-api-characterization.json <API的.001> \
    --source ebi=<EBI的.001> --workers 4
```

`--source 代號=路徑` 的**代號要跟卡片上的 `Source name` 一樣**（預設 `ebi`）。

---

## `patch-dsnr-by-class.json`

一整批 patch 的 **dSNR 分布**：去雜訊 → 找重複的那一格（templateGC）→
量 focus 與灰階 → 三刀分四類 → 出**報表**與**一張 box plot**。

```
Load images ──test,ref──> Denoise (gaussian, k=3) ─┬─test──> ROI (templateGC) → gc / gc_center / gc_others
                                                    ├─test──> Focus index
                                                    ├─test──> GLV  (source)
                                                    └─ref───> GLV  (reference source)

        ┌ OUTPUT ─────────────────────────────────┐
        │ Write report (report+images+csv+recipe)  │   ← 兩張都不接線
        │ Write report (box plot)                  │   ← 同一張卡、兩個節點
        └──────────────────────────────────────────┘
```

**SNR 是這樣量的**：GLV 卡開 `each box`（一格一格量，`pooled` 會把幾百格平均
起來、正好把缺陷抹掉），`_outlier` 就是「test 內離典型最遠的那一格」＝ **T**；
參照選「另一塊 @ 另一條流」，區域 `gc_others`、流 `ref` ＝ **R**。

### 判定（三刀）

```
① focus_lapvar  >= focus_min (150) ?   否 → bin 99  garbage (out of focus)
② cmp_snr_mean_outlier > snr_min (4) ? 否 → bin 3   no signal
③ cmp_abs_delta_mean_outlier > delta_min (40) ? 是 → bin 1 strong / 否 → bin 2 weak
```

三個門檻是判定段的 **working number**（`focus_min` / `snr_min` / `delta_min`），
改一個數字改一行，不必動樹。**問不到的題目一律答「否」**，所以量不到 focus
的那一顆會落在 bin 99 —— 方向是安全的那一邊。

### ⚠ 兩件要先知道的

**① 模板要自己畫一次（沒得繞）。** `ROI` 卡的 templateGC 需要
一張**模板影像**加上畫在它上面的框，而模板是一張圖、塞不進 JSON。載進去會有
一條紅字指名那顆按鈕：選那張卡 → **`Edit template & regions…`** → 在你自己的
一格上圈一次。圈完紅字就沒了。

**② 第三刀是 `abs_delta`，不是帶正負號的 `delta`。** `_outlier` 挑的是
「離典型最遠」的那一格，**兩個方向都算**，而 `delta` 帶正負號 —— 暗缺陷是負的，
`> 40` 對它**永遠不成立**（合成資料上實測 −18.6）。用 `delta` 等於一條
「只抓亮缺陷」的規則。

`delta` **仍然一起量**：它是那個差的**方向**（亮還是暗），進 CSV 也進得了
box plot。只要抓亮的話，樹上第三題把 `cmp_abs_delta_mean_outlier` 換回
`cmp_delta_mean_outlier` 就好 —— **不必重跑影像段**。

### 輸出

| 檔案 | 什麼 |
|---|---|
| `patch_report/report.html` ＋ `images/` ＋ `defects.csv` | 一顆一列，點一列換圖 |
| `patch_report/spread.html` | **box plot**：一個盒子一類，畫的是判定問過的那三個數字（`focus_lapvar` / `cmp_snr_mean_outlier` / `cmp_abs_delta_mean_outlier`）|

盒子＝中間一半的 defect，鬚伸到 1.5×IQR 之內最遠的那一顆，超出的畫成小圈。
**四類的盒子不重疊 = 那個數字分得開它們。**

> box plot 那個節點的 `Numbers to plot` 留空 = **判定問過的那幾個**。
> 寫死一份清單的話，樹改了而清單沒改的那一天，圖上畫的就不是在判的東西了。

---

## `rsem-worst-box.json`

**RSEM 單張、沒有參照影像**：一顆 defect 一張圖，圖上鋪滿框，讓 GLV 挑出
「灰階離其他所有框最遠」的那一格。這是抓 defect 最基本的那一招 ——
**沒有第二張圖可以比的時候，同一張圖上的其他框就是參照**。

```
Load one image ──single─┬──> ROI (stripes, crossing)          → on_pattern ───────┐
                        ├──> ROI (stripes, between_vertical)   → between_columns ─┤
                        ├──> ROI (stripes, between_horizontal) → between_rows ────┤
                        └──single──────────────────────────────────> GLV (each box) <─────────┘
                                                                       ▲ 三條虛線都接在同一個 Region 埠

        ┌ OUTPUT ─────────────────────────────────┐
        │ Write report (report+table+images+recipe)│   ← 不接線
        └──────────────────────────────────────────┘
```

### ⚠ 為什麼是**三張** Region 卡，不是一張

三張卡把整張圖鋪滿：**圖案上**（兩組條紋交會的地方）、**直條之間的溝**、
**橫條之間的溝**。三條線都接進同一張 GLV 的 `Region` 埠 —— 那個埠是
`region_keys`（複數），第二條線是**累加**不是取代，每個數字自動帶上區域名
前綴（`on_pattern_glv_worst_score` / `between_columns_…` / `between_rows_…`）。

**這不是為了整齊，是因為只鋪圖案會漏掉一整類缺陷。** 合成 RSEM 上實測
（24 顆，一半是真的）：

| 鋪哪裡 | 準確率 |
|---|---|
| 只鋪圖案上（`crossing`）| **75%** |
| 三個都鋪 | **96%** |

差的那些**全部是暗缺陷**：暗點掉在兩條之間的溝裡，而只鋪在圖案上的框
**正好從它旁邊跨過去**。那一顆跑得完、有數字、而且是錯的 —— 圖上看得見
一個黑點，特徵表上每一格都正常。

### 判定（兩刀）

```
① 量得到嗎（worst < 0，也就是 fill 補的那個值）？  是 → bin 9  nothing to measure
② worst < quiet (2.5)  ？                          是 → bin 0  nothing stands out
③ boxes_off >= 2 ？   是 → bin 2 more than one box is off / 否 → bin 1 one box stands out
```

**「什麼都沒有」是 bin 0，不是隨便一個編號。** `bin != 0` 就是這套工具
（與 CLI 的 ground-truth 對照）認定的「判成真缺陷」—— 挑別的號碼的話，
`python -m d4t run` 底下那一行會說誤殺率 100%，而每一個 bin 的純度表就在
它下面兩行，寫著相反的事。

判定段的三個 working number：

| 名字 | 是什麼 |
|---|---|
| `worst` | `max(三個區域的 glv_worst_score)` —— 整張圖最異常的那一格，單位是穩健 σ。**`fill = -1`**：三個區域都量不到的時候補一個不可能的值，第一刀就把它撈成 bin 9，而不是讓它安靜地滑進 bin 1 |
| `boxes_off` | 三個區域 `glv_boxes_over_k` 相加（GLV 卡上 `Also count boxes beyond = 3σ`）|
| `quiet` | 那一刀的門檻（2.5 σ）。改一個數字改一行，不必動樹 |

**第三刀分開的是兩種完全不同的處置**：一顆髒點（`boxes_off` 0–1）vs
一條橫跨好幾格的東西或整片漂移（`boxes_off ≥ 2`）。合成資料上這一刀
把四條 bridge 全部收進 bin 2，而每一顆單點缺陷都留在 bin 1。

### 疊圖：粗框畫的就是分數說的那一格

報表每張圖上，**細框＝量過的框**（三個區域長得一樣，因為它們就是同一件
事）、**琥珀粗框＝分數來自哪一格**。預設 `near the winner` 只畫贏家附近
25 個 —— 300 個框全畫會把圖蓋滿。

> 這件事 2026-09-02 修過一次，值得記住：以前疊圖畫的是**接線順序第一個
> 區域**的框與**它自己的**贏家。三個區域的時候，標題印著整顆的分數
> （來自 `between_columns`），粗框卻畫在 `on_pattern` 一個 1.3σ 的框上。
> 見 `core/export/overlay.worst_note_for_overlay`。

### 要調的幾格

| 卡 | 格 | 什麼時候動 |
|---|---|---|
| GLV | **Looking for boxes that are** | 知道自己這一層只有暗缺陷（或只有亮的）就選一邊；不知道就留 `both`。⚠ 選錯方向比留 `both` 糟得多：合成資料上（兩種都有）選 `darker` 從 96% 掉到 71% |
| GLV | **Pick the odd one by** | 預設 `glv_mean`。想抓「一格裡的一顆亮點」而不是「整格偏亮」就換 `glv_max` |
| 三張 Region 卡 | **Box inset** | 框往內縮幾個 px。條紋邊緣是糊的，縮太少會把邊緣的灰階算進來 |
| 輸出卡 | **Write to** | 站點資料。預設 `rsem_report` 是**相對於你啟動程式的位置** |

### 命令列

```bash
python -m d4t run recipes/rsem-worst-box.json <你的.001> --workers 4
```
