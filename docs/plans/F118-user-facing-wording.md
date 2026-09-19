# F118 — 使用者面的字：訊息不准講開發者的話（F117 J1／I11／J5／J6）

狀態：**進行中（2026-09-19）** —— 設計經使用者同意，**第 1 步做完**
（`ui/wording.py` ＋ 四個呼叫端，不動 core）。下一步是第 2 步
（`Issue` 加選配欄位）。§5 那 84 條文字斷言仍然是後面幾步真正的成本。

> F117 走查把這件事記成四條（J1 P1、I11、J5、J6）。它們是**同一個病根**，
> 所以收成一輪：[`F117-ui-review.md`](F117-ui-review.md)。

---

## 1. 為什麼

**推廣鐵則**（`CLAUDE.md` §1）：目標使用者是不會寫 code 的製程／設備工程師，
**任何讓他們看不懂或會爆錯誤訊息的設計都是 bug**。

而現在畫面上會出現這個（真的跑出來的，不是編的 —— 把分數表達式寫成
`glv_max + nosuch_feature`）：

```
[warning/unknown-feature] Score expression uses unknown features
route 'ebi_patch': the variables ['nosuch_feature'] are not among the features
this route produces (['cd_axis_deg', 'cd_bright', 'cd_edge_score', 'cd_lines',
'cd_max', 'cd_max_nm', 'cd_median', 'cd_median_nm', 'cd_min', 'cd_min_nm',
'cd_n', 'cd_std', 'cd_std_nm', 'clip_frac', 'glv_max', … 還有 20 幾個 …])
```

四個問題疊在一句話裡：

1. `route 'ebi_patch'` —— 使用者的 recipe **只有一條 route**，那個前綴對他沒有
   意義（而「route」是引擎的詞，不是他的）；
2. `['nosuch_feature']` —— **Python 的 list repr**；
3. 「這條 route 產出的特徵」把**全部**列出來，一行變五行，而他要找的是
   「我打錯的那個字最接近哪一個」；
4. 沒有一個字告訴他**去哪一張卡改**。

其餘三條同一個病根：

| 條目 | 現在長什麼樣 | 病根 |
|---|---|---|
| J1 | `Preview problem: [glv_stats] no input connected: 'source' is empty` | step **key** 與參數**名**，不是卡片名與欄位 label |
| I11 | `Removed “dn”` | node **id** |
| J5 | 問題清單一行一條、要水平捲動才讀得完 | 一句話塞三件事（見上面那段） |
| J6 | warning 太長，結論在最後 | 同上 |

---

## 2. 分析：漏在哪一層

**這一輪最重要的發現：結構其實都還在，是被字串吃掉的。**

| 產地 | 帶不帶得動結構 | 現況 |
|---|---|---|
| `recipe.Issue` | `code` / `level` / `node_id` / `title` / `detail` | `detail` 是**在 core 裡組好的散文**，裡面已經塞進 repr |
| `step.StepError` | `step_key` ＋ `detail`（**不含** `[key]` 前綴） | 它的說明就寫著「那句話是給使用者看的（推廣鐵則），不是給 log 看的」 |
| `engine.StepTrace` | `node_id` / `step_key` ＋ `error` | `error=str(e)` —— **把結構壓回字串，而 `node_id`/`step_key` 就在旁邊** |

換句話說：

* `StepError` 那一半**已經解決了**，UI 只是沒有用它 —— 現在畫面上那個
  `[glv_stats]` 是 `str(e)` 來的，而 `e.detail` 就是同一句話的乾淨版；
* `Issue` 那一半**沒有**解決：句子是在 core 組好的，UI 拿到時已經是散文。

### 63 個產地

```
d4t/core/pipeline/recipe.py   48
d4t/core/ingest/klarf_core.py 15
```

### 一句話服務兩種讀者

`StepTrace.error` 同時餵**狀態列**（人）與 `result_to_json_dict` → **CSV／報表**
（下游程式）。`[glv_stats]` 這個前綴對後者**有用**（機器讀得到是哪張卡），
對前者是雜訊。

**這個 repo 已經解過同一道題**：`d4t/core/numbers.py` 的說明寫著
「**畫面是給人讀的，資料檔是給下游程式讀的，兩件事**」—— CSV 保留全精度，
畫面走共用的格式化。F118 是同一條界線畫在「訊息」上。

---

## 3. 設計：誰翻譯

### 三個選項

| | 做法 | 問題 |
|---|---|---|
| **A** | UI 拿到 `detail` 之後做字串後處理（正則把 `['x']` 換成 `x`、把 `route '…'` 拿掉）| **對散文做正則**。句子一改就失效，而且失效的方式是**安靜的**（換回原樣，沒有人會發現）|
| **B** | core 直接把卡片名／label 組進句子 | core 要 import UI 的詞彙（`Step.label` 在 `core.pipeline.step` 上還好，但「只有一條 route 就不要講 route」是**畫面的判斷**，core 不知道使用者在看什麼）|
| **C** ✅ | **core 出結構化欄位，UI 組句子** | 要動 63 個產地 —— 但可以**逐步**做（見 §4），而且每一步都可驗 |

### 選 C，而且形狀已經有先例

`Issue` 加**選配**欄位（預設空，所以 63 個產地不必一次全改）：

```python
@dataclass
class Issue:
    code: str
    level: str
    node_id: Optional[str]
    title: str
    detail: str
    #: F118：給 UI 組句子用的結構化欄位。**空的就照舊用 `detail`**。
    subject: Optional[str] = None      # 這條在講哪一張卡的哪一格（param 名）
    names: Tuple[str, ...] = ()        # 句子裡要列出來的名字（UI 決定怎麼排版）
    suggest: Tuple[str, ...] = ()      # 「你是不是要打這個」（最接近的幾個）
    route: Optional[str] = None        # 哪一條 route；UI 只在**多於一條**時印
```

* **`detail` 不刪**：CLI（`d4t run` / lint）與測試照舊拿得到一句完整的話，
  而 CLI 的讀者本來就接受 `route 'ebi_patch'` 這種講法；
* **UI 有結構就用結構、沒有就退回 `detail`** —— 所以 63 個產地可以一個一個搬，
  每搬一個畫面就好一條，中途不會有「半好半壞」的破畫面。

### UI 那一側：一支 `wording.py`

新模組 `d4t/ui/wording.py`（Qt-free），**全 UI 只有這一支**在做這件事：

```python
def card(win_or_model, node_id) -> str      # "dn" → 「Denoise」
def field(step_key, param) -> str           # ("glv_stats","source") → 「Measure on」
def name_list(names, limit=4) -> str        # ('a','b','c','d','e') → "a, b, c and 2 more"
def issue_line(issue, model) -> str         # Issue → 一句使用者看得懂的話
```

為什麼是新模組而不是塞進 `problems_bar`：**狀態列、問題清單、參數表的錯誤、
Results 的 warning 四個地方都要用**，而那正是 F52（`numbers.py`）與 F116
（`canvas_edges.py`）反覆學到的同一課 —— 一件事只寫一個地方，抄第二份就會漂。

### 「只有一條 route 時不印 route」住哪

**UI**。core 不知道使用者在看哪一條、也不知道他的 recipe 有幾條在畫面上。
`issue_line()` 拿 `issue.route` 與 `len(model.routes)` 自己決定。

---

## 4. 步驟（一步一個 commit，可以停在任何一步）

| 步 | 做什麼 | 關掉 | 風險 |
|---|---|---|---|
| **1** ✅ | **做完**。`ui/wording.py`（Qt-free）＋ `card` / `card_of_step` / `field` / `name_list` / `trace_error_text` / `step_error_text`，接了**四**個呼叫端（多一個 `Preview: stopped after “dn”`）。實際畫面：`Removed “dn”` → **`Removed “Write report”`**；`Preview problem: [glv_stats] no input connected…` → **`Preview problem: “GLV”: no input connected…`** | **I11**、J1 的一半 | 低 —— 沒有動 core |
| **2** | `Issue` 加那四個選配欄位（預設空），UI 的 `issue_line()` 有就用、沒有就退回 `detail` | — | 低 —— 63 個產地一個都還沒改 |
| **3** | 搬**最常出現的 6 條** lint（`unknown-feature`、`ambiguous-input`、`duplicate-region`、`no-input`、`unknown-step`、`wrong-content`）填那四個欄位 | **J1** 主體、J5 | 中 —— 會動到 §5 那批文字斷言 |
| **4** | 問題清單改成兩行（結論在第一行、細節第二行）＋「帶我去」 | **J5**、**J6** | 低 |
| **5** | 剩下 42 條 lint 逐步填（可以分好幾輪，**不急**）| 尾巴 | 低 |

**第 1 步就會讓畫面明顯變好，而且它不動 core** —— 如果這一輪只做得完一步，
就做那一步。

### 第 1 步之後還剩什麼（實測）

那一句現在是 ``“GLV”: no input connected: 'source' is empty.`` —— **`'source'`
還在**，而那一段是 `engine.py` 在 core 裡組好的（`missing_inputs` 回參數名，
engine 把它們串成句子）。要變成「Measure on」只有兩條路：UI 對散文做正則
（§3 否決），或 core 把參數名**當欄位吐出來**讓 UI 自己組 —— 也就是第 2、3 步。
**這正是 §3 那一刀的價值：第 1 步能做的到此為止，而界線是清楚的，不是含糊的。**

---

## 5. 測試策略（這一輪真正的成本）

```
測試裡斷言在 code 上的    219 處   ← 不受影響
測試裡斷言在 detail/title  84 處   ← 要一條一條看
```

**84 條不是都要改。** 分三類處理：

1. **CLI／lint 的測試**：`detail` 沒有變（見 §3 的「`detail` 不刪」），**不動**；
2. **斷言「句子裡有某個關鍵詞」**（例 `"still needs" in …`）：多數仍然成立，
   因為新句子講的是同一件事；
3. **斷言整句**：改成斷言 `code` ＋ 結構化欄位。**那本來就是比較好的斷言** ——
   它問的是「這條 lint 判對了嗎」，而不是「這句話怎麼寫」。

⚠ **一條新測試要先加**：`issue_line()` 對**每一個** `code` 都給得出一句話
（沒填結構化欄位的就是 `detail`）—— 不然第 3 步搬到一半時，沒搬到的那些會
安靜地掉回原樣而沒有人發現。

---

## 6. 檢查清單（每一步）

- [ ] `ruff check`、`python tools/run_tests.py`（紅的要跟既有那 10 個檔案一樣）
- [ ] 三份黃金值（本機基準）逐項相同 —— 這一輪**不該**動到任何數字
- [ ] **真的開一次 Studio 看那幾句話**：刪一張卡、拉一條錯的線、把分數寫錯字，
      逐句唸出來問「一個不寫 code 的人看得懂嗎」
- [ ] `tests/test_size_ceilings.py` —— ⚠ `studio.py` 那一格**只准往下**，
      要在那裡加字就先搬走等量的東西（F116 第 5 步踩過）
- [ ] 訊息改寫之後 `python tools/i18n_todo.py` 會多出新句子 —— 這一輪**不翻**
      （H5 使用者決定先不碰），但要確認沒有句子繞過 `strings.tr()`

---

## 7. 風險

1. **對散文做正則的誘惑**（選項 A）。它一開始最快，而且**失效時是安靜的**。
   §3 選 C 就是為了這一條。
2. **一句話兩種讀者**（§2）。改 `StepTrace.error` 的時候要記得它也進 CSV ——
   `numbers.py` 那條界線是先例：畫面走 `wording`，檔案保留機器讀得懂的那份。
3. **「翻成白話」翻過頭**。`Step.label` 與階段名**不准進 catalog**
   （`CLAUDE.md` §3：它們是 recipe JSON 的鄰居）—— 卡片名要用 `label`，
   但不要順手把 feature 名也「翻譯」掉，那是 recipe 的鍵。
4. **83% 的斷言在 `code` 上是好事，但那 84 條會一次紅一批**。第 3 步要
   **一條 lint 一個 commit**，不要六條一起。

---

## 8. 什麼叫做完

* J1／I11／J5／J6 四條在走查文件上標成做完，而且**有一句話寫著新的句子長什麼樣**。
* `d4t/ui/wording.py` 是全 UI 唯一在做「node id / step key / param 名 → 使用者
  的字」的地方（同 `numbers.py` 的地位）。
* 那 84 條文字斷言：**改成 `code` ＋ 結構的那幾條要比原本問得更準**，
  不是為了讓測試變綠而放寬。
* 一句話的驗收：**把畫面上的每一句錯誤訊息唸給一個不寫 code 的人聽，
  他知道下一步要去點哪裡。**
