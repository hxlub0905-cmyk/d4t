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

這一檔目前鎖兩條：

* **I2 換個行程跑，答案要一樣。** 批次是用 ProcessPool 跑的，主程式把 recipe
  序列化成 JSON 送進 worker。那趟來回一旦不是 identity，``workers=1`` 與
  ``workers=4`` 就會算出不同的分數 —— 兩邊都跑得完、都有數字。
  2026-08-16 真的發生過（一道遷移看到 subtract 沒寫 ``b`` 就補 ``ref_aligned``），
  有這條的話那天就會紅。
* **I3 卡片宣告什麼就只碰什麼。** 畫布上一張卡連了哪幾條線，是照它自己宣告的
  ``resolve_reads`` / ``resolve_writes`` 畫的。``run()`` 偷讀一條沒宣告的流，
  **畫布就在說謊** —— 畫面上兩張卡沒有連線，改了上面那張下面的數字卻會變。

還沒做的（同一個機制，之後補）：I1 同輸入跑兩次相同、I4 快取重放＝全程重算、
I5 參數推到上下界不炸、I6 換影像尺寸照跑。見 ``docs/ROADMAP.md`` Phase 1。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import adept.core.steps                                    # noqa: E402,F401
from adept.core.ingest.dataset import load_dataset          # noqa: E402
from adept.core.pipeline import Recipe, run_defect          # noqa: E402
from adept.core.pipeline.recipe import RecipeNode, ScoreSpec  # noqa: E402
from adept.core.pipeline.step import REGISTRY               # noqa: E402

KIND = "ebi_patch"

#: 這幾張卡沒辦法「只接 load_patch 就跑」，需要它們自己的前置或外部資料。
#:
#: **刻意寫死成一張清單**：新增一張卡而它跑不起來時，測試會叫，逼人做一個決定
#: （補前置、或明確寫進這裡並說明為什麼），而不是安靜地少測一張。
NEEDS_MORE_SETUP = {
    # 模板是一張影像，要先用 template_dialog 從大圖疊出來凍進 recipe。
    "roi_template": "模板參數要外部資料（一張原大圖）",
    # 只有 RSEM 單張才有意義；patch 本來就有 ref。
    "golden_cell": "RSEM 專用（patch 有現成的 ref）",
    "cell_period": "只有餵 golden_cell 時有意義",
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


def recipe_for(key: str, sparse: bool = False) -> Recipe:
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
import adept.core.steps                                    # noqa
from adept.core.pipeline.batch import pin_cv2_deterministic
pin_cv2_deterministic()
from adept.core.ingest.dataset import load_dataset
from adept.core.pipeline import Recipe, run_defect

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

    from adept.core.pipeline.batch import pin_cv2_deterministic
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

    from adept.core.pipeline.batch import pin_cv2_deterministic
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
        from adept.core.pipeline.context import Context
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
