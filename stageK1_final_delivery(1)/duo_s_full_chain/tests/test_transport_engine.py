from __future__ import annotations

import unittest

import numpy as np

from duo_s_full_chain.runtime.engine import FullChainRuntime, RuntimeConfig
from duo_s_full_chain.runtime.events import StructuredLogger
from duo_s_full_chain.runtime.model import CallableModelBackend, ModelContract
from duo_s_full_chain.runtime.modes import RuntimeMode
from duo_s_full_chain.runtime.transport import Advertisement, CharacteristicInfo, DuoBleTransport, NOTIFY_UUID, REQUESTED_MTU, SERVICE_UUID
from duo_s_full_chain.runtime.uart import MemoryUartSink

from helpers import make_frame


def constant_model(label: int = 2, margin: float = 3.0) -> CallableModelBackend:
    contract = ModelContract("host-test", "no-model", "host-pipeline", 1.0)

    def predict(_: np.ndarray) -> np.ndarray:
        logits = np.zeros(9, dtype=np.float32)
        logits[label] = margin
        return logits

    return CallableModelBackend(predict, contract)


class MockBlePlatform:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.connected = True
        self.on_disconnect = None

    def scan(self, duration_seconds: int):
        self.calls.append(("scan", duration_seconds))
        return [Advertisement("A", "BT-11(BLE)", ())]

    def connect(self, advertisement, on_disconnect):
        self.calls.append(("connect", advertisement.address))
        self.on_disconnect = on_disconnect
        self.connected = True

    def request_mtu(self, mtu: int) -> int:
        self.calls.append(("mtu", mtu))
        return mtu

    def discover_characteristic(self, service_uuid: str, characteristic_uuid: str):
        self.calls.append(("discover", service_uuid, characteristic_uuid))
        return CharacteristicInfo(True, True)

    def subscribe(self, characteristic_uuid: str, indicate: bool, callback):
        self.calls.append(("subscribe", characteristic_uuid, indicate))
        self.callback = callback

    def is_connected(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.calls.append(("close",))


class FlakyScanPlatform(MockBlePlatform):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def scan(self, duration_seconds: int):
        self.calls.append(("scan", duration_seconds))
        if self.failures:
            self.failures -= 1
            raise RuntimeError("BLE scan start was not proven")
        return [Advertisement("A", "BT-11(BLE)", ())]


class TransportEngineTests(unittest.TestCase):
    def test_formal_mode_uses_authoritative_sample_wise_schedule(self) -> None:
        runtime = FullChainRuntime(constant_model(), config=RuntimeConfig(mode=RuntimeMode.BLE_INFER_UART_TEST))
        runtime.start(0)
        runtime.on_source_connected("ble", 0)
        for index in range(13):
            runtime.notification_callback(make_frame(index * 20))
            runtime.poll(index)
        self.assertEqual(runtime.snapshots.get().inference_count, 1)
        self.assertEqual(runtime.snapshots.get().timestamp_ms, 248)

    def test_ble_sequence_and_poll_disconnect_delayed_rescan(self) -> None:
        platform = MockBlePlatform()
        connected: list[bool] = []
        disconnected: list[tuple[str, int]] = []
        transport = DuoBleTransport(platform, lambda _: None, lambda: connected.append(True), lambda reason, now: disconnected.append((reason, now)), StructuredLogger())
        self.assertTrue(transport.start(0))
        self.assertEqual(platform.calls[:5], [
            ("scan", 5),
            ("connect", "A"),
            ("mtu", REQUESTED_MTU),
            ("discover", SERVICE_UUID, NOTIFY_UUID),
            ("subscribe", NOTIFY_UUID, False),
        ])
        platform.connected = False
        transport.poll(100)
        self.assertEqual(disconnected, [("disconnect_poll", 100)])
        scans = sum(call[0] == "scan" for call in platform.calls)
        transport.poll(599)
        self.assertEqual(sum(call[0] == "scan" for call in platform.calls), scans)
        transport.poll(600)
        self.assertEqual(sum(call[0] == "scan" for call in platform.calls), scans + 1)

    def test_scan_failure_is_safe_retried_and_then_recovers(self) -> None:
        platform = FlakyScanPlatform(failures=2)
        connected: list[bool] = []
        logger = StructuredLogger()
        transport = DuoBleTransport(platform, lambda _: None, lambda: connected.append(True), lambda reason, now: None, logger)
        self.assertFalse(transport.start(100))
        self.assertFalse(transport.connected)
        self.assertEqual(transport.next_scan_ms, 600)
        self.assertEqual(connected, [])
        self.assertEqual(logger.records()[-1].as_dict()["event"], "ble_scan_failed")
        transport.poll(599)
        self.assertEqual(sum(call[0] == "scan" for call in platform.calls), 1)
        transport.poll(600)
        self.assertFalse(transport.connected)
        self.assertEqual(transport.next_scan_ms, 1100)
        transport.poll(1100)
        self.assertTrue(transport.connected)
        self.assertEqual(connected, [True])

    def test_scan_failure_keeps_runtime_no_stable(self) -> None:
        platform = FlakyScanPlatform(failures=1)
        sink = MemoryUartSink()
        runtime = FullChainRuntime(constant_model(), uart_sink=sink, config=RuntimeConfig(mode=RuntimeMode.BLE_INFER_UART_TEST))
        runtime.start(0)
        transport = DuoBleTransport(
            platform,
            runtime.notification_callback,
            lambda: runtime.on_source_connected("ble", 0),
            lambda reason, now: runtime.on_source_disconnected(reason, now),
            StructuredLogger(),
        )
        self.assertFalse(transport.start(0))
        self.assertEqual(runtime.snapshots.get().validity, "SIGNAL_INVALID")
        self.assertGreaterEqual(runtime.uart.no_stable_count, 1)

    def test_disconnect_timeout_overflow_fatal_and_recovery(self) -> None:
        sink = MemoryUartSink()
        runtime = FullChainRuntime(constant_model(), uart_sink=sink, config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST, queue_capacity=128))
        runtime.start(0)
        runtime.on_source_connected("recorded", 0)
        for index in range(13):
            runtime.notification_callback(make_frame(index * 20))
            runtime.poll(index * 20)
        self.assertGreaterEqual(runtime.snapshots.get().inference_count, 1)
        before = len(sink.frames)
        runtime.poll(490)
        self.assertEqual(runtime.snapshots.get().last_safety_reason, "no_valid_frame_timeout")
        self.assertGreater(len(sink.frames), before)
        runtime.notification_callback(make_frame(1000) * 2)
        runtime.poll(500)
        self.assertEqual(runtime.snapshots.get().last_safety_reason, "queue_overflow")
        runtime.on_source_disconnected("disconnect", 510)
        self.assertEqual(runtime.snapshots.get().validity, "SIGNAL_INVALID")
        runtime.on_source_connected("recorded", 520)
        for index in range(13):
            runtime.notification_callback(make_frame(2000 + index * 20))
            runtime.poll(520 + index)
        self.assertFalse(runtime.snapshots.get().signal_timeout)

        def explode(_: np.ndarray):
            raise RuntimeError("fatal")

        fatal = FullChainRuntime(CallableModelBackend(explode, ModelContract("fatal", "none", "p", 1.0)), config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST))
        fatal.start(0)
        fatal.on_source_connected("recorded", 0)
        for index in range(13):
            fatal.notification_callback(make_frame(index * 20))
            fatal.poll(index)
        self.assertEqual(fatal.snapshots.get().last_safety_reason, "fatal_inference")
        self.assertEqual(fatal.snapshots.get().inference_failures, 1)


if __name__ == "__main__":
    unittest.main()
