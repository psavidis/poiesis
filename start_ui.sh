#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

PORT="${1:-8000}"

VENV_PYTHON="$ROOT/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "ERROR: venv not found at $ROOT/.venv"
    echo "Create it first, e.g.: python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn"
    exit 1
fi

cd "$ROOT/ui"

URL="http://127.0.0.1:$PORT"

echo "Starting Poiesis Control Panel at $URL"
echo "(Ctrl+C to stop)"
echo

if command -v open >/dev/null 2>&1; then
    ( sleep 1 && open "$URL" ) &
fi

exec "$VENV_PYTHON" -m uvicorn server:app --port "$PORT"
