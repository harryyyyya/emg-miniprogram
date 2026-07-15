"""
AI assistant endpoint.

Uses DeepSeek-compatible chat completions when DEEPSEEK_API_KEY is configured.
Falls back to local rule-based replies otherwise.
"""
import json
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import get_current_user
from models import Device, HealthRecord, TrainingSession, User, get_db

router = APIRouter(prefix="/ai", tags=["ai"])

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatIn(BaseModel):
    message: str
    hardware_id: str | None = None
    history: list[HistoryMessage] = Field(default_factory=list)


@router.post("/chat")
async def chat(
    body: ChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    device = _get_target_device(body, current_user, db)
    ai_reply = await _call_deepseek(body, current_user, device, db)
    if ai_reply is not None:
        return {"reply": ai_reply, "source": "deepseek", "model": DEEPSEEK_MODEL}

    return {
        "reply": _local_fallback_reply(message, current_user, device, db),
        "source": "local_fallback",
        "model": "rule-based",
    }


async def _call_deepseek(body: ChatIn, user: User, device: Device | None, db: Session) -> str | None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    try:
        import httpx
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="后端缺少 httpx，请先执行 pip install -r requirements.txt",
        ) from exc

    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": _build_messages(body, user, device, db),
        "stream": False,
        "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", "0.4")),
        "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", "800")),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = httpx.Timeout(35.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="AI 接口请求超时") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI 接口连接失败: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"AI 接口返回错误: {_extract_error(response)}",
        )

    data = response.json()
    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI 返回格式异常") from exc

    if not reply:
        raise HTTPException(status_code=502, detail="AI 返回内容为空")
    return reply.strip()


def _build_messages(
    body: ChatIn,
    user: User,
    device: Device | None,
    db: Session,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": _build_system_prompt(body, user, device, db)}]

    for item in body.history[-10:]:
        content = item.content.strip()
        if not content:
            continue
        messages.append({"role": item.role, "content": content[:1200]})

    messages.append({"role": "user", "content": body.message.strip()})
    return messages


def _build_system_prompt(body: ChatIn, user: User, device: Device | None, db: Session) -> str:
    training_count = db.query(TrainingSession).filter(TrainingSession.user_id == user.id).count()
    latest_report = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id)
        .order_by(HealthRecord.recorded_at.desc())
        .first()
    )

    health_context = "暂无健康报告。"
    if latest_report:
        health_context = (
            f"最近健康报告：RMS={latest_report.rms_value}，"
            f"侧压力={latest_report.side_presure}，"
            f"肌肉状态={latest_report.muscle_status}，"
            f"建议={latest_report.diagnostics or '暂无'}。"
        )

    hardware = body.hardware_id or (device.hardware_id if device else "未绑定设备")
    device_context = _build_device_context(device)

    return (
        "你是肌电假手康复小程序里的 AI 助手。"
        "请始终使用中文回答，语气简洁、专业、可执行。"
        "你可以解释设备状态、训练记录、肌电数据和康复建议。"
        "不要编造实时硬件数据；没有数据时要明确说明。"
        "涉及疼痛、感染、严重不适或诊断结论时，应建议用户咨询专业医生。"
        f"\n当前用户：{user.name or '用户'}"
        f"\n设备标识：{hardware}"
        f"\n训练次数：{training_count}"
        f"\n{device_context}"
        f"\n{health_context}"
    )


def _get_target_device(body: ChatIn, user: User, db: Session) -> Device | None:
    query = db.query(Device).filter(Device.user_id == user.id)
    if body.hardware_id:
        return query.filter(Device.hardware_id == body.hardware_id).first()
    return query.order_by(Device.updated_at.desc(), Device.bind_time.desc(), Device.id.desc()).first()


def _build_device_context(device: Device | None) -> str:
    if not device:
        return "当前没有已绑定设备信息。"

    telemetry = _parse_json_blob(device.telemetry_json)
    telemetry_parts: list[str] = []
    if telemetry.get("rms_value") is not None:
        telemetry_parts.append(f"RMS={telemetry['rms_value']}")
    if telemetry.get("side_pressure") is not None:
        telemetry_parts.append(f"侧压力={telemetry['side_pressure']}")
    if telemetry.get("muscle_status"):
        telemetry_parts.append(f"肌肉状态={telemetry['muscle_status']}")

    parts = [
        f"当前设备名称：{device.device_name or device.hardware_id}",
        f"设备通信方式：{device.transport or 'ble'}",
        f"设备在线状态：{device.status or 'offline'}",
    ]
    if device.battery_level is not None:
        parts.append(f"设备电量：{device.battery_level}%")
    if device.signal_strength is not None:
        parts.append(f"设备信号强度：{device.signal_strength}")
    if telemetry_parts:
        parts.append(f"最近设备遥测：{'，'.join(telemetry_parts)}")
    return "；".join(parts) + "。"


def _parse_json_blob(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_error(response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]

    error = data.get("error")
    if isinstance(error, dict):
        return error.get("message") or str(error)
    if error:
        return str(error)
    return response.text[:300]


def _local_fallback_reply(message: str, user: User, device: Device | None, db: Session) -> str:
    msg = message.lower()
    telemetry = _parse_json_blob(device.telemetry_json if device else "")

    if any(k in msg for k in ["电量", "电池", "battery"]):
        if device and device.battery_level is not None:
            status = device.status or "offline"
            return (
                f"当前绑定设备 {device.device_name or device.hardware_id} 的电量约为 "
                f"{device.battery_level}%，设备状态为 {status}。"
            )
        return "当前还没有可用的设备电量数据。请先绑定设备，并让设备上报一次状态。"

    if any(k in msg for k in ["状态", "在线", "signal", "信号"]):
        if not device:
            return "你目前还没有绑定设备，所以我暂时无法查询设备在线状态。"
        signal = "暂无"
        if device.signal_strength is not None:
            signal = str(device.signal_strength)
        return (
            f"当前设备 {device.device_name or device.hardware_id} 状态为 {device.status or 'offline'}，"
            f"信号强度为 {signal}。"
        )

    if any(k in msg for k in ["肌电", "数据", "rms", "报告"]):
        if telemetry.get("rms_value") is not None or telemetry.get("side_pressure") is not None:
            muscle_status = telemetry.get("muscle_status") or "暂无"
            return (
                f"设备最近一次上报数据显示：RMS 为 {telemetry.get('rms_value', '暂无')}，"
                f"侧压力为 {telemetry.get('side_pressure', '暂无')}，"
                f"肌肉状态为 {muscle_status}。"
            )

        last = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == user.id)
            .order_by(HealthRecord.recorded_at.desc())
            .first()
        )
        if last:
            diagnosis = f"建议：{last.diagnostics}" if last.diagnostics else "暂无额外风险提示。"
            return (
                f"最近一次健康报告中，肌电 RMS 为 {last.rms_value}，"
                f"侧压力为 {last.side_presure}，肌肉状态为 {last.muscle_status}。"
                f"{diagnosis}"
            )
        return "暂时还没有肌电数据或健康报告。请先完成一次数据采集或让设备上报状态。"

    if any(k in msg for k in ["训练", "采集", "康复"]):
        count = db.query(TrainingSession).filter(TrainingSession.user_id == user.id).count()
        return (
            f"你目前已经完成 {count} 次训练采集。建议保持低强度、规律训练；"
            "如果出现疼痛或疲劳明显加重，应暂停训练并咨询专业医生。"
        )

    return (
        "后端 AI 已接通，目前正在使用本地规则回复。"
        "如果你配置 `DEEPSEEK_API_KEY` 并重启后端，就可以切换到真实大模型对话。"
    )
