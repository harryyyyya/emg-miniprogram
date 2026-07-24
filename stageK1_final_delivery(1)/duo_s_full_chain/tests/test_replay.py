from __future__ import annotations

import json
import unittest

from duo_s_full_chain.runtime.replay import run_replay

from helpers import MARGIN_THRESHOLD, RECORDING, SIGNED_EXPECTED


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report, cls.runtime = run_replay(
            RECORDING.read_bytes(),
            json.loads(SIGNED_EXPECTED.read_text(encoding="utf-8")),
            MARGIN_THRESHOLD,
        )

    def test_reuses_all_570_frames_and_267_windows(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["frames"], 570)
        self.assertEqual(self.report["windows"], 267)

    def test_stable_safety_uart_and_json_sinks(self) -> None:
        self.assertGreater(self.report["stable_gesture_event_count"], 0)
        self.assertGreaterEqual(self.report["state_event_count"], self.report["stable_gesture_event_count"])
        self.assertGreaterEqual(self.report["safety_event_count"], 3)
        self.assertGreater(self.report["uart_frames"], 0)
        self.assertGreater(self.report["uart_no_stable"], 0)
        self.assertIn("/devices/wifi/register", self.report["json_sink_paths"])
        self.assertIn("/devices/wifi/heartbeat", self.report["json_sink_paths"])
        self.assertEqual(self.report["safe_mode_emg_upload_requests"], 0)


if __name__ == "__main__":
    unittest.main()
