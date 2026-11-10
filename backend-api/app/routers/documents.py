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
from ..models import KnowledgeCategory, KnowledgeDocument, SysUser, now_local
from ..responses import ApiError, success
from ..security import decode_download_token
from ..services import document_json, make_download_url
from ..utils import fmt_dt, pagination

router = APIRouter(tags=["首页与文档"])
settings = get_settings()


def visible_query(db: Session):
    today = now_local().date()
    return (db.query(KnowledgeDocument, KnowledgeCategory)
            .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id)
            .filter(KnowledgeCategory.status == "ENABLED", KnowledgeDocument.status == "PUBLISHED",
                    KnowledgeDocument.is_deleted.is_(False),
                    or_(KnowledgeDocument.effective_date.is_(None), KnowledgeDocument.effective_date <= today),
                    or_(KnowledgeDocument.expire_date.is_(None), KnowledgeDocument.expire_date >= today)))


@router.get("/home/categories")
def home_categories(category_id: int | None = None, limit: int = Query(default=5, ge=1, le=20),
                    with_empty: bool = False, _user: SysUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    categories = db.query(KnowledgeCategory).filter(KnowledgeCategory.status == "ENABLED")
    if category_id is not None:
        categories = categories.filter(KnowledgeCategory.id == category_id)
    categories = categories.order_by(KnowledgeCategory.sort_order, KnowledgeCategory.id).all()
    result = []
    for category in categories:
        docs = (visible_query(db).filter(KnowledgeDocument.category_id == category.id)
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
    query = visible_query(db)
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
    row = visible_query(db).filter(KnowledgeDocument.id == document_id).first()
    if row is None:
        raise ApiError(200104, "文档不存在或已下架", 404)
    doc, category = row
    doc.view_count += 1
    db.commit()
    data = document_json(doc)
    data.update({"category_name": category.name, "content": doc.parsed_text or "",
                 "download_url": make_download_url(doc.id) if doc.allow_download else ""})
    return success({"document": data})


@router.get("/documents/{document_id}/download")
def get_download(document_id: int, _user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = visible_query(db).filter(KnowledgeDocument.id == document_id).first()
    if row is None:
        raise ApiError(200104, "文档不存在或已下架", 404)
    doc = row[0]
    if not doc.allow_download:
        raise ApiError(200105, "该文档未开放下载", 403)
    return success({"file_url": make_download_url(document_id), "file_name": doc.file_name, "expires_in": 300})


@router.get("/files/download/{token}")
def download_file(token: str, db: Session = Depends(get_db)):
    try:
        object_id = decode_download_token(token, "document")
    except jwt.PyJWTError as exc:
        raise ApiError(200104, "下载地址无效或已过期", 403) from exc
    doc = db.get(KnowledgeDocument, int(object_id))
    today = now_local().date()
    if (doc is None or doc.is_deleted or doc.status != "PUBLISHED" or not doc.allow_download
            or (doc.effective_date and doc.effective_date > today)
            or (doc.expire_date and doc.expire_date < today)):
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
