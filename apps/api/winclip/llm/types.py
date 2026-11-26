"""Contratos internos del gateway LLM (`docs/architecture.md §8`).

Los proveedores implementan `LLMProvider`; el router los envuelve en `LLMResult`.
Ninguna estructura de este módulo contiene claves de API.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, ValidationError

_FENCE_PATTERN = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(?P<body>.*?)\n?```$", re.DOTALL)


class TokenUsage(BaseModel):
    """Consumo reportado por el SDK (0 cuando el proveedor no lo informa)."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class ProviderAttempt(BaseModel):
    """Resultado de intentar un proveedor concreto dentro de una solicitud."""

    provider: str
    model: str = ""
    status: Literal["ok", "skipped", "error"]
    error: str | None = None
    latency_ms: int = Field(default=0, ge=0)


class LLMResult[T: BaseModel](BaseModel):
    """Respuesta validada más trazabilidad de proveedor, caché y tokens."""

    data: T
    provider: str
    model: str
    cached: bool = False
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    attempts: list[ProviderAttempt] = Field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Identificador compuesto para `candidates.json.provider`."""
        return f"{self.provider}:{self.model}"


class LLMError(RuntimeError):
    """Error base del gateway; `retryable` indica si conviene reintentar."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = False


class RateLimitError(LLMError):
    """El proveedor respondió 429 (cuota o límite de tasa)."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message, provider=provider)
        self.retryable = True


class ProviderUnavailableError(LLMError):
    """Fallo de red, timeout, 5xx o credenciales/modelo inutilizables."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retryable = retryable


class InvalidJSONResponseError(LLMError):
    """El texto devuelto no es JSON válido o no cumple el esquema Pydantic."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message, provider=provider)


class NoProviderAvailableError(LLMError):
    """Ningún proveedor del orden configurado logró una respuesta válida."""

    def __init__(self, message: str, *, attempts: list[ProviderAttempt] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


@runtime_checkable
class LLMProvider(Protocol):
    """Interfaz de proveedor LLM (`docs/architecture.md §8`) con modelo y uso."""

    name: str
    model: str
    last_usage: TokenUsage | None

    def available(self) -> bool: ...

    def complete_json[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T: ...


def estimate_tokens(text: str) -> int:
    """Estimación aproximada (~4 caracteres por token) sin dependencias extra."""
    return max(1, len(text) // 4)


def scrub_secrets(text: str, secrets: list[str] | tuple[str, ...]) -> str:
    """Elimina cualquier clave conocida del texto antes de registrarlo."""
    cleaned = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            cleaned = cleaned.replace(secret, "***")
    return cleaned


def _status_code(exc: BaseException) -> int | None:
    """Extrae el código HTTP de excepciones de los SDK (openai y google-genai)."""
    for attribute in ("status_code", "status", "code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def map_provider_error(
    exc: BaseException,
    *,
    provider: str,
    secrets: list[str] | tuple[str, ...] = (),
) -> LLMError:
    """Traduce errores de SDK a las excepciones tipadas del gateway."""
    status = _status_code(exc)
    name = type(exc).__name__
    message = scrub_secrets(f"{name}: {exc}", secrets)
    prefix = f"{provider}: "

    if status == 429 or "ratelimit" in name.lower():
        return RateLimitError(f"{prefix}límite de tasa (HTTP 429): {message}", provider=provider)
    if status is not None and 500 <= status < 600:
        return ProviderUnavailableError(
            f"{prefix}error de servidor (HTTP {status}): {message}",
            provider=provider,
            retryable=True,
        )
    if status in (401, 403, 404):
        return ProviderUnavailableError(
            f"{prefix}credenciales o modelo no utilizables (HTTP {status}): {message}",
            provider=provider,
        )
    if any(token in name for token in ("Timeout", "Connection")):
        return ProviderUnavailableError(
            f"{prefix}fallo de red o timeout: {message}",
            provider=provider,
            retryable=True,
        )
    return ProviderUnavailableError(f"{prefix}error del proveedor: {message}", provider=provider)


def parse_json_payload[T: BaseModel](text: str, schema: type[T]) -> T:
    """Extrae el objeto JSON (tolera vallas markdown) y lo valida con Pydantic."""
    raw = (text or "").strip()
    fence = _FENCE_PATTERN.match(raw)
    if fence:
        raw = fence.group("body").strip()
    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start : end + 1]

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidJSONResponseError(
            f"JSON inválido: {exc.msg} (línea {exc.lineno}, columna {exc.colno})"
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidJSONResponseError("la respuesta debe ser un objeto JSON")

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'raíz'}: {error['msg']}"
            for error in exc.errors()
        )
        raise InvalidJSONResponseError(f"esquema inválido: {details}") from exc
