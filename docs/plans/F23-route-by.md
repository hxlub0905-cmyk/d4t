# F23 — 分流：不同 CLASSNUMBER 走不同的卡片

> 狀態：**期1（引擎）已完成（2026-08-24）**；期2（UI）、期3（lot_stats）未動。
> 四題已定調（使用者 2026-08-24「照提案著做」）：① default 兩種都支援、
> ② 第一期用選項 A、③ 預覽自動切 route、④ lot_stats 併第 3 期。
> 期1 的實作紀錄見 `SESSION_LOG.md`；驗收在 `tests/test_route_by.py`（27 條）。
> 需求（使用者 2026-08-24 原話）：「我要的 pre-filter 不是不同判定，而是
> **不同的 Classnumber 走不同的『卡片』**」——
> Classnumber=1 走 A route、Classnumber=2 走 B route，各自不同的卡。

---

## 1. 一句話

把「這一顆走哪條 route」從**一批一個常數**（`dataset.kind`）變成
**逐顆由 KLARF 的一欄決定**。

## 2. 為什麼判定段（F22 的 decide）代替不了它

`decide` 的規則可以寫 `CLASSNUMBER == 1`，但那是**跑完所有卡之後**才分的 ——
每一顆還是把兩組卡都跑過一遍。分流要的是 Class 2 **根本不跑** A 組卡：

* **省計算**：10k 顆的批次，每顆多跑一組用不到的量測是實打實的時間；
* **避免假數字**：對 Class 2 跑 A 組的 CD 卡，量出來的是一個看起來正常、
  但問錯問題的數字 —— 它會進 CSV，而沒有任何線索說它不該被看。

## 3. 現況盤點：機制八成在，卡住的只有一件事

| 需要的 | 現況 |
|---|---|
| 一份 recipe 好幾條 route | ✅ `recipe.routes` 就是 `{鍵: [節點]}`，`execution_order(recipe, 鍵)` 支援任意鍵 |
| 逐顆拿得到 KLARF 欄 | ✅ `fill_fields(dataset, columns)` 填進 `item.fields`（F16 起 main 也用） |
| 引擎不假設一批一條路 | ✅ `run_defect(recipe, item, kind)` 的 kind 是逐次呼叫傳的 |
| 快取分得開 | ✅ 簽章已含 route 鍵 |
| **逐顆決定鍵** | ❌ `run_batch` 第 250 行：`kind = dataset.kind`，一批一個常數 |

合成資料也現成：`make_sample.py` 的 KLARF 本來就有 `CLASSNUMBER` 欄。

## 4. `route_by` 的形狀（提案）

recipe 頂層一個新區塊，跟 `kind` 同層級（**在跑之前**就決定，所以不能是卡片
—— 卡片是在 route 裡面跑的，雞生蛋；也不能是 decide 的表達式 —— 那些變數是
特徵，特徵要跑完才有）：

```json
"route_by": {
  "column": "CLASSNUMBER",
  "map":    { "1": "particle_route", "2": "scratch_route" },
  "default": "particle_route"
}
```

語意：

* `column` 是 KLARF 的欄名（大寫），值**先 strip 再比字串**（KLARF 的值都是
  字串；`"1"` 與 `" 1"` 要同一格）。
* 對不上 `map` 的走 `default`；`default` 留空 = 對不上就是**這一顆失敗**
  （`ok=False`，訊息講出「值 X 不在對照表裡」）—— 兩種都要支援，因為
  「沒見過的 class 該怎麼辦」是站點政策不是軟體能替他決定的。
* **鐵則 9 條款**：`route_by` 不在 → 一個位元都不動（跟 `decide` 同一個
  嚴格附加模式）。round-trip 是 identity。

### 4.1 三個必須跟著出生的東西（F21/F22 的教訓直接套用）

1. **`route_taken` 特徵**（每一顆永遠寫，值＝route 鍵的索引或雜湊；route 名
   本身進 `ctx.meta`）—— F19 的規矩：自動做的每個決定都要是一個畫得出分布的
   數字。沒有它，CSV 上 `cd_median` 空白的顆分不出「走了 B 路沒量」還是
   「走了 A 路量不到」。
2. **掉進 default 的顆數要看得見**（CLI 摘要一行 ＋ Studio 狀態列）——
   站點換了編碼，全部掉進 default 是「跑得完、有數字、而且是錯的」的形狀。
3. **三條 lint**：`route_by` 指到 KLARF 沒有的欄（error）、map 指到不存在的
   route（error）、**有 route 一批一顆都沒走**（warning —— 寫了但用不到的
   路最容易爛）。

### 4.2 與 `kind` 的關係（要定調 ①）

一份 recipe 目前用 kind 當 route 鍵（`ebi_patch` / `rsem`）。`route_by` 進來
之後兩個軸疊在一起。提案：**`route_by` 存在時覆蓋 kind 選路**，並限制
「一份帶 `route_by` 的 recipe 只服務一種 kind」（lint 擋）。理由：實務上一批
只有一種 kind；複合鍵（`ebi_patch/1`）的複雜度現在買不到東西。

## 5. 前置：F17-⑤（route 模型）—— 最大的一筆，要定調 ②

現在的模型：**節點跨 route 共用 id**。分流的兩條路幾乎必然要「同名但參數不同
的卡」（兩條路各自的 normalize），而共用 id 做不到 —— 改 A 路的卡會動到 B 路，
且畫布上看不出兩張卡是「同一件事的兩個版本」。

兩個選項：

| | 選項 A：維持現模型 ＋ 慣例 | 選項 B：一份 recipe 一個圖（F17-⑤ 本體） |
|---|---|---|
| 做法 | 兩條 route 用**不同的節點 id**（`normA` / `normB`），共用的卡（load）同 id | 整份 recipe 是一張圖，入口卡後面**分岔**；route 是圖上的兩條支線，不再是兩張清單 |
| 動多少 | 幾乎零（模型已支援 route 各列各的 id） | `routes` 資料結構、拓撲、UI 的 route 切換、遷移 |
| 畫布 | 一次看一條 route（現況 `RecipeModel` 就是單 route），**切著看** | 一張畫布看到整個分岔 —— 分流「長什麼樣」直接畫出來 |
| 風險 | 「兩份幾乎一樣的 route」會漂（改 A 忘了改 B）—— 這個 repo 最怕的形狀 | 大手術；F17 當時評「代價大」 |
| 我的建議 | **第一期用 A** | 症狀出現（route 真的開始漂）再做 B |

選 A 的配套：一支 lint `routes-drift`（兩條 route 上**同一張卡不同參數**時
提示 —— 不是 error，因為「刻意不同」正是分流的目的；提示的是「這兩張卡差在
哪幾格」，跟 `uneven-treatment` 同一個家族）。

## 6. UI（要定調 ③）

> **2026-08-24 補**：判定段的畫布形狀已在
> [`F24-decision-tree.md`](F24-decision-tree.md) 定稿（判定樹上畫布）。
> 分流的每條支線最後匯進**同一棵**判定樹 —— 本節的 route 切換與預覽跟隨
> 照舊，判定那一半改為引用 F24。

`RecipeModel` 是單 route 的，畫布一次顯示一條 —— 這一點第一期**不動**，補三件：

1. **route 切換器**放到工具列（現在切 kind 藏在資料集邏輯裡）：
   `Route: [particle_route ▾]`，切了畫布跟著換。
2. **預覽跟著這一顆走**：看 defect 12 時，畫布自動切到它真正走的 route，
   標籤寫 `defect 12 · CLASSNUMBER=2 · route "scratch_route"` ——
   不做這個就是 F10 那批「畫布說謊」的重演。
3. `route_by` 的編輯放在**判定面板同一欄的上方**（一個小區塊：欄位下拉
   （`choices_from="main_columns"` 現成）＋ 值→route 的對照表）。
   不是卡片、不進畫布 —— 它在跑之前就決定，畫布畫的是跑的東西。

## 7. 引擎改動（小）

* `run_batch`：`kind` 常數 → 每顆 `route_key = route_of(item, recipe, kind)`；
  worker 的 `_init_worker` 拿掉 kind 常數，`_run_one` 逐顆算。
  `item.fields` 本來就 pickle 得進 worker（`fill_fields` 的設計目的）。
* `run_batch` 開跑前自動 `fill_fields(dataset, [route_by.column])` ——
  使用者不必記得先 carry。
* 快取簽章：`image_segment_signature(recipe, route_key)` 已經吃鍵，零改動；
  條目數會變多（兩條路各一份），可接受。

## 8. 搭這一輪一起做：`lot_stats` 與兩趟引擎（要定調 ④）

Algo 段最後一張卡（跨顆換算：robust z / 百分位 / Tukey 離群）卡在
「跨顆算出來的數字進不了判定」—— `_eval_score` 在 `run_defect` 裡面跑，
`run_batch_steps` 在整批之後。

提案（跟 F23 動同一段程式，所以併一輪）：

```
run_batch（逐顆，判定先跳過或先算一版）
   ↓
SCALE_LOT 的 Algo 卡（lot_stats）：回填每顆的 features
   ↓
重算判定（rescore 那條現成的路：不重跑影像，秒級）
   ↓
run_batch_steps（Output 卡照舊最後）
```

規矩：`lot_stats` 取中位數時**排除 `feature_fill` 補進去的值**
（`<name>_missing == 1` 的列不算 —— A1 當時就記下的那件事）。

## 9. 上一輪評估的十個問題 → 對照表

| # | 問題 | 本計畫的答案 |
|---|---|---|
| 1 | 特徵表參差 | `feature_fill` ＋ `route_taken` 特徵（§4.1） |
| 2 | route 之間漂 | 選項 A ＋ `routes-drift` lint（§5） |
| 3 | 畫布說謊 | 預覽自動切 route ＋ 標籤（§6） |
| 4 | 沒對到的值 | default 顆數看得見（§4.1） |
| 5 | 選法住哪 | recipe 頂層 `route_by`（§4） |
| 6 | 與 kind 撞 | route_by 覆蓋，單 kind 限制（§4.2） |
| 7 | 批次平行 | 逐顆算鍵（§7） |
| 8 | 健檢 | 三條 lint（§4.1） |
| 9 | 快取 | 簽章已含鍵，零改動（§7） |
| 10 | KLARF 寫回 | bin 仍是一個整數，不受影響 |

## 10. 驗收（先寫好再動工）

* 合成 lot 用現成的 `CLASSNUMBER` 欄產兩群，A 路量 CD、B 路量 blob：
  逐顆比對「走對路」＝ 100%、`route_taken` 每顆都在、B 路的顆**沒有** A 路
  才有的特徵（證明真的沒跑，不是跑了丟掉）。
* `workers=1` 與 `workers=4` 結果逐位元組相同（鐵則 9 的分流版）。
* 沒有 `route_by` 的 recipe：黃金值三份逐項相同（嚴格附加的證明）。
* 快取冷跑＝熱跑（兩條路各自驗）。

## 11. 分期

| 期 | 內容 | 大小 |
|---|---|---|
| 1 | `route_by` 引擎（§4、§7）＋ lint ＋ 驗收 | ✅ **2026-08-24 完成** |
| 2 | UI 三件（§6） | ✅ **2026-08-24 完成**（route 切換器、預覽跟著顆走＋標籤、`RouteByBox` 編輯區塊；model 抱住整份多 route recipe，見 SESSION_LOG） |
| 3 | `lot_stats` ＋ 兩趟判定（§8） | ✅ **2026-08-24 完成**（不是一張卡 —— 照 F24 §5 做成 `Let.scale`「跟整批比」；`batch.apply_lot_scaling` 回填＋重算判定，`_missing==1` 的顆不進統計） |
| — | F17-⑤ 選項 B | 等症狀 |

---

## 四題的定調（使用者 2026-08-24「照提案著做」）

1. **對不上 map 的預設行為**：兩種都支援，`default` 留空＝那一顆失敗
   （訊息講出值 X 不在對照表裡）。✅ 已實作。
2. **route 模型**：第一期用選項 A（不同節點 id）。`routes-drift` lint
   **先不做**：它會對**每一份**刻意分流的 recipe 叫（兩條路的卡不同參數
   正是分流的目的），而「一支會誤報的 lint 比沒有 lint 更糟」是這個 repo
   自己的規矩（F11 Enhance-3）。要不要做、判準收多窄，等真的漂過一次
   再跟使用者定調。
3. **UI**：預覽自動切 route。→ 期2。
4. **`lot_stats`**：併第 3 期。

## 期1 實作備忘（跟提案不同的兩個小地方）

* **route 在 `run_defect`／`run_defect_cached` 裡自己解**，不是在 `run_batch`
  逐顆算了傳進去（§7 原提案）—— 呼叫端一個都不必改，Studio 預覽因此自動拿到
  同一個答案（③ 的引擎那一半免費了）。`_init_worker` 的 kind 常數**留著**：
  它現在只是資料身分（`meta["_dataset_kind"]`，load 卡讀它），不再選路。
* `run_batch` 的自動補欄**只在有顆缺這一欄時**動手，而且補「現有欄位 ∪
  這一欄」—— `fill_fields` 是整份換掉，只補一欄會把 carry 進來的其他欄洗掉；
  每顆都有＝一個位元不動（測試手排路線靠這個）。
* 合成資料：`make_sample.py --class-by-truth`（REAL=1、NUISANCE=2）。**選配**，
  預設輸出逐位元組不變 —— `test_export_klarf` 倚著「原檔 CLASSNUMBER 全 0」
  在算「應該改動幾列」。
