"""
Web admin/user compatibility APIs.

These endpoints adapt the existing mini-program database tables for the Vue web
frontend, so the mini program, ESP32 bridge, and web dashboard share one DB.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from deps import get_current_user
from models import (
    Device,
    EmgCollectionSession,
    ErrorLog,
    ForumComment,
    ForumPost,
    HealthRecord,
    PostLike,
    TrainingSession,
    User,
    get_db,
)

router = APIRouter(tags=["web"])

DEVICE_OFFLINE_SECONDS = 15


def _require_admin(user: User) -> None:
    if (user.role or "user") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


def _dt(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _parse_json(raw: str | None, default: Any):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _device_online(device: Device) -> bool:
    if (device.transport or "ble") != "wifi":
        return (device.status or "offline") == "online"
    if not device.last_seen_at:
        return False
    return datetime.utcnow() - device.last_seen_at <= timedelta(seconds=DEVICE_OFFLINE_SECONDS)


def _device_row(device: Device) -> dict[str, Any]:
    telemetry = _parse_json(device.telemetry_json, {})
    return {
        "id": device.id,
        "user_id": device.user_id,
        "user_name": device.user.name if device.user else f"用户#{device.user_id}",
        "hardware_id": device.hardware_id,
        "device_name": device.device_name or device.hardware_id,
        "transport": device.transport or "ble",
        "battery_level": device.battery_level if device.battery_level is not None else 0,
        "firmware_version": device.firmware_version or "-",
        "status": "online" if _device_online(device) else "offline",
        "is_online": _device_online(device),
        "last_seen_at": _dt(device.last_seen_at),
        "rms_value": telemetry.get("rms_value"),
        "prediction_result": telemetry.get("prediction_result", ""),
    }


@router.get("/devices")
def list_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Device).join(User, Device.user_id == User.id, isouter=True)
    if (current_user.role or "user") != "admin":
        query = query.filter(Device.user_id == current_user.id)
    devices = query.order_by(Device.updated_at.desc(), Device.id.desc()).all()
    return [_device_row(device) for device in devices]


def _training_row_from_emg(session: EmgCollectionSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "user_name": session.user.name if session.user else f"用户#{session.user_id}",
        "hardware_id": session.hardware_id or "",
        "gesture_name": session.gesture_name or "",
        "raw_data_path": session.file_path or "",
        "status": "completed" if session.is_completed else "collecting",
        "created_at": _dt(session.created_at),
        "updated_at": _dt(session.updated_at),
        "total_samples": session.total_samples or 0,
        "batch_count": session.batch_count or 0,
        "rms_value": session.rms_value or 0,
    }


def _training_row_from_legacy(session: TrainingSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "user_name": session.user.name if getattr(session, "user", None) else f"用户#{session.user_id}",
        "hardware_id": "",
        "gesture_name": session.gesture_name or "",
        "raw_data_path": session.file_path or "",
        "status": "completed" if session.file_path else "queued",
        "created_at": _dt(session.created_at),
        "updated_at": _dt(session.created_at),
        "total_samples": 0,
        "batch_count": session.total_chunks or 0,
        "rms_value": 0,
    }


@router.get("/training/sessions")
def list_training_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_admin = (current_user.role or "user") == "admin"
    emg_query = db.query(EmgCollectionSession).join(User, EmgCollectionSession.user_id == User.id, isouter=True)
    legacy_query = db.query(TrainingSession).join(User, TrainingSession.user_id == User.id, isouter=True)
    if not is_admin:
        emg_query = emg_query.filter(EmgCollectionSession.user_id == current_user.id)
        legacy_query = legacy_query.filter(TrainingSession.user_id == current_user.id)

    rows_by_id: dict[str, dict[str, Any]] = {}
    for session in emg_query.order_by(EmgCollectionSession.updated_at.desc()).limit(100).all():
        rows_by_id[session.session_id] = _training_row_from_emg(session)
    for session in legacy_query.order_by(TrainingSession.created_at.desc()).limit(100).all():
        rows_by_id.setdefault(session.session_id, _training_row_from_legacy(session))

    return sorted(
        rows_by_id.values(),
        key=lambda row: row.get("updated_at") or row.get("created_at") or "",
        reverse=True,
    )


@router.get("/health/logs/{user_id}")
def list_health_logs(
    user_id: int,
    range: str = "7d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (current_user.role or "user") != "admin":
        user_id = current_user.id

    hours = 24 if range == "24h" else 24 * 7
    start = datetime.utcnow() - timedelta(hours=hours)
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id, HealthRecord.recorded_at >= start)
        .order_by(HealthRecord.recorded_at.asc())
        .all()
    )
    return [
        {
            "id": item.id,
            "user_id": item.user_id,
            "rms_value": item.rms_value or 0,
            "side_pressure": item.side_presure or 0,
            "side_presure": item.side_presure or 0,
            "muscle_status_label": item.muscle_status or "正常",
            "muscle_status": item.muscle_status or "正常",
            "diagnostics": item.diagnostics or "",
            "created_at": _dt(item.recorded_at),
        }
        for item in records
    ]


class ErrorLogIn(BaseModel):
    hardware_id: str = ""
    error_code: str = "UNKNOWN"
    error_msg: str = ""
    level: str = "warning"


@router.post("/logs/error")
def create_error_log(body: ErrorLogIn, db: Session = Depends(get_db)):
    item = ErrorLog(
        hardware_id=body.hardware_id,
        error_code=body.error_code,
        error_msg=body.error_msg,
        level=body.level,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "error log saved", "id": item.id}


@router.get("/logs/error")
def list_error_logs(
    page: int = 1,
    pageSize: int = 10,
    startDate: str | None = None,
    endDate: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    query = db.query(ErrorLog)
    if startDate:
        query = query.filter(ErrorLog.created_at >= datetime.fromisoformat(startDate))
    if endDate:
        query = query.filter(ErrorLog.created_at < datetime.fromisoformat(endDate) + timedelta(days=1))

    total = query.count()
    size = max(1, min(int(pageSize or 10), 2000))
    offset = max(0, int(page or 1) - 1) * size
    items = query.order_by(ErrorLog.created_at.desc()).offset(offset).limit(size).all()
    return {
        "total": total,
        "items": [
            {
                "id": item.id,
                "hardware_id": item.hardware_id,
                "error_code": item.error_code,
                "error_msg": item.error_msg,
                "level": item.level,
                "created_at": _dt(item.created_at),
            }
            for item in items
        ],
    }


@router.post("/logs/error/analyze")
def analyze_error_logs(
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    rows = db.query(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(2000).all()
    counts = Counter(row.error_code or "UNKNOWN" for row in rows)
    total = sum(counts.values()) or 1
    colors = ["#ef4444", "#f59e0b", "#6366f1", "#06b6d4", "#334155"]
    clusters = [
        {"name": key, "pct": round(value * 100 / total, 1), "color": colors[index % len(colors)]}
        for index, (key, value) in enumerate(counts.most_common(5))
    ]
    if not clusters:
        clusters = [{"name": "暂无错误", "pct": 100, "color": "#22c55e"}]

    report = "当前暂无错误日志，系统运行平稳。"
    if rows:
        top = clusters[0]["name"]
        report = (
            f"最近共分析 {len(rows)} 条错误日志，出现最多的是 {top}。"
            "建议先检查对应设备的 Wi-Fi/蓝牙连接、电量和 ESP32 串口日志，再复测心跳与肌电数据上报。"
        )
    return {"clusters": clusters, "report": report}


@router.get("/admin/seed/status")
def seed_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    return {
        "users": db.query(User).count(),
        "devices": db.query(Device).count(),
        "health_logs": db.query(HealthRecord).count(),
        "forum_posts": db.query(ForumPost).count(),
        "training_sessions": db.query(TrainingSession).count() + db.query(EmgCollectionSession).count(),
    }


@router.post("/admin/seed/{entity}")
def seed_entity(
    entity: str,
    rows: list[dict[str, Any]] = Body(default_factory=list),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    created = 0
    for row in rows:
        if entity == "users":
            user = User(name=row.get("name") or "示例用户", role="user")
            db.add(user)
            created += 1
        elif entity == "devices":
            db.add(Device(
                user_id=int(row.get("user_id") or current_user.id),
                hardware_id=row.get("hardware_id") or f"ESP32-DEMO-{created + 1}",
                device_name=row.get("hardware_id") or f"演示设备{created + 1}",
                transport="wifi",
                battery_level=int(row.get("battery_level") or 80),
                firmware_version=row.get("firmware_version") or "demo",
                status="offline",
            ))
            created += 1
        elif entity == "health_logs":
            db.add(HealthRecord(
                user_id=int(row.get("user_id") or current_user.id),
                rms_value=float(row.get("rms_value") or 0),
                side_presure=float(row.get("side_pressure") or row.get("side_presure") or 0),
                muscle_status=row.get("muscle_status_label") or row.get("muscle_status") or "正常",
            ))
            created += 1
        elif entity == "forum_posts":
            db.add(ForumPost(
                user_id=int(row.get("user_id") or current_user.id),
                content=row.get("content") or row.get("title") or "示例帖子",
                image_urls="[]",
            ))
            created += 1
        elif entity == "training_sessions":
            db.add(TrainingSession(
                session_id=row.get("session_id") or f"demo_session_{datetime.utcnow().timestamp()}_{created}",
                user_id=int(row.get("user_id") or current_user.id),
                gesture_name=row.get("gesture_name") or "",
                file_path=row.get("raw_data_path") or "",
                total_chunks=1,
            ))
            created += 1
        else:
            raise HTTPException(status_code=404, detail="未知种子数据类型")
    db.commit()
    return {"message": "seed ok", "created": created}


@router.delete("/admin/seed/{entity}")
def reset_entity(entity: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    model_map = {
        "users": User,
        "devices": Device,
        "health_logs": HealthRecord,
        "forum_posts": ForumPost,
        "training_sessions": TrainingSession,
    }
    model = model_map.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="未知种子数据类型")

    if entity == "forum_posts":
        db.query(PostLike).delete(synchronize_session=False)
        db.query(ForumComment).delete(synchronize_session=False)
    deleted = db.query(model).delete(synchronize_session=False)
    db.commit()
    return {"message": "reset ok", "deleted": deleted}
