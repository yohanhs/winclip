"""Gestión de perfiles persistentes de Chromium con Playwright (`design.md`, decisión 3)."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLAYWRIGHT_SUPPORTED_PLATFORMS = ("tiktok", "instagram")


@dataclass(frozen=True)
class PlatformBrowserConfig:
    login_url: str
    check_url: str
    session_cookies: tuple[str, ...]
    domain_substring: str
    login_path_markers: tuple[str, ...]


PLATFORM_BROWSER_CONFIGS: dict[str, PlatformBrowserConfig] = {
    "tiktok": PlatformBrowserConfig(
        login_url="https://www.tiktok.com/login",
        check_url="https://www.tiktok.com/creator-center/upload",
        session_cookies=("sessionid", "sessionid_ss", "sid_tt"),
        domain_substring="tiktok.com",
        login_path_markers=("/login", "/signup"),
    ),
    "instagram": PlatformBrowserConfig(
        login_url="https://www.instagram.com/accounts/login/",
        check_url="https://www.instagram.com/",
        session_cookies=("sessionid", "ds_user_id"),
        domain_substring="instagram.com",
        login_path_markers=("/accounts/login", "/challenge"),
    ),
}

_HANDLE_RE = re.compile(r"@([A-Za-z0-9._]{2,40})")


def get_platform_browser_config(platform: str) -> PlatformBrowserConfig:
    cfg = PLATFORM_BROWSER_CONFIGS.get(platform)
    if cfg is None:
        raise ValueError(f"Login con navegador no soportado para la plataforma: {platform}")
    return cfg


def has_authenticated_cookies(cookies: list[dict[str, Any]], platform: str) -> bool:
    """Devuelve True si el perfil contiene cookies de sesión válidas para la plataforma."""
    cfg = get_platform_browser_config(platform)
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        domain = str(cookie.get("domain") or "").lower()
        value = str(cookie.get("value") or "").strip()
        if name in cfg.session_cookies and cfg.domain_substring in domain and bool(value):
            return True
    return False


def is_login_url(url: str, platform: str) -> bool:
    """Indica si la URL actual sigue siendo una pantalla de login/reto."""
    cfg = get_platform_browser_config(platform)
    lowered = url.lower()
    return any(marker in lowered for marker in cfg.login_path_markers)


def extract_profile_hint(page: Any, platform: str) -> tuple[str | None, str | None]:
    """Intenta extraer `(display_name, handle)` de la página actual sin fallar."""
    try:
        title = str(page.title() or "").strip()
    except Exception:
        title = ""
    try:
        url = str(page.url or "")
    except Exception:
        url = ""

    handle: str | None = None
    match = _HANDLE_RE.search(url) or _HANDLE_RE.search(title)
    if match:
        handle = f"@{match.group(1)}"

    display_name: str | None = None
    if title and platform not in title.lower():
        display_name = title[:120]
    elif handle:
        display_name = handle.lstrip("@")
    return display_name, handle


@contextlib.contextmanager
def open_persistent_context(
    profile_dir: Path,
    *,
    headless: bool = False,
) -> Iterator[Any]:
    """Abre un contexto persistente de Chromium en `profile_dir` y lo cierra limpiamente."""
    from playwright.sync_api import sync_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 840},
        )
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):
                context.close()


ContextFactory = Callable[[Path, bool], contextlib.AbstractContextManager[Any]]


def _default_context_factory(
    profile_dir: Path, headless: bool
) -> contextlib.AbstractContextManager[Any]:
    return open_persistent_context(profile_dir, headless=headless)


def verify_persistent_session(
    profile_dir: Path,
    platform: str,
    *,
    headless: bool = True,
    context_factory: ContextFactory | None = None,
) -> tuple[bool, str | None, str | None, str | None]:
    """Comprueba si un perfil persistente sigue autenticado sin enviar formularios."""
    if not profile_dir.is_dir():
        return False, None, None, "Perfil de navegador no encontrado; vuelve a conectar la cuenta"

    cfg = get_platform_browser_config(platform)
    factory = context_factory or _default_context_factory
    try:
        with factory(profile_dir, headless) as context:
            pages = list(context.pages)
            page = pages[0] if pages else context.new_page()
            page.goto(cfg.check_url, wait_until="domcontentloaded", timeout=20000)
            cookies = context.cookies()
            current_url = str(page.url or "")
            authenticated = has_authenticated_cookies(cookies, platform) and not is_login_url(
                current_url, platform
            )
            if not authenticated:
                return (
                    False,
                    None,
                    None,
                    "Sesión de navegador expirada; vuelve a iniciar sesión",
                )
            display_name, handle = extract_profile_hint(page, platform)
            return True, display_name, handle, None
    except Exception as exc:
        return False, None, None, f"Error verificando sesión de navegador ({type(exc).__name__})"
