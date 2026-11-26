"""Tests de las migraciones Alembic (upgrade, downgrade y lectura de `DATABASE_URL`)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic import command
from winclip.core.config import Settings
from winclip.core.db import alembic_config

CORE_TABLES = {"workspace", "project", "clip", "job", "job_event"}


def _url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'migraciones.db'}"


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_roundtrip(tmp_path: Path) -> None:
    url = _url(tmp_path)

    command.upgrade(alembic_config(url), "head")
    tables = _tables(url)
    assert tables >= CORE_TABLES
    assert "alembic_version" in tables

    command.downgrade(alembic_config(url), "base")
    assert not (CORE_TABLES & _tables(url))

    command.upgrade(alembic_config(url), "head")
    assert _tables(url) >= CORE_TABLES


def test_queue_and_event_indexes_exist(tmp_path: Path) -> None:
    url = _url(tmp_path)
    command.upgrade(alembic_config(url), "head")

    engine = create_engine(url)
    try:
        job_indexes = {index["name"] for index in inspect(engine).get_indexes("job")}
        event_indexes = {index["name"] for index in inspect(engine).get_indexes("job_event")}
    finally:
        engine.dispose()

    assert "ix_job_status_next_run_at_created_at" in job_indexes
    assert "ix_job_event_project_id_id" in event_indexes


def test_env_reads_database_url_from_settings(monkeypatch, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    database = storage / "desde-settings.db"
    monkeypatch.setenv("STORAGE_DIR", str(storage))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")

    config = alembic_config("")
    config.set_main_option("sqlalchemy.url", "")
    command.upgrade(config, "head")

    assert database.is_file()
    assert _tables(f"sqlite:///{database}") >= CORE_TABLES
    assert Settings().database_url == f"sqlite:///{database}"
