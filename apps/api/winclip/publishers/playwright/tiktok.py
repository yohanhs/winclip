"""Publicador Playwright de respaldo para TikTok (`design.md`, decisión 5)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from winclip.core.config import Settings
from winclip.core.ids import new_publication_id
from winclip.core.models import Clip, SocialAccount
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.publishers.base import (
    AccountStatus,
    AuthExpiredError,
    PermanentPublishError,
    ProgressCallback,
    PublishError,
    PublishMeta,
    PublishResult,
    PublishValidationError,
)
from winclip.publishers.metadata import validate_publish_meta
from winclip.publishers.playwright.selectors import (
    TIKTOK_SELECTORS,
    PlatformSelectors,
    StepCapture,
    account_browser_lock,
    assert_no_challenge_or_login,
    find_first_attached,
    find_first_visible,
    human_delay,
    type_human,
)
from winclip.publishers.playwright.session import (
    ContextFactory,
    open_persistent_context,
    verify_persistent_session,
)

logger = logging.getLogger("winclip.publishers.playwright.tiktok")

PLAYWRIGHT_TOS_WARNING = (
    "Publicado mediante navegador automatizado (Playwright). Recuerda que la automatización web "
    "conlleva riesgos frente a los Términos de Servicio de TikTok; prioriza la API oficial."
)


class TikTokPlaywrightPublisher:
    """Publicador de respaldo para cuentas TikTok con sesión persistente de Chromium."""

    platform: Literal["tiktok"] = "tiktok"

    def __init__(
        self,
        *,
        settings: Settings,
        session: object | None = None,
        context_factory: ContextFactory | None = None,
        selectors: PlatformSelectors = TIKTOK_SELECTORS,
        upload_url_override: str | None = None,
        on_progress: ProgressCallback | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        min_delay_sec: float = 0.8,
        max_delay_sec: float = 2.0,
        headless: bool | None = None,
    ) -> None:
        self.settings = settings
        self.storage = LocalStorage(settings.storage_dir)
        self._context_factory = context_factory or (
            lambda profile_dir, is_headless: open_persistent_context(
                profile_dir, headless=is_headless
            )
        )
        self._selectors = selectors
        self._upload_url_override = upload_url_override
        self.on_progress = on_progress
        self._sleep = sleep_fn
        self._min_delay = min_delay_sec
        self._max_delay = max_delay_sec
        self._headless = settings.playwright_headless if headless is None else headless

    def _report(self, percent: float, stage: str) -> None:
        if self.on_progress is not None:
            self.on_progress(percent, stage)

    def _profile_dir(self, account: SocialAccount) -> Path:
        return self.storage.path("accounts", account.id, "profile")

    def check(self, account: SocialAccount) -> AccountStatus:
        ok, _name, _handle, err = verify_persistent_session(
            self._profile_dir(account),
            "tiktok",
            headless=True,
            context_factory=self._context_factory,
        )
        return AccountStatus(
            status="connected" if ok else "expired",
            message=err,
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

        profile_dir = self._profile_dir(account)
        if not profile_dir.is_dir():
            raise AuthExpiredError(
                "No se encontró el perfil de navegador de esta cuenta; reconecta desde /accounts."
            )

        pub_id = meta.publication_id or new_publication_id()
        capture = StepCapture(self.storage, pub_id)
        target_url = self._upload_url_override or self._selectors.upload_url

        with account_browser_lock(account.id):
            self._report(10.0, "launch_browser")
            with self._context_factory(profile_dir, self._headless) as context:
                pages = list(context.pages)
                page = pages[0] if pages else context.new_page()
                try:
                    self._report(20.0, "open_upload")
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    human_delay(self._min_delay, self._max_delay, sleep_fn=self._sleep)
                    capture.capture(page, "open_upload")
                    assert_no_challenge_or_login(
                        page, "tiktok", self._selectors, capture, step_name="open"
                    )

                    self._report(40.0, "select_file")
                    file_input = find_first_attached(page, self._selectors.file_inputs)
                    if file_input is None:
                        shot = capture.capture(page, "error_no_file_input")
                        raise PermanentPublishError(
                            "No se encontró el selector de archivo en TikTok Studio.",
                            screenshot_path=shot,
                        )
                    file_input.set_input_files(str(clip_path))
                    human_delay(self._min_delay, self._max_delay, sleep_fn=self._sleep)
                    capture.capture(page, "file_selected")
                    assert_no_challenge_or_login(
                        page, "tiktok", self._selectors, capture, step_name="after_file"
                    )

                    self._report(65.0, "fill_caption")
                    caption = (meta.caption or meta.title or clip.title).strip()
                    if caption:
                        caption_box = find_first_visible(
                            page, self._selectors.caption_inputs, timeout_ms=4000
                        )
                        if caption_box is not None:
                            type_human(caption_box, caption, delay_ms=10)
                            human_delay(self._min_delay, self._max_delay, sleep_fn=self._sleep)
                            capture.capture(page, "caption_filled")

                    self._report(82.0, "submit")
                    publish_btn = find_first_visible(
                        page, self._selectors.publish_buttons, timeout_ms=5000
                    )
                    if publish_btn is None:
                        shot = capture.capture(page, "error_no_publish_btn")
                        raise PermanentPublishError(
                            "No se encontró el botón de publicar en TikTok Studio.",
                            screenshot_path=shot,
                        )
                    publish_btn.click()
                    human_delay(self._min_delay, self._max_delay, sleep_fn=self._sleep)
                    assert_no_challenge_or_login(
                        page, "tiktok", self._selectors, capture, step_name="after_submit"
                    )

                    success = find_first_visible(
                        page, self._selectors.success_indicators, timeout_ms=8000
                    )
                    final_shot = capture.capture(page, "published")
                    if success is None:
                        raise PermanentPublishError(
                            "TikTok no mostró confirmación de publicación tras enviar el video.",
                            screenshot_path=final_shot,
                        )

                    warnings.append(PLAYWRIGHT_TOS_WARNING)
                    self._report(100.0, "done")
                    return PublishResult(
                        external_id=f"pw-tt-{pub_id}",
                        external_url=str(getattr(page, "url", "") or "") or None,
                        delivery_mode="direct",
                        status="published",
                        warnings=warnings,
                        screenshot_path=final_shot,
                        step_screenshots=list(capture.screenshots),
                        raw_status="playwright_submitted",
                    )
                except PublishError:
                    raise
                except Exception as exc:
                    shot = capture.capture(page, "error_unexpected")
                    raise PermanentPublishError(
                        f"Error en publicador Playwright de TikTok ({type(exc).__name__}): {exc}",
                        screenshot_path=shot,
                    ) from exc
