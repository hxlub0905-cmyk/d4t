# F7-18 驗收：影像流是節點的事，不是控制列的事。
"""使用者的三件回饋，全部指向同一句話：**test 與 ref 是兩張不同的輸入影像，
兩張都要可以獨立操作，而「要對哪一張做」應該用節點講。**

1. 輸出埠上那顆「+」會永久掛在畫面上 → 拿掉，改從旁邊的卡片庫加。
2. 虛線（隱含順序）跟實線同一個顏色 → 給它自己的色相。
3. 很多卡片把 ref 當附帶（``also_apply``），而且兩個節點之間只拉得動一條線
   → 一張卡一條流；從哪個埠拉線就決定那張卡做在哪一條流上。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes"


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


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1200, 700)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 一張卡一條流
# --------------------------------------------------------------------------- #
ENHANCE_CARDS = ("percentile_norm", "glv_mask_norm", "denoise", "flatten",
                 "local_contrast", "brightness_contrast", "gamma")


def test_no_enhance_card_quietly_writes_a_second_stream():
    """這是這一輪的核心不變量。

    一張卡寫兩條流有兩個後果，兩個都只有在**看不到**的地方發作：畫布上那張卡
    看起來只在一條鏈上，但它其實動了另一條；而「要不要一起動」變成控制列裡的
    一組勾選框，於是 test 是主角、ref 是附帶。
    """
    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline import get_step

    for key in ENHANCE_CARDS:
        cls = get_step(key)
        params = cls.validate_params({})
        assert cls.resolve_writes(params) == [params.get("target")
                                              or params.get("source")], key
        names = [p.name for p in cls.params]
        assert "also_apply" not in names, key
        assert "anchor" not in names, key


def test_the_two_normalize_cards_can_still_share_one_range():
    """唯一會被「一張卡一條流」弄丟的能力，要有一個看得見的替代品。

    ``anchor="source"`` 的意思是「ref 用 test 量出來的範圍」—— 那是「兩張圖
    正規化完還比得起來」的關鍵。現在它是 ``range_from``，而且它是一條**影像流
    的名字**，所以在畫布上就是接進這張卡的第二條線。
    """
    import numpy as np

    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context

    row = np.linspace(0, 255, 128).astype(np.uint8)
    src = np.tile(row, (128, 1))
    half = (src.astype(np.float32) / 2).astype(np.uint8)

    cls = get_step("percentile_norm")
    assert cls.resolve_reads(cls.validate_params({"source": "ref"})) == ["ref"]
    assert cls.resolve_reads(cls.validate_params(
        {"source": "ref", "range_from": "test"})) == ["ref", "test"]

    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
    cls().run(ctx, {"source": "ref", "range_from": "test"})
    cls().run(ctx, {"source": "test"})
    assert ctx.images["test"].max() == 255
    # ref 借了 test 的範圍 → 它保持「只有一半亮」，兩張仍然比得起來
    assert abs(ctx.images["ref"].mean() - ctx.images["test"].mean() / 2) < 8


def test_old_recipes_with_also_apply_still_load_and_mean_the_same_thing(tmp_path):
    """recipe 是拿來交接的檔案。認不得舊的字等於「工具壞了」。"""
    import json

    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline.recipe import Recipe

    raw = {
        "recipe_id": "legacy", "version": 1,
        "routes": {"ebi_patch": ["load", "norm", "dn"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "norm": {"step": "percentile_norm",
                     "params": {"source": "test", "also_apply": "ref",
                                "anchor": "source"}},
            "dn": {"step": "denoise",
                   "params": {"target": "test", "also_apply": "ref"}},
        },
        "score": {"expr": "1", "threshold": 0.0, "bins": {"below": 0, "above": 1}},
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    rec = Recipe.load(path)
    route = rec.routes["ebi_patch"]
    assert route == ["load", "norm_ref", "norm", "dn", "dn_ref"]

    # anchor=source：借範圍的那張要排在**前面**，此時 test 還沒被拉伸過 ——
    # 反過來的話 ref 借到的是「已經拉成 0–255」的範圍，數字就不一樣了。
    assert rec.nodes["norm_ref"].params == {"source": "ref", "range_from": "test",
                                            }
    assert rec.nodes["norm"].params == {"source": "test", "range_from": ""}
    # denoise 是逐張獨立的運算，順序無所謂，維持原本的先後
    assert rec.nodes["dn_ref"].params["target"] == "ref"
    assert rec.nodes["dn"].params["target"] == "test"

    # 存回去就是新格式（再讀一次不會又長出節點）
    out = tmp_path / "again.json"
    rec.save(out)
    assert "also_apply" not in out.read_text(encoding="utf-8")
    assert Recipe.load(out).routes["ebi_patch"] == route


def test_the_shipped_examples_are_already_in_the_new_shape():
    for path in sorted(EXAMPLE.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "also_apply" not in text, path.name
        assert '"anchor"' not in text, path.name


# --------------------------------------------------------------------------- #
# 2. 連線說出「這張卡做在哪一條流上」
# --------------------------------------------------------------------------- #
def test_dragging_from_the_ref_port_points_the_card_at_ref(window):
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise", "test")
    assert window.model.nodes[nid].params["target"] == "test"

    # 從 Input 的第二個輸出埠（ref）拉一條線過去
    window.pipeline.link_to(src, nid, port=1)
    assert window.model.nodes[nid].params["target"] == "ref"
    assert "ref" in window.status_text()


def test_a_second_line_between_the_same_two_cards_is_not_refused(window):
    """使用者原話：「很多張卡片都會限制或阻撓」。

    先從 test 拉、再從 ref 拉是很正常的操作（「我改變主意了」），而以前那第二
    條線只會得到一句 already connected 然後什麼都沒發生 —— 畫面上看起來就像
    這張卡不准你碰 ref。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "gamma", "test")
    window.pipeline.link_to(src, nid, port=0)
    assert window.model.has_edge(src, nid) is True

    window.pipeline.link_to(src, nid, port=1)      # 同一對節點，另一個埠
    assert window.model.nodes[nid].params["target"] == "ref"
    assert "ref" in window.status_text()


def test_a_line_that_would_loop_leaves_no_trace(window):
    """會成環的那條線沒有落地 —— 它不該留下任何痕跡，尤其不是「那張卡安靜地
    改成做 ref 了」。"""
    src = window.model.node_order[0]
    first = window.add_card_after(src, "denoise", "test")
    second = window.add_card_after(first, "gamma", "ref")   # 它的輸出埠是 ref
    assert (first, second) in window.model.edges

    window.pipeline.link_to(second, first, port=0)   # 反過來拉：會成環
    assert window.model.has_edge(second, first) is False
    assert window.model.nodes[first].params["target"] == "test"
    assert "Cannot connect" in window.status_text()
    assert window.status_level() == "error"


def test_wiring_a_card_with_no_stream_parameter_changes_nothing(window):
    """Compare 卡有自己的 a / b 兩個輸入，連線不該亂改它們。"""
    src = window.model.node_order[0]
    a = window.add_card_after(src, "align", "test")
    sub = window.add_card_after(a, "subtract")
    before = dict(window.model.nodes[sub].params)
    window.pipeline.link_to(src, sub, port=1)
    assert window.model.nodes[sub].params == before


def test_adding_from_the_library_follows_the_selected_card(window):
    """「+」拿掉之後，卡片庫要接得下它的工作：接在選著的那張後面、同一條流。"""
    src = window.model.node_order[0]
    on_ref = window.add_card_after(src, "denoise", "ref")
    window.select_node(on_ref)

    window._on_add_requested("gamma")
    nid = window.selected_node
    assert nid != on_ref
    assert window.model.nodes[nid].params["target"] == "ref"
    order = window.model.node_order
    assert order.index(on_ref) < order.index(nid)
    assert (on_ref, nid) in window.model.edges


# --------------------------------------------------------------------------- #
# 3. 虛線不能跟實線同一個顏色
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_implicit_edge_has_its_own_hue(qapp, theme_name):
    """同色淡一點只說得出「比較不重要」。這兩種線是不同的東西：一條是使用者
    拉的（刪得掉），一條是卡片排列帶來的順序（刪不掉，虛線的意思是「這裡可以
    拉」）。而深淺在縮放與換主題之後就不一定分得出來了。"""
    from PySide6.QtGui import QColor

    theme_mod.apply_theme(qapp, theme_name)
    solid = QColor(theme_mod.TOKENS["canvas_edge"])
    dashed = QColor(theme_mod.TOKENS["canvas_edge_implicit"])
    assert dashed.isValid() and solid.isValid()
    # 色相差得出來（不是同一個灰的深淺），而且亮度不能差太多（同一套色票）
    assert abs(dashed.hue() - solid.hue()) > 20
    assert abs(dashed.lightness() - solid.lightness()) < 70
    theme_mod.apply_theme(qapp, "light")


def test_the_canvas_actually_paints_the_two_kinds_differently(window, qapp):
    """token 換了不代表畫出來不一樣 —— ``paint()`` 也要真的去讀它。"""
    from PySide6.QtGui import QColor, QPixmap

    assert window.load_recipe_path(str(EXAMPLE / "die_to_die_basic.json"),
                                   sync=True) is True
    # 這份範例只有 route 順序（全虛線）—— 親手拉一條，兩種線才都在畫面上。
    window._on_edge_added("load", "sub", "test")
    edges = window.pipeline._edges
    assert any(e.implicit for e in edges), "這份 recipe 應該有隱含順序的虛線"
    assert any(not e.implicit for e in edges), "也要有使用者拉的實線"

    def dominant_hue(edge):
        """畫出來那條線的主色相（抗鋸齒會混出一堆中間色，取最常見的那個）。"""
        from PySide6.QtGui import QPainter

        rect = edge.boundingRect()
        pm = QPixmap(int(rect.width()) + 4, int(rect.height()) + 4)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        p.translate(-rect.topLeft())
        edge.paint(p, None, None)
        p.end()
        img = pm.toImage()
        counts = {}
        for x in range(img.width()):
            for y in range(img.height()):
                c = img.pixelColor(x, y)
                if c.hue() >= 0 and c != QColor("#ffffff"):
                    counts[c.hue()] = counts.get(c.hue(), 0) + 1
        assert counts, "這條線根本沒畫出有顏色的畫素"
        return max(counts.items(), key=lambda kv: kv[1])[0]

    solid = dominant_hue(next(e for e in edges if not e.implicit))
    dashed = dominant_hue(next(e for e in edges if e.implicit))
    assert abs(solid - dashed) > 60, (
        "虛線與實線畫出來仍然是同一個色相（solid=%d dashed=%d）" % (solid, dashed))
