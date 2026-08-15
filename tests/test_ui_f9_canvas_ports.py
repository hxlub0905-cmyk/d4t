# F9 Phase 3d 後續：畫布不要說謊，也不要多話（2026-08-15，來自試用回饋）。
"""兩句使用者的原話，兩個問題。

1. **「為啥圖中會有卡有 3 個 node」** —— Normalize 有四個輸入埠
   （`streams` / `range_from` / `use_within` / `reference`），一份典型的
   recipe 只用到一兩個，其餘那幾顆空圓點常駐在節點旁邊跟資料流搶畫面，
   而且使用者會問「這一顆要接什麼」，答案卻是「什麼都不用接」。
   （同 F7-8「常駐在節點旁邊的裝飾」那條教訓。）

2. **「Normalize 前面接 test 但後方又出來 ref 這樣蠻怪的吧」** —— 副標印的是
   `ref test → ref`，讀起來就是「test 進去、ref 出來」。它其實做的是
   「正規化 **ref**，拉伸範圍跟 test **借**」。處理與借用是兩件事，
   混在箭頭左邊就會變成一句錯的話。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, studio_mod=studio_mod,
             theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    win.load_recipe_path(str(studio_mod.TEMPLATE_RECIPE))
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 沒接線的選配埠不畫
# --------------------------------------------------------------------------- #
def test_an_optional_port_with_nothing_wired_to_it_gets_no_dot(window):
    """``norm`` 只正規化 test，沒有借任何東西 —— 它只該有一顆輸入埠。"""
    item = window.pipeline.card("norm")
    assert item.in_port_names() == ["streams"], item.in_port_names()


def test_an_optional_port_that_is_actually_wired_keeps_its_dot(window):
    """``norm_ref`` 借了 test 的範圍，那條線要有落腳的地方。"""
    item = window.pipeline.card("norm_ref")
    names = item.in_port_names()
    assert "streams" in names and "range_from" in names, names
    # 沒用到的那幾顆（use_within / reference）不該出現
    assert len(names) == 2, names


def test_ports_you_must_connect_are_always_shown(window):
    """必接的埠不會因為「還沒接」就消失 —— 那樣使用者根本不知道要接什麼。"""
    assert window.pipeline.card("sub").in_port_names() == ["a", "b"]
    assert window.pipeline.card("align").in_port_names() == ["moving", "fixed"]


# --------------------------------------------------------------------------- #
# 2. 副標不准把「借來的」講成「處理的」
# --------------------------------------------------------------------------- #
def test_a_borrowed_stream_is_not_on_the_left_of_the_arrow(window):
    """箭頭只講這張卡**處理**什麼、產出什麼。"""
    sub = window.pipeline.card("norm_ref").subtitle()
    assert sub.endswith("ref → ref"), sub
    assert "test" not in sub, "借來的流不該出現在箭頭左邊：%s" % sub


def test_the_borrowed_stream_is_still_visible_somewhere(window):
    """拿掉之後不能變成「畫面上沒有任何地方說得出那條線是幹嘛的」。

    它搬到下面那一行的參數摘要 —— 那本來就是「這張卡這次被設定成做什麼」。
    """
    info = window.pipeline.card("norm_ref").info
    assert "range_from=test" in str(info.get("summary", ""))
    assert info.get("borrows") == ["test"]


def test_a_card_that_really_consumes_two_streams_still_says_both(window):
    """``subtract`` 是真的吃兩條流 —— 那一句本來就是對的，不要一起改掉。"""
    assert window.pipeline.card("sub").subtitle().endswith(
        "test ref_aligned → diff")
