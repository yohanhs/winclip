"""Tests de `winclip.rules.validator` para evaluación completa de `CampaignRules`."""

from __future__ import annotations

from winclip.rules.schema import CampaignRules, RuleViolation
from winclip.rules.validator import (
    estimate_hook_seconds,
    find_banned_words,
    missing_required_hashtags,
    missing_required_keywords,
    validate_candidate,
)


def test_accent_insensitive_and_word_boundary_matching() -> None:
    assert find_banned_words("Esto ofrece dinero facil hoy", ["dinero fácil"]) == ["dinero fácil"]
    assert find_banned_words("Una educación sin estafador", ["estafa"]) == []
    assert missing_required_keywords("Hablamos de inversion real", ["inversión"]) == []


def test_missing_required_hashtags_is_case_and_accent_insensitive() -> None:
    assert missing_required_hashtags(
        ["#Finanzas", "#inversion"], ["#finanzas", "#inversión", "#clips"]
    ) == ["#clips"]


def test_validate_candidate_clean_clip_has_no_violations() -> None:
    rules = CampaignRules(
        name="Finanzas",
        min_duration=20,
        max_duration=60,
        banned_words=["garantizado"],
        required_keywords=["inversión"],
        hashtags=["#finanzas", "#shorts"],
        hook_max_seconds=4,
    )

    violations = validate_candidate(
        start=10.0,
        end=45.0,
        rules=rules,
        clip_text="Hoy explico una estrategia de inversion a largo plazo.",
        title="Cómo empezar tu inversión",
        hook="Tres errores que frenan tu ahorro",
        description="Aprende a invertir con disciplina.",
        hashtags=["#Finanzas", "#Shorts"],
    )

    assert violations == []


def test_validate_candidate_reports_all_deterministic_violations() -> None:
    rules = CampaignRules(
        name="Bounty",
        min_duration=25,
        max_duration=50,
        banned_words=["garantizado", "dinero fácil"],
        required_keywords=["criptografía", "seguridad"],
        hashtags=["#tech", "#shorts"],
        hook_max_seconds=2,
    )

    violations = validate_candidate(
        start=0.0,
        end=12.0,
        rules=rules,
        clip_text="Este método de dinero facil es 100% garantizado.",
        title="Truco rápido",
        hook="Esta frase introductoria es deliberadamente demasiado larga para dos segundos",
        description="Sin palabras clave aquí",
        hashtags=["#tech"],
        existing_violations=[
            RuleViolation(
                code="banned_topic_risk",
                field="banned_topics",
                severity="warning",
                message="Posible mención de tema restringido",
            )
        ],
    )

    codes = [v.code for v in violations]
    assert "duration_out_of_range" in codes
    assert codes.count("banned_word_present") == 2
    assert "missing_required_keyword" in codes
    assert "missing_required_hashtag" in codes
    assert "hook_too_long" in codes
    assert "banned_topic_risk" in codes

    dur_violation = next(v for v in violations if v.code == "duration_out_of_range")
    assert dur_violation.severity == "error"
    assert dur_violation.field == "min_duration"


def test_validate_candidate_reports_max_duration_violation() -> None:
    rules = CampaignRules(min_duration=15, max_duration=45)
    violations = validate_candidate(start=0.0, end=62.5, rules=rules, clip_text="texto")
    assert len(violations) == 1
    assert violations[0].code == "duration_out_of_range"
    assert violations[0].field == "max_duration"
    assert violations[0].severity == "error"


def test_estimate_hook_seconds() -> None:
    assert estimate_hook_seconds("") == 0.0
    assert estimate_hook_seconds("Tres claves") < 2.0
    assert estimate_hook_seconds("uno dos tres cuatro cinco seis siete ocho nueve diez") > 3.0
