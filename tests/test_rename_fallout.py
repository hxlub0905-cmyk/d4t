# d4t 測試 — F37 A2：改名的連帶影響（2026-08-26）.
"""量測卡的前綴是**條件式的**，所以拉一條線會把它寫的每一個名字都改掉。

`MultiSourceStep.stream_prefix` / `region_prefix` 只在「超過一個」的時候才加
前綴。於是在一張既有的卡上多接一條區域線：

    glv_median  →  epi_glv_median  ＋  mg_glv_median

而分數表達式、判定樹、Output 卡的 ``rank_by`` 裡指著舊名字的那幾個字**不會
跟著改**。使用者只做了一個動作（拉一條線），下游三個地方同時失效。

條件式前綴本身**沒有被改掉**（那要遷移每一份既有 recipe 加重凍三份黃金值，
使用者定調先不做）。危險的不是它，是「改名是安靜的」—— 這一份守的正是那件事
不再安靜。兩層：

1. **當下** —— `RecipeModel.set_param` 回一串話（狀態列講）。
2. **一直** —— `stale-feature-ref` 這條 lint 讓那張卡在畫布上掛著警示標記。

狀態列的字會被下一個動作蓋掉，所以第一層不能是唯一的防線。
"""
from __future__ import annotations

import pytest

import d4t.core.steps  # noqa: F401 — 註冊卡片
from d4t.core.pipeline.recipe import (Recipe, RecipeNode, ScoreSpec,
                                      feature_referrers, mentions_feature,
                                      validate)
from d4t.core.pipeline.step import get_step


# --------------------------------------------------------------------------- #
# 1. 誰還指著這個名字（純函式）
# --------------------------------------------------------------------------- #
def test_a_name_inside_a_longer_name_is_not_a_reference():
    """``glv_median`` 出現在 ``epi_glv_median`` 裡面 —— 那是兩個不同的數字。

    用 ``in`` 比對的話，改名的連帶影響會把「加了前綴之後的自己」算成引用者，
    於是每一次拉線都報一句假警報 —— 而學會忽略警報之後，真的那一條也沒了。
    """
    assert mentions_feature("glv_median > 3", "glv_median")
    assert not mentions_feature("epi_glv_median > 3", "glv_median")
    assert not mentions_feature("", "glv_median")


def test_it_finds_every_place_a_feature_name_can_live():
    """每一個地方跟改名遷移走的**同一份清單**。

    ⚠ 以前叫「四個地方」，第四個是 `feature_math` 的算式 —— 那張卡 2026-08-27
    刪掉了（Phase 3）。剩下三種：分數表達式、判定段、以及卡片參數裡的特徵名
    （單獨一格的 `feature_key` 與一串的 `feature_keys`）。

    ⚠ 兩支要一起看：遷移是「自動搬」，這一支是「搬不動的時候說出搬不動的是
    哪幾個」。少一個地方的話，那個地方就是安靜失效的那一個。
    """
    from d4t.core.pipeline.recipe import DecideSpec, TreeLeaf, TreeStep

    nodes = {
        "glv": RecipeNode("glv", "glv_stats",
                          {"source": "test", "metrics": "glv_median"}),
        "img": RecipeNode("img", "output_report",
                          {"folder": "/tmp/x", "rank_by": "glv_median"}),
        # 同一張卡的第二個節點，這一次是 box plot 那一格（F38 併進來的，
        # 而它的參數名也跟著換了：`features` → `plot_features`）。
        "bp": RecipeNode("bp", "output_report",
                         {"folder": "/tmp/x", "contents": "boxplot",
                          "plot_features": "cd_median,glv_median"}),
    }
    decide = DecideSpec(tree=TreeStep(when="glv_median > 3",
                                      yes=TreeLeaf(bin=1, label="hot"),
                                      no=TreeLeaf(bin=0, label="ok")))
    where = feature_referrers("glv_median", nodes,
                              score_expr="glv_median + 1", decide=decide,
                              skip="glv")
    joined = " | ".join(where)
    assert "the score expression" in joined
    assert "the decision" in joined
    assert "img" in joined           # 單獨一格特徵名（feature_key）
    assert "bp" in joined            # 一串特徵名（feature_keys）


def test_the_card_being_rewired_is_not_its_own_referrer():
    """改名的那張卡是**來源**，不是引用者 —— 不然每一次都會報自己。"""
    nodes = {"glv": RecipeNode("glv", "glv_stats",
                               {"source": "test", "metrics": "glv_median"})}
    assert feature_referrers("glv_median", nodes, skip="glv") == []


# --------------------------------------------------------------------------- #
# 2. 當下：拉一條線，model 就講得出來
# --------------------------------------------------------------------------- #
def _wired_model():
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel()
    m.add_step("load_patch")
    roi = m.add_step("roi_reference")
    for k, v in (("method", "stripes in the image"), ("source", "test"),
                 ("roi_out", "epi")):
        m.set_param(roi, k, v)
    glv = m.add_step("glv_stats")
    for k, v in (("source", "test"), ("metrics", "glv_median"), ("roi", "epi")):
        m.set_param(glv, k, v)
    out = m.add_step("output_report")
    m.set_param(out, "folder", "/tmp/x")
    m.set_param(out, "rank_by", "glv_median")
    m.set_expr("glv_median")
    return m, glv, out


def test_wiring_a_second_region_says_what_stopped_existing():
    """接第二條區域線 → 名字全部改掉，而下游沒有跟著改。

    ⚠ **把 `set_param` 裡的 `rename_fallout` 那一行拿掉，這支測試會紅。**
    """
    pytest.importorskip("PySide6")
    m, glv, _out = _wired_model()

    before = get_step("glv_stats").resolve_features(m.nodes[glv].params)
    assert "glv_median" in before

    says = m.set_param(glv, "roi", "epi,epi_center")

    after = get_step("glv_stats").resolve_features(m.nodes[glv].params)
    assert "glv_median" not in after and "epi_glv_median" in after
    assert says, "改名了卻一句話都沒說"
    joined = " ".join(says)
    assert "glv_median" in joined
    assert "score expression" in joined       # 分數表達式指空了
    assert "output_report" in joined          # Output 卡那一格也是


def test_a_change_that_renames_nothing_says_nothing():
    """調一個不影響名字的參數不該講話 —— 每次都講的提醒會被學會忽略。"""
    pytest.importorskip("PySide6")
    m, glv, _out = _wired_model()
    assert m.set_param(glv, "min_pixels", 10) == []


def test_unticking_a_statistic_is_a_rename_too():
    """在設定區少勾一個統計量，那個數字就從此不存在 —— 跟拉線同一件事。"""
    pytest.importorskip("PySide6")
    m, glv, _out = _wired_model()
    says = m.set_param(glv, "metrics", "glv_mad")
    assert says and "glv_median" in " ".join(says)


# --------------------------------------------------------------------------- #
# 3. 一直：lint 讓那張卡掛著標記
# --------------------------------------------------------------------------- #
def _recipe(roi):
    return Recipe(
        recipe_id="a2", routes={"ebi_patch": ["load", "r1", "glv", "out"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "r1": RecipeNode("r1", "roi_reference",
                             {"method": "stripes in the image",
                              "source": "test", "roi_out": "epi"}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "roi": roi,
                               "metrics": "glv_median"}),
            "out": RecipeNode("out", "output_report",
                              {"folder": "/tmp/x", "rank_by": "glv_median"}),
        },
        score=ScoreSpec(expr="glv_median", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def test_a_stale_rank_by_is_a_warning_not_an_error():
    """出圖卡指到一個沒人算出來的數字 → **warning**，不是 error。

    契約在 `Step.configuration_issues` / `configuration_hints` 那一對上寫著：
    error 是「會失敗」、warning 是「跑得起來，但你八成不是這個意思」。
    出圖卡照樣寫得出圖 —— 它只是**安靜地退回檔案順序**，而使用者拿到 N 張
    正常的圖，「最值得看的那 N 顆」完全沒有發生（F30 修過一次的那個 bug）。

    ⚠ **把 `optional_features_in` 從 `OutputReportStep` 拿掉，這支會紅。**
    """
    stale = [i for i in validate(_recipe("epi,epi_center"), kind="ebi_patch")
             if i.code == "stale-feature-ref"]
    assert stale, "拉線改名之後，指空的那張卡沒有被標出來"
    assert stale[0].level == "warning"
    assert stale[0].node_id == "out"
    assert "glv_median" in stale[0].detail


def test_one_region_is_clean():
    """只接一條線的時候名字沒有變 —— 不該有任何一句話。"""
    assert not [i for i in validate(_recipe("epi"), kind="ebi_patch")
                if i.code == "stale-feature-ref"]


def test_the_score_sentinel_is_never_stale():
    """``rank_by`` 的預設 ``score`` 不是任何一張卡算出來的東西。"""
    r = _recipe("epi")
    r.nodes["out"].params["rank_by"] = "score"
    assert not [i for i in validate(r, kind="ebi_patch")
                if i.code == "stale-feature-ref"]


def test_klarf_does_not_complain_about_a_size_feature_it_is_not_using():
    """``size_feature`` 有一個非空的預設，而「一格目標欄位都沒填」是正常用法。

    照型別無條件掃的話，那種 recipe 會因為一個**沒有在用的預設值**被報一句話
    —— 而每一份正常 recipe 上都會出現的警告會被學會忽略。
    """
    card = get_step("output_klarf")
    base = {"mode": "inplace", "path": "/tmp/x.klarf",
            "size_feature": "cd_median"}
    assert card.optional_features_in(dict(base, size_col="")) == []
    assert card.optional_features_in(dict(base, size_col="DSIZE")) == ["cd_median"]
    assert card.optional_features_in(dict(base, mode="annotate")) == []
