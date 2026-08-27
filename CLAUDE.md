# CLAUDE.md — d4t 操作手冊

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
| **怎麼做 EBI ↔ API characterization**（給使用者的操作手冊：線接哪、每格填什麼、報表怎麼讀、出事了照什麼順序查）| [`docs/USING-CHARACTERIZATION.md`](docs/USING-CHARACTERIZATION.md) | 要動 `pair_source` / `H2H` / `output_char` 的參數或說明之前 |
| **怎麼用 CD 那張卡**（給使用者的操作手冊：每一格什麼時候動、數字會往哪走）| [`docs/USING-CD.md`](docs/USING-CD.md) | 要動 CD 卡的參數、help 文字或輸出名字之前 |
| **架構**：三段式心智模型、資料模型（影像流 vs 具名區域）、目錄結構 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 動到 pipeline／資料流之前 |
| **已知的坑**（30+ 條，只增不減）| [`docs/PITFALLS.md`](docs/PITFALLS.md) | 動到 Qt 繪圖／快取／批次平行／KLARF 寫回／recipe 遷移之前，**先搜關鍵字** |
| **進度與 phase 計畫** | [`docs/ROADMAP.md`](docs/ROADMAP.md) | 想知道「接下來做什麼」 |
| **為什麼長成這樣**：需求訪談結論、六個來源專案的脈絡 | [`docs/HANDOVER.md`](docs/HANDOVER.md) | 第一次接手；想改一個「看起來多餘」的設計之前 |
| 廠內待驗證的假設、受限機器的部署 | [`docs/FAB-VALIDATION.md`](docs/FAB-VALIDATION.md) | 要動 KLARF／單位／搬運時 |
| **上游 GLAS 的介面**（label map／合成 gray／alignment；d4t 不解析 layout）| [`docs/GLAS-INTERFACE.md`](docs/GLAS-INTERFACE.md) | 要動 ROI 第三條路、或要請 GLAS 改東西時 |
| 逐輪的決策與理由 | [`SESSION_LOG.md`](SESSION_LOG.md)（近期）＋ [`docs/history/`](docs/history/) | 查「這個決定當初為什麼這樣下」|

**加一份新文件之前先問：這個主題已經有家了嗎。** 有的話寫進那一份。

### ⚠ 一個字，兩個東西：**bundle**

上面那條規矩的鏡像。這個 repo 裡 `bundle` 指**兩個完全不相干**的東西，而它們
從來不會在同一段程式碼裡出現 —— 所以會混淆的是**人**（2026-08-26 真的發生過：
一整輪對話裡兩個意思交替使用，使用者問「bundle 在這邊是什麼」）。

| 寫成 | 是什麼 | 住哪 | 誰在用 |
|---|---|---|---|
| ~~`output_bundle`~~ | **一張 Output 卡**（“Write report folder”）。**F38 於 2026-08-26 折進 `output_report` 了** —— 那個 key 不存在了，舊 recipe 走 `_migrate_folded_output_cards` | ~~`d4t/core/steps/output.py`~~ | — |
| `bundle/d4t_bundle.py` | **整個 repo 打包成的一個純文字檔**，公司機拿程式碼的唯一路徑（政策擋 .zip、proxy 不讓逐檔抓）。`tools/release.py` 產它 | `bundle/` | 開發者搬程式碼 |

**所以現在這個字只剩一個意思，而這一段留著是為了下一次。** 兩件事要記住：

**① `bundle/d4t_bundle.py` 仍然不改名。** 它是**公司機的操作步驟**
（`docs/NO-GIT-SETUP.md` 寫著那個檔名，而那台機器不能跑 git —— 改檔名等於讓
一份寫下來的程序在一台救不了的機器上失效）。

**② 不要再造第二個 `bundle`。** 上一次兩個意思並存的代價是實際發生過的：
2026-08-26 一整輪對話裡兩個意思交替使用，使用者問「bundle 在這邊是什麼」。
那一輪量過代價、決定兩個都不改名（因為改 key 要付一道遷移，而那個錢只在
使用者要求時才付）—— 而錢在 F38 因為別的理由付掉了，混淆才跟著消失。
**下一個含糊的名字不會這麼剛好。**

**講的時候不要用裸的「bundle」** —— 講「報表那張卡」或「搬運用的單檔包」。

---

## 1. 這是什麼

**d4t** = *defect* 的 numeronym（頭字母 + 中間字數 + 尾字母，跟 i18n / k8s / n8n 同一套）。
名字底下永遠釘一行全稱：**d4t — defect**。
半導體 E-beam Inspection 的彈性 ADC 工具：讀 patch/RSEM 影像 + KLARF，
用「步驟卡片組 pipeline」對每顆 defect 算分、分 bin、寫回 KLARF。

**最高指導原則：站點差異封裝進 recipe，不封裝進程式碼。**
第二原則：**推廣鐵則** —— 目標使用者是不會寫 code 的製程/設備工程師。
任何讓他們看不懂或會爆錯誤訊息的設計，都是 bug。

一句話的心智模型（完整版見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)）：

```
【影像段】把圖變乾淨可比 → 【算法段】從圖量出數字 → 【ADC 判定】score → bin → 寫回 KLARF
```

### 目前收起來的一件事（不是漏掉的）

engine 還在做（**Phase 1「讓數字可信」已於 2026-08-16 收斂**，下一步是
Phase 2），使用者定調**先把引擎做對，再回頭做產品化**（見
[`docs/ROADMAP.md`](docs/ROADMAP.md)）：

- **範本庫是空的**（`examples/` 已移除），Studio 的「用範例資料試一次」與
  「Templates…」兩個入口收起來了 —— 開關在 `ui/scope.py`。

**出貨的 recipe 在 [`recipes/`](recipes/)**（2026-08-26），走 `Open recipe…`
不走範本庫，而且**每一份都有測試真的跑一次**
（`tests/test_shipped_recipes.py`）—— 舊的 `examples/` 就是因為沒人測而爛掉的。
加一份新的就在那支測試裡加一段。目前兩份：EBI↔API characterization、
patch 的 dSNR 分布（F36）。

⚠ 那支測試有一張 **`ALLOWED_ERRORS`**（哪一份 recipe 允許哪一條 lint error
—— 目前只有「模板是一張影像、塞不進 JSON」那一種），而它配著一支**反向的**
測試：例外修好了卻沒從表上拿掉的話，那份 recipe 從此少一條防線而測試照樣綠。
**任何「例外清單」都要有那支反向測試**，不然它就是一張只會變長的紙。

**存檔 recipe 2026-08-26 做回來了**（F34，[`docs/history/plans/F34-save-recipe.md`](docs/history/plans/F34-save-recipe.md)）。
`Recipe.save()`、工具列的「Save recipe…」、`Ctrl+S`（存回原檔）與
`Ctrl+Shift+S`（另存）都在。⚠ 它帶來一個**以前不存在的後果**：Studio 載入時做的
UI 層遷移（門檻 → 判定樹）現在會被存回磁碟。那是對的（存出跟畫面不一樣的東西
才是說謊），但寫在 `_adopt_threshold_as_a_tree` 裡的「反正存不了檔」那句話
已經作廢 —— 見 `Recipe.save` 的說明。

---

## 2. 鐵則（違反 = 測試會擋）

1. **`d4t/core` 不得 import Qt**。UI 只透過 callback 與 core 互動。
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

    **具名區域完全一樣（F12 起有線，F42 起同一套機制）**：一張卡用到的每一個
    區域，畫布上都要有一條線指到定義它的那張卡（虛線 + 菱形埠），而那條線
    **就住在 `recipe.edges` 裡**（`[來源, 區域名, 這張卡, 參數名]`）——
    `roi="epi"` 那一格是從線**水合**出來的值，不寫進 JSON。判準只有一支：
    `recipe.is_region_edge`。三條由此而來：

    * **順序也只看線**（F17-①）。把 Region 卡拖到量測卡右邊不會再讓量測卡
      先跑 —— 那個 bug 是 F42 的起點，第七個「跑得完、有數字、而且是錯的」。
    * **同一條 route 上兩張卡不准定義同名區域**（`duplicate-region`，error）。
      引擎的 `ctx.set_roi` 是同名覆寫，名字唯一才讓「線指的那張卡」＝
      「引擎真的給的那個框」恆成立 —— 那是引擎一行都不用改的原因。
    * **手寫 recipe 從此要寫那條線**；舊檔案由 `version < RECIPE_VERSION`
      的遷移補，`tools/doctor.py` 的「recipe 格式」那一項會提醒。

    見 `docs/plans/F42-region-edges-plan-b.md`（F12 §3 於該輪推翻，
    其他部分 —— 埠、虛線、唯讀參數格、同進同出 —— 全部保留）。

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
>
> **改變「量得出什麼」的那種選擇是岔路，不是 method**（F19 第二批）。CD 卡最
> 上面的「一條線／一團東西」問的是樣品，而且它決定了後面哪幾格**算不算數**
> （方向對一團東西沒有意義）—— 那種要用 `show_when` 把不適用的收起來，不是攤
> 在那裡讓使用者猜。判準仍然是那一句：**這個參數問的是使用者的樣品，還是問
> 軟體**。反過來，兩支都成立的那一格（CD 的門檻高度）就**共用同一格、同一支
> 函式** —— 分成兩份的那天，同一句話會長出兩種意思。

> **參數名是 recipe 的鍵，不是給人看的字**（F7-9）。`ParamSpec` 有選填的
> `label`：有就顯示 label，沒有就顯示 `name`。`range_from` 對製程工程師不是
> 一句話，`Borrow range from` 才是。同理，「一串影像流」請用 `type="image_keys"`
> 而不是 `str` —— 值的格式一樣（逗號分隔字串），但 UI 認得它是**接線的結果**。
>
> **`image_key` / `image_keys` 的欄位在設定區是唯讀的**（F9-6，使用者定調：
> 「他會很亂連」）。來源只在畫布上拉線決定，設定區只顯示現在接的是什麼。
> 所以卡片吃影像流的參數請務必用這兩個型別 —— 用 `str` 的話它會變成一個
> 打得進去、但畫布上沒有對應線條的自由文字框。
>
> **吃具名區域的參數同理，用 `region_key` / `region_keys` 並宣告
> `direction="in"`**（F12，2026-08-19）。區域在畫布上是**菱形埠 + 一條虛線**，
> 那一格一樣唯讀。用 `str` 的下場更糟：畫面上兩張卡看起來互不相干，而拿掉上游
> 那張 Region 卡，量測卡不會報錯 —— 它會**安靜地改量整張圖**。
> 區域**產出**的名字不走參數，由 `resolve_regions_out` 宣告
> （`<name>_center` 那種是算出來的，不是某一格填的字）。
>
> **單數／複數的意思跟影像流一字不差**（F13-⑥）：`region_keys`（一串）是
> 「同一件事做在好幾個區域上」，第二條線**累加**，而每個數字會自動帶上
> 區域名前綴（`epi_glv_mean` / `mg_glv_mean`；只接一個時名字跟以前逐字相同）；
> `region_key`（單一角色，例 `roi_compare` 的 target / reference）第二條線是
> **取代**。量測卡的迴圈在 `MultiSourceStep`，子類只實作 `measure` —— 它不必
> 知道接了幾條流，也不必知道接了幾個區域。

> **一張卡同時吐「自己的量」與「比出來的量」時，名字要分家族**（F18，
> 2026-08-21）。`glv_median` 是這一塊自己的灰階、`cmp_delta_median` 是跟參照
> 比出來的，而**比的是哪個統計量落在尾巴** —— 使用者可以一次挑好幾個統計量，
> 那是唯一不撞的寫法。理由不是整齊：這些名字會排在同一份 CSV、同一條分數
> 表達式裡，而「這個數字是誰跟誰算出來的」在那兩個地方沒有別的線索。
> 改名要**連同分數表達式一起遷移**，而對照表住在那張卡上
> （`Step.legacy_feature_renames`），不是住在 `recipe.py`。

> **卡片庫由上而下的順序 = `steps/__init__.py` 的 import 順序**（F29，
> 2026-08-25）。`list_steps()` 就是照 `REGISTRY` 的插入序回，不排序 ——
> 所以加一張卡要**放在它該出現的位置**，不是接在檔案最後。
> 這一條是踩出來的：2026-08-25 使用者說「Measure 的 card 順序幫我改命名&重排：
> GLV → CD → Focus index」，那一輪改了 import 順序、也在那裡寫下這句話，
> **而畫面上一格都沒有動** —— 當時 `list_steps` 是照 `key` 的字母序排的
> （CD、Focus index、GLV）。整個改動看起來完成了，全套測試也全綠，因為沒有
> 任何一條測試問過「使用者看到的第一張是哪一張」。現在有了：
> `tests/test_card_library_order.py`。

> **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。ParamForm 看到有上下界的
> `int`/`float` 就自動配一支跟數字框雙向綁定的滑桿。這不只是好看 ——
> 使用者是一邊拖一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。
> `type="curve"` 則會拿到一張可以自己拉的色調曲線編輯器（見 `pipeline/curve.py`）。

> **卡片自動做的每一個決定，都要變成一個使用者畫得出分布的數字**（F19）。
> 有 `auto` 選項的參數，就要有一個特徵說出它這一顆選了什麼（CD 的
> `cd_axis_deg` / `cd_bright`）。理由不是完整性：`target="auto"` 在一批 patch
> 上逐顆挑了不同的極性，於是 `cd_median` 那一欄同時裝著「線寬 6.5」與
> 「溝寬 9.4」**兩群**數字 —— 每一顆都吐得出正常的值，而 CSV 上沒有任何線索。
> 同一族的還有「量得準不準」（`glv_pixels` / `cd_n`）：**算不出來的那一格不寫**
> （不是 0、也不是 NaN），但「為什麼沒寫」要留得下來。

> **量測卡要在影像上標出它正在量哪裡**：覆寫 `Step.overlay_marks(ctx, params)`
> 回 `(線段, 每條線上的點, 要畫粗的那一條)`，正規化座標，預設什麼都不畫。
> 這是**整個 Measure 段共用**的一條路（F19 建的，F18 §9.0 指名要的）——
> 讀 meta 的程式碼住在**那張卡**上，UI 只負責畫。
> ⚠ 它跟區域框**不同來源**：框從 model 推導（recipe 說要看哪裡），標記來自跑完
> 的 context（這一顆真的量到了什麼）。混在一起的話，「框還在但標記沒了」這個
> 最有用的狀態就講不出來。

---

## 4. 開發流程

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt && pip install pytest

QT_QPA_PLATFORM=offscreen pytest -q                # 全部測試（Windows 不用設）
python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
python -m d4t gui                                # 開 Studio
python -m d4t run <recipe>.json /tmp/lot/LOT_SYN.001 \
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

### 新的 UI 面板一律開新模組（不要塞進 `studio.py`）

`StudioWindow` 現在是 **6,017 行、246 個方法、363 個 `self.*` 名字**的一個類別
（2026-08-25 量的；寫下這一段時是 5,244 行 / 229 個方法 —— **三天長了 773 行**）。
它還沒到「非拆不可」，但**拆分壓力已經在影響新功能該放哪裡**了 —— F22 的 commit
訊息裡就寫著「不塞進已經 5000 多行的 `studio.py`」，那是一個人在替一個結構問題
繞路。

所以規矩寫下來：**一塊新的面板／畫布元件＝一個新模組**。F22 的
`ui/decide_panel.py`、F24 的 `ui/tree_panel.py`／`ui/tree_scene.py`、F25 的
`ui/route_badge.py`、F27 的 `ui/verdict_band.py`／`ui/results_table.py`、
F30 的 `ui/output_band.py` 已經都是這樣做的 —— 這一段只是把它從「這次剛好這樣
做」變成「本來就這樣做」。`studio.py` 留給**接線**（建 widget、接訊號、轉呼叫），
不留給內容。

⚠ **現在不要動 `studio.py` 本身**，但**理由已經換了一個**。
以前寫的是「那把尺（黃金值）是壞的」—— 那是真的，從 F19（08-21）到 08-23 兩天
沒有在守，而 **2026-08-23 已經重凍、三份全綠**（`docs/history/plans/F21-algo-and-roi.md`
§6 的後記、`SESSION_LOG.md`「黃金值重凍」）。**尺回來了，擋路的只剩順序**：
使用者定的是「先把引擎做對，再回頭產品化」。

所以真的要動的那一天，前置條件是**做得到而不是等得到**：先
`python tools/freeze_golden.py --check` 三份全綠（那就是「改了但數字沒變」的
唯一證據，而這個 repo 踩過六次「跑得完、有數字、而且是錯的」），再切
`widgets.py` 那幾群自繪圖示（最好拆、風險最低）。

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

**第二份 lot 走另一條路**（F15，2026-08-19；**F33 於 2026-08-25 續完**）。
那份缺的「點對點包含圖的 report」現在是 `output_char` 那張卡，而它需要的兩個
資料缺口也補了：**配不到的那一顆會留下來**（`pair_found = 0`，繼續走到判定樹
—— 「EBI 根本沒偵測到」是 characterization 要數的一類，不是一個錯誤）與
**die 內排名**（`pair_die_rank` / `pair_die_total`，母體是第二份的完整清單）。
詳見 [`docs/history/plans/F33-ebi-characterization.md`](docs/history/plans/F33-ebi-characterization.md)。
以下是它現在的樣子：

`pair_source` 這張卡上的
`Open data…` 掛的是「拿來對照的那一份」（EBI ↔ RSEM(API) characterization），
它掛在 `Dataset.sources[代號]` 上，**不取代目前的資料集** —— main 決定批次跑幾
顆、走哪一條 route、KLARF 寫回誰。CLI 是 `--source 代號=路徑`（可以重複）。
**卡片不自己 `open()`**：讀檔在 ingest 層（`core/ingest/pair_source.attach`），
路徑不進 recipe，而第二份的身分要進快取簽章 —— 否則換一份而簽章看不見就回舊
影像（鐵則 9）。

`d4t/ui/scope.py` 仍然是這類「暫時不給看」的**唯一**去處，
**而「入口長什麼樣」也住在同一份**（F11 Input-5）：

```python
SUPPORTED_KINDS = ("ebi_patch", "tiff_stack", "rsem", "folder")
HIDDEN_STEPS = ("align",)        # 收起來（引擎照認、舊 recipe 照跑）
                                 # ⚠ `feature_math` / `feature_fill` 2026-08-27
                                 # **刪掉**了（功能進了 `decide.let`）——
                                 # 先收起來、使用者確定之後再刪，那張對照表
                                 # 第一次跑完全程
SHOW_SAMPLE_ENTRIES = False      # 範例入口（見下）
INPUT_SOURCES = (...)            # 三顆 Open 的字、圖示、一句白話說明
ATTACHMENTS = (...)              # 掛在已載入 lot 上的附加檔（GLAS 匯出）
```

**加／改一個入口＝改 `INPUT_SOURCES`，不要動 UI。** 工具列的按鈕與空白狀態
（「一開始進去看到的那一塊」）上的每一列都是從這張表長出來的。以前它們是三份
各自寫死的文字，於是工具列有三顆 Open、空白狀態卻只講 KLARF —— 帶著一個資料夾
的圖片進來的人，在整個畫面最大的那一塊上找不到自己那條路。

`SHOW_SAMPLE_ENTRIES`（2026-08-16）管兩個入口：導覽與空白狀態上的
**「用範例資料試一次」**、工具列的 **「Templates…」**。範例 recipe 全部拿掉之後
它們都是死路（庫是空的、demo 產得出資料卻載不到 pipeline），而**按了撞牆的鈕
比沒有那顆鈕更糟**（推廣鐵則）。`run_demo` / `RecipeLibraryDialog` 一行都沒動。

`tests/test_ui_input_kinds.py`（原 `test_ui_patch_only.py`）鎖住四種都進得來、
沒有 KLARF 的兩種會講出來、而**「暫時收起來」的機制還在**。

**收起來（`HIDDEN_STEPS`）／刪掉／改名是三件不同的事，判準都是使用者說了哪一
句話**，不是你覺得那張卡有沒有用。2026-08-18 一天之內三種都發生過：

| 使用者說的 | 處置 | 代價 |
|---|---|---|
| 「之後真需要我再回來」（`align`）| **收起來**：卡片庫看不到，`get_step` 拿得到、舊 recipe 照跑、黃金值不動 | 加一個字串 |
| 「不需要這功能」（`cell_period`）／「完全沒用」（`pattern_ref`）| **刪掉**：`REGISTRY` 裡沒有，舊 recipe 開起來是一條 `unknown-step` | 依賴它的 fixture / 黃金值要一起處理 |
| 「拿回來 不過要改名字」（`golden_cell` → `pattern_ref`）| **改名**：要一道遷移 | key **加上**它寫出來的 feature 名（那些會被打進分數表達式）—— 只換一半等於沒換 |
| 「名字剪短一點」（`CD measure` → `CD`）| **只改 `label`** | 零：`key` 是 recipe 的鍵、feature 名是表達式的變數名，兩者都不准動 |

同一張卡（`pattern_ref`）走完了**刪掉 → 量代價 → 要回來 → 改名 → 收起來 →
刪掉**六步，最後一步是 2026-08-20（F16，使用者：「完全沒用，請直接拿掉」）。

**而這一次代價真的付了**，值得記住價差長什麼樣：

| | 收起來（2026-08-18） | 刪掉（2026-08-20） |
|---|---|---|
| 動到什麼 | 一個字串 | 卡片、測試、fixture 的 rsem route、一組黃金值 |
| rsem route 的準確率 | 24/24（照跑）| **每一顆都判 bin 0**（seed 11/3/21 皆 12/24，而那 12 顆正好是沒有缺陷的那些）|
| 那條 route 還證明什麼 | 「單張影像也判得出缺陷」 | 只剩「跑得完、算得出分數」|

**不確定的時候先收起來**：成本是零，回復的成本是拿掉一個字串。使用者確定之後
再刪 —— 上面那張表就是「確定」值多少錢。

> ⚠ **`d4t/core/algo/period.py` 與 `algo/golden.py` 都不要刪。**
> `pattern_ref` 走了之後**呼叫者只剩 `algo/template.py` 一個**（疊 Golden Cell
> 模板要 `stack_cells` 與 `estimate_period` / `choose_origin`）。2026-08-18
> 有一小時它們一個呼叫者都沒有 —— 那正是這種模組被當成死碼順手清掉的時候，
> 而「只剩一個」離那個狀態只有一步。
> `estimate_period` / `choose_origin` 的相位搜尋是之後做 **pattern-frame ROI**
> 的唯一工具（patch 是以 defect 為中心裁切的，晶格相位逐顆不同；見
> `docs/history/plans/F7-canvas-and-taxonomy.md` §4）。
> 便利貼：`tests/test_ui_input_kinds.py::test_period_module_is_not_orphaned`。

CLI 不受影響：`python -m d4t run` 照樣跑得動 rsem recipe。

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
