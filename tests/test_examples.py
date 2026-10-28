import json
from pathlib import Path

import pytest

from conftest import analyze

EX = Path(__file__).resolve().parents[1] / "examples"
MANIFEST = json.loads((EX / "manifest.json").read_text())


@pytest.mark.parametrize("item", MANIFEST, ids=[m["id"] for m in MANIFEST])
def test_example_matches_hand_derived_expectation(item):
    source = (EX / item["file"]).read_text()
    x = item["expected"]
    strict = analyze(source, function=item["function"], convention="strict")
    course = analyze(source, function=item["function"], convention="course")
    s, c = strict["statistics"], strict["complexity"]
    assert s["nodes_total"] == x["nodes"]
    assert s["edges_total"] == x["edges"]
    assert s["nodes_reachable"] == x["reachable_nodes"]
    assert c["value"] == x["complexity"]
    assert course["complexity"]["value"] == x.get("course_complexity", x["complexity"])
    assert s["decision_nodes"] == x["decision_nodes"]
    assert strict["reachability"]["exit_reachable"] == x["exit_reachable"]
    assert strict["paths"]["status"] == x["basis_status"]
    assert c["structural"]["agrees"]
    if c["formulas_agree"]:
        assert c["value"] == c["predicate_value"]
    if course["complexity"]["formulas_agree"]:
        assert course["complexity"]["value"] == course["complexity"]["predicate_value"]


def test_every_example_file_is_in_the_manifest():
    assert {m["file"] for m in MANIFEST} == {p.name for p in EX.glob("*.c")}


def test_analysis_is_deterministic():
    src = (EX / "15_switch_and_conditions.c").read_text()
    assert analyze(src) == analyze(src)
