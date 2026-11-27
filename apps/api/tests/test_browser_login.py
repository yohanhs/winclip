"""Tests de `winclip/accounts/browser_login.py` y `publishers/playwright/session.py`."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session

from winclip.accounts.browser_login import (
    BrowserLoginConflictError,
    BrowserLoginManager,
    check_browser_account_health,
)
from winclip.accounts.crypto import LocalCredentialStore
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, ensure_default_workspace, init_db
from winclip.core.ids import new_ulid
from winclip.core.models import SocialAccount


class _FakePage:
    def __init__(self, url: str = "", title: str = "") -> None:
        self.url = url
        self._title = title

    def goto(self, url: str, **_kwargs: Any) -> None:
        self.url = url

    def title(self) -> str:
        return self._title


class _FakeContext:
    def __init__(
        self,
        *,
        cookies_sequence: list[list[dict[str, Any]]],
        urls_sequence: list[str] | None = None,
        title: str = "Creator Profile @creator_tt",
    ) -> None:
        self._cookies_seq = cookies_sequence
        self._urls_seq = urls_sequence or []
        self._calls = 0
        self.page = _FakePage(title=title)
        self.pages = [self.page]
        self.closed = False

    def cookies(self) -> list[dict[str, Any]]:
        idx = min(self._calls, len(self._cookies_seq) - 1)
        if self._urls_seq:
            u_idx = min(self._calls, len(self._urls_seq) - 1)
            self.page.url = self._urls_seq[u_idx]
        self._calls += 1
        return self._cookies_seq[idx]

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


def _wait_for_terminal(mgr: BrowserLoginManager, account_id: str, timeout: float = 3.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sess = mgr.get_session(account_id)
        if sess is not None and sess.status != "waiting":
            return sess.status
        time.sleep(0.02)
    raise AssertionError("La sesión de navegador no terminó a tiempo")


def test_browser_login_detects_cookie_and_marks_connected(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path / "storage")
    engine = init_db(settings)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        acc = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="tiktok",
            display_name="TikTok (navegador)",
            auth_method="playwright",
            credentials_ref="accounts/x/profile",
            status="pending",
        )
        session.add(acc)
        session.commit()
        acc_id = acc.id

    fake_ctx = _FakeContext(
        cookies_sequence=[
            [],
            [{"name": "sessionid", "value": "fake-cookie-val", "domain": ".tiktok.com"}],
        ],
        urls_sequence=[
            "https://www.tiktok.com/login",
            "https://www.tiktok.com/@creator_tt",
        ],
        title="Creator TT (@creator_tt)",
    )

    @contextlib.contextmanager
    def factory(profile_dir: Path, headless: bool) -> Iterator[_FakeContext]:
        assert headless is False
        assert profile_dir.is_dir()
        try:
            yield fake_ctx
        finally:
            fake_ctx.close()

    mgr = BrowserLoginManager()
    mgr.start_login(
        engine=engine,
        settings=settings,
        account_id=acc_id,
        platform="tiktok",
        timeout_seconds=5.0,
        poll_interval=0.05,
        context_factory=factory,
    )

    status = _wait_for_terminal(mgr, acc_id)
    assert status == "connected"
    assert fake_ctx.closed is True

    with Session(engine) as session:
        updated = session.get(SocialAccount, acc_id)
        assert updated is not None
        assert updated.status == "connected"
        assert updated.handle == "@creator_tt"


def test_browser_login_cancel_and_conflict_lock(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path / "storage")
    engine = init_db(settings)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        acc = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="instagram",
            display_name="Instagram (navegador)",
            auth_method="playwright",
            credentials_ref="accounts/x/profile",
            status="pending",
        )
        session.add(acc)
        session.commit()
        acc_id = acc.id

    fake_ctx = _FakeContext(
        cookies_sequence=[[]],
        urls_sequence=["https://www.instagram.com/accounts/login/"],
    )

    @contextlib.contextmanager
    def factory(_profile_dir: Path, _headless: bool) -> Iterator[_FakeContext]:
        yield fake_ctx

    mgr = BrowserLoginManager()
    mgr.start_login(
        engine=engine,
        settings=settings,
        account_id=acc_id,
        platform="instagram",
        timeout_seconds=10.0,
        poll_interval=0.05,
        context_factory=factory,
    )

    with pytest.raises(BrowserLoginConflictError):
        mgr.start_login(
            engine=engine,
            settings=settings,
            account_id=acc_id,
            platform="instagram",
            context_factory=factory,
        )

    mgr.cancel_login(acc_id)
    assert _wait_for_terminal(mgr, acc_id) == "cancelled"

    with Session(engine) as session:
        unchanged = session.get(SocialAccount, acc_id)
        assert unchanged is not None
        assert unchanged.status == "pending"


def test_browser_account_health_check_detects_expired_session(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path / "storage")
    engine = init_db(settings)
    store = LocalCredentialStore(settings)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        acc_id = new_ulid()
        store.ensure_profile_dir(acc_id)
        acc = SocialAccount(
            id=acc_id,
            workspace_id=ws.id,
            platform="tiktok",
            display_name="TT Browser",
            auth_method="playwright",
            credentials_ref=store.profile_relpath(acc_id),
            status="connected",
        )
        session.add(acc)
        session.commit()

        @contextlib.contextmanager
        def expired_factory(_profile_dir: Path, headless: bool) -> Iterator[_FakeContext]:
            assert headless is True
            yield _FakeContext(
                cookies_sequence=[[]],
                urls_sequence=["https://www.tiktok.com/login"],
            )

        checked = check_browser_account_health(
            session, acc, settings, context_factory=expired_factory
        )
        assert checked.status == "expired"
        assert checked.last_error is not None
