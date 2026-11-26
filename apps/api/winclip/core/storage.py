"""Almacenamiento local por proyecto (`docs/architecture.md §5` y protocolo `§8`)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from winclip.core.ids import validate_project_id

SOURCE_DIR = "source"
AUDIO_DIR = "audio"
TRANSCRIPT_DIR = "transcript"
SOURCE_META_FILENAME = "meta.json"
AUDIO_FILENAME = "audio16k.wav"
TRANSCRIPT_FILENAME = "transcript.json"


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
