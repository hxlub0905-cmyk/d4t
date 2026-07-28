# CLAUDE.md — ADEPT 開發指南

給 Claude Code / 開發者的專案脈絡（操作手冊）。
**每次 session 結束請更新 `SESSION_LOG.md`。**

> **第一次接手這個專案？先讀 [`docs/HANDOVER.md`](docs/HANDOVER.md)。**
> 那份講「為什麼會長成這樣」：工具的由來與目的、需求訪談的結論與理由、
> 六個來源專案各給了什麼（那份跨專案脈絡不在程式碼裡）、
> 哪些事已驗證哪些還是假設、以及哪些設計「看起來可以隨便改但其實有理由」。
> 這份 CLAUDE.md 則是「怎麼動手」。

---

## 1. 這是什麼

**ADEPT** = Auto Defect Evaluation Pipeline Tool。
半導體 E-beam Inspection 的彈性 ADC 工具：讀 patch/RSEM 影像 + KLARF，
用「步驟卡片組 pipeline」對每顆 defect 算分、分 bin、寫回 KLARF。

**最高指導原則：站點差異封裝進 recipe，不封裝進程式碼。**
第二原則：**推廣鐵則** —— 目標使用者是不會寫 code 的製程/設備工程師。
任何讓他們看不懂或會爆錯誤訊息的設計，都是 bug。

---

## 2. 心智模型：三段式

```
【影像段 Image】把圖變乾淨、變可比  → 產出「影像流」（ctx.images）
        ↓
【算法段 Algo】 從圖量出數字（量化證據）→ 產出「特徵」（ctx.features）
        ↓
【ADC 判定段】 features → score → bin → 寫回 KLARF
```

**注意（F7-3 起）**：上面的三段是 `Step.category` —— **引擎**的分類
（快取切點、驗證順序）。**使用者看到的**分組是另一個軸 `Step.group`：

```
Input → Enhance → Region → Compare → Measure → ADC
```

因為 category 描述的是「這張卡吐什麼型別」，不是「使用者想解決什麼問題」。
兩個軸各有各的用途，不要合併。新卡片放哪一組：看它吃什麼、吐什麼
（規則寫在 `pipeline/step.py` 的 `GROUP_*` 常數旁邊）。

UI 三段分色（影像=藍 `#6f93b5`／算法=橙 `#c06a1d`／判定=紫 `#8a6fb5`）。
這個分類不是裝飾 —— 它同時是 `Step.category`、快取切點、recipe 驗證順序的依據。

---

## 3. 目錄結構

```
adept/
├── core/                    # 純運算，**禁止任何 Qt import**（tests/test_no_qt.py 守門）
│   ├── ingest/              # KLARF + 影像載入
│   │   ├── klarf_core.py    #   KLARF 1.2/1.8 無損讀寫引擎（vendored from KLIP，最重要的資產）
│   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
│   │   ├── imageio.py       #   CJK-safe 影像讀寫（np.fromfile + cv2.imdecode）
│   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 → DefectItem
│   ├── algo/                # 純 numpy/cv2 演算法（step 卡片包這些，不要在卡片裡重寫數學）
│   ├── pipeline/            # 引擎
│   │   ├── context.py       #   Context（images/features/meta）—— 步驟間的唯一介面
│   │   ├── step.py          #   Step 介面 + ParamSpec + registry
│   │   ├── recipe.py        #   Recipe(DAG) + lint 式 validate
│   │   ├── expression.py    #   score 表達式引擎（自寫 parser，不用 eval）
│   │   ├── engine.py        #   單顆執行 + checkpoint 快取版
│   │   ├── batch.py         #   ProcessPool 平行批次
│   │   └── cache.py         #   影像段 checkpoint 快取（npz）
│   ├── steps/               # 步驟卡片（每檔一類）
│   ├── store/               # SQLite 批次歷史 + rescore
│   ├── export/              # KLARF 三種寫回模式 + CSV/Excel 報表 + overlay
│   └── calibration.py       # nm/px 校正 profile
├── ui/                      # PySide6 Studio（**唯一允許 Qt 的地方**）
│   ├── scope.py             #   產品範圍開關：目前只吃 EBI patch（F7-1，見 §11）
│   ├── viewmodel.py         #   RecipeModel（Qt-free，可 headless 測；含 edges）
│   ├── canvas.py            #   節點畫布（n8n 式；F7-6，純 UI，引擎零改動）
│   ├── results.py           #   Results 視窗：直方圖 + Gallery + 輸出（F7-5）
│   ├── theme.py widgets.py  #   主題 token + 6 個資料驅動元件
│   ├── gallery.py           #   同屏比多顆（虛擬捲動，撐 10k+）
│   ├── welcome.py           #   首啟導覽 + 範例 recipe 庫對話框
│   ├── export_dialog.py     #   輸出精靈（寫回前一定先預覽變更）
│   ├── workers.py           #   載入/預覽(請求合併)/試跑 背景執行緒
│   └── studio.py app.py     #   主視窗 + 進入點
├── tests/                   # 520+ 個測試，全部用合成資料，~30s 跑完
├── tools/                   # make_sample(_rsem).py 合成資料；離線安裝三件套：
│                            #   fetch_wheels.py（有網路的機器抓）→ install_offline.py
│                            #   （air-gapped 機器裝）→ doctor.py（環境自檢）
├── examples/recipes/        # 範例 recipe（也是 UI「載入範本」的來源）
├── fab_probe/               # 廠內格式探測腳本（stdlib-only、純文字輸出），見 §8
└── docs/plans/              # F0 = master plan；每個 milestone 一份
```

---

## 4. 鐵則（違反 = 測試會擋）

1. **`adept/core` 不得 import Qt**。UI 只透過 callback 與 core 互動。
2. **Python 3.9 相容語法**（廠內機器可能是舊版）。測試以 `ast.parse(feature_version=(3,9))` 掃全套件。
3. **每個 ParamSpec 的 `help` 必填**且要是白話。`register_step` 會拒絕沒有 help 的卡片。
4. **每個 Step 要有合理 default 與 min/max**。使用者填爆的值必須擋在 `validate_params`，
   不能讓它跑到演算法裡炸。
5. **檔案寫入一律 atomic**（`.tmp` + `os.replace`）。
6. **KLARF 寫回必須無損**：沒被改到的 byte 要與原檔逐位元組相同（`klarf_core` 的 span-splice）。
7. **單顆 defect 出錯不得殺掉整批**（`run_defect` 從不 raise，回 `ok=False`）。

---

## 5. 加一張新卡片（最常見的工作）

```python
# adept/core/steps/my_card.py
from ..pipeline.context import Context
from ..pipeline.step import CATEGORY_ALGO, ParamSpec, Step, StepError, register_step

@register_step
class MyCardStep(Step):
    key = "my_card"                    # recipe JSON 用的 id
    label = "我的卡片"                  # UI 顯示
    category = CATEGORY_ALGO           # image / algo / adc
    help = "一行白話：這張卡做什麼。"      # 必填
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="要分析哪個影像流。"),
        ParamSpec(name="k", type="int", default=3, min=1, max=99,
                  help="視窗大小（越大越平滑）。"),
    ]
    reads = ["diff"]; writes = []; features_out = ["my_metric"]

    def run(self, ctx: Context, params):
        p = self.validate_params(params)
        img = ctx.require_image(p["source"])       # 缺影像會拋帶說明的 ContextError
        ctx.add_feature("my_metric", float(...))   # 演算法請呼叫 adept.core.algo.*
        return ctx
```

`steps/__init__.py` import 它即完成註冊 —— **UI 與引擎零修改**，卡片庫自動出現。
param 相依 I/O（例如輸出流名稱由參數決定）覆寫 `resolve_reads/resolve_writes/resolve_features`。

---

## 6. 開發流程

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt && pip install pytest

QT_QPA_PLATFORM=offscreen pytest -q                # 全部測試（Windows 不用設 QT_QPA_PLATFORM）
python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
python -m adept gui                                # 開 Studio
python -m adept run examples/recipes/die_to_die_basic.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
```

新功能請開 `docs/plans/F<n>-<name>.md`（沿用 GLAS/MMH 慣例），完成後更新 `SESSION_LOG.md`。

---

## 7. 已知的坑（踩過，別再踩）

| 坑 | 症狀 | 解法 |
|---|---|---|
| **fork 死鎖** | GUI 按「試跑」永遠不回、progress 一格不動 | `batch._pool_context()`：主執行緒 fork、非主執行緒 spawn。改動這裡務必跑 `tests/test_batch_thread_safety.py` |
| **OpenCV IPP 非決定性** | 同張圖算兩次差 ~1e-8，快取結果對不起來 | `batch.pin_cv2_deterministic()` 關 IPP（每個 worker 都呼叫） |
| **Fusi³ ecc 對位正負號** | ecc backend 位移與其他四個相反 | 已於 `algo/align.py` 修正並鎖測試 |
| **MMH 次像素 batch 版偏移** | batch 版比 scalar 版低約 1.5 px | 刻意保留原行為，檔頭有記錄；要用精確值請用 scalar 版 |
| **中心框幾何與影像尺寸綁死**（F7-4 已修） | 同一組 `glv_stats` 參數在 128² patch 上準、在 256² RSEM 上漏抓（缺陷散佈超出框） | **幾何已從量測卡搬到 Region 卡**（`roi_define`），量測卡只引用 ROI 名字。`size_unit="percent"` 的框會隨影像尺寸縮放，同一份 recipe 換 patch 尺寸不會失效。迴歸測試 `tests/test_region.py::test_percent_sizing_survives_a_patch_size_change` |
| **pytest 收集期 import Qt** | `test_no_qt_after_import` 失敗 | UI 測試一律 **lazy import**（在 fixture 內 import 並注入 globals） |
| **KLARF variant D 誤判**（M5 修正） | 真實 1.8 檔（ImageList 欄不在最後、且無 IMAGECOUNT 欄）被 `lint()` 判定每一列都違法，Export 精靈跳紅字 | `row_len_ok` 改用 `effective_row_len()`：把 `Images N { … }` 子區塊折算成一欄。**注意 `image_layout()` 對這個變體仍回 None，而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它**。迴歸測試 `tests/test_klarf_variant_d.py` |

---

## 8. 待廠內驗證的假設（重要）

開發全程用合成資料（真實資料不能出廠）。以下假設**必須在廠內用 `fab_probe/` 探測腳本確認**。
那三支腳本是 stdlib-only 單檔、輸出純文字且預設遮蔽 Lot/Wafer/Device 等識別碼，
設計成可以直接複製貼出廠區（細節與資料外流說明見 `fab_probe/README.md`）：

| 假設 | 現況 | 用哪支腳本確認 |
|---|---|---|
| 1. EBI patch 的 page→channel 對應 | 假設每顆 defect 第一張=test、第二張=ref（`load_dataset` 的 `channel_order`） | `probe_tiff.py FILE.tif --with-klarf FILE.klarf` → 看它回報的配對型態（pairs / single / triples）。`probe_stats.py` 的奇偶頁均值比較可佐證 |
| 2. `nm_per_px` 來源 | 找不到，暫為 None（CD 量測的 nm 值因此是 0） | `probe_klarf.py` 的 nm_per_px 名稱搜尋段；`probe_tiff.py` 的解析度/描述標籤 |
| 3. KLARF 變體 | `klarf_core` 已知四種（含 M5 修正的 variant D） | `probe_klarf.py` 的 image-layout 變體判定與證據 |

**每遇到一種新變體 → 做成最小化合成 fixture → 永久回歸測試**（見
`tests/test_klarf_variant_d.py` 的寫法：先斷言「這份檔案確實是該變體」當前提，再測行為）。

## 9. 進度與下一步

| Milestone | 狀態 | 內容 |
|---|---|---|
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：`examples/recipes/dual_route_basic.json` 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1% |
| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `adept export` |
| M6 推廣包 | ✅ | 離線安裝三件套（`tools/fetch_wheels.py` / `install_offline.py` / `doctor.py`，全 stdlib-only）、首啟導覽 + 範例 recipe 庫對話框、5 份範例 recipe。快速參考卡 PDF 暫緩（移到 backlog） |
| M7 UI/UX | ✅ | A 組防呆 + **UI 全英文**（`tests/test_ui_english_only.py` 鎖住）。F7 全數完成：patch-only 收斂（`ui/scope.py`）、中性色/平面主題 + 暗色、卡片依流程階段分組 + 搜尋 + 前置條件 badge、**Region 段（具名 ROI）**、Results 視窗、**節點畫布**。計畫書 `docs/plans/F7-canvas-and-taxonomy.md` |

v2 backlog：快速參考卡 PDF、自由 DAG 畫布、ground-truth 標注 + 混淆矩陣、ML Classify 卡
（吃現成的 feature vector CSV）、PCA Ref、Region Stats/FFT、BSE/SE 多通道融合。

---

## 11. 產品範圍開關（F7-1）

**Studio 目前只吃 EBI patch。** RSEM 的能力（ingest、Golden Cell、週期估測、
範例 recipe、測試）**完全沒有被刪**，只是從 GUI 上收起來。

要打開，改 `adept/ui/scope.py` 一個常數：

```python
SUPPORTED_KINDS = ("ebi_patch",)            # 加 "rsem" 就整條路線回來
HIDDEN_STEPS = ("golden_cell", "cell_period")   # 清空就出現在卡片庫
```

`tests/test_ui_patch_only.py` 同時鎖住兩邊：GUI 真的收斂了，而且
**打開開關就回得來**（那支測試會 monkeypatch 這兩個常數再驗一次）。

> ⚠ **`adept/core/algo/period.py` 不要刪。** 它現在只被 Golden Cell 用到，
> 看起來像是可以跟 RSEM 一起砍掉的東西 —— 但 `estimate_period` /
> `choose_origin` 的相位搜尋是之後做 **pattern-frame ROI** 的唯一工具
> （patch 是以 defect 為中心裁切的，晶格相位逐顆不同；
> 見 `docs/plans/F7-canvas-and-taxonomy.md` §4）。

CLI 不受影響：`python -m adept run` 照樣跑得動 rsem recipe。

---

## 9.5 部署到受限的廠內機器

主要使用情境是**沒有 git、pip 連不出去、DLP 會擋含二進位的壓縮檔**的公司機。
對應設計：

- 整個 repo **只有純文字檔**（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml`），
  所以 GitHub「Download ZIP」下載得下來（那份 zip 不含 `.git`）。
  **不要把 `.git` 打包給使用者** —— 二進位 pack 物件 + `hooks/*.sample` 腳本會觸發 DLP。
- 相依套件走離線 wheels：`tools/fetch_wheels.py`（有網路的機器）→ 帶 `wheels\` 過去 →
  `tools/install_offline.py`（廠內機器）。兩支都是 stdlib-only，因為它們在套件裝好之前就要能跑。
- 裝不起來或跑不動時的第一件事：`python tools/doctor.py` —— 逐項 ✓/✗ 並附「怎麼修」。
  最常見的失敗是 **wheels 的 Python 版本與機器上的不符**（cp39 的輪子配 py3.12），
  `install_offline.py` 會在 pip 之前就攔下來並講清楚。
- 詳細步驟：`docs/OFFLINE-INSTALL.md`；不用 git 的取得方式：`docs/NO-GIT-SETUP.md`。

---

## 10. 來源專案對照（vendoring）

每個 vendored 模組檔頭都註明來源與改動。原始專案：

| 來源 | 提供了什麼 |
|---|---|
| **KLIP** | KLARF 1.2/1.8 無損引擎、TIFF page 對應、健檢 lint |
| **GLAS** | fine align、SEM loader、DAG 拓撲排序概念、ROI label map 契約 |
| **MMH** | recipe 架構原型、批次引擎模式、次像素邊緣定位、品質指標、KLARF 寫回 |
| **PEAR** | GLV 統計 metric bank、Tukey 離群、η²/Cohen's d、CJK-safe 影像載入 |
| **cell-period-estimator** | 週期估測、Golden Cell 堆疊、ghosting 分數 |
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、SNR map、blob 分割、MultiROISet |
