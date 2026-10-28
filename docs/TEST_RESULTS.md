# Test results

Actual runs on 28 Oct 2026 in this workspace: macOS arm64, Python 3.13.7, pytest 9.2.0, Node 24.14.1,
Vitest 2.1.9, Vite 5.4.21, Playwright 1.64.1 with Chromium 156.

| Suite | Command | Actual result |
|---|---|---|
| Backend | `.venv/bin/python -m pytest tests --ignore=tests/e2e --disable-warnings -o addopts=''` | **562 passed** (4.22 s) |
| Frontend typecheck | `npm run typecheck` in `frontend/` | **passed** (`tsc --noEmit`, exit 0) |
| Frontend unit | `npm test` in `frontend/` | **29 passed** (2 files; 781 ms) |
| Frontend build | `npm run build` in `frontend/` | **passed**; Vite reported the existing large-chunk advisory (822.85 kB JavaScript bundle) |
| Browser end-to-end | `.venv/bin/python -m pytest tests/e2e --disable-warnings --maxfail=1 -o addopts=''` | **20 passed** (13.45 s, Chromium) |

The 400 seeded random-program cases now analyze each generated program under both conventions. They check
the graph/predicate invariant, strict-to-course delta for default-bearing switches, merge invariance, and
path validity. The hand-derived `process` example reports strict M = 10 and course M = 11 in the backend.
