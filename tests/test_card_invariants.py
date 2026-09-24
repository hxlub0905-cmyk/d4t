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

這一檔目前鎖九條（⚠ 這一行以前寫著「六條」，而 I7／I8 早就在檔案裡了 ——
2026-09-08 加 I9 那一輪一起補上）：

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
* **I7 改一個參數，快取一定要跟著失效。** I4 的另一半：I4 問「同一份 recipe
  冷跑熱跑一不一樣」，這條問「改了參數還會不會拿到舊影像」。
* **I8 每一張卡都答得出「哪幾格是進階的」。** ``describe()`` 少了那個鍵的話，
  UI 會整批當成非進階 —— 安靜地失效，不是壞掉。
* **I9 藏起來的參數不影響結果**（2026-09-08）。``show_when`` 是**顯示**規則
  不是驗證規則，而 registry 裡有 91 個參數掛著它（``roi_reference`` 一張卡就
  33 個）。在這條之前，「用不到的參數不影響結果」是**靠人記得**的。

每一條都用「把對應的 bug 放回去」驗過會紅（見各自的 docstring）。
進度見 ``docs/ROADMAP.md`` Phase 1。
"""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps                                    # noqa: E402,F401
from d4t.core.ingest.dataset import load_dataset          # noqa: E402
from d4t.core.pipeline import (                           # noqa: E402
    Recipe, get_step, list_steps, run_defect, validate,
)
from d4t.core.pipeline.recipe import RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.pipeline.step import REGISTRY               # noqa: E402

KIND = "ebi_patch"

#: 這幾張卡沒辦法「只接 load_patch 就跑」，需要它們自己的前置或外部資料。
#:
#: **刻意寫死成一張清單**：新增一張卡而它跑不起來時，測試會叫，逼人做一個決定
#: （補前置、或明確寫進這裡並說明為什麼），而不是安靜地少測一張。
#: ⚠ **這張表有一支反向測試**（``test_the_setup_exception_list_has_no_ghosts``，
#: 2026-09-08）：卡片刪掉或改名之後，這裡那一列要跟著拿掉。補那支測試的當天
#: 它就抓到兩隻幽靈 —— ``roi_template``（F29 併進 ``roi_reference`` 的
#: ``method="a cell I mark myself"``）與 ``roi_from_mask``（F74 刪掉），
#: 兩列都指著不存在的卡。
NEEDS_MORE_SETUP = {
    # （F11 的 `load_single` 在這裡有過一列 —— 它在一顆兩張的 harness 上正確的
    # 行為是擋下來。F121 期 2 併回 Input 了，那一列跟著拿掉。）
    # 它讀的是 GLAS 匯出掛上來的附加檔（`DefectItem.sidecars`），而這個 harness
    # 的 lot 沒有掛。沒掛的時候這張卡**正確的行為就是擋下來並講出兩種原因**
    # （見 steps/load_sidecar.py）。專屬驗收在 tests/test_glas_sidecar.py。
    "load_sidecar": "需要掛上 GLAS 匯出的資料集（harness 的 lot 沒有）",
    # F16：`roi_compare` 併進 `glv_stats` 的 ``method="compare"`` 了。
    # 那個 method 需要上游先有一張 Region 卡（這個 harness 只接 load_patch，
    # 所以一個區域都沒有），而**預設的 method 是 `stats`**，在這裡跑得起來 ——
    # 所以 `glv_stats` 不在這張表上，compare 那一半的專屬驗收在
    # tests/test_glv_compare.py。
    #
    # ⚠ `feature_math` / `feature_fill` 兩列 2026-08-27 拿掉了 —— 那兩張卡刪了
    # （Phase 3）。**這張表上留一個不存在的 key 沒有任何測試會叫**，而它會讓
    # 下一個讀的人以為那張卡還在（`CLAUDE.md`：任何「例外清單」都要有一支反向
    # 的測試，而這一張目前沒有）。
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
    # `snr_map`（Z-map）2026-08-25 刪掉之後，**沒有任何一張卡再讀那條流**了
    # —— 所以這裡只剩 `diff` 要有人產。
    if "diff" in reads:
        nodes["sub"] = RecipeNode("sub", "subtract", node_params("subtract"))
        route.append("sub")
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


#: 這六條不變量問的都是「**一顆** defect 跑起來會怎樣」，所以跨顆卡不在裡面
#: —— 它們根本沒有 `run(ctx, params)`（F16：`Step.is_batch`）。
#:
#: **用類別的性質篩，不是逐張列名字**：列名字的話，第二張跨顆卡加進來的那天
#: 它會撞上一個看不懂的錯誤（「這張卡跑起來就丟 StepError」），而正確的答案是
#: 「它本來就不該用這種方式跑」。跨顆卡自己的驗收在 tests/test_batch_steps.py。
CARDS = sorted(k for k, c in REGISTRY.items() if not c.is_batch)
BATCH_CARDS = sorted(k for k, c in REGISTRY.items() if c.is_batch)

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
    # ⚠ **下限 2026-09-02 從 12 降到 11**（`roi_mask` 刪掉了）——
    # 理由與下面 `test_the_declaration_check_is_not_vacuous` 那一段逐字相同：
    # 這一條問的是「這組測試有沒有真的測到東西」，不是「卡片有幾張」。
    ran = [k for k in CARDS if k not in NEEDS_MORE_SETUP]
    assert len(ran) >= 11, ran
    ok = 0
    for key in ran:
        if run_defect(recipe_for(key), dataset.items[0], dataset.kind).ok:
            ok += 1
    assert ok >= 11, "只有 %d 張卡真的跑得起來，這組測試等於沒測到什麼" % ok


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
    # ⚠ **這個下限降過兩次**：2026-08-25 從 12 降到 11（`snr_map` / Z-map 刪
    # 掉了）、2026-09-02 從 11 降到 10（`roi_mask` 刪掉了）。降下限是**唯一**
    # 誠實的改法：這一條問的是「這組測試有沒有真的測到東西」，而不是「卡片有
    # 幾張」—— 留在原本的數字只會逼出「找一張卡湊數」，而那時它就不再擋得住
    # 任何事。
    assert checked >= 10, "只有 %d 張卡真的讀了影像流，這組測試沒測到什麼" % checked


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
# I7：改一個參數，快取一定要跟著失效
# --------------------------------------------------------------------------- #
def _another_value(spec):
    """這個參數的**另一個**值（跟預設不同、而且在宣告的界線裡）。

    回 ``None`` = 這一格造不出第二個值（自由文字、影像流、曲線…）——
    那些格子的變化不由這條測試負責。
    """
    default = spec.default
    if spec.type == "bool":
        return not bool(default)
    # ⚠ **三種下拉／膠囊都要算**：`icon_choice` 從來沒有被這條測試蓋到，而
    # F68 第二輪把所有的 `choice` 換成 `chip_choice` 之後，漏掉的那一族就從
    # 七個變成二十一個 —— 那一輪它真的紅了（56 < 60），也就是這一行的來歷。
    if spec.type in ("choice", "icon_choice", "chip_choice") and spec.choices:
        for choice in spec.choices:
            if choice != default:
                return choice
        return None
    if spec.type in ("int", "float"):
        cast = int if spec.type == "int" else float
        lo = cast(spec.min) if spec.min is not None else None
        hi = cast(spec.max) if spec.max is not None else None
        for candidate in (cast(default) + (2 if spec.type == "int" else 1.0),
                          cast(default) - (2 if spec.type == "int" else 1.0),
                          hi, lo):
            if candidate is None or candidate == default:
                continue
            if lo is not None and candidate < lo:
                continue
            if hi is not None and candidate > hi:
                continue
            return candidate
    return None


def _param_change_cases():
    """``(卡片, 參數名, 另一個值)`` —— 每一張卡的每一個造得出第二個值的參數。"""
    for key in CARDS:
        if key in NEEDS_MORE_SETUP:
            continue
        for spec in REGISTRY[key].params:
            value = _another_value(spec)
            if value is not None:
                yield (key, spec.name, value)


PARAM_CHANGES = list(_param_change_cases())


@pytest.mark.parametrize("key, name, value", PARAM_CHANGES,
                         ids=["%s.%s" % (k, n) for k, n, _ in PARAM_CHANGES])
def test_changing_a_parameter_invalidates_the_cache(key, name, value,
                                                    dataset, tmp_path):
    """**改了會影響結果的東西，快取一定要失效**（鐵則 9）。

    I4 問的是「同一份 recipe，冷跑與熱跑一不一樣」。這一條問的是**另一半**：
    **改了參數之後**，帶著舊快取跑出來的，還是不是對的答案。

    兩者不能互相取代，而缺的那一半正是這個 repo 踩過的形狀 ——
    F9-8 的實測原話是「把 ``x5`` 的輸入從 ``load`` 改接到 ``x3``，正確答案
    15.0，帶著舊快取跑出來是 5.0」。那一次是**線**沒進簽章；同一個洞在
    **參數**上一樣開得起來（``_writes_an_image`` 第一版漏了 ``validate_params``，
    於是一張正常的 Enhance 卡被判成「不吐影像」，checkpoint 整個往前縮）。

    做法：同一個快取目錄，先用預設參數跑一次（把舊影像寫進去），
    再改一個參數跑一次，結果必須等於**乾淨重跑**（沒有快取）。
    不等於就代表簽章看不見這一格。
    """
    from dataclasses import replace as dc_replace

    from d4t.core.pipeline.batch import pin_cv2_deterministic, run_batch
    pin_cv2_deterministic()

    base = recipe_for(key, trailing_image=True)
    if key not in base.nodes:                  # 這張卡是別人的前置，沒有自己的節點
        pytest.skip("%s 在這個 harness 裡沒有自己的節點" % key)

    cache_dir = str(tmp_path / "cache")
    # ① 先用預設參數跑一次 —— 這一步是把「舊影像」寫進快取
    run_batch(base, dataset, workers=1, cache_dir=cache_dir)

    # ② 改一格
    node = base.nodes[key]
    params = dict(node.params)
    params[name] = value
    changed = dc_replace(base, nodes=dict(base.nodes,
                                          **{key: dc_replace(node, params=params)}))

    clean = _numbers(run_batch(changed, dataset, workers=1))
    warm = _numbers(run_batch(changed, dataset, workers=1, cache_dir=cache_dir))
    assert warm == clean, (
        "%s 的 %s 改成 %r 之後，帶著舊快取跑出來跟乾淨重跑不一樣 —— "
        "影像段簽章看不見這一格" % (key, name, value))


def _numbers(rows):
    """一批結果裡「所有算出來的數字」，可以逐項比對。"""
    return [(r.get("defect_id"), bool(r.get("ok")),
             None if r.get("score") is None else repr(float(r["score"])),
             tuple(sorted((k, repr(float(v)))
                          for k, v in (r.get("features") or {}).items())))
            for r in rows]


def test_the_parameter_change_check_covers_a_real_spread_of_cards():
    """上面那一組必須真的涵蓋到卡片與參數 —— 否則它會安靜地空轉。

    同 `test_the_extreme_parameter_check_is_not_vacuous` 的理由：
    ``_another_value`` 回 None 太多的話（例如有人把 min/max 拿掉），
    這一組會縮到剩幾個而沒有人發現。
    """
    cards = {k for k, _, _ in PARAM_CHANGES}
    assert len(PARAM_CHANGES) >= 60, (
        "只造得出 %d 組參數變化 —— _another_value 可能失效了" % len(PARAM_CHANGES))
    assert len(cards) >= 10, "只涵蓋到 %d 張卡：%s" % (len(cards), sorted(cards))


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
#: 目前最長的那一個。這不是一個猜出來的美感數字，是**現況的天花板**：
#: 新卡片超過它，就要先看一眼卡片庫再決定。
#:
#: ⚠ **它跟著現況往下走**（F110，2026-09-17）：27 → 17。27 那一版的持有者是
#: ``flatten`` 的 ``Remove background / stripes``，而 2026-09-17 量出來只有
#: **三張離群**（27／24／18，中位數 11），三張一起剪短了 ——
#: ``Flatten`` / ``Pair source`` / ``layout(GDS)``。天花板掉下去就要跟著降
#: （`CLAUDE.md` §4 那條反向規矩），不然它擋的是一個已經沒有人站的高度。
#:
#: 為什麼要有這條：卡片庫是一列一張卡讀下去的，名字長到要換行、或被 ``…``
#: 截掉，那一列就不再是一眼的事 —— 而目標使用者正是靠掃過那一列找卡的。
#: 實際發生過（2026-08-18）：``Reference from repeating pattern`` 進了卡片庫，
#: 使用者第一句話就是「名字太長」。收成 ``Reference from pattern`` 之後，
#: 句型跟隔壁的 ``Mask from regions`` 一樣：**「產出 from 來源」**。
#:
#: 掉出去的字（那張卡的 ``repeating``）該去 ``help``：名字回答「這張卡做什麼」，
#: 前提與細節回答「我能不能用它」，兩者不是同一個問題。
MAX_LABEL_CHARS = 17


@pytest.mark.parametrize("key", CARDS)
def test_a_card_name_fits_on_one_line(key):
    label = str(REGISTRY[key].label)
    assert label.strip(), "%s：沒有 label" % key
    assert len(label) <= MAX_LABEL_CHARS, (
        "%s 的名字 %r 有 %d 個字元，超過現況的天花板 %d —— 卡片庫是一列一張卡"
        "讀下去的。把前提／細節搬進 help，名字只留「這張卡做什麼」。"
        % (key, label, len(label), MAX_LABEL_CHARS))


def test_the_name_ceiling_is_the_real_maximum_not_a_round_number():
    """**反向**：天花板掉下去要跟著降（`CLAUDE.md` §4）。

    `MAX_LABEL_CHARS` 說的是「現況最長的那一個」。它比真的最長值高的時候，
    擋的是一個**已經沒有人站的高度** —— 於是下一張卡可以取一個比現況所有卡
    都長的名字而不被問一句話，而那正是這條規矩要防的事。

    訊息裡帶中位數：下一個取名字的人看得到自己離群多遠（2026-09-17 量到的是
    三張離群 27／24／18，中位數 11 —— 那個對比才是「太長了」的證據）。
    """
    lens = sorted(((len(str(c.label)), k, str(c.label))
                   for k, c in REGISTRY.items()), reverse=True)
    longest = lens[0][0]
    mid = statistics.median(n for n, _k, _l in lens)
    assert MAX_LABEL_CHARS == longest, (
        "天花板寫著 %d，而現在最長的是 %d（%s《%s》）。中位數 %g。\n"
        "  長了 → 有人取了更長的名字，先看一眼卡片庫；\n"
        "  短了 → 把 MAX_LABEL_CHARS 改成 %d，把成果鎖住。"
        % (MAX_LABEL_CHARS, longest, lens[0][1], lens[0][2], mid, longest))


# --------------------------------------------------------------------------- #
# I7 每一張卡都要**接得起來**，而接不起來的組合要在 lint 就被講出來
#
# 2026-08-27（F39-B3）從 `test_ui_f7_9_feedback.py` 搬過來的四條。它們問的正是
# 這個檔的問題 ——「不管哪一張卡，這件事都成立嗎」—— 而且**一條 Qt 都沒有用到**
# （原本掛在 UI 檔上只是因為它們是那一輪的驗收）。搬過來換到兩件事：
#
# * 它們回到**核心批**（`--ignore-glob="*test_ui_*"`），不再吃 Qt 那 20 秒
#   —— 四條合起來從 UI 批搬走，核心批只多 0.6 秒；
# * 加第 N 張卡的人會在這裡被擋下 —— 這個檔就是「自動套用到 registry 裡每一
#   張卡」的家。
#
# ⚠ `test_every_visible_card_can_be_wired_up_without_a_dead_end` 讀
# `d4t.ui.scope.visible_steps`。`scope.py` 是一份**純資料模組**（只 import
# typing），所以核心批 import 它不會把 Qt 拖進來 —— `test_no_qt_after_import`
# 仍然是那條線的守門人。
# --------------------------------------------------------------------------- #
def _lint_recipe(seq):
    """一串 step key -> 一份照順序接起來的 recipe（給下面兩條掃描用）。"""
    nodes, order = {}, []
    for i, key in enumerate(seq):
        nid = "n%d" % i
        nodes[nid] = RecipeNode(id=nid, step=key,
                                params=get_step(key).validate_params({}))
        order.append(nid)
    return Recipe(recipe_id="combo", routes={"ebi_patch": order}, nodes=nodes,
                  score=ScoreSpec(expr="0", threshold=0.0,
                                  bins={"below": 0, "above": 1}))


#: repo 裡**現在**還在出貨的 fixture recipe 全部住在這裡。
#:
#: 以前指的是 examples/recipes/（教學範例）。那個目錄 2026-08-16 移除了，
#: 而 glob 對不存在的資料夾**回空清單、不丟例外** —— 下面那條測試會因此
#: 「檢查了 0 份 recipe」然後綠燈通過。指到 fixtures 才有東西可檢查。
FIXTURE_RECIPES = Path(__file__).resolve().parent / "fixtures" / "recipes"


def test_a_measure_card_that_needs_a_region_nobody_defines_is_caught():
    """以前這件事只有兩種下場，兩種都不好。

    名字打錯 → 每顆 defect 跑到一半 StepError；而且以前有一個保留字 ``blob``，
    上游沒有那張卡時會**安靜地改量整張圖** —— 跑得完、有數字、而且是錯的。
    （那個保留字隨著 ROI 收斂成 Profile / Template / GDS 一起拿掉了。）
    """
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "glv": RecipeNode("glv", "glv_stats", {"roi": "nobody_defines_this"}),
    }
    recipe = Recipe(recipe_id="r", routes={"ebi_patch": ["load", "glv"]},
                    nodes=nodes,
                    score=ScoreSpec(expr="1", threshold=0.5,
                                    bins={"below": 0, "above": 1}))
    codes = [i.code for i in validate(recipe, kind="ebi_patch")
             if i.level == "error"]
    assert "unknown-region" in codes

    # 補上一張 ROI 卡（Profile 定義 'nobody_defines_this'）之後就乾淨了
    nodes["roi"] = RecipeNode("roi", "roi_reference",
                              {"method": "stripes in the image",
                               "roi_out": "nobody_defines_this"})
    ok = validate(Recipe(recipe_id="r",
                         routes={"ebi_patch": ["load", "roi", "glv"]},
                         nodes=nodes,
                         score=ScoreSpec(expr="1", threshold=0.5,
                                         bins={"below": 0, "above": 1})),
                  kind="ebi_patch")
    assert [i.code for i in ok if i.level == "error"] == []


def test_measuring_two_regions_warns_instead_of_silently_losing_one():
    """特徵是**扁平的全域命名空間**，所以兩張同型別的量測卡會寫同一組名字。

    「量中心 vs 量整片」是使用者一定會做的事，而以前的下場是：跑得完、
    lint 全綠、後面那張把前面那張蓋掉，分數表達式**完全沒有辦法**指到前面
    那個值。這是 warning 不是 error（同名覆寫有時是刻意的），但它必須看得見。
    """
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        # 兩張 ROI 卡各給自己的 output_prefix —— 不然它們**自己**的特徵就先撞
        # 起來了，而這條測的是下面那兩張量測卡的撞名。
        "roiA": RecipeNode("roiA", "roi_reference",
                           {"method": "stripes in the image",
                            "roi_out": "center", "output_prefix": "a"}),
        "roiB": RecipeNode("roiB", "roi_reference",
                           {"method": "stripes in the image",
                            "roi_out": "wide", "place": "crossing",
                            "output_prefix": "b"}),
        "glvA": RecipeNode("glvA", "glv_stats",
                           {"roi": "center", "metrics": "glv_mean"}),
        "glvB": RecipeNode("glvB", "glv_stats",
                           {"roi": "wide", "metrics": "glv_mean"}),
    }
    recipe = Recipe(
        recipe_id="two_roi",
        routes={"ebi_patch": ["load", "roiA", "roiB", "glvA", "glvB"]},
        nodes=nodes, score=ScoreSpec(expr="glv_mean", threshold=0.0,
                                     bins={"below": 0, "above": 1}))
    issues = validate(recipe, kind="ebi_patch")
    collisions = [i for i in issues if i.code == "feature-collision"]
    # 兩張卡都吐 `glv_mean` 與 `glv_pixels`，但**警告只有量測值那一個**：
    # `glv_pixels` 是宣告過的診斷（「量得準不準」，每一張 GLV 都必然產出，
    # 跟 Enhance 的 `clip_frac` 同一族），兩邊都宣告就不報 —— 不然每一份
    # 有兩張 GLV 的正常 recipe 都會警告，而學會忽略一條警告之後，真的那一條
    # 也一起被忽略了。值沒有丟：engine 會留成 `glvA_glv_pixels`。
    assert len(collisions) == 1
    assert collisions[0].level == "warning", "撞名不擋執行，但要講出來"
    assert collisions[0].node_id == "glvB"
    assert "glv_mean" in collisions[0].title
    assert not any("glv_pixels" in i.title for i in collisions), \
        "診斷數字的撞名不該報 —— 報了它就是每份雙 GLV recipe 的常駐雜訊"
    assert not [i for i in issues if i.level == "error"]


def test_every_recipe_that_ships_in_the_repo_passes_lint():
    """repo 裡出貨的 recipe 自己必須全部過 lint。

    以前掃的是 ``examples/recipes/``（教學範例，使用者的起點）。那些 2026-08-16
    全部拿掉了，現在 repo 裡的 recipe 只剩 ``tests/fixtures/recipes/`` ——
    它們是 e2e 的地基，接錯了的話一整批 e2e 會用「跑得完但每顆都失敗」的方式
    壞掉。所以這條測試改了對象，要擋的事沒變。
    """
    paths = sorted(FIXTURE_RECIPES.glob("*.json"))
    assert paths, "%s 是空的 —— 這條測試會變成什麼都沒檢查" % FIXTURE_RECIPES
    bad = {}
    for path in paths:
        recipe = Recipe.load(str(path))
        errs = [i for i in validate(recipe) if i.level == "error"]
        if errs:
            bad[path.name] = [(i.code, i.node_id) for i in errs]
    assert not bad, bad


def test_every_visible_card_can_be_wired_up_without_a_dead_end():
    """每一張卡都要有一條「照著加就會通」的路，否則它在 UI 上就是死路。

    這是回饋 5（「卡片操作與組合是否相互會有問題」）的機械化版本：對每張卡
    找一組前置卡，驗證整條 route 過得了 lint。找不到 = 那張卡沒有人用得起來。
    """
    from d4t.ui.scope import visible_steps

    # 前置鏈：能滿足所有 reads / regions 的最短已知順序
    PREREQ = {
        "subtract": ["align"],
        "glv_stats": ["align", "subtract"],
        "cd_measure": ["align", "subtract", "glv_stats"],
        # GDS 那條路的上游不是影像處理，是**另一張 Input 卡**：label map 那條流
        # 由 `load_sidecar` 產（配對在 ingest 層做，見 F11 Region-3 第 2 步）。
        "roi_reference": ["load_sidecar"],
        # 比較卡吃的是**區域**，所以上游要有一張出得了區域的 Region 卡。
        # `roi_reference` 預設那一支（重複晶格）不需要任何外部資料。
        "roi_compare": ["roi_reference"],
        # 配對卡吐的那條流（配到的那顆的圖）—— 上游一樣是**另一張 Input 卡**。
        "align_to": ["pair_source"],
    }
    keys = [d["key"] for d in visible_steps([s.describe() for s in list_steps()])]
    dead_ends = {}
    needs_setup = {}
    for key in keys:
        if key == "load_patch":
            continue
        seq = ["load_patch"] + PREREQ.get(key, []) + [key]
        errs = [i for i in validate(_lint_recipe(seq), kind="ebi_patch")
                if i.level == "error"]
        # ``not-configured`` 不是接線問題（F7-13）：那張卡缺的是一份要另外匯入
        # 的東西（模板是一張影像），不是缺上游。它的路是通的，只是還沒設定完 ——
        # 所以這裡不算死路，但**訊息必須指得出路在哪**，否則它就真的是死路了。
        needs = [i for i in errs if i.code == "not-configured"]
        rest = [i for i in errs if i.code != "not-configured"]
        # 「還沒設定完」歸給**發出它的那張卡**，不是這一輪的主角 —— 前置鏈裡的
        # 卡也會講這句話（`align_to` 的上游 `pair_source` 就是），而下面要拿
        # 「引號裡的字是不是這張卡的欄位」去驗它。歸錯卡等於拿 A 的欄位表去驗
        # B 的訊息。
        for i in needs:
            nid = str(i.node_id or "")
            owner = seq[int(nid[1:])] if nid[1:].isdigit() else key
            if i.detail not in needs_setup.setdefault(owner, []):
                needs_setup[owner].append(i.detail)
        if rest:
            dead_ends[key] = [(i.code, i.detail) for i in rest]
    assert not dead_ends, "這些卡片沒有可行的組合：%s" % sorted(dead_ends)

    # 「還沒設定完」的訊息**必須指向一個使用者按得到／填得到的東西**。
    # 那有**兩種**形狀，兩種都算數（F11 Measure 的比較卡逼出了第二種）：
    #
    # * 一顆**鈕**（`…` 結尾）—— 缺的是要另外匯入的東西（模板是一張影像）；
    # * 這張卡**自己的一格**（“引號”起來的欄位名）—— 缺的只是一個要挑的值，
    #   而那一格就在旁邊。這種卡沒有鈕可以指，只認第一種的話它剩兩條路：
    #   湊一個不存在的鈕，或者乾脆不講。
    #
    # 用「或」不是「改成」：舊的那條沒有錯，只是不完整 —— 換掉它會讓
    # `roi_mask` 那種本來講得很好的訊息突然變成違規。
    #
    # 而**引號那一種要驗**：引號裡的字必須真的是這張卡的欄位名，或工具列上真的
    # 有那顆鈕。不然「指向一個東西」會退化成「寫一句看起來像樣的話」。
    import re as _re

    studio_src = (Path(__file__).resolve().parent.parent
                  / "d4t" / "ui" / "studio.py").read_text(encoding="utf-8")
    # **第三種形狀：另一張卡的名字**（F14-1）。入口從工具列搬到卡片上之後，
    # 「去哪裡做那件事」的答案是一張卡 —— 而卡名是使用者找得到的東西
    # （卡片庫裡有、畫布上也有）。它跟前兩種一樣要驗：引的必須是**真的**
    # 有那張卡，不然「指向一個東西」又退化成「寫一句看起來像樣的話」。
    card_labels = {str(c.label) for c in list_steps()}
    for key, details in needs_setup.items():
        labels = {str(p.get("label") or p["name"])
                  for p in get_step(key).describe()["params"]}
        for detail in details:
            quoted = _re.findall(r"“([^”]+)”", detail)
            real = [q for q in quoted
                    if q in labels or q in card_labels
                    or ('"%s"' % q) in studio_src]
            assert ("…" in detail or "..." in detail) or real, (
                "%s 說它還沒設定完，但沒有指向任何一個按得到／填得到的東西"
                "（要嘛一顆 `…` 結尾的鈕，要嘛“引號”起來的欄位名）：%s"
                % (key, detail))
            fake = [q for q in quoted if q not in real and not q.endswith("…")]
            assert not fake, (
                "%s 的訊息引了一個不存在的欄位／鈕：%s（這張卡的欄位：%s）"
                % (key, fake, sorted(labels)))


# --------------------------------------------------------------------------- #
# I8 每一張卡都答得出「哪幾格是進階的」
#
# 2026-08-27（F39-B3）從 `test_ui_f8_advanced.py` 搬過來。它是那一檔裡唯一
# 逐張套用到 registry 的一條，而且不碰 Qt —— 其餘十條問的是那個表單長什麼樣。
# --------------------------------------------------------------------------- #
def test_every_card_can_declare_advanced_rows():
    """``describe()`` 一定要帶這個鍵 —— UI 讀不到就整批當成非進階，
    而那是「安靜地失效」而不是「壞掉」。"""
    for step in list_steps():
        for spec in step().describe()["params"]:
            assert "advanced" in spec, "%s.%s" % (step.key, spec["name"])
            assert isinstance(spec["advanced"], bool)


# --------------------------------------------------------------------------- #
# I9：藏起來的參數不影響結果
#
# `CLAUDE.md` §3 已經寫下這條規矩，但在這之前**沒有任何東西在守它**：
#
#   「注意 `show_when` 是**顯示**規則不是驗證規則：藏起來的參數照樣有預設值，
#     卡片自己要保證用不到的參數不影響結果（`resolve_reads` 也一樣）。」
#
# 「卡片自己要保證」＝ 人要記得。而 2026-09-08 量到 registry 裡有 91 個參數掛著
# `show_when`，光 `roi_reference` 一張卡就 33 個 —— 那是 33 個要靠人記得的分支。
#
# 這條為什麼是「安靜地錯」那一族
# ------------------------------
# 藏起來的參數壞掉時，畫面上**什麼都看不到**：使用者選了 method A，畫面上只有
# A 的那幾格，而卡片偷偷讀了 B 的某一格的預設值。他改不到它、看不到它，
# 而數字是錯的。這正是這一檔開頭那張表的形狀 ——「有一條路徑讓 pipeline 安靜地
# 用了跟使用者宣告的不一樣的輸入」。
#
# 這條在這之前是**逐卡臨時做的**：`test_roi_cross.py` 對 `directions` 做了兩半
# （藏起來的那一種真的沒有作用、沒藏的那幾種有作用），`test_output_uniformity.py`
# 只留了一句註解說「⚠ show_when 是顯示規則不是驗證規則」。升成不變量之後，
# 第 20 張卡的作者不必記得來補。
# --------------------------------------------------------------------------- #
#: 換一個值的時候不碰這幾種型別。
#:
#: `image_key` / `image_keys` / `region_key` / `region_keys` 的值是**接線的結果**
#: （F9-6：設定區唯讀，來源只在畫布上拉線決定），所以「換一個值」在那裡不是
#: 使用者做得到的動作 —— 塞一個不存在的流名進去，量到的會是「引擎對壞值的
#: 反應」，不是這條不變量要問的事。
_UNSWAPPABLE = ("image_key", "image_keys", "region_key", "region_keys",
                "curve", "template", "cell_rois", "channel_map",
                "chart_spec", "chart_style", "expr", "feature_keys")


def _another_value(spec, current):
    """給這個參數挑一個**跟現在不一樣**的合法值；挑不出來回 ``None``。"""
    if spec.type in _UNSWAPPABLE:
        return None
    if spec.type == "bool":
        return not bool(current)
    if spec.type in ("int", "float"):
        bounds = [b for b in (spec.min, spec.max) if b is not None]
        if not bounds:
            return None
        cast = int if spec.type == "int" else float
        # 離現在最遠的那一界 —— 「換了值」要換得夠明顯，換到一個跟預設只差
        # 0.001 的值，就算卡片真的偷讀了它也看不出來。
        far = max(bounds, key=lambda b: abs(float(b) - float(current or 0)))
        return cast(far) if cast(far) != current else None
    if spec.type in ("choice", "chip_choice", "icon_choice"):
        for choice in (spec.choices or []):
            if choice != current:
                return choice
        return None
    if spec.type == "multi_choice":
        # 值是逗號分隔的一串。挑一個「不是現在這一串」的組合。
        picked = [c for c in (spec.choices or []) if c not in str(current or "")]
        return ",".join(picked[:2]) if picked else None
    if spec.type == "str":
        return None          # 自由文字沒有「另一個合法值」可言
    return None


def _hidden_param_cases(key: str):
    """這張卡在**預設設定下被藏起來**的參數 → ``(參數名, 另一個值)``。

    只問預設那一組設定（使用者剛從卡片庫拖出來的樣子）。要把每一個 method
    的每一種組合都走一遍的話，這組會爆炸成幾百個 case，而抓到的東西是同一
    類 —— 預設那一組已經覆蓋了每一張卡最常被走到的那條路。
    """
    cls = REGISTRY[key]
    defaults = _defaults(key)
    for spec in cls.params:
        if not getattr(spec, "show_when", None):
            continue
        if spec.visible_for(defaults):
            continue                       # 現在看得到 → 不是這條要問的
        alt = _another_value(spec, defaults.get(spec.name))
        if alt is None:
            continue
        yield spec.name, alt


def _recipe_with_probe(key: str) -> Recipe:
    """:func:`recipe_for` 再接一張**量測卡**在被測的那張後面。

    ⚠ 這一段是踩出來的。第一版直接用 ``recipe_for(key)``，然後把「偷讀一個
    藏起來的參數」這個 bug 放進 ``denoise`` 去驗 —— **測試照樣全綠**。原因是
    影像段的卡（Enhance 那四張）**根本不產 feature**：它改的是影像，而
    ``run_defect`` 回傳的 ``features`` 是空的，於是「結果不變」這句話問的是
    兩個空 dict 相不相等。

    那正是這個 repo 踩過好幾次的老樣式（測試通過，只是什麼都沒測），所以這裡
    在後面接一張 ``glv_stats`` 讀被測卡吐出來的那條流 —— **影像變了，就會有
    一個數字跟著變**。
    """
    recipe = recipe_for(key)
    if key == "glv_stats":
        return recipe                       # 它自己就是量測卡
    defaults = _defaults(key)
    writes = list(REGISTRY[key].resolve_writes(defaults))
    regions = list(REGISTRY[key].resolve_regions_out(defaults))
    if not writes and not regions:
        return recipe
    probe = dict(_defaults("glv_stats"))
    if writes:
        probe["source"] = writes[0]
    if regions:
        probe["roi"] = regions[0]
    probe["output_prefix"] = "probe"
    recipe.nodes["probe"] = RecipeNode("probe", "glv_stats", probe)
    recipe.routes[KIND].append("probe")
    return recipe


HIDDEN_CASES = sorted(
    (key, name, value)
    for key in CARDS if key not in NEEDS_MORE_SETUP
    for name, value in _hidden_param_cases(key))


@pytest.mark.parametrize("key,name,value", HIDDEN_CASES,
                         ids=["%s.%s=%s" % c for c in HIDDEN_CASES])
def test_a_hidden_parameter_changes_nothing(key, name, value, dataset):
    """把一個**畫面上看不到的**參數換掉，這張卡必須：

    1. **宣告不變** —— ``resolve_reads`` / ``resolve_writes`` /
       ``resolve_features`` / ``resolve_regions_out`` 逐項相同。
       這一半是 `CLAUDE.md` 那句「``resolve_reads`` 也一樣」的執行機構：
       藏起來的參數改變了這張卡吃哪條流的話，**畫布會多畫一條使用者拉不到、
       也看不到的線**（I3 的孿生條款）。
    2. **結果不變** —— feature 逐項相同、score 相同。

    紅了的時候要修的是**卡片**，不是這條測試：要嘛那一格其實有作用（那它就
    不該被藏起來，`show_when` 的條件寫錯了），要嘛卡片該在用不到它的時候
    真的不去讀它。
    """
    from d4t.core.pipeline.batch import pin_cv2_deterministic
    pin_cv2_deterministic()

    cls = REGISTRY[key]
    base = dict(_defaults(key))
    swapped = dict(base)
    swapped[name] = value

    def features_with(params):
        recipe = _recipe_with_probe(key)
        recipe.nodes[key].params = params
        return run_defect(recipe, dataset.items[0], dataset.kind)

    # ---- 1. 宣告不變 ----
    for what in ("resolve_reads", "resolve_writes", "resolve_features",
                 "resolve_regions_out"):
        before = list(getattr(cls, what)(base))
        after = list(getattr(cls, what)(swapped))
        assert before == after, (
            "%s 的 %s 是藏起來的，但把它換成 %r 之後 %s() 變了：%s → %s\n"
            "  畫布是照這個宣告畫線的，所以這會畫出一條使用者看不到、"
            "也改不到的線。"
            % (key, name, value, what, before, after))

    # ---- 2. 結果不變 ----
    before = features_with(base)
    after = features_with(swapped)

    assert before.ok == after.ok, (
        "%s 的 %s 是藏起來的，但把它換成 %r 之後這一顆從 ok=%s 變成 ok=%s（%s）"
        % (key, name, value, before.ok, after.ok, after.error))
    if not before.ok:
        return                      # 兩邊都失敗且理由一致 → 不是這條要問的

    diff = sorted(
        k for k in set(before.features or {}) | set(after.features or {})
        if (before.features or {}).get(k) != (after.features or {}).get(k))
    assert not diff, (
        "%s 的 %s 在畫面上是藏起來的，但把它換成 %r 之後這幾個特徵變了：%s\n"
        "  使用者看不到那一格、也改不到它，而數字跟著動了 —— "
        "要嘛 show_when 的條件寫錯，要嘛卡片在用不到它的時候還是讀了它。"
        % (key, name, value, [(k, (before.features or {}).get(k),
                               (after.features or {}).get(k)) for k in diff]))
    assert before.score == after.score, (
        "%s 的 %s 是藏起來的，但分數從 %r 變成 %r"
        % (key, name, value, before.score, after.score))


def test_the_hidden_parameter_check_is_not_vacuous():
    """真的有藏起來的參數被換過 —— 不然這組會安靜地空轉。

    2026-09-08：registry 有 91 個參數掛 `show_when`，這組蒐集到 %d 個 case。
    數字掉到個位數的話，要嘛是 `_UNSWAPPABLE` 排掉太多，要嘛是 `_defaults`
    那一組設定剛好什麼都藏不住 —— 兩種都要看一眼。
    """
    assert len(HIDDEN_CASES) >= 12, len(HIDDEN_CASES)
    assert len({key for key, _n, _v in HIDDEN_CASES}) >= 3, HIDDEN_CASES


def test_the_setup_exception_list_has_no_ghosts():
    """:data:`NEEDS_MORE_SETUP` 上不准留已經不存在的卡片 key。

    這一條是 `NEEDS_MORE_SETUP` 自己的註解點名要的（2026-08-27 寫下、
    2026-09-08 補上）：

      「**這張表上留一個不存在的 key 沒有任何測試會叫**，而它會讓下一個讀的人
        以為那張卡還在（`CLAUDE.md`：任何『例外清單』都要有一支反向的測試，
        而這一張目前沒有）。」

    而它已經發生了：`roi_template` 與 `roi_from_mask` 兩張卡分別在 F29 與 F74
    被併掉／刪掉，兩列卻留到現在 —— 於是這張表一邊說「這幾張卡跳過」，
    一邊指著兩張不存在的卡。
    """
    ghosts = sorted(k for k in NEEDS_MORE_SETUP if k not in REGISTRY)
    assert not ghosts, (
        "NEEDS_MORE_SETUP 上這幾個 key 已經不在 registry 裡了：%s\n"
        "  卡片刪掉或改名之後那一列要跟著拿掉，不然這張表會指著不存在的卡。"
        % ghosts)
