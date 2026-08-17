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

from adept.core.pipeline import list_steps          # noqa: E402
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
