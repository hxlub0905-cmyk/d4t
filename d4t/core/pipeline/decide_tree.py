# d4t 判定樹的走訪 — 2026-08-25 (F29 C0) 從 `ui/tree_scene.py` 搬過來。
"""判定樹怎麼走、每一條路上有幾顆 —— **一份，不是兩份**。

為什麼搬家
----------
這些東西原本住在 `d4t/ui/tree_scene.py`，因為第一個要畫樹的人是畫布。
報表也要寫「每一類幾顆」，而**`d4t/core` 不得 import Qt**（鐵則 1）——
於是只剩兩條路：把邏輯搬進 core，或在 core 裡再寫一份。

第二條是這個 repo 踩過最多次的形狀（CLAUDE.md 開頭那一段：「同一件事只寫在
一個地方 —— 抄第二份出來的那份一定會漂移」）。所以搬家，而 `tree_scene`
改成 import 它並原樣再匯出：既有的 `from d4t.ui.tree_scene import
flow_counts` 一個字都不用改，而**只有一份實作**。

三個不變量沒有變（`docs/history/plans/F24-decision-tree.md` §4、§10）：

* **樹的每一步就是引擎的一步** —— 這裡走的樹直接來自 `DecideSpec`
  （`rules` 模式先過 `rules_to_tree`，那個轉換無損）。
* **分支流量守恆**：每個菱形 in = yes + no；根 = 這一批跑成功的顆數。
  流量是**拿每一顆的特徵把樹重走一遍**算的（:func:`flow_counts`）——
  引擎的 `meta["decide"]["path"]` 刻意不進結果 JSON（動 schema 動到黃金值），
  而 F24 ① 已證明「拿 features 重走 = 引擎走的那一條」。
* **未試跑：數字誠實地不在**（F18 的老規矩，不顯示 0）。

顏色也在這裡（而它不是 Qt）
---------------------------
:data:`LEAF_PALETTE` 是一串 hex 字串。它放這裡的理由跟上面同一句：**畫面上
那一類的顏色與報表上那一類的顏色必須是同一個**，而報表由 core 產、core 不能
import ui。bin 0（慣例上的 nuisance）那一格由呼叫端給 —— 那一個顏色**是**
主題的一部分（`theme.TOKENS["seg_disabled"]`），而主題住 UI。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .expression import parse_expression
from .recipe import TreeLeaf, TreeStep, rules_to_tree

__all__ = [
    "OPS", "parse_simple_condition", "format_condition", "rows_reaching",
    "count_yes", "suggest_condition", "display_tree", "layout_cells",
    "flow_counts", "leaf_stats", "decision_info", "path_text",
    "answer", "walk",
    "LEAF_PALETTE", "leaf_color", "verdict_rows", "NUISANCE_HEX",
    "DANGER_HEX", "FAILED_KEY", "UNBINNED_KEY",
]


OPS = (
    (">", "greater than"),
    ("<", "less than"),
    (">=", "at least"),
    ("<=", "at most"),
    ("==", "equals"),
    ("!=", "is not"),
)

#: 一個「單純的比較」長什麼樣：一個數字的名字、一個運算子、一個數值。
_SIMPLE_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*"
    r"(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$")


def parse_simple_condition(when: str):
    """``"contrast > 120"`` → ``("contrast", ">", 120.0)``；不是單純比較回
    ``None``（那時候編輯器退回「自己寫算式」那一格）。

    刻意**只認最單純的那一種**：複合條件（``(a > 5) * (b < 2)``）用猜的去
    拆成幾格，猜錯的那次會安靜地改掉使用者的判定 —— 而它跑得完、有數字。
    認不得就誠實地說「這一條要用算式編輯」。
    """
    m = _SIMPLE_RE.match(str(when or ""))
    if not m:
        return None
    return (m.group(1), m.group(2), float(m.group(3)))


def format_condition(name: str, op: str, value: float) -> str:
    """三格 → ``when`` 的字串。``%g`` 讓 120.0 寫成 ``120``（使用者打的樣子）。"""
    return "%s %s %g" % (str(name), str(op), float(value))


def rows_reaching(tree: Any, rows: Any, path: str) -> List[Dict[str, Any]]:
    """走到樹上這一步（或這片葉子）的那些顆。

    滑桿的範圍與「幾顆說 yes」都吃它 —— 用**流到這一步**的顆而不是整批，
    因為那才是這一步真正在分的東西（畫布上那條分支的顆數講的也是它，
    兩個數字必須是同一個）。
    """
    out: List[Dict[str, Any]] = []
    if tree is None:
        return out
    want = str(path)
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001 — 顯示用，走不動就不算
            continue
        if p.startswith(want):
            out.append(r)
    return out


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    return value != threshold


def count_yes(rows: Any, name: str, op: str, value: float):
    """``(幾顆說 yes, 有值的顆數)`` —— 拖滑桿時旁邊那一行即時的數字。

    沒有那個數字的顆不算進分母：它們在引擎裡會走 `Let.fill` 或整顆失敗，
    把它們算成「no」會讓這一行說一個不成立的話。
    """
    yes = n = 0
    for r in rows or []:
        v = (r.get("features") or {}).get(str(name))
        if not isinstance(v, (int, float)):
            continue
        n += 1
        if _compare(float(v), str(op), float(value)):
            yes += 1
    return yes, n


#: 建議問題時**不挑**這些（它們不是「量出來的東西」）。
_NOT_A_QUESTION = ("score", "route_taken")


def suggest_condition(rows: Any, prefer: Any = ()):
    """幫使用者挑一個起手的問題：``(名字, ">", 門檻)``；挑不出來回 ``None``。

    規則刻意簡單、而且講得出理由：**挑這一批上分得最開的那個數字**
    （四分位距 ÷ 中位數，量綱無關），門檻放在**中位數**——
    一按就有東西看，剩下的用滑桿調。這不是自動最佳化，是一個
    「不會卡在空白畫面」的起點（推廣鐵則：按了要有東西發生）。

    ``prefer`` 是這份 recipe 的 working numbers（`decide.let` 的名字）——
    使用者自己組出來的數字優先，那是他心裡的量。
    """
    stats: Dict[str, List[float]] = {}
    for r in rows or []:
        if not r.get("ok"):
            continue
        for k, v in (r.get("features") or {}).items():
            k = str(k)
            if k in _NOT_A_QUESTION or k.endswith("_missing") \
                    or k.endswith("_raw"):
                continue
            if isinstance(v, (int, float)):
                stats.setdefault(k, []).append(float(v))
    best = None
    prefer = {str(x) for x in (prefer or ())}
    for name, vals in stats.items():
        if len(vals) < 4:
            continue
        s = sorted(vals)
        med = s[len(s) // 2]
        q1, q3 = s[len(s) // 4], s[(3 * len(s)) // 4]
        spread = (q3 - q1) / (abs(med) or 1.0)
        if spread <= 0:
            continue
        rank = (1 if name in prefer else 0, spread)
        if best is None or rank > best[0]:
            best = (rank, name, med)
    if best is None:
        return None
    return (best[1], ">", round(float(best[2]), 4))


# --------------------------------------------------------------------------- #
# 純資料（headless 測得到）
# --------------------------------------------------------------------------- #
def display_tree(decide: Any) -> Optional[Any]:
    """要畫的那棵樹。``decide`` 是 None → 沒有判定區的樹（回 None）。

    `rules` 模式**畫成等價的鏈狀樹**（`rules_to_tree`，無損）—— 畫布上只有
    一種語言：一步一問。使用者看到的形狀跟引擎走的形狀是同一個。
    """
    if decide is None:
        return None
    if decide.tree is not None:
        return decide.tree
    return rules_to_tree(decide)


def _is_otherwise(decide: Any, path: str, tree: Any) -> bool:
    """這片葉子是不是「(anything else)」—— 全部往 no 走到底的那一片。

    只有 `rules` 模式有 otherwise 的概念（鏈狀樹的最深 no 葉）；手寫的樹
    沒有 —— 每片葉子都是使用者自己放的。
    """
    if decide is None or decide.tree is not None:
        return False
    return path == "n" * len(path) and bool(path) or (
        path == "" and isinstance(tree, TreeLeaf))


def layout_cells(tree: Any, decide: Any = None) -> List[Dict[str, Any]]:
    """樹 → 一串格子：``{"path","kind","col","row", ...}``。

    佈局規則（mockup 定稿）：**yes 往右、no 往下**。yes 那一支排完佔了幾列，
    no 那一支從它下面接著排 —— 所以鏈狀樹（rules）畫出來就是一道樓梯：
    每一步右邊一個托盤、往下一步。
    """
    cells: List[Dict[str, Any]] = []
    if tree is None:
        return cells

    def walk(node: Any, path: str, col: int, row: int) -> int:
        if isinstance(node, TreeLeaf):
            cells.append({"path": path, "kind": "leaf", "col": col, "row": row,
                          "bin": int(node.bin), "label": str(node.label),
                          "otherwise": _is_otherwise(decide, path, tree)})
            return 1
        cells.append({"path": path, "kind": "step", "col": col, "row": row,
                      "when": str(node.when)})
        h_yes = walk(node.yes, path + "y", col + 1, row)
        h_no = walk(node.no, path + "n", col, row + h_yes)
        return h_yes + h_no

    walk(tree, "", 0, 0)
    return cells


def answer(when: str, feats: Any) -> Tuple[bool, List[str]]:
    """一題的答案，以及**問不出來的話是缺了哪幾個數字**（F30，2026-08-25）。

    ``(成立?, 缺了哪幾個)``。缺了東西的時候答案是 **False（走 no 那一支）**，
    而缺的名字要交出去 —— 呼叫端負責讓那件事在畫面與 CSV 上看得見。

    為什麼問不出來要算「否」而不是讓整顆失敗
    ----------------------------------------
    「量不到就不寫那一格」是量測卡的規矩（不是 0、也不是 NaN），所以
    ``cd_area_px`` 在一顆什麼都沒量到的 defect 上**本來就不存在** ——
    那是**正確**的行為。而 F30 之前，樹上只要問到它，`Expression.eval` 就
    raise，`run_defect` 接成整顆 ``ok=False``、錯誤訊息
    ``[score] unknown variable 'cd_area_px'``。

    於是一顆跑得好好的 defect 被報成「執行失敗」：它不進 Results 的統計、
    疊圖的 ``ok=True`` 過濾也把它濾掉 —— 而「什麼都沒量到」正是使用者最想
    看到的那一類之一。使用者 2026-08-25 定調：**那一題答「否」，繼續走。**

    ⚠ 這**不是**「缺值 = 0」。`0 > 5` 與「問不出來」在這裡都走 no，但兩者
    在 CSV 上分得出來：問不出來的那些顆 ``decide_unanswered`` 大於 0。
    要把「有沒有量到」當成一個**明講的**問題來問，走 ``let`` 的
    「missing ⇒ 用 __」（F24 ⑤）—— 那條路會給你一個 ``<name>_missing`` 的
    旗標，而它是一個真的特徵，樹上問得到、CSV 上畫得出分布。

    ⚠ **值不是數字仍然 raise。** 那不是「量不到」，那是有人往 features 塞了
    奇怪的東西 —— 安靜地答「否」會把一個真的 bug 埋掉。
    """
    expr = parse_expression(when)
    missing = sorted(v for v in expr.variables if v not in (feats or {}))
    if missing:
        return False, missing
    return expr.eval(feats) != 0.0, []


def walk(tree: Any, feats: Any) -> Tuple[Any, str, List[str]]:
    """把這一顆的特徵餵進樹裡走一遍：``(落在哪片葉子, 路徑, 問不出來的名字)``。

    **引擎與畫布走的是這一支** —— `engine._eval_decision` 與 :func:`_path_of`
    都叫它。以前那兩邊是各自寫的兩段迴圈，而 `_path_of` 的說明寫著「判準跟
    引擎一字不差」：只改一邊的那一天，畫布上的顆數與引擎判的類別會對不起來，
    而畫面上沒有任何東西看得出來。
    """
    node, path = tree, ""
    missing: List[str] = []
    while not isinstance(node, TreeLeaf):
        yes, gaps = answer(node.when, feats)
        missing.extend(gaps)
        node = node.yes if yes else node.no
        path += "y" if yes else "n"
    return node, path, missing


def _path_of(tree: Any, feats: Dict[str, Any]) -> str:
    """一顆 defect 的特徵走這棵樹，走的是哪條路（``"yn…"``）。

    判準跟引擎一字不差（`engine._eval_decision`）—— 因為**是同一支**
    （:func:`walk`）。**非 0 就是成立**；問不出來的那一題算「否」。
    """
    return walk(tree, feats)[1]


def flow_counts(tree: Any, rows: Any) -> Dict[str, int]:
    """每個節點「流過幾顆」：``路徑前綴 → 顆數``（``""`` = 根 = 全部）。

    守恆是**構造上的**：一顆走到路徑 p，就把 p 的每一個前綴各 +1 ——
    所以每個菱形的 in 恆等於它 yes + no 的和，不必另外對帳。

    只算**判定真的跑到**的顆（``ok`` 且有 ``bin``）；某一顆的特徵走不動樹
    （表達式炸了）就整顆不計 —— 記半條路會把守恆弄破，而那正是這張圖存在
    的理由。
    """
    counts: Dict[str, int] = {}
    if tree is None:
        return counts
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001 — 顯示用，走不動就不計
            continue
        for i in range(len(p) + 1):
            prefix = p[:i]
            counts[prefix] = counts.get(prefix, 0) + 1
    return counts


def leaf_stats(tree: Any, rows: Any,
               ground_truth: Optional[Dict[str, Any]]) -> Dict[str, Tuple[int, int]]:
    """每片葉子「幾顆是真的」：``路徑 → (真缺陷數, 對得上 ground truth 的顆數)``。

    沒有 ground truth 就是空的 —— 托盤上那一小條純度就不畫
    （不是畫一條 0%：沒有分母不等於純度是零）。
    """
    out: Dict[str, Tuple[int, int]] = {}
    if tree is None or not ground_truth:
        return out
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        gt = ground_truth.get(str(r.get("defect_id")))
        if not isinstance(gt, dict) or "is_real" not in gt:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001
            continue
        real, n = out.get(p, (0, 0))
        out[p] = (real + (1 if gt.get("is_real") else 0), n + 1)
    return out


def decision_info(decide: Any, rows: Any = None,
                  ground_truth: Optional[Dict[str, Any]] = None
                  ) -> Optional[Dict[str, Any]]:
    """`PipelineCanvas.set_decision` 吃的那一份 dict。

    ``decide`` 是 None（recipe 走二元 score 老路）→ 回 None，畫布上沒有
    判定區 —— 那條路的判定住在右欄的門檻滑桿，畫一個空樹只會讓人問這是
    什麼。``rows`` 是 None 或空 = **還沒試跑**：樹的形狀在、數字不在。
    """
    if decide is None:
        return None
    tree = display_tree(decide)
    ran = bool(rows)
    return {
        "lets": ["%s = %s" % (x.name, x.expr) for x in decide.let],
        "cells": layout_cells(tree, decide),
        "counts": flow_counts(tree, rows) if ran else None,
        "leaf_stats": leaf_stats(tree, rows, ground_truth) if ran else {},
    }


def path_text(tree: Any, path: str) -> str:
    """一顆 defect 走過的路，一句給人讀的話（Preview 的 Path，F24 §8）。

    ``cd_deq_missing > 0 ? no → contrast > 120 ? yes`` —— 問題照走過的順序，
    每一步接它的答案。走不完（樹跟 path 對不上）就回空字串，不要硬湊半句。
    """
    node, bits = tree, []
    for ch in str(path):
        if not isinstance(node, TreeStep):
            return ""
        bits.append("%s ? %s" % (node.when, "yes" if ch == "y" else "no"))
        node = node.yes if ch == "y" else node.no
    return " → ".join(bits)




#: 托盤色條的顏色（類別色）。**畫面與報表共用這一份** —— 同一類在兩個地方
#: 不同色的話，「這根柱子是哪一類」在報表上要重新學一次。
LEAF_PALETTE = ("#3574d6", "#2e9e62", "#d97706", "#8a5fbf",
                "#c2418a", "#0e9aa7")


#: bin 0（慣例上的 nuisance）的預設顏色 —— 一個中性灰。
#: 畫面上會換成主題的那一個（`theme.TOKENS["seg_disabled"]`），報表用這個。
NUISANCE_HEX = "#9aa0a6"

#: 「算不出來」那兩列的顏色（畫面上是 `theme.TOKENS["danger"]`）。
DANGER_HEX = "#d05a4c"

#: 「算不出來」那兩列的 key（不可能跟樹的路徑撞名 —— 路徑只有 y/n）。
FAILED_KEY = "!failed"
UNBINNED_KEY = "!unbinned"


def leaf_color(bin_: int, nuisance: str = NUISANCE_HEX) -> str:
    """一個 bin 一個穩定的顏色（同一份 recipe 重開顏色不變）。

    ``nuisance`` 是 bin 0 那一格用的顏色 —— 畫面上那一個是主題的一部分
    （`theme.TOKENS["seg_disabled"]`），而主題住 UI，所以由呼叫端給。
    """
    b = int(bin_)
    if b == 0:
        return str(nuisance)
    return LEAF_PALETTE[(b - 1) % len(LEAF_PALETTE)]


def verdict_rows(decide: Any, results: Any,
                 ground_truth: Optional[Dict[Any, Any]] = None,
                 nuisance: str = NUISANCE_HEX,
                 danger: str = DANGER_HEX) -> List[Dict[str, Any]]:
    """``[{key, name, bin, count, ids, real, labelled, colour, kind}, …]``
    —— **每一類幾顆**。

    順序**跟畫布上的樹一樣**（`layout_cells` 的走訪順序）：面板、畫布與報表
    講同一件事的時候，順序也該是同一個；而且它**穩定** —— 重跑一次列不會跳來
    跳去（照顆數排序會，而那讓人以為結構變了）。

    一列是**一片葉子不是一個 bin**：兩片葉子共用一個 bin 是合法的，而它們是
    使用者眼中兩個不同的類別。也因此篩選要用這裡算好的 defect_id（``ids``），
    不能用 bin。

    最後補上「算不出來」的那幾顆。它們是**兩種**不同的事故，所以是兩列：

    * ``kind="failed"`` —— 這一顆有卡片出錯（鐵則 7：單顆出錯不殺整批，
      回 ``ok=False`` 並帶原因），根本沒走到判定；
    * ``kind="unbinned"`` —— 跑完了，但判定給不出 bin（表達式炸了）。

    兩種都**沒有的時候整列不出現**（F18：不顯示 0）。

    ⚠ 這一支 2026-08-25（F29 C0）從 `ui/verdict_band.py` 搬進 core：報表也要
    寫「每一類幾顆」，而 core 不得 import Qt（鐵則 1）。顏色因此變成兩個參數
    —— 畫面上傳主題的那兩個，報表用上面的預設。
    """
    rows_in = [dict(r) for r in (results or [])]
    out: List[Dict[str, Any]] = []
    tree = display_tree(decide)

    if tree is not None:
        # path → 走到那裡的 defect_id（順序照結果的順序）。
        by_path: Dict[str, List[str]] = {}
        for r in rows_in:
            if not r.get("ok") or r.get("bin") is None:
                continue
            try:
                p = _path_of(tree, dict(r.get("features") or {}))
            except Exception:          # noqa: BLE001 — 顯示用，走不動就不計
                continue
            by_path.setdefault(p, []).append(str(r.get("defect_id")))

        truth = dict(ground_truth or {})
        for cell in layout_cells(tree, decide):
            if cell.get("kind") != "leaf":
                continue
            path = str(cell.get("path"))
            ids = by_path.get(path, [])
            real = labelled = 0
            for did in ids:
                gt = truth.get(did)
                if isinstance(gt, dict) and "is_real" in gt:
                    labelled += 1
                    real += 1 if gt.get("is_real") else 0
            out.append({
                "key": path or "root",
                "name": str(cell.get("label") or ""),
                "bin": int(cell.get("bin")),
                "count": len(ids),
                "ids": ids,
                "real": real,
                "labelled": labelled,
                "colour": leaf_color(int(cell.get("bin")), nuisance),
                "kind": "class",
            })
    else:
        # 沒有判定樹（二元 score 的老路）—— 一列一個 bin。
        by_bin: Dict[int, List[str]] = {}
        for r in rows_in:
            b = r.get("bin")
            if not r.get("ok") or b is None:
                continue
            by_bin.setdefault(int(b), []).append(str(r.get("defect_id")))
        for b in sorted(by_bin):
            out.append({"key": "bin%d" % b, "name": "bin %d" % b, "bin": b,
                        "count": len(by_bin[b]), "ids": by_bin[b],
                        "real": 0, "labelled": 0,
                        "colour": leaf_color(b, nuisance), "kind": "class"})

    failed = [str(r.get("defect_id")) for r in rows_in if not r.get("ok")]
    unbinned = [str(r.get("defect_id")) for r in rows_in
                if r.get("ok") and r.get("bin") is None]
    if failed:
        out.append({"key": FAILED_KEY, "name": "a card errored", "bin": None,
                    "count": len(failed), "ids": failed, "real": 0,
                    "labelled": 0, "colour": str(danger), "kind": "failed"})
    if unbinned:
        out.append({"key": UNBINNED_KEY, "name": "no verdict", "bin": None,
                    "count": len(unbinned), "ids": unbinned, "real": 0,
                    "labelled": 0, "colour": str(danger), "kind": "unbinned"})
    return out
