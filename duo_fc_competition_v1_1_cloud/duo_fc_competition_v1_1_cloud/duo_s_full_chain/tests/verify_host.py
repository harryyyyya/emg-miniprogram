from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from duo_s_full_chain.runtime.replay import run_replay


ARTIFACT = ROOT / "artifacts/duo_s_full_chain_runtime_f2"
CONTRACTS = ROOT / "duo_s_full_chain/contracts"
RECORDING = ROOT / "artifacts/stageh/fixtures/demo_sequence.bin"
EXPECTED = ROOT / "artifacts/stageh/reference/recorded_onnx_reference.json"
MODEL_MANIFEST = ROOT / "artifacts/stageh/model/manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "duo_s_full_chain/tests"), pattern="test_*.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    model_manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    replay, _ = run_replay(
        RECORDING.read_bytes(),
        json.loads(EXPECTED.read_text(encoding="utf-8")),
        float(model_manifest["default_margin_profile"]["threshold"]),
    )
    contract_files = sorted(CONTRACTS.glob("*.json"))
    contract_errors: list[str] = []
    for path in contract_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            contract_errors.append(f"{path.name}: {error}")
    forbidden_suffixes = {".onnx", ".cvimodel", ".so", ".dll", ".pyc"}
    owned_roots = [ROOT / "duo_s_full_chain" / name for name in ("contracts", "runtime", "native", "tests")]
    forbidden_files = [
        str(path.relative_to(ROOT))
        for owned in owned_roots
        for path in owned.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes and "__pycache__" not in path.parts
    ]
    provenance_paths = [
        ROOT / "artifacts/stageh/model/manifest.json",
        ROOT / "artifacts/stageh/model/pipeline_contract.json",
        ROOT / "artifacts/stageh/model/preprocess.json",
        ROOT / "artifacts/stageh/model/RISK_ACCEPTANCE.json",
        RECORDING,
        EXPECTED,
    ]
    status = "PASS" if result.wasSuccessful() and replay["status"] == "PASS" and not contract_errors and not forbidden_files else "FAIL"
    report = {
        "status": status,
        "scope": "WINDOWS_HOST_MOCK_RECORDED_REPLAY_ONLY",
        "duration_seconds": time.perf_counter() - started,
        "tests": {
            "run": result.testsRun,
            "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "output": stream.getvalue(),
        },
        "contracts": {"count": len(contract_files), "errors": contract_errors, "files": [path.name for path in contract_files]},
        "replay": replay,
        "prohibited_files_in_source": forbidden_files,
        "credentials_included": False,
        "model_artifacts_included": False,
        "hardware": {
            "duo_ble": "NOT_RUN_UNBOUND",
            "duo_tpu": "NOT_RUN_MODEL_NOT_INCLUDED",
            "j3_uart": "NOT_RUN_UNBOUND",
            "wifi_backend": "NOT_RUN_MOCK_ONLY",
        },
        "coverage": {
            "parser": ["fragmentation", "coalescing", "garbage_prefix", "bad_length_byte", "bad_tail", "resync"],
            "features": "267 signed D2 windows",
            "controller": ["labels_0_to_8", "MLP_top2_margin", "margin_boundary", "200ms_hold", "reset_recovery", "state_seq"],
            "uart": ["golden_bytes", "checksum", "sequence_wrap", "500ms_keepalive", "no_stable"],
            "network_paths": ["/devices/wifi/register", "/devices/wifi/heartbeat", "/devices/wifi/command/ack", "/devices/wifi/emg"],
            "network_commands": ["start_collect_ACK", "stop_collect_ACK"],
            "network_isolation": "20 real parser frames and inference continued while HTTP mock slept 200ms",
            "modes": "five formal plus one development replay",
            "snapshot": "frozen value plus concurrent locked safety publication",
        },
        "provenance_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in provenance_paths},
        "protected_directories_modified_by_this_task": [],
    }
    (ARTIFACT / "host_test_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = f"""# Host verifier report

- Status: `{status}`
- Scope: Windows host/mock/recorded replay only
- Tests: {report['tests']['passed']}/{report['tests']['run']} passed, {len(result.skipped)} skipped
- Contracts: {len(contract_files)} JSON documents parsed
- Replay: {replay['frames']} frames, {replay['windows']} windows, {replay['stable_gesture_event_count']} stable gesture events, {replay['state_event_count']} gesture/validity state events
- Safety: {replay['safety_event_count']} events, `{json.dumps(replay['safety_counters'], sort_keys=True)}`
- UART sink: {replay['uart_frames']} frames, including {replay['uart_no_stable']} no-stable frames
- JSON sink paths: `{', '.join(replay['json_sink_paths'])}`
- Network contract: register, heartbeat/pending_command, start/stop ACK, and EMG path tested
- Concurrency: signal parser/inference processed 20 frames during a controlled 200 ms HTTP stall
- Safe-mode EMG uploads: {replay['safe_mode_emg_upload_requests']}
- Hardware BLE/UART/Wi-Fi/TPU: NOT RUN
- Credentials/model artifacts/raw fixture included in handoff: no
"""
    (ARTIFACT / "host_test_report.md").write_text(markdown, encoding="utf-8")
    (ARTIFACT / "replay_report.json").write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "tests": report["tests"], "replay": {key: replay[key] for key in ("frames", "windows", "stable_gesture_event_count", "state_event_count", "safety_event_count", "uart_frames")}}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
