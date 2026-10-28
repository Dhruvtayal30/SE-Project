# Supported C, unsupported C, known limitations

The tool targets a documented, useful subset of C; it is not a compiler. The program is parsed with tree-sitter and **never compiled or executed**.

## Supported (each covered by automated tests)

* Function definitions (several per file; select one, `main` is the default), any return type including pointers, `static`, `inline`.
* Declarations with or without initialisers, arrays, structs/unions/enums/typedefs inside functions, comments, string/char literals (keywords inside strings and comments are ignored because analysis is syntax-tree based).
* `if`, `if/else`, `else if` chains, nested conditionals.
* `while`, `do-while`, `for` (with declaration or expression init, any part omitted), nested loops, empty bodies.
* `switch` / `case` / `default`: dispatch edges, fall-through, stacked labels, `default` anywhere, no `default`, `break` leaving the switch only.
* Two selectable complexity conventions: `strict` keeps plain McCabe counting (a default is not a decision); `course` counts each default label as one predicate and builds default-bearing switches as binary label-test chains.
* `break`, `continue` (for-loops continue at the update expression), `return` (any number; one shared EXIT).
* `&&`, `||`, `!`, `?:` expanded into decisions with C evaluation order and precedence, in conditions and in value contexts; operators inside `sizeof` are not evaluated.
* `goto` and labels (backward and forward); loops formed with goto get back edges via dominators.
* `exit()`, `abort()`, `_Exit()`, `quick_exit()`, `pthread_exit()` as expression statements go straight to EXIT.
* Literal-true loops: `while (1)`, `while (true)`, `do … while (1)`, `for (;;)`.
* Unreachable code after `return`/`break`/`continue`/`goto`/infinite loops: kept, dashed, excluded from M, warned.
* Inline `asm` as one opaque statement (info).

## Reported as errors (no graph is produced)

| Construct | Why |
|---|---|
| Syntax errors inside the analysed function | the tree would be guesswork; line/column listed |
| `#if` / `#ifdef` / `#else` inside a function body | the tool does not evaluate preprocessor conditions, so it cannot know which branch exists |
| GNU statement expressions `({ ... })`, nested functions | their control flow cannot be represented |
| computed goto, GNU case ranges (`case 1 ... 5`) | reported as syntax errors by the parser |
| `case` labels nested inside another statement of a switch (Duff's device) | not modelled |
| `break`/`continue` outside a loop/switch, `goto` to an undefined label, duplicate labels | invalid C |
| Input larger than the limits | 100,000 characters, 4,000 lines, 500 displayed nodes |

## Reported as warnings / info (graph is produced)

`#define`/`#include`/`#pragma` inside a function (ignored); macros whose replacement text contains `return`/`goto`/`break`/`continue` and are used in the function (their control flow is **not** in the graph); `setjmp`/`longjmp`; `goto`; inline asm; syntax errors in *other* functions of the file; constant loop conditions; `exit()`-style calls; unreachable code; unreachable EXIT; irreducible flow.

## Known limitations

* **Macros are never expanded**; function-like macros are treated as calls. Preprocessing is not performed, so macro-heavy code can produce syntax errors.
* **Intra-procedural only**: calls are single statements; recursion and callee control flow are not modelled.
* **Constant conditions** are folded only for the literal-true loop forms listed above. `if (0)`, `while (0)`, `1 == 1`, constants hidden behind macros or `const` variables are treated as ordinary decisions.
* **Basis paths are structural.** Conditions are not solved; a listed path can be infeasible for every input. The tool does not generate test data.
* `setjmp`/`longjmp`, signals, exceptions-by-library and other non-local transfers are not modelled.
* Switch `case` constants are not evaluated (duplicate or impossible labels are not detected).
* Column numbers count characters; tabs count as one character.
* Tested only with Chromium (see TEST_RESULTS.md); layout of very large graphs (hundreds of nodes) is readable only with zoom.
