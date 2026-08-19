# F15 — 配對分析：EBI ↔ RSEM(API) 兩筆資料，逐顆對起來

**狀態**：計畫（2026-08-19）。**程式碼一行都還沒動。**
**前置**：F14-1（資料的入口已經在讀它的那張卡上）
**取代**：本檔案取代先前的 `F15-multi-source.md` 草案（那一版把配對拆成兩張
永遠只能成對出現的卡，見 §3.1 為什麼那是錯的）。

---

## 1. 要解的實際問題：EBI to API Characterization

使用者的原話（整理）：

> API 空拍 = 用 RSEM 機台把 area 布滿點位拍滿，**直接對 RSEM 影像寫 algo 抓
> defect，不經過 inspection**。所以**對 EBI 來說 API RSEM 就是 ground truth**。
> 驗收一隻 EBI recipe 的 sensitivity 時，拿 RSEM 的 true defect 位置與影像
> **回疊 EBI 掃過的位置**，就可以驗證 EBI 有沒有把 defect 掃出來、是否高分、
> 或是**藏在 raw data 內**（分數不夠高，不會被 sample 到去拍）。

正常的 inspection 流程與這條驗收流程的差別：

```
正常流程     EBI scan ──► 高分的 sample ──► Review(RSEM 拍那幾顆)
                              ▲
                              └── 只有被 sample 的才有 RSEM 影像

驗收流程     RSEM API 空拍（拍滿）──► 直接對影像抓 defect = ground truth
                                          │
                                          └──► 回疊 EBI 的 raw KLARF
                                               「這顆真 defect，EBI 怎麼說？」
```

### 1.1 這條流程要答的是三個問題，不是一個

| 回疊的結果 | 意思 | EBI recipe 的問題 |
|---|---|---|
| 配到，而且分數高 / 有被 sample | **抓到了** | — |
| **配到，但分數低、沒被 sample** | **藏在 raw data 內** | 排序／分數的問題 |
| **沒配到** | 根本沒偵測到 | sensitivity 的問題 |

**中間那一列是這個功能存在的理由。** 它要答得出來，就不能只回「配到 / 沒配到」
——**配到的那一顆在 EBI KLARF 裡的欄位（DEFECTID、分數欄）必須變成 feature**，
否則第二列與第一列在資料上長得一模一樣。見 §4.3。

## 2. 資料長什麼樣（為什麼不能只靠座標）

```
   RSEM API（ground truth）                    EBI（受測）
   ┌──────────────────────┐                    ┌────────┐
   │                      │  1000×1000         │        │ 128×128
   │        ▓▓            │  一張大圖蓋住一片   │   ▓▓   │ 以 defect 為中心
   │                      │  area              │        │ 裁出來的 patch
   └──────────────────────┘                    └────────┘
        ▲                                          ▲
        └── 座標來自「algo 在大圖上抓到的位置」      └── 座標來自 EBI 的 KLARF
            → 兩邊的座標都是**近似**的
```

兩件事讓「只比座標」不夠：

1. **兩邊的座標都有誤差**（機台座標系、對位、algo 的中心點定義）。KLARF 給的是
   **近似座標**，容差內可能不只一顆。
2. **尺寸差一個量級**。EBI patch 很小、RSEM 影像很大 —— 所以就算座標對上了，
   **疊到的那一塊 RSEM 也可能根本不是同一個東西**（使用者原話：「也有可能疊到
   的 patch 跟 RSEM 不符合」）。

→ **座標給候選、圖對圖做確認**。這句話就是整個設計。

## 3. 兩張卡

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │  Input                                                              │
 │   [Load images]        EBI patch → test / ref     ← 主流程照舊       │
 │                                                                     │
 │   [Pair with another source]  ────────────────────────────┐         │
 │     · 自己 Open 一份 RSEM API                              │         │
 │     · 用 KLARF 座標找候選（klarf_core.compare 的演算法）    │         │
 │     · 吐一條流 `rsem` ＋ paired / match_dist_nm / 帶欄位    │         │
 └────────────────────────────────────────────────────────────┼────────┘
                                                              ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  Compare                                                            │
 │   [Align to another stream]                                         │
 │     · 小圖（test）當模板，在大圖（rsem）裡 NCC 搜尋                   │
 │     · 吐**裁到跟 test 同尺寸、對齊過的** rsem_aligned ＋ ncc_score    │
 └─────────────────────────────────────────────────────────────────────┘
                                                              ▼
        之後 Enhance / ROI / Measure / ADC **一行都不用改**
        （subtract、glv_stats、roi_compare… 兩邊尺寸一樣就都成立了）
```

### 3.1 為什麼是這兩張，而不是上一版的那兩張

上一版拆成「connector 挑哪一顆」＋「Load #2 讀圖」。**那個拆法立不住**：
Load #2 沒有 connector 不知道讀哪一顆，connector 沒有 Load 吐不出任何影像 ——
兩張永遠只能成對出現的卡就是一張卡。

這一版的拆法通過同一個檢驗：

| 卡 | 單獨用得起來嗎 |
|---|---|
| `pair_source` | ✅ 拿到另一份的對應那顆圖，不做圖對圖也成立 |
| `align_to` | ✅ 任兩條流都可以「小圖在大圖裡找位置」，不需要第二份 source |

### 3.2 為什麼 `align_to` 在 Compare 段

這個 repo 的分段規則：**Compare = 兩張圖進、一張圖出**（`subtract` 是它的原型）。
`align_to` 吃 test + rsem、吐一張裁切對齊過的 rsem —— 逐字符合。

而**裁成同尺寸**正是它最重要的產出：EBI 128×128 對 RSEM 1000×1000 沒有一張
下游的卡比得起來；裁出對齊的窗之後，`subtract` / `glv_stats` / `roi_compare`
全部照舊。

## 4. `pair_source`（Input 段）

### 4.1 參數

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `source` | `str`（唯讀，卡片上按 `Open data…` 選） | `""` | 這張卡自己的那一份資料 |
| `match` | `choice`：`position` / `id` / `order` | `position` | 怎麼配 |
| `tol_nm` | `float` | `500` | 容差（`position` 才顯示） |
| `candidates` | `int` 1–8 | `1` | 座標最近的前 K 顆都留著（給 `align_to` 挑） |
| `carry` | `str`（KLARF 欄位清單） | `""` | 把配到那顆的哪些欄位帶成 feature |
| `out` | `image_key`（out） | `paired` | 吐出來的流叫什麼 |

### 4.2 配對演算法：**已經在 repo 裡了**

`d4t/core/ingest/klarf_core.py:1263` 的 `compare(doc_a, doc_b, tol_nm, mode)`
**就是 KLIP 的那一支**（KLIP 是 d4t 的六個來源專案之一，`klarf_core` 整份
vendored 過來）。它現在**沒有任何呼叫者** —— 這一輪就是它的用途。

它做的事：

```
  以 die 分桶 ─► 桶內用 tol_nm 大小的網格雜湊 ─► 找容差內最近的一顆
                                              └► used_b：一對一，不重複配
  mode='id' 走另一條：直接依 DEFECTID join
```

要加的只有一件事：**回傳距離**（現在只回配到誰）。`candidates > 1` 時回前 K 個。

### 4.3 產出

| feature | 意思 |
|---|---|
| `paired` | 0 / 1 |
| `match_dist_nm` | 配得多近（**座標系對不上的時候，它會是整片 wafer 的尺度**）|
| `match_ambiguous` | 容差內不只一顆 |
| `pair_defect_id` | 配到那一顆的 DEFECTID |
| `pair_<COLUMN>` | `carry` 列的每一個 KLARF 欄位（例：`pair_ROUGHBINNUMBER`）|

**`carry` 是 characterization 的關鍵**：有了它，「藏在 raw data 內」才寫得成
一句分數表達式（例：`paired == 1 and pair_SCORE < 20`）。

### 4.4 配不到的那一顆

不吐流、`paired = 0`。下游要那條流的卡會失敗 → **這一顆 `ok=False`，整批照跑**
（鐵則 7）。這跟 `load_sidecar` 遇到沒有 label 的那一顆是同一個行為，
**不發明第二套**。

## 5. `align_to`（Compare 段）

### 5.1 它在做什麼

```
   test (128×128)              rsem (1000×1000)
   ┌────────┐                  ┌──────────────────────┐
   │   ▓▓   │  ── 當模板 ──►   │        ┌────────┐    │
   └────────┘                  │        │   ▓▓   │◄───┼── NCC 峰值
                               │        └────────┘    │
                               └──────────────────────┘
                                        │
                                        ▼
                              rsem_aligned (128×128)  ＋ ncc_score
```

`cv2.matchTemplate(TM_CCOEFF_NORMED)` + 拋物線次像素精修 —— **兩件事 repo 裡
都有了**（`algo/align.py` 的 `ncc_score` / `parabola_subpx` /
`_calculate_alignment_template`）。差的只是「模板比搜尋圖小很多」這個情形，
約 20 行。

### 5.2 參數與產出

| 參數 | 說明 |
|---|---|
| `template` | 小的那條流（預設 `test`） |
| `search` | 大的那條流（預設 `pair_source` 吐的那條） |
| `min_score` | 低於這個就算沒對上 |
| `out` | 裁切對齊後的流名 |

| feature | 意思 |
|---|---|
| `ncc_score` | 疊得多像（0–1） |
| `align_ok` | 有沒有過 `min_score` |
| `align_dx_px` / `align_dy_px` | 對到大圖的哪裡（次像素） |

### 5.3 `candidates > 1` 時：**座標給候選，NCC 選最像的**

這正是使用者那句「也有可能疊到的 patch 跟 RSEM 不符合」的解法：

```
   座標最近的 3 顆 RSEM ──► 各做一次 NCC ──► 取分數最高的那一顆
                                             └─► 其餘的分數也留著（第二高
                                                 跟最高差很少 = 可疑）
```

配錯的那一顆**不會安靜地過去**：`ncc_score` 會掉下來，而它是一個擋得掉的數字。

## 6. 引擎要動的三件事（都小）

### 6.1 多一份 dataset

```
Dataset(main)                 ← 迴圈跑它、route 由它的 kind 決定、KLARF 寫回它
  └ sources: {sid: Dataset}   ← 這張卡自己 Open 的那一份
```

`run_batch(recipe, dataset, others={sid: Dataset})`；`DefectItem` 裝的是路徑
不是像素，所以 worker 拿得到（picklable）。

### 6.2 鐵則 9：**卡片不自己 `open()`**

「這張卡 load 自己的 source」是**使用者看到的事**。引擎裡讀檔的仍然是 ingest ——
Studio / CLI 把那一份載成 `Dataset` 掛上去，卡片只從掛好的東西裡挑一顆。

為什麼不能讓卡片自己讀檔：影像段快取的簽章是照「這份資料是什麼」算的。卡片
偷偷讀檔的話，**換一份第二 source 而簽章看不見 → 回舊影像**，而那是「跑得完、
有數字、而且是錯的」。F9 踩過兩次。

掛上去之後簽章自動涵蓋它 —— `_dataset_token_for` 已經對 sidecar 做過同一件事
（`_sidecar_token`），這裡只是多一個來源。

### 6.3 路徑不進 recipe

卡片存的是**代號**（`source="rsem"`），路徑跟著這一次的工作階段走 ——
跟 main 那一份同一條規矩，理由也一樣：recipe 要能換一批資料重跑。

* Studio：卡片上那顆 `Open data…`（F14-1 已經是這個形狀）
* CLI：`python -m d4t run r.json <main-klarf> --source rsem=<path>`

## 7. main 選哪一邊 = 你在問哪個問題

| main | 迴圈跑 | 答的問題 | 典型用途 |
|---|---|---|---|
| **RSEM API** | 每一顆 ground truth | **EBI 漏了幾顆**（recall / sensitivity） | 驗收一隻 EBI recipe |
| EBI | 每一顆 EBI 偵測 | 我掃到的有幾顆是真的（precision） | 看 nuisance 率 |

**同一張卡，兩份 recipe。** 這也是「指定一個 main」這個決定的全部意義。

## 8. 分三步

| 步 | 做什麼 | 怎麼驗收 |
|---|---|---|
| **A** | `pair_source`（`match="order"`）＋ 第二份 dataset 掛上去＋快取簽章 | 管線端到端跑得通；**`workers=1` 與 `workers=4` 逐位元組相同**（鐵則 9 那條測試） |
| **B** | `match="position"`（接上 `klarf_core.compare`）＋ `carry` ＋ 儀表 | 拿**真實的兩份**量配對率與 `match_dist_nm` 的分布 |
| **C** | `align_to`（NCC ＋ 裁切）＋ `candidates>1` 的挑選 | 量 `ncc_score` 的分布；刻意配錯一顆，看它掉下來 |

**A 之前不要碰 B**：順序配對幼稚，但它讓「兩份資料」這件事先跑起來；配對規則
要拿真實資料調，那是 B 的事。（GLAS 那條路就是這樣做的：先寫健檢跑真實匯出，
才寫卡片，而那次健檢推翻了三個猜測。）

## 9. 明講不做的事

* **第二份不寫回 KLARF、不進 defect 導覽、不進 Export** —— 它只是圖與座標。
* **不做 N 份**：一張卡一份。要第三份就再放一張卡。
* **不動 route**：route 仍由 main 的 `kind` 決定。
* **座標系對齊**（兩份 KLARF 的原點／die grid 不同）先不做 —— 先讓
  `match_dist_nm` 把它**量出來**；真的需要，那是之後另一張卡，而且到那時候
  我們手上會有真實的距離分布可以看。
