# CLAUDE.md — d4t 操作手冊

給 Claude Code／開發者的**動手指南**。這一份每個 session 都會被讀進去，所以
只留**規則**：不知道就會做錯的東西。每條規則當初怎麼踩出來的**故事**在
[`docs/history/CLAUDE-2026-09-09.md`](docs/history/CLAUDE-2026-09-09.md)
（2026-09-09 之前的完整版，逐字保留）；參考資料一律在 `docs/`，用到才讀。

> **每次 session 結束請更新 [`SESSION_LOG.md`](SESSION_LOG.md) 最上方。**

---

## 0. 先讀哪一份（每個主題只有一個家）

同一件事只寫在一個地方 —— 抄第二份出來的那份一定會漂移（真的發生過：
`tools/doctor.py` 因為一份沒跟上的文件，對每台機器給出一個**錯的**診斷）。

| 你要知道的事 | 去哪 | 什麼時候要讀 |
|---|---|---|
| **環境限制**：兩台機器、剪貼簿是唯一通道、為什麼工具都 stdlib-only | [`AGENTS.md`](AGENTS.md) | **動手之前** |
| 怎麼加卡片、鐵則、開發流程 | 這一份 | 一直 |
| EBI ↔ API characterization 的使用手冊 | [`docs/USING-CHARACTERIZATION.md`](docs/USING-CHARACTERIZATION.md) | 動 `pair_source` / `H2H` / `output_char` 之前 |
| 均勻度的使用手冊 | [`docs/USING-UNIFORMITY.md`](docs/USING-UNIFORMITY.md) | 動 `glv_stats` 的 `report`、`output_uniformity`、四張圖之前 |
| CD 卡的使用手冊 | [`docs/USING-CD.md`](docs/USING-CD.md) | 動 CD 卡的參數、help、輸出名之前 |
| Golden Cell 產模擬資料的使用手冊 | [`docs/USING-SIMGEN.md`](docs/USING-SIMGEN.md) | 動 `simgen` 視窗或 `tools/make_lot_from_gc.py` 之前 |
| **架構**：三段式心智模型、資料模型、目錄結構 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 動 pipeline／資料流之前 |
| **已知的坑**（只增不減）| [`docs/PITFALLS.md`](docs/PITFALLS.md) | 動 Qt 繪圖／快取／批次平行／KLARF 寫回／recipe 遷移之前，**先搜關鍵字** |
| **進度與 phase 計畫** | [`docs/ROADMAP.md`](docs/ROADMAP.md) | 想知道「接下來做什麼」 |
| **為什麼長成這樣**：需求訪談、六個來源專案 | [`docs/HANDOVER.md`](docs/HANDOVER.md) | 第一次接手；想改一個「看起來多餘」的設計之前 |
| **授權**：專有／內部（[`LICENSE`](LICENSE)）、vendoring 來源、第三方相依 | [`docs/LICENSING.md`](docs/LICENSING.md) | **加相依套件之前**（`LICENSE` 的 carve-out 與 §4 的表兩邊都要加，測試會擋）|
| 廠內待驗證的假設、受限機器的部署 | [`docs/FAB-VALIDATION.md`](docs/FAB-VALIDATION.md) | 動 KLARF／單位／搬運時 |
| **上游 GLAS 的介面** | [`docs/GLAS-INTERFACE.md`](docs/GLAS-INTERFACE.md) | 動 ROI 第三條路、或要請 GLAS 改東西時 |
| 逐輪的決策與理由 | [`SESSION_LOG.md`](SESSION_LOG.md) ＋ [`docs/history/`](docs/history/) | 查「這個決定當初為什麼這樣下」|

**加一份新文件之前先問：這個主題已經有家了嗎。** 有的話寫進那一份。
文件裡寫了數字（幾張卡、幾份 recipe）就要對：`tests/test_docs_match_registry.py`
從 registry 與 `recipes/` 數真值比對；不想被管就把數字拿掉改成連結。

**`bundle` 只有一個意思**：`bundle/d4t_bundle.py`，公司機拿程式碼的唯一路徑。
**不改它的名字**（`docs/NO-GIT-SETUP.md` 寫著那個檔名，而那台機器不能跑 git），
**不要再造第二個 `bundle`**。

---

## 1. 這是什麼

**d4t** = *defect* 的 numeronym（同 i18n / k8s）。名字底下永遠釘一行全稱：
**d4t — defect**。半導體 E-beam Inspection 的彈性 ADC 工具：讀 patch/RSEM 影像
＋ KLARF，用「步驟卡片組 pipeline」對每顆 defect 算分、分 bin、寫回 KLARF。

**最高指導原則：站點差異封裝進 recipe，不封裝進程式碼。**
第二原則：**推廣鐵則** —— 目標使用者是不會寫 code 的製程/設備工程師。
任何讓他們看不懂或會爆錯誤訊息的設計，都是 bug。

```
【影像段】把圖變乾淨可比 → 【算法段】從圖量出數字 → 【ADC 判定】score → bin → 寫回 KLARF
```

**現況**：Phase 1「讓數字可信」2026-08-16 收斂，使用者定調**先把引擎做對，
再回頭做產品化**（[`docs/ROADMAP.md`](docs/ROADMAP.md)）。

**出貨的 recipe 在 [`recipes/`](recipes/)**，**每一份都有測試真的跑一次**
（`tests/test_shipped_recipes.py`；舊的 `examples/` 就是因為沒人測而爛掉的）。
加一份新的就在那支測試裡加一段。**目前四份**：RSEM 逐框挑最異常的那一格、
一張影像的均勻度、EBI die-to-die（也是「用範例資料試一次」背後那份）、
DOE 逐 condition 比 SNR。
那支測試的 `ALLOWED_ERRORS` 配著一支反向測試 —— **任何「例外清單」都要有
反向測試**，不然它就是一張只會變長的紙。

存檔 recipe（`Recipe.save()`、`Ctrl+S`／`Ctrl+Shift+S`）會把 Studio 載入時做的
UI 層遷移存回磁碟。那是對的：存出跟畫面不一樣的東西才是說謊。

---

## 2. 鐵則（違反 = 測試會擋）

1. **`d4t/core` 不得 import Qt**。UI 只透過 callback 與 core 互動。
2. **Python 3.9 相容語法**。測試以 `ast.parse(feature_version=(3,9))` 掃全套件。
3. **每個 ParamSpec 的 `help` 必填**且要是白話。`register_step` 會拒絕沒有 help 的卡片。
4. **每個 Step 要有合理 default 與 min/max**。填爆的值擋在 `validate_params`，不能跑進演算法裡炸。
5. **檔案寫入一律 atomic**（`.tmp` + `os.replace`）。
6. **KLARF 寫回必須無損**：沒被改到的 byte 逐位元組相同（`klarf_core` 的 span-splice）。
7. **單顆 defect 出錯不得殺掉整批**（`run_defect` 從不 raise，回 `ok=False`）。
   **但「不 raise」不等於「不記」**（2026-09-09）：`except Exception:` 後面只有
   `pass`／`continue`／`return` 的地方，前面要先 `swallowed("模組.函式")`
   （`d4t/core/log.py`；`tests/test_core_log.py` 用 ast 守）。CLI 是 `run --log FILE`，
   Studio 寫進 `crashlog.log_dir()/d4t.log`。
8. **repo 裡不得有未遮蔽的廠內識別碼**（Lot／Wafer／機台／device／recipe 名／廠區／
   缺陷分類名）。fixture 也一樣 —— 它們斷言的是結構。`tests/test_no_real_fab_data.py` 會擋。
9. **recipe 的遷移只能靠「舊東西在不在」判斷，不能靠「新東西不在」。** 後者分不出
   「舊檔案靠舊預設」與「新 recipe 靠新預設」，而 `to_json_dict → from_json_dict` 是
   `run_batch` 送 recipe 進 worker 的路 —— 它一旦不是 identity，`workers=1` 與
   `workers=2` 就會算出不同的分數（真的發生過，見 `docs/PITFALLS.md`）。
10. **資料從哪來由「線」決定，而畫布上每一條線都是使用者拉的**（F9）。影像流的身分是
    `(節點, 埠)`。由此來的三條：**加卡不准順手接線**、**一個輸入埠只能有一條線**
    （`ambiguous-input`）、**任何會影響影像段結果的東西都要進快取簽章**。
    **具名區域完全一樣**（F12／F42）：區域線住在 `recipe.edges`
    （`[來源, 區域名, 這張卡, 參數名]`），`roi="epi"` 那一格是從線水合出來的，不寫進
    JSON；判準只有 `recipe.is_region_edge`。**順序也只看線**；**同一條 route 上兩張卡
    不准定義同名區域**（`duplicate-region`）；手寫 recipe 要寫那條線，舊檔案由
    `version < RECIPE_VERSION` 的遷移補。
11. **Studio 跑不寫，寫是另一個動作**（2026-09-09，使用者定的）。`run_trial` 與
    `run_all` 都不叫 `run_batch_steps`；寫是 `write_outputs()`，KLARF `inplace` 的確認在
    **寫的時候**問，被停掉的部分結果拒寫並講出來。Results 的「Re-run」走
    `batch.rerun_decision`（只重判），`batch.measurement_signature` 決定能不能這樣走 ——
    **不拿舊數字配新量測卡**。守門：`tests/test_ui_write_only_on_run_all.py`、
    `tests/test_rerun_decision.py`。

---

## 3. 加一張新卡片（最常見的工作）

```python
# d4t/core/steps/my_card.py
from ..pipeline.context import Context
from ..pipeline.step import CATEGORY_ALGO, ParamSpec, Step, StepError, register_step

@register_step
class MyCardStep(Step):
    key = "my_card"                    # recipe JSON 用的 id
    label = "我的卡片"                  # UI 顯示
    category = CATEGORY_ALGO           # image / algo / adc
    help = "一行白話：這張卡做什麼。"      # 必填
    params = [
        ParamSpec(name="source", type="image_key", default="diff",
                  help="要分析哪個影像流。"),
        ParamSpec(name="k", type="int", default=3, min=1, max=99,
                  help="視窗大小（越大越平滑）。"),
    ]
    reads = ["diff"]; writes = []; features_out = ["my_metric"]

    def run(self, ctx: Context, params):
        p = self.validate_params(params)
        img = ctx.require_image(p["source"])       # 缺影像會拋帶說明的 ContextError
        ctx.add_feature("my_metric", float(...))   # 演算法請呼叫 d4t.core.algo.*
        return ctx
```

`steps/__init__.py` import 它即完成註冊 —— **UI 與引擎零修改**。param 相依 I/O
覆寫 `resolve_reads/resolve_writes/resolve_features`。**卡片庫由上而下的順序 =
`steps/__init__.py` 的 import 順序**（`tests/test_card_library_order.py`），所以要放在
它該出現的位置。

卡片的規矩（每一條的故事在封存版 §3）：

* **一張卡是一次處理，寫出去的正好等於接進來的。** Enhance 卡繼承 `MultiStreamStep`，
  吃 `streams`、只實作 `build_op`。要讓兩條流吃**不同**設定才放兩張卡。真正的不變量是
  **畫布不能說謊**：卡片動到的每一條流，畫面上都要有一條線。「借另一條流的資訊」要有
  自己的參數（例 `normalize` 的 `range_from`），型別 `image_key`。
* **同一個家族的做法收成一張卡的 `method`**，方法相依的參數用 `ParamSpec.show_when`
  （它是顯示規則不是驗證規則，藏起來的參數不准影響結果 —— `test_card_invariants` I9）。
  「可以同時做」的東西不要做成四選一。**改變「量得出什麼」的選擇是岔路，不是 method**
  （問的是使用者的樣品，不是問軟體）。
* **參數名是 recipe 的鍵，不是給人看的字** —— 顯示用 `label`。影像流用 `image_key` /
  `image_keys`，區域用 `region_key` / `region_keys`（`direction="in"`），數字的名字用
  `feature_key` / `feature_keys` —— 這幾個型別在設定區是唯讀的、由畫布上的線決定，
  用 `str` 會變成一個打得進去但畫布上沒有線的文字框。區域**產出**由
  `resolve_regions_out` 宣告。
* **單數／複數**：`*_keys` 是「同一件事做在好幾個上」（第二條線累加、數字自動帶
  前綴），`*_key` 是單一角色（第二條線取代）。量測卡的迴圈在 `MultiSourceStep`。
* **「自己的量」與「比出來的量」名字要分家族**（`glv_median` vs `cmp_delta_median`）。
  改名要**連同分數表達式一起遷移**，對照表住在那張卡的 `Step.legacy_feature_renames`。
* **一格選項＝一排膠囊**（`chip_choice`：`choices` 配 `icons`、`choice_help`、例外才填
  `choice_labels`）。`choice` 純下拉是退路，測試會擋；`icon_choice` 刪掉了。
* **`min`/`max` 填好，滑桿是免費的**；`type="curve"` 拿到色調曲線編輯器。
* **卡片自動做的每一個決定，都要變成一個使用者畫得出分布的數字**（有 `auto` 就要有
  一個特徵說它選了什麼）。**算不出來的那一格不寫**（不是 0、不是 NaN），但「為什麼
  沒寫」要留得下來。
* **量測卡要在影像上標出它正在量哪裡**：覆寫 `Step.overlay_marks(ctx, params)`。
  它跟區域框**不同來源**（框從 model 推導、標記來自跑完的 context），不要混。
* **使用者面的字走 `ui/strings.py`，卡片名與階段名不走**（`Step.label` 與
  `step.GROUPS` 是 recipe JSON 的鄰居，不准進 catalog；三條測試守著）。
  缺哪些句子跑 `python tools/i18n_todo.py`。

---

## 4. 開發流程

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt && pip install -e .[dev]

ruff check                                         # 幾秒，先跑這個
python tools/typecheck.py                          # pyright（basic）掃 core，錯誤數不准超過上限
QT_QPA_PLATFORM=offscreen python -m pytest -q      # 全部測試（Windows 不用設）
python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
python -m d4t gui                                  # 開 Studio
python -m d4t run <recipe>.json /tmp/lot/LOT_SYN.001 --workers 4 --cache /tmp/cache --csv f.csv
python -m d4t --version                            # 版本 + build id（= bundle 檔頭那個數）
```

**一律 `python -m pytest`**，不是 `pytest`：兩者可能不是同一個直譯器（2026-09-09
踩到）。**`ruff check` 先跑**（設定在 `pyproject.toml`，只掃出貨的程式碼，不掃
`tests/`）。⚠ `--fix` 要看過再收：F401 答不出「別人有沒有透過這個檔案用到」，
轉出口請留 `# noqa: F401` 加一句為什麼。`RUF100` 開著：沒作用的 `noqa` 會被擋。

**跑測試的方式很重要**：開發迴圈只跑改到的檔；核心批
（`--ignore-glob="*test_ui_*"`）約 3 分半；**UI 測試不要用一個行程跑整套**（Qt
物件不會消失，時間超線性：一個行程 1:39:09、分批 7 分鐘）。要跑就
`python tools/run_tests.py`（逐檔一個行程；`--fast` 略過 UI）—— 兩台機器都跑得動。
**需要 Qt 的測試檔名要叫 `test_ui_*`**，核心批在沒有 Qt 函式庫的機器上也要綠；
函式內 lazy import 要配 `pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)`
（`tests/test_no_qt.py` 守）。

**每次改完之後**（**家用機**，公司機不能執行 git）：

```bash
git add -A && python tools/release.py && git add -A
```

`git add` 要在前面 —— 兩個產出從 `git ls-files` 產，沒 add 的新檔案會**安靜地不在
裡面**。哪一支工具在哪一台機器跑，見 [`AGENTS.md`](AGENTS.md) §4.5。
新功能開 `docs/plans/F<n>-<name>.md`，**前 5 行要有一句「狀態：」**；做完不再改的
搬進 `docs/history/plans/`（`tests/test_plan_docs.py` 守）。完成後更新 `SESSION_LOG.md`。

### 三把尺：正確性以外的兩條軸（F90）

| 尺 | 在哪 | 什麼時候會叫 |
|---|---|---|
| **規模** | `tests/test_size_ceilings.py` | 凍住的檔案變長、沒列名的檔案超過一般上限、按卡片名字分支的地方變多、`StudioWindow` 的方法／`self.*` 變多、遷移道數變多 |
| **時間** | `tools/bench.py`（家用機，`--check`）| 時間欄容差 2×，**結構欄嚴 ±2%** |
| **型別** | `tools/typecheck.py`（pyright basic，只掃 core）| 錯誤數超過上限 |
| **藏起來的參數** | `tests/test_card_invariants.py` I9 | `show_when` 藏起來的參數改變了結果或宣告 |

**天花板的意思不是「不准變大」，是「變大要有人簽名」**：上限寫在測試裡，調高要在
同一個 commit 裡改數字**並說為什麼**；掉下去要跟著降（反向測試）。
⚠ **`studio.py` 那三格例外：只准往下**（`HARD_CAPS`）。它兩天內被簽了 17 次，尺變成
流水帳 —— 要往 `studio.py` 加東西，先從它手上搬走等量的東西。**現在有幾行、幾個方法，
去那支測試看，這裡不抄第二份。**

### 新的 UI 面板一律開新模組（不要塞進 `studio.py`）

**一塊新的面板／畫布元件＝一個新模組**；`studio.py` 留給**接線**，不留給內容。
先問那一塊該不該是一塊（F50 的 `output_band.py` 就是因為「框的意思是一組、真相是
跑的時間不一樣」而刪掉的）。`d4t/ui` 裡不准直接 `QSplitter(`（用 `ui/splitters.py`，
有測試數像素）。新元件直接 import 拆出來的那幾支（`ui/fields.py`、`ui/chips.py`、
`ui/icons.py`、`ui/library.py`、`ui/histogram.py`、`ui/image_view.py`、
`ui/param_form.py`、`ui/buttons.py`、`ui/feature_text.py`）；**`widgets.py` 只是一道
轉出口，裡面不准再有 class / def**（幾行去 `tests/test_size_ceilings.py` 看）。搬家時「誰在用這個名字」不能只掃 import
（測試大量用屬性存取），判準是搬前有的名字搬後 `hasattr` 還答得出來。

真的要動 `studio.py` 那一天，前置條件是 `python tools/freeze_golden.py --check` 三份
全綠 —— 那是「改了但數字沒變」的唯一證據（這個 repo 踩過七次「跑得完、有數字、
而且是錯的」）。

### 三件會安靜做錯的事（F91）

* **不要寫死視窗尺寸**：用 `fit_screen.fit(widget, w, h)`；內容比螢幕高的要在**建構時**
  掛到 `fit_screen.scroll_host`（事後搬進捲軸在 PySide6 上是 segfault）。
* **測試不准寫進使用者真正的檔案**：`crashlog.LOG_DIR`、`autosave.DIR`、
  `BaselineStore(settings)` 是覆寫點；**加第四個會寫磁碟的東西時，先做出覆寫點**。
* **會跳 modal 對話框的新東西要有一個關得掉的旗標**（`crashlog.SHOW_DIALOG`、
  `autosave.ASK_ON_START`、`studio.PROMPT_ON_CLOSE`）—— headless 測試會永遠停在那裡。

---

## 5. 產品範圍開關

**一種 source 一張載入卡**：`load_patch`「Load images」（一顆好幾張）與 `load_single`
「Load one image」（一顆一張），**兩張都不看資料型別**。五種 source：

| kind | 什麼樣的資料 | 入口 |
|---|---|---|
| `ebi_patch` | KLARF + patch TIFF（每顆連續幾頁；檔名 `.tif` 或 `.I01`，**內容都是 TIFF**，副檔名只住在 `klarf_core.PATCH_IMAGE_EXTS`）| `Open KLARF…` |
| `rsem` | KLARF + 每顆一個影像檔 | `Open KLARF…`（自動判別）|
| `tiff_stack` | 一個多頁 TIFF、**沒有 KLARF** | `Open stack…` |
| `folder` | 一個資料夾的單張影像、沒有 KLARF | `Open folder…` |
| `doe_folder` | **一個子目錄一顆、裡面每個檔案一個 imaging condition**（DOE）、沒有 KLARF | `Open conditions…` |

後三種**寫不回 KLARF**，那句話**常駐在資料集標籤上**。第二份 lot 走 `pair_source`
卡的 `Open data…`（掛在 `Dataset.sources[代號]`，不取代目前的資料集；CLI
`--source 代號=路徑`）；**卡片不自己 `open()`**，讀檔在 ingest 層，第二份的身分要進
快取簽章。

`d4t/ui/scope.py` 是「暫時不給看」與「入口長什麼樣」的**唯一**去處；旗標由
profile 設（`fab` 預設／`dev`／`demo`，看 `D4T_PROFILE`）。⚠ **旗標要透過模組讀**
（`scope.SHOW_ROUTE_BY`），不准 `from .scope import SHOW_…`（拿到的是複本）。

```python
SUPPORTED_KINDS = ("ebi_patch", "tiff_stack", "rsem", "folder")
HIDDEN_STEPS = ()                # 目前沒有收起來的卡（`align` F109 拿回來了）
SHOW_TEMPLATE_LIBRARY = True     # 工具列的 Templates…（2026-09-08 打開）
SHOW_SAMPLE_DATA = True          # 「用範例資料試一次」（2026-09-09 隨 ebi-die-to-die.json 打開）
INPUT_SOURCES = (...)            # 五顆 Open 的字、圖示、一句白話說明
                                 # （加一列就好 —— 分岔在 ui/open_dialogs.open_source）
ATTACHMENTS = (...)              # 掛在已載入 lot 上的附加檔（GLAS 匯出）
```

**加／改一個入口＝改 `INPUT_SOURCES`，不要動 UI。** 兩個入口是兩個旗標，因為它們的
死法不一樣；`test_ui_template_library.py` 兩個方向都守（關著要有理由、開著那份 recipe
要在）。

**收起來／刪掉／改名是三件不同的事，判準都是使用者說了哪一句話**：

| 使用者說的 | 處置 | 代價 |
|---|---|---|
| 「之後真需要我再回來」 | **收起來**：卡片庫看不到，`get_step` 拿得到、舊 recipe 照跑、黃金值不動 | 加一個字串 |
| 「不需要這功能」／「完全沒用」 | **刪掉**：`REGISTRY` 裡沒有，舊 recipe 開起來是一條 `unknown-step` | 依賴它的 fixture／黃金值要一起處理 |
| 「拿回來 不過要改名字」 | **改名**：要一道遷移 | key **加上**它寫出來的 feature 名 —— 只換一半等於沒換 |
| 「名字剪短一點」 | **只改 `label`** | 零 |

**不確定的時候先收起來**：成本是零。刪之前**先去量**誰在用它（`grep` 得出來）。

> ⚠ `d4t/core/algo/` 底下四支「呼叫者很少、但不准刪」：`snr.py`（正負號慣例的規範
> 出處）、`histmatch.py`（「量與套用分開」的規範出處）、`period.py`（pattern-frame ROI
> 的唯一工具）、`golden.py`（疊 Golden Cell）。便利貼：
> `tests/test_ui_input_kinds.py::test_period_module_is_not_orphaned`。

---

## 6. 來源專案對照（vendoring）

授權那一面在 [`docs/LICENSING.md`](docs/LICENSING.md)（有測試守著兩張表不漂）。
六個專案都是同一個作者的，vendoring 沒有第三方授權義務；有義務的是執行時相依。

| 來源 | 提供了什麼 |
|---|---|
| **KLIP** | KLARF 1.2/1.8 無損引擎、TIFF page 對應、健檢 lint |
| **GLAS** | fine align、SEM loader、DAG 拓撲排序概念、ROI label map 契約 |
| **MMH** | recipe 架構原型、批次引擎模式、次像素邊緣定位、品質指標、KLARF 寫回 |
| **PEAR** | GLV 統計 metric bank、Tukey 離群、均勻度與位置趨勢（F85）、CJK-safe 影像載入 |
| **cell-period-estimator** | 週期估測、Golden Cell 堆疊、ghosting 分數 |
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、MultiROISet |
