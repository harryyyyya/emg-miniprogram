#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CONFIG="${DUO_CONFIG:-$ROOT/config/mock.env}"
test -r "$CONFIG" || { echo "FAIL: config not readable: $CONFIG" >&2; exit 2; }
set -a
. "$CONFIG"
set +a

mkdir -p "$ROOT/logs" "$ROOT/state"
test ! -f "$ROOT/state/runtime.pid" || { echo "FAIL: runtime.pid already exists; run stop first" >&2; exit 3; }

export DUO_MODEL_CONTRACT="$ROOT/duo_s_full_chain/contracts/model_contract.json"
export DUO_CVIMODEL_PATH="$ROOT/model/duo_fc_mlp_3session_v1_retry2_risk_accepted.cvimodel"
export DUO_PREPROCESS_PATH="$ROOT/model/preprocess.json"
export DUO_FEATURE_LIB="$ROOT/build/libduo_emg_features.so"
export DUO_BLE_PLATFORM_MODULE=duo_s_full_chain.runtime.platform_gatttool
export DUO_RUNTIME_VERSION=duo-fc-competition-v1.1
export DUO_MODE=FULL_CHAIN_SAFE_DEMO

cleanup_failure() {
    "$ROOT/bin/stop_safe_demo.sh" >/dev/null 2>&1 || true
}
trap cleanup_failure HUP INT TERM

"$ROOT/bin/preflight.sh" | tee "$ROOT/logs/preflight.log"

if test "${DUO_BACKEND_MODE:-mock}" = mock; then
    PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/competition/mock_server.py" \
        --audit "$ROOT/logs/mock_http.jsonl" \
        --summary "$ROOT/logs/mock_http_summary.json" \
        --delay-ms "${DUO_MOCK_DELAY_MS:-0}" \
        > "$ROOT/logs/mock_server.log" 2>&1 &
    printf '%s\n' "$!" > "$ROOT/state/mock_server.pid"
    sleep 1
    kill -0 "$!" 2>/dev/null || { echo "FAIL: mock server did not start" >&2; cleanup_failure; exit 4; }
fi

"$ROOT/bin/hci_start.sh" | tee "$ROOT/logs/hci_wrapper_start.log"

LD_LIBRARY_PATH="/mnt/system/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT" \
python3 -m duo_s_full_chain.runtime.main --mode FULL_CHAIN_SAFE_DEMO \
    > "$ROOT/logs/runtime.jsonl" 2> "$ROOT/logs/runtime.stderr.log" &
printf '%s\n' "$!" > "$ROOT/state/runtime.pid"
sleep 2
kill -0 "$!" 2>/dev/null || { echo "FAIL: runtime exited during startup" >&2; cleanup_failure; exit 5; }

trap - HUP INT TERM
echo "SAFE_DEMO_START=PASS"
echo "EVIDENCE_BOUNDARY=BT11_LIVE_NOT_RUN_UNTIL_REAL_TARGET_LOG_EXISTS"
echo "UART_SINK=$DUO_UART_SINK"
echo "BACKEND_MODE=${DUO_BACKEND_MODE:-mock}"
