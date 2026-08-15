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

URL="http://127.0.0.1:$PORT"

PREVIEW_APP_DIR="$ROOT/video-renderer/preview-app"
PREVIEW_PID=""

if [ -d "$PREVIEW_APP_DIR/node_modules" ]; then
    ( cd "$PREVIEW_APP_DIR" && exec npm run dev ) &
    PREVIEW_PID=$!
    trap '[ -n "$PREVIEW_PID" ] && kill "$PREVIEW_PID" 2>/dev/null' EXIT
else
    echo "WARNING: preview app dependencies not installed at $PREVIEW_APP_DIR/node_modules"
    echo "Skipping overlay-timing preview (install with: cd video-renderer/preview-app && npm install)"
fi

cd "$ROOT/ui"

echo "Starting Poiesis Control Panel at $URL"
echo "(Ctrl+C to stop)"
echo

if command -v open >/dev/null 2>&1; then
    ( sleep 1 && open "$URL" ) &
fi

"$VENV_PYTHON" -m uvicorn server:app --port "$PORT"
