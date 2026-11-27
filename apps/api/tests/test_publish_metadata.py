"""Tests de generación y validación de metadatos por plataforma (`task 1.2`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from winclip.core.models import Clip
from winclip.publishers.base import PublishMeta, PublishValidationError
from winclip.publishers.metadata import (
    YOUTUBE_TITLE_MAX_LEN,
    build_platform_meta,
    normalize_hashtags,
    truncate_clean,
    validate_publish_meta,
)
from winclip.rules.schema import CampaignRules


def _sample_clip(**overrides: object) -> Clip:
    data: dict[str, object] = {
        "id": "clip-1",
        "project_id": "proj-1",
        "title": "Cómo escalar tu negocio local con contenido vertical diario",
        "description": "Resumen práctico con 3 pasos aplicables hoy mismo.",
        "hashtags": ["#negocios", "marketing", "#Negocios"],
        "hook": "Este error te cuesta clientes",
        "thumb_path": "projects/proj-1/clips/clip-1/thumb.jpg",
        "candidate": {"language": "es"},
    }
    data.update(overrides)
    return Clip(**data)  # type: ignore[arg-type]


def _sample_rules(**overrides: object) -> CampaignRules:
    data: dict[str, object] = {
        "name": "Campaña Growth",
        "language": "es",
        "cta_text": "Suscríbete para más consejos diarios",
        "hashtags": ["#growth", "#marketing"],
    }
    data.update(overrides)
    return CampaignRules(**data)  # type: ignore[arg-type]


def test_normalize_hashtags_deduplicates_case_insensitively() -> None:
    assert normalize_hashtags(["#Uno", "dos", " #uno ", "", "   ", "#"]) == ["#Uno", "#dos"]


def test_truncate_clean_respects_word_boundary_and_max_len() -> None:
    long_title = "Uno dos tres cuatro cinco seis siete ocho nueve diez " * 4
    result = truncate_clean(long_title, YOUTUBE_TITLE_MAX_LEN)
    assert len(result) <= YOUTUBE_TITLE_MAX_LEN
    assert result.endswith("…")


def test_build_youtube_meta_merges_campaign_cta_hashtags_and_shorts() -> None:
    clip = _sample_clip(title="Título muy largo " * 12)
    meta = build_platform_meta(clip, _sample_rules(), "youtube")
    assert len(meta.title) <= YOUTUBE_TITLE_MAX_LEN
    assert "#Shorts" in meta.hashtags
    assert "#growth" in meta.hashtags
    assert "Suscríbete para más consejos diarios" in meta.description
    assert meta.pinned_comment == "Suscríbete para más consejos diarios"
    assert meta.category_id == "22"
    assert meta.language == "es"
    assert meta.privacy_status == "public"
    assert "Shorts" in meta.tags
    assert validate_publish_meta("youtube", meta) == []


def test_build_tiktok_and_instagram_meta() -> None:
    clip = _sample_clip()
    rules = _sample_rules(language="en")

    tt_meta = build_platform_meta(clip, rules, "tiktok", delivery_mode="inbox")
    assert tt_meta.delivery_mode == "inbox"
    assert tt_meta.language == "en"
    assert "#growth" in tt_meta.caption
    assert "Suscríbete" in tt_meta.caption
    assert validate_publish_meta("tiktok", tt_meta) == []

    ig_meta = build_platform_meta(clip, rules, "instagram")
    assert ig_meta.share_to_feed is True
    assert "#negocios" in ig_meta.caption
    assert validate_publish_meta("instagram", ig_meta) == []


def test_validate_rejects_youtube_title_over_100_chars() -> None:
    meta = PublishMeta(title="x" * 101)
    with pytest.raises(PublishValidationError, match="100"):
        validate_publish_meta("youtube", meta)


def test_validate_rejects_empty_youtube_title_and_long_captions() -> None:
    with pytest.raises(PublishValidationError):
        validate_publish_meta("youtube", PublishMeta(title="   "))

    with pytest.raises(PublishValidationError):
        validate_publish_meta("tiktok", PublishMeta(caption="a" * 2201))

    with pytest.raises(PublishValidationError):
        validate_publish_meta("instagram", PublishMeta(caption="b" * 2201))


def test_validate_warns_when_scheduled_at_is_in_past() -> None:
    meta = PublishMeta(
        title="Ok",
        scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    warnings = validate_publish_meta("youtube", meta)
    assert len(warnings) == 1
