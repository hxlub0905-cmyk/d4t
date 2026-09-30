# F8-UI 驗收：畫布再往 n8n 靠（使用者 2026-08-14 的 3-1～3-4）。
"""四件事，全部是「看起來」的事，但每一件都鎖得住：

* 3-1 連線要**水平離埠、水平進埠**（切線不夠平，曲線就退化成斜的直線）；
  自動排版要跟上游對齊（barycenter），讓大部分的線根本不用斜。
* 3-2 卡片要回應：hover 邊框亮一階（由 view 判斷 —— 卡片自己收 hover
  會把線上的 × 悶死，見 test_ui_canvas_cut_button）、選中有光暈。
* 3-3 → D 案（使用者當天退掉右緣抽屜後拍板）：畫布只佔中欄**上面一塊**
  （它會 zoom），設定拿大頭；看全貌用 zoom bar 的**彈出視窗**，彈出時
  主視窗的設定自動補滿、關窗還原。
* 3-4 右欄與參數區的間距走 8px 節奏。

⚠ **F39-B3（2026-08-27）搬走了三條**到 ``tests/test_ui_canvas.py``：使用者拖過
的位置在重建畫布／彈出視窗之後還在、換一份 recipe 之後不繼承、卡片拖出邊界
``sceneRect`` 要跟著長大。那三條問的是畫布的性質，不是這一輪的打磨。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests.region_cards import (  # noqa: E402
    add_region_step, region_card,
)

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes" \
    / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
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
    # 虛線退役後畫布只畫顯式線 —— 自己拉一條跨列的前行線來驗形狀。
    order = window.model.node_order
    # 跨列的線 = 深度差剛好越過換行點，而換行點跟著畫布寬度走（F13-1）——
    # 寫死 `canvas_mod.WRAP` 的話，窄畫布上這條線根本不跨列，測不到形狀。
    window.model.add_edge(order[0], order[window.pipeline.wrap() + 1])
    qapp.processEvents()
    checked = 0
    for edge in window.pipeline._edges:
        a = edge.src.out_port(edge.port)
        b = edge.dst.in_port()
        if b.x() - a.x() < 2 * edge.BACK_REACH:
            continue                    # 往回走的線走另一個形狀（F7-24）
        if abs(b.y() - a.y()) < 8:
            continue                    # 同列的線本來就近似水平，驗不出東西
        path = edge.path()
        if path.elementCount() > 4:
            # 繞過中間那張卡的折線（F124 期 3）：它的第一段本來就是水平的，
            # 驗的是「離埠那一段貼著埠的高度」，不是 10% 處。
            p = path.pointAtPercent(path.percentAtLength(edge.SIDE / 2.0))
            assert abs(p.y() - a.y()) < 1.0, (edge.src.node_id, edge.dst.node_id)
            checked += 1
            continue
        p10 = path.pointAtPercent(0.10)
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

    # 沒按鍵的滑鼠移動要送得進 mouseMoveEvent —— viewport 的 mouseTracking
    # 必須開著（QGraphicsView 預設就開，這裡鎖住「它不准被關掉」；
    # 關掉的症狀是 hover 只在拖曳時有效，PR #6 review 提出的情境）。
    assert window.pipeline.viewport().hasMouseTracking() is True

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
    # 光暈畫在卡片邊緣之外，boundingRect 必須跟著蓋到（殘影守則，docs/PITFALLS.md）
    br = item.boundingRect()
    assert br.top() <= -3.0 and br.bottom() >= canvas_mod.NODE_H + 3.0


# --------------------------------------------------------------------------- #
# 3-3 → D 案：畫布佔中上一塊、設定拿大頭、看全貌用彈出視窗
#（右緣抽屜當天被使用者退掉：「pipeline 往右長，抽屜也吃右邊，
#  兩個在搶同一個方向的空間」。）
# --------------------------------------------------------------------------- #
def test_the_canvas_is_the_top_block_and_settings_get_the_rest(window, qapp):
    """中欄上下切：畫布在上、設定在下，而且**設定拿大頭** ——
    畫布會 zoom、又有彈出視窗，平面上不需要大面積。"""
    window.show()
    window.resize(1400, 900)
    qapp.processEvents()
    col = window.canvas_column
    assert col.widget(0) is window.pipeline, "畫布要在中欄的上面"
    # ⚠ U8（2026-09-08）曾把儀表併進這一格；F100 v3 把它搬回右欄（影像下面），
    # 所以下半現在**只有** `stack` —— 設定區拿整個中欄的寬度。
    assert col.widget(1) is window.params_row, "設定在下面"
    assert window.params_row.widget(0) is window.stack
    assert window.params_row.count() == 1, "v3：儀表不在工作台裡"
    assert window.right_column.widget(1) is window.gauge_pane, "v3：儀表在影像下面"

    # F100（2026-09-08）：影像住進工作台的第三格，所以**工作台開窗就攤開**
    # —— 收掉它等於把影像藏起來。F13-1 那條「沒選卡片時收起來」的理由（那塊
    # 空白壓到畫布）在新版面上不成立：畫布現在吃滿寬度、高度有保底。
    assert window.right_column.widget(0) is window.preview_pane   # v3：右欄上影像下儀表
    assert window.params_open() is True, "F100：工作台開窗就攤開（影像在裡面）"
    top, bottom = col.sizes()
    assert top > 0 and bottom > 0

    # 選了卡片：工作台仍然開著，而且**工作台拿大頭**（畫布保底 40%）。
    window.select_node(window.model.node_order[0])
    assert window.params_open() is True
    top, bottom = col.sizes()
    assert bottom > top, "工作台要拿大頭（畫布 40 / 工作台 60）：%s" % col.sizes()

    # 使用者自己收起來（「現在只想看流程」）仍然做得到。
    window.set_params_open(False)
    assert window.canvas_column.sizes()[1] == 0, "收起來時畫布拿整欄"
    window.set_params_open(True)


def test_the_canvas_takes_the_column_in_build_mode(window, qapp):
    """**「看全貌」不再是第二個視窗**（U5，2026-09-08）。

    這一條以前叫 `test_the_canvas_pops_out_into_its_own_window`：zoom bar 上
    那顆鈕會開一個 `QDialog`，裡面第二份 `PipelineCanvas` 接同一個 model。
    那條路 work，但代價是**兩份畫布實體與兩份狀態** —— 每個訊號接兩次、每次
    重畫記得兩邊都畫，而畫布明明是這個工具的賣點卻是螢幕上第三大的東西。

    現在同一顆鈕換版面：Build = 畫布吃滿中欄。**切換不重建畫布** ——
    node id 與選取狀態原封不動。
    """
    window.show()
    window.resize(1400, 900)
    qapp.processEvents()
    assert window.layout_mode() == "tune"
    assert len(window._canvases()) == 1, "只該有一份畫布"

    nid = window.pipeline.node_ids()[1]
    window.select_node(nid)
    before_ids = window.pipeline.node_ids()

    window.set_layout_mode("build")
    qapp.processEvents()
    assert window.layout_mode() == "build"
    assert window.canvas_column.sizes()[1] == 0, "Build 模式畫布吃滿整欄"
    assert len(window._canvases()) == 1, "換模式不該多出一份畫布"
    assert window.pipeline.node_ids() == before_ids, "切模式不重建畫布"
    assert window.pipeline.selected() == nid, "選取狀態要留著"

    # 加一張卡照樣長出來（同一份畫布，不必再同步第二份）
    n2 = wire_up(window.model, window.model.add_step("denoise"))
    qapp.processEvents()
    assert n2 in window.pipeline.node_ids()

    window.set_layout_mode("tune")
    qapp.processEvents()
    assert window.canvas_column.sizes()[0] > 0, "切回來畫布不該佔整欄"
    assert sum(window.canvas_column.sizes()) > 0

    # 切回來之後再動 model 不可以炸
    wire_up(window.model, window.model.add_step("tone"))
    qapp.processEvents()


# --------------------------------------------------------------------------- #
# 第五輪：量測卡的 overlay 與勾選的統計量
# --------------------------------------------------------------------------- #
def test_a_measure_card_draws_the_region_it_reads(window, qapp):
    """選著量測卡時，預覽要畫出**它在量的那個區域**（使用者：「mask 蓋在
    diff 上」）。以前只有 Region 卡畫框 —— 量測卡 roi 填錯只能用數字猜。"""
    m = window.model
    pr = wire_up(m, add_region_step(m, "roi_cross"))
    gs = wire_up(m, m.add_step("glv_stats"))
    m.set_param(gs, "roi", "cross")
    window.select_node(gs)
    window.refresh_preview(sync=True)
    qapp.processEvents()
    assert window.image_view.overlay_count() > 0, \
        "量測卡引用的區域沒有畫到預覽上"
    # Region 卡自己的框照舊
    window.select_node(pr)
    window.refresh_preview(sync=True)
    qapp.processEvents()
    assert window.image_view.overlay_count() > 0


def test_glv_metrics_are_ticked_not_typed(window, qapp):
    """統計量用勾的不是用打的（使用者要求）。清單外的手寫值（glv_q37）
    照樣列出來並勾著 —— 看不到就被靜靜刪掉是最糟的一種「幫忙」。

    F18 把勾選網格換成分群的膠囊（`MetricChips`）—— **這一條要的東西沒有變**，
    換的只有長相，所以測的仍然是「列得出來、勾著、值一字不差」。
    """
    from d4t.ui.widgets import MetricChips

    m = window.model
    gs = m.add_step("glv_stats")
    m.set_param(gs, "metrics", "glv_mean,glv_q37")
    window.select_node(gs)
    qapp.processEvents()
    editor = window.param_form.editor("metrics")
    assert isinstance(editor, MetricChips)
    assert "glv_q37" in editor.choice_names(), "recipe 帶來的自由值要列出來"
    assert editor.text() == "glv_mean,glv_q37"


# --------------------------------------------------------------------------- #
# 第五輪：右鍵平移 + 拖出邊界的卡片要捲得到
# --------------------------------------------------------------------------- #
def _mouse_event(etype, pos, button, buttons):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    # 6 參數版（含 globalPos）—— 5 參數版在 Qt6 是 deprecated，CI 會警告。
    return QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
                       canvas_mod.Qt.NoModifier)


def test_right_drag_pans_the_canvas(window, qapp):
    """右鍵按住拖曳 = 平移（使用者要求）。拖了就不出選單。"""
    from PySide6.QtCore import QEvent, QPoint

    window.show()
    qapp.processEvents()
    view = window.pipeline
    view.zoom_by(2.0)                      # 放大到一定捲得動
    qapp.processEvents()
    bar = view.horizontalScrollBar()
    # **兩邊都要有得捲**：停在頂到底的那一端時，往那個方向拖會被夾住，
    # 於是「沒有平移」與「捲不動了」在斷言上長得一樣。
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    h0 = bar.value()

    view.mousePressEvent(_mouse_event(
        QEvent.MouseButtonPress, QPoint(200, 80),
        canvas_mod.Qt.RightButton, canvas_mod.Qt.RightButton))
    view.mouseMoveEvent(_mouse_event(
        QEvent.MouseMove, QPoint(120, 60),
        canvas_mod.Qt.NoButton, canvas_mod.Qt.RightButton))
    assert view._pan_moved is True
    assert view.horizontalScrollBar().value() != h0, "畫布沒有跟著右鍵拖動"

    opened = []
    for item in view._items.values():
        item.show_context_menu = lambda *_a, it=item: opened.append(it)  # type: ignore
    view.mouseReleaseEvent(_mouse_event(
        QEvent.MouseButtonRelease, QPoint(120, 60),
        canvas_mod.Qt.RightButton, canvas_mod.Qt.NoButton))
    assert view._pan_last is None
    assert not opened, "拖曳之後放開不可以彈出右鍵選單"


def test_a_new_card_takes_its_regions_from_a_line_not_from_typing(window, qapp):
    """區域名不該要使用者重打一次 —— **而 F12 起那件事由一條線做，不是由
    自動填**。

    F8 當時的做法是加卡時把上游每一個區域名都填進那一格。區域變成畫布上的埠
    之後，那等於**自動幫他畫了好幾條他沒有拉過的線** —— 正是鐵則 10 擋的
    那件事。他仍然不必打字：埠就在上游那張卡的右邊，拉過去就是了。

    ⚠ **下游那張卡以前是 ``roi_mask``，而它 2026-09-02 刪掉了。** 換成
    ``glv_stats`` —— 它的 ``roi`` 同樣是 ``region_keys``（一串），走的是同一條
    路（``_autofill_new_card`` 那一支）。規矩沒有跟著那張卡走。
    """
    window.show()
    qapp.processEvents()
    with_regions = wire_up(window.model, add_region_step(window.model, "roi_cross"))
    qapp.processEvents()
    window.select_node(with_regions)
    window._on_add_requested("glv_stats")
    qapp.processEvents()
    nid = window.selected_node
    node = window.model.nodes[nid]
    assert node.step == "glv_stats"
    assert str(node.params.get("roi", "")) == "", \
        "加卡不准順手接線（鐵則 10）"

    outs = region_card("roi_cross").resolve_regions_out(
        window.model.nodes[with_regions].params)
    # 名字在上游那張卡的埠上（不必用抄的），拉一條線就填好了。
    assert outs
    item = window.pipeline.node_item(with_regions)
    assert set(outs) <= {d["name"] for d in item.out_specs()}
    window._on_edge_added(with_regions, nid, outs[0], "roi")
    assert window.model.nodes[nid].params["roi"] == outs[0]


# --------------------------------------------------------------------------- #
# 3-4 間距節奏
# --------------------------------------------------------------------------- #
def test_the_preview_column_walks_an_8px_grid(window):
    """右欄的留白是 8 的倍數 —— 「差一點對齊」比沒對齊更亂。"""
    lay = window.preview_pane.layout()
    m = lay.contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (8, 8, 8, 8)
    assert lay.spacing() == 8
