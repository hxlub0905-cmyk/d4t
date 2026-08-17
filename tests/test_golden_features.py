# F9 的安全網：重構前後，每一個數字都要一樣 — authored 2026-08-16 (F9-0).
"""**預設不跑。** 要跑：``ADEPT_GOLDEN=1 pytest -q tests/test_golden_features.py``

為什麼要有這一支
----------------
F9（影像流綁在線上）動的是引擎的地基。這種重構最危險的失敗**不是跑不動**——
跑不動當場就看得到。危險的是**跑得動、而答案悄悄變了**：測試全綠、畫面正常，
只有分數跟上禮拜不一樣，而沒有人會發現。這個 repo 已經有過一次那樣的東西
（2026-08-16 的 subtract 遷移，`workers=1` 與 `workers=4` 算出不同分數）。

所以動地基之前先把「現在算出來的每一個數字」凍起來
（`python tools/freeze_golden.py`），之後每改完一段就對一次。

為什麼預設 skip
---------------
凍下來的是**浮點數**，會隨 numpy / OpenCV 版本漂移。CI 跑 3.9 / 3.11 / 3.12
三種環境，家用機又是另一種 —— committed 的值不可能在每一台都逐位元組相同，
硬要它綠只會逼出「調寬容差直到它閉嘴」，那時這份東西就再也擋不住任何事。

而它的用途本來就不是跨機器重現，是**同一台機器上、重構前後的比較**：

1. 開始 F9 之前，在你自己的機器上 ``python tools/freeze_golden.py``；
2. 每改完一段 ``ADEPT_GOLDEN=1 pytest -q tests/test_golden_features.py``；
3. 數字真的該變的時候重新凍一次，並在 commit 訊息裡說明為什麼。

換句話說：**它是一把尺，不是一道門。** 門是其他 885 條測試。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import freeze_golden                                      # noqa: E402

ENABLED = os.environ.get("ADEPT_GOLDEN", "").strip().lower() in ("1", "true", "yes")

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason="黃金值是浮點數、跨環境會漂移 —— 設 ADEPT_GOLDEN=1 才跑（見檔頭）")


@pytest.mark.parametrize(
    "case", freeze_golden.CASES,
    ids=lambda c: "%s-%s" % (Path(c[0]).stem, c[1]))
def test_the_numbers_did_not_move(case):
    """凍起來的每一顆 defect、每一個特徵，都要跟現在算出來的逐項相同。"""
    import json

    recipe_file, gen, n, seed = case
    path = Path(freeze_golden.golden_path(recipe_file, gen))
    if not path.is_file():
        pytest.skip("%s 還沒凍過 —— 先跑 python tools/freeze_golden.py" % path.name)

    new = freeze_golden.compute(recipe_file, gen, n, seed)
    if new.get("skipped"):
        pytest.skip(str(new["skipped"]))
    old = json.loads(path.read_text(encoding="utf-8"))

    lines = freeze_golden._diff(old, new)
    assert not lines, (
        "%s：%d 處的數字變了。如果不是刻意的，那就是重構動到了行為。\n%s"
        % (path.name, len(lines), "\n".join("  " + s for s in lines[:20])))


def test_the_golden_files_exist_and_look_sane():
    """凍出來的東西本身要合理 —— 不能是一份空表然後永遠綠。

    這個 repo 踩過五次「測試通過，只是什麼都沒測」，所以這一條特地在這裡。
    """
    seen = 0
    for recipe_file, gen, _n, _seed in freeze_golden.CASES:
        path = Path(freeze_golden.golden_path(recipe_file, gen))
        if not path.is_file():
            continue
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        defects = data.get("defects") or {}
        assert defects, "%s 裡沒有任何 defect" % path.name
        for did, row in defects.items():
            assert row.get("features"), "%s 的 defect %s 沒有任何特徵" % (path.name, did)
        seen += 1
    assert seen >= 1, "一份黃金值都沒有 —— 先跑 python tools/freeze_golden.py"
