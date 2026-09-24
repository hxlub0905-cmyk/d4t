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

## `ebi-die-to-die.json`

**EBI patch，一顆兩張**：test 是這一顆、ref 是另一片 die 上同一個位置。兩張先拉到
同一個亮度（ref 借 test 的範圍，兩張才比得起來），相減、把差異圖用小 median
壓掉雜訊，然後 GLV 讀差異圖裡**最亮的那一點**。真缺陷是兩片 die 唯一不共有的
東西，所以它是相減之後留下來的；雜訊與輕微的圖案漂移到不了同一個高度。
判定只問一句：那個峰有沒有高過「安靜」的水位（`quiet`，預設 32）。

```
Patch ──test─┬──> Normalize (test)           ──test──┐
                   ├──> Normalize (ref, range from test) ──ref──┤
            ──ref──┘                                            ▼
                                                    Subtract |test − ref| ──diff──> Denoise (median 3) ──diff──> GLV (glv_max)
        ┌ OUTPUT ─────────────────────────────────┐
        │ Write report (report+table+images+recipe)│   ← 不接線
        └──────────────────────────────────────────┘
```

這一份也是 Studio「用範例資料試一次」背後那份 recipe（`tools/make_sample.py`
產的合成 lot 就是 `ebi_patch`）。合成資料上實測三個 seed 各 24 顆：22–24 中，
真缺陷的峰是雜訊最高值的 4 倍以上（`tests/test_shipped_recipes.py`）。

---

## `rsem-worst-box.json`

**RSEM 單張、沒有參照影像**：一顆 defect 一張圖，圖上鋪滿框，讓 GLV 挑出
「灰階離其他所有框最遠」的那一格。這是抓 defect 最基本的那一招 ——
**沒有第二張圖可以比的時候，同一張圖上的其他框就是參照**。

```
SEM image ──single─┬──> ROI (stripes, crossing)          → on_pattern ───────┐
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

---

## `one-image-uniformity.json`

**一張影像、沒有 KLARF、沒有參照**：用 `Open images…` 打開（指到那張圖，或指到
一整批），這一份把量測框鋪滿整個視野、**逐格量一次**，然後回答一句話 ——
**這片區域的灰階均不均勻**：CV %，以及左右與上下各斜了多少（`slope_per_100px`）。

```
                                        ┌──→ Write charts    四張圖 + 一張自己配的
SEM image ──single─┬──> ROI (stripes) ┄cells┄> GLV (across boxes)
                        └──single──────────────────→ ┘   └──→ Write report   defects.csv + recipe
```

（`ROI` 到 `GLV` 那一條是**虛線** —— 區域走的是菱形埠，跟影像流不同埠。）

**它刻意只給數字，不給判決。** 這裡沒有任何一個門檻說「這片算好還算壞」——
那個數字是你的，而且每一層都不一樣。判定樹只分兩類：
`spread < 0`（`glv_mean_cv_pct` 沒量到，`fill` 補 −1）→ bin 9「nothing to measure」，
其餘 → bin 0「measured」。**「一張沒有圖案可找的圖」因此不會被當成「完美平坦」。**

### 為什麼兩張 Output 卡都在

`Write charts`（`output_uniformity`）畫的四張圖是**拿來看的**：box plot、
直方圖、位置剖面、熱圖 —— **一個點是一格量測框，不是一顆 defect**，所以
一道橫跨視野的梯度在圖上就長得像一道梯度，而且看得出它在哪。
那張卡還有第五格讓你自己配（挑兩欄放到軸上），出貨的檔案裡沒有勾。

`Write report`（`output_report`）把**同一批數字**寫進 `defects.csv`，並把這份
recipe 複製一份進去 —— **圖是拿來看的，CSV 是拿來留的**。
（F85 出貨的第一版只有圖，`tests/test_shipped_recipes.py` 為此加了一條。）

### 要調的幾格

| 卡 | 格 | 什麼時候動 |
|---|---|---|
| ROI | **Box inset** | 框往內縮幾個 px。條紋邊緣是糊的，縮太少會把邊緣的灰階算進來 |
| GLV | **Pick the odd one by** | 預設 `glv_mean`（整格的平均）。要看「格子裡最亮的點」才換 |
| 兩張輸出卡 | **Write to** | 站點資料。出貨的檔案填的是**相對路徑**，會落在**資料旁邊**（KLARF 所在的資料夾；沒有 KLARF 就是影像那個資料夾） |

完整的一格一格說明在 [`../docs/USING-UNIFORMITY.md`](../docs/USING-UNIFORMITY.md)。

### 命令列

```bash
python -m d4t run recipes/one-image-uniformity.json <一個放影像的資料夾> --workers 4
```

---
