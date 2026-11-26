"""Proveedores LLM falsos, deterministas y sin red para los tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from winclip.llm.types import TokenUsage, parse_json_payload

ResponseItem = str | BaseModel | BaseException | Callable[[str, str, type[BaseModel]], Any]


class FakeLLMProvider:
    """Proveedor guionizado: devuelve respuestas en orden y registra las llamadas."""

    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-1",
        responses: list[ResponseItem] | None = None,
        *,
        available: bool = True,
        usage: TokenUsage | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.available_flag = available
        self.last_usage = usage
        self.calls: list[tuple[str, str, type[BaseModel]]] = []
        self._responses: list[ResponseItem] = list(responses or [])

    def available(self) -> bool:
        return self.available_flag

    def queue(self, *items: ResponseItem) -> FakeLLMProvider:
        self._responses.extend(items)
        return self

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((system, user, schema))
        if not self._responses:
            raise AssertionError(f"{self.name}: no quedan respuestas guionizadas")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item) and not isinstance(item, BaseModel):
            item = item(system, user, schema)
        if isinstance(item, BaseModel):
            return item
        return parse_json_payload(item, schema)


class FakeSelectionProvider(FakeLLMProvider):
    """Genera candidatos deterministas a partir de las líneas `[Uxxxx ...]` del prompt."""

    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-1",
        *,
        score: int = 85,
        candidates_per_request: int = 3,
        skip_lines_containing: tuple[str, ...] = (),
        available: bool = True,
    ) -> None:
        super().__init__(name=name, model=model, available=available)
        self.score = score
        self.candidates_per_request = candidates_per_request
        self.skip_lines_containing = tuple(term.lower() for term in skip_lines_containing)

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((system, user, schema))
        fields = schema.model_fields
        if "ranking" in fields:
            ranking = [
                {"index": index, "score": max(1, self.score - index), "reason": "ranking fake"}
                for index in range(len(_candidate_lines(user)))
            ]
            return schema.model_validate({"ranking": ranking})
        if "candidates" not in fields:
            raise AssertionError(f"esquema no soportado por FakeSelectionProvider: {fields}")

        proposals = []
        usable = [entry for entry in _utterance_entries(user) if not self._skip(entry[2])]
        for number, (start, end, _) in enumerate(usable[: self.candidates_per_request]):
            proposals.append(
                {
                    "start": start,
                    "end": end,
                    "title": f"Clip {number + 1}",
                    "hook": f"Gancho {number + 1}",
                    "description": f"Descripción {number + 1}",
                    "hashtags": ["#shorts"],
                    "score": max(1, self.score - number),
                    "reason": "propuesta fake determinista",
                }
            )
        return schema.model_validate({"candidates": proposals})

    def _skip(self, text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in self.skip_lines_containing)


def _utterance_entries(user: str) -> list[tuple[float, float, str]]:
    """Extrae `(inicio, fin, texto)` de las líneas serializadas de utterances."""
    entries: list[tuple[float, float, str]] = []
    for line in user.splitlines():
        stripped = line.strip()
        if not stripped.startswith("[U") or "]" not in stripped:
            continue
        header = stripped[1 : stripped.index("]")]
        _, _, times = header.partition(" ")
        start_text, _, end_text = times.partition("-")
        entries.append((_parse_timestamp(start_text), _parse_timestamp(end_text), stripped))
    return entries


def _candidate_lines(user: str) -> list[str]:
    return [line for line in user.splitlines() if line.strip().startswith("[C")]


def _parse_timestamp(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
