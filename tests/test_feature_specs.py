# PR-3（3a）：FeatureSpec —— 結構在名字誕生處建立，不事後拆字串。
"""三半鐵測試：

* **A 半（registry 全掃）**：每張卡、每組代表參數下
  ``[s.name for s in resolve_feature_specs(p)] == resolve_features(p)``
  （順序也同）、``{s.name: s.parts()} == feature_parts(p)``、card==key。
* **B 半（字面快照）**：~20 組結構上有趣的案例，名字清單**寫死在這個檔案裡**
  （在 spec-first 重構之前對現行碼抓的）。spec-first 之後 A 半是套套邏輯
  （名字由 spec 導出），B 半才是「一個位元組不改」的真鐵。
* **C 半（反空洞）**：variant/metric/stat/region_role 真的有人填 ——
  防 hook 全回空字串而 A/B 照樣綠。

⚠ 宣告是「**可能**產出」（nm 孿生、snr/tstat、worst 家族、carry 欄）——
這裡永遠比宣告對宣告，不比 ``ctx.features``。
"""
from __future__ import annotations

import pytest

import d4t.core.steps  # noqa: F401 - 註冊卡片
from d4t.core.pipeline.step import REGISTRY

#: 結構上有趣的參數組（B/C 半用；A 半再加上每張卡的預設值）。
CASES = {
    "glv_bare": ("glv_stats", {"source": "test", "metrics": "glv_median"}),
    "glv_multistream": ("glv_stats", {"source": "diff,test", "metrics": "glv_max"}),
    "glv_stream_own": ("glv_stats", {"source": "diff,test", "metrics": "glv_max", "output_prefix": "center"}),
    "glv_multiregion": ("glv_stats", {"source": "test", "roi": "epi,mg", "metrics": "glv_median,glv_mad"}),
    # ⚠ autofill 陷阱：單區域時 region 前綴是空的，Studio 把區域名填進
    # output_prefix —— `epi_glv_median` 的身分是 own="epi"、region=""。
    "glv_autofill": ("glv_stats", {"source": "test", "roi": "epi", "output_prefix": "epi", "metrics": "glv_median"}),
    "glv_center_ref": ("glv_stats", {"source": "test", "roi": "epi_center,epi_others", "metrics": "glv_median", "reference_region": "mg", "compare_metrics": "delta", "stat": "glv_median"}),
    "glv_eachbox": ("glv_stats", {"source": "test", "metrics": "glv_median", "across_boxes": "each box", "min_pixels": 5, "reference_region": "bg", "compare_metrics": "delta,snr,overlap,spread_ratio", "stat": "glv_median,glv_q90"}),
    "cd_line": ("cd_measure", {"source": "test"}),
    "cd_blob": ("cd_measure", {"source": "test", "shape": "blob"}),
    "cd_blob_size": ("cd_measure", {"source": "test", "shape": "blob", "size_report": "cd_area_px,cd_roundness"}),
    "cd_target": ("cd_measure", {"source": "test", "report": "cd_median,cd_dev,cd_dev_frac", "target_cd": 120.0}),
    "cd_no_target": ("cd_measure", {"source": "test", "report": "cd_median,cd_dev,cd_dev_frac", "target_cd": 0.0}),
    "cd_multi": ("cd_measure", {"source": "a,b", "output_prefix": "x", "roi": "top,bot"}),
    "focus_multi": ("focus_quality", {"source": "test,ref", "output_prefix": "q"}),
    "roi_profile": ("roi_reference", {"method": "stripes in the image", "roi_out": "cells"}),
    "roi_profile_nopick": ("roi_reference", {"method": "stripes in the image", "roi_out": "cells", "pick": "none"}),
    "roi_gds": ("roi_reference", {"method": "layout layers", "layers": "17:epi,18:mg"}),
    "enhance_two": ("normalize", {"streams": "test,ref"}),
    "denoise_hot": ("denoise", {"streams": "test", "method": "hot_pixels"}),
    "load_carry": ("load_patch", {"carry": "roughbinnumber,score"}),
    "pair_rank": ("pair_source", {"rank_by": "SCORE", "carry": "SCORE"}),
}

#: B 半：2026-08-27 對**spec-first 重構之前**的 `resolve_features` 抓的字面
#: 清單。這一張表就是「特徵字串名一個位元組不改」的可執行形式 —— 動到它
#: 等於改了名，而改名要走 `legacy_feature_renames` 那條路，不是改這張表。
EXPECTED = {
    "glv_bare": [
        "glv_median",
        "glv_pixels"
    ],
    "glv_multistream": [
        "diff_glv_max",
        "diff_glv_pixels",
        "test_glv_max",
        "test_glv_pixels"
    ],
    "glv_stream_own": [
        "diff_center_glv_max",
        "diff_center_glv_pixels",
        "test_center_glv_max",
        "test_center_glv_pixels"
    ],
    "glv_multiregion": [
        "epi_glv_median",
        "epi_glv_mad",
        "epi_glv_pixels",
        "mg_glv_median",
        "mg_glv_mad",
        "mg_glv_pixels"
    ],
    "glv_autofill": [
        "epi_glv_median",
        "epi_glv_pixels"
    ],
    "glv_center_ref": [
        "epi_center_glv_median",
        "epi_center_cmp_delta_median",
        "epi_center_glv_pixels",
        "epi_others_glv_median",
        "epi_others_cmp_delta_median",
        "epi_others_glv_pixels"
    ],
    "glv_eachbox": [
        "glv_median_typical",
        "glv_median_outlier",
        "glv_median_outlier_box",
        "cmp_delta_median_typical",
        "cmp_delta_median_outlier",
        "cmp_delta_median_outlier_box",
        "cmp_delta_q90_typical",
        "cmp_delta_q90_outlier",
        "cmp_delta_q90_outlier_box",
        "cmp_snr_median_typical",
        "cmp_snr_median_outlier",
        "cmp_snr_median_outlier_box",
        "cmp_snr_q90_typical",
        "cmp_snr_q90_outlier",
        "cmp_snr_q90_outlier_box",
        "cmp_overlap_typical",
        "cmp_overlap_outlier",
        "cmp_overlap_outlier_box",
        "cmp_spread_ratio_typical",
        "cmp_spread_ratio_outlier",
        "cmp_spread_ratio_outlier_box",
        "glv_boxes",
        "glv_worst_i",
        "glv_worst_x",
        "glv_worst_y",
        "glv_worst_w",
        "glv_worst_h",
        "glv_worst_score",
        "glv_worst_value",
        "glv_worst_score_median",
        "glv_worst_score_spread",
        "glv_pixels",
        "glv_ok"
    ],
    "cd_line": [
        "cd_n",
        "cd_lines",
        "cd_axis_deg",
        "cd_bright",
        "cd_edge_score",
        "cd_median",
        "cd_std",
        "cd_min",
        "cd_max",
        "cd_median_nm",
        "cd_std_nm",
        "cd_min_nm",
        "cd_max_nm"
    ],
    "cd_blob": [
        "cd_pieces",
        "cd_touches_edge",
        "cd_feret_angle",
        "cd_bright",
        "cd_edge_score",
        "cd_box_x",
        "cd_box_y",
        "cd_box_w",
        "cd_box_h",
        "cd_cx",
        "cd_cy",
        "cd_area_px",
        "cd_deq",
        "cd_feret_max",
        "cd_feret_min",
        "cd_area_nm2",
        "cd_deq_nm",
        "cd_feret_max_nm",
        "cd_feret_min_nm"
    ],
    "cd_blob_size": [
        "cd_pieces",
        "cd_touches_edge",
        "cd_feret_angle",
        "cd_bright",
        "cd_edge_score",
        "cd_box_x",
        "cd_box_y",
        "cd_box_w",
        "cd_box_h",
        "cd_cx",
        "cd_cy",
        "cd_area_px",
        "cd_roundness",
        "cd_area_nm2"
    ],
    "cd_target": [
        "cd_n",
        "cd_lines",
        "cd_axis_deg",
        "cd_bright",
        "cd_edge_score",
        "cd_median",
        "cd_dev",
        "cd_dev_frac",
        "cd_median_nm",
        "cd_dev_nm"
    ],
    "cd_no_target": [
        "cd_n",
        "cd_lines",
        "cd_axis_deg",
        "cd_bright",
        "cd_edge_score",
        "cd_median",
        "cd_median_nm"
    ],
    "cd_multi": [
        "a_top_x_cd_n",
        "a_top_x_cd_lines",
        "a_top_x_cd_axis_deg",
        "a_top_x_cd_bright",
        "a_top_x_cd_edge_score",
        "a_top_x_cd_median",
        "a_top_x_cd_std",
        "a_top_x_cd_min",
        "a_top_x_cd_max",
        "a_top_x_cd_median_nm",
        "a_top_x_cd_std_nm",
        "a_top_x_cd_min_nm",
        "a_top_x_cd_max_nm",
        "a_bot_x_cd_n",
        "a_bot_x_cd_lines",
        "a_bot_x_cd_axis_deg",
        "a_bot_x_cd_bright",
        "a_bot_x_cd_edge_score",
        "a_bot_x_cd_median",
        "a_bot_x_cd_std",
        "a_bot_x_cd_min",
        "a_bot_x_cd_max",
        "a_bot_x_cd_median_nm",
        "a_bot_x_cd_std_nm",
        "a_bot_x_cd_min_nm",
        "a_bot_x_cd_max_nm",
        "b_top_x_cd_n",
        "b_top_x_cd_lines",
        "b_top_x_cd_axis_deg",
        "b_top_x_cd_bright",
        "b_top_x_cd_edge_score",
        "b_top_x_cd_median",
        "b_top_x_cd_std",
        "b_top_x_cd_min",
        "b_top_x_cd_max",
        "b_top_x_cd_median_nm",
        "b_top_x_cd_std_nm",
        "b_top_x_cd_min_nm",
        "b_top_x_cd_max_nm",
        "b_bot_x_cd_n",
        "b_bot_x_cd_lines",
        "b_bot_x_cd_axis_deg",
        "b_bot_x_cd_bright",
        "b_bot_x_cd_edge_score",
        "b_bot_x_cd_median",
        "b_bot_x_cd_std",
        "b_bot_x_cd_min",
        "b_bot_x_cd_max",
        "b_bot_x_cd_median_nm",
        "b_bot_x_cd_std_nm",
        "b_bot_x_cd_min_nm",
        "b_bot_x_cd_max_nm"
    ],
    "focus_multi": [
        "test_q_focus_lapvar",
        "test_q_focus_tenengrad",
        "test_q_focus_fft",
        "ref_q_focus_lapvar",
        "ref_q_focus_tenengrad",
        "ref_q_focus_fft"
    ],
    "roi_profile": [
        "cross_count",
        "cross_pitch_x_px",
        "cross_pitch_y_px",
        "cross_filled",
        "cross_dist_px",
        "cross_pitch_ratio_x",
        "cross_pitch_ratio_y",
        "cross_edge_dropped",
        "locate_conf",
        "locate_ok",
        "cells_present",
        "cells_boxes",
        "cells_area_px",
        "cells_clipped",
        "cells_edge_dropped",
        "cells_center_present",
        "cells_center_boxes",
        "cells_center_area_px",
        "cells_center_clipped",
        "cells_center_edge_dropped",
        "cells_others_present",
        "cells_others_boxes",
        "cells_others_area_px",
        "cells_others_clipped",
        "cells_others_edge_dropped"
    ],
    "roi_profile_nopick": [
        "cross_count",
        "cross_pitch_x_px",
        "cross_pitch_y_px",
        "cross_filled",
        "cross_pitch_ratio_x",
        "cross_pitch_ratio_y",
        "cross_edge_dropped",
        "locate_conf",
        "locate_ok",
        "cells_present",
        "cells_boxes",
        "cells_area_px",
        "cells_clipped",
        "cells_edge_dropped"
    ],
    "roi_gds": [
        "layout_ok",
        "layout_layers",
        "epi_present",
        "epi_boxes",
        "epi_area_px",
        "epi_clipped",
        "epi_edge_dropped",
        "epi_center_present",
        "epi_center_boxes",
        "epi_center_area_px",
        "epi_center_clipped",
        "epi_center_edge_dropped",
        "epi_others_present",
        "epi_others_boxes",
        "epi_others_area_px",
        "epi_others_clipped",
        "epi_others_edge_dropped",
        "mg_present",
        "mg_boxes",
        "mg_area_px",
        "mg_clipped",
        "mg_edge_dropped",
        "mg_center_present",
        "mg_center_boxes",
        "mg_center_area_px",
        "mg_center_clipped",
        "mg_center_edge_dropped",
        "mg_others_present",
        "mg_others_boxes",
        "mg_others_area_px",
        "mg_others_clipped",
        "mg_others_edge_dropped",
        "epi_pieces",
        "mg_pieces"
    ],
    "enhance_two": [
        "test_clip_frac",
        "ref_clip_frac",
        "pair_level_delta",
        "pair_spread_ratio"
    ],
    "denoise_hot": [
        "clip_frac",
        "hot_px_frac"
    ],
    "load_carry": [
        "n_channels",
        "ROUGHBINNUMBER",
        "SCORE"
    ],
    "pair_rank": [
        "pair_found",
        "match_dist_nm",
        "match_ambiguous",
        "pair_SCORE",
        "pair_die_rank",
        "pair_die_total"
    ]
}


def _all_cases():
    for key in REGISTRY:
        yield "%s-default" % key, key, None
    for cid, (key, params) in CASES.items():
        yield cid, key, params


# --------------------------------------------------------------------------- #
# A 半：registry 全掃
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("cid", "key", "params"),
                         list(_all_cases()),
                         ids=[c[0] for c in _all_cases()])
def test_spec_names_are_byte_identical_to_resolve_features(cid, key, params):
    cls = REGISTRY[key]
    p = cls.validate_params(params)
    specs = cls.resolve_feature_specs(p)
    assert [s.name for s in specs] == list(cls.resolve_features(p)), \
        "%s：spec 的名字（含順序）跟 resolve_features 對不上" % cid
    assert all(s.card == key for s in specs)
    # `feature_parts` 有描述的名字，spec.parts() 要逐鍵相同（feature_html
    # 讀那份）。沒描述的卡（base 退化）spec 只多一個 base —— 少資訊不是錯。
    by_name = {s.name: s for s in specs}
    for name, want in cls.feature_parts(p).items():
        assert by_name[name].parts() == want, \
            "%s：%s 的 spec.parts() 跟 feature_parts 對不上" % (cid, name)


# --------------------------------------------------------------------------- #
# B 半：字面快照 —— spec-first 之後的真鐵
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cid", sorted(EXPECTED), ids=sorted(EXPECTED))
def test_the_names_are_the_names_from_before_the_refactor(cid):
    key, params = CASES[cid]
    cls = REGISTRY[key]
    assert list(cls.resolve_features(cls.validate_params(dict(params)))) \
        == EXPECTED[cid]


def test_the_snapshot_table_is_not_vacuous():
    assert len(EXPECTED) >= 18
    assert any(len(v) > 10 for v in EXPECTED.values())
    # 陷阱組真的在表上，而且長成陷阱的樣子。
    assert "epi_glv_median" in EXPECTED["glv_autofill"]
    assert "epi_center_glv_median" in EXPECTED["glv_center_ref"]


def test_output_cards_declare_nothing():
    for key in ("output_report", "output_klarf", "output_char"):
        assert REGISTRY[key].resolve_feature_specs(
            REGISTRY[key].validate_params(None)) == []


# --------------------------------------------------------------------------- #
# C 半：反空洞 —— 身分欄真的有人填
# --------------------------------------------------------------------------- #
def _specs(cid):
    key, params = CASES[cid]
    cls = REGISTRY[key]
    return {s.name: s for s in
            cls.resolve_feature_specs(cls.validate_params(dict(params)))}


def test_the_autofill_trap_is_reproduced_exactly():
    """`epi_glv_median` 的身分是 **own="epi"、region=""**（單區域時區域前綴
    是空的、Studio 把區域名填進 output_prefix）—— 拆字串猜的話這裡必錯。"""
    s = _specs("glv_autofill")["epi_glv_median"]
    assert s.own == "epi" and s.region == "" and s.region_index == -1
    assert s.metric == "glv_median" and s.family == "glv"


def test_center_wired_regions_carry_their_role():
    by = _specs("glv_center_ref")
    s = by["epi_center_glv_median"]
    assert s.region == "epi_center" and s.region_role == "center"
    assert by["epi_others_glv_median"].region_role == "others"
    # cmp 名帶 metric 與 stat —— `_split_cmp` 以前用最長比對猜的那兩格。
    cmp_names = [n for n in by if "cmp_delta" in n]
    assert cmp_names, "反空洞：這組真的有 cmp 名"
    c = by[cmp_names[0]]
    assert c.family == "cmp" and c.metric == "delta" and c.stat == "median"


def test_eachbox_suffixes_are_variants_with_the_metric_stripped_back():
    by = _specs("glv_eachbox")
    s = by["glv_median_outlier_box"]
    assert s.variant == "outlier_box" and s.metric == "glv_median"
    assert by["glv_median_typical"].variant == "typical"
    # worst 那一族是 metric，不是 variant（2026-08-27 使用者定調）。
    w = by["glv_worst_score"]
    assert w.metric == "glv_worst_score" and w.variant == ""
    # stat-free 的 cmp 名 stat 記空（each-box 下也帶盒後綴，variant 照記）。
    c = by["cmp_overlap_typical"]
    assert c.stat == "" and c.metric == "overlap" and c.variant == "typical"


def test_nm_twins_are_variants_that_inherit_the_metric():
    by = _specs("cd_target")
    s = by["cd_median_nm"]
    assert s.variant == "nm" and s.metric == "cd_median" and s.family == "cd"
    by_blob = _specs("cd_blob_size")
    assert by_blob["cd_area_nm2"].variant == "nm2"
    assert by_blob["cd_area_nm2"].metric == "cd_area_px"


def test_enhance_pair_features_have_no_stream_on_purpose():
    by = _specs("enhance_two")
    assert by["test_clip_frac"].stream == "test"
    assert by["pair_level_delta"].stream == "", \
        "它講的是「這兩條之間」，掛在流名下面會是錯的"
