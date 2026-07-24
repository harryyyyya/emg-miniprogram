from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from .engine import FullChainRuntime, RuntimeConfig
from .events import StructuredLogger
from .model import CviTpuModelBackend, ModelContract, ModelOutput
from .modes import RuntimeMode
from .network import DeploymentIdentity, NetworkWorker
from .replay import MemoryHttpAdapter, run_replay
from .signal import NativeFeatureBackend
from .transport import RecordedByteSource
from .uart import MemoryUartSink


def rss_kb() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def normalize_events(report: dict[str, Any]) -> list[tuple[int, str, int]]:
    return [
        (int(item["gesture_id"]), str(item["validity"]), int(item["state_seq"]))
        for item in report["state_events"]
    ]


class ComparingBackend:
    def __init__(self, backend: CviTpuModelBackend, expected_rows: list[dict[str, Any]]) -> None:
        self.backend = backend
        self.contract = backend.contract
        self.expected_rows = expected_rows
        self.index = 0
        self.top1_matches = 0
        self.max_logit_abs_diff = 0.0

    def predict(self, features: np.ndarray) -> ModelOutput:
        actual = self.backend.predict(features)
        expected = self.expected_rows[self.index]
        expected_logits = np.asarray(expected["logits"], dtype=np.float32)
        if actual.top1 == int(expected["top1"]):
            self.top1_matches += 1
        difference = float(np.max(np.abs(np.asarray(actual.logits, dtype=np.float32) - expected_logits)))
        self.max_logit_abs_diff = max(self.max_logit_abs_diff, difference)
        self.index += 1
        return actual


def execute_round(args: argparse.Namespace, expected_rows: list[dict[str, Any]], reference_report: dict[str, Any], round_index: int) -> dict[str, Any]:
    contract = ModelContract.from_json(args.model_contract)
    preprocess = json.loads(args.preprocess.read_text(encoding="utf-8"))
    rss_before = rss_kb()
    load_started = time.perf_counter_ns()
    model = CviTpuModelBackend(
        contract,
        args.cvimodel,
        preprocess["mean"],
        preprocess.get("scale", preprocess.get("std")),
        args.runtime_lib,
    )
    model_load_us = (time.perf_counter_ns() - load_started) / 1000.0
    comparing = ComparingBackend(model, expected_rows)
    logger = StructuredLogger()
    uart = MemoryUartSink()
    runtime = FullChainRuntime(
        comparing,
        feature_backend=NativeFeatureBackend(args.feature_lib),
        uart_sink=uart,
        logger=logger,
        config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST),
    )
    started = time.perf_counter_ns()
    try:
        runtime.start(0)
        runtime.on_source_connected("recorded", 0)
        host_ms = 0

        def drain() -> None:
            nonlocal host_ms
            runtime.poll(host_ms)
            host_ms += 1

        chunks = RecordedByteSource(args.recording.read_bytes()).emit(runtime.notification_callback, drain)
        runtime.poll(host_ms)
        snapshot = runtime.snapshots.get()
        state_events = [record.as_dict() for record in logger.records() if record.event == "state_change"]
        runtime.on_source_disconnected("recorded_eof", host_ms + 1)
        safety_snapshot = runtime.snapshots.get()
        actual_report = {
            "state_events": state_events,
            "safety_counters": dict(safety_snapshot.safety_counters),
            "safety_event_count": safety_snapshot.safety_event_count,
        }
        http = MemoryHttpAdapter()
        identity = DeploymentIdentity("DUO-S-RECORDED", "placeholder", "duo-s-full-chain-f8", "127.0.0.1", 80, contract.model_version, contract.pipeline_sha256)
        NetworkWorker(http, identity, runtime.snapshots, logger, enable_emg_upload=False).tick_once()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        top1_rate = comparing.top1_matches / len(expected_rows)
        state_exact = normalize_events(actual_report) == normalize_events(reference_report)
        safety_exact = (
            actual_report["safety_counters"] == reference_report["safety_counters"]
            and actual_report["safety_event_count"] == reference_report["safety_event_count"]
        )
        upload_count = sum(path == "/devices/wifi/emg" for path, _ in http.requests)
        passed = all(
            (
                snapshot.valid_frames == 570,
                comparing.index == 267,
                snapshot.inference_failures == 0,
                top1_rate >= 0.95,
                state_exact,
                safety_exact,
                snapshot.model_p95_us < 40_000.0,
                upload_count == 0,
            )
        )
        return {
            "round": round_index,
            "status": "PASS" if passed else "FAIL",
            "frames": snapshot.valid_frames,
            "windows": comparing.index,
            "notify_chunks": chunks,
            "top1_matches": comparing.top1_matches,
            "top1_match_rate": top1_rate,
            "max_logit_abs_diff_vs_wsl_simulator": comparing.max_logit_abs_diff,
            "state_events_exact": state_exact,
            "safety_events_exact": safety_exact,
            "model_load_us": model_load_us,
            "pipeline_p50_us": snapshot.model_p50_us,
            "pipeline_p95_us": snapshot.model_p95_us,
            "pipeline_max_us": snapshot.model_max_us,
            "inference_failures": snapshot.inference_failures,
            "safe_mode_emg_upload_requests": upload_count,
            "uart_frames": len(uart.frames),
            "rss_before_kb": rss_before,
            "rss_after_kb": rss_kb(),
            "elapsed_ms": elapsed_ms,
        }
    finally:
        model.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Duo S Stage H persistent TPU recorded replay")
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--model-contract", type=Path, required=True)
    parser.add_argument("--cvimodel", type=Path, required=True)
    parser.add_argument("--preprocess", type=Path, required=True)
    parser.add_argument("--feature-lib", type=Path, required=True)
    parser.add_argument("--runtime-lib", default="/mnt/system/lib/libcviruntime.so")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    expected_rows = json.loads(args.expected.read_text(encoding="utf-8"))
    reference_report, _ = run_replay(args.recording.read_bytes(), expected_rows, ModelContract.from_json(args.model_contract).margin_threshold)
    rounds = [execute_round(args, expected_rows, reference_report, index + 1) for index in range(args.rounds)]
    status = "PASS" if len(rounds) == args.rounds and args.rounds > 0 and all(item["status"] == "PASS" for item in rounds) else "FAIL"
    report = {
        "status": status,
        "scope": "DUO_S_TPU_RECORDED_REPLAY_NOT_LIVE_BLE_UART_OR_WIFI",
        "rounds_requested": args.rounds,
        "rounds_passed": sum(item["status"] == "PASS" for item in rounds),
        "rounds": rounds,
        "pipeline_p95_max_us": max(item["pipeline_p95_us"] for item in rounds),
        "rss_first_kb": rounds[0]["rss_before_kb"],
        "rss_last_kb": rounds[-1]["rss_after_kb"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
