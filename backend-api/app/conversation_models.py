from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, Session

from .card_read_models import CardTxn, Merchant, SubsidyRecord
from .models import Base, CampusCardAccount, IdType, SysUser, now_local
from .security import hash_password


class CardOrder(Base):
    __tablename__ = "card_order"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    card_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False
    )
    __table_args__ = (
        Index("ix_order_card_created", "card_no", "created_at"),
        Index("ix_order_user_type_created", "user_id", "type", "created_at"),
    )


class OrderEvent(Base):
    __tablename__ = "order_event"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(
        String(64), ForeignKey("card_order.order_no"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (Index("ix_order_event_order_time", "order_no", "at"),)


class Office(Base):
    __tablename__ = "office"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(String(250), nullable=False)
    hours: Mapped[str] = mapped_column(String(120), nullable=False)


class AppointmentSlot(Base):
    __tablename__ = "appointment_slot"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    office_id: Mapped[int] = mapped_column(IdType, ForeignKey("office.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    booked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("office_id", "date", "slot", name="uq_slot_office_date_time"),
        Index("ix_slot_office_date", "office_id", "date", "slot"),
    )


class ActionToken(Base):
    __tablename__ = "action_token"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    card_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("sys_user.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        Index("ix_action_token_pending", "user_id", "card_no", "used", "expires_at"),
    )


DEMO_MERCHANTS = [
    ("第一食堂", "食堂"), ("第二食堂", "食堂"), ("校园便利店", "超市"),
    ("水电充值", "水电"), ("宿舍网费", "网费"), ("图书馆打印", "打印"),
    ("洗衣房", "洗衣"), ("校园巴士", "交通"), ("学校补助", "补助"),
    ("其他消费", "其他"),
]


def _ensure_merchants(db: Session) -> dict[str, Merchant]:
    result: dict[str, Merchant] = {}
    for name, category in DEMO_MERCHANTS:
        row = db.query(Merchant).filter(Merchant.name == name).first()
        if row is None:
            row = Merchant(name=name, category=category)
            db.add(row)
            db.flush()
        result[category] = row
    return result


def _month_start(reference: date, offset: int) -> date:
    month_index = reference.year * 12 + reference.month - 1 - offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def seed_conversation_data(db: Session) -> None:
    """Create deterministic mock bills, subsidy records, offices and slots."""
    merchants = _ensure_merchants(db)
    for username in ("student", "student01", "student02"):
        user = db.query(SysUser).filter(SysUser.username == username).first()
        account = (
            db.query(CampusCardAccount)
            .filter(CampusCardAccount.user_id == user.id)
            .first()
            if user
            else None
        )
        if account is None:
            continue
        today = now_local().date()
        subsidy_date = date(today.year, 9, 10)
        exists_subsidy = (
            db.query(SubsidyRecord.id)
            .filter(
                SubsidyRecord.card_no == account.card_no,
                SubsidyRecord.item == "秋季助学补助",
                SubsidyRecord.pay_date == subsidy_date,
            )
            .first()
        )
        if exists_subsidy is None:
            db.add(SubsidyRecord(
                card_no=account.card_no, item="秋季助学补助",
                amount=Decimal("2000.00"), pay_date=subsidy_date,
                source="学校学生资助管理中心",
            ))
            db.add(CardTxn(
                card_no=account.card_no,
                txn_time=datetime.combine(subsidy_date, datetime.min.time()).replace(hour=9),
                amount=Decimal("2000.00"), direction="IN",
                merchant_id=merchants["补助"].id, channel="系统入账",
                balance_after=account.balance,
                summary="秋季助学补助入账",
            ))
        if db.query(CardTxn.id).filter(CardTxn.card_no == account.card_no).first() is not None:
            continue
        rng = random.Random(f"bill:{account.card_no}")
        balance = Decimal("520.00")
        categories = ["食堂", "超市", "水电", "网费", "打印", "洗衣", "交通", "其他"]
        # Months 0, 1, 2 and 4 contain data; month 3 intentionally remains blank.
        for month_offset in (4, 2, 1, 0):
            month_start = _month_start(today, month_offset)
            count = 40 + rng.randrange(21)
            for index in range(count):
                day = 1 + rng.randrange(27)
                hour = 7 + rng.randrange(14)
                minute = rng.randrange(60)
                txn_time = datetime(
                    month_start.year, month_start.month,
                    min(day, 28), hour, minute,
                )
                category = categories[rng.randrange(len(categories))]
                amount = Decimal(f"{2 + rng.randrange(3900) / 100:.2f}")
                balance = max(Decimal("0"), balance - amount)
                db.add(CardTxn(
                    card_no=account.card_no, txn_time=txn_time, amount=amount,
                    direction="OUT", merchant_id=merchants[category].id,
                    channel="校园卡终端", balance_after=balance,
                    summary=f"{merchants[category].name}消费",
                ))
            if month_offset == 2:
                anomaly_time = datetime(month_start.year, month_start.month, min(18, 28), 19, 30)
                db.add(CardTxn(
                    card_no=account.card_no, txn_time=anomaly_time,
                    amount=Decimal("268.00"), direction="OUT",
                    merchant_id=merchants["其他"].id, channel="校园卡终端",
                    balance_after=max(Decimal("0"), balance - Decimal("268.00")),
                    summary="大额异常消费待核查",
                ))
        subsidy_date = (today.replace(day=1) - timedelta(days=63)).replace(day=10)
        db.add(SubsidyRecord(
            card_no=account.card_no, item="秋季助学补助",
            amount=Decimal("2000.00"), pay_date=subsidy_date,
            source="学校学生资助管理中心",
        ))
        db.add(CardTxn(
            card_no=account.card_no,
            txn_time=datetime.combine(subsidy_date, datetime.min.time()).replace(hour=9),
            amount=Decimal("2000.00"), direction="IN",
            merchant_id=merchants["补助"].id, channel="系统入账",
            balance_after=balance + Decimal("2000.00"),
            summary="秋季助学补助入账",
        ))

    lost_user = db.query(SysUser).filter(SysUser.username == "lost_demo").first()
    if lost_user is None:
        lost_user = SysUser(
            username="lost_demo", nickname="挂失演示同学", phone="13800000999",
            student_no="20259999", password_hash=hash_password("Student123"),
            role="USER", status="ACTIVE", privacy_agreed_at=now_local(),
        )
        db.add(lost_user)
        db.flush()
        db.add(CampusCardAccount(
            user_id=lost_user.id, card_no="CARD20259999",
            balance=Decimal("42.00"), status="LOST",
        ))

    offices = [
        ("行政楼校园卡服务大厅", "行政楼一层东侧", "周一至周五 08:30-17:30"),
        ("东区师生服务中心", "东区生活广场一层", "周一至周六 09:00-18:00"),
        ("西区卡务窗口", "西区综合楼二层", "周一至周五 09:00-17:00"),
    ]
    office_rows: list[Office] = []
    for values in offices:
        row = db.query(Office).filter(Office.name == values[0]).first()
        if row is None:
            row = Office(name=values[0], address=values[1], hours=values[2])
            db.add(row)
            db.flush()
        office_rows.append(row)
    today = now_local().date()
    for office in office_rows:
        for offset in range(1, 8):
            appointment_date = today + timedelta(days=offset)
            for slot in ("09:00", "10:30", "14:00", "15:30"):
                exists = (
                    db.query(AppointmentSlot.id)
                    .filter(AppointmentSlot.office_id == office.id,
                            AppointmentSlot.date == appointment_date,
                            AppointmentSlot.slot == slot)
                    .first()
                )
                if exists is None:
                    db.add(AppointmentSlot(
                        office_id=office.id, date=appointment_date, slot=slot,
                        capacity=20, booked=3 if slot == "14:00" else 0,
                    ))
    db.flush()
