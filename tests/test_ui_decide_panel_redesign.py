# 判定面板的重排（草案 1–6，2026-08-24）— 每一條都對著一張截圖。
"""這一份鎖住的是**「在挑門檻，就要看得到分布」**那一輪改掉的東西。

改動的來源不是讀程式碼，是把 Studio 開起來、載 24 顆、接線、試跑，
再把判定段的每一個狀態截下來 —— 而截圖裡看到的每一個問題都在這裡有一條。

⚠ 這一份**不驗美感**，驗的是可以斷言的性質：

* 該出現的元件在有資料時出現、沒資料時**不出現**（F18：不顯示 0）；
* 同一個事實不要在一個面板裡講三次；
* 控制項不可以橫向溢位那一欄（溢位＝把控制項藏在捲軸後面）；
* 建議出來的問題**切得開**流到這一步的顆。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QScrollArea,
)

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import TreeLeaf, TreeStep  # noqa: E402
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.threshold_view import SplitBar, ThresholdHistogram  # noqa: E402
from d4t.ui.tree_panel import TreePanel  # noqa: E402
from d4t.ui.tree_scene import OPS, decision_info  # noqa: E402
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _rows(n=24, spread=True):
    """一批假的試跑結果 —— `glv_max` 從 30 鋪到 30+n。"""
    return [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {"glv_max": float(30 + (i if spread else 0)),
                          "glv_mad": float(i % 5)}}
            for i in range(n)]


def _feed(p, m, rows):
    """照 Studio 餵的那一套餵（`studio._sync_tree_pane` → `decision_info`）。

    ⚠ **顆數是外面算好餵進來的，面板不自己數。** 畫布與面板吃的是同一份
    `flow_counts`，抄第二份出來的那份會漂 —— 而漂掉的時候畫面上兩個數字
    會對不起來，沒有人知道哪一個是對的。測試也走同一條路，否則它驗的是
    一個真實情況下不存在的面板。
    """
    p.set_rows(rows)
    p.set_counts(decision_info(getattr(m, "decide", None), rows)["counts"]
                 if rows else None)


@pytest.fixture()
def panel(qapp):
    """一個編到第一步的面板，帶著 24 顆的試跑結果。"""
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True)
    m.ensure_tree()
    m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel()
    p.resize(431, 551)
    p.set_model(m)
    _feed(p, m, _rows())
    p.set_features(["glv_max", "glv_mad"])
    p.show_path("")
    return p


# --------------------------------------------------------------------------- #
# 草案 1：分布圖
# --------------------------------------------------------------------------- #
def _find(widget, cls):
    """``findChildren`` 一次只吃一個型別 —— tuple 要自己攤開。"""
    if isinstance(cls, tuple):
        out = []
        for one in cls:
            out.extend(widget.findChildren(one))
        return out
    return widget.findChildren(cls)


def _shown(widgets):
    """會出現在畫面上的那些（**不是** ``isVisible()``）。

    ⚠ 這一條差別會讓一整批測試安靜地變成空的：一個從來沒有 ``show()`` 過的
    面板，它底下每一個子元件的 ``isVisible()`` 都是 ``False`` —— 於是
    「有沒有畫出分布」跟「沒資料時不要畫」**兩條都通過**，而其中一條根本
    沒有在驗任何東西。``isHidden()`` 問的才是我們要的那件事：
    **有沒有人明講要藏起來**（`setVisible(False)`）。
    """
    return [w for w in widgets if not w.isHidden()]


def test_the_threshold_shows_up_on_a_distribution(panel):
    """有試跑資料時，門檻要畫在**這一步流到的顆**的分布上。

    以前這裡是一根沒有刻度的滑桿 —— 使用者拖的時候不知道自己在 60 還是 200，
    唯一的回饋是上面那個數字框。而這個專案的 Gray level 面板早就在畫分布了
    （F18），真正在挑門檻的地方反而沒有。
    """
    plots = _shown(_find(panel, ThresholdHistogram))
    assert plots, "有 24 顆資料，卻沒有畫出分布"
    span = plots[0].span()
    assert span is not None and span[0] < span[1]


def test_no_distribution_is_drawn_when_there_is_nothing_to_draw(qapp):
    """沒跑過就**不要畫一張空圖**（F18：不顯示 0）。

    一張沒有資料的分布圖看起來跟「這批真的什麼都沒有」一模一樣 ——
    而那兩件事要使用者分得出來。
    """
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True)
    m.ensure_tree()
    m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel()
    p.resize(431, 551)
    p.set_model(m)
    p.set_rows([])                     # ← 還沒試跑
    p.set_features(["glv_max"])
    p.show_path("")

    assert not _shown(_find(p, ThresholdHistogram))


def test_a_threshold_outside_the_batch_widens_the_axis_instead_of_being_clamped():
    """「大於 12」在這批最大只有 9 的時候仍然是一條**完全合法**的規則。

    那正是怎麼寫一條今天抓不到、明天出事才抓得到的規則（`_slider_range`
    的說明講過同一件事）。所以圖的橫軸跟著撐開，不是把門檻夾回來 ——
    夾回來等於把那種規則變成打不出來的東西。
    """
    plot = ThresholdHistogram()
    plot.set_data([1.0, 2.0, 3.0], threshold=99.0)
    lo, hi = plot.span()
    assert hi >= 99.0, (lo, hi)

    plot.set_data([1.0, 2.0, 3.0], threshold=-99.0)
    lo, hi = plot.span()
    assert lo <= -99.0, (lo, hi)


def test_dragging_the_plot_reports_a_value_inside_the_axis(qapp):
    plot = ThresholdHistogram()
    plot.resize(200, 64)
    plot.set_data([10.0, 20.0, 30.0], threshold=20.0)
    got = []
    plot.threshold_changed.connect(got.append)
    plot._emit_at(100.0)               # 正中間
    assert got, "拖了門檻卻沒有發出新的值"
    lo, hi = plot.span()
    assert lo <= got[0] <= hi


# --------------------------------------------------------------------------- #
# 草案 2：一條分流條取代兩句重複的話
# --------------------------------------------------------------------------- #
def test_the_split_is_shown_once_not_three_times(panel):
    """「幾顆說 yes」以前在一個 550px 的面板裡出現**三次**：
    滑桿底下一行、100px 之後的 THIS BATCH 一行、而顆數本身又沒有在
    Yes／No 那兩列上。現在：麵包屑說「幾顆流到這裡」、分流條說「切成幾比幾」、
    Yes／No 的標籤各自帶自己那一邊的數字 —— 三個位置，三件不同的事。
    """
    bars = _shown(_find(panel, SplitBar))
    assert len(bars) == 1
    yes, no = bars[0].counts()
    assert yes + no == 24
    assert yes > 0 and no > 0, "這一刀應該切得開（%d/%d）" % (yes, no)

    texts = _panel_texts(panel)
    assert not [t for t in texts if "arrive here" in t], (
        "THIS BATCH 那一段還在 —— 它講的每一件事都已經有更好的位置了")
    assert not [t for t in texts if "of the" in t and "say yes" in t], (
        "滑桿底下那一句還在")


def test_an_empty_split_bar_draws_nothing(qapp):
    bar = SplitBar()
    bar.set_counts(0, 0)
    assert not bar.isVisible()
    bar.set_counts(3, 1)
    assert bar.isVisible()


# --------------------------------------------------------------------------- #
# 草案 3：我在樹的哪裡
# --------------------------------------------------------------------------- #
def _panel_texts(panel):
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in _find(panel, QLabel) if w.text()]


def test_the_panel_says_where_in_the_tree_you_are(panel):
    """樹深了以後右欄長得一模一樣，只有裡面的數字不同。"""
    crumb = [t for t in _panel_texts(panel) if t.startswith("Decision tree")]
    assert crumb, _panel_texts(panel)
    assert "step 1" in crumb[0]
    assert "24 defects reach here" in crumb[0]


def test_a_deeper_step_says_which_side_it_is_on(panel):
    """第二步要講出它掛在上一步的哪一邊 —— 那是「我在哪裡」的另一半。"""
    m = panel._model
    m.split_tree_leaf("n")
    m.set_tree_when("n", "glv_mad > 2")
    panel.show_path("n")
    crumb = [t for t in _panel_texts(panel) if t.startswith("Decision tree")]
    assert crumb, _panel_texts(panel)
    assert "step 2" in crumb[0]
    assert "no side" in crumb[0] and "glv_max > 42" in crumb[0]


# --------------------------------------------------------------------------- #
# 草案 5：Yes／No 兩邊帶顆數
# --------------------------------------------------------------------------- #
def test_both_branches_carry_their_own_count(panel):
    tags = [t for t in _panel_texts(panel)
            if t.startswith("Yes ") or t.startswith("No ")]
    assert len(tags) == 2, tags
    assert all(t.split()[-1].isdigit() for t in tags), tags


def test_the_branches_do_not_carry_counts_before_a_trial(qapp):
    """沒跑過就不寫數字（F18）—— ``Yes 0`` 比 ``Yes`` 更糟。"""
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True); m.ensure_tree(); m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel(); p.resize(431, 551)
    p.set_model(m); p.set_rows([]); p.set_features(["glv_max"]); p.show_path("")
    tags = [t for t in _panel_texts(p)
            if t.strip() in ("Yes", "No") or t.startswith(("Yes ", "No "))]
    assert tags and all(t.strip() in ("Yes", "No") for t in tags), tags


# --------------------------------------------------------------------------- #
# 草案 6：用詞
# --------------------------------------------------------------------------- #
def test_the_jargon_is_gone(panel):
    """``Split`` 對寫過 decision tree 的人是一秒，對製程工程師是一個要猜的動詞。"""
    from PySide6.QtWidgets import QAbstractButton
    labels = [b.text() for b in _find(panel, QAbstractButton) if b.text()]
    assert not [t for t in labels if t.strip() == "Split"], labels
    assert [t for t in labels if "Ask another question" in t], labels


@pytest.mark.parametrize("symbol, text", OPS)
def test_every_operator_word_fits_the_dropdown(qapp, symbol, text):
    """六個運算子的差別**正好在容易被截掉的那幾個字**。

    以前是 ``is greater than`` 那一組，在 118px 的下拉裡被截成
    ``is greater tha…`` —— 而 greater than 跟 greater than or equal
    的差別就在那裡。
    """
    box = QComboBox()
    box.setFixedWidth(118)
    box.addItem(text, symbol)
    # 下拉的箭頭大約吃掉 22px，剩下的要放得下字。
    assert box.fontMetrics().horizontalAdvance(text) <= 118 - 26, text


# --------------------------------------------------------------------------- #
# 建議出來的問題要**切得開**
# --------------------------------------------------------------------------- #
def test_a_suggestion_for_a_new_step_splits_the_defects_that_reach_it(panel):
    """**這一條是一個真的 bug 的迴歸測試。**

    一個剛加進來的步驟 ``when`` 是空的，而 `_path_of` 走到它就會炸
    （`parse_expression("")`）—— 那一顆因此整條路都不算，於是
    `rows_reaching` 回空的、`suggest_question` 退回整批，而整批算出來的建議
    正好就是**上一步已經問過的那一個**。

    實測（修之前）：第一步 `glv_max > 67`，第二步建議一模一樣的
    `glv_max > 67`，切出來 **0 yes / 13 no** —— 一個切不開的問題。
    """
    m = panel._model
    m.split_tree_leaf("n")
    panel.show_path("n")
    assert panel.suggest_question("n") is True

    node = m.tree_node("n")
    assert isinstance(node, TreeStep) and node.when.strip()
    assert node.when != m.tree_node("").when, (
        "第二步建議了跟第一步一模一樣的問題 —— 它切不開任何東西")

    panel.show_path("n")
    bars = _shown(_find(panel, SplitBar))
    assert bars, "第二步沒有分流條"
    yes, no = bars[0].counts()
    assert yes > 0 and no > 0, "建議出來的問題切不開（%d yes / %d no）" % (yes, no)


# --------------------------------------------------------------------------- #
# 版面：不可以橫向溢位
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("width", [431, 380])
def test_nothing_spills_out_of_the_column(qapp, width):
    """控制項溢位那一欄 = 把它藏在橫向捲軸後面。

    這一條是**我自己踩的**：草案 6 把 ``Split`` 換成
    ``Ask another question`` 之後，那一列在 431px 裡放不下，於是數字框整個
    跑到畫面外。修法是把分支拆成兩行 —— 面板底下本來就有 300 多 px 是空的，
    **高度是免費的、寬度不是**。

    380px 那一組是保險：廠內機器多半是 1366×768，那一欄只會更窄。

    ⚠ **量的是「需不需要橫向捲軸」，不是「每個控制項的右邊在哪」。**
    第一版量的是後者，而它抓不到東西 —— 面板裡是一個 `QScrollArea`：
    內容比欄寬多 5px 的時候，控制項的右邊仍然在欄裡，多出來的 5px 變成
    一根捲軸。**而那根捲軸正是要擋的東西**（把控制項推到看不見的地方
    是它，不是右邊那幾個 px）。
    """
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True); m.ensure_tree(); m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel()
    p.resize(width, 600)
    p.set_model(m); _feed(p, m, _rows())
    p.set_features(["glv_max", "glv_mad"])
    p.show_path("")
    p.show()
    qapp.processEvents()

    scroll = p.findChild(QScrollArea)
    need = scroll.widget().minimumSizeHint().width()
    have = scroll.viewport().width()
    bar = scroll.horizontalScrollBar()
    over = [w for w in _find(p, (QLineEdit, QComboBox, QAbstractSpinBox))
            if not w.isHidden() and w.mapTo(p, w.rect().topRight()).x() > width]
    p.hide()
    assert not bar.isVisible() and need <= have, (
        "欄寬 %d：內容最少要 %dpx，可用 %dpx（超出的控制項：%s）"
        % (width, need, have, [type(w).__name__ for w in over] or "都還在欄裡"))


# --------------------------------------------------------------------------- #
# 重建不可以留下孤兒（我自己踩的第二個）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rows", [24, 0])
def test_rebuilding_the_panel_does_not_pile_up_widgets(qapp, rows):
    """**改一格就整段重建**的面板，重建 40 次之後元件數不可以多 40 個。

    `clear_layout_parked` 清的是**版面裡**的東西。所以一個
    ``QWidget(self)`` 生出來、卻沒有 ``addWidget`` 進去的元件，就永遠掛在
    面板上 —— 而這個面板每動一格就重建一次，拖一次門檻是幾十次。

    這一條是草案 1 自己種的：分布圖無條件生出來、只在有資料時進版面，
    於是**沒有資料的那條路每重建一次就漏一個**（實測 34 次重建 = 34 個）。
    兩組參數都要：有資料走的是進版面那條路，沒資料走的才是漏的那條。
    """
    from PySide6.QtWidgets import QWidget

    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True); m.ensure_tree(); m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel(); p.resize(431, 551)
    p.set_model(m)
    _feed(p, m, _rows() if rows else [])
    p.set_features(["glv_max", "glv_mad"])
    p.show_path("")
    qapp.processEvents()

    before = len(p.findChildren(QWidget))
    for _ in range(40):
        p.refresh(force=True)
        qapp.processEvents()
    after = len(p.findChildren(QWidget))
    assert after <= before, "重建 40 次多出 %d 個元件" % (after - before)


@pytest.mark.parametrize("rows", [0, 24])
def test_the_threshold_box_is_wide_enough_for_what_it_shows(qapp, rows):
    """框裡的數字**要看得完**。

    還沒試跑的時候沒有分布 → 小數位只能給到最寬的那一檔（4 位），於是
    ``42.0000`` 把 84px 的框整個塞滿，看起來像被切掉一半。

    ⚠ **不能反過來砍小數位**：砍掉等於 ``0.0001`` 這種門檻打不進去，而那
    正是使用者回報的那個 bug（「搖桿只能填最大 1」）的形狀 —— 一個為了版面
    把值變成打不出來的決定。所以讓框變寬，不是讓值變粗。
    """
    m = RecipeModel.starter("ebi_patch")
    m.use_decide(True); m.ensure_tree(); m.split_tree_leaf("")
    m.set_tree_when("", "glv_max > 42")
    p = TreePanel(); p.resize(431, 551)
    p.set_model(m)
    _feed(p, m, _rows() if rows else [])
    p.set_features(["glv_max"])
    p.show_path("")

    from PySide6.QtWidgets import (QDoubleSpinBox, QStyle,
                                   QStyleOptionSpinBox)
    p.show()
    qapp.processEvents()
    spin = _shown(_find(p, QDoubleSpinBox))[0]
    text = spin.textFromValue(spin.value())
    need = spin.fontMetrics().horizontalAdvance(text)
    # ⚠ **量的是樣式算出來的文字區，不是「框寬減一個猜出來的數」。**
    # 第一版猜「箭頭 18 ＋ 內距 8」＝ 26px，於是 84px 的框看起來有 58px 可用
    # —— 而實際的文字區只有 53px，比 ``42.0000`` 的 54px 少 1px。那一版
    # 測試把**正在畫錯的那個版面**判成通過。
    opt = QStyleOptionSpinBox()
    spin.initStyleOption(opt)
    field = spin.style().subControlRect(QStyle.CC_SpinBox, opt,
                                        QStyle.SC_SpinBoxEditField, spin)
    p.hide()
    assert need <= field.width(), (
        "%r 要 %dpx，框裡的文字區只有 %dpx" % (text, need, field.width()))


# --------------------------------------------------------------------------- #
# ③ ADC 那一頁的圖示與空狀態（2026-09-01）
#
# 使用者：「ADC 的設定頁面是不是也加入一些 icon 會比較好（目前的如果沒設定好
# 空）」。**icon 與空狀態是兩件事**，這一段兩件都守。
# --------------------------------------------------------------------------- #
def test_the_scale_row_is_chips_not_a_dropdown(qapp):
    """「這個數字要怎麼用」是三把尺 —— 卡片設定區早就用膠囊在問這種問題。"""
    from d4t.ui.decide_panel import SCALES, DecidePanel
    from d4t.ui.widgets import ChoiceChips

    m = RecipeModel()
    m.use_decide(True)
    m.add_let()
    p = DecidePanel()
    p.set_model(m)
    p.refresh(force=True)

    chips = p.findChildren(ChoiceChips)
    assert len(chips) == 1, "每一行 working number 一排膠囊"
    got = chips[0]
    assert [c.mid for c in got._chips] == [v for v, _l, _g, _h in SCALES]
    # **空字串是「照原值」的真值，不是「沒填」** —— 它必須勾得起來
    assert got.chip("").is_checked(), "預設那一顆要亮著"
    assert got.chip("").label == "As measured"


def test_picking_a_scale_chip_writes_the_same_value_the_dropdown_wrote(qapp):
    """換掉的只有長相：recipe 存的字一模一樣。"""
    from d4t.ui.decide_panel import DecidePanel
    from d4t.ui.widgets import ChoiceChips

    m = RecipeModel()
    m.use_decide(True)
    m.add_let()
    p = DecidePanel()
    p.set_model(m)
    p.refresh(force=True)
    p.findChildren(ChoiceChips)[0].chip("z").click()
    assert str(getattr(m.decide.let[0], "scale", "")) == "z"


def test_every_operator_has_its_own_picture(qapp):
    """六個運算子的差別是「箭頭往哪、含不含等於」—— 六個英文詞要讀完才分得出。

    ⚠ 這一條同時擋住**漏掉一個**：`OPS` 多一個運算子而 `OP_ICONS` 沒跟上，
    那一項會退回 `cmp_eq` 的圖 —— 一張**說錯話**的圖比沒有圖更糟。
    """
    from d4t.ui.tree_panel import OP_ICONS
    from d4t.ui.widgets import GLYPH_ICONS

    for sym, _text in OPS:
        assert sym in OP_ICONS, sym
        assert OP_ICONS[sym] in GLYPH_ICONS, (sym, OP_ICONS[sym])
    assert len(set(OP_ICONS.values())) == len(OP_ICONS), "六個要各長各的"


def test_the_empty_decision_page_teaches_instead_of_being_blank(qapp):
    """使用者：「目前的如果沒設定好空。」

    ⚠ **不准在這裡列「幾種判定方式」**：二元門檻那個編輯器 2026-08-24 整個
    拿掉了（使用者：「UI 完全拿掉」），判定就是一棵樹 —— 列出不存在的選擇比
    沒有說明更糟。所以這裡只驗「有沒有把那一顆鈕會做的事講出來」。
    """
    from PySide6.QtWidgets import QLabel

    from d4t.ui.decide_panel import _EMPTY_STEPS, DecidePanel

    p = DecidePanel()
    p.set_model(RecipeModel())          # 沒有判定的新 recipe
    p.refresh(force=True)

    said = " ".join(w.text() for w in p.findChildren(QLabel) if w.text())
    for _icon, line in _EMPTY_STEPS:
        assert line in said, line
    assert len(_EMPTY_STEPS) == 3
    # 每一句都配一張真的畫得出來的圖
    from d4t.ui.widgets import GLYPH_ICONS
    for icon, _line in _EMPTY_STEPS:
        assert icon in GLYPH_ICONS, icon


def test_a_number_from_a_region_carries_that_region_colour(qapp):
    """同一塊區域在三個畫面上是同一個顏色：影像上的框、Feature 表的上標、
    判定段下拉的那一點。"""
    import d4t.core.steps  # noqa: F401
    from d4t.ui.widgets import region_dot_icon

    m = RecipeModel()
    load = m.add_step("load_patch")
    roi = m.add_step("roi_reference")
    m.set_param(roi, "method", "stripes in the image")
    m.set_param(roi, "roi_out", "epi")
    m.add_edge(load, roi, "test", "source")
    glv = m.add_step("glv_stats")
    m.add_edge(load, glv, "test", "source")
    m.add_edge(roi, glv, "epi", "roi")

    regions = m.feature_regions()
    assert regions, "接了區域的 recipe 至少要有一個帶區域的數字"
    assert all(i >= 0 for i in regions.values())
    assert not region_dot_icon(list(regions.values())[0]).isNull()
