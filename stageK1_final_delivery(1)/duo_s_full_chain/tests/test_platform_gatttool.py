from __future__ import annotations

import re
import unittest
from pathlib import Path

import numpy as np

from duo_s_full_chain.runtime.engine import FullChainRuntime, RuntimeConfig
from duo_s_full_chain.runtime.events import StructuredLogger
from duo_s_full_chain.runtime.model import CallableModelBackend, ModelContract
from duo_s_full_chain.runtime.modes import RuntimeMode
from duo_s_full_chain.runtime.platform_gatttool import (
    GatttoolBlePlatform,
    NotificationLineDecoder,
    parse_characteristics,
    parse_descriptors,
    parse_primary_services,
    parse_scan_transcript,
)
from duo_s_full_chain.runtime.transport import Advertisement, DuoBleTransport, NOTIFY_UUID, SERVICE_UUID


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures_stagei"
RECORDING = ROOT / "fixtures/demo_sequence.bin"


class FakeSession:
    def __init__(self, on_disconnect, failures: set[str] | None = None) -> None:
        self.on_disconnect = on_disconnect
        self.failures = failures or set()
        self.alive = True
        self.commands: list[str] = []
        self.callback = None

    def start(self) -> None:
        return None

    def command(self, command: str, timeout_seconds: float = 10.0) -> str:
        self.commands.append(command)
        key = command.split()[0]
        if key in self.failures:
            raise RuntimeError(f"forced {key} failure")
        if key == "connect":
            return "Connection successful\n[AA:BB:CC:DD:EE:FF][LE]>"
        if key == "mtu":
            return "MTU was exchanged successfully: 28\n[AA:BB:CC:DD:EE:FF][LE]>"
        if key == "primary":
            return (FIXTURES / "gatt_primary_derived.txt").read_text(encoding="utf-8")
        if key == "characteristics":
            return (FIXTURES / "gatt_characteristic_derived.txt").read_text(encoding="utf-8")
        if key == "char-desc":
            return (FIXTURES / "gatt_descriptor_derived.txt").read_text(encoding="utf-8")
        if key == "char-write-req":
            return "Characteristic value was written successfully\n[AA:BB:CC:DD:EE:FF][LE]>"
        raise AssertionError(command)

    def set_notification_callback(self, callback) -> None:
        self.callback = callback

    def is_alive(self) -> bool:
        return self.alive

    def crash(self) -> None:
        self.alive = False
        self.on_disconnect()

    def close(self) -> None:
        was_alive = self.alive
        self.alive = False
        if was_alive:
            self.on_disconnect()


def constant_model() -> CallableModelBackend:
    def predict(_: np.ndarray) -> np.ndarray:
        logits = np.zeros(9, dtype=np.float32)
        logits[2] = 4.0
        return logits

    return CallableModelBackend(predict, ModelContract("stagei-test", "none", "pipeline", 1.0))


class DerivedTranscriptParserTests(unittest.TestCase):
    def test_fixture_provenance_is_explicit(self) -> None:
        text = (FIXTURES / "README.txt").read_text(encoding="utf-8")
        self.assertIn("synthetic parser inputs", text)
        self.assertIn("not hardware logs", text)

    def test_board_format_derived_scan_and_gatt_parsers(self) -> None:
        advertisements = parse_scan_transcript((FIXTURES / "bluetoothctl_scan_derived.txt").read_text(encoding="utf-8"))
        self.assertEqual([(item.address, item.name) for item in advertisements], [
            ("AA:BB:CC:DD:EE:FF", "BT-11(BLE)"),
            ("10:20:30:40:50:60", "OtherDevice"),
        ])
        self.assertEqual(advertisements[1].service_uuids, (SERVICE_UUID,))
        service = parse_primary_services((FIXTURES / "gatt_primary_derived.txt").read_text(encoding="utf-8"))[0]
        characteristic = parse_characteristics((FIXTURES / "gatt_characteristic_derived.txt").read_text(encoding="utf-8"))[0]
        descriptor = parse_descriptors((FIXTURES / "gatt_descriptor_derived.txt").read_text(encoding="utf-8"))[0]
        self.assertEqual(service, (0x10, 0x1F, SERVICE_UUID))
        self.assertEqual((characteristic.value_handle, characteristic.uuid, characteristic.properties), (0x12, NOTIFY_UUID, 0x10))
        self.assertEqual(descriptor[0], 0x13)

    def test_notification_fragment_coalescing_case_whitespace_and_errors(self) -> None:
        decoder = NotificationLineDecoder()
        self.assertEqual(decoder.feed("Notifi"), [])
        decoded = decoder.feed(
            "cation handle = 0x0012 value: aa BB 0c\n"
            "Indication   handle = 0x0012 value:  01  02\n"
        )
        self.assertEqual(decoded, [b"\xaa\xbb\x0c", b"\x01\x02"])
        self.assertEqual(decoder.feed("Notification handle = 0x0012 value: AA GG\n"), [])
        self.assertEqual(decoder.feed("Notification handle = broken\n"), [])
        self.assertEqual(decoder.feed("unrelated\n"), [])
        self.assertEqual(decoder.error_count, 2)


class PlatformStateTests(unittest.TestCase):
    def make_platform(self, failures: set[str] | None = None, scan_text: str | None = None, show_text: str = "Discovering: yes\n"):
        sessions: list[FakeSession] = []

        def factory(on_disconnect):
            session = FakeSession(on_disconnect, failures)
            sessions.append(session)
            return session

        def runner(command: list[str], timeout_seconds: float):
            if command[-2:] == ["scan", "off"]:
                return 0, "Failed to stop discovery: org.bluez.Error.Failed", ""
            if command[-1:] == ["show"]:
                return 0, show_text, ""
            if command[-1:] == ["devices"]:
                return 0, "", ""
            transcript = scan_text if scan_text is not None else (FIXTURES / "bluetoothctl_scan_derived.txt").read_text(encoding="utf-8")
            return 124, transcript, ""

        return GatttoolBlePlatform(runner, factory, monotonic_clock=lambda: 0.0, sleeper=lambda _: None), sessions

    def test_scan_connect_mtu_discovery_subscribe_and_process_crash(self) -> None:
        platform, sessions = self.make_platform()
        target = next(item for item in platform.scan(5) if item.name == "BT-11(BLE)")
        disconnects: list[bool] = []
        platform.connect(target, lambda: disconnects.append(True))
        self.assertEqual(platform.request_mtu(28), 28)
        info = platform.discover_characteristic(SERVICE_UUID, NOTIFY_UUID)
        self.assertTrue(info.can_notify)
        platform.subscribe(NOTIFY_UUID, False, lambda _: None)
        self.assertEqual(sessions[0].commands, [
            "connect AA:BB:CC:DD:EE:FF",
            "mtu 28",
            "primary FFE0",
            "characteristics 0x0010 0x001f FFE2",
            "char-desc 0x0013 0x001f",
            "char-write-req 0x0013 0100",
        ])
        sessions[0].crash()
        self.assertFalse(platform.is_connected())
        self.assertEqual(disconnects, [True])

    def test_failed_or_unproven_scan_is_not_target_absent(self) -> None:
        failed, _ = self.make_platform(scan_text="Set scan parameters failed: I/O error\n")
        with self.assertRaisesRegex(RuntimeError, "scan failed"):
            failed.scan(5)
        unproven, _ = self.make_platform(scan_text="", show_text="Discovering: no\n")
        with self.assertRaisesRegex(RuntimeError, "not proven"):
            unproven.scan(5)
        filter_only, _ = self.make_platform(scan_text="SetDiscoveryFilter success\n", show_text="Discovering: no\n")
        with self.assertRaisesRegex(RuntimeError, "not proven"):
            filter_only.scan(5)
        empty, _ = self.make_platform(scan_text="SetDiscoveryFilter success\nDiscovery started\n")
        self.assertEqual(list(empty.scan(5)), [])

    def test_show_discovering_yes_proves_scan_and_deadline_only_waits_remaining_time(self) -> None:
        elapsed = [10.0]
        waits: list[float] = []

        def runner(command, timeout_seconds):
            if command[-1:] == ["show"]:
                return 0, "Controller 00:00:00:00:00:00\nDiscovering: yes\n", ""
            if command[-2:] == ["scan", "off"] or command[-1:] == ["devices"]:
                return 0, "", ""
            elapsed[0] = 13.0
            return 0, "SetDiscoveryFilter success\n", ""

        platform = GatttoolBlePlatform(runner, lambda _: FakeSession(lambda: None), monotonic_clock=lambda: elapsed[0], sleeper=waits.append)
        self.assertEqual(list(platform.scan(5)), [])
        self.assertEqual(waits, [2.0])

    def test_filter_only_without_discovering_yes_is_unproven(self) -> None:
        platform, _ = self.make_platform(scan_text="SetDiscoveryFilter success\n", show_text="Discovering: no\n")
        with self.assertRaisesRegex(RuntimeError, "not proven"):
            platform.scan(5)

    def test_connect_mtu_and_discovery_failures_close_and_rescan(self) -> None:
        for failure in ("connect", "mtu", "primary", "characteristics"):
            platform, sessions = self.make_platform({failure})
            transport = DuoBleTransport(
                platform,
                lambda _: None,
                lambda: None,
                lambda reason, now: None,
                StructuredLogger(),
            )
            self.assertFalse(transport.start(100))
            self.assertEqual(transport.next_scan_ms, 600)
            self.assertFalse(sessions[0].is_alive())

    def test_real_recording_uses_same_notification_callback_queue_parser(self) -> None:
        blob = RECORDING.read_bytes()
        self.assertEqual(len(blob), 570 * 98)
        runtime = FullChainRuntime(constant_model(), config=RuntimeConfig(mode=RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST))
        runtime.start(0)
        runtime.on_source_connected("ble", 0)
        decoder = NotificationLineDecoder()
        host_ms = 0

        def accept(payload: bytes) -> None:
            nonlocal host_ms
            runtime.notification_callback(payload)
            runtime.poll(host_ms)
            host_ms += 20

        for offset in range(0, len(blob), 98):
            line = "Notification handle = 0x0012 value: " + blob[offset : offset + 98].hex(" ") + "\n"
            chunks = (line[:1], line[1:8], line[8:29], line[29:])
            for chunk in chunks:
                for payload in decoder.feed(chunk):
                    accept(payload)
        snapshot = runtime.snapshots.get()
        self.assertEqual(snapshot.valid_frames, 570)
        self.assertEqual(snapshot.inference_count, 267)
        self.assertEqual(snapshot.invalid_frames, 0)
        self.assertEqual(snapshot.queue_overflows, 0)


if __name__ == "__main__":
    unittest.main()
