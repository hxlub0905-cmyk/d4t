# F12：區域也有線 — authored 2026-08-19.
"""**一張卡用到的每一個具名區域，畫布上都要有一條線指到定義它的那張卡。**

起點是使用者讀完 GDS → GLV 的接法之後說的那句話：「但我還是這樣怪怪的」。
怪的地方不是 bug —— 那條路跑起來是對的（順序由 route 相鄰對保證，見
``execution_order``）—— 而是**畫布上有兩套規則**：影像要拉線，區域用打字。

而它會說謊：拿掉上游那張 Region 卡，量測卡不會報錯，它會**安靜地改量整張圖**。

這一份鎖住四件事：

1. 區域參數一律是 ``region_key`` / ``region_keys`` + ``direction="in"``，
   而且設定區那一格**唯讀**（來源只在畫布上決定，同 F9-6）。
2. 區域線是從**參數推導**出來的，不進 ``recipe.edges`` —— recipe JSON 的格式
   一個欄位都沒有變，舊檔打開就有線。
3. 拉線 = 設那一格；剪線 = 清那一格；刪掉定義它的卡 = 下游那一格也空掉。
4. 型別不合與「來源排在下游」都擋得住，而且講得出可以照做的下一句話。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from conftest import first_source, wire_up  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLineEdit   # noqa: E402

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step, list_steps      # noqa: E402
from d4t.core.pipeline.recipe import Recipe             # noqa: E402
from d4t.core.pipeline.step import REGION_TYPES         # noqa: E402
from d4t.ui import canvas as canvas_mod                 # noqa: E402
from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402
from d4t.ui.viewmodel import RecipeModel                # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def _gds_route(model: RecipeModel):
    """``load_single → load_sidecar → roi_reference → glv_stats``（GDS 那條路）。

    這正是 `docs/GLAS-INTERFACE.md` 講的接法，也是使用者問「某個 layer 的 GLV
    要怎麼設定」時得到的那張圖。
    """
    img = model.add_step("load_single")
    lbl = model.add_step("load_sidecar")
    gds = model.add_step("roi_reference")
    glv = model.add_step("glv_stats")
    model.set_param(gds, "method", "layout layers")
    model.set_param(gds, "label_source", "layout_label")
    model.set_param(gds, "layers", "1:epi")
    model.set_param(glv, "source", "single")
    return img, lbl, gds, glv


# --------------------------------------------------------------------------- #
# 1. 區域是埠，而那一格是唯讀的
# --------------------------------------------------------------------------- #
def test_every_region_parameter_is_an_input_port():
    """整個 registry 一起驗 —— 第 18 張卡的作者不必記得回來補。"""
    for cls in list_steps():
        for spec in cls.params:
            if spec.type in REGION_TYPES:
                assert spec.direction == "in", \
                    "%s.%s 是區域參數，方向只能是 in" % (cls.key, spec.name)


def test_no_card_takes_a_region_name_as_free_text():
    """``roi`` 曾經是 ``str`` —— 打錯字要跑一次 lint 才知道，而畫布上什麼都沒有。

    判準不是名字也不是逐張列舉，是**問卡片自己**：把一個記號塞進某一格，
    如果它出現在 ``resolve_regions_in``（＝「這張卡要用上游的哪個區域」），
    那一格就是在指一個區域，型別必須是 ``region_key`` / ``region_keys``。

    這樣寫的理由是**下一張卡**：欄位叫 `my_roi` 或 `baseline` 都一樣抓得到，
    而「這一格指的是不是區域」永遠只有卡片自己知道。
    """
    mark = "zz_sentinel_zz"
    bad = []
    for cls in list_steps():
        try:
            base = cls.validate_params({})
        except Exception:                      # noqa: BLE001 — 壞卡另有測試
            continue
        for spec in cls.params:
            if spec.type in REGION_TYPES:
                continue                       # 已經是對的型別
            if spec.type != "str":
                continue                       # 塞不進一個名字的格子不必問
            try:
                names = cls.resolve_regions_in(dict(base, **{spec.name: mark}))
            except Exception:                  # noqa: BLE001
                continue
            if mark in names:
                bad.append("%s.%s (%s)" % (cls.key, spec.name, spec.type))
    assert not bad, "區域名不可以用打的：" + ", ".join(bad)


def test_the_region_field_is_read_only_in_the_panel(window):
    """來源只在畫布上決定（同 F9-6 對影像做的事）。"""
    src = first_source(window, "load_single")
    glv = window.add_card_after(src, "glv_stats")
    window._on_edge_added(src, glv, "single", "source")
    window.select_node(glv)
    editor = window.param_form.editor("roi")
    assert isinstance(editor, QLineEdit) and editor.isReadOnly()


# --------------------------------------------------------------------------- #
# 2. 線是推導出來的，不進 recipe
# --------------------------------------------------------------------------- #
def test_the_line_is_derived_from_the_parameter():
    model = RecipeModel(kind="rsem")
    _img, _lbl, gds, glv = _gds_route(model)
    assert model.region_lines() == []

    model.set_param(glv, "roi", "epi")
    assert model.region_lines() == [(gds, glv, "epi", "roi")]
    # **不進 recipe.edges** —— 值只有一個家，兩份會漂（F9 的教訓）。
    assert model.edge_lines() == []


def test_an_old_recipe_gets_its_lines_without_any_migration(tmp_path):
    """``roi="epi"`` 的舊檔打開就有線 —— 檔案格式一個欄位都沒有變。"""
    model = RecipeModel(kind="rsem")
    _img, _lbl, gds, glv = _gds_route(model)
    model.set_param(glv, "roi", "epi")

    path = tmp_path / "r.json"
    path.write_text(json.dumps(model.to_recipe().to_json_dict()),
                    encoding="utf-8")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["edges"] == [], "區域線不該被存進 edges"

    again = RecipeModel.from_recipe(Recipe.from_json_dict(doc), kind="rsem")
    assert again.region_lines() == [(gds, glv, "epi", "roi")]


def test_a_region_nobody_defines_draws_no_line():
    """畫一條無中生有的線比沒有線更糟（壞在哪由 ``unknown-region`` 講）。"""
    model = RecipeModel(kind="rsem")
    _img, _lbl, _gds, glv = _gds_route(model)
    model.set_param(glv, "roi", "nope")
    assert model.region_lines() == []
    assert "unknown-region" in [i.code for i in model.validate()]


# --------------------------------------------------------------------------- #
# 3. 拉線、剪線、刪卡
# --------------------------------------------------------------------------- #
def test_dragging_a_line_picks_the_region(window):
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, glv, "single", "source")

    window._on_edge_added(gds, glv, "epi", "roi")
    assert window.model.nodes[glv].params["roi"] == "epi"
    # 挑了區域就順手把輸出名填成區域名（F7-11）—— 拉線走的是同一條路。
    assert window.model.nodes[glv].params["output_prefix"] == "epi"


def test_a_measure_card_takes_more_than_one_region(window):
    """**多連一，區域這一半**（F13-⑥）。

    使用者：「我想將 ROI A 跟 ROI B 的區域線一起接到 GLV stats，但仍然一次
    只能接一條」。對 —— 而「多連一」講的是**同一件事做在好幾個東西上**，
    那對區域跟對影像流一樣成立：同一組統計量、同一張圖，量在兩個區域上。

    規則跟影像逐字相同（F7-19）：``region_keys``（一串）**累加**，
    ``region_key``（單一角色）**取代**。
    """
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi, 2:mg")
    window._on_edge_added(src, glv, "single", "source")

    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_edge_added(gds, glv, "mg", "roi")
    assert window.model.nodes[glv].params["roi"] == "epi,mg"

    lines = {ln for ln in window.model.region_lines() if ln[1] == glv}
    assert lines == {(gds, glv, "epi", "roi"), (gds, glv, "mg", "roi")}, \
        "兩個區域就要有兩條線"

    # 每個數字帶自己的區域名 —— 不然兩組會互相蓋掉，而畫面上看不出來。
    params = window.model.nodes[glv].params
    feats = get_step("glv_stats").resolve_features(params)
    assert any(f.startswith("epi_") for f in feats)
    assert any(f.startswith("mg_") for f in feats)

    # **自動填的輸出名要收回來**：接第一條線時 `_autofill_output_prefix` 把它
    # 填成 `epi`（F7-11），而第二條線一來每個數字本來就帶區域名了 ——
    # 留著的話是 `epi_epi_glv_mean`。
    assert params["output_prefix"] == ""
    assert all(not f.startswith("epi_epi") for f in feats), feats


def test_a_name_the_user_typed_is_not_taken_back(window):
    """只收回**自動填的那個值**（正好等於原本那一個區域的名字）。
    使用者自己打的字被收掉，比沒有這個功能更糟。"""
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi, 2:mg")
    window._on_edge_added(src, glv, "single", "source")

    window._on_edge_added(gds, glv, "epi", "roi")
    window.model.set_param(glv, "output_prefix", "mine")
    window._on_edge_added(gds, glv, "mg", "roi")
    assert window.model.nodes[glv].params["output_prefix"] == "mine"


def test_a_role_region_port_is_still_replaced(window):
    """「跟誰比」那一格是**角色**：一次只有一個答案，第二條線是**取代**。

    往它再拉一條的意思是「改跟別的比」，不是「參照有兩個」。

    （F16 之前這是獨立的 `roi_compare` 卡，F16 併成 `method="compare"`，
    F18 再變成 `reference` 那一格。這條測的東西一路上一個字都沒變 ——
    變的只是那個角色埠現在叫什麼、以及它什麼時候才長出來。）
    """
    from d4t.core.steps.glv_stats import REF_REGION

    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    cmp_ = window.add_card_after(gds, "glv_stats")
    window.model.set_param(cmp_, "reference", REF_REGION)
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi, 2:mg")
    window._on_edge_added(src, cmp_, "single", "source")

    window._on_edge_added(gds, cmp_, "epi", "reference_region")
    window._on_edge_added(gds, cmp_, "mg", "reference_region")
    assert window.model.nodes[cmp_].params["reference_region"] == "mg"
    lines = [ln for ln in window.model.region_lines()
             if ln[1] == cmp_ and ln[3] == "reference_region"]
    assert lines == [(gds, cmp_, "mg", "reference_region")], "舊線沒有跟著消失"


def test_a_region_goes_in_one_side_and_out_the_other(window):
    """同進同出（使用者：「區域線應該也要 follow 圖像線一樣，前進後出」）。

    量測卡接進來的區域，它後面也接得出去 —— 不然第二張要量同一個區域的卡只能
    回頭去接那張 Region 卡，而那條線會橫跨整張畫布。

    副標**不跟著變**：它印的是「這張卡真的產出什麼」，而量測卡沒有定義任何
    區域。混在一起的話，一張 Gray-level stats 在畫布上會讀起來像 Region 卡。
    """
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    a = window.add_card_after(gds, "glv_stats")
    b = window.add_card_after(a, "cd_measure")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, a, "single", "source")
    window._on_edge_added(src, b, "single", "source")
    window._on_edge_added(gds, a, "epi", "roi")

    item = window.pipeline.node_item(a)
    assert {"name": "epi", "kind": "region"} in item.out_specs(),         "接進來的區域，後面要接得出去"
    assert "epi" not in item.subtitle(),         "副標印的是真的產出什麼 —— 量測卡沒有定義任何區域"

    # 從**那一顆**埠接下去：線一段一段接，不是每一條都從 Region 卡拉出來。
    window._on_edge_added(a, b, "epi", "roi")
    assert window.model.nodes[b].params["roi"] == "epi"
    assert (a, b, "epi", "roi") in window.model.region_lines()


def test_cutting_the_line_clears_the_field(window):
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, glv, "single", "source")
    window._on_edge_added(gds, glv, "epi", "roi")

    window._on_edge_removed(gds, glv, "epi", "roi")
    assert window.model.nodes[glv].params["roi"] == ""
    assert window.model.region_lines() == []


def test_removing_the_region_card_empties_the_field(window):
    """畫面上線沒了、卡片卻還指著一個再也沒有人定義的區域 —— 那是同一種說謊。"""
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, glv, "single", "source")
    window._on_edge_added(gds, glv, "epi", "roi")

    window._on_remove_requested(gds)
    assert window.model.nodes[glv].params["roi"] == ""


def test_several_regions_accumulate_on_a_region_keys_field(window):
    """``roi_mask`` 吃一串區域 —— 第二條線是「這個也算」，不是「改成這個」。"""
    src = first_source(window, "load_single")
    tpl = window.add_card_after(src, "roi_reference")
    # F30：一張卡四個 method，而 `regions` 只在「我自己標的那一格」上算數。
    window.model.set_param(tpl, "method", "a cell I mark myself")
    window._on_edge_added(src, tpl, "single", "source")
    window.model.set_param(tpl, "regions", "epi: 0.1,0,0.3,1 | mg: 0.5,0,0.2,1")
    mask = window.add_card_after(tpl, "roi_mask")
    window._on_edge_added(src, mask, "single", "source")
    # 加進來的卡**不帶區域**：自動填等於自動畫了六條他沒拉過的線（鐵則 10）。
    assert window.model.nodes[mask].params["regions"] == ""

    window._on_edge_added(tpl, mask, "epi", "regions")
    window._on_edge_added(tpl, mask, "mg", "regions")
    assert window.model.nodes[mask].params["regions"] == "epi,mg"

    window._on_edge_removed(tpl, mask, "epi", "regions")
    assert window.model.nodes[mask].params["regions"] == "mg"


# --------------------------------------------------------------------------- #
# 4. 接不到的東西要擋，而且講得出下一句話
# --------------------------------------------------------------------------- #
def test_an_image_line_cannot_land_on_a_region_port(window):
    """放行的話那一格會變成一個沒有人定義的區域名 —— 跑起來是 `unknown-region`，
    而畫面上那條線看起來完全正常。"""
    src = first_source(window, "load_single")
    glv = window.add_card_after(src, "glv_stats")
    window._on_edge_added(src, glv, "single", "source")

    window._on_edge_added(src, glv, "single", "roi")
    assert window.model.nodes[glv].params["roi"] == ""
    assert "region" in window.status_text().lower()


def test_a_region_defined_later_is_now_allowed_and_reorders(window):
    """**這一條翻面了**（F42 B2，2026-08-27）。

    原本它鎖的是 F12 §4 的第四道守門：「來源排在下游 → 擋下來，叫使用者把
    Region 卡往前搬」。那句話在 F12 當時是真的 —— 區域線不進 `recipe.edges`，
    所以順序只能靠卡片的左右位置。

    方案 B 把線存進去了，於是**那條線自己就是順序**（`execution_order` 只看
    線）。擋下來等於不讓使用者做那個唯一能修好順序的動作 —— 而「Region 卡排在
    量測卡右邊，量測卡先跑、安靜地量整張圖」正是這一輪要修的 bug。

    所以現在它接得起來，而且排版跟著線走。真正會壞的那一種（成環）由
    `add_edge` 擋，那擋的是事實不是排版。
    """
    src = first_source(window, "load_single")
    glv = window.add_card_after(src, "glv_stats")
    window._on_edge_added(src, glv, "single", "source")
    gds = window.add_card_after(glv, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")

    window._on_edge_added(gds, glv, "epi", "roi")
    assert window.model.nodes[glv].params["roi"] == "epi"
    order = window.model.node_order
    assert order.index(gds) < order.index(glv), "線說了算 —— 排版跟著它走"


# --------------------------------------------------------------------------- #
# 5. 畫布真的畫得出來
# --------------------------------------------------------------------------- #
def test_the_canvas_draws_the_region_line_as_a_region_line(window):
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, glv, "single", "source")
    window._on_edge_added(gds, glv, "epi", "roi")

    item = window.pipeline.node_item(gds)
    assert {"name": "epi", "kind": "region"} in item.out_specs()
    consumer = window.pipeline.node_item(glv)
    assert "region" in consumer.in_kinds()

    kinds = [e.kind() for e in window.pipeline._edges
             if e.pair() == (gds, glv)]
    assert kinds == ["region"], "GDS → 量測卡那一條要是區域線"


def test_ports_never_pile_up_on_a_card_with_many_regions(window):
    """埠多就長高 —— 疊在一起的埠是**點不到**的（取最近的那一顆）。"""
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:a, 2:b, 3:c, 4:d, 5:e")
    window._refresh_pipeline()

    item = window.pipeline.node_item(gds)
    anchors = item.out_anchors_local()
    # 一條原樣送出的流 ＋ 五層 × **三個名字**（F29 之前一層只有一個名字，
    # 所以這裡本來是 6）。`canvas._MAX_REGION_PORTS` 數的是埠不是區域 ——
    # 它留在 6 的話，第三層開始的每一個區域在畫布上都沒有出口。
    assert len(anchors) == 1 + 5 * 3, [d["name"] for d in item.out_specs()]
    gaps = [anchors[i + 1].y() - anchors[i].y() for i in range(len(anchors) - 1)]
    assert min(gaps) >= 2 * canvas_mod._PORT_R, gaps
    for i, anchor in enumerate(anchors):
        assert item.out_port_at(anchor) == i, "第 %d 顆埠點到的是別人" % i


def test_pick_none_folds_a_family_into_one_port(window):
    """`pick="none"` 的家族只有主名字 —— 畫布上一個區域一顆菱形埠（F31 T4）。

    埠的數量走 `resolve_regions_out`，所以宣告變了畫布就跟著變 ——
    畫著一顆沒有人產出的 `_center` 埠，跟少畫一顆真的產出的埠一樣是說謊。
    """
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:a, 2:b, 3:c, 4:d, 5:e")
    window.model.set_param(gds, "pick", "none")
    window._refresh_pipeline()

    item = window.pipeline.node_item(gds)
    assert len(item.out_anchors_local()) == 1 + 5 * 1, \
        [d["name"] for d in item.out_specs()]
    names = [d["name"] for d in item.out_specs() if d["kind"] == "region"]
    assert names == ["a", "b", "c", "d", "e"]
