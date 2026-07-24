from __future__ import annotations

import json
from enum import Enum
from pathlib import Path


class RuntimeMode(str, Enum):
    UART_ONLY_TEST = "UART_ONLY_TEST"
    WIFI_ONLY_TEST = "WIFI_ONLY_TEST"
    BLE_INFER_UART_TEST = "BLE_INFER_UART_TEST"
    FULL_CHAIN_SAFE_DEMO = "FULL_CHAIN_SAFE_DEMO"
    FULL_CHAIN_WITH_EMG_UPLOAD = "FULL_CHAIN_WITH_EMG_UPLOAD"
    RECORDED_REPLAY_FULL_CHAIN_TEST = "RECORDED_REPLAY_FULL_CHAIN_TEST"


DEFAULT_MODE = RuntimeMode.FULL_CHAIN_SAFE_DEMO


def mode_capabilities(mode: RuntimeMode | str) -> dict[str, bool]:
    selected = RuntimeMode(mode)
    path = Path(__file__).resolve().parents[1] / "contracts" / "modes.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {key: bool(value) for key, value in document["modes"][selected.value].items() if isinstance(value, bool)}
