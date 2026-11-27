"""Flujos OAuth 2.0 oficiales para YouTube, TikTok e Instagram Graph (`design.md`, decisión 2)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.repository import has_default_for_platform
from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_ulid
from winclip.core.models import ACCOUNT_PLATFORMS, SocialAccount, utcnow

OAUTH_STATE_TTL_SECONDS = 600
IG_SELECTION_TTL_SECONDS = 300

YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
)
YOUTUBE_DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
YOUTUBE_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

TIKTOK_AUTH_URI = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URI = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"

META_GRAPH_VERSION = "v21.0"
META_AUTH_URI = f"https://www.facebook.com/{META_GRAPH_VERSION}/dialog/oauth"
META_TOKEN_URI = f"https://graph.facebook.com/{META_GRAPH_VERSION}/oauth/access_token"
META_ME_ACCOUNTS_URL = f"https://graph.facebook.com/{META_GRAPH_VERSION}/me/accounts"
META_SCOPES = (
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
)


class OAuthError(RuntimeError):
    """Error base del flujo OAuth."""


class OAuthConfigError(OAuthError):
    """Faltan variables de entorno o archivos de cliente para la plataforma."""

    def __init__(self, message: str, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing = missing or []


class OAuthStateError(OAuthError):
    """El parámetro `state` OAuth no existe, expiró o no corresponde a la plataforma."""


class OAuthExchangeError(OAuthError):
    """Error al intercambiar el código OAuth o consultar el perfil remoto."""


@dataclass
class OAuthStateEntry:
    state: str
    platform: str
    workspace_id: str
    code_verifier: str
    expires_at: datetime
    account_id: str | None = None
    direct_post: bool = False
    alias: str | None = None


@dataclass
class InstagramCandidate:
    external_account_id: str
    username: str
    display_name: str
    avatar_url: str | None
    page_id: str
    page_name: str
    page_access_token: str


@dataclass
class PendingInstagramSelection:
    token: str
    workspace_id: str
    user_access_token: str
    token_expires_at: datetime | None
    candidates: list[InstagramCandidate]
    expires_at: datetime
    account_id: str | None = None
    alias: str | None = None


@dataclass
class OAuthStartResult:
    auth_url: str
    state: str
    platform: str


@dataclass
class OAuthCallbackResult:
    platform: str
    accounts: list[SocialAccount] = field(default_factory=list)
    pending_selection_token: str | None = None
    instagram_candidates: list[InstagramCandidate] = field(default_factory=list)


class OAuthStateManager:
    """Almacén en memoria de estados anti-CSRF y selecciones temporales de Instagram."""

    def __init__(self) -> None:
        self._states: dict[str, OAuthStateEntry] = {}
        self._ig_selections: dict[str, PendingInstagramSelection] = {}

    def _purge_expired(self) -> None:
        now = utcnow()
        self._states = {k: v for k, v in self._states.items() if v.expires_at > now}
        self._ig_selections = {k: v for k, v in self._ig_selections.items() if v.expires_at > now}

    def create_state(
        self,
        *,
        platform: str,
        workspace_id: str,
        account_id: str | None = None,
        direct_post: bool = False,
        alias: str | None = None,
        ttl_seconds: int = OAUTH_STATE_TTL_SECONDS,
    ) -> OAuthStateEntry:
        self._purge_expired()
        entry = OAuthStateEntry(
            state=secrets.token_urlsafe(32),
            platform=platform,
            workspace_id=workspace_id,
            code_verifier=_generate_code_verifier(),
            expires_at=utcnow() + timedelta(seconds=ttl_seconds),
            account_id=account_id,
            direct_post=direct_post,
            alias=alias,
        )
        self._states[entry.state] = entry
        return entry

    def consume_state(self, state: str, platform: str) -> OAuthStateEntry:
        self._purge_expired()
        entry = self._states.pop(state, None)
        if entry is None:
            raise OAuthStateError("Estado OAuth inválido o expirado; vuelve a iniciar la conexión")
        if entry.platform != platform:
            raise OAuthStateError("El estado OAuth no corresponde a la plataforma solicitada")
        return entry

    def create_ig_selection(
        self,
        *,
        workspace_id: str,
        user_access_token: str,
        token_expires_at: datetime | None,
        candidates: list[InstagramCandidate],
        account_id: str | None = None,
        alias: str | None = None,
        ttl_seconds: int = IG_SELECTION_TTL_SECONDS,
    ) -> PendingInstagramSelection:
        self._purge_expired()
        selection = PendingInstagramSelection(
            token=secrets.token_urlsafe(24),
            workspace_id=workspace_id,
            user_access_token=user_access_token,
            token_expires_at=token_expires_at,
            candidates=candidates,
            expires_at=utcnow() + timedelta(seconds=ttl_seconds),
            account_id=account_id,
            alias=alias,
        )
        self._ig_selections[selection.token] = selection
        return selection

    def get_ig_selection(self, token: str) -> PendingInstagramSelection:
        self._purge_expired()
        selection = self._ig_selections.get(token)
        if selection is None:
            raise OAuthStateError(
                "La selección de cuentas de Instagram expiró; vuelve a conectar con Meta"
            )
        return selection

    def consume_ig_selection(self, token: str) -> PendingInstagramSelection:
        self._purge_expired()
        selection = self._ig_selections.pop(token, None)
        if selection is None:
            raise OAuthStateError(
                "La selección de cuentas de Instagram expiró; vuelve a conectar con Meta"
            )
        return selection


_DEFAULT_STATE_MANAGER = OAuthStateManager()


def get_oauth_state_manager() -> OAuthStateManager:
    return _DEFAULT_STATE_MANAGER


def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def _code_challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _redirect_uri(settings: Settings, platform: str) -> str:
    return f"http://localhost:{settings.api_port}/api/accounts/oauth/{platform}/callback"


def _load_google_client_config(settings: Settings) -> dict[str, Any]:
    raw_path = settings.google_client_secret_file.strip()
    if not raw_path:
        raise OAuthConfigError(
            "Falta GOOGLE_CLIENT_SECRET_FILE en .env para conectar YouTube por API oficial",
            missing=["GOOGLE_CLIENT_SECRET_FILE"],
        )
    secret_path = Path(raw_path).expanduser()
    if not secret_path.is_file():
        raise OAuthConfigError(
            f"GOOGLE_CLIENT_SECRET_FILE apunta a una ruta inexistente: {secret_path}",
            missing=["GOOGLE_CLIENT_SECRET_FILE"],
        )
    try:
        data = json.loads(secret_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OAuthConfigError(
            "No se pudo leer el archivo JSON de GOOGLE_CLIENT_SECRET_FILE",
            missing=["GOOGLE_CLIENT_SECRET_FILE"],
        ) from exc

    section = data.get("installed") or data.get("web") or data
    client_id = section.get("client_id")
    client_secret = section.get("client_secret")
    if not client_id or not client_secret:
        raise OAuthConfigError(
            "GOOGLE_CLIENT_SECRET_FILE no contiene client_id y client_secret válidos",
            missing=["GOOGLE_CLIENT_SECRET_FILE"],
        )
    return {
        "client_id": str(client_id),
        "client_secret": str(client_secret),
        "auth_uri": str(section.get("auth_uri") or YOUTUBE_DEFAULT_AUTH_URI),
        "token_uri": str(section.get("token_uri") or YOUTUBE_DEFAULT_TOKEN_URI),
    }


def check_platform_oauth_config(platform: str, settings: Settings) -> tuple[bool, list[str]]:
    """Comprueba si la plataforma tiene las variables OAuth configuradas (sin revelar valores)."""
    if platform == "youtube":
        raw_path = settings.google_client_secret_file.strip()
        if not raw_path or not Path(raw_path).expanduser().is_file():
            return False, ["GOOGLE_CLIENT_SECRET_FILE"]
        return True, []
    if platform == "tiktok":
        missing: list[str] = []
        if not settings.tiktok_client_key.get_secret_value().strip():
            missing.append("TIKTOK_CLIENT_KEY")
        if not settings.tiktok_client_secret.get_secret_value().strip():
            missing.append("TIKTOK_CLIENT_SECRET")
        return not missing, missing
    if platform == "instagram":
        missing = []
        if not settings.meta_app_id.strip():
            missing.append("META_APP_ID")
        if not settings.meta_app_secret.get_secret_value().strip():
            missing.append("META_APP_SECRET")
        return not missing, missing
    raise OAuthConfigError(f"Plataforma no soportada: {platform}")


def start_oauth(
    platform: str,
    settings: Settings,
    *,
    workspace_id: str,
    account_id: str | None = None,
    direct_post: bool = False,
    alias: str | None = None,
    state_manager: OAuthStateManager | None = None,
) -> OAuthStartResult:
    """Inicia un flujo OAuth 2.0 y devuelve la URL de autorización con state anti-CSRF y PKCE."""
    if platform not in ACCOUNT_PLATFORMS:
        raise OAuthConfigError(f"Plataforma no soportada: {platform}")

    manager = state_manager or get_oauth_state_manager()
    redirect_uri = _redirect_uri(settings, platform)

    if platform == "youtube":
        cfg = _load_google_client_config(settings)
        entry = manager.create_state(
            platform="youtube",
            workspace_id=workspace_id,
            account_id=account_id,
            alias=alias,
        )
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": entry.state,
            "code_challenge": _code_challenge_s256(entry.code_verifier),
            "code_challenge_method": "S256",
        }
        return OAuthStartResult(
            auth_url=f"{cfg['auth_uri']}?{urlencode(params)}",
            state=entry.state,
            platform="youtube",
        )

    if platform == "tiktok":
        ok, missing = check_platform_oauth_config("tiktok", settings)
        if not ok:
            raise OAuthConfigError(
                f"Faltan variables en .env para conectar TikTok por API: {', '.join(missing)}",
                missing=missing,
            )
        entry = manager.create_state(
            platform="tiktok",
            workspace_id=workspace_id,
            account_id=account_id,
            direct_post=direct_post,
            alias=alias,
        )
        scopes = ["user.info.basic", "video.upload"]
        if direct_post:
            scopes.append("video.publish")
        params = {
            "client_key": settings.tiktok_client_key.get_secret_value().strip(),
            "response_type": "code",
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
            "state": entry.state,
            "code_challenge": _code_challenge_s256(entry.code_verifier),
            "code_challenge_method": "S256",
        }
        return OAuthStartResult(
            auth_url=f"{TIKTOK_AUTH_URI}?{urlencode(params)}",
            state=entry.state,
            platform="tiktok",
        )

    # Instagram Graph (Meta)
    ok, missing = check_platform_oauth_config("instagram", settings)
    if not ok:
        raise OAuthConfigError(
            f"Faltan variables en .env para conectar Instagram Graph: {', '.join(missing)}",
            missing=missing,
        )
    entry = manager.create_state(
        platform="instagram",
        workspace_id=workspace_id,
        account_id=account_id,
        alias=alias,
    )
    params = {
        "client_id": settings.meta_app_id.strip(),
        "redirect_uri": redirect_uri,
        "state": entry.state,
        "scope": ",".join(META_SCOPES),
        "response_type": "code",
    }
    return OAuthStartResult(
        auth_url=f"{META_AUTH_URI}?{urlencode(params)}",
        state=entry.state,
        platform="instagram",
    )


def _upsert_oauth_account(
    session: Session,
    settings: Settings,
    *,
    workspace_id: str,
    platform: str,
    display_name: str,
    handle: str,
    avatar_url: str | None,
    external_account_id: str | None,
    capabilities: dict[str, Any],
    token_expires_at: datetime | None,
    credentials_payload: dict[str, Any],
    account_id: str | None = None,
    alias: str | None = None,
) -> SocialAccount:
    store = LocalCredentialStore(settings)
    now = utcnow()

    account: SocialAccount | None = None
    if account_id:
        account = session.get(SocialAccount, account_id)

    if account is None:
        new_id = new_ulid()
        creds_ref = store.save_credentials(new_id, credentials_payload)
        is_default = not has_default_for_platform(session, workspace_id, platform)
        account = SocialAccount(
            id=new_id,
            workspace_id=workspace_id,
            platform=platform,
            display_name=display_name,
            handle=handle,
            alias=alias,
            avatar_url=avatar_url,
            auth_method="api",
            credentials_ref=creds_ref,
            status="connected",
            is_default=is_default,
            capabilities_json=capabilities,
            external_account_id=external_account_id,
            token_expires_at=token_expires_at,
            last_check_at=now,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
    else:
        creds_ref = store.save_credentials(account.id, credentials_payload)
        account.display_name = display_name or account.display_name
        account.handle = handle or account.handle
        if alias is not None:
            account.alias = alias
        account.avatar_url = avatar_url or account.avatar_url
        account.auth_method = "api"
        account.credentials_ref = creds_ref
        account.status = "connected"
        account.capabilities_json = capabilities
        account.external_account_id = external_account_id or account.external_account_id
        account.token_expires_at = token_expires_at
        account.last_check_at = now
        account.last_error = None
        account.updated_at = now

    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _parse_expires_at(expires_in: Any) -> datetime | None:
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _complete_youtube_oauth(
    session: Session,
    settings: Settings,
    entry: OAuthStateEntry,
    code: str,
    client: httpx.Client,
) -> OAuthCallbackResult:
    cfg = _load_google_client_config(settings)
    redirect_uri = _redirect_uri(settings, "youtube")
    token_resp = client.post(
        cfg["token_uri"],
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": entry.code_verifier,
        },
        timeout=20.0,
    )
    if token_resp.status_code >= 400:
        raise OAuthExchangeError(
            f"Google rechazó el intercambio de código OAuth (HTTP {token_resp.status_code})"
        )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthExchangeError("Google no devolvió access_token en el intercambio OAuth")

    expires_at = _parse_expires_at(token_data.get("expires_in"))
    granted_scopes = [s for s in str(token_data.get("scope", "")).split() if s] or list(
        YOUTUBE_SCOPES
    )

    profile_resp = client.get(
        YOUTUBE_CHANNELS_URL,
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20.0,
    )
    if profile_resp.status_code >= 400:
        raise OAuthExchangeError(
            f"No se pudo consultar el canal de YouTube (HTTP {profile_resp.status_code})"
        )
    items = profile_resp.json().get("items") or []
    if not items:
        raise OAuthExchangeError("La cuenta de Google autorizada no tiene un canal de YouTube")

    channel = items[0]
    snippet = channel.get("snippet") or {}
    thumbnails = snippet.get("thumbnails") or {}
    avatar_url = (
        (thumbnails.get("high") or {}).get("url")
        or (thumbnails.get("medium") or {}).get("url")
        or (thumbnails.get("default") or {}).get("url")
    )
    channel_id = str(channel.get("id") or "")
    display_name = str(snippet.get("title") or "YouTube Channel")
    raw_handle = str(snippet.get("customUrl") or "")
    handle = raw_handle if not raw_handle or raw_handle.startswith("@") else f"@{raw_handle}"

    creds_payload = {
        "provider": "youtube",
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token", ""),
        "token_uri": cfg["token_uri"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scopes": granted_scopes,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    capabilities = {
        "direct_post": "https://www.googleapis.com/auth/youtube.upload" in granted_scopes,
        "scopes": granted_scopes,
    }
    account = _upsert_oauth_account(
        session,
        settings,
        workspace_id=entry.workspace_id,
        platform="youtube",
        display_name=display_name,
        handle=handle,
        avatar_url=avatar_url,
        external_account_id=channel_id or None,
        capabilities=capabilities,
        token_expires_at=expires_at,
        credentials_payload=creds_payload,
        account_id=entry.account_id,
        alias=entry.alias,
    )
    return OAuthCallbackResult(platform="youtube", accounts=[account])


def _complete_tiktok_oauth(
    session: Session,
    settings: Settings,
    entry: OAuthStateEntry,
    code: str,
    client: httpx.Client,
) -> OAuthCallbackResult:
    client_key = settings.tiktok_client_key.get_secret_value().strip()
    client_secret = settings.tiktok_client_secret.get_secret_value().strip()
    redirect_uri = _redirect_uri(settings, "tiktok")

    token_resp = client.post(
        TIKTOK_TOKEN_URI,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": entry.code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    if token_resp.status_code >= 400:
        raise OAuthExchangeError(
            f"TikTok rechazó el intercambio de código OAuth (HTTP {token_resp.status_code})"
        )
    token_data = token_resp.json()
    if token_data.get("error"):
        raise OAuthExchangeError(
            f"Error OAuth de TikTok: {token_data.get('error_description') or token_data['error']}"
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthExchangeError("TikTok no devolvió access_token")

    expires_at = _parse_expires_at(token_data.get("expires_in"))
    refresh_expires_at = _parse_expires_at(token_data.get("refresh_expires_in"))
    raw_scope = str(token_data.get("scope") or "")
    granted_scopes = [s.strip() for s in raw_scope.replace(" ", ",").split(",") if s.strip()]
    direct_post = "video.publish" in granted_scopes
    capabilities = {
        "direct_post": direct_post,
        "inbox_only": not direct_post,
        "scopes": granted_scopes,
    }

    open_id = str(token_data.get("open_id") or "")
    display_name = "TikTok Account"
    handle = ""
    avatar_url: str | None = None

    tiktok_fields = (
        "open_id,display_name,avatar_url,username"
        if "user.info.profile" in granted_scopes
        else "open_id,display_name,avatar_url"
    )
    user_resp = client.get(
        TIKTOK_USER_INFO_URL,
        params={"fields": tiktok_fields},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20.0,
    )
    if user_resp.status_code < 400:
        user_data = (user_resp.json().get("data") or {}).get("user") or {}
        open_id = str(user_data.get("open_id") or open_id)
        display_name = str(user_data.get("display_name") or display_name)
        username = str(user_data.get("username") or "")
        handle = f"@{username}" if username and not username.startswith("@") else username
        avatar_url = user_data.get("avatar_url")

    creds_payload = {
        "provider": "tiktok",
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token", ""),
        "open_id": open_id,
        "scopes": granted_scopes,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "refresh_expires_at": refresh_expires_at.isoformat() if refresh_expires_at else None,
    }
    account = _upsert_oauth_account(
        session,
        settings,
        workspace_id=entry.workspace_id,
        platform="tiktok",
        display_name=display_name,
        handle=handle,
        avatar_url=avatar_url,
        external_account_id=open_id or None,
        capabilities=capabilities,
        token_expires_at=expires_at,
        credentials_payload=creds_payload,
        account_id=entry.account_id,
        alias=entry.alias,
    )
    return OAuthCallbackResult(platform="tiktok", accounts=[account])


def _complete_instagram_oauth(
    session: Session,
    settings: Settings,
    entry: OAuthStateEntry,
    code: str,
    client: httpx.Client,
    state_manager: OAuthStateManager,
) -> OAuthCallbackResult:
    app_id = settings.meta_app_id.strip()
    app_secret = settings.meta_app_secret.get_secret_value().strip()
    redirect_uri = _redirect_uri(settings, "instagram")

    short_resp = client.get(
        META_TOKEN_URI,
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=20.0,
    )
    if short_resp.status_code >= 400:
        raise OAuthExchangeError(f"Meta rechazó el código OAuth (HTTP {short_resp.status_code})")
    short_token = short_resp.json().get("access_token")
    if not short_token:
        raise OAuthExchangeError("Meta no devolvió access_token")

    long_resp = client.get(
        META_TOKEN_URI,
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=20.0,
    )
    if long_resp.status_code >= 400:
        raise OAuthExchangeError(
            f"No se pudo obtener token de larga duración en Meta (HTTP {long_resp.status_code})"
        )
    long_data = long_resp.json()
    long_token = long_data.get("access_token") or short_token
    expires_at = _parse_expires_at(long_data.get("expires_in"))

    pages_resp = client.get(
        META_ME_ACCOUNTS_URL,
        params={
            "fields": (
                "id,name,access_token,"
                "instagram_business_account{id,username,name,profile_picture_url}"
            ),
            "access_token": long_token,
        },
        timeout=20.0,
    )
    if pages_resp.status_code >= 400:
        raise OAuthExchangeError(
            "No se pudieron consultar las páginas de Facebook/Instagram "
            f"(HTTP {pages_resp.status_code})"
        )

    candidates: list[InstagramCandidate] = []
    for page in pages_resp.json().get("data") or []:
        ig = page.get("instagram_business_account")
        if not isinstance(ig, dict) or not ig.get("id"):
            continue
        username = str(ig.get("username") or "")
        candidates.append(
            InstagramCandidate(
                external_account_id=str(ig["id"]),
                username=username,
                display_name=str(ig.get("name") or username or page.get("name") or "Instagram"),
                avatar_url=ig.get("profile_picture_url"),
                page_id=str(page.get("id") or ""),
                page_name=str(page.get("name") or ""),
                page_access_token=str(page.get("access_token") or long_token),
            )
        )

    if not candidates:
        raise OAuthExchangeError(
            "No se encontraron cuentas Business o Creator de Instagram vinculadas a tus páginas"
        )

    if len(candidates) == 1:
        account = _save_instagram_candidate(
            session,
            settings,
            workspace_id=entry.workspace_id,
            candidate=candidates[0],
            user_access_token=long_token,
            token_expires_at=expires_at,
            account_id=entry.account_id,
            alias=entry.alias,
        )
        return OAuthCallbackResult(platform="instagram", accounts=[account])

    selection = state_manager.create_ig_selection(
        workspace_id=entry.workspace_id,
        user_access_token=long_token,
        token_expires_at=expires_at,
        candidates=candidates,
        account_id=entry.account_id,
        alias=entry.alias,
    )
    return OAuthCallbackResult(
        platform="instagram",
        pending_selection_token=selection.token,
        instagram_candidates=candidates,
    )


def _save_instagram_candidate(
    session: Session,
    settings: Settings,
    *,
    workspace_id: str,
    candidate: InstagramCandidate,
    user_access_token: str,
    token_expires_at: datetime | None,
    account_id: str | None = None,
    alias: str | None = None,
) -> SocialAccount:
    handle = (
        f"@{candidate.username}"
        if candidate.username and not candidate.username.startswith("@")
        else candidate.username
    )
    creds_payload = {
        "provider": "instagram",
        "access_token": user_access_token,
        "page_access_token": candidate.page_access_token,
        "page_id": candidate.page_id,
        "ig_user_id": candidate.external_account_id,
        "scopes": list(META_SCOPES),
        "expires_at": token_expires_at.isoformat() if token_expires_at else None,
    }
    capabilities = {
        "direct_post": True,
        "scopes": list(META_SCOPES),
        "page_name": candidate.page_name,
    }
    return _upsert_oauth_account(
        session,
        settings,
        workspace_id=workspace_id,
        platform="instagram",
        display_name=candidate.display_name,
        handle=handle,
        avatar_url=candidate.avatar_url,
        external_account_id=candidate.external_account_id,
        capabilities=capabilities,
        token_expires_at=token_expires_at,
        credentials_payload=creds_payload,
        account_id=account_id,
        alias=alias,
    )


def complete_oauth(
    session: Session,
    settings: Settings,
    *,
    platform: str,
    code: str,
    state: str,
    state_manager: OAuthStateManager | None = None,
    http_client: httpx.Client | None = None,
) -> OAuthCallbackResult:
    """Valida el state anti-CSRF, intercambia el código y registra/actualiza la cuenta."""
    if platform not in ACCOUNT_PLATFORMS:
        raise OAuthConfigError(f"Plataforma no soportada: {platform}")

    manager = state_manager or get_oauth_state_manager()
    entry = manager.consume_state(state, platform)
    ensure_default_workspace(session)

    owns_client = http_client is None
    client = http_client or httpx.Client()
    try:
        if platform == "youtube":
            return _complete_youtube_oauth(session, settings, entry, code, client)
        if platform == "tiktok":
            return _complete_tiktok_oauth(session, settings, entry, code, client)
        return _complete_instagram_oauth(session, settings, entry, code, client, manager)
    except httpx.HTTPError as exc:
        raise OAuthExchangeError(
            f"Error de red al completar OAuth con {platform}: {type(exc).__name__}"
        ) from exc
    finally:
        if owns_client:
            client.close()


def confirm_instagram_selection(
    session: Session,
    settings: Settings,
    *,
    selection_token: str,
    external_account_ids: list[str],
    state_manager: OAuthStateManager | None = None,
) -> list[SocialAccount]:
    """Persiste las cuentas Business/Creator de Instagram elegidas por el usuario."""
    manager = state_manager or get_oauth_state_manager()
    selection = manager.consume_ig_selection(selection_token)

    chosen_set = set(external_account_ids)
    selected = [c for c in selection.candidates if c.external_account_id in chosen_set]
    if not selected:
        raise OAuthExchangeError("Debes seleccionar al menos una cuenta válida de Instagram")

    accounts: list[SocialAccount] = []
    for idx, candidate in enumerate(selected):
        target_account_id = selection.account_id if idx == 0 else None
        target_alias = selection.alias if idx == 0 else None
        accounts.append(
            _save_instagram_candidate(
                session,
                settings,
                workspace_id=selection.workspace_id,
                candidate=candidate,
                user_access_token=selection.user_access_token,
                token_expires_at=selection.token_expires_at,
                account_id=target_account_id,
                alias=target_alias,
            )
        )
    return accounts
