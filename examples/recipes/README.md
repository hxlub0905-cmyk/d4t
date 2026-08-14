# 範例 recipe 庫 —— 先挑一個最像你的情況，再改參數

這裡每一份 `.json` 都是一條**可以直接跑**的完整流程（影像段 → 算法段 → ADC 判定）。
建議的用法：**不要從空白開始**。挑一份最接近你站點情況的，載進 Studio 之後
改參數、改分數門檻，存成你自己的 recipe。

在 Studio 裡：工具列「範例 recipe」→ 選一份 →「載入」。

---

## 先回答三個問題，就知道要挑哪一份

1. **有沒有可以拿來比對的參考圖（ref）？**
   機台的 die-to-die patch 通常會附一張 ref；Review SEM 單張通常沒有。
2. **沒有 ref 的話，圖上有沒有重複的 cell 圖案？**
   有的話可以把重複的 cell 疊成一張乾淨的「Golden Cell」自己當 ref。
3. **你要用什麼決定「這顆重不重要」？**
   殘差有多亮（灰階）？還是缺陷有多大（CD 尺寸）？

---

## 對照表

| Recipe | 什麼情況用它 | 走哪條 route | 分數怎麼算 |
|---|---|---|---|
| `die_to_die_basic.json` | **最常見的起點**。機台有給 ref 的 die-to-die patch，想先把假點濾掉。 | `ebi_patch` | 對位相減後，**中心 32 px 方框內差異圖的最亮值**，再加上「最亮值比 99 百分位高多少」當尖銳度加權：`glv_max + (glv_max - glv_q99)`，門檻 50。 |
| `dual_route_basic.json` | 同一套判定標準要**同時吃兩種輸入**（機台 patch 與 Review SEM），不想維護兩份 recipe。 | `ebi_patch` + `rsem` | 中心區差異圖的**無量綱對比**：`(glv_max - glv_median) / (glv_std + 0.5)`，門檻 4.2。無量綱 → 兩條 route 可以共用同一個門檻。 |
| `rsem_golden_cell.json` | **只有單張 Review SEM、沒有 ref，但圖上有重複的 cell**。 | `rsem` | 量出 cell 週期 → 疊出 Golden Cell 當 ref → 相減；分數就是**中心區殘差的最大值** `glv_max`，門檻 30。自己減自己，亮度／對比飄移會抵消，不必先做正規化。 |
| `single_image_rules.json` | **既沒有 ref、圖上也沒有週期性**可以疊 Golden Cell 的保底作法。 | `ebi_patch` + `rsem` | 直接在原圖上算局部訊號突出度，三條規則相乘：**訊號要強 × 塊要夠大 ÷ 離報點位置要近**，前面再加一道對焦閘（模糊的圖直接 0 分）：`(focus_lapvar > 100) * snr_max * blob_area / (blob_dist_center + 5)`，門檻 0.16。 |
| `cd_gate.json` | 站點對「**多小的缺陷可以放過**」有明確規格，要用尺寸而不是亮度做決定。 | `ebi_patch` | 先用中心區殘差當閘門確認「這是真的」，過關的才用缺陷尺寸算分：`(glv_max > 30 and cd_x_px > 2) * max(cd_x_px, cd_y_px)`，門檻 3 —— **門檻的單位就是像素**，填你在意的最小缺陷尺寸。 |

---

## 每一份在教什麼（挑 recipe 之外的價值）

- **`die_to_die_basic`** —— 標準的影像段五連：正規化 → 對位 → 相減 → 去噪 → SNR 地圖。
  沒有 ref 就沒有 `diff`，後面整段算法都動不了；這是三段式的骨架。
- **`dual_route_basic`** —— 一份 recipe、兩條 route。兩條路共用同一批算法節點，
  **只有和影像尺寸有關的幾何參數（中心框大小）各自一個節點**。
  這是踩過的坑：同一組 `box_size` 在 128² patch 上準、在 256² 上會漏抓。
  分數改用無量綱式子，兩條路才能共用一個門檻。
- **`rsem_golden_cell`** —— 「沒有 ref 就自己造一張」。`cell_period` 量週期、
  `golden_cell` 疊圖，之後就完全回到 die-to-die 的老路。也示範了
  **不是每條流程都需要正規化與對位**（Golden Cell 天生對齊、亮度天生一致）。
- **`single_image_rules`** —— 不用參考圖也能給分：把工程師口頭的判斷條件
  （「訊號要明顯、東西要夠大、要在報點附近」）直接寫成一條乘法算式，
  再用比較運算子做閘。**這是準確率最低的一條**（合成資料上約九成，
  而且很吃參數），只在前面兩條路都走不通時當保底。
- **`cd_gate`** —— 分數不一定要是無單位的「可疑度」，**也可以是有物理單位的量**。
  分數 = 缺陷寬高（像素），門檻 = 規格。另外示範 `blob_segment` 可以直接切
  `diff`，不一定要先做 SNR 地圖。
- **`cross_regions`** —— **純規則的 ROI 定位**：不用 GDS、也不用 Golden Cell
  模板，只看 patch 自己。兩個方向各投影一次找出兩組條紋（直的、橫的），
  交會處就是要量的地方 —— 一張 patch 上通常有好幾處，所以
  `roi_cross` 吐的是**一組**框（而 `xing_center` 是缺陷所在的那一塊）。
  也示範了**定位只做一次、兩張圖共用**：框在 ref 上找（那裡沒有缺陷來干擾），
  test 與 ref 量同一組框，所以兩者的差只來自缺陷。
  練習資料：`python tools/make_sample.py <dir> --pattern lines`。

---

## 改的時候注意

- **幾何類參數要跟著影像尺寸走**（中心框 `box_size`、SNR 視窗 `window`、
  `exclude_border`、`min_area`）。同一份 recipe 要吃兩種尺寸的圖時，
  請像 `dual_route_basic` 那樣**每條 route 各放一個節點**，不要共用。
- **門檻先看直方圖再決定**。試跑之後直接在直方圖上拖那條線，
  bin 數會即時跟著變；覺得對了再放開滑鼠套用。
- **分數表達式的變數 = 上游卡片產出的特徵名**。用分數編輯頁的
  「插入特徵 ▾」挑，不會打錯字。
- 改完存成自己的檔案（工具列「存 Recipe…」），**不要覆蓋這裡的範例** ——
  `tests/test_example_recipes.py` 會對每一份範例做驗證與實跑，
  改壞了測試會紅。
