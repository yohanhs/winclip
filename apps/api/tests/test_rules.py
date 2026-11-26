"""Tests de `winclip.rules` (esquema §6.4 y validador post-LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from winclip.rules.schema import CampaignRules, RulesFileError, load_rules
from winclip.rules.validator import (
    build_candidate_text,
    duration_allowed,
    find_banned_words,
    missing_required_keywords,
    validate_candidate_text,
)


def _write_rules(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_defaults_are_safe() -> None:
    rules = CampaignRules()

    assert rules.name == "default"
    assert rules.language == "auto"
    assert rules.min_duration == 20
    assert rules.max_duration == 60
    assert rules.max_clips is None
    assert rules.priority_topics == []
    assert rules.banned_words == []
    assert rules.required_keywords == []
    assert rules.hook_max_seconds == 3


def test_load_rules_valid_file(tmp_path: Path) -> None:
    path = _write_rules(
        tmp_path,
        {
            "name": "canal",
            "language": "es",
            "min_duration": 25,
            "max_duration": 55,
            "banned_words": ["estafa"],
            "required_keywords": ["dinero"],
            "target_platforms": ["youtube", "tiktok"],
        },
    )

    rules = load_rules(path)

    assert rules.name == "canal"
    assert rules.language == "es"
    assert rules.banned_words == ["estafa"]
    assert rules.target_platforms == ["youtube", "tiktok"]


def test_load_rules_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RulesFileError, match="no existe"):
        load_rules(tmp_path / "no-existe.json")


def test_load_rules_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "roto.json"
    path.write_text("{no es json", encoding="utf-8")

    with pytest.raises(RulesFileError, match="no es JSON válido"):
        load_rules(path)


def test_load_rules_invalid_schema(tmp_path: Path) -> None:
    path = _write_rules(tmp_path, {"language": "de"})

    with pytest.raises(RulesFileError, match="language"):
        load_rules(path)


def test_load_rules_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _write_rules(tmp_path, {"campo_inventado": True})

    with pytest.raises(RulesFileError, match="campo_inventado"):
        load_rules(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_duration": 4},
        {"min_duration": 30, "max_duration": 30},
        {"max_clips": 0},
        {"hook_max_seconds": 0},
    ],
)
def test_rules_validation_rejects_inconsistent_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CampaignRules(**overrides)


def test_duration_allowed_is_inclusive() -> None:
    rules = CampaignRules(min_duration=20, max_duration=60)

    assert duration_allowed(10.0, 30.0, rules) is True
    assert duration_allowed(10.0, 70.0, rules) is True
    assert duration_allowed(10.0, 71.0, rules) is False
    assert duration_allowed(0.0, 10.0, rules) is False


def test_banned_words_are_case_insensitive_and_respect_word_boundaries() -> None:
    banned = ["estafa", "dinero fácil"]

    assert find_banned_words("Esto es una ESTAFA total", banned) == ["estafa"]
    assert find_banned_words("Esto es una estafador", banned) == []
    assert find_banned_words("Un método de Dinero   Fácil", banned) == ["dinero fácil"]


def test_required_keywords_missing_detection() -> None:
    keywords = ["inversión", "rentabilidad"]

    assert missing_required_keywords("hablamos de inversión", keywords) == ["rentabilidad"]
    assert missing_required_keywords("inversión y rentabilidad", keywords) == []


def test_validate_candidate_text_reports_violations() -> None:
    rules = CampaignRules(banned_words=["estafa"], required_keywords=["dinero"])
    text = build_candidate_text(
        "Cuidado con la estafa",
        title="Alerta",
        hook="No caigas",
        description="Historia real",
    )

    validation = validate_candidate_text(text, rules)

    assert validation.rejected is True
    assert validation.banned_words == ["estafa"]
    violations = validation.violations
    assert len(violations) == 1
    assert violations[0].code == "missing_required_keyword"
    assert violations[0].field == "required_keywords"
    assert violations[0].severity == "warning"
    assert "dinero" in violations[0].message


def test_validate_candidate_text_without_rules() -> None:
    validation = validate_candidate_text("cualquier texto", CampaignRules())

    assert validation.rejected is False
    assert validation.violations == []
