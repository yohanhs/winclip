"""Caché determinista de respuestas LLM en `STORAGE_DIR/cache/llm/<sha256>.json`."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from winclip.core.storage import LocalStorage


class LLMCacheEntry(BaseModel):
    """Contenido de un archivo de caché; nunca incluye claves de API."""

    model_config = ConfigDict(extra="forbid")

    cache_key: str
    logical_model: str
    provider: str
    model: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    data: dict[str, Any]


def compute_cache_key(
    *,
    logical_model: str,
    system: str,
    user: str,
    schema: type[BaseModel],
) -> str:
    """SHA-256 del JSON canónico de (modelo lógico, prompt, esquema)."""
    payload = {
        "logical_model": logical_model,
        "system": system,
        "user": user,
        "schema": schema.model_json_schema(),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LLMCache:
    """Lectura/escritura atómica de entradas de caché sobre `LocalStorage`."""

    def __init__(self, storage: LocalStorage) -> None:
        self.storage = storage

    def load(self, cache_key: str) -> LLMCacheEntry | None:
        """Devuelve la entrada o `None` si no existe, está corrupta o no coincide."""
        path = self.storage.llm_cache_path(cache_key)
        if not path.is_file():
            return None
        try:
            entry = LLMCacheEntry.model_validate(self.storage.read_json(path))
        except (OSError, ValueError, ValidationError):
            return None
        if entry.cache_key != cache_key:
            return None
        return entry

    def save(
        self,
        *,
        cache_key: str,
        logical_model: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        data: dict[str, Any],
    ) -> Path:
        """Escribe la entrada con `write_json_atomic` y devuelve su ruta."""
        entry = LLMCacheEntry(
            cache_key=cache_key,
            logical_model=logical_model,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            data=data,
        )
        return self.storage.write_json_atomic(self.storage.llm_cache_path(cache_key), entry)
