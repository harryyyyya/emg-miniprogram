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
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from deps import get_current_user, get_current_user_optional
from models import (
    Device,
    EmgCollectionSession,
    ErrorLog,
    ForumComment,
    ForumPost,
    HealthRecord,
    KnowledgeArticle,
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


def _user_row(user: User, db: Session) -> dict[str, Any]:
    latest_health = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id)
        .order_by(HealthRecord.recorded_at.desc(), HealthRecord.id.desc())
        .first()
    )
    return {
        "id": user.id,
        "user_id": user.id,
        "name": user.name or user.username or user.phone or f"用户#{user.id}",
        "username": user.username or "",
        "phone": user.phone or "",
        "role": user.role or "user",
        "avatar_url": user.avatar_url or "",
        "created_at": _dt(user.created_at),
        "device_count": db.query(Device).filter(Device.user_id == user.id).count(),
        "health_log_count": db.query(HealthRecord).filter(HealthRecord.user_id == user.id).count(),
        "latest_health_at": _dt(latest_health.recorded_at) if latest_health else "",
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (current_user.role or "user") != "admin":
        return [_user_row(current_user, db)]

    users = db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
    return [_user_row(user, db) for user in users]


def _safe_json_dumps(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _article_sections(article: KnowledgeArticle) -> list[dict[str, Any]]:
    sections = _parse_json(article.sections_json, [])
    if isinstance(sections, list) and sections:
        return sections

    paragraphs = [line.strip() for line in (article.content or "").splitlines() if line.strip()]
    if not paragraphs:
        paragraphs = [article.summary or "暂无正文内容。"]
    return [{"heading": "正文", "items": paragraphs}]


def _article_tips(article: KnowledgeArticle) -> list[str]:
    tips = _parse_json(article.tips_json, [])
    return tips if isinstance(tips, list) else []


def _article_row(article: KnowledgeArticle) -> dict[str, Any]:
    tag = article.type or "guide"
    created_at = article.created_at or datetime.utcnow()
    return {
        "id": article.id,
        "title": article.title,
        "type": tag,
        "tag": _article_type_label(tag),
        "summary": article.summary or "",
        "excerpt": article.summary or (article.content or "")[:120],
        "desc": article.summary or (article.content or "")[:120],
        "content": article.content or "",
        "full_content": article.content or "",
        "cover_url": article.cover_url or "",
        "cover": article.cover_url or "",
        "theme": article.theme or "",
        "sections": _article_sections(article),
        "tips": _article_tips(article),
        "is_published": article.is_published is not False,
        "published": article.is_published is not False,
        "sort_order": article.sort_order or 0,
        "created_by": article.created_by,
        "created_at": _dt(article.created_at),
        "updated_at": _dt(article.updated_at),
        "date": created_at.date().isoformat(),
    }


def _article_type_label(value: str) -> str:
    labels = {
        "guide": "使用指南",
        "training": "训练建议",
        "connection": "设备连接",
        "mental": "心理支持",
        "update": "版本更新",
    }
    return labels.get(value or "guide", value or "使用指南")


DEFAULT_KNOWLEDGE_ARTICLES = [
    {
        "title": "新手第一次连接：先确认这 3 件事",
        "type": "connection",
        "summary": "如果小程序绑定成功但设备仍显示离线，可以按这份清单逐项检查。",
        "cover_url": "/assets/images/article1.jpg",
        "theme": "",
        "sort_order": 30,
        "content": "先确认 ESP32 已连接 Wi-Fi，再确认设备编号和设备密钥与小程序绑定信息一致。串口监视器中看到 registerBoard status=200 代表注册成功，看到 heartbeat status=200 代表后端已经收到心跳。",
        "sections": [
            {
                "heading": "1. 先检查 ESP32 程序配置",
                "items": [
                    "BACKEND_HOST 应该是 api.handemglsh.cloud。",
                    "BACKEND_PORT 应该是 443。",
                    "HARDWARE_ID 要和小程序绑定的设备编号一致。",
                    "BOARD_TOKEN 要和小程序绑定时填写的设备密钥一致。",
                ],
            },
            {
                "heading": "2. 再看串口监视器",
                "items": [
                    "串口波特率选择 115200。",
                    "看到 WiFi connected, IP=... 说明 ESP32 已连上 Wi-Fi。",
                    "看到 registerBoard status=200 说明设备已注册到后端。",
                    "看到 heartbeat status=200 说明后端已收到设备心跳。",
                ],
            },
            {
                "heading": "3. 最后检查小程序",
                "items": [
                    "如果使用默认固件，直接绑定 ESP32-HAND-001。",
                    "进入控制页后点击刷新设备状态。",
                    "如果仍然离线，优先核对设备编号和设备密钥。",
                ],
            },
        ],
        "tips": [
            "绑定成功只代表后端保存了设备信息，真正在线要看 ESP32 是否持续上报心跳。",
            "换新板子也可以继续使用，只要烧录同一份程序，并保持设备编号和密钥一致。",
        ],
    },
    {
        "title": "动作录入怎么练：每次 5 秒更稳定",
        "type": "training",
        "summary": "肌电训练不一定越久越好，稳定、干净、可重复的数据更重要。",
        "cover_url": "/assets/images/article2.jpg",
        "theme": "",
        "sort_order": 20,
        "content": "录入动作前先放松几秒，保持臂环位置稳定。录入时让动作尽量一致，观察原始肌电波形和 RMS 是否出现明显变化。",
        "sections": [
            {
                "heading": "1. 录入前准备",
                "items": [
                    "固定臂环位置，避免每次佩戴位置差异过大。",
                    "确认蓝牙臂环或 ESP32 状态在线。",
                    "开始前让手臂放松几秒，减少无关肌肉紧张。",
                ],
            },
            {
                "heading": "2. 每个动作怎么做",
                "items": [
                    "先保持 3 秒放松，再保持 3 秒目标动作。",
                    "动作过程中尽量不要大幅移动手臂。",
                    "波形应该有明显变化，但不要长期贴顶或贴底。",
                ],
            },
            {
                "heading": "3. 录入后判断质量",
                "items": [
                    "查看 RMS、峰值、MIN、MAX 是否异常跳变。",
                    "如果波形几乎是一条直线，可能没有采到有效信号。",
                    "如果某次数据明显异常，可以删除后重新录入。",
                ],
            },
        ],
        "tips": [
            "短时间稳定样本通常比长时间噪声样本更适合训练。",
            "识别不稳定时，先检查数据质量，再考虑调整模型。",
        ],
    },
    {
        "title": "假手适应期心理疏导：慢慢来，也是一种进步",
        "type": "mental",
        "summary": "适应假手不只是训练动作，也是在重新建立安全感、自信和生活节奏。",
        "cover_url": "/assets/images/article3.jpg",
        "theme": "warm",
        "sort_order": 10,
        "content": "刚开始使用假手时，出现紧张、烦躁或失落都很常见。把目标拆小，给自己一个更安全、更可持续的训练节奏。",
        "sections": [
            {
                "heading": "1. 先允许自己有情绪",
                "items": [
                    "刚开始使用假手时，出现烦躁、紧张、失落或害怕被关注都很常见。",
                    "把目标拆小：今天完成一次连接、一次佩戴、一次动作练习，都算有效进步。",
                    "可以每天用一句话记录感受，帮助自己看见变化。",
                ],
            },
            {
                "heading": "2. 用身体放松降低压力",
                "items": [
                    "训练前先做 1 到 3 分钟慢呼吸，让肩膀和前臂尽量放松。",
                    "如果训练中明显紧张，可以暂停、伸展、喝水或短暂离开屏幕。",
                    "保持规律睡眠、轻量活动和低压力爱好，有助于训练更稳定。",
                ],
            },
            {
                "heading": "3. 建立支持网络",
                "items": [
                    "把训练计划告诉家人或朋友，请他们多记录事实和进步，少做评价。",
                    "遇到挫败时，可以向康复治疗师、医生、心理咨询师说明具体困难。",
                    "如果情绪低落、焦虑或失眠持续影响生活，请及时寻求专业帮助。",
                ],
            },
        ],
        "tips": [
            "心理疏导不是“想开点”，而是给自己一个更安全、更可持续的训练环境。",
            "本页内容只作康复陪伴和健康教育参考，不能替代专业诊断或治疗。",
        ],
    },
]


def _ensure_default_knowledge_articles(db: Session) -> None:
    if db.query(KnowledgeArticle).count() > 0:
        _promote_unsorted_knowledge_articles(db)
        return

    for item in DEFAULT_KNOWLEDGE_ARTICLES:
        db.add(KnowledgeArticle(
            title=item["title"],
            type=item["type"],
            summary=item["summary"],
            content=item["content"],
            cover_url=item["cover_url"],
            theme=item["theme"],
            sort_order=item["sort_order"],
            sections_json=_safe_json_dumps(item["sections"]),
            tips_json=_safe_json_dumps(item["tips"]),
            is_published=True,
        ))
    db.commit()


def _promote_unsorted_knowledge_articles(db: Session) -> None:
    rows = (
        db.query(KnowledgeArticle)
        .filter(KnowledgeArticle.sort_order <= 0, KnowledgeArticle.is_published == True)
        .order_by(KnowledgeArticle.created_at.asc(), KnowledgeArticle.id.asc())
        .all()
    )
    if not rows:
        return

    max_sort_order = db.query(func.max(KnowledgeArticle.sort_order)).scalar() or 0
    for index, article in enumerate(rows, start=1):
        article.sort_order = int(max_sort_order) + index * 10
    db.commit()


class KnowledgeArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    type: str = Field(default="guide", max_length=32)
    summary: str = ""
    content: str = ""
    cover_url: str = Field(default="", max_length=512)
    theme: str = Field(default="", max_length=32)
    is_published: bool = True
    sort_order: int = 0
    sections: list[dict[str, Any]] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


@router.get("/knowledge/articles")
def list_knowledge_articles(
    published: str = "true",
    limit: int = 50,
    keyword: str = "",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    _ensure_default_knowledge_articles(db)
    query = db.query(KnowledgeArticle)

    published_value = (published or "true").lower()
    if published_value in {"all", "false", "0"}:
        if not current_user or (current_user.role or "user") != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        if published_value in {"false", "0"}:
            query = query.filter(KnowledgeArticle.is_published == False)
    else:
        query = query.filter(KnowledgeArticle.is_published == True)

    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (KnowledgeArticle.title.like(like))
            | (KnowledgeArticle.summary.like(like))
            | (KnowledgeArticle.content.like(like))
        )

    size = max(1, min(int(limit or 50), 200))
    items = (
        query.order_by(KnowledgeArticle.sort_order.desc(), KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())
        .limit(size)
        .all()
    )
    return [_article_row(item) for item in items]


@router.get("/knowledge/articles/{article_id}")
def get_knowledge_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    _ensure_default_knowledge_articles(db)
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    if article.is_published is False and (not current_user or (current_user.role or "user") != "admin"):
        raise HTTPException(status_code=404, detail="文章不存在")
    return _article_row(article)


@router.post("/knowledge/articles")
def create_knowledge_article(
    body: KnowledgeArticleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    sort_order = body.sort_order
    if sort_order <= 0:
        max_sort_order = db.query(func.max(KnowledgeArticle.sort_order)).scalar() or 0
        sort_order = int(max_sort_order) + 10

    article = KnowledgeArticle(
        title=body.title.strip(),
        type=(body.type or "guide").strip(),
        summary=body.summary.strip(),
        content=body.content.strip(),
        cover_url=body.cover_url.strip(),
        theme=body.theme.strip(),
        is_published=body.is_published,
        sort_order=sort_order,
        sections_json=_safe_json_dumps(body.sections),
        tips_json=_safe_json_dumps(body.tips),
        created_by=current_user.id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return _article_row(article)


@router.put("/knowledge/articles/{article_id}")
def update_knowledge_article(
    article_id: int,
    body: KnowledgeArticleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    article.title = body.title.strip()
    article.type = (body.type or "guide").strip()
    article.summary = body.summary.strip()
    article.content = body.content.strip()
    article.cover_url = body.cover_url.strip()
    article.theme = body.theme.strip()
    article.is_published = body.is_published
    article.sort_order = body.sort_order
    article.sections_json = _safe_json_dumps(body.sections)
    article.tips_json = _safe_json_dumps(body.tips)
    article.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(article)
    return _article_row(article)


@router.delete("/knowledge/articles/{article_id}")
def delete_knowledge_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    db.delete(article)
    db.commit()
    return {"message": "文章已删除"}


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
