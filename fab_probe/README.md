# fab_probe —— 廠內格式探測腳本

給**廠內工程師**與**資料攜出審核人員**看的說明。

ADEPT 全程用合成資料開發（真實資料不能出廠），因此有三個假設必須拿真實檔案確認。
這個資料夾裡的三支腳本就是為此而生：**它們只讀檔、只印文字報告，不修改任何檔案、
不連網路、不產生新檔**（除非你自己用 `>` 把輸出導到檔案）。

| 腳本 | 回答哪個假設 | 會不會讀像素 |
|---|---|---|
| `probe_klarf.py` | **假設 #3**：KLARF 的影像佈局變體有幾種 —— **唯一還沒結掉的那個** | 否 |
| `probe_tiff.py`  | 交叉確認 **假設 #1**：每顆 defect 是不是兩頁（test/ref） | 否（只讀 IFD 標籤） |
| `probe_stats.py` | 影像段參數怎麼設；奇偶頁亮度差是 **假設 #1** 的旁證 | **是（唯一會讀像素的一支）** |

三個假設的原文在 `CLAUDE.md` §8。**2026-07-30 結掉了前兩個**，只剩第 3 個要確認：

1. ~~EBI patch 的 page→channel 對應~~ —— ✅ **已確認**：第 1 張 = test、第 2 張 = ref。
   `probe_tiff.py` / `probe_stats.py` 現在是**交叉確認**，不是前提。
2. ~~`nm_per_px` 從哪裡來~~ —— ✅ **用設計繞開**：量測全程用 pixel，nm 換算搬到
   輸出的那一刻、由使用者自己填 nm/px。腳本順手找到的話仍會印出來（有值總是好的），
   但**沒有它不擋任何事**。
3. **KLARF 影像佈局變體**（目前處理了四種，實際站點可能還有新花樣）——
   **這個還在，`probe_klarf.py` 是為它跑的。**

---

## 1. 執行前你需要知道的事

* **單檔、純標準函式庫。** 每支腳本都是一個 `.py`，不需要 `pip install` 任何東西，
  也不會 import ADEPT。有 Python 就能跑（3.6 以上；3.8 以上最保險）。
* **不需要網路、不需要管理員權限。**
* **只讀不寫。** 腳本不會碰你的原始檔（以唯讀模式開檔）。
* **輸出是純文字。** 直接看得懂，也可以用 `>` 存成 `.txt` 再貼給對方。

## 2. 怎麼跑（Windows）

把 `fab_probe` 資料夾（三個 `.py` + 這份 README）複製到廠內機器，開啟「命令提示字元」：

```bat
cd C:\adept\fab_probe

REM 1) KLARF 結構（最先跑這支）
python probe_klarf.py C:\data\LOT1234.001 > klarf_report.txt

REM 2) TIFF 結構 + 與 KLARF 的成對檢查
python probe_tiff.py C:\data\LOT1234.tif --with-klarf C:\data\LOT1234.001 > tiff_report.txt

REM 3) 灰階統計（會讀像素，請先確認可否攜出）
python probe_stats.py C:\data\LOT1234.tif --pages 20 --bins 16 > stats_report.txt
```

路徑有空白時記得加引號：`python probe_klarf.py "C:\my data\LOT1234.001"`。
沒有 `python` 指令時，試 `py -3 probe_klarf.py ...`。

Linux / macOS 一樣：`python3 probe_klarf.py /data/LOT1234.001 > klarf_report.txt`。

### 常用選項

| 選項 | 適用 | 說明 |
|---|---|---|
| `--include-ids` | klarf / tiff | 連 LotID、WaferID、檔名等識別碼一起輸出（**預設遮蔽**）。只有在你確認可攜出時才加。 |
| `--rows N` | klarf | 抽樣列數上限（型別推斷、列尾樣式、異常列索引；預設 20）。 |
| `--pages N` | tiff | 細看前 N 頁（另外自動加看中段與最後兩頁；預設 8）。 |
| `--with-klarf FILE` | tiff | 同時給對應的 KLARF，做「頁數 vs defect 數」的成對檢查（假設 #1 的重點）。 |
| `--pages N` / `--bins N` | stats | 抽樣頁數（預設 20）／直方圖格數（預設 16）。 |
| `--max-pixels N` | stats | 每頁最多取樣幾個像素（預設 200 萬；大圖會自動依列抽樣，抽樣率會印出來）。 |

### 回傳碼

| 碼 | 意思 |
|---|---|
| 0 | 正常完成 |
| 2 | 檔案找不到／不是這支腳本吃的格式（會印一行白話說明） |
| 3 | 非預期錯誤（會印錯誤類型，請把那一行回報） |

腳本不會丟出 Python traceback；看到的一定是中文說明。

---

## 3. 攜出審核用：到底有什麼東西會離開這台機器？

報告本身也把這一節印在最前面，方便直接給審核人員看。

### 一律**不會**出現在報告裡

* 任何 defect 的座標（`XREL` / `YREL` / `XINDEX` / `YINDEX`）—— 連最大最小值都不印
* 任何 defect 資料列的原始內容 —— 只印「token 的型別樣式」，例如 `d d f d { s s d s }`
  （`d`=整數、`f`=浮點、`s`=字串、`w`=文字、`{}`=括號；**沒有任何數值或文字內容**）
* 任何像素值 —— `probe_klarf` / `probe_tiff` 連一個 byte 的影像資料都沒有解碼
* 影像縮圖、任何可還原影像的資料
* 檔名原文（只印副檔名與字元數，例如 `<redacted, 11 chars>.001`）
* class 類別名稱（只印「有幾類」）

### 預設**遮蔽**（加 `--include-ids` 才會出現）

* `LotID`、`WaferID`、`DeviceID`、`StepID`、`SetupID`、`ScribeID`、`InspectionStationID`、
  `RecipeID`、`FabID`、`TiffFileName` 等識別碼欄位的**值**
  —— 預設印成 `LotID: <redacted, 9 chars>`（保留字元數，因為欄位長度本身是格式資訊）
* TIFF 的 `ImageDescription` / `Software` / `Make` / `Model` 裡「像識別碼的字」
  —— 規則：字母數字混合且長度 ≥ 6 的字換成 `<id:長度>`；
  **純數字（含 3.25、1.2e-3、25nm 這種帶單位的）一律保留**（`nm_per_px` 要靠它）；
  純字母的字（如 `PixelSize`）保留。整段截斷到 160 字元。

### **會**出現在報告裡（這些就是我們要的東西）

* 欄位**名稱**（header 欄位名、defect 欄位名與宣告型別）—— 這是格式，不是資料
* 各種計數與統計：列數、欄位數、頁數、每顆 defect 的影像張數分布、列長分布、
  異常列的**索引編號**（不是內容）
* 結構性欄位的值：`FileVersion`、`SampleType`、`SampleSize`、`DiePitch`、`DieOrigin`、
  `TiffSpec`、時間戳 —— 判讀格式必需
* **`nm_per_px` 候選欄位的值**（這是刻意的例外，也正是探測目的）：
  名稱含 PIXEL / SCALE / RESOLUT / MAG / NM / UM / SIZE / PITCH / FOV 之類的欄位，
  會印出它的值或值域（defect 欄位只印 min/max 與相異值個數）。
  若該欄位名同時像識別碼（例如 `RecipeID`），仍然遮蔽。
* TIFF 結構標籤：尺寸、位元深度、通道數、壓縮方式、strip/tile 排列、解析度標籤
* `probe_stats.py` 額外輸出：灰階直方圖、min/max/平均/標準差、每頁平均與標準差、
  以及**一張 4×4 的區塊平均**（整張圖只切成 16 格取平均；粗到無法辨識任何圖樣，
  但看得出視野是否有大範圍明暗不均）

### 特別提醒：`probe_stats.py`

三支裡只有它會**實際讀取像素值**。它輸出的都是彙總統計（不可能還原影像），
但既然碰了像素，**請先確認貴公司的資料攜出規範允許，再把報告貼出廠外**。
報告最上方也印了同樣的警語。

---

## 4. 報告怎麼讀（每支的重點段落）

### `probe_klarf.py`

| 段 | 內容 |
|---|---|
| 1 | 檔案基本資訊（大小、換行、編碼） |
| 2 | 版本判定 1.2 / 1.8，以及**是哪一條啟發式命中的** |
| 3 | header 欄位名清單，並標出哪些是 ADEPT 目前**沒看過**的欄位（`NEW`） |
| 4 | defect 欄位清單（宣告型別 + 由資料推斷的型別）、列數 |
| **5** | **影像佈局變體判定 + 證據**（假設 #3；最重要） |
| 6 | 列長異常統計（只有數量與索引） |
| **7** | **`nm_per_px` 獵捕**（假設 #2） |
| 尾 | 「請回報這一段」：一段 JSON 摘要，貼回來就好 |

第 5 段目前認得四種變體：

* **變體 A `images18`**：有 `IMAGECOUNT` 欄，影像欄是 `Images N { … }` 子區塊
* **變體 B `declared`**：有 `IMAGELIST` 欄，且 `TiffSpec` 宣告了每張圖佔幾個 token
* **變體 C `inferred`**：以上都沒有，從資料推斷每張圖佔幾個 token（報告會印投票明細）
* **變體 D `imagefile`**：沒有 `IMAGECOUNT` 欄，但列中有 `Image/Images N { "檔名" … }`
  子區塊（Review SEM 常見）

若印出「**四種已知變體都不成立**」，那就是我們要找的新花樣 ——
請把第 5 段（含列尾樣式）整段回報，我們會做成回歸測試 fixture。

### `probe_tiff.py`

重點在**第 5 段**（要加 `--with-klarf` 才有）：

* 檢查 A：TIFF 頁數 == 2 × defect 數？
* 檢查 B：TIFF 頁數 == `IMAGECOUNT` 總和？
* 觀察到的排列：`pairs`（每顆 2 張）/ `single` / `triples` / `mixed`
* KLARF 宣告的 page 對應解不解得開（`imagelist` 直接是頁碼，還是只能 `sequential` 連續配頁）、
  id 是 0-based 還是 1-based

注意：檢查 A 通過只證明「**成對**」，**沒有證明哪一張是 test**。
先後順序請看第 4 段（頁面標籤週期性）與 `probe_stats.py` 的奇偶頁亮度比較。

第 3 段的 `ImageDescription` / `Software` / 解析度標籤是假設 #2 的主要線索：
若出現 `PixelSize=3.2nm` 這類字樣，那就是 `nm_per_px` 的來源。

### `probe_stats.py`

* 第 2 段：每頁的 min/max/平均/標準差
* 第 3 段：合計灰階直方圖（含「貼邊像素」比例 → 判斷是否飽和截斷）
* 第 4 段：**奇偶頁亮度比較** —— 有系統性差異就是「兩頁來源不同（test/ref）」的旁證
* 第 5 段：4×4 區塊平均 ASCII 圖 —— 看視野是否有大範圍照明不均

遇到解不開的壓縮（LZW、JPEG、deflate）或 tile 排列時，**會清楚說明並跳過該頁**，
不會中斷；那一行的說明本身就是要回報的重要資訊
（代表廠內 TIFF 用了 ADEPT 沒預期的編碼方式）。

---

## 5. 要回報什麼

每份報告最後都有一段：

```
==========================================================================
請回報這一段（機器可讀摘要…）
==========================================================================
>>>JSON_BEGIN
{ ... }
>>>JSON_END
```

**最少**把這一段（含 `>>>JSON_BEGIN` / `>>>JSON_END` 兩行）貼回來。
它不含識別碼、不含座標、不含像素，是三份報告裡最安全的部分。

如果報告裡出現下列任何一句，請**連同它上下那一整段**一起回報：

* 「四種已知變體都不成立」（假設 #3 的新變體）
* 「與 test/ref 成對假設不符」（這一份檔案不照已確認的 test/ref 慣例走 ——
  例如一顆出三頁以上，那要換 `channel_order`）
* 「本腳本只解得開 未壓縮 與 PackBits」（TIFF 編碼方式沒預期到）
* 「頁面規格不一致」
* 「klarf_core 未涵蓋（NEW）」後面列出的欄位名
* 第 7 段裡任何看起來真的帶 nm / pixel 的欄位（假設 #2 —— **不再擋事**，
  但找得到的話 Export 那格 nm/px 就有預設值可帶，值得回報）

---

## 6. 給維護者的話（不是給廠內使用者）

* 三支腳本**刻意不 import `adept`**，而是把 `adept/core/ingest/klarf_core.py` 與
  `adept/core/ingest/tiff_index.py` 的判定邏輯**重寫一份**（純標準函式庫）。
  這是為了讓廠內只需要複製單一檔案，代價是**兩邊要同步維護**：
  改動 `detect_version` / `image_layout` 一族 / `read_tiff_pages` 時，
  這裡也要跟著改。每支腳本的檔頭都列了它鏡射了哪些函式。
* `tests/test_fab_probe.py` 會用 `tools/make_sample.py` 與 `tools/make_sample_rsem.py`
  產生資料，再以 subprocess 跑這三支腳本並檢查輸出（含遮蔽政策與「不得 import
  numpy/cv2/tifffile/adept」的原始碼掃描）。
