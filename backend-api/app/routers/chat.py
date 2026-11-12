from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai_client import AIServiceError, ai_client
from ..database import SessionLocal, get_db
from ..dependencies import require_mobile_user
from ..models import (ChatCitation, ChatFeedback, ChatMessage, ChatSession, KnowledgeCategory,
                       KnowledgeChunk, KnowledgeDocument, SysUser, now_local)
from ..responses import ApiError, success
from ..schemas import ChatRequest, FeedbackRequest, SessionCreateRequest, SessionUpdateRequest
from ..services import (ACCOUNT_ACTION_PHRASES, allowed_versions_for, build_context,
                        get_bool_config, get_config, get_float_config, get_int_config,
                        is_document_visible, local_retrieve, sensitive_reminder)
from ..utils import default_suggestions, fmt_dt, pagination

router = APIRouter(prefix="/chat", tags=["AI问答与会话"])

WEB_FIRST_HINTS = ("最新", "实时", "今天", "今日", "今年", "新闻", "官网", "联网", "网上查询")


def is_web_first_question(question: str, enable_web: bool) -> bool:
    return bool(enable_web and any(word in (question or "") for word in WEB_FIRST_HINTS))


def get_owned_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id,
                                            ChatSession.status == "ACTIVE").first()
    if session is None:
        raise ApiError(700101, "会话不存在或无权访问", 404)
    return session


def session_json(session: ChatSession, message_count: int | None = None) -> dict[str, Any]:
    data = {"session_id": session.id, "title": session.title, "status": session.status,
            "last_message_at": fmt_dt(session.last_message_at), "created_at": fmt_dt(session.created_at),
            "updated_at": fmt_dt(session.updated_at)}
    if message_count is not None:
        data["message_count"] = message_count
    return data


@router.get("/sessions")
def list_sessions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    query = db.query(ChatSession).filter(ChatSession.user_id == user.id, ChatSession.status == "ACTIVE")
    total = query.count()
    sessions = query.order_by(ChatSession.last_message_at.desc(), ChatSession.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    counts = dict(db.query(ChatMessage.session_id, func.count(ChatMessage.id))
                  .filter(ChatMessage.session_id.in_([s.id for s in sessions] or [0])).group_by(ChatMessage.session_id).all()) if sessions else {}
    return success({"list": [session_json(s, counts.get(s.id, 0)) for s in sessions]}, pagination(page, page_size, total))


@router.post("/sessions")
def create_session(payload: SessionCreateRequest, user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    session = ChatSession(user_id=user.id, title=payload.title or "新的咨询", last_message_at=now_local())
    db.add(session)
    db.commit()
    db.refresh(session)
    return success({"session": session_json(session, 0)}, status_code=201)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: int, payload: SessionUpdateRequest,
                   user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    session = get_owned_session(db, session_id, user.id)
    session.title = payload.title
    db.commit()
    db.refresh(session)
    return success({"session": session_json(session)})


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    session = get_owned_session(db, session_id, user.id)
    session.status = "DELETED"
    session.deleted_at = now_local()
    db.commit()
    return success({"result": True})


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: int, user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    session = get_owned_session(db, session_id, user.id)
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.id).all()
    feedback = {f.message_id: f for f in db.query(ChatFeedback).filter(ChatFeedback.user_id == user.id,
                                                                      ChatFeedback.message_id.in_([m.id for m in messages] or [0])).all()}
    citations = {}
    for citation in db.query(ChatCitation).filter(ChatCitation.message_id.in_([m.id for m in messages] or [0])).order_by(ChatCitation.sort_order).all():
        citations.setdefault(citation.message_id, []).append({
            "citation_id": citation.id, "source_type": citation.source_type,
            "document_id": citation.document_id, "title": citation.title,
            "source_url": citation.source_url or "", "snippet": citation.snippet or "",
            "page_no": citation.page_no, "tool_name": citation.tool_name or "",
            "sort_order": citation.sort_order})
    data = []
    for message in messages:
        item = {"message_id": message.id, "role": message.role, "content": message.content,
                "status": message.status, "is_grounded": message.is_grounded,
                "suggestions": message.suggestions or [], "created_at": fmt_dt(message.created_at),
                "citations": citations.get(message.id, [])}
        if message.id in feedback:
            item["feedback"] = {"rating": feedback[message.id].rating, "status": feedback[message.id].status}
        data.append(item)
    return success({"session": session_json(session), "messages": data})


def sse_frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def citation_from_context(db: Session, context: dict[str, Any]) -> dict[str, Any]:
    vector_id = context.get("vector_id")
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.vector_id == vector_id).first() if vector_id else None
    return {"source_type": "DOCUMENT", "document_id": context.get("document_id"),
            "chunk_id": chunk.id if chunk else None, "title": context.get("title") or "知识库文档",
            "source_url": "", "snippet": context.get("snippet") or "", "page_no": context.get("page_no"),
            "tool_name": "", "sort_order": 0}


def normalize_citation(raw: dict[str, Any], order: int) -> dict[str, Any]:
    return {"source_type": raw.get("source_type", "DOCUMENT"), "document_id": raw.get("document_id"),
            "chunk_id": raw.get("chunk_id"), "title": raw.get("title") or "来源",
            "source_url": raw.get("source_url") or "", "snippet": raw.get("snippet") or "",
            "page_no": raw.get("page_no"), "tool_name": raw.get("tool_name") or "", "sort_order": order}


def dedupe_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, result = set(), []
    for item in items:
        key = (item.get("source_type"), item.get("document_id"), item.get("source_url"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        result.append(normalize_citation(item, len(result)))
    return result[:10]


def clean_snippet(value: Any, title: str = "", limit: int = 220) -> str:
    """切片里常带 Markdown 标题，回答时去掉标题行和重复标题，只保留正文。"""
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if len(lines) > 1 and re.fullmatch(r"#{1,6}\s*.*", lines[0]):
        lines = lines[1:]
    text = " ".join(re.sub(r"^#{1,6}\s*", "", line) for line in lines)
    text = " ".join(text.split())
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" ：:，,。.、")
    return text[:limit]


def local_answer(question: str, contexts: list[dict[str, Any]]) -> str:
    if any(phrase in question for phrase in ACCOUNT_ACTION_PHRASES):
        return ("本工具只能提供咨询与办理指引，不能直接执行充值、挂失、解冻、退款等账户操作。"
                "请通过学校正式服务渠道办理，并注意保护密码和验证码。")
    if not contexts:
        return ("暂未在知识库中找到足够依据。请补充问题，或联系校园卡服务中心等学校正式渠道；"
                "本回答不构成业务办理承诺。")
    parts = ["根据学校公开的校园卡资料，可以这样处理："]
    seen_titles: set[str] = set()
    for context in contexts:
        title = (context.get("title") or "相关资料").strip()
        if title in seen_titles:
            continue
        snippet = clean_snippet(context.get("snippet") or "", title)
        if not snippet:
            continue
        seen_titles.add(title)
        parts.append(f"- {title}：{snippet}")
        if len(seen_titles) >= 3:
            break
    parts.append("以上内容仅供参考，具体办理要求请以学校最新正式通知为准。")
    return "\n\n".join(parts)


async def stream_local_answer(text: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    for index in range(0, len(text), 24):
        yield "delta", {"content": text[index:index + 24]}


def persist_answer(assistant_id: int, status: str, content: str, citations: list[dict[str, Any]],
                   suggestions: list[str], grounded: bool, model_name: str, started: float) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        message = db.get(ChatMessage, assistant_id)
        if message is None:
            return citations
        message.content = content
        message.status = status
        message.is_grounded = grounded
        message.suggestions = suggestions[:3]
        message.model_name = model_name
        message.latency_ms = int((time.perf_counter() - started) * 1000)
        db.query(ChatCitation).filter(ChatCitation.message_id == assistant_id).delete(synchronize_session=False)
        saved = []
        for order, citation in enumerate(dedupe_citations(citations)):
            row = ChatCitation(message_id=assistant_id, source_type=citation["source_type"],
                               document_id=citation.get("document_id"), chunk_id=citation.get("chunk_id"),
                               title=citation["title"], source_url=citation.get("source_url") or None,
                               snippet=citation.get("snippet") or None, page_no=citation.get("page_no"),
                               tool_name=citation.get("tool_name") or None, sort_order=order,
                               retrieved_at=now_local())
            db.add(row)
            db.flush()
            saved.append({**citation, "citation_id": row.id, "sort_order": order})
        session = db.get(ChatSession, message.session_id)
        if session:
            session.last_message_at = now_local()
            total_questions = db.query(ChatMessage).filter(ChatMessage.session_id == session.id,
                                                           ChatMessage.role == "USER").count()
            max_turns = max(1, get_int_config(db, "chat.history_turns", 10))
            # 只有跨过整轮窗口才刷新摘要：旧实现每问一句就覆盖成最近 8 个问题，
            # 既丢失更早上下文，也把“摘要”变成了问题列表。
            if total_questions > max_turns and total_questions % max_turns == 0:
                recent = (db.query(ChatMessage)
                          .filter(ChatMessage.session_id == session.id, ChatMessage.status == "SUCCESS",
                                  ChatMessage.role.in_(["USER", "ASSISTANT"]))
                          .order_by(ChatMessage.id.desc()).limit(max_turns).all())
                lines = [f"{'问' if item.role == 'USER' else '答'}：{(item.content or '')[:80]}"
                         for item in reversed(recent) if item.content]
                if lines:
                    session.context_summary = "；".join(lines)[-1200:]
        db.commit()
        return saved
    finally:
        db.close()


async def run_generation(assistant_id: int, session_id: int, question: str, document_id: int | None,
                         enable_web: bool, enable_db_tool: bool, history: list[dict[str, str]],
                         user_context: dict[str, Any]
                         ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    db = SessionLocal()
    started = time.perf_counter()
    content = ""
    citations: list[dict[str, Any]] = []
    suggestions: list[str] = []
    grounded = False
    model_name = "offline-extractive"
    try:
        top_k = get_int_config(db, "rag.top_k", 5)
        threshold = get_float_config(db, "rag.similarity_threshold", 0.12)
        versions = allowed_versions_for(db, document_id)
        contexts: list[dict[str, Any]] = []
        if not is_web_first_question(question, enable_web):
            try:
                contexts = await ai_client.retrieve(question, versions, top_k, threshold, document_id)
                model_name = "ai-service-rag"
            except Exception:
                contexts = local_retrieve(db, question, versions, top_k, document_id, threshold)
            if not contexts:
                contexts = local_retrieve(db, question, versions, top_k, document_id, threshold)
        fallback_citations = [citation_from_context(db, item) for item in contexts]
        if contexts or enable_web or enable_db_tool:
            payload = {
                "question": question, "contexts": contexts, "history": history,
                "enable_web": enable_web, "enable_db_tool": enable_db_tool,
                "service_channels": get_config(db, "service.channels", ""),
                "user_context": user_context,
            }
            try:
                async for event, data in ai_client.stream_chat(payload):
                    if event == "delta":
                        piece = str(data.get("content", ""))
                        if piece:
                            content += piece
                            yield "delta", {"content": piece}
                    elif event == "citation":
                        incoming = [normalize_citation(item, len(citations))
                                    for item in data.get("citations", []) if isinstance(item, dict)]
                        citations.extend(incoming)
                        if incoming:
                            yield "citation", {"citations": dedupe_citations(citations)}
                    elif event == "suggestion":
                        suggestions.extend(str(item) for item in data.get("suggestions", []) if str(item).strip())
                    elif event == "error":
                        raise AIServiceError(str(data.get("message", "AI回答生成失败")))
                    elif event == "done":
                        guard = data.get("guard") or {}
                        if "is_grounded" in guard:
                            grounded = bool(guard.get("is_grounded"))
            except Exception:
                if content:
                    raise
                if fallback_citations:
                    citations = dedupe_citations(fallback_citations)
                    yield "citation", {"citations": citations}
                content = local_answer(question, contexts)
                model_name = "offline-extractive"
                async for event, data in stream_local_answer(content):
                    yield event, data
        else:
            content = local_answer(question, contexts)
            async for event, data in stream_local_answer(content):
                yield event, data
        if not content.strip():
            content = local_answer(question, contexts)
            async for event, data in stream_local_answer(content):
                yield event, data
        reminder = sensitive_reminder(db, question)
        if reminder:
            content = f"{content}\n\n{reminder}"
            yield "delta", {"content": "\n\n" + reminder}
        grounded = grounded or bool(citations)
        suggestions = list(dict.fromkeys(item for item in suggestions if item.strip()))[:3] or default_suggestions(question)
        yield "suggestion", {"suggestions": suggestions}
        saved = persist_answer(assistant_id, "SUCCESS", content, citations, suggestions,
                               grounded, model_name, started)
        yield "done", {"message_id": assistant_id, "session_id": session_id,
                       "citations": saved, "suggestions": suggestions,
                       "guard": {"is_grounded": grounded,
                       "reason": "" if grounded else "无可用知识依据"}}
    except Exception as exc:
        persist_answer(assistant_id, "FAILED", content, citations, suggestions,
                       grounded, model_name, started)
        yield "error", {"code": 400101, "message": f"AI回答生成失败：{str(exc)[:120]}"}
    finally:
        db.close()


async def sse_stream(generator: AsyncIterator[tuple[str, dict[str, Any]]]) -> AsyncIterator[str]:
    async for event, data in generator:
        yield sse_frame(event, data)


@router.post("/messages")
async def send_message(payload: ChatRequest, user: SysUser = Depends(require_mobile_user),
                       db: Session = Depends(get_db)):
    if payload.session_id:
        session = get_owned_session(db, payload.session_id, user.id)
    else:
        title = payload.question.strip()[:20] or "新的咨询"
        session = ChatSession(user_id=user.id, title=title, last_message_at=now_local())
        db.add(session)
        db.flush()
    if payload.document_id is not None:
        row = (db.query(KnowledgeDocument, KnowledgeCategory)
               .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
               .filter(KnowledgeDocument.id == payload.document_id).first())
        if row is None or not is_document_visible(row[0], row[1]):
            raise ApiError(200104, "当前文档不存在或不可访问", 404)
    max_chars = get_int_config(db, "chat.context_max_chars", 6000)
    max_turns = get_int_config(db, "chat.history_turns", 10)
    enable_web = payload.enable_web and get_bool_config(db, "web.enabled", True)
    history = build_context(db, session, max_chars, max_turns)
    if session.title == "新的咨询":
        session.title = payload.question.strip()[:20] or "新的咨询"
    question = ChatMessage(session_id=session.id, role="USER", content=payload.question.strip(),
                           status="SUCCESS")
    db.add(question)
    db.flush()
    assistant = ChatMessage(session_id=session.id, role="ASSISTANT", reply_to_message_id=question.id,
                            content="", status="FAILED", is_grounded=False)
    db.add(assistant)
    session.last_message_at = now_local()
    db.commit()
    db.refresh(assistant)
    session_id = session.id
    assistant_id = assistant.id
    generator = run_generation(assistant_id, session_id, question.content, payload.document_id,
                               enable_web, payload.enable_db_tool, history,
                               {"user_id": user.id, "role": user.role,
                                "student_no": user.student_no or ""})
    if payload.stream:
        return StreamingResponse(sse_stream(generator), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    content_parts, final_data = [], {}
    async for event, data in generator:
        if event == "delta":
            content_parts.append(str(data.get("content", "")))
        elif event == "done":
            final_data = data
        elif event == "error":
            raise ApiError(int(data.get("code", 400101)), str(data.get("message", "AI回答生成失败")), 502)
    return success({"message_id": assistant_id, "session_id": session_id,
                    "content": "".join(content_parts), "citations": final_data.get("citations", []),
                    "suggestions": final_data.get("suggestions", default_suggestions(payload.question)),
                    "guard": final_data.get("guard", {})})


@router.post("/messages/{message_id}/feedback")
def submit_feedback(message_id: int, payload: FeedbackRequest, user: SysUser = Depends(require_mobile_user),
                    db: Session = Depends(get_db)):
    message = (db.query(ChatMessage).join(ChatSession, ChatSession.id == ChatMessage.session_id)
               .filter(ChatMessage.id == message_id, ChatMessage.role == "ASSISTANT",
                       ChatSession.user_id == user.id, ChatSession.status == "ACTIVE").first())
    if message is None:
        raise ApiError(700102, "消息不存在或无权操作", 404)
    existing = db.query(ChatFeedback).filter(ChatFeedback.message_id == message_id,
                                             ChatFeedback.user_id == user.id).first()
    if existing:
        raise ApiError(700103, "您已对该回答提交过反馈", 409)
    feedback = ChatFeedback(message_id=message_id, user_id=user.id, rating=payload.rating,
                            reason=payload.reason, status="PENDING")
    db.add(feedback)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(700103, "您已对该回答提交过反馈", 409) from exc
    db.refresh(feedback)
    return success({"feedback_id": feedback.id, "message_id": feedback.message_id,
                    "rating": feedback.rating, "reason": feedback.reason or "",
                    "status": feedback.status, "created_at": fmt_dt(feedback.created_at)}, status_code=201)
