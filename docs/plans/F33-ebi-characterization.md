# F33 —— EBI ↔ API characterization：把三類分開，並且看得見

**狀態**：✅ 收斂（2026-08-25）。C1–C4 全部做完，端對端跑過。
**接的是**：[`F15-pair-sources.md`](F15-pair-sources.md) §16 停下來的那一段
（使用者 2026-08-20：「太快了」）。這一輪把它停下來的理由**滿足掉**再續做。

---

## 1. 要回答什麼

工程師想知道：**EBI 這台機台的這個 recipe，到底表現如何？**

做法是拿 RSEM 的 API 空拍當答案卷（它拍滿了一塊區域、直接從影像上抓出所有真的
存在的缺陷），然後把那些位置回頭去對 EBI 掃過的結果。每一顆分成三類：

| | 意思 | 代表什麼 | 怎麼調 |
|---|---|---|---|
| ① | 配到、分數夠高、被 sample 去 review 了 | EBI 做對的部分 | — |
| ② | **配到、但排名太低沒被 sample**（藏在 raw data 內）| 偵測能力夠，是 **sample 門檻**設錯了 | 調得動 |
| ③ | 沒配到 —— raw KLARF 裡連這一筆都沒有 | **偵測條件**有問題（landing energy／beam current／演算法門檻）| 另一個層級 |

②③ 的處置完全不同，而它們在資料上長得很像 —— **分開它們是這個功能存在的全部
理由**。

## 2. 三個前提（跟主流程相反的地方）

1. **main 掛 API（RSEM），不是 EBI。** ground truth 是 API，要走遍的是 API 的
   清單。從 EBI 出發的話 ③ 那一類**根本走不到** —— EBI 的清單裡沒有那一顆，
   不會有一列去描述它。這不是偏好，是邏輯上的必然。
2. **這條 recipe 沒有任何量測卡。** 所有數字來自兩份 KLARF 的欄位（`carry`）
   ＋ 各自的影像。它不「量」任何東西，做的是配對與比對。
3. **批次很小**（30 顆以內，至多 100）。`output_bundle` 為 6000 顆做的每一個
   取捨，在這裡都要反過來。

## 3. 風險全部集中在配對

沒有量測卡，代表「跑得完、有數字、而且是錯的」不會出現在量測上 —— 它會出現在
**配對**上：兩顆其實不是同一個東西，卻被配在一起。後果特別惡劣，因為配錯的那
一顆會被算進 ③，而 ③ 的數量正是這個分析的結論。

`ncc_score`（`align_to` 吐的比對分數）是第一道擋板，所以它**預設就在報表的表格
裡**（`output_char` 的 `columns` 預設值），不是收在進階裡。

⚠ **但它一個不夠** —— 陣列區裡 NCC 0.98 而位置全錯是實測出來的，第二道是 `align_peak_ratio`，兩個都在預設欄位裡。見 §8.5。

## 4. 這條 recipe 長什麼樣

```
Load one image        main = RSEM / API 空拍
      |
pair_source           掛 EBI，1:1 配（wafer 座標 + tol_nm）
                      carry：EBI 的分數欄、XINDEX、YINDEX、DEFECTID
                      rank_within / rank_by → die 內排名           ← C1
      |
align_to (H2H)        EBI patch 在 RSEM 空拍裡的位置
                      → 裁出對齊的一塊 ＋ ncc_score
      |
判定樹                 第一步問 pair_found → 分出 ①②③              ← C2
      |
output_char           Characterization report                     ← C3
```

判定樹：

```
第一步  pair_found < 1
        Yes → ● 沒偵測到                （③）
        No  → ◇ 第二步
第二步  pair_die_rank <= <sample 的名次門檻>
        Yes → ● 抓到了                  （①）
        No  → ● 偵測到但沒被 sample      （②）
```

**第一步一定要問 `pair_found`**：`decide_tree.walk` 只評走得到的那條路，所以
③ 那一支永遠問不到 ncc／分數那幾題，`decide_unanswered` 維持 0。

---

## 5. C2 —— 配不到的那一顆要留下來（地基）

**改了什麼**：`pair_source` 配不到時不再 `raise`。寫 `pair_found = 0`、不吐流、
其餘 `pair_*` 一格都不寫，**這一顆繼續走**。`align_to` 靠
`meta["pair_match"]`（`index == -1` ＋ `out` 的流名）安靜讓路。

**為什麼**：以前那一顆 `ok=False`、沒有分數也沒有 bin，**走不到判定樹** ——
③ 那一類數不出來，而 CSV 上看不出來（少了幾列，跟「本來就沒那幾顆」一樣）。

### 順帶修掉的兩個坑

* **配不到不再寫 `match_dist_nm`（原本是 NaN）。** 判定樹問問題是
  `expr.eval(feats) != 0.0`，而 `NaN != 0.0` 是 **True** —— `match_dist_nm > X`
  會對一顆根本沒配到的 defect 答「是」。算不出來的那一格本來就不該寫。
* **`paired` → `pair_found`。** 那個字同時是特徵名與這張卡的預設輸出流名。
  流名不動（它是畫布上的接線身分），改的是特徵，而它順帶跟 `pair_<欄位>`
  排成同一家族。

### 改名遷移本來只做了一半

`legacy_feature_renames`（F18）的遷移只改寫 `score.expr`
（`recipe._compare_feature_renames` → `_rename_in_expr`）。而 **F30 之後問問題
的地方是判定樹** —— 樹上的 `when` 沒跟著換，開起來就是一題**永遠答「否」**的
問題（問不到的特徵算否），畫面上它跟一條正常的規則長得一模一樣。
補了 `_rename_in_decide`（`let` / `rules` / `tree` / `decide.score`），冪等、
round-trip 仍是 identity（鐵則 9）。

### 兩個輸入埠都要問（端對端才抓到）

`align_to` 的讓路判斷第一版只問 `search` 埠。但 characterization 那條 recipe
把第二份接在 **`template`** 上（小圖是 EBI 的 patch、大圖是 RSEM 空拍）——
八顆裡的三顆因此照樣 `ok=False`，而那三顆正是要數的那一類。
**單元測試沒抓到，端對端跑抓到了**：測試只接了 `search`。現在兩個埠都問，
測試也 parametrize 成兩種接線。

---

## 6. C1 —— die 內排名

**母體是那一份的完整 defect list（幾千筆），不是這一批跑過 pipeline 的三十顆。**

### 為什麼不能用判定段的 `Let.scale`

判定段有現成的「跟整批比」（z / percentile）。用在這裡是錯的，因為**母體錯了**：

```
這一批 = API 清單 = 30 顆
→ Let.scale 給的是「這顆在我挑出來看的這 30 顆裡排第幾」—— 沒有意義

要的是「這顆在它自己那個 die 裡、EBI 全部 defect 中排第幾」
→ 母體是第二份 KLARF 的完整 defect list，可能幾千筆
```

判定段永遠看不到那幾千筆。只有 `pair_source` 那一層看得到完整的第二份
（`ingest/pair_source.attach` 把整份掛上來）。而且**排名是資料的屬性**，
不是判定的中間值 —— 放在讀資料那一層才是對的位置（同「一格 nm/px 長在把那份
資料讀進來的那張卡上」）。

（`Let.scale` 本身沒問題，它只是回答另一個問題。）

### 三格參數

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `rank_within` | `multi_choice`, `choices_from="source_columns"` | `""` | 分組欄位。挑 XINDEX+YINDEX 就是每個 die 自己排；留空＝整份排一組 |
| `rank_by` | `str`, `choices_from="source_columns"` | `""` | 排序欄位。**使用者自己選，不寫死** —— 不同機台、不同 recipe 的分數欄名字不一樣 |
| `rank_desc` | `bool` | `True` | 最大值第 1 名 |

**不預設 `XINDEX,YINDEX`** —— 那是這個 lot 剛好有，不是通則。

輸出 `pair_die_rank` 與 `pair_die_total`。**total 不是湊數的**：「第 7 名」在
10 筆裡跟在 3000 筆裡是兩件事，而 rank 那一格看起來一模一樣（同 `blob_n` /
`cd_pieces` 那一族的理由 —— 每個自動決定都要變成一個畫得出分布的數字）。

### 三個實作要點

* **一份資料算一次**（O(N log N)），不是逐顆算。備忘掛在 `DefectItem` 物件上
  （`_d4t_rank`，一組設定一個 key）：`sources_for_run` 重建的是 list、item 物件
  是共用的，而重掛一份 lot 會產生全新的 item —— 過期不了。兩張卡不同排名設定＝
  同一個 dict 兩個 key，不相撞。
* **tie-break 是 DEFECTID**。同分兩筆誰在前面必須是確定的，不然同一份資料跑
  兩次名次會變，而黃金值會抓不到真正的迴歸。測試把 items 反過來擺再跑一次。
* **轉不成數字要點名欄位、那個值、與那顆 DEFECTID**。安靜地全部並列第一的話，
  每一顆都拿到 rank 1，而它跟「真的是第一名」在報表上長得一模一樣。

排名欄位跟 `carry` 走同一條路進 `DefectItem.fields`（`columns_for_source` 的
聯集），所以 CLI 與 Studio 兩個掛載點都免費跟上，打錯欄位名在掛載那一刻就擋。

---

## 7. C3 —— `output_char`

### 為什麼是新的一張卡，不是 `output_bundle` 的一格參數

`output_bundle` 的每一個取捨都是為 6000 顆做的：

| 6000 顆（output_bundle） | 30 顆（這裡） |
|---|---|
| 表格裡不放縮圖（DOM 會鈍）| **表格裡就是要放縮圖** |
| 點一列換圖，整份只有一個 `<img>` | **一眼要能一一對應** |
| 圖擺在資料夾旁邊，不嵌進 HTML | 一樣（這一條不變）|

用一格參數在同一張卡上切換兩種版面的話，「這張卡長什麼樣」就有兩個答案，而
help、說明書、測試都得同時描述兩種。做成第二張卡，**底層共用**：
`export/html.py` 的 CSS／`escape`／`number`／判定那一段（新增
`build_char_report`）、抽成模組層的 `write_recipe_json`、`overlay` 的檔名消毒與
JPEG、以及改成公開的 `overlay.pick_base`（「沒有指名時這一顆的圖是哪一張」
兩個地方都要問，而答案只能有一個）。

### 版面

```
| defect | ground truth 縮圖 | second lot 縮圖 | 數字欄… | verdict |
```

* 圖仍然是**外部檔案**（`images/<id>_main.jpg` / `_pair.jpg`），**相對路徑**。
* **沒配到的那一顆右邊那一格完全不產生 `<img>`** —— 破圖示講的是「載入失敗」，
  而那一格要講的是「這一顆在另一份資料裡不存在」，那是結論之一。
* verdict 那一欄是**葉子的名字**，它不在 `rows` 裡（engine 刻意不放進 CSV
  schema），由 `decide_tree.verdict_rows` 的 `ids` 反查。
* 一樣寫 `recipe.json` 與 `defects.csv`。

### 顆數上限

超過 `limit`（預設 200）就 `bctx.warn` 並**指名 `Write report folder`**，
但**版面不換** —— 使用者要知道他拿到的是哪一種報表。

---

## 8. C4 —— montage 可以指定哪幾條流、橫排還是直疊

`render_overlay` 加 `panes`（一串流名，第一個就是底圖）與 `stack`（`"h"`／
`"v"`）。預設路徑一個位元都沒動（`panes=None` 走原來那條），而測試直接比
「不給參數」與「明確給 `panes=None, stack="h"`」逐位元組相同。

兩格的建構抽成 `_pane`、接縫抽成 `_stack_panes`（分隔線仍然是**覆寫**接縫後
的第一列／行，所以兩格橫排的總寬度還是剛好兩倍）。

⚠ **目前沒有正式呼叫者**（測試以外），而這是刻意的：C3 的表格本來就是兩欄兩張
圖，一一對應已經成立，使用者也把這一件標成「可選」。它要換來的是「單張圖自我
完整、可以單獨寄出去」—— 那一步等有人真的要寄一張圖的時候再接。
**寫在這裡是為了下一個人不要把它當成順手可清的死碼。**

---

## 8.5 ⚠ 對位的那個坑：`search_within` 預設 15% 是**另一個模型**

2026-08-26 使用者問：「RSEM image 通常比 defect patch 大很多（1000² vs 100²），
ground truth 又落在 RSEM 上面某一處，這樣有辦法對位嗎？」——**問對了**，而實測
的答案不是「可以」也不是「不行」，是「**可以，但預設值會安靜地給你錯的答案**」。

### 那個 15% 編碼的是 Review SEM，不是空拍

F15-4 的 `search_within` 預設 15%，依據是使用者當時那句話：「RSEM 基本上就是
移到 KLARF 座標（defect 在中間），不置中的原因是機台 stage 移動的 offset」。
那是 **review 一顆、拍一張**的模型：defect 在正中間 ± stage 誤差。

**空拍不是那個模型**：影像涵蓋一塊區域，defect 落在它剛好在的地方。

### 實測（1000×1000 空拍、100×100 patch、非週期紋理）

| defect 在空拍哪裡 | 預設 15% 框 | `search_within=0` |
|---|---|---|
| 正中央 (450,450) | ✓ (449,449) NCC=1.00 | ✓ NCC=1.00 |
| 略偏 (560,520) | ✓ (560,520) NCC=1.00 | ✓ NCC=1.00 |
| 偏左上 (150,200) | **⚠ (307,383) NCC=0.43** | ✓ (150,199) NCC=1.00 |
| 角落 (820,780) | **⚠ (304,366) NCC=0.30** | ✓ (820,780) NCC=1.00 |
| (60,900) | **⚠ (578,397) NCC=0.37** | ✓ (59,900) NCC=1.00 |

**它不會失敗。** 對的那一塊根本不在搜尋範圍裡，於是卡片在中間那一塊裡挑出
「矮子裡的高個」，回一個錯的位置加一個 **0.30–0.43** 的分數 ——
而 `min_score` 預設正是 **0.3**。報表上會出現一張裁錯地方的圖配一個看起來
還行的分數：跑得完、有數字、而且是錯的。

**規矩**：影像不是以這一顆為中心拍的 → `search_within = 0`。
這句話寫在卡片的 help 上（使用者會讀到的地方），迴歸測試是
`tests/test_pair_source.py::test_a_defect_that_is_not_in_the_middle_needs_the_whole_image_searched`。

**沒有改預設值**：Review SEM 那條路（15% 是對的）是既有 recipe 在走的，
改預設會動到它們。這是一個「講清楚」的問題，不是一個「換數字」的問題。

### `ncc_score` 一個擋板不夠 —— 陣列區要看 `align_peak_ratio`

任務書原本說「`ncc_score` 是唯一的擋板」。**在陣列區那句話不成立**，實測：

| 情境 | ncc_score | align_peak_ratio | 位置 |
|---|---|---|---|
| 週期性 layout、兩台機台各拍一次 | **0.98** | **1.00** | **每一顆都錯** |

NCC 0.98 看起來完美而位置全錯 —— 因為第二名的位置跟第一名一樣好。抓得到這件事
的只有 `align_peak_ratio`（第一名÷第二名，越接近 1 越是猜的；F15 §14.2 已經量過
這個數字，只是沒有人把它放進報表）。

所以 `output_char` 的 `columns` 預設是
**`ncc_score,align_peak_ratio,pair_die_rank,pair_die_total`** ——
兩個擋板都在表格裡，不是收在進階裡。

### 還沒做：用座標當錨點

真正的解法不是「搜整張」而是「**根本不用搜**」：API 的 KLARF 已經說了這一顆在
哪裡。拿它當錨點，「在 1000×1000 裡撈針」就變成「確認一個 ±30px 的 stage 誤差」。
那是 F15 §14.4 刻意留下的（KLARF-y 與影像列的正負號沒有在真資料上驗證過）——
**這一輪也沒做**，因為使用者確認 API 匯出是「一顆一張圖」，`search_within=0`
就夠了。哪天遇到「一張大圖上好幾顆」再回來接（那時候 ingest 層也要先能表達它）。

---

## 8.6 圖上要指出 defect 在哪 —— 而「拍歪多少」是**量得出來**的

使用者 2026-08-26：「名義上 defect 會在 FOV 正中央（RSEM 機台就是針對 KLARF
給定的座標移過去拍），但實際可能會拍歪一點點（一定會在 FOV 正中心附近）。
**可是這樣就沒有明確在圖上指出 defect 位置。**」

接著的追問更關鍵：「不太理解你怎麼量得出來 —— 拍歪這格，你要看得到圖知道位置
在哪，你才能知道 defect 距離中心偏多少。」

### 不需要在 RSEM 上「看到」defect —— **EBI patch 本身就是尺**

EBI 的 patch 是**以 defect 為中心裁出來的**。所以 NCC 找的不是 defect，是
「這一小塊圖案落在大圖的哪裡」——用的是整塊 patch 的紋理（圖案＋defect 一起），
不是去偵測 defect。落點確定了，defect 就在那個落點的中心。

`align_off_* = 落點 − 影像中心`，而落點中心即 defect ⇒ **那個數字就是 defect
離 FOV 中心多遠**。實測（400×400 FOV、100×100 patch，patch 以 defect 為中心）：

| defect 真的偏離中心 | `align_off_(x,y)_px` |
|---|---|
| (+0,+0) | (−0.00, +0.01) |
| (+18,−12) | (+18.00, −11.99) |
| (−25,+30) | (−25.00, +30.00) |
| (+40,+5) | (+40.00, +5.00) |
| (−8,−33) | (−7.99, −32.99) |

子像素等級吻合，全程沒有在 RSEM 上做任何缺陷偵測。

### ⚠ 承重假設：**patch 必須以 defect 為中心**

這件事不是「大概成立」，它是**承重**的。同一組實驗，只換 patch 怎麼裁：

| EBI patch 怎麼裁 | `align_off` 量到 | 意思 |
|---|---|---|
| 以 defect 為中心（EBI 的常態）| (+18.0, −12.0) | = defect 離中心多遠 ✓ |
| 以 defect 為中心、但偏了 (+20,+15) | (+38.0, +3.0) | **多算了那個偏移** ⚠ |
| 固定格線裁、完全不管 defect | (−0.0, +0.0) | **恆為 0，跟 defect 無關** ⚠ |

最後一列是最危險的形狀：`align_off` 一路是 0，十字與框完美重合，報表看起來
「每一顆都對得剛剛好」—— 而那個數字跟 defect 一點關係都沒有。
**廠內第一次跑真資料時要確認的就是這一條**（記進 `docs/FAB-VALIDATION.md`
的假設清單）：EBI 那一份的 patch 是不是以 defect 為中心裁的。

### 圖上的兩個記號（`output_char` 的 `mark_defect`，預設開）

* **綠色十字＝機台瞄準的那一點**。來自 `meta["align_to"]["expected"]`
  （那正是 `align_off_*` 的分母）；沒跑過 H2H 的那一顆就是**影像正中央**。
* **紅框＝小圖真的對到哪**（`align_dx/dy_px` ＋ 模板尺寸）。

**兩者的間距就是這一顆的 stage 偏移** —— 重合＝「這兩顆是同一個東西」長的樣子，
差很遠＝要人工看。配不到的那一顆（③）**只有十字**：那仍然是它該在的地方，
而「該在這裡、另一份卻什麼都沒有」正是第三類要講的話。

⚠ **框只畫在 H2H 真的搜過的那條流上**（`meta["align_to"]["search"]`，
這一輪替 `align_to` 補的）。換一條流當左圖時那組座標的意思就變了，而一個指著
錯地方的框比沒有框糟得多（同 `_draw_roi_boxes` 的「不猜」）。

---

## 9. 被否決的方案

| 想過的做法 | 為什麼不做 |
|---|---|
| 用 `Let.scale`（z / percentile）做 die 排名 | **母體錯了** —— 判定段只看得到跑過 pipeline 的那 30 顆（見 §6）|
| 在這條 recipe 裡加量測卡 | 這個功能用的是兩份 KLARF 的欄位＋各自的影像，**不量任何東西** |
| C3 做成 `output_bundle` 的一格參數 | 「這張卡長什麼樣」會有兩個答案（見 §7）|
| **配對方向做成可切換**（讓 EBI 當 main）| ground truth 是 API，從 EBI 出發**答不出 ③**。那不是一個選項，是一個錯誤 —— 做成選項的話，選錯的人會得到一份漏掉一整類的結論，而報表上看不出來 |
| 配不到時保留 `match_dist_nm = NaN` | `NaN != 0` 在判定樹上答「是」（見 §5）|
| 加一個 `pair_found` 而保留 `paired` | 同一件事兩個名字，兩份必然漂一份（`CLAUDE.md` §0）|

---

## 10. 沒做的／留給下一輪

* **`rank_by` 那一欄有空白值的真實 KLARF 會硬錯**（規格要求：不可以安靜地並列
  第一）。廠內驗證如果發現太嚴，逃生口是後續議題 —— **不做安靜容忍**。
* `pair_die_rank` / `pair_die_total` 的名字裡有 die，即使 `rank_within` 分的
  不是 die（規格定死的）。help 裡講清楚。
* 多張 `pair_source` 卡時 `ctx.meta["pair_match"]` 後寫者贏。讓路的判斷以 `out`
  的流名比對收窄誤傷；F15 本來就是一卡一來源。
* C4 的呼叫者（見 §8）。

---

## 11. 驗收

* `tests/test_pair_source.py`（51 → 68 條）：配不到留下來、兩個埠都讓路、
  接錯線照炸、③ 走得到那片葉子且顆數加總對得起來、改名遷移到 `score` 與判定樹
  兩處且冪等、排名的母體／tie-break／不寫／點名錯誤／一份算一次／跨 worker 相同。
* `tests/test_output_char.py`（新，15 條）：相對路徑先問是不是相對、沒配到那一格
  留白、兩張縮圖名字分得開、超過上限講出來但版面不換、verdict 欄是葉名、
  預設欄位含 `ncc_score`、end-point 不變量。
* `tests/test_export_overlay.py`（+8 條）：預設逐位元組不變、選流選序、直疊、
  缺流跳過、框畫在每一格。
* **黃金值三份全綠**（`tools/freeze_golden.py --check`）—— 這就是「沒填排名參數
  黃金值一個位元不變」的驗收。
* **端對端**（8 顆 API × 5 顆 EBI，`python -m d4t run … --source ebi=…`）：
  8 成功 / 0 失敗；5 顆 caught、3 顆 not detected，三類顆數加總等於 8；
  ③ 那三顆 `ok=1`、`bin=3`，rank 與 ncc 那幾格是**空的**（不是 0）；
  報表 5.9 KB、13 張外部 JPEG（5×2 + 3×1）、路徑全部相對。
