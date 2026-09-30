# F119：哪一個 bin 是好消息（2026-09-20）。
"""判定膠囊的紅綠以前是**看 bin 的號碼**決定的，而號碼本身沒有意義。

2026-09-20 量到的：三份出貨的 recipe **全部反了** —— ``nothing stands out``
（沒找到缺陷＝好消息）是紅的、``a spot stands out``（找到了）是綠的。走查
（F117 D2）只抓到均勻度那一條，因為那一條的字跟顏色矛盾得最刺眼。

這一支守 core 那一半：**意義存得下來，而且存它不會弄壞任何舊檔案。**
畫面那一半在 `tests/test_ui_verdict_wording.py`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from d4t.core.pipeline.recipe import (  # noqa: E402
    OUTCOMES, RECIPE_VERSION, DecideSpec, Recipe, Rule, ScoreSpec,
    TreeLeaf, TreeStep,
)


def _tree(a_out: str = "", b_out: str = "") -> TreeStep:
    return TreeStep(when="x > 1",
                    yes=TreeLeaf(bin=1, label="found", outcome=a_out),
                    no=TreeLeaf(bin=0, label="clean", outcome=b_out))


# --------------------------------------------------------------------------- #
# 1. 存得下來，而且沒標的檔案一個位元組都沒變
# --------------------------------------------------------------------------- #
def test_an_unmarked_recipe_writes_exactly_what_it_used_to():
    """⚠ **這一條就是「不必遷移」那句話的證據**（F119 §3.3）。

    `outcome` 是新加的、預設 ``""``，而 ``""`` 對舊檔案與新 recipe 的意思完全
    相同（都是「還沒說」）。所以它**有才寫** —— 一份沒標的 recipe（＝每一份
    F119 之前的檔案）存出來跟以前逐位元組相同，`RECIPE_VERSION` 也不必動。
    """
    # F119 沒有動版本號（它沒有遷移）；之後第 6 版是 F123 期 1 的 Decision 卡、
    # 第 7 版是 F123 期 2 的數字線與結果線、第 8 版是 F124 的「只有量測卡送得
    # 進判定」。
    assert RECIPE_VERSION == 8
    r = Recipe(recipe_id="t", routes={"ebi_patch": []}, nodes={}, edges=[],
               score=ScoreSpec(expr="", threshold=0.0, bins={}),
               decide=DecideSpec(tree=_tree(),
                                 rules=[Rule(when="a", bin=3, label="n")]))
    out = json.dumps(r.to_json_dict())
    assert "outcome" not in out, out
    assert Recipe.from_json_dict(r.to_json_dict()).to_json_dict()         == r.to_json_dict()


def test_every_shipped_recipe_says_which_of_its_bins_is_good_news():
    """**出貨的 recipe 一片葉子都不准沒標**（F119 第 3 步）。

    這一條會在有人加第四份 recipe 而忘了標的那天紅 —— 而忘了標的下場不是
    崩潰，是**膠囊變成灰的**，那種退步沒有人會在測試以外發現。

    ⚠ 順便釘住那份對照表本身：``nothing stands out`` 是**好消息**。走查
    （F117 D2）之前它是紅的 —— 三份全反，而沒有人發現，因為「找到缺陷 = 綠」
    看起來像在慶祝。
    """
    expected = {
        "nothing to measure": "neutral",
        "nothing stands out": "good",
        "measured": "good",
        "a spot stands out": "bad",
        "one box stands out": "bad",
        "more than one box is off": "bad",
    }
    seen = set()
    for path in sorted((REPO / "recipes").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        decide = Recipe.from_json_dict(raw).decide
        assert decide is not None, "%s 沒有判定段" % path.name
        labels, outcomes = decide.bin_labels(), decide.bin_outcomes()
        assert labels, path.name
        for b, name in labels.items():
            assert outcomes.get(b),                 "%s 的 bin %d（%s）沒說是好消息還是壞消息" % (path.name, b, name)
            assert outcomes[b] == expected[name], (path.name, name)
            seen.add(name)
    assert seen == set(expected), "對照表跟出貨的 recipe 對不上：%s" % (
        set(expected) ^ seen)


def test_a_marked_recipe_survives_a_round_trip():
    """``to_json_dict → from_json_dict`` 要是 identity（鐵則 9 的那條路）。

    它是 `run_batch` 送 recipe 進 worker 的路 —— 一旦不是 identity，
    ``workers=1`` 與 ``workers=2`` 就會算出不同的東西。
    """
    for decide in (
        DecideSpec(tree=_tree("bad", "good")),
        DecideSpec(rules=[Rule(when="a > 1", bin=2, label="n",
                               outcome="neutral")],
                   otherwise_bin=0, otherwise_label="o",
                   otherwise_outcome="good"),
    ):
        r = Recipe(recipe_id="t", routes={"ebi_patch": []}, nodes={},
                   edges=[], decide=decide,
                   score=ScoreSpec(expr="", threshold=0.0, bins={}))
        d = r.to_json_dict()
        assert d == Recipe.from_json_dict(d).to_json_dict()
        assert Recipe.from_json_dict(d).decide.bin_outcomes() \
            == decide.bin_outcomes()


# --------------------------------------------------------------------------- #
# 2. bin_outcomes()：判準跟 bin_labels() 逐字相同
# --------------------------------------------------------------------------- #
def test_the_first_one_wins_just_like_the_names_do():
    """同一個 bin 被標兩次 —— **由上往下讀，第一個贏**（同 `bin_labels`）。

    兩支的判準要一樣，不然畫面上那一格的字與它的顏色會來自不同的葉子。
    """
    d = DecideSpec(rules=[Rule(when="a", bin=1, label="first", outcome="good"),
                          Rule(when="b", bin=1, label="second",
                               outcome="bad")])
    assert d.bin_outcomes() == {1: "good"}
    assert d.bin_labels() == {1: "first"}


def test_nothing_marked_means_nothing_in_the_table():
    """**沒標的不在裡面** —— 「還沒說」不是一個值，是查不到。

    畫面靠這件事分辨「還沒說」（要講一句話）與「說了是中性」（不必）。
    """
    assert DecideSpec(tree=_tree()).bin_outcomes() == {}
    assert DecideSpec(tree=_tree("", "neutral")).bin_outcomes() == {0: "neutral"}


def test_a_value_nobody_recognises_is_treated_as_unmarked():
    """打錯的 ``"gud"`` 不該變成一個猜出來的顏色。

    「為什麼沒生效」留得下來 —— `validate` 的 `unknown-outcome` 會講
    （卡片自動做的每一個決定都要留得下來，CLAUDE.md §3 的同一條）。
    """
    d = DecideSpec(tree=TreeStep(when="x", yes=TreeLeaf(bin=1, outcome="gud"),
                                 no=TreeLeaf(bin=0, outcome="good")))
    assert d.bin_outcomes() == {0: "good"}


def test_the_vocabulary_is_the_one_the_theme_already_uses():
    """三個名字跟 `ui/theme.TOKENS` 的 ``chip_*`` **一比一**。

    中間放一張翻譯表的話，那張表遲早會漂（這個 repo 記過三次）。
    ⚠ ``""`` 也在表裡，而它的意思是「還沒說」，不是「中性」。
    """
    assert OUTCOMES == ("", "good", "bad", "neutral")
    tokens = (REPO / "d4t" / "ui" / "theme.py").read_text(encoding="utf-8")
    for name in OUTCOMES[1:]:
        assert '"chip_%s_bg"' % name in tokens, name


# --------------------------------------------------------------------------- #
# 3. 標錯／標不一致要講出來（第 5 步）
# --------------------------------------------------------------------------- #
def _codes(decide):
    from d4t.core.pipeline.recipe import validate
    r = Recipe(recipe_id="t", routes={"ebi_patch": []}, nodes={}, edges=[],
               score=ScoreSpec(expr="", threshold=0.0, bins={}), decide=decide)
    return [i for i in validate(r)
            if i.code in ("unknown-outcome", "conflicting-outcome")]


def test_not_answering_is_not_a_lint():
    """⚠ **這一條擋的是「每一份都多兩行不痛不癢的話」。**

    一份每個舊 recipe 都會亮的訊息會被學會忽略，而真的那一條也跟著被忽略
    —— `test_the_reference_recipes_stay_completely_clean` 鎖的正是「一條都
    沒有」，而那些參考檔案就是沒標的。「還沒說」講在它該講的地方：判定樹
    的托盤上，就在那一排膠囊旁邊。
    """
    assert _codes(DecideSpec(tree=_tree())) == []


def test_a_word_nobody_understands_gets_a_did_you_mean():
    """打錯的字**安靜地不生效** —— 沒有這一條的話沒有人會發現。"""
    got = _codes(DecideSpec(tree=_tree("gud", "good")))
    assert [i.code for i in got] == ["unknown-outcome"]
    assert got[0].level == "warning"
    assert got[0].names == ("gud",)
    assert "good" in got[0].suggest, got[0].suggest
    assert "no colour" in got[0].advice


def test_two_classes_that_disagree_say_which_one_wins():
    """同一個 bin 標成一好一壞 —— **第一個贏**，所以要講出贏的是哪一個。

    不講的話使用者去改後面那一片，畫面上一點反應都沒有。
    """
    d = DecideSpec(tree=TreeStep(
        when="x > 1",
        yes=TreeLeaf(bin=0, label="clean", outcome="good"),
        no=TreeStep(when="y > 2",
                    yes=TreeLeaf(bin=0, label="also clean", outcome="bad"),
                    no=TreeLeaf(bin=1, label="found", outcome="bad"))))
    got = _codes(d)
    assert [i.code for i in got] == ["conflicting-outcome"]
    assert "clean" in got[0].advice and "also clean" in got[0].advice
    assert "The first one wins" in got[0].advice
    assert d.bin_outcomes()[0] == "good", "講的跟畫面上真的用的要是同一個"
    # 同一個答案標兩次不是衝突（那只是寫了兩遍，沒有歧義）。
    same = DecideSpec(tree=TreeStep(
        when="x > 1",
        yes=TreeLeaf(bin=0, label="a", outcome="good"),
        no=TreeLeaf(bin=0, label="b", outcome="good")))
    assert _codes(same) == []


def test_the_new_lints_hang_on_the_decision_not_on_a_card():
    """它們沒有 `node_id`（判定不是一張卡），所以判定的徽章要認得它們。"""
    from d4t.core.pipeline.recipe import DECISION_ISSUE_CODES
    for code in ("unknown-outcome", "conflicting-outcome"):
        assert code in DECISION_ISSUE_CODES, code
    for issue in _codes(DecideSpec(tree=_tree("gud", ""))):
        assert issue.node_id is None


# --------------------------------------------------------------------------- #
# 4. 一支走訪，不是三支
# --------------------------------------------------------------------------- #
def test_the_names_and_the_outcomes_are_read_in_the_same_order():
    """⚠ `bin_labels` / `bin_outcomes` / 兩條 lint **走同一支** `entries()`。

    各走一次的那天，它們對「哪一片葉子排在前面」會有四個答案 —— 而「第一個
    贏」整條規則就是靠那個順序。這一條問的是那件事還成立。
    """
    d = DecideSpec(tree=TreeStep(
        when="x > 1",
        yes=TreeLeaf(bin=1, label="first", outcome="bad"),
        no=TreeLeaf(bin=1, label="second", outcome="good")))
    # ⚠ 尾巴那一筆是 `otherwise`，**走樹的時候它用不到** —— 但它照樣在清單
    # 裡，而那是刻意的：`bin_labels` 在 F119 之前就是這樣走的，而它靠「空的
    # 就不算」把它濾掉。這一支不過濾（判準住在呼叫端），所以這裡看得到它。
    assert d.entries() == [(1, "first", "bad"), (1, "second", "good"),
                           (0, "", "")]
    assert d.bin_labels()[1] == "first" and d.bin_outcomes()[1] == "bad"


# --------------------------------------------------------------------------- #
# F122：規則轉成樹時，好消息／壞消息跟著過去
# --------------------------------------------------------------------------- #
def test_turning_rules_into_a_tree_keeps_every_outcome():
    """Studio 第一次點一份手寫的規則 recipe 就把它轉成樹（`ensure_tree`）；
    以前那一刻每一條規則的 outcome 安靜地消失，存檔就寫回磁碟。"""
    from d4t.core.pipeline.recipe import rules_to_tree

    spec = DecideSpec(rules=[Rule(when="x > 5", bin=2, label="big",
                                  outcome="bad"),
                             Rule(when="x > 1", bin=1, label="small",
                                  outcome="neutral")],
                      otherwise_bin=0, otherwise_label="clean",
                      otherwise_outcome="good")
    before = spec.bin_outcomes()
    after = DecideSpec(tree=rules_to_tree(spec)).bin_outcomes()
    assert before == after == {2: "bad", 1: "neutral", 0: "good"}
