"""Entorno de Alembic: `DATABASE_URL` desde `Settings` y modo batch en SQLite."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlmodel import SQLModel

from alembic import context
from winclip.core import models  # noqa: F401  (registra las tablas en el metadata)
from winclip.core.config import Settings

config = context.config
target_metadata = SQLModel.metadata


def _database_url() -> str:
    """URL pasada por `winclip/core/db.py` o derivada de `Settings`."""
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    settings = Settings()
    return settings.database_url or f"sqlite:///{settings.storage_dir / 'winclip.db'}"


def _configure(url: str) -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    """Genera el SQL sin conexión (no se usa en el flujo normal, pero es el estándar)."""
    url = _database_url()
    _configure(url=url)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base real."""
    url = _database_url()
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            # SQLite trae `foreign_keys` desactivado por defecto, así que las
            # recreaciones en modo batch no necesitan desactivarlo a mano.
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=connection.dialect.name == "sqlite",
                compare_type=True,
                compare_server_default=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
