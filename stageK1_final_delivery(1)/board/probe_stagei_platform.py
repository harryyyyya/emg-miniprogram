from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from duo_s_full_chain.runtime.platform_gatttool import GatttoolBlePlatform, GatttoolPtySession, run_bounded_command
from duo_s_full_chain.runtime.transport import SERVICE_UUID, TARGET_NAME


def pty_selftest() -> int:
    disconnects: list[str] = []
    session = GatttoolPtySession(lambda: disconnects.append("disconnect"))
    try:
        session.start()
        transcript = session.command("help", 3.0)
        required = ["connect", "disconnect", "primary", "characteristics", "char-desc", "char-write-req", "mtu"]
        missing = [item for item in required if item not in transcript]
        result = {
            "status": "PASS" if not missing else "FAIL",
            "scope": "PTY_COMMAND_CONTROL_ONLY_NO_HCI_NO_CONNECTION",
            "missing_commands": missing,
            "help_transcript": transcript,
        }
    finally:
        session.close()
    result["disconnect_callback_count"] = len(disconnects)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


def scan_only(raw_log_path: Path) -> int:
    if raw_log_path.exists():
        print(f"refusing to append existing raw command log: {raw_log_path}", file=sys.stderr)
        return 3

    def logged_runner(command: list[str], timeout_seconds: float):
        code, stdout, stderr = run_bounded_command(command, timeout_seconds)
        with raw_log_path.open("a", encoding="utf-8") as handle:
            handle.write("=== COMMAND ===\n")
            handle.write(json.dumps(command) + "\n")
            handle.write(f"EXIT={code}\n")
            handle.write("=== STDOUT ===\n")
            handle.write(stdout)
            if not stdout.endswith("\n"):
                handle.write("\n")
            handle.write("=== STDERR ===\n")
            handle.write(stderr)
            if not stderr.endswith("\n"):
                handle.write("\n")
        return code, stdout, stderr

    platform = GatttoolBlePlatform(command_runner=logged_runner)
    advertisements = list(platform.scan(8))
    target = next(
        (
            item
            for item in advertisements
            if item.name == TARGET_NAME or SERVICE_UUID in {value.lower() for value in item.service_uuids}
        ),
        None,
    )
    result = {
        "status": "PASS",
        "scope": "SCAN_ONLY_NO_CONNECTION",
        "advertisement_count": len(advertisements),
        "advertisements": [
            {
                "address": item.address,
                "name": item.name,
                "service_uuids": list(item.service_uuids),
            }
            for item in advertisements
        ],
        "target_present": target is not None,
        "target_name": TARGET_NAME,
        "target_service": SERVICE_UUID,
        "raw_command_log": str(raw_log_path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("TARGET_PRESENT=" + ("YES" if target is not None else "NO"))
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"pty", "scan"}:
        print("usage: probe_stagei_platform.py pty | scan <raw-command-log>", file=sys.stderr)
        return 2
    if sys.argv[1] == "pty":
        return pty_selftest() if len(sys.argv) == 2 else 2
    return scan_only(Path(sys.argv[2])) if len(sys.argv) == 3 else 2


if __name__ == "__main__":
    raise SystemExit(main())
