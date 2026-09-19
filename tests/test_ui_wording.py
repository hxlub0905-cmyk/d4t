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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402  —— 觸發卡片註冊
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
