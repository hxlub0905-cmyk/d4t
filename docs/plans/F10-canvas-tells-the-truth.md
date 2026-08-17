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

---

## 5. 驗收

`tests/test_ui_f10_canvas_reality.py`（10 條），**每一條都對 registry 裡的
每一張卡自動套用** —— 之後加第 18 張卡的人不必記得回來補。

既有測試有 **27 條踩到舊契約**，逐條更新成「使用者現在真的會做的事」：加完卡
要接線（`conftest.wire_up`）、兩顆輸入要拉兩條線。其中兩條的**前提**被這一輪
推翻（「連線不該亂改 a/b」、「兩條線拉到同一顆輸入會並排」），改寫並在
docstring 裡寫明為什麼。

核心 947 綠、UI 全綠、黃金值一個數字都沒動。

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
