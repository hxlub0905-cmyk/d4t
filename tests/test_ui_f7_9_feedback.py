# F7-9 驗收：第三輪試用回饋（顏色／埠／起手卡／影像流／卡片組合）。
"""這一輪的四個回饋加上一個提問，逐條鎖在這裡。

1. 「圖示很不錯，但太多都同個顏色（Input、Enhance、Compare 都是藍的）」
2. 「移動 Load images 時還是會有殘點（test 跟 ref）」＋「新增的節點只有前面有
   圓框，後面沒有」＋「一開始預設畫布上就應該有 load image 這個節點」
3. 「target 跟 also apply 要怎麼使用？對應的節點又是什麼？」
4. 「打開 compare 之後，點卡片時右上的 image stream 一直被切成 ref」
5. 「也請幫我確認目前的卡片操作與組合是否相互會有問題」

2 的前兩件事其實是**同一個 bug**：``paint()`` 拿場景座標去畫本地座標的東西。
節點在原點時看起來正常（第一欄的 Input 剛好在那），一離開原點，輸出埠與埠標
籤就被畫到「兩倍位移」的地方 —— 於是後面每張卡的右側圓點都跑到卡外面（看起來
像沒有），而拖動 Input 會把標籤留在 ``boundingRect`` 之外（擦不掉，就是殘影）。
所以這裡不測「畫面上看不看得到殘影」，而是測那個不變量本身。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from d4t.core.pipeline import (          # noqa: E402 — Qt-free，可以直接 import
    Recipe, RecipeNode, ScoreSpec, get_step, list_steps, validate,
)
import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊

FIXTURE_RECIPES = Path(__file__).resolve().parent / "fixtures" / "recipes"
#: repo 裡**現在**還在出貨的 recipe 全部住在這裡。
#:
#: 以前指的是 ``examples/recipes/``（教學範例）。那個目錄 2026-08-16 移除了，
#: 而 ``glob`` 對不存在的資料夾**回空清單、不丟例外** —— 下面那條測試會因此
#: 「檢查了 0 份 recipe」然後綠燈通過。指到 fixtures 才有東西可檢查。
EXAMPLE = FIXTURE_RECIPES / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import canvas as canvas_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui import viewmodel as vm_mod
    from d4t.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
             studio_mod=studio_mod, theme_mod=theme_mod, vm_mod=vm_mod,
             widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f7_9")), n=6, seed=11)


@pytest.fixture
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 六個階段六個顏色
# --------------------------------------------------------------------------- #
GROUPS = ("input", "enhance", "region", "compare", "measure", "adc")


def _lab(hex_str):
    """sRGB hex -> CIE L*a*b*（D65）。用感知距離判「看不看得出不一樣」。

    RGB 的算術距離跟眼睛看到的差異對不上（藍色差 40 看得出來，綠色差 40
    看不太出來），所以不要拿 RGB 距離當「顏色夠不夠分得開」的標準。
    """
    import math

    s = hex_str.lstrip("#")
    r, g, b = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(c):
        return c ** (1.0 / 3.0) if c > 0.008856 else 7.787 * c + 16.0 / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a, b):
    import math
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))))


def test_every_stage_has_its_own_colour(qapp):
    """回饋原話：「太多都同個顏色（input enhance 跟 compare 都是藍色）」。

    以前是 ``group -> category -> 顏色``，六個階段只有三種色。這裡鎖的是
    **性質**（兩兩感知上分得開），不是寫死色碼 —— 色票還可以再調。
    ΔE ≥ 25 大約是「一眼看得出是兩個顏色」而不只是「同色的深淺」。
    """
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        colours = {g: theme_mod.group_hex(g) for g in GROUPS}
        assert len(set(colours.values())) == len(GROUPS), \
            "%s 主題有階段共用顏色：%s" % (name, colours)
        for i, a in enumerate(GROUPS):
            for b in GROUPS[i + 1:]:
                d = _delta_e(colours[a], colours[b])
                assert d >= 25, "%s 的 %s 與 %s 太接近（%s vs %s, ΔE=%.1f）" % (
                    name, a, b, colours[a], colours[b], d)
    theme_mod.apply_theme(qapp, "light")


def test_the_stage_colours_stay_one_family(qapp):
    """分得開之外還要**看起來像一套**：同一主題內明度不可以亂跳。

    六個顏色如果亮度差很多，rail 上就會有幾個特別跳、幾個特別悶 ——
    那是「六個顏色」，不是「一套色票」。
    """
    for name in ("light", "dark"):
        theme_mod.set_theme(name)
        lums = [_lab(theme_mod.group_hex(g))[0] for g in GROUPS]
        assert max(lums) - min(lums) <= 15, \
            "%s 主題的階段色明度差太多：%s" % (name, [round(x) for x in lums])
    theme_mod.apply_theme(qapp, "light")


def test_the_library_and_the_canvas_use_the_same_stage_colour(qapp):
    """rail 上看到的顏色，跟畫布節點上的必須是同一個 —— 不然顏色不是語言。"""
    panel = widgets_mod.LibraryPanel()
    panel.set_steps([s.describe() for s in list_steps()])
    for gid in GROUPS:
        btn = panel.stage_buttons[gid]
        assert theme_mod.group_hex(gid) in btn.styleSheet() \
            or btn.icon.color == theme_mod.group_hex(gid)


# --------------------------------------------------------------------------- #
# 2. 埠：本地座標 vs 場景座標
# --------------------------------------------------------------------------- #
def _canvas_with_two_nodes(qapp):
    canvas = canvas_mod.PipelineCanvas()
    canvas.set_nodes([
        {"node_id": "load", "label": "Load images", "group": "input",
         "enabled": True, "summary": "", "reads": [], "writes": ["test", "ref"]},
        {"node_id": "sub", "label": "Subtract", "group": "compare",
         "enabled": True, "summary": "", "reads": ["test", "ref"],
         "writes": ["diff"]},
    ], [("load", "sub")])
    return canvas


def test_every_port_is_drawn_inside_the_nodes_bounding_rect(qapp):
    """``paint()`` 只准畫在 ``boundingRect`` 裡面，否則就是殘影。

    埠與埠標籤都畫在**本地座標**；``boundingRect`` 也是本地座標。把節點拖到
    任何地方，這個關係都不可以變 —— 這正是「移動 Load images 會留下 test /
    ref 殘點」與「後面的節點沒有圓框」的共同成因。
    """
    from PySide6.QtCore import QPointF

    canvas = _canvas_with_two_nodes(qapp)
    for pos in (QPointF(0, 0), QPointF(240, 130), QPointF(-90, 55)):
        for item in (canvas.card("load"), canvas.card("sub")):
            item.setPos(pos)
            rect = item.boundingRect()
            assert rect.contains(item.in_port_local()), "輸入埠畫到框外"
            for anchor, name in zip(item.out_anchors_local(), item.out_names()):
                assert rect.contains(anchor), \
                    "%s 的輸出埠 %r 畫到 boundingRect 外面" % (item.node_id, name)
                # 埠標籤畫在埠右邊 _PORT_LABEL_W 之內，也必須在框裡
                label_right = anchor.x() + canvas_mod._PORT_LABEL_W - 1
                assert label_right <= rect.right(), "埠標籤畫到框外（= 殘影）"


def test_scene_anchors_track_the_node_position(qapp):
    """場景座標 = 本地座標 + ``scenePos()``。連線用前者，繪製用後者。"""
    from PySide6.QtCore import QPointF

    canvas = _canvas_with_two_nodes(qapp)
    item = canvas.card("load")
    item.setPos(QPointF(311, 47))
    for local, scene in zip(item.out_anchors_local(), item.out_anchors()):
        assert scene == item.scenePos() + local
    assert item.in_port() == item.scenePos() + item.in_port_local()
    # 命中判定吃的是本地座標，拖走之後仍然要打得到
    assert item.out_port_at(item.out_anchors_local()[1]) == 1


def test_every_node_has_an_output_port_to_drag_from(qapp):
    """回饋原話：「新增的節點只有前面有圓框，後面沒有圓框讓人可以連」。"""
    canvas = _canvas_with_two_nodes(qapp)
    for nid in ("load", "sub"):
        item = canvas.card(nid)
        assert len(item.out_anchors_local()) >= 1
        for anchor in item.out_anchors_local():
            assert anchor.x() == canvas_mod.NODE_W, "輸出埠必須貼在節點右緣"


def test_output_ports_are_labelled_with_the_stream_they_carry(qapp):
    """埠標籤就是 ``target`` / ``also apply`` 下拉裡的那些名字（回饋 3）。"""
    canvas = _canvas_with_two_nodes(qapp)
    assert canvas.card("load").out_names() == ["test", "ref"]
    assert canvas.card("sub").out_names() == ["diff"]


def test_an_unwired_recipe_wraps_instead_of_running_off_the_screen(qapp):
    """九張還沒拉線的卡排成一列會超過 2500px，``fit()`` 只能縮到看不出字。

    （而且它有下限 —— 縮成小方塊比留捲軸更糟，所以結果是「一排讀不出來的
    小方塊 **加上** 一條捲軸」，兩邊都輸。）
    """
    ids = ["n%d" % i for i in range(9)]
    pos = canvas_mod.layout_columns(ids, [])
    assert max(c for c, _r in pos.values()) < canvas_mod.WRAP
    assert max(r for _c, r in pos.values()) == (len(ids) - 1) // canvas_mod.WRAP
    # 閱讀順序仍然是左到右、上到下
    assert pos["n0"] == (0, 0) and pos["n3"] == (3, 0) and pos["n4"] == (0, 1)

    width = canvas_mod.WRAP * (canvas_mod.NODE_W + canvas_mod.COL_GAP)
    assert width < 1200, "換行之後整張圖要塞得進一般的工作區寬度"


# --------------------------------------------------------------------------- #
# 2b. 起手卡
# --------------------------------------------------------------------------- #
def test_a_new_model_starts_empty(qapp):
    """F11 Enhance-4：**開窗不預先放載入卡**（使用者定調）。

    F7-9 起開窗就有一張 `load_patch`，那時候只有一張載入卡所以是純粹的好意。
    Input-4 把它拆成兩張（一顆好幾張 / 一顆一張）之後，預先放一張就是替使用者
    決定了他還沒決定的事 —— 而猜錯的那一半在畫布上看起來完全正常（兩顆埠 vs
    一顆埠）。
    """
    m = vm_mod.RecipeModel.starter()
    assert m.node_order == []
    assert m.dirty is False, "使用者還沒做任何事，不該被當成「改過」"


def test_the_studio_opens_with_an_empty_canvas(qapp):
    """這一支刻意**不用 `window` fixture**（那個 fixture 會先載一份資料，而載入
    資料本來就會補上一張載入卡）—— 問的是「剛開窗」那一刻。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.pipeline.node_ids() == []
        assert win.selected_node is None
    finally:
        win.close()


def test_opening_data_brings_in_the_card_that_data_needs(window):
    """開窗時不猜，但**載入資料時「哪一張」已經不是猜的** —— kind 就是答案。

    （`window` fixture 進來之前就載過一份 patch 資料。）
    """
    assert window.model.node_order == ["load_patch"]
    assert window.pipeline.card("load_patch").out_names() == ["test", "ref"]
    # 補進來的那張卡**不算「使用者做過的一步」**：Ctrl+Z 不該退掉它，
    # 關窗也不該因此問「要存檔嗎」。
    assert window.model.dirty is False
    assert window.model.can_undo() is False
    # 而且它是選起來的 —— 右欄立刻有東西可以看（一開窗那句「請先挑一張卡」
    # 在這個時候已經不是使用者需要的話了）。
    assert window.selected_node == "load_patch"


# --------------------------------------------------------------------------- #
# 3. 這張卡做在哪一條流上（F7-18 起：一張卡一條流）
# --------------------------------------------------------------------------- #
def test_stream_params_have_plain_language_labels(qapp):
    """參數名是 recipe 的鍵，不是給人看的字。"""
    for key in ("normalize", "tone", "denoise", "flatten"):
        params = {p["name"]: p for p in get_step(key).describe()["params"]}
        primary = params.get("streams")
        assert primary["label"] == "Image streams"
        # 說明要講出「流是畫布上的線」與 test / ref 是什麼
        assert "canvas" in primary["help"] and "ref" in primary["help"]


def test_image_keys_values_are_normalised(qapp):
    """``image_keys`` 是「一串影像流」的型別：手打的與勾出來的要等價。

    F7-18 之後沒有卡片用它（``also_apply`` 拆成節點了），但型別與正規化規則
    仍然是 ParamSpec 的契約 —— 值的格式跟輸入方式無關這件事要繼續成立。
    """
    from d4t.core.pipeline.step import ParamSpec

    spec = ParamSpec(name="streams", type="image_keys", default="",
                     direction="in",
                     help="which streams")
    assert spec.validate(" ref , ref ,,test ") == "ref,test"
    assert spec.validate("") == ""
    assert spec.validate("ref") == "ref"


def test_stream_picker_is_checkboxes_over_the_upstream_streams(qapp):
    picker = widgets_mod.StreamPicker(["test", "ref", "diff"], "ref")
    assert picker.stream_names() == ["test", "ref", "diff"]
    assert picker.text() == "ref"

    seen = []
    picker.changed.connect(seen.append)
    picker._boxes[0].setChecked(True)             # 也勾 test
    assert seen[-1] == "test,ref"
    picker._boxes[1].setChecked(False)            # 取消 ref -> 兩張圖分開處理
    assert seen[-1] == "test"


def test_a_stream_the_pipeline_no_longer_has_is_still_shown(qapp):
    """recipe 指到一條現在不存在的流時，不可以看不到就靜靜消失。"""
    picker = widgets_mod.StreamPicker(["test", "ref"], "ghost")
    assert "ghost" in picker.stream_names()
    assert picker.text() == "ghost"


def test_each_image_source_gets_its_own_card(window):
    """「test 跟 ref 就是兩張不同的 image source，都要可以做操作」（F7-18）。

    以前那件事是一張卡上的一組勾選框；現在它就是**兩張卡**，而畫布上因此看得到
    兩條各自的處理鏈。
    """
    src = first_source(window)
    on_test = window.add_card_after(src, "normalize")
    window._on_edge_added(src, on_test, "test")
    on_ref = window.add_card_after(src, "normalize")
    window._on_edge_added(src, on_ref, "ref")
    assert window.model.nodes[on_test].params["streams"] == "test"
    assert window.model.nodes[on_ref].params["streams"] == "ref"
    for nid in (on_test, on_ref):
        cls = get_step(window.model.nodes[nid].step)
        assert cls.resolve_writes(window.model.nodes[nid].params) == \
            [window.model.nodes[nid].params["streams"]]


# --------------------------------------------------------------------------- #
# 4. 點卡片時預覽顯示哪一張
# --------------------------------------------------------------------------- #
def test_selecting_a_card_shows_that_cards_main_stream(window):
    """回饋 4：點 Normalize 卻跳到 ref，並排時左右變成同一張 ref。

    成因是「這張卡寫過的最後一條流」被當成「這張卡的主要輸出」；當時 Enhance
    卡的 writes 是 ``[主流] + 附帶的那一串``，所以最後一項永遠是附帶的那條。
    """
    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
    assert window.select_node("norm") is True
    window.refresh_preview(sync=True)

    assert window.stream_combo.currentText() == "test", \
        "點 Normalize 應該看到它處理的 test"
    assert window.model.nodes["norm"].params["streams"] == "test"


def test_side_by_side_never_shows_the_same_image_twice(window):
    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
    assert window.set_compare(True) is True
    window.select_node("norm")
    window.refresh_preview(sync=True)
    left, right = window.stream_combo.currentText(), window.stream_combo_b.currentText()
    assert (left, right) == ("test", "ref")

    # 使用者親手把右邊挑成 ref 之後，再點別張卡也不可以變成左右都是 ref
    window._on_stream_b_changed("ref")
    for node_id in ("norm", "sub", "dn"):
        window.select_node(node_id)
        window.refresh_preview(sync=True)
        assert window.stream_combo.currentText() != window.stream_combo_b.currentText(), \
            "節點 %s：左右顯示同一條流" % node_id


# --------------------------------------------------------------------------- #
# 5. 卡片組合
# --------------------------------------------------------------------------- #
def _recipe(seq):
    nodes, order = {}, []
    for i, key in enumerate(seq):
        nid = "n%d" % i
        nodes[nid] = RecipeNode(id=nid, step=key,
                                params=get_step(key).validate_params({}))
        order.append(nid)
    return Recipe(recipe_id="combo", routes={"ebi_patch": order}, nodes=nodes,
                  score=ScoreSpec(expr="0", threshold=0.0,
                                  bins={"below": 0, "above": 1}))


def test_a_measure_card_that_needs_a_region_nobody_defines_is_caught(qapp):
    """以前這件事只有兩種下場，兩種都不好。

    名字打錯 → 每顆 defect 跑到一半 StepError；而且以前有一個保留字 ``blob``，
    上游沒有那張卡時會**安靜地改量整張圖** —— 跑得完、有數字、而且是錯的。
    （那個保留字隨著 ROI 收斂成 Profile / Template / GDS 一起拿掉了。）
    """
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "glv": RecipeNode("glv", "glv_stats", {"roi": "nobody_defines_this"}),
    }
    recipe = Recipe(recipe_id="r", routes={"ebi_patch": ["load", "glv"]},
                    nodes=nodes,
                    score=ScoreSpec(expr="1", threshold=0.5,
                                    bins={"below": 0, "above": 1}))
    codes = [i.code for i in validate(recipe, kind="ebi_patch")
             if i.level == "error"]
    assert "unknown-region" in codes

    # 補上一張 ROI 卡（Profile 定義 'nobody_defines_this'）之後就乾淨了
    nodes["roi"] = RecipeNode("roi", "roi_cross",
                              {"roi_out": "nobody_defines_this"})
    ok = validate(Recipe(recipe_id="r",
                         routes={"ebi_patch": ["load", "roi", "glv"]},
                         nodes=nodes,
                         score=ScoreSpec(expr="1", threshold=0.5,
                                         bins={"below": 0, "above": 1})),
                  kind="ebi_patch")
    assert [i.code for i in ok if i.level == "error"] == []


def test_measuring_two_regions_warns_instead_of_silently_losing_one(qapp):
    """特徵是**扁平的全域命名空間**，所以兩張同型別的量測卡會寫同一組名字。

    「量中心 vs 量整片」是使用者一定會做的事，而以前的下場是：跑得完、
    lint 全綠、後面那張把前面那張蓋掉，分數表達式**完全沒有辦法**指到前面
    那個值。這是 warning 不是 error（同名覆寫有時是刻意的），但它必須看得見。
    """
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        # 兩張 ROI 卡各給自己的 output_prefix —— 不然它們**自己**的特徵就先撞
        # 起來了，而這條測的是下面那兩張量測卡的撞名。
        "roiA": RecipeNode("roiA", "roi_cross",
                           {"roi_out": "center", "output_prefix": "a"}),
        "roiB": RecipeNode("roiB", "roi_cross",
                           {"roi_out": "wide", "place": "crossing",
                            "output_prefix": "b"}),
        "glvA": RecipeNode("glvA", "glv_stats",
                           {"roi": "center", "metrics": "glv_mean"}),
        "glvB": RecipeNode("glvB", "glv_stats",
                           {"roi": "wide", "metrics": "glv_mean"}),
    }
    recipe = Recipe(
        recipe_id="two_roi",
        routes={"ebi_patch": ["load", "roiA", "roiB", "glvA", "glvB"]},
        nodes=nodes, score=ScoreSpec(expr="glv_mean", threshold=0.0,
                                     bins={"below": 0, "above": 1}))
    issues = validate(recipe, kind="ebi_patch")
    collisions = [i for i in issues if i.code == "feature-collision"]
    assert len(collisions) == 1
    assert collisions[0].level == "warning", "撞名不擋執行，但要講出來"
    assert collisions[0].node_id == "glvB"
    assert "glv_mean" in collisions[0].title
    assert not [i for i in issues if i.level == "error"]


def test_a_warning_does_not_block_the_run_but_is_reported_afterwards(window):
    """警告描述的是「跑得完、數字卻不是你以為的那個」，所以不能擋，
    但也不能不講。跑**之前**講會被「Running: 3 / 200」洗掉，所以跑完才講。"""
    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
    dup = window.model.add_step("glv_stats")          # 跟範例裡的 glv 撞名
    window.model.set_param(dup, "source", "diff")

    assert window.run_trial(6, workers=1, sync=True) is True
    assert "Run finished" in window.status_text()
    assert "overwrites the feature" in window.status_text()


def test_every_recipe_that_ships_in_the_repo_passes_lint(qapp):
    """repo 裡出貨的 recipe 自己必須全部過 lint。

    以前掃的是 ``examples/recipes/``（教學範例，使用者的起點）。那些 2026-08-16
    全部拿掉了，現在 repo 裡的 recipe 只剩 ``tests/fixtures/recipes/`` ——
    它們是 e2e 的地基，接錯了的話一整批 e2e 會用「跑得完但每顆都失敗」的方式
    壞掉。所以這條測試改了對象，要擋的事沒變。
    """
    paths = sorted(FIXTURE_RECIPES.glob("*.json"))
    assert paths, "%s 是空的 —— 這條測試會變成什麼都沒檢查" % FIXTURE_RECIPES
    bad = {}
    for path in paths:
        recipe = Recipe.load(str(path))
        errs = [i for i in validate(recipe) if i.level == "error"]
        if errs:
            bad[path.name] = [(i.code, i.node_id) for i in errs]
    assert not bad, bad


def test_a_broken_combination_refuses_to_run_instead_of_failing_every_defect(window):
    """引擎的契約是「單顆出錯不殺整批」，所以接錯的卡片以前會**跑完整批而且
    每一顆都失敗**：進度條走完、結果是空的、原因埋在每顆的錯誤訊息裡。

    （subtract 的預設 2026-08-14 起是 ``ref`` —— patch 本來就對齊，加了就
    跑得動。要製造「指到沒人產的流」得自己指過去，情境跟以前一樣真實：
    使用者把 b 改成打錯的名字。）
    """
    src = first_source(window)
    node_id = window.model.add_step("subtract")
    # F10：先把兩條線接上（新卡前後都是空的），這一題問的是**接好之後**指到
    # 一條沒人產的流會怎樣 —— 那跟「還沒接線」是兩個不同的錯。
    window._on_edge_added(src, node_id, "test", "a")
    window._on_edge_added(src, node_id, "ref", "b")
    window.model.set_param(node_id, "b", "ref_aligned")   # 沒有 Align 在上游
    assert window.run_trial(6, workers=1, sync=True) is False
    assert "Cannot run" in window.status_text()
    assert "ref_aligned" in window.status_text()

    # 指到真的存在的流之後就跑得動了
    window.model.set_param(node_id, "b", "ref")
    assert window.run_trial(6, workers=1, sync=True) is True


def test_adding_a_card_says_what_is_still_missing_and_who_provides_it(window):
    """卡片庫上那個 ``needs …`` 的灰字 badge 對不會寫 code 的人沒有動作可做
    —— 他不知道那條流是誰產的。（改用 SNR map 觸發：它預設吃 ``diff``，
    Load 之後直接加一定缺；subtract 的預設已改成 patch 加了就能跑。）"""
    window.selected_node = None        # 沒選卡（否則會接在選取卡後、指到它的流）
    window.library.add_requested.emit("snr_map")
    msg = window.status_text()
    assert "diff" in msg
    assert "Compare two streams" in msg, "要講出哪一張卡會產出這條流"
    assert "test" in msg and "ref" in msg, "也要講現在有哪些流可以改指"


def test_every_visible_card_can_be_wired_up_without_a_dead_end(qapp):
    """每一張卡都要有一條「照著加就會通」的路，否則它在 UI 上就是死路。

    這是回饋 5（「卡片操作與組合是否相互會有問題」）的機械化版本：對每張卡
    找一組前置卡，驗證整條 route 過得了 lint。找不到 = 那張卡沒有人用得起來。
    """
    from d4t.ui.scope import visible_steps

    # 前置鏈：能滿足所有 reads / regions 的最短已知順序
    PREREQ = {
        "subtract": ["align"],
        "snr_map": ["align", "subtract"],
        "cd_measure": ["align", "subtract", "snr_map"],
        "roi_snr": ["align", "subtract", "snr_map"],
        # GDS 那條路的上游不是影像處理，是**另一張 Input 卡**：label map 那條流
        # 由 `load_sidecar` 產（配對在 ingest 層做，見 F11 Region-3 第 2 步）。
        "roi_from_mask": ["load_sidecar"],
        # 比較卡吃的是**區域**，所以上游要有一張出得了區域的 Region 卡。
        # `roi_cross` 是三張裡唯一不需要外部資料的（純規則）。
        "roi_compare": ["roi_cross"],
    }
    keys = [d["key"] for d in visible_steps([s.describe() for s in list_steps()])]
    dead_ends = {}
    needs_setup = {}
    for key in keys:
        if key == "load_patch":
            continue
        seq = ["load_patch"] + PREREQ.get(key, []) + [key]
        errs = [i for i in validate(_recipe(seq), kind="ebi_patch")
                if i.level == "error"]
        # ``not-configured`` 不是接線問題（F7-13）：那張卡缺的是一份要另外匯入
        # 的東西（模板是一張影像），不是缺上游。它的路是通的，只是還沒設定完 ——
        # 所以這裡不算死路，但**訊息必須指得出路在哪**，否則它就真的是死路了。
        needs = [i for i in errs if i.code == "not-configured"]
        rest = [i for i in errs if i.code != "not-configured"]
        if needs:
            needs_setup[key] = [i.detail for i in needs]
        if rest:
            dead_ends[key] = [(i.code, i.detail) for i in rest]
    assert not dead_ends, "這些卡片沒有可行的組合：%s" % sorted(dead_ends)

    # 「還沒設定完」的訊息**必須指向一個使用者按得到／填得到的東西**。
    # 那有**兩種**形狀，兩種都算數（F11 Measure 的比較卡逼出了第二種）：
    #
    # * 一顆**鈕**（`…` 結尾）—— 缺的是要另外匯入的東西（模板是一張影像）；
    # * 這張卡**自己的一格**（“引號”起來的欄位名）—— 缺的只是一個要挑的值，
    #   而那一格就在旁邊。這種卡沒有鈕可以指，只認第一種的話它剩兩條路：
    #   湊一個不存在的鈕，或者乾脆不講。
    #
    # 用「或」不是「改成」：舊的那條沒有錯，只是不完整 —— 換掉它會讓
    # `roi_mask` 那種本來講得很好的訊息突然變成違規。
    #
    # 而**引號那一種要驗**：引號裡的字必須真的是這張卡的欄位名，或工具列上真的
    # 有那顆鈕。不然「指向一個東西」會退化成「寫一句看起來像樣的話」。
    import re as _re

    studio_src = (Path(__file__).resolve().parent.parent
                  / "d4t" / "ui" / "studio.py").read_text(encoding="utf-8")
    for key, details in needs_setup.items():
        labels = {str(p.get("label") or p["name"])
                  for p in get_step(key).describe()["params"]}
        for detail in details:
            quoted = _re.findall(r"“([^”]+)”", detail)
            real = [q for q in quoted
                    if q in labels or ('"%s"' % q) in studio_src]
            assert ("…" in detail or "..." in detail) or real, (
                "%s 說它還沒設定完，但沒有指向任何一個按得到／填得到的東西"
                "（要嘛一顆 `…` 結尾的鈕，要嘛“引號”起來的欄位名）：%s"
                % (key, detail))
            fake = [q for q in quoted if q not in real and not q.endswith("…")]
            assert not fake, (
                "%s 的訊息引了一個不存在的欄位／鈕：%s（這張卡的欄位：%s）"
                % (key, fake, sorted(labels)))
