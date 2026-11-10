from __future__ import annotations

from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import KnowledgeCategory, KnowledgeDocument, SysUser
from ..responses import ApiError, success
from ..security import decode_download_token
from ..services import (document_json, get_int_config, is_document_visible,
                        make_download_url, visible_documents_query)
from ..utils import fmt_dt, pagination

router = APIRouter(tags=["首页与文档"])
settings = get_settings()


@router.get("/home/categories")
def home_categories(category_id: int | None = None, limit: int | None = Query(default=None, ge=1, le=20),
                    with_empty: bool = False, _user: SysUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    limit = limit or get_int_config(db, "home.documents_limit", 5)
    categories = db.query(KnowledgeCategory).filter(KnowledgeCategory.status == "ENABLED")
    if category_id is not None:
        categories = categories.filter(KnowledgeCategory.id == category_id)
    categories = categories.order_by(KnowledgeCategory.sort_order, KnowledgeCategory.id).all()
    result = []
    for category in categories:
        docs = (visible_documents_query(db).filter(KnowledgeDocument.category_id == category.id)
                .order_by(KnowledgeDocument.sort_order, KnowledgeDocument.published_at.desc()).limit(limit).all())
        if not docs and not with_empty:
            continue
        result.append({"category_id": category.id, "name": category.name,
                       "icon": category.default_cover_url or "", "sort_order": category.sort_order,
                       "documents": [
                           {"document_id": doc.id, "title": doc.title, "summary": (doc.summary or "")[:120],
                            "cover_url": doc.cover_url or "", "category_id": doc.category_id,
                            "publish_at": fmt_dt(doc.published_at), "view_count": doc.view_count,
                            "allow_download": doc.allow_download} for doc, _cat in docs]})
    return success({"categories": result})


@router.get("/documents")
def search_documents(keyword: str = "", category_id: int | None = None, sort: str = "latest",
                     page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     _user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    query = visible_documents_query(db)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(KnowledgeDocument.title.like(pattern), KnowledgeDocument.summary.like(pattern),
                                 KnowledgeDocument.keywords.like(pattern)))
    if category_id is not None:
        query = query.filter(KnowledgeDocument.category_id == category_id)
    total = query.count()
    if sort == "popular":
        query = query.order_by(KnowledgeDocument.view_count.desc(), KnowledgeDocument.id.desc())
    else:
        query = query.order_by(KnowledgeDocument.published_at.desc(), KnowledgeDocument.id.desc())
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [{**document_json(doc), "category_name": cat.name} for doc, cat in rows]
    return success({"list": items}, pagination(page, page_size, total))


@router.get("/documents/{document_id}")
def get_document(document_id: int, _user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = visible_documents_query(db).filter(KnowledgeDocument.id == document_id).first()
    if row is None:
        raise ApiError(200104, "文档不存在或已下架", 404)
    doc, category = row
    doc.view_count += 1
    ttl = get_int_config(db, "download.url_ttl_seconds", 300)
    db.commit()
    data = document_json(doc)
    data.update({"category_name": category.name, "content": doc.parsed_text or "",
                 "download_url": make_download_url(doc.id, ttl) if doc.allow_download else "",
                 "download_expires_in": ttl})
    return success({"document": data})


@router.get("/documents/{document_id}/download")
def get_download(document_id: int, _user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = visible_documents_query(db).filter(KnowledgeDocument.id == document_id).first()
    if row is None:
        raise ApiError(200104, "文档不存在或已下架", 404)
    doc = row[0]
    if not doc.allow_download:
        raise ApiError(200105, "该文档未开放下载", 403)
    ttl = get_int_config(db, "download.url_ttl_seconds", 300)
    return success({"file_url": make_download_url(document_id, ttl), "file_name": doc.file_name,
                    "expires_in": ttl})


@router.get("/files/download/{token}")
def download_file(token: str, db: Session = Depends(get_db)):
    try:
        object_id = decode_download_token(token, "document")
    except jwt.PyJWTError as exc:
        raise ApiError(200104, "下载地址无效或已过期", 403) from exc
    row = (db.query(KnowledgeDocument, KnowledgeCategory)
           .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
           .filter(KnowledgeDocument.id == int(object_id)).first())
    if row is None:
        raise ApiError(200104, "文档不存在或不可下载", 404)
    doc, category = row
    # 下载令牌可能早于分类停用/文档过期签发，落盘前必须重新校验可见性。
    if not is_document_visible(doc, category) or not doc.allow_download:
        raise ApiError(200104, "文档不存在或不可下载", 404)
    path = (settings.upload_dir / Path(doc.storage_path).name).resolve()
    if not path.exists():
        raise ApiError(200104, "原始文件不存在", 404)
    return FileResponse(path, filename=doc.file_name)


@router.get("/files/exports/{token}")
def download_export(token: str):
    try:
        filename = decode_download_token(token, "export")
    except jwt.PyJWTError as exc:
        raise ApiError(100105, "下载地址无效或已过期", 403) from exc
    path = (settings.export_dir / Path(filename).name).resolve()
    if not path.exists():
        raise ApiError(100105, "导出文件不存在或已过期", 404)
    return FileResponse(path, filename=path.name)
