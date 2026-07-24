from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .byte_queue import BoundedByteQueue
from .controller import ControllerConfig, ControllerOutput, EmgController, Validity
from .events import StructuredLogger
from .frame_parser import FrameStreamParser, ParsedFrame
from .model import ModelBackend
from .modes import DEFAULT_MODE, RuntimeMode, mode_capabilities
from .signal import FeatureBackend, NumpyFeatureBackend, RingBuffer
from .snapshot import RuntimeSnapshot, SnapshotStore
from .uart import MemoryUartSink, UartLink, UartSink


@dataclass(frozen=True)
class RuntimeConfig:
    mode: RuntimeMode = DEFAULT_MODE
    queue_capacity: int = 4096
    no_valid_frame_timeout_ms: int = 250
    packet_interval_ms: int = 20
    sample_interval_ms: int = 2
    vote_horizon_ms: int = 300
    vote_fraction: float = 0.70
    low_confidence_hold_ms: int = 200
    frame_boundary_schedule: bool | None = None


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


class FullChainRuntime:
    def __init__(
        self,
        model_backend: ModelBackend | None,
        feature_backend: FeatureBackend | None = None,
        uart_sink: UartSink | None = None,
        logger: StructuredLogger | None = None,
        config: RuntimeConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.capabilities = mode_capabilities(self.config.mode)
        self.frame_boundary_schedule = (
            self.config.mode == RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST
            if self.config.frame_boundary_schedule is None
            else bool(self.config.frame_boundary_schedule)
        )
        if self.capabilities.get("inference", False) and model_backend is None:
            raise ValueError("selected mode requires an injected model backend")
        self.model_backend = model_backend
        self.feature_backend = feature_backend or NumpyFeatureBackend()
        self.clock = clock
        self.logger = logger or StructuredLogger(clock=clock)
        self.queue = BoundedByteQueue(self.config.queue_capacity)
        self.parser = FrameStreamParser()
        self.ring = RingBuffer(125, 20)
        margin_threshold = model_backend.contract.margin_threshold if model_backend is not None else 0.0
        self.controller = EmgController(
            ControllerConfig(
                margin_threshold=margin_threshold,
                vote_horizon_ms=self.config.vote_horizon_ms,
                vote_required_fraction=self.config.vote_fraction,
                nominal_step_ms=40,
                low_confidence_hold_ms=self.config.low_confidence_hold_ms,
            )
        )
        model_version = model_backend.contract.model_version if model_backend is not None else "NOT_USED"
        pipeline_sha = model_backend.contract.pipeline_sha256 if model_backend is not None else "NOT_USED"
        self.snapshots = SnapshotStore(RuntimeSnapshot(mode=self.config.mode.value, model_version=model_version, pipeline_sha256=pipeline_sha))
        self.uart = UartLink(uart_sink or MemoryUartSink(), self.logger) if self.capabilities.get("uart", False) else None
        self._notify_lock = threading.Lock()
        self._notify_count = 0
        self._notify_bytes = 0
        self._overflow_pending = False
        self._source_active = False
        self._source_kind = "none"
        self._last_valid_host_ms: int | None = None
        self._last_packet_timestamp_ms: int | None = None
        self._signal_timeout_active = True
        self._model_timings_us: list[float] = []
        self._inference_count = 0
        self._inference_failures = 0
        self._timestamp_gaps = 0
        self._estimated_missing = 0
        self._started = False
        self._emg_frame_callback: Callable[[list[list[int]]], None] | None = None

    def now_ms(self) -> int:
        return int(self.clock() * 1000)

    def set_emg_frame_callback(self, callback: Callable[[list[list[int]]], None] | None) -> None:
        self._emg_frame_callback = callback

    def start(self, now_ms: int | None = None) -> None:
        if self._started:
            return
        timestamp = self.now_ms() if now_ms is None else int(now_ms)
        self._started = True
        if self.uart is not None:
            self.uart.force_no_stable(timestamp, "startup")
        self._publish_common()
        self.logger.emit("runtime_start", mode=self.config.mode.value)

    def on_source_connected(self, source_kind: str, now_ms: int | None = None) -> None:
        timestamp = self.now_ms() if now_ms is None else int(now_ms)
        self._source_active = True
        self._source_kind = source_kind
        self._signal_timeout_active = True
        self._last_valid_host_ms = None
        self.snapshots.update(ble_connected=source_kind == "ble", source_kind=source_kind, signal_timeout=True)
        self.logger.emit("source_connected", source_kind=source_kind, now_ms=timestamp)

    def on_source_disconnected(self, reason: str = "disconnect", now_ms: int | None = None) -> None:
        timestamp = self.now_ms() if now_ms is None else int(now_ms)
        self._source_active = False
        self._safety_reset(reason, timestamp, clear_parser=True)
        self.snapshots.update(ble_connected=False)
        self.logger.emit("source_disconnected", reason=reason)

    def notification_callback(self, data: bytes) -> None:
        """BLE/recorded callback boundary: queue write and lightweight counters only."""
        result = self.queue.push(data)
        with self._notify_lock:
            self._notify_count += 1
            self._notify_bytes += len(data)
            if result.overflowed:
                self._overflow_pending = True

    def _take_notify_counters(self) -> tuple[int, int, bool]:
        with self._notify_lock:
            overflow = self._overflow_pending
            self._overflow_pending = False
            return self._notify_count, self._notify_bytes, overflow

    def _publish_common(self, **extra: object) -> None:
        notify_count, notify_bytes, _ = self._take_notify_counters()
        timings = self._model_timings_us
        uart_tx = self.uart.tx_count if self.uart is not None else 0
        uart_safe = self.uart.no_stable_count if self.uart is not None else 0
        uart_sequence = self.uart.sequence if self.uart is not None else 0
        self.snapshots.update(
            notify_count=notify_count,
            notify_bytes=notify_bytes,
            invalid_frames=self.parser.parse_error_count,
            discarded_bytes=self.parser.discarded_byte_count,
            timestamp_gaps=self._timestamp_gaps,
            estimated_missing_packets=self._estimated_missing,
            queue_overflows=self.queue.overflow_count,
            queue_dropped_bytes=self.queue.dropped_byte_count,
            inference_count=self._inference_count,
            inference_failures=self._inference_failures,
            model_last_us=timings[-1] if timings else 0.0,
            model_p50_us=_percentile(timings, 0.50),
            model_p95_us=_percentile(timings, 0.95),
            model_max_us=max(timings, default=0.0),
            uart_tx_count=uart_tx,
            uart_no_stable_count=uart_safe,
            uart_last_sequence=uart_sequence,
            **extra,
        )

    def _safety_reset(self, reason: str, now_ms: int, clear_parser: bool) -> None:
        self.queue.clear()
        if clear_parser:
            self.parser.reset()
        self.ring.reset()
        output = self.controller.reset_for_continuity_block(0)
        self._last_packet_timestamp_ms = None
        self._last_valid_host_ms = None
        self._signal_timeout_active = True
        if self.uart is not None:
            self.uart.force_no_stable(now_ms, reason)
        self.snapshots.note_safety(
            reason,
            gesture_id=0,
            raw_top1=0,
            validity=Validity.SIGNAL_INVALID.name,
            margin=0.0,
            state_seq=output.state_seq,
            frame_seq=output.frame_seq,
            signal_timeout=True,
        )
        self._publish_common()
        self.logger.emit("safety_reset", reason=reason, state_seq=output.state_seq)

    def _continuity_reset(self, reason: str, timestamp_ms: int, now_ms: int) -> None:
        self.ring.reset()
        output = self.controller.reset_for_continuity_block(timestamp_ms)
        if self.uart is not None:
            self.uart.force_no_stable(now_ms, reason)
        self.snapshots.note_safety(
            reason,
            gesture_id=0,
            raw_top1=0,
            validity=Validity.SIGNAL_INVALID.name,
            margin=0.0,
            state_seq=output.state_seq,
            frame_seq=output.frame_seq,
            signal_timeout=True,
        )
        self.logger.emit("continuity_reset", reason=reason, timestamp_ms=timestamp_ms)

    def _run_inference(self, window: np.ndarray, sample_timestamp_ms: int, now_ms: int) -> ControllerOutput | None:
        if self.model_backend is None:
            return None
        started = time.perf_counter_ns()
        try:
            features = self.feature_backend.compute(window)
            prediction = self.model_backend.predict(features)
            if not 0 <= prediction.top1 <= 8:
                raise RuntimeError("model returned class outside 0..8")
        except Exception as error:
            self._inference_failures += 1
            self._safety_reset("fatal_inference", now_ms, clear_parser=True)
            self.logger.emit("inference_failure", error=str(error))
            return None
        model_us = (time.perf_counter_ns() - started) / 1000.0
        self._model_timings_us.append(model_us)
        self._inference_count += 1
        previous = self.controller.last_output
        output = self.controller.update(sample_timestamp_ms, prediction.top1, prediction.margin, True)
        if self.uart is not None:
            self.uart.consider(output, now_ms)
        self._publish_common(
            timestamp_ms=output.timestamp_ms,
            gesture_id=output.gesture_id,
            raw_top1=prediction.top1,
            validity=output.validity.name,
            margin=prediction.margin,
            state_seq=output.state_seq,
            frame_seq=output.frame_seq,
            signal_timeout=False,
        )
        self.logger.emit("inference", timestamp_ms=sample_timestamp_ms, top1=prediction.top1, margin=prediction.margin, validity=output.validity.name, model_us=model_us)
        if (output.gesture_id, output.validity, output.state_seq) != (previous.gesture_id, previous.validity, previous.state_seq):
            self.logger.emit("state_change", gesture_id=output.gesture_id, validity=output.validity.name, state_seq=output.state_seq)
        return output

    def _handle_frame(self, frame: ParsedFrame, now_ms: int) -> None:
        if self._last_packet_timestamp_ms is not None:
            delta = (frame.timestamp_ms - self._last_packet_timestamp_ms) & 0xFFFFFFFF
            if delta != self.config.packet_interval_ms:
                self._timestamp_gaps += 1
                if delta > self.config.packet_interval_ms and delta % self.config.packet_interval_ms == 0:
                    self._estimated_missing += delta // self.config.packet_interval_ms - 1
                    reason = "timestamp_packet_gap"
                else:
                    reason = "timestamp_interval_error"
                self._continuity_reset(reason, frame.timestamp_ms, now_ms)
        self._last_packet_timestamp_ms = frame.timestamp_ms
        self._last_valid_host_ms = now_ms
        self._signal_timeout_active = False
        snapshot = self.snapshots.get()
        preview = tuple(tuple(int(item) for item in row) for row in frame.emg)
        self.snapshots.update(
            valid_frames=snapshot.valid_frames + 1,
            timestamp_ms=frame.timestamp_ms,
            battery_level=frame.battery_percent,
            signal_timeout=False,
            emg_preview=preview,
        )
        if self._emg_frame_callback is not None:
            self._emg_frame_callback([[int(item) for item in row] for row in frame.emg])
        self.logger.emit("frame", timestamp_ms=frame.timestamp_ms, battery=frame.battery_percent)
        if self.frame_boundary_schedule:
            for window in self.ring.push_frame(frame.emg):
                if self._run_inference(window, frame.timestamp_ms, now_ms) is None and self._signal_timeout_active:
                    break
        else:
            for sample_index, sample in enumerate(frame.emg):
                window = self.ring.push_sample(sample)
                if window is not None:
                    sample_timestamp = (frame.timestamp_ms + sample_index * self.config.sample_interval_ms) & 0xFFFFFFFF
                    if self._run_inference(window, sample_timestamp, now_ms) is None and self._signal_timeout_active:
                        break

    def poll(self, now_ms: int | None = None) -> int:
        timestamp = self.now_ms() if now_ms is None else int(now_ms)
        _, _, overflow = self._take_notify_counters()
        if overflow:
            self._safety_reset("queue_overflow", timestamp, clear_parser=True)
            return 0
        payload = self.queue.drain()
        before_errors = self.parser.parse_error_count
        frames = self.parser.feed(payload) if payload else []
        if self.parser.parse_error_count != before_errors:
            self.logger.emit("frame_resync", parse_errors=self.parser.parse_error_count, discarded_bytes=self.parser.discarded_byte_count)
        for frame in frames:
            self._handle_frame(frame, timestamp)
        if (
            self._source_active
            and self._last_valid_host_ms is not None
            and not self._signal_timeout_active
            and timestamp - self._last_valid_host_ms >= self.config.no_valid_frame_timeout_ms
        ):
            self._safety_reset("no_valid_frame_timeout", timestamp, clear_parser=True)
        self._publish_common()
        return len(frames)
