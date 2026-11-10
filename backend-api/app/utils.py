from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from .models import now_local


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def fmt_date(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def pagination(page: int, page_size: int, total: int) -> dict[str, Any]:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": page * page_size < total,
    }


def page_count(page: int, page_size: int, total: int) -> int:
    return max(1, math.ceil(total / page_size)) if total else 0


def extract_first_json(text: str) -> dict[str, Any] | None:
    import json
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def default_suggestions(question: str = "") -> list[str]:
    suggestions = ["校园卡丢失后如何补办？", "校园卡有哪些充值方式？", "校园卡消费范围包括哪些？"]
    if "优惠" in question:
        suggestions.insert(0, "校园卡优惠政策如何申请？")
    return suggestions[:3]


def utc_iso_now() -> str:
    return now_local().strftime("%Y-%m-%d %H:%M:%S")
