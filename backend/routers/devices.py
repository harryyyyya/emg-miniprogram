"""
Device binding, ESP32 Wi-Fi telemetry, command, and EMG upload endpoints.
"""
from __future__ import annotations

import json
import struct
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import get_current_user
from models import Device, EmgCollectionBatch, EmgCollectionSession, TrainingSession, User, get_db

router = APIRouter(prefix="/devices", tags=["devices"])

DEVICE_OFFLINE_TIMEOUT = timedelta(seconds=15)
ESP32_EMG_DIR = Path("uploads/esp32_emg")
ESP32_EMG_DIR.mkdir(parents=True, exist_ok=True)


class BindIn(BaseModel):
    user_id: int | None = None
    hardware_id: str
    transport: str = "ble"
    device_name: str = ""
    board_token: str = ""
    wifi_host: str = ""
    wifi_port: int = 0


class BoardRegisterIn(BaseModel):
    hardware_id: str
    board_token: str
    firmware_version: str = ""
    wifi_host: str = ""
    wifi_port: int = 0


class HeartbeatIn(BaseModel):
    hardware_id: str
    board_token: str
    ip_address: str = ""
    firmware_version: str = ""
    battery_level: int | None = None
    signal_strength: int | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class CommandIn(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandAckIn(BaseModel):
    hardware_id: str
    board_token: str
    command_id: str
    success: bool = True
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class Esp32EmgUploadIn(BaseModel):
    hardware_id: str
    board_token: str
    session_id: str
    gesture_name: str = ""
    sequence_no: int = 0
    sample_rate_hz: int | None = None
    samples: list[list[int]] = Field(default_factory=list)
    is_final: bool = False


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_transport(value: str) -> str:
    transport = (value or "ble").strip().lower()
    if transport not in {"ble", "wifi"}:
        raise HTTPException(status_code=400, detail="transport only supports ble or wifi")
    return transport


def _parse_json_blob(raw: str | None, default: Any):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _effective_status(device: Device) -> str:
    if device.transport != "wifi":
        return "online" if device.status == "online" else "offline"
    if not device.last_seen_at:
        return "offline"
    return "online" if _now() - device.last_seen_at <= DEVICE_OFFLINE_TIMEOUT else "offline"


def _serialize_device(device: Device) -> dict[str, Any]:
    return {
        "hardware_id": device.hardware_id,
        "device_name": device.device_name or device.hardware_id,
        "transport": device.transport or "ble",
        "status": _effective_status(device),
        "bind_time": device.bind_time.isoformat() if device.bind_time else None,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "wifi_host": device.wifi_host or "",
        "wifi_port": device.wifi_port or 0,
        "firmware_version": device.firmware_version or "",
        "last_ip": device.last_ip or "",
        "battery_level": device.battery_level,
        "signal_strength": device.signal_strength,
        "telemetry": _parse_json_blob(device.telemetry_json, {}),
        "last_command_ack": _parse_json_blob(device.last_command_ack_json, {}),
    }


def _get_owned_device(db: Session, user_id: int, hardware_id: str) -> Device:
    device = db.query(Device).filter(
        Device.hardware_id == hardware_id,
        Device.user_id == user_id,
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="device not found for current user")
    return device


def _get_board_device(db: Session, hardware_id: str, board_token: str) -> Device:
    device = db.query(Device).filter(Device.hardware_id == hardware_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="device not bound")
    if (device.transport or "ble") != "wifi":
        raise HTTPException(status_code=400, detail="device is not configured for wifi")
    if not device.board_token or device.board_token != board_token:
        raise HTTPException(status_code=401, detail="invalid board_token")
    return device


def _build_pending_command(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "command_id": uuid.uuid4().hex,
        "action": action,
        "payload": payload,
        "status": "pending",
        "created_at": _now().isoformat(),
    }


def _update_wifi_presence(device: Device, body: HeartbeatIn | BoardRegisterIn, *, ip_address: str = "") -> None:
    device.transport = "wifi"
    if body.firmware_version:
        device.firmware_version = body.firmware_version
    if getattr(body, "wifi_host", ""):
        device.wifi_host = body.wifi_host
    if getattr(body, "wifi_port", 0):
        device.wifi_port = body.wifi_port
    if ip_address:
        device.last_ip = ip_address
    device.status = "online"
    device.last_seen_at = _now()
    device.updated_at = _now()


def _normalize_telemetry(raw: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    telemetry = dict(existing or {})
    telemetry.update(raw or {})

    module_statuses = telemetry.get("module_statuses") or telemetry.get("modules") or {}
    if not isinstance(module_statuses, dict):
        module_statuses = {}

    mapping = {
        "storage": ["storage", "storage_status", "flash", "flash_status", "memory"],
        "model": ["model", "model_status", "model_loader"],
        "bluetooth": ["bluetooth", "bluetooth_status", "ble", "ble_status", "armband_ble"],
        "cpu": ["cpu", "cpu_status", "inference", "inference_status", "cpu_model"],
    }
    for target, aliases in mapping.items():
        if target in module_statuses and module_statuses[target]:
            continue
        for alias in aliases:
            value = telemetry.get(alias)
            if value not in (None, ""):
                module_statuses[target] = value
                break

    telemetry["module_statuses"] = module_statuses
    telemetry["prediction_result"] = (
        telemetry.get("prediction_result")
        or telemetry.get("prediction")
        or telemetry.get("gesture_result")
        or telemetry.get("mode_result")
        or ""
    )
    telemetry["prediction_confidence"] = (
        telemetry.get("prediction_confidence")
        or telemetry.get("confidence")
        or telemetry.get("score")
        or None
    )

    collect_state = telemetry.get("collect_state") or {}
    if not isinstance(collect_state, dict):
        collect_state = {}
    telemetry["collect_state"] = collect_state
    return telemetry


def _session_data_path(session_id: str) -> Path:
    return ESP32_EMG_DIR / f"{session_id}.dat"


def _session_meta_path(session_id: str) -> Path:
    return ESP32_EMG_DIR / f"{session_id}.json"


def _load_session_meta(session_id: str) -> dict[str, Any]:
    path = _session_meta_path(session_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_session_meta(session_id: str, meta: dict[str, Any]) -> None:
    _session_meta_path(session_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _unlink_file(path: str | Path | None) -> None:
    if not path:
        return
    try:
        target = Path(path)
        if target.exists() and target.is_file():
            target.unlink()
    except OSError:
        pass


def _validate_samples(samples: list[list[int]]) -> tuple[int, int]:
    if not samples:
        return 0, 0
    channel_count = len(samples[0])
    if channel_count <= 0:
        raise HTTPException(status_code=400, detail="samples must contain at least one channel")
    for row in samples:
        if len(row) != channel_count:
            raise HTTPException(status_code=400, detail="all sample rows must have equal channel count")
    return len(samples), channel_count


def _append_samples(path: Path, samples: list[list[int]]) -> None:
    if not samples:
        return
    with open(path, "ab") as fh:
        for row in samples:
            packed = struct.pack(f"<{len(row)}h", *[int(v) for v in row])
            fh.write(packed)


def _calculate_rms(samples: list[list[int]]) -> float:
    if not samples or not samples[0]:
        return 0.0
    total_sq = 0.0
    count = 0
    for row in samples:
        for value in row:
            total_sq += float(value) * float(value)
            count += 1
    return round((total_sq / count) ** 0.5, 2) if count else 0.0


def _trim_preview_samples(samples: list[list[int]], limit: int = 24) -> list[list[int]]:
    if not samples:
        return []
    return [list(map(int, row)) for row in samples[-limit:]]


def _samples_to_json(samples: list[list[int]]) -> str:
    return json.dumps([[int(v) for v in row] for row in samples], ensure_ascii=False)


def _upsert_emg_collection_batch(
    db: Session,
    *,
    device: Device,
    body: Esp32EmgUploadIn,
    sample_count: int,
    channel_count: int,
    batch_rms: float,
) -> EmgCollectionBatch:
    record = (
        db.query(EmgCollectionBatch)
        .filter(
            EmgCollectionBatch.session_id == body.session_id,
            EmgCollectionBatch.sequence_no == body.sequence_no,
        )
        .first()
    )
    if not record:
        record = EmgCollectionBatch(
            session_id=body.session_id,
            user_id=device.user_id,
            hardware_id=body.hardware_id,
            transport="wifi",
            sequence_no=body.sequence_no,
        )
        db.add(record)

    record.sample_count = sample_count
    record.channel_count = channel_count
    record.sample_rate_hz = body.sample_rate_hz or 0
    record.rms_value = batch_rms
    record.samples_json = _samples_to_json(body.samples)
    record.is_final = bool(body.is_final)
    record.hardware_id = body.hardware_id
    record.transport = "wifi"
    return record


def _upsert_emg_collection_session(
    db: Session,
    *,
    device: Device,
    session_id: str,
    gesture_name: str,
    sample_rate_hz: int | None,
    channel_count: int,
    batch_count: int,
    total_samples: int,
    batch_rms: float,
    completed: bool,
    file_path: str,
    preview_samples: list[list[int]],
) -> EmgCollectionSession:
    record = db.query(EmgCollectionSession).filter(EmgCollectionSession.session_id == session_id).first()
    if not record:
        record = EmgCollectionSession(
            session_id=session_id,
            user_id=device.user_id,
            hardware_id=device.hardware_id,
            transport="wifi",
            source="wifi",
        )
        db.add(record)

    record.user_id = device.user_id
    record.hardware_id = device.hardware_id
    record.transport = "wifi"
    record.source = "wifi"
    record.gesture_name = gesture_name
    record.sample_rate_hz = sample_rate_hz or 0
    record.channel_count = channel_count
    record.batch_count = batch_count
    record.total_samples = total_samples
    record.rms_value = batch_rms
    record.file_path = file_path
    record.preview_json = _samples_to_json(_trim_preview_samples(preview_samples))
    record.is_completed = completed
    return record


def _serialize_emg_session(record: EmgCollectionSession) -> dict[str, Any]:
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "hardware_id": record.hardware_id or "",
        "transport": record.transport or "wifi",
        "source": record.source or "wifi",
        "gesture_name": record.gesture_name or "",
        "sample_rate_hz": record.sample_rate_hz or 0,
        "channel_count": record.channel_count or 0,
        "batch_count": record.batch_count or 0,
        "total_samples": record.total_samples or 0,
        "rms_value": record.rms_value or 0.0,
        "file_path": record.file_path or "",
        "preview": _parse_json_blob(record.preview_json, []),
        "is_completed": bool(record.is_completed),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _finalize_training_session(
    db: Session,
    *,
    device: Device,
    session_id: str,
    gesture_name: str,
    batch_count: int,
) -> TrainingSession:
    record = db.query(TrainingSession).filter(TrainingSession.session_id == session_id).first()
    if record:
        record.gesture_name = gesture_name or record.gesture_name
        record.total_chunks = batch_count
        record.file_path = str(_session_data_path(session_id))
        return record

    record = TrainingSession(
        session_id=session_id,
        user_id=device.user_id,
        gesture_name=gesture_name,
        file_path=str(_session_data_path(session_id)),
        total_chunks=batch_count,
    )
    db.add(record)
    return record


@router.post("/bind")
def bind_device(
    body: BindIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id
    transport = _normalize_transport(body.transport)

    existing = db.query(Device).filter(Device.hardware_id == body.hardware_id).first()
    if existing:
        existing.user_id = uid
        existing.transport = transport
        existing.device_name = body.device_name or existing.device_name or body.hardware_id
        existing.bind_time = _now()
        existing.updated_at = _now()
        if transport == "wifi":
            existing.board_token = body.board_token or existing.board_token
            existing.wifi_host = body.wifi_host or existing.wifi_host
            existing.wifi_port = body.wifi_port or existing.wifi_port
        db.commit()
        db.refresh(existing)
        return {"message": "device rebound", "device": _serialize_device(existing)}

    device = Device(
        user_id=uid,
        hardware_id=body.hardware_id,
        device_name=body.device_name or body.hardware_id,
        transport=transport,
        board_token=body.board_token if transport == "wifi" else "",
        wifi_host=body.wifi_host if transport == "wifi" else "",
        wifi_port=body.wifi_port if transport == "wifi" else 0,
        status="offline",
        telemetry_json="{}",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {"message": "device bound", "device": _serialize_device(device)}


@router.get("/mine")
def my_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    devices = db.query(Device).filter(Device.user_id == current_user.id).all()
    return {"devices": [_serialize_device(device) for device in devices]}


@router.get("/emg/sessions")
def list_emg_sessions(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(EmgCollectionSession)
        .filter(EmgCollectionSession.user_id == current_user.id)
        .order_by(EmgCollectionSession.updated_at.desc(), EmgCollectionSession.created_at.desc())
        .limit(max(1, min(int(limit or 10), 50)))
        .all()
    )
    return {"sessions": [_serialize_emg_session(record) for record in sessions]}


@router.get("/emg/sessions/{session_id}")
def get_emg_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        db.query(EmgCollectionSession)
        .filter(
            EmgCollectionSession.session_id == session_id,
            EmgCollectionSession.user_id == current_user.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": _serialize_emg_session(record)}


@router.delete("/emg/sessions/{session_id}")
def delete_emg_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        db.query(EmgCollectionSession)
        .filter(
            EmgCollectionSession.session_id == session_id,
            EmgCollectionSession.user_id == current_user.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="session not found")

    file_path = record.file_path
    db.query(EmgCollectionBatch).filter(
        EmgCollectionBatch.session_id == session_id,
        EmgCollectionBatch.user_id == current_user.id,
    ).delete(synchronize_session=False)
    db.query(TrainingSession).filter(
        TrainingSession.session_id == session_id,
        TrainingSession.user_id == current_user.id,
    ).delete(synchronize_session=False)
    db.delete(record)
    db.commit()

    _unlink_file(file_path)
    _unlink_file(_session_data_path(session_id))
    _unlink_file(_session_meta_path(session_id))
    return {"message": "session deleted", "session_id": session_id}


@router.get("/{hardware_id}/status")
def get_device_status(
    hardware_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = _get_owned_device(db, current_user.id, hardware_id)
    return {"device": _serialize_device(device)}


@router.post("/{hardware_id}/command")
def push_device_command(
    hardware_id: str,
    body: CommandIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = _get_owned_device(db, current_user.id, hardware_id)
    if (device.transport or "ble") != "wifi":
        raise HTTPException(status_code=400, detail="current device is not a wifi device")

    command = _build_pending_command(body.action, body.payload)
    device.pending_command_json = json.dumps(command, ensure_ascii=False)
    device.updated_at = _now()
    db.commit()
    return {"message": "command queued", "command": command}


@router.delete("/{hardware_id}")
def unbind_device(
    hardware_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = _get_owned_device(db, current_user.id, hardware_id)
    db.delete(device)
    db.commit()
    return {"message": "device unbound"}


@router.post("/wifi/register")
def wifi_register(
    body: BoardRegisterIn,
    db: Session = Depends(get_db),
):
    device = _get_board_device(db, body.hardware_id, body.board_token)
    _update_wifi_presence(device, body)
    db.commit()
    db.refresh(device)
    return {"message": "register ok", "device": _serialize_device(device)}


@router.post("/wifi/heartbeat")
def wifi_heartbeat(
    body: HeartbeatIn,
    db: Session = Depends(get_db),
):
    device = _get_board_device(db, body.hardware_id, body.board_token)
    _update_wifi_presence(device, body, ip_address=body.ip_address)
    device.battery_level = body.battery_level
    device.signal_strength = body.signal_strength

    existing_telemetry = _parse_json_blob(device.telemetry_json, {})
    telemetry = _normalize_telemetry(body.telemetry, existing_telemetry)
    if telemetry:
        device.telemetry_json = json.dumps(telemetry, ensure_ascii=False)

    db.commit()
    db.refresh(device)

    pending = _parse_json_blob(device.pending_command_json, None)
    return {
        "message": "heartbeat ok",
        "status": _effective_status(device),
        "server_time": _now().isoformat(),
        "pending_command": pending,
    }


@router.post("/wifi/emg")
def wifi_emg_upload(
    body: Esp32EmgUploadIn,
    db: Session = Depends(get_db),
):
    device = _get_board_device(db, body.hardware_id, body.board_token)
    _update_wifi_presence(device, BoardRegisterIn(
        hardware_id=body.hardware_id,
        board_token=body.board_token,
        firmware_version="",
        wifi_host=device.wifi_host or "",
        wifi_port=device.wifi_port or 0,
    ))

    sample_count, channel_count = _validate_samples(body.samples)
    batch_rms = _calculate_rms(body.samples)
    data_path = _session_data_path(body.session_id)
    _append_samples(data_path, body.samples)

    meta = _load_session_meta(body.session_id)
    batch_count = int(meta.get("batch_count", 0)) + (1 if sample_count > 0 else 0)
    total_samples = int(meta.get("total_samples", 0)) + sample_count
    gesture_name = body.gesture_name or meta.get("gesture_name", "")
    preview_samples = _trim_preview_samples(body.samples)
    meta.update({
        "session_id": body.session_id,
        "hardware_id": body.hardware_id,
        "user_id": device.user_id,
        "gesture_name": gesture_name,
        "batch_count": batch_count,
        "total_samples": total_samples,
        "channel_count": channel_count or int(meta.get("channel_count", 0) or 0),
        "sample_rate_hz": body.sample_rate_hz or meta.get("sample_rate_hz"),
        "file_path": str(data_path),
        "updated_at": _now().isoformat(),
        "completed": bool(body.is_final),
    })
    if "created_at" not in meta:
        meta["created_at"] = _now().isoformat()
    _save_session_meta(body.session_id, meta)

    telemetry = _normalize_telemetry({}, _parse_json_blob(device.telemetry_json, {}))
    telemetry["rms_value"] = batch_rms
    telemetry["emg_preview"] = preview_samples
    telemetry["emg_preview_sequence_no"] = body.sequence_no
    telemetry["emg_preview_sample_rate_hz"] = body.sample_rate_hz or telemetry.get("emg_preview_sample_rate_hz")
    telemetry["emg_preview_updated_at"] = _now().isoformat()
    telemetry["collect_state"] = {
        "session_id": body.session_id,
        "gesture_name": gesture_name,
        "batch_count": batch_count,
        "sample_count": total_samples,
        "channel_count": meta["channel_count"],
        "last_batch_rms": batch_rms,
        "recording": not body.is_final,
        "updated_at": _now().isoformat(),
    }
    if body.is_final:
        telemetry["last_collection"] = dict(telemetry["collect_state"])
        telemetry["last_collection"]["recording"] = False
    device.telemetry_json = json.dumps(telemetry, ensure_ascii=False)
    device.updated_at = _now()

    _upsert_emg_collection_batch(
        db,
        device=device,
        body=body,
        sample_count=sample_count,
        channel_count=channel_count,
        batch_rms=batch_rms,
    )
    _upsert_emg_collection_session(
        db,
        device=device,
        session_id=body.session_id,
        gesture_name=gesture_name,
        sample_rate_hz=body.sample_rate_hz,
        channel_count=channel_count,
        batch_count=batch_count,
        total_samples=total_samples,
        batch_rms=batch_rms,
        completed=bool(body.is_final),
        file_path=str(data_path),
        preview_samples=preview_samples,
    )

    if body.is_final:
        _finalize_training_session(
            db,
            device=device,
            session_id=body.session_id,
            gesture_name=gesture_name,
            batch_count=batch_count,
        )

    db.commit()
    return {
        "message": "emg batch received",
        "session_id": body.session_id,
        "sample_count": sample_count,
        "total_samples": total_samples,
        "channel_count": channel_count,
        "batch_rms": batch_rms,
        "completed": body.is_final,
    }


@router.post("/wifi/command/ack")
def wifi_command_ack(
    body: CommandAckIn,
    db: Session = Depends(get_db),
):
    device = _get_board_device(db, body.hardware_id, body.board_token)
    pending = _parse_json_blob(device.pending_command_json, {})

    if not pending or pending.get("command_id") != body.command_id:
        raise HTTPException(status_code=404, detail="pending command not found")

    ack = {
        "command_id": body.command_id,
        "success": body.success,
        "message": body.message,
        "result": body.result,
        "acked_at": _now().isoformat(),
    }
    device.pending_command_json = ""
    device.last_command_ack_json = json.dumps(ack, ensure_ascii=False)
    device.status = "online"
    device.last_seen_at = _now()
    device.updated_at = _now()
    db.commit()
    return {"message": "ack ok", "ack": ack}
