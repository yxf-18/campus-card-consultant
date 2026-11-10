from __future__ import annotations

import csv
import json
import re
import uuid
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import require_admin, require_internal_token
from ..models import (CampusCardAccount, ChatFeedback, ChatMessage, KnowledgeCategory,
                      KnowledgeDocument, RagSyncTask, SysConfig, SysUser, now_local)
from ..responses import ApiError, success
from ..schemas import ConfigUpdateRequest, FeedbackHandleRequest, InternalToolRequest, UserStatusRequest
from ..security import create_download_token
from ..services import (export_document_rows, export_feedback_rows, export_qa_rows,
                        export_user_rows, get_config, run_sync_task)
from ..utils import fmt_dt, pagination

router = APIRouter(prefix="/admin", tags=["后台-运营管理"])
internal_router = APIRouter(prefix="/internal/v1", tags=["内部工具"])
settings = get_settings()


def admin_user_json(user: SysUser) -> dict:
    return {"user_id": user.id, "username": user.username, "nickname": user.nickname,
            "phone": user.phone or "", "email": user.email or "", "student_no": user.student_no or "",
            "role": user.role, "status": user.status, "last_login_at": fmt_dt(user.last_login_at),
            "created_at": fmt_dt(user.created_at), "updated_at": fmt_dt(user.updated_at)}


@router.get("/users")
def list_users(keyword: str = "", role: str | None = None, status: str | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(SysUser)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(SysUser.username.like(pattern), SysUser.nickname.like(pattern),
                                 SysUser.phone.like(pattern)))
    if role:
        query = query.filter(SysUser.role == role)
    if status:
        query = query.filter(SysUser.status == status)
    total = query.count()
    rows = query.order_by(SysUser.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return success({"list": [admin_user_json(item) for item in rows]}, pagination(page, page_size, total))


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: int, payload: UserStatusRequest, admin: SysUser = Depends(require_admin),
                       db: Session = Depends(get_db)):
    user = db.get(SysUser, user_id)
    if user is None:
        raise ApiError(100107, "用户不存在", 404)
    if user.role == "ADMIN" and payload.status == "DISABLED":
        raise ApiError(100105, "管理员账号不能被禁用，只能封禁普通用户", 400)
    user.status = payload.status
    db.commit()
    db.refresh(user)
    return success({"user": admin_user_json(user)})


@router.get("/sync/tasks")
def list_sync_tasks(status: str | None = None, document_id: int | None = None,
                    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(RagSyncTask, KnowledgeDocument).join(
        KnowledgeDocument, KnowledgeDocument.id == RagSyncTask.document_id)
    if status:
        query = query.filter(RagSyncTask.status == status)
    if document_id is not None:
        query = query.filter(RagSyncTask.document_id == document_id)
    total = query.count()
    rows = query.order_by(RagSyncTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for task, doc in rows:
        data.append({"task_id": task.id, "document_id": task.document_id, "document_title": doc.title,
                     "task_type": task.task_type, "target_version": task.target_version,
                     "status": task.status, "retry_count": task.retry_count,
                     "chunk_count": task.chunk_count, "duration_ms": task.duration_ms,
                     "error_message": task.error_message or "", "created_at": fmt_dt(task.created_at),
                     "started_at": fmt_dt(task.started_at), "finished_at": fmt_dt(task.finished_at)})
    return success({"list": data}, pagination(page, page_size, total))


@router.post("/sync/tasks/{task_id}/retry")
def retry_sync_task(task_id: int, background_tasks: BackgroundTasks,
                    _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    task = db.get(RagSyncTask, task_id)
    if task is None or task.status != "FAILED":
        raise ApiError(300104, "同步任务不存在或状态不允许重试", 400)
    task.status = "PENDING"
    task.retry_count += 1
    task.error_message = None
    task.started_at = None
    task.finished_at = None
    db.commit()
    background_tasks.add_task(run_sync_task, task.id)
    return success({"task_id": task.id, "status": task.status, "retry_count": task.retry_count})


@router.get("/feedbacks")
def list_feedbacks(status: str | None = None, rating: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    query = (db.query(ChatFeedback, ChatMessage, SysUser)
             .join(ChatMessage, ChatMessage.id == ChatFeedback.message_id)
             .join(SysUser, SysUser.id == ChatFeedback.user_id))
    if status:
        query = query.filter(ChatFeedback.status == status)
    if rating:
        query = query.filter(ChatFeedback.rating == rating)
    total = query.count()
    rows = query.order_by(ChatFeedback.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [{"feedback_id": feedback.id, "message_id": feedback.message_id,
             "user_id": user.id, "username": user.username, "nickname": user.nickname,
             "rating": feedback.rating, "reason": feedback.reason or "", "status": feedback.status,
             "answer": message.content, "handled_by": feedback.handled_by,
             "handled_at": fmt_dt(feedback.handled_at), "created_at": fmt_dt(feedback.created_at)}
            for feedback, message, user in rows]
    return success({"list": data}, pagination(page, page_size, total))


@router.patch("/feedbacks/{feedback_id}")
def handle_feedback(feedback_id: int, payload: FeedbackHandleRequest,
                    admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    feedback = db.get(ChatFeedback, feedback_id)
    if feedback is None:
        raise ApiError(700104, "反馈不存在", 404)
    feedback.status = payload.status
    feedback.handled_by = admin.id
    feedback.handled_at = now_local() if payload.status != "PENDING" else None
    db.commit()
    db.refresh(feedback)
    return success({"feedback_id": feedback.id, "status": feedback.status,
                    "handled_by": feedback.handled_by, "handled_at": fmt_dt(feedback.handled_at)})


@router.get("/statistics/overview")
def statistics_overview(start_date: date | None = None, end_date: date | None = None,
                        dimension: Literal["day", "week", "month"] = "day",
                        _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    end = end_date or now_local().date()
    start = start_date or (end - timedelta(days=29))
    if start > end:
        raise ApiError(100105, "开始日期不得晚于结束日期", 400)
    total_users = db.query(SysUser).count()
    active_users = db.query(SysUser).filter(func.date(SysUser.last_login_at) >= start,
                                             func.date(SysUser.last_login_at) <= end).count()
    new_users = db.query(SysUser).filter(func.date(SysUser.created_at) >= start,
                                          func.date(SysUser.created_at) <= end).count()
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.is_deleted.is_(False))
    doc_total = docs.count()
    doc_published = docs.filter(KnowledgeDocument.status == "PUBLISHED").count()
    doc_offline = docs.filter(KnowledgeDocument.status == "OFFLINE").count()
    user_messages = (db.query(ChatMessage).filter(ChatMessage.role == "USER",
                                                  func.date(ChatMessage.created_at) >= start,
                                                  func.date(ChatMessage.created_at) <= end))
    assistant_messages = (db.query(ChatMessage).filter(ChatMessage.role == "ASSISTANT",
                                                       func.date(ChatMessage.created_at) >= start,
                                                       func.date(ChatMessage.created_at) <= end))
    like_count = db.query(ChatFeedback).filter(ChatFeedback.rating == "LIKE",
                                                func.date(ChatFeedback.created_at) >= start,
                                                func.date(ChatFeedback.created_at) <= end).count()
    dislike_count = db.query(ChatFeedback).filter(ChatFeedback.rating == "DISLIKE",
                                                   func.date(ChatFeedback.created_at) >= start,
                                                   func.date(ChatFeedback.created_at) <= end).count()
    pending = db.query(ChatFeedback).filter(ChatFeedback.status == "PENDING").count()

    def bucket(value: date) -> str:
        if dimension == "week":
            return (value - timedelta(days=value.weekday())).isoformat()
        if dimension == "month":
            return value.strftime("%Y-%m")
        return value.isoformat()

    trend: OrderedDict[str, dict] = OrderedDict()
    cursor = start
    while cursor <= end:
        key = bucket(cursor)
        trend.setdefault(key, {"date": key, "user_active": 0, "qa_count": 0, "feedback_count": 0})
        cursor += timedelta(days=1)
    for user in db.query(SysUser).filter(SysUser.last_login_at.is_not(None)).all():
        login_date = user.last_login_at.date()
        if start <= login_date <= end:
            trend[bucket(login_date)]["user_active"] += 1
    for message in user_messages.all():
        trend[bucket(message.created_at.date())]["qa_count"] += 1
    feedbacks = db.query(ChatFeedback).filter(func.date(ChatFeedback.created_at) >= start,
                                               func.date(ChatFeedback.created_at) <= end).all()
    for feedback in feedbacks:
        trend[bucket(feedback.created_at.date())]["feedback_count"] += 1
    answered = assistant_messages.filter(ChatMessage.is_grounded.is_(True)).count()
    fallback = assistant_messages.filter(ChatMessage.is_grounded.is_(False)).count()
    return success({
        "range": {"start_date": start.isoformat(), "end_date": end.isoformat(), "dimension": dimension},
        "user": {"total": total_users, "active": active_users, "new": new_users},
        "document": {"total": doc_total, "published": doc_published, "offline": doc_offline},
        "qa": {"total": user_messages.count(), "answered": answered, "fallback": fallback},
        "feedback": {"like": like_count, "dislike": dislike_count, "pending": pending},
        "trend": list(trend.values()),
    })


def config_json(item: SysConfig) -> dict:
    return {"config_key": item.config_key, "config_value": item.config_value or "",
            "config_group": item.config_group, "value_type": item.value_type,
            "remark": item.description or "", "updated_at": fmt_dt(item.updated_at), "updated_by": item.updated_by}


@router.get("/configs")
def list_configs(config_group: str | None = None, _admin: SysUser = Depends(require_admin),
                 db: Session = Depends(get_db)):
    query = db.query(SysConfig)
    if config_group:
        query = query.filter(SysConfig.config_group == config_group)
    rows = query.order_by(SysConfig.config_group, SysConfig.config_key).all()
    return success({"configs": [config_json(item) for item in rows]})


@router.put("/configs/{config_key}")
def update_config(config_key: str, payload: ConfigUpdateRequest,
                  admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.query(SysConfig).filter(SysConfig.config_key == config_key).first()
    if item is None:
        raise ApiError(100105, "配置键不在白名单内", 400)
    value = payload.config_value
    if item.value_type == "INT":
        if not re.fullmatch(r"\d+", value):
            raise ApiError(100105, "该配置必须为整数", 400)
    elif item.value_type == "BOOL" and value.lower() not in {"true", "false", "0", "1"}:
        raise ApiError(100105, "该配置必须为布尔值", 400)
    elif item.value_type == "JSON":
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ApiError(100105, "该配置必须为合法JSON", 400) from exc
    item.config_value = value
    if payload.remark is not None:
        item.description = payload.remark
    item.updated_by = admin.id
    item.updated_at = now_local()
    db.commit()
    db.refresh(item)
    return success({"config": config_json(item)})


class ExportRequest(BaseModel):
    type: Literal["user", "document", "qa", "feedback"]
    start_date: date
    end_date: date
    dimension: Literal["day", "week", "month"] = "day"
    desensitize: bool = True
    format: Literal["CSV", "XLSX"] = "CSV"

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不得早于开始日期")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("导出区间不能超过一年")
        return self


@router.post("/statistics/export")
def export_statistics(payload: ExportRequest, _admin: SysUser = Depends(require_admin),
                      db: Session = Depends(get_db)):
    if payload.type == "user":
        rows = export_user_rows(db, payload.start_date, payload.end_date, payload.desensitize)
    elif payload.type == "document":
        rows = export_document_rows(db, payload.start_date, payload.end_date)
    elif payload.type == "qa":
        rows = export_qa_rows(db, payload.start_date, payload.end_date)
    else:
        rows = export_feedback_rows(db, payload.start_date, payload.end_date)
    suffix = ".xlsx" if payload.format == "XLSX" else ".csv"
    filename = f"{payload.type}_{payload.start_date}_{payload.end_date}_{uuid.uuid4().hex[:8]}{suffix}"
    path = settings.export_dir / filename
    if payload.format == "XLSX":
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = payload.type
        for row in rows:
            sheet.append(row)
        workbook.save(path)
    else:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
    token = create_download_token("export", filename, 300)
    return success({"file_url": f"{settings.public_base_url}/api/v1/files/exports/{token}",
                    "file_name": filename, "format": payload.format,
                    "row_count": max(0, len(rows) - 1), "desensitized": payload.desensitize,
                    "expires_in": 300})


@internal_router.post("/tools/query")
def internal_tool_query(payload: InternalToolRequest, _: None = Depends(require_internal_token),
                        db: Session = Depends(get_db)):
    if payload.tool_name == "get_card_balance":
        context = payload.user_context or {}
        requester_id = context.get("user_id")
        role = context.get("role")
        requested_student_no = str(payload.params.get("student_no", "")).strip()
        requested_card_no = str(payload.params.get("card_no", "")).strip()
        if role != "USER":
            raise ApiError(100201, "仅普通用户可查询本人校园卡余额", 403)
        own_student_no = str(context.get("student_no", "")).strip()
        if requested_student_no and requested_student_no != own_student_no:
            raise ApiError(100201, "普通用户只能查询本人校园卡余额", 403)
        if requested_card_no:
            raise ApiError(100201, "普通用户只能查询本人校园卡余额", 403)
        if not requester_id:
            raise ApiError(100201, "缺少用户身份，无法查询校园卡余额", 403)
        query = (db.query(CampusCardAccount, SysUser)
                 .join(SysUser, SysUser.id == CampusCardAccount.user_id)
                 .filter(CampusCardAccount.user_id == int(requester_id)))
        row = query.first()
        if row is None:
            return {"result": {"found": False, "message": "未找到对应的校园卡账户"}}
        account, student = row
        card_no = account.card_no
        masked_card_no = card_no[:4] + "****" + card_no[-4:] if len(card_no) >= 8 else card_no
        return {"result": {"found": True, "student_no": student.student_no or "",
                           "student_name": student.nickname, "card_no": masked_card_no,
                           "balance": str(account.balance), "status": account.status,
                           "source": "本地校园卡账户数据库"}}
    if payload.tool_name == "find_documents":
        keyword = str(payload.params.get("keyword", "")).strip()
        query = db.query(KnowledgeDocument).filter(KnowledgeDocument.is_deleted.is_(False),
                                                    KnowledgeDocument.status == "PUBLISHED")
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(or_(KnowledgeDocument.title.like(pattern),
                                     KnowledgeDocument.summary.like(pattern)))
        docs = query.order_by(KnowledgeDocument.id).limit(10).all()
        return {"result": [{"document_id": doc.id, "title": doc.title,
                            "summary": doc.summary or ""} for doc in docs]}
    if payload.tool_name == "list_categories":
        categories = db.query(KnowledgeCategory).filter(KnowledgeCategory.status == "ENABLED").order_by(
            KnowledgeCategory.sort_order).all()
        return {"result": [{"category_id": item.id, "name": item.name} for item in categories]}
    channels = get_config(db, "service.channels", "{}")
    try:
        result = json.loads(channels)
    except json.JSONDecodeError:
        result = {"note": channels}
    return {"result": result}
