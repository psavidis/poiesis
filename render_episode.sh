#!/usr/bin/env bash

set -euo pipefail

usage() {
    echo "Usage: $0 <episode-name> [WIDTHxHEIGHT] [--transparent]"
    echo "  e.g. $0 /path/to/episode 3840x2160"
    echo "  e.g. $0 /path/to/episode --transparent"
    echo
    echo "  --transparent  Render presenter + overlays only (no background/intro/outro/music)"
    echo "                 as an alpha-preserving ProRes 4444 .mov, meant to be composited"
    echo "                 with background/intro/outro/music in DaVinci Resolve. Requires"
    echo "                 keyed presenter footage (key_footage.py) to actually be transparent"
    echo "                 — see the README for the full finishing workflow."
    exit 1
}

EPISODE=""
RESOLUTION=""
TRANSPARENT=false

for arg in "$@"; do
    case "$arg" in
        --transparent)
            TRANSPARENT=true
            ;;
        *)
            if [[ -z "$EPISODE" ]]; then
                EPISODE="$arg"
            elif [[ -z "$RESOLUTION" ]]; then
                RESOLUTION="$arg"
            else
                usage
            fi
            ;;
    esac
done

if [[ -z "$EPISODE" ]]; then
    usage
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"

RENDERER="$ROOT/video-renderer"

OUTPUT_DIR="$EPISODE/rendered"

mkdir -p "$OUTPUT_DIR"

if [[ "$TRANSPARENT" == true ]]; then
    OUTPUT="$OUTPUT_DIR/${EPISODE##*/}-transparent.mov"
else
    OUTPUT="$OUTPUT_DIR/${EPISODE##*/}.mp4"
fi

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

if [[ "$TRANSPARENT" == true ]]; then
    # image-format must be png for a transparent pixel format — the project
    # default (remotion.config.ts) is jpeg, which silently produces an
    # opaque render if not overridden here.
    RENDER_ARGS+=(--codec=prores --prores-profile=4444 --pixel-format=yuva444p10le --image-format=png)

    # --props does a shallow merge onto defaultProps (verified against
    # remotion's ResolveCompositionConfig: props: {...defaultProps,
    # ...cliInputProps}), so this only overrides backgroundVideo and leaves
    # width/height/videos/assets/scenePlan untouched. Without this,
    # episodes that have a backgroundVideo configured (common — see
    # manifest.json) would still render with an opaque background baked in,
    # defeating the point of a transparent master.
    RENDER_ARGS+=(--props='{"backgroundVideo": null}')

    echo "Transparent master: presenter + overlays only, ProRes 4444 alpha"
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
