from __future__ import annotations

import unittest

from duo_s_full_chain.runtime.controller import ControllerOutput, Validity
from duo_s_full_chain.runtime.events import StructuredLogger
from duo_s_full_chain.runtime.uart import MemoryUartSink, UartLink, build_uart_frame, validate_uart_frame


class UartTests(unittest.TestCase):
    def test_golden_valid_and_no_stable_frames(self) -> None:
        valid = build_uart_frame(2, 0, 1)
        no_stable = build_uart_frame(0xFE, 1, 0)
        self.assertEqual(valid, bytes.fromhex("aa55020001fc"))
        self.assertEqual(no_stable, bytes.fromhex("aa55fe010000"))
        self.assertTrue(validate_uart_frame(valid))
        self.assertTrue(validate_uart_frame(no_stable))

    def test_sequence_wrap_keepalive_and_no_stable(self) -> None:
        sink = MemoryUartSink()
        link = UartLink(sink, StructuredLogger())
        link.sequence = 0xFF
        output = ControllerOutput(1, 1, 8, Validity.VALID, 3.0, 0, 8)
        link.consider(output, 0)
        link.consider(output, 100)
        link.consider(output, 500)
        invalid = ControllerOutput(2, 2, 0, Validity.SIGNAL_INVALID, 0.0, 0, 0)
        link.consider(invalid, 501)
        self.assertEqual([frame[3] for frame in sink.frames], [0xFF, 0x00, 0x01])
        self.assertEqual(link.no_stable_count, 1)
        self.assertTrue(all(validate_uart_frame(frame) for frame in sink.frames))

    def test_invalid_mode_cannot_be_encoded_as_valid(self) -> None:
        with self.assertRaises(ValueError):
            build_uart_frame(9, 0, 1)


if __name__ == "__main__":
    unittest.main()
