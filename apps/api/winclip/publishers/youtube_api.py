"""Publicador oficial de YouTube Shorts vía YouTube Data API v3 (`design.md`, decisión 2)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from sqlmodel import Session

from winclip.accounts.crypto import CredentialsNotFoundError
from winclip.accounts.health import (
    AccountHealthError,
    TokenExpiredError,
    check_account,
    get_valid_credentials,
)
from winclip.core.config import Settings
from winclip.core.models import Clip, SocialAccount
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.publishers.base import (
    AccountStatus,
    AuthExpiredError,
    PermanentPublishError,
    ProgressCallback,
    PublishMeta,
    PublishResult,
    PublishValidationError,
    QuotaExceededError,
    TransientPublishError,
)
from winclip.publishers.metadata import validate_publish_meta

logger = logging.getLogger("winclip.publishers.youtube_api")

YOUTUBE_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB
YOUTUBE_DEFAULT_CATEGORY_ID = "22"


def _build_youtube_service(creds: dict[str, Any]) -> Any:
    """Construye el cliente de YouTube Data API v3 desde las credenciales descifradas."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_creds = Credentials(
        token=creds.get("access_token"),
        refresh_token=creds.get("refresh_token"),
        token_uri=creds.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=creds.get("client_id"),
        client_secret=creds.get("client_secret"),
        scopes=creds.get("scopes"),
    )
    return build("youtube", "v3", credentials=oauth_creds, cache_discovery=False)


def _make_media_upload(path: Path, *, mimetype: str, resumable: bool = True) -> Any:
    from googleapiclient.http import MediaFileUpload

    return MediaFileUpload(
        str(path),
        mimetype=mimetype,
        chunksize=YOUTUBE_CHUNK_SIZE if resumable else -1,
        resumable=resumable,
    )


def _extract_http_error_info(exc: Exception) -> tuple[int | None, str, str]:
    """Extrae `(status_code, reason, message)` de un `HttpError` de Google sin filtrar secretos."""
    resp = getattr(exc, "resp", None)
    status_code = getattr(resp, "status", None)
    if status_code is not None:
        try:
            status_code = int(status_code)
        except (TypeError, ValueError):
            status_code = None

    reason = ""
    message = str(exc)
    content = getattr(exc, "content", None)
    if isinstance(content, (bytes, bytearray)):
        try:
            parsed = json.loads(content.decode("utf-8", errors="replace"))
            err = parsed.get("error") or {}
            if isinstance(err, dict):
                message = str(err.get("message") or message)
                errors = err.get("errors") or []
                if errors and isinstance(errors[0], dict):
                    reason = str(errors[0].get("reason") or "")
        except Exception:
            pass
    return status_code, reason, message


def _classify_google_error(exc: Exception, *, external_id: str | None = None) -> Exception:
    status_code, reason, message = _extract_http_error_info(exc)
    lowered = f"{reason} {message}".lower()

    if (
        "quotaexceeded" in lowered
        or "dailylimitexceeded" in lowered
        or "uploadlimitexceeded" in lowered
    ):
        return QuotaExceededError(
            "Cuota diaria de YouTube Data API v3 agotada (límite estándar: 10 000 unidades/día, "
            "~6 subidas). Intenta mañana o solicita aumento de cuota.",
            external_id=external_id,
        )
    if status_code == 401 or "invalid_grant" in lowered or "autherror" in lowered:
        return AuthExpiredError(
            "Las credenciales de YouTube expiraron o fueron revocadas; reconecta la cuenta.",
            external_id=external_id,
        )
    if status_code == 403:
        return AuthExpiredError(
            f"Permiso denegado por YouTube API ({reason or 'forbidden'}): {message}",
            external_id=external_id,
        )
    if status_code in (400, 404, 422):
        return PublishValidationError(
            f"YouTube rechazó la solicitud ({status_code}): {message}",
            external_id=external_id,
        )
    if status_code in (429, 500, 502, 503, 504) or isinstance(
        exc, (TimeoutError, ConnectionError, OSError, httpx.HTTPError)
    ):
        return TransientPublishError(
            f"Error temporal comunicando con YouTube "
            f"({status_code or type(exc).__name__}): {message}",
            external_id=external_id,
        )
    return PermanentPublishError(
        f"Error publicando en YouTube: {message}",
        external_id=external_id,
    )


class YouTubeApiPublisher:
    """Publicador oficial de YouTube Shorts con subida reanudable, programación y cuota."""

    platform: Literal["youtube"] = "youtube"

    def __init__(
        self,
        *,
        settings: Settings,
        session: Session | None = None,
        service_factory: Callable[[dict[str, Any]], Any] | None = None,
        media_factory: Callable[[Path, str, bool], Any] | None = None,
        http_client: httpx.Client | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.session = session
        self.storage = LocalStorage(settings.storage_dir)
        self._service_factory = service_factory or _build_youtube_service
        self._media_factory = media_factory or (
            lambda path, mimetype, resumable: _make_media_upload(
                path, mimetype=mimetype, resumable=resumable
            )
        )
        self.http_client = http_client
        self.on_progress = on_progress

    def _report(self, percent: float, stage: str) -> None:
        if self.on_progress is not None:
            self.on_progress(percent, stage)

    def _get_credentials(self, account: SocialAccount) -> dict[str, Any]:
        if self.session is None:
            raise AuthExpiredError("Sesión de base de datos requerida para leer credenciales")
        try:
            return get_valid_credentials(
                self.session,
                account,
                self.settings,
                http_client=self.http_client,
            )
        except (TokenExpiredError, CredentialsNotFoundError) as exc:
            raise AuthExpiredError(str(exc)) from exc
        except AccountHealthError as exc:
            raise TransientPublishError(str(exc)) from exc

    def check(self, account: SocialAccount) -> AccountStatus:
        if self.session is not None:
            updated = check_account(
                self.session,
                account,
                self.settings,
                http_client=self.http_client,
            )
            return AccountStatus(
                status=updated.status,  # type: ignore[arg-type]
                message=updated.last_error,
                capabilities=dict(updated.capabilities_json or {}),
            )
        return AccountStatus(
            status=account.status,  # type: ignore[arg-type]
            message=account.last_error,
            capabilities=dict(account.capabilities_json or {}),
        )

    def delete_video(self, account: SocialAccount, video_id: str) -> None:
        """Elimina un video programado en YouTube (solo bajo confirmación explícita)."""
        creds = self._get_credentials(account)
        service = self._service_factory(creds)
        try:
            service.videos().delete(id=video_id).execute()
        except Exception as exc:
            raise _classify_google_error(exc, external_id=video_id) from exc

    def publish(self, clip: Clip, account: SocialAccount, meta: PublishMeta) -> PublishResult:
        warnings = validate_publish_meta("youtube", meta)
        if not clip.path:
            raise PublishValidationError("El clip no tiene archivo renderizado para publicar")
        try:
            clip_path = self.storage.resolve_safe(clip.path)
        except StoragePathError as exc:
            raise PublishValidationError(str(exc)) from exc
        if not clip_path.is_file():
            raise PublishValidationError(f"No existe el archivo de video del clip: {clip.path}")

        self._report(5.0, "auth")
        creds = self._get_credentials(account)
        service = self._service_factory(creds)

        now_utc = datetime.now(UTC)
        scheduled_utc: datetime | None = None
        if meta.scheduled_at is not None:
            candidate = (
                meta.scheduled_at.astimezone(UTC)
                if meta.scheduled_at.tzinfo is not None
                else meta.scheduled_at.replace(tzinfo=UTC)
            )
            if candidate > now_utc:
                scheduled_utc = candidate

        video_id = meta.existing_external_id
        external_url = meta.existing_external_url

        if video_id:
            logger.info("reutilizando external_id=%s para publicación idempotente", video_id)
            self._report(80.0, "reconcile")
        else:
            status_body: dict[str, Any] = {
                "privacyStatus": "private" if scheduled_utc is not None else meta.privacy_status,
                "selfDeclaredMadeForKids": False,
            }
            if scheduled_utc is not None:
                status_body["publishAt"] = scheduled_utc.isoformat().replace("+00:00", "Z")

            body: dict[str, Any] = {
                "snippet": {
                    "title": meta.title.strip(),
                    "description": meta.description,
                    "tags": list(meta.tags),
                    "categoryId": meta.category_id or YOUTUBE_DEFAULT_CATEGORY_ID,
                    "defaultLanguage": meta.language or "es",
                    "defaultAudioLanguage": meta.language or "es",
                },
                "status": status_body,
            }

            self._report(10.0, "uploading")
            media = self._media_factory(clip_path, "video/mp4", True)
            try:
                request = service.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media,
                )
                response: dict[str, Any] | None = None
                while response is None:
                    status, response = request.next_chunk()
                    if status is not None and hasattr(status, "progress"):
                        pct = 10.0 + float(status.progress()) * 70.0
                        self._report(min(80.0, pct), "uploading")
            except Exception as exc:
                raise _classify_google_error(exc) from exc

            video_id = str((response or {}).get("id") or "").strip()
            if not video_id:
                raise PermanentPublishError("YouTube no devolvió el identificador del video subido")
            external_url = f"https://www.youtube.com/shorts/{video_id}"
            self._report(82.0, "uploaded")

        if not external_url and video_id:
            external_url = f"https://www.youtube.com/shorts/{video_id}"

        # Paso secundario no fatal: miniatura personalizada
        if meta.upload_thumbnail and clip.thumb_path:
            try:
                thumb_path = self.storage.resolve_safe(clip.thumb_path)
                if thumb_path.is_file():
                    self._report(88.0, "thumbnail")
                    thumb_media = self._media_factory(thumb_path, "image/jpeg", False)
                    service.thumbnails().set(
                        videoId=video_id,
                        media_body=thumb_media,
                    ).execute()
            except Exception as exc:
                status_code, reason, _ = _extract_http_error_info(exc)
                if status_code == 403:
                    warnings.append(
                        "No se pudo subir la miniatura personalizada (403): verifica que el canal "
                        "tenga verificación telefónica habilitada en YouTube Studio."
                    )
                else:
                    err_label = reason or type(exc).__name__
                    warnings.append(f"No se pudo subir la miniatura personalizada ({err_label}).")

        # Paso secundario no fatal: comentario inicial/fijado
        pinned = (meta.pinned_comment or "").strip()
        if pinned:
            try:
                self._report(94.0, "comment")
                service.commentThreads().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "topLevelComment": {
                                "snippet": {
                                    "textOriginal": pinned,
                                }
                            },
                        }
                    },
                ).execute()
                warnings.append(
                    "Comentario inicial publicado. YouTube API v3 no permite fijarlo "
                    "automáticamente; fíjalo desde YouTube Studio si lo deseas."
                )
            except Exception as exc:
                _, reason, _ = _extract_http_error_info(exc)
                warnings.append(
                    f"No se pudo publicar el comentario inicial ({reason or type(exc).__name__})."
                )

        self._report(100.0, "done")
        final_status: Literal["published", "scheduled"] = (
            "scheduled" if scheduled_utc is not None else "published"
        )
        return PublishResult(
            external_id=video_id,
            external_url=external_url,
            delivery_mode="direct",
            status=final_status,
            warnings=warnings,
            raw_status="scheduled" if scheduled_utc is not None else "uploaded",
        )
