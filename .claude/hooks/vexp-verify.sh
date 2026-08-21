#!/bin/bash
# vexp-verify: mechanical completion gate on Stop (Horizon). Fails open.
VEXP_BIN="/opt/homebrew/lib/node_modules/vexp-cli/node_modules/@vexp/core-darwin-arm64/bin/vexp-core"
[ -x "$VEXP_BIN" ] || exit 0
"$VEXP_BIN" stop-gate 2>/dev/null
exit 0
