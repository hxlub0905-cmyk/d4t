# F11 — Phase 2：逐段把功能做完（Input → ADC）

**狀態：計畫中（2026-08-17 開工）。** Phase 1 已收斂（見 [`../ROADMAP.md`](../ROADMAP.md)）。

Phase 2 的定調是使用者的兩句話：

> 「我想優先做好內部的每個功能。」
>
> 「整體 Phase 2 開發週期應該會拉很長，因為我必須增加新功能 & 完善舊功能。
> 我自己主要看法是就**從左側功能一步一步往下開發**（從 Input 開始到 Enhance
> 接著 ROI 一路往下到 ADC），**每張卡的預期功能與 UI 介面與核心設定（要放在哪裡、
> UIUX 要怎麼放 Card Setting）都需要跟你討論過。**」

所以這一份**不是**六個項目的待辦清單，而是**六段的議程**：
一段一段往下、一張一張討論，討論完的決定就寫回這一份。

---

## 0. 這一份怎麼用

**節奏：一次一段，一段裡一次一張卡。** 每張卡討論到有結論才動手，
動完手就把結論寫進 §3 那一段的表格裡（不要另開檔案 —— 那份會漂移）。

**每張卡要回答的四題**（順序有意義：功能沒定之前談 UI 是空的）：

| # | 題 | 判準 |
|---|---|---|
| 1 | **這張卡做什麼**（一句白話，會變成 `help`）| 不會寫 code 的製程／設備工程師看得懂 |
| 2 | **吃什麼、吐什麼**（哪幾條流／區域／特徵）| 決定畫布上前後有幾顆埠。**宣告出來的東西不能比使用者接的多**（F10 的不變量）|
| 3 | **參數有哪些、怎麼分組**（`section` / `show_when` / `advanced`）| 見下面的「設定要放哪」清單 |
| 4 | **右下角要不要一個自己的儀表**（`ui/inspectors.py` 依 `Step.key` 註冊）| 這張卡的參數是不是「看著圖調的」？是就要 |

**設定要放哪 —— 現有的機制（不要重新發明，這些是既有卡片一路踩出來的）：**

| 想達到 | 用什麼 | 出處 |
|---|---|---|
| 分組小標題（一組參數回答同一個問題）| `ParamSpec.section="1 · …"` | F8 第三輪（`roi_cross` 19 個參數攤平時使用者說「不知道是什麼功能」）|
| 預設收起來、按 Show advanced 才出現 | `ParamSpec.advanced=True` | 判準：**填預設值就跑得出正確答案的話，它就是進階的** |
| 跟著方法出現／消失 | `ParamSpec.show_when=("method", ("percentile",))` | F7-20。⚠ **顯示規則不是驗證規則**，藏起來的參數照樣有預設值 |
| 一個家族的做法收成一張卡 | `type="choice"` + `choices` | F7-10／F7-20（四種正規化是一張卡的下拉，不是四張卡）|
| 「可以同時做」的東西 | 幾個預設不作用的旋鈕，**不要**做成四選一 | `tone` 的亮度／gamma／反相 |
| 滑桿（一邊拖一邊看圖決定值）| 把 `min`/`max` 填好就自動有 | F7-8 |
| 顯示名跟 recipe 的鍵分開 | `label`（`name` 是 JSON 鍵，改不得）| F7-9 |
| 影像流的來源／輸出 | `type="image_key(s)"` + **必填** `direction` | F10。設定區**唯讀**，來源只在畫布上拉線決定（F9-6）|
| 值會變成特徵名的一部分 | `pattern` + `pattern_help` | 打了空白或減號，score 表達式就指不到那個特徵 |
| 多選、曲線、模板、單位 | `type="multi_choice"` / `"curve"` / `"template"`、`unit` | F7-8／F7-12／F8 |

**每張卡動手前後的固定動作**：`help` 必填（鐵則 3）、合理 default 與 min/max
（鐵則 4）、改預設值必附遷移（`recipe._migrate_*`）、跑黃金值 `--check`
（新卡不得改變既有數字）。六條卡片不變量與 F10 的 20 條畫布不變量會**自動**
套用到新註冊的卡，不必為它們補工。

---

## 1. 現況稽核（讀 code 讀出來的，不是推論）

Phase 2 的起點跟 ROADMAP 上那幾行寫的不一樣，四件事先記下來。

### 1.1 ADC 段**一張卡都沒有**，而且只分得出兩類

這是整個 app 最大的功能缺口，而它剛好排在「一路往下」的最後一站，所以先講。

- `GROUP_ADC` 這個常數在，但**沒有任何 Step 用它**（`grep GROUP_ADC` 只有定義處）。
- 畫布／卡片庫上那張「Score」不是卡片，是 UI 造的一個假節點
  （`studio.py` 的 `_SCORE_LIBRARY_KEY = "__score__"`）。
- 真正的 ADC 是 recipe 上的**一個欄位**：`ScoreSpec(expr, threshold, bins)`，
  而 `bins` 被 `validate` 的 `bad-bins` **強制只有 `below` / `above` 兩個 key**。

也就是說：**現在整個工具只做得到二分類**（score ≥ threshold → bin 1，否則 bin 0）。
一個 ADC 工具的本業是分好幾類（`Particle` / `Bridge` / `Open` / `Nuisance`…），
而那件事現在連資料結構都還沒有。這不是一張卡的工作量，見 §3.6。

### 1.2 有演算法、沒有卡片 —— 而 help 叫使用者去跑那張不存在的卡

| 資產 | 誰在用 |
|---|---|
| `algo/blob.py`（`segment_defects` / `DefectROI`，155 行，vendored from Fusi³）| **沒有任何卡片**。只有 `algo/__init__` re-export 與 `tests/test_blob.py` |
| `algo/stats.py`（`group_outliers` / `cohens_d` / `attribute_separability`，85 行，vendored from PEAR）| **沒有任何卡片**。只有 `algo/__init__` re-export 與 `tests/test_stats.py` |

而缺這張卡是**看得見的**，有三個懸空的引用：

1. `cd_measure` 定不出框時的警告字面上寫 **“run Blob segment first”** ——
   registry 裡沒有 `blob_segment`。
2. `cd_measure` 讀 `ctx.meta["blobs"]` 算面積 —— **沒有任何一張卡寫得出那個 key**。
3. `export/overlay.py::primary_blob_box` 兩條路（`meta["blobs"]`、特徵
   `blob_x/y/w/h`）**都沒有生產者** → 「主 blob 紅框」在真的 pipeline 上永遠畫不出來。

這是 F10 那個形狀的親戚：**畫面（與 help、與輸出功能）說得出來的東西，引擎做不到。**

### 1.3 多通道：機制在，但 recipe 摸不到命名

`ingest/dataset.py::_channel_name` 已支援任意頁數（第 j 頁 → `channel_order[j]`，
名單用完接 `img3`、`img4`…），但 **`channel_order` 只有 `tests/test_dataset.py` 傳過**
—— UI 與 CLI 都吃預設 `("test", "ref")`。而使用者的資料是
**1 張 BSE + 4 張 SE，BSE 固定在第 2 頁**（2026-08-17），所以現在會載成：

```
第1頁 → test      第2頁 → ref  ← 其實是 BSE      第3–5頁 → img3, img4, img5
```

`load_patch` 的參數只有 `channels`（挑要載哪幾條，名字是 ingest 給的），
**recipe 與 Studio 沒有任何地方改得動那些名字**。

### 1.4 GDS 那條路變成「吃 GLAS 的匯出」，而且它已經在產了

ADEPT **不解析 layout**（使用者定調）。讀完 GLAS repo 之後確認：
它已經在匯出 `<id>_label.png`（整數 label map）、`<id>_gray.png`（模擬 GLV 灰階）、
manifest 的 `label_map`（label id → layer 名）與 alignment CSV/JSON；
**join key 兩邊同源**（都是 KLARF 的 `DEFECTID`）。

契約與「上游要小改什麼」（多頁 TIFF 的 page 對應是必要的那一條）全部寫在
[`../GLAS-INTERFACE.md`](../GLAS-INTERFACE.md) —— 那一份的 §4 可以直接複製給 GLAS。

---

## 2. 使用者定調（2026-08-17）

| 題 | 答 |
|---|---|
| 開發順序 | **從左側功能一步一步往下**（Input → Enhance → Region → Compare → Measure → ADC），**每張卡的功能／UI／設定放哪都要先討論** |
| 週期 | **會拉很長**（新功能 + 完善舊功能）—— 所以這一份是議程，不是待辦清單 |
| 演算法 | **不照抄 vendored 的**：「演算法請幫我移除，我要重新來，基本上不用照抄就有 vendor 的算法（我基本會想要優化改良）」。範圍見 §7.1 |
| GDS ROI | **ADEPT 不解析 layout**，只吃上游 GLAS 的 mask（一一對應）。契約見 [`../GLAS-INTERFACE.md`](../GLAS-INTERFACE.md) |
| 多通道 | **1 BSE + 4 SE，BSE 固定在 TIFF 第 2 頁**，SE 的順序無所謂 |
| ML Classify | Phase 2 後半 |

---

## 3. 六段的議程

每一段的表格：**現在有什麼** → **缺什麼** → **要討論的**。
討論完的結論寫回對應的那一列（連同日期）。

### 3.1 Input —— **這一段是「輸入端的核心」，不是一張載入卡**

使用者定調（2026-08-17）：

> 關於多通道，我反而想在 Input 段做。目前 Input 只支援 patch，但實際
> **Input 段就是整個輸入 image source 的核心**對吧，所以她要能**支援各種的資料形式**。
> （**五頁的資料不會有 ref**。）

所以這一段的題目不是「`load_patch` 加一個參數」，而是**要支援哪些輸入端接頭**。

#### 3.1.1 現在真的支援什麼（`ingest/dataset.py`）

三種 `kind`，偵測是自動的：

| kind | 怎麼認出來 | 一顆長什麼樣 |
|---|---|---|
| `ebi_patch` | 找得到 patch TIFF **且** KLARF 的 `IMAGECOUNT`/`IMAGELIST` 對得出 page | 多頁 TIFF 的**連續幾頁**，依序命名 `channel_order[j]`（預設 test, ref，多的接 `img3`…）|
| `rsem` | KLARF 的 defect 列帶**每顆一個檔名** | `{"single": 一個影像檔}`，路徑相對 KLARF 資料夾解析 |
| `folder` | 沒有 KLARF，掃一個資料夾（不遞迴）| 每個影像檔一顆，`defect_id` = 檔名主幹，無座標 |

**已經吃得下、只是沒人餵過的事**：一顆五頁**引擎層已經支援** ——
`defect_image_map` 的頁數是從**每顆的 `IMAGECOUNT`** 來的，不是寫死 2。
所以五頁資料進來會得到五個 `ImageRef`，缺的只有兩件事：**名字**（§1.3）與
**「沒有 ref」的下游後果**（§3.1.4）。

`ui/scope.py` 目前只開 `ebi_patch`（`SUPPORTED_KINDS`）—— rsem 那條路能力沒刪，
只是 GUI 收起來。

#### 3.1.2 接頭有四個獨立的軸（不要把它們混成一個下拉）

會出現「各種資料形式」是因為這四件事**各自獨立**，四個軸的組合才是一種形式：

| 軸 | 現在有的 | 可能要加的 |
|---|---|---|
| **A. defect 清單從哪來** | KLARF 1.2／1.8；資料夾（無清單）| CSV／Excel 清單（沒有 KLARF 的機台）；其他家 inspector 的格式 |
| **B. 影像怎麼裝** | 一個大 TIFF 裝一整批（每顆佔連續幾頁）；一顆一個檔案 | **一顆一個多頁 TIFF**（N 頁 = N 通道）；**一顆一個資料夾**（每通道一個檔）|
| **C. 一顆的通道語意** | test + ref；single | **N 個 detector 通道、沒有 ref**（1 BSE + 4 SE）|
| **D. sidecar（同一顆的附加檔）** | 無 | GLAS 的 `<id>_label.png`／`<id>_gray.png`；ground truth；per-defect 對位 offset |

#### 3.1.3 提案：**sidecar 走 Input 段的接頭，不是 Region 卡自己讀檔**

這是我讀完 GLAS 契約之後想改的一件事（原本 §3.3 打算讓 mask 卡自己吃一個目錄）。

理由是使用者那句話的直接推論 —— **Input 段是輸入來源的核心，那檔案 I/O 就該只在
那裡發生**。三個具體的好處：

- **配對規則只有一份。** `<DEFECTID>_label.png` 怎麼對到那一顆，只在 ingest 層寫
  一次；Region 段的卡只吃「一條流」，不知道也不必知道檔案在哪。
- **快取與平行是對的。** 影像段快取的簽章與 `ProcessPool` 的 worker 都是照
  「`DefectItem` 帶著哪些 `ImageRef`」在算的。卡片自己偷偷讀檔的話，
  換了 mask 目錄而簽章看不見 —— 那正是 F9 那六個「跑得完、有數字、而且是錯的」
  的形狀（鐵則 9）。
- **畫布不會說謊。** sidecar 進來就是一條有名字的流（例如 `layout_label`、
  `layout_gray`），使用者在畫布上看得到它、可以拉線；Region 卡吃那條流吐具名區域。

所以分工變成：

```
ingest（檔案 I/O、配對）→ 流：test / bse / se1..4 / layout_label / layout_gray
   └─ load_patch（Input 卡）把它們攤成 ctx.images
        └─ Region 卡吃 layout_label 那條流 → 具名區域（不碰檔案）
```

#### 3.1.4 「五頁沒有 ref」的連鎖後果（**這一項比命名重要**）

現在整條 pipeline 的預設路線是 `test − ref = diff`，而
**沒有 ref 的資料會把下游一路撞到底**：

- `recipe.validate` 的 **`requires-ref`** 會報錯（`subtract`、`align`、部分卡片）；
  現在那條訊息只講 rsem 單張的情形。
- `load_patch` 有一段「`single` 鏡射成 `test`」的特例（讓下游用預設參數就吃得到圖）
  —— 五通道進來時，「哪一條算 `test`」要有答案，而它**不該再是一個寫死的特例**。
- Compare 段要比什麼？三個候選，都不是白做的：
  **① Golden Cell**（已經有，需要 layout 有週期）、
  **② GLAS 的合成 `gray`**（die-to-database，見 [`../GLAS-INTERFACE.md`](../GLAS-INTERFACE.md) §5）、
  **③ 通道之間互比**（BSE vs SE：不同 detector 對同一個結構的反應不同 ——
  這是 Fusi³ 融合那條路真正的用途，不只是「多一張圖」）。
- 好消息：**blob 分割那條保底路線**（單張、沒有 ref、沒有週期，§7.1）
  正好是為這種資料準備的，所以它的優先度比原本高。

#### 3.1.5 使用者定調（2026-08-17）

| 題 | 答 | 後果 |
|---|---|---|
| 通道的名字 | **使用者自己命名，程式只給預設** | 預設 `bse` / `se1..se4`（不預設方位 —— SE 順序無所謂，`se_ul` 那種名字保證不了它真的是左上）。名字是**值**不是常數，所以 UI 要有地方打字，而打進去的字會變成特徵前綴 → 要 `pattern` 擋掉不能當變數用的字元 |
| 「哪一頁是什麼」在哪一層設定 | **recipe 裡**（`load_patch` 的 `channel_map` 參數）| 我原本傾向載入時問，使用者選 recipe。**那就必須補一道防呆**，見 §3.1.6 的「頁數不符要擋下來」——否則同一份 recipe 換一台頁序不同的機台會**安靜地量錯**（這正是現在的行為：第 2 頁的 BSE 被叫成 `ref`，`subtract` 不報錯，比的是 BSE 減 SE）|
| 沒有 ref 要跟什麼比 | **通道互比（BSE vs SE）** | 融合卡的定位因此定了：它是**產生 ref**，不是「多一張圖」。Golden Cell 與 GLAS gray 留著當備案，不排這一輪 |
| 接頭順序 | **C → D → B → A** | 先多通道無 ref、再 GLAS sidecar、再影像裝法、最後 CSV 清單 |
| **入口不該只有一條** | 使用者補的一條（見 §3.1.6）| Input 段是**一群入口卡**，不是一張 load 卡；引擎那一半要先改 |

#### 3.1.6 「Input 入口不該只有一條」—— 引擎那一半（**✅ 完成 2026-08-17**）

使用者原話：

> 可以通道互比，但你忘記最重要的，**Input (image source) 入口，我覺得不該只有一條**。

對，而且這件事在引擎裡有一道具體的阻礙。`recipe.validate` 現在是這樣走的：

```python
first = True
for nid in order:
    if first:
        # 第一張卡（load）：reads / requires_ref 不檢查；
        # writes 用 kind-aware 宣告
        avail |= set(step_cls.resolve_writes_for_kind(p, k))
        first = False
        continue
    ...
```

**「起點」被定義成「route 上的第一張啟用卡」** —— 那是線性 route 時代的殘留
（F9 之前畫布還沒有線）。後果是第二張入口卡只拿得到非 kind-aware 的
`resolve_writes`（`load_patch` 在 `channels="auto"` 下只保守宣告 `["test"]`），
於是它其實產出的那幾條流在 validate 眼裡不存在 → 下游一片假的 `missing-image`。

**要改成：沒有輸入埠的卡都是起點。** 判準已經有了 —— `Step.input_specs()`
（`direction="in"` 的 `image_key(s)` 參數）是 F10 為了畫布做的**宣告**，
一張入口卡沒有輸入埠是事實而不是位置。這一改順便讓三件事成立：

- 一份 recipe 可以有**好幾個 image source**（patch 的頁、GLAS 的 sidecar、
  以後的第二批資料），每一個在畫布上是自己的節點、自己的線；
- 「第一張卡」不再是特殊的，所以**刪掉第一張卡不會讓整條 route 的檢查換一套語意**；
- kind-aware 的 writes 對**每一張**入口卡都成立（現在只有第一張）。

⚠ 一起要顧的：`engine` 的執行順序（Kahn 拓撲排序）本來就吃得下多個起點；
**快取的 checkpoint 切點**要確認多入口時仍然正確（鐵則 9 第三條：任何會影響
影像段結果的東西都要進簽章 —— 多一個入口就是多一組來源檔案）。

##### 做完之後

判斷收成**一個** `Step.is_source()`，三個 `first = True` 全部刪掉
（`recipe.validate`、`engine._implicit_bindings`、`viewmodel.available_streams`）。
判準是兩個宣告的聯集：**沒有輸入埠、而且沒有靜態 `reads`**。

第二條不是多餘的 —— 第一版只看埠，結果 `tests/test_recipe.py` 當場三條紅：
那些假卡片宣告 `reads = ["diff"]` 但沒有讓使用者挑來源的參數（早期的卡片風格），
只看埠的話**它們全部變成入口，`missing-image` 整條檢查安靜失效**。
真的卡片裡只有 `load_patch` 是入口（有一條測試鎖住這件事）。

**抓到一個這一改造出來的新缺口**：`feature-collision` 的檢查以前**不對入口卡跑**
—— 因為入口只有一張，撞不起來。現在兩張 `load_patch` 都寫 `n_channels`，
後面那張會安靜地蓋掉前面那張。所以那段檢查抽成 `_feature_collisions()`
給兩條路共用（**同一段判斷抄兩份，總有一份會長歪** —— 這個 repo 記過三次），
而 `n_channels` 的語意也順便鎖進測試：它問的是「**這張卡**載了幾條流」，
所以兩個入口各自回 1，前面那張仍然指得到（`load_t_n_channels`）。

驗收 `tests/test_f11_multi_input.py`（5 條，用**真的**卡片與合成 lot）：
兩個入口 lint 全綠、**量出來的數字與一個入口逐項相同**、停用第二個入口下游就
拿不到 `ref`（擋「兩個入口其實是裝飾」）、冷跑熱跑逐項相同（快取簽章看得見第二個
入口）、`n_channels` 的語意。加上 `tests/test_recipe.py` 的 4 條（lint 層、假卡片）。

| 驗證 | 結果 |
|---|---|
| 核心測試 | 1019 passed / 34 skipped |
| UI 測試（34 個檔案逐檔跑）| 全綠 |
| 黃金值 `freeze_golden.py --check` | 三組 22 顆**逐項相同** |

#### 3.1.7 Input 段的卡片群：**一種 source 一張卡**

使用者定調（2026-08-17）：

> 你不一定要把它全部塞到 load image 這張 card 裡，我更想像的是像其他 card 一樣分類
> （**應該說 source 不一樣本來就要分**）。同理 GDS 相關的 png 理所當然也可以是一張 card。
>
> 簡單來說目前 ADEPT 可以支援 patch + 對應 KLARF，我需要他也能支援
> **RSEM image + KLARF，或單純圖片**。

| 卡 | 一顆給什麼 | 吐的流 | 狀態 |
|---|---|---|---|
| `load_patch`（EBI patch）| 主資料集的那幾頁 | 依 `channel_map` 命名（預設沿用現行行為）| 有，要加 `channel_map` |
| `load_rsem`（RSEM 大圖）| 一張大圖（**有 KLARF 或沒有都要能吃**）| `rsem` | 新 |
| `load_layout`（GLAS 的匯出）| label map ＋ 合成 gray | `layout_label`、`layout_gray`（**兩顆輸出埠**）| 新 |

一種 source 一張卡的三個好處，剛好對上既有的三條規矩：

- **卡片自己的參數只講自己的事**（RSEM 的配對規則不會出現在 patch 卡上）；
- **畫布看得到有幾個來源**（一個來源一個節點，F9 的「線只有一個作者」）；
- **`Step.is_source()` 已經支援任意張數**（Input-0 就是為了這個）。

##### ⚠ 那「檔案在哪」寫在哪裡？—— **recipe 宣告插槽，資料層綁路徑**

這是 Input-3 真正的設計題，而它有一個一眼看不出來的陷阱：把 RSEM 的**路徑**寫進
`load_rsem` 卡的參數，recipe 就綁死一批資料 —— 換一個 lot 要改 recipe，
而 recipe 是「站點差異」的家，不是「這一批資料在哪」的家（最高指導原則）。
KLARF 本身從來沒有寫在 recipe 裡，就是這個道理。

所以：

```
recipe（可攜）        load_rsem 卡說：我要一個叫 "rsem" 的來源，配對規則 = 檔名
資料層（每批不同）    Studio 的載入對話框／CLI 的 --rsem <路徑> 把插槽綁到真的檔案
lint                 「這份 recipe 需要一個 rsem 來源，你還沒有指定」← 跑之前就講
```

卡片的參數因此是**插槽名 + 配對規則 + 流名**，不是路徑。這也讓同一份 recipe
在「有 RSEM」與「沒有 RSEM」的兩批資料上有明確的行為差異（後者 lint 就擋下來），
而不是安靜地少一條流。

`channel_map` 的三個設計點：

1. **預設值 = 現行行為**（空的就照 dataset 給的名字：`test`, `ref`, `img3`…）。
   這樣**不需要遷移**，而且黃金值逐項相同 —— 鐵則 9 說遷移不能靠「新東西不在」
   判斷，而這裡根本不必判斷：新參數的預設值就是舊行為。
2. **UI 是一個小表格**（每列：第幾頁 → 叫什麼），不是一行逗號字串 ——
   五頁的時候逗號字串數不清位置。這需要一個新的 `ParamSpec.type`
   （像 `curve` / `template` 那樣有自己的編輯器）。
3. **頁數不符要擋下來**（因為設定放在 recipe 裡）：`channel_map` 宣告了五頁而
   這批資料每顆只有兩頁（或反之）→ `Step.configuration_issues()` → lint，
   在跑之前就講一句可以照做的話。**不准安靜地照順序硬套** ——
   那正是「跑得完、有數字、而且是錯的」。

#### 3.1.8 Input 現在吃得下什麼檔案／格式（**量出來的，不是讀 code 推論**）

##### 影像

| 形式 | 現況 | 走哪條路 |
|---|---|---|
| **多頁 TIFF**（一批一檔，每顆佔連續幾頁）| ✅ 支援，頁數由**每顆的 `IMAGECOUNT`** 決定 | `tiff_index`（免解碼盤點，含 **BigTIFF**）→ `tifffile` 讀單頁 |
| **每顆一個影像檔**（KLARF 帶檔名）| ✅ 支援 `.png` `.tif` `.tiff` `.jpg` `.jpeg` `.bmp` | `imageio.load_gray`（`np.fromfile` + `cv2.imdecode`，**CJK 路徑安全**）|
| **資料夾**（沒有 KLARF）| ✅ 支援，同上副檔名 | 同上 |
| 彩色（BGR／BGRA）| ✅ 自動轉灰 | `ensure_gray` / `load_gray` |
| **一顆一個多頁 TIFF**（N 頁 = N 通道）| ❌ 接頭 B | — |
| **一顆一個資料夾**（每通道一檔）| ❌ 接頭 B | — |

##### ⚠ 位元深度：**兩條路都會安靜地毀掉數字**（實測）

兩條路對非 8-bit 的處理不一樣，而**兩條都是安靜的**（不會有任何警告）：

```
一張 12-bit 的圖（值域 0–4095，4096 個灰階）：

路徑 A（ebi_patch → to_uint8）    : clip 到 0–255 → **93.8% 的像素飽和成 255**
路徑 B（rsem/folder → load_gray） : 每張圖各自 MINMAX 拉到 0–255
   └ 後果：把同一張圖的亮度砍半再載入，平均值 127.5 vs 127.5（**一模一樣**）
     ＝ 兩張圖之間不再可比，而 test − ref 的整個前提就是可比
```

路徑 A 是**現在唯一開放的那條**（`scope.py` 只開 `ebi_patch`）。所以：
**如果廠內的 patch 是 16-bit（或 12-in-16），現在算出來的每一個數字都是垃圾** ——
一張幾乎全白的圖，而且沒有任何錯誤訊息。這是 Input 段第一個要解的格式問題，
而且它是**可探測的**（bit depth 就在 TIFF 標頭裡，`fab_probe` 讀得到）。

修法有三個層次，代價差很多（要討論）：

| 做法 | 代價 |
|---|---|
| **① 固定位移**（12-bit `>>4`、16-bit `>>8`），對整批一致 | 最小改動、維持可比、8-bit 管線不動。丟精度（12→8 bit）|
| ② 載入時**不**降位，內部管線改 `float32` | 精度全留。但**黃金值全部改變**、每張卡都要複查值域假設 —— 那是一輪自己的工作 |
| ③ 讓使用者選（recipe 參數）| 彈性，但兩條路都要維護，而且使用者要懂位元深度 |

我的建議是 **① 先做**（它把「垃圾數字」變成「精度少 4 bit 的正確數字」），
②列成一個獨立的項目排在 Measure 段之後 —— 那時候才知道 8-bit 夠不夠。

##### defect 清單與座標

| 形式 | 現況 |
|---|---|
| **KLARF 1.2 / 1.8** | ✅ 無損讀寫（`klarf_core`，最重要的資產），已知四種 image-layout 變體 |
| KLARF 的座標（XREL/YREL）| ✅ 依 `unit_info()` 換算成 nm（1.2 是 µm → ×1000、1.8 是 nm）|
| **沒有 KLARF**（純資料夾）| ✅ 有，但沒有座標、沒有 die |
| **CSV／Excel 的 defect 清單** | ❌ 接頭 A（觸發條件是「沒有 KLARF 的機台」，還沒發生）|
| `ground_truth.json`（答案卷）| ✅ Studio 載資料時自動撿 KLARF 旁邊的那一份 |

##### sidecar（同一顆的附加檔）—— 全部還沒有

`<DEFECTID>_label.png`（uint8 label map）、`<DEFECTID>_gray.png`、
manifest JSON（`label_map`）、alignment CSV／JSON。契約已經寫好在
[`../GLAS-INTERFACE.md`](../GLAS-INTERFACE.md)，接頭 D。

##### 格式問題的答案（使用者 2026-08-17）

| 題 | 答 | 後果 |
|---|---|---|
| 位元深度 | **8-bit** | 位元深度那一條**降級**：不做管線改造。但要補一道**擋下來** —— 拿到非 8-bit 的資料時講一句話，不准安靜飽和／各自拉伸。假設 #4 從「猜錯就毀掉數字」變成「已知 8-bit，但程式不該把它當成保證」|
| 五通道怎麼裝 | **在大 TIFF 內，但這種大 TIFF 通常不伴隨 KLARF** | ⚠ **這一句把接頭 B 從「以後再說」變成「多通道能不能進來」的前提** —— 見 §3.1.10 的 Input-2 |
| TIFF 壓縮 | 不清楚 | 不阻塞（`tifffile` 吃得下大多數）；探測腳本可以順手回答 |
| 影像尺寸 | **同一組 data 每顆相同，不同組可能不一樣** | 正規化座標的設計是對的（跨組成立）。而且「同一批之內一致」反過來是一道免費的防呆：一批之內尺寸忽然變了就是資料問題，該講出來 |

#### 3.1.9 多入口真正要解的事：patch ↔ RSEM 對位

使用者說明了他要多入口的原因：

> 之後會想要做 **patch 對 RSEM image 做 match**（patch 是小張圖、RSEM 是大張圖，
> 利用 align 來對齊 layout）。一個是 EBI 機台掃的、另一個是 RSEM 機台拍的
> （**但會有 offset**），**SEM condition 也不一樣**。對齊可以幫我們做後續分析，
> 所以我會想把功能寫好，我會想在這邊就把可以 input 的入口做好。

這件事需要的東西比「一份資料的兩個通道」多一層：**兩個機台、兩個資料集、逐顆配對**。
現況量出來四個事實（三個好消息、一個壞的）：

| 事實 | 量出來的結果 |
|---|---|
| `Context` 允不允許兩條**不同尺寸**的流共存 | ✅ 可以（`set_image` 不綁尺寸）。所以 128² 的 patch 與 512² 的 RSEM 可以同時在一顆裡 |
| `subtract` 對尺寸不符的處置 | ✅ 擋下來並講清楚：`'patch' and 'rsem' differ in size ((128,128) vs (512,512)); cannot subtract.` |
| **`align` 對尺寸不符的處置** | ❌ **警告 + 零位移**。五個 backend（phase／ncc／ecc／hybrid／template）**全部要求同尺寸**。實測：把大圖裡 (300, 200) 那一塊裁出來當 patch，五個 backend 全部回 `dx=0, dy=0, score=0` —— 有一句警告，但那三個數字照樣流進分數。**對「小圖對大圖」這個用途，align 等於功能不存在** |
| 正確的工具在不在 | ⚠ **一半**。見下面「template backend 為什麼還不夠」|

##### 「align 裡的 template matching 應該就可以吧？」—— 讀了程式碼之後：**primitive 對了，座標數學不對**

使用者問得對，`cv2.matchTemplate` 就是這件事的工具。但 repo 裡現成的兩支
**都不是為「小圖進大圖」寫的**：

| 現成的 | 它實際做什麼 | 為什麼還不夠 |
|---|---|---|
| `align` 的 `template` backend（`algo/align.py::_calculate_alignment_template`）| 確實是 `cv2.matchTemplate(TM_CCOEFF_NORMED)` | template 取的是 **base 的中心裁切**（留 `search_radius` 的邊），而 `best_dx = peak_x - sr` 把結果面當成「**以零位移為中心**」—— 那個數學只在**兩張同尺寸**時成立。而且卡片的 `search_radius` 上限 64 px，patch↔RSEM 的 offset 可能上百 |
| `algo/template.py::match_patch`（`roi_template` 用的）| 是「把小圖滑進大模板」沒錯 | 它是為**週期性** layout 寫的：把 cell 平鋪成 canvas、再把相關面**摺回一個週期**（同相位取最大）。非週期的 RSEM 大圖用它，信心值會是錯的 |

所以要補的是**同一個 primitive 的第三種座標數學**：
template = **整張小圖**（可選去掉邊緣幾 px 的 scan artifact）、搜尋**整張大圖**、
peak = 小圖左上角在大圖裡的**絕對位置**（不是相對位移），
**搜尋範圍不受 `search_radius` 限制**。工作量是一個 algo 函式（約 30 行）+ 一張卡
—— 比「寫新演算法」小得多，但**不是「已經可以」**。

##### 提案：新卡「Locate in a larger image」（Compare 段）

| | |
|---|---|
| 吃 | 小圖流（patch）＋ 大圖流（rsem）—— 兩個 `image_key` 輸入埠 |
| 吐 | `match_dx` / `match_dy` / `match_score` / `locate_ok`，**外加一條與 patch 同尺寸的裁切流**（例 `rsem_crop`）|
| 為什麼要吐裁切流 | 吐了它，**下游所有既有的卡一行都不用改** —— 量測卡、`subtract`、ROI 全都是在「同尺寸的兩條流」上工作的。跟 ROI 三條路共用出口是同一個手法 |
| SEM condition 不同 | 對位前要正規化（`normalize` 的 `match`）。寫進 help，而且做成 `configuration_issues()` → lint，不是只在說明裡提一句 |
| 失敗處置 | `locate_ok=0` + 不裁切，**不殺整批**（鐵則 7）。跟 ROI 定位法同一個慣例，使用者已經認得 |
| 順帶要修的 | **`align` 尺寸不符時應該報錯，不是零位移** —— 「警告 + 0」讓一件做不到的事看起來像做完了 |

##### 兩題要你定

1. **patch 與 RSEM 怎麼配對？** RSEM 那邊如果是「大 TIFF 沒有 KLARF」，可用的只有
   **順序**（第 k 顆 ↔ 第 k 個頁組）或**檔名**。順序最省事但最脆（少一顆就全錯一位），
   所以我會做成參數 + 一道防呆（兩邊數量不符就擋下來）。你手上的 RSEM 資料
   **有沒有自己的 KLARF 或清單**？
2. **對位之後你要什麼？** ①裁切流（可以接所有既有量測卡）②只要 offset 數字
   ③兩個都要。預設做③，先做①。

#### 3.1.10 三個接頭的規格

順序照定調的 C → D → B → A，但**B 的一半提前**：多通道的資料是「大 TIFF 沒有 KLARF」，
所以 `tiff_stack` 是 C 能不能進來的前提。

##### Input-1 — `channel_map`（頁 → 流的命名）**✅ 完成 2026-08-17**

三個設計點全部照做：

1. **預設值＝現行行為**（空字串 = 照 ingest 給的名字）→ **不需要遷移**，
   黃金值三組 22 顆逐項相同。
2. **UI 是一張小表**（`widgets.ChannelMapField`）：一列一張圖，
   **左邊的位置是程式寫的（打不錯）、右邊的名字才是使用者打的**；空著的那一列
   就是「這一張不命名」，而 placeholder 寫出它不命名時會叫什麼（`test`/`ref`/`img3`…）
   —— 使用者看得到自己在改什麼。新的 `ParamSpec.type="channel_map"`。
3. **宣告與資料不符就擋下來**：宣告了第 5 張而這顆只有 2 張 → `StepError`，
   訊息講得出「去哪裡改」（`Fix “Name the images”…`）。**不准照順序硬套**。
   反過來（資料比命名的多）→ 載入命名的那幾張 + `ctx.warn` 講出**哪幾張**沒載入
   （中間跳號也看得見）。

值的格式與規則在新模組 `pipeline/channels.py`（照 `curve` 那條路：自己的
parse／format／錯誤類別，正規化成「依頁碼排序、`", "` 分隔」——
**round-trip 必須是 identity**，不然 `workers=1` 與 `workers=2` 會算出不同分數）。

改名只改「流叫什麼」，讀圖仍然走 ingest 自己的 key（`src_of` 這一層）——
第一版漏了它，`item.load("bse")` 當場 KeyError，測試抓到。

驗收：`tests/test_f11_channel_map.py`（21 條，含**真的 KLARF + 真的 10 頁 TIFF、
兩顆各五張**的端到端：第二顆的五張是絕對頁號 6–10，而它的 `bse` 仍然是**自己的
第 2 張**）＋ `tests/test_ui_f11_channel_map.py`（7 條）。
核心 1046 passed／UI 35 檔全綠／黃金值逐項相同。

**還沒做（下一輪順手）**：表格的列數目前要按「Add another image」自己加。
資料載進來之後其實知道「每顆幾張」（`load_patch` 的 F7-17 面板就印著），
把那個數字接到編輯器上就能預先排好列數 —— 那要把資料層的資訊接進 `ParamForm`。

##### Input-2 — 大 TIFF 沒有 KLARF（`kind="tiff_stack"`）**✅ 完成 2026-08-17**

做出來的東西：`dataset.load_tiff_stack(path, per_defect)`、Studio 工具列的
**`Open stack…`**（自己的入口 + 自己的 `stack` 自繪圖示 —— 併進 `Open KLARF…`
的話使用者按下去之前分不出自己要的是哪一種）、`scope.SUPPORTED_KINDS` 加
`tiff_stack`。

**分組（資料層）與命名（recipe）刻意分開**：`per_defect` 在載入時問（那是機台
怎麼收的），名字由 `channel_map` 決定（Input-1）。分不開的話，同一批資料的
「一顆幾張」會因為換一份 recipe 而改變。

順帶修掉 `load_folder` 的謊：多頁 TIFF 在那條路上**只讀得到第 0 頁**
（`cv2.imdecode`），而以前一句話都沒有 —— 一個 15 頁的檔案安靜地變成一顆 defect。
行為刻意不變（那條路的定義就是「一個檔案一顆」），改的是**它會講出來**並指向
`Open stack…`。

**「沒有 KLARF」講在哪裡：狀態列不夠。** 第一版寫在載入訊息裡，測試當場紅 ——
載完就接著算預覽，那句話幾毫秒後被 `Computing preview…` 蓋掉。**同一個教訓
ground truth 那一輪學過**（`_on_dataset_loaded` 的註解就寫著）。改成掛在**資料集
標籤**上：`tiff_stack · defect 1 / 3 · no KLARF`，tooltip 講完整句（寫不回 KLARF、
CSV／Excel 還在）。常駐、在眼前，而且它講的正是「你現在手上是什麼資料」。

對不齊的尾巴**不吞掉**：15 頁 ÷ 4 → 3 顆 + 剩 3 頁，剩下的不進任何一顆並在
`warnings` 講出剩幾頁（安靜塞進最後一顆的話，那幾頁的數字會出現在錯的 defect 上）。

驗收 `tests/test_f11_tiff_stack.py`（11 條，含「第三顆拿的是第 11–15 頁」與
**Input-1＋Input-2 合起來**的那條：五張一顆 + BSE 在第 2 張）＋
`tests/test_ui_f11_tiff_stack.py`（6 條）。核心 1061 passed／UI 36 檔全綠／
黃金值逐項相同。

---

##### Input-2 的原始規格（保留）

**現況實測**：一個 15 頁的 TIFF 丟進 `load_folder` → **1 顆 defect，而且只讀得到
第 0 頁**（`imageio.load_gray` 走 `cv2.imdecode`，多頁 TIFF 只解第一頁）。
所以今天這種資料進來會**安靜地變成一顆**。

規格：

- **頁怎麼分組**：每 N 頁一顆，N = `channel_map` 宣告的通道數（N=1 就是每頁一顆）。
  頁數不是 N 的整數倍 → 擋下來（那是資料或設定錯了，不是四捨五入）。
- `defect_id` = 頁組序號（或 `<檔名>_<序號>`，看跟 RSEM 的配對怎麼定）。
- 沒有座標、沒有 die、沒有 KLARF → **不能寫回 KLARF**（輸出只有 CSV／報表）。
  這件事要在 UI 上先講，不是等使用者按了 Export 才發現。
- 讀單頁一律走 `tiff_index.read_page`（`tifffile`），**不要**走 `cv2.imdecode`。

##### GDS 的 source 放 Input 還是放 ROI 段？—— **載入放 Input，解讀放 ROI**

使用者問的。我的答案與四個理由：

| 理由 | 說明 |
|---|---|
| **GLAS 給的是兩個檔，用途不同段** | `_label.png` 是**區域**（ROI 段要）、`_gray.png` 是**影像流**（Compare 段當合成 ref）。放進 ROI 卡的話，gray 那一半就沒有家 —— 而它們是同一個來源的兩個輸出，一張 Input 卡兩顆輸出埠正好 |
| **快取簽章** | 影像段快取是照「`DefectItem` 帶著哪些來源」算簽章的。ROI 卡自己讀檔的話，**換了 mask 目錄簽章看不見** → 回舊影像（鐵則 9，F9 踩過兩次）|
| **同一條流會有第二個消費者** | overlay 要畫 label、以後「gray 當 ref」也要它。讀檔藏在 ROI 卡裡，第二個用途就得再讀一次檔（於是有兩份配對規則，其中一份會長歪）|
| **畫布不能說謊** | 一個來源在畫布上要有一個節點、一條線。ROI 卡裡偷偷冒出資料，就是 F10 修掉的那個形狀 |

**但使用者體驗上「GDS 的事在一個地方」這個訴求是對的**，所以不靠合併卡片來達成：
ROI 卡的**右下角儀表**（`ui/inspectors.py` 依 `Step.key` 註冊）顯示 label 上色預覽、
對到幾個區域、對位分數。設定在 Input、**看**在 ROI —— 兩邊都在使用者眼前。

（反面論點也記著：如果哪天 GDS 那條路變成「一張卡從頭到尾自己搞定」，
那就是這個決定要重看的時候。判準是「有沒有第二個消費者」。）

##### Input-3 — 第二個資料來源，逐顆配對（**一個機制、三個用途**）

RSEM 大圖、GLAS 的 `_label.png`、GLAS 的 `_gray.png` 是**同一件事**：
「跟這一顆一一對應的另一個影像來源」。所以做成一個機制：

```
主資料集（EBI patch）
  └─ attach(來源, 配對規則, 流名) ─→ DefectItem 多帶幾個 ImageRef
        例：attach(rsem_stack, by="order",     name="rsem")
            attach(glas_dir,   by="defect_id", name="layout_label")
```

- **配對規則是參數**（`defect_id` / 檔名 / 順序），不是寫死的猜測。
- **配不上的那幾顆要看得見**：不是靜靜地少一條流，而是一個列得出來的清單
  （「24 顆裡有 3 顆沒有對到 RSEM」）。
- 檔案 I/O 只在 ingest 層（§3.1.3：配對規則只有一份、**快取簽章看得見**、
  畫布上是一條真的流）。

#### 3.1.11 還沒定的

- **patch ↔ RSEM 的配對規則**與「對位之後要什麼」（§3.1.9 的兩題）。
- `layout_label` / `layout_gray` 的配對規則等 GLAS 的樣本到（見
  [`../GLAS-INTERFACE.md`](../GLAS-INTERFACE.md) §5）—— 但機制與 RSEM 那條共用（Input-3）。
- 五頁的順序（假設 #5）與 TIFF 壓縮方式要不要寫一支探測腳本帶回來。
  位元深度（假設 #4）使用者已答 **8-bit**，所以那條降級成一道防呆。

#### 3.1.12 Input 段的做事順序（**接下來就照這個做**）

| # | 做什麼 | 為什麼排這裡 |
|---|---|---|
| ✅ Input-0 | 多入口（`Step.is_source`）| 其餘全部踩在它上面。**完成 2026-08-17** |
| ✅ Input-1 | `channel_map`：頁 → 流的命名（含頁數不符擋下來）| **完成 2026-08-17** |
| ✅ Input-2 | `tiff_stack`：大 TIFF 沒有 KLARF | **完成 2026-08-17**（順帶修掉「15 頁 TIFF 安靜變成一顆」）|
| Input-3 | **插槽機制** + `load_rsem` / `load_layout` 兩張卡（一種 source 一張卡，§3.1.7）| patch ↔ RSEM 的前提；RSEM 與 GLAS 共用同一個機制 |
| Compare-1 | 新卡「Locate in a larger image」（matchTemplate 的第三種座標數學，§3.1.9）＋ 修 `align` 尺寸不符要報錯 | 對位本身。Input-3 進來之後才有兩條流可以對 |
| 防呆 | 非 8-bit 就講一句話；一批之內尺寸忽然變了就講一句話 | 兩個都是幾行的事，但擋掉的是「安靜地算出垃圾」|

### 3.2 Enhance

| | |
|---|---|
| 現在有什麼 | `normalize`（4 method）、`tone`（亮度/對比/gamma/曲線/反相）、`denoise`、`flatten`（去背景/條紋/top-hat）。F7-20 已從 9 張收成 4 張 |
| 缺什麼 | 多通道進來之後的融合（PCA Ref、BSE·SE quadrant）—— 它們是「N 條流 → **一條新的流**」，所以踩 §4.1 的命名契約 |

**要討論的**

- 融合卡放哪一組？它產生新流（像 `subtract`），所以可能屬於 **Compare** 而不是
  Enhance。組別不是裝飾 —— 卡片庫是照 `Step.group` 排的，放錯使用者就找不到。
- 融合的順序：**先融合再處理**還是**先處理再融合**？（會決定 recipe 的典型長相，
  也決定要不要在 help 裡明講。）
- PCA 的成分數、要不要凍住（同一份 recipe 跨顆要用同一組基底嗎）——
  這一題很像 Golden Cell 的「模板凍進 recipe」，可以照抄那個做法。

### 3.3 Region（ROI）

| | |
|---|---|
| 現在有什麼 | `roi_cross`（Profile，純規則）、`roi_template`（Template，Golden Cell）、`roi_mask`（區域 → mask 流）|
| 缺什麼 | **第三條路**：吃 GLAS 的 label map（暫名 `roi_from_mask`）|

**要討論的（Region-1：`roi_from_mask`）**

- ⚠ **檔案 I/O 不在這張卡**（§3.1.3 的提案）：mask 由 **Input 段的 sidecar 接頭**
  載成一條流（例如 `layout_label`），這張卡吃**流**、吐具名區域。
  所以它的參數裡**沒有目錄、沒有配對規則**，只有「吃哪一條流、label 怎麼變成名字」。
- 參數：要不要只取某幾個 label／尺寸不符怎麼辦（拒絕 or 縮放 + 警告）。
- 區域的名字從 manifest 的 `label_map` 來（layer 名），使用者不用手打 ——
  但名字要能當變數用（`pattern` 擋空白與減號）。
- 右下角儀表：label 上色預覽 + 「這一顆對到了幾個區域、對位分數多少」。
- 出口照既有契約（吐具名區域）→ **下游零改動**。
- 家用機怎麼驗：`tools/` 補一支合成 label map 產生器（與合成 lot 一一對應）。
  新功能只能用真實資料驗證的話，它在家用機上就等於不能驗證（`AGENTS.md` §1）。

### 3.4 Compare

| | |
|---|---|
| 現在有什麼 | `align`（5 backend）、`subtract`（Compare two streams）、`golden_cell` |
| 缺什麼 | ① **沒有 ref 的資料要跟什麼比**（§3.1.4 的三個候選）；② GLAS 的 `gray` 當 ref（die-to-database）；③ 對位可以**吃 GLAS 已經算好的 offset**（省一次對位，而且那是對 layout 對的，比對 ref 準）|

**要討論的**

- **五頁資料的 Compare 路線**（§3.1.4）：Golden Cell／GLAS 合成 gray／通道互比
  —— 這一題的答案會決定 Enhance 段那兩張融合卡到底是「多一張圖」還是「產生 ref」。
- `align` 要不要多一個 method：「從 GLAS 的 alignment CSV 讀 offset」。
- 合成的 `gray` 與真 SEM 的灰階分佈不同 → 前面要接 `normalize` 的 `match`，
  這件事要寫進 help 還是做成卡片的前置檢查（`configuration_issues()` → lint）。

### 3.5 Measure

| | |
|---|---|
| 現在有什麼 | `glv_stats`、`roi_snr`、`cd_measure`、`snr_map`、`focus_quality`、`cell_period` |
| 缺什麼 | ① **blob 分割**（§1.2，演算法要重寫）；② **離群旗標**（跨顆統計，不是單顆）；③ Region Stats / FFT；④ `snr_map` 多來源（§4.1）|

**要討論的**

- **blob 重寫要改良什麼**：門檻怎麼定（現在是 SNR map 灰階門檻）、要不要吃
  `roi_mask` 限定範圍、主 blob 的挑法（現在是 SNR 最強；「離報點最近」在 ADC 上
  常常更對）。**輸出契約不能改**：`ctx.meta["blobs"]` 的 `x/y/w/h/area/snr_value`
  已經被 overlay 與 export_dialog 讀（§1.2）。
- **離群算在哪一層**：Tukey IQR 是**跨顆**的，而 `run_defect` 一顆一顆跑 ——
  所以它不是普通量測卡。`store/` 已經有 rescore 的路，可能是那一層的事。
- Region Stats 的 FFT 那一半不必從零開始：`algo/period.py` 的 rFFT 與相位搜尋在
  （`CLAUDE.md` §5 明講那個模組不要刪）。

### 3.6 ADC —— **這一段要先設計資料結構，不是加一張卡**

| | |
|---|---|
| 現在有什麼 | recipe 上一個 `ScoreSpec(expr, threshold, bins)`；UI 一個假節點 `__score__`；**只分得出 bin 0 / bin 1**（§1.1）|
| 缺什麼 | **多類別**。真正的 ADC 要吐好幾個 class；KLARF 寫回也已經支援 CLASSNUMBER / ROUGHBIN / FINEBIN（M5 做完了），所以缺的是**判定那一層** |

**要討論的（這一段最少要三輪）**

1. **規則怎麼表達**：一串「條件 → class」的規則（第一個命中的贏）？
   每個 class 一條表達式取最大？決策樹？
   —— 傾向「一串有序規則」，因為它是**製程工程師講得出來的形狀**
   （「SNR 大於 5 而且面積大於 100 就是 Particle」），而且看得懂＝改得動。
2. **UI 怎麼看**：現在是「一張直方圖 + 一條可以拖的門檻線」，多類別之後那個
   互動要重新設計（每條規則一個直方圖？混淆矩陣？）。
   ⚠ Phase 1 換來的「拖門檻即時重算準確率」不能弄丟 —— 那是調參迴圈的核心。
3. **相容**：舊 recipe 的 `below/above` 要能無痛升級（遷移只能靠「舊東西在不在」
   判斷 —— 鐵則 9）。
4. **ML Classify 是這一段的一個 method 還是一張卡**（Phase 2 後半再定；
   相依策略也留到那時候）。

---

## 4. 跨段的契約（先定，不然每張卡各發明一套）

### 4.1 產流卡的輸出命名（`snr_map` 多來源、融合卡、會吐圖的 Region Stats 共用）

F10 §6 刻意留下的題目。**提案，照 F10-3 量測卡的先例**：

| 接幾條線 | 輸出流叫什麼 |
|---|---|
| 一條 | **就是 `out` 的值，逐字不變** |
| N 條 | `<流名>_<out>`（例：`test_snr_map`、`diff_snr_map`）|

「一條的時候逐字不變」是**黃金值不動**的前提，而量測卡（F10-3）就是這條規則的
另一半（兩條流才加流名前綴、只接一條時特徵名逐字相同）—— 兩邊同一條規則，
使用者只要學一次。

要一起改的三處：`resolve_writes`（畫布才畫得出正確數量的輸出埠）、
**快取簽章**（鐵則 9）、那張卡的 inspector 面板要顯示 N 張圖。

### 4.2 ROI 出口（已經有，不要動）

三條定位法（純規則／Golden Cell／GLAS mask）**出口相同：吐具名區域**。
下游（量測卡、`roi_mask`、overlay、region check）零改動。
不要幫量測卡加 mask 流輸入、也不要讓區域卡直接吐 mask ——
兩條平行的路會腐爛（`ARCHITECTURE.md`，F7-17 的教訓）。

---

## 5. 驗收（整輪）

Phase 1 立起來的安全網**全部自動套用到新卡**：

| 層 | 對 Phase 2 的意思 |
|---|---|
| 黃金值（`tools/freeze_golden.py --check`）| 新增卡片不得改變既有三組 22 顆的任何一項。**除了 §7.1 選 B**，那要重新定錨 |
| 六條卡片不變量（`tests/test_card_invariants.py`）| 對 registry 裡每一張卡自動跑 |
| F10 的畫布不變量（`tests/test_ui_f10_canvas_reality.py`，20 條）| 同上 |
| 兩支稽核腳本（11 項）| 每一段做完跑一次 |

---

## 6. 順手做掉的

- **文件漂移（1 MB 上限）**：`docs/FAB-VALIDATION.md` 曾叫公司機複製
  `bundle/ADEPT_part1of6.py … part6of6.py`（**那些檔案不存在**，現在是單檔
  `ADEPT_bundle.py`）；`SESSION_LOG.md` 開頭那句「離 1 MB 只剩不到一成」。
  兩處都在 2026-08-17 修掉並連回 `AGENTS.md` §2。

---

## 7. 待使用者定調

### 7.1 演算法移除 —— **A，已執行（2026-08-17）**

使用者定調 **A**：「移除 blob 跟 stat 跟相關測試就好。」做掉的：

```
adept/core/algo/blob.py      （155 行，vendored from Fusi³）
adept/core/algo/stats.py     （85 行，vendored from PEAR）
tests/test_blob.py  tests/test_stats.py
adept/core/algo/__init__.py 的兩行 re-export
```

`tests/test_export_overlay.py` 有一條 import 過 `DefectROI`，改成一個**最小替身** ——
它要驗的本來就是 `overlay` 吃 dict **也**吃有 `x/y/w/h` 屬性的物件（duck typing），
不是那個 dataclass 長什麼樣。之後重寫的 Blob 卡若吐 dataclass，那條就是它接得上
overlay 的保證。

驗證：核心測試 **1010 passed / 34 skipped**（只有 FILELIST／bundle 那三條因為檔案
變動而紅，重跑 `release.py` 後綠）。

#### 被移除的東西的**規格**（留著的理由本身是資產，所以搬到這裡）

重寫的時候這幾條是**需求**，不是實作參考：

- **blob 分割**（原 `segment_defects`）：吃一張 SNR map（uint8 或 float [0,1]）
  → 門檻 → 連通元件 → 每塊回 `x/y/w/h`、`cx/cy`（重心）、`area`（真實像素數，
  不是 bbox 面積）、`mean_signal`、`snr_value`、`aspect_ratio`、
  **`dist_to_center`（離影像中心多遠 —— patch 是以報點為中心裁的，所以這一項
  等於「離報點多遠」）**。
- 那張卡在 F8 第五輪（ROI 收斂成三條路）被拿掉的理由是
  **「它框的是缺陷本身，不是圖案上的位置」** —— 所以它**不屬於 Region 段**，
  它是 Measure 段的卡（見 §3.5）。
- 它也是 v2 backlog 上「**單張影像、沒有 ref 也沒有週期**」那條保底路線的材料
  —— 而那條路線現在有了具體的資料（五頁 BSE+SE **沒有 ref**，見 §3.1），
  所以它的優先度比原本高。
- **離群**（原 `group_outliers`）：Tukey IQR，`[Q1 − k·IQR, Q3 + k·IQR]` 之外算離群，
  **組內**比較（k 預設 1.5）。連帶兩個評估用的量：`cohens_d`（兩組平均差的標準化）、
  `attribute_separability`（η²，一個量有多少變異是組別解釋的）——
  後兩個是「這個特徵分得開嗎」的量化，跟 ground-truth 準確率是互補的東西。

#### 還留著的懸空引用（等 Blob 卡回來才解得掉）

`cd_measure` 與 `roi_snr` 的警告仍然寫「run Blob segment first」，
`ctx.meta["blobs"]` 與 `overlay` 的主 blob 紅框仍然沒有生產者。
**刻意不動**：那三處指向的是**接下來要做的那張卡**，把字改掉只是把缺口藏起來。
engine 對區域名 `blob` 的保留字處理（`recipe.validate` 的 `unknown-region`）也留著
—— 它現在會在跑之前就說「你指到一個沒人定義的區域」，那正是對的行為。

### 7.2 五頁資料要不要寫成「待驗證假設 #4」+ 一支探測

「BSE 在第 2 頁」目前是口述的事實。`docs/FAB-VALIDATION.md` 的機制是
「假設 + 一支可以在公司機跑的探測腳本」，而假設 #1 只確認過兩頁的情形。
要不要照那個機制走一次（`fab_probe/` 加一支或擴充 `probe_klarf.py`：
印出每顆 defect 有幾頁、各頁的尺寸與平均灰階，預設遮蔽識別碼）？
成本是一支單檔腳本、一次複製，換到的是「五頁的順序」寫成可驗證的事實。

### 7.3 第一段從哪一張卡開始

照左側順序就是 **Input-1（頁怎麼命名）**。但它會動到 `load_patch` 的預設值
（要附遷移 + 黃金值逐項相同），而 §3.1 那三個名字問題要先有答案。
要不要就從它開始？
