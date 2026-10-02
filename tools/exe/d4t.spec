# -*- mode: python ; coding: utf-8 -*-
# d4t 的 PyInstaller spec — authored 2026-10-02 (F125).
#
# **不要直接叫 `pyinstaller tools/exe/d4t.spec`**，請跑 `python tools/build_exe.py`：
# 它負責 preflight、圖示、冒煙與白話摘要，而且模式是走環境變數進來的 ——
# `pyinstaller 某某.spec` 會**忽略** `--onefile`，所以這裡讀 `D4T_EXE_MODE`。
#
# 這個檔案裡沒有清單：要包哪些檔案、hidden imports、要排掉的 Qt 模組、兩個 exe 的
# 名字全部住在 `tools/build_exe.py`（唯一出處，測試逐條驗檔案存在）。這裡只做
# PyInstaller 自己的那三件事：Analysis → PYZ → EXE（＋ 資料夾版的 COLLECT）。
#
# 兩個 exe：
#   d4t.exe         console=True   命令列（run / steps / validate / --version …）
#   d4t-studio.exe  console=False  雙擊開 Studio，沒有黑視窗
#
# 資料夾版：兩個 EXE(exclude_binaries=True) 丟進**同一個** COLLECT —— Qt 的 DLL
# 只有一份（COLLECT 會把兩份 Analysis 的 TOC 合併去重）。
# 單檔版：兩個各自自含的 EXE，同一個 spec 一次跑完。刻意不用 MERGE（多包共用）——
# 它在 PyInstaller 6 上脆弱，而資料夾版已經是「共用一份」的答案。
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

_SPEC_DIR = Path(SPECPATH)                       # <repo>/tools/exe  （PyInstaller 給的全域）
_TOOLS = _SPEC_DIR.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import build_exe as cfg                          # noqa: E402

ROOT = Path(os.environ.get("D4T_EXE_ROOT") or _TOOLS.parent)
MODE = os.environ.get("D4T_EXE_MODE", cfg.DEFAULT_MODE)
if MODE not in cfg.MODES:
    raise SystemExit("D4T_EXE_MODE must be one of %s, not %r" % (cfg.MODES, MODE))
_icon = os.environ.get("D4T_EXE_ICON") or ""
ICON = _icon if os.path.isfile(_icon) else None

DATAS = cfg.expand_datas(str(ROOT))
# 卡片模組之後若再有「按名字 importlib」的方法實作，整個 steps 套件都在就不會漏
HIDDEN = sorted(set(cfg.HIDDEN_IMPORTS) | set(collect_submodules("d4t.core.steps")))
EXCLUDES = list(cfg.EXCLUDES)


def analyse(script_rel: str):
    return Analysis(
        [str(ROOT / script_rel)],
        pathex=[str(ROOT)],
        binaries=[],
        datas=DATAS,
        hiddenimports=HIDDEN,
        hookspath=[],
        runtime_hooks=[],
        excludes=EXCLUDES,
        noarchive=False,
    )


a_cli = analyse(cfg.LAUNCHERS["cli"])
a_gui = analyse(cfg.LAUNCHERS["gui"])
pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)

if MODE == "onedir":
    exe_cli = EXE(
        pyz_cli, a_cli.scripts, [],
        exclude_binaries=True,
        name=cfg.EXE_NAMES["cli"],
        console=True,
        debug=False, strip=False, upx=False,
        icon=ICON,
    )
    exe_gui = EXE(
        pyz_gui, a_gui.scripts, [],
        exclude_binaries=True,
        name=cfg.EXE_NAMES["gui"],
        console=False,
        debug=False, strip=False, upx=False,
        icon=ICON,
    )
    COLLECT(
        exe_cli, exe_gui,
        a_cli.binaries, a_cli.datas,
        a_gui.binaries, a_gui.datas,
        strip=False, upx=False,
        name=cfg.COLLECT_NAME,
    )
else:
    EXE(
        pyz_cli, a_cli.scripts, a_cli.binaries, a_cli.datas, [],
        name=cfg.EXE_NAMES["cli"],
        console=True,
        debug=False, strip=False, upx=False,
        icon=ICON,
    )
    EXE(
        pyz_gui, a_gui.scripts, a_gui.binaries, a_gui.datas, [],
        name=cfg.EXE_NAMES["gui"],
        console=False,
        debug=False, strip=False, upx=False,
        icon=ICON,
    )
