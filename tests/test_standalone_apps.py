"""`apps/` 底下那兩個**可以帶走的資料夾** —— 它們真的帶得走嗎（F120，2026-09-23）。

使用者 2026-09-23：「請幫我將這個 pitch helper 獨立成一個資料夾」＋「我之後帶走
後 d4t 會把 pitch helper 移除，就等於 pitch helper 直接開新 repo，原來 d4t 不會
有殘留」。

⚠ **這個檔案要 Qt，所以檔名是 `test_ui_*`？不是** —— 它大部分只讀檔案與跑
`ast`，唯一要 Qt 的那一條自己 `importorskip`。核心批在沒有 Qt 的機器上也要綠。

守的是**帶走那一刻會安靜做錯的三件事**：

1. **漏一支模組** —— 資料夾複製出去、`import` 過、視窗開得起來，然後在一條
   沒有人走過的路上 `ModuleNotFoundError`。
2. **偷偷回頭吃 d4t** —— 在開發機上跑得動（因為 `d4t` 還裝著），到了別人手上才炸。
3. **留著一句假話** —— 指向 d4t Studio 的指路、掛著 `d4t` 的視窗標題。
   「一句寫了找不到的東西的指路，比不寫還糟」（F120 §27 為這件事付過一次錢）。
"""
from __future__ import annotations

import ast
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = ("pitch", "simgen")


def _pkg(app: str) -> str:
    """`apps/<app>/` 底下那個 package 的路徑。"""
    base = os.path.join(ROOT, "apps", app)
    names = [n for n in sorted(os.listdir(base))
             if os.path.isdir(os.path.join(base, n)) and n.endswith("app")]
    assert len(names) == 1, (app, names)
    return os.path.join(base, names[0])


def _py_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


@pytest.mark.parametrize("app", APPS)
def test_the_folder_has_what_it_takes_to_be_a_repo(app):
    """一個可以 `git init` 的資料夾：進入點、說明、相依。"""
    base = os.path.join(ROOT, "apps", app)
    for name in ("main.py", "README.md", "requirements.txt"):
        assert os.path.isfile(os.path.join(base, name)), (app, name)
    assert os.path.isfile(os.path.join(_pkg(app), "__main__.py"))


@pytest.mark.parametrize("app", APPS)
def test_nothing_in_there_imports_d4t(app):
    """⚠ **在開發機上跑得動不算數。**

    這台機器裝著 d4t（`pip install -e .`），所以一支漏改的 `import d4t.…`
    在這裡完全正常 —— 到了別人手上才炸。所以用 `ast` 掃，不靠跑跑看。
    """
    bad = []
    for path in _py_files(_pkg(app)):
        for node in ast.walk(ast.parse(io.open(path, encoding="utf-8").read())):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("d4t"):
                bad.append((os.path.relpath(path, ROOT), node.lineno, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("d4t"):
                        bad.append((os.path.relpath(path, ROOT), node.lineno,
                                    alias.name))
    assert not bad, bad


@pytest.mark.parametrize("app", APPS)
def test_every_module_it_imports_is_actually_in_there(app):
    """⚠ **漏一支不會在 import 的時候炸。**

    `from .crop_dialog import …` 少了那一支，`import` 整個 package 仍然過 ——
    要等到使用者按下 Crop 才 `ModuleNotFoundError`。所以逐檔把相對 import 解出來
    對一次。
    """
    pkg = _pkg(app)
    pkg_name = os.path.basename(pkg)
    have = set()
    for path in _py_files(pkg):
        rel = os.path.relpath(path, os.path.dirname(pkg))[:-3].replace(os.sep, ".")
        have.add(rel)
    missing = []
    for path in _py_files(pkg):
        rel = os.path.relpath(path, os.path.dirname(pkg))[:-3].replace(os.sep, ".")
        here = rel.rsplit(".", 1)[0]
        for node in ast.walk(ast.parse(io.open(path, encoding="utf-8").read())):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            up = here
            for _ in range(node.level - 1):
                up = up.rsplit(".", 1)[0]
            target = up + ("." + node.module if node.module else "")
            if target in have or target == pkg_name:
                continue
            # package：名字可能是它底下的模組
            for alias in node.names:
                if target + "." + alias.name not in have:
                    missing.append((os.path.relpath(path, ROOT), node.lineno,
                                    target + "." + alias.name))
    assert not missing, missing


@pytest.mark.parametrize("app", APPS)
def test_no_sentence_points_at_something_that_will_not_exist(app):
    """⚠ 指向 d4t Studio 的指路、掛著主程式名字的視窗標題 —— 在新的 repo 裡
    是假話。**一句寫了找不到的東西的指路，比不寫還糟。**"""
    bad = []
    for path in _py_files(_pkg(app)):
        for i, line in enumerate(io.open(path, encoding="utf-8"), 1):
            if line.lstrip().startswith("#") or "d4t" not in line:
                continue
            if "setWindowTitle(" in line or "NEXT_STEP" in line:
                bad.append((os.path.relpath(path, ROOT), i, line.strip()[:70]))
            if "python -m d4t" in line and '"""' in line:
                bad.append((os.path.relpath(path, ROOT), i, line.strip()[:70]))
    assert not bad, bad


@pytest.mark.parametrize("app", APPS)
def test_the_asset_files_it_names_are_all_there(app):
    """⚠ 少一個**不會報錯** —— `app_icon()` 的 `os.path.isfile` 會安靜地回一個
    空 `QIcon`，畫面上只是「沒有圖示」。"""
    import re

    brand = os.path.join(_pkg(app), "ui", "branding.py")
    if not os.path.isfile(brand):
        pytest.skip("這個 app 不用 branding")
    src = io.open(brand, encoding="utf-8").read()
    names = re.findall(r'ASSETS_DIR,\s*"([^"]+)"', src)
    assert names, "branding 裡沒有任何資產名字？那這一條要重寫"
    for name in names:
        assert os.path.isfile(
            os.path.join(_pkg(app), "ui", "assets", name)), (app, name)


@pytest.mark.parametrize("app,module,window", [
    ("pitch", "pitch_helper", "PitchHelperWindow"),
    ("simgen", "gc_generator", "GcGeneratorWindow"),
])
def test_it_opens_without_d4t_on_the_path(app, module, window):
    """⚠ **真的擋掉 `d4t` 再開一次。**

    上面那幾條是靜態的；這一條是動態的最後一關 —— 裝一個 meta path hook 讓任何
    `import d4t…` 直接炸，然後把視窗開起來。這台機器裝著 d4t，不擋的話這一條
    永遠是綠的，而它守的就是「到了別人手上才炸」。
    """
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import subprocess
    import sys

    pkg = os.path.basename(_pkg(app))
    code = (
        "import sys\n"
        "class B:\n"
        "    def find_module(self, name, path=None):\n"
        "        return self if name == 'd4t' or name.startswith('d4t.') else None\n"
        "    def load_module(self, name):\n"
        "        raise ImportError(name)\n"
        "sys.meta_path.insert(0, B())\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from %s.ui import theme\n"
        "theme.apply_theme(app)\n"
        "from %s.ui.%s import %s as W\n"
        "w = W(); w.resize(900, 600)\n"
        "assert 'd4t' not in w.windowTitle(), w.windowTitle()\n"
        "assert not [k for k in sys.modules if k.startswith('d4t')]\n"
        "w.close()\n"
        "print('ok', w.windowTitle())\n" % (pkg, pkg, module, window))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH="")
    out = subprocess.run([sys.executable, "-c", code],
                         cwd=os.path.join(ROOT, "apps", app),
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.startswith("ok "), out.stdout
