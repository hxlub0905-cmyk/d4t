# F121 — 入口簡單化：一顆 Open、一張 Input 卡、recipe 不認資料型別

狀態：**計畫中（2026-09-24）—— 方向與四項做法使用者已同意，程式一行都還沒動。**
下一步：期 0（拿掉 DOE 入口），做之前先給使用者看這一份。

同一系列的後續：ADC 與 Output 那兩張「特別的卡」各自另開一份（見 §6）。

---

## 1. 起因（使用者回報，2026-09-24）

> 為何 d4t 在跑單純 RSEM image 時（沒有 KLARF）run 檔案時都會報 card error：
> unknown input-type route 'folder'; this recipe only defines ebi_patch

### 1.1 查到的原因（headless Studio 重現，三條路都走過）

一份 recipe 用**資料型別當鑰匙**：`routes = {"ebi_patch": [節點…]}`。引擎照
`dataset.kind` 挑 route（`recipe_schema.resolve_route`，沒有 `route_by` 時直接回
`kind`）。沒有 KLARF 的影像是 `folder`（不是 `rsem` —— `rsem` 是「KLARF ＋ 一顆
一張」），那份 recipe 沒有 `folder` 那一條，於是**每一顆**都在第一步失敗。

| 使用者的順序 | 發生什麼 |
|---|---|
| 先有 pipeline（先加了卡／用 KLARF 資料蓋到一半／開窗救回草稿 —— 草稿一律算「改過」）再開影像 | Studio 刻意不動 pipeline（`studio.py` 載入資料那一段），只在狀態列講一句，下一刻就被預覽的訊息蓋掉 |
| 先開影像，再開只有 `ebi_patch` 的 recipe | 狀態列說 "preview and trial runs will fail"，同樣一閃就過 |
| 先開 recipe，再開影像 | Studio **默默把 route 改名成 `folder`**（`model.kind = ds_kind`，節點不動）。錯誤變成 Patch 卡的「要 ≥2 張」；按 `Ctrl+S` 會把原檔改寫成 folder 版 |

**擋不下來的原因**：開跑前的健檢（`run_controller.run_trial`，註解寫明是為了
避免「跑完 200 顆、每一顆都失敗」）呼叫 `model.validate()`，而它拿去比的是
**pipeline 自己的 kind**，不是資料的。`unknown-route` 那條 lint 早就寫好了，只是
餵錯了型別：

```
lint(kind=model.kind)   → []                 ← 放行
lint(kind=dataset.kind) → ['unknown-route']  ← 本來該在這裡擋下
```

### 1.2 光把 route 改名成 `folder` 也跑不起來（實測）

| 出貨 recipe | 改成 `folder` 之後 |
|---|---|
| `ebi-die-to-die` | Patch 卡：要 ≥2 張（test/ref），這顆 1 張 |
| `rsem-worst-box` | 要 KLARF 的 `XREL`/`YREL`，這份資料沒有 KLARF |
| `one-image-uniformity` | ✅（它本來就是 `folder` 的）|

**卡能不能用，看的是「一顆幾張」與「有沒有 KLARF」，不是型別的名字。**

---

## 2. 使用者定調（2026-09-24，原話）

* 「我想要一勞永逸的改法，**Input 跟 Output 和 ADC card 這三張比較特別**」
* 「我們先從 input 開始」、「簡單來說，**我想把入口『簡單化』**」
* 同意的四項：
  1. **Patch 與 SEM image 合成一張 Input 卡**（等於推翻 F11 Input-4 的拆卡；
     拆卡當初要解的「畫布跟實際對不起來」由「名字表照資料填」解掉，見 §4）
  2. **三顆 Open 合成一顆**，程式從路徑自己判斷
  3. **一顆好幾張、名字表只寫一列** → 讀第一張，並警告「其餘幾張沒有載入」
     （Patch 卡現在的行為；SEM image 卡現在是拒絕）
  4. **舊 recipe 自動升級**：`SEM image` → `Input`，名字表 `1:<原本的 out>`；
     `Patch` 照舊。三份黃金值一個數字都不准變
* 「**DOE 的相關都先拿掉**，或之後再討論（我當初設計錯了）。DOE 更像是一個資料夾
  內有多張圖片但沒有 KLARF 的情況（單張 image）」

---

## 3. 現況盤點（量出來的）

### 3.1 入口：四樣東西要對得上，三樣看不見

1. 按哪一顆 Open（`scope.INPUT_SOURCES`：KLARF… / Images… / Conditions…）
2. 資料被判成哪種型別（`ebi_patch` / `rsem` / `folder` / `doe_folder`）—— 看不見
3. 放哪一張主入口卡（Patch / SEM image）
4. recipe 的 route 鑰匙 —— 看不見

### 3.2 Input 段的四張卡

| 卡 | key | 讀什麼 | 碰 KLARF 的參數 |
|---|---|---|---|
| Patch | `load_patch` | 主資料，一顆好幾張 | `carry`、`only_column`/`only_codes` |
| SEM image | `load_single` | 主資料，一顆一張 | 同上 |
| layout(GDS) | `load_sidecar` | 掛上去的 GLAS 匯出 | 無（要先掛匯出）|
| Pair source | `pair_source` | 掛上去的第二份 lot | 配對 `position`/`id` 要兩邊有座標／DEFECTID |

**這一份只動前兩張（主入口）。** 後兩張是「掛上去的第二份東西」，本來就是另一種。

### 3.3 兩張主入口卡 × 四種資料（實測）

| | ebi_patch（KLARF，2 張）| rsem（KLARF，1 張）| folder（無 KLARF，1 張）| doe_folder（無 KLARF，3 張）|
|---|---|---|---|---|
| Patch（1:test, 2:ref）| ✅ | ❌ 要 ≥2 張 | ❌ 要 ≥2 張 | ✅（第 3 張不載入、警告）|
| SEM image | ❌ 這顆有 2 張 | ✅ | ✅ | ❌ 這顆有 3 張 |
| ＋`carry CLASSNUMBER` | — | — | ❌ 每一顆報「沒有這個 KLARF 欄」| ❌ 同左 |
| ＋`only_codes`，無 KLARF | — | — | 篩掉全部，Studio 說「篩選條件沒對上」（**真正原因沒講**）| 同左 |

每一格 ❌ 都是**跑下去才一顆一顆報**，而那些條件在開資料那一刻就知道了。

### 3.4 SEM image ＝ 名字表只有一列的 Patch（實測）

在 `folder` 與 `rsem` 上，`load_single(out="single")` 與
`load_patch(channel_map="1:single")` 的**像素逐一相同、特徵相同**
（`n_channels = 1`）。兩張卡差的只是預設值。

### 3.5 「一個路徑自己判斷」CLI 早就做了

`d4t/__main__.py` 開資料那一支：資料夾裡是影像 → `load_folder`；資料夾裡是資料夾
→ `load_doe_folder`；單一影像檔 → `load_image_file`；`.raw` → 問版面；其他 →
KLARF（`load_dataset`）。Studio 的三顆鈕是**同一件事的第二份**。

---

## 4. 目標形狀

| | 現在 | 之後 |
|---|---|---|
| 開資料 | 三顆 Open，使用者要先知道自己的資料是哪一種 | **一顆「Open data…」**，檔案或資料夾都吃 |
| 主入口卡 | Patch、SEM image 兩張，要選對 | **一張「Input」**，名字表開資料時照資料填 |
| recipe 與資料 | 型別當鑰匙，看不見 | 沒有鑰匙；只有 Input 卡上看得見的名字表 |
| 資料不合 | 每一顆報一次錯 | **Input 卡上一行紅字＋一鍵「照這份資料重填」** |

**畫布不說謊的條件不變**：埠＝名字表＝資料真的有的。名字表在開資料時照資料填
（一顆 1 張 → `1:single`；2 張 → `1:test, 2:ref`；N 張 → N 列，名字取 ingest 給的
channel 名），所以不會回到 F11 那個「RSEM 單張卻冒出 TEST／REF 兩顆埠」。

---

## 5. 分期

每一期自己一個（或一組）commit，各自綠、各自可以停。每一期都跑：`ruff check`、
`python tools/typecheck.py`、改到的測試檔、`python tools/run_tests.py --fast`、
**`python tools/freeze_golden.py --check`**（家用機第三份的已知紅見
`docs/PITFALLS.md`「`align_score` 那一格」）、最後 `git add -A && python tools/release.py && git add -A`。

### 期 0 — 拿掉 DOE 入口（使用者：「我當初設計錯了」）

照 `CLAUDE.md` §5 的表，這是**刪掉**（設計錯了）而不是收起來。刪之前量過誰在用：

| 拿掉 | 在哪 |
|---|---|
| `doe_folder` 這個 kind | `ui/scope.py`（`SUPPORTED_KINDS`、`KIND_WORDS`）、`core/pipeline/step.py`（`PATCH_KINDS`）|
| 「Open conditions…」鈕 | `ui/scope.py`（`INPUT_SOURCES`）、`ui/open_dialogs.py`、`ui/icons.py`（`folder_stack`）|
| 讀資料夾的資料夾 | `core/ingest/dataset.py`（`load_doe_folder`）與 `ingest/__init__.py` 的轉出口、`ui/workers.py` 與 `studio.load_folder_path` 的 `doe` 參數 |
| CLI 的判別 | `__main__.py`：資料夾裡只有資料夾 → 講一句「這個資料夾裡沒有影像，只有子資料夾；請開其中一個」|
| 合成資料 | `tools/make_doe_sample.py` |
| 測試 | `tests/test_doe_folder.py` 刪；`test_no_qt`、`test_offline_tools`、`test_ui_no_klarf_label`、`test_ui_says_which_one` 裡提到它的那幾行改掉 |
| 文件 | `CLAUDE.md` §5 的 source 表、`AGENTS.md` §4.5 的工具表、`README.md`、`docs/ROADMAP.md` |

**不拿掉**（DOE 那一輪帶出來、但本身是通用的）：`align` 卡（F109 拿回來）、
GLV「參照只有一個框」、三條以上的流時特徵名帶流名前綴。使用者要拿掉的話另外說。

使用者現在對 DOE 的描述（一個資料夾、多張圖、沒有 KLARF、每張是單張 image）
**就是今天的 `folder`**：用 Open images… 開那個資料夾即可。之後要不要多做什麼
（例如「同一個條件的幾張放在一起比」）另外討論。

### 期 1 — recipe 不再以資料型別當鑰匙

**規則只改一行的意思**：沒有 `route_by`、而且 recipe **只有一條 route** 時，不管
資料是哪種都跑那一條（鍵名只剩標籤）。有兩條以上且沒有 `route_by` 的舊檔
（只有手寫 JSON 做得出來，例：`tests/fixtures/recipes/dual_route_basic.json`）照舊
用 kind 挑 —— **不遷移、不改格式**，所以：

* 大量測試直接寫的 `routes={"ebi_patch": […]}` 照樣成立；
* 型別與資料相符時選到的 route 跟今天一模一樣 → 黃金值、快取簽章都不動。

動到的地方（同一個判準收成一支 helper，例如 `route_for(recipe, kind)`，不准四處各寫一份）：

* `recipe_schema.resolve_route`（引擎選路）
* `batch.run_batch` 的 `route_keys`（整批那一層的卡）
* `recipe_validate.validate` 決定要檢查哪幾條 route 的那一段
* `__main__.py` 開跑前的「recipe 沒有這個 kind 的 route」那一句
* Studio：
  * 開資料時**不再換 `model.kind`**、不再默默改名（§1.1 第三條路消失）；
  * 開跑前健檢改成「這份 recipe 在**這份資料**上跑不跑得動」（`run_trial` 與 Re-run 兩處）；
  * `model.kind` 的意思是「正在編哪一條 route」，改名成 `model.route`，資料型別另外傳。
    ⚠ 動 `studio.py` 之前先 `tools/studio_surface.py --save`，搬完 `--check`；
    `studio.py` 的三格上限只准往下（`CLAUDE.md` §4）。

做完這一期，原始回報的那句 `unknown input-type route` 就不會再出現；取而代之的是
Patch 卡的「要 ≥2 張」—— 還是一顆一顆報，那是期 3 的事。

### 期 2 — 一張 Input 卡

* **key 留 `load_patch`**，`label` 改成「Input」（`CLAUDE.md` §5：只改 label 零代價；
  key 是 recipe 的鍵不是給人看的字）。出貨 recipe、黃金值裡的 `load_patch` 一個字都不動。
* `load_single` 從 `REGISTRY` 刪掉，舊 recipe 由一道遷移換成
  `load_patch(channel_map="1:<out>")`，`nm_per_px`、`carry`、`only_*` 原樣帶過去。
  判準是「`load_single` 這個節點在不在」（鐵則 9：只看舊東西在不在）。
  節點 id 不變、`out` 那條流的名字不變 → 線（`recipe.edges` 的埠名）不必動。
  特徵兩張卡都只寫 `n_channels`，不必遷移特徵名。
  ⚠ 遷移道數有上限（`tests/test_size_ceilings.py`），在同一個 commit 裡改數字並寫為什麼。
* **行為差一格**（使用者同意的第 3 項）：一顆好幾張、名字表只寫一列 → 讀第一張、
  警告其餘沒載入（今天的 Patch 卡），不再拒絕。
* 開資料時自動放的起手卡（`RecipeModel.SINGLE_IMAGE_STARTERS` 與
  `studio._adopt_source_for`）只剩一張，**名字表照資料填**（§4）。
* 卡片庫、help、`docs/USING-*.md`、`recipes/README.md` 裡的「SEM image」改寫；
  `rsem-worst-box.json`、`one-image-uniformity.json` 經遷移存回新格式（出貨 recipe
  一律有測試跑，`tests/test_shipped_recipes.py`）。
* 驗收：`load_single` → Input 的遷移前後，出貨 recipe 與黃金值逐位元組相同的特徵表。

### 期 3 — Input 卡看資料

* **一份「這批資料長什麼樣」**（core，不碰 Qt）：一顆幾張（整批的最小／最大）、
  有沒有 KLARF、KLARF 有哪幾欄。Studio 開資料時算一次，CLI 開跑前算一次。
* **Input 卡宣告它要什麼**（仿 `Step.kind_issues` 的形狀）：名字表要 N 張、
  `carry` 要哪幾欄、`only_*` 要哪一欄。資料不合 → **lint error 掛在 Input 卡上**，
  開跑前擋下（取代「每一顆報一次」）。白話，例：
  「這份資料一顆 1 張，名字表寫了 2 張（test、ref）。」
  「這份資料沒有 KLARF，『Carry these columns』用不了。」
  「這份資料沒有 KLARF，『Only run this column』篩不了 —— 不是篩選條件沒對上。」
* **一鍵「照這份資料重填」**：名字表改成資料有的那幾張。流名還對得上的線留著；
  接到消失的埠（例 `ref`）的線斷掉，下游那幾張卡在畫布上變紅 —— 使用者一眼看得出
  哪幾張卡在這種資料上做不到。**不偷偷接線、不偷偷刪卡**（鐵則 10）。
* KLARF 那幾格在沒有 KLARF 的資料上整塊變灰＋一句「這份資料沒有 KLARF」。
  ⚠ 變灰是**顯示**；值還在 recipe 裡，換回有 KLARF 的資料時照樣用（同 `show_when`
  的規矩：藏起來的東西不准改變結果 —— `test_card_invariants` I9）。

### 期 4 — 一顆 Open

* CLI 那一支「從路徑判斷」搬進 `core/ingest`（一個家），CLI 與 Studio 都叫它。
* `scope.INPUT_SOURCES` 剩一列「Open data…」（`CLAUDE.md` §5：加／改入口＝改那張表，
  不動 UI）。說明那一句要講得出它吃哪幾種：KLARF、影像資料夾、單張影像、`.raw`。
* 判不出來的（資料夾裡什麼都沒有、只有子資料夾…）當場講一句能照做的話。
* 資料集標籤上「寫不回 KLARF」那一句照舊常駐。

---

## 6. 這一份不做的

* **ADC 與 Output**（使用者說的另外兩張「特別的卡」）：例如沒有 KLARF 的資料配上
  Write KLARF 卡該擋還是跳過、判定樹用到 KLARF 欄時怎麼講 —— 各自另開一份。
* **DOE 重新設計**：期 0 只拿掉，之後再談。
* **一份 recipe 同時吃兩種資料**（畫布上兩張 Input 卡、開哪種跑哪條）：期 1 讓舊的
  多 route 檔照舊能跑，要不要做成畫布上看得見的樣子之後再定。
* layout(GDS)、Pair source：不動。

---

## 7. 驗收（整份做完時）

* **原始情境**：一份 EBI（Patch，test/ref）recipe ＋ 一個 RSEM 影像資料夾 →
  不會出現 N 個 card error；Input 卡上一句話；按「照這份資料重填」之後，做得到的
  卡照跑、做不到的在畫布上是紅的。
* 三份出貨 recipe、`freeze_golden --check` 的黃金值，數字一個都沒變。
* 舊 recipe（含 `load_single`、含 `doe_folder` 以外的每一種 kind 鍵）開得起來、
  跑出一樣的數字；`to_json_dict → from_json_dict` 是 identity（鐵則 9）。
* CLI 與 Studio 對同一個路徑判出同一種資料（一支函式）。
