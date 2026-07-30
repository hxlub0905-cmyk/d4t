# ADEPT 開發計畫（工作代號，名稱待定）

> 一個 **flexible、多步驟、任何 Inspection 站點都適用**的 ADC 工具：
> 讀 EBI patch（test+ref）或 RSEM 單張影像 + 對應 KLARF，
> 用「步驟卡片組 pipeline」把腦中想法變成算法，對每顆 defect 算分、
> 調參看整批分佈、寫回 KLARF。
> 定位：PADC / RADC 的低門檻繼承者 —— **站點差異封裝進 recipe，不封裝進程式碼**。
> 推廣目標：同事學會操作後，不寫 code 也能把想法轉成算法。

版本：v1.0 · 2026-07-27 · 依據六專案盤點 + 三輪需求訪談定案

---

## 1. 已確認的需求與決策（訪談結論）

| 決策點 | 結論 |
|---|---|
| 使用對象 | **推廣給部門同事**（不寫 code）→ UX 引導、防呆預設值、教學文件是一級需求，不是附屬品 |
| 形態 | 桌面 GUI（PySide6），core/ui 嚴格分離；**CLI 附帶**（`adept run <recipe> <klarf>` 供排程/腳本） |
| 組裝方式 | 視覺化 pipeline 編輯器（step 卡片 + 自動生成的參數表單），底層 recipe JSON |
| 輸入 | 兩者都吃：**EBI patch = test+ref 兩兩配對、8-bit、multi-page TIFF（格式參照 KLIP）**；RSEM = 單張/defect。ingest 自動判別；16-bit 防禦性支援 |
| 輸出 | ① 無損寫回 KLARF（CLASSNUMBER、ROUGHBIN/FINEBIN、DSIZE）② **score + new class 寫入指定欄位並 gen 新 KLARF**（含 Top-N 篩選）③ CSV/Excel 報表 + overlay ④ per-defect feature vector 匯出（為未來 ML 備料） |
| Pipeline 結構 | **core 第一版即 DAG**（直線是特例）；UI v1 = 直線鏈 + 輸入型別分流，自由 DAG 畫布 v2 |
| Gallery | v1 就要：縮圖網格 + score/feature 排序 + 直方圖點 bar 篩選；ground-truth 標注 v2 |
| CD | 「CD Measure」是 pipeline 中的一張特徵卡，輸出進 score 表達式、可回寫 DSIZE |
| Step 分類 | **兩大類：影像（Image，影像優化）與算法（Algo，量化）**，由 ADC 判定段串起 —— defect 分數就是這兩件事決定的，UI 分類必須一眼看懂 |
| v1 精簡 | PCA Ref、Region Stats/FFT 兩張卡移出 v1（列 backlog，之後要加隨時加回） |
| ML | v1 純 rule-based；**feature 匯出先做**（CSV per defect），「ML Classify」卡留 v2 擴充位 |
| KPI | 三個都要：自動分類準確度、壓 nuisance rate、**review efficiency（分數排名高的都要是真 defect）** |
| 資料量級 | 千級常態、偶爾上萬 → **設計目標 10k defect 流暢**（批次 < 2 min、gallery 虛擬捲動） |
| 程式碼重用 | **Vendoring**：從六專案 copy 進新 repo 改名空間，新工具完全獨立、不動現有專案 |
| 開發資料 | 實際資料**不能出廠**；開發用合成資料 + KLIP 產的測試 KLARF，配套**廠內探測腳本**（純文字輸出、可複製貼上回報格式變體）§10 |
| 廠內環境 | 可裝 Python（離線 wheels 建 venv）；單 exe 打包為選配（KLIP build.bat 模式備援） |
| Recipe 分享 | 單一 JSON 檔互傳即可；工具內建匯入/匯出 + 版本/作者欄位 |
| 首發實戰案例 | **EBI patch 算分**：證明「想法 → 算法」這條路真的走得通（M3 驗收目標） |

---

## 2. 架構總覽

```
adept/
├── core/                    # 純運算，零 Qt import（headless 可測）
│   ├── ingest/              # KLARF + 影像載入、dataset 模型
│   │   ├── klarf_core.py    # ← KLIP（整檔搬，補 per-defect ImageFileName 解析）
│   │   ├── tiff_index.py    # ← KLIP klarf_tif_probe.read_tiff_pages + tifffile 像素讀取
│   │   └── dataset.py       # Dataset / DefectItem（GLAS sem_loader 一般化）
│   ├── pipeline/
│   │   ├── step.py          # Step 介面 + ParamSpec + registry
│   │   ├── recipe.py        # Recipe(DAG) 模型、JSON serde、lint 式驗證
│   │   ├── context.py       # Context 資料模型
│   │   ├── engine.py        # 單顆執行 + 批次 ProcessPool + 中間結果快取（← MMH）
│   │   └── expression.py    # score 表達式引擎（← GLAS gds_boolean AST 改造）
│   ├── steps/               # step library（見 §5，每類一檔）
│   ├── store/               # recipe 持久化（← MMH recipe_registry）、批次歷史 SQLite（← MMH batch_run_store）
│   └── export/              # KLARF 寫回/新檔、CSV/Excel、feature vector、overlay PNG
├── ui/                      # PySide6 殼
│   ├── studio/              # Recipe Studio：library｜pipeline｜單顆預覽｜直方圖
│   ├── gallery/             # 縮圖網格 + 排序 + 直方圖聯動（虛擬捲動）
│   ├── onboarding/          # 首啟導覽 + 內建範例 recipe（← Fusi³ welcome_tutorial 模式）
│   └── theme.py             # 設計 token（沿用 GLAS/CPE 主題系統）
├── fab_probe/               # 廠內探測腳本（獨立、stdlib-only、文字輸出）§10
├── tests/                   # 合成影像測試（照 CPE test_synthetic 模式）+ KLARF fixtures
└── tools/                   # CLI 進入點、synthetic data generator
```

六專案共同驗證過的慣例，直接沿用：core 不得 import Qt；批次 worker 為 top-level
picklable 純函數、recipe 以 dict 序列化進子行程；檔案寫入一律 atomic（`.tmp`+`os.replace`）；
KLARF 寫回走 KLIP 無損 span-splice。

---

## 3. 資料模型

### 3.1 Dataset / DefectItem（統一兩種輸入）

```python
@dataclass
class DefectItem:
    defect_id: str
    die: tuple[int, int]              # XINDEX, YINDEX
    xrel_nm: float; yrel_nm: float
    images: dict[str, ImageRef]       # ebi_patch: {"test","ref"}；rsem: {"single"}
    nm_per_px: float | None           # KLARF pixel size / TIFF tag / calibration profile
    klarf_row: int                    # 寫回用列索引
    tags: dict                        # class, roughbin, dsize… 原始欄位

@dataclass
class Dataset:
    kind: Literal["ebi_patch", "rsem", "folder"]
    klarf: KlarfDoc | None            # 活的 KLIP 物件，供無損寫回
    items: list[DefectItem]
```

判別：KLARF + multi-page TIFF 且 `defect_image_map` 解析成功 → `ebi_patch`
（page 依 TiffSpec/推斷對應 test/ref）；defect 各帶 ImageFileName → `rsem`；
純資料夾 → `folder`（演算法開發用）。**diff 不假設存在，一律由 Subtract 卡現算。**

### 3.2 Context（步驟間的執行狀態）

```python
class Context:
    images:   dict[str, np.ndarray]   # 命名影像流："test"、"ref_aligned"、"diff"、"snr_map"…
    rois:     MultiROISet | None      # ← Fusi³（正規化座標，可隨對位 shifted()）
    labels:   np.ndarray | None       # 整數 ROI label map（← GLAS 契約：gray[label==k]）
    features: dict[str, float]        # 扁平特徵區 = score 表達式的變數空間
    meta:     dict                    # nm_per_px、dx/dy、step 診斷（fallback_reason…）
```

- 每張卡宣告 reads / writes（如 `Subtract: reads ["test","ref_aligned"] → writes ["diff"]`），
  recipe 驗證期靜態檢查「串起來缺什麼」，不等執行才爆。
- `features` 是唯一算分介面：CD、SNR、GLV、focus 一視同仁，全部可進表達式、
  全部進 feature vector 匯出（ML 備料）。
- 內部運算 float32，顯示端才轉 8-bit；載入用 CJK-safe `np.fromfile`+`imdecode`（PEAR）。

### 3.3 Step 介面與註冊

```python
class Step(ABC):
    key: str                          # "snr_map"
    category: str                     # 前處理｜對位｜Reference｜運算｜ROI｜特徵｜判定
    params: list[ParamSpec]           # 名稱/型別/範圍/預設/一行說明 → UI 表單自動生成
    reads: list[str]; writes: list[str]
    requires_ref: bool = False        # rsem 模式下自動禁用（除非上游有 Reference 卡）

    @abstractmethod
    def run(self, ctx: Context, p: dict) -> Context: ...

@register_step                        # 新算法 = 新 class + decorator，UI 零修改
```

> MMH `recipe_base` 的一般化：寫死 6 stage → 任意 DAG 節點；並補上 MMH 缺的 params 驗證。
> **ParamSpec 的「一行說明 + 合理預設 + 範圍防呆」是推廣成敗關鍵**，每張卡都必填。

### 3.4 Recipe（DAG JSON，單檔可互傳）

```json
{
  "recipe_id": "M1_EBI_bridge", "version": 3, "author": "HX",
  "description": "M1 站 EBI 假點過濾：對位相減 + SNR/CD 雙特徵",
  "routes": {
    "ebi_patch": ["load","norm","align","subtract","snr","segment","cd","score","bin"],
    "rsem":      ["load","norm","golden","subtract","snr","segment","cd","score","bin"]
  },
  "nodes": { "align": {"step":"align","params":{"method":"phase","search":8}}, "…": {} },
  "edges": [["subtract","snr"],["subtract","cd"],["snr","score"],["cd","score"]],
  "score": {"expr": "snr_max * sqrt(blob_area)", "threshold": 3.0,
             "bins": {"below": 0, "above": 1}}
}
```

- v1 UI 產生直線＋分流（routes），core 以一般 DAG 執行（拓撲排序 ← GLAS
  `recipe_dependency_order`），v2 上自由畫布時引擎零改動。
- 驗證走 lint 模式（← KLIP `Issue` 結構）：無環、reads/writes 相容、params 範圍、
  輸入型別可用性，一次列出所有問題。

---

## 4. Score 表達式引擎

GLAS `gds_boolean` 的 tokenizer → AST → evaluator 移植改造：

- 變數 = `features` 的 key（`snr_max`、`cd_x_px`、`glv_mean_roi1`…），UI 下拉列出目前 pipeline 會產出的全部 key
- 運算：`+ - * / ** sqrt log abs min max`、比較與布林 `> < >= <= == and or not`
- 兩用：`score = <expr>`（連續分數 → 直方圖/排序）與 bin 條件（`score >= 3 and cd_x_px > 25`）
- v1 鎖定此運算元集，不做迴圈/自訂函數 —— 更複雜的邏輯就寫新 Step（本來就是擴充點）

---

## 5. Step Library v1（19 張卡）—— 兩大類 + ADC 串接

Pipeline 在 UI 上呈現為**三段式**，對應「defect 分數由影像與算法兩件事決定」的心智模型：

```
【影像段 Image】把圖變乾淨、變可比 → 產出的是「影像流」
        ↓
【算法段 Algo】從圖量出數字（量化證據）→ 產出的是「features」
        ↓
【ADC 判定段】features → score → bin → 寫回
```

每張卡依所屬段落上色（影像=藍、算法=橙、判定=紫），Library 也照這三組排 ——
使用者不用理解 context/DAG，只要記得「先弄圖、再量化、最後判定」。
段落順序由 recipe 驗證強制（算法卡不能排在它要用的影像流之前）。

### 影像段（Image — 影像優化，寫入 images）

| 卡片 | 做什麼 | 來源（搬運 function） |
|---|---|---|
| **Load Patch**（固定第一張） | dataset → images | KLIP `klarf_core`+`read_tiff_pages`+tifffile；GLAS `sem_loader` |
| **Percentile Norm** | P2–P98 拉伸 | Fusi³ `_normalize_image_with_range` |
| **GLV-Mask Norm** | 指定 GLV 帶內錨定正規化 | Fusi³ `_percentile_range_glv_masked` |
| **Histogram Match** | 向 reference 匹配直方圖（跨機台） | Fusi³ `match_histogram_linear/_percentile/_exact` |
| **Denoise** | median / gaussian / NLM | cv2 薄封裝（新，~50 行） |
| **Align** | 5 backends：phase/ncc/ecc/hybrid/template | Fusi³ `_calculate_alignment`+`_apply_alignment`；GLAS `fine_align_one`、`_parabola_subpx` |
| **In-patch Ref** | patch 內附 ref page 當 reference 流 | ingest 直供 |
| **Golden Cell** | 週期估測+堆疊 golden，ghosting 信心 gate | CPE `estimate_period`+`stack_cells`+`ghosting_score` |
| **GDS Render** *(v1.5 選配)* | layout 渲染合成 ref + ROI label map | GLAS `render_gray_and_label_from_geoms` |
| **Subtract / Blend / Invert** | 影像流運算 | Fusi³ |

### 算法段（Algo — 量化，寫入 features）

| 卡片 | 做什麼 | 來源 |
|---|---|---|
| **ROI Box / Grid / MultiROI** | 手畫、網格、target/reference ROI 集 | Fusi³ `MultiROISet`（隨對位 `shifted()`）；PEAR grid |
| **GLV Stats** | ROI 內 mean/median/Qn/std/min/max | PEAR `attributes.glv_value/glv_stats` |
| **ROI SNR** | defect box vs 背景 ring：SNR/contrast/edge/DVI | Fusi³ `calculate_roi_snr` |
| **SNR Map** | 局部訊噪比地圖 + snr_max | Fusi³ `compute_snr_map`（修 tuple 回傳） |
| **Blob Segment** | 門檻→連通域→area/aspect/dist | Fusi³ `segment_defects` → `DefectROI` |
| **CD Measure** | blob/ROI 次像素邊緣定位 → cd_x/y_nm、area_nm² | MMH `_refine_yedge_*_batch`、`_extract_strip`、`_SubpixelResult`（一般化到 X/Y）+ `calibration` |
| **Focus / Quality** | Laplacian/Tenengrad/FFT 高頻比（預篩 gate） | MMH `image_quality`+`compute_quality` |
| **Outlier Flag** | 族群內 Tukey IQR 離群 | PEAR `group_outliers` |

### ADC 判定段（串接，寫入 score / bin）

| 卡片 | 做什麼 | 來源 |
|---|---|---|
| **Score** | 表達式算分（features 自由組合） | §4 表達式引擎（新） |
| **Threshold → Bin** | 門檻/條件 → bin/class | 新 |
| **寫回 / 輸出** | KLARF 三模式 + 報表（§8） | KLIP + MMH exporters |

特徵命名慣例：`<卡片>_<量>[_<roi>]`（`snr_max`、`cd_x_px`、`glv_mean_roi1`）。
**v1 移除（列 backlog）**：PCA Ref、Region Stats/FFT。
v2 擴充卡備選：上述兩張 + ML Classify、BSE/SE 多通道融合、雙 reference AND。

---

## 6. 批次引擎、快取與結果儲存

- **執行**：MMH `measurement_engine` 模式 —— ProcessPool + `as_completed`、per-defect
  try/except（單顆爆=該顆 FAIL 不殺整批）、`on_progress`/`abort_check` callback、
  Focus/Quality gate 低分短路。
- **效能目標**：千級常態、偶爾上萬 → **10k patch 全 pipeline < 2 min**（MMH 實測 13k
  張大圖 3–6 min，patch 更小，目標合理）。
- **中間結果快取（調參迴圈的核心）**：per-defect、以「step 參數鏈 hash」為 key。
  改第 5 張卡 → 前 4 張輸出直接複用；改門檻/表達式 → 完全不重跑影像，
  純重算 score（**拖門檻線 → bin 數即時變**的基礎）。
- **結果**：每顆一列 `{defect_id, features…, score, bin, 診斷}` → SQLite 批次歷史
  （← MMH `batch_run_store`）；直方圖/gallery/報表/feature 匯出全吃這張表。

---

## 7. UI v1（三工作區 + 導覽）

### 7.0 使用旅程 —— 「我有一組圖 + KLARF，然後呢？」（不寫 code 的使用者視角）

工具頂部是固定的四步 stepper：**① 載入資料 → ② 設計 pipeline → ③ 試跑調參 → ④ 輸出**。

1. **載入**：把 KLARF 檔（或整個資料夾）拖進來。工具自動認版本、找到對應 TIFF、
   判別 ebi_patch/rsem，顯示摘要卡：幾顆 defect、有無 ref、pixel size、wafer map 縮圖。
   此時還沒有任何算法，就能先逐顆瀏覽 test/ref 原圖（KLIP 的看圖體驗）。
2. **選起點**（三選一）：(a) **內建範本** —— 系統依資料型別推薦（EBI patch → die-to-die
   假點過濾範本；RSEM → cell-to-cell 或單張 rule-based 範本），一鍵載入就是一條能跑的
   pipeline；(b) 匯入同事給的 recipe JSON；(c) 空白開始。**推廣場景 90% 走 (a)：
   從會動的東西開始改，不是從白紙開始。**
3. **設計**：在 Studio 把想法翻成卡片。左側 Library 三組（影像藍/算法橙/判定紫），
   中間 pipeline 同色分段；每加一張卡或改一個參數，右側立刻重算目前這顆 defect 的
   中間輸出鏈 —— **所見即所得，想法對不對當場看到**。切幾顆代表性 defect
   （已知真缺陷、已知假點各挑幾顆釘選）來回驗證。
4. **試跑調參**：按「試跑」（預設抽 500 顆）→ 下方直方圖亮起來 → 拖門檻線看 bin 數
   → 開 Gallery 按分數排序掃一眼（高分的是不是都真的？門檻附近是什麼？）→ 回頭改參數
   （快取讓重算只發生在改動之後的步驟）。滿意後跑全批。
5. **輸出**：Export 精靈選寫回模式（就地改欄/新 KLARF 含 score+class/Top-N）＋報表；
   存 recipe JSON，傳給同事 —— 對方載入後從第 1 步直接跑。

### 工作區

1. **Studio**（mock 已確認方向）：Step Library（三色分組）｜Pipeline（三段式直線＋
   輸入型別分流 tab）｜單顆預覽（點卡看中間輸出、features 表、verdict、釘選比對顆）｜
   整批分數直方圖（門檻線可拖）。
2. **Gallery**：縮圖網格（test/diff/overlay 底圖可切）、score/任一 feature 排序、
   點直方圖 bar 篩選該區間、框選送單顆詳看；虛擬捲動撐 10k+。
   → 對應 KPI「review efficiency」：按分數排序一眼驗證「排前面的是不是都是真的」。
3. **Export**：KLARF 寫回精靈 —— 選模式（就地改 CLASSNUMBER/BIN/DSIZE ｜ gen 新
   KLARF 含 score+new class 欄位 ｜ Top-N 篩選新檔），寫回前自動跑 KLIP `lint()` 健檢
   ＋ 變更摘要確認（動了幾列、哪些欄）。另有 CSV/Excel、feature vector CSV、overlay 資料夾。
4. **推廣配套**：首啟導覽（← Fusi³ welcome_tutorial 模式）、內建 2 份範例 recipe
   （die-to-die、cell-to-cell）+ 合成示範資料、一頁快速參考卡 PDF（← GLAS 慣例）。

主題沿用 GLAS/CPE token 系統（奶油底、單一 accent、instrument 風格）。

---

## 8. KLARF 寫回細節（依訪談展開）

| 模式 | 行為 | 依託 |
|---|---|---|
| 就地改欄 | CLASSNUMBER / ROUGHBIN / FINEBIN / DSIZE 依 bin 結果 `batch_set`，其餘 byte 不動 | KLIP span-splice |
| Gen 新 KLARF（全量） | 複製原檔 + 擴充 DefectRecordSpec 加自訂欄（如 `ADCSCORE` `ADCCLASS`）寫入分數與新分類 | KLIP `to_text` + spec 改寫（新檔不受無損限制） |
| Gen 新 KLARF（Top-N） | 依 score 排序取前 N（或條件篩選）產新檔給 Review SEM，DEFECTID 重排 | KLIP API-KLARF 既有能力 + MMH TopN exporter 座標修正 |

---

## 9. Milestones

| 里程碑 | 內容 | 驗收 |
|---|---|---|
| **M0 抽庫** | Vendoring §5 清單檔案進 `adept/core`；統一 KLARF parser（KLIP `klarf_core` 為底，補 ImageFileName；棄用重複的 `klarf_parser`）；修三摩擦（ROI 座標統一正規化、SNR 正負號統一、`compute_snr_map` 回傳）；合成影像單元測試 | `pytest` 全綠、core 零 Qt import |
| **M1 引擎** | Context/Step/registry/Recipe(DAG)/表達式/單顆執行 + **synthetic data generator + KLIP 產測試 KLARF fixture 庫** | CLI 對合成 KLARF+TIFF 跑通 die-to-die pipeline，輸出 features JSON |
| **M2 批次** | ProcessPool + SQLite + 中間快取 + headless CLI + feature vector 匯出 | 10k 合成 patch < 2 min；改末端參數重跑 < 5 s |
| **M3 Studio** | 四區塊 Studio + 即時中間輸出鏈 + 直方圖/門檻拖曳 | **首發案例：EBI patch 算分全程滑鼠完成**（想法→算法的證明點） |
| **M4 雙輸入** | rsem ingest、型別分流、Golden Cell 卡（含相位搜尋補完） | 同一 recipe 吃 EBI patch 與 RSEM 合成資料 |
| **M5 Gallery+Export** | Gallery 聯動、KLARF 三種寫回模式（含 lint+確認）、報表/overlay | 完整調參迴圈 demo：調參→分佈→gallery→寫回 |
| **M6 推廣包** | 離線 wheels 安裝腳本（主）+ exe 打包（備）、首啟導覽、範例 recipe、快速參考卡 PDF | 乾淨離線 Windows 機從零裝起→跑通範例 |
| **廠內驗證**（穿插） | 每個 M 完成後帶 `fab_probe` 腳本進廠對真資料，文字報告貼回修 fixture | 真實 KLARF 變體全部進 fixture 庫 |

每個 milestone 照現行慣例開 `docs/plans/F*.md` + SESSION_LOG。

---

## 10. 開發資料策略（資料不能出廠的配套）

1. **合成資料產生器**（`tools/make_sample.py`，CPE/PEAR/GLAS 皆有先例）：
   可調參的合成 patch（cell 陣列/線條 + 植入 bridge/particle/missing + noise/對位偏移），
   搭配 KLIP 產生對應測試 KLARF —— 全 pipeline 開發與 CI 都用它。
2. **fab_probe 廠內探測腳本**（stdlib-only、單檔、免安裝）：
   - `probe_klarf.py`：KLARF 版本/欄位/image-layout 變體盤點（← `klarf_tif_probe` 擴充）
   - `probe_tiff.py`：page 數/尺寸/位深/壓縮盤點（不碰像素值輸出）
   - `probe_stats.py`：匿名統計（GLV 直方圖形狀、patch 尺寸分佈）
   輸出一律純文字/可貼上的 JSON —— 你在廠內跑、貼結果回來，我把變體補進 fixture。
3. **格式契約測試**：每收到一種新變體 → 寫成最小化合成 fixture → 永久回歸測試。

## 11. 風險與待決

1. KLARF 變體超出 `klarf_core` 已知三種 → fab_probe 持續收集，M1 起建 fixture 庫。
2. Golden Cell 相位（CPE `choose_origin` 是 stub）→ M4 補相位搜尋。
3. 推廣後 recipe 品質參差 → recipe lint + 範例庫 + 參考卡緩解；權限/集中管理留 v2。
4. 命名待定（ADEPT 為代號；可延續水果/自然系：PEAR、Fusi³…）。

## 12. v2+ Backlog

PCA Ref 卡、Region Stats/FFT 卡（v1 移出）｜自由 DAG 畫布（雙 reference AND）｜
ground-truth 標注 + 抓漏/誤殺/混淆矩陣儀表板（KPI「分類準確度」的完整量化靠這個）｜
ML Classify 卡（吃 v1 匯出的 feature vector）｜自然語言→recipe 草稿（AI 輔助）｜
BSE/SE 多通道融合卡｜GDS Render 正式化（die-to-database）｜recipe diff / A-B 比較｜
共用 recipe library｜多 lot 趨勢。
