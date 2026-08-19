# 品牌資產驗收：Studio 的視窗圖示 — authored 2026-08-19。
"""圖示不是裝飾，它是**同一套三段式**在工作列上的樣子。

這個檔案鎖三件事：

1. `assets/` 裡那三個 SVG 在、而且是合法的 SVG（不是被編輯器存壞的半個檔案）；
2. Qt 真的畫得出來 —— PySide6 帶著 SVG image plugin，所以我們直接餵向量檔給
   `QIcon`，不轉點陣。**萬一哪天那個 plugin 沒被打包進去，這支測試會紅**，
   而不是等到使用者在廠內開起來看到一個空白圖示；
3. 圖示上那四顆點的顏色，跟 `theme.py` 的 dark palette **逐字相等**。
   有人改了分段色卻忘了改圖示，這裡就會擋下來 —— 畫布跟圖示講不同語言，
   對「不會寫 code 的使用者」來說就是兩個看起來無關的東西。

比的是 dark palette 而不是 light：磚是深色的，圖示上的藍/橙/紫本來就該用
深色底那一組。這幾個值不是用眼睛調的，是從 `theme.PALETTES["dark"]` 抄過去的。
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QIcon                       # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from adept.ui import theme                            # noqa: E402
from adept.ui.branding import (ASSETS_DIR, ICON_PATH,  # noqa: E402
                               WORDMARK_DARK_PATH, WORDMARK_PATH, app_icon)

SVG_NS = "http://www.w3.org/2000/svg"

#: 圖示是 64×64 的座標系；四顆點在哪、代表哪一段。
#: 座標直接對應 `assets/d4t.svg` 裡的 `<circle>`。
PORTS = (
    ("影像流進來（上）", 41, 13, "seg_image"),
    ("影像流進來（左）", 15, 38, "seg_image"),
    ("算法（交會點）",   41, 38, "seg_algo"),
    ("判定出去（下）",   41, 52, "seg_adc"),
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --------------------------------------------------------------------------
# 1. 檔案本身
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path,view_box", [
    (ICON_PATH, "0 0 64 64"),
    (WORDMARK_PATH, "0 0 168 60"),
    (WORDMARK_DARK_PATH, "0 0 168 60"),
])
def test_assets_are_wellformed_svg(path, view_box):
    assert os.path.isfile(path), "少了品牌資產：%s" % path
    root = ET.parse(path).getroot()
    assert root.tag == "{%s}svg" % SVG_NS
    assert root.get("viewBox") == view_box


def test_assets_dir_holds_only_what_we_ship():
    """`pyproject.toml` 的 package-data 是 `assets/*.svg` —— 別的東西不會跟著走。"""
    stray = [n for n in sorted(os.listdir(ASSETS_DIR))
             if not n.endswith(".svg")]
    assert stray == [], (
        "assets/ 裡有非 .svg 的東西，它不會被 package-data 收進去：%s" % stray)


# --------------------------------------------------------------------------
# 2. Qt 真的畫得出來
# --------------------------------------------------------------------------

def test_app_icon_loads(qapp):
    icon = app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull(), (
        "QIcon 讀不到 d4t.svg —— 多半是 Qt 的 SVG image plugin 沒被打包進去")


@pytest.mark.parametrize("size", [16, 32, 48, 256])
def test_app_icon_renders_at_every_size(qapp, size):
    pm = app_icon().pixmap(size, size)
    assert not pm.isNull()
    assert (pm.width(), pm.height()) == (size, size)


def test_missing_file_gives_empty_icon_not_a_crash(qapp, monkeypatch):
    """少一個檔案不該讓 Studio 開不起來（受限機器是用複製檔案部署的）。"""
    monkeypatch.setattr("adept.ui.branding.ICON_PATH",
                        os.path.join(ASSETS_DIR, "does-not-exist.svg"))
    assert app_icon().isNull()


# --------------------------------------------------------------------------
# 3. 圖示的顏色 = theme 的三段式
# --------------------------------------------------------------------------

@pytest.mark.parametrize("label,x,y,token", PORTS)
def test_ports_carry_the_stage_colours(qapp, label, x, y, token):
    img = app_icon().pixmap(256, 256).toImage()
    k = 256 / 64.0
    got = img.pixelColor(int(x * k), int(y * k)).name()
    want = theme.PALETTES["dark"][token]
    assert got == want, (
        "%s：圖示上是 %s，theme.PALETTES['dark']['%s'] 是 %s —— "
        "改了分段色就要一起改 adept/ui/assets/d4t.svg"
        % (label, got, token, want))
