# F115：OP-301 廠外驗證的結果與三處修正

**狀態：** 已收斂（2026-09-18）—— 2.1～2.6 六項全部做完，測試綠，
所以這一份直接進封存。⚠ **但最後一節那個問題是開放的**：機台方一回答，
array 區那條路可能整條換掉。答到之前不要再調參數 —— 那句話同時寫在
[`USING-FOCUS.md`](../../USING-FOCUS.md) §5，而那裡才是使用者會讀到的地方。

---

## 這是什麼

2026-09-18，使用者在一個隔離環境裡拿**兩批真實機台檔**（共 23 張，每張帶著
機台自己算的 F.I. 真值）跑了一次 d4t 的 CLI，回來一份驗證報告。這一輪把那份
報告裡**能落成程式碼與文件的部分**做掉。

⚠ **那些影像不能進 repo（鐵則 8），而這台機器上也沒有它們。** 所以：

* 報告裡的每一個相關係數、殘差、校正常數都是**唯讀的事實** —— 照抄進文件，
  不四捨五入、不「改好看一點」；
* 這一輪**每一行新程式碼的驗收都是合成資料**（`tests/iqi_fixtures.py`）；
* **重驗只有資料的擁有者做得到。**

量到的東西住在 [`USING-FOCUS.md`](../../USING-FOCUS.md)（使用者面）與
`d4t/core/algo/iqi.py` 的模組說明（演算法面）。這一份不抄第二遍。

---

## 做了什麼（對照原提案的六項）

| # | 事情 | 落在哪 |
|---|---|---|
| 2.1 | 兩個 ASSUMPTION 寫進實測答案：`noise_percent` 是站點參數（logic 區要留 0，開到 20 就從 r 0.959 崩到 0.06）；前 30% 與梯度預篩在 array 區是 no-op（前提不成立，不是 bug）| `d4t/core/algo/iqi.py` 模組說明 |
| 2.2 | `focus_quality` 多一格 `Measure on`（`pixel` / `gradient`，預設 `pixel`）；`algo/iqi.py` 的 `focus_index(domain=…)` 與抽出來的 `gradient_magnitude()`；兩顆新膠囊圖 | `steps/quality.py`、`algo/iqi.py`、`ui/glyphs.py` |
| 2.3 | `.raw` **先讀檔頭再猜大小**：`layout_from_header()` 三道關（`W,0,H,0` 簽名、邊長範圍、大小逐位元組吻合），`guess_layouts(path=…)` 讀得懂就只回那一個 | `core/ingest/rawfile.py`、`ui/open_dialogs.py`、`__main__.py` |
| 2.4 | 校正流程（`GT = a × FI + b` 擬合 → 寫進判定段的 `Working numbers`，**不必加卡**）＋ 兩組量到的常數 ＋ 不跨機台的警告 | 新的 [`USING-FOCUS.md`](../../USING-FOCUS.md) §4 |
| 2.5 | 兩列坑：指標的適用性由**區域型態**決定；u16 的動態範圍決定**降位法** | [`PITFALLS.md`](../../PITFALLS.md) 末兩列 |
| 2.6 | 兩個合成產生器（logic／array）＋ 十條斷言（含「pixel 逐項不變」那道黃金值守門）| `tests/iqi_fixtures.py`、`tests/test_iqi.py`、`tests/test_raw_input.py` |

---

## 兩處**刻意跟提案不一樣**的地方（都寫在程式碼裡了）

1. **梯度不拉 `cv2.Sobel`，用模組自己那一份。** 提案寫
   `cv2.Sobel(CV_32F)`；`iqi.py` 是純 numpy 的（它連 Sobel 都自己寫），而
   `pattern_density` **本來就已經**在算同一張梯度圖。再養一支的話同一個模組裡
   會有兩個「梯度」，那兩個遲早不一樣。所以把既有那一份抽成
   `gradient_magnitude()`，兩個下游共用。
   差別只在邊界處理（edge padding vs reflect）與 float64 vs float32 ——
   落在最外面那一圈像素上。
   ⚠ **代價要講出來**：廠外量到的 0.49 / 0.9596 是**另外兩個變體**
   （機台 A 那個不切塊、機台 B 那個把 Gx/Gy 分開帶通再相加），所以**出貨這條路
   在真資料上的相關係數還沒有人量過**。那句話寫在 `USING-FOCUS.md` §2。

2. **合成產生器放 `tests/iqi_fixtures.py`，不放 `tests/fixtures/`。**
   後者是**資料**（recipe、黃金值、KLARF 樣本），而這兩個是**共用工具** ——
   這個 repo 對那種東西已經有一個家：`tests/region_cards.py`。

---

## 還沒問到的那一句話（**這一份留著的理由**）

> **機台 A 的 F.I. 是在哪一個影像階段算的？它的正規化會不會跟同一批的其他張
> 有關？**

只有機台方答得出來。在那之前：

* **不要為 array 區另外加一張量測卡** —— 答案可能會把整條路換掉；
* **不要繼續調參數** —— 整份網格已經掃過，最高 0.31；
* `Measure on` = `Its edges` 是一個**起點**（0.49），不是終點。
