from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, IdType, now_local


class Merchant(Base):
    __tablename__ = "merchant"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "category IN ('食堂','超市','水电','网费','打印','洗衣','交通','补助','其他')",
            name="ck_merchant_category",
        ),
        Index("ix_merchant_category_name", "category", "name"),
    )


class CardTxn(Base):
    __tablename__ = "card_txn"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    card_no: Mapped[str] = mapped_column(
        String(64), ForeignKey("campus_card_account.card_no"), nullable=False
    )
    txn_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_local)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    merchant_id: Mapped[int | None] = mapped_column(
        IdType, ForeignKey("merchant.id"), nullable=True
    )
    channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    __table_args__ = (
        CheckConstraint("direction IN ('IN','OUT')", name="ck_card_txn_direction"),
        CheckConstraint("amount >= 0", name="ck_card_txn_amount"),
        Index("ix_card_txn_card_time", "card_no", "txn_time"),
        Index("ix_card_txn_merchant_time", "merchant_id", "txn_time"),
    )


class SubsidyRecord(Base):
    __tablename__ = "subsidy_record"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    card_no: Mapped[str] = mapped_column(
        String(64), ForeignKey("campus_card_account.card_no"), nullable=False
    )
    item: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_subsidy_amount"),
        Index("ix_subsidy_card_date", "card_no", "pay_date"),
    )

