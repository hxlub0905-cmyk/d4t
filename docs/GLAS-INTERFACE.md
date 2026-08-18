# ADEPT ← GLAS 介面契約

**這一份是 ADEPT 與 [GLAS](https://github.com/hxlub0905-cmyk/GLAS) 之間介面的唯一出處。**
兩邊的 repo 都連過來，不要各抄一份（抄第二份出來的那份一定會漂移）。

分工一句話：**layout 的解析與對位在 GLAS，ADEPT 只吃它匯出的東西。**
ADEPT 裡**不會**有 OASIS/GDS parser（使用者 2026-08-17 定調）。

> 這一份的後半段（§4）是**寫給 GLAS 那邊的需求**，可以直接複製過去。
> 每一條都寫了「為什麼 ADEPT 需要」與「怎麼驗這條做好了」。

---

## 1. GLAS 現在已經產出什麼（讀 GLAS repo 得到，不是提案）

來源：GLAS 的 `README.md` 匯出章節、`docs/plans/F15-glv-grayscale-roi-export.md`、
`glas/core/fine_align.py::render_label_image`、`glas/core/overlay_export.py`、
`glas/app/gds_align_tool.py::ALIGNMENT_COLUMNS`。

| 產出 | 內容 | ADEPT 要拿它做什麼 |
|---|---|---|
| **`<id>_label.png`** | uint8 label map：**0 = 背景、1..N = 第 N 個 POI 層**，**不 blur**（邊界精確，`gray[label==id]` 一個 boolean index 就取到） | **具名區域**（`ctx.rois`）—— ROI 定位的第三條路 |
| **`<id>_gray.png`** | 模擬 GLV 灰階圖：每層 polygon 用各自 `fg_glv` 畫在 `bg_glv` 上 + blur，SEM-like | 候選：當 **`ref` 影像流**（die-to-database 的合成參考圖）|
| **`<id>_label_view.png`** | label map 的人眼版（上色）| **ADEPT 不吃**，那是 QC 用的 |
| **manifest JSON** | 每張影像一列（含 `gray_png` / `label_png` 欄），外加一份 **`label_map = [{id, layer, fg_glv}, …]`** | `label_map` 是 **label id → 區域名字**的來源 |
| **alignment CSV / JSON** | schema `mmh-gds-alignment-v1`；欄位 `image_id`、`klarf_path`、`gds_path`、`poi_layer`、`coarse_dx/dy_nm`、`fine_dx/dy_nm`、`score`、`nm_per_px` | 對位分數（可信度 gate）；ADEPT **不必自己再對一次** |

## 2. join key 已經天然對上（兩邊同源，驗過）

| | 從哪來 |
|---|---|
| GLAS `SemImage.image_id` | KLARF 的 **`DEFECTID`** 欄（`glas/app/sem_loader.py::load_klarf`）；folder 模式退回檔名 stem |
| ADEPT `DefectItem.defect_id` | KLARF 的 **`DEFECTID`** 欄（`adept/core/ingest/dataset.py`）|

所以「一一對應」不需要發明新的 id：**`<DEFECTID>_label.png` 就是那顆 defect 的 mask。**
（folder 模式那條退路要能分辨，見 §4 的「建議 3」。）

## 3. ADEPT 這邊會怎麼接（下游零改動的理由）

ADEPT 的 ROI 定位法有一個**共同出口**：吐**具名區域**（`resolve_regions_out`，
0–1 正規化座標）。`roi_cross`（純規則）與 `roi_template`（Golden Cell）都走這個出口，
所以第三條路接上去之後，量測卡、`roi_mask`、overlay、region check **一行都不用改**
（見 [`ARCHITECTURE.md`](ARCHITECTURE.md) 的定位法契約）。

**分兩層**（2026-08-17 定調 —— Input 段是輸入來源的核心，所以**檔案 I/O 只在那裡**）：

```
ingest 層（配對 + 讀檔）      <DEFECTID>_label.png → 影像流 layout_label
  └ 同一條路也載 gray            <DEFECTID>_gray.png  → 影像流 layout_gray
       └ Region 卡（暫名 roi_from_mask）吃 layout_label 那條流
            + manifest 的 label_map → 每個 label id 一個具名區域
              （名字取 layer 名；座標一律正規化 0–1，因為 patch 尺寸會變）
```

為什麼配對規則要在 ingest 層而不是卡片裡：影像段快取的簽章與 `ProcessPool` 的
worker 都是照「`DefectItem` 帶著哪些影像來源」在算的。卡片自己偷偷讀檔的話，
**換了 mask 目錄而快取簽章看不見** —— 那就是 ADEPT 鐵則 9 擋的那類安靜錯誤。

三個已經定了的原則（不必再討論）：

- **一律正規化座標。** label 圖的尺寸不保證等於 patch，而寫死像素座標的 recipe
  換到 512² 就錯位（F7-4 的坑）。
- **這張卡不吐 mask 影像流。** 要 mask 流走既有的 `roi_mask` 卡 ——
  兩條平行的路會腐爛（F7-17 的教訓）。
- **對不上的那顆不殺整批**（ADEPT 鐵則 7）：`locate_ok=0`、退回整張圖、
  警告講一句可以照做的話。

---

## 3.4 **實測：manifest 已經是 v4，§4 的必要 1／建議 3 都做完了**（2026-08-18）

使用者在公司機上對一份真實匯出跑了 `tools/check_glas_export.py`（399 顆）。
結果推翻了下面 §4 的一部分 —— **GitHub 上的 GLAS 是 v3，廠內那份是 v4**：

```
schema   mmh-gds-overlay-v4
columns  image_id, raw_png, overlay_png, fine_dx_nm, fine_dy_nm, score, status,
         gray_png, label_png, id_source, page, width_px, height_px, nm_per_px,
         label_view_png
```

| §4 的項目 | 實際狀態 |
|---|---|
| 必要 1（多頁 TIFF 的 page 對應）| **欄位在了**（`page`）。RSEM 這批是空的 —— 那是對的 |
| 建議 3（`id_source` / `width_px` / `height_px`）| **全部做完了**，而且 `nm_per_px` 也逐張帶了 |

所以 ADEPT 不必再猜也不必再自己比：**`id_source` 直接說 `image_id` 是不是 KLARF
的 `DEFECTID`，`width_px`/`height_px` 直接說 label 圖該多大。**

那一批的其他事實（全部遮蔽過）：399 顆、`status` 全 `ok`、每顆五種 PNG 都在、
label 是 1000×1000 單通道 8-bit、3 層、`nm_per_px` 全批都是 1、
`image_id` 是不補零的數字（長度 1–6）、檔名不需要 `_safe_name` 改寫、沒有碰撞。

**唯一的 WARN 是 layer 名**：三個名字都含有 ADEPT 的區域名規則不接受的字元
（`L17/D0` 那種形式）。所以 `roi_from_mask` 一定要有一層「layer 名 → 區域名」的
改寫，而且**改寫規則要固定、要能查碰撞**（見 §3.6）。

## 3.6 一層 mask 拆成幾個矩形 —— 這是 Region-3 的設計輸入

`check_glas_export.py` 會把抽樣的那張 label 圖拆一次，印出每一層的
**pieces（連通元件）** 與 **rectangles（精確矩形分解）**。兩個數字問的是不同的事：

* **rectangles** = ADEPT 真的要存幾個框。既有的 Region 卡 `max_boxes` 預設 **64**
  —— 那是為「重複結構的幾份」設計的。GDS 這條路一層可能是**幾百到上千個**矩形
  （合成的 1000×1000 三層測起來 1014 / 988 / 25），64 會**安靜地砍掉大部分**。
  所以 `roi_from_mask` 要有自己的、大得多的上限。
* **pieces** = 「一份」有幾個。`<name>_center` / `<name>_others` 只有在「一份」
  講得通的時候才有意義 —— 而在非週期的 layout 上通常講不通（§3.3.13 已經據此
  決定這張卡只吐 `<name>`）。

兩者差很大的時候，意思是**那一層正被後面畫的層切碎**
（`render_label_image` 是 `lbl[m > 0] = label_id`）。

## 3.5 先驗，再寫程式：`tools/check_glas_export.py`（2026-08-18）

真實資料在**只能複製文字出來**的那台機器上（`AGENTS.md` §2），而卡片要接對，
猜不出來的東西全都是文字：欄位名、id 的格式、檔名慣例。猜錯的下場不是報錯，
是整批安靜對不上。

所以有一支健檢：

```
python tools/check_glas_export.py <匯出資料夾> [--klarf <KLARF>] [--images <SEM 影像資料夾>]
```

它**預設遮蔽**（layer 名 → `L1`、defect id → `IMG1`、路徑一律不印，只留結構、
格式與計數），所以整份報告可以直接貼出來；`--reveal` 那一份不要貼。
純標準函式庫（PNG 是自己讀的），不寫檔、不連網。

### 讀 GLAS 的程式碼讀出來的四件事（commit `bef5492`）

這四件都**不在**上面那張表裡，而且每一件錯了都不會報錯：

1. **檔名不是 `<DEFECTID>_label.png`，是 `<_safe_name(DEFECTID)>_label.png`。**
   `overlay_export._safe_name` 把非 `[A-Za-z0-9-_.]` 的字元換成底線。
   所以 ADEPT 配對時必須套**同一個轉換** —— 而且兩個不同的 id（`a/b`、`a:b`）
   會折到同一個檔名，後匯出的那顆**覆蓋**前一顆，manifest 裡兩列的 id 仍然不同。
2. **`label_map` 裡的層在某一顆上可能一個像素都沒有。**
   `fine_align.render_label_image` 是 `lbl[m > 0] = label_id`，**後面的層蓋掉
   前面的層**。名字還在 manifest 裡，而那一顆的區域是空的。
3. **`<id>_label_view.png` 是 3 通道的上色預覽**，指錯檔案的話 ADEPT 會把通道
   平均掉，label id 被混成一堆不存在的值。`_gray.png` 也不能拿來切區域：
   它有 Gaussian blur、背景是 `bg_glv`（預設 80）不是 0。
4. **`overlay_manifest.csv` 是用平台預設編碼寫的**（`open(..., "w")` 沒給
   `encoding`），非 ASCII 的 layer 名在 Windows 上會變成 cp950。
   **JSON 那一份是安全的**（`json.dump` 預設 `ensure_ascii=True`）——
   ADEPT 一律讀 `overlay_manifest.json`。

另外兩件是既有事實的確認：`label_map` **只有匯出時勾了 label 才會寫**；
alignment 檔的**檔名與資料夾都是使用者在另一個對話框選的**，所以它常常不在
PNG 那個資料夾裡（健檢靠 schema 字串找它，`--alignment` 可以直接指過去）。

## 4. 要請 GLAS 改的（**這一段可以直接複製過去**）

> 以下是 ADEPT（下游）對 GLAS 匯出的需求。ADEPT 不解析 layout，
> 只吃 `<id>_label.png` + `<id>_gray.png` + manifest；join key 是 KLARF `DEFECTID`。

> ⚠ **2026-08-18 實測更新（見 §3.4）**：廠內那份 GLAS 已經是 **v4**，
> 底下的「必要 1」與「建議 3」**都已經做掉了**（manifest 有 `page`、`id_source`、
> `width_px`、`height_px`、逐張 `nm_per_px`）。而 Region-3 定調成 **RSEM only**
> 之後，「必要 1」與「必要 2」本來就不再擋 ADEPT（一顆一個檔、只有一頁）。
> 下面這幾段留著是給**未來要做 patch 那條路**的人 —— 那時候它們會回來。

### 必要 1 — 多頁 TIFF 的 page 對應（不改的話，多頁資料整批對錯）

**現況**：`glas/app/sem_loader.py::load_klarf` 每顆 defect 只取
`defect["_image_filename"]`，`SemImage` **沒有 page 欄位**；讀圖是
`cv2.imread(path, IMREAD_GRAYSCALE)`（`fine_align.py:785`、`overlay_export.py:114/340`）。

**問題**：EBI patch 的資料形式是**一個多頁 TIFF 裝一整批 defect**（一顆佔連續幾頁）。
於是所有 defect 都指到同一個檔案，而 `cv2.imread` 只讀**第 0 頁** ——
GLAS 會拿同一張圖對位 N 次，產出的 label 也全部是同一顆的。

**要什麼**：`SemImage` 加 `page: Optional[int]`；`load_klarf` 依 KLARF 的 image
記錄算出每顆 defect 的頁；讀圖改成讀得到指定頁（`cv2.imreadmulti` 或 `tifffile`）。

**可以直接抄的實作**：ADEPT 已經做完這件事 ——
`adept/core/ingest/klarf_core.py::defect_image_map(n_pages)` 回每顆 defect 的頁清單，
`adept/core/ingest/tiff_index.py::n_pages/read_page` 是免解碼盤點 + 單頁讀取。
兩支都是純函式、不吃 Qt。

**怎麼驗**：一份多頁 TIFF 的 KLARF，載入後每顆 defect 的 `(file, page)` 互不相同；
兩顆不同的 defect 產出的 `_label.png` 不相同。

### 必要 2 — 對位要用哪一頁可以指定（我們的資料是 1 BSE + 4 SE）

**現況**：就算做完「必要 1」，還要決定「一顆 defect 的好幾頁裡，對位用哪一頁」。

**事實**（使用者 2026-08-17）：一顆 defect 的 TIFF 裡是 **1 張 BSE + 4 張 SE**
（四個象限的 detector 同時收），**BSE 固定在第 2 頁**，SE 的順序無所謂。

**要什麼**：`fine-align` 與 label/gray 匯出用的那一頁**可以設定**（預設可以是「第 2 頁」，
但要是個設定值不是寫死的常數）。理由：BSE 的結構訊號最清楚，template match 對它最穩；
而兩頁的舊資料（第 1 頁 test、第 2 頁 ref）用的是另一個慣例，寫死會撞。

**怎麼驗**：換一個「對位用第幾頁」的設定，同一顆 defect 的 `fine_dx/dy_nm` 會變；
設回去會逐項相同。

### 建議 3 — manifest 明講 id 是哪一種、每一列帶 shape

**為什麼**：ADEPT 要驗兩件事，而現在都驗不了 ——
(a) 那個 `image_id` 到底是 KLARF `DEFECTID` 還是檔名 stem（folder 模式）：
猜錯的話**整批對不上，而且是安靜的**；
(b) label 圖與 patch **是不是同一個網格**：尺寸不同就該拒絕或縮放並警告，
不能默默把框放到錯的地方。

**要什麼**：manifest（JSON）每一列加
`id_source: "klarf-defectid" | "filename-stem"`、`width_px`、`height_px`；
`nm_per_px` 已經有了（alignment 那份是全批一個值，如果會逐張不同請也搬進列裡）。

### 建議 4 — 沒產出的那幾顆也要在 manifest 留一列

**現況**：gray/label 吃 score threshold（`mask_should_export`），不達門檻**就不寫檔**。

**問題**：ADEPT 看到的只是「檔案不存在」，而它分不出三件不同的事 ——
GLAS 沒跑過這顆／跑了但分數低／跑了但沒有座標。這三種在 ADC 上的處置不一樣
（第二種是「對位不可信，這顆的區域別用」，第三種是資料問題）。

**要什麼**：每一顆都在 manifest 留一列，檔名欄位空白 + 帶 `status`（沿用
`fine_align_result_rows` 已經有的 `ok` / `low-score` / `no-coords` /
`missing-file` / `flat` / `not-run`）與 `score`。ADEPT 會把它變成
`locate_ok` / `align_score` 兩個特徵，讓使用者可以在 score 表達式裡拿它當 gate。

### 建議 5 — `label_map` 的層名要是穩定的

**為什麼**：ADEPT 拿 `label_map` 的 `layer` 當**具名區域的名字**，而那個名字會被
使用者寫進 score 表達式（`MG_glv_mean` 這種）。名字換了，recipe 就指不到。

**要什麼**：`layer` 名（含 Boolean 合成層的 `name`）在同一份 recipe 生命週期內穩定；
會變的話 manifest 的 schema 版本要 bump（GLAS 已經有 schema 版本的慣例）。
ADEPT 這邊會把「名字裡不能當變數用的字元」擋掉並講清楚（例如空白、減號）。

### 不要改的（ADEPT 就是吃這個形狀）

- `<id>_label.png` 是**整數 label map**（0 = 背景、1..N），**不 blur**。
  不要改成二值、不要改成用 GLV 值編碼區域 —— F15 §Q2/Q3 的理由 ADEPT 完全同意：
  blur 與抗鋸齒會破壞邊界，而 boolean index 是最快也最穩的讀法。
- `<id>_gray.png` 與 label **共用同一組幾何**（同網格）。這是 ADEPT 敢把 gray 當
  `ref` 流的前提。
- `label_view` 是 QC 用的，ADEPT 不吃 —— 不必為 ADEPT 維護它。

---

## 5. 還沒定的（等樣本）

- **檔案怎麼交到 ADEPT 手上**：一個資料夾（`<DEFECTID>_label.png` 平鋪）＋ manifest？
  還是每個 lot 一個 `glas_out/`？ADEPT 這邊會做成參數，等看到真的目錄長相再定預設。
- **`gray` 當 `ref` 流要不要正式支援**：它讓「沒有 ref page 的資料」也能做
  die-to-database 比較，價值高；但它是**合成**的圖，灰階分佈與真 SEM 不同，
  前面得接 Normalize 的 `match`（直方圖匹配）才比得起來。等 mask 那條路跑通再開。
