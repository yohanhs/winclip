"""`/api/accounts`: gestión multi-cuenta, OAuth oficial, navegador persistente e importación."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from winclip.accounts.browser_login import (
    BrowserLoginConflictError,
    BrowserLoginError,
    get_browser_login_manager,
)
from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.health import check_account
from winclip.accounts.importer import TokenImportError, import_local_tokens
from winclip.accounts.logging_filter import install_accounts_log_filter
from winclip.accounts.oauth import (
    OAuthConfigError,
    OAuthExchangeError,
    OAuthStateError,
    check_platform_oauth_config,
    complete_oauth,
    confirm_instagram_selection,
    get_oauth_state_manager,
    start_oauth,
)
from winclip.accounts.repository import has_default_for_platform, set_default_account
from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_ulid
from winclip.core.models import ACCOUNT_PLATFORMS, SocialAccount, utcnow
from winclip.routers.deps import EngineDep, SessionDep, SettingsDep
from winclip.routers.schemas import (
    AccountPlatform,
    AccountsOAuthConfigOut,
    BrowserLoginOut,
    BrowserLoginStartRequest,
    InstagramCandidateOut,
    InstagramSelectionOut,
    InstagramSelectRequest,
    OAuthStartOut,
    OAuthStartRequest,
    PlatformOAuthConfigOut,
    SocialAccountOut,
    SocialAccountUpdate,
    TokenImportRequest,
)
from winclip.routers.serializers import social_account_out

install_accounts_log_filter()
logger = logging.getLogger("winclip.accounts.router")

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _account_or_404(session: Session, account_id: str) -> SocialAccount:
    account = session.get(SocialAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe la cuenta {account_id}")
    return account


@router.get("", response_model=list[SocialAccountOut], operation_id="listAccounts")
def list_accounts(session: SessionDep) -> list[SocialAccountOut]:
    """Lista las cuentas del workspace ordenadas por plataforma, defecto y fecha."""
    accounts = session.exec(
        select(SocialAccount).order_by(
            SocialAccount.platform,
            SocialAccount.is_default.desc(),
            SocialAccount.created_at.asc(),
        )
    ).all()
    return [social_account_out(item) for item in accounts]


@router.get(
    "/config",
    response_model=AccountsOAuthConfigOut,
    operation_id="getAccountsOAuthConfig",
)
def get_accounts_oauth_config(settings: SettingsDep) -> AccountsOAuthConfigOut:
    """Indica qué plataformas tienen configuración OAuth lista (sin exponer secretos)."""
    items: list[PlatformOAuthConfigOut] = []
    for platform in ACCOUNT_PLATFORMS:
        configured, missing = check_platform_oauth_config(platform, settings)
        items.append(
            PlatformOAuthConfigOut(
                platform=platform,  # type: ignore[arg-type]
                configured=configured,
                missing=missing,
            )
        )
    return AccountsOAuthConfigOut(platforms=items)


@router.patch(
    "/{account_id}",
    response_model=SocialAccountOut,
    operation_id="updateAccount",
)
def update_account(
    account_id: str,
    payload: SocialAccountUpdate,
    session: SessionDep,
) -> SocialAccountOut:
    """Actualiza alias y/o marca la cuenta como predeterminada de su plataforma."""
    account = _account_or_404(session, account_id)
    changes = payload.model_dump(exclude_unset=True)

    if "alias" in changes:
        account.alias = payload.alias

    if changes.get("is_default") is True:
        account = set_default_account(session, account)
    else:
        if "is_default" in changes and payload.is_default is False:
            account.is_default = False
        account.updated_at = utcnow()
        session.add(account)
        session.commit()
        session.refresh(account)

    return social_account_out(account)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAccount",
)
def delete_account(account_id: str, session: SessionDep, settings: SettingsDep) -> None:
    """Elimina la cuenta de SQLite y borra su directorio de credenciales/perfil en disco."""
    account = _account_or_404(session, account_id)
    manager = get_browser_login_manager()
    active_login = manager.get_session(account_id)
    if active_login is not None and active_login.status == "waiting":
        manager.cancel_login(account_id)

    session.delete(account)
    session.commit()

    store = LocalCredentialStore(settings)
    store.delete_account_dir(account_id)
    logger.info("Cuenta %s (%s) eliminada", account_id, account.platform)
    return None


@router.post(
    "/{account_id}/check",
    response_model=SocialAccountOut,
    operation_id="checkAccount",
)
def check_account_endpoint(
    account_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> SocialAccountOut:
    """Ejecuta comprobación de salud en vivo y refresca el token si procede."""
    account = _account_or_404(session, account_id)
    updated = check_account(session, account, settings)
    return social_account_out(updated)


@router.post(
    "/oauth/{platform}/start",
    response_model=OAuthStartOut,
    operation_id="startAccountOAuth",
)
def start_account_oauth(
    platform: AccountPlatform,
    session: SessionDep,
    settings: SettingsDep,
    payload: OAuthStartRequest | None = None,
) -> OAuthStartOut:
    """Genera la URL de autorización OAuth 2.0 y estado anti-CSRF para la plataforma."""
    workspace = ensure_default_workspace(session)
    req = payload or OAuthStartRequest()
    if req.account_id:
        _account_or_404(session, req.account_id)

    try:
        started = start_oauth(
            platform,
            settings,
            workspace_id=workspace.id,
            account_id=req.account_id,
            direct_post=req.direct_post,
            alias=req.alias,
        )
    except OAuthConfigError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"message": str(exc), "missing": exc.missing},
        ) from exc
    return OAuthStartOut(
        auth_url=started.auth_url,
        state=started.state,
        platform=platform,
    )


@router.get(
    "/oauth/{platform}/callback",
    operation_id="handleAccountOAuthCallback",
    response_model=None,
)
def handle_account_oauth_callback(
    platform: AccountPlatform,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    response_format: str | None = Query(default=None, alias="format"),
) -> RedirectResponse | JSONResponse:
    """Completa el intercambio OAuth y redirige a `/accounts` (o devuelve JSON si se solicita)."""
    wants_json = response_format == "json" or "application/json" in (
        request.headers.get("accept") or ""
    )
    web_base = f"http://localhost:{settings.web_port}/accounts"

    if error:
        msg = error_description or error
        if wants_json:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Autorización rechazada: {msg}")
        return RedirectResponse(
            f"{web_base}?{urlencode({'oauth_error': msg, 'platform': platform})}",
            status_code=status.HTTP_302_FOUND,
        )

    if not code or not state:
        if wants_json:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faltan parámetros code o state")
        err_qs = urlencode({"oauth_error": "Faltan parámetros code o state", "platform": platform})
        return RedirectResponse(
            f"{web_base}?{err_qs}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        result = complete_oauth(session, settings, platform=platform, code=code, state=state)
    except (OAuthStateError, OAuthConfigError, OAuthExchangeError) as exc:
        if wants_json:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        return RedirectResponse(
            f"{web_base}?{urlencode({'oauth_error': str(exc), 'platform': platform})}",
            status_code=status.HTTP_302_FOUND,
        )

    if result.pending_selection_token:
        if wants_json:
            return JSONResponse(
                InstagramSelectionOut(
                    selection_token=result.pending_selection_token,
                    candidates=[
                        InstagramCandidateOut(
                            external_account_id=c.external_account_id,
                            username=c.username,
                            display_name=c.display_name,
                            avatar_url=c.avatar_url,
                            page_name=c.page_name,
                        )
                        for c in result.instagram_candidates
                    ],
                ).model_dump(mode="json")
            )
        return RedirectResponse(
            f"{web_base}?{urlencode({'ig_selection': result.pending_selection_token})}",
            status_code=status.HTTP_302_FOUND,
        )

    account_id = result.accounts[0].id if result.accounts else ""
    if wants_json:
        return JSONResponse(
            [social_account_out(a).model_dump(mode="json") for a in result.accounts]
        )
    return RedirectResponse(
        f"{web_base}?{urlencode({'connected': account_id, 'platform': platform})}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/oauth/instagram/pending/{selection_token}",
    response_model=InstagramSelectionOut,
    operation_id="getPendingInstagramSelection",
)
def get_pending_instagram_selection(selection_token: str) -> InstagramSelectionOut:
    """Devuelve las cuentas Business/Creator de Instagram pendientes de selección."""
    manager = get_oauth_state_manager()
    try:
        pending = manager.get_ig_selection(selection_token)
    except OAuthStateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InstagramSelectionOut(
        selection_token=pending.token,
        candidates=[
            InstagramCandidateOut(
                external_account_id=c.external_account_id,
                username=c.username,
                display_name=c.display_name,
                avatar_url=c.avatar_url,
                page_name=c.page_name,
            )
            for c in pending.candidates
        ],
    )


@router.post(
    "/oauth/instagram/select",
    response_model=list[SocialAccountOut],
    operation_id="selectInstagramAccounts",
)
def select_instagram_accounts(
    payload: InstagramSelectRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> list[SocialAccountOut]:
    """Guarda las cuentas Business/Creator de Instagram elegidas por el usuario."""
    try:
        accounts = confirm_instagram_selection(
            session,
            settings,
            selection_token=payload.selection_token,
            external_account_ids=payload.external_account_ids,
        )
    except (OAuthStateError, OAuthExchangeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return [social_account_out(a) for a in accounts]


@router.post(
    "/browser-login/start",
    response_model=BrowserLoginOut,
    operation_id="startBrowserLogin",
)
def start_browser_login(
    payload: BrowserLoginStartRequest,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> BrowserLoginOut:
    """Crea o reutiliza una cuenta Playwright y abre Chromium visible para login manual."""
    workspace = ensure_default_workspace(session)
    store = LocalCredentialStore(settings)
    now = utcnow()

    if payload.account_id:
        account = _account_or_404(session, payload.account_id)
        if account.platform != payload.platform:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "La cuenta indicada pertenece a otra plataforma",
            )
        account.auth_method = "playwright"
        account.credentials_ref = store.profile_relpath(account.id)
        if payload.alias is not None:
            account.alias = payload.alias
        account.updated_at = now
        session.add(account)
        session.commit()
        session.refresh(account)
    else:
        acc_id = new_ulid()
        is_default = not has_default_for_platform(session, workspace.id, payload.platform)
        account = SocialAccount(
            id=acc_id,
            workspace_id=workspace.id,
            platform=payload.platform,
            display_name=f"{payload.platform.title()} (navegador)",
            handle="",
            alias=payload.alias,
            auth_method="playwright",
            credentials_ref=store.profile_relpath(acc_id),
            status="pending",
            is_default=is_default,
            capabilities_json={"direct_post": True, "browser_session": True},
            created_at=now,
            updated_at=now,
        )
        session.add(account)
        session.commit()
        session.refresh(account)

    manager = get_browser_login_manager()
    try:
        login_session = manager.start_login(
            engine=engine,
            settings=settings,
            account_id=account.id,
            platform=payload.platform,
        )
    except BrowserLoginConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except BrowserLoginError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return BrowserLoginOut(
        account_id=account.id,
        platform=payload.platform,
        session_status=login_session.status,
        error=login_session.error,
    )


@router.get(
    "/{account_id}/browser-login/status",
    response_model=BrowserLoginOut,
    operation_id="getBrowserLoginStatus",
)
def get_browser_login_status(account_id: str, session: SessionDep) -> BrowserLoginOut:
    """Devuelve el estado actual del login interactivo para la cuenta."""
    account = _account_or_404(session, account_id)
    manager = get_browser_login_manager()
    login_session = manager.get_session(account_id)
    if login_session is None:
        derived = "connected" if account.status == "connected" else "cancelled"
        return BrowserLoginOut(
            account_id=account.id,
            platform=account.platform,  # type: ignore[arg-type]
            session_status=derived,
            error=account.last_error,
        )
    return BrowserLoginOut(
        account_id=account.id,
        platform=account.platform,  # type: ignore[arg-type]
        session_status=login_session.status,
        error=login_session.error,
    )


@router.post(
    "/{account_id}/browser-login/confirm",
    response_model=BrowserLoginOut,
    operation_id="confirmBrowserLogin",
)
def confirm_browser_login(account_id: str, session: SessionDep) -> BrowserLoginOut:
    """Confirma manualmente que el usuario ya completó el inicio de sesión en Chromium."""
    account = _account_or_404(session, account_id)
    manager = get_browser_login_manager()
    try:
        login_session = manager.confirm_login(account_id)
    except BrowserLoginError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return BrowserLoginOut(
        account_id=account.id,
        platform=account.platform,  # type: ignore[arg-type]
        session_status=login_session.status,
        error=login_session.error,
    )


@router.post(
    "/{account_id}/browser-login/cancel",
    response_model=BrowserLoginOut,
    operation_id="cancelBrowserLogin",
)
def cancel_browser_login(account_id: str, session: SessionDep) -> BrowserLoginOut:
    """Cancela el login interactivo en curso y cierra la ventana de Chromium."""
    account = _account_or_404(session, account_id)
    manager = get_browser_login_manager()
    try:
        login_session = manager.cancel_login(account_id)
    except BrowserLoginError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return BrowserLoginOut(
        account_id=account.id,
        platform=account.platform,  # type: ignore[arg-type]
        session_status=login_session.status,
        error=login_session.error,
    )


@router.post(
    "/import",
    response_model=list[SocialAccountOut],
    status_code=status.HTTP_201_CREATED,
    operation_id="importAccountTokens",
)
def import_account_tokens_endpoint(
    payload: TokenImportRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> list[SocialAccountOut]:
    """Importa tokens locales existentes en modo solo lectura sin copiar archivos al repo."""
    try:
        accounts = import_local_tokens(
            session,
            settings,
            payload.path,
            platform=payload.platform,
            alias=payload.alias,
            run_health_check=True,
        )
    except TokenImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return [social_account_out(a) for a in accounts]
