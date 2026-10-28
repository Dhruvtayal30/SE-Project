from pathlib import Path

from conftest import analyze


def assert_course_graph(r):
    c = r["complexity"]
    assert c["value"] == c["edges"] - c["nodes"] + 2 * c["components"]
    assert c["value"] == c["predicate_value"]
    assert c["formulas_agree"]


def test_default_only_is_a_course_predicate():
    src = "int f(int x){ switch (x) { default: a(); } return 0; }"
    strict, course = analyze(src), analyze(src, convention="course")
    assert strict["complexity"]["value"] == 1
    assert course["complexity"]["value"] == 2
    assert_course_graph(course)
    tests = [n for n in course["graph"]["nodes"] if n["construct"] == "switch_default"]
    assert len(tests) == 1 and tests[0]["out_degree"] == 2


def test_case_and_default_are_separate_predicates():
    src = "int f(int x){ switch (x) { case 1: a(); break; default: b(); } return 0; }"
    strict, course = analyze(src), analyze(src, convention="course")
    assert strict["complexity"]["value"] == 2
    assert course["complexity"]["value"] == 3
    assert_course_graph(course)
    assert len([n for n in course["graph"]["nodes"] if n["construct"].startswith("switch_")]) == 2


def test_stacked_cases_and_default_keep_each_label_test():
    src = "int f(int x){ switch (x) { case 1: case 2: default: a(); } return 0; }"
    course = analyze(src, convention="course")
    assert course["complexity"]["predicate_breakdown"]["case"] == 2
    assert course["complexity"]["predicate_breakdown"]["default"] == 1
    assert len([n for n in course["graph"]["nodes"] if n["construct"].startswith("switch_")]) == 3
    assert_course_graph(course)


def test_default_is_tested_last_but_body_fallthrough_stays_in_source_order():
    src = "int f(int x){ switch (x) { case 1: a(); default: b(); case 2: c(); break; } return 0; }"
    course = analyze(src, convention="course")
    tests = {n["label"]: n for n in course["graph"]["nodes"] if n["construct"].startswith("switch_")}
    assert set(tests) == {"x == 1", "x == 2", "default"}
    edges = course["graph"]["edges"]
    by_id = {n["id"]: n["label"] for n in course["graph"]["nodes"]}
    assert any(e["source"] == tests["x == 1"]["id"] and e["label"] == "False" and by_id[e["target"]] == "x == 2" for e in edges)
    assert any(e["source"] == tests["x == 2"]["id"] and e["label"] == "False" and by_id[e["target"]] == "default" for e in edges)
    assert any(by_id[e["source"]] == "b();" and e["kind"] == "fallthrough" and by_id[e["target"]] == "c();" for e in edges)
    assert all(t["out_degree"] == 2 for t in tests.values())
    assert_course_graph(course)


def test_default_fallthrough_nested_switch_and_switch_in_loop():
    src = "int f(int x){ while (x) { switch(x) { case 1: switch(x) { default: a(); } default: b(); } x--; } return 0; }"
    strict, course = analyze(src), analyze(src, convention="course")
    assert course["complexity"]["value"] == strict["complexity"]["value"] + 2
    assert course["complexity"]["predicate_breakdown"]["default"] == 2
    assert_course_graph(course)
    edges = course["graph"]["edges"]
    labels = {n["id"]: n["label"] for n in course["graph"]["nodes"]}
    assert any(labels[e["source"]] == "a();" and e["kind"] == "fallthrough" and labels[e["target"]] == "b();" for e in edges)


def test_switch_without_default_keeps_the_existing_graph_shape():
    src = "int f(int x){ switch (x) { case 1: a(); break; case 2: b(); } return 0; }"
    strict, course = analyze(src), analyze(src, convention="course")
    assert strict["complexity"]["value"] == course["complexity"]["value"]
    assert strict["graph"] == course["graph"]
    assert_course_graph(course)


def test_requested_example_has_hand_derived_strict_and_course_values():
    src = (Path(__file__).resolve().parents[1] / "examples" / "17_course_default.c").read_text()
    # Hand derivation: for(1) + if/&&(2) + cases(3) + if(1) + while(1) + ternary(1) = 10;
    # course convention adds the default predicate = 11.
    strict, course = analyze(src, function="process"), analyze(src, function="process", convention="course")
    assert strict["complexity"]["value"] == 10
    assert course["complexity"]["value"] == 11
    assert_course_graph(strict)
    assert_course_graph(course)


def test_formula_disagreement_is_returned_as_an_explicit_warning():
    r = analyze("void f(void){ for (;;) { } }", convention="strict")
    assert not r["complexity"]["formulas_agree"]
    assert any(n["code"] == "FORMULA_MISMATCH" for n in r["complexity"]["applicability"])
    assert any(w["code"] == "FORMULA_MISMATCH" and w["severity"] == "warning" for w in r["warnings"])
