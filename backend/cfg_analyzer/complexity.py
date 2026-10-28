"""Cyclomatic complexity and convention-aware predicate counts derived from the actual CFG.

The headline value uses ``E - N + 2P`` on the ENTRY-reachable subgraph. A separate predicate count is
compared with that graph formula after every analysis; disagreement is returned as a visible warning.
Strict mode retains plain McCabe switch counting. Course mode builds a default-bearing switch as a chain
of binary decisions, including a predicate for its default label. A syntax-tree count remains an
independent whole-function cross-check. Parallel edges and self-loops retain their edge identities.
"""

from __future__ import annotations

from typing import Any

from . import model as m
from .model import CFG
from .reachability import Reachability


def _components(nodes: set[int], edges) -> int:
    parent = {n: n for n in nodes}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        if e.src in parent and e.dst in parent:
            parent[find(e.src)] = find(e.dst)
    return len({find(n) for n in nodes})


def _branch(nodes: set[int], edges) -> tuple[int, int]:
    outdeg = {n: 0 for n in nodes}
    for e in edges:
        if e.src in outdeg:
            outdeg[e.src] += 1
    return sum(max(0, d - 1) for d in outdeg.values()), sum(1 for d in outdeg.values() if d >= 2)


BANDS = [(10, "low", "Simple function, low risk", "Easy to understand and test; around this many tests cover every independent path."),
         (20, "moderate", "Moderately complex", "More than ten independent paths: consider splitting the function or adding tests per branch."),
         (50, "high", "Complex, high risk", "Hard to test exhaustively; refactoring into smaller functions is recommended."),
         (10**9, "very_high", "Very complex, very high risk", "Practically untestable as one unit; refactor.")]


def band(m: int) -> dict[str, str]:
    for limit, key, label, text in BANDS:
        if m <= limit:
            return {"band": key, "label": label, "text": text}
    raise AssertionError


PREDICATE_KINDS = ("if", "for", "while", "do_while", "logical", "ternary", "case", "default")


def _predicate_breakdown(cfg: CFG, live: set[int], convention: str) -> dict[str, int]:
    counts = {kind: 0 for kind in PREDICATE_KINDS}
    out, _ = cfg.adjacency()
    decision_constructs = {kind: kind for kind in ("if", "for", "while", "do_while", "logical", "ternary")}
    for nid in live:
        node = cfg.nodes[nid]
        if node.kind == m.DECISION:
            if node.construct in decision_constructs:
                counts[decision_constructs[node.construct]] += 1
            elif node.construct == "switch_case":
                counts["case"] += 1
            elif node.construct == "switch_default":
                counts["default"] += 1
        elif node.kind == m.SWITCH:
            counts["case"] += sum(edge.kind == m.CASE for edge in out[nid])
        elif convention == "course" and node.construct == "loop_head":
            text = node.stmts[0].text if node.stmts else ""
            if text.startswith("do … while"):
                counts["do_while"] += 1
            elif text.startswith("while "):
                counts["while"] += 1
            elif text.startswith("for"):
                counts["for"] += 1
    return counts


def compute(cfg: CFG, reach: Reachability, structural: dict[str, int], convention: str = "strict") -> dict[str, Any]:
    all_nodes = set(cfg.nodes)
    live = reach.reachable
    live_edges = [e for e in cfg.edges if e.src in live]
    n_l, e_l = len(live), len(live_edges)
    p_l = _components(live, live_edges)
    m_graph = e_l - n_l + 2 * p_l
    branch_l, decisions_l = _branch(live, live_edges)
    m_branch = 1 + branch_l

    n_a, e_a = len(all_nodes), len(cfg.edges)
    p_a = _components(all_nodes, cfg.edges)
    branch_a, _ = _branch(all_nodes, cfg.edges)
    predicate_breakdown = _predicate_breakdown(cfg, live, convention)
    predicate_count = sum(predicate_breakdown.values())
    predicate_value = predicate_count + 1
    structural_value = 1 + structural["total"]
    structural_agrees = (1 + branch_a) == structural_value

    notes: list[dict[str, str]] = []
    if not reach.exit_reachable:
        notes.append({"code": "EXIT_UNREACHABLE", "message":
                      f"EXIT is not reachable from ENTRY (non-terminating function). The graph has no sink, so E-N+2P ({m_graph}) "
                      f"exceeds the branch formula ({m_branch}) by one; the reading 'number of independent ENTRY-to-EXIT paths' "
                      "does not apply and no basis paths are produced."})
    elif reach.trapped:
        notes.append({"code": "TRAPPED_NODES", "message":
                      f"{len(reach.trapped)} reachable node(s) can never reach EXIT (infinite loop inside a branch). "
                      "M is still valid as a graph measure, but terminating basis paths are not available."})
    if reach.unreachable:
        notes.append({"code": "UNREACHABLE_EXCLUDED", "message":
                      f"{len(reach.unreachable)} unreachable node(s) are excluded from M (full graph: N={n_a}, E={e_a}, P={p_a})."})
    if reach.irreducible:
        notes.append({"code": "IRREDUCIBLE", "message": "The graph contains irreducible control flow (goto into a loop); loop edges are approximate."})
    if m_graph != predicate_value:
        notes.append({"code": "FORMULA_MISMATCH", "message":
                      f"Formula invariant failed for {convention} convention: graph formula gives {m_graph}, "
                      f"while predicate formula gives {predicate_value} (P_d={predicate_count}). Both values are shown."})
    if not structural_agrees:
        notes.append({"code": "STRUCTURAL_MISMATCH", "message":
                      f"Internal consistency check failed: graph branch count gives {1 + branch_a}, syntax tree gives {structural_value}."})

    return {
        "value": m_graph,
        "convention": convention,
        "convention_label": "Course convention" if convention == "course" else "Strict McCabe",
        "formula": "M = E − N + 2P",
        "substituted": f"M = {e_l} − {n_l} + 2×{p_l} = {m_graph}",
        "nodes": n_l, "edges": e_l, "components": p_l,
        "decision_nodes": decisions_l, "branch_contribution": branch_l,
        "branch_formula": "M = 1 + Σ max(0, outdeg(v) − 1)",
        "branch_substituted": f"M = 1 + {branch_l} = {m_branch}",
        "branch_value": m_branch,
        "predicate_formula": "M = P_d + 1",
        "predicate_substituted": f"M = {predicate_count} + 1 = {predicate_value}",
        "predicate_count": predicate_count,
        "predicate_breakdown": predicate_breakdown,
        "predicate_value": predicate_value,
        "formulas_agree": m_graph == predicate_value,
        "structural": {"value": structural_value, "decisions": structural["total"],
                       "breakdown": {k: v for k, v in structural.items() if k != "total"},
                       "agrees": structural_agrees,
                       "scope": "whole graph, including unreachable code"},
        "full_graph": {"nodes": n_a, "edges": e_a, "components": p_a, "value": e_a - n_a + 2 * p_a},
        "interpretation": band(m_graph),
        "applicability": notes,
    }
