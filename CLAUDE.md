# CLAUDE.md — ADEPT 開發指南

給 Claude Code / 開發者的專案脈絡。**每次 session 結束請更新 `SESSION_LOG.md`。**

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
│   └── calibration.py       # nm/px 校正 profile
├── ui/                      # PySide6 Studio（**唯一允許 Qt 的地方**）
│   ├── viewmodel.py         #   RecipeModel（Qt-free，可 headless 測）
│   ├── theme.py widgets.py  #   主題 token + 6 個資料驅動元件
│   ├── workers.py           #   載入/預覽(請求合併)/試跑 背景執行緒
│   └── studio.py app.py     #   主視窗 + 進入點
├── tests/                   # 291 個測試，全部用合成資料，<10s 跑完
├── tools/make_sample.py     # 合成 KLARF + patch TIFF 產生器（開發與 CI 的資料來源）
├── examples/recipes/        # 範例 recipe（也是 UI「載入範本」的來源）
├── (fab_probe/)             # 廠內格式探測腳本 —— **尚未建立**，見 §8
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
| **中心框幾何與影像尺寸綁死** | 同一組 `glv_stats` 參數在 128² patch 上準、在 256² RSEM 上漏抓（缺陷散佈超出框） | 幾何類參數要隨 route 走（見 `dual_route_basic.json`：兩條 route 各自一個 glv 節點），或改用無量綱分數如 `(glv_max-glv_median)/(glv_std+0.5)` |
| **pytest 收集期 import Qt** | `test_no_qt_after_import` 失敗 | UI 測試一律 **lazy import**（在 fixture 內 import 並注入 globals） |

---

## 8. 待廠內驗證的假設（重要）

開發全程用合成資料（真實資料不能出廠）。以下假設**必須在廠內確認**（`fab_probe/` 探測腳本尚未建立，已移至 M5 工作項）：

1. **EBI patch 的 page→channel 對應**：目前假設每顆 defect 第一張 = test、第二張 = ref
   （`dataset.load_dataset` 的 `channel_order` 參數）。真實 TiffSpec 語意待確認。
2. **`nm_per_px` 來源**：KLARF 裡目前找不到，暫為 None（CD 量測的 nm 值因此為 0）。
   需確認實際站點從哪拿（TIFF tag？recipe？calibration profile？）。
3. **KLARF 變體**：`klarf_core` 已處理三種 image-layout 變體，實際站點可能還有新花樣。
   每遇到一種新變體 → 做成最小化合成 fixture → 永久回歸測試。

---

## 9. 進度與下一步

| Milestone | 狀態 | 內容 |
|---|---|---|
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：`examples/recipes/dual_route_basic.json` 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1% |
| M5 Gallery+Export | ⬜ | 縮圖網格 + 直方圖聯動；KLARF 三種寫回模式 + 報表 |
| M6 推廣包 | ⬜ | 離線安裝、首啟導覽、範例 recipe、快速參考卡 |

v2 backlog：自由 DAG 畫布、ground-truth 標注 + 混淆矩陣、ML Classify 卡
（吃現成的 feature vector CSV）、PCA Ref、Region Stats/FFT、BSE/SE 多通道融合。

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
