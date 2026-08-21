#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "ERROR: venv not found at $SCRIPT_DIR/.venv"
    echo "Create it first, e.g.: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

"$VENV_PYTHON" "$SCRIPT_DIR/pipeline/run_pipeline.py" "$@"