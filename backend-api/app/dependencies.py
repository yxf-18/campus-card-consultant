from __future__ import annotations

from datetime import datetime

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import SysUser, now_local
from .responses import ApiError
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)
settings = get_settings()


def _credentials_to_payload(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(100106, "登录已失效，请重新登录", 401)
    try:
        return decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise ApiError(100106, "登录已失效，请重新登录", 401) from exc


def get_token_payload(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    return _credentials_to_payload(credentials)


def get_current_user(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> SysUser:
    user = db.get(SysUser, int(payload.get("sub", 0)))
    if user is None:
        raise ApiError(100107, "用户不存在", 401)
    if user.status != "ACTIVE":
        raise ApiError(100103, "账号已禁用", 403)
    if user.locked_until and user.locked_until > now_local():
        raise ApiError(100102, "账号已被锁定，请稍后再试", 423)
    return user


def require_admin(user: SysUser = Depends(get_current_user)) -> SysUser:
    if user.role != "ADMIN":
        raise ApiError(100201, "无访问权限", 403)
    return user


def require_mobile_user(user: SysUser = Depends(get_current_user)) -> SysUser:
    if user.role != "USER":
        raise ApiError(100201, "管理员不能使用移动端功能", 403)
    return user


def require_internal_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if not x_internal_token or x_internal_token != settings.internal_token:
        raise ApiError(100201, "内部接口授权失败", 403)


def parse_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""
