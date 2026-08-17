# F10：畫布要符合現實 — authored 2026-08-17.
"""**畫布上看得到的，就是引擎真的會做的。**（使用者定調 2026-08-17）

> 一張卡片剛被 new add 時，前後應該都是空的乾淨的；連上 source，後面 source
> 才會出來。

這一支鎖住那條不變量的三個面向，而且每一條都**自動套用到 registry 裡的每一張
卡** —— 之後加第 18 張卡的人不必記得回來補：

1. **埠點得到、而且點到的是自己那一顆**（F10-1）。
2. 剛加進來的卡**前後都是空的**：沒有來源、也沒有輸出流（F10-2、F10-3）。
3. 沒有來源的卡不准安靜地跑（lint 擋、引擎不退回全域名字）。

為什麼要對整個 registry 跑：這三件事都不是某一張卡的行為，是**卡片這個東西**
的行為。逐張列舉的測試會在加第 18 張卡的那天安靜地留下一個沒被測到的角落。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF                  # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

from adept.core.pipeline import get_step, list_steps  # noqa: E402
from adept.ui import canvas as canvas_mod           # noqa: E402
from adept.ui import studio as studio_mod           # noqa: E402
from adept.ui import theme as theme_mod             # noqa: E402
from adept.ui.scope import HIDDEN_STEPS             # noqa: E402


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


def _every_card(window):
    """把卡片庫裡每一張卡都加進畫布，逐一 yield ``(key, 節點圖元)``。"""
    first = window.model.node_order[0]
    for cls in list_steps():
        if cls.key in HIDDEN_STEPS:
            continue
        nid = window.add_card_after(first, cls.key)
        item = window.pipeline.node_item(nid)
        assert item is not None, "%s 加進去了但畫布上沒有" % cls.key
        yield cls.key, item


# --------------------------------------------------------------------------- #
# 1. 埠點到的是自己那一顆
# --------------------------------------------------------------------------- #
def test_every_output_port_grabs_itself(window):
    """點在一顆埠的圓心上，拉出來的必須是**那一條**流。

    以前 ``out_port_at`` 取的是「由上往下第一個落在半徑內的」，而抓取半徑
    （15px）比三個埠的間距（14px）大 —— 於是 ``subtract`` 的三顆埠裡，點
    ``test`` 拉到 ``diff``、點 ``ref`` 拉到 ``test``。

    使用者回報的是「一連多的時候點不到、線拉不出來」，但真相更糟：**線拉得
    出來，只是接到隔壁那條流**，而那條線在畫面上看起來完全正常。
    """
    wrong = []
    for key, item in _every_card(window):
        names = item.out_names()
        for i, anchor in enumerate(item.out_anchors_local()):
            got = item.out_port_at(anchor)
            if got != i:
                wrong.append("%s：想拉 %s，實際拉到 %s"
                             % (key, names[i],
                                names[got] if got is not None else "沒中"))
    assert not wrong, "點在埠心上卻拉到別條流：\n  " + "\n  ".join(wrong)


def test_the_hit_area_is_the_grab_area(window):
    """``shape()`` 要涵蓋每一顆埠的抓取圈，``boundingRect()`` 要涵蓋 ``shape()``。

    兩層都會讓「點下去完全沒反應」：Qt 先用 boundingRect 粗篩再問 shape，
    所以任何一層小於 ``out_port_at`` 的判定圈，那一圈就是死的 —— 而使用者
    看到的是一顆畫在那裡、但按不動的埠。
    """
    r = canvas_mod._PORT_GRAB - 1.0
    for key, item in _every_card(window):
        shape, bounds = item.shape(), item.boundingRect()
        assert bounds.contains(shape.boundingRect()), (
            "%s：shape 伸出 boundingRect 之外，那一圈點不到" % key)
        anchors = [item.in_port_local()] + item.out_anchors_local()
        for anchor in anchors:
            assert shape.contains(anchor), "%s：埠心不在命中區裡" % key
            # 瞄埠的人常常落在圓點外圍，不是正中心
            for d in (QPointF(r, 0), QPointF(-r, 0),
                      QPointF(0, r), QPointF(0, -r)):
                assert shape.contains(anchor + d), (
                    "%s：埠的抓取圈有一段不在命中區裡" % key)


# --------------------------------------------------------------------------- #
# 2. 剛加進來的卡，前後都是空的
# --------------------------------------------------------------------------- #
def test_a_new_card_has_no_source_and_no_output(window):
    """**每一張**卡加進畫布時都不帶來源，因此也不吐任何流。

    以前每張卡都帶著自己的預設來源（``source="diff"``、``streams="test"``），
    於是畫布上一加卡就前後各長出一顆埠 —— 而那些流沒有任何一條線指向它們。
    最糟的是它**跑得動**：引擎查不到線就退回「執行順序上最後一個寫這個名字
    的人」，所以「還沒接線」與「接好了」算出來的數字一模一樣（實測逐項相同）。
    """
    for key, item in _every_card(window):
        node = window.model.nodes[item.node_id]
        step = get_step(node.step)
        if not step.input_specs():
            continue                       # Input 卡本來就沒有來源
        empty = {s.name: node.params.get(s.name) for s in step.input_specs()}
        assert not any(empty.values()), "%s 一加進來就帶著來源 %s" % (key, empty)
        assert item.out_names() == [], (
            "%s 還沒接線就長出輸出埠 %s" % (key, item.out_names()))
        assert item.out_anchors_local() == [], "%s 拉得出線（但它什麼都還沒算）" % key


def test_the_output_appears_only_when_every_input_is_connected(window):
    """`Compare to stream` 要兩條流才算得出 diff —— 接一條的時候後面不該有東西。

    使用者的原話：「在還沒有把給定 image source 來源填上時，後方的 Node 節點
    diff 也不該出現（只有在設定內 first stream 跟 second stream 都填上時，
    diff 才會出現）」。
    """
    src = window.model.node_order[0]
    sub = window.add_card_after(src, "subtract")
    card = window.pipeline.node_item(sub)
    assert card.out_names() == []

    window._on_edge_added(src, sub, "test", "a")
    assert window.pipeline.node_item(sub).out_names() == [], \
        "只接了一條就長出 diff —— 那條 diff 還算不出來"

    window._on_edge_added(src, sub, "ref", "b")
    assert "diff" in window.pipeline.node_item(sub).out_names()


def test_the_output_port_carries_the_name_the_user_gave_it(window):
    """輸出流改名，畫布上那顆埠要跟著改名（使用者要求）。

    ``write result to`` 是 recipe 裡真正的流名，也是下游要指的那個字。
    畫布上還印著 ``diff`` 的話，使用者就得自己在腦裡做一次翻譯 ——
    而「兩張卡都叫 diff」正是他想用改名解掉的問題。
    """
    src = window.model.node_order[0]
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")

    window.model.set_param(sub, "out", "GGG")
    window._refresh_pipeline()
    outs = window.pipeline.node_item(sub).out_names()
    assert "GGG" in outs and "diff" not in outs, outs


def test_an_unconnected_card_is_refused_before_it_can_produce_numbers(window):
    """沒有來源的卡**不准安靜地跑**：lint 擋、畫布掛警示、引擎也不放行。

    三層都要有，因為它們各自回答不同的時機：lint 是「按 Run trial 之前」、
    畫布是「現在看著它的時候」、引擎是「別的路徑（CLI、舊檔）繞進來的時候」。
    """
    src = window.model.node_order[0]
    nid = window.add_card_after(src, "glv_stats")

    codes = [i.code for i in window.model.validate() if i.node_id == nid]
    assert "not-connected" in codes
    assert window.pipeline.node_item(nid).problem(), "畫布上沒有任何標記"

    # 引擎那一層：直接問卡片，不必真的跑一批
    node = window.model.nodes[nid]
    assert get_step(node.step).missing_inputs(node.params) == ["source"]

    # 接上線之後三層一起變乾淨
    window._on_edge_added(src, nid, "test", "source")
    assert [i.code for i in window.model.validate() if i.node_id == nid] == []


def test_every_image_parameter_says_whether_it_is_an_input(window):
    """``image_key`` / ``image_keys`` 一律要宣告方向 —— 沒宣告的卡註冊不進來。

    這條測試存在的理由是**下一張卡**：畫布靠 ``direction`` 決定要畫幾顆輸入埠、
    輸出埠要不要等來源接齊。用推的（「值有出現在 reads 裡就算輸入」）會在來源
    被清空的那一刻失效，而那正是新卡的常態。
    """
    for cls in list_steps():
        for spec in cls.params:
            if spec.type in ("image_key", "image_keys"):
                assert spec.direction in ("in", "out"), \
                    "%s.%s 沒說自己是輸入還是輸出" % (cls.key, spec.name)
            else:
                assert spec.direction == "", \
                    "%s.%s 不是影像流參數卻宣告了方向" % (cls.key, spec.name)
