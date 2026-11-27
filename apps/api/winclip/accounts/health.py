"""Refresco automático de tokens OAuth y comprobación de salud (`design.md`, decisión 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session

from winclip.accounts.crypto import (
    CredentialDecryptionError,
    CredentialsNotFoundError,
    LocalCredentialStore,
)
from winclip.accounts.oauth import (
    META_GRAPH_VERSION,
    META_TOKEN_URI,
    TIKTOK_TOKEN_URI,
    TIKTOK_USER_INFO_URL,
    YOUTUBE_CHANNELS_URL,
    YOUTUBE_DEFAULT_TOKEN_URI,
)
from winclip.core.config import Settings
from winclip.core.models import SocialAccount, utcnow

DEFAULT_REFRESH_MARGIN_SECONDS = 300
INSTAGRAM_REFRESH_MARGIN_SECONDS = 10 * 24 * 3600


class AccountHealthError(RuntimeError):
    """Error durante el refresco o verificación de una cuenta."""


class TokenExpiredError(AccountHealthError):
    """El token expiró o fue revocado y requiere reconexión del usuario."""


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _needs_refresh(platform: str, expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    margin = (
        INSTAGRAM_REFRESH_MARGIN_SECONDS
        if platform == "instagram"
        else DEFAULT_REFRESH_MARGIN_SECONDS
    )
    return expires_at <= datetime.now(UTC) + timedelta(seconds=margin)


def _refresh_youtube(creds: dict[str, Any], client: httpx.Client) -> dict[str, Any]:
    refresh_token = str(creds.get("refresh_token") or "").strip()
    if not refresh_token:
        raise TokenExpiredError("Token de YouTube expirado sin refresh_token; reconecta la cuenta")

    token_uri = str(creds.get("token_uri") or YOUTUBE_DEFAULT_TOKEN_URI)
    resp = client.post(
        token_uri,
        data={
            "client_id": creds.get("client_id", ""),
            "client_secret": creds.get("client_secret", ""),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    if resp.status_code in (400, 401, 403):
        raise TokenExpiredError("El token de YouTube fue revocado o expiró; reconecta la cuenta")
    if resp.status_code >= 400:
        raise AccountHealthError(f"Error al refrescar token de YouTube (HTTP {resp.status_code})")

    data = resp.json()
    new_access = data.get("access_token")
    if not new_access:
        raise TokenExpiredError("Google no devolvió un nuevo access_token")

    updated = dict(creds)
    updated["access_token"] = new_access
    if data.get("refresh_token"):
        updated["refresh_token"] = data["refresh_token"]
    expires_in = data.get("expires_in")
    if expires_in:
        updated["expires_at"] = (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()
    return updated


def _refresh_tiktok(
    creds: dict[str, Any], settings: Settings, client: httpx.Client
) -> dict[str, Any]:
    refresh_token = str(creds.get("refresh_token") or "").strip()
    if not refresh_token:
        raise TokenExpiredError("Token de TikTok expirado sin refresh_token; reconecta la cuenta")

    client_key = settings.tiktok_client_key.get_secret_value().strip() or str(
        creds.get("client_key") or ""
    )
    client_secret = settings.tiktok_client_secret.get_secret_value().strip() or str(
        creds.get("client_secret") or ""
    )
    resp = client.post(
        TIKTOK_TOKEN_URI,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    if resp.status_code in (400, 401, 403):
        raise TokenExpiredError("El token de TikTok expiró o fue revocado; reconecta la cuenta")
    if resp.status_code >= 400:
        raise AccountHealthError(f"Error al refrescar token de TikTok (HTTP {resp.status_code})")

    data = resp.json()
    if data.get("error"):
        raise TokenExpiredError(
            f"TikTok rechazó el refresco de sesión ({data.get('error')}); reconecta la cuenta"
        )
    new_access = data.get("access_token")
    if not new_access:
        raise TokenExpiredError("TikTok no devolvió un nuevo access_token")

    updated = dict(creds)
    updated["access_token"] = new_access
    if data.get("refresh_token"):
        updated["refresh_token"] = data["refresh_token"]
    if data.get("expires_in"):
        updated["expires_at"] = (
            datetime.now(UTC) + timedelta(seconds=int(data["expires_in"]))
        ).isoformat()
    return updated


def _refresh_instagram(
    creds: dict[str, Any], settings: Settings, client: httpx.Client
) -> dict[str, Any]:
    current_token = str(creds.get("access_token") or "").strip()
    if not current_token:
        raise TokenExpiredError("Token de Instagram ausente; reconecta la cuenta")

    app_id = settings.meta_app_id.strip()
    app_secret = settings.meta_app_secret.get_secret_value().strip()
    if not app_id or not app_secret:
        raise TokenExpiredError(
            "Faltan META_APP_ID/META_APP_SECRET para renovar el token de Instagram"
        )

    resp = client.get(
        META_TOKEN_URI,
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": current_token,
        },
        timeout=20.0,
    )
    if resp.status_code in (400, 401, 403):
        raise TokenExpiredError("El token de Instagram expiró o fue revocado; reconecta la cuenta")
    if resp.status_code >= 400:
        raise AccountHealthError(f"Error al renovar token de Instagram (HTTP {resp.status_code})")

    data = resp.json()
    new_token = data.get("access_token")
    if not new_token:
        raise TokenExpiredError("Meta no devolvió un token renovado")

    updated = dict(creds)
    updated["access_token"] = new_token
    if data.get("expires_in"):
        updated["expires_at"] = (
            datetime.now(UTC) + timedelta(seconds=int(data["expires_in"]))
        ).isoformat()
    return updated


def get_valid_credentials(
    session: Session,
    account: SocialAccount,
    settings: Settings,
    *,
    http_client: httpx.Client | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Devuelve credenciales OAuth válidas, refrescando y re-cifrando si expiran pronto."""
    store = LocalCredentialStore(settings)
    creds = store.load_credentials(account.id)
    expires_at = _parse_iso_datetime(creds.get("expires_at")) or account.token_expires_at
    missing_access = not str(creds.get("access_token") or "").strip()

    if (
        not force_refresh
        and not missing_access
        and not _needs_refresh(account.platform, expires_at)
    ):
        return creds

    owns_client = http_client is None
    client = http_client or httpx.Client()
    try:
        if account.platform == "youtube":
            updated = _refresh_youtube(creds, client)
        elif account.platform == "tiktok":
            updated = _refresh_tiktok(creds, settings, client)
        elif account.platform == "instagram":
            updated = _refresh_instagram(creds, settings, client)
        else:
            raise AccountHealthError(f"Plataforma no soportada: {account.platform}")
    except httpx.HTTPError as exc:
        raise AccountHealthError(
            f"Error de red al refrescar credenciales ({type(exc).__name__})"
        ) from exc
    finally:
        if owns_client:
            client.close()

    store.save_credentials(account.id, updated)
    new_expires = _parse_iso_datetime(updated.get("expires_at"))
    account.token_expires_at = new_expires
    account.updated_at = utcnow()
    session.add(account)
    session.commit()
    return updated


def _fetch_profile(
    platform: str, creds: dict[str, Any], client: httpx.Client
) -> tuple[str | None, str | None, str | None, str | None]:
    """Devuelve `(external_id, display_name, handle, avatar_url)` desde la API remota."""
    access_token = str(creds.get("access_token") or "")
    if platform == "youtube":
        resp = client.get(
            YOUTUBE_CHANNELS_URL,
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        if resp.status_code in (401, 403):
            raise TokenExpiredError("Credenciales de YouTube rechazadas o revocadas")
        if resp.status_code >= 400:
            raise AccountHealthError(f"Error consultando YouTube (HTTP {resp.status_code})")
        items = resp.json().get("items") or []
        if not items:
            raise AccountHealthError("No se encontró ningún canal asociado a la cuenta de YouTube")
        channel = items[0]
        snippet = channel.get("snippet") or {}
        thumbs = snippet.get("thumbnails") or {}
        avatar = (
            (thumbs.get("high") or {}).get("url")
            or (thumbs.get("medium") or {}).get("url")
            or (thumbs.get("default") or {}).get("url")
        )
        raw_handle = str(snippet.get("customUrl") or "")
        handle = raw_handle if not raw_handle or raw_handle.startswith("@") else f"@{raw_handle}"
        return str(channel.get("id") or "") or None, snippet.get("title"), handle or None, avatar

    if platform == "tiktok":
        resp = client.get(
            TIKTOK_USER_INFO_URL,
            params={"fields": "open_id,display_name,avatar_url,username"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        if resp.status_code in (401, 403):
            raise TokenExpiredError("Credenciales de TikTok rechazadas o revocadas")
        if resp.status_code >= 400:
            raise AccountHealthError(f"Error consultando TikTok (HTTP {resp.status_code})")
        payload = resp.json()
        err = payload.get("error") or {}
        if isinstance(err, dict) and err.get("code") not in (None, "", "ok"):
            if str(err.get("code")) in ("access_token_invalid", "invalid_token"):
                raise TokenExpiredError("Token de TikTok inválido o revocado")
            raise AccountHealthError(f"TikTok devolvió error: {err.get('message') or err['code']}")
        user = (payload.get("data") or {}).get("user") or {}
        username = str(user.get("username") or "")
        handle = f"@{username}" if username and not username.startswith("@") else username
        return (
            user.get("open_id") or creds.get("open_id"),
            user.get("display_name"),
            handle or None,
            user.get("avatar_url"),
        )

    if platform == "instagram":
        ig_user_id = str(creds.get("ig_user_id") or "")
        if not ig_user_id:
            raise AccountHealthError("Falta ig_user_id en las credenciales de Instagram")
        page_token = str(creds.get("page_access_token") or access_token)
        resp = client.get(
            f"https://graph.facebook.com/{META_GRAPH_VERSION}/{ig_user_id}",
            params={
                "fields": "id,username,name,profile_picture_url",
                "access_token": page_token,
            },
            timeout=20.0,
        )
        if resp.status_code in (400, 401, 403):
            raise TokenExpiredError("Credenciales de Instagram rechazadas o expiradas")
        if resp.status_code >= 400:
            raise AccountHealthError(f"Error consultando Instagram (HTTP {resp.status_code})")
        data = resp.json()
        username = str(data.get("username") or "")
        handle = f"@{username}" if username and not username.startswith("@") else username
        return (
            str(data.get("id") or ig_user_id),
            data.get("name") or username or None,
            handle or None,
            data.get("profile_picture_url"),
        )

    raise AccountHealthError(f"Plataforma no soportada: {platform}")


def check_account(
    session: Session,
    account: SocialAccount,
    settings: Settings,
    *,
    http_client: httpx.Client | None = None,
) -> SocialAccount:
    """Ejecuta una comprobación de salud en vivo sobre la cuenta y actualiza SQLite."""
    now = utcnow()
    if account.auth_method == "playwright":
        from winclip.accounts.browser_login import check_browser_account_health

        return check_browser_account_health(session, account, settings)

    owns_client = http_client is None
    client = http_client or httpx.Client()
    try:
        creds = get_valid_credentials(session, account, settings, http_client=client)
        try:
            ext_id, display_name, handle, avatar_url = _fetch_profile(
                account.platform, creds, client
            )
        except TokenExpiredError:
            # Si el token parecía vigente pero la plataforma devolvió 401, reintentamos refrescar.
            creds = get_valid_credentials(
                session, account, settings, http_client=client, force_refresh=True
            )
            ext_id, display_name, handle, avatar_url = _fetch_profile(
                account.platform, creds, client
            )

        if ext_id:
            account.external_account_id = ext_id
        if display_name:
            account.display_name = display_name
        if handle:
            account.handle = handle
        if avatar_url:
            account.avatar_url = avatar_url
        account.token_expires_at = (
            _parse_iso_datetime(creds.get("expires_at")) or account.token_expires_at
        )
        account.status = "connected"
        account.last_error = None
        account.last_check_at = now
        account.updated_at = now
    except CredentialDecryptionError as exc:
        account.status = "error"
        account.last_error = str(exc)
        account.last_check_at = now
        account.updated_at = now
    except (TokenExpiredError, CredentialsNotFoundError) as exc:
        account.status = "expired"
        account.last_error = str(exc)
        account.last_check_at = now
        account.updated_at = now
    except (AccountHealthError, httpx.HTTPError) as exc:
        account.status = "error"
        account.last_error = str(exc)
        account.last_check_at = now
        account.updated_at = now
    finally:
        if owns_client:
            client.close()

    session.add(account)
    session.commit()
    session.refresh(account)
    return account
