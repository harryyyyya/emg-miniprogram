from __future__ import annotations

import ctypes
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np


@dataclass(frozen=True)
class ModelContract:
    model_version: str
    model_sha256: str
    pipeline_sha256: str
    margin_threshold: float
    class_order: tuple[int, ...] = tuple(range(9))

    def __post_init__(self) -> None:
        if not self.model_version or self.model_version == "REPLACE_ME":
            raise ValueError("model_version must be bound")
        if not np.isfinite(self.margin_threshold) or self.margin_threshold < 0:
            raise ValueError("model contract requires a finite non-negative margin_threshold")
        if self.class_order != tuple(range(9)):
            raise ValueError("model class order must be 0..8")

    @classmethod
    def from_json(cls, path: Path) -> "ModelContract":
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if document.get("margin_threshold") is None:
            raise ValueError("model contract margin_threshold is unbound")
        return cls(
            model_version=str(document["model_version"]),
            model_sha256=str(document["model_sha256"]),
            pipeline_sha256=str(document["pipeline_sha256"]),
            margin_threshold=float(document["margin_threshold"]),
            class_order=tuple(int(item) for item in document["class_order"]),
        )


@dataclass(frozen=True)
class ModelOutput:
    top1: int
    margin: float
    logits: tuple[float, ...]

    @classmethod
    def from_logits(cls, logits: Sequence[float]) -> "ModelOutput":
        values = np.asarray(logits, dtype=np.float32).reshape(-1)
        if values.shape != (9,) or not np.all(np.isfinite(values)):
            raise ValueError("model must return 9 finite logits")
        order = np.argsort(values)
        top1 = int(order[-1])
        margin = float(values[order[-1]] - values[order[-2]])
        return cls(top1, margin, tuple(float(item) for item in values))


class ModelBackend(Protocol):
    contract: ModelContract

    def predict(self, features: np.ndarray) -> ModelOutput: ...


class ReplayLogitBackend:
    """Development backend that returns signed reference logits in order."""

    def __init__(self, logits: Sequence[Sequence[float]], contract: ModelContract) -> None:
        self.contract = contract
        self._logits = tuple(tuple(float(item) for item in row) for row in logits)
        self.index = 0

    def predict(self, features: np.ndarray) -> ModelOutput:
        if np.asarray(features).shape != (48,):
            raise ValueError("model input must contain 48 features")
        if self.index >= len(self._logits):
            raise RuntimeError("replay model exhausted")
        output = ModelOutput.from_logits(self._logits[self.index])
        self.index += 1
        return output


class CallableModelBackend:
    def __init__(self, predict_fn: Any, contract: ModelContract) -> None:
        self.predict_fn = predict_fn
        self.contract = contract

    def predict(self, features: np.ndarray) -> ModelOutput:
        return ModelOutput.from_logits(self.predict_fn(np.asarray(features, dtype=np.float32)))


class CviTpuModelBackend:
    """Injected libcviruntime adapter; actual Duo library/model paths stay local."""

    def __init__(
        self,
        contract: ModelContract,
        model_path: Path,
        mean: Sequence[float],
        scale: Sequence[float],
        runtime_library: str = "/mnt/system/lib/libcviruntime.so",
    ) -> None:
        self.contract = contract
        self.model_path = Path(model_path)
        digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        if digest.lower() != contract.model_sha256.lower():
            raise RuntimeError(f"cvimodel SHA256 mismatch: {digest}")
        self.mean = np.asarray(mean, dtype=np.float32)
        self.scale = np.asarray(scale, dtype=np.float32)
        if self.mean.shape != (48,) or self.scale.shape != (48,) or not np.all(np.isfinite(self.scale) & (self.scale > 0)):
            raise ValueError("preprocess mean/scale must be 48 finite values with positive scale")
        self.lib = ctypes.CDLL(runtime_library)
        self.handle = ctypes.c_void_p()
        self.inputs = ctypes.c_void_p()
        self.outputs = ctypes.c_void_p()
        self.input_count = ctypes.c_int32()
        self.output_count = ctypes.c_int32()
        self._bind()
        self._check(self.lib.CVI_NN_RegisterModel(str(self.model_path).encode(), ctypes.byref(self.handle)), "RegisterModel")
        self._check(self.lib.CVI_NN_GetInputOutputTensors(self.handle, ctypes.byref(self.inputs), ctypes.byref(self.input_count), ctypes.byref(self.outputs), ctypes.byref(self.output_count)), "GetInputOutputTensors")
        if self.input_count.value != 1 or self.output_count.value != 1:
            raise RuntimeError("model contract requires exactly one input and one output")
        self.input_tensor = self.lib.CVI_NN_GetTensorByName(b"input", self.inputs, self.input_count)
        self.output_tensor = self.lib.CVI_NN_GetTensorByName(b"logits", self.outputs, self.output_count)
        if not self.output_tensor:
            self.output_tensor = self.lib.CVI_NN_GetTensorByName(b"logits_Gemm_f32", self.outputs, self.output_count)
        if not self.input_tensor or not self.output_tensor:
            raise RuntimeError("required input/logits tensors were not found")
        self.input_ptr = self.lib.CVI_NN_TensorPtr(self.input_tensor)
        self.output_ptr = self.lib.CVI_NN_TensorPtr(self.output_tensor)

    def _bind(self) -> None:
        self.lib.CVI_NN_RegisterModel.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self.lib.CVI_NN_RegisterModel.restype = ctypes.c_int32
        self.lib.CVI_NN_GetInputOutputTensors.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int32)]
        self.lib.CVI_NN_GetInputOutputTensors.restype = ctypes.c_int32
        self.lib.CVI_NN_GetTensorByName.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int32]
        self.lib.CVI_NN_GetTensorByName.restype = ctypes.c_void_p
        self.lib.CVI_NN_TensorPtr.argtypes = [ctypes.c_void_p]
        self.lib.CVI_NN_TensorPtr.restype = ctypes.c_void_p
        self.lib.CVI_NN_Forward.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32]
        self.lib.CVI_NN_Forward.restype = ctypes.c_int32
        self.lib.CVI_NN_CleanupModel.argtypes = [ctypes.c_void_p]
        self.lib.CVI_NN_CleanupModel.restype = ctypes.c_int32

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if int(code) != 0:
            raise RuntimeError(f"CVI_NN_{operation} failed with {int(code)}")

    def predict(self, features: np.ndarray) -> ModelOutput:
        values = (np.asarray(features, dtype=np.float32) - self.mean) / self.scale
        values = np.ascontiguousarray(values.reshape(1, 48), dtype=np.float32)
        ctypes.memmove(self.input_ptr, values.ctypes.data, values.nbytes)
        self._check(self.lib.CVI_NN_Forward(self.handle, self.inputs, self.input_count, self.outputs, self.output_count), "Forward")
        logits = np.ctypeslib.as_array(ctypes.cast(self.output_ptr, ctypes.POINTER(ctypes.c_float)), shape=(9,)).copy()
        return ModelOutput.from_logits(logits)

    def close(self) -> None:
        if self.handle:
            self.lib.CVI_NN_CleanupModel(self.handle)
            self.handle = ctypes.c_void_p()
