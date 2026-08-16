"""
routers/health.py - 健康数据 & 报告接口
  POST /health/report/generate   生成健康报告（基于最近 EMG 数据分析）
  GET  /health/records           查询历史健康记录
"""
import random

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import Device, get_db, HealthRecord, User
from deps import get_current_user

router = APIRouter(prefix="/health", tags=["health"])


class ReportIn(BaseModel):
    user_id: int | None = None   # 兼容旧调用，实际以 JWT 用户为准


@router.post("/report/generate")
def generate_report(
    body:         ReportIn | None = Body(default=None),
    user_id:      int | None = None,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """为已绑定设备的用户生成并保存一份演示肌肉健康报告。"""
    requested_user_id = user_id or (body.user_id if body else None)
    if requested_user_id and (current_user.role or "user") == "admin":
        target_user = db.query(User).filter(User.id == requested_user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="用户不存在")
        uid = target_user.id
    else:
        uid = current_user.id

    device = (
        db.query(Device)
        .filter(Device.user_id == uid)
        .order_by(Device.updated_at.desc(), Device.id.desc())
        .first()
    )
    if not device:
        raise HTTPException(status_code=400, detail="请先绑定设备，再生成肌肉健康报告")

    rms = round(random.uniform(155, 175), 1)
    side = round(random.uniform(35, 58), 1)
    muscle_status = "正常"
    diagnostics = "演示评估数据：肌电强度与侧压力处于合理范围，肌肉状态正常，建议保持规律训练。"

    # 写入健康记录
    record = HealthRecord(
        user_id       = uid,
        rms_value     = rms,
        side_presure  = side,
        muscle_status = muscle_status,
        diagnostics   = diagnostics,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "report_id":    record.id,
        "user_id":      uid,
        "hardware_id":  device.hardware_id,
        "device_name":  device.device_name or device.hardware_id,
        "rms_value":     rms,
        "side_pressure": side,
        "side_presure":  side,
        "muscle_status": muscle_status,
        "diagnostics":   diagnostics,
        "data_source":   "simulated",
        "generated_at":  record.recorded_at.isoformat(),
    }


@router.get("/records")
def get_records(
    limit:        int  = 20,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == current_user.id)
        .order_by(HealthRecord.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "records": [
            {
                "id":            r.id,
                "rms_value":     r.rms_value,
                "side_presure":  r.side_presure,
                "muscle_status": r.muscle_status,
                "diagnostics":   r.diagnostics,
                "recorded_at":   r.recorded_at.isoformat(),
            }
            for r in records
        ]
    }
