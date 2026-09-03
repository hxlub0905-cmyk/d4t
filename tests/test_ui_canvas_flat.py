# 卡片靠自己的明度浮起來，不靠一塊畫在底下的陰影（F81）。
"""`theme.py` 的檔頭從 F7-2 起就寫著「全平面 —— 沒有陰影、沒有漸層」，
而節點卡底下一直畫著一塊實心、單一 alpha、有硬邊的偏移方塊。**那句話一直是
假的**，而且那塊東西不是陰影，是重影。

量出來它其實**只在亮色主題上看得見**：

* alpha 46 的黑疊在亮色的 `canvas_bg` 上 → ΔL* 15.7
* 疊在暗色的 `#16181d` 上 → ΔL* **2.3**

也就是說暗色的卡片一直是靠明度差站著的（底比卡片暗 ΔL* 6.9），只有亮色在靠那
塊重影撐 —— 因為亮色的 `canvas_bg` 離白卡只有 ΔL* 4.9。

所以 F81 拿掉陰影、把亮色的 `canvas_bg` 壓深，兩個主題改成用**同一個機制**。

這個檔案問的是那個機制本身，不是「有沒有畫某一行」：

1. 兩個主題的卡片都靠明度差跟畫布分開（而且**亮色不准再比暗色差**）。
2. 畫布上真的沒有陰影了（畫一次，看卡片下緣外面有沒有比底色暗的東西）。
3. 點陣底沒有跟著變淡（底色壓深了，點要一起壓）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QPointF=QPointF, QRectF=QRectF, Qt=Qt, QColor=QColor,
             QImage=QImage, QPainter=QPainter, QApplication=QApplication,
             canvas_mod=canvas_mod, studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app
    theme_mod.apply_theme(app, "light")


def _lab_L(hex_str):
    s = hex_str.lstrip("#")
    rgb = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return 116 * (y ** (1 / 3.0)) - 16 if y > 0.008856 else 903.3 * y


#: 卡片與畫布底至少要差這麼多 L*。
#:
#: 6.0 不是挑一個好看的數字：**暗色本來就有 6.9**，而它從來沒有需要那塊陰影。
#: 門檻訂在暗色已經做到的水準之下一點，說的是「亮色不准比暗色差」。
MIN_CARD_LIFT = 6.0


# --------------------------------------------------------------------------- #
# 1. 兩個主題都靠明度差
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_a_card_stands_out_from_the_canvas_without_any_shadow(qapp, theme_name):
    pal = theme_mod.PALETTES[theme_name]
    lift = abs(_lab_L(pal["bg_surface"]) - _lab_L(pal["canvas_bg"]))
    assert lift >= MIN_CARD_LIFT, (
        "%s：卡片跟畫布底只差 ΔL* %.1f —— 沒有陰影的話它就站不住了"
        % (theme_name, lift))


def test_the_light_theme_is_no_longer_the_one_that_cheats(qapp):
    """**這是這一輪的重點。**

    陰影只在亮色看得見（ΔL* 15.7 對上暗色的 2.3），所以「兩個主題長得一樣」
    以前是假的：暗色靠明度、亮色靠一塊重影。這條測試守住它們用同一個機制。
    """
    lifts = {}
    for name in ("light", "dark"):
        pal = theme_mod.PALETTES[name]
        lifts[name] = abs(_lab_L(pal["bg_surface"]) - _lab_L(pal["canvas_bg"]))
    assert lifts["light"] >= lifts["dark"] - 0.5, (
        "亮色的卡片浮得比暗色淺（%.1f vs %.1f）—— 那正是它以前需要陰影的原因"
        % (lifts["light"], lifts["dark"]))


# --------------------------------------------------------------------------- #
# 2. 畫布上真的沒有陰影了
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_nothing_darker_than_the_backdrop_is_painted_under_a_card(qapp,
                                                                  theme_name):
    """**真的畫一次**，看卡片右下角外面那一塊有沒有比底色暗的東西。

    問畫素而不是問「程式碼裡還有沒有 drawRoundedRect」：陰影的定義是「畫在卡片
    外面、比底色暗」，而那件事只有畫出來才看得到。
    """
    theme_mod.apply_theme(qapp, theme_name)
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1000, 700)
    win.show()
    qapp.processEvents()
    first_source(win)
    qapp.processEvents()
    view = win.pipeline
    view.tidy()
    view.reset_zoom()
    # **先取消選取。** 加一張卡進來它就是選中的，而選中的卡有一圈畫在邊框
    # **外面**的 accent 光暈（F7 起就有）—— 那圈東西正好落在探測框裡，量到的
    # ΔL* 42.6 是它不是陰影。這一條問的是「沒有選、沒有 hover 的那張卡下面
    # 有沒有東西」。
    view.set_selected(None)
    qapp.processEvents()

    item = view.node_item(view.node_ids()[0])
    body = QRectF(item.scenePos(),
                  QPointF(item.scenePos().x() + canvas_mod.NODE_W,
                          item.scenePos().y() + item.height()))
    # 卡片右下角外面 12×12 的一塊 —— 舊的陰影偏移 (1.5, 2.5)，就落在這裡
    probe = QRectF(body.right() - 2.0, body.bottom() - 2.0, 14.0, 14.0)
    img = QImage(28, 28, QImage.Format_ARGB32)
    # **用底色預填，不要用透明。** `QGraphicsScene.render` 不會呼叫 view 的
    # `drawBackground`（那支是畫在 view 上的），所以沒有圖元的地方會留白 ——
    # 透明的 (0,0,0,0) 讀出來是純黑，整張圖看起來就像鋪滿了陰影。
    img.fill(QColor(theme_mod.TOKENS["canvas_bg"]))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    view.scene().render(p, img.rect(), probe)
    p.end()
    win.close()
    theme_mod.apply_theme(qapp, "light")

    back = _lab_L(theme_mod.PALETTES[theme_name]["canvas_bg"])
    darkest = min(_lab_L(img.pixelColor(x, y).name())
                  for x in range(img.width()) for y in range(img.height()))
    # 卡片本身的 1px 邊框可能擦到探測框的邊，所以留 2.5 的餘裕；
    # 舊的陰影是 ΔL* 15.7，離這條線很遠。
    assert back - darkest < 2.5, (
        "%s：卡片外面畫了比底色暗 ΔL* %.1f 的東西 —— 陰影回來了"
        % (theme_name, back - darkest))


# --------------------------------------------------------------------------- #
# 3. hover 中的按鈕不能跟它坐的底同亮度
# --------------------------------------------------------------------------- #
#: 一顆 hover 中的按鈕與它坐的底至少要差這麼多 L*。
#:
#: **這個數字不是憑感覺訂的，是從已經出貨的東西推出來的。** 工具列那一排白鈕
#: 平常就是 100.0 坐在 97.6 上（差 2.4），F7-24 量過並且接受了那個薄度；
#: 它們 hover 之後是 95.4，差 2.1 —— 同一個薄度的另一側。
#:
#: 所以底線是 **2.0**：出貨中最薄的那一階就在 2.1，而 `bg_page` 以前的 1.1
#: 掉在它下面一半。訂 3.0 的話會連工具列一起判死，而那不是這一輪要改的東西
#: （第一版就是這樣寫的，測試當場指著 `light/toolbar ΔL* 2.1` 說話）。
#:
#: ⚠ 工具列現在**貼著這條線**（2.1）。誰要再動 `hover_warm` 或 `toolbar`，
#: 這條會先擋下來 —— 那時候該做的是把工具列那一階也一起想清楚，不是調門檻。
MIN_HOVER_ON_GROUND = 2.0


def test_a_hovered_button_does_not_vanish_into_the_surface_it_sits_on(qapp):
    """**這是 #6 那個決定的另一半。**

    亮色的白鈕 hover 之後是 L* 95.4，而 `bg_page` 以前是 96.5 —— 差 1.1。
    滑上去的那一刻，按鈕跟它坐的地板幾乎同亮度，填色不再幫忙分辨圖與地
    （只剩 `border_hover` 撐著）。跟卡片以前需要一塊陰影是同一個病：
    **明度階不夠用**。

    ⚠ 問的是**每一種底**，不是只有出問題的那一個 —— 下一次有人調 `hover_warm`
    或某個底色時，這條會替他問一次三個都還成不成立。
    """
    bad = []
    for theme_name in ("light", "dark"):
        pal = theme_mod.PALETTES[theme_name]
        hover = _lab_L(pal["hover_warm"])
        for ground in ("bg_page", "toolbar", "bg_panel"):
            delta = abs(_lab_L(pal[ground]) - hover)
            if delta < MIN_HOVER_ON_GROUND:
                bad.append("%s/%s ΔL* %.1f" % (theme_name, ground, delta))
    assert bad == [], (
        "hover 中的按鈕跟它坐的底幾乎同亮度：%s" % bad)


def test_the_dark_theme_never_had_this_problem(qapp):
    """暗色的 hover 是**往亮**走（離開地板），亮色是往暗走（走向地板）。

    寫下來是因為「兩個主題各調一次」很容易變成「兩個主題各有一套規則」——
    這條說的是：暗色不用改，不是忘了改。
    """
    pal = theme_mod.PALETTES["dark"]
    assert _lab_L(pal["hover_warm"]) > _lab_L(pal["bg_surface"]) > _lab_L(pal["bg_page"]), (
        "暗色的 hover 不再是往亮走了 —— 那條規則要重看")


# --------------------------------------------------------------------------- #
# 4. 點陣底沒有跟著變淡
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ("light", "dark"))
def test_the_dots_did_not_fade_when_the_backdrop_got_deeper(qapp, theme_name):
    """底色壓深了，點要一起壓 —— 不然那層對齊參考會**安靜地**淡一階。

    F79 才剛讓點陣底變成真的對齊參考（`GRID` 與版面同一套），這一輪把底色壓深
    的話，不動點就等於把剛買回來的東西又還回去一半。
    """
    pal = theme_mod.PALETTES[theme_name]
    delta = abs(_lab_L(pal["canvas_grid"]) - _lab_L(pal["canvas_bg"]))
    assert delta >= 9.0, (
        "%s：點跟底只差 ΔL* %.1f，那層對齊參考看不太出來了" % (theme_name, delta))
