# F103 — 標一格量週期（seed）＋ 把格線鋪回原圖看（lattice check）

狀態：**已收斂（2026-09-17）** —— 使用者說「好 試試看」當天做完：`core/algo/seed.py`、
`GoldenCell.origin`、`ui/lattice_dialog.py`（新模組）、`TemplateDialog` 的
「Mark one cell…」與「Check on the image…」；測試 `test_seed_period.py` 十一條、
`test_ui_seed_and_lattice.py` 九條。

## 1. 使用者問了什麼

> 目前計算 cell 方式你覺得還可以添加什麼方法，假設算不對我該怎麼知道？列出來。→ 好 試試看

建議清單在 `SESSION_LOG.md`（F102 那一段）。這一份做的是清單裡的第 1 項（拉一格當
種子）與「鋪回原圖」的預覽，兩個共用同一個畫布（`crop_dialog.CropView`）。

## 2. 第二種量法：`algo/seed.period_from_seed`

| 步驟 | 做法 | 為什麼 |
|---|---|---|
| 找複本 | 框的那一格當模板，`cv2.matchTemplate(TM_CCOEFF_NORMED)` 掃整張圖；二維 NMS（視窗＝框的一半）數出總複本數 | NCC 對亮度／對比免疫，同 `template.match_patch` |
| 量週期 | **只看框那一列／那一行的 NCC 剖面**：局部極大 ≥ 0.6、彼此至少隔半格；相鄰峰間距的中位數＝週期，落在 ±1 px 的比例＝信心 | O(n)、而且正是「隔壁那幾格離我多遠」的意思；二維峰有幾萬個，而且別列的峰會漏進來把間距弄歪（第一版踩到：83% 而不是 100%） |
| 平的軸 | 剖面上 ≥ 0.6 的比例超過一半＝那一軸沒有週期（垂直條紋的 Y） | 第一版在平的軸上量到 20–24 px 的假週期 —— 那只是 NMS 視窗的倒影。合成資料：有週期的軸 0.07、平的軸 1.00 |
| 原點 | 框的左上角 | 使用者標的那一格就是格線的起點，疊出來的 cell 長得跟他框的一樣 |

不假裝：同一列不到 3 個複本＝沒有週期（不拿兩個點硬算）；框裡沒結構、框蓋住整張
都直接說；間距不一致（< 70% agree）講出來但不擋。

## 3. `GoldenCell.origin`

`build_golden_cell` 多 `origin=`：給了就不做相位搜尋、不做上升邊錨定。回傳的
`origin` **已含錨定的捲動**（`(o + roll) % p`）—— 從它起每 px 一格，格子裡的東西
就是 cell。沒有週期的那一軸原點是 0（第一版拿 100 % 240 = 100 當原點，
`tile_coords` 一格都放不下，疊出一張全黑的 cell 而且不報錯 —— 測試鎖住）。

## 4. 「算錯了怎麼知道」：`ui/lattice_dialog.py`

用既有的 `ImageView`（滾輪縮放、拖曳平移、雙擊 fit）把 `golden.tile_coords`
的格子當 overlay 鋪回原圖：每一格框住的東西都一樣＝對；格線在另一頭漂到別的結構
＝錯。畫的是引擎真的用的那組格子（`GoldenCell.origin`），不是 UI 自己算的。
超過 4000 格只畫離中心最近的並講出來。非 modal：開著它回去改尺寸再按一次，
同一個視窗換格子。

## 5. 接線（`TemplateDialog`）

* 「Mark one cell…」在**目前疊的那一塊**（裁切後）上框；`load_image(..., seed=)`
  兩格都沒給尺寸時週期從 seed 來，不管誰給尺寸原點都是 seed 的左上角；
  re-stack 保留 seed；換一塊 crop 就忘掉 seed（座標不存在了）。
* 摘要多一段「period from the cell you marked (N copies found, spacing agrees
  across X%, down Y%)」；間距不均的那句跟在後面。
* seed 不進 recipe（同 crop：原料不是結果）。
