from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import time
from pathlib import Path

from .engine import FullChainRuntime, RuntimeConfig
from .events import StructuredLogger
from .model import CviTpuModelBackend, ModelContract
from .modes import DEFAULT_MODE, RuntimeMode, mode_capabilities
from .network import DeploymentIdentity, NetworkWorker
from .platform_linux import FileUartSink, PosixUartSink, UrllibHttpAdapter
from .signal import NativeFeatureBackend
from .transport import DuoBleTransport


def _required(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} is required for this mode")
    return value


def _load_model(args: argparse.Namespace) -> CviTpuModelBackend:
    contract_path = Path(_required(args.model_contract or os.environ.get("DUO_MODEL_CONTRACT"), "model contract"))
    model_path = Path(_required(args.cvimodel or os.environ.get("DUO_CVIMODEL_PATH"), "cvimodel path"))
    preprocess_path = Path(_required(args.preprocess or os.environ.get("DUO_PREPROCESS_PATH"), "preprocess path"))
    contract = ModelContract.from_json(contract_path)
    preprocess = json.loads(preprocess_path.read_text(encoding="utf-8"))
    return CviTpuModelBackend(
        contract,
        model_path,
        preprocess["mean"],
        preprocess.get("scale", preprocess.get("std")),
        args.cvi_runtime_lib,
    )


def _load_uart_sink(args: argparse.Namespace) -> FileUartSink | PosixUartSink:
    target = args.uart_sink or os.environ.get("DUO_UART_SINK") or args.uart_device
    target = _required(target, "DUO_UART_SINK or DUO_UART_DEVICE")
    if target.startswith("file:"):
        return FileUartSink(target[5:])
    return PosixUartSink(target)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Duo S FULL_CHAIN_SAFE_DEMO runtime")
    parser.add_argument("--mode", choices=[item.value for item in RuntimeMode if item != RuntimeMode.RECORDED_REPLAY_FULL_CHAIN_TEST], default=DEFAULT_MODE.value)
    parser.add_argument("--model-contract")
    parser.add_argument("--cvimodel")
    parser.add_argument("--preprocess")
    parser.add_argument("--feature-lib", default=os.environ.get("DUO_FEATURE_LIB"))
    parser.add_argument("--cvi-runtime-lib", default="/mnt/system/lib/libcviruntime.so")
    parser.add_argument("--ble-platform-module", default=os.environ.get("DUO_BLE_PLATFORM_MODULE"))
    parser.add_argument("--uart-device", default=os.environ.get("DUO_UART_DEVICE"))
    parser.add_argument("--uart-sink", default=os.environ.get("DUO_UART_SINK"), help="file:/absolute/path for mock, or a verified /dev path")
    parser.add_argument("--backend-url", default=os.environ.get("DUO_BACKEND_URL"))
    parser.add_argument("--duration-seconds", type=float, default=0.0, help="0 runs until interrupted")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = RuntimeMode(args.mode)
    capabilities = mode_capabilities(mode)
    logger = StructuredLogger(sink=print)
    model = _load_model(args) if capabilities.get("inference", False) else None
    uart = _load_uart_sink(args) if capabilities.get("uart", False) else None
    feature_backend = NativeFeatureBackend(Path(args.feature_lib)) if args.feature_lib else None
    runtime = FullChainRuntime(model, feature_backend=feature_backend, uart_sink=uart, logger=logger, config=RuntimeConfig(mode=mode))
    network = None
    transport = None
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    try:
        runtime.start()
        if capabilities.get("network", False):
            identity = DeploymentIdentity.from_env(
                model.contract.model_version if model is not None else "NOT_USED",
                model.contract.pipeline_sha256 if model is not None else "NOT_USED",
            )
            network = NetworkWorker(
                UrllibHttpAdapter(_required(args.backend_url, "DUO_BACKEND_URL")),
                identity,
                runtime.snapshots,
                logger,
                enable_emg_upload=capabilities.get("emg_upload", False),
            )
            runtime.set_emg_frame_callback(network.queue_emg_samples)
            network.start()
        if capabilities.get("ble", False):
            module_name = _required(args.ble_platform_module, "DUO_BLE_PLATFORM_MODULE")
            module = importlib.import_module(module_name)
            platform = module.create_ble_platform()
            transport = DuoBleTransport(
                platform,
                runtime.notification_callback,
                lambda: runtime.on_source_connected("ble"),
                lambda reason, now: runtime.on_source_disconnected(reason, now),
                logger,
            )
            transport.start(runtime.now_ms())
        deadline = None if args.duration_seconds <= 0 else time.monotonic() + args.duration_seconds
        while not stop_requested and (deadline is None or time.monotonic() < deadline):
            now_ms = runtime.now_ms()
            if transport is not None:
                transport.poll(now_ms)
            runtime.poll(now_ms)
            time.sleep(0.001)
        return 0
    finally:
        if transport is not None:
            transport.stop()
        if network is not None:
            network.stop()
        if runtime.uart is not None:
            runtime.uart.force_no_stable(runtime.now_ms(), "shutdown")
        if model is not None:
            model.close()
        if uart is not None:
            uart.close()
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
