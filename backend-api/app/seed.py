from __future__ import annotations

import hashlib
import os
from decimal import Decimal

from sqlalchemy.orm import Session

from .config import get_settings
from .card_read_service import seed_card_read_data
from .conversation_models import seed_conversation_data
from .database import SessionLocal, init_db
from .models import (CampusCardAccount, ChatFeedback, ChatMessage, ChatSession, KnowledgeCategory,
                     KnowledgeDocument, ProfileChangeRequest, SysConfig, SysUser, now_local)
from .security import hash_password
from .services import DEFAULT_CONFIGS

settings = get_settings()
DEMO_USER_COUNT = max(0, int(os.getenv("SEED_DEMO_USER_COUNT", "120")))

SEED_CATEGORIES = [
    ("使用指南", 10), ("充值补办", 20), ("消费管理", 30), ("优惠政策", 40), ("常见问题", 50),
]
SEED_DOCUMENTS = [
    ("校园卡使用指南.md", "校园卡使用指南", "使用指南", "基础使用与安全提醒"),
    ("充值补办流程说明.md", "充值补办流程说明", "充值补办", "充值、挂失与补办咨询指引"),
    ("消费管理规定.md", "消费管理规定", "消费管理", "校内消费范围与异常处理"),
    ("优惠政策文件.md", "优惠政策说明", "优惠政策", "优惠对象与查询渠道说明"),
    ("常见问题及处理方案汇总.md", "常见问题及处理方案汇总", "常见问题", "校园卡高频问题汇总"),
    ("校园卡校园码使用说明.md", "校园卡校园码使用说明", "使用指南", "校园码出示、失效与安全使用"),
    ("校园卡激活与密码管理.md", "校园卡激活与密码管理", "使用指南", "新卡激活、密码修改与找回"),
    ("线上充值操作指引.md", "线上充值操作指引", "充值补办", "线上充值步骤、到账与异常处理"),
    ("校园卡挂失与解挂说明.md", "校园卡挂失与解挂说明", "充值补办", "挂失、解挂与补办衔接"),
    ("校园卡消费异常核查指引.md", "校园卡消费异常核查指引", "消费管理", "重复扣款、金额异常的核查材料"),
    ("校园卡消费限额与流水说明.md", "校园卡消费限额与流水说明", "消费管理", "消费限额、流水查询与对账"),
    ("学生优惠资格认定说明.md", "学生优惠资格认定说明", "优惠政策", "学生优惠对象与认定材料"),
    ("校园卡优惠活动参与指引.md", "校园卡优惠活动参与指引", "优惠政策", "活动优惠的参与与查询方式"),
    ("校园卡高频问题补充.md", "校园卡高频问题补充", "常见问题", "补卡、退款、异常交易等补充问答"),
    ("毕业离校与卡片注销说明.md", "毕业离校与卡片注销说明", "常见问题", "毕业离校前的余额与卡片处理"),
    ("校园卡办理与领取指引.md", "校园卡办理与领取指引", "使用指南", "新卡办理、领取与首次启用"),
    ("校园卡在图书馆与门禁的使用.md", "校园卡在图书馆与门禁的使用", "使用指南", "借书、门禁与场馆通行规则"),
    ("校园卡余额不足与自动充值说明.md", "校园卡余额不足与自动充值说明", "充值补办", "余额不足时的消费与充值选择"),
    ("校园卡补办进度查询说明.md", "校园卡补办进度查询说明", "充值补办", "补办进度、领取时间与临时卡"),
    ("校园卡消费明细与对账指引.md", "校园卡消费明细与对账指引", "消费管理", "消费明细查看与逐笔对账方法"),
    ("校园卡商户与终端使用说明.md", "校园卡商户与终端使用说明", "消费管理", "商户范围、终端使用与刷卡失败"),
    ("校园卡优惠资格变更说明.md", "校园卡优惠资格变更说明", "优惠政策", "身份变化后的优惠资格调整"),
    ("校园卡临时优惠活动规则.md", "校园卡临时优惠活动规则", "优惠政策", "临时活动的参与、叠加与失效"),
    ("校园卡常见报错与处理.md", "校园卡常见报错与处理", "常见问题", "刷卡失败、余额不同步等报错处理"),
    ("校园卡余额与流水不一致怎么办.md", "校园卡余额与流水不一致怎么办", "常见问题", "余额流水不一致的核查与申诉"),
    ("补助与助学金入账说明.md", "补助与助学金入账说明", "消费管理", "补助、助学金入账识别与核对方式"),
]


def seed_configs(db: Session) -> None:
    # 从旧版本升级时清理已废弃的登录锁定配置，管理后台不再显示相关项。
    db.query(SysConfig).filter(SysConfig.config_key.in_([
        "auth.login_fail_limit", "auth.login_lock_minutes",
    ])).delete(synchronize_session=False)
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
    student02 = db.query(SysUser).filter(SysUser.username == "student02").first()
    if student02 is None:
        db.add(SysUser(username="student02", nickname="演示学生02", phone="13800000002",
                       email="student02@demo.edu.cn", student_no="20230002",
                       password_hash=hash_password("Student123"), role="USER",
                       status="ACTIVE", privacy_agreed_at=now_local()))
    else:
        student02.phone = student02.phone or "13800000002"
        student02.email = student02.email or "student02@demo.edu.cn"
        student02.student_no = student02.student_no or "20230002"
    # 演示用批量用户：共享同一个密码摘要，避免启动时对每个账号做一次昂贵哈希。
    shared_hash: str | None = None
    for index in range(1, DEMO_USER_COUNT + 1):
        username = f"demo{index:04d}"
        if db.query(SysUser.id).filter(SysUser.username == username).first():
            continue
        if shared_hash is None:
            shared_hash = hash_password("Student123")
        user = SysUser(
            username=username, nickname=f"演示学生{index:04d}",
            phone=f"139{index:08d}", student_no=f"2024{index:06d}",
            email=f"demo{index:04d}@demo.edu.cn",
            password_hash=shared_hash, role="USER", status="ACTIVE",
            privacy_agreed_at=now_local())
        db.add(user)
        db.flush()
        db.add(CampusCardAccount(
            user_id=user.id, card_no=f"CARD2024{index:06d}",
            balance=Decimal(f"{(index * 37) % 500 + 10}.50"), status="ACTIVE"))


def seed_card_accounts(db: Session) -> None:
    demos = [
        ("student", "CARD20230001", Decimal("128.50")),
        ("student01", "CARD00000001", Decimal("66.80")),
        ("student02", "CARD20230002", Decimal("88.20")),
    ]
    for username, card_no, balance in demos:
        student = db.query(SysUser).filter(SysUser.username == username).first()
        if student and db.query(CampusCardAccount).filter(CampusCardAccount.user_id == student.id).first() is None:
            db.add(CampusCardAccount(user_id=student.id, card_no=card_no,
                                     balance=balance, status="ACTIVE"))


def seed_profile_requests(db: Session) -> None:
    """给后台审核页准备演示申请：两条待审核 + 一条已通过 + 一条已驳回。"""
    demos = [
        ("demo0002", "phone", "13999990002", "PENDING", None),
        ("demo0004", "email", "demo0004.new@demo.edu.cn", "PENDING", None),
        ("demo0006", "phone", "13911110006", "APPROVED", "管理员审核通过"),
        ("demo0008", "email", "demo0008.old@demo.edu.cn", "REJECTED", "邮箱信息与学校登记不一致"),
    ]
    for username, field_name, new_value, status, remark in demos:
        user = db.query(SysUser).filter(SysUser.username == username).first()
        if user is None:
            continue
        exists = (db.query(ProfileChangeRequest)
                  .filter(ProfileChangeRequest.user_id == user.id,
                          ProfileChangeRequest.field_name == field_name,
                          ProfileChangeRequest.new_value == new_value).first())
        if exists:
            continue
        current = getattr(user, field_name) or ""
        db.add(ProfileChangeRequest(
            user_id=user.id, field_name=field_name, old_value=current, new_value=new_value,
            status=status, remark=remark,
            reviewed_at=now_local() if status != "PENDING" else None))
        if status == "APPROVED" and current != new_value:
            setattr(user, field_name, new_value)


DEMO_SESSION_SAMPLES = [
    ("demo0003", "校园卡丢失后应该怎么补办？",
     "建议先通过学校正式渠道办理挂失，避免卡片被他人使用。挂失后按学校公布的补办流程提交申请，"
     "一般需要本人身份证明和学号信息；新卡领取后，原卡自动失效。补办期间如需在校内消费，"
     "可以向卡务中心咨询临时消费方式。", "LIKE", ""),
    ("demo0005", "校园卡有哪些充值方式？",
     "常见方式是线上充值和线下自助终端充值。线上充值后通常需要到刷卡终端或校园码页面同步余额；"
     "如果长时间没有到账，请保留充值时间与订单号，联系卡务中心核对。", "DISLIKE",
     "希望能写清楚线上充值入口在哪里"),
    ("demo0007", "校园卡消费限额是多少？",
     "单笔和单日限额由学校统一设置，具体数值以学校正式通知为准。如果提示超出限额，"
     "可以分次消费，或先通过校园卡服务中心核实本人账户的限额规则。", "LIKE", ""),
]


def seed_demo_activity(db: Session) -> None:
    """准备演示用的问答会话与反馈，让运营概览、会话记录和反馈处理页开箱即有数据。"""
    for username, question, answer, rating, reason in DEMO_SESSION_SAMPLES:
        user = db.query(SysUser).filter(SysUser.username == username).first()
        if user is None:
            continue
        if db.query(ChatSession).filter(ChatSession.user_id == user.id).first() is not None:
            continue
        session = ChatSession(user_id=user.id, title=question[:20], status="ACTIVE",
                              last_message_at=now_local())
        db.add(session)
        db.flush()
        question_row = ChatMessage(session_id=session.id, role="USER", content=question, status="SUCCESS")
        db.add(question_row)
        db.flush()
        answer_row = ChatMessage(session_id=session.id, role="ASSISTANT", reply_to_message_id=question_row.id,
                                 content=answer, status="SUCCESS", model_name="seed-demo",
                                 is_grounded=True, suggestions=["校园卡挂失后如何解挂？", "补办校园卡需要什么材料？"])
        db.add(answer_row)
        db.flush()
        db.add(ChatFeedback(message_id=answer_row.id, user_id=user.id, rating=rating,
                            reason=reason or None, status="PENDING"))


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
        seed_profile_requests(db)
        db.commit()
        seed_demo_activity(db)
        db.commit()
        seed_knowledge(db)
        db.commit()
        seed_card_read_data(db, months=6)
        db.commit()
        seed_conversation_data(db)
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
