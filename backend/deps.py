"""
deps.py - 公共依赖：JWT 解析、获取当前用户
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt

from models import get_db, User

SECRET_KEY = "emg_hand_secret_2024"   # 生产环境请改成随机长串并写入环境变量
ALGORITHM  = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 中解析用户，不存在则 401"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        raw_sub = payload.get("sub")
        if raw_sub is None:
            raise ValueError
        user_id = int(raw_sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选认证，未登录时返回 None（供论坛只读接口使用）"""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        raw_sub = payload.get("sub")
        if raw_sub is None:
            return None
        user_id = int(raw_sub)
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None
