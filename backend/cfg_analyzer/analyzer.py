"""The analysis pipeline: source text -> JSON-serialisable result. No HTTP code in here."""

from __future__ import annotations

from typing import Any

from . import basic_blocks, basis_paths, complexity, parser, reachability, structural, validation
from .cfg_builder import build_cfg
from .errors import AnalysisError, FunctionNotFound, LimitExceeded, SyntaxFailure
from .model import BLOCK, CFG, DECISION, ENTRY, EXIT, SWITCH, Diagnostic
from .parser import FunctionDef, SourceText
from .serialize import serialize
from .validation import MAX_NODES, AnalysisRequest


def _build(fn: FunctionDef, src: SourceText, merge: bool, convention: str) -> CFG:
    try:
        cfg = build_cfg(fn, src, convention)
    except RecursionError:
        raise LimitExceeded(f"Function '{fn.name}' is nested too deeply to analyse.", code="TOO_DEEP") from None
    if merge:
        basic_blocks.compact(cfg)
    if len(cfg.nodes) > MAX_NODES:
        raise LimitExceeded(f"Function '{fn.name}' produces {len(cfg.nodes)} graph nodes; the limit is {MAX_NODES}.",
                            code="GRAPH_TOO_LARGE")
    basic_blocks.renumber(cfg)
    return cfg


def _summary(fn: FunctionDef, src: SourceText, macros: dict, merge: bool, convention: str) -> dict[str, Any]:
    """Cheap per-function entry for the function list."""
    item: dict[str, Any] = {"name": fn.name, "start_line": fn.start_line, "end_line": fn.end_line,
                            "complexity": None, "error": None}
    if fn.has_error:
        item["error"] = "syntax error"
        return item
    try:
        validation.scan_function(fn, src, macros)
        cfg = _build(fn, src, merge, convention)
        reach = reachability.analyze(cfg)
        item["complexity"] = complexity.compute(
            cfg, reach, structural.count_decisions(fn.body, src, convention), convention)["value"]
    except AnalysisError as exc:
        item["error"] = exc.message.split(" (line")[0][:120]
    return item


def analyze_source(req: AnalysisRequest) -> dict[str, Any]:
    src = SourceText(req.source)
    tree = parser.parse(src)
    issues = parser.syntax_issues(tree, src)
    funcs = parser.find_functions(tree, src, issues)

    if not funcs:
        if issues:
            raise SyntaxFailure(f"Syntax error at line {issues[0].line}, column {issues[0].column}: {issues[0].message}.",
                                locations=[i.to_dict() for i in issues])
        raise FunctionNotFound("No function definition found. Wrap the code in a function, e.g. int main(void) { ... }.")

    if req.function:
        matches = [f for f in funcs if f.name == req.function]
        if not matches:
            raise FunctionNotFound(f"Function '{req.function}' not found.", details={"available": [f.name for f in funcs]})
        fn = matches[0]
    else:
        fn = next((f for f in funcs if f.name == "main" and not f.has_error), None) \
            or next((f for f in funcs if not f.has_error), funcs[0])
    default_name = fn.name if not req.function else (next((f.name for f in funcs if f.name == "main"), funcs[0].name))

    if fn.has_error:
        inside = [i for i in issues if i.start_byte <= fn.node.end_byte and i.end_byte >= fn.node.start_byte]
        first = inside[0]
        raise SyntaxFailure(f"Syntax error in function '{fn.name}' at line {first.line}, column {first.column}: {first.message}. "
                            "No graph was generated.", locations=[i.to_dict() for i in inside])

    macros = parser.collect_macros(tree, src)
    scan = validation.scan_function(fn, src, macros)
    cfg = _build(fn, src, req.merge_blocks, req.convention)
    cfg.diagnostics = scan + cfg.diagnostics

    reach = reachability.analyze(cfg)
    struct = structural.count_decisions(fn.body, src, req.convention)
    cx = complexity.compute(cfg, reach, struct, req.convention)
    paths = basis_paths.compute(cfg, reach, cx["value"]) if req.basis_paths else \
        {"status": "disabled", "reason": "Basis paths were not requested.", "paths": [], "expected": cx["value"], "rank": 0}

    # diagnostics derived from the analysis
    for nid in reach.unreachable:
        n = cfg.nodes[nid]
        if n.kind == EXIT:
            continue
        if n.kind == BLOCK and not any(s.executable for s in n.stmts) and n.construct != "label":
            continue  # bare declarations such as `int x;` are not executable
        cfg.warn("UNREACHABLE_CODE", f"Unreachable code: {n.stmts[0].text[:60]}", "warning", n.stmts[0].line, n.stmts[0].column, nid)
    if not reach.exit_reachable:
        cfg.warn("EXIT_UNREACHABLE", "EXIT is unreachable: the function never returns (infinite loop or noreturn path).", "warning")
    elif reach.trapped:
        cfg.warn("TRAPPED_NODES", f"{len(reach.trapped)} node(s) are reachable but cannot reach EXIT (infinite loop).", "warning")
    if reach.irreducible:
        cfg.warn("IRREDUCIBLE_FLOW", "Irreducible control flow detected (goto into a loop).", "warning")
    for note in cx["applicability"]:
        if note["code"] == "STRUCTURAL_MISMATCH":
            cfg.warn("STRUCTURAL_MISMATCH", note["message"], "error")
        elif note["code"] == "FORMULA_MISMATCH":
            cfg.warn("FORMULA_MISMATCH", note["message"], "warning")
    for i in issues:
        if not (i.start_byte <= fn.node.end_byte and i.end_byte >= fn.node.start_byte):
            cfg.warn("SYNTAX_ERROR_ELSEWHERE", f"Syntax error outside this function at line {i.line}, column {i.column}: {i.message}.",
                     "warning", i.line, i.column)

    functions = []
    for f in funcs:
        item = _summary(f, src, macros, req.merge_blocks, req.convention) if f is not fn else \
            {"name": f.name, "start_line": f.start_line, "end_line": f.end_line, "complexity": cx["value"], "error": None}
        item["selected"] = f is fn
        item["default"] = f.name == default_name
        functions.append(item)

    return serialize(cfg, reach, cx, paths, functions, src)
