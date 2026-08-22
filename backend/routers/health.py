"""Health records and real-time sEMG analysis endpoints."""
import json
import math
import os
import random
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import get_current_user
from models import Device, get_db, HealthRecord, User

try:  # Keep the API importable in a minimal environment; production installs these from requirements.txt.
    import numpy as np
    from scipy import signal
except ImportError:  # pragma: no cover - exercised only when dependencies are missing.
    np = None
    signal = None

router = APIRouter(prefix="/health", tags=["health"])
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class ReportIn(BaseModel):
    user_id: int | None = None   # 兼容旧调用，实际以 JWT 用户为准


class AnalyzeIn(BaseModel):
    samples: list[list[float]] = Field(default_factory=list)
    sample_rate_hz: int = Field(default=500, ge=100, le=2000)
    hardware_id: str = ""
    side_pressure: float | None = None
    include_ai: bool = False
    persist: bool = False


def _finite(value: float, default: float = 0.0) -> float:
    value = float(value)
    return value if math.isfinite(value) else default


def _format_beijing_time(value: datetime | None) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING_TZ).isoformat(timespec="seconds")


def _validate_samples(samples: list[list[float]]):
    if np is None or signal is None:
        raise HTTPException(status_code=503, detail="后端缺少 numpy/scipy，请先安装 requirements.txt 依赖")
    if len(samples) < 32:
        raise HTTPException(status_code=422, detail="实时分析至少需要 32 个采样点")
    if len(samples) > 5000:
        samples = samples[-5000:]
    if any(len(row) != 8 for row in samples):
        raise HTTPException(status_code=422, detail="肌电数据必须是 8 通道数组")
    try:
        matrix = np.asarray(samples, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="肌电数据包含无法解析的数值") from exc
    if not np.isfinite(matrix).all():
        raise HTTPException(status_code=422, detail="肌电数据包含 NaN 或无穷值")
    return matrix


def _window_features(window, fs: int) -> dict[str, float]:
    rms = float(np.sqrt(np.mean(window ** 2)))
    mav = float(np.mean(np.abs(window)))
    signs = np.sign(window)
    zc = float(np.count_nonzero(np.diff(signs) != 0))
    diff_signal = np.diff(window)
    ssc = float(np.count_nonzero(np.diff(np.sign(diff_signal)) != 0)) if len(diff_signal) > 1 else 0.0
    wl = float(np.sum(np.abs(diff_signal)))

    if len(window) >= 16:
        freqs, psd = signal.welch(window, fs=fs, nperseg=min(len(window), 256))
        total_power = float(np.sum(psd))
        if total_power > 0 and np.isfinite(total_power):
            cumulative = np.cumsum(psd)
            mf = float(freqs[np.searchsorted(cumulative, total_power / 2)])
            mnf = float(np.sum(freqs * psd) / total_power)
        else:
            mf = 0.0
            mnf = 0.0
    else:
        mf = 0.0
        mnf = 0.0
        total_power = 0.0

    return {"rms": rms, "mav": mav, "zc": zc, "ssc": ssc, "wl": wl, "mf": mf, "mnf": mnf, "total_power": total_power}


def _score(value: float) -> float:
    return round(max(0.0, min(100.0, _finite(value))), 1)


def _analyze_matrix(matrix, fs: int) -> dict[str, Any]:
    # The supplied reference code uses 20-450 Hz at 500 Hz. Since Nyquist is 250 Hz,
    # clamp the high cutoff to keep the filter valid while retaining the available band.
    centered = matrix - np.median(matrix, axis=0)
    nyquist = fs / 2.0
    high_cut = min(450.0, nyquist - 1.0)
    filtered = centered
    if high_cut > 20.0 and len(matrix) >= 64:
        try:
            b_band, a_band = signal.butter(4, [20.0 / nyquist, high_cut / nyquist], btype="bandpass")
            filtered = signal.filtfilt(b_band, a_band, centered, axis=0)
            if 0 < 50.0 < nyquist:
                b_notch, a_notch = signal.iirnotch(50.0 / nyquist, 30.0)
                filtered = signal.filtfilt(b_notch, a_notch, filtered, axis=0)
        except ValueError:
            filtered = centered

    win_len = max(32, int(fs * 0.2))
    step = max(1, win_len // 2)
    windows = []
    if len(filtered) < win_len:
        windows.append(filtered)
    else:
        windows.extend(filtered[start:start + win_len] for start in range(0, len(filtered) - win_len + 1, step))

    feature_rows = []
    for window in windows:
        channel_features = [_window_features(window[:, channel], fs) for channel in range(8)]
        feature_rows.append({
            key: float(np.mean([item[key] for item in channel_features]))
            for key in channel_features[0]
        })

    if not feature_rows:
        raise HTTPException(status_code=422, detail="没有足够的有效肌电窗口")

    rms_values = np.asarray([row["rms"] for row in feature_rows], dtype=np.float64)
    mf_values = np.asarray([row["mf"] for row in feature_rows], dtype=np.float64)
    wl_values = np.asarray([row["wl"] for row in feature_rows], dtype=np.float64)
    rest_count = max(1, int(len(feature_rows) * 0.2))
    baseline_rms = float(np.mean(rms_values[:rest_count]))
    rms_mean = float(np.mean(rms_values))
    rms_cv = float(np.std(rms_values) / max(abs(rms_mean), 1e-6))
    if len(mf_values) > 1 and np.any(np.isfinite(mf_values)):
        mf_slope = float(np.polyfit(np.arange(len(mf_values)), mf_values, 1)[0])
    else:
        mf_slope = 0.0

    baseline_score = 100.0 - max(0.0, baseline_rms - 5.0) * 4.0
    stability_score = 100.0 - max(0.0, rms_cv - 0.1) * 250.0
    frequency_score = 100.0 - max(0.0, abs(mf_slope) - 0.05) * 200.0
    quality_score = 100.0 - abs(float(np.mean(wl_values)) - 500.0) / 5.0
    total_score = (
        _score(baseline_score) * 0.25
        + _score(stability_score) * 0.25
        + _score(frequency_score) * 0.30
        + _score(quality_score) * 0.20
    )
    if total_score >= 85:
        level = "优秀"
        status = "正常"
        level_desc = "肌肉状态健康，静息放松良好，神经肌肉控制稳定。"
    elif total_score >= 70:
        level = "良好"
        status = "正常"
        level_desc = "肌肉状态整体正常，建议保持规律训练并注意放松。"
    elif total_score >= 55:
        level = "一般"
        status = "需关注"
        level_desc = "肌肉可能存在轻度紧张、波动或疲劳，建议降低训练强度并观察。"
    else:
        level = "需关注"
        status = "需关注"
        level_desc = "当前信号提示持续紧张、疲劳或信号质量不足，不能替代医学诊断。"

    first_mf = float(mf_values[0]) if len(mf_values) else 0.0
    last_mf = float(mf_values[-1]) if len(mf_values) else 0.0
    fatigue_index = max(0.0, min(100.0, (first_mf - last_mf) / max(abs(first_mf), 1.0) * 100.0))
    metrics = {
        "sample_count": int(len(matrix)),
        "sample_rate_hz": int(fs),
        "window_count": int(len(feature_rows)),
        "rms": round(rms_mean, 3),
        "mav": round(float(np.mean([row["mav"] for row in feature_rows])), 3),
        "mf": round(float(np.mean(mf_values)), 3),
        "mnf": round(float(np.mean([row["mnf"] for row in feature_rows])), 3),
        "total_power": round(float(np.mean([row["total_power"] for row in feature_rows])), 6),
        "baseline_rms": round(baseline_rms, 3),
        "rms_cv": round(rms_cv, 4),
        "mf_slope": round(mf_slope, 6),
        "fatigue_index": round(fatigue_index, 1),
        "baseline_score": _score(baseline_score),
        "stability_score": _score(stability_score),
        "frequency_score": _score(frequency_score),
        "quality_score": _score(quality_score),
        "health_score": _score(total_score),
        "health_level": level,
        "muscle_status": status,
        "level_description": level_desc,
    }
    return metrics


def _rule_advice(metrics: dict[str, Any]) -> str:
    advice = []
    if metrics["baseline_score"] < 70:
        advice.append("训练前先做 2-3 分钟放松，避免肌肉在静息时持续用力")
    if metrics["stability_score"] < 70:
        advice.append("降低单次训练强度，保持动作节奏稳定并增加休息")
    if metrics["fatigue_index"] >= 25 or metrics["frequency_score"] < 70:
        advice.append("当前频率指标有疲劳趋势，建议分组训练并及时补水")
    if metrics["quality_score"] < 70:
        advice.append("检查电极贴合、佩戴位置和设备接地，避免运动伪迹")
    if not advice:
        advice.append("当前指标整体平稳，继续保持规律、低到中等强度训练")
    return "；".join(advice) + "。如出现疼痛、麻木或症状持续加重，请停止训练并咨询专业医生。"


def _target_device(db: Session, user: User, hardware_id: str) -> Device | None:
    query = db.query(Device).filter(Device.user_id == user.id)
    if hardware_id:
        return query.filter(Device.hardware_id == hardware_id).first()
    return query.order_by(Device.updated_at.desc(), Device.id.desc()).first()


async def _ai_advice(metrics: dict[str, Any], user: User, device: Device | None, db: Session) -> tuple[str, str]:
    rule_advice = _rule_advice(metrics)
    if not os.getenv("DEEPSEEK_API_KEY"):
        return rule_advice, "local_fallback"
    try:
        from routers.ai import ChatIn, _call_deepseek

        prompt = (
            "请根据以下真实肌电分析指标，为用户生成不超过 120 字的中文健康建议。"
            "只能做康复和训练建议，不能下医学诊断；请明确说明异常时应停止训练并咨询医生。\n"
            f"指标：{json.dumps(metrics, ensure_ascii=False)}"
        )
        reply = await _call_deepseek(ChatIn(message=prompt), user, device, db)
        if reply:
            return reply.strip(), "deepseek"
    except Exception:
        # Keep the report usable when the key, network, quota, or upstream
        # response is unavailable, but expose the real source to the client.
        return f"{rule_advice}（DeepSeek 暂时不可用，当前显示本地规则建议。）", "deepseek_unavailable"
    return rule_advice, "deepseek_unavailable"


@router.post("/report/analyze")
async def analyze_report(
    body: AnalyzeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分析最近一段真实 EMG；可选保存报告并请求 DeepSeek 建议。"""
    matrix = _validate_samples(body.samples)
    device = _target_device(db, current_user, body.hardware_id.strip())
    metrics = _analyze_matrix(matrix, body.sample_rate_hz)
    rule_advice = _rule_advice(metrics)
    ai_advice = rule_advice
    ai_source = "local_fallback"
    if body.include_ai:
        ai_advice, ai_source = await _ai_advice(metrics, current_user, device, db)

    report_id = None
    recorded_at: datetime | None = None
    if body.persist:
        if not device and body.hardware_id:
            raise HTTPException(status_code=404, detail="找不到当前用户绑定的设备")
        record = HealthRecord(
            user_id=current_user.id,
            rms_value=metrics["rms"],
            side_presure=float(body.side_pressure or 0),
            muscle_status=metrics["muscle_status"],
            diagnostics=f"{metrics['level_description']} {rule_advice}",
            health_score=metrics["health_score"],
            health_level=metrics["health_level"],
            analysis_json=json.dumps(metrics, ensure_ascii=False),
            ai_advice=ai_advice,
            ai_source=ai_source,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        report_id = record.id
        recorded_at = record.recorded_at

    return {
        "report_id": report_id,
        "user_id": current_user.id,
        "hardware_id": device.hardware_id if device else body.hardware_id,
        "device_name": (device.device_name or device.hardware_id) if device else "",
        "metrics": metrics,
        "health_score": metrics["health_score"],
        "health_level": metrics["health_level"],
        "muscle_status": metrics["muscle_status"],
        "diagnostics": metrics["level_description"],
        "ai_advice": ai_advice,
        "ai_source": ai_source,
        "generated_at": _format_beijing_time(recorded_at),
        "data_source": "realtime_emg",
    }


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
        "generated_at":  _format_beijing_time(record.recorded_at),
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
                "health_score":  r.health_score or 0,
                "health_level":  r.health_level or "",
                "ai_advice":     r.ai_advice or "",
                "ai_source":     r.ai_source or "",
                "analysis":      _parse_analysis(r.analysis_json),
                "recorded_at":   _format_beijing_time(r.recorded_at),
            }
            for r in records
        ]
    }


def _parse_analysis(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
