from __future__ import annotations

import time
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def success(data: Any = None, pagination: dict[str, Any] | None = None, status_code: int = 200) -> JSONResponse:
    body: dict[str, Any] = {"code": 0, "message": "success", "data": data, "timestamp": int(time.time())}
    if pagination is not None:
        body["pagination"] = pagination
    return JSONResponse(status_code=status_code, content=body)


def fail(code: int, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "data": None, "timestamp": int(time.time())},
    )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return fail(exc.code, exc.message, exc.status_code)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first.get("loc", []) if item not in {"body", "query", "path"})
    field = location.split(".")[-1] if location else ""
    labels = {"account": "账号", "password": "密码", "username": "用户名", "nickname": "昵称",
              "phone": "手机号", "email": "邮箱", "student_no": "学号", "question": "问题",
              "title": "标题", "session_id": "会话", "document_id": "文档", "category_id": "分类",
              "status": "状态", "config_value": "配置值", "reason": "原因"}
    label = labels.get(field, field)
    detail = _chinese_validation_message(first)
    return fail(100105, f"参数校验失败：{label} {detail}".strip(), 400)


def _chinese_validation_message(first: dict[str, Any]) -> str:
    """把 Pydantic 的英文校验提示转换成用户能看懂的中文。"""
    error_type = str(first.get("type", ""))
    ctx = first.get("ctx") or {}
    if error_type == "missing":
        return "不能为空"
    if error_type == "string_too_short":
        return f"不能少于{ctx.get('min_length', '')}个字符"
    if error_type == "string_too_long":
        return f"不能超过{ctx.get('max_length', '')}个字符"
    if error_type in {"int_parsing", "int_type"}:
        return "必须为整数"
    if error_type in {"float_parsing", "float_type"}:
        return "必须为数字"
    if error_type == "bool_parsing":
        return "必须为是或否"
    if error_type == "literal_error":
        return "取值不在允许范围内"
    if error_type in {"string_pattern_mismatch", "string_type"}:
        return "格式不正确"
    if error_type == "value_error":
        message = str(ctx.get("error") or first.get("msg", ""))
        return message.removeprefix("Value error, ") or "格式不正确"
    message = str(first.get("msg", "参数格式不正确"))
    return message or "参数格式不正确"


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return fail(900001, "系统暂不可用，请稍后重试", 500)
