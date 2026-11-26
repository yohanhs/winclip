"""Dependencias compartidas por los routers (settings, motor y sesión)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlmodel import Session

from winclip.core.config import Settings


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_engine_dep(request: Request) -> Engine:
    return request.app.state.engine


def get_session(
    engine: Annotated[Engine, Depends(get_engine_dep)],
) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
EngineDep = Annotated[Engine, Depends(get_engine_dep)]
SessionDep = Annotated[Session, Depends(get_session)]
