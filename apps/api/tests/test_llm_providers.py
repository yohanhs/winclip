"""Tests de `winclip.llm.providers` con SDKs simulados (sin red)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from winclip.core.config import Settings
from winclip.llm.providers import GroqProvider, NvidiaProvider, OllamaProvider, OpenRouterProvider
from winclip.llm.providers.gemini import GeminiProvider
from winclip.llm.types import (
    InvalidJSONResponseError,
    ProviderUnavailableError,
    RateLimitError,
    parse_json_payload,
)


class Ping(BaseModel):
    ok: bool


class FakeStatusError(Exception):
    """Error genérico con código HTTP, como los de los SDK reales."""

    def __init__(self, status_code: int, detail: str = "fallo") -> None:
        super().__init__(detail)
        self.status_code = status_code


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def _reply(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=5),
    )


class FakeCompletions:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeOpenAIClient:
    def __init__(self, outcome: Any) -> None:
        self.completions = FakeCompletions(outcome)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeGeminiModels:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeGeminiClient:
    def __init__(self, outcome: Any) -> None:
        self.models = FakeGeminiModels(outcome)


class FakeHTTPResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeHTTPClient:
    def __init__(self, response: Any = None, error: BaseException | None = None) -> None:
        self.response = response if response is not None else FakeHTTPResponse(200)
        self.error = error
        self.calls: list[tuple[str, Any]] = []

    def get(self, url: str, timeout: Any = None) -> Any:
        self.calls.append((url, timeout))
        if self.error is not None:
            raise self.error
        return self.response


def test_gemini_requires_key_and_forces_json_schema() -> None:
    assert GeminiProvider(_settings()).available() is False

    client = FakeGeminiClient(SimpleNamespace(text='{"ok": true}'))
    provider = GeminiProvider(_settings(gemini_api_key="clave-gemini"), client=client)

    assert provider.available() is True
    result = provider.complete_json("sistema", "usuario", Ping)

    assert result == Ping(ok=True)
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "usuario"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is Ping
    assert provider.last_usage is not None
    assert provider.last_usage.prompt_tokens == 0


def test_gemini_maps_rate_limit_and_server_errors() -> None:
    provider = GeminiProvider(
        _settings(gemini_api_key="clave-gemini"),
        client=FakeGeminiClient(FakeStatusError(429, "cuota agotada")),
    )
    with pytest.raises(RateLimitError):
        provider.complete_json("s", "u", Ping)

    provider = GeminiProvider(
        _settings(gemini_api_key="clave-gemini"),
        client=FakeGeminiClient(FakeStatusError(503, "no disponible")),
    )
    with pytest.raises(ProviderUnavailableError) as info:
        provider.complete_json("s", "u", Ping)
    assert info.value.retryable is True


def test_openai_compatible_request_and_usage() -> None:
    client = FakeOpenAIClient(_reply('{"ok": true}'))
    provider = NvidiaProvider(_settings(nvidia_api_key="clave-nvidia"), client=client)

    assert provider.available() is True
    assert provider.complete_json("sistema", "usuario", Ping) == Ping(ok=True)

    call = client.completions.calls[0]
    assert call["model"] == "meta/llama-3.3-70b-instruct"
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0] == {"role": "system", "content": "sistema"}
    assert provider.last_usage is not None
    assert (provider.last_usage.prompt_tokens, provider.last_usage.completion_tokens) == (11, 5)


@pytest.mark.parametrize(
    ("provider_class", "key_env"),
    [
        (NvidiaProvider, "nvidia_api_key"),
        (OpenRouterProvider, "openrouter_api_key"),
        (GroqProvider, "groq_api_key"),
    ],
)
def test_openai_compatible_providers_skip_without_key(
    provider_class: type[NvidiaProvider | OpenRouterProvider | GroqProvider], key_env: str
) -> None:
    assert provider_class(_settings()).available() is False
    assert provider_class(_settings(**{key_env: "clave"})).available() is True


def test_openai_compatible_maps_http_errors() -> None:
    provider = GroqProvider(
        _settings(groq_api_key="clave-groq"),
        client=FakeOpenAIClient(FakeStatusError(401, "no autorizado")),
    )
    with pytest.raises(ProviderUnavailableError) as info:
        provider.complete_json("s", "u", Ping)
    assert info.value.retryable is False

    provider = GroqProvider(
        _settings(groq_api_key="clave-groq"),
        client=FakeOpenAIClient(FakeStatusError(500, "boom")),
    )
    with pytest.raises(ProviderUnavailableError) as info:
        provider.complete_json("s", "u", Ping)
    assert info.value.retryable is True


def test_provider_errors_never_leak_the_api_key() -> None:
    secret = "clave-super-secreta-123"
    provider = GroqProvider(
        _settings(groq_api_key=secret),
        client=FakeOpenAIClient(FakeStatusError(400, f"token {secret} inválido")),
    )

    with pytest.raises(ProviderUnavailableError) as info:
        provider.complete_json("s", "u", Ping)

    assert secret not in str(info.value)
    assert "***" in str(info.value)


def test_ollama_probes_tags_once_and_ignores_missing_key() -> None:
    http = FakeHTTPClient(FakeHTTPResponse(200))
    client = FakeOpenAIClient(_reply('{"ok": true}'))
    provider = OllamaProvider(
        _settings(ollama_host="http://127.0.0.1:11434/"), http_client=http, client=client
    )

    assert provider.available() is True
    assert provider.available() is True
    assert len(http.calls) == 1
    assert http.calls[0][0] == "http://127.0.0.1:11434/api/tags"
    assert http.calls[0][1] == 2.0
    assert provider.complete_json("s", "u", Ping) == Ping(ok=True)
    call = client.completions.calls[0]
    assert call["model"] == "qwen3.5:4b"


def test_ollama_unavailable_when_service_does_not_answer() -> None:
    provider = OllamaProvider(
        _settings(),
        http_client=FakeHTTPClient(error=RuntimeError("connection refused")),
    )

    assert provider.available() is False


def test_parse_json_payload_accepts_markdown_fences_and_prose() -> None:
    assert parse_json_payload('```json\n{"ok": true}\n```', Ping) == Ping(ok=True)
    assert parse_json_payload('Aquí tienes: {"ok": true} fin', Ping) == Ping(ok=True)


def test_parse_json_payload_reports_invalid_json() -> None:
    with pytest.raises(InvalidJSONResponseError, match="JSON inválido"):
        parse_json_payload("no es json", Ping)

    with pytest.raises(InvalidJSONResponseError, match="esquema inválido"):
        parse_json_payload('{"ok": "quizá"}', Ping)
