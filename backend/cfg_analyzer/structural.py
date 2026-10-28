"""Independent structural decision count, derived from the syntax tree only (no CFG involved).

It is used as a cross-check of the CFG-based result: for the *whole* graph (reachable or not),
    1 + sum(max(0, outdegree - 1))  ==  1 + structural decision count.
Counting rules are selected by convention. `strict` follows plain McCabe (case labels count, default
does not, literal-true loops are folded); `course` counts a default label as a predicate as well.
"""

from __future__ import annotations

from tree_sitter import Node as TSNode

from .parser import UNEVALUATED, SourceText, is_const_true, logical_op


def count_decisions(body: TSNode, src: SourceText, convention: str = "strict") -> dict[str, int]:
    c = {"if": 0, "for": 0, "while": 0, "do_while": 0, "logical": 0,
         "ternary": 0, "case": 0, "default": 0}

    def walk(n: TSNode, skip: TSNode | None = None) -> None:
        t = n.type
        if t in UNEVALUATED:
            return
        if t == "if_statement":
            c["if"] += 1
        elif t == "while_statement":
            if convention == "course" or not is_const_true(n.child_by_field_name("condition"), src):
                c["while"] += 1
        elif t == "do_statement":
            if convention == "course" or not is_const_true(n.child_by_field_name("condition"), src):
                c["do_while"] += 1
        elif t == "for_statement":
            condition = n.child_by_field_name("condition")
            if convention == "course" or not is_const_true(condition, src):
                c["for"] += 1
        elif t == "case_statement":
            if n.child_by_field_name("value") is not None:
                c["case"] += 1
            elif convention == "course":
                c["default"] += 1
        elif t == "conditional_expression":
            c["ternary"] += 1
        elif logical_op(n):
            c["logical"] += 1
        value = n.child_by_field_name("value") if t == "case_statement" else None
        for ch in n.children:
            if value is not None and ch == value:
                continue  # case constants are never evaluated as control flow
            walk(ch)

    walk(body)
    c["total"] = sum(c.values())
    return c
