"""Tests de publicadores Playwright contra páginas HTML fixture locales (`task 3.2`)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from winclip.core.config import Settings
from winclip.core.ids import new_clip_id, new_project_id, new_publication_id, new_ulid
from winclip.core.models import Clip, SocialAccount
from winclip.publishers.base import AuthExpiredError, ChallengeDetectedError, PublishMeta
from winclip.publishers.playwright.instagram import InstagramPlaywrightPublisher
from winclip.publishers.playwright.tiktok import TikTokPlaywrightPublisher

TIKTOK_OK_HTML = """<!doctype html>
<html>
  <body>
    <h1>TikTok Studio Fixture</h1>
    <input type="file" accept="video/mp4" id="video-input" />
    <div data-e2e="caption-input" contenteditable="true" role="textbox"></div>
    <button data-e2e="post_video_button">Publicar</button>
    <div id="ok" data-e2e="upload-success" data-reveal-on="post_video_button">
      Tu video se ha publicado
    </div>
  </body>
</html>
"""

TIKTOK_CAPTCHA_HTML = """<!doctype html>
<html>
  <body>
    <div data-e2e="captcha-verify">Verify to continue</div>
  </body>
</html>
"""

INSTAGRAM_OK_HTML = """<!doctype html>
<html>
  <body>
    <button data-testid="create-post-button">Crear</button>
    <input type="file" accept="video/mp4" id="ig-file" />
    <button data-testid="next-step-button">Siguiente</button>
    <textarea name="caption"></textarea>
    <button data-testid="share-reel-button">Compartir</button>
    <div id="shared" data-testid="reel-shared-success" data-reveal-on="share-reel-button">
      Se ha compartido tu reel
    </div>
  </body>
</html>
"""

INSTAGRAM_LOGIN_HTML = """<!doctype html>
<html>
  <body>
    <form id="loginForm">
      <input name="username" />
      <input name="password" type="password" />
    </form>
  </body>
</html>
"""


class _FixtureLocator:
    def __init__(self, page: _HtmlFixturePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _FixtureLocator:
        return self

    def count(self) -> int:
        return 1 if self._page.matches(self._selector, include_hidden=True) else 0

    def is_visible(self, timeout: int = 0) -> bool:
        return self._page.matches(self._selector, include_hidden=False)

    def set_input_files(self, path: str) -> None:
        self._page.uploaded_files.append(path)

    def click(self) -> None:
        self._page.clicked.append(self._selector)
        if "post_video_button" in self._selector:
            self._page.revealed.add("post_video_button")
        if "share-reel-button" in self._selector:
            self._page.revealed.add("share-reel-button")
        if "next-step-button" in self._selector:
            self._page.next_clicks += 1

    def fill(self, value: str) -> None:
        self._page.typed_text.append(value)

    def type(self, value: str, delay: int = 0) -> None:
        self._page.typed_text.append(value)


class _HtmlFixturePage:
    """Driver ligero que lee páginas HTML fixture locales desde disco (`file://`)."""

    def __init__(self) -> None:
        self.url = ""
        self.html = ""
        self.uploaded_files: list[str] = []
        self.clicked: list[str] = []
        self.typed_text: list[str] = []
        self.revealed: set[str] = set()
        self.next_clicks = 0

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> None:
        self.url = url
        parsed = urlparse(url)
        if parsed.scheme == "file":
            self.html = Path(parsed.path).read_text(encoding="utf-8")
        else:
            self.html = ""

    def matches(self, selector: str, *, include_hidden: bool) -> bool:
        if selector == 'input[type="file"][accept*="video"]':
            return 'type="file"' in self.html and 'accept="video' in self.html
        if selector == 'input[type="file"]':
            return 'type="file"' in self.html
        if selector == '[data-e2e="caption-input"]':
            return 'data-e2e="caption-input"' in self.html
        if selector == 'button[data-e2e="post_video_button"]':
            return 'data-e2e="post_video_button"' in self.html
        if selector == '[data-e2e="upload-success"]':
            if 'data-e2e="upload-success"' not in self.html:
                return False
            return include_hidden or ("post_video_button" in self.revealed)
        if selector == '[data-e2e="captcha-verify"]':
            return 'data-e2e="captcha-verify"' in self.html
        if selector == 'button[data-testid="create-post-button"]':
            return 'data-testid="create-post-button"' in self.html
        if selector == 'button[data-testid="next-step-button"]':
            return 'data-testid="next-step-button"' in self.html and self.next_clicks == 0
        if selector == 'textarea[name="caption"]':
            return 'name="caption"' in self.html
        if selector == 'button[data-testid="share-reel-button"]':
            return 'data-testid="share-reel-button"' in self.html
        if selector == '[data-testid="reel-shared-success"]':
            if 'data-testid="reel-shared-success"' not in self.html:
                return False
            return include_hidden or ("share-reel-button" in self.revealed)
        if selector == 'form[id="loginForm"]':
            return 'id="loginForm"' in self.html
        return False

    def locator(self, selector: str) -> _FixtureLocator:
        return _FixtureLocator(self, selector)

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Encabezado PNG válido mínimo
        target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)


class _HtmlFixtureContext:
    def __init__(self, page: _HtmlFixturePage) -> None:
        self.pages = [page]

    def new_page(self) -> _HtmlFixturePage:
        return self.pages[0]

    def cookies(self) -> list[dict[str, Any]]:
        return []


def _make_context_factory(page: _HtmlFixturePage) -> Any:
    @contextlib.contextmanager
    def _factory(_profile_dir: Path, _headless: bool) -> Iterator[_HtmlFixtureContext]:
        yield _HtmlFixtureContext(page)

    return _factory


def _prepare_clip_and_account(
    tmp_path: Path, platform: str
) -> tuple[Settings, Clip, SocialAccount]:
    settings = Settings(storage_dir=tmp_path / "storage", playwright_headless=True)
    proj_id = new_project_id()
    clip_id = new_clip_id()
    acc_id = new_ulid()

    clip_rel = f"projects/{proj_id}/clips/{clip_id}/clip.mp4"
    clip_file = settings.storage_dir / clip_rel
    clip_file.parent.mkdir(parents=True, exist_ok=True)
    clip_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    profile_dir = settings.storage_dir / "accounts" / acc_id / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    clip = Clip(
        id=clip_id, project_id=proj_id, title="Clip local", status="rendered", path=clip_rel
    )
    account = SocialAccount(
        id=acc_id,
        workspace_id="ws-1",
        platform=platform,
        auth_method="playwright",
        display_name=f"Cuenta {platform}",
        handle=f"@{platform}",
        status="connected",
    )
    return settings, clip, account


def test_tiktok_playwright_publishes_on_local_fixture_and_saves_screenshots(tmp_path: Path) -> None:
    settings, clip, account = _prepare_clip_and_account(tmp_path, "tiktok")
    fixture = tmp_path / "tiktok_ok.html"
    fixture.write_text(TIKTOK_OK_HTML, encoding="utf-8")

    page = _HtmlFixturePage()
    pub_id = new_publication_id()
    pub = TikTokPlaywrightPublisher(
        settings=settings,
        context_factory=_make_context_factory(page),
        upload_url_override=fixture.as_uri(),
        sleep_fn=lambda _: None,
        min_delay_sec=0.0,
        max_delay_sec=0.0,
        headless=True,
    )
    result = pub.publish(
        clip,
        account,
        PublishMeta(caption="Hola desde fixture #test", publication_id=pub_id),
    )
    assert result.status == "published"
    assert len(page.uploaded_files) == 1
    assert any("Hola desde fixture" in text for text in page.typed_text)
    assert result.screenshot_path is not None
    assert (settings.storage_dir / result.screenshot_path).is_file()
    assert len(result.step_screenshots) >= 3
    assert any("Términos de Servicio" in w for w in result.warnings)


def test_tiktok_playwright_aborts_immediately_on_captcha_fixture(tmp_path: Path) -> None:
    settings, clip, account = _prepare_clip_and_account(tmp_path, "tiktok")
    fixture = tmp_path / "tiktok_captcha.html"
    fixture.write_text(TIKTOK_CAPTCHA_HTML, encoding="utf-8")

    page = _HtmlFixturePage()
    pub = TikTokPlaywrightPublisher(
        settings=settings,
        context_factory=_make_context_factory(page),
        upload_url_override=fixture.as_uri(),
        sleep_fn=lambda _: None,
        min_delay_sec=0.0,
        max_delay_sec=0.0,
        headless=True,
    )
    with pytest.raises(ChallengeDetectedError) as exc_info:
        pub.publish(clip, account, PublishMeta(caption="Test", publication_id=new_publication_id()))

    assert exc_info.value.code == "challenge_required"
    assert exc_info.value.retryable is False
    assert exc_info.value.screenshot_path is not None
    assert (settings.storage_dir / exc_info.value.screenshot_path).is_file()
    assert len(page.uploaded_files) == 0


def test_instagram_playwright_publishes_on_local_fixture(tmp_path: Path) -> None:
    settings, clip, account = _prepare_clip_and_account(tmp_path, "instagram")
    fixture = tmp_path / "ig_ok.html"
    fixture.write_text(INSTAGRAM_OK_HTML, encoding="utf-8")

    page = _HtmlFixturePage()
    pub = InstagramPlaywrightPublisher(
        settings=settings,
        context_factory=_make_context_factory(page),
        upload_url_override=fixture.as_uri(),
        sleep_fn=lambda _: None,
        min_delay_sec=0.0,
        max_delay_sec=0.0,
        headless=True,
    )
    result = pub.publish(
        clip,
        account,
        PublishMeta(caption="Reel desde fixture #ig", publication_id=new_publication_id()),
    )
    assert result.status == "published"
    assert len(page.uploaded_files) == 1
    assert result.screenshot_path is not None
    assert (settings.storage_dir / result.screenshot_path).is_file()
    assert len(result.step_screenshots) >= 4


def test_instagram_playwright_aborts_on_login_fixture(tmp_path: Path) -> None:
    settings, clip, account = _prepare_clip_and_account(tmp_path, "instagram")
    fixture = tmp_path / "ig_login.html"
    fixture.write_text(INSTAGRAM_LOGIN_HTML, encoding="utf-8")

    page = _HtmlFixturePage()
    pub = InstagramPlaywrightPublisher(
        settings=settings,
        context_factory=_make_context_factory(page),
        upload_url_override=fixture.as_uri(),
        sleep_fn=lambda _: None,
        min_delay_sec=0.0,
        max_delay_sec=0.0,
        headless=True,
    )
    with pytest.raises(AuthExpiredError) as exc_info:
        pub.publish(clip, account, PublishMeta(caption="Test", publication_id=new_publication_id()))

    assert exc_info.value.code == "session_expired"
    assert exc_info.value.retryable is False
    assert exc_info.value.screenshot_path is not None
    assert (settings.storage_dir / exc_info.value.screenshot_path).is_file()
    assert len(page.uploaded_files) == 0
