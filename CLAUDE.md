# CLAUDE.md — ADEPT 操作手冊

給 Claude Code／開發者的**動手指南**。這一份會被讀進每一個 session，
所以它刻意只留「不知道就會做錯」的東西；**參考資料一律放在 `docs/`，用到才讀**。

> **每次 session 結束請更新 [`SESSION_LOG.md`](SESSION_LOG.md) 最上方。**

---

## 0. 先讀哪一份（每個主題只有一個家）

同一件事只寫在一個地方 —— 抄第二份出來的那份一定會漂移
（2026-08 實際發生過：程式碼刪了五份範例 recipe，四份文件裡只有一份跟上，
而 `tools/doctor.py` 因此對每台機器給出一個**錯的**診斷）。

| 你要知道的事 | 去哪 | 什麼時候要讀 |
|---|---|---|
| **環境限制**：兩台機器、剪貼簿是唯一通道、為什麼工具都 stdlib-only | [`AGENTS.md`](AGENTS.md) | **動手之前**（不知道會把必要設計當成過度設計刪掉）|
| 怎麼加卡片、鐵則、開發流程 | 這一份 | 一直 |
| **架構**：三段式心智模型、資料模型（影像流 vs 具名區域）、目錄結構 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 動到 pipeline／資料流之前 |
| **已知的坑**（30+ 條，只增不減）| [`docs/PITFALLS.md`](docs/PITFALLS.md) | 動到 Qt 繪圖／快取／批次平行／KLARF 寫回／recipe 遷移之前，**先搜關鍵字** |
| **進度與 phase 計畫** | [`docs/ROADMAP.md`](docs/ROADMAP.md) | 想知道「接下來做什麼」 |
| **為什麼長成這樣**：需求訪談結論、六個來源專案的脈絡 | [`docs/HANDOVER.md`](docs/HANDOVER.md) | 第一次接手；想改一個「看起來多餘」的設計之前 |
| 廠內待驗證的假設、受限機器的部署 | [`docs/FAB-VALIDATION.md`](docs/FAB-VALIDATION.md) | 要動 KLARF／單位／搬運時 |
| **上游 GLAS 的介面**（label map／合成 gray／alignment；ADEPT 不解析 layout）| [`docs/GLAS-INTERFACE.md`](docs/GLAS-INTERFACE.md) | 要動 ROI 第三條路、或要請 GLAS 改東西時 |
| 逐輪的決策與理由 | [`SESSION_LOG.md`](SESSION_LOG.md)（近期）＋ [`docs/history/`](docs/history/) | 查「這個決定當初為什麼這樣下」|

**加一份新文件之前先問：這個主題已經有家了嗎。** 有的話寫進那一份。

---

## 1. 這是什麼

**ADEPT** = Auto Defect Evaluation Pipeline Tool。
半導體 E-beam Inspection 的彈性 ADC 工具：讀 patch/RSEM 影像 + KLARF，
用「步驟卡片組 pipeline」對每顆 defect 算分、分 bin、寫回 KLARF。

**最高指導原則：站點差異封裝進 recipe，不封裝進程式碼。**
第二原則：**推廣鐵則** —— 目標使用者是不會寫 code 的製程/設備工程師。
任何讓他們看不懂或會爆錯誤訊息的設計，都是 bug。

一句話的心智模型（完整版見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)）：

```
【影像段】把圖變乾淨可比 → 【算法段】從圖量出數字 → 【ADC 判定】score → bin → 寫回 KLARF
```

### 目前不支援的兩件事（不是漏掉的）

engine 還在做（**Phase 1「讓數字可信」已於 2026-08-16 收斂**，下一步是
Phase 2），使用者定調**先把引擎做對，再回頭做產品化**（見
[`docs/ROADMAP.md`](docs/ROADMAP.md)）：

- **沒有範例 recipe**（`examples/` 已移除），Studio 的「用範例資料試一次」與
  「Templates…」兩個入口收起來了 —— 開關在 `ui/scope.py`。
- **不能存檔 recipe**（2026-08-16 移除）：沒有 Save Recipe…、沒有 Ctrl+S、
  沒有 `Recipe.save()`。**讀取仍然在**，CLI 照跑。

---

## 2. 鐵則（違反 = 測試會擋）

1. **`adept/core` 不得 import Qt**。UI 只透過 callback 與 core 互動。
2. **Python 3.9 相容語法**（廠內機器可能是舊版）。測試以 `ast.parse(feature_version=(3,9))` 掃全套件。
3. **每個 ParamSpec 的 `help` 必填**且要是白話。`register_step` 會拒絕沒有 help 的卡片。
4. **每個 Step 要有合理 default 與 min/max**。使用者填爆的值必須擋在 `validate_params`，
   不能讓它跑到演算法裡炸。
5. **檔案寫入一律 atomic**（`.tmp` + `os.replace`）。
6. **KLARF 寫回必須無損**：沒被改到的 byte 要與原檔逐位元組相同（`klarf_core` 的 span-splice）。
7. **單顆 defect 出錯不得殺掉整批**（`run_defect` 從不 raise，回 `ok=False`）。
8. **repo 裡不得有未遮蔽的廠內識別碼**（Lot／Wafer／機台／device／recipe 名稱／
   廠區代號／缺陷分類名稱）。測試 fixture 也一樣 —— 它們斷言的是**結構**，
   值遮蔽掉一條測試都不會壞。`tests/test_no_real_fab_data.py` 會擋。
9. **recipe 的遷移只能靠「舊東西在不在」判斷，不能靠「新東西不在」。**
   後者分不出「舊檔案靠舊預設」與「新 recipe 靠新預設」，而
   `to_json_dict → from_json_dict` 是 `run_batch` 送 recipe 進 worker 的路 ——
   它一旦不是 identity，`workers=1` 與 `workers=2` 就會算出不同的分數。
   真的發生過（見 `docs/PITFALLS.md`）。
10. **資料從哪來由「線」決定，而畫布上每一條線都是使用者拉的**（F9）。
    影像流的身分是 `(節點, 埠)`，不是一個全域名字 —— 同一條 `ref` 分岔成兩支
    才成立。由此來的三條規矩：**加卡不准順手接線**（自動接的線與使用者拉的線
    會落在同一個輸入，而只有一條算數）、**一個輸入埠只能有一條線**
    （`validate` 會報 `ambiguous-input`）、**任何會影響影像段結果的東西都要進
    快取簽章**（改接線可以完全不動參數，簽章看不見線就會回舊影像）。
    這一段踩過六個「跑得完、有數字、而且是錯的」，全部記在 `docs/PITFALLS.md`
    與 `docs/history/plans/F9-dag-streams.md`。

---

## 3. 加一張新卡片（最常見的工作）

```python
# adept/core/steps/my_card.py
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
        ctx.add_feature("my_metric", float(...))   # 演算法請呼叫 adept.core.algo.*
        return ctx
```

`steps/__init__.py` import 它即完成註冊 —— **UI 與引擎零修改**，卡片庫自動出現。
param 相依 I/O（例如輸出流名稱由參數決定）覆寫 `resolve_reads/resolve_writes/resolve_features`。

> **一張卡是一次處理，寫出去的正好等於接進來的**（F7-19／F7-20）。Enhance 卡
> 繼承 `MultiStreamStep`（`steps/_util.py`）：吃 `streams`（一串影像流）、
> 只實作 `build_op` 回一個 `img -> img`，迴圈交給基底。接 test 也接 ref，
> 兩條就吃**同一組設定** —— 那正是「兩張圖還比得起來」的前提。
> 要讓兩條流吃**不同**設定才放兩張卡。
>
> 真正的不變量是**畫布不能說謊**：卡片動到的每一條流，畫面上都要有一條線。
> （F7-18 的「一張卡一條流」是當時達成它的手段，不是不變量本身 —— 見計畫書
> §23.1。`also_apply` 那種「藏在控制列的第二條流」仍然不准回來。）
> 需要「借另一條流的資訊」時，那件事要有自己的參數（例：`normalize` 的
> `range_from`），型別是 `image_key` —— 它在畫布上就是第二條接進來的線。

> **同一個家族的做法收成一張卡的 `method`**（F7-10／F7-20）。四種正規化、
> 五種去背景、四種去雜訊各是一張卡的下拉，不是十三張卡 —— 卡片庫多一列，
> 使用者就要多讀一段說明才知道該用哪一個。**方法相依的參數用
> `ParamSpec.show_when`**（例 `show_when=("method", ("percentile",))`），
> 不要在 help 裡寫「（這個方法用不到）」那種道歉。
> 注意 `show_when` 是**顯示**規則不是驗證規則：藏起來的參數照樣有預設值，
> 卡片自己要保證用不到的參數不影響結果（`resolve_reads` 也一樣）。
> 但**「可以同時做」的東西不要做成四選一** —— `tone` 的亮度／gamma／反相是
> 幾個預設不作用的旋鈕，因為使用者常常要一起用。

> **參數名是 recipe 的鍵，不是給人看的字**（F7-9）。`ParamSpec` 有選填的
> `label`：有就顯示 label，沒有就顯示 `name`。`range_from` 對製程工程師不是
> 一句話，`Borrow range from` 才是。同理，「一串影像流」請用 `type="image_keys"`
> 而不是 `str` —— 值的格式一樣（逗號分隔字串），但 UI 認得它是**接線的結果**。
>
> **`image_key` / `image_keys` 的欄位在設定區是唯讀的**（F9-6，使用者定調：
> 「他會很亂連」）。來源只在畫布上拉線決定，設定區只顯示現在接的是什麼。
> 所以卡片吃影像流的參數請務必用這兩個型別 —— 用 `str` 的話它會變成一個
> 打得進去、但畫布上沒有對應線條的自由文字框。

> **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。ParamForm 看到有上下界的
> `int`/`float` 就自動配一支跟數字框雙向綁定的滑桿。這不只是好看 ——
> 使用者是一邊拖一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。
> `type="curve"` 則會拿到一張可以自己拉的色調曲線編輯器（見 `pipeline/curve.py`）。

---

## 4. 開發流程

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt && pip install pytest

QT_QPA_PLATFORM=offscreen pytest -q                # 全部測試（Windows 不用設）
python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
python -m adept gui                                # 開 Studio
python -m adept run <recipe>.json /tmp/lot/LOT_SYN.001 \
    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
```

**跑測試的方式很重要**（不照做會浪費很多時間）：

- 開發迴圈**只跑改到的測試檔**：`pytest -q tests/test_xxx.py`。
- 核心（`--ignore-glob="*test_ui_*"`）約 20–30 秒，隨時可以跑。
- **UI 測試不要用一個行程跑整套** —— Qt 記憶體會累積，在容器裡實測從 100 秒
  變成跑不完。要跑就一個檔案一個檔案跑（每個 1–10 秒）：
  `for f in tests/test_ui_*.py; do pytest -q "$f"; done`

**每次改完之後**（**家用機**，公司機不能執行 git）：

```bash
git add -A && python tools/release.py && git add -A
```

`git add` 要在前面 —— 兩個產出都是從 `git ls-files` 產的，還沒 add 的新檔案會
**安靜地不在裡面**。`tests/test_offline_tools.py` 會擋住它們過期。
哪一支工具在哪一台機器跑，見 [`AGENTS.md`](AGENTS.md) §4.5。

新功能請開 `docs/plans/F<n>-<name>.md`（沿用 GLAS/MMH 慣例），完成後更新
`SESSION_LOG.md`；做完不再改的計畫書搬進 `docs/history/plans/`。

---

## 5. 產品範圍開關

**Studio 吃四種輸入（2026-08-17，F11 Input-3）**，一種 source 一個入口：

**一種 source 一張卡**（F11 Input-4，使用者定調）：Input 段有兩張載入卡 ——
`load_patch`「Load images」（一顆好幾張，`channel_map` 命名）與 `load_single`
「Load one image」（一顆一張，`out` 命名）。**兩張都不看資料型別**，宣告只看
使用者看得到的值 —— 一張卡服務四種 source 的時候，畫布會說謊（那時候「這張卡吐
哪幾條流」有三個不同的答案，而畫布拿到的是錯的那一個）。

| kind | 什麼樣的資料 | 入口 |
|---|---|---|
| `ebi_patch` | KLARF + patch TIFF（每顆連續幾頁）| `Open KLARF…` |
| `rsem` | KLARF + 每顆一個影像檔 | `Open KLARF…`（自動判別）|
| `tiff_stack` | 一個多頁 TIFF、**沒有 KLARF** | `Open stack…`（問「一顆幾張」）|
| `folder` | 一個資料夾的單張影像、沒有 KLARF | `Open folder…` |

後兩種沒有 KLARF → 沒有座標、**寫不回 KLARF**，而那句話**常駐在資料集標籤上**
（`tiff_stack · defect 1 / 3 · no KLARF`）—— 不是等使用者按了 Export 才發現。

`adept/ui/scope.py` 仍然是這類「暫時不給看」的**唯一**去處：

```python
SUPPORTED_KINDS = ("ebi_patch", "tiff_stack", "rsem", "folder")
HIDDEN_STEPS = ()                # 空了（原本收著 golden_cell / cell_period）
SHOW_SAMPLE_ENTRIES = False      # 範例入口（見下）
```

`SHOW_SAMPLE_ENTRIES`（2026-08-16）管兩個入口：導覽與空白狀態上的
**「用範例資料試一次」**、工具列的 **「Templates…」**。範例 recipe 全部拿掉之後
它們都是死路（庫是空的、demo 產得出資料卻載不到 pipeline），而**按了撞牆的鈕
比沒有那顆鈕更糟**（推廣鐵則）。`run_demo` / `RecipeLibraryDialog` 一行都沒動。

`tests/test_ui_input_kinds.py`（原 `test_ui_patch_only.py`）鎖住四種都進得來、
沒有 KLARF 的兩種會講出來、而**「暫時收起來」的機制還在**（`HIDDEN_STEPS` 空著
但 `visible_steps()` 照樣管用 —— 下次要藏一張卡時加一個字串就好）。

F7-1 收斂成 patch-only 時用的是「**收起來、不刪掉**」，於是這一輪打開只改了
`scope.py` 的兩個常數，`ingest` / `golden_cell` / `algo/period.py` 一行都沒動。
**收起來的成本是零、回復的成本是加一個字串** —— 那個判斷被驗證了。

> ⚠ **`adept/core/algo/period.py` 不要刪。** 它現在只被 Golden Cell 用到，
> 看起來像是可以跟 RSEM 一起砍掉的東西 —— 但 `estimate_period` /
> `choose_origin` 的相位搜尋是之後做 **pattern-frame ROI** 的唯一工具
> （patch 是以 defect 為中心裁切的，晶格相位逐顆不同；
> 見 `docs/history/plans/F7-canvas-and-taxonomy.md` §4）。

CLI 不受影響：`python -m adept run` 照樣跑得動 rsem recipe。

---

## 6. 來源專案對照（vendoring）

每個 vendored 模組檔頭都註明來源與改動。原始專案：

| 來源 | 提供了什麼 |
|---|---|
| **KLIP** | KLARF 1.2/1.8 無損引擎、TIFF page 對應、健檢 lint |
| **GLAS** | fine align、SEM loader、DAG 拓撲排序概念、ROI label map 契約 |
| **MMH** | recipe 架構原型、批次引擎模式、次像素邊緣定位、品質指標、KLARF 寫回 |
| **PEAR** | GLV 統計 metric bank、Tukey 離群、η²/Cohen's d、CJK-safe 影像載入 |
| **cell-period-estimator** | 週期估測、Golden Cell 堆疊、ghosting 分數 |
| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、SNR map、blob 分割、MultiROISet |
