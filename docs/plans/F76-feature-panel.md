# F76 — Feature 面板：一張平表裝不下一個立方體

**狀態：提案，等使用者挑方向。** 開工 2026-09-02。

使用者：「目前 feature 顯示面板跟後面帶的數值我覺得好亂，你覺得可以怎麼改進
（我可以接受大改）」。

---

## 0. 先量一次（`recipes/rsem-worst-box.json`，出貨的那一份）

不是感覺亂，是**真的裝不下**。那份 recipe 攤在 `FeatureTable` 上是：

| | 數字 |
|---|---|
| 特徵總數 | **118** |
| 其中 GLV 那一張卡自己產出的 | **75** |
| 說明欄（What it is）**只是把 id 抄一遍**的 | **36** |
| 說明欄**跟別的特徵一字不差**的 | **97** |
| 名字裡區域名出現兩次的 | 9 |
| 同一個區域在同一張表上被畫成**兩種顏色** | 2 個區域 |

重現（不必開 GUI）：本輪用的稽核腳本在 §6。

---

## 1. 五個病，照嚴重度排

### ① 顏色指錯區域 —— 這是 bug，不是設計問題

`CLAUDE.md` §3 寫著「**顏色指錯區域比沒有顏色糟得多**」，而現在就是：

```
region              產出它的卡        region_index   顏色
on_pattern          roi_reference     0              #5fd0a0  綠
between_columns     roi_reference     0              #5fd0a0  綠   ←
between_rows        roi_reference     0              #5fd0a0  綠   ←
on_pattern          glv_stats         0              #5fd0a0  綠
between_columns     glv_stats         1              #f0b429  琥珀 ←
between_rows        glv_stats         2              #7aa7ff  藍   ←
```

同一個 `between_columns`，在 Region 卡那一組是**綠**、在 GLV 卡那一組是**琥珀**
—— 而影像上那個 ROI 框只有一種顏色。使用者照顏色找「這個數字是量哪一塊」會
被帶到另一塊去。

原因：`region_index` 是**每張卡各自從自己的參數算**的序，而 Region 卡對自己
寫出去的 `<name>_present` 那一族一律記 0（它一次只定義一個區域，自己的序當然
是 0）。GLV 卡接了三條區域線，序是 0/1/2。兩份說法，鐵則 10 擋的正是這個。

**修法**：序不能由卡片各自發明，要由**接線的那一份**給（`recipe.edges` 上區域
線的順序就是唯一的那份，跟影像上畫框用的是同一個來源）。這一條**跟面板長什麼
樣無關，先修**。

### ② 說明欄對 GLV 的主力模式整欄失效

`feature_gloss` 只看 `spec.metric`，**不看 `spec.variant`**。於是：

```
glv_median_typical      median(gray)      ← 這一批單元的中位數
glv_median_outlier      median(gray)      ← 離它最遠那一格的值
glv_median_outlier_box  median(gray)      ← 這是第幾格（一個框號！不是灰階）
glv_median_worst        median(gray)      ← judge 挑的那一格的值
```

四個不同的數字，說明欄四行一字不差；而第三行**根本不是灰階**，它是 0 起算的
框序號。那一欄本來是 F18 補課「不必先背命名規則」的答案，在 each box 模式下
它對 36 列裡的 36 列都在說謊。

### ③ 使用者現在在問的那幾個字，表上沒有解釋

`glv_worst_score` 的說明欄寫的是 `glv_worst_score`。`glv_worst_value`、
`glv_worst_score_median`、`glv_worst_score_spread`、`glv_boxes_over_k_frac`、
`glv_boxes`、`glv_worst_i/x/y/w/h` 全部一樣 —— 36 列在原地打轉。

`metric_formula` 只認得統計量（它們不是），`_ABS_GLOSS` 只有兩條。而
`Step.feature_help()` 這條路**已經存在**（2026-09-01 建的，`_card_says` 在用）
—— GLV 卡沒有替 worst 那一族填而已。**這一條是最便宜的一刀**。

### ④ 平表裝的是一個三維立方體

GLV each-box 產出的是 **區域 × 統計量 × 身分** 的乘積：

```
3 區域 × 3 統計量 × 4 身分(typical/outlier/outlier_box/worst) = 36 列
3 區域 × 13 個「贏家那一格」的數字                            = 39 列
```

表格把它攤成 75 個長字串，而每一串裡真正在變的只有最後一段
（`between_columns_glv_median_` 這 25 個字元出現 25 次）。眼睛得逐字比對前綴
才知道自己站在哪一格。

分組（`sections`）只分到「哪張卡」為止 —— GLV 那一組就是 75 列。

### ⑤ 值那一欄沒有量綱

同一欄、同一個 `%.5g`、同一種右對齊，裝的是：

| 值 | 其實是 |
|---|---|
| `128.4` | 灰階 0–255 |
| `4.83` | **σ**（幾倍的鄰居散布） |
| `612` | 像素座標 |
| `37` | 框號 |
| `1` | 布林旗標 |
| `0.982` | 比值 |
| `625` | 計數 |

所以「27.753 是大是小」讀不出來 —— 那正是「後面帶的數值好亂」。
`ParamSpec` **早就有 `unit`**（`over_k` 那格寫著 `unit="σ"`），
`FeatureSpec` 沒有。

---

## 2. 提案（四刀，每一刀各自可驗收）

### 刀 1 ── `FeatureSpec` 加 `unit` 與 `variant` 的說明（core，改一次，全 UI 受惠）

* `FeatureSpec.unit`：`"gray"` / `"px"` / `"σ"` / `"box"` / `"count"` /
  `"ratio"` / `"flag"` / `""`。**在名字誕生的地方宣告**（`base_specs` 那幾行
  手上就有），不在 UI 猜。
* `feature_gloss` 吃 `spec.variant`：四胞胎各自一句話，而 `outlier_box`
  的單位是 `box` 不是 `gray`。
* GLV 卡的 `feature_help()` 補上 worst 那一族（§3 那幾句直接搬）。

驗收：`test_ui_widgets.py` 加一條 —— **每一個 registry 產得出的特徵，說明欄
不得等於它自己的 id**（反向測試，例外清單要配一支「例外修好了沒從表上拿掉」
的測試，照 `CLAUDE.md` §1 的規矩）。

### 刀 2 ── 修區域顏色的序（§1①）

序由區域線給，一份出處。驗收：同一個區域名在同一份 recipe 的任兩張卡底下
拿到同一個 `region_index`。

### 刀 3 ── 分組再深一層：卡 › **區域**，而「贏家那一格」升格成標題

現在的標題是 `GLV · 75`。改成三段，每段的標題**自己就是那一段的結論**：

```
▾ GLV › on_pattern            worst #37 · 4.8σ · 625 boxes · 2 over 3σ
      median      typical 128.4   odd 96.2 (#37)   worst 96.2      gray
      mean        typical 127.9   odd 99.1 (#37)   worst 99.1      gray
      std         typical   4.2   odd 11.8 (#12)   worst  6.0      gray
▸ GLV › between_columns       worst #4 · 1.2σ · 625 boxes
▸ GLV › between_rows          worst #88 · 3.1σ · 625 boxes
```

兩件事同時發生：

* **四胞胎從四列變成一列四欄**（36 列 → 9 列）。它們本來就是同一個量的四種
  身分，攤成四列是把「同一件事」講了四遍。`outlier_box` 回到它該在的位置
  —— 一個**地址**，貼在它定位的那個值旁邊（`96.2 (#37)`），不佔一列。
* **`glv_worst_*` 那 13 個從列變成標題那一行**。它們回答的是「這一區的結論
  是什麼」，而那是一個人打開這一段時的第一個問題；座標 x/y/w/h 是給疊圖用的，
  收在標題的 tooltip 裡。

75 列 → **3 個標題 + 9 列**（展開一區時）。

⚠ 這一刀要注意 `CLAUDE.md` §4 那條：**新的面板一律開新模組**。四欄那一段
不塞進 `widgets.FeatureTable`（那份檔案已經 6,928 行），開 `ui/feature_panel.py`。
而 F50 的教訓也適用 —— **先問那一塊該不該是一塊**：這裡的答案是「該」，因為
分的依據（哪張卡 / 哪個區域）是引擎本來就記著的事（`feature_owner` ＋
`spec.region`），不是畫上去的框。

### 刀 4 ── 預設只顯示「有人在用的」，其餘收在一顆鈕後面

118 列裡，決定這一顆判成什麼的通常是 1–3 個。現在那幾個只有 accent 底色，
其餘 115 列照樣要滾過去。

* 預設顯示：分數表達式／判定樹用到的（`highlight` 已經算好了）＋
  `diagnostic_alarms` 亮起來的 ＋ 每一區的標題行。
* 一顆 `Show all 118` 與一格搜尋框（打 `worst` 就只剩 worst 那一族）。

驗收：`highlight` 是空的（多數樹沒有分數表達式）時**不可以整張表變空** ——
退回「全部顯示」，並在鈕上講出為什麼。

---

## 3. 順便：那四個字到底是什麼（要寫進 `feature_help()`）

（GLV 卡開「Boxes in the region = each box」才有這一族。這個模式的問題是
**「這幾百格裡哪一格跟別人不一樣」**。）

| 名字 | 一句話 | 單位 |
|---|---|---|
| `<量>_typical` | 每一格各自算完之後，**取中位數** —— 「這一批單元長什麼樣」 | 跟該統計量相同 |
| `<量>_outlier` | 離 typical **最遠**那一格的值。「最遠」跟著 `direction` 走（both = 絕對值、darker = 只看比較暗的、brighter = 反之） | 同上 |
| `<量>_outlier_box` | 上一格**是第幾格**（0 起算） | box |
| `<量>_worst` | **judge 挑的那一格**的這個量 | 同上 |
| `glv_worst_score` | 贏家那一格的異常度，**單位是 σ**：`\|v − 鄰居中位數\| ÷ (1.4826 × 鄰居 MAD)`，底線 1 灰階。鄰居 = **除了自己以外的所有格**（leave-one-out，異常格連自己那一票都不投） | σ |
| `glv_worst_value` | 贏家那一格的 **judge 統計量**的值（judge 預設 `glv_median`） | 跟 judge 相同 |
| `glv_worst_i / x / y / w / h` | 贏家是第幾格、它在整張影像的哪裡（就是那一格 ROI 自己，不另外量） | box / px |
| `glv_worst_score_median` / `_spread` | **逐框異常度那條分布**的中心與寬度 —— 「一格特別怪」vs「500 格都一樣怪」靠它分 | σ |
| `glv_boxes_over_k` / `_frac` | 超過 `over_k` 個 σ 的有幾格 / 佔幾成 —— 同上那個分辨，答得更直接 | count / ratio |
| `glv_boxes` | 真的量得出來的有幾格（太小的格會跳過，不是寫 0） | count |
| `score`（裸的，表最下面粗體那一列） | **ADC 分數表達式的結果** —— 跟上面整族沒有關係 | — |

### ⚠ `_outlier` 與 `_worst` 不一定是同一格

* `_outlier` 照**這個量自己**挑（median 的最極端格）；
* `_worst` 照 **judge**（那一格「Pick the odd one by」）挑，整張卡共用一個贏家。

judge 選 `glv_median` 時，`glv_median_outlier` 與 `glv_median_worst` 幾乎總是
同一格 —— 但 `glv_std_worst` 是「**median 最怪的那格**的 std」，不是「std 最怪
的那格」。

### ⚠ `score` 這個字在同一張表上有兩個意思

`glv_worst_score`（逐框異常度，σ）與最後一列的 `score`（ADC 分數）。
而 `glv_worst_score_median` 讀起來像「分數的中位數」。
`CLAUDE.md` §0 的 **bundle** 故事講的正是這件事：會混淆的是**人**，
而下一個含糊的名字不會剛好自己消失。

**這一輪不改名**（`glv_worst_*` 是分數表達式裡的變數，改名要一道遷移，而
F37 才剛付過一次這筆錢）。刀 1 的說明欄與刀 3 的區段標題把兩者在**畫面上**
分開 —— 如果之後使用者仍然會混，再量改名的代價。

---

## 4. 順序與代價

| 刀 | 動到 | 風險 | 值 |
|---|---|---|---|
| 1 說明欄 ＋ `unit` | core 的 `FeatureSpec`、GLV 卡的 `feature_help`、`feature_gloss` | 低（顯示層，數字不動） | 36 列從打轉變成一句話 |
| 2 區域顏色的序 | 區域線 → `region_index` 的那一支 | 低，但**要跑黃金值** | 修掉一個會把人帶錯的 bug |
| 3 卡 › 區域 ＋ 四欄 | 新模組 `ui/feature_panel.py` | 中 | 75 列 → 3 標題 + 9 列 |
| 4 預設只顯示在用的 | 同上 | 低 | 118 → 通常 3–5 |

刀 1 與刀 2 彼此獨立、也跟 3/4 獨立 —— **先做這兩把**，畫面就已經不說謊了；
3/4 是「不必滾」，可以之後再談要不要做成這個樣子。

⚠ 動任何一刀之前先 `python tools/freeze_golden.py --check` 三份全綠
（`CLAUDE.md` §4）。

---

## 5. 沒有選的路（記下來，免得下次再想一遍）

* **在 UI 拆特徵字串把 variant 猜回來** —— F51 剛把這種猜法清掉。variant
  `spec` 上早就有，用它。
* **把 `<量>_outlier_box` 改名成不像灰階的名字** —— 要遷移，而刀 1 的單位欄
  已經把話講清楚了。名字是 recipe 的鍵，貴的那一邊先不動。
* **在 `widgets.py` 裡加第四欄** —— 那份檔案 6,928 行，而 `CLAUDE.md` §4
  那條規矩就是為了這一刻寫的。
* **把 `glv_worst_*` 收進 `diagnostic_features`**（讓它預設收起來）——
  它們不是診斷，它們正是 F68 那張卡的主要輸出。刀 3 的標題行才是它們的位置。

---

## 6. 稽核腳本（重現 §0 那張表）

```python
import json, d4t.core.steps
from d4t.core.pipeline import get_step
from d4t.core.pipeline.recipe import Recipe
from d4t.ui.widgets import feature_gloss
from d4t.ui import theme

r = Recipe.from_json_dict(json.load(open("recipes/rsem-worst-box.json")))
specs, echo, dup = {}, [], {}
for nid, n in r.nodes.items():
    st = get_step(n.step); p = st.validate_params(n.params)
    for s in st.resolve_feature_specs(p):
        specs.setdefault(s.name, s)
        print("%-22s %-16s index=%d %s" % (s.region, st.key, s.region_index,
                                           theme.region_hex(s.region_index))
              if s.region else "", end="")
for name, s in specs.items():
    _kind, g = feature_gloss(name, {}, s)
    if g in (name, s.metric, s.base):
        echo.append(name)
    dup.setdefault(g, []).append(name)
print(len(specs), "features;", len(echo), "gloss = its own id;",
      sum(len(v) for v in dup.values() if len(v) > 1), "share a gloss")
```
