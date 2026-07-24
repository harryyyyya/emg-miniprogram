from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from duo_s_full_chain.runtime.main import _load_uart_sink, parse_args
from duo_s_full_chain.runtime.platform_linux import FileUartSink, PosixUartSink


class CompetitionSinkTests(unittest.TestCase):
    def test_file_sink_preserves_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uart.bin"
            sink = FileUartSink(path)
            sink.write(b"\xaa\x55\xfe\x00\x00\x01")
            sink.close()
            self.assertEqual(path.read_bytes(), b"\xaa\x55\xfe\x00\x00\x01")

    def test_file_sink_requires_absolute_path(self) -> None:
        with self.assertRaises(ValueError):
            FileUartSink("relative.bin")

    def test_reserved_uart_devices_are_rejected_before_open(self) -> None:
        for device in ("/dev/ttyS0", "/dev/ttyS4"):
            with self.subTest(device=device), self.assertRaisesRegex(ValueError, "reserved"):
                PosixUartSink(device)

    def test_main_loader_accepts_explicit_file_scheme(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uart.bin"
            args = parse_args(["--uart-sink", f"file:{path}"])
            sink = _load_uart_sink(args)
            self.assertIsInstance(sink, FileUartSink)
            sink.close()


if __name__ == "__main__":
    unittest.main()
