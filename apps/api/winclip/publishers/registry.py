"""Registro dinámico de publicadores por `(platform, auth_method)` (`design.md`, decisión 1)."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from winclip.core.models import SocialAccount
from winclip.publishers.base import Publisher, UnsupportedPublisherError

PublisherKey = tuple[str, str]
PublisherFactory = Callable[..., Publisher]

_DEFAULT_IMPORTS: dict[PublisherKey, tuple[str, str]] = {
    ("youtube", "api"): ("winclip.publishers.youtube_api", "YouTubeApiPublisher"),
    ("tiktok", "api"): ("winclip.publishers.tiktok_api", "TikTokApiPublisher"),
    ("instagram", "api"): ("winclip.publishers.instagram_graph", "InstagramGraphPublisher"),
    ("tiktok", "playwright"): ("winclip.publishers.playwright.tiktok", "TikTokPlaywrightPublisher"),
    ("instagram", "playwright"): (
        "winclip.publishers.playwright.instagram",
        "InstagramPlaywrightPublisher",
    ),
}

_CUSTOM_REGISTRY: dict[PublisherKey, PublisherFactory] = {}


def register_publisher(platform: str, auth_method: str, factory: PublisherFactory) -> None:
    """Registra una fábrica personalizada para `(platform, auth_method)` (útil en tests)."""
    key = (platform.strip().lower(), auth_method.strip().lower())
    _CUSTOM_REGISTRY[key] = factory


def unregister_publisher(platform: str, auth_method: str) -> None:
    """Elimina un registro personalizado (restaurando el valor por defecto si existe)."""
    key = (platform.strip().lower(), auth_method.strip().lower())
    _CUSTOM_REGISTRY.pop(key, None)


def clear_custom_publishers() -> None:
    """Limpia todos los registros personalizados."""
    _CUSTOM_REGISTRY.clear()


def supported_publisher_keys() -> tuple[PublisherKey, ...]:
    """Claves `(platform, auth_method)` soportadas actualmente."""
    keys = set(_DEFAULT_IMPORTS.keys()) | set(_CUSTOM_REGISTRY.keys())
    return tuple(sorted(keys))


def _load_default_factory(key: PublisherKey) -> PublisherFactory:
    target = _DEFAULT_IMPORTS.get(key)
    if target is None:
        raise UnsupportedPublisherError(
            f"No existe publicador para platform={key[0]!r}, auth_method={key[1]!r}"
        )
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name)
    return factory  # type: ignore[no-any-return]


def get_publisher(account: SocialAccount, **kwargs: Any) -> Publisher:
    """Resuelve e instancia el `Publisher` adecuado para `account`."""
    key = (account.platform.strip().lower(), account.auth_method.strip().lower())
    factory = _CUSTOM_REGISTRY.get(key)
    if factory is None:
        factory = _load_default_factory(key)
    return factory(**kwargs)
