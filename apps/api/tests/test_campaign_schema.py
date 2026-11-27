"""Tests de `CampaignRules`, validadores estrictos y plantillas ES/EN."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from winclip.rules.schema import (
    CampaignRules,
    RulesFileError,
    RuleViolation,
    load_campaign_templates,
    normalize_hashtags,
    validate_watermark_path,
)


def test_campaign_rules_valid_full_payload() -> None:
    rules = CampaignRules(
        name="  Finanzas Pro  ",
        language="es",
        min_duration=20,
        max_duration=60,
        max_clips=12,
        priority_topics=["ahorro", "Ahorro", "  inversión  "],
        banned_topics=["cripto", ""],
        banned_words=["garantizado", "dinero fácil"],
        required_keywords=["inversión"],
        tone="  educativo  ",
        hook_max_seconds=3,
        cta_text="  Suscríbete hoy  ",
        hashtags=["finanzas", "#Finanzas", "# ahorro largo ", "##"],
        subtitle_preset="bold-yellow",
        watermark_path="campaigns/watermarks/01hzy1234567890abcdef12345.png",
        target_platforms=["youtube", "tiktok", "youtube"],
        extra_instructions="  Sin relleno  ",
    )

    assert rules.name == "Finanzas Pro"
    assert rules.priority_topics == ["ahorro", "inversión"]
    assert rules.banned_topics == ["cripto"]
    assert rules.tone == "educativo"
    assert rules.cta_text == "Suscríbete hoy"
    assert rules.hashtags == ["#finanzas", "#ahorrolargo"]
    assert rules.subtitle_preset == "bold-yellow"
    assert rules.watermark_path == "campaigns/watermarks/01hzy1234567890abcdef12345.png"
    assert rules.target_platforms == ["youtube", "tiktok"]
    assert rules.extra_instructions == "Sin relleno"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"name": "a" * 121},
        {"min_duration": 4},
        {"max_duration": 181},
        {"min_duration": 60, "max_duration": 60},
        {"min_duration": 70, "max_duration": 40},
        {"max_clips": 0},
        {"max_clips": 51},
        {"hook_max_seconds": 0.5},
        {"hook_max_seconds": 16},
        {"min_duration": 5, "max_duration": 30, "hook_max_seconds": 6},
        {"subtitle_preset": "no-existe-preset"},
        {"watermark_path": "/etc/passwd.png"},
        {"watermark_path": "../secret.png"},
        {"watermark_path": "campaigns/../secret.png"},
        {"watermark_path": "projects/123/logo.png"},
        {"watermark_path": "campaigns/watermarks/logo.jpg"},
        {"watermark_path": "campaigns\\watermarks\\logo.png"},
    ],
)
def test_campaign_rules_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CampaignRules(**overrides)


def test_watermark_path_accepts_png_and_webp_under_campaigns() -> None:
    assert validate_watermark_path(None) is None
    assert validate_watermark_path("   ") is None
    assert (
        validate_watermark_path("campaigns/watermarks/brand.PNG")
        == "campaigns/watermarks/brand.PNG"
    )
    assert (
        validate_watermark_path("campaigns/watermarks/brand.webp")
        == "campaigns/watermarks/brand.webp"
    )


def test_normalize_hashtags_deduplicates_and_formats() -> None:
    assert normalize_hashtags(["shorts", "#Shorts", " mi clip ", "#", ""]) == [
        "#shorts",
        "#miclip",
    ]


def test_rule_violation_schema() -> None:
    violation = RuleViolation(
        code="banned_word_present",
        field="banned_words",
        severity="error",
        message="Contiene 'garantizado'",
    )
    assert violation.severity == "error"


def test_load_campaign_templates_es_and_en() -> None:
    templates = load_campaign_templates()
    assert len(templates) >= 4
    languages = [tpl.language for tpl in templates]
    assert languages.count("es") >= 2
    assert languages.count("en") >= 2
    ids = [tpl.id for tpl in templates]
    assert len(ids) == len(set(ids))
    for tpl in templates:
        assert tpl.rules.name
        assert tpl.rules.hashtags
        assert tpl.rules.cta_text
        assert tpl.rules.subtitle_preset is not None


def test_load_campaign_templates_rejects_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{bad json", encoding="utf-8")
    with pytest.raises(RulesFileError, match="no se pudo leer"):
        load_campaign_templates(tmp_path)


def test_load_campaign_templates_rejects_invalid_rules(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "title": "Bad",
                "description": "Invalid",
                "language": "es",
                "rules": {"min_duration": 2, "max_duration": 10},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RulesFileError, match="plantilla inválida"):
        load_campaign_templates(tmp_path)
