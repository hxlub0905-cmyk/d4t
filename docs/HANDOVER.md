# d4t 交接文件

> **給接手的人（含新的 Claude Code session）：先讀這份，再讀 `CLAUDE.md`。**
>
> `CLAUDE.md` 是「怎麼動手」的操作手冊；這份是「為什麼會長成這樣」。
> d4t 是在一個 Claude Cowork session 裡從零做到 v1 的，那個 session 同時讀過
> 六個既有專案的原始碼 —— **那份跨專案的脈絡不在程式碼裡，只在這份文件裡。**

版本：2026-07-28 · 對應 commit `M6: offline install toolchain…` · 588 tests

---

## 1. 這個工具為什麼存在

### 出發點（使用者原話的整理）

在半導體 E-beam Inspection 的工作裡，機台會對每顆 defect 產出小圖（patch），
Review SEM 則會產出單張高解析影像，兩者都配一份 KLARF。長年的做法是針對每個站點
寫一套 ADC（Auto Defect Classification）程式來重新算分、重新分類 ——
patch 的叫 **PADC**、review 影像的叫 **RADC**。

問題是：**入門門檻太高，要會寫 code。**

所以每次換站點、換想法，都得回頭找會寫程式的人。而真正知道「這種缺陷長什麼樣、
該看哪裡」的是製程與設備工程師，不是寫程式的人。

> 目標：**打造一個可以把腦中想法轉變成算法的工具。**
> 讓不會寫 code 的人，也能自己做出 ADC 算分 —— 也就是**量化證據**。

明確不要的東西：**不是單純框個 ROI、算 BBOX 內 GLV 那種一步到位的工具**。
要的是多步驟、能組合、任何 Inspection 站點都適用的。

### 由此推導出的最高指導原則

**站點差異封裝進 recipe，不封裝進程式碼。**

傳統 PADC/RADC 每個站點一份 code；d4t 是一份程式 + 每個站點一份 recipe JSON。
recipe 是使用者用滑鼠組出來的、可存檔、可互傳給同事。

第二原則：**推廣鐵則** —— 目標使用者不會寫 code。
任何讓他們看不懂、或會噴出 traceback 的設計，都是 bug。
（這條在程式碼層級有強制力：沒寫白話 `help` 的卡片，`register_step` 會直接拒絕註冊。）

### 心智模型：為什麼是三段式

使用者自己給的分類：**defect 分數最主要就跟兩件事有關 —— 影像（優化）和算法。**
於是整個 UI 與資料流都照這個切：

```
【影像段 Image】把圖變乾淨、變可比  → 產出影像流（ctx.images）
【算法段 Algo】 從圖量出數字        → 產出特徵（ctx.features）
【ADC 判定段】  特徵 → 分數 → bin → 寫回 KLARF
```

這不是裝飾。它同時是 `Step.category`、UI 分色、快取切點（快取邊界就切在影像段結尾，
所以改算法段或門檻都是秒級回饋）、以及 recipe 驗證的順序依據。

---

## 2. 需求訪談的結論與理由

以下每一條都是問過使用者才定的，改動前請先確認前提還在。

| 決策 | 結論 | 理由 |
|---|---|---|
| 使用對象 | **推廣給部門同事**（不寫 code） | 決定了 UX 引導、防呆預設、範例庫都是一級需求而非附屬品 |
| 形態 | 桌面 GUI（PySide6），core/ui 嚴格分離，CLI 附帶 | 廠內機器；CLI 供排程與腳本 |
| 組裝方式 | 視覺化 pipeline 編輯器 + recipe JSON | 「把想法轉成算法」的具體形式 |
| 輸入 | **兩種都要**：EBI patch（test+ref 配對、8-bit、multi-page TIFF）與 RSEM 單張 | 使用者明說格式參照 KLIP |
| 輸出 | 寫回 KLARF（class/bin/DSIZE）、另存含 score+class 的新檔、Top-N、報表、feature vector | feature vector 是為了未來 ML 備料 |
| Pipeline 結構 | **core 即 DAG**，UI v1 只呈現直線 + 輸入型別分流 | 直線是 DAG 的特例；之後上自由畫布時引擎零改動 |
| Gallery | v1 就要，含直方圖聯動 | 「同屏比多顆」是調參迴圈的另一半 |
| CD | 是 pipeline 中的一張特徵卡，不是特例 | 使用者主動提的：CD 當 attribute 很好 |
| ML | v1 純 rule-based，但 **feature 匯出先做** | 保留未來訓練分類器的料 |
| 重用方式 | **Vendoring**（複製進新 repo 改名空間） | 新工具完全獨立，不動現有六個專案 |
| KPI | 三個都要：自動分類準確度、壓 nuisance rate、**review efficiency**（分數排名高的都要是真 defect）| review efficiency 是 Gallery 按分排序的存在理由 |
| 資料量級 | 千級常態、偶爾上萬 | 設計目標 10k defect 流暢 |

### 名稱由來

這個專案改過兩次名字，兩次的理由都在這裡 —— 之後有人問「為什麼叫 d4t」，
答案是這一段，不要再重新推導一次。

**FlexADC（工作代號）→ ADEPT（M3）→ d4t（2026-08-19）。**

第一次定名 **ADEPT = Auto Defect Evaluation Pipeline Tool**：挑選時排除了水果系
（PEACH/FIG/PLUM，本來想跟 PEAR 成家族），理由是縮寫精準對應功能，而
*adept*（熟練、得心應手）正是要給不寫 code 同事的承諾。

第二次改成 **d4t**，理由是 **P = Pipeline 已經跟現況不符**。F9 之後核心不變量是
「資料從哪來由**線**決定」、影像流的身分是 `(節點, 埠)`、`validate` 會報
`ambiguous-input` —— 這是 DAG 與畫布，不是一條流水線。名字裡留著 Pipeline
會一直誤導新人。

`d4t` 是 *defect* 的 **numeronym**（頭字母 + 中間字數 + 尾字母），跟
i18n / k8s / n8n 同一套慣例；使用者要的就是「像 n8n 那樣，英文加數字」。
照抄 n8n 的做法：**名字底下永遠釘一行全稱** —— `d4t — defect`。

---

## 3. 六個來源專案：跨專案脈絡

**這一節是新 session 最缺的東西。** d4t 的演算法幾乎都是從使用者既有的六個專案
vendoring 過來的。那六個專案在使用者的桌面上（`Desktop\hxlub0905-cmyk\`），
但新的 Claude Code session 不會去讀它們。以下是當初讀過之後的判斷。

### 各專案提供了什麼

| 專案 | 是什麼 | d4t 拿了什麼 | **刻意沒拿什麼** |
|---|---|---|---|
| **KLIP** | KLARF 檔案編輯器（PySide6 GUI + 純邏輯 core） | `klarf_core.py` **整檔搬**（1.2/1.8 無損讀寫、健檢 lint、defect↔TIFF page 對應、比對、API-KLARF 產生）；`klarf_tif_probe` 的免解碼 TIFF 走訪 | 3340 行的 Qt GUI。只留下裡面的 filter DSL 概念 |
| **GLAS** | GDS/OASIS layout 與 SEM 對位工具 | `fine_align_one`、`_parabola_subpx`、`sem_loader`、ROI label map 契約（`gray[label==k]`）、DAG 拓撲排序概念（`recipe_dependency_order`）、boolean 運算式的 AST 架構 | **整套 OASIS/GDS 解析與渲染**（`oasis_streamer.py` 就 125KB、`gds_align_tool.py` 398KB）、multiprocessing pool harness |
| **MMH** | SEM 大量量測工具 | recipe 架構原型（一般化成 Step/DAG）、批次引擎模式（ProcessPool + as_completed + per-defect try/except）、次像素邊緣定位（CD 用）、影像品質三指標、calibration profile、KLARF 寫回與 exporter 模式 | CMG 專用的 recipe（54KB）、GUI workspaces |
| **PEAR** | Pre-EBI 屬性排序工具 | GLV 統計 metric bank、Tukey IQR 離群、Cohen's d / η²、**CJK-safe 影像讀寫**（`np.fromfile` + `imdecode`，Windows 中文路徑必備） | Qt UI、wafer map |
| **cell-period-estimator (CPE)** | 週期陣列的 cell 週期估測 | `estimate_period`、`stack_cells`、`ghosting_score`；UI 主題 token 系統（d4t 的配色延續自這裡） | `refine_period` / `candidate_periods`（2026-08-27 刪掉，見下）|
| **Perspective-Combination (Fusi³)** | 多視角 E-beam 影像融合 | 正規化、直方圖匹配、**5-backend 對位**、SNR map、blob 分割、`MultiROISet`（正規化座標、可隨對位平移） | 557KB 的 `dialog.py` UI、PCA fusion（v1 移出）、quadrant 多通道融合（v2 backlog）|

### 在來源專案裡發現、但**尚未回報給原專案**的問題

這幾件事值得回頭修原專案：

1. **Fusi³ `ecc` 對位 backend 位移正負號與其他四個相反。**
   `cv2.findTransformECC` 的 `WARP_INVERSE_MAP` 語意被弄反了。d4t 版已修正並用測試鎖住
   五個 backend 同號（見 `d4t/core/algo/align.py` 檔頭）。
2. **CPE `choose_origin` 是 stub**（永遠回 `(0,0)`）。d4t 在 M4 補完了相位搜尋。
3. **MMH 次像素 batch 版比 scalar 版低約 1.5 px 的系統性偏移。**
   d4t 照「行為不變」原則保留原行為並在檔頭記錄；要精確值請用 scalar 版。
4. **CPE `refine_period` 會走離真值**（2026-08-27 量的）。它照「疊完那張圖的
   Laplacian 變異數」排候選週期，而**銳利不等於對得準** —— 相位錯開的疊圖是
   兩份輪廓疊在一起，邊緣能量反而更高。實測真值 28、從 26 出發，它挑 20。
   d4t 這一版**直接刪掉**（vendored 進來之後一個 production 呼叫者都沒有），
   並改用 `golden.stack_agreement`（無量綱、量的是「那幾格彼此有多一致」）。
   原專案若還在用它排週期，這是一個安靜的錯誤。

### 還沒挖、但可以挖的（v2 backlog）

- **GLAS 的 GDS render** → die-to-database 參考圖（`render_gray_and_label_from_geoms`
  已經能同時吐灰階圖與 ROI label map，兩者保證像素對齊）。這是「連 Golden Cell 都做不出
  參考圖」時的最後一條路。
- **Fusi³ 的 PCA fusion 與 quadrant 多通道融合**（BSE/SE）。
- **MMH 的 Region Stats / FFT**（分區統計、去趨勢、週期頻譜）。

---

## 4. 目前狀態：哪些是真的，哪些還是假設

**這一節請務必誠實看待。**

### 已驗證的

- 588 個測試全綠，全部跑在**合成資料**上，約 30 秒跑完。
- 效能：2 核容器、2000 顆合成 patch，cold 17.5 ms/顆、暖快取 2.2 ms/顆、rescore 0.17 s。
- 分類效果：`dual_route_basic.json` 跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1%。
- KLARF 無損寫回：inplace 模式沒改東西時輸出逐位元組相同（有測試鎖）。
- 唯一一份**真實來源的 KLARF**（`tests/fixtures/sample_real.klarf`，來自 GLAS）能正確解析、
  lint 乾淨、無損還原。

### 還是假設的（docs/FAB-VALIDATION.md 有完整版）

真實資料不能出廠，所以原本有三件事從頭到尾沒有用真實資料驗證過。
**2026-07-30 使用者結掉了前兩條**，剩一條：

1. ~~**EBI patch 的 page→channel 對應**~~ —— ✅ **已確認**：第一張 = test、第二張 = ref。
2. ~~**`nm_per_px` 從哪來**~~ —— ✅ **用設計繞開**：不再需要這個值。
   量測**全程用 pixel**，nm 換算搬到輸出的那一刻、由使用者自己填 nm/px
   （Export 的 `size_scale`）。以前「找不到就吐 0」的三個 `*_nm` 特徵已經拿掉 ——
   那個 0 進得了分數表達式也寫得進 DSIZE，而它每一顆都是 0。
3. **KLARF 變體還有幾種** —— 已知四種（含 M5 修正的 variant D）。**這條還在。**

`fab_probe/` 三支腳本本來是為了回答這三題而做的：stdlib-only 單檔、輸出純文字、
預設遮蔽 Lot/Wafer/Device 識別碼，設計成可以直接複製貼出廠區。
現在它們主要負責第 3 題（`probe_klarf.py` 的 image-layout 判定），
另外兩支仍值得跑一次當作交叉確認 —— 只是它們不再擋著任何事。

### 開發過程中踩到、已修但值得知道的坑

完整表在 [`PITFALLS.md`](PITFALLS.md)。三個最容易再踩的：

- **fork 死鎖**：Linux 預設 fork 若從 QThread 呼叫，ProcessPool 100% 卡死（GUI 按「試跑」
  永遠不回、也不報錯）。已改成主執行緒 fork、非主執行緒 spawn。
- **OpenCV IPP 非決定性**：同張圖算兩次差 ~1e-8，快取結果對不起來。已關閉 IPP。
- **KLARF variant D**：`ImageList` 欄不在最後 + 沒有 IMAGECOUNT 欄 → `row_len_ok` 誤判每列違法。
  修法是把 `Images N { … }` 折算成一欄。**注意 `image_layout()` 對這個變體仍回 `None`，
  而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它。**

---

## 5. 設計決策與理由（改動前先看這裡）

這些是「看起來可以隨便改、但其實有理由」的地方。

**`golden_cell` 預設寫進 `ref`。**
RSEM 沒有機台給的參考圖，Golden Cell 疊一張出來後命名為 `ref` ——
於是下游所有吃 ref 的卡片（對位、相減…）完全不用改，rsem route 只是比 ebi route
多插一張卡，整條算法段直接重用。這是「站點差異封裝進 recipe」最漂亮的一次體現。

**快取邊界切在影像段結尾。**
與三段式心智模型對齊：使用者改算法段或判定段的任何東西，都只重算後半，秒級回饋。

**score 表達式引擎是自己寫的 parser，不用 `eval`。**
安全語意：除以零、log 負數、NaN 都回 0.0，不會噴 traceback 給不寫 code 的人看。

**幾何類參數要隨 route 走。**
同一組 `glv_stats` 中心框在 128² patch 上準、在 256² RSEM 上會漏抓（缺陷散佈超出框）。
`dual_route_basic.json` 的做法是兩條 route 各自一個 glv 節點。
或者改用無量綱分數（`(glv_max-glv_median)/(glv_std+0.5)`），那樣才有共用門檻。

**Export 一定要先「預覽變更」才解鎖「寫出」。**
對著正式 KLARF 按下去的東西，不該讓人賭。任何選項一改動就作廢重鎖。

**`repo 只有純文字檔`是刻意維持的不變量。**
使用者的公司機有 DLP 會擋含二進位的壓縮檔。所以：不要把任何 `.png`/`.pyd`/`.zip`
加進版控，也**不要把 `.git` 打包給使用者**（二進位 pack 物件 + `hooks/*.sample`
腳本會觸發 DLP —— 這件事踩過一次）。

---

## 6. 接手後可以做什麼

依價值排序：

1. **帶 `fab_probe/` 進廠跑一次**，把 §4 剩下那個假設（KLARF 變體）變成事實。
   輸出貼回來 → 把真實格式做成最小化合成 fixture → 永久回歸測試
   （寫法參考 `tests/test_klarf_variant_d.py`：先斷言「這份檔案確實是該變體」當前提，再測行為）。
2. **拿一份真實 lot 跑一次完整流程**，看分數分佈長什麼樣、Gallery 掃起來合不合理。
   這是第一次知道合成資料上的 95% 有多少能兌現。
3. **v2 backlog**（[`ROADMAP.md`](ROADMAP.md) 底部）：ground-truth 標注 + 混淆矩陣儀表板
   （KPI「分類準確度」的完整量化靠這個）、自由 DAG 畫布、ML Classify 卡、
   快速參考卡 PDF、以及 §3 那些還沒挖的來源專案資產。

### 給 Claude Code session 的提醒

- `CLAUDE.md` 會自動載入，是操作手冊；這份 `HANDOVER.md` 要自己開。
- **每次 session 結束請更新 `SESSION_LOG.md`**（沿用 GLAS/MMH 的慣例）。
  那份是逐次的決策紀錄，比 commit message 詳細。
- 這個 repo 的測試全部用合成資料、~30 秒跑完，所以**改任何東西都應該先跑一次全套**：
  `QT_QPA_PLATFORM=offscreen pytest -q`（Windows 不用設環境變數）。
- 新增卡片的完整範例在 `CLAUDE.md` §5。新算法 = 新 class + decorator，UI 與引擎零修改。
