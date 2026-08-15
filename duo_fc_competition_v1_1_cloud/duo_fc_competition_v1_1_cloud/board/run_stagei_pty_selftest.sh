#!/bin/sh
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
PACKAGE_ROOT="$(dirname -- "$SCRIPT_DIR")"
OUT_DIR="${1:-/tmp/stagei_pty_selftest_$$}"
mkdir -p "$OUT_DIR" || exit 1

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PACKAGE_ROOT" \
    python3 "$SCRIPT_DIR/probe_stagei_platform.py" pty \
    >"$OUT_DIR/pty_selftest.log" 2>&1
CODE=$?
cat "$OUT_DIR/pty_selftest.log"
echo "PTY_SELFTEST_EXIT=$CODE"
exit "$CODE"
