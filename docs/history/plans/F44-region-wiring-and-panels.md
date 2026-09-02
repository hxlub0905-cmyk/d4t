# F44 — 區域接線可讀性 + 儀表補洞（總工作單 PR-2）

2026-08-27。總工作單三個 PR 的第二個（PR-1 = F43）。六個子項 2a–2f。

## 問題

`<n>` / `<n>_center` / `<n>_others` 三顆菱形埠對使用者是三個謎；Subtract /
output_report / output_char / focus 完全沒有儀表；GLV 的 each-box 面板只講得
出「worst 是第幾格、幾個 σ」，看不到那一格的分布也看不到選拔比過的數字。

## 做了什麼

**2a — GLV「我要量什麼」三選（preset，不是參數）＋ 兩條 kind 感知 lint**

- preset 的腦袋在 `RecipeModel.glv_intent` / `apply_glv_intent`：roi 是線水合
  的（`to_json_dict` 還會省略跟線一致的值），所以 preset **動的是線**——
  存出的 JSON 跟手拉線手填格**逐位元組相同**（測試鎖著，證明 schema 沒動）。
  一次 Ctrl+Z 全還原（compound）。偵測永不改 recipe，比不上顯示 custom。
  表單那排是 `ParamForm.set_intent_row`（照 F14 `_source_row` 的注入先例）。
- **使用者拍板**：preset (1)「量缺陷那格」= roi 接 `_center` +
  reference="another region" + reference_region 接 `_others`（兩條虛線同一
  producer）。工作單字面的 REF_OTHERS+_center 是已知壞組合（派生
  `<n>_center_others`，`test_glv_compare.py` 鎖著），不用。
  across_boxes 填 pooled（`_center` 只有一格）。
- lint 住卡片上（新 hook `Step.kind_issues(params, kind)`——
  `configuration_issues` 看不到 kind）：rsem/folder 接 `_center` →
  **warning**（大圖上沒有置中保證）；patch 開 each box 且沒接 `_center` →
  **info**（缺陷位置已知，worst 可能被髒污參照格帶走）。kind 分群
  `PATCH_KINDS`/`SINGLE_IMAGE_KINDS` 搬進 step.py，UI 測試 cross-check
  它跟 `scope.SUPPORTED_KINDS` 剛好蓋滿。
- **Issue 多了真的 `info` 級**（使用者拍板）：畫布徽章不畫
  （`canvas.badge_paints`）、卡片 tooltip 與 CLI（·）看得到、run 前後的
  攔截照舊只認 error/warning。`studio._node_problems` 改 rank
  error>warning>info。

**2b — 埠一句話 / 斜線圖例 / GLV 標題：一份字典**

新模組 `d4t/ui/region_words.py`（canvas/inspectors/widgets 三方共用）。
埠 hover 掛在 view 的 `_port_tip_at`（node 故意不收 hover——邊的 × 鈕）；
ProfilePanel 摘要條右側畫斜線色塊＋「boxes left out (different material)」
（同一支斜線畫法）；GLV tab_title 接 `_center` 時講「the defect's box
(epi_center)」。USING-CD.md §2 同步了三句。

**2c — GLV worst 直方圖 + judge 值帶**

引擎在 `_measure_each_box` **同一次計算**裡對 worst 框多做一份
`pixel_hist`（同一個 rect ——逐位元組是 `ctx.roi_rects()[worst_i]` 那格、
同一組像素過濾），擴充 `glv_hist` meta 的 `worst` 欄；`judge` 新欄記
選拔比過的那串數字（>512 格等距取樣、記 `sampled`、worst 必留）。面板把
worst 疊在 typical 上（同一把 0-255 尺、danger 色實線；虛線留給參照），
標題「typical #N vs odd #K (X.Xσ) of M」；judge 帶一格一點、median 虛線、
worst 加圈。單格/零格整組不出現。

**2d — Subtract 診斷面板**

新 helper `algo_glv.signed_hist`（0 置中、±99.5 百分位、超界收編最外側 bin
記 `clipped`；docstring 明講與 `pixel_hist` 的分工——後者 0-255 寫死**不准
動**，有絆線測試）。`SubtractStep` 在 `track_changes`（預覽）下自己 note
`meta["subtract"][out]`（`diff` 是新流，`stream_change` 只記覆寫）：有號直
方圖、median/MAD/±3×MAD 超界比例、行/列平均曲線（各 ≤128 點——抓半像素對位
條紋的主角，測試用一條直方圖看不見的條紋證明這句話）。`SubtractInspector`
只畫這一份。

**2e — 輸出預覽 + focus 即時**

`planned_files(params)` 是 run_batch 那張「勾選 → 檔名」表本人（run_batch
改為迭代同一張表，writer 用 tick 查——兩份不可能漂）；
`ReportPreviewInspector`/`CharPreviewInspector` 援引 Write KLARF 的硬規則：
選到卡就列會寫哪幾個檔、隨勾選即時變、未跑就有、**永不寫檔、不猜大小**。
`focus_quality.measure` note 三個銳利度值進 meta → `FocusInspector` 單顆
立即顯示（批次 Spread 繼承補上），加一句 8-bit 提示（僅顯示，dtype 檢查歸
bug 單）。

**2f — 共用 header + 空狀態巡檢**

`note_header`/`paint_note_header`（inspectors.py，`row_labels` 仍是分辨
邏輯唯一出處；高度 `max(13, 字高)`——CD 底線被切的教訓收進 helper 一次）。
GLV/CD/Cross/Enhance/Spread 家族換用，只加標題不動主體。
`Inspector.empty_reason` 預設改寫，registry 全掃測試逼每個註冊面板自己講。
沒面板的 fallback 證據卡換成 roi_mask/load_sidecar（工作單明文不補的兩張）。

## 與工作單的偏離（都有依據）

1. preset (1) 的組合（使用者拍板，見上）。
2. info lint 加「已接 `_center` 不報」guard——不然它嘮叨的正是它自己建議的接法。
3. 2f 的 CD/Cross 採用方式是「面板頂部一條共用 header、主體整段下移」——
   它們的三欄式 caption 是主體的一部分，硬換會動到主體。

## 驗收

黃金值三份逐項相同（每個 core commit 後跑過）；`test_export_parity.py` 全綠
（planned_files 重構後）；`pixel_hist` 絆線測試；preset JSON 逐位元組；
新測試：`test_algo_glv_signed_hist`、`test_subtract_note`、
`test_glv_kind_lints`、`test_ui_info_level`、`test_ui_region_words`、
`test_ui_canvas_ports`、`test_ui_panels_pr2`、`test_ui_glv_intent`、
`test_glv_compare` 四條新增；核心 + UI 兩批全綠。
