# Convenience targets (macOS / Linux). Plain commands are also listed in README.md.
.PHONY: setup build run dev test test-backend test-frontend test-e2e

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm install
	.venv/bin/python -m playwright install chromium

build:
	cd frontend && npm run build

run: build           ## single process: Flask serves the API and the built UI on http://127.0.0.1:5000
	cd backend && ../.venv/bin/python -m cfg_analyzer

dev:                 ## two processes: Flask on :5000 and Vite (hot reload) on :5173
	(cd backend && ../.venv/bin/python -m cfg_analyzer &) ; cd frontend && npm run dev

test-backend:
	.venv/bin/python -m pytest tests --ignore=tests/e2e
test-frontend:
	cd frontend && npm run typecheck && npm test
test-e2e: build
	.venv/bin/python -m pytest tests/e2e
test: test-backend test-frontend test-e2e
