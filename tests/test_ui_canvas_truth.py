# 畫布不能說謊 —— 性質測試 — authored 2026-08-24（bug 獵捕的 B1／B5）。
"""**這是 F9／F10 那兩輪換來的東西，而在這一份之前沒有任何測試在守它。**

不變量只有一句：

    一張卡的某一格輸入指著一條影像流  ⇔  畫布上有一條線落在那一格。

兩個方向都要成立，而兩個方向壞掉的樣子不一樣：

* **參數有、線沒有** —— 引擎退回隱含綁定（「執行順序上最後一個寫這條流的
  人」），也就是**用猜的**。線性的時候猜的跟真的一樣所以看不出來，
  分岔的時候猜錯，而且跑得完、有數字。
* **線有、參數空** —— 那張卡根本不會去處理那條流，畫面上卻畫著一條線。

為什麼是性質測試而不是幾條寫死的案例
------------------------------------
F9／F10 修過的東西**全部**是這個形狀（六個「跑得完、有數字、而且是錯的」），
而它們每一個都是靠人「剛好想到那個組合」才發現的。寫死的案例只守得住已經
想到的那幾個；這一份讓機器去撞 —— 隨機的接線／剪線序列，每一步之後檢查。

它抓到的第一個東西就是 B1（見下面那條迴歸測試）：`_drop_conflicting_edges`
挑線挑得很精確（比對 `dst_in`），剪的時候卻只帶 `src_out` —— 於是同一個來源
餵到下游卡好幾個埠的時候，剪一條會剪掉一整排。400 組隨機序列裡有六種不同的
重現路徑。

只做使用者做得到的動作
----------------------
* **接線**：從任一顆輸出埠拖到任一格輸入（任何組合都拖得出來）。
* **剪線**：只對**畫布上真的存在的那條線**按剪刀，而且帶著它自己的埠 ——
  剪刀是畫在線上的，所以剪一條不存在的線不是使用者做得到的事。

第一版沒有分這件事，於是它「抓到」十幾個違反，而那些全部是拿剪刀去剪空氣。
**一條抓得到不存在的問題的測試，跟一條什麼都抓不到的測試一樣沒用。**

不建整個 `StudioWindow`
-----------------------
接線的邏輯住在 `StudioWindow._connect` / `_on_edge_removed`，而建一個真的
`QMainWindow` 實測要一分多鐘。:class:`Shim` 把那些方法借過來綁到一個只有
`model` 的殼上 —— 跑的是**真的那段程式碼**，不是一份抄本。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.step import REGISTRY  # noqa: E402
from d4t.ui import scope  # noqa: E402
from d4t.ui import studio as studio_mod  # noqa: E402
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


class Shim:
    """借用 `StudioWindow` 的方法，但只有一個 ``model``。

    `__getattr__` 把找不到的名字轉成 `StudioWindow` 上同名的方法並綁到自己 ——
    所以 `_connect` 裡呼叫的 `_param_for_stream`、`_point_at_stream`、
    `_drop_conflicting_edges`、`_autofill_new_card` 全部是**真的那幾支**。

    只有兩樣東西是假的：`_status`（把狀態列的話收進 list）與 `_gds_layers`
    （`_autofill_new_card` 會讀它，真的視窗上是掛上來的 GLAS 匯出）。

    ⚠ ``selected_node`` 是**一個值不是一支方法**，所以 `__getattr__` 借不到它
    —— 這裡明講「這個殼上沒有選著任何卡」。接線那幾支收尾會問一次
    （`_resync_params`：動到的是不是選著的那一張），而在這裡答案永遠是「不是」，
    於是它什麼都不做 —— 這個殼本來就沒有設定欄可以重畫。
    """

    def __init__(self, model: RecipeModel) -> None:
        self.model = model
        self.messages: list = []
        self._gds_layers: list = []
        self.selected_node = ""

    def _status(self, text: str, level: str = "info") -> None:
        self.messages.append(str(text))

    def __getattr__(self, name):
        fn = getattr(studio_mod.StudioWindow, name, None)
        if fn is None or not callable(fn):
            raise AttributeError(name)
        return fn.__get__(self, type(self))


# --------------------------------------------------------------------------- #
# 不變量
# --------------------------------------------------------------------------- #
def _named_streams(spec, value) -> list:
    """這一格參數指著哪幾條流（``image_keys`` 是一串、``image_key`` 是一條）。"""
    if spec.type == "image_keys":
        return [x.strip() for x in str(value or "").split(",") if x.strip()]
    text = str(value or "").strip()
    return [text] if text else []


def canvas_lies(model: RecipeModel) -> list:
    """畫布說謊的地方（空 list = 畫面與參數對得起來）。"""
    lines_in: dict = {}
    for e in model.edges:
        lines_in.setdefault((e.dst, e.dst_in), []).append(e)

    out = []
    for nid, node in model.nodes.items():
        step = REGISTRY.get(node.step)
        if step is None:
            continue
        for spec in step.input_specs():
            named = _named_streams(spec, node.params.get(spec.name, spec.default))
            lines = lines_in.get((nid, spec.name), [])
            if named and not lines:
                out.append("%s.%s 指著 %r，但畫布上沒有線落在這一格"
                           % (nid, spec.name, ",".join(named)))
            if lines and not named:
                out.append("%s.%s 上有 %d 條線，但那一格是空的"
                           % (nid, spec.name, len(lines)))
    return out


def _blank_canvas(rnd: random.Random, n_cards: int) -> tuple:
    """一張乾淨的畫布：幾張卡、零條線、每一格輸入都是空的。

    **每一格輸入都要清空**是重點：卡片的 `ParamSpec` 帶著預設流名
    （`streams="test"`），而剛加進來的卡在畫布上是沒有線的 —— 那個狀態本身
    就違反不變量，但它是 F10 定的（「一張卡片剛被 new add 時，前後應該都是
    空的乾淨的」），由 `RecipeModel.add_step` 之外的路徑負責。這一份測的是
    **接線這件事**，所以從一個對得起來的狀態出發。
    """
    keys = [k for k in sorted(REGISTRY)
            if k not in scope.HIDDEN_STEPS
            and not k.startswith("output_")
            and k not in ("pair_source", "load_sidecar")]
    model = RecipeModel.starter("ebi_patch")
    ids = [model.add_step("load_patch")]
    for _ in range(n_cards):
        ids.append(model.add_step(rnd.choice(keys)))
    for e in list(model.edges):
        model.remove_edge(e.src, e.dst, e.src_out or None)
    for nid in ids:
        for spec in REGISTRY[model.nodes[nid].step].input_specs():
            model.set_param(nid, spec.name, "")
    return model, ids


#: 幾組隨機序列。400 組 × 25 步在本機約 1.5 秒 —— 便宜到不必為了時間縮水，
#: 而它抓 B1 的那幾顆種子散在 200 以後（第一版只跑 100 組就漏掉了）。
SEEDS = 400
STEPS = 25


def _one_run(seed: int) -> tuple:
    """跑一組隨機的接線／剪線序列，回 ``(違反的話, 做過的動作)``。"""
    rnd = random.Random(seed)
    model, ids = _blank_canvas(rnd, rnd.randint(2, 4))
    win = Shim(model)
    history: list = []
    for _ in range(STEPS):
        if model.edges and rnd.random() < 0.35:
            edge = rnd.choice(list(model.edges))
            win._on_edge_removed(edge.src, edge.dst, edge.src_out, edge.dst_in)
            history.append("剪 %s.%s → %s.%s" % (edge.src, edge.src_out,
                                                 edge.dst, edge.dst_in))
        else:
            a, b = rnd.sample(ids, 2)
            outs = REGISTRY[model.nodes[a].step].resolve_writes(
                model.nodes[a].params) or []
            ins = [s.name for s in REGISTRY[model.nodes[b].step].input_specs()]
            if not outs or not ins:
                continue
            src_out, dst_in = rnd.choice(outs), rnd.choice(ins)
            win._connect(a, b, src_out, dst_in)
            history.append("接 %s.%s → %s.%s" % (a, src_out, b, dst_in))
        lies = canvas_lies(model)
        if lies:
            return lies, history
    return [], history


def test_the_canvas_never_lies_about_where_a_card_gets_its_data():
    """隨機的接線／剪線序列，每一步之後畫面與參數都要對得起來。

    紅的時候訊息會印出**做過的每一個動作** —— 隨機測試最貴的不是它會紅，
    是紅了之後不知道怎麼重現。
    """
    for seed in range(SEEDS):
        lies, history = _one_run(seed)
        assert not lies, (
            "seed=%d 之後畫布說謊了：\n  %s\n做過的動作：\n  %s"
            % (seed, "\n  ".join(lies), "\n  ".join(history)))


def test_the_random_sequences_actually_connect_and_cut_things():
    """上面那一支必須真的在接線與剪線 —— 否則它是一條永遠會綠的測試。

    這個 repo 踩過四次「測試通過，只是什麼都沒測」，所以每一條性質測試都要有
    一條同伴證明它不是空轉的（同 `test_card_invariants.py` 的
    ``…_is_not_vacuous``）。
    """
    total_cuts = total_cons = 0
    peak_edges = 0
    for seed in range(40):
        rnd = random.Random(seed)
        model, ids = _blank_canvas(rnd, rnd.randint(2, 4))
        win = Shim(model)
        for _ in range(STEPS):
            if model.edges and rnd.random() < 0.35:
                e = rnd.choice(list(model.edges))
                win._on_edge_removed(e.src, e.dst, e.src_out, e.dst_in)
                total_cuts += 1
            else:
                a, b = rnd.sample(ids, 2)
                outs = REGISTRY[model.nodes[a].step].resolve_writes(
                    model.nodes[a].params) or []
                ins = [s.name for s in REGISTRY[model.nodes[b].step].input_specs()]
                if not outs or not ins:
                    continue
                win._connect(a, b, rnd.choice(outs), rnd.choice(ins))
                total_cons += 1
            peak_edges = max(peak_edges, len(model.edges))
    assert total_cons > 200, total_cons
    assert total_cuts > 50, total_cuts
    assert peak_edges >= 3, "序列從來沒有讓畫布上同時有三條線 —— 撞不到並排的情況"


# --------------------------------------------------------------------------- #
# B1：剪線少帶 dst_in，會剪掉同一個來源餵到別的埠的線
# --------------------------------------------------------------------------- #
@pytest.fixture()
def canvas():
    """`load_patch` + `subtract` + `denoise`，零條線、每一格都空著。"""
    model = RecipeModel.starter("ebi_patch")
    ids = {k: model.add_step(k) for k in ("load_patch", "subtract", "denoise")}
    for e in list(model.edges):
        model.remove_edge(e.src, e.dst, e.src_out or None)
    for nid in ids.values():
        for spec in REGISTRY[model.nodes[nid].step].input_specs():
            model.set_param(nid, spec.name, "")
    return Shim(model), ids


def test_replacing_one_input_leaves_the_other_input_alone(canvas):
    """**B1 的迴歸測試。**

    ``load`` 的同一顆輸出埠餵 ``subtract`` 的 a 與 b 兩格（合法：兩條線的
    ``dst_in`` 不同）。把別的卡接到 b 的時候，只有 b 那條該讓位。

    在修好之前這裡會斷兩條 —— `_drop_conflicting_edges` 挑出來的只有 b 那條，
    但 `remove_edge` 少了 `dst_in`，於是「符合這個 src_out 的全部」把 a 那條
    一起帶走了。而 a 的參數還留著，所以畫布上沒有線、卡片卻還指著那條流。
    """
    win, ids = canvas
    load, sub, den = ids["load_patch"], ids["subtract"], ids["denoise"]
    win._connect(load, sub, "test", "a")
    win._connect(load, sub, "test", "b")
    win._connect(load, den, "test", "streams")
    assert not canvas_lies(win.model)

    win._connect(den, "%s" % sub, "denoise", "b")

    on = {(e.dst_in): (e.src, e.src_out) for e in win.model.edges if e.dst == sub}
    assert "a" in on, "沒有人碰 a，但 a 那條線被一起剪掉了"
    assert on["a"] == (load, "test")
    assert on["b"] == (den, "denoise")
    assert not canvas_lies(win.model)


def test_a_second_line_from_the_same_source_into_another_port_is_allowed(canvas):
    """上面那條測試的前提：同一個來源餵兩格**本來就該成立**（F9-9 的多連一）。

    這一條顧的是「前提沒了測試就空轉」—— 如果哪天 `_connect` 改成不准這樣接，
    上面那一條會變成在測一個不存在的情境。
    """
    win, ids = canvas
    load, sub = ids["load_patch"], ids["subtract"]
    win._connect(load, sub, "test", "a")
    win._connect(load, sub, "test", "b")
    got = sorted((e.src_out, e.dst_in) for e in win.model.edges if e.dst == sub)
    assert got == [("test", "a"), ("test", "b")], got


# --------------------------------------------------------------------------- #
# B5：剪線的退路會剪掉兩張卡之間全部並排的線
# --------------------------------------------------------------------------- #
def test_cutting_a_line_with_no_stream_name_still_only_cuts_that_one(canvas):
    """**B5 的迴歸測試。**

    剪刀瞄不到流名（舊格式的線沒有埠）但埠問得出來的時候，
    以前 ``stream and …`` 整條短路掉，直接跳到「拿掉整對」——
    兩張卡之間有兩條並排的線時（F9-9 起是正常的接法），按一把剪刀會斷兩條。
    """
    win, ids = canvas
    load, sub = ids["load_patch"], ids["subtract"]
    win._connect(load, sub, "test", "a")
    win._connect(load, sub, "ref", "b")

    win._on_edge_removed(load, sub, "", "a")          # 沒有流名，只有埠

    left = sorted((e.src_out, e.dst_in) for e in win.model.edges if e.dst == sub)
    assert left == [("ref", "b")], "b 那條也被剪掉了：%r" % (left,)
    assert not canvas_lies(win.model)
