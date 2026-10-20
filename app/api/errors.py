"""错误归一化与中间件：统一错误体 {"error":{"code","message","details"}}。"""
from __future__ import annotations

import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

ERROR_MAP = {
    "workspace.not_found": 404,
    "workspace.locked": 409,
    "workspace.anchor_mismatch": 409,
    "workspace.tampered": 403,
    "workspace.detached": 409,
    "workspace.state_invalid": 422,
    "path.traversal": 400,
    "path.outside_workspace": 403,
    "path.inaccessible": 404,
    "doc.parse_failed": 422,
    "doc.skipped": 422,
    "retrieval.empty": 200,
    "retrieval.failed": 500,
    "fts5.unavailable": 503,
    "llm.unavailable": 503,
    "llm.budget_exceeded": 429,
    "llm.timeout": 504,
    "llm.parse_failed": 502,
    "integrity.verify_failed": 403,
    "integrity.chain_corrupt": 500,
    "budget.exceeded": 429,
    "config.invalid": 422,
    "schema.unsupported": 400,
    "server.busy": 503,
    "unsupported.operation": 501,
}


def error_response(code: str, message: str, details: dict | None = None) -> JSONResponse:
    status = ERROR_MAP.get(code, 500)
    return JSONResponse(status_code=status, content={
        "error": {"code": code, "message": message, "details": details or {}}
    })


class AppError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.details)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    traceback.print_exc()
    return error_response("internal.error", str(exc)[:300])


async def catch_all_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return error_response("internal.error", str(e)[:300])
