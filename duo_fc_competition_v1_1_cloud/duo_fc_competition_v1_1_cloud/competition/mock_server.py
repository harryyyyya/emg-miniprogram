from __future__ import annotations

import argparse
import json
import signal
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PATHS = {
    "/devices/wifi/register",
    "/devices/wifi/heartbeat",
    "/devices/wifi/command/ack",
    "/devices/wifi/emg",
}


class State:
    def __init__(self, audit_path: Path, summary_path: Path, delay_ms: int) -> None:
        self.audit_path = audit_path
        self.summary_path = summary_path
        self.delay_ms = delay_ms
        self.counts: Counter[str] = Counter()
        self.pending_sent = False

    def record(self, path: str, payload: dict[str, Any]) -> None:
        self.counts[path] += 1
        row = {"monotonic_ns": time.monotonic_ns(), "path": path, "payload": payload}
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")

    def summary(self) -> dict[str, Any]:
        return {
            "scope": "LOCAL_MOCK_NOT_REAL_BACKEND",
            "counts": dict(self.counts),
            "emg_upload_count": self.counts["/devices/wifi/emg"],
            "pending_command_sent": self.pending_sent,
        }

    def flush_summary(self) -> None:
        self.summary_path.write_text(json.dumps(self.summary(), indent=2) + "\n", encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DuoCompetitionMock/1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        state: State = self.server.state  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_error(400)
            return
        if self.path not in PATHS or not isinstance(payload, dict):
            self.send_error(404)
            return
        state.record(self.path, payload)
        if state.delay_ms:
            time.sleep(state.delay_ms / 1000.0)
        status = 409 if self.path == "/devices/wifi/emg" else 200
        response: dict[str, Any] = {"ok": status == 200}
        if self.path == "/devices/wifi/heartbeat" and not state.pending_sent:
            response["pending_command"] = {"command_id": "mock-stop-1", "action": "stop_collect"}
            state.pending_sent = True
        body = json.dumps(response, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        state.flush_summary()


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly local Duo competition HTTP mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--delay-ms", type=int, default=0)
    args = parser.parse_args()
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    state = State(args.audit, args.summary, args.delay_ms)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.state = state  # type: ignore[attr-defined]

    def stop(_signum: int, _frame: object) -> None:
        state.flush_summary()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.flush_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

