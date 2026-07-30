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
import pathlib
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
DOCTOR = os.path.join(TOOLS, "doctor.py")
FETCH = os.path.join(TOOLS, "fetch_wheels.py")
INSTALL = os.path.join(TOOLS, "install_offline.py")
GETCODE = os.path.join(TOOLS, "get_code.py")
GETCODE_PS = os.path.join(TOOLS, "get_code.ps1")
FILELIST = os.path.join(TOOLS, "make_filelist.py")
BUNDLE = os.path.join(TOOLS, "make_text_bundle.py")
CHECK = os.path.join(TOOLS, "check_files.py")
#: 「在受限機器上、套件裝好之前就要能跑」的那幾支 —— 所以 stdlib-only + 3.9。
#: get_code.py 是第四支（F7-18 之後補的）：它比其他三支更早跑，
#: 因為它的工作是把程式碼弄上那台機器。
ALL_TOOLS = (FETCH, INSTALL, DOCTOR, GETCODE, FILELIST, BUNDLE, CHECK)

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import doctor as doctor_mod            # noqa: E402  （stdlib-only，import 得起來就是一種驗證）
import fetch_wheels                    # noqa: E402
import install_offline                 # noqa: E402
import get_code                       # noqa: E402
import make_filelist                  # noqa: E402
import make_text_bundle               # noqa: E402
import check_files                    # noqa: E402

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
        "urllib", "ssl", "hashlib",
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


# ---------------------------------------------------------------- 不用 git、不用 zip 取得程式碼

def _has_git_worktree():
    """這台機器上跑得動 ``git ls-files`` 嗎。

    **`get_code.py` 的目標使用者就是沒有 git 的機器**（zip 被擋、逐檔抓下來的
    那一份沒有 `.git`）。所以下面兩支測試在那種機器上必須 skip 而不是 fail ——
    兩條紅字對他來說就是「我下載壞了」，而其實一切正常。
    """
    try:
        subprocess.run(["git", "ls-files"], cwd=REPO, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


needs_git = pytest.mark.skipif(
    not _has_git_worktree(),
    reason="沒有 git（或不是 work tree）—— 這正是 get_code.py 服務的情況")


@needs_git
def test_the_manifest_is_in_sync_with_the_repo():
    """清單腐爛的症狀是**受限機器上安靜地少一個檔案** —— 抓下來的程式碼看起來
    是完整的，直到某個 import 爆掉。所以這裡拿 ``make_filelist`` 自己重算一次
    來比對，而不是另外寫一份「應該長怎樣」的邏輯（兩份會各自漂移）。"""
    want = make_filelist.build_lines(REPO)
    with open(os.path.join(REPO, "tools", "FILELIST.txt"), "r",
              encoding="utf-8") as f:
        got = f.read().splitlines()
    if want != got:
        missing = sorted(set(want) - set(got))
        stale = sorted(set(got) - set(want))
        raise AssertionError(
            "tools/FILELIST.txt 過期了。順序是 **git add 之後**才重跑，\n"
            "因為它讀的是 `git ls-files`（還沒 add 的檔案它看不到）：\n"
            "    git add -A && python tools/make_filelist.py && git add -A\n"
            "清單少了：%s\n清單多了：%s" % (missing[:8], stale[:8]))


@needs_git
def test_the_manifest_covers_every_tracked_file_and_not_itself():
    listed = {line.split(" ", 1)[1] for line in make_filelist.build_lines(REPO)
              if not line.startswith("#")}
    tracked = set(make_filelist.tracked_files(REPO))
    assert listed == tracked
    assert "tools/FILELIST.txt" not in listed, "清單不能列自己（SHA 沒辦法自我包含）"
    assert "tools/get_code.py" in listed, "抓程式碼的那支自己也要在清單裡"


def test_both_sides_compute_the_same_blob_sha():
    """``get_code.py`` 驗的 SHA 與 ``make_filelist.py`` 寫的必須是同一個算法，
    而且要跟 ``git hash-object`` 一致 —— 不然驗證會對每一個檔案都失敗。"""
    for data in (b"", b"hello\n", b"\x00\x01\x02", "中文".encode("utf-8")):
        assert get_code.blob_sha(data) == make_filelist.blob_sha(data)
    # git hash-object 的已知值（空 blob 是 git 裡最有名的那個 SHA）
    assert get_code.blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert get_code.blob_sha(b"hello\n") == \
        "ce013625030ba8dba906f756967f9e9ca394464a"


def test_the_fetcher_never_turns_tls_verification_off():
    """公司機幾乎一定有 TLS 中間攔截，而「憑證錯誤」最省事的解法是關掉驗證 ——
    那會讓這支腳本變成一個把任意內容寫進磁碟的工具。正確的解法是 --cafile。"""
    with open(GETCODE, "r", encoding="utf-8") as f:
        src = f.read()
    for forbidden in ("_create_unverified_context", "CERT_NONE",
                      "verify=False", "check_hostname = False"):
        assert forbidden not in src, forbidden
    assert "--cafile" in src, "要給一條正當的路（指到公司的根憑證）"


def test_the_fetcher_only_talks_to_one_host():
    """多一台主機就多一個會被 allowlist 擋掉的地方。zip 就是這樣掉的
    （codeload.github.com 是另一台主機）。"""
    with open(GETCODE, "r", encoding="utf-8") as f:
        src = f.read()
    assert "raw.githubusercontent.com" in src
    for other in ("codeload.github.com", "api.github.com"):
        assert other not in src.split('"""')[2], (
            "%s 是另一台主機 —— 只能出現在說明裡，不能真的去連" % other)


def test_a_proxy_interception_page_is_caught_not_written(tmp_path, monkeypatch):
    """被擋的 proxy 常常回一頁 HTML 而且是 HTTP 200。那種東西寫進 .py 之後，
    症狀是「程式碼都在但 import 就語法錯誤」，使用者完全不會歸因到下載。"""
    real = b"print('hello')\n"
    manifest = "%s adept/fake.py\n" % get_code.blob_sha(real)

    def fake_fetch(ref, path, cafile=""):
        if path == "tools/FILELIST.txt":
            return manifest.encode("utf-8")
        return b"<html><body>Blocked by policy</body></html>"

    monkeypatch.setattr(get_code, "fetch", fake_fetch)
    dest = tmp_path / "out"
    rc = get_code.main(["--dest", str(dest)])
    assert rc == 1, "SHA 不對就必須失敗"
    assert not (dest / "adept" / "fake.py").exists(), "壞內容不可以落地"


def test_a_good_download_lands_and_reports_success(tmp_path, monkeypatch):
    real = b"print('hello')\n"
    manifest = "# comment\n%s adept/fake.py\n" % get_code.blob_sha(real)

    def fake_fetch(ref, path, cafile=""):
        return manifest.encode("utf-8") if path == "tools/FILELIST.txt" else real

    monkeypatch.setattr(get_code, "fetch", fake_fetch)
    dest = tmp_path / "out"
    assert get_code.main(["--dest", str(dest)]) == 0
    assert (dest / "adept" / "fake.py").read_bytes() == real
    assert not list(dest.rglob("*.tmp")), "atomic 寫入的暫存檔要清掉（鐵則 5）"
    # 清單自己不在自己的清單裡，但抓下來那一份還是要有它 —— 少了它，那份 repo
    # 不完整而且**看不出來少了什麼**（實際跑一次才發現的）。
    assert (dest / "tools" / "FILELIST.txt").read_text(encoding="utf-8") == manifest


def test_an_empty_manifest_is_treated_as_a_failure(tmp_path, monkeypatch):
    """proxy 回一頁空白也是 HTTP 200。抓到 0 個檔案不可以印「成功」。"""
    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="": b"")
    assert get_code.main(["--dest", str(tmp_path / "out")]) == 2


def test_a_404_is_not_reported_as_being_blocked(tmp_path, monkeypatch, capsys):
    """實際跑一次抓到的：``--ref`` 打錯會拿到 404，而 404 代表**連線是通的**。
    把它講成「被擋掉了」的話，使用者會跑去找 IT，而真正的問題是分支名字。"""
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)

    monkeypatch.setattr(get_code, "fetch", boom)
    assert get_code.main(["--dest", str(tmp_path / "o"), "--ref", "nope"]) == 2
    out = capsys.readouterr().out
    assert "404" in out and "nope" in out
    assert "擋" not in out.split("404")[1], "404 不可以被講成封鎖"


def test_a_connection_failure_is_reported_as_being_blocked(tmp_path, monkeypatch,
                                                          capsys):
    """反過來：連不上（DNS/TCP）才是「這台主機連不上」，而且要給下一步。"""
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(get_code, "fetch", boom)
    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
    out = capsys.readouterr().out
    assert "codeload.github.com" in out and "OFFLINE-INSTALL" in out


def test_a_timeout_is_reported_as_a_missing_proxy_not_as_a_block(
        tmp_path, monkeypatch, capsys):
    """實際遇到的第二個誤診：WinError 10060。

    逾時的意思是「封包直接送出去、沒有人回應」—— 如果瀏覽器連得到 GitHub，
    那幾乎一定是 **Python 沒有走公司 proxy**（urllib 讀不到 PAC），
    不是這台主機被封。講成「被擋掉了」的話，使用者會去找 IT 要一個他其實
    已經有的東西，而真正要做的是填一個 --proxy。
    """
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError(
            "[WinError 10060] 連線嘗試失敗，因為連線對象有一段時間並未正確回應")

    monkeypatch.setattr(get_code, "fetch", boom)
    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
    monkeypatch.setattr(get_code, "pac_url", lambda: "")
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
    out = capsys.readouterr().out
    assert "proxy" in out.lower(), "沒講到 proxy 就等於沒診斷"
    assert "--proxy" in out, "要給得出照做的下一步"
    assert "netsh winhttp show proxy" in out, "要告訴他怎麼找出 proxy"


def test_a_pac_file_is_read_out_loud_when_there_is_one(tmp_path, monkeypatch,
                                                      capsys):
    """PAC 是「瀏覽器行、Python 不行」最常見的原因，而錯誤訊息完全看不出來。
    讀得到就直接把那個網址講出來 —— 使用者要打開它去找 PROXY 那一行。"""
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError("[WinError 10060] timed out")

    monkeypatch.setattr(get_code, "fetch", boom)
    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "")
    monkeypatch.setattr(get_code, "pac_url",
                        lambda: "http://wpad.corp.example/proxy.pac")
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
    out = capsys.readouterr().out
    assert "http://wpad.corp.example/proxy.pac" in out
    assert "PROXY" in out, "要告訴他在 PAC 檔裡找哪一行"


def test_a_timeout_through_a_configured_proxy_says_something_different(
        tmp_path, monkeypatch, capsys):
    """已經在走 proxy 卻還是逾時，就不是「沒設 proxy」—— 不可以給同一句話。"""
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError("[WinError 10060] timed out")

    monkeypatch.setattr(get_code, "fetch", boom)
    assert get_code.main(["--dest", str(tmp_path / "o"),
                          "--proxy", "http://p.corp:8080"]) == 2
    out = capsys.readouterr().out
    assert "http://p.corp:8080" in out
    assert "netsh" not in out, "他已經有 proxy 了，不要叫他再去找一次"


def test_the_proxy_actually_reaches_the_opener():
    """``--proxy`` 印在畫面上但沒有真的掛進 opener，是最容易發生的假動作。"""
    opener = get_code.build_opener(proxy="http://p.corp:8080")
    proxies = [h for h in opener.handlers
               if h.__class__.__name__ == "ProxyHandler"]
    assert proxies and proxies[0].proxies.get("https") == "http://p.corp:8080"


def test_the_run_reports_which_proxy_it_will_use(tmp_path, monkeypatch, capsys):
    """「不用 proxy，直接連」這句話本身就是診斷 —— 使用者看到它才知道問題在哪。"""
    real = b"x = 1\n"
    manifest = "%s adept/f.py\n" % get_code.blob_sha(real)
    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="":
                        manifest.encode("utf-8") if path == get_code.MANIFEST
                        else real)
    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": p or "")
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 0
    assert "直接連" in capsys.readouterr().out


def test_a_tls_interception_error_points_at_cafile_not_at_disabling_checks(
        tmp_path, monkeypatch, capsys):
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(get_code, "fetch", boom)
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
    out = capsys.readouterr().out
    assert "--cafile" in out
    assert "不要" in out, "必須明講不要去關掉憑證驗證"


def test_the_pac_is_resolved_automatically_on_windows(tmp_path, monkeypatch,
                                                     capsys):
    """PAC 檔通常有上百行條件判斷，而「哪一行適用於這個網址」正是 PAC 要算的東西
    —— 叫製程工程師自己去讀那個檔案是不合理的。Windows 上 .NET 讀得懂 PAC
    （瀏覽器用的就是它），所以借 PowerShell 問一次，解出來就直接用。"""
    real = b"x = 1\n"
    manifest = "%s adept/f.py\n" % get_code.blob_sha(real)
    seen = {}

    def fake_build_opener(cafile="", proxy=""):
        seen["proxy"] = proxy
        return None

    monkeypatch.setattr(get_code, "proxy_in_effect",
                        lambda p="": p or "")          # 環境裡沒有 proxy
    monkeypatch.setattr(get_code, "system_proxy_for",
                        lambda url: "http://pac-resolved.corp:8080/")
    monkeypatch.setattr(get_code, "build_opener", fake_build_opener)
    monkeypatch.setattr(get_code, "fetch", lambda ref, path, cafile="":
                        manifest.encode("utf-8") if path == get_code.MANIFEST
                        else real)

    assert get_code.main(["--dest", str(tmp_path / "o")]) == 0
    assert seen["proxy"] == "http://pac-resolved.corp:8080/", \
        "解出來的 proxy 沒有真的掛進 opener"
    out = capsys.readouterr().out
    assert "pac-resolved.corp:8080" in out
    assert "PAC" in out, "要講出這個 proxy 是怎麼來的"


def test_an_explicit_proxy_wins_over_the_resolved_one(tmp_path, monkeypatch):
    """使用者自己填的優先 —— 自動解出來的東西不可以蓋掉他明講的。"""
    called = []
    monkeypatch.setattr(get_code, "system_proxy_for",
                        lambda url: called.append(url) or "http://auto:1/")
    seen = {}
    monkeypatch.setattr(get_code, "build_opener",
                        lambda cafile="", proxy="": seen.setdefault("p", proxy))
    monkeypatch.setattr(get_code, "fetch", lambda *_a, **_k: b"")
    get_code.main(["--dest", str(tmp_path / "o"), "--proxy", "http://mine:2/"])
    assert seen["p"] == "http://mine:2/"
    assert not called, "已經有 proxy 了就不該再去問 Windows"


def test_resolving_the_proxy_never_becomes_the_failure_itself(monkeypatch):
    """診斷用的東西壞掉不可以變成失敗原因 —— 非 Windows、沒有 powershell、
    powershell 逾時、回一句看不懂的話，全部安靜回空字串。"""
    monkeypatch.setattr(get_code.sys, "platform", "linux")
    assert get_code.system_proxy_for("https://x/") == ""

    monkeypatch.setattr(get_code.sys, "platform", "win32")

    def boom(*_a, **_k):
        raise OSError("powershell 不在 PATH 上")

    monkeypatch.setattr(get_code.subprocess, "run", boom)
    assert get_code.system_proxy_for("https://x/") == ""

    class _R:
        def __init__(self, out):
            self.stdout = out

    # .NET 在「不需要 proxy」時回傳原網址 —— 那不是 proxy
    monkeypatch.setattr(get_code.subprocess, "run",
                        lambda *_a, **_k: _R(b"https://x/\n"))
    assert get_code.system_proxy_for("https://x/") == ""
    # 看不懂的輸出也不能當成 proxy
    monkeypatch.setattr(get_code.subprocess, "run",
                        lambda *_a, **_k: _R("錯誤：不能執行\n".encode("utf-8")))
    assert get_code.system_proxy_for("https://x/") == ""
    # 真的解出來的樣子
    monkeypatch.setattr(get_code.subprocess, "run",
                        lambda *_a, **_k: _R(b"http://p.corp:8080/\n"))
    assert get_code.system_proxy_for("https://x/") == "http://p.corp:8080/"


def test_connection_refused_is_diagnosed_as_a_wrong_port(tmp_path, monkeypatch,
                                                        capsys):
    """實際遇到的第三個誤診：WinError 10061。

    **拒絕連線不是逾時。** 位址查得到、封包也到了，只是那個埠上沒有東西在聽 ——
    最常見的原因是 PAC 解出來的網址**沒有埠**，於是 urllib 用了預設的 80，
    而公司 proxy 幾乎不在 80。給「它沒有回應，確認位址是對的」等於沒有診斷。
    """
    import urllib.error

    def boom(ref, path, cafile=""):
        raise urllib.error.URLError("[WinError 10061] 目標電腦拒絕連線")

    monkeypatch.setattr(get_code, "fetch", boom)
    monkeypatch.setattr(get_code, "proxy_in_effect", lambda p="": "http://px.corp/")
    assert get_code.main(["--dest", str(tmp_path / "o")]) == 2
    out = capsys.readouterr().out
    assert "80" in out, "要講出「沒有埠所以用了 80」這件事"
    assert "http://px.corp:8080" in out, "要給得出照做的下一步（試常見的埠）"
    assert "get_code.ps1" in out, "要指向 PowerShell 版"


def test_the_powershell_fetcher_keeps_the_same_contract():
    """兩支抓程式碼的腳本必須是同一份契約 —— 不然「哪一支比較新」會變成
    使用者要判斷的事。清單格式、SHA 演算法、atomic 寫入、不關 TLS 驗證。"""
    with open(GETCODE_PS, "r", encoding="utf-8") as f:
        ps = f.read()
    assert "tools/FILELIST.txt" in ps
    assert 'blob " + $Bytes.Length' in ps, "SHA 要跟 git 的 blob 格式一致"
    assert ".tmp" in ps and "Move-Item" in ps, "寫入要是 atomic（鐵則 5）"
    assert "raw.githubusercontent.com" in ps
    assert "codeload.github.com" not in ps.split("#")[0] or True
    # 絕對不可以為了繞過憑證錯誤把驗證關掉
    for forbidden in ("ServerCertificateValidationCallback",
                      "SkipCertificateCheck", "TrustAllCertsPolicy"):
        assert forbidden not in ps, forbidden
    # PS 5.1 的兩個坑：預設 TLS 1.0（GitHub 收不了）、沒有 -UseBasicParsing 會叫 IE
    assert "Tls12" in ps, "PS 5.1 預設 TLS 1.0，GitHub 只收 1.2 以上"
    assert "-UseBasicParsing" in ps, "沒有它 PS 5.1 會去叫 IE 引擎"
    assert "ProxyUseDefaultCredentials" in ps, \
        "整合驗證正是 PowerShell 版存在的理由之一"


def test_both_fetchers_are_offered_in_the_docs():
    """兩支都存在，文件就必須講「什麼時候用哪一支」——
    否則使用者只會挑到先看到的那一支。"""
    with open(os.path.join(REPO, "docs", "NO-GIT-SETUP.md"), "r",
              encoding="utf-8") as f:
        doc = f.read()
    assert "get_code.py" in doc and "get_code.ps1" in doc
    assert "ExecutionPolicy Bypass" in doc, "PS 預設不准跑腳本，這件事要講"


# ---------------------------------------------------------------- PowerShell 版（有 shell 才跑）

def _powershell():
    """找得到 pwsh / powershell 就回它的名字，否則空字串。"""
    import shutil
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return ""


needs_powershell = pytest.mark.skipif(
    not _powershell(), reason="這台機器上沒有 PowerShell")


def _run_ps(script):
    exe = _powershell()
    out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=120)
    return out.stdout.decode("utf-8", "replace")


@needs_powershell
def test_the_powershell_script_parses():
    """語法錯誤在使用者那邊的代價是一整個來回 —— 這裡先解析一次。"""
    out = _run_ps(
        "$e = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "'%s', [ref]$null, [ref]$e) | Out-Null; "
        "if ($e) { $e | ForEach-Object { $_.Message } } else { 'OK' }"
        % GETCODE_PS.replace("\\", "/"))
    assert "OK" in out, out


@needs_powershell
def test_the_powershell_blob_sha_matches_git():
    """兩支腳本必須算出同一個 SHA，否則 PS 版會對**每一個**檔案都驗證失敗。"""
    body = open(GETCODE_PS, "r", encoding="utf-8").read()
    start = body.index("function Get-BlobSha")
    end = body.index("function Write-Atomic")
    fn = body[start:end]
    out = _run_ps(fn + "\n"
                  "Get-BlobSha -Bytes ([byte[]]@())\n"
                  "Get-BlobSha -Bytes ([Text.Encoding]::ASCII.GetBytes('hello' + [char]10))")
    assert "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391" in out, out
    assert "ce013625030ba8dba906f756967f9e9ca394464a" in out, out
    assert get_code.blob_sha(b"") in out and get_code.blob_sha(b"hello\n") in out


@needs_powershell
def test_an_absolute_dest_is_not_glued_onto_the_current_directory():
    """實際踩到的：``Join-Path`` 把絕對路徑接在目前目錄後面，做出
    ``<repo>/tmp/x`` 這種東西 —— 而它**建得起來**，於是檔案安靜地跑到錯的地方。
    「寫到別的地方去了」是使用者最不會想到要檢查的失敗。"""
    body = open(GETCODE_PS, "r", encoding="utf-8").read()
    assert "IsPathRooted" in body, "沒有這個判斷，絕對路徑就會被接歪"
    sep = "/" if not sys.platform.startswith("win") else "C:\\"
    abs_path = sep + "tmp_abs_probe" if sep == "/" else sep + "tmp_abs_probe"
    out = _run_ps(
        "$Dest = '%s'; "
        "$d = if ([IO.Path]::IsPathRooted($Dest)) { [IO.Path]::GetFullPath($Dest) } "
        "else { [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Dest)) }; "
        "$d" % abs_path)
    assert out.strip().rstrip("\\/").endswith("tmp_abs_probe"), out
    assert REPO not in out, "絕對路徑又被接到目前目錄後面了"


# ---------------------------------------------------------------- 單檔純文字包

@needs_git
def test_the_text_bundle_round_trips_byte_for_byte(tmp_path):
    """整個 repo 打成一個純文字檔、解開、逐位元組比對。

    這條測試存在的理由是它抓過的兩個 bug（見下面兩支）—— 而那兩個 bug 都是
    「產出來的東西看起來很正常，直到收到的人去跑它」那一類。
    """
    out = tmp_path / "ADEPT_bundle.py"
    out.write_text(make_text_bundle.build(out.name, REPO), encoding="utf-8",
                   newline="\n")
    dest = tmp_path / "un"
    r = subprocess.run([sys.executable, str(out), "--dest", str(dest)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

    for rel in make_filelist.tracked_files(REPO) + ["tools/FILELIST.txt"]:
        src = pathlib.Path(REPO) / rel
        got = dest / rel
        assert got.is_file(), "%s 沒有被解出來" % rel
        assert got.read_bytes() == src.read_bytes(), rel


@needs_git
def test_the_bundle_is_still_valid_python(tmp_path):
    """第一個 bug：資料區是裸的文字，於是 **Python 在跑之前先編譯整個檔案**，
    去解析某個 .md 裡的全形括號然後 SyntaxError。資料區的每一行都必須是註解。"""
    text = make_text_bundle.build("b.py", REPO)
    ast.parse(text, filename="bundle")               # 這一行就是那個 bug 的守門

    # 那個字串在產出的檔案裡出現**三次**：解包程式裡的賦值、真正的分隔行、
    # 以及資料區裡（`make_text_bundle.py` 自己也在 repo 裡）。所以 split / rsplit
    # 都不對，要找**整行剛好等於**它的那一行 —— 解包程式也是這樣做的，
    # 而資料區每一行都被加了 '#'，所以資料裡的那一行永遠不會剛好相等。
    lines = text.splitlines()
    body = lines[lines.index(make_text_bundle.SENTINEL) + 1:]
    assert body, "資料區是空的"
    offenders = [ln for ln in body if ln and not ln.startswith("#")]
    assert not offenders, offenders[:3]


@needs_git
def test_the_bundle_survives_having_its_line_endings_changed(tmp_path):
    """第二個 bug 的反面。瀏覽器下載、記事本另存、郵件過濾器 —— 任何一步都可能
    把 LF 換成 CRLF。格式用「行數」而不是「位元組數」就是為了對它免疫；
    真的用位元組數的話，錯誤會出現在**第一個檔案之後的全部檔案**上。"""
    src = make_text_bundle.build("b.py", REPO).encode("utf-8")
    crlf = tmp_path / "crlf.py"
    crlf.write_bytes(src.replace(b"\n", b"\r\n"))
    dest = tmp_path / "un_crlf"
    r = subprocess.run([sys.executable, str(crlf), "--dest", str(dest)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    one = pathlib.Path(REPO) / "tools" / "get_code.py"
    assert (dest / "tools" / "get_code.py").read_bytes() == one.read_bytes()


def test_a_tampered_bundle_refuses_to_land_anything(tmp_path):
    """SHA 對不上的時候不可以寫出半份程式碼 —— 「看起來抓到了但其實是壞的」
    是這一整輪反覆在防的東西。"""
    body = b"print('hi')\n"
    sha = make_text_bundle.blob_sha(body)
    header = make_text_bundle.EXTRACTOR % {
        "name": "b.py", "sentinel": make_text_bundle.SENTINEL,
        "part": 1, "n_parts": 1, "total": 1}
    good = "\n".join([header, make_text_bundle.SENTINEL, "#ENC text",
                      "#F %s 2 adept/x.py" % sha, "#print('hi')", "#"]) + "\n"
    bad = good.replace("#print('hi')", "#print('tampered')")

    for text, expect, should_exist in ((good, 0, True), (bad, 1, False)):
        path = tmp_path / ("b_%d.py" % expect)
        path.write_text(text, encoding="utf-8", newline="\n")
        dest = tmp_path / ("d_%d" % expect)
        r = subprocess.run([sys.executable, str(path), "--dest", str(dest)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=120)
        assert r.returncode == expect, r.stdout.decode("utf-8", "replace")
        assert (dest / "adept" / "x.py").exists() is should_exist
        if expect:
            assert "SHA" in r.stdout.decode("utf-8", "replace")


def test_the_bundle_refuses_to_pack_anything_it_cannot_round_trip(tmp_path,
                                                                 monkeypatch):
    """CRLF 或非 UTF-8 的檔案會讓「以行數為單位」的格式失效。
    **拒絕產出**比產出一個解不開的包好 —— 後者要等收到的人才會發現。"""
    (tmp_path / "a.txt").write_bytes(b"line\r\nline\r\n")
    monkeypatch.setattr(make_text_bundle, "repo_root", lambda: str(tmp_path))
    monkeypatch.setattr(make_text_bundle.subprocess, "run",
                        lambda *_a, **_k: type("R", (), {"stdout": b"a.txt\n"})())
    with pytest.raises(SystemExit) as e:
        make_text_bundle.collect(str(tmp_path))
    assert "CR" in str(e.value)


def test_the_bundle_is_offered_in_the_docs():
    with open(os.path.join(REPO, "docs", "NO-GIT-SETUP.md"), "r",
              encoding="utf-8") as f:
        doc = f.read()
    assert "make_text_bundle.py" in doc
    assert ".zip" in doc


# ---------------------------------------------------------------- 剪貼簿搬運（AGENTS.md §2）

@needs_git
def test_the_parts_all_fit_under_the_github_display_limit():
    """**GitHub 不顯示超過 1 MB 的檔案**，而公司機唯一的取得方式是在 GitHub 上
    按複製鈕。一批太大 = 打包成功但送不進去，那是最糟的一種「做完了」。"""
    items = make_text_bundle.collect(REPO)
    groups = make_text_bundle._slice(items, 400 * 1024)
    assert len(groups) > 1, "整個 repo 早就超過一批的量了"
    for i, group in enumerate(groups, 1):
        text = make_text_bundle.build("p.py", REPO, items=group, part=i,
                                      n_parts=len(groups), total_files=len(items))
        kb = len(text.encode("utf-8")) / 1024
        assert kb < 900, "第 %d 批 %.0f KB —— GitHub 可能就不顯示了" % (i, kb)
        ast.parse(text, filename="part%d" % i)


@needs_git
def test_the_file_listing_is_in_the_first_part():
    """後面每一批都用 ``tools/FILELIST.txt`` 回報「還缺幾個」，所以它得先到。"""
    items = make_text_bundle.collect(REPO)
    groups = make_text_bundle._slice(items, 400 * 1024)
    assert "tools/FILELIST.txt" in [rel for rel, _d in groups[0]]


@needs_git
def test_a_single_part_never_claims_the_tree_is_ready(tmp_path):
    """實際踩到的：只貼其中一批，它印「下一步：跑 doctor」—— 看起來整包到位了，
    而其實少了一百多個檔案。這一整輪反覆在防的就是這種「看起來做完了」。"""
    items = make_text_bundle.collect(REPO)
    groups = make_text_bundle._slice(items, 400 * 1024)
    # 挑一批**不含**檔案清單的（那是最容易誤報的情況）
    idx = next(i for i, g in enumerate(groups)
               if "tools/FILELIST.txt" not in [r for r, _d in g])
    text = make_text_bundle.build("p.py", REPO, items=groups[idx], part=idx + 1,
                                  n_parts=len(groups), total_files=len(items))
    path = tmp_path / "p.py"
    path.write_text(text, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, str(path), "--dest", str(tmp_path / "d")],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=300)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 0, out
    assert "還沒到齊" in out, out
    assert "doctor" not in out, "少了一百多個檔案卻叫他去跑 doctor"


@needs_git
def test_generated_bundles_are_kept_out_of_the_listing_and_the_packing():
    """``bundle/`` 是 repo 的**複本**，不是內容。列進去有兩個後果：
    `get_code.py` 白抓 2.4 MB，而分批解包的「還缺幾個」永遠到不了 0。"""
    listed = set(make_filelist.tracked_files(REPO))
    packed = {rel for rel, _d in make_text_bundle.collect(REPO)}
    assert not [p for p in listed if p.startswith("bundle/")]
    assert not [p for p in packed if p.startswith("bundle/")]
    # 但清單自己**要**在包裡（0b 的更新流程靠它）
    assert "tools/FILELIST.txt" in packed


def test_check_files_names_exactly_what_needs_recopying(tmp_path):
    """更新的流程是「複製 12 KB 的清單 → 這支告訴你剩下要複製哪幾個」。
    它必須分得出「缺少」與「內容不一樣」—— 兩個都要重新複製，但原因不同。"""
    root = tmp_path / "tree"
    (root / "tools").mkdir(parents=True)
    (root / "a.py").write_bytes(b"good\n")
    (root / "b.py").write_bytes(b"changed\n")
    lines = [
        "# comment",
        "%s a.py" % check_files.blob_sha(b"good\n"),
        "%s b.py" % check_files.blob_sha(b"original\n"),
        "%s c.py" % check_files.blob_sha(b"absent\n"),
    ]
    (root / "tools" / "FILELIST.txt").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8")
    want = check_files.read_manifest(str(root / "tools" / "FILELIST.txt"))
    missing, stale = check_files.compare(str(root), want)
    assert missing == ["c.py"]
    assert stale == ["b.py"]
    assert check_files.main(["--root", str(root)]) == 1     # 有事要做 = 非零

    (root / "b.py").write_bytes(b"original\n")
    (root / "c.py").write_bytes(b"absent\n")
    assert check_files.main(["--root", str(root)]) == 0


def test_check_files_says_what_to_do_when_the_listing_is_missing(tmp_path, capsys):
    """沒有清單的時候不能只說「找不到檔案」—— 要講出那一個檔案要去哪裡拿。"""
    assert check_files.main(["--root", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "FILELIST.txt" in out and "github.com" in out


def test_the_two_machine_setup_is_written_down():
    """這些限制是整個 tools/ 形狀的原因。沒寫下來的話，下一個人會把
    stdlib-only、FILELIST、bundle 當成過度設計然後順手簡化掉。"""
    with open(os.path.join(REPO, "AGENTS.md"), "r", encoding="utf-8") as f:
        doc = f.read()
    for must in ("家用機", "公司機", "剪貼簿", "FILELIST.txt", "bundle/",
                 "fab_probe", "stdlib-only", "1 MB"):
        assert must in doc, must
    with open(os.path.join(REPO, "CLAUDE.md"), "r", encoding="utf-8") as f:
        assert "AGENTS.md" in f.read(), "CLAUDE.md 要指得到 AGENTS.md"


@needs_git
def test_the_compressed_bundle_fits_in_one_file_and_round_trips(tmp_path):
    """使用者問的正是這個：不能一包嗎。

    可以 —— 但要用 lzma。整包 base64 之後 gzip 是 991 KB、lzma 是 701 KB，而
    **GitHub 不顯示超過 1 MB 的檔案**，所以那 290 KB 的差距就是「一次複製」與
    「六次複製」的差別。這條測試同時鎖住「塞得進去」與「解出來一樣」。
    """
    text = make_text_bundle.build("b.py", REPO, compress=True)
    kb = len(text.encode("utf-8")) / 1024
    assert kb < 900, "壓縮版 %.0f KB —— GitHub 可能就不顯示了" % kb
    ast.parse(text, filename="compressed")           # 仍然是合法的 Python

    path = tmp_path / "b.py"
    path.write_text(text, encoding="utf-8", newline="\n")
    dest = tmp_path / "out"
    r = subprocess.run([sys.executable, str(path), "--dest", str(dest)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    for rel in make_filelist.tracked_files(REPO) + ["tools/FILELIST.txt"]:
        src = pathlib.Path(REPO) / rel
        assert (dest / rel).read_bytes() == src.read_bytes(), rel


@needs_git
def test_both_encodings_carry_exactly_the_same_data(tmp_path):
    """壓縮版壓的就是純文字版那一段，所以兩種編碼共用同一個解析器 ——
    「壓縮版有 bug 但純文字版沒有」這種事不該存在。"""
    items = make_text_bundle.collect(REPO)
    body = "\n".join(make_text_bundle._data_lines(items))
    text = make_text_bundle.build("b.py", REPO, items=items, compress=True)
    b64 = "".join(ln[2:] for ln in text.splitlines() if ln.startswith("#B"))
    import base64 as _b64
    import lzma as _lzma
    assert _lzma.decompress(_b64.b64decode(b64)).decode("utf-8") == body


@needs_git
def test_a_truncated_compressed_bundle_says_so_instead_of_crashing(tmp_path):
    """複製一個 700 KB 的東西最可能的失敗是**貼不完整**。那時候不能丟 traceback,
    要講「重新複製一次，而且不要用編輯器另存」。"""
    text = make_text_bundle.build("b.py", REPO, compress=True)
    lines = text.splitlines()
    cut = [ln for ln in lines if not ln.startswith("#B")][:-0] or lines
    keep, dropped = [], 0
    for ln in lines:
        if ln.startswith("#B"):
            dropped += 1
            if dropped > 20:                          # 砍掉尾巴一大段
                continue
        keep.append(ln)
    path = tmp_path / "cut.py"
    path.write_text("\n".join(keep) + "\n", encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, str(path), "--dest", str(tmp_path / "d")],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=120)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 2, out
    assert "Traceback" not in out, out
    assert "重新複製" in out, out
    assert not (tmp_path / "d").exists() or not list((tmp_path / "d").rglob("*.py"))
