"""Almacenamiento local por proyecto (`docs/architecture.md §5` y protocolo `§8`)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from winclip.core.ids import validate_project_id

SOURCE_DIR = "source"
CLIPS_DIR = "clips"
CLIP_VIDEO_FILENAME = "clip.mp4"
CLIP_THUMB_FILENAME = "thumb.jpg"
AUDIO_DIR = "audio"
TRANSCRIPT_DIR = "transcript"
SELECTION_DIR = "selection"
CACHE_DIR = "cache"
LLM_CACHE_DIR = "llm"
SOURCE_META_FILENAME = "meta.json"
AUDIO_FILENAME = "audio16k.wav"
TRANSCRIPT_FILENAME = "transcript.json"
CANDIDATES_FILENAME = "candidates.json"

_CACHE_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StoragePathError(ValueError):
    """La ruta solicitada quedaría fuera de la raíz de almacenamiento."""


@runtime_checkable
class Storage(Protocol):
    """Interfaz de almacenamiento: local hoy, S3 mañana (`docs/architecture.md §8`)."""

    def path(self, *parts: str) -> Path: ...


class LocalStorage:
    """Almacenamiento en disco bajo `STORAGE_DIR/projects/<project_id>/`."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.projects_dir = self.root / "projects"

    def path(self, *parts: str) -> Path:
        """Devuelve una ruta bajo la raíz, rechazando cualquier escape (`..`, absolutas)."""
        candidate = self.root.joinpath(*parts).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise StoragePathError(f"ruta fuera de STORAGE_DIR: {candidate}")
        return candidate

    def project_dir(self, project_id: str) -> Path:
        """Directorio del proyecto, validando el identificador contra path traversal."""
        return self.path("projects", validate_project_id(project_id))

    def source_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / SOURCE_DIR

    def audio_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / AUDIO_DIR

    def transcript_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / TRANSCRIPT_DIR

    def source_meta_path(self, project_id: str) -> Path:
        return self.source_dir(project_id) / SOURCE_META_FILENAME

    def audio_path(self, project_id: str) -> Path:
        return self.audio_dir(project_id) / AUDIO_FILENAME

    def transcript_path(self, project_id: str) -> Path:
        return self.transcript_dir(project_id) / TRANSCRIPT_FILENAME

    def selection_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / SELECTION_DIR

    def selection_path(self, project_id: str) -> Path:
        """`selection/candidates.json` del proyecto (`docs/architecture.md §6.2`)."""
        return self.selection_dir(project_id) / CANDIDATES_FILENAME

    def clips_dir(self, project_id: str) -> Path:
        """`projects/<project_id>/clips/` (`docs/architecture.md §5`)."""
        return self.project_dir(project_id) / CLIPS_DIR

    def clip_dir(self, project_id: str, clip_id: str) -> Path:
        """`projects/<project_id>/clips/<clip_id>/`, validando ambos identificadores."""
        return self.clips_dir(project_id) / validate_project_id(clip_id)

    def clip_video_path(self, project_id: str, clip_id: str) -> Path:
        return self.clip_dir(project_id, clip_id) / CLIP_VIDEO_FILENAME

    def clip_thumb_path(self, project_id: str, clip_id: str) -> Path:
        return self.clip_dir(project_id, clip_id) / CLIP_THUMB_FILENAME

    def resolve_safe(self, relative: str | Path) -> Path:
        """Resuelve una ruta **relativa** bajo la raíz y rechaza cualquier escape.

        Resuelve symlinks antes de comparar, así que un enlace dentro de `STORAGE_DIR`
        que apunte fuera también se rechaza. Se usa al servir `/file` y `/thumb`.
        """
        candidate = Path(relative)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise StoragePathError(f"ruta no permitida: {relative}")
        resolved = (self.root / candidate).resolve()
        if not resolved.is_relative_to(self.root):
            raise StoragePathError(f"ruta fuera de STORAGE_DIR: {resolved}")
        return resolved

    def llm_cache_dir(self) -> Path:
        return self.path(CACHE_DIR, LLM_CACHE_DIR)

    def llm_cache_path(self, cache_key: str) -> Path:
        """`cache/llm/<sha256>.json`, validando que la clave sea un SHA-256 hexadecimal."""
        if not _CACHE_KEY_PATTERN.fullmatch(cache_key):
            raise StoragePathError(f"clave de caché LLM inválida: {cache_key!r}")
        return self.llm_cache_dir() / f"{cache_key}.json"

    def ensure_project_dirs(self, project_id: str) -> Path:
        """Crea `source/` y `audio/` del proyecto y devuelve su directorio raíz."""
        project = self.project_dir(project_id)
        for directory in (SOURCE_DIR, AUDIO_DIR):
            (project / directory).mkdir(parents=True, exist_ok=True)
        return project

    def write_json_atomic(self, path: Path, payload: BaseModel | dict[str, Any]) -> Path:
        """Escribe JSON con archivo temporal en el mismo directorio + `os.replace`."""
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        descriptor, tmp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return path

    def read_json(self, path: Path) -> dict[str, Any]:
        """Lee un JSON ya escrito por el pipeline (lanza `ValueError` si no es un objeto)."""
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{path} no contiene un objeto JSON")
        return data
