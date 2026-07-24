from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class QueuePushResult:
    pushed: int
    dropped: int
    overflowed: bool


class BoundedByteQueue:
    """Thread-safe byte queue used directly by BLE notify callbacks."""

    def __init__(self, capacity: int = 4096) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self._bytes: deque[int] = deque()
        self._lock = threading.Lock()
        self.overflow_count = 0
        self.dropped_byte_count = 0

    def push(self, data: bytes) -> QueuePushResult:
        payload = bytes(data)
        with self._lock:
            available = self.capacity - len(self._bytes)
            pushed = min(available, len(payload))
            self._bytes.extend(payload[:pushed])
            dropped = len(payload) - pushed
            if dropped:
                self.overflow_count += 1
                self.dropped_byte_count += dropped
            return QueuePushResult(pushed, dropped, dropped > 0)

    def drain(self, limit: int | None = None) -> bytes:
        with self._lock:
            count = len(self._bytes) if limit is None else min(len(self._bytes), max(0, int(limit)))
            payload = bytes(self._bytes.popleft() for _ in range(count))
        return payload

    def clear(self) -> None:
        with self._lock:
            self._bytes.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._bytes)
