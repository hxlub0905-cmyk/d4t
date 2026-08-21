# d4t Studio UI 元件測試 — authored 2026-07-28 (M3).
"""``d4t/ui/theme.py`` 與 ``d4t/ui/widgets.py`` 的離屏（offscreen）測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_widgets.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 是「先蒐集全部測試檔、再開始跑」，所以只要這個檔案在
**模組層** ``import PySide6``，蒐集階段就會把 Qt 塞進 ``sys.modules``，那個守門測試
就會紅 —— 即使它先跑。

因此：所有 Qt / ``d4t.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須要求 ``qapp`` fixture，否則那些名字不存在。

pytest-qt 沒有安裝：訊號一律用手動 slot（append 到 list）捕捉，滑鼠事件用
``QTest`` 或自己建構 ``QMouseEvent`` 後 ``QApplication.sendEvent`` 派送
（離屏平台上 ``QTest.mouseMove`` 不可靠，拖曳的中間段自己派送最穩）。
"""
from __future__ import annotations

import sys

import numpy as np
import pytest


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: F401
    from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: F401
    from PySide6.QtTest import QTest  # noqa: F401
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit,
        QSlider, QSpinBox,
    )

    from d4t.ui import theme as theme_mod  # noqa: F401
    from d4t.ui import widgets as widgets_mod  # noqa: F401
    from d4t.ui import viewmodel as vm_mod  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _steps():
    """真實 registry 的 describe() dict（不是手捏的假資料）。"""
    import d4t.core.steps  # noqa: F401 — 觸發註冊
    from d4t.core.pipeline import list_steps

    return [s.describe() for s in list_steps()]


def _describe(key):
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    return get_step(key).describe()


def _mouse(widget, etype, pos, button=None, buttons=None):
    """建構並派送一顆滑鼠事件（離屏環境下比 QTest.mouseMove 可靠）。"""
    button = Qt.NoButton if button is None else button
    buttons = button if buttons is None else buttons
    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
                     Qt.NoModifier)
    QApplication.sendEvent(widget, ev)



# --------------------------------------------------------------------------- #
# theme
# --------------------------------------------------------------------------- #
def _rgb(hexstr):
    h = str(hexstr).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def test_theme_applies_and_has_d4t_tokens(qapp):
    assert qapp.styleSheet(), "apply_theme 應該有裝上 QSS"
    qss = theme_mod.build_stylesheet()
    # 主要動作按鈕靠 objectName "primary"
    assert "QPushButton#primary" in qss
    for selector in ("QComboBox", "QSpinBox", "QLineEdit", "QCheckBox::indicator",
                     "QScrollBar", "QSplitter::handle", "QHeaderView::section",
                     "QToolTip", "QAbstractItemView"):
        assert selector in qss, selector


def test_theme_is_neutral_and_flat(qapp):
    """F7-2 的兩條產品要求，用性質斷言而不是寫死色碼。

    舊配色是暖奶油底 + 琥珀 accent + 填滿色塊，使用者的評語是「太像玩具」。
    這裡鎖住的是**中性**（大面積不帶色相）與**平面**（無陰影漸層），
    色碼本身還可以繼續微調。
    """
    for key in ("bg_page", "bg_panel", "bg_surface", "toolbar", "statusbar"):
        r, g, b = _rgb(theme_mod.TOKENS[key])
        assert max(r, g, b) - min(r, g, b) <= 8, \
            "%s = %s 帶了明顯色相，大面積底色要中性" % (key, theme_mod.TOKENS[key])

    qss = theme_mod.build_stylesheet()
    for banned in ("box-shadow", "qlineargradient", "qradialgradient"):
        assert banned not in qss, "平面設計不用 %s" % banned


def test_every_colour_token_is_a_real_colour(qapp):
    """Qt 對無效的顏色字串是**靜靜畫成黑色**，不會報錯（F7-17）。

    暗色盤裡曾經有 ``"accent_border": "#2f4straight"`` —— 一個「稍後修正」的
    佔位字串，靠 70 行之後的一句覆寫救著。那句覆寫要是哪天被搬走或漏掉，
    畫面上只會多出幾條看不出所以然的黑邊，沒有任何錯誤訊息。
    """
    import re

    hexish = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
    bad = []
    for name, palette in theme_mod.PALETTES.items():
        for key, value in palette.items():
            if isinstance(value, str) and value.startswith("#") \
                    and not hexish.match(value):
                bad.append("%s.%s = %r" % (name, key, value))
    assert not bad, "不是合法顏色的 token：%s" % bad


def test_light_and_dark_palettes_have_identical_keys(qapp):
    light, dark = theme_mod.PALETTES["light"], theme_mod.PALETTES["dark"]
    assert set(light) == set(dark), set(light) ^ set(dark)
    assert set(theme_mod.TOKENS) == set(light)
    # 暗色真的比較暗（拿最大的底色面積比）
    assert sum(_rgb(dark["bg_page"])) < sum(_rgb(light["bg_page"]))


def test_every_token_the_ui_asks_for_actually_exists():
    """``TOKENS["typo"]`` 只會在**那個 widget 被畫出來的那一刻**炸。

    離屏測試通常不觸發 ``paintEvent``（沒有人 grab 它），所以自繪元件裡
    打錯的 token 名可以一路活到使用者打開那個畫面才 KeyError ——
    已經發生過一次（``surface_raised``）。這裡靜態掃一遍，成本近乎零。

    不需要 ``qapp``：純文字掃描，故意不 import Qt。
    """
    import ast
    import pathlib

    from d4t.ui import theme as t

    ui = pathlib.Path(__file__).resolve().parent.parent / "d4t" / "ui"
    bad = []
    for py in sorted(ui.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            target = node.value
            name = (target.id if isinstance(target, ast.Name)
                    else getattr(target, "attr", None))
            if name != "TOKENS":
                continue
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value not in t.PALETTES["light"]:
                    bad.append("%s:%d  TOKENS[%r]"
                               % (py.name, node.lineno, key.value))
    assert not bad, "這些 token 不存在（畫到那個 widget 時才會 KeyError）：\n  " \
                    + "\n  ".join(bad)


def test_self_painted_widgets_survive_an_actual_repaint(qapp):
    """真的畫一次。自繪元件的 bug 只在 ``paintEvent`` 執行時才浮出來。"""
    from PySide6.QtGui import QPixmap

    widgets = [widgets_mod.CurveEditor(), widgets_mod.CurveField(),
               widgets_mod.ImageView(), widgets_mod.GroupIcon("region", "#c06a1d"),
               widgets_mod.HistogramWidget(), widgets_mod.VerdictChip(),
               widgets_mod.ProfilePanel()]
    lib = widgets_mod.LibraryPanel()
    lib.set_steps(_steps())
    widgets.append(lib)

    for theme_name in ("light", "dark"):
        theme_mod.set_theme(theme_name)
        for w in widgets:
            w.resize(220, 160)
            pm = QPixmap(w.size())
            pm.fill()
            w.render(pm)          # KeyError / 例外會在這裡冒出來
            assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


def test_set_theme_is_in_place_and_reversible(qapp):
    """``TOKENS`` 必須是**同一個物件** —— 各模組都 import 過它了。"""
    before = theme_mod.TOKENS
    try:
        theme_mod.set_theme("dark")
        assert theme_mod.TOKENS is before, "set_theme 不可以換掉 TOKENS 物件"
        assert theme_mod.current_theme() == "dark"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
        assert theme_mod.seg_hex("algo") == theme_mod.PALETTES["dark"]["seg_algo"]

        # 不認得的名字要退回預設，不能炸
        assert theme_mod.set_theme("nope") == theme_mod.DEFAULT_THEME
    finally:
        theme_mod.apply_theme(qapp, "light")
    assert theme_mod.current_theme() == "light"


def test_theme_segment_tokens(qapp):
    t = theme_mod.TOKENS
    for cat in ("image", "algo", "adc"):
        assert t["seg_%s" % cat].startswith("#")
        assert t["seg_%s_bg" % cat].startswith("#")
    for tone in ("good", "bad", "neutral"):
        for part in ("bg", "text", "border"):
            assert t["chip_%s_%s" % (tone, part)].startswith("#")


def test_seg_color_mapping(qapp):
    for cat in ("image", "algo", "adc"):
        assert theme_mod.seg_color(cat).name() == theme_mod.TOKENS["seg_%s" % cat]
        assert theme_mod.seg_bg(cat).name() == theme_mod.TOKENS["seg_%s_bg" % cat]
    assert theme_mod.seg_color("algo", bg=True).name() == theme_mod.TOKENS["seg_algo_bg"]
    # 未知分類要有中性退路，不能炸
    assert theme_mod.seg_color("nope").isValid()


# --------------------------------------------------------------------------- #
# 1. ImageView
# --------------------------------------------------------------------------- #
def test_image_view_uint8_float_and_none(qapp):
    view = widgets_mod.ImageView()
    view.resize(320, 240)

    assert view.has_image() is False          # 初始 = 空狀態（畫「（無影像）」）

    u8 = np.arange(256, dtype=np.uint8).reshape(16, 16)
    view.set_image(u8)
    assert view.has_image()
    assert view.image().dtype == np.uint8
    np.testing.assert_array_equal(view.image(), u8)   # uint8 直接用，不做拉伸
    assert view.scale() > 1.0                          # 16x16 塞進 320x240 -> 放大

    # float + NaN：自動 min-max，NaN 不參與統計也不會炸
    f = np.full((8, 8), np.nan, dtype=np.float32)
    f[0, 0] = -2.0
    f[7, 7] = 6.0
    view.set_image(f)
    shown = view.image()
    assert shown.dtype == np.uint8
    assert shown[0, 0] == 0 and shown[7, 7] == 255
    assert shown[3, 3] == 0                            # NaN -> 0

    # 全 NaN 不應該爆
    view.set_image(np.full((4, 4), np.nan, dtype=np.float32))
    assert int(view.image().max()) == 0

    view.set_image(None)
    assert view.has_image() is False


def test_image_view_wheel_zoom_changes_scale(qapp):
    view = widgets_mod.ImageView()
    view.resize(300, 200)
    view.set_image(np.zeros((50, 50), dtype=np.uint8))
    before = view.scale()

    ev = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
                     QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(view, ev)
    assert view.scale() > before

    ev_out = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
                         QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                         Qt.NoScrollPhase, False)
    QApplication.sendEvent(view, ev_out)
    assert view.scale() == pytest.approx(before, rel=1e-6)

    view.zoom_by(4.0)
    assert view.scale() > before
    view.fit()                                   # 雙擊走的是同一條路
    assert view.scale() == pytest.approx(before, rel=1e-6)


# --------------------------------------------------------------------------- #
# 2. ParamForm（用真實 registry 的卡片）
# --------------------------------------------------------------------------- #
def test_param_form_int_and_image_key_from_snr_map(qapp):
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))

    desc = _describe("snr_map")
    streams = ["test", "ref", "diff", "ref_aligned"]
    form.set_step(desc, {"window": 31}, streams)

    # 每個 ParamSpec 都要有一列
    assert form.param_names() == [p["name"] for p in desc["params"]]
    # 建表本身不可以噴 param_edited
    assert edits == []

    window = form.editor("window")
    assert isinstance(window, QSpinBox)
    assert (window.minimum(), window.maximum()) == (5, 201)
    assert window.value() == 31
    window.setValue(41)
    assert edits[-1] == ("window", 41)
    assert isinstance(edits[-1][1], int)

    clip = form.editor("clip_sigma")
    assert isinstance(clip, QDoubleSpinBox)
    assert clip.value() == pytest.approx(3.0)
    clip.setValue(4.5)
    assert edits[-1] == ("clip_sigma", pytest.approx(4.5))
    assert isinstance(edits[-1][1], float)

    # image_key -> **唯讀顯示**（F9-6：來源只在畫布上決定）。
    #
    # 以前這裡是可編輯的下拉，於是同一件事有兩個入口 —— 拉線會改它、下拉也會
    # 改它 —— 而兩邊很容易對不起來（使用者的原話是「他會很亂連」）。現在這一格
    # 只顯示現在接的是什麼，改要回畫布上拉線。
    source = form.editor("source")
    assert isinstance(source, QLineEdit)
    assert source.isReadOnly() is True, "來源不該在參數表單裡改得動"
    assert source.text() == "diff", "要看得到現在接的是哪一條"
    assert source.toolTip().strip(), "唯讀就要講得出去哪裡改（推廣鐵則）"
    n_before = len(edits)
    source.setText("ref_aligned")          # 程式硬設也不該當成使用者編輯
    assert len(edits) == n_before, "唯讀欄位不可以發出參數變更"

    # 每一列都看得見白話 help（推廣鐵則）
    for spec in desc["params"]:
        assert form.hint_text(spec["name"]) == spec["help"]
        assert spec["help"]


def test_bounded_numbers_get_a_slider_bound_both_ways(qapp):
    """F7-8：有上下界的數字都配一支滑桿。

    「gamma 要填多少」對不會寫 code 的人沒有答案 —— 他要的是一邊拖一邊看圖。
    數字框留著，因為 recipe 是要交接給別人的，那需要一個確切的值。
    """
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))
    form.set_step(_describe("tone"), {}, ["test", "ref"])

    s = form.slider("gamma")
    box = form.editor("gamma")
    assert isinstance(s, QSlider) and isinstance(box, QDoubleSpinBox)
    assert edits == [], "建表本身不可以噴 param_edited"

    # 滑桿 -> 數字框 -> param_edited
    s.setValue(s.minimum())
    assert box.value() == pytest.approx(0.1)
    assert edits[-1] == ("gamma", pytest.approx(0.1))
    s.setValue(s.maximum())
    assert box.value() == pytest.approx(5.0)

    # 數字框 -> 滑桿（反向也要跟上，而且不可以互相回寫到爆掉）
    box.setValue(1.0)
    assert s.value() == pytest.approx(s.maximum() * (1.0 - 0.1) / (5.0 - 0.1),
                                      abs=2)
    assert len([e for e in edits if e[0] == "gamma"]) == 3

    # 整數參數也有；沒有上下界的就沒有（硬給一支只會誤導）
    form.set_step(_describe("snr_map"), {}, ["test", "diff"])
    assert isinstance(form.slider("window"), QSlider)
    assert (form.slider("window").minimum(),
            form.slider("window").maximum()) == (5, 201)
    form.set_step(_describe("load_patch"), {}, [])
    assert form.slider("channels") is None


def test_curve_editor_is_wysiwyg_and_feeds_the_recipe(qapp):
    """曲線編輯器畫的線 = 影像上套的線（同一個 core 函式）。

    UI 自己再實作一份插值太容易了，而那會讓使用者看到的和跑出來的不一樣。
    """
    from d4t.core.algo.curve import curve_lut
    from d4t.core.steps.tone import apply_curve

    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))
    form.set_step(_describe("tone"), {}, ["test", "ref"])

    field = form.editor("curve")
    assert isinstance(field, widgets_mod.CurveField)
    assert field.text() == "0,0; 1,1" and field.is_identity() is True

    # 拉一個點 -> 值進 param_edited（也就是進 recipe）
    field.editor._insert(0.4, 0.7)
    assert edits[-1] == ("curve", "0,0; 0.4,0.7; 1,1")
    assert field.is_identity() is False

    # 畫面上的曲線就是 core 的 LUT
    lut = curve_lut(field.editor.points(), 256)
    assert lut[0] == pytest.approx(0.0) and lut[-1] == pytest.approx(1.0)
    assert np.all(np.diff(lut) >= -1e-12), "保單調：不可以 overshoot 出假的暗環"
    assert lut[int(0.4 * 255)] > 0.4, "把中間點往上拉，中間就要變亮"

    # 而且引擎吃得下同一個字串
    img = np.linspace(0, 255, 64, dtype=np.uint8).reshape(8, 8)
    out = apply_curve(img, field.text())
    assert out.dtype == img.dtype and out[4, 0] > img[4, 0]

    # 打字打到一半的不合法字串不可以把辛苦拉的線清掉
    before = field.text()
    assert field.set_text("0,0; 0.4,") is False
    assert field.text() == before

    field.editor.reset()
    assert field.text() == "0,0; 1,1"


def test_a_drawn_curve_visibly_takes_over_from_the_gamma_slider(qapp):
    """規則寫在 steps/tone.py（曲線接管 gamma），這裡驗**使用者看得見**。

    不然他會拉了曲線又去動 gamma，然後以為 gamma 壞了。
    """
    form = widgets_mod.ParamForm()
    form.set_step(_describe("tone"), {}, ["test", "ref"])
    gamma_row = form._rows["gamma"]
    assert gamma_row.property("dimmed") == "false"

    form.editor("curve").editor._insert(0.3, 0.6)
    assert gamma_row.property("dimmed") == "true"
    assert "custom curve" in form.hint_text("gamma")
    # 調淡不是鎖死 —— 使用者可能只是想比較兩種做法
    assert gamma_row.isEnabled() is True

    form.editor("curve").editor.reset()
    assert gamma_row.property("dimmed") == "false"
    assert form.hint_text("gamma") == gamma_row.spec["help"]


def test_curve_points_can_be_dragged_and_the_ends_stay_put(qapp):
    """頭尾的 x 鎖在 0 和 1 —— 曲線必須覆蓋整個灰階範圍，少一段就沒定義。"""
    ed = widgets_mod.CurveEditor()
    ed.resize(200, 200)
    seen = []
    ed.curve_changed.connect(seen.append)

    idx = ed._insert(0.5, 0.5)
    assert idx == 1 and len(ed.points()) == 3

    def _drag(px_from, px_to):
        _mouse(ed, QEvent.MouseButtonPress, px_from, Qt.LeftButton)
        _mouse(ed, QEvent.MouseMove, px_to, Qt.LeftButton)
        _mouse(ed, QEvent.MouseButtonRelease, px_to, Qt.LeftButton, Qt.NoButton)

    # 拖中間那點往上
    _drag(ed._to_px(0.5, 0.5), ed._to_px(0.5, 0.85))
    assert ed.points()[1][1] > 0.7
    assert seen, "拖曳要發訊號，不然參數不會進 recipe"

    # 拖最後一點：y 動得了，x 不動
    _drag(ed._to_px(1.0, 1.0), ed._to_px(0.6, 0.6))
    assert ed.points()[-1][0] == pytest.approx(1.0)
    assert ed.points()[-1][1] < 0.9

    # 頭尾刪不掉，中間刪得掉
    ed._remove(0)
    ed._remove(len(ed.points()) - 1)
    assert len(ed.points()) == 3
    ed._remove(1)
    assert len(ed.points()) == 2


def test_param_form_bool_choice_and_str(qapp):
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))

    # bool -> QCheckBox（subtract.absolute 預設 True）
    form.set_step(_describe("subtract"), {}, ["test", "ref_aligned"])
    absolute = form.editor("absolute")
    assert isinstance(absolute, QCheckBox)
    assert absolute.isChecked() is True
    absolute.setChecked(False)
    assert edits[-1] == ("absolute", False)
    assert isinstance(edits[-1][1], bool)

    # choice -> 非可編輯 QComboBox，選項 = spec.choices
    edits.clear()
    desc = _describe("align")
    form.set_step(desc, {}, ["test", "ref"])
    method = form.editor("method")
    choices = [p for p in desc["params"] if p["name"] == "method"][0]["choices"]
    assert isinstance(method, QComboBox) and not method.isEditable()
    assert [method.itemText(i) for i in range(method.count())] == choices
    assert method.currentText() == "phase"
    method.setCurrentText("ncc")
    assert edits[-1] == ("method", "ncc")

    # int 有下限：search_radius 1..64
    radius = form.editor("search_radius")
    assert (radius.minimum(), radius.maximum()) == (1, 64)

    # str -> QLineEdit（load_patch.channels）
    edits.clear()
    form.set_step(_describe("load_patch"), {}, [])
    channels = form.editor("channels")
    assert isinstance(channels, QLineEdit)
    assert channels.text() == "auto"
    channels.setText("test,ref")
    assert edits[-1] == ("channels", "test,ref")
    assert isinstance(edits[-1][1], str)


def test_param_form_show_and_clear_errors(qapp):
    form = widgets_mod.ParamForm()
    desc = _describe("snr_map")
    form.set_step(desc, {}, ["diff"])
    help_text = [p for p in desc["params"] if p["name"] == "window"][0]["help"]

    assert form.has_error("window") is False
    form.show_error("window", "參數 'window'：4 低於下限 5")
    assert form.has_error("window") is True
    assert "低於下限 5" in form.hint_text("window")
    assert "color:%s" % theme_mod.TOKENS["danger_text"] in \
        form._rows["window"].hint.styleSheet()
    assert form.has_error("out") is False        # 其他列不受影響

    form.clear_errors()
    assert form.has_error("window") is False
    assert form.hint_text("window") == help_text


def test_param_form_empty_state(qapp):
    form = widgets_mod.ParamForm()
    form.set_step(None, {}, [])
    assert form.param_names() == []
    assert form.step_key() is None


# --------------------------------------------------------------------------- #
# 3. LibraryPanel
# --------------------------------------------------------------------------- #
def test_library_panel_groups_and_double_click(qapp):
    """F7-3：卡片庫改依**流程階段**分組（不是依 category 的影像／算法）。"""
    panel = widgets_mod.LibraryPanel()
    steps = _steps()
    panel.set_steps(steps)

    # 標題與順序的**唯一出處**是 LibraryPanel.GROUPS（它自己再對齊
    # step.GROUP_ORDER，由 tests/test_ui_f16_stages.py 鎖住）。這裡以前抄了
    # 第四份，於是 F16 加兩段時它是「忘了改」的那一份。
    assert panel.section_titles() == [
        t for _gid, t, _sub in widgets_mod.LibraryPanel.GROUPS]
    assert set(panel.step_keys()) == {s["key"] for s in steps}

    # 每張卡都被歸進宣告的那一段
    by_group = {}
    for s_ in steps:
        by_group.setdefault(s_["group"], set()).add(s_["key"])
    assert "load_patch" in by_group["input"]
    assert {"subtract", "align"} <= by_group["compare"]
    assert "roi_cross" in by_group["region"]
    assert {"glv_stats", "cd_measure"} <= by_group["measure"]

    # 空的段落要留一行提示（registry 目前沒有 adc 卡片）
    empties = [lbl for lbl in panel.findChildren(QLabel)
               if lbl.objectName() == "libEmpty"]
    assert len(empties) == sum(
        1 for g, _t, _s in panel.GROUPS if not by_group.get(g))

    got = []
    panel.add_requested.connect(got.append)

    snr_desc = _describe("snr_map")
    item = panel.entry("snr_map")
    assert item is not None
    assert item.label.text() == snr_desc["label"]
    assert item.toolTip() == snr_desc["help"]             # help 掛成 tooltip
    QTest.mouseDClick(item, Qt.LeftButton)
    assert got == ["snr_map"]

    # 另一條路：hover 出現的「Add」按鈕
    other = panel.entry("align")
    assert other.add_button.text() == "Add"
    other.add_button.click()
    assert got == ["snr_map", "align"]

    # 重新 set_steps 不會留下舊項目
    panel.set_steps([s_ for s_ in steps if s_["group"] == "compare"])
    assert panel.entry("snr_map") is None
    assert panel.entry("align") is not None


def test_library_search_filters_cards_and_hides_empty_sections(qapp):
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)                 # 全部收起來，只靠搜尋
    everything = set(panel.step_keys())

    panel.set_query("snr")
    hit = set(panel.visible_step_keys())
    # `snr_map`（Z-map）的說明裡有 SNR；Gray level 的 `snr` 是它的比較項之一。
    # （`roi_snr` 那張卡在 2026-08-21 刪掉了 —— 使用者要的是 GL 比對的 SNR。）
    assert {"snr_map", "glv_stats"} <= hit
    assert "denoise" not in hit
    assert "Input" not in panel.visible_section_titles(), \
        "整組都沒命中的區塊標題要一起收起來"

    # 多個詞是 AND；說明文字也在搜尋範圍內
    panel.set_query("gray percentiles")
    assert set(panel.visible_step_keys()) == {"glv_stats"}

    # F7-7：清空搜尋之後回到 rail 的狀態（這裡是全部收起來），不是全部攤開
    panel.set_query("")
    assert panel.open_group() is None
    assert panel.visible_step_keys() == []

    panel.toggle_group("enhance")
    assert set(panel.visible_step_keys()) < everything
    assert panel.visible_section_titles() == ["Enhance"]


def test_library_badges_unmet_prerequisites_but_still_allows_adding(qapp):
    """前置條件沒滿足 → 標 ``needs …`` 並調淡，**但不擋著不給加**。

    卡片庫的順序不是執行順序：使用者可能先放卡再補上游。擋住只會讓人以為壞了。
    """
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    # 還不知道上游有什麼 -> 一個 badge 都不該出現（別在空流程上嚇人）
    assert not [k for k in panel.step_keys() if panel.entry(k).badge_text()]

    panel.set_available_streams(["test", "ref"])
    assert panel.entry("snr_map").badge_text() == "needs diff"
    # subtract 2026-08-14 起預設吃 ref（patch 本來就對齊）—— 不再有假前置
    assert panel.entry("subtract").badge_text() == ""
    assert panel.entry("denoise").badge_text() == ""      # 只讀 test，滿足了

    got = []
    panel.add_requested.connect(got.append)
    panel.entry("snr_map").add_button.click()
    assert got == ["snr_map"], "有 badge 的卡仍然要加得進去"

    # 上游補齊之後 badge 要消失
    panel.set_available_streams(["test", "ref", "ref_aligned", "diff"])
    assert panel.entry("snr_map").badge_text() == ""
    assert panel.entry("subtract").badge_text() == ""


def test_group_icons_are_painted_not_files(qapp):
    """icon 一律 QPainter 畫 —— repo 有「只放純文字檔」的不變量。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    # 每個階段有兩個 icon：rail 上的大顆 + 展開區的小標題；
    # 再加 rail 底部的搜尋鈕（它不是流程階段，所以不在 stage_buttons 裡）
    icons = panel.findChildren(widgets_mod.GroupIcon)
    assert len(icons) == 2 * len(panel.GROUPS) + 1
    assert len(panel.stage_buttons) == len(panel.GROUPS)
    assert panel.search_button.group == "search"
    assert all(i.width() > 0 and i.height() > 0 for i in icons)

    # 換主題之後 icon 要跟著換色
    before = [i.color for i in icons]
    theme_mod.set_theme("dark")
    try:
        panel.refresh_colors()
        assert [i.color for i in icons] != before
    finally:
        theme_mod.set_theme("light")
        panel.refresh_colors()


def test_every_stage_icon_is_a_different_shape(qapp):
    """八個階段要有八個**看得出差別**的圖示（F17）。

    這一條以前不存在，於是 ``draw_group_icon`` 的 ``else`` 分支（一個打勾）
    同時服務 Algo、ADC、Output 三段 —— rail 上由上而下掃過去，最後三顆一模一樣。
    顏色也救不了：F16 那兩段刻意畫得淡（見 ``theme`` 的說明），三個打勾裡有兩個
    是低彩度的，實際看起來就是「同一個圖示重複三次」。

    測法是**量畫出來的畫素**，跟 ``test_ui_f7_23_buttons`` 同一種：斷言
    「有沒有寫 elif」沒有用，因為兩段各寫各的、畫出同一個形狀也會過。
    這裡比的是 15 px（區塊標題與畫布節點磚用的尺寸）—— 大顆的 rail 圖示只會
    更容易分辨，會先在小的這一邊糊掉。
    """
    from PySide6.QtGui import QColor, QPainter, QPixmap

    size = 15
    ink = {}
    for gid, _t, _s in widgets_mod.LibraryPanel.GROUPS:
        pm = QPixmap(size, size)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        widgets_mod.draw_group_icon(p, gid, "#000000", float(size))
        p.end()
        img = pm.toImage()
        ink[gid] = [img.pixelColor(x, y).value() < 200
                    for y in range(size) for x in range(size)]
        assert sum(ink[gid]) >= 12, "%s 幾乎沒畫出東西" % gid

    # 差 24 個畫素 ≈ 15×15 的一成。最接近的一對是 Input / Output（35 個）——
    # 那一對**刻意**相像：同樣是托盤加箭頭，差別在箭頭往哪走，跟 glyph 的
    # save / export 是同一種對比。其餘每一對都差得更多。
    too_close = []
    keys = list(ink)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            d = sum(1 for x, y in zip(ink[a], ink[b]) if x != y)
            if d < 24:
                too_close.append("%s 與 %s 只差 %d 個畫素" % (a, b, d))
    assert not too_close, "這幾對圖示看起來是同一個：\n  " + "\n  ".join(too_close)


# --------------------------------------------------------------------------- #
# 3b. MetricChips（F18）
# --------------------------------------------------------------------------- #
def _metric_ink(size=19):
    """每一顆統計量小圖畫出來的「有沒有墨」點陣（給下面兩條測試共用）。"""
    from PySide6.QtGui import QColor, QPainter, QPixmap

    out = {}
    for name in widgets_mod.METRIC_GLYPHS:
        pm = QPixmap(size, size)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        widgets_mod.draw_metric_glyph(p, name, float(size), "#000000", "#bbbbbb")
        p.end()
        img = pm.toImage()
        out[name] = [img.pixelColor(x, y).value() < 200
                     for y in range(size) for x in range(size)]
    return out


def test_every_metric_glyph_is_a_different_shape(qapp):
    """十五張統計量小圖要在 **19 px**（膠囊裡的尺寸）下兩兩分得開。

    第一版有六顆是廢的：``mean`` 只是「``median`` 沒填色」、``trimmed`` 的虛線
    在這個尺寸下整條不見、``skew`` 的箭頭搶戲而不對稱的山根本看不出來、
    ``percentile`` 跟 ``median`` 幾乎一樣。那些都是 render 出來逐顆看才發現的
    —— 斷言「有沒有寫 elif」不會發現任何一個。
    """
    import pytest as _pytest

    ink = _metric_ink()
    blank = [n for n, m in ink.items() if sum(m) < 12]
    assert not blank, "這些小圖畫出來幾乎是空的：%s" % ", ".join(blank)

    too_close = []
    names = list(ink)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = sum(1 for x, y in zip(ink[a], ink[b]) if x != y)
            if d < 20:
                too_close.append("%s 與 %s 只差 %d 個畫素" % (a, b, d))
    assert not too_close, "這幾對小圖看起來是同一個：\n  " + "\n  ".join(too_close)

    from PySide6.QtGui import QPainter, QPixmap
    with _pytest.raises(ValueError):
        pm = QPixmap(19, 19)
        p = QPainter(pm)
        try:
            widgets_mod.draw_metric_glyph(p, "no_such", 19.0, "#000", "#888")
        finally:
            p.end()


def test_every_statistic_the_card_offers_has_a_face(qapp):
    """引擎說「有哪些」，UI 說「長什麼樣」—— 兩份不准漂開。

    卡片多宣告一顆統計量而 UI 沒登記，畫出來會是一顆沒有分群、標籤是原始
    id（``glv_kurt``）的膠囊 —— 跑得完、看得到、而且醜，也就是不會有人回報。
    """
    from d4t.core.steps.glv_stats import METRIC_CHOICES

    for mid in METRIC_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and not label.startswith("glv_"), mid
        assert glyph in widgets_mod.METRIC_GLYPHS, mid

    # 手寫 recipe 的那三種參數化 id 也答得出來（它們不在 METRIC_GROUPS 裡）
    assert widgets_mod.metric_face("glv_q37") == ("Ends", "P37", "percentile")
    assert widgets_mod.metric_face("glv_trim05")[2] == "trimmed"
    assert widgets_mod.metric_face("glv_above200")[0] == "Counts"


def test_every_report_metric_the_card_offers_has_a_face(qapp):
    """Report 那一格跟 Statistics 同一條規矩（F18 補課第二輪，2026-08-21）。

    使用者：「我覺得 Report 要有更多統計量可以量」。多的那五顆一樣要有分群、
    短標籤與小圖 —— 沒有的話它們會是一排原始 id 的膠囊排在漂亮的那幾顆旁邊。
    """
    from d4t.core.steps.glv_stats import COMPARE_CHOICES

    groups = set()
    for mid in COMPARE_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and glyph in widgets_mod.METRIC_GLYPHS, mid
        groups.add(group)
    # **「哪幾個需要參照的格子」要在畫面上分得出來** —— 那是「為什麼我的 snr
    # 是空的」唯一的線索。
    assert groups == {"Difference", "Vs boxes", "Distributions"}
    assert widgets_mod.metric_face("pct_rank")[0] == "Vs boxes"


def test_a_hidden_metric_is_still_shown_when_a_recipe_has_it(qapp):
    """收起來 ≠ 刪掉（使用者 2026-08-21：「請幫我將這些收起來」）。

    卡片庫上沒有那顆膠囊，但舊 recipe 帶著它進來的時候要列出來並且勾著 ——
    「看不到就被靜靜刪掉」是這個 widget 從 `MultiChoicePicker` 繼承來的老規矩。
    """
    from d4t.core.steps.glv_stats import (COMPARE_CHOICES, HIDDEN_METRICS,
                                          HIDDEN_COMPARE_METRICS,
                                          METRIC_CHOICES)

    for mid in HIDDEN_METRICS:
        assert mid not in METRIC_CHOICES
    for mid in HIDDEN_COMPARE_METRICS:
        assert mid not in COMPARE_CHOICES

    w = widgets_mod.MetricChips(METRIC_CHOICES, "glv_median,glv_entropy")
    assert w.chip("glv_entropy") is not None
    assert w.chip("glv_entropy").is_checked()
    assert "glv_entropy" in w.text()
    # 而且它們照樣有臉（收起來的只有清單上那一顆膠囊）
    assert widgets_mod.metric_face("glv_kurt")[0] == "Shape"
    assert widgets_mod.metric_face("percent")[0] == "Difference"

    c = widgets_mod.MetricChips(COMPARE_CHOICES, "delta,percent")
    assert c.chip("percent") is not None and c.chip("percent").is_checked()


def test_the_group_column_fits_the_longest_group_name(qapp):
    """群名那一欄的寬度**由最長的群名決定**，不是一個寫死的 46 px。

    寫死的那個數字剛好裝得下 Statistics 的五個群（Center…Counts），所以
    Report 分成三群的那一刻，畫面上是「ifference」與「ributions」——
    一個切掉了頭的字，而不是一個看起來就壞掉的版面。
    """
    from PySide6.QtWidgets import QLabel

    from d4t.core.steps.glv_stats import COMPARE_CHOICES

    w = widgets_mod.MetricChips(list(COMPARE_CHOICES), "delta,snr")
    seen = {}
    for lbl in w.findChildren(QLabel):
        if lbl.objectName() == "metricGroup" and lbl.text():
            seen[lbl.text()] = lbl
    assert "Distributions" in seen, "群名沒有印出來"
    for text, lbl in seen.items():
        need = lbl.fontMetrics().horizontalAdvance(text)
        assert lbl.width() >= need, "%s 被切掉了（%d < %d）" % (
            text, lbl.width(), need)


def test_metric_chips_round_trip_the_recipe_string(qapp):
    """值的格式跟 ``multi_choice`` 一字不差 —— 換掉的只有長相。"""
    from d4t.core.steps.glv_stats import DEFAULT_METRICS, METRIC_CHOICES

    seen = []
    w = widgets_mod.MetricChips(METRIC_CHOICES, DEFAULT_METRICS)
    w.changed.connect(seen.append)
    assert w.text() == DEFAULT_METRICS
    assert w.picked() == ["glv_median", "glv_mad", "glv_min", "glv_max"]

    w.chip("glv_mean").click()
    assert "glv_mean" in w.picked() and seen[-1] == w.text()
    w.chip("glv_mean").click()
    assert "glv_mean" not in w.picked()

    # 順序＝畫面上的順序，**不是點選的順序** —— 同一組勾選每次都要產生同一個
    # 字串，不然一份 recipe 會因為使用者點的先後而長得不一樣（而它進得了
    # 快取簽章）。
    w.set_text("glv_max,glv_median")
    assert w.text() == "glv_median,glv_max"

    # 「不是 metric chip 的那幾顆」不算進值裡（+ Percentile… 是動作）
    adders = [c for c in w.findChildren(widgets_mod._MetricChip) if c.adder]
    assert adders, "應該要有『再加一顆』的膠囊"
    assert all(a.mid not in w.text() for a in adders)


def test_a_hand_written_statistic_is_shown_and_stays_ticked(qapp):
    """recipe 帶進來、清單上沒有的值要列出來並勾著。

    看不到就被靜靜刪掉，是最糟的一種「幫忙」—— `MultiChoicePicker` 的老規矩，
    換了長相之後仍然要成立。
    """
    from d4t.core.steps.glv_stats import METRIC_CHOICES

    w = widgets_mod.MetricChips(METRIC_CHOICES, "glv_median,glv_q37,glv_trim05")
    # 順序是**畫面上的**（Center 那一群在 Ends 前面），不是使用者列的順序 ——
    # 見 `MetricChips.text` 為什麼那件事必須是穩定的。
    assert w.text() == "glv_median,glv_trim05,glv_q37"
    assert w.chip("glv_q37") is not None and w.chip("glv_q37").is_checked()
    assert w.chip("glv_trim05").label == "Trimmed 5%"


def test_all_three_metric_fields_on_the_gray_level_card_are_chips(qapp):
    """**Statistics、Compare their 與 Report 是同一種膠囊**（F18 補課）。

    使用者第一輪：「Compare 跟 absolute 一樣重要，而且它的 Metric 面板 UI 也
    沒有 Statistics 那麼漂亮，我覺得可以改成切換式」；第二輪：「Compare their
    只能單參數嗎？我不能一次選擇 report glv_median 或 glv_pn 的資訊嗎？」——
    後者讓那一格從下拉變成同一種膠囊（值仍然是逗號分隔，所以不必遷移）。
    """
    form = widgets_mod.ParamForm()
    form.set_step(_describe("glv_stats"),
                  {"metrics": "glv_median,glv_mad",
                   "reference": "another region",
                   "stat": "glv_median,glv_q90",
                   "compare_metrics": "delta,snr"},
                  ["test", "ref"])
    chips = {c.text() for c in form.findChildren(widgets_mod.MetricChips)}
    assert chips == {"glv_median,glv_mad", "glv_median,glv_q90", "delta,snr"}
    # 舊的勾選網格在這張卡上一個都不剩
    assert not [g for g in form.findChildren(widgets_mod.MultiChoicePicker)
                if g.isVisibleTo(form)]


def test_the_compare_chips_do_not_offer_to_add_a_percentile(qapp):
    """「+ Percentile…」是 GLV 統計量專屬的動作。

    在「跟誰比」那一格長出它，會是一顆按了就加出一個那張表不認得的值的鈕。
    """
    from d4t.core.steps.glv_stats import COMPARE_CHOICES

    w = widgets_mod.MetricChips(list(COMPARE_CHOICES), "delta,snr")
    assert set(w.choice_names()) == set(COMPARE_CHOICES)
    assert not [c for c in w.findChildren(widgets_mod._MetricChip) if c.adder]
    assert widgets_mod.metric_face("snr") == ("Vs boxes", "SNR", "snr")

    # Statistics 那一格照樣有
    from d4t.core.steps.glv_stats import METRIC_CHOICES
    g = widgets_mod.MetricChips(METRIC_CHOICES, "glv_median")
    assert [c for c in g.findChildren(widgets_mod._MetricChip) if c.adder]


# --------------------------------------------------------------------------- #
# 4. PipelinePanel
# --------------------------------------------------------------------------- #
# （PipelinePanel 的兩支測試連同那個 widget 一起刪掉了 —— 見下面的說明）
#
# 它是 M3 的直式節點清單，F7-6 的畫布把它整個取代掉了，之後 studio.py 只剩一行
# import、從來沒有實例化過。留著的代價不是那 240 行程式碼，是**每一輪主題工作
# 都要繞過它**：F7-23 第三輪把三個元件的 stylesheet 搬進 QSS 時，`nodeCard` 與
# `scoreCard` 被判為「顏色依 category 算出來、該留在 widget」而放過 —— 那個判斷
# 本身沒錯，錯的是它們根本不在畫面上。畫布那邊的對應行為由
# `tests/test_ui_canvas.py` 蓋著（選取、訊號、重畫、換膚）。
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# 5. HistogramWidget
# --------------------------------------------------------------------------- #
def test_histogram_data_threshold_and_drag(qapp):
    hist = widgets_mod.HistogramWidget()
    hist.resize(420, 220)

    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
    edges, counts = vm_mod.histogram(scores, n_bins=8)
    hist.set_data(edges, counts)
    assert hist.has_data()

    hist.set_threshold(3.0)
    assert hist.threshold() == pytest.approx(3.0)
    # set_threshold 是程式設定，不該回頭發訊號
    changed, committed = [], []
    hist.threshold_changed.connect(changed.append)
    hist.threshold_committed.connect(committed.append)
    hist.set_threshold(2.5)
    assert changed == [] and committed == []

    rect = hist._plot_rect()
    y = rect.center().y()
    start = QPointF(rect.left() + 20, y)
    mid = QPointF(rect.center().x(), y)
    end = QPointF(rect.right() - 20, y)

    _mouse(hist, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, mid, Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)

    assert len(changed) >= 3, "拖曳過程要連續發 threshold_changed"
    assert len(committed) == 1, "放開才 commit 一次"
    lo, hi = edges[0], edges[-1]
    for v in changed:
        assert lo <= v <= hi
    assert changed[0] < changed[-1]                      # 由左拖到右
    assert committed[0] == pytest.approx(changed[-1])
    assert hist.threshold() == pytest.approx(committed[0])
    assert hist.threshold() == pytest.approx(hi, abs=(hi - lo) * 0.2)

    # 拖出範圍也要夾在 [lo, hi] 內
    changed.clear()
    _mouse(hist, QEvent.MouseButtonPress, QPointF(rect.right() - 1, y),
           Qt.LeftButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseMove, QPointF(rect.right() + 500, y),
           Qt.NoButton, Qt.LeftButton)
    _mouse(hist, QEvent.MouseButtonRelease, QPointF(rect.right() + 500, y),
           Qt.LeftButton, Qt.NoButton)
    assert hist.threshold() == pytest.approx(hi)
    assert all(lo <= v <= hi for v in changed)


def test_histogram_bin_summary_tooltip_and_empty(qapp):
    hist = widgets_mod.HistogramWidget()
    hist.resize(420, 220)

    # 空狀態
    assert hist.has_data() is False
    assert hist.bin_summary_text() == ""
    hist.set_data([0.0, 1.0], [0])                       # viewmodel 的空回傳
    assert hist.has_data() is False

    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
    edges, counts = vm_mod.histogram(scores, n_bins=8)
    hist.set_data(edges, counts)

    hist.set_bin_summary(vm_mod.rebin(scores, 3.0))
    text = hist.bin_summary_text()
    assert text.startswith("bin 0=") and "bin 1=" in text
    assert text == "bin 0=5   bin 1=5"

    # hover 某根長條 -> tooltip「score a–b：N 顆」
    rect = hist._plot_rect()
    bw = rect.width() / len(counts)
    idx = next(i for i, c in enumerate(counts) if c > 0)
    _mouse(hist, QEvent.MouseMove,
           QPointF(rect.left() + bw * (idx + 0.5), rect.bottom() - 4))
    tip = hist.toolTip()
    assert "score" in tip and "defects" in tip and "–" in tip
    assert tip.endswith("%d defects" % counts[idx])

    hist.set_bin_summary({})
    assert hist.bin_summary_text() == ""


# --------------------------------------------------------------------------- #
# 6. FeatureTable / VerdictChip
# --------------------------------------------------------------------------- #
def test_feature_table_formatting_and_score_pinned_last(qapp):
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"score": 8.5, "snr_peak": 4.23456, "blob_area": 12.0,
         "glv_mean": 128.0, "tiny": 0.00002},
        highlight={"snr_peak"},
    )
    assert table.columnCount() == 3
    assert [table.horizontalHeaderItem(i).text() for i in range(3)] == [
        "Feature", "What it is", "Value"]

    names = table.feature_names()
    assert names[-1] == "score"                          # score 釘最後
    assert set(names) == {"score", "snr_peak", "blob_area", "glv_mean", "tiny"}

    assert table.value_text("blob_area") == "12"         # 乾淨整數
    assert table.value_text("glv_mean") == "128"
    assert table.value_text("snr_peak") == "4.235"       # 3 位小數
    assert table.value_text("tiny") == "2e-05"           # 極小值不要變成 0.000
    assert table.value_text("score") == "8.500"

    score_row = names.index("score")
    assert table.item(score_row, 0).font().bold() is True
    assert table.item(score_row, 2).font().bold() is True

    hi_row = names.index("snr_peak")
    assert table.item(hi_row, 0).background().color().name() == \
        theme_mod.TOKENS["accent_bg"]

    table.set_features({})                               # 清空不該炸
    assert table.rowCount() == 0


def test_the_middle_column_says_what_each_feature_is(qapp):
    """橫向空間拿來**解釋名字**（F18 補課第三輪，2026-08-21）。

    使用者：「目前只有縱向空間被用到（橫向空間幾乎沒有：Feature 右側就只有
    Value 還到最右邊）」＋「絕對量的跟相對量的還是要分類好」。所以中間那一欄
    是「這是什麼」，而**兩種量用顏色分**。
    """
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"epi_glv_median": 128.0, "epi_cmp_delta_median": 23.4,
         "epi_cmp_overlap": 0.02, "epi_glv_pixels": 812.0},
        about={"epi_cmp_delta_median": "mg", "epi_cmp_overlap": "mg"})

    assert table.about_text("epi_glv_median") == "median(gray)"
    assert table.about_text("epi_glv_pixels") == "how many pixels counted"
    assert table.about_text("epi_cmp_delta_median") == \
        "Difference of median vs mg"
    # 不看 stat 的那兩個沒有「of …」那一段（`spread_ratio` 自己就帶底線 ——
    # 切最後一個底線的寫法會把它變成「spread 的 ratio」）
    assert table.about_text("epi_cmp_overlap") == "Overlap vs mg"

    names = table.feature_names()
    rel = names.index("epi_cmp_delta_median")
    abs_ = names.index("epi_glv_median")
    assert table.item(rel, 1).foreground().color().name() == \
        theme_mod.TOKENS["accent_active"]
    assert table.item(abs_, 1).foreground().color().name() == \
        theme_mod.TOKENS["text_hint"]
    table.deleteLater()


def test_a_feature_nobody_can_decode_gets_no_gloss(qapp):
    """別張卡寫的數字沒有這套命名規則 —— 那一格留白，不要瞎猜一句話。"""
    assert widgets_mod.feature_gloss("blob_area") == ("", "")
    assert widgets_mod.feature_gloss("score") == ("", "")


def test_absolute_comes_before_relative_inside_a_card(qapp):
    """交錯的話，那一段要一行一行讀才知道自己在看哪一種。"""
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"cmp_delta_mean": 1.0, "glv_median": 2.0, "cmp_snr_mean": 3.0,
         "glv_mad": 4.0},
        sections=[{"title": "Gray level", "color": "#bf7030",
                   "names": ["cmp_delta_mean", "glv_median", "cmp_snr_mean",
                             "glv_mad"]}])
    assert table.feature_names() == ["glv_median", "glv_mad",
                                     "cmp_delta_mean", "cmp_snr_mean"]
    table.deleteLater()


def test_verdict_chip(qapp):
    chip = widgets_mod.VerdictChip()
    assert chip.text() == "—" and chip.tone() == "neutral"

    chip.set_verdict(1)
    assert chip.text() == "bin 1 · ≥ threshold"
    assert chip.tone() == "good"
    assert theme_mod.TOKENS["chip_good_bg"] in chip.styleSheet()
    assert chip.verdict() == 1

    chip.set_verdict(0)
    assert chip.text() == "bin 0 · < threshold"
    assert chip.tone() == "bad"
    assert theme_mod.TOKENS["chip_bad_bg"] in chip.styleSheet()

    # is_real_style：bin 1 = 抓到真缺陷 = 壞消息（紅），bin 0 = 乾淨（綠）
    chip.set_verdict(1, is_real_style=True)
    assert chip.text() == "bin 1 · ≥ threshold" and chip.tone() == "bad"
    chip.set_verdict(0, is_real_style=True)
    assert chip.text() == "bin 0 · < threshold" and chip.tone() == "good"

    chip.set_verdict(None)
    assert chip.text() == "—" and chip.verdict() is None


# --------------------------------------------------------------------------- #
# 7. F7-2 換膚：切主題之後畫面上的東西不能少，也不能殘留舊色
# --------------------------------------------------------------------------- #
def test_studio_theme_toggle_keeps_everything_and_repaints(qapp):
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        cards_before = win.library.step_keys()
        assert theme_mod.current_theme() == "light"

        assert win.toggle_theme() == "dark"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
        assert win.library.step_keys() == cards_before, \
            "換膚會重建卡片庫 —— 內容不可以在過程中掉東西"
        assert qapp.styleSheet().find(theme_mod.PALETTES["dark"]["bg_page"]) >= 0

        assert win.toggle_theme() == "light"
        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["light"]["bg_page"]
    finally:
        win.close()
        theme_mod.apply_theme(qapp, "light")


# --------------------------------------------------------------------------- #
# 8. F7-7 左側 rail：先選階段，才展開裡面的卡片
# --------------------------------------------------------------------------- #
def test_stage_rail_drills_down_one_stage_at_a_time(qapp):
    """一開始就把 15 張卡攤開，正是「太瑣碎」的來源。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    assert len(panel.stage_buttons) == len(panel.GROUPS)
    # 每顆按鈕標出該段有幾張卡
    for gid, _t, _s in panel.GROUPS:
        n = sum(1 for d in _steps() if d["group"] == gid)
        assert panel.stage_buttons[gid].count.text() == ("" if n == 0 else str(n))

    panel.toggle_group("enhance")
    assert panel.open_group() == "enhance"
    assert panel.stage_buttons["enhance"].is_active() is True
    visible = set(panel.visible_step_keys())
    assert "tone" in visible and "subtract" not in visible, \
        "沒展開的階段不該出現在清單裡"

    # 一次只開一段
    panel.toggle_group("measure")
    assert panel.open_group() == "measure"
    assert panel.stage_buttons["enhance"].is_active() is False
    assert "glv_stats" in panel.visible_step_keys()

    # 點同一顆再一次 = 收起來
    panel.toggle_group("measure")
    assert panel.open_group() is None
    assert panel.visible_step_keys() == []


def test_every_stage_opens_at_the_same_height(qapp):
    """哪一段展開，卡片就從**同一個高度**開始（F17）。

    使用者原話：「點 Input 出來的選擇 card，跟點 Output 的高度不一樣」。
    收起來的那七段本來仍然各佔 8 px —— 一個藏起來的 widget 在父層 layout 裡是
    零，但一個**空的巢狀 layout 不是**，它的 contentsMargins 照算。於是
    Output（排第八）的標題被前面七段推下去 56 px，畫面上就是一條沒有東西的
    空白，而且高度隨著點哪一段變。

    量的是「標題離捲動區頂端多遠」，不是某一段的實作 —— 這樣未來不管卡片區
    怎麼重排，只要它又開始隨段數飄移，這條就會紅。
    """
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.resize(300, 500)
    panel.show()                                # 沒 show 過的話 layout 不會重排

    tops = {}
    panel.toggle_group(None)
    for gid, _t, _s in panel.GROUPS:
        panel.toggle_group(gid)
        qapp.processEvents()
        head = panel._headers[gid]
        host = head.parentWidget()
        tops[gid] = head.mapTo(host, head.rect().topLeft()).y()
        panel.toggle_group(gid)                 # 收回來，換下一段
    assert len(set(tops.values())) == 1, \
        "每一段展開時標題的位置不一樣：%r" % (tops,)


def test_search_still_reaches_across_collapsed_stages(qapp):
    """收起來的階段不該把搜尋擋住 —— 搜尋是「我不知道它在哪一段」時用的。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)
    assert panel.open_group() is None

    panel.set_query("tone")
    assert panel.visible_step_keys() == ["tone"]
    panel.set_query("")
    assert panel.visible_step_keys() == []


def test_rail_is_vertical_and_the_card_area_gives_its_width_back(qapp):
    """F7-8：rail 像工作列一樣由上而下，收起來時整欄只剩那條圖示條。

    寬度用 ``minimumWidth()`` 驗，不用 ``width()`` —— 沒 show 過的 widget
    幾何還沒生效，那會驗到一個假的數字。
    """
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())

    assert panel.rail.layout().__class__.__name__ == "QVBoxLayout"
    assert panel.rail.width() == panel.RAIL_W
    # 「圖示要大一點」：rail 上的 icon 明顯大於區塊標題的小 icon
    assert panel.stage_buttons["input"].icon._SIZE > widgets_mod.GroupIcon._SIZE

    seen = []
    panel.panel_toggled.connect(seen.append)

    panel.toggle_group(None)
    assert panel.panel_open() is False
    assert panel.minimumWidth() == panel.RAIL_W, "收起來就該把寬度還出去"

    panel.toggle_group("region")
    assert panel.panel_open() is True
    assert panel.minimumWidth() == panel.RAIL_W + panel.PANEL_W
    assert seen == [False, True]


def test_the_search_button_survives_collapsing_the_card_area(qapp):
    """搜尋框住在卡片區裡，卡片區收起來它也跟著不見 ——
    所以 rail 上必須留一顆放大鏡，不然搜尋就再也叫不出來了。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)
    assert panel.panel_open() is False

    panel.search_button.clicked.emit("search")
    assert panel.panel_open() is True, "按了放大鏡就要把卡片區帶回來"
    # 而且搜尋框真的可以打字（不是被留在隱藏的容器裡）
    assert panel.search.isVisibleTo(panel) is True
    panel.set_query("tone")
    assert panel.visible_step_keys() == ["tone"]


def test_rows_appear_and_disappear_with_the_method(qapp):
    """F7-20：``show_when`` 在畫面上真的生效，而且改下拉就立刻重算。

    藏起來而不是變淡，是因為兩者講的是不同的事：變淡（``_sync_curve_override``）
    是「這一格還在，只是現在沒作用」；藏起來是「這一格根本不是這張卡的一部分」。
    """
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("normalize").describe(), {}, ["test", "ref"])

    assert form._rows["p_low"].isVisibleTo(form) is True
    assert form._rows["tiles"].isVisibleTo(form) is False
    assert form._rows["reference"].isVisibleTo(form) is False

    form._emit("method", "local")
    assert form._rows["p_low"].isVisibleTo(form) is False
    assert form._rows["tiles"].isVisibleTo(form) is True

    form._emit("method", "match")
    assert form._rows["reference"].isVisibleTo(form) is True
    assert form._rows["tiles"].isVisibleTo(form) is False
    # streams / method 本身沒有 show_when，永遠在
    assert form._rows["streams"].isVisibleTo(form) is True


# --------------------------------------------------------------------------- #
# icon_choice —— 用圖取代下拉的英文句子（F11 Region-2）
# --------------------------------------------------------------------------- #
def test_every_icon_a_card_declares_really_exists(qapp):
    """`core` 不 import Qt，所以圖示名對不對只有**這一側**驗得了。

    對不上的症狀是 `IconButton` 直接 `ValueError: unknown icon` —— 那張卡整個
    打不開，而且是在使用者點下去的時候才炸。
    """
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import list_steps
    from d4t.ui.widgets import GLYPH_ICONS

    seen = 0
    for step in list_steps():
        for spec in step.describe()["params"]:
            for icon in (spec.get("icons") or []):
                seen += 1
                assert icon in GLYPH_ICONS, (step.key, spec["name"], icon)
    assert seen >= 11, "應該至少有 Profile 那三排（5+3+3）"


def test_an_icon_choice_row_is_buttons_not_a_dropdown(qapp):
    """使用者：「我不希望 profile 設定頁面那麼多文字，能用圖就用圖。」"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import IconButton, IconChoice, ParamForm

    form = ParamForm()
    form.set_step(get_step("roi_cross").describe(),
                  {"place": "crossing"}, ["ref", "test"])
    editor = form.editor("place")
    assert isinstance(editor, IconChoice)
    assert editor.text() == "crossing"

    buttons = editor.findChildren(IconButton)
    assert len(buttons) == 5                    # place 有五個選項
    for b in buttons:
        assert b.text() == ""                   # 一顆字都不放
        assert b.toolTip()                      # 說明退到 tooltip
    assert sum(1 for b in buttons if b.isChecked()) == 1


def test_picking_an_icon_emits_the_value(qapp):
    from d4t.ui.widgets import IconChoice

    got = []
    w = IconChoice(["a", "b"], ["fit", "tidy"], "a")
    w.changed.connect(got.append)
    w._pick("b")
    assert got == ["b"]
    assert w.text() == "b"


def test_a_value_nobody_recognises_lights_nothing(qapp):
    """手寫 recipe 打錯字的時候，**亮錯一顆比一顆都不亮更糟**。"""
    from d4t.ui.widgets import IconButton, IconChoice

    w = IconChoice(["a", "b"], ["fit", "tidy"], "zzz")
    assert w.text() == "zzz"                    # 不偷偷改掉他的值
    assert not any(b.isChecked() for b in w.findChildren(IconButton))


def test_the_profile_card_lost_three_dropdowns_of_english(qapp):
    from d4t.core.pipeline import get_step

    kinds = {p["name"]: p["type"]
             for p in get_step("roi_cross").describe()["params"]}
    assert kinds["place"] == "icon_choice"
    assert kinds["side"] == "icon_choice"
    assert kinds["fill_rule"] == "icon_choice"
