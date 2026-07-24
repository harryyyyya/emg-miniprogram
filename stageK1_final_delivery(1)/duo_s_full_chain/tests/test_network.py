from __future__ import annotations

import threading
import time
import unittest
import statistics
from typing import Any

import numpy as np

from duo_s_full_chain.runtime.engine import FullChainRuntime, RuntimeConfig
from duo_s_full_chain.runtime.events import StructuredLogger
from duo_s_full_chain.runtime.model import CallableModelBackend, ModelContract
from duo_s_full_chain.runtime.modes import RuntimeMode
from duo_s_full_chain.runtime.network import DeploymentIdentity, NetworkWorker
from duo_s_full_chain.runtime.snapshot import RuntimeSnapshot, SnapshotStore

from helpers import make_frame


class ScriptedHttp:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None, delay: float = 0.0) -> None:
        self.responses = responses or {}
        self.delay = delay
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.started = threading.Event()

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[int, dict[str, Any]]:
        self.started.set()
        self.requests.append((path, payload))
        if self.delay:
            time.sleep(self.delay)
        return 200, dict(self.responses.get(path, {}))


def worker(http: ScriptedHttp, upload: bool = False) -> NetworkWorker:
    identity = DeploymentIdentity("DUO-S-TEST", "placeholder", "test", "127.0.0.1", 80, "model", "pipeline")
    return NetworkWorker(http, identity, SnapshotStore(RuntimeSnapshot()), StructuredLogger(), enable_emg_upload=upload, heartbeat_interval_s=0.01, timeout_s=0.5)


class NetworkTests(unittest.TestCase):
    def test_four_paths_and_safe_mode_does_not_upload(self) -> None:
        http = ScriptedHttp({"/devices/wifi/heartbeat": {"pending_command": {"command_id": "c1", "action": "start_collect", "payload": {"session_id": "s1"}}}})
        network = worker(http, upload=False)
        network.tick_once()
        self.assertEqual([path for path, _ in http.requests], ["/devices/wifi/register", "/devices/wifi/heartbeat", "/devices/wifi/command/ack"])
        self.assertFalse(network.collecting)
        self.assertFalse(network.queue_emg({"session_id": "s1", "samples": []}))
        self.assertNotIn("/devices/wifi/emg", [path for path, _ in http.requests])
        for _, payload in http.requests:
            self.assertIn("hardware_id", payload)

    def test_upload_mode_has_emg_path_and_stop_ack(self) -> None:
        responses = {"/devices/wifi/heartbeat": {"pending_command": {"command_id": "c1", "action": "start_collect", "payload": {"session_id": "s1"}}}}
        http = ScriptedHttp(responses)
        network = worker(http, upload=True)
        network.tick_once()
        self.assertTrue(network.collecting)
        self.assertTrue(network.queue_emg({"session_id": "s1", "gesture_name": "gesture_1", "sample_rate_hz": 500, "sequence_no": 0, "is_final": False, "samples": [[127] * 8]}))
        http.responses["/devices/wifi/heartbeat"] = {"pending_command": {"command_id": "c2", "action": "stop_collect"}}
        network.tick_once()
        self.assertFalse(network.collecting)
        self.assertIn("/devices/wifi/emg", [path for path, _ in http.requests])
        ack_ids = [payload["command_id"] for path, payload in http.requests if path == "/devices/wifi/command/ack"]
        self.assertEqual(ack_ids, ["c1", "c2"])

    def test_slow_http_worker_does_not_block_signal_thread(self) -> None:
        def measure(with_slow_http: bool) -> tuple[float, int, int, int]:
            http = ScriptedHttp(delay=0.2)
            backend = CallableModelBackend(lambda _: np.arange(9, dtype=np.float32), ModelContract("host", "none", "pipeline", 1.0))
            runtime = FullChainRuntime(backend, config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST))
            runtime.start(0)
            runtime.on_source_connected("recorded", 0)
            network = None
            if with_slow_http:
                identity = DeploymentIdentity("DUO-S-TEST", "placeholder", "test", "127.0.0.1", 80, "host", "pipeline")
                network = NetworkWorker(http, identity, runtime.snapshots, StructuredLogger(), heartbeat_interval_s=0.01)
                network.start()
                self.assertTrue(http.started.wait(1.0))
            started = time.perf_counter()
            for index in range(20):
                runtime.notification_callback(make_frame(index * 20))
                runtime.poll(index)
            elapsed = time.perf_counter() - started
            snapshot = runtime.snapshots.get()
            if network is not None:
                network.stop()
            return elapsed, snapshot.valid_frames, snapshot.inference_count, len(http.requests)

        # An absolute host-time threshold was invalid on Duo S: a returned
        # five-run diagnostic measured 0.210199472 s without any network
        # worker and 0.214607280 s with a real 200 ms mock HTTP stall. Compare
        # paired work instead; a serialized stall would add about 0.2 s.
        baseline = [measure(False) for _ in range(3)]
        slow_http = [measure(True) for _ in range(3)]
        baseline_median = statistics.median(item[0] for item in baseline)
        slow_median = statistics.median(item[0] for item in slow_http)
        self.assertLess(slow_median - baseline_median, 0.05)
        self.assertTrue(all(item[1] == 20 and item[2] > 0 for item in baseline + slow_http))
        self.assertTrue(all(item[3] >= 1 for item in slow_http))


if __name__ == "__main__":
    unittest.main()
