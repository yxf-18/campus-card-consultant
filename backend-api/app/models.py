from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now_local() -> datetime:
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


IdType = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local, nullable=False)


class SysUser(TimestampMixin, Base):
    __tablename__ = "sys_user"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    student_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("role IN ('USER','ADMIN')", name="ck_user_role"), CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_user_status"))


class CampusCardAccount(TimestampMixin, Base):
    __tablename__ = "campus_card_account"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False, unique=True)
    card_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    balance: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_transaction_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_card_status", "status"),)


class ProfileChangeRequest(TimestampMixin, Base):
    """手机号/邮箱修改申请：用户提交，管理员审核通过后才落到 sys_user。"""
    __tablename__ = "profile_change_request"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(20), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_value: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (
        CheckConstraint("field_name IN ('phone','email')", name="ck_profile_change_field"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_profile_change_status"),
        Index("ix_profile_change_status_created", "status", "created_at"),
        Index("ix_profile_change_user_field", "user_id", "field_name", "status"),
    )


class SysConfig(Base):
    __tablename__ = "sys_config"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config_group: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    config_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="STRING")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local, nullable=False)


class KnowledgeCategory(TimestampMixin, Base):
    __tablename__ = "knowledge_category"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    default_cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLED")


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_document"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(IdType, ForeignKey("knowledge_category.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_INDEXED")
    active_index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (
        Index("ix_document_category_status", "category_id", "status", "is_deleted"),
        Index("ix_document_expire", "expire_date"),
        Index("ix_document_sync", "sync_status"),
    )


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunk"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(IdType, ForeignKey("knowledge_document.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chunk_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", "chunk_index", name="uq_chunk_doc_version_index"),
        Index("ix_chunk_document_status", "document_id", "chunk_status"),
    )


class RagSyncTask(TimestampMixin, Base):
    __tablename__ = "rag_sync_task"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(IdType, ForeignKey("knowledge_document.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[int | None] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_sync_document_status", "document_id", "status"), Index("ix_sync_status_created", "status", "created_at"))


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_session"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_session_user_status_last", "user_id", "status", "last_message_at"),)


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_message"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(IdType, ForeignKey("chat_session.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    reply_to_message_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("chat_message.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCESS")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    suggestions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (Index("ix_message_session_created", "session_id", "created_at"), Index("ix_message_reply_to", "reply_to_message_id"))


class ChatCitation(Base):
    __tablename__ = "chat_citation"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(IdType, ForeignKey("chat_message.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("knowledge_document.id"), nullable=True)
    chunk_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("knowledge_chunk.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    __table_args__ = (Index("ix_citation_message_order", "message_id", "sort_order"),)


class ChatFeedback(TimestampMixin, Base):
    __tablename__ = "chat_feedback"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(IdType, ForeignKey("chat_message.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    handled_by: Mapped[int | None] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"), Index("ix_feedback_status_created", "status", "created_at"))
