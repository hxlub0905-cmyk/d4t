# ADEPT M1 端到端驗收 — authored 2026-07-28.
"""M1 驗收：合成 KLARF+TIFF → die-to-die recipe → 分數把真/假 defect 分開。

流程：tools/make_sample 產一份合成 lot（含 ground truth）→ ingest 自動判別
ebi_patch → 範例 recipe 全 pipeline → 檢查分類正確率與分數分離。
另附 CLI（python -m adept run）煙霧測試。
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RECIPE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.ingest.dataset import load_dataset  # noqa: E402
from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402


@pytest.fixture(scope="module")
def synlot(tmp_path_factory):
    out = tmp_path_factory.mktemp("synlot")
    paths = generate(str(out), n=24, seed=7)
    return paths


def test_recipe_validates_clean():
    recipe = Recipe.load(str(RECIPE))
    issues = validate(recipe, kind="ebi_patch")
    assert not [i for i in issues if i.level == "error"], issues


def test_pipeline_separates_real_from_nuisance(synlot):
    ds = load_dataset(synlot["klarf"])
    assert ds.kind == "ebi_patch"
    gt = json.loads(Path(synlot["ground_truth"]).read_text())
    recipe = Recipe.load(str(RECIPE))

    results = run_dataset(recipe, ds)
    assert len(results) == 24
    failed = [r for r in results if not r.ok]
    assert not failed, [(r.defect_id, r.error) for r in failed]

    real = [r.score for r in results if gt[r.defect_id]["is_real"]]
    fake = [r.score for r in results if not gt[r.defect_id]["is_real"]]
    # 母體層級分離：真缺陷分數中位數需明顯高於假點
    assert statistics.median(real) > 2 * statistics.median(fake)
    # 分類正確率（seed=7 實測 24/24；門檻留餘裕 ≥ 22/24）
    correct = sum(1 for r in results if (r.bin == 1) == gt[r.defect_id]["is_real"])
    assert correct >= 22, f"分類正確 {correct}/24"
    # 每顆都要有完整 feature vector（供 ML 匯出）
    for r in results:
        for key in ("snr_max", "cd_x_px", "glv_max", "score"):
            assert key in r.features, f"{r.defect_id} 缺 {key}"


def test_cli_run_smoke(synlot, tmp_path):
    out_json = tmp_path / "results.json"
    out_csv = tmp_path / "results.csv"
    proc = subprocess.run(
        [sys.executable, "-m", "adept", "run", str(RECIPE), synlot["klarf"],
         "--out", str(out_json), "--csv", str(out_csv), "--limit", "6"],
        cwd=str(REPO), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out_json.read_text())
    assert len(payload) == 6 and all("score" in p["features"] for p in payload)
    assert out_csv.read_text(encoding="utf-8-sig").count("\n") >= 7  # header + 6 列


def test_cli_steps_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "adept", "steps"],
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0
    assert "load_patch" in proc.stdout and "影像段" in proc.stdout
