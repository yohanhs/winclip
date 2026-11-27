"""Publicador oficial de TikTok vía Content Posting API v2 (`design.md`, decisión 3)."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
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
    TransientPublishError,
)
from winclip.publishers.metadata import validate_publish_meta

logger = logging.getLogger("winclip.publishers.tiktok_api")

TIKTOK_DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_STATUS_FETCH_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

TIKTOK_MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024  # 64 MiB
TIKTOK_DEFAULT_CHUNK_BYTES = 10 * 1024 * 1024  # 10 MiB
TIKTOK_POLL_INTERVALS = (2.0, 4.0, 6.0, 10.0, 15.0, 20.0, 20.0, 20.0, 20.0, 20.0)

INBOX_NOTICE = (
    "Video enviado como borrador al Inbox de TikTok. Abre la app móvil de TikTok para revisarlo "
    "y completar la publicación."
)


def _check_tiktok_response(
    resp: httpx.Response,
    *,
    context: str,
    external_id: str | None = None,
) -> dict[str, Any]:
    if resp.status_code in (401, 403):
        raise AuthExpiredError(
            f"Token de TikTok rechazado o expirado durante {context}; reconecta la cuenta.",
            external_id=external_id,
        )
    if resp.status_code in (429, 500, 502, 503, 504):
        raise TransientPublishError(
            f"TikTok devolvió HTTP {resp.status_code} durante {context}.",
            external_id=external_id,
        )
    if resp.status_code >= 400:
        raise PermanentPublishError(
            f"TikTok rechazó la petición durante {context} (HTTP {resp.status_code}).",
            external_id=external_id,
        )
    payload = resp.json()
    err = payload.get("error") or {}
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip().lower()
        if code and code != "ok":
            msg = str(err.get("message") or code)
            if code in ("access_token_invalid", "invalid_token", "scope_not_authorized"):
                raise AuthExpiredError(
                    f"TikTok rechazó las credenciales ({code}): {msg}",
                    external_id=external_id,
                )
            if code in (
                "rate_limit_exceeded",
                "internal_error",
                "spam_risk_too_many_pending_share",
            ):
                raise TransientPublishError(
                    f"Error temporal de TikTok ({code}): {msg}",
                    external_id=external_id,
                )
            raise PermanentPublishError(
                f"TikTok devolvió error ({code}): {msg}",
                external_id=external_id,
            )
    return payload


def _compute_chunks(video_size: int) -> tuple[int, int]:
    """Devuelve `(chunk_size, total_chunk_count)` compatibles con TikTok API v2."""
    if video_size <= TIKTOK_MAX_SINGLE_CHUNK_BYTES:
        return video_size, 1
    chunk_size = TIKTOK_DEFAULT_CHUNK_BYTES
    total = math.ceil(video_size / chunk_size)
    return chunk_size, total


class TikTokApiPublisher:
    """Publicador oficial de TikTok (Direct Post o borrador Inbox) con `httpx`."""

    platform: Literal["tiktok"] = "tiktok"

    def __init__(
        self,
        *,
        settings: Settings,
        session: Session | None = None,
        http_client: httpx.Client | None = None,
        on_progress: ProgressCallback | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        poll_intervals: tuple[float, ...] = TIKTOK_POLL_INTERVALS,
    ) -> None:
        self.settings = settings
        self.session = session
        self.storage = LocalStorage(settings.storage_dir)
        self.http_client = http_client
        self.on_progress = on_progress
        self._sleep = sleep_fn
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
        warnings = validate_publish_meta("tiktok", meta)
        if not clip.path:
            raise PublishValidationError("El clip no tiene archivo renderizado para publicar")
        try:
            clip_path = self.storage.resolve_safe(clip.path)
        except StoragePathError as exc:
            raise PublishValidationError(str(exc)) from exc
        if not clip_path.is_file():
            raise PublishValidationError(f"No existe el archivo de video del clip: {clip.path}")

        video_size = clip_path.stat().st_size
        if video_size <= 0:
            raise PublishValidationError("El archivo de video del clip está vacío")

        can_direct = bool((account.capabilities_json or {}).get("direct_post"))
        use_direct = can_direct and meta.delivery_mode == "direct"
        if meta.delivery_mode == "direct" and not can_direct:
            warnings.append(
                "Esta cuenta de TikTok solo tiene permiso `video.upload` (sin auditoría "
                "`video.publish`); se envió como borrador al Inbox."
            )

        owns_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=60.0)
        try:
            self._report(5.0, "auth")
            creds = self._get_credentials(account, client)
            access_token = str(creds.get("access_token") or "").strip()
            if not access_token:
                raise AuthExpiredError("Falta access_token de TikTok; reconecta la cuenta")

            auth_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            }

            publish_id = meta.existing_external_id
            if publish_id:
                logger.info("reconciliando publish_id=%s existente en TikTok", publish_id)
                self._report(75.0, "polling")
            else:
                chunk_size, total_chunks = _compute_chunks(video_size)
                source_info = {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunks,
                }
                if use_direct:
                    init_url = TIKTOK_DIRECT_INIT_URL
                    init_body: dict[str, Any] = {
                        "post_info": {
                            "title": (meta.caption or meta.title or clip.title)[:2200],
                            "privacy_level": meta.privacy_level,
                            "disable_duet": meta.disable_duet,
                            "disable_comment": meta.disable_comment,
                            "disable_stitch": meta.disable_stitch,
                        },
                        "source_info": source_info,
                    }
                else:
                    init_url = TIKTOK_INBOX_INIT_URL
                    init_body = {"source_info": source_info}

                self._report(12.0, "init_upload")
                try:
                    init_resp = client.post(init_url, headers=auth_headers, json=init_body)
                except httpx.HTTPError as exc:
                    raise TransientPublishError(
                        f"Error de red iniciando subida a TikTok ({type(exc).__name__})"
                    ) from exc

                init_payload = _check_tiktok_response(init_resp, context="init")
                data = init_payload.get("data") or {}
                publish_id = str(data.get("publish_id") or "").strip()
                upload_url = str(data.get("upload_url") or "").strip()
                if not publish_id or not upload_url:
                    raise PermanentPublishError(
                        "TikTok no devolvió `publish_id` o `upload_url` al inicializar la subida"
                    )

                self._report(18.0, "uploading")
                with clip_path.open("rb") as fh:
                    offset = 0
                    for idx in range(total_chunks):
                        chunk = fh.read(chunk_size)
                        if not chunk:
                            break
                        end_byte = offset + len(chunk) - 1
                        put_headers = {
                            "Content-Type": "video/mp4",
                            "Content-Range": f"bytes {offset}-{end_byte}/{video_size}",
                            "Content-Length": str(len(chunk)),
                        }
                        try:
                            put_resp = client.put(upload_url, headers=put_headers, content=chunk)
                        except httpx.HTTPError as exc:
                            raise TransientPublishError(
                                f"Error de red subiendo chunk a TikTok ({type(exc).__name__})",
                                external_id=publish_id,
                            ) from exc
                        if put_resp.status_code in (429, 500, 502, 503, 504):
                            raise TransientPublishError(
                                "Error temporal subiendo video a TikTok "
                                f"(HTTP {put_resp.status_code})",
                                external_id=publish_id,
                            )
                        if put_resp.status_code not in (200, 201, 206):
                            raise PermanentPublishError(
                                "Falló la transferencia del video a TikTok "
                                f"(HTTP {put_resp.status_code})",
                                external_id=publish_id,
                            )
                        offset += len(chunk)
                        pct = 18.0 + (idx + 1) / total_chunks * 57.0
                        self._report(min(75.0, pct), "uploading")

            # Polling de estado remoto
            self._report(80.0, "polling")
            final_status_str = ""
            external_url: str | None = meta.existing_external_url
            for attempt_idx, delay in enumerate(self._poll_intervals):
                try:
                    status_resp = client.post(
                        TIKTOK_STATUS_FETCH_URL,
                        headers=auth_headers,
                        json={"publish_id": publish_id},
                    )
                except httpx.HTTPError as exc:
                    raise TransientPublishError(
                        f"Error de red consultando estado en TikTok ({type(exc).__name__})",
                        external_id=publish_id,
                    ) from exc

                status_payload = _check_tiktok_response(
                    status_resp, context="status/fetch", external_id=publish_id
                )
                status_data = status_payload.get("data") or {}
                final_status_str = str(status_data.get("status") or "").upper()

                if final_status_str == "PUBLISH_COMPLETE":
                    post_ids = status_data.get("publicaly_available_post_id") or []
                    if post_ids and account.handle:
                        clean_handle = account.handle.lstrip("@")
                        external_url = f"https://www.tiktok.com/@{clean_handle}/video/{post_ids[0]}"
                    self._report(100.0, "done")
                    return PublishResult(
                        external_id=publish_id,
                        external_url=external_url,
                        delivery_mode="direct",
                        status="published",
                        warnings=warnings,
                        raw_status=final_status_str,
                    )

                if final_status_str == "SEND_TO_USER_INBOX":
                    if INBOX_NOTICE not in warnings:
                        warnings.append(INBOX_NOTICE)
                    self._report(100.0, "done")
                    return PublishResult(
                        external_id=publish_id,
                        external_url=external_url,
                        delivery_mode="inbox",
                        status="published",
                        warnings=warnings,
                        raw_status=final_status_str,
                    )

                if final_status_str == "FAILED":
                    fail_reason = str(status_data.get("fail_reason") or "Error remoto en TikTok")
                    raise PermanentPublishError(
                        f"TikTok rechazó la publicación: {fail_reason}",
                        external_id=publish_id,
                    )

                pct = 80.0 + min(18.0, (attempt_idx + 1) * 2.0)
                self._report(pct, "polling")
                if attempt_idx < len(self._poll_intervals) - 1:
                    self._sleep(delay)

            raise TransientPublishError(
                "TikTok sigue procesando el video "
                f"(último estado: {final_status_str or 'desconocido'}).",
                external_id=publish_id,
            )
        finally:
            if owns_client:
                client.close()
