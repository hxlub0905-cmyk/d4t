"""把一個獨立小工具抽成**一個可以帶走的資料夾**（F120，2026-09-23）。

使用者 2026-09-23：「請幫我將這個 pitch helper 獨立成一個資料夾」＋「我之後帶走
後 d4t 會把 pitch helper 移除，就等於 pitch helper 直接開新 repo，原來 d4t 不會
有殘留」。

⚠ **這一支是一次性的搬家工具，不是一道長期的產生線。**
d4t 那邊之後會把這個工具刪掉，所以不會出現「兩個家會漂」的問題 —— 也因此這裡
**不做**「產生後再比對」那一套。它要做對的只有兩件最容易手工做錯的事：

1. **相依閉包**：從進入點把 `d4t.` 底下真正會被 import 到的模組全部算出來
   （含 `from d4t.core.algo import period` 這種 package 底下的名字）。漏一支，
   帶走的資料夾會在某一條沒走過的路上才炸。
2. **import 改寫**：`from ..core.algo import period` 這種相對 import 在新的
   package 裡要還原得對。做法是**保持目錄形狀**（`<pkg>/ui/`、`<pkg>/core/`），
   所以相對 import 一個字都不用動 —— 只有絕對的 `d4t.xxx` 要換成相對。

用法::

    python tools/extract_app.py pitch  apps/pitch
    python tools/extract_app.py simgen apps/simgen
    python tools/extract_app.py --list
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import shutil
import sys
from typing import Dict, List, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 哪幾個工具抽得出來 —— `(進入點模組, package 名, 視窗標題, 一句話)`。
#:
#: ⚠ **判準不是「它是不是一個視窗」，是「它有沒有自己的 `run()` 進入點、而且
#: 不吃目前的 recipe」**（`docs/ARCHITECTURE.md` 的「什麼時候可以開一個新視窗」
#: 那張表）。`d4t/ui` 底下唯二符合的就是這兩個。
APPS: Dict[str, Tuple[str, str, str, str]] = {
    "pitch": ("d4t.ui.pitch_helper", "pitchapp", "Pitch helper",
              "丟一張圖進去，回答它的 cell period。"),
    "simgen": ("d4t.ui.gc_generator", "simgenapp", "Golden Cell generator",
               "從一張 Golden Cell 產一整批模擬資料。"),
}

#: 一起帶走的非程式檔（相對 repo 根目錄 → 相對 package 根目錄）。
#:
#: ⚠ **`branding.py` 裡寫著檔名的每一個檔都要在**。`ICON_PATH` 指的 `d4t.svg`
#: 沒被複製的話，帶走的那一份會有一個指向不存在檔案的常數 —— 而 `app_icon()`
#: 的 `os.path.isfile` 會安靜地回一個空 `QIcon`，所以**它不會報錯，只是沒有
#: 圖示**。抽取完有一道檢查（`_check_assets`）在擋這件事。
ASSETS: Dict[str, List[Tuple[str, str]]] = {
    "pitch": [("d4t/ui/assets/pitch.svg", "ui/assets/pitch.svg"),
              ("d4t/ui/assets/d4t.svg", "ui/assets/d4t.svg"),
              ("d4t/ui/assets/d4t-wordmark.svg", "ui/assets/d4t-wordmark.svg"),
              ("d4t/ui/assets/d4t-wordmark-dark.svg",
               "ui/assets/d4t-wordmark-dark.svg")],
    "simgen": [],
}

#: 抽出來之後要換掉的字 —— **一份很短、寫在這裡看得見的清單，不是魔法**。
#:
#: ⚠ 判準只有一個：**這句話在新的 repo 裡還是不是真的。**
#: 指向 d4t Studio 某個地方的指路、掛著主程式名字的視窗標題、講
#: `python -m d4t …` 的進入點說明 —— 這三種在獨立出去之後都會變成假話，而
#: 「一句寫了找不到的東西的指路，比不寫還糟」（F120 §27 為了 `NEXT_STEP`
#: 付過一次這個錢）。**其餘一個字都不改** —— 抽取要是忠實的，不然帶走的那份
#: 跟你在 d4t 裡看到的就是兩個東西。
RENAMES: Dict[str, List[Tuple[str, str]]] = {
    "pitch": [
        ('NEXT_STEP = "Next: paste it into Template & regions → Cell W / Cell H"',
         'NEXT_STEP = "Copy it into your tool\'s cell size fields."'),
        ('"""``python -m d4t pitch`` 的進入點。"""',
         '"""``python main.py`` 的進入點。"""'),
    ],
    "simgen": [
        ('self.setWindowTitle("Simulate a lot from a Golden Cell — d4t")',
         'self.setWindowTitle("Golden Cell generator")'),
        ('"""``python -m d4t simgen`` 的進入點。"""',
         '"""``python main.py`` 的進入點。"""'),
    ],
}


def _file(mod: str) -> str:
    """模組名 → 檔案路徑（不存在就回空字串）。"""
    p = os.path.join(ROOT, mod.replace(".", "/") + ".py")
    return p if os.path.isfile(p) else ""


def deps(mod: str) -> Set[str]:
    """這一支直接 import 到的 `d4t.` 模組。

    ⚠ **`from d4t.core.algo import period` 這種要拆開看**：`d4t.core.algo` 是
    package（`__init__.py` 是空的），真正要帶走的是 `d4t.core.algo.period`。
    只看 `n.module` 的話這一支會被漏掉，而漏掉的那一支要等到跑起來才炸。
    """
    path = _file(mod)
    if not path:
        return set()
    pkg = mod.rsplit(".", 1)[0]
    out: Set[str] = set()
    for node in ast.walk(ast.parse(io.open(path, encoding="utf-8").read())):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                up = pkg
                for _ in range(node.level - 1):
                    up = up.rsplit(".", 1)[0]
                target = up + ("." + node.module if node.module else "")
            elif (node.module or "").startswith("d4t"):
                target = node.module
            else:
                continue
            if _file(target):
                out.add(target)
            else:                      # package：名字可能是它底下的模組
                for alias in node.names:
                    if _file(target + "." + alias.name):
                        out.add(target + "." + alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("d4t") and _file(alias.name):
                    out.add(alias.name)
    return out


def closure(start: str) -> List[str]:
    seen: Set[str] = set()
    todo = [start]
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        todo.extend(deps(mod))
    return sorted(seen)


def _check_assets(root_pkg: str) -> List[str]:
    """`branding.py` 名字裡寫著的每一個檔案都在嗎。

    ⚠ 少一個**不會報錯** —— `app_icon()` 的 `os.path.isfile` 會安靜地回一個
    空 `QIcon`。所以這件事要在抽取的當下就擋，不能等使用者發現「圖示不見了」。
    """
    bad = []
    brand = os.path.join(root_pkg, "ui", "branding.py")
    if not os.path.isfile(brand):
        return bad
    src = io.open(brand, encoding="utf-8").read()
    for name in re.findall(r'ASSETS_DIR,\s*"([^"]+)"', src):
        if not os.path.isfile(os.path.join(root_pkg, "ui", "assets", name)):
            bad.append(name)
    return bad


def rewrite(src: str, pkg: str) -> str:
    """把絕對的 `d4t.x.y` import 換成新 package 的相對寫法。

    相對 import（`from .theme import …`、`from ..core.algo import …`）**一個字
    都不用動** —— 因為抽出來的目錄形狀跟 `d4t/` 一樣（`ui/`、`core/`）。
    """
    out = src
    # `from d4t.core.log import swallowed` → `from ...core.log import swallowed`
    # 深度看檔案自己在哪一層，所以交給呼叫者算好的 `pkg` 名：直接用絕對名字換成
    # 新 package 的絕對名字最不容易錯。
    out = re.sub(r"\bfrom d4t\.", "from %s." % pkg, out)
    out = re.sub(r"\bimport d4t\.", "import %s." % pkg, out)
    out = re.sub(r"\bfrom d4t import\b", "from %s import" % pkg, out)
    return out


MAIN = '''"""%(title)s —— %(blurb)s

獨立的進入點：``python main.py``（或 ``python -m %(pkg)s``）。
"""
from __future__ import annotations

import sys


def main() -> int:
    from %(pkg)s.ui.%(entry)s import run
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
'''

README = '''# %(title)s

%(blurb)s

```bash
pip install -r requirements.txt
python main.py
```

## 這個資料夾是什麼

它是一個**完整、可以單獨帶走的程式** —— 整個資料夾複製到任何地方都跑得起來，
不需要 d4t。

它由 `tools/extract_app.py` 從 d4t 抽出來（%(date)s），而那是一次性的搬家：
d4t 那邊之後會把這個工具移除，所以**這裡是唯一的家**，不會有兩份要對。

## 裡面有什麼

`%(pkg)s/` 底下的目錄形狀跟 d4t 一樣，所以從 d4t 帶過來的程式碼一個字都沒改
（只有 `import d4t.…` 換成 `import %(pkg)s.…`）：

* `%(pkg)s/core/` — 純運算，**不 import Qt**
* `%(pkg)s/ui/` — 視窗與元件

共 %(n)d 支模組、%(lines)s 行。

## 相依

* Python 3.9+
* 見 `requirements.txt`

## 授權

跟 d4t 同一份（專有／內部）—— 見原 repo 的 `LICENSE`。
'''

REQS = """numpy
opencv-python
PySide6
tifffile
"""


def extract(app: str, out_dir: str) -> int:
    entry_mod, pkg, title, blurb = APPS[app]
    mods = closure(entry_mod)
    lines = sum(len(io.open(_file(m), encoding="utf-8").read().splitlines())
                for m in mods)

    out = os.path.join(ROOT, out_dir) if not os.path.isabs(out_dir) else out_dir
    if os.path.isdir(out):
        shutil.rmtree(out)
    root_pkg = os.path.join(out, pkg)

    made = set()
    renamed = set()
    for mod in mods:
        rel = mod.replace("d4t.", "", 1).replace(".", "/") + ".py"
        dst = os.path.join(root_pkg, rel)
        d = os.path.dirname(dst)
        os.makedirs(d, exist_ok=True)
        # 每一層都要有 `__init__.py`，不然它不是一個 package。
        while d != out and d not in made:
            init = os.path.join(d, "__init__.py")
            if not os.path.isfile(init):
                io.open(init, "w", encoding="utf-8").write("")
            made.add(d)
            d = os.path.dirname(d)
        text = rewrite(io.open(_file(mod), encoding="utf-8").read(), pkg)
        for was, now in RENAMES.get(app, []):
            if was in text:
                text = text.replace(was, now)
                renamed.add(was.split("=")[0].strip()[:40] or was[:40])
        io.open(dst, "w", encoding="utf-8").write(text)

    for src_rel, dst_rel in ASSETS.get(app, []):
        dst = os.path.join(root_pkg, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, src_rel), dst)

    import datetime
    fields = {"title": title, "blurb": blurb, "pkg": pkg,
              "entry": entry_mod.rsplit(".", 1)[-1], "n": len(mods),
              "lines": "{:,}".format(lines),
              "date": datetime.date.today().isoformat()}
    io.open(os.path.join(out, "main.py"), "w", encoding="utf-8").write(MAIN % fields)
    io.open(os.path.join(out, "README.md"), "w", encoding="utf-8").write(README % fields)
    io.open(os.path.join(out, "requirements.txt"), "w", encoding="utf-8").write(REQS)
    io.open(os.path.join(root_pkg, "__main__.py"), "w", encoding="utf-8").write(
        MAIN % fields)

    missing = _check_assets(root_pkg)
    if missing:
        print("✗ %s：`branding.py` 指名的這幾個檔案沒被複製：%s\n"
              "   把它們加進 `ASSETS`，不然帶走的那份會安靜地少一個圖示。"
              % (app, ", ".join(missing)), file=sys.stderr)
        return 1
    want = {w for w, _ in RENAMES.get(app, [])}
    if len(renamed) != len(want):
        print("✗ %s：`RENAMES` 有 %d 條，只套用了 %d 條 —— 來源改過了，"
              "那張表要跟著改（不然帶走的那份會留著一句假話）。"
              % (app, len(want), len(renamed)), file=sys.stderr)
        return 1
    print("✓ %s → %s（%d 支模組、%s 行，換掉 %d 句 d4t 專屬的字）"
          % (app, out_dir, len(mods), fields["lines"], len(renamed)))
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("app", nargs="?", choices=sorted(APPS))
    ap.add_argument("out", nargs="?")
    ap.add_argument("--list", action="store_true", help="列出抽得出來的工具")
    args = ap.parse_args(argv)
    if args.list or not args.app:
        for name, (mod, _pkg, title, blurb) in sorted(APPS.items()):
            mods = closure(mod)
            print("%-8s %-26s %2d 支  %s" % (name, title, len(mods), blurb))
        return 0
    if not args.out:
        ap.error("要給輸出資料夾，例如 apps/%s" % args.app)
    return extract(args.app, args.out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
