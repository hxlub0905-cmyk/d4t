# F123 期 2：數字線與結果線（2026-09-29）；F124 改規則（2026-09-30）。
"""Decision、Output 跟 Input 一樣是真的卡，線由使用者拉（F123 做法 B）。

F124 起（`docs/plans/F124-measured-flow.md`）釘住四件事：

1. **送去判定的埠只長在量測卡上**（`Step.measures`：GLV、CD、Focus index、H2H）。
2. **線講流到哪裡，不講准你用哪些數字** —— 判定問得到 Decision **上游**每一張卡
   的數字；問到沒流進來的卡是提醒（`decision-not-wired`，warning）＋接誰。
3. **Output 寫整張表**（`rows_for_output`）；上游有 Decision 才有類別。
4. **第 8 版遷移**：從不再送得出數字的卡拉出來的線拿掉、改接下游的量測卡；
   新檔案不碰。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import validate  # noqa: E402
from d4t.core.pipeline.data_lines import (  # noqa: E402
    DECISION_KEY, feeder, rows_for_output, wired_into,
)
from d4t.core.pipeline.recipe import (  # noqa: E402
    RECIPE_VERSION, Edge, Recipe, RecipeNode, ScoreSpec, is_data_edge,
    is_region_edge,
)
from d4t.core.pipeline.recipe_schema import upstream_of  # noqa: E402
from d4t.core.pipeline.step import (  # noqa: E402
    DATA_PORTS, NUMBERS, REGISTRY, RESULTS,
)
from d4t.core.steps.decision import DecisionStep  # noqa: E402

KIND = "ebi_patch"


def _recipe(edges, *, out="output_report", cd=True, decision=True,
            expr="glv_max"):
    """Input → GLV（＋一張 CD）→ Decision → 一張 Output。線由呼叫端給。"""
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "glv": RecipeNode("glv", "glv_stats",
                               {"source": "test", "metrics": "glv_max"})}
    if cd:
        nodes["cd"] = RecipeNode("cd", "cd_measure", {"source": "test"})
    if decision:
        nodes["dec"] = RecipeNode("dec", "decision", {})
    nodes["out"] = RecipeNode("out", out, {"folder": "/tmp/x"})
    return Recipe(recipe_id="lines", routes={KIND: list(nodes)}, nodes=nodes,
                  edges=list(edges),
                  score=ScoreSpec(expr=expr, threshold=1.0,
                                  bins={"below": 0, "above": 1}))


IMAGE = [Edge("load", "glv", "test", "source"),
         Edge("load", "cd", "test", "source")]
NUM = Edge("glv", "dec", NUMBERS, NUMBERS)
RES = Edge("dec", "out", RESULTS, RESULTS)


def _codes(r):
    return {(i.code, i.node_id) for i in validate(r, kind=KIND)}


# --------------------------------------------------------------------------- #
# 線是哪一種：看下游那顆埠
# --------------------------------------------------------------------------- #
def test_a_data_line_is_told_by_the_port_it_goes_into():
    r = _recipe(IMAGE + [NUM, RES])
    assert is_data_edge(NUM, r.nodes) and is_data_edge(RES, r.nodes)
    assert not is_data_edge(IMAGE[0], r.nodes)
    assert not is_region_edge(NUM, r.nodes)
    # 埠名不是任何一張卡的參數名 —— 不然一條資料線會被當成那一格的值。
    for cls in REGISTRY.values():
        assert not {p.name for p in cls.params} & set(DATA_PORTS), cls.key


def test_the_decision_key_is_the_cards_key():
    assert DECISION_KEY == DecisionStep.key


def test_upstream_follows_every_kind_of_line():
    r = _recipe(IMAGE + [NUM, RES])
    assert upstream_of("out", r.edges) == {"dec", "glv", "load"}
    assert wired_into(r, "dec") == ["glv"]


# --------------------------------------------------------------------------- #
# 1. 送去判定的埠只長在量測卡上
# --------------------------------------------------------------------------- #
def test_only_the_measuring_cards_send_numbers():
    sends = sorted(k for k, cls in REGISTRY.items()
                   if cls.data_output(cls.validate_params({})) == NUMBERS)
    assert sends == ["align_to", "cd_measure", "focus_quality", "glv_stats"]


def test_a_number_noted_down_on_the_way_reaches_the_first_measuring_card():
    """Normalize 記的 `clip_frac` 跟著圖流到 GLV：要它流進來，接 GLV 就好。"""
    r = _recipe(IMAGE + [NUM, RES])
    r.nodes["norm"] = RecipeNode("norm", "normalize", {"streams": "test"})
    r.routes[KIND].insert(1, "norm")
    r.edges[0] = Edge("load", "norm", "test", "streams")
    r.edges.insert(1, Edge("norm", "glv", "test", "source"))
    assert feeder(r, "norm") == "glv"
    assert feeder(r, "glv") == "glv"
    assert feeder(r, "dec") == "", "Decision 送的是結果，不是數字"


# --------------------------------------------------------------------------- #
# 2. 判定問得到流進來的每一個數字；問到沒流進來的只提醒
# --------------------------------------------------------------------------- #
def _not_wired(r):
    return [i for i in validate(r, kind=KIND) if i.code == "decision-not-wired"]


def test_asking_about_a_card_that_does_not_flow_in_is_a_reminder():
    r = _recipe(IMAGE + [RES])                      # GLV 沒接進 Decision
    got = _not_wired(r)
    assert got and got[0].level == "warning", "提醒，不擋（照常跑）"
    assert got[0].node_id == "dec"
    assert "glv_max" in got[0].names
    assert got[0].connect == ("glv",), "那顆「Connect」接的是 GLV"
    assert not _not_wired(_recipe(IMAGE + [NUM, RES]))


def test_the_card_that_is_wired_is_the_one_that_counts():
    """接了 CD 不算：問的是 GLV 的數字，而 GLV 不在 Decision 上游。"""
    r = _recipe(IMAGE + [Edge("cd", "dec", NUMBERS, NUMBERS), RES])
    assert [i.connect for i in _not_wired(r)] == [("glv",)]


def test_a_number_that_rides_along_the_lines_needs_no_line_of_its_own():
    """Input 記的 `n_channels` 在 GLV 上游 —— GLV 接進來，它就流進來了。"""
    r = _recipe(IMAGE + [NUM, RES], expr="n_channels")
    assert not _not_wired(r)


def test_nothing_is_an_error_because_of_what_the_decision_asks():
    r = _recipe(IMAGE + [RES], expr="cd_median + glv_max")
    assert not [i for i in validate(r, kind=KIND) if i.level == "error"]


# --------------------------------------------------------------------------- #
# Output 卡要有東西流進來；寫類別的要有 Decision
# --------------------------------------------------------------------------- #
def test_an_output_with_nothing_flowing_in_is_an_error():
    assert ("output-not-connected", "out") in _codes(_recipe(IMAGE + [NUM]))
    assert ("output-not-connected", "out") not in _codes(
        _recipe(IMAGE + [NUM, RES]))


def test_a_recipe_with_nothing_that_measures_does_not_ask_for_a_line():
    """只有影像卡的 recipe（整理圖片）沒有任何東西接得進 Output —— 講「沒接」
    是一條修不好的紅字。"""
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "tone": RecipeNode("tone", "tone", {"streams": "test"}),
             "out": RecipeNode("out", "output_report", {"folder": "/tmp/x"})}
    r = Recipe(recipe_id="pics", routes={KIND: list(nodes)}, nodes=nodes,
               edges=[Edge("load", "tone", "test", "streams")],
               score=ScoreSpec(expr="", threshold=0.0, bins={}))
    assert ("output-not-connected", "out") not in _codes(r)


def test_write_klarf_needs_the_decision_upstream():
    direct = _recipe(IMAGE + [NUM, Edge("glv", "out", NUMBERS, RESULTS)],
                     out="output_klarf")
    got = [i for i in validate(direct, kind=KIND) if i.code == "needs-decision"]
    assert got and got[0].level == "error" and got[0].connect == ("dec",)
    wired = _recipe(IMAGE + [NUM, RES], out="output_klarf")
    assert ("needs-decision", "out") not in _codes(wired)


def test_a_line_into_the_wrong_port_is_caught():
    # Decision 不收 results。
    bad = _recipe(IMAGE + [NUM, RES, Edge("dec", "dec2", RESULTS, NUMBERS)])
    bad.nodes["dec2"] = RecipeNode("dec2", "decision", {})
    bad.routes[KIND].append("dec2")
    assert ("data-port-mismatch", "dec2") in _codes(bad)
    # numbers 拉進一張影像卡的影像埠
    stray = _recipe(IMAGE + [NUM, RES, Edge("glv", "cd", NUMBERS, "source")])
    assert ("data-port-mismatch", "cd") in _codes(stray)
    # 一張不量東西的卡沒有那顆埠（F124）
    loose = _recipe(IMAGE + [NUM, RES, Edge("load", "dec", NUMBERS, NUMBERS)])
    assert ("data-port-mismatch", "dec") in _codes(loose)


def test_a_decision_without_its_card_says_so_when_there_is_an_output():
    r = _recipe(IMAGE + [Edge("glv", "out", NUMBERS, RESULTS)], decision=False)
    assert ("decide-without-card", None) in _codes(r)


# --------------------------------------------------------------------------- #
# 3. Output 寫整張表
# --------------------------------------------------------------------------- #
ROWS = [{"defect_id": "1", "ok": True, "error": "", "score": 3.0, "bin": 1,
         "features": {"glv_max": 3.0, "cd_median": 7.0, "n_channels": 2.0,
                      "decide_unanswered": 0.0, "mystery": 1.0}}]


def test_from_the_decision_the_output_sees_the_classes():
    r = _recipe(IMAGE + [NUM, RES], cd=False)
    rows, decided = rows_for_output(r, "out", ROWS, [KIND])
    assert decided
    assert rows[0]["bin"] == 1 and rows[0]["score"] == 3.0
    assert "glv_max" in rows[0]["features"]


def test_from_a_measuring_card_there_is_no_class_but_every_number():
    r = _recipe(IMAGE + [NUM, Edge("glv", "out", NUMBERS, RESULTS)])
    rows, decided = rows_for_output(r, "out", ROWS, [KIND])
    assert not decided
    assert rows[0]["bin"] is None and rows[0]["score"] is None
    f = rows[0]["features"]
    assert "glv_max" in f and "n_channels" in f
    assert "cd_median" in f, "整張表：CD 沒接進來也寫（F124）"
    assert "decide_unanswered" not in f, "判定寫的數字：上游沒有 Decision"
    assert f["mystery"] == 1.0, "認不出是誰的留著"
    assert ROWS[0]["bin"] == 1, "不准改到整批那一份"


def test_the_whole_table_goes_out_even_when_one_measuring_card_is_wired():
    """F123 的排除式判準：一張量測卡接進來，它上游以外的數字全被排掉 ——
    F124 起其他卡沒有送出去的埠，那個判準會讓報表安靜地少欄。"""
    r = _recipe(IMAGE + [NUM, RES])
    rows, _decided = rows_for_output(r, "out", ROWS, [KIND])
    assert rows[0]["features"] == ROWS[0]["features"]


# --------------------------------------------------------------------------- #
# 4. 第 8 版遷移
# --------------------------------------------------------------------------- #
def _old(path, version=6):
    raw = json.loads((REPO / path).read_text(encoding="utf-8"))
    raw["version"] = version
    raw["edges"] = [e for e in raw.get("edges", [])
                    if e[1] not in DATA_PORTS]
    return raw


def test_an_old_file_gets_its_lines():
    r = Recipe.from_json_dict(_old("recipes/ebi-die-to-die.json"))
    data = [e.to_json() for e in r.edges if is_data_edge(e, r.nodes)]
    assert sorted(data) == sorted([["glv", NUMBERS, "decision", NUMBERS],
                                   ["decision", RESULTS, "report", RESULTS]])
    assert not [i for i in validate(r, kind=KIND) if i.level == "error"]


def test_an_old_file_does_not_get_a_line_for_every_card_that_writes_a_number():
    """F123 的第 7 版遷移給每一張「以前寫得出去」的卡補一條直接接報表的線；
    F124 起報表寫整張表，那幾條不需要。"""
    raw = _old("recipes/ebi-die-to-die.json")
    raw["nodes"]["cd"] = {"step": "cd_measure", "params": {"source": "test"}}
    raw["routes"]["ebi_patch"].insert(-2, "cd")
    raw["edges"].append(["load", "test", "cd", "source"])
    r = Recipe.from_json_dict(raw)
    assert Edge("cd", "report", NUMBERS, RESULTS) not in r.edges
    rows, _ = rows_for_output(r, "report", ROWS, [KIND])
    assert "cd_median" in rows[0]["features"], "報表照樣寫 CD 的數字"


def test_a_version_7_line_from_a_card_that_does_not_measure_moves_to_glv():
    """第 7 版的檔案：判定問 `n_channels`，所以那時候從 Input 拉了一條數字線
    （而且是唯一一條）。第 8 版拿掉它、改接 Input 下游第一張量測卡。"""
    raw = _old("recipes/ebi-die-to-die.json", version=7)
    raw["edges"] += [["load", NUMBERS, "decision", NUMBERS],
                     ["decision", RESULTS, "report", RESULTS]]
    raw["decide"]["let"][0]["expr"] = "n_channels"
    r = Recipe.from_json_dict(raw)
    data = sorted(e.to_json() for e in r.edges if is_data_edge(e, r.nodes))
    assert data == sorted([["glv", NUMBERS, "decision", NUMBERS],
                           ["decision", RESULTS, "report", RESULTS]])
    assert not _not_wired(r)
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.to_json_dict() == r.to_json_dict(), "鐵則 9：identity"


def test_the_migration_says_what_it_took_off():
    from d4t.core.pipeline.recipe_migrations import describe_migration
    raw = _old("recipes/ebi-die-to-die.json", version=7)
    raw["edges"] += [["glv", NUMBERS, "decision", NUMBERS],
                     ["norm", NUMBERS, "decision", NUMBERS],
                     ["decision", RESULTS, "report", RESULTS]]
    says = describe_migration(raw, Recipe.from_json_dict(raw))
    assert "took off 1 wire from cards that do not measure" in says, says


def test_a_current_file_is_left_alone():
    """鐵則 9：第 8 版起線是使用者拉的 —— 一份刻意沒接的新 recipe 不准被補。"""
    raw = json.loads((REPO / "recipes/ebi-die-to-die.json").read_text(
        encoding="utf-8"))
    assert raw["version"] == RECIPE_VERSION
    raw["edges"] = [e for e in raw["edges"] if e[1] not in DATA_PORTS]
    r = Recipe.from_json_dict(raw)
    assert not [e for e in r.edges if is_data_edge(e, r.nodes)]
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.to_json_dict() == r.to_json_dict()
