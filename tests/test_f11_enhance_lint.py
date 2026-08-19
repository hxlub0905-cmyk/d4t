"""F11 Enhance-3：兩支 lint —— 兩張圖不再可比、自動正規化排在手動調色之後。

兩個都是「跑得完、有數字、而且是錯的」，而且**兩個在畫面上都好看**：

- test 正規化了、ref 沒有 → 兩張圖各自都漂亮，但已經不在同一個灰階尺度上，
  而 `subtract` 減出來的整片偏移看起來就是一個大面積的缺陷。
- `tone` 排在 `normalize` 前面 → 使用者手動調的亮度被後面的正規化再拉回去，
  也就是他那一步**完全沒有作用**，而畫面上看起來是有的。

為什麼要 lint 而不是只靠 `pair_level_delta`（F11 UI-B 那個特徵）：**特徵要跑過
才有，lint 在按下 Run 之前就講得出來**。兩者不能互相取代。
"""
from __future__ import annotations

import json

import pytest

from d4t.core.pipeline import get_step
from d4t.core.pipeline.recipe import (
    Edge, Recipe, RecipeNode, ScoreSpec, validate,
)
import d4t.core.steps  # noqa: F401 - 註冊卡片


def _recipe(nodes, edges, kind: str = "ebi_patch") -> Recipe:
    return Recipe(
        recipe_id="lint_test",
        routes={kind: [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2])) for n in nodes},
        score=ScoreSpec(expr="0", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="lint",
        edges=[Edge(*e) for e in edges])


def _codes(recipe) -> list:
    return [i.code for i in validate(recipe)]


def _detail(recipe, code: str) -> str:
    got = [i for i in validate(recipe) if i.code == code]
    assert got, "沒有 %s：%s" % (code, _codes(recipe))
    return got[0].detail


LOAD = ("load", "load_patch", {})
SUB = ("sub", "subtract", {"a": "test", "b": "ref", "out": "diff"})


# --------------------------------------------------------------------------- #
# 1. 兩條要比較的流受到不同的處理
# --------------------------------------------------------------------------- #
def test_normalizing_only_one_of_the_two_streams_is_a_warning():
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test"}), SUB],
        [("load", "n1", "test", "streams"), ("n1", "sub", "test", "a"),
         ("load", "sub", "ref", "b")])
    assert "uneven-treatment" in _codes(r)
    d = _detail(r, "uneven-treatment")
    assert "'test' went through Normalize" in d
    assert "'ref' went through nothing" in d
    # 那句話要講得出**下一步怎麼做**，而正確做法是 F7-19 的一張卡接兩條流
    assert "ONE Enhance card at both streams" in d


def test_it_is_a_warning_not_an_error():
    """recipe 照樣跑得完，而且「刻意只處理一條」偶爾是對的（例如只有 test 有
    charging）。它必須看得見，但不該擋住 Run。"""
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test"}), SUB],
        [("load", "n1", "test", "streams"), ("n1", "sub", "test", "a"),
         ("load", "sub", "ref", "b")])
    got = [i for i in validate(r) if i.code == "uneven-treatment"]
    assert got[0].level == "warning"
    assert got[0].node_id == "sub", "要指在比較的那張卡上（使用者從它看回去）"


def test_one_card_pointed_at_both_streams_is_silent():
    """**F7-19 的正確寫法**：一張卡接兩條流，兩條吃同一組設定。"""
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test,ref"}), SUB],
        [("load", "n1", "test", "streams"), ("load", "n1", "ref", "streams"),
         ("n1", "sub", "test", "a"), ("n1", "sub", "ref", "b")])
    assert _codes(r) == []


def test_two_cards_with_the_same_settings_are_silent():
    """一張接 test、一張接 ref 但設定一樣 —— 那也是可比的，不要叫。

    這一條是這支 lint 會不會被信任的關鍵：它比的是**設定**，不是接線
    （接線一定不一樣，不然就不是兩張卡了）。
    """
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test", "p_low": 3.0}),
         ("n2", "normalize", {"streams": "ref", "p_low": 3.0}), SUB],
        [("load", "n1", "test", "streams"), ("load", "n2", "ref", "streams"),
         ("n1", "sub", "test", "a"), ("n2", "sub", "ref", "b")])
    assert "uneven-treatment" not in _codes(r)


def test_two_cards_with_different_settings_name_the_setting():
    """同樣的卡、不同的參數 —— 訊息要指出**差在哪一格**。

    以前這裡會印成「'test' 經過 Normalize，而 'ref' 經過 Normalize」，
    一句自我矛盾的話（實際差在 p_low 是 3 還是 12）。
    """
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test", "p_low": 3.0}),
         ("n2", "normalize", {"streams": "ref", "p_low": 12.0}), SUB],
        [("load", "n1", "test", "streams"), ("load", "n2", "ref", "streams"),
         ("n1", "sub", "test", "a"), ("n2", "sub", "ref", "b")])
    d = _detail(r, "uneven-treatment")
    assert "different settings" in d
    assert "Low percentile" in d, "要用使用者看得到的欄位名（ParamSpec.label）"
    assert "3.0" in d and "12.0" in d


def test_the_order_of_the_same_cards_counts():
    """先 Denoise 再 Normalize，跟先 Normalize 再 Denoise，出來的圖不一樣。"""
    r = _recipe(
        [LOAD,
         ("a1", "denoise", {"streams": "test"}),
         ("a2", "normalize", {"streams": "test"}),
         ("b1", "normalize", {"streams": "ref"}),
         ("b2", "denoise", {"streams": "ref"}), SUB],
        [("load", "a1", "test", "streams"), ("a1", "a2", "test", "streams"),
         ("load", "b1", "ref", "streams"), ("b1", "b2", "ref", "streams"),
         ("a2", "sub", "test", "a"), ("b2", "sub", "ref", "b")])
    d = _detail(r, "uneven-treatment")
    assert "Denoise, Normalize" in d and "Normalize, Denoise" in d


def test_align_gets_the_same_check():
    """對位也是「拿兩張圖互相比」—— 灰階尺度不一樣，相關性就找錯位置。"""
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "ref"}),
         ("al", "align", {"moving": "ref", "fixed": "test",
                          "search_radius": 6})],
        [("load", "n1", "ref", "streams"), ("n1", "al", "ref", "moving"),
         ("load", "al", "test", "fixed")])
    assert "uneven-treatment" in _codes(r)


def test_a_stream_that_was_computed_upstream_is_not_compared():
    """`diff` 跟 `test` 比「處理歷史」沒有意義 —— 它們的來歷本來就不同。

    這是這支 lint 不誤報的另一半（誤報一次，使用者就學會忽略它）。
    """
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test,ref"}), SUB,
         ("s2", "subtract", {"a": "diff", "b": "test", "out": "diff2"})],
        [("load", "n1", "test", "streams"), ("load", "n1", "ref", "streams"),
         ("n1", "sub", "test", "a"), ("n1", "sub", "ref", "b"),
         ("sub", "s2", "diff", "a"), ("n1", "s2", "test", "b")])
    assert "uneven-treatment" not in _codes(r)


def test_measure_cards_are_not_dragged_into_this():
    """量測卡讀兩條流不代表它在「比較」它們（例如 snr_map 的多來源）。"""
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test"}),
         ("m", "snr_map", {"image_keys": "test,ref"})],
        [("load", "n1", "test", "streams"), ("n1", "m", "test", "image_keys"),
         ("load", "m", "ref", "image_keys")])
    assert "uneven-treatment" not in _codes(r)


# --------------------------------------------------------------------------- #
# 2. 自動正規化排在手動調色之後
# --------------------------------------------------------------------------- #
def test_normalize_after_tone_is_a_warning():
    """`tone.py` 的 docstring 早就寫了這條，但沒有任何人檢查它。"""
    r = _recipe(
        [LOAD, ("t", "tone", {"streams": "test", "brightness": 20.0}),
         ("n", "normalize", {"streams": "test"})],
        [("load", "t", "test", "streams"), ("t", "n", "test", "streams")])
    assert "card-order" in _codes(r)
    d = _detail(r, "card-order")
    assert "has no effect on what gets measured" in d
    assert "Put the manual card after the automatic one" in d


def test_the_documented_order_is_silent():
    r = _recipe(
        [LOAD, ("n", "normalize", {"streams": "test"}),
         ("t", "tone", {"streams": "test", "brightness": 20.0})],
        [("load", "n", "test", "streams"), ("n", "t", "test", "streams")])
    assert "card-order" not in _codes(r)


def test_the_two_cards_on_different_streams_do_not_trigger_it():
    """調 test 的色、正規化 ref —— 順序上沒有互相抵銷（雖然那會是 uneven）。"""
    r = _recipe(
        [LOAD, ("t", "tone", {"streams": "test", "brightness": 20.0}),
         ("n", "normalize", {"streams": "ref"})],
        [("load", "t", "test", "streams"), ("load", "n", "ref", "streams")])
    assert "card-order" not in _codes(r)


def test_it_is_reported_once_per_card_not_once_per_stream():
    """兩條流都中的時候講一次就夠 —— 同一張卡兩條訊息是噪音。"""
    r = _recipe(
        [LOAD, ("t", "tone", {"streams": "test,ref", "brightness": 20.0}),
         ("n", "normalize", {"streams": "test,ref"})],
        [("load", "t", "test", "streams"), ("load", "t", "ref", "streams"),
         ("t", "n", "test", "streams"), ("t", "n", "ref", "streams")])
    assert [c for c in _codes(r) if c == "card-order"] == ["card-order"]


# --------------------------------------------------------------------------- #
# 3. 不要在正常的 recipe 上叫（推廣鐵則）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", [
    "tests/fixtures/recipes/dual_route_basic.json",
    "tests/fixtures/recipes/die_to_die_basic.json",
])
def test_the_reference_recipes_stay_completely_clean(path):
    """**一支會誤報的 lint 比沒有 lint 更糟**：使用者學會忽略它之後，
    真的那一條也被忽略了（推廣鐵則）。

    這兩份就是「一份正常的 recipe」的定義 —— 它們一條警告都不該有。
    """
    r = Recipe.from_json_dict(json.load(open(path, encoding="utf-8")))
    assert validate(r) == []


def test_diagnostic_features_do_not_count_as_a_collision():
    """`clip_frac` 是**每一張** Enhance 卡都會產出的，所以兩張卡必然撞名 ——
    那個警告會出現在每一份正常的 recipe 上。

    值沒有丟：engine 的 `_rescue_overwritten_features` 把前一張的值留成
    `<節點名>_clip_frac`（黃金值裡的 `norm_clip_frac` 就是它）。跳掉的只是那句話。
    """
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test", "p_low": 3.0}),
         ("n2", "normalize", {"streams": "ref", "p_low": 3.0})],
        [("load", "n1", "test", "streams"), ("load", "n2", "ref", "streams")])
    assert _codes(r) == []
    # 但**真的量測值**撞名還是要講（兩張量測卡寫同一組名字）
    r2 = _recipe(
        [LOAD, ("m1", "glv_stats", {"source": "test"}),
         ("m2", "glv_stats", {"source": "ref"})],
        [("load", "m1", "test", "source"), ("load", "m2", "ref", "source")])
    assert "feature-collision" in _codes(r2)


def test_enhance_cards_declare_which_of_their_numbers_are_diagnostics():
    """宣告在卡片上（不是在 lint 裡列一張名單）—— 之後加一張 Enhance 卡就自動
    對，而 lint 一行都不用改。"""
    cls = get_step("denoise")
    p = {"streams": "test", "method": "median"}
    assert set(cls.diagnostic_features(p)) == set(cls.resolve_features(p))
    # 量測卡沒有診斷數字：它報的每一個都是量出來的
    assert get_step("glv_stats").diagnostic_features({"source": "test"}) == []
