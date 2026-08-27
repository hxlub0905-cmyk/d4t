# F42 — 區域線改存進 `recipe.edges`（方案 B）

**狀態**：進行中（B0／B1／B2／B3 完成 2026-08-27）
**起點**：一個排序 bug —— 把 Region 卡放在量測卡**右邊**（route 上排在後面）
的時候，`execution_order` 讓量測卡先跑，於是它量的是整張圖。畫布上有一條
區域線指著那張 Region 卡，而那條線**不影響執行順序** —— 因為它根本不在
`recipe.edges` 裡。

跑得完、有數字、而且是錯的。第七個。

---

## 1. 這一輪推翻 F12 §3

[`docs/history/plans/F12-region-edges.md`](../history/plans/F12-region-edges.md)
§3 的標題是「區域線**不存進 recipe**，是推導出來的」，而它的代價那一段寫著：

> 代價：區域線不進 `recipe.edges`，所以它不影響 `execution_order` ——
> **但那本來就不需要**：route 相鄰對已經保證了順序。

**那個前提在 F17-① 失效了。** F17 把 `execution_order` 的邊收成「只有使用者
拉的線」，route 的排列從此是**排版不是語意**（`recipe.py` 的模組 docstring 就
寫著這句）。route 相鄰對不再保證任何順序，而區域線是唯一還能表達那個順序的
東西 —— 它偏偏是唯一一種不存進 `edges` 的線。

F12 的其他部分**全部保留**：菱形埠、虛線、型別不合擋下、參數格唯讀、同進同出。
**改的是儲存，不是畫面。**

> ⚠ `F12-region-edges.md` 本身**不改**（它是歷史，記的是那一天的判斷與當時
> 成立的理由）。這一段就是那份文件的續集。

## 2. 使用者的決策（授權依據）

* **採方案 B**：區域依賴存進 `recipe.edges`，跟影像線同一套機制。
  理由是「對齊比較安全」—— 兩套機制本身是每次改動都要多想一次的稅。
* **同名區域直接禁止（P1-a）**：同一條 route 兩張卡產出同名區域 = error。
  **不改引擎的身分模型**（P1-b 明確不做）。
* **廠內沒有存量 recipe**，遷移只需要顧 repo 內的檔案。
* **「the other regions」**：舊檔遷移時自動補線；新 recipe 上勾選只讓埠長出來，
  線由使用者拉。
* **畫法不變。**

## 3. 為什麼 B0 要先做，而且要是 error

B 的線指著**一個特定的節點**。引擎那一頭沒有節點的概念 ——
`Context.set_roi` 是同名覆寫，量測卡拿到的永遠是「上游最後一張寫 `epi` 的卡」。

名字唯一的時候這兩件事是同一件事：**線指的那張卡 ＝ 引擎真的給的那個框**。
撞名的時候不是 —— 畫布可以指著第一張，引擎給第二張的框，而兩邊都跑得完。

所以擋掉撞名，`ctx.set_roi` 一行都不用改。這是 P1-a 買到的東西。

## 4. 階段

| 階段 | 做什麼 | 狀態 |
|---|---|---|
| **B0** | 同名區域 → `duplicate-region` error | ✅ 2026-08-27 |
| **B1** | 引擎認得區域線（`is_region_edge`；排序 bug 即修復） | ✅ 2026-08-27 |
| **B2** | UI 拉線走真的 `add_edge` ＋ 水合 | ✅ 2026-08-27 |
| **B3** | 遷移（`version < N` 為判準） | ✅ 2026-08-27 |
| **B4** | 拆舊路（刪 `region_lines()`）＋ 文件收尾 | ⏳ |

**每一個階段的驗收都含「黃金值逐項相同」，無例外。**
整個方案 B 是純重構：特徵值一項都不許變，任何差異都是 bug，
**沒有「預期差異」**。

---

## B0 — 同名區域是 error（2026-08-27）

`validate()` 多一條 lint：同一條 route 內，兩張**啟用中**的卡的
`resolve_regions_out` 出現同一個名字 → `duplicate-region`（error）。

實作在 `recipe._region_collisions`，形狀刻意抄 `_feature_collisions`
（同一段判斷抄兩份的話總有一份會長歪 —— 這個 repo 記過三次）。

### 三個邊界，每一個都有測試

1. **「原樣送出」不算。** 只看 `resolve_regions_out`（引擎的宣告）。畫布上
   量測卡右邊也有一個 `epi` 埠（「同進同出」，F12 §7-①），但它送出去的是
   別人的框。兩者混為一談的話，每一份「一張 Region 卡 ＋ 兩張量測卡」的正常
   recipe 都會冒出紅字 —— 而在每一份 recipe 上都出現的 error 會被學會忽略。
   `viewmodel.region_outputs`（畫布的埠）因此刻意跟它分家。
2. **`_center` / `_others` 自動在範圍內。** 它們本來就在
   `resolve_regions_out` 的回傳裡（`_util.region_family` 是唯一那一份），
   所以兩張都吐 `epi` 的卡撞的是**三個**名字。
3. **一條 route 一張表。** 兩條 route 各有一張叫 `epi` 的 Region 卡是常態
   （`ebi_patch` 與 `rsem` 各走各的），它們永遠不會在同一次執行裡碰面。

### 為什麼是 error，而 `feature-collision` 只是 warning

差別不是嚴重程度，是**有沒有第二條路拿得到被蓋掉的那一份**：
特徵被蓋掉時引擎會把前一份救成 `<節點名>_<特徵>`，所以那句話是
「你可能不是故意的」；`ctx.set_roi` 沒有救援，前一張卡畫的框就是不見了。

### 驗收

* 新測試 `tests/test_region_names_are_unique.py`（10 條）——
  四條正面斷言驗過「把 lint 拿掉會紅」。
* 兩份出貨 recipe、兩份 fixture recipe 都沒有撞名（明著測一次，
  訊息是「哪兩張卡撞了哪個名字」而不是「有一條 error」）。
* 核心測試 2397 綠、62 支 UI 測試逐檔綠、黃金值三份逐項相同。


---

## B1 — 引擎認得區域線（2026-08-27）

### `is_region_edge` —— 全 repo 唯一的判準

住在 `core/pipeline/recipe.py`，判準只有一件事：**`dst_in` 那一格的型別是不是
`region_key` / `region_keys`**（`step.REGION_TYPES` 是那張表唯一的家）。

方案 B 之後畫布、排版、引擎、健檢四個地方都要分得出兩種線。這種「同一個判斷抄
四份」的形狀這個 repo 記過三次 —— 改動其中一份不會讓任何測試變紅，而長歪的那
一份會讓畫布跟引擎說出不同的話。

**簽章跟工作單寫的不一樣，理由要記下來。** 工作單建議
`is_region_edge(edge, registry)`，但一條 `Edge` 身上只有節點 **id**，而型別住在
**下游那張卡**上 —— 節點表非進來不可。收 `nodes`（而不是整份 `Recipe`）是為了
B2／B4：`RecipeModel.nodes` 與 `Recipe.nodes` 都是 `Dict[str, RecipeNode]`，
所以畫布不必為了呼叫它先組一份 `Recipe`。

**不看 `src_out`。** `src_out` 是「哪一個區域」，這裡問的是「這是不是區域線」
—— 兩件事分開，一條還沒填來源的區域線才講得出它是什麼（那條線由
`region-edge-no-port` 講話）。

**`dst_in` 沒填就一律不是區域線。** 那不是漏判，是舊語意：埠空著的邊「只表達
先後順序」。判成區域線的話，每一條舊格式的兩欄邊都會變成區域線。
⚠ 那個 early return 是**規則寫出來**、不是最佳化 —— 底下的迴圈也找不到叫 `""`
的參數，所以拿掉它一條測試都不會紅。留著是因為讓契約只是「剛好沒有參數叫空
字串」是一種靠巧合的正確。

### 引擎：`else: continue` 是對的，補一條測試釘住

`engine._explicit_bindings` 收的是 `(節點, 流名) → (來源節點, 來源埠)`，而區域
走的是 `ctx.rois` 那一套。放區域線進去的話，`epi` 會變成一條**指向不存在的影像
流**的線，而那張表是量測卡拿影像的唯一依據。程式一行沒改（本來就跳過），
改的是那段註解：現在它明說這是區域線唯一會走到的分支，並指向判準與測試。

**驗過會紅**：把 `region_key` / `region_keys` 加進那個 `if` 之後，
`test_the_image_binding_ignores_a_region_edge` 與
`test_only_the_image_edges_survive_into_the_binding_table` 兩條同時變紅。

### `execution_order` 一行都不用改

它只看 `src`/`dst`（F9-1 的註解就寫著「不看埠」），所以區域線進了 `edges` 自然
生效。**這是方案 B 幾乎不用動引擎的原因**，也是 B1 唯一要證明的事。

回歸測試三條，成對地講同一件事：

* `..._runs_first_even_when_it_sits_to_the_right` —— route 排成
  load → glv → **roi**（Region 卡在量測卡右邊），加了區域線就排得對。
* `..._without_the_region_edge_the_order_follows_the_layout` —— **bug 的形狀**：
  沒有那條線時順序由卡片被拖到哪裡決定。留著是為了讓上一條的差異看得見：
  兩份 recipe 只差一條線。
* `..._does_not_disturb_an_already_correct_order` —— Region 卡本來就在左邊時，
  加線不改變任何東西（純重構的前提）。

### 端對端：那條線是 200 與 150 的差別

假卡片（左半 200、右半 100 的一張圖）跑一次 `run_defect`：

| | `glv_mean` |
|---|---|
| 有區域線 | **200**（量左半） |
| 沒有區域線 | **150**（量測卡先跑，`ctx.rois` 是空的 → 退回整張圖） |

兩邊都 `ok=True`、都有數字。**這就是那個 bug 的完整形狀**，而它現在是一條測試。

> 為什麼用假卡片而不是真的 `roi_reference`：真的那張要在影像上**找**得到條紋
> 才吐得出區域，於是測試會同時測到「找得準不準」—— 而這裡要問的是順序。
> （`tests/test_recipe.py` 的 dummy 卡片同一個理由。）

### `region-edge-no-port`（warning）

`src_out` 空著的區域線**排得出順序**（`execution_order` 只看 src/dst），所以它
跑得完 —— 它只是沒有講出量的是哪一塊。畫布上看得到一條接好的線，而那張卡實際
上退回量整張圖。

**warning 不是 error**：「那一格是空的」由 `not-connected` 與卡片自己的
`configuration_issues` 講，這一條講的是**線本身沒講完**。
埠空著的**影像**線不在範圍內 —— 那是 F9-1 之前每一份檔案的常態。

### 驗收

* 新測試 `tests/test_region_edges_engine.py`（16 條）。三個突變各驗過會紅：
  ① 影像綁定收區域線、② 判準只認 `region_key`（漏掉 `region_keys`）。
* `test_every_region_parameter_in_the_card_library_is_recognised` 掃**整個卡片
  庫**：`region_input_specs()` 說是區域的那幾格，`is_region_edge` 一格都不准漏
  —— 新加一張卡時兩支判斷不會長歪。
* 核心測試 2414 綠、62 支 UI 測試逐檔綠、黃金值三份逐項相同。

### 留給 B2 的一句話（現在還不用做）

快取簽章（`engine.image_segment_signature`）收的是「`dst` 落在影像段的線」，
所以進了 `edges` 的區域線**自動**進簽章 —— 只要 `dst` 在影像段裡
（`roi_mask` 就是，它吃區域吐影像）。B2 把區域參數改成水合、
`to_json_dict` 濾掉它之後，記憶體裡的 `params` 仍然帶著區域名，
所以簽章兩邊都看得到；而「來源是誰」由 `sig_edges` 補上。
B0 之後名字唯一，兩者不可能指到不同的卡。


---

## B2 — 拉線走真的 `add_edge`，參數是水合出來的（2026-08-27）

**F12 §3 在這裡真的被推翻。** 區域線進了 `recipe.edges`，`roi="epi"` 那一格
從「唯一的儲存」變成「線的呈現」。

### 一支水合，五個入口

`RecipeModel._hydrate_regions(emptied=())` —— 全程式只有這一支。
入口：載檔（`from_recipe`）、拉線（`add_edge`）、剪線（`remove_edge`）、
undo／redo、刪卡（`remove`）。

核心那一支是 `recipe.hydrate_regions()`，換算住在
`recipe.region_edge_values()`（**唯一一份**）—— 序列化、還原、UI 三邊都問它。

### 那個不對稱：只填不清，除了剛被剪掉線的那幾格

沒有線的那一格**不動**。看起來像是留了一個後門，其實那個狀態有兩種來歷，
兩種都必須留著：

1. **B3 之前的舊檔案** —— 區域參數還沒有線，那一格是它唯一的儲存。
   在載入時清掉等於每一份既有 recipe 打開就安靜地少量一塊。
2. **打錯字的名字**（`roi="epi_"`，沒有人定義它）—— 清掉的話
   `unknown-region` 那條 lint 就永遠問不到了，而 `glv_stats` 的空 `roi` 是
   完全合法的「量整張圖」。**看不到就被靜靜刪掉是最糟的一種「幫忙」。**

> ⚠ 這一點跟工作單 B3-② 寫的不一樣。那裡寫「參數指到沒人產出的名字 → 不補線，
> 讓埠空著……錯誤從 `unknown-region` 變 `not-connected`」。實作選擇是**把名字
> 留著**，於是錯誤仍然是 `unknown-region` —— 因為工作單同一句話還寫著
> 「**訊息不得變差**」，而 `glv_stats` 根本長不出 `not-connected`
> （空的 `roi` 合法），那條路的終點是「安靜地量整張圖」。

**但剪掉線就是拿掉來源**（F10）：`remove_edge` / `remove` 會把剛剪掉線的那幾格
`(節點, 參數)` 交給水合，那幾格由剩下的線說了算（沒有剩下的就空掉）。
剪的時候我們知道是哪一格 —— 那正是「只填不清」缺的那個資訊。

⚠ `emptied` **只作用在區域參數上**。第一版沒有這道過濾，於是剪一條
`subtract.b` 的影像線會讓那一格空掉**兩次**，其中一次繞過了
`_unpoint_stream`（它還要判斷剪掉的是一串裡的哪一條）——
`test_ui_canvas_truth` 當場抓到「畫布上有線、那一格是空的」。

### 常開的斷言

`RecipeModel.CHECK_REGION_INVARIANT`（`tests/conftest.py` 在**每一條測試**上
打開）：每一次 `_changed()` 都問一次「**有線的**那幾格是不是正好等於線說的」。

為什麼要常開而不是幾條測試：方案 B 的安全性建立在「用哪個區域只有一個家」上，
而破壞它的方式是**加一條新路徑**（一個忘了水合的新入口），不是改壞既有的那
五條 —— 既有測試不會走那條還不存在的路徑。它在這一輪就抓到兩個真的問題
（刪卡時 `_unpoint_stream` 先清了參數、`emptied` 沒過濾區域參數）。

### 序列化：一個家

* `to_json_dict` **不寫**線管著的那一格（值跟線說的一模一樣才丟 ——
  不一樣的時候丟掉就是安靜地改了使用者的 recipe）。
* `from_json_dict` 在**所有遷移之後**呼叫 `hydrate_regions` 補回來。
* `to_json_dict → from_json_dict` 仍然是 identity（鐵則 9）——
  兩邊算的是同一件事。

### 拿掉了一道守門（工作單沒點名，但它擋的正是這一輪要修的動作）

F12 §4 的第四條：「來源排在下游的區域**也擋**」。那句話在 F12 當時是真的
—— 區域線不進 `edges`，順序只能靠卡片的左右位置。

方案 B 把線存進去之後，**那條線自己就是順序**。擋下來等於不讓使用者做那個
唯一能修好順序的動作，而「Region 卡排在量測卡右邊 → 量測卡先跑 → 安靜地量整
張圖」正是這一輪的起點。所以拿掉，`test_a_region_defined_later_...` 翻面。
真正會壞的那一種（成環）由 `add_edge` 擋 —— 它擋的是事實，不是排版。

### 接受的代價：排版會動

`add_edge` 會重排 `node_order`，所以拉一條區域線之後畫布上的卡片會移位 ——
以前不會，因為那條線根本不在 `edges` 裡。**那是對的**：它一直都是一條真的
依賴，只是以前畫布看得到、引擎看不到。釘成
`test_a_region_line_now_moves_the_layout`，免得下一個人以為那是 bug。

### 「the other regions」：答案是「本來就對」

`reference="the other regions"` **沒有自己的那一格**，所以沒有埠 ——
`epi_others` 是從 `roi` 算出來的（`glv_stats.resolve_regions_in` 的
「derive，不存第二份」），而它跟 `epi` 出自**同一張 Region 卡**
（`region_family` 一次吐三個名字）。接進 `roi` 的那條線已經指著它了。

所以 B3 不必為它補第二條線 —— 而且補不出來：一條線的 `dst_in` 是**參數名**，
而那個依賴沒有參數。`test_the_other_regions_needs_no_port_of_its_own` 記著。

`another region` 那一格（`reference_region`）本來就靠 `show_when` 長出來，
線由使用者拉，**不自動接**（`_autofill_regions` 在 F12 §6-① 就刪掉了）。

### 驗收

* 新測試 `tests/test_ui_region_hydration.py`（18 條），涵蓋五個入口 ＋
  序列化 ＋ 核心那一支。三個突變各驗過會紅：
  ① undo／redo 不重新水合、② `to_json_dict` 照寫所有參數、
  ③ `remove_edge` 不把那一格交出去。
* `region_lines()` **一個字都沒改**（B4 才拆），畫布仍然讀它 ——
  所以它現在是一份**對照的預言**：線推導出來的與參數推導出來的必須一致。
* 核心 2415 綠、62 支 UI 測試逐檔綠、黃金值三份逐項相同。


---

## B3 — 遷移（2026-08-27）

`_migrate_region_params_into_edges`，判準是 **`version < RECIPE_VERSION`**
（`RECIPE_VERSION = 2`），跑完寫成 2。

**不是**「有參數但沒有線」—— 那是鐵則 9 明文禁止的「靠新東西不在判斷」，
而這個 repo 為它付過一次 `workers=1` 與 `workers=2` 算出不同分數的錢。

### ⚠ `Recipe.version` 的預設值跟著改成 2，而那是必要的

留在 1 的話，一份**記憶體裡組出來**的 recipe（Studio 的 `to_recipe()`）走
`to_json_dict → from_json_dict`（`run_batch` 送進 worker 的路）時會**再跑一次
遷移**，而遷移把版本號改成 2 —— 那一對就不再是 identity 了（鐵則 9）。
`RecipeModel.version` 一起改。

這一條是實際踩到的：改之前 `test_json_defaults_filled` 立刻變紅。

### 四種情形

| | 情形 | 處置 |
|---|---|---|
| ① | 上游找得到 | 補線 |
| ② | 指到沒有人產出的名字 | **不補線，那個字留著** |
| ③ | 產出它的卡排在**下游** | **補線** —— 順序因此被排對 |
| ④ | 補上去會**成環** | 不補，由 `region-has-no-line` 講 |

**③ 是一個刻意的行為改變**，而且是這一輪存在的理由：遷移之前那兩張卡在引擎
眼裡毫無關係，量測卡先跑、`ctx.rois` 是空的，於是安靜地量整張圖。遷移之後線
把順序排對，一份原本算錯的 recipe 開始算對的數字。寫進遷移的 docstring，
釘成 `test_a_region_card_to_the_right_gets_wired_and_the_order_is_fixed`。

**② 跟工作單寫的不一樣**（工作單：讓埠空著、錯誤變 `not-connected`）。
實作選了把名字留著，因為同一句話還寫著「**訊息不得變差**」—— 而 `glv_stats`
根本長不出 `not-connected`：空的 `roi` 是完全合法的「量整張圖」，
清掉之後那條路的終點是**安靜地算錯**。所以錯誤仍然是 `unknown-region`，
而訊息重寫過（B3-⑥）：現在講的是「拉一條線」，不是「把 roi 那一格清掉」——
那一格從 F12 起就是唯讀的了。

### ④ 查下來是一道「不可能發生、但必須擋」的檢查

工作單點名的路徑是「Profile 吃 roi_mask 的 mask 流、roi_mask 又吃 Profile 的
區域」。查下來**這個形狀今天就是壞的**，而且不可能不壞：

> 要讓那條區域線成環，就得先有一條 `consumer → producer` 的線；而那條線會把
> consumer 排在 producer 前面 —— 於是 consumer 跑的時候那個區域還不存在。
> 所以「今天跑得動、補了線就成環」的 recipe **不存在**。

那這道檢查還有什麼用：**讓一份壞的 recipe 維持壞得一樣**。沒有它的話
`execution_order` 會 raise，於是一條講得出話的 lint error 變成「這個檔案打不
開」—— 遷移沒有資格把病情升級。測試因此比對的是**遷移前後的 issue 清單逐項
相同**，不是「有沒有那條線」。

### 新 lint：`region-has-no-line`（warning）

「有名字、上游也真的定義了它、但畫布上沒有那條線。」B2 之後這個狀態只剩兩種
來歷，而 `unknown-region` 只講得出另一種。它的真正客群是**手寫 recipe 的
CLI 使用者** —— 工作單那句「CLI 手寫 recipe 從此要寫 edges」的安全網。

warning 不是 error：它跑起來是對的（`ctx.rois` 是全域的，順序由 route 的排列
決定）。但它不可以安靜 —— 畫布上兩張卡看起來互不相干，而其中一張真的在量另一
張畫的框。

⚠ ② 與 ④ 是**兩種不同的病，不准同時報**（一句話講兩次，使用者會以為有兩個
問題）—— `test_a_name_nobody_produces_gets_only_the_error_not_both`。

### 出貨的 recipe

兩份都重存成 v2。diff 只有一行（`"version": 1` → `2`）——
`ebi-to-api-characterization` 沒有區域參數；`patch-dsnr-by-class` 的 `roi="gc"`
沒有補線，因為 templateGC 沒有模板就產不出區域名（那本來就是
`ALLOWED_ERRORS` 裡的那條 `unknown-region`）。**證明過**：重存前後每一張卡的
每一個參數、每一條線、每一條 route 都逐項相同。

`recipes/README.md` 沒有版本欄位、`0822test/` 的產生器不產 recipe，兩者都不必改。

### 驗收

* 新測試 `tests/test_region_edges_migration.py`（12 條）。三個突變各驗過會紅：
  ① 拿掉環的檢查、② 判準換成「沒有線就補」、③ 把沒有人產出的名字清掉。
* 核心 2428 綠、62 支 UI 測試逐檔綠、黃金值三份逐項相同。
