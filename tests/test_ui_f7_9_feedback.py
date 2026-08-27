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

⚠ **F39-B3（2026-08-27）搬走了 12 條** —— 它們問的不是「F7-9 那一輪交付了
什麼」，是**性質**，所以它們回到性質住的地方：

* 階段色三條 → ``tests/test_ui_widgets.py``（逐段套用到 ``GROUP_ORDER``）
* 埠的座標系與換行五條 → ``tests/test_ui_canvas.py``（畫的座標系＝宣告的座標
  系，就是這裡守的；``docs/PITFALLS.md`` 那條 ``paint()`` 用場景座標的坑）
* lint 四條 → ``tests/test_card_invariants.py``。它們**一條 Qt 都沒用到**，
  搬過去之後回到核心批，逐檔跑的 UI 批少了它們那份時間。

留在這裡的十三條是**這一輪的情境**：起手卡、影像流參數的白話標籤與正規化、
點卡片預覽哪一張、以及三條要 ``StudioWindow`` 才問得出來的 lint 行為
（警告不擋執行、接錯的組合擋在跑之前、加卡時講出還缺什麼）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from d4t.core.pipeline import get_step, list_steps   # noqa: E402 — Qt-free
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


def test_a_warning_does_not_block_the_run_but_is_reported_afterwards(window):
    """警告描述的是「跑得完、數字卻不是你以為的那個」，所以不能擋，
    但也不能不講。跑**之前**講會被「Running: 3 / 200」洗掉，所以跑完才講。"""
    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
    dup = window.model.add_step("glv_stats")          # 跟範例裡的 glv 撞名
    window.model.set_param(dup, "source", "diff")

    assert window.run_trial(6, workers=1, sync=True) is True
    assert "Run finished" in window.status_text()
    assert "overwrites the feature" in window.status_text()


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
    —— 他不知道那條流是誰產的。

    ⚠ 觸發用的卡 2026-08-25 換過：以前是 `snr_map`（預設吃 `diff`），而
    Z-map 刪掉之後**整個卡片庫沒有一張卡預設吃 `diff`** 了。現在用
    `align_to`：它預設吃 `paired`，而那條流只有 `pair_source` 產得出來 ——
    Load 之後直接加一定缺，形狀跟以前一字不差。
    """
    window.selected_node = None        # 沒選卡（否則會接在選取卡後、指到它的流）
    window.library.add_requested.emit("align_to")
    msg = window.status_text()
    assert "paired" in msg
    # 名字從 registry 拿，不要抄一份 —— 這條測的是「訊息講得出是**哪一張卡**」，
    # 不是那張卡現在叫什麼（F16 把它從 `Compare two streams` 改成
    # `Image Combination`，而寫死的那份當場變成假失敗）。
    assert get_step("pair_source").label in msg, "要講出哪一張卡會產出這條流"
    assert "test" in msg and "ref" in msg, "也要講現在有哪些流可以改指"


