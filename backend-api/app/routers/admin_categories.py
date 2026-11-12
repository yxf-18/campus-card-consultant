from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import (
    ChatCitation,
    KnowledgeCategory,
    KnowledgeChunk,
    KnowledgeDocument,
    RagSyncTask,
    SysUser,
)
from ..responses import ApiError, success
from ..schemas import CategoryCreateRequest, CategoryUpdateRequest
from ..services import category_json
from ..utils import pagination

router = APIRouter(prefix="/admin/categories", tags=["后台-分类管理"])


@router.get("")
def list_categories(page: int = 1, page_size: int = 100, _admin: SysUser = Depends(require_admin),
                    db: Session = Depends(get_db)):
    page, page_size = max(1, page), min(100, max(1, page_size))
    query = db.query(KnowledgeCategory)
    total = query.count()
    rows = query.order_by(KnowledgeCategory.sort_order, KnowledgeCategory.id).offset((page - 1) * page_size).limit(page_size).all()
    counts = dict(db.query(KnowledgeDocument.category_id, func.count(KnowledgeDocument.id))
                  .filter(KnowledgeDocument.is_deleted.is_(False)).group_by(KnowledgeDocument.category_id).all())
    return success({"list": [category_json(item, counts.get(item.id, 0)) for item in rows]},
                   pagination(page, page_size, total))


@router.post("")
def create_category(payload: CategoryCreateRequest, _admin: SysUser = Depends(require_admin),
                    db: Session = Depends(get_db)):
    if db.query(KnowledgeCategory).filter(KnowledgeCategory.name == payload.name).first():
        raise ApiError(100105, "分类名称已存在", 409)
    category = KnowledgeCategory(name=payload.name, default_cover_url=payload.icon,
                                 sort_order=payload.sort_order, status=payload.status)
    db.add(category)
    db.commit()
    db.refresh(category)
    return success({"category": category_json(category, 0)}, status_code=201)


@router.put("/{category_id}")
def update_category(category_id: int, payload: CategoryUpdateRequest,
                    _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    category = db.get(KnowledgeCategory, category_id)
    if category is None:
        raise ApiError(200106, "分类不存在", 404)
    duplicate = db.query(KnowledgeCategory).filter(KnowledgeCategory.name == payload.name,
                                                   KnowledgeCategory.id != category_id).first()
    if duplicate:
        raise ApiError(100105, "分类名称已存在", 409)
    category.name = payload.name
    category.default_cover_url = payload.icon
    category.sort_order = payload.sort_order
    category.status = payload.status
    db.commit()
    db.refresh(category)
    return success({"category": category_json(category)})


@router.delete("/{category_id}")
def delete_category(category_id: int, _admin: SysUser = Depends(require_admin), db: Session = Depends(get_db)):
    category = db.get(KnowledgeCategory, category_id)
    if category is None:
        raise ApiError(200106, "分类不存在", 404)
    active_count = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.category_id == category_id,
            KnowledgeDocument.is_deleted.is_(False),
        )
        .count()
    )
    if active_count:
        raise ApiError(100105, "分类下仍有未删除文档，请先迁移或删除文档", 409)

    # Logically deleted documents are no longer visible in the admin count.
    # Purge those archived rows before deleting the category so the foreign key
    # behavior matches the number shown in the UI.
    archived_documents = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.category_id == category_id,
            KnowledgeDocument.is_deleted.is_(True),
        )
        .all()
    )
    document_ids = [document.id for document in archived_documents]
    if document_ids:
        chunk_ids = [
            row[0]
            for row in db.query(KnowledgeChunk.id)
            .filter(KnowledgeChunk.document_id.in_(document_ids))
            .all()
        ]
        if chunk_ids:
            db.query(ChatCitation).filter(ChatCitation.chunk_id.in_(chunk_ids)).update(
                {ChatCitation.chunk_id: None}, synchronize_session=False
            )
        db.query(ChatCitation).filter(ChatCitation.document_id.in_(document_ids)).update(
            {ChatCitation.document_id: None}, synchronize_session=False
        )
        db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id.in_(document_ids)).delete(
            synchronize_session=False
        )
        db.query(RagSyncTask).filter(RagSyncTask.document_id.in_(document_ids)).delete(
            synchronize_session=False
        )
        db.query(KnowledgeDocument).filter(KnowledgeDocument.id.in_(document_ids)).delete(
            synchronize_session=False
        )
    db.delete(category)
    db.commit()
    return success({"result": True})
