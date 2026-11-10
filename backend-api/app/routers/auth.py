from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_token_payload
from ..models import SysUser, now_local
from ..responses import ApiError, success
from ..schemas import LoginRequest, ProfileBindRequest, RegisterRequest
from ..security import create_access_token, hash_password, revoke_token, verify_password
from ..services import get_int_config
from ..utils import fmt_dt

router = APIRouter(prefix="/auth", tags=["认证"])


def user_json(user: SysUser) -> dict:
    return {
        "user_id": user.id, "username": user.username, "nickname": user.nickname,
        "phone": user.phone or "", "email": user.email or "", "student_no": user.student_no or "",
        "role": user.role, "status": user.status, "created_at": fmt_dt(user.created_at),
        "last_login_at": fmt_dt(user.last_login_at),
        "profile_complete": bool(user.phone and user.student_no),
    }


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    duplicate = None
    for field, value in (("username", payload.username), ("phone", payload.phone),
                         ("email", payload.email), ("student_no", payload.student_no)):
        if value and db.query(SysUser).filter(getattr(SysUser, field) == value).first():
            duplicate = field
            break
    if duplicate:
        labels = {"username": "用户名", "phone": "手机号", "email": "邮箱", "student_no": "学号"}
        raise ApiError(100104, f"{labels[duplicate]}已存在", 409)
    user = SysUser(
        username=payload.username, phone=payload.phone or None, email=payload.email or None,
        student_no=payload.student_no or None, password_hash=hash_password(payload.password),
        nickname=payload.nickname or payload.username, role="USER", status="ACTIVE",
        privacy_agreed_at=now_local())
    db.add(user)
    db.commit()
    db.refresh(user)
    return success({"user_id": user.id, "username": user.username, "nickname": user.nickname,
                    "role": user.role, "status": user.status, "created_at": fmt_dt(user.created_at)}, status_code=201)


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    if payload.login_type == "STUDENT_NO":
        user = db.query(SysUser).filter(SysUser.student_no == payload.account).first()
    elif payload.login_type == "PHONE":
        user = db.query(SysUser).filter(SysUser.phone == payload.account).first()
    elif payload.login_type == "EMAIL":
        user = db.query(SysUser).filter(SysUser.email == payload.account).first()
    elif payload.login_type == "USERNAME":
        user = db.query(SysUser).filter(SysUser.username == payload.account).first()
    else:
        user = db.query(SysUser).filter(or_(SysUser.username == payload.account,
                                            SysUser.phone == payload.account,
                                            SysUser.email == payload.account,
                                            SysUser.student_no == payload.account)).first()
    if user is None:
        raise ApiError(100101, "账号或密码错误", 401)
    if user.status != "ACTIVE":
        raise ApiError(100103, "账号已禁用", 403)
    now = now_local()
    if user.locked_until and user.locked_until > now:
        raise ApiError(100102, "账号已被锁定，请稍后再试", 423)
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        limit = get_int_config(db, "auth.login_fail_limit", 5)
        lock_minutes = get_int_config(db, "auth.login_lock_minutes", 10)
        if user.failed_login_count >= limit:
            user.locked_until = now + timedelta(minutes=lock_minutes)
            user.failed_login_count = 0
        db.commit()
        raise ApiError(100101, "账号或密码错误", 401)
    if payload.client_type == "MOBILE" and user.role != "USER":
        raise ApiError(100201, "管理员账号不能登录移动端", 403)
    if payload.client_type == "ADMIN" and user.role != "ADMIN":
        raise ApiError(100201, "普通用户不能登录管理后台", 403)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    token, expires_in = create_access_token(user.id, user.username, user.role)
    return success({
        "token": token, "token_type": "Bearer", "expires_in": expires_in,
        "user": user_json(user), "redirect_url": payload.redirect_url or "",
    })


@router.post("/logout")
def logout(payload: dict = Depends(get_token_payload), _user: SysUser = Depends(get_current_user)):
    revoke_token(payload)
    return success({"result": True})


@router.get("/me")
def me(user: SysUser = Depends(get_current_user)):
    return success({"user": user_json(user)})


@router.put("/profile")
def bind_profile(payload: ProfileBindRequest, user: SysUser = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    for field, value, label in (("phone", payload.phone, "手机号"),
                                ("student_no", payload.student_no, "学号"),
                                ("email", payload.email, "邮箱")):
        if value:
            duplicate = (db.query(SysUser)
                         .filter(getattr(SysUser, field) == value, SysUser.id != user.id).first())
            if duplicate:
                raise ApiError(100104, f"{label}已被其他账号使用", 409)
    user.phone = payload.phone
    user.student_no = payload.student_no
    if payload.email is not None:
        user.email = payload.email or None
    if payload.nickname:
        user.nickname = payload.nickname
    db.commit()
    db.refresh(user)
    return success({"user": user_json(user)})
