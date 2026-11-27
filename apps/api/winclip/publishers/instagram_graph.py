"""Publicador de Instagram Reels vía Graph API con subida reanudable local (`design.md`)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
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
from winclip.accounts.oauth import META_GRAPH_VERSION
from winclip.core.config import Settings
from winclip.core.models import Clip, SocialAccount
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.pipeline.ingest import probe_media
from winclip.publishers.base import (
    AccountStatus,
    AuthExpiredError,
    PermanentPublishError,
    ProgressCallback,
    PublishMeta,
    PublishResult,
    PublishValidationError,
    TransientPublishError,
)
from winclip.publishers.metadata import validate_publish_meta

logger = logging.getLogger("winclip.publishers.instagram_graph")

GRAPH_BASE_URL = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
RUPLOAD_BASE_URL = f"https://rupload.facebook.com/ig-api-upload/{META_GRAPH_VERSION}"
REEL_MIN_DURATION_SEC = 3.0
REEL_MAX_DURATION_SEC = 900.0  # 15 min límite técnico Graph API
REEL_RECOMMENDED_MAX_SEC = 90.0
IG_POLL_INTERVALS = (2.0, 4.0, 6.0, 10.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0)


def _check_graph_response(
    resp: httpx.Response,
    *,
    context: str,
    external_id: str | None = None,
) -> dict[str, Any]:
    try:
        payload = resp.json()
    except Exception:
        payload = {}

    err = payload.get("error") if isinstance(payload, dict) else None
    err_msg = ""
    err_code = None
    if isinstance(err, dict):
        err_msg = str(err.get("message") or "")
        err_code = err.get("code")

    if resp.status_code in (401, 403) or err_code in (190, 102):
        raise AuthExpiredError(
            f"Credenciales de Instagram expiradas o revocadas durante {context}: "
            f"{err_msg or resp.status_code}",
            external_id=external_id,
        )
    if resp.status_code in (429, 500, 502, 503, 504) or err_code in (4, 17, 32, 613):
        raise TransientPublishError(
            f"Error temporal de Instagram Graph durante {context}: {err_msg or resp.status_code}",
            external_id=external_id,
        )
    if resp.status_code >= 400 or isinstance(err, dict):
        raise PermanentPublishError(
            f"Instagram Graph rechazó {context}: {err_msg or f'HTTP {resp.status_code}'}",
            external_id=external_id,
        )
    return payload if isinstance(payload, dict) else {}


def validate_reel_video(
    clip_path: Path,
    settings: Settings,
    *,
    probe_fn: Callable[[Path, Settings], Any] | None = None,
) -> list[str]:
    """Valida requisitos básicos de Instagram Reels antes de transferir a `rupload.facebook.com`."""
    warnings: list[str] = []
    if clip_path.suffix.lower() != ".mp4":
        ext = clip_path.suffix or "sin extensión"
        raise PublishValidationError(f"Instagram Reels requiere un archivo MP4 (recibido: {ext})")
    if clip_path.stat().st_size <= 0:
        raise PublishValidationError("El archivo MP4 del clip está vacío")

    if probe_fn is None:
        return warnings

    try:
        probe = probe_fn(clip_path, settings)
    except Exception as exc:
        logger.debug("omitiendo validación ffprobe detallada: %s", exc)
        return warnings

    duration = float(getattr(probe, "duration", 0.0) or 0.0)
    if duration > 0:
        if duration < REEL_MIN_DURATION_SEC:
            raise PublishValidationError(
                f"El Reel es demasiado corto ({duration:.1f}s); "
                f"el mínimo de Instagram es {REEL_MIN_DURATION_SEC:.0f}s"
            )
        if duration > REEL_MAX_DURATION_SEC:
            raise PublishValidationError(
                f"El Reel supera la duración máxima permitida "
                f"({duration:.1f}s > {REEL_MAX_DURATION_SEC:.0f}s)"
            )
        if duration > REEL_RECOMMENDED_MAX_SEC:
            warnings.append(
                f"El Reel dura {duration:.0f}s (por encima de los 90s recomendados por Instagram)."
            )

    codec = str(getattr(probe, "video_codec", "") or "").lower()
    if codec and codec not in ("h264", "hevc", "h265"):
        raise PublishValidationError(
            f"Códec de video incompatible con Instagram Reels ({codec}); se requiere H.264 o HEVC."
        )

    width = int(getattr(probe, "width", 0) or 0)
    height = int(getattr(probe, "height", 0) or 0)
    if width > 0 and height > 0 and width > height:
        warnings.append(
            f"El clip no es vertical ({width}x{height}); Instagram Reels recomienda 9:16."
        )
    return warnings


class InstagramGraphPublisher:
    """Publicador de Instagram Reels vía Graph API usando subida reanudable local."""

    platform: Literal["instagram"] = "instagram"

    def __init__(
        self,
        *,
        settings: Settings,
        session: Session | None = None,
        http_client: httpx.Client | None = None,
        on_progress: ProgressCallback | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        probe_fn: Callable[[Path, Settings], Any] | None = probe_media,
        poll_intervals: tuple[float, ...] = IG_POLL_INTERVALS,
    ) -> None:
        self.settings = settings
        self.session = session
        self.storage = LocalStorage(settings.storage_dir)
        self.http_client = http_client
        self.on_progress = on_progress
        self._sleep = sleep_fn
        self._probe_fn = probe_fn
        self._poll_intervals = poll_intervals

    def _report(self, percent: float, stage: str) -> None:
        if self.on_progress is not None:
            self.on_progress(percent, stage)

    def _get_credentials(self, account: SocialAccount, client: httpx.Client) -> dict[str, Any]:
        if self.session is None:
            raise AuthExpiredError("Sesión de base de datos requerida para leer credenciales")
        try:
            return get_valid_credentials(
                self.session,
                account,
                self.settings,
                http_client=client,
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

    def publish(self, clip: Clip, account: SocialAccount, meta: PublishMeta) -> PublishResult:
        warnings = validate_publish_meta("instagram", meta)
        if not clip.path:
            raise PublishValidationError("El clip no tiene archivo renderizado para publicar")
        try:
            clip_path = self.storage.resolve_safe(clip.path)
        except StoragePathError as exc:
            raise PublishValidationError(str(exc)) from exc
        if not clip_path.is_file():
            raise PublishValidationError(f"No existe el archivo de video del clip: {clip.path}")

        warnings.extend(validate_reel_video(clip_path, self.settings, probe_fn=self._probe_fn))

        owns_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=120.0)
        try:
            self._report(5.0, "auth")
            creds = self._get_credentials(account, client)
            ig_user_id = str(creds.get("ig_user_id") or account.external_account_id or "").strip()
            token = str(creds.get("page_access_token") or creds.get("access_token") or "").strip()
            if not ig_user_id or not token:
                raise AuthExpiredError(
                    "Faltan ig_user_id o access_token para Instagram Graph; reconecta la cuenta."
                )

            container_id = meta.existing_external_id
            if container_id:
                logger.info("reutilizando container_id=%s en reintento idempotente", container_id)
                self._report(60.0, "polling")
            else:
                # 1. Crear contenedor de Reel en modo resumable
                self._report(12.0, "create_container")
                create_data: dict[str, Any] = {
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": (meta.caption or meta.description or meta.title)[:2200],
                    "share_to_feed": "true" if meta.share_to_feed else "false",
                    "access_token": token,
                }
                if meta.thumb_offset_ms is not None and meta.thumb_offset_ms >= 0:
                    create_data["thumb_offset"] = str(meta.thumb_offset_ms)

                try:
                    create_resp = client.post(
                        f"{GRAPH_BASE_URL}/{ig_user_id}/media",
                        data=create_data,
                    )
                except httpx.HTTPError as exc:
                    raise TransientPublishError(
                        f"Error de red creando contenedor de Instagram ({type(exc).__name__})"
                    ) from exc

                create_payload = _check_graph_response(create_resp, context="crear contenedor")
                container_id = str(create_payload.get("id") or "").strip()
                upload_uri = str(create_payload.get("uri") or "").strip()
                if not container_id:
                    raise PermanentPublishError("Instagram Graph no devolvió el id del contenedor")
                if not upload_uri:
                    upload_uri = f"{RUPLOAD_BASE_URL}/{container_id}"

                # 2. Subida binaria directa del MP4 local a rupload.facebook.com
                self._report(25.0, "uploading")
                file_bytes = clip_path.read_bytes()
                try:
                    upload_resp = client.post(
                        upload_uri,
                        headers={
                            "Authorization": f"OAuth {token}",
                            "offset": "0",
                            "file_size": str(len(file_bytes)),
                            "Content-Type": "application/octet-stream",
                        },
                        content=file_bytes,
                    )
                except httpx.HTTPError as exc:
                    raise TransientPublishError(
                        f"Error de red transfiriendo binario a Instagram ({type(exc).__name__})",
                        external_id=container_id,
                    ) from exc

                _check_graph_response(
                    upload_resp, context="subida reanudable", external_id=container_id
                )
                self._report(60.0, "polling")

            # 3. Polling del estado del contenedor hasta FINISHED
            status_code = ""
            for attempt_idx, delay in enumerate(self._poll_intervals):
                try:
                    status_resp = client.get(
                        f"{GRAPH_BASE_URL}/{container_id}",
                        params={"fields": "status_code,status", "access_token": token},
                    )
                except httpx.HTTPError as exc:
                    raise TransientPublishError(
                        f"Error de red consultando estado del contenedor ({type(exc).__name__})",
                        external_id=container_id,
                    ) from exc

                status_payload = _check_graph_response(
                    status_resp, context="estado de contenedor", external_id=container_id
                )
                status_code = str(status_payload.get("status_code") or "").upper()
                status_detail = str(status_payload.get("status") or "")

                if status_code in ("FINISHED", "PUBLISHED"):
                    break
                if status_code in ("ERROR", "EXPIRED"):
                    raise PermanentPublishError(
                        f"Instagram falló al procesar el Reel ({status_code}): {status_detail}",
                        external_id=container_id,
                    )

                pct = 60.0 + min(22.0, (attempt_idx + 1) * 3.0)
                self._report(pct, "polling")
                if attempt_idx < len(self._poll_intervals) - 1:
                    self._sleep(delay)
            else:
                raise TransientPublishError(
                    "Instagram sigue procesando el Reel "
                    f"(último estado: {status_code or 'IN_PROGRESS'}).",
                    external_id=container_id,
                )

            # 4. Publicar el contenedor
            self._report(88.0, "publishing")
            try:
                publish_resp = client.post(
                    f"{GRAPH_BASE_URL}/{ig_user_id}/media_publish",
                    data={"creation_id": container_id, "access_token": token},
                )
            except httpx.HTTPError as exc:
                raise TransientPublishError(
                    f"Error de red publicando el Reel ({type(exc).__name__})",
                    external_id=container_id,
                ) from exc

            publish_payload = _check_graph_response(
                publish_resp, context="media_publish", external_id=container_id
            )
            media_id = str(publish_payload.get("id") or container_id)

            # 5. Obtener permalink (no fatal si falla)
            permalink: str | None = meta.existing_external_url
            try:
                self._report(95.0, "permalink")
                perm_resp = client.get(
                    f"{GRAPH_BASE_URL}/{media_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                if perm_resp.status_code == 200:
                    permalink = perm_resp.json().get("permalink") or permalink
            except Exception:
                pass

            self._report(100.0, "done")
            return PublishResult(
                external_id=media_id,
                external_url=permalink,
                delivery_mode="direct",
                status="published",
                warnings=warnings,
                raw_status=status_code or "PUBLISHED",
            )
        finally:
            if owns_client:
                client.close()
