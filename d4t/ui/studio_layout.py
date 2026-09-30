# d4t UI — authored 2026-09-19 (F116 第 2 步).
"""`StudioWindow` 的**介面組裝**：工具列、主體、預覽區、進度列、快捷鍵。

為什麼自己一個模組（`CLAUDE.md` §4：`studio.py` 留給接線，不留給內容）：
這一族是**擺東西**，一千行裡沒有一條是接線 —— 哪一顆鈕放在哪一段、分隔線切在
哪裡、哪一塊包進捲軸、三欄的比例。它跟 `studio.py` 剩下的東西
（model → UI、signal 接線）沒有共用任何狀態。

**形狀照 `ui/open_dialogs.py` 的慣例**：模組層函式吃 `win`，而且**照舊在 `win`
上設屬性**（`win.toolbar`、`win.btn_trial`、`win.image_view`…）。那 86 個名字
一個都沒有改 —— 測試與其他模組大量用它們，而這一步搬的是「這段程式碼住在哪」，
不是「這些東西叫什麼」。所以這一步減的是**行數與方法數，不是 `self.*` 數**
（F116 §4 寫著那是預期的）。

⚠ **`fit_screen.scrolled` 要在建構時包**（`CLAUDE.md` §4 F91）：
`build_preview_pane` 裡那一行「先建好 `pane` 再 `fit_screen.scrolled(pane)`」的
順序不准動 —— 事後把一個已經長好的 widget 搬進捲軸在 PySide6 上是 **segfault**，
不是例外。

**行為零改動**（F116 §1）：本體逐字搬，只把 `self` 換成 `win`。

⚠ **這一支跑在 controller 建出來之前**（F116 §7-2 的順序：介面組裝 → controller
→ 接線）。所以指到 controller 的 slot **一律包一層 `lambda`** ——
`win.run_ctl._on_trial_clicked` 這樣寫會在**建工具列的當下**去查
`win.run_ctl`，而那一刻它還不存在（症狀是建視窗就 AttributeError）。
包了之後查詢延到「使用者按下去」那一刻，那時一切都在了。
"""
from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QProgressBar,
    QPushButton, QSizePolicy, QSpinBox, QStackedWidget, QToolBar, QToolButton,
    QVBoxLayout, QWidget,
)

from d4t.core.pipeline import sampling

from . import fit_screen
from . import language
from . import open_dialogs
from . import scope
from . import strings
from .canvas import PipelineCanvas
from .decide_panel import DecidePanel
from .feature_panel import FeaturePanel
from .image_view import ImageView
from . import cross_links
from . import wording
from .problems_bar import ProblemsBar
from .results import ResultsWindow
from .splitters import HairlineSplitter
from .why_panel import WhyPanel
from .widgets import (
    IconButton, LibraryPanel, ParamForm, VerdictChip, _GlyphMixin,
    column_header, small_button,
)
from .workbench import WorkbenchLayout

if TYPE_CHECKING:                      # 只給型別看：這一支不 import studio
    from .studio import StudioWindow


class _GlyphToolButton(_GlyphMixin, QToolButton):
    """工具列上會自己畫圖示的 QToolButton（``_tool_button(icon=…)`` 用）。

    F116 第 2 步跟著 `_tool_button` 從 `studio.py` 搬過來 —— 那一支是它唯一的
    使用者。
    """


# --------------------------------------------------------------------------- #
# 版面常數（F116 第 2 步跟著用它們的程式碼搬過來）
# --------------------------------------------------------------------------- #
#: 單顆預覽那兩個下拉框的寬度上限（px）。
DEFECT_COMBO_MAX = 220
STREAM_COMBO_MAX = 180

#: 主視窗三欄的出廠寬度：卡片庫 | 主欄（畫布在上、設定區與儀表在下）| 單顆預覽。
#: F100 v2（`ui/workbench.py`）：影像回到右欄、全高——調參數的迴圈是
#: 「改一格 → 看影像」，那一刻影像是主角；畫布在 Tune 裡是導覽，要全貌有 Build。
COLUMN_SIZES = (256, 660, 450)

#: 「試跑筆數」的出廠值。載入資料集時會再夾成 ``min(這個值, 資料集顆數)`` ——
#: 對一份只有 24 顆的 lot 顯示 200 沒有任何意義，只會讓人以為自己看錯了。
DEFAULT_TRIAL_N = 200


def clear_selection(win: Any) -> None:
    """Esc（與那個連結）：放掉手上的東西 —— **而且預覽跟著跑到底**。

    ⚠ **以前它只放掉畫布那一份**（F117 D1）：`win.selected_node` 原封不動，
    而預覽停在哪裡看的正是它（`_run_preview` 的 `upto`）。所以膠囊旁邊那句
    「press Esc to run the decision too」**是假的** —— 按了 Esc 畫布上的框
    不見了，預覽照樣停在同一張卡上，判定也照樣沒有跑。

    走查把 D1 記成「句子是對的，但很難被想到」；查下去**句子也不是對的**。

    ⚠ 這一支住在這裡而不是 `studio.py`：那一支的三格尺只准往下（F116），
    而這是畫布與視窗之間的接線 —— 這個模組正是接線的家。
    """
    win.pipeline.clear_selection()
    if getattr(win, "selected_node", None) is None:
        return
    win.selected_node = None
    win.param_form.set_step(None, {}, [])
    win._schedule_preview()


def build_toolbar(win: "StudioWindow") -> None:
    """工具列（M7 精簡；F7-22 分組）。

    兩處刻意的取捨：

    * **「載入範本」併進「Templates…」** —— 舊版兩顆鈕做的是同一件事
      （都在載 ``examples/recipes/`` 底下的 JSON），而 die-to-die 對第一次
      用的人是行話。現在只留一個入口，範本庫自己把 die-to-die 排第一。
    * **「全跑」收進「Run trial」的下拉** —— 兩顆長得一樣的 ▶ 鈕擺在一起，
      新手分不出差別也不知道該按哪顆。主要動作只留一顆，破壞性比較大的
      「跑整批」降級成選單項目。⚠ 這一條後來被 F16 Stage 5c 悄悄破壞了
      （「Export…」空出來的那一格改成整批入口，於是同一支 `run_all()`
      在工具列上有兩顆鈕）—— 2026-08-24 使用者指出來之後拿掉那一顆，
      這條規矩恢復成唯一的答案。

    分組（F7-22）
    -------------
    以前是七顆長得一模一樣的鈕排成一列，沒有任何分隔 —— 讀起來是一串等權重
    的東西，使用者得逐顆讀完才知道哪顆是自己要的。現在照**做什麼事**分四段，
    中間用分隔線：

        檔案（開/存） │ 起手與輸出 │ 復原 │ ……… │ 結果・主題 │ 試跑

    Results 與主題在右邊：它們是**隨時可用但不屬於流程**的東西，混在檔案
    操作裡只會讓左邊那段變長。（`Help` 鈕 2026-09-24 使用者要求拿掉 ——
    連同它掛著的「開著哪些視窗」小箭頭。）試跑仍然在最右邊 —— 它是這個畫面的主要動作。

    **復原／重做這一輪才長出按鈕。** F7-16 給了 Ctrl+Z / Ctrl+Shift+Z，
    但工具列上沒有對應的鈕 —— 而目標使用者是不寫 code 的工程師，
    「這個軟體能不能反悔」這件事不該只寫在快捷鍵裡。
    """
    bar = QToolBar("Main actions", win)
    bar.setMovable(False)
    bar.setFloatable(False)
    win.toolbar = bar
    win.addToolBar(bar)

    # **資料的入口不在工具列上**（F14-1，2026-08-19 使用者定調：
    # 「工具列拿掉吧（會混淆）」）。
    #
    # 它現在長在**讀那份資料的那張卡上**（`ParamForm.set_source_action`）。
    # 理由跟這幾輪一直在講的是同一條：以前檔案在工具列上選，而畫布上那張
    # Load 卡完全不會說它讀的是哪個檔案 —— 同一件事兩個地方，而畫布是說謊
    # 的那一個。之後一份 recipe 要掛好幾個 source 的時候，入口也已經在對的
    # 地方了。
    #
    # **入口沒有變少，只是搬家**：畫面最大的那一塊（沒有資料時的空白狀態）
    # 仍然一種 source 一列（`empty_source_buttons`，從同一張 `INPUT_SOURCES`
    # 長出來），而那是第一次進來的人真的會看的地方。
    win.btn_open_recipe = _tool_button(win,
        "Open recipe…", "Load a recipe JSON",
        partial(open_dialogs.open_recipe, win),
        icon="document")
    # **存檔回來了**（2026-08-26）。2026-08-16 拿掉的理由是「先把整個
    # engine 用好，再來支援」，而 Phase 1 同一天就收斂了 —— 那個前提到期。
    #
    # 一顆鈕、兩個快捷鍵：`Ctrl+S` 存回原檔（第一次沒有原檔就問），
    # `Ctrl+Shift+S` 一定問。鈕接的是 `Ctrl+S` 那一支 —— 使用者按工具列上
    # 那顆鈕的意思是「存起來」，不是「我要選一個路徑」。
    win.btn_save_recipe = _tool_button(win,
        "Save recipe…", "Save this pipeline as a recipe JSON",
        partial(open_dialogs.save_recipe, win), icon="save")
    win.btn_examples = _tool_button(win,
        "Templates…",
        "Open the template library — every entry is a complete, runnable "
        "pipeline. Start here rather than from an empty pipeline.",
        win.open_recipe_library, icon="templates")
    # **2026-09-08（F91 X4）：這顆鈕回來了。** 它收起來的理由是「範本庫是
    # 空的」（``examples/`` 已移除），而 `recipes/` 現在有出貨的 recipe、
    # 逐份有測試跑過 —— 那個理由到期了。開關在
    # ``scope.SHOW_TEMPLATE_LIBRARY``。
    win.btn_examples.setVisible(bool(scope.SHOW_TEMPLATE_LIBRARY))
    # ⚠ **這裡以前還有一顆「Run all & write」**，而它跟 `Run trial ▾` 選單
    # 裡的「跑整批」是**同一支函式**（兩邊都是 `run_all()`，一個位元的
    # 差別都沒有）。兩個決定各自都對，只是沒有互相看到：M7 把「全跑」收進
    # 下拉（見這支的說明），而 F16 Stage 5c 把「Export…」空出來的那一格
    # 改成整批入口。合起來就是同一個動作在工具列上有兩顆鈕。
    #
    # 使用者 2026-08-24：「若沒差或差不多 請留一個即可（傾向 trial）」。
    # 留下的是下拉裡那一項 —— 而**「跑完之後要做的那件事」搬到它真的會
    # 發生的地方**：Results 視窗（使用者正在看試跑結果，下一步才是整批）。
    # 工具列因此只剩一顆有顏色的鈕，而那正是這個畫面唯一的主要動作。
    win.btn_undo = _tool_button(win,
        "", "Undo the last change", win.undo, icon="undo")
    win.btn_redo = _tool_button(win,
        "", "Redo the change you just undid", win.redo, icon="redo")
    # **第三級：純圖示、沒有框**（F13-2）。工具列上「有框的字」是按鈕、
    # 「沒框的字」讀起來是選單列（那條規矩沒有變，見 theme.py）——
    # 但這幾顆**沒有字**，所以那個顧慮不成立，而它們也不該跟 `Open KLARF…`
    # 搶同一級的視覺重量：它們是隨時在旁邊的工具，不是流程上的一步。
    for b in (win.btn_undo, win.btn_redo):
        b.setProperty("variant", "ghost")
    # **Results 視窗的入口**（F48，2026-08-28，使用者：「可以改成加一個
    # 按鈕獨立呼叫一個視窗嗎（目前是跑完才會出來）」）。
    #
    # 以前只有兩條路會開它：跑完自動彈出、或在直方圖上點一根長條 ——
    # 兩條都要**先跑過一批**。關掉之後想再看一次，唯一的辦法是再跑一次
    # （而 `results.py` 的檔頭一直寫著「關掉它不會丟掉結果」：結果確實
    # 還在，只是沒有一顆鈕叫得出來，所以那句話描述著一個不存在的入口）。
    #
    # **跟主題同一段**，而不是接在 `Run trial` 右邊。動線上「跑 →
    # 看結果」確實是那個順序，但工具列的最後一格是留給那顆藍鈕的
    # （`test_the_toolbar_is_grouped_not_one_long_row` 守著：試跑在最後
    # 面）—— 而這一段的定義正好就是它：**不屬於流程、但要隨時找得到**。
    win.btn_results = _tool_button(win,
        "Results", "Open the Results window - score distribution, "
                   "thumbnails and the per-defect table (Ctrl+Shift+R)",
        win.show_gallery, icon="popout")
    # **這顆鈕以前不會說裡面有沒有東西**（U21）。`ResultsWindow` 是先建好、
    # 跑完才 show，關掉不丟結果 —— 機制是對的，但使用者的心智模型裡「關掉
    # 視窗」通常等於「丟掉」，而鈕上沒有任何東西反駁那個猜測。
    win._refresh_results_button()
    # 主題切換：一顆字元鈕，不佔位子也找得到（偏好存 QSettings）
    win.btn_theme = _tool_button(win,
        "", "Switch between the light and dark theme",
        win.toggle_theme, icon="theme")
    win.btn_theme.setProperty("variant", "ghost")
    # 語言切換（評價清單 #6，2026-09-24）：鈕上寫的是**按下去會切到的那一種**
    # （「中文」／「EN」），跟主題鈕一樣是 ghost —— 隨時找得到、不搶流程的重量。
    win.btn_lang = _tool_button(
        win, language.button_text(),
        "Switch the interface language - d4t restarts to apply it",
        lambda: language.toggle(win))
    win.btn_lang.setProperty("variant", "ghost")

    # 一段 = 一種事情；段與段之間一條分隔線。
    #
    # ⚠ **整段都看不見的時候不要放那條分隔線。** 「Templates…」曾經是藏著的
    # （`scope.SHOW_TEMPLATE_LIBRARY`，2026-09-08 打開），而它那一段以前
    # 還有「Run all & write」
    # 撐著；那顆鈕 2026-08-24 拿掉之後，那一段變成空的 —— 工具列上因此出現
    # 兩條連在一起的分隔線，中間夾著什麼都沒有。分隔線講的是「這裡換一種
    # 事情」，而一條隔開空氣的線只是雜訊。
    for group in ((win.btn_open_recipe, win.btn_save_recipe),
                  (win.btn_examples,),
                  (win.btn_undo, win.btn_redo)):
        # ⚠ **鈕還是要 addWidget**（藏著的也要）：建了卻沒加進工具列的
        # widget 會以工具列為 parent 疊在左上角
        # （`test_every_button_built_for_the_toolbar_is_actually_on_it`
        # 在第一版就抓到了）。跳過的只有那條**分隔線**。
        #
        # ⚠ 而「這一段看不看得見」**要在 addWidget 之前問**，用的也不是
        # `isHidden()`：`addWidget` 會把 widget 包進一個 QWidgetAction，
        # 而 Qt 在工具列真的顯示出來以前把它們**全部**藏著 —— 那時候
        # 每一顆都答 hidden，於是一條分隔線都不會加。要問的是「**我們**
        # 有沒有明講要藏它」（`setVisible(False)` 留下的那兩個屬性）。
        visible = [b for b in group
                   if not (b.testAttribute(Qt.WA_WState_ExplicitShowHide)
                           and b.testAttribute(Qt.WA_WState_Hidden))]
        for b in group:
            bar.addWidget(b)
        if visible:
            bar.addSeparator()

    # 分流的 route 切換器（F23 期2）：`RecipeModel` 一次編一條 route
    # （§6 第一期不動的那條），切換是「換一條來編」—— 畫布跟著換。
    # 只有一條 route 時整組收起來（多數 recipe 用不到它）。
    win.lbl_route = QLabel("Route ", bar)
    win.route_combo = QComboBox(bar)
    win.route_combo.setToolTip(
        "Which route (which set of cards) the canvas is editing. "
        "With route_by, each defect picks its own route at run time.")
    win.route_combo.activated.connect(win._on_route_combo)
    # ⚠ 工具列上的顯示/隱藏要走 **addWidget 回傳的 QAction**：直接
    # `widget.setVisible(False)` 會被 QToolBar 的排版蓋回去 —— 症狀是
    # 單 route 的 recipe 工具列上掛著一個空的下拉。
    win._route_actions = [bar.addWidget(win.lbl_route),
                           bar.addWidget(win.route_combo)]
    for act in win._route_actions:
        act.setVisible(False)

    spacer = QWidget(bar)
    spacer.setObjectName("toolbarSpacer")
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    bar.addWidget(spacer)

    # 右邊：不屬於流程、但要隨時找得到的那幾顆。
    bar.addWidget(win.btn_results)
    bar.addWidget(win.btn_lang)
    bar.addWidget(win.btn_theme)
    bar.addSeparator()

    # **工具列的字要跟著抽樣方式換**（X3）。以前這裡寫死是「First」，
    # 而如果換了抽樣方式畫面卻沒有變，就是這個功能最危險的失敗方式：
    # 跑的東西變了、看的人不知道。字從 `sampling.describe()` 來。
    #
    # ⚠ **那個字自己就是那顆鈕。** 第一版是「一個 QLabel ＋ 旁邊一顆
    # 『…』」，而那多花 56 px —— 工具列在 1366×768 上量出來 1,285 px，
    # 超過那台機器的 1,229 px，尾巴幾顆會被收進 » 溢位選單
    # （`test_ui_small_screen` 當場抓到）。合成一顆之後既省了寬度，
    # 也比較誠實：會變的那個字就是可以點的那個東西。
    win.lbl_trial_n = QToolButton(bar)
    win.lbl_trial_n.setCursor(Qt.PointingHandCursor)
    win.lbl_trial_n.setPopupMode(QToolButton.InstantPopup)
    bar.addWidget(win.lbl_trial_n)
    win.spin_trial_n = QSpinBox(bar)
    win.spin_trial_n.setRange(10, 5000)
    # 「First 200」旁邊沒有單位時，200 可以是任何東西（秒？百分比？）。
    win.spin_trial_n.setSuffix(" defects")
    win.spin_trial_n.setValue(DEFAULT_TRIAL_N)
    win.spin_trial_n.setToolTip(
        "How many defects a trial run covers (keep it small while tuning)")
    bar.addWidget(win.spin_trial_n)

    # 抽樣方式（X3）：**一個下拉，掛在上面那個會變的字上**（見上）。
    menu_s = QMenu(win.lbl_trial_n)
    win._sample_actions = {}
    for mode in sampling.MODES:
        word, why = sampling.describe(mode)
        act = menu_s.addAction(word)
        act.setToolTip(why)
        act.setCheckable(True)
        act.setChecked(mode == win.sample_mode)
        act.triggered.connect(
            lambda _c=False, m=mode: win.set_sample_mode(m))
        win._sample_actions[mode] = act
    win.lbl_trial_n.setMenu(menu_s)
    win.set_sample_mode(win.sample_mode, say=False)

    win.btn_trial = _tool_button(win,
        "Run trial", "Run the current pipeline over the first N defects "
                     "and show the score distribution",
        lambda: win.run_ctl._on_trial_clicked(), primary=True, icon="play")
    # 「跑整批」是同一顆鈕的次要動作：點主體 = 試跑，點箭頭才看得到它。
    menu = QMenu(win.btn_trial)
    # ⚠ ``&&`` 不是筆誤：Qt 把單一個 ``&`` 當成助憶鍵的記號吃掉，畫出來
    # 是 **``Run all _write``**（使用者就是這樣叫它的）。要顯示一個真的
    # ``&`` 就得寫兩個。
    #
    # 名字跟 Results 視窗那顆**逐字相同** —— 同一個動作在兩個地方叫兩個
    # 名字，正是上面那兩顆鈕變成兩顆的第一步。
    # 2026-09-09 起它**只跑，不寫**：寫是 Results 視窗上另一顆鈕
    # （「Write outputs」）—— 使用者要先看過結果再決定要不要寫。
    win.act_run_all = QAction("Run all", menu)
    win.act_run_all.setToolTip(
        "Run every defect, not just the first N. Nothing is written - "
        "press “Write outputs” in Results when the numbers look right.")
    win.act_run_all.triggered.connect(lambda: win.run_ctl._on_full_clicked())
    menu.addAction(win.act_run_all)
    win.trial_menu = menu

    # 箭頭是**第二顆真的按鈕**，不是 ``MenuButtonPopup``（F7-23 第二輪）。
    #
    # 以前這兩個動作是同一顆 QToolButton 的兩半，而那半邊的外觀完全歸 Qt
    # 管：它用自己的淺色按鈕樣式畫在我們的藍底上，也不理會圓角 —— 全 UI
    # 最重要的一顆鈕，右邊掛著一塊跟主題無關的東西。
    #
    # 補樣式補不起來：只要給 ``::menu-button`` 一個盒子（背景、邊框、圓角
    # **任一**），Qt 就把繪製整個交給 stylesheet，而 stylesheet 沒有
    # ``image`` 就不畫箭頭 —— 這個 repo 是純文字的（docs/FAB-VALIDATION.md）塞不了
    # 圖檔。實測只有 ``width`` 是安全的。同一條坑 F7-13 在
    # ``QComboBox::drop-down`` 上踩過，這次量到 ``::menu-button`` 上。
    #
    # 所以拆成兩顆普通按鈕，兩顆都是我們控制得了的。這顆**不設 menu**：
    # 設了 Qt 又會自己加一個下拉指示器，等於畫兩個箭頭。
    win.btn_trial_more = _tool_button(win,
        "", "More ways to run — including the whole dataset",
        win._popup_trial_menu, primary=True, icon="chevron_down")

    # 兩顆**放進同一個容器**，中間只留 1px（F7-24 第二輪）。
    #
    # 分開放在工具列上時它們吃全域的 6px 間距，讀起來像兩顆不相干的按鈕 ——
    # 而箭頭是 ``Run trial`` 的次要動作，不是另一個功能。1px 的縫加上內側
    # 拉直的圓角（QSS 的 ``[seg]``）就是一個分段控制項：**一件事，兩個半邊**。
    #
    # 注意這跟 F7-23 拆掉 ``MenuButtonPopup`` 不衝突：那一輪要的是「這半邊的
    # 外觀歸我們管」，而這裡正是在管它 —— 差別在現在兩個半邊都是真的按鈕。
    win.btn_trial.setProperty("seg", "left")
    win.btn_trial_more.setProperty("seg", "right")
    group = QWidget(bar)
    group.setObjectName("toolbarGroup")
    glay = QHBoxLayout(group)
    glay.setContentsMargins(0, 0, 0, 0)
    glay.setSpacing(1)
    glay.addWidget(win.btn_trial)
    glay.addWidget(win.btn_trial_more)
    win.trial_group = group
    bar.addWidget(group)


def _tool_button(win: "StudioWindow", text: str, tip: str, slot: Any,
                 primary: bool = False,
                 icon: Optional[str] = None) -> QToolButton:
    """工具列上的一顆鈕。``icon`` 給的是**自繪**圖示的名字（不是字元）。

    有文字又有圖示時（只有 ``Run trial``），圖示畫在左邊那一格 ——
    QSS 的 ``[hasGlyph="true"]`` 把左邊 padding 撐開，文字才不會疊上去。
    """
    b = _GlyphToolButton(win) if icon else QToolButton(win)
    # **翻譯層擺在共用的那一支**（U14）：工具列的每一顆鈕都流過這裡，所以
    # 包這一次就涵蓋整條工具列 —— 而呼叫端一個字都不用改。那正是「之後
    # 不必改 38 個檔案」那句話成立的方式。
    b.setText(strings.tr(text))
    b.setToolTip(strings.tr(tip))
    b.setToolButtonStyle(Qt.ToolButtonTextOnly)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setObjectName("primary")
    if icon:
        b._init_glyph(icon, "left" if text else "center")
    b.clicked.connect(slot)
    return b


def build_shortcuts(win: "StudioWindow") -> None:
    handlers = {
        "open_klarf": partial(open_dialogs.open_source, win,
                              scope.INPUT_SOURCES[0].key),
        "open_recipe": partial(open_dialogs.open_recipe, win),
        "save_recipe": partial(open_dialogs.save_recipe, win),
        "save_recipe_as": partial(open_dialogs.save_recipe_as, win),
        "run": lambda: win.run_ctl._on_trial_clicked(),
        "results": win.show_gallery,
        "undo": win.undo,
        "redo": win.redo,
        "zoom_reset": win.pipeline.reset_zoom,
        "zoom_in": lambda: win.pipeline.zoom_by(1.25),
        "zoom_out": lambda: win.pipeline.zoom_by(1 / 1.25),
        "zoom_fit": win.pipeline.fit,
        "find_card": win.focus_card_search,
        "prev_defect": lambda: win.step_defect(-1),
        "next_defect": lambda: win.step_defect(+1),
        "layout_mode": win.toggle_layout_mode,
        "delete_selected": win._delete_selected_on_canvas,
        "clear_selection": win._clear_canvas_selection,
        "copy_cards": win.copy_cards,
        "paste_cards": win.paste_cards,
        "duplicate_cards": win.duplicate_cards,
    }
    win._shortcuts = []
    for keys, name in win.SHORTCUTS:
        # 畫布專用的那幾個掛在畫布上、而且是 `WidgetWithChildrenShortcut`
        # —— 焦點不在畫布裡的時候它們根本不會被叫到（U18）。
        host = win.pipeline if name in win._WIDGET_SHORTCUTS else win
        sc = QShortcut(QKeySequence(keys), host)
        if name in win._WIDGET_SHORTCUTS:
            sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(handlers[name])
        win._shortcuts.append(sc)

    # 按鍵存在還不夠 —— 使用者要**發現得到**。工具列的 tooltip 是他唯一
    # 會停留的地方，所以把快捷鍵寫進去（作業系統慣例：括號附在後面）。
    #
    # 註冊而不是「設一次」：``_update_action_states`` 每次 refresh 都會重寫
    # 這幾顆的 tooltip（「還沒有東西可以存」之類的原因），設一次的話第一次
    # refresh 就被蓋掉了。所以改成**設 tooltip 的那個動作自己會補上快捷鍵**。
    win._tip_keys = {
        id(win.btn_open_recipe): "Ctrl+Shift+O",
        id(win.btn_save_recipe): "Ctrl+S",
        id(win.btn_trial): "Ctrl+R",
        # F14-1：`Ctrl+O` 的鈕搬到空白狀態與入口卡上了（工具列那幾顆
        # 拿掉了），而快捷鍵一個字都沒變 —— 它要在**還看得到的**那顆鈕上
        # 講出來，不然它就只活在原始碼裡。
        id(win.btn_empty_open): "Ctrl+O",
        # F7-22：這兩顆這一輪才長出來，快捷鍵 F7-16 就有了。
        id(win.btn_undo): "Ctrl+Z",
        id(win.btn_redo): "Ctrl+Shift+Z",
    }
    for w in (win.btn_open_recipe, win.btn_save_recipe,
              win.btn_trial, win.btn_empty_open,
              win.btn_undo, win.btn_redo):
        win._set_tip(w, w.toolTip())


def build_progress(win: "StudioWindow") -> None:
    """狀態列右側的進度條（F7-7）。

    以前載入資料集與試跑都只有狀態列的一行字，那對「跑一批一萬顆」這種
    會等好幾分鐘的動作是不夠的 —— 使用者看不出還要多久、也看不出它到底
    在不在動。這條進度條在**閒著時完全隱藏**，不佔位子也不製造噪音。

    載入 KLARF 沒有可回報的百分比（``load_dataset`` 是一次呼叫），所以那個
    情況用**不定型**（range 0–0）的跑馬燈：它回答的是「還在動嗎」，
    而不是「還剩多久」——謊報一個假的百分比比不報還糟。
    """
    win.progress = QProgressBar(win)
    win.progress.setFixedWidth(220)
    win.progress.setTextVisible(True)
    win.progress.setVisible(False)
    # 明確狀態：``isVisible()`` 在視窗 show() 之前一律 False，
    # headless 測試會全部誤判（同 LibraryPanel 的 badge，見 widgets.py）。
    win._progress_on = False
    win.statusBar().addPermanentWidget(win.progress)

    # 「跑到一半發現參數設錯」是最常見的情況，而一萬顆要好幾分鐘（F7-16）。
    # 引擎本來就支援中止（``run_batch`` 的 ``abort_check``、
    # ``TrialWorker.abort``）—— 只是以前沒有任何地方按得到它，
    # 於是使用者唯一的中止方式是把整個視窗關掉。
    win.btn_stop = QPushButton("Stop", win)
    win.btn_stop.setProperty("variant", "danger")
    win.btn_stop.setToolTip(
        "Stop this run. Defects already finished are kept — you get the "
        "results for them, not nothing.")
    win.btn_stop.setVisible(False)
    win.btn_stop.clicked.connect(win.stop_run)
    win.statusBar().addPermanentWidget(win.btn_stop)
    win._stop_on = False


def build_body(win: "StudioWindow") -> None:
    # 左：卡片庫
    win.library = LibraryPanel(win)
    win.library.panel_toggled.connect(win._on_library_panel_toggled)

    # 中：流程畫布（上）+ 參數表單／分數編輯（下）。
    #
    # 版面史，因為它繞了一圈（F7-22 → F8-UI 抽屜 → 現在）：F7-22 讓參數
    # 預設收起、雙擊才攤開（畫布是主體）；F8-UI 第一輪改成畫布右緣的
    # 抽屜 —— 使用者當天就退了它：「pipeline 往右長，抽屜也吃右邊，兩個
    # 在搶同一個方向」。他拍板的形狀（D 案）是：**畫布會 zoom、又有
    # 彈出視窗，所以平面上只需要中上一塊**；大空間還給設定與影像。
    # 所以：上下切回來、比例反過來（畫布 2 / 設定 3）、設定**預設攤開**，
    # 「看全貌」由 zoom bar 的彈出視窗鈕承接（open_canvas_window）。
    win.pipeline = PipelineCanvas(win)
    # 主畫布是概覽條（D 案）：fit 的「全部看得完」贏過「副標讀得出」。
    # 讀細節的地方是下方設定區與彈出視窗（那份維持類別預設 0.7）。
    win.pipeline.MIN_FIT_SCALE = 0.5
    win.param_form = ParamForm(win)
    # 「插入數字 ▾」每一項的說明與顏色點（`number_picker`，2026-09-09）。
    win.param_form.number_info_provider = win._number_info
    win.score_pane = build_score_pane(win)
    # 判定樹一步的編輯面板（F24 ③）—— 點畫布上的菱形時換到它。
    from .tree_panel import TreePanel

    win.tree_pane = TreePanel(win)
    win.tree_pane.set_model(win.model)
    win.tree_pane.step_requested.connect(win._on_tree_step_clicked)
    win.stack = QStackedWidget(win)
    win.stack.addWidget(win.param_form)     # index 0
    win.stack.addWidget(win.score_pane)     # index 1
    win.stack.addWidget(win.tree_pane)      # index 2

    middle = HairlineSplitter(Qt.Vertical, win)
    middle.addWidget(win.pipeline)
    # 下半在 `_build_preview_pane` 跑完之後才接得起來（儀表是在那裡建的）
    # —— 見 `_build_params_row`。
    win.canvas_column = middle

    # 「為什麼還不能跑」的常駐清單（U2）—— **整個視窗最下面一條，橫跨三欄**
    # （見下面 `setCentralWidget` 那一段）。它不在任何一個 splitter 裡：
    # 它是使用者在畫布上找不到路時唯一的答案，而一個拖得掉的東西答不到
    # 那件事。
    win.problems = ProblemsBar(win)
    win.problems.problem_activated.connect(win._on_problem_activated)
    # 「Connect ＿」（F124）：走跟手拉的線同一條路。
    from . import canvas_edges
    win.problems.connect_requested.connect(
        lambda dst, srcs: canvas_edges.connect_into(win, dst, srcs))
    # **開窗時沒有選任何卡片，所以設定區是收起來的**（F13-1）。
    # 以前它一律攤開，於是畫面最大的一塊（中欄下半，1600×1000 上量到
    # 551px 高）裝的是一行灰字「(Pick a card from the library…)」——
    # 一塊叫人去別的地方點東西的空白，而它同時把畫布壓到 50% 縮放，
    # 卡片的副標（「這張卡吃什麼吐什麼」）當場讀不出來。
    # F100：那個狀態現在住在 `WorkbenchLayout.open`（工作台攤開著嗎）——
    # 而 Tune 模式開窗就是攤開的，因為影像住在工作台裡。
    # 比例在 showEvent 才真的套 —— setSizes 要有實際高度才算得出來
    #（isVisible 之前那些數字沒有意義，docs/PITFALLS.md 的老坑）。
    win._layout_ratio_applied = False
    # 右：單顆預覽（F7-5：Gallery 與直方圖搬到 Results 視窗，
    #     主視窗只留「編流程 + 看單顆」，影像因此拿得到整欄高度）
    win.preview_pane = build_preview_pane(win)
    # 參數 ＋ 儀表同欄同框（U8）。要在 preview pane 之後 —— 儀表那幾個
    # widget 是在那一支裡建的。
    middle.addWidget(build_params_row(win))
    middle.setStretchFactor(0, 2)
    middle.setStretchFactor(1, 3)
    # 版面模式的狀態與幾何（F100）—— 邏輯在 `ui/workbench.py`，這裡只接。
    # 主欄 = 畫布/工作台那根 splitter（F100 v2：Verdict 列搬進右欄影像下面）。
    win.main_column = middle

    # Results 視窗（跑完才 show；先建好讓 histogram / gallery 一直有實體，
    # 這樣所有既有接線與測試都不用管它現在開著沒有）
    win.results = ResultsWindow(win)
    win.histogram = win.results.histogram
    win.gallery = win.results.gallery
    win.results.rerun_requested.connect(win.rerun)
    win.results.write_requested.connect(win.write_outputs)
    win.results.class_selected.connect(win._on_verdict_class)

    # 右欄：影像在上、儀表在下（F100 v3），一根直向 splitter，比例記得住。
    win.right_column = HairlineSplitter(Qt.Vertical, win)
    win.right_column.addWidget(win.preview_pane)
    win.right_column.addWidget(win.gauge_pane)
    win.right_column.setStretchFactor(0, 3)
    win.right_column.setStretchFactor(1, 2)
    win.right_column.setCollapsible(0, False)
    root = HairlineSplitter(Qt.Horizontal, win)
    root.addWidget(win.library)
    root.addWidget(win.main_column)
    root.addWidget(win.right_column)
    root.setStretchFactor(0, 0)
    root.setStretchFactor(1, 3)
    root.setStretchFactor(2, 2)
    root.setCollapsible(1, False)
    # 出廠欄寬；上一次關窗的欄寬由 `WorkbenchLayout`（F100 v2）在 showEvent
    # 套（只記 Tune 的：Build 的右欄是 0，不是使用者調出來的）。
    root.setSizes(list(COLUMN_SIZES))
    # 版面模式的狀態與幾何（F100）—— 邏輯在 `ui/workbench.py`，這裡只接。
    # ⚠ 在函式裡 import：那兩支讀寫 QSettings，而且要問 `_running_under_pytest()`
    # （測試不准寫進使用者真正的設定 —— `CLAUDE.md` §4 F91），所以它們的家留在
    # `studio.py`；模組層 import 會繞回來。
    from .studio import _load_sizes, _save_sizes

    win.layout_modes = WorkbenchLayout(
        middle, win.params_row, win.pipeline, win.library,
        root=root, preview_index=2, right=win.right_column,
        load=_load_sizes, save=_save_sizes)
    win.top_splitter = root
    win.root_splitter = root

    # Problems 列住在**三欄的下面、狀態列的上面**（U2）—— 橫跨整個視窗。
    #
    # ⚠ 位置換過兩次，而兩次都是**現有的不變量把它推到這裡**：
    #   1. 包在畫布外面 → `canvas_column.widget(0)` 不再是畫布
    #      （`canvas.py::_build_header` 的說明就寫著誰靠著它，
    #      `test_ui_f8_ui_polish` 當場紅）；
    #   2. 包住整個中欄 → `root_splitter` 的三個子項不再是
    #      `[library, canvas_column, preview_pane]`
    #      （`test_ui_results::test_main_window_keeps_only_the_editing_surface`）。
    # 包 central widget 誰都不礙著 —— 而且**這一塊本來就是視窗層級的答案**
    # （「這份 pipeline 現在能不能跑」不是中欄自己的事）。
    host = QWidget(win)
    hl = QVBoxLayout(host)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)
    hl.addWidget(root, 1)
    hl.addWidget(win.problems)
    win.setCentralWidget(host)


def build_score_pane(win: "StudioWindow") -> QWidget:
    """判定段那一欄 —— 內容全部住在 `DecidePanel`（F22-UI）。

    為什麼搬出去：這一欄現在有兩種樣子（一個門檻／一串規則），而規則那一種
    是逐列生出來的。留在 `studio.py`（已經 5000 多行）的話，這一欄會是這個
    檔案裡最長的一段，而它跟視窗的其他部分沒有任何共用的東西。
    """
    win.decide_panel = DecidePanel(win)
    win.decide_panel.set_model(win.model)
    win.decide_panel.mode_changed.connect(win._on_decide_mode)
    win.decide_panel.decision_requested.connect(win.add_decision)
    # 分流的編輯區塊（F23 期2）—— 判定欄**上方**：它在跑之前就決定每一顆
    # 走哪條 route，判定是跑完之後的事，由上往下讀正好是時間順序。
    from .route_panel import RouteByBox

    win.route_box = RouteByBox(win)
    win.route_box.set_model(win.model)
    # ⚠ **建出來再藏，不是不建**（同 `btn_examples` 那一顆）：版面量測、
    # 既有測試、`_refresh_*` 都還指得到它，回復只要改一個字串。
    #
    # ⚠ 而且**它跟畫布上的徽章要同進同出**（`scope.SHOW_ROUTE_BY`）。
    # 只藏徽章的話，使用者仍然編得出一份會分流的 recipe，而畫布上一個字
    # 都不會說 —— 那正是這個 repo 一直在消滅的「畫布說謊」。
    win.route_box.setVisible(bool(scope.SHOW_ROUTE_BY))
    pane = QWidget(win)
    lay = QVBoxLayout(pane)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(win.route_box)
    lay.addWidget(win.decide_panel, 1)
    return pane


def build_params_row(win: "StudioWindow") -> QWidget:
    """中欄的下半：**參數在左、這張卡的儀表在右，同一個框裡**（U8）。

    為什麼它們必須挨著
    ------------------
    調參數的迴圈是「改一個數字 → 看那個數字怎麼變」。儀表以前住在右欄
    下半，中間隔著整張影像 —— 每改一格眼睛就要橫跨半個螢幕來回一趟，而那
    件事在一個 1366×768 的螢幕上尤其貴。

    **卡名與階段色只出現一次**：ParamForm 自己的標頭就是那一次，儀表這一
    邊只留 Card / Features 兩顆切換鈕。兩邊各畫一次的話，同一張卡的名字在
    同一個框裡出現兩遍，而使用者要花一秒鐘確認那是不是兩張卡。

    影像**不搬**：它是另一種迴圈（改參數 → 看圖），而且它要的是高度 ——
    把它擠進這一列只會讓兩件事都變小。
    """
    row = HairlineSplitter(Qt.Horizontal, win)
    row.addWidget(win.stack)
    # F100 v3：儀表搬到**右欄影像下面**（使用者：「最一開始的排版最好，儀表
    # 換到影像下方」）。設定區於是拿到整個中欄的寬度，儀表拿到右欄的寬度
    # ——兩個要寬的東西各一整欄，只有影像付出高度。「儀表挨著參數」（U8）
    # 沒有破：中欄下半與右欄下半左右相鄰，同一條視線。
    win.workbench = row
    # 參數那一邊寬一點：它裝的是一排排可以拖的滑桿（F7-8），而儀表是
    # 讀的東西。3:2 是量出來的 —— 再窄一點，`Borrow range from` 那種
    # 兩行的 label 會開始折行。
    row.setStretchFactor(0, 3)
    row.setStretchFactor(1, 2)
    row.setCollapsible(0, False)
    win.params_row = row
    return row


def build_preview_pane(win: "StudioWindow") -> QWidget:
    pane = QWidget(win)
    lay = QVBoxLayout(pane)
    # 間距走 8px 節奏（F8-UI）：這一欄以前是 2/4/6px 各處自己挑，
    # 排在一起就是「差一點對齊」—— 比完全沒對齊更讓人覺得亂。
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(8)
    # 這一欄叫什麼（F13-4）—— 四個直欄以前只靠 splitter 隔開，
    # 沒有任何東西說得出「這一欄是什麼」。它自己不帶左右內距，
    # 靠這一欄的 8px 邊界對齊（那個節奏是 F8-UI 定的，不要為了一個
    # 地標破壞它）。
    lay.addWidget(column_header("Preview", pane))

    nav = QHBoxLayout()
    nav.setSpacing(8)
    win.btn_prev = IconButton("prev", "Previous defect", pane, kind="icon")
    win.btn_next = IconButton("next", "Next defect", pane, kind="icon")
    win.defect_combo = QComboBox(pane)
    win.defect_combo.setToolTip("Jump straight to a defect")
    win.defect_label = QLabel("(no dataset loaded)", pane)
    win.defect_label.setObjectName("paramHint")
    # 下拉框**不吃 stretch**。它裝的是一個 defect id，而以前它拿了
    # ``stretch 1``，於是在寬螢幕上是一個 800px 寬、裡面寫著「1」的框，
    # 而真正有資訊的那句（``ebi_patch · defect 1 / 24``）被擠到最右邊。
    # 空間給誰，就是在說什麼比較重要。
    win.defect_combo.setMaximumWidth(DEFECT_COMBO_MAX)
    win.defect_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    nav.addWidget(win.btn_prev)
    nav.addWidget(win.btn_next)
    nav.addWidget(win.defect_combo)
    nav.addWidget(win.defect_label, 1)
    lay.addLayout(nav)

    srow = QHBoxLayout()
    srow.setSpacing(8)
    lbl_stream = QLabel("Image stream", pane)
    lbl_stream.setObjectName("paramLabel")
    win.stream_combo = QComboBox(pane)
    win.stream_combo.setToolTip(
        "Which image stream to look at (test / ref / diff / snr_map …)")
    # 同上：影像流的名字是 ``test`` / ``ref`` / ``diff`` / ``snr_map``，
    # 最長也就那樣，不需要整列。
    win.stream_combo.setMaximumWidth(STREAM_COMBO_MAX)
    srow.addWidget(lbl_stream)
    srow.addWidget(win.stream_combo)

    # 並排比對（F7-8）—— 預設關著，見 _set_compare 的說明
    win.compare_check = QCheckBox("Compare", pane)
    win.compare_check.setToolTip(
        "Show a second image stream side by side, with linked zoom and pan "
        "— useful when tuning Enhance cards, to check test and ref still "
        "match")
    win.stream_combo_b = QComboBox(pane)
    win.stream_combo_b.setToolTip("The stream shown on the right")
    win.stream_combo_b.setVisible(False)
    win.stream_combo_b.setMaximumWidth(STREAM_COMBO_MAX)
    srow.addWidget(win.compare_check)
    srow.addWidget(win.stream_combo_b)
    srow.addStretch(1)
    # 游標讀數有自己的位置（M7）。以前它是寫進狀態列的，於是滑鼠只要飄過
    # 影像，剛才那句「Trial run finished: …」就被 x/y/gray 洗掉了 ——
    # 狀態列該留給「使用者要讀的事件」，一直在刷的東西不該跟它搶同一格。
    win.cursor_label = QLabel("", pane)
    win.cursor_label.setObjectName("paramHint")
    # F100：這一列住在工作台的一格裡（1366 上約 420 px），150 的保留寬度
    # 是那一格硬最小寬度的最大來源之一。讀數最長是「x 1234, y 1234 · 255」，
    # 100 夠；不夠的那一瞬間它會被擠成省略號，而不是把整個視窗撐寬。
    win.cursor_label.setMinimumWidth(100)
    win.cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    win.cursor_label.setToolTip("Cursor position and gray level")
    srow.addWidget(win.cursor_label)
    lay.addLayout(srow)

    win.image_view = ImageView(pane)
    win.image_view_b = ImageView(pane)
    win.image_view_b.setVisible(False)
    images = QWidget(pane)
    irow = QHBoxLayout(images)
    irow.setContentsMargins(0, 0, 0, 0)
    irow.setSpacing(8)
    irow.addWidget(win.image_view, 1)
    irow.addWidget(win.image_view_b, 1)

    # 還沒載資料時，畫面上最大的一塊是**一片黑**，角落有一行極小的
    # 「(no dataset loaded)」（F7-15）。首啟導覽關掉之後就沒有任何東西告訴
    # 使用者下一步要做什麼 —— 而「下一步」只有兩個，就把那兩個放在這裡。
    # F100：影像現在是工作台的一格（1366 上約 480 px 寬、380 px 高），而這
    # 一塊空白狀態是四列「鈕 ＋ 一句話」—— 塞不下的時候要**捲**，不是疊在
    # 一起（第一版就是疊的）。用 `fit_screen.scrolled` 在**建構時**包，
    # 事後搬是 segfault（`CLAUDE.md` §4）。捲軸還有第二個好處：
    # `QStackedWidget` 的最小寬度是它每一頁的最大值——**藏起來的那一頁也
    # 算**——而以前這一頁的 468 px 就是右欄硬最小寬度的來源。
    win.empty_state_host, win.empty_state = fit_screen.scrolled(pane)
    estack = QVBoxLayout(win.empty_state)
    estack.addStretch(1)
    title = QLabel("No data loaded yet", win.empty_state)
    title.setObjectName("paramTitle")
    title.setAlignment(Qt.AlignCenter)
    estack.addWidget(title)
    # 這句話要跟旁邊實際看得到的鈕一致 —— 範例資料那顆收起來的時候還講
    # 「or try the tool with generated sample data」，使用者會去找一顆不在
    # 畫面上的鈕。
    why = QLabel("d4t reads four kinds of data. Pick the one you have."
                 if not scope.SHOW_SAMPLE_DATA else
                 "d4t reads four kinds of data. Pick the one you have, "
                 "or try the tool with generated sample data first.",
                 win.empty_state)
    why.setObjectName("paramHint")
    why.setAlignment(Qt.AlignCenter)
    why.setWordWrap(True)
    # 留一個名字：這句話必須跟旁邊看得到的鈕一致，而那是測得出來的
    # （`test_nothing_on_screen_points_at_a_button_that_is_not_there`）。
    win.empty_state_hint = why
    estack.addWidget(why)

    # **每一種 source 一列，而那幾列是從 `scope.INPUT_SOURCES` 長出來的**
    # （F11 Input-5，使用者：「各種 image source 資料流是否改成個別入口比較
    # 好（但同時 UI 一開始進去的地方顯示也要改）」）。
    #
    # 以前這裡只有一顆 ``Open KLARF…``，而工具列上有三顆 —— 於是帶著一個
    # 資料夾的圖片、或一個多頁 TIFF 進來的人，在**整個畫面最大的那一塊**上
    # 看到的是「Open a KLARF to see your patches here」。他要嘛以為 d4t
    # 讀不了他的東西，要嘛得自己去工具列上一顆一顆讀過去。
    #
    # 一列一句話，說的是**這條路吃什麼樣的檔案**，不是它會做什麼 ——
    # 使用者站在這個畫面前面時，手上已經有檔案了，他要回答的問題是
    # 「我這一堆算哪一種」。
    win.empty_source_buttons: Dict[str, QPushButton] = {}
    rows = QVBoxLayout()
    rows.setSpacing(6)
    for i, src in enumerate(scope.INPUT_SOURCES):
        row = QHBoxLayout()
        row.setSpacing(10)
        # ⚠ **不再把兩側撐開**（F117 H3）。這一欄在 1366 上只有 509 px 寬，而
        # 兩邊各留一份彈簧等於把 159 px 讓給空白 —— 說明因此從兩行變三行，
        # 三列一起多出 70 px 高，而那一塊在 768 高的螢幕上本來就要捲。
        # 整塊由外層置中，一列裡面不需要再置中一次。
        b = QPushButton(src.title, win.empty_state)
        if i == 0:
            b.setObjectName("primary")     # 最常見的那一條是主要動作
        b.setMinimumWidth(140)
        b.clicked.connect(
            partial(open_dialogs.open_source, win, src.key))
        win.empty_source_buttons[src.key] = b
        row.addWidget(b)
        # **一句話，全文在 tooltip**（F117 H3）。那三段說明各有 115～169 個
        # 字，在這一欄（200 px）折成 7～9 行、整塊 128～154 px 高 —— 而 1366×768
        # 上這一塊看得到的只有 **160 px**，所以**三列全部被切掉**（走查只看到
        # 第三列被切，實際上第一列從第 160 px 起就沒了）。
        #
        # ⚠ 使用者站在這個畫面前面時手上已經有檔案了，他要回答的是「我這一堆
        # 算哪一種」—— 那是一句話答得完的問題。細節（副檔名、要不要 KLARF）
        # 留給 tooltip 與開檔對話框。
        full = (src.what if src.has_klarf else
                "%s No KLARF, so no write-back." % src.what)
        what = QLabel(wording.headline(full), win.empty_state)
        what.setObjectName("paramHint")
        what.setWordWrap(True)
        what.setMinimumWidth(200)
        what.setToolTip(full)
        row.addWidget(what, 1)
        rows.addLayout(row)
    estack.addLayout(rows)

    # 第一顆保留原本的名字：既有測試與 ``_build_shortcuts``（Ctrl+O）
    # 都指得到它，而它做的事一個字都沒變。
    win.btn_empty_open = win.empty_source_buttons[
        scope.INPUT_SOURCES[0].key]

    # 附加檔不是第五條路，所以它不是一顆鈕，是**一句說明它什麼時候才出現**
    # 的話。這正是使用者問的那一句「Load layout labels 要怎麼 load，好像
    # 沒有 load 的地方」—— 卡片在卡片庫裡看得到，而它的入口要等 lot 載進來
    # 才亮，於是這個畫面上必須說得出那個順序。
    att_bits = ["%s — %s %s" % (a.title, a.what, a.needs)
                for a in scope.ATTACHMENTS]
    win.empty_state_attachments = QLabel(
        "  ·  ".join(att_bits), win.empty_state)
    win.empty_state_attachments.setObjectName("paramHint")
    win.empty_state_attachments.setAlignment(Qt.AlignCenter)
    win.empty_state_attachments.setWordWrap(True)
    win.empty_state_attachments.setVisible(bool(scope.ATTACHMENTS))
    estack.addSpacing(6)
    estack.addWidget(win.empty_state_attachments)

    brow = QHBoxLayout()
    brow.addStretch(1)
    win.btn_empty_sample = QPushButton("Try it with sample data",
                                        win.empty_state)
    win.btn_empty_sample.setProperty("variant", "secondary")
    # ⚠ **這顆跟 `btn_examples` 看的不是同一個旗標了**（F91 X4）：
    # demo 產得出資料，但**不載 pipeline** —— 按完看到的是一批資料配一張
    # 空白畫布。範本庫那個理由修好了，這個沒有。
    win.btn_empty_sample.setVisible(bool(scope.SHOW_SAMPLE_DATA))
    brow.addWidget(win.btn_empty_sample)
    brow.addStretch(1)
    estack.addSpacing(8)
    estack.addLayout(brow)
    estack.addStretch(1)

    win.image_stack = QStackedWidget(pane)
    win.image_stack.addWidget(win.empty_state_host)  # index 0
    win.image_stack.addWidget(images)                # index 1
    lay.addWidget(win.image_stack, 3)

    # 模板定位卡的入口在**參數列裡**（F7-13），不在這裡。它是那個參數的值
    # 從哪來，不是一個預覽動作 —— 放在影像下方等於把「這個欄位怎麼填」的
    # 答案擺到半個螢幕外，而欄位本身看起來只是「還沒填」。

    # 「這個區域在整批上都對嗎」（F7-11）。跟曲線面板一樣平常收起來，
    # 只有選到會定義區域的卡片時才出現。
    win.btn_region_check = QPushButton("Check this region across defects…",
                                        pane)
    win.btn_region_check.setProperty("variant", "secondary")
    win.btn_region_check.setToolTip(
        "Draw this region on many defects at once. A setting that looks "
        "right on defect 1 can be completely off on defect 50 — the "
        "structure sits in a different place on every patch.")
    win.btn_region_check.setVisible(False)
    lay.addWidget(win.btn_region_check)

    # 投影曲線面板（F7-11）。**平常收起來** —— 它只有在編輯投影定位卡的
    # 時候才有意義，常駐會把好不容易爭取到的影像高度又吃掉一塊。
    # 投影曲線面板搬進卡片儀表（F7-17）：它本來就是「這張卡自己的儀表」，
    # 只是 F7-11 當時直接掛在這裡，變成一條跟儀表機制平行的路。兩條並存的
    # 下場是加新面板的人不知道走哪一條，然後兩邊各長一半。

    # 右下角那一塊：**選哪張卡就換成那張卡的儀表**（F7-17）。
    # 原本固定是一張「特徵 / 數值」表 —— 問題不是它佔位子，是那些數字沒有
    # 辦法判讀（`glv_snr 11.170` 是大還是小？），而且使用者在問的
    # 問題**每張卡都不一樣**。特徵表仍然留著，用切換列回去。
    # F76 刀 4：這一塊從 `widgets.FeatureTable`（一條平的清單）換成
    # `feature_panel.FeaturePanel`（卡 › 區域 分段、四胞胎橫過來）。
    # 名字仍叫 `feature_panel`，取用口跟舊的那張表同名同義。
    win.feature_panel = FeaturePanel(win)
    win.feature_panel.setMinimumHeight(120)
    # **滑過一段數字＝在畫布上指出算它的那張卡**（F117 I6）。用的是
    # `reveal_cards`（hover 那一套），不是 `select_card` —— 選取會把右邊的設定
    # 整個換掉，而使用者現在只是在看數字，他要的是眼睛找到來源。
    #
    # ⚠ **接 `partial` 不接一個新的 `StudioWindow` 方法**：那一格的方法數是
    # `HARD_CAPS`（只准往下）。內容本來就住在 `cross_links`，而在那裡也比較
    # 好測 —— 測試直接叫那一支，不必先開一個視窗。
    win.feature_panel.card_hovered.connect(
        partial(cross_links.hover_card, win))

    win.inspector_host = QWidget(win)
    ihost = QVBoxLayout(win.inspector_host)
    ihost.setContentsMargins(0, 0, 0, 0)
    ihost.setSpacing(2)
    win.inspector_summary = QLabel("", win.inspector_host)
    win.inspector_summary.setObjectName("paramHint")
    win.inspector_summary.setWordWrap(True)
    win.inspector_slot = QVBoxLayout()
    win.inspector_slot.setContentsMargins(0, 0, 0, 0)
    ihost.addLayout(win.inspector_slot, 1)
    ihost.addWidget(win.inspector_summary)

    win.bottom_stack = QStackedWidget(win)
    win.bottom_stack.addWidget(win.inspector_host)      # index 0
    win.bottom_stack.addWidget(win.feature_panel)       # index 1

    # ---- 儀表搬到參數旁邊（U8，2026-09-08）--------------------------
    #
    # 這一塊（Card 儀表 / Features）以前住在**右欄下半**，而參數住在
    # 中欄下半 —— 中間隔著整張影像。調參數的迴圈是「改一個數字 → 看那個
    # 數字怎麼變」，而那兩件事每一次都要橫跨半個螢幕，眼睛來回一趟。
    #
    # 現在它跟參數同欄同框（見 `_build_params_row`）。**影像維持獨立**：
    # 它是另一種迴圈（改參數 → 看圖），而且它需要的是高度。
    win.gauge_pane = QWidget(win)
    glay = QVBoxLayout(win.gauge_pane)
    glay.setContentsMargins(0, 0, 0, 0)
    glay.setSpacing(2)
    tabs = QHBoxLayout()
    tabs.setContentsMargins(0, 0, 0, 0)
    tabs.setSpacing(4)
    win.btn_tab_card = small_button("Card", parent=win.gauge_pane,
                                     shape="wide")
    win.btn_tab_features = small_button("Features", parent=win.gauge_pane,
                                         shape="wide")
    for i, b in enumerate((win.btn_tab_card, win.btn_tab_features)):
        b.setCheckable(True)
        b.clicked.connect(
            lambda _c=False, k=i: win.gauges.show_bottom_page(k))
        tabs.addWidget(b)
    # 選到判定樹的一步時，這一塊裝的還是**上一張卡**的儀表（F99 P1-7）——
    # 以前畫面上沒有任何東西講這件事，左邊寫著 Decision、右邊寫著 GLV。
    # 現在它淡掉，而且這一句說出它是誰的。
    win.gauge_note = QLabel("", win.gauge_pane)
    win.gauge_note.setObjectName("paramHint")
    tabs.addWidget(win.gauge_note, 1)
    glay.addLayout(tabs)
    glay.addWidget(win.bottom_stack, 1)

    # ---- 判定那一塊（F76 刀 5，2026-09-02）----------------------------
    #
    # **沒有判定就不畫它。** 使用者 2026-09-02：「大部分人應該建立
    # Pipeline 時 ADC 不會放到第一個」—— 而在那段時間裡，這一塊永遠是一個
    # 寫著 `—` 的 chip 加一片空白。它不是壞的，它是**什麼都沒說**，而那塊
    # 面積正好是量測卡最需要的地方（同 F7-15「空白狀態要說得出下一步」、
    # 以及 scope.SHOW_SAMPLE_DATA 那條「按了撞牆的鈕比沒有那顆鈕更糟」
    # 的鏡像 —— 這裡是「說不出話的那一格比沒有那一格更佔位」）。
    # Verdict 是一條**常駐的結論列**（F100）：橫跨在工作台下面，不在任何
    # splitter 裡，所以 Build 模式收掉工作台之後它還在。
    win.verdict_strip = QWidget(win)
    strip = QVBoxLayout(win.verdict_strip)
    strip.setContentsMargins(8, 4, 8, 4)
    strip.setSpacing(0)
    win.verdict_live = QWidget(win.verdict_strip)
    # **兩行，不是一行**（F100 v2）：這一塊住在右欄（1366 上約 460 px），
    # 一行排「Verdict ＋ 膠囊 ＋ score ＋ 那句為什麼 ＋ 路徑」的最小寬度是
    # 五百多 px，整欄被它撐開。膠囊（類別名）跟 Verdict 一行、數字與說明
    # 第二行、路徑第三行（會換行）。
    vcol = QVBoxLayout(win.verdict_live)
    vcol.setContentsMargins(0, 0, 0, 0)
    vcol.setSpacing(2)
    vrow = QHBoxLayout()
    vrow.setContentsMargins(0, 0, 0, 0)
    vrow.setSpacing(8)
    win.verdict = VerdictChip(win.verdict_live)
    # 「Class」（F122 期 3）：以前叫「Verdict」—— 同一件事的第五個名字。膠囊上
    # 寫的就是這一顆落在哪一類（樹上那片葉子的名字）＋ bin。
    vrow.addWidget(QLabel("Class", win.verdict_live))
    vrow.addWidget(win.verdict)
    vrow.addStretch(1)
    vcol.addLayout(vrow)
    vrow2 = QHBoxLayout()
    vrow2.setContentsMargins(0, 0, 0, 0)
    vrow2.setSpacing(8)
    # **score 那個數字跟 bin 一起常駐**（F76 刀 4 之後）。以前它是特徵表
    # 最後一列、粗體、永遠不被收合走的那一格 —— 理由是「它是這張表的
    # 結論」。新面板把它歸進 `Decision` 那一段，而那一段收得起來，
    # 所以那條不變量搬到這裡：結論跟判定在同一塊，永遠看得到。
    win.verdict_score = QLabel("", win.verdict_live)
    win.verdict_score.setStyleSheet("font-weight:700;")
    vrow2.addWidget(win.verdict_score)
    # **膠囊寫著「—」的時候要說為什麼**（F99 P1-2）。預覽停在選到的那張卡
    # 是對的（F7 定調），但那一刻 Verdict 從「more than one box is off」
    # 變成一個破折號，而畫面上沒有任何東西講它為什麼不見 —— 看起來像剛剛
    # 還有判定、現在壞了。這一句住在膠囊旁邊，不住在狀態列。
    win.verdict_note = QLabel("", win.verdict_live)
    win.verdict_note.setObjectName("paramHint")
    win.verdict_note.setWordWrap(True)
    # ⚠ **「按 Esc」是對的，但沒有人想得到**（F117 D1）。Esc 在這個畫面的
    # 意思是「放掉手上的東西」（U18），而「放掉選取 ⇒ 預覽跑到底」是一條要
    # 先知道前提才推得出來的因果 —— 一句正確而想不到的提示，等於沒有提示。
    #
    # **做成連結而不是另加一顆鈕** —— 跟底下 `decide_path` 同一個先例
    # （U11）：底線本來就是「這個字可以點」的意思，而多一顆鈕要多一個
    # `StudioWindow` 的屬性（那一格只准往下）。
    win.verdict_note.setTextFormat(Qt.RichText)
    win.verdict_note.setOpenExternalLinks(False)
    win.verdict_note.linkActivated.connect(
        lambda _href: win._clear_canvas_selection())
    win.verdict_note.setToolTip(
        "Let go of the selected card so the preview runs the whole pipeline, "
        "decision included. Esc does the same thing.")
    vrow2.addWidget(win.verdict_note, 1)
    vcol.addLayout(vrow2)
    # **那一行點得下去**（U11）：走過的路旁邊沒有別的入口，而回溯以前只有
    # 「跑一整批 → Results → 點 score/bin」那一條路 —— 使用者手上明明就有
    # 這一顆的每一個數字。做成連結而不是另加一顆鈕：底線本來就是
    # 「這個字可以點」的意思。
    win.decide_path = QLabel("", win.verdict_live)
    win.decide_path.setObjectName("paramHint")
    win.decide_path.setWordWrap(True)      # 右欄裝不下一整條路徑
    win.decide_path.setTextFormat(Qt.RichText)
    win.decide_path.setOpenExternalLinks(False)
    win.decide_path.linkActivated.connect(
        lambda _href: win.toggle_preview_why())
    vcol.addWidget(win.decide_path)
    strip.addWidget(win.verdict_live)

    # 這一顆為什麼判成這樣（U11）—— **跟 Results 那一份是同一個 widget**
    # （`why_panel.WhyPanel`），只是住在單顆預覽這一欄。跑整批之前它就答得
    # 出來，因為 `verdict_trace` 吃的是特徵、不是一批結果。
    #
    # ⚠ 高度有上限：它是回答一個問題的東西，不是這一欄的主角 ——
    # 把影像擠掉的話，使用者為了讀它得先關掉它。
    win.why_preview = WhyPanel(pane)
    win.why_preview.setMaximumHeight(220)
    win.why_preview.hide()
    win.why_preview.item_activated.connect(
        lambda name: win.gallery_ctl._on_why_item(win.why_preview.defect_id(),
                                                  str(name)))
    lay.addWidget(win.why_preview)
    # Verdict 列住在影像下面（F100 v2）：這一顆判成什麼，跟這一顆的圖挨著。
    lay.addWidget(win.verdict_strip)

    # 還沒有判定的時候換成**一句可以照做的話 ＋ 那顆鈕**（推廣鐵則：
    # 講得出下一步，而那一步就在旁邊）。
    win.verdict_empty = QWidget(win.verdict_strip)
    erow = QHBoxLayout(win.verdict_empty)
    erow.setContentsMargins(0, 0, 0, 0)
    erow.setSpacing(8)
    hint = QLabel("No decision yet — these numbers are measured, but "
                  "nothing is drawing a conclusion from them.",
                  win.verdict_empty)
    hint.setObjectName("paramHint")
    hint.setWordWrap(True)
    erow.addWidget(hint, 1)
    win.btn_add_decision = QPushButton("Add a decision…",
                                        win.verdict_empty)
    win.btn_add_decision.setProperty("variant", "secondary")
    win.btn_add_decision.clicked.connect(win.show_score_page)
    erow.addWidget(win.btn_add_decision)
    strip.addWidget(win.verdict_empty)
    win._sync_verdict_block()

    return pane
