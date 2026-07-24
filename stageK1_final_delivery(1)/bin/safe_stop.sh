#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
"$ROOT/bin/stop_safe_demo.sh"
echo "ROLLBACK_TARGET=SAFE_STOP_ONLY"
echo "NO_ESP32_ROLLBACK=TRUE"
echo "NO_OLD_MODEL_ROLLBACK=TRUE"

