from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, init_db
from .models import CampusCardAccount, KnowledgeCategory, KnowledgeDocument, SysConfig, SysUser, now_local
from .security import hash_password
from .services import DEFAULT_CONFIGS
from decimal import Decimal

settings = get_settings()

SEED_CATEGORIES = [
    ("使用指南", 10), ("充值补办", 20), ("消费管理", 30), ("优惠政策", 40), ("常见问题", 50),
]
SEED_DOCUMENTS = [
    ("校园卡使用指南.md", "校园卡使用指南", "使用指南", "基础使用与安全提醒"),
    ("充值补办流程说明.md", "充值补办流程说明", "充值补办", "充值、挂失与补办咨询指引"),
    ("消费管理规定.md", "消费管理规定", "消费管理", "校内消费范围与异常处理"),
    ("优惠政策文件.md", "优惠政策说明", "优惠政策", "优惠对象与查询渠道说明"),
    ("常见问题及处理方案汇总.md", "常见问题及处理方案汇总", "常见问题", "校园卡高频问题汇总"),
]


def seed_configs(db: Session) -> None:
    for key, group, value, value_type, description in DEFAULT_CONFIGS:
        row = db.query(SysConfig).filter(SysConfig.config_key == key).first()
        if row is None:
            db.add(SysConfig(config_key=key, config_group=group, config_value=value,
                             value_type=value_type, description=description))


def seed_users(db: Session) -> None:
    admin = db.query(SysUser).filter(SysUser.username == settings.initial_admin_username).first()
    if admin is None:
        db.add(SysUser(
            username=settings.initial_admin_username, nickname="系统管理员",
            password_hash=hash_password(settings.initial_admin_password), role="ADMIN",
            status="ACTIVE", privacy_agreed_at=now_local()))
    elif admin.role == "ADMIN":
        admin.status = "ACTIVE"
    student = db.query(SysUser).filter(SysUser.username == "student").first()
    if student is None:
        db.add(SysUser(username="student", nickname="演示同学", phone="13800000000",
                       student_no="20230001", password_hash=hash_password("Student123"), role="USER",
                       status="ACTIVE", privacy_agreed_at=now_local()))
    else:
        student.phone = student.phone or "13800000000"
        student.student_no = student.student_no or "20230001"
    student01 = db.query(SysUser).filter(SysUser.username == "student01").first()
    if student01 is None:
        db.add(SysUser(username="student01", nickname="演示学生01", phone="13800000001",
                       student_no="01", password_hash=hash_password("Student123"), role="USER",
                       status="ACTIVE", privacy_agreed_at=now_local()))
    else:
        student01.phone = student01.phone or "13800000001"
        student01.student_no = student01.student_no or "01"


def seed_card_accounts(db: Session) -> None:
    demos = [
        ("student", "CARD20230001", Decimal("128.50")),
        ("student01", "CARD00000001", Decimal("66.80")),
    ]
    for username, card_no, balance in demos:
        student = db.query(SysUser).filter(SysUser.username == username).first()
        if student and db.query(CampusCardAccount).filter(CampusCardAccount.user_id == student.id).first() is None:
            db.add(CampusCardAccount(user_id=student.id, card_no=card_no,
                                     balance=balance, status="ACTIVE"))


def seed_knowledge(db: Session) -> None:
    admin = db.query(SysUser).filter(SysUser.role == "ADMIN").order_by(SysUser.id).first()
    if admin is None:
        return
    categories: dict[str, KnowledgeCategory] = {}
    for name, sort_order in SEED_CATEGORIES:
        row = db.query(KnowledgeCategory).filter(KnowledgeCategory.name == name).first()
        if row is None:
            row = KnowledgeCategory(name=name, sort_order=sort_order, status="ENABLED")
            db.add(row)
            db.flush()
        categories[name] = row
    source_dir = settings.data_dir.parent / "seed_docs"
    for file_name, title, category_name, summary in SEED_DOCUMENTS:
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.title == title,
                                                      KnowledgeDocument.is_deleted.is_(False)).first()
        if existing is not None:
            continue
        source = source_dir / file_name
        if not source.exists():
            continue
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        target = settings.upload_dir / f"seed-{digest[:20]}.md"
        target.write_bytes(content)
        db.add(KnowledgeDocument(
            category_id=categories[category_name].id, title=title, summary=summary,
            keywords=f"{category_name},{title}", file_name=file_name, storage_path=target.name,
            parsed_text=content.decode("utf-8"), file_type="MD", file_size=len(content),
            file_hash=digest, source_department="演示资料", status="PUBLISHED",
            sync_status="NOT_INDEXED", allow_download=True, sort_order=0,
            published_at=now_local(), created_by=admin.id, updated_by=admin.id))


def seed_database(db: Session | None = None) -> None:
    own_session = db is None
    db = db or SessionLocal()
    try:
        seed_configs(db)
        seed_users(db)
        db.commit()
        seed_card_accounts(db)
        db.commit()
        seed_knowledge(db)
        db.commit()
    finally:
        if own_session:
            db.close()


def main() -> None:
    init_db()
    seed_database()
    print("Database initialized and demo data seeded.")


if __name__ == "__main__":
    main()
