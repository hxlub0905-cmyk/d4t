# U10：產品範圍收斂成 profile — authored 2026-09-08.
"""**那幾個旗標已經開始互相牽扯，而「一起設對」沒有任何東西在守。**

實例（F91 X4 那一輪付過的錢）：`SHOW_SAMPLE_ENTRIES` 一個旗標管兩個入口，
而它們的**死法不一樣** —— 範本庫的理由到期了，範例資料那條仍然是死路。合在
一起的下場是「打開其中一個順手把另一個也放回畫面上」，而那顆鈕按下去會撞牆
（推廣鐵則：按了撞牆的鈕比沒有那顆鈕更糟）。拆開之後又多了一個問題：三個旗標
要一起設對。

profile 把「這台機器要看到什麼」變成一句話。這一份守的是那句話真的算數。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from d4t.ui import scope                     # noqa: E402 — 不 import Qt


@pytest.fixture(autouse=True)
def _restore_profile():
    """**測試不准把 profile 留給下一支測試。**

    它是模組層的狀態，而模組在一個行程裡只 import 一次 —— 忘了還原的話，
    後面每一支測試看到的是這一支設的那一組，而失敗會出現在別的檔案上。
    """
    before = scope.current_profile()
    yield
    scope.use_profile(before)


#: 每一組 profile 都要設的那幾個旗標。**這一份是唯一的清單** ——
#: 底下三條測試都讀它，而 `test_the_flags_a_profile_names_are_real`
#: 反過來守它跟 `scope.PROFILES` 對得起來。
_FLAGS = ("SHOW_TEMPLATE_LIBRARY", "SHOW_SAMPLE_DATA", "SHOW_ROUTE_BY",
          "HIDDEN_STEPS")


def test_the_default_is_the_fab_machine():
    """目標使用者是廠內那台機器上的人 —— 預設就該是他看到的那一組。"""
    assert scope.DEFAULT_PROFILE == "fab"


#: 一個不可能是任何旗標真值的值 —— `use_profile` 漏設哪一格，哪一格就會留著它。
_SENTINEL = object()


def test_a_profile_sets_every_switch_it_names():
    """**每一個它宣告的旗標都真的被寫過一次。**

    ⚠ 這一條刻意**不寫死任何旗標的值** —— 那是 2026-09-17（F109）付過的錢：
    它本來斷言 `HIDDEN_STEPS == ("align",)`，而那一輪 `align` 拿回卡片庫、
    `HIDDEN_STEPS` 變成 `()`，於是這支測試紅了。紅得沒有道理：**壞掉的不是
    「一句話設一組開關」這個機制**，只是那組開關的內容換了。把值抄進測試裡的
    下場，是每一次產品範圍的決定都要順手改一次測試，而改久了就會變成「跟著
    程式碼改到綠」——那時候它就不再守任何東西。

    問的改成機制本身：先把每一格塞成一個不可能的哨兵值，套一組 profile，
    再看**沒有一格還是哨兵**，而且每一格都等於表上寫的那個值。
    """
    for name in scope.PROFILES:
        for key in _FLAGS:
            setattr(scope, key, _SENTINEL)
        assert scope.use_profile(name) == name
        for key in _FLAGS:
            got = getattr(scope, key)
            assert got is not _SENTINEL, \
                "profile %r 沒有設 %s —— 它會留著上一組的值" % (name, key)
            assert got == scope.PROFILES[name][key], \
                "profile %r 的 %s 設成了 %r，表上寫的是 %r" % (
                    name, key, got, scope.PROFILES[name][key])


def test_the_profiles_are_not_all_the_same_one():
    """至少有一個旗標**真的分得出組別** —— 不然 profile 是一個不做事的抽象層。

    值不寫死（見上一條），問的是「三組裡有沒有哪一格答案不一樣」。
    """
    differ = [k for k in _FLAGS
              if len({str(v[k]) for v in scope.PROFILES.values()}) > 1]
    assert differ, ("三組 profile 每一格都一樣 —— 那 `use_profile` 換不換都沒差。"
                    "要嘛有一組該長得不一樣，要嘛這整個機制可以拿掉。")


def test_every_profile_sets_the_same_switches():
    """一組漏設一個旗標的話，那個旗標會**留著上一組的值** —— 而症狀是
    「換了 profile 但有一格沒變」，找起來要翻三個檔案。"""
    keys = [set(v) for v in scope.PROFILES.values()]
    assert all(k == keys[0] for k in keys), \
        "各組管的旗標不一樣：%s" % {n: sorted(v) for n, v in scope.PROFILES.items()}


def test_an_unknown_name_falls_back_instead_of_raising():
    """這是產品範圍的旋鈕，不是輸入驗證的地方 —— 打錯字不該讓 Studio 開不起來。"""
    assert scope.use_profile("no_such_profile") == "fab"
    assert scope.current_profile() == "fab"
    assert scope.use_profile("") == "fab"


def test_the_environment_decides_at_startup():
    """廠內那台是**點捷徑開的** —— 捷徑改得動環境變數，改不動命令列。"""
    assert scope.profile_from_env({"D4T_PROFILE": "dev"}) == "dev"
    assert scope.profile_from_env({}) == scope.DEFAULT_PROFILE
    assert scope.profile_from_env({"D4T_PROFILE": ""}) == scope.DEFAULT_PROFILE


def _described_steps():
    from d4t.core.pipeline.step import list_steps
    import d4t.core.steps                    # noqa: F401 — 觸發註冊

    return [s.describe() for s in list_steps()]


def test_the_hidden_steps_really_disappear_from_the_library():
    """驗收條件：`HIDDEN_STEPS` 裡的字串真的讓那張卡從卡片庫消失。

    這裡問的是**卡片庫真的少了那張卡**，不是「旗標的值對不對」—— 後者是
    上面那條，而兩條中間那一段（`visible_steps` 有沒有讀到現在的值）壞掉的話，
    只有這一條會紅。

    ⚠ **這一條不挑任何一張特定的卡。** 2026-09-17（F109）起 `HIDDEN_STEPS`
    是空的（`align` 拿回來了），而那正是這種測試最危險的時候 —— 空的清單過濾
    不掉任何東西，「`visible_steps` 根本沒在讀那個旗標」這種壞法會**全綠通過**。
    所以這裡自己塞一張進去：機制留著的意思就是「下一次加一個字串就好」，
    那就當場加一個字串試給它看。
    """
    described = _described_steps()
    assert described, "卡片一張都沒註冊到，這支測試問不出任何事"
    victim = described[0]["key"]

    before = scope.HIDDEN_STEPS
    try:
        scope.HIDDEN_STEPS = (victim,)
        keys = {d["key"] for d in scope.visible_steps(described)}
        assert victim not in keys, (
            "`%s` 寫進 HIDDEN_STEPS 了，卡片庫還是看得到它 —— "
            "`visible_steps` 沒有讀到現在的值。" % victim)
        assert len(keys) == len(described) - 1, "收起來一張卡，別的卡跟著不見了"
    finally:
        scope.HIDDEN_STEPS = before


def test_nothing_is_hidden_right_now_and_that_is_on_purpose():
    """**現在三組 profile 都沒有收起任何一張卡**，而這裡把它釘住。

    釘住的理由是「收起來」是一個**使用者說出口的決定**（`CLAUDE.md` §5 那張表：
    收起來／刪掉／改名，判準都是使用者說了哪一句話）。悄悄多出一個字串 =
    有一張卡從畫面上消失了而沒有人做過那個決定，而症狀是「卡片庫裡找不到那張卡」
    —— 離 `scope.py` 很遠。

    要收起一張卡的時候：在 `_DEFAULT_HIDDEN` 加那個字串，**並在這裡寫下是誰、
    哪一天說的**。
    """
    hidden = {k: tuple(v["HIDDEN_STEPS"]) for k, v in scope.PROFILES.items()}
    assert all(v == () for v in hidden.values()), (
        "有 profile 收起了卡片而這支測試不知道：%s\n"
        "  收起來是使用者的決定 —— 把出處寫進 `scope._DEFAULT_HIDDEN` 的說明，"
        "再更新這一條。" % hidden)


# --------------------------------------------------------------------------- #
# 「一個寫入端」那條規矩
# --------------------------------------------------------------------------- #
def test_nobody_copies_a_flag_at_import_time():
    """**旗標要透過模組讀。**

    `from .scope import SHOW_ROUTE_BY` 拿到的是一份**當時的複本**，而
    `use_profile()` 改的是 scope 模組上的那個名字 —— 換了 profile 而那個模組
    停在舊值，症狀是「設定說關著、畫面上還在」，而它離設定很遠。

    這一條是踩出來的：`welcome.py` 本來就是這樣寫的（U10 那一輪改掉）。
    """
    bad = []
    for path in sorted((REPO / "d4t").rglob("*.py")):
        if path.name == "scope.py":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ImportFrom):
                continue
            if not str(node.module or "").endswith("scope"):
                continue
            for a in node.names:
                if a.name in _FLAGS:
                    bad.append("%s:%d 抄了 %s" % (path.name, node.lineno, a.name))
    assert not bad, (
        "這幾個地方在 import 時就把旗標的值抄走了：\n  %s\n"
        "  改成 `from . import scope` 再讀 `scope.<旗標>`。" % "\n  ".join(bad))


def test_the_flags_a_profile_names_are_real():
    """表上寫著的旗標要真的存在（打錯字的話它會安靜地建一個新的全域名字）。"""
    for name, switches in scope.PROFILES.items():
        for key in switches:
            assert hasattr(scope, key), "%s 那一組寫了不存在的旗標 %s" % (name, key)


def test_this_file_knows_every_flag_a_profile_sets():
    """`_FLAGS` 是這一份自己的清單，而上面三條靠它決定要檢查哪幾格。

    多一個旗標而忘了加進 `_FLAGS`，那個旗標就**沒有任何測試在看** ——
    而症狀是「新加的那一格在某一組 profile 底下留著上一組的值」。
    """
    for name, switches in scope.PROFILES.items():
        assert set(switches) == set(_FLAGS), (
            "profile %r 管的旗標跟這一份的 `_FLAGS` 對不起來：多了 %s、少了 %s"
            % (name, sorted(set(switches) - set(_FLAGS)),
               sorted(set(_FLAGS) - set(switches))))
