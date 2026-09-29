# F123 期 2：數字線與結果線（2026-09-29）。
"""使用者選了做法 B：Decision、Output 跟 Input 一樣是真的卡，線由使用者拉。

釘住三件事：

1. **數字線必要**（`decision-not-wired`）—— 判定問到的數字，產出它的卡要有線
   接進 Decision；Studio 與 CLI 在 error 時都不跑，所以它真的是必要的。
2. **Output 寫的是線上游的東西**（`rows_for_output`）—— 接 Decision 有類別，
   直接接量測卡只有那張卡（與它上游）的數字。判準是排除：認不出是誰的留著。
3. **第 7 版遷移**：舊檔案補線，判定與寫出去的東西逐項不變；新檔案不碰。
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
    DECISION_KEY, rows_for_output, wired_into,
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
# 1. 數字線必要
# --------------------------------------------------------------------------- #
def test_a_decision_asking_about_an_unwired_card_is_an_error():
    r = _recipe(IMAGE + [RES])                      # GLV 沒接進 Decision
    issues = [i for i in validate(r, kind=KIND)
              if i.code == "decision-not-wired"]
    assert issues and issues[0].level == "error"
    assert issues[0].node_id == "dec"
    assert "glv_max" in issues[0].names
    assert ("decision-not-wired", "dec") not in _codes(_recipe(IMAGE + [NUM, RES]))


def test_the_card_that_is_wired_is_the_one_that_counts():
    """接了 CD 不算：問的是 GLV 的數字。"""
    r = _recipe(IMAGE + [Edge("cd", "dec", NUMBERS, NUMBERS), RES])
    assert ("decision-not-wired", "dec") in _codes(r)


# --------------------------------------------------------------------------- #
# Output 要有東西接進來；寫類別的要有 Decision
# --------------------------------------------------------------------------- #
def test_an_output_with_nothing_wired_in_has_nothing_to_write():
    assert ("output-not-connected", "out") in _codes(_recipe(IMAGE + [NUM]))
    assert ("output-not-connected", "out") not in _codes(
        _recipe(IMAGE + [NUM, RES]))


def test_write_klarf_needs_the_decision_upstream():
    direct = _recipe(IMAGE + [NUM, Edge("glv", "out", NUMBERS, RESULTS)],
                     out="output_klarf")
    assert ("needs-decision", "out") in _codes(direct)
    wired = _recipe(IMAGE + [NUM, RES], out="output_klarf")
    assert ("needs-decision", "out") not in _codes(wired)


def test_a_line_into_the_wrong_port_is_caught():
    # 影像卡沒有 numbers 出埠以外的資料出埠；Decision 不收 results。
    bad = _recipe(IMAGE + [NUM, RES, Edge("dec", "dec2", RESULTS, NUMBERS)])
    bad.nodes["dec2"] = RecipeNode("dec2", "decision", {})
    bad.routes[KIND].append("dec2")
    assert ("data-port-mismatch", "dec2") in _codes(bad)
    # numbers 拉進一張影像卡的影像埠
    stray = _recipe(IMAGE + [NUM, RES, Edge("glv", "cd", NUMBERS, "source")])
    assert ("data-port-mismatch", "cd") in _codes(stray)


def test_a_decision_without_its_card_says_so_when_there_is_an_output():
    r = _recipe(IMAGE + [Edge("glv", "out", NUMBERS, RESULTS)], decision=False)
    assert ("decide-without-card", None) in _codes(r)


# --------------------------------------------------------------------------- #
# 2. Output 寫的是線上游的東西
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


def test_from_a_measuring_card_there_is_no_class():
    r = _recipe(IMAGE + [NUM, Edge("glv", "out", NUMBERS, RESULTS)])
    rows, decided = rows_for_output(r, "out", ROWS, [KIND])
    assert not decided
    assert rows[0]["bin"] is None and rows[0]["score"] is None
    f = rows[0]["features"]
    assert "glv_max" in f and "n_channels" in f       # GLV 與它的上游
    assert "cd_median" not in f, "CD 不在上游"
    assert "decide_unanswered" not in f, "判定寫的數字：上游沒有 Decision"
    assert f["mystery"] == 1.0, "認不出是誰的留著（排除，不是列舉）"
    assert ROWS[0]["bin"] == 1, "不准改到整批那一份"


# --------------------------------------------------------------------------- #
# 3. 第 7 版遷移
# --------------------------------------------------------------------------- #
def _v6(path):
    raw = json.loads((REPO / path).read_text(encoding="utf-8"))
    raw["version"] = 6
    raw["edges"] = [e for e in raw.get("edges", [])
                    if e[1] not in DATA_PORTS]
    return raw


def test_an_old_file_gets_its_lines_and_writes_the_same_things():
    raw = _v6("recipes/ebi-die-to-die.json")
    r = Recipe.from_json_dict(raw)
    data = [e.to_json() for e in r.edges if is_data_edge(e, r.nodes)]
    assert ["glv", NUMBERS, "decision", NUMBERS] in data
    assert ["decision", RESULTS, "report", RESULTS] in data
    assert not [i for i in validate(r, kind=KIND) if i.level == "error"]


def test_a_card_the_decision_does_not_ask_about_still_reaches_the_report():
    """以前報表寫整張數字表。CD 不在判定裡也不在上游 → 補一條直接的線。"""
    raw = _v6("recipes/ebi-die-to-die.json")
    raw["nodes"]["cd"] = {"step": "cd_measure", "params": {"source": "test"}}
    raw["routes"]["ebi_patch"].insert(-2, "cd")
    raw["edges"].append(["load", "test", "cd", "source"])
    r = Recipe.from_json_dict(raw)
    assert Edge("cd", "report", NUMBERS, RESULTS) in r.edges


def test_a_current_file_is_left_alone():
    """鐵則 9：第 7 版起線是使用者拉的 —— 一份刻意沒接的新 recipe 不准被補。"""
    raw = json.loads((REPO / "recipes/ebi-die-to-die.json").read_text(
        encoding="utf-8"))
    assert raw["version"] == RECIPE_VERSION
    raw["edges"] = [e for e in raw["edges"] if e[1] not in DATA_PORTS]
    r = Recipe.from_json_dict(raw)
    assert not [e for e in r.edges if is_data_edge(e, r.nodes)]
    again = Recipe.from_json_dict(r.to_json_dict())
    assert again.to_json_dict() == r.to_json_dict()
