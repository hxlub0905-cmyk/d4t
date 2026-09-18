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

`--check` 對 `before.json` 裡**每一個被測試用到的名字**，確認它仍是
`StudioWindow` 的方法、或仍在某個方法裡被 `self.x = ...` 設過；答不出來的
列出來並回非零 —— 那就是「要嘛留一行門面、要嘛改測試」的清單。

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


def shape() -> tuple:
    """`StudioWindow` 現在有哪些方法、哪些 `self.*` 被賦值過。"""
    tree = ast.parse(STUDIO.read_text(encoding="utf-8"))
    cls = next(c for c in tree.body
               if isinstance(c, ast.ClassDef) and c.name == "StudioWindow")
    meths = {f.name for f in cls.body
             if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    attrs = set()
    for node in ast.walk(cls):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "self" and isinstance(node.ctx, ast.Store)):
            attrs.add(node.attr)
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
            {"methods": len(meths), "attrs": len(attrs), "used": used},
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
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
