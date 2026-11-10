from __future__ import annotations

from pydantic import BaseModel, Field


class AllowedVersion(BaseModel):
    document_id: int
    version_no: int


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    allowed_versions: list[AllowedVersion] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.12, ge=-1, le=1)
    document_id: int | None = None


class UnindexRequest(BaseModel):
    document_id: int


class SummarizeRequest(BaseModel):
    messages: list[dict[str, str]] = Field(default_factory=list)
    previous_summary: str = ""


class ChatPayload(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    contexts: list[dict] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)
    enable_web: bool = True
    enable_db_tool: bool = True
    service_channels: str = ""
    user_context: dict = Field(default_factory=dict)
