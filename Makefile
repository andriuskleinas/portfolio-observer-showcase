.PHONY: setup start demo api web test build

# Install backend (Python venv) and frontend (npm) dependencies
setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev]"
	npm --prefix frontend install

# One command: build the web app and serve everything from http://127.0.0.1:8000
start: build
	./scripts/backend.sh

# Same, against a separate database full of fake data (data/demo)
demo: build
	./scripts/demo.sh

# Development: run these two in separate terminals, then open http://127.0.0.1:5173
api:
	./scripts/backend.sh --reload
web:
	npm --prefix frontend run dev

build:
	npm --prefix frontend run build

test:
	cd backend && .venv/bin/pytest -q
	npm --prefix frontend run typecheck
