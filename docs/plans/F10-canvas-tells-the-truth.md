# F10 — 畫布要符合現實

**狀態：三項都完成（2026-08-17）。**

---

## 1. 需求從哪裡來

使用者在畫布上實際操作之後回報三件事，並補了一句總綱：

> 然後最重要的是 **DAG 畫布要符合現實**。

三件事：

1. 「加任何 new card 時若還沒連線 → 前後方段不能有 image source 跑出來
   （每張 card 在 new add 但還沒連結起來之前是獨立的，**連結為唯一 source
   來源**）」
2. 「Measure 中有些 card 加進去會自動連接，且**不能多連一**」
3. 「假設 node 要一連多，有時候會**點不到（線拉不出來）**」

補充（同一輪）：

> 在畫布上 add new card 時，card 後方不會預先帶出 Node（要符合現實），還沒有
> image source 連過去怎麼會預設有節點從後面出來。如果是會產生新 Node 的那種
> 卡，例如 Compare to Stream，在還沒有把給定 image source 來源填上時，後方的
> Node 節點 diff 也不該出現（只有在設定內 first stream 跟 second stream 都
> 填上時，diff 才會出現）。另外也要能 custom 命名 —— 設定欄內 write result to
> 命名成 GGG，那 DAG 畫布上新產生的 node（原 diff）名字也要顯示為 GGG。
>
> 整個核心架構是 → **一張卡片剛被 new add 時，前後應該都是空的乾淨的，連上
> source，後面 source 才會出來。**

以及一句解除限制：**「舊有範例 recipe 全部刪光光，不要被她限制。」**

---

## 2. 先確認問題（可執行的探針，不是讀 code 推論）

### 2.1 沒有線也算得出數字

同一份 recipe，一份**零條線**、一份三條線齊全，跑同一批 defect：

```
零條線 : glv_mean 6.7626 / glv_max 33.0 …
三條線 : glv_mean 6.7626 / glv_max 33.0 …
逐項相同 : True        lint : 全綠，一句話都沒說
```

兩層原因疊起來：

- **17 張卡沒有一張的來源參數是空的**（`glv_stats.source="test"`、
  `snr_map.source="diff"`、`subtract.a/b="test"/"ref"`…），所以新卡一加進來就
  宣告了 reads/writes，畫布照著畫出前後埠；
- 埠沒填的線引擎**跳過**（`_explicit_bindings`），資料退回
  `_implicit_bindings` ＝「執行順序上最後一個寫這個名字的人」。

於是「畫布上沒有線」與「引擎裡沒有來源」是兩件不同的事。

### 2.2 「自動連接」的兩條路

加卡本身**不會**產生線（F9-7 已修，實測 `model.edges = 0`、畫布 0 條線）。
看起來像自己接上了的是這兩件：

- 2.1 那件事（沒有線也跑得出數字）；
- **一條「沒有埠」的線會被畫成好幾條**：model 上 1 條 `load→subtract`，畫布
  畫出 **2 條**（`_ports_between` 從「兩端共用哪幾條流」推的）。舊 recipe 載
  進來的線都是這種。

### 2.3 量測卡不能多連一

`source` 是 `image_key`（單一角色），`_drop_conflicting_edges` 對這個型別
不分流名一律把舊線刪掉：

```
拉 load(test) → glv_stats  : 1 條
再拉 sub(diff) → glv_stats : 還是 1 條（第一條被刪），source 變成 diff
對照 denoise（image_keys）  : 2 條並存，streams = test,ref
```

### 2.4 埠點不到 —— 真相是「點在圓心上拉到隔壁那條流」

`out_port_at` 取「由上往下第一個落在半徑內的」，抓取半徑 15px，而三顆埠的
間距只有 14px：

| 卡片 | 畫布上的輸出埠 | 點各埠圓心，實際抓到 |
|---|---|---|
| `subtract` | diff, test, ref | diff ✅ ／ test → **diff** ／ ref → **test** |
| `align` | ref_aligned, test, ref | ref_aligned ✅ ／ test → **ref_aligned** ／ ref → **test** |

最下面那顆埠的可用區間還有一段落在 `shape()` 之外（y 到 59.5，命中區只到
57）—— 那幾個位置是真的完全點不到。三顆埠是 F9-6「同進同出」帶來的，所以
**之後每一張吃兩條流的卡都會中**。

---

## 3. 使用者定調的四個決定

| 題目 | 決定 |
|---|---|
| 「連線是唯一 source 來源」做到哪一層 | **兩層都改**（畫布＝現實） |
| 舊 recipe 怎麼辦 | **空值就是沒接線** —— 清的是「這一張卡的值」，不是卡片的 `default` |
| 怎麼分辨 `image_key` 是輸入還是輸出 | **ParamSpec 加欄位，測試強制** |
| 量測卡多連一的特徵命名 | **開放，自動加流名前綴** |
| 三顆埠太擠 | **只修命中判定**（卡片不長高、pass-through 埠留著） |

---

## 4. 做了什麼

### F10-1：埠點到的是自己那一顆

- `out_port_at` 改成**取最近的**（半徑不縮 —— 縮了只會讓每顆都更難點）。
- `shape()` 照著判定圈畫（逐顆埠一個圈）。⚠ 必須 `WindingFill`：預設的奇偶
  規則會把「圈與本體的交集」抵消成洞，輸入埠的圓心反而不算命中。
- `boundingRect()` 跟著涵蓋 `shape()` —— Qt 先用它粗篩再問 shape，小了那一圈
  是死的。右緣不加寬（埠標籤本來就比抓取圈遠）。

### F10-2：一張卡剛加進來，前後都是空的

- **`ParamSpec.direction`（`image_key` / `image_keys` 必填）**。`subtract` 的
  `a`/`b`（吃進來）與 `out`（吐出去）型別一模一樣，在這之前沒有人分得出來。
  用**宣告**不用推導：推導看的是值，而新卡的值本來就是空的。沒宣告的卡直接
  註冊失敗 → 之後加的每一張卡都躲不掉。
- **`RecipeModel.add_step` 把每一格輸入清成空字串**。清的是這一張卡的值，
  `default` 留著（手寫 recipe 省略那一格時仍要有東西可用）。
- **每一格輸入一顆埠**（`in_specs` / `in_anchors_local` / `in_param_at`），線
  落在哪一格由**使用者放開滑鼠的位置**決定；`edge_added` 因此多一個欄位、
  `edge_lines()` 回四欄。以前是 Studio 用一張寫死的名單
  （`streams → target → source`）猜。
- **沒有來源就什麼都沒有**：不畫輸出埠（Compare 要兩條流都接上，`diff` 才
  出現）、不畫輸入標籤、不宣告具名區域；lint 報 `not-connected`、畫布掛警示、
  引擎在跑之前擋下來。`MultiStreamStep` 空 `streams` 退回 `test` 的 `or`
  一併拿掉。
- 輸出埠印的是 `write result to` 的值 —— 改名就跟著改。
- 順手修掉一個同源的洞：從**同一張卡**往同一顆角色埠拉第二條線時，舊線沒被
  拿掉（一個輸入埠上兩條線，正是 F9-7 擋的那件事）。

### F10-3：量測卡也可以多連一

- 新基底 `_util.MultiSourceStep`：`source` 改成 `image_keys`，接幾條就量幾條。
  卡片只實作 `measure(ctx, img, params) → dict`，迴圈與命名交給基底（跟
  Enhance 卡的 `MultiStreamStep` 同一套辦法）。
- **兩條以上才加流名前綴**（`diff_glv_max` / `test_glv_max`）；只接一條時名字
  **逐字相同** —— 那是「分數表達式不必改寫、黃金值不動」的前提。
  使用者自己填的 `output_prefix` 疊在流名後面（`diff_center_glv_max`）。
- 累加的判準從「這一對節點之間已經有線了嗎」改成「**這一格上已經有線了嗎**」。
  舊判準漏掉「兩條線來自不同上游卡」那種多連一，而那正是量測卡最常見的接法。
- `cd_measure` 用 `REQUIRE_IMAGE = False` 保住原本的寬容（`roi="blob"` 時矩形
  已是像素座標，沒有影像也量得下去）。

### F10-4：剪掉線 = 拿掉來源

使用者回報：「連接卡片節點後，再把線按 X 清掉 → **後方卡片的 Node 不會跟著
清掉**。」量出來比回報的更嚴重：兩條線都剪掉之後 `a='test' b='ref'` 一個字都
沒變、輸出埠還在、lint 說乾淨 —— 那張卡照樣跑得出數字。

三個原因疊起來，其中一個是 F10-2 自己造成的：

1. `_unpoint_stream` 對 `image_key`（角色埠）**直接跳過** —— 以前那一格的值是
   唯一的紀錄，清了就沒有東西講「這張卡本來要做什麼」。F10 之後線才是唯一的
   來源，這個理由消失了。
2. 「最後一條不清空」的保留條款，理由是 `MultiStreamStep` 對空字串會退回
   `test` —— 那個 `or` 在 F10-2 拿掉了，保留條款也跟著沒有理由。
3. 它用 `_param_for_stream()` 找參數，而那個函式在 F10-2 改成回**第一個還空著
   的輸入** —— 剪線時要的正好相反（要那條線自己的那一格）。所以連該清哪一格
   都找錯了。

修法：`edge_removed` 帶上 `dst_in`（跟 `edge_added` 對稱），`remove_edge` 收得下
「整條線」的四個欄位，`_unpoint_stream` 照那一格的型別清（`image_keys` 拿掉那
一條、`image_key` 整格清空）。剪完那張卡回到跟剛加進來一模一樣的狀態。

**接線與剪線必須是彼此的反向操作** —— 只做一半的話，畫布會在「剪」這個方向上
說謊，而症狀跟接線那一半一樣難查。驗收裡有一條對整個 registry 跑的
`test_wiring_and_cutting_are_exact_opposites_for_every_card`。

### F10-5：刪掉卡片 = 連同它的線一起刪

使用者回報：「刪掉 Profile 這整個 Card 後，再 add new card profile，DAG 畫布上
**線還會殘留**。」

病根不是畫布沒重畫（畫布每次都整份重建），是 **`RecipeModel.remove` 只刪節點、
不刪線**。那條線留在 `edges` 裡指著一個不存在的節點 —— 平常看不出來（畫布只畫
兩端都還在的線，`execution_order` 也會過濾掉），直到**新卡拿到同一個自動編號**：
`_new_id` 看到 `roi_cross` 沒人用就再發一次，殘留的線於是接到一張使用者從來
沒有接過的新卡。

它不只是視覺殘留：那條線會被存進 recipe、會進快取簽章、也會被引擎當成明講的
來源。而且它是**假的** —— 新卡的來源參數是空的，畫布與設定當場互相矛盾。

修法兩層：`remove()` 一併拿掉碰到那個節點的每一條線並重算拓撲順序；Studio 在
刪卡之前，把那張卡餵出去的每一條線都走一次 `_unpoint_stream`（跟按 × 剪線
**同一條路**，不另寫一份），所以下游的來源會跟著空出來。整段包成一步復原。

---

## 5. 驗收

`tests/test_ui_f10_canvas_reality.py`（14 條），**每一條都對 registry 裡的
每一張卡自動套用** —— 之後加第 18 張卡的人不必記得回來補。

既有測試有 **27 條踩到舊契約**，逐條更新成「使用者現在真的會做的事」：加完卡
要接線（`conftest.wire_up`）、兩顆輸入要拉兩條線。其中兩條的**前提**被這一輪
推翻（「連線不該亂改 a/b」、「兩條線拉到同一顆輸入會並排」），改寫並在
docstring 裡寫明為什麼。

核心 947 綠、UI 全綠、黃金值一個數字都沒動。

---

## 5.5 哪些卡支援多來源（一格輸入接好幾條線）

判準是**那一格輸入的型別**：`image_keys` 收得下好幾條流，`image_key` 是一個
角色、一次一條。這張表由 `tests/test_ui_f10_canvas_reality.py` 的兩條測試守著
（量測卡一律要是多來源；每張卡的方向宣告必填），所以它不會跟程式碼漂開。

| 卡片 | 組別 | 輸入格 | 多來源 |
|---|---|---|---|
| `load_patch` | Input | （沒有輸入） | — |
| `normalize` / `denoise` / `tone` / `flatten` | Enhance | `streams`（多）＋ `range_from` / `use_within` / `reference`（各單） | ✅ |
| `subtract` | Compare | `a`（單）、`b`（單） | ❌ |
| `align` | Compare | `moving`（單）、`fixed`（單） | ❌ |
| `roi_cross` / `roi_template` / `roi_mask` | Region | `source`（單） | ❌ |
| `glv_stats` / `cd_measure` / `roi_snr` / `focus_quality` | Measure | `source`（多） | ✅ |
| `snr_map` | Measure | `source`（單） | ❌ |

**為什麼有些不行 —— 三個不同的理由，不是漏掉的：**

* **角色埠**（`subtract` 的 a/b、`align` 的 moving/fixed）：那兩格**不是同一件
  事做兩次**，是「被減的」與「拿來減的」。塞兩條進 `a` 沒有意義 —— 要比較三張
  圖就是兩張 Compare 卡。多連一在這裡的正確形式是**兩格各接一條**，那本來就
  做得到（F10-2 起兩格是分得開的兩顆埠）。
* **會產生新流的卡**（`snr_map`、`roi_mask`）：多來源的意思會變成「一條流一張
  輸出圖」，而輸出流的名字只有一格（`out`）—— 要先決定 N 張圖怎麼命名，那是
  另一個題目。
* **Region 卡**（`roi_cross` / `roi_template`）：它們產出的是**具名區域**，
  接兩條的意思是「同一個名字底下有兩組來自不同影像的框」，那會讓下游量測卡
  指到一個語意不明的區域。同樣要先決定命名。

真正「同一件事做好幾次」的兩類 —— Enhance（一張卡處理 N 條流）與 Measure
（一張卡量 N 條流）—— 都已經支援。

---

## 6. 沒做（刻意）

- **`snr_map` 沒有改成多來源。** 它掛在 Measure 這一組是因為只為了餵 blob
  而存在，但它產出的是一張**圖** —— 多連一對它的意思是「一條流一張輸出圖」，
  那要先決定輸出流怎麼命名，是另一個題目。
- **一條「沒有埠」的線仍然會被畫成好幾條**（§2.2 的第二條）。那是舊 recipe
  唯一的顯示方式：埠是空的時候，畫布只能從「兩端共用哪幾條流」推。Studio 現在
  產的每一條線都有埠，所以新做的 recipe 不會走到那條路。要徹底解掉，得決定
  舊 recipe 載進來時要不要**把推出來的來源寫成真的線**（見 `docs/PITFALLS.md`
  的「快取的簽章看不見線」那一列旁邊的討論）。
