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
    detail = first.get("msg", "参数格式不正确")
    return fail(100105, f"参数校验失败：{location} {detail}".strip(), 400)


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return fail(900001, "系统暂不可用，请稍后重试", 500)
