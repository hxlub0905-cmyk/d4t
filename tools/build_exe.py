#!/usr/bin/env python3
# d4t exe 打包 — authored 2026-10-02 (F125).
"""把 d4t 包成 Windows 執行檔：**資料夾版**（onedir）或**單檔版**（onefile）。

    python tools/build_exe.py                 # 會問你要哪一種（1 = 資料夾、2 = 單檔）
    python tools/build_exe.py --onedir        # 資料夾版：dist\\d4t\\（建議）
    python tools/build_exe.py --onefile       # 單檔版：dist\\d4t.exe + dist\\d4t-studio.exe
    python tools/build_exe.py --dry-run       # 只印它會做什麼，不建任何東西

兩種模式都產**兩個**執行檔（2026-10-02 使用者定的）：

* ``d4t-studio.exe`` —— 雙擊開 Studio，沒有黑色的命令列視窗。
* ``d4t.exe`` —— 命令列：``d4t.exe run RECIPE KLARF …``、``d4t.exe steps``、
  ``d4t.exe --version``（印的 build id 跟 ``python -m d4t --version`` 同一個數）。

資料夾版兩個 exe 共用同一份 ``_internal\\``（Qt 只放一份）；單檔版各帶一份，所以
兩個檔案各約 Qt＋numpy＋cv2 的大小。**預設建議資料夾版**。白話說明、怎麼搬進
公司機、單檔版要注意的三件事：`docs/BUILD-EXE.md`。

⚠ **這支是給家用機的**（`AGENTS.md` §4.5）：要 pip 裝得到 ``pyinstaller``。exe 是
二進位，不能走剪貼簿、不進 repo 也不進 bundle（``dist/`` 與 ``build/`` 在
``.gitignore``）；帶進公司機的路跟 ``wheels\\`` 一樣。公司機若有內部 PyPI 鏡像裝得
到 pyinstaller，在那裡建也行 —— 這支本身 stdlib-only，PyInstaller 用子行程叫。

這個檔案同時是**打包清單的唯一出處**：要包哪些非程式碼的檔案（:data:`DATAS`）、
PyInstaller 看不到的 import（:data:`HIDDEN_IMPORTS`）、不要帶的 Qt 模組
（:data:`EXCLUDES`）、兩個 exe 的名字（:data:`EXE_NAMES`）都在這裡；
``tools/exe/d4t.spec`` import 這一支拿清單，``tests/test_build_exe.py`` 逐條驗
「清單上的檔案真的在」。寫兩份一定會漂（`CLAUDE.md` §0 那句話）。

為什麼 datas 的目的地要**鏡射 repo 的版面**：PyInstaller 把模組的 ``__file__``
設成 ``<_MEIPASS>/d4t/ui/studio.pyc``，所以程式裡所有
``Path(__file__).parents[2] / "recipes"`` 這種寫法在 exe 裡會指到
``<_MEIPASS>/recipes`` —— 只要 ``recipes/`` 放在那裡，**一行程式都不用改**
（範本庫、「用範例資料試一次」、手冊、build id、圖示、翻譯檔全部如此）。
``d4t.exe --version`` 印出真的 build id（不是 ``unknown``）就是這件事成立的證據，
所以冒煙測試一定看它。
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

MODES: Tuple[str, ...] = ("onedir", "onefile")
DEFAULT_MODE = "onedir"

#: 兩個執行檔的名字（不含 ``.exe``）。``cli`` 有 console，``gui`` 沒有。
EXE_NAMES: Dict[str, str] = {"cli": "d4t", "gui": "d4t-studio"}
#: 資料夾版那個資料夾的名字：``dist/d4t/``。
COLLECT_NAME = "d4t"

#: PyInstaller 的進入腳本（相對 repo 根）。launcher 第一句一定是
#: ``multiprocessing.freeze_support()`` —— 少了它，exe 裡 ``--workers N`` 會開 N 個
#: Studio（Windows 的 spawn 是重跑這個 exe）。``tests/test_build_exe.py`` 用 ast 守。
LAUNCHERS: Dict[str, str] = {
    "cli": os.path.join("tools", "exe", "launch_cli.py"),
    "gui": os.path.join("tools", "exe", "launch_studio.py"),
}
SPEC = os.path.join("tools", "exe", "d4t.spec")
ICON_MAKER = os.path.join("tools", "exe", "make_icon.py")
ICON_SVG = os.path.join("d4t", "ui", "assets", "d4t.svg")

#: 要包進去的非程式碼檔案：``(glob，相對 repo 根, 目的地資料夾)``。
#: 目的地一律**鏡射 repo 的版面**（見模組說明）。
DATAS: Tuple[Tuple[str, str], ...] = (
    # 範本庫（Templates…）與「用範例資料試一次」那份 recipe
    ("recipes/*.json", "recipes"),
    ("recipes/README.md", "recipes"),
    # 卡片上的手冊連結（`ui/manual.py`）；快速參考卡 PDF 有的話一起帶
    ("docs/USING-*.md", "docs"),
    ("docs/*.pdf", "docs"),
    # 「用範例資料試一次」（`studio.generate_demo_lot`）與 simgen 視窗的後端 ——
    # 它們在執行時 import `tools/` 底下的這幾支，連同它們互相 import 的那兩支
    ("tools/make_sample.py", "tools"),
    ("tools/make_sample_rsem.py", "tools"),
    ("tools/_synth.py", "tools"),
    ("tools/_synth_mgepi.py", "tools"),
    ("tools/make_lot_from_gc.py", "tools"),
    ("tools/show_template.py", "tools"),       # make_lot_from_gc 的 PNG 寫出走它
    # build id（`d4t.build_id()` 讀它；`--version` 印的就是這個數）
    ("tools/FILELIST.txt", "tools"),
    # 圖示與翻譯檔（套件內的資料，pip 的 package-data 同一批）
    ("d4t/ui/assets/*.svg", os.path.join("d4t", "ui", "assets")),
    ("d4t/ui/locales/*.json", os.path.join("d4t", "ui", "locales")),
    # 授權跟著二進位走（`docs/LICENSING.md` 的 LGPL 那一段）
    ("LICENSE", "."),
    ("docs/LICENSING.md", "docs"),
)
#: 這幾個 pattern **可以**一個都沒配到（例：repo 裡目前沒有 PDF）。
OPTIONAL_DATAS: Tuple[str, ...] = ("docs/*.pdf",)

#: PyInstaller 的靜態掃描看不到的 import。
HIDDEN_IMPORTS: Tuple[str, ...] = (
    # `steps/roi_reference.py` 用 importlib 按 method 名字載入這兩支
    "d4t.core.steps.roi_cross",
    "d4t.core.steps.roi_template",
    # SVG 圖示要 Qt 的 svg icon engine plugin —— 列了 QtSvg 它才會被收進來
    "PySide6.QtSvg",
    # 函式內 lazy import 的兩個（靜態看得到，列著是便宜的保險）
    "openpyxl",
    "tifffile",
)

#: 不要帶的東西。d4t 只用 QtWidgets／QtCore／QtGui／QtSvg；PySide6 的 wheel 裡其他
#: 幾十個模組（WebEngine 一個就上百 MB）一個都用不到。**不要排 QtSvg、QtNetwork**。
EXCLUDES: Tuple[str, ...] = (
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtLocation", "PySide6.QtPositioning",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtWebView",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtSpatialAudio", "PySide6.QtHttpServer", "PySide6.QtNetworkAuth",
    "PySide6.QtAsyncio",
    # 不是 d4t 的相依，但常常裝在同一個環境裡被順手掃進來
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "PyQt5", "PyQt6",
)

OK, WARN, BAD = "✓", "△", "✗"


# --------------------------------------------------------------------------- #
# 純函式（測試直接叫）
# --------------------------------------------------------------------------- #
def repo_root() -> str:
    """這支檔案在 ``<repo>/tools/``。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exe_suffix(platform: Optional[str] = None) -> str:
    return ".exe" if (platform or sys.platform).startswith("win") else ""


def expand_datas(root: str) -> List[Tuple[str, str]]:
    """:data:`DATAS` 的 glob 展開成 PyInstaller 要的 ``(絕對來源, 目的地)``。"""
    out: List[Tuple[str, str]] = []
    for pattern, dest in DATAS:
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            if os.path.isfile(path):
                out.append((path, dest))
    return out


def missing_datas(root: str) -> List[str]:
    """一個檔案都沒配到、而且不在 :data:`OPTIONAL_DATAS` 裡的 pattern。"""
    missing = []
    for pattern, _dest in DATAS:
        if pattern in OPTIONAL_DATAS:
            continue
        if not any(os.path.isfile(p) for p in glob.glob(os.path.join(root, pattern))):
            missing.append(pattern)
    return missing


def pyinstaller_command(python: str, spec: str, distpath: str, workpath: str,
                        clean: bool = False) -> List[str]:
    """叫 PyInstaller 的那一行。spec 一定在最後；模式走環境變數（``pyinstaller
    某某.spec`` 會**忽略** ``--onefile``，所以不能用旗標傳）。"""
    cmd = [python, "-m", "PyInstaller", "--noconfirm"]
    if clean:
        cmd.append("--clean")
    cmd += ["--distpath", distpath, "--workpath", workpath, spec]
    return cmd


def env_for(mode: str, root: str, icon: Optional[str],
            base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """spec 讀的三個環境變數。"""
    if mode not in MODES:
        raise ValueError("mode must be one of %s, not %r" % (MODES, mode))
    env = dict(os.environ if base is None else base)
    env["D4T_EXE_MODE"] = mode
    env["D4T_EXE_ROOT"] = root
    env["D4T_EXE_ICON"] = icon or ""
    return env


def expected_outputs(mode: str, distpath: str,
                     platform: Optional[str] = None) -> Dict[str, str]:
    """建完之後 ``{"cli": 路徑, "gui": 路徑}`` 應該在哪。"""
    sfx = exe_suffix(platform)
    if mode == "onedir":
        base = os.path.join(distpath, COLLECT_NAME)
    elif mode == "onefile":
        base = distpath
    else:
        raise ValueError("mode must be one of %s, not %r" % (MODES, mode))
    return {kind: os.path.join(base, name + sfx) for kind, name in EXE_NAMES.items()}


def smoke_commands(exe_cli: str) -> List[List[str]]:
    """建完拿 CLI 那個 exe 跑的兩句話：版本（證明 FILELIST 包到了）、卡片清單
    （證明 numpy／cv2／tifffile 在 frozen 下 import 得起來）。"""
    return [[exe_cli, "--version"], [exe_cli, "steps"]]


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return ("%d %s" % (size, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024.0
    return "%d B" % n


def folder_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def pyinstaller_version(python: str) -> Optional[str]:
    """裝了就回版本字串，沒裝回 ``None``。用子行程問 —— 這支自己不 import 它。"""
    try:
        proc = subprocess.run([python, "-m", "PyInstaller", "--version"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or "?"


def explain_missing_pyinstaller() -> List[str]:
    return [
        "%s 這台機器沒有 PyInstaller（打包用的工具）。" % BAD,
        "   裝法：  pip install pyinstaller",
        "   公司機走內部鏡像的話：  pip install --index-url <內部鏡像站>/simple pyinstaller",
        "   （鏡像站網址請問 IT；它是開發用的工具，不會進到任何一條搬運路徑。）",
    ]


def version_info(root: str) -> Tuple[str, str]:
    """``(版本, build id)`` —— 從 repo 裡的 ``d4t`` 讀（它的 ``__init__`` 不吃任何
    第三方套件，所以這裡 import 它是安全的）。"""
    if root not in sys.path:
        sys.path.insert(0, root)
    import d4t  # 只讀 __version__ 與 build_id，不碰 core

    return d4t.__version__, d4t.build_id()


def preflight(root: str, python: str, platform: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """``(擋下來的問題, 只是提醒)`` —— 每一條都是一句話加怎麼修。"""
    bad: List[str] = []
    warn: List[str] = []
    for rel in ("pyproject.toml", os.path.join("d4t", "__init__.py"), SPEC,
                LAUNCHERS["cli"], LAUNCHERS["gui"]):
        if not os.path.isfile(os.path.join(root, rel)):
            bad.append("%s 找不到 %s —— 請在 d4t 的 repo 根目錄跑這支（dir 要看得到 d4t、tools）。"
                       % (BAD, rel))
    if not os.path.isfile(os.path.join(root, "tools", "FILELIST.txt")):
        bad.append("%s tools/FILELIST.txt 不在 —— 沒有它 exe 的 --version 會印 unknown。\n"
                   "   家用機先跑：  git add -A && python tools/release.py && git add -A" % BAD)
    missing = missing_datas(root)
    if missing:
        bad.append("%s 清單上要包的檔案找不到：%s（build_exe.py 的 DATAS 跟 repo 不一致）"
                   % (BAD, "、".join(missing)))
    for mod, pip_name in (("numpy", "numpy"), ("cv2", "opencv-python"),
                          ("tifffile", "tifffile"), ("openpyxl", "openpyxl"),
                          ("PySide6", "PySide6")):
        if importlib.util.find_spec(mod) is None:
            bad.append("%s 這個 Python 環境沒有 %s —— 先裝：  pip install -r requirements.txt"
                       % (BAD, pip_name))
    if pyinstaller_version(python) is None:
        bad.extend(explain_missing_pyinstaller())
    if not (platform or sys.platform).startswith("win"):
        warn.append("%s 這台不是 Windows：產出只能在這台上跑。給廠內的 .exe 要在 Windows 上做"
                    "（或交給 GitHub Actions 的 exe workflow）。" % WARN)
    return bad, warn


# --------------------------------------------------------------------------- #
# 流程
# --------------------------------------------------------------------------- #
def _say(*parts: object) -> None:
    print(*parts)
    sys.stdout.flush()


def choose_mode(args: argparse.Namespace) -> str:
    """旗標 → 模式；都沒給就問（不是 tty 或 ``--no-prompt`` 就用預設）。"""
    if args.onefile:
        return "onefile"
    if args.onedir:
        return "onedir"
    if args.no_prompt or not sys.stdin or not sys.stdin.isatty():
        return DEFAULT_MODE
    _say("要包成哪一種？")
    _say("  1 = 資料夾（建議）：dist\\d4t\\ 裡兩個 exe 共用一份程式庫，啟動快、體積小")
    _say("  2 = 單檔：dist\\d4t.exe 與 dist\\d4t-studio.exe 各自一個檔，複製方便，但啟動慢、各帶一份程式庫")
    while True:
        try:
            ans = input("輸入 1 或 2（直接 Enter = 1）：").strip()
        except EOFError:
            return DEFAULT_MODE
        if ans in ("", "1"):
            return "onedir"
        if ans == "2":
            return "onefile"
        _say("請輸入 1 或 2。")


def make_icon(root: str, python: str, workpath: str) -> Optional[str]:
    """SVG → ICO（用 Qt 畫，子行程）。失敗就回 ``None``，exe 用預設圖示，不擋打包。"""
    out = os.path.join(workpath, "d4t.ico")
    os.makedirs(workpath, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        proc = subprocess.run([python, os.path.join(root, ICON_MAKER),
                               os.path.join(root, ICON_SVG), out],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, env=env, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        _say("%s 圖示沒做出來（%s）—— exe 會用預設圖示，其他不受影響。" % (WARN, exc))
        return None
    if proc.returncode != 0 or not os.path.isfile(out):
        tail = (proc.stdout or "").strip().splitlines()[-1:] or ["?"]
        _say("%s 圖示沒做出來（%s）—— exe 會用預設圖示，其他不受影響。" % (WARN, tail[0]))
        return None
    return out


def run_smoke(exe_cli: str, build: str) -> bool:
    """跑 :func:`smoke_commands`；``--version`` 要含 build id，``steps`` 要列得出卡片。"""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    ok = True
    for cmd in smoke_commands(exe_cli):
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  universal_newlines=True, env=env, timeout=600,
                                  encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as exc:
            _say("%s 冒煙失敗：%s → %s" % (BAD, " ".join(cmd[1:]), exc))
            ok = False
            continue
        text = proc.stdout or ""
        what = cmd[1]
        if proc.returncode != 0:
            _say("%s 冒煙失敗：exe %s 回 %d\n%s" % (BAD, what, proc.returncode, text[-2000:]))
            ok = False
        elif what == "--version" and build not in text:
            _say("%s exe --version 印的是「%s」，裡面沒有 build %s —— tools/FILELIST.txt 沒包到。"
                 % (BAD, text.strip(), build))
            ok = False
        elif what == "steps" and "load_patch" not in text:
            _say("%s exe steps 沒有列出卡片（輸出尾端：%s）" % (BAD, text.strip()[-300:]))
            ok = False
        else:
            first = text.strip().splitlines()[0] if text.strip() else ""
            _say("%s exe %s → %s" % (OK, what, first[:100]))
    return ok


def summary(mode: str, outputs: Dict[str, str], distpath: str) -> None:
    _say("")
    _say("=" * 64)
    if mode == "onedir":
        folder = os.path.join(distpath, COLLECT_NAME)
        _say("完成：資料夾版在  %s  （%s）" % (os.path.abspath(folder), human_size(folder_size(folder))))
        _say("  雙擊  %s  開 Studio" % os.path.basename(outputs["gui"]))
        _say("  命令列：  %s run RECIPE.json LOT.001 --csv out.csv" % os.path.basename(outputs["cli"]))
        _say("  要搬去別台機器請**整個資料夾**一起複製（_internal\\ 不能少）。")
    else:
        _say("完成：單檔版")
        for kind in ("gui", "cli"):
            p = outputs[kind]
            _say("  %s  （%s）" % (os.path.abspath(p), human_size(folder_size(p))))
        _say("  第一次啟動會先把自己解壓到 %TEMP%，比資料夾版慢；防毒軟體對這種檔案也比較敏感。")
    _say("  版本回報：  %s --version" % os.path.basename(outputs["cli"]))
    _say("  怎麼搬進公司機、SmartScreen 擋下來怎麼辦：docs/BUILD-EXE.md")
    _say("=" * 64)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="build_exe.py",
        description="把 d4t 包成 Windows 執行檔（資料夾版或單檔版，各含 d4t.exe 與 d4t-studio.exe）。")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--onedir", action="store_true", help="資料夾版：dist/d4t/（建議）")
    mode.add_argument("--onefile", action="store_true", help="單檔版：dist/d4t.exe 與 dist/d4t-studio.exe")
    ap.add_argument("--no-prompt", action="store_true",
                    help="沒給 --onedir/--onefile 時不要問，直接用資料夾版（CI 用）")
    ap.add_argument("--dist", default="dist", help="產出放哪（預設 dist）")
    ap.add_argument("--work", default=os.path.join("build", "exe"),
                    help="PyInstaller 的工作目錄（預設 build/exe）")
    ap.add_argument("--clean", action="store_true", help="先清掉上一次的產出與工作目錄")
    ap.add_argument("--no-icon", action="store_true", help="不做圖示（省幾秒；exe 用預設圖示）")
    ap.add_argument("--no-smoke", action="store_true", help="建完不跑 exe 驗證")
    ap.add_argument("--dry-run", action="store_true", help="只印會執行的指令與預期產出，不建任何東西")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # cp950 的 console 印得出 ✓✗△
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    root = repo_root()
    python = sys.executable
    mode = choose_mode(args)
    distpath = os.path.abspath(args.dist)
    workpath = os.path.abspath(args.work)

    bad, warn = preflight(root, python)
    for line in warn:
        _say(line)
    if bad and not args.dry_run:
        for line in bad:
            _say(line)
        _say("\n結論：還不能打包，先修上面 %d 件。" % len(bad))
        return 2

    try:
        version, build = version_info(root)
    except Exception as exc:  # 沒有 d4t 可讀就是跑錯地方
        _say("%s 讀不到 d4t 的版本（%s）—— 請在 repo 根目錄跑。" % (BAD, exc))
        return 2
    _say("打包的是：d4t %s (build %s)，模式：%s" % (version, build, mode))

    outputs = expected_outputs(mode, distpath)
    cmd = pyinstaller_command(python, os.path.join(root, SPEC), distpath, workpath, clean=args.clean)
    if args.dry_run:
        env = env_for(mode, root, None, base={})
        _say("[dry-run] 會執行：  " + " ".join(cmd))
        _say("[dry-run] 環境變數：  " + "  ".join("%s=%s" % kv for kv in sorted(env.items())))
        _say("[dry-run] 會包進去的檔案：%d 個" % len(expand_datas(root)))
        for kind, path in outputs.items():
            _say("[dry-run] 預期產出（%s）：%s" % (kind, path))
        if bad:
            for line in bad:
                _say("[dry-run] 真的跑的話會被擋下來：" + line.replace("\n", " "))
        return 0

    if args.clean:
        for target in (os.path.join(distpath, COLLECT_NAME), workpath, *outputs.values()):
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.isfile(target):
                os.remove(target)

    icon = None if args.no_icon else make_icon(root, python, workpath)
    if icon:
        _say("%s 圖示：%s" % (OK, icon))

    _say("%s PyInstaller %s …（第一次要幾分鐘）" % (OK, pyinstaller_version(python)))
    proc = subprocess.run(cmd, env=env_for(mode, root, icon), cwd=root)
    if proc.returncode != 0:
        _say("\n%s PyInstaller 失敗（回 %d）。往上找第一個 ERROR 那一行；常見的是某個套件沒裝、"
             "或防毒把 build/ 裡的檔案鎖住了。" % (BAD, proc.returncode))
        return 1

    missing = [p for p in outputs.values() if not os.path.isfile(p)]
    if missing:
        _say("%s PyInstaller 跑完了，但這些檔案不在：%s" % (BAD, "、".join(missing)))
        return 1
    for kind, path in outputs.items():
        _say("%s 產出（%s）：%s" % (OK, kind, path))

    if not args.no_smoke:
        if not run_smoke(outputs["cli"], build):
            _say("\n結論：exe 建出來了但驗證沒過，不要拿去用。")
            return 1

    summary(mode, outputs, distpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
