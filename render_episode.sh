#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -lt 1 || "$#" -gt 2 ]]; then
    echo "Usage: $0 <episode-name> [WIDTHxHEIGHT]"
    echo "  e.g. $0 /path/to/episode 3840x2160"
    exit 1
fi

EPISODE="$1"
RESOLUTION="${2:-}"

ROOT="$(cd "$(dirname "$0")" && pwd)"

RENDERER="$ROOT/video-renderer"

OUTPUT_DIR="$EPISODE/rendered"

mkdir -p "$OUTPUT_DIR"

OUTPUT="$OUTPUT_DIR/${EPISODE##*/}.mp4"

RENDER_ARGS=(Episode "$OUTPUT")

if [[ -n "$RESOLUTION" ]]; then
    WIDTH="${RESOLUTION%x*}"
    HEIGHT="${RESOLUTION#*x}"

    if [[ ! "$RESOLUTION" =~ ^[0-9]+x[0-9]+$ ]]; then
        echo "ERROR: resolution must be WIDTHxHEIGHT, e.g. 3840x2160"
        exit 1
    fi

    RENDER_ARGS+=(--width="$WIDTH" --height="$HEIGHT")

    echo "Resolution override: ${WIDTH}x${HEIGHT}"
fi

echo "Rendering episode:"
echo "$EPISODE"

cd "$RENDERER"

npx remotion render "${RENDER_ARGS[@]}"

echo
echo "================================"
echo "Render completed"
echo "Output:"
echo "$OUTPUT"
echo "================================"