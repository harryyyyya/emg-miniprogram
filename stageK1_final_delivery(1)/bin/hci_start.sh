#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
STATE="$ROOT/state"
LOGS="$ROOT/logs"
mkdir -p "$STATE" "$LOGS"

rollback() {
    "$ROOT/bin/hci_stop.sh" >/dev/null 2>&1 || true
}
trap rollback EXIT
trap 'exit 130' HUP INT TERM

test "$(id -u)" -eq 0 || { echo "FAIL: root required" >&2; exit 10; }
test -c /dev/ttyS4 || { echo "FAIL: /dev/ttyS4 missing" >&2; exit 11; }
if grep -qw ttyS4 /proc/cmdline 2>/dev/null || grep -qw ttyS4 /sys/class/tty/console/active 2>/dev/null; then
    echo "FAIL: /dev/ttyS4 is a console" >&2
    exit 12
fi
test ! -d /sys/class/bluetooth/hci0 || { echo "FAIL: hci0 already exists; wrapper ownership unknown" >&2; exit 13; }
ip link show wlan0 >/dev/null 2>&1 || { echo "FAIL: wlan0 absent" >&2; exit 14; }

printf '0\n' > "$STATE/btlpm_loaded_by_wrapper"
if ! lsmod | grep -q '^aic8800_btlpm '; then
    insmod /mnt/system/ko/aic8800_btlpm.ko
    printf '1\n' > "$STATE/btlpm_loaded_by_wrapper"
fi
if rfkill list bluetooth 2>/dev/null | grep -q 'Soft blocked: yes'; then
    printf '1\n' > "$STATE/bt_was_soft_blocked"
else
    printf '0\n' > "$STATE/bt_was_soft_blocked"
fi
rfkill unblock bluetooth

# Exact Stage G/Stage I proven command. ttyS4 is HCI-only, never J3 UART.
hciattach -n -s 1500000 /dev/ttyS4 any 1500000 flow nosleep > "$LOGS/hciattach.log" 2>&1 &
printf '%s\n' "$!" > "$STATE/hciattach.pid"

ready=0
for _attempt in 1 2 3 4 5; do
    if test -d /sys/class/bluetooth/hci0; then ready=1; break; fi
    sleep 1
done
if test "$ready" -ne 1; then
    echo "FAIL: hci0 not created" >&2
    exit 20
fi
hciconfig hci0 up
hciconfig -a > "$LOGS/hci_start_state.log"
test "$(grep -o 'errors:0' "$LOGS/hci_start_state.log" | wc -l)" -ge 2 || {
    echo "FAIL: HCI RX/TX zero-error evidence missing" >&2
    exit 21
}
ip link show wlan0 >> "$LOGS/hci_start_state.log"
trap - EXIT HUP INT TERM
echo "HCI_START=PASS scope=DUO_S_HCI_NOT_BT11_GATT"
