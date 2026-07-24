"""Duo S BLE platform using the tools proven on WYH's locked image.

Evidence for every command and output parser is captured in the returned
board probes.  gatttool interactive mode requires a PTY on this image; a
plain stdin pipe was explicitly tested and timed out.
"""

from __future__ import annotations

import os
import re
import select
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .transport import Advertisement, CharacteristicInfo


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_DEVICE_RE = re.compile(r"(?:^|\]\s*)Device\s+([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.+?)\s*$", re.I)
_PRIMARY_RE = re.compile(
    r"attr handle\s*[:=]\s*0x([0-9a-f]+),\s*end grp handle\s*[:=]\s*0x([0-9a-f]+)\s+uuid\s*:\s*([0-9a-f-]+)",
    re.I,
)
_CHAR_RE = re.compile(
    r"handle\s*[:=]\s*0x([0-9a-f]+),\s*char properties\s*[:=]\s*0x([0-9a-f]+),\s*"
    r"char value handle\s*[:=]\s*0x([0-9a-f]+),\s*uuid\s*[:=]\s*([0-9a-f-]+)",
    re.I,
)
_DESC_RE = re.compile(r"handle\s*:\s*0x([0-9a-f]+),\s*uuid\s*:\s*([0-9a-f-]+)", re.I)
_NOTIFY_RE = re.compile(
    r"(?:Notification|Indication)\s+handle\s*=\s*0x[0-9a-f]+\s+value:\s*(.*?)\s*$",
    re.I,
)
_PROMPT_RE = re.compile(r"\]\[LE\]>")
_UUID_BASE = "-0000-1000-8000-00805f9b34fb"


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "")


def normalize_uuid(value: str) -> str:
    value = value.strip().lower()
    if re.fullmatch(r"[0-9a-f]{4}", value):
        return f"0000{value}{_UUID_BASE}"
    if re.fullmatch(r"[0-9a-f]{8}", value):
        return f"{value}{_UUID_BASE}"
    return value


def parse_scan_transcript(text: str) -> list[Advertisement]:
    found: dict[str, Advertisement] = {}
    for line in strip_ansi(text).splitlines():
        match = _DEVICE_RE.search(line)
        if not match:
            continue
        address, detail = match.groups()
        detail = detail.strip()
        if detail.lower().startswith("uuids:"):
            advertised = tuple(normalize_uuid(item) for item in re.findall(r"[0-9a-fA-F-]{36}|[0-9a-fA-F]{8}|[0-9a-fA-F]{4}", detail.split(":", 1)[1]))
            address = address.upper()
            previous = found.get(address)
            previous_services = previous.service_uuids if previous else ()
            found[address] = Advertisement(
                address,
                previous.name if previous else None,
                tuple(dict.fromkeys(previous_services + advertised)),
            )
            continue
        if detail.lower().startswith(("rssi:", "txpower:", "manufacturerdata", "servicedata")):
            continue
        if detail.lower().startswith(("name:", "alias:")):
            detail = detail.split(":", 1)[1].strip()
        name = None if detail.lower() in {"(unknown)", "unknown"} else detail
        address = address.upper()
        previous = found.get(address)
        found[address] = Advertisement(
            address,
            name or (previous.name if previous else None),
            previous.service_uuids if previous else (),
        )
    return list(found.values())


def parse_primary_services(text: str) -> list[tuple[int, int, str]]:
    return [(int(start, 16), int(end, 16), normalize_uuid(uuid)) for start, end, uuid in _PRIMARY_RE.findall(strip_ansi(text))]


@dataclass(frozen=True)
class ParsedCharacteristic:
    declaration_handle: int
    properties: int
    value_handle: int
    uuid: str


def parse_characteristics(text: str) -> list[ParsedCharacteristic]:
    return [
        ParsedCharacteristic(int(handle, 16), int(properties, 16), int(value, 16), normalize_uuid(uuid))
        for handle, properties, value, uuid in _CHAR_RE.findall(strip_ansi(text))
    ]


def parse_descriptors(text: str) -> list[tuple[int, str]]:
    return [(int(handle, 16), normalize_uuid(uuid)) for handle, uuid in _DESC_RE.findall(strip_ansi(text))]


class NotificationLineDecoder:
    """Decode only complete, proven gatttool notification/indication lines."""

    def __init__(self, max_pending_chars: int = 16384) -> None:
        self.max_pending_chars = int(max_pending_chars)
        self.pending = ""
        self.error_count = 0

    def feed(self, chunk: str) -> list[bytes]:
        self.pending += strip_ansi(chunk)
        if len(self.pending) > self.max_pending_chars:
            self.pending = self.pending[-self.max_pending_chars :]
            self.error_count += 1
        lines = self.pending.split("\n")
        self.pending = lines.pop()
        payloads: list[bytes] = []
        for line in lines:
            lowered = line.lower()
            if "notification" not in lowered and "indication" not in lowered:
                continue
            match = _NOTIFY_RE.search(line)
            if not match:
                self.error_count += 1
                continue
            tokens = match.group(1).split()
            if not tokens or any(re.fullmatch(r"[0-9a-fA-F]{2}", token) is None for token in tokens):
                self.error_count += 1
                continue
            payloads.append(bytes(int(token, 16) for token in tokens))
        return payloads


def run_bounded_command(command: list[str], timeout_seconds: float, limit: int = 131072) -> tuple[int, str, str]:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}

    def drain(name: str, stream: object) -> None:
        while True:
            chunk = stream.read(4096)  # type: ignore[attr-defined]
            if not chunk:
                return
            target = buffers[name]
            target.extend(chunk)
            if len(target) > limit:
                del target[: len(target) - limit]

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            code = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
    for thread in threads:
        thread.join(timeout=1.0)
    return (
        code,
        buffers["stdout"].decode("utf-8", "replace"),
        buffers["stderr"].decode("utf-8", "replace"),
    )


class GatttoolPtySession:
    """One stateful gatttool connection, with bounded combined PTY output."""

    def __init__(self, on_disconnect: Callable[[], None], max_capture_chars: int = 65536) -> None:
        self.on_disconnect = on_disconnect
        self.max_capture_chars = int(max_capture_chars)
        self.process: subprocess.Popen[bytes] | None = None
        self.master_fd: int | None = None
        self._condition = threading.Condition()
        self._capture = ""
        self._decoder = NotificationLineDecoder()
        self._notification_callback: Callable[[bytes], None] | None = None
        self._disconnect_reported = False

    def start(self) -> None:
        master_fd, slave_fd = os.openpty()
        self.master_fd = master_fd
        try:
            self.process = subprocess.Popen(
                ["gatttool", "-I"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        finally:
            os.close(slave_fd)
        threading.Thread(target=self._reader, name="gatttool-pty-reader", daemon=True).start()
        self._wait_for_prompt(3.0)

    def _append_capture(self, text: str) -> None:
        with self._condition:
            self._capture += strip_ansi(text)
            if len(self._capture) > self.max_capture_chars:
                self._capture = self._capture[-self.max_capture_chars :]
            self._condition.notify_all()

    def _reader(self) -> None:
        assert self.master_fd is not None
        while True:
            try:
                readable, _, _ = select.select([self.master_fd], [], [], 0.5)
                if not readable:
                    if self.process is not None and self.process.poll() is not None:
                        break
                    continue
                chunk = os.read(self.master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            text = chunk.decode("utf-8", "replace")
            callback = self._notification_callback
            if callback is not None:
                for payload in self._decoder.feed(text):
                    callback(payload)
            self._append_capture(text)
        self._report_disconnect()

    def _report_disconnect(self) -> None:
        with self._condition:
            if self._disconnect_reported:
                return
            self._disconnect_reported = True
            self._condition.notify_all()
        self.on_disconnect()

    def _wait_for_prompt(self, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                if _PROMPT_RE.search(self._capture):
                    return self._capture
                if self._disconnect_reported or (self.process is not None and self.process.poll() is not None):
                    raise RuntimeError("gatttool exited before returning a prompt")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("gatttool prompt timeout")
                self._condition.wait(min(remaining, 0.1))

    def command(self, command: str, timeout_seconds: float = 10.0) -> str:
        if self.process is None or self.process.poll() is not None or self.master_fd is None:
            raise RuntimeError("gatttool PTY is not running")
        with self._condition:
            self._capture = ""
        os.write(self.master_fd, (command + "\n").encode("ascii"))
        return self._wait_for_prompt(timeout_seconds)

    def set_notification_callback(self, callback: Callable[[bytes], None]) -> None:
        self._notification_callback = callback

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None and not self._disconnect_reported

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None and self.master_fd is not None:
            try:
                self.command("disconnect", 2.0)
            except Exception:
                pass
            try:
                os.write(self.master_fd, b"exit\n")
            except OSError:
                pass
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self._report_disconnect()


class GatttoolBlePlatform:
    def __init__(
        self,
        command_runner: Callable[[list[str], float], tuple[int, str, str]] = run_bounded_command,
        session_factory: Callable[[Callable[[], None]], GatttoolPtySession] = GatttoolPtySession,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._command_runner = command_runner
        self._session_factory = session_factory
        self._monotonic_clock = monotonic_clock
        self._sleeper = sleeper
        self._session: GatttoolPtySession | None = None
        self._service_range: tuple[int, int] | None = None
        self._characteristic: ParsedCharacteristic | None = None

    def scan(self, duration_seconds: int) -> Sequence[Advertisement]:
        duration = max(1, int(duration_seconds))
        deadline = self._monotonic_clock() + duration
        code, stdout, stderr = self._command_runner(["timeout", str(duration), "bluetoothctl", "scan", "on"], duration + 2.0)
        transcript = stdout + "\n" + stderr
        status_code, status_stdout, status_stderr = self._command_runner(["bluetoothctl", "show"], 3.0)
        status_text = status_stdout + "\n" + status_stderr
        combined = transcript + "\n" + status_text
        if re.search(r"Failed to (?:start discovery|set discovery filter)|Set scan parameters failed", transcript, re.I):
            self._command_runner(["bluetoothctl", "scan", "off"], 3.0)
            raise RuntimeError(f"BLE scan failed: {strip_ansi(combined).strip()}")
        started = re.search(r"Discovery started|discovering on", transcript, re.I)
        discovering = status_code == 0 and re.search(r"^\s*Discovering:\s*yes\s*$", strip_ansi(status_text), re.I | re.M)
        if started is None and discovering is None:
            self._command_runner(["bluetoothctl", "scan", "off"], 3.0)
            raise RuntimeError(f"BLE scan start was not proven (exit {code}): {strip_ansi(combined).strip()}")
        remaining = deadline - self._monotonic_clock()
        if remaining > 0:
            self._sleeper(remaining)
        self._command_runner(["bluetoothctl", "scan", "off"], 3.0)
        _, devices_stdout, devices_stderr = self._command_runner(["bluetoothctl", "devices"], 3.0)
        return parse_scan_transcript(combined + "\n" + devices_stdout + "\n" + devices_stderr)

    def connect(self, advertisement: Advertisement, on_disconnect: Callable[[], None]) -> None:
        if re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", advertisement.address, re.I) is None:
            raise ValueError("invalid BLE address")
        session = self._session_factory(on_disconnect)
        self._session = session
        try:
            session.start()
            transcript = session.command(f"connect {advertisement.address}", 12.0)
            if "Connection successful" not in transcript:
                raise RuntimeError(f"gatttool connection failed: {transcript.strip()}")
        except Exception:
            session.close()
            self._session = None
            raise

    def _require_session(self) -> GatttoolPtySession:
        if self._session is None or not self._session.is_alive():
            raise RuntimeError("BLE session is not connected")
        return self._session

    def request_mtu(self, mtu: int) -> int:
        if int(mtu) != 28:
            raise ValueError("locked BLE contract requires MTU 28")
        transcript = self._require_session().command("mtu 28")
        match = re.search(r"MTU was exchanged successfully:\s*(\d+)", transcript, re.I)
        if match is None:
            raise RuntimeError(f"MTU 28 exchange failed: {transcript.strip()}")
        return int(match.group(1))

    def discover_characteristic(self, service_uuid: str, characteristic_uuid: str) -> CharacteristicInfo:
        session = self._require_session()
        service_text = session.command("primary FFE0")
        service = next((item for item in parse_primary_services(service_text) if item[2] == normalize_uuid(service_uuid)), None)
        if service is None:
            raise RuntimeError("FFE0 service not found")
        characteristic_text = session.command(f"characteristics 0x{service[0]:04x} 0x{service[1]:04x} FFE2")
        characteristic = next(
            (item for item in parse_characteristics(characteristic_text) if item.uuid == normalize_uuid(characteristic_uuid)),
            None,
        )
        if characteristic is None or not service[0] <= characteristic.value_handle <= service[1]:
            raise RuntimeError("FFE2 characteristic not found inside FFE0")
        self._service_range = (service[0], service[1])
        self._characteristic = characteristic
        return CharacteristicInfo(
            can_notify=bool(characteristic.properties & 0x10),
            can_indicate=bool(characteristic.properties & 0x20),
        )

    def subscribe(self, characteristic_uuid: str, indicate: bool, callback: Callable[[bytes], None]) -> None:
        if self._characteristic is None or self._service_range is None:
            raise RuntimeError("discover_characteristic must run before subscribe")
        if self._characteristic.uuid != normalize_uuid(characteristic_uuid):
            raise RuntimeError("subscription UUID does not match discovered FFE2")
        session = self._require_session()
        start = self._characteristic.value_handle + 1
        end = self._service_range[1]
        descriptor_text = session.command(f"char-desc 0x{start:04x} 0x{end:04x}")
        cccd = next((handle for handle, uuid in parse_descriptors(descriptor_text) if uuid == normalize_uuid("2902")), None)
        if cccd is None:
            raise RuntimeError("FFE2 CCCD 0x2902 not found")
        session.set_notification_callback(callback)
        value = "0200" if indicate else "0100"
        write_text = session.command(f"char-write-req 0x{cccd:04x} {value}")
        if "Characteristic value was written successfully" not in write_text:
            raise RuntimeError(f"CCCD write failed: {write_text.strip()}")

    def is_connected(self) -> bool:
        return self._session is not None and self._session.is_alive()

    def close(self) -> None:
        session = self._session
        self._session = None
        if session is not None:
            session.close()


def create_ble_platform() -> GatttoolBlePlatform:
    return GatttoolBlePlatform()
