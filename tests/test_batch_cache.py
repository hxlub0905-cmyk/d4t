# d4t M2 驗收 — authored 2026-07-28.
"""M2 驗收：平行批次（run_batch）+ 影像段快取（StageCache / run_defect_cached）。

鐵則：快取/平行的結果必須與 M1 循序 run_dataset **位元級一致**
（features / score / bin），快取層任何故障都只能退回重算、不准 crash。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import (  # noqa: E402
    Recipe,
    RecipeNode,
    ScoreSpec,
    StageCache,
    image_segment_signature,
    result_to_json_dict,
    run_batch,
    run_dataset,
    run_defect,
    run_defect_cached,
)
from d4t.core.pipeline.batch import pin_cv2_deterministic  # noqa: E402
from d4t.core.pipeline.cache import dataset_token  # noqa: E402

N = 12
KIND = "ebi_patch"


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _cv2_deterministic():
    """cv2 的 IPP kernel（Sobel 等）結果會隨 buffer 位址飄 1e-8 級雜訊 ——
    同一顆同參數兩次重算都不保證 bit 相同。本模組把 parent 進程調成與
    run_batch worker 相同的 deterministic 模式（threads=1 + IPP off，
    見 batch.pin_cv2_deterministic），「快取/平行 vs 循序位元級一致」的
    驗收才有意義。測完還原，不污染其他測試。"""
    import cv2
    prev_threads = cv2.getNumThreads()
    try:
        prev_ipp = cv2.ipp.useIPP()
    except Exception:
        prev_ipp = None
    pin_cv2_deterministic()
    try:
        yield
    finally:
        cv2.setNumThreads(prev_threads)
        if prev_ipp is not None:
            cv2.ipp.setUseIPP(prev_ipp)


@pytest.fixture(scope="module")
def synlot(tmp_path_factory):
    out = tmp_path_factory.mktemp("m2lot")
    return generate(str(out), n=N, seed=7)


@pytest.fixture(scope="module")
def ds(synlot):
    d = load_dataset(synlot["klarf"])
    assert d.kind == KIND and len(d.items) == N
    return d


def make_recipe(snr_threshold: float = 200.0, search_radius: int = 8) -> Recipe:
    """die-to-die 節點組（同 tests/fixtures/recipes/die_to_die_basic.json）。"""
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        # 一張卡一條流（F7-18）：ref 先做（借 test 還沒被拉伸的範圍），test 再做。
        "norm_ref": RecipeNode("norm_ref", "normalize",
                               {"streams": "ref", "range_from": "test"}),
        "norm": RecipeNode("norm", "normalize", {"streams": "test"}),
        "align": RecipeNode("align", "align",
                            {"method": "phase", "search_radius": search_radius}),
        "sub": RecipeNode("sub", "subtract", {}),
        "dn": RecipeNode("dn", "denoise",
                         {"streams": "diff", "method": "median", "ksize": 3}),
        "snr": RecipeNode("snr", "snr_map", {"window": 15, "exclude_border": 8}),
        "cd": RecipeNode("cd", "cd_measure", {"source": "diff"}),
        "glv": RecipeNode("glv", "glv_stats",
                          {"source": "diff",
                           "metrics": "glv_max,glv_q99,glv_mean"}),
    }
    return Recipe(
        recipe_id="m2_batch_cache_test",
        routes={KIND: ["load", "norm_ref", "norm", "align", "sub", "dn",
                       "snr", "cd", "glv"]},
        nodes=nodes,
        score=ScoreSpec(expr="glv_max + (glv_max - glv_q99)", threshold=50.0,
                        bins={"below": 0, "above": 1}),
    )


def _slim(d: dict) -> dict:
    """run_batch dict → 只留可比對欄位（traces 的 ms 每次都不同）。"""
    return {k: d[k] for k in ("defect_id", "ok", "error",
                              "features", "score", "bin")}


def _assert_same_features(a: dict, b: dict) -> None:
    """位元級一致（NaN 視為相等 —— 雖然本 recipe 不該產 NaN）。"""
    assert set(a) == set(b)
    for k in a:
        va, vb = float(a[k]), float(b[k])
        if math.isnan(va) or math.isnan(vb):
            assert math.isnan(va) and math.isnan(vb), k
        else:
            assert va == vb, (k, va, vb)


def _assert_same_result(ra, rb) -> None:
    """兩個 DefectResult：ok / features / score / bin 位元級一致。"""
    assert ra.defect_id == rb.defect_id
    assert ra.ok == rb.ok and ra.error == rb.error
    _assert_same_features(ra.features, rb.features)
    assert ra.score == rb.score
    assert ra.bin == rb.bin


# ---------------------------------------------------------------------------
# 1. serial vs parallel vs M1 run_dataset：全部一致
# ---------------------------------------------------------------------------
def test_serial_parallel_and_m1_agree(ds):
    rec = make_recipe()
    serial = run_batch(rec, ds, workers=1)
    parallel = run_batch(rec, ds, workers=2)      # 真開 ProcessPool
    m1 = [result_to_json_dict(r) for r in run_dataset(rec, ds)]

    assert len(serial) == len(parallel) == len(m1) == N
    # 原始 item 順序（parallel 的 as_completed 亂序要被排回來）
    assert [d["defect_id"] for d in serial] == [d["defect_id"] for d in m1]
    assert [d["defect_id"] for d in parallel] == [d["defect_id"] for d in m1]
    for a, b, c in zip(serial, parallel, m1):
        assert _slim(a) == _slim(b) == _slim(c)
    assert all(d["ok"] for d in serial)


def test_run_batch_limit_and_progress(ds):
    rec = make_recipe()
    calls = []
    out = run_batch(rec, ds, workers=1, limit=4,
                    progress=lambda done, total, d: calls.append((done, total)))
    assert len(out) == 4
    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]


# ---------------------------------------------------------------------------
# 2. 快取：首跑全 miss、再跑全 hit，結果與無快取完全一致
# ---------------------------------------------------------------------------
def test_cache_miss_then_hit_bit_identical(ds, synlot, tmp_path):
    rec = make_recipe()
    token = dataset_token(synlot["klarf"])
    cache = StageCache(str(tmp_path / "cache"))

    first = [run_defect_cached(rec, it, KIND, cache, token) for it in ds.items]
    assert cache.misses == N and cache.hits == 0
    st = cache.stats()
    assert st["n_files"] == N and st["bytes"] > 0

    second = [run_defect_cached(rec, it, KIND, cache, token) for it in ds.items]
    assert cache.hits == N and cache.misses == N

    plain = [run_defect(rec, it, KIND) for it in ds.items]
    for a, b, c in zip(first, second, plain):
        assert a.ok and b.ok and c.ok
        _assert_same_result(a, c)
        _assert_same_result(b, c)

    cache.clear()
    assert cache.stats() == {"n_files": 0, "bytes": 0}


# ---------------------------------------------------------------------------
# 3. 改「算法段」參數：簽章不變 → 全 hit，結果與 fresh full run 一致
# ---------------------------------------------------------------------------
def test_algo_param_change_keeps_cache(ds, synlot, tmp_path):
    rec_a = make_recipe(snr_threshold=200.0)
    rec_b = make_recipe(snr_threshold=180.0)
    sig_a, ck_a = image_segment_signature(rec_a, KIND)
    sig_b, ck_b = image_segment_signature(rec_b, KIND)
    assert sig_a == sig_b
    assert ck_a == ck_b == 6      # load, norm_ref, norm, align, sub, dn 之後

    token = dataset_token(synlot["klarf"])
    cache = StageCache(str(tmp_path / "cache"))
    for it in ds.items:
        run_defect_cached(rec_a, it, KIND, cache, token)
    assert cache.misses == N and cache.hits == 0

    tuned = [run_defect_cached(rec_b, it, KIND, cache, token) for it in ds.items]
    assert cache.hits == N        # 全 hit：影像段沒重算
    fresh = [run_defect(rec_b, it, KIND) for it in ds.items]
    for a, b in zip(tuned, fresh):
        _assert_same_result(a, b)


# ---------------------------------------------------------------------------
# 4. 改「影像段」參數：簽章改變 → 全 miss
# ---------------------------------------------------------------------------
def test_image_param_change_invalidates_cache(ds, synlot, tmp_path):
    rec_a = make_recipe(search_radius=8)
    rec_b = make_recipe(search_radius=6)
    sig_a, _ = image_segment_signature(rec_a, KIND)
    sig_b, _ = image_segment_signature(rec_b, KIND)
    assert sig_a != sig_b

    token = dataset_token(synlot["klarf"])
    cache = StageCache(str(tmp_path / "cache"))
    for it in ds.items:
        run_defect_cached(rec_a, it, KIND, cache, token)
    assert cache.misses == N

    retuned = [run_defect_cached(rec_b, it, KIND, cache, token) for it in ds.items]
    assert cache.misses == 2 * N and cache.hits == 0     # 全 miss
    assert cache.stats()["n_files"] == 2 * N             # 兩套簽章各一份
    fresh = [run_defect(rec_b, it, KIND) for it in ds.items]
    for a, b in zip(retuned, fresh):
        _assert_same_result(a, b)


def test_dataset_token_changes_when_lot_regenerated(tmp_path):
    paths = generate(str(tmp_path / "lot"), n=2, seed=1)
    t1 = dataset_token(paths["klarf"])
    # 重寫 KLARF（模擬重產 lot）→ mtime/size 變 → token 變
    p = Path(paths["klarf"])
    p.write_text(p.read_text() + "\n")
    assert dataset_token(paths["klarf"]) != t1


# ---------------------------------------------------------------------------
# 5. 快取故障（壞檔 / 寫不進去）→ 不 crash、結果照樣正確
# ---------------------------------------------------------------------------
def test_corrupt_cache_file_falls_back(ds, synlot, tmp_path):
    rec = make_recipe()
    token = dataset_token(synlot["klarf"])
    cache = StageCache(str(tmp_path / "cache"))
    item = ds.items[0]
    plain = run_defect(rec, item, KIND)

    sig, _ = image_segment_signature(rec, KIND)
    key = cache.make_key(token, item.defect_id, sig)
    shard = Path(cache.dir) / key[:2]
    shard.mkdir(parents=True, exist_ok=True)
    (shard / (key + ".npz")).write_bytes(b"\x00this is not an npz\xff")

    r = run_defect_cached(rec, item, KIND, cache, token)
    assert r.ok
    _assert_same_result(r, plain)
    assert cache.misses == 1      # 壞檔算 miss（且已被 put 換成好檔）
    assert cache.get(key) is not None and cache.hits == 1


def test_unwritable_cache_falls_back(ds, synlot, tmp_path):
    rec = make_recipe()
    token = dataset_token(synlot["klarf"])
    cache = StageCache(str(tmp_path / "cache"))
    item = ds.items[0]
    plain = run_defect(rec, item, KIND)

    sig, _ = image_segment_signature(rec, KIND)
    key = cache.make_key(token, item.defect_id, sig)
    # 用「檔案」佔住 shard 目錄名 → put 的 makedirs 必爆（root 也擋得住）
    (Path(cache.dir) / key[:2]).write_text("blocker")

    r = run_defect_cached(rec, item, KIND, cache, token)   # 不准 crash
    assert r.ok
    _assert_same_result(r, plain)
    assert cache.stats()["n_files"] == 0                   # 沒寫成也沒殘骸

    # get 也拿不到（shard 是檔案）→ 再跑一次仍正確
    r2 = run_defect_cached(rec, item, KIND, cache, token)
    assert r2.ok
    _assert_same_result(r2, plain)


# ---------------------------------------------------------------------------
# 6. abort_check：3 顆後喊停 → 回傳部分結果
# ---------------------------------------------------------------------------
def test_abort_returns_partial(ds):
    rec = make_recipe()
    seen = []
    results = run_batch(rec, ds, workers=1,
                        progress=lambda done, total, d: seen.append(done),
                        abort_check=lambda: len(seen) >= 3)
    assert 3 <= len(results) < N
    assert all(d["ok"] for d in results)


# ---------------------------------------------------------------------------
# 7. 平行 + 快取整合：真開 pool、cache_dir 共用、結果一致
# ---------------------------------------------------------------------------
def test_run_batch_parallel_with_cache(ds, tmp_path):
    rec = make_recipe()
    cdir = str(tmp_path / "batch_cache")

    r1 = run_batch(rec, ds, workers=2, cache_dir=cdir)   # 首跑：workers 建快取
    assert StageCache(cdir).stats()["n_files"] == N
    r2 = run_batch(rec, ds, workers=2, cache_dir=cdir)   # 再跑：全 hit
    base = run_batch(rec, ds, workers=1)                 # 無快取循序基準

    assert len(r1) == len(r2) == len(base) == N
    for a, b, c in zip(r1, r2, base):
        assert _slim(a) == _slim(b) == _slim(c)


# ---------------------------------------------------------------------------
# 8. 快照必須涵蓋整個 Context —— 不只 images / features / meta（F7-9 迴歸）
# ---------------------------------------------------------------------------
def _roi_then_image_recipe() -> Recipe:
    """一份**很自然**、但會踩到快取切點的 recipe。

    checkpoint 是執行順序上的**位置**（最後一張影像段卡的下一格），不是
    「所有影像段的卡」。所以「先框出要看的地方，再做影像處理，最後量測」
    這個順序會把 Region 卡（algo）夾在快取段裡面。
    """
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        # ROI 卡在 F8 第五輪只剩 Profile / Template / GDS —— 這裡用 Profile
        # （``roi_cross``），它跟被拿掉的 ``roi_define`` 一樣是 algo 段，
        # 一樣會落在快取段裡面，所以這條迴歸測的東西沒有變。
        "roi": RecipeNode("roi", "roi_cross",
                          {"source": "test", "roi_out": "main"}),
        "dn": RecipeNode("dn", "denoise",
                         {"streams": "test", "method": "median", "ksize": 3}),
        "glv": RecipeNode("glv", "glv_stats",
                          {"source": "test", "roi": "main"}),
    }
    return Recipe(recipe_id="roi_in_cached_segment",
                  routes={KIND: ["load", "roi", "dn", "glv"]}, nodes=nodes,
                  score=ScoreSpec(expr="glv_mean", threshold=0.0,
                                  bins={"below": 0, "above": 1}))


def test_named_rois_survive_a_cache_hit(ds, tmp_path):
    """第一次跑對、第二次跑錯，是最難查的一種 bug。

    v1 的快照只存 images/features/meta，``ctx.rois`` 沒有存 —— 快取命中時
    整個具名 ROI 表是空的，量測卡就報「region 'main' is not defined」。
    """
    rec = _roi_then_image_recipe()
    _sig, ckpt = image_segment_signature(rec, KIND)
    assert ckpt == 3, "前提：roi 卡確實落在快取段裡（不然這條測試沒在測東西）"

    cache = StageCache(str(tmp_path / "roi_cache"))
    token = dataset_token(ds.klarf_path if hasattr(ds, "klarf_path") else "lot")
    item = ds.items[0]

    first = run_defect_cached(rec, item, KIND, cache, token)
    second = run_defect_cached(rec, item, KIND, cache, token)
    assert cache.hits >= 1, "第二次應該要命中快取，不然沒測到那條路徑"

    assert first.ok is True, first.error
    assert second.ok is True, second.error
    _assert_same_result(first, second)

    # 而且要跟完全不用快取的結果一致
    _assert_same_result(first, run_defect(rec, item, KIND))


def test_an_old_format_snapshot_is_ignored_instead_of_trusted(ds, tmp_path):
    """使用者的快取目錄可能是舊版寫的（缺 rois 欄位）。

    版本對不上就當 miss 重算 —— 不然升級之後第一次跑仍然會踩到舊的殘缺快照。
    """
    import json

    import numpy as np

    cache = StageCache(str(tmp_path / "old"))
    key = cache.make_key("tok", "d1", "sig")
    path = cache._path(key)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {"image_names": ["test"], "features": {}, "meta": {}}   # 無 version
    np.savez_compressed(path, **{"img__test": np.zeros((4, 4), np.uint8),
                                 "__payload__": np.array(json.dumps(payload))})
    assert cache.get(key) is None
    assert cache.misses == 1


def test_a_multi_box_roi_survives_a_cache_hit_with_every_box():
    """**一個名字可能有好幾個框**（F8 的交會定位），而還原時逐一 ``set_roi``
    是錯的 —— 它會先刪掉同名的，17 個框還原完只剩最後一個。

    這是 F7-9 那條「第一次跑對、第二次跑錯」的第二形態，而且更難發現：
    不是整組不見（那會報 region not defined），是**只剩一個**，兩邊都跑得完、
    都有數字，只有數字不一樣。
    """
    import numpy as np

    from d4t.core.pipeline.context import Context
    from d4t.core.pipeline.engine import _restore_context, _roi_snapshot

    ctx = Context(images={"test": np.zeros((32, 32), np.float32)})
    boxes = [(i / 10.0, 0.1, 0.05, 0.2) for i in range(6)]
    ctx.set_roi_boxes("xing", boxes)
    ctx.set_roi("one", (0.4, 0.4, 0.2, 0.2))
    assert ctx.roi_count("xing") == 6

    snap = {"images": {}, "features": {}, "meta": {},
            "rois": _roi_snapshot(ctx), "labels": None}
    back = _restore_context(_FakeItem(), KIND, "1", snap)

    assert back.roi_count("xing") == 6, \
        "多框區域還原之後只剩 %d 個" % back.roi_count("xing")
    assert back.roi_count("one") == 1
    assert back.roi_names() == ["xing", "one"]


class _FakeItem:
    """``_seed_context`` 只會讀這幾個欄位。"""
    defect_id = "1"
    test_path = ref_path = None
    test_page = ref_page = 0
    meta: dict = {}


# ---------------------------------------------------------------------------
# 12. F9-3 的歸屬要活得過快取（冷跑 = 熱跑）
# ---------------------------------------------------------------------------
def test_feature_ownership_survives_a_cache_hit(ds, tmp_path):
    """撞名**跨越 checkpoint** 時，冷跑與熱跑要算出一模一樣的東西。

    F9-3 讓被蓋掉的特徵留下來（``<前一張卡的節點名>_<原名>``），而那件事靠的是
    「誰產出了哪個特徵」這份帳。checkpoint 之前的節點在熱跑時**根本沒有執行**
    —— 帳如果沒跟著快照走，熱跑就不知道 ``glv_max`` 本來是誰的，於是**不會**
    救、少一個特徵。

    那正是這個 repo 踩過兩次的形態：冷跑對、熱跑錯，兩邊都跑得完、都有數字
    （F7-9 的 `region 'main' is not defined`、39b9fea 的「17 個框只剩 1 個」）。

    這裡刻意讓兩張卡都吐 ``align_dx``：align 是影像段（在 checkpoint 之前），
    後面那張是算法段（在 checkpoint 之後），所以撞名一定跨越 checkpoint。
    """
    from d4t.core.pipeline.step import (CATEGORY_ALGO, REGISTRY, ParamSpec,
                                          Step, register_step)
    from d4t.core.pipeline.context import Context as Ctx

    key = "t_f94_shadow"
    REGISTRY.pop(key, None)

    @register_step
    class TF94Shadow(Step):
        key = "t_f94_shadow"
        label = "測試遮蔽"
        category = CATEGORY_ALGO           # ← 算法段：落在 checkpoint 之後
        help = "測試用：吐一個跟 align 撞名的特徵"
        reads = ["diff"]
        features_out = ["align_dx"]
        params = [ParamSpec("value", "float", 99.0, "要吐的值")]

        def run(self, ctx: Ctx, params) -> Ctx:
            ctx.add_feature("align_dx", float(params["value"]))
            return ctx

    try:
        rec = make_recipe()
        rec.nodes["shadow"] = RecipeNode("shadow", key, {"value": 99.0})
        rec.routes[KIND] = list(rec.routes[KIND]) + ["shadow"]

        cache = StageCache(str(tmp_path / "cache_own"))
        item = ds.items[0]

        cold = run_defect_cached(rec, item, KIND, cache, "tok")
        assert cache.misses == 1 and cache.hits == 0
        warm = run_defect_cached(rec, item, KIND, cache, "tok")
        assert cache.hits == 1

        assert cold.ok and warm.ok, (cold.error, warm.error)
        # 遮蔽有效：align_dx 是後面那張卡的值
        assert cold.features["align_dx"] == 99.0
        # 被蓋掉的那份救得回來，而且**熱跑也要有**
        assert "align_align_dx" in cold.features, sorted(cold.features)
        _assert_same_features(cold.features, warm.features)
        assert cold.score == warm.score and cold.bin == warm.bin
    finally:
        REGISTRY.pop(key, None)
