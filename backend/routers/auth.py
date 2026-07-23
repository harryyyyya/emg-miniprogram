"""
Authentication routes.
"""
import hashlib
import hmac
import os
import random
import string
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import ALGORITHM, SECRET_KEY, get_current_user
from models import SmsCode, User, get_db

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_EXPIRE_DAYS = 30


def _make_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "user_id": user.id,
        "name": user.name,
        "phone": user.phone or "",
        "username": user.username or "",
        "role": user.role or "user",
        "avatar_url": user.avatar_url or "",
        "amputation_part": user.amputation_part or "",
        "illness_duration_months": user.illness_duration_months or 0,
    }


def _hash_password(password: str) -> str:
    salt = os.getenv("PASSWORD_SALT", "emg-hand-web-admin")
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password), password_hash or "")


def _ensure_default_web_accounts(db: Session) -> None:
    defaults = [
        ("admin", os.getenv("ADMIN_PASSWORD", "admin"), "管理员", "admin"),
        ("user", os.getenv("USER_PASSWORD", "user"), "普通用户", "user"),
    ]
    changed = False
    for username, password, name, role in defaults:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            db.add(User(
                username=username,
                password_hash=_hash_password(password),
                name=name,
                role=role,
            ))
            changed = True
        elif not user.password_hash:
            user.password_hash = _hash_password(password)
            user.role = user.role or role
            changed = True
    if changed:
        db.commit()


class WechatLoginIn(BaseModel):
    code: str
    name: str = Field(default="", max_length=32)
    avatar_url: str = Field(default="", max_length=512)
    amputation_part: str = Field(default="", max_length=128)
    illness_duration_months: int = Field(default=0, ge=0, le=1200)


class PasswordLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def password_login(body: PasswordLoginIn, db: Session = Depends(get_db)):
    _ensure_default_web_accounts(db)
    username = body.username.strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not _verify_password(body.password, user.password_hash or ""):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    role = user.role or "user"
    return {
        "token": _make_token(user.id),
        "role": role,
        "username": user.username or "",
        "name": user.name or user.username or "用户",
        "user_id": user.id,
        "user": _user_dict(user),
    }


@router.post("/wechat")
def wechat_login(body: WechatLoginIn, db: Session = Depends(get_db)):
    """
    Mock WeChat login for local development.
    In production, exchange `code` for openid via WeChat server.
    """
    openid = f"mock_openid_{body.code}"
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid, name="微信用户")
        db.add(user)

    name = body.name.strip()
    avatar_url = body.avatar_url.strip()
    amputation_part = body.amputation_part.strip()
    if name:
        user.name = name[:32]
    if avatar_url:
        user.avatar_url = avatar_url[:512]
    if amputation_part:
        user.amputation_part = amputation_part[:128]
    user.illness_duration_months = max(0, int(body.illness_duration_months or 0))

    db.commit()
    db.refresh(user)
    return {"token": _make_token(user.id), "user": _user_dict(user)}


class SmsSendIn(BaseModel):
    phone: str


@router.post("/sms/send")
def sms_send(body: SmsSendIn, db: Session = Depends(get_db)):
    code = "".join(random.choices(string.digits, k=6))
    expired_at = datetime.utcnow() + timedelta(minutes=5)

    old = db.query(SmsCode).filter(
        SmsCode.phone == body.phone,
        SmsCode.used == False,
    ).first()
    if old:
        old.code = code
        old.expired_at = expired_at
    else:
        db.add(SmsCode(phone=body.phone, code=code, expired_at=expired_at))
    db.commit()

    print(f"[SMS Mock] phone={body.phone}, code={code}")
    return {"message": "验证码已发送（Mock 模式，请查看后端控制台）"}


class SmsVerifyIn(BaseModel):
    phone: str
    code: str


@router.post("/sms/verify")
def sms_verify(body: SmsVerifyIn, db: Session = Depends(get_db)):
    record = db.query(SmsCode).filter(
        SmsCode.phone == body.phone,
        SmsCode.code == body.code,
        SmsCode.used == False,
    ).order_by(SmsCode.id.desc()).first()

    if not record:
        raise HTTPException(status_code=400, detail="验证码错误")
    if record.expired_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="验证码已过期")

    record.used = True
    user = db.query(User).filter(User.phone == body.phone).first()
    if not user:
        user = User(phone=body.phone, name=f"用户{body.phone[-4:]}")
        db.add(user)

    db.commit()
    db.refresh(user)
    return {"token": _make_token(user.id), "user": _user_dict(user)}


class UpdateProfileIn(BaseModel):
    name: str = Field(default="", max_length=32)
    avatar_url: str = Field(default="", max_length=512)
    amputation_part: str = Field(default="", max_length=128)
    illness_duration_months: int | None = Field(default=None, ge=0, le=1200)


@router.put("/profile")
def update_profile(
    body: UpdateProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = body.name.strip()
    avatar_url = body.avatar_url.strip()
    amputation_part = body.amputation_part.strip()
    has_duration = body.illness_duration_months is not None
    if not name and not avatar_url and not amputation_part and not has_duration:
        raise HTTPException(status_code=400, detail="请至少提交一项更新内容")

    if name:
        current_user.name = name[:32]
    if avatar_url:
        current_user.avatar_url = avatar_url[:512]
    if amputation_part:
        current_user.amputation_part = amputation_part[:128]
    if has_duration:
        current_user.illness_duration_months = max(0, int(body.illness_duration_months or 0))

    db.commit()
    db.refresh(current_user)
    return {"message": "用户信息已更新", "user": _user_dict(current_user)}
