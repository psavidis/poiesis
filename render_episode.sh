#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
    echo "Usage: $0 <episode-name>"
    exit 1
fi

EPISODE="$1"

ROOT="$(cd "$(dirname "$0")" && pwd)"

RENDERER="$ROOT/video-renderer"

OUTPUT_DIR="$EPISODE/rendered"

mkdir -p "$OUTPUT_DIR"

OUTPUT="$OUTPUT_DIR/${EPISODE##*/}.mp4"

echo "Rendering episode:"
echo "$EPISODE"

cd "$RENDERER"

npx remotion render \
    Episode \
    "$OUTPUT"

echo
echo "================================"
echo "Render completed"
echo "Output:"
echo "$OUTPUT"
echo "================================"