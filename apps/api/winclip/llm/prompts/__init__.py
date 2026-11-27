"""Carga de prompts versionados de selección de clips.

Cada archivo `*.md` vive dentro del paquete y su sufijo `_vN` define la versión que
se incorpora al `logical_model` de la caché, de modo que editar un prompt la invalida.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

_KIND_BY_PROMPT = {
    "select_single": "single",
    "select_chunk": "chunk",
    "select_rank": "rank",
}


class PromptError(RuntimeError):
    """El prompt solicitado no existe o no se puede renderizar."""


@dataclass(frozen=True)
class PromptTemplate:
    """Prompt cargado desde disco con su nombre y versión."""

    name: str
    version: str
    text: str

    def render(self, **values: object) -> str:
        try:
            return self.text.format(**values)
        except KeyError as exc:
            raise PromptError(f"falta el valor {exc.args[0]!r} para el prompt {self.name}") from exc

    @property
    def logical_model(self) -> str:
        """Identificador lógico para la caché, p. ej. `clip-selection:single:v1`."""
        if self.name == "parse_campaign":
            return f"campaign-parser:v{self.version}"
        kind = _KIND_BY_PROMPT.get(self.name, self.name)
        return f"clip-selection:{kind}:v{self.version}"


def load_prompt(name: str) -> PromptTemplate:
    """Lee `prompts/<name>.md` y extrae la versión del sufijo `_vN`."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"no existe el prompt {name!r} en {PROMPTS_DIR}")
    stem = path.stem
    base, _, suffix = stem.rpartition("_v")
    if base and suffix.isdigit():
        name, version = base, suffix
    else:
        name, version = stem, "1"
    return PromptTemplate(name=name, version=version, text=path.read_text(encoding="utf-8"))
