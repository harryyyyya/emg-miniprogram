from __future__ import annotations

from collections import deque
import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np


FEATURE_NAMES = tuple(
    f"emg_{channel}_{feature}"
    for feature in ("mav", "rms", "wl", "var", "zc", "ssc")
    for channel in range(1, 9)
)


class RingBuffer:
    def __init__(self, window_samples: int = 125, step_samples: int = 20) -> None:
        self.window_samples = int(window_samples)
        self.step_samples = int(step_samples)
        self._samples: deque[np.ndarray] = deque(maxlen=self.window_samples)
        self._pending = 0

    def reset(self) -> None:
        self._samples.clear()
        self._pending = 0

    def push_sample(self, sample: np.ndarray) -> np.ndarray | None:
        row = np.asarray(sample, dtype=np.uint8)
        if row.shape != (8,):
            raise ValueError(f"expected sample shape (8,), got {row.shape}")
        self._samples.append(row.copy())
        self._pending += 1
        if len(self._samples) < self.window_samples or self._pending < self.step_samples:
            return None
        self._pending = 0
        return np.stack(tuple(self._samples)).astype(np.uint8, copy=False)

    def push_frame(self, emg: np.ndarray) -> list[np.ndarray]:
        values = np.asarray(emg, dtype=np.uint8)
        if values.shape != (10, 8):
            raise ValueError(f"expected frame shape (10, 8), got {values.shape}")
        for row in values:
            self._samples.append(row.copy())
            self._pending += 1
        # BLE delivers ten samples atomically. Scheduling only at the frame
        # boundary preserves the signed D2 replay fixtures while the retained
        # window remains exactly the newest 125 samples.
        if len(self._samples) < self.window_samples or self._pending < self.step_samples:
            return []
        self._pending = 0
        return [np.stack(tuple(self._samples)).astype(np.uint8, copy=False)]


class FeatureBackend(Protocol):
    def compute(self, window: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class NumpyFeatureBackend:
    baseline: float = 127.0
    zc_threshold: float = 5.0
    ssc_threshold: float = 5.0

    def compute(self, window: np.ndarray) -> np.ndarray:
        raw = np.asarray(window)
        if raw.shape != (125, 8):
            raise ValueError(f"expected window shape (125, 8), got {raw.shape}")
        values = raw.astype(np.float32) - np.float32(self.baseline)
        diff = np.diff(values, axis=0)
        previous_delta = values[1:-1] - values[:-2]
        next_delta = values[1:-1] - values[2:]
        features = (
            np.mean(np.abs(values), axis=0),
            np.sqrt(np.mean(np.square(values), axis=0)),
            np.sum(np.abs(diff), axis=0),
            np.var(values, axis=0, ddof=0),
            np.count_nonzero(
                (values[:-1] * values[1:] < 0)
                & (np.abs(diff) >= self.zc_threshold),
                axis=0,
            ),
            np.count_nonzero(
                (previous_delta * next_delta > 0)
                & (np.maximum(np.abs(previous_delta), np.abs(next_delta)) >= self.ssc_threshold),
                axis=0,
            ),
        )
        result = np.concatenate(features).astype(np.float32)
        if result.shape != (48,) or not np.all(np.isfinite(result)):
            raise RuntimeError("feature backend produced invalid output")
        return result


class NativeFeatureBackend:
    """ctypes adapter for the included Duo-targetable C feature source."""

    def __init__(self, library_path: Path) -> None:
        self.library = ctypes.CDLL(str(library_path))
        self.library.duo_emg_features.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_float,
            ctypes.c_float,
        ]
        self.library.duo_emg_features.restype = ctypes.c_int

    def compute(self, window: np.ndarray) -> np.ndarray:
        values = np.ascontiguousarray(window, dtype=np.uint8)
        if values.shape != (125, 8):
            raise ValueError(f"expected window shape (125, 8), got {values.shape}")
        output = np.empty(48, dtype=np.float32)
        status = self.library.duo_emg_features(
            values.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            output.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_float(5.0),
            ctypes.c_float(5.0),
        )
        if status != 0 or not np.all(np.isfinite(output)):
            raise RuntimeError(f"native feature backend failed with status {status}")
        return output
