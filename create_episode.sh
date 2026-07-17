#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 "$SCRIPT_DIR/pipeline/run_pipeline.py" "$@"