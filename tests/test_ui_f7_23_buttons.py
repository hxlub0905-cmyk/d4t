# F7-23 驗收（第一批，只動 theme.py）：按鈕要說得出自己現在是什麼狀態。
"""這一支跟 ``test_ui_controls_readable.py`` 是同一種測法 —— **量畫出來的畫素**。

理由一樣：這裡每一條都不是「功能壞了」。快捷鍵按得到、按鈕點得下去、
disabled 真的擋住了動作 —— 每一項功能都是好的，壞的是**畫面沒有把狀態講出來**。
斷言 QSS 裡有沒有寫某一行沒有用，因為 F7-23 修的三件事裡有兩件正是
「規則寫了，但沒有生效」：

* ``QPushButton:focus`` 寫了，但 ``#primary`` 是 id 選擇器、``[variant=…]``
  寫在後面，兩者都把它蓋掉；工具列則是從頭到尾沒有 ``:focus`` 規則。
* ``QToolBar::separator`` 寫了兩次，值不一樣，帶著說明的那一份是死的。

所以一律問「畫出來長什麼樣」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QPushButton, QToolBar, QToolButton, QVBoxLayout, QWidget,
    )

    from adept.ui import theme as theme_mod
    g.update(Qt=Qt, QColor=QColor, QPixmap=QPixmap, QApplication=QApplication,
             QPushButton=QPushButton, QToolBar=QToolBar, QToolButton=QToolButton,
             QVBoxLayout=QVBoxLayout, QWidget=QWidget, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app
    theme_mod.apply_theme(app, "light")


#: 中性灰的背板：淺色與深色主題都不會剛好同色，所以「這格是按鈕還是背板」
#: 在兩個主題下都問得出來。
BACKDROP = "#808080"


# --------------------------------------------------------------------------- #
# 造一顆按鈕：六種 QPushButton 變體 + 兩種工具列按鈕
# --------------------------------------------------------------------------- #
def _make(kind, parent):
    """``kind`` -> 一顆已經套好樣式的按鈕（放進 ``parent``）。"""
    if kind.startswith("tool"):
        bar = QToolBar(parent)
        b = QToolButton(bar)
        b.setText("Run trial")
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        if kind == "tool_primary":
            b.setObjectName("primary")
        bar.addWidget(b)
        return bar, b
    b = QPushButton("Run trial", parent)
    if kind == "primary":
        b.setObjectName("primary")
    elif kind == "cardButton":
        b.setObjectName("cardButton")
    elif kind in ("secondary", "danger", "ghost"):
        b.setProperty("variant", kind)
    return b, b


#: 每一種按鈕，以及它的焦點框**該用哪個 token 的顏色**。
#:
#: 不是同一個顏色 —— 焦點框畫在按鈕的填色上面（Qt 的 ``outline`` 對按鈕不
#: 生效），所以它要跟**那一顆按鈕自己的底**對比：淡底用 accent，accent 底
#: 用白色。一個顏色走天下的話，藍底上的藍框等於沒畫。
KINDS = (
    ("plain", "border_focus"),
    ("primary", "focus_ring_inverse"),
    ("secondary", "border_focus"),
    ("danger", "border_focus"),
    ("ghost", "border_focus"),
    ("cardButton", "border_focus"),
    ("tool_plain", "border_focus"),
    ("tool_primary", "focus_ring_inverse"),
)


def _shot(app, kind, focused):
    """畫一顆按鈕（``focused`` 決定焦點在它身上還是在旁邊那顆），回傳 QImage。

    焦點必須是**真的**：``setFocus`` 在沒有 show 過、沒有 activate 過的
    widget 上不會生效，而 ``hasFocus()`` 回 False 的那一張圖看起來會跟
    「沒有焦點框」一模一樣 —— 那樣這條測試會永遠是綠的。
    """
    host = QWidget()
    lay = QVBoxLayout(host)
    decoy = QPushButton("elsewhere", host)
    lay.addWidget(decoy)
    holder, button = _make(kind, host)
    lay.addWidget(holder)
    host.show()
    app.processEvents()
    host.activateWindow()
    (button if focused else decoy).setFocus(Qt.TabFocusReason)
    app.processEvents()
    assert button.hasFocus() is bool(focused), \
        "%s 的焦點沒有真的設進去，這張圖問不出東西" % kind

    button.resize(140, 30)
    pm = QPixmap(button.size())
    pm.fill(QColor(BACKDROP))
    button.render(pm)
    img = pm.toImage()
    host.hide()
    return img


def _count(img, hex_colour, tol=24):
    """整張圖裡有多少畫素接近 ``hex_colour``。"""
    want = QColor(hex_colour)
    n = 0
    for x in range(img.width()):
        for y in range(img.height()):
            p = img.pixelColor(x, y)
            if (abs(p.red() - want.red()) + abs(p.green() - want.green())
                    + abs(p.blue() - want.blue())) <= tol:
                n += 1
    return n


# --------------------------------------------------------------------------- #
# A1：焦點看得見（每一種變體）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_every_button_variant_shows_that_it_has_focus(qapp, theme_name):
    """Tab 到哪一顆，畫面上就要看得出來 —— **八種按鈕全部**。

    F7-23 之前只有「沒有 objectName 也沒有 variant 的 QPushButton」有焦點框。
    Run trial（``#primary``）、Stop（``danger``）、Try it with sample data
    （``secondary``）與整條工具列都沒有 —— 而 F7-16 才剛把快捷鍵做進來。
    鍵盤路徑做了一半：按得到，但看不到自己站在哪。
    """
    theme_mod.apply_theme(qapp, theme_name)
    ring_missing = []
    for kind, token in KINDS:
        colour = theme_mod.TOKENS[token]
        off = _count(_shot(qapp, kind, False), colour)
        on = _count(_shot(qapp, kind, True), colour)
        if on - off < 40:          # 一圈 1–2px 的框遠遠不只 40 個畫素
            ring_missing.append("%s（%s=%s）: %d -> %d"
                                % (kind, token, colour, off, on))
    assert not ring_missing, \
        "這些按鈕拿到焦點時畫面沒有變：\n  " + "\n  ".join(ring_missing)
    theme_mod.apply_theme(qapp, "light")


def test_the_focus_ring_does_not_move_the_label(qapp):
    """焦點框畫在按鈕**裡面**（Qt 的 outline 不生效），所以它會吃掉 1px。

    那 1px 一定要從自己的 padding 還回去，否則每次 Tab 過去文字就跳一格 ——
    比沒有焦點框更糟，因為畫面在動而使用者不知道為什麼。

    ``contentsRect()`` 就是 Qt 依 border + padding 算出來的文字可用區，
    直接問它，不必去猜文字的畫素落在哪。
    """
    moved = []
    for kind, _token in KINDS:
        host = QWidget()
        lay = QVBoxLayout(host)
        decoy = QPushButton("elsewhere", host)
        lay.addWidget(decoy)
        holder, button = _make(kind, host)
        lay.addWidget(holder)
        host.show()
        qapp.processEvents()
        host.activateWindow()
        button.resize(140, 30)

        decoy.setFocus(Qt.TabFocusReason)
        qapp.processEvents()
        before = button.contentsRect()
        button.setFocus(Qt.TabFocusReason)
        qapp.processEvents()
        after = button.contentsRect()
        host.hide()
        if before != after:
            moved.append("%s: %s -> %s" % (kind, before, after))
    assert not moved, "拿到焦點時文字區跟著移動了：\n  " + "\n  ".join(moved)


# --------------------------------------------------------------------------- #
# A2：disabled 的主要動作仍然是主要動作
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_a_disabled_primary_still_looks_like_the_primary(qapp, theme_name):
    """沒載資料時整條工具列不能變成同一片灰。

    以前 ``#primary:disabled`` 與一般鈕的 ``:disabled`` 是逐項相同的宣告
    （``disabled_bg`` / ``disabled_text`` / ``border_default``），於是「我該按
    哪一顆」在**第一次打開這個工具的那一刻**沒有答案 —— 而那正是最需要它的
    時候。
    """
    theme_mod.apply_theme(qapp, theme_name)
    host = QWidget()
    lay = QVBoxLayout(host)
    # **同一個字**：兩顆鈕的差別必須只剩樣式。字不一樣的話，取樣點有可能一顆
    # 落在筆畫上、一顆落在空白處，那兩個顏色本來就不同 —— 這條測試會變成
    # 恆真（實際發生過：改之前的 theme 也「通過」了）。
    plain = QPushButton("Run trial", host)
    primary = QPushButton("Run trial", host)
    primary.setObjectName("primary")
    for b in (plain, primary):
        b.setEnabled(False)
        lay.addWidget(b)
    host.show()
    qapp.processEvents()

    fills = [_fill_colour(b) for b in (plain, primary)]
    host.hide()

    assert fills[0] != fills[1], \
        "disabled 的 primary 與 disabled 的一般鈕填色相同（%s）" % fills[0].name()
    assert fills[1] == QColor(theme_mod.TOKENS["accent_bg"]), \
        "disabled 的 primary 應該留著 accent 的淡底（%s），實際是 %s" \
        % (theme_mod.TOKENS["accent_bg"], fills[1].name())
    theme_mod.apply_theme(qapp, "light")


def _fill_colour(button):
    """按鈕的**底色** —— 取邊框內側一條橫帶裡最常見的顏色。

    不要拿正中央那一格：那裡多半落在文字的筆畫上，量到的是字不是底。
    """
    button.resize(140, 30)
    pm = QPixmap(button.size())
    pm.fill(QColor(BACKDROP))
    button.render(pm)
    img = pm.toImage()
    seen = {}
    for x in range(8, img.width() - 8):
        for y in range(4, 8):                 # 邊框以內、文字以上
            c = img.pixelColor(x, y)
            seen[c.name()] = seen.get(c.name(), 0) + 1
    return QColor(max(seen.items(), key=lambda kv: kv[1])[0])


# --------------------------------------------------------------------------- #
# B3：圓角是 token
# --------------------------------------------------------------------------- #
def test_the_corner_radius_really_comes_from_the_token(qapp):
    """把 ``radius_md`` 改成 0，角就要變方 —— 否則那個 token 只是裝飾。

    F7-23 之前 QSS 裡有六個各自寫死的圓角值。收成 token 這件事只有在
    **改 token 真的會改到畫面**時才算數。

    只問「角落那一格有沒有跟著變」，不預設它該是什麼顏色：``render()`` 底下
    畫什麼跟平台與 autoFillBackground 有關，而這條測試在意的不是那個。
    """
    def corner():
        host = QWidget()
        lay = QVBoxLayout(host)
        decoy = QPushButton("elsewhere", host)      # 焦點放這顆，免得焦點框
        b = QPushButton("Run trial", host)          # 混進角落那一格
        lay.addWidget(decoy)
        lay.addWidget(b)
        host.show()
        qapp.processEvents()
        host.activateWindow()
        decoy.setFocus(Qt.TabFocusReason)
        qapp.processEvents()
        b.resize(140, 30)
        pm = QPixmap(b.size())
        pm.fill(QColor(BACKDROP))
        b.render(pm)
        img = pm.toImage()
        host.hide()
        return img.pixelColor(0, 0)

    round_corner = corner()
    original = theme_mod.TOKENS["radius_md"]
    try:
        theme_mod.TOKENS["radius_md"] = "0px"
        qapp.setStyleSheet(theme_mod.build_stylesheet())
        square_corner = corner()
    finally:
        theme_mod.TOKENS["radius_md"] = original
        theme_mod.apply_theme(qapp, "light")

    assert round_corner != square_corner, \
        "radius_md 改成 0 之後角落沒有變（%s）—— QSS 沒有真的在用這個 token" \
        % round_corner.name()
    assert square_corner == QColor(theme_mod.TOKENS["border_input"]), \
        "角變方之後，最角落那一格應該就是按鈕自己的邊框色，實際是 %s" \
        % square_corner.name()


def test_light_and_dark_agree_on_shape(qapp):
    """換膚換的是顏色，不是形狀。"""
    light, dark = theme_mod.PALETTES["light"], theme_mod.PALETTES["dark"]
    for key in ("radius_sm", "radius_md", "radius_pill"):
        assert light[key] == dark[key], key


# --------------------------------------------------------------------------- #
# B6：一條規則只寫一次
# --------------------------------------------------------------------------- #
def test_the_toolbar_separator_is_defined_once(qapp):
    """同一個選擇器寫兩次，贏的是後面那一份 —— 而說明通常寫在前面那一份上。

    這裡曾經是 ``margin: 4px 4px``（帶著解釋它為什麼存在的註解）與
    ``margin: 5px 6px``（沒有註解）各一份。改前面那一份不會有任何效果，
    而那正是有註解、看起來該改的那一份。
    """
    qss = theme_mod.build_stylesheet()
    assert qss.count("QToolBar::separator") == 1, \
        "QToolBar::separator 被定義了 %d 次" % qss.count("QToolBar::separator")
