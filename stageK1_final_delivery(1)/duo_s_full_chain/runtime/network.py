from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .events import StructuredLogger
from .snapshot import RuntimeSnapshot, SnapshotStore


REGISTER_PATH = "/devices/wifi/register"
HEARTBEAT_PATH = "/devices/wifi/heartbeat"
ACK_PATH = "/devices/wifi/command/ack"
EMG_PATH = "/devices/wifi/emg"


class HttpAdapter(Protocol):
    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[int, dict[str, Any]]: ...


@dataclass(frozen=True)
class DeploymentIdentity:
    hardware_id: str
    board_token: str
    firmware_version: str
    wifi_host: str
    wifi_port: int
    model_version: str
    pipeline_sha256: str

    @classmethod
    def from_env(cls, model_version: str, pipeline_sha256: str) -> "DeploymentIdentity":
        token = os.environ.get("DUO_BOARD_TOKEN", "")
        if not token:
            raise RuntimeError("DUO_BOARD_TOKEN must come from local environment/config")
        return cls(
            hardware_id=os.environ.get("DUO_HARDWARE_ID", "DUO-S-HAND-PLACEHOLDER"),
            board_token=token,
            firmware_version=os.environ.get("DUO_RUNTIME_VERSION", "duo-s-full-chain-f2"),
            wifi_host=os.environ.get("DUO_WIFI_HOST", "0.0.0.0"),
            wifi_port=int(os.environ.get("DUO_WIFI_PORT", "80")),
            model_version=model_version,
            pipeline_sha256=pipeline_sha256,
        )


class NetworkWorker:
    def __init__(
        self,
        http: HttpAdapter,
        identity: DeploymentIdentity,
        snapshots: SnapshotStore,
        logger: StructuredLogger,
        enable_emg_upload: bool = False,
        heartbeat_interval_s: float = 1.0,
        timeout_s: float = 0.25,
    ) -> None:
        self.http = http
        self.identity = identity
        self.snapshots = snapshots
        self.logger = logger
        self.enable_emg_upload = bool(enable_emg_upload)
        self.heartbeat_interval_s = float(heartbeat_interval_s)
        self.timeout_s = float(timeout_s)
        self.registered = False
        self.collecting = False
        self.session_id = ""
        self.gesture_name = ""
        self.sample_count = 0
        self.sequence_no = 0
        self._last_command_id = ""
        self._uploads: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            status, response = self.http.post_json(path, payload, self.timeout_s)
        except TimeoutError:
            snap = self.snapshots.get()
            self.snapshots.update(http_timeout_count=snap.http_timeout_count + 1, last_http_path=path)
            self.logger.emit("http_timeout", path=path)
            return 0, {}
        except Exception as error:
            snap = self.snapshots.get()
            self.snapshots.update(http_fail_count=snap.http_fail_count + 1, last_http_path=path)
            self.logger.emit("http_failure", path=path, error=str(error))
            return 0, {}
        snap = self.snapshots.get()
        if 200 <= status < 300:
            self.snapshots.update(http_ok_count=snap.http_ok_count + 1, last_http_path=path)
        else:
            self.snapshots.update(http_fail_count=snap.http_fail_count + 1, last_http_path=path)
        self.logger.emit("http_result", path=path, status=status)
        return status, response

    def register_payload(self) -> dict[str, Any]:
        return {
            "hardware_id": self.identity.hardware_id,
            "board_token": self.identity.board_token,
            "firmware_version": self.identity.firmware_version,
            "wifi_host": self.identity.wifi_host,
            "wifi_port": self.identity.wifi_port,
            "model_version": self.identity.model_version,
            "pipeline_sha256": self.identity.pipeline_sha256,
            "board_type": "milk_duo_s",
            "platform": "milk-v-duo-s",
        }

    def heartbeat_payload(self, snapshot: RuntimeSnapshot) -> dict[str, Any]:
        return {
            "hardware_id": self.identity.hardware_id,
            "board_token": self.identity.board_token,
            "ip_address": self.identity.wifi_host,
            "firmware_version": self.identity.firmware_version,
            "battery_level": snapshot.battery_level,
            "signal_strength": 0,
            "telemetry": {
                "prediction_result": f"gesture_{snapshot.gesture_id}",
                "prediction_confidence": snapshot.margin,
                "prediction_margin": snapshot.margin,
                "gesture_id": snapshot.gesture_id,
                "raw_top1": snapshot.raw_top1,
                "validity": snapshot.validity,
                "model_version": snapshot.model_version,
                "pipeline_sha256": snapshot.pipeline_sha256,
                "board_type": "milk_duo_s",
                "platform": "milk-v-duo-s",
                "emg_preview": [list(row) for row in snapshot.emg_preview],
                "module_statuses": {
                    "model": "loaded",
                    "bluetooth": "connected" if snapshot.ble_connected else "disconnected",
                    "uart": "initialized",
                    "wifi": "connected" if snapshot.wifi_connected else "unknown",
                    "backend": "available" if snapshot.registered else "unregistered",
                    "signal": snapshot.validity,
                },
                "duo_runtime": snapshot.runtime_version,
                "safety_counters": dict(snapshot.safety_counters),
            },
        }

    def ack_payload(self, command_id: str, success: bool, message: str) -> dict[str, Any]:
        return {
            "hardware_id": self.identity.hardware_id,
            "board_token": self.identity.board_token,
            "command_id": command_id,
            "success": bool(success),
            "message": message,
            "result": {"collecting": self.collecting, "session_id": self.session_id, "sample_count": self.sample_count},
        }

    def _handle_pending(self, response: dict[str, Any]) -> None:
        command = response.get("pending_command")
        if not isinstance(command, dict):
            return
        command_id = str(command.get("command_id", ""))
        action = str(command.get("action", ""))
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if not command_id or command_id == self._last_command_id:
            return
        if action == "start_collect":
            self.session_id = str(command.get("session_id") or payload.get("session_id") or "")
            self.gesture_name = str(command.get("gesture_name") or payload.get("gesture_name") or "")
            self.sample_count = 0
            self.sequence_no = 0
            self.collecting = self.enable_emg_upload
            success = self.enable_emg_upload
            message = "collect started" if success else "emg upload disabled in this mode"
        elif action == "stop_collect":
            if self.enable_emg_upload and self.collecting and self.session_id:
                self.queue_emg({
                    "session_id": self.session_id,
                    "gesture_name": self.gesture_name,
                    "sample_rate_hz": 500,
                    "sequence_no": self.sequence_no,
                    "is_final": True,
                    "samples": [],
                })
            self.collecting = False
            success = True
            message = "collect stop requested"
        else:
            success = False
            message = "unsupported action"
        self._post(ACK_PATH, self.ack_payload(command_id, success, message))
        self._last_command_id = command_id

    def tick_once(self) -> None:
        if not self.registered:
            status, _ = self._post(REGISTER_PATH, self.register_payload())
            self.registered = 200 <= status < 300
            self.snapshots.update(registered=self.registered, wifi_connected=self.registered)
            if not self.registered:
                return
        status, response = self._post(HEARTBEAT_PATH, self.heartbeat_payload(self.snapshots.get()))
        if 200 <= status < 300:
            self._handle_pending(response)
        try:
            upload = self._uploads.get_nowait()
        except queue.Empty:
            return
        if self.enable_emg_upload:
            self._post(EMG_PATH, upload)

    def queue_emg(self, payload: dict[str, Any]) -> bool:
        if not self.enable_emg_upload:
            return False
        complete = {"hardware_id": self.identity.hardware_id, "board_token": self.identity.board_token, **payload}
        try:
            self._uploads.put_nowait(complete)
            rows = complete.get("samples")
            if isinstance(rows, list):
                self.sample_count += len(rows)
            self.sequence_no = max(self.sequence_no, int(complete.get("sequence_no", self.sequence_no)) + 1)
            return True
        except queue.Full:
            self.logger.emit("emg_upload_queue_drop")
            return False

    def queue_emg_samples(self, samples: list[list[int]], sample_rate_hz: int = 500) -> bool:
        if not self.collecting or not self.session_id:
            return False
        return self.queue_emg({
            "session_id": self.session_id,
            "gesture_name": self.gesture_name,
            "sample_rate_hz": int(sample_rate_hz),
            "sequence_no": self.sequence_no,
            "is_final": False,
            "samples": samples,
        })

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick_once()
            self._stop.wait(self.heartbeat_interval_s)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="duo-network-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
