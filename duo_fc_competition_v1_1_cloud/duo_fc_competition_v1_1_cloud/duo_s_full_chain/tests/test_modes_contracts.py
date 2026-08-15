from __future__ import annotations

import json
import unittest
from pathlib import Path

from duo_s_full_chain.runtime.modes import RuntimeMode, mode_capabilities


class ModesContractTests(unittest.TestCase):
    def test_formal_modes_and_replay_matrix(self) -> None:
        path = Path(__file__).resolve().parents[1] / "contracts/modes.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["default"], "FULL_CHAIN_SAFE_DEMO")
        self.assertEqual(len(document["modes"]), 6)
        for mode in RuntimeMode:
            self.assertIn(mode.value, document["modes"])
        self.assertTrue(mode_capabilities(RuntimeMode.FULL_CHAIN_SAFE_DEMO)["network"])
        self.assertFalse(mode_capabilities(RuntimeMode.FULL_CHAIN_SAFE_DEMO)["emg_upload"])
        self.assertTrue(mode_capabilities(RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST)["recorded_input"])
        self.assertFalse(document["modes"]["RECORDED_REPLAY_FULL_CHAIN_TEST"]["formal"])

    def test_every_contract_is_valid_json(self) -> None:
        contract_dir = Path(__file__).resolve().parents[1] / "contracts"
        for path in contract_dir.glob("*.json"):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
