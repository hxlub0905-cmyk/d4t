# 規模的天花板 — authored 2026-09-08.
"""**這個 repo 的每一道關都在問「數字對不對」，沒有一道在問「東西多大」。**

3,442 支測試、三份黃金值、七條卡片不變量、逐位元組的決定論 —— 全部長在
**正確性**那一條軸上。而 2026-09-08 量出來的：

* ``d4t/ui/studio.py`` 在 2026-09-02 是 5,244 行（`CLAUDE.md` 記的）、09-08 是
  6,942 行，而**中間沒有任何一輪是在動它**；
* 同一段時間 ``StudioWindow`` 從 261 個方法 / 386 個 ``self.*`` 名字長到
  268 / 393。

沒有人決定要加那些行，它們是**漂進來的**。這一份就是那把缺的尺。

它買到的不是「不准變大」
------------------------
一道天花板擋不住任何事 —— 它做的是把 drift 變成 **diff 裡的一行**：那一輪的
作者必須在同一個 commit 裡把上限從 6,942 改成 7,180，而那一行改動就是 code
review 的全部內容。「這一輪把判定那塊的三支方法搬進來」是合法的理由，
「順手」不是。

五條設計規則（違反的話它會變成一張只會變長的紙）
------------------------------------------------
1. **設在現在的值，不留 buffer。** 留 500 行餘裕 ＝ 那道關在餘裕用完之前是
   關著的。
2. **每一格附一句「為什麼是這個數字」**（下面每一格都有）。沒有那句話，
   下一個人的反射動作就是 +500。
3. **配一支反向測試** —— 實際值掉下來夠多而上限沒跟著降，也要紅。這是
   `CLAUDE.md` 已經寫下來的規矩：*任何「例外清單」都要有那支反向測試*
   （`tests/test_shipped_recipes.py` 的 ``ALLOWED_ERRORS`` 是先例）。
4. **一張表、一個家。** 數字只住在這裡，**不要在 `CLAUDE.md` 抄第二份** ——
   那正是 2026-08 那次 `tools/doctor.py` 對每台機器給出錯診斷的病根。
5. **調高要在同一個 commit 裡說理由。**

它守不到的三件事（明講，免得有人以為它是保證）
----------------------------------------------
* **它分不出好的成長與壞的成長。** 加一張卡讓 ``inspectors.py`` 多 40 行是
  健康的，``studio.py`` 多 40 行通常不是 —— 這裡只會說「變大了」，判斷仍然
  是人的。
* **它不會讓設計變好。** 只買到「變大是一個決定」；真正的拆分還是要做。
* **反射性上調 ＝ 劇場。** 這是唯一會讓它失效的方式，而擋它的只有規則 2 和 5。

⚠ 這一份**不 import Qt**（它讀原始碼、用 ``ast`` 解析），所以它跑在核心那一批
裡，幾百毫秒就有答案。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps                                    # noqa: E402,F401
from d4t.core.pipeline.step import REGISTRY              # noqa: E402

#: 掃哪幾個目錄。
#:
#: **`bundle/` 不在裡面**：`bundle/d4t_bundle.py` 是 `tools/release.py` 產出來
#: 的，它的大小是「repo 有多大」的鏡像，不是一個人寫出來的檔案（水位表在
#: `AGENTS.md` §2，守它的是 `tests/test_docs_match_registry.py`）。對產出物設上限只會得到一道每次 commit 都要調的關。
#:
#: **`tests/` 也不在裡面**：測試檔變長通常是好事（多守一件事），而這一份要抓
#: 的是「沒有人決定卻變大」，那件事發生在出貨的程式碼上。
SCOPE = ("d4t", "tools", "fab_probe")

#: **凍住的那幾支**：上限就是 2026-09-08 的實際行數，一行都不留。
#:
#: 為什麼是這五支而不是「全部」：這五支是 2026-09-08 那份體檢點名的
#: —— 前四支是接線層與遷移層（成長跟功能不成比例），`canvas.py` 則單純是
#: 超過下面那個一般上限而且不該再漂。其他 138 支走 :data:`GENERAL_CEILING`。
FILE_CEILINGS = {
    # **2026-09-08（U7）：7,140 → 123。那件事做完了。**
    #
    # 這一格的註解以前寫的是「真正的解法是把那幾群圖示切出去，而那件事的前置
    # 是黃金值三份全綠 —— 已經成立了」。U7 就是那一刀：24 個不相干的類別拆成
    # 八支（`buttons` / `icons` / `image_view` / `fields` / `param_form` /
    # `chips` / `library` / `histogram` / `feature_text`），而 `widgets.py`
    # 只剩一層轉出口 —— 四十幾個模組與上百條測試一個字都沒有改。
    #
    # ⚠ **這一格現在守的是「它不要再長回來」**，而那正是這把尺設計時就寫著的
    # 那件事（反向測試那一段：「`studio.py` 真的拆掉 2,000 行之後，上限如果還
    # 留在 6,942，它就可以在沒有人注意的情況下再長回來」）。123 行是那道門
    # 本身；`test_ui_widgets.py::test_the_front_door_stayed_a_front_door`
    # 從另一邊問同一句話（那支檔案裡不准再有 class / def）。
    #
    # 123 → 137（同日，U7 的收尾）：轉出口漏了十個**它 import 進來**的名字
    # （`TOKENS` 那一批），而 `test_ui_f8_ruler` 是用 `widgets_mod.TOKENS`
    # 讀走的 —— 補回去要十四行 import。
    "d4t/ui/widgets.py": 137,
    # 接線層（建 widget、接訊號、轉呼叫）。`CLAUDE.md` §4：新的面板一律開新
    # 模組，不要塞進這裡。這一格就是那句話的執行機構。
    #
    # 2026-09-08（P0 那一批 ＋ X4/U11）：6,942 → 7,198（+256）。
    # **七個新模組，而這裡只加接線** —— 每一項的內容都在自己的檔案裡：
    #   `baseline.py`（X1）、`truth_marks.py`（X2）、`fit_screen.py`（U1）、
    #   `crashlog.py`（U3）、`autosave.py`（U4）、`problems_bar.py` ＋
    #   `status_log.py`（U2 的前後兩半）。
    # P0 那一批的 166 行：三支新方法（`_publish_run_snapshot` /
    # `_on_truth_marked` / `_on_problem_activated`）、Problems 列／狀態列歷史／
    # 草稿的建構與掛勾、以及 `_refresh_pipeline` 改成只跑一次 lint。
    # X4 的 0 行（只換了旗標的名字）＋ U11 的 90 行：把 Results 那個
    # `WhyPanel` **同一個 widget** 掛進單顆預覽這一欄，加上讓路徑那一行變成
    # 連結（三支：`_decide_path_markup` / `_fill_preview_why` /
    # `toggle_preview_why`）。
    #
    # 2026-09-08（U6）：7,198 → 7,037（−161）。接線／換線／剪線的**決定**搬進
    # `ui/edit_plan.py`（純函式、不碰 Qt），這裡只剩「照計畫動 model」——
    # 那一段留著是因為它的**順序**有意義（`add_edge` 會因為成環而失敗，而失敗
    # 的那條線不該留下任何痕跡）。降下來的這一格就是把那件事鎖住。
    #
    # 2026-09-08（U13/X7 ＋ X5/X6 ＋ U21 ＋ U17）：7,037 → 7,170（+133）。
    # **四件事，而內容全在別的地方**：那顆「下一步」鈕住在 `ui/status_action.py`
    # （X5 開資料夾 ＋ X6 就地反悔共用同一個機制）、「這份 recipe 升級了什麼」
    # 算在 `recipe.describe_migration` 上。這裡加的是接線與四支小方法
    # （`_status_next_step` / `_open_output_folder` / `_refresh_results_button`
    # / `_describe_upgrade` ＋ `_show_upgrade_detail`）。
    #
    # 2026-09-08（U18 ＋ X3）：7,170 → 7,279（+109）。抽樣的**挑法**住在
    # `core/pipeline/sampling.py`（純資料、不 import Qt），這裡加的是工具列
    # 那顆下拉、換模式時把字換掉、以及把設定送進 `run_batch`。U18 的兩支則
    # 是把快捷鍵表上那兩格接到畫布已經有的實作上。
    #
    # 2026-09-08（U5 ＋ U8）：7,279 → 7,390（+111）。**這一格本來會下降** ——
    # U5 刪掉了整個彈出視窗（`open_canvas_window` / `_on_canvas_popout_closed`
    # / `canvas_popout_open`，約 55 行）—— 而換上來的兩種模式要記兩份比例、
    # 要把「模式」跟「設定區攤開沒有」講清楚（第一版把它們合成一個狀態，
    # 而那是錯的：模式是使用者選的，攤開是選到卡片時的自動行為）。
    # U8 的 `_build_params_row` 是新的一支，加上儀表從右欄搬過來的接線。
    #
    # 2026-09-08（U14）：7,390 → 7,404（+14）。翻譯層只包了兩個**繞過
    # `_tool_button` 的地方**（`_refresh_results_button` 與 `_sync_layout_button`
    # 自己改寫 text/tooltip）—— 整條工具列與狀態列各只加一行，因為那兩支本來
    # 就是共用的入口。那正是 U14 的整個賣點：翻譯不必改 38 個檔案。
    #
    # 2026-09-08（X3 收尾）：7,404 → 7,427（+23）。`_sample_line` ——
    # 抽樣的種子以前只存在 `sample_note` 這個欄位上，**使用者看不到**，而
    # Studio 不寫 runs.db（只有 CLI 寫）。一次跑出漂亮結果而重現不了的隨機
    # 抽樣等於沒有跑過，所以跑完那句話後面要帶著種子。
    #
    # 2026-09-08（刪死碼）：7,427 → 7,429（**+2，而它刪掉了三行程式**）。
    # `_bound_param` 寫了三次、一次都沒有被讀過 —— F9-5b 的真相搬到邊上
    # （`add_edge(dst_in=…)`）之後它就只是一個會讓人以為「有人在用它」的欄位。
    # 換上來的是五行說明：**為什麼那件事不在這一支做、以及它以前在哪裡**。
    # 解釋比程式碼貴，而那是對的價錢 —— 沒有它，下一個人會把它加回來。
    #
    # 2026-09-08（工具列裝不下的那個 regression）：7,429 → 7,444（+15）。
    # U5／X3 各在工具列上加了一顆鈕，加起來 132 px，而那台 1366×768 的機器只
    # 剩 76 px 的餘裕（`test_ui_small_screen` 抓到）。兩顆都搬走了：版面切換
    # 進畫布的縮放列（它控制的就是那塊畫布）、抽樣併進那個會變的字本身。
    # 加的行是**為什麼**（下一個人加鈕之前會讀到）。
    # 2026-09-08（F99／F100）：7,444 → 7,560。**淨值 +116，而它換掉了一整段
    # 版面**：`set_layout_mode` / `set_params_open` / `_sync_params_pane` 的
    # 幾何搬進 `ui/workbench.py`（−56），進來的全是接線：右鍵／拖線到空白處的
    # 兩支（內容在 `ui/card_menu.py`）、Ctrl+C/V/D 三支轉呼叫（內容在
    # `ui/clipboard.py`）、Windows 下拉一支（`ui/windows_menu.py`）、Verdict
    # 常駐列與「為什麼是破折號」那一句、儀表板淡掉那兩行、執行狀態一行。
    # 2026-09-08（F100 v3）：7,582 → 7,592（+10）。右欄變成一支直向 splitter
    # （影像在上、儀表在下）而它的建立與 stretch 住在這裡；工作台那一列只剩
    # `stack`。幾何本身（開合、比例、記住尺寸）仍在 `ui/workbench.py`。
    # 2026-09-09：7,592 → 7,611（+19）。整批一次的卡（Output 段）的「插入
    # 數字 ▾」多列 working numbers（`_dynamic_choices_for` 那一段），與設定區
    # 那支下拉的 tooltip／顏色 provider（`_number_info`）—— 都是接線。
    # 2026-09-09（同日第二次）：7,611 → 7,750（+139）。跑與寫拆成兩個動作
    # （`run_all` 不寫、`write_outputs` 另一顆鈕）、`rerun`（量測沒改就只重判，
    # 邏輯在 `batch.rerun_decision` / `measurement_signature`）、Results 單擊
    # 帶主畫面過去（`_on_defect_selected`）、Output 卡與判定樹的預覽跑到底
    # （`_preview_whole_route`）。四件都是使用者 2026-09-09 點名的，內容各在
    # core 或 Results 那幾支，這裡是接線與三句要講的話。
    # 2026-09-09（logger）：7,747 → 7,753。`d4t/core/log.py` 落地：每一個
    # `except Exception:` 後面直接 pass/continue/return 的地方多一行
    # `swallowed("studio.<函式>")`，加一行 import。**這一格從此不再往上**
    # （見下面 `HARD_CAPS`）。
    # 2026-09-18（F110）：7,753 → **7,717**（−36）。第五顆 Open 鈕（DOE）要加，
    # 而這一格只准往下 —— 所以先搬走等量的東西：五顆 Open 的對話框與那個
    # 「按下去要做什麼」的分岔整族搬進 `ui/open_dialogs.py`，`studio.py` 只留
    # `partial(open_dialogs.open_source, self, src.key)`。
    # **順便讓一句話變成真的**：`CLAUDE.md` §5 寫著「加／改一個入口＝改
    # `INPUT_SOURCES`，不要動 UI」，而在這之前加一列就得同時在這裡長一支
    # `_on_open_<key>` 出來，不然那顆鈕按下去是 AttributeError。
    # 2026-09-18（F114）：7,717 → **7,686**（−31）。stack 拿掉，`load_stack_path`
    # 跟著走 —— 見下面 `HARD_CAPS` 那一段。
    # 2026-09-18（F116 第 1 步）：7,686 → **7,388**（−298）。右下角那一族
    # （卡片儀表：換儀表、一鍵校正、圖的視窗、曲線背景）整族搬進
    # `ui/gauge_panel.py`，`studio.py` 只留三行門面與 `self.gauges = GaugePanel(self)`。
    # 這是 F116「`StudioWindow` 只留組裝與接線」的第一步，見
    # `docs/plans/F116-split-studio.md`。
    # 2026-09-19（F116 第 1 步之 1b）：7,388 → **7,149**（−239）。`bottom_stack`
    # 的另一頁（特徵表）跟著儀表進 `ui/gauge_panel.py`；區域跨顆檢視那四支進
    # **既有的** `ui/region_check.py`（它用的每一個東西本來就在那裡，而那顆按鈕
    # 住在預覽區，不在右下角）。
    # 2026-09-19（F116 第 1 步之 1c）：7,149 → **6,782**（−367）。影像流選擇與
    # 畫在圖上的東西（區域框、量測標記、熱色磚、並排比對、兩張圖互跟）整族進
    # `ui/preview_overlays.py`。第 1 步做完：7,686 → 6,782，−904。
    # 2026-09-19（F116 第 2 步）：6,782 → **5,792**（−990）。介面組裝那一族整族
    # 進 `ui/studio_layout.py`（見下面 `HARD_CAPS` 那一段）。
    # 2026-09-19（F116 第 3 步）：5,792 → **5,434**（−358）。Gallery／Results／
    # 回溯那一族進 `ui/gallery_controller.py`，縮圖那一條鏈
    # （`THUMB_CHANNEL_PRIORITY` → `thumb_channel` → `load_thumb` →
    # `ThumbWorker`）跟著走 —— 它們的唯一使用者就是 Gallery。
    # 2026-09-19（F116 第 4 步）：5,434 → **5,135**（−299）。「把第二份東西掛到
    # 已經載入的這一份上」那一族（配對卡的第二份 lot ＋ GLAS 匯出）進
    # `ui/attach_sources.py`；recipe 的開／存三支進**既有的** `ui/open_dialogs.py`
    # （同一個「只問路徑、做事交給 window」的契約）。
    # 2026-09-19（F116 第 5 步）：5,135 → **4,785**（−350）。「怎麼發動一次執行、
    # 怎麼把結果寫出去」那一族（含鐵則 11 的三道關）進 `ui/run_controller.py`。
    # ⚠ `_apply_trial_results` **留在這裡**：它叫的那一串 `_refresh_*` 跟訊息、
    # 跟「要不要寫」是交織的，而且順序有守門的註解 —— 見那一支上面那一段。
    # 2026-09-19（F116 第 6 步）：4,785 → **4,347**（−438）。畫布上拉一條線／
    # 剪一條線在 model 上是什麼意思（鐵則 10 的主場）進 `ui/canvas_edges.py`。
    # 計畫書把這一塊猜成「本質上就是接線」，量出來不是：437 行裡六支規則型的
    # 方法就佔 284 行，真正的 handler 只有 67 行。
    # 2026-09-29（F121 期 1～4）：4,347 → **4,302**（−45）。入口簡單化：Input 卡
    # 上那張「你要開哪一種」的選單拿掉（見下面 `HARD_CAPS` 那一段）。
    # 2026-09-29（F122 期 2）：4,302 → **4,293**（−9）。「這一批的底稿」搬進
    # `RunController.snapshot`（它多記了判定的簽章）。
    # 2026-09-29（F122 期 3）：4,293 → **4,236**（−57）。舊門檻那條路退役：
    # 分數直方圖上的門檻線、它的兩個 handler、重算 bin 數與準確率那兩支。
    # 2026-09-29（F123 期 1）：4,236 → **4,186**（−50）。Decision 變成一張卡：
    # 卡片庫的 `__score__` 偽卡、`_decision_problem`（判定的 lint 走卡片那條路）
    # 拿掉，`remove_decision` 的確認搬進 `canvas_edges`。
    "d4t/ui/studio.py": 4186,
    # 19 道 `_migrate_*` 住在這裡（見下面 `recipe_migrations`）。它會用跟
    # `studio.py` 完全一樣的機制長成第二個 `studio.py`。
    #
    # 2026-09-08（U17）：3,732 → 3,830（+98）。`describe_migration` ——
    # 「這份舊 recipe 開起來被升級了什麼」講成人話。它**比對前後**而不是讓
    # 19 道 `_migrate_*` 各自回報：那會是 19 個要維護的字串，而第 20 道一定
    # 會忘（`ALLOWED_ERRORS` 學到的同一課）。
    #
    # 2026-09-09：3,830 → 3,865（+35）。`let_names_written` —— 判定段 `let`
    # 會寫的名字（＋ `_missing` / `_raw`）**一個家**：`_decide_unknown` 以前把
    # 這條規則寫在自己的迴圈裡，而 `validate` 對 Output 卡的 `rank_by` 根本
    # 不知道 let 存在（指到 working number 被標成 nobody produces it）。
    # 2026-09-09（logger）：3,865 → 3,870。同上：五處 `except Exception:` 留痕。
    # 2026-09-17（F109）：3,870 → 3,949（+79）。第 20 道遷移
    # （`_migrate_align_into_streams`，RECIPE_VERSION 3 → 4）。**它比前 19 道
    # 都長，而那不是隨便寫的**：align 的舊 `out` 參數是一個**下游看得見的名字**
    # （`ref_aligned`），所以換掉它的不是那一張卡自己的三個鍵，還有每一張指著
    # 那個名字的 `image_key` 參數與 `recipe.edges` 上的 `src_out`。少改任何一邊，
    # 舊 recipe 開起來就是一條斷掉的線 —— 而畫布會照實畫出來（F9），使用者看到
    # 的是「我的 recipe 壞了」。
    # 那 79 行裡有一半是說明：下一個要改「卡片寫出去的名字」的人得先讀到這件事。
    # 2026-09-18（F110）：3,949 → 4,017（+68）。`wrong-content` —— 把 layout
    # label map 接進 Normalize 今天是一條**完全合法**的線，而 lint／畫布／引擎
    # 三層都沒擋。label map 的像素值就是層號，正規化會把 1、2、3 混成 1.7，
    # 而且**不會報錯**：跑得完、有數字、下游每一個區域都是錯的。
    # 多的是兩支（`_content_written` 傳播、`_wrong_content` 檢查）與它們的理由。
    # 2026-09-18（F110，同一輪第二次）：4,017 → 4,101（+84）。第 21、22 道遷移
    # —— `subtract` 拆卡（換 step、併兩顆埠、改線上的埠名）與 `absolute` → `sign`。
    # 那 84 行裡有一半是**兩道遷移判準不同的理由**：一道看舊的值（鐵則 9 正牌），
    # 一道看舊鍵在不在，而 F109 的 align 那一道只能靠版本號 —— 三種判準的差別
    # 在「預設值的意思有沒有變」，下一個寫遷移的人得先讀到這件事。
    # 2026-09-19（F118 第 2 步）：4,101 → 4,124（+23）。`Issue` 上四個**選配**
    # 欄位（`param` / `names` / `suggest` / `route`），讓 lint 把結構交出來而
    # 不是先組成散文。+23 裡只有 4 行是欄位，其餘是**為什麼預設要是空的**：
    # 48 個產地要一條一條搬，而中途畫面不准是半好半壞的（`ui/wording.py`
    # 的 `issue_line()` 沒拿到結構就原樣回 `detail`）。
    # 2026-09-19（F118 第 3 步）：4,124 → **4,214**（+90）。最常出現的六條 lint
    # 搬去交結構（`unknown-feature` ×2、`not-connected`、`unknown-step`、
    # `ambiguous-input`、`duplicate-region`、`wrong-content`），＋ 兩支 core
    # 自己就答得出來的翻譯（`card_name`：node id → 卡片名；`closest`：拼錯 →
    # 最接近的幾個）。+90 裡大半是**為什麼這兩件在 core 而那兩件在畫面**：
    # `Step.label` 本來就住在 core，所以「那張卡叫什麼」在產地做又對又便宜；
    # 畫面留著的是它才答得出來的「幾條 route」與「列到第幾個就夠」。
    # 2026-09-19（F118 第 5 步）：4,214 → **4,342**（+128）。剩下的 lint 掃完：
    # 34/48 個產地現在交結構，而另外 14 個**量出來是本來就乾淨的**（判定段的
    # 語法錯、卡片自己的「還沒設定完」、分數表達式 parse 不過）—— 對它們填欄位
    # 買不到任何東西。+91 裡有一半是那些句子本身（node id → 卡片名、list repr →
    # 讀得下去的一串字、`decide.let[3]` → 「let line 4」），另一半是理由。
    # 這一輪真正買到的是 `tests/test_ui_wording.py` 那條**不准回頭**的關。
    # 2026-09-20（F119 第 1 步）：4,342 → **4,427**（+85）。`OUTCOMES` ＋ 三個
    # `outcome` 欄位 ＋ `bin_outcomes()` ＋ serde（有才寫）。判定膠囊的紅綠以前
    # 是看 bin 的**號碼**決定的，而三份出貨的 recipe 全反了（F117 D2）。+85 裡
    # 有一半是 `OUTCOMES` 上面那一段**為什麼不准猜**：`rsem-worst-box` 的
    # bin 2 比 bin 1 更嚴重，任何按號碼排的規則都答不出來。
    # 2026-09-20（F119 第 5 步）：4,427 → **4,471**（+44）。標錯／標不一致的
    # 兩條 lint（`unknown-outcome`／`conflicting-outcome`，照 F118 交結構）。
    # ⚠ **「還沒說」刻意不是一條 lint**：一份每個舊 recipe 都會亮的訊息會被
    # 學會忽略，而真的那一條也跟著被忽略 —— 理由寫在 `_outcome_issues` 上面。
    # 淨增只有 +44 是因為 `bin_labels` / `bin_outcomes` 的兩支走訪收成一支
    # `entries()`（四個地方對「哪一片排在前面」本來會有四個答案）。
    # 2026-09-20（F117 F5）：4,471 → 4,522（+51）。`_doubled_names` ＋ 那一條
    # lint（`doubled-prefix`）：出貨的均勻度 recipe 寫出來的欄名是
    # `cells_cells_area_px` —— 一次是 `output_prefix`，一次是卡片自己給那個
    # 區域的名字。
    # ⚠ **這 51 行買的是「不改組名字的規則」。** 另一條路是讓 `full_prefix`
    # 遇到同名不疊 —— 那要遷移全 repo 的特徵名與分數表達式、重錄黃金值，而換
    # 來的是一個**看不見的**行為。一條講得出後果的 warning 便宜得多，而且它
    # 擋得住每一張卡，不只被走查點到的那一張。
    # 2026-09-24：4,522 → 648。拆成四支（schema／migrations／validate 與留下來的
    # `Recipe`＋執行順序），另外三支都在一般上限底下。
    # 2026-09-24（F121 期 1＋2）：648 → 650（+2）。`route_for` 的轉出口一行、
    # `load_single` → Input 那一道的呼叫一行。**遷移的呼叫順序只住在
    # `from_json_dict`**（`recipe_migrations` 的檔頭這樣規定），所以這一行只能加
    # 在這裡；F11 那一道的版本閘收進那一支自己的參數，沒有在這裡多長一段 if。
    # 2026-09-29（F123 期 1）：650 → 653（+3）。第 6 版的版本閘（判定變成一張卡
    # 的那一道）與它的轉入口一行。版本閘拆成兩段（`< 5` / `< 6`）是必要的：
    # 第 5 版以前那三道**不能**對第 5 版的檔案再跑一次（F68 那一道會把逐框比較
    # 的參照釘回舊行為）。
    "d4t/core/pipeline/recipe.py": 653,
    # 逐卡儀表板。這一支變長**通常是健康的**（加一張卡就多一個面板），所以
    # 這一格比其他四格更常需要調高 —— 那沒關係，重點是調高時有人看見。
    # 2026-09-08（F99 P0-2）：3,622 → 3,660。`header_boxes` —— 共用 header 左右
    # 兩段以前畫進同一個矩形而沒有一方讓寬度，面板窄到 200 px 時疊在一起。
    # 2026-09-17（F109）：3,660 → 3,669（+9）。`AlignInspector` 的散佈圖以前寫死
    # `align_dx`／`align_dy` 兩個名字，而 align 現在對 N 條流、三條以上時特徵名
    # **帶著流名前綴** —— 寫死的那一版在 DOE（一次 N 個 condition，正是這張圖最
    # 有用的時候）會畫出一張**空圖**，而空圖上寫的是「跑一次試跑就看得到」。
    # 多的幾行是「跟卡片要名字，不自己拼字串」與那句為什麼。
    # 2026-09-24：3,669 → 1,733。基底、GLV、CD、Enhance 四塊各搬進自己的
    # `ui/inspector_*.py`（每支都在一般上限底下）；這裡剩註冊表與小面板。
    # 2026-09-29（F122 期 2）：1,733 → 1,745（+12）。Write KLARF 的儀表要分得出
    # 「拿不到 KlarfDoc」與「這份資料**沒有** KLARF」（後者寫的時候跳過，儀表不准
    # 給一個「N 顆會改」的估計），而「Write to」空著時要寫出**真的會寫到**的那個
    # 檔（預設在原檔旁邊）。兩件都是這一個面板的內容，不是接線。
    "d4t/ui/inspectors.py": 1745,
    # 節點畫布。沒有被點名，只是它超過一般上限，凍住免得它安靜地漂。
    #
    # 2026-09-08（U18/U19/U20）：2,705 → 2,887（+182）。三件都長在畫布上，
    # 而它們**本來就該長在這裡**：Tab／Esc／Delete 要知道選著什麼、第一次
    # 接線的提示要畫在那顆埠旁邊、區域線的顏色是線自己的事。
    #
    # 2026-09-08：2,887 → 2,900（+13）。`zoom_buttons()` ＋ 那顆「看全貌」鈕
    # 現在切換版面而不是開視窗的說明。
    # 2026-09-08（F99）：2,900 → 3,050。四件都長在畫布上：動畫殼的生命週期
    # （`_stop_anim` / `_forget_anim`，P0-1 那個 RuntimeError）、空白處右鍵與
    # 拖線到空白的兩個訊號（P1-1）、Region 卡標題帶區域名（P1-3）、每張卡的
    # 執行狀態（`run_status_from` / `run_text`，P1-5）。
    # 2026-09-09：3,058 → 3,070（+12）。`run_text` 從總耗時改成每秒幾顆
    # （使用者：「X img/s 而不是 total time」）—— 多的是那句「為什麼加總的 ms
    # 不是牆上時鐘」的說明。
    # 2026-09-19（F117 A3／J2）：3,070 → 3,100（+30）。`ensure_card_visible()`
    # （**只捲、不亮** —— 跟 `reveal_cards` 那一套 hover 高亮的差別，以及
    # ⚠「不要接進 `set_selected`」那條界線，都寫在它的說明裡）與 `select_card()`
    # （選一張卡在畫布上是**一件事**：畫成選中、清掉樹的選取、捲進視野）。
    # 後者讓 `studio.py` 那邊從三行變一行 —— 那一格是 HARD_CAPS，只准往下，
    # 而這正是「要往 studio.py 加東西，先從它手上搬走等量的東西」的樣子。
    # 2026-09-20（F117 I7）：3,100 → 3,160（+60）。走查記的是「每張卡都印
    # `20 ok · 2051 img/s`」—— 那一行重複七次之後就不是資訊了。多的是
    # `loud_nodes()`（誰值得佔那一格：失敗的永遠講、瓶頸只在它真的吃掉三分之
    # 一以上的時候講）與 `sync_run_tip()`（**每一張卡的數字照樣量得到**，
    # 它搬進 tooltip —— 丟掉一個量得到的數字跟把它印七遍一樣糟）。
    # ⚠ 那個三分之一的門檻**自己就要一段說明**：平均分配的那一批沒有瓶頸，
    # 而硬挑一個最慢的標出來，會讓使用者去調一張其實不重要的卡。
    # 2026-09-20（F117 A6）：3,160 → 3,163（+3）。卡片的外框改用畫布自己的
    # `canvas_card_border` —— `border_default` 是配面板底色調的，畫在畫布上
    # 淺色只有 **1.03** 的對比（那條框等於不存在）。多的三行是那句說明。
    # 2026-09-29（F123 期 1）：3,163 → 3,154（−9）。判定區的外框拿掉了（樹掛在
    # Decision 卡底下、拖卡就拖樹），整區拖曳那一族（位移、重設）跟著走。
    "d4t/ui/canvas.py": 3154,
    # `CLAUDE.md` **每個 session 都會被讀進去**。2026-09-09 之前它是 647 行，
    # 一半是「某年某月使用者說了什麼」的故事 —— 規則留下、故事搬進
    # `docs/history/CLAUDE-2026-09-09.md`，瘦到 319 行。這一格擋它長回去：
    # 要加一條規矩可以，要加一段故事去 SESSION_LOG／history。
    # 2026-09-19（F116）：323 → 332（+9），而且是**先砍掉故事才簽的**：第一版
    # 寫了 +16（F116 的行數、七個模組的名字、六種漏法逐條列出）—— 那是故事，
    # 被這一格擋下來之後改成三條**規則 ＋ 指標**：① 要再從 `studio.py` 搬東西
    # 先讀那一份計畫的 §3／§6 ② 判準是 `tools/studio_surface.py`（它同時守
    # 「測試找不找得到」與「別的 UI 模組還有沒有人在叫」）③ 家用機上黃金值
    # 第三份是紅的而那不是行為變了。三條各自擋掉一次真的發生過的浪費。
    # 333 → 332（2026-09-23）：pitch helper 搬去自己的 repo 了，§0 那一列
    # 指向的交接檔跟著刪，所以這裡跟著降。**上限掉下去要跟著降**是這張表的
    # 另一半（`test_the_ceilings_are_not_far_above_the_truth` 會叫）——
    # 一個沒人踩得到的上限等於沒有上限。
    "CLAUDE.md": 332,
}

#: 沒被列名的檔案共用的上限。
#:
#: 2,200 是量出來的：扣掉上面那五支之後最長的是 `steps/glv_stats.py` 2,101 行，
#: 次高 `steps/output.py` 2,016、`ingest/klarf_core.py` 1,982。所以這個數字給
#: 現役的大檔約 100–200 行的呼吸空間，而**一支新檔案一寫就超過 2,200 行**這件
#: 事本來就該先講一句話。
GENERAL_CEILING = 2200


def _lines(rel: str) -> int:
    return len((REPO / rel).read_text(encoding="utf-8").splitlines())


def _all_sources():
    for base in SCOPE:
        for path in sorted((REPO / base).rglob("*.py")):
            yield path.relative_to(REPO).as_posix()


# --------------------------------------------------------------------------- #
# 「按卡片名字分支」的地方有幾個
# --------------------------------------------------------------------------- #
#: **這兩張表是設計好的擴充點，不算耦合。**
#:
#: `inspectors.INSPECTORS`（一張卡一個面板）與 `inspectors.BY_METHOD`
#: （同一張卡的不同 method 不同面板）就是「加一張卡要在 UI 註冊一個面板」那條
#: 明講的路 —— `inspector_for()` 讀的正是這兩張，沒註冊的卡落回通用的特徵表。
#: 把它們算進去的話，這個指標量到的會是「卡片有幾張」，不是「耦合有多深」。
SANCTIONED_TABLES = {"INSPECTORS", "BY_METHOD"}


def _is_shouty(name: str) -> bool:
    """`STARTER_STEP` / `_PAIR_CARDS` 這種模組級常數名。"""
    return name.lstrip("_").isupper()


def card_key_couplings():
    """``d4t/ui`` 底下**按卡片名字分支**的每一個地方。

    只認三種語法位置，所以不會把同名的字串誤算進來（實測驗過：
    ``widgets.py`` 的 ``setProperty("tone", …)`` 是 Qt 屬性、
    ``inspectors.py`` 的 ``{"subtract": "−"}`` 是運算子符號，兩者都不算）：

    1. **比較**：``node.step == "glv_stats"``、``not in ("load_patch", …)``；
    2. **模組級常數**：``STARTER_STEP = "load_patch"``、``HIDDEN_STEPS = ("align",)``
       （:data:`SANCTIONED_TABLES` 那兩張除外）；
    3. ``get_step("glv_stats")``。

    回 ``(檔名, 行號, 形式, 卡片 key)`` 的集合。
    """
    keys = set(REGISTRY)
    found = set()
    for path in sorted((REPO / "d4t" / "ui").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                sides = [node.left] + list(node.comparators)
                for side in sides:
                    lits = [side] if isinstance(side, ast.Constant) else \
                        list(getattr(side, "elts", []))
                    for lit in lits:
                        if isinstance(lit, ast.Constant) and lit.value in keys:
                            found.add((rel, lit.lineno, "compare", lit.value))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) \
                    else [node.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                if not names or not any(_is_shouty(n) for n in names):
                    continue
                if any(n.lstrip("_") in SANCTIONED_TABLES for n in names):
                    continue
                for sub in (ast.walk(node.value) if node.value else []):
                    if isinstance(sub, ast.Constant) and sub.value in keys:
                        found.add((rel, sub.lineno, "const:" + names[0],
                                   sub.value))
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) \
                    else getattr(fn, "id", "")
                if name == "get_step":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and arg.value in keys:
                            found.add((rel, arg.lineno, "get_step", arg.value))
    return found


def _class_shape(rel: str, cls_name: str):
    """一個類別的 ``(方法數, self.* 名字數)``。

    行數量的是「打了多少字」，這兩個數字量的是**耦合** —— 刪掉一段註解會讓
    行數變好看，不會讓這兩個變好看。
    """
    src = (REPO / rel).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            methods = [n for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            seg = ast.get_source_segment(src, node) or ""
            attrs = set(re.findall(r"self\.([A-Za-z_][A-Za-z0-9_]*)", seg))
            return len(methods), len(attrs)
    raise AssertionError("%s 裡找不到 class %s" % (rel, cls_name))


def _migration_count() -> int:
    # 2026-09-24 起遷移住在 `recipe_migrations.py`（`recipe.py` 拆成四支）。
    src = (REPO / "d4t/core/pipeline/recipe_migrations.py").read_text(encoding="utf-8")
    return len([n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.FunctionDef)
                and n.name.startswith("_migrate")])


#: 不是行數的那幾把尺 —— ``名字: (上限, 為什麼是這個數字, 量它的函式)``。
COUNT_CEILINGS = {
    # 這一格守的是**整個專案的賣點**：「加一張卡，UI 與引擎零修改」。
    # 唯一會安靜殺掉那句話的，就是這個數字慢慢變大。
    # 2026-09-08 的 23 個：viewmodel 8、studio 10、inspectors 3、scope 1、
    # canvas 1。要加第 24 個之前先問：這件事能不能改成問卡片自己
    # （`Step` 上多一個宣告），而不是在 UI 裡問「你是不是那張卡」。
    # 2026-09-24（F121 期 2）：23 → 20。`load_single` 併回 Input，問「你是
    # `load_patch` 還是 `load_single`」的那三處只剩一個答案。
    "ui_card_key_coupling": (
        20,
        "d4t/ui 裡按卡片名字分支的地方（不含 INSPECTORS/BY_METHOD 兩張註冊表）",
        lambda: len(card_key_couplings()),
    ),
    # god object 的兩個投影。261 → 268（六天）。
    "studio_window_methods": (
        191,
        # 2026-09-29（F123 期 1）：192 → 191。`_decision_problem` 拿掉 —— 判定的
        # lint 現在掛在 Decision 卡上，走跟每一張卡同一條路（`_node_problems`）。
        # 2026-09-29（F122 期 3）：197 → 192。舊門檻那條路退役：分數直方圖上的
        # 門檻線那一族五支（兩個 handler、`_uses_a_threshold`、
        # `_refresh_bin_summary`、`_accuracy_text`）。
        # 2026-09-19（F116 第 6 步）：210 → 197。搬走 16 支，回來三支門面
        # （`_on_edge_added` **191 處／21 個測試檔**、`_connect` 17／3、
        # `_on_edge_removed` 16／5）——門面留**舊名字**，所以那 191 處一個字
        # 都不用改。
        # 2026-09-19（F116 第 5 步）：221 → 210。搬走 15 支，回來四支門面
        # （`run_trial` 44 處／13 檔、`run_all` 12／4、`write_outputs` 10／2、
        # `rerun` 4／1 ＋ Results 那顆鈕）—— 它們是這個視窗的**公開動詞**。
        # 2026-09-19（F116 第 4 步）：235 → 221。搬走 14 支（attach 那一族 11 支
        # ＋ recipe 的開存 3 支），**一支門面都沒留** —— 接線改成
        # `partial(open_dialogs.save_recipe, win)`，同那三顆 Open 鈕的形狀。
        # 2026-09-19（F116 第 3 步）：248 → 235。搬走 15 支，回來兩支門面
        # （`show_gallery` —— 工具列那顆鈕與 Ctrl+Shift+R 都接它；
        # `results_visible` —— 14 處／2 個測試檔）。
        # 2026-09-19（F116 第 2 步）：256 → 248。七支 `_build_*` ＋ `_tool_button`
        # 變成 `ui/studio_layout.py` 的模組層函式（沒有留門面 —— 沒有人從外面
        # 叫它們，`__init__` 改成 `studio_layout.build_toolbar(self)`）。
        # 2026-09-19（F116 第 1 步之 1c）：272 → 256。搬走 21 支，回來五支門面
        # （`set_compare` / `compare_enabled` / `region_overlay_names` /
        # `heat_tiles` / `_focus_box_index`）。`compare_enabled` 不只是給測試的：
        # `GaugePanel` 要知道畫面上是一條流還是兩條，而 controller 之間不直接
        # 互叫（F116 §3-2），它走的就是那一行。
        # 2026-09-19（F116 第 1 步之 1b）：280 → 272。搬走 11 支，回來三支門面
        # （`open_region_check` / `profile_panel` / `profile_panel_visible` ——
        # 兩個測試檔都在用）。
        # 2026-09-18（F116 第 1 步）：293 → 280。右下角那一族 16 支搬進
        # `ui/gauge_panel.py`，回來三支門面（`inspector` / `bottom_page` /
        # `_on_calibrated` —— 測試用得多的那幾個，見 F116 §3-3）。
        # 2026-09-18（F114）：294 → 293。使用者把 stack 拿掉（「我們用不到」），
        # `load_stack_path` 跟著走。**刪掉也要把尺調下來**（反向測試在守）。
        # 2026-09-09：294 → 298。`write_outputs`（跑與寫拆開）、`rerun`
        # （邏輯在 `batch.rerun_decision`）、`_on_defect_selected`（Results
        # 單擊帶過去）、`_preview_whole_route`（Output 卡／判定樹跑到底）。
        # 2026-09-08（F99）：287 → 294。六支全是轉呼叫：`_on_add_menu` /
        # `_on_link_dropped`（`card_menu`）、`copy_cards` / `paste_cards` /
        # `duplicate_cards`（`clipboard`）、`_open_windows`（`windows_menu`）。
        # 2026-09-08（X3 收尾）：286 → 287。`_sample_line`（見上）。
        # 2026-09-08（U5 ＋ U8）：284 → 286。**淨值 +2，而它換掉了三支**：
        # 走的是 `open_canvas_window` / `_on_canvas_popout_closed` /
        # `canvas_popout_open`，來的是 `layout_mode` / `set_layout_mode` /
        # `toggle_layout_mode` / `_sync_layout_button` / `_build_params_row`（F116 第 2 步起在 `ui/studio_layout.py`）。
        # 2026-09-08（U18 ＋ X3）：280 → 284。四支：`_delete_selected_on_canvas`
        # 與 `_clear_canvas_selection`（快捷鍵表上那兩格 → 畫布已經有的實作，
        # 刪除仍然只有一份）、`set_sample_mode`（換模式**並且**把工具列的字
        # 換掉 —— 跑的東西變了而畫面沒變是最危險的失敗方式）、`sample_spec`。
        # 2026-09-08（那四件事）：275 → 280。五支，每一支都是接線：
        # `_status_next_step`（一句話 ＋ 它旁邊那顆鈕）、`_open_output_folder`
        # （X5，開不起來要說出來）、`_refresh_results_button`（U21）、
        # `_describe_upgrade` / `_show_upgrade_detail`（U17 的兩半：算出來、
        # 講出來）。四件事的**內容**分別在 `status_action.py` 與 `recipe.py`。
        # 2026-09-08（U6）：274 → 275。**搬走了一堆行，方法卻多一支** —— 那不是
        # 帳算錯了：`_drop_conflicting_edges` 裡「算出誰要被剪」與「真的剪掉並
        # 講一句話」本來黏在一起，前者進了 `edit_plan.conflicting_edges`，後者
        # 留下來變成 `_drop_edges`（`_connect` 與 `_connect_region` 都要用它）。
        # 這一格量的是**這個類別有幾件事要做**，而它確實多了一件；`studio.py`
        # 那一格量的行數少了 161，兩個數字講的是同一次搬家的兩面。
        #
        # 2026-09-08（X4/U11）：271 → 274。U11 的三支：`_decide_path_markup`
        # （把路徑跳脫成連結）、`_fill_preview_why`（餵目前這一顆）、
        # `toggle_preview_why`（那一行點下去）。
        #
        # 之前那一批 268 → 271。三支，每一支都是**接線**：
        # `_publish_run_snapshot`（X1 把一批壓成一塊交給 Results）、
        # `_on_truth_marked`（X2 寫答案卷 —— 只有主視窗知道資料在哪）、
        # `_on_problem_activated`（U2 點清單 → 選中那張卡）。
        # 三件事的**內容**都在各自的新模組裡。
        "StudioWindow 的方法數（2026-09-02 是 261）",
        lambda: _class_shape("d4t/ui/studio.py", "StudioWindow")[0],
    ),
    "studio_window_attributes": (
        261,
        # 2026-09-29（F122 期 3）：266 → 261。同上那一族拿掉，掉的是它們讀的
        # `self.model.threshold` / `self.trial_scores` 那幾個參照。
        # 2026-09-19（F116 第 6 步）：279 → 266。這一族**沒有任何自己的狀態**
        # （全部讀寫 `win.model`），掉的是那 437 行裡的 `self.*` 參照。
        # 2026-09-19（F116 第 5 步）：292 → 279。只有 `_trial_t0` 與
        # `_write_outputs_sync` 的家跟著走；`trial_worker` / `output_worker`
        # （`stop_run` 也在用）、`trial_results` / `trial_scores`、`_last_run`
        # / `_pending_warnings` / `_filtered_note` / `_write_outputs_this_run`
        # （`_apply_trial_results` 在讀或在寫）全部留在視窗 —— §3-1。
        # 2026-09-19（F116 第 4 步）：308 → 292。`pair_worker` / `_pending_pair`
        # / `_pair_filled` 的家跟著 attach 那一族走；`_carry_filled` 留在視窗
        # （換資料集時 `_on_dataset_loaded` 會清它 —— §3-1）。
        # 2026-09-19（F116 第 3 步）：323 → 308。`thumb_worker` 的家跟著它唯一的
        # 使用者走；`_items_by_id` **留在視窗**（`_on_dataset_loaded` 在寫它 ——
        # §3-1：被別段也寫的留在視窗），進來的是 `gallery_ctl`。
        # 2026-09-19（F116 第 2 步）：389 → 323。**不是視窗上的名字變少**：那一族
        # 照舊在 `win` 上設同樣的 86 個名字，只是那一千行 `self.x = …` 住到
        # `ui/studio_layout.py` 去了，而這一格數的是**這個檔案裡**的 `self.*`。
        # 2026-09-19（F116 第 1 步之 1c）：409 → 389。`_compare_on` 與
        # `_view_syncing` 的家跟著行為走；`_user_stream` / `_user_stream_b`
        # 留在視窗（前者在換卡片時被別段重設 —— §3-1），進來的是 `overlays`。
        # 2026-09-19（F116 第 1 步之 1b）：418 → 409。`_no_profile` 的家跟著
        # `profile_panel` 走，`region_window` / `_region_regions` 仍然是視窗的
        # （`ui/region_check.py` 的函式明寫 `win.xxx = ...`，同 `open_dialogs`）。
        # 2026-09-18（F116 第 1 步）：433 → 418。儀表那一族用到的名字跟著它
        # 的行為走（`_inspector` / `_charts_window` 的家搬進 `GaugePanel`），
        # 進來的只有 `gauges` 一個。
        # 2026-09-18（F114）：434 → 433。同上 —— `load_stack_path` 帶走一個名字。
        # 2026-09-09（第二次）：431 → 437。`_last_run`（上一批的底稿：rows／
        # 量測簽章／被停掉／幾顆，一個 dict 不是四個名字）、`_tree_focus`
        # （編樹時預覽跑到底），以及下面那四支方法的名字。
        # 2026-09-09：430 → 431。`_number_info` —— 設定區「插入數字 ▾」的
        # tooltip／顏色 provider（內容在 `ui/number_picker.py`，這裡只是接線）。
        # 2026-09-08（F99／F100）：418 → 430。走的：`_layout_mode` / `_params_open`
        # / `_SPLIT_KEYS`（進 `WorkbenchLayout`）；來的：`layout_modes` /
        # `main_column` / `workbench` / `verdict_strip` / `verdict_note` /
        # `gauge_note` / `empty_state_host` / `_card_clipboard`，每一個都是
        # 畫面上一塊新東西的把手，內容在各自的模組。
        # 2026-09-08：420 → 418。`btn_layout` / `btn_sample` 兩顆工具列的鈕
        # 搬走了（見 `d4t/ui/studio.py` 那一格）。
        # 2026-09-08（X3 收尾）：419 → 420。
        # 2026-09-08（U5 ＋ U8）：415 → 419。`_layout_mode` / `btn_layout` /
        # `params_row` / `gauge_pane` 進來，`_canvas_popout` / `_popout_view`
        # / `_pre_popout_sizes` 走掉。
        # 2026-09-08：406 → 415。`sample_mode` / `sample_note` / `btn_sample`
        # / `_sample_actions`（X3）加上它們用到的既有名字。
        # 2026-09-08：400 → 406。`status_action`（那顆鈕）加上它與 U21／U17
        # 用到的既有名字。
        # 2026-09-08（U6）：403 → 400。`REGION_TYPES` 那一組判斷跟著
        # `edit_plan.is_region_param` 走了，連帶三個只有它在讀的名字。
        #
        # 之前那一批 393 → 403。`autosave`（草稿）、`problems`（Problems 列）、
        # `status_history`（狀態列說過的話）、`why_preview`（單顆回溯面板）與
        # `_preview_trace`（那一顆的判定重放），加上它們用到的既有名字。
        "StudioWindow 的 self.* 名字數（2026-09-02 是 386）",
        lambda: _class_shape("d4t/ui/studio.py", "StudioWindow")[1],
    ),
    # 22 道遷移撐 5 個 RECIPE_VERSION，而且**只增不減** —— 沒有任何一份文件說
    # 過「舊到哪一版可以不再自動轉」。第 23 道要寫的時候，這一格會先問那句話。
    #
    # 2026-09-18（F110）：20 → 22。`subtract` 拆成比較卡與融合卡（`combine`），
    # 而 `absolute`（bool）換成 `sign`（三選一）。**兩道都看舊的東西在不在**
    # （鐵則 9 的正牌用法，不是 F109 那種只能靠版本號的情況）——
    # `absolute` 那一道的第一版寫成版本閘，被
    # `test_reading_a_recipe_never_invents_a_parameter` 當場擋下來：
    # 舊的 `absolute=True` 跟新的 `sign="abs"` 是同一件事，所以檔案裡沒寫就
    # 什麼都不該寫進去。
    #
    # 2026-09-17（F109）：19 → 20。align 從 `moving`/`fixed`/`out` 改成
    # `streams`/`fixed`/`suffix`（一張卡對 N 條流，DOE 要的形狀）。
    # **這一格問的那句話這一次有答案**：`tests/fixtures/recipes/dual_route_basic.json`
    # 用著 align 而且撐著三組黃金值裡的兩組，出貨的 recipe 也可能帶著舊參數 ——
    # 不寫這道遷移，那些檔案開起來是一張參數全空的卡，跑出來的數字跟以前不一樣
    # **而且不會報錯**。那正是這個 repo 最貴的失敗（「跑得完、有數字、而且是錯的」）。
    # 2026-09-24（F121 期 2）：22 → 23。`load_single`「SEM image」併回
    # `load_patch`「Input」（使用者同意合卡、舊 recipe 自動升級）。**這一格問的
    # 那句話有答案**：兩份出貨 recipe 與 `dual_route_basic.json` 都寫著
    # `load_single`，不遷移的話它們開起來是一條 `unknown-step`。
    "recipe_migrations": (
        # 2026-09-29（F123 期 1）：23 → 24。判定變成一張卡（第 6 版）。
        24,
        "recipe_migrations.py 裡 _migrate_* 的道數（RECIPE_VERSION 現在是 6）",
        _migration_count,
    ),
}


#: **只准往下的那幾格。** 2026-09-09 在 `git log -p` 上量到的：`studio.py` 那一格
#: 從 09-08 到 09-09 兩天被調高 **17 次**（6,942 → 7,750），`StudioWindow`
#: 的方法數 261 → 298。「調高要簽名」的機制是對的，但每一次簽的都是同一個
#: 理由（「這幾支都是接線」），尺就量不到東西了 —— 它變成一本流水帳。
#:
#: 所以這三格從今天起**不再往上**：要往 `studio.py` 加東西，先從它手上拿走
#: 等量的東西（`CLAUDE.md` §4「一塊新的面板／畫布元件＝一個新模組」）。
#: 這張表不是另一個上限 —— 它是「上面那張表裡這幾格的上限本身不准動」。
#: 要改這張表的數字，commit 訊息裡要寫的不是「為什麼多了 40 行」，而是
#: 「為什麼這條規矩今天要廢」。
#: 數字凍在 2026-09-09 `d4t/core/log.py` 那一刀落地之後（每個被吃掉的例外
#: 多一行 `swallowed(...)`，那是整個 repo 一起做的機械改動，不是 Studio 長了）。
HARD_CAPS = {
    # 2026-09-18（F110）：三格一起往下。五顆 Open 的對話框與分岔搬進
    # `ui/open_dialogs.py` —— 行 7,753 → 7,717、方法 298 → 294（五支
    # `_on_open_<key>` 收成模組層的一支）、`self.*` 437 → 434。
    # 那一輪要**加**第五顆 Open 鈕，而這三格只准往下：規矩就是先從它手上
    # 搬走等量的東西，而搬完之後多出來的餘裕要鎖住，不是留著下次偷偷用掉。
    # 2026-09-18（F114）：三格再往下。使用者把 stack 拿掉（「我們用不到」），
    # 而 `load_stack_path` 是 `StudioWindow` 上的一支 —— 行 7,717 → 7,686、
    # 方法 294 → 293、`self.*` 434 → 433。**刪掉東西也要把尺跟著調** ——
    # 留著那段餘裕就是留給下一個人偷偷用掉的空間。
    # 2026-09-18（F116 第 1 步）：三格一起往下。右下角那一族整族搬進
    # `ui/gauge_panel.py` —— 行 7,686 → 7,388、方法 293 → 280、`self.*`
    # 433 → 418。這是 F116 六步裡的第一步（`docs/plans/F116-split-studio.md`），
    # 而那一份的驗收正是「每一步都要讓這三格**明顯**往下」。
    # 2026-09-19（F116 第 1 步之 1b）：行 7,388 → 7,149、方法 280 → 272、
    # `self.*` 418 → 409。
    # 2026-09-19（F116 第 1 步之 1c）：行 7,149 → 6,782、方法 272 → 256、
    # `self.*` 409 → 389。**第 1 步整步做完**：7,686 → 6,782（−904）、
    # 293 → 256（−37）、433 → 389（−44）。
    # 2026-09-19（F116 第 2 步）：介面組裝那一族（工具列、主體、預覽區、進度列、
    # 快捷鍵，七支 `_build_*` ＋ `_tool_button`）整族進 `ui/studio_layout.py`。
    # 行 6,782 → 5,792、方法 248、`self.*` 389 → 323。
    # ⚠ **`self.*` 這一格會掉是因為那一千行的 `self.x = …` 不在這個檔案裡了，
    # 不是因為視窗上的名字變少** —— 那 86 個名字一個都沒動（計畫書 §4 寫著
    # 這一步減的是行數與方法數）。`tools/studio_surface.py` 現在也讀
    # `ui/*.py` 裡的 `win.x = …`，問「那個名字還在不在」要用它，不要用這一格。
    # 2026-09-19（F116 第 3 步）：Gallery／Results／回溯那一族進
    # `ui/gallery_controller.py`，縮圖那一條鏈跟著走。行 5,792 → 5,434、
    # 方法 248 → 235、`self.*` 323 → 308。
    # **前三步合計**：7,686 → 5,434（−2,252）、293 → 235（−58）、433 → 308。
    # 2026-09-19（F116 第 4 步）：行 5,434 → 5,135、方法 235 → 221、
    # `self.*` 308 → 292。**前四步合計**：7,686 → 5,135（−2,551）、
    # 293 → 221（−72）、433 → 292（−141）。
    # 2026-09-19（F116 第 5 步）：行 5,135 → 4,785、方法 221 → 210、
    # `self.*` 292 → 279。**前五步合計**：7,686 → 4,785（−2,901）、
    # 293 → 210（−83）、433 → 279（−154）。
    # 2026-09-19（F116 第 6 步）：行 4,785 → 4,347、方法 210 → 197、
    # `self.*` 279 → 266。**六步全部做完**：7,686 → 4,347（−3,339，−43%）、
    # 293 → 197（−96）、433 → 266（−167）。
    # 2026-09-29（F121 期 1～4）：行 4,347 → 4,302（−45）。入口簡單化那四期在
    # `studio.py` 上刪的比加的多：開資料時不再默默換 route、起手卡的說明收短、
    # Input 卡上那張「你要開哪一種」的選單拿掉（入口只剩一顆）。方法與 `self.*`
    # 一個都沒動。**刪掉的餘裕鎖住**，不留給下一個人偷偷用掉。
    # 2026-09-29（F122 期 2）：行 4,302 → 4,293（−9）。「這一批的底稿」
    # （`_last_run` 那個 dict）搬進 `RunController.snapshot` —— 它要多記判定的
    # 簽章（Write outputs 拿來擋「改了判定沒按 Re-run 就寫」），而那一行不該
    # 加在這裡。方法與 `self.*` 沒動。
    # 2026-09-29（F122 期 3）：行 4,293 → 4,236（−57）、方法 197 → 192、
    # `self.*` 266 → 261。舊門檻那條路退役（判定只剩判定樹）：分數直方圖上
    # 那條拖得動的門檻線、`_on_threshold_changed/_committed`、
    # `_uses_a_threshold`、`_refresh_bin_summary`、`_accuracy_text` 整族拿掉。
    # 2026-09-29（F123 期 1）：行 4,236 → 4,186（−50）、方法 192 → 191。
    # Decision 變成一張卡：`__score__` 偽卡、`_decision_problem` 拿掉。
    "d4t/ui/studio.py": 4186,
    "studio_window_methods": 191,
    "studio_window_attributes": 261,
}


def _slack(ceiling: int) -> int:
    """反向測試的門檻：掉到 ``上限 - slack`` 以下就要求把上限降下來。

    2%（至少 3）—— 大到不會被一次小刪改觸發，小到一次真正的拆分一定會踩到。
    """
    return max(3, ceiling // 50)


# --------------------------------------------------------------------------- #
# 正向：不准超過
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", sorted(FILE_CEILINGS))
def test_a_frozen_file_did_not_grow(rel):
    """凍住的那幾支不准變長。

    要調高的話：改 :data:`FILE_CEILINGS` 那一格，**並在同一個 commit 裡說明
    這一輪為什麼往它加東西**。那句話就是這道關的全部價值。
    """
    ceiling = FILE_CEILINGS[rel]
    actual = _lines(rel)
    assert actual <= ceiling, (
        "%s 現在 %d 行，超過上限 %d 行（+%d）。\n"
        "  這一輪真的該往這一支加東西嗎？`CLAUDE.md` §4：新的面板一律開新模組。\n"
        "  真的該加 → 把 FILE_CEILINGS 裡那一格改成 %d，並在 commit 訊息裡寫\n"
        "  一句為什麼。"
        % (rel, actual, ceiling, actual - ceiling, actual))


def test_an_unlisted_file_stays_under_the_general_ceiling():
    """沒被列名的檔案共用 :data:`GENERAL_CEILING`。

    一支新檔案一寫就超過 2,200 行的話，那件事本身該先講一句話 —— 而不是等它
    變成第六支要凍住的檔案。
    """
    too_big = [(rel, _lines(rel)) for rel in _all_sources()
               if rel not in FILE_CEILINGS and _lines(rel) > GENERAL_CEILING]
    assert not too_big, (
        "這幾支超過一般上限 %d 行：%s\n"
        "  要嘛把它拆小，要嘛把它加進 FILE_CEILINGS 並寫一句為什麼它該這麼大。"
        % (GENERAL_CEILING, too_big))


@pytest.mark.parametrize("name", sorted(COUNT_CEILINGS))
def test_a_counted_thing_did_not_grow(name):
    """不是行數的那幾把尺（耦合、god object、遷移道數）。"""
    ceiling, why, measure = COUNT_CEILINGS[name]
    actual = measure()
    assert actual <= ceiling, (
        "%s 現在是 %d，超過上限 %d（+%d）。\n"
        "  這一格量的是：%s\n"
        "  真的該漲 → 改 COUNT_CEILINGS 那一格並在 commit 訊息裡寫一句為什麼。"
        % (name, actual, ceiling, actual - ceiling, why))


# --------------------------------------------------------------------------- #
# 反向：縮小了，上限要跟著降
# --------------------------------------------------------------------------- #
# `CLAUDE.md`：**任何「例外清單」都要有那支反向的測試**，不然它就是一張只會
# 變長的紙。`tests/test_shipped_recipes.py` 的 ALLOWED_ERRORS 是先例 ——
# 例外修好了卻沒從表上拿掉的話，那份 recipe 從此少一條防線而測試照樣綠。
#
# 這裡是同一件事：`studio.py` 真的拆掉 2,000 行之後，上限如果還留在 6,942，
# 它就可以在沒有人注意的情況下**再長回來**，而那正是這一份要擋的事。
@pytest.mark.parametrize("rel", sorted(FILE_CEILINGS))
def test_a_shrunk_file_lowers_its_ceiling(rel):
    ceiling = FILE_CEILINGS[rel]
    actual = _lines(rel)
    assert actual > ceiling - _slack(ceiling), (
        "%s 只剩 %d 行，而上限還留在 %d —— 中間那 %d 行是白送的成長空間。\n"
        "  把 FILE_CEILINGS 裡那一格改成 %d，把拆分的成果鎖住。"
        % (rel, actual, ceiling, ceiling - actual, actual))


@pytest.mark.parametrize("name", sorted(COUNT_CEILINGS))
def test_a_shrunk_count_lowers_its_ceiling(name):
    ceiling, why, measure = COUNT_CEILINGS[name]
    actual = measure()
    assert actual > ceiling - _slack(ceiling), (
        "%s 只剩 %d，而上限還留在 %d。\n"
        "  這一格量的是：%s\n"
        "  把 COUNT_CEILINGS 那一格改成 %d，把成果鎖住。"
        % (name, actual, ceiling, why, actual))


# --------------------------------------------------------------------------- #
# 只准往下：god object 的三格上限本身不准調高
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", sorted(HARD_CAPS))
def test_the_god_object_ceilings_only_go_down(name):
    """`FILE_CEILINGS` / `COUNT_CEILINGS` 裡 `studio.py` 那三格，上限不准高過
    `HARD_CAPS`。兩天 17 次調高之後，「簽名」已經不是煞車 —— 這一條才是。"""
    if name in FILE_CEILINGS:
        ceiling = FILE_CEILINGS[name]
    else:
        ceiling = COUNT_CEILINGS[name][0]
    assert ceiling <= HARD_CAPS[name], (
        "%s 的上限被調高到 %d，超過 HARD_CAPS 的 %d。這一格不再往上：要往 "
        "studio.py 加東西，先從它手上搬走等量的東西（開新模組），再回來。"
        % (name, ceiling, HARD_CAPS[name]))


def test_the_hard_caps_name_real_ceilings():
    for name in HARD_CAPS:
        assert name in FILE_CEILINGS or name in COUNT_CEILINGS, name


# --------------------------------------------------------------------------- #
# 這把尺自己有沒有在量東西
# --------------------------------------------------------------------------- #
def test_every_frozen_file_exists():
    """表上列的檔案要真的在磁碟上 —— 改名或刪檔之後這一格會變成死的。"""
    missing = [rel for rel in FILE_CEILINGS if not (REPO / rel).exists()]
    assert not missing, "FILE_CEILINGS 上這幾支已經不存在了：%s" % missing


def test_the_general_ceiling_is_not_vacuous():
    """一般上限要真的貼著現役的大檔，不然它是一道永遠不會響的關。"""
    rest = [_lines(rel) for rel in _all_sources() if rel not in FILE_CEILINGS]
    assert rest, "掃不到任何檔案 —— SCOPE 設錯了？"
    assert max(rest) > GENERAL_CEILING * 0.85, (
        "沒被列名的檔案最長才 %d 行，而上限是 %d —— 差太多，這道關幾年都不會響。"
        % (max(rest), GENERAL_CEILING))


def test_the_coupling_metric_does_not_count_look_alikes():
    """指標本身要誠實：同名但不是卡片的字串不能算進來。

    實測過的兩個假陽性，兩個都必須**不**在結果裡：

    * ``widgets.py`` 的 ``setProperty("tone", tone)`` —— Qt 屬性，跟 `tone`
      那張卡無關；
    * ``inspectors.py`` 的 ``{"subtract": "−", "ratio": "÷"}`` —— 運算子符號表。

    這一條是這把尺的自我檢查：指標髒掉的話，凍住的那個數字就沒有意義。
    """
    hits = card_key_couplings()
    files = {rel for rel, _ln, _how, _key in hits}
    assert "d4t/ui/widgets.py" not in files, (
        "widgets.py 被算進去了 —— 它只有 Qt 的 setProperty(\"tone\", …)，"
        "指標把同名字串誤算成卡片耦合了：%s"
        % sorted(h for h in hits if h[0] == "d4t/ui/widgets.py"))
    ops = [h for h in hits if h[0] == "d4t/ui/inspectors.py" and h[2] == "compare"]
    assert not ops, "inspectors.py 的運算子符號表被算成比較了：%s" % ops


def test_the_sanctioned_tables_are_really_the_registration_path():
    """:data:`SANCTIONED_TABLES` 排除掉的那兩張，要真的是 UI 的註冊表。

    它們哪天改名或不再是擴充點的話，這裡會紅 —— 否則那個排除會安靜地
    變成「排除一張不存在的表」，而真正的註冊表開始被算進耦合裡。
    """
    src = (REPO / "d4t/ui/inspectors.py").read_text(encoding="utf-8")
    for name in SANCTIONED_TABLES:
        assert re.search(r"^%s\s*[:=]" % name, src, re.M), (
            "d4t/ui/inspectors.py 裡沒有叫 %s 的表了 —— "
            "SANCTIONED_TABLES 要跟著改" % name)
    assert "INSPECTORS.get(key)" in src, \
        "inspector_for() 不再讀 INSPECTORS 了 —— 註冊路徑換了，這張表要重看"
