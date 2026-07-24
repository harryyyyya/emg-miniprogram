from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .events import StructuredLogger


TARGET_NAME = "BT-11(BLE)"
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"
REQUESTED_MTU = 28


@dataclass(frozen=True)
class Advertisement:
    address: str
    name: str | None
    service_uuids: tuple[str, ...]
    rssi: int | None = None


@dataclass(frozen=True)
class CharacteristicInfo:
    can_notify: bool
    can_indicate: bool


class BlePlatform(Protocol):
    """Platform API selected after WYH's Duo image probe."""

    def scan(self, duration_seconds: int) -> Sequence[Advertisement]: ...
    def connect(self, advertisement: Advertisement, on_disconnect: Callable[[], None]) -> None: ...
    def request_mtu(self, mtu: int) -> int: ...
    def discover_characteristic(self, service_uuid: str, characteristic_uuid: str) -> CharacteristicInfo: ...
    def subscribe(self, characteristic_uuid: str, indicate: bool, callback: Callable[[bytes], None]) -> None: ...
    def is_connected(self) -> bool: ...
    def close(self) -> None: ...


class BleTransport(Protocol):
    def start(self, now_ms: int = 0) -> bool: ...
    def poll(self, now_ms: int) -> None: ...
    def stop(self) -> None: ...


class DuoBleTransport:
    """Contract state machine independent of the eventual Linux BLE binding."""

    def __init__(
        self,
        platform: BlePlatform,
        notify_callback: Callable[[bytes], None],
        connected_callback: Callable[[], None],
        disconnected_callback: Callable[[str, int], None],
        logger: StructuredLogger,
        rescan_delay_ms: int = 500,
    ) -> None:
        self.platform = platform
        self.notify_callback = notify_callback
        self.connected_callback = connected_callback
        self.disconnected_callback = disconnected_callback
        self.logger = logger
        self.rescan_delay_ms = int(rescan_delay_ms)
        self.connected = False
        self.next_scan_ms = 0
        self._now_ms = 0

    @staticmethod
    def _matches(advertisement: Advertisement) -> bool:
        services = {item.lower() for item in advertisement.service_uuids}
        return advertisement.name == TARGET_NAME or SERVICE_UUID in services

    def _platform_disconnect(self) -> None:
        if self.connected:
            self.connected = False
            self.disconnected_callback("disconnect_callback", self._now_ms)
        self.next_scan_ms = self._now_ms + self.rescan_delay_ms

    def start(self, now_ms: int = 0) -> bool:
        self._now_ms = int(now_ms)
        self.logger.emit("ble_scan_start", target_name=TARGET_NAME, service_uuid=SERVICE_UUID)
        try:
            candidates = [item for item in self.platform.scan(5) if self._matches(item)]
        except Exception as error:
            self.connected = False
            self.platform.close()
            self.next_scan_ms = self._now_ms + self.rescan_delay_ms
            self.logger.emit("ble_scan_failed", error=str(error), retry_at_ms=self.next_scan_ms)
            return False
        if not candidates:
            self.next_scan_ms = self._now_ms + self.rescan_delay_ms
            self.logger.emit("ble_scan_empty")
            return False
        target = candidates[0]
        self.logger.emit("ble_scan_match", name=target.name, address=target.address, rssi=target.rssi)
        try:
            self.platform.connect(target, self._platform_disconnect)
            negotiated_mtu = self.platform.request_mtu(REQUESTED_MTU)
            characteristic = self.platform.discover_characteristic(SERVICE_UUID, NOTIFY_UUID)
            if characteristic.can_notify:
                indicate = False
            elif characteristic.can_indicate:
                indicate = True
            else:
                raise RuntimeError("FFE2 exposes neither notify nor indicate")
            self.platform.subscribe(NOTIFY_UUID, indicate, self.notify_callback)
        except Exception as error:
            self.logger.emit("ble_connect_failed", error=str(error))
            self.platform.close()
            self.next_scan_ms = self._now_ms + self.rescan_delay_ms
            return False
        self.connected = True
        self.connected_callback()
        self.logger.emit("ble_connected", requested_mtu=REQUESTED_MTU, negotiated_mtu=negotiated_mtu, subscription="indicate" if indicate else "notify")
        return True

    def poll(self, now_ms: int) -> None:
        self._now_ms = int(now_ms)
        if self.connected and not self.platform.is_connected():
            self.connected = False
            self.disconnected_callback("disconnect_poll", self._now_ms)
            self.platform.close()
            self.next_scan_ms = self._now_ms + self.rescan_delay_ms
        if not self.connected and self._now_ms >= self.next_scan_ms:
            self.start(self._now_ms)

    def stop(self) -> None:
        self.platform.close()
        if self.connected:
            self.connected = False
            self.disconnected_callback("transport_stop", self._now_ms)
        self.connected = False


class RecordedByteSource:
    """Development source that deliberately enters through the notify callback."""

    def __init__(self, blob: bytes, chunk_pattern: Sequence[int] = (1, 7, 28, 3, 196, 19)) -> None:
        if not chunk_pattern or any(int(item) <= 0 for item in chunk_pattern):
            raise ValueError("chunk_pattern must contain positive sizes")
        self.blob = bytes(blob)
        self.chunk_pattern = tuple(int(item) for item in chunk_pattern)

    def emit(self, notify_callback: Callable[[bytes], None], after_chunk: Callable[[], None] | None = None) -> int:
        offset = 0
        chunk_index = 0
        while offset < len(self.blob):
            size = self.chunk_pattern[chunk_index % len(self.chunk_pattern)]
            chunk = self.blob[offset : offset + size]
            notify_callback(chunk)
            if after_chunk is not None:
                after_chunk()
            offset += len(chunk)
            chunk_index += 1
        return chunk_index
