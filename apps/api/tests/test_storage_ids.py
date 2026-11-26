"""Tests de `core/ids.py` y `core/storage.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from winclip.core.ids import (
    InvalidProjectIdError,
    new_clip_id,
    new_job_id,
    new_project_id,
    validate_project_id,
    validate_ulid,
)
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


def test_resolve_safe_accepts_relative_paths(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    target = storage.path("projects", "p1", "clips", "c1", "clip.mp4")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mp4")

    resolved = storage.resolve_safe("projects/p1/clips/c1/clip.mp4")

    assert resolved == target
    assert storage.resolve_safe(target.relative_to(tmp_path)) == target


@pytest.mark.parametrize(
    "value",
    ["../escape.mp4", "projects/../../escape.mp4", "/etc/passwd", "a/../../b"],
)
def test_resolve_safe_rejects_traversal_and_absolute_paths(tmp_path: Path, value: str) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(StoragePathError):
        storage.resolve_safe(value)


def test_resolve_safe_rejects_symlink_escaping_storage(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    storage.root.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"secreto")
    link = storage.root / "link.mp4"
    link.symlink_to(outside)

    with pytest.raises(StoragePathError):
        storage.resolve_safe("link.mp4")


def test_clip_paths_live_under_project_clips_dir(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    assert (
        storage.clip_video_path("p1", "c1")
        == (tmp_path / "projects" / "p1" / "clips" / "c1" / "clip.mp4").resolve()
    )
    assert storage.clip_thumb_path("p1", "c1").name == "thumb.jpg"


def test_validate_ulid_accepts_generated_ids_and_rejects_others() -> None:
    value = new_project_id()

    assert validate_ulid(value) == value
    assert new_clip_id() != new_job_id()
    for invalid in ("", "abc", "../escape", value + "x", "!" * 26):
        with pytest.raises(InvalidProjectIdError):
            validate_ulid(invalid)
