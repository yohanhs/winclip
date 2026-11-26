"""Tests de `core/ids.py` y `core/storage.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from winclip.core.ids import InvalidProjectIdError, new_project_id, validate_project_id
from winclip.core.storage import LocalStorage, StoragePathError


def test_new_project_id_is_sortable_lowercase_ulid() -> None:
    first = new_project_id()
    second = new_project_id()

    assert len(first) == 26
    assert first == first.lower()
    assert first.isalnum()
    assert first < second
    assert validate_project_id(first) == first


@pytest.mark.parametrize(
    "value",
    ["../escape", "", "a", "ABCdef", "-abc", "a/b", "con espacio", "ñandu", "a" * 65],
)
def test_validate_project_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(InvalidProjectIdError):
        validate_project_id(value)


def test_validate_project_id_accepts_safe_value() -> None:
    assert validate_project_id("proyecto_01") == "proyecto_01"


def test_storage_layout_matches_architecture(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    project = storage.ensure_project_dirs("proyecto-01")

    assert project == (tmp_path / "projects" / "proyecto-01").resolve()
    assert (project / "source").is_dir()
    assert (project / "audio").is_dir()
    assert storage.source_meta_path("proyecto-01") == project / "source" / "meta.json"
    assert storage.audio_path("proyecto-01") == project / "audio" / "audio16k.wav"
    assert storage.transcript_path("proyecto-01") == project / "transcript" / "transcript.json"


def test_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(StoragePathError):
        storage.path("..", "escape")
    with pytest.raises(InvalidProjectIdError):
        storage.project_dir("../escape")


def test_write_json_atomic_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = storage.path("projects", "p1", "source", "meta.json")

    storage.write_json_atomic(path, {"b": 1, "a": "ñ"})

    assert storage.read_json(path) == {"a": "ñ", "b": 1}
    assert list(path.parent.iterdir()) == [path]


def test_write_json_atomic_rejects_non_object_payload(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = tmp_path / "lista.json"
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(ValueError, match="objeto JSON"):
        storage.read_json(path)
