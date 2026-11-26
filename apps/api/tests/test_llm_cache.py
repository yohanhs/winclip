"""Tests de `winclip.llm.cache`."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from winclip.core.storage import LocalStorage
from winclip.llm.cache import LLMCache, compute_cache_key


class Answer(BaseModel):
    text: str


class OtherAnswer(BaseModel):
    text: str
    score: int = 0


def _storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


def test_cache_key_is_deterministic() -> None:
    first = compute_cache_key(
        logical_model="clip-selection:single:v1",
        system="sistema",
        user="usuario",
        schema=Answer,
    )
    second = compute_cache_key(
        logical_model="clip-selection:single:v1",
        system="sistema",
        user="usuario",
        schema=Answer,
    )

    assert first == second
    assert len(first) == 64
    assert first.islower()


def test_cache_key_changes_with_prompt_model_or_schema() -> None:
    base = compute_cache_key(
        logical_model="clip-selection:single:v1",
        system="sistema",
        user="usuario",
        schema=Answer,
    )

    assert (
        compute_cache_key(
            logical_model="clip-selection:single:v2",
            system="sistema",
            user="usuario",
            schema=Answer,
        )
        != base
    )
    assert (
        compute_cache_key(
            logical_model="clip-selection:single:v1",
            system="sistema",
            user="otro usuario",
            schema=Answer,
        )
        != base
    )
    assert (
        compute_cache_key(
            logical_model="clip-selection:single:v1",
            system="sistema",
            user="usuario",
            schema=OtherAnswer,
        )
        != base
    )


def test_cache_roundtrip_in_storage_cache_dir(tmp_path: Path) -> None:
    cache = LLMCache(_storage(tmp_path))
    key = compute_cache_key(
        logical_model="clip-selection:single:v1",
        system="sistema",
        user="usuario",
        schema=Answer,
    )

    assert cache.load(key) is None

    path = cache.save(
        cache_key=key,
        logical_model="clip-selection:single:v1",
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_tokens=12,
        completion_tokens=4,
        data={"text": "hola"},
    )

    assert path == tmp_path / "storage" / "cache" / "llm" / f"{key}.json"
    assert path.is_file()
    entry = cache.load(key)
    assert entry is not None
    assert entry.provider == "gemini"
    assert entry.data == {"text": "hola"}
    assert entry.created_at.tzinfo is not None

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "cache_key",
        "logical_model",
        "provider",
        "model",
        "created_at",
        "prompt_tokens",
        "completion_tokens",
        "data",
    }


def test_corrupted_cache_entry_is_a_miss(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    cache = LLMCache(storage)
    key = "a" * 64
    path = storage.llm_cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{roto", encoding="utf-8")

    assert cache.load(key) is None


def test_cache_does_not_accept_arbitrary_paths(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    try:
        storage.llm_cache_path("../escape")
    except ValueError as exc:
        assert "inválida" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("se esperaba StoragePathError")
