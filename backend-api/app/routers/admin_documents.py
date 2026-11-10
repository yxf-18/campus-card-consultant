from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import KnowledgeCategory, KnowledgeChunk, KnowledgeDocument, RagSyncTask, SysUser, now_local
from ..responses import ApiError, success
from ..schemas import DocumentStatusRequest
from ..services import document_json, get_int_config, run_sync_task, save_upload, trigger_sync
from ..utils import pagination

router = APIRouter(prefix="/admin/documents", tags=["后台-文档管理"])
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError(100105, "日期格式应为YYYY-MM-DD", 400) from exc


async def read_upload(file: UploadFile, max_mb: int) -> tuple[bytes, str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ApiError(200101, "请上传PDF、DOCX、TXT或MD文件", 400)
    content = await file.read(max_mb * 1024 * 1024 + 1)
    if len(content) > max_mb * 1024 * 1024:
        raise ApiError(200102, f"文件大小不能超过{max_mb}MB", 413)
    return content, file.filename or f"document{suffix}", suffix.lstrip(".").upper()


@router.get("")
def list_documents(keyword: str = "", category_id: int | None = None, status: str | None = None,
                   sync_status: str | None = None, page: int = Query(1, ge=1),
                   page_size: int = Query(20, ge=1, le=100), _admin: SysUser = Depends(require_admin),
                   db: Session = Depends(get_db)):
    query = db.query(KnowledgeDocument, KnowledgeCategory).join(
        KnowledgeCategory, KnowledgeCategory.id == KnowledgeDocument.category_id).filter(
        KnowledgeDocument.is_deleted.is_(False))
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(KnowledgeDocument.title.like(pattern), KnowledgeDocument.summary.like(pattern)))
    if category_id is not None:
        query = query.filter(KnowledgeDocument.category_id == category_id)
    if status:
        query = query.filter(KnowledgeDocument.status == status)
    if sync_status:
        query = query.filter(KnowledgeDocument.sync_status == sync_status)
    total = query.count()
    rows = query.order_by(KnowledgeDocument.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    counts = dict(db.query(KnowledgeChunk.document_id, func.count(KnowledgeChunk.id))
                  .filter(KnowledgeChunk.chunk_status == "ACTIVE").group_by(KnowledgeChunk.document_id).all())
    items = [{**document_json(doc, counts.get(doc.id, 0)), "category_name": cat.name} for doc, cat in rows]
    return success({"list": items}, pagination(page, page_size, total))


@router.get("/{document_id}")
def get_document_detail(document_id: int, _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None or doc.is_deleted:
        raise ApiError(200104, "文档不存在", 404)
    count = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id,
                                             KnowledgeChunk.chunk_status == "ACTIVE").count()
    category = db.get(KnowledgeCategory, doc.category_id)
    data = {**document_json(doc, count), "category_name": category.name if category else "",
            "content": doc.parsed_text or ""}
    return success({"document": data})


@router.post("")
async def create_document(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                          title: str = Form(...), category_id: int = Form(...),
                          summary: str | None = Form(None), keywords: str | None = Form(None),
                          source: str | None = Form(None), document_no: str | None = Form(None),
                          effective_date: str | None = Form(None), expire_date: str | None = Form(None),
                          allow_download: bool = Form(True), sort_order: int = Form(0),
                          status_value: str = Form("DRAFT", alias="status"),
                          admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    category = db.get(KnowledgeCategory, category_id)
    if category is None or category.status != "ENABLED":
        raise ApiError(200106, "分类不存在或已停用", 400)
    if status_value not in {"DRAFT", "PUBLISHED"}:
        raise ApiError(100105, "新建文档状态只能为DRAFT或PUBLISHED", 400)
    max_mb = get_int_config(db, "upload.max_size_mb", 20)
    content, file_name, file_type = await read_upload(file, max_mb)
    path, digest = save_upload(content, file_name)
    doc = KnowledgeDocument(
        category_id=category_id, title=title, summary=summary, keywords=keywords,
        file_name=file_name, storage_path=path.name, file_type=file_type, file_size=len(content),
        file_hash=digest, source_department=source, document_no=document_no,
        effective_date=parse_date(effective_date), expire_date=parse_date(expire_date),
        status=status_value, sync_status="NOT_INDEXED", allow_download=allow_download,
        sort_order=sort_order, published_at=now_local() if status_value == "PUBLISHED" else None,
        created_by=admin.id, updated_by=admin.id)
    if file_type in {"TXT", "MD"}:
        try:
            doc.parsed_text = content.decode("utf-8")
        except UnicodeDecodeError:
            doc.parsed_text = content.decode("gb18030", errors="ignore")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    task_id = None
    if status_value == "PUBLISHED":
        task = trigger_sync(db, doc, "CREATE", admin.id)
        task_id = task.id
        background_tasks.add_task(run_sync_task, task.id)
    return success({"document": document_json(doc, 0), "task_id": task_id}, status_code=201)


@router.put("/{document_id}")
async def update_document(document_id: int, background_tasks: BackgroundTasks,
                          file: UploadFile | None = File(None), title: str | None = Form(None),
                          category_id: int | None = Form(None), summary: str | None = Form(None),
                          keywords: str | None = Form(None), source: str | None = Form(None),
                          document_no: str | None = Form(None), effective_date: str | None = Form(None),
                          expire_date: str | None = Form(None), allow_download: bool | None = Form(None),
                          sort_order: int | None = Form(None),
                          admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None or doc.is_deleted:
        raise ApiError(200104, "文档不存在", 404)
    if title is not None:
        doc.title = title
    if category_id is not None:
        category = db.get(KnowledgeCategory, category_id)
        if category is None or category.status != "ENABLED":
            raise ApiError(200106, "分类不存在或已停用", 400)
        doc.category_id = category_id
    if summary is not None:
        doc.summary = summary
    if keywords is not None:
        doc.keywords = keywords
    if source is not None:
        doc.source_department = source
    if document_no is not None:
        doc.document_no = document_no
    if effective_date is not None:
        doc.effective_date = parse_date(effective_date)
    if expire_date is not None:
        doc.expire_date = parse_date(expire_date)
    if allow_download is not None:
        doc.allow_download = allow_download
    if sort_order is not None:
        doc.sort_order = sort_order
    if file is not None and file.filename:
        max_mb = get_int_config(db, "upload.max_size_mb", 20)
        content, file_name, file_type = await read_upload(file, max_mb)
        path, digest = save_upload(content, file_name)
        doc.file_name, doc.storage_path, doc.file_type = file_name, path.name, file_type
        doc.file_size, doc.file_hash = len(content), digest
        if file_type in {"TXT", "MD"}:
            try:
                doc.parsed_text = content.decode("utf-8")
            except UnicodeDecodeError:
                doc.parsed_text = content.decode("gb18030", errors="ignore")
    doc.updated_by = admin.id
    db.commit()
    db.refresh(doc)
    task_id = None
    if doc.status == "PUBLISHED":
        task = trigger_sync(db, doc, "UPDATE", admin.id)
        task_id = task.id
        background_tasks.add_task(run_sync_task, task.id)
    return success({"document": document_json(doc), "task_id": task_id})


def change_status(doc: KnowledgeDocument, target: str, admin: SysUser, db: Session,
                  background_tasks: BackgroundTasks) -> int | None:
    old = doc.status
    doc.status = target
    doc.updated_by = admin.id
    if target == "PUBLISHED" and not doc.published_at:
        doc.published_at = now_local()
    db.commit()
    task_id = None
    if target == "PUBLISHED" and old != "PUBLISHED":
        task = trigger_sync(db, doc, "UPDATE" if doc.active_index_version else "CREATE", admin.id)
    elif target == "OFFLINE" and old != "OFFLINE":
        task = trigger_sync(db, doc, "OFFLINE", admin.id)
    else:
        task = None
    if task:
        task_id = task.id
        background_tasks.add_task(run_sync_task, task.id)
    return task_id


@router.patch("/{document_id}")
@router.patch("/{document_id}/status")
def update_document_status(document_id: int, payload: DocumentStatusRequest,
                           background_tasks: BackgroundTasks, admin: SysUser = Depends(require_admin),
                           db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None or doc.is_deleted:
        raise ApiError(200104, "文档不存在", 404)
    task_id = change_status(doc, payload.status, admin, db, background_tasks)
    db.refresh(doc)
    return success({"document": document_json(doc), "task_id": task_id})


@router.delete("/{document_id}")
def delete_document(document_id: int, background_tasks: BackgroundTasks,
                    admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None or doc.is_deleted:
        raise ApiError(200104, "文档不存在", 404)
    doc.is_deleted = True
    doc.deleted_at = now_local()
    doc.status = "OFFLINE"
    doc.updated_by = admin.id
    db.commit()
    task = trigger_sync(db, doc, "DELETE", admin.id)
    background_tasks.add_task(run_sync_task, task.id)
    return success({"result": True, "task_id": task.id})
