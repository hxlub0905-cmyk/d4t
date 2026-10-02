"""`tools/build_exe.py` ＋ `tools/exe/`（F125：把 d4t 包成 exe）。

這裡**不跑 PyInstaller**（幾分鐘、要裝、產出幾百 MB）；真的建一次的那條在最後，
要設 ``D4T_RUN_PYINSTALLER=1`` 才跑。其餘守的是「不跑也能壞」的那幾件：

* 清單上的每個檔案真的在 repo 裡（改名一份 USING 文件、搬走 make_sample 就會紅）；
* 兩支 launcher 與兩個進入點的 ``__main__`` 守衛都叫了 ``multiprocessing.freeze_support()``
  —— 少了它的症狀是 exe 裡 ``--workers 4`` 開出四個 Studio，而那只在 Windows 的
  exe 上看得到，沒有測試就沒有人會在家用機上發現；
* spec 是 3.9 吃得下的 Python、兩個 exe 的名字與 console 旗標都在；
* ``--dry-run`` 不建任何東西；沒裝 PyInstaller 時是一句話加 pip 指令，不是 traceback。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import build_exe  # noqa: E402

SPEC = os.path.join(REPO, build_exe.SPEC)


def _module_body_without_docstring(path):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    return body


def _is_freeze_support_call(node) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Attribute) and func.attr == "freeze_support"


# ---------------------------------------------------------------- 清單

def test_every_data_pattern_matches_a_real_file():
    missing = build_exe.missing_datas(REPO)
    assert not missing, "build_exe.DATAS 裡這些 pattern 在 repo 裡一個檔案都沒配到：%s" % missing


def test_expanded_datas_exist_and_mirror_the_repo_layout():
    datas = build_exe.expand_datas(REPO)
    assert datas, "清單展開是空的"
    for src, dest in datas:
        assert os.path.isfile(src), src
        rel = os.path.relpath(src, REPO).replace(os.sep, "/")
        # 目的地要鏡射 repo 版面：程式用 parents[2] 找資料，放錯地方 exe 就找不到
        expected = os.path.dirname(rel) or "."
        assert dest.replace(os.sep, "/") == expected, (rel, dest, expected)


@pytest.mark.parametrize("rel", [
    "tools/make_sample.py", "tools/make_sample_rsem.py", "tools/_synth.py",
    "tools/_synth_mgepi.py", "tools/make_lot_from_gc.py", "tools/FILELIST.txt",
    "recipes/ebi-die-to-die.json", "d4t/ui/locales/zh_TW.json", "d4t/ui/assets/d4t.svg",
    "LICENSE",
])
def test_the_things_the_running_program_opens_are_on_the_list(rel):
    """Studio 在執行時 import／讀的那幾個檔案（`studio.generate_demo_lot`、
    `gc_generator.load_backend`、`d4t.build_id`、範本庫、翻譯、圖示）。"""
    srcs = {os.path.relpath(s, REPO).replace(os.sep, "/") for s, _d in build_exe.expand_datas(REPO)}
    assert rel in srcs, "%s 不在打包清單裡" % rel


def test_the_sample_makers_dependencies_are_all_bundled():
    """`make_sample.py` import `_synth_mgepi`、`make_lot_from_gc.py` import
    `make_sample_rsem` —— 少帶一支，exe 裡「用範例資料試一次」就是 ImportError。"""
    bundled = {os.path.basename(s) for s, d in build_exe.expand_datas(REPO) if d == "tools"}
    for name in bundled:
        if not name.endswith(".py"):
            continue
        with open(os.path.join(TOOLS, name), "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for mod in names:
                sibling = mod.split(".")[0] + ".py"
                if os.path.isfile(os.path.join(TOOLS, sibling)):
                    assert sibling in bundled, "%s import 了 %s，但後者不在打包清單裡" % (name, sibling)


def test_hidden_imports_name_the_dynamically_loaded_roi_modules():
    for mod in ("d4t.core.steps.roi_cross", "d4t.core.steps.roi_template", "PySide6.QtSvg"):
        assert mod in build_exe.HIDDEN_IMPORTS
    for mod in build_exe.HIDDEN_IMPORTS:
        if mod.startswith("d4t."):
            assert os.path.isfile(os.path.join(REPO, *mod.split("."))) or \
                os.path.isfile(os.path.join(REPO, *mod.split(".")) + ".py"), mod


def test_excludes_do_not_drop_what_d4t_uses():
    for keep in ("PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtSvg",
                 "PySide6.QtNetwork", "numpy", "cv2", "tifffile", "openpyxl"):
        assert keep not in build_exe.EXCLUDES


# ---------------------------------------------------------------- 指令與路徑

def test_pyinstaller_command_shape():
    cmd = build_exe.pyinstaller_command("py", "x.spec", "D", "W")
    assert cmd[:4] == ["py", "-m", "PyInstaller", "--noconfirm"]
    assert "--clean" not in cmd
    assert cmd[-1] == "x.spec"
    assert cmd[cmd.index("--distpath") + 1] == "D"
    assert cmd[cmd.index("--workpath") + 1] == "W"
    assert "--clean" in build_exe.pyinstaller_command("py", "x.spec", "D", "W", clean=True)
    assert "--onefile" not in cmd, "spec 模式下 --onefile 會被 PyInstaller 忽略，模式要走環境變數"


def test_env_carries_mode_root_and_icon():
    env = build_exe.env_for("onefile", "/r", "/r/i.ico", base={"PATH": "x"})
    assert env["D4T_EXE_MODE"] == "onefile"
    assert env["D4T_EXE_ROOT"] == "/r"
    assert env["D4T_EXE_ICON"] == "/r/i.ico"
    assert env["PATH"] == "x"
    assert build_exe.env_for("onedir", "/r", None, base={})["D4T_EXE_ICON"] == ""
    with pytest.raises(ValueError):
        build_exe.env_for("zip", "/r", None, base={})


def test_expected_outputs_per_mode():
    d = build_exe.expected_outputs("onedir", "dist", platform="win32")
    assert d == {"cli": os.path.join("dist", "d4t", "d4t.exe"),
                 "gui": os.path.join("dist", "d4t", "d4t-studio.exe")}
    f = build_exe.expected_outputs("onefile", "dist", platform="linux")
    assert f == {"cli": os.path.join("dist", "d4t"), "gui": os.path.join("dist", "d4t-studio")}
    with pytest.raises(ValueError):
        build_exe.expected_outputs("zip", "dist")


def test_smoke_asks_for_version_and_steps():
    cmds = build_exe.smoke_commands("X")
    assert ["X", "--version"] in cmds and ["X", "steps"] in cmds


def test_human_size():
    assert build_exe.human_size(512) == "512 B"
    assert build_exe.human_size(1536) == "1.5 KB"
    assert build_exe.human_size(3 * 1024 ** 3) == "3.0 GB"


# ---------------------------------------------------------------- spec 與 launcher

def test_spec_is_python39_and_names_both_exes():
    with open(SPEC, "r", encoding="utf-8") as f:
        src = f.read()
    ast.parse(src, filename=SPEC, feature_version=(3, 9))
    assert "import build_exe" in src, "spec 要從 build_exe 拿清單（唯一出處）"
    assert "D4T_EXE_MODE" in src
    assert "console=True" in src and "console=False" in src
    assert "upx=False" in src
    assert "MERGE(" not in src
    assert 'EXE_NAMES["cli"]' in src and 'EXE_NAMES["gui"]' in src


def test_spec_does_not_duplicate_the_manifest():
    """清單只有一份：spec 裡不准再出現 recipes/ 或 hidden import 的字面值。"""
    with open(SPEC, "r", encoding="utf-8") as f:
        src = f.read()
    for literal in ('"recipes/', "roi_cross", "QtWebEngine"):
        assert literal not in src, "%s 出現在 spec 裡 —— 清單要住在 build_exe.py" % literal


@pytest.mark.parametrize("kind", ["cli", "gui"])
def test_launchers_call_freeze_support_first(kind):
    path = os.path.join(REPO, build_exe.LAUNCHERS[kind])
    assert os.path.isfile(path)
    body = [n for n in _module_body_without_docstring(path)
            if not isinstance(n, (ast.Import, ast.ImportFrom))]
    assert body and _is_freeze_support_call(body[0]), (
        "%s 的第一句（import 之後）要是 multiprocessing.freeze_support()" % path)


@pytest.mark.parametrize("rel", ["d4t/__main__.py", "d4t/ui/app.py"])
def test_entry_guards_call_freeze_support(rel):
    path = os.path.join(REPO, rel)
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    guards = [n for n in tree.body if isinstance(n, ast.If)
              and "__main__" in ast.dump(n.test)]
    assert guards, "%s 沒有 if __name__ == '__main__'" % rel
    assert any(_is_freeze_support_call(s) for s in guards[-1].body), (
        "%s 的 __main__ 守衛裡沒有 multiprocessing.freeze_support()" % rel)


def test_relaunch_command_in_a_frozen_exe_reruns_the_exe(monkeypatch):
    from d4t.ui import language

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", [r"C:\x\d4t-studio.exe", "--foo"])
    prog, args, cwd = language._relaunch_command()
    assert prog == sys.executable
    assert args == ["--foo"]
    assert cwd == os.getcwd()
    assert "-m" not in args


# ---------------------------------------------------------------- CLI 行為

def _run(args, env_extra=None, timeout=120):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_extra or {})
    return subprocess.run([sys.executable, os.path.join(TOOLS, "build_exe.py")] + list(args),
                          cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=timeout)


def test_help_works_without_third_party():
    proc = subprocess.run([sys.executable, "-S", os.path.join(TOOLS, "build_exe.py"), "--help"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=60)
    assert proc.returncode == 0, proc.stdout
    assert "--onefile" in proc.stdout and "--onedir" in proc.stdout


def test_dry_run_prints_the_plan_and_builds_nothing(tmp_path):
    dist = tmp_path / "dist"
    proc = _run(["--dry-run", "--onefile", "--dist", str(dist), "--work", str(tmp_path / "w")])
    assert proc.returncode == 0, proc.stdout
    assert "Traceback" not in proc.stdout
    assert "PyInstaller" in proc.stdout
    assert "D4T_EXE_MODE=onefile" in proc.stdout
    assert "d4t-studio" in proc.stdout
    assert not dist.exists()
    assert not (tmp_path / "w").exists()


def test_both_mode_flags_together_is_an_error():
    proc = _run(["--onedir", "--onefile", "--dry-run"])
    assert proc.returncode == 2
    assert "not allowed with" in proc.stdout


def test_no_prompt_defaults_to_onedir(monkeypatch):
    ns = build_exe.build_parser().parse_args(["--no-prompt"])
    assert build_exe.choose_mode(ns) == "onedir"
    ns = build_exe.build_parser().parse_args(["--onefile"])
    assert build_exe.choose_mode(ns) == "onefile"


def test_missing_pyinstaller_is_a_sentence_with_the_pip_command(monkeypatch, capsys):
    monkeypatch.setattr(build_exe, "pyinstaller_version", lambda _python: None)
    rc = build_exe.main(["--onedir", "--no-prompt", "--dist", "/nonexistent/x"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "pip install pyinstaller" in out
    assert "Traceback" not in out


def test_preflight_names_the_missing_pieces(tmp_path, monkeypatch):
    monkeypatch.setattr(build_exe, "pyinstaller_version", lambda _python: "6.0")
    bad, _warn = build_exe.preflight(str(tmp_path), sys.executable, platform="win32")
    joined = "\n".join(bad)
    assert "pyproject.toml" in joined
    assert "FILELIST.txt" in joined
    assert "release.py" in joined


def test_preflight_warns_off_windows(monkeypatch):
    monkeypatch.setattr(build_exe, "pyinstaller_version", lambda _python: "6.0")
    _bad, warn = build_exe.preflight(REPO, sys.executable, platform="linux")
    assert any("Windows" in w for w in warn)
    _bad, warn = build_exe.preflight(REPO, sys.executable, platform="win32")
    assert not warn


# ---------------------------------------------------------------- 真的建一次（選用）

@pytest.mark.skipif(not os.environ.get("D4T_RUN_PYINSTALLER"),
                    reason="真的跑 PyInstaller 要幾分鐘；設 D4T_RUN_PYINSTALLER=1 才跑")
def test_a_real_onedir_build_reports_the_build_id(tmp_path):
    proc = _run(["--onedir", "--no-prompt", "--no-icon", "--dist", str(tmp_path / "dist"),
                 "--work", str(tmp_path / "work")], timeout=1800)
    assert proc.returncode == 0, proc.stdout[-4000:]
    from d4t import build_id
    assert build_id() in proc.stdout
