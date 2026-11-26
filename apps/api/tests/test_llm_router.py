"""Tests de `winclip.llm.router` con proveedores falsos (sin red)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeLLMProvider
from pydantic import BaseModel

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.llm.cache import LLMCache
from winclip.llm.router import LLMRouter
from winclip.llm.types import (
    InvalidJSONResponseError,
    NoProviderAvailableError,
    ProviderUnavailableError,
    RateLimitError,
)


class Answer(BaseModel):
    text: str
    score: int = 0


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _router(
    providers: dict[str, FakeLLMProvider],
    *,
    order: str,
    tmp_path: Path | None = None,
    sleeps: list[float] | None = None,
    max_retries: int = 2,
) -> LLMRouter:
    recorded = sleeps if sleeps is not None else []
    settings = _settings(
        llm_provider_order=order,
        llm_max_retries_per_provider=max_retries,
        storage_dir=tmp_path / "storage"
        if tmp_path is not None
        else Path("/tmp/winclip-router-tests"),
    )
    cache = LLMCache(LocalStorage(settings.storage_dir)) if tmp_path is not None else None
    return LLMRouter(
        settings,
        providers,
        cache=cache,
        sleep_fn=recorded.append,
        jitter_fn=lambda: 0.0,
    )


def test_skips_unavailable_provider_and_uses_next(tmp_path: Path) -> None:
    unavailable = FakeLLMProvider("sin-clave", available=False)
    healthy = FakeLLMProvider("con-clave", responses=[Answer(text="hola")])
    router = _router(
        {"sin-clave": unavailable, "con-clave": healthy},
        order="sin-clave,con-clave",
        tmp_path=tmp_path,
    )

    result = router.complete_json("s", "u", Answer, logical_model="test:v1")

    assert result.data == Answer(text="hola")
    assert result.provider == "con-clave"
    assert result.provider_id == "con-clave:fake-1"
    assert [attempt.status for attempt in result.attempts] == ["skipped", "ok"]
    assert unavailable.calls == []


def test_retries_429_with_backoff_then_falls_back(tmp_path: Path) -> None:
    throttled = FakeLLMProvider(
        "limitado",
        responses=[
            RateLimitError("429", provider="limitado"),
            RateLimitError("429", provider="limitado"),
            RateLimitError("429", provider="limitado"),
        ],
    )
    healthy = FakeLLMProvider("sano", responses=[Answer(text="ok")])
    sleeps: list[float] = []
    router = _router(
        {"limitado": throttled, "sano": healthy},
        order="limitado,sano",
        tmp_path=tmp_path,
        sleeps=sleeps,
        max_retries=2,
    )

    result = router.complete_json("s", "u", Answer, logical_model="test:v1")

    assert result.provider == "sano"
    assert len(throttled.calls) == 3
    assert sleeps == [1.0, 2.0]
    assert result.attempts[0].status == "error"
    assert "429" in (result.attempts[0].error or "")


def test_retries_retryable_errors_and_skips_non_retryable(tmp_path: Path) -> None:
    transient = FakeLLMProvider(
        "transitorio",
        responses=[
            ProviderUnavailableError("timeout", retryable=True),
            ProviderUnavailableError("timeout", retryable=True),
        ],
    )
    healthy = FakeLLMProvider("sano", responses=[Answer(text="ok")])
    router = _router(
        {"transitorio": transient, "sano": healthy},
        order="transitorio,sano",
        tmp_path=tmp_path,
        max_retries=1,
    )
    assert router.complete_json("s", "u", Answer, logical_model="test:v1").provider == "sano"
    assert len(transient.calls) == 2

    forbidden = FakeLLMProvider(
        "prohibido",
        responses=[ProviderUnavailableError("401", retryable=False)],
    )
    router = _router(
        {"prohibido": forbidden, "sano": FakeLLMProvider("sano", responses=[Answer(text="ok")])},
        order="prohibido,sano",
        tmp_path=tmp_path,
    )
    assert router.complete_json("s", "u", Answer, logical_model="test:v2").provider == "sano"
    assert len(forbidden.calls) == 1


def test_json_correction_retry_in_same_provider(tmp_path: Path) -> None:
    provider = FakeLLMProvider(
        "corrige",
        responses=[
            InvalidJSONResponseError("esquema inválido: text: campo requerido"),
            Answer(text="corregido"),
        ],
    )
    router = _router({"corrige": provider}, order="corrige", tmp_path=tmp_path)

    result = router.complete_json("s", "u", Answer, logical_model="test:v1")

    assert result.data == Answer(text="corregido")
    assert len(provider.calls) == 2
    assert "CORRECCIÓN OBLIGATORIA" in provider.calls[1][1]
    assert "campo requerido" in provider.calls[1][1]
    assert result.attempts[0].status == "ok"


def test_persistent_invalid_json_exhausts_corrections_and_falls_back(tmp_path: Path) -> None:
    broken = FakeLLMProvider(
        "roto",
        responses=[InvalidJSONResponseError("mal") for _ in range(3)],
    )
    healthy = FakeLLMProvider("sano", responses=[Answer(text="ok")])
    router = _router({"roto": broken, "sano": healthy}, order="roto,sano", tmp_path=tmp_path)

    result = router.complete_json("s", "u", Answer, logical_model="test:v1")

    assert result.provider == "sano"
    assert len(broken.calls) == 3


def test_all_providers_failing_raises_descriptive_error(tmp_path: Path) -> None:
    first = FakeLLMProvider("uno", responses=[ProviderUnavailableError("caído")])
    second = FakeLLMProvider("dos", available=False)
    router = _router({"uno": first, "dos": second}, order="uno,dos", tmp_path=tmp_path)

    with pytest.raises(NoProviderAvailableError) as info:
        router.complete_json("s", "u", Answer, logical_model="test:v1")

    message = str(info.value)
    assert "uno: caído" in message
    assert "dos: sin credenciales" in message
    assert [attempt.status for attempt in info.value.attempts] == ["error", "skipped"]


def test_cache_hit_skips_provider(tmp_path: Path) -> None:
    first = FakeLLMProvider("gemini", responses=[Answer(text="cacheado")])
    router = _router({"gemini": first}, order="gemini", tmp_path=tmp_path)
    initial = router.complete_json("s", "u", Answer, logical_model="clip-selection:single:v1")
    assert initial.cached is False

    never_called = FakeLLMProvider("gemini")
    cached_router = _router({"gemini": never_called}, order="gemini", tmp_path=tmp_path)
    cached = cached_router.complete_json("s", "u", Answer, logical_model="clip-selection:single:v1")

    assert cached.cached is True
    assert cached.data == Answer(text="cacheado")
    assert cached.attempts == []
    assert never_called.calls == []
    assert cached.provider == "gemini"


def test_cache_invalidated_by_prompt_version_and_no_cache_flag(tmp_path: Path) -> None:
    provider = FakeLLMProvider(
        "gemini",
        responses=[Answer(text="v1"), Answer(text="v2"), Answer(text="sin caché")],
    )
    router = _router({"gemini": provider}, order="gemini", tmp_path=tmp_path)

    assert router.complete_json("s", "u", Answer, logical_model="single:v1").data.text == "v1"
    assert router.complete_json("s", "u", Answer, logical_model="single:v2").data.text == "v2"
    assert (
        router.complete_json("s", "u", Answer, logical_model="single:v1", use_cache=False).data.text
        == "sin caché"
    )
    assert len(provider.calls) == 3


def test_cache_files_never_contain_api_keys(tmp_path: Path) -> None:
    secret = "clave-gemini-que-no-debe-persistir"
    provider = FakeLLMProvider("gemini", responses=[Answer(text="hola")])
    router = _router({"gemini": provider}, order="gemini", tmp_path=tmp_path)
    router.complete_json("sistema", "usuario", Answer, logical_model="single:v1")

    cache_dir = tmp_path / "storage" / "cache" / "llm"
    contents = "".join(path.read_text(encoding="utf-8") for path in cache_dir.glob("*.json"))

    assert contents
    assert secret not in contents
    assert "GEMINI_API_KEY" not in contents


def test_token_usage_falls_back_to_estimation(tmp_path: Path) -> None:
    provider = FakeLLMProvider("fake", responses=[Answer(text="x" * 40)])
    router = _router({"fake": provider}, order="fake", tmp_path=tmp_path)

    result = router.complete_json("sistema", "usuario", Answer, logical_model="single:v1")

    assert result.prompt_tokens >= 1
    assert result.completion_tokens >= 1


def test_token_usage_uses_sdk_values_when_available(tmp_path: Path) -> None:
    from winclip.llm.types import TokenUsage

    provider = FakeLLMProvider(
        "fake",
        responses=[Answer(text="hola")],
        usage=TokenUsage(prompt_tokens=123, completion_tokens=45),
    )
    router = _router({"fake": provider}, order="fake", tmp_path=tmp_path)

    result = router.complete_json("s", "u", Answer, logical_model="single:v1")

    assert (result.prompt_tokens, result.completion_tokens) == (123, 45)


def test_router_without_providers_fails_cleanly(tmp_path: Path) -> None:
    router = _router({}, order="gemini", tmp_path=tmp_path)

    with pytest.raises(NoProviderAvailableError, match="no hay proveedores"):
        router.complete_json("s", "u", Answer, logical_model="single:v1")
