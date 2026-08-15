"""Template only: WYH must bind these calls to the probed Duo BLE stack."""

from __future__ import annotations

from typing import Callable, Sequence

from .transport import Advertisement, CharacteristicInfo


class ProbedDuoBlePlatform:
    def scan(self, duration_seconds: int) -> Sequence[Advertisement]:
        raise NotImplementedError("bind to the BLE stack confirmed on WYH's current image")

    def connect(self, advertisement: Advertisement, on_disconnect: Callable[[], None]) -> None:
        raise NotImplementedError

    def request_mtu(self, mtu: int) -> int:
        raise NotImplementedError

    def discover_characteristic(self, service_uuid: str, characteristic_uuid: str) -> CharacteristicInfo:
        raise NotImplementedError

    def subscribe(self, characteristic_uuid: str, indicate: bool, callback: Callable[[bytes], None]) -> None:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def create_ble_platform() -> ProbedDuoBlePlatform:
    return ProbedDuoBlePlatform()
