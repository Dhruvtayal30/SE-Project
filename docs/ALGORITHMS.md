# Algorithms and formulas

## 1. CFG construction (`cfg_builder.py`)

A *frontier* is the list of pending edges ("outs") whose destination is not yet known. Creating a node wires the whole frontier into it, then clears it; the statement's own outs become the new frontier.

| Construct | Construction |
|---|---|
| sequence | each simple statement is a node; `frontier = [out(node)]` |
| `if (c) A else B` | `(T, F) = cond(c)`; `frontier = T`; build A; `frontier = F`; build B; `frontier = outsA ∪ outsB` (no else: `F` flows on) |
| `while (c) S` | `head` = first node of `cond(c)`; `frontier = T`; build S; link `frontier ∪ continues → head`; exits = `F ∪ breaks` |
| `do S while (c)` | build S; `frontier ∪= continues`; `cond(c)`; `T → first node of S`; exits = `F ∪ breaks` |
| `for (i; c; u) S` | init node; cond as `while`; after S: `frontier ∪= continues` then update node `u`; `u → head`. `continue` therefore reaches the update, not the condition. |
| `switch (e)`, strict | one SWITCH node; each `case v:` adds an edge `case v` from it; the previous case body's frontier flows into the next label as `fall-through`; no `default` adds `default (no match)`; exits = last body ∪ breaks |
| `switch (e)`, course with default | one binary decision per case label in source order, then one binary default test; True enters that label's body, False advances through the tests, and the final False edge is no-match. Body processing stays in source order, preserving fall-through and breaks. |
| `switch (e)`, course without default | Same graph shape as strict mode. |
| `break` / `continue` | the frontier becomes pending jump edges (a True/False edge keeps its identity and is labelled e.g. `True · break`); frontier = ∅ so following code is unreachable |
| `return e;` | statement node, edge `return` → EXIT; frontier = ∅ |
| `goto L` / `L:` | label node; pending goto edges resolved at the end of the function |
| `exit()`, `abort()`… | statement node, edge `exit()` → EXIT |

**Conditions.** `cond(e)` returns `(T outs, F outs)`:

* `a && b`: `a`'s True flows into `b`; False outs = `a`'s ∪ `b`'s.
* `a || b`: `a`'s False flows into `b`; True outs = `a`'s ∪ `b`'s.
* `!(...)` around a logical expression swaps the outs (De Morgan). A plain `!x` stays one predicate.
* anything else is one DECISION node with `True`/`False` edges.

`&&`/`||` **used as a value** (`x = a && b;`): only the left operand is a decision; the right operand becomes a value arm (like a ternary arm). Otherwise the right operand would get True/False edges to the same node (parallel edges) and over-count M — a bug the randomized test caught during development.

`c ? a : b` becomes a DECISION on `c` plus two arm nodes joined before the statement.

**Constant loop conditions.** Only the literals `1`, non-zero integers and `true` (and an omitted `for` condition) are folded: the loop gets an explicit head node and no False edge. Other constant expressions are not folded.

## 2. Basic blocks (`basic_blocks.py`)

Node *v* is merged into *u* iff `outdeg(u) = 1`, the edge is a plain fall-through, `indeg(v) = 1`, and both are straight-line blocks. ENTRY, EXIT, decisions, switches and loop heads are never merged; labels with several predecessors, loop-body starts and `continue` targets stay leaders automatically. Source ranges of all merged statements are kept. Only plain fall-through edges are removed, so M is unchanged.

## 3. Reachability, loops (`reachability.py`)

* Forward BFS from ENTRY: reachable set, shortest distance, parent edge (`distance`, `parent_edge` per node).
* Reverse BFS from EXIT: nodes that can reach EXIT; *trapped* = reachable but cannot reach EXIT.
* Dominators (Cooper–Harvey–Kennedy). A **back edge** is `u → v` where `v` dominates `u`. A retreating edge that is not a back edge means irreducible flow (reported).

## 4. Cyclomatic complexity (`complexity.py`)

Let the *live graph* be the nodes reachable from ENTRY and the edges leaving them.

The request selects one of two conventions (`course` is the API default; `strict` retains the original
plain-McCabe result). The active value is derived from the entry-reachable graph and displayed with two
substituted formulas:

```
M = E − N + 2P       (N, E and P are measured from the live graph)
M = P_d + 1          (P_d is the active graph's predicate count, grouped by predicate kind)
```

`P_d` is independently counted from the live CFG: binary decision nodes contribute one; a strict or
default-free switch contributes one per `case` edge; a course switch with `default` has one decision
node for each case and one for default. The syntax-tree count is also reported for the whole function,
including unreachable code, as a separate cross-check.

* **Strict:** `else` and `default` add nothing; each `case` label adds one. A switch with *k* case labels contributes *k*, whether or not it has a default.
* **Course:** each `default` label adds one as well. A switch with *k* cases and a default contributes *k+1*. Stacked labels count separately, including a stacked default.
* **Parallel edges and self-loops** are separate edges and count.
* **Unreachable code** is excluded from the headline formulas. Full-graph statistics and the whole-function syntax-tree breakdown are reported separately.
* **Formula mismatch:** every analysis compares the graph and predicate formulas. If unreachable EXIT, a folded literal-true loop, or another graph condition makes them differ, both substitutions remain visible and a `FORMULA_MISMATCH` warning is returned; the disagreement is never hidden.
* **EXIT unreachable** (non-terminating): the graph has no sink, so `E − N + 2P` can exceed a branching/predicate count. The independent-path interpretation no longer applies and basis paths are unavailable. For example, `for (;;) {}` has graph `M=2`; the loop-head convention and selected predicate convention are shown explicitly.
* **Trapped infinite loop inside one branch** (EXIT still reachable): the formulas agree; basis paths are unavailable.
* Both conventions are checked against the graph on 400 randomized programs with default/no-default switches, stacked labels, nesting, fall-through and switches in loops; merging blocks must not change M.

Interpretation bands: 1–10 low, 11–20 moderate, 21–50 high, >50 very high.

## 5. Basis paths (`basis_paths.py`)

Goal: *M* ENTRY→EXIT paths that are linearly independent and span all ENTRY→EXIT walks (finite even with loops).

1. `prefix(u)` = shortest route ENTRY→u (BFS tree); `suffix(v)` = shortest route v→EXIT (reverse BFS tree).
2. Candidates: `suffix(ENTRY)`, then `prefix(u) + e + suffix(v)` for every live edge `e = (u, v)`.
3. Greedily accept a candidate if it raises the **exact rational rank** of the edge-usage vectors (incremental Gaussian elimination with `Fraction`). Stop at rank *M*.

Why this is complete: a walk *W = e₁…e_k* satisfies `Σ cand(eᵢ) = W + Σ_{interior x} (P(x) + S(x))`, and for every `x ≠ ENTRY` the node walk `P(x)+S(x)` equals the candidate of *x*'s BFS-tree edge. So the candidates span every walk and the greedy rank reaches *M*. Tests recompute the rank independently with a dense `Fraction` elimination.

Independence is over ℚ, not GF(2): parity only detects whether an edge is used an odd number of times, and cannot tell the difference between a path that loops once and one that loops twice.

**Limits.** Paths are structural: branch conditions are not solved, so a path may be infeasible for every input. No basis is produced if EXIT is unreachable, if any reachable node cannot reach EXIT, or if M > 120 (metrics are still reported).

## 6. Complexity of the implementation

Building and merging: O(N·E) worst case for the merge pass. Reachability and dominators: near-linear. Basis paths: O(E) candidates × O(M·E) elimination; measured at M = 120 in about 0.2 s. Limits: 100,000 characters, 4,000 lines, 500 displayed nodes.
