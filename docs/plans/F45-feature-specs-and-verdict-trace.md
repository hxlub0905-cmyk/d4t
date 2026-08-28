# F45 — 結構化身分（FeatureSpec）＋ 分數回溯（verdict_trace / WhyPanel）

**總工作單 PR-3**（2026-08-27 ～ 08-28）。PR-1＝F43、PR-2＝F44。

## 問題

特徵是扁平字串，UI 只能拆字串猜語意（`_split_cmp` 的最長比對、
`endswith("_nm")`、`endswith("locate_ok")`…），而每一處猜法都是一份會漂的
第二真相。「這顆為什麼判 NG」要人腦重放：打開 recipe、找到樹、逐格查 CSV。

## 解法（三件事）

1. **結構在名字誕生處建立**：`FeatureSpec`（`pipeline/step.py`）——
   name / card / base / stream / region / region_index / region_role / own /
   variant / metric / stat / family。唯一產地 `Step.resolve_feature_specs`
   （組名字的迴圈同時宣告身分），`resolve_features` / `feature_parts` 是投影。
   **使用者拍板（2026-08-27）**：variant 照真實文法
   （`"" | nm | nm2 | typical | outlier | outlier_box | missing | raw |
   rescued`）；center/others 住 region + region_role；worst/judge 是 metric。
2. **判定可重放**：`pipeline/verdict_trace.py` ——
   `verdict_trace(recipe, route, features) → Trace`（帶實值的算式
   `valued_text`（pos 替換，子字串撞名免疫）、逐步路徑與缺值、葉子）。
   三條立身規矩：不重算任何值（SAFE 語意不可能跟引擎不一致）、有 `scale`
   的 let 不重放（鏡射 `batch.redecide` 丟 scale let）、缺值明白標名字。
   樹走訪與引擎同一支：`decide_tree.walk_steps`（`walk` 變三行投影）。
3. **三次點擊回溯**：結果表點 score/bin/class → `ui/why_panel.py`
   （`why_rows` 純函式先、薄 widget 後；Esc 關、不搶焦點、不擋列選取）→
   點一項經 `bound_specs` 跳到產出卡；有區域的項
   `StudioWindow.highlight_region` ＋ `ImageView.set_overlay_emphasis`
   把那一塊亮起來（命中全強度、其餘降 alpha —— 不 overload focus，
   `set_overlay` 會清掉）；引擎項對映 Score / Bin 偽卡。
   Preview 的 Path 行改建在 trace 上（刪 meta 讀）。

## 其他落地

- **binder**：`verdict_features.bound_specs`（BoundSpec = node_id + label +
  spec；名字歸第一個產出者；救援名 `FeatureSpec.qualified` 與引擎同一支；
  引擎組 score**有算式才宣告**／decide_unanswered／route_taken／let ＋
  `_missing`/`_raw`）。**刪 `feature_groups_by_card`**。
- **結果表**：`column_tree`（卡→區域→統計量的樹只算一次；同區域欄相鄰）、
  `TwoLevelHeader`（上半區域跨欄、`theme.region_hex` 同色；無區域＝單層
  一個像素不變；`header_spans` 純函式畫測同源；tooltip 第一行永遠是原始
  欄名）、維度過濾（Region/Statistic/Card 下拉＋`widgets.FilterChip`
  （自 `gallery._Chip` 升格）；chip 限縮兩層、同維 OR 跨維 AND、
  **搜尋命中 > 維度限縮**）。
- **必刪清單六處全刪**（各有替案）：viewmodel nm 字尾 → variant（三份清單
  收成一個 `_declared_specs` 迴圈）；`feature_gloss` 吃 spec、
  **刪 `_split_cmp`**、無 spec 留白不猜；gloss 排序看 `family=="cmp"`；
  `_compare_caption` 讀 GLV note 的 `metrics` 表（舊 meta 缺 → 留白）；
  CD `_paint_batch` 查 note 的 `feature_names`（缺 → 裸 base）；
  region_check 用 `spec.metric == "locate_ok"`（加了 output_prefix 案例）。
  grep-proof：`rg 'endswith\("_nm|split\("cmp_|endswith\("locate_ok|_split_cmp'`
  只剩 docstring 的歷史敘述。
- **鐵測試**（`tests/test_feature_specs.py`）三半：A＝registry 全掃
  `spec.name == resolve_features`（含順序、parts 子集）；B＝**改碼前抓的
  字面快照**（spec-first 之後這一半才是真的鐵）；C＝反空洞結構抽查
  （autofill 陷阱、center 角色、each-box variant、nm 孿生繼承 metric、
  enhance PAIR 無 stream）。
- **出貨煙霧**：CHAR 三類各一顆重放逐項同引擎（leaf/path/缺值總數）＋
  未配置跑的 `die_rank` filled；PATCH 一顆三題全帶值無 "?"。
  ⚠ 疊在既有的 e2e 測試裡，不另起批次 —— CI 時間不變差。

## 記錄在案的偏離（相對工作單字面）

- spec 欄位比工作單五欄多（feature_html 與刪 cmp_ 拆解都需要）。
- 「`len(missing) == decide_unanswered`」修正為**逐步缺值總數**
  （引擎每一題各記一次不去重；`Trace.missing` 才去重）。
- 面板模組名 `why_panel.py`（`trace_panel` 與既有 `tree_panel` 太像）。
- 表頭上半點擊不特殊處理（預設 QHeaderView＝排序該欄）。
- `FEATURE_LABEL_SEP` 保留（傳輸編碼，不是猜語意）。

## 硬邊界（全程守住）

特徵字串名一個位元組不改（B 半快照）；黃金值三份逐項相同（每個 core commit
後 `freeze_golden --check`）；匯出逐位元組（export 程式碼零改動，meta 只增）；
core 不 import Qt；Python 3.9；UI 英文；UI 測試寫不變量。
