# API

Base URL (single-process mode): `http://127.0.0.1:5000`. All bodies are JSON.

## `POST /api/analyze`

```json
{ "source": "int main(void){ ... }",
  "function": "main",                    // optional; default: main, else the first function
  "convention": "course",                 // optional; "strict" or "course" (default: course)
  "options": { "merge_blocks": true,     // optional; false = one node per statement
               "basis_paths": true } }   // optional
```

### Success (200)

```jsonc
{
  "ok": true, "api_version": "1.0", "convention": "course|strict",
  "function":  { "name", "signature", "start_line", "end_line" },
  "functions": [ { "name", "start_line", "end_line", "complexity": 3|null, "error": null|"…", "selected", "default" } ],
  "graph": {
    "entry": "n0", "exit": "n8",
    "nodes": [ { "id": "n2", "index": 2, "kind": "entry|exit|block|decision|switch",
                 "construct": "if|while|for|do_while|ternary|logical|statement|…", "role": "Decision (if condition)",
                 "explanation": "…", "label": "a > b",
                 "statements": [ { "text", "line", "column", "end_line", "end_column" } ],   // 1-based, character columns
                 "lines": [3],
                 "reachable": true, "can_reach_exit": true, "distance": 2, "parent_edge": "e2",
                 "loop_header": false, "in_degree": 1, "out_degree": 2, "returns": false } ],
    "edges": [ { "id": "e3", "index": 3, "source": "n2", "target": "n3",
                 "kind": "next|true|false|case|default|fallthrough|break|continue|goto|return|noreturn",
                 "label": "True", "via": null|"break"|"continue"|"goto", "back_edge": false, "reachable": true } ]
  },
  "statistics":   { "nodes_total", "edges_total", "nodes_reachable", "nodes_unreachable", "decision_nodes",
                    "switch_nodes", "basic_blocks", "loops", "function_lines" },
  "complexity":   { "value", "convention", "convention_label", "formula", "substituted", "nodes", "edges", "components", "decision_nodes",
                    "branch_contribution", "branch_formula", "branch_substituted", "branch_value",
                    "predicate_formula", "predicate_substituted", "predicate_count", "predicate_breakdown", "predicate_value", "formulas_agree",
                    "structural": { "value", "decisions", "breakdown", "agrees", "scope" },
                    "full_graph": { "nodes", "edges", "components", "value" },
                    "interpretation": { "band", "label", "text" },
                    "applicability": [ { "code", "message" } ] },
  "reachability": { "exit_reachable", "unreachable_nodes", "trapped_nodes", "back_edges", "irreducible", "reachable_percent" },
  "paths":        { "status": "complete|partial|unavailable|skipped|disabled", "reason", "convention",
                    "expected", "rank",
                    "paths": [ { "index", "nodes", "edges", "length", "repeats_nodes", "new_edges",
                                 "decisions": [ { "node", "edge", "label" } ] } ] },
  "warnings":     [ { "code", "severity": "info|warning|error", "message", "line", "column", "node" } ],
  "source_map":   { "line_to_nodes": { "3": ["n2"] } },
  "assumptions":  [ "…" ]
}
```

### Errors

```json
{ "ok": false, "error": { "code": "SYNTAX_ERROR", "message": "…", "locations": [ { "line": 2, "column": 12, "message": "missing ';'" } ], "details": {} } }
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `MALFORMED_JSON`, `INVALID_REQUEST`, `EMPTY_SOURCE`, `INVALID_SOURCE` | body is not JSON / wrong types / blank source / NUL bytes / convention other than `strict` or `course` |
| 404, 405 | `NOT_FOUND`, `METHOD_NOT_ALLOWED` | unknown route / wrong method |
| 413 | `SOURCE_TOO_LARGE` | more than 100,000 characters or 4,000 lines |
| 422 | `SYNTAX_ERROR` | syntax error inside the analysed function (all error locations listed) |
| 422 | `UNSUPPORTED_CONSTRUCT` | construct that cannot be represented (see SUPPORTED_C.md) |
| 422 | `FUNCTION_NOT_FOUND` | no function in the source, or the requested name is absent (`details.available`) |
| 422 | `GRAPH_TOO_LARGE`, `TOO_DEEP` | more than 500 displayed nodes / nesting too deep |
| 500 | `INTERNAL_ERROR` | unexpected failure; generic message, traceback only in the server log |

## `GET /api/examples`
Returns `{ "examples": [ { id, title, description, function, source, expected: { nodes, edges, reachable_nodes, complexity, course_complexity, decision_nodes, exit_reachable, basis_status } } ] }`. `complexity` is the strict value; `course_complexity` is the course value (where it differs). The hand-derived examples are checked in both conventions by `tests/test_examples.py`.

## `GET /api/health`
`{ "ok": true, "api_version": "1.0" }`.
