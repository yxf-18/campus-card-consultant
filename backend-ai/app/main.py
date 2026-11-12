from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse

from .config import get_settings
from .documents import chunk_document, parse_document
from .embeddings import embedding_provider
from .providers import (classify_question, core_tool, format_tool_answer, make_suggestions,
                        plan_tool_requests, safe_refusal, small_talk_response,
                        stream_llm, tavily_search, tool_has_evidence)
from .schemas import ChatPayload, RetrieveRequest, SummarizeRequest, UnindexRequest
from .vector_store import vector_store

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", docs_url=None, redoc_url=None)

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "swagger-ui"
if DOCS_DIR.exists():
    app.mount("/swagger-assets", StaticFiles(directory=str(DOCS_DIR)), name="swagger-assets")


@app.get("/docs", include_in_schema=False)
def offline_docs():
    return HTMLResponse('<html><head><meta charset="utf-8"><title>校园一卡通 AI API 文档</title><link rel="stylesheet" href="/swagger-assets/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="/swagger-assets/swagger-ui-bundle.js"></script><script src="/swagger-assets/swagger-ui-standalone-preset.js"></script><script>window.onload=()=>{SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui",deepLinking:true,presets:[SwaggerUIBundle.presets.apis,SwaggerUIStandalonePreset],layout:"StandaloneLayout"})}</script></body></html>')



def require_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_token):
        raise HTTPException(status_code=403, detail="内部接口授权失败")


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
def health():
    return {"status": "ok", "service": "backend-ai", "version": "1.0.0",
            "routing": "intent-v2",
            "vector_backend": vector_store.__class__.__name__,
            "embedding_provider": settings.embedding_provider}


@app.post("/internal/v1/index", dependencies=[Depends(require_token)])
async def index_document(document_id: int = Form(...), version_no: int = Form(...),
                         title: str = Form(...), category: str = Form(""),
                         file: UploadFile = File(...)):
    suffix = Path(file.filename or "document.txt").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    temp_path = settings.data_dir / f"upload-{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    temp_path.write_bytes(content)
    try:
        parsed = parse_document(temp_path, suffix)
        if not parsed.text.strip():
            raise HTTPException(status_code=422, detail="文档未解析出有效文本")
        chunks = chunk_document(parsed.pages)
        if not chunks:
            raise HTTPException(status_code=422, detail="文档未生成有效切片")
        vectors = await embedding_provider.embed([item["content"] for item in chunks])
        indexed = vector_store.index(document_id, version_no, title, category, chunks, vectors,
                                     settings.embedding_model or settings.embedding_provider)
        by_index = {item["chunk_index"]: item["vector_id"] for item in indexed}
        result_chunks = [{**item, "vector_id": by_index[item["chunk_index"]],
                          "embedding_model": settings.embedding_model or settings.embedding_provider}
                         for item in chunks]
        return {"document_id": document_id, "version_no": version_no,
                "chunk_count": len(result_chunks), "chunks": result_chunks,
                "parsed_text": parsed.text}
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/internal/v1/unindex", dependencies=[Depends(require_token)])
def unindex_document(payload: UnindexRequest):
    vector_store.unindex(payload.document_id)
    return {"document_id": payload.document_id, "result": True}


@app.post("/internal/v1/retrieve", dependencies=[Depends(require_token)])
async def retrieve(payload: RetrieveRequest):
    allowed = {item.document_id: item.version_no for item in payload.allowed_versions}
    if not allowed:
        return {"contexts": []}
    vector = await embedding_provider.embed_one(payload.question)
    contexts = vector_store.retrieve(vector, allowed, payload.top_k, payload.threshold, payload.document_id)
    return {"contexts": contexts}


@app.post("/internal/v1/summarize", dependencies=[Depends(require_token)])
def summarize(payload: SummarizeRequest):
    parts = []
    if payload.previous_summary:
        parts.append(payload.previous_summary[:500])
    for message in payload.messages[-10:]:
        content = str(message.get("content", "")).strip()
        if content:
            parts.append(content[:180])
    return {"summary": "；".join(parts)[:1200]}


async def chat_events(payload: ChatPayload):
    small_talk = small_talk_response(payload.question)
    if small_talk:
        for index in range(0, len(small_talk), 20):
            yield "delta", {"content": small_talk[index:index + 20]}
        suggestions = make_suggestions(payload.question, [])
        yield "suggestion", {"suggestions": suggestions}
        yield "done", {
            "citations": [],
            "suggestions": suggestions,
            "guard": {"is_grounded": False, "reason": "日常问候"},
            "sources_used": {"knowledge": False, "database": False, "web": False},
        }
        return

    refusal = safe_refusal(payload.question)
    if refusal:
        for index in range(0, len(refusal), 20):
            yield "delta", {"content": refusal[index:index + 20]}
        suggestions = make_suggestions(payload.question, [])
        yield "suggestion", {"suggestions": suggestions}
        yield "done", {"citations": [], "suggestions": suggestions,
                       "guard": {"is_grounded": False, "reason": "账户操作仅提供办理指引"}}
        return

    route = classify_question(payload.question, payload.history, payload.user_context)
    selected_contexts = payload.contexts if route["use_knowledge"] else []
    tool_result: dict[str, Any] | None = None
    web_results: list[dict[str, Any]] = []

    if route["use_database"] and payload.enable_db_tool:
        calls = plan_tool_requests(payload.question, payload.history, payload.user_context)
        operation_results: list[dict[str, Any]] = []
        for call in calls:
            result = await core_tool(payload.question, payload.user_context,
                                     call["tool_name"], call.get("params", {}))
            if result is not None:
                operation_results.append(result)
        if len(operation_results) == 1:
            tool_result = operation_results[0]
        elif operation_results:
            tool_result = {
                "tool_name": "conversation",
                "result": {"ok": True, "data": {"operations": operation_results}},
            }

    # 越权查询他人余额时直接说明隐私规则，不继续检索网页或知识库，避免把无关信息拼进回答。
    if tool_result and isinstance(tool_result.get("result"), dict) and tool_result["result"].get("denied"):
        text = str(tool_result["result"].get("message") or
                   "为了保护账户隐私，只能查询本人的校园卡余额。")
        for index in range(0, len(text), 20):
            yield "delta", {"content": text[index:index + 20]}
        suggestions = make_suggestions(payload.question, [])
        yield "suggestion", {"suggestions": suggestions}
        yield "done", {"citations": [], "suggestions": suggestions,
                       "guard": {"is_grounded": False, "reason": "隐私保护"}}
        return

    local_evidence = bool(selected_contexts) or tool_has_evidence(tool_result)
    if payload.enable_web and (route["explicit_web"] or not local_evidence):
        web_results = await tavily_search(payload.question)

    citations: list[dict[str, Any]] = []
    for context in selected_contexts[:5]:
        citations.append({"source_type": "DOCUMENT", "document_id": context.get("document_id"),
                          "chunk_id": None, "title": context.get("title") or "知识库文档",
                          "source_url": "", "snippet": context.get("snippet") or "",
                          "page_no": context.get("page_no")})
    if tool_has_evidence(tool_result):
        citations.append({"source_type": "TOOL", "document_id": None, "chunk_id": None,
                          "title": "本地数据库查询", "source_url": "",
                          "snippet": json.dumps(tool_result.get("result"), ensure_ascii=False)[:500],
                          "page_no": None, "tool_name": tool_result.get("tool_name")})
    for item in web_results:
        citations.append({"source_type": "WEB", "document_id": None, "chunk_id": None,
                          "title": item.get("title") or "网页资料", "source_url": item.get("url") or "",
                         "snippet": item.get("snippet") or "", "page_no": None,
                         "published": item.get("published") or "",
                         "retrieved": item.get("retrieved_at") or ""})
    if citations:
        yield "citation", {"citations": citations}

    if not selected_contexts and not web_results and not tool_has_evidence(tool_result):
        text = ("暂未在本地知识库或业务数据库中找到足够依据。请补充问题，或联系校园卡服务中心等学校正式渠道核实；"
                "本工具不会编造政策、金额或办理时限。")
        for index in range(0, len(text), 20):
            yield "delta", {"content": text[index:index + 20]}
        grounded = False
    else:
        direct_answer = format_tool_answer(tool_result, selected_contexts, payload.question)
        if direct_answer and not web_results:
            for index in range(0, len(direct_answer), 20):
                yield "delta", {"content": direct_answer[index:index + 20]}
        else:
            async for piece in stream_llm(payload.question, selected_contexts, payload.history,
                                          web_results, tool_result):
                if piece:
                    yield "delta", {"content": piece}
        grounded = bool(citations)

    suggestions = make_suggestions(payload.question, selected_contexts)
    yield "suggestion", {"suggestions": suggestions}
    yield "done", {"citations": citations, "suggestions": suggestions,
                   "guard": {"is_grounded": grounded,
                             "reason": "" if grounded else "无可用知识依据"},
                   "sources_used": {"knowledge": route["use_knowledge"],
                                    "database": route["use_database"],
                                    "web": bool(web_results)}}


@app.post("/internal/v1/chat/stream", dependencies=[Depends(require_token)])
async def chat_stream(payload: ChatPayload):
    async def stream():
        try:
            async for event, data in chat_events(payload):
                yield sse(event, data)
        except Exception as exc:
            yield sse("error", {"code": 400101, "message": f"AI服务处理失败：{str(exc)[:120]}"})
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
