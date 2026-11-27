"""Generación y validación de metadatos de publicación por plataforma (`design.md`, decisión 7)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from winclip.core.models import Campaign, Clip
from winclip.publishers.base import (
    DeliveryMode,
    PublishMeta,
    PublishPlatform,
    PublishValidationError,
)
from winclip.rules.schema import CampaignRules

YOUTUBE_TITLE_MAX_LEN = 100
YOUTUBE_DESCRIPTION_MAX_LEN = 5000
YOUTUBE_TAGS_MAX_CHARS = 500
TIKTOK_CAPTION_MAX_LEN = 2200
INSTAGRAM_CAPTION_MAX_LEN = 2200
YOUTUBE_PINNED_COMMENT_MAX_LEN = 10000

VALID_YOUTUBE_PRIVACY = frozenset({"public", "unlisted", "private"})
VALID_TIKTOK_PRIVACY = frozenset(
    {
        "PUBLIC_TO_EVERYONE",
        "MUTUAL_FOLLOW_FRIENDS",
        "FOLLOWER_OF_CREATOR",
        "SELF_ONLY",
    }
)


def normalize_hashtags(hashtags: Iterable[str]) -> list[str]:
    """Normaliza hashtags con prefijo `#`, sin espacios internos ni duplicados."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in hashtags:
        if not raw:
            continue
        cleaned = "".join(str(raw).strip().split())
        if not cleaned:
            continue
        tag = cleaned if cleaned.startswith("#") else f"#{cleaned}"
        if tag == "#":
            continue
        lowered = tag.lower()
        if lowered not in seen:
            seen.add(lowered)
            result.append(tag)
    return result


def truncate_clean(text: str, max_len: int) -> str:
    """Recorta texto limpiamente respetando límites de palabra sin superar `max_len`."""
    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return normalized
    if max_len <= 1:
        return normalized[:max_len]
    cut = normalized[: max_len - 1]
    if " " in cut:
        candidate = cut.rsplit(" ", 1)[0].rstrip(" ,;:-")
        if candidate:
            return f"{candidate}…"
    return f"{cut.rstrip()}…"


def _extract_rules(campaign: CampaignRules | Campaign | None) -> CampaignRules | None:
    if campaign is None:
        return None
    if isinstance(campaign, CampaignRules):
        return campaign
    return CampaignRules.model_validate(campaign.rules_json)


def _resolve_language(
    clip: Clip,
    rules: CampaignRules | None,
    fallback: str = "es",
) -> str:
    if rules is not None and rules.language in ("es", "en"):
        return rules.language
    candidate_lang = str((clip.candidate or {}).get("language") or "").strip().lower()
    if candidate_lang in ("es", "en"):
        return candidate_lang
    return fallback if fallback in ("es", "en") else "es"


def _build_tags_from_hashtags(hashtags: list[str]) -> list[str]:
    """Deriva etiquetas de YouTube sin `#`, respetando el límite total de 500 caracteres."""
    tags: list[str] = []
    total_chars = 0
    for tag in hashtags:
        clean = tag.lstrip("#").strip()
        if not clean:
            continue
        added = len(clean) + (1 if tags else 0)
        if total_chars + added > YOUTUBE_TAGS_MAX_CHARS:
            break
        tags.append(clean)
        total_chars += added
    return tags


def _join_sections(parts: list[str], max_len: int) -> str:
    non_empty = [part.strip() for part in parts if part and part.strip()]
    joined = "\n\n".join(non_empty)
    if len(joined) <= max_len:
        return joined
    return truncate_clean(joined, max_len)


def build_platform_meta(
    clip: Clip,
    campaign: CampaignRules | Campaign | None,
    platform: PublishPlatform,
    *,
    delivery_mode: DeliveryMode = "direct",
    language_fallback: str = "es",
) -> PublishMeta:
    """Precalcula metadatos editables combinando el clip y su campaña asociada."""
    rules = _extract_rules(campaign)
    language = _resolve_language(clip, rules, fallback=language_fallback)
    cta = (rules.cta_text or "").strip() if rules else ""
    campaign_tags = list(rules.hashtags) if rules else []
    merged_hashtags = normalize_hashtags([*list(clip.hashtags or []), *campaign_tags])

    raw_title = (clip.title or clip.hook or "Short").strip()
    raw_desc = (clip.description or "").strip()

    if platform == "youtube":
        yt_hashtags = normalize_hashtags([*merged_hashtags, "#Shorts"])
        title = truncate_clean(raw_title, YOUTUBE_TITLE_MAX_LEN)
        desc_parts = [raw_desc]
        if cta and cta.lower() not in raw_desc.lower():
            desc_parts.append(cta)
        if yt_hashtags:
            desc_parts.append(" ".join(yt_hashtags))
        description = _join_sections(desc_parts, YOUTUBE_DESCRIPTION_MAX_LEN)
        tags = _build_tags_from_hashtags(yt_hashtags)
        return PublishMeta(
            title=title,
            description=description,
            caption=description,
            hashtags=yt_hashtags,
            tags=tags,
            category_id="22",
            language=language,
            privacy_status="public",
            pinned_comment=cta or None,
            upload_thumbnail=bool(clip.thumb_path),
            delivery_mode="direct",
        )

    if platform == "tiktok":
        lead = raw_title if not raw_desc else f"{raw_title}\n{raw_desc}"
        parts = [lead]
        if cta and cta.lower() not in lead.lower():
            parts.append(cta)
        if merged_hashtags:
            parts.append(" ".join(merged_hashtags))
        caption = _join_sections(parts, TIKTOK_CAPTION_MAX_LEN)
        return PublishMeta(
            title=truncate_clean(raw_title, 150),
            description=raw_desc,
            caption=caption,
            hashtags=merged_hashtags,
            language=language,
            privacy_level="PUBLIC_TO_EVERYONE",
            disable_comment=False,
            disable_duet=False,
            disable_stitch=False,
            delivery_mode=delivery_mode,
        )

    if platform == "instagram":
        lead = raw_desc or raw_title
        parts = [lead]
        if cta and cta.lower() not in lead.lower():
            parts.append(cta)
        if merged_hashtags:
            parts.append(" ".join(merged_hashtags))
        caption = _join_sections(parts, INSTAGRAM_CAPTION_MAX_LEN)
        return PublishMeta(
            title=truncate_clean(raw_title, 150),
            description=raw_desc,
            caption=caption,
            hashtags=merged_hashtags,
            language=language,
            share_to_feed=True,
            delivery_mode="direct",
        )

    raise PublishValidationError(f"Plataforma no soportada para metadatos: {platform}")


def validate_publish_meta(platform: PublishPlatform, meta: PublishMeta) -> list[str]:
    """Valida metadatos antes de subir; lanza `PublishValidationError` si hay errores fatales.

    Devuelve una lista de advertencias no fatales.
    """
    warnings: list[str] = []

    if meta.scheduled_at is not None:
        scheduled = (
            meta.scheduled_at.astimezone(UTC)
            if meta.scheduled_at.tzinfo is not None
            else meta.scheduled_at.replace(tzinfo=UTC)
        )
        if scheduled <= datetime.now(UTC):
            warnings.append("La fecha programada está en el pasado; se ejecutará de inmediato.")

    if platform == "youtube":
        title = meta.title.strip()
        if not title:
            raise PublishValidationError("El título de YouTube es obligatorio")
        if len(title) > YOUTUBE_TITLE_MAX_LEN:
            raise PublishValidationError(
                f"El título de YouTube supera el máximo de {YOUTUBE_TITLE_MAX_LEN} caracteres "
                f"({len(title)})"
            )
        if len(meta.description) > YOUTUBE_DESCRIPTION_MAX_LEN:
            raise PublishValidationError(
                f"La descripción de YouTube supera {YOUTUBE_DESCRIPTION_MAX_LEN} caracteres"
            )
        tags_chars = sum(len(t) for t in meta.tags) + max(0, len(meta.tags) - 1)
        if tags_chars > YOUTUBE_TAGS_MAX_CHARS:
            raise PublishValidationError(
                f"Las etiquetas de YouTube superan {YOUTUBE_TAGS_MAX_CHARS} caracteres totales"
            )
        if meta.privacy_status not in VALID_YOUTUBE_PRIVACY:
            raise PublishValidationError(f"Privacidad de YouTube inválida: {meta.privacy_status}")
        if meta.pinned_comment and len(meta.pinned_comment) > YOUTUBE_PINNED_COMMENT_MAX_LEN:
            raise PublishValidationError("El comentario fijado supera el límite permitido")
        return warnings

    if platform == "tiktok":
        caption = (meta.caption or meta.title or "").strip()
        if len(caption) > TIKTOK_CAPTION_MAX_LEN:
            raise PublishValidationError(
                f"El caption de TikTok supera {TIKTOK_CAPTION_MAX_LEN} caracteres ({len(caption)})"
            )
        if meta.privacy_level not in VALID_TIKTOK_PRIVACY:
            raise PublishValidationError(
                f"Nivel de privacidad de TikTok inválido: {meta.privacy_level}"
            )
        return warnings

    if platform == "instagram":
        caption = (meta.caption or meta.description or meta.title or "").strip()
        if len(caption) > INSTAGRAM_CAPTION_MAX_LEN:
            raise PublishValidationError(
                f"El caption de Instagram supera {INSTAGRAM_CAPTION_MAX_LEN} caracteres "
                f"({len(caption)})"
            )
        return warnings

    raise PublishValidationError(f"Plataforma no soportada: {platform}")
