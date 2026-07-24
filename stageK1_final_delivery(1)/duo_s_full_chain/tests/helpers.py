from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDING = ROOT / "fixtures/demo_sequence.bin"
SIGNED_FEATURES = ROOT / "reference/recorded_standardized_features.npy"
SIGNED_EXPECTED = ROOT / "reference/recorded_onnx_reference.json"
PREPROCESS = ROOT / "model/preprocess.json"
MODEL_MANIFEST = ROOT / "model/manifest.json"
MARGIN_THRESHOLD = float(json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))["default_margin_profile"]["threshold"])


def make_frame(timestamp_ms: int, fill: int = 127, battery: int = 80) -> bytes:
    frame = bytearray(98)
    frame[0:2] = b"\xaa\xaa"
    frame[2] = 0x5F
    frame[3:7] = (timestamp_ms & 0xFFFFFFFF).to_bytes(4, "big")
    frame[7:16] = bytes(range(9))
    frame[16:96] = bytes([fill & 0xFF]) * 80
    frame[96] = battery & 0xFF
    frame[97] = 0x55
    return bytes(frame)
