# ADEPT UI-language guard — authored 2026-07-28 (M7).
"""UI 一律英文：掃原始碼，禁止「會顯示在畫面上的字串」出現 CJK。

為什麼要這條規則
----------------
使用者的原話：**「中英夾雜很混亂」**。工具列是英文、卡片名是中文、錯誤訊息
又是中文夾英文術語——每換一個區塊就要換一次讀法，對第一次用的人是純噪音。
所以 M7 把所有 user-facing 字串統一成英文，並用這支測試把它鎖住。

界線在哪（很重要）
------------------
**只管會顯示給使用者看的字串**，也就是 AST 裡的字串常數。
docstring 與 ``#`` 註解**維持中文** —— 那是給開發者/接手者的說明文件，
是這個 repo 刻意累積的資產（見 ``docs/HANDOVER.md``），翻成英文只會弄丟脈絡。

實作上：用 :mod:`ast` 走一遍，跳過 module/class/function 的 docstring 節點，
其餘字串常數只要含 CJK 就算違規。``#`` 註解根本不在 AST 裡，天然被排除。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

PKG = Path(__file__).resolve().parent.parent / "adept"

#: 還沒翻完、暫時放行的檔案（相對 ``adept/`` 的 posix 路徑）。
#:
#: * ``__main__.py`` —— CLI 是另一個介面層，使用者這次要求的是 GUI；
#:   要不要跟著英文化是獨立的決定，還沒問過。
#: * ``core/ingest/klarf_core.py`` —— 從 KLIP 整檔 vendoring 進來的 KLARF
#:   引擎（``docs/HANDOVER.md`` 稱之為「最重要的資產」）。它的 lint / 修補
#:   訊息**會**出現在 Export 精靈的「Output health check」區塊，所以最終應該
#:   一起英文化；但那是一個獨立、需要小心處理的改動，不混在 UI 這批裡。
PENDING: Tuple[str, ...] = (
    "__main__.py",
    "core/ingest/klarf_core.py",
)


def _has_cjk(text: str) -> bool:
    """CJK 文字**或全形標點**。

    標點也要抓：``、``、``：``、全形空白 ``\u3000`` 這些混在英文句子裡一樣刺眼，
    而且是翻譯時最容易漏掉的東西（M7 就漏了 9 處，全都是標點）。
    """
    return any("一" <= ch <= "鿿"        # CJK 統一表意文字
               or "　" <= ch <= "〿"      # CJK 標點（、。「」，含全形空白）
               or "！" <= ch <= "｠"      # 全形 ASCII 變體（：；！？（））
               for ch in text)


def _docstring_node_ids(tree: ast.AST) -> set:
    """module / class / function 的 docstring 節點 id（這些不算 UI 字串）。"""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _cjk_strings(path: Path) -> List[Tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_node_ids(tree)
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in skip and _has_cjk(node.value)):
            hits.append((node.lineno, node.value))
    return sorted(hits)


def test_no_cjk_in_user_facing_strings():
    """UI 顯示的字串一律英文（docstring / 註解不在此限）。"""
    offenders = []
    for py in sorted(PKG.rglob("*.py")):
        rel = py.relative_to(PKG).as_posix()
        if rel in PENDING:
            continue
        for lineno, value in _cjk_strings(py):
            offenders.append("%s:%d  %s" % (rel, lineno, value[:70]))
    assert not offenders, (
        "以下字串會顯示給使用者，但含中文（UI 一律英文）：\n  "
        + "\n  ".join(offenders))


def test_pending_files_are_really_still_pending():
    """PENDING 清單不准長霉：翻完了就要把檔案從清單移除。"""
    stale = [rel for rel in PENDING if not _cjk_strings(PKG / rel)]
    assert not stale, (
        "這些檔案已經沒有中文 UI 字串了，請把它們從 PENDING 移除：%s" % stale)


def test_step_cards_are_english():
    """卡片庫看得到的每一張卡：label / help / 每個 ParamSpec 的 help 都要是英文。"""
    import adept.core.steps  # noqa: F401 — 觸發註冊
    from adept.core.pipeline import list_steps

    bad = []
    for step in list_steps():
        for field, text in (("label", step.label), ("help", step.help)):
            if _has_cjk(str(text)):
                bad.append("%s.%s = %r" % (step.key, field, text))
        for spec in step.params:
            if _has_cjk(str(spec.help)):
                bad.append("%s.%s.help = %r" % (step.key, spec.name, spec.help))
    assert not bad, "卡片庫仍有中文字串：\n  " + "\n  ".join(bad)


def test_every_card_declares_a_known_group():
    """F7-3：每張卡都要落在一個已知的流程階段，不能靠預設矇混過去。

    ``resolve_group()`` 有依 category 的保守 fallback（讓外掛卡不會壞），
    但**本 repo 內建的卡片一律要明講**——否則新加的量測卡會安靜地掉進
    Enhance，而使用者永遠找不到它。
    """
    import adept.core.steps  # noqa: F401
    from adept.core.pipeline import list_steps
    from adept.core.pipeline.step import GROUP_ORDER

    undeclared, unknown = [], []
    for step in list_steps():
        if not step.group:
            undeclared.append(step.key)
        elif step.group not in GROUP_ORDER:
            unknown.append("%s -> %r" % (step.key, step.group))
    assert not undeclared, "沒宣告 group 的卡片：%s" % undeclared
    assert not unknown, "group 不在 GROUP_ORDER 裡：%s" % unknown
