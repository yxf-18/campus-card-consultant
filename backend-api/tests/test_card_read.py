from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.card_read_models import CardTxn, Merchant, SubsidyRecord
from app.card_read_service import (
    aggregate_transactions,
    compare_periods,
    forecast_balance,
    get_balance,
    list_subsidy_records,
    query_transactions,
    resolve_time_range,
    seed_card_read_data,
)
from app.database import Base
from app.models import CampusCardAccount, SysUser
from app.security import hash_password


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_user(session: Session, username: str = "student", card_no: str = "CARD20230001",
               balance: str = "128.50") -> tuple[SysUser, CampusCardAccount]:
    user = SysUser(
        username=username, nickname="演示用户", student_no=f"S{username}",
        password_hash=hash_password("Student123"), role="USER", status="ACTIVE",
    )
    session.add(user)
    session.flush()
    account = CampusCardAccount(
        user_id=user.id, card_no=card_no, balance=Decimal(balance), status="ACTIVE"
    )
    session.add(account)
    session.commit()
    return user, account


def test_time_range_uses_shanghai_calendar_and_limits_span():
    today = date(2026, 11, 12)
    assert resolve_time_range("this_month", today=today).start_date == date(2026, 11, 1)
    assert resolve_time_range("last_month", today=today).end_date == date(2026, 10, 31)
    assert resolve_time_range("this_week", today=today).start_date == date(2026, 11, 9)
    assert resolve_time_range(
        "custom", "2026-09-10", "2026-09-10", today=today
    ).as_dict()["start_date"] == "2026-09-10"
    with pytest.raises(ValueError):
        resolve_time_range("custom", "2024-01-01", "2026-01-02", today=today)
    with pytest.raises(ValueError):
        resolve_time_range("unknown", today=today)


def test_transactions_are_scoped_to_current_user_and_aggregated(db: Session):
    first, account = _seed_user(db)
    second, _ = _seed_user(db, "other", "CARD-OTHER", "999.00")
    canteen = Merchant(name="第一食堂", category="食堂")
    supermarket = Merchant(name="校园超市", category="超市")
    db.add_all([canteen, supermarket])
    db.flush()
    db.add_all([
        CardTxn(card_no=account.card_no, txn_time=datetime(2026, 11, 1, 12),
                amount=Decimal("20.00"), direction="OUT", merchant_id=canteen.id),
        CardTxn(card_no=account.card_no, txn_time=datetime(2026, 11, 2, 12),
                amount=Decimal("30.00"), direction="OUT", merchant_id=supermarket.id),
        CardTxn(card_no="CARD-OTHER", txn_time=datetime(2026, 11, 2, 12),
                amount=Decimal("5000.00"), direction="OUT", merchant_id=canteen.id),
    ])
    db.commit()
    result = query_transactions(
        db, first.id, "custom", start="2026-11-01", end="2026-11-30",
        direction="OUT", limit=1,
    )
    assert result["ok"] is True
    assert result["data"]["total_count"] == 2
    assert result["data"]["total_amount"] == "50.00"
    assert len(result["data"]["list"]) == 1
    assert result["truncated"] is True
    assert "5000" not in str(result)

    aggregate = aggregate_transactions(
        db, first.id, "custom", "category", "OUT",
        start="2026-11-01", end="2026-11-30",
    )
    assert aggregate["ok"] is True
    assert aggregate["data"]["total_amount"] == "50.00"
    assert aggregate["data"]["list"][0]["label"] == "超市"
    assert aggregate["data"]["list"][0]["percentage"] == "60.00"


def test_compare_subsidy_and_forecast(db: Session):
    user, account = _seed_user(db)
    merchant = Merchant(name="第一食堂", category="食堂")
    db.add(merchant)
    db.flush()
    today = datetime.now()
    db.add_all([
        CardTxn(card_no=account.card_no, txn_time=datetime(today.year, today.month, 1, 12),
                amount=Decimal("40.00"), direction="OUT", merchant_id=merchant.id),
        CardTxn(card_no=account.card_no, txn_time=datetime(today.year, today.month, 2, 12),
                amount=Decimal("60.00"), direction="OUT", merchant_id=merchant.id),
        CardTxn(card_no=account.card_no, txn_time=datetime(today.year, today.month, 3, 9),
                amount=Decimal("200.00"), direction="IN", merchant_id=merchant.id,
                summary="国家助学金入账"),
        SubsidyRecord(card_no=account.card_no, item="国家助学金",
                      amount=Decimal("200.00"), pay_date=today.date(),
                      source="学生资助中心"),
    ])
    db.commit()
    compare = compare_periods(
        db, user.id, "this_month", "last_month", "category", "OUT"
    )
    assert compare["ok"] is True
    assert compare["data"]["current_total"] == "100.00"
    assert compare["data"]["previous_total"] == "0.00"
    assert compare["data"]["change_percent"] is None

    subsidies = list_subsidy_records(db, user.id, "this_month")
    assert subsidies["data"]["total_count"] == 1
    assert subsidies["data"]["list"][0]["item"] == "国家助学金"

    forecast = forecast_balance(db, user.id, days=30)
    assert forecast["ok"] is True
    assert forecast["data"]["average_daily_spend"] == "3.33"
    assert forecast["data"]["days_until_threshold"] is not None
    assert forecast["data"]["threshold_date"]
    assert get_balance(db, user.id)["data"]["card_last4"] == "0001"


def test_seed_is_idempotent_and_contains_blank_month_subsidy_and_anomaly(db: Session):
    _seed_user(db)
    first = seed_card_read_data(db, months=6)
    db.commit()
    assert first["created_transactions"] > 0
    assert db.query(CardTxn).count() == first["created_transactions"]
    assert db.query(SubsidyRecord).count() >= 2
    assert db.query(CardTxn).filter(CardTxn.amount == Decimal("1200.00")).count() == 1
    blank = first["blank_month"]
    assert db.query(CardTxn).filter(
        CardTxn.txn_time >= datetime.fromisoformat(f"{blank}-01"),
        CardTxn.txn_time < datetime.fromisoformat(f"{blank}-28"),
    ).count() == 0
    second = seed_card_read_data(db, months=6)
    db.commit()
    assert second["created_transactions"] == 0
    assert second["skipped_cards"] == 1
