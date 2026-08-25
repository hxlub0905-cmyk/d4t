# F29 — 把已經量到的位置說出來，加上報表 bundle

> 狀態：**Phase A 完成**（2026-08-25）。B／C 未開始。
> 主計畫：[`docs/ROADMAP.md`](../ROADMAP.md)。

---

## 1. 為什麼

使用者是 defect team 的分析工程師。跑完一整筆 image 之後他要看到的是
**「缺陷被抓出來」**：位置框起來、照分數排序、6000 顆一次出成報表。

第一版計畫的前提是錯的。我寫「像素級的位置沒有 → 要做一張新的偵測卡」，
使用者連問兩次：

> 「Q3 你還是沒回答我，GLV CD 在 Measurements 就已經量出這顆 defect 或位置的
> 一些資訊了（這些資訊不能拿來用嗎）」

去讀了程式碼之後 —— **他是對的**。

---

## 2. 三個問題的答案（查過程式碼的那一版）

### Q3：GLV／CD 已經量到的資訊，不能拿來用嗎

**能。缺口不是「量不到」，是「量到了、畫在螢幕上了、然後丟掉」。**

`cd_measure` 的團那一支，在 F29 之前就已經在做這些事：

| 在哪 | 做了什麼 |
|---|---|
| `steps/cd.py` `_note_blob` | 算出整條輪廓（正規化座標）與最長那條弦 |
| 同上 | 存進 `ctx.meta["cd"][前綴]` |
| `steps/cd.py` `_blob_marks` | **已經畫在 Studio 預覽上了** |
| `features_out`（26 個）| `cd_area_px` `cd_deq` `cd_feret_max/min` `cd_aspect` `cd_roundness` `cd_pieces` `cd_touches_edge` …… |

那 26 個特徵**沒有一個是「在哪」**。`cd_touches_edge` 甚至證明程式碼知道它貼在
哪一邊，卻沒把位置說出來。

更下面一層也一樣：`algo/shape.py::measure_blob` 呼叫
`cv2.connectedComponentsWithStats`，拿到的 `stats` 只用來判 `touches_edge`
就丟掉，`centroids` 直接接成 `_cent`。**外接矩形與質心本來就算好了。**

⚠ **這沒有把 F19 那個決定翻過來。** F19（2026-08-21，使用者：「就得完全刪掉
以新的為主」）刪掉 `cd_x_px` / `cd_y_px` / `area_px`，理由寫在 `cd.py` 檔頭：
**舊值是 bbox，跟新值不是同一種量測**。那是在防「同一個名字悄悄換意思」，
不是在說位置沒用。所以位置用**新名字**回來，舊名永遠不會再出現。

**GLV 那一半是完整的**：`glv_stats` 的 `reference` 有一個選項就叫
`the other regions` —— 「這一塊」對上「其餘那些」，吐 `cmp_delta_*` /
`cmp_snr_*`。那幾個數字就是「哪一塊不一樣、差多少」。

⇒ 兩級 detect 用**現有的卡**就講得完：

```
GLV（哪一塊不一樣、差多少）→ CD（那一塊裡面，東西在哪、多大）
```

### Q：「Detect 你要 detect 什麼？數字？」

**不是數字，只欠一個框。**

| 你要的 | 現況 |
|---|---|
| 框（x, y, w, h）| **CD blob 量到了但沒吐出來** ← 真正的缺口 |
| 排序 | 已經有：你自己寫的 `score`（`overlay.pick_overlay_results` 照它排）|
| 「多可疑」當成打分的原料 | `cmp_snr_mean`（區域級）已經有；`blob_strength`（像素級 σ）是 `find_defect` 唯一新增的數字 |

所以 `find_defect` 是**退路**不是主力。

### Q2：golden cell 跟 GDS 同樣重要，要在同一張卡

**收下**（第一版寫「GDS 為主力」是錯的）。這正是這個 repo 自己的規矩
（`CLAUDE.md` §3「同一個家族的做法收成一張卡的 `method`」），也**已經做過一次
一模一樣的事**：`roi_compare` → `glv_stats` + `method="compare"`
（`recipe.py::_migrate_roi_compare_into_glv_stats`，2026-08-20）。

**而且沒有黃金值擋路**：`tests/fixtures/golden/` 三份 recipe 用到的卡是
`load_patch / normalize / denoise / align / subtract / glv_stats / cd_measure`
—— **一張 Region 卡都沒有**。

---

## 3. Phase A（✅ 2026-08-25）：讓位置有出口

### A1 — CD blob 模式吐位置

* `algo/shape.py` 的 `BlobResult` 多兩格：`bbox` 與 `centroid`
  （兩個都是 `connectedComponentsWithStats` 本來就回傳、然後被丟掉的東西）。
* `steps/cd.py` 的 `ALWAYS_BLOB` 多六格：`cd_box_x/y/w/h` ＋ `cd_cx`/`cd_cy`，
  **座標是整張影像的像素**（區域偏移在卡片裡加回去，換算只做一次）。
* 一律吐而不是 `size_report` 上的一個選項：**位置不是「要不要量」的選擇，
  是「我剛才量在哪」**。
* 量不到就**一格都不寫**（不是 0：0 會讓疊圖在左上角畫一個 0×0 的框）。
* **不配 nm 版**：框是「畫在哪」不是「多大」。給框配 nm 等於請人拿 bbox
  當尺寸用，而那正是 F19 拆掉的東西。
* `line` 模式留白：它的「位置」是一條掃描線，不是一個東西。

### A3 — overlay 認得它

`export/overlay.py::primary_blob_box` 的退路寫成一張表（`_BOX_FEATURE_SETS`），
順序 = `blobs` → `blob_*` → `cd_box_*`：**去圖上找出來的贏過順手量到的**。

⚠ 只認**沒有前綴**的那一份。接了兩個以上區域時名字會變成 `epi_cd_box_x`，
那時候「主 blob」有兩個答案 —— 挑一個畫、畫面上又不說是哪一個，就是
「跑得完、有圖、而且是錯的」。

### A2 — `find_defect`（Measure 段第四張卡）

在一條流（可再指定區域）裡切出過門檻的每一團，照「比背景高出幾個 σ」排序，
**取最強的一個**。演算法在 `algo/shape.py::find_blobs`，跟 `measure_blob`
**共用同一組準位與門檻**（`pick_levels` / `threshold_level` / `edge_quality`）。

* 吐 `blob_x/y/w/h`（**正是 `primary_blob_box` 本來在讀的那四個**）、
  `blob_cx/cy`、`blob_strength`、`blob_area_px`、`blob_deq`；
  一律吐 `blob_n` / `blob_bright` / `blob_edge_score`。
* 預設 `source="diff"` —— 唯一一張預設吃差影像的量測卡（結構已經減掉，
  剩下的就是缺陷）。前置鏈因此要有 `subtract`。
* **不呼叫 `ctx.add_region()`**、**不寫 `ctx.meta["blobs"]`**。

**界線移動了，而移的是哪一格要講清楚**（使用者 2026-08-20：「Blob 分割不需要
也不要再出現」）：

> **可以找一個框，不可以產生具名區域。**

具名區域是下游每一張卡的輸入（`roi=`），一張卡自動長出區域等於畫布上出現一條
沒有人拉過的線 —— F9 那六個「跑得完、有數字、而且是錯的」全部長那個樣子。
一個框只是一組數字，跟任何一個特徵一樣**要有人接才會被用到**。

### A0（順手抓到的真 bug）— 卡片庫的順序一直是字母序

`list_steps()` 同一類裡是照 `key` 排的。所以 2026-08-25 使用者說「Measure 的
card 順序幫我改命名&重排：GLV → CD → Focus index」，那一輪改了
`steps/__init__.py` 的 import 順序、還在那裡寫下「卡片庫裡看到的先後住在這三
行」—— **而畫面上一格都沒有動**（字母序是 CD、Focus index、GLV）。
整個改動看起來完成了，全套測試也全綠，因為沒有任何一條測試問過
「使用者看到的第一張是哪一張」。

改成**純註冊順序**（`category` 不再參與排序 —— 它跟卡片庫的分區是兩條不同的
軸，兩條一起排的結果是「import 順序決定看到的先後」只對了一半）。
每一段因此讀起來就是資料流過的順序：

```
input    Load images → Load one image → Load layout labels → Pair with another source
enhance  Normalize → Denoise → Adjust tone → Remove background / stripes
region   Profile → GDS layers → Mask from regions → Template
measure  GLV → CD → Focus index → Find defect
compare  Image Combination → H2H
output   Write CSV → Write report → Write KLARF → Write images → Write HTML
```

便利貼：`tests/test_card_library_order.py`。

---

## 4. Phase B（未開始）：Reference regions —— GDS 與 golden cell 同一張卡

`roi_from_mask` 就地改成一張有 `method` 的卡：

* **key** `roi_from_mask` → `roi_reference`；**label**「GDS layers」→
  **「Reference regions」**。
* **method（兩個，地位相同）**
  * `golden_cell`（預設）—— `algo/period.py::estimate_period` 找週期 →
    `choose_origin` 定相位 → `algo/golden.py::tile_coords` 吐出每一個完整
    cell 的框。**每個 cell 就是一塊區域。**
  * `gds` —— 今天的行為，一層一塊，形狀照 GLAS 給的。
* 共用參數擺前面（`source` / `output_prefix` / `max_boxes` / `pick` /
  `pick_source` / `drop_edge` / `edge_margin`），method 專屬的用 `show_when`。
* 接上共用的 `pick_rule_specs()` 並改用 `set_region_family()` ——
  於是多出 `<name>_center`（挑出來的那一塊）/ `<name>_others`（**參照**）。
* **誠實閘門**：`estimate_period` 本來就有 modulation gate 與 confidence，
  量不到週期時 `StepError` 明講，不可以吐一格垃圾晶格。
* 遷移照 `_migrate_roi_compare_into_glv_stats` 抄（判準是「舊 step 名在不在」，
  鐵則 9），命中就換 key 並寫入 `method="gds"`。

`roi_from_mask` 那段「刻意不吐 `_center`」要**改寫**成新的界線，不是刪掉：
幾何的 `_center`（缺陷在正中央）在大圖上仍然沒有意義，所以這條路要用
`pick="strongest"` —— 它不假設，它去找。

接完之後**不需要任何新卡**就有兩級 detect：

```
roi_reference(method=golden_cell|gds, pick=strongest)
      → glv_stats(roi=epi_center, reference="the other regions")  → cmp_snr_mean
      → cd_measure(roi=epi_center, shape=blob)                    → cd_box_*
```

⚠ **要先量的一件事**：`max_boxes` 預設 8192（GDS 一層實測可到 ~5000 個矩形）。
`set_region_family` 在 5000 塊上會產生一個 4999 塊的 `_others` —— 先量
`glv_stats` 在那個規模上的耗時與記憶體；太慢的話 `_others` 改成「抽樣 N 塊」，
而 N 要寫成一個看得見的特徵。

> `roi_cross`（Profile）與 `roi_template`（Template）這一輪不動。它們最後也該
> 收進同一張卡的 `method`（本來就是同一件事的四種做法），但它們各自帶著專屬
> 編輯器（`template` / `cell_rois` / `icon_choice`），搬進 `show_when` 是
> ParamForm 的工。**這是排程上的取捨，不是原則上的分界。**

> **`pattern_ref` 不回來。** golden cell 走區域這條路之後它多餘了，而使用者
> 2026-08-20 才說過那張卡「完全沒用，請直接拿掉」。

---

## 5. Phase C（未開始）：報表 bundle

| 步 | 做什麼 |
|---|---|
| **C0** | 把判定樹的走訪（`ui/tree_scene.py` 的 `display_tree` / `_path_of` / `flow_counts` / `layout_cells`）搬進 `core/pipeline/decide_tree.py` —— 報表要寫「每一類幾顆」，而 core 不得 import Qt（鐵則 1）。**不留第二份。** |
| **C1** | `overlay.write_jpeg(arr, path, quality=80)`，跟 `write_png` 同一個 atomic 寫法。實測：整張 overlay panel PNG 70 KB → JPEG q75 **12.6 KB** |
| **C2** | `output_html` 現在把整份 HTML inline 在 `run_batch` 裡。抽成 `core/export/html.py::build_report(...)`，兩張卡共用。⚠ **表格預設不放縮圖**：6000 個 `<tr>` 各一個 `<img>`，即使 lazy load，DOM 節點本身就會讓瀏覽器很鈍 —— 改成點一列換圖，同一個 `<img>` 重複使用 |
| **C3** | `OutputBundleStep`：`report.html`（純文字，約 3 MB）＋ `images/<id>.jpg` ＋ `defects.csv` ＋ `recipe.json`（沒有它，半年後沒人重現得出來）。參數 `folder` / `limit`（**0 = 全部，預設 0**）/ `jpeg_quality` / `montage` |
| **C4** | 讓第二趟吃快取。`output_image` 叫的是 `run_defect` 不是 `run_defect_cached`；`run_batch_steps` 沒有 `cache_dir` 參數；CLI 手上有 `args.cache` 但沒有傳。三個地方接起來之後，影像段命中，第二趟只跑算法段 |

實測的大小（一顆一張 overlay panel）：PNG 70 KB、JPEG q75 12.6 KB。
6000 顆嵌進 HTML 是 566 MB（PNG）／101 MB（JPEG base64）；純文字報表約 3 MB。

---

## 6. 驗收（Phase A 已做）

* `tests/test_cd_position.py`（10 條）—— 框落在團上、質心不是框的中心、
  **接了區域時座標是整張圖的**、輪廓與框對得起來、量不到不寫、線那一支不寫、
  一律吐不是選項、不配 nm 版、舊名不回來、兩個區域帶前綴。
* `tests/test_find_defect.py`（19 條）—— 挑最強的那一個、只有最強的有座標、
  極性寫下來、不看區域外、座標是整張圖的、**不長出具名區域**、找不到說原因、
  雜訊不算缺陷、疊圖直接讀那四個數字、預覽畫得出框、面積換算要平方。
* `tests/test_export_overlay.py` 多 4 條 —— CD 的框接得上、順序、少一格不算框、
  帶前綴的不撿。
* `tests/test_card_library_order.py`（5 條）—— 使用者點名的順序、註冊順序、
  **而且不是同義反覆**（Enhance 段字母序與註冊序是不同的答案）。

每一條回歸測試都驗過會紅（把 bug 放回去 → 它抓到）：
拿掉區域偏移、質心改用框算、量不到時寫 0、退路順序寫反、少一格也算框、
改用後綴比對、不排序、偷偷長出區域、面積少乘一次、順序改回字母序。
