from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, get_token_payload
from ..models import ProfileChangeRequest, SysUser, now_local
from ..responses import ApiError, success
from ..schemas import LoginRequest, ProfileUpdateRequest
from ..security import create_access_token, revoke_token, verify_password
from ..services import identity_conflict
from ..utils import fmt_dt

router = APIRouter(prefix="/auth", tags=["认证"])

FIELD_LABELS = {"phone": "手机号", "email": "邮箱"}


def user_json(user: SysUser) -> dict:
    return {
        "user_id": user.id, "username": user.username, "nickname": user.nickname,
        "phone": user.phone or "", "email": user.email or "", "student_no": user.student_no or "",
        "role": user.role, "status": user.status, "created_at": fmt_dt(user.created_at),
        "last_login_at": fmt_dt(user.last_login_at),
        "profile_complete": bool(user.phone and user.student_no),
    }


def change_request_json(item: ProfileChangeRequest) -> dict:
    return {
        "request_id": item.id, "user_id": item.user_id,
        "field_name": item.field_name, "field_label": FIELD_LABELS.get(item.field_name, item.field_name),
        "old_value": item.old_value or "", "new_value": item.new_value, "status": item.status,
        "remark": item.remark or "", "created_at": fmt_dt(item.created_at),
        "reviewed_at": fmt_dt(item.reviewed_at),
    }


def pending_request(db: Session, user_id: int, field_name: str) -> ProfileChangeRequest | None:
    return (db.query(ProfileChangeRequest)
            .filter(ProfileChangeRequest.user_id == user_id,
                    ProfileChangeRequest.field_name == field_name,
                    ProfileChangeRequest.status == "PENDING")
            .order_by(ProfileChangeRequest.id.desc()).first())


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    account = payload.account.strip()
    if payload.login_type == "STUDENT_NO":
        user = db.query(SysUser).filter(SysUser.student_no == account).first()
    elif payload.login_type == "PHONE":
        user = db.query(SysUser).filter(SysUser.phone == account).first()
    elif payload.login_type == "EMAIL":
        user = db.query(SysUser).filter(SysUser.email == account).first()
    elif payload.login_type == "USERNAME":
        user = db.query(SysUser).filter(SysUser.username == account).first()
    else:
        user = db.query(SysUser).filter(or_(SysUser.username == account,
                                            SysUser.phone == account,
                                            SysUser.email == account,
                                            SysUser.student_no == account)).first()
    if user is None:
        raise ApiError(100101, "账号或密码错误，请检查后重试", 401)
    if user.status != "ACTIVE":
        raise ApiError(100103, "账号已被禁用，请联系管理员", 403)
    now = now_local()
    if not verify_password(payload.password, user.password_hash):
        raise ApiError(100101, "账号或密码错误，请重试", 401)
    if payload.client_type == "MOBILE" and user.role != "USER":
        raise ApiError(100201, "管理员账号不能登录移动端", 403)
    if payload.client_type == "ADMIN" and user.role != "ADMIN":
        raise ApiError(100201, "普通用户不能登录管理后台", 403)
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
def update_profile(payload: ProfileUpdateRequest, user: SysUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """学号/昵称直接更新；手机号、邮箱首次补录直接生效，之后修改需管理员审核。"""
    if payload.nickname is not None:
        user.nickname = payload.nickname
    if payload.student_no is not None and payload.student_no != (user.student_no or ""):
        if identity_conflict(db, payload.student_no, user.id):
            raise ApiError(100104, "学号已被其他账号使用", 409)
        user.student_no = payload.student_no
    pending: dict[str, str] = {}
    for field in ("phone", "email"):
        value = getattr(payload, field)
        if value is None:
            continue
        current = getattr(user, field) or ""
        if value == current:
            continue
        if identity_conflict(db, value, user.id):
            raise ApiError(100104, f"{FIELD_LABELS[field]}已被其他账号使用", 409)
        if not current:
            # 首次补录属于完善资料，不经过审批。
            setattr(user, field, value)
            continue
        request = pending_request(db, user.id, field)
        if request is None:
            request = ProfileChangeRequest(user_id=user.id, field_name=field,
                                           old_value=current, new_value=value, status="PENDING")
            db.add(request)
        else:
            request.old_value = current
            request.new_value = value
        pending[field] = value
    db.commit()
    db.refresh(user)
    if pending:
        labels = "、".join(FIELD_LABELS[field] for field in pending)
        message = f"{labels}修改申请已提交，管理员审核通过后生效"
    else:
        message = "资料已更新"
    return success({"user": user_json(user), "pending_changes": pending, "message": message})


@router.get("/profile/change-requests")
def my_change_requests(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ProfileChangeRequest)
            .filter(ProfileChangeRequest.user_id == user.id)
            .order_by(ProfileChangeRequest.id.desc()).limit(20).all())
    return success({"list": [change_request_json(item) for item in rows]})
