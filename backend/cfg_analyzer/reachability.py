"""Reachability, shortest paths from ENTRY, dominators and loop (back) edges.

All results are written onto the CFG's nodes/edges so the serializer has one source of truth.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .model import CFG


@dataclass
class Reachability:
    reachable: set[int] = field(default_factory=set)
    can_reach_exit: set[int] = field(default_factory=set)
    unreachable: list[int] = field(default_factory=list)
    trapped: list[int] = field(default_factory=list)       # reachable, but can never reach EXIT
    exit_reachable: bool = False
    back_edges: list[int] = field(default_factory=list)
    irreducible: bool = False
    next_to_exit: dict[int, int] = field(default_factory=dict)  # node -> first edge of a shortest route to EXIT


def analyze(cfg: CFG) -> Reachability:
    out, inc = cfg.adjacency()
    r = Reachability()

    # forward BFS from ENTRY (records shortest structural distance and its last edge)
    dist = {cfg.entry: 0}
    parent: dict[int, int] = {}
    q = deque([cfg.entry])
    while q:
        u = q.popleft()
        for e in out[u]:
            if e.dst not in dist:
                dist[e.dst] = dist[u] + 1
                parent[e.dst] = e.id
                q.append(e.dst)
    r.reachable = set(dist)

    # reverse BFS from EXIT
    back = {cfg.exit}
    q = deque([cfg.exit])
    while q:
        v = q.popleft()
        for e in inc[v]:
            if e.src not in back:
                back.add(e.src)
                r.next_to_exit[e.src] = e.id
                q.append(e.src)
    r.can_reach_exit = back
    r.exit_reachable = cfg.exit in r.reachable

    for nid, n in cfg.nodes.items():
        n.reachable = nid in r.reachable
        n.can_reach_exit = nid in back
        n.distance = dist.get(nid)
        n.parent_edge = parent.get(nid)
    r.unreachable = sorted(set(cfg.nodes) - r.reachable)
    r.trapped = sorted(r.reachable - back)

    for e in cfg.edges:
        e.reachable = e.src in r.reachable

    _loops(cfg, out, r)
    return r


def _dominators(cfg: CFG, out, rpo: list[int]) -> dict[int, int]:
    index = {n: i for i, n in enumerate(rpo)}
    preds: dict[int, list[int]] = {n: [] for n in rpo}
    for n in rpo:
        for e in out[n]:
            if e.dst in index:
                preds[e.dst].append(n)
    idom: dict[int, int] = {cfg.entry: cfg.entry}

    def intersect(a: int, b: int) -> int:
        while a != b:
            while index[a] > index[b]:
                a = idom[a]
            while index[b] > index[a]:
                b = idom[b]
        return a

    changed = True
    while changed:
        changed = False
        for n in rpo[1:]:
            ps = [p for p in preds[n] if p in idom]
            if not ps:
                continue
            new = ps[0]
            for p in ps[1:]:
                new = intersect(p, new)
            if idom.get(n) != new:
                idom[n] = new
                changed = True
    return idom


def _loops(cfg: CFG, out, r: Reachability) -> None:
    """Back edge = edge u->v where v dominates u. Retreating edges that are not back edges mean irreducible flow."""
    # iterative DFS for reverse post-order and retreating edges
    state: dict[int, int] = {}
    order: list[int] = []
    retreating: set[int] = set()
    stack = [(cfg.entry, iter(out[cfg.entry]))]
    state[cfg.entry] = 1
    while stack:
        u, it = stack[-1]
        for e in it:
            if e.dst not in state:
                state[e.dst] = 1
                stack.append((e.dst, iter(out[e.dst])))
                break
            if state[e.dst] == 1:
                retreating.add(e.id)
        else:
            state[u] = 2
            order.append(u)
            stack.pop()
    rpo = list(reversed(order))
    idom = _dominators(cfg, out, rpo)

    def dominates(a: int, b: int) -> bool:
        while True:
            if a == b:
                return True
            if b == cfg.entry or b not in idom:
                return False
            b = idom[b]

    by_id = {e.id: e for e in cfg.edges}
    for e in cfg.edges:
        if e.reachable and e.dst in idom and e.src in idom and dominates(e.dst, e.src):
            e.back_edge = True
            cfg.nodes[e.dst].loop_header = True
            r.back_edges.append(e.id)
    r.irreducible = any(not by_id[i].back_edge for i in retreating)
