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
from tests.region_cards import (  # noqa: E402
    add_region_step, region_card,
)


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

    ⚠ **中性這一條只對 light 盤成立，而且那是使用者定調的**（2026-08-24）。
    dark 盤的大面積底色刻意帶一點冷色調（`#1e2127` = 30/33/39，RGB 跨距 9），
    所以下面那個 ``<= 8`` 套上去會紅 —— 差一。實測的感知彩度（CIE L*a*b*
    的 C*ab）：light 是 0.0–1.1、dark 是 3.8–5.1，而被否決掉的那種暖奶油底
    大約落在 3.7–7.5。**dark 與「玩具」在這個尺上分不開**，所以這條要求
    留給 light，不去調寬容差讓它同時涵蓋兩者（調寬之後它就再也擋不住暖奶油）。

    ⚠ 而且這裡讀的是 ``PALETTES["light"]``，**不是 ``TOKENS``**。
    ``TOKENS`` 裝著的是「現在這個行程剛好套著哪一組」—— 讀它等於讓這條測試
    的成敗由檔案順序決定，而那正是 CI 紅了三週的原因（見 conftest 那支
    `_the_theme_does_not_leak_into_the_next_test`）。**一條性質測試要自己
    講清楚它測的是哪一組值。**
    """
    light = theme_mod.PALETTES["light"]
    for key in ("bg_page", "bg_panel", "bg_surface", "toolbar", "statusbar"):
        r, g, b = _rgb(light[key])
        assert max(r, g, b) - min(r, g, b) <= 8, \
            "light 的 %s = %s 帶了明顯色相，大面積底色要中性" % (key, light[key])

    qss = theme_mod.build_stylesheet()
    for banned in ("box-shadow", "qlineargradient", "qradialgradient"):
        assert banned not in qss, "平面設計不用 %s" % banned


#: 上一條測試離開時的主題 —— 下一條測試用它驗 conftest 真的把主題收回來了。
_theme_before_the_switch = {}


def test_a_test_may_switch_the_theme(qapp):
    """故意把主題留在 dark 就收工 —— 下一條測試負責證明它沒有漏出去。"""
    _theme_before_the_switch["name"] = theme_mod.current_theme()
    theme_mod.set_theme("dark")
    assert theme_mod.current_theme() == "dark"


def test_and_the_next_test_does_not_inherit_it(qapp):
    """conftest 的 autouse fixture 要把上一條測試切走的主題收回來。

    這兩條合起來是那個「CI 紅三週」的迴歸測試：把 conftest 那支 fixture 拿掉，
    這一條會紅。它們**必須相鄰而且照順序**（pytest 在同一個檔案裡照定義順序跑），
    所以中間不要插東西。
    """
    assert theme_mod.current_theme() == _theme_before_the_switch["name"], \
        "上一條測試把主題留成 dark 了 —— conftest 的還原沒有生效"


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
def test_param_form_int_float_and_image_key(qapp):
    form = widgets_mod.ParamForm()
    edits = []
    form.param_edited.connect(lambda n, v: edits.append((n, v)))

    # `snr_map`（Z-map）2026-08-25 刪掉了 —— 這裡要的是同時有
    # **int（帶上下界）／float／image_key** 三種型別的一張卡，
    # 才驗得到「哪一種型別配哪一種編輯器」。`roi_reference` 是同一個形狀
    # （F30 起 Profile 是它的一個 method，`smooth` 那幾格在它上面）。
    desc = region_card("roi_cross").describe()
    streams = ["test", "ref", "diff", "ref_aligned"]
    form.set_step(desc, {"smooth": 31}, streams)

    # 每個 ParamSpec 都要有一列
    assert form.param_names() == [p["name"] for p in desc["params"]]
    # 建表本身不可以噴 param_edited
    assert edits == []

    smooth = form.editor("smooth")
    assert isinstance(smooth, QSpinBox)
    assert (smooth.minimum(), smooth.maximum()) == (1, 99)
    assert smooth.value() == 31
    smooth.setValue(41)
    assert edits[-1] == ("smooth", 41)
    assert isinstance(edits[-1][1], int)

    box = form.editor("box_size")
    assert isinstance(box, QDoubleSpinBox)
    assert box.value() == pytest.approx(5.0)
    box.setValue(4.5)
    assert edits[-1] == ("box_size", pytest.approx(4.5))
    assert isinstance(edits[-1][1], float)

    # image_key -> **接線插槽**（F9-6 的「來源只在畫布上決定」＋ F68 的插槽）。
    #
    # 以前這裡是可編輯的下拉，於是同一件事有兩個入口 —— 拉線會改它、下拉也會
    # 改它 —— 而兩邊很容易對不起來（使用者的原話是「他會很亂連」）。F9-6 把它
    # 變成唯讀顯示；F68 把它變成插槽：看得到現在接的是什麼、也挑得動，但**挑
    # 了之後走的是跟畫布拉線同一條路**（發訊號給 Studio），所以線仍然是唯一
    # 的儲存 —— 那格自己一個字都不改。
    from d4t.ui.wiring_slot import WiringSlot

    source = form.editor("source")
    assert isinstance(source, WiringSlot)
    assert source.text_value() == "ref", "要看得到現在接的是哪一條"
    assert source.toolTip().strip(), "講得出這一格是什麼（推廣鐵則）"
    n_before = len(edits)
    picked = []
    form.wire_requested.connect(lambda n, v: picked.append((n, v)))
    source.set_choices(["test", "ref"])
    source.wire_requested.emit("test")     # 就是選單那一下
    assert len(edits) == n_before, "插槽不可以自己發出參數變更（線才是真相）"
    assert picked == [("source", "test")], "要往上送給 Studio 去動線"

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
    form.set_step(_describe("align"), {}, ["test", "diff"])
    assert isinstance(form.slider("search_radius"), QSlider)
    assert (form.slider("search_radius").minimum(),
            form.slider("search_radius").maximum()) == (1, 64)
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

    # chip_choice -> 一排膠囊，值就是 spec.choices 裡那個字
    # （F68 第二輪之前這裡是 QComboBox —— 值的格式一字不差，換掉的只有長相）
    edits.clear()
    desc = _describe("align")
    form.set_step(desc, {}, ["test", "ref"])
    method = form.editor("method")
    choices = [p for p in desc["params"] if p["name"] == "method"][0]["choices"]
    assert isinstance(method, widgets_mod.ChoiceChips)
    assert [c.mid for c in method._chips] == choices
    assert method.text() == "phase"
    method.chip("ncc").click()
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
    desc = region_card("roi_cross").describe()
    form.set_step(desc, {}, ["diff"])
    help_text = [p for p in desc["params"]
                 if p["name"] == "smooth"][0]["help"]

    assert form.has_error("smooth") is False
    form.show_error("smooth", "參數 'smooth'：0 低於下限 1")
    assert form.has_error("smooth") is True
    assert "低於下限 1" in form.hint_text("smooth")
    assert "color:%s" % theme_mod.TOKENS["danger_text"] in \
        form._rows["smooth"].hint.styleSheet()
    assert form.has_error("source") is False     # 其他列不受影響

    form.clear_errors()
    assert form.has_error("smooth") is False
    assert form.hint_text("smooth") == help_text


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
    # F30：四張 Region 卡收成一張（`roi_reference` 的四個 method）。
    assert "roi_reference" in by_group["region"]
    assert {"glv_stats", "cd_measure"} <= by_group["measure"]

    # 空的段落要留一行提示（registry 目前沒有 adc 卡片）
    empties = [lbl for lbl in panel.findChildren(QLabel)
               if lbl.objectName() == "libEmpty"]
    assert len(empties) == sum(
        1 for g, _t, _s in panel.GROUPS if not by_group.get(g))

    got = []
    panel.add_requested.connect(got.append)

    snr_desc = _describe("glv_stats")
    item = panel.entry("glv_stats")
    assert item is not None
    assert item.label.text() == snr_desc["label"]
    assert item.toolTip() == snr_desc["help"]             # help 掛成 tooltip
    QTest.mouseDClick(item, Qt.LeftButton)
    assert got == ["glv_stats"]

    # 另一條路：hover 出現的「Add」按鈕
    other = panel.entry("align")
    assert other.add_button.text() == "Add"
    other.add_button.click()
    assert got == ["glv_stats", "align"]

    # 重新 set_steps 不會留下舊項目
    panel.set_steps([s_ for s_ in steps if s_["group"] == "compare"])
    assert panel.entry("glv_stats") is None
    assert panel.entry("align") is not None


def test_library_search_filters_cards_and_hides_empty_sections(qapp):
    panel = widgets_mod.LibraryPanel()
    panel.set_steps(_steps())
    panel.toggle_group(None)                 # 全部收起來，只靠搜尋
    everything = set(panel.step_keys())

    panel.set_query("snr")
    hit = set(panel.visible_step_keys())
    # GLV 卡的 `snr` 是它的比較項之一。（`roi_snr` 那張卡 2026-08-21 刪掉了
    # —— 使用者要的是 GL 比對的 SNR；`snr_map` / Z-map 2026-08-25 也刪掉了，
    # 所以現在整個卡片庫只剩這一張講得到 SNR。）
    assert {"glv_stats"} <= hit
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

    # ⚠ 這裡以前用 `snr_map`（預設吃 `diff`）當例子。它 2026-08-25 刪掉之後，
    # **卡片庫裡沒有任何一張卡預設讀 `diff`** 了 —— `diff` 仍然到處在用，
    # 但都是使用者接出來的。所以例子換成 `subtract`：只給 `test` 的時候，
    # 它缺的是 `ref`。
    panel.set_available_streams(["test"])
    assert panel.entry("subtract").badge_text() == "needs ref"
    assert panel.entry("denoise").badge_text() == ""      # 只讀 test，滿足了

    got = []
    panel.add_requested.connect(got.append)
    panel.entry("subtract").add_button.click()
    assert got == ["subtract"], "有 badge 的卡仍然要加得進去"

    # 上游補齊之後 badge 要消失
    panel.set_available_streams(["test", "ref", "ref_aligned", "diff"])
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
                   "reference_region": "mg",
                   "stat": "glv_median,glv_q90",
                   "compare_metrics": "delta,snr"},
                  ["test", "ref"])
    chips = {c.text() for c in form.findChildren(widgets_mod.MetricChips)
             # `judge` 的單選膠囊（MetricPick）是它的子類 —— 那一格是另一個
             # 參數型別（metric_choice），不在「三格多選」這一題裡。
             if not isinstance(c, widgets_mod.MetricPick)}
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

    # ⚠ **這幾條 2026-08-28 跟著改了（F52），而理由不是「數字剛好變了」。**
    #
    # 這張表以前走 `widgets._fmt_number` 自己那一份（整數捷徑 ＋ 3 位小數），
    # 而畫面上還有五個地方各自寫了一份 —— 同一個值印出來六種寫法。最傷的
    # 兩個：`99.995` 在結果表是 `100`、在這張表是 `99.995`（使用者會以為自己
    # 點錯顆）；`8.5` 在這裡是 `8.500`，那三位小數是**發明出來的精度**。
    #
    # 現在全 UI 走 `numbers.format_feature_value`：**有效位數**（5 位）＋
    # 整數不拖小數。所以 `8.5` 就是 `8.5`，`4.23456` 是 `4.2346`。
    from d4t.ui.numbers import format_feature_value

    assert table.value_text("blob_area") == "12"         # 乾淨整數
    assert table.value_text("glv_mean") == "128"
    assert table.value_text("snr_peak") == "4.2346"      # 5 位有效數字
    assert table.value_text("tiny") == "2e-05"           # 極小值不要變成 0.000
    assert table.value_text("score") == "8.5"            # 不再是 8.500
    # 而且是**同一支**印的 —— 值一樣可能只是巧合，這一行問的是出處。
    for name, value in (("snr_peak", 4.23456), ("score", 8.5),
                        ("tiny", 0.00002)):
        assert table.value_text(name) == format_feature_value(value)

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
    # 身分從**真的那張卡**宣告出來（資料同源）—— gloss 不再拆字串猜。
    from d4t.core.pipeline import get_step
    glv = get_step("glv_stats")
    p = glv.validate_params({
        "source": "test", "roi": "epi", "output_prefix": "epi",
        "metrics": "glv_median",
        "reference_region": "mg", "compare_metrics": "delta,overlap",
        "stat": "glv_median"})
    specs = {s.name: s for s in glv.resolve_feature_specs(p)}
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"epi_glv_median": 128.0, "epi_cmp_delta_median": 23.4,
         "epi_cmp_overlap": 0.02, "epi_glv_pixels": 812.0},
        about={"epi_cmp_delta_median": "mg", "epi_cmp_overlap": "mg"},
        specs=specs)

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


def test_a_feature_without_a_spec_gets_no_gloss(qapp):
    """沒有宣告身分的名字 —— 那一格留白，**不猜**（PR-3 起連 `glv_` 開頭
    的字串都不猜：說明只跟著 spec 走）。"""
    assert widgets_mod.feature_gloss("blob_area") == ("", "")
    assert widgets_mod.feature_gloss("score") == ("", "")
    assert widgets_mod.feature_gloss("glv_median") == ("", ""), \
        "名字長得像也不猜 —— 身分要卡片宣告"


def test_absolute_comes_before_relative_inside_a_card(qapp):
    """交錯的話，那一段要一行一行讀才知道自己在看哪一種。
    「哪個是相對量」看宣告的 ``family``，不再拆名字。"""
    from d4t.core.pipeline import get_step
    glv = get_step("glv_stats")
    p = glv.validate_params({
        "source": "test", "metrics": "glv_median,glv_mad",
        "reference_region": "mg",
        "compare_metrics": "delta,snr", "stat": "glv_mean"})
    specs = {s.name: s for s in glv.resolve_feature_specs(p)}
    table = widgets_mod.FeatureTable()
    table.set_features(
        {"cmp_delta_mean": 1.0, "glv_median": 2.0, "cmp_snr_mean": 3.0,
         "glv_mad": 4.0},
        sections=[{"title": "Gray level", "color": "#bf7030",
                   "names": ["cmp_delta_mean", "glv_median", "cmp_snr_mean",
                             "glv_mad"]}],
        specs=specs)
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
# 選項上的圖（F11 Region-2 起；F68 第二輪之後只剩膠囊這一種長相）
# --------------------------------------------------------------------------- #
def test_every_icon_a_card_declares_really_exists(qapp):
    """`core` 不 import Qt，所以圖示名對不對只有**這一側**驗得了。

    對不上的症狀是那顆膠囊直接 `ValueError: unknown icon` —— 那張卡整個
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
    assert seen >= 60, "每一格選項都要有圖（F68 第二輪把所有的下拉換掉了）"


def test_the_profile_card_lost_three_dropdowns_of_english(qapp):
    kinds = {p["name"]: p["type"]
             for p in region_card("roi_cross").describe()["params"]}
    assert kinds["place"] == "chip_choice"
    assert kinds["side"] == "chip_choice"
    assert kinds["fill_rule"] == "chip_choice"


def test_no_card_anywhere_still_shows_a_bare_dropdown(qapp):
    """使用者 2026-09-01：「我認為**設定區都要變成這樣** icon 膠囊 + 文字。」

    這一條蓋的是**每一張卡**，不是這一輪動到的那幾張 —— 新加的卡也躲不掉。
    """
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import list_steps

    plain = ["%s.%s" % (st.key, sp.name) for st in list_steps()
             for sp in st.params if sp.type in ("choice", "icon_choice")]
    assert not plain, "這幾格還是純下拉（或只有圖）：" + ", ".join(plain)


def test_a_spelled_out_value_keeps_the_words_the_card_wrote(qapp):
    """``a cell I mark myself`` 不可以被拼字函式改成「a cell **i** mark…」。

    `str.capitalize()` 會把其餘的字全部轉小寫 —— 而那是使用者看得到的一句話。
    """
    from d4t.ui.widgets import _spell

    assert _spell("a cell I mark myself") == "A cell I mark myself"
    assert _spell("beside_vertical") == "Beside vertical"


def test_a_value_that_spells_badly_gets_a_written_name(qapp):
    """``zscore`` / ``nlm`` / ``topn`` 是 recipe 的鍵，不是給人看的字。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    step = get_step("normalize")
    form.set_step(step.describe(),
                  {p.name: p.default for p in step.params}, ["test", "ref"])
    chips = form._rows["method"].editor
    assert chips.chip("zscore").label == "Z-score"
    assert chips.chip("glv_band").label == "GLV band"


def test_a_name_nobody_declared_is_caught_at_registration(qapp):
    """`choice_labels` 打錯一個值**不會叫**，它只是安靜地不生效。"""
    from d4t.core.pipeline.step import ParamError, ParamSpec

    with pytest.raises(ParamError):
        ParamSpec(name="x", type="chip_choice", default="a",
                  choices=["a", "b"], icons=["fit", "tidy"],
                  choice_labels={"c": "See"}, help="h")


# ---------------------------------------------------------------------------
# ChoiceChips：`chip_choice` 的膠囊（F68 第二輪 —— 設定欄那幾個下拉）
#
# 使用者 2026-09-01：「我希望設定欄這邊也是能像下方一樣膠囊 icon 配文字，
# 這樣 user 比較會有感覺。」
# ---------------------------------------------------------------------------
def test_the_settings_column_has_no_bare_dropdown_left_on_the_glv_card(qapp):
    """**這一條是那句話本身。** 加一個 `type="choice"` 的參數回去就會紅。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    plain = [p["name"] for p in get_step("glv_stats").describe()["params"]
             if p["type"] == "choice"]
    assert not plain, (
        "GLV 的設定欄又出現純下拉：%s —— 這張卡上的選項是膠囊（圖 + 字）"
        % ", ".join(plain))


def test_a_chip_choice_row_is_chips_not_a_dropdown(qapp):
    """而且**圖與字都在** —— 那正是它跟 `icon_choice` 的差別。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("glv_stats").describe(),
                  {"across_boxes": "each box"}, ["test"], [], {})
    row = form._rows.get("across_boxes")
    assert row is not None
    assert isinstance(row.editor, widgets_mod.ChoiceChips)
    assert not row.editor.findChildren(QComboBox), "下拉不該還在"
    assert row.editor.text() == "each box"

    chips = [row.editor.chip(v) for v in ("pooled", "each box")]
    assert all(c is not None for c in chips)
    assert [c.label for c in chips] == ["Pooled", "Each box"], \
        "字要留著：`each box` 是一個做法，圖只能當錨點"
    assert all(c.icon in widgets_mod.GLYPH_ICONS for c in chips)
    assert [c.is_checked() for c in chips] == [False, True]


def test_picking_a_chip_writes_exactly_what_the_dropdown_wrote(qapp):
    """值的格式跟 `choice` **一字不差** —— recipe JSON 不因為換了長相而變。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("glv_stats").describe(),
                  {"across_boxes": "pooled"}, ["test"], [], {})
    seen = []
    form.param_edited.connect(lambda n, v: seen.append((n, v)))
    form._rows["across_boxes"].editor.chip("each box").click()
    assert seen == [("across_boxes", "each box")]


def test_a_chip_row_never_ends_up_empty(qapp):
    """再點選中的那一顆不會把它關掉（同 MetricPick）：空值會被換回預設，
    看起來像「我點了但沒有反應」。"""
    seen = []
    w = widgets_mod.ChoiceChips(["a", "b"], ["fit", "tidy"], "a")
    w.changed.connect(seen.append)
    w.chip("a").click()
    assert w.text() == "a"
    assert w.chip("a").is_checked()
    assert seen == []


def test_a_chip_value_nobody_recognises_lights_nothing(qapp):
    """手寫 recipe 打錯字：**亮錯一顆比一顆都不亮更糟**（同 IconChoice）。"""
    w = widgets_mod.ChoiceChips(["a", "b"], ["fit", "tidy"], "zzz")
    assert w.text() == "zzz"                    # 不偷偷改掉他的值
    assert not any(c.is_checked() for c in (w.chip("a"), w.chip("b")))


def test_both_chip_families_are_the_same_pill(qapp):
    """統計量那一族與設定欄那一族**共用同一個外觀**。

    使用者要的是「像下方一樣」—— 兩份各畫各的話，第二份會慢慢漂走，而漂走的
    症狀是同一張卡上兩種高度、兩種字級的膠囊（這個 repo 記過三次抄第二份的
    代價）。
    """
    metrics = widgets_mod.MetricChips(["glv_median"], "glv_median")
    choices = widgets_mod.ChoiceChips(["a"], ["fit"], "a")
    a, b = metrics.chip("glv_median"), choices.chip("a")
    assert isinstance(a, widgets_mod._ChipBase)
    assert isinstance(b, widgets_mod._ChipBase)
    assert a.height() == b.height() == widgets_mod._ChipBase.H


def test_a_chip_choice_needs_one_icon_per_option(qapp):
    """少一個圖示 = 少一顆膠囊，而它不會叫 —— 所以擋在註冊的當下。"""
    from d4t.core.pipeline.step import ParamError, ParamSpec

    with pytest.raises(ParamError):
        ParamSpec(name="x", type="chip_choice", default="a",
                  choices=["a", "b"], icons=["fit"], help="h")


# ---------------------------------------------------------------------------
# MetricPick：`metric_choice` 的單選膠囊（F32 —— judge 那一格）
# ---------------------------------------------------------------------------
def test_metric_pick_is_single_select(qapp):
    """點一顆就把其他的關掉 —— 值永遠是**一個** id。"""
    from d4t.core.steps.glv_stats import METRIC_CHOICES

    seen = []
    w = widgets_mod.MetricPick(METRIC_CHOICES, "glv_median")
    w.changed.connect(seen.append)
    assert w.text() == "glv_median"
    w.chip("glv_max").click()
    assert w.text() == "glv_max"
    assert not w.chip("glv_median").is_checked()
    assert seen[-1] == "glv_max"


def test_metric_pick_never_ends_up_empty(qapp):
    """取消最後一顆 = 留下一個空值 —— 不准：把它勾回來、值不變、不發訊號。"""
    from d4t.core.steps.glv_stats import METRIC_CHOICES

    seen = []
    w = widgets_mod.MetricPick(METRIC_CHOICES, "glv_median")
    w.changed.connect(seen.append)
    w.chip("glv_median").click()          # 想取消唯一選著的那顆
    assert w.text() == "glv_median"
    assert w.chip("glv_median").is_checked()
    assert seen == []


def test_metric_pick_shows_a_hand_written_id(qapp):
    """recipe 帶進來、清單上沒有的 glv_q97 要列出來並選著（不是靜靜換掉）。"""
    from d4t.core.steps.glv_stats import METRIC_CHOICES

    w = widgets_mod.MetricPick(METRIC_CHOICES, "glv_q97")
    assert w.text() == "glv_q97"
    assert w.chip("glv_q97") is not None and w.chip("glv_q97").is_checked()
    # 「+ Percentile…」照樣長得出來 —— 自訂值的入口跟 Statistics 那格同一個
    adders = [c for c in w.findChildren(widgets_mod._MetricChip) if c.adder]
    assert adders


def test_the_judge_row_renders_as_a_metric_pick(qapp):
    """glv_stats 的 `judge` 在面板上是單選膠囊，不是顯示原始 id 的下拉。"""
    import d4t.core.steps  # noqa: F401
    from d4t.core.pipeline import get_step

    form = widgets_mod.ParamForm()
    form.set_step(get_step("glv_stats").describe(),
                  {"across_boxes": "each box"}, ["test"], [], {})
    row = form._rows.get("judge")
    assert row is not None
    assert isinstance(row.editor, widgets_mod.MetricPick)
    assert row.editor.text() == "glv_median"


# --------------------------------------------------------------------------- #
# 階段色與 metric 的「臉」（2026-08-27／F39-B3 搬過來）
#
# 三條階段色來自 `test_ui_f7_9_feedback.py`、兩條 metric-face 來自
# `test_ui_f19_cd.py`。它們問的都是**這個模組的性質**，不是那一輪交付了什麼：
# 每一段都有自己看得出來的顏色、色票是一套不是六個、卡片庫與畫布用同一個顏色、
# 每一個卡片宣告得出來的 metric 在 UI 都登記得到一張臉。
#
# ⚠ 這幾條**逐一套用到 registry / 卡片自己宣告的清單**（`GROUP_ORDER`、
# `REPORT_CHOICES`、`SIZE_CHOICES`），所以加一段、加一顆 metric 的人會自動被
# 納管 —— 那正是它們不該待在驗收檔裡的理由。
# --------------------------------------------------------------------------- #
#: **從 `GROUP_ORDER` 拿，不要在這裡再抄一份**（F16）。
#: 原本寫死六個字串，於是加一段的人要記得回來補 —— 忘了的話那條測試會
#: 「檢查了六個顏色」然後綠燈通過，而新那一段的顏色從來沒有被驗過。
def _stage_groups():
    from d4t.core.pipeline.step import GROUP_ORDER
    return tuple(GROUP_ORDER)


def _lab(hex_str):
    """sRGB hex -> CIE L*a*b*（D65）。用感知距離判「看不看得出不一樣」。

    RGB 的算術距離跟眼睛看到的差異對不上（藍色差 40 看得出來，綠色差 40
    看不太出來），所以不要拿 RGB 距離當「顏色夠不夠分得開」的標準。
    """
    s = hex_str.lstrip("#")
    r, g, b = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(c):
        return c ** (1.0 / 3.0) if c > 0.008856 else 7.787 * c + 16.0 / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a, b):
    import math
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))))


def test_every_stage_has_its_own_colour(qapp):
    """回饋原話：「太多都同個顏色（input enhance 跟 compare 都是藍色）」。

    以前是 ``group -> category -> 顏色``，六個階段只有三種色。這裡鎖的是
    **性質**（兩兩感知上分得開），不是寫死色碼 —— 色票還可以再調。
    ΔE ≥ 25 大約是「一眼看得出是兩個顏色」而不只是「同色的深淺」。
    """
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        GROUPS = _stage_groups()
        colours = {g: theme_mod.group_hex(g) for g in GROUPS}
        assert len(set(colours.values())) == len(GROUPS), \
            "%s 主題有階段共用顏色：%s" % (name, colours)
        for i, a in enumerate(GROUPS):
            for b in GROUPS[i + 1:]:
                d = _delta_e(colours[a], colours[b])
                assert d >= 25, "%s 的 %s 與 %s 太接近（%s vs %s, ΔE=%.1f）" % (
                    name, a, b, colours[a], colours[b], d)
    theme_mod.apply_theme(qapp, "light")


def test_the_stage_colours_stay_one_family(qapp):
    """分得開之外還要**看起來像一套**：同一主題內明度不可以亂跳。

    六個顏色如果亮度差很多，rail 上就會有幾個特別跳、幾個特別悶 ——
    那是「六個顏色」，不是「一套色票」。
    """
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        GROUPS = _stage_groups()
        lums = [_lab(theme_mod.group_hex(g))[0] for g in GROUPS]
        assert max(lums) - min(lums) <= 15, \
            "%s 主題的階段色明度差太多：%s" % (name, [round(x) for x in lums])
    theme_mod.apply_theme(qapp, "light")


def test_the_library_and_the_canvas_use_the_same_stage_colour(qapp):
    """rail 上看到的顏色，跟畫布節點上的必須是同一個 —— 不然顏色不是語言。"""
    from d4t.core.pipeline import list_steps

    panel = widgets_mod.LibraryPanel()
    panel.set_steps([s.describe() for s in list_steps()])
    for gid in _stage_groups():
        btn = panel.stage_buttons[gid]
        assert theme_mod.group_hex(gid) in btn.styleSheet() \
            or btn.icon.color == theme_mod.group_hex(gid)


def test_every_report_metric_the_cd_card_offers_has_a_face(qapp):
    """卡片多宣告一顆而 UI 沒登記，畫出來是一顆沒有分群、標籤是原始 id 的膠囊
    —— 跑得完、看得到、而且醜，也就是不會有人回報（同 F18 的規矩）。"""
    from d4t.core.steps.cd import REPORT_CHOICES
    from d4t.ui import widgets as widgets_mod

    groups = set()
    for mid in REPORT_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and not label.startswith("cd_"), mid
        assert glyph in widgets_mod.METRIC_GLYPHS, mid
        groups.add(group)
    # **粗糙度那一群要分得出來** —— 它只有在量測線夠多時才有意義，而那是
    # 「為什麼我的 LER 是 0」的答案。
    assert groups == {"Width", "Roughness", "Vs target"}


def test_every_size_metric_the_card_offers_has_a_face(qapp):
    from d4t.core.steps.cd import SIZE_CHOICES
    from d4t.ui import widgets as widgets_mod

    groups = set()
    for mid in SIZE_CHOICES:
        group, label, glyph = widgets_mod.metric_face(mid)
        assert group in widgets_mod.METRIC_GROUP_ORDER, mid
        assert group != "Other", "%s 沒有登記在 METRIC_GROUPS" % mid
        assert label and not label.startswith("cd_"), mid
        assert glyph in widgets_mod.METRIC_GLYPHS, mid
        groups.add(group)
    # **不要用 ``Shape``** —— 那個字在 GLV 那邊已經是偏度那一群了。
    assert groups == {"Size", "Outline"}
    assert "Shape" not in groups


# --------------------------------------------------------------------------- #
# F68 收尾：浮點欄位的小數位跟著範圍走
# --------------------------------------------------------------------------- #
def test_a_sigma_threshold_is_not_printed_with_three_decimals(qapp):
    """`0.000 σ` 的三位小數不是精度，是雜訊 —— 而且讓人以為那格要填那麼細。"""
    from d4t.ui.widgets import _float_decimals

    # px / % / σ / 灰階 那一族：一位就夠
    assert _float_decimals(0.0, 99.0, 0.0) == 1        # over_k、mark_pixels_k
    assert _float_decimals(0.0, 49.0, 0.0) == 1        # trim_percent
    assert _float_decimals(-255.0, 510.0, 0.0) == 1    # tone.brightness

    # 本來就在細部的那一族**不准變粗**（砍掉小數位它就填不進去了）
    assert _float_decimals(0.01, 999999.99, 1.0) == 3  # nm_per_px
    assert _float_decimals(0.1, 4.9, 1.0) == 3         # gamma
    assert _float_decimals(-1.0, 2.0, 0.0) == 3        # min_score
    assert _float_decimals(0.0, 1.0, 0.5) == 3         # flatten.strength


def test_the_field_never_shows_a_coarser_number_than_the_recipe_holds(qapp):
    """**顯示不准比 recipe 裡的值粗。**

    QDoubleSpinBox 會把值捨進它的位數 —— 手寫 recipe 填了 2.55 而欄位只有一位
    的話，畫面上是 2.6，而使用者不會知道自己看到的不是檔案裡的東西。
    """
    from d4t.ui.widgets import _float_decimals

    assert _float_decimals(0.0, 49.0, 2.55) == 2
    assert _float_decimals(0.0, 99.0, 4.125) == 3
    assert _float_decimals(0.0, 99.0, 3.0) == 1, "整數不必為此加位數"


def test_the_real_form_shows_the_value_it_was_given(qapp):
    """走真的那條路（describe → 表單 → 讀回來），不是只打那支純函式。"""
    from PySide6.QtWidgets import QDoubleSpinBox

    from d4t.core.pipeline import get_step
    import d4t.core.steps  # noqa: F401

    form = widgets_mod.ParamForm()
    card = get_step("glv_stats")
    form.set_step(card.describe(),
                  card.validate_params({"source": "test", "across_boxes":
                                        "each box", "over_k": 2.55}),
                  ["test"])
    box = form.editor("over_k")
    assert isinstance(box, QDoubleSpinBox)
    assert box.value() == pytest.approx(2.55), "值不可以被欄位捨掉"
    assert "0.000" not in box.text()
