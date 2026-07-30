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

> **一張卡只做一條影像流**（F7-18）。Enhance 卡吃 `target`（或 `source`）一條流、
> 寫回同一條，`resolve_writes` 就只回那一條。要對 ref 也做同一件事就**再放一張卡**
> —— 「要對哪幾張圖做」是畫布上的事（哪條線接進來），不是控制列上的一組勾選框。
> 一張卡寫兩條流會讓畫布說謊：它畫在 test 那條鏈上，卻同時改寫了 ref。
> 需要「借另一條流的資訊」時，那件事要有自己的參數（例：`percentile_norm` 的
> `range_from`），而且型別是 `image_key` —— 它在畫布上就是第二條接進來的線。

> **參數名是 recipe 的鍵，不是給人看的字**（F7-9）。`ParamSpec` 有選填的
> `label`：有就顯示 label，沒有就顯示 `name`。`range_from` 對製程工程師不是
> 一句話，`Borrow range from` 才是。同理，「一串影像流」請用 `type="image_keys"`
> 而不是 `str` —— 值的格式一樣（逗號分隔字串），但 UI 會給上游每一條流一個
> 勾選框，使用者不必猜能填什麼，也不會打錯字。

> **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。ParamForm 看到有上下界的
> `int`/`float` 就自動配一支跟數字框雙向綁定的滑桿。這不只是好看 ——
> 使用者是一邊拖一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。
> `type="curve"` 則會拿到一張可以自己拉的色調曲線編輯器（見 `pipeline/curve.py`）。

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
| **中心框幾何與影像尺寸綁死**（F7-4 已修） | 同一組 `glv_stats` 參數在 128² patch 上準、在 256² RSEM 上漏抓（缺陷散佈超出框） | **幾何已從量測卡搬到 Region 卡**（`roi_define`），量測卡只引用 ROI 名字。`size_unit="percent"` 的框會隨影像尺寸縮放，同一份 recipe 換 patch 尺寸不會失效。迴歸測試 `tests/test_region.py::test_percent_sizing_survives_a_patch_size_change` |
| **pytest 收集期 import Qt** | `test_no_qt_after_import` 失敗 | UI 測試一律 **lazy import**（在 fixture 內 import 並注入 globals） |
| **`QGraphicsItem` 拖曳留殘影**（F7-8 已修） | 拖動節點時埠標籤（"test"/"ref"）的舊位置沒被清掉 | `boundingRect()` **必須涵蓋所有畫得出去的東西**。埠標籤畫在節點右緣之外，之前只算到 `NODE_W + _PORT_R`，Qt 就只重繪那個範圍 |
| **在節點外面畫東西**（F7-8／F7-9／F7-14 同一條） | 拖動節點留殘影 | `boundingRect()` 必須涵蓋**所有畫得出去的東西** —— 埠標籤（F7-8）、埠圓點（F7-9）、輸出埠的 `+`（F7-14）都在節點右緣之外。加任何畫在卡片外的裝飾時，先把 `boundingRect` 加寬，`tests/test_ui_f7_14_canvas_flow.py` 會斷言 `+` 的中心在 `boundingRect` 裡 |
| **`paint()` 用場景座標**（F7-9 已修） | 殘影**又**出現；而且「新增的節點只有左邊有圓框，右邊沒有」 | 兩個症狀同一個因：`paint()` 拿 `out_anchors()`（**場景**座標）去畫本地座標的東西。節點在原點看起來正常（第一欄的 Input 剛好在那）；一離開原點就畫到「兩倍位移」的位置。現在分成 `out_anchors_local()`（繪製／命中）與 `out_anchors()`（連線）。F7-8 只放大了 `boundingRect`，那是對症狀動刀 —— 真正的不變量是**畫的座標系＝宣告的座標系**，`tests/test_ui_f7_9_feedback.py` 直接鎖它 |
| **`test_no_qt_after_import` 跟檔名字母序有關**（F7-9 已修） | 新增一支 UI 測試檔就讓它失敗，而且失敗訊息指不到真正的原因 | 它以前在測試行程裡看 `sys.modules`，所以任何排在 `test_no_qt.py` **之前**的 UI 測試檔跑過 fixture 之後就會誤報。改成在乾淨的子行程裡 import core 再問 —— 那本來就是這條測試唯一想問的事 |
| **快取只存了 Context 的一部分**（F7-9 已修） | 同一份 recipe **第一次跑對、第二次跑錯**（`region 'main' is not defined`） | checkpoint 是執行順序上的**位置**（最後一張影像段卡的下一格），不是「所有影像段的卡」，所以夾在中間的 Region 卡（algo）會落在快取段裡。v1 快照只存 images/features/meta，`ctx.rois` 命中時整個不見。快照現在涵蓋 `rois` 與 `labels`，並帶 `FORMAT_VERSION`（版本不合一律當 miss，舊快取目錄不會餵回殘缺快照）。迴歸測試 `tests/test_batch_cache.py::test_named_rois_survive_a_cache_hit` |
| **特徵是扁平的全域命名空間**（F7-11 已解） | 兩張同型別的量測卡（例：量兩個 ROI 的 `glv_stats`）都寫 `glv_mean`，後面那張**安靜地蓋掉**前面那張，分數表達式指不到前面那個值 | 量測卡有 `output_prefix`（Studio 挑了區域會自動填成區域名），撞名時 `validate()` 仍會出 `feature-collision` warning、Studio 跑完在狀態列講出來 |
| **量測卡指到沒人定義的 ROI**（F7-9 已修） | `cd_measure` 預設 `roi="blob"`，少了上游 Blob 卡時**安靜地改量整張圖** —— 跑得完、有數字、而且是錯的 | 具名區域現在跟影像流走同一條檢查：`Step.resolve_regions_in/out()` + `validate()` 的 `unknown-region`；`blob` 退回整張圖時會 `ctx.warn`。Studio 也在試跑前先跑 lint（以前完全沒跑，於是接錯的卡片會「跑完 200 顆、每顆都失敗」） |
| **色調曲線用自然三次樣條** | 使用者把中間點往上拉，影像出現一圈**不存在的暗環** | 樣條會 overshoot。`algo/curve.py` 用保單調三次 Hermite（Fritsch–Carlson）。這是演算法自己造出來的假缺陷 —— 對判 defect 的工具是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住 |
| **`isVisible()` 在 show 之前恆為 False** | 「這個面板收起來了嗎」在建構期永遠答錯 | 一律追明確狀態（`LibraryPanel.panel_open()`、`StudioWindow.compare_enabled()`、`_progress_on`），不要問 widget |
| **`drawPolygon` 傳散的 `QPointF`**（F7-17） | 整個行程 **segfault**（不是丟例外，所以看不到任何訊息，只有 exit 139） | PySide6 會綁到別的 overload。要傳 `QPolygonF([...])`。自繪面板加任何多邊形時注意 |
| **暗色盤裡的佔位字串**（F7-17 已清） | `accent_border` 的值是 `"#2f4straight"`，靠 70 行後的一句覆寫救著 | Qt 對無效色字串是**靜靜畫成黑色**，不會報錯。色盤裡不要留「稍後修正」的值；`tests/` 有一條掃描所有 token 是否為合法 hex |
| **`_update_action_states` 會蓋掉 tooltip**（F7-16 已修） | 把快捷鍵寫進工具列 tooltip，第一次 refresh 之後就不見了 | 那幾顆的 tooltip 每次 refresh 都會依前置條件重寫（「還沒有東西可以存」）。所以不能「建構時附加一次」，要讓**設 tooltip 的那個動作自己補上快捷鍵**（`_set_tip`）。`test_ui_f7_16_safety_net.py` 會 refresh 一次再驗 |
| **Qt 的 Enter/Leave 在父子之間會打架**（F7-15 已修） | 滑鼠從參數列的空白處移進**那一列自己的**輸入框，說明就閃一下（收起來又立刻攤開） | Qt 先送 `Leave` 給父元件、再送 `Enter` 給子元件。照字面處理必閃。`leaveEvent` 改成直接問**游標還在不在自己的矩形裡**（`rect().contains(mapFromGlobal(QCursor.pos()))`），不要相信事件的字面意思 |
| **QSS 把 subcontrol 的箭頭畫成 0 個畫素**（F7-13 已修） | 下拉選單跟自由文字框**長得一模一樣**，使用者無從得知哪個點得開（`Match on` vs `Name this region`） | `QComboBox::drop-down { border: 0 }` —— styled 的 subcontrol 要**自己提供 `down-arrow` 圖檔**，否則 Qt 什麼都不畫，而這個 repo 是純文字的（§9.5）塞不了圖。拿掉 `border: 0` 讓它留在 base style 上。`tests/test_ui_controls_readable.py` 用畫素數量鎖住（箭頭區 0 → 20，而 QLineEdit 恆為 0） |
| **參數合法 ≠ 設定完成**（F7-13 已修） | 空模板是完全合法的 str，lint 沒話說 —— 但那張卡跑起來**每一顆**都失敗，而使用者是跑完 200 顆才知道 | `Step.configuration_issues(params)`：卡片自己講缺什麼、用**這張卡的話**講（要去按哪顆鈕），變成 lint error `not-configured`，畫布上那張卡右上角掛警示標記。加這種卡時記得：`test_every_visible_card_can_be_wired_up_without_a_dead_end` 會要求訊息**指得出路在哪** |
| **模板比對：分數本身會騙人**（F7-12） | 全白／純雜訊的 patch 對任何模板都能拿到 NCC 0.44（門檻 0.3 → 過關），於是「碰巧」被當成「對得準」，框放到隨機的位置 | **沒有任何分數門檻分得出這兩者**（分數重疊）。要問的是另一個問題：**這張 patch 自己有沒有東西可比**（`min_structure`，實測無結構約 1、有結構 20 以上）。另外 margin 必須**先把比對曲面折回一個週期**再取次高峰，否則相鄰週期的次高峰讓 margin 恆為 0 —— 週期性把自己打敗了 |
| **Golden Cell 的原點會飄**（F7-12） | 同一份 recipe、不同時間建的模板指到不同的地方，而且畫面上完全看不出來 | cell 的第 0 欄預設是大圖上的**任意切點**，換張圖就換了 —— 而使用者是在 cell 上標框的。`algo/template.py::anchor_cell()` 旋轉到**最強的上升邊**在第 0 欄；用最大正梯度而不是 `abs`，否則一個週期的兩個相反邊界會競爭，錨點在兩者之間跳 |
| **`estimate_period` 在純雜訊上會回一個看似合理的週期**（F7-12） | 噪音圖疊出一個沒有意義的模板，然後安靜地拿去對每一顆 | 週期信心門檻 `MIN_PERIOD_CONFIDENCE = 40`（實測噪音 20.3）。「說我做不到」比「給一個沒有意義的答案」好得多。順帶：一維 layout（垂直條紋，只有 X 有週期）以前會被整個放棄 —— 那是最常見的情況，現在兩軸各自判斷，不重複的那軸取整個影像高度／寬度 |
| **KLARF variant D 誤判**（M5 修正） | 真實 1.8 檔（ImageList 欄不在最後、且無 IMAGECOUNT 欄）被 `lint()` 判定每一列都違法，Export 精靈跳紅字 | `row_len_ok` 改用 `effective_row_len()`：把 `Images N { … }` 子區塊折算成一欄。**注意 `image_layout()` 對這個變體仍回 None，而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它**。迴歸測試 `tests/test_klarf_variant_d.py` |
| **一張卡偷偷寫了第二條流**（F7-18 已改） | 畫布上那張 Denoise 畫在 test 那條鏈上，它其實同時改了 ref；而「要不要一起做」藏在控制列的 `also_apply` 勾選框裡，於是 test 是主角、ref 是附帶 | **一張卡一條流**：`resolve_writes` 只回主流。要對 ref 做就再放一張卡接到 ref。需要借另一條流的資訊時給它自己的 `image_key` 參數（`percentile_norm.range_from`），那條線在畫布上看得見。舊 recipe 的 `also_apply` 由 `recipe._migrate_also_apply` 展開成多張卡 |
| **拆卡片時的順序陷阱**（F7-18） | `anchor="source"` 拆成兩張卡之後，如果 test 那張先跑，ref 借到的是「已經拉成 0–255」的範圍 —— 數字不一樣，而兩張輸出都是看起來正常的圖 | 借範圍的那幾張要排在**前面**。這類遷移不要讀程式碼驗證：跑同一份 recipe 100 顆，比 `min/median/max` 與 bin 數量是否逐項相同（`tests/test_ui_f7_18_streams_as_nodes.py`）|
| **兩個節點之間只拉得動一條線**（F7-18 已修） | 先從 test 拉、再從 ref 拉，第二條只得到一句 `already connected` 然後什麼都沒發生 —— 使用者的結論是「這張卡不准我碰 ref」 | `edge_added` 帶第三個參數（**這條線從哪個輸出埠出發**），Studio 據此把下游卡的主要輸入指到那條流。同一對節點再拉一條要當成「我改變主意了」處理 |
| **常駐在節點旁邊的裝飾**（F7-18 已清） | 每個輸出埠一顆「+」，十張卡的 pipeline 就有十幾顆加號跟資料流搶畫面 | 入口收回卡片庫；「+」做對的事（接上線、接在對的流上）改由「選著一張卡時從卡片庫加」承接（`add_card_after`）。加完**選取新卡**，連按三張才會長成一條鏈而不是倒過來 |
| **虛線只是實線淡一點** | 「這條是我拉的」與「這條是排列順序帶來的」看起來只差深淺，而深淺會被縮放與主題影響 | 不同語意給不同**色相**（`canvas_edge_implicit`）。測試要鎖兩層：token 的色相差得出來，而且 `paint()` 真的去讀了它（畫進 pixmap 比主色相）|

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
| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：`examples/recipes/dual_route_basic.json` 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1% |
| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `adept export` |
| M6 推廣包 | ✅ | 離線安裝三件套（`tools/fetch_wheels.py` / `install_offline.py` / `doctor.py`，全 stdlib-only）、首啟導覽 + 範例 recipe 庫對話框、5 份範例 recipe。快速參考卡 PDF 暫緩（移到 backlog） |
| M7 UI/UX | ✅ | A 組防呆 + **UI 全英文**（`tests/test_ui_english_only.py` 鎖住）。F7 全數完成：patch-only 收斂（`ui/scope.py`）、中性色/平面主題 + 暗色、卡片依流程階段分組 + 搜尋 + 前置條件 badge、**Region 段（具名 ROI）**、Results 視窗、**節點畫布**。計畫書 `docs/plans/F7-canvas-and-taxonomy.md` |
| F7-19 | 📋 計畫 | **一張卡是「一次處理」，不是一條流**（試用回饋第六輪）：卡片頭尾都變成每條流一個埠，接幾條就處理幾條（N 進 N 出）。**這不是 `also_apply` 回來** —— F7-18 保護的不變量是「畫布不能說謊」，而這一輪的第二條流有真的線、真的埠。順手解掉 §22.7 全部三條未解。**不做卡片分類、不新增參數**：既有的 `range_from` 原樣保留（它已經是畫布上一條線），要讓兩條流吃不同處理就放兩張卡 —— 計畫第一版為此發明了 `measure_on` + 三類卡，被使用者當場擋下來，理由與復盤寫在 §23.3。計畫書 §23 |
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

**完整的環境限制看 [`AGENTS.md`](AGENTS.md)** —— 開發在家用機（有 git、能下載、
但**沒有真實資料**），執行在公司機（**只有那裡有資料**，但不能裝 git、
目前什麼都下載不了）。唯一的傳輸通道是**在 GitHub 上看到檔案並按複製鈕**。

三條路，用在不同時機：

| 情況 | 用什麼 |
|---|---|
| 第一次搬整包 | `bundle/ADEPT_part1of6.py` … `part6of6.py`，每一批貼進去跑一次（分批是因為 **GitHub 不顯示超過 1 MB 的檔案**）|
| 之後更新 | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 |
| 只想跑格式探測 | 直接複製 `fab_probe/probe_*.py`（stdlib-only 單檔，**不需要整個 repo**）|

網路哪天通了還有 `tools/get_code.py` / `.ps1`（逐檔抓）。其餘對應設計：

- 整個 repo **只有純文字檔**（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml` + 一份 `.klarf`），
  所以 GitHub「Download ZIP」下載得下來（那份 zip 不含 `.git`；170 個檔案、約 830 KB）。
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
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、SNR map、blob 分割、MultiROISet |
