"""Tests for tools/fetch_wheels.py · tools/install_offline.py · tools/doctor.py（M6-1 離線安裝包）。

這三支是「bootstrap 工具」：它們要在**相依套件都還沒裝**的機器上跑，
所以測試的重點有三塊：
  1. 以 subprocess 當外部程式跑（跟使用者的用法一致），檢查離開碼與訊息文字；
  2. 事前檢查（preflight）的失敗一定要是白話訊息 + 非零離開碼，**不能有 traceback**；
  3. 用 ast 掃原始碼，確認模組層只 import 標準函式庫（lazy import 在函式裡的不算）。

網路相關的動作（pip download）一律不真的執行：只驗 argv 組裝（純函式 + --dry-run）。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
DOCTOR = os.path.join(TOOLS, "doctor.py")
FETCH = os.path.join(TOOLS, "fetch_wheels.py")
INSTALL = os.path.join(TOOLS, "install_offline.py")
ALL_TOOLS = (FETCH, INSTALL, DOCTOR)

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import doctor as doctor_mod            # noqa: E402  （stdlib-only，import 得起來就是一種驗證）
import fetch_wheels                    # noqa: E402
import install_offline                 # noqa: E402

REQUIRED_DEPS = ("numpy", "cv2", "tifffile", "PySide6", "openpyxl")


def _run(args, cwd=REPO, env_extra=None, drop_pythonpath=False, timeout=300):
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    if drop_pythonpath:
        env.pop("PYTHONPATH", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable] + list(args), cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout)
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace")


def _deps_present() -> bool:
    """相依套件在不在。

    **一定要用 find_spec，不能真的 import** —— 這個檔案在 pytest 主行程裡跑，
    import 到 PySide6 會害 tests/test_no_qt.py 的「core 不得載入 Qt」守門失敗。
    """
    import importlib.util

    for name in REQUIRED_DEPS:
        try:
            if importlib.util.find_spec(name) is None:
                return False
        except Exception:  # noqa: BLE001 — 壞掉的安裝也算「沒有」
            return False
    return True


# ---------------------------------------------------------------- doctor

@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件才會全綠")
def test_doctor_passes_in_repo_root():
    """在 repo 根目錄跑 doctor：離開碼 0、列出每個套件、最後一行是結論。"""
    rc, out = _run([DOCTOR])
    assert rc == 0, out
    for pip_name, import_name, _essential in doctor_mod.DEPENDENCIES:
        assert pip_name in out, (pip_name, out)
        assert import_name in out or pip_name == import_name
    assert "Python 版本" in out
    assert "adept" in out
    assert "Qt" in out
    assert "端到端試跑" in out          # smoke test 有跑到
    assert "結論" in out
    assert out.strip().splitlines()[-1].startswith("結論")
    assert "Traceback" not in out


@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件")
def test_doctor_verbose_still_passes():
    rc, out = _run([DOCTOR, "--verbose", "--skip-smoke"])
    assert rc == 0, out
    assert "結論" in out
    assert "略過" in out                # smoke 被跳過會標成 △


def test_doctor_detects_wrong_folder(tmp_path):
    """經典錯誤：在別的資料夾執行 → 必須明確說「adept 載入不到」並教他 cd。"""
    try:
        subprocess.run([sys.executable, "-c", "import adept"], cwd=str(tmp_path),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, env={k: v for k, v in os.environ.items()
                                        if k != "PYTHONPATH"})
    except subprocess.CalledProcessError:
        pass                            # 預期：從 tmp 資料夾 import 不到 adept
    else:
        pytest.skip("adept 已安裝到 site-packages，無法模擬『跑錯資料夾』")

    rc, out = _run([DOCTOR], cwd=str(tmp_path), drop_pythonpath=True)
    assert rc == 1, out
    assert "adept" in out
    assert "cd" in out                  # 有告訴他要 cd 到哪
    assert "ADEPT-main" in out
    assert "Traceback" not in out
    assert out.strip().splitlines()[-1].startswith("（想看完整錯誤") or "結論" in out


def test_doctor_help():
    rc, out = _run([DOCTOR, "--help"])
    assert rc == 0
    assert "--verbose" in out


# ---------------------------------------------------------------- --help（不得依賴第三方套件）

@pytest.mark.parametrize("script", [FETCH, INSTALL, DOCTOR])
def test_help_works_without_third_party(script):
    """--help 必須在「什麼都沒裝」時也能跑：這裡用空 sys.path 前綴模擬不了，

    但至少確認 import 期間沒有碰到 numpy 之類的東西（-S 關掉 site-packages）。
    """
    rc, out = _run(["-S", script, "--help"])
    assert rc == 0, out
    assert "usage:" in out or "用法" in out
    assert "Traceback" not in out


# ---------------------------------------------------------------- fetch_wheels（不連網）

def test_build_pip_command_targets_windows_from_any_host():
    cmd = fetch_wheels.build_pip_command(
        dest="/tmp/wheels", requirements="/repo/requirements.txt",
        platforms=("win_amd64",), python_version="39", implementation="cp",
        extra_packages=("pytest",), python_exe="/usr/bin/python3")
    assert cmd[:4] == ["/usr/bin/python3", "-m", "pip", "download"]
    assert "--only-binary=:all:" in cmd
    assert cmd[cmd.index("--platform") + 1] == "win_amd64"
    assert cmd[cmd.index("--python-version") + 1] == "39"
    assert cmd[cmd.index("--implementation") + 1] == "cp"
    assert cmd[cmd.index("--abi") + 1] == "cp39"
    assert cmd[cmd.index("--dest") + 1] == "/tmp/wheels"
    assert cmd[cmd.index("-r") + 1] == "/repo/requirements.txt"
    assert cmd[-1] == "pytest"


def test_build_pip_command_multiple_platforms_and_custom_abi():
    cmd = fetch_wheels.build_pip_command(dest="w", platforms=("win_amd64", "win32"),
                                         python_version="311", abi="none")
    assert cmd.count("--platform") == 2
    assert cmd[cmd.index("--abi") + 1] == "none"
    assert fetch_wheels.default_abi("311") == "cp311"
    assert fetch_wheels.default_abi("37") == "cp37m"
    assert fetch_wheels.default_abi("39", "pp") == "none"


def test_fetch_wheels_dry_run_does_not_download(tmp_path):
    dest = tmp_path / "wheels"
    rc, out = _run([FETCH, "--dry-run", "--dest", str(dest), "--python-version", "39"])
    assert rc == 0, out
    assert "--only-binary=:all:" in out
    assert "win_amd64" in out
    assert not dest.exists()            # dry-run 連資料夾都不該建
    assert "Traceback" not in out


def test_fetch_wheels_missing_requirements_is_readable(tmp_path):
    rc, out = _run([FETCH, "--requirements", str(tmp_path / "nope.txt"), "--dry-run"])
    assert rc != 0
    assert "找不到" in out
    assert "Traceback" not in out


def test_parse_requirements_and_wheel_filename():
    reqs = fetch_wheels.parse_requirements(os.path.join(REPO, "requirements.txt"))
    assert "numpy" in reqs and "opencv-python" in reqs and "PySide6" in reqs
    info = fetch_wheels.parse_wheel_filename("opencv_python-4.8.1.78-cp37-abi3-win_amd64.whl")
    assert info is not None
    assert info[0] == "opencv_python" and info[1] == "4.8.1.78" and info[4] == "win_amd64"
    assert fetch_wheels.parse_wheel_filename("numpy-1.26.4.tar.gz") is None


def test_match_requirements_normalises_names():
    matched = fetch_wheels.match_requirements(
        ["opencv-python", "PySide6", "tifffile"],
        ["opencv_python-4.8.1-cp39-abi3-win_amd64.whl",
         "PySide6-6.5.2-cp39-abi3-win_amd64.whl"])
    assert matched["opencv-python"] and matched["PySide6"]
    assert matched["tifffile"] == []    # 缺的要抓得出來


def test_manifest_roundtrip(tmp_path):
    """fetch_wheels 寫出的 MANIFEST，install_offline 一定要讀得懂（兩支工具的介面契約）。"""
    dest = tmp_path / "wheels"
    dest.mkdir()
    (dest / "numpy-1.26.4-cp39-cp39-win_amd64.whl").write_bytes(b"not a real wheel")
    text = fetch_wheels.build_manifest_text(
        wheels=["numpy-1.26.4-cp39-cp39-win_amd64.whl"], dest=str(dest),
        platforms=["win_amd64"], python_version="39", implementation="cp", abi="cp39",
        requirements_path="requirements.txt", requirement_names=["numpy"])
    path = dest / fetch_wheels.MANIFEST_NAME
    path.write_text(text, encoding="utf-8")

    info = install_offline.parse_manifest(str(path))
    assert info["target_python"] == "39"
    assert info["target_platform"] == "win_amd64"
    assert info["wheel_count"] == "1"
    assert "numpy-1.26.4-cp39-cp39-win_amd64.whl" in text
    assert fetch_wheels.sha256_of(str(dest / "numpy-1.26.4-cp39-cp39-win_amd64.whl")) in text


def test_explain_pip_failure_gives_advice():
    tips = fetch_wheels.explain_pip_failure(
        "ERROR: Could not find a version that satisfies the requirement PySide6",
        platform="win_amd64", python_version="39")
    assert tips and any("--python-version" in t for t in tips)


# ---------------------------------------------------------------- install_offline 事前檢查

def _make_wheels(tmp_path, name, files, manifest=None):
    d = tmp_path / name
    d.mkdir()
    for fn in files:
        (d / fn).write_bytes(b"x" * 16)
    if manifest is not None:
        (d / "MANIFEST.txt").write_text(manifest, encoding="utf-8")
    return d


def _other_python_tag():
    """挑一個保證跟目前 Python 不同的版本 tag。"""
    return "38" if sys.version_info[:2] != (3, 8) else "39"


def test_install_offline_help():
    rc, out = _run([INSTALL, "--help"])
    assert rc == 0
    assert "--wheels" in out and "--no-venv" in out


def test_install_offline_missing_wheels_dir(tmp_path):
    rc, out = _run([INSTALL, "--wheels", str(tmp_path / "does_not_exist"), "--dry-run"])
    assert rc != 0
    assert "找不到離線套件資料夾" in out
    assert "fetch_wheels" in out        # 有指出下一步怎麼做
    assert "Traceback" not in out


def test_install_offline_empty_wheels_dir(tmp_path):
    d = _make_wheels(tmp_path, "empty", [])
    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run"])
    assert rc != 0
    assert "沒有任何 .whl" in out
    assert "Traceback" not in out


def test_install_offline_python_version_mismatch(tmp_path):
    tag = _other_python_tag()
    d = _make_wheels(tmp_path, "mismatch",
                     ["numpy-1.26.4-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
                     manifest="target_platform: win_amd64\ntarget_python: %s\n" % tag)
    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run"])
    assert rc != 0
    assert "Python 版本對不上" in out
    assert "3.%s" % tag[1:] in out                              # wheels 的版本
    assert "%d.%d" % sys.version_info[:2] in out                # 這台機器的版本
    assert "fetch_wheels.py --python-version" in out            # 教他怎麼修
    assert "Traceback" not in out
    # 安裝完全沒有開始
    assert "安裝沒有開始" in out


def test_install_offline_version_mismatch_ok_for_pure_python_wheels(tmp_path):
    """py3-none-any 的 wheel 與版本無關 —— 不該被擋下來（只給提醒）。"""
    tag = _other_python_tag()
    d = _make_wheels(tmp_path, "pure", ["openpyxl-3.1.5-py2.py3-none-any.whl"],
                     manifest="target_python: %s\n" % tag)
    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run", "--no-venv"])
    assert rc == 0, out
    assert "與版本無關" in out


def test_install_offline_dry_run_passes_and_prints_command(tmp_path):
    tag = "%d%d" % sys.version_info[:2]
    d = _make_wheels(tmp_path, "good", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
                     manifest="target_platform: win_amd64\ntarget_python: %s\n" % tag)
    rc, out = _run([INSTALL, "--wheels", str(d), "--dry-run",
                    "--venv", str(tmp_path / "venv")])
    assert rc == 0, out
    assert "--no-index" in out and "--find-links" in out
    assert not (tmp_path / "venv").exists()


def test_install_offline_missing_requirements(tmp_path):
    rc, out = _run([INSTALL, "--requirements", str(tmp_path / "nope.txt"), "--dry-run"])
    assert rc != 0
    assert "requirements.txt" in out
    assert "cd" in out                  # 提示他可能跑錯資料夾
    assert "Traceback" not in out


def test_install_offline_pure_functions():
    assert install_offline.parse_python_tag("cp39") == (3, 9)
    assert install_offline.parse_python_tag("3.11") == (3, 11)
    assert install_offline.parse_python_tag("311") == (3, 11)
    assert install_offline.parse_python_tag("") is None
    assert install_offline.wheel_python_tags("a-1.0-py2.py3-none-any.whl") == ["py2", "py3"]
    assert install_offline.wheels_are_pure_python(["a-1.0-py2.py3-none-any.whl"])
    assert not install_offline.wheels_are_pure_python(["a-1.0-cp39-cp39-win_amd64.whl"])
    cmd = install_offline.build_pip_install_command("py.exe", "W", "R", user=True)
    assert cmd[:5] == ["py.exe", "-m", "pip", "install", "--no-index"]
    assert cmd[cmd.index("--find-links") + 1] == "W"
    assert cmd[cmd.index("-r") + 1] == "R"
    assert "--user" in cmd
    assert install_offline.build_pip_install_command(
        "py", "W", "R", extra_packages=("pytest",))[-1] == "pytest"


def test_install_offline_include_pytest(tmp_path):
    """--include-pytest：wheels 裡有 pytest 才加進安裝清單，沒有就只是提醒。"""
    tag = "%d%d" % sys.version_info[:2]
    manifest = "target_python: %s\n" % tag
    with_pytest = _make_wheels(tmp_path, "wp", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag),
                                                "pytest-8.2.0-py3-none-any.whl"],
                               manifest=manifest)
    rc, out = _run([INSTALL, "--wheels", str(with_pytest), "--dry-run", "--no-venv",
                    "--include-pytest"])
    assert rc == 0, out
    assert "requirements.txt pytest" in out          # 加在 pip 指令最後面

    without = _make_wheels(tmp_path, "np", ["numpy-2.0.0-cp%s-cp%s-win_amd64.whl" % (tag, tag)],
                           manifest=manifest)
    rc, out = _run([INSTALL, "--wheels", str(without), "--dry-run", "--no-venv",
                    "--include-pytest"])
    assert rc == 0, out
    assert "沒有 pytest 的 wheel" in out


@pytest.mark.skipif(not _deps_present(), reason="需要全部相依套件")
def test_doctor_survives_ascii_console():
    """cp950/ASCII 主控台吐不出 ✓ 或中文時，不可以爆 UnicodeEncodeError。"""
    rc, out = _run([DOCTOR, "--skip-smoke"], env_extra={"PYTHONIOENCODING": "ascii"})
    assert rc == 0, out
    assert "Traceback" not in out
    assert "[OK]" in out                # 自動退回純 ASCII 標記


def test_explain_venv_failure_suggests_no_venv():
    tips = install_offline.explain_venv_failure(
        "Error: Command '['...', '-m', 'ensurepip', ...]' returned non-zero exit status 1.",
        ".venv")
    joined = "\n".join(tips)
    assert "ensurepip" in joined
    assert "--no-venv" in joined
    assert "--user" in joined


# ---------------------------------------------------------------- bootstrap 鐵則：只用標準函式庫

def _stdlib_names():
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    return {                                     # Python 3.9 沒有 stdlib_module_names
        "__future__", "argparse", "ast", "base64", "datetime", "hashlib", "json",
        "os", "platform", "re", "shutil", "struct", "subprocess", "sys",
        "tempfile", "time", "typing", "unicodedata", "zipfile", "importlib",
    }


def _module_level_imports(path):
    """回傳模組層 import 到的頂層模組名（函式/類別內部的 lazy import 不算）。"""
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    found = set()
    for node in tree.body:                       # 只看最外層
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
            elif node.level:
                found.add("<relative>")
    return found


@pytest.mark.parametrize("script", ALL_TOOLS)
def test_tools_import_only_stdlib_at_module_level(script):
    imports = _module_level_imports(script)
    extra = imports - _stdlib_names()
    assert not extra, "%s 的模組層 import 了非標準函式庫：%s（請改成函式內 lazy import）" % (
        os.path.basename(script), sorted(extra))


@pytest.mark.parametrize("script", ALL_TOOLS)
def test_tools_are_python39_compatible(script):
    """與 tests/test_no_qt.py 同樣的守門：語法必須是 3.9 吃得下的。"""
    with open(script, "r", encoding="utf-8") as f:
        src = f.read()
    ast.parse(src, filename=script, feature_version=(3, 9))
    assert "from __future__ import annotations" in src
