# F11 Region-3 第 4 步：Studio 那一頭（掛匯出的入口、layers 的表格、儀表）。
"""**這一份要放在 `test_ui_*`，不是跟 ingest 的測試擺一起。**

第一版把它接在 `tests/test_glas_sidecar.py` 後面，結果核心那一輪（不含 UI）
整個行程崩掉 —— 那一份不叫 `test_ui_*`，於是 Qt 被拉進「一個行程跑全部」的
核心測試裡。`CLAUDE.md` §4 講的就是這件事，只是我從另一個方向撞上它。

內容是三件，共同的要求只有一個：**畫面上的東西要跟引擎算的一樣**。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "dark")
    yield app


# --------------------------------------------------------------------------- #
# 1. 「掛上匯出」那顆鈕
# --------------------------------------------------------------------------- #
"""為什麼這一顆鈕必須在這一輪就有：`roi_from_mask` 的「還沒設定完」那句話
**指向它**。訊息指向一個不存在的東西，那句話本身就是死路（推廣鐵則），而
`tests/test_ui_f7_9_feedback.py` 有一條不變量在擋。"""


def test_the_card_message_points_at_a_button_that_exists(qapp):
    """訊息裡那個「…」結尾的東西，工具列上要真的有。

    問的是**真的建出來的那條工具列**，不是 `studio.py` 的原始碼裡有沒有那串字
    （第一版是後者，而它有兩個洞：字搬到別的模組去就紅、以及 —— 更糟 ——
    字在原始碼裡、鈕卻沒被 `addWidget` 上去時它是綠的。後者實際發生過）。
    """
    from PySide6.QtWidgets import QToolButton

    from d4t.core.pipeline import get_step
    from d4t.ui.studio import StudioWindow

    says = get_step("roi_from_mask").configuration_issues({"layers": ""})[0]
    named = re.findall(r"“([^”]+…)”", says)
    assert named, "訊息沒有指向任何一個按得下去的東西：%s" % says

    win = StudioWindow(show_welcome_on_start=False)
    try:
        on_bar = set()
        for a in win.toolbar.actions():
            w = win.toolbar.widgetForAction(a)
            if w is None:
                continue
            if isinstance(w, QToolButton):
                on_bar.add(w.text())
            on_bar.update(c.text() for c in w.findChildren(QToolButton))
        for label in named:
            assert label in on_bar, "工具列上沒有 %r 這顆鈕" % label

        # 使用者第九輪的第一句話：「Load layout labels 要怎麼 load，好像沒有
        # load 的地方」。那張卡上**沒有東西可以填**（來源是 ingest 掛上去的），
        # 所以「怎麼 load」的答案只能寫在它自己的說明與它擋下來的那句話裡 ——
        # 而那兩處指的東西也必須真的在工具列上。
        card = get_step("load_sidecar")
        for text in (card.help, _no_sidecar_message(card)):
            pointed = re.findall(r"“([^”]+…)”", text)
            assert pointed, "這段話沒有指向任何按得下去的東西：%s" % text
            for label in pointed:
                assert label in on_bar, "工具列上沒有 %r 這顆鈕" % label

        # 空白狀態（第一次進來看到的那一塊）也要說得出那個順序。
        assert "Open GDS export…" in win.empty_state_attachments.text()
    finally:
        win.deleteLater()


def _no_sidecar_message(card) -> str:
    """跑一次「這顆沒有 label」那條路，把訊息拿出來。"""
    from d4t.core.pipeline.context import Context
    from d4t.core.pipeline.step import StepError

    class _Item:
        defect_id = "1"
        sidecars = {}

    try:
        card().run(Context(meta={"_defect_item": _Item()}), {})
    except StepError as e:
        return str(e)
    raise AssertionError("沒有匯出時這張卡應該擋下來")


# --------------------------------------------------------------------------- #
# 7. 第 4 步的 UI：labels 的表格 ＋ 儀表
# --------------------------------------------------------------------------- #
"""這兩件都只有一個共同的要求：**畫面上的東西要跟引擎算的一樣**。

表格那一件還多一條：一張 recipe 上可能同時有 `load_patch`（一列一張圖）與
`roi_from_mask`（一列一層）兩個 `channel_map` —— 用同一個數字去排兩者的列數，
其中一邊一定是錯的。
"""


def test_the_layer_table_says_layer_not_image(qapp):
    """`L17/D0` 不是「第幾張圖」。同一個 widget、三句話不同（見 `_WORDS`）。"""
    from d4t.ui.widgets import ChannelMapField

    images = ChannelMapField("", row_kind="images")
    labels = ChannelMapField("", row_kind="labels")
    assert images.row_kind() == "images" and labels.row_kind() == "labels"
    assert "Image" in images._words[0] and "Layer" in labels._words[0]
    assert images._words[1] != labels._words[1]


def test_the_two_kinds_of_row_count_do_not_overwrite_each_other(qapp):
    """一張 recipe 上兩個 `channel_map` 各排各的列數。"""
    from d4t.core.pipeline import get_step
    from d4t.ui.widgets import ChannelMapField, ParamForm

    form = ParamForm()
    form.set_step(get_step("roi_from_mask").describe(), {"layers": ""},
                  stream_choices=["layout_label"])
    form.set_image_count(5)          # 一顆五張圖 —— 跟層數無關
    form.set_label_count(3)
    row = form._rows["layers"]
    assert isinstance(row.editor, ChannelMapField)
    assert row.editor.row_kind() == "labels"
    assert row.editor.row_count() == 3, "層的列數被「一顆幾張圖」蓋掉了"


def test_an_empty_layer_row_means_no_region_not_a_default_name(qapp):
    """`load_patch` 空著 = 用預設名（test/ref）；這裡空著 = **這一層不要**。"""
    from d4t.ui.widgets import ChannelMapField

    w = ChannelMapField("", row_kind="labels")
    w.set_min_rows(2)
    assert w.text() == "", "沒填名字不該生出區域"
    assert "no region" in w._default_name(0)


def test_the_inspector_is_registered_and_reads_the_engines_numbers(qapp):
    """畫的是 `ctx.meta["gds_layers"]` —— UI 不自己再拆一次 label。"""
    import numpy as np

    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.ui import inspectors as insp

    assert insp.inspector_for("roi_from_mask") is insp.GdsInspector

    lab = np.zeros((10, 10), np.uint8)
    lab[1:5, 1:5] = 1
    ctx = Context(images={"layout_label": lab})
    params = {"source": "layout_label", "layers": "1:epi, 2:mg",
              "min_area": 0, "output_prefix": "", "max_boxes": 8192}
    get_step("roi_from_mask")().run(ctx, params)

    w = insp.GdsInspector()
    w.set_context("n", params, meta=ctx.meta)
    assert w.has_data()
    rec = w.record()
    by = {e["name"]: e for e in rec["layers"]}
    assert by["epi"]["boxes"] == ctx.roi_count("epi")
    assert by["mg"]["boxes"] == 0
    assert "1 of 2 layer(s)" in w.summary()


def test_the_inspector_says_when_a_layer_has_no_name(qapp):
    """匯出多了一層而 recipe 沒跟上 —— 它會**安靜地**少一個區域。"""
    import numpy as np

    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.ui import inspectors as insp

    lab = np.zeros((10, 10), np.uint8)
    lab[1:5, 1:5] = 1
    lab[6:9, 6:9] = 3                       # 圖裡有第 3 層，recipe 只講到 2
    ctx = Context(images={"layout_label": lab})
    params = {"source": "layout_label", "layers": "1:epi, 2:mg",
              "min_area": 0, "output_prefix": "", "max_boxes": 8192}
    get_step("roi_from_mask")().run(ctx, params)
    w = insp.GdsInspector()
    w.set_context("n", params, meta=ctx.meta)
    assert "have no name" in w.summary()


def test_the_inspector_says_when_the_box_limit_bit(qapp):
    import numpy as np

    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.ui import inspectors as insp

    n = 30
    lab = np.array([[1 if x <= y else 0 for x in range(n)] for y in range(n)],
                   np.uint8)
    ctx = Context(images={"layout_label": lab})
    params = {"source": "layout_label", "layers": "1:epi", "min_area": 0,
              "output_prefix": "", "max_boxes": 5}
    get_step("roi_from_mask")().run(ctx, params)
    w = insp.GdsInspector()
    w.set_context("n", params, meta=ctx.meta)
    assert "box limit" in w.summary()


def test_the_empty_state_points_at_the_button(qapp):
    from d4t.ui import inspectors as insp

    w = insp.GdsInspector()
    assert not w.has_data()
    assert "Open GDS export…" in w.empty_reason()


def test_the_attachment_entry_turns_on_once_a_lot_is_open(qapp, tmp_path):
    """「怎麼 load」的最後一段：那顆鈕**灰著也要在畫面上**，載完 lot 就亮。

    這是使用者第九輪第一句話的完整答案。它由三段組成，而三段都測得到：
    卡片與空白狀態說得出那顆鈕的名字（上面那條）、那顆鈕真的在工具列上
    （`test_every_button_built_for_the_toolbar_is_actually_on_it`），
    以及**它什麼時候會亮**（這一條）。

    灰著也要在，不是載了 lot 才長出來：一顆到那時候才出現的鈕，使用者在需要它
    之前根本不知道 d4t 做得到這件事。
    """
    import sys

    from d4t.ui.studio import StudioWindow

    sys.path.insert(0, "tools")
    from make_sample_rsem import generate

    win = StudioWindow(show_welcome_on_start=False)
    try:
        assert win.btn_open_gds.isEnabled() is False
        lot = generate(str(tmp_path / "lot"), n=3, seed=5)
        assert win.load_dataset_path(lot["klarf"], sync=True) is True
        assert win.btn_open_gds.isEnabled() is True
    finally:
        win.deleteLater()


def test_a_card_added_after_the_export_still_gets_its_layer_names(qapp,
                                                                  tmp_path):
    """填層名那一段原本只在**掛匯出的當下**跑，掃的是當時已經存在的卡。

    但使用者的自然順序是「開 KLARF → 開 GDS 匯出 → 加卡」：那顆鈕在沒有 lot
    的時候是灰的，空白狀態也叫他先載 lot。於是後加的那張卡是空的 —— 而它擋下來
    的那句話寫著「Use “Open GDS export…” — attaching the export fills in the
    layers」，也就是叫使用者去做他剛剛做完的事。

    這一條把**兩個順序**都測掉：先加卡後掛（原本就會過）、先掛後加卡（原本是空的）。
    """
    import sys

    from d4t.ui.studio import StudioWindow

    sys.path.insert(0, "tools")
    from make_glas_export import generate as gen_export
    from make_sample_rsem import generate as gen_lot

    lot = gen_lot(str(tmp_path / "lot"), n=3, seed=4)
    exp = gen_export(str(tmp_path / "lot"), str(tmp_path / "exp"),
                     layers=2, seed=4)

    def layers_of(order):
        win = StudioWindow(show_welcome_on_start=False)
        try:
            assert win.load_dataset_path(lot["klarf"], sync=True)
            if order == "attach-first":
                win.attach_gds_export(str(tmp_path / "exp"))
                nid = win.model.add_step("roi_from_mask")
                win._autofill_new_card(nid)
            else:
                nid = win.model.add_step("roi_from_mask")
                win._autofill_new_card(nid)
                win.attach_gds_export(str(tmp_path / "exp"))
            return str(win.model.nodes[nid].params.get("layers", ""))
        finally:
            win.deleteLater()

    first = layers_of("attach-first")
    second = layers_of("card-first")
    assert first, "先掛匯出、後加卡 —— 那張卡是空的（使用者的自然順序）"
    assert first == second, "兩個順序填出來的東西要一樣：%r vs %r" % (first,
                                                                     second)
    assert first.startswith("1:"), first
    assert exp     # 產生器真的產了東西


def test_the_users_own_names_are_never_overwritten(qapp, tmp_path):
    """自動填只填**空的**。使用者把 `L17_D0` 改成 `epi` 之後重新掛一次匯出，
    不可以把它洗回去 —— 寫分數表達式的是他。"""
    import sys

    from d4t.ui.studio import StudioWindow

    sys.path.insert(0, "tools")
    from make_glas_export import generate as gen_export
    from make_sample_rsem import generate as gen_lot

    lot = gen_lot(str(tmp_path / "lot"), n=3, seed=6)
    gen_export(str(tmp_path / "lot"), str(tmp_path / "exp"), layers=2, seed=6)

    win = StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lot["klarf"], sync=True)
        win.attach_gds_export(str(tmp_path / "exp"))
        nid = win.model.add_step("roi_from_mask")
        win._autofill_new_card(nid)
        win.model.set_param(nid, "layers", "1:epi, 2:mg")
        win.attach_gds_export(str(tmp_path / "exp"))          # 再掛一次
        win._autofill_new_card(nid)
        assert win.model.nodes[nid].params["layers"] == "1:epi, 2:mg"
    finally:
        win.deleteLater()


# --------------------------------------------------------------------------- #
# 8. 防呆：這張卡永遠不該是空的（F11 Region-3 第五輪）
# --------------------------------------------------------------------------- #
"""使用者實際跑真實資料之後的第一句話：

> 「一開始 layout labels 連過去 GDS layer card 時候，image stream 完全不會顯示
>   任何 overlay，要輸入 region name 才有，我希望有個防呆機制讓 Layer 一開始就
>   填好（可以先預設填名字 LayerA/LayerB/LayerC 這樣以此類推）這樣才會一開始就
>   有顯示（避免 user 以為沒連到沒 work）」

規則本身沒問題（**某一列空著 = 那一層不要**，使用者要有辦法排除一層）。貴的是
**整張卡都空著**那個狀態：一個區域都不吐、影像上一個框都沒有 —— 而那跟「線沒
接上」「這張卡壞了」在畫面上長得一模一樣。
"""


def _gds_lot(tmp_path, seed, layers=3, label_map=True):
    import json
    import sys

    sys.path.insert(0, "tools")
    from make_glas_export import generate as gen_export
    from make_sample_rsem import generate as gen_lot

    lot = gen_lot(str(tmp_path / "lot"), n=3, seed=seed)
    exp = tmp_path / "exp"
    gen_export(str(tmp_path / "lot"), str(exp), layers=layers, seed=seed)
    if not label_map:
        # GLAS 匯出時沒勾「export ROI label map」就長這樣。
        f = exp / "overlay_manifest.json"
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc.pop("label_map", None)
        f.write_text(json.dumps(doc), encoding="utf-8")
    return lot, str(exp)


def test_connecting_the_labels_fills_the_layers_and_shows_boxes(qapp, tmp_path):
    """**接上線的那一刻**畫面上就要有框 —— 那正是使用者期待有反應的時刻。

    這一條走的是沒有 `label_map` 的匯出（名字只能是 `LayerA`…），因為那是唯一
    會真的落到防呆上的情況；有 `label_map` 的走真層名，見下一條。
    """
    from d4t.ui.studio import StudioWindow

    lot, exp = _gds_lot(tmp_path, seed=11, label_map=False)
    win = StudioWindow(show_welcome_on_start=False)
    try:
        assert win.load_dataset_path(lot["klarf"], sync=True)
        win.attach_gds_export(exp)
        sid = win.model.add_step("load_sidecar")
        win.select_node(sid)
        win.refresh_preview(sync=True)
        gid = win.model.add_step("roi_from_mask")
        win.select_node(gid)
        win._autofill_new_card(gid)

        win._connect(sid, gid, "layout_label", dst_in="source")
        got = win.model.nodes[gid].params["layers"]
        # 字母跟著 **id** 走：這一顆上剛好沒有某一層時，字母不該整排往前遞補。
        assert got and all(
            row.split(":")[1] == "Layer" + "ABCDEFG"[int(row.split(":")[0]) - 1]
            for row in got.split(", ")), got

        win.refresh_preview(sync=True)
        shown = set(win.region_overlay_names())
        assert shown == {r.split(":")[1] for r in got.split(", ")}, shown
        assert shown, "接上線之後畫面上一個框都沒有 —— 那跟沒接上長得一樣"
    finally:
        win.deleteLater()


def test_the_real_layer_names_win_over_the_fallback(qapp, tmp_path):
    """`LayerA` 是防呆，不是命名建議 —— manifest 給得出真名字就用真的。"""
    from d4t.ui.studio import StudioWindow

    lot, exp = _gds_lot(tmp_path, seed=12, layers=2, label_map=True)
    win = StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lot["klarf"], sync=True)
        win.attach_gds_export(exp)
        gid = win.model.add_step("roi_from_mask")
        win._autofill_new_card(gid)
        got = win.model.nodes[gid].params["layers"]
        assert "Layer" not in got, got      # 不可以退回防呆的名字
        assert got.startswith("1:L"), got   # `L17/D0` → `L17_D0`
    finally:
        win.deleteLater()


def test_an_excluded_layer_stays_excluded(qapp, tmp_path):
    """防呆只填**整張卡都空著**的時候。

    「某一列空著 = 那一層不要」這條規則不可以被防呆吃掉 —— 那是使用者唯一能
    排除一層的方法（`tests/test_roi_from_mask.py` 鎖著它的引擎行為）。
    """
    from d4t.ui.studio import StudioWindow

    lot, exp = _gds_lot(tmp_path, seed=13, label_map=False)
    win = StudioWindow(show_welcome_on_start=False)
    try:
        win.load_dataset_path(lot["klarf"], sync=True)
        win.attach_gds_export(exp)
        sid = win.model.add_step("load_sidecar")
        win.select_node(sid)
        win.refresh_preview(sync=True)
        gid = win.model.add_step("roi_from_mask")
        # 「不要第 2 層」在這張表上的寫法是**那個 id 不出現**
        # （`ChannelMapField` 的空列不會被寫出來，見
        #  test_an_empty_layer_row_means_no_region_not_a_default_name）。
        win.model.set_param(gid, "layers", "1:epi, 3:mg")
        win._connect(sid, gid, "layout_label", dst_in="source")
        assert win.model.nodes[gid].params["layers"] == "1:epi, 3:mg"
    finally:
        win.deleteLater()


def test_the_fallback_names_do_not_run_out_of_letters():
    """256 層也不會撞名（Excel 的欄名）。"""
    from d4t.core.ingest.glas_export import fallback_layer_names

    assert fallback_layer_names([3, 1, 2]) == "1:LayerA, 2:LayerB, 3:LayerC"
    assert fallback_layer_names([0]) == ""          # 0 是背景，不是一層
    # 字母跟著 id 走：少了第 2 層，第 3 層仍然是 LayerC（不遞補）
    assert fallback_layer_names([1, 3]) == "1:LayerA, 3:LayerC"
    many = fallback_layer_names(range(1, 60)).split(", ")
    assert many[25].endswith("LayerZ") and many[26].endswith("LayerAA")
    assert len({n.split(":")[1] for n in many}) == len(many)
