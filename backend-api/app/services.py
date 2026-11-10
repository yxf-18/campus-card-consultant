from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .ai_client import ai_client
from .config import get_settings
from .database import SessionLocal
from .models import (
    ChatFeedback, ChatMessage, ChatSession, KnowledgeCategory, KnowledgeChunk,
    KnowledgeDocument, RagSyncTask, SysConfig, SysUser, now_local,
)
from .security import create_download_token
from .utils import fmt_date, fmt_dt

settings = get_settings()

DEFAULT_CONFIGS = [
    ("home.documents_limit", "home", "5", "INT", "首页每个分类展示的文档数量"),
    ("rag.top_k", "rag", "5", "INT", "问答召回切片数量"),
    ("rag.similarity_threshold", "rag", "0.12", "STRING", "问答召回相似度阈值"),
    ("chat.context_max_chars", "chat", "6000", "INT", "参与问答的上下文字符上限"),
    ("chat.history_turns", "chat", "10", "INT", "参与上下文的历史轮数"),
    ("chat.session_retention_days", "chat", "180", "INT", "会话数据保留天数"),
    ("auth.login_fail_limit", "auth", "5", "INT", "连续登录失败锁定阈值"),
    ("auth.login_lock_minutes", "auth", "10", "INT", "登录失败锁定分钟数"),
    ("upload.max_size_mb", "upload", "20", "INT", "文档上传大小上限"),
    ("download.url_ttl_seconds", "download", "300", "INT", "下载地址有效时长（秒）"),
    ("service.channels", "service", json.dumps({"name": "校园卡服务中心", "note": "具体地点与开放时间请以学校正式通知为准"}, ensure_ascii=False), "JSON", "正式服务渠道说明"),
    ("security.sensitive_words", "security", json.dumps(["转账", "密码明文", "身份证号"], ensure_ascii=False), "JSON", "安全兜底敏感词"),
    ("web.enabled", "web", "true", "BOOL", "是否启用Web Search（三来源问答默认启用）"),
]


def get_config(db: Session, key: str, default: str = "") -> str:
    row = db.query(SysConfig).filter(SysConfig.config_key == key).first()
    return row.config_value if row and row.config_value is not None else default


def get_int_config(db: Session, key: str, default: int) -> int:
    try:
        return int(get_config(db, key, str(default)))
    except ValueError:
        return default


def get_float_config(db: Session, key: str, default: float) -> float:
    try:
        return float(get_config(db, key, str(default)))
    except ValueError:
        return default


def category_json(category: KnowledgeCategory, document_count: int | None = None) -> dict[str, Any]:
    data = {"category_id": category.id, "name": category.name,
            "icon": category.default_cover_url or "", "default_cover_url": category.default_cover_url or "",
            "sort_order": category.sort_order, "status": category.status,
            "created_at": fmt_dt(category.created_at), "updated_at": fmt_dt(category.updated_at)}
    if document_count is not None:
        data["document_count"] = document_count
    return data


def document_json(document: KnowledgeDocument, chunk_count: int | None = None) -> dict[str, Any]:
    data = {
        "document_id": document.id, "category_id": document.category_id, "title": document.title,
        "summary": document.summary or "", "keywords": document.keywords or "", "cover_url": document.cover_url or "",
        "file_name": document.file_name, "file_type": document.file_type, "file_size": document.file_size,
        "source_department": document.source_department or "", "document_no": document.document_no or "",
        "effective_date": fmt_date(document.effective_date), "expire_date": fmt_date(document.expire_date),
        "status": document.status, "sync_status": document.sync_status,
        "active_index_version": document.active_index_version, "view_count": document.view_count,
        "sort_order": document.sort_order, "allow_download": document.allow_download,
        "published_at": fmt_dt(document.published_at), "created_at": fmt_dt(document.created_at),
        "updated_at": fmt_dt(document.updated_at),
    }
    if chunk_count is not None:
        data["chunk_count"] = chunk_count
    return data


def is_document_visible(document: KnowledgeDocument, category: KnowledgeCategory | None, today: date | None = None) -> bool:
    today = today or now_local().date()
    return bool(category and category.status == "ENABLED" and document.status == "PUBLISHED"
                and not document.is_deleted
                and (document.effective_date is None or document.effective_date <= today)
                and (document.expire_date is None or document.expire_date >= today))


def visible_versions(db: Session) -> dict[int, int]:
    rows = (db.query(KnowledgeDocument, KnowledgeCategory)
            .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
            .filter(KnowledgeDocument.status == "PUBLISHED", KnowledgeDocument.is_deleted.is_(False),
                    KnowledgeDocument.active_index_version > 0, KnowledgeCategory.status == "ENABLED").all())
    today = now_local().date()
    return {doc.id: doc.active_index_version for doc, category in rows if is_document_visible(doc, category, today)}


def allowed_versions_for(db: Session, document_id: int | None = None) -> dict[int, int]:
    versions = visible_versions(db)
    if document_id is not None:
        return {document_id: versions[document_id]} if document_id in versions else {}
    return versions


def local_retrieve(db: Session, question: str, allowed: dict[int, int], top_k: int,
                   document_id: int | None = None) -> list[dict[str, Any]]:
    rows_query = (db.query(KnowledgeDocument, KnowledgeCategory)
                  .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
                  .filter(KnowledgeDocument.status == "PUBLISHED", KnowledgeDocument.is_deleted.is_(False),
                          KnowledgeCategory.status == "ENABLED"))
    if allowed:
        rows_query = rows_query.filter(KnowledgeDocument.id.in_(list(allowed.keys())))
    if document_id is not None:
        rows_query = rows_query.filter(KnowledgeDocument.id == document_id)
    rows = rows_query.all()
    query_chars = set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", question.lower()))
    scored: list[tuple[float, KnowledgeDocument, str]] = []
    for doc, category in rows:
        if not is_document_visible(doc, category):
            continue
        text = " ".join(filter(None, [doc.title, doc.summary, doc.keywords, doc.parsed_text]))
        chars = set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text.lower()))
        overlap = len(query_chars & chars)
        score = overlap / max(1, len(query_chars)) + (0.3 if doc.id == document_id else 0)
        snippet = (doc.parsed_text or doc.summary or doc.title)[:700]
        scored.append((score, doc, snippet))
    scored.sort(key=lambda item: item[0], reverse=True)
    result = []
    for score, doc, snippet in scored[:top_k]:
        if score <= 0 and not document_id:
            continue
        result.append({"vector_id": f"local:{doc.id}", "chunk_id": None, "document_id": doc.id,
                       "title": doc.title, "snippet": snippet, "page_no": None, "score": round(score, 4)})
    return result


def safe_file_name(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", base)
    return cleaned[:180] or "document.txt"


def save_upload(content: bytes, original_name: str) -> tuple[Path, str]:
    original_name = safe_file_name(original_name)
    suffix = Path(original_name).suffix.lower()
    digest = hashlib.sha256(content).hexdigest()
    target = settings.upload_dir / f"{digest[:20]}{suffix}"
    target.write_bytes(content)
    return target, digest


def make_download_url(document_id: int) -> str:
    token = create_download_token("document", document_id, 300)
    # Keep both PC and mobile on the same origin as the frontend/proxy.
    return f"/api/v1/files/download/{token}"


def build_context(db: Session, session: ChatSession, max_chars: int, max_turns: int) -> list[dict[str, str]]:
    messages = (db.query(ChatMessage).filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(max_turns * 2).all())
    messages.reverse()
    result: list[dict[str, str]] = []
    if session.context_summary:
        result.append({"role": "system", "content": f"此前会话摘要：{session.context_summary}"})
    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(messages):
        if message.status != "SUCCESS" or not message.content:
            continue
        content = message.content
        if used + len(content) > max_chars:
            content = content[: max(0, max_chars - used)]
        if content:
            selected.append({"role": "user" if message.role == "USER" else "assistant", "content": content})
            used += len(content)
        if used >= max_chars:
            break
    result.extend(reversed(selected))
    return result


async def index_document_for_task(db: Session, document: KnowledgeDocument, task: RagSyncTask) -> None:
    started = time.perf_counter()
    task.status = "RUNNING"
    task.started_at = now_local()
    document.sync_status = "RUNNING"
    db.commit()
    try:
        if task.task_type in {"OFFLINE", "DELETE"}:
            await ai_client.unindex(document.id)
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).update(
                {KnowledgeChunk.chunk_status: "INACTIVE"}, synchronize_session=False)
            document.active_index_version = 0
            document.sync_status = "NOT_INDEXED"
        else:
            category = db.get(KnowledgeCategory, document.category_id)
            file_path = settings.upload_dir / Path(document.storage_path).name
            if not file_path.exists():
                raise FileNotFoundError("原始文件不存在")
            result = await ai_client.index_document(
                document_id=document.id, version_no=task.target_version, title=document.title,
                category=category.name if category else "", file_path=file_path,
                file_name=document.file_name, content_type="application/octet-stream")
            chunks = result.get("chunks", [])
            if not chunks:
                raise ValueError("文档未生成有效切片")
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id,
                                            KnowledgeChunk.version_no == task.target_version).delete(synchronize_session=False)
            for chunk in chunks:
                content = str(chunk.get("content", ""))
                db.add(KnowledgeChunk(
                    document_id=document.id, version_no=task.target_version,
                    chunk_index=int(chunk.get("chunk_index", 0)), heading_path=chunk.get("heading_path"),
                    page_no=chunk.get("page_no"), content=content, char_count=len(content),
                    vector_id=chunk.get("vector_id"), embedding_model=chunk.get("embedding_model"),
                    chunk_status="ACTIVE"))
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id,
                                            KnowledgeChunk.version_no != task.target_version).update(
                {KnowledgeChunk.chunk_status: "INACTIVE"}, synchronize_session=False)
            document.active_index_version = task.target_version
            document.sync_status = "SUCCESS"
            if result.get("parsed_text"):
                document.parsed_text = str(result["parsed_text"])
            task.chunk_count = len(chunks)
        task.status = "SUCCESS"
        task.finished_at = now_local()
        task.duration_ms = int((time.perf_counter() - started) * 1000)
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.get(RagSyncTask, task.id)
        document = db.get(KnowledgeDocument, document.id)
        if task:
            task.status = "FAILED"
            task.error_message = str(exc)[:1000]
            task.finished_at = now_local()
            task.duration_ms = int((time.perf_counter() - started) * 1000)
        if document:
            document.sync_status = "FAILED"
        db.commit()


async def run_sync_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(RagSyncTask, task_id)
        if task is None:
            return
        document = db.get(KnowledgeDocument, task.document_id)
        if document is None:
            task.status = "FAILED"
            task.error_message = "文档不存在"
            db.commit()
            return
        await index_document_for_task(db, document, task)
    finally:
        db.close()


def trigger_sync(db: Session, document: KnowledgeDocument, task_type: str, user_id: int) -> RagSyncTask:
    target_version = document.active_index_version + 1 if task_type in {"CREATE", "UPDATE", "REINDEX"} else max(1, document.active_index_version)
    task = RagSyncTask(document_id=document.id, task_type=task_type, target_version=target_version,
                       status="PENDING", created_by=user_id)
    document.sync_status = "PENDING"
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def export_user_rows(db: Session, start_date: date, end_date: date, desensitize: bool = True) -> list[list[Any]]:
    rows = db.query(SysUser).filter(func.date(SysUser.created_at) >= start_date,
                                     func.date(SysUser.created_at) <= end_date).all()
    result: list[list[Any]] = [["user_id", "username", "nickname", "phone", "email", "role", "status", "created_at"]]
    for user in rows:
        phone, email = user.phone or "", user.email or ""
        if desensitize:
            phone = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else ""
            if email and "@" in email:
                local, domain = email.split("@", 1)
                email = (local[:1] if local else "") + "***@" + domain
        result.append([user.id, user.username, user.nickname, phone, email, user.role, user.status, fmt_dt(user.created_at)])
    return result


def export_document_rows(db: Session, start_date: date, end_date: date) -> list[list[Any]]:
    rows = db.query(KnowledgeDocument).filter(func.date(KnowledgeDocument.created_at) >= start_date,
                                              func.date(KnowledgeDocument.created_at) <= end_date).all()
    result: list[list[Any]] = [["document_id", "title", "status", "sync_status", "view_count", "created_at"]]
    result.extend([[d.id, d.title, d.status, d.sync_status, d.view_count, fmt_dt(d.created_at)] for d in rows])
    return result


def export_qa_rows(db: Session, start_date: date, end_date: date) -> list[list[Any]]:
    rows = db.query(ChatMessage).filter(func.date(ChatMessage.created_at) >= start_date,
                                         func.date(ChatMessage.created_at) <= end_date,
                                         ChatMessage.role == "USER").all()
    result: list[list[Any]] = [["message_id", "session_id", "question", "created_at"]]
    result.extend([[m.id, m.session_id, m.content[:200], fmt_dt(m.created_at)] for m in rows])
    return result


def export_feedback_rows(db: Session, start_date: date, end_date: date) -> list[list[Any]]:
    rows = db.query(ChatFeedback).filter(func.date(ChatFeedback.created_at) >= start_date,
                                          func.date(ChatFeedback.created_at) <= end_date).all()
    result: list[list[Any]] = [["feedback_id", "message_id", "rating", "reason", "status", "created_at"]]
    result.extend([[f.id, f.message_id, f.rating, f.reason or "", f.status, fmt_dt(f.created_at)] for f in rows])
    return result
