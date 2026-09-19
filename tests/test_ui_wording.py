# F118：使用者面的字（2026-09-19）。
"""`d4t/ui/wording.py` —— **訊息裡不准出現開發者的字**。

走查（F117 J1／I11／J5／J6）在畫面上抓到四種內部識別碼：node id（``dn``）、
step key（``[glv_stats]``）、參數名（``'source'``）、以及 Python 的 list repr
（``['glv_max']``）。這一支守的是前三種的翻譯，以及第四種的排版。

⚠ **翻譯有邊界**：卡片名與欄位 label 要翻（它們本來就是「給人看的字」），
**feature 名與 step key 不翻** —— 它們是 recipe 的鍵，使用者在分數表達式裡
就是那樣打的。把 `glv_max` 翻掉會讓畫面上的字跟他要打的字對不起來。

本模組 Qt-free，所以這支測試不需要 QApplication。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402  —— 觸發卡片註冊
from d4t.core.pipeline.recipe import Issue  # noqa: E402
from d4t.core.pipeline.step import StepError  # noqa: E402
from d4t.ui import wording  # noqa: E402


class _Node:
    def __init__(self, step):
        self.step = step


class _Model:
    def __init__(self, **nodes):
        self.nodes = {k: _Node(v) for k, v in nodes.items()}


class _Trace:
    def __init__(self, node_id, step_key, error):
        self.node_id, self.step_key, self.error = node_id, step_key, error


# --------------------------------------------------------------------------- #
# 1. 名字：node id / step key / 參數名 → 畫面上的字
# --------------------------------------------------------------------------- #
def test_a_node_id_becomes_the_card_name():
    """``Removed “dn”`` 是 node **id** —— 那是自動產的，不是使用者取的名字。"""
    m = _Model(dn="denoise", glv="glv_stats")
    assert wording.card(m, "dn") == "Denoise"
    assert wording.card(m, "glv") == "GLV"


def test_an_unknown_name_is_returned_as_it_is():
    """認不得就原樣回去 —— **不要猜**。

    舊 recipe 開在新版上就會這樣（那張卡已經刪了），而那個 key 本身正是使用者
    要看到的線索。回一個猜出來的漂亮名字會把線索蓋掉。
    """
    m = _Model(dn="denoise")
    assert wording.card(m, "nope") == "nope"          # 不在 model 裡
    assert wording.card_of_step("no_such_step") == "no_such_step"
    assert wording.card(m, "") == ""


def test_a_param_name_becomes_the_field_label():
    """``'source' is empty`` —— 那一格上面寫的是「Measure on」。"""
    assert wording.field("glv_stats", "source") == "Measure on"
    assert wording.field("glv_stats", "no_such_param") == "no_such_param"


def test_feature_names_are_not_translated():
    """⚠ **邊界**：feature 名是 recipe 的鍵，不是給人看的字。

    使用者在分數表達式裡打的就是 `glv_max`。`name_list` 只負責**排版**，
    一個字母都不准改。
    """
    assert "glv_max" in wording.name_list(["glv_max"])


# --------------------------------------------------------------------------- #
# 2. 一串名字：不是 Python 的 list repr
# --------------------------------------------------------------------------- #
def test_a_list_of_names_reads_like_a_sentence():
    assert wording.name_list([]) == ""
    assert wording.name_list(["a"]) == "“a”"
    assert wording.name_list(["a", "b"]) == "“a” and “b”"
    assert wording.name_list(["a", "b", "c"]) == "“a”, “b” and “c”"
    for text in (wording.name_list(["a"]), wording.name_list(["a", "b"])):
        assert "[" not in text and "'" not in text


def test_a_long_list_is_cut_short_and_says_how_many_are_left():
    """走查看到的那一句把**整條 route 的每一個 feature** 都列出來（二十幾個）。

    使用者要找的是「我打錯的那個字最接近哪一個」，不是一份清單 ——
    清單有它的地方（Features 面板），錯誤訊息不是。
    """
    text = wording.name_list(list("abcdefg"), limit=4)
    assert text == "“a”, “b”, “c”, “d” and 3 more"
    assert "e" not in text.replace("more", "")


# --------------------------------------------------------------------------- #
# 3. 錯誤訊息：結構本來就在，只是沒有人用
# --------------------------------------------------------------------------- #
def test_a_step_error_already_carries_the_structure():
    """⚠ 這一條釘的是 F118 §2 的發現：**`StepError` 一直帶著結構**。

    `step_key` 與一份不含 ``[key]`` 前綴的 `detail` 從一開始就在，而它的說明
    寫著「那句話是給使用者看的」—— 畫面上那個前綴是 `str(e)` 來的。
    這一條會在有人把 `detail` 拿掉的那天紅。
    """
    e = StepError("glv_stats", "no input connected")
    assert e.step_key == "glv_stats"
    assert e.detail == "no input connected"
    assert str(e).startswith("[glv_stats] ")           # log 那一份還在
    assert wording.step_error_text(e) == "“GLV”: no input connected"


def test_the_trace_prefix_is_removed_by_matching_not_by_guessing():
    """``[glv_stats] …`` → ``“GLV”: …``。

    engine 存的是 `str(e)`，所以畫面拿到的那句話已經帶著前綴。拿掉它靠的是
    **比對已知的前綴**（``"[%s] " % step_key``），不是對散文做正則 ——
    F118 §3 明著否決了那條路，因為它失效的時候是**安靜的**。
    """
    m = _Model(g="glv_stats")
    tr = _Trace("g", "glv_stats", "[glv_stats] no input connected")
    assert wording.trace_error_text(tr, m) == "“GLV”: no input connected"

    # 對不上就原樣留著（訊息不是 StepError 來的，或前綴換過寫法）
    other = _Trace("g", "glv_stats", "something else entirely")
    assert wording.trace_error_text(other, m) == "“GLV”: something else entirely"
    assert wording.trace_error_text(_Trace("g", "glv_stats", "")) == ""


def test_the_card_name_wins_over_the_step_key():
    """同一張卡可以放兩次 —— **node id 才分得出是哪一張**。"""
    m = _Model(first="denoise", second="denoise")
    tr = _Trace("second", "denoise", "[denoise] boom")
    assert wording.trace_error_text(tr, m) == "“Denoise”: boom"
    # 沒有 model 就退回 step key 的 label（總比印 key 好）
    assert wording.trace_error_text(tr) == "“Denoise”: boom"


# --------------------------------------------------------------------------- #
# 4. 沒有一個對外的名字會漏掉內部識別碼
# --------------------------------------------------------------------------- #
def test_nothing_it_returns_looks_like_an_internal_id():
    """整支的驗收：**吐出去的字裡不准有 `[` `]` `'` 這種形狀。**"""
    m = _Model(dn="denoise")
    tr = _Trace("dn", "denoise", "[denoise] it failed")
    for text in (wording.card(m, "dn"),
                 wording.card_of_step("glv_stats"),
                 wording.field("glv_stats", "source"),
                 wording.name_list(["a", "b", "c"]),
                 wording.trace_error_text(tr, m)):
        assert "[" not in text and "]" not in text, text


# --------------------------------------------------------------------------- #
# 5. 每一條 lint 都給得出一句話（F118 §5 的便利貼）
# --------------------------------------------------------------------------- #
#: 48 條 lint 的產地。**一條一條搬**（F118 §4 第 3／5 步），所以這一節守的是
#: 「搬到一半」那段日子：沒搬到的那些**必須原樣**，而不是安靜地變成空字串。
RECIPE_PY = Path(__file__).resolve().parent.parent / "d4t/core/pipeline/recipe.py"


def _issue_calls():
    """`recipe.py` 裡每一個 ``Issue(...)`` → ``({code: 行號}, 轉手的, 認不出的)``。

    **轉手的**是 ``code=str(code)`` 那種：那一條 lint 的內容來自卡片
    （`Step.kind_issues`），`recipe.py` 只是把它包成 `Issue`。它照樣走這裡的
    `issue_line()`，只是名冊數不到 —— 所以要數得出**有幾個**這種地方。
    """
    tree = ast.parse(RECIPE_PY.read_text(encoding="utf-8"))
    codes, relays, unnamed = {}, [], []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "Issue"):
            continue
        code = {k.arg: k.value for k in node.keywords}.get("code")
        if isinstance(code, ast.Constant) and isinstance(code.value, str):
            codes.setdefault(code.value, node.lineno)
        elif (isinstance(code, ast.Call) and getattr(code.func, "id", "") == "str"
                and len(code.args) == 1 and isinstance(code.args[0], ast.Name)):
            relays.append(node.lineno)
        else:
            unnamed.append(node.lineno)
    return codes, relays, unnamed


def test_every_lint_has_a_code_you_can_read_off_the_source():
    """``code`` 一律是字面值 —— **不然沒有人數得出還剩幾條沒搬**。

    唯一的例外是**一個**轉手的地方（`Step.kind_issues`：「這組設定對不對」
    有時取決於那顆 defect 拿到的是 patch 還是一張大圖，所以判準在卡片上）。
    ⚠ 那個數字寫死成 1 是故意的：第二個轉手的地方出現時，名冊會**安靜地**
    少掉一批 code，而這一條會在那一天紅。
    """
    codes, relays, unnamed = _issue_calls()
    assert not unnamed, "Issue(code=…) 不是字面值，行號：%s" % unnamed
    assert len(relays) == 1, "轉手 kind_issues 的地方變成 %d 個：%s" % (
        len(relays), relays)
    assert len(codes) > 30, codes          # 48 個產地、去重後的 code 數
    for code in codes:
        assert code and code == code.strip().lower(), code


def test_every_lint_still_gets_a_sentence():
    """**每一個 `code` 都給得出一句話**，而沒填結構化欄位的那句正好是 `detail`。

    ⚠ 這是 F118 §5 那張便利貼：第 3／5 步是一條一條搬的，而「搬到一半」會
    持續好幾輪。沒有這一條的話，某一天有人把 `detail` 從一個還沒搬的產地拿
    掉，畫面上那一列就變成空白 —— **而空白不會讓任何測試紅**。
    """
    codes = _issue_calls()[0]
    m = _Model(dn="denoise")
    for code, lineno in sorted(codes.items()):
        issue = Issue(code=code, level="warning", node_id="dn",
                      title="something is off", detail="the long explanation")
        assert wording.issue_line(issue, m) == "the long explanation",             "%s（recipe.py:%d）" % (code, lineno)
        assert wording.issue_line(issue) == "the long explanation"
        # `detail` 是空的那幾條（有，而且合理：結論本身就是全部）退回 `title`
        # —— **不准回空字串**：清單上一列空白比沒有那一列更糟。
        bare = Issue(code=code, level="warning", node_id="dn",
                     title="something is off", detail="")
        assert wording.issue_line(bare, m) == "something is off", code


def test_a_migrated_lint_says_where_and_still_says_why():
    """搬過的那幾條：**多了「去哪一張卡的哪一格」，而原來那句話還在**。

    那不是裝飾 —— 走查（J1）數到的第四個問題就是「沒有一個字告訴他去哪一張
    卡改」。而 `detail` 留著是因為它回答的是另一個問題（為什麼這樣算錯）。
    """
    m = _Model(g="glv_stats")
    issue = Issue(code="unknown-feature", level="warning", node_id="g",
                  title="the score uses a name nobody writes",
                  detail="fix the name or add a card that writes it",
                  param="source", names=("nosuch_feature",),
                  suggest=("glv_max", "glv_min"))
    line = wording.issue_line(issue, m)
    assert "GLV" in line and "Measure on" in line      # 去哪裡改
    assert "nosuch_feature" in line                    # 打錯的是哪個字
    assert "glv_max" in line and "glv_min" in line     # 是不是要打這個
    assert "fix the name" in line                      # 原來那句還在
    assert "[" not in line and "']" not in line        # 不是 list repr


def test_the_route_is_only_mentioned_when_there_is_more_than_one():
    """``route 'ebi_patch'`` —— **單 route 的 recipe 上那個字純粹是雜訊**。

    而「這份 recipe 有幾條 route」只有畫面答得出來，所以判斷住在 UI 這一側。
    """
    class _R(_Model):
        def __init__(self, n, **nodes):
            super().__init__(**nodes)
            self.routes = {"r%d" % i: [] for i in range(n)}

    issue = Issue(code="unknown-feature", level="warning", node_id="g",
                  title="t", detail="d", names=("x",), route="ebi_patch")
    assert "ebi_patch" not in wording.issue_line(issue, _R(1, g="glv_stats"))
    assert "ebi_patch" in wording.issue_line(issue, _R(2, g="glv_stats"))
