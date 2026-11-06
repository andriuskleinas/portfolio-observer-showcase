#!/usr/bin/env bash
# Runs the API against a separate demo database full of fake data (OSS-02).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PT_DATA_DIR="$ROOT/data/demo"
if [ ! -f "$PT_DATA_DIR/portfolio.db" ]; then
  "$ROOT/scripts/backend.sh" --version >/dev/null 2>&1 || true   # makes sure the venv exists
  (cd "$ROOT/backend" && .venv/bin/python -m app.seed)
fi
exec "$ROOT/scripts/backend.sh" "$@"
