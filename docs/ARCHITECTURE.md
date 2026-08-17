# ADEPT 架構

這一份是**架構的唯一出處**：心智模型、資料模型、目錄結構。
其他文件要講到這些，一律連過來，不要複製一份 —— 複製出來的那份會漂移
（2026-08 就發生過：程式碼刪了五份範例 recipe，四份文件裡只有一份跟上）。

- 環境限制看 [`../AGENTS.md`](../AGENTS.md)
- 怎麼動手看 [`../CLAUDE.md`](../CLAUDE.md)
- 為什麼長成這樣看 [`HANDOVER.md`](HANDOVER.md)

---

## 心智模型：三段式

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

## 資料模型：兩個通道（影像流 vs 具名區域）

Context 有三層資料：**影像流 images**（名字 → 像素陣列，綁尺寸）、
**具名區域 rois**（名字 → 一串框，**0–1 正規化座標**，帶結構：幾個框、各在哪）、
**特徵 features**（名字 → 數字）。

```
影像流通道（像素）  Load ─→ Enhance ─→ Compare ─→ 'diff' ──────┐
                                                              ├─→ 量測卡 ─→ 特徵 ─→ score
區域通道（哪裡）    roi_cross / roi_template / GDS(未來)        │   source='diff'（流）
                      └─→ 具名區域 'cross' ────────────────────┘   roi='cross'（名字）
                            └─→ roi_mask ─→ 'mask' 流 ─→ Normalize 的 use_within（影像段）
```

**規則一句話：量測卡吃區域「名字」，影像卡吃 mask「影像流」。**
量測卡要「哪裡」的**結構**（框數、邊界、框外背景圈、哪框靠中心）——
0/255 的 mask 圖把結構壓扁丟光，所以量測卡的 `roi` 填名字、引擎量測當下
才換成像素。影像卡（Normalize 的 `use_within`）只要「哪些像素參與統計」，
那正是 mask 流的全部內容。兩條路同源（`Context.rois`），不會分家 ——
**不要**幫量測卡加 mask 流輸入、也**不要**讓區域卡直接吐 mask，
兩條平行的路會腐爛（F7-17 的教訓，F8c 落地時明確重申過）。

為什麼存「名字 + 正規化座標」不存 mask 圖：(1) patch 以 defect 為中心裁切、
晶格相位逐顆不同 —— recipe 存「怎麼找」，定位卡**每顆重新定位**；
(2) 比例座標讓同一份 recipe 在 128² 與 512² 上都對（F7-4 的坑）。

定位法契約：`roi_cross`（純規則）、`roi_template`（Golden Cell）、GDS（未來）
—— **出口相同：吐具名區域**（`resolve_regions_out`），下游零改動。
新 image source 進來的 checklist：Load 層吐具名流 → 挑一個定位法吐具名區域 →
下游（量測/mask/overlay/region check）不用動。

---

## 目錄結構

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
│   ├── region_check.py      #   區域跨顆檢視：框畫在 N 顆縮圖上（F7-11）
│   ├── template_dialog.py   #   從大圖疊 Golden Cell 模板（F7-12；模板存進 recipe）
│   ├── inspectors.py        #   每張卡自己的儀表（F7-17；依 Step.key 註冊）
│   ├── theme.py widgets.py  #   主題 token + 資料驅動元件 + 自繪圖示
│   ├── gallery.py           #   同屏比多顆（虛擬捲動，撐 10k+）
│   ├── welcome.py           #   首啟導覽 + 範例 recipe 庫對話框
│   ├── export_dialog.py     #   輸出精靈（寫回前一定先預覽變更）
│   ├── workers.py           #   載入/預覽(請求合併)/試跑 背景執行緒
│   └── studio.py app.py     #   主視窗 + 進入點
├── tests/                   # 1250+ 個測試，全部用合成資料
│   └── fixtures/recipes/    #   e2e 用的最小 recipe（**測試用，不是教學範例**）
├── tools/                   # make_sample(_rsem).py 合成資料；離線安裝三件套：
│                            #   fetch_wheels.py（有網路的機器抓）→ install_offline.py
│                            #   （air-gapped 機器裝）→ doctor.py（環境自檢）
├── fab_probe/               # 廠內格式探測腳本（stdlib-only、純文字輸出），見 §8
├── docs/plans/              # 進行中的開發計畫（F0 = master plan、F8）
└── docs/history/            # 封存：按月的 SESSION_LOG、做完的計畫書（**不進搬運包**）
```

> **`examples/` 不見了不是漏掉的。** 2026-08-16 使用者定調「範例 recipe 都先全部
> 拿掉」，整個目錄移除；連帶「用範例資料試一次」與「Templates…」兩個入口
> 也收起來了（`ui/scope.py` 的 `SHOW_SAMPLE_ENTRIES`）。要放回去：JSON 丟回
> `examples/recipes/`、常數改 `True`。加卡片時**不必**再同步維護五份範例。
