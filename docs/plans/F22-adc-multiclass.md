# F22 — 多類別 ADC

> 狀態：**引擎完成（2026-08-23）。畫布那一半還沒做，而且有一個開放問題（§6）。**
> 起點：ADC 段是整個 app 最大的功能缺口 —— 一個叫 Auto Defect **Classification**
> 的工具，`score.bins` 卻被強制只有 `below` / `above`，只分得出兩類。

---

## 1. 形狀

```json
{
  "let": [
    {
      "name": "contrast",
      "expr": "cmp_delta_median * cd_deq"
    },
    {
      "name": "brightness",
      "expr": "glv_mad"
    }
  ],
  "rules": [
    {
      "when": "cd_deq_missing > 0",
      "bin": 9,
      "label": "not measurable"
    },
    {
      "when": "contrast > 120",
      "bin": 3,
      "label": "big particle"
    },
    {
      "when": "contrast > 30",
      "bin": 2,
      "label": "particle"
    },
    {
      "when": "brightness > 6",
      "bin": 1,
      "label": "faint"
    }
  ],
  "otherwise": {
    "bin": 0,
    "label": "nuisance"
  },
  "score": "contrast"
}
```

實跑 48 顆（`F21-algo-and-roi.md` 那份 recipe，把 `Feature math` 拔掉、算式搬進
判定段）：

| bin | 類別 | 總數 | 真缺陷 | 假的 |
|---:|---|---:|---:|---:|
| 9 | not measurable | 1 | 0 | 1 |
| 3 | big particle | 11 | **11** | 0 |
| 2 | particle | 16 | 13 | 3 |
| 1 | faint | 20 | 0 | 20 |

**這是這個 app 第一次分出兩類以上。** bin 3 純度 11/11。

---

## 2. 四個設計決定

### 2.1 由上往下，第一個成立的贏（一張篩子）

不是「每條算分取最高」。理由是使用者是不會寫 code 的製程工程師（推廣鐵則）：

> 「由上往下，第一個對上的就是答案」是一句他讀得懂、而且**改順序就等於改優先
> 權**的規則。算分取最高要他同時想像好幾條分數線的相對高度，而那件事在畫面上
> 畫不出來。

驗收：`test_reordering_the_rules_changes_the_answer`。

### 2.2 `let` 的中間值是**真的特徵**

每一行算完寫進 `ctx.features` → 進 CSV、進報表，使用者畫得出它的分布
（F19 的規矩）。後面一行看得到前面一行。

**這正是 `feature_math` 存在的唯一真理由**（「一份 recipe 只有一條表達式，中間值
沒有地方放」）—— 而在這裡它不必是一張卡。所以 F21 §5.3 留的那個題目
（「把算式子搬進 ADC，讓 `feature_math` 被吸收」）**引擎這一半已經成立**：
實跑的那份 recipe 就是把 `Feature math` 拔掉、算式搬進 `let` 的。

⚠ **但還不能刪 `feature_math`** —— 見 §5。

### 2.3 不用學第二套語法

比較運算子本來就回 1.0／0.0（`expression.py` 的左結合折疊），所以
`"(a > 5) * (b < 2)"` 就是 AND、`"a > 5"` 就是一條規則。判真假的規矩是一句話：
**非 0 就是成立**。

### 2.4 `score` 還是 `score`

`decide.score` 算完寫進 `features["score"]` —— 跟老路一字不差，所以 KLARF 的
DSIZE、Top-N 排序、CSV 的 score 欄**都不必知道這一段換過**。

---

## 3. 為什麼是「嚴格附加」而不是取代

`decide` 不在 → `_eval_score` 的第一行就分岔，老路**一個位元都沒動**；
`to_json_dict` 也不會長出 `decide` 這個鍵。

理由不是保守，是**黃金值從 F19 起就是壞的**（`F21-algo-and-roi.md` §6）——
沒有那條防線的時候，「改了判定段但既有的數字沒變」這句話沒有人證得了。
目前唯一守著它的是 `test_an_old_recipe_round_trips_without_growing_a_decide_key`。

**兩種寫法不能並存**：`validate` 把「兩個都寫」判成 `ambiguous-decision` 的
error，而不是挑一個贏。同一件事兩個地方存是這個 repo 最怕的形狀 —— 挑一個贏的
話，另一份會安靜地漂，而使用者改了沒用的那一份時畫面上看不出來。

---

## 4. 還沒做的

| | 東西 | 為什麼還沒做 |
|---|---|---|
| **UI** | Studio 的判定面板還是「一條表達式 + 一個門檻」 | 引擎先做完才知道面板要長什麼樣 |
| **label 進 CSV** | `label` 目前只在 `ctx.meta["decide"]` | 那會動到 SQLite schema 與 CSV 的欄，而 export parity 是逐位元組比的 —— 黃金值壞著的時候不動序列化 |
| **ground truth 的比對** | `run --ground-truth` 仍然是二元的（bin≠0 = 抓到） | 多類別的正確率要先定義「對」是什麼（同一類？同一群？） |
| **遷移** | 舊 recipe 不會自動變成 `decide` | 鐵則 9 的遷移要靠「舊東西在不在」，而這一步要等 UI 有地方顯示結果 |

---

## 5. 為什麼還不能刪 `feature_math`

`let` 在引擎上已經取代得了它，但**兩件事還沒成立**：

1. **UI 還沒有 `let` 的編輯器** —— 現在只能手寫 JSON。刪掉卡片等於把那個能力
   從 Studio 上拿掉。
2. **F21-B 的挑選器只做在卡片與 score 那一格上** —— `let` 那幾行也要有同一支
   「插入數字 ▾」，不然使用者又回到「得知道 `cmp_delta_median` 這個名字」。

判準照 `CLAUDE.md` 的那張表：**不確定的時候先收起來，成本是零。** 等 UI 做完、
使用者確認 `let` 比卡片好用，再決定是收起來還是刪掉。

---

## 6. 開放問題：ADC 要不要有線 —— **已定稿（2026-08-24），見 F24**

> 答案：判定整棵**住在畫布上**（菱形步驟樹＋托盤葉子＋分支流量），
> 數字不畫常駐的線、用幽靈線答來源。完整定稿在
> [`F24-decision-tree.md`](F24-decision-tree.md)。以下保留當時的思路。

### 當時的思路（歷史）

使用者 2026-08-23：「**我覺得 ADC 也可以有線啦（但我們再來討論）**」。

F21 §5.3 我主張「ADC 吃的是全部，所以不需要埠」（借 F17 對 Output 卡講的話）。
**多類別之後那個論證有漏洞**：每條規則吃的是**特定幾個**數字，不是全部 ——
那時候線是有意義的。

而 F21 §5.2 記的兩個重啟條件，其中一條現在正在逼近：

> 一份 recipe 用到 3 張以上 Algo 卡；或出現兩張同型別的量測卡撞名。

多類別會讓「這條規則吃哪幾個數字」變成一個使用者天天要問的問題。所以這一題
要在 UI 那一輪一起決定，而不是先做完面板再回頭補。

⚠ 決定之前要記得的兩件事（F21 量過的）：
* **特徵不跟線跑**（`engine._local_view` 只有 `images` 是每張卡自己的）——
  現在畫的線會是「說明」不是資料流。
* 要它說實話，引擎得先給特徵作用域，而那會動到 CSV 欄名 → SQLite → 黃金值。
