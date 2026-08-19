# F15 — 配對分析：一張卡，帶自己的 source

**狀態**：設計定稿（2026-08-19）。**還沒動程式碼。**
**前置**：F14-1（資料的入口已經在讀它的那張卡上）。

---

## 1. 使用者要的東西（第二次講，這一次是對的形狀）

> 「我只想把它做成一個小功能 card，這張 card 會 load 自己的 source。
> 主要流程什麼 ROI GLV MEASURE 一樣什麼都可以做，但**如果要做配對分析就用
> 這張卡**。」

加上前一輪定調的四件事：兩筆就是不同的 set、**指定一個 main**、
用 KLARF 位置 + image 形狀找最像的、**KLARF 寫回 main**。

## 2. 我原本提的兩張卡是錯的

我上一版把它拆成 `Match another source`（挑哪一顆）+ `Load images #2`（讀圖），
理由是「一張卡一次處理」。**那個拆法立不住**，而使用者的說法自己帶出了證據：

* `Load images #2` 沒有 connector **不知道要讀哪一顆**；
* connector 沒有 Load **吐不出任何影像**。

兩張永遠只能成對出現、單獨放上去都不成立的卡，就是**一張卡**。
（這個 repo 對這件事已經有一條規矩：一張卡如果只為了餵另一張而存在，
它就不該是獨立的一張。）

**「挑哪一顆」本來就是讀取的一部分**——`load_patch` 也在挑（一顆 defect 對到
多頁 TIFF 的哪幾頁），只是它的挑法沒有參數。

## 3. 這張卡

**`pair_source`「Pair with another source」**（Input 段）

| 參數 | 型別 | 說明 |
|---|---|---|
| `source` | `str`（唯讀，卡片上按 `Open data…` 選） | 這張卡自己的那一份資料 |
| `match` | `choice`：`position` / `order` | 怎麼決定「這一顆對到那邊哪一顆」 |
| `max_distance_nm` | `float` | 超過就算沒配到（`position` 才顯示） |
| `out` | `image_key`（direction=out） | 配到的那顆的圖叫什麼流名 |

產出：

* **一條影像流**（`out`）——之後 Enhance / Compare / ROI / Measure 一切照舊；
* **兩個特徵**：`paired`（0/1）、`match_dist_nm`（配得多近）。

**配不到的那一顆**：不吐那條流、`paired=0`。下游要它的卡會失敗，於是那一顆
`ok=False` 而**整批照跑**（鐵則 7）——跟 `load_sidecar` 遇到沒有 label 的那顆
完全同一個行為，不必發明第二套。

主流程完全不知道有這張卡存在。**不用它就是現在的 d4t。**

## 4. 路徑不進 recipe（跟 main 同一條規矩）

卡片上存的是**代號**（`source="ref"`），路徑跟著這一次的工作階段走 ——
就像 main 那一份不進 recipe 一樣。理由一樣：recipe 要能換一批資料重跑。

* Studio：卡片上那顆 `Open data…`（F14-1 已經是這個形狀了）。
* CLI：`python -m d4t run r.json <main-klarf> --source ref=<path>`。

## 5. 鐵則 9 怎麼守：**卡片不自己讀檔**

「這張 card 會 load 自己的 source」是**使用者看到的事**；引擎裡讀檔的仍然是
ingest 層 —— Studio / CLI 把那一份載成 `Dataset` 掛在 main 上（
`dataset.sources[sid]`），卡片只從已經掛好的東西裡挑一顆。

為什麼不能讓卡片自己 `open()`：影像段快取的簽章是照「這份資料是什麼」算的。
卡片偷偷讀檔的話，**換一份第二 source 而簽章看不見 → 回舊影像**，而那是
「跑得完、有數字、而且是錯的」。F9 踩過兩次。

掛上去之後簽章自動涵蓋它 —— `_dataset_token_for` 已經對 sidecar 做過同一件事
（`_sidecar_token`），這裡只是多一個來源。

## 6. 配對怎麼算

**座標是主鍵、形狀是相容性檢查。** 「最像」若指影像內容，那是 N×M 次影像比對
（400 × 5000 = 兩百萬次），而且它答的是另一個問題。

1. 候選 = 形狀相容的（`(h, w)` 相同）；
2. 距離 = wafer 絕對座標（`die` × die 尺寸 + `xrel_nm` / `yrel_nm`）的歐氏距離；
3. 取最近的一顆，且要在 `max_distance_nm` 之內；
4. 一對多 → 取最近，並吐 `match_ambiguous=1` 讓它看得見。

### 兩份 KLARF 的座標系不一樣怎麼辦

**不用先問，讓它量出來。** `match_dist_nm` 是每一顆都會有的數字：座標系對得上
的時候它是幾百 nm，對不上的時候它會是整片 wafer 的尺度。所以

* 儀表畫 `match_dist_nm` 的分布 —— 一眼看得出「這兩份根本沒對上」；
* 使用者可以用 `max_distance_nm` 把配不好的擋掉，或在分數表達式裡用 `paired`。

真的需要一次座標對齊的話，那是**之後另一張卡**的事（而且到那時候我們手上會有
真實的距離分布可以看），不是現在憑空設計。

## 7. 分兩步

| 步 | 做什麼 | 驗收 |
|---|---|---|
| **A** | 卡片 + source 掛在 dataset 上 + `match="order"` | 兩份資料的第 n 顆對第 n 顆，管線端到端跑得通、`workers=1` 與 `workers=4` 逐位元組相同 |
| **B** | `match="position"` + `match_dist_nm` + 儀表 | 拿**真實的兩份**量配對率與距離分布 |

A 的順序配對幼稚，但它讓「多 source」這件事先跑起來；配對規則要拿真實資料調，
那是 B 的事。（GLAS 那條路就是這樣做的：先寫健檢跑真實匯出，才寫卡片。）

## 8. 不做的事（明講）

* **main 以外的那一份不寫回 KLARF**、不進 defect 導覽、不進 Export ——
  它只是圖。
* **不做 N 份**：一張卡一份。要第三份就再放一張卡（各自有自己的代號與流名）。
* **不動 route**：route 仍然由 main 的 `kind` 決定。
