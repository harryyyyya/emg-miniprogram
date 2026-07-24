from __future__ import annotations

import unittest

from duo_s_full_chain.runtime.byte_queue import BoundedByteQueue
from duo_s_full_chain.runtime.frame_parser import FrameStreamParser, parse_frame

from helpers import make_frame


class ParserQueueTests(unittest.TestCase):
    def test_fragmented_and_packed_frames(self) -> None:
        parser = FrameStreamParser()
        first = make_frame(20, 125)
        second = make_frame(40, 129)
        frames = []
        for chunk in (first[:1], first[1:17], first[17:] + second[:50], second[50:]):
            frames.extend(parser.feed(chunk))
        self.assertEqual([item.timestamp_ms for item in frames], [20, 40])
        self.assertEqual(parser.pending_bytes, 0)

    def test_garbage_prefix_and_resync_after_bad_length_and_tail(self) -> None:
        parser = FrameStreamParser()
        bad_length = bytearray(make_frame(20))
        bad_length[2] = 0x5E
        bad_tail = bytearray(make_frame(40))
        bad_tail[97] = 0x54
        good = make_frame(60)
        frames = parser.feed(b"garbage\xaa" + bytes(bad_length) + bytes(bad_tail) + good)
        self.assertEqual([item.timestamp_ms for item in frames], [60])
        self.assertGreaterEqual(parser.parse_error_count, 2)
        self.assertGreater(parser.discarded_byte_count, 0)

    def test_parse_frame_layout(self) -> None:
        parsed = parse_frame(make_frame(0x01020304, 200, 73))
        self.assertEqual(parsed.timestamp_ms, 0x01020304)
        self.assertEqual(parsed.battery_percent, 73)
        self.assertEqual(parsed.emg.shape, (10, 8))
        self.assertTrue((parsed.emg == 200).all())
        self.assertEqual(parsed.imu, bytes(range(9)))

    def test_bounded_queue_overflow_is_counted_without_growth(self) -> None:
        queue = BoundedByteQueue(5)
        result = queue.push(b"12345678")
        self.assertEqual((result.pushed, result.dropped, result.overflowed), (5, 3, True))
        self.assertEqual(queue.overflow_count, 1)
        self.assertEqual(queue.dropped_byte_count, 3)
        self.assertEqual(queue.drain(), b"12345")


if __name__ == "__main__":
    unittest.main()
