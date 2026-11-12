from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .conversation_models import (
    ActionToken, AppointmentSlot, CardOrder, CardTxn, Merchant, Office, OrderEvent,
    SubsidyRecord,
)
from .models import CampusCardAccount, SysUser, now_local

settings = get_settings()
ALLOWED_ACTIONS = {"loss", "unfreeze", "reissue", "recharge"}
ALLOWED_ORDER_STATUS = {
    "created", "submitted", "processing", "completed", "failed", "cancelled",
}
ORDER_TRANSITIONS = {
    "created": {"submitted", "cancelled", "failed"},
    "submitted": {"processing", "cancelled", "failed"},
    "processing": {"completed", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def demo_mode() -> bool:
    return _bool_env("DEMO_MODE", settings.app_env != "production")


def ok(data: Any, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, **{key: value for key, value in extra.items() if value is not None}}


def failure(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "error_code": error_code,
        "message": message,
        **{key: value for key, value in extra.items() if value is not None},
    }


def money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def money_text(value: Any) -> str:
    return f"{money(value):.2f}"


def mask_card_no(card_no: str) -> str:
    value = str(card_no or "")
    return f"{value[:4]}****{value[-4:]}" if len(value) >= 8 else value


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def resolve_time_range(
    range_key: str = "this_month",
    start: str | date | None = None,
    end: str | date | None = None,
    base_date: date | None = None,
) -> dict[str, Any]:
    """Resolve every relative range in Asia/Shanghai, capped at 365 days."""
    today = base_date or now_local().date()
    custom_start, custom_end = _parse_date(start), _parse_date(end)
    if range_key == "today":
        start_date = end_date = today
    elif range_key == "this_week":
        start_date, end_date = today - timedelta(days=today.weekday()), today
    elif range_key == "this_month":
        start_date, end_date = today.replace(day=1), today
    elif range_key == "last_month":
        end_date = today.replace(day=1) - timedelta(days=1)
        start_date = end_date.replace(day=1)
    elif range_key == "since_term_start":
        if today.month >= 9:
            start_date = date(today.year, 9, 1)
        elif today.month >= 2:
            start_date = date(today.year, 2, 15)
        else:
            start_date = date(today.year - 1, 9, 1)
        end_date = today
    elif range_key == "custom":
        if custom_start is None or custom_end is None:
            raise ValueError("自定义时间范围需要开始日期和结束日期")
        start_date, end_date = custom_start, custom_end
    else:
        raise ValueError("不支持的时间范围")
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    if (end_date - start_date).days > 365:
        raise ValueError("查询跨度不能超过一年")
    return {
        "range": range_key,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "label": f"{start_date.isoformat()} 至 {end_date.isoformat()}",
    }


def _user_id(user_context: dict[str, Any] | None) -> int:
    if not user_context or user_context.get("role") != "USER":
        raise ValueError("仅普通用户可查询本人校园卡数据")
    try:
        return int(user_context.get("user_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("缺少当前用户身份") from exc


def _account(db: Session, user_context: dict[str, Any] | None,
             params: dict[str, Any] | None = None) -> tuple[CampusCardAccount, SysUser]:
    params = params or {}
    if params.get("card_no"):
        raise PermissionError("不能按卡号查询他人账户，只能查询本人校园卡")
    requested_student = str(params.get("student_no") or "").strip()
    own_student = str((user_context or {}).get("student_no") or "").strip()
    if requested_student and requested_student != own_student:
        raise PermissionError("不能查询他人的校园卡信息")
    user_id = _user_id(user_context)
    row = (
        db.query(CampusCardAccount, SysUser)
        .join(SysUser, SysUser.id == CampusCardAccount.user_id)
        .filter(CampusCardAccount.user_id == user_id)
        .first()
    )
    if row is None:
        raise LookupError("未找到当前用户的校园卡账户")
    return row


def _base_txn_query(db: Session, card_no: str):
    return (
        db.query(CardTxn, Merchant)
        .outerjoin(Merchant, Merchant.id == CardTxn.merchant_id)
        .filter(CardTxn.card_no == card_no)
    )


def _range_dates(params: dict[str, Any]) -> tuple[dict[str, Any], date, date]:
    resolved = resolve_time_range(
        str(params.get("range") or params.get("range_key") or "this_month"),
        params.get("start"), params.get("end"),
    )
    return resolved, date.fromisoformat(resolved["start_date"]), date.fromisoformat(resolved["end_date"])


def get_balance(db: Session, user_context: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        account, user = _account(db, user_context, params)
        return ok({
            "balance": money_text(account.balance),
            "status": account.status,
            "card_no": mask_card_no(account.card_no),
            "student_no": user.student_no or "",
            "source": "本地校园卡账户数据库",
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("PRIVACY_OR_ACCOUNT", str(exc))


def query_transactions(db: Session, user_context: dict[str, Any],
                       params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        account, _ = _account(db, user_context, params)
        resolved, start_date, end_date = _range_dates(params)
        limit = min(50, max(1, int(params.get("limit", 20))))
        offset = max(0, int(params.get("offset", 0)))
        query = _base_txn_query(db, account.card_no).filter(
            CardTxn.txn_time >= datetime.combine(start_date, time.min),
            CardTxn.txn_time < datetime.combine(end_date + timedelta(days=1), time.min),
        )
        category = str(params.get("category") or "").strip()
        merchant = str(params.get("merchant") or "").strip()
        direction = str(params.get("direction") or "").upper()
        if category:
            query = query.filter(Merchant.category == category)
        if merchant:
            query = query.filter(Merchant.name.like(f"%{merchant}%"))
        if direction in {"IN", "OUT"}:
            query = query.filter(CardTxn.direction == direction)
        if params.get("min_amount") is not None:
            query = query.filter(CardTxn.amount >= money(params["min_amount"]))
        if params.get("max_amount") is not None:
            query = query.filter(CardTxn.amount <= money(params["max_amount"]))
        total = query.count()
        rows = query.order_by(CardTxn.txn_time.desc(), CardTxn.id.desc()).offset(offset).limit(limit).all()
        total_out = sum(
            (money(txn.amount) for txn, _merchant in query.filter(CardTxn.direction == "OUT").all()),
            Decimal("0"),
        )
        total_in = sum(
            (money(txn.amount) for txn, _merchant in query.filter(CardTxn.direction == "IN").all()),
            Decimal("0"),
        )
        items = [
            {
                "txn_id": txn.id, "time": txn.txn_time.strftime("%Y-%m-%d %H:%M"),
                "amount": money_text(txn.amount), "direction": txn.direction,
                "category": merchant_row.category if merchant_row else "其他",
                "merchant": merchant_row.name if merchant_row else "其他",
                "summary": txn.summary or "",
            }
            for txn, merchant_row in rows
        ]
        return ok(
            {
                "range": resolved,
                "total": total,
                "total_out": money_text(total_out),
                "total_in": money_text(total_in),
                "items": items,
            },
            truncated=total > offset + len(items),
        )
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def _group_key(txn: CardTxn, merchant: Merchant | None, group_by: str) -> str:
    if group_by == "day":
        return txn.txn_time.date().isoformat()
    if group_by == "week":
        week_start = txn.txn_time.date() - timedelta(days=txn.txn_time.weekday())
        return week_start.isoformat()
    if group_by == "month":
        return txn.txn_time.strftime("%Y-%m")
    if group_by == "merchant":
        return merchant.name if merchant else "其他"
    return merchant.category if merchant else "其他"


def aggregate_transactions(
    db: Session, user_context: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = params or {}
    try:
        account, _ = _account(db, user_context, params)
        resolved, start_date, end_date = _range_dates(params)
        group_by = str(params.get("group_by") or "category")
        if group_by not in {"day", "week", "month", "category", "merchant"}:
            raise ValueError("不支持的分组方式")
        direction = str(params.get("direction") or "OUT").upper()
        query = _base_txn_query(db, account.card_no).filter(
            CardTxn.txn_time >= datetime.combine(start_date, time.min),
            CardTxn.txn_time < datetime.combine(end_date + timedelta(days=1), time.min),
        )
        if direction in {"IN", "OUT"}:
            query = query.filter(CardTxn.direction == direction)
        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"amount": Decimal("0"), "count": 0}
        )
        for txn, merchant in query.all():
            key = _group_key(txn, merchant, group_by)
            buckets[key]["amount"] += money(txn.amount)
            buckets[key]["count"] += 1
        total_amount = sum((bucket["amount"] for bucket in buckets.values()), Decimal("0"))
        total_count = sum(bucket["count"] for bucket in buckets.values())
        items = [
            {
                "key": key,
                "amount": money_text(value["amount"]),
                "count": value["count"],
                "share": round(float(value["amount"] / total_amount * 100), 2) if total_amount else 0.0,
            }
            for key, value in buckets.items()
        ]
        items.sort(key=lambda item: (Decimal(item["amount"]), item["count"]), reverse=True)
        days = max(1, (end_date - start_date).days + 1)
        return ok({
            "range": resolved,
            "group_by": group_by,
            "direction": direction,
            "total_amount": money_text(total_amount),
            "total_count": total_count,
            "daily_average": money_text(total_amount / days),
            "items": items,
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def compare_periods(db: Session, user_context: dict[str, Any],
                    params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        group_by = str(params.get("group_by") or "category")
        direction = str(params.get("direction") or "OUT")
        range_a = params.get("range_a") or "this_month"
        range_b = params.get("range_b") or "last_month"
        first = aggregate_transactions(db, user_context, {
            "range": range_a, "group_by": group_by, "direction": direction,
            "start": params.get("start_a"), "end": params.get("end_a"),
        })
        second = aggregate_transactions(db, user_context, {
            "range": range_b, "group_by": group_by, "direction": direction,
            "start": params.get("start_b"), "end": params.get("end_b"),
        })
        if not first.get("ok"):
            return first
        if not second.get("ok"):
            return second
        first_map = {item["key"]: money(item["amount"]) for item in first["data"]["items"]}
        second_map = {item["key"]: money(item["amount"]) for item in second["data"]["items"]}
        keys = set(first_map) | set(second_map)
        contributions = [
            {
                "key": key,
                "difference": money_text(first_map.get(key, Decimal("0")) - second_map.get(key, Decimal("0"))),
                "current": money_text(first_map.get(key, Decimal("0"))),
                "previous": money_text(second_map.get(key, Decimal("0"))),
            }
            for key in keys
        ]
        contributions.sort(key=lambda item: abs(money(item["difference"])), reverse=True)
        current_total = money(first["data"]["total_amount"])
        previous_total = money(second["data"]["total_amount"])
        difference = current_total - previous_total
        growth = (
            float(difference / previous_total * 100) if previous_total else None
        )
        return ok({
            "group_by": group_by,
            "direction": direction,
            "period_a": first["data"]["range"],
            "period_b": second["data"]["range"],
            "current_total": money_text(current_total),
            "previous_total": money_text(previous_total),
            "difference": money_text(difference),
            "growth_percent": round(growth, 2) if growth is not None else None,
            "top_contributors": contributions[:3],
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def list_subsidy_records(db: Session, user_context: dict[str, Any],
                         params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        account, _ = _account(db, user_context, params)
        resolved, start_date, end_date = _range_dates(params)
        rows = (
            db.query(SubsidyRecord)
            .filter(
                SubsidyRecord.card_no == account.card_no,
                SubsidyRecord.pay_date >= start_date,
                SubsidyRecord.pay_date <= end_date,
            )
            .order_by(SubsidyRecord.pay_date.desc())
            .all()
        )
        return ok({
            "range": resolved,
            "items": [
                {
                    "item": row.item, "amount": money_text(row.amount),
                    "pay_date": row.pay_date.isoformat(), "source": row.source,
                }
                for row in rows
            ],
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def forecast_balance(db: Session, user_context: dict[str, Any],
                     params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        account, _ = _account(db, user_context, params)
        days = min(180, max(7, int(params.get("days", 30))))
        threshold = money(params.get("threshold", 50))
        today = now_local().date()
        start_date = today - timedelta(days=days - 1)
        spent = (
            db.query(func.coalesce(func.sum(CardTxn.amount), 0))
            .filter(
                CardTxn.card_no == account.card_no,
                CardTxn.direction == "OUT",
                CardTxn.txn_time >= datetime.combine(start_date, time.min),
            )
            .scalar()
        )
        total_spent = money(spent)
        daily_average = (total_spent / days).quantize(Decimal("0.01"))
        balance = money(account.balance)
        support_days = int((balance / daily_average).to_integral_value(rounding=ROUND_CEILING)) if daily_average else None
        threshold_date = (
            today + timedelta(days=max(0, support_days - 1))
            if support_days is not None else None
        )
        suggest = Decimal("0")
        if daily_average:
            target = daily_average * Decimal("14") + threshold
            suggest = max(Decimal("0"), target - balance).quantize(Decimal("0.01"))
        return ok({
            "balance": money_text(balance),
            "window_days": days,
            "total_spent": money_text(total_spent),
            "daily_average": money_text(daily_average),
            "support_days": support_days,
            "threshold": money_text(threshold),
            "threshold_date": threshold_date.isoformat() if threshold_date else None,
            "suggested_recharge": money_text(suggest),
        })
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def _normalize_params(action_type: str, params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    normalized.pop("_auto_commit", None)
    normalized.pop("_pending_token", None)
    if action_type == "recharge":
        normalized["amount"] = money_text(normalized.get("amount"))
        normalized["channel"] = str(normalized.get("channel") or "本地模拟充值")
    if action_type == "reissue":
        date_value = str(normalized.get("date") or "")
        relative = re.fullmatch(r"relative:(\d+)d", date_value)
        if relative:
            date_value = (now_local().date() + timedelta(days=int(relative.group(1)))).isoformat()
        normalized["date"] = date_value
        slot_value = str(normalized.get("slot") or "")
        if not slot_value:
            slot_value = {
                "afternoon": "14:00", "morning": "09:00", "noon": "10:30",
            }.get(str(normalized.get("preferred_slot") or ""), "")
        normalized["slot"] = slot_value
        normalized["office_id"] = int(normalized.get("office_id") or 0)
        normalized.pop("office", None)
        normalized.pop("preferred_slot", None)
    return normalized


def _params_hash(params: dict[str, Any]) -> str:
    payload = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _idempotency_key(card_no: str, action_type: str, params: dict[str, Any]) -> str:
    window = now_local().strftime("%Y-%m-%d")
    raw = f"{card_no}|{action_type}|{_params_hash(params)}|{window}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event(db: Session, order: CardOrder, to_status: str, note: str = "") -> None:
    previous = order.status
    if to_status not in ORDER_TRANSITIONS.get(previous, set()):
        raise ValueError(f"订单不能从 {previous} 变更为 {to_status}")
    changed = (
        db.query(CardOrder)
        .filter(
            CardOrder.id == order.id,
            CardOrder.version == order.version,
            CardOrder.status == previous,
        )
        .update(
            {
                CardOrder.status: to_status,
                CardOrder.version: CardOrder.version + 1,
                CardOrder.updated_at: now_local(),
            },
            synchronize_session=False,
        )
    )
    if not changed:
        raise ValueError("工单状态已被其他操作更新，请刷新后重试")
    order.status = to_status
    order.version += 1
    order.updated_at = now_local()
    db.add(OrderEvent(
        order_no=order.order_no, from_status=previous, to_status=to_status,
        note=note or f"状态更新为 {to_status}",
    ))


def _next_order_no(prefix: str) -> str:
    return f"{prefix}-{now_local():%Y%m%d%H%M%S}-{secrets.token_hex(2).upper()}"


def _order_json(db: Session, order: CardOrder) -> dict[str, Any]:
    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_no == order.order_no)
        .order_by(OrderEvent.at, OrderEvent.id)
        .all()
    )
    return {
        "order_no": order.order_no,
        "type": order.type,
        "status": order.status,
        "amount": money_text(order.amount) if order.amount is not None else "",
        "payload": order.payload_json or {},
        "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": order.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "events": [
            {
                "from": event.from_status, "to": event.to_status,
                "at": event.at.strftime("%Y-%m-%d %H:%M"),
                "note": event.note or "",
            }
            for event in events
        ],
    }


def _latest_txn(db: Session, card_no: str) -> CardTxn | None:
    return (
        db.query(CardTxn)
        .filter(CardTxn.card_no == card_no)
        .order_by(CardTxn.txn_time.desc(), CardTxn.id.desc())
        .first()
    )


def _choose_slot(
    db: Session, params: dict[str, Any], today: date | None = None,
) -> AppointmentSlot | None:
    today = today or now_local().date()
    target = _parse_date(params.get("date")) or today + timedelta(days=1)
    office_id = int(params.get("office_id") or 0)
    slot = str(params.get("slot") or "").strip()
    query = db.query(AppointmentSlot).filter(
        AppointmentSlot.date == target,
        AppointmentSlot.booked < AppointmentSlot.capacity,
    )
    if office_id:
        query = query.filter(AppointmentSlot.office_id == office_id)
    if slot:
        query = query.filter(AppointmentSlot.slot == slot)
    return query.order_by(AppointmentSlot.office_id, AppointmentSlot.slot).first()


def prepare_action(
    db: Session, user_context: dict[str, Any], action_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = params or {}
    if action_type not in ALLOWED_ACTIONS:
        return failure("UNSUPPORTED_ACTION", "暂不支持这类校园卡操作")
    if not demo_mode():
        return failure("NOT_IMPLEMENTED", "演示办理功能当前未开启")
    try:
        account, user = _account(db, user_context, params)
        normalized = _normalize_params(action_type, params)
        if action_type != "reissue":
            existing_key = _idempotency_key(account.card_no, action_type, normalized)
            existing_order = db.query(CardOrder).filter(
                CardOrder.idempotency_key == existing_key
            ).first()
            if existing_order:
                return ok({
                    "duplicate": True,
                    "order": _order_json(db, existing_order),
                    "requires_confirmation": existing_order.status == "created",
                })
        if action_type == "loss" and account.status != "ACTIVE":
            return failure("INVALID_CARD_STATE", "校园卡当前不是正常状态，无需重复挂失")
        if action_type == "unfreeze" and account.status not in {"LOST", "FROZEN"}:
            return failure("INVALID_CARD_STATE", "校园卡当前不需要解挂")
        if action_type == "unfreeze":
            tail = str(normalized.get("student_tail4") or "")
            last_amount = normalized.get("last_amount")
            latest = _latest_txn(db, account.card_no)
            student_ok = bool(tail and tail == (user.student_no or "")[-4:])
            amount_ok = bool(
                last_amount is not None and latest and money(last_amount) == money(latest.amount)
            )
            if not student_ok and not amount_ok:
                return failure(
                    "VERIFY_REQUIRED",
                    "请提供学号后四位，或最近一笔消费金额，用于核验本人身份",
                )
        if action_type == "reissue":
            if account.status != "LOST":
                return failure(
                    "LOSS_REQUIRED",
                    "校园卡当前没有挂失，补办预约需要先完成挂失",
                )
            slot = _choose_slot(db, normalized)
            if slot is None:
                return failure("NO_APPOINTMENT", "所选日期暂无可预约时段，可以换一天试试")
            office = db.get(Office, slot.office_id)
            normalized.update({
                "date": slot.date.isoformat(), "slot": slot.slot,
                "office_id": slot.office_id, "office_name": office.name if office else "校园卡服务网点",
                "office_address": office.address if office else "",
                "slot_id": slot.id,
            })
        if action_type == "recharge":
            amount = money(normalized.get("amount"))
            single_limit = money(_int_env("RECHARGE_SINGLE_LIMIT", 500))
            daily_limit = money(_int_env("RECHARGE_DAILY_LIMIT", 1000))
            balance_limit = money(_int_env("CARD_BALANCE_LIMIT", 5000))
            if amount <= 0 or amount > single_limit:
                return failure("INVALID_AMOUNT", f"单笔充值金额需在 0.01 至 {money_text(single_limit)} 元之间")
            if account.status != "ACTIVE":
                return failure(
                    "INVALID_CARD_STATE",
                    "卡目前不是正常状态，不能充值；如已挂失，请先解挂",
                )
            if money(account.balance) + amount > balance_limit:
                return failure("BALANCE_LIMIT", f"充值后余额不能超过 {money_text(balance_limit)} 元")
            start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
            today_total = (
                db.query(func.coalesce(func.sum(CardOrder.amount), 0))
                .filter(
                    CardOrder.user_id == user.id, CardOrder.type == "recharge",
                    CardOrder.status.in_(["submitted", "processing", "completed"]),
                    CardOrder.created_at >= start,
                )
                .scalar()
            )
            if money(today_total) + amount > daily_limit:
                return failure("DAILY_LIMIT", f"今日累计充值不能超过 {money_text(daily_limit)} 元")
            normalized["amount"] = money_text(amount)
        idempotency_key = _idempotency_key(account.card_no, action_type, normalized)
        existing = db.query(CardOrder).filter(CardOrder.idempotency_key == idempotency_key).first()
        if existing:
            return ok({
                "duplicate": True,
                "order": _order_json(db, existing),
                "requires_confirmation": existing.status == "created",
            })
        type_label = {"loss": "挂失", "unfreeze": "解挂", "reissue": "补办预约", "recharge": "充值"}[action_type]
        order = CardOrder(
            order_no=_next_order_no({"loss": "LOS", "unfreeze": "UNF", "reissue": "REI", "recharge": "RCG"}[action_type]),
            card_no=account.card_no, user_id=user.id, type=action_type, status="created",
            amount=money(normalized.get("amount")) if action_type == "recharge" else None,
            payload_json=normalized, idempotency_key=idempotency_key,
        )
        db.add(order)
        db.flush()
        db.add(OrderEvent(
            order_no=order.order_no, from_status="none", to_status="created",
            note=f"已预演{type_label}，等待用户确认",
        ))
        token_value = secrets.token_urlsafe(32)
        db.add(ActionToken(
            token=token_value, card_no=account.card_no, user_id=user.id,
            action_type=action_type, params_hash=_params_hash(normalized),
            params_json={**normalized, "order_no": order.order_no},
            expires_at=now_local() + timedelta(minutes=5),
        ))
        db.commit()
        return ok({
            "confirm_token": token_value,
            "requires_confirmation": True,
            "order": _order_json(db, order),
            "summary": _action_summary(action_type, normalized),
        })
    except PermissionError as exc:
        db.rollback()
        return failure("PRIVACY", str(exc))
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return failure("INVALID_ACTION", str(exc))


def _action_summary(action_type: str, params: dict[str, Any]) -> str:
    if action_type == "loss":
        return "挂失后将立即冻结校园卡消费，并生成一张挂失工单。"
    if action_type == "unfreeze":
        return "核验通过后将恢复校园卡消费功能。"
    if action_type == "reissue":
        date_value = _parse_date(params.get("date"))
        weekday = "一二三四五六日"[date_value.weekday()] if date_value else ""
        date_text = f"{date_value.month} 月 {date_value.day} 日（周{weekday}）" if date_value else "待定"
        return (
            f"预约 {date_text} {params.get('slot', '')}，"
            f"{params.get('office_name', '校园卡服务网点')}；请带学生证并提前 10 分钟到场。"
        )
    return f"将为校园卡充值 {params.get('amount')} 元，演示环境不会产生真实资金变动。"


def _rate_limited(db: Session, user_id: int, action_type: str, current_order: str) -> bool:
    since = now_local() - timedelta(minutes=1)
    return (
        db.query(CardOrder.id)
        .filter(
            CardOrder.user_id == user_id, CardOrder.type == action_type,
            CardOrder.order_no != current_order,
            CardOrder.status.in_(["submitted", "processing", "completed"]),
            CardOrder.updated_at >= since,
        )
        .first()
        is not None
    )


def commit_action(
    db: Session, user_context: dict[str, Any],
    token: str | None = None, params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not demo_mode():
        return failure("NOT_IMPLEMENTED", "演示办理功能当前未开启")
    token = token or str((params or {}).get("confirm_token") or "")
    if not token:
        return failure("TOKEN_REQUIRED", "请先确认办理内容，再执行操作")
    try:
        account, user = _account(db, user_context, params)
        token_row = db.query(ActionToken).filter(ActionToken.token == token).first()
        if token_row is None:
            return failure("INVALID_TOKEN", "确认信息无效或已失效，请重新发起")
        if token_row.used:
            return failure("TOKEN_USED", "这条确认已经使用过，请勿重复提交")
        if token_row.expires_at <= now_local():
            return failure("TOKEN_EXPIRED", "确认已超过 5 分钟，请重新发起")
        if token_row.user_id != user.id or token_row.card_no != account.card_no:
            return failure("TOKEN_MISMATCH", "确认信息与当前账号不匹配")
        order_no = str((token_row.params_json or {}).get("order_no") or "")
        order = db.query(CardOrder).filter(CardOrder.order_no == order_no).first()
        if order is None:
            return failure("ORDER_NOT_FOUND", "待办理工单不存在")
        if _rate_limited(db, user.id, token_row.action_type, order.order_no):
            return failure("RATE_LIMITED", "同类操作一分钟内只能办理一次，请稍后再试")
        action_params = token_row.params_json or {}
        claimed = (
            db.query(ActionToken)
            .filter(ActionToken.id == token_row.id, ActionToken.used.is_(False))
            .update({ActionToken.used: True}, synchronize_session=False)
        )
        if not claimed:
            db.rollback()
            return failure("TOKEN_USED", "这条确认已经使用过，请勿重复提交")
        if token_row.action_type == "loss":
            account.status = "LOST"
            note = "校园卡已挂失并冻结消费"
        elif token_row.action_type == "unfreeze":
            account.status = "ACTIVE"
            note = "校园卡已解挂并恢复消费"
        elif token_row.action_type == "reissue":
            slot_id = int(action_params.get("slot_id") or 0)
            updated = (
                db.query(AppointmentSlot)
                .filter(
                    AppointmentSlot.id == slot_id,
                    AppointmentSlot.booked < AppointmentSlot.capacity,
                )
                .update({AppointmentSlot.booked: AppointmentSlot.booked + 1},
                        synchronize_session=False)
            )
            if not updated:
                db.rollback()
                return failure("SLOT_FULL", "该预约时段刚刚约满，请换一个时段")
            note = "补办预约已提交"
        else:
            amount = money(action_params.get("amount"))
            account.balance = money(account.balance) + amount
            account.last_transaction_at = now_local()
            merchant = db.query(Merchant).filter(Merchant.category == "其他").first()
            db.add(CardTxn(
                card_no=account.card_no, txn_time=now_local(), amount=amount,
                direction="IN", merchant_id=merchant.id if merchant else None,
                channel="本地模拟充值", balance_after=account.balance,
                summary="校园卡本地模拟充值",
            ))
            note = "本地模拟充值成功"
        _event(db, order, "submitted", note)
        db.commit()
        return ok({"order": _order_json(db, order), "summary": note})
    except PermissionError as exc:
        db.rollback()
        return failure("PRIVACY", str(exc))
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return failure("INVALID_ACTION", str(exc))


def cancel_action(
    db: Session, user_context: dict[str, Any],
    token: str | None = None, params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = token or str((params or {}).get("confirm_token") or "")
    try:
        account, user = _account(db, user_context, params)
        token_row = db.query(ActionToken).filter(ActionToken.token == token).first()
        if token_row is None or token_row.used or token_row.user_id != user.id:
            return failure("INVALID_TOKEN", "没有可取消的待确认操作")
        claimed = (
            db.query(ActionToken)
            .filter(ActionToken.id == token_row.id, ActionToken.used.is_(False))
            .update({ActionToken.used: True}, synchronize_session=False)
        )
        if not claimed:
            return failure("TOKEN_USED", "这条确认已经处理过")
        order_no = str((token_row.params_json or {}).get("order_no") or "")
        order = db.query(CardOrder).filter(CardOrder.order_no == order_no).first()
        if order and order.status in {"created", "submitted", "processing"}:
            if order.status != "created":
                _restore_cancelled_order(db, order, account)
            _event(db, order, "cancelled", "用户取消办理")
        db.commit()
        return ok({"cancelled": True, "order": _order_json(db, order) if order else None})
    except (PermissionError, ValueError) as exc:
        db.rollback()
        return failure("INVALID_ACTION", str(exc))


def _restore_cancelled_order(db: Session, order: CardOrder, account: CampusCardAccount) -> None:
    if order.type == "loss":
        account.status = "ACTIVE"
    elif order.type == "reissue":
        slot_id = int((order.payload_json or {}).get("slot_id") or 0)
        slot = db.get(AppointmentSlot, slot_id)
        if slot and slot.booked > 0:
            slot.booked -= 1
    elif order.type == "recharge" and order.amount:
        account.balance = max(Decimal("0"), money(account.balance) - money(order.amount))


def refresh_demo_order(db: Session, order: CardOrder) -> None:
    if not demo_mode() or order.status not in {"submitted", "processing"}:
        return
    submitted = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_no == order.order_no, OrderEvent.to_status == "submitted")
        .order_by(OrderEvent.at)
        .first()
    )
    if submitted is None:
        return
    elapsed = (now_local() - submitted.at).total_seconds()
    processing_after = max(0, _int_env("DEMO_PROCESSING_SECONDS", 3))
    completed_after = max(processing_after, _int_env("DEMO_COMPLETED_SECONDS", 10))
    if order.status == "submitted" and elapsed >= processing_after:
        _event(db, order, "processing", "业务窗口正在处理")
        db.commit()
    if order.status == "processing" and elapsed >= completed_after:
        _event(db, order, "completed", "办理完成")
        db.commit()


def query_order_status(db: Session, user_context: dict[str, Any],
                       params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        account, user = _account(db, user_context, params)
        order_no = str(params.get("order_no") or "").strip()
        query = db.query(CardOrder).filter(
            CardOrder.user_id == user.id, CardOrder.card_no == account.card_no,
        )
        if order_no:
            query = query.filter(CardOrder.order_no == order_no)
        order = query.order_by(CardOrder.created_at.desc(), CardOrder.id.desc()).first()
        if order is None:
            return ok({"found": False, "message": "没有查询到对应工单"})
        refresh_demo_order(db, order)
        return ok({"found": True, "order": _order_json(db, order)})
    except (PermissionError, LookupError, ValueError) as exc:
        return failure("INVALID_QUERY", str(exc))


def cancel_order(db: Session, user_context: dict[str, Any],
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        account, user = _account(db, user_context, params)
        order_no = str(params.get("order_no") or "").strip()
        query = db.query(CardOrder).filter(
            CardOrder.user_id == user.id, CardOrder.card_no == account.card_no,
        )
        if order_no:
            query = query.filter(CardOrder.order_no == order_no)
        order = query.order_by(CardOrder.created_at.desc(), CardOrder.id.desc()).first()
        if order is None:
            return failure("ORDER_NOT_FOUND", "没有找到可取消的工单")
        if order.status in {"completed", "failed", "cancelled"}:
            return failure("NOT_CANCELLABLE", "该工单已经结束，不能取消")
        _restore_cancelled_order(db, order, account)
        _event(db, order, "cancelled", "用户取消工单")
        db.commit()
        return ok({"order": _order_json(db, order)})
    except (PermissionError, ValueError) as exc:
        db.rollback()
        return failure("INVALID_ACTION", str(exc))


def advance_demo_status(db: Session, user_context: dict[str, Any],
                        params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not demo_mode():
        return failure("NOT_IMPLEMENTED", "演示状态推进仅在演示环境可用")
    params = params or {}
    try:
        account, user = _account(db, user_context, params)
        order_no = str(params.get("order_no") or "")
        order = db.query(CardOrder).filter(
            CardOrder.order_no == order_no, CardOrder.user_id == user.id,
            CardOrder.card_no == account.card_no,
        ).first()
        if order is None:
            return failure("ORDER_NOT_FOUND", "工单不存在")
        next_status = {"created": "submitted", "submitted": "processing",
                       "processing": "completed"}.get(order.status)
        if next_status is None:
            return failure("NOT_ADVANCEABLE", "该工单不能继续推进")
        _event(db, order, next_status, "演示脚本推进")
        db.commit()
        return ok({"order": _order_json(db, order)})
    except (PermissionError, ValueError) as exc:
        db.rollback()
        return failure("INVALID_ACTION", str(exc))


def _pending_token(db: Session, user_context: dict[str, Any]) -> str | None:
    try:
        account, _ = _account(db, user_context)
    except (PermissionError, LookupError, ValueError):
        return None
    row = (
        db.query(ActionToken)
        .filter(
            ActionToken.user_id == account.user_id,
            ActionToken.card_no == account.card_no,
            ActionToken.used.is_(False),
            ActionToken.expires_at > now_local(),
        )
        .order_by(ActionToken.created_at.desc())
        .first()
    )
    return row.token if row else None


def get_pending_action_token(db: Session, user_context: dict[str, Any]) -> str | None:
    """Return an opaque token for trusted orchestration; it is never placed in the prompt."""
    return _pending_token(db, user_context)


def _normalized_text(question: str) -> str:
    return re.sub(r"[\s，。！？!?,.；;：:]+", "", question or "").lower()


def _extract_recharge_amount(question: str) -> Decimal | None:
    match = re.search(r"(?:充|充值)\s*(?:值)?\s*(\d+(?:\.\d{1,2})?)\s*元?", question or "")
    return money(match.group(1)) if match else None


def _relative_date(text: str) -> str:
    today = now_local().date()
    if "后天" in text:
        target = today + timedelta(days=2)
    elif "明天" in text:
        target = today + timedelta(days=1)
    elif "今天" in text:
        target = today
    else:
        match = re.search(r"(?:(\d{1,2})月(\d{1,2})日)|(20\d{2}-\d{1,2}-\d{1,2})", text)
        if match:
            if match.group(3):
                return date.fromisoformat(match.group(3)).isoformat()
            return date(today.year, int(match.group(1)), int(match.group(2))).isoformat()
        return (today + timedelta(days=1)).isoformat()
    return target.isoformat()


def _slot_for_text(text: str) -> str:
    if "下午" in text:
        return "14:00"
    if "上午" in text:
        return "09:00"
    if "中午" in text:
        return "10:30"
    return ""


def handle_conversation(
    db: Session, question: str, user_context: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One deterministic conversation entry that composes reads and two-stage writes."""
    params = params or {}
    text = _normalized_text(question)
    compact = re.sub(r"\s+", "", question or "")
    if any(term in text for term in ("别人的余额", "他人余额", "同学的余额", "别人校园卡", "查一下别人")):
        return failure("PRIVACY", "为了保护账户隐私，只能查询本人的校园卡信息。")
    confirmations = {"好", "可以", "嗯", "行", "确认", "就这样", "好的", "没问题", "就它了"}
    cancels = {"不用了", "算了", "取消", "改天", "不要了"}
    if text in confirmations or text in {"是的", "对"}:
        token = params.get("_pending_token") or _pending_token(db, user_context)
        if token:
            return commit_action(db, user_context, str(token))
        return failure("NO_PENDING_ACTION", "当前没有等待确认的办理事项")
    if "取消" in text and any(term in text for term in ("工单", "预约", "订单")):
        order_match = re.search(r"(?:单号|工单号|凭证号)[:：]?\s*([A-Za-z0-9-]{6,})", question or "")
        return cancel_order(db, user_context, {
            "order_no": order_match.group(1) if order_match else "",
        })
    if text in cancels or text.startswith("取消"):
        token = params.get("_pending_token") or _pending_token(db, user_context)
        if token:
            return cancel_action(db, user_context, str(token))
        return failure("NO_PENDING_ACTION", "当前没有可取消的待确认事项")
    if any(term in text for term in ("改成", "换一个", "换个", "改到")):
        token = str(params.get("_pending_token") or _pending_token(db, user_context) or "")
        pending = db.query(ActionToken).filter(ActionToken.token == token).first()
        if pending is None or pending.used or pending.action_type != "reissue":
            return failure("NO_PENDING_ACTION", "当前没有可以改期的补办预约")
        old_params = dict(pending.params_json or {})
        new_params: dict[str, Any] = {"date": old_params.get("date") or _relative_date(compact)}
        if "下午" in compact:
            new_params["preferred_slot"] = "afternoon"
        elif "上午" in compact:
            new_params["preferred_slot"] = "morning"
        if "网点" in compact:
            offices = db.query(Office).order_by(Office.id).all()
            current = int(old_params.get("office_id") or 0)
            ids = [office.id for office in offices]
            if ids:
                new_params["office_id"] = ids[(ids.index(current) + 1) % len(ids)] if current in ids else ids[0]
        replacement = prepare_action(db, user_context, "reissue", new_params)
        if not replacement.get("ok"):
            return replacement
        cancelled = cancel_action(db, user_context, token)
        committed = commit_action(db, user_context, replacement["data"]["confirm_token"])
        return ok({
            "operations": [cancelled.get("data"), committed.get("data")],
            "partial": not committed.get("ok"),
            "summary": "已取消原预约并按新条件重新预约",
        })

    wants_loss = any(term in text for term in ("卡丢", "挂失", "卡片遗失", "找不到卡"))
    wants_reissue = any(term in text for term in ("补办", "补卡", "预约办理", "预约校园卡"))
    wants_unfreeze = "解挂" in text or "解除挂失" in text
    wants_recharge = "充值" in text or "充钱" in text
    wants_compound = "先" in text and wants_loss and wants_reissue
    if wants_compound:
        loss = prepare_action(db, user_context, "loss", {})
        if not loss.get("ok"):
            return loss
        loss_commit = commit_action(db, user_context, loss["data"]["confirm_token"])
        if not loss_commit.get("ok"):
            return loss_commit
        reissue_params = {"date": _relative_date(compact), "slot": _slot_for_text(compact)}
        reissue = prepare_action(db, user_context, "reissue", reissue_params)
        if not reissue.get("ok"):
            return ok({
                "operations": [loss_commit["data"], reissue],
                "partial": True,
                "message": "挂失已完成，补办预约还需要补充条件",
            })
        reissue_commit = commit_action(db, user_context, reissue["data"]["confirm_token"])
        return ok({
            "operations": [loss_commit.get("data"), reissue_commit.get("data")],
            "partial": False,
        })
    if wants_unfreeze:
        verify: dict[str, Any] = {}
        tail_match = re.search(r"学号后四位\s*(\d{4})", question or "")
        amount_match = re.search(r"(?:金额|消费了?)\s*(\d+(?:\.\d{1,2})?)\s*元", question or "")
        if tail_match:
            verify["student_tail4"] = tail_match.group(1)
        if amount_match:
            verify["last_amount"] = amount_match.group(1)
        return prepare_action(db, user_context, "unfreeze", verify)
    if wants_reissue:
        result = prepare_action(db, user_context, "reissue", {
            "date": _relative_date(compact), "slot": _slot_for_text(compact),
        })
        if result.get("ok") and any(term in compact for term in ("我要预约", "帮我预约", "直接预约")):
            committed = commit_action(db, user_context, result["data"]["confirm_token"])
            if committed.get("ok"):
                return committed
        return result
    if wants_recharge:
        amount = _extract_recharge_amount(question)
        if amount is None:
            return failure("MISSING_AMOUNT", "请告诉我想充值多少元")
        return prepare_action(db, user_context, "recharge", {"amount": amount})
    if wants_loss:
        return prepare_action(db, user_context, "loss", {})
    if any(term in text for term in ("工单进度", "办理进度", "查到哪", "最近一笔工单", "订单进度")):
        order_match = re.search(r"(?:单号|工单号|凭证号)[:：]?\s*([A-Za-z0-9-]{6,})", question or "")
        return query_order_status(db, user_context, {
            "order_no": order_match.group(1) if order_match else "",
        })
    if any(term in text for term in ("余额", "卡里多少钱", "还有多少钱")):
        return get_balance(db, user_context)
    if any(term in text for term in ("月底够", "照这样花", "还能用多久", "余额预测", "预计什么时候")):
        return forecast_balance(db, user_context, {"days": 30})
    if "比上个月" in text or ("环比" in text and "余额" not in text):
        return compare_periods(db, user_context, {
            "range_a": "this_month", "range_b": "last_month",
            "group_by": "category", "direction": "OUT",
        })
    if any(term in text for term in ("哪块花", "哪类花", "花得最多", "消费最多")):
        return aggregate_transactions(db, user_context, {
            "range": "this_month", "group_by": "category", "direction": "OUT",
        })
    if "这个月花了多少" in text or ("这个月" in text and any(term in text for term in ("花了", "支出", "消费多少"))):
        return aggregate_transactions(db, user_context, {
            "range": "this_month", "group_by": "month", "direction": "OUT",
        })
    if any(term in text for term in ("补助", "助学", "入账", "发了什么钱")):
        subsidy = list_subsidy_records(db, user_context, {
            "range": "since_term_start",
        })
        return subsidy
    specific_day = re.search(
        r"(?:(\d{1,2})月(\d{1,2})[日号]).{0,8}([+-]?(\d+(?:\.\d{1,2})?))",
        question or "",
    )
    if specific_day:
        today = now_local().date()
        start = date(today.year, int(specific_day.group(1)), int(specific_day.group(2)))
        result = query_transactions(db, user_context, {
            "range": "custom", "start": start.isoformat(), "end": start.isoformat(),
            "direction": "IN" if "+" in question or "入账" in question else "",
            "limit": 20,
        })
        if result.get("ok"):
            result["data"]["context"] = "该笔入账可结合补助记录和本地知识库中的发放规则解释"
        return result
    if any(term in text for term in ("流水", "消费明细", "账单", "哪笔", "交易记录")):
        return query_transactions(db, user_context, {
            "range": "this_month", "limit": 20,
        })
    return failure(
        "UNSUPPORTED",
        "暂时没有识别出可执行的校园卡查询或办理事项，请补充时间、金额或具体业务。",
    )
