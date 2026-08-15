#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
fail() { echo "PREFLIGHT=FAIL $*" >&2; exit 1; }

test "$(id -u)" -eq 0 || fail "root required on Duo S"
uname -r | grep -F '5.10.4-tag-' >/dev/null || fail "kernel is not the validated 5.10.4-tag- image"
grep -F 'Buildroot 2025.02' /etc/os-release >/dev/null 2>&1 || fail "Buildroot 2025.02 identity missing"
command -v python3 >/dev/null || fail "python3 missing"
command -v sha256sum >/dev/null || fail "sha256sum missing"
command -v hciattach >/dev/null || fail "hciattach missing"
command -v hciconfig >/dev/null || fail "hciconfig missing"
command -v bluetoothctl >/dev/null || fail "bluetoothctl missing"
command -v gatttool >/dev/null || fail "gatttool missing"
test -r /mnt/system/lib/libcviruntime.so || fail "CVI runtime missing"
test -c /dev/ttyS4 || fail "/dev/ttyS4 missing for HCI"
if grep -qw ttyS4 /proc/cmdline 2>/dev/null || grep -qw ttyS4 /sys/class/tty/console/active 2>/dev/null; then
    fail "/dev/ttyS4 is a console"
fi
ip link show wlan0 >/dev/null 2>&1 || fail "wlan0 missing"
sha256sum -c competition/identity.sha256 || fail "frozen identity mismatch"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT" python3 - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
risk = json.loads((root / "model/RISK_ACCEPTANCE.json").read_text(encoding="utf-8"))
contract = json.loads((root / "duo_s_full_chain/contracts/model_contract.json").read_text(encoding="utf-8"))
assert risk["model_id"] == "duo_fc_mlp_3session_v1_retry2_risk_accepted"
assert risk["quality_gates_passed"] is False
assert contract["quality_gates_passed"] is False
assert contract["risk_acceptance_present"] is True
assert contract["cvimodel_sha256"] == "184f567ab263efc8349e4ce8ca251262bfcda777eab4afefa7f73b494e41e6fa"
assert contract["pipeline_sha256"] == "836a520473ca4bbe857b17501a349a5ff11f385d8593f66970ee4a83021f5273"
assert contract["input_shape"] == [1, 48] and contract["output_shape"] == [1, 9]
print("MODEL_RISK_IDENTITY=PASS quality_gates_passed=false")
PY

uart_sink="${DUO_UART_SINK:-file:$ROOT/logs/uart_mock.bin}"
case "$uart_sink" in
    file:/*) echo "UART_GATE=MOCK_FILE sink=$uart_sink" ;;
    /dev/ttyS0|/dev/ttyS4) fail "reserved UART device forbidden: $uart_sink" ;;
    /dev/*)
        test "${DUO_J3_UART_EVIDENCE:-NOT_PROVEN}" = LIVE_VERIFIED || fail "real UART requested without LIVE_VERIFIED J3 evidence"
        test -c "$uart_sink" || fail "real UART path is not a character device"
        if grep -qw "$(basename "$uart_sink")" /proc/cmdline 2>/dev/null || grep -qw "$(basename "$uart_sink")" /sys/class/tty/console/active 2>/dev/null; then
            fail "requested J3 UART is a console"
        fi
        echo "UART_GATE=LIVE_VERIFIED device=$uart_sink"
        ;;
    *) fail "UART sink must be file:/absolute/path or a verified /dev path" ;;
esac

if test "${DUO_BACKEND_MODE:-mock}" = real; then
    test "${DUO_REAL_BACKEND_GATE:-NOT_PROVEN}" = LIVE_VERIFIED || fail "real backend requested without LIVE_VERIFIED gate"
    case "${DUO_BOARD_TOKEN:-}" in ''|REPLACE_*|LOCAL_MOCK_*) fail "real backend token missing/placeholder" ;; esac
    echo "BACKEND_GATE=LIVE_VERIFIED"
else
    echo "BACKEND_GATE=LOCAL_MOCK_NOT_REAL_BACKEND"
fi

echo "BT11_LIVE_GATE=NOT_RUN_UNLESS_TARGET_IS_ACTUALLY_LOGGED"
echo "ACTUATOR_GATE=NOT_RUN"
echo "PREFLIGHT=PASS"

