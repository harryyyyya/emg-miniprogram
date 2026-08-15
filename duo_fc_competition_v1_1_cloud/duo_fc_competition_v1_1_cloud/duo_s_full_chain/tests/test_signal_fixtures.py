from __future__ import annotations

import json
import unittest

import numpy as np

from duo_s_full_chain.runtime.frame_parser import FRAME_SIZE, parse_frame
from duo_s_full_chain.runtime.signal import FEATURE_NAMES, NumpyFeatureBackend, RingBuffer

from helpers import PREPROCESS, RECORDING, SIGNED_FEATURES


class SignalFixtureTests(unittest.TestCase):
    def test_feature_names_are_feature_major(self) -> None:
        self.assertEqual(FEATURE_NAMES[:8], tuple(f"emg_{index}_mav" for index in range(1, 9)))
        self.assertEqual(FEATURE_NAMES[40:], tuple(f"emg_{index}_ssc" for index in range(1, 9)))

    def test_ring_and_features_match_existing_signed_fixture(self) -> None:
        blob = RECORDING.read_bytes()
        signed = np.load(SIGNED_FEATURES)
        preprocess = json.loads(PREPROCESS.read_text(encoding="utf-8"))
        mean = np.asarray(preprocess["mean"], dtype=np.float32)
        std = np.asarray(preprocess["std"], dtype=np.float32)
        ring = RingBuffer()
        backend = NumpyFeatureBackend()
        rows: list[np.ndarray] = []
        previous_timestamp = None
        for offset in range(0, len(blob), FRAME_SIZE):
            frame = parse_frame(blob[offset : offset + FRAME_SIZE])
            if previous_timestamp is not None and frame.timestamp_ms < previous_timestamp:
                ring.reset()
            previous_timestamp = frame.timestamp_ms
            for window in ring.push_frame(frame.emg):
                rows.append(((backend.compute(window) - mean) / std).astype(np.float32))
        actual = np.stack(rows)
        self.assertEqual(actual.shape, (267, 48))
        self.assertEqual(actual.shape, signed.shape)
        np.testing.assert_allclose(actual, signed, rtol=1e-5, atol=1e-4)


if __name__ == "__main__":
    unittest.main()
