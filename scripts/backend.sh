#!/usr/bin/env bash
# Runs the API on 127.0.0.1 only. Data lives in ./data unless PT_DATA_DIR says otherwise.
set -euo pipefail
cd "$(dirname "$0")/../backend"
if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e ".[dev]"
fi
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" "$@"
