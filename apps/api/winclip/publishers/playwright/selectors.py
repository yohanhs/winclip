"""Selectores aislados y utilidades seguras para publicadores Playwright (`design.md`, decisión 5).

IMPORTANTE: Este módulo NUNCA intenta resolver, clickear ni evadir CAPTCHAs, retos anti-bot
ni verificaciones 2FA. Ante cualquier señal de reto o sesión expirada, captura pantalla
diagnóstica bajo `STORAGE_DIR/publications/<id>/` y aborta inmediatamente con error estructurado.
"""

from __future__ import annotations

import contextlib
import random
import re
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from winclip.core.storage import LocalStorage
from winclip.publishers.base import AuthExpiredError, ChallengeDetectedError
from winclip.publishers.playwright.session import is_login_url


@dataclass(frozen=True)
class PlatformSelectors:
    """Listas ordenadas de selectores con fallback por paso para una plataforma."""

    upload_url: str
    file_inputs: tuple[str, ...]
    caption_inputs: tuple[str, ...]
    publish_buttons: tuple[str, ...]
    success_indicators: tuple[str, ...]
    login_indicators: tuple[str, ...]
    challenge_indicators: tuple[str, ...]
    create_buttons: tuple[str, ...] = ()
    next_buttons: tuple[str, ...] = ()


TIKTOK_SELECTORS = PlatformSelectors(
    upload_url="https://www.tiktok.com/tiktokstudio/upload",
    file_inputs=(
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    ),
    caption_inputs=(
        '[data-e2e="caption-input"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea[name="caption"]',
    ),
    publish_buttons=(
        'button[data-e2e="post_video_button"]',
        'button:has-text("Publicar")',
        'button:has-text("Post")',
        'button[type="submit"]',
    ),
    success_indicators=(
        '[data-e2e="upload-success"]',
        ':text("Tu video se ha publicado")',
        ':text("Your video is being uploaded")',
        ':text("Video published")',
        ':text("Manage your posts")',
    ),
    login_indicators=(
        'form[action*="login"]',
        'input[name="username"]',
        'input[type="password"]',
        '[data-e2e="login-button"]',
        ':text("Log in to TikTok")',
        ':text("Inicia sesión en TikTok")',
    ),
    challenge_indicators=(
        '[id*="captcha"]',
        '[class*="captcha"]',
        'iframe[src*="captcha"]',
        'iframe[src*="verify"]',
        '[data-e2e="captcha-verify"]',
        ':text("Verify to continue")',
        ':text("Verifica para continuar")',
        ':text("2-step verification")',
        ':text("Verificación en dos pasos")',
    ),
)

INSTAGRAM_SELECTORS = PlatformSelectors(
    upload_url="https://www.instagram.com/",
    create_buttons=(
        'a[aria-label="Nueva publicación"]',
        'a[aria-label="New post"]',
        'a:has(svg[aria-label="Nueva publicación"])',
        'a:has(svg[aria-label="New post"])',
        'svg[aria-label="Nueva publicación"]',
        'svg[aria-label="New post"]',
        'div[role="button"]:has(svg[aria-label="Nueva publicación"])',
        'div[role="button"]:has(svg[aria-label="New post"])',
        'button[data-testid="create-post-button"]',
        'button:has-text("Crear")',
        'button:has-text("Create")',
    ),
    file_inputs=(
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    ),
    next_buttons=(
        'button[data-testid="next-step-button"]',
        'button:has-text("Siguiente")',
        'button:has-text("Next")',
        'div[role="button"]:has-text("Siguiente")',
        'div[role="button"]:has-text("Next")',
    ),
    caption_inputs=(
        'div[aria-label="Write a caption..."]',
        'div[aria-label="Escribe un pie de foto..."]',
        'div[aria-label="Escribe una descripción..."]',
        'textarea[aria-label="Write a caption..."]',
        'textarea[name="caption"]',
        'div[contenteditable="true"][role="textbox"]',
    ),
    publish_buttons=(
        'button[data-testid="share-reel-button"]',
        'button:has-text("Compartir")',
        'button:has-text("Share")',
        'div[role="button"]:has-text("Compartir")',
        'div[role="button"]:has-text("Share")',
        'button[type="submit"]',
    ),
    success_indicators=(
        '[data-testid="reel-shared-success"]',
        ':text("Se ha compartido tu reel")',
        ':text("Se compartió tu reel")',
        ':text("Se compartió tu publicación")',
        ':text("Your reel has been shared")',
        ':text("Reel shared")',
    ),
    login_indicators=(
        'form[id="loginForm"]',
        'input[name="username"]',
        'input[name="password"]',
        ':text("Log in")',
        ':text("Iniciar sesión")',
    ),
    challenge_indicators=(
        '[id*="captcha"]',
        '[class*="captcha"]',
        'iframe[src*="captcha"]',
        'iframe[src*="challenge"]',
        'input[name="verificationCode"]',
        'input[name="security_code"]',
        ':text("Confirm it\'s you")',
        ':text("Confirma que eres tú")',
        ':text("Two-Factor Authentication")',
        ':text("Autenticación en dos pasos")',
    ),
)

CHALLENGE_URL_MARKERS = (
    "/challenge",
    "/checkpoint",
    "/two_factor",
    "/verify",
    "captcha",
    "recaptcha",
    "hcaptcha",
    "turnstile",
)

_LOCKS_GUARD = threading.Lock()
_ACCOUNT_LOCKS: dict[str, threading.Lock] = {}


def get_account_lock(account_id: str) -> threading.Lock:
    """Devuelve un lock exclusivo por `account_id` para evitar colisiones de perfil."""
    with _LOCKS_GUARD:
        lock = _ACCOUNT_LOCKS.get(account_id)
        if lock is None:
            lock = threading.Lock()
            _ACCOUNT_LOCKS[account_id] = lock
        return lock


@contextlib.contextmanager
def account_browser_lock(account_id: str) -> Iterator[None]:
    """Context manager de exclusión mutua por cuenta para Playwright."""
    lock = get_account_lock(account_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def human_delay(
    min_sec: float = 0.8,
    max_sec: float = 2.5,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> float:
    """Inserta una pausa natural aleatoria entre acciones de navegador."""
    duration = random.uniform(min_sec, max_sec)
    if duration > 0:
        sleep_fn(duration)
    return duration


def _slug(step_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", step_name.strip().lower()).strip("_")
    return cleaned or "step"


@dataclass
class StepCapture:
    """Gestiona capturas PNG por paso bajo `STORAGE_DIR/publications/<id>/steps/`."""

    storage: LocalStorage
    publication_id: str
    screenshots: list[str] = field(default_factory=list)
    _counter: int = 0

    @property
    def last_path(self) -> str | None:
        return self.screenshots[-1] if self.screenshots else None

    def capture(self, page: Any, step_name: str) -> str | None:
        """Guarda una captura PNG y devuelve su ruta relativa a `STORAGE_DIR`."""
        self._counter += 1
        steps_dir = self.storage.publication_steps_dir(self.publication_id)
        steps_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._counter:02d}_{_slug(step_name)}.png"
        target = steps_dir / filename
        try:
            page.screenshot(path=str(target), full_page=False)
        except Exception:
            return None
        rel = target.resolve().relative_to(self.storage.root).as_posix()
        self.screenshots.append(rel)
        return rel


def is_locator_visible(page: Any, selector: str, *, timeout_ms: int = 400) -> bool:
    """Devuelve True si `selector` coincide con un elemento visible en la página."""
    try:
        locator = page.locator(selector).first
        return bool(locator.is_visible(timeout=timeout_ms))
    except Exception:
        return False


def find_first_visible(
    page: Any,
    selectors: Sequence[str],
    *,
    timeout_ms: int = 3000,
) -> Any | None:
    """Busca el primer selector visible de una lista ordenada de fallbacks."""
    per_selector = max(250, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=per_selector):
                return locator
        except Exception:
            continue
    return None


def find_first_attached(page: Any, selectors: Sequence[str]) -> Any | None:
    """Busca el primer selector presente en el DOM (útil para `<input type="file">`)."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator
        except Exception:
            continue
    return None


def type_human(locator: Any, text: str, *, delay_ms: int = 20) -> None:
    """Rellena un campo de texto o `contenteditable` con escritura progresiva segura."""
    locator.click()
    with contextlib.suppress(Exception):
        locator.fill("")
    if hasattr(locator, "type"):
        try:
            locator.type(text, delay=delay_ms)
            return
        except Exception:
            pass
    locator.fill(text)


def assert_no_challenge_or_login(
    page: Any,
    platform: str,
    selectors: PlatformSelectors,
    capture: StepCapture,
    *,
    step_name: str = "guard",
) -> None:
    """Detiene inmediatamente el flujo ante CAPTCHA/2FA/anti-bot o redirección a login.

    NUNCA intenta resolver ni evadir el reto: guarda captura diagnóstica y lanza error
    estructurado no reintentable (`ChallengeDetectedError` o `AuthExpiredError`).
    """
    current_url = str(getattr(page, "url", "") or "").lower()

    # 1. Revisar desafíos anti-bot / CAPTCHA / 2FA en URL y DOM
    if any(marker in current_url for marker in CHALLENGE_URL_MARKERS) or any(
        is_locator_visible(page, sel, timeout_ms=250) for sel in selectors.challenge_indicators
    ):
        shot = capture.capture(page, f"challenge_{step_name}")
        raise ChallengeDetectedError(
            f"Se detectó un desafío anti-bot, CAPTCHA o verificación 2FA en {platform}. "
            "WinClip detuvo el flujo automáticamente para intervención manual.",
            screenshot_path=shot,
        )

    # 2. Revisar sesión expirada / redirección a login
    if is_login_url(current_url, platform) or any(
        is_locator_visible(page, sel, timeout_ms=250) for sel in selectors.login_indicators
    ):
        shot = capture.capture(page, f"session_expired_{step_name}")
        raise AuthExpiredError(
            f"La sesión de navegador en {platform} expiró o redirigió a inicio de sesión; "
            "vuelve a conectar la cuenta desde /accounts.",
            screenshot_path=shot,
        )
