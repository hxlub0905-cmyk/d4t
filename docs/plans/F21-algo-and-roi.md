# F21 — Algo 段要不要存在，以及 ROI 到底值多少

> 狀態：**量完了（2026-08-23）**。Algo 段的決定寫在 §5，blob 的修法已經進去（§3）。
> 起點：使用者問「algo 這張 card 有沒有存在的必要」。

---

## 1. 為什麼是用量的，不是用想的

在這一輪之前，Algo 段的討論全部建立在推論上。而查 repo 得到的事實是：

| 東西 | 在任何 recipe 裡出現的次數 |
|---|---|
| `feature_math`（Algo 段唯一的卡） | **0** |
| 任何一張 ROI 卡（Region 段，已收斂） | **0** |
| `glv_stats` 的 compare（F18，一整輪） | **0** |

**三個收斂過的段落，零使用。** 所以先把它們串起來跑一次，再談要不要為 Algo 段加東西。

---

## 2. ROI 是槓桿，實測 +0.35

同一批資料（`make_mgepi_real.py`，48 顆，24 真 24 假）：

| | 沒有 ROI（原 fixture recipe） | 有 ROI（這一份） |
|---|---|---|
| 正確率 | 50.0% | **93.8%** |
| 誤殺率 | 95.8% | 12.5% |
| `glv_max` 的 AUC | 0.632 | **0.944** |
| 最好的特徵 | 0.686 | **0.995** |

特徵分離度（AUC = 隨機抓一真一假，真的排在前面的機率）：

```
  0.995 ↑  defect_score        ← Algo 卡的產出
  0.983 ↑  glv_mad
  0.976 ↑  cmp_delta_median    ← F18 的 compare
  0.941 ↑  cd_deq
  0.922 ↓  cross_dist_px       ← 見 §4，不採信
  ────── 其餘 34 個特徵 ≤ 0.55
```

---

## 3. 修掉的 bug：**ROI 框得越準，blob 越量不到**

症狀是反過來的，所以特別難查。

| ROI | `min_edge`（預設 0.5） | 量不到 | `cd_deq` 的 AUC |
|---|---|---|---|
| 緊框 `spacer_center`（4×8 px） | 0.5 | **92%** | 0.514 |
| 整張圖 | 0.5 | 2% | 0.564 |
| 緊框，**修好之後** | 0.5 | **12%** | **0.901** |

**根因**：`algo/shape._region_noise` 的空間項拿「外框那一圈」當背景的樣本。
4×8 的框，外框有 20 個像素、內部只有 12 —— 外框已經不是一圈邊，它就是這塊區域
本身。而一團 3 px 的東西在 4 px 寬的框裡**必然碰到外框**，於是它自己被算成
背景起伏：

```
逐點 σ    8.3     ← 真正的雜訊
外框 MAD  26.5    ← 被缺陷污染
用的 σ    取大的 → 26.5  → quality 0.35 < 0.5 → 判 "flat"
```

**修法**：`ring_is_a_border(shape)` —— 外框的像素超過整塊的一半時，它就不是
一圈邊，那時只用逐點估計。判準是**幾何**（外框會不會比內部多），不是調出來的
數字。

**沒有把低頻那條防線放回去**：它守的是大區域，驗收用 64×64（外框佔 6%），
規則對它恆為真。`test_the_wandering_background_guard_is_untouched_by_the_border_rule`
釘住這件事。

---

## 4. 一個不採信的數字

`cross_dist_px`（挑中的那一塊離 patch 中心多遠）AUC 0.922，而且**加進任何組合
都會變成 1.000**。

不採信，因為這批合成資料的假點是 `type: "none"` —— **完全沒有缺陷**。所以
「最強的訊號離中心很遠」幾乎就是 ground truth 本身。真實的 nuisance 是
「有東西但不重要」，不是「什麼都沒有」。§2 的所有結論都排除了它。

---

## 5. Algo 段的決定

### 5.1 它值多少（量出來的）

同一份 recipe，只差最後一張卡：

| | AUC | 最佳正確率 |
|---|---|---|
| 只用 `glv_mad`（最好的單一特徵） | 0.983 | 95.8% |
| 只用 `cd_deq` | 0.941 | 91.7% |
| **`cmp_delta_median × cd_deq`（Algo）** | **0.995** | **97.9%** |

**+0.012 → 576 對裡多排對 7 對。** 有用，但在 24×24 的樣本下不顯著。
而且**相乘（都要成立）比相加好** —— 那是使用者原本的直覺，方向是對的。

### 5.2 三個決定

**① 保留 `feature_math`，現在不做特徵線。** 理由：

* Algo 卡值 +0.012
* 畫布的缺口比想像小 —— 11 個節點只有 2 個沒線，而且它們的上游（glv / cd）
  **已經被區域線綁在一起了**（都指向 `spacer_center`）
* **特徵不跟線跑**（`engine._local_view` 只有 `images` 是每張卡自己的），
  所以現在畫的線會是「說明」不是資料流
* 成本要到引擎（特徵作用域 → CSV 欄名 → SQLite → 黃金值）

**重啟條件**（任一成立就回來做）：一份 recipe 用到 3 張以上 Algo 卡；
或出現兩張同型別的量測卡撞名，使用者分不出 Algo 卡吃的是哪一個。

**② 錢花在真正的痛點。** 實際用過一次之後，痛的順序跟猜的相反：

| | 痛點 | 實際 |
|---|---|---|
| 🔴 | **不知道有哪些數字可以用** | 必須跑 Python 呼叫 `resolve_features()` 才知道 `cmp_delta_median` 存在 |
| 🟡 | 量不到就整顆失敗 | 44/48 —— A1（`feature_fill`）已修 |
| 🟢 | 看不出數字從哪來 | 只有一張 glv 卡時一次都沒混淆過 |

所以要做的是**「可以點的數字清單」，而且做在 `expression` 的編輯器上、不是做在
`feature_math` 這張卡上** —— `score.expr` 有一模一樣的痛點，做在編輯器上兩邊都
受惠，而且不管 `feature_math` 之後是留是搬，這份投資都不會浪費。

**③ 判準寫死，Algo 段就不要再長了。**

> **式子寫得出來 → 不開新卡（用 `feature_math`）**
> **要看過整批才算得出來 → 才開新卡**

Algo 段最終形狀 = **三張卡**：`feature_math`（這一顆的數字互相算）、
`feature_fill`（量不到那一格）、`lot_stats`（要整批才算得出來的，未做）。

### 5.3 留給 ADC 的第一個設計題目

**在今天這份 recipe 裡，`feature_math` 其實沒有帶來任何價值** —— `score.expr`
打得出一模一樣的式子，而 `score` 本來就是 CSV 的一欄。

它的價值要等多類別 ADC 出現才成立（那時不會只有一條表達式，中間值才真的需要
有地方放）。所以 ADC 的設計要先回答一題：

> **把「算式子」搬進 ADC 那一段（好幾行的計算表），讓 `feature_math` 被吸收掉。**

那個位置有一個 `feature_math` 沒有的優勢：F17 對 Output 卡講過的話對 ADC 一字
不差地成立 —— 「它吃的是這一次跑的全部，沒有『哪一個』可以選，所以它不需要埠」。
**ADC 沒有線不是說謊，那是它的本質；`feature_math` 站在中間卻沒有線，那才是。**

---

## 6. 順手發現：黃金值從 F19 起就是壞的

`tools/freeze_golden.py --check` 現在會紅，而且**跟這一輪的改動無關**（把
`shape.py` 暫存起來再跑一次，一樣紅）。差異是 F19 改名留下的：
少了 `area_px` / `cd_x_px` / `cd_y_px`，多了 `cd_axis_deg` / `cd_bright` / `cd_n` …

也就是說 **「重構的驗收＝跟改動前逐項相同」這條防線，從 2026-08-21 起就沒有在守。**
CLAUDE.md 記著「⚠ 黃金值要在家用機重凍」—— 那筆待辦現在有代價了，
而且它擋在任何後續重構前面。

---

## 7. 用的 recipe

資料：`python tools/make_mgepi_real.py <目錄>`（固定種子，逐位元組可重現，不進版控）。

```json
{
  "recipe_id": "mgepi_roi_algo",
  "version": 1,
  "routes": {
    "ebi_patch": [
      "load",
      "norm_ref",
      "norm",
      "align",
      "sub",
      "roi",
      "glv",
      "cd",
      "snr",
      "fill",
      "algo"
    ]
  },
  "nodes": {
    "load": {
      "step": "load_patch",
      "params": {},
      "enabled": true
    },
    "norm_ref": {
      "step": "normalize",
      "params": {
        "streams": "ref",
        "range_from": "test",
        "method": "percentile"
      },
      "enabled": true
    },
    "norm": {
      "step": "normalize",
      "params": {
        "streams": "test",
        "method": "percentile"
      },
      "enabled": true
    },
    "align": {
      "step": "align",
      "params": {
        "method": "phase",
        "search_radius": 8
      },
      "enabled": true
    },
    "sub": {
      "step": "subtract",
      "params": {
        "b": "ref_aligned"
      },
      "enabled": true
    },
    "roi": {
      "step": "roi_cross",
      "params": {
        "source": "ref",
        "directions": "both",
        "vertical_select": "brightest",
        "horizontal_select": "brightest",
        "place": "beside_vertical",
        "box_size": 4.0,
        "side": "both",
        "gap": 1.0,
        "inset": 0.0,
        "roi_out": "spacer",
        "max_boxes": 64,
        "pick": "strongest",
        "pick_source": "diff",
        "drop_edge": true,
        "edge_margin": 4.0
      },
      "enabled": true
    },
    "glv": {
      "step": "glv_stats",
      "params": {
        "source": "diff",
        "roi": "spacer_center",
        "metrics": "glv_median,glv_max,glv_mad",
        "reference": "another region",
        "reference_region": "spacer_others",
        "stat": "glv_median",
        "compare_metrics": "delta,snr"
      },
      "enabled": true
    },
    "cd": {
      "step": "cd_measure",
      "params": {
        "shape": "blob",
        "source": "diff",
        "roi": "spacer_center",
        "threshold_pct": 50,
        "min_area": 2,
        "size_report": "cd_area_px,cd_deq,cd_feret_max,cd_feret_min"
      },
      "enabled": true
    },
    "snr": {
      "step": "snr_map",
      "params": {
        "window": 9,
        "exclude_border": 4
      },
      "enabled": true
    },
    "algo": {
      "step": "feature_math",
      "params": {
        "expr": "cmp_delta_median * cd_deq",
        "out": "defect_score"
      },
      "enabled": true
    },
    "fill": {
      "step": "feature_fill",
      "params": {
        "features": "cd_deq,cd_area_px,cd_feret_max",
        "fill": 0.0
      },
      "enabled": true
    }
  },
  "score": {
    "expr": "defect_score",
    "threshold": 10.0,
    "bins": {
      "below": 0,
      "above": 1
    }
  },
  "description": "把 roi_cross / glv_stats 的 compare / feature_math 第一次串起來的 recipe（F21 的量測用）。資料由 tools/make_mgepi_real.py 重產。"
}
```
