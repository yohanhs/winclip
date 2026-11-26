"""Aplicación FastAPI de WinClip."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from winclip import __version__
from winclip.core.config import get_settings
from winclip.routers import health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="API local de WinClip (clipping, jobs y publicación).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{settings.web_port}",
            f"http://127.0.0.1:{settings.web_port}",
        ],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
