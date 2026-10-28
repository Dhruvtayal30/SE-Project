"""Basic-block construction and final numbering.

`compact` is the textbook merge: node v is absorbed into u when the only way out of u is a plain
fall-through edge to v and the only way into v is that edge (i.e. v is not a leader). Decisions,
switches, ENTRY/EXIT, loop heads and anything with several predecessors or successors are leaders
and are never merged. Merging removes only plain fall-through edges, so cyclomatic complexity is
unchanged by it (verified by tests).
"""

from __future__ import annotations

from . import model as m
from .model import CFG

_NO_MERGE = {"loop_head"}


def compact(cfg: CFG) -> None:
    out, inc = cfg.adjacency()
    alias: dict[int, int] = {}
    changed = True
    while changed:
        changed = False
        for uid in sorted(cfg.nodes):
            u = cfg.nodes.get(uid)
            if u is None or u.kind != m.BLOCK or u.construct in _NO_MERGE:
                continue
            while len(out[uid]) == 1:
                e = out[uid][0]
                v = cfg.nodes[e.dst]
                if (e.kind != m.NEXT or e.dst == uid or v.kind != m.BLOCK or v.construct in _NO_MERGE
                        or len(inc[v.id]) != 1):
                    break
                u.stmts.extend(v.stmts)
                u.construct = "block"
                out[uid] = out[v.id]
                for oe in out[uid]:
                    oe.src = uid
                alias[v.id] = uid
                cfg.edges.remove(e)
                del cfg.nodes[v.id], out[v.id], inc[v.id]
                changed = True
    for d in cfg.diagnostics:
        while d.node in alias:
            d.node = alias[d.node]


def renumber(cfg: CFG) -> None:
    """Deterministic ids: ENTRY = 0, other nodes by source position, EXIT last; edges by (source, creation)."""
    others = sorted((n for n in cfg.nodes.values() if n.kind not in (m.ENTRY, m.EXIT)),
                    key=lambda n: (n.start_key, n.id))
    order = [cfg.nodes[cfg.entry]] + others + [cfg.nodes[cfg.exit]]
    remap = {n.id: i for i, n in enumerate(order)}
    for n in order:
        n.id = remap[n.id]
    cfg.nodes = {n.id: n for n in order}
    for e in cfg.edges:
        e.src, e.dst = remap[e.src], remap[e.dst]
    cfg.edges.sort(key=lambda e: (e.src, e.id))
    for i, e in enumerate(cfg.edges, 1):
        e.id = i
    for d in cfg.diagnostics:
        if d.node is not None:
            d.node = remap.get(d.node)
    cfg.entry, cfg.exit = 0, len(order) - 1
