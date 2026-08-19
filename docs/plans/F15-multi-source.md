# F15 — 一份 recipe 掛好幾個 image source

**狀態**：設計中（2026-08-19 起）。**還沒動任何程式碼。**
**前置**：F14-1（資料的入口已經搬到讀它的那張卡上）。

---

## 1. 使用者定調的五件事

我列了五個「多 source 會撞到」的問題，他逐條回答：

| 問題 | 他的答案 |
|---|---|
| 兩個 source 要不要是同一批 | **兩筆就是不同的 set，沒關係** |
| 批次要跑幾顆 | **指定一個 main route**（主 source 決定迴圈長度） |
| 怎麼配對 | **用 KLARF 位置 + image 形狀配對，找最像的** |
| KLARF 寫回誰 | **寫回 main route 的** |
| 要不要新機制 | 「我覺得勢必是要添加新功能（**類似 connector 之類的東西**）」 |

## 2. 主張：**讀檔留在 ingest、配對規則放在卡片上**

看起來跟 GLAS 那條路的決定相反（`GLAS-INTERFACE.md` §3：「配對規則要在 ingest
層而不是卡片裡」），但判準不是「配對」這個字，是**這個決定有沒有參數**：

| | GLAS label map | 這一輪的第二個 source |
|---|---|---|
| 怎麼配 | `image_id == DEFECTID`，**精確、無參數** | 座標最近 + 形狀相容，**有容差、有取捨** |
| 配錯了會怎樣 | 不會配錯（同源的 id） | 會配到隔壁那顆，而**畫面上看起來完全正常** |
| 要不要調 | 不用 | 要，而且要看得到配得好不好 |

這個 app 裡**每一個要調的決定都在卡片上**，而且只有卡片吐得出 feature ——
「配得多近」必須變成一個數字（`match_dist_nm`），使用者才有辦法在分數表達式
裡把配不好的那幾顆擋掉。一個藏在對話框裡的容差做不到這件事。

**但檔案還是 ingest 讀**（鐵則 9 一個字都沒鬆）：卡片自己讀檔的話，換一份
第二 source 而快取簽章看不見 → 回舊影像。那個坑 F9 踩過兩次。

## 3. 資料模型

```
Dataset(main)                       Dataset(second)          ← 兩個各自載進來的 set
  kind = "rsem"                       kind = "ebi_patch"
  items = [DefectItem, …]             items = [DefectItem, …]
     ↑ 迴圈跑這一份、route 由它的 kind 決定、KLARF 寫回它
```

* `Dataset` 多一個 `source_id`（`"main"` / 使用者取的名字）。
* Studio 持有 `{source_id: Dataset}`；**`main` 那一份就是現在的 `self.dataset`**
  —— 既有的每一條路（預覽、defect 導覽、Export）一行都不用改。
* `run_batch(recipe, dataset, others={sid: Dataset})`；worker 拿得到全部
  （`DefectItem` 裝的是路徑不是像素，picklable）。

## 4. 卡片：一個 connector + 一張 Load

```
  [Load images]  main            ← Open data…（F14-1 已經在卡片上了）
        │
  [Match another source]  ←── connector：這一顆在另一份資料裡是哪一顆
        │  (寫進 ctx.meta["_defect_item:<sid>"]，吐 paired / match_dist_nm)
        ▼
  [Load images #2]  source=<sid>  ← 只負責把**那一顆**的圖讀進來，命名成流
        │
        ▼  兩邊的流從這裡開始就是一般的影像流（Enhance / Compare / …）
```

**為什麼是兩張卡不是一張**：一張卡一次處理。connector 做的是「挑哪一顆」
（有參數、吐數字、可能配不到），Load 做的是「讀圖」（沒有選擇）。合成一張的話，
「配得多近」這個數字會變成一張載入卡的副產品，而換一個配對規則要動到載入。

**畫布怎麼看得出來**：`Load images #2` 的 `source` 參數指著一個 source id，
而定義它的是那張 connector —— 那正是 F12 的區域線的形狀（**線從參數推導、
不存進 `recipe.edges`**）。所以這裡不發明第三種線，用同一套機制再開一種筆觸。

## 5. 配對怎麼算

**主鍵是座標，形狀只是相容性檢查。** 「最像」如果是指影像內容，那是 N×M 次
影像比對（400 × 5000 顆就是兩百萬次），而且它答的是另一個問題。

1. **候選**：形狀相容的（`(h, w)` 一樣，或差在容許的縮放內）。
2. **距離**：wafer 絕對座標（`die` × die 尺寸 + `xrel_nm/yrel_nm`）的歐氏距離。
3. **取最近的一顆**，而且要在 `max_distance_nm` 之內；超過就是**沒配到**。
4. **每一顆都吐**：`paired`（0/1）、`match_dist_nm`、`match_id`（配到誰）。
   沒配到**不殺整批**（鐵則 7）—— 下游看得到 `paired=0`，使用者可以在分數
   表達式裡把它擋掉。

一對多（main 一顆對到 B 的兩顆）：**取最近的那一顆**，並吐
`match_ambiguous=1` 讓它看得見。

## 6. 快取簽章怎麼保持誠實（鐵則 9）

配對是在 pipeline 裡算的，而快取鍵是在跑之前算的 —— 看起來衝突，其實不會：
**配對結果是 (connector 參數, 第二 source 的身分, 這一顆 main defect) 的
確定性函數**。所以簽章加兩樣就夠：

* connector 卡的參數（本來就在 `sig_nodes` 裡）；
* **第二個 source 的 token**（`_dataset_token_for` 已經在做這件事，
  對 sidecar 也已經有 `_sidecar_token` 這個先例）。

換一份第二 source → token 變 → 整段重算。這正是 GLAS 那條路擔心的事，
而它在 ingest 讀檔的前提下自動成立。

## 7. KLARF 寫回

寫回 **main** 那一份，一個字都不用改（`klarf_core` 的 span-splice 認的是
`DefectItem.klarf_row`，而那是 main 的列索引）。第二 source 沒有 KLARF 也
無所謂 —— 它只是圖。

## 8. 分幾步

| 步 | 做什麼 | 為什麼可以獨立驗收 |
|---|---|---|
| **A** | `Dataset.source_id` + Studio 持有多份 + 第二張 Load 卡指定 source | 還沒有配對：兩份的第 n 顆對第 n 顆（順序配對），先把管線打通 |
| **B** | `match_source` 卡（座標 + 形狀）＋ `paired` / `match_dist_nm` | 拿真實的兩份資料量配對率 |
| **C** | 快取簽章、`run_batch` 的 `others=`、worker 傳遞 | 平行跑出來的數字要跟 `workers=1` 逐位元組相同（鐵則 9 那條測試） |
| **D** | 畫布上的 source 線、connector 的儀表（配對率、距離分布） | 看得見配得好不好 |

**A 之前不要碰 B**：順序配對雖然簡單得幼稚，但它讓「多 source」這件事本身
先跑起來 —— 而配對規則要拿真實資料調，那是 B 的事。

## 9. 還沒定的（要先回答才動手）

1. **「image 形狀」是尺寸還是內容？** 我的假設是**尺寸**（相容性檢查），
   而「最像」由座標決定。如果真的要比內容，那是另一張卡（配完之後算一個
   相似度分數），不是配對本身。
2. **main 是哪一種？** 要寫回哪一份 KLARF，決定誰是 main。
3. **兩份 KLARF 的座標系一樣嗎**（同一片 wafer、同一個 die grid、同一個原點）？
   不一樣的話，配對前要先做一次座標對齊（那會是 connector 的參數，或另一張卡）。
4. **配不到的那一顆**：照跑但 `paired=0`（我的建議，鐵則 7），還是整顆算失敗？
5. **第二個 source 有 KLARF 嗎**？沒有的話座標從哪來 —— 那時候就只剩形狀，
   而形狀配不出一對一。
