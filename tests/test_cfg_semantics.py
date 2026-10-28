"""Semantic checks: the *edges* (with labels) must be exactly what the C semantics demand.
Uses merge_blocks=False so every statement/condition is its own node."""

from conftest import analyze, edge_set, fine, labels, node_by_label

T, F = "True", "False"


def test_straight_line():
    r = fine("int f(void){ int a = 1; a++; return a; }")
    assert edge_set(r) == {("ENTRY", "", "int a = 1;"), ("int a = 1;", "", "a++;"), ("a++;", "", "return a;"),
                           ("return a;", "return", "EXIT")}


def test_if_without_else():
    r = fine("int f(int x){ if (x) x = 1; return x; }")
    assert edge_set(r) == {("ENTRY", "", "x"), ("x", T, "x = 1;"), ("x", F, "return x;"),
                           ("x = 1;", "", "return x;"), ("return x;", "return", "EXIT")}


def test_if_else_joins():
    r = fine("int f(int x){ if (x) a(); else b(); c(); return 0; }")
    assert {("x", T, "a();"), ("x", F, "b();"), ("a();", "", "c();"), ("b();", "", "c();")} <= edge_set(r)


def test_nested_if_else_if():
    r = fine("int f(int x){ if (x>1) return 1; else if (x>0) return 2; return 3; }")
    es = edge_set(r)
    assert ("x>1", T, "return 1;") in es and ("x>1", F, "x>0") in es
    assert ("x>0", T, "return 2;") in es and ("x>0", F, "return 3;") in es
    assert {t for s, l, t in es if l == "return"} == {"EXIT"}


def test_while_loop_edges():
    r = fine("int f(int n){ while (n > 0) n--; return n; }")
    es = edge_set(r)
    assert ("n > 0", T, "n--;") in es and ("n > 0", F, "return n;") in es and ("n--;", "", "n > 0") in es
    back = [e for e in r["graph"]["edges"] if e["back_edge"]]
    assert len(back) == 1 and labels(r)[back[0]["target"]] == "n > 0"


def test_do_while_runs_body_first():
    r = fine("int f(int n){ do { n--; } while (n > 0); return n; }")
    es = edge_set(r)
    assert ("ENTRY", "", "n--;") in es and ("n--;", "", "n > 0") in es
    assert ("n > 0", T, "n--;") in es and ("n > 0", F, "return n;") in es


def test_for_loop_init_cond_body_update():
    r = fine("int f(int n){ int s = 0; for (int i = 0; i < n; i++) s += i; return s; }")
    es = edge_set(r)
    assert ("int s = 0;", "", "int i = 0;") in es and ("int i = 0;", "", "i < n") in es
    assert ("i < n", T, "s += i;") in es and ("s += i;", "", "i++") in es and ("i++", "", "i < n") in es
    assert ("i < n", F, "return s;") in es


def test_for_continue_reaches_update_not_condition():
    r = fine("int f(int n){ for (int i = 0; i < n; i++) { if (i) continue; g(); } return 0; }")
    es = edge_set(r)
    assert ("i", "True · continue", "i++") in es
    assert ("i", "True · continue", "i < n") not in es


def test_while_continue_goes_to_condition():
    r = fine("int f(int n){ while (n) { if (n == 3) continue; n--; } return 0; }")
    assert ("n == 3", "True · continue", "n") in edge_set(r)


def test_break_leaves_innermost_loop_only():
    r = fine("int f(int n){ while (n) { while (n > 5) { if (n == 9) break; n--; } n--; } return 0; }")
    es = edge_set(r)
    assert ("n == 9", "True · break", "n--;") in es or any(l == "True · break" for _, l, _ in es)
    inner_break = [(s, l, t) for s, l, t in es if l == "True · break"]
    assert len(inner_break) == 1
    # the target is the statement after the inner loop (outer body's n--), not the function's return
    lab = labels(r)
    tgt = [e for e in r["graph"]["edges"] if e["label"] == "True · break"][0]["target"]
    assert lab[tgt] == "n--;" and r["graph"]["nodes"][int(tgt[1:])]["lines"][0] == 1


def test_do_while_continue_goes_to_condition():
    r = fine("int f(int n){ do { n--; if (n == 2) continue; g(); } while (n > 0); return n; }")
    assert ("n == 2", "True · continue", "n > 0") in edge_set(r)


def test_multiple_returns_share_one_exit():
    r = fine("int f(int x){ if (x) return 1; if (x > 5) return 2; return 3; }")
    exits = [e for e in r["graph"]["edges"] if e["target"] == r["graph"]["exit"]]
    assert len(exits) == 3 and all(e["label"] == "return" for e in exits)
    assert sum(1 for n in r["graph"]["nodes"] if n["kind"] == "exit") == 1


def test_fall_off_end_connects_to_exit():
    r = fine("void f(int x){ g(x); }")
    assert ("g(x);", "", "EXIT") in edge_set(r)


def test_switch_dispatch_fallthrough_and_break():
    r = fine("int f(int x){ switch (x) { case 1: a(); case 2: b(); break; default: c(); } return 0; }")
    es = edge_set(r)
    assert ("switch (x)", "case 1", "a();") in es and ("switch (x)", "case 2", "b();") in es
    assert ("switch (x)", "default", "c();") in es
    assert ("a();", "fall-through", "b();") in es          # case 1 falls into case 2
    assert ("b();", "break", "return 0;") in es and ("c();", "", "return 0;") in es
    assert ("a();", "", "return 0;") not in es and ("a();", "break", "return 0;") not in es


def test_switch_without_default_has_no_match_edge():
    r = fine("int f(int x){ switch (x) { case 1: a(); break; } return 0; }")
    assert ("switch (x)", "default (no match)", "return 0;") in edge_set(r)


def test_switch_stacked_labels_keep_separate_parallel_edges():
    r = fine("int f(int x){ switch (x) { case 1: case 2: a(); break; default: b(); } return 0; }")
    to_a = [e for e in r["graph"]["edges"] if labels(r)[e["target"]] == "a();" and e["kind"] == "case"]
    assert sorted(e["label"] for e in to_a) == ["case 1", "case 2"]
    assert len({e["id"] for e in to_a}) == 2


def test_switch_default_in_the_middle_with_fallthrough():
    r = fine("int f(int x){ switch (x) { case 1: a(); break; default: b(); case 2: c(); } return 0; }")
    es = edge_set(r)
    assert ("b();", "fall-through", "c();") in es and ("switch (x)", "default", "b();") in es
    assert ("switch (x)", "case 2", "c();") in es


def test_break_inside_switch_inside_loop_leaves_only_the_switch():
    r = fine("int f(int n){ while (n) { switch (n) { case 1: break; default: n--; } n--; } return 0; }")
    brk = [e for e in r["graph"]["edges"] if e["via"] == "break" or e["kind"] == "break"]
    assert len(brk) == 1
    # target is the statement after the switch inside the loop (the second n--), not the loop exit
    assert labels(r)[brk[0]["target"]] == "n--;" and r["graph"]["nodes"][int(brk[0]["target"][1:])]["lines"] == [1]


def test_short_circuit_and_order():
    r = fine("int f(int a,int b){ if (a && b) return 1; return 0; }")
    es = edge_set(r)
    assert ("a", T, "b") in es and ("a", F, "return 0;") in es
    assert ("b", T, "return 1;") in es and ("b", F, "return 0;") in es


def test_short_circuit_or_order():
    r = fine("int f(int a,int b){ if (a || b) return 1; return 0; }")
    es = edge_set(r)
    assert ("a", T, "return 1;") in es and ("a", F, "b") in es
    assert ("b", T, "return 1;") in es and ("b", F, "return 0;") in es


def test_precedence_and_binds_tighter_than_or():
    r = fine("int f(int a,int b,int c){ if (a || b && c) return 1; return 0; }")
    es = edge_set(r)
    assert ("a", F, "b") in es and ("b", T, "c") in es and ("b", F, "return 0;") in es
    assert ("c", T, "return 1;") in es and ("c", F, "return 0;") in es


def test_negation_swaps_branches_and_parentheses_are_ignored():
    r = fine("int f(int a,int b){ if (!(a && b)) return 1; return 0; }")
    es = edge_set(r)
    assert ("a", T, "b") in es and ("a", F, "return 1;") in es
    assert ("b", T, "return 0;") in es and ("b", F, "return 1;") in es


def test_simple_negation_stays_one_atomic_decision():
    r = fine("int f(int a){ if (!a) return 1; return 0; }")
    assert ("!a", T, "return 1;") in edge_set(r)


def test_logical_operators_in_loop_conditions():
    r = fine("int f(int i,int n){ while (i < n && i != 3) i++; return i; }")
    es = edge_set(r)
    assert ("i < n", T, "i != 3") in es and ("i != 3", T, "i++;") in es
    assert ("i < n", F, "return i;") in es and ("i != 3", F, "return i;") in es and ("i++;", "", "i < n") in es


def test_ternary_has_explicit_arms():
    r = fine("int f(int a,int b){ int m = a > b ? a : b; return m; }")
    es = edge_set(r)
    assert ("a > b", T, "a") in es and ("a > b", F, "b") in es
    assert ("a", "", "int m = a > b ? a : b;") in es and ("b", "", "int m = a > b ? a : b;") in es


def test_ternary_condition_with_short_circuit_and_nesting():
    r = analyze("int f(int a,int b,int c){ return a && b ? c ? 1 : 2 : 3; }")
    assert r["complexity"]["value"] == 4          # a, b, c => 3 decisions


def test_logical_value_expression_has_one_decision_per_operator():
    """`x = a && b;` has ONE extra path (b skipped when a is false): M = 2, not 3.
    Regression: expanding the right operand into its own True/False decision created parallel edges
    to the same node and over-counted M by one (found by the random-program cross-check)."""
    r = fine("int f(int a,int b){ int x = a && b; return x; }")
    assert r["complexity"]["value"] == 2 and r["statistics"]["decision_nodes"] == 1
    es = edge_set(r)
    assert ("a", "True", "b") in es and ("a", "False", "int x = a && b;") in es and ("b", "", "int x = a && b;") in es
    pairs = [(e["source"], e["target"]) for e in r["graph"]["edges"]]
    assert len(pairs) == len(set(pairs)), "no parallel edges expected here"


def test_logical_value_chain_counts_each_operator():
    assert analyze("int f(int a,int b,int c){ return a || b || c; }")["complexity"]["value"] == 3
    assert analyze("int f(int a,int b,int c){ return a || b && c; }")["complexity"]["value"] == 3


def test_operators_inside_sizeof_are_not_evaluated():
    r = analyze("int f(int a,int b){ return sizeof(a && b); }")
    assert r["complexity"]["value"] == 1


def test_goto_edge_and_label():
    r = fine("int f(int n){ again: n--; if (n) goto again; return n; }")
    es = edge_set(r)
    assert ("n", "True · goto", "again:") in es and ("again:", "", "n--;") in es


def test_noreturn_call_goes_to_exit():
    r = fine("int f(int n){ if (n) exit(1); return 0; }")
    assert ("exit(1);", "exit()", "EXIT") in edge_set(r)


def test_loop_back_edge_marked_only_on_loops():
    r = analyze("int f(int n){ if (n) n++; while (n) n--; return n; }")
    assert sum(e["back_edge"] for e in r["graph"]["edges"]) == 1
    assert r["statistics"]["loops"] == 1


def test_nested_loops_have_two_back_edges():
    r = analyze("int f(int n){ for (int i=0;i<n;i++) for (int j=0;j<n;j++) g(); return 0; }")
    assert r["statistics"]["loops"] == 2


def test_empty_while_body_is_a_self_loop():
    r = fine("int f(int x){ while (x); return 0; }")
    es = edge_set(r)
    assert ("x", T, "x") in es and ("x", F, "return 0;") in es


def test_empty_for_body_and_update():
    r = fine("int f(int n){ for (int i = 0; i < n; i++); return 0; }")
    assert ("i++", "", "i < n") in edge_set(r)


def test_infinite_for_has_no_exit_edge_from_loop():
    r = analyze("void f(void){ for (;;) { g(); } }")
    assert r["reachability"]["exit_reachable"] is False
    assert r["reachability"]["unreachable_nodes"] == [r["graph"]["exit"]]


def test_while_true_exits_only_through_break_or_return():
    r = analyze("int f(int n){ while (1) { if (n++ > 3) break; } return n; }")
    assert r["reachability"]["exit_reachable"] is True
    assert r["complexity"]["value"] == 2
    assert not any(e["label"] == "False" and e["source"] == "n1" for e in r["graph"]["edges"])


def test_return_inside_loop():
    r = analyze("int f(int n){ while (n) { if (n == 3) return 1; n--; } return 0; }")
    assert r["complexity"]["value"] == 3 and r["reachability"]["exit_reachable"]


def test_unreachable_code_is_kept_flagged_and_reported():
    r = analyze("int f(void){ return 1; int x = 2; x++; }")
    dead = [n for n in r["graph"]["nodes"] if not n["reachable"]]
    assert len(dead) == 1 and dead[0]["statements"][0]["text"].startswith("int x")
    assert any(w["code"] == "UNREACHABLE_CODE" and w["line"] == 1 for w in r["warnings"])
    assert all(not e["reachable"] for e in r["graph"]["edges"] if e["source"] == dead[0]["id"])


def test_code_after_break_and_continue_is_unreachable():
    r = analyze("int f(int n){ while (n) { break; n--; } return 0; }")
    assert any(w["code"] == "UNREACHABLE_CODE" for w in r["warnings"])


def test_declaration_without_initialiser_after_return_is_not_a_warning():
    r = analyze("int f(void){ return 1; int x; }")
    assert not any(w["code"] == "UNREACHABLE_CODE" for w in r["warnings"])


def test_unreachable_decision_does_not_change_reachable_m():
    r = analyze("int f(int a){ return 1; if (a) a++; }")
    assert r["complexity"]["value"] == 1
    assert r["complexity"]["full_graph"]["value"] != 1 or r["statistics"]["nodes_unreachable"] > 0
    assert r["complexity"]["structural"]["agrees"] is True


# ---- source mapping --------------------------------------------------------------------------
def test_node_lines_and_reverse_map():
    r = analyze("int f(int x){\n  int y = 0;\n  if (x > 0)\n    y = 1;\n  return y;\n}")
    cond = node_by_label(r, "x > 0")
    assert cond["lines"] == [3]
    assert "n" + str(cond["index"]) in r["source_map"]["line_to_nodes"]["3"]
    assert r["source_map"]["line_to_nodes"]["4"] == [node_by_label(r, "y = 1;")["id"]]


def test_merged_block_keeps_all_statement_lines():
    r = analyze("int f(void){\n  int a = 1;\n  int b = 2;\n  return a + b;\n}")
    blocks = [n for n in r["graph"]["nodes"] if n["kind"] == "block"]
    assert len(blocks) == 1 and blocks[0]["lines"] == [2, 3, 4]
    assert [s["line"] for s in blocks[0]["statements"]] == [2, 3, 4]


def test_for_update_maps_to_the_header_line():
    r = analyze("int f(int n){\n  for (int i = 0;\n       i < n;\n       i++)\n    g(i);\n  return 0;\n}")
    cond = node_by_label(r, "i < n")
    assert cond["lines"] == [3]
    body = [n for n in r["graph"]["nodes"] if "g(i);" in n["label"]][0]
    assert 5 in body["lines"] and 4 in body["lines"]          # body and the merged update expression
