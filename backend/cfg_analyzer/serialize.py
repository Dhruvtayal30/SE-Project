"""Turn the analysis results into the JSON response. This is the single source of truth the frontend renders."""

from __future__ import annotations

from collections import Counter
from typing import Any

from . import model as m
from .model import CFG
from .parser import SourceText
from .reachability import Reachability

API_VERSION = "1.0"

DECISION_ROLES = {"if": "if condition", "while": "while-loop condition", "for": "for-loop condition",
                  "do_while": "do-while condition", "ternary": "ternary (?:) condition",
                  "logical": "short-circuit operand", "switch_case": "switch case test",
                  "switch_default": "switch default test"}
BLOCK_ROLES = {"loop_head": "Loop head (constant-true loop)", "label": "Label", "for_update": "For-loop update",
               "for_init": "For-loop initialisation", "ternary_then": "Ternary value (true arm)",
               "ternary_else": "Ternary value (false arm)",
               "logical_value": "Short-circuit right operand value"}


def _role(cfg: CFG, n: m.Node, out_deg: int, has_return: bool) -> tuple[str, str]:
    if n.kind == m.ENTRY:
        return "Entry", "Synthetic start node. Control enters the function here."
    if n.kind == m.EXIT:
        return "Exit", "Single logical exit. Every return, noreturn call and fall-off-the-end connects here."
    if n.kind == m.SWITCH:
        return "Switch dispatch", (f"Multi-way branch with {out_deg} outgoing edges (one per case label plus default). "
                                   f"It adds {max(0, out_deg - 1)} to the cyclomatic complexity.")
    if n.kind == m.DECISION:
        what = DECISION_ROLES.get(n.construct, "condition")
        return f"Decision ({what})", (f"Evaluates one predicate of the {what}. It has True and False edges, "
                                      "so it adds 1 to the cyclomatic complexity.")
    role = BLOCK_ROLES.get(n.construct) or ("Return block" if has_return else "Sequential block")
    if n.construct == "block" and has_return:
        role = "Return block"
    return role, "Straight-line code: entered only at the top, left only at the bottom. It adds 0 to the cyclomatic complexity."


def serialize(cfg: CFG, reach: Reachability, cx: dict[str, Any], paths: dict[str, Any],
              functions: list[dict[str, Any]], src: SourceText) -> dict[str, Any]:
    out, inc = cfg.adjacency()
    nid = {i: f"n{i}" for i in cfg.nodes}
    eid = {e.id: f"e{e.id}" for e in cfg.edges}

    nodes = []
    for i, n in cfg.nodes.items():
        has_return = any(e.kind in (m.RETURN, m.NORETURN) for e in out[i])
        role, why = _role(cfg, n, len(out[i]), has_return)
        label = n.text if n.kind in (m.ENTRY, m.EXIT) else " ⏎ ".join(s.text for s in n.stmts)
        nodes.append({
            "id": nid[i], "index": i, "kind": n.kind, "construct": n.construct, "role": role, "explanation": why,
            "label": label, "statements": [s.to_dict() for s in n.stmts],
            "lines": [] if n.kind in (m.ENTRY, m.EXIT) else n.lines(),
            "reachable": n.reachable, "can_reach_exit": n.can_reach_exit,
            "distance": n.distance, "parent_edge": eid.get(n.parent_edge) if n.parent_edge else None,
            "loop_header": n.loop_header, "in_degree": len(inc[i]), "out_degree": len(out[i]),
            "returns": has_return,
        })
    edges = [{"id": eid[e.id], "index": e.id, "source": nid[e.src], "target": nid[e.dst], "kind": e.kind,
              "label": e.label, "via": e.via, "back_edge": e.back_edge, "reachable": e.reachable}
             for e in cfg.edges]

    line_map: dict[str, list[str]] = {}
    for i, n in cfg.nodes.items():
        if n.kind in (m.ENTRY, m.EXIT):
            continue
        for ln in n.lines():
            line_map.setdefault(str(ln), []).append(nid[i])

    kinds = Counter(n.kind for n in cfg.nodes.values())
    stats = {
        "nodes_total": len(cfg.nodes), "edges_total": len(cfg.edges),
        "nodes_reachable": len(reach.reachable), "nodes_unreachable": len(reach.unreachable),
        "decision_nodes": cx["decision_nodes"], "switch_nodes": kinds[m.SWITCH],
        "basic_blocks": kinds[m.BLOCK], "loops": len(reach.back_edges),
        "function_lines": cfg.function.end_line - cfg.function.start_line + 1,
    }
    reachability = {
        "exit_reachable": reach.exit_reachable,
        "unreachable_nodes": [nid[i] for i in reach.unreachable],
        "trapped_nodes": [nid[i] for i in reach.trapped],
        "back_edges": [eid[i] for i in reach.back_edges],
        "irreducible": reach.irreducible,
        "reachable_percent": round(100 * len(reach.reachable) / len(cfg.nodes), 2),
    }
    paths_out = dict(paths)
    paths_out["paths"] = [{**p, "nodes": [nid[i] for i in p["nodes"]], "edges": [eid[i] for i in p["edges"]],
                           "new_edges": [eid[i] for i in p["new_edges"]],
                           "decisions": [{**d, "node": nid[d["node"]], "edge": eid[d["edge"]]} for d in p["decisions"]]}
                          for p in paths["paths"]]
    order = {"error": 0, "warning": 1, "info": 2}
    diags = sorted(cfg.diagnostics, key=lambda d: (order.get(d.severity, 3), d.line or 0))
    return {
        "ok": True, "api_version": API_VERSION, "convention": cx["convention"],
        "function": {"name": cfg.function.name, "signature": cfg.function.signature,
                     "start_line": cfg.function.start_line, "end_line": cfg.function.end_line},
        "functions": functions,
        "graph": {"entry": nid[cfg.entry], "exit": nid[cfg.exit], "nodes": nodes, "edges": edges},
        "statistics": stats, "complexity": cx, "reachability": reachability, "paths": paths_out,
        "warnings": [d.to_dict(nid) for d in diags],
        "source_map": {"line_to_nodes": line_map},
        "assumptions": ["Static analysis only: the program is parsed, never compiled or executed.",
                        "Function calls are single statements (no inter-procedural analysis); macros are not expanded.",
                        "Paths are structural: branch conditions are not solved, so a listed path may be infeasible."],
    }
