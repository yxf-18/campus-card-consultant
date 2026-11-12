from __future__ import annotations

import calendar
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .card_read_models import CardTxn, Merchant, SubsidyRecord
from .models import CampusCardAccount, now_local

MONEY = Decimal("0.01")
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_RANGE_DAYS = 366
RANGE_TYPES = {
    "today", "this_week", "this_month", "last_month", "since_term_start", "custom"
}
GROUP_BY_TYPES = {"day", "week", "month", "category", "merchant"}
DEFAULT_MERCHANTS = (
    ("第一食堂", "食堂"),
    ("第二食堂", "食堂"),
    ("校园超市", "超市"),
    ("学生公寓水电", "水电"),
    ("校园网络服务", "网费"),
    ("图文打印中心", "打印"),
    ("自助洗衣房", "洗衣"),
    ("校车服务", "交通"),
    ("学校财务处", "补助"),
    ("校园卡服务中心", "其他"),
)


@dataclass(frozen=True)
class TimeRange:
    start_date: date
    end_date: date
    range_type: str

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.start_date, time.min)

    @property
    def end_exclusive(self) -> datetime:
        return datetime.combine(self.end_date + timedelta(days=1), time.min)

    def as_dict(self) -> dict[str, str]:
        return {
            "range_type": self.range_type,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }


def _money(value: Any) -> str:
    return str((Decimal(value or 0)).quantize(MONEY))


def _ok(data: Any, *, truncated: bool | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True, "data": data}
    if truncated is not None:
        result["truncated"] = bool(truncated)
    return result


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error_code": code, "message": message}


def _parse_date(value: date | datetime | str | None, field: str) -> date:
    if value is None:
        raise ValueError(f"{field}不能为空")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field}必须为 YYYY-MM-DD 格式") from exc


def resolve_time_range(
    range_type: str = "this_month",
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    *,
    today: date | None = None,
) -> TimeRange:
    """Resolve a model-supplied enum into concrete Asia/Shanghai calendar dates."""
    today = today or now_local().date()
    normalized = (range_type or "this_month").strip().lower()
    if normalized not in RANGE_TYPES:
        raise ValueError("时间范围仅支持 today/this_week/this_month/last_month/since_term_start/custom")
    if normalized == "today":
        result = TimeRange(today, today, normalized)
    elif normalized == "this_week":
        result = TimeRange(today - timedelta(days=today.weekday()), today, normalized)
    elif normalized == "this_month":
        result = TimeRange(today.replace(day=1), today, normalized)
    elif normalized == "last_month":
        last_day = today.replace(day=1) - timedelta(days=1)
        result = TimeRange(last_day.replace(day=1), last_day, normalized)
    elif normalized == "since_term_start":
        if today.month >= 8:
            term_start = date(today.year, 9, 1)
        elif today.month == 1:
            term_start = date(today.year - 1, 9, 1)
        else:
            term_start = date(today.year, 2, 17)
        result = TimeRange(term_start, today, normalized)
    else:
        result = TimeRange(
            _parse_date(start, "开始日期"), _parse_date(end, "结束日期"), normalized
        )
    if result.start_date > result.end_date:
        raise ValueError("开始日期不得晚于结束日期")
    if (result.end_date - result.start_date).days > MAX_RANGE_DAYS:
        raise ValueError("查询跨度不能超过一年")
    return result


def _account(db: Session, user_id: int | str | None) -> CampusCardAccount | None:
    try:
        parsed_user_id = int(user_id or 0)
    except (TypeError, ValueError):
        return None
    if parsed_user_id <= 0:
        return None
    return db.query(CampusCardAccount).filter(CampusCardAccount.user_id == parsed_user_id).first()


def get_balance(db: Session, user_id: int | str | None) -> dict[str, Any]:
    account = _account(db, user_id)
    if account is None:
        return _error("ACCOUNT_NOT_FOUND", "未找到本人的校园卡账户")
    return _ok({
        "balance": _money(account.balance),
        "status": account.status,
        "last_transaction_at": account.last_transaction_at.isoformat(
            sep=" ", timespec="seconds"
        ) if account.last_transaction_at else "",
        "card_last4": account.card_no[-4:],
    })


def _transaction_query(
    db: Session,
    card_no: str,
    range_value: TimeRange,
    *,
    category: str | None = None,
    merchant: str | None = None,
    direction: str | None = None,
    min_amount: Decimal | float | int | str | None = None,
    max_amount: Decimal | float | int | str | None = None,
):
    query = (
        db.query(CardTxn, Merchant)
        .outerjoin(Merchant, Merchant.id == CardTxn.merchant_id)
        .filter(
            CardTxn.card_no == card_no,
            CardTxn.txn_time >= range_value.start_at,
            CardTxn.txn_time < range_value.end_exclusive,
        )
    )
    if category:
        query = query.filter(Merchant.category == category.strip())
    if merchant:
        query = query.filter(Merchant.name.like(f"%{merchant.strip()}%"))
    if direction:
        normalized = direction.strip().upper()
        if normalized not in {"IN", "OUT"}:
            raise ValueError("收支方向仅支持 IN 或 OUT")
        query = query.filter(CardTxn.direction == normalized)
    try:
        min_value = Decimal(str(min_amount)) if min_amount not in (None, "") else None
        max_value = Decimal(str(max_amount)) if max_amount not in (None, "") else None
    except Exception as exc:
        raise ValueError("金额区间必须为数字") from exc
    if min_value is not None and min_value < 0:
        raise ValueError("最小金额不能为负数")
    if max_value is not None and max_value < 0:
        raise ValueError("最大金额不能为负数")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("最小金额不能大于最大金额")
    if min_value is not None:
        query = query.filter(CardTxn.amount >= min_value)
    if max_value is not None:
        query = query.filter(CardTxn.amount <= max_value)
    return query


def _txn_json(txn: CardTxn, merchant: Merchant | None) -> dict[str, Any]:
    return {
        "id": txn.id,
        "txn_time": txn.txn_time.isoformat(sep=" ", timespec="seconds"),
        "amount": _money(txn.amount),
        "direction": txn.direction,
        "category": merchant.category if merchant else "其他",
        "merchant": merchant.name if merchant else "未知商户",
        "channel": txn.channel or "",
        "balance_after": _money(txn.balance_after) if txn.balance_after is not None else "",
        "summary": txn.summary or "",
    }


def query_transactions(
    db: Session,
    user_id: int | str | None,
    range_type: str = "this_month",
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    category: str | None = None,
    merchant: str | None = None,
    direction: str | None = None,
    min_amount: Decimal | float | int | str | None = None,
    max_amount: Decimal | float | int | str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    account = _account(db, user_id)
    if account is None:
        return _error("ACCOUNT_NOT_FOUND", "未找到本人的校园卡账户")
    try:
        range_value = resolve_time_range(range_type, start, end)
        query = _transaction_query(
            db, account.card_no, range_value, category=category, merchant=merchant,
            direction=direction, min_amount=min_amount, max_amount=max_amount,
        )
        rows = query.order_by(CardTxn.txn_time.desc(), CardTxn.id.desc()).all()
    except ValueError as exc:
        return _error("INVALID_ARGUMENT", str(exc))
    try:
        limit_value = max(1, min(MAX_LIMIT, int(limit)))
        offset_value = max(0, int(offset))
    except (TypeError, ValueError):
        return _error("INVALID_ARGUMENT", "分页参数必须为整数")
    total_count = len(rows)
    total_amount = sum(
        (Decimal(txn.amount) for txn, _merchant in rows), Decimal("0")
    )
    selected = rows[offset_value:offset_value + limit_value]
    return _ok({
        "range": range_value.as_dict(),
        "list": [_txn_json(txn, merchant_row) for txn, merchant_row in selected],
        "total_count": total_count,
        "total_amount": _money(total_amount),
        "returned_count": len(selected),
        "offset": offset_value,
        "limit": limit_value,
    }, truncated=offset_value + len(selected) < total_count)


def _bucket(txn_time: datetime, group_by: str) -> str:
    if group_by == "day":
        return txn_time.date().isoformat()
    if group_by == "week":
        monday = txn_time.date() - timedelta(days=txn_time.date().weekday())
        return monday.isoformat()
    if group_by == "month":
        return txn_time.strftime("%Y-%m")
    raise ValueError("未知分组方式")


def aggregate_transactions(
    db: Session,
    user_id: int | str | None,
    range_type: str = "this_month",
    group_by: str = "category",
    direction: str | None = "OUT",
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
) -> dict[str, Any]:
    account = _account(db, user_id)
    if account is None:
        return _error("ACCOUNT_NOT_FOUND", "未找到本人的校园卡账户")
    normalized_group = (group_by or "category").strip().lower()
    if normalized_group not in GROUP_BY_TYPES:
        return _error("INVALID_ARGUMENT", "分组仅支持 day/week/month/category/merchant")
    try:
        range_value = resolve_time_range(range_type, start, end)
        rows = _transaction_query(
            db, account.card_no, range_value, direction=direction
        ).all()
    except ValueError as exc:
        return _error("INVALID_ARGUMENT", str(exc))
    buckets: dict[str, dict[str, Any]] = {}
    for txn, merchant in rows:
        if normalized_group in {"day", "week", "month"}:
            key = _bucket(txn.txn_time, normalized_group)
            label = key
        elif normalized_group == "category":
            key = merchant.category if merchant else "其他"
            label = key
        else:
            key = str(merchant.id) if merchant else "unknown"
            label = merchant.name if merchant else "未知商户"
        bucket = buckets.setdefault(key, {"key": key, "label": label, "amount": Decimal("0"),
                                           "count": 0})
        bucket["amount"] += Decimal(txn.amount)
        bucket["count"] += 1
    total_amount = sum((item["amount"] for item in buckets.values()), Decimal("0"))
    items = []
    for item in buckets.values():
        percentage = (item["amount"] / total_amount * 100) if total_amount else Decimal("0")
        items.append({
            **item,
            "amount": _money(item["amount"]),
            "percentage": str(percentage.quantize(MONEY)),
        })
    items.sort(key=lambda item: (-Decimal(item["amount"]), -item["count"], item["label"]))
    return _ok({
        "range": range_value.as_dict(),
        "group_by": normalized_group,
        "direction": (direction or "").upper() or None,
        "total_amount": _money(total_amount),
        "total_count": len(rows),
        "list": items,
    })


def compare_periods(
    db: Session,
    user_id: int | str | None,
    range_a: str = "this_month",
    range_b: str = "last_month",
    group_by: str = "category",
    direction: str | None = "OUT",
    *,
    start_a: date | datetime | str | None = None,
    end_a: date | datetime | str | None = None,
    start_b: date | datetime | str | None = None,
    end_b: date | datetime | str | None = None,
) -> dict[str, Any]:
    first = aggregate_transactions(
        db, user_id, range_a, group_by, direction,
        start=start_a, end=end_a,
    )
    second = aggregate_transactions(
        db, user_id, range_b, group_by, direction,
        start=start_b, end=end_b,
    )
    if not first.get("ok"):
        return first
    if not second.get("ok"):
        return second
    first_data, second_data = first["data"], second["data"]
    first_items = {item["key"]: item for item in first_data["list"]}
    second_items = {item["key"]: item for item in second_data["list"]}
    contributions = []
    for key in set(first_items) | set(second_items):
        current = Decimal(first_items.get(key, {}).get("amount", "0"))
        previous = Decimal(second_items.get(key, {}).get("amount", "0"))
        difference = current - previous
        contributions.append({
            "key": key,
            "label": first_items.get(key, second_items.get(key, {})).get("label", key),
            "current_amount": _money(current),
            "previous_amount": _money(previous),
            "difference": _money(difference),
        })
    contributions.sort(key=lambda item: abs(Decimal(item["difference"])), reverse=True)
    current_total = Decimal(first_data["total_amount"])
    previous_total = Decimal(second_data["total_amount"])
    difference = current_total - previous_total
    percentage = (
        str((difference / previous_total * 100).quantize(MONEY))
        if previous_total else None
    )
    return _ok({
        "range_a": first_data["range"],
        "range_b": second_data["range"],
        "group_by": group_by,
        "direction": (direction or "").upper() or None,
        "current_total": _money(current_total),
        "previous_total": _money(previous_total),
        "difference": _money(difference),
        "change_percent": percentage,
        "top_contributors": contributions[:3],
    })


def list_subsidy_records(
    db: Session,
    user_id: int | str | None,
    range_type: str = "since_term_start",
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
) -> dict[str, Any]:
    account = _account(db, user_id)
    if account is None:
        return _error("ACCOUNT_NOT_FOUND", "未找到本人的校园卡账户")
    try:
        range_value = resolve_time_range(range_type, start, end)
    except ValueError as exc:
        return _error("INVALID_ARGUMENT", str(exc))
    rows = (
        db.query(SubsidyRecord)
        .filter(
            SubsidyRecord.card_no == account.card_no,
            SubsidyRecord.pay_date >= range_value.start_date,
            SubsidyRecord.pay_date <= range_value.end_date,
        )
        .order_by(SubsidyRecord.pay_date.desc(), SubsidyRecord.id.desc())
        .all()
    )
    total = sum((Decimal(item.amount) for item in rows), Decimal("0"))
    return _ok({
        "range": range_value.as_dict(),
        "list": [{
            "id": item.id,
            "item": item.item,
            "amount": _money(item.amount),
            "pay_date": item.pay_date.isoformat(),
            "source": item.source or "",
        } for item in rows],
        "total_count": len(rows),
        "total_amount": _money(total),
    })


def forecast_balance(
    db: Session,
    user_id: int | str | None,
    days: int = 30,
    threshold: Decimal | float | int | str = 20,
) -> dict[str, Any]:
    account = _account(db, user_id)
    if account is None:
        return _error("ACCOUNT_NOT_FOUND", "未找到本人的校园卡账户")
    try:
        history_days = max(1, min(365, int(days)))
        threshold_value = max(Decimal("0"), Decimal(str(threshold)))
    except (TypeError, ValueError):
        return _error("INVALID_ARGUMENT", "预测天数和余额阈值必须为数字")
    today = now_local().date()
    start_at = datetime.combine(today - timedelta(days=history_days - 1), time.min)
    rows = (
        db.query(CardTxn.amount)
        .filter(
            CardTxn.card_no == account.card_no,
            CardTxn.direction == "OUT",
            CardTxn.txn_time >= start_at,
            CardTxn.txn_time < datetime.combine(today + timedelta(days=1), time.min),
        )
        .all()
    )
    spend = sum((Decimal(row[0]) for row in rows), Decimal("0"))
    average_daily = spend / Decimal(history_days)
    balance = Decimal(account.balance or 0)
    if average_daily > 0 and balance > threshold_value:
        days_to_threshold = math.floor((balance - threshold_value) / average_daily)
    elif average_daily > 0:
        days_to_threshold = 0
    else:
        days_to_threshold = None
    threshold_date = (
        today + timedelta(days=days_to_threshold)
        if days_to_threshold is not None else None
    )
    target_balance = average_daily * Decimal(30) + threshold_value
    recommended = max(Decimal("0"), target_balance - balance)
    recommended = recommended.quantize(Decimal("1"), rounding=ROUND_CEILING)
    return _ok({
        "balance": _money(balance),
        "history_days": history_days,
        "total_spend": _money(spend),
        "average_daily_spend": _money(average_daily),
        "threshold": _money(threshold_value),
        "days_until_threshold": days_to_threshold,
        "threshold_date": threshold_date.isoformat() if threshold_date else None,
        "recommended_recharge": str(recommended.quantize(MONEY)),
        "sufficient_for_30_days": (
            days_to_threshold is None or days_to_threshold >= 30
        ),
    })


def seed_card_read_data(
    db: Session,
    usernames: Iterable[str] | None = None,
    *,
    months: int = 6,
    commit: bool = False,
) -> dict[str, Any]:
    """Create deterministic banking-card history; reruns skip cards already seeded."""
    months = max(3, min(6, int(months)))
    for name, category in DEFAULT_MERCHANTS:
        if db.query(Merchant.id).filter(Merchant.name == name).first() is None:
            db.add(Merchant(name=name, category=category))
    db.flush()
    merchant_rows = db.query(Merchant).all()
    by_category: dict[str, list[Merchant]] = {}
    for merchant in merchant_rows:
        by_category.setdefault(merchant.category, []).append(merchant)
    query = db.query(CampusCardAccount)
    if usernames is not None:
        from .models import SysUser
        names = list(usernames)
        query = query.join(SysUser, SysUser.id == CampusCardAccount.user_id).filter(
            SysUser.username.in_(names)
        )
    accounts = query.order_by(CampusCardAccount.id).all()
    today = now_local().date()
    month_cursor = date(today.year, today.month, 1)
    generated_months: list[date] = []
    for _ in range(months):
        generated_months.append(month_cursor)
        month_cursor = (
            date(month_cursor.year - 1, 12, 1)
            if month_cursor.month == 1
            else date(month_cursor.year, month_cursor.month - 1, 1)
        )
    blank_month = generated_months[min(2, len(generated_months) - 1)]
    created = 0
    skipped = 0
    for account in accounts:
        if db.query(CardTxn.id).filter(CardTxn.card_no == account.card_no).first():
            skipped += 1
            continue
        rng = random.Random(f"card-history:{account.card_no}")
        records: list[CardTxn] = []
        latest_time: datetime | None = None
        for month_start in reversed(generated_months):
            if month_start == blank_month:
                continue
            last_day = calendar.monthrange(month_start.year, month_start.month)[1]
            month_end = date(month_start.year, month_start.month, last_day)
            effective_end = min(month_end, today)
            if effective_end < month_start:
                continue
            txn_count = rng.randint(40, 80)
            category_names = [name for name, _ in DEFAULT_MERCHANTS if name != "学校财务处"]
            for index in range(txn_count):
                day_offset = rng.randint(0, max(0, (effective_end - month_start).days))
                txn_date = month_start + timedelta(days=day_offset)
                txn_time = datetime.combine(txn_date, time(
                    rng.randint(7, 21), rng.randint(0, 59), rng.randint(0, 59)
                ))
                category = rng.choice([
                    "食堂", "食堂", "食堂", "超市", "超市", "水电", "网费",
                    "打印", "洗衣", "交通", "其他",
                ])
                merchant = rng.choice(by_category[category])
                if category == "食堂":
                    amount = Decimal(rng.randint(4, 28)) + Decimal(rng.choice(["0.00", "0.50"]))
                else:
                    amount = Decimal(rng.randint(2, 90)) + Decimal(rng.choice(["0.00", "0.50"]))
                records.append(CardTxn(
                    card_no=account.card_no, txn_time=txn_time, amount=amount,
                    direction="OUT", merchant_id=merchant.id,
                    channel=rng.choice(["刷卡", "校园码", "自助终端"]),
                    summary=f"{category}消费",
                ))
                latest_time = max(latest_time, txn_time) if latest_time else txn_time
            if month_start in generated_months[-3:-1] or month_start == generated_months[-1]:
                subsidy_merchant = next(
                    (item for item in by_category["补助"] if item.name == "学校财务处"),
                    by_category["补助"][0],
                )
                subsidy_day = min(10 + rng.randint(0, 8), effective_end.day)
                subsidy_date = date(month_start.year, month_start.month, subsidy_day)
                item_name = rng.choice(["国家助学金", "校内生活补助", "勤工助学补助"])
                subsidy_amount = Decimal(rng.choice(["200.00", "300.00", "500.00"]))
                db.add(SubsidyRecord(
                    card_no=account.card_no, item=item_name, amount=subsidy_amount,
                    pay_date=subsidy_date, source="学校学生资助管理中心演示数据",
                ))
                records.append(CardTxn(
                    card_no=account.card_no,
                    txn_time=datetime.combine(subsidy_date, time(9, 0)),
                    amount=subsidy_amount, direction="IN",
                    merchant_id=subsidy_merchant.id, channel="财务代发",
                    summary=f"{item_name}入账",
                ))
        if records:
            abnormal_date = max(item.txn_time for item in records).date()
            abnormal_time = datetime.combine(
                abnormal_date, time(min(21, max(8, now_local().hour)), 15)
            )
            large_merchant = by_category["超市"][0]
            records.append(CardTxn(
                card_no=account.card_no, txn_time=abnormal_time,
                amount=Decimal("1200.00"), direction="OUT",
                merchant_id=large_merchant.id, channel="校园码",
                summary="大额异常消费（演示）",
            ))
            records.sort(key=lambda item: item.txn_time)
            running_after = Decimal(account.balance or 0)
            for record in reversed(records):
                amount = Decimal(record.amount)
                record.balance_after = running_after
                running_after = (
                    running_after + amount if record.direction == "OUT"
                    else running_after - amount
                )
                db.add(record)
            account.last_transaction_at = records[-1].txn_time
            created += len(records)
    if commit:
        db.commit()
    else:
        db.flush()
    return {"ok": True, "created_transactions": created, "skipped_cards": skipped,
            "blank_month": blank_month.strftime("%Y-%m")}

