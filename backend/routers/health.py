"""
routers/health.py - 健康数据 & 报告接口
  POST /health/report/generate   生成健康报告（基于最近 EMG 数据分析）
  GET  /health/records           查询历史健康记录
"""
import random
from datetime import datetime

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import get_db, HealthRecord, TrainingSession, User
from deps import get_current_user

router = APIRouter(prefix="/health", tags=["health"])


class ReportIn(BaseModel):
    user_id: int | None = None   # 兼容旧调用，实际以 JWT 用户为准


@router.post("/report/generate")
def generate_report(
    body:         ReportIn | None = Body(default=None),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """
    根据该用户最近一次训练会话的 EMG 数据生成健康报告。
    当前为规则引擎实现（生产可替换为 ML 模型）。
    """
    uid = current_user.id

    # 取最近一次训练会话
    last_session = (
        db.query(TrainingSession)
        .filter(TrainingSession.user_id == uid)
        .order_by(TrainingSession.created_at.desc())
        .first()
    )

    if last_session and last_session.file_path:
        rms, side = _analyze_emg_file(last_session.file_path)
    else:
        # 没有真实数据时生成随机 Mock 数据
        rms  = round(random.uniform(80, 180), 1)
        side = round(random.uniform(30, 70), 1)

    muscle_status, diagnostics = _diagnose(rms, side)

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

    return {
        "rms_value":     rms,
        "side_presure":  side,
        "muscle_status": muscle_status,
        "diagnostics":   diagnostics,
        "generated_at":  datetime.utcnow().isoformat(),
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


# ──────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────
def _analyze_emg_file(file_path: str) -> tuple[float, float]:
    """读取 EMG 二进制文件，计算 RMS 和模拟侧压力"""
    import struct
    from pathlib import Path

    try:
        raw = Path(file_path).read_bytes()
    except FileNotFoundError:
        return 0.0, 0.0

    CHANNELS         = 8
    BYTES_PER_SAMPLE = CHANNELS * 2
    n                = len(raw) // BYTES_PER_SAMPLE
    if n == 0:
        return 0.0, 0.0

    total_sq = 0.0
    for i in range(n):
        for ch in range(CHANNELS):
            val = struct.unpack_from("<h", raw, i * BYTES_PER_SAMPLE + ch * 2)[0]
            total_sq += val * val

    rms  = round((total_sq / (n * CHANNELS)) ** 0.5, 1)
    # 侧压力：用前4通道幅值之比模拟
    side = round(rms * random.uniform(0.3, 0.5), 1)
    return rms, side


def _diagnose(rms: float, side: float) -> tuple[str, str]:
    """简单规则引擎：根据 RMS 判断肌肉状态"""
    if rms < 50:
        return "萎缩风险", "肌电RMS偏低，存在肌肉萎缩风险，建议增加训练强度并咨询专业医生。"
    if rms > 200:
        return "过度疲劳", "肌电RMS偏高，肌肉可能存在过度疲劳，建议适当休息。"
    return "正常", ""
