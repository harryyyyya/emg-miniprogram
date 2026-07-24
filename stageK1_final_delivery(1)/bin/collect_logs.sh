#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo rtc_unknown)"
OUT="${1:-/root/duo_fc_competition_v1_logs_$STAMP.tar.gz}"

# Only logs and non-secret identity/status files are returned. config/local.env is excluded by construction.
tar -czf "$OUT" -C "$ROOT" \
    logs \
    competition/identity.sha256 \
    COMPETITION_STATUS.json \
    RESULT_RETURN_TEMPLATE.md \
    VERSION.json
sha256sum "$OUT" > "$OUT.sha256"
sha256sum -c "$OUT.sha256"
echo "LOG_ARCHIVE=$OUT"
echo "LOG_ARCHIVE_SHA=$OUT.sha256"

