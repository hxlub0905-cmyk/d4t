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

### 特徵的身分：名字是字串，結構是宣告（F45，2026-08-28）

特徵仍然是**扁平的全域命名空間**（名字 → 數字）：名字是分數表達式的變數、
CSV 的欄名、KLARF 寫回的來源 —— **一個位元組都不改**，這一條是鐵測試守的
（`tests/test_feature_specs.py` 的字面快照）。

改變的是：每個名字**在誕生的地方**多了一份結構化身分 ——
`FeatureSpec`（`pipeline/step.py`）：這個名字屬於哪張卡（`card`）、哪條流
（`stream`）、哪個區域與角色（`region` / `region_role`）、使用者取的前綴
（`own`）、是哪個統計量（`metric`）、比的是哪個統計量（`stat`）、以及名字裡
真正存在的變體後綴（`variant`：nm/nm2 孿生、each-box 的
typical/outlier/outlier_box、引擎的 missing/raw、撞名救援的 rescued）。

- **唯一產地是 `Step.resolve_feature_specs`**：組名字的那個迴圈同時宣告身分
  （`MultiSourceStep` 一個雙迴圈），`resolve_features` 與 `feature_parts`
  都是它的投影 —— 拆與合只有一個家。
- **UI 不拆字串猜語意**（總工作單的禁令，PR-3 之後不准存在）：結果表的
  卡→區域→統計量分組、雙層表頭、維度過濾、特徵表的說明與上下標、
  region check 的定位旗標，讀的全部是 spec。沒有 spec 的名字照原樣顯示、
  說明留白 —— 少一點資訊，不會是錯的資訊。
- `verdict_features.bound_specs` 把 spec 綁上節點 id（route 上第一個產出者
  贏，跟引擎的撞名語意一致），是顯示層「這個數字是誰的」的唯一出處。

### 判定可以重放：`verdict_trace`（F45）

「這顆為什麼判 NG」是一支純函式：
`verdict_trace(recipe, route, features) → Trace`
（`pipeline/verdict_trace.py`）。吃批次列的 features dict（引擎在判定後
快照，let 值都在），重放出帶實值的算式（`valued_text`，pos 定位替換）、
逐步的路徑與每一步缺了什麼、落在哪片葉子。三條立身規矩：**不重算任何值**
（SAFE 語意因此不可能跟引擎不一致）、**有 `scale` 的 let 不重放**（鏡射
`batch.redecide` 丟掉 scale let 的規則）、**缺值明白標名字**（答「否」照走，
F30）。樹的走訪跟引擎是**同一支** `decide_tree.walk_steps` —— 重放出的路
不可能跟引擎走的漂移。Studio 的回溯面板（`ui/why_panel.py`）與 Preview 的
Path 行都建在它上面。

---

## 目錄結構

⚠ **這一段有測試守著**（`tests/test_doc_file_tree.py`）：下面每一個條目要真的存在，
而 `d4t/` 底下每一支模組都要在下面被提到。以前沒有 —— 於是它漂到把 `tests/`、
`tools/`、`docs/` 畫成 `d4t/` 的**子目錄**（它們是同層），還漏掉了近一個月新增的
十幾支模組。加一支新模組就在這裡加一行，那支測試會提醒你。

### repo 根

```
<repo>/
├── d4t/                      # 套件本體（下一段展開）
├── tests/                    # 179 個測試檔、2,700+ 支 test function，全部用合成資料
│   ├── conftest.py           #   （根目錄另有一份 conftest.py —— 那份負責 sys.path）
│   ├── region_cards.py       #   測試共用的小工具（不是測試檔）
│   └── fixtures/
│       ├── recipes/          #     e2e 用的最小 recipe（**測試用，不是教學範例**）
│       ├── golden/           #     黃金值三份，`tools/freeze_golden.py` 產與驗
│       └── sample_real.klarf #     遮蔽過的 KLARF 結構樣本（鐵則 8：值遮蔽、結構保留）
├── recipes/                  # **出貨的 recipe**：走 `Open recipe…`，不走範本庫
│                             #   每一份都被 `tests/test_shipped_recipes.py` 真的跑一次
├── tools/                    # 開發／搬運／診斷腳本（bootstrap 那幾支 stdlib-only）
├── fab_probe/                # 廠內格式探測腳本（stdlib-only、純文字輸出、單檔可貼）
├── bundle/
│   └── d4t_bundle.py         #   整個 repo 打成的單檔純文字包 —— 公司機拿程式碼的唯一路徑
│                             #   **不要改名**（`docs/NO-GIT-SETUP.md` 寫著這個檔名，
│                             #   而那台機器不能跑 git）
├── docs/                     # 文件（下一段展開）
├── .github/workflows/ci.yml  # CI
├── conftest.py               # 讓 `pytest` 在 repo 根跑得起來
├── pyproject.toml            # 套件中繼資料；`gui` extra ＝ PySide6（CLI 那條路不需要 Qt）
├── requirements.txt          # 開發環境（含 PySide6 —— 跟 pyproject 的用途不一樣）
├── LICENSE                   # **專有／內部使用**（2026-08-28 定案）—— 條款與來由見 `docs/LICENSING.md`
├── README.md                 # 對外的第一頁
├── AGENTS.md                 # 環境限制（兩台機器、剪貼簿是唯一通道）—— **動手前先讀**
├── CLAUDE.md                 # 開發手冊（每個 session 都會被讀進去）
└── SESSION_LOG.md            # 逐輪決策（近期；舊的按月封存進 `docs/history/`）
```

**`bundle/` 與 `docs/history/` 不進搬運包。** 唯一出處是
`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 直接 import 它
（兩份定義會漂，一份不會）。

### `d4t/` 套件

```
d4t/
├── __main__.py               # CLI：run / steps / validate / runs / rescore / export / gui
├── core/                     # 純運算，**禁止任何 Qt import**（`tests/test_no_qt.py` 守門）
│   ├── ingest/               # 讀進來：KLARF、TIFF、影像檔、掛在 lot 上的第二份資料
│   │   ├── klarf_core.py     #   KLARF 1.2/1.8 無損讀寫引擎（vendored from KLIP，最重要的資產）
│   │   ├── tiff_index.py     #   免解碼 TIFF/BigTIFF 盤點 ＋ tifffile 讀 page
│   │   ├── imageio.py        #   CJK-safe 影像讀寫（`np.fromfile` ＋ `cv2.imdecode`）
│   │   ├── dataset.py        #   四種 source → 統一的 `DefectItem` 清單
│   │   ├── pair_source.py    #   **另一份 lot** 掛上來（`Dataset.sources[代號]`，F15）
│   │   └── glas_export.py    #   GLAS 匯出（`<id>_label.png`）掛上來 → 一條影像流
│   ├── algo/                 # 純 numpy/cv2 數學（卡片包這些，**不要在卡片裡重寫數學**）
│   │   ├── align.py normalize.py histmatch.py       #   對位／正規化／直方圖匹配
│   │   ├── enhance.py curve.py                      #   局部對比、去背景、去噪；tone curve 求值
│   │   ├── glv.py snr.py quality.py                 #   GLV metric bank／SNR 正負號正典／對焦指標
│   │   ├── edge.py subpixel.py shape.py profile.py  #   CD 的四塊：剖面、次像素、團塊、投影
│   │   ├── grid.py mask.py roi.py                   #   條紋→框／label map→框／MultiROISet
│   │   ├── period.py golden.py template.py          #   週期估測／Golden Cell 疊圖／模板定位
│   │   └── pairing.py                               #   兩批 defect 的座標配對（容差內、一對一）
│   ├── pipeline/             # 引擎
│   │   ├── context.py        #   Context（images／features／regions／meta）—— 步驟間的唯一介面
│   │   ├── step.py           #   Step 介面 ＋ ParamSpec ＋ registry ＋ `GROUP_ORDER`（七段的唯一出處）
│   │   ├── recipe.py         #   Recipe(DAG) ＋ lint 式 validate ＋ 版本遷移
│   │   ├── expression.py     #   score 表達式引擎（自寫 parser，**不用 eval**）
│   │   ├── decide_tree.py    #   判定樹怎麼走 —— 引擎與 UI 共用同一支
│   │   ├── verdict_features.py verdict_trace.py  #   判定問了哪幾個數字／重放一顆的判定（F45）
│   │   ├── engine.py batch.py cache.py  #   單顆執行／ProcessPool 批次／影像段 checkpoint 快取
│   │   ├── channels.py       #   這一顆的第幾張圖 → 叫什麼流名
│   │   ├── cellrois.py       #   標在 Golden Cell 上的具名區域（一個名字、好幾個矩形）
│   │   └── curve.py          #   tone curve 控制點的字串編碼（parse／format）
│   ├── steps/                # 步驟卡片 —— **註冊 19 張，卡片庫可見 18 張**（`align` 收起來）
│   │                         #   ⚠ 卡片庫由上而下的順序 ＝ `__init__.py` 的 import 順序
│   │   ├── load.py           #   load_patch／load_single（**一種 source 一張卡**）
│   │   ├── load_sidecar.py pair_source.py               #   別的程式產的圖／另一份 lot 的那一顆
│   │   ├── normalize.py tone.py denoise.py flatten.py   #   Enhance 段
│   │   ├── align.py arith.py align_to.py                #   Compare 段（`align` 目前收起來）
│   │   ├── roi_reference.py roi_mask.py                 #   Region 段：四種找法 → 具名區域／區域 → mask 流
│   │   ├── roi_cross.py roi_template.py  #   ⚠ **不是卡片**：折進 `roi_reference` 的兩個 method（F30）
│   │   ├── glv_stats.py cd.py quality.py #   Measure 段：GLV → CD → Focus index（**順序有意義**）
│   │   ├── output.py         #   Output 段三張：output_report／output_klarf／output_char
│   │   └── _util.py          #   卡片共用小工具（不註冊任何 step）
│   ├── export/               # 寫出去
│   │   ├── klarf_out.py      #   KLARF 三種寫回模式：inplace／annotate／topn
│   │   ├── report.py html.py boxplot.py  #   CSV／Excel／HTML 報表／box plot（手寫 SVG，零新相依）
│   │   └── overlay.py        #   缺陷疊圖：把「機器看到什麼」畫成人看得懂的圖
│   ├── store/results.py      # SQLite 批次歷史 ＋ rescore
│   └── calibration.py        # nm/px 校正 profile
└── ui/                       # PySide6 Studio（**唯一允許 Qt 的地方**）
    ├── scope.py              #   產品範圍開關：支援哪些輸入、哪些卡片收起來、入口長什麼樣
    ├── viewmodel.py          #   RecipeModel（Qt-free、可 headless 測；含 edges）
    ├── studio.py app.py      #   主視窗（**只做接線**）＋ 進入點
    ├── canvas.py             #   節點畫布（n8n 式；純 UI，引擎零改動）
    ├── cell_canvas.py        #   一格 cell 鋪成一片，區域的框畫在上面、拖得動
    ├── tree_scene.py tree_panel.py     #   判定樹住在畫布上／點一步就編輯那一步（F24）
    ├── decide_panel.py route_panel.py route_badge.py  #   判定段編輯器／`route_by` 編輯器與徽章
    ├── verdict_band.py       #   判定段的橫幅（一列一類）
    │                         #   ⚠ 這裡以前還有 output_band.py（Output 段的虛線框），
    │                         #     F50 拿掉了：「整批跑一次」變成卡片自己的一條腳帶
    ├── threshold_view.py     #   在挑門檻，就要看得到分布
    ├── results.py results_table.py why_panel.py  #   Results 視窗／結果表／三次點擊回溯（F45）
    ├── gallery.py region_check.py      #   縮圖網格（虛擬捲動，撐 10k+）／區域畫在很多顆上
    ├── inspectors.py         #   每張卡自己的儀表（依 `Step.key` 註冊）
    ├── template_dialog.py    #   從大圖疊 Golden Cell 模板（模板存進 recipe）
    ├── gc_generator.py       #   **反過來**：貼一張 GC 進來，鋪成整批擬真資料（F60）
    │                         #     `python -m d4t simgen`；只做介面，邏輯在
    │                         #     `tools/make_lot_from_gc.py`
    ├── welcome.py            #   首啟導覽 ＋ 範例 recipe 庫對話框（兩個入口目前收起來）
    ├── workers.py            #   載入／預覽（請求合併）／試跑／寫出 背景執行緒
    ├── theme.py widgets.py branding.py region_words.py  #   主題 token／資料驅動元件／圖示字標／
    │                         #   區域那三個埠的白話字
    ├── numbers.py            #   一個特徵值印成字 —— **全 UI 只有這一支**（F52）
    └── assets/               #   `d4t.svg` 與兩份字標（pyproject 的 package-data 帶著它們走）
```

⚠ **新的 UI 面板一律開新模組**，不要塞進 `studio.py`（6,000 行以上）——
`studio.py` 留給接線，不留給內容。理由與現況見 [`../CLAUDE.md`](../CLAUDE.md) §4。

### `docs/`

```
docs/
├── ARCHITECTURE.md           # 這一份 —— 架構的唯一出處
├── LICENSING.md              # 授權與來源：d4t 自己的授權狀態、vendoring 來源、第三方相依
├── ROADMAP.md                # 進度與 phase 計畫
├── PITFALLS.md               # 已知的坑（只增不減）
├── HANDOVER.md               # 為什麼長成這樣：需求訪談結論、六個來源專案的脈絡
├── FAB-VALIDATION.md         # 廠內待驗證的假設
├── GLAS-INTERFACE.md         # 上游 GLAS 的介面契約（d4t 不解析 layout）
├── USING-CD.md               # 給使用者：CD 那張卡每一格什麼時候動
├── USING-CHARACTERIZATION.md # 給使用者：EBI ↔ API characterization 怎麼做
├── NO-GIT-SETUP.md           # 受限機器：怎麼把程式碼弄上去
├── OFFLINE-INSTALL.md        # 受限機器：怎麼離線裝相依套件
├── plans/                    # **進行中**的計畫書（`F0-master-plan.md` 是總表）
└── history/                  # 封存（**不進搬運包**）：按月的 SESSION_LOG、做完的計畫書
```

---

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
