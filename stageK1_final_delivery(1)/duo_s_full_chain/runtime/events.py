from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class LogRecord:
    event: str
    monotonic_ms: int
    fields: tuple[tuple[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {"event": self.event, "monotonic_ms": self.monotonic_ms, **dict(self.fields)}


class StructuredLogger:
    def __init__(self, sink: Callable[[str], None] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._sink = sink
        self._clock = clock
        self._records: list[LogRecord] = []
        self._lock = threading.Lock()

    def emit(self, event: str, **fields: Any) -> LogRecord:
        record = LogRecord(event, int(self._clock() * 1000), tuple(sorted(fields.items())))
        with self._lock:
            self._records.append(record)
        if self._sink is not None:
            self._sink(json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":")))
        return record

    def records(self) -> tuple[LogRecord, ...]:
        with self._lock:
            return tuple(self._records)
