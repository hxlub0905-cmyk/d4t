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

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes"


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
ENHANCE_CARDS = ("normalize", "tone", "denoise", "flatten")


def test_a_card_only_writes_the_streams_that_are_wired_into_it():
    """核心不變量還在，但**達成它的手段換了**（F7-18 → F7-19，計畫書 §23.1）。

    F7-18 保護的從來不是「一張卡一條流」—— 那只是當時最保守的手段。真正的
    不變量是**畫布不能說謊**：卡片動到的每一條流，在畫面上都要有一條線。
    ``also_apply`` 違反它是因為第二條流是控制列裡的一個勾選框，畫布上根本
    看不到。

    F7-19 讓一張卡吃 N 條流，但每一條都是接進來的、每一條都有埠 —— 不變量
    因此仍然成立。所以這條測試問的問題從「是不是只寫一條」改成
    **「寫出去的是不是正好等於接進來的那幾條」**，那才是不變量本身。

    ``also_apply`` / ``anchor`` 仍然不准回來：它們是「畫布上看不到的第二條流」
    的具體形狀。
    """
    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline import get_step

    for key in ENHANCE_CARDS:
        cls = get_step(key)
        # 預設：一條流進、同一條出
        params = cls.validate_params({})
        assert cls.resolve_writes(params) == ["test"], key
        # 兩條流進 → 正好那兩條出，一條不多
        both = cls.validate_params({"streams": "test,ref"})
        assert cls.resolve_writes(both) == ["test", "ref"], key
        names = [p.name for p in cls.params]
        assert "also_apply" not in names, key
        assert "anchor" not in names, key


def test_one_card_gives_both_streams_the_same_treatment():
    """F7-19 要買到的東西：成對的處理**不可能**再漂移開。

    F7-18 之後一份 recipe 會有一對 Normalize、一對 Denoise，而它們必須維持
    同樣的參數才比得起來 —— 改了一張忘了另一張是那個形狀帶進來的新的安靜
    失敗（計畫書 §22.7 第一條，原本打算用一條 lint warning 補）。

    一張卡就一組參數，所以這件事現在是**結構上不可能**，不是靠檢查擋。
    """
    import numpy as np

    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context

    img = np.tile(np.linspace(0, 200, 64).astype(np.uint8), (64, 1))
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    get_step("tone")().run(ctx, {"streams": "test,ref", "brightness": 20.0})
    assert np.array_equal(ctx.images["test"], ctx.images["ref"])


def test_two_streams_can_still_share_one_range():
    """``range_from`` 原樣保留 —— F7-19 沒有為它發明新東西（計畫書 §23.3）。

    ``anchor="source"`` 的意思是「ref 用 test 量出來的範圍」，那是「兩張圖
    正規化完還比得起來」的關鍵。它現在是 ``range_from``，是一條**影像流的
    名字**，所以在畫布上就是接進這張卡的第二條線。

    而且順序陷阱消失了：基準值在迴圈**之前**量好，那時候這張卡還沒改過任何
    東西 —— 兩條流是同一張卡處理的，中間插不進別的卡（§22.7 第三條）。
    """
    import numpy as np

    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context

    row = np.linspace(0, 255, 128).astype(np.uint8)
    src = np.tile(row, (128, 1))
    half = (src.astype(np.float32) / 2).astype(np.uint8)

    cls = get_step("normalize")
    assert cls.resolve_reads(cls.validate_params({"streams": "ref"})) == ["ref"]
    assert cls.resolve_reads(cls.validate_params(
        {"streams": "ref", "range_from": "test"})) == ["ref", "test"]

    # 兩張卡的老寫法（仍然合法）
    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
    cls().run(ctx, {"streams": "ref", "range_from": "test"})
    cls().run(ctx, {"streams": "test"})
    assert ctx.images["test"].max() == 255
    # ref 借了 test 的範圍 → 它保持「只有一半亮」，兩張仍然比得起來
    assert abs(ctx.images["ref"].mean() - ctx.images["test"].mean() / 2) < 8

    # 一張卡的新寫法：**結果必須一樣**，而且不必再擔心誰排前面
    one = Context(images={"test": src.copy(), "ref": half.copy()})
    cls().run(one, {"streams": "test,ref", "range_from": "test"})
    assert np.array_equal(one.images["test"], ctx.images["test"])
    assert np.array_equal(one.images["ref"], ctx.images["ref"])


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
    assert rec.nodes["norm_ref"].params == {"streams": "ref", "range_from": "test",
                                            "method": "percentile"}
    assert rec.nodes["norm"].params == {"streams": "test", "range_from": "",
                                        "method": "percentile"}
    # denoise 是逐張獨立的運算，順序無所謂，維持原本的先後
    assert rec.nodes["dn_ref"].params["streams"] == "ref"
    assert rec.nodes["dn"].params["streams"] == "test"

    # 轉成 JSON 就是新格式（再讀一次不會又長出節點）
    import json as _json
    text = _json.dumps(rec.to_json_dict(), ensure_ascii=False)
    assert "also_apply" not in text
    assert Recipe.from_json_dict(_json.loads(text)).routes["ebi_patch"] == route


def test_the_shipped_examples_are_already_in_the_new_shape():
    for path in sorted(EXAMPLE.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "also_apply" not in text, path.name
        assert '"anchor"' not in text, path.name


# --------------------------------------------------------------------------- #
# 2. 連線說出「這張卡做在哪一條流上」
# --------------------------------------------------------------------------- #
def test_dragging_from_the_ref_port_wires_ref_into_the_card(window):
    """從哪個埠拉線，就決定那張卡碰哪一條流 —— 這一點沒變。

    **變的是第二條線的意思**（F7-19，使用者第八輪回饋）。F7-18 當時定成
    「取代」（我改變主意了，這張卡改做 ref），因為那時一張卡本來就只做得了
    一條流。F7-20 之後一張卡吃 N 條，取代就變成擋路的：畫布上做得出來的最多
    一條，第二條得回控制列去勾 —— 而那正是 F7-18 想拿掉的東西。

    所以現在是**累加**：先 test 再 ref = 兩條都做。詳見
    ``test_ui_f7_19_wiring.py``。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "denoise", "test")
    assert window.model.nodes[nid].params["streams"] == "test"

    # 從 Input 的第二個輸出埠（ref）拉一條線過去
    window.pipeline.link_to(src, nid, port=1)
    assert window.model.nodes[nid].params["streams"] == "test,ref"
    assert "ref" in window.status_text()


def test_a_second_line_between_the_same_two_cards_is_not_refused(window):
    """使用者原話：「很多張卡片都會限制或阻撓」。

    先從 test 拉、再從 ref 拉是很正常的操作，而以前那第二條線只會得到一句
    already connected 然後什麼都沒發生 —— 畫面上看起來就像這張卡不准你碰 ref。
    **這條測試守的是「第二條線一定要有反應」**，那件事沒變。

    變的是那個反應是什麼：F7-18 是取代，F7-19 起是累加（兩條都做）。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "tone", "test")
    window.pipeline.link_to(src, nid, port=0)
    assert window.model.has_edge(src, nid) is True

    window.pipeline.link_to(src, nid, port=1)      # 同一對節點，另一個埠
    assert window.model.nodes[nid].params["streams"] == "test,ref"
    assert "ref" in window.status_text()


def test_a_line_that_would_loop_leaves_no_trace(window):
    """會成環的那條線沒有落地 —— 它不該留下任何痕跡，尤其不是「那張卡安靜地
    改成做 ref 了」。"""
    src = window.model.node_order[0]
    first = window.add_card_after(src, "denoise", "test")
    second = window.add_card_after(first, "tone", "ref")   # 它的輸出埠是 ref
    assert (first, second) in window.model.edge_pairs()

    window.pipeline.link_to(second, first, port=0)   # 反過來拉：會成環
    assert window.model.has_edge(second, first) is False
    assert window.model.nodes[first].params["streams"] == "test"
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

    window._on_add_requested("tone")
    nid = window.selected_node
    assert nid != on_ref
    assert window.model.nodes[nid].params["streams"] == "ref"
    order = window.model.node_order
    assert order.index(on_ref) < order.index(nid)
    assert (on_ref, nid) in window.model.edge_pairs()


# --------------------------------------------------------------------------- #
# 3. 虛線退役（2026-08-14）：route 順序不再畫成線
#    （F7-18 給了虛線自己的色相；使用者實測後整條退掉 ——「會混淆」。
#      這裡改鎖「真的沒畫」，孤兒 token 也一併移除。）
# --------------------------------------------------------------------------- #
def test_route_order_draws_no_dashed_lines(window, qapp):
    assert window.load_recipe_path(str(EXAMPLE / "die_to_die_basic.json"),
                                   sync=True) is True
    assert window.pipeline._edges == [], "route 順序不該畫成任何線"
    # 親手拉一條 → 唯一的線是實線
    window._on_edge_added("load", "sub", "test")
    assert len(window.pipeline._edges) >= 1
    assert "canvas_edge_implicit" not in theme_mod.TOKENS, \
        "虛線退役了，色票不要留孤兒 token"
