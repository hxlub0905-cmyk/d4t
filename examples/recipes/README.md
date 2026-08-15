# 範例 recipe 庫 —— 先挑一個最像你的情況，再改參數

這裡每一份 `.json` 都是一條**可以直接跑**的完整流程（影像段 → 算法段 → ADC 判定）。
建議的用法：**不要從空白開始**。挑一份最接近你站點情況的，載進 Studio 之後
改參數、改分數門檻，存成你自己的 recipe。

在 Studio 裡：工具列「範例 recipe」→ 選一份 →「載入」。

> **目前只有一份。** F8 第五輪把 ROI 收斂成 Profile / Template / GDS 三條路，
> 舊的五份（`die_to_die_basic`、`dual_route_basic`、`rsem_golden_cell`、
> `single_image_rules`、`cd_gate`）全部依賴被拿掉的 `roi_define` / `blob_segment`，
> 使用者的決定是「**等 APP 完成再給範例**」—— 與其留五份載進來就報錯的檔案，
> 不如先留一份跑得動的。`tests/test_example_recipes.py` 守著「庫不可以是空的」。

---

## 對照表

| Recipe | 什麼情況用它 | 走哪條 route | 分數怎麼算 |
|---|---|---|---|
| `cross_regions.json` | **純規則的 ROI 定位**：不用 GDS、也不用 Golden Cell 模板，只看 patch 自己。適合圖上有兩組交叉條紋（例如 MG / EPI 的交界）的 layout。 | `ebi_patch` | 定不出位就 0 分，定得出來就取「缺陷那一塊」與「整組交會處」殘差最大值裡較大的那個：`locate_ok * max(here_glv_max, xing_glv_max)`，門檻 40。 |

練習資料：`python tools/make_sample.py <dir> --pattern lines`

---

## `cross_regions` 在教什麼（挑 recipe 之外的價值）

- **一組框，不是一個框。** 兩個方向各投影一次找出兩組條紋（直的、橫的），
  交會處就是要量的地方 —— 一張 patch 上通常有好幾處，數量還隨影像而異。
  所以 `roi_cross` 吐的是**一個名字配一組框**（而 `xing_center` 是離 patch
  中心最近的那一塊，也就是缺陷所在的那塊）。
- **定位只做一次、兩張圖共用。** 框在 ref 上找（那裡沒有缺陷來干擾定位），
  test 與 ref 量同一組框 —— 所以兩者的差只來自缺陷。
- **影像段的骨架**仍然在裡面：正規化 → 對位 → 相減 → 量測。
  沒有 `diff` 就沒有東西可量，這是三段式的基本形狀。
- **定位失敗要進得了分數。** `roi_cross` 定不出來時會退回整張圖並把
  `locate_ok` 標成 0，而分數式子把它乘在最前面 —— 所以「沒定位到」的那幾顆
  拿 0 分，不會混進「量出來很乾淨所以低分」裡面。

---

## 改的時候注意

- **幾何類參數要跟著影像尺寸走。** 具名 ROI 存的是 0–1 比例座標，所以框本身
  換尺寸不會失效；但以像素為單位的參數（SNR 視窗 `window`、`exclude_border`、
  `pitch`）不會自己縮。同一份 recipe 要吃兩種尺寸的圖時，那幾個要各放一個節點。
- **門檻先看直方圖再決定。** 試跑之後直接在直方圖上拖那條線，bin 數會即時
  跟著變；覺得對了再放開滑鼠套用。
- **分數表達式的變數 = 上游卡片產出的特徵名。** 用分數編輯頁的
  「插入特徵 ▾」挑，不會打錯字。
- 改完存成自己的檔案（工具列「存 Recipe…」），**不要覆蓋這裡的範例** ——
  `tests/test_example_recipes.py` 會對每一份範例做驗證與實跑，改壞了測試會紅。
