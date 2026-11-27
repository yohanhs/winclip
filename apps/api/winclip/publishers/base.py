"""Contratos base para publicadores (`docs/architecture.md §8` y `design.md`)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from winclip.core.models import Clip, SocialAccount, utcnow

PublishPlatform = Literal["youtube", "tiktok", "instagram"]
DeliveryMode = Literal["direct", "inbox"]
AccountStatusState = Literal["pending", "connected", "expired", "error"]
YouTubePrivacy = Literal["public", "unlisted", "private"]

ProgressCallback = Callable[[float, str], None]


class AccountStatus(BaseModel):
    """Resultado normalizado de `Publisher.check(account)`."""

    status: AccountStatusState
    message: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=utcnow)


class PublishMeta(BaseModel):
    """Metadatos de publicación unificados y editables por plataforma."""

    # Comunes
    title: str = ""
    description: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None
    delivery_mode: DeliveryMode = "direct"
    language: str = "es"

    # YouTube Shorts
    tags: list[str] = Field(default_factory=list)
    category_id: str = "22"
    privacy_status: YouTubePrivacy = "public"
    pinned_comment: str | None = None
    upload_thumbnail: bool = True

    # TikTok
    privacy_level: str = "PUBLIC_TO_EVERYONE"
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False

    # Instagram Reels
    share_to_feed: bool = True
    thumb_offset_ms: int | None = None

    # Contexto interno de idempotencia / trazabilidad
    publication_id: str | None = None
    existing_external_id: str | None = None
    existing_external_url: str | None = None


class PublishResult(BaseModel):
    """Resultado estructurado de `Publisher.publish(...)`."""

    external_id: str | None = None
    external_url: str | None = None
    delivery_mode: DeliveryMode = "direct"
    status: Literal["published", "scheduled"] = "published"
    warnings: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None
    step_screenshots: list[str] = Field(default_factory=list)
    raw_status: str | None = None


class PublishError(RuntimeError):
    """Error base de publicación con clasificación de reintento y trazabilidad."""

    code: str = "publish_error"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        screenshot_path: str | None = None,
        external_id: str | None = None,
        external_url: str | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.screenshot_path = screenshot_path
        self.external_id = external_id
        self.external_url = external_url


class TransientPublishError(PublishError):
    """Error temporal elegible para reintento con backoff (red, 5xx, timeout, 429)."""

    code: str = "transient_error"
    retryable: bool = True


class PermanentPublishError(PublishError):
    """Error permanente que no debe reintentarse automáticamente."""

    code: str = "permanent_error"
    retryable: bool = False


class PublishValidationError(PermanentPublishError):
    """Metadatos o archivo de clip inválidos antes o durante el envío."""

    code: str = "validation_error"


class AuthExpiredError(PermanentPublishError):
    """Token OAuth o sesión de navegador expirada o revocada."""

    code: str = "session_expired"


class QuotaExceededError(PermanentPublishError):
    """Cuota diaria de API agotada (p. ej. YouTube Data API v3 10k unidades/día)."""

    code: str = "quota_exceeded"


class ChallengeDetectedError(PermanentPublishError):
    """Desafío anti-bot, CAPTCHA o verificación 2FA detectada en navegador."""

    code: str = "challenge_required"


class DailyLimitExceededError(PermanentPublishError):
    """Límite diario configurado para la cuenta alcanzado."""

    code: str = "daily_limit_exceeded"


class MissedScheduleWindowError(PermanentPublishError):
    """Ventana de programación diferida excedida mientras el worker estuvo apagado."""

    code: str = "missed_schedule_window"


class UnsupportedPublisherError(PermanentPublishError):
    """Combinación `(platform, auth_method)` sin publicador registrado."""

    code: str = "unsupported_publisher"


@runtime_checkable
class Publisher(Protocol):
    """Interfaz común de publicadores (`docs/architecture.md §8`)."""

    platform: PublishPlatform

    def check(self, account: SocialAccount) -> AccountStatus: ...

    def publish(self, clip: Clip, account: SocialAccount, meta: PublishMeta) -> PublishResult: ...
