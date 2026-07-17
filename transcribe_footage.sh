#!/usr/bin/env bash

set -euo pipefail

FORCE=false

if [[ "$#" -lt 1 || "$#" -gt 2 ]]; then
    echo "Usage: $0 <episode-folder> [--force]"
    exit 1
fi

EPISODE_FOLDER="$(cd "$1" && pwd)"

if [[ "${2:-}" == "--force" ]]; then
    FORCE=true
fi

MANIFEST="$EPISODE_FOLDER/processing/manifest.json"
OUTPUT_DIR="$EPISODE_FOLDER/processing/transcripts"

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: Manifest not found:"
    echo "$MANIFEST"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

PROCESSED=0
SKIPPED=0
FAILED=0

echo "Manifest:"
echo "$MANIFEST"
echo

VIDEO_COUNT=$(jq '.videos | length' "$MANIFEST")

echo "Videos found: $VIDEO_COUNT"
echo "Force mode: $FORCE"
echo


for ((i=0; i<VIDEO_COUNT; i++)); do

    ID=$(jq -r ".videos[$i].id" "$MANIFEST")
    FILE=$(jq -r ".videos[$i].path" "$MANIFEST")
    FILENAME=$(jq -r ".videos[$i].filename" "$MANIFEST")

    VIDEO_PATH="$EPISODE_FOLDER/$FILE"
    OUTPUT_FILE="$OUTPUT_DIR/$ID.json"


    if [ ! -f "$VIDEO_PATH" ]; then
        echo "ERROR: Missing video:"
        echo "$VIDEO_PATH"
        FAILED=$((FAILED + 1))
        continue
    fi


    if [ -f "$OUTPUT_FILE" ] && [ "$FORCE" = false ]; then
        echo "[$ID] $FILENAME"
        echo "      skipped (already exists)"
        SKIPPED=$((SKIPPED + 1))
        echo
        continue
    fi


    echo "[$ID] $FILENAME"
    echo "      transcribing..."


    TEMP_DIR="$OUTPUT_DIR/.tmp-$ID"

    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR"


    if whisper \
        "$VIDEO_PATH" \
        --model turbo \
        --language en \
        --output_dir "$TEMP_DIR" \
        --output_format json
    then

        GENERATED_FILE=$(find "$TEMP_DIR" -name "*.json" | head -n 1)

        if [ -n "$GENERATED_FILE" ]; then
            mv "$GENERATED_FILE" "$OUTPUT_FILE"
            PROCESSED=$((PROCESSED + 1))
            echo "      completed"
        else
            echo "      FAILED: no output produced"
            FAILED=$((FAILED + 1))
        fi

    else
        echo "      FAILED: whisper error"
        FAILED=$((FAILED + 1))
    fi


    rm -rf "$TEMP_DIR"

    echo

done


echo "================================"
echo "Transcription summary"
echo "================================"
echo "Processed: $PROCESSED"
echo "Skipped:   $SKIPPED"
echo "Failed:    $FAILED"
echo "================================"


if [ "$FAILED" -gt 0 ]; then
    exit 1
fi