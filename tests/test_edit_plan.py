# U6：接線／換線／剪線的語意 —— **不開視窗就問得出來** — authored 2026-09-08.
"""這幾條以前只有開一個 `QMainWindow` 才驗得到。

`_connect` / `_connect_region` / `_drop_conflicting_edges` / `_unpoint_stream`
/ `_unmet_needs` / `_producers_of` 是**引擎正確性的一半** —— F9／F10／F42 那三輪
踩過的七個「跑得完、有數字、而且是錯的」全部發生在這幾支裡。而它們住在
`studio.py` 裡，所以每一條相關的測試都得先開視窗、等版面、關視窗。

U6 把「決定」抽進 `ui/edit_plan.py`（純函式，吃 `RecipeModel` —— 那個東西本來
就不碰 Qt）。**這一份因此一行 Qt 都沒有 import**，而它守的是同一批不變量：

* 一個輸入埠只能有一條線（F9-7），而「搶不搶」的判準對 `image_key` 與
  `image_keys` 不一樣；
* 剪一條線不可以連旁邊那條一起剪（F10 的那個洞）；
* 區域線帶的是區域名，不是影像流（F42 B2）；
* 剪掉線之後那一格要跟著空掉，不然畫布反過來說謊。

⚠ **這一支跑在核心那一批裡**（不 import Qt），所以它幾百毫秒就有答案 ——
那正是把它們搬出來換到的東西。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps                      # noqa: E402,F401 — 註冊卡片
from d4t.ui import edit_plan               # noqa: E402
from d4t.ui.viewmodel import RecipeModel   # noqa: E402


def _model(kind: str = "ebi_patch") -> RecipeModel:
    """一張空白畫布 + 這種資料的那張載入卡。

    ``RecipeModel.starter()`` 是**真的空的**（F11 Input-4：預先放一張就是替
    使用者決定了他還沒決定的事）—— 所以這裡自己補一張，好讓每一支測試都能拿
    ``node_order[0]`` 當「上游那張卡」。
    """
    m = RecipeModel.starter(kind)
    nid = m.add_step(RecipeModel.STARTER_STEP)
    # 一顆一張的資料：名字表一列（F121 期 2 之前這裡是 `load_single`）。
    if kind in ("rsem", "folder"):
        m.set_param(nid, "channel_map", "1:single")
    return m


def _add(model: RecipeModel, step: str) -> str:
    """加一張卡，回它的 node id（`add_step` 的回傳就是那個 id）。"""
    return model.add_step(step)


# --------------------------------------------------------------------------- #
# 這條線落在哪一格
# --------------------------------------------------------------------------- #
def test_an_empty_input_wins_over_one_that_is_already_taken():
    """沒有指定落點時挑「第一個**還空著**的輸入」。

    以前這裡是一張寫死的名單（``streams`` → ``target`` → ``source``），於是
    ``subtract`` 的 a / b 永遠只挑得到同一個 —— 兩顆輸入的卡在畫布上根本分不開。
    """
    m = _model()
    load = m.node_order[0]
    sub = _add(m, "subtract")
    assert edit_plan.param_for_stream(m, sub) == "a"

    m.set_param(sub, "a", "test")
    assert edit_plan.param_for_stream(m, sub) == "b", \
        "第一格已經有值了，第二條線該落到還空著的那一格"
    del load


def test_a_card_with_no_input_says_so_rather_than_guessing():
    m = _model()
    assert edit_plan.param_for_stream(m, m.node_order[0]) == "", \
        "Input 卡沒有輸入 —— 不該硬挑一格"


# --------------------------------------------------------------------------- #
# 一個輸入埠只能有一條線（F9-7）
# --------------------------------------------------------------------------- #
def test_a_role_port_lets_the_old_line_go_even_from_the_same_card():
    """**判準是「不是剛拉的這一條」，不是「來源不同的那些」**（F10 修）。

    從同一張卡先拉 test 再拉 ref 到同一顆角色埠時，來源相同 —— 舊的判準把它
    放過去，於是參數換成了 ref、而畫布上兩條線都還在。那正是 F9-7 擋下來的
    東西（引擎只認其中一條，而畫面上看不出是哪條）。
    """
    m = _model()
    load = m.node_order[0]
    sub = _add(m, "subtract")
    assert m.add_edge(load, sub, src_out="test", dst_in="a")

    plan = edit_plan.plan_connect(m, load, sub, "ref", dst_in="a")
    assert plan.kind == edit_plan.IMAGE and plan.param == "a"
    assert [(e.src, e.src_out) for e in plan.conflicts] == [(load, "test")], \
        "同一張卡拉來的舊線也要讓位 —— 一顆角色埠只放得下一條"


def test_a_multi_stream_port_only_fights_over_the_same_stream_name():
    """``image_keys`` 可以同時做好幾條 —— 一條給 test、一條給 ref 是兩個 key。"""
    m = _model()
    load = m.node_order[0]
    den = _add(m, "denoise")
    assert m.add_edge(load, den, src_out="test", dst_in="streams")

    same = edit_plan.plan_connect(m, load, den, "test", dst_in="streams")
    assert same.already, "同一條線再拉一次 = 什麼都不用做"

    other = edit_plan.plan_connect(m, load, den, "ref", dst_in="streams")
    assert other.conflicts == [], "ref 跟 test 不搶同一個 key"
    assert other.accumulate is True, "這一格上已經有線了 → 累加，不是取代"


def test_the_first_line_on_a_port_replaces_rather_than_accumulates():
    """卡片預設的 ``streams="test"`` 是規格的預設值，不是使用者拉的線。

    把 ref 累加上去的話，他拉了一條卻得到兩條，而畫布就說謊了。
    """
    m = _model()
    load = m.node_order[0]
    den = _add(m, "denoise")
    plan = edit_plan.plan_connect(m, load, den, "ref", dst_in="streams")
    assert plan.accumulate is False


def test_conflicts_are_the_same_before_and_after_the_edge_lands():
    """**先算 conflicts、後 `add_edge` 是安全的** —— 這一條就是那句話的證據。

    `_connect` 現在先問計畫再動 model，而原本的順序是反的。篩子把「剛拉的
    這一條」明確排除掉了，所以兩種順序算得出同一組答案 —— 但那是一句需要被
    釘住的話，不是一個可以用讀的相信的東西。
    """
    m = _model()
    load = m.node_order[0]
    sub = _add(m, "subtract")
    m.add_edge(load, sub, src_out="test", dst_in="a")

    before = edit_plan.conflicting_edges(m, load, sub, "ref", "a")
    m.add_edge(load, sub, src_out="ref", dst_in="a")
    after = edit_plan.conflicting_edges(m, load, sub, "ref", "a")
    assert [(e.src, e.src_out) for e in before] == \
           [(e.src, e.src_out) for e in after]


# --------------------------------------------------------------------------- #
# 剪一條線
# --------------------------------------------------------------------------- #
def test_cutting_a_line_empties_the_box_it_pointed_at():
    """畫面上那條線沒了，卡片不可以還在處理它。"""
    m = _model()
    load = m.node_order[0]
    sub = _add(m, "subtract")
    m.add_edge(load, sub, src_out="test", dst_in="a")
    m.set_param(sub, "a", "test")

    plan = edit_plan.plan_unpoint(m, sub, "test", "a")
    assert plan.change is True and plan.value == "", \
        "角色埠：那條線就是它的全部來源"


def test_cutting_one_of_two_streams_keeps_the_other():
    m = _model()
    load = m.node_order[0]
    den = _add(m, "denoise")
    m.set_param(den, "streams", "test,ref")
    plan = edit_plan.plan_unpoint(m, den, "test", "streams")
    assert plan.change is True and plan.value == "ref"


def test_it_would_rather_do_nothing_than_guess_which_line_was_cut():
    """指不出剪的是哪一條就不動 —— 猜錯的話那張卡會安靜地改做別的流。"""
    m = _model()
    den = _add(m, "denoise")
    m.set_param(den, "streams", "test,ref")
    plan = edit_plan.plan_unpoint(m, den, "", "streams")
    assert plan.change is False


def test_a_region_box_is_not_this_functions_business():
    """區域那一格的值是從線水合出來的（F42 B2）。

    在這裡動它 = 在線還在的時候讓參數跟線說不同的話。
    """
    m = _model()
    glv = _add(m, "glv_stats")
    plan = edit_plan.plan_unpoint(m, glv, "epi", "roi")
    assert plan.change is False


# --------------------------------------------------------------------------- #
# 區域線
# --------------------------------------------------------------------------- #
def test_an_image_line_into_a_region_port_is_refused_with_a_next_step():
    """放行的話那一格會變成一個沒有人定義的區域名 —— 跑起來是 `unknown-region`，
    而畫面上那條線看起來完全正常。"""
    m = _model()
    load = m.node_order[0]
    glv = _add(m, "glv_stats")
    plan = edit_plan.plan_connect(m, load, glv, "test", dst_in="roi")
    assert plan.kind == edit_plan.REJECT
    assert "image stream, not a region" in plan.reject
    assert "diamond port" in plan.reject, "要講得出可以照做的下一句話"


def test_a_region_line_into_an_image_port_is_refused_too():
    m = _model()
    load = m.node_order[0]
    roi = _add(m, "roi_reference")
    m.add_edge(load, roi, src_out="test", dst_in="source")
    den = _add(m, "denoise")
    name = next(iter(m.region_outputs(roi)), "")
    assert name, "roi_reference 應該吐得出區域"
    plan = edit_plan.plan_connect(m, roi, den, name, dst_in="streams")
    assert plan.kind == edit_plan.REJECT
    assert "no region input" in plan.reject


def test_a_single_role_region_port_swaps_and_a_list_one_adds_up():
    """`region_key` 的第二條線是「改接別的」，`region_keys` 的是「這個也算」。"""
    m = _model()
    load = m.node_order[0]
    roi = _add(m, "roi_reference")
    m.add_edge(load, roi, src_out="test", dst_in="source")
    glv = _add(m, "glv_stats")
    names = list(m.region_outputs(roi))
    assert names
    m.add_edge(roi, glv, src_out=names[0], dst_in="roi")

    # `roi` 是 region_keys（一串）—— 第二條線累加，一條都不讓位。
    plan = edit_plan.plan_connect(m, roi, glv, names[-1], dst_in="roi")
    if names[-1] != names[0]:
        assert plan.conflicts == [], "region_keys 的第二條線是累加"


# --------------------------------------------------------------------------- #
# 「這張卡還缺什麼」
# --------------------------------------------------------------------------- #
def test_a_freshly_added_card_says_what_it_needs_and_who_makes_it():
    """**「還缺 test」不夠，「先加一張 Load images」才是做得下去的話**（推廣鐵則）。

    這裡刻意用一張**還沒有載入卡**的空白畫布 —— 那正是「加了一張量測卡，而它
    上面什麼都沒有」的那一刻。
    """
    m = RecipeModel.starter("ebi_patch")
    glv = _add(m, "glv_stats")
    said = edit_plan.unmet_needs(m, glv)
    assert said, "剛加的卡什麼都還沒接，不該說「什麼都不缺」"
    assert "still needs the image stream" in said
    assert "add " in said, "要講得出那條流是誰產的"


def test_a_card_that_has_its_line_says_nothing():
    m = _model()
    load = m.node_order[0]
    den = _add(m, "denoise")
    m.add_edge(load, den, src_out="test", dst_in="streams")
    m.set_param(den, "streams", "test")
    assert edit_plan.unmet_needs(m, den) == ""


def test_a_region_line_is_not_counted_as_an_image_stream():
    """算進來的話，一張接了 `epi` 的卡會被當成「它已經有一條叫 epi 的流」。

    這是 F42 B2 那一條，而它以前只有開視窗才驗得到。
    """
    m = _model()
    load = m.node_order[0]
    roi = _add(m, "roi_reference")
    m.add_edge(load, roi, src_out="test", dst_in="source")
    glv = _add(m, "glv_stats")
    names = list(m.region_outputs(roi))
    assert names
    m.add_edge(roi, glv, src_out=names[0], dst_in="roi")

    said = edit_plan.unmet_needs(m, glv)
    assert names[0] not in said.split("point it at one of:")[-1], \
        "區域名不該出現在「這張卡有哪些影像流」那一串裡"


def test_who_makes_this_stream_reads_the_card_library():
    """答案是從卡片宣告長出來的，不是一張寫死的名單。"""
    makers = edit_plan.producers_of(_model(), "diff")
    assert makers, "沒有任何一張卡說它產得出 diff？"
    assert all(isinstance(m, str) and m for m in makers)


def test_the_planner_does_not_need_qt():
    """**驗收條件本身**：這幾條不必開視窗就問得出來。

    U6 換到的正是這件事 —— 而一條「後來偷偷把 Qt 拉進來」的相依會讓它安靜地
    失效（那一族本來就慢，多一支沒有人會發現）。

    ⚠ **在一個新的行程裡問。** 這一條以前問的是
    ``"PySide6.QtWidgets" not in sys.modules`` —— 而那是一個**行程層的事實**：
    `tools/run_tests.py` 逐檔一個行程，所以它在本機是綠的；CI 用**一個行程**跑
    整套，於是別的測試檔先把 Qt import 進來，這一條就紅了（實測：本機全綠、
    CI 三個 Python 版本全紅）。

    一條「只有在某一種跑法下才成立」的斷言不是一道關，它是一個會挑時間響的
    鬧鐘。真正要問的是**這個模組自己需不需要 Qt**，而那件事只有在一個乾淨的
    直譯器裡問得準。

    ⚠ **這個 repo 已經學過這一課了**：`tests/test_no_qt.py::test_no_qt_after_import`
    的說明從頭到尾講的就是同一件事（「以前是在測試行程裡直接看 `sys.modules`，
    那讓這條測試變成跟執行順序有關」）。我沒有讀到它就重寫了一次同樣的錯 ——
    寫下這一段是為了讓下一個人在**這裡**也讀得到那句話。
    """
    import subprocess

    code = (
        "import sys, importlib\n"
        "importlib.import_module('d4t.ui.edit_plan')\n"
        "bad = [m for m in sys.modules if m.startswith('PySide6')]\n"
        "print(','.join(sorted(bad)))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    pulled = [m for m in out.stdout.strip().split(",") if m]
    assert not pulled, (
        "`ui/edit_plan` 把 Qt 拉進來了：%s\n"
        "  它是純函式層（吃 `RecipeModel`，而那個東西本來就不碰 Qt）——"
        "  真的動 widget 的那一段住在 `studio.py`。" % pulled)
