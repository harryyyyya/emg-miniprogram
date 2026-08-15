from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .engine import FullChainRuntime, RuntimeConfig
from .events import StructuredLogger
from .model import ModelContract, ReplayLogitBackend
from .modes import RuntimeMode
from .network import DeploymentIdentity, NetworkWorker
from .transport import RecordedByteSource
from .uart import MemoryUartSink


class MemoryHttpAdapter:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[int, dict[str, Any]]:
        self.requests.append((path, payload))
        return 200, {}


def run_replay(blob: bytes, expected_rows: list[dict[str, Any]], margin_threshold: float = 1.0) -> tuple[dict[str, Any], FullChainRuntime]:
    contract = ModelContract(
        model_version="D1-R2-SIGNED-LOGITS-HOST-REPLAY-ONLY",
        model_sha256="REFERENCE_LOGITS_NO_MODEL_INCLUDED",
        pipeline_sha256="D2_SIGNED_FEATURE_FIXTURE",
        margin_threshold=margin_threshold,
    )
    backend = ReplayLogitBackend(
        [row["logits"] if "logits" in row else row["onnx_logits"] for row in expected_rows],
        contract,
    )
    uart_sink = MemoryUartSink()
    logger = StructuredLogger()
    runtime = FullChainRuntime(
        backend,
        uart_sink=uart_sink,
        logger=logger,
        config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST),
    )
    runtime.start(0)
    runtime.on_source_connected("recorded", 0)
    host_ms = 0

    def drain() -> None:
        nonlocal host_ms
        runtime.poll(host_ms)
        host_ms += 1

    chunks = RecordedByteSource(blob).emit(runtime.notification_callback, drain)
    runtime.poll(host_ms)
    runtime.on_source_disconnected("recorded_eof", host_ms + 1)
    http = MemoryHttpAdapter()
    identity = DeploymentIdentity("DUO-S-HOST-MOCK", "placeholder", "duo-s-full-chain-f2", "127.0.0.1", 80, contract.model_version, contract.pipeline_sha256)
    worker = NetworkWorker(http, identity, runtime.snapshots, logger, enable_emg_upload=False)
    worker.tick_once()
    snapshot = runtime.snapshots.get()
    stable_events = [record.as_dict() for record in logger.records() if record.event == "state_change"]
    stable_gesture_events: list[dict[str, Any]] = []
    previous_gesture = 0
    for event in stable_events:
        gesture = int(event["gesture_id"])
        if gesture != previous_gesture:
            stable_gesture_events.append(event)
            previous_gesture = gesture
    report = {
        "status": "PASS" if snapshot.valid_frames == 570 and backend.index == len(expected_rows) else "FAIL",
        "scope": "WINDOWS_HOST_RECORDED_REPLAY_NOT_LIVE_BLE_UART_OR_WIFI_HARDWARE",
        "frames": snapshot.valid_frames,
        "windows": backend.index,
        "expected_windows": len(expected_rows),
        "notify_chunks": chunks,
        "state_event_count": len(stable_events),
        "state_events": stable_events,
        "stable_gesture_event_count": len(stable_gesture_events),
        "stable_gesture_events": stable_gesture_events,
        "safety_event_count": snapshot.safety_event_count,
        "safety_counters": dict(snapshot.safety_counters),
        "uart_frames": len(uart_sink.frames),
        "uart_no_stable": runtime.uart.no_stable_count if runtime.uart else 0,
        "json_sink_paths": [path for path, _ in http.requests],
        "safe_mode_emg_upload_requests": sum(path == "/devices/wifi/emg" for path, _ in http.requests),
        "snapshot": snapshot.to_dict(),
    }
    return report, runtime


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Duo S full-chain recorded byte replay")
    parser.add_argument("--recording", type=Path, default=root / "artifacts/stage5_replay/fixtures/demo_sequence.bin")
    parser.add_argument("--expected", type=Path, default=root / "artifacts/duo_s_stage2/reference/raw_window_expected.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--margin-threshold", type=float, default=1.0, help="development replay threshold; formal runtime reads the model contract")
    args = parser.parse_args(argv)
    report, _ = run_replay(args.recording.read_bytes(), json.loads(args.expected.read_text(encoding="utf-8")), args.margin_threshold)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
