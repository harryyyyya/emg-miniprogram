from __future__ import annotations

import unittest

from duo_s_full_chain.runtime.controller import ControllerConfig, EmgController, Validity
from duo_s_full_chain.runtime.model import ModelOutput


def mature(controller: EmgController, label: int, start_ms: int = 0, margin: float = 2.0):
    output = None
    for index in range(9):
        output = controller.update(start_ms + index * 40, label, margin, True)
    return output


class ControllerTests(unittest.TestCase):
    def test_mlp_logit_margin_adapter_uses_top_two_logits(self) -> None:
        output = ModelOutput.from_logits([0.0, 1.0, 4.5, 2.0, -1.0, 0.5, 0.2, 0.1, -2.0])
        self.assertEqual(output.top1, 2)
        self.assertAlmostEqual(output.margin, 2.5)

    def test_all_labels_zero_through_eight_are_supported(self) -> None:
        for label in range(9):
            with self.subTest(label=label):
                controller = EmgController(ControllerConfig(margin_threshold=1.0))
                output = mature(controller, label)
                self.assertEqual(output.gesture_id, label)
                self.assertEqual(output.validity, Validity.VALID)

    def test_margin_boundary_is_confident(self) -> None:
        controller = EmgController(ControllerConfig(margin_threshold=1.0))
        equal = controller.update(0, 2, 1.0, True)
        below = controller.update(40, 2, 0.999, True)
        self.assertEqual(equal.validity, Validity.VALID)
        self.assertEqual(below.validity, Validity.LOW_CONFIDENCE)

    def test_hold_is_at_most_200_ms(self) -> None:
        controller = EmgController(ControllerConfig(margin_threshold=1.0))
        stable = mature(controller, 5)
        self.assertEqual(stable.gesture_id, 5)
        held = controller.update(520, 1, 0.0, True)
        expired = controller.update(521, 1, 0.0, True)
        self.assertEqual((held.gesture_id, held.validity), (5, Validity.LOW_CONFIDENCE))
        self.assertEqual((expired.gesture_id, expired.validity), (0, Validity.LOW_CONFIDENCE))

    def test_state_seq_tracks_gesture_and_validity(self) -> None:
        controller = EmgController(ControllerConfig(margin_threshold=1.0))
        stable = mature(controller, 3)
        self.assertEqual(stable.state_seq, 1)
        low = controller.update(360, 3, 0.0, True)
        self.assertEqual(low.state_seq, 2)
        invalid = controller.update(400, 3, 2.0, False)
        self.assertEqual(invalid.state_seq, 3)
        reset = controller.reset_for_continuity_block(420)
        self.assertEqual(reset.state_seq, 3)

    def test_backward_timestamp_is_signal_invalid_and_recovery_reaccumulates(self) -> None:
        controller = EmgController(ControllerConfig(margin_threshold=1.0))
        mature(controller, 8, 100)
        invalid = controller.update(10, 8, 2.0, True)
        self.assertEqual((invalid.gesture_id, invalid.validity), (0, Validity.SIGNAL_INVALID))
        first = controller.update(20, 8, 2.0, True)
        self.assertEqual(first.gesture_id, 0)
        recovered = mature(controller, 8, 60)
        self.assertEqual(recovered.gesture_id, 8)


if __name__ == "__main__":
    unittest.main()
