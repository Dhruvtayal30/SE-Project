#!/usr/bin/env bash
# One-command start for macOS/Linux: creates a venv, installs dependencies, builds the UI, runs the server.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
(cd frontend && npm install --no-audit --no-fund && npm run build)
echo "Open http://127.0.0.1:5000"
cd backend && exec ../.venv/bin/python -m cfg_analyzer
