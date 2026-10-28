"""Thin tree-sitter layer: parsing, function discovery, syntax errors, and the small expression
helpers (parentheses, constant conditions, short-circuit operators) shared by the CFG builder and
the independent structural counter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

import tree_sitter_c as tsc
from tree_sitter import Language, Node as TSNode, Parser, Tree

from .model import Stmt

_LANGUAGE = Language(tsc.language())

CONTAINER_TYPES = {"translation_unit", "preproc_if", "preproc_ifdef", "preproc_else", "preproc_elif",
                   "preproc_elifdef", "linkage_specification", "declaration_list"}
UNEVALUATED = {"sizeof_expression", "alignof_expression"}  # operands are never executed


class SourceText:
    """Source with byte->character column conversion (tree-sitter columns are bytes)."""

    def __init__(self, text: str):
        self.text = text
        self.data = text.encode("utf-8")
        self._lines = self.data.split(b"\n")

    def col(self, row: int, byte_col: int) -> int:
        line = self._lines[row] if row < len(self._lines) else b""
        return len(line[:byte_col].decode("utf-8", "ignore")) + 1

    def node_text(self, n: TSNode) -> str:
        return self.data[n.start_byte:n.end_byte].decode("utf-8", "replace")

    def norm(self, n: TSNode) -> str:
        return " ".join(self.node_text(n).split())

    def stmt(self, n: TSNode, text: str | None = None, end: TSNode | None = None) -> Stmt:
        e = end or n
        return Stmt(text if text is not None else self.norm(n),
                    n.start_point[0] + 1, self.col(n.start_point[0], n.start_point[1]),
                    e.end_point[0] + 1, self.col(e.end_point[0], e.end_point[1]))


def parse(src: SourceText) -> Tree:
    return Parser(_LANGUAGE).parse(src.data)  # a Parser per call: instances are not thread-safe


@dataclass
class FunctionDef:
    name: str
    node: TSNode
    body: TSNode
    start_line: int
    end_line: int
    signature: str
    has_error: bool = False


@dataclass
class SyntaxIssue:
    line: int
    column: int
    message: str
    start_byte: int
    end_byte: int

    def to_dict(self) -> dict:
        return {"line": self.line, "column": self.column, "message": self.message}


def _declarator_name(decl: TSNode | None, src: SourceText) -> str:
    while decl is not None:
        if decl.type == "function_declarator":
            inner = decl.child_by_field_name("declarator")
            if inner is not None and inner.type == "identifier":
                return src.node_text(inner)
            decl = inner
        elif decl.type in ("pointer_declarator", "parenthesized_declarator", "attributed_declarator"):
            decl = decl.child_by_field_name("declarator") or (decl.named_children[-1] if decl.named_children else None)
        elif decl.type == "identifier":
            return src.node_text(decl)
        else:
            break
    return "<anonymous>"


def syntax_issues(tree: Tree, src: SourceText, limit: int = 25) -> list[SyntaxIssue]:
    """Every ERROR / MISSING node, in source order (innermost only)."""
    out: list[SyntaxIssue] = []

    def walk(n: TSNode) -> None:
        if len(out) >= limit or not n.has_error:
            return
        if n.is_missing:
            msg = f"missing '{n.type}'"
        elif n.type == "ERROR":
            snippet = " ".join(src.node_text(n).split())[:24]
            msg = f"unexpected '{snippet}'" if snippet else "unexpected token"
        else:
            msg = ""
        if msg:
            out.append(SyntaxIssue(n.start_point[0] + 1, src.col(n.start_point[0], n.start_point[1]), msg,
                                   n.start_byte, n.end_byte))
            if n.type == "ERROR":
                return
        for c in n.children:
            walk(c)

    walk(tree.root_node)
    return out


def find_functions(tree: Tree, src: SourceText, issues: list[SyntaxIssue]) -> list[FunctionDef]:
    funcs: list[FunctionDef] = []

    def walk(n: TSNode) -> None:
        for c in n.children:
            if c.type == "function_definition":
                body = c.child_by_field_name("body")
                if body is None:
                    continue
                sig = " ".join(src.data[c.start_byte:body.start_byte].decode("utf-8", "replace").split())
                bad = any(i.start_byte <= c.end_byte and i.end_byte >= c.start_byte for i in issues)
                funcs.append(FunctionDef(_declarator_name(c.child_by_field_name("declarator"), src), c, body,
                                         c.start_point[0] + 1, c.end_point[0] + 1, sig, bad))
            elif c.type in CONTAINER_TYPES:
                walk(c)

    walk(tree.root_node)
    return funcs


_CONTROL_WORDS = re.compile(r"\b(return|goto|break|continue)\b")


def collect_macros(tree: Tree, src: SourceText) -> dict[str, tuple[int, bool]]:
    """Macros defined in the file -> (line, replacement text contains control flow)."""
    macros: dict[str, tuple[int, bool]] = {}

    def walk(n: TSNode) -> None:
        for c in n.children:
            if c.type in ("preproc_def", "preproc_function_def"):
                name = c.child_by_field_name("name")
                value = c.child_by_field_name("value")
                if name is not None:
                    text = src.node_text(value) if value is not None else ""
                    macros[src.node_text(name)] = (c.start_point[0] + 1, bool(_CONTROL_WORDS.search(text)))
            elif c.type in CONTAINER_TYPES:
                walk(c)

    walk(tree.root_node)
    return macros


# ---------------------------------------------------------------- expression helpers
def children(n: TSNode) -> list[TSNode]:
    return [c for c in n.named_children if c.type != "comment"]


def unwrap(e: TSNode) -> TSNode:
    """Strip redundant parentheses."""
    while e.type == "parenthesized_expression":
        inner = children(e)
        if len(inner) != 1:
            break
        e = inner[0]
    return e


def logical_op(e: TSNode) -> str | None:
    """'&&' or '||' for a short-circuit binary expression."""
    if e.type != "binary_expression":
        return None
    op = e.child_by_field_name("operator")
    return op.type if op is not None and op.type in ("&&", "||") else None


def not_arg(e: TSNode) -> TSNode | None:
    if e.type == "unary_expression":
        op = e.child_by_field_name("operator")
        if op is not None and op.type == "!":
            return e.child_by_field_name("argument")
    return None


def is_ternary(e: TSNode) -> bool:
    return e.type == "conditional_expression"


def is_ctl(e: TSNode) -> bool:
    return logical_op(e) is not None or is_ternary(e)


def is_const_true(e: TSNode | None, src: SourceText) -> bool:
    """Literal-true loop conditions only: `1`, `0x1`, `true`. Nothing else is folded."""
    if e is None:
        return True  # for (;;)
    e = unwrap(e)
    if e.type == "true":
        return True
    if e.type == "number_literal":
        t = src.node_text(e).rstrip("uUlL").lower()
        try:
            if re.fullmatch(r"0[0-7]+", t):
                return int(t, 8) != 0
            return int(t, 0) != 0
        except ValueError:
            return False
    return False


def ctl_subexprs(n: TSNode) -> Iterator[TSNode]:
    """Outermost ?: / && / || expressions in `n` (itself included), in source order."""
    if is_ctl(n):
        yield n
        return
    for c in n.named_children:
        if c.type in UNEVALUATED:
            continue
        yield from ctl_subexprs(c)
