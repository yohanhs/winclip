"""Tests de utilidades comunes de Playwright: selectores, lock, capturas y retos (`task 3.1`)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from winclip.core.storage import LocalStorage
from winclip.publishers.base import AuthExpiredError, ChallengeDetectedError
from winclip.publishers.playwright.selectors import (
    INSTAGRAM_SELECTORS,
    TIKTOK_SELECTORS,
    StepCapture,
    account_browser_lock,
    assert_no_challenge_or_login,
    find_first_visible,
    human_delay,
)


class _FakeLocator:
    def __init__(self, visible: bool) -> None:
        self._visible = visible

    @property
    def first(self) -> _FakeLocator:
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self._visible


class _FakePage:
    def __init__(self, url: str, visible_selectors: set[str] | None = None) -> None:
        self.url = url
        self._visible = visible_selectors or set()

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(selector in self._visible)

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\nfake")


def test_human_delay_calls_sleep_within_bounds() -> None:
    recorded: list[float] = []
    val = human_delay(0.5, 1.5, sleep_fn=recorded.append)
    assert 0.5 <= val <= 1.5
    assert recorded == [val]


def test_account_browser_lock_serializes_same_account() -> None:
    order: list[str] = []
    started = threading.Event()

    def worker() -> None:
        with account_browser_lock("acc-sync"):
            started.set()
            order.append("t1-enter")
            threading.Event().wait(0.05)
            order.append("t1-exit")

    thread = threading.Thread(target=worker)
    thread.start()
    started.wait(1.0)
    with account_browser_lock("acc-sync"):
        order.append("main-enter")
    thread.join(2.0)

    assert order == ["t1-enter", "t1-exit", "main-enter"]


def test_step_capture_saves_under_publications_dir(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    capture = StepCapture(storage, "pub01")
    page = _FakePage("https://example.com")

    rel = capture.capture(page, "open upload")
    assert rel == "publications/pub01/steps/01_open_upload.png"
    assert (storage.root / rel).is_file()
    assert capture.last_path == rel


def test_assert_no_challenge_aborts_immediately_and_captures(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    capture = StepCapture(storage, "pub02")
    page = _FakePage(
        "https://www.tiktok.com/tiktokstudio/upload",
        visible_selectors={'[data-e2e="captcha-verify"]'},
    )

    with pytest.raises(ChallengeDetectedError) as exc_info:
        assert_no_challenge_or_login(page, "tiktok", TIKTOK_SELECTORS, capture, step_name="open")

    assert exc_info.value.code == "challenge_required"
    assert exc_info.value.retryable is False
    assert exc_info.value.screenshot_path is not None
    assert (storage.root / exc_info.value.screenshot_path).is_file()


def test_assert_no_login_aborts_on_redirect_to_login(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    capture = StepCapture(storage, "pub03")
    page = _FakePage("https://www.instagram.com/accounts/login/")

    with pytest.raises(AuthExpiredError) as exc_info:
        assert_no_challenge_or_login(
            page, "instagram", INSTAGRAM_SELECTORS, capture, step_name="open"
        )

    assert exc_info.value.code == "session_expired"
    assert exc_info.value.retryable is False
    assert exc_info.value.screenshot_path is not None
    assert (storage.root / exc_info.value.screenshot_path).is_file()


def test_find_first_visible_falls_back_in_order() -> None:
    page: Any = _FakePage("https://example.com", visible_selectors={"#second"})
    found = find_first_visible(page, ("#first", "#second", "#third"), timeout_ms=300)
    assert found is not None
