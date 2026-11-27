"""Tests de contratos base `Publisher`, errores y registro (`task 1.1`)."""

from __future__ import annotations

import pytest

from winclip.core.models import Clip, SocialAccount
from winclip.publishers.base import (
    AccountStatus,
    AuthExpiredError,
    ChallengeDetectedError,
    DailyLimitExceededError,
    MissedScheduleWindowError,
    PermanentPublishError,
    Publisher,
    PublishError,
    PublishMeta,
    PublishResult,
    PublishValidationError,
    QuotaExceededError,
    TransientPublishError,
    UnsupportedPublisherError,
)
from winclip.publishers.registry import (
    clear_custom_publishers,
    get_publisher,
    register_publisher,
    supported_publisher_keys,
    unregister_publisher,
)


class _DummyPublisher:
    platform = "youtube"

    def __init__(self, *, tag: str = "default") -> None:
        self.tag = tag

    def check(self, account: SocialAccount) -> AccountStatus:
        return AccountStatus(status="connected", message=f"ok:{account.id}:{self.tag}")

    def publish(self, clip: Clip, account: SocialAccount, meta: PublishMeta) -> PublishResult:
        return PublishResult(
            external_id=f"ext-{clip.id}",
            external_url=f"https://example.com/{clip.id}",
            delivery_mode=meta.delivery_mode,
        )


def _account(platform: str, auth_method: str) -> SocialAccount:
    return SocialAccount(
        id="acc-1",
        workspace_id="ws-1",
        platform=platform,
        auth_method=auth_method,
        display_name="Cuenta",
        handle="@cuenta",
        status="connected",
    )


def test_error_hierarchy_distinguishes_transient_and_permanent() -> None:
    transient = TransientPublishError("timeout")
    assert isinstance(transient, PublishError)
    assert transient.retryable is True
    assert transient.code == "transient_error"

    for exc_cls, expected_code in [
        (PermanentPublishError, "permanent_error"),
        (PublishValidationError, "validation_error"),
        (AuthExpiredError, "session_expired"),
        (QuotaExceededError, "quota_exceeded"),
        (ChallengeDetectedError, "challenge_required"),
        (DailyLimitExceededError, "daily_limit_exceeded"),
        (MissedScheduleWindowError, "missed_schedule_window"),
        (UnsupportedPublisherError, "unsupported_publisher"),
    ]:
        err = exc_cls("boom", screenshot_path="publications/p1/error.png", external_id="vid-1")
        assert isinstance(err, PublishError)
        assert err.retryable is False
        assert err.code == expected_code
        assert err.screenshot_path == "publications/p1/error.png"
        assert err.external_id == "vid-1"


def test_publisher_protocol_and_custom_registry() -> None:
    clear_custom_publishers()
    try:
        register_publisher("youtube", "api", _DummyPublisher)
        acc = _account("youtube", "api")
        pub = get_publisher(acc, tag="custom")
        assert isinstance(pub, Publisher)
        assert pub.check(acc).status == "connected"
        clip = Clip(id="clip-1", project_id="proj-1", title="Hola")
        res = pub.publish(clip, acc, PublishMeta(title="Hola"))
        assert res.external_id == "ext-clip-1"
    finally:
        unregister_publisher("youtube", "api")


def test_unsupported_publisher_raises_permanent_error() -> None:
    acc = _account("youtube", "playwright")
    with pytest.raises(UnsupportedPublisherError):
        get_publisher(acc)


def test_supported_publisher_keys_contains_all_five_targets() -> None:
    keys = set(supported_publisher_keys())
    assert {
        ("youtube", "api"),
        ("tiktok", "api"),
        ("instagram", "api"),
        ("tiktok", "playwright"),
        ("instagram", "playwright"),
    }.issubset(keys)
