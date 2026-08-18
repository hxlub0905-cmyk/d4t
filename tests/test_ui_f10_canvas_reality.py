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

from conftest import first_source  # noqa: E402

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
    first = first_source(window)
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
        # **畫出來的埠**才要點得到。F11 Enhance-4 起入口卡沒有輸入埠
        # （它是最初始的 source，任何線都接不上去），所以這裡問的是
        # `in_anchors_local()`（畫幾顆就是幾顆）而不是 `in_port_local()`
        # （那個是給連線畫圖用的幾何點，畫面上沒有它）。
        anchors = item.in_anchors_local() + item.out_anchors_local()
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
    src = first_source(window)
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
    src = first_source(window)
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
    src = first_source(window)
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


# --------------------------------------------------------------------------- #
# 3. 量測卡也可以多連一（F10-3）
# --------------------------------------------------------------------------- #
def test_a_measure_card_takes_more_than_one_source(window):
    """兩條線接進同一張量測卡，兩條都算 —— 第二條不再把第一條踢掉。

    使用者定調（F9-9 的原話，F10 補上量測卡這一半）：「餵圖是節點跟節點間在
    處理的，卡片只負責把餵進來的 source 處理完丟出去，所以可以多連一，也可以
    一連多。」以前量測卡的 ``source`` 是單一角色，第二條線的意思是「改接
    別的」—— 想同時量 test 與 diff 就得放兩張卡，而那兩張卡的其他設定還得逐格
    對齊，對不齊的時候畫面上看不出來。
    """
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    glv = window.add_card_after(sub, "glv_stats")

    window._on_edge_added(sub, glv, "diff", "source")
    assert window.model.nodes[glv].params["source"] == "diff"

    window._on_edge_added(src, glv, "test", "source")
    assert window.model.nodes[glv].params["source"] == "diff,test", \
        "第二條線把第一條蓋掉了"
    assert len([e for e in window.model.edges if e.dst == glv]) == 2
    assert [i.code for i in window.model.validate() if i.node_id == glv] == []


def test_two_sources_get_the_stream_name_in_front_of_every_number(window):
    """接兩條就自動加流名前綴；**只接一條時名字跟以前逐字相同**。

    後半句是這個改動敢動既有 recipe 的唯一理由：分數表達式不必改寫，
    黃金值一個數字都不動（`tests/test_e2e_*` 與 freeze_golden 對著這件事）。
    """
    glv = get_step("glv_stats")
    one = glv.validate_params({"source": "diff", "metrics": "glv_max"})
    assert glv.resolve_features(one) == ["glv_max"]

    two = glv.validate_params({"source": "diff,test", "metrics": "glv_max"})
    assert glv.resolve_features(two) == ["diff_glv_max", "test_glv_max"]

    # 使用者自己填的 output_prefix 疊在流名後面，而且只有一個底線
    named = glv.validate_params({"source": "diff,test", "metrics": "glv_max",
                                 "output_prefix": "center"})
    assert glv.resolve_features(named) == ["diff_center_glv_max",
                                           "test_center_glv_max"]


def test_every_measure_card_can_take_more_than_one_source(window):
    """多連一是**量測卡這一類**的性質，不是某一張卡的功能。

    逐張列舉的話，加第 18 張量測卡的那天它會安靜地留在單一來源上 ——
    而症狀是「別張卡可以接兩條，這張不行」，使用者只會覺得工具壞了。
    """
    from adept.core.steps._util import MultiSourceStep

    for cls in list_steps():
        # 「量測卡」＝**只吐數字、不吐影像**的那一類。``snr_map`` 掛在 Measure
        # 這一組是因為它只為了餵 blob 而存在（見 step.py 的分組規則），但它
        # 產出的是一張圖 —— 多連一對它的意思是「一條流一張輸出圖」，那是另一
        # 個題目（要先決定輸出流怎麼命名），不在這一輪。
        if (cls.resolve_group() != "measure" or cls.key in HIDDEN_STEPS
                or cls.writes or not cls.features_out):
            continue
        assert issubclass(cls, MultiSourceStep), \
            "%s 是量測卡，但接不了第二條來源" % cls.key
        spec = next(sp for sp in cls.input_specs() if sp.name == cls.SOURCE)
        assert spec.type == "image_keys", \
            "%s.%s 還是單一來源的型別" % (cls.key, spec.name)


# --------------------------------------------------------------------------- #
# 4. 剪掉線 = 拿掉來源（F10-4）
# --------------------------------------------------------------------------- #
def test_cutting_a_line_puts_the_card_back_to_having_no_input(window):
    """按線上的 × 之後，那張卡要回到「剛加進來」的狀態。

    使用者回報：「連接卡片節點後，再把線按 X 清掉 → **後方卡片的 Node 不會
    跟著清掉**。」量出來比回報的更嚴重：兩條線都剪掉之後 `a='test' b='ref'`
    一個字都沒變、輸出埠還在、lint 說乾淨 —— 那張卡照樣跑得出數字。

    線是唯一的來源，所以剪掉線就是拿掉來源。**接線與剪線必須是彼此的反向操作**
    —— 只做一半的話，畫布會在「剪」這個方向上說謊。
    """
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    assert "diff" in window.pipeline.node_item(sub).out_names()

    window._on_edge_removed(src, sub, "ref", "b")
    assert window.model.nodes[sub].params["b"] == "", "剪掉的那一格沒有清空"
    assert window.model.nodes[sub].params["a"] == "test", "剪一條動到了另一格"
    assert window.pipeline.node_item(sub).out_names() == [], \
        "來源少了一條，diff 卻還掛在後面"

    window._on_edge_removed(src, sub, "test", "a")
    assert window.model.nodes[sub].params["a"] == ""
    assert window.model.edges == []
    assert [i.code for i in window.model.validate() if i.node_id == sub] \
        == ["not-connected"]


def test_wiring_and_cutting_are_exact_opposites_for_every_card(window):
    """接上再剪掉，每一張卡都要回到一模一樣的參數。

    對整個 registry 跑，因為這是**卡片這個東西**的性質：只要有人加一張卡而它
    的輸入型別剛好走到沒被覆蓋的那條路，畫布就會在剪線這個方向上說謊，而症狀
    （「數字沒跟著變」）跟接線那一半完全一樣難查。
    """
    src = first_source(window)
    for cls in list_steps():
        if cls.key in HIDDEN_STEPS or not cls.input_specs():
            continue
        nid = window.add_card_after(src, cls.key)
        before = dict(window.model.nodes[nid].params)
        spec = cls.input_specs()[0]
        window._on_edge_added(src, nid, "test", spec.name)
        assert window.model.nodes[nid].params[spec.name] == "test", cls.key
        window._on_edge_removed(src, nid, "test", spec.name)
        assert window.model.nodes[nid].params == before, \
            "%s：接上再剪掉之後參數跟原本不一樣" % cls.key
        assert not [e for e in window.model.edges if e.dst == nid]


# --------------------------------------------------------------------------- #
# 5. 刪掉卡片 = 連同它的線一起刪（F10-5）
# --------------------------------------------------------------------------- #
def test_deleting_a_card_takes_its_lines_with_it(window):
    """刪掉一張卡，碰到它的線要一起消失 —— 包含 model 裡那一份。

    使用者回報：「刪掉 Profile 這整個 Card 後，再 add new card profile，
    DAG 畫布上**線還會殘留**。」

    病根不是畫布沒重畫，是 ``RecipeModel.remove`` 只刪節點、不刪線。那條線
    留在 ``edges`` 裡指著一個不存在的節點（畫布不畫兩端不齊的線，所以看不
    出來），直到**新卡拿到同一個自動編號** —— ``_new_id`` 看到 `roi_cross`
    沒人用就再發一次，殘留的線於是接到一張使用者從來沒接過的新卡。

    而且那條線是假的：新卡的來源參數是空的，畫布與設定當場互相矛盾。
    """
    src = first_source(window)
    dn = window.add_card_after(src, "denoise")
    window._on_edge_added(src, dn, "ref", "streams")
    pr = window.add_card_after(dn, "roi_cross")
    window._on_edge_added(dn, pr, "ref", "source")
    assert len(window.model.edges) == 2

    window._on_remove_requested(pr)
    assert [(e.src, e.dst) for e in window.model.edges] == [(src, dn)], \
        "刪掉的卡還留著一條線在 model 裡"

    # 再加一張同型別的卡 —— 它會拿到同一個 node id，而線不可以跟著回來
    again = window.add_card_after(dn, "roi_cross")
    assert again == pr, "這條測試的前提是 node id 會被重複使用"
    assert not [e for e in window.model.edges if e.dst == again]
    assert not [e for e in window.pipeline._edges if e.pair()[1] == again], \
        "畫布上那條線殘留了"
    assert window.model.nodes[again].params["source"] == ""


def test_deleting_a_card_leaves_its_downstream_without_a_source(window):
    """被刪掉那張卡餵出去的下游，來源要跟著空掉（跟按 × 剪線同一條路）。

    不清的話下游指著一條**再也沒有人產出**的流：畫布上沒有線、參數卻還寫著
    `ref`，而那正是 F10 一路在拔的那種「看起來成立、跑起來不是那回事」。
    """
    src = first_source(window)
    dn = window.add_card_after(src, "denoise")
    window._on_edge_added(src, dn, "ref", "streams")
    glv = window.add_card_after(dn, "glv_stats")
    window._on_edge_added(dn, glv, "ref", "source")
    assert window.model.nodes[glv].params["source"] == "ref"

    window._on_remove_requested(dn)
    assert window.model.nodes[glv].params["source"] == "", \
        "上游被刪了，下游還指著它產的那條流"
    assert [i.code for i in window.model.validate() if i.node_id == glv] \
        == ["not-connected"]


# --------------------------------------------------------------------------- #
# 6. 改輸出流的名字 = 沿著線把下游帶著走（F10-6）
# --------------------------------------------------------------------------- #
def test_renaming_an_output_carries_the_downstream_with_it(window):
    """`write result to` 改成 GGG，下游要跟著指到 GGG —— 線不可以斷。

    稽核抓到的（不是使用者回報的）：改名之後下游的 `source` 還寫著 `diff`、
    線上的 `src_out` 也還是 `diff`，於是使用者只是幫一條流取個好記的名字，
    整條 pipeline 就 `missing-image` 了 —— 而畫布上**線還在**（線是照節點畫
    的），所以他看不出發生了什麼事。

    名字是**顯示用的標籤**，線才是「誰接誰」的事實。改名只該換標籤。
    """
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    glv = window.add_card_after(sub, "glv_stats")
    window._on_edge_added(sub, glv, "diff", "source")

    window.model.set_param(sub, "out", "GGG")

    assert window.model.nodes[glv].params["source"] == "GGG"
    assert [e.src_out for e in window.model.edges if e.dst == glv] == ["GGG"]
    assert [i.code for i in window.model.validate()] == [], \
        "改個名字就把 pipeline 弄斷了"
    window._refresh_pipeline()
    assert "GGG" in window.pipeline.node_item(sub).out_names()


def test_renaming_an_output_is_one_undo_step(window):
    """改名動到好幾張卡，但那是**一個**動作 —— Ctrl+Z 要一次全部回來。

    分成好幾步的話，按一次 Ctrl+Z 會停在「上游叫 GGG、下游還指著 diff」——
    一個使用者從來沒有做出來過的中間狀態。
    """
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    glv = window.add_card_after(sub, "glv_stats")
    window._on_edge_added(sub, glv, "diff", "source")
    before = window.model.snapshot()

    window.model.set_param(sub, "out", "GGG")
    assert window.model.undo() is True
    assert window.model.nodes[glv].params["source"] == "diff"
    assert window.model.nodes[sub].params["out"] == "diff"
    assert window.model.snapshot() == before

    window.model.redo()
    assert window.model.nodes[glv].params["source"] == "GGG"


def test_renaming_a_stream_on_a_multi_source_card_only_touches_that_one(window):
    """下游接了兩條流時，改名只換掉被改的那一條。"""
    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    glv = window.add_card_after(sub, "glv_stats")
    window._on_edge_added(sub, glv, "diff", "source")
    window._on_edge_added(src, glv, "test", "source")
    assert window.model.nodes[glv].params["source"] == "diff,test"

    window.model.set_param(sub, "out", "GGG")
    assert window.model.nodes[glv].params["source"] == "GGG,test"


# --------------------------------------------------------------------------- #
# 7. 輸出流的名字是使用者的（F10-7）
# --------------------------------------------------------------------------- #
def test_the_result_stream_name_is_editable_but_the_sources_are_not(window):
    """`write result to` 要打得進去；`a` / `b` 這種**來源**維持唯讀。

    使用者回報：「Write result to 沒辦法改名（不給輸入）。」病根是 F9-6 那條
    「來源只在畫布上決定」的規則按**型別**（image_key）套，而輸出名的型別
    一模一樣 —— 那時候還沒有 `direction`，只能連輸出一起鎖住。
    """
    from PySide6.QtWidgets import QLineEdit

    src = first_source(window)
    sub = window.add_card_after(src, "subtract")
    window._on_edge_added(src, sub, "test", "a")
    window._on_edge_added(src, sub, "ref", "b")
    window.select_node(sub)

    for name in ("a", "b"):
        ed = window.param_form.editor(name)
        assert isinstance(ed, QLineEdit) and ed.isReadOnly(), \
            "%s 是來源，應該只在畫布上決定" % name
    out = window.param_form.editor("out")
    assert isinstance(out, QLineEdit) and not out.isReadOnly(), \
        "輸出流的名字是使用者自己取的，不該唯讀"

    out.setText("GGG")
    assert window.model.nodes[sub].params["out"] == "GGG"


def test_a_result_stream_name_has_to_be_usable_as_a_variable(window):
    """流名會變成特徵前綴（`diff_glv_max`），而特徵名是分數表達式的變數名。

    所以空的／有空白／數字開頭的名字要擋在打字的當下 —— 不擋的話，使用者要
    到寫分數的時候才發現指不到，而那時候他已經不記得問題出在三張卡以前。
    """
    from adept.core.pipeline import ParamError

    cls = get_step("subtract")
    for bad in ("", "   ", "my stream", "2diff", "GG-G"):
        with pytest.raises(ParamError):
            cls.validate_params({"out": bad})
    for good in ("GGG", "my_stream", "_x2"):
        assert cls.validate_params({"out": good})["out"] == good


def test_a_cleared_input_is_never_reported_as_a_stream(window):
    """**每一張**卡：輸入清空之後，`resolve_reads` 不准回報任何流。

    這是「空的就偷偷退回預設」那個暗門的通用版本 —— `MultiStreamStep` 有過
    （`keys or ["test"]`）、`roi_mask` 有過（`or "test"`），兩次都是同一個
    形狀：宣告出來的東西比使用者接的多，而畫布是照宣告畫的。

    對 registry 跑，因為下一張卡最容易在這裡重犯：寫 `params.get("source",
    "test")` 是很自然的一行，而它在**值是空字串**的時候不會退回預設 ——
    退回預設的是那些多寫了 `or "test"` 的。
    """
    for cls in list_steps():
        if not cls.input_specs():
            continue
        cleared = cls.cleared_inputs(cls.validate_params({}))
        reads = [r for r in cls.resolve_reads(cleared) if str(r).strip()]
        assert reads == [], \
            "%s：輸入都清空了，卻還宣告讀 %s" % (cls.key, reads)
