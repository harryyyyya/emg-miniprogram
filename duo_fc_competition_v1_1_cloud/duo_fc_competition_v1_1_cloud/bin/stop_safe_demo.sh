#!/bin/sh
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
STATE="$ROOT/state"
mkdir -p "$STATE" "$ROOT/logs"

stop_owned_pid() {
    file="$1"
    expected="$2"
    test -f "$file" || return 0
    pid="$(cat "$file")"
    if test -n "$pid" && kill -0 "$pid" 2>/dev/null; then
        cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$cmdline" in
            *"$expected"*) kill "$pid" 2>/dev/null || true ;;
            *) echo "WARN: refusing to kill PID $pid; ownership mismatch" >&2 ;;
        esac
        for _attempt in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
    fi
    rm -f "$file"
}

# Runtime finally emits a sequence-continuous no_stable frame before closing UART.
stop_owned_pid "$STATE/runtime.pid" 'duo_s_full_chain.runtime.main'
stop_owned_pid "$STATE/mock_server.pid" 'competition/mock_server.py'
"$ROOT/bin/hci_stop.sh" || true

echo "SAFE_DEMO_STOP=PASS_OR_WARNINGS_REPORTED"
echo "SAFE_STATE=NO_STABLE_EMITTED_BY_RUNTIME_FINALLY_IF_RUNTIME_WAS_RUNNING"

