"""Identificadores de proyecto: ULID en minúsculas (`docs/architecture.md §5`)."""

from __future__ import annotations

import re

from ulid import ULID

# Identificador seguro para usar como nombre de carpeta: sin `/`, `..` ni mayúsculas.
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
# ULID canónico en minúsculas (Crockford base32) tal como lo emite `python-ulid`.
_ULID_PATTERN = re.compile(r"^[0-9a-hjkmnp-tv-z]{26}$")


class InvalidProjectIdError(ValueError):
    """El identificador no cumple el formato permitido."""


def new_ulid() -> str:
    """Genera un ULID ordenable cronológicamente y lo devuelve en minúsculas."""
    return str(ULID()).lower()


def new_project_id() -> str:
    """Identificador de proyecto: un ULID en minúsculas."""
    return new_ulid()


def new_clip_id() -> str:
    """Identificador de clip: un ULID en minúsculas."""
    return new_ulid()


def new_job_id() -> str:
    """Identificador de trabajo de la cola: un ULID en minúsculas."""
    return new_ulid()


def validate_ulid(value: str) -> str:
    """Valida un ULID (26 caracteres Crockford en minúsculas) y lo devuelve."""
    if not isinstance(value, str) or not _ULID_PATTERN.fullmatch(value):
        raise InvalidProjectIdError(f"ULID inválido: {value!r}")
    return value


def validate_project_id(project_id: str) -> str:
    """Valida un `project_id` explícito y lo devuelve sin cambios.

    Se usa tanto en la CLI como en `LocalStorage` para impedir rutas como `../escape`.
    """
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise InvalidProjectIdError(
            f"project_id inválido: {project_id!r}; usa de 2 a 64 caracteres "
            "[a-z0-9_-] empezando por letra o dígito"
        )
    return project_id
