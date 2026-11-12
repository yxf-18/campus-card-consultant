from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .database import SessionLocal, engine, init_db
from .models import ChatMessage, RagSyncTask
from .responses import (ApiError, api_error_handler, fail, unhandled_error_handler,
                        validation_error_handler)
from .routers import admin_categories, admin_documents, admin_ops, auth, card, chat, documents
from .seed import seed_database
from .services import get_int_config, purge_expired_sessions

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.auto_seed:
        seed_database()
    db = SessionLocal()
    try:
        db.query(RagSyncTask).filter(RagSyncTask.status == "RUNNING").update(
            {RagSyncTask.status: "FAILED", RagSyncTask.error_message: "服务重启导致任务中断，可重试"},
            synchronize_session=False)
        stale_answers = db.query(ChatMessage).filter(
            ChatMessage.role == "ASSISTANT",
            ChatMessage.status == "STREAMING",
        ).all()
        for message in stale_answers:
            message.status = "FAILED"
            message.is_grounded = False
            if (message.content or "").strip():
                message.content += "\n\n（上一次回答未完成，请重新提问。）"
            else:
                message.content = "上一次回答未能完成，请重新提问。"
        db.commit()
        # 已删除会话按配置的保留期做物理清理，避免过期问答内容长期滞留。
        purge_expired_sessions(db, get_int_config(db, "chat.session_retention_days", 180))
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "swagger-ui"
if DOCS_DIR.exists():
    app.mount("/swagger-assets", StaticFiles(directory=str(DOCS_DIR)), name="swagger-assets")


@app.get("/", include_in_schema=False)
def root_login_redirect():
    return RedirectResponse(f"{settings.admin_web_url}/login")


@app.get("/docs", include_in_schema=False)
def offline_docs():
    return HTMLResponse('<html><head><meta charset="utf-8"><title>校园一卡通业务 API 文档</title><link rel="stylesheet" href="/swagger-assets/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="/swagger-assets/swagger-ui-bundle.js"></script><script src="/swagger-assets/swagger-ui-standalone-preset.js"></script><script>window.onload=()=>{SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui",deepLinking:true,presets:[SwaggerUIBundle.presets.apis,SwaggerUIStandalonePreset],layout:"StandaloneLayout"})}</script></body></html>')

app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request, exc: StarletteHTTPException):
    return fail(exc.status_code * 1000, str(exc.detail), exc.status_code)


@app.get("/health")
@app.get(f"{settings.api_prefix}/health")
def health():
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception:
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "database": database,
            "service": "backend-api", "version": "1.0.0",
            "auth_scope": "client-type-v1"}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(card.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(admin_categories.router, prefix=settings.api_prefix)
app.include_router(admin_documents.router, prefix=settings.api_prefix)
app.include_router(admin_ops.router, prefix=settings.api_prefix)
app.include_router(admin_ops.internal_router)
