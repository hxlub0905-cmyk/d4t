# 每一張卡都必須成立的性質 — authored 2026-08-16.
"""**不是問「這張卡算得對不對」，是問「不管哪一張卡，這件事都成立嗎」。**

為什麼要有這個檔
----------------
其他測試檔幾乎都是「一張卡一張卡問你算得對不對」（``test_steps.py`` 那一類）。
那種測試抓不到這個專案至今出過的四個真 bug —— 它們**每一張卡單獨看都是對的**：

===========================================  ===========================================
``cd_measure`` 的 ``roi`` 指到不存在的區域   安靜地改量整張圖
快取沒存 ``ctx.rois``                        同一份 recipe 第一次跑對、第二次跑錯
``set_roi`` 逐一還原                         17 個框還原完只剩 1 個
subtract 的遷移（2026-08-16）                ``workers=1`` 與 ``workers=2`` 算出不同分數
===========================================  ===========================================

共同點是**「有一條路徑讓 pipeline 安靜地用了跟使用者宣告的不一樣的輸入」**，
而不是「演算法算錯」。所以這裡問的是整台引擎的規矩，並且**自動套用到 registry
裡的每一張卡** —— 加第 18 張卡的人不必記得來補，它自己會被納管。

這一檔目前鎖六條：

* **I1 同一份輸入跑兩次，答案要一樣。** 抓的是演算法自己的非決定性（OpenCV 的
  IPP 路徑、未固定的隨機初值、吃到 dict/set 迭代順序的實作）。
* **I2 換個行程跑，答案要一樣。** 批次是用 ProcessPool 跑的，主程式把 recipe
  序列化成 JSON 送進 worker。那趟來回一旦不是 identity，``workers=1`` 與
  ``workers=4`` 就會算出不同的分數 —— 兩邊都跑得完、都有數字。
  2026-08-16 真的發生過（一道遷移看到 subtract 沒寫 ``b`` 就補 ``ref_aligned``），
  有這條的話那天就會紅。
* **I3 卡片宣告什麼就只碰什麼。** 畫布上一張卡連了哪幾條線，是照它自己宣告的
  ``resolve_reads`` / ``resolve_writes`` 畫的。``run()`` 偷讀一條沒宣告的流，
  **畫布就在說謊** —— 畫面上兩張卡沒有連線，改了上面那張下面的數字卻會變。

* **I4 快取重放 = 全程重算。** 快取是效能設施，唯一被允許改變的是速度。
  這個 repo 在這件事上踩過三次，每次的症狀都是「第一次跑對、第二次跑錯」。
* **I5 參數推到上下界不炸，也不吐 NaN。** ``min``/``max`` 是卡片自己宣告的
  「使用者拖得到的範圍」（鐵則 4），所以這條問的是**那個範圍宣告得對嗎**。
* **I6 換一個 patch 尺寸照樣跑得動。** F7-4 那個坑的性質版。

每一條都用「把對應的 bug 放回去」驗過會紅（見各自的 docstring）。
進度見 ``docs/ROADMAP.md`` Phase 1。
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps                                    # noqa: E402,F401
from d4t.core.ingest.dataset import load_dataset          # noqa: E402
from d4t.core.pipeline import Recipe, run_defect          # noqa: E402
from d4t.core.pipeline.recipe import RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.pipeline.step import REGISTRY               # noqa: E402

KIND = "ebi_patch"

#: 這幾張卡沒辦法「只接 load_patch 就跑」，需要它們自己的前置或外部資料。
#:
#: **刻意寫死成一張清單**：新增一張卡而它跑不起來時，測試會叫，逼人做一個決定
#: （補前置、或明確寫進這裡並說明為什麼），而不是安靜地少測一張。
NEEDS_MORE_SETUP = {
    # 模板是一張影像，要先用 template_dialog 從大圖疊出來凍進 recipe。
    "roi_template": "模板參數要外部資料（一張原大圖）",
    # 這一套 harness 餵的是 ebi_patch（一顆兩張），而這張卡承諾「一顆一張」——
    # 它對多張資料的正確行為就是**擋下來**（見 steps/load.py）。專屬驗收在
    # tests/test_f11_split_load_cards.py。
    "load_single": "需要「一顆一張」的資料集（harness 餵的是 patch）",
    # 它讀的是 GLAS 匯出掛上來的附加檔（`DefectItem.sidecars`），而這個 harness
    # 的 lot 沒有掛。沒掛的時候這張卡**正確的行為就是擋下來並講出兩種原因**
    # （見 steps/load_sidecar.py）。專屬驗收在 tests/test_glas_sidecar.py。
    "load_sidecar": "需要掛上 GLAS 匯出的資料集（harness 的 lot 沒有）",
    # 它吃的是 `load_sidecar` 吐的那條流，而那張卡在這個 harness 上跑不起來
    # （上一行）。專屬驗收在 tests/test_roi_from_mask.py。
    "roi_from_mask": "需要 GLAS 的 label map 那條流（前一張卡在這裡跑不起來）",
    # F16：`roi_compare` 併進 `glv_stats` 的 ``method="compare"`` 了。
    # 那個 method 需要上游先有一張 Region 卡（這個 harness 只接 load_patch，
    # 所以一個區域都沒有），而**預設的 method 是 `stats`**，在這裡跑得起來 ——
    # 所以 `glv_stats` 不在這張表上，compare 那一半的專屬驗收在
    # tests/test_glv_compare.py。
    #
    # 它的表達式預設是空的 —— 而那是對的（F7-13：卡片一開始就該說「我還沒設定
    # 完」，不是猜一個式子）。空的時候它正確的行為就是擋下來並講出要填哪一格。
    # 專屬驗收在 tests/test_feature_math.py。
    "feature_math": "要填一個表達式（預設空的，那是刻意的）",
    # 它要的是**第二份 lot**（`Dataset.sources`），而這個 harness 只載了一份。
    # 沒掛的時候它正確的行為就是擋下來並講出「用這張卡上的 Open data…」。
    # 專屬驗收在 tests/test_pair_source.py。
    "pair_source": "需要掛上第二份 lot（harness 只載了一份）",
    # 它吃的是 `pair_source` 吐的那條流（配到的那顆的圖），而那張卡在這個
    # harness 上跑不起來（上一行）。專屬驗收在 tests/test_pair_source.py。
    "align_to": "需要配對卡吐出來的那條流（前一張卡在這裡跑不起來）",
}


def _lot(tmp_path_factory):
    from make_sample import generate
    out = tmp_path_factory.mktemp("invariants_lot")
    return generate(str(out), n=2, seed=7)


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    return _lot(tmp_path_factory)


@pytest.fixture(scope="module")
def dataset(lot):
    ds = load_dataset(lot["klarf"])
    assert ds.kind == KIND
    return ds


def _defaults(key: str) -> dict:
    """一張卡的預設參數（跟使用者剛從卡片庫拖出來時一樣）。"""
    return REGISTRY[key].validate_params({})


def recipe_for(key: str, sparse: bool = False,
               trailing_image: bool = False) -> Recipe:
    """``load_patch`` →（需要的話 ``subtract``）→ 這張卡。

    前置是**從卡片自己宣告的 reads 推出來的**，不是寫死的表 —— 卡片改了讀哪
    條流，這裡自動跟上。

    ``sparse=True`` 時每張卡的 ``params`` 是**空的**（等於使用者手寫的 recipe
    只填了在意的那幾格，其餘靠卡片預設）。這一版**非常重要**：

    第一版的這支測試只跑 ``sparse=False``（參數全部寫滿），於是把 2026-08-16
    那個 bug 放回去之後**測試照樣全綠** —— 因為那道遷移的條件正是「參數**沒**
    寫」。參數寫滿就永遠碰不到它。換句話說，那一版測的是一個不會出事的情境。

    這正是這個 repo 踩過四次的老樣式（測試通過，只是什麼都沒測），所以兩種
    寫法都要跑，而且**兩者的結果必須相同**：省略一個參數 = 用卡片當下的預設，
    不該因為省略而算出別的答案。
    """
    params = {} if sparse else _defaults(key)
    reads = set(REGISTRY[key].resolve_reads(_defaults(key)))

    def node_params(k: str) -> dict:
        return {} if sparse else _defaults(k)

    nodes = {"load": RecipeNode("load", "load_patch", node_params("load_patch"))}
    route = ["load"]
    if reads & {"diff", "snr_map"}:
        nodes["sub"] = RecipeNode("sub", "subtract", node_params("subtract"))
        route.append("sub")
    if "snr_map" in reads:
        nodes["snr"] = RecipeNode("snr", "snr_map", node_params("snr_map"))
        route.append("snr")
    if key not in nodes:
        nodes[key] = RecipeNode(key, key, params)
        route.append(key)

    if trailing_image and "tail" not in nodes:
        # 最後補一張影像卡，把 checkpoint 推到被測那張卡的**後面**（I4 要的）。
        # 它讀 test、寫 test，跟被測的卡不會互相干擾。
        nodes["tail"] = RecipeNode("tail", "denoise", node_params("denoise"))
        route.append("tail")
        # 這張卡定義了具名區域的話，再補一張**量它**的卡放在 checkpoint 之後
        # —— 那正是 2026 年那個真 bug 的形狀（Region 卡落在快取段裡、量測卡在
        # 段外）。沒有這個消費者的話，rois 存不存進快照根本沒人看得出來。
        regions = list(REGISTRY[key].resolve_regions_out(_defaults(key)))
        if regions and "probe" not in nodes:
            probe = dict(_defaults("glv_stats"))
            probe["roi"] = regions[0]
            probe["output_prefix"] = "probe"
            nodes["probe"] = RecipeNode("probe", "glv_stats", probe)
            route.append("probe")

    return Recipe(
        recipe_id="invariant_%s" % key,
        routes={KIND: route},
        nodes=nodes,
        score=ScoreSpec(expr="0", threshold=0.0, bins={"below": 0, "above": 1}),
    )


CARDS = sorted(REGISTRY)

#: 參數寫滿 vs 省略 —— 兩種都要跑，見 :func:`recipe_for` 的說明。
PARAM_STYLES = [False, True]
STYLE_ID = {False: "params-filled-in", True: "params-omitted"}


# --------------------------------------------------------------------------- #
# I2：換個行程跑，答案要一樣
# --------------------------------------------------------------------------- #
#: 在子行程裡跑同一份 recipe，把結果印成 JSON。
#:
#: 走的是**跟 worker 一樣的路**：recipe 以 JSON 傳進來、``from_json_dict`` 讀
#: 回來、``pin_cv2_deterministic()`` 先呼叫。那正是 ``batch._init_worker`` 做的事。
_CHILD = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[1] + "/tools")
import d4t.core.steps                                    # noqa
from d4t.core.pipeline.batch import pin_cv2_deterministic
pin_cv2_deterministic()
from d4t.core.ingest.dataset import load_dataset
from d4t.core.pipeline import Recipe, run_defect

_root, klarf, recipe_json = sys.argv[1], sys.argv[2], sys.argv[3]
ds = load_dataset(klarf)
rec = Recipe.from_json_dict(json.loads(recipe_json))
r = run_defect(rec, ds.items[0], ds.kind)
print("RESULT:" + json.dumps({
    "ok": bool(r.ok), "error": r.error, "score": r.score,
    "features": {k: float(v) for k, v in (r.features or {}).items()},
}, sort_keys=True))
'''


def _run_in_child(klarf: str, recipe: Recipe) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(REPO), str(klarf),
         json.dumps(recipe.to_json_dict())],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    text = proc.stdout.decode("utf-8", "replace")
    for line in text.split("\n"):
        if line.startswith("RESULT:"):
            return json.loads(line[len("RESULT:"):])
    raise AssertionError("子行程沒有回報結果：\n%s" % text[-2000:])


def _compare(label: str, here, there: dict) -> None:
    assert bool(here.ok) == there["ok"], (label, here.error, there["error"])
    assert here.error == there["error"], label
    assert here.score == there["score"], label
    assert set(here.features or {}) == set(there["features"]), \
        "%s：兩邊算出來的特徵**名字**就不一樣了" % label
    for name, value in (here.features or {}).items():
        assert float(value) == there["features"][name], \
            "%s 的 %s：主程式 %r、子行程 %r" % (label, name, value,
                                              there["features"][name])


@pytest.mark.parametrize("sparse", PARAM_STYLES, ids=lambda s: STYLE_ID[s])
@pytest.mark.parametrize("key", CARDS)
def test_a_card_gives_the_same_answer_in_another_process(key, sparse, dataset, lot):
    """同一張卡、同一顆 defect：主程式跑一次、子行程跑一次，結果必須相同。

    這條要抓的**不是演算法的非決定性**，是「recipe 走了一趟 JSON 之後變成
    另一份 recipe」。批次就是這樣把 recipe 送進 worker 的，所以這條一旦破，
    使用者會看到「我開 4 個 workers 比較快，但分數跟昨天不一樣」。

    兩種參數寫法都跑（寫滿／省略）—— **省略的那種才抓得到「靠參數缺席判斷」
    的遷移**，見 :func:`recipe_for`。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()          # 跟 worker 同一組 cv2 設定，才比得起來

    recipe = recipe_for(key, sparse=sparse)
    here = run_defect(recipe, dataset.items[0], dataset.kind)
    there = _run_in_child(lot["klarf"], recipe)
    _compare("%s[%s]" % (key, STYLE_ID[sparse]), here, there)


@pytest.mark.parametrize("key", CARDS)
def test_omitting_a_parameter_means_the_card_default(key, dataset, lot):
    """參數**省略**與**寫滿預設值**必須算出一模一樣的東西。

    「省略 = 用卡片當下的預設」是這個工具對使用者的承諾（手寫的 recipe 只會
    填在意的那幾格）。2026-08-16 破過一次：讀檔時看到 subtract 沒寫 ``b`` 就
    補一個**別的**值進去，於是同一份 recipe 寫滿與省略算出不同的分數。

    這條跟上面那條是互補的：上面問「換個行程一不一樣」，這條問「換個寫法
    一不一樣」。那個 bug 兩條都會抓到。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()

    filled = run_defect(recipe_for(key, sparse=False), dataset.items[0],
                        dataset.kind)
    omitted = run_defect(recipe_for(key, sparse=True), dataset.items[0],
                         dataset.kind)
    assert bool(filled.ok) == bool(omitted.ok), (filled.error, omitted.error)
    assert filled.score == omitted.score, key
    assert dict(filled.features or {}) == dict(omitted.features or {}), key


def test_the_cross_process_check_is_not_vacuous(dataset, lot):
    """上面那組測試必須真的有跑起來的卡 —— 否則它會全部 skip 然後全綠。

    這條是這個 repo 踩過三次的教訓：**測試會通過，只是什麼都沒測**
    （glob 到不存在的資料夾、回傳值沒人檢查、藏起來的鈕文字沒變）。
    """
    ran = [k for k in CARDS if k not in NEEDS_MORE_SETUP]
    assert len(ran) >= 12, ran
    ok = 0
    for key in ran:
        if run_defect(recipe_for(key), dataset.items[0], dataset.kind).ok:
            ok += 1
    assert ok >= 12, "只有 %d 張卡真的跑得起來，這組測試等於沒測到什麼" % ok


# --------------------------------------------------------------------------- #
# I3：卡片宣告什麼就只碰什麼（畫布不能說謊）
# --------------------------------------------------------------------------- #
class _RecordingImages(dict):
    """記下每一次讀 / 寫，其餘行為跟一般 dict 一樣。

    攔在 ``Context.images`` 這一層而不是包 ``Context``：卡片有的走
    ``ctx.require_image(k)``、有的直接 ``ctx.images[k]``，而兩條路最後都會
    落到這個 dict 上。

    **「讀」指的是外部依賴**，所以兩種存取不算：

    * ``"ref" in ctx.images`` —— 那是在問「這條流在不在」，不是拿它的像素。
    * **自己寫完之後再讀回來** —— 例如 ``load_patch`` 寫完 test/ref 之後
      ``ctx.images.get(ch)`` 回頭數有幾個 channel。那不是依賴上游，
      是它自己剛放進去的東西。
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._log = []                       # [("r"/"w", key), …] 依序

    # ---- 查詢 -------------------------------------------------------------
    @property
    def writes(self):
        return [k for op, k in self._log if op == "w"]

    @property
    def reads(self):
        """外部讀取：在**自己寫它之前**就讀的那些。"""
        written = set()
        out = []
        for op, key in self._log:
            if op == "w":
                written.add(key)
            elif key not in written:
                out.append(key)
        return out

    # ---- dict hooks -------------------------------------------------------
    def __getitem__(self, key):
        self._log.append(("r", key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._log.append(("r", key))
        return super().get(key, default)

    def __setitem__(self, key, value):
        self._log.append(("w", key))
        super().__setitem__(key, value)


def _prepared_context(key: str, dataset):
    """把這張卡跑得起來所需的上游先跑完，回傳 (Context, 這張卡的參數)。"""
    recipe = recipe_for(key)
    route = recipe.routes[KIND]
    if route[-1] != key:                       # 這張卡本身就是前置（load/subtract）
        upto = None if len(route) == 1 else route[route.index(key) - 1]
    else:
        upto = route[-2] if len(route) > 1 else None
    if upto is None:
        from d4t.core.pipeline.context import Context
        ctx = Context()
        ctx.meta["_defect_item"] = dataset.items[0]
        ctx.meta["_dataset_kind"] = dataset.kind
        return ctx, _defaults(key)
    res = run_defect(recipe, dataset.items[0], dataset.kind,
                     keep_context=True, upto_node=upto)
    assert res.context is not None, res.error
    return res.context, _defaults(key)


@pytest.mark.parametrize("key", CARDS)
def test_a_card_only_touches_what_it_declares(key, dataset):
    """``run()`` 實際讀寫的影像流，必須是 ``resolve_reads/writes`` 宣告的子集。

    為什麼是「子集」而不是「相等」：宣告是**可能會碰到的**（有些參數組合下
    某條流用不到，例如 ``normalize`` 的 ``range_from`` 留空時就不借別條流）。
    多碰一條沒宣告的才是問題 —— **那條線不會出現在畫布上**，使用者於是看不出
    這兩張卡有關係。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    ctx, params = _prepared_context(key, dataset)
    rec = _RecordingImages(ctx.images)
    ctx.images = rec
    before_features = set(ctx.features)

    step = REGISTRY[key]()
    step.run(ctx, step.validate_params(params))

    declared_reads = set(REGISTRY[key].resolve_reads(params))
    # 有些卡「寫什麼」取決於資料型別（load_patch：ebi_patch 給 test+ref、
    # rsem 給 single+test），那是 ``resolve_writes_for_kind`` 在回答的問題。
    # 問錯方法的話 load 卡會被誤判成「寫了沒宣告的 ref」。
    declared_writes = set(REGISTRY[key].resolve_writes_for_kind(params, KIND))
    actual_reads = set(rec.reads)
    actual_writes = set(rec.writes)

    assert actual_reads <= declared_reads, (
        "%s 讀了沒宣告的影像流 %s —— 畫布上不會有那條線，"
        "使用者看不出這兩張卡有關係（宣告：%s）"
        % (key, sorted(actual_reads - declared_reads), sorted(declared_reads)))
    assert actual_writes <= declared_writes, (
        "%s 寫了沒宣告的影像流 %s（宣告：%s）"
        % (key, sorted(actual_writes - declared_writes), sorted(declared_writes)))

    declared_features = set(REGISTRY[key].resolve_features(params))
    new_features = set(ctx.features) - before_features
    assert new_features <= declared_features, (
        "%s 產出了沒宣告的特徵 %s —— 它會出現在 feature 表與 score 表達式的"
        "自動完成裡，但沒有任何地方說得出它從哪來（宣告：%s）"
        % (key, sorted(new_features - declared_features),
           sorted(declared_features)))


def test_the_declaration_check_is_not_vacuous(dataset):
    """同上：確認真的有卡片被檢查到，而且它們真的讀了東西。"""
    checked = 0
    for key in CARDS:
        if key in NEEDS_MORE_SETUP or key == "load_patch":
            continue
        ctx, params = _prepared_context(key, dataset)
        rec = _RecordingImages(ctx.images)
        ctx.images = rec
        step = REGISTRY[key]()
        step.run(ctx, step.validate_params(params))
        if rec.reads:
            checked += 1
    assert checked >= 12, "只有 %d 張卡真的讀了影像流，這組測試沒測到什麼" % checked


# --------------------------------------------------------------------------- #
# I1：同一份輸入跑兩次，答案要一樣
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", CARDS)
def test_a_card_gives_the_same_answer_twice(key, dataset):
    """同一張卡、同一顆 defect，連跑兩次必須逐位元組相同。

    I2 問的是「換個行程一不一樣」（recipe 的 JSON 來回），這條問的是**演算法
    自己**穩不穩。兩者會被同一個症狀吸引過去（「分數跟昨天不一樣」），但根因
    完全不同 —— 這條抓的是 OpenCV 的 IPP 路徑、未固定的隨機初值、以及吃到
    dict／set 迭代順序的實作。

    這個 repo 已經為此付過一次代價：``batch.pin_cv2_deterministic()`` 就是因為
    「同張圖算兩次差 ~1e-8，快取結果對不起來」才存在的。那個保護目前只有批次
    路徑呼叫得到，這條測試讓**每一張卡**都被問一次。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()

    recipe = recipe_for(key)
    a = run_defect(recipe, dataset.items[0], dataset.kind)
    b = run_defect(recipe, dataset.items[0], dataset.kind)

    assert bool(a.ok) == bool(b.ok), (a.error, b.error)
    assert a.score == b.score, key
    assert dict(a.features or {}) == dict(b.features or {}), \
        "%s 跑兩次算出不同的數字（比 == 而不是 approx —— 這裡要的是逐位元組）" % key


# --------------------------------------------------------------------------- #
# I4：快取重放 = 全程重算
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", CARDS)
def test_a_card_replays_from_cache_exactly(key, dataset, lot, tmp_path):
    """全程重算、冷跑（寫快取）、熱跑（讀快取）三者必須完全相同。

    快取是**效能**設施，所以它唯一被允許改變的是速度。這個 repo 在這件事上
    踩過三次，每一次的症狀都是「第一次跑對、第二次跑錯」：

    * 快照漏了 ``ctx.rois`` → 熱跑時區域整組不見；
    * ``set_roi`` 逐一還原 → 17 個框只剩 1 個（跑得完、有數字、少 16 塊）；
    * 快照漏了 ``feature_owner`` → 熱跑少一個被救回來的特徵。

    三次都是「快照少存了 Context 的某個欄位」。這條把它變成**每張卡都問一次**
    的性質，所以下一次有人往 Context 加欄位時，忘了同步快照就會紅。

    **關鍵在最後補一張影像卡**（``recipe_for(..., trailing_image=True)``）：
    checkpoint 是「執行順序上最後一張影像卡的下一格」，所以不補的話被測的那張
    卡會落在 checkpoint **之後** —— 它產出的東西根本不必經過快照，這條就變成
    「把同一條路跑了三次」。補了之後它落在快取段裡，rois／features／影像全部
    都得從快照活著回來。第一版就是漏了這件事：把「快照不存 rois」那個真的
    bug 放回去，測試照樣全綠。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    from d4t.core.pipeline.batch import pin_cv2_deterministic
    from d4t.core.pipeline.cache import StageCache
    from d4t.core.pipeline.engine import run_defect_cached
    pin_cv2_deterministic()

    recipe = recipe_for(key, trailing_image=True)
    item = dataset.items[0]
    plain = run_defect(recipe, item, dataset.kind)

    cache = StageCache(str(tmp_path / ("cache_%s" % key)))
    cold = run_defect_cached(recipe, item, dataset.kind, cache, "tok")
    warm = run_defect_cached(recipe, item, dataset.kind, cache, "tok")

    for label, other in (("冷跑", cold), ("熱跑", warm)):
        assert bool(plain.ok) == bool(other.ok), (key, label, plain.error,
                                                  other.error)
        assert plain.score == other.score, "%s 的 %s 分數不一樣" % (key, label)
        assert dict(plain.features or {}) == dict(other.features or {}), \
            "%s：%s 跟全程重算算出不一樣的特徵" % (key, label)


def test_the_cache_replay_check_actually_uses_the_cache(dataset, lot, tmp_path):
    """上面那條必須真的**命中過快取** —— 否則它只是把同一條路跑了三次。

    影像段 checkpoint 是「執行順序上最後一張影像卡的下一格」，所以一張
    algo 卡的 recipe 才會有非零的 checkpoint。這裡直接問快取的 hit 計數。
    """
    from d4t.core.pipeline.cache import StageCache
    from d4t.core.pipeline.engine import run_defect_cached

    hits = 0
    for key in CARDS:
        if key in NEEDS_MORE_SETUP:
            continue
        rec = recipe_for(key, trailing_image=True)
        cache = StageCache(str(tmp_path / ("hit_%s" % key)))
        run_defect_cached(rec, dataset.items[0], dataset.kind, cache, "tok")
        run_defect_cached(rec, dataset.items[0], dataset.kind, cache, "tok")
        hits += cache.stats_counters()["hits"] if hasattr(
            cache, "stats_counters") else cache.hits
    assert hits >= 8, "只有 %d 次快取命中 —— I4 幾乎沒有走到熱跑那條路" % hits


# --------------------------------------------------------------------------- #
# I5：參數推到上下界不炸，而且不吐出 NaN
# --------------------------------------------------------------------------- #
def _extreme_param_cases(key: str):
    """這張卡的每個有界數值參數 → ``(參數名, 值)`` 的極端組合。

    一次只推**一個**參數（其餘留預設）：全部一起推的話，紅了也不知道是誰造成
    的，而使用者實際上也是一次拖一支滑桿。
    """
    for spec in REGISTRY[key].params:
        if spec.type not in ("int", "float"):
            continue
        for bound in (spec.min, spec.max):
            if bound is None:
                continue
            value = int(bound) if spec.type == "int" else float(bound)
            yield spec.name, value


def _extreme_ids(case):
    return "%s=%s" % case


EXTREME_CASES = sorted(
    (key, name, value)
    for key in CARDS if key not in NEEDS_MORE_SETUP
    for name, value in _extreme_param_cases(key))


@pytest.mark.parametrize("key,name,value", EXTREME_CASES,
                         ids=["%s.%s=%s" % c for c in EXTREME_CASES])
def test_a_parameter_at_its_limit_does_not_produce_nonsense(key, name, value,
                                                            dataset):
    """把一個參數推到它宣告的上界／下界，這張卡必須：

    1. **不丟出未攔截的例外**（引擎會收成 ``ok=False``，但訊息要讀得懂）；
    2. **不產出 NaN／Inf 的特徵**。

    第 2 點才是這條真正在守的東西。NaN 不是「壞掉」而是**安靜地錯**：
    score 表達式對 nan/inf 的規則是「一律歸 0.0」（`expression.py` 的 SAFE
    語意，那是刻意的 —— 一顆 defect 不該因為除以零就殺掉整批）。於是一個
    NaN 特徵的下場是 **score 變成 0.0 → 判進 ``below``（＝ nuisance）**：
    那顆真缺陷被安靜地漏掉了，而畫面上它跟一顆真的很乾淨的 defect 一模一樣。

    所以擋 NaN 的地方必須是**卡片**：SAFE 的表達式救得了「整批不要死」，
    救不了「這個數字是錯的」。

    ``min``/``max`` 是卡片自己宣告的「使用者拖得到的範圍」（鐵則 4），
    所以這條問的正是：**那個範圍宣告得對嗎**。
    """
    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()

    params = dict(_defaults(key))
    params[name] = value
    recipe = recipe_for(key)
    recipe.nodes[key].params = params

    res = run_defect(recipe, dataset.items[0], dataset.kind)
    if not res.ok:
        # 擋下來是可以的 —— 但要講得出人話（推廣鐵則），不能是 traceback
        # 的殘骸或空字串。
        assert res.error and len(str(res.error)) > 10, \
            "%s 的 %s=%s 失敗了，但訊息是 %r" % (key, name, value, res.error)
        return
    assert res.score is not None and math.isfinite(float(res.score)), \
        "%s 的 %s=%s 算出非有限的分數 %r" % (key, name, value, res.score)
    bad = [k for k, v in (res.features or {}).items()
           if not math.isfinite(float(v))]
    assert not bad, (
        "%s 的 %s=%s 產出了 NaN／Inf 的特徵 %s —— score 會跟著變 NaN，"
        "而 NaN < threshold 是 False，那顆 defect 會安靜地被判成真缺陷"
        % (key, name, value, bad))


def test_the_extreme_parameter_check_is_not_vacuous():
    """真的有參數被推到界線 —— 卡片全都沒宣告 min/max 的話這組會空轉。"""
    assert len(EXTREME_CASES) >= 30, len(EXTREME_CASES)
    assert len({key for key, _n, _v in EXTREME_CASES}) >= 8


# --------------------------------------------------------------------------- #
# I6：換一個影像尺寸，同一份 recipe 照樣跑得動
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def big_dataset(tmp_path_factory):
    """跟 :func:`lot` 同樣的 lot，但 patch 大一倍。"""
    from make_sample import generate
    out = tmp_path_factory.mktemp("invariants_lot_256")
    lot = generate(str(out), n=2, seed=7, size=256)
    ds = load_dataset(lot["klarf"])
    assert ds.kind == KIND
    return ds


@pytest.mark.parametrize("key", CARDS)
def test_a_card_survives_a_different_patch_size(key, dataset, big_dataset):
    """同一份 recipe 換一個 patch 尺寸（128 → 256）必須照樣跑得動。

    這是 F7-4 那個坑的性質版：``glv_stats`` 的中心框以前是**畫素**寫死的，
    於是同一組參數在 128² 上準、在 256² 上漏抓 —— 而兩邊都跑得完、都有數字。
    幾何後來搬到 Region 卡並支援 ``percent``，這條讓每一張卡都被問一次。

    只問「跑不跑得動 + 數字是有限的」，**不問數字一不一樣** —— 影像變了數字
    本來就會變，那是對的。
    """
    if key in NEEDS_MORE_SETUP:
        pytest.skip("%s：%s" % (key, NEEDS_MORE_SETUP[key]))

    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()

    recipe = recipe_for(key)
    small = run_defect(recipe, dataset.items[0], dataset.kind)
    big = run_defect(recipe, big_dataset.items[0], big_dataset.kind)

    assert bool(big.ok) == bool(small.ok), (
        "%s 在 128² 上 ok=%s，換成 256² 變成 ok=%s：%s"
        % (key, small.ok, big.ok, big.error))
    if not big.ok:
        return
    assert set(big.features or {}) == set(small.features or {}), \
        "%s 換個尺寸就產出了不同的**特徵名**（%s）" % (
            key, sorted(set(big.features or {}) ^ set(small.features or {})))
    bad = [k for k, v in (big.features or {}).items()
           if not math.isfinite(float(v))]
    assert not bad, "%s 在 256² 上產出 NaN／Inf 的特徵 %s" % (key, bad)


# --------------------------------------------------------------------------- #
# 卡片名的長度 —— 一列讀得完
# --------------------------------------------------------------------------- #
#: 目前最長的那一個（``Remove background / stripes``）。這不是一個猜出來的美感
#: 數字，是**現況的天花板**：新卡片超過它，就要先看一眼卡片庫再決定。
#:
#: 為什麼要有這條：卡片庫是一列一張卡讀下去的，名字長到要換行、或被 ``…``
#: 截掉，那一列就不再是一眼的事 —— 而目標使用者正是靠掃過那一列找卡的。
#: 實際發生過（2026-08-18）：``Reference from repeating pattern`` 進了卡片庫，
#: 使用者第一句話就是「名字太長」。收成 ``Reference from pattern`` 之後，
#: 句型跟隔壁的 ``Mask from regions`` 一樣：**「產出 from 來源」**。
#:
#: 掉出去的字（那張卡的 ``repeating``）該去 ``help``：名字回答「這張卡做什麼」，
#: 前提與細節回答「我能不能用它」，兩者不是同一個問題。
MAX_LABEL_CHARS = 27


@pytest.mark.parametrize("key", CARDS)
def test_a_card_name_fits_on_one_line(key):
    label = str(REGISTRY[key].label)
    assert label.strip(), "%s：沒有 label" % key
    assert len(label) <= MAX_LABEL_CHARS, (
        "%s 的名字 %r 有 %d 個字元，超過現況的天花板 %d —— 卡片庫是一列一張卡"
        "讀下去的。把前提／細節搬進 help，名字只留「這張卡做什麼」。"
        % (key, label, len(label), MAX_LABEL_CHARS))
