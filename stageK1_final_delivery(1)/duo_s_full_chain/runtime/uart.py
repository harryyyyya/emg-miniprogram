from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .controller import ControllerOutput, Validity
from .events import StructuredLogger


def build_uart_frame(mode: int, sequence: int, status: int) -> bytes:
    if status == 1 and not 0 <= mode <= 8:
        raise ValueError("valid UART mode must be in 0..8")
    if status == 0 and mode != 0xFE:
        raise ValueError("no_stable UART mode must be 0xFE")
    frame = bytearray((0xAA, 0x55, mode & 0xFF, sequence & 0xFF, status & 0xFF, 0))
    frame[5] = frame[0] ^ frame[1] ^ frame[2] ^ frame[3] ^ frame[4]
    return bytes(frame)


def validate_uart_frame(frame: bytes) -> bool:
    return (
        len(frame) == 6
        and frame[:2] == b"\xaa\x55"
        and frame[5] == (frame[0] ^ frame[1] ^ frame[2] ^ frame[3] ^ frame[4])
        and ((frame[4] == 1 and 0 <= frame[2] <= 8) or (frame[4] == 0 and frame[2] == 0xFE))
    )


class UartSink(Protocol):
    def write(self, frame: bytes) -> None: ...


class MemoryUartSink:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def write(self, frame: bytes) -> None:
        self.frames.append(bytes(frame))


@dataclass(frozen=True)
class UartTx:
    frame: bytes
    sequence: int
    valid: bool
    reason: str


class UartLink:
    def __init__(self, sink: UartSink, logger: StructuredLogger, keepalive_ms: int = 500) -> None:
        self.sink = sink
        self.logger = logger
        self.keepalive_ms = int(keepalive_ms)
        self.sequence = 0
        self.last_tx_ms: int | None = None
        self.last_mode: int | None = None
        self.last_was_valid = False
        self.tx_count = 0
        self.no_stable_count = 0

    def _send(self, mode: int, status: int, now_ms: int, reason: str) -> UartTx:
        sequence = self.sequence
        frame = build_uart_frame(mode, sequence, status)
        self.sink.write(frame)
        self.sequence = (self.sequence + 1) & 0xFF
        self.last_tx_ms = int(now_ms)
        self.last_mode = mode if status == 1 else None
        self.last_was_valid = status == 1
        self.tx_count += 1
        if status == 0:
            self.no_stable_count += 1
        self.logger.emit("uart_tx", sequence=sequence, mode=mode, status=status, reason=reason, bytes_hex=frame.hex())
        return UartTx(frame, sequence, status == 1, reason)

    def force_no_stable(self, now_ms: int, reason: str) -> UartTx:
        return self._send(0xFE, 0, now_ms, reason)

    def consider(self, output: ControllerOutput, now_ms: int) -> UartTx | None:
        elapsed = None if self.last_tx_ms is None else int(now_ms) - self.last_tx_ms
        if output.validity == Validity.VALID and 0 <= output.gesture_id <= 8:
            if not self.last_was_valid or self.last_mode != output.gesture_id or elapsed is None or elapsed >= self.keepalive_ms:
                return self._send(output.gesture_id, 1, now_ms, "inference")
            return None
        if self.last_was_valid or elapsed is None or elapsed >= self.keepalive_ms:
            return self._send(0xFE, 0, now_ms, "no_stable")
        return None
