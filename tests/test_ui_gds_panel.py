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

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.pipeline import get_step  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from adept.ui import theme
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
    """訊息裡那個「…」結尾的東西，工具列上要真的有。"""
    from adept.core.pipeline import get_step

    says = get_step("roi_from_mask").configuration_issues({"layers": ""})[0]
    named = re.findall(r"“([^”]+…)”", says)
    assert named, "訊息沒有指向任何一個按得下去的東西：%s" % says
    src = open("adept/ui/studio.py", encoding="utf-8").read()
    for label in named:
        assert '"%s"' % label in src, "工具列上沒有 %r 這顆鈕" % label


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
    from adept.ui.widgets import ChannelMapField

    images = ChannelMapField("", row_kind="images")
    labels = ChannelMapField("", row_kind="labels")
    assert images.row_kind() == "images" and labels.row_kind() == "labels"
    assert "Image" in images._words[0] and "Layer" in labels._words[0]
    assert images._words[1] != labels._words[1]


def test_the_two_kinds_of_row_count_do_not_overwrite_each_other(qapp):
    """一張 recipe 上兩個 `channel_map` 各排各的列數。"""
    from adept.core.pipeline import get_step
    from adept.ui.widgets import ChannelMapField, ParamForm

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
    from adept.ui.widgets import ChannelMapField

    w = ChannelMapField("", row_kind="labels")
    w.set_min_rows(2)
    assert w.text() == "", "沒填名字不該生出區域"
    assert "no region" in w._default_name(0)


def test_the_inspector_is_registered_and_reads_the_engines_numbers(qapp):
    """畫的是 `ctx.meta["gds_layers"]` —— UI 不自己再拆一次 label。"""
    import numpy as np

    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context
    from adept.ui import inspectors as insp

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

    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context
    from adept.ui import inspectors as insp

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

    from adept.core.pipeline import get_step
    from adept.core.pipeline.context import Context
    from adept.ui import inspectors as insp

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
    from adept.ui import inspectors as insp

    w = insp.GdsInspector()
    assert not w.has_data()
    assert "Open GDS export…" in w.empty_reason()
