# F24 ③：判定樹的編輯互動。
"""鎖住編輯層的六條性質：

1. `ensure_tree`：rules → 等價鏈狀樹（無損），而且 **rules 清空**（兩個都在
   是 `ambiguous-decision`）。
2. 樹的 setter 用路徑指節點；改 when／改葉子／加一步／插一步／拿掉一步。
3. 「加一步」原本那一類**留著**（掛在新步驟的 no 邊），新葉子拿一個沒用過
   的 bin（同 `add_rule` 的規則）。
4. 「拿掉一步」＝它的 no 邊接回上游（F24 §6）。
5. undo 一步回得來（樹進了 `_decide_snapshot`，F24 ① 就鎖了 —— 這裡鎖的是
   編輯動作真的各記一步）。
6. 面板：菱形＝Question + Yes/No 兩列；沒跑過 batch 那一行一個字都不畫。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Rule, TreeLeaf, TreeStep, rules_to_tree,
)
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


def _model_with_rules() -> RecipeModel:
    m = RecipeModel()
    m.decide = DecideSpec(
        let=[Let(name="contrast", expr="a * 2")],
        rules=[Rule(when="contrast > 100", bin=3, label="big"),
               Rule(when="contrast > 30", bin=2, label="mid")],
        otherwise_bin=0, otherwise_label="nuisance", score="contrast")
    m.clear_history()
    return m


def _model_with_tree() -> RecipeModel:
    m = _model_with_rules()
    m.ensure_tree()
    m.clear_history()
    return m


# --------------------------------------------------------------------------- #
# model（headless，不用 Qt）
# --------------------------------------------------------------------------- #
def test_ensure_tree_converts_and_clears_the_rules():
    m = _model_with_rules()
    want = rules_to_tree(m.decide)
    m.ensure_tree()
    assert m.decide.tree == want
    assert m.decide.rules == []              # 兩個都在是 ambiguous-decision
    before = m.decide.tree
    m.ensure_tree()                          # 第二次是 no-op
    assert m.decide.tree is before


def test_tree_node_walks_by_path():
    m = _model_with_tree()
    assert isinstance(m.tree_node(""), TreeStep)
    assert m.tree_node("y") == TreeLeaf(bin=3, label="big")
    assert m.tree_node("ny") == TreeLeaf(bin=2, label="mid")
    assert m.tree_node("nn") == TreeLeaf(bin=0, label="nuisance")
    assert m.tree_node("yy") is None         # 葉子下面沒有東西


def test_set_tree_when_touches_only_that_step():
    m = _model_with_tree()
    m.set_tree_when("n", "contrast > 55")
    assert m.tree_node("n").when == "contrast > 55"
    assert m.tree_node("").when == "contrast > 100"


def test_set_tree_leaf_edits_bin_and_label():
    m = _model_with_tree()
    m.set_tree_leaf("y", bin=7, label="huge")
    assert m.tree_node("y") == TreeLeaf(bin=7, label="huge")


def test_split_keeps_the_old_class_on_the_no_side():
    m = _model_with_tree()
    old = m.tree_node("y")
    m.split_tree_leaf("y")
    step = m.tree_node("y")
    assert isinstance(step, TreeStep) and step.when == ""
    assert step.no == old                    # 原本那一類留著
    fresh = step.yes
    assert isinstance(fresh, TreeLeaf)
    assert fresh.bin not in {0, 2, 3}        # 沒用過的 bin


def test_insert_above_hangs_the_subtree_on_the_no_side():
    m = _model_with_tree()
    old_root = m.tree_node("")
    m.insert_tree_step_above("")
    root = m.tree_node("")
    assert isinstance(root, TreeStep) and root.when == ""
    assert root.no == old_root
    assert isinstance(root.yes, TreeLeaf)


def test_remove_step_reconnects_the_no_side():
    m = _model_with_tree()
    no_side = m.tree_node("n")
    m.remove_tree_step("")
    assert m.tree_node("") == no_side


def test_every_edit_is_one_undo_step():
    m = _model_with_tree()
    base = m.decide.tree
    m.set_tree_when("", "contrast > 99")
    m.split_tree_leaf("y")
    assert m.tree_node("") .when == "contrast > 99"
    m.undo()
    assert isinstance(m.tree_node("y"), TreeLeaf)     # split 回去了
    assert m.tree_node("").when == "contrast > 99"    # when 還在
    m.undo()
    assert m.decide.tree == base


def test_feature_owners_maps_lets_to_the_entry_card():
    m = _model_with_tree()
    owners = m.feature_owners()
    assert owners.get("contrast") == ""      # let 中間值 → 入口卡


def test_the_algo_cards_are_gone_for_good():
    """F24 ④ 先把 `feature_math` / `feature_fill` **收起來**，
    Phase 3（2026-08-27）**刪掉**它們 —— 使用者：「功能已經被 `decide.let`
    取代了，刪掉」。

    ⚠ 這一條原本叫 ``algo_cards_are_shelved_not_deleted``，斷言的是「收起來但
    還在」。**收起來與刪掉是兩件不同的事，而它們的證據剛好相反** —— 所以這一條
    要跟著翻面，不是跟著刪：舊 recipe 帶著那兩張卡開起來，要拿到一條講得出來的
    `unknown-step`，不是一個 KeyError。

    這是 `CLAUDE.md` §5 那張對照表**第一次跑完全程**：不確定 → 先收起來（成本
    是一個字串）→ 使用者確定 → 再刪。
    """
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline.recipe import (
        Recipe, RecipeNode, ScoreSpec, validate,
    )
    from d4t.core.pipeline.step import REGISTRY
    from d4t.ui.scope import HIDDEN_STEPS

    for key in ("feature_math", "feature_fill"):
        assert key not in HIDDEN_STEPS, "刪掉的卡不該還留在「收起來」那張表上"
        assert key not in REGISTRY, key

    # 舊 recipe：載得進來（不炸），而 lint 講得出是哪一張卡不認得
    old = Recipe(recipe_id="legacy",
                 routes={"ebi_patch": ["load", "fm"]},
                 nodes={"load": RecipeNode("load", "load_patch", {}),
                        "fm": RecipeNode("fm", "feature_math",
                                         {"expr": "glv_mean * 2", "out": "v"})},
                 score=ScoreSpec(expr="v", threshold=1.0,
                                 bins={"below": 0, "above": 1}))
    issues = [i for i in validate(old, kind="ebi_patch") if i.level == "error"]
    assert [i.code for i in issues] == ["unknown-step"]
    assert "feature_math" in issues[0].title


# --------------------------------------------------------------------------- #
# 面板（要 Qt）
# --------------------------------------------------------------------------- #
def _import_qt(g):
    from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox

    from d4t.ui import theme as theme_mod
    from d4t.ui.tree_panel import TreePanel
    g.update(QApplication=QApplication, QLineEdit=QLineEdit,
             QSpinBox=QSpinBox, theme_mod=theme_mod, TreePanel=TreePanel)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _texts(panel):
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in panel.findChildren(QLabel)]


def test_the_panel_shows_the_question_as_three_pickers(qapp):
    """F25：問題不再是一格要自己打的算式，是「哪個數字·比什麼·多少」。"""
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox

    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    combos = panel.findChildren(QComboBox)
    assert any(c.currentText() == "contrast" for c in combos), \
        [c.currentText() for c in combos]
    assert any(c.currentText() == "greater than" for c in combos)
    spins = panel.findChildren(QDoubleSpinBox)
    assert any(s.value() == 100.0 for s in spins)
    texts = _texts(panel)
    assert any("Yes" in t for t in texts) and any("No" in t for t in texts)
    # yes 邊是葉子 → 名字可編；no 邊是另一步 → 一句摘要
    assert any(e.text() == "big" for e in panel.findChildren(QLineEdit))
    assert any("contrast > 30" in t for t in texts)


def test_dragging_the_value_writes_the_model(qapp):
    from PySide6.QtWidgets import QDoubleSpinBox

    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    spin = next(s for s in panel.findChildren(QDoubleSpinBox)
                if s.value() == 100.0)
    spin.setValue(88.0)
    assert m.tree_node("").when == "contrast > 88"


def test_switching_the_comparison_writes_the_model(qapp):
    from PySide6.QtWidgets import QComboBox

    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    opbox = next(c for c in panel.findChildren(QComboBox)
                 if c.currentText() == "greater than")
    i = opbox.findData("<=")
    opbox.setCurrentIndex(i)
    opbox.activated.emit(i)
    assert m.tree_node("").when == "contrast <= 100"


def test_a_compound_condition_falls_back_to_the_expression_box(qapp):
    """複合條件拆不成三格 —— 誠實地給算式框，不要猜。"""
    m = _model_with_tree()
    m.set_tree_when("", "(contrast > 5) * (glv_mad < 2)")
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    assert any(e.text() == "(contrast > 5) * (glv_mad < 2)"
               for e in panel.findChildren(QLineEdit))


def test_the_live_count_says_how_many_reach_here_and_say_yes(qapp):
    """「一邊拖一邊看」的那個回饋 —— 沒跑過就一個數字都不畫（F18）。

    ⚠ 這一條驗的**事實沒變、形狀變了**（草案 2，2026-08-24）：以前是一行字
    「2 of the 4 defects that reach here say yes」，現在是一條**寬度就是顆數**
    的分流條 —— 同一個問題，但掃一眼就知道這一刀切得均不均。
    """
    from d4t.ui.threshold_view import SplitBar

    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    assert not [b for b in panel.findChildren(SplitBar) if not b.isHidden()], \
        "沒跑過卻畫了一條分流條"

    rows = [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {"contrast": float(v), "a": float(v) / 2}}
            for i, v in enumerate((10.0, 50.0, 150.0, 300.0))]
    panel.set_rows(rows)
    panel.show_path("")
    bars = [b for b in panel.findChildren(SplitBar) if not b.isHidden()]
    assert len(bars) == 1, bars
    # contrast > 100 → 150 與 300 兩顆
    assert bars[0].counts() == (2, 2), bars[0].counts()


def test_a_new_step_arrives_with_a_question_that_asks_something(qapp):
    """F25：加一步不要丟一格空白給使用者 —— 挑這一批分得最開的數字。"""
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    rows = [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {"contrast": float(v), "flat": 1.0}}
            for i, v in enumerate((1.0, 20.0, 60.0, 900.0))]
    panel.set_rows(rows)
    panel.show_path("y")
    panel._split("y")                      # ＝ 按了 Split…
    node = m.tree_node("y")
    assert node.when, "新的一步是空白的 —— 使用者又被丟回原點"
    assert node.when.startswith("contrast"), node.when
    assert "flat" not in node.when         # 完全分不開的數字不會被挑中


# ⚠ **THIS BATCH 那一段現在只在葉子上**（草案 2／3，2026-08-24）。一個步驟
# 上它講的三件事都有更好的位置了：「幾顆流到這裡」在最上面的麵包屑、「切成
# 幾比幾」是分流條的寬度、兩邊各幾顆寫在 Yes／No 的標籤上 —— 留著就是同一個
# 事實在一個 550px 的面板裡講三次。葉子沒有「切成兩邊」，「20 land here」是
# 它唯一的批次數字，所以那裡留著，而下面兩條就指著那裡。
def test_no_batch_line_before_a_run(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_counts(None)
    panel.show_path("y")                   # ← 葉子
    assert not any("land here" in t for t in _texts(panel))


def test_the_batch_line_reads_the_flow_counts(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_counts({"": 47, "y": 11, "n": 36})
    panel.show_path("y")                   # ← 葉子
    assert any("11" in t and "land here" in t for t in _texts(panel)), \
        _texts(panel)


def test_a_step_says_the_flow_counts_without_a_batch_line(qapp):
    """步驟那一邊的**同一份數字**：麵包屑一個、Yes／No 標籤各一個。

    這一條接住上面兩條讓出來的地盤 —— 拿掉 THIS BATCH 不等於拿掉顆數。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_counts({"": 47, "y": 11, "n": 36})
    panel.show_path("")
    texts = _texts(panel)
    assert any("47 defects reach here" in t for t in texts), texts
    assert "Yes 11" in texts and "No 36" in texts, texts


def test_a_leaf_panel_edits_the_class(qapp):
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("y")
    edit = next(e for e in panel.findChildren(QLineEdit)
                if e.text() == "big")
    edit.textEdited.emit("huge")
    assert m.tree_node("y").label == "huge"
    spin = panel.findChildren(QSpinBox)[0]
    spin.valueChanged.emit(7)
    assert m.tree_node("y").bin == 7


def test_converting_a_threshold_recipe_keeps_every_verdict():
    """F25：舊 recipe 一打開就變成樹 —— **判定不能因此改變**。

    用值網格逐點比（同 F24 ① 證明 `rules_to_tree` 無損的那一套）：同一個
    分數表達式，走老路（score + threshold）與走轉出來的樹，score 與 bin
    逐點相同。這是「自動遷移」敢做的唯一理由。
    """
    from d4t.core.pipeline import Context, Recipe, ScoreSpec
    from d4t.core.pipeline.engine import _eval_score

    base = Recipe(recipe_id="t", routes={"ebi_patch": []}, nodes={},
                  score=ScoreSpec(expr="glv_max - 2", threshold=3.0,
                                  bins={"below": 0, "above": 1}))
    m = RecipeModel.from_recipe(base, kind="ebi_patch")
    m.use_decide(True)
    m.ensure_tree()
    converted = m.to_recipe()
    assert converted.decide is not None and converted.decide.tree is not None

    for v in (-10.0, 0.0, 4.9, 5.0, 5.1, 100.0):
        old_ctx, new_ctx = Context(), Context()
        old_ctx.features["glv_max"] = v
        new_ctx.features["glv_max"] = v
        assert _eval_score(base, old_ctx) == _eval_score(converted, new_ctx), v


# --------------------------------------------------------------------------- #
# 導引式問題的數字範圍（A1，2026-08-24）
# --------------------------------------------------------------------------- #
def _spin(panel):
    from PySide6.QtWidgets import QDoubleSpinBox
    spins = panel.findChildren(QDoubleSpinBox)
    assert spins, "面板上沒有數字框"
    return spins[0]


def _plots(panel):
    """畫出來的分布圖（草案 1 之後取代滑桿的那個東西）。

    ⚠ 用 ``isHidden()`` 不是 ``isVisible()``：這些面板從來沒有 ``show()``
    過，那時候每一個子元件的 ``isVisible()`` 都是 ``False`` —— 底下兩條會
    **兩條都通過**，而其中一條根本沒有在驗東西。
    """
    from d4t.ui.threshold_view import ThresholdHistogram
    return [w for w in panel.findChildren(ThresholdHistogram)
            if not w.isHidden()]


def test_the_threshold_box_accepts_a_number_bigger_than_one(qapp):
    """**使用者回報的那一條：「搖桿只能填最大 1」。**

    還沒試跑的時候沒有分布，而舊的 `_range_for` 會憑空編一個範圍
    （``value ± max(|value|, 1)``）。剛加進來的一步 ``value`` 是 0，
    所以那個範圍是 **−1 … 1** —— 而**數字框跟滑桿共用同一組上下界**，
    於是想問「大於 6.5」的人，那個 6.5 打不進去。

    門檻的合理範圍隨著卡片天差地遠（灰階 0–255、CD 幾個 px、面積上萬 px²、
    z 分數是負的、百分位 0–100），沒有一個通用的上下界 —— 所以數字框不夾人。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")                    # 沒有 set_rows ＝ 還沒試跑

    spin = _spin(panel)
    for want in (6.5, 255.0, 16384.0, -12.5):
        spin.setValue(want)
        assert spin.value() == want, (
            "打 %r 之後變成 %r —— 數字框把它夾掉了" % (want, spin.value()))
    assert m.tree_node("").when.endswith("-12.5"), m.tree_node("").when


def test_no_plot_before_a_run_but_it_says_why(qapp):
    """門檻的那個把手要跨的是**這一批真的量到什麼**。沒有那份資料時它跨不出
    東西來 —— 生一個跨著憑空範圍的控制項，等於讓它說一件不成立的話。

    但**安靜地少一個控制項比沒有用的控制項更難懂**，所以那句話要說出來，
    而且要指向拿得回它的動作。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")

    assert not _plots(panel), "沒有資料卻畫了一張分布圖"
    assert any("Run a trial" in t for t in _texts(panel)), _texts(panel)


def test_the_plot_comes_back_once_there_is_a_distribution(qapp):
    """有分布就該畫出來 —— 那是 F25「問題不用打的」的主角（草案 1 把它從
    一根沒有刻度的滑桿換成一張看得到形狀的分布圖）。"""
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_rows([{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
                     "features": {"contrast": float(v)}}
                    for i, v in enumerate((10.0, 50.0, 150.0, 300.0))])
    panel.show_path("")

    assert _plots(panel), "有分布卻沒有畫出來"
    assert not any("Run a trial" in t for t in _texts(panel))


def test_the_box_still_takes_a_threshold_outside_what_the_batch_measured(qapp):
    """滑桿跨觀測範圍是對的；**數字框跟著夾就不對**。

    「大於 500」在這一批最大只有 300 的時候仍然是一條完全合法的規則 ——
    那正是怎麼寫一條今天抓不到、明天出事才抓得到的規則。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_rows([{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
                     "features": {"contrast": float(v)}}
                    for i, v in enumerate((10.0, 50.0, 150.0, 300.0))])
    panel.show_path("")

    spin = _spin(panel)
    spin.setValue(500.0)
    assert spin.value() == 500.0
    assert m.tree_node("").when == "contrast > 500"


def test_one_measured_value_is_better_than_an_invented_range(qapp):
    """整批只有一顆、或那個數字每顆都一樣的時候，**資料還是在手上**。

    舊的寫法把它丟掉，退回 ``value ± 1`` 的憑空範圍 —— 於是量到的是 6.5，
    而滑桿跨的是 −1…1。改成以那個量到的值為中心撐開。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.set_rows([{"defect_id": "1", "ok": True, "bin": 0, "score": 0.0,
                     "features": {"contrast": 6.5}}])
    panel.show_path("")

    rng = panel._slider_range("contrast", 0.0)
    assert rng is not None, "有一個量到的值卻說沒有範圍"
    assert rng[1] >= 6.5, "範圍 %r 跨不到量到的 6.5" % (rng,)


def test_the_slider_range_is_none_only_when_there_is_nothing_to_go_on(qapp):
    """`_slider_range` 的契約：**回 None ＝ 真的沒有資料**。

    這一條顧的是上面那幾條的前提 —— 如果它變成「幾乎都回 None」，
    「有分布就有滑桿」那條會安靜地永遠成立。
    """
    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("")
    assert panel._slider_range("contrast", 0.0) is None

    panel.set_rows([{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
                     "features": {"contrast": float(v)}}
                    for i, v in enumerate((10.0, 50.0))])
    panel.show_path("")
    assert panel._slider_range("contrast", 0.0) is not None


def test_the_bin_box_takes_a_real_fab_class_code(qapp):
    """**跟 A1 同一個形狀：一個我們自己發明的上限。**

    四個 bin 數字框以前都寫死 ``setRange(0, 999)``，而**引擎與 KLARF 寫回都
    沒有這個上限**（``CLASSNUMBER`` 就是一個整數欄）。廠內的分類碼四五位數
    很常見 —— 打 1200 進去會安靜地變成 999，而寫回是不可逆的。
    """
    from PySide6.QtWidgets import QSpinBox

    m = _model_with_tree()
    panel = TreePanel()
    panel.set_model(m)
    panel.show_path("y")                   # 一片葉子 → 有 bin 的數字框

    spin = next(s for s in panel.findChildren(QSpinBox) if s.prefix() == "bin ")
    spin.setValue(1200)
    assert spin.value() == 1200, "1200 被夾成 %d" % spin.value()
    assert m.tree_node("y").bin == 1200


def test_running_out_of_bin_numbers_does_not_raise(qapp, monkeypatch):
    """`_fresh_bin` 用光了要**回一個數字**，不是漏出 ``StopIteration``。

    它被一顆按鈕（Split）直接呼叫，所以那個例外會冒到 Qt 的事件迴圈裡。

    真的用光 999999 個 bin 沒辦法在測試裡湊出來，所以把上限暫時壓到 3 —— 驗的
    是**那條路本身**（``next(..., 預設值)`` 而不是 ``next(...)``），
    不是那個數字。
    """
    from d4t.ui import viewmodel as vm

    monkeypatch.setattr(vm, "MAX_BIN", 3)
    m = _model_with_tree()
    # 樹裡已經有 bin 3 / 2 / 0，再把 1 也用掉 → 1..3 全滿
    m.set_tree_leaf("nn", bin=1)
    assert sorted(_all_bins(m.decide.tree)) == [1, 2, 3]

    assert m._fresh_bin() == 3, "用光了應該回上限，而不是拋例外"


def _all_bins(node):
    from d4t.core.pipeline.recipe import TreeLeaf
    if isinstance(node, TreeLeaf):
        return [int(node.bin)]
    return _all_bins(node.yes) + _all_bins(node.no)
