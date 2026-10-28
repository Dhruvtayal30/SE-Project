import itertools
import pytest

from conftest import analyze, fine


@pytest.mark.parametrize("src,n,e,m", [
    ("int f(void){ return 0; }", 3, 2, 1),
    ("int f(int x){ if (x) x++; return x; }", 5, 5, 2),
    ("int f(int x){ while (x) x--; return x; }", 5, 5, 2),                  # ENTRY, cond, body, ret, EXIT
    ("int f(int x){ do x--; while (x); return x; }", 5, 5, 2),
    ("int f(int x){ for (int i=0;i<x;i++) g(); return 0; }", 7, 7, 2),
])
def test_known_graphs_without_merging(src, n, e, m):
    r = fine(src)
    assert (r["statistics"]["nodes_total"], r["statistics"]["edges_total"], r["complexity"]["value"]) == (n, e, m)


def test_formula_substitution_is_reported():
    c = analyze("int f(int x){ if (x) return 1; return 0; }")["complexity"]
    assert c["substituted"] == "M = 5 − 5 + 2×1 = 2"
    assert c["value"] == c["edges"] - c["nodes"] + 2 * c["components"]
    assert c["branch_value"] == c["value"] and c["formulas_agree"]


def test_complexity_counts_each_case_label_and_not_default():
    c = analyze("int f(int x){ switch (x) { case 1: case 2: case 3: a(); break; default: b(); } return 0; }")["complexity"]
    assert c["value"] == 4
    c = analyze("int f(int x){ switch (x) { default: b(); } return 0; }")["complexity"]
    assert c["value"] == 1


def test_switch_without_default_contributes_same_as_with_default():
    a = analyze("int f(int x){ switch (x) { case 1: a(); break; case 2: b(); break; } return 0; }")["complexity"]["value"]
    b = analyze("int f(int x){ switch (x) { case 1: a(); break; case 2: b(); break; default: c(); } return 0; }")["complexity"]["value"]
    assert a == b == 3


def test_decision_node_count_differs_from_complexity_for_switch():
    r = analyze("int f(int x){ switch (x) { case 1: a(); break; case 2: b(); break; case 3: c(); break; } return 0; }")
    assert r["statistics"]["decision_nodes"] == 1 and r["complexity"]["value"] == 4
    assert r["complexity"]["branch_contribution"] == 3


def test_parallel_edges_are_counted_separately():
    # both edges of `x` go to the same node: `if (x) ;`
    r = analyze("int f(int x){ if (x) ; return x; }")
    es = [e for e in r["graph"]["edges"] if e["source"] == "n1"]
    assert {e["label"] for e in es} == {"True", "False"} and len({e["target"] for e in es}) == 1
    assert r["complexity"]["value"] == 2


def test_self_loop_counts_as_an_edge():
    r = analyze("int f(int x){ while (x); return 0; }")
    assert r["complexity"]["value"] == 2


def test_basic_block_merging_does_not_change_complexity():
    src = "int f(int n){ int s=0; for(int i=0;i<n;i++){ if(i%2) continue; s+=i; s*=2; } while(s>10) s-=3; return s; }"
    a, b = analyze(src), fine(src)
    assert a["complexity"]["value"] == b["complexity"]["value"]
    assert a["statistics"]["nodes_total"] < b["statistics"]["nodes_total"]


def test_node_count_is_graph_nodes_not_source_lines():
    r = analyze("int f(void){\n int a;\n int b;\n int c;\n int d;\n return 0;\n}")
    assert r["statistics"]["function_lines"] == 7 and r["statistics"]["nodes_total"] == 3


def test_unreachable_nodes_are_excluded_from_m_but_reported():
    r = analyze("int f(int a){ return 1; if (a) a++; return 2; }")
    c = r["complexity"]
    assert c["value"] == 1 and c["nodes"] < r["statistics"]["nodes_total"]
    assert any(n["code"] == "UNREACHABLE_EXCLUDED" for n in c["applicability"])
    assert c["full_graph"]["nodes"] == r["statistics"]["nodes_total"]
    assert c["structural"]["agrees"]            # structural count includes the dead `if`


def test_nonterminating_function_formulas_disagree_and_are_flagged():
    r = analyze("void f(void){ for (;;) { } }")
    c = r["complexity"]
    assert (c["value"], c["branch_value"]) == (2, 1) and not c["formulas_agree"]
    assert any(n["code"] == "EXIT_UNREACHABLE" for n in c["applicability"])


def test_trapped_loop_inside_branch_keeps_formulas_in_agreement():
    r = analyze("int f(int x){ if (x) { for (;;) { } } return 0; }")
    c = r["complexity"]
    assert c["formulas_agree"] and c["value"] == 2
    assert any(n["code"] == "TRAPPED_NODES" for n in c["applicability"])
    assert r["paths"]["status"] == "unavailable"


def test_structural_cross_check_breakdown():
    c = analyze("int f(int a,int b){ if (a && b) return 1; for (int i=0;i<a;i++) { if (b ? 1 : 0) a--; } "
                "switch (a) { case 1: break; default: break; } return 0; }")["complexity"]["structural"]
    assert c["breakdown"] == {"if": 2, "for": 1, "while": 0, "do_while": 0,
                               "logical": 1, "ternary": 1, "case": 1, "default": 0}
    assert c["agrees"] and c["value"] == 7


def test_interpretation_bands():
    low = analyze("int f(void){ return 0; }")["complexity"]["interpretation"]["band"]
    body = "".join(f"if (x=={i}) y++; " for i in range(12))
    mod = analyze("int f(int x){ int y=0; " + body + "return y; }")["complexity"]
    assert low == "low" and mod["value"] == 13 and mod["interpretation"]["band"] == "moderate"


@pytest.mark.parametrize("n", [1, 5, 40])
def test_many_sequential_ifs_scale_linearly(n):
    r = analyze("int f(int x){ int y=0; " + "if (x>0) y++; " * n + "return y; }")
    assert r["complexity"]["value"] == n + 1 and r["complexity"]["formulas_agree"]
