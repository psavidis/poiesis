#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

APP_DIR="$ROOT/video-renderer/preview-app"

if [ ! -d "$APP_DIR/node_modules" ]; then
    echo "ERROR: dependencies not installed at $APP_DIR/node_modules"
    echo "Install them first: cd video-renderer/preview-app && npm install"
    exit 1
fi

echo "Starting Poiesis overlay-timing preview at http://127.0.0.1:5173"
echo "(Ctrl+C to stop — the control panel's \"Adjust timing\" links open this app,"
echo "so it needs to stay running alongside ./start_ui.sh)"
echo

cd "$APP_DIR"
exec npm run dev
