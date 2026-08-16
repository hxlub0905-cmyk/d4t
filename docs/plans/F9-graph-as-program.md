# F9 — 圖就是程式（線變成真的資料通道）

**狀態：Phase 1–3d 完成（2026-08-15）。線是真的資料通道、判定與輸入都是畫布
上的卡（`Recipe.score` 與 `Recipe.routes` 兩個固定欄位都已退場）、畫布畫的是
編譯出來的圖、「不就地改寫像素」從慣例變成擋得住的鎖。
Phase 4 完成：剪線是真的（§5h）、接不出騙人的線（§5i）。**

---

## 1. 需求從哪裡來

使用者對這個工具的定位講清楚了：

> 「我想要的是我把 Function 寫好 → 工程師只需用節點（n8n like）方式，將所想要
> 做的事自己**創造出來**。你說的什麼 ADC、ML、寫回 KLARF、output 什麼什麼東東
> 都是後面的**增加卡片**、增加節點的功能。但我現在是想要確立**大方向**。」

也就是說：**產品是那台編輯器，卡片是外掛。** 六個方向題的回答：

| | 決定 |
|---|---|
| 線要不要變成真的資料通道 | **要** |
| 誰寫卡片 | 使用者自己寫 → **不需要外掛機制**，卡片進 repo 就好 |
| 邊界 | 主要是影像 + KLARF；之後要能依 KLARF 欄位分流（例 `CLASSNUMBER=1` 走 A、`=2` 走 B）|
| 判定（ADC）要不要變卡片 | 要（卡片後做，**位置現在就空出來**）|
| 跨顆的卡 | 同上 |
| 輸入要不要變卡片 | **要**，依資料型別分 |

---

## 2. 為什麼現在做不到

**畫布上的線不搬資料。** 證據是 repo 裡唯一那份範例 recipe：

```
$ python -c "import json; print(json.load(open('examples/recipes/cross_regions.json'))['edges'])"
[]
```

九張卡、**零條線**，而它跑得完全正常。

因為真正的接線不在線上，在每張卡的參數字串裡：`normalize` 讀 `streams="test"`、
`glv_stats` 讀 `source="diff"`。資料走的是一個**全域的 `ctx.images` 字典**，
用名字取。`edges` 只影響執行順序。

三個具體後果：

1. 載入一份 recipe，畫布可能一條線都沒有，但它是對的
2. **把線刪掉，那張卡照樣讀同一條流** —— 刪線什麼都沒發生
3. 兩張卡都寫 `test`，後面那張蓋掉前面那張，畫布上看不出來

另外三件事是寫死的，而它們正好擋住上面表格裡的每一個「要」：

- **判定不是卡片**：`CATEGORY_ADC` 的卡片數是 **0**。`score`/`threshold`/`bins`
  是 `Recipe` 的固定欄位，不在圖上。
- **輸入不是卡片**：引擎先把 defect 塞進 `ctx.meta`，Load 卡去撿；而 route 是
  以 dataset kind（`ebi_patch`/`rsem`）當 key 的。
- **分流沒有地方表達**：`routes` 分的是「資料型別」，不是「資料的值」。

---

## 3. 決定：線上流的是「一顆 defect 的整包狀態」

兩個候選：

**A. 線上流一條影像流**（`test` 一條線、`ref` 一條線）
這是 F7-18～F7-21 已經投資的方向。看得出哪張圖去哪裡，但：量測卡吐十個數字，
判定卡就要接十條線；而且「`CLASSNUMBER=1` 走 A」分的是**整顆 defect**，
不是某一條影像流 —— 在 A 底下沒有自然的表達方式。

**B. 線上流一顆 defect 的整包狀態**（= 現在的 `Context` 從全域變成在線上流動）

選 **B**。理由：分流天生成立、特徵不必接線、分岔天生是各自一份。

### 3.1 這條不變量要改寫

F7-18 立的是「**一張卡動到的每一條流，畫面上都要有一條線**」。那條在 B 底下
不成立，也不需要成立 —— 一條線帶的是整包，卡片動裡面哪一條是它自己的參數。
新的說法是：

> **畫布上看得到的是「這顆 defect 的狀態往哪裡流、在哪裡分岔、依什麼條件」。
> 一張卡動到裡面哪一條影像流，是那張卡自己的事（節點副標已經印 `吃什麼 → 吐什麼`）。**
>
> 可測的那一半：**刪掉一條線，下游就真的收不到東西。** 這正是今天壞掉的部分。

不要因為「F7-18 說過一張卡一條流」就把 A 拉回來 —— F7-18 保護的是「畫布不能
說謊」，B 用另一個粒度達成同一件事，而且它做得到 A 做不到的分流。

---

## 4. 契約

### 4.1 Packet —— 線上流的東西

```python
@dataclass(frozen=True)
class Packet:
    images:   Dict[str, np.ndarray]
    regions:  Dict[str, List[tuple]]     # 名字 -> 一組框（0–1 比例座標，不變）
    features: Dict[str, float]
    meta:     Dict[str, Any]             # defect_id、KLARF 欄位、診斷…
```

**不可變。** 卡片回傳新的 Packet，不改舊的（`with_image()` 只換 dict，
像素陣列本身共用）。這一條同時買到兩件事：

- **分岔安全**：兩條分支各拿一個 Packet，一邊改不到另一邊
- **分岔不吃記憶體**：沒有人就地改陣列，所以不必深拷貝像素

> ⚠ 對卡片作者的規矩：**永遠產生新陣列，不要就地寫**（`arr += 1` 不行，
> `arr = arr + 1` 可以）。現在的卡片本來就是這樣寫的（`ctx.set_image(k, op(img))`），
> 所以這不是新負擔，但它從慣例升級成規則。

### 4.2 Node —— 卡片

```python
class Node:
    inputs:   Tuple[str, ...] = ("in",)
    outputs:  Tuple[str, ...] = ("out",)
    required: Tuple[str, ...] = ("in",)   # 少了就不執行（也不報錯）

    def run(self, ins: Dict[str, Packet], params) -> Dict[str, Packet]:
        """回 {輸出埠名: Packet} —— 只放它這次要吐的埠。"""
```

「回一個 dict，只放要吐的埠」這一個設計同時涵蓋四種卡：

| 卡的種類 | 回什麼 |
|---|---|
| 一般處理 | `{"out": pk}` |
| **條件分流** | `{"match": pk}` **或** `{"else": pk}`（只吐一個） |
| 分裂 | 兩個都吐 |
| 判定（尾節點） | `outputs = ()`，吐判定結果 |

### 4.3 執行語意

- **拓撲排序**求值；每個節點從進來的線上收 Packet
- **`required` 少一個就整段安靜跳過** —— 分支沒被選到時，下游不是報錯，是不執行
- **一張圖可以有好幾個判定尾節點**（每條分支自己的判定標準）
  - 0 個判定觸發 → 這顆 defect **沒有結論**，要如實記錄（不是給 0 分）
  - 2 個以上觸發 → 編輯期就該 lint 出來

### 4.4 這會取代掉什麼

| 現在 | 之後 |
|---|---|
| `routes: {ebi_patch: [...]}` | Input 節點（依資料型別分）+ 分流卡 |
| `score: {expr, threshold, bins}` | ADC 節點（可以有好幾個） |
| `params.source` / `streams` 決定接線 | `edges` 決定接線；參數只決定「動裡面哪一條流」 |
| `edges` 只影響順序 | `edges` 就是資料流 |

---

## 5. 原型驗證了什麼

寫了一份約 250 行的 spike（附錄），跑起來證明六件事：

```
== 分流：只有被選到的那一邊會跑 ==
  CLASSNUMBER=1 -> 跑過 ['input', 'route', 'enh_a', 'sub_a', 'meas_a', 'adc_a']
     判定：{'adc_a': {'score': 60.0, 'bin': 1, 'by': 'A'}}
  CLASSNUMBER=2 -> 跑過 ['input', 'route', 'enh_b', 'sub_b', 'meas_b', 'adc_b']
     判定：{'adc_b': {'score': 233.0, 'bin': 1, 'by': 'B'}}

== 分岔：兩條分支互不影響，而且不複製像素 ==
  跑過 ['input', 'left', 'right', 'join', 'adc']
  right 量到的是**原圖**的峰值：179.0
```

1. 一條線把整包狀態帶到下一張卡 ✓
2. 分岔各自一份、原始輸入沒被就地改掉（斷言鎖住）✓
3. 一張卡多個輸出埠、依條件只吐一個 ✓
4. 沒被選到的分支，下游整段安靜不執行 ✓
5. 合流是一張明講「怎麼合」的卡 ✓
6. 一張圖有多個判定尾節點 ✓

**Q3 的 `CLASSNUMBER` 分流在這個模型下不需要任何特殊機制** —— 它就是一張
「多輸出埠 + 依條件擇一」的普通卡。

---

## 5b. Phase 2 實際做了什麼（2026-08-15）

新檔案 `adept/core/pipeline/graph.py`：`Packet` / `Wire` / `Graph` /
`compile_recipe()` / `run_graph()`。`engine._run_nodes()` 變成一層薄殼，
真正的執行在圖執行器上。**17 張卡一行都沒改。**

### 5b.1 契約跟 §4.1 有一處不一樣（重要）

§4.1 寫的是「`Packet` 是 frozen dataclass，卡片回傳新的」。**實作沒有這樣做。**

`Packet` 現在就是包著一個 `Context`，不可變性靠兩件事保證：

1. 卡片本來就**產生新陣列、不就地改寫像素**（現有 17 張卡都是這樣寫的）
2. 執行器在**分岔的時候**複製（copy-on-fork），線性鏈上直接把物件交出去

換來的是「卡片不用改」—— 而那正是讓 Phase 2 的風險降到可以一次做完的原因。
代價是**不可變性從型別保證降級成慣例**：卡片作者若寫 `arr += 1`（就地改寫），
分岔的兩條分支會互相汙染，而且不會報錯。這一條要在 Phase 3 卡片搬家時
用型別重新鎖上（或加一條測試掃描就地改寫）。**✅ 已鎖上，見 §5f** ——
`Context.set_image` 一律把陣列標成唯讀。

### 5b.2 踩到的坑：第一個取用者不能拿原件

`take()` 一開始寫成「第一個下游拿原件、第二個以後拿複本」（想省一次複製）。
錯的：**既有卡片是就地改 `ctx` 的**，第一個下游一改，留在 outbox 裡的那份
就髒了，第二個分支複製到的是「已經被上一條分支改過」的狀態 —— 正好是分岔
要防的那件事。現在是「扇出 > 1 就每一個都複製」。
`tests/test_graph.py::test_a_fork_gives_each_branch_its_own_copy` 鎖住它。

### 5b.3 驗收

**逐顆對答案**（計畫書要求的那條）：同一份 `cross_regions.json`、同一批 60 顆
合成 defect，舊引擎（commit `d0650d8`，全域 Context）與新引擎（圖執行器）
比對 `score` / `bin` / **每一個特徵值**：

```
顆數: 舊 60 / 新 60
逐項完全相同的顆數: 60 / 60
```

**效能沒有退化**（各跑 5 次取中位數）：

```
old: median 8.40 ms/顆
new: median 7.89 ms/顆
```

新的略快，因為編譯結果現在有快取（以前每顆都重算一次 `execution_order`）。
快取掛在 `Recipe` 物件上並用**結構指紋**驗證 —— 只認物件不認內容的快取會在
Studio 改完 recipe 之後安靜地跑舊的圖。

**全套測試**：77 個檔案全綠（既有的 `test_engine` / `test_batch_cache` /
`test_e2e_*` 一個字都沒改，它們全綠就是「線性 pipeline 行為沒變」的證明）。

新性質由 `tests/test_graph.py` 釘住：編出來的線、**剪掉線下游就收不到**、
分岔隔離（像素共用但 warnings 不互相汙染）、條件分流只跑選到的那一邊、
停用節點要把線接過去。

---

## 5c. Phase 3a：判定變成卡片（2026-08-15）

新卡 `adept/core/steps/adc.py`（key `adc`，label **Decide**）—— 這是專案裡
**第一張 `CATEGORY_ADC` 的卡**（在此之前那一段的卡片數是 0）。

### 5c.1 為什麼這件事值得先做

判定以前是 `Recipe.score` 這個固定欄位：一份 recipe 只有一條式子、一個門檻，
而且不在畫布上。那擋住的正是使用者要的東西 —— `CLASSNUMBER=1` 走 A、`=2` 走 B
的時候，**兩條分支的門檻本來就該不一樣**（A 是已知的真缺陷要抓乾淨、B 是雜訊
要濾掉），綁成同一個數字等於兩邊都調不好。

現在一張圖可以放好幾張判定卡，每條分支自己一張。

### 5c.2 三種情況，三種下場（`engine._judge`）

| 情況 | 下場 |
|---|---|
| 圖上**沒有**判定卡 | 走舊的 `recipe.score`（既有的每一份 recipe 都走這條） |
| 剛好**一張**跑到 | 就用它 |
| **一張都沒跑到** | **沒有結論**：score/bin 留 `None`，並在 warnings 講出來 |
| **兩張以上**跑到 | recipe 接錯了 → 失敗並指名是哪幾張，不偷偷挑一個 |

第三條是 §6.4 那一題的答案。給 0 分是最糟的處理 —— 0 會排序、會進報表、
看起來像「很乾淨」，跟 `cd_x_nm` 恆為 0 是同一類的坑。

### 5c.3 順手補上：線存得下「從哪個埠出去」

寫測試的時候發現得 monkeypatch 才能塞一張分支的圖 —— 那是個訊號：**檔案格式
存不下埠**，所以分支 recipe 根本存不起來。`edges` 因此多一種寫法：

```json
["r", "match", "m", "in"]      // 四段式：從 r 的 match 埠 → m 的 in 埠
["subtract", "snr"]            // 兩段式：兩端的預設埠（既有檔案都是這種）
```

四段式**贏過**route 順序推出來的那條線（使用者指名了就是他說了算）。
三個元素的線會在載入時被擋下來並講清楚 —— 不猜使用者的意思。

### 5c.4 `adc` 暫時不出現在卡片庫

`ui/scope.py` 的 `HIDDEN_STEPS` 加了 `"adc"`。理由：Studio 的分數頁
（`Recipe.score`）還在，兩個地方都能設門檻而使用者不知道哪個算數。
**Phase 3b 拿掉 `score` 欄位的同一輪要把這個字串刪掉** —— 不然會變成
「做好了但沒有人打開」。CLI 與既有 recipe 不受影響。

---

## 5d. Phase 3b：流由線決定（2026-08-15）

使用者追加兩條原則：

> 1. 原來卡片內可以選擇 image source，我想改成都只能從「節點拉」避免誤會
> 2. image source 一個節點可以多拉 —— 例如我可以在 load image 後的 ref 拉
>    Compare 中的 ROI，也能在同樣節點 ref 拉 Normalize

### 5d.1 埠名就是影像流名（而且不用逐張卡改）

兩條規則，從卡片**自己已經有的宣告**推出來：

* **輸入埠 = 每一個「選影像流」的參數**（`image_key` / `image_keys`，`out` 除外）。
  埠名就是角色名：`source` / `a` / `b` / `moving` / `fixed` / `reference` /
  `range_from` / `use_within` / `streams`。
* **輸出埠 = 這張卡寫出來的流名**（`out` 參數，或 `resolve_writes()`）。
  所以 Load 的輸出埠就叫 `test` 與 `ref`，從 `ref` 拉出去的每一條線都代表
  「這條線帶的是 ref」。

16 張有流參數的卡片**一行都沒改**。

執行時，線把來源埠的名字綁進下游卡的那個參數 —— **參數不再是使用者選的，
是線決定的**。同一個埠接好幾條線 = 這張卡同時做那幾條流（`image_keys`）。

### 5d.2 線有兩種，這是這一輪最重要的設計

第一版把「照名字接線」全做成搬狀態的線。結果：`ref` 被 Normalize、一張
Region 卡、一張量測卡讀到 → **變成三岔**，每張卡各拿一份複本，量出來的數字
散在三包裡，而分數式子只看得到其中一份。既有 recipe 當場全部壞掉
（`available variables: n_channels`）。

所以線分成兩種：

| kind | 意思 | 分岔要不要複製 |
|---|---|---|
| `packet` | **狀態的去向** —— 這一顆 defect 的整包沿著它走 | 要 |
| `stream` | **這張卡動哪一條流** —— 只把埠名綁進參數，不搬狀態 | 不算扇出 |

一條流被三張卡讀 = 三條 `stream` 線（畫布上看得見「這三張都在動 ref」），
但**不是三條分岔**：它們的特徵仍然累積到同一包，最後才判定得出來。

這也正好對上使用者的原則 2：同一顆 `ref` 埠拉三條線出去是**正常**的，
不是三份複本。

### 5d.3 踩到的坑：埠算了兩次，兩邊答案不一樣

編譯時算一次埠、執行時又算一次。`load_patch` 的輸出流**跟資料型別有關**
（`rsem` 是 single+test、`ebi_patch` 是 test+ref），而執行期看不到 `kind` ——
於是編譯期接的是 `load.single`、執行期吐的是 `load.test`。

症狀最糟：對不上 → 下游**整條鏈安靜地不執行**。跑得完、沒有錯誤訊息、
只有 load 一張卡跑過，然後在算分數那一刻才說「找不到變數」。

修法是把埠**編譯時算一次存進 `Graph.ports`**，執行期只讀不算。
一份資料只有一個來源，就沒有機會不一致。

### 5d.4 驗收

同一份 `cross_regions.json`、同一批 60 顆：與 **F9 動工前**（commit `d0650d8`）
逐項比對 `score` / `bin` / 每一個特徵值 —— **60 / 60 完全相同**。
效能 7.66 → 7.82 ms/顆。77 個檔案全綠。

`tests/test_graph.py` 新增三條鎖住這一輪：只改線不改參數就換一條流、
同一顆輸出埠餵好幾張卡且特徵仍然累積、**stream 線不算分岔**。

### 5d.5 Phase 3c 第一批：埠不該憑空多出來 + 下拉退場（2026-08-15）

**埠要吃 `show_when`（這是 bug，不是取捨）。** `normalize` 的 `reference` 只有
方法選 `match` 才用得到，參數表上本來就會把它藏起來 —— 但埠的推導沒看
`show_when`，於是畫布上長出一顆 `reference` 埠而且真的接了一條線，**那條線
完全不影響結果**。跟 §7 那條「help 裡寫『這個方法用不到』是一句道歉不是設計」
是同一個病，只是搬到了畫布上。修完 `cross_regions` 的 stream 線 13 → 11 條。

**埠分兩級**（`graph.optional_ports`）：非接不可的永遠顯示；選用的
（`advanced`，或預設值是空字串的 `range_from` / `use_within`）**接了才長出來**。
判準沿用卡片自己已經有的旗標，不發明新的。理由是量出來的：`normalize` 4 個
輸入埠、`subtract` 2 個、`align` 2 個，全部常駐會跟資料流搶畫面（F7-8 的教訓）。

**參數表不再顯示 `image_key` / `image_keys` 那幾列。** 這是原則 1 對使用者
真正成真的那一步：以前同一件事有兩個地方可以改（畫布的線、表單的下拉），
不一致時沒有人看得出來而且**線贏**。現在要換一條流就把線改接到別顆埠。
值仍然存在 recipe JSON 裡 —— 它是那條線的落腳處，不是給人填的欄位。

### 5d.6 Phase 3c 第二批：畫布畫的是編譯出來的圖（2026-08-15）

**畫布以前畫的是 `RecipeModel.edges`（只有使用者親手拉過的線）。** 所以一份
recipe 可能一條線都沒有而它跑得完全正確 —— 那正是 §2 開頭那個「`edges` 是
`[]`」的另一面：畫面上看不到的接線，其實一直都在。

現在 `studio._compiled_wiring()` 問引擎要那張圖（`compile_recipe`），連同每個
節點的埠一起送進畫布。編不出來（recipe 還沒接完）就退回舊的那幾條 ——
畫布永遠有東西畫，不會因為 lint 沒過就整片空白。

三件配套，**每一件都是看著截圖決定的**（§7：用實際尺寸看過再收工）：

| | 決定 | 為什麼 |
|---|---|---|
| 輸入埠 | 依角色分（`a` / `b` / `source`…），**圓點永遠畫、名字只有選到才標** | 第一版常駐標籤，截圖看到的是「ge_from_」「e_within」被截斷又跟上游的輸出標籤疊在一起 —— 兩張卡之間只有 `COL_GAP`，左右各一組標籤本來就塞不下 |
| stream 線 | **只在選到那張卡時才畫** | 九張卡會編出 11 條 stream + 8 條主幹 = 19 條。全部常駐就是毛球，而使用者 2026-08-14 才因為「會混淆」退掉過一種常駐的線 |
| 兩種線 | 不同**色相**（`canvas_edge_stream`）、細一點、**不畫箭頭** | §7「虛線只是實線淡一點」。stream 線沒有方向可言（東西不從它走），給它箭頭等於說謊 |

**一條使用者的決定被反過來了，這是刻意的。** 2026-08-14 退掉的 route 金色
虛線是**裝飾**（只說「這兩張卡有先後」）；現在畫的那條鏈是**程式本身**
（資料真的沿著它流）。`tests/test_ui_f7_10_route_edges.py` 與
`test_ui_f7_18_streams_as_nodes.py` 兩支測試的前提因此改寫，各自寫了為什麼
——⚠ 不要因為「使用者退過虛線」就把它再退一次。

**順手抓到一個我自己造的 bug**：新編譯器只認四段式的顯式 `edges`，把使用者
手拉的兩段式線**整個丟掉**了 —— 畫面上他接了 `load → norm`、實際跑的卻是
`load → norm_ref → norm`。正好是 F9 要修的那件事，而我自己犯了。

## 5e. Phase 3d 第一批：分數不再是 recipe 上的欄位（2026-08-15）

判定卡在 Phase 3a 就做好了，但一直**收在 `scope.HIDDEN_STEPS` 裡沒有出場** ——
因為 `Recipe.score` 那個固定欄位還在，兩個都露出來的話畫面上有兩個地方能設
門檻而使用者不知道哪個算數。這一批就是把那個欄位拿掉，同一輪把卡片放出來。

### 5e.1 拿掉一個欄位，要走完它的每一條下游

`score` 不只是 `Recipe` 上的一個 dataclass 欄位。沿著它往下游走一遍，
它同時是：

| 在哪 | 是什麼 | 現在變成 |
|---|---|---|
| `recipe.py` | `ScoreSpec` 欄位 + JSON 的 `"score"` 區塊 | 沒有了；舊檔案載入時遷移成 route 尾端一張 `adc` 卡 |
| `recipe.validate()` | `score-expr` / `bad-bins` / 全域的 `unknown-feature` | 判定卡自己的 `not-configured`；`unknown-feature` 改成**逐張卡**、拿它上游累積的特徵比 |
| `engine._eval_score()` | 舊判定路徑 | 刪掉；`_judge` 只看判定卡 |
| `store.rescore()` | 讀 recipe JSON 的 `score` 區塊 | 讀 `adc` 節點的參數；**舊 run 的 `score` 區塊仍讀得懂**（資料庫裡是歷史快照，沒辦法遷移）|
| `viewmodel.RecipeModel` | `expr` / `threshold` / `bins` 三個欄位 | `decide_nodes()` / `decision_threshold()` / `set_decision_threshold()` —— 值住在卡片參數裡 |
| `studio.py` | 一整頁「Score / Bin」+ 卡片庫裡一個假卡片 `__score__` | 都沒有了；判定卡走**跟其他卡完全一樣**的那張參數表 |
| `canvas.py` | `score_clicked` / `set_score_summary()` | 都沒有了；判定在畫布上是一顆節點 |
| `welcome.py` | 範本庫顯示 `score.expr` | 讀 `adc` 節點；舊檔案的 `score` 區塊仍讀得懂 |

**這張表本身就是這一輪的教訓**（跟 §7 的「拿掉一張卡，週邊會留下承諾」同一
條）：死掉的程式碼沒人會發現，死掉的**承諾**使用者天天看得到。

### 5e.2 新增一個參數型別：`expr`

判定卡的分數式子如果只是一格 `str`，就等於要使用者憑記憶打出上游卡自己取的
變數名（`snr_max` / `glv_q99` / `cd_x_px`…）。最常見的下場不是「打不出來」而是
**打錯一個字**：lint 只出一句 warning、整批照樣跑得完，而每一顆都沒有分數。

所以 `ParamSpec` 多一個型別 `expr`（值仍是 str，recipe JSON 沒有變），UI 給它
一行輸入框 + 一顆「Insert feature ▾」，列的是**這張卡上游真的量得出來的**那幾個
名字。這跟 `image_keys` 給勾選框、`min/max` 給滑桿是同一個道理 ——
**能列出來的東西就不要讓人用打的。**

順帶：`RecipeModel.available_features()` 多一個 `before_node=`。判定卡自己吐的
`score` 不該出現在它自己的變數清單裡（那會讓人以為 `score = score * 2` 是合法的
寫法）。

### 5e.3 兩個順手抓到的坑

**`upto_node` 指到一張停用的卡時停不下來。** Studio 點某張卡看中間輸出走的是
`run_defect(upto_node=…)`，而它以前只靠 `run_graph` 去認節點 id ——
編譯過的圖裡沒有停用節點，認不到就一路跑到底。以前看不出來，因為判定還不是
卡片，route 尾巴後面沒有東西；判定變成卡片之後它會照跑，然後回一個
「算式裡的變數找不到」這種指不到原因的錯。改成用**索引**切段
（`order.index(upto_node) + 1`），停用與否都對。

**registry 是 import 的副作用填起來的。** 卡片註冊發生在 `import
adept.core.steps` 的時候，而 `test_graph.py` / `test_engine.py` 只 import
`adept.core.pipeline` —— 於是第一個用到 `adc` 的測試拿到一個還沒有它的
registry，錯誤訊息是 `unknown step 'adc'`，指不到真正的原因。兩個檔案都補上
明確的 `import adept.core.steps  # noqa: F401`。

### 5e.4 驗收

* 同一批 60 顆合成 defect，`examples/recipes/cross_regions.json`
  **改寫前（`7132b89` 的舊格式）與改寫後逐格相同** —— CSV 全欄位 0 個差異。
* `python tools/run_tests.py`：**77 個檔案全綠，137 秒**。
* 舊格式仍載得進來：`tests/fixtures/recipes/*.json` 三份**刻意留成舊格式**，
  它們現在是遷移的迴歸測試（`test_ui_f7_18` 直接斷言遷移後的 route 尾巴多了
  一張 `decide`）。

### 5e.5 Phase 3d 還沒做的

* **Input 變卡片**（依資料型別分張），`routes` 欄位退場
* ~~**卡片用型別或掃描測試鎖住「不就地改寫像素陣列」**~~ —— ✅ 已解（§5f）
* `ui/scope.py` 綁 dataset kind 的機制要重想（見 §6.3）
* 「沒有結論」的 UI 那一半：Gallery 與輸出精靈要分得出「沒有結論」與「分數很低」

---

## 5f. Phase 3d 第二批：把「不就地改寫」從慣例變成鎖（2026-08-15）

§5b.1 記了一條降級：`Packet` 不是 frozen，不可變性靠「卡片本來就不就地改寫」
這個**慣例**撐著，並要求在 Phase 3 用型別或掃描重新鎖上。這一批把它鎖回去。

### 5f.1 鎖在哪：`Context.set_image` 一律 `freeze()`

`Packet.fork()` 的複製**不含像素**（`images=dict(src.images)` 只複製那本
字典）。兩條分支指著同一塊記憶體 —— 一張卡若就地改寫（`arr += 1`、
`arr[mask] = 0`、`cv2.xxx(..., dst=arr)`），另一條分支拿到的是被改過的圖，
**而且不會有任何錯誤訊息**。

numpy 的 `writeable` 旗標就是那個鎖，而且它比原始碼掃描準：`arr += 1` 掃得
出來，`cv2.blur(src, dst=arr)` 掃不出來 —— 而兩者的後果一模一樣。

**選擇在 `set_image` 凍、而不是在 `fork()` 凍。** 只在分岔時凍的話，這條規則
只在有分支的圖上成立，而卡片是在沒有分支的時候寫出來的 —— 等到有人接了一條
分支才爆，那個錯誤離犯規的那一行已經很遠了。在入口凍，違規當場就現形。

這**不擋任何合法的寫法**：卡片本來就是「算一張新的、`set_image` 回去」，
要就地改也只要先 `.copy()`（新的那份是可寫的，直到它自己被 set 進來）。

### 5f.2 驗收：18 張卡一張都沒改

全套測試**一次就綠** —— 也就是說整個卡片庫本來就守著這條規則，這一輪只是把
它變成擋得住的東西。逐顆分數與 §5e 完全相同（60 顆 CSV 0 個差異），
每顆 7.91 ms（設一個旗標的成本量不出來）。

`tests/test_f9_no_inplace_writes.py` 掃**整個 registry**（`parametrize` 吃
`REGISTRY`，加新卡片不必來改清單），並且**先證明它自己抓得到** ——
一張故意犯規的假卡片必須被擋下來，不然那個掃描只是一句永遠成立的話。

### 5f.3 順手補完 §6.4 的 UI 那一半

「沒有結論」在引擎裡是一個真的狀態（Phase 3a），但畫面上看不出來：

* **Results 的那一行** 只說 `N ok`。沒有結論的那幾顆算在 ok 裡（沒有錯，
  它們確實沒有失敗），於是整批看起來「全部跑完了」，而旁邊那個分數範圍其實
  只涵蓋其中一部分。現在多一句 `· N with no verdict`。
* **Gallery 的說明文字** 寫的是 `bin —`，然後什麼都不說。一個破折號讀起來像
  「還沒算好」，而真相是「這條分支上沒有判定卡」—— 兩件事要修的地方完全不同。
  現在直接寫 `no verdict`。

（輸出那一路本來就是誠實的：`klarf_out` 會數出「幾顆沒有 bin / 沒有分數」
並寫進 `plan.notes`，就地模式直接跳過它們。）

---

## 5g. Phase 3d 第三批：輸入變卡片、`routes` 退場（2026-08-15）

「這條 pipeline 吃什麼資料」以前寫在 `Recipe.routes` 的**鍵**上 —— 一個使用者
從來沒看過的地方，而它同時決定三件事：跑哪幾張卡、Input 卡的埠長什麼樣、
Studio 能不能開這份檔案。現在它是**畫布上第一張卡的身分**。

### 5g.1 一種資料型別一張 Input 卡

`load_patch` 以前一張卡吃所有型別，靠 `channels="auto"` 在**執行期**看資料
才決定寫出哪幾條流。拆成 `load_patch`（ebi_patch）與 `load_single`
（rsem / folder）之後，兩個代價一起消失：

* **`Step.resolve_writes_for_kind(params, kind)` 整個拿掉了。** 那是為了「首卡
  吐什麼要看 dataset kind」而存在的特例，它把 kind 一路傳進埠的計算裡 ——
  於是埠算了兩次，而編譯期知道 kind、執行期不知道（§5d.3 那個坑：線接到
  `load.single`、執行期卻吐在 `load.test` 上，整條下游安靜地不跑）。
  現在 `stream_ports(step_cls, params)` 不再有 `kind` / `first` 兩個參數。
* **使用者看得出這份 recipe 是給什麼資料用的** —— 圖上第一張卡的名字就是答案。

新的類別屬性 `Step.accepts_kinds`：空的 = 普通的卡；非空 = 一條 pipeline 的
起點。這是 Input 卡跟其他卡**唯一**的差別。

### 5g.2 `routes` → `order` + 分段

`Recipe` 現在是 `nodes` + `order`（一份清單）+ `edges`。`order` 從每一張
Input 卡切成一段（`pipeline_segments`），`kind` 對到哪一段就跑哪一段
（`route_for_kind`）。

**為什麼 `order` 是一份顯式的清單，而不是靠 `nodes` 這個 dict 的順序**：
JSON 物件的鍵順序不是規格保證的東西，把執行順序賭在它上面，換一個 parser
就換一種行為。

`sorted(recipe.routes)` 這個問句換成 `accepted_kinds(recipe)` —— 同一個問題，
答案改由畫布上看得到的那幾張卡回答。

### 5g.3 舊檔案：共用的節點會被拆開

`_migrate_routes` 做兩件事：把每條 route 的第一張卡換成對的 Input 變體，
以及**把多條 route 共用的節點複製成一段一份**（`<原id>__<kind>`，該段內的
edges 一起改名）。

`dual_route_basic` 的 11 個節點有 8 個同時屬於兩條 route —— 改一個就改了兩邊。
那從來不是使用者要的（跟判定卡「每條分支一張」是同一個理由，見 §5e.1）。
拆開之後行為完全不變，變的是它們現在改得動而不互相干擾。

### 5g.4 `ui/scope.py` 不再需要一份手寫名單（§6.3 已解）

「Studio 只吃 ebi_patch」以前是靠 `SUPPORTED_KINDS` 過濾 route **加上**一份
手寫的 `HIDDEN_STEPS`，於是「打開 RSEM」要記得同時改兩個地方。現在
`visible_steps()` 直接問卡片自己的 `accepts_kinds` —— 一張只吃 RSEM 的
Input 卡在只支援 patch 的 build 裡不會出現在卡片庫，而 `SUPPORTED_KINDS`
加一個字串就會回來（`test_f9_input_cards.py` 兩邊都鎖）。

### 5g.5 順帶：`execution_order` 現在要 registry

它得問卡片「你是不是 Input、你吃什麼」，所以多一個 `registry` 參數
（預設全域 registry）。引擎、圖編譯、`validate` 都把自己手上那份傳下去 ——
用假卡片的測試檔如果忘了傳，症狀會是「這份 recipe 沒有 Input 卡」。

### 5g.6 驗收

* 同一批 60 顆，`examples/recipes/cross_regions.json`（已改寫成新格式）
  與前一批 **CSV 逐格相同**（0 個差異）。
* 雙輸入 e2e（`test_e2e_dual_route`）全綠：同一份舊格式 fixture 遷移之後，
  patch 與 RSEM 兩批照樣跑得完、分數照樣算得出來。
* `python tools/run_tests.py`：**80 個檔案全綠、143 秒**。

### 5g.7 Phase 3d 到此結束，剩下的是 Phase 4

`routes` / `score` 都退場了，判定與輸入都是卡片，像素不准就地改寫。
剩下的都是**畫布變成真的編輯器**（Phase 4）：埠型別擋不合法連線、
刪線＝真的斷開、分岔／合流畫得出來。

其中「刪線＝真的斷開」現在才真的做得到 —— 以前執行順序有一半藏在 `routes`
的相鄰對裡，畫布上那個「×」剪掉的只是 `model.edges`，剪一條由順序推出來的線
**什麼都不會發生**。順序現在就是線本身。

---

## 5h. Phase 4a：剪線＝真的斷開（2026-08-15）

畫布上那顆「×」以前是**假的**。主幹是從 `order` 的相鄰對推導出來的，而那顆 ×
只從 `model.edges` 裡刪東西 —— 推導出來的線根本不在那份清單裡。按下去：
狀態列說「Disconnected」、圖一點都沒變、線還畫在原地。

那是這個工具最糟的一種行為（**說做了卻沒做**），而且它是 §5g.7 就講明的
「Phase 4 的第一件事」。

### 5h.1 規矩：一條顯式的線就關掉推導

`graph._compile_recipe` 多一個 `backbone_is_explicit`（這份 recipe 的 `edges`
裡有沒有兩段式的線）。有的話推導整個關掉 —— 主幹以 `edges` 為準。
四段式的 `edges`（條件分流的 `match` / `else`）不算數：它講的是「從哪個出口
走」，跟「主幹在哪」是兩件事。

### 5h.2 第一次動線就把整條主幹寫下來

只寫新拉的那一條會出事：推導一關，其餘八張卡在使用者拉了一條線的瞬間全部
變成沒人接的孤兒。所以 `RecipeModel.add_edge` 與 `remove_edge` 都先呼叫
`materialise_backbone()`（把 `node_order` 的相鄰對寫成真的 edges），再做自己
那一步。

這反過來一條 F7-10 的舊決定（「存檔只寫使用者親手拉的線」）。當時的理由是
「卡片順序一改，推導出來的線就該重算」—— 成立，但它換來的是**那些線不是資料
所以剪不掉**。現在的交換是：線就是順序，排版與執行順序都從 edges 拓撲排序，
不再有第二套真理。理由寫在 `tests/test_ui_f7_10_route_edges.py` 那支測試的
docstring 裡（前提反轉必須留下說明，見計畫書 §5d.6 的先例）。

### 5h.3 斷掉的卡要在跑之前就看得見

新 lint code `no-upstream`：主幹寫下來之後，route 上除了 Input 卡以外每一張
都得有人接。沒有的話它會收到一個空的 Context，然後卡片自己報「找不到影像流
test」—— 一句指不到真正原因（沒人接它）的錯誤訊息。

### 5h.4 順帶一條型別規則：接不進 Input 卡

Input 卡是一條 pipeline 的**起點**。以前一條指向它的線拉得起來、存得下去，
然後什麼都不會發生。現在當場拒絕，而且訊息講的是「它是 Input 卡，pipeline
從它開始」——比原本那句「這樣會繞回去」更指得出該怎麼辦。

### 5h.5 驗收

60 顆 CSV 與前一批**逐格相同**（沒動線的 recipe 行為完全不變）；
`tests/test_ui_f9_cut_is_real.py`（6 條）；83 個檔案全綠、115 秒。

---

## 5i. Phase 4b：接不出騙人的線（2026-08-15）

跟 §5h 一樣，動手前先實測「哪些不合法的線現在接得起來」。三個發現：

### 5i.1 Region 卡的輸出被當成影像流

`roi_cross` 不寫任何影像流，所以它的輸出埠是那個佔位的 `out`。從那顆埠拉一條
線到量測卡上，以前會把量測卡的 `source` 設成 `"out"` —— 一條**沒有人產出**的
流。狀態列還說「now works on out」，而那份 recipe 跑起來每一顆都失敗。

線本身是有意義的（「先定位、再量」是真的先後關係），錯的只有「順手把那張卡
改成做 out」。所以只擋改參數那一半（`_real_stream`），並且講清楚
「cross 不產生影像流，所以 glv_here 看的還是原來那條」。

### 5i.2 合流會安靜地丟掉一整條分支

最小重現（`l→a`、`l→b`、`a→end`、`b→end`）：

```
合流之後的特徵: ['feat_b', 'feat_e']     ← feat_a 整個不見
ok: True   error: None                   ← 沒有任何錯誤訊息
```

執行器對同一個入口的多條線是「取最後一條」（`feeding[-1]`）。那不是可以在
畫面上看出來的規則，而後果是另一條分支量出來的東西**整批消失**。

兩層處理：

* **lint `merge-into-one-port`**（error）—— 手寫的 recipe 也擋得到。
  真正的「合流卡」要能表達的話，它會宣告兩個**不同名**的輸入埠，所以這一條
  擋不到它。
* **畫布上根本接不出來**：拉第二條進同一個入口是「我改變主意了」，當場把舊的
  那條換掉（沿用 F7-18 那條先例），而且**講出換掉了誰** —— 不然畫面上會有
  一條線無聲無息地消失。

⚠ 換掉的動作要等 `add_edge` **成功之後**才做。會成環（或接進 Input 卡）的那條
線沒有落地，它不該留下任何痕跡 —— 尤其不是「原本那條被剪掉了」。這一條在
實作時踩到過，測試 `test_nothing_can_be_wired_into_an_input_card` 鎖住它。

### 5i.3 分岔本來就成立

`sub.diff` 同時餵兩張量測卡：編譯出來 fanout = 2、畫布兩條線都畫、
copy-on-fork 在 §5b 就做好了、lint 零錯誤。**這一項不用做。**
（合流不成立，是因為還沒有一張「合流卡」宣告得出兩個輸入埠 —— 那是新卡片的
工作，不是引擎的。）

### 5i.4 驗收

60 顆 CSV 逐格相同；`tests/test_ui_f9_cut_is_real.py` 增到 7 條；83 檔全綠。

---

## 6. 還沒解決的（Phase 3c 要面對）

### 6.1 快取切點在 DAG 上不成立

現在的定義是「執行順序上**最後一張** `category==image` 的卡的下一格」。
在有分支的圖上這句話沒有意義。

提議改成**逐節點記憶化**：key = (defect, 這個節點的上游簽章)。好處是它比現在
更通用（分支各自命中）、而且「改算法段參數不重算影像段」自動成立。代價是要決定
存哪些節點的 Packet（全部存會爆記憶體）—— 這一題留到 Phase 2 量過再定。

### 6.2 舊 recipe 遷移 —— ✅ 已解（`score` 見 §5e、`routes` 見 §5g）

`routes` → `order` + Input 卡（`recipe._migrate_routes`）；
`score` → ADC 節點（`recipe._migrate_score_block`）。機械式，但
**驗收必須是「同一份 recipe、同一批資料，遷移前後逐顆分數相同」**（沿用 F7-18
的作法，不要靠讀程式碼驗證）。

### 6.3 `ui/scope.py` 綁 dataset kind —— ✅ 已解（見 §5g.4）

猜對了：現在就是「卡片庫裡只列這幾張 Input 卡」，而且是問卡片自己的
`accepts_kinds`，不必再維護一份手寫名單。

### 6.4 判定為 0 個時要說什麼 —— ✅ 已解（見 §5c.2 與 §5f.3）

score/bin 留 `None` 並在 warnings 講出來；Results 的那一行多一句
「N with no verdict」、Gallery 的說明文字寫 `no verdict` 而不是一個破折號。

---

## 7. Phase 切法

| Phase | 做什麼 | 風險 |
|---|---|---|
| **1** ✅ | 定契約 + 原型證明 | 無 |
| **2** ✅ | 引擎換心：依 wires 求值、copy-on-fork、編譯快取。**卡片沒動。** | 已通過逐顆驗收 |
| **3a** ✅ | ADC 變卡片（引擎支援多判定 / 沒有判定）；線存得下埠 | 低（舊路徑保留） |
| **3b** ✅ | 流由線決定（埠名 = 流名；線分 packet / stream 兩種）。**16 張卡沒動。** | 已通過逐顆驗收 |
| **3c** ✅ | UI 那一半：流的下拉退場、埠依角色分、畫布畫編譯出來的圖、兩種線不同色相 | 已看過截圖 |
| **3d** ✅ | `score` 退場 + `scope.py` 解除隱藏 `adc`（§5e）；「不就地改寫」變成鎖（§5f）；Input 變卡片 + `routes` 退場（§5g） | 已通過逐顆驗收 |
| **4** ✅ | 刪線＝真的斷開（§5h）；接不出騙人的線（§5i：Region 卡的 `out` 不是影像流、合流當場換掉舊線 + lint、接不進 Input 卡）。分岔本來就成立；合流要等一張「合流卡」宣告得出兩個輸入埠 | 已實測驗收 |
| **5+** | 開始長功能卡：`CLASSNUMBER` 分流、跨顆統計、ML、更多量測 | 低（純加法） |

Phase 2 的驗收是整件事的安全網：**遷移前後逐顆分數相同** —— 已通過（見 §5b.3）。

---

## 8. 附錄：原型原始碼

> 這份 spike 刻意**不放進套件**（它是一條平行的路，留在 `adept/` 底下會腐爛）。
> 保留在這裡是為了 Phase 2 動工時可以拿它對答案。存成 `.py` 直接跑即可。

```python
"""Phase 1 原型：驗證「線上流的是一顆 defect 的整包狀態」這個模型成立。"""
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Tuple
import numpy as np


@dataclass(frozen=True)
class Packet:
    images: Dict[str, np.ndarray] = field(default_factory=dict)
    regions: Dict[str, List[tuple]] = field(default_factory=dict)
    features: Dict[str, float] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def with_image(self, name, arr):
        d = dict(self.images); d[name] = arr
        return replace(self, images=d)

    def with_features(self, **kw):
        d = dict(self.features); d.update({k: float(v) for k, v in kw.items()})
        return replace(self, features=d)


class Node:
    inputs: Tuple[str, ...] = ("in",)
    outputs: Tuple[str, ...] = ("out",)
    required: Tuple[str, ...] = ("in",)

    def run(self, ins, p):
        raise NotImplementedError


class Input(Node):
    inputs, required = (), ()

    def run(self, ins, p):
        item = p["item"]
        return {"out": Packet(images=dict(item["images"]),
                              meta={"defect_id": item["id"],
                                    "klarf": item["klarf"]})}


class Route(Node):
    """依 KLARF 欄位分流：兩個輸出埠，只吐其中一個。"""
    outputs = ("match", "else")

    def run(self, ins, p):
        pk = ins["in"]
        hit = pk.meta["klarf"].get(p["field"]) == p["equals"]
        return {("match" if hit else "else"): pk}


class Enhance(Node):
    def run(self, ins, p):
        pk = ins["in"]
        for name in p["streams"]:
            pk = pk.with_image(name, pk.images[name] * float(p["gain"]))
        return {"out": pk}


class Subtract(Node):
    def run(self, ins, p):
        pk = ins["in"]
        out = pk.images[p["a"]].astype(np.float32) - pk.images[p["b"]]
        return {"out": pk.with_image(p["out"], out)}


class Measure(Node):
    def run(self, ins, p):
        pk = ins["in"]
        return {"out": pk.with_features(
            **{p["name"]: float(np.max(np.abs(pk.images[p["source"]])))})}


class Merge(Node):
    """合流：明講怎麼合。"""
    inputs = required = ("a", "b")

    def run(self, ins, p):
        a, b = ins["a"], ins["b"]
        return {"out": replace(a, features={**a.features, **b.features},
                               images={**a.images, **b.images})}


class Adc(Node):
    outputs = ()

    def run(self, ins, p):
        pk = ins["in"]
        score = float(eval(p["expr"], {"__builtins__": {}}, dict(pk.features)))
        return {"__verdict__": replace(pk, meta={**pk.meta, "verdict": {
            "score": score, "bin": 1 if score >= p["threshold"] else 0,
            "by": p["label"]}})}


@dataclass
class Wire:
    src: str
    src_port: str
    dst: str
    dst_port: str


def run_graph(nodes, wires, item):
    indeg = {n: 0 for n in nodes}
    succ = {n: [] for n in nodes}
    for w in wires:
        succ[w.src].append(w.dst); indeg[w.dst] += 1
    order, ready = [], sorted([n for n, d in indeg.items() if d == 0])
    while ready:
        n = ready.pop(0); order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort()
    assert len(order) == len(nodes), "圖上有循環"

    outbox, verdicts, ran = {}, {}, []
    for nid in order:
        node, params = nodes[nid]
        ins = {w.dst_port: outbox[(w.src, w.src_port)] for w in wires
               if w.dst == nid and (w.src, w.src_port) in outbox}
        if any(r not in ins for r in node.required):
            continue                     # 上游沒吐 -> 這一段整個不跑
        ran.append(nid)
        for port, pk in node.run(ins, dict(params, item=item)).items():
            if port == "__verdict__":
                verdicts[nid] = pk.meta["verdict"]
            else:
                outbox[(nid, port)] = pk
    return {"verdicts": verdicts, "ran": ran}
```
