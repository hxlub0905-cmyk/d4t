# F87：圖的視窗（`ui/uniformity_window`）＋ 設定編輯器（`ui/chart_settings`）。
"""鎖的都是不變量：

* 視窗畫的 SVG **就是**會寫出去的那一份（同一支 `build_chart_svg`、
  同一支 `_style_for`）；
* 編輯器 round-trip 是 identity（鐵則 9 的 UI 側）；
* 上下界只有一份（`chart_style.bounds`），UI 不自己抄；
* 沒顯示的每張圖覆寫不准被安靜地清掉。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QDoubleSpinBox, QLineEdit, QSpinBox,
)

from d4t.ui.widgets import ChoiceChips  # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.core.export import uniformity_charts as uc  # noqa: E402
from d4t.core.pipeline import chart_style as cs  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.ui import chart_settings  # noqa: E402
from d4t.ui import studio as studio_mod  # noqa: E402
from d4t.ui import theme as theme_mod  # noqa: E402
from d4t.ui.chart_settings import (  # noqa: E402
    BoolChips, ChartSettingsDialog, ColourButton,
)
from d4t.ui.uniformity_window import UniformityWindow, fit_into  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _series(n=24, metric="glv_mean"):
    vals = [112.0 + i * 2.4 for i in range(n)]
    notes = [{"region": "cells", "prefix": "cells", "spread": {
        "stats": {metric: vals},
        "cx": [float(40 + 70 * (i % 6)) for i in range(n)],
        "cy": [float(40 + 70 * (i // 6)) for i in range(n)],
        "rects": [[40 + 70 * (i % 6), 40 + 70 * (i // 6), 40, 40]
                  for i in range(n)],
        "boxes": list(range(n))}}]
    return uc.chart_series(notes, metric)


# --------------------------------------------------------------------------- #
# 視窗
# --------------------------------------------------------------------------- #
def test_the_window_draws_exactly_what_gets_written(qapp):
    """**畫面上那一張就是檔案裡那一張** —— 一個位元組都不差。

    這是 F85 計畫書風險表的第一行（「兩份繪圖程式碼會漂」）。收成一份之後，
    這一條問的是它**真的還是一份**：視窗那一格產的字串，跟卡片走
    `_style_for` 產的字串比對。
    """
    win = UniformityWindow()
    win.set_context(_series(), look='{"tick_size":15}', metric="glv_mean")
    card = get_step("output_uniformity")
    p = card.validate_params({"folder": "/tmp/x", "look": '{"tick_size":15}',
                              "metric": "glv_mean"})
    for kind, view in win.views.items():
        view.resize(view.MIN_W, view.MIN_H)
        want = uc.build_chart_svg(_series(), kind,
                                  card()._style_for(kind, p, "glv_mean"),
                                  width=view.MIN_W, height=view.MIN_H)
        assert view.svg() == want, kind


def test_the_window_only_shows_the_ticked_charts(qapp):
    win = UniformityWindow()
    win.set_context(_series(), kinds=["box", "map"], metric="glv_mean")
    assert sorted(win.views) == ["box", "map"]
    win.set_context(_series(), kinds=list(uc.CHARTS), metric="glv_mean")
    assert sorted(win.views) == sorted(uc.CHARTS)


def test_the_window_says_when_there_is_nothing_to_plot(qapp):
    """空白視窗本身不是訊息（同儀表的 `empty_reason`）。"""
    win = UniformityWindow()
    win.set_context({"groups": [], "metric": "", "metrics": []})
    assert "Nothing to plot" in win.head.text()


def test_a_chart_is_never_stretched_out_of_shape(qapp):
    """``QSvgRenderer.render(p, rect)`` 會把 viewBox 拉滿 —— 一張被橫向
    拉扁的散佈圖讀起來是另一組資料。"""
    box = QRectF(0, 0, 400, 100)

    class _S:
        def width(self):
            return 300.0

        def height(self):
            return 200.0

    got = fit_into(_S(), box)
    assert abs(got.width() / got.height() - 1.5) < 1e-6
    assert got.height() <= box.height() + 1e-6
    assert abs(got.center().x() - box.center().x()) < 1e-6


def test_a_broken_size_does_not_take_the_window_down(qapp):
    """鐵則 7 的 UI 版 —— 圖畫不出來不准毀掉視窗。"""
    win = UniformityWindow()
    win.set_context(_series(), metric="glv_mean")
    for w, h in ((40, 30), (1, 1), (900, 600)):
        for view in win.views.values():
            view.resize(w, h)
            assert view.svg()


# --------------------------------------------------------------------------- #
# 編輯器
# --------------------------------------------------------------------------- #
def test_the_editor_round_trips(qapp):
    """開起來、什麼都不動、按 OK —— **一個字都不准變**（鐵則 9 的 UI 側）。

    這是最容易壞的那一條：任何一格的預設值在 UI 與 core 之間漂掉，
    這個對話框就會在使用者「只是看了一下」之後偷偷改掉 recipe。
    """
    for look in ('', '{"tick_size":14,"tick_bold":true}',
                 '{"box.title":"EPI","lock":true,"lo":10,"hi":90}',
                 '{"line_color":"#ff8800","percent":true,"profile.xticks":9}'):
        dlg = ChartSettingsDialog(look, list(uc.CHARTS))
        assert dlg.value() == cs.format_style(cs.parse_style(look)), look


def test_the_editor_keeps_overrides_for_charts_it_is_not_showing(qapp):
    """把熱圖取消勾選之後再來調設定 —— 熱圖的標題不准被安靜地清掉。"""
    look = '{"map.title":"Where","box.title":"Spread"}'
    dlg = ChartSettingsDialog(look, ["box"])
    assert "map.title" in dlg.value()
    dlg.per["box"]["title"].setText("Spread 2")
    got = cs.parse_style(dlg.value())
    assert got["map.title"] == "Where" and got["box.title"] == "Spread 2"


def test_reset_says_what_it_does(qapp):
    """鈕上寫的是「全部回預設」—— 收起來的覆寫也一起（不然那是半句實話）。"""
    dlg = ChartSettingsDialog('{"map.title":"Where","tick_size":18}', ["box"])
    dlg.reset()
    assert dlg.value() == ""


def test_every_setting_has_a_home_on_the_page(qapp):
    """**每一格都要編得到。** 少一格的下場是它只能靠手改 JSON ——
    而目標使用者不會寫 code（推廣鐵則）。"""
    dlg = ChartSettingsDialog("", list(uc.CHARTS))
    assert set(dlg.globals) == set(cs.GLOBAL_KEYS)
    for kind in uc.CHARTS:
        # 每張圖只放**用得到的**那幾格（`PER_CHART_APPLIES`）—— 盒鬚圖的 X 軸
        # 是類別，「橫著幾個刻度」在那裡沒有意思，攤在那裡只是讓人猜。
        assert set(dlg.per[kind]) == set(uc.PER_CHART_APPLIES[kind])
    # 而**每一格至少有一張圖用得到**（不然那是一格沒有家的設定）
    covered = set().union(*(set(v) for v in uc.PER_CHART_APPLIES.values()))
    assert covered == set(cs.PER_CHART_KEYS)


def test_the_bounds_come_from_core_not_from_a_copy(qapp):
    """上下界只有一份（`chart_style.bounds`）。

    抄一份的那天，使用者打得進一個滑桿拉不到的值 —— 或反過來，拉得到一個
    存不進去的值，而錯誤訊息會出現在按下 OK 之後。
    """
    dlg = ChartSettingsDialog("", ["box"])
    for key, w in dlg.globals.items():
        got = cs.bounds(key)
        if got is None:
            assert not isinstance(w, (QSpinBox, QDoubleSpinBox)), key
            continue
        lo, hi = got
        assert abs(w.minimum() - lo) < 1e-6, key
        assert abs(w.maximum() - hi) < 1e-6, key


def test_the_editors_match_the_kind_of_value(qapp):
    """bool → 打勾、顏色 → 色塊、文字 → 輸入框、數字 → 數字框。

    型別對不上不會炸，它會**安靜地存錯東西**（一個 QLineEdit 存出來的
    ``"True"`` 不是 ``true``）。
    """
    from d4t.ui.chart_settings import BoolChips

    dlg = ChartSettingsDialog("", ["box"])
    for key, w in dlg.globals.items():
        default = cs.DEFAULTS[key]
        if key.endswith("_color"):
            assert isinstance(w, ColourButton), key
        elif isinstance(default, bool):
            # F87 第十刀：獨立成一列的開關改成**一排兩顆膠囊**（`BoolChips`）。
            # 它長得像 QCheckBox（isChecked / setChecked / toggled），所以
            # 對話框其餘部分不必分兩種寫法。
            #
            # ⚠ **例外只有那兩個粗體旗標**，而且名字寫死在這裡：它們是
            # 「Tick values：大小｜粗體｜顏色」那一列裡的**一個屬性**，不是
            # 一個「要哪一種長相」的問題 —— 那一列的標題已經說了它是什麼，
            # 而兩顆膠囊塞進三欄的格子會把整排的對齊撐爛。
            # 寫死名字是刻意的：新加一個 bool 不會安靜地混進這張表。
            if key in ("tick_bold", "axis_bold"):
                assert isinstance(w, QCheckBox), key
            else:
                assert isinstance(w, BoolChips), key
        elif key in chart_settings.CHOICE_CHIPS:
            # 三顆以上的那幾格（`slot_order`）—— `BoolChips` 只裝得下兩顆。
            assert isinstance(w, ChoiceChips), key
        elif key in chart_settings.CHIP_VALUES:
            # 值是字串、而它只有**兩種**（`ramp` 是單色階／彩虹）——
            # 一個兩選一的東西做成文字框等於要使用者去記那兩個字。
            # `CHIP_VALUES` 是那條例外的唯一出處（見它的說明）。
            assert isinstance(w, BoolChips), key
        elif isinstance(default, str):
            assert isinstance(w, QLineEdit), key
        else:
            assert isinstance(w, (QSpinBox, QDoubleSpinBox)), key


def test_a_colour_goes_back_to_auto(qapp):
    """顏色的預設是**自動**（跟著區域色走），而回到自動要**看得見** ——
    藏在右鍵裡的功能對不會寫 code 的人等於不存在。"""
    dlg = ChartSettingsDialog('{"point_color":"#ff0000"}', ["box"])
    btn = dlg.globals["point_color"]
    assert btn.value() == "#ff0000" and btn.clear_btn.isEnabled()
    btn.clear_btn.click()
    assert btn.value() == "" and not btn.clear_btn.isEnabled()
    assert dlg.value() == "", "回到自動就等於預設，那一格不該再留在 recipe 裡"


def test_the_per_chart_tick_count_can_say_follow_the_others(qapp):
    """每張圖的刻度數要能說「跟大家一樣」—— 一個看起來像 1 的數字答不出
    「這是沒設定，還是真的設成 1」。"""
    dlg = ChartSettingsDialog("", ["box"])
    w = dlg.per["box"]["yticks"]
    assert w.value() == w.minimum()
    assert w.specialValueText()
    assert dlg.value() == ""
    w.setValue(9)
    assert cs.parse_style(dlg.value())["box.yticks"] == 9


def test_a_broken_style_string_opens_on_the_defaults(qapp):
    """recipe 那一格壞掉（手改壞了）也要開得起來 —— 開不起來的對話框
    等於把使用者鎖在外面（鐵則 7 的 UI 版）。"""
    dlg = ChartSettingsDialog("{not json", list(uc.CHARTS))
    assert dlg.value() == ""


def test_the_settings_reach_all_four_charts(qapp):
    """**字級不能只對四張裡的兩張有效。**

    盒鬚圖走 `boxplot.build_boxplot_svg`、熱圖以前寫死 10px —— 兩條不同的
    路，而「只有兩張跟著變」是使用者會以為自己按錯的那種 bug。
    """
    from d4t.ui.chart_settings import SAMPLE_SPEC, _sample_frame

    s = _series()
    # ⚠ 散佈圖吃的是**長表**，不是 series —— 少了它那一張畫的是「no boxes to
    # plot」，而那句話對每一格設定都沒有反應（於是這支測試會說它壞了）。
    extra = {"frame": _sample_frame(), "spec": SAMPLE_SPEC}
    for kind in uc.CHARTS:
        a = uc.build_chart_svg(s, kind, cs.style_for("", kind), **extra)
        b = uc.build_chart_svg(
            s, kind, cs.style_for('{"tick_size":22,"tick_bold":true}', kind),
            **extra)
        assert a != b, kind


# --------------------------------------------------------------------------- #
# 接線（Studio）
# --------------------------------------------------------------------------- #
@pytest.fixture
def window(qapp):
    # ⚠ `studio` **一定要在模組層 import**：`conftest` 那支關掉「關閉時確認
    # 存檔」的 autouse fixture 是 ``sys.modules.get("d4t.ui.studio")`` ——
    # 在 fixture 裡才 import 的話它那時候還看不到這個模組，於是 `win.close()`
    # 會停在一個沒有人按得下去的 QMessageBox 上，測試就永遠跑不完
    # （實際發生過，2026-09-07）。
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def _pick_uniformity(window):
    nid = window.model.add_step("output_uniformity")
    window.select_node(nid)
    return nid


def test_the_button_opens_one_window_not_a_pile_of_them(qapp, window):
    """開第二次是把同一個抬到最前面。

    每按一次多開一個的話，改設定只會改到其中一個 —— 而其他幾個還畫著舊的
    樣子，兩張都畫得出來。
    """
    from d4t.ui import inspectors as insp_mod

    _pick_uniformity(window)
    assert isinstance(window.gauges._inspector, insp_mod.UniformityPreviewInspector)
    window.gauges._inspector.charts_requested.emit()
    first = window.gauges._charts_window
    assert first is not None and first.isVisible()
    window.gauges._inspector.charts_requested.emit()
    assert window.gauges._charts_window is first


def test_changing_the_style_in_the_window_writes_it_back_to_the_card(
        qapp, window):
    """視窗裡改完設定要**進 recipe**，而且 Ctrl+Z 撤得掉。

    一個會改 recipe 而撤不掉的視窗，比沒有那個視窗糟 —— 所以它走「量給我填」
    同一條路（`_on_param_requested` → `set_param`）。
    """
    nid = _pick_uniformity(window)
    before = str(window.model.nodes[nid].params.get("look", ""))
    window.gauges._on_chart_style_changed('{"tick_size":18}')
    assert window.model.nodes[nid].params["look"] == '{"tick_size":18}'
    window.undo()
    assert str(window.model.nodes[nid].params.get("look", "")) == before


def test_the_style_only_lands_on_a_uniformity_card(qapp, window):
    """選到別張卡的時候那個訊號**什麼都不做** —— 視窗還開著、使用者按了
    設定，而 `look` 落在一張沒有那一格的卡上會是一條驗證錯誤。

    ⚠ 這裡以前用的是 `output_report`，而 F87 第九刀給了它自己的 `look` ——
    那讓這條測試變成「寫得進去所以紅」。守的東西沒變（**那個視窗畫的是均勻度
    的圖，寫回去也只該寫那張卡**），換一張真的沒有那一格的卡就好。
    """
    nid = window.model.add_step("output_klarf")
    window.select_node(nid)
    window.gauges._on_chart_style_changed('{"tick_size":18}')
    assert "look" not in window.model.nodes[nid].params


def test_the_charts_window_does_not_write_to_the_report_card(qapp, window):
    """`Write report` **也有** `look` 了，而那正是這一條要守的：兩張卡各有
    各的一份，圖的視窗只寫它畫的那一張。"""
    nid = window.model.add_step("output_report")
    window.select_node(nid)
    before = str(window.model.nodes[nid].params.get("look", ""))
    window.gauges._on_chart_style_changed('{"tick_size":18}')
    assert str(window.model.nodes[nid].params.get("look", "")) == before


# --------------------------------------------------------------------------- #
# 熱圖疊在影像上（F87 第五刀）
# --------------------------------------------------------------------------- #
def _heat_view(qapp, n=6):
    import numpy as np

    from d4t.ui.widgets import ImageView

    view = ImageView()
    view.resize(400, 380)
    view.set_image(np.linspace(60, 200, 200 * 200,
                               dtype=np.float32).reshape(200, 200))
    cells = [(0.05 + 0.15 * i, 0.2, 0.15, 0.3) for i in range(n)]
    colours = [uc.heat_hex(i / max(1, n - 1)) for i in range(n)]
    view.set_heat(cells, colours, (10.0, 90.0, "glv_mean"))
    return view


def test_the_view_paints_the_heat_and_says_how_much(qapp):
    view = _heat_view(qapp)
    assert view.heat_count() == 6
    assert view.heat_legend() == (10.0, 90.0, "glv_mean")
    view.show()
    qapp.processEvents()
    view.grab()                       # 畫一次不准炸


def test_a_mismatched_heat_is_dropped_whole(qapp):
    """**長度對不上就整組不畫** —— 同 `set_overlay` / `set_marks` 的規矩。

    錯位的顏色會把值畫在別的地方，而畫面上沒有任何東西透露那件事。
    """
    view = _heat_view(qapp)
    view.set_heat([(0.1, 0.1, 0.2, 0.2), (0.4, 0.1, 0.2, 0.2)], ["#ff0000"],
                  (0.0, 1.0, "x"))
    assert view.heat_count() == 0


def test_clearing_the_heat_takes_the_bar_with_it(qapp):
    view = _heat_view(qapp)
    view.clear_heat()
    assert view.heat_count() == 0 and view.heat_legend() is None
    view.grab()


def test_the_heat_goes_under_the_boxes_not_over_them(qapp):
    """順序就是意思：熱色是「量出來多少」，框是「量的是哪一塊」。

    反過來畫的話，一片色塊會蓋掉框 —— 而「這一塊的顏色是從哪一格量來的」
    那句話就沒了（PEAR 的 `_paint_heat_cells` 也是先熱後框）。
    """
    import inspect as _inspect

    from d4t.ui.widgets import ImageView

    src = _inspect.getsource(ImageView.paintEvent)
    assert src.index("_paint_heat(") < src.index("_paint_overlay(")
    assert src.index("_paint_overlay(") < src.index("_paint_marks(")


def test_the_colour_bar_is_readable_on_any_image(qapp):
    """色條底下要墊一塊 —— 影像可以是任何亮度，直接寫字的話深色圖上那兩個
    數字看不見，而那些顏色就不再是資料、只是裝飾。"""
    import inspect as _inspect

    from d4t.ui.widgets import ImageView

    src = _inspect.getsource(ImageView._paint_heat_bar)
    assert "bg_surface" in src and "drawRoundedRect" in src


def test_the_studio_hands_the_view_what_the_card_says(qapp, window):
    """卡片交、UI 畫 —— 同 `measure_marks` 那條界線（`Step.overlay_heat`）。"""
    nid = window.model.add_step("output_uniformity")
    window.select_node(nid)
    # 還沒跑過就什麼都沒有（熱色來自 context，不是 model）
    assert window.heat_tiles("test") == ([], [], None)
    assert window.image_view.heat_count() == 0


# --------------------------------------------------------------------------- #
# 卡片上的那一格（F87 第六刀）
# --------------------------------------------------------------------------- #
def test_the_chart_look_row_has_a_button_not_a_json_box(qapp):
    """使用者 2026-09-07：「Chart look 是什麼? 我沒看到 Chart setting
    沒看到編輯器」。

    `chart_style` 的值是一串 JSON。沒有專屬編輯器的話那一格會掉進表單的預設
    分支 —— 一個**可以打字的文字框，裡面是生 JSON** —— 而目標使用者是不會寫
    code 的製程工程師。更糟的是編輯器**存在**、只是掛在別的地方，所以畫面上
    那一格看起來就是「這個功能沒做」。
    """
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ChartStyleField, ParamForm

    form = ParamForm()
    form.set_step(get_step("output_uniformity").describe(),
                  {"folder": "out", "charts": "box,map",
                   "look": '{"tick_size":14,"box.title":"EPI"}'}, [], [])
    row = form._rows["look"]
    assert isinstance(row.editor, ChartStyleField)
    # **原字串照放，不偷偷正規化** —— 這一格只是顯示，改寫 recipe 的值
    # 要有人真的按了 OK（同 `CurveField` 只在 `curve_changed` 時才送出）。
    assert row.editor.text() == '{"tick_size":14,"box.title":"EPI"}'
    assert "2 changes" in row.editor.summary.text()
    assert row.editor.button.text().startswith("Chart settings")


def test_every_chart_style_param_gets_that_editor(qapp):
    """**registry 全掃** —— 下一張用 `chart_style` 的卡不必再發現一次。"""
    from d4t.core.pipeline import list_steps
    from d4t.ui.widgets import ChartStyleField, ParamForm

    seen = 0
    for card in list_steps():
        spec = card.describe()
        names = [q["name"] for q in spec["params"]
                 if q["type"] == "chart_style"]
        if not names:
            continue
        form = ParamForm()
        form.set_step(spec, {}, [], [])
        for name in names:
            assert isinstance(form._rows[name].editor, ChartStyleField), name
            seen += 1
    assert seen, "沒有任何一格是 chart_style —— 這條測試就沒在守東西了"


def test_the_editor_only_offers_the_charts_this_card_writes(qapp):
    """右半的分頁 = 這張卡勾了哪幾張圖。沒勾的那幾張的覆寫**不准被清掉**。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    form.set_step(get_step("output_uniformity").describe(),
                  {"folder": "out", "charts": "box",
                   "look": '{"map.title":"Where"}'}, [], [])
    assert form._chart_kinds() == ["box"]
    dlg = ChartSettingsDialog(form._rows["look"].editor.text(),
                              form._chart_kinds())
    assert sorted(dlg.per) == ["box"]
    assert "map.title" in dlg.value()


def test_an_empty_charts_box_still_opens_on_all_four(qapp):
    """一個空的分頁區讀起來是「壞了」—— 沒勾就全部給。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    form.set_step(get_step("output_uniformity").describe(),
                  {"folder": "out", "charts": ""}, [], [])
    assert form._chart_kinds() == list(uc.CHARTS)


# --------------------------------------------------------------------------- #
# 即時預覽（F87 第七刀）
# --------------------------------------------------------------------------- #
def test_the_editor_previews_every_chart_it_offers(qapp):
    """使用者 2026-09-07：「Chart setting 我是希望能支援即時 preview」。"""
    dlg = ChartSettingsDialog("", list(uc.CHARTS))
    assert sorted(dlg.views) == sorted(uc.CHARTS)
    for kind, view in dlg.views.items():
        assert view.svg(), kind


def test_every_editor_moves_the_preview(qapp):
    """**每一格都要有反應。**

    漏接一種 widget 的下場是那一格「調了沒反應」—— 比沒有預覽更糟，因為使用者
    會以為那個設定壞了。所以逐格動一下，然後問四張圖有沒有變。
    ⚠ 有些格子只影響某一張（`bins` 只影響直方圖、`whiskers` 只影響盒鬚圖），
    所以問的是「**至少一張**變了」。
    """
    from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLineEdit, QSpinBox

    from d4t.ui.chart_settings import ColourButton

    # ⚠ **要真的排版過**：沒 show 的話每一張預覽停在 260 px 最小寬，而熱圖在
    # 那個寬度下一格只剩 20 px —— 「每一格印出值」有一條「放不下就不印」的
    # 規矩，於是那一格會看起來沒反應，而那是尺寸問題不是接線問題。
    # ⚠ 自己配的那一張要給一份**長條**的 spec（F89-5）：有幾格只有某幾種
    # 記號讀得到（`slot_order` 只有長條與盒鬚），而拿預設的散點來試等於問一個它本來
    # 就答不了的問題 —— 那一格在畫面上也是收起來的。
    #
    # ⚠ X 要挑一個**槽夠多**的欄（`value` 有 18 個相異值）：長條把 X 當槽，
    # 而槽 ≤ 12 的時候標籤是全部都印的 —— 那時候「橫著幾個刻度」不動任何
    # 東西，而那是那一格的定義，不是它沒接上（同 `lo`/`hi` 那兩格）。
    from d4t.ui.chart_settings import _sample_frame

    dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame(),
                              spec='{"mark":"bar","x":"value","y":"spread"}')
    dlg.resize(1020, 760)
    dlg.show()
    qapp.processEvents()
    # 只有**現在那一頁**會被排版，其餘分頁的預覽停在最小寬（Qt 的行為，不是
    # bug —— 使用者切到那一頁時它就撐開了）。這裡問的是「設定有沒有走到畫圖
    # 那一側」，不是版面，所以直接給每一張一個看得出東西的尺寸。
    for _v in dlg.views.values():
        _v.resize(460, 280)
    qapp.processEvents()
    editors = list(dlg.globals.items()) + [
        ("%s.%s" % (k, n), w)
        for k, f in dlg.per.items() for n, w in f.items()]
    # ⚠ **`yscale` 排到最後。** 這個迴圈是累積的（改過的那一格留著改過的值），
    # 而切成 log 之後那條軸的刻度是**整數次方**，不是「你要幾個就幾個」——
    # 於是後面輪到 `yticks` 時它動不了任何東西，而那是 log 軸的定義，不是那
    # 一格沒接上。把它放最後，後面就沒有人被它影響。
    editors.sort(key=lambda kv: kv[0] == "yscale")
    # ⚠ `lock` **一格自己不算數**，而那是它的定義：`chart_style.style_for`
    # 只在 `hi > lo` 時才鎖，兩格都是 0（預設）就是 auto。面板上也是這樣
    # 帶的（關著的時候 Bottom/Top 是灰的）。所以先給它一段真的範圍。
    dlg.globals["lo"].setValue(100.0)
    dlg.globals["hi"].setValue(140.0)
    qapp.processEvents()

    for name, w in editors:
        before = {k: v.svg() for k, v in dlg.views.items()}
        if name == "ref_lines":
            # ⚠ 這一格**不能塞任意字串**（雖然它是個 QLineEdit）：它有格式，
            # 而壞掉的值會被 `_coerce` 擋下來 → 預覽不動 → 這支測試會說它沒
            # 接上，而那正是它接對了的證據。要給一個**落在樣本範圍裡**的數字
            # （樣本的 value 大約 112–132）—— 落在範圍外的那條線刻意不畫
            # （`draw_refs` 的規矩）。
            w.setText("USL=125")
        elif isinstance(w, ColourButton):
            w.set_value("#123456")
        elif isinstance(w, (QCheckBox, BoolChips)):
            w.setChecked(not w.isChecked())
        elif isinstance(w, ChoiceChips):
            # 換到**下一顆**（不是第一顆 —— 那可能就是現在選著的那一個，
            # 而「值一樣」不是「沒接上」）。
            got = [c.mid for c in w._chips]
            w.chip(got[(got.index(w.text()) + 1) % len(got)]).click()
        elif isinstance(w, QLineEdit):
            # ⚠ **每一格一個不同的字**：全都填 "moved" 的話，`value_name` 會
            # 先把直方圖的 X 軸變成 "moved"，接著 `histogram.xlabel` 也填
            # "moved" —— 圖當然沒變，而那是「值一樣」不是「沒接上」。
            w.setText("moved-%s" % name)
        elif "." in name and isinstance(w, QSpinBox):
            # ⚠ 每張圖自己的刻度數要給一個**跟全域不一樣**的值：上面那一輪已經
            # 把全域的 `xticks`/`yticks` 拉到 20，再覆寫成 20 是 no-op，而那
            # 是「值一樣」，不是「這一格沒接上」。
            w.setValue(w.minimum() + 3)
        elif name in ("lo", "hi"):
            # ⚠ 這兩格**不能用極值試**：`lo` 拉到 1e9 之後 `hi` 再拉到 1e9，
            # 兩次都是「上界沒有高過下界」→ 兩次都不鎖 → 圖都沒變，而那是
            # 這兩格的定義，不是它們沒接上。給一段真的範圍才問得出來。
            w.setValue(120.0 if name == "lo" else 200.0)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            lo, hi = w.minimum(), w.maximum()
            w.setValue(hi if w.value() != hi else lo)
        else:
            raise AssertionError("unknown editor for %s: %r" % (name, w))
        qapp.processEvents()
        after = {k: v.svg() for k, v in dlg.views.items()}
        assert any(after[k] != before[k] for k in before), name


def test_a_half_typed_value_does_not_break_the_preview(qapp):
    """使用者正在打字，中途一定會經過打不完的狀態 —— 不准擋路。"""
    dlg = ChartSettingsDialog("", ["box"])
    dlg.globals["value_name"].setText("Gray")
    qapp.processEvents()
    assert dlg.views["box"].svg()
    dlg.globals["tick_color"].set_value("#nothex")   # 繞過 UI 灌一個壞值
    qapp.processEvents()
    assert dlg.views["box"].svg(), "壞值只該讓預覽停住，不該炸"


def test_the_preview_says_when_it_is_sample_data(qapp):
    """沒有資料時預覽用樣本 —— 而**那件事要說出來**，不然他會以為那是他的圖。"""
    dlg = ChartSettingsDialog("", ["box"])
    assert dlg._is_sample is True
    from PySide6.QtWidgets import QLabel

    hints = [w.text() for w in dlg.findChildren(QLabel)
             if "sample data" in w.text()]
    assert hints, "沒有那一句提醒"


def test_real_data_replaces_the_sample(qapp):
    dlg = ChartSettingsDialog("", ["box"], series=_series())
    assert dlg._is_sample is False
    assert dlg._series["metric"] == "glv_mean"
    dlg.set_series(None)
    assert dlg._is_sample is True


def test_the_window_hands_its_own_data_to_the_editor(qapp):
    """調外觀最有用的是**用自己的資料看** —— 視窗要把手上那一顆帶進去。"""
    import inspect as _inspect

    from d4t.ui.uniformity_window import UniformityWindow

    src = _inspect.getsource(UniformityWindow.open_settings)
    assert "series=self._series" in src


def test_the_card_row_can_be_fed_a_series(qapp):
    """`Chart look` 那一列同理（Studio 從儀表餵）。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ParamForm

    form = ParamForm()
    form.set_step(get_step("output_uniformity").describe(),
                  {"folder": "out", "charts": "box"}, [], [])
    form.set_chart_series(_series())
    assert form._rows["look"].editor._series["metric"] == "glv_mean"


# --------------------------------------------------------------------------- #
# 暗色主題（F87 第七刀）
# --------------------------------------------------------------------------- #
def test_all_four_charts_carry_their_own_white_background(qapp):
    """使用者 2026-09-07：「暗色模式下 preview chart box plot 的表示會跟其他
    人不一樣」。

    以前盒鬚圖沒有底：在報表的白色頁面上看不出來，但圖的視窗用主題色當底 ——
    暗色主題下那張圖是**透明**的，深灰的字落在近黑的底上幾乎看不見，而旁邊
    三張都是白卡片。

    補的是**底**不是主題：這四張會被寫進 HTML、貼進投影片，那些地方是白的。
    """
    s = _series()
    for kind in uc.CHARTS:
        svg = uc.build_chart_svg(s, kind, {})
        assert "fill='#fff'" in svg or 'fill="#fff"' in svg, kind


def test_the_preview_uses_the_same_style_resolver_as_the_file(qapp):
    """**預覽只能有一條路** —— `uniformity_window.chart_style_for`。

    這一條是踩出來的：第一版的預覽直接叫 `chart_style.style_for`，少了住在
    卡片上的那一半（這張圖預設叫什麼、「值那一軸」的名字落在哪一軸）。症狀是
    改 `Name of the value axis` 那一格**畫面完全沒有反應**，而它在寫出去的
    檔案裡是有作用的 —— 「預覽跟輸出不一樣」正是這整個功能最貴的那種 bug。
    抓到它的是 `test_every_editor_moves_the_preview`。
    """
    import inspect as _inspect

    from d4t.ui.chart_settings import ChartSettingsDialog as _D

    src = _inspect.getsource(_D.refresh_preview)
    assert "chart_style_for(" in src
    assert "cs.style_for(" not in src

    # 而它真的把 value_name 帶到那一軸上（不是只有呼叫得到）
    dlg = ChartSettingsDialog('{"value_name":"Gray level"}', ["histogram"])
    assert "Gray level" in dlg.views["histogram"].svg()


# --------------------------------------------------------------------------- #
# `Write report` 的盒鬚圖也吃同一份設定（F87 第九刀）
# --------------------------------------------------------------------------- #
def test_the_report_box_plot_takes_the_same_settings(qapp):
    """使用者 2026-09-07：「有辦法把 report 的 box plot 跟 Uniformity 整合嗎」
    → 先做「讓兩張圖長得一樣」。

    兩張卡畫的本來就是**同一支** `build_boxplot_svg`，但以前只有
    `Write charts` 吃得到 `Chart settings` —— 於是同一份投影片裡兩張盒鬚圖
    的字級、線寬、鎖定範圍都不一樣，而畫面上沒有任何線索說為什麼。
    """
    from d4t.core.pipeline import get_step

    names = [q["name"] for q in get_step("output_report").describe()["params"]]
    assert "look" in names
    spec = [q for q in get_step("output_report").describe()["params"]
            if q["name"] == "look"][0]
    assert spec["type"] == "chart_style"


def test_the_report_card_offers_only_the_box_plot_and_no_per_chart_words(qapp):
    """它只畫盒鬚圖，而且**一次畫好幾張**（一個數字一張）——
    所以「這張圖的標題」那一格在這裡沒有意思（一組標題會套到五張上）。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ParamForm

    card = get_step("output_report")
    assert card.chart_kinds({}) == [uc.CHART_BOX]
    assert card.chart_words is False

    form = ParamForm()
    form.set_step(card.describe(), {"folder": "out"}, [], [])
    assert form._chart_kinds() == [uc.CHART_BOX]
    assert form._chart_words() is False
    dlg = ChartSettingsDialog("", form._chart_kinds(),
                              words=form._chart_words())
    assert sorted(dlg.views) == [uc.CHART_BOX], "預覽還是要有"
    assert dlg.per[uc.CHART_BOX] == {}, "但沒有那幾格字"


def test_the_uniformity_card_still_has_its_words(qapp):
    """反過來的那一半 —— 換一張卡不該把別張卡的東西也拿掉。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ParamForm

    card = get_step("output_uniformity")
    assert card.chart_words is True
    assert card.chart_kinds({"charts": "box,map"}) == ["box", "map"]
    form = ParamForm()
    form.set_step(card.describe(), {"folder": "out", "charts": "box"}, [], [])
    assert form._chart_words() is True
    assert form._chart_kinds() == ["box"]


def test_the_report_box_plot_really_changes_with_the_look(qapp, tmp_path):
    """不是「有那一格」而已 —— 設定要真的走到畫出來的 SVG 上。"""
    from d4t.core.export import uniformity_charts as _uc
    from d4t.core.pipeline import get_step

    card = get_step("output_report")()
    series = [{"name": "a", "values": [1.0, 2.0, 3.0, 4.0, 9.0]}]

    class _B:
        rows = [{"defect_id": "1", "ok": True, "features": {"m": 1.0}}]

        def warn(self, *_a):
            pass

    groups = [{"name": "a", "ids": ["1"], "colour": "#5fd0a0"}]
    plain = card._charts(_B(), ["m"], groups,
                         style=_uc.resolve_style("", _uc.CHART_BOX))
    big = card._charts(_B(), ["m"], groups,
                       style=_uc.resolve_style('{"tick_size":22}',
                                               _uc.CHART_BOX))
    assert plain and big
    assert plain[0]["svg"] != big[0]["svg"]
    assert series  # 只是說明那個形狀，實際資料來自 bctx


def test_settings_that_cannot_apply_are_hidden(qapp):
    """只畫盒鬚圖的卡片不必看到「直方圖切幾根柱」（`GLOBAL_APPLIES`）。

    ⚠ **收起來不等於清掉** —— 值仍然 round-trip 回去：把 Heat map 取消勾選
    再勾回來，設定要還在。
    """
    look = '{"bins":40,"equal_cells":false,"tick_size":13}'
    dlg = ChartSettingsDialog(look, [uc.CHART_BOX], words=False)
    assert dlg.globals["bins"].isVisibleTo(dlg) is False
    assert dlg.globals["equal_cells"].isVisibleTo(dlg) is False
    assert dlg.globals["whiskers"].isVisibleTo(dlg) is True
    assert dlg.globals["tick_size"].isVisibleTo(dlg) is True
    assert cs.parse_style(dlg.value()) == cs.parse_style(look), \
        "藏起來的那幾格不准被清掉"


def test_all_the_charts_show_everything(qapp):
    """⚠ 「全部勾起來」現在**不夠**（F89-5）：有幾格還要看自己配的那一張畫成
    哪一種記號（`slot_order` 只有長條與盒鬚讀）。所以這裡也給一份長條的 spec ——
    這一條問的是「有沒有哪一格永遠躲著」，而那件事還是要有答案。
    """
    from d4t.ui.chart_settings import _sample_frame

    dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame(),
                              spec='{"mark":"bar","x":"region","y":"value"}')
    for key in cs.GLOBAL_KEYS:
        assert dlg.globals[key].isVisibleTo(dlg) is True, key


def test_every_global_setting_is_used_by_at_least_one_chart(qapp):
    """一格沒有任何一張圖用得到的設定，是一格沒有家的設定。"""
    for key, uses in uc.GLOBAL_APPLIES.items():
        assert key in cs.GLOBAL_KEYS, key
        assert uses and set(uses) <= set(uc.CHARTS), key


# --------------------------------------------------------------------------- #
# 填色與膠囊（F87 第十刀）
# --------------------------------------------------------------------------- #
def test_the_fills_can_be_set(qapp):
    """使用者 2026-09-07：「histogram的底色，例如直方圖或盒鬚圖的底 或
    Position profile的圓圈底顏色可以設定嗎?」→ 以前一個都設不到。"""
    from d4t.core.export.boxplot import build_boxplot_svg

    s = _series()
    box = [{"name": "a", "values": [1.0, 2.0, 3.0, 4.0, 9.0]}]
    base_box = build_boxplot_svg(box)
    assert build_boxplot_svg(box, style={"fill_strength": 2.0}) != base_box
    assert build_boxplot_svg(box, style={"fill_color": "#123456"}) != base_box
    base_hist = uc.build_chart_svg(s, uc.CHART_HIST, {})
    assert uc.build_chart_svg(s, uc.CHART_HIST,
                              {"fill_strength": 2.0}) != base_hist
    assert uc.build_chart_svg(s, uc.CHART_HIST,
                              {"fill_color": "#123456"}) != base_hist
    base_prof = uc.build_chart_svg(s, uc.CHART_PROFILE, {})
    assert uc.build_chart_svg(s, uc.CHART_PROFILE,
                              {"point_fill": True}) != base_prof


def test_the_default_fill_is_byte_for_byte_the_old_one(qapp):
    """**倍率 1.0 就是以前那個字面值。**

    填色的濃度是倍率不是絕對值（每一種圖自己那個淡度是設計過的，而沒有一個
    絕對值同時等於今天的 0.45 與 0.18）。所以預設下 `output_report` 的盒鬚圖
    一個位元組都不准變。
    """
    from d4t.core.export.boxplot import build_boxplot_svg

    box = [{"name": "a", "values": [1.0, 2.0, 3.0, 4.0, 9.0]}]
    assert build_boxplot_svg(box) == build_boxplot_svg(box, style={})
    assert 'fill-opacity="0.18"' in build_boxplot_svg(box)
    assert "fill-opacity='0.45'" in uc.build_chart_svg(_series(),
                                                       uc.CHART_HIST, {})


def test_the_two_sides_of_a_switch_are_both_named(qapp):
    """**每一個開關都是一排兩顆膠囊，而兩顆都要說得出自己是什麼。**

    這一族的價值就在「不打勾會變成什麼樣子」本來看不見 —— 所以 off 那一顆
    不是「不要」，是它自己那個樣子的名字。
    """
    from d4t.ui.chart_settings import BOOL_CHIPS
    from d4t.ui.glyphs import CHIP_ICONS

    bools = {k for k, v in cs.DEFAULTS.items() if isinstance(v, bool)}
    # 兩個粗體旗標是那一列裡的一個屬性，不是「要哪一種長相」的問題；
    # `CHIP_VALUES` 那幾格值不是 bool，但問的一樣是「要哪一種長相」。
    assert (set(BOOL_CHIPS) - set(chart_settings.CHIP_VALUES)
            == bools - {"tick_bold", "axis_bold"})
    for key, (off, on, off_help, on_help) in BOOL_CHIPS.items():
        assert off[0] and on[0] and off[0] != on[0], key
        assert off[1] in CHIP_ICONS and on[1] in CHIP_ICONS, key
        assert off_help and on_help, key
        assert "not " not in off[0].lower(), (key, "說它自己是什麼，不是「不要」")


def test_a_chip_pair_behaves_like_a_checkbox(qapp):
    """`BoolChips` 長得像 QCheckBox，**而且設值會發訊號**。

    ⚠ `ChoiceChips.set_text` 刻意不發（載入 recipe 不該被當成使用者改了），
    而 `QCheckBox.setChecked` 會 —— 那條差別要在 `BoolChips` 補平，不然
    「程式設值不重畫」會變成「這一格沒有反應」。踩過：即時預覽對每一顆膠囊
    都沒反應。
    """
    seen = []
    w = BoolChips(("Off", "dots_off"), ("On", "dots_on"), False)
    w.toggled.connect(seen.append)
    assert w.isChecked() is False
    w.setChecked(True)
    assert w.isChecked() is True and seen == [True]
    w.setChecked(True)
    assert seen == [True], "沒有變就不要發"


def test_no_setting_has_two_controls(qapp):
    """**一格設定只能有一個地方改得到。**

    使用者 2026-09-07：「Icon 很漂亮，但有全應用進去嗎」—— 一眼看出
    `point_fill` 同時是「Data points」那一列裡的 `filled` 勾選框、又是
    「Markers」那一排膠囊。後放的把前面的從 `globals` 裡蓋掉，於是那個勾選框
    看得到、按得下、**什麼都不會發生**。

    這一條靠兩張表對得起來：`chart_style.ROWS`（那個網格）與
    `chart_settings.BOOL_CHIPS`（一排兩顆的那些）**不准有交集**。
    """
    from d4t.ui.chart_settings import BOOL_CHIPS

    in_grid = {k for _t, props in cs.ROWS for k, _c in props}
    assert not (in_grid & set(BOOL_CHIPS)), sorted(in_grid & set(BOOL_CHIPS))
    # 而每一格都要有**一個**家
    homed = (in_grid | set(BOOL_CHIPS) | set(chart_settings.CHOICE_CHIPS)
             | {"value_name", "bins", "xticks", "yticks", "lo", "hi",
                "ref_lines"})
    assert homed == set(cs.GLOBAL_KEYS), sorted(homed ^ set(cs.GLOBAL_KEYS))


def test_a_row_says_which_charts_it_reaches(qapp):
    """使用者 2026-09-07：「不同 chart 可設定的應該要不一樣?」

    左半名義上是「共用的」，但**共用不等於每一張都吃得到**。四張都勾著的
    時候每一列都在，而畫面上要說得出哪一列管哪一張。
    """
    dlg = ChartSettingsDialog("", list(uc.CHARTS))
    assert "Position profile" in dlg._labels["point_fill"].text(), \
        "「Markers」沒說它只影響 profile"
    assert "Histogram" in dlg._labels["xticks"].text()
    # **標題已經說了就不要再說一次** —— `Heat map cells` 底下再掛一行
    # `Heat map` 是噪音，而噪音會讓真正需要那行的幾列也被跳過不讀。
    #
    # ⚠ 這一條以前是一張寫死的鍵清單（那幾格「只影響它標題上那張圖」）。
    # F88 第四刀之後不成立了：`Heat map labels` 現在**也**管自己配的那一張，
    # 而那件事標題沒說 —— 所以那一列該有尾巴。規則本身沒有變，所以改成直接
    # 問規則：**尾巴裡不准出現標題已經講過的那張圖**。
    for key, lab in dlg._labels.items():
        text = lab.text()
        if "<span" not in text:
            continue
        title, tail = text.split("<br>", 1)
        for label in uc.CHART_LABELS.values():
            if label.lower() in title.lower():
                assert label not in tail, (key, text)
    # 每一張都吃得到的那幾格連尾巴都不加
    assert "<span" not in dlg._labels["value_name"].text()
    assert "<span" not in dlg._labels["lock"].text()
    # 而標題**沒有**說出來的那幾張要有尾巴（上面那兩條 `point_fill` /
    # `xticks` 就是；`bins` 的標題是「Histogram bars」，它自己說完了）。


def test_one_chart_needs_no_tag(qapp):
    """只有一張圖在畫面上的時候，每一列本來就是那張圖的 —— 不必再說一次。"""
    dlg = ChartSettingsDialog("", [uc.CHART_HIST])
    assert "<span" not in dlg._labels["bins"].text()
    assert "<span" not in dlg._labels["xticks"].text()


def test_a_setting_this_mark_cannot_use_is_hidden(qapp):
    """F88 第五刀：`GLOBAL_APPLIES` 是**一張圖一列**，答不出「這張圖現在畫成
    散點，那 `Whiskers` 有作用嗎」。

    沒有這一層的話，把 `Your own chart` 配成散點的人在設定裡看得到
    `Whiskers` 而它什麼都不做 —— 一格答了也沒用的設定比沒有那一格更糟。
    """
    from d4t.ui.chart_settings import _sample_frame

    frame = _sample_frame()
    seen = {}
    for mark, spec in (
            ("point", '{"mark":"point","x":"value","y":"spread"}'),
            ("box", '{"mark":"box","x":"region","y":"value"}'),
            ("cell", '{"color":"value","mark":"cell","x":"col","y":"row"}')):
        dlg = ChartSettingsDialog("", [uc.CHART_CUSTOM], frame=frame,
                                  spec=spec)
        seen[mark] = {k for k in ("whiskers", "map_values", "points",
                                  "point_fill", "fill_color")
                      if dlg.globals[k].isVisibleTo(dlg)}
    assert "whiskers" in seen["box"] and "whiskers" not in seen["point"]
    assert "map_values" in seen["cell"] and "map_values" not in seen["box"]
    assert "point_fill" in seen["point"] and "point_fill" not in seen["cell"]


def test_the_hidden_ones_are_still_carried_back_out(qapp):
    """**收起來不等於清掉** —— 換一種記號再換回來，設定要還在。"""
    from d4t.ui.chart_settings import _sample_frame

    look = '{"whiskers":false}'
    dlg = ChartSettingsDialog(look, [uc.CHART_CUSTOM], frame=_sample_frame(),
                              spec='{"mark":"point","x":"value","y":"spread"}')
    assert not dlg.globals["whiskers"].isVisibleTo(dlg)
    assert cs.parse_style(dlg.value()).get("whiskers") is False


# --------------------------------------------------------------------------- #
# F89-1：預覽讀得動（使用者 2026-09-08：「預覽圖每次都會太小」）
# --------------------------------------------------------------------------- #
def test_the_preview_keeps_its_shape_instead_of_becoming_a_tall_strip(qapp):
    """**問題不是「太小」，是長寬比是反的。**

    以前那一格只給了最小高度再 `setRowStretch(..., 1)`，於是它吃掉分頁裡所有
    垂直空間，被拉成 390 寬 × 655 高 —— 而 SVG 是**照那個尺寸產的**，所以
    盒鬚圖被畫成一根直條，第二個盒子掉到摺線下面。圖表要的是寬 > 高。
    """
    from d4t.ui.chart_settings import _sample_frame

    want = ChartSettingsDialog.PREVIEW_ASPECT
    for w, h in ((1180, 940), (1600, 1100), (1020, 700)):
        dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame())
        dlg.resize(w, h)
        dlg.show()
        qapp.processEvents()
        view = dlg.views[uc.CHART_BOX]
        got = view.width() / float(max(1, view.height()))
        assert abs(got - want) < 0.1, (w, h, view.width(), view.height())


def test_the_preview_grows_with_the_window(qapp):
    from d4t.ui.chart_settings import _sample_frame

    seen = []
    for w, h in ((1180, 940), (1700, 1200)):
        dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame())
        dlg.resize(w, h)
        dlg.show()
        qapp.processEvents()
        seen.append(dlg.views[uc.CHART_BOX].width())
    assert seen[1] > seen[0], seen


def test_the_chart_does_not_scroll_away_while_you_change_a_setting(qapp):
    """整頁在一個捲動區裡的話，拉一個滑桿要往下捲，而捲下去圖就出畫面了
    —— 那正好毀掉即時預覽存在的理由。**設定捲動，圖不動。**"""
    from PySide6.QtWidgets import QScrollArea

    from d4t.ui.chart_settings import _sample_frame

    dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame())
    dlg.show()
    qapp.processEvents()
    view = dlg.views[uc.CHART_BOX]
    parent = view.parent()
    while parent is not None:
        assert not isinstance(parent, QScrollArea), "預覽掉進捲動區裡了"
        parent = parent.parent()


def test_the_settings_column_is_never_squeezed_sideways(qapp):
    """最右邊那顆回到 auto 的 `×` 被切掉的話，就沒有路回到「跟著區域色走」
    （`ColourButton` 的說明）。寬度不夠讓對話框長，不要切內容。"""
    from PySide6.QtWidgets import QScrollArea

    from d4t.ui.chart_settings import _sample_frame

    dlg = ChartSettingsDialog("", list(uc.CHARTS), frame=_sample_frame())
    dlg.resize(1180, 940)
    dlg.show()
    qapp.processEvents()
    scroll = dlg.findChild(QScrollArea)
    assert not scroll.horizontalScrollBar().isVisible()
    assert scroll.width() >= scroll.widget().sizeHint().width()
