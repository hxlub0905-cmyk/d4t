# SESSION_LOG

開發歷程。**每次 session 結束請在最上方新增一段。**

較早的紀錄封存在 [`docs/history/`](docs/history/)，這裡只留最近的：

| 期間 | 在哪 |
|---|---|
| **2026-09-09 起** | 這個檔案（下面）—— **09-09 四輪**（判定樹上找得到 working numbers、「插入數字 ▾」一張卡一組帶說明、**跑與寫拆開＋Re-run**（鐵則 11）、Results 單擊帶主畫面、卡片寫 img/s、縮圖與表格同一份排序／篩選、體檢與十四件待辦）、**09-17**（`.I01` 副檔名不同的 patch TIFF、F102 疊模板前先框一塊、F103 標一格量週期、F104 二維自相關找峰、F105 交錯晶格上的小數週期、F107 文件稽核與七道新守門） |
| 2026-09-01 ～ 09-08 | [`docs/history/2026-09.md`](docs/history/2026-09.md) —— F67/F68 GLV 的「跟誰比」由線決定與抓 defect 的主力卡、F69–F72 設定欄／Feature 表／ADC 那一頁／報表打得開、F73 把 F68 的驗收真的跑完、F74 Region 段只剩一張卡、F75 文件對齊現況、F76 Feature 面板、F77 IQI (OP-301)、F78–F82 畫布的視覺那一批、F83 使用者回報的三個 UI bug、F84 ruff 那道關／`align_off` 的症狀／pack 裡的 378 MB、F85 PEAR 的均勻度、F86 使用者拿去用回來的四件、F87–F89 圖表那一塊、**F90 三把尺**、F91–F94 外部檢視的 P0 與 U6/U7、F95–F100 UI 評審的十七件與二十一件 |
| 2026-08-19 ～ 08-28 | [`docs/history/2026-08b.md`](docs/history/2026-08b.md) —— F42 區域線走 edges、F43–F45 結果表分層／區域接線／FeatureSpec、F46/F47 檔案架構與授權、F48 六個決定、F50 畫布上只剩卡片和線、F51/F52 特徵名與數字只有一種寫法、F53–F57 五件小事、F58–F66 合成資料長成真的那種 layout |
| 2026-08-07 ～ 08-18 | [`docs/history/2026-08.md`](docs/history/2026-08.md) —— F8 純規則 ROI、畫布 n8n 化、Phase 1 收斂、F10、Phase 2 的 Input／Enhance／Region 三段 |
| 2026-07 | [`docs/history/2026-07.md`](docs/history/2026-07.md) —— M0–M7、F7-9…F7-24 前半、兩台機器與搬運通道的成形 |

**切點換過一次，而第四份是在同一個月裡再切的。** 前兩份用的是「上一次合併進
main 的那一輪」，而這條分支從 2026-08-19 起就沒有再併回 `main` —— 那條線因此不再
切得動任何東西，再等下去這個檔案只會一直長（第三份封存之前它是 6,380 行 / 392 KB）。
所以第三份改用**月份**。

**第四份（2026-09-17）沒有再換切點，是量到了**：九月前八天的量本身就夠一份 ——
封存前這個檔案是 2,837 行 / 186 KB，搬走 F67 ～ F100 之後剩 363 行 / 28 KB。
留 09-09 起是因為那四輪定的是鐵則 11（跑不寫、寫是另一個動作），還在被引用。

封存不是整理癖：這個檔案**只增不減**，而它跟著整包被複製進公司機
（`docs/history/` 不進搬運包）。包的大小**不是限制**（2026-08-17 使用者確認直接
複製 raw，見 `AGENTS.md` §2）—— 封存是為了 diff 乾淨與公司機用不到的東西不佔
體積，不是為了那道 1 MB 的線。

---

## F112：DOE 的出貨 recipe —— `recipes/doe-conditions.json`（2026-09-18）

F111 更正完「DOE 缺一張卡」那句錯話，這一輪把那份 recipe 真的寫出來。
**出貨的 recipe 從三份變四份。**

```
Load images ─┬─le300─┐
             ├─le500─┼──> Align ─┬─le800──> ROI (a cell I mark myself) ┄target┄┐
             └─le800─┘  （整數平移） └─三條全部──────────────────────> GLV <┄ref┄┘
                                                                        └─> Write report
```

一張 GLV 卡吃**全部**的 condition，同一組 target／ref box 套在每一條流上，
每個 condition 各出一份 `<condition>_cmp_snr_px` 與 `<condition>_cmp_contrast_mean`。
那就是 imageY 的動作。**一行產品程式碼都沒改** —— 卡片本來就夠了（F111 的結論）。

### 三個實測才知道的東西

**① ROI 與 Align 都要接**最安靜的那個 condition**。**
相關性是拿訊號去找的，而雜訊最大的那一張訊號最少。實測拿 `le300`（σ=18）定位：
模板比對的 `structure` 只有 3.89（門檻 5）、分數 0.304（門檻 0.3），**兩道閘都在
邊緣** → 區域退回整張圖 → target 與 ref 變成同一塊 → `snr_px` 整批是 0
**而且每一顆都 `ok=True`**。接 `le800`（σ=2）之後分數 1.000、structure 11.74。

⚠ 那個失敗形狀正是這個 repo 最怕的那一種，所以它有自己一條測試
（`test_the_doe_recipe_really_places_its_two_boxes`）：盯 `locate_ok` 與兩個框的
**面積**，不是只看有沒有數字。驗它有沒有牙齒的時候看得很清楚 —— 把 ROI 接回
`le300`，「順序排得對嗎」那一條**照樣綠**（`sorted([0,0,0]) == [0,0,0]`），
只有這一條紅。

**② 範例資料不能沿用 `make_sample.py`，而那是量出來的。**
那一份的 patch **整張都是高對比晶格**：實測任何一個 16×16 的框標準差都在 62 以上、
整張圖 63.7。而 `snr_px = |μT − μR| / σR` 的分母正是**參照那一塊自己的像素標準差**
—— 拿一塊全是圖案的地方當參照，σR 由圖案決定而不是由雜訊決定，於是「哪一個
condition 訊噪比比較好」**在那份資料上根本問不出來**（三個 condition 的 σR 差不到 3%）。

所以新增 `tools/make_doe_sample.py`：低對比週期背景（有結構讓模板比對得到峰，
但不淹掉雜訊）＋**正中央**一顆缺陷 ＋ 每個 condition 各自的雜訊 σ（18／8／2）。
換過來之後 `snr_px` 是 0.37 / 0.83 / 1.25 —— 順序乾淨、而且最好的那個 > 1。

**③ 判定段要用 `decide` 不是 `score`。**
`score.expr` 空著會讓每一顆 `ok=False`（「the expression is empty」）。
量測型的 recipe 沒有門檻可言，所以照 `one-image-uniformity.json` 的形狀走判定樹：
`best_snr = max(每個 condition 的 snr_px)`，`< 0`（一個都沒量到，`fill` 補 −1）
→ bin 9「nothing to measure」，其餘 → bin 0「measured」。

### 一個自己咬到自己的錯

改 ROI 的來源時我只改了**節點的參數**，沒改**線**。而**資料從哪來由線決定**
（鐵則 10）—— 參數上寫著 `le800`、線上接的還是 `le300`，跑出來的仍然是壞的那一版。
那條鐵則在 `CLAUDE.md` 上讀過很多次，真的踩到才知道它擋的就是這個。

### 守門

`tests/test_shipped_recipes.py` 四條（那支測試的結構檢查 glob 到就自動跑，
這四條是**真的跑一批**的）：
* 每個 condition 都有自己的 `snr_px`，而且**雜訊越小的排越前面** —— 那是這份
  recipe 存在的理由，「跑得完、有數字」不算通過；
* 兩個框**真的放下去了**（`locate_ok` ＋ 面積，見上面 ①）；
* **一張 GLV 卡**吃全部的 condition，不是一個 condition 一張卡；
* **沒有 `normalize`** —— N 張之間的亮度差異正是要量的東西，一正規化就抹掉了。
  這一條守的不只是那份檔案：沒有它，下一個人會「順手加一張 Normalize 讓圖好看
  一點」，然後每一個 `snr_px` 都變小而沒有人知道為什麼。

`recipes/README.md` 加一節（含「拿去用在自己的資料上先做這兩件」：重畫那兩個框、
改 condition 的名字）。`tools/make_doe_sample.py` 進 `AGENTS.md` 的機器對照表與
`NEEDS_THIRD_PARTY`（它要 numpy，所以是家用機那一組）。

---

## F111：更正 —— DOE 的 recipe 不缺卡，是我把 `template` 讀錯了（2026-09-18）

F110 收尾我寫了一句「還差第四種 ROI method（或一張新卡）才出得了 DOE 的 recipe」，
**而那是錯的**。使用者一句話就戳破：

> 「其實固定位置的框在 ROI 內就有現成的，因為 defect 都會置中阿，ROI card 內就有
> 一個這選項」
> 「ROI reference 方法請用 a cell I mark myself」
> 「就丟其中一張的 template 給他讓他算，然後在上面框 ROI(Bbox)」

### 錯在哪 —— 前提，不是推論

那一段的每一步推論都對：三種 method 確實都要有東西可以鎖、DOE 的 defect 確實置中、
`pick="centre"` 確實只是從既有的框裡挑一個而不是造一個。**錯的是前提**：
我把「要有東西可以鎖」當成**卡片要自己去找一個可重複的 pattern**，於是
「DOE 的影像未必有 pattern」就變成一道過不去的牆。

但 `a cell I mark myself` 的 `template` **不是卡片要去猜的東西，是使用者自己挑的
那一張圖**。使用者裁一塊當 template、在上面把 target 與 ref 的 bbox 框出來
（`regions`，型別 `cell_rois`，存的就是那幾個矩形）—— 那正是 imageY 的動作：
**設一組 box**，不是叫軟體去找什麼。我讀過那一格的 help（「Draw them on the cell
in Studio」），卻沒有把「誰提供 template」這件事想清楚。

⚠ 第二條路我也讀到了卻沒認出來：`pick` 那一格**預設就是 `centre`**，吐
`<name>_center` / `<name>_others`，而它的說明逐字寫著「Patches are cut around the
defect, so the middle one is usually it」—— 那句話講的正是 DOE 的事實。

### 這一輪只改文件

`docs/ROADMAP.md` 的 Compare 那一列與 `SESSION_LOG.md` 的 F110 那一段。
F110 那一段**逐字留著並標成已更正** —— 它是紀錄，不能假裝沒發生過，而更正一句
錯話的前提是看得到錯的那一句。

**一行程式碼都沒有改**，那正是「判斷錯了」的意思：DOE 的出貨 recipe 還沒寫，
但它不缺任何卡。

### 留給下一個人的那一課

**「做不到」是一個比「還沒做」貴很多的結論**，因為下一個人會照著它去開一張新卡。
這一次的教訓很具體：**下這種結論之前，先問「這個輸入是誰給的」** ——
我把一個使用者提供的東西當成程式要自己產生的東西，整條推論就往錯的方向走完了。

---

## F110：Compare 段收斂 —— 拆卡、第五種 kind、流的內容型別（2026-09-18）

使用者說「**全部**」：F109 之後定案但沒做的六件一次做完。Compare 是 Phase 2 七段裡
最後一段，這一輪之後**七段全部收斂**。

**Compare 段現在四張卡**：`align`（Align）、`subtract`（Compare two images）、
**`combine`（Image Combination，新）**、`align_to`（H2H）。註冊 19 → 20 張。

### ① Image Combination 拆成兩張

`subtract` 的五個 `op` 是**兩個問題**擠在一張卡上，而判準是 F109 定的那條 ——
**訊號形狀**：`subtract`/`ratio` 問「這兩張哪裡不一樣」（2 條進 1 條出），
`max`/`min`/`mean` 問「把這幾張併成一張」（N 條進 1 條出）。

擠在一起的代價實際看得見：那張卡只有 `a` 與 `b` **兩顆埠**，所以想把三張 condition
併成一張 reference 的人得放兩張卡串起來，而畫布上那兩張卡看起來是在比較兩次。

* **比較卡**留著 `subtract` 這個 key（使用者定的 —— 出貨的三份與 fixture 都只用
  `op: "subtract"`，所以那一邊一個字都不用遷移），label 換成 `Compare two images`。
  ⚠ 名字換過兩次而**兩次的理由是同一個**：F16 從 `Compare two streams` 改叫
  `Image Combination`（「五個 op 只有一個是相減」），F110 又改回去 —— 因為那四個
  「不是相減」的裡有三個已經搬走了。名字跟著卡片真的在做的事走。
* 比較卡加兩個 op：`normalized`（`(a−b)/(a+b)`，參照接近黑時不會爆）與
  `over_sigma`（`(a−b)/σ(b)`，讓門檻在安靜的圖與有顆粒的圖上意思一樣）。
* `absolute`（bool）→ `sign`（`abs`／`signed`／**`split`**）。兩個值的格子答不出
  第三種答案，而第三種是使用者真的要的：**亮的缺陷與暗的缺陷分兩條流出去**
  （`<out>_bright` / `<out>_dark`），讓下游各給一個門檻。
* **融合卡** `combine` 拿走 `max`/`min`/`mean` 並加 `median`/`trimmed`。
  **median 是預設**：它是唯一拿得掉「只有一張有」的那個東西的，而那正是缺陷 ——
  「用好幾張造一張乾淨的 reference」是這張卡最常見的用途。

### ② DOE 的輸入：第五種 kind

`folder` 是「一個檔案一顆」，DOE 要的是**正好相反**的「一個子目錄一顆、裡面每個
檔案一個 imaging condition」。使用者選了**開第五種 kind**（`doe_folder`），而那是
對的：同一個 kind 兩種形狀會讓畫布說謊 —— `SINGLE_IMAGE_KINDS` 裡寫著 `folder`，
而 DOE 一顆有好幾張，畫布上那張預設的 `load_single` 對它一定報錯。

⚠ **流的順序是檔名排序，而那是一個契約**：這些 `ImageRef` 的 `page` 是 `None`，
所以 `_in_defect_order` 退回 dict 插入順序 —— 也就是 `sorted()` 的順序，而
`load_patch` 的 `channel_map`（1-based）正是照它數的。湊不成一顆的空目錄與撞名的
目錄**不吞掉**，進 `warnings`（同 `load_tiff_stack` 對零頭的處置）。

CLI 那一條**由內容判斷不是多一個旗標**：一個目錄裡裝的是影像檔還是資料夾是看得
出來的事實，而使用者在命令列重打一次那個事實沒有道理（推廣鐵則）。

### ③ `snr_px` —— DOE 真正要的那個數字

現有 `snr` 的分母是**框與框之間**（使用者 2026-08-21：「SNR 全線改成 by box，
by pixel 會太小」），而**參照少於兩格時整格不寫**。DOE 只有一個 target box、
一個 ref box —— 所以 `snr` 對它永遠是空的，而那正是 `snr_px` 存在的理由。

`snr_px = |μT − μR| / σR`，直接用 `algo/snr.snr_signed`（這個 repo 帶正負號慣例的
**規範出處**，而它到今天為止只有一個 `hasattr` 測試在守 —— 現在它有第一個真的
呼叫者）。⚠ 算在 `if len(boxes) < 2: return out` 那個提前返回的**上面**，否則它在
唯一需要它的情況下被安靜地丟掉。**現有 `snr` 一個位元組都沒動。**

畫面上它自己一群（`Vs pixels`），不掛在 `Vs boxes` 底下：那個群名講的正是 `snr`
的分母，而**分母是這兩個數字唯一的差別**。⚠ 新群名沒加進 `METRIC_GROUP_ORDER` 的
下場是那一群的膠囊**安靜地不畫**（F77 真的踩過）。

### ④ 流的「內容型別」（Q1）

**把 layout label map 接進 Normalize，今天是一條完全合法的線**，而 lint／畫布／
引擎三層都沒擋。它的像素值就是層號，正規化會把 1、2、3 混成 1.7 —— 跑得完、
不報錯、預覽上那張圖看起來還變漂亮了，而下游每一個區域都是錯的。
`load_sidecar.py` 從 2026-08-18 起就逐字寫著這件事，但那句話擋不住一條線。

`ParamSpec.content`（`gray`／`label`）由產出那一格宣告、沿著線傳下去，
只收灰階的輸入格吃到 label 就是一條 **`wrong-content`**（error 級）。
**沒宣告 = 只收灰階**，保守的預設是刻意的：加新卡的人不必想這件事就受保護。

順手刪掉 **`Context.labels`** —— 量過了：**沒有任何一張卡寫過它**，只有引擎與快取
快照在搬運它。一個沒有人寫的欄位不是「還沒用到」，是一條**看起來存在的第二條路**：
下一個要傳 label 的人會挑它，而它不進快取簽章、畫布上也沒有線。
快照欄位集合改了 → `cache.FORMAT_VERSION` 4 → 5。

### ⑤ `focus_quality` 吃區域（Q4）＋ ⑥ 三個 label 剪短（Q5）

`MultiSourceStep` **本來就有整個區域迴圈**（`REGION = "roi"`），所以前者是加一格
參數。⚠ 裁的必須是**二維的一塊**（`crop_to_roi`）不是 `roi_pixels`：銳利度量的是
相鄰像素之間的變化，攤平之後「相鄰」是假的，而四個數字照樣算得出來。
多框區域走既有那條路（報錯並指名 `<name>_center`，CD 卡同一條），不自己發明規矩。

label：`Remove background / stripes` → `Flatten`、`Pair with another source` →
`Pair source`、`Load layout labels` → `Load layout`。天花板跟著從 27 降到 17，
外加一條**反向**測試把「上限＝真的最大值」釘住。

### `studio.py` 那三格只准往下的 —— 這一輪是往下

第五顆 Open 鈕要加，而規矩是「先從它手上搬走等量的東西」。搬的是**五顆 Open 的
對話框與那個「按下去要做什麼」的分岔**（→ `ui/open_dialogs.py`）：
行 7,753 → **7,717**、方法 298 → **294**、`self.*` 437 → **434**，三格一起往下。

**順便讓一句話變成真的**：`CLAUDE.md` §5 寫著「加／改一個入口＝改 `INPUT_SOURCES`，
不要動 UI」，而在這之前加一列就得同時在 `studio.py` 上長一支 `_on_open_<key>`
出來，不然那顆鈕按下去是 `AttributeError`。現在五種共用
`open_dialogs.open_source`，那句話第一次成立。

### 黃金值：這一輪的驗收是「**沒有變**」

跟 F109 相反（那一輪是行為真的改了）。`freeze_golden.py --check` 三份全綠**而且
沒有重凍** —— 兩道新遷移必須跑出逐位元組相同的數字，變了就是遷移寫錯。

⚠ **一個被測試當場擋下來的錯誤**：`absolute → sign` 那一道第一版寫成版本閘
（照抄 F109 的 align），而 `test_reading_a_recipe_never_invents_a_parameter` 立刻紅了。
它是對的 —— 舊的 `absolute=True` 跟新的 `sign="abs"` **是同一件事**，所以檔案裡
沒寫就什麼都不該寫進去。三道遷移三種判準，差別在**預設值的意思有沒有變**：

| 遷移 | 判準 | 為什麼 |
|---|---|---|
| align（F109）| 版本號 | 舊預設與新預設是兩種行為，從「缺一個 key」分不出來 |
| `subtract` 拆卡 | 舊的**值**（`op` 是不是 max/min/mean）| 鐵則 9 正牌 |
| `absolute` → `sign` | 舊**鍵**在不在 | 同上，而且預設值的意思沒變 |

### 沒做完的那一件 —— ⚠ **而這個判斷是錯的（F111 更正）**

> 下面這一段是當時寫的，**逐字留著**：它是「我當時怎麼想的」，而更正一句錯話的
> 前提是看得到錯的那一句。正確的版本在下一段。

> **`recipes/doe-conditions.json` 出不了貨**，而理由不是時間：三種找 ROI 的方法
> （條紋／我標的 cell ＋ 模板比對／GDS label map）**都要有東西可以鎖**，而 DOE
> **不需要找** —— defect 本來就固定在 FOV 正中間，要的是「把框放在這個固定位置」。
> 那是第四種 method（或一張新卡），是**卡片層的決定**，不是一份 recipe 寫得出來的。
> 硬用 `roi_template` 的話要在 recipe 裡塞一張模板圖，而 DOE 的影像未必有可重複的
> pattern 給它鎖 —— 那份 recipe 會在 `test_shipped_recipes` 裡真的跑，然後真的失敗。

**更正見下一輪（F111）**：那一段的每一句推論都對，只有**前提**是錯的 ——
「要有東西可以鎖」不是卡片要去猜，那一張 template 本來就是使用者自己挑的。
DOE 的出貨 recipe **不缺任何卡**。

### 天花板

`recipe.py` 3,949 → 4,101（兩批：`wrong-content` 的兩支 ＋ 第 21、22 道遷移），
遷移道數 20 → 22，`RECIPE_VERSION` 4 → 5，`cache.FORMAT_VERSION` 4 → 5，
卡片 label 上限 27 → 17（往下），`studio.py` 三格往下（見上）。

---

## F109：align 重做並拿回卡片庫 —— **對齊不動灰階**（2026-09-17）

使用者定調把 `align` 拿回來，而且講清楚了用途：**DOE**。同一顆 defect、位置固定在
FOV 正中間、FOV 相同，用**不同 E-beam condition**（Landing energy／電流）各拍一張，
對齊之後在**同一組 target／ref box** 上比 SNR 與 contrast。對標公司內的 imageY 流程
（一次載入許多條件的圖、設一組 box、對齊、一起量）。輸入是**一個資料夾的圖片、
沒有 KLARF、一顆就是一張圖**。

2026-08-18 收起它的時候使用者說的是「**之後真需要我再回來**」—— DOE 就是那個「之後」。
`CLAUDE.md` §5 那張表（收起來／刪掉／改名）第五次被驗證：**收起來的成本是零，
回復的成本是改一個字串**。

### 它當初做錯的那件事這一輪修掉了

收起來的理由是「拉 align 反而會飄掉 shift」，而那有兩個機制：

1. 真實位移接近 0 時，相關峰的位置由雜訊決定；test 有缺陷、ref 沒有，**缺陷把峰往
   自己那邊拉**。
2. **只有被移動的那一條被重採樣**（次像素走 `cv2.INTER_LINEAR`）—— 等於對它過一次
   低通、對基準那條沒有。

**DOE 讓第 2 個從副作用變成致命傷**：量的就是 SNR，而 SNR 就是灰階。對其中幾張各過
一次不一樣的低通，再去比它們的 SNR，那個比較是假的。

而 `align_to`（H2H）早就解出正解（`align_to.py`：「次像素的那一點點留在數字裡 ——
不要為了對齊而重採樣」）。這一輪就是把那條紀律套到 align 上：**位移只取整數，
所有流一起裁成共同重疊區**，次像素仍然寫進 `align_dx` / `align_dy`。
第 1 個機制**沒有**修：要修它得讓對位只看一塊不含缺陷的區域，那是另一件事。

### 形狀：一張卡、N 條流、就地對齊

| 參數 | 型別 | |
|---|---|---|
| `streams` | `image_keys` | 要對齊的那幾條（**含基準**） |
| `fixed` | `image_key` | 基準（不在 `streams` 裡 → lint 報錯：它不會被裁，出去的尺寸就對不起來） |
| `method` | `chip_choice` | 五個 backend 沿用 |
| `search_radius` | `int` | 沿用，**補了 `extent`** |
| `suffix` | `str` | 空 = **寫回原名**（遷移就是把舊檔案帶到這裡）；填了才寫在旁邊 |

加幾個 condition 都只有一張卡。特徵：一條對一條**不加前綴**（舊 recipe 的分數表達式
寫的是 `align_dx`，改名等於讓每一份舊 recipe 都算錯）；三條以上才帶流名前綴。
新增 `align_valid_frac`（裁完剩原來的幾成）—— 照「卡片自動做的每一個決定都要變成一個
畫得出分布的數字」。

⚠ **裁切會改變正規化座標的意義，所以 ROI 卡要接在 align 之後**（`Load → Align → ROI → GLV`）。

### 順便修掉三個「看起來像做完了」

* **`align_score` 的 help 值域是錯的**：寫著 `0 to 1`，而 `algo/align` 每個 backend
  都 `* 100` → 實際 0–100。那個數字**進得了分數表達式**，而 help 是使用者唯一讀得到
  的說明 —— 寫錯就是把人帶到一個差 100 倍的門檻上（`score < 0.8` 會是「全部都過」）。
* **尺寸不符時回 `dx=0, dy=0, score=0` 而三個數字照樣流進 features** → 改成**報錯**，
  訊息指名該用 `H2H`。單顆報錯只讓那一顆 `ok=False`，整批照跑（鐵則 7）。
* **`search_radius` 是半徑，而 UI 那個框畫的是邊長** —— 填 `extent=True` 的話畫面上
  那個框只有真實搜尋範圍的**一半**，而「一個小一半的搜尋窗」看起來完全正常。
  新增 `ParamSpec.extent` 的 `"radius"` 值與 `ParamSpec.extent_px()`：換算住在
  `ParamSpec` 上而不是 UI，因為「半徑還是邊長」是**參數自己的性質** ——
  放進 UI 就變成一張要跟著 `ParamSpec` 走的對照表，而那種表會漂。

### 黃金值變了，而每一格都解釋得出來

第 20 道遷移（`_migrate_align_into_streams`，`RECIPE_VERSION` 3 → 4）：
`moving`/`fixed`/`out` → `streams`/`fixed`/`suffix`。判準照鐵則 9 看**舊鍵在不在**，
但 fixture 那一份**一個舊參數都沒寫**（全靠預設值），所以實際的閘是
`version < RECIPE_VERSION`。這道遷移比前 19 道都長，理由是 align 的舊 `out` 是一個
**下游看得見的名字**（`ref_aligned`）—— 換掉它還要改每一張指著那個名字的 `image_key`
參數與 `recipe.edges` 上的 `src_out`。少改任何一邊，舊 recipe 開起來就是一條斷掉的線。

**而 `dual_route_basic.json` 的準確率從 24/24 掉到 18/24 —— 追下去發現舊的那個數字
才是假的。** 把 align **整張停用**也是 18/24：舊的 24/24 靠的是「ref 被一個雜訊驅動的
次像素重採樣過了一次」。`tools/make_sample.py` 的 `shift_max` 預設是 **0**（機台出的
patch 本來就對好了），所以量到的 0.1–0.36 px 全是雜訊，那次重採樣沒有在修正任何東西
—— 它**就是**使用者回報的那個「飄」。

拿掉之後分數反而變乾淨：seed 7 上 nuisance 最高 5.38、真缺陷最低 5.81，兩類完全分得
開，而**舊門檻 4.2 落在 nuisance 範圍裡面**。跨四個 seed（7/3/11/21）掃門檻：
4.2 → 73/96、5.4 → 87/96、6.0 → 88/96。取 **5.4**（平台的左端，不是掃描的 argmax ——
取 argmax 是對掃描過擬合）。

⚠ 中途有一個**被自己的實驗推翻的假設**：我猜「那層意外的低通本身在幫忙」。實測對
ref 顯式加模糊：gaussian k=3 → 13/24、median k=3 → 14/24、gaussian k=5 → 16/24 ——
**全部更差**。真正的原因是那個沒跟著搬的門檻。

### 守門（每一條都先驗過「把錯誤放回去會紅」）

新檔 `tests/test_align_card.py`（21 條）：

* **對齊不動灰階** —— `ref` 是 `test` 整數平移過的同一張圖，所以裁完之後兩張必須
  `np.array_equal`。**這不是「差很小」，是那個等號** —— 它就是這張卡的承諾。
* **出去的每一個灰階值都是進來那張圖上真的有的值**（`INTER_LINEAR` 會造出原圖沒有的
  中間值）。兩條都對五個 backend 各跑一次。
* N 條流裁完尺寸一致；`align_valid_frac` 對得上實際裁掉的比例。
* 尺寸不符報錯、單一條流報錯、`fixed` 不在 `streams` 裡是 lint error。
* **反向**：`align_score` 的 help 宣稱的值域**從 help 裡讀出來**，跟五個 backend 實際
  跑出來的分數比（上界還要「貼著真值」—— 寫 `0 to 1000` 也會紅）。

`tests/test_recipe.py` 三條守那道遷移（換參數、**改下游**、`out == moving` 時不要順手
改壞它的線），外加「遷完之後 `to_json_dict → from_json_dict` 仍然是 identity」——
那一對正是 `run_batch` 送 recipe 進 worker 的路（鐵則 9）。

### 儀表板那一塊也要跟著，不然 DOE 上它是一張空圖

`AlignInspector` 畫的是**整批的位移散佈圖**（對位失敗在單顆上看不出來 —— 演算法一定會
回一個位移，真正的訊號是「點貼在搜尋框的邊上」）。它以前寫死 `align_dx` / `align_dy`
兩個名字，而**三條以上的流時特徵名帶著流名前綴** —— 也就是說 DOE（一次 N 個 condition，
正是這張圖最有用的時候）會得到一張空圖，而空圖上寫的是「跑一次試跑就看得到」。
使用者照做之後還是空的，然後去懷疑資料。

名字改成跟卡片要（`align.shift_feature_names`），並加一條測試守著它跟
`resolve_features` **不准漂開** —— 那是兩支各自算前綴的函式，而那種對子會漂。

`tests/test_ui_scope_profiles.py` 兩條改寫過：它們本來斷言 `HIDDEN_STEPS == ("align",)`
與 `"align" not in fab_keys`，而這一輪把 align 拿回來就紅了。**紅得沒有道理** ——
壞掉的不是「一句話設一組開關」那個機制，只是那組開關的內容換了。改成問機制本身：
用哨兵值驗「每一格都真的被寫過」、當場塞一張卡進 `HIDDEN_STEPS` 驗「`visible_steps`
真的讀得到現在的值」（**空的清單過濾不掉任何東西，那正是這種測試最危險的時候**）。
另外加一條把「現在沒有收起任何卡」釘住：**收起來是使用者說出口的決定**，悄悄多一個
字串 = 有一張卡從畫面上消失而沒有人做過那個決定。

天花板兩格簽了名：`recipe.py` 3,870 → 3,949（第 20 道遷移），`recipe_migrations`
19 → 20（那一格問的「舊到哪一版可以不再自動轉」這次有答案：不寫這道遷移，
帶著舊參數的檔案開起來是一張參數全空的卡，**跑得完、有數字、而且是錯的**）。
`inspectors.py` 3,660 → 3,669（散佈圖跟卡片要名字）。
`studio.py` 的只往下那一格**沒有動** —— `extent_px` 的換算搬進 `ParamSpec`，
UI 那一行只是換了呼叫對象，淨值 0。

⚠ 一個**連帶的名字變化**：撞名時被蓋掉的那份 `align_dx` 以前叫 `ref_aligned_align_dx`
（F17-② 的規則：前綴用「那張卡寫出去的那條流」），現在退回節點 id 叫
`align_align_dx`。那是照 `feature_prefix` 自己寫著的退路走的 —— 新的 align 寫 N 條、
讀 N 條，**兩邊都不是剛好一條**，而且兩條以上時沒有任何一條流名說得出 `align_dx` 是誰的
位移（它講的是被移動的那一條，不是基準）。F17-② 那條規則本身由
`tests/test_feature_owner_prefix.py` 守著，那一份一個字都沒改。

### 這一輪同時收斂的：Compare 段是什麼

使用者問「Compare 段要放什麼」，並且指定**不要從既有程式碼回答**。討論出的判準是
**訊號形狀，不是意圖**：

* **Enhance** = 1 條流 → 1 條流
* **Compare** = 2 條以上 → 一條流
* **Measure** = 流（＋區域）→ 數字

用「意圖」當判準的話 Enhance 整段都會被吞進來 —— 每一張 Enhance 卡都是為了讓後面
比得準。而**「跟誰比」不該是任何一張卡的參數**：那由畫布上的線決定（鐵則 10）。

⚠ 討論中我說「手畫框是個缺口」，**使用者當場糾正**：`roi_template` 的 `regions`
（型別 `cell_rois`）就是手畫的矩形。已經有的東西不要當成缺口。

Compare 段剩下三件（**這一輪沒做，已定案，寫進 `docs/ROADMAP.md` 那一列**）：
① DOE 的輸入形狀（`load_folder` 今天是「一個檔案 = 一顆」，DOE 要的是「一個資料夾 =
一顆、裡面每個檔案 = 一個 condition」）；② 新 metric `snr_px` = `|μT − μR| / σR`
（⚠ **不能改現有 `snr`**，它是框與框之間的 σ —— 同一個名字兩種算法是這個 repo 最
明文反對的）；③ `Image Combination` 拆成**比較卡**與**融合卡**。①② 做完配一份
`recipes/doe-conditions.json`，README 要寫一句：**DOE recipe 裡不要放 `normalize`**
—— N 張的亮度差異正是你要量的東西，一正規化就抹掉了。

另外三個卡片位置的問題也定案了（都**不在這一輪**）：**label map** 要加「流的內容型別」
（gray／label）並刪掉死的 `ctx.labels`（今天把 label map 接進 Normalize 是一條
**完全合法**的線，而 lint／畫布／引擎三層都沒擋）；**`focus_quality` 要吃區域**
（三張 Measure 卡裡唯一沒有 `region_keys` 的）；**三個 label 太長**
（`Flatten`、`Pair source`、`Load layout` —— 27／24／18 字元，中位數 11，
太長的在「Add ▾」裡會被截掉）。

---

## F108：封存九月上旬 —— 把搬運包的成長按回去 79 KB（2026-09-17）

F107 量到 `bundle/d4t_bundle.py` 兩週從 2,172 KB 長到 **4,243 KB**。那不只是大小：
包是 lzma+base64，每次 commit 整份改變，**git 沒辦法 delta 壓縮** —— F84 直接量過，
repo 378 MB 裡 **98% 是這一個檔案的歷史版本**。而 `docs/history/` **不進搬運包**
（`tools/make_filelist.py` 的 `EXCLUDE_DIRS`，`make_text_bundle.py` 共用同一份定義），
所以封存是一個**不刪任何內容**就按得回去的動作。

* **切點在 09-08／09-09 之間**（使用者定的）。搬走 F99/F100（09-08）一路到 F67（09-01），
  **2,472 行 / 158 KB** → [`docs/history/2026-09.md`](docs/history/2026-09.md)（第四份封存）。
  留下 09-09 那四輪與 09-17 那幾段 —— **09-09 定的是鐵則 11**（跑不寫、寫是另一個動作），
  還在被引用；而 09-09 同時是 `CLAUDE.md` 封存的日子，切在那裡兩份對得上。
  `SESSION_LOG.md` 從 2,837 行 / 186 KB 縮到 **368 行 / 32 KB**。
* **實際省 79 KB**（4,243 → 4,164 KB），比 2026-09-02 那次的 182 KB 少一半 ——
  **那次連 18 份做完的計畫書一起搬，這次 `docs/plans/` 只剩 F11 一份活的，沒得搬。**
  如實記進 `AGENTS.md` §2 的水位表（那張表是下次有人想省的時候唯一的依據）。
* **唯一准改的是相對連結的深度**（`docs/history/README.md` 白紙黑字：「搬完檔案本身的
  相對連結也要重算（深了一層）」）—— **12 條** `](docs/history/plans/…)` → `](plans/…)`，
  逐條核對過，`test_docs_links` 也綠。內容一個字都沒有改。
* **三處指標跟著改**：`SESSION_LOG` 最上方那張表（第一列重寫成「09-09 起」＋補一列指向
  新封存檔 —— 那一列本來就已經漂了，它列到 09-09 為止，完全沒提 F87/F88/F90–F98/F102–F107）、
  `docs/history/README.md` 的開發紀錄表、以及**該檔 F68 那一列**寫著「驗收由 F73 補跑完，
  見 `../../SESSION_LOG.md`」—— **F73 這一輪被搬走了**，改指新檔。
  最後那一條正是 F107 講的那個盲區：**連結指得到，但指錯地方**，`test_docs_links` 抓不到。
* 順手修一條同族的：`docs/history/README.md` 結尾寫著 `release.py`「超過 85% 就會叫」，
  而 `tools/release.py::bundle_size_report` 的 docstring 自己寫著那一級**早就拿掉了**
  （「一句沒有對應動作的警告只會訓練人忽略警告」）。

⚠ F107 加的兩條水位測試**這次都沒叫**，而那是對的：表上的 max 仍是 4,243，
實際 4,164 落在 `[0.8, 1.25]` 之內。反向那條守的是「一次搬走一大塊卻沒記一筆」，
79 KB 不到那個量級 —— **測試沒叫不等於不用補那一列**，慣例比測試寬。

---

## F107：文件稽核 —— 「名字對、說明錯」那個盲區，補七道守門（2026-09-17）

使用者要求「瀏覽專案後，完整的整理專案內容」，順序定為**先稽核修正、再做總覽**。
逐項驗證出 **20 條漂移**，而它們全部落在同一個盲區裡：
`test_docs_links`（指標）、`test_doc_file_tree`（樹上的名字）、`test_docs_match_registry`
（卡片數／recipe 份數）三支的檔頭**都自己寫著「抓不到『名字對、說明錯』」** ——
這一輪量到的就是那一類。

**最貴的一條不是文件，是使用者看得到的那句話**：`roi_reference` 的 `help` 對使用者說
`"Four ways to find them"`，而 `METHODS` 只有三個（`repeating cells` 2026-08-25 就刪了）。
照那句話去找第四個的人找不到 —— 第二原則說那是 bug，不是文件問題。
同一支檔案的註解還寫著「``method`` 的**兩個**值」。一份文件、三個答案。

其餘幾類（完整清單在這一輪的 diff）：

* **同一份文件裡兩個答案**：`ARCHITECTURE.md` 的「Output 段是三張卡」對「Output 段四張」
  （`output_uniformity` 是 F85 加的）、「三個 method」對「四種找法」；
  CLI 清單漏 `simgen`，而同一份文件下面自己在教 `python -m d4t simgen`。
* **事實已變而文件沒動**：`welcome.py` 那一行還寫著「兩個入口目前收起來」（09-08／09-09
  都開了）；結尾那段還教人去改 `SHOW_SAMPLE_ENTRIES`，而 `test_ui_template_library.py`
  有一條斷言那個名字**不存在** —— 兩邊隔著一個月各說各話。
* **抄了第二份的數字**：`widgets.py`「123 行」抄在 `CLAUDE.md` 與 `ARCHITECTURE.md`
  兩處，實際 137（而 `test_size_ceilings` 的 `FILE_CEILINGS` 早就是 137）——
  那一支的設計規則 4 寫的就是「數字只住在這裡，不要在 `CLAUDE.md` 抄第二份」。
  `studio.py`「6,000 行以上」（7,753）、`tests/` 的「179 檔／2,700+ 支」（252／3,832）、
  `HANDOVER` 的「588 tests／30 秒」、`pyproject` 的「3,126 支」、`ci.yml` 的「2,989」同族。
  **全部改成連結，不是改成新數字** —— 那正是 `CLAUDE.md` 給的退路。
* **那張盯水位的表自己過期了**：`AGENTS.md` §2 停在 2026-09-02 / 2,172 KB，
  實際 4,234 KB —— 兩週又翻一倍，而那張表存在的唯一理由就是盯這件事。
* `recipes/README.md` 少了 `one-image-uniformity.json` 那一節（那份 recipe 有測試跑）；
  `README.md` 的文件索引少了兩份 `docs/*.md`；`HANDOVER` 指「加卡片看 `CLAUDE.md` §5」
  而那在 §3（§ 存在，所以 `test_docs_links` 綠 —— 它檔頭就說了自己抓不到這個）。

**七道新守門全部住進 `tests/test_docs_match_registry.py`**（那一支就是這個主題的家）：
Output 卡數（從 registry 的 `GROUP_OUTPUT` 數）、CLI 子命令（從 `__main__.py` 的
`add_parser` 抽）、文件不得提到 `d4t/ui/` 裡不存在的 `SHOW_*`、`recipes/README.md`
每份 recipe 一節、**`roi_reference` 的 help 宣稱的數量 = `len(METHODS)`**、
README 要連到每一份 `docs/*.md`、bundle 水位不得超出 `AGENTS.md` 那張表 1.25 倍。
既有的「目前 N 份」那條加進 `README.md`。
**十條各自驗過「把錯誤放回去會紅」。**

水位那一條**刻意不是相等**而是上限（×1.25，配一條反向 ×0.8）：bundle 每次 `release.py`
都會長幾 KB，要求逐 KB 相符只會逼每個 commit 去改那張表 —— 那是劇場，不是煞車。

⚠ 兩次撞到尺：`studio.py` 的註解改長了 2 行（`HARD_CAPS` 只准往下）、`recipe.py`
多 1 行 —— 兩處都改回等長，**沒有調高任何一格上限**。

---

## F105：交錯晶格＋粗亮線上的週期量測退化 —— 小數週期、半週期陷阱、第一峰規則（2026-09-17）

外部沙盒拿一張真實大圖（交錯晶格、亮線 10 px、人工驗證 41 × 79.5）回報：投影法回 (41, 40)、
F104 的二維回 (10, 30)、仲裁照抄投影、`build_golden_cell` 再把 79.5 截成 79 —— 格線「靠邊會滑」
（[`docs/history/plans/F105-staggered-thick-lines-period.md`](docs/history/plans/F105-staggered-thick-lines-period.md)）。
使用者定的範圍：小數週期**做到疊圖**、加交錯分數（旋轉角另開 F106）、摘要要顯示每一句量測決定。

* **`period2d`**：第一峰門檻 0.5 → 0.85（線寬峰、交錯半格 0.6–0.67 對真週期 0.92）；諧波鏈擬合次像素
  （`px_sub`）；`autocorr2d` 補零成**線性**自相關（環狀的在視窗不是週期整數倍時拉歪遠諧波，318.47 對 318）；
  `half_period_check` 第三票（沿軸 `ac[2q]` 比 `ac[q]` 高 0.1 才加倍）＋交錯分數。
* **`template`**：`_measure_period` → `MeasuredPeriod`（小數、notes、stagger、doubled）；snap 是**漂移界**
  （整張圖 ≤ 0.5 px）不是絕對值；小數疊圖 = `cv2.resize` 成整數 pitch 再走今天的整數機器（一條路徑、F86
  逐位元組照守、相位搜尋成本不變：tile 大小 3.6 s 對 3.7 s）。`GoldenCell` 加 `period_x/y`、`stagger`、
  `doubled`、`notes`；`origin` 可以是小數（格子左上邊 `x'/s`，不是像素中心 —— 那會少畫一列）。
* **UI**：Cell W／H 改 `QDoubleSpinBox` 餵真的週期（否則 Re-stack 安靜用 80）；格線用 `golden.cell_origins`；
  摘要 `cell 41 x 79.5 px` 並列出每一句 notes（F104 的「交錯」以前畫面上看不到）。
* **測試**：`test_period2d_staggered.py` 十九條（解析式 body-centred fixture、fixture 有牙齒、每條例外規則的反向、
  小數疊得比截成 79 的齊 0.995 對 0.932）；F86 逐位元組測試加 float 型整數參數；一條 UI。`typecheck` 上限 136 → 128。
* **PITFALLS 加兩列**：半週期／線寬陷阱；銳利度與鋪回去的 NCC 都不是週期的裁判（錯的反而更高）。

---

## F104：二維自相關找峰；模板對話框收回一列；Mark one cell 刪掉（2026-09-17）

使用者看過 F102／F103 之後定的三件事（[`docs/history/plans/F104-period2d-and-fewer-buttons.md`](docs/history/plans/F104-period2d-and-fewer-buttons.md)）：

* **二維自相關**（`core/algo/period2d.py`）：交錯 layout 上投影法 X 軸互相抵消（實測
  回 None、Y 回一列的高度），二維自相關沿軸找離原點最近的峰 → 真正的矩形單元 32 × 48。
  分工在 `template._measure_period`：投影法是主，同意就不改（黃金值不動），只在
  「投影量不到而二維量得到」或「二維是投影的整數倍」時接手並講一句。
* **按鈕收回一列**：crop 併進載入（每次載入都先問「哪一塊」，整張是一顆鈕）；
  「Mark one cell」**刪掉**（使用者：不實用）—— `seed.py`、`origin=` 參數、seed 模式、
  三十幾條測試一起拿掉，`GoldenCell.origin` 留著給格線用。
* **Grid 開關**取代「Check on the image…」：開＝格線視窗出現、跟著 re-stack 更新；
  關＝收起來；直接關視窗開關跟著彈回。

---

## F102：疊模板之前先框一塊；cell 週期怎麼算、算錯怎麼知道（2026-09-17）

使用者：「幫我加入 crop 功能，載入 template 的大圖，可以選擇要不要 crop 想要的部分
之後再進行計算。目前計算 cell 方式你覺得還可以添加什麼方法，假設算不對我該怎麼知道？」

**Crop 做了**（[`docs/history/plans/F102-crop-before-stacking.md`](docs/history/plans/F102-crop-before-stacking.md)）：
新模組 `ui/crop_dialog.py`（`CropView` 拉框、`CropDialog` 三選一），`TemplateDialog`
多「Crop first」勾選（挑圖／用畫面上那一張之前先問）與「Crop…」鈕（事後換一塊，
重新量週期）。裁的是原料不是結果：框不進 recipe，摘要講「cropped to W × H px at
(x, y)」；`restack` 走整張＋框。從 recipe 讀回的模板沒有原料，「Crop…」講出來。
`tests/test_ui_crop_dialog.py` 十一條。

**F103 —— 使用者說「好 試試看」，當天做了清單裡的第 1 項與「鋪回原圖」**
（[`docs/history/plans/F103-seed-cell-and-lattice-check.md`](docs/history/plans/F103-seed-cell-and-lattice-check.md)）：
`algo/seed.period_from_seed`（框一格 → NCC 找複本 → 框那一列／那一行剖面的峰間距
＝週期、框的左上角＝原點；平的軸靠「整條剖面都很像」擋掉）、`GoldenCell.origin`
（含錨定捲動的格線原點；`build_golden_cell(origin=)` 不搜相位不錨定）、
`ui/lattice_dialog.py`（`ImageView` 把引擎真的用的格子鋪回原圖）、`TemplateDialog`
的「Mark one cell…」與「Check on the image…」。兩個第一版的坑都有測試：平的軸量到
假週期、沒有週期的軸原點不是 0 就疊出全黑的 cell。

**使用者拿去用回來的三件**（同一天）：① 「使用後跳出 error」——`CropView` 有一個叫
`rect()` 的方法蓋掉了 `QWidget.rect()`，還沒拉框時 `paintEvent` 的 `fillRect(None)`
炸在使用者面前；headless 測試沒抓到是因為視窗從沒真的畫過。改名 `box()`／`set_box()`，
`tests/test_ui_crop_dialog.py` 現在 `grab()` 一次逼三個視窗真的畫。② 「上方按鈕變得
有點多」——那一列有十一個東西，拆成兩列：圖從哪來（還沒有圖就有意義）／cell 怎麼定
（每一顆都要先有圖），第二列排不下橫向捲。③ 「我該怎麼使用」寫在回覆裡。

**cell 計算的替代方法與「算錯怎麼知道」** 寫在回覆裡（摘要）：現在是投影 FFT ＋
自相關（`algo/period`），弱點是投影會把二維結構壓掉、對斜的／非曼哈頓 layout 與
「兩種 cell 混在一張圖」無解。可加的：二維自相關直接找峰（不靠投影）、使用者拉
一格當種子再用 NCC 找相鄰複本量週期（跟 crop 同一種手勢）、GDS 給的 pitch 直接
填（`build_golden_cell` 本來就吃明講的 px/py）。算錯的訊號已經有四個（agreement、
sharpness、k× 提示、諧波修正的 warning），缺的是「把 cell 鋪回去疊在原圖上看」與
「換一塊 crop 重算、兩個答案要一樣」—— 後者現在用 Crop… 就做得到。

---

## `.I01`：副檔名不同的 patch TIFF；Load 卡要不要合回一張（2026-09-17）

使用者：「我想將 load (input) 卡片整合，你覺得呢？同時我要能支援新的圖檔叫做
I01，一樣是跟 klarf 一一配對的」。兩件事，一件做了、一件給了建議等定調。

**`.I01` 做了（F101，[`docs/history/plans/F101-i01-companion.md`](docs/history/plans/F101-i01-companion.md)）**
—— **不是新 kind、不是新卡**：一份 KLARF 配一個檔、裡面是多頁 TIFF，資料形狀跟
`.tif` 逐項相同，所以副檔名只住在「去哪找檔」那一層：

* `klarf_core.PATCH_IMAGE_EXTS = ('.tif', '.tiff', '.I01')`，`tiff_path()` 的同名候選
  多找它（大小寫都試，Linux 分大小寫）；KLARF 的 `TiffFileName` 直接指到 `.I01`
  本來就吃得下。找到之後 kind、卡片、快取簽章都看不到副檔名。
* `dataset._TIFF_EXTS` 多 `.i01`（`Open image…`／`Open folder…` 的「這是多頁檔，去
  開 stack」提醒一視同仁）；Studio 的 stack／image 兩個對話框過濾字串加 `*.I01`；
  CLI `--tiff` 的 help 講明兩種副檔名。
* **真檔當天就看到了**（使用者的另一個 agent 解析 `.001`＋`.I01`，只貼結構不貼
  識別碼）：record 語法 1.8、`ImageFileName` 住在 `WaferRecord`、`.I01` 是 MM 多頁
  TIFF 64×64 8-bit、列尾 `Images 2 {id "30", id "31"}` 的 **id 全檔連號、page = id − 1**
  —— 正是 `defect_image_map` 既有的 imagelist 模式，對映零改動（`FAB-VALIDATION.md`
  #8 當天開、當天結）。使用者接著確認 **`"30"` = test、`"31"` = ref，「以後 pair 的都預設
  第一張為 test」** —— 跟 `Load images` 預設的 `1:test, 2:ref` 一致，零改動。順手補兩件：`defect_image_filename` 不再把 `"30"` 當檔名；
  `.I01` 不在旁邊時 `load_dataset` 講出 KLARF 點名的那個檔名。
* **假設錯的那一天**（`.I01` 內容不是 TIFF）：`load_dataset` 先
  `tiff_index.check_header`（8 個位元組），不是就 warnings 講一次「哪個檔、為什麼、
  跑哪支探測腳本」，defect 進來、沒有影像。以前 `bit_depths` 對非 TIFF 安靜回空
  list（刻意的），後果是載入看起來正常、每一顆各自倒在 `Not a TIFF` 上。
* `tools/make_sample.py --image-ext .I01`：家用機唯一能練這條路的資料；預設產出
  逐位元組不變。兩支 fab_probe 跟著改（`sibling_tiff` 鏡射候選表、`probe_tiff`
  的用法多一行）。守門 `tests/test_i01_companion.py`（十三條：同名找得到、KLARF
  指名找得到、像素跟 `.tif` 那份一模一樣、內容不是 TIFF 時那句話、三處對得上、
  兩支探測腳本讀得動、真檔形狀的三條）。

**Load 卡合併：建議不併（等使用者定調）。** 理由寫在回覆裡，摘要：拆是使用者
2026-08-17 自己定的（「畫布跟實際對不起來」），而拆完之後兩張卡都只看使用者看得到
的值（`channel_map`／`out`）—— 合回一張的話單張資料要靠 `1:single` 這種對照表
才不說謊，等於把「選哪張卡」換成「填對那張表」，沒有比較簡單；代價是一道遷移
（`load_single` → `load_patch`）、兩份出貨 recipe、三十幾支測試、起手卡與 lint
的 kind 分支、黃金值。**`.I01` 不需要它**：格式住 ingest，卡片只看「一顆幾張」。
如果痛點是「不知道該選哪張」，便宜的做法是卡片庫依載入的資料只亮那一張
（`scope` 的機制），不是合併。

---

## 體檢與十四件待辦（2026-09-09 第五輪）

使用者：「給這個專案一些建議（各方面）」→「把它整理成待處理事項，列出解決方法」
→「好 開始修正」。先量再開清單，十四件裡十三件做完，一件做了一半（見末段）。

量到的（都有證據）：`studio.py` 的天花板兩天被調高 17 次（尺變成流水帳）；
`d4t/` 有 203 個 `except Exception`、59 個直接吞掉、零處 `logging`；文件裡
「幾張卡／幾份 recipe」四處三種答案；421 條 `noqa` 標的是沒開的規則；
`test_glv_combinations.py` 在核心批裡開 Qt，沒有 Qt 函式庫的機器核心批紅 34 條；
`pytest` 與 `python -m pytest` 不是同一個直譯器；`docs/plans/` 八份有七份早已出貨。

做了什麼（一件一個 commit）：

* **尺**：`HARD_CAPS` —— `studio.py` 那三格上限本身不准再調高（凍在 logger 那一刀
  之後的 7,753／298／437）。`CLAUDE.md` 也進 `FILE_CEILINGS`。
* **留痕**：`d4t/core/log.py`（一個 logger、預設不寫；`swallowed("模組.函式")`），
  59 處補一行、`ctx.warn` 送一份、CLI `run --log`、Studio 寫進 `crashlog.log_dir()`。
  `tests/test_core_log.py` 用 ast 守「寬的 except 不准再安靜吞掉」。
* **文件對真值**：`tests/test_docs_match_registry.py` 從 registry 與 `recipes/` 數。
  `tests/test_plan_docs.py`：計畫書前 5 行要有「狀態：」，七份已收斂的搬進 history。
* **測試分批**：兩支改名 `test_ui_*`；核心批的 lazy Qt import 一律
  `importorskip("PySide6.QtWidgets", exc_type=ImportError)`（pytest 9 起預設只認
  `ModuleNotFoundError`；dev extra 的 pytest 底線抬到 8.2）；`test_no_qt.py` 兩條守門。
* **工具鏈**：`ruff` 加 `RUF100`、清 352 條沒作用的 `noqa`（有說明的留成註解）；
  `tools/typecheck.py`（pyright basic 掃 core，上限 136）＋ CI job；UI 批只在 3.11 跑；
  `.gitattributes`（KLARF／fixtures／bundle 標 `-text`）；文件一律 `python -m pytest`。
* **doctor**：Qt 開不了視窗是 △，結論分「命令列可以、Studio 不行」兩句；指令用
  `os.sep`。
* **版本**：bundle 檔頭 `BUILD <sha12> <date>`（= `tools/FILELIST.txt` 的 blob SHA），
  `python -m d4t --version` 印同一個數 —— 公司機沒有 git，這是它答得出「哪一版」的
  唯一方式。
* **第三份出貨 recipe**：`recipes/ebi-die-to-die.json`（ref 借 test 的範圍、
  |test − ref|、median 3、GLV 讀最亮那一點；三個 seed 各 24 顆：24／22／23 中）。
  「用範例資料試一次」入口打開（`SHOW_SAMPLE_DATA = True`，`TEMPLATE_RECIPE` 指它）。
* **`CLAUDE.md` 647 → 319 行**：規則留下，故事逐字封存進
  `docs/history/CLAUDE-2026-09-09.md`。

**做了一半的那一件**：`studio.py` 的接線搬成 controller 模組
（`results_wiring` / `decide_wiring` / `canvas_wiring`）。這台容器沒有 Qt 系統函式庫
（`libEGL.so.1`），UI 測試一條都跑不了，盲搬 7,700 行的 god object 不是一個可以
驗收的動作 —— 留給家用機。同一個理由：這一輪改到的 UI 測試
（`test_ui_template_library.py`、`test_ui_welcome.py` 那條「整條路跑到底」、
`test_ui_glv_combinations.py`、`test_ui_guided_condition.py`）**沒有在這裡跑過**，
請先 `python tools/run_tests.py`。核心批（`--ignore-glob="*test_ui_*"`）與黃金值
三份在這裡全綠。

---

## Results 表：四欄一樣的 min、跟 Tiles 一樣的排序與篩選（2026-09-09 第四輪）

使用者：「results 內 table 會有重名的 column，例如中間會有 4 欄一樣的 min
4 欄一樣的 max，同時希望它跟 Tiles 一樣支援排序跟篩選」。

* **重名的欄**：下層表頭只看 metric（`feature_tree.stat_label`），而
  `glv_stats` 開 each box 之後同一個統計量有 typical / outlier / outlier_box /
  worst 四欄。現在名字裡真的有的兩段接上去（``Min · typical``、
  ``Δ · Median``；`VARIANT_WORDS` 一張表），沒有那兩段的一個字不變（既有測試
  `"Median"` 照過）。兩張卡只差 `output_prefix` 的那種（``N_glv_min`` /
  ``M_glv_min``）另一條路：`header_spans` 把前綴當成區域那樣在上層表頭成段
  （淡灰，區域才有顏色）；`group_row_wanted` 是「要不要上層」的唯一判準。
* **排序**：表頭點一下本來就會排（`setSortingEnabled`），缺的是跟縮圖**同一
  個**排序 —— 現在縮圖的下拉換了表格照那欄排、表頭點了下拉跟著
  （`ResultsWindow._on_gallery_sort` / `_on_table_sort`，`_syncing` 擋回彈；
  `GalleryPanel.sort_changed` 只在使用者手勢時發）。
* **篩選**：`ResultsTableModel.set_filter` 吃跟 Gallery 一字不差的
  `make_filter` spec（`_all_rows` 留著，換條件不重餵；排序連篩掉的一起排）。
  宿主改走 `ResultsWindow.set_filter` 一次餵兩邊（判定段點一類、直方圖點一根
  bar），任一邊按掉 chip 另一邊也清。

尺：`test_ui_results_layers.py` 三條（四個變體四種字、cmp 講比的是哪個
統計量、前綴成段而平鋪仍單層）、`test_ui_results_table.py` 三條、
`test_ui_results_sync.py`（新，兩條：一個條件到兩邊、排序來回）。

---

## 跑與寫拆開、Re-run、Results 單擊帶主畫面、卡片上寫 img/s（2026-09-09 第三輪）

使用者點名四件事，全部做了：

1. **Output 卡也看得到 working numbers。** 清單只有一個來源
   （`studio._dynamic_choices_for`），整批一次的卡（`scale == SCALE_LOT`）接上
   `decision_features()`；逐顆的卡**不接**（判定在它們之後才算，列了就是
   `x = x` 那個 bug）。順手抓到 **`feature_key`（單一個名字）從來沒有過下拉**
   —— `param_form._make_editor` 那一行只認 `expr` / `feature_keys`，於是三張
   Output 卡的 `rank_by` 一直是純文字框，而 `output.py` 的 spec 上寫著「UI 會
   給這一格一支」。lint 那一半：`recipe.let_names_written` 是 let 會寫的名字
   的**唯一的家**（`_decide_unknown` 改用它；`validate` 對整批卡的
   `stale-feature-ref` 現在認得 let）。「插入數字 ▾」搬進 `ui/number_picker.py`
   —— `param_form` 也要用，而它反過來 import `decide_panel` 是一個圈。
2. **跑不寫，寫是另一顆鈕。** 使用者問「還是你覺得不適合」—— 適合：
   `run_batch` 與 `run_batch_steps` 本來就是兩支（batch.py 的 docstring 講的
   正是「寫做成旗標遲早有人忘記關」），Studio 只是把它們綁在一個鈕上。現在
   `run_all` 只跑、`write_outputs` 寫（KLARF `inplace` 的確認搬到寫的時候問；
   被停掉的部分結果拒寫並講出來）。Results 那顆「Run all & write」拆成
   **Re-run** 與 **Write outputs**。Re-run 走 `batch.rerun_decision`：每一行
   let 重算（含跟整批比的，錨拔掉重算）、上一次判定失敗的顆救回來
   （`redecide(revive=True)`）、影像一顆不碰；`batch.measurement_signature`
   決定能不能這樣走 —— 量測那一段改了就整批重跑，**不拿舊數字配新量測卡**。
   底稿是 `_last_run["rows"]`（原封不動那一份），不是畫面上那份。
   ⚠ `tests/test_ui_write_only_on_run_all.py` 的契約整份改寫（那條「試跑不寫，
   只有整批才寫」是使用者 F16 定的，這次也是使用者改的）。
3. **Results 單擊（或方向鍵）一顆 → 主畫面帶過去，不搶焦點**
   （`defect_selected`，雙擊仍是 `defect_activated` 會叫主視窗到前面）。
   「ADC 跟 output 段影像預設不顯示？」—— 是，而且是 F11「沒有線就沒有圖」
   那條規矩的假陽性：Output 卡是整批一次的，逐顆引擎跳過它、沒有 trace，
   `_selected_card_ran` 就把影像清掉。現在 `_preview_whole_route`：選的是
   整批一次的卡、或正在編判定樹（`_tree_focus`）→ 預覽跑到底、連判定，
   路徑才亮得起來。
4. **卡片右上角從總耗時改成每秒幾顆**（`canvas.run_text`：``24 ok · 71 img/s``）。
   加總的 ms 是所有 worker 的 CPU 時間，不是牆上時鐘 —— docstring 講了。

尺：`test_rerun_decision.py`（五條，core）、`test_ui_rerun_and_jump.py`（七條）、
`test_ui_number_picker.py`（三條）、`test_rename_fallout.py` 兩條；改契約的
`test_ui_write_only_on_run_all.py`、`test_ui_button_labels.py`、
`test_ui_results.py`、`test_ui_studio_m5.py`、`test_ui_f99_gestures.py`。
`docs/USING-UNIFORMITY.md` §5 跟著改。

---

## 判定樹上找得到 working numbers；「插入數字 ▾」一張卡一組（2026-09-09）

使用者拿一份 recipe 來問「為何我沒法執行，working numbers 設的 attribute QAA
在後面 tree 上也找不到」。兩件事，一件是 recipe 自己的（樹上有一步 `when` 是
空的 → `bad-rule`；ROI 卡沒模板 → `not-configured`），一件是 Studio 的缺口：

* **樹那一步的「pick a number」與「插入數字 ▾」只列卡片宣告的名字**
  （`labelled_features` 走的是 `_declared_specs`），而引擎（`_eval_decision`
  先算 let 再走樹）與 lint（`_decide_unknown`）早就認得 let 的名字。清單少列
  的那一半正好是使用者自己剛取的。⚠ 這一輪先講錯過一次：「下拉會標成
  from Decision」—— 那是畫布上幽靈線的字，不是下拉的。**答一個 UI 問題之前
  把那一格的來源讀完。**

  補在 `RecipeModel.decision_features(upto_let=None)`：名字、`_missing`、
  `_raw` **不再抄一份規則**，由 `verdict_features.bound_specs` 宣告（family
  `engine`、`base` 是 let 名），這裡只按行序過濾 —— 第 n 行 let 只看得到前
  n−1 行（引擎順序，lint 講的同一句話）；樹的問題與 score 看得到全部。
  卡片的 `labelled_features` **不動**：讓一張卡看到判定段的名字就是 F21-B
  那個 `x = x`。
* **「ADC 下拉選單分類可以再做更好一點嗎」** → `decide_panel.fill_number_picker`
  一支填三個下拉（let 行、score、樹那一步的兩種編法）：一張卡一組、組名是
  卡片的 `label`、組名 disabled 點不到、working numbers 永遠第一組；名字裡
  不再重複「— 誰算的」（`glv_stats` 開 each box 一張卡 55 個名字，那半邊
  重複 55 次）。`itemData` / `findData` 仍是裸名，呼叫端一個字沒改。

順手答掉的三句（寫在對話裡，不進 docs）：算式的空格可有可無（tokenizer
跳過空白）；`_typical` 是逐框值的中位數（含自己）、`_outlier` 是離它最遠那格
的值（跟著 `direction`）、`_outlier_box` 是那一格的序號（0 起算）。

**第二輪（同日）：「你覺得 user 會不會混淆 or 看不懂」—— 會。** 證據不是
猜的：作者自己問了三次才分清 `_outlier` 與 `_worst`，而 `glv_stats.py` 的
`FEATURE_HELP` 註解記著 2026-09-02 有人問過一模一樣的「typical 跟 outliner、
worst、score 是指什麼」。四個提案（補說明／`across_boxes` 那格講兩族／
`_outlier` 一族預設收起來／不改名），使用者：「1 跟 2 先做」。

* **每個下拉項目帶 tooltip**（`decide_panel.number_tips`）：卡片算的走
  `feature_gloss` ＋ `feature_unit`（**跟 Feature 表那一欄同一支**，說明只有
  一個家）；working number 講它的算式、fill、scale，`_missing` / `_raw` 各一
  句。`RecipeModel.bound_feature_specs` 是 `bound_specs` 的投影（同
  `feature_owners` / `feature_regions`）。
* **`across_boxes` 的 help 多一段**：兩族常常指到不同格；`_worst` 一族全部來
  自 judge 挑的那一格，`_typical` / `_outlier` / `_outlier_box` 是每個統計量
  各自的。使用者是在那一格決定開 each box 的，那裡是他唯一會讀說明的時候。
* 第 3 項（收起 `_outlier`）**沒做**，等使用者點頭：出貨 recipe 只用
  `_worst`，但使用者手上那份用了 `_outlier`。

尺：`test_viewmodel.py` 三條（列得出、只看上面幾行、沒判定就空）、
`test_ui_tree_edit.py` 四條（導引式列得出、點了寫進 model、算式框那個也列、
分組長相）、`test_ui_f22_decide_panel.py` 一條（第 n 行只看前 n−1 行）；第二輪再加
`test_glv.py` 一條（那一格的 help 兩族都在）、`test_ui_tree_edit.py` 一條
（每一項都有 tooltip，`_outlier_box` 標成 box）。
