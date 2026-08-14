# F7-23 驗收：按鈕要說得出自己現在是什麼狀態（第一、二輪）。
"""這一支跟 ``test_ui_controls_readable.py`` 是同一種測法 —— **量畫出來的畫素**。

理由一樣：這裡每一條都不是「功能壞了」。快捷鍵按得到、按鈕點得下去、
disabled 真的擋住了動作 —— 每一項功能都是好的，壞的是**畫面沒有把狀態講出來**。
斷言 QSS 裡有沒有寫某一行沒有用，因為 F7-23 修的三件事裡有兩件正是
「規則寫了，但沒有生效」：

* ``QPushButton:focus`` 寫了，但 ``#primary`` 是 id 選擇器、``[variant=…]``
  寫在後面，兩者都把它蓋掉；工具列則是從頭到尾沒有 ``:focus`` 規則。
* ``QToolBar::separator`` 寫了兩次，值不一樣，帶著說明的那一份是死的。

所以一律問「畫出來長什麼樣」。

第二輪（尺寸、游標、拆掉那顆 ``MenuButtonPopup``）在檔案後半，測法不同 ——
那些問的是「這件事還是不是每個呼叫端各自記得」，所以量 ``sizeHint()``、
掃游標、靜態掃 ``setFixedSize``。
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


# --------------------------------------------------------------------------- #
# 第二輪：尺寸與游標不該是每個呼叫端各自記得的事
# --------------------------------------------------------------------------- #
def _studio(qapp):
    from adept.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.show()
    qapp.processEvents()
    return win


def test_every_small_button_is_the_same_size(qapp):
    """六個呼叫端曾經寫死六種尺寸：22×22、24×22、30×22、寬 28、寬 40、高 20。

    同一種視覺語言，卻沒有兩顆是一樣大的 —— 而且要改的時候得先找出那六個地方。
    現在尺寸由 QSS 的 ``control_sm`` 決定，呼叫端只說「方的還是帶文字的」。
    """
    from PySide6.QtWidgets import QPushButton

    win = _studio(qapp)
    try:
        smalls = [b for b in win.findChildren(QPushButton)
                  if b.objectName() == "cardButton"]
        assert len(smalls) >= 9, "小按鈕應該至少有九顆（縮放列 5 + 導覽 2 + 切換 2）"

        odd = []
        heights = {}
        for b in smalls:
            shape = b.property("shape")
            if shape not in ("square", "wide"):
                odd.append("%r 沒有宣告形狀（%r）" % (b.text(), shape))
                continue
            hint = b.sizeHint()
            heights.setdefault(hint.height(), []).append(b.text())
            if shape == "square" and hint.width() != hint.height():
                odd.append("%r 宣告是方的，實際 %d×%d"
                           % (b.text(), hint.width(), hint.height()))
        assert not odd, "\n  ".join(odd)

        # 高度只准有一種。不去驗「等於 control_sm」—— QSS 的 min/max-height 管的
        # 是內容框，加上邊框才是外框尺寸，把那個算式抄進測試只是把 Qt 的盒模型
        # 複製一份。這裡要問的是「六種尺寸收成一種了沒有」。
        assert len(heights) == 1, \
            "小按鈕還有 %d 種高度：%s" % (len(heights), heights)
        # 而且那一種確實是 control_sm 撐出來的（改 token 要改得動）
        want = int(str(theme_mod.TOKENS["control_sm"]).replace("px", ""))
        got = next(iter(heights))
        assert want <= got <= want + 4, \
            "小按鈕高 %d，但 control_sm 是 %d —— 尺寸不是它決定的" % (got, want)
    finally:
        win.close()


def test_nobody_hard_codes_a_button_size_any_more(qapp):
    """尺寸寫死在呼叫端就會慢慢長回六種。靜態掃一遍，成本近乎零。"""
    import ast
    import pathlib

    ui = pathlib.Path(__file__).resolve().parent.parent / "adept" / "ui"
    banned = {"setFixedSize", "setFixedWidth", "setFixedHeight"}
    hits = []
    for py in sorted(ui.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in banned):
                line = src.splitlines()[node.lineno - 1]
                # 只管按鈕。進度條、色條、縮圖那些固定尺寸是它們的規格。
                if "btn" in line or "button" in line.lower():
                    hits.append("%s:%d  %s" % (py.name, node.lineno, line.strip()))
    assert not hits, "按鈕的尺寸請交給 QSS 的 shape，不要寫在呼叫端：\n  " \
                     + "\n  ".join(hits)


def test_every_button_says_it_can_be_clicked(qapp):
    """滑過去有沒有變手指，是使用者判斷「這能不能點」的第一個訊號。

    以前這是每個呼叫端自己記得要做的事，於是只做到一半 —— 工具列、卡片庫、
    節點卡有，Stop、Open KLARF…、輸出精靈那四顆、畫布縮放列全都沒有。
    現在是視窗建好之後掃一次的規則（``widgets.apply_button_cursors``）。
    """
    from PySide6.QtWidgets import QPushButton

    win = _studio(qapp)
    try:
        # 參數列是選到卡片才長出來的，所以先選一張，把那批也納入檢查
        if win.model.node_order:
            win.select_node(win.model.node_order[0])
        qapp.processEvents()

        wrong = []
        for b in win.findChildren(QWidget):
            if not isinstance(b, (QPushButton, QToolButton)):
                continue
            if b.cursor().shape() != Qt.PointingHandCursor:
                wrong.append("%s %r" % (type(b).__name__, b.text()))
        assert not wrong, "這些按鈕滑過去沒有變手指：\n  " + "\n  ".join(wrong)
    finally:
        win.close()


def test_importance_is_horizontal_not_vertical(qapp):
    """primary 比別人**寬**，不比別人高。

    以前 `#primary` 的垂直 padding 多 1px，於是空白狀態下「Open KLARF…」比
    旁邊的「Try it with sample data」高 2px —— 兩顆並排的鈕對不齊，是那種
    說不出哪裡怪但就是怪的畫面。
    """
    from PySide6.QtWidgets import QPushButton

    host = QWidget()
    lay = QVBoxLayout(host)
    plain = QPushButton("Try it with sample data", host)
    plain.setProperty("variant", "secondary")
    primary = QPushButton("Open KLARF…", host)
    primary.setObjectName("primary")
    for b in (plain, primary):
        lay.addWidget(b)
    host.show()
    qapp.processEvents()

    assert plain.sizeHint().height() == primary.sizeHint().height(), \
        "primary %d vs 一般鈕 %d" % (primary.sizeHint().height(),
                                     plain.sizeHint().height())
    assert primary.sizeHint().width() > 0
    host.hide()


def test_run_trial_no_longer_leaves_half_of_itself_to_qt(qapp):
    """``MenuButtonPopup`` 的那半邊完全歸 Qt 管，而 QSS 修不了它。

    量過的結論在計畫書 §27.5：只要給 ``::menu-button`` 一個盒子（背景、邊框、
    圓角**任一**），Qt 就把繪製交給 stylesheet，而 stylesheet 沒有 ``image``
    就不畫箭頭 —— 這個 repo 塞不了圖檔。所以拆成兩顆普通按鈕。

    這條鎖的是「別退回去」：主鈕不掛 menu（掛了 Qt 就會自己畫那半邊），
    箭頭鈕也不掛（掛了 Qt 會再加一個自己的下拉指示器，等於兩個箭頭）。
    """
    win = _studio(qapp)
    try:
        assert win.btn_trial.menu() is None
        assert win.btn_trial_more.menu() is None
        assert win.btn_trial.popupMode() != QToolButton.MenuButtonPopup
        assert [a.text() for a in win.trial_menu.actions()] == ["Run all defects"]
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 第三輪：外觀回到 QSS，而狀態的變化要看得見
# --------------------------------------------------------------------------- #
def _silhouette(qapp, widget, host):
    """widget 左緣的輪廓：每一列第一個「不是背板」的 x。

    圓角看得出來的話，這串數字上下兩端會是遞減／遞增的弧；方角則是一整排 0。
    """
    host.show()
    qapp.processEvents()
    pm = QPixmap(host.size())
    pm.fill(QColor(BACKDROP))
    host.render(pm)
    img = pm.toImage()
    r = widget.geometry()
    out = []
    for y in range(r.top(), r.bottom() + 1):
        first = 0
        for x in range(r.left(), min(img.width(), r.left() + 24)):
            if img.pixelColor(x, y).name() != BACKDROP:
                first = x - r.left()
                break
        out.append(first)
    return out


def test_the_pill_token_is_actually_round(qapp):
    """``radius_pill`` 必須真的畫出膠囊 —— 而 CSS 的 ``999px`` 寫法在 Qt 是**方的**。

    Qt 不會把超出範圍的圓角夾回半高，它直接放棄圓角、畫一個矩形，而且不報錯。
    一個叫 ``pill`` 的 token 畫出方角，是最難發現的那種錯：名字說得斬釘截鐵，
    畫面上沒有任何地方對得起來，也沒有訊息。

    （第一輪加這個 token 時填的正是 ``999px``；還沒有人用到就先被這條抓下來。）
    """
    from PySide6.QtWidgets import QHBoxLayout, QPushButton

    # 兩件事都是必要的，少一件這條測試就永遠是綠的：
    #
    # 1. **畫 host，不要單獨畫 chip。** Qt 會用 widget 自己的底把整個矩形填滿，
    #    再把有圓角的框畫上去 —— 單獨 render 那顆 chip，圓角外面那幾格拿到的
    #    還是 chip 的底色，輪廓完全量不出來。
    # 2. host 的底要用 **id 選擇器**：主 QSS 裡的
    #    ``QMainWindow, QWidget, QDialog { background: … }`` 會贏過型別選擇器，
    #    於是背板變成 bg_page，而 bg_page 不是我們要比對的那個顏色。
    qapp.setStyleSheet("%s\nQWidget#pillHost { background: %s; }"
                       % (theme_mod.build_stylesheet(), BACKDROP))
    try:
        host = QWidget()
        host.setObjectName("pillHost")
        lay = QHBoxLayout(host)
        lay.setContentsMargins(8, 8, 8, 8)
        chip = QPushButton("Sort: score", host)
        chip.setObjectName("galleryChip")
        lay.addWidget(chip)
        host.show()
        qapp.processEvents()
        host.resize(180, 42)
        qapp.processEvents()
        profile = _silhouette(qapp, chip, host)
        host.hide()
    finally:
        theme_mod.apply_theme(qapp, "light")

    assert max(profile) >= 3, \
        "chip 的左緣是直的（輪廓 %s）—— radius_pill 沒有生效" % profile
    # 最圓的地方在上下兩端、最平的地方在中線，那才是膠囊而不是隨便一個圓角
    middle = profile[len(profile) // 2]
    assert middle == 0, "膠囊的中線應該貼齊左緣，實際縮了 %d px" % middle


def _lab_L(hex_str):
    """sRGB hex -> CIE L*（只要亮度，判斷「差得看不看得出來」夠用）。"""
    s = hex_str.lstrip("#")
    rgb = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return 116 * (y ** (1 / 3.0)) - 16 if y > 0.008856 else 903.3 * y


@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_pressed_is_a_step_you_can_actually_see(qapp, theme_name):
    """按下去的回饋以前是 hover 再深一階 —— 量出來 ΔL* ≈ 3.5。

    而按住的時間大約 100ms、按鈕可能只有 24px。全平面設計沒有陰影可以用，
    那底色就得真的跳一階。
    """
    pal = theme_mod.PALETTES[theme_name]
    d = abs(_lab_L(pal["pressed_bg"]) - _lab_L(pal["hover_warm"]))
    assert d >= 6.0, \
        "%s：pressed 與 hover 只差 ΔL* %.1f，按下去看不出來" % (theme_name, d)


def test_a_checkable_button_looks_checked(qapp):
    """``QPushButton`` 以前完全沒有 ``:checked`` 規則。

    現在能用的只有 ``#cardButton:checked``（F7-17 為了 Card/Features 那一組加
    的）—— 下一個做成 checkable 的一般鈕會永遠看起來像沒選中。
    """
    from PySide6.QtWidgets import QPushButton

    host = QWidget()
    lay = QVBoxLayout(host)
    b = QPushButton("Compare", host)
    b.setCheckable(True)
    lay.addWidget(b)
    host.show()
    qapp.processEvents()

    off = _fill_colour(b)
    b.setChecked(True)
    qapp.processEvents()
    on = _fill_colour(b)
    host.hide()

    assert off != on, "選起來之後填色沒有變（%s）" % off.name()
    assert on == QColor(theme_mod.TOKENS["accent_bg"]), \
        "選中的底色應該是 accent_bg，實際是 %s" % on.name()


def test_the_stage_button_repolishes_when_it_opens(qapp):
    """外觀搬進 QSS 之後，**改屬性不會自己重畫** —— 少一次 polish 就完全沒反應。

    這是把 per-widget stylesheet 換成 ``[active="true"]`` 時最容易漏的一步：
    ``setProperty`` 只是存一個值，而且不報錯。
    """
    from adept.ui import widgets as widgets_mod

    host = QWidget()
    lay = QVBoxLayout(host)
    btn = widgets_mod.StageButton("region", "ROI", "where to look",
                                  theme_mod.group_hex("region"), host)
    lay.addWidget(btn)
    host.show()
    qapp.processEvents()

    closed = _fill_colour(btn)
    btn.set_active(True)
    qapp.processEvents()
    opened = _fill_colour(btn)
    host.hide()

    assert closed != opened, "打開的那一段看起來跟沒打開一樣（%s）" % closed.name()
    assert opened == QColor(theme_mod.TOKENS["accent_bg"])


def test_a_library_row_follows_a_theme_switch(qapp):
    """換膚之後卡片庫的列要跟著換色 —— 以前那要靠有人記得逐顆重套。

    最容易漏的是 badge：它是 ``set_missing`` 當下用 ``TOKENS`` 組出來的字串，
    而換主題的那條路只走了 rail 上的階段鈕。於是「needs diff」那幾列會留在
    上一個主題的灰色，而畫面其他地方都變了。
    """
    from adept.ui import widgets as widgets_mod

    describe = {"key": "subtract", "label": "Subtract", "help": "test - ref",
                "reads": ["diff"], "group": "compare"}
    host = QWidget()
    lay = QVBoxLayout(host)
    row = widgets_mod._LibraryItem(describe, theme_mod.group_hex("compare"), host)
    row.set_missing(["diff"])
    lay.addWidget(row)
    host.show()
    qapp.processEvents()

    def badge_ink():
        pm = QPixmap(row.badge.size())
        pm.fill(QColor(BACKDROP))
        row.badge.render(pm)
        img = pm.toImage()
        seen = {}
        for x in range(img.width()):
            for y in range(img.height()):
                c = img.pixelColor(x, y).name()
                if c != BACKDROP:
                    seen[c] = seen.get(c, 0) + 1
        return seen

    theme_mod.apply_theme(qapp, "light")
    qapp.processEvents()
    light = badge_ink()
    theme_mod.apply_theme(qapp, "dark")
    qapp.processEvents()
    dark = badge_ink()
    host.hide()
    theme_mod.apply_theme(qapp, "light")

    assert light and dark, "badge 沒有畫出任何東西"
    assert set(light) != set(dark), \
        "換主題之後 badge 的顏色一模一樣 —— 它沒有跟著 QSS 走"


def test_the_widgets_stopped_writing_their_own_palette(qapp):
    """這三個元件不准再自己組 stylesheet 字串。

    留著的話下一個人只會照抄，而抄過去的那一份不會跟著換膚 —— theme.py
    docstring 那句「顏色永遠不會兩邊走鐘」就繼續是半真的。

    ``nodeCard`` / ``scoreCard`` / ``VerdictChip`` **不在這條裡**：它們的顏色
    是依 category / 判定算出來的，本來就該留在 widget（見 QSS 那一段的說明）。
    """
    import pathlib

    ui = pathlib.Path(__file__).resolve().parent.parent / "adept" / "ui"
    offenders = []
    for name, marker in (("widgets.py", "QFrame#libItem"),
                         ("widgets.py", "QFrame#stageButton"),
                         ("gallery.py", "QPushButton#galleryChip")):
        src = (ui / name).read_text(encoding="utf-8")
        # 只找**組 stylesheet 字串**的地方（註解裡提到選擇器不算）
        for line in src.splitlines():
            stripped = line.strip()
            if marker in line and not stripped.startswith("#"):
                offenders.append("%s: %s" % (name, stripped))
    assert not offenders, "還有元件在自己畫色盤：\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------------------- #
# 第四輪：圖示用畫的，不用字元
# --------------------------------------------------------------------------- #
def _ink_count(widget, qapp):
    """widget 畫出來之後，有多少畫素不是它自己的底色。"""
    qapp.processEvents()
    pm = QPixmap(widget.size())
    pm.fill(QColor(BACKDROP))
    widget.render(pm)
    img = pm.toImage()
    bg = _fill_colour(widget)
    n = 0
    for x in range(img.width()):
        for y in range(img.height()):
            p = img.pixelColor(x, y)
            if (abs(p.red() - bg.red()) + abs(p.green() - bg.green())
                    + abs(p.blue() - bg.blue())) > 40:
                n += 1
    return n


def test_every_icon_name_actually_draws_something(qapp):
    """每一個圖示都要畫得出東西 —— 而且**打錯名字要當場炸**。

    以前這些位置放的是字元。打錯一個字元不會有人發現（畫面上就是一個奇怪的
    符號）；而字型缺字的時候畫出來是豆腐框，那也不會有人發現 —— 因為缺字的是
    廠內那台 Windows，我們在這裡看不到。名字換成 ``GLYPH_ICONS`` 之後，
    兩種錯都在建構的當下就擋掉。
    """
    from PySide6.QtGui import QPainter

    from adept.ui import widgets as widgets_mod

    blank = []
    for name in widgets_mod.GLYPH_ICONS:
        pm = QPixmap(24, 24)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        widgets_mod.draw_glyph_icon(p, name, 24.0, "#000000")
        p.end()
        img = pm.toImage()
        ink = sum(1 for x in range(24) for y in range(24)
                  if img.pixelColor(x, y) != QColor("#ffffff"))
        if ink < 12:
            blank.append("%s（只有 %d 個畫素）" % (name, ink))
    assert not blank, "這些圖示畫出來幾乎是空的：\n  " + "\n  ".join(blank)

    with pytest.raises(ValueError):
        pm = QPixmap(24, 24)
        p = QPainter(pm)
        try:
            widgets_mod.draw_glyph_icon(p, "no_such_icon", 24.0, "#000000")
        finally:
            p.end()


def test_no_button_relies_on_a_glyph_the_fab_machine_may_not_have(qapp):
    """按鈕的文字裡不准再出現「不保證有字型」的字元。

    廠內是 Windows，而 Segoe UI 蓋不到底下這幾個 —— 要退到 Segoe UI Symbol。
    退字型的結果是同一排按鈕裡每顆字的大小與 baseline 都不一樣，最壞是豆腐框。
    **而我們在這裡看不到**（開發機不是那台），所以只能用規則擋。

    這串**刻意不是「所有非 ASCII」**：

    * ``↶↷``(U+21B6/B7)、``⤢``(U+2922)、``⌗``(U+2317) —— Segoe UI 沒有
    * ``◐``(U+25D0)、``◀▶``(U+25C0/B6)、``▾``(U+25BE)、``△``(U+25B3) ——
      Geometric Shapes，靠 Segoe UI Symbol 補，而且 ``▶`` 在某些設定下會被當
      emoji 換一整套字型
    * ``✓✗✕``(U+2713/17/15) —— Dingbats，同上

    **不在這串裡的**：``−``(U+2212) 與 ``←↑→↓``(U+2190–93) 是 Segoe UI 的基本
    覆蓋範圍，``×``(U+00D7) 更是 Latin-1 —— 它們留成文字是安全的，
    把它們也一起畫掉只會多一堆沒有換到東西的改動。``1:1`` 這種 ASCII 同理。
    """
    from PySide6.QtWidgets import QPushButton

    risky = "↶↷◐◀▶⤢⌗✕▾△✗✓"
    win = _studio(qapp)
    try:
        if win.model.node_order:
            win.select_node(win.model.node_order[0])
        qapp.processEvents()
        bad = []
        for b in win.findChildren(QWidget):
            if not isinstance(b, (QPushButton, QToolButton)):
                continue
            hit = [ch for ch in b.text() if ch in risky]
            if hit:
                bad.append("%r 用了 %s" % (b.text(), " ".join(hit)))
        assert not bad, "這些按鈕還在靠字元當圖示：\n  " + "\n  ".join(bad)
    finally:
        win.close()


def test_an_icon_button_says_what_it_is_without_a_label(qapp):
    """沒有文字的按鈕對讀螢幕軟體是**空的**。

    tooltip 已經寫了那句話，直接拿來當 accessible name —— 不要為同一件事再發明
    第二份說明，那兩份遲早會不一樣。
    """
    from adept.ui import widgets as widgets_mod

    b = widgets_mod.IconButton("fit", "Fit the whole pipeline in view")
    assert b.text() == ""
    assert b.accessibleName() == "Fit the whole pipeline in view"

    win = _studio(qapp)
    try:
        nameless = [w.glyph_name() for w in (win.btn_undo, win.btn_redo,
                                             win.btn_theme, win.btn_prev,
                                             win.btn_next)
                    if not w.accessibleName()]
        assert not nameless, "這些圖示鈕沒有名字：%s" % nameless
    finally:
        win.close()


def test_the_icon_follows_the_button_it_is_drawn_on(qapp):
    """圖示的顏色取自 widget 自己的 palette（Qt 從 QSS 的 ``color`` 解析出來的）。

    所以換膚與變灰完全不必通知任何人 —— 這正是第三輪那條教訓的延續：
    要嘛交給 QSS，要嘛就會有人忘記重套。
    """
    from adept.ui import widgets as widgets_mod

    host = QWidget()
    lay = QVBoxLayout(host)
    b = widgets_mod.IconButton("close", "Remove from the pipeline", host)
    lay.addWidget(b)
    host.show()
    qapp.processEvents()

    on = _ink_count(b, qapp)
    b.setEnabled(False)
    off = _ink_count(b, qapp)
    host.hide()

    assert on > 8, "圖示根本沒畫出來（%d 個畫素）" % on
    assert off != on, "變灰之後圖示一模一樣 —— 顏色沒有跟著 palette 走"


def test_the_theme_button_says_which_theme_is_on(qapp):
    """以前不管在哪個主題，那顆鈕都是同一個 ``◐``。

    看不出現在是哪一個、也看不出按下去會變成什麼 —— 一顆只有兩個狀態的開關，
    卻沒有任何地方顯示它現在在哪一邊。
    """
    from PySide6.QtGui import QPainter

    from adept.ui import widgets as widgets_mod

    def render(dark):
        pm = QPixmap(24, 24)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        widgets_mod.draw_glyph_icon(p, "theme", 24.0, "#000000", dark=dark)
        p.end()
        return pm.toImage()

    light, dark = render(False), render(True)
    diff = sum(1 for x in range(24) for y in range(24)
               if light.pixelColor(x, y) != dark.pixelColor(x, y))
    assert diff > 40, "兩個主題下的主題鈕長得一樣（只差 %d 個畫素）" % diff
