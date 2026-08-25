# 鐵則 9：``to_json_dict → from_json_dict`` 必須是 identity。
"""那不是潔癖，是 `run_batch` 送 recipe 進 worker 的路（`batch.py:81`）——
主行程持有的是一份 `Recipe` 物件，worker 拿到的是它 `to_json_dict()` 之後再
`from_json_dict()` 重建的另一份。兩份只要有一格不同，**`workers=1` 與
`workers=2` 就會算出不同的分數**，而且兩邊都跑得完、都有數字。

`CLAUDE.md` 鐵則 9 寫著「真的發生過」。

為什麼要一份專門的測試（既有的抓不到）
--------------------------------------
`tests/test_batch_cache.py::test_serial_parallel_and_m1_agree` 是真的開
`workers=2` 的 —— 但它跑的是一份**特定**的 recipe，而破壞 identity 的東西
通常長在「某一種形狀的 recipe」上。F17-② 那道遷移就是這樣：它只在**節點 id
剛好等於一個流名**時才不冪等，而那份 fixture 沒有那個形狀。

所以這一份走另一條路：**對每一份 fixture ＋ 一組刻意造出來的對抗案例**，
直接驗 round-trip 的不動點性質。

⚠ **遷移不在這條路上**（F17 審查的結論）：`from_json_dict` 是「重建一個物件」，
`Recipe.load` 才是「讀一個檔案」。遷移屬於後者 —— 見 `Recipe.load` 的說明。
下面 `test_loading_a_file_still_migrates` 守著「搬過去之後檔案那一路沒有壞掉」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import Recipe  # noqa: E402

FIXTURES = sorted((REPO / "tests" / "fixtures" / "recipes").glob("*.json"))
KIND = "ebi_patch"


def _fixed_point(d: dict, rounds: int = 3) -> None:
    """連續 round-trip ``rounds`` 次，每一次都要跟上一次一模一樣。

    只跑一次是不夠的：F17-② 那個 bug 要**第二次**才顯形（第一次是正常的遷移，
    第二次才把已經遷移過的名字再改一次）。
    """
    seen = Recipe.from_json_dict(d).to_json_dict()
    for i in range(rounds):
        again = Recipe.from_json_dict(seen).to_json_dict()
        assert again == seen, (
            "第 %d 次 round-trip 就不一樣了 —— worker 拿到的 recipe 會跟主行程"
            "不同（鐵則 9）。差在：%s"
            % (i + 2, sorted(k for k in set(again) | set(seen)
                             if again.get(k) != seen.get(k))))
        seen = again


# --------------------------------------------------------------------------- #
# 1. 每一份 fixture 都是不動點
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_recipe_is_a_fixed_point(path):
    _fixed_point(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# 2. 對抗案例：節點 id 剛好等於一個流名
# --------------------------------------------------------------------------- #
def _recipe_with_node_named(nid: str, streams: str) -> dict:
    """一份含撞名特徵的 recipe，其中一個節點的 id 是 `nid`。

    `norm_ref` 與 `norm` 都吐 `clip_frac` → 撞名 → 引擎會把被蓋掉的那份救成
    `<流名>_clip_frac`（F17-②）。而 `nid` 如果剛好等於某個流名，那個救出來的
    名字就跟「`nid` 這張卡的特徵」長得一模一樣。
    """
    return {
        "recipe_id": "adversarial", "version": 3,
        "routes": {KIND: ["load", "norm_ref", "norm", nid]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "norm_ref": {"id": "norm_ref", "step": "normalize",
                         "params": {"streams": "ref", "range_from": "test"}},
            "norm": {"id": "norm", "step": "normalize",
                     "params": {"streams": "test"}},
            nid: {"id": nid, "step": "normalize",
                  "params": {"streams": streams}}},
        "score": {"expr": "norm_clip_frac + 1", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }


@pytest.mark.parametrize("nid,streams", [
    ("test", "diff"),        # 節點 id ＝ 最常見的那條流名
    ("ref", "diff"),
    ("diff", "test"),
])
def test_a_node_named_like_a_stream_is_still_a_fixed_point(nid, streams):
    """**這一條是 F17 審查抓到的那個 bug 的迴歸測試。**

    以前：第一次 `norm_clip_frac` → `test_clip_frac`；第二次那個名字又符合
    「節點 `test` 產出的 `clip_frac`」的形狀，於是再被改成 `diff_clip_frac`。
    """
    _fixed_point(_recipe_with_node_named(nid, streams))


def test_whether_a_node_id_can_still_equal_a_stream_name():
    """上面那組對抗案例**現在還從卡片庫裡拉得出來嗎**。

    節點 id 就是 step key（`viewmodel._new_id`），所以只要有一張卡的 key 跟它
    自己吐出來的流名相同，使用者從卡片庫拉一張進來就是那個形狀。以前那張卡是
    `snr_map`（key 與流名都叫 `snr_map`）。

    ⚠ **2026-08-25 起答案是「拉不出來」**：Z-map 刪掉之後，卡片庫裡一張都
    沒有。所以這一條現在記錄的是**這件事**，而不是假裝還有一個活例子 ——
    上面那組 round-trip 案例因此從「觀察到的形狀」降級成「防守用的形狀」，
    它們仍然該綠（規則沒變），但沒有人再從畫面上走到那裡。

    哪一天又有一張卡長成那樣（很容易：一張卡叫 `mask`、又吐一條叫 `mask` 的
    流），這一條會**紅**，而那正是它要講的話：對抗案例重新變成真的了。
    """
    from d4t.core.pipeline.step import REGISTRY

    live = []
    for key, cls in REGISTRY.items():
        p = {sp.name: sp.default for sp in cls.params}
        try:
            if key in set(cls.resolve_writes(p)):
                live.append(key)
        except Exception:          # noqa: BLE001 — 參數湊不齊的卡跳過
            continue
    assert live == [], (
        "卡片庫又有 key 等於自己流名的卡了：%s —— 上面那組 round-trip 對抗"
        "案例重新變成活的，請把這條測試改回斷言它們可達" % live)


# --------------------------------------------------------------------------- #
# 3. 遷移還在，只是搬到「讀檔案」那一路
# --------------------------------------------------------------------------- #
def test_loading_a_file_still_migrates(tmp_path):
    """遷移屬於**讀一個檔案**，不屬於重建一個物件。

    搬家不能把功能搬丟：舊 recipe 的分數表達式指著舊名字時，`Recipe.load`
    仍然要換過來，否則那份 recipe 打開來是一條 `unknown-feature` 加一個算不出
    來的分數 —— 而那個分數是這份 recipe 存在的理由。
    """
    old = {
        "recipe_id": "old", "version": 3,
        "routes": {KIND: ["load", "norm_ref", "norm"]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "norm_ref": {"id": "norm_ref", "step": "normalize",
                         "params": {"streams": "ref", "range_from": "test"}},
            "norm": {"id": "norm", "step": "normalize",
                     "params": {"streams": "test"}}},
        "score": {"expr": "norm_clip_frac + norm_ref_clip_frac * 2",
                  "threshold": 1.0, "bins": {"below": 0, "above": 1}},
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    assert Recipe.load(path).score.expr == "test_clip_frac + ref_clip_frac * 2"


def test_rebuilding_an_object_does_not_migrate():
    """反過來也要成立 —— 那正是 identity 的來源。

    `from_json_dict` 拿到的是**已經在記憶體裡的一份 recipe** 的 JSON，它不需要
    也不可以再遷移一次。worker 走的就是這一條。
    """
    old = {
        "recipe_id": "old", "version": 3,
        "routes": {KIND: ["load", "norm"]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "norm": {"id": "norm", "step": "normalize",
                     "params": {"streams": "test"}}},
        "score": {"expr": "norm_clip_frac", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    assert Recipe.from_json_dict(old).score.expr == "norm_clip_frac"


# --------------------------------------------------------------------------- #
# 4. 多 route：遷移算出來的名字要跟引擎產出的一致
# --------------------------------------------------------------------------- #
def test_a_two_route_recipe_migrates_per_route(tmp_path):
    """**執行時是每條 route 各算一次前綴**（`_run_nodes` 用該 route 的
    `order`），所以遷移也要照 route 算。

    以前遷移拿整份 `nodes` 一起算：兩條 route 各有一張 normalize 時，去重的
    池子多了一個成員 → 判定撞名 → 兩張都退回節點 id → **整份 recipe 一個字都
    沒遷移**，而引擎產出的是新名字。症狀是一條 `unknown-feature`。
    """
    old = {
        "recipe_id": "two", "version": 3,
        "routes": {KIND: ["load", "nA"], "rsem": ["load_single", "nB"]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "load_single": {"id": "load_single", "step": "load_single",
                            "params": {}},
            "nA": {"id": "nA", "step": "normalize",
                   "params": {"streams": "test"}},
            "nB": {"id": "nB", "step": "normalize",
                   "params": {"streams": "test"}}},
        "score": {"expr": "nA_clip_frac", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
    }
    path = tmp_path / "two.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    assert Recipe.load(path).score.expr == "test_clip_frac"
