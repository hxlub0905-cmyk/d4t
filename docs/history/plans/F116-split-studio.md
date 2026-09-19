# F116 — 拆 `studio.py`：`StudioWindow` 只留組裝與接線，內容搬進 controller

狀態：**已收斂（2026-09-19）** —— 六步全部做完，`studio.py` 7,686 → **4,347** 行
（−43%）、方法 293 → **197**、`self.*` 433 → **266**。逐輪的決定與數字在
[`SESSION_LOG.md`](../../../SESSION_LOG.md) 的 F116 那一段。

**這一份留著的價值在 §3（controller 的長相）與 §6（搬家會安靜做錯的六件事）** ——
下一個要從 `studio.py` 搬東西的人先讀那兩節。§8 記著「≤ 4,000 行」那條線為什麼
沒達成、以及它該換成什麼。

> 起點 commit `3329659`。下面的數字都是那一刻量的；動手前用 §6 那支腳本重量一次，
> 對不上就以重量的為準（這一份不是數字的家，`tests/test_size_ceilings.py` 才是）。

---

## 1. 為什麼、要做到哪

`CLAUDE.md` §4 已經寫了「`studio.py` 留給**接線**，不留給內容」，而 `HARD_CAPS`
讓那一格只准往下。F110／F114 各往下搬了一小塊，證明這條路走得通；這一份把它
**有計畫地走完**。

| | 現在 | 第 1+2 步之後（估） | 全部做完（估） |
|---|---|---|---|
| `studio.py` 行數 | 7,686 | ~5,900 | ~3,500 |
| `StudioWindow` 方法數 | 293 | ~230 | ~120 |

**目標**：每一塊有自己狀態與行為的 UI，住在自己的模組；`StudioWindow` 只做三件事 ——
建出 controller、把 signal 接起來、提供測試與其他模組要用的門面。

**非目標（這一份不做，做了就違規）**：

* **不改任何行為。** 方法本體逐字搬，只把 `self.` 換成 `self.w.`（屬於視窗的）或
  留 `self.`（屬於 controller 自己的）。改名、合併、順手修 bug 一律另開一輪。
* 不動 `d4t/core`。不動 recipe JSON。不動任何使用者看得到的字。
* 不重寫 toolbar／layout 的外觀（第 2 步是搬家，資料表驅動是可選的附加，見 §4）。

---

## 2. 分析：哪一塊跟誰黏在一起

用 ast 量 `StudioWindow` 每一段（以 `# ====` 區段頭為界）：擁有哪些 `self.*`、
往外叫了別段哪些方法、被別段叫了哪些。

| 區塊（行號約） | 行 | 方法 | 往外叫 | 被叫 | 判讀 |
|---|---|---|---|---|---|
| 右下角：卡片儀表 F7-17（5426–6343）| 866 | 45 | **7** | 13 | **最獨立、最大** → 第 1 步 |
| 介面組裝（694–1786）| 1,028 | 22 | 34 | 11 | 機械式搬移，但設了 86 個 `self.*` → 第 2 步 |
| Gallery ＋ 回溯（6871–7134）| 241 | 15 | 5 | 10 | 低 → 第 3 步 |
| 第二份 lot ＋ 對話框（7237–7587）| 319 | 17 | 9 | 12 | 中 → 第 4 步 |
| 試跑 ＋ Output（6390–6871）| 460 | 16 | **17**（一串 `_refresh_*`）| 9 | 中高：要改成 signal → 第 5 步 |
| 畫布連線 ＋ 區域線（3325–3725）| 384 | 14 | 17 | 6 | **最黏**，測試引用最多 → 第 6 步或不動 |
| model → UI（2101–3027）| 883 | 37 | — | — | 這就是「接線」本身，**留在 Studio** |

另外兩個數字決定了做法：

* **方法裡被賦值的 142 個 `self.*`（跟 `HARD_CAPS` 那格 433 是不同量法，不要拿來比）裡有 37 個被兩段以上寫入**（`model`、`selected_node`、`dataset`、
  `trial_results` ……）。前四步**不處理**，controller 一律透過 `self.w.xxx` 讀寫；
  第 5 步才考慮收進一個帶 signal 的狀態物件（§5）。
* **測試直接用了約 126 個 `StudioWindow` 的方法**（`_on_edge_added` 191 處、
  `select_node` 132、`add_card_after` 119、`load_dataset_path` 101 ……）。所以每一步
  都要先量「測試用到的名字」，搬完還答得出來（§6）。

### 第 1 步那一塊其實是三小塊

「卡片儀表」區段底下混了三件事，**分三個 commit**（同一個 PR 可以）：

| 小塊 | 方法（起點行號） | 去處 |
|---|---|---|
| 1a 儀表本身 | `show_bottom_page` `bottom_page` `inspector` `_install_inspector` `_connect_inspector` `_on_calibrate_requested` `_on_calibrated` `_on_param_requested` `_on_charts_requested` `_refresh_charts_window` `_on_chart_style_changed` `_on_select_requested` `_on_measure` `_on_measure_ended` `_refresh_inspector` `_refresh_curve_backdrop`（5427–5748）| `ui/gauge_panel.py` |
| 1b 區域檢查 ＋ 特徵表 | `_refresh_region_button` `open_region_check` `_on_region_ready` `_apply_region_results` `profile_panel` `profile_panel_visible` `_feature_about` `_feature_model` `_feature_specs` `_feature_sections` `_highlight_features`（5749–5995）| 併進 `ui/gauge_panel.py`，或另開 `ui/feature_pane.py`（看搬完多長，>600 行就分）|
| 1c 影像流選擇 ＋ 畫在圖上的東西 | `_default_stream` `_populate_streams` `_default_compare_stream` `_show_current_stream` `region_overlay` `_overlay_region_names` `region_overlay_names` `_refresh_region_overlay` `measure_marks` `heat_tiles` `_refresh_measure_marks` `_marks_solid` `_focus_box_index` `_defines_regions` `_picks_a_center` `_center_rects` `_on_stream_changed` `_on_stream_b_changed`（5996–6342）＋ 並排比對三支（6343–6389）| `ui/preview_overlays.py` |

---

## 3. controller 的長相（每一步都一樣）

```python
# d4t/ui/gauge_panel.py
from PySide6.QtCore import QObject

class GaugePanel(QObject):
    """右下角卡片儀表。從 StudioWindow 搬來（F116 第 1 步），行為零改動。"""

    def __init__(self, win: "StudioWindow") -> None:
        super().__init__(win)          # ⚠ 一定要掛 parent，理由見 §7-1
        self.w = win
        self._inspector = None         # 原本 StudioWindow._inspector 的家搬到這

    def refresh(self, result) -> None: # 原 _refresh_inspector，本體逐字
        ...
```

`StudioWindow.__init__` 裡在**介面組裝完之後**：`self.gauges = GaugePanel(self)`。

規矩：

1. **狀態跟著行為走。** 只被這一塊讀寫的 `self.*`（例 `_inspector`、`_compare_on`、
   `_view_syncing`）搬進 controller；被別段也寫的留在視窗，controller 用 `self.w.`。
2. **controller 之間不直接互叫。** 要叫另一塊就走 `self.w.<門面>` 或 signal —— 否則只是
   把一個大球拆成幾個互相纏住的小球。
3. **門面**：測試或別的模組用到的名字，在 `StudioWindow` 留一行轉呼叫
   `def inspector(self): return self.gauges.inspector()`。
   用得少的名字**改測試**不留門面 —— 門面也算方法數。
   **判準改成「用到它的測試**檔案**數」**（第 1 步量出來的）：≥2 個檔案就留門面，
   只有一個檔案就改測試。呼叫點數答錯過兩次 —— `_feature_sections` 4 處但全在
   同一檔（改測試比留門面便宜），`region_overlay` 8 處也全在同一檔。
   ⚠ **門面的簽章要跟 controller 那一支一模一樣**：憑印象寫會得到一個
   `takes 1 positional argument but 2 were given`，而它只在跑到那一條測試時才現形。
   門面集中放在 `StudioWindow` 最後一段 `# 門面（F116）`，一眼看得出哪些是轉呼叫。
4. **signal 的接線留在 `studio.py`**（`_connect` 那一段），controller 只提供 slot。
   那正是 `studio.py` 該留的東西。接在**門面**上的那一條（例
   `calibrate_worker.ready.connect(self._on_calibrated)`）可以留在原地不動 ——
   門面是類別屬性，建構順序碰不到它。
5. 模組頂部照慣例寫 `# d4t UI — authored <日期> (F116 第 n 步).` 與一段「為什麼自己一個模組」。

---

## 4. 六步

每一步 = 一個 PR，照 §6 的檢查清單走。**一步做完、CI 綠、合進 main，再開下一步。**

**第 1 步：卡片儀表**（§2 的 1a／1b／1c）。✅ **做完**（2026-09-19）。

第 1 步的結果：`studio.py` 7,686 → **6,782**（−904）、方法 293 → **256**、
`self.*` 433 → **389**。三個模組：`ui/gauge_panel.py`（儀表 ＋ 特徵表，
`bottom_stack` 的兩頁）、`ui/preview_overlays.py`（影像流選擇 ＋ 畫在圖上的東西），
以及**沒有新開的那一個** —— 區域跨顆檢視那四支進了既有的 `ui/region_check.py`
（它用的每一個東西本來就在那裡，而那顆按鈕住在預覽區）。原本寫的
`ui/feature_pane.py` **沒有出現**：併進去是 609 行，剛好踩線，而回頭問
「那一塊該不該是一塊」得到的答案是照**畫面上的位置**分，不是照行數分。

**第 2 步：介面組裝** → `ui/studio_layout.py`。✅ **做完**（2026-09-19）。

第 2 步的結果：`studio.py` 6,782 → **5,792**（−990）、方法 256 → **248**。
搬的是**七支** `_build_*`（計畫書原本只列五支 —— `_build_score_pane` 與
`_build_params_row` 是 `_build_body` / `_build_preview_pane` 叫的，同一族）
加上 `_tool_button` 與它唯一的使用者 `_GlyphToolButton`，以及四個版面常數
（`COLUMN_SIZES`、`DEFAULT_TRIAL_N`、`DEFECT_COMBO_MAX`、`STREAM_COMBO_MAX`）。
**沒有留任何門面** —— 沒有人從外面叫那幾支，`__init__` 改成
`studio_layout.build_toolbar(self)`。`COLUMN_SIZES` / `DEFAULT_TRIAL_N` 在
`studio.py` 用 `# noqa: F401` 轉出去，因為測試是用 `studio_mod.` 拿的。

`_load_sizes` / `_save_sizes` **留在 `studio.py`**：它們要問
`_running_under_pytest()`（那一支的家在 studio.py，而且測試會 monkeypatch 它），
所以 `build_body` 在**函式裡** import 它們。

⚠ **這一步之後，「那個名字還在不在視窗上」不能再問 `studio_window_attributes`
那一格。** 那一格數的是 `studio.py` 這個檔案裡的 `self.*`，而那 86 個名字現在是
在 `studio_layout.py` 裡用 `win.x = …` 設的 —— 數字掉了 66 個，名字一個都沒動。
要問名字用 `tools/studio_surface.py`（它現在會讀 `d4t/ui/*.py` 裡的 `win.x = …`
與 `self.w.x = …`）。
`_build_toolbar`（275 行）、`_build_preview_pane`（374）、`_build_body`（120）、
`_build_progress`、`_build_shortcuts` 變成模組層函式 `build_toolbar(win) -> None`，
照 `open_dialogs.py` 的慣例吃 `window`。它們**照舊在 win 上設屬性**（86 個名字不動，
測試大量用），所以這一步減的是行數與方法數，不是 `self.*` 數 —— 那是預期的。
可選附加（**另一個 commit**，要使用者點頭）：toolbar 改成一張資料表驅動，跟
`scope.INPUT_SOURCES` 同一個模式。

**第 3 步：Gallery ＋ 回溯面板** → `ui/gallery_controller.py`。✅ **做完**（2026-09-19）。

第 3 步的結果：`studio.py` 5,792 → **5,434**（−358）、方法 248 → **235**。
15 支方法，加上**縮圖那一條鏈**（`THUMB_CHANNEL_PRIORITY` → `thumb_channel` →
`load_thumb` → `ThumbWorker`，原本散在 `studio.py` 的模組層，而唯一的使用者是
Gallery）。`studio.py` 用 `# noqa: F401` 把那三個名字轉出去 —— 前兩個在它的
`__all__` 裡，而測試是用 `studio_mod.` 拿的。

`thumb_worker` 跟著搬，而且**由 controller 自己建、自己接**：它兩端都在自己家裡，
不是 §3-4 講的那種「視窗的 widget 發、controller 收」。

⚠ **`_items_by_id` 沒有跟著搬**（這一份原本寫它要搬）：它是 `_on_dataset_loaded`
寫的，而那一段不在這一族裡 —— §3-1 說被別段也寫的留在視窗。搬了的話會變成
別的段落往 controller 裡塞一個欄位，那比留著更難讀。

門面兩支：`show_gallery`（工具列那顆鈕與 `Ctrl+Shift+R` 都接它，而且
`studio_layout.py` 用 `win.show_gallery`）、`results_visible`（14 處／2 個檔案）。
`_on_defect_activated` **沒有**留門面 —— 這一份原本寫它要留，但它的三個呼叫端
全部是 `_wire_widgets` 裡的接線，而接線本來就留在 `studio.py`，直接指到
`self.gallery_ctl._on_defect_activated` 就好，測試一處都沒有用到它。

**第 4 步：第二份 lot ＋ recipe 的存開對話框**。✅ **做完**（2026-09-19）。

第 4 步的結果：`studio.py` 5,434 → **5,135**（−299）、方法 235 → **221**。

* recipe 的開／存三支 ＋ `RECIPE_SUFFIX` → **既有的** `ui/open_dialogs.py`
  （同一個「只問路徑、做事交給 `window`」的契約，照計畫）。
* **`ui/pair_source_ui.py` 沒有出現** —— 那一族搬進的是
  `ui/attach_sources.py`，而且 **GLAS 匯出那兩支（`_on_open_gds` /
  `attach_gds_export`）一起搬了**。理由是它們的形狀一字不差：**問一個路徑 →
  交給 ingest 層 → 把結果講成一句話 → 把量到的名字填回卡片**。只搬一半的話，
  `對話框` 那一段會剩下兩支名字對不上段名的東西，而模組名會比內容窄。
  `_source_id_from`（模組層的小工具）跟著走 —— 它唯一的使用者在這一族裡。
* **一支門面都沒留**：接線改成 `partial(open_dialogs.save_recipe, win)`，
  跟那三顆 Open 鈕同一個形狀。

**留在 `studio.py` 的三支**（它們在那一段裡只是鄰居，不是「掛第二份東西」）：
`_number_info`、`_dynamic_choices_for`、`sources_for_run`。
`_carry_filled` 也留著 —— 換資料集時 `_on_dataset_loaded` 會清它（§3-1）。

⚠ **第二種漏法（這一輪新的）：組出來的名字。** `_on_source_requested` 用
`getattr(self, "_on_open_%s" % att_key)()` 分派到 `_on_open_gds` —— 那個名字是
`"_on_open_"` 加上一張表裡的值拼出來的，**沒有任何靜態掃描找得到它**。
`ruff`、`studio_surface --check`、`import` 全綠，只有「選到 layout(GDS) 卡再按
那顆鈕」那一條路會炸（`test_ui_f14_input_on_the_card` 抓到）。

⚠ **第 3 步加的那一關當場就賺回來了**：`--check` 一跑就列出 `studio_layout.py`
那 5 行還在叫 `win._on_open_recipe` / `win._on_save_recipe` / `_on_save_recipe_as`
—— 那是「按工具列那顆存檔鈕就 AttributeError」，而**一條測試都不會紅**
（沒有人去按那顆鈕）。修完再跑就乾淨了。

**第 5 步：試跑 ＋ Output** → `ui/run_controller.py`。✅ **做完**（2026-09-19）。

第 5 步的結果：`studio.py` 5,135 → **4,785**（−350）、方法 221 → **210**。
15 支搬走，門面四支（`run_trial` / `run_all` / `write_outputs` / `rerun` ——
這個視窗的**公開動詞**，光 `run_trial` 就有 44 處／13 個測試檔）。
鐵則 11 的三道關（沒有結果／部分結果／`inplace` 先問）整條住在新模組裡，
`test_ui_write_only_on_run_all.py` 與 `test_rerun_decision.py` 15 條全綠。

⚠ **signal 那一段沒有照做，而那是這一步最重要的決定。**
這一份原本寫「改成 controller 發 `trial_finished(results)`，`studio.py` 把它接到
那一串 refresh」。真的讀了 `_apply_trial_results` 那 115 行之後，**前提不成立**：
那不是一串可以搬出來的 refresh —— `_refresh_verdict` / `_refresh_spread` /
`_refresh_decide_counts` 跟「這批數字怎麼變成一句話」「要不要寫出去」是**交織**
的，而且每一段前面都釘著一句 ⚠（「判定段要先算，順序反過來圖上染的是上一批的
類別 —— 跑得完、有顏色、而且是錯的」）。要保住那個順序，signal 得在精確的點發
好幾次，那只是把直接呼叫包一層。

所以刀切在**另一個地方**：`_apply_trial_results`（＝「結果到了，畫面怎麼變」）
**留在視窗**，跟它叫的那一串 `_refresh_*` 住在一起；controller 只留「怎麼發動、
怎麼寫」。於是這一族往外就剩**一個**呼叫，而那正是這一份想用 signal 換到的東西。

**連那一個也沒有做成 signal**：它有三個發射點，而 Qt 的 direct connection 雖然
同步，例外卻會被 Qt 的 hook 吃掉、不往上傳。測試大量用 `run_trial(sync=True)`，
`_apply_trial_results` 裡爆掉的東西現在會讓那條測試**當場紅**；包成 signal 之後
只會印在 stderr 上。這個 repo 最怕「跑得完、有數字、而且是錯的」。

⚠ **順序又咬了一次**（§7-2 的實例）：`studio_layout` 跑在 controller **之前**，
所以它裡面 `win.run_ctl._on_trial_clicked` 這種寫法會在**建工具列的當下**查
`win.run_ctl` —— 建視窗就 AttributeError。指到 controller 的 slot **一律包一層
`lambda`**（查詢延到按下去那一刻）。那條規矩寫進 `studio_layout.py` 的檔頭。

**第 6 步：畫布連線 ＋ 區域線** → `ui/canvas_edges.py`。✅ **做完**（2026-09-19，
評估後決定做）。

第 6 步的結果：`studio.py` 4,785 → **4,347**（−438）、方法 210 → **197**。

評估推翻了這一份原本的兩個判斷：

1. **「它本質上就是接線」—— 量出來不是。** 437 行裡，六支**規則**型的方法就佔
   284 行（65%）：`_point_at_stream` 75、`_apply_edge_removed` 69、
   `_connect_region` 47、`connect` 40、`unpoint_stream` 27、`_param_for_stream` 26。
   真正的 handler 只有 67 行（15%）。那 284 行寫的是鐵則 10 本身 ——
   一個輸入埠只能有一條線、區域線住在 `recipe.edges`、拉一條線＝一步復原。
2. **「測試引用最重 ⇒ 最危險」—— 反了。** 這一整輪真正咬人的是**沒有測試按過的
   那顆鈕**（第 4 步的 GDS 分派、第 3 步的 `region_check.py` 兩行接線）：
   ruff 綠、import 綠、`--check` 綠，只有使用者真的按下去才炸。
   `_on_edge_added` 有 **191 處／21 個測試檔**，意思是每一個錯誤都會當場紅 ——
   按這一輪量到的證據，它是剩下**最安全**的一塊。耦合也最低（只碰 11 個外部名字，
   儀表那一族 23、跑那一族 34）。

**形狀**：模組層函式吃 `win`（這一族沒有任何自己的狀態）。族外叫得到的改成公開名，
而 `StudioWindow` 上的門面**留舊名字** —— 所以那 191 處測試一個字都沒有改。

---

## 5. 共用狀態 —— **評估完了：不做**（2026-09-19）

37 個多方寫入的 `self.*` 本來要在第 5 步之前評估「收進一個帶 signal 的
`StudioState`」。五步走完，答案是**不做**，理由是量出來的：

* **它沒有痛。** 五個 controller 一路用 `self.w.<名字>` 讀寫共用狀態，
  五步下來因為它出過的錯是 **0 次**。真正出錯的是**名字搬走之後沒人跟上**
  （§6 那三條新檢查守的），而 `StudioState` 一條都擋不到 —— 那些是接線。
* **它會讓「誰在寫」變模糊。** 現在 `grep self.w._last_run` 就看得到全部的
  讀寫點；收進一個帶 signal 的物件之後，寫的人變成「發了一個 signal」，
  而讀的人變成「接了一個 slot」，查一條資料流要跳三個檔案。
* **它跟「行為零改動」不相容。** 改「住哪」是搬家，改「怎麼通知」是重寫 ——
  這一份 §1 的第一條就是不准在同一輪做第二件事。

要做的話它是**自己一輪**（F118+），而且前提是先有一個它真的會修好的 bug。

---

## 6. 每一步的檢查清單

動手前：

- [ ] `python tools/freeze_golden.py --check` 三份全綠（`CLAUDE.md` §4 的前置條件）
      ⚠ **2026-09-19 在家用機上第三份紅**，而那**不是**這個 repo 的行為變了：
      `dual_route_basic__make_sample` 的 `align_score` 差在第 4 位，而
      `align_dx`／`align_dy`（17 位）與每一個下游特徵逐位元組相同，
      `d4t/core/algo/align.py`（算那個分數的地方）自從凍結以來一個位元都沒動
      —— 同樣的程式碼配同樣的輸入吐不同的數字，剩下的變數只有這台機器的
      OpenCV build（`final_score` 吃 `cv2.warpAffine` 的殘差）。
      `freeze_golden.py` 的說明本來就寫著「用途是同一台機器上、重構前後的比較」。
      所以第 1 步的基準**凍在 scratchpad**（不覆蓋 repo 裡那三份，它們帶著
      跨環境的歷史），三個 commit 每一個都對過、逐項相同。
- [ ] `python tools/studio_surface.py --save before.json`（腳本見下，第 1 步順手加進 `tools/`）
- [ ] 在 `docs/PITFALLS.md` 搜 `Qt`、`segfault`、`parent`、`signal`、`deleteLater`、`scroll_host`

搬的時候：

- [ ] 方法本體逐字搬；diff 裡除了 `self.`→`self.w.` 與縮排，**不應有別的變化**
      （§3 的範例把 `_refresh_inspector` 寫成 `refresh` —— **不要照那個做**，
      §1 說改名另開一輪，而這一條才是檢查得出來的）
- [ ] **切區間要從裝飾器那一行開始**：`ast` 的 `lineno` 指的是 `def`，照它切會
      把 `@property`／`@staticmethod` 留在原地，而症狀是門面回一個 bound method
      （不是 ImportError）。第 1 步兩支：`profile_panel`、`_overlay_region_names`
- [ ] **單獨當參數傳出去的 `self`** 機械式取代抓不到：`UniformityWindow(self)`、
      `ProfilePanel(self)`、`RegionCheckWindow(self)` 的 parent 要是**視窗**
      （controller 是 QObject，不是 QWidget）。搬完 grep 一次 `self(?!\s*\.)`
- [ ] 搬完 grep 一次每一個 `self.w.<名字>`，確認它真的還在 `StudioWindow` 上
      —— 跨 controller 的狀態（第 1 步是 `_compare_on`）要走門面（§3-2）
- [ ] ⚠ **組出來的名字沒有任何掃描找得到**：`getattr(self, "_on_open_%s" % key)`
      這一種（`studio.py` 的 `_ATTACHMENT_CARDS` 分派就是）。`ruff`、
      `studio_surface --check`、`import` 在第 4 步全部是綠的，只有「選到
      layout(GDS) 卡再按那顆鈕」那一條路會 AttributeError。搬一族之前先
      `grep 'getattr(self, "'`，看看有沒有人用字串拼它們的名字。
- [ ] **`d4t/ui/` 裡別的模組也可能在叫搬走的那個名字**（不只 `studio.py` 與
      `tests/`）：`region_check.py` 與 `studio_layout.py` 都是吃 `win` 的模組，
      而它們的 `win.<名字>(…)` 是**接線** —— 只有使用者真的按下那一顆才會炸。
      第 3 步漏了三處。`tools/studio_surface.py --check` 現在會掃這一關
      （判準是「這一輪搬走的名字」，所以 `--save` 的基準要是新版的）
- [ ] **搬到模組層函式的時候，`self` 一律變成 `win`（連當參數傳的也是）**，而
      那一族沒有自己的狀態 —— 全部設在視窗上。⚠ 先用 `tokenize` 確認要搬的
      區間裡**沒有任何字串含 `self`**，再做整段取代（第 2 步搬 922 行，靠這一步
      才敢一次換掉）
- [ ] 每個搬走的名字：測試用得多 → 留門面；用得少 → 改測試
- [ ] 新模組不 import `studio`（型別註記用 `TYPE_CHECKING` 或字串）

搬完：

- [ ] `python tools/studio_surface.py --check before.json` —— 測試用到的名字 `hasattr` 都還答得出來
- [ ] `ruff check`、`python tools/typecheck.py`
      ⚠ ruff 會報一批 `F401`（搬走之後 `studio.py` 那幾個 import 沒人用了）。
      **`--fix` 之前一個一個查**（`CLAUDE.md` §4）：第 1 步有一個是
      `tests/` 用 `studio_mod.FEATURE_OWNER_KEY` **別名**拿的，grep
      `studio.FEATURE_OWNER_KEY` 掃不到。那一個修的是測試（那個鍵的家在引擎，
      `ui.studio` 只是剛好 import 過它），不是加 `# noqa`
- [ ] 相關的 `test_ui_*` 逐檔跑（`python tools/run_tests.py` 或只挑那幾支），再跑核心批
- [ ] `python tools/freeze_golden.py --check` 再一次
- [ ] **開 Studio 手動走一遍**那一塊：載範例資料 → 選卡 → 看儀表／Gallery／試跑。測試全綠而畫面壞掉（signal 沒接、物件被回收）是這種搬家最常見的死法
- [ ] `tests/test_size_ceilings.py` 的 `HARD_CAPS` 三格**在同一個 commit 往下調**到新值（反向測試會逼你）
- [ ] 新模組的上限：若 >1,000 行，在 `FILE_CEILINGS` 登記
- [ ] `git add -A && python tools/release.py && git add -A`，更新 `SESSION_LOG.md`

### `tools/studio_surface.py`（第 1 步加進 repo）

stdlib-only，量兩件事：`StudioWindow` 的方法／`self.*`，以及**測試裡以視窗物件存取的名字**。
`--check` 時對 `before.json` 裡每個被測試用到的名字，確認搬完後仍是
`StudioWindow` 的方法、或在 `self.*` 裡被設過；答不出來的列出來並回非零。

```python
"""量 StudioWindow 的表面：方法、self.* 名字、測試用到的名字（F116）。"""
from __future__ import annotations
import argparse, ast, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STUDIO = REPO / "d4t" / "ui" / "studio.py"
# 測試裡指向 StudioWindow 的常見變數名；漏抓的話加在這裡
_VAR = r"(?:w|win|window|studio|sw|self\.w|self\.win)"

def shape():
    tree = ast.parse(STUDIO.read_text(encoding="utf-8"))
    cls = next(c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "StudioWindow")
    meths = {f.name for f in cls.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    attrs = set()
    for node in ast.walk(cls):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "self" and isinstance(node.ctx, ast.Store)):
            attrs.add(node.attr)
    return meths, attrs

def used_by_tests(names):
    pat = re.compile(r"\b%s\.(\w+)" % _VAR)
    hits = {}
    for f in sorted((REPO / "tests").glob("*.py")):
        for m in pat.findall(f.read_text(encoding="utf-8")):
            if m in names:
                hits[m] = hits.get(m, 0) + 1
    return hits

def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save"); g.add_argument("--check")
    a = ap.parse_args(argv)
    meths, attrs = shape()
    if a.save:
        used = used_by_tests(meths | attrs)
        Path(a.save).write_text(json.dumps(
            {"methods": len(meths), "attrs": len(attrs), "used": used},
            ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print("methods=%d attrs=%d used_by_tests=%d" % (len(meths), len(attrs), len(used)))
        return 0
    before = json.loads(Path(a.check).read_text(encoding="utf-8"))
    missing = sorted(n for n in before["used"] if n not in meths and n not in attrs)
    print("methods %d -> %d, attrs %d -> %d"
          % (before["methods"], len(meths), before["attrs"], len(attrs)))
    for n in missing:
        print("  ✗ 測試用到 %s（%d 處），StudioWindow 上已經沒有" % (n, before["used"][n]))
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
```

⚠ 這是**靜態**的近似：屬性若是在 controller 裡 `setattr(self.w, ...)` 設的它看不到，
會誤報 —— 誤報就改成在 `studio_layout` 裡明寫 `win.xxx = ...`（本來就該這樣寫）。
加進 repo 時照 `tools/` 的規矩：stdlib-only、`ruff check` 過、`release.py` 會更新 `FILELIST.txt`。

---

## 7. 已知的風險

1. **Qt 物件擁有權。** controller 若不是視窗的 `QObject` 子物件、又沒有人持有參考，
   Python 端會被回收，接在它 bound method 上的 signal 會**安靜地不再觸發**（不是例外）。
   所以 §3 規定一律 `super().__init__(win)` 且 `self.w.<名字> = controller`。
2. **建構順序。** controller 要在介面組裝**之後**建（它讀 `self.w.bottom_stack` 之類）；
   但 `_connect` 要在 controller **之後**跑。第 1 步就把這個順序在 `__init__` 裡寫清楚、加一句註解。
3. **`fit_screen.scroll_host` 要在建構時掛**（`CLAUDE.md` §4 F91）。第 2 步搬
   `_build_*` 時不准把「先建再搬進捲軸」的順序改掉 —— 那是 segfault。
4. **測試的屬性存取。** `hasattr` 判準（`CLAUDE.md` §4）只靠 grep import 不夠，
   用 §6 的腳本。
5. **尺被簽成流水帳。** `HARD_CAPS` 只准往下 —— 這一份的每一步都應該讓它**明顯**往下；
   哪一步如果淨值沒降（門面留太多），代表那一塊不該這樣拆，停下來回報，不要調高上限。

---

## 8. 什麼叫做完

* ✅ 六步都做完了，每一步一個 commit 對、一條分支、三把尺在同一個 commit 裡往下調。
* ⚠ **`studio.py` ≤ 4,000 行：沒有達成（4,347），而那個數字當初是在還沒看到形狀
  的時候訂的。** 剩下的 4,347 行裡：

  | 段 | 行 | 該不該再搬 |
  |---|---|---|
  | `model → UI` | 927 | **不搬** —— 這一份 §2 自己寫的「這就是接線本身」 |
  | 卡片庫 / 流程（第 6 步之後） | 662 | 可以再看，但它是 30 幾支小方法，不是一塊 |
  | 資料集 309 / 預覽 301 / 主題 281 | 891 | **這裡才是下一個 −300 的來源**（預覽最不黏：23 個外部名字）|
  | 其餘 11 段 | 各 ≤ 199 | 已經符合「沒有一段超過 ~150 行的內容」的精神 |

  要壓到 4,000 只要再搬一塊「預覽」（−301 → 約 4,050）。**但那是一輪自己的事**，
  而且要先問它是不是一塊 —— 不要為了一個當初隨手訂的數字再開一刀。
  **建議：把這條線改成「`model → UI` 以外沒有一段超過 300 行」**，那是這六步
  真正在守的東西，而現在已經成立。
* ✅ 三份黃金值（本機基準）與整套測試綠（紅的 10 個檔案在起點 commit 上逐條一樣）。
* ✅ 手動走過 Studio **41 條**，而且是「在起點的樹上跑同一支、`diff` 空的」那種。
* 這一份可以改成「已收斂」搬去 `docs/history/plans/` —— 但**先把六條分支合進
  main**，那才是 §4「一步做完、CI 綠、合進 main」真正的終點。
