"""Validación post-LLM de las reglas de campaña (duración, palabras y keywords)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from winclip.rules.schema import CampaignRules, RuleViolation


def _term_pattern(term: str) -> re.Pattern[str] | None:
    """Patrón insensible a mayúsculas con límites de palabra (soporta frases)."""
    parts = [re.escape(part) for part in term.split()]
    if not parts:
        return None
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def find_banned_words(text: str, banned_words: Sequence[str]) -> list[str]:
    """Devuelve las palabras/frases prohibidas presentes en `text` (sin duplicados)."""
    found: list[str] = []
    for term in banned_words:
        pattern = _term_pattern(term.strip())
        if pattern is not None and pattern.search(text) and term not in found:
            found.append(term)
    return found


def find_required_keywords(text: str, required_keywords: Sequence[str]) -> list[str]:
    """Devuelve las palabras clave requeridas que sí aparecen en `text`."""
    found: list[str] = []
    for term in required_keywords:
        pattern = _term_pattern(term.strip())
        if pattern is not None and pattern.search(text) and term not in found:
            found.append(term)
    return found


def missing_required_keywords(text: str, required_keywords: Sequence[str]) -> list[str]:
    """Palabras clave requeridas ausentes del texto (vacío si no hay ninguna regla)."""
    present = set(find_required_keywords(text, required_keywords))
    return [term for term in required_keywords if term not in present]


def duration_allowed(start: float, end: float, rules: CampaignRules) -> bool:
    """`min_duration <= end - start <= max_duration`."""
    duration = end - start
    return rules.min_duration <= duration <= rules.max_duration


def build_candidate_text(
    clip_text: str,
    *,
    title: str = "",
    hook: str = "",
    description: str = "",
) -> str:
    """Texto sobre el que se validan `banned_words` y `required_keywords`."""
    return "\n".join(part for part in (clip_text, title, hook, description) if part)


@dataclass(frozen=True)
class CandidateValidation:
    """Resultado de validar el texto de un candidato contra las reglas."""

    banned_words: list[str] = field(default_factory=list)
    violations: list[RuleViolation] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        """Un candidato con palabras prohibidas se descarta (filtro duro)."""
        return bool(self.banned_words)


def validate_candidate_text(text: str, rules: CampaignRules) -> CandidateValidation:
    """Aplica `banned_words` (descarte) y `required_keywords` (aviso estructurado)."""
    banned = find_banned_words(text, rules.banned_words)
    violations: list[RuleViolation] = []
    missing = missing_required_keywords(text, rules.required_keywords)
    if missing:
        violations.append(
            RuleViolation(
                code="missing_required_keyword",
                field="required_keywords",
                severity="warning",
                message=(
                    "el clip no contiene ninguna de las palabras clave requeridas: "
                    + ", ".join(missing)
                ),
            )
        )
    return CandidateValidation(banned_words=banned, violations=violations)
