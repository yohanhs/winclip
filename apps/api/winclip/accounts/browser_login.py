"""Flujo interactivo "Conectar con navegador" (Playwright visible) y health check."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import Engine
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.core.config import Settings
from winclip.core.models import SocialAccount, utcnow
from winclip.publishers.playwright.session import (
    PLAYWRIGHT_SUPPORTED_PLATFORMS,
    ContextFactory,
    extract_profile_hint,
    get_platform_browser_config,
    has_authenticated_cookies,
    is_login_url,
    open_persistent_context,
    verify_persistent_session,
)

logger = logging.getLogger("winclip.accounts.browser_login")

BrowserLoginStatus = Literal["waiting", "connected", "timeout", "cancelled", "error"]
DEFAULT_LOGIN_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


class BrowserLoginError(RuntimeError):
    """Error base del flujo de login interactivo con navegador."""


class BrowserLoginConflictError(BrowserLoginError):
    """Ya existe una ventana de login abierta para esta cuenta."""


@dataclass
class BrowserLoginSession:
    account_id: str
    platform: str
    status: BrowserLoginStatus = "waiting"
    error: str | None = None
    display_name: str | None = None
    handle: str | None = None
    started_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    confirm_event: threading.Event = field(default_factory=threading.Event, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)


class BrowserLoginManager:
    """Coordina sesiones de login interactivo con bloqueo por cuenta (`account_id`)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._sessions: dict[str, BrowserLoginSession] = {}

    def get_session(self, account_id: str) -> BrowserLoginSession | None:
        with self._guard:
            return self._sessions.get(account_id)

    def start_login(
        self,
        *,
        engine: Engine,
        settings: Settings,
        account_id: str,
        platform: str,
        timeout_seconds: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        context_factory: ContextFactory | None = None,
    ) -> BrowserLoginSession:
        if platform not in PLAYWRIGHT_SUPPORTED_PLATFORMS:
            supported = ", ".join(PLAYWRIGHT_SUPPORTED_PLATFORMS)
            raise BrowserLoginError(
                f"Conectar con navegador solo está disponible para: {supported}"
            )

        with self._guard:
            existing = self._sessions.get(account_id)
            if existing is not None and existing.status == "waiting":
                raise BrowserLoginConflictError(
                    "Ya hay una ventana de inicio de sesión abierta para esta cuenta"
                )
            login_session = BrowserLoginSession(account_id=account_id, platform=platform)
            self._sessions[account_id] = login_session

        store = LocalCredentialStore(settings)
        profile_dir = store.ensure_profile_dir(account_id)

        def _worker() -> None:
            self._run_login_loop(
                login_session=login_session,
                engine=engine,
                profile_dir=profile_dir,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
                context_factory=context_factory,
            )

        thread = threading.Thread(
            target=_worker,
            name=f"browser-login-{account_id[:8]}",
            daemon=True,
        )
        login_session.thread = thread
        thread.start()
        return login_session

    def confirm_login(self, account_id: str) -> BrowserLoginSession:
        with self._guard:
            login_session = self._sessions.get(account_id)
            if login_session is None:
                raise BrowserLoginError("No hay una sesión de navegador activa para esta cuenta")
        login_session.confirm_event.set()
        return login_session

    def cancel_login(self, account_id: str) -> BrowserLoginSession:
        with self._guard:
            login_session = self._sessions.get(account_id)
            if login_session is None:
                raise BrowserLoginError("No hay una sesión de navegador activa para esta cuenta")
        login_session.cancel_event.set()
        return login_session

    def _run_login_loop(
        self,
        *,
        login_session: BrowserLoginSession,
        engine: Engine,
        profile_dir,
        timeout_seconds: float,
        poll_interval: float,
        context_factory: ContextFactory | None,
    ) -> None:
        cfg = get_platform_browser_config(login_session.platform)
        factory = context_factory or (
            lambda path, headless: open_persistent_context(path, headless=headless)
        )
        deadline = time.monotonic() + timeout_seconds

        try:
            with factory(profile_dir, False) as context:
                pages = list(context.pages)
                page = pages[0] if pages else context.new_page()
                page.goto(cfg.login_url, wait_until="domcontentloaded", timeout=30000)

                while time.monotonic() < deadline:
                    if login_session.cancel_event.is_set():
                        self._finalize(
                            login_session, "cancelled", error="Inicio de sesión cancelado"
                        )
                        return

                    try:
                        cookies = context.cookies()
                        current_url = str(page.url or "")
                    except Exception:
                        # El usuario cerró la ventana manualmente.
                        self._finalize(
                            login_session,
                            "cancelled",
                            error="Ventana de navegador cerrada antes de completar el login",
                        )
                        return

                    auto_detected = has_authenticated_cookies(
                        cookies, login_session.platform
                    ) and not is_login_url(current_url, login_session.platform)

                    if login_session.confirm_event.is_set() or auto_detected:
                        display_name, handle = extract_profile_hint(page, login_session.platform)
                        login_session.display_name = display_name
                        login_session.handle = handle
                        break

                    # Espera corta interrumpible por confirm o cancel
                    sleep_step = min(poll_interval, max(0.05, deadline - time.monotonic()))
                    if login_session.cancel_event.wait(timeout=sleep_step):
                        self._finalize(
                            login_session, "cancelled", error="Inicio de sesión cancelado"
                        )
                        return
                    if login_session.confirm_event.is_set():
                        display_name, handle = extract_profile_hint(page, login_session.platform)
                        login_session.display_name = display_name
                        login_session.handle = handle
                        break
                else:
                    self._finalize(
                        login_session,
                        "timeout",
                        error="Tiempo de espera agotado para completar el inicio de sesión",
                    )
                    return

            # Al salir del `with`, el contexto cerró y volcó cookies a disco.
            now = utcnow()
            with Session(engine) as session:
                account = session.get(SocialAccount, login_session.account_id)
                if account is not None:
                    if login_session.display_name and (
                        not account.display_name or account.display_name.endswith("(navegador)")
                    ):
                        account.display_name = login_session.display_name
                    if login_session.handle:
                        account.handle = login_session.handle
                    account.status = "connected"
                    account.last_check_at = now
                    account.last_error = None
                    account.updated_at = now
                    session.add(account)
                    session.commit()

            self._finalize(login_session, "connected", error=None)
        except Exception as exc:
            logger.warning(
                "Error en login de navegador para cuenta %s: %s",
                login_session.account_id,
                type(exc).__name__,
            )
            self._finalize(
                login_session,
                "error",
                error=f"No se pudo completar el inicio de sesión ({type(exc).__name__})",
            )

    def _finalize(
        self,
        login_session: BrowserLoginSession,
        status: BrowserLoginStatus,
        *,
        error: str | None,
    ) -> None:
        with self._guard:
            login_session.status = status
            login_session.error = error
            login_session.updated_at = utcnow()


_DEFAULT_BROWSER_LOGIN_MANAGER = BrowserLoginManager()


def get_browser_login_manager() -> BrowserLoginManager:
    return _DEFAULT_BROWSER_LOGIN_MANAGER


def check_browser_account_health(
    session: Session,
    account: SocialAccount,
    settings: Settings,
    *,
    context_factory: ContextFactory | None = None,
) -> SocialAccount:
    """Comprueba la sesión persistente Playwright de una cuenta y actualiza su estado."""
    store = LocalCredentialStore(settings)
    profile_dir = store.profile_dir(account.id)
    now = utcnow()

    ok, display_name, handle, error_msg = verify_persistent_session(
        profile_dir,
        account.platform,
        headless=True,
        context_factory=context_factory,
    )
    if ok:
        if display_name and (
            not account.display_name or account.display_name.endswith("(navegador)")
        ):
            account.display_name = display_name
        if handle:
            account.handle = handle
        account.status = "connected"
        account.last_error = None
    else:
        account.status = "expired" if error_msg and "expirada" in error_msg.lower() else "error"
        account.last_error = error_msg
    account.last_check_at = now
    account.updated_at = now
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
