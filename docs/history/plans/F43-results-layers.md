# F43 — 結果表：分層 + 診斷徽章（總工作單 PR-1）

2026-08-27。總工作單「特徵與介面改版」三個 PR 的第一個。

## 問題

批次結果表五六十欄平鋪：判定真正用到的兩三個數字，跟每張卡順手吐的品質
指標、救援名、`route_taken` 全部攤在同一排，使用者找不到重點。

## 做了什麼

**分層是自動的**（由 recipe 推導，沒有手動挑欄的設定頁 —— 使用者定調）：

* **core（新模組）`d4t/core/pipeline/verdict_features.py`** —— 判定到底問了
  哪幾個數字，唯一出處。四個來源的聯集：判定樹（`decide_tree.features_used`，
  let 已展開含巢狀）、score 算式（`Expression.variables`；decide 在時 score
  不跑，二取一）、route 上啟用卡的 `optional_features_in` 與
  `resolve_features_in`。**引用了沒人產出的名字照樣入集合** —— 空欄看得到比
  默默消失好。另外三支：`diagnostic_columns`（含 engine 救援名，跟
  `feature_prefixes` 同一支）、`diagnostic_alarm_map`、`feature_groups_by_card`
  （第一產出者歸戶、執行序）。
  放新模組的原因：`decide_tree` 在模組層 import `recipe`，塞進 recipe.py 就
  循環了。
* **UI `results_table.py`** —— 判定層（徽章 + base + class + 判定特徵，照
  引用順序）預設可見；其餘按產出卡分組排在後面，`ResultsTablePane` 的
  「All measurements (N)」整批展開、搜尋框子字串把摺疊欄叫出來（清空還原、
  搜尋不改展開狀態）。分層邏輯全在純函式 `visible_columns` 上。展開狀態
  session 級（純 attr，不進 QSettings）。
* **診斷徽章** —— 診斷欄離開表格（兩層都不出現），每列最左一格徽章：
  警示**只**來自整列的 `error` 與卡宣告的布林（新的
  `Step.diagnostic_alarms -> [(名字, 壞值)]`，極性是資料不是後綴猜的）。
  數值型診斷（sat 那類）不在 alarm 表上，UI 想發明門檻也沒有依據。
  懸停/點擊看明細（名字、值、來自哪張卡 —— 由該列 `traces` 歸戶，引擎真相）。
  匯出照舊含診斷欄（匯出不走 `table_columns`，`report.py` 一個位元組沒動）。

## 跟工作單的三筆偏離（都有記錄）

1. **沿用 `diagnostic_features`，不另開 `resolve_diagnostics`** —— 工作單寫
   的那支其實已經存在（F11 Enhance-3），另開新名違反「一個主題一個家」。
   後果之一順手收下：兩張 GLV 卡撞 `glv_pixels` 不再警告（兩邊都宣告診斷，
   跟 `clip_frac` 同一條路；`glv_median` 的撞名照講）——
   `test_card_invariants.py` 那條測試改成鎖新行為。
2. **GLV 的 sat 族不宣告成診斷**（使用者 2026-08-27 拍板）：`glv_sat_frac` /
   `glv_above128` 是 `metrics` 勾了才產出的統計量，勾了就是要看的。診斷只收
   品質/信任族：`glv_pixels`、`glv_ok`（有 min_pixels 時）、`glv_boxes`
   （each box 時）；CD 收 `cd_n`/`cd_lines`/`cd_edge_score`（線）、
   `cd_touches_edge`/`cd_edge_score`（團）。`cd_axis_deg`/`cd_bright` 保持
   量測欄（F19：自動決定要畫得出分布）。
3. **Focus 沒有 error/trust 名可宣告**（工作單假設有誤）—— `focus_quality`
   只吐三個銳利度值，什麼都不宣告。

另一條使用者拍板：**判定引用 > 診斷隱藏** —— 判定樹真的比了 `glv_ok` 的話
那一欄照樣進判定層（「這顆為什麼判 NG」要看得到比的那個值），規矩住在
`column_layout` 一個地方。

## 驗收（工作單 PR-1 驗收單）

* 1a 邊界測試齊（`tests/test_verdict_features.py`）：沒人產出照樣入集合、
  只有 score、停用卡不貢獻、route 各自算、巢狀 let、引用順序。
* 診斷鐵測試：registry 全掃 `diagnostic_features ⊆ resolve_features`、
  alarm 名 ⊆ diagnostics（預設 + 變體參數），配反空洞。
* UI 不變量（`tests/test_ui_results_layers.py`）：預設可見集合、展開全可見、
  搜尋命中現身、診斷欄不在可見集合、布林警示/數值不警示、明細三元組、
  排序與選列不變。
* 匯出逐位元組（`test_export_parity.py` 全綠、`report.py` 未動）；
  `tools/freeze_golden.py --check` 三份逐項相同；核心與 UI 兩批全綠。
