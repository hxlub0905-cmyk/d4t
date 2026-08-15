# CLAUDE.md — ADEPT 開發指南

給 Claude Code / 開發者的專案脈絡（操作手冊）。
**每次 session 結束請更新 `SESSION_LOG.md`。**

> **第一次接手這個專案？三份文件，先讀前兩份。**
>
> - **[`AGENTS.md`](AGENTS.md) —— 環境。** 開發在家用機、執行在公司機，兩台的
>   限制正好互補：**有真實資料的那一台不能裝 git、目前什麼都下載不了**，
>   唯一的傳輸通道是「在 GitHub 上看到檔案、按複製鈕」。不知道這些的話，很多
>   設計看起來是多餘的然後就會被「順手簡化」掉 —— 為什麼 `tools/` 全是
>   stdlib-only、為什麼有 `FILELIST.txt`、為什麼有 `bundle/`。
> - **[`docs/HANDOVER.md`](docs/HANDOVER.md) —— 為什麼長成這樣。** 工具的由來與
>   目的、需求訪談的結論與理由、六個來源專案各給了什麼（那份跨專案脈絡不在
>   程式碼裡）、哪些事已驗證哪些還是假設、哪些設計「看起來可以隨便改但其實有
>   理由」。
> - **這份 CLAUDE.md —— 怎麼動手。**

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

## 2.5 資料模型：兩個通道（影像流 vs 具名區域）

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
│   ├── region_check.py      #   區域跨顆檢視：框畫在 N 顆縮圖上（F7-11）
│   ├── template_dialog.py   #   從大圖疊 Golden Cell 模板（F7-12；模板存進 recipe）
│   ├── inspectors.py        #   每張卡自己的儀表（F7-17；依 Step.key 註冊）
│   ├── theme.py widgets.py  #   主題 token + 資料驅動元件 + 自繪圖示
│   ├── gallery.py           #   同屏比多顆（虛擬捲動，撐 10k+）
│   ├── welcome.py           #   首啟導覽 + 範例 recipe 庫對話框
│   ├── export_dialog.py     #   輸出精靈（寫回前一定先預覽變更）
│   ├── workers.py           #   載入/預覽(請求合併)/試跑 背景執行緒
│   └── studio.py app.py     #   主視窗 + 進入點
├── tests/                   # 1200+ 個測試，全部用合成資料（見 §6 的「測試要跑多久」）
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
   6.5 **`adept/ui/` 底下的字一律英文**（`tests/test_ui_english_only.py` 鎖住）。
   **CLI（`adept/__main__.py`）刻意是中文，這不是漏掉的。** 兩者的讀者不同：
   Studio 要給廠內的製程/設備工程師用（推廣鐵則），而 CLI 是開發與除錯的入口，
   讀者就是維護這個專案的人。要改成英文請先改掉這一條，不要因為「看起來不一致」
   就順手統一 —— 那會讓 Studio 的英文變成一個沒有理由的慣例。
7. **單顆 defect 出錯不得殺掉整批**（`run_defect` 從不 raise，回 `ok=False`）。
8. **repo 裡不得有未遮蔽的廠內識別碼**（Lot／Wafer／機台／device／recipe 名稱／
   廠區代號／缺陷分類名稱）。測試 fixture 也一樣 —— 它們斷言的是**結構**，
   值遮蔽掉一條測試都不會壞。`tests/test_no_real_fab_data.py` 會擋。

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

> **一張 Input 卡就是宣告 `accepts_kinds`**（F9 Phase 3d）。它是 pipeline 的
> 起點：引擎拿 `dataset.kind` 來對，決定從哪一張卡開始跑。非 Input 卡不要碰
> 這個屬性。**一種資料型別一張卡** —— 別再讓一張卡「依資料長相決定吐什麼」，
> 那會讓埠在編譯期與執行期不同調（見 §7 那一列）。

> **不准就地改寫接進來的影像流**（F9 Phase 3d）。`ctx.images` 裡的陣列是
> **唯讀**的 —— 分岔的兩條分支共用同一塊記憶體，就地改一個另一邊就髒了。
> 算一張新的 `set_image` 回去（本來就該這樣寫），要改也先 `.copy()`。
> 犯規會當場丟 `ValueError`，不會等到有人接了一條分支才發現。

> **一張卡是一次處理，寫出去的正好等於接進來的**（F7-19／F7-20）。Enhance 卡
> 繼承 `MultiStreamStep`（`steps/_util.py`）：吃 `streams`（一串影像流）、
> 只實作 `build_op` 回一個 `img -> img`，迴圈交給基底。接 test 也接 ref，
> 兩條就吃**同一組設定** —— 那正是「兩張圖還比得起來」的前提。
> 要讓兩條流吃**不同**設定才放兩張卡。
>
> 真正的不變量是**畫布不能說謊**：卡片動到的每一條流，畫面上都要有一條線。
> （F7-18 的「一張卡一條流」是當時達成它的手段，不是不變量本身 —— 見計畫書
> §23.1。`also_apply` 那種「藏在控制列的第二條流」仍然不准回來。）
> 需要「借另一條流的資訊」時，那件事要有自己的參數（例：`normalize` 的
> `range_from`），型別是 `image_key` —— 它在畫布上就是第二條接進來的線。

> **同一個家族的做法收成一張卡的 `method`**（F7-10／F7-20）。四種正規化、
> 五種去背景、四種去雜訊各是一張卡的下拉，不是十三張卡 —— 卡片庫多一列，
> 使用者就要多讀一段說明才知道該用哪一個。**方法相依的參數用
> `ParamSpec.show_when`**（例 `show_when=("method", ("percentile",))`），
> 不要在 help 裡寫「（這個方法用不到）」那種道歉。
> 注意 `show_when` 是**顯示**規則不是驗證規則：藏起來的參數照樣有預設值，
> 卡片自己要保證用不到的參數不影響結果（`resolve_reads` 也一樣）。
> 但**「可以同時做」的東西不要做成四選一** —— `tone` 的亮度／gamma／反相是
> 幾個預設不作用的旋鈕，因為使用者常常要一起用。

> **參數名是 recipe 的鍵，不是給人看的字**（F7-9）。`ParamSpec` 有選填的
> `label`：有就顯示 label，沒有就顯示 `name`。`range_from` 對製程工程師不是
> 一句話，`Borrow range from` 才是。同理，「一串影像流」請用 `type="image_keys"`
> 而不是 `str` —— 值的格式一樣（逗號分隔字串），但 UI 會給上游每一條流一個
> 勾選框，使用者不必猜能填什麼，也不會打錯字。

> **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。ParamForm 看到有上下界的
> `int`/`float` 就自動配一支跟數字框雙向綁定的滑桿。這不只是好看 ——
> 使用者是一邊拖一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。
> `type="curve"` 則會拿到一張可以自己拉的色調曲線編輯器（見 `pipeline/curve.py`）。
> `type="expr"`（F9 Phase 3d）拿到的是「算式框 + Insert feature ▾」，下拉裡列的是
> **這張卡上游真的量得出來的**特徵名。**能列出來的東西就不要讓人用打的** ——
> 判定卡的變數名是上游的卡自己取的，憑記憶打字最常見的下場不是「打不出來」而是
> **打錯一個字**：lint 只出一句 warning、整批照樣跑得完，而每一顆都沒有分數。

---

## 6. 開發流程

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt && pip install pytest

QT_QPA_PLATFORM=offscreen pytest -q tests/test_xxx.py   # ← 平常就跑這個
python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
python -m adept gui                                # 開 Studio
python -m adept run examples/recipes/cross_regions.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
```

### 測試要跑多久（**規則，不是建議**）

| 情況 | 指令 | 實測 |
|---|---|---|
| 開發迴圈 | `pytest -q tests/test_<改到的>.py` | 秒級 |
| 沒把握改到什麼 | `python tools/run_tests.py --fast` | **~47 秒** |
| commit 前 | `python tools/run_tests.py` | **~2.5 分鐘** |
| CI | `pytest -q`（`.github/workflows/ci.yml`，三個 Python 版本） | 十幾分鐘 |

> **絕對不要在雲端 session 裡跑 `pytest -q` 全套。** 實測（2026-08-15，同一台
> 容器、同一套測試）：
>
> | 跑法 | 時間 |
> |---|---|
> | `pytest -q`（一個行程跑完全部） | **> 11 分鐘** |
> | 每個檔案各自一個行程（`tools/run_tests.py`） | **148 秒** |
> | 只算 25 支 UI 測試檔，一個行程 | **> 10 分鐘** |
> | 同樣那 25 支，各自一個行程 | **101 秒** |
>
> 差距在 Qt：一個行程裡，前面每一支 UI 測試建立的 `QWidget` 都還掛在同一個
> `QApplication` 底下（Qt 物件不會因為測試結束就消失），所以後面每開一個視窗
> 都要跟愈來愈多的殘留物一起做版面計算 —— 時間是**超線性**的。行程結束就全部
> 歸零，所以分開跑不只是平行，是把那個累積整個拿掉。
>
> 以前這裡寫「全套 ~30s，雲端要好幾分鐘，commit 前跑一次就好」。那個建議在
> 雲端 session 裡的實際後果是**一次十一分鐘、期間什麼都推不動**，而且它是
> 每一輪都會再發生一次的成本。

`tools/run_tests.py` 是 stdlib-only 的單檔（跟 `tools/` 其他腳本同一條規矩），
會印出最慢的幾個檔案，紅了就把那個檔案的完整輸出貼出來。

`pytest -q -m "not slow"` 也可以（marker 由 `tests/conftest.py` **依檔名自動
套用**，新增 UI 測試檔不必記得標）。但它仍然是一個行程，所以只在你確定不會
碰到 UI 時才比較快 —— 一般情況直接用 `run_tests.py --fast`。

⚠ `slow` 篩掉的是**慢**，不是**不重要**。CI 跑不加參數的全套，因為
「在同一個行程裡跑也要能過」本身是一條性質（測試之間不該互相汙染）。
`--fast` 綠了不等於可以 commit。

**每次改完之後**（**在家用機上** —— 公司機不能執行 git 操作）要重產公司機拿得到
的那兩樣東西。順序是 `git add` 之後才跑，因為它們讀的是 `git ls-files`：

```bash
git add -A && python tools/release.py && git add -A
```

哪一支工具在哪一台機器跑，見 [`AGENTS.md`](AGENTS.md) §4.5。

`tests/test_offline_tools.py` 會擋住那份清單腐爛 —— 忘了跑的話，那個檔案在
「下載被擋、只能用剪貼簿搬」的機器上會**安靜地少掉**（見 §9.5 與 `AGENTS.md`）。

想要**看得懂的**純文字版（六批，記事本讀得到每個檔案）才另外產 ——
它每次更新會動到 2.4 MB，所以不固定放在 repo 裡：

```bash
python tools/make_text_bundle.py --out bundle/ADEPT.py --split 400
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
| **中心框幾何與影像尺寸綁死**（F7-4 已修） | 同一組 `glv_stats` 參數在 128² patch 上準、在 256² RSEM 上漏抓（缺陷散佈超出框） | **幾何已從量測卡搬到 Region 卡**，量測卡只引用 ROI 名字。ROI 一律存 0–1 比例座標，所以同一份 recipe 換 patch 尺寸不會失效。（當時的 `roi_define` 卡已於 F8 第五輪隨 ROI 收斂被拿掉，現在的 Region 卡是 `roi_cross` / `roi_template`；比例座標這條性質沒有變，迴歸測試在 `tests/test_roi_cross.py` 與 `tests/test_roi.py`）|
| **pytest 收集期 import Qt** | `test_no_qt_after_import` 失敗 | UI 測試一律 **lazy import**（在 fixture 內 import 並注入 globals） |
| **`QGraphicsItem` 拖曳留殘影**（F7-8 已修） | 拖動節點時埠標籤（"test"/"ref"）的舊位置沒被清掉 | `boundingRect()` **必須涵蓋所有畫得出去的東西**。埠標籤畫在節點右緣之外，之前只算到 `NODE_W + _PORT_R`，Qt 就只重繪那個範圍 |
| **在節點外面畫東西**（F7-8／F7-9／F7-14 同一條） | 拖動節點留殘影 | `boundingRect()` 必須涵蓋**所有畫得出去的東西** —— 埠標籤（F7-8）、埠圓點（F7-9）、輸出埠的 `+`（F7-14）都在節點右緣之外。加任何畫在卡片外的裝飾時，先把 `boundingRect` 加寬，`tests/test_ui_f7_14_canvas_flow.py` 會斷言 `+` 的中心在 `boundingRect` 裡 |
| **`paint()` 用場景座標**（F7-9 已修） | 殘影**又**出現；而且「新增的節點只有左邊有圓框，右邊沒有」 | 兩個症狀同一個因：`paint()` 拿 `out_anchors()`（**場景**座標）去畫本地座標的東西。節點在原點看起來正常（第一欄的 Input 剛好在那）；一離開原點就畫到「兩倍位移」的位置。現在分成 `out_anchors_local()`（繪製／命中）與 `out_anchors()`（連線）。F7-8 只放大了 `boundingRect`，那是對症狀動刀 —— 真正的不變量是**畫的座標系＝宣告的座標系**，`tests/test_ui_f7_9_feedback.py` 直接鎖它 |
| **`test_no_qt_after_import` 跟檔名字母序有關**（F7-9 已修） | 新增一支 UI 測試檔就讓它失敗，而且失敗訊息指不到真正的原因 | 它以前在測試行程裡看 `sys.modules`，所以任何排在 `test_no_qt.py` **之前**的 UI 測試檔跑過 fixture 之後就會誤報。改成在乾淨的子行程裡 import core 再問 —— 那本來就是這條測試唯一想問的事 |
| **快取只存了 Context 的一部分**（F7-9 已修） | 同一份 recipe **第一次跑對、第二次跑錯**（`region 'main' is not defined`） | checkpoint 是執行順序上的**位置**（最後一張影像段卡的下一格），不是「所有影像段的卡」，所以夾在中間的 Region 卡（algo）會落在快取段裡。v1 快照只存 images/features/meta，`ctx.rois` 命中時整個不見。快照現在涵蓋 `rois` 與 `labels`，並帶 `FORMAT_VERSION`（版本不合一律當 miss，舊快取目錄不會餵回殘缺快照）。迴歸測試 `tests/test_batch_cache.py::test_named_rois_survive_a_cache_hit` |
| **特徵是扁平的全域命名空間**（F7-11 已解） | 兩張同型別的量測卡（例：量兩個 ROI 的 `glv_stats`）都寫 `glv_mean`，後面那張**安靜地蓋掉**前面那張，分數表達式指不到前面那個值 | 量測卡有 `output_prefix`（Studio 挑了區域會自動填成區域名），撞名時 `validate()` 仍會出 `feature-collision` warning、Studio 跑完在狀態列講出來 |
| **量測卡指到沒人定義的 ROI**（F7-9 已修） | `cd_measure` 當時預設 `roi="blob"`，少了上游 Blob 卡時**安靜地改量整張圖** —— 跑得完、有數字、而且是錯的 | 具名區域現在跟影像流走同一條檢查：`Step.resolve_regions_in/out()` + `validate()` 的 `unknown-region`；退回整張圖時會 `ctx.warn`。（量測卡的 `roi` 預設值已改成空字串 = 明確地「量整張圖」，不再預設指向一個要靠別張卡產生的名字）Studio 也在試跑前先跑 lint（以前完全沒跑，於是接錯的卡片會「跑完 200 顆、每顆都失敗」） |
| **色調曲線用自然三次樣條** | 使用者把中間點往上拉，影像出現一圈**不存在的暗環** | 樣條會 overshoot。`algo/curve.py` 用保單調三次 Hermite（Fritsch–Carlson）。這是演算法自己造出來的假缺陷 —— 對判 defect 的工具是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住 |
| **每讀一張圖就重開整個 TIFF**（2026-07-31 已修） | 「換下一顆 defect」明顯卡頓，而整條 pipeline 明明只要 9 ms | `read_page` 以前每次都 `with tifffile.TiffFile(path)` 開一次檔，而且用 `len(tf.pages)` 檢查範圍 —— **那一行會強迫走完整條 IFD 鏈**。4000 頁的 TIFF 每張圖 16 ms，而圖本身只有 16 KB。改成快取開好的 handle（版本鍵 = `(pid, mtime, size)`），換一顆 32 ms → 0.4 ms。同理 `load_dataset` 只要「幾頁」卻呼叫會解析所有 tag 的 `read_tiff_pages`，改用 `count_pages` 後 117 ms → 19 ms |
| **fork 出來的子行程共用檔案偏移量**（同上一輪一起處理） | 批次某幾顆拿到別頁的影像 —— 不丟例外、不變慢，只是錯 | fork 複製的 fd **共用同一個 offset**，四個 worker 各自 seek+read 會互相把位置移掉。所以 TIFF handle 的快取鍵含 `os.getpid()`：子行程一進來就發現「這不是我的」而重開。`tests/test_tiff_index.py` 真的 fork 一個子行程去驗 |
| **快取住的 TIFF handle 被兩個執行緒共用**（2026-07-31 已修） | 預覽**偶爾**失敗、訊息是 tifffile 的 `suspicious number of tags 13111`；單獨跑那條測試 6 次過 5 次 | 一個 `TiffFile` 底下就是一個 fd，讀一頁像素是「seek 過去、讀下來」。Studio 點一張卡會排一次背景預覽，同步預覽又跑一次，兩個執行緒交錯 seek 就把對方的位置移掉 —— tifffile 把像素當 IFD 解析。`read_page` 現在**全程持有 RLock**（拿 handle 到 `asarray()` 回來）。另外開檔時就 `len(tf.pages)` 把頁面清單建好：tifffile 的 lazy 解析依賴「檔案位置停在上一頁結尾」，而 `asarray()` 會移動它，所以**同一個 handle 讀完第 0 頁再要第 1 頁必失敗**。跟 fork 那條是同一件事的兩半 —— 子行程共用偏移量、執行緒共用 handle |
| **兩台機器版本不同步時，訊息會誤導**（2026-07-31 已修） | 新版存的 recipe 在舊版打開，只說 `unknown parameters: ['…']` —— 使用者的結論是「這份檔案壞了」，於是去重做一份 recipe，而該做的是更新程式 | recipe 存檔時寫 `app_version`；`recipe.version_skew()` 判斷「這份檔案比這個程式新」，並把那句話接在 `bad-param` / `unknown-step` 的訊息後面，載入的當下也在狀態列講一次。**公司機是用複製檔案更新的（`AGENTS.md`），所以版本不同步是常態不是意外** |
| **`isVisible()` 在 show 之前恆為 False** | 「這個面板收起來了嗎」在建構期永遠答錯 | 一律追明確狀態（`LibraryPanel.panel_open()`、`StudioWindow.compare_enabled()`、`_progress_on`），不要問 widget |
| **`drawPolygon` 傳散的 `QPointF`**（F7-17） | 整個行程 **segfault**（不是丟例外，所以看不到任何訊息，只有 exit 139） | PySide6 會綁到別的 overload。要傳 `QPolygonF([...])`。自繪面板加任何多邊形時注意 |
| **暗色盤裡的佔位字串**（F7-17 已清） | `accent_border` 的值是 `"#2f4straight"`，靠 70 行後的一句覆寫救著 | Qt 對無效色字串是**靜靜畫成黑色**，不會報錯。色盤裡不要留「稍後修正」的值；`tests/` 有一條掃描所有 token 是否為合法 hex |
| **`_update_action_states` 會蓋掉 tooltip**（F7-16 已修） | 把快捷鍵寫進工具列 tooltip，第一次 refresh 之後就不見了 | 那幾顆的 tooltip 每次 refresh 都會依前置條件重寫（「還沒有東西可以存」）。所以不能「建構時附加一次」，要讓**設 tooltip 的那個動作自己補上快捷鍵**（`_set_tip`）。`test_ui_f7_16_safety_net.py` 會 refresh 一次再驗 |
| **Qt 的 Enter/Leave 在父子之間會打架**（F7-15 已修） | 滑鼠從參數列的空白處移進**那一列自己的**輸入框，說明就閃一下（收起來又立刻攤開） | Qt 先送 `Leave` 給父元件、再送 `Enter` 給子元件。照字面處理必閃。`leaveEvent` 改成直接問**游標還在不在自己的矩形裡**（`rect().contains(mapFromGlobal(QCursor.pos()))`），不要相信事件的字面意思。（2026-08-14 起參數列的 hover 攤開整個拿掉了 —— 修好之後它還是「跟著滑鼠閃」，使用者實測嫌亂；說明搬進 tooltip。教訓本身仍適用於其他 hover 元件） |
| **`:focus` 被 id / attribute 選擇器安靜蓋掉**（F7-23 已修） | Tab 到「Run trial」「Stop」或任何一顆工具列按鈕，畫面上零回饋 —— 而 QSS 裡明明有 `QPushButton:focus` | QSS 照 CSS2 特異性：`QPushButton#primary`（id）贏過 `QPushButton:focus`，`[variant="…"]` 同分但寫在後面也贏，於是那條總括規則只對「沒有 objectName 也沒有 variant」的按鈕生效；工具列更單純 —— 從頭到尾沒有 `QToolButton:focus`。**每一種變體都要有自己的一條 `:focus`**。另外 **Qt 的 `outline` 對按鈕不生效**（收下屬性但什麼都不畫，加不加 `outline-offset` 都一樣），框只能用 border 畫在裡面 —— 那就會吃掉 1px，必須從自己的 padding 還回去，否則 Tab 過去文字會跳一格。`tests/test_ui_f7_23_buttons.py` 對八種按鈕逐一量畫素，並用 `contentsRect()` 鎖住「文字不准移動」|
| **`contentsRect()` 的原點永遠是 (0, 0)**（F7-23 第四輪） | 想把圖示畫進 QSS 撐開的那塊 padding 裡，用 `contentsRect()` 定位會畫錯地方 | QSS 樣式下 contentsRect 的**尺寸**確實扣掉了 padding（所以拿它比對「文字區有沒有移動」是對的），但**原點沒有跟著移** —— 它不是一個可以拿來定位的框。要畫在 padding 裡就用 `rect()` |
| **小圖示不能照大圖示的比例縮**（F7-23 第四輪） | 自繪圖示在 22px 下好看，放到按鈕上的 15px 就糊成一團 | 三個實例：`undo` 的弧用 `size/9` 的線變成實心月牙（改 `size/11`）；`fit` 的四個角括號用 0.26 長度兩臂幾乎接起來變成矩形（改 0.17）；`tidy` 的 2×2 描邊方格線比空隙還粗（改實心）。**加新圖示時用實際尺寸（≤15px）看過再收工** —— `tests/test_ui_f7_23_buttons.py` 只擋得住「畫出來是空的」|
| **Qt 不會把超出範圍的 `border-radius` 夾回去**（F7-23 第三輪抓到） | 一個叫 `radius_pill` 的 token 畫出來是**方角**，而且不報錯 | CSS 的慣用寫法是 `border-radius: 999px`（讓瀏覽器自己夾到半高）。**Qt 不夾，它直接放棄圓角畫矩形** —— 實測 999px 的左緣輪廓與 0px 逐列相同。所以圓角值必須**已經在範圍內**（chip 高 22px → 11px），而且 chip 的高度改了要跟著改。`tests/test_ui_f7_23_buttons.py::test_the_pill_token_is_actually_round` 量左緣輪廓鎖住它 |
| **搬進 QSS 的 `[property]` 不會自己重畫**（F7-23 第三輪） | `setProperty("active", True)` 之後畫面完全沒反應，也沒有錯誤 | Qt 只是存下那個值，選擇器要等下一次 polish 才重算。用 `widgets.restyle(w)`（`unpolish` + `polish` + `update`）。把 per-widget stylesheet 換成 property 選擇器時這是最容易漏的一步 |
| **`::menu-button` 只要給它一個盒子，箭頭就消失**（F7-23 量出來） | 想幫 `Run trial ▾` 的下拉區補一塊底色把兩個動作分開，補完箭頭不見了 | 跟下一列的 `QComboBox::drop-down` 是同一件事：**背景／邊框／圓角任一**都會讓 Qt 把該 subcontrol 的繪製整個交給 stylesheet，而 stylesheet 沒有 `image` 就什麼都不畫 —— 這個 repo 是純文字的（§9.5）塞不了圖。實測只有 `width` 是安全的。所以這件事不是 QSS 的問題是**結構**的問題：要控制外觀就別用 `MenuButtonPopup`，拆成兩顆真的按鈕。逐項量測表在 `docs/plans/F7-canvas-and-taxonomy.md` §27.5 |
| **QSS 把 subcontrol 的箭頭畫成 0 個畫素**（F7-13 已修） | 下拉選單跟自由文字框**長得一模一樣**，使用者無從得知哪個點得開（`Match on` vs `Name this region`） | `QComboBox::drop-down { border: 0 }` —— styled 的 subcontrol 要**自己提供 `down-arrow` 圖檔**，否則 Qt 什麼都不畫，而這個 repo 是純文字的（§9.5）塞不了圖。拿掉 `border: 0` 讓它留在 base style 上。`tests/test_ui_controls_readable.py` 用畫素數量鎖住（箭頭區 0 → 20，而 QLineEdit 恆為 0） |
| **參數合法 ≠ 設定完成**（F7-13 已修） | 空模板是完全合法的 str，lint 沒話說 —— 但那張卡跑起來**每一顆**都失敗，而使用者是跑完 200 顆才知道 | `Step.configuration_issues(params)`：卡片自己講缺什麼、用**這張卡的話**講（要去按哪顆鈕），變成 lint error `not-configured`，畫布上那張卡右上角掛警示標記。加這種卡時記得：`test_every_visible_card_can_be_wired_up_without_a_dead_end` 會要求訊息**指得出路在哪** |
| **模板比對：分數本身會騙人**（F7-12） | 全白／純雜訊的 patch 對任何模板都能拿到 NCC 0.44（門檻 0.3 → 過關），於是「碰巧」被當成「對得準」，框放到隨機的位置 | **沒有任何分數門檻分得出這兩者**（分數重疊）。要問的是另一個問題：**這張 patch 自己有沒有東西可比**（`min_structure`，實測無結構約 1、有結構 20 以上）。另外 margin 必須**先把比對曲面折回一個週期**再取次高峰，否則相鄰週期的次高峰讓 margin 恆為 0 —— 週期性把自己打敗了 |
| **Golden Cell 的原點會飄**（F7-12） | 同一份 recipe、不同時間建的模板指到不同的地方，而且畫面上完全看不出來 | cell 的第 0 欄預設是大圖上的**任意切點**，換張圖就換了 —— 而使用者是在 cell 上標框的。`algo/template.py::anchor_cell()` 旋轉到**最強的上升邊**在第 0 欄；用最大正梯度而不是 `abs`，否則一個週期的兩個相反邊界會競爭，錨點在兩者之間跳 |
| **`estimate_period` 在純雜訊上會回一個看似合理的週期**（F7-12） | 噪音圖疊出一個沒有意義的模板，然後安靜地拿去對每一顆 | 週期信心門檻 `MIN_PERIOD_CONFIDENCE = 40`（實測噪音 20.3）。「說我做不到」比「給一個沒有意義的答案」好得多。順帶：一維 layout（垂直條紋，只有 X 有週期）以前會被整個放棄 —— 那是最常見的情況，現在兩軸各自判斷，不重複的那軸取整個影像高度／寬度 |
| **KLARF variant D 誤判**（M5 修正） | 真實 1.8 檔（ImageList 欄不在最後、且無 IMAGECOUNT 欄）被 `lint()` 判定每一列都違法，Export 精靈跳紅字 | `row_len_ok` 改用 `effective_row_len()`：把 `Images N { … }` 子區塊折算成一欄。**注意 `image_layout()` 對這個變體仍回 None，而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它**。迴歸測試 `tests/test_klarf_variant_d.py` |
| **一張卡偷偷寫了第二條流**（F7-18 已改） | 畫布上那張 Denoise 畫在 test 那條鏈上，它其實同時改了 ref；而「要不要一起做」藏在控制列的 `also_apply` 勾選框裡，於是 test 是主角、ref 是附帶 | **一張卡一條流**：`resolve_writes` 只回主流。要對 ref 做就再放一張卡接到 ref。需要借另一條流的資訊時給它自己的 `image_key` 參數（`percentile_norm.range_from`），那條線在畫布上看得見。舊 recipe 的 `also_apply` 由 `recipe._migrate_also_apply` 展開成多張卡。**F7-19/F7-20 起改用另一個手段達成同一個不變量**：一張卡吃 N 條流，但每一條都有埠、都有線（見 §5 的框與計畫書 §23.1）—— 不變量是「畫布不能說謊」，不是「一張卡一條流」|
| **拆卡片時的順序陷阱**（F7-18） | `anchor="source"` 拆成兩張卡之後，如果 test 那張先跑，ref 借到的是「已經拉成 0–255」的範圍 —— 數字不一樣，而兩張輸出都是看起來正常的圖 | 借範圍的那幾張要排在**前面**。這類遷移不要讀程式碼驗證：跑同一份 recipe 100 顆，比 `min/median/max` 與 bin 數量是否逐項相同（`tests/test_ui_f7_18_streams_as_nodes.py`）|
| **兩個節點之間只拉得動一條線**（F7-18 已修） | 先從 test 拉、再從 ref 拉，第二條只得到一句 `already connected` 然後什麼都沒發生 —— 使用者的結論是「這張卡不准我碰 ref」 | `edge_added` 帶第三個參數（**這條線從哪個輸出埠出發**），Studio 據此把下游卡的主要輸入指到那條流。同一對節點再拉一條要當成「我改變主意了」處理 |
| **常駐在節點旁邊的裝飾**（F7-18 已清） | 每個輸出埠一顆「+」，十張卡的 pipeline 就有十幾顆加號跟資料流搶畫面 | 入口收回卡片庫；「+」做對的事（接上線、接在對的流上）改由「選著一張卡時從卡片庫加」承接（`add_card_after`）。加完**選取新卡**，連按三張才會長成一條鏈而不是倒過來 |
| **虛線只是實線淡一點** | 「這條是我拉的」與「這條是排列順序帶來的」看起來只差深淺，而深淺會被縮放與主題影響 | 不同語意給不同**色相**（`canvas_edge_implicit`）。測試要鎖兩層：token 的色相差得出來，而且 `paint()` 真的去讀了它（畫進 pixmap 比主色相）|
| **拿掉一張卡，週邊會留下承諾**（2026-08-15 清完） | `blob_segment` 在 F8 第五輪被拿掉，但 Export 精靈上還寫著「the main blob boxed in red」—— 而 `ctx.meta["blobs"]` 與 `blob_*` 特徵**再也沒有人產出**，所以那個紅框永遠畫不出來。使用者勾了、等疊圖跑完、拿到一疊沒有框的圖，畫面上沒有任何東西說明為什麼 | 刪一張卡要**沿著它的產出往下游走一遍**：誰讀 `meta` 的那個 key、誰讀那組特徵、哪句 UI 文案在描述它、哪個參數的預設值指向它（`cd_measure` 的 `roi="blob"`）、哪個 algo 模組只為它而存在（`algo/blob.py`）。死掉的**程式碼**沒人會發現，死掉的**承諾**使用者天天看得到。現在框只有一個來源：呼叫端明講 `box=`，`render_overlay` 不猜 |
| **docstring 後面接 `%` 就不再是 docstring**（2026-08-15 踩到） | 想在說明裡插一個常數值，寫成 `"""…%s…""" % (X,)` —— 結果 `func.__doc__` **變成 None**，而且不會有任何錯誤 | 那是一個字串**運算式**，不是字串常值，所以 Python 不把它當 docstring 收。症狀完全是間接的（這次是 `test_ui_english_only` 把它當成「會顯示給使用者的字串」才抓到）。要插值就把數字寫進文字裡，或在函式外面組 `__doc__` |
| **借來的流被畫成「處理的流」**（2026-08-15 已修） | Normalize 的副標印`ref test → ref`，使用者讀成「test 進去、ref 出來」—— 而它做的是「正規化 ref，拉伸範圍跟 test 借」。同一張卡左邊還掛著三顆輸入埠圓點，其中一顆永遠不必接 | **箭頭只講這張卡處理什麼、產出什麼**；借來的流（`range_from` / `use_within` 這種「預設值是空的」參數）搬到下一行的參數摘要。**沒接線的選配埠不畫**（`graph.optional_ports`，早就寫好但一直沒人用），必接的永遠顯示。加新卡片時注意：一個 `image_key` 參數如果不是「這張卡處理的東西」，它的預設值就該是空字串 —— 那一個字同時決定它在畫布上算主角還是配角 |
| **「這份 recipe 吃什麼資料」曾經有兩個答案**（F9 Phase 3d 已收斂） | 同一張 Load 卡吐什麼要看 dataset kind，於是**埠算了兩次**：編譯期知道 kind、執行期不知道 —— 線接到 `load.single`、執行期卻吐在 `load.test` 上，整條下游安靜地不跑（跑得完、沒報錯、什麼都沒做）| 一種資料型別一張 Input 卡（`Step.accepts_kinds`），每張卡吐什麼是寫死的。`resolve_writes_for_kind` 這個特例整個拿掉，`stream_ports` 不再吃 `kind`/`first`。**新卡片如果又想「依情況吐不同的流」，先問這件事在畫布上看不看得見** ——看不見的話它就會再變成一個編譯期與執行期不同調的地方 |
| **分岔的兩條分支共用像素**（F9 Phase 3d 已鎖） | 一張卡就地改寫影像流（`arr += 1`、`arr[mask] = 0`、`cv2.xxx(..., dst=arr)`），另一條分支拿到的是**被改過的圖** —— 跑得完、有數字、而且是錯的，沒有任何錯誤訊息 | `Packet.fork()` 的複製**不含像素**（只複製那本字典）。`Context.set_image` 現在一律把陣列標成唯讀（`context.freeze`），就地改寫當場丟 `ValueError` 指著犯規的那一行。**選擇在 set_image 凍而不是在 fork 凍** —— 只在分岔時凍的話，規則只在有分支的圖上成立，而卡片是在沒有分支的時候寫出來的。這不擋任何合法寫法：要就地改先 `.copy()`。掃原始碼做不到這件事（`dst=` 掃不出來）。`tests/test_f9_no_inplace_writes.py` 掃整個 registry，並先證明自己抓得到 |
| **`upto_node` 指到一張停用的卡時停不下來**（2026-08-15 已修） | Studio 點卡看中間輸出，回一句「算式裡的變數找不到」—— 那句話跟他按的那顆鈕沒有任何關係 | `run_defect(upto_node=…)` 以前只靠 `run_graph` 去**認節點 id**，而編譯過的圖裡沒有停用節點 —— 認不到就一路跑到底。以前看不出來，因為判定還不是卡片、route 尾巴後面沒有東西；判定變成卡片之後那張卡會照跑。改成用**索引**切段（`order.index(upto_node) + 1`），停用與否都對 |
| **registry 是 `import` 的副作用填起來的**（2026-08-15 踩到） | 一支測試檔單獨跑會紅、跟別的檔一起跑就綠，訊息是 `unknown step 'adc'` | 卡片註冊發生在 `import adept.core.steps` 的那一刻。只 import `adept.core.pipeline` 的測試檔，registry 裡就只有它自己註冊的假卡片 —— 而先跑過的別支測試會**順便**把真卡片庫載進來，於是結果跟**檔名字母序**有關。要用真卡片的測試檔請明講 `import adept.core.steps  # noqa: F401`（跟 `test_no_qt_after_import` 那條是同一類的病）|
| **拿掉一個欄位，要走完它的每一條下游**（F9 Phase 3d） | `Recipe.score` 拿掉之後，還有七個地方在讀它：lint 的三個 code、`store.rescore`、Studio 的整頁分數編輯器 + 卡片庫裡一個假卡片 `__score__`、畫布角落的摘要、範本庫對話框 | 跟「拿掉一張卡，週邊會留下承諾」是同一條。順帶一個**不能一起拿掉**的：`store` 的資料庫裡存的是 recipe **歷史快照**，沒有辦法遷移 —— `rescore` 必須同時讀得懂舊的 `score` 區塊與新的 `adc` 節點 |
| **遷移的判準要是「這是舊檔案」，不是「這個欄位缺了」**（2026-08-15 已修） | 同一份 recipe、同一批資料，`--workers 1` 與 `--workers 4` 算出**不一樣的分數**，兩邊都跑得完、都有數字 | `from_json_dict` 補 `subtract.b` 的條件是「params 裡沒有 b」。但 `run_batch` 會把 recipe 序列化送進 worker 再反序列化 —— 那趟 round-trip 也符合這個條件，於是子進程拿到的參數跟主進程不一樣（`n <= 1` 走循序路徑，所以連「跑一顆」跟「跑兩顆」都不同）。判準改成 **`app_version` 這一欄在不在**：`to_json_dict()` 一定會寫它，所以 round-trip 回來的 dict 不會被誤認成舊檔案。**任何 `from_json_dict` 裡的遷移都要先問一次「round-trip 會不會踩到我」**（`tests/test_recipe.py::test_a_recipe_round_trip_does_not_pick_up_the_old_subtract_default`）|

---

## 8. 待廠內驗證的假設（重要）

開發全程用合成資料（真實資料不能出廠）。原本有三條假設，**2026-07-30 使用者結掉了
前兩條**（一條確認、一條改設計繞開），剩下第 3 條要在廠內用 `fab_probe/` 探測腳本確認。
那三支腳本是 stdlib-only 單檔、輸出純文字且預設遮蔽 Lot/Wafer/Device 等識別碼，
設計成可以直接複製貼出廠區（細節與資料外流說明見 `fab_probe/README.md`）：

| 假設 | 現況 | 用哪支腳本確認 |
|---|---|---|
| ~~1. EBI patch 的 page→channel 對應~~ | ✅ **已確認（2026-07-30）**：第一張 = test、第二張 = ref。`load_dataset` 的 `channel_order` 預設就是對的。參數保留是給「一顆多於兩頁」或站點慣例不同用的，不再是「怕猜錯」 | — |
| ~~2. `nm_per_px` 來源~~ | ✅ **已用設計繞開（2026-07-30）**：不再需要這個值。見下面「單位一律 pixel」 | —（`probe_*.py` 若順手看到仍會回報，那是加分不是前提）|
| 3. KLARF 變體 | `klarf_core` 已知四種（含 M5 修正的 variant D） | `probe_klarf.py` 的 image-layout 變體判定與證據 |

### 單位一律 pixel，換算在輸出那一刻由使用者填（2026-07-30）

`nm_per_px` 在 KLARF 裡找不到來源，而舊做法是「找不到就吐 0」——
`cd_measure` 在沒有它的時候照樣吐 `cd_x_nm` / `cd_y_nm` / `area_nm2` 三個 **0**。
那是最糟的一種缺值：**0 是個看起來很像答案的答案**，它進得了分數表達式、
寫得進 DSIZE 欄，一路安靜到最後。而實務上它每一顆都是 0。

現在的分工：

- **pipeline 全程用 pixel。** `cd_measure` 吐 `cd_x_px` / `cd_y_px` / `area_px`
  （`area_px` 是新的 —— 以前只在算 nm 的時候用到，沒有吐出來）。
  卡片裡不做單位換算，**任何 `*_nm` 特徵都不該再出現**。
- **換算只發生在輸出。** Export 精靈的 DSIZE 那一列多一格 `× scale`
  （`klarf_out` 的 `size_scale`，CLI 是 `--size-scale`），預設 `1` = 原樣寫 pixel。
  要寫 nm 就把 nm/px 填進去 —— **那個數字只有站點自己知道**，所以它是一格輸入，
  不是一個猜出來的欄位。計畫書會把換算寫進 plan.notes，因為「這一欄是什麼單位」
  不能只存在按下去那個人的腦子裡（鐵則：寫回前一定先預覽變更）。

舊 recipe 若在分數表達式裡引用 `cd_x_nm`，`validate()` 會出 `unknown-feature`
warning 指名它 —— 那正是要看到的（它以前恆為 0，那份分數本來就是錯的）。

`core/calibration.py`（MMH 來的 nm/px profile 管理）**沒有被刪**：哪天真的量出
站點的 nm/px，它就是存那個值的地方，Export 那一格可以從 profile 帶預設值進來。

**每遇到一種新變體 → 做成最小化合成 fixture → 永久回歸測試**（見
`tests/test_klarf_variant_d.py` 的寫法：先斷言「這份檔案確實是該變體」當前提，再測行為）。

## 9. 進度與下一步

| Milestone | 狀態 | 內容 |
|---|---|---|
| **F9** | ✅ | **圖就是程式**（Phase 1–3d 完成，2026-08-15）：線是**真的資料通道**（`core/pipeline/graph.py`；線上流一顆 defect 的整包狀態，分岔才複製）。**線分兩種**：`packet`（狀態的去向）與 `stream`（這張卡動哪一條流，不搬狀態）—— 一條流被三張卡讀是三條 stream 線，**不是三岔**。**埠名就是影像流名**，卡片裡選流的下拉退場。**畫布畫的是編譯出來的圖**。**判定是一張卡**（`steps/adc.py`）：一張圖可放好幾張、每條分支的門檻各自調、沒有一張跑到 = **沒有結論**（score/bin 留 None，不給 0 分）。**輸入也是卡片**（`load_patch` / `load_single`，`Step.accepts_kinds`）——「這條 pipeline 吃什麼資料」是圖上第一張卡的身分，不是 `routes` 的鍵。**`Recipe.score` 與 `Recipe.routes` 兩個固定欄位都退場**，recipe = `nodes` + `order` + `edges`；舊檔案兩種都載得進來（`_migrate_score_block` / `_migrate_routes`）。**「不就地改寫像素」從慣例變成鎖**（`Context.set_image` 一律 freeze）。新參數型別 `expr`（算式框 +「Insert feature ▾」）。驗收：同一份範例 recipe 每一批改寫前後 60 顆 CSV **逐格相同**、80 檔全綠。計畫書 `docs/plans/F9-graph-as-program.md`。⚠ §5d.6 反過來一條使用者決定（route 順序現在**要**畫成線，因為它已經是程式本身而不是裝飾）—— 別再退掉它。**下一步 Phase 4**：畫布變成真的編輯器（埠型別擋不合法連線、刪線＝真的斷開、分岔／合流畫得出來）|
| F8 | 🔨 | **純規則 ROI 定位 + mask 通道 + UI 第二波**（詳見 `SESSION_LOG.md` 逐輪紀錄與 `docs/plans/F8-rule-based-roi.md`）。已完成：`roi_cross`（條紋交會處放框、一鍵整批量 pitch）、`roi_mask` + Normalize `use_within`（見 §2.5）、參數說明搬 tooltip、D 案版面（畫布佔中上、設定拿大頭、**畫布彈出視窗**兩窗互通）、右鍵平移、手動佈局保留（tidy 才重排）、route 虛線退役（排版仍吃隱含順序）、量測卡預覽疊區域框、`multi_choice` 參數型別（glv_stats 統計量用勾的）、subtract 預設 `b=ref`（patch 天生對齊；舊檔載入遷移補 `ref_aligned` —— **改預設值必附遷移**） |
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/卡片庫/合成資料/CLI（卡片數會變，看 `python -m adept steps`）|
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：一份 recipe 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1%（當時的 `dual_route_basic.json` 已隨 F8 第五輪的範例改版移除，雙 route 的迴歸測試留在 `tests/test_e2e_dual_route.py`）|
| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `adept export` |
| M6 推廣包 | ✅ | 離線安裝三件套（`tools/fetch_wheels.py` / `install_offline.py` / `doctor.py`，全 stdlib-only）、首啟導覽 + 範例 recipe 庫對話框、範例 recipe（**目前只有 `cross_regions.json` 一份** —— 舊的五份都依賴 F8 第五輪被拿掉的卡，使用者決定「等 APP 完成再給範例」）。快速參考卡 PDF 暫緩（移到 backlog） |
| M7 UI/UX | ✅ | A 組防呆 + **UI 全英文**（`tests/test_ui_english_only.py` 鎖住）。F7 全數完成：patch-only 收斂（`ui/scope.py`）、中性色/平面主題 + 暗色、卡片依流程階段分組 + 搜尋 + 前置條件 badge、**Region 段（具名 ROI）**、Results 視窗、**節點畫布**。計畫書 `docs/plans/F7-canvas-and-taxonomy.md` |
| F7-24 | ✅ | **版面把空間給對的東西**（來自一張跑起來的截圖）：**開 recipe 自動 fit**（`fit_later()` 等畫布真的有尺寸才算；`fit` 加上限 1.0 —— `fitInView` 會把兩張卡的 pipeline 放大成三倍）、**兩個下拉框不再吃掉整列**（以前各佔八百多 px 去裝「1」與「diff」，而 `ebi_patch · defect 1 / 24` 被擠掉）、**刪掉死掉的 `PipelinePanel`**（F7-6 的畫布取代了它，但每一輪主題工作都還要繞過它）、**工具列不再是七顆一樣的白鈕**（亮色 `toolbar` 以前與 `bg_surface` **同為 `#ffffff`**；五顆文字鈕各配一個自繪圖示；`Export…` 拿 accent 外框 —— 整條工具列只有兩顆有顏色，而它們正好是要按的那兩顆）。**`Spread` 面板補上軸與圖例**（刻度畫在每一排自己身上 —— 每排單位不同，不能共用一句「0 → 255」；圖例畫一次，並明講右邊那欄是**這一顆**的值）、**往回走的線不再橫掃畫布**（換行那條線以前控制點水平推 `|Δx|*0.5`，一條線甩七百多 px；改成水平只推固定的 46px、量交給垂直方向）。**第二輪（對著自己截的圖再看一次）**：**fit 的下限從 0.45 改成量出來的 0.7**（十張卡落在 52%，卡片副標是一團灰；52/60/70/80/100% 逐級看過，副標要到 70% 才回來）、**塞不下時靠開頭對齊不置中**（`fitInView` 置中會把第一張跟最後一張同時切掉，而 pipeline 是從左往右讀的 —— 這條是前一項造出來的問題，**一輪改動要再截一次圖**）、**`Run trial` 與 `▾` 包成分段控制項**（1px 縫 + 內側直角）。驗收 `tests/test_ui_f7_24_layout.py`（13 條）。計畫書 §28、§29 |
| F7-23 | ✅ | **按鈕要說得出自己現在是什麼狀態**（試用回饋第九輪）。第一輪**只動 `theme.py`**、呼叫端零改動：**八種按鈕全部補上焦點框**（以前只有「沒有 objectName 也沒有 variant」的那一種有 —— 見 §7 新增的兩列；新 token `focus_ring_inverse`，因為框要跟按鈕自己的底對比）、**disabled 的 primary 留住 accent 淡底**（以前跟一般鈕同一片灰，於是沒載資料時「該按哪一顆」沒有答案）、**圓角收成 `radius_sm/md/pill` 三個 token**（原本六個值散在 QSS 各處）、刪掉**寫了兩次的 `QToolBar::separator`**（贏的是沒有註解的那一份）。`Run trial ▾` 的下拉區量下來 QSS 做不到（見 §7），移到第二輪。**第二輪**：小按鈕的**六種尺寸收成一種**（`widgets.small_button()` 只說形狀 `square`/`wide`，邊長由 `control_sm` 決定；`kind="icon"` 給浮在畫布／影像上的那幾顆一個自己的底）、**垂直節奏統一**（重要性只用水平 padding 表達 —— 以前 primary 高 2px，空白狀態下兩顆並排的鈕對不齊）、**游標從「每個人自己記得」變成規則**（`apply_button_cursors()` 掃一次；以前一半的按鈕滑過去沒有變手指）、**`Run trial ▾` 拆成兩顆真的按鈕**。驗收 `tests/test_ui_f7_23_buttons.py`（13 條；對第一輪前 7 紅、對第二輪前 5 紅），含一條靜態掃描擋 `setFixedSize` 長回按鈕上。**第三輪**：**三個元件不再自己組色盤**（`_Chip` / `StageButton` / `LibraryItem`+`libBadge` 搬進 QSS —— 以前換膚要靠有人記得逐顆重套，而帶 badge 的卡片庫列那條路沒被走到，會留在上一個主題的灰色；真正每個實例不同的階段色仍留在 widget）、**`pressed` 真的跳一階**（新 token `pressed_bg`；以前與 hover 只差 ΔL*≈3.5）、**最小的按鈕不再有最大的反應**（`#cardButton:hover` 從動三件事收成兩件）、**`QPushButton` 補上 `:checked`**。順帶抓到 `radius_pill` 的 `999px` 在 Qt 是**方角**（見 §7）。**第四輪**：**按鈕上的字元圖示改自繪**（`widgets.draw_glyph_icon()` 14 個 + `IconButton`；`⤢`(U+2922)、`⌗`(U+2317)、`↶↷`(U+21B6/B7) 在廠內的 Windows 上 Segoe UI 根本沒有，退字型會讓同一排按鈕每顆字大小與 baseline 都不同，最壞是豆腐框 —— 而開發機看不到）。圖示顏色取 `palette()` 的 `ButtonText`（Qt 從 QSS 的 `color` 解析），換膚與變灰自動跟著；**主題鈕的實心半邊會隨目前主題翻面**，以前兩個主題長得一樣。刻意**不**碰 `−↑↓×` —— 那幾個 Segoe UI 有，一起畫掉只是多改動。計畫書 §27。|
| F7-22 | ✅ | **畫布再往 n8n 靠一步**：**參數表預設收起、雙擊卡片才攤開**（畫布因此拿到整欄；`params_open()` 追明確狀態）、**線上 hover 出現斷開 ×**（虛線不給 —— 它刪不掉）、**「排整齊」按鈕**（放縮放鈕旁邊：兩者都只動「怎麼看」）、**卡片庫可以拖到畫布**（自訂 MIME，不是純文字）。計畫書 §26 |
| F7-21 | ✅ | **畫布上接得出「兩條都做」＋ 直方圖看得懂**（試用回饋第八輪）：同一對節點的**第二條線改成累加**（`image_keys` 才累加；`subtract` 的 a/b 這種角色埠仍然取代。而且**第一條線是取代** —— 卡片預設的 `streams="test"` 是規格預設值不是使用者拉的線，第一條就累加的話他拉一條會得到兩條）、**並排預設左 test 右 ref**、**並排時一條流一張直方圖**（`set_context` 多 `shown_streams`）、**直方圖標出軸與圖例**（`gray level` / `pixels`，圖例改成畫一段線＋一塊方塊，不再用 `outline = before` 那種要先翻譯的字）。順手修掉 F7-20 的回歸：`_default_stream` 拿 `"test,ref"` 整串去比流名比不到，會掉回 writes 最後一項 → 點 Normalize 跳到 ref。計畫書 §25 |
| F7-20 | ✅ | **正規化那一家收成一張卡**（試用回饋第七輪）：Enhance **9 張 → 4 張** —— Normalize（percentile / glv_band / match / local 四選一）、Adjust tone（亮度・對比・gamma・曲線・反相，**不是**四選一，是可以同時做的幾個旋鈕）、Denoise、Remove background。新增 `ParamSpec.show_when`（參數跟著方法出現／消失，取代 help 裡那句「這個方法用不到」的道歉）與 `Step.resolve_requires_ref`。順帶做掉 F7-19 的引擎那一半：`MultiStreamStep` 讓一張卡吃 N 條流（`streams`），`range_from` 的順序陷阱因此消失。**畫布那一半還沒做**（輸入側仍是單一埠）。舊 recipe 由 `recipe._migrate_merged_cards` 換名，分數逐項相同。計畫書 §24 |
| F7-19 | ✅ | 引擎於 F7-20、畫布於 F7-21 完成。原始計畫與復盤見下一列與 §23 |
| F7-19（計畫） | ✅ | **一張卡是「一次處理」，不是一條流**（試用回饋第六輪）：卡片頭尾都變成每條流一個埠，接幾條就處理幾條（N 進 N 出）。**這不是 `also_apply` 回來** —— F7-18 保護的不變量是「畫布不能說謊」，而這一輪的第二條流有真的線、真的埠。順手解掉 §22.7 全部三條未解。**不做卡片分類、不新增參數**：既有的 `range_from` 原樣保留（它已經是畫布上一條線），要讓兩條流吃不同處理就放兩張卡 —— 計畫第一版為此發明了 `measure_on` + 三類卡，被使用者當場擋下來，理由與復盤寫在 §23.3。計畫書 §23；引擎已完成於 F7-20，剩畫布的輸入埠 |
| 單位 | ✅ | **量測一律 pixel，換算搬到輸出**（2026-07-30 使用者決定）：`cd_measure` 拿掉 `cd_x_nm` / `cd_y_nm` / `area_nm2`（它們在沒有 `nm_per_px` 時**每一顆都是 0**，而那個欄位從來沒有來源），改吐 `cd_x_px` / `cd_y_px` / **`area_px`**（新的）。nm 換算由 Export 精靈的 `× scale` 一格輸入承接（`klarf_out` 的 `size_scale`、CLI `--size-scale`，預設 1 = 原樣寫 pixel），並寫進 plan.notes。同日確認 **page→channel 就是 test/ref**，兩條待驗證假設結案。見 §8 |
| F7-18 | ✅ | **影像流是節點的事，不是控制列的事**（試用回饋第五輪）：拿掉輸出埠上常駐的「+」（入口收回卡片庫，接線與影像流由 `add_card_after` 承接）、**虛線給自己的色相**（`canvas_edge_implicit`；同色淡一點只說得出「比較不重要」）、**一張卡一條流**（七張 Enhance 卡的 `also_apply` / `anchor` 拿掉；`percentile_norm` / `glv_mask_norm` 補 `range_from` 保住「兩張圖還比得起來」）、**連線指定影像流**（`edge_added` 帶出發埠；同一對節點再拉一條是「我改變主意了」）。舊 recipe 由 `recipe._migrate_also_apply` 展開成多張卡，分數逐項相同。計畫書 §22 |
| F7-17 | ✅ | **右下角變成「這張卡自己的儀表」**（依 `Step.key` 註冊，沒註冊的用原本的特徵表 → 加新卡不必動 UI）。四個：`load_patch` 的 **page→stream 對應**（廠內假設 #1 第一次看得見）、Enhance 九張卡的 **before/after 直方圖 + 削平計數**（新增 `Context.track_changes`，**只有預覽打開**）、`align` 的**整批位移散佈圖 + 搜尋半徑框**、五張量測卡的**整批分布 + 這一顆站在哪**。第二批：`roi_profile` 的曲線面板**收進同一個機制**（原本是平行的另一條路）、`roi_template` 的**三道閘門各自的門檻線**（match / certainty / **structure** 三種失敗的處置完全不同）。計畫書 §21 |
| F7-16 | ✅ | **四張安全網**：**復原/重做**（存整份快照，不是反向操作；滑桿一次拖曳算一步）、**快捷鍵**（Ctrl+O/S/R/Z/0/±/F/←→，全照 OS 慣例，並寫進 tooltip）、**關窗前問「還沒存」**（存檔失敗不算可以關）、**跑到一半可以停**（引擎本來就支援，只是按不到；已跑完的留著，而且訊息講「stopped」不是「finished」）。計畫書 §20 |
| F7-15 | ✅ | **畫面上的字要能被讀完**（C 組）：參數說明**收成一行、用到才攤開**（錯誤永遠攤開；`hint_text()` 回全文）、沒資料時最大的那一塊給「Open KLARF… / Try it with sample data」、**狀態列的拒絕變紅字**（`_status(msg, "error")` + QSS，逐條列舉哪些算 error）。計畫書 §19 |
| F7-14 | ✅ | **從畫布上就做得完一條 pipeline**（B 組）：輸出埠上的 **「+」**（清單只列**現在就接得上**的卡，依階段排序；按哪個埠決定新卡做在哪條流上；接出來的是實線）、**畫布縮放控制**（左下四顆 + 百分比，夾在 25–300%）、**節點副標印 `吃什麼 → 吐什麼`**（Region 卡取 `resolve_regions_out`；重複的卡才帶 id）。計畫書 §18 |
| F7-13 | ✅ | **控制項要看得出自己是什麼**（試用回饋第四輪 A 組）：下拉選單的箭頭（0 個畫素的 QSS 坑）、`template` 參數型別（按鈕 + 摘要，不是文字框，入口從預覽面板搬回參數列）、`Step.configuration_issues()` → lint `not-configured` → **畫布上的警示標記**、工具列按鈕看起來像按鈕。計畫書 §17。**未做**：n8n 的輸出埠 `+`、畫布縮放控制、節點副標印關鍵參數 |
| F7-12 | ✅ | **ROI 定位第二批：Golden Cell 模板**。匯入一張原大圖 → 量週期 → 疊出一個完整 cell 當模板 → 在 cell 上標一次框，每顆 patch 用 NCC 對回相位再把框搬過來。patch **小於**一個週期沒關係（是把小 patch 滑進大模板，不是兩張小圖互相對位）。模板凍進 recipe（base64 純文字，不是路徑）。新卡 `roi_template` + `ui/template_dialog.py`。三道閘門見 §7 表。計畫書 §16。**未做**：用當次的大圖對凍住的 GC 做健檢 |
| F7-11 | ✅ | **ROI 定位第一批**：量測卡 `output_prefix`（多區域的前置；Studio 挑了區域自動填名）、**投影定位卡** `roi_profile`（壓成曲線→找轉折→挑一段，可一次吐出鄰段）、**曲線面板**、**區域跨顆檢視**（把框畫到前 N 顆縮圖上，可只看定位失敗的）。定不出來就退回整張圖並標 `locate_ok=0`。順手修掉「過期的背景預覽會蓋掉新畫面」。計畫書 §15 |
| F7-10 | ✅ | **route 的隱含順序畫成虛線**（畫布上「沒有線」以前不代表「沒有連接」，而使用者看到的是九張互不相干的卡）；**Enhance 補齊空間性 artifact**：新卡 `flatten`（背景梯度／掃描線條紋／top-hat／black-hat 五個方法一張卡）與 `local_contrast`（CLAHE），邊緣保留去噪塞進既有 `denoise`、雙流運算塞進既有 `subtract`。計畫書 §14 |
| F7-9 | ✅ | 試用回饋第三輪：**六個階段六個顏色**（`theme.group_hex`，ΔE ≥ 25 且明度差 ≤ 15，兩條都有測試鎖）、**埠座標系 bug**（殘影＋「後面沒有圓框」同一個因）、**開窗就有 Input 起手卡**、**`image_keys` 參數型別**（`also_apply` 從自由文字變成勾選框）+ `ParamSpec.label`、**點卡片不再跳到 ref**、**具名 ROI 納入 lint** + Studio 試跑前先 lint。計畫書 §13 |
| F7-7 / F7-8 | ✅ | 試用回饋兩輪：階段大按鈕 → **直式 icon rail**（卡片區收起來時整欄只剩 rail）、載入/試跑進度條、Brightness/Contrast + **Gamma / Curve** 卡、**每個有上下界的參數配滑桿**、**自訂色調曲線**（保單調插值）、**並排比對兩條影像流**（連動縮放平移）、畫布 n8n 化（圖示磚／點陣底／方向箭頭／每條影像流一條線）。詳見計畫書 §12 |

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

**F9 Phase 3d 起 `SUPPORTED_KINDS` 一個字串就夠了。** Input 卡自己宣告
`Step.accepts_kinds`（`load_patch` = ebi_patch、`load_single` = rsem/folder），
`visible_steps()` 直接問卡片 —— 吃不到的那幾張不會出現在卡片庫。以前那要靠
`HIDDEN_STEPS` 這份手寫名單，於是「打開 RSEM」得記得同時改兩個地方。
`HIDDEN_STEPS` 還在，但它現在只管「不是 Input 卡、但只在某種型別下有意義」
的那幾張（`golden_cell` / `cell_period`）。

`tests/test_ui_patch_only.py` 與 `tests/test_f9_input_cards.py` 兩邊都鎖：
GUI 真的收斂了，而且**打開開關就回得來**（monkeypatch 常數再驗一次）。

> ⚠ **`adept/core/algo/period.py` 不要刪。** 它現在只被 Golden Cell 用到，
> 看起來像是可以跟 RSEM 一起砍掉的東西 —— 但 `estimate_period` /
> `choose_origin` 的相位搜尋是之後做 **pattern-frame ROI** 的唯一工具
> （patch 是以 defect 為中心裁切的，晶格相位逐顆不同；
> 見 `docs/plans/F7-canvas-and-taxonomy.md` §4）。

CLI 不受影響：`python -m adept run` 照樣跑得動 rsem recipe。

---

## 9.5 部署到受限的廠內機器

**完整的環境限制看 [`AGENTS.md`](AGENTS.md)** —— 開發在家用機（有 git、能下載、
但**沒有真實資料**），執行在公司機（**只有那裡有資料**，但不能裝 git、
目前什麼都下載不了）。唯一的傳輸通道是**在 GitHub 上看到檔案並按複製鈕**。

三條路，用在不同時機：

| 情況 | 用什麼 |
|---|---|
| 第一次搬整包 | `bundle/ADEPT_bundle.py` **一個檔案**，貼進去跑一次（不分批，理由見 `AGENTS.md` §2 那段引言）|
| 之後更新 | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 |
| 只想跑格式探測 | 直接複製 `fab_probe/probe_*.py`（stdlib-only 單檔，**不需要整個 repo**）|

網路哪天通了還有 `tools/get_code.py` / `.ps1`（逐檔抓）。其餘對應設計：

- 整個 repo **只有純文字檔**（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml` + 一份 `.klarf`），
  所以 GitHub「Download ZIP」下載得下來（那份 zip 不含 `.git`；190 幾個檔案、約 1 MB）。
  **不要把 `.git` 打包給使用者** —— 二進位 pack 物件 + `hooks/*.sample` 腳本會觸發 DLP。
- **「純文字」是必要條件，不是充分條件。** DLP 也掃**內容**，而最容易破功的地方是
  測試 fixture：一份真實的 KLARF 帶著 Lot／Wafer／機台／device／**recipe 名稱**
  （通常編碼了層別與製程步驟）、缺陷分類名稱，甚至廠區代號 —— 而那些值對測試
  完全沒有用（`test_klarf_variant_d.py` 斷言的全是結構）。已全部遮蔽，
  並由 `tests/test_no_real_fab_data.py` 守著（白名單 + 合成命名規則，
  **不是列出不准出現的字** —— 那等於把要保護的東西寫進 repo）。
- Download ZIP 是從 **`codeload.github.com`** 出來的，不是 `github.com`。
  「以前下載得到、現在被擋」最常見的原因是 proxy allowlist 只放了後者，
  跟 repo 內容無關。分辨方式與替代路徑見 `docs/NO-GIT-SETUP.md`。
- **連 zip 都下載不了**（實際遇到：proxy 只放行 `github.com`，沒放 `codeload`）→
  `tools/get_code.py`：只用 `raw.githubusercontent.com` **一台主機**逐檔抓，
  每個檔案對 `tools/FILELIST.txt` 的 git blob SHA 驗過才落地。
  驗 SHA 不是龜毛：被擋的 proxy 常常回一頁 HTML 而且是 **HTTP 200**，
  那種東西寫進 `.py` 之後症狀是「程式碼都在但 import 就語法錯誤」。
  清單由 `tools/make_filelist.py` 產生，有測試擋它腐爛（見 §6）。
- 相依套件走離線 wheels：`tools/fetch_wheels.py`（有網路的機器）→ 帶 `wheels\` 過去 →
  `tools/install_offline.py`（廠內機器）。全部 stdlib-only，因為它們在套件裝好之前就要能跑。
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
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、SNR map、MultiROISet（blob 分割也是從這裡來的，已於 2026-08-15 移除，見 §7）|
