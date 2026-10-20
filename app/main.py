"""FastAPI create_app + lifespan：静态前端托管、错误处理、优雅退出。"""
from __future__ import annotations

import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import AppError, app_error_handler, error_response, unhandled_error_handler
from app.api.routes import router
from app.deps import registry


def _base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


FRONTEND_DIST = _base_dir() / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    registry.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="盘枢 KBEngine", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.middleware("http")
    async def catch_all(request, call_next):
        try:
            return await call_next(request)
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return error_response("internal.error", str(e)[:300])

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            target = FRONTEND_DIST / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")
    return app
