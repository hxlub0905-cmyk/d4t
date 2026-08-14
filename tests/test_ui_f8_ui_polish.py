# F8-UI 驗收：畫布再往 n8n 靠（使用者 2026-08-14 的 3-1～3-4）。
"""四件事，全部是「看起來」的事，但每一件都鎖得住：

* 3-1 連線要**水平離埠、水平進埠**（切線不夠平，曲線就退化成斜的直線）；
  自動排版要跟上游對齊（barycenter），讓大部分的線根本不用斜。
* 3-2 卡片要回應：hover 邊框亮一階（由 view 判斷 —— 卡片自己收 hover
  會把線上的 × 悶死，見 test_ui_canvas_cut_button）、選中有光暈。
* 3-3 設定是**畫布右緣的抽屜**，畫布永遠整欄大小 —— 不再被砍掉四成高度。
* 3-4 右欄與參數區的間距走 8px 節奏。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes" \
    / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import canvas as canvas_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f8_ui")), n=4, seed=11)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1400, 900)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 3-1 線的形狀與排版
# --------------------------------------------------------------------------- #
def test_forward_edges_leave_and_enter_horizontally(window, qapp):
    """往前走的線，離埠的那一小段要貼著出發埠的高度 —— 切線是水平的。

    推力太小（以前最小 40px）時三次貝茲退化成斜的直線，n8n 那種
    「資料水平流動」的秩序感就沒了。鎖 10% 處的縱向偏移。
    """
    window.show()
    qapp.processEvents()
    checked = 0
    for edge in window.pipeline._edges:
        a = edge.src.out_port(edge.port)
        b = edge.dst.in_port()
        if b.x() - a.x() < 2 * edge.BACK_REACH:
            continue                    # 往回走的線走另一個形狀（F7-24）
        if abs(b.y() - a.y()) < 8:
            continue                    # 同列的線本來就近似水平，驗不出東西
        p10 = edge.path().pointAtPercent(0.10)
        drop = abs(p10.y() - a.y())
        total = abs(b.y() - a.y())
        assert drop < total * 0.25, (
            "%s → %s 在 10%% 處已經掉了 %.0f/%.0f px —— 這是斜線不是曲線"
            % (edge.src.node_id, edge.dst.node_id, drop, total))
        checked += 1
    assert checked, "這份 recipe 應該有跨列的前行線可驗"


def test_layout_aligns_children_with_their_parents(qapp):
    """同欄的列序照上游的位置排（barycenter），讓線根本不用交叉。

    a(第0列)、b(第1列)；x 接 b、y 接 a。照舊排法（原順序）x 在第 0 列、
    y 在第 1 列 —— 兩條線交叉。跟上游對齊之後 y 在上、x 在下，零交叉。
    """
    pos = canvas_mod.layout_columns(
        ["a", "b", "x", "y"], [("b", "x"), ("a", "y")])
    assert pos["a"][1] < pos["b"][1]
    assert pos["y"][1] < pos["x"][1], "y 的上游在第 0 列，它就該排在 x 上面"


# --------------------------------------------------------------------------- #
# 3-2 卡片的回應
# --------------------------------------------------------------------------- #
def test_hover_is_tracked_by_the_view_not_the_item(window, qapp):
    """hover 邊框由 view 判斷。卡片自己 **不可以** 收 hover 事件 ——
    一收，事件就穿不過去，壓在線中點上的卡會把「斷開」的 × 悶死。"""
    window.show()
    qapp.processEvents()
    nid = window.pipeline.node_ids()[0]
    item = window.pipeline.node_item(nid)
    assert item.acceptHoverEvents() is False, \
        "卡片不能自己收 hover（見 test_ui_canvas_cut_button）"

    view_pos = window.pipeline.mapFromScene(
        item.scenePos().x() + 20, item.scenePos().y() + 20)
    window.pipeline._sync_hover_node(view_pos)
    assert item._hover is True
    # 移到空白處就退
    far = window.pipeline.mapFromScene(-500.0, -500.0)
    window.pipeline._sync_hover_node(far)
    assert item._hover is False


def test_a_selected_card_paints_differently_from_a_plain_one(window, qapp):
    """選中要看得出來（光暈 + accent 框）。畫進 pixmap 比，不信屬性。"""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    window.show()
    qapp.processEvents()
    nid = window.pipeline.node_ids()[1]
    item = window.pipeline.node_item(nid)

    def shot():
        img = QImage(240, 80, QImage.Format_RGB32)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        p.translate(10, 10)
        item.paint(p, None, None)
        p.end()
        return img

    window.pipeline.set_selected(None)
    plain = shot()
    window.pipeline.set_selected(nid)
    selected = shot()
    diff = sum(1 for x in range(240) for y in range(80)
               if plain.pixelColor(x, y) != selected.pixelColor(x, y))
    assert diff > 300, "選中前後只差 %d 個畫素 —— 光暈沒畫出來" % diff
    # 光暈畫在卡片邊緣之外，boundingRect 必須跟著蓋到（殘影守則，CLAUDE.md §7）
    br = item.boundingRect()
    assert br.top() <= -3.0 and br.bottom() >= canvas_mod.NODE_H + 3.0


# --------------------------------------------------------------------------- #
# 3-3 設定抽屜
# --------------------------------------------------------------------------- #
def test_settings_are_a_drawer_over_the_canvas(window, qapp):
    """攤開設定時畫布不變小 —— 抽屜浮在中欄右緣、吃滿高度。"""
    window.show()
    qapp.processEvents()
    col = window.canvas_column
    canvas_before = window.pipeline.size()

    nid = window.pipeline.node_ids()[1]
    window.select_node(nid)
    window.set_params_open(True)
    qapp.processEvents()

    assert window.params_open() is True
    drawer = window.param_drawer
    assert drawer.geometry().right() >= col.width() - 2, "抽屜要貼齊右緣"
    assert drawer.geometry().height() == col.height(), "抽屜要吃滿整欄高度"
    assert drawer.width() >= 320, "窄過 320px 的參數表塞不下一支滑桿"
    assert window.pipeline.size() == canvas_before, \
        "畫布被抽屜擠小了 —— 它該浮在上面，不是搶版面"

    window.set_params_open(False)
    assert window.params_open() is False
    assert drawer.isHidden(), "收起來就要不見，不能留一條空欄"


def test_the_drawer_has_a_close_button(window, qapp):
    """抽屜要有自己的關閉鈕 —— 「怎麼把它弄走」不能只靠再雙擊一次卡片。"""
    window.set_params_open(True)
    window.btn_close_params.click()
    assert window.params_open() is False


# --------------------------------------------------------------------------- #
# 3-4 間距節奏
# --------------------------------------------------------------------------- #
def test_the_preview_column_walks_an_8px_grid(window):
    """右欄的留白是 8 的倍數 —— 「差一點對齊」比沒對齊更亂。"""
    lay = window.preview_pane.layout()
    m = lay.contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (8, 8, 8, 8)
    assert lay.spacing() == 8
