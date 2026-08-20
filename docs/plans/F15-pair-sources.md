# F15 — 配對分析：EBI ↔ RSEM(API) 兩筆資料，逐顆對起來

**狀態**：**A / B / C 全部做完**（2026-08-19）＋ **第二輪 F15-2**（用起來的那
兩件事：背景載入、三格用選的）。驗收見 `tests/test_pair_source.py`（27 條）與
`tests/test_ui_f15_pair_source.py`（21 條）。落地與計畫的差異記在 §10，
F15-2 記在 §11。
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


---

## 10. 做完之後：跟計畫差在哪

三步一次做完（使用者：「開工，請一路到 C 做完」）。計畫沒寫、但實作逼出來的
四件事：

### 10.1 `carry` 打錯一個欄位名，以前會安靜地沒事

`carry="ROUHGBINNUMBER"`（打錯字）本來會落進「這欄是空的」那條路，於是 CSV 少
一欄 —— 而**那一欄正是這張卡存在的理由**（「偵測到但分數太低」只有靠它答得
出來）。少一欄的 CSV 跟成功的 CSV 長得一模一樣。

現在配到的那一顆**沒有那個欄位**就擋下來，訊息裡同時有打錯的那個、真的有的那
幾個、以及要改哪一格。那幾顆 `ok=False` 而整批照跑（鐵則 7）。

### 10.2 循序路徑沒有 pin cv2 —— 鐵則 9 的洞

`run_batch` 的循序路徑註解寫著「語意同平行路徑」，但 worker 一進去就
`pin_cv2_deterministic()`，循序那條不套。cv2 的 IPP 會依 buffer 對齊選不同的
SIMD 路徑，於是 **NCC 那種卡的分數在 `workers=1` 與 `workers=2` 差在 1e-7**。

那正是鐵則 9 講的東西，而且更糟：**Studio 的試跑走的就是循序那條**（一顆 →
`n <= 1`），所以那個差還會變成「畫面上的數字」與「批次的數字」不一樣。
F15 只是讓它現形（在這之前沒有一張卡在這條路上用 NCC）。

修法是循序路徑也 pin。便利貼：
`tests/test_batch_cache.py::test_the_serial_path_pins_cv2_the_same_way_the_pool_does`。

### 10.3 配對卡是 `is_source()`，所以畫布本來會印錯檔名

`_card_summary_parts` 對每一張 `is_source()` 的卡印 `dataset_name` —— 而配對卡
讀的**不是**目前這份 lot。什麼都不做的話它會在自己身上印 main 的檔名，
一個標準的「畫布說謊」。現在它印的是掛在它那個代號上的第二份。

### 10.4 儀表：分布答不出來的那兩件事

`match_dist_nm` / `paired` / `ncc_score` 的整批分布 `MeasureInspector` 本來就
在畫（調容差要看的正是那張圖）。`PairInspector` 只多兩件它答不出來的：
**對到的是第二份裡的哪一顆**（使用者要拿 DEFECTID 回去翻原始資料），以及
**帶過來的字串欄位** —— 那些欄位不在特徵表裡（feature 是數字的地盤），
沒有這裡的話它們哪裡都看不到。

### 10.5 一個測試 harness 的洞（順手補）

`test_ui_f7_9_feedback` 的「每張卡都要有一條走得通的路」把**前置鏈裡**那張卡
講的「還沒設定完」歸給了這一輪的主角，於是拿 A 的欄位表去驗 B 的訊息。
`align_to` 的前置是 `pair_source`，一接上就撞到。現在歸給發出它的那張卡。


---

## 11. F15-2：拿真實資料用了一次之後（2026-08-19）

使用者回報六件事，這一輪做前兩件（其餘記在 §12）。

### 11.1 「開 EBI raw data 會無法回應一陣子」

**是同一件事有兩種做法，而慢的那一種是使用者會遇到的那一種。** main 那一份
早就在背景載了（`dataset_worker` + 進度條），第二份走的卻是
`DatasetLoadWorker.run_sync` —— 直接卡住 UI 執行緒。

```
以前                          現在
Open data… ─► run_sync ─┐     Open data… ─► pair_worker.start ─┐
                        │                 （立刻回來、進度條轉）  │
              UI 凍住 ──┘                                       │
                              …載完 ─► loaded ─► _on_pair_source_loaded
```

* 第二份用**另一個** `DatasetLoadWorker`（`pair_worker`）—— 跟 main 是兩件可以
  同時發生的事，共用一個的話「已經有工作在跑」會把其中一個默默擋掉。
* `attach_pair_source(..., sync=True)` 留給測試與 headless（同
  `load_dataset_path` 的慣例）。
* 「載到一半」是一個要記住的狀態：`_pending_pair = (哪張卡, 哪個檔)` ——
  載完才知道要掛到哪張卡上。

### 11.2 只複製 `carry` 要的那幾欄

`fill_fields` 本來把**每一顆**的**每一欄**都複製一份。raw data 是幾十萬顆
×24 欄字串 = 幾百 MB，而其中 22 欄從來沒有人 `carry` —— 而且那幾欄還要 pickle
進每一個 worker（`sources_for_run` 只送 items）。

* `fill_fields(dataset, columns=None)`：`None` = 全部（CLI／測試的路）。
* 要哪幾欄由 **`steps/pair_source.columns_for_source(nodes, sid)`** 回答 ——
  指著那個代號的每一張卡的 `carry` **聯集**（同一份可以被兩張卡指著）。
  它住在卡片那一側，因為 `carry` 的意思是那張卡的事。
* `carry` 之後改了 → `refill_fields`（KlarfDoc 還在手上，很便宜）。
  **整個換掉不是疊加**：少填一欄的時候舊的還留著的話，「這一欄還在不在」
  就有兩個答案。

⚠ 這裡冒出一個新的說謊點並且修掉了：卡片跑起來時手上**只有複製過去的那幾
欄**，所以它原本那句「Its columns are: …」會把「你要的那幾欄」講成「那一份有
的那幾欄」。現在分成兩句話，各自只講自己答得出來的：

| 誰講 | 什麼時候 | 講什麼 |
|---|---|---|
| `ingest.missing_columns` | **掛上來／勾起來的當下**（doc 還在手上） | 「這一份沒有 X —— 它有的是 A, B, C…」 |
| 卡片的 `run()` | 跑起來（backstop） | 「帶過來的是哪幾欄」 |

CLI 也在 attach 之後就擋下來 —— 整批跑完才發現「那一欄根本不存在」是最貴的
一種發現方式。

### 11.3 三格用選的（`ParamSpec.choices_from`）

使用者：「太不方便，要自己填（希望可以自動帶出來用選的）」。

三格的答案程式都知道，只是**執行期才知道**：

| 欄 | 選項從哪來 |
|---|---|
| `Source name` | 現在掛了哪幾份第二 source |
| `Which image` | 那一份的一顆有哪幾張圖 |
| `Carry these columns` | 那一份的 KLARF 有哪些欄 |

所以不是 `ParamSpec.choices`（卡片列得出來的一張表），而是新的
**`ParamSpec.choices_from`** —— 填一個 `RUNTIME_CHOICES` 裡的鍵，
UI 去問 Studio 要清單。這是 `stream_choices` / `region_choices` 的第三次：
**程式知道的名字不該讓使用者用打的。**

**為什麼不是 `type="choice"`**：`choice` 的 `validate` 會擋掉不在清單裡的值，
而 recipe 是**在資料掛上來之前**讀進來的 —— 那時候一份都還沒掛，於是每一份
存了 source 名字的 recipe 都會在開檔的那一刻爆掉。型別維持 `str` /
`multi_choice`（兩者都不強制值落在清單裡），`choices_from` 只影響**打字還是
用選的**。可編輯的下拉：清單是現在載了什麼，值仍然可以是還沒載進來的名字。

**換清單不重建表單**（`ParamForm.set_dynamic_choices`）：重建會把游標搶走，
而這件事最常發生的時機正是「使用者剛在 Source name 那一格打字」（那一格一改，
另外兩格的清單就跟著變）。有游標的那一格**整格跳過** —— 只保住文字不夠，
`clear() + addItems()` 會把游標推到字尾。

**空清單要講話**：「還沒掛第二份」是正常狀態，而它畫出來是一塊空白 ——
留白讀起來像壞掉。三個鍵各有一句話（`ParamForm._EMPTY_HINTS`）。

**指著一個沒掛上來的代號 → 兩格都是空的**，不拿「唯一掛著的那一份」去頂替：
那一格印的欄位就會是另一份的，而畫面說謊比空白糟。

## 12. 還沒做的（使用者回報，排過序）

1. **像素尺寸不同**（`align_to` 不含縮放）—— 見 §12.1，這是「對不上」的主因。
2. **大圖對小圖的搜尋策略**：先用座標裁一塊再 NCC、峰的第一二名差距當 feature。
3. **by-die 排名**：報表的固定欄沒有帶 die（`BASE_COLUMNS`）。
4. **並排的第二條流**：已經有（連動縮放），要的是「預設就把 test 與 aligned
   擺在左右」這件事自動發生。


---

## 13. F15-3：像素大小（2026-08-20）

使用者：「像素尺寸不同，可以預設一樣，或給 user 輸入」＋「在 load image 那邊
source（各種 source），可以輸入 nm/pixel（也可以不輸入）」。

### 13.1 一格 nm/px 長在把那份資料讀進來的那張卡上

`load_patch` / `load_single` / `pair_source` 各有一格（`_util.nm_per_px_spec`，
預設 0 = 不知道，收在進階裡）。規則因此是**一句話**而不是三句。

2026-07-30 曾經拿掉 `cd_x_nm` 那一組，理由是「nm/px 沒有來源，所以每一顆都是
0，而 0 是個看起來很像答案的答案」。**這一格正是那個來源** —— 那次的結論沒有
被推翻，是被補完了。

### 13.2 多一組，不是換掉

使用者原本的提案是「有輸入單位就用 nm，沒輸入就用 pixel」。那會讓**同一個特徵
名在不同資料上是不同單位**：

```
recipe：  score = cd_x > 50
資料 A（沒填）→ 50 pixel → bin 1
資料 B（填 1.5）→ 50 nm  → bin 0     ← recipe 沒改、卡片沒改
```

而 CSV 上看不出來。所以改成 **`cd_x_px` 旁邊多一個 `cd_x_nm`**：單位在名字上，
舊 recipe 一個字都不用改，兩批資料混算也對得起來。面積乘平方（`area_nm2`）——
名字結尾看不出來，所以 `_util.AREA_FEATURES` 列著它。

沒填就一個 `_nm` 都不產出；而**下拉裡也不列**（`RecipeModel.available_features`
—— 量測卡看不到 Load 卡上填了什麼，但那張表看得到每一張卡）。

### 13.3 nm/px 掛在**流**上，不是一個全域數字

一份 pipeline 可以同時吃兩份資料，而兩台機台的像素大小不一樣 —— 那正是
`align_to` 要縮放才對得起來的原因。所以數字掛在流上
（`Context.stream_nm_per_px`），由把那條流吐出來的那張卡填。
`align_to` 因此不必知道誰是誰。

### 13.4 `align_to` 的 `Size ratio`

`scale` 預設 **0 = 自動**（兩條流的 nm/px 相除），填了就以填的為準。
算出來的值**變成一個特徵**（`align_scale`）—— 它影響每一顆的結果，不可以只
活在某個人的腦子裡。

實測（同一塊區域、1.5 倍的像素大小差）：

| | NCC |
|---|---|
| 不處理尺度 | **0.03**（看起來就像「配錯了」）|
| 自動算出 0.667 | **0.93**，位移 (40, 90) 完全正確 |

**只有拿去比對的那一份被重採樣**，裁出來的那一塊原封不動 —— 重採樣會動到灰階，
而下游量的正是灰階。所以 `out` 那條流是**大圖的像素**，而它帶著大圖的 nm/px：
下游在它身上量 CD 的時候 `_nm` 那一份才會是對的。
