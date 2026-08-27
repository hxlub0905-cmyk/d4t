# F7-18 驗收：影像流是節點的事，不是控制列的事。
"""使用者的三件回饋，全部指向同一句話：**test 與 ref 是兩張不同的輸入影像，
兩張都要可以獨立操作，而「要對哪一張做」應該用節點講。**

1. 輸出埠上那顆「+」會永久掛在畫面上 → 拿掉，改從旁邊的卡片庫加。
2. 虛線（隱含順序）跟實線同一個顏色 → 給它自己的色相。
3. 很多卡片把 ref 當附帶（``also_apply``），而且兩個節點之間只拉得動一條線
   → 一張卡一條流；從哪個埠拉線就決定那張卡做在哪一條流上。

⚠ F39-B2b（2026-08-27）刪了三條**純重複**的：

* ``dragging_from_the_ref_port_wires_ref_into_the_card`` 與
  ``a_second_line_between_the_same_two_cards_is_not_refused``
  → ``test_ui_f7_19_wiring::test_wiring_a_second_stream_adds_it_instead_of_replacing``
  （F7-19 改了第二條線的意思，那一檔才是正典 —— 這兩條的 docstring 自己就
  指過去了）
* ``adding_from_the_library_lands_after_the_selected_card``
  → ``test_ui_canvas_one_line_per_input::test_the_new_card_still_lands_after_the_selected_one``

``a_line_that_would_loop_leaves_no_trace`` **沒有刪**：``test_ui_canvas`` 的
成環那條只問「線沒落地」，這一條多問了「那張卡沒有被安靜地改成做 ref」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source, wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes"


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
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step

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

    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

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

    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context

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

    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline.recipe import Recipe

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


def test_a_line_that_would_loop_leaves_no_trace(window):
    """會成環的那條線沒有落地 —— 它不該留下任何痕跡，尤其不是「那張卡安靜地
    改成做 ref 了」。"""
    src = first_source(window)
    first = window.add_card_after(src, "denoise")
    window._on_edge_added(src, first, "test")
    second = window.add_card_after(first, "tone")   # 它的輸出埠是 ref
    window._on_edge_added(first, second, "ref")
    assert (first, second) in window.model.edge_pairs()

    window.pipeline.link_to(second, first, port=0)   # 反過來拉：會成環
    assert window.model.has_edge(second, first) is False
    assert window.model.nodes[first].params["streams"] == "test"
    assert "Cannot connect" in window.status_text()
    assert window.status_level() == "error"


def test_wiring_a_card_lands_on_the_input_you_dropped_it_on(window):
    """Compare 卡的 a / b 是**兩顆分得開的輸入埠**（F10）。

    這條測試以前叫 `…_changes_nothing`，斷言「連線不該亂改 a / b」——
    那是 F10 之前的真相：那兩格靠預設值填好，畫布上那條線其實什麼都沒說，
    所以「接哪一顆都一樣」。使用者要的多連一正好要求相反的事：**線落在哪一格
    由使用者決定**，兩條線接進同一張卡的不同輸入才有意義。
    """
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    assert window.model.nodes[sub].params["a"] == ""
    assert window.model.nodes[sub].params["b"] == ""

    window.pipeline.link_to(src, sub, port=0, dst_port=0)   # test → First
    window.pipeline.link_to(src, sub, port=1, dst_port=1)   # ref  → Second
    assert window.model.nodes[sub].params["a"] == "test"
    assert window.model.nodes[sub].params["b"] == "ref"
    # 兩條線各自落在自己的埠上，畫布上不會疊在一起
    lines = {(e.src_out, e.dst_in) for e in window.model.edges if e.dst == sub}
    assert lines == {("test", "a"), ("ref", "b")}


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


# ---------------------------------------------------------------------------
# F9-6：同進同出 + 來源只在畫布上決定
# ---------------------------------------------------------------------------
def test_a_measure_card_still_has_an_output_port(window):
    """量測卡的 ``writes`` 是空的 —— 以前它在畫布上**沒有任何輸出埠**，
    線到那裡就斷了，後面接不下去也分不了支。

    F9-6：**接進來的每一條流，卡片後面也要接得出去**。引擎那邊本來就成立
    （跑一張卡的 local Context 是用它的輸入種出來的，跑完整份收成產出），
    這裡是把它畫出來。「不需要就不要連它」—— 多出來的埠不接線就沒有作用。
    """
    nid = wire_up(window.model, window.model.add_step("glv_stats"))
    window._refresh_all()
    card = window.pipeline.card(nid)
    assert card is not None
    outs = card.out_names()
    assert outs, "量測卡在畫布上沒有輸出埠 —— 鏈到這裡就斷了"
    from d4t.core.pipeline import get_step
    reads = list(get_step("glv_stats").resolve_reads(window.model.nodes[nid].params))
    for r in reads:
        assert r in outs, "接進來的 %s 沒有原樣送出去（同進同出）" % r


def test_a_card_that_makes_a_new_stream_also_passes_its_inputs_through(window):
    """會產生新流的卡（subtract → diff）：輸出埠 = 新流 **＋** 原本接進來的。

    使用者的原話：「這樣才會更 flexible，如果我不需其它後端接口，不要連他就好」。
    """
    nid = wire_up(window.model, window.model.add_step("subtract"))
    window._refresh_all()
    outs = window.pipeline.card(nid).out_names()
    assert "diff" in outs, "自己產的新流不見了"
    for r in ("test", "ref"):
        assert r in outs, "%s 沒有原樣送出去" % r
    assert outs.index("diff") < outs.index("test"), \
        "自己產的要排在前面（原樣送出的是附加的，不該搶第一顆埠）"


def test_the_source_cannot_be_changed_from_the_card_settings(window):
    """來源**只在畫布上決定**；設定區只顯示，不給改（使用者定調）。

    以前同一件事有兩個入口 —— 拉線會改它、設定區的下拉也會改它 —— 而兩邊很容易
    對不起來。這條測試同時鎖住「不能改」與「看得到」：唯讀不等於藏起來。
    """
    from PySide6.QtWidgets import QLineEdit

    nid = wire_up(window.model, window.model.add_step("denoise"))
    window.select_node(nid)
    editor = window.param_form.editor("streams")
    assert isinstance(editor, QLineEdit), "來源欄位還是可編輯的控制項"
    assert editor.isReadOnly() is True
    assert editor.text(), "看不到現在接的是哪一條 —— 唯讀不等於藏起來"
    assert editor.toolTip().strip(), "要講得出去哪裡改（推廣鐵則）"
