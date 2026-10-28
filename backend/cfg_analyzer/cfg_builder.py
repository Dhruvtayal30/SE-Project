"""Build a fine-grained CFG (one node per simple statement / condition) from a tree-sitter function.

Technique: a *frontier* of pending edges ("outs") whose destination is not known yet. Creating a node
wires every pending out to it; structured statements are frontier manipulation:

    if      (T, F) = cond(c); frontier = T; then; keep outs; frontier = F; else; frontier = both
    while   head = first node of cond; body outs and `continue`s -> head; exits = F + `break`s
    break   the frontier becomes pending `break` outs; frontier = []  (so following code is dead)

`&&`, `||`, `!` and `?:` are expanded into real decision nodes (short-circuit order preserved), so each
atomic predicate is one decision. Merging straight-line nodes into basic blocks happens afterwards in
`basic_blocks.compact`; reachability is decided afterwards in `reachability`, so dead code is built
as ordinary (but unreachable) nodes rather than silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tree_sitter import Node as TSNode

from . import model as m
from .errors import LimitExceeded, UnsupportedConstruct
from .model import CFG, Edge, FunctionInfo, Node, Stmt
from .parser import (FunctionDef, SourceText, children, ctl_subexprs, is_const_true, is_ternary,
                     logical_op, not_arg, unwrap)
from .validation import MAX_RAW_NODES, NORETURN_CALLS

ENTRY_ID, EXIT_ID = 0, 1
LABELS = {m.TRUE: "True", m.FALSE: "False"}


@dataclass
class Out:
    """An edge whose destination is not known yet."""
    src: int
    kind: str = m.NEXT
    label: str = ""
    via: str | None = None


@dataclass
class Ctx:
    kind: str  # "loop" | "switch"
    breaks: list[Out] = field(default_factory=list)
    continues: list[Out] = field(default_factory=list)


def build_cfg(fn: FunctionDef, src: SourceText, convention: str = "strict") -> CFG:
    return _Builder(fn, src, convention).build()


class _Builder:
    def __init__(self, fn: FunctionDef, src: SourceText, convention: str = "strict"):
        self.fn, self.src = fn, src
        self.convention = convention
        info = FunctionInfo(fn.name, fn.start_line, fn.end_line, fn.signature, fn.has_error)
        self.cfg = CFG(info, entry=ENTRY_ID, exit=EXIT_ID)
        self.cfg.nodes[ENTRY_ID] = Node(ENTRY_ID, m.ENTRY, "entry", [Stmt("ENTRY", fn.start_line, 1, fn.start_line, 1)])
        self.cfg.nodes[EXIT_ID] = Node(EXIT_ID, m.EXIT, "exit", [Stmt("EXIT", fn.end_line, 1, fn.end_line, 1)])
        self.seq = EXIT_ID                       # last allocated node id
        self.eseq = 0
        self.frontier: list[Out] = [Out(ENTRY_ID)]
        self.ctx: list[Ctx] = []
        self.labels: dict[str, int] = {}
        self.gotos: list[tuple[list[Out], str, TSNode]] = []

    # ------------------------------------------------------------------ plumbing
    def _edge(self, src: int, dst: int, kind: str, label: str = "", via: str | None = None) -> None:
        self.eseq += 1
        self.cfg.edges.append(Edge(self.eseq, src, dst, kind, label, via))

    def _link(self, outs: list[Out], dst: int) -> None:
        for o in outs:
            self._edge(o.src, dst, o.kind, o.label, o.via)

    def _node(self, kind: str, construct: str, stmts: list[Stmt]) -> Node:
        """Create a node, wire the frontier into it, clear the frontier."""
        self.seq += 1
        if self.seq > MAX_RAW_NODES:
            raise LimitExceeded(f"Function '{self.fn.name}' is too large to analyse "
                                f"(more than {MAX_RAW_NODES:,} statements and conditions).", code="GRAPH_TOO_LARGE")
        node = Node(self.seq, kind, construct, stmts)
        self.cfg.nodes[node.id] = node
        self._link(self.frontier, node.id)
        self.frontier = []
        return node

    def _mark(self) -> int:
        return self.seq

    def _first_since(self, mark: int) -> int | None:
        return mark + 1 if self.seq > mark else None

    def _jump(self, kind: str) -> list[Out]:
        """Turn the frontier into pending jump edges (break / continue / goto)."""
        outs = []
        for o in self.frontier:
            if o.kind == m.NEXT:
                outs.append(Out(o.src, kind, kind))
            else:  # a True/False/case edge keeps its identity and records that it is also a jump
                outs.append(Out(o.src, o.kind, f"{o.label} · {kind}", kind))
        self.frontier = []
        return outs

    def _fail(self, n: TSNode, msg: str) -> UnsupportedConstruct:
        loc = {"line": n.start_point[0] + 1, "column": self.src.col(*n.start_point), "message": msg}
        return UnsupportedConstruct(f"{msg} (line {loc['line']}).", locations=[loc])

    # ------------------------------------------------------------------ driver
    def build(self) -> CFG:
        self._stmt(self.fn.body)
        self._link(self.frontier, EXIT_ID)       # falling off the end of the function
        for outs, name, n in self.gotos:
            if name not in self.labels:
                raise self._fail(n, f"goto to undefined label '{name}'")
            self._link(outs, self.labels[name])
        return self.cfg

    # ------------------------------------------------------------------ expressions
    def _decision(self, e: TSNode, construct: str) -> Node:
        return self._node(m.DECISION, construct, [self.src.stmt(e)])

    def _cond(self, e: TSNode, construct: str) -> tuple[list[Out], list[Out]]:
        """Expand a condition into decision nodes. Returns (true outs, false outs); the frontier is left empty."""
        e = unwrap(e)
        op = logical_op(e)
        if op:
            tl, fl = self._cond(e.child_by_field_name("left"), construct)
            self.frontier = tl if op == "&&" else fl
            tr, fr = self._cond(e.child_by_field_name("right"), "logical")
            return (tr, fl + fr) if op == "&&" else (tl + tr, fr)
        arg = not_arg(e)
        if arg is not None:
            inner = unwrap(arg)
            if logical_op(inner) or not_arg(inner) is not None:   # De Morgan: only when it exposes more branches
                t, f = self._cond(inner, construct)
                return f, t
        self._expand_ctl(e)                      # ?: or && inside an atomic predicate, e.g. f(a && b) > 0
        node = self._decision(e, construct)
        return [Out(node.id, m.TRUE, "True")], [Out(node.id, m.FALSE, "False")]

    def _expand_ctl(self, n: TSNode) -> None:
        """Emit the decisions hidden inside an expression statement/initialiser/argument."""
        for c in ctl_subexprs(n):
            if is_ternary(c):
                cond = c.child_by_field_name("condition")
                t, f = self._cond(cond, "ternary")
                outs: list[Out] = []
                for arm_outs, arm, name in ((t, c.child_by_field_name("consequence"), "ternary_then"),
                                            (f, c.child_by_field_name("alternative"), "ternary_else")):
                    self.frontier = arm_outs
                    self._expand_ctl(arm)
                    node = self._node(m.BLOCK, name, [self.src.stmt(arm)])
                    outs.append(Out(node.id))
                self.frontier = outs
            else:
                # && / || used as a value: only the LEFT operand decides whether the right one is evaluated.
                # The right operand's value is just computed (an arm), it is not a branch of its own.
                op = logical_op(c)
                right = c.child_by_field_name("right")
                t, f = self._cond(c.child_by_field_name("left"), "logical")
                self.frontier = t if op == "&&" else f
                self._expand_ctl(right)
                arm = self._node(m.BLOCK, "logical_value", [self.src.stmt(right)])
                self.frontier = [Out(arm.id)] + (f if op == "&&" else t)

    # ------------------------------------------------------------------ statements
    def _stmt(self, n: TSNode) -> None:
        t = n.type
        if t == "comment":
            return
        handler = getattr(self, "_s_" + t, None)
        if handler is not None:
            handler(n)
        elif t in ("declaration", "type_definition", "struct_specifier", "union_specifier", "enum_specifier"):
            self._simple(n, "statement")
        elif t.startswith("preproc_"):
            return                                # include/define/pragma: reported by validation, no control flow
        else:
            raise self._fail(n, f"unsupported statement type '{t}'")

    def _simple(self, n: TSNode, construct: str = "statement", text: str | None = None) -> Node:
        self._expand_ctl(n)
        node = self._node(m.BLOCK, construct, [self.src.stmt(n, text)])
        if n.type == "declaration" and "init_declarator" not in self.src.node_text(n) and "=" not in self.src.node_text(n):
            node.stmts[0].executable = False
        self.frontier = [Out(node.id)]
        return node

    def _s_compound_statement(self, n: TSNode) -> None:
        for c in children(n):
            self._stmt(c)

    def _s_expression_statement(self, n: TSNode) -> None:
        kids = children(n)
        if not kids:
            return                                # empty statement ';'
        node = self._simple(n)
        e = unwrap(kids[0])
        if e.type == "call_expression":
            fn = e.child_by_field_name("function")
            if fn is not None and fn.type == "identifier" and self.src.node_text(fn) in NORETURN_CALLS:
                self.cfg.warn("NORETURN_CALL", f"'{self.src.node_text(fn)}()' never returns; an edge to EXIT is drawn.",
                              "info", n.start_point[0] + 1, self.src.col(*n.start_point), node.id)
                self._edge(node.id, EXIT_ID, m.NORETURN, f"{self.src.node_text(fn)}()")
                self.frontier = []

    def _s_if_statement(self, n: TSNode) -> None:
        t, f = self._cond(n.child_by_field_name("condition"), "if")
        self.frontier = t
        self._stmt(n.child_by_field_name("consequence"))
        then_outs = self.frontier
        self.frontier = f
        alt = n.child_by_field_name("alternative")
        if alt is not None:
            for c in children(alt):
                self._stmt(c)
        self.frontier = then_outs + self.frontier

    def _loop_head(self, text: str, n: TSNode) -> Node:
        """Explicit head for a loop whose condition is the constant `true` (no decision exists)."""
        node = self._node(m.BLOCK, "loop_head", [self.src.stmt(n, text)])
        node.stmts[0].end_line = node.stmts[0].line
        node.stmts[0].end_column = node.stmts[0].column + len(text)
        self.frontier = [Out(node.id)]
        self.cfg.warn("CONSTANT_LOOP", "Loop condition is the literal constant true: no False edge is created, so code after "
                      "the loop is reachable only through break/return/goto.", "info", n.start_point[0] + 1,
                      self.src.col(*n.start_point), node.id)
        return node

    def _s_while_statement(self, n: TSNode) -> None:
        cond, body = n.child_by_field_name("condition"), n.child_by_field_name("body")
        ctx = Ctx("loop")
        if is_const_true(cond, self.src):
            head = self._loop_head(f"while {self.src.norm(cond)}", n).id
            self.ctx.append(ctx)
            self._stmt(body)
            self.ctx.pop()
            self._link(self.frontier + ctx.continues, head)
            self.frontier = ctx.breaks
            return
        mark = self._mark()
        t, f = self._cond(cond, "while")
        head = self._first_since(mark)
        self.frontier = t
        self.ctx.append(ctx)
        self._stmt(body)
        self.ctx.pop()
        self._link(self.frontier + ctx.continues, head)
        self.frontier = f + ctx.breaks

    def _s_do_statement(self, n: TSNode) -> None:
        cond, body = n.child_by_field_name("condition"), n.child_by_field_name("body")
        ctx = Ctx("loop")
        const = is_const_true(cond, self.src)
        if const:
            head = self._loop_head(f"do … while {self.src.norm(cond)}", n).id
            self.ctx.append(ctx)
            self._stmt(body)
            self.ctx.pop()
            self._link(self.frontier + ctx.continues, head)
            self.frontier = ctx.breaks
            return
        mark = self._mark()
        self.ctx.append(ctx)
        self._stmt(body)
        self.ctx.pop()
        self.frontier = self.frontier + ctx.continues     # `continue` goes to the condition
        t, f = self._cond(cond, "do_while")
        first = self._first_since(mark)
        self._link(t, first)
        self.frontier = f + ctx.breaks

    def _s_for_statement(self, n: TSNode) -> None:
        init, cond = n.child_by_field_name("initializer"), n.child_by_field_name("condition")
        update, body = n.child_by_field_name("update"), n.child_by_field_name("body")
        if init is not None:
            if init.type == "declaration":
                self._simple(init, "for_init")
            else:
                self._simple(init, "for_init", self.src.norm(init) + ";")
        ctx = Ctx("loop")
        const = is_const_true(cond, self.src)
        if const:
            head = self._loop_head("for (;;)" if cond is None else f"for (; {self.src.norm(cond)};)", n).id
            t: list[Out] = []
            f: list[Out] = []
        else:
            mark = self._mark()
            t, f = self._cond(cond, "for")
            head = self._first_since(mark)
            self.frontier = t
        self.ctx.append(ctx)
        self._stmt(body)
        self.ctx.pop()
        self.frontier = self.frontier + ctx.continues     # `continue` reaches the update expression
        if update is not None:
            self._simple(update, "for_update")
        self._link(self.frontier, head)
        self.frontier = f + ctx.breaks

    def _s_switch_statement(self, n: TSNode) -> None:
        cond, body = n.child_by_field_name("condition"), n.child_by_field_name("body")
        self._expand_ctl(cond)
        items = children(body) if body.type == "compound_statement" else [body]
        cases = [item for item in items if item.type == "case_statement"]
        default_item = next((item for item in cases if item.child_by_field_name("value") is None), None)
        if self.convention == "course" and default_item is not None:
            self._s_switch_with_default_chain(n, cond, items, cases, default_item)
            return

        sw = self._node(m.SWITCH, "switch", [self.src.stmt(n, "switch " + self.src.norm(cond), cond)])
        ctx = Ctx("switch")
        self.ctx.append(ctx)
        self.frontier = []                                    # statements before the first label are dead
        has_default = False
        for item in items:
            if item.type != "case_statement":
                self._stmt(item)
                continue
            value = item.child_by_field_name("value")
            if value is None:
                has_default, kind, label = True, m.DEFAULT, "default"
            else:
                kind, label = m.CASE, "case " + self.src.norm(value)
            fall = [Out(o.src, m.FALLTHROUGH, "fall-through") if o.kind == m.NEXT else o for o in self.frontier]
            self.frontier = fall + [Out(sw.id, kind, label)]
            for c in children(item):
                if value is not None and c == value:
                    continue
                self._stmt(c)
        self.ctx.pop()
        outs = self.frontier + ctx.breaks
        if not has_default:
            outs.append(Out(sw.id, m.DEFAULT, "default (no match)"))
        self.frontier = outs

    def _s_switch_with_default_chain(self, n: TSNode, cond: TSNode, items: list[TSNode],
                                     cases: list[TSNode], default_item: TSNode) -> None:
        """Model a default-bearing switch as binary label tests, with default tested last."""
        selector = self.src.norm(unwrap(cond))
        tests = [item for item in cases if item is not default_item] + [default_item]
        entries: dict[int, Out] = {}
        previous: Node | None = None
        for item in tests:
            value = item.child_by_field_name("value")
            is_default = value is None
            label = "default" if is_default else f"{selector} == {self.src.norm(value)}"
            stmt = self.src.stmt(item, label)
            # The test belongs to the label line, not to all statements in its case body.
            stmt.end_line = stmt.line
            stmt.end_column = stmt.column + len(label)
            if previous is not None:
                self.frontier = [Out(previous.id, m.FALSE, "False")]
            test = self._node(m.DECISION, "switch_default" if is_default else "switch_case", [stmt])
            entries[item.id] = Out(test.id, m.TRUE, "True")
            previous = test

        assert previous is not None
        no_match = Out(previous.id, m.FALSE, "False · no match")
        ctx = Ctx("switch")
        self.ctx.append(ctx)
        self.frontier = []                                    # statements before the first label are dead
        for item in items:
            if item.type != "case_statement":
                self._stmt(item)
                continue
            fall = [Out(o.src, m.FALLTHROUGH, "fall-through") if o.kind == m.NEXT else o
                    for o in self.frontier]
            self.frontier = fall + [entries[item.id]]
            value = item.child_by_field_name("value")
            for child in children(item):
                if value is not None and child == value:
                    continue
                self._stmt(child)
        self.ctx.pop()
        self.frontier = self.frontier + ctx.breaks + [no_match]

    def _s_case_statement(self, n: TSNode) -> None:
        raise self._fail(n, "'case'/'default' label nested inside another statement of the switch (Duff's-device style) is not supported")

    def _s_return_statement(self, n: TSNode) -> None:
        node = self._simple(n, "return")
        self._edge(node.id, EXIT_ID, m.RETURN, "return")
        self.frontier = []

    def _s_break_statement(self, n: TSNode) -> None:
        if not self.ctx:
            raise self._fail(n, "'break' outside a loop or switch")
        self.ctx[-1].breaks += self._jump(m.BREAK)

    def _s_continue_statement(self, n: TSNode) -> None:
        loops = [c for c in self.ctx if c.kind == "loop"]
        if not loops:
            raise self._fail(n, "'continue' outside a loop")
        loops[-1].continues += self._jump(m.CONTINUE)

    def _s_goto_statement(self, n: TSNode) -> None:
        label = n.child_by_field_name("label")
        if label is None:
            raise self._fail(n, "computed goto is not supported")
        name = self.src.node_text(label)
        outs = self._jump(m.GOTO)
        for o in outs:
            if o.kind == m.GOTO:
                o.label = f"goto {name}"
        self.gotos.append((outs, name, n))

    def _s_labeled_statement(self, n: TSNode) -> None:
        label = n.child_by_field_name("label")
        name = self.src.node_text(label)
        if name in self.labels:
            raise self._fail(n, f"duplicate label '{name}'")
        node = self._node(m.BLOCK, "label", [self.src.stmt(label, name + ":", label)])
        self.labels[name] = node.id
        self.frontier = [Out(node.id)]
        for c in children(n):
            if c != label:
                self._stmt(c)
