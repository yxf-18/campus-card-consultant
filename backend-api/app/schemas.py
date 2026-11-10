from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=32)
    phone: str | None = Field(default=None, max_length=11)
    email: str | None = Field(default=None, max_length=64)
    student_no: str | None = Field(default=None, max_length=32)
    nickname: str | None = Field(default=None, max_length=32)
    privacy_agreed: bool

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("密码必须同时包含字母和数字")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"1\d{10}", value):
            raise ValueError("手机号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("邮箱格式不正确")
        return value

    @model_validator(mode="after")
    def validate_privacy(self):
        if not self.privacy_agreed:
            raise ValueError("必须同意隐私协议")
        return self


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=32)
    login_type: Literal["USERNAME", "PHONE", "EMAIL", "STUDENT_NO"] | None = None
    client_type: Literal["MOBILE", "ADMIN"] | None = None
    redirect_url: str | None = Field(default=None, max_length=500)


class ProfileBindRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    student_no: str = Field(min_length=1, max_length=32)
    nickname: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=64)

    @field_validator("phone")
    @classmethod
    def validate_bind_phone(cls, value: str) -> str:
        if not re.fullmatch(r"1\d{10}", value):
            raise ValueError("手机号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_bind_email(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("邮箱格式不正确")
        return value


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)


class SessionUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class FeedbackRequest(BaseModel):
    rating: Literal["LIKE", "DISLIKE"]
    reason: str | None = Field(default=None, max_length=500)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: int | None = None
    document_id: int | None = None
    enable_web: bool = True
    enable_db_tool: bool = True
    stream: bool = True


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
