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
