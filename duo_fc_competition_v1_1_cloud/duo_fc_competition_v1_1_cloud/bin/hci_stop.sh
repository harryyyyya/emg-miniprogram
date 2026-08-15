#!/bin/sh
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
STATE="$ROOT/state"
LOGS="$ROOT/logs"
mkdir -p "$STATE" "$LOGS"
bluetoothctl scan off >/dev/null 2>&1 || true

if test -f "$STATE/hciattach.pid"; then
    pid="$(cat "$STATE/hciattach.pid")"
    if test -n "$pid" && kill -0 "$pid" 2>/dev/null; then
        cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$cmdline" in
            *hciattach*'/dev/ttyS4'*) kill "$pid" 2>/dev/null || true ;;
            *) echo "WARN: refusing to kill PID $pid; command is not owned hciattach" >&2 ;;
        esac
    fi
fi
for _attempt in 1 2 3 4 5; do
    test ! -d /sys/class/bluetooth/hci0 && break
    sleep 1
done

if test "$(cat "$STATE/bt_was_soft_blocked" 2>/dev/null || echo 0)" -eq 1; then
    rfkill block bluetooth >/dev/null 2>&1 || true
fi
if test "$(cat "$STATE/btlpm_loaded_by_wrapper" 2>/dev/null || echo 0)" -eq 1; then
    rmmod aic8800_btlpm >/dev/null 2>&1 || true
fi

{
    echo "=== HCI cleanup state ==="
    hciconfig -a 2>/dev/null || true
    lsmod | grep -E 'aic8800_(bsp|fdrv|btlpm)' || true
    ip link show wlan0 || true
} > "$LOGS/hci_stop_state.log" 2>&1

if test -d /sys/class/bluetooth/hci0; then
    echo "HCI_STOP=FAIL hci0_still_present" >&2
    exit 1
fi
rm -f "$STATE/hciattach.pid" "$STATE/bt_was_soft_blocked" "$STATE/btlpm_loaded_by_wrapper"
echo "HCI_STOP=PASS"
