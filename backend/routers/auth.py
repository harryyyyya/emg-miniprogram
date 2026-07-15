"""
Authentication routes.
"""
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
        "name": user.name,
        "phone": user.phone or "",
        "avatar_url": user.avatar_url or "",
    }


class WechatLoginIn(BaseModel):
    code: str
    name: str = Field(default="", max_length=32)
    avatar_url: str = Field(default="", max_length=512)


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
    if name:
        user.name = name[:32]
    if avatar_url:
        user.avatar_url = avatar_url[:512]

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


@router.put("/profile")
def update_profile(
    body: UpdateProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = body.name.strip()
    avatar_url = body.avatar_url.strip()
    if not name and not avatar_url:
        raise HTTPException(status_code=400, detail="请至少提交一项更新内容")

    if name:
        current_user.name = name[:32]
    if avatar_url:
        current_user.avatar_url = avatar_url[:512]

    db.commit()
    db.refresh(current_user)
    return {"message": "用户信息已更新", "user": _user_dict(current_user)}
