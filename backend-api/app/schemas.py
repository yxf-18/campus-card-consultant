from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)
    login_type: Literal["USERNAME", "PHONE", "EMAIL", "STUDENT_NO"] | None = None
    client_type: Literal["MOBILE", "ADMIN"] | None = None
    redirect_url: str | None = Field(default=None, max_length=500)


class ProfileUpdateRequest(BaseModel):
    phone: str | None = Field(default=None, max_length=11)
    student_no: str | None = Field(default=None, max_length=32)
    nickname: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=64)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("手机号不能为空")
        if not re.fullmatch(r"1\d{10}", value):
            raise ValueError("手机号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("student_no")
    @classmethod
    def validate_student_no(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("学号不能为空")
        return value

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProfileReviewRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    remark: str | None = Field(default=None, max_length=500)


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("会话标题不能为空")
        return cleaned


class SessionUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("会话标题不能为空")
        return cleaned


class FeedbackRequest(BaseModel):
    rating: Literal["LIKE", "DISLIKE"]
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: int | None = Field(default=None, gt=0)
    document_id: int | None = Field(default=None, gt=0)
    enable_web: bool = True
    enable_db_tool: bool = True
    stream: bool = True

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("问题不能为空")
        return cleaned


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    icon: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=200)
    sort_order: int = 0
    status: Literal["ENABLED", "DISABLED"] = "ENABLED"


class CategoryUpdateRequest(CategoryCreateRequest):
    pass


class DocumentStatusRequest(BaseModel):
    status: Literal["DRAFT", "PUBLISHED", "OFFLINE"]


class UserStatusRequest(BaseModel):
    status: Literal["ACTIVE", "DISABLED"]


class FeedbackHandleRequest(BaseModel):
    status: Literal["PENDING", "PROCESSED", "IGNORED"]
    reason: str | None = Field(default=None, max_length=500)


class ConfigUpdateRequest(BaseModel):
    config_value: str = Field(min_length=1, max_length=1000)
    remark: str | None = Field(default=None, max_length=200)


class InternalToolRequest(BaseModel):
    tool_name: Literal["find_documents", "list_categories", "get_service_channels", "get_card_balance"]
    params: dict = Field(default_factory=dict)
    user_context: dict = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category_id: int
    summary: str | None = Field(default=None, max_length=500)
    keywords: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=200)
    document_no: str | None = Field(default=None, max_length=100)
    effective_date: date | None = None
    expire_date: date | None = None
    allow_download: bool = True
    sort_order: int = 0
