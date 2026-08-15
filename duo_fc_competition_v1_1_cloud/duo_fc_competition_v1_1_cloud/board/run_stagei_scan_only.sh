#!/bin/sh
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
PACKAGE_ROOT="$(dirname -- "$SCRIPT_DIR")"
OUT_DIR="${1:-/tmp/stagei_scan_only_$$}"
if [ -e "$OUT_DIR" ]; then
    echo "ABORT: evidence directory already exists: $OUT_DIR" >&2
    exit 2
fi
mkdir -p "$OUT_DIR" || exit 1
LOG="$OUT_DIR/scan_only.log"
exec >>"$LOG" 2>&1

BTLPM_LOADED_BY_TEST=0
BT_WAS_SOFT_BLOCKED=0
HCIATTACH_PID=""
CLEANED_UP=0

cleanup() {
    if [ "$CLEANED_UP" -eq 1 ]; then
        return
    fi
    CLEANED_UP=1
    echo "=== cleanup ==="
    bluetoothctl scan off 2>/dev/null || true
    if [ -n "$HCIATTACH_PID" ] && kill -0 "$HCIATTACH_PID" 2>/dev/null; then
        kill "$HCIATTACH_PID" 2>/dev/null || true
        wait "$HCIATTACH_PID" 2>/dev/null || true
    fi
    if [ "$BT_WAS_SOFT_BLOCKED" -eq 1 ]; then
        rfkill block bluetooth 2>/dev/null || true
    fi
    if [ "$BTLPM_LOADED_BY_TEST" -eq 1 ]; then
        rmmod aic8800_btlpm 2>/dev/null || true
    fi
    echo "=== post-cleanup ==="
    lsmod | grep -E 'aic8800_(bsp|fdrv|btlpm)' || true
    ip link show wlan0 || true
    hciconfig -a 2>/dev/null || true
    test ! -d /sys/class/bluetooth/hci0 && echo "POST_HCI0_ABSENT=PASS" || echo "POST_HCI0_ABSENT=FAIL"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

echo "EVIDENCE_DIR=$OUT_DIR"
echo "=== preflight ==="
uname -a
cat /etc/os-release 2>/dev/null || true
test -c /dev/ttyS4 || { echo "ABORT: /dev/ttyS4 absent/not char device"; exit 10; }
if grep -qw 'ttyS4' /proc/cmdline 2>/dev/null || grep -qw 'ttyS4' /sys/class/tty/console/active 2>/dev/null; then
    echo "ABORT: ttyS4 is a console"
    exit 11
fi
if hciconfig hci0 >/dev/null 2>&1 || test -d /sys/class/bluetooth/hci0; then
    echo "ABORT: hci0 already exists; baseline is not clean"
    exit 12
fi
ip link show wlan0 || { echo "ABORT: wlan0 absent"; exit 13; }

if ! lsmod | grep -q '^aic8800_btlpm '; then
    insmod /mnt/system/ko/aic8800_btlpm.ko || exit 20
    BTLPM_LOADED_BY_TEST=1
fi
if rfkill list bluetooth 2>/dev/null | grep -q 'Soft blocked: yes'; then
    BT_WAS_SOFT_BLOCKED=1
fi
rfkill unblock bluetooth || exit 21

echo "=== Stage G authoritative attach command ==="
hciattach -n -s 1500000 /dev/ttyS4 any 1500000 flow nosleep >"$OUT_DIR/hciattach.log" 2>&1 &
HCIATTACH_PID=$!
sleep 3
test -d /sys/class/bluetooth/hci0 || { echo "FAIL: hci0 not created"; exit 30; }
hciconfig hci0 up || exit 31
hciconfig -a

echo "=== adapter scan only ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PACKAGE_ROOT" \
    python3 "$SCRIPT_DIR/probe_stagei_platform.py" scan "$OUT_DIR/raw_bluetoothctl_commands.log"
SCAN_CODE=$?
echo "ADAPTER_SCAN_EXIT=$SCAN_CODE"
exit "$SCAN_CODE"
