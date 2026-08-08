# F7-24 驗收：版面把空間給對的東西，工具列不要七顆一模一樣的白鈕。
"""這一支問的是**版面與層次**，不是某個功能對不對。

來源是一張實際跑起來的截圖：六張卡擠在畫布左下角、上面一大片空白；兩個下拉框
各佔了八百多 px 去裝「1」與「diff」，而真正有資訊的那句被擠到最右邊；工具列
七顆白鈕貼在白條上。三件事都不會讓任何測試變紅 —— 它們是「畫面把空間與注意力
分配錯了」，所以只能直接量版面。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE_RECIPE = (Path(__file__).resolve().parent.parent
                  / "examples" / "recipes" / "die_to_die_basic.json")


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod, widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app
    theme_mod.apply_theme(app, "light")


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1600, 900)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 畫布開起來就擺好
# --------------------------------------------------------------------------- #
def test_a_whole_recipe_is_placed_where_you_can_see_it(window, qapp):
    """開一份 recipe，卡片要在畫面裡，不是在角落等人去找。

    以前載入之後卡片擠在左下角、上面一大片空白，而使用者的第一個動作永遠是
    自己去按「全部看得完」——「回到看得完」那顆鈕該是滾亂了的時候用的，
    不是每次開檔的儀式。
    """
    assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    qapp.processEvents()

    view = window.pipeline
    visible = view.mapToScene(view.viewport().rect()).boundingRect()
    content = view._scene.itemsBoundingRect()
    assert content.isValid() and content.width() > 0

    # 問的是「**擺正**了沒有」，不是「一格不漏地全在畫面裡」——``fit`` 有
    # ``MIN_FIT_SCALE`` 的下限（不縮到看不懂），所以一條很長的 pipeline 本來就
    # 會有一點溢出。壞掉的樣子是「內容縮在角落、旁邊一大片空白」，那在數字上
    # 就是兩個中心差很遠。
    dx = abs(visible.center().x() - content.center().x())
    dy = abs(visible.center().y() - content.center().y())
    assert dx <= content.width() * 0.1 and dy <= max(content.height(), 120) * 0.2, \
        "內容沒有擺在畫面中央：可視中心 %s vs 內容中心 %s" \
        % (visible.center(), content.center())


def test_fit_shrinks_but_never_blows_up(window, qapp):
    """``fit`` 是「全部看得完」，不是「放到最大」。

    ``fitInView`` 會把內容撐滿 viewport —— 一條只有兩張卡的 pipeline 因此會被
    放大成三倍，卡片變成巨無霸。要夾住上限，否則「自動 fit」對小 pipeline
    反而是幫倒忙。
    """
    view = window.pipeline
    view.fit()
    qapp.processEvents()
    assert view.zoom_percent() <= 100, \
        "fit 把畫面放大到 %d%%" % view.zoom_percent()
    # 下限那一頭本來就有（MIN_FIT_SCALE），順手一起鎖
    assert view.zoom_percent() >= int(round(view.MIN_FIT_SCALE * 100))


# --------------------------------------------------------------------------- #
# 2. 空間給有資訊的那一邊
# --------------------------------------------------------------------------- #
def test_the_short_dropdowns_do_not_swallow_the_row(window, qapp):
    """裝一個 defect id 的框，不該比整列的一半還寬。

    以前那兩個下拉都吃 ``stretch 1``，於是在寬螢幕上各自變成八百多 px、裡面
    只寫著「1」或「diff」的框，而 ``ebi_patch · defect 1 / 24`` 被擠到最右邊。
    空間給誰，就是在說什麼比較重要。
    """
    qapp.processEvents()
    pane_w = window.preview_pane.width()
    assert pane_w > 400, "這條測試要在夠寬的視窗上跑才有意義（實得 %d）" % pane_w

    for name, w in (("defect", window.defect_combo),
                    ("stream", window.stream_combo)):
        assert w.width() <= pane_w * 0.5, \
            "%s 下拉佔了 %d / %d px" % (name, w.width(), pane_w)

    # 而且那句話拿得到位子（以前它被推到最右邊、還被切掉）
    assert window.defect_label.width() > window.defect_combo.width() * 0.5


# --------------------------------------------------------------------------- #
# 3. 死掉的那個面板
# --------------------------------------------------------------------------- #
def test_the_replaced_pipeline_panel_is_gone(qapp):
    """``PipelinePanel`` 是 M3 的直式節點清單，F7-6 的畫布整個取代了它。

    之後 ``studio.py`` 只剩一行 import、從來沒有實例化過。留著的代價不是那
    240 行，是**每一輪主題工作都要繞過它** —— F7-23 第三輪把元件的 stylesheet
    搬進 QSS 時，``nodeCard`` / ``scoreCard`` 被判成「顏色依 category 算出來、
    該留在 widget」而放過。那個判斷沒錯，錯的是它們根本不在畫面上。
    """
    import ast
    import pathlib

    assert not hasattr(widgets_mod, "PipelinePanel")

    ui = pathlib.Path(__file__).resolve().parent.parent / "adept" / "ui"
    hits = []
    for py in sorted(ui.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Name) and node.id == "PipelinePanel":
                hits.append("%s:%d" % (py.name, node.lineno))
    assert not hits, "還有地方在用它：%s" % hits


# --------------------------------------------------------------------------- #
# 4. 工具列的層次與辨識度
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_the_toolbar_is_not_the_same_colour_as_its_buttons(qapp, theme_name):
    """七顆白鈕貼在白條上 —— 那就是使用者說的「單調」。

    單調的來源不是缺顏色，是**缺層次**：以前 ``toolbar`` 與 ``bg_surface``
    都是 ``#ffffff``，那一排按鈕只靠一條 1px 的淺灰邊框跟背景分開。
    暗色盤本來就沒有這個問題，所以這條兩個主題都要問。
    """
    pal = theme_mod.PALETTES[theme_name]
    assert pal["toolbar"] != pal["bg_surface"], \
        "%s：工具列與按鈕同色（%s）" % (theme_name, pal["toolbar"])


def test_each_toolbar_button_has_its_own_silhouette(window):
    """五顆同樣寬、同樣灰、只有字不一樣的按鈕，要讀完才知道哪顆是自己要的。

    圖示給每一顆一個輪廓 —— 這是對「單調」的正解，而不是替它們各上一個顏色
    （這個主題的規則是**顏色只表達語意**，見 theme.py 的 docstring）。
    """
    buttons = (window.btn_open_klarf, window.btn_open_recipe,
               window.btn_save_recipe, window.btn_examples, window.btn_export)
    names = [b.glyph_name() for b in buttons]
    assert all(names), "這些工具列按鈕沒有圖示：%s" % names
    assert len(set(names)) == len(names), "圖示重複了：%s" % names
    # 有圖示就要有位子放 —— 否則圖示會疊在文字上
    for b in buttons:
        assert b.property("hasGlyph") == "true", b.text()


def test_the_two_actions_worth_pressing_are_the_two_with_colour(window, qapp):
    """整條工具列只有兩顆有顏色，而它們正好是使用者真正要按的那兩顆。

    ``Run trial`` 是填滿的 accent（主要動作），``Export…`` 是 accent 外框
    （跑完之後要做的那件事）。其餘是中性的 —— 顏色在這個主題裡表達語意，
    不是拿來讓畫面熱鬧的。
    """
    assert window.btn_trial.objectName() == "primary"
    assert window.btn_export.property("variant") == "secondary"
    plain = (window.btn_open_klarf, window.btn_open_recipe,
             window.btn_save_recipe, window.btn_examples, window.btn_help)
    for b in plain:
        assert b.objectName() != "primary"
        assert b.property("variant") is None, b.text()


# --------------------------------------------------------------------------- #
# 5. 儀表要說得出自己畫的是什麼（同 §28.6 的第一件）
# --------------------------------------------------------------------------- #
def _paint(widget, w=520, h=340):
    """把 widget 畫出來，回傳 QImage（自繪面板的 bug 只在 paintEvent 才浮出來）。"""
    from PySide6.QtGui import QColor, QPixmap

    widget.resize(w, h)
    pm = QPixmap(widget.size())
    pm.fill(QColor("#808080"))
    widget.render(pm)
    return pm.toImage()


def _spread_with_data(qapp):
    from adept.ui import inspectors as insp

    panel = insp.MeasureInspector()
    batch = [{"features": {"glv_mean": 40.0 + i, "glv_max": 200.0 + 2 * i}}
             for i in range(24)]
    panel.set_context("glv", params={}, result={"features": {"glv_mean": 52.0,
                                                            "glv_max": 231.0}},
                      batch=batch, feature_names=["glv_mean", "glv_max"])
    return panel


def _diff(a, b):
    """兩張圖有多少格不一樣。"""
    return sum(1 for x in range(a.width()) for y in range(a.height())
               if a.pixelColor(x, y) != b.pixelColor(x, y))


def test_the_spread_panel_says_what_its_axis_is(qapp):
    """三排長條、右邊一個數字、中間一條紅線 —— 而畫面上沒有一個地方說得出
    橫軸從哪到哪、紅線是什麼、右邊那個數字又是誰的。

    F7-21 幫 Enhance 的直方圖補了軸與圖例，這個量測卡儀表沒跟上 —— 同一種東西
    兩套做法，兩邊各長一半（正是 F7-23 第三輪在清的那種）。

    測法：**把那段程式關掉，畫面要真的變**。第一版是「數某個 token 顏色的畫素
    夠不夠多」，結果對著改之前的程式也通過 —— 抗鋸齒的字邊本來就會經過那個
    顏色附近。量顏色之前要先確定那個顏色只有你要找的東西會畫。
    """
    from adept.ui import inspectors as insp

    panel = _spread_with_data(qapp)
    assert panel.has_data() is True
    full = _paint(panel)

    # (1) 兩端的刻度：把「一排要多高才畫刻度」調到不可能達到
    keep = insp.MeasureInspector.AXIS_MIN_ROW_H
    try:
        insp.MeasureInspector.AXIS_MIN_ROW_H = 10 ** 6
        without_axis = _paint(panel)
    finally:
        insp.MeasureInspector.AXIS_MIN_ROW_H = keep
    assert _diff(full, without_axis) > 60, "關掉刻度之後畫面沒有變 —— 它沒有真的畫"

    # (2) 圖例：同一招
    keep = insp.MeasureInspector.LEGEND_H
    try:
        insp.MeasureInspector.LEGEND_H = 10 ** 6
        without_legend = _paint(panel)
    finally:
        insp.MeasureInspector.LEGEND_H = keep
    assert _diff(full, without_legend) > 60, "關掉圖例之後畫面沒有變"


def test_the_spread_panel_degrades_instead_of_squashing(qapp):
    """面板拖矮的時候，長條比刻度與圖例重要 —— 兩者都要讓位，不是擠成一團。"""
    panel = _spread_with_data(qapp)
    tall = _paint(panel, 520, 340)
    short = _paint(panel, 520, 120)        # 最小高度
    assert short.height() == 120           # 畫得出來、不炸
    assert _diff(tall, short) > 0
    assert panel.summary()


# --------------------------------------------------------------------------- #
# 6. 往回走的線不要橫掃整張畫布（§28.6 的第二件）
# --------------------------------------------------------------------------- #
def test_an_edge_that_runs_backwards_stays_near_its_two_ends(window, qapp):
    """換行的那條線（上一列最後一張 → 下一列第一張）本來就得往回走。

    以前它跟往前走的線共用同一條式子：控制點水平推 ``|Δx| * 0.5``，而往回走時
    Δx 是一整列的寬度 —— 於是一條連兩張卡的線橫掃七百多 px，還甩到比第一張卡
    更左邊。三列就三條這種折線橫過整張畫布，比它要表達的「順序」還搶眼。
    """
    assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    qapp.processEvents()

    view = window.pipeline
    backwards = []
    for edge in view._edges:
        a = edge.src.out_port(edge.port)
        b = edge.dst.in_port()
        if b.x() >= a.x():
            continue
        box = edge.path().boundingRect()
        over_left = a.x() and (min(a.x(), b.x()) - box.left())
        over_right = box.right() - max(a.x(), b.x())
        backwards.append((edge.pair(), over_left, over_right))

    assert backwards, "這份 recipe 應該至少有一條往回走的線（換行）"
    reach = view._edges[0].BACK_REACH
    bad = [(pair, l, r) for pair, l, r in backwards
           if l > reach + 2 or r > reach + 2]
    assert not bad, \
        "這些往回走的線甩得太遠（允許 %.0f px）：%s" % (reach, bad)
