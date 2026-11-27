"""Importación opcional en modo solo lectura de tokens locales (`design.md`, decisión 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.health import check_account
from winclip.accounts.oauth import YOUTUBE_DEFAULT_TOKEN_URI
from winclip.accounts.repository import has_default_for_platform
from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_ulid
from winclip.core.models import ACCOUNT_PLATFORMS, SocialAccount, utcnow


class TokenImportError(ValueError):
    """Error al validar o importar un archivo/carpeta de tokens locales."""


def _detect_and_normalize_token(
    raw: dict[str, Any],
    *,
    requested_platform: str | None,
    source_name: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Detecta formato Google Authorized User o TikTok y devuelve `(platform, creds, caps)`."""
    is_google = raw.get("type") == "authorized_user" or (
        bool(raw.get("refresh_token"))
        and bool(raw.get("client_id"))
        and bool(raw.get("client_secret"))
    )
    if is_google:
        if requested_platform and requested_platform != "youtube":
            raise TokenImportError(
                f"{source_name} tiene formato de token Google/YouTube, no de {requested_platform}"
            )
        raw_scopes = raw.get("scopes") or raw.get("scope") or []
        if isinstance(raw_scopes, str):
            scopes = [s for s in raw_scopes.split() if s]
        elif isinstance(raw_scopes, list):
            scopes = [str(s) for s in raw_scopes if s]
        else:
            scopes = []
        creds = {
            "provider": "youtube",
            "access_token": str(raw.get("token") or raw.get("access_token") or ""),
            "refresh_token": str(raw.get("refresh_token") or ""),
            "token_uri": str(raw.get("token_uri") or YOUTUBE_DEFAULT_TOKEN_URI),
            "client_id": str(raw.get("client_id") or ""),
            "client_secret": str(raw.get("client_secret") or ""),
            "scopes": scopes,
            "expires_at": raw.get("expiry") or raw.get("expires_at"),
        }
        capabilities = {
            "direct_post": (
                not scopes or "https://www.googleapis.com/auth/youtube.upload" in scopes
            ),
            "scopes": scopes,
        }
        return "youtube", creds, capabilities

    is_tiktok = bool(raw.get("open_id")) or (
        bool(raw.get("access_token"))
        and (
            requested_platform == "tiktok"
            or "refresh_expires_in" in raw
            or "video." in str(raw.get("scope") or "")
        )
    )
    if is_tiktok:
        if requested_platform and requested_platform != "tiktok":
            raise TokenImportError(
                f"{source_name} tiene formato de token TikTok, no de {requested_platform}"
            )
        raw_scope = raw.get("scopes") or raw.get("scope") or ""
        if isinstance(raw_scope, list):
            scopes = [str(s).strip() for s in raw_scope if str(s).strip()]
        else:
            scopes = [s.strip() for s in str(raw_scope).replace(" ", ",").split(",") if s.strip()]
        direct_post = "video.publish" in scopes
        creds = {
            "provider": "tiktok",
            "access_token": str(raw.get("access_token") or ""),
            "refresh_token": str(raw.get("refresh_token") or ""),
            "open_id": str(raw.get("open_id") or ""),
            "scopes": scopes,
            "expires_at": raw.get("expires_at"),
        }
        capabilities = {
            "direct_post": direct_post,
            "inbox_only": not direct_post,
            "scopes": scopes,
        }
        return "tiktok", creds, capabilities

    raise TokenImportError(
        f"{source_name} no corresponde a un formato de token soportado (YouTube/Google o TikTok)"
    )


def _collect_token_files(target: Path) -> list[Path]:
    if not target.exists():
        raise TokenImportError(f"La ruta no existe: {target}")
    if target.is_file():
        return [target]
    if target.is_dir():
        files = sorted(p for p in target.glob("*.json") if p.is_file())
        if not files:
            raise TokenImportError(f"No se encontraron archivos .json en {target}")
        return files
    raise TokenImportError(f"Ruta no soportada: {target}")


def import_local_tokens(
    session: Session,
    settings: Settings,
    source_path: str | Path,
    *,
    platform: str | None = None,
    alias: str | None = None,
    run_health_check: bool = True,
    http_client: httpx.Client | None = None,
) -> list[SocialAccount]:
    """Importa tokens JSON locales en modo solo lectura y los cifra en `STORAGE_DIR`."""
    if platform is not None and platform not in ACCOUNT_PLATFORMS:
        raise TokenImportError(f"Plataforma no soportada: {platform}")

    resolved_path = Path(source_path).expanduser()
    files = _collect_token_files(resolved_path)

    parsed_entries: list[tuple[Path, str, dict[str, Any], dict[str, Any]]] = []
    for file_path in files:
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise TokenImportError(f"No se pudo leer JSON válido desde {file_path.name}") from exc
        if not isinstance(raw, dict):
            raise TokenImportError(f"{file_path.name} no contiene un objeto JSON")
        detected_platform, creds, capabilities = _detect_and_normalize_token(
            raw, requested_platform=platform, source_name=file_path.name
        )
        parsed_entries.append((file_path, detected_platform, creds, capabilities))

    workspace = ensure_default_workspace(session)
    store = LocalCredentialStore(settings)
    imported: list[SocialAccount] = []
    created_ids: list[str] = []

    try:
        for idx, (file_path, detected_platform, creds, capabilities) in enumerate(parsed_entries):
            account_id = new_ulid()
            creds_ref = store.save_credentials(account_id, creds)
            created_ids.append(account_id)

            stem = file_path.stem.replace("_", " ").replace("-", " ").strip()
            default_display = stem or f"{detected_platform.title()} (importada)"
            entry_alias = alias if (alias and (len(parsed_entries) == 1 or idx == 0)) else None
            is_default = not has_default_for_platform(session, workspace.id, detected_platform)
            now = utcnow()
            account = SocialAccount(
                id=account_id,
                workspace_id=workspace.id,
                platform=detected_platform,
                display_name=default_display,
                handle="",
                alias=entry_alias,
                auth_method="api",
                credentials_ref=creds_ref,
                status="pending",
                is_default=is_default,
                capabilities_json=capabilities,
                external_account_id=creds.get("open_id") or None,
                created_at=now,
                updated_at=now,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            imported.append(account)
    except BaseException:
        session.rollback()
        for acc_id in created_ids:
            store.delete_account_dir(acc_id)
        raise

    if run_health_check:
        checked: list[SocialAccount] = []
        for account in imported:
            checked.append(check_account(session, account, settings, http_client=http_client))
        return checked
    return imported
