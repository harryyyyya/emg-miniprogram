from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1])
    cycles = []
    for index in range(1, 11):
        path = root / f"cycle_{index}" / "replay.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["status"] == "PASS"
        assert report["rounds_requested"] == 1 and report["rounds_passed"] == 1
        item = report["rounds"][0]
        assert item["frames"] == 570 and item["windows"] == 267
        assert item["top1_match_rate"] >= 0.95
        assert item["state_events_exact"] is True and item["safety_events_exact"] is True
        assert item["pipeline_p95_us"] < 40000.0
        assert item["inference_failures"] == 0
        assert item["safe_mode_emg_upload_requests"] == 0
        cycles.append(item)
    summary = {
        "status": "PASS",
        "scope": "10_COLD_PROCESS_RECORDED_REPLAYS_PLUS_HCI_CREATE_CLEANUP_NOT_LIVE_BT11_UART_BACKEND_OR_ACTUATOR",
        "cycles_passed": len(cycles),
        "total_frames": sum(item["frames"] for item in cycles),
        "total_windows": sum(item["windows"] for item in cycles),
        "total_top1_matches": sum(item["top1_matches"] for item in cycles),
        "pipeline_p95_max_us": max(item["pipeline_p95_us"] for item in cycles),
        "pipeline_absolute_max_us": max(item["pipeline_max_us"] for item in cycles),
        "rss_first_kb": cycles[0]["rss_before_kb"],
        "rss_last_kb": cycles[-1]["rss_after_kb"],
        "inference_failures": sum(item["inference_failures"] for item in cycles),
        "emg_upload_requests": sum(item["safe_mode_emg_upload_requests"] for item in cycles),
        "live_gates": {
            "BT-11": "NOT_RUN",
            "J3_to_STM32": "NOT_RUN",
            "real_backend": "NOT_RUN",
            "actuator": "NOT_RUN",
        },
    }
    (root / "acceptance_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

