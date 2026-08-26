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
