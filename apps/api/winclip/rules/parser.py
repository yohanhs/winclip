"""Parseo asistido de briefs en texto libre (ES/EN) a `CampaignRules` vía `LLMRouter`."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from winclip.core.config import Settings, get_settings
from winclip.llm.prompts import load_prompt
from winclip.llm.router import LLMRouter
from winclip.llm.types import LLMError
from winclip.pipeline.subtitles.presets import available_presets, list_presets
from winclip.rules.schema import CampaignRules, normalize_hashtags
from winclip.rules.validator import normalize_for_match

VALID_RULE_FIELDS = frozenset(CampaignRules.model_fields.keys())
VALID_PLATFORMS = frozenset({"youtube", "tiktok", "instagram"})
VALID_LANGUAGES = frozenset({"es", "en", "auto"})

_DURATION_HINT = re.compile(
    r"\b(\d{1,3}\s*(?:s|sec|secs|seg|segs|segundo|segundos|second|seconds|min|minuto|minutos)"
    r"|duraci[oó]n|duration|entre\s+\d+\s+y\s+\d+|\d+\s*[-\u2013]\s*\d+)\b",
    re.IGNORECASE,
)
_HOOK_HINT = re.compile(r"\b(hook|gancho|primeros?\s+\d+\s*(?:s|seg|sec))\b", re.IGNORECASE)
_CLIPS_HINT = re.compile(r"\b(clips?|shorts?|reels?|m[aá]ximo|max)\b", re.IGNORECASE)
_PRESET_HINT = re.compile(
    r"\b(subt[ií]tulos?|captions?|preset|hormozi|mrbeast|bold[- ]yellow|clean[- ]white)\b",
    re.IGNORECASE,
)
_PLATFORM_HINTS = {
    "youtube": re.compile(r"\b(youtube|yt|shorts)\b", re.IGNORECASE),
    "tiktok": re.compile(r"\b(tiktok|tik\s*tok)\b", re.IGNORECASE),
    "instagram": re.compile(r"\b(instagram|ig|reels)\b", re.IGNORECASE),
}


class BriefParseError(RuntimeError):
    """Error recuperable al analizar un brief en texto libre."""


class _LLMRawRules(BaseModel):
    """Esquema tolerante para recibir la salida del LLM antes de sanitizarla."""

    model_config = ConfigDict(extra="ignore")

    name: str = "Nueva campaña"
    language: str = "auto"
    min_duration: float = 20
    max_duration: float = 60
    max_clips: int | None = 10
    priority_topics: list[str] = Field(default_factory=list)
    banned_topics: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    tone: str | None = None
    hook_max_seconds: float = 3
    cta_text: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    subtitle_preset: str | None = None
    watermark_path: str | None = None
    target_platforms: list[str] = Field(default_factory=list)
    extra_instructions: str | None = None


class _LLMParseResponse(BaseModel):
    """Respuesta cruda del LLM para `parse_campaign_v1`."""

    model_config = ConfigDict(extra="ignore")

    rules: _LLMRawRules
    inferred_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedCampaignDraft(BaseModel):
    """Propuesta validada devuelta por `POST /api/campaigns/parse` (sin persistir)."""

    model_config = ConfigDict(extra="forbid")

    rules: CampaignRules
    inferred_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str = Field(min_length=1)


def _add_unique(target: list[str], item: str) -> None:
    if item not in target:
        target.append(item)


def _sanitize_rules(
    raw: _LLMRawRules,
    *,
    inferred: list[str],
    warnings: list[str],
) -> CampaignRules:
    presets = set(list_presets())

    name = " ".join(str(raw.name or "").split())[:120]
    if not name:
        name = "Nueva campaña"
        _add_unique(inferred, "name")

    language = str(raw.language or "auto").strip().lower()
    if language not in VALID_LANGUAGES:
        warnings.append(f"Idioma '{raw.language}' no reconocido; se ajustó a 'auto'.")
        language = "auto"
        _add_unique(inferred, "language")

    min_dur = float(raw.min_duration)
    max_dur = float(raw.max_duration)
    if min_dur < 5 or min_dur > 179:
        warnings.append(f"min_duration ({min_dur:g}s) fuera de rango [5, 179]; se ajustó.")
        min_dur = max(5.0, min(179.0, min_dur))
        _add_unique(inferred, "min_duration")
    if max_dur < 6 or max_dur > 180:
        warnings.append(f"max_duration ({max_dur:g}s) fuera de rango [6, 180]; se ajustó.")
        max_dur = max(6.0, min(180.0, max_dur))
        _add_unique(inferred, "max_duration")
    if max_dur <= min_dur:
        warnings.append("max_duration debía ser mayor que min_duration; se ajustó automáticamente.")
        max_dur = min(180.0, max(min_dur + 10.0, 60.0))
        if max_dur <= min_dur:
            min_dur = max(5.0, max_dur - 1.0)
        _add_unique(inferred, "max_duration")

    max_clips = raw.max_clips
    if max_clips is not None and not (1 <= max_clips <= 50):
        warnings.append(f"max_clips ({max_clips}) fuera de rango [1, 50]; se ajustó.")
        max_clips = max(1, min(50, max_clips))
        _add_unique(inferred, "max_clips")

    hook_max = float(raw.hook_max_seconds)
    if hook_max < 1 or hook_max > 15 or hook_max > min_dur:
        max_allowed = min(15, min_dur)
        warnings.append(
            f"hook_max_seconds ({hook_max:g}s) ajustado al rango permitido [1, {max_allowed:g}]."
        )
        hook_max = max(1.0, min(15.0, min_dur, hook_max))
        _add_unique(inferred, "hook_max_seconds")

    preset = (raw.subtitle_preset or "").strip() or None
    if preset is not None and preset not in presets:
        warnings.append(
            f"Preset de subtítulos '{preset}' no existe; se dejó vacío para revisión manual."
        )
        preset = None
        _add_unique(inferred, "subtitle_preset")

    if raw.watermark_path:
        warnings.append(
            "La marca de agua debe subirse como archivo PNG/WebP desde el editor de campaña."
        )

    platforms: list[str] = []
    for plat in raw.target_platforms:
        normalized = str(plat).strip().lower()
        if normalized in VALID_PLATFORMS and normalized not in platforms:
            platforms.append(normalized)

    payload: dict[str, Any] = {
        "name": name,
        "language": language,
        "min_duration": round(min_dur, 2),
        "max_duration": round(max_dur, 2),
        "max_clips": max_clips,
        "priority_topics": list(raw.priority_topics),
        "banned_topics": list(raw.banned_topics),
        "banned_words": list(raw.banned_words),
        "required_keywords": list(raw.required_keywords),
        "tone": (raw.tone or "").strip()[:120] or None,
        "hook_max_seconds": round(hook_max, 2),
        "cta_text": (raw.cta_text or "").strip()[:200] or None,
        "hashtags": normalize_hashtags(list(raw.hashtags)),
        "subtitle_preset": preset,
        "watermark_path": None,
        "target_platforms": platforms,
        "extra_instructions": (raw.extra_instructions or "").strip()[:2000] or None,
    }
    return CampaignRules.model_validate(payload)


def _post_verify_inferred(
    source_text: str,
    rules: CampaignRules,
    inferred: list[str],
) -> list[str]:
    """Completa `inferred_fields` cuando el brief no respalda heurísticamente campos sugeridos."""
    result = [field for field in inferred if field in VALID_RULE_FIELDS]
    normalized_source = normalize_for_match(source_text)

    if not _DURATION_HINT.search(source_text):
        _add_unique(result, "min_duration")
        _add_unique(result, "max_duration")

    if not _HOOK_HINT.search(source_text):
        _add_unique(result, "hook_max_seconds")

    if rules.subtitle_preset is not None and not _PRESET_HINT.search(source_text):
        _add_unique(result, "subtitle_preset")

    if rules.tone:
        tone_words = [
            word
            for word in re.findall(r"[a-z0-9]+", normalize_for_match(rules.tone))
            if len(word) > 3
        ]
        if tone_words and not any(word in normalized_source for word in tone_words):
            _add_unique(result, "tone")

    if rules.max_clips is not None and not _CLIPS_HINT.search(source_text):
        _add_unique(result, "max_clips")

    if rules.target_platforms and not any(
        _PLATFORM_HINTS[platform].search(source_text) for platform in rules.target_platforms
    ):
        _add_unique(result, "target_platforms")

    deduped: list[str] = []
    for field in result:
        _add_unique(deduped, field)
    return deduped


def parse_campaign_brief(
    source_text: str,
    *,
    settings: Settings | None = None,
    router: LLMRouter | None = None,
    use_cache: bool = True,
) -> ParsedCampaignDraft:
    """Convierte un brief en texto libre ES/EN en `ParsedCampaignDraft` sin persistir."""
    cleaned = source_text.strip()
    if not cleaned:
        raise BriefParseError("el brief no puede estar vacío")

    resolved_settings = settings or get_settings()
    active_router = router or LLMRouter(resolved_settings)
    template = load_prompt("parse_campaign_v1")
    system = template.render(available_presets=available_presets())

    try:
        llm_result = active_router.complete_json(
            system,
            cleaned,
            _LLMParseResponse,
            logical_model=template.logical_model,
            use_cache=use_cache,
        )
    except LLMError as exc:
        raise BriefParseError(
            f"No se pudo analizar el brief con los proveedores LLM configurados: {exc}"
        ) from exc

    inferred = [field for field in llm_result.data.inferred_fields if field in VALID_RULE_FIELDS]
    warnings = [item.strip() for item in llm_result.data.warnings if item.strip()]
    rules = _sanitize_rules(llm_result.data.rules, inferred=inferred, warnings=warnings)
    verified_inferred = _post_verify_inferred(cleaned, rules, inferred)

    return ParsedCampaignDraft(
        rules=rules,
        inferred_fields=verified_inferred,
        warnings=warnings,
        provider=llm_result.provider_id,
    )
