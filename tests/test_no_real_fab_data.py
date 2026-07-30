# 守門：repo 裡不得有未遮蔽的廠內識別碼。
"""這個 repo 的前提是「整包可以帶出廠、可以放在 GitHub 上」。

那個前提有一個很容易破掉的地方：**測試 fixture**。開發過程中最有價值的檔案就是
一份真實的 KLARF（`sample_real.klarf` 就是這樣抓到 variant D 的），而真實的 KLARF
裡帶著 Lot／Wafer／Device／機台／**recipe 名稱**（recipe 名稱通常編碼了層別與製程
步驟）、缺陷分類名稱，甚至廠區代號。

這些欄位對測試**完全沒有用**：`test_klarf_variant_d.py` 斷言的全部是結構
（版本、欄位佈局、ImageList 在第幾欄、round-trip 逐位元組相同），一條都不看值。
所以真實值留在裡面是純風險、零收益。

這支測試因此要求：**fixture 裡每一個會帶識別碼的欄位，值都要長得像合成的。**
它不能靠「列出不准出現的字」來檢查 —— 那等於把要保護的東西寫進 repo。
所以反過來做：白名單 + 一個明顯是合成的命名規則。

加新 fixture 而這支測試擋下來的時候，正確的做法是**遮蔽那個值**（等長替換，
`klarf_core` 是 span-splice，長度變了也不會壞，但等長比較不會動到別的斷言），
不是把真實值加進白名單。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 會帶識別碼的 KLARF 欄位（值要被檢查的）。
ID_FIELDS = (
    "LotRecord", "WaferRecord", "ScribeID", "DeviceID", "SetupID",
    "RecipeID", "ProcessEquipmentState", "InspectionStationID",
    "ClassLookupTable",
)

#: 合成值的命名規則：全大寫／數字／底線的代號，看得出「這是編出來的」。
#: 例：``AA0000.0X``（lot）、``DEV001``、``TOOL01``、``FAB01``、``LOT_SYN``、
#: ``DEV001_LAYERA_STP_BSTP_CST_DS01_E01``（recipe）。
_SYNTHETIC = re.compile(
    r"^(?:"
    r"AA\d{4}(?:\.[0-9A-Z]{1,3})?"          # lot / wafer / scribe
    r"|DEV\d{3}(?:_[0-9A-Z_]+)?"            # device / recipe
    r"|TOOL\d{2}|FAB\d{2}"                  # 機台 / 廠區
    r"|LOT_SYN[0-9A-Z_.]*|SYN[0-9A-Z_.]*"   # make_sample 產的
    r"|LAYER[0-9A-Z_]*"
    r")$"
)

#: KLARF 的通用詞彙與廠商產品名 —— 不是公司機密，留著讓 fixture 讀起來仍然真實。
_GENERIC = {
    "", "WAFER", "NOTCH", "PRIMEVISION", "No Review", "Grey VC", "JPG", "PNG",
    "TIF", "TIFF", "1", "2", "3", "24",
}

_DATE = re.compile(r"^\d{2}-\d{2}-\d{2,4}$")
_TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_IMAGE = re.compile(r"^[0-9A-Za-z_.\-]+\.(?:jpe?g|png|tiff?)$", re.I)


def _fixture_files():
    if not FIXTURES.is_dir():                       # pragma: no cover
        return []
    return sorted(p for p in FIXTURES.rglob("*") if p.is_file())


def _ok(value: str) -> bool:
    v = value.strip()
    return (v in _GENERIC or bool(_SYNTHETIC.match(v))
            or bool(_DATE.match(v)) or bool(_TIME.match(v))
            or bool(_IMAGE.match(v)))


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_identifier_fields_look_synthetic(path):
    """fixture 裡的識別碼欄位一定要長得像編出來的。"""
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):           # pragma: no cover
        pytest.skip("不是純文字檔")

    bad = []
    for line in text.splitlines():
        if not any(f in line for f in ID_FIELDS):
            continue
        for value in re.findall(r'"([^"]*)"', line):
            if not _ok(value):
                bad.append((line.strip()[:72], value))
    assert not bad, (
        "這些識別碼看起來是真的（廠區／Lot／Wafer／機台／device／recipe 名稱都算）。\n"
        "遮蔽它們 —— 等長替換，測試只看結構不看值，所以遮蔽不會弄壞任何斷言。\n"
        "不要把真實值加進白名單。\n" + "\n".join("  %s  ← %r" % b for b in bad))


def test_the_guard_would_actually_catch_a_real_looking_lot(tmp_path):
    """白名單式的檢查最容易變成「什麼都通過」—— 先證明它擋得下東西。

    **反例一律用憑空編的字，不可以用真的。** 這條規則我自己第一版就違反了：
    負面案例直接寫了真實的 lot 與機台代號，於是這支「防止真實識別碼進 repo」
    的測試本身變成了真實識別碼進 repo 的管道。抓到它的方式是把整包壓成 zip
    之後掃一遍 —— 那件事本來就該在推上去之前做。

    反例要的是**形狀**（不符合合成命名規則），不是內容。
    """
    assert _ok("AA0000.0X") is True
    assert _ok("DEV001_LAYERA_STP_BSTP_CST_DS01_E01") is True
    # 憑空編的，但形狀像真的：lot 帶尾碼、recipe 帶層別／步驟、機台是四碼＋數字
    assert _ok("QQ1234.5Z") is False
    assert _ok("WWXY_ZZZ_QQQ_VVV_UUU_TT99") is False
    assert _ok("ZZZZ99") is False


def test_at_least_one_fixture_is_actually_checked():
    """這份 parametrize 空掉的話上面那支測試會靜靜地全部跳過。"""
    files = _fixture_files()
    assert files, "tests/fixtures 沒有檔案 —— 這支守門測試就等於沒有在跑"
    assert any(p.suffix == ".klarf" for p in files)
