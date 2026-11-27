"""Tests de `winclip.rules.parser` con proveedor LLM simulado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from winclip.core.config import Settings
from winclip.llm.router import LLMRouter
from winclip.llm.types import LLMError
from winclip.rules.parser import BriefParseError, parse_campaign_brief


class _StaticProvider:
    def __init__(self, payload: dict[str, Any] | Exception, *, name: str = "fake") -> None:
        self.name = name
        self.model = "fake-1"
        self._payload = payload
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return True

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((system, user))
        if isinstance(self._payload, Exception):
            raise self._payload
        return schema.model_validate(self._payload)


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, storage_dir=tmp_path / "storage")


def _router(settings: Settings, provider: _StaticProvider) -> LLMRouter:
    return LLMRouter(
        settings,
        {provider.name: provider},
        sleep_fn=lambda _s: None,
        jitter_fn=lambda: 0.0,
    )


def test_parse_complete_brief_es(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    brief = (
        "Campaña Podcast Finanzas ES: clips de 25 a 55 segundos, máximo 8 clips, "
        "hook de 3 segundos, tono educativo y directo, subtítulos hormozi, "
        "plataformas YouTube y TikTok, hashtags #finanzas #shorts, "
        "prohibido decir garantizado."
    )
    provider = _StaticProvider(
        {
            "rules": {
                "name": "Podcast Finanzas ES",
                "language": "es",
                "min_duration": 25,
                "max_duration": 55,
                "max_clips": 8,
                "banned_words": ["garantizado"],
                "tone": "educativo y directo",
                "hook_max_seconds": 3,
                "hashtags": ["finanzas", "#shorts"],
                "subtitle_preset": "hormozi",
                "target_platforms": ["youtube", "tiktok"],
            },
            "inferred_fields": [],
            "warnings": [],
        }
    )

    draft = parse_campaign_brief(brief, settings=settings, router=_router(settings, provider))

    assert draft.provider == "fake:fake-1"
    assert draft.rules.name == "Podcast Finanzas ES"
    assert draft.rules.language == "es"
    assert draft.rules.min_duration == 25
    assert draft.rules.max_duration == 55
    assert draft.rules.hashtags == ["#finanzas", "#shorts"]
    assert draft.rules.subtitle_preset == "hormozi"
    assert draft.inferred_fields == []
    assert draft.warnings == []


def test_parse_partial_brief_marks_inferred_and_sanitizes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    brief = "Need English clips with #creator and never say scam."
    provider = _StaticProvider(
        {
            "rules": {
                "name": "Creator EN",
                "language": "en",
                "min_duration": 20,
                "max_duration": 60,
                "max_clips": 10,
                "banned_words": ["scam"],
                "tone": "energetic and bold",
                "hook_max_seconds": 3,
                "hashtags": ["#creator"],
                "subtitle_preset": "invented-preset",
                "watermark_path": "/etc/passwd.png",
                "target_platforms": ["youtube"],
            },
            "inferred_fields": ["tone"],
            "warnings": [],
        }
    )

    draft = parse_campaign_brief(brief, settings=settings, router=_router(settings, provider))

    assert draft.rules.subtitle_preset is None
    assert draft.rules.watermark_path is None
    assert "tone" in draft.inferred_fields
    assert "min_duration" in draft.inferred_fields
    assert "max_duration" in draft.inferred_fields
    assert "hook_max_seconds" in draft.inferred_fields
    assert "subtitle_preset" in draft.inferred_fields
    assert "target_platforms" in draft.inferred_fields
    assert len(draft.warnings) >= 2


def test_parse_brief_provider_failure_raises_recoverable_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = _StaticProvider(LLMError("timeout"))

    with pytest.raises(BriefParseError, match="No se pudo analizar el brief"):
        parse_campaign_brief(
            "Brief de prueba",
            settings=settings,
            router=_router(settings, provider),
            use_cache=False,
        )


def test_parse_empty_brief_raises_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(BriefParseError, match="vacío"):
        parse_campaign_brief("   ", settings=settings)
