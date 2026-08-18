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
| 多通道 | **⏸ 暫時不做**（2026-08-17 下午：「我決定我暫時不做 multi channel（多通道的），暫時 focus 在 patch 跟 RSEM Image」）。事實記著：1 BSE + 4 SE、BSE 固定第 2 頁、沒有 ref。**做出來的兩個機制不是多通道專用的**，見 §3.1.14 |
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

##### Input-3 — 四種輸入都進得來 **✅ 完成 2026-08-17**

使用者把 Input 段的範圍講清楚了：

> **配對是之後的事吧（或者之後的功能），別忘了我們在 input 階段。**
>
> 簡單來說目前 ADEPT 可以支援 patch + 對應 KLARF，我需要他也能支援
> **RSEM image + KLARF，或單純圖片**。

所以 Input-3 不是「兩個來源逐顆配對」（那是 Compare 段的事，見下一節），而是
**把四種 source 的入口做齊**。而那四種的 core 能力早就在，被 `scope.py` 收著：

| kind | 入口 | 這一輪做了什麼 |
|---|---|---|
| `ebi_patch` | `Open KLARF…` | 本來就有 |
| `rsem` | `Open KLARF…`（自動判別）| **打開**（`SUPPORTED_KINDS`）|
| `tiff_stack` | `Open stack…` | Input-2 |
| `folder` | **`Open folder…`**（新）| 打開 + 新入口 + `folder_open` 自繪圖示 |

**`HIDDEN_STEPS` 清空**：`golden_cell` / `cell_period` 回到卡片庫。收著它們的理由
是「它們存在的唯一目的是幫**單張影像**疊 ref，而 Studio 只吃兩兩成對的 patch」
—— 單張那條路打開了，繼續收著等於把功能打開一半。

##### 打開之後，兩條既有的不變量當場抓到兩個缺口

1. **`cell_period` 從來沒有做過 F10-3 的多來源處理。** 它被收起來的那段時間，
   「量測卡都接得了好幾條來源」那條不變量**跳過**它（那條測試會 skip
   `HIDDEN_STEPS` 裡的卡）。一解除隱藏就紅了 —— 於是它改成 `MultiSourceStep`。
   **這正是那條不變量存在的理由**：它逐張套用到 registry，所以一張卡重新可見的
   時候不會安靜地少一半功能。
   （`golden_cell` 讀的 `ctx.meta["cell_period"]` 改成 `setdefault` —— 接好幾條流
   時**第一條就定案**，不讓最後一條無聲地決定 Golden Cell 的週期。）
2. **route 型別從來沒有真的跟著資料走。** 那一行的條件是「畫布是空的」，
   而 F7-9 之後**開窗就有一張起手卡**，所以它永遠是 False —— 在只支援一種輸入
   的時候看不出來。四種輸入之後的症狀是：載一份 rsem 資料，pipeline 還留在
   `ebi_patch` 那條 route 上，於是 lint 依 kind-aware 宣告以為有 `ref`，
   而執行期才發現沒有。判準改成 **`model.dirty`**（`RecipeModel.starter()` 特意
   把它設 False）：使用者還沒動過就跟著資料走；動過了就**不偷改他的 pipeline**，
   而是講出「這條 pipeline 是給 X 資料的，你剛開的是 Y」。

驗收：`tests/test_ui_input_kinds.py`（9 條 —— 這個檔案原本叫 `test_ui_patch_only.py`，
鎖的是**相反**的事；F7-1 的用字是「暫時只支援 patch」而做法是收起來不刪掉，
所以這一輪打開只改了兩個常數，**那個判斷被驗證了**）。核心 1061 passed／UI 36 檔全綠／
黃金值逐項相同。

---

##### （原 Input-3 的內容）第二個資料來源，逐顆配對 —— **移到 Compare 段**

使用者：「**配對是之後的事**。」下面這一段留著當那一輪的起點：

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

#### 3.1.13 **Input 卡按 source 拆開**（Input-4，✅ 完成 2026-08-17）

> 我還是傾向不同資料流（IMAGE SOURCE）卡片要拆分不要放在一起耶，這樣放在一起
> 反而變得很複雜。例如我現在 load 一張 RSEM image 他就是單張的～但其後的 NODE
> 節點會有 TEST 跟 REF？但實際上是 Single。**這樣畫布跟實際對不起來。**

量出來的實情比回報的更糟 —— 同一個問題「這張卡吐哪幾條流」有**三個不同的答案**：

| 誰回答 | 對 rsem 資料的答案 |
|---|---|
| `resolve_writes`（靜態宣告）| `["test"]` |
| `resolve_writes_for_kind(rsem)` | `["single", "test"]`（`single` 鏡射成 `test`）|
| **畫布上真的畫出來的** | **`["test", "ref"]`** ← 使用者看到的 |
| 資料真的有的 | `["single"]` |

**第一層（已修 2026-08-17）**：`model.kind` 是直接設的屬性，**不會通知 listener**，
而畫布的埠是照 kind 算的 —— 少了一次重畫，載 rsem 之後畫布還留著 patch 的
`test`/`ref`。修完之後畫布是 `single` + `test`。驗收
`tests/test_ui_input_kinds.py::test_switching_route_repaints_the_canvas`。

**第二層（要照使用者說的拆卡）**：`single` + `test` 仍然是「宣告比現實多」——
`test` 是 `load_patch.run()` 裡一段**寫死的鏡射**（讓下游用預設參數就吃得到圖）。
病根是**一張卡服務四種 kind，而它的宣告隨 kind 改變** —— 那就是
`resolve_writes_for_kind` 這個機制，也是三個答案的來源。

##### 提案：拆成兩張，而且 `resolve_writes_for_kind` 整個消失

拆的軸是**「一顆長什麼樣」**（那正是畫布上看得到的差別），不是檔案格式
（檔案格式已經由三個 Open 入口分掉了）：

| 卡 | 一顆給什麼 | 吐什麼 | 用在 |
|---|---|---|---|
| `load_patch`「Load images」| 好幾張 | **`channel_map` 表格裡的名字**（預設 `1:test, 2:ref`）| `ebi_patch`、`tiff_stack` |
| `load_single`「Load one image」（新）| 一張 | **一條**，名字由 `out` 決定（`image_key` + `direction="out"`，畫布跟著改名）| `rsem`、`folder` |

為什麼是兩張而不是四張（一個 kind 一張）：`rsem` 與 `folder` 在**卡片**這一層
一模一樣（都是「一顆一張」），做成兩張會是兩份會各自長歪的程式碼 ——
而「同一個家族收成一張卡」是既有的規矩（F7-10）。四個 kind 的差別在**檔案怎麼
找到**，那件事在 Input 的三個入口就分完了。

為什麼 `resolve_writes_for_kind` 會消失：`load_patch` 的 writes 改成**只看
`channel_map`**（預設值 `1:test, 2:ref` ＝ 現在 ebi_patch 的行為），
`load_single` 的 writes 只看 `out`。兩張卡都不再需要知道 kind ——
**宣告從「隱形的資料型別」變成「使用者看得到的值」**，那正是畫布不說謊的條件。

##### 做完之後

| | |
|---|---|
| `load_patch`「Load images」| `channel_map` 預設 **`1:test, 2:ref`**（原本是空字串）→ 宣告永遠等於**使用者看得到的那張表**，不再問資料型別 |
| `load_single`「Load one image」（新）| 一個 `out` 參數（預設 `single`）、一顆埠。多張資料**擋下來並講出該用哪張卡**，不偷偷拿第一張 |
| `resolve_writes_for_kind` | **沒有人覆寫它了**，而且有一條對整個 registry 跑的測試守著（下次有人想用「這個 kind 給這幾條」解問題時會叫）|
| 鏡射 | 拿掉（`single` 不再偷偷變成 `test`）|
| 起手卡 | 跟著資料走：`rsem`/`folder` → `load_single`（`RecipeModel.starter_step_for`）|
| 舊 recipe | `_migrate_split_load_cards`：單張影像那條 route 上的 `load_patch` → `load_single`（`out="test"`，＝原本鏡射的結果）|

**遷移踩到一個真的坑**：**兩條 route 可以共用同一個節點**，而 v1 的雙輸入 recipe
正是那樣寫的（`dual_route_basic.json` 的 ebi_patch 與 rsem 共用八個節點，包含那張
load 卡）。就地換掉共用的那一張會把另一條 route 弄壞 —— 第一版這樣寫，**黃金值當場
抓到**（patch 那 8 顆全部 `ok=False`：「這張卡只載一張圖，但這顆有 2 張」）。
所以共用的情況要**多開一個節點**給單張那條 route 用。

**第二個坑**：`resolve_writes` 拿到的是**原始 `node.params`**（recipe JSON 省略預設值
是合法的），所以「沒有這個鍵」要回到卡片預設、「有鍵但空字串」才是「使用者把每一列
都清掉了」。第一版混成一件事 → 畫布上的 Input 卡一顆埠都不剩（兩支 UI 測試抓到）。

驗收 `tests/test_f11_split_load_cards.py`（10 條）＋ 既有測試改寫（`test_steps.py`、
`test_rsem_ingest.py`、`test_f11_channel_map.py`、`test_recipe.py` 各有一兩條斷言的是
舊行為）。**黃金值三組 22 顆逐項相同**（`load_single` 保留 `n_channels` 就是為了這個
—— 一個常數特徵的資訊量是零，但「同一份資料換一張卡就少一欄」的代價不是零）。

#### 3.1.14 範圍縮到 patch + RSEM（2026-08-17）—— **這一輪沒有一項白做**

使用者：「我決定我暫時不做 multi channel（多通道的），暫時 focus 在 patch 跟
RSEM Image。」

多通道是 Input-1／Input-2 的**動機**，但兩個機制最後都不是多通道專用的 ——
因為它們解的是更基本的問題（**宣告要等於使用者看得到的值**）：

| 做出來的東西 | 在 patch + RSEM 的範圍裡還做什麼 |
|---|---|
| `channel_map`（一顆的第幾張叫什麼）| **`load_patch` 的宣告靠它才誠實**：預設 `1:test, 2:ref` 就是 patch 的老規矩，而畫布上的埠 = 那張表。少了它就得回去問資料型別 —— 那正是 Input-4 拆掉的東西 |
| `tiff_stack`（大 TIFF 沒有 KLARF）| `per_defect=1` 就是「**一疊 RSEM 影像、沒有 KLARF**」—— 而那是使用者明講要支援的兩種資料之一。順帶修掉「15 頁的 TIFF 安靜地變成一顆」|
| `load_single`（一顆一張）| **RSEM 的那張卡**。它存在的理由本來就是單張資料，跟多通道無關 |
| 位元深度防呆 | 與通道數無關 |

**擱置的是**：BSE/SE 融合卡、PCA Ref（Enhance 段）、「五頁沒有 ref → 通道互比」
那條 Compare 路線、廠內假設 #5（頁序）。要回來時只要在命名表格上多填幾列 ——
沒有任何東西需要拆掉重做。

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
| ✅ Input-3 | 四種輸入的入口做齊（`rsem` / `folder` 打開、`Open folder…`、`HIDDEN_STEPS` 清空）| **完成 2026-08-17** |
| Compare-1 | **配對機制**（第二個來源逐顆對上）＋ 新卡「Locate in a larger image」（matchTemplate 的第三種座標數學，§3.1.9）＋ 修 `align` 尺寸不符要報錯 | 使用者：「配對是之後的事」—— 它屬於**對位**那一輪，不是 Input 段 |
| 防呆 | 非 8-bit 就講一句話；一批之內尺寸忽然變了就講一句話 | 兩個都是幾行的事，但擋掉的是「安靜地算出垃圾」|

### 3.2 Enhance

| | |
|---|---|
| 現在有什麼 | `normalize`（**5** method）、`tone`（亮度/對比/gamma/曲線/反相）、`denoise`（**5** method）、`flatten`（5 method＋兩種背景估計）。F7-20 已從 9 張收成 4 張，而這一輪加的三個能力**一張卡都沒有新開** |
| 缺什麼 | **這一段做完了**（§3.2.2 契約、§3.2.3 三個方法、§3.2.6 五個面板輔助、§3.2.5 兩支 lint、§3.2.7 試用回報四項）。剩下的只有 ⏸ **融合卡（PCA Ref、BSE·SE quadrant）**（2026-08-17：多通道暫時不做，見 §3.1.14）|

#### 3.2.1 四張卡逐張稽核（讀 code＋實際跑出來量的）

四張卡都是 `MultiStreamStep`：**接幾條流進來就處理幾條，每條流一個埠，每條吃同
一組設定**（F7-19）。所以「畫布上有幾條線」與「這張卡動了幾條流」永遠相等 ——
這一段的稽核不必再問那件事，改問**它對每一條流做的那件事誠實嗎**。

```
        Enhance 段現在的形狀（四張卡，一律 N 條進 → 同樣的 N 條出）

   test ──┐                              ┌── test'      每一條流：
          ├─▶ ┌──────────────────┐ ──────┤              · 讀進來
   ref  ──┘   │  一張 Enhance 卡  │       └── ref'       · 套同一組設定
              │  method + 幾個旋鈕 │                     · 寫回同一條流
              └──────────────────┘
                       │
                       └─▶ 想讓兩條流吃**不同**設定 = 放兩張卡（那才是它們
                           該長得不一樣的時候）
```

| 卡 | 它真的在做什麼 | 稽核出來的問題 |
|---|---|---|
| `normalize` | percentile / glv_band / match / local(CLAHE)，把灰階重新映射到可比 | ① `use_within`（只用 mask 內的畫素量）**三個方法有、`match` 沒有** —— 而 `match` 是最需要它的那一個（面積浮動直接歪掉亮度對齊）<br>⑦ 沒有「把平均與 σ 釘在固定值」那一種（percentile 釘的是端點）|
| `tone` | 亮度／對比／gamma／曲線／反相，手動調 | ② 削平（把畫素壓到 0/255）**只在直方圖上看得到**，沒有數字、沒有一句話 |
| `denoise` | median / gaussian / bilateral / nlm | ③ `strength` 的單位是**這張圖自己的雜訊 σ**，而那個 σ 只活在演算法內部 —— 使用者在調一個以他看不到的數字為單位的旋鈕<br>⑥ 只有幾顆壞點時，四種方法都是把**整張圖**磨過一遍 |
| `flatten` | background / stripes_h / stripes_v / bright_spots / dark_spots | ④ **輸出沒有值域契約**。實測 `stripes_h` → 261.5、`background`+`keep_level` → 250.09<br>⑤ 背景估計只有高斯一種，而**加權平均一定會把缺陷吃進背景** |

##### ④ 的實測（這是這一批的起點，不是推論）

拿同一張 patch 餵四張卡，量輸出的 dtype 與值域：

```
   Normalize (percentile) → uint8     0.00 … 255.00   ✓
   Adjust tone            → uint8    40.00 … 255.00   ✓
   Denoise                → uint8     0.00 … 255.00   ✓
   Remove bg (background) → float32 116.36 … 250.09
   Remove bg (stripes_h)  → float32 125.50 … 261.50   ← 超過 255
   Normalize (local)      → float32   8.00 … 255.00
```

261.5 會一路活到**後面某個** `to_uint8` 才被壓掉 —— 也就是資訊在使用者看不見的
地方飽和。而 `keep_level` 的 help 還寫著「讓影像留在原本的灰階區間，下游的門檻
才還是同一個意思」：**那句話在這個修正之前是假的**。

#### 3.2.2 第一批：把契約補上（✅ 完成 2026-08-17）

使用者定調：先做這四項（①②③④），**不做**銳化／unsharp（見 §3.2.4）。

##### 1) 值域變成明講的契約

```
      一張 Enhance 卡的輸出                MultiStreamStep.run（基底，四張卡共用）
   ┌────────────────────────┐
   │ build_op 算出來的畫素   │  0 ─────────────────────── 255
   │  … 258.3  261.5  -3.1  │      ├──────────────────────┤   ↑ 界外
   └────────────────────────┘      │                      │
                │                  ▼                      ▼
                └──▶ clip_to_range ── 壓回 0/255 ──▶ 寫進影像流
                            │
                            └──▶ clip_frac = 界外畫素 / 總畫素
                                     │
                                     ├─ 是一個**特徵**（進 CSV、進 DB、可以拿來 gate）
                                     └─ > 1% 就 ctx.warn 一句可以照做的話
```

兩個刻意的決定：

- **只 clip，不 rescale。** rescale 會動到每一個畫素，那就違背了「留在原本的灰階
  區間」這個承諾（下游所有門檻會一起失效）。clip 只動界外那些，而「動了多少」由
  `clip_frac` 講出來。
- **dtype 不強制統一**（三張回 uint8、兩個方法回 float32）。值域一致之後那個差別
  對量測沒有影響（float 少一次量化，鏈起來反而更準）。強制統一會讓既有 recipe 的
  數字整批位移，換到的只有「看起來整齊」。

##### 2) 削平：`clip_frac` 只補**看不見**的那一半（界線畫在哪裡）

原本的計畫是「削平計數從『圖上看得到』升級成數字」。做的時候發現**這是兩件事**，
而合成一個數字會壞掉：

| | 是什麼 | 看得見嗎 | 誰報 |
|---|---|---|---|
| `clipped_low/high`（`stream_change`）| 輸出裡有多少畫素**坐在** 0 / 255（原圖本來就有的黑也算）| 看得見（直方圖兩端染色的柱子）| 儀表面板，預覽時 |
| `clip_frac`（新）| 這張卡**算出了 0–255 以外的值** | **看不見**（存進流之前就被壓掉了）| 引擎，永遠 |

合成一個「新增被釘在端點的比例」試過，不行：`bright_spots` / `dark_spots`
（top-hat）的輸出本來就有一大片剛好等於 0 的畫素 —— 那是這張卡的**用途**，不是
失敗。合成之後它每跑一次就喊一次狼來了，而 1% 那個門檻的整個意義就是不喊。

所以 `tone` 把六成畫素壓到 255 時 `clip_frac` **是 0，而那是對的** ——
它在卡片內部（`apply_brightness_contrast` 的 `np.clip`）就夾回去了，而那種削平在
直方圖上一眼可見。`tests/test_f11_enhance_range.py::
test_clip_frac_is_about_values_computed_out_of_range_not_flattening` 把這條界線釘住。

⚠ **留下來的洞**：`clipped_low/high` 只在 `ctx.track_changes` 開著時記（預覽開、
批次關 —— 一萬顆每次 `set_image` 算兩個直方圖是白花的力氣）。所以「批次跑完之後
從 CSV 看得出哪些顆被 tone 削平了」目前**做不到**。要補的話是一個「新增釘在端點」
的特徵加上一個「這張卡本來就會產生端點值嗎」的旗標（top-hat 那類卡自己宣告），
不是把 `track_changes` 打開。

##### 3) σ 露出來

```
   right-bottom 儀表（Before / after 面板）

   ┌─ “test” 直方圖 ──────────────┐ ┌─ “ref” 直方圖 ───────────────┐
   │ ▁▂▃▅▇▅▃▂▁   細線 = before     │ │ ▁▂▃▅▇▅▃▂▁                    │
   │ ░▒▓█▓▒░     實心 = after      │ │ ░▒▓█▓▒░                      │
   │ 0 black      gray level  255  │ │ 0 black      gray level  255 │
   └───────────────────────────────┘ └──────────────────────────────┘
   “test” 0.3% at black, 0.1% at white (noise σ ≈ 6.1)  ·  “ref” … (noise σ ≈ 0.5)
                                       ↑                              ↑
                            只有 Denoise 卡印這一段        逐流各一個（印錯一條比不印更糟）
```

- σ 存在 **`ctx.meta["noise_sigma"][流名]`，不是特徵**：σ 是**這張圖的性質**，不是
  這張卡算出來的結果（同一張圖不管接不接 Denoise，σ 都一樣）。當成特徵的話，
  「有沒有這個數字」會取決於使用者有沒有放這張卡 —— 那不是一個可以拿來當 gate 的
  東西。要 gate 請用 Measure 段的 `focus_quality`。
- 機制是 `MultiStreamStep` 上一個新的 hook `note_stream(ctx, key, img, params)`：
  `build_op` 在迴圈**之前**只呼叫一次，所以它看不到「哪一條流、長什麼樣」，而儀表
  要回答的問題常常是逐流的。用 hook 而不是「讓 op 多收一個參數」—— op 是最短的
  那一段（`img -> img`），把診斷混進去會讓四張卡各自長出一份。

##### 4) `match` 也吃 `use_within`

```
   量在 mask 內、套用在整張圖（跟 percentile / glv_band 同一條規則）

   test ─────────────────┬────────────────────────────▶ 整張圖套同一個映射
                         │                                        ▲
   mask ─▶ 只留這群畫素 ─┤  量 mean/std（或 CDF、P2/P98）─────────┘
                         │
   ref  ─▶ 只留這群畫素 ─┘   ← ref 也用同一個 mask（不然兩邊量的不是同一種圖案）

   為什麼：64px 的 patch 裡一根 Metal Gate 進出畫面就是 12% 的面積差。拿整張圖的
   統計去對齊亮度，同一片 EPI 只因為隔壁多了一根 MG，對齊完就變一個值。

   為什麼套用不跟著 mask：mask 外的畫素要走同一個映射，否則影像會在 mask 邊界上
   出現一道人工的階梯 —— 而那道階梯會被下游當成邊緣訊號。
```

- `algo/histmatch.py` 三個 method 都加了選填的 `mask=`（vendored 檔頭已註明）。
  `mask=None` 與 vendor 進來的那份**逐位元組相同**，測試釘住。
- `use_within` 的 `show_when` 從三個方法變四個；`extra_reads` 在 `match` 時要
  **同時**宣告 `reference` 與 `use_within` —— 漏了後者，畫布上就沒有那條線，
  而使用者看不出這兩張卡有關係（F9）。
- mask 尺寸不符 → 白話 `StepError`，講得出下一步（去改 Mask-from-regions 的
  “Same size as”）。

##### 做完之後

| 檢查 | 結果 |
|---|---|
| 核心測試 | 1100 passed（`test_offline_tools` 的 FILELIST/bundle 過期是預期的，跑 `release.py` 收掉）|
| 新測試 | `tests/test_f11_enhance_range.py`（21）＋ `tests/test_ui_f11_enhance_panel.py`（8，含一支從真實預覽走完整條路的）|
| 黃金值 | 三組 22 顆**逐項相同**。特徵多了三個（`clip_frac`、`norm_clip_frac`、`norm_ref_clip_frac`），**沒有任何既有數字移動** → 重凍一次 |
| 卡片不變量 | `test_card_invariants` 全過（`resolve_features` 的宣告 = 真的吐出來的名字）|

#### 3.2.3 第二批：三個新方法（✅ 完成 2026-08-17）

三個都是**既有卡片的一個下拉選項**，不是新卡片（F7-10／F7-20 那條規則）。

##### ⑤ `flatten/background` 的背景估計法：`gaussian` | `median`

```
   同一張圖、同一個 size=21，只換背景估計法（實測）

   原圖：背景梯度 110→140，缺陷 4x4、比背景亮 60
   ┌─────────────┐
   │      ▓▓     │   gaussian（加權平均）
   │      ▓▓     │     背景估計在缺陷位置被抬高  →  殘差只剩 ~43 GLV
   └─────────────┘     ↑ 缺陷自己有一部分被算成背景，然後被減掉

                       median（排序中間那一個）
                         缺陷佔核心面積 < 一半 → 背景估計完全不受影響
                                              →  殘差 ~59 GLV（幾乎全留）
```

- **平均沒有辦法忽略離群值**，所以 gaussian 的這個誤差不是「核心開大一點就好」，
  是結構性的。中位數對「少於一半的畫素長得不一樣」完全免疫。
- 代價：慢一些，而且背景是平滑梯度時會有輕微的階梯（中位數是離散的）。
- 大核心的中位數在 float 上跑不動（cv2 的 float 路只支援 ksize 3/5），所以
  `algo/enhance.py::median_blur_f32` 走 uint8 的 Huang 直方圖法 ——
  **背景估計**量化到動態範圍的 1/255，殘差仍然是用原始浮點值減出來的。
- 沒有加 `opening`：`img − open(img)` 就是既有的 `bright_spots`（top-hat），
  同一件事不要有兩個入口。
- 舊 recipe 沒有 `estimator` 這個鍵 → 走 `gaussian`，逐位元組相同（測試釘住）。

##### ⑥ `denoise` 的 `hot_pixels`：一顆都不磨，只換壞掉的那幾顆

```
   median（原本唯一「對付亮點」的方法）        hot_pixels
   ┌───────────────────────────┐            ┌───────────────────────────┐
   │ 整張圖都被 3x3 中位數過一遍 │            │ |img − 鄰居中位數| > 4σ ?  │
   │  ├ 壞點消失 ✓              │            │  ├ 是 → 換成鄰居中位數     │
   │  └ 邊緣一起被磨掉 ✗        │            │  └ 否 → **逐位元組不動**    │
   │     ↑ 而那是下一段要拿來    │            └───────────────────────────┘
   │       量 CD 的東西          │              換掉的比例 → hot_px_frac
   └───────────────────────────┘              > 0.5% 就講一句話
```

- 門檻的單位是**這張圖自己的雜訊 σ**（同 `bilateral`/`nlm` 的 `strength`），
  所以 4.0 在安靜的 lot 與吵的 lot 上是同一件事。
- `hot_px_frac` 是使用者調門檻時**唯一看得到的回饋**：門檻壓低到開始吃真的缺陷
  時影像上看不出來（少了幾顆亮點而已），這個數字會跳。它也只在選了這個方法時
  才宣告 —— 另外四種方法動的是每一個畫素，那個比例恆等於 1，一個永遠是 1 的
  欄位只會佔 CSV 的寬度。
- 機制：新的 hook `MultiStreamStep.after_stream(ctx, key, before, after, params)`
  —— 跟 `note_stream` 對稱，但拿得到前後兩張圖，所以「這張卡動了多少」是**免費**
  的（比對兩張圖，不必把演算法再跑一次）。前綴由 `run()` 統一套。
- 1 GLV 的地板：合成的無雜訊影像 σ ≈ 0，沒有地板的話門檻變 0，整張圖都算「跟鄰居
  不一樣」。

##### ⑦ `normalize` 的 `zscore` —— 而且它是**耐離群**的那一版

```
   percentile：釘兩個端點          zscore：釘背景的位置與一個 σ 的寬度
     P2  ──────────▶ 0              背景     ──────▶ target_level (128)
     P98 ──────────▶ 255            1 個 σ   ──────▶ target_spread (32)
   ⇒ 「一個灰階代表多少變異」        ⇒ 「偏離背景 2 個 σ」永遠是 64 GLV
     逐張都不同                        ⇒ 下游一個固定門檻跨批才有意義
```

**量的方式是中位數與 MAD，不是平均與標準差** —— 這一項是做的時候量出來才改的：

```
   64x64 patch、背景雜訊 σ=5.0，放一顆 4x4 的缺陷進去
   缺陷振幅   0 GLV → 整張圖的標準差 5.05
             60 GLV → 6.2   ← 24% 的「這張圖有多抖」是缺陷貢獻的
            120 GLV → 8.6
   ⇒ 用平均/標準差的話，**兩顆大小不同的缺陷會被套上不同的縮放** ——
     那正是正規化要消除的東西。
   中位數/MAD：三個振幅量到的 spread 差 < 1 GLV（測試釘住）。
```

- 這跟 `remove_stripes` 用逐列**中位數**而不是平均是同一個理由（那一條的
  docstring 早就寫了：「一顆夠大的缺陷會把該列的平均值整個帶偏」）。
- 要平均/標準差版本的話，這張卡的 `match` + `linear` 就是（它對齊的是另一條流的
  mean/std）—— 所以這個家族兩種都有，而預設是耐離群的那個。
- `1.4826 × MAD` 的換算讓回傳值的單位跟 σ 一樣，呼叫端不必知道裡面用哪一種估計。
- `zscore` 跟 `percentile`/`glv_band` 共用 `range_from` 與 `use_within`
  （「量哪一張、量哪些畫素」抽成 `_measure_from`，寫兩次就會有兩種意思）。
- **op 刻意不自己 clip**：壓回 0–255 是基底的事（Enhance-1），而它會順便算出
  `clip_frac`。自己先 clip 掉的話那個數字永遠是 0 —— `target_spread` 開太大把
  尾巴削平的代價就又變回「只有直方圖看得到」。

##### 做完之後

| 檢查 | 結果 |
|---|---|
| 核心測試 | 1127 passed（`test_offline_tools` 的過期是預期的）|
| 新測試 | `tests/test_f11_enhance_methods.py`（19）＋ 面板 3 支 |
| 黃金值 | 三組 22 顆逐項相同（三個新方法都不是預設，既有 recipe 一個數字都沒動）|
| 舊測試改到的 | `test_enhance.py` 三處：兩個 `choices` 集合、`show_when` 的參數矩陣 —— 都是「這張卡多了一個選項」的必然更新，斷言的意思沒有變 |

#### 3.2.4 明確不做的

- **銳化 / unsharp mask。** 它讓影像**看起來**更清楚，同時把邊緣位置推走 ——
  而下一段就是拿邊緣量 CD。一張讓數字變壞、讓畫面變好的卡，在這個工具裡是陷阱。

#### 3.2.6 操作面板上還能放什麼輔助（提案，使用者 2026-08-17 問的）

使用者：「你幫忙想 UI 操作面板有沒有需要放任何用來輔助的東東（for 每張卡片）」。

**挑選的標準沿用 F7-17 那一條**（`ui/inspectors.py` 的模組 docstring）：

> 這張卡最常見的失敗模式是什麼，而那個失敗**在單顆畫面上看不出來**。

看得出來的（影像整個黑掉）不需要輔助；看不出來的才需要。下面五項按這個標準排，
**A 與 H 是建議先做的兩個**，而且兩個都是**通用機制**（不是每張卡各寫一份）。

##### A. 把核心大小畫在影像上（`flatten` 的 `size`、`denoise` 的 `ksize`）**✅ 完成 2026-08-17**

```
   預覽影像（patch 是以缺陷為中心裁的，所以缺陷就在正中間）
   ┌──────────────────────────────┐
   │                              │      ┌ 設定區 ────────────────┐
   │        ╭──────────╮          │      │ Scale to remove  [21]px│
   │        │   ▓▓     │◀── 半透明 │◀────▶│ ├──────●─────────────┤ │
   │        │   ▓▓     │    的 21px│      └────────────────────────┘
   │        ╰──────────╯    方框   │        拖滑桿 → 框跟著大小變
   │                              │
   └──────────────────────────────┘
   一眼可見「這個核心比缺陷大嗎」—— 而那正是這兩個參數 help 裡唯一的規則
   （flatten 要**明顯大於**缺陷，denoise 的 hot_pixels 要**貼著**缺陷）。
```

- 現在使用者是在猜像素數：help 說「抓 patch 邊長的 1/4 ~ 1/2」，但畫面上沒有任何
  尺度參考。這跟 F7-8「把 min/max 填好滑桿是免費的」是同一個道理 ——
  **使用者是一邊看影像一邊決定值的**，那個參考就該在影像上。
- **機制而非個案**，但**不是靠 `unit="px"` 推導的**（提案時想錯了一次）：
  registry 裡 `unit="px"` 的參數有一半不是鄰域範圍 —— `roi_cross` 的條紋間距、
  框線粗細、離邊界的留白全都是 px。拿一個方框去表示「條紋間距」會讓**影像**說謊，
  而那跟 F9/F10 的「畫布不能說謊」是同一件事。所以加的是一個**明講的旗標**
  `ParamSpec.extent`，判準寫在欄位的註解裡：**這個數字是不是一個鄰域的邊長**
  （濾波核、結構元素、搜尋窗）。目前只有兩個參數填了它。
- 實作：`ImageView.set_kernel_hint(size_px, label)`（第三個 overlay，前兩個是
  ROI 框與量測尺）＋ Studio 的 `_kernel_extent()`。三個 overlay 用**線型**分辨
  （ROI 實線 accent、量測尺實線綠、核心**虛線**）—— 三者會同時在畫面上，而
  「哪一個是我剛剛拖出來的」不能只靠深淺。
- 三個「不要畫」的情況都有測試釘住：`show_when` 藏起來的那一列（去條紋方法用不到
  `size`）、`ksize=1`（不濾波）、選到沒有這種參數的卡（框要消失，留著會被讀成
  「這張卡的核心」）。
- `align` 的 `search_radius` 沒有填 `extent`：它是**半徑**，畫成邊長會差兩倍。
  要畫的話得先決定「這個旗標的值是邊長還是半徑」—— 那是下一次的事。

##### H. 這一批有幾顆被削平（`clip_frac` 的整批分布）**✅ 完成 2026-08-17**

```
   右下角面板底部多一條（資料已經在 self.batch 裡，不必再跑）

   clip_frac across 100 defects   ▁▁▁▁▁▁▁▁▁▁▁▁▁▂▃█   3 defects lost > 1%
                                  0%                5%     ↑ 點得到 = 跳到那顆
```

- 這是 `AlignInspector` 教過的那一課：**Enhance 的失敗是「某幾顆」的事**，
  而單顆畫面永遠只回答那一顆。調參數的人看的是第 1 顆，出問題的是第 57 顆。
- 資料現成（`Inspector.feature_values(name)` 已經是「整批某個特徵的值」），
  所以這一項幾乎只是畫圖。
- 順帶解決 §3.2.2 記的那個洞的一半：批次的 CSV 有 `clip_frac`，但沒有人會去看
  CSV —— 面板上一條分布會被看到。
- 做出來的三個決定：
  - **橫軸是「第幾顆」，不是分布直方圖。** 使用者接下來要做的事是去看那幾顆，
    而分布圖答得出「有幾顆很糟」卻答不出「是哪幾顆」。
  - **只有真的有整批資料時才佔位子**（跑過一次 trial 之前它是空的，而一條空的
    軸線只是雜訊）。
  - **刻度上界是 `max(實際最大值, 1%)`**：全部都很小的時候不要把 0.01% 放大成
    滿格 —— 那看起來像是出了事。
  - 摘要那一行講的是**別的顆**，所以它講「100 顆之中的 3 顆」而不是一個比例，
    並且明說「螢幕上這一顆不是最糟的那一顆」。

##### C. 曲線後面放這張圖的直方圖（`tone`）**✅ 完成 2026-08-17**

```
   ┌ Custom curve ─────────────┐   使用者拉曲線時看不到「哪一段灰階真的有畫素」，
   │ 255 ┤            ╱        │   於是常常在一個空的區間上花力氣（或反過來，
   │     ┤        ╱            │   把所有畫素都在的那一小段壓平了）。
   │     ┤    ╱  ░▒▓█▓▒░       │
   │   0 ┼──╱────────────────  │   ░▒▓█ = 這張圖的直方圖（淡色墊底）
   │     0                255  │
   └───────────────────────────┘
```

Photoshop 的 Curves 就是這個形狀，所以對「不會寫 code 但會修圖」的使用者是零學習
成本。

- 資料是**引擎那份** `ctx.meta['stream_change'][流]['before']` —— 跟儀表左邊那條
  細線同一組數字。UI 不自己再壓一次直方圖：畫面上的分布跟真的跑出來的不一樣，
  比沒有那個背景更糟。而 `before` 正好就是「這張卡動它之前」，與曲線的橫軸
  （輸入灰階）講的是同一件事，所以不必另外算一份。
- 高度用**平方根**（同 Enhance 儀表的理由：兩端的削平會堆出極高的柱子，線性刻度
  下其餘的形狀會被壓成一條貼著底的線）。
- 放大的那一張（`Enlarge…`）也墊 —— 「做細活」正是最需要知道哪一段有畫素的時候。
- `set_histogram` 走 `ParamForm` 而不是 `set_step` 的簽章：這是**資料的事實**，
  不是這張卡的參數（同 `set_image_count` 的形狀，F11 Input-1 就是這樣）。

##### E. 磨掉的是雜訊還是訊號（`denoise`）**✅ 完成 2026-08-17**

一個數字 `removed_over_noise` = `RMS(before − after) / σ`。≈1 表示磨掉的量級就是
雜訊；≫1 表示連結構一起磨掉了。

```
   同一張有 2px 條紋的圖（實測）
   median ksize=3   → 1.01   雜訊磨掉了，條紋還在
   median ksize=7   → 57.7   條紋整個被抹平        ⚠ 超過 2 就講一句話
   gaussian ksize=7 → 36.9   同上
   bilateral ksize=7→ 0.64   條紋留著（這就是保留邊緣的意思）
   而**四種在單顆畫面上都「看起來乾淨了」** ← 那正是它需要一個數字的理由
```

- 分子要處理後才知道、分母要處理前才對 —— 所以 `note_stream`（量 σ）與
  `after_stream`（比對前後）**必須成對存在**。σ 若用濾過的圖去量，比值會無限膨脹。
- 黃金值三組 22 顆量到的都是 0.96–0.98：既有 recipe 的 denoise 拿掉的正好是雜訊。
  那是這個刻度的一次獨立驗證（不是為了測試挑的合成圖）。

##### B. 兩條流現在真的可比了嗎 **✅ 完成 2026-08-17**

處理兩條以上流的 Enhance 卡多報兩個**不帶前綴**的特徵：`pair_level_delta`
（背景差幾個灰階）與 `pair_spread_ratio`（起伏差幾倍）。面板印
`“test” vs “ref” now: 0.8 gray levels apart, spread 1.04×`，差太多就補一句
「還不能比，diff 會把這個落差當成缺陷」。

- 統計用**中位數與 MAD**（`robust_level_spread`），理由跟 `zscore` 一樣：
  要量的東西就是缺陷本身，用平均/標準差的話「這兩張有多像」會隨缺陷大小浮動。
- 兩張圖**尺寸不必一樣**（patch 對 RSEM 就是不一樣，§3.1.9）—— 量的是各自的整體
  統計，不是逐像素比對。
- 大圖等間隔取樣到 65536 個畫素：這是一個**診斷**，要便宜到每顆都算。取樣是
  決定性的，所以 `workers=1` 與 `workers=2` 不會算出不同的值（鐵則 9 的那條線）。
- 不帶流名前綴：它們講的是「這兩條之間」，掛在其中一條的名字下面會是錯的。
- ⚠ 原本以為這一項會改動既有 recipe 的特徵集 —— **實際上沒有**：三組黃金 recipe
  的 Enhance 卡每一張都只接一條流（兩條流是 F7-19 之後才可能的寫法）。
  這一輪唯一多出來的欄位是 E 的 `removed_over_noise`，而**既有的每一個數字
  逐位元組不變**。

##### 五項做完之後（A H C E B，2026-08-17）

| 檢查 | 結果 |
|---|---|
| 新測試 | `tests/test_ui_f11_card_aids.py`（18：A 七、C 六、H 五）＋ `tests/test_f11_enhance_diag.py`（16：E 七、B 九）＋ 面板 5 支 |
| 核心測試 | 1145 passed |
| 黃金值 | **只多一個欄位**（`removed_over_noise`，量到 0.96–0.98），既有的每一個數字逐位元組不變 → 重凍一次 |
| 剩下的 | §3.2.5 的兩支 lint —— **已於同日完成**，見那一節 |

##### 不建議做的

- **before/after 的 wipe 滑桿**：並排比對（F9-9）已經在了，wipe 只是換一種呈現，
  不解新的問題。
- **把四張卡的參數再分 `section`**：`show_when` 已經把不相關的列整個藏起來，
  剩下的最多五列。再分組是給列數多的卡用的（例如之後的 ADC 卡）。

#### 3.2.7 使用者試用回報（Enhance-4，✅ 完成 2026-08-17）

三件都是**同一條規矩的破口**（鐵則 10：資料從哪來由線決定，而畫布上每一條線都是
使用者拉的）—— 只是這一次破在**影像區**與**畫布的預設狀態**，不在接線邏輯。

##### ① 開窗不預先放 Load 卡

> 「一開始進去 GUI 畫面時，Load image 卡片改成預設沒有（user 可以選擇要
> Load images or Load one image），add 才會出現。」

F7-9 起開窗就有一張 `load_patch`。那時候只有一張載入卡，所以「先幫你放好」是純粹
的好意；**Input-4 把它拆成兩張之後，預先放一張就是替使用者決定了他還沒決定的事**
—— 而猜錯的那一半在畫布上看起來完全正常（兩顆埠 vs 一顆埠）。

`RecipeModel.starter()` 因此不再加卡片。**但載入資料的那一刻「哪一張」已經不是猜
的**（`ingest` 判別出來的 kind 就是答案），所以 `studio._adopt_source_for` 會在
**空白且沒動過**的畫布上補上那一張，並在狀態列講「added “Load one image” for it」。
使用者已經放了東西的話，這一段一個字都不動它。

> ⚠ 這一項是**我加的一半**：使用者只說了「開窗時不要有」。補的理由是「載入資料時
> 那個選擇已經有唯一答案」，而如果他要的是**任何時候都不自動出現**，把
> `_adopt_source_for` 拿掉就是嚴格版（那時候 72 處測試要改寫成手動加卡）。

##### ② 入口卡左邊不畫輸入埠

> 「因為她是最初始的 source，card 最前方不能有連接的白色原點。」

`in_anchors_local()` 以前的註解是「沒有輸入的卡（Input）**仍畫一顆**」——
那顆埠看起來可以接線，但入口卡的資料不是從別張卡來的，任何線都接不上去。
現在沒有輸入就沒有埠，而且 `in_port_at()` 回 `None`（連拖過去的動作都不成立）。
`in_port()` 仍然答得出一個幾何點 —— 那是給連線畫圖用的座標，不是畫在畫面上的東西。

##### ③ 沒接線的卡不准有畫面

> 「Load image 載入圖片後點選 Denoise / remove background 為何會有畫面？
> 我前面的 rule 應該有說要連接線（image source），右側才會出現 patch。」

他是對的，而那張圖是這樣來的：預覽**跑的是整條 route**（`upto_node` 只是提早停），
而入口卡不需要任何線就跑得起來 —— 它把 `test` / `ref` 寫進了 master context。
Denoise 沒有輸入所以失敗，但失敗的策略是**「把已經算出來的影像留在畫面上（診斷比
清空有用）」**，於是畫面上出現的是入口卡的輸出，看起來像 Denoise 的結果。

判準改成**選取的那張卡自己這一次的 trace**：

| 情況 | 影像 | 狀態列 |
|---|---|---|
| 這張卡跑起來、成功 | 顯示 | 正常 |
| 這張卡跑起來、失敗（例：偶數核） | **不顯示** | 引擎那句錯誤（它自己帶著怎麼修）|
| 這張卡沒跑到（自己或上游沒接線）| **不顯示** | 引擎的 `no input connected … Drag a line …`，退路是 lint 的 `not-connected` |
| **後面**某張卡失敗 | 顯示（診斷比清空有用，這一半保留）| 那個錯誤 |

用 trace 而不是 lint：它同時涵蓋「這張卡沒接線」與「**上游**沒接線」—— 後者一樣
不會執行，而畫面上一樣會出現入口卡的圖。

##### ④ 節點的第三行不准被切在字中間

> 「normalize 的節點文字會被吃掉。」

畫面上是 ``streams= · p_low=1.2 · refer…``，三個問題：

- `streams=` —— **空的值印出來了**。剛加的卡每一格輸入都是空的（F10
  `cleared_inputs`），而空字串跟卡片預設值不相等，所以它被當成「非預設」。
  一個沒有任何資訊的欄位，還把有用的那一項擠掉了。
- `refer…` —— 項數在 Studio 那邊就砍成 3，而節點只有 ~150 px 寬。**被切掉的那一項
  使用者根本不知道它存在。** 現在改成畫的人照**寬度**決定塞得下幾項
  （`canvas._fit_parts`），放不下的收成 `+N` —— `+1` 是一個看得懂的訊息，
  `refer…` 不是。
- 副標印 `normalize`（step key）—— 使用者剛在上面一行讀過同一個字。兩邊都空的時候
  現在直接講狀態：`(not connected)`。

##### 做完之後

| 檢查 | 結果 |
|---|---|
| 新測試 | `tests/test_ui_f11_canvas_truth.py`（15）|
| 改到的舊測試 | 6 支檔案的斷言（開窗有沒有卡片、埠數、tooltip 措辭）＋ 14 支檔案把 `window.model.node_order[0]` 換成 `conftest.first_source(window)` |
| 核心測試 | 1164 passed |
| 黃金值 | 三組 22 顆逐項相同（這一輪全部在 UI 層）|

#### 3.2.5 第三批：兩支 lint（✅ 完成 2026-08-17）

兩支都是 **warning**（recipe 照樣跑得完），而且都出現在**畫布上那張卡**身上 ——
既有的 `_node_problems`（F7-13）機制照舊，兩支新 lint 一行 UI 程式碼都沒改。

##### `uneven-treatment` —— 兩條要比較的流受到不同的處理

```
   load ──test──▶ Normalize ──▶┐
        └─ref───────────────────┤ Subtract   ⚠ 'test' went through Normalize,
                                            but 'ref' went through nothing
   兩張圖各自都好看，但已經不在同一個灰階尺度上 —— 而減出來的整片偏移
   看起來就是一個大面積的缺陷。
```

不誤報是這支能不能被信任的關鍵（**一支會誤報的 lint 比沒有 lint 更糟**：
使用者學會忽略它之後，真的那一條也被忽略了）。所以：

| 情況 | 結果 | 為什麼 |
|---|---|---|
| 一張卡接兩條流（F7-19 的正確寫法）| 安靜 | 同一組設定 |
| 兩張卡、**設定一樣** | 安靜 | 比的是**設定**，不是接線 —— 接線一定不一樣，不然就不是兩張卡 |
| 兩張卡、設定不同 | 講，而且**指出差在哪一格**（`Low percentile is 3.0 for 'test' but 12.0 for 'ref'`）| 原本會印成「'test' 經過 Normalize，而 'ref' 經過 Normalize」，一句自我矛盾的話 |
| 同樣的卡、順序相反 | 講 | 先 Denoise 再 Normalize 跟反過來出來的圖不一樣 |
| 其中一條是 `diff` 這種中途產生的流 | 安靜 | 來歷本來就不同，比「處理歷史」沒有意義 |
| 量測卡讀兩條流（`snr_map` 多來源）| 安靜 | 讀兩條 ≠ 在比較它們。只認 `GROUP_COMPARE` 的卡 |

`align` 也吃這一支：灰階尺度不一樣，相關性就找錯位置。

##### `card-order` —— 自動正規化排在手動調色之後

`tone.py` 的 docstring 早就寫了「手動那張通常放在正規化之後，否則正規化會把你剛調
的東西再拉回去」—— 但**沒有任何人檢查它**，而後果是使用者那一步**完全沒有作用**，
畫面上卻看起來有。只認這一組（`tone` → `normalize`）、同一條流、一張卡一則訊息。

##### 順手修掉的一個新噪音（Enhance-1 帶進來的）

`clip_frac` 是**每一張** Enhance 卡都會產出的，所以任何有兩張 Enhance 卡的 recipe
都會撞名 —— 兩份參考 recipe 因此各多出 2–4 條 `feature-collision`。那正是上面說的
「會被學會忽略的警告」。

修法是讓卡片**宣告哪些數字是診斷**（`Step.diagnostic_features`，預設空），
兩邊都是診斷就不報。值沒有丟：engine 的 `_rescue_overwritten_features` 把前一張的
留成 `<節點名>_clip_frac`（黃金值裡的 `norm_clip_frac` 就是它），跳掉的只是那句話。
真的量測值撞名（兩張 `glv_stats`）照樣講。

⚠ 過程中我一度以為那句「The earlier one is still available as `<owner>_<f>`」是假的
（只讀了 `Context.add_feature`，它確實只是覆寫）—— 實際上 engine 在外面包了一層
救回機制。**先查清楚再改**，不然這一輪會「修掉」一句本來就對的話。

##### 做完之後

| 檢查 | 結果 |
|---|---|
| 新測試 | `tests/test_f11_enhance_lint.py`（17）＋ 畫布上看得見 3 支 |
| 核心測試 | 1163 passed |
| 兩份參考 recipe | `validate()` 回**空清單**（做之前有 4 條 / 2 條 `feature-collision`）|
| 黃金值 | 三組 22 顆逐項相同 |

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
| 現在有什麼 | `roi_cross`（Profile，純規則，**24 個參數**）、`roi_template`（Template，Golden Cell，12 個參數）、`roi_mask`（區域 → mask 流，3 個參數）|
| 缺什麼 | **第三條路**（吃 GLAS 的 label map）＋ 見 §3.3.1 的稽核 |

#### 3.3.1 稽核（讀 code 讀出來的，2026-08-17）

##### ⚠ 最重要的一項：**具名區域只有「矩形」這一種形狀**

```
   資料模型（algo/roi.py::NamedROI）
      name → [(nx, ny, nw, nh), …]      ← 每一塊都是**軸對齊的矩形**
                                            量測卡 roi_pixels 把每一塊接起來當
                                            一個像素母體；roi_mask 也照框畫

   GLAS 的 label map                     ← 一張 uint8 圖，0=背景、1..N=各 layer
      任意形狀（L 形、斜的、有洞的都可能）
```

兩邊對不起來，而**這一項決定 `roi_from_mask` 怎麼做**（三條路，§3.3.2 的第一題）。
在這之前 ROI 的三張卡都是自己**產生**框的，所以沒有人碰到這個限制。

##### 其餘四項

| # | 發現 | 為什麼要處理 |
|---|---|---|
| 1 | `roi_cross` **24 個參數**（5 個小標題、6 個 advanced）| 使用者上一輪就回報過這張卡「有些我不知道是什麼功能，也不知道怎麼調」。小標題與 advanced 已經做過一輪（F8 第三輪／第六輪），但它仍然是全庫最大的一張卡 —— 要重新看一次「哪幾格其實可以自己算出來」|
| 2 | ~~`roi_template` **12 個參數、一個小標題都沒有**~~ **← 已解，見 §3.3.4** | 同一段裡兩張卡兩種待遇。而它的四個 `roi_x/y/w/h` 是**手打的數字**，畫面上沒有任何東西告訴使用者「這四個數字是相對於什麼量的」（相對於對位到的那一格 cell，不是相對於整張 patch）—— 那才是這張卡最需要講清楚的一件事 |
| 3 | ~~三張卡的**框畫在預覽上，但拖不動**~~ **← 使用者否決，見 §3.3.2** | 我原本把它當成缺點。但 ROI 的參數要對**整批**成立，而拖框只回答「這一顆」—— 該加強的是既有的跨顆檢視（F7-11），不是拖曳 |
| 4 | ~~`roi_mask` 的 `regions` 是**自由文字**~~ **← 已解，見 §3.3.4** | 要打的字必須跟上游卡片的 `roi_out` 一字不差。打錯的話 lint 會抓（`unknown-region`），但它本來可以是一個下拉 —— 上游有哪些名字，程式知道 |

#### 3.3.2 三題的答案（使用者定調 2026-08-17）

##### 第一題：label map 的任意形狀怎麼變成「具名區域」

| | 做法 | 好 | 壞 |
|---|---|---|---|
| **A** | 每個 label 取一個**外接矩形** | 最省事、資料模型零改動 | **會框到不屬於它的東西**：一片 L 形的 layer 外接矩形裡有一半是別的圖案，而 `glv_stats` 會把那些像素一起平均進去 —— 那正是 ROI 要避免的事 |
| **B** | 每個 label **切成一堆小矩形**（連通元件／逐列 run-length）| 資料模型零改動、統計**精確**（`roi_pixels` 本來就是把每一塊接起來）；而半導體 layout 幾乎都是曼哈頓的，一根 MG 本身就是一個矩形 | 框數會多（幾十個很正常）—— 畫面上要處理、`max_boxes` 那類上限要重看 |
| **C** | 區域模型加一個**選填的 mask**（一個名字可以帶一張 0/1 圖）| 完全保真、任何形狀都行 | 每一個吃區域的地方都要處理兩種形態（矩形 or mask）—— 量測卡、`roi_mask`、overlay、region check、KLARF 寫回 |

**答案：B**（使用者 2026-08-17）。而且他補了一個**站點事實**，它比理由本身更重要：

> 「目前區域**基本上都只會是矩形**。」

所以 B 在這個站點不是「近似」，是**等價**：要框的東西本來就是矩形，切成一堆小矩形
只是把「一個名字對應好幾塊」這件既有的能力（`set_roi_boxes`，F8 就有了）用上。
C（區域帶一張 mask）因此**不是被否決，是還不需要** —— 它的入口是「NamedROI 多一個
選填欄位」，B 做完也不會擋住它，等真的遇到斜的或圓的再說。

⚠ 這一句要記進 `docs/FAB-VALIDATION.md` 的「已確認事實」那一類：它不是假設，
是使用者對自己站點的陳述；但它也**只對這個站點成立**，所以 C 的入口要留著。

##### 第二題：做事的順序 —— **三個階段對應三種 mode**（使用者定調）

> 「ROI 這部分我想分 3 個階段（對應 3 種 mode）：分別先是 template → profile → GDS
> （難度上會是這樣）。」

**這個順序跟我原本的建議相反，而使用者是對的。** 我提的是「新能力先做」，
他提的是**照難度爬**：

| 階段 | mode | 那張卡 | 為什麼排這裡 |
|---|---|---|---|
| **Region-1** | Template | `roi_template` | 最單純：模板已經能用，缺的是**設定介面**（12 個參數、0 個小標題、四個手打的框座標）|
| **Region-2** | Profile | `roi_cross` | 難在**參數太多**（24 個）。要重新看哪幾格其實可以自己算出來、哪幾格該收起來 |
| **Region-3** | GDS | `roi_from_mask`（新卡）| 最難：要新卡、要 Input 段的 sidecar 接頭、要合成 label map 產生器，而且要等 GLAS 的樣本 |

**照難度爬的好處**：Region-1 是「既有功能 + 介面」，Region-2 是「既有功能 + 減法」，
Region-3 才是「三個沒做過的東西一起上」（新卡 + sidecar 接頭 + 合成資料產生器）。
反過來做的話，最難的那一段會同時在解三個沒解過的問題。

##### ⛔ 「框可以用滑鼠拖」—— 使用者否決（2026-08-17）

我在稽核裡把它列成 §3.3.1 的第 3 項，並建議做成 Region 段的通用互動。**使用者否決
了，理由比我的提案有力**：

> 「拖 ROI 沒什麼實質效益，因為我要跑的是**每一顆 defect**。」

拖框回答的是「這個框在**這一顆**上對不對」，但 ROI 的參數要對**整批**成立 ——
patch 是以 defect 為中心裁的，同一個框在第 1 顆剛好、第 50 顆可能整個偏掉。
**用眼睛在一顆上拖到好看，正是那個會安靜出錯的做法。**

這跟 F7-11 當初做「跨顆檢視」（框畫在 N 顆縮圖上）的理由一字不差 ——
那扇窗已經在了，而它才是這一段該加強的地方。

⚠ **對照 Enhance-UI-A（核心大小畫在影像上）為什麼成立**：那個畫的是**參數本身的
大小**（核心 21 px 有多大），跟哪一顆無關；框的**位置**則是逐顆不同的。
兩者看起來都是「把參數畫在影像上」，但一個是尺規、一個是猜測。

##### 第三題：合成資料怎麼產

家用機沒有 GLAS 的輸出（`AGENTS.md` §1：只能用真實資料驗的功能，在家用機上等於
不能驗）。所以 `tools/` 要補一支**合成 label map 產生器**，與 `make_sample.py`
的合成 lot 一一對應（同一個 `DEFECTID`）。這一項沒有選項，只是要記得它是
Region-1 的**第一步**，不是最後一步。

#### 3.3.4 Region-1（`roi_template`）—— **✅ 完成 2026-08-18**

稽核（§3.3.1）列的兩件事都在，但**使用者定調的形狀比稽核大一個級別**：

> 「我會想要在那張 GC 上就可以標注 ROI（用 drag、用 add box、用點的把 ROI 標
> 注出來），同時也要能分 ROI Group —— 同張影像可能會有 ROI1、ROI2…，而且 ROI
> 不限一個矩形。總之這個操作面板要很 flexible 好用（基本的增加刪除、放大縮小
> 都要有）。目前的 template 界面太難用，請重新設計。」

以及他舉的那個例子，它決定了資料模型：

> 「一個 layout 是橫向 EPI 跟直向 MG 交錯，假設我想要的 ROI1 是 EPI 部分扣掉
> MG 交集。」

**那個形狀用一個矩形表達不出來，用好幾個就可以** —— 也就是 §3.3.2 第一題的
答案 B，只是這次是使用者自己標，不是從 label map 切出來的。

##### 一個尺寸關係，我一開始搞反了

我原本問「ROI 在 patch 上有好幾個落點要取哪一個」，是把大小關係想反了。
使用者更正：

> 「Template 是一定會比 patch 大的，如果它落在 repeating pattern 對到 template
> 哪個位置根本沒關係。」

而模組說明本來就這樣寫（「patch 比週期小也沒關係 —— 是把小 patch 滑進大模板」）。
接著他補的那句話才是關鍵：**要框的東西本身是重複的**（「隊到哪都會有各種 ROI」）。
所以有一條**同時涵蓋兩種大小關係**的規則，不必請使用者選：

> 框標在 cell 上，映到 patch 時**cell 在這張 patch 裡出現幾次就畫幾個框**。

* cell 比 patch 大（常態）→ 最多一份，可能一份都沒有（正常，不是失敗）
* cell 比 patch 小 → 每一份都有，量的是「這張圖上所有的 EPI」

舊行為（只取離缺陷最近的那一份）在後者會**只量到一根 EPI，其餘的靜靜漏掉**。

##### 做了什麼

| | |
|---|---|
| `pipeline/cellrois.py`（新）| 區域的字串編碼 `ROI1: 0.1,0,0.25,1; 0.62,0,0.25,1 \| ROI2: …`；一行字串而不是巢狀 JSON（`curve` 定下的規則），round-trip 是 identity（鐵則 9）。加 `array_boxes`（multi add 的幾何）|
| `algo/template.py` | `roi_in_patch` → `roi_boxes_in_patch`（整片鋪過去、`max_boxes` 留中間的那些）|
| `steps/roi_template.py` | `roi_x/y/w/h` + `roi_out` 五個參數 → 一個 `regions`；每個區域一個 `<name>_present`、多框的給 `<name>_center`；5 個小標題；門檻三兄弟收 advanced |
| 區域沒落上這一顆 | **不再退回整張圖**（那會安靜地量到全部像素）：記進 `meta["regions_absent"]`，量測卡的錯誤訊息照它講出真正的原因 |
| `ui/cell_canvas.py`（新）| 標註畫布：縮放平移、拖拉增刪、cell 鋪成一片（看得到接縫）、畫出一顆 patch 有多大、**multi add** |
| `ui/template_dialog.py`（重寫）| 建模板與標區域合成一個對話框；`load_encoded` 讓「回來改框」不必重建模板（重建會重算相位 → 框全部平移）|
| `roi_mask` 的 `regions` | 自由文字 → 勾選（新型別 `region_keys` + `RecipeModel.available_regions`）。§3.3.1 第 4 項 |

##### multi add 的規格（使用者定的，逐條照做）

> 「會定義兩個錨點左上跟右下（按下去滑鼠中心為錨點長出 box + 十字錨點（可預覽），
> 當然也要定義輸入 pixel box 大小 W/H），再來輸入 x 跟 y 代表的是以左上跟右下框
> 的範圍內有多少個矩形（以 box 中心為原點），自動長出預覽，確認沒問題後按下確認
> 就可以一次框選大量同 period box。」

間距由**兩個端點**算出來（`(b − a) / (n − 1)`），不是另外再輸入一個 pitch ——
端點看得見，pitch 看不見。一根一根拉會漂，而漂掉在畫面上看不出來、在數字上看
得出來。

##### 在 cell 上可以拖，跟「⛔ 框可以用滑鼠拖被否決」不衝突

否決的理由是「我要跑的是**每一顆** defect」—— 在一顆 patch 上拖到好看，第 50 顆
可能整個偏掉。**但 cell 不是一顆 defect**：它是整批共用的同一個模板物件，在它
上面標框跟拖四支滑桿產出的是同一組數字。所以這裡拖的是尺規，不是猜測
（同 Enhance-UI-A 的分界）。

##### 還沒做的（Region-1 的尾巴）

* **模板過期健檢** —— `roi_template.py` 的檔頭寫著「換一批資料要不要重算模板，
  是 Studio 在設定時提供的健檢」，而那個健檢**不存在**（grep 全 repo）。
  F10 那個形狀：文字說得出來、引擎做不到。
* `configuration_issues` 只擋「沒有模板」與「沒有區域」，不擋「框整個落在 cell
  外」這種設定完了但每一顆都白跑的組合。

#### 3.3.5 使用者試用回報（Region-1 第二輪，✅ 完成 2026-08-18）

七項，逐條照做。**第 1 項是 bug，其餘六項是介面。**

| # | 回報 | 處置 |
|---|---|---|
| 1 | 「沒辦法 multi-add → 按下 Add them 加不進去 region」| **真的 bug**，見下 |
| 2 | 「取的 cell size 也要能 customer 取（有時候會需要 2X 大 cell）」| 來源列加 Cell W/H ＋「×2」＋「Re-stack」。量出來的週期變成**預設值不是結論** |
| 3 | 「定義 ROI 方式分三種：add（click add／multi add）／drag／點一顆一顆 pixel 的…請改成用 icon（目前介面文字太多）」| 四支工具、四顆圖示鈕（新 glyph `roi_drag/roi_click/roi_array/roi_paint`），說明退到 tooltip。第四支取名 **paint** |
| 4 | 「單位是 pixel 但我想要取整數」| 每一次新增／搬移／改大小都吸附到整數 cell 像素，寬高至少 1 px；數字表也是整數 |
| 5 | 「拖東頂點框（那 8 個端點）太大很醜」| 把手半徑 7 → 3，命中判定另外放寬到 7（縮小不變難抓），加白色細邊 |
| 6 | 「按住右鍵要能拖拉移動」| 右鍵（與中鍵、Shift＋左鍵）平移 |
| 7 | 「視窗可以大一點；表格建議不顯示，放在一個按鈕裡打開來可編輯」| 1320×880；數字表收進「Edit numbers…」的彈出視窗，側欄只留「這個區域有幾塊」|

##### 第 1 項的根：**沒有容器可以裝，於是什麼都沒發生**

`add_box` / `add_boxes` 開頭是 `if not (0 <= self._current < len(self._regions)):
return -1 / 0`。從 Studio 打開一張**已經有模板、還沒有區域**的卡時，
`set_regions_text("")` 讓區域清單是空的 —— 於是畫出來的框跟按下 Add them
**都安靜地什麼都沒發生**，而且沒有任何訊息，因為程式覺得自己沒事。

處置：`ensure_region()` —— 「使用者做了一個明確的動作」與「沒有容器可以裝」
之間，該讓步的是後者。**拖曳新增走的是同一條路，所以它以前也一樣壞著**，
只是使用者先撞到 multi add。

##### 第 2 項踩到一個「使用者明講的一律相信」的反作用

「×2」第一版把兩軸一起加倍，結果在一維 layout（垂直條紋、Y 上沒有週期）疊出一個
**比原圖還高**的 cell（240 px 的圖 → 480 px 的 cell）；而 `build_golden_cell` 對
明講的 `px`/`py` **不做信心檢查**（那是使用者說的，不是猜的），所以那一軸被當成
有週期 —— `locate_axis` 從 `x` 變成 `both`，定位開始在一個沒有相位的方向上搜尋。

處置：沒有週期的那一軸**鎖起來並講出原因**（「這張圖在這個方向沒有週期，一格就是
整張影像」），`restack` 對那一軸傳 `None`。實測寫成測試。

##### paint 這個名字與它的資料

使用者說「點一顆一顆 pixel 的（我想不到名字你幫我想）」。取 **paint** ——
但圖示是**幾格點亮的方格**不是筆刷，因為畫出來的東西是像素不是筆觸。
放手時那些像素併成**逐列的矩形**（run-length），因為區域的資料模型是矩形 ——
那正是 §3.3.2 答案 B 對 label map 講的同一套做法，這次換成手畫的來源。

#### 3.3.7 編輯器第四輪：游標、復原、對齊（✅ 2026-08-18）＋ 一個量出來的算法問題

| # | 回報 | 處置 |
|---|---|---|
| 1 | 「視窗框左上會出現『Whole pixels of on…』字樣」| **bug**：`box_units` / `box_table` 以對話框為 parent、卻等第一次按鈕才放進 layout。**沒有家的 widget 不是隱形的，它是畫在 (0, 0) 的。** 彈出視窗改成在 `__init__` 就建好（隱藏著）|
| 2 | 「icon 功能列大一點漂亮一點，增加 Cursor 才能選 ROI，刪除、還原也加入 icon」| 新 `[shape="tool"]`（34 px，QSS 的 `max-width` 才是第一版只有 26 px 的原因）＋ 圖示跟著放大到 21（門檻式，30 px 以下的既有鈕逐像素不變）。新工具 `cursor`；新圖示 `roi_cursor` / `trash` / 六個 `align_*`；`undo` 沿用既有的 |
| 3 | 「支援畫布操作，例如框一整排 box 有 align 功能」| 多選（Ctrl＋點、空白處拖曳＝套索）＋ 六顆對齊鈕。基準是**選取範圍的外框**，不是「第一個選的那個」—— 使用者是先框一整排再按對齊，那時候「第一個」是哪一個他自己也不知道 |
| — | 順帶 | 復原（Ctrl+Z，深度 40，每次改動前存整份快照）；刪除改成刪**每一個**選起來的；方向鍵微調整組一起動 |

游標與拖曳分成兩支工具的理由：`cursor` 在空白處拖是**框選**，`drag` 在空白處拖是
**畫新框**。同一個手勢兩種意思會讓使用者不敢在畫布上隨便拖。

##### ⚠ 量出來的算法問題：**2× cell 讓 certainty 歸零**

使用者：「假設我是 2x cell 大，certainty 可能會被壓很低，有解嗎？」實測（合成資料，
8 個相位）：

| cell | certainty（margin）| score |
|---|---|---|
| 1×（40 px）| 0.37 – 0.61 | 1.00 |
| **2×（80 px）**| **0.000** | 1.00 |
| 3×（120 px）| 0.000 | 1.00 |

不是「壓很低」，是**歸零**，而預設 `min_margin = 0.05` → **每一顆都 locate_ok = 0**。

**機制**：`match_patch` 的 margin 是把相關面**摺回「一個 cell」**之後才比最高與次高
（`_fold_to_period(surface, cx, cy)`，cx = cell 寬）。cell 取 2× 而影像其實以 1× 重複
時，摺完的一個週期裡有**兩個一模一樣的峰** → 最高 ＝ 次高 → margin ≡ 0。
score 仍然 1.00 —— 比對是完美的，它只是**不唯一**。

**而「不唯一」要不要緊，取決於一件可以判定的事**：落在哪一半，只有在
**兩半上標的區域不一樣**的時候才有差。都一樣的話兩個答案都對。

提案（還沒做）：

1. `build_golden_cell` 已經知道量到的週期，所以**它知道 cell 是不是自己的 k 倍**。
   把那個自週期存進模板字串（`gc1:` → `gc2:`，舊的照讀），`match_patch` 改**摺在
   自週期上** —— certainty 就回到 0.37–0.61，量的是真正該問的問題（「在真的重複
   單元裡定得出來嗎」）。
2. 另外報一個**單元內的歧義**旗標，並檢查「把區域整組平移 1/k 之後是不是落回自己」
   —— 是就無害（講一句話），不是就要警告「這一顆可能落在另一半，而你在兩半上標的
   東西不一樣」。
3. 在編輯器上，選了 k× cell 的當下就講出來，不要等跑完 200 顆。

第 1 項是真正的解，第 3 項是最便宜的止血。

#### 3.3.6 Target / Reference **不住在 Region 段**（使用者定調 2026-08-18）

##### 問題怎麼來的

使用者問「Target ROI box（紅框）跟 Reference ROI box 兩種方法差別？怎麼定位？」
查下去發現這個 repo 裡有**三個紅框，沒有一個是活的**：

| 在哪 | 是什麼 | 現況 |
|---|---|---|
| `algo/roi.py` 的 `roi_type='target'`（紅）／`'reference'`（青）| vendored 自 Fusi³ | **死的** —— `set_target()` 在 `steps/`／`pipeline/`／`ui/` 一次也沒被呼叫，ADEPT 建的每個框都是預設的 `'reference'` |
| `export/overlay.py` 的「主 blob 紅框」| 缺陷 blob 的外框 | **畫不出來** —— 讀 `ctx.meta["blobs"]`，而那個沒有生產者（Blob 卡不存在，§1.2）|
| `<name>_center` | 離 patch 正中心最近的那一塊 | **唯一活的**，但它是**位置**不是角色 |

##### 定調：Region 段只出名詞

> 「以這張 card 的功能（ROI）來說我不太想要去區分 target 跟 reference，原因是
> 會有很多種組合，要 by 情況討論……我傾向這邊 ROI 只 labeled 出區域，之後再給
> card 標註 T 跟 R。主要是我不知道資料留在哪邊設定好會比較好。」

**同意，而且理由比「情況太多」更硬：角色是「這一次比較」的屬性，不是區域的
屬性。** 同一塊 EPI 在一個比較裡是 target、在另一個裡是 reference。角色一旦寫進
區域，每一種比較都要複製一份區域 —— 而區域是**畫**出來的，複製一份等於請使用者
在 cell 上重畫一次同一塊。

這條線這個 repo 已經畫過兩次，理由一字不差：F7-17 的「mask 給影像段、量測段照樣
引用名字 —— 兩條平行的路會腐爛」，以及 §3.3.2 否決 C 的「每一個吃區域的地方都要
處理兩種形態」。把 T/R 塞進區域是第三次踩同一個坑。

**所以：Region 段出名詞（有哪些區域、每一塊在哪），Measure 段出動詞（拿哪兩個
比）。**

##### 三個獨立的軸，使用者列的三種組合就都成立了

| 軸 | 誰決定 | 狀態 |
|---|---|---|
| 哪些像素 | Region 卡（畫在 cell 上）| ✅ |
| 哪一張圖 | **畫布上的線**（量測卡接兩條就吐 `test_epi_glv_mean` / `ref_epi_glv_mean`，`MultiSourceStep`）| ✅ |
| 哪一份（缺陷那塊 vs 其餘）| Region 卡 —— 它有晶格、有相位、知道缺陷在正中央 | ✅ **這一輪補的** |

| 使用者的情況 | target | reference |
|---|---|---|
| patch，跟自己兩側的 EPI 比 | `epi_center` @ test | `epi_others` @ test |
| patch，跟 ref 那張的同一塊比 | `epi` @ test | `epi` @ ref |
| 單張 source（沒有 ref）| `epi_center` @ single | `epi_others` @ single |

##### 做了什麼（✅ 2026-08-18）

`_util.set_region_family()` —— 一組框 → **三個**具名區域，兩張 Region 卡共用
（規則只有一份）：

- `<name>`         全部接起來的像素母體（**仍然包含**缺陷那一塊 —— 它的意思是
  「這張圖上所有的 EPI」，改掉會動到黃金值）
- `<name>_center`  缺陷所在的那一塊
- `<name>_others`  **其餘那幾塊 = 同一張圖上同材質的基準**

拿 `<name>` 當基準是**有偏的**：N 塊時缺陷佔 1/N 的像素，N=4、缺陷偏 50 GLV 的話
基準本身就被拉走 12.5 GLV —— 跟要量的量同一個數量級。

只有一份的時候 `<name>_others` **不存在**（不是空的、也不是退回整張圖）：這張
patch 上就是沒有基準。記進 `meta["regions_absent"]`，量測卡照它講出真正的原因。
「這一顆有沒有基準」怎麼問：`roi_cross` 用 `cross_count > 1`，`roi_template` 用
`<name>_others_present`（兩張卡的特徵命名慣例本來就一張是卡層級、一張是區域
層級）。

⚠ **卡片不可以有叫 target/reference 的參數，也不可以在區域上標記角色。**
`test_the_card_never_says_which_one_is_the_target` 鎖住這件事，順便鎖住
「vendored 的 `roi_type` 是死的，不要把它救活」。

##### 之後那張比較卡長什麼樣（Measure 段，**不是現在**）

```
Compare regions
  ├ Target region     [epi_center ▾]     ← region_keys 下拉（型別已經有了）
  ├ Reference region  [epi_others ▾]
  └ 吃哪幾條流 = 畫布上接進來的線
     → delta / ratio / z-score
```

T/R 住在**那張卡的參數上**：recipe 的 diff 看得懂「這一次比的是哪兩塊」；同一組
區域可以被三張比較卡用三種方式比（那正是使用者說的「很多種組合」，而組合屬於
消費端）；而且不動 Region 段，Region-2／Region-3 照原計畫走。

**今天沒有那張卡也做得到**，只是比較發生在**分數表達式**裡
（`test_epi_glv_mean - ref_epi_glv_mean`）。所以那張卡不是解鎖功能，是把一件
現在藏在表達式裡的事變成看得見的一張卡。

#### 3.3.3 Region-3（`roi_from_mask`）的規格 —— GDS mode，**第三階段**

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
