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
    "d4t/ui/studio.py": 7717,
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
    "d4t/core/pipeline/recipe.py": 4101,
    # 逐卡儀表板。這一支變長**通常是健康的**（加一張卡就多一個面板），所以
    # 這一格比其他四格更常需要調高 —— 那沒關係，重點是調高時有人看見。
    # 2026-09-08（F99 P0-2）：3,622 → 3,660。`header_boxes` —— 共用 header 左右
    # 兩段以前畫進同一個矩形而沒有一方讓寬度，面板窄到 200 px 時疊在一起。
    # 2026-09-17（F109）：3,660 → 3,669（+9）。`AlignInspector` 的散佈圖以前寫死
    # `align_dx`／`align_dy` 兩個名字，而 align 現在對 N 條流、三條以上時特徵名
    # **帶著流名前綴** —— 寫死的那一版在 DOE（一次 N 個 condition，正是這張圖最
    # 有用的時候）會畫出一張**空圖**，而空圖上寫的是「跑一次試跑就看得到」。
    # 多的幾行是「跟卡片要名字，不自己拼字串」與那句為什麼。
    "d4t/ui/inspectors.py": 3669,
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
    "d4t/ui/canvas.py": 3070,
    # `CLAUDE.md` **每個 session 都會被讀進去**。2026-09-09 之前它是 647 行，
    # 一半是「某年某月使用者說了什麼」的故事 —— 規則留下、故事搬進
    # `docs/history/CLAUDE-2026-09-09.md`，瘦到 319 行。這一格擋它長回去：
    # 要加一條規矩可以，要加一段故事去 SESSION_LOG／history。
    "CLAUDE.md": 323,
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
    src = (REPO / "d4t/core/pipeline/recipe.py").read_text(encoding="utf-8")
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
    "ui_card_key_coupling": (
        23,
        "d4t/ui 裡按卡片名字分支的地方（不含 INSPECTORS/BY_METHOD 兩張註冊表）",
        lambda: len(card_key_couplings()),
    ),
    # god object 的兩個投影。261 → 268（六天）。
    "studio_window_methods": (
        294,
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
        # `toggle_layout_mode` / `_sync_layout_button` / `_build_params_row`。
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
        434,
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
    "recipe_migrations": (
        22,
        "recipe.py 裡 _migrate_* 的道數（RECIPE_VERSION 現在是 5）",
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
    "d4t/ui/studio.py": 7717,
    "studio_window_methods": 294,
    "studio_window_attributes": 434,
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
