"""Motor SQLite, sesiones y arranque de la base de datos (`winclip.db`).

La API y el worker son procesos separados sobre el mismo archivo, así que el motor abre
SQLite en WAL con `busy_timeout` y claves foráneas activas (design, decisión 2). Las
migraciones se aplican con Alembic (`render_as_batch=True` en SQLite) y el workspace por
defecto se garantiza de forma idempotente.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from alembic import command
from winclip.core.config import Settings
from winclip.core.ids import new_ulid
from winclip.core.models import DEFAULT_WORKSPACE_NAME, Workspace, utcnow

APPS_API_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APPS_API_DIR / "alembic.ini"
ALEMBIC_DIR = APPS_API_DIR / "alembic"
MIGRATION_LOCK_FILENAME = ".migrate.lock"


def _register_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


_ENGINES: dict[str, Engine] = {}


def get_engine(database_url: str) -> Engine:
    """Motor cacheado por URL, con los PRAGMA de SQLite ya aplicados."""
    engine = _ENGINES.get(database_url)
    if engine is None:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 5.0},
            pool_pre_ping=True,
        )
        _register_pragmas(engine)
        _ENGINES[database_url] = engine
    return engine


def clear_engine_cache() -> None:
    """Cierra y olvida los motores cacheados (tests con SQLite temporales)."""
    for engine in _ENGINES.values():
        engine.dispose()
    _ENGINES.clear()


def engine_for(settings: Settings) -> Engine:
    """Motor del proyecto; crea el directorio de `STORAGE_DIR` si falta."""
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return get_engine(_database_url(settings))


def _database_url(settings: Settings) -> str:
    url = settings.database_url
    if url:
        return url
    return f"sqlite:///{settings.storage_dir / 'winclip.db'}"


def alembic_config(database_url: str) -> Config:
    """Configuración de Alembic apuntando a `apps/api/alembic` y a la URL dada."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@contextlib.contextmanager
def _migration_lock(storage_dir: Path) -> Iterator[None]:
    """Evita que API y worker migren a la vez sobre el mismo archivo."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    lock_path = storage_dir / MIGRATION_LOCK_FILENAME
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - solo plataformas no POSIX
            yield
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_migrations(database_url: str, *, revision: str = "head") -> None:
    """Aplica las migraciones de Alembic (programático, usado por API, worker y CLI)."""
    command.upgrade(alembic_config(database_url), revision)


def ensure_default_workspace(session: Session) -> Workspace:
    """Devuelve el workspace por defecto, creándolo si no existe (idempotente)."""
    existing = session.exec(
        select(Workspace).where(Workspace.name == DEFAULT_WORKSPACE_NAME)
    ).first()
    if existing is not None:
        return existing

    workspace = Workspace(id=new_ulid(), name=DEFAULT_WORKSPACE_NAME, created_at=utcnow())
    session.add(workspace)
    try:
        session.commit()
    except IntegrityError:
        # Otra instancia lo creó entre el SELECT y el INSERT.
        session.rollback()
        existing = session.exec(
            select(Workspace).where(Workspace.name == DEFAULT_WORKSPACE_NAME)
        ).first()
        if existing is None:  # pragma: no cover - defensivo
            raise
        return existing
    session.refresh(workspace)
    return workspace


def default_workspace_id(session: Session) -> str:
    """Identificador del workspace por defecto."""
    return ensure_default_workspace(session).id


def init_db(settings: Settings) -> Engine:
    """Migra la base de datos y garantiza el workspace por defecto."""
    engine = engine_for(settings)
    with _migration_lock(settings.storage_dir):
        run_migrations(_database_url(settings))
    with Session(engine) as session:
        ensure_default_workspace(session)
    return engine


@contextlib.contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Sesión con commit al salir y rollback ante error."""
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
