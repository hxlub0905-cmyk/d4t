"""M2 驗收：RunStore（SQLite 批次歷史）＋ rescore（不重跑影像的重算分）。

不需要真影像 —— 全部用 result_to_json_dict 形狀的假 result dict。
每個測試各開自己的 tmp_path db，互不干擾。
"""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
import time

import pytest

from adept.core.pipeline import Recipe, RecipeNode, ScoreSpec
from adept.core.store import RunStore, rescore


# ---------------------------------------------------------------------------
# 假資料工廠
# ---------------------------------------------------------------------------
def _recipe_dict(expr="snr_max * 2", threshold=4.0, bins=None):
    """最小 recipe JSON dict（save_run 也吃 dict，不強制 Recipe 物件）。"""
    return {
        "recipe_id": "t_store",
        "version": 1,
        "author": "HX",
        "description": "store 測試用",
        "routes": {"ebi_patch": []},
        "nodes": {},
        "edges": [],
        "score": {"expr": expr, "threshold": threshold,
                  "bins": dict(bins or {"below": 0, "above": 1})},
    }


def _fake_result(i, *, feats=None, ok=True, error=None):
    """result_to_json_dict 形狀（traces 不入庫，但保留在輸入裡驗證會被忽略）。"""
    if feats is None:
        feats = {
            "snr_max": float(i),
            "blob_area": float(i * 3 + 1),
            "cd_x_nm": 20.0 + i * 0.5,
            "glv_mean": 128.0,
            "glv_std": 7.5,
            "focus": 0.8,
            "dvi": -1.25,
            "score": float(i) * 2.0,
        }
    return {
        "defect_id": "D{:05d}".format(i),
        "ok": ok,
        "error": error,
        "features": feats,
        "score": feats.get("score"),
        "bin": (1 if feats.get("score", 0.0) is not None
                and (feats.get("score") or 0.0) >= 4.0 else 0) if ok else None,
        "traces": [{"node_id": "x", "step_key": "t", "ok": True, "ms": 0.1,
                    "error": None, "features_added": {}, "images_after": []}],
    }


def _make_results(n, fail_every=None):
    out = []
    for i in range(n):
        if fail_every and i % fail_every == 0:
            out.append(_fake_result(i, feats={}, ok=False,
                                    error="[align] 對位失敗（測試用）"))
        else:
            out.append(_fake_result(i))
    return out


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------
def test_save_load_roundtrip_120_rows(tmp_path):
    db = str(tmp_path / "runs.db")
    results = _make_results(120, fail_every=10)  # 12 顆 FAIL
    # 一顆的特徵塞 nan / inf → 存檔要變 None（JSON 安全）
    results[5]["features"]["snr_max"] = float("nan")
    results[5]["features"]["blob_area"] = float("inf")
    results[5]["score"] = float("nan")

    with RunStore(db) as store:
        run_id = store.save_run(
            _recipe_dict(), results,
            klarf_path="/data/lot1.001", dataset_kind="ebi_patch",
            notes="回歸測試批")

        run = store.get_run(run_id)
        assert run["run_id"] == run_id
        assert run["recipe_id"] == "t_store"
        assert run["klarf_path"] == "/data/lot1.001"
        assert run["dataset_kind"] == "ebi_patch"
        assert run["notes"] == "回歸測試批"
        assert run["n_total"] == 120
        assert run["n_ok"] == 108
        assert run["n_fail"] == 12
        assert json.loads(run["recipe_json"])["score"]["expr"] == "snr_max * 2"

        rows = list(store.iter_results(run_id))
        assert len(rows) == 120
        by_id = {r["defect_id"]: r for r in rows}
        # features 已解析回 dict；一般顆數值原樣回來
        r7 = by_id["D00007"]
        assert r7["ok"] is True and r7["error"] is None
        assert r7["features"]["snr_max"] == 7.0
        assert r7["features"]["cd_x_nm"] == pytest.approx(23.5)
        assert r7["score"] == 14.0 and r7["bin"] == 1
        # nan/inf → None
        r5 = by_id["D00005"]
        assert r5["features"]["snr_max"] is None
        assert r5["features"]["blob_area"] is None
        assert r5["score"] is None
        # FAIL 顆：空 features、error 保留
        r10 = by_id["D00010"]
        assert r10["ok"] is False and "對位失敗" in r10["error"]
        assert r10["features"] == {} and r10["bin"] is None

        ids, feats = store.get_features_table(run_id)
        assert len(ids) == len(feats) == 120
        assert ids[0] == "D00000"
        assert feats[7]["snr_max"] == 7.0


def test_save_run_accepts_recipe_object(tmp_path):
    recipe = Recipe(
        recipe_id="t_obj",
        routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode(id="load", step="load_patch", params={})},
        score=ScoreSpec(expr="snr_max", threshold=3.0, bins={"below": 0, "above": 1}),
    )
    with RunStore(str(tmp_path / "runs.db")) as store:
        run_id = store.save_run(recipe, _make_results(3))
        run = store.get_run(run_id)
        assert run["recipe_id"] == "t_obj"
        assert json.loads(run["recipe_json"])["score"]["threshold"] == 3.0


def test_list_runs_newest_first_without_recipe_json(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        ids = [store.save_run(_recipe_dict(), _make_results(2),
                              notes="第 {} 批".format(k)) for k in range(3)]
        runs = store.list_runs()
        assert [r["run_id"] for r in runs] == list(reversed(ids))  # 新的在前
        for r in runs:
            assert "recipe_json" not in r
            assert r["n_total"] == 2


def test_delete_run_cascade(tmp_path):
    db = str(tmp_path / "runs.db")
    with RunStore(db) as store:
        keep = store.save_run(_recipe_dict(), _make_results(5))
        gone = store.save_run(_recipe_dict(), _make_results(7))
        store.delete_run(gone)

        with pytest.raises(KeyError):
            store.get_run(gone)
        with pytest.raises(KeyError):
            list(store.iter_results(gone))
        assert len(list(store.iter_results(keep))) == 5  # 別的 run 不受影響

    # 直接開第二條連線驗證 results 列真的被 CASCADE 掉
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM results WHERE run_id=?",
                         (gone,)).fetchone()[0]
        assert n == 0
        n_keep = conn.execute("SELECT COUNT(*) FROM results WHERE run_id=?",
                              (keep,)).fetchone()[0]
        assert n_keep == 5
    finally:
        conn.close()


def test_run_id_uniqueness_and_format_across_rapid_saves(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        ids = [store.save_run(_recipe_dict(), []) for _ in range(30)]
        assert len(set(ids)) == 30
        for rid in ids:
            assert re.match(r"^\d{8}T\d{4}-[0-9a-f]{6}$", rid), rid
        # 指定 run_id 時原樣使用
        assert store.save_run(_recipe_dict(), [], run_id="my-run") == "my-run"


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------
def test_export_csv_header_union_and_bom(tmp_path):
    db = str(tmp_path / "runs.db")
    out = str(tmp_path / "out.csv")
    results = [
        _fake_result(0, feats={"snr_max": 1.5, "blob_area": 9.0, "score": 3.0}),
        _fake_result(1, feats={"snr_max": 2.5, "cd_x_nm": 21.0, "score": 5.0}),
        _fake_result(2, feats={}, ok=False, error="[load] 讀檔失敗（測試）"),
    ]
    with RunStore(db) as store:
        run_id = store.save_run(_recipe_dict(), results)
        store.export_csv(run_id, out)

    with open(out, "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"  # utf-8-sig BOM（Excel 直開不亂碼）

    with open(out, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]
    # 基本欄 + 排序後 feature key 聯集
    assert header == ["defect_id", "ok", "error", "score", "bin",
                      "blob_area", "cd_x_nm", "score", "snr_max"]
    assert len(data) == 3
    by_id = {r[0]: r for r in data}
    # 缺的 feature 留空；中文 error 原樣
    assert by_id["D00001"][header.index("blob_area", 5)] == ""
    assert by_id["D00001"][8] == "2.5"  # snr_max
    assert "讀檔失敗" in by_id["D00002"][2]
    assert by_id["D00002"][3] == "" and by_id["D00002"][4] == ""  # score/bin 空


# ---------------------------------------------------------------------------
# rescore
# ---------------------------------------------------------------------------
def _saved_run_for_rescore(store, n=100):
    """expr="snr_max"、threshold=50 → i<50 進 bin0、其餘 bin1。"""
    results = [_fake_result(i) for i in range(n)]
    return store.save_run(
        _recipe_dict(expr="snr_max", threshold=50.0), results,
        klarf_path="/data/lot2.001", dataset_kind="ebi_patch")


def test_rescore_threshold_only_flips_bins(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        run_id = _saved_run_for_rescore(store, n=100)  # snr_max = 0..99

        s0 = rescore(store, run_id)  # 全沿用 recipe：threshold=50
        assert s0["run_id"] == run_id
        assert s0["n"] == 100 and s0["n_errors"] == 0
        assert s0["bin_counts"] == {0: 50, 1: 50}
        assert s0["score_min"] == 0.0 and s0["score_max"] == 99.0
        assert s0["score_median"] == pytest.approx(49.5)
        assert s0["saved_run_id"] is None

        s1 = rescore(store, run_id, threshold=25.0)  # 只改門檻 → bin 數翻轉
        assert s1["bin_counts"] == {0: 25, 1: 75}
        s2 = rescore(store, run_id, threshold=90.0)
        assert s2["bin_counts"] == {0: 90, 1: 10}
        # 改 bins 對應值也要跟著走
        s3 = rescore(store, run_id, threshold=25.0, bins={"below": 7, "above": 9})
        assert s3["bin_counts"] == {7: 25, 9: 75}


def test_rescore_new_expr_saved_as_new_run(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        run_id = _saved_run_for_rescore(store, n=40)

        s = rescore(store, run_id, expr="blob_area", threshold=60.0,
                    save_as=True, notes="改用 blob_area 重算")
        # blob_area = 3i+1（i=0..39）→ < 60 者 i<=19 → 20 顆 bin0
        assert s["n"] == 40 and s["n_errors"] == 0
        assert s["bin_counts"] == {0: 20, 1: 20}
        assert s["score_max"] == 3.0 * 39 + 1

        new_id = s["saved_run_id"]
        assert new_id and new_id != run_id

        # 新 run 可讀：recipe_json 已更新、繼承 klarf_path/kind、notes 是新的
        new_run = store.get_run(new_id)
        spec = json.loads(new_run["recipe_json"])["score"]
        assert spec["expr"] == "blob_area" and spec["threshold"] == 60.0
        assert new_run["klarf_path"] == "/data/lot2.001"
        assert new_run["dataset_kind"] == "ebi_patch"
        assert new_run["notes"] == "改用 blob_area 重算"
        assert new_run["n_total"] == 40 and new_run["n_ok"] == 40

        rows = list(store.iter_results(new_id))
        by_id = {r["defect_id"]: r for r in rows}
        r10 = by_id["D00010"]
        assert r10["score"] == 31.0 and r10["bin"] == 0
        assert r10["features"]["score"] == 31.0  # features["score"] 同步更新
        assert r10["features"]["snr_max"] == 10.0  # 其他特徵原樣保留

        # 指定字串 save_as → 用該 id
        s2 = rescore(store, run_id, threshold=10.0, save_as="rescored-abc")
        assert s2["saved_run_id"] == "rescored-abc"
        assert store.get_run("rescored-abc")["n_total"] == 40


def test_rescore_missing_feature_counts_errors_without_crashing(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        results = []
        for i in range(100):
            feats = {"snr_max": float(i), "blob_area": float(i)}
            if i % 5 != 0:  # 80 顆有 cd_x_nm、20 顆缺
                feats["cd_x_nm"] = 20.0 + i
            results.append(_fake_result(i, feats=feats))
        run_id = store.save_run(
            _recipe_dict(expr="snr_max", threshold=50.0), results)

        s = rescore(store, run_id, expr="cd_x_nm * 2", threshold=100.0,
                    save_as=True)
        assert s["n"] == 100
        assert s["n_errors"] == 20  # 缺 cd_x_nm 的顆數
        assert sum(s["bin_counts"].values()) == 80  # 其餘照常算分
        assert s["score_min"] == 42.0  # i=1 → (20+1)*2

        # 存下的新 run：出錯顆 score/bin None、ok=False、有錯誤訊息
        rows = {r["defect_id"]: r for r in store.iter_results(s["saved_run_id"])}
        bad = rows["D00005"]
        assert bad["ok"] is False and bad["score"] is None and bad["bin"] is None
        assert "cd_x_nm" in bad["error"]
        good = rows["D00006"]
        assert good["ok"] is True and good["score"] == 52.0


def test_rescore_none_valued_feature_is_error_not_crash(tmp_path):
    """nan 存成 None 的特徵被表達式引用 → 該顆記錯，不殺整批。"""
    with RunStore(str(tmp_path / "runs.db")) as store:
        results = [_fake_result(i) for i in range(10)]
        results[3]["features"]["snr_max"] = float("nan")  # 存檔後變 None
        run_id = store.save_run(_recipe_dict(expr="snr_max", threshold=5.0),
                                results)
        s = rescore(store, run_id)
        assert s["n"] == 10 and s["n_errors"] == 1
        assert sum(s["bin_counts"].values()) == 9


def test_rescore_ignores_stored_score_variable(tmp_path):
    """變數空間排除舊 "score" —— 表達式引用 score 應視為缺變數。"""
    with RunStore(str(tmp_path / "runs.db")) as store:
        run_id = store.save_run(
            _recipe_dict(expr="score + 1", threshold=0.0), [_fake_result(2)])
        s = rescore(store, run_id)
        assert s["n"] == 1 and s["n_errors"] == 1  # 舊分數不可當變數


def test_rescore_10k_rows_under_5s(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as store:
        results = []
        for i in range(10_000):
            feats = {
                "snr_max": (i % 97) * 0.25,
                "blob_area": float(i % 311),
                "cd_x_nm": 18.0 + (i % 53) * 0.1,
                "glv_mean": 120.0 + (i % 17),
                "glv_std": 6.0,
                "focus": 0.5 + (i % 7) * 0.05,
                "dvi": -1.0,
                "score": 0.0,
            }
            results.append(_fake_result(i, feats=feats))
        run_id = store.save_run(
            _recipe_dict(expr="snr_max", threshold=10.0), results)

        t0 = time.perf_counter()
        s = rescore(store, run_id,
                    expr="snr_max * sqrt(blob_area) + cd_x_nm / glv_std",
                    threshold=30.0, save_as=True)
        wall = time.perf_counter() - t0

        assert s["n"] == 10_000 and s["n_errors"] == 0
        assert sum(s["bin_counts"].values()) == 10_000
        assert s["elapsed_s"] < 5.0
        assert wall < 5.0, "10k rescore 花了 {:.2f}s（目標 < 5s）".format(wall)
        assert store.get_run(s["saved_run_id"])["n_total"] == 10_000
        # 抽查一顆數值正確
        r = next(store.iter_results(s["saved_run_id"]))
        f = r["features"]
        expect = f["snr_max"] * math.sqrt(f["blob_area"]) + f["cd_x_nm"] / f["glv_std"]
        assert r["score"] == pytest.approx(expect)
