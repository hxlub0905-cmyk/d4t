# F42 — 區域線改存進 `recipe.edges`（方案 B）

**狀態**：進行中（B0／B1 完成 2026-08-27）
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
| **B2** | UI 拉線走真的 `add_edge` ＋ 水合 | ⏳ |
| **B3** | 遷移（`version < N` 為判準） | ⏳ |
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
