# F11 — Phase 2 功能補完

**狀態：計畫中（2026-08-17 開工）。** Phase 1 已於 2026-08-17 收斂（見
[`../ROADMAP.md`](../ROADMAP.md)），這一份是 Phase 2 的計畫書。

Phase 2 的定調來自使用者一句話：**「我想優先做好內部的每個功能。」**
產品化（手冊、範例庫、標注介面）在 2026-08-17 與這一個 phase 對調到後面 ——
理由跟 Phase 1 先做的理由是同一個：對著還會長的東西寫說明書，寫完就得重寫。

---

## 1. 先確認現況（讀 code 讀出來的，不是推論）

六項裡有三項的起點跟 ROADMAP 上那一行寫的不一樣，所以先把實際狀態記下來。

### 1.1 有演算法、沒有卡片 —— 而 help 叫使用者去跑那張不存在的卡

| 資產 | 誰在用 |
|---|---|
| `algo/blob.py`（`segment_defects` / `DefectROI`，155 行，vendored from Fusi³） | **沒有任何卡片**。只有 `algo/__init__` re-export 與 `tests/test_blob.py` |
| `algo/stats.py`（`group_outliers` / `cohens_d` / `attribute_separability`，85 行，vendored from PEAR） | **沒有任何卡片**。只有 `algo/__init__` re-export 與 `tests/test_stats.py` |

而缺這張卡是**看得見的**，有三個懸空的引用：

1. `cd_measure` 定不出框時的警告字面上寫 **“run Blob segment first”** ——
   registry 裡沒有 `blob_segment`（`ls adept/core/steps/` 十八張卡，沒有它）。
2. `cd_measure` 的 `output_prefix` 預設叫 `blob`，面積那一行讀 `ctx.meta["blobs"]`
   —— **沒有任何一張卡寫得出那個 key**（只有測試自己塞）。
3. `export/overlay.py::primary_blob_box` 有兩條路：`meta["blobs"]`，或退回特徵
   `blob_x/blob_y/blob_w/blob_h`。**兩條路現在都沒有生產者**，所以「主 blob 紅框」
   這個輸出功能在真的 pipeline 上永遠畫不出來。

這是 F10 那個形狀的親戚：**畫面（與 help、與輸出）說得出來的東西，引擎做不到。**

### 1.2 多通道：機制在，但 recipe 摸不到命名

`ingest/dataset.py::_channel_name` 已經支援任意頁數：第 j 頁 → `channel_order[j]`，
名單用完接 `img3`、`img4`…。但 **`channel_order` 只有 `tests/test_dataset.py` 傳過**
—— UI 與 CLI 都吃預設值 `("test", "ref")`。所以今天一顆五頁的 defect
（例如 1×BSE + 4×SE）會載成：

```
test, ref, img3, img4, img5
```

而 `load_patch` 的參數只有 `channels`（挑要載哪幾條，名字是 ingest 給的），
**recipe 與 Studio 沒有任何地方改得動那些名字**。融合卡要接的兩條線，現在叫
`ref` 與 `img4`。

### 1.3 GDS 的起點變了（使用者定調，見 §2）

ADEPT **不解析 layout**。GDS/OASIS 留在上游的
[GLAS](https://github.com/hxlub0905-cmyk/GLAS)，ADEPT 只吃它產出的
**mask image**，與 defect **一一對應**。這一項因此從「vendoring 一個 125 KB 的
OASIS streamer」變成「定一個 mask 進來的契約」—— 而且**可以用合成資料驗證**，
不必等真檔案（差別見 §4.1）。

### 1.4 產流卡的多來源，缺一個命名契約

F10 §6 刻意留的：`snr_map` 吃 `image_key`（單一來源）、吐 `out`（單一輸出名）。
多連一對它的意思是「一條流一張輸出圖」，而輸出流叫什麼還沒有規則。
**PCA Ref、BSE/SE 融合、會吐圖的 Region Stats 全部踩在同一條規則上**，
所以它要先定，不然三張卡會各發明一套。

### 1.5 ML 的料已經有了

per-defect feature vector 的 CSV 匯出在 M5 就做完了（CLI `--csv`、Export 精靈），
所以 ML Classify 不欠上游，欠的是「模型放哪、誰訓練」那個決定（§2）。

### 1.6 順手：兩處文件漂移（1 MB 上限）

`AGENTS.md` §2 已於 2026-08-17 定調「包的大小不是限制」（使用者直接複製 raw），
而另外兩處還在講舊事，其中一處會讓公司機**照著做卻搬不進去**：

- `docs/FAB-VALIDATION.md` §部署 叫人複製 `bundle/ADEPT_part1of6.py … part6of6.py`
  —— **那些檔案不存在**，`bundle/` 現在只有單檔 `ADEPT_bundle.py`（997 KB）。
- `SESSION_LOG.md` 開頭那句「離 1 MB 顯示上限只剩不到一成」。

一個主題只有一個家（`CLAUDE.md` §0），這兩處連過去 `AGENTS.md` 就好。

---

## 2. 使用者定調（2026-08-17）

| 題 | 答 |
|---|---|
| 演算法要不要照抄 vendored 的 | **不要。「演算法請幫我移除，我要重新來，基本上不用照抄就有 vendor 的算法（我基本會想要優化改良）」** |
| ML Classify | **排 Phase 2 後半**（相依那題到時候再定）|
| GDS ROI | **ADEPT 只吃上游 GLAS 的 mask image，與 defect 一一對應；樣本之後提供** |
| 多通道 | 使用者反問「是指一張 TIFF 裡含多張圖（1×BSE + 4×SE、同時由不同 detector 收）嗎」→ 是。回答與反問見 §6.1 |

### 2.1 「演算法請幫我移除」的範圍（**動手前要確認**）

我讀成 **A**，但這件事刪錯了要重來，所以寫在這裡等確認：

- **A（我的讀法）**：把**沒有卡片在用的** vendored 演算法移除 —— `algo/blob.py`、
  `algo/stats.py`，連同 `algo/__init__` 的 re-export、`tests/test_blob.py`、
  `tests/test_stats.py`。兩張卡（blob 分割、離群）的演算法**重新寫**，
  照現在的需求設計，不照抄。
- **B（更大的範圍）**：連 18 張卡正在用的那些也要重寫（`glv` / `snr` / `align` /
  `normalize` / `enhance` / `grid` / `template` / `period` / `subpixel` /
  `histmatch` / `profile` / `quality` / `curve` / `roi`）。
  這一條的代價要先知道：**黃金值（三組 22 顆）會全部改變**，Phase 1 剛立起來的
  「跟改動前逐項相同」那個驗收基準就沒有了，1033 條核心測試裡凡是斷言數值的都要
  重新定錨。做得到，但那是一輪自己的工作，不是 Phase 2 的副作用。

兩個模組的 docstring 都刻意寫著「別把它當死碼刪掉」（blob.py 甚至解釋了卡片被
拿掉但演算法留著的理由）。移除的時候那段理由要跟著搬進這一份計畫書 ——
**留著的理由本身是資產**，不能跟著檔案一起消失。

---

## 3. 排序與依賴

```
F11-0  文件漂移（§1.6）………………………… 順手，不依賴任何東西
F11-1  mask 進來（GLAS 一一對應）………… 契約先定；合成資料可全程驗證
F11-2  產流卡的輸出命名契約 + snr_map 多來源
          └─ F11-5 融合 / PCA 全部踩在它上面
F11-3  blob 分割 + 離群（重寫）…………… 順手解掉 §1.1 的三個懸空引用
F11-4  Region Stats / FFT
F11-5  多通道 → PCA Ref / BSE·SE 融合……（要 F11-2，且要先答 §6.1）
F11-6  ML Classify ………………………………… Phase 2 後半（使用者定調）
```

排這個順序的理由，只有一條是「大小」，其餘都是依賴：

- **F11-1 先做**是因為它現在是六項裡**唯一被外部進度卡住**的一項（樣本之後提供），
  而「契約」這一半不必等樣本 —— 先定契約 + 合成 mask，樣本來了只換認檔規則。
- **F11-2 先於 F11-4/F11-5** 是因為那條命名規則是它們共用的。
- **F11-3 排在中間**是因為它同時是「重寫演算法」這件事的第一個實例 ——
  拿一張輸出契約已經被兩個消費者（overlay、export_dialog）定好的卡來試，
  比拿一張全新的卡來試安全。

---

## 4. 各項規格草案

### 4.1 F11-1 — mask 進來：GLAS 的 mask image → 具名區域

**要解什麼。** ROI 定位的第三條路。前兩條（`roi_cross` 純規則、`roi_template`
Golden Cell）都只看 patch 自己，所以非週期 layout 定不出來。第三條路的資訊來自
layout，而 layout 的解析**不在 ADEPT** —— 上游 GLAS 產 mask，ADEPT 吃 mask。

**出口契約（已經留好，下游零改動）。** `resolve_regions_out` 吐**具名區域**
（0–1 正規化座標），跟 `roi_cross` / `roi_template` 逐字相同的出口。
所以量測卡、`roi_mask`、overlay、region check **一行都不用改**
（見 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) 的定位法契約）。

**兩個要決定的（§6.2 問使用者，但先寫傾向）：**

1. **mask 的語意**：二值（一個區域）還是 **label map**（`gray[label==k]`，
   每個 k 一個具名區域）？傾向 label map —— 它一次帶得動多個區域，而且**那正是
   GLAS 既有的 ROI label map 契約**（`docs/HANDOVER.md` 記的 GLAS 資產之一）；
   二值是它 k=1 的特例，兩者不必做成兩張卡。
2. **怎麼跟 defect 一一對應**：檔名＝defect id？一顆一個檔案的資料夾？KLARF row？
   這一項等樣本，但**參數化**（一個 `pairing` 下拉），不要寫死。

**已經決定的三件事（不必再問）：**

- **一律正規化座標。** mask 的尺寸不保證等於 patch（F7-4 那個坑：寫死像素座標的
  recipe 換到 512² 就錯位）。
- **這張卡不吐 mask 影像流。** 要 mask 流的話走既有的 `roi_mask` 卡
  —— `ARCHITECTURE.md` 明講過「兩條平行的路會腐爛」（F7-17 的教訓）。
- **對不上的那顆不殺整批**（鐵則 7）：`locate_ok=0`、退回整張圖、`ctx.warn` 講一句
  可以照做的話。

**家用機怎麼驗（AGENTS.md §1 的硬要求）：** `tools/make_sample.py` 加一個開關
（或另一支 `make_sample_masks.py`）產「與合成 lot 一一對應」的合成 label map。
新功能如果只能用真實資料驗證，它在家用機上就等於不能驗證。

**驗收：** 一份 recipe 吃合成 mask → 具名區域 → `glv_stats` 吐帶前綴的特徵；
故意抽掉一顆的 mask，那一顆 `locate_ok=0` 而整批照跑完；
換 patch 尺寸（128² / 512²）框的相對位置逐項相同。

### 4.2 F11-2 — 產流卡的輸出命名契約（+ `snr_map` 多來源）

**規則（提案，照 F10-3 量測卡的先例）：**

| 接幾條線 | 輸出流叫什麼 |
|---|---|
| 一條 | **就是 `out` 的值，逐字不變** |
| N 條 | `<流名>_<out>`（例：`test_snr_map`、`diff_snr_map`）|

「一條的時候逐字不變」不是為了好看，是**黃金值不動**的前提：F10-3 的量測卡就是
這樣做的（兩條流才加流名前綴，只接一條時特徵名逐字相同），兩邊用同一條規則，
使用者只要學一次。

**要一起改的三個地方**（不改就是 F9 那六個「跑得完、有數字、而且是錯的」的第七個）：

- `resolve_writes` 要照上表算，畫布才畫得出正確數量的輸出埠（F10 的不變量）；
- **快取簽章要看得見這件事**（鐵則 9 第三條）；
- 那張卡的 inspector 面板（`ui/inspectors.py` 依 `Step.key` 註冊）要能顯示 N 張圖。

### 4.3 F11-3 — blob 分割 + 離群（**重寫**，不照抄）

**輸出契約已經被兩個消費者定死了**，重寫可以改演算法但**不能改 key**：

- `ctx.meta["blobs"]`：dict 清單，`export/overlay.py::_blob_box` 認
  `x/y/w/h`、`_blob_rank` 認 `snr_value`（沒有就用 `area`）；`ui/export_dialog.py`
  也讀同一個 key。
- 或者特徵 `blob_x/blob_y/blob_w/blob_h`（overlay 的第二條路）。
- `cd_measure` 的 `roi="blob"` 要接得上（它現在的警告就是指這張卡）。

**重寫的時候要改良什麼**（等使用者補充，先列我讀出來的候選）：
門檻怎麼定（現在是 SNR map 灰階門檻）、要不要吃 `roi_mask` 限定範圍、
主 blob 的挑法（現在是 SNR 最強，但「離報點最近」在 ADC 上常常更對）。

**離群那張卡**：Tukey IQR 是**跨顆**的統計，而 `run_defect` 是一顆一顆跑的
—— 所以它不是一張普通的量測卡，得決定算在哪一層（批次後的 rescore？
`store/` 已經有 rescore 的路）。這一點寫在這裡，做到再定。

### 4.4 F11-4 — Region Stats / FFT

F0 從 v1 移出的兩張。分區統計（把一個具名區域切格子、每格出統計）＋去趨勢
＋週期頻譜。**FFT 那一半不必從零開始**：`algo/period.py` 的 rFFT 與相位搜尋
已經在（`CLAUDE.md` §5 明講過那個模組不要刪，因為它是 pattern-frame ROI 的唯一
工具）。會吐圖的話踩 F11-2 的命名規則。

### 4.5 F11-5 — 多通道 → PCA Ref / BSE·SE 融合

依賴：**先答 §6.1**（真實資料到底是幾頁、哪一頁是什麼），再決定 `load_patch`
要怎麼讓 recipe 命名那些頁（§1.2 的缺口）。兩張融合卡本身都是「N 條流 → 一條新
的流」，所以它們的輸出名照 F11-2。

順序上這一項排在最後，不是因為不重要，是因為**它的前提是廠內事實**，而那件事
現在只有一個「頁→channel」的既有機制與一個未確認的假設。

### 4.6 F11-6 — ML Classify（Phase 2 後半）

使用者定調排後半。到時候要定的是相依：自寫 numpy-only 小分類器（模型 base64
凍進 recipe，跟 `roi_template` 的 Golden Cell 同一個做法）／加 scikit-learn
（離線 wheels 要多帶幾十 MB 進公司機）／只做推論吃外部訓練好的模型。
上游不欠料（§1.5）。

---

## 5. 整輪的驗收（每一項自己的驗收在 §4）

Phase 1 立起來的三層安全網**全部自動套用到新卡**，所以這一輪不必為它們補工：

| 層 | 對 Phase 2 的意思 |
|---|---|
| 黃金值（`tools/freeze_golden.py --check`） | 新增卡片不得改變既有三組 22 顆的任何一項。**除了 §2.1 選 B**，那要重新定錨 |
| 六條卡片不變量（`tests/test_card_invariants.py`） | 對 registry 裡每一張卡自動跑 —— 新卡一註冊就被驗 |
| F10 的畫布不變量（`tests/test_ui_f10_canvas_reality.py`，20 條） | 同上：新卡自動被驗「畫布不說謊」 |
| 兩支稽核腳本（11 項） | 每一項做完跑一次 |

---

## 6. 待使用者定調

### 6.1 多通道 —— 回答你的問題，並反問一句

**是，就是你說的那個。**「多通道」在這裡指**一顆 defect 的 TIFF 裡含好幾頁**，
例如 1 張 BSE + 4 張 SE（四個象限的 detector 同時收）。ADEPT 的機制已經支援
任意頁數（§1.2），兩個缺口是：

- 頁的**名字**只能在 ingest 層決定，recipe 與 Studio 摸不到（現在會叫
  `test, ref, img3, img4, img5`）；
- 目前唯一確認過的事實是「兩頁的 patch：第一張 test、第二張 ref」
  （`docs/FAB-VALIDATION.md` 假設 #1，2026-07-30 確認）。

**要問你的是：你手上的資料實際是幾頁、順序是什麼？**
（例如「5 頁：第 1 頁 BSE，第 2–5 頁 SE 左上/右上/左下/右下」。）
不確定的話我可以先寫一支探測（`fab_probe/` 的既有路子：stdlib-only 單檔、
純文字輸出、預設遮蔽識別碼），你在公司機跑一次把結果貼回來 ——
那支腳本不需要搬整個 repo。

### 6.2 mask 的兩個規格（§4.1）

樣本還沒到，但這兩個先知道傾向會少走一輪：
**(a)** label map（每個 k 一個具名區域）還是二值？
**(b)** mask 檔怎麼跟 defect 對上（檔名＝defect id／一顆一個資料夾／KLARF row）？

### 6.3 「演算法請幫我移除」的範圍 —— A 還是 B（§2.1）

A = 只移除沒有卡片在用的那兩個模組並重寫那兩張卡；
B = 連 18 張卡在用的一起重寫（**黃金值會全部改變**，要重新定錨）。
**確認之前我不動任何演算法檔案。**
