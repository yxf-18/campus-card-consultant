from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .ai_client import ai_client
from .config import get_settings
from .database import SessionLocal
from .models import (
    ChatCitation, ChatFeedback, ChatMessage, ChatSession, KnowledgeCategory, KnowledgeChunk,
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

# 配置不是“随便存一个字符串”：后台修改时必须先通过类型与业务范围校验，
# 否则 top_k=0、下载有效期=0 之类的值会直接破坏问答和下载链路。
CONFIG_RULES: dict[str, tuple[str, float | None, float | None]] = {
    "home.documents_limit": ("int", 1, 20),
    "rag.top_k": ("int", 1, 20),
    "rag.similarity_threshold": ("float", 0.0, 1.0),
    "chat.context_max_chars": ("int", 500, 20000),
    "chat.history_turns": ("int", 1, 50),
    "chat.session_retention_days": ("int", 7, 3650),
    "auth.login_fail_limit": ("int", 1, 20),
    "auth.login_lock_minutes": ("int", 1, 1440),
    "upload.max_size_mb": ("int", 1, 100),
    "download.url_ttl_seconds": ("int", 30, 3600),
    "web.enabled": ("bool", None, None),
    "service.channels": ("json", None, None),
    "security.sensitive_words": ("json", None, None),
}

# 账户类操作只提供办理指引，业务后端与 AI 服务使用同一份口径。
ACCOUNT_ACTION_PHRASES = (
    "帮我充值", "替我充值", "帮我挂失", "替我挂失", "冻结我的卡",
    "解冻我的卡", "帮我退款", "替我退款",
)


def validate_config_value(key: str, value_type: str, raw_value: str) -> str:
    """校验并归一化后台配置值，非法值抛出 ValueError。"""
    value = (raw_value or "").strip()
    kind, lower, upper = CONFIG_RULES.get(key, (value_type.lower(), None, None))
    if kind == "int":
        if not re.fullmatch(r"\d+", value):
            raise ValueError("该配置必须为正整数")
        number = int(value)
        if lower is not None and upper is not None and not lower <= number <= upper:
            raise ValueError(f"该配置取值范围为 {int(lower)}-{int(upper)}")
        return str(number)
    if kind == "float":
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError("该配置必须为数字") from exc
        if lower is not None and upper is not None and not lower <= number <= upper:
            raise ValueError(f"该配置取值范围为 {lower:g}-{upper:g}")
        return f"{number:g}"
    if kind == "bool":
        lowered = value.lower()
        if lowered in {"true", "1"}:
            return "true"
        if lowered in {"false", "0"}:
            return "false"
        raise ValueError("该配置必须为布尔值")
    if kind == "json":
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("该配置必须为合法JSON") from exc
        if key == "security.sensitive_words":
            if not isinstance(parsed, list) or not parsed or not all(
                    isinstance(item, str) and item.strip() for item in parsed):
                raise ValueError("敏感词配置必须为非空字符串数组")
            parsed = [item.strip() for item in parsed]
        if key == "service.channels" and not isinstance(parsed, dict):
            raise ValueError("服务渠道配置必须为JSON对象")
        return json.dumps(parsed, ensure_ascii=False)
    return value


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


def get_bool_config(db: Session, key: str, default: bool) -> bool:
    value = get_config(db, key, "true" if default else "false").strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    return default


SENSITIVE_INTENT_HINTS = ("告诉我", "发给我", "提供给我", "明文", "完整", "截图", "拍照", "转发给我")


def sensitive_reminder(db: Session, question: str) -> str:
    """命中“敏感词 + 索取意图”时追加安全提醒，而不是对所有转账问题一刀切拒答。"""
    try:
        words = json.loads(get_config(db, "security.sensitive_words", "[]"))
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(words, list):
        return ""
    hits = [str(word).strip() for word in words
            if isinstance(word, str) and word.strip() and word.strip() in question]
    if not hits or not any(hint in question for hint in SENSITIVE_INTENT_HINTS):
        return ""
    return ("安全提醒：涉及" + "、".join(dict.fromkeys(hits)) +
            "等敏感信息时，请仅通过学校正式渠道办理，不要向他人提供密码、验证码或完整身份证号。")


def identity_conflict(db: Session, value: str | None, exclude_id: int | None = None) -> bool:
    """用户名、手机号、邮箱、学号共用一个登录入口，因此不能跨字段重名。"""
    if not value:
        return False
    query = db.query(SysUser.id).filter(or_(SysUser.username == value, SysUser.phone == value,
                                            SysUser.email == value, SysUser.student_no == value))
    if exclude_id is not None:
        query = query.filter(SysUser.id != exclude_id)
    return query.first() is not None


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


def visible_documents_query(db: Session):
    """公开端、下载端和内部工具共用的“用户可见文档”过滤条件。"""
    today = now_local().date()
    return (db.query(KnowledgeDocument, KnowledgeCategory)
            .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
            .filter(KnowledgeCategory.status == "ENABLED",
                    KnowledgeDocument.status == "PUBLISHED",
                    KnowledgeDocument.is_deleted.is_(False),
                    or_(KnowledgeDocument.effective_date.is_(None),
                        KnowledgeDocument.effective_date <= today),
                    or_(KnowledgeDocument.expire_date.is_(None),
                        KnowledgeDocument.expire_date >= today)))


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


_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")


def _text_tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _best_snippet(text: str, query_tokens: set[str], limit: int = 700) -> str:
    """在长文档中截取与问题最相关的一段，而不是永远返回开头 700 字。"""
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    step = max(1, limit // 2)
    last_start = len(cleaned) - limit
    best_start, best_hits = 0, -1
    for start in range(0, last_start + 1, step):
        window = cleaned[start:start + limit]
        hits = sum(1 for token in query_tokens if token in window)
        if hits > best_hits:
            best_start, best_hits = start, hits
    if best_start:
        boundary = min((pos for pos in (
            cleaned.find("\n", best_start, best_start + 120),
            cleaned.find("。", best_start, best_start + 120),
        ) if pos != -1), default=-1)
        if boundary != -1:
            best_start = boundary + 1
    return cleaned[best_start:best_start + limit].strip() or cleaned[:limit]


def local_retrieve(db: Session, question: str, allowed: dict[int, int], top_k: int,
                   document_id: int | None = None, threshold: float = 0.12) -> list[dict[str, Any]]:
    """AI 服务不可用时按词重合度应急检索，并保持与向量检索相近的召回门槛。"""
    query_tokens = _text_tokens(question)
    if not query_tokens:
        return []
    rows_query = (db.query(KnowledgeDocument, KnowledgeCategory)
                  .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
                  .filter(KnowledgeDocument.status == "PUBLISHED", KnowledgeDocument.is_deleted.is_(False),
                          KnowledgeCategory.status == "ENABLED"))
    if allowed:
        rows_query = rows_query.filter(KnowledgeDocument.id.in_(list(allowed.keys())))
    if document_id is not None:
        rows_query = rows_query.filter(KnowledgeDocument.id == document_id)
    rows = rows_query.all()
    min_score = 0.0 if document_id is not None else max(0.15, min(0.6, threshold))
    scored: list[tuple[float, KnowledgeDocument, str]] = []
    for doc, category in rows:
        if not is_document_visible(doc, category):
            continue
        text = " ".join(filter(None, [doc.title, doc.summary, doc.keywords, doc.parsed_text]))
        matched = query_tokens & _text_tokens(text)
        score = len(matched) / len(query_tokens) + (0.3 if doc.id == document_id else 0)
        if score < min_score:
            continue
        snippet = _best_snippet(doc.parsed_text or doc.summary or doc.title, matched or query_tokens)
        scored.append((score, doc, snippet))
    scored.sort(key=lambda item: item[0], reverse=True)
    result = []
    for score, doc, snippet in scored[:top_k]:
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


def make_download_url(document_id: int, ttl_seconds: int = 300) -> str:
    token = create_download_token("document", document_id, max(1, ttl_seconds))
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


def purge_expired_sessions(db: Session, retention_days: int) -> int:
    """物理清理“已删除且超过保留期”的会话，避免问答内容长期滞留。"""
    cutoff = now_local() - timedelta(days=max(1, retention_days))
    session_ids = [row[0] for row in db.query(ChatSession.id).filter(
        ChatSession.status == "DELETED",
        ChatSession.deleted_at.is_not(None),
        ChatSession.deleted_at < cutoff).all()]
    if not session_ids:
        return 0
    message_ids = [row[0] for row in db.query(ChatMessage.id).filter(
        ChatMessage.session_id.in_(session_ids)).all()]
    if message_ids:
        db.query(ChatMessage).filter(ChatMessage.id.in_(message_ids)).update(
            {ChatMessage.reply_to_message_id: None}, synchronize_session=False)
        db.query(ChatCitation).filter(ChatCitation.message_id.in_(message_ids)).delete(synchronize_session=False)
        db.query(ChatFeedback).filter(ChatFeedback.message_id.in_(message_ids)).delete(synchronize_session=False)
        db.query(ChatMessage).filter(ChatMessage.id.in_(message_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)
    db.commit()
    return len(session_ids)


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
