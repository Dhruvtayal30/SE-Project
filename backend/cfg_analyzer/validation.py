"""Input validation: request limits and the supported-C-subset scan.

Anything the CFG builder cannot represent faithfully is reported here, either as a blocking error
(the control-flow effect would be lost) or as a warning/info (the graph is still correct, but the
user should know about an assumption)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tree_sitter import Node as TSNode

from .errors import LimitExceeded, RequestError, UnsupportedConstruct
from .model import Diagnostic
from .parser import FunctionDef, SourceText

MAX_SOURCE_CHARS = 100_000
MAX_SOURCE_LINES = 4_000
MAX_NODES = 500            # displayed CFG nodes (after basic-block merging)
MAX_RAW_NODES = 3_000      # builder safety valve before merging
MAX_BASIS_COMPLEXITY = 120  # skip basis-path extraction above this M
MAX_FUNCTION_NAME = 200

NORETURN_CALLS = {"exit", "_exit", "_Exit", "abort", "quick_exit", "pthread_exit"}
NONLOCAL_CALLS = {"setjmp", "_setjmp", "sigsetjmp", "longjmp", "siglongjmp"}
PREPROC_BRANCH = {"preproc_if", "preproc_ifdef", "preproc_elif", "preproc_else", "preproc_elifdef"}
PREPROC_IGNORED = {"preproc_include", "preproc_def", "preproc_function_def", "preproc_call", "preproc_undef"}


@dataclass
class AnalysisRequest:
    source: str
    function: str | None
    merge_blocks: bool
    basis_paths: bool
    convention: str


def validate_request(payload: Any) -> AnalysisRequest:
    if not isinstance(payload, dict):
        raise RequestError("Request body must be a JSON object like {\"source\": \"...\"}.")
    source = payload.get("source")
    if not isinstance(source, str):
        raise RequestError("Field 'source' is required and must be a string.")
    if not source.strip():
        raise RequestError("Source is empty. Paste or upload some C code.", code="EMPTY_SOURCE")
    if "\x00" in source:
        raise RequestError("Source contains NUL characters; it does not look like C text.", code="INVALID_SOURCE")
    if len(source) > MAX_SOURCE_CHARS:
        raise LimitExceeded(f"Source is {len(source):,} characters; the limit is {MAX_SOURCE_CHARS:,}.",
                            code="SOURCE_TOO_LARGE", status=413)
    if source.count("\n") + 1 > MAX_SOURCE_LINES:
        raise LimitExceeded(f"Source has more than {MAX_SOURCE_LINES:,} lines.", code="SOURCE_TOO_LARGE", status=413)
    function = payload.get("function")
    if function is not None and (not isinstance(function, str) or len(function) > MAX_FUNCTION_NAME):
        raise RequestError("Field 'function' must be a function name (string).")
    convention = payload.get("convention", "course")
    if convention not in ("strict", "course"):
        raise RequestError("Field 'convention' must be 'strict' or 'course'.")
    options = payload.get("options", {})
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise RequestError("Field 'options' must be an object.")
    for key in ("merge_blocks", "basis_paths"):
        if key in options and not isinstance(options[key], bool):
            raise RequestError(f"Option '{key}' must be true or false.")
    return AnalysisRequest(source, function or None, options.get("merge_blocks", True),
                           options.get("basis_paths", True), convention)


def scan_function(fn: FunctionDef, src: SourceText, macros: dict[str, tuple[int, bool]]) -> list[Diagnostic]:
    """Find constructs outside the supported subset. Raises UnsupportedConstruct for blocking ones;
    returns the non-blocking diagnostics otherwise."""
    blocking: list[dict] = []
    diags: list[Diagnostic] = []
    seen_macro: set[tuple[str, int]] = set()

    def loc(n: TSNode, msg: str) -> dict:
        return {"line": n.start_point[0] + 1, "column": src.col(n.start_point[0], n.start_point[1]), "message": msg}

    def info(code: str, msg: str, n: TSNode, sev: str = "info") -> None:
        diags.append(Diagnostic(code, msg, sev, n.start_point[0] + 1, src.col(n.start_point[0], n.start_point[1])))

    def walk(n: TSNode) -> None:
        t = n.type
        if t in PREPROC_BRANCH:
            blocking.append(loc(n, "conditional compilation (#if / #ifdef / #else) inside a function"))
            return
        if t in PREPROC_IGNORED:
            info("PREPROCESSOR_IGNORED", f"Preprocessor directive inside the function was ignored (no macro expansion): "
                 f"{' '.join(src.node_text(n).split())[:40]}", n)
            return
        if t == "compound_statement" and n.parent is not None and n.parent.type == "parenthesized_expression":
            blocking.append(loc(n, "GNU statement expression ({ ... })"))
            return
        if t == "function_definition":
            blocking.append(loc(n, "nested function definition (GNU extension)"))
            return
        if t == "gnu_asm_expression":
            info("INLINE_ASM", "Inline assembly is treated as one opaque statement; its control flow is not modelled.", n)
        elif t == "goto_statement":
            info("GOTO_USED", "goto: an edge is drawn to the label; loops built from goto are not classified as structured loops.", n)
        elif t == "identifier":
            name = src.node_text(n)
            if name in macros and macros[name][1] and (name, n.start_point[0]) not in seen_macro:
                seen_macro.add((name, n.start_point[0]))
                info("MACRO_CONTROL_FLOW", f"Macro '{name}' (defined on line {macros[name][0]}) contains return/goto/break/continue; "
                     "macros are not expanded, so its control flow is NOT in the graph.", n, "warning")
            elif name in NONLOCAL_CALLS:
                info("NONLOCAL_JUMP", f"'{name}' transfers control non-locally; this is not modelled in the graph.", n, "warning")
        for c in n.children:
            walk(c)

    walk(fn.body)
    if blocking:
        first = blocking[0]["message"]
        raise UnsupportedConstruct(
            f"Unsupported construct in function '{fn.name}': {first}. "
            "Its control-flow effect cannot be represented faithfully, so no graph was generated.",
            locations=blocking)
    return diags
