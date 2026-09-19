#!/usr/bin/env python3
# 量 StudioWindow 的表面 — authored 2026-09-18 (F116 第 1 步).
"""量 `StudioWindow` 的表面：方法、`self.*` 名字，以及**測試裡用到的名字**。

為什麼需要這支
--------------
F116 把 `StudioWindow` 的內容一塊一塊搬進 controller。這種搬家最危險的失敗
不是搬壞了 —— 那測試當場就紅。危險的是**搬走一個測試正在用的名字**：測試
大量用屬性存取（`w.inspector()`、`w._refresh_charts_window()`），`grep import`
答不出「誰在用這個名字」（`CLAUDE.md` §4：判準是搬前有的名字搬後 `hasattr`
還答得出來）。

所以搬之前先把表面寫下來，搬完對一次：

    python tools/studio_surface.py --save before.json
    ...搬家...
    python tools/studio_surface.py --check before.json

`--check` 問兩件事：

1. `before.json` 裡**每一個被測試用到的名字**，現在還在不在視窗上（是方法、
   或被 `self.x = …` / 別的模組的 `win.x = …` 設過）。答不出來的列出來 ——
   那就是「要嘛留一行門面、要嘛改測試」的清單。
2. **這一輪搬走的名字，`d4t/ui/` 裡還有沒有人在 `win.<名字>` 上叫它。**
   那種呼叫是**接線**，只有在使用者真的按下那一顆的那一刻才會炸 —— import
   過、視窗開得起來、而測試大多不會碰到。F116 第 3 步漏掉三處
   （`region_check.py` 兩處、`studio_layout.py` 一處），而它們是「按下
   Results 裡的一列就 AttributeError」那種。

⚠ 這是**靜態**的近似：屬性若是在 controller 裡 `setattr(self.w, ...)` 設的它
看不到，會誤報。誤報就改成在那一支裡明寫 `win.xxx = ...`（本來就該這樣寫）。

本檔與 `tools/` 其他工具一樣是 stdlib-only。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STUDIO = REPO / "d4t" / "ui" / "studio.py"

#: 測試裡指向 StudioWindow 的常見變數名；漏抓的話加在這裡。
_VAR = r"(?:w|win|window|studio|sw|ran|mixed_window|self\.w|self\.win)"

#: `monkeypatch.setattr(type(win), "_picks_a_center", …)` 這一種：名字是**字串**，
#: 上面那條認屬性存取的樣式看不到它。漏掉的代價是測試打在一個**已經沒有人叫**的
#: 方法上（斷言照過，而它守的事情沒有在守）—— F116 第 1 步踩到 7 處。
_PATCHED = re.compile(r'(?:set|get|has)attr\([^)]*?["\'](\w+)["\']')


def _stores(node: ast.AST, is_window) -> set:
    """``<視窗>.名字 = …`` 裡的那些名字。``is_window`` 判斷「點的左邊是視窗嗎」。"""
    out = set()
    for n in ast.walk(node):
        if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                and is_window(n.value)):
            out.add(n.attr)
    return out


def _is_self(v) -> bool:
    return isinstance(v, ast.Name) and v.id == "self"


def _is_win(v) -> bool:
    """`win`（模組層函式吃的那個）或 `self.w`（controller 握著的那個）。"""
    if isinstance(v, ast.Name) and v.id == "win":
        return True
    return (isinstance(v, ast.Attribute) and v.attr == "w" and _is_self(v.value))


def shape() -> tuple:
    """`StudioWindow` 現在有哪些方法、哪些名字被設在視窗上。

    ⚠ **不只看 `studio.py`**：F116 把內容搬進 `ui/gauge_panel.py`、
    `ui/preview_overlays.py`、`ui/studio_layout.py` 那一族之後，`win.toolbar`、
    `win.btn_trial`、`self.w.xxx` 這些**仍然是視窗上的名字**，只是賦值那一行
    住在別的檔案裡。只讀 `studio.py` 的話它們會被當成「不見了」——
    第 2 步一次誤報 69 個（`pipeline`、`param_form`、`results` …），而那些名字
    一個都沒有動過。
    """
    tree = ast.parse(STUDIO.read_text(encoding="utf-8"))
    cls = next(c for c in tree.body
               if isinstance(c, ast.ClassDef) and c.name == "StudioWindow")
    meths = {f.name for f in cls.body
             if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    attrs = _stores(cls, _is_self)
    for node in cls.body:                     # 類別層的常數也是視窗上的名字
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            attrs.add(node.target.id)
        elif isinstance(node, ast.Assign):
            attrs |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    for f in sorted((REPO / "d4t" / "ui").glob("*.py")):
        if f.name == "studio.py":
            continue
        try:
            attrs |= _stores(ast.parse(f.read_text(encoding="utf-8")), _is_win)
        except SyntaxError:                       # 壞檔案不該讓這支掛掉
            continue
    return meths, attrs


def used_by_tests(names: set) -> dict:
    """`tests/` 裡以視窗物件存取的名字 → 出現幾次。"""
    pat = re.compile(r"\b%s\.(\w+)" % _VAR)
    hits: dict = {}
    for f in sorted((REPO / "tests").glob("*.py")):
        text = f.read_text(encoding="utf-8")
        for m in pat.findall(text):
            if m in names:
                hits[m] = hits.get(m, 0) + 1
        for m in _PATCHED.findall(text):      # 字串形式（見 `_PATCHED`）
            if m in names:
                hits[m] = hits.get(m, 0) + 1
    return hits


def dangling_calls(gone: set) -> list:
    """`d4t/ui/*.py` 裡還在叫**這一輪搬走的那些名字**的那幾行。

    為什麼需要這一條：`--check` 只看 `tests/`，而搬走一個名字之後，**別的
    UI 模組**也可能還在叫它 —— `region_check.py` 的
    `win.region_window.defect_activated.connect(win._on_defect_activated)`
    與 `studio_layout.py` 的 `lambda name: win._on_why_item(…)` 就是這樣漏掉的
    （F116 第 3 步）。它們是**接線**，只有在使用者真的按下那一顆的那一刻才會
    炸，所以 import 過、開得起來、而且測試大多不會碰到。

    ⚠ 判準是「**搬走的**名字」而不是「視窗上沒有的名字」：後者會把每一個
    繼承來的 Qt 方法（`show`、`statusBar`…）、每一個類別層的常數，以及每一個
    剛好也叫 `win` 的區域變數都報成紅的（實測 26 個全是誤報）。
    """
    if not gone:
        return []
    pat = re.compile(r"\b(?:win|self\.w)\.(\w+)")
    out = []
    for f in sorted((REPO / "d4t" / "ui").glob("*.py")):
        if f.name == "studio.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for name in pat.findall(line):
                if name in gone:
                    out.append((f.name, i, name, line.strip()[:70]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", help="把現在的表面寫成 JSON")
    g.add_argument("--check", help="對著一份 JSON 檢查測試用到的名字還在不在")
    a = ap.parse_args(argv)

    meths, attrs = shape()
    if a.save:
        used = used_by_tests(meths | attrs)
        Path(a.save).write_text(json.dumps(
            {"methods": len(meths), "attrs": len(attrs), "used": used,
             "names": sorted(meths | attrs)},
            ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print("methods=%d attrs=%d used_by_tests=%d"
              % (len(meths), len(attrs), len(used)))
        return 0

    before = json.loads(Path(a.check).read_text(encoding="utf-8"))
    missing = sorted(n for n in before["used"]
                     if n not in meths and n not in attrs)
    print("methods %d -> %d, attrs %d -> %d"
          % (before["methods"], len(meths), before["attrs"], len(attrs)))
    for n in missing:
        print("  x 測試用到 %s（%d 處），StudioWindow 上已經沒有"
              % (n, before["used"][n]))

    # 這一輪從視窗上消失的名字（舊的 JSON 沒有 `names`，就跳過這一關）
    gone = set(before.get("names") or ()) - (meths | attrs)
    if "names" not in before:
        print("  （這份基準沒有 names，跳過「別的模組還在叫它嗎」那一關）")
    dangling = dangling_calls(gone)
    for fname, line_no, name, text in dangling:
        print("  x %s:%d 指到 win.%s，而 StudioWindow 上沒有這個名字\n      %s"
              % (fname, line_no, name, text))
    if dangling:
        return 1
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
