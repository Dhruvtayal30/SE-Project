"""Graph data model shared by every analysis stage.

One model, one source of truth: the CFG built here is the only graph that metrics, paths and the
JSON response are derived from. Nothing in this module knows about tree-sitter, Flask or rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Node kinds
ENTRY, EXIT, BLOCK, DECISION, SWITCH = "entry", "exit", "block", "decision", "switch"

# Edge kinds
NEXT, TRUE, FALSE, CASE, DEFAULT = "next", "true", "false", "case", "default"
FALLTHROUGH, BREAK, CONTINUE, GOTO, RETURN, NORETURN = (
    "fallthrough", "break", "continue", "goto", "return", "noreturn")


@dataclass
class Stmt:
    """A source fragment (statement, condition, ...) with its 1-based location."""
    text: str
    line: int
    column: int
    end_line: int
    end_column: int
    executable: bool = True           # False for declarations without initialisers

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "line": self.line, "column": self.column,
                "end_line": self.end_line, "end_column": self.end_column}


@dataclass
class Node:
    id: int
    kind: str
    construct: str                     # which source construct produced it: "if", "while", "statement", ...
    stmts: list[Stmt] = field(default_factory=list)
    # Filled in by later stages:
    reachable: bool = True
    can_reach_exit: bool = True
    distance: int | None = None        # edges on a shortest path from ENTRY
    parent_edge: int | None = None     # last edge of that shortest path
    loop_header: bool = False

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.stmts)

    @property
    def start_line(self) -> int | None:
        return min((s.line for s in self.stmts), default=None)

    @property
    def start_key(self) -> tuple[int, int]:
        return min(((s.line, s.column) for s in self.stmts), default=(10**9, 0))

    def lines(self) -> list[int]:
        out: set[int] = set()
        for s in self.stmts:
            out.update(range(s.line, s.end_line + 1))
        return sorted(out)


@dataclass
class Edge:
    id: int
    src: int
    dst: int
    kind: str
    label: str = ""
    via: str | None = None             # "break" / "continue" / "goto" when a branch edge is also a jump
    back_edge: bool = False
    reachable: bool = True


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str = "warning"          # "info" | "warning" | "error"
    line: int | None = None
    column: int | None = None
    node: int | None = None

    def to_dict(self, node_ids: dict[int, str] | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "severity": self.severity, "message": self.message,
                             "line": self.line, "column": self.column}
        if self.node is not None and node_ids is not None:
            d["node"] = node_ids.get(self.node)
        return d


@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    signature: str
    has_error: bool = False


@dataclass
class CFG:
    function: FunctionInfo
    nodes: dict[int, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    entry: int = 0
    exit: int = 1
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def out_edges(self, nid: int) -> list[Edge]:
        return [e for e in self.edges if e.src == nid]

    def in_edges(self, nid: int) -> list[Edge]:
        return [e for e in self.edges if e.dst == nid]

    def adjacency(self) -> tuple[dict[int, list[Edge]], dict[int, list[Edge]]]:
        out: dict[int, list[Edge]] = {n: [] for n in self.nodes}
        inc: dict[int, list[Edge]] = {n: [] for n in self.nodes}
        for e in self.edges:
            out[e.src].append(e)
            inc[e.dst].append(e)
        return out, inc

    def warn(self, code: str, message: str, severity: str = "warning", line: int | None = None,
             column: int | None = None, node: int | None = None) -> None:
        d = Diagnostic(code, message, severity, line, column, node)
        if d not in self.diagnostics:
            self.diagnostics.append(d)
