import pytest

from conftest import analyze
from cfg_analyzer.errors import AnalysisError, FunctionNotFound, SyntaxFailure, UnsupportedConstruct


def test_valid_function_basic():
    r = analyze("int main(void){ return 0; }")
    assert r["function"]["name"] == "main" and r["function"]["start_line"] == 1


def test_comments_and_declarations_do_not_create_control_flow():
    r = analyze("""
    /* if (x) { while (1) {} } */   // for (;;) {}
    int f(void) {
        int a = 1;   // if (a) ;
        char *s = "while (a) { break; }";
        return a;
    }""")
    assert r["complexity"]["value"] == 1
    assert r["statistics"]["decision_nodes"] == 0


def test_keywords_in_strings_are_not_parsed_as_syntax():
    r = analyze('int f(void){ printf("if (x) else while for switch case"); return 0; }')
    assert r["complexity"]["value"] == 1


def test_multiple_functions_default_is_main():
    r = analyze("int a(void){return 1;}\nint main(void){ if (1) return 2; return 3; }\nint z(void){return 0;}")
    assert r["function"]["name"] == "main"
    assert [f["name"] for f in r["functions"]] == ["a", "main", "z"]
    assert [f["selected"] for f in r["functions"]] == [False, True, False]
    assert {f["name"]: f["complexity"] for f in r["functions"]} == {"a": 1, "main": 2, "z": 1}


def test_without_main_first_function_is_default():
    r = analyze("int b(void){return 1;}\nint c(int x){ if (x) return 1; return 0; }")
    assert r["function"]["name"] == "b"


def test_explicit_function_selection():
    r = analyze("int b(void){return 1;}\nint c(int x){ if (x) return 1; return 0; }", function="c")
    assert r["function"]["name"] == "c" and r["complexity"]["value"] == 2


def test_unknown_function_is_reported_with_choices():
    with pytest.raises(FunctionNotFound) as ei:
        analyze("int b(void){return 1;}", function="nope")
    assert ei.value.details["available"] == ["b"]


def test_pointer_returning_function_name():
    assert analyze("char *dup(char *s){ return s; }")["function"]["name"] == "dup"


@pytest.mark.parametrize("src,line,col", [
    ("int f(void){\n  int x = 1\n  return x;\n}", 2, 12),
    ("int f(void){ if (x { return 1; } }", 1, None),
    ("int f(void){ return 1;", None, None),
])
def test_syntax_errors_have_locations(src, line, col):
    with pytest.raises(SyntaxFailure) as ei:
        analyze(src)
    assert ei.value.locations, "must report at least one location"
    loc = ei.value.locations[0]
    assert loc["line"] >= 1 and loc["column"] >= 1
    if line:
        assert loc["line"] == line
    if col:
        assert loc["column"] == col


def test_syntax_error_in_other_function_is_a_warning_not_a_graph_for_it():
    src = "int ok(void){ return 1; }\nint bad(void){ int x = ; return x }\n"
    r = analyze(src, function="ok")
    assert any(w["code"] == "SYNTAX_ERROR_ELSEWHERE" for w in r["warnings"])
    assert [f["error"] is not None for f in r["functions"]] == [False, True]
    with pytest.raises(SyntaxFailure):
        analyze(src, function="bad")


def test_no_function():
    with pytest.raises(FunctionNotFound):
        analyze("int x = 3;")


def test_bare_statements_are_rejected_not_graphed():
    with pytest.raises(AnalysisError):
        analyze("x = 1; if (x) y = 2;")


@pytest.mark.parametrize("src,needle", [
    ("int f(void){\n#ifdef DEBUG\n log();\n#endif\n return 0; }", "conditional compilation"),
    ("int f(void){ int y = ({ int t = 1; t; }); return y; }", "statement expression"),
    ("int f(void){ int g(void){ return 1; } return g(); }", "nested function"),
])
def test_unsupported_constructs_are_blocking_and_located(src, needle):
    with pytest.raises(UnsupportedConstruct) as ei:
        analyze(src)
    assert needle in ei.value.message and ei.value.locations[0]["line"] >= 1


@pytest.mark.parametrize("src", [
    "int f(void){ break; }", "int f(void){ continue; }", "int f(void){ goto nowhere; }",
])
def test_semantically_invalid_jumps_are_rejected(src):
    with pytest.raises(UnsupportedConstruct):
        analyze(src)


def test_ignored_preprocessor_lines_are_reported():
    r = analyze("int f(void){\n#define X 1\n return X; }")
    assert any(w["code"] == "PREPROCESSOR_IGNORED" for w in r["warnings"])


def test_macro_with_control_flow_is_flagged():
    r = analyze("#define BAIL return -1\nint f(int x){ if (x) BAIL; return 0; }")
    assert any(w["code"] == "MACRO_CONTROL_FLOW" for w in r["warnings"])


def test_unicode_columns_are_character_based():
    r = analyze('int f(void){ char *s = "héllo"; if (s) return 1; return 0; }')
    cond = next(n for n in r["graph"]["nodes"] if n["kind"] == "decision")
    assert cond["statements"][0]["column"] == len('int f(void){ char *s = "héllo"; if (') + 1


def test_nested_case_labels_are_reported_not_mis_graphed():
    with pytest.raises(UnsupportedConstruct) as ei:
        analyze("int f(int n){ switch (n) { case 0: while (n) { case 1: n--; } } return n; }")
    assert "nested" in ei.value.message


@pytest.mark.parametrize("src,m,warning", [
    ("int f(void){ struct S { int a; } s; typedef int T; enum E { A, B } e; T t = 1; s.a = t; return s.a; }", 1, None),
    ("static inline int f(int x){ return x; }", 1, None),
    ("int f(int n){ while (true) { if (n) break; } return n; }", 2, "CONSTANT_LOOP"),
    ("int f(int n){ do { n++; if (n>3) break; } while (1); return n; }", 2, "CONSTANT_LOOP"),
    ("int f(int n){\n#pragma omp parallel\n return n; }", 1, "PREPROCESSOR_IGNORED"),
    ("int f(void){ if (setjmp(b)) return 1; return 0; }", 2, "NONLOCAL_JUMP"),
    ('int f(void){ __asm__ volatile("nop"); return 0; }', 1, "INLINE_ASM"),
    ("int f(int n){ int a[10]; for (int i=0;i<10;i++) a[i]=i; return a[n]; }", 2, None),
    ("int f(int n){ for (int i=0, j=n; i<j; i++, j--) ; return n; }", 2, None),
])
def test_documented_supported_constructs(src, m, warning):
    r = analyze(src)
    assert r["complexity"]["value"] == m
    codes = [w["code"] for w in r["warnings"]]
    assert (warning in codes) if warning else codes == []
