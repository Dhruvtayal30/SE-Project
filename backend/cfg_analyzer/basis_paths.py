"""Independent (basis) ENTRY-to-EXIT paths for white-box testing.

Independence convention: each path is a vector counting how often it traverses every edge; a set of
paths is independent iff these vectors are linearly independent over the rationals (exact Fraction
arithmetic, not parity). Every ENTRY-to-EXIT walk is an integer combination of a basis, whose size is
M = E - N + 2 for the live graph.

Construction (finite even with loops): for every live edge e=(u,v) form the candidate
    prefix(u) + e + suffix(v)
where prefix/suffix are shortest-route trees from ENTRY and to EXIT, plus the shortest ENTRY-to-EXIT
route. These candidates span all walks (a walk W = sum of its edges' candidates minus the node walks
P(x)+S(x) of its interior nodes, and each node walk is the candidate of x's tree edge). Candidates are
accepted greedily when they raise the rank.

Limitations, reported rather than hidden: paths are *structural*; conditions are not solved, so a path
may be infeasible for any input. If EXIT is unreachable, or some reachable node cannot reach EXIT, no
terminating basis exists and none is invented.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .model import CFG
from .reachability import Reachability
from .validation import MAX_BASIS_COMPLEXITY


class _Rank:
    """Incremental exact row-echelon rank over the rationals."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, dict[int, Fraction]]] = []

    def add(self, vec: dict[int, int]) -> bool:
        v = {k: Fraction(x) for k, x in vec.items() if x}
        for pivot, row in self.rows:
            c = v.get(pivot)
            if c:
                for k, x in row.items():
                    nv = v.get(k, 0) - c * x
                    if nv:
                        v[k] = nv
                    else:
                        v.pop(k, None)
        if not v:
            return False
        p = min(v)
        d = v[p]
        self.rows.append((p, {k: x / d for k, x in v.items()}))
        return True

    @property
    def rank(self) -> int:
        return len(self.rows)


def compute(cfg: CFG, reach: Reachability, expected: int) -> dict[str, Any]:
    base = {"convention": "linear independence of edge-usage vectors over the rationals (exact)",
            "expected": expected, "rank": 0, "paths": []}
    if not reach.exit_reachable:
        return {**base, "status": "unavailable", "reason":
                "EXIT is not reachable from ENTRY, so no terminating ENTRY-to-EXIT path exists."}
    if reach.trapped:
        return {**base, "status": "unavailable", "reason":
                f"{len(reach.trapped)} reachable node(s) can never reach EXIT (infinite loop), so a terminating basis cannot be established."}
    if expected > MAX_BASIS_COMPLEXITY:
        return {**base, "status": "skipped", "reason":
                f"Complexity {expected} exceeds the basis-path limit ({MAX_BASIS_COMPLEXITY}); metrics are still valid."}

    by_id = {e.id: e for e in cfg.edges}
    live = [e for e in cfg.edges if e.reachable]
    eidx = {e.id: i for i, e in enumerate(live)}

    def prefix(u: int) -> list[int]:
        route: list[int] = []
        while u != cfg.entry:
            e = by_id[cfg.nodes[u].parent_edge]
            route.append(e.id)
            u = e.src
        route.reverse()
        return route

    def suffix(v: int) -> list[int]:
        route: list[int] = []
        while v != cfg.exit:
            e = by_id[reach.next_to_exit[v]]
            route.append(e.id)
            v = e.dst
        return route

    candidates = [suffix(cfg.entry)] + [prefix(e.src) + [e.id] + suffix(e.dst) for e in live]
    ranker = _Rank()
    chosen: list[list[int]] = []
    for cand in candidates:
        vec: dict[int, int] = {}
        for eid in cand:
            vec[eidx[eid]] = vec.get(eidx[eid], 0) + 1
        if ranker.add(vec):
            chosen.append(cand)
            if ranker.rank == expected:
                break

    paths, used = [], set()
    for i, route in enumerate(chosen, 1):
        nodes = [cfg.entry] + [by_id[e].dst for e in route]
        decisions = []
        for eid in route:
            e = by_id[eid]
            if sum(1 for x in live if x.src == e.src) > 1:
                decisions.append({"node": e.src, "edge": eid, "label": e.label or e.kind})
        paths.append({"index": i, "nodes": nodes, "edges": route, "decisions": decisions,
                      "new_edges": [e for e in dict.fromkeys(route) if e not in used],
                      "repeats_nodes": len(set(nodes)) != len(nodes), "length": len(route)})
        used.update(route)
    status = "complete" if ranker.rank == expected else "partial"
    out = {**base, "status": status, "rank": ranker.rank, "paths": paths}
    if status == "partial":
        out["reason"] = f"Only {ranker.rank} of {expected} independent paths could be constructed."
    return out
