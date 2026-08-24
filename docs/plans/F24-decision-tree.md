# F24 — 判定樹上畫布（分揀槽定稿）

> 狀態：**方向已定稿（2026-08-24，使用者看過 mockup 拍板），未動工**。
> Mockup（四個 artboard，含便利貼註記）：
> https://claude.ai/code/artifact/adfed023-6280-4acf-b6c0-749c9f299767
> 前情：F22 做了多類別引擎（`decide`：平面規則清單）與判定面板；
> F21 §5.2 記了「特徵線」的重啟條件；使用者 2026-08-24 定調本篇。

---

## 1. 使用者定調的三句話

1. **「以終為始 —— 這是給不會寫 code 的人使用的，畫布不能說謊。」**
2. **「分揀槽（ADC）也要在畫布上呈現。」**
3. **「希望它是多步驟判定（decision tree like）。」**

## 2. 心智模型：三種東西，三種呈現

之前所有「畫布說謊」的病根是同一個：**硬把數字塞進線的隱喻**。線對影像是真的
（像素真的流），對區域勉強是真的（名字對應來源），對數字是假的（引擎裡特徵是
一張全域的表，`engine._local_view` 只有 `images` 是每張卡自己的）。定稿：

> **畫布管「圖與區域怎麼流」，表格管「數字」，判定樹管「怎麼分」。**

| 東西 | 呈現 | 誠實的理由 |
|---|---|---|
| 影像流 | 實線（現況） | 像素真的沿線流 |
| 具名區域 | 虛線＋菱形埠（現況，F12） | 名字唯一，來源推得出來 |
| 數字 | **不畫常駐的線**；要問來源用幽靈線（§7） | 引擎裡是全域表，畫存的線就是說謊 |
| 判定 | **一棵樹，住在畫布上**（§4） | 樹的每一步真的就是引擎的一步 |

## 3. 資料結構：`decide` 從清單長成樹

F22 的 `DecideSpec.rules` 是「由上往下第一個成立的贏」—— 那**就是一條鏈狀的
樹**（每一步 yes → 葉子、no → 下一步）。所以這不是換掉 F22，是把它一般化：

```json
"decide": {
  "let": [ {"name": "contrast", "expr": "cmp_delta_median * cd_deq"} ],
  "tree": {
    "when": "cd_deq_missing > 0",
    "yes":  {"bin": 9, "label": "not measurable"},
    "no": {
      "when": "contrast > 120",
      "yes": {"bin": 3, "label": "big particle"},
      "no": {
        "when": "contrast > 30",
        "yes": {"bin": 2, "label": "particle"},
        "no": {
          "when": "brightness > 6",
          "yes": {"bin": 1, "label": "faint"},
          "no":  {"bin": 0, "label": "nuisance"}
        }
      }
    }
  },
  "score": "contrast"
}
```

* 節點兩種：**步驟**（`when` ＋ `yes` ＋ `no`，兩邊各自是步驟或葉子）與
  **葉子**（`bin` ＋ `label`）。
* **`rules` 與 `tree` 二選一**（同 `score` vs `decide` 的 `ambiguous-decision`
  模式）。讀到 `rules` 的舊 recipe **自動翻成鏈狀樹是無損的**——遷移判準是
  「舊東西在不在」（鐵則 9），且 `rules` 寫法照讀不誤（F22 的 21 條測試不動）。
* 引擎：`_eval_decision` 從根往下走；**每一顆記下走過的路徑**
  （`ctx.meta["decide"]["path"]`，一串 yes/no）——Preview 的 Path 與畫布的
  分支流量都吃它。
* 深度上限與 lint：`tree` 太深（>16）warning；兩個葉子同 bin 合法（同 F22
  規則共用 bin）；`when` 解析不了沿用 `bad-rule`。

## 4. 畫布：判定區（定稿的樣子，見 mockup 主圖）

* **判定區**：畫布右側一塊淡紫底（`seg_adc_bg`）虛線框，標題 DECISION。
  它是畫布的一部分（一起平移縮放），不是側欄。
* **入口小卡**：funnel icon ＋「Decision」＋ `ƒ` working numbers 摘要 ＋
  試跑後的「48 in」。**永遠恰好一個、不能刪**。雙擊可收合整棵樹成這一張小卡
  （嫌佔位的出口）。
* **步驟＝菱形**（流程圖語言，製程工程師本來就會讀）：`when` 寫在裡面，
  yes 往右、no 往下。點選＝右欄變成這一步的編輯面板（§6）。
* **葉子＝托盤**：類別色條＋名字＋顆數＋「x/y real」＋微型純度條。
  點托盤＝Gallery 篩出那一格。`(anything else)` 的葉子虛線框。
* **分支流量**：試跑後每條分支標「流過幾顆」（48 → 1/47 → 11/36 → …）。
  哪一步分錯了，看數字就知道 —— 這是 F22 面板「每條規則的顆數」的樹版，
  而且比它準（樹上每一條邊的顆數是唯一的，不會有「兩條規則共用 bin」的歧義）。
* **未試跑**：樹的形狀在、數字誠實地不在（**不顯示 0** —— F18 的老規矩）。
* **量測卡 → 判定區之間刻意沒有存的線**：只有一個淡的 `numbers →` 提示。

## 5. Algo 段解散；ADC 入口保留但特別化

* **卡片庫保留 ADC 入口，但跟一般卡片分家**（使用者 2026-08-24 補充定調：
  「左側 ADC card 不要拿掉，但不要跟那些畫布 card 放在一起／要讓它特別一點」）。
  定稿的樣子（mockup 已更新）：
  - segment rail 底部，**分隔線之下**一顆帶紫框的 funnel 圖示（ADC）；
  - 卡片庫清單底部一塊**淡紫底的常駐入口**（Decision · `1 of 1` 徽章 ＋
    「Always on the canvas. Click to jump to the tree.」）。
  - 它**不是可拖的卡**：點了是「跳到畫布上的樹＋選取入口卡」，不是生一張新卡
    —— 永遠恰好一棵，`1 of 1` 那顆徽章講的就是這件事。
* 卡片庫**沒有 Algo 段**。
* `feature_math` → 入口卡的 `ƒ` working numbers（`let`，F22 已有引擎與編輯器）。
* `feature_fill` → 樹的第一步天然位置（`cd_deq_missing > 0` 就是它的形狀），
  補值那一半變成 working number 行的「missing ⇒ 用 __」屬性。
* 兩張卡**先收 `HIDDEN_STEPS`**（成本零、舊 recipe 照跑），使用者用過樹之後
  確認夠了再刪（CLAUDE.md 那張收/刪對照表）。
* `lot_stats`（未做）→ working number 行的「跟整批比」勾選；引擎仍要兩趟
  （F23 §8），UI 的家先定在這裡。
* F16 的八段順序因此變七段（Algo 那格清空）—— 這是使用者 2026-08-20 定的
  段落，**動之前要再點一次頭**。

## 6. 編輯（見 mockup「Editing one step」）

點菱形 → 右欄（跟點卡片同一條路，零新概念）：

```
QUESTION   [ contrast > 120        ]  [Insert a number… ▾]
Yes →      [ ● big particle ▾ ]          ← 類別或下一步
No  →      [ ◇ next step: contrast > 30 ? ▾ ]
THIS BATCH  47 arrive here → 11 yes · 36 no
[＋ Insert step above]  [✕ Remove step]
```

* Yes/No 各自接「一個類別」或「另一步」—— 加一步＝把某一邊從葉子換成新菱形。
* 「Insert a number ▾」沿用 F21-B 那一支（名字—誰算的）。
* 拿掉一步：它的 no 邊接回上游（葉子孤兒要問使用者）。

## 7. 幽靈線（見 mockup「Ghost trace」）

滑鼠停在**任何地方**的數字名上（菱形裡、working numbers、特徵表）→
產出它的卡發亮＋一條**臨時**的點線＋光暈＋「from CD」標籤拉回去，移開就消失。

* 從 `feat_owner`（寫入當下的事實）推導 —— 所以它不說謊。
* 樣式刻意跟資料流的線不同：**它是一個「答案」，不是一條連接**。
* 使用者不用拉、沒有新埠 —— 8/20 否決第三種埠的理由（學習成本）不適用。

## 8. Preview 的 Path

右欄 Preview 逐顆顯示：類別 chip（色點＋名字＋bin）、
`Path: missing? no → contrast > 120 yes`、working numbers 的值。
瀏覽 defect 時**路徑在樹上亮起來**。資料就是 §3 的 `meta["decide"]["path"]`。

## 9. 分期（每期獨立可收）

| 期 | 內容 | 依賴 |
|---|---|---|
| ① | 資料結構＋引擎：`tree` 節點、路徑記錄、`rules`→鏈狀樹遷移、lint | ✅ 2026-08-24 |
| ② | 畫布渲染（唯讀）：判定區、入口卡、菱形、托盤、分支流量、未試跑狀態 | ✅ 2026-08-24（`ui/tree_scene.py`；流量由特徵重走樹算，見 SESSION_LOG） |
| ③ | 編輯互動：點菱形→右欄面板、加/刪步、收合 | ✅ 2026-08-24（`ui/tree_panel.py`；rules 在第一次點菱形時無損轉樹） |
| ④ | 幽靈線 ＋ Algo 收進 `HIDDEN_STEPS` ＋ Preview Path | ✅ 2026-08-24（幽靈線從宣告推 `feature_owners`；path 亮在樹上） |
| ⑤ | working numbers 的「missing ⇒」與「跟整批比」（吸收 feature_fill / lot_stats） | ③ ＋ F23 §8 的兩趟引擎 |

與 **F23（route_by）**的關係：分流的每條支線最後都流進**同一棵**判定樹 ——
畫布上兩條支線匯進一個判定區，pre-filter 的故事一張圖講完。F23 §6 的 UI 期
改為引用本篇。

## 10. 驗收（先寫好）

* `rules` 舊 recipe 讀進來＝等價鏈狀樹：**48 顆逐顆 bin 相同、score 相同**
  （拿 F22 那份實跑 recipe 當基準）。
* 樹的 round-trip 是 identity（鐵則 9）。
* 每一顆的 `path` 與 bin 一致（走 path 重算一次 bin 必同）。
* 分支流量加總守恆：每個菱形 in = yes + no；根 = 批次總數。
* 未試跑：畫布上沒有任何數字（不是 0）。
* 黃金值三份不動（沒有 `decide` 的 recipe 一個位元不變）。
