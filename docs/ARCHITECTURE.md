# d4t 架構

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
Input → Enhance → ROI → Measure → Compare → ADC → Output
```

（**七段**。F16 2026-08-20 使用者定稿的是八段；`Algo` 那一段在 F24 §5 解散進
判定（算式住進 `decide.let` 的 working numbers、補值變成那一行的「missing ⇒」
屬性、跨顆換算變成 `Let.scale`），2026-08-24 使用者點頭。`GROUP_ALGO` 這個常數
留著給外掛卡相容，但它不在 `GROUP_ORDER` 裡。`ROI` 的內部 id 仍是 `region`
—— 顯示名與 id 是兩件事。）

因為 category 描述的是「這張卡吐什麼型別」，不是「使用者想解決什麼問題」。
兩個軸各有各的用途，不要合併。新卡片放哪一組：看它吃什麼、吐什麼
（規則寫在 `pipeline/step.py` 的 `GROUP_*` 常數旁邊）。

**這個順序不決定執行順序。** 執行是 `recipe.execution_order()` 的 DAG 拓撲排序
—— 線怎麼拉就怎麼跑。`GROUP_ORDER` 排的是**卡片庫的分區順序**（連帶 rail 的
上下順序與階段顏色），所以「Compare 排在 Measure 後面」不代表 `diff` 會晚一步
產生：那件事由線保證。

### 執行順序只有一個家：線（F17-①，2026-08-20）

⚠ **上面那句話在 2026-08-20 之前只對了一半，值得記住它錯在哪。** 舊的
`execution_order` 除了 `edges` 之外，還把 **route 上相鄰的每一對也當成一條邊**：

```python
for a, b in zip(route, route[1:]):     # 沒有人拉過的線
    pair_edges.add((a, b))
```

那串隱含邊構成一條走遍全部節點的鏈，所以執行順序**恆等於 route 順序** ——
而 route 順序在畫布上就是卡片的左右位置。也就是說：**兩張沒有任何線相連的卡，
誰先跑由使用者把它拖到哪裡決定**，而畫面上完全看不出來。

d4t 因此不是純 DAG 引擎，是「**有序清單 ＋ 補充的線**」：UI 照純 DAG 畫，引擎不
照純 DAG 跑。那個落差是好幾件事的共同根源 —— 特徵靠 route 順序（「後面的贏」）、
Output 卡靠 route 位置、`_late_normalize` / `_uneven_treatment` 的 history 也靠它。

現在邊**只**來自 `recipe.edges`，route 的排列退成 Kahn 的平手依據（排版，不是
語意）。拿掉隱含邊**不改變任何一份跑得起來的 recipe 的順序**（證明見
`execution_order` 的 docstring），唯一的行為差異是：一條「往回走」的線以前是
cycle 錯誤，現在照線跑。

`routes` 因此退化成「**這條 route 有哪些卡**」＋ 一個穩定的排序依據。

⚠ 順序有**兩份**（`step.py` 的 `GROUP_ORDER` 與 `ui/widgets.py` 的
`LibraryPanel.GROUPS`，後者多帶標題與副標），`tests/test_ui_f16_stages.py`
把它們綁在一起。

兩段的界線各有一條自動套用到 registry 的測試：
**Algo 段的卡不吃影像流**（`resolve_reads()` 恆為空 —— 使用者：「measure 是量出
數值來，Algo 是拿這些 feature 去做更 custom 的處理」）、
**Output 段的卡是 end point**（`resolve_writes()` 與 `resolve_features()` 都是空的）。

Output 段是**三張卡**（F38，2026-08-26）：`output_report`「Write report」
（一個資料夾，要哪幾樣是一格勾選：報表／表格／圖／Excel／box plot／recipe）、
`output_klarf`「Write KLARF」、`output_char`「Write comparison」。
以前是七張，而其中五張回答的是同一個問題 —— 收斂的理由與那四張的去向見
`d4t/core/steps/output.py` 的模組說明。

這個分類不是裝飾 —— 它同時是 `Step.category`、快取切點、recipe 驗證順序的依據。

⚠ **顏色不是照這三段分的**（F7-9 起）。以前這裡寫著「影像=藍／算法=橙／
判定=紫」，而那在 F7-9 就過期了：試用回饋的原話是「圖示很不錯，但太多都同個
顏色」—— 六個階段只有三種色，等於顏色這個維度白給了。現在**每個流程階段各一
個色相**（冷暖仍然對得上三段式），`seg_hex` 只留給真的在講三段的地方（首啟
導覽的三段說明、直方圖、Score/Bin 尾卡）。
**唯一出處是 `d4t/ui/theme.py::group_hex` 的 docstring**，不要在這裡複製一份
色碼 —— 上一次複製出來的那一份漂了一年。

## 資料模型：兩個通道（影像流 vs 具名區域）

Context 有三層資料：**影像流 images**（名字 → 像素陣列，綁尺寸）、
**具名區域 rois**（名字 → 一串框，**0–1 正規化座標**，帶結構：幾個框、各在哪）、
**特徵 features**（名字 → 數字）。

```
影像流通道（像素）  Load ─→ Enhance ─→ Compare ─→ 'diff' ──────┐
                                                              ├─→ 量測卡 ─→ 特徵 ─→ score
區域通道（哪裡）    roi_reference（三個 method）                  │   source='diff'（流）
                      └╌→ 具名區域 'cross' ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘   roi='cross'（名字，
                          （畫布上是虛線 + 菱形埠）                  由那條線水合出來）
                            └─→ roi_mask ─→ 'mask' 流 ─→ Normalize 的 use_within（影像段）
```

**規則一句話：量測卡吃區域「名字」，影像卡吃 mask「影像流」。**

那個「名字」在畫布上是**一條虛線 + 菱形埠**，而**線就是儲存**
（F42，2026-08-27）：區域依賴跟影像流一樣住在 `recipe.edges` 裡
（`[來源, 區域名, 這張卡, 參數名]`），`roi="cross"` 那一格是從線**水合**出來
的值，不寫進 JSON。判準只有一支：`recipe.is_region_edge`。

* **兩套機制對齊**了 —— 以前影像走線、區域走參數，每次改動都要多想一次。
* **順序因此是對的**：`execution_order` 只看線（F17-①），所以把 Region 卡
  拖到量測卡右邊不再讓量測卡先跑（那個 bug 是 F42 的起點）。
* 舊檔案由 `version < RECIPE_VERSION` 的遷移補線；`recipes/` 裡出貨的兩份
  已經是新格式。**手寫 recipe 從此要寫那條線**，而 `tools/doctor.py` 的
  「recipe 格式」那一項會提醒。
* 同一條 route 上兩張卡不准定義同名區域（`duplicate-region`，error）——
  引擎的 `ctx.set_roi` 是同名覆寫，名字唯一才讓「線指的那張卡」＝
  「引擎真的給的那個框」恆成立。

計畫書：[`plans/F42-region-edges-plan-b.md`](plans/F42-region-edges-plan-b.md)
（它推翻的是 [`history/plans/F12-region-edges.md`](history/plans/F12-region-edges.md)
§3，其他部分 —— 埠、虛線、唯讀參數格、同進同出 —— 全部保留）。
量測卡要「哪裡」的**結構**（框數、邊界、框外背景圈、哪框靠中心）——
0/255 的 mask 圖把結構壓扁丟光，所以量測卡的 `roi` 填名字、引擎量測當下
才換成像素。影像卡（Normalize 的 `use_within`）只要「哪些像素參與統計」，
那正是 mask 流的全部內容。兩條路同源（`Context.rois`），不會分家 ——
**不要**幫量測卡加 mask 流輸入、也**不要**讓區域卡直接吐 mask，
兩條平行的路會腐爛（F7-17 的教訓，F8c 落地時明確重申過）。

為什麼存「名字 + 正規化座標」不存 mask 圖：(1) patch 以 defect 為中心裁切、
晶格相位逐顆不同 —— recipe 存「怎麼找」，定位卡**每顆重新定位**；
(2) 比例座標讓同一份 recipe 在 128² 與 512² 上都對（F7-4 的坑）。

定位法契約：`roi_reference` **一張卡三個 method**（純規則的條紋／自己標的 cell／GDS 層；F30）
—— **出口相同：吐具名區域**（`resolve_regions_out`），下游零改動。
新 image source 進來的 checklist：Load 層吐具名流 → 挑一個定位法吐具名區域 →
下游（量測/mask/overlay/region check）不用動。

---

## 目錄結構

```
d4t/
├── core/                    # 純運算，**禁止任何 Qt import**（tests/test_no_qt.py 守門）
│   ├── ingest/              # KLARF + 影像載入
│   │   ├── klarf_core.py    #   KLARF 1.2/1.8 無損讀寫引擎（vendored from KLIP，最重要的資產）
│   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
│   │   ├── imageio.py       #   CJK-safe 影像讀寫（np.fromfile + cv2.imdecode）
│   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 + tiff_stack（多頁無 KLARF）→ DefectItem
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
│   ├── scope.py             #   產品範圍開關：四種輸入（patch/rsem/stack/folder，F11 Input-3）
│   ├── viewmodel.py         #   RecipeModel（Qt-free，可 headless 測；含 edges）
│   ├── canvas.py            #   節點畫布（n8n 式；F7-6，純 UI，引擎零改動）
│   ├── results.py           #   Results 視窗：直方圖 + Gallery + 整批入口（F7-5）
│   ├── region_check.py      #   區域跨顆檢視：框畫在 N 顆縮圖上（F7-11）
│   ├── template_dialog.py   #   從大圖疊 Golden Cell 模板（F7-12；模板存進 recipe）
│   ├── inspectors.py        #   每張卡自己的儀表（F7-17；依 Step.key 註冊）
│   ├── theme.py widgets.py  #   主題 token + 資料驅動元件 + 自繪圖示
│   ├── gallery.py           #   同屏比多顆（虛擬捲動，撐 10k+）
│   ├── welcome.py           #   首啟導覽 + 範例 recipe 庫對話框
│   ├── workers.py           #   載入/預覽(請求合併)/試跑/寫出 背景執行緒
│   └── studio.py app.py     #   主視窗 + 進入點
├── tests/                   # 2900+ 個測試，全部用合成資料
│   └── fixtures/recipes/    #   e2e 用的最小 recipe（**測試用，不是教學範例**）
├── tools/                   # make_sample(_rsem).py 合成資料；離線安裝三件套：
│                            #   fetch_wheels.py（有網路的機器抓）→ install_offline.py
│                            #   （air-gapped 機器裝）→ doctor.py（環境自檢）
├── fab_probe/               # 廠內格式探測腳本（stdlib-only、純文字輸出）
├── docs/plans/              # 進行中的開發計畫（F0 = master plan、F8）
└── docs/history/            # 封存：按月的 SESSION_LOG、做完的計畫書（**不進搬運包**）
```

> **`examples/` 不見了不是漏掉的。** 2026-08-16 使用者定調「範例 recipe 都先全部
> 拿掉」，整個目錄移除；連帶「用範例資料試一次」與「Templates…」兩個入口
> 也收起來了（`ui/scope.py` 的 `SHOW_SAMPLE_ENTRIES`）。要放回去：JSON 丟回
> `examples/recipes/`、常數改 `True`。加卡片時**不必**再同步維護五份範例。
>
> **出貨的 recipe 現在住在 [`recipes/`](../recipes/)**（2026-08-26），走
> `Open recipe…` 而不是範本庫。跟舊的 `examples/` 差一件事，而那件事就是它們
> 爛掉的原因：`tests/test_shipped_recipes.py` 會**真的把每一份跑一次**
> （載得進來、`validate` 沒有 error、線在該在的埠上、跑得出它承諾的那幾類）。
> 加一份新的就在那支測試裡加一段。
