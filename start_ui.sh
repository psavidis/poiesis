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

PREVIEW_APP_DIR="$ROOT/video-renderer/preview-app"
PREVIEW_URL="http://127.0.0.1:5173"

if [ ! -d "$PREVIEW_APP_DIR/node_modules" ]; then
    echo "ERROR: preview app dependencies not installed at $PREVIEW_APP_DIR/node_modules"
    echo "Install them first: cd video-renderer/preview-app && npm install"
    exit 1
fi

PREVIEW_PID=""
( cd "$PREVIEW_APP_DIR" && exec npm run dev ) &
PREVIEW_PID=$!
trap '[ -n "$PREVIEW_PID" ] && kill "$PREVIEW_PID" 2>/dev/null' EXIT

cd "$ROOT/ui"

echo "Starting Poiesis backend at http://127.0.0.1:$PORT"
echo "Starting Poiesis at $PREVIEW_URL"
echo "(Ctrl+C to stop both)"
echo

if command -v open >/dev/null 2>&1; then
    ( sleep 1 && open "$PREVIEW_URL" ) &
fi

"$VENV_PYTHON" -m uvicorn server:app --port "$PORT"
