from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import termios
except ImportError:  # Windows host tests can still exercise the explicit file sink.
    termios = None  # type: ignore[assignment]


class PosixUartSink:
    """Linux J3 UART sink configured as 115200 8N1; board device is injected."""

    def __init__(self, device: str) -> None:
        if not device.startswith("/dev/"):
            raise ValueError("UART device must be an explicit /dev path")
        if device in {"/dev/ttyS0", "/dev/ttyS4"}:
            raise ValueError(f"UART device is reserved and forbidden: {device}")
        if termios is None:
            raise RuntimeError("POSIX termios is unavailable on this host")
        self.fd = os.open(device, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[2] &= ~(termios.PARENB | termios.CSTOPB)
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def write(self, frame: bytes) -> None:
        written = os.write(self.fd, frame)
        if written != len(frame):
            raise OSError(f"short UART write: {written}/{len(frame)}")

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class FileUartSink:
    """Explicit mock UART sink; bytes are appended exactly as transmitted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("mock UART file path must be absolute")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)

    def write(self, frame: bytes) -> None:
        written = os.write(self.fd, frame)
        if written != len(frame):
            raise OSError(f"short mock UART write: {written}/{len(frame)}")

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class UrllibHttpAdapter:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            self.base_url + (path if path.startswith("/") else "/" + path),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = response.read()
                return int(response.status), json.loads(body) if body else {}
        except TimeoutError:
            raise
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TimeoutError(str(error)) from error
            raise RuntimeError(str(error)) from error
