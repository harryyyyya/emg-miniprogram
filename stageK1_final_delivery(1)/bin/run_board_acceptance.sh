#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
OUT="${1:-$ROOT/logs/acceptance_$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo unknown)_$$}"
test ! -e "$OUT" || { echo "FAIL: output already exists: $OUT" >&2; exit 2; }
mkdir -p "$OUT"
cd "$ROOT"

cleanup() {
    "$ROOT/bin/hci_stop.sh" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

DUO_UART_SINK="file:$OUT/uart_contract.bin" \
DUO_J3_UART_EVIDENCE=NOT_PROVEN \
DUO_BACKEND_MODE=mock \
    "$ROOT/bin/preflight.sh" > "$OUT/preflight.log" 2>&1

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT" \
python3 -m unittest discover -s duo_s_full_chain/tests -v \
    > "$OUT/unittest.log" 2>&1

cycle=1
while test "$cycle" -le 10; do
    cycle_dir="$OUT/cycle_$cycle"
    mkdir -p "$cycle_dir"
    "$ROOT/bin/hci_start.sh" > "$cycle_dir/hci_start.log" 2>&1
    cp "$ROOT/logs/hci_start_state.log" "$cycle_dir/hci_start_state.log"

    set +e
    LD_LIBRARY_PATH="/mnt/system/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT" \
    python3 -m duo_s_full_chain.runtime.board_replay \
        --recording fixtures/demo_sequence.bin \
        --expected reference/recorded_bf16_reference.json \
        --model-contract duo_s_full_chain/contracts/model_contract.json \
        --cvimodel model/duo_fc_mlp_3session_v1_retry2_risk_accepted.cvimodel \
        --preprocess model/preprocess.json \
        --feature-lib build/libduo_emg_features.so \
        --runtime-lib /mnt/system/lib/libcviruntime.so \
        --rounds 1 \
        --output "$cycle_dir/replay.json" \
        > "$cycle_dir/replay.stdout.log" 2>&1
    replay_code=$?
    set -e

    "$ROOT/bin/hci_stop.sh" > "$cycle_dir/hci_stop.log" 2>&1
    cp "$ROOT/logs/hci_stop_state.log" "$cycle_dir/hci_stop_state.log"
    test "$replay_code" -eq 0 || { echo "FAIL: cycle $cycle replay exit=$replay_code" >&2; exit "$replay_code"; }
    test ! -d /sys/class/bluetooth/hci0 || { echo "FAIL: cycle $cycle leaked hci0" >&2; exit 30; }
    cycle=$((cycle + 1))
done

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/competition/summarize_acceptance.py" "$OUT"
trap - EXIT HUP INT TERM
echo "BOARD_ACCEPTANCE=PASS"
echo "SCOPE=RECORDED_REPLAY_AND_HCI_LIFECYCLE_NOT_BT11_NOT_STM32_NOT_REAL_BACKEND_NOT_ACTUATOR"
