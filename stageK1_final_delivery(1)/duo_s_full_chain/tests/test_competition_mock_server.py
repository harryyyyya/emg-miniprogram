from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from competition.mock_server import Handler, State


class CompetitionMockServerTests(unittest.TestCase):
    def test_four_paths_pending_ack_and_emg_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = State(root / "audit.jsonl", root / "summary.json", 0)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.state = state  # type: ignore[attr-defined]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def post(path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
                request = urllib.request.Request(
                    base + path,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=2) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            try:
                self.assertEqual(post("/devices/wifi/register", {"hardware_id": "test"})[0], 200)
                status, heartbeat = post("/devices/wifi/heartbeat", {"hardware_id": "test"})
                self.assertEqual(status, 200)
                self.assertEqual(heartbeat["pending_command"]["command_id"], "mock-stop-1")  # type: ignore[index]
                self.assertEqual(post("/devices/wifi/command/ack", {"command_id": "mock-stop-1"})[0], 200)
                self.assertEqual(post("/devices/wifi/emg", {})[0], 409)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["/devices/wifi/register"], 1)
            self.assertEqual(summary["counts"]["/devices/wifi/heartbeat"], 1)
            self.assertEqual(summary["counts"]["/devices/wifi/command/ack"], 1)
            self.assertEqual(summary["emg_upload_count"], 1)
            self.assertEqual(summary["scope"], "LOCAL_MOCK_NOT_REAL_BACKEND")


if __name__ == "__main__":
    unittest.main()
