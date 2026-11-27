"""Validación determinista de candidatos y clips contra `CampaignRules`."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from winclip.rules.schema import CampaignRules, RuleViolation, normalize_hashtags

HOOK_WORDS_PER_SECOND = 2.8


def normalize_for_match(text: str) -> str:
    """Normaliza a minúsculas sin tildes/marcas diacríticas para coincidencia léxica."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.casefold()


def _term_pattern(term: str) -> re.Pattern[str] | None:
    """Patrón insensible a mayúsculas/tildes con límites de palabra (soporta frases)."""
    normalized = normalize_for_match(term)
    parts = [re.escape(part) for part in normalized.split()]
    if not parts:
        return None
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)")


def find_banned_words(text: str, banned_words: Sequence[str]) -> list[str]:
    """Devuelve las palabras/frases prohibidas presentes en `text` (sin duplicados)."""
    normalized_text = normalize_for_match(text)
    found: list[str] = []
    for term in banned_words:
        pattern = _term_pattern(term.strip())
        if pattern is not None and pattern.search(normalized_text) and term not in found:
            found.append(term)
    return found


def find_required_keywords(text: str, required_keywords: Sequence[str]) -> list[str]:
    """Devuelve las palabras clave requeridas que sí aparecen en `text`."""
    normalized_text = normalize_for_match(text)
    found: list[str] = []
    for term in required_keywords:
        pattern = _term_pattern(term.strip())
        if pattern is not None and pattern.search(normalized_text) and term not in found:
            found.append(term)
    return found


def missing_required_keywords(text: str, required_keywords: Sequence[str]) -> list[str]:
    """Palabras clave requeridas ausentes del texto (vacío si no hay ninguna regla)."""
    present = set(find_required_keywords(text, required_keywords))
    return [term for term in required_keywords if term not in present]


def missing_required_hashtags(
    hashtags: Sequence[str],
    required_hashtags: Sequence[str],
) -> list[str]:
    """Hashtags de la campaña ausentes en el candidato (sin distinción de tildes/caso)."""
    normalized_present = {normalize_for_match(tag) for tag in normalize_hashtags(list(hashtags))}
    missing: list[str] = []
    for required in normalize_hashtags(list(required_hashtags)):
        if normalize_for_match(required) not in normalized_present:
            missing.append(required)
    return missing


def duration_allowed(start: float, end: float, rules: CampaignRules) -> bool:
    """`min_duration <= end - start <= max_duration`."""
    duration = end - start
    return rules.min_duration <= duration <= rules.max_duration


def estimate_hook_seconds(hook: str) -> float:
    """Estima la duración hablada del hook a partir de su conteo de palabras."""
    words = [word for word in hook.split() if word.strip()]
    if not words:
        return 0.0
    return round(len(words) / HOOK_WORDS_PER_SECOND, 2)


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


def validate_candidate(
    *,
    start: float,
    end: float,
    rules: CampaignRules,
    clip_text: str = "",
    title: str = "",
    hook: str = "",
    description: str = "",
    hashtags: Sequence[str] = (),
    hook_duration_sec: float | None = None,
    existing_violations: Sequence[RuleViolation] = (),
) -> list[RuleViolation]:
    """Evalúa un candidato/clip contra todas las reglas verificables de `CampaignRules`."""
    violations: list[RuleViolation] = []
    duration = round(end - start, 3)

    if duration < rules.min_duration:
        violations.append(
            RuleViolation(
                code="duration_out_of_range",
                field="min_duration",
                severity="error",
                message=(
                    f"La duración ({duration:.1f}s) es menor que el mínimo "
                    f"permitido ({rules.min_duration:g}s)"
                ),
            )
        )
    elif duration > rules.max_duration:
        violations.append(
            RuleViolation(
                code="duration_out_of_range",
                field="max_duration",
                severity="error",
                message=(
                    f"La duración ({duration:.1f}s) supera el máximo "
                    f"permitido ({rules.max_duration:g}s)"
                ),
            )
        )

    combined = build_candidate_text(clip_text, title=title, hook=hook, description=description)

    for word in find_banned_words(combined, rules.banned_words):
        violations.append(
            RuleViolation(
                code="banned_word_present",
                field="banned_words",
                severity="error",
                message=f"Contiene la palabra prohibida '{word}'",
            )
        )

    missing_kw = missing_required_keywords(combined, rules.required_keywords)
    if missing_kw:
        violations.append(
            RuleViolation(
                code="missing_required_keyword",
                field="required_keywords",
                severity="warning",
                message=(
                    "Faltan palabras clave obligatorias de la campaña: " + ", ".join(missing_kw)
                ),
            )
        )

    missing_tags = missing_required_hashtags(hashtags, rules.hashtags)
    if missing_tags:
        violations.append(
            RuleViolation(
                code="missing_required_hashtag",
                field="hashtags",
                severity="warning",
                message="Faltan hashtags de la campaña: " + ", ".join(missing_tags),
            )
        )

    estimated_hook = (
        hook_duration_sec if hook_duration_sec is not None else estimate_hook_seconds(hook)
    )
    if hook.strip() and estimated_hook > rules.hook_max_seconds:
        violations.append(
            RuleViolation(
                code="hook_too_long",
                field="hook_max_seconds",
                severity="warning",
                message=(
                    f"El hook estimado ({estimated_hook:.1f}s) supera el máximo "
                    f"de {rules.hook_max_seconds:g}s"
                ),
            )
        )

    seen = {(item.code, item.field, item.message) for item in violations}
    for extra in existing_violations:
        key = (extra.code, extra.field, extra.message)
        if key not in seen:
            seen.add(key)
            violations.append(extra)

    return violations
