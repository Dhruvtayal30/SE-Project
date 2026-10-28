"""Basis paths are audited with an independent rank computation and a path-validity check."""

import pytest

from conftest import analyze, rank_of

PROGRAMS = {
    "straight": "int f(void){ return 0; }",
    "if_else": "int f(int x){ int m; if (x) m = 1; else m = 2; return m; }",
    "loop": "int f(int n){ int s=0; while (n>0) { s+=n; n--; } return s; }",
    "nested_loops": "int f(int a){ for(int i=0;i<a;i++) for(int j=0;j<i;j++){ if(j==2) continue; if(i==5) break; } return a; }",
    "switch": "int f(int x){ switch(x){ case 1: a(); case 2: b(); break; case 3: case 4: c(); break; default: d(); } return 0; }",
    "shortcircuit": "int f(int a,int b,int c){ if (a || b && c) return 1; return 0; }",
    "dowhile": "int f(int n){ do { n--; if (n==3) break; } while (n>0); return n; }",
    "goto": "int f(int n){ again: n--; if (n>0) goto again; return n; }",
    "early_return": "int f(int n){ while (n) { if (n==3) return 1; n--; } return 0; }",
}


def audit(r):
    """Check every basis-path invariant against the graph in the response."""
    p = r["paths"]
    assert p["status"] == "complete"
    g = r["graph"]
    edges = {e["id"]: e for e in g["edges"] if e["reachable"]}
    order = list(edges)
    assert len(p["paths"]) == p["rank"] == p["expected"] == r["complexity"]["value"]
    vectors = []
    for path in p["paths"]:
        assert path["nodes"][0] == g["entry"] and path["nodes"][-1] == g["exit"]
        cur = g["entry"]
        for eid, nxt in zip(path["edges"], path["nodes"][1:]):
            assert edges[eid]["source"] == cur and edges[eid]["target"] == nxt, "path must follow real edges"
            cur = nxt
        vec = [0] * len(order)
        for eid in path["edges"]:
            vec[order.index(eid)] += 1
        vectors.append(vec)
    assert rank_of(vectors) == len(vectors), "basis paths must be linearly independent"
    return vectors


@pytest.mark.parametrize("name", PROGRAMS)
def test_basis_paths_are_valid_and_independent(name):
    audit(analyze(PROGRAMS[name]))


def test_count_equals_complexity_on_all_examples():
    import glob
    for f in glob.glob(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "examples" / "*.c")):
        r = analyze(open(f).read())
        if r["paths"]["status"] == "complete":
            audit(r)


def test_basis_spans_every_edge():
    r = analyze(PROGRAMS["nested_loops"])
    used = {e for p in r["paths"]["paths"] for e in p["edges"]}
    assert used == {e["id"] for e in r["graph"]["edges"] if e["reachable"]}


def test_loop_paths_are_flagged_as_repeating_nodes():
    r = analyze(PROGRAMS["loop"])
    assert any(p["repeats_nodes"] for p in r["paths"]["paths"])


def test_decisions_listed_with_branch_labels():
    r = analyze(PROGRAMS["if_else"])
    seen = {d["label"] for p in r["paths"]["paths"] for d in p["decisions"]}
    assert seen == {"True", "False"}


def test_unreachable_code_is_not_in_any_path():
    r = analyze("int f(int a){ return 1; if (a) a++; return 2; }")
    dead = {n["id"] for n in r["graph"]["nodes"] if not n["reachable"]}
    assert dead and all(not (set(p["nodes"]) & dead) for p in r["paths"]["paths"])
    assert r["paths"]["status"] == "complete" and len(r["paths"]["paths"]) == 1


@pytest.mark.parametrize("src", ["void f(void){ for(;;){} }", "int f(int x){ if (x) { for(;;){} } return 0; }"])
def test_no_terminating_basis_is_invented(src):
    p = analyze(src)["paths"]
    assert p["status"] == "unavailable" and p["paths"] == [] and p["reason"]


def test_basis_can_be_disabled():
    assert analyze(PROGRAMS["loop"], basis_paths=False)["paths"]["status"] == "disabled"


def test_huge_complexity_skips_basis_but_keeps_metrics():
    src = "int f(int x){ int y=0; " + "if (x>0) y++; " * 130 + "return y; }"
    r = analyze(src)
    assert r["paths"]["status"] == "skipped" and r["complexity"]["value"] == 131
