from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True)
class RuntimeSnapshot:
    runtime_version: str = "duo-s-full-chain-f2"
    mode: str = "FULL_CHAIN_SAFE_DEMO"
    model_version: str = "UNBOUND"
    pipeline_sha256: str = "UNBOUND"
    timestamp_ms: int = 0
    battery_level: int = 0
    gesture_id: int = 0
    raw_top1: int = 0
    validity: str = "SIGNAL_INVALID"
    margin: float = 0.0
    state_seq: int = 0
    frame_seq: int = 0
    ble_connected: bool = False
    source_kind: str = "none"
    signal_timeout: bool = True
    notify_count: int = 0
    notify_bytes: int = 0
    valid_frames: int = 0
    invalid_frames: int = 0
    discarded_bytes: int = 0
    timestamp_gaps: int = 0
    estimated_missing_packets: int = 0
    queue_overflows: int = 0
    queue_dropped_bytes: int = 0
    inference_count: int = 0
    inference_failures: int = 0
    model_last_us: float = 0.0
    model_p50_us: float = 0.0
    model_p95_us: float = 0.0
    model_max_us: float = 0.0
    uart_tx_count: int = 0
    uart_no_stable_count: int = 0
    uart_last_sequence: int = 0
    wifi_connected: bool = False
    registered: bool = False
    http_ok_count: int = 0
    http_fail_count: int = 0
    http_timeout_count: int = 0
    last_http_path: str = ""
    safety_event_count: int = 0
    safety_counters: tuple[tuple[str, int], ...] = ()
    last_safety_reason: str = "startup"
    emg_preview: tuple[tuple[int, ...], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["safety_counters"] = dict(self.safety_counters)
        result["emg_preview"] = [list(row) for row in self.emg_preview]
        return result


class SnapshotStore:
    """Locked copy-on-write publication of immutable snapshots."""

    def __init__(self, initial: RuntimeSnapshot) -> None:
        self._snapshot = initial
        self._lock = threading.Lock()

    def get(self) -> RuntimeSnapshot:
        with self._lock:
            return self._snapshot

    def update(self, **changes: Any) -> RuntimeSnapshot:
        with self._lock:
            self._snapshot = replace(self._snapshot, **changes)
            return self._snapshot

    def note_safety(self, reason: str, **changes: Any) -> RuntimeSnapshot:
        with self._lock:
            counters = dict(self._snapshot.safety_counters)
            counters[reason] = counters.get(reason, 0) + 1
            self._snapshot = replace(
                self._snapshot,
                safety_event_count=self._snapshot.safety_event_count + 1,
                safety_counters=tuple(sorted(counters.items())),
                last_safety_reason=reason,
                **changes,
            )
            return self._snapshot
