from __future__ import annotations

from dataclasses import dataclass

import numpy as np


FRAME_SIZE = 98
HEADER = b"\xaa\xaa"
FRAME_TYPE = 0x5F
TAIL = 0x55


@dataclass(frozen=True)
class ParsedFrame:
    timestamp_ms: int
    battery_percent: int
    emg: np.ndarray
    imu: bytes
    raw: bytes


def parse_frame(payload: bytes) -> ParsedFrame:
    raw = bytes(payload)
    if len(raw) != FRAME_SIZE:
        raise ValueError(f"expected {FRAME_SIZE} bytes, got {len(raw)}")
    if raw[:2] != HEADER:
        raise ValueError("invalid frame header")
    if raw[2] != FRAME_TYPE:
        raise ValueError(f"invalid frame type/length byte 0x{raw[2]:02x}")
    if raw[97] != TAIL:
        raise ValueError("invalid frame tail")
    emg = np.frombuffer(raw[16:96], dtype=np.uint8).reshape(10, 8).copy()
    emg.setflags(write=False)
    return ParsedFrame(
        timestamp_ms=int.from_bytes(raw[3:7], "big", signed=False),
        battery_percent=raw[96],
        emg=emg,
        imu=raw[7:16],
        raw=raw,
    )


class FrameStreamParser:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self.parse_error_count = 0
        self.discarded_byte_count = 0

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[ParsedFrame]:
        self._buffer.extend(data)
        frames: list[ParsedFrame] = []
        while True:
            header_index = self._buffer.find(HEADER)
            if header_index < 0:
                preserve = 1 if self._buffer[-1:] == HEADER[:1] else 0
                discard = len(self._buffer) - preserve
                self.discarded_byte_count += discard
                if preserve:
                    self._buffer[:] = HEADER[:1]
                else:
                    self._buffer.clear()
                break
            if header_index:
                self.discarded_byte_count += header_index
                del self._buffer[:header_index]
            if len(self._buffer) < FRAME_SIZE:
                break
            if self._buffer[2] != FRAME_TYPE or self._buffer[97] != TAIL:
                self.parse_error_count += 1
                self.discarded_byte_count += 1
                del self._buffer[0]
                continue
            raw = bytes(self._buffer[:FRAME_SIZE])
            del self._buffer[:FRAME_SIZE]
            frames.append(parse_frame(raw))
        return frames
