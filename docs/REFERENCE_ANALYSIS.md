# What was taken from each reference (and what was not)

Inspected before any code was written: both ZIPs (source, tests, READMEs, samples) and all 36 pages of the PDF. Test results below are from actually running the reference suites in this environment (Python 3.13, Node 22).

## Reference results (measured, not quoted)

| Reference | Command | Result |
|---|---|---|
| `c-cfg-visualizer.zip` (React, custom JS parser) | `npx vitest run` | **36 passed, 0 failed** (32 engine tests, 4 UI smoke tests) |
| `cfg-analyzer3.zip` (Flask + tree-sitter, 4 languages) | `pytest` | **446 passed, 83 failed.** 75 failures in `test_languages.py`, 5 in `test_ui.py`, 2 in `test_web.py`, 1 in `test_export.py`. Re-running those files showed 76 `ModuleNotFoundError`s for the tree-sitter **Python / Java / C++** grammars (only the C grammar was installed here, because the final project is C-only); the 5 UI tests need Playwright browsers; the 2 `test_web.py` failures return HTTP 500 and were not diagnosed (most likely the same missing grammars). I found no failure caused by C logic, but I did not verify every one. |
| `se project report .pdf` | read in full | Describes a **third** code base (`SE-Project-Independent-Paths.zip`: Flask + **pycparser** + vanilla-JS Dagre, 145 tests). That project is not either ZIP and was not provided, so its 145 passing tests could not be reproduced and are not claimed here. |

## Feature inventory

| Capability | React ref (A) | Flask ref (B) | Report (PDF) | Decision for the final project |
|---|---|---|---|---|
| C parsing | hand-written lexer + recursive-descent parser, good error messages, but a subset that rejects `__attribute__`, K&R, etc. | tree-sitter C | pycparser validation + own lexer | **tree-sitter** (B): complete C grammar, error nodes with positions. Custom parser discarded. |
| CFG construction | AST → linear IR → leaders → blocks (clean textbook pipeline) | *frontier* builder: concise, handles jumps naturally | fragments with entry/open exits, then merge | **Frontier builder** (B's idea, rewritten) for construction + **separate leader-style merge pass** (A's idea). |
| Short-circuit `&&`, `\|\|`, `?:` | one decision per statement (documented weakness) | expanded | expanded (Fig. 3.3) | **Expanded**, with evaluation order; value-context operators handled so M is not over-counted. |
| Switch fall-through, break/continue | yes | yes | yes | Kept, plus labelled fall-through edges and `True · break` style labels. |
| Unreachable code | warns | drops it with a warning | kept, flagged, excluded from live metrics | **Kept and flagged** (PDF): dead code stays visible and cannot be mistaken for a path. |
| Complexity | computed in the **frontend** (`complexity.js`) | Python, decision-counting | Python, E−N+2C, reachable vs full | **Backend only.** `E−N+2P` on the reachable graph + branch formula + independent syntax-tree count; frontend never recomputes. |
| Non-terminating loops | not special-cased | warns | formulas diverge, basis suppressed | PDF's behaviour, with the disagreement explained in the UI. |
| Basis paths | dominator-based "basis set", not verified for independence | rational-rank verified | BFS candidates + **GF(2)** elimination | **B's rational rank** with the PDF's candidate scheme (plus a completeness argument in `ALGORITHMS.md`). GF(2) only detects parity, so it was not used. |
| Interactive graph | React Flow + dagre, minimap, node and edge selection | server-side Graphviz SVG + custom zoom | vanilla JS + Dagre SVG | **React Flow + dagre** (A). Graphviz was dropped (extra system dependency). Loop back edges are re-routed around the outside. |
| Source ↔ graph sync | two-way | node → lines | node details | **Two-way** (A), implemented with CodeMirror line decorations. |
| Exports | PNG/SVG via DOM screenshot, JSON | JSON/HTML/DOT/SVG/PDF | SVG/CSV/TXT | **SVG built from the data** (no screenshot), PNG from that SVG, JSON, Markdown summary. |
| Examples | 13 samples | numbered examples with M | built-in examples | 16 examples with **hand-derived expected values** in a manifest that a test checks. |
| Multi-language, compare versions, test-case suggestions, quality warnings, CLI, HTML report | – | yes | – | **Dropped**: outside the stated problem; the brief asked for one coherent C tool. |
| Reflexive reachability matrix, planar-region count | – | – | yes | **Dropped**: not needed to explain M; would add NetworkX for little value. |
| Report's reference example | – | – | N=17, E=23, V=8, 6 decisions, 8 basis paths | Reproduced exactly (`examples/15_*.c`). |

## Differences you may notice against the report

* The report's default view merges ENTRY/EXIT into blocks (its worked example has N = 7). This project keeps ENTRY and EXIT as separate nodes (the brief requires them), so the same program has N = 9, E = 10. **M is identical (3)**, and the reference example matches the report exactly (N = 17, E = 23) because it has no leading/trailing mergeable statements.
* The report rejects `goto`, labels and `#if`-less preprocessing; this project supports `goto` and reports `#if` inside functions as an error.
