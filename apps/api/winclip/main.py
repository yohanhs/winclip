"""Aplicación FastAPI de WinClip."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from winclip import __version__
from winclip.core.config import Settings, get_settings
from winclip.core.db import init_db
from winclip.routers import accounts, campaigns, clips, events, health, jobs, presets, projects
from winclip.services.events import EventBroadcaster


def create_app(settings: Settings | None = None) -> FastAPI:
    """Crea la app; `settings` permite inyectar una configuración temporal en tests."""
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = init_db(resolved)
        app.state.engine = engine
        broadcaster = EventBroadcaster(engine)
        app.state.broadcaster = broadcaster
        await broadcaster.start()
        try:
            yield
        finally:
            await broadcaster.stop()

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description="API local de WinClip (clipping, jobs y publicación).",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.engine = None
    app.state.broadcaster = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{resolved.web_port}",
            f"http://127.0.0.1:{resolved.web_port}",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router)
    app.include_router(clips.router)
    app.include_router(campaigns.router)
    app.include_router(accounts.router)
    app.include_router(jobs.router)
    app.include_router(presets.router)
    app.include_router(events.router)
    return app


app = create_app()
