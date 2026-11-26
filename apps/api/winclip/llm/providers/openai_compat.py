"""Base común de proveedores compatibles con la API OpenAI (`/chat/completions`)."""

from __future__ import annotations

from typing import Any

from winclip.core.config import Settings
from winclip.llm.types import (
    TokenUsage,
    map_provider_error,
    parse_json_payload,
)

# Marcadores con los que algunos servidores rechazan `response_format`.
_UNSUPPORTED_FORMAT_MARKERS = (
    "structured output",
    "structured_output",
    "response_format",
    "response format",
    "json_object",
)


def _http_status(exc: BaseException) -> int | None:
    """Extrae el código HTTP de las excepciones del SDK `openai`."""
    for attribute in ("status_code", "status", "code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _rejects_response_format(exc: BaseException) -> bool:
    """`True` si el proveedor no soporta `response_format` (HTTP 400 o 501)."""
    if _http_status(exc) not in (400, 501):
        return False
    message = str(exc).lower()
    return any(marker in message for marker in _UNSUPPORTED_FORMAT_MARKERS)


class OpenAICompatibleProvider:
    """Cliente mínimo sobre el SDK `openai` con base_url, clave y modelo inyectables."""

    def __init__(
        self,
        settings: Settings,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        client: Any | None = None,
        extra_headers: dict[str, str] | None = None,
        error_secrets: list[str] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.last_usage: TokenUsage | None = None
        self._api_key = api_key.strip()
        self._client = client
        self._extra_headers = extra_headers or {}
        # Claves a redactar en los errores; los proveedores con clave ficticia las anulan.
        self._error_secrets = [self._api_key] if error_secrets is None else list(error_secrets)

    def available(self) -> bool:
        """Un proveedor con API key es disponible; sin clave se omite."""
        return bool(self._api_key)

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key or "sin-clave",
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def _request(self, client: Any, kwargs: dict[str, Any]) -> Any:
        """Llama a `chat.completions.create`, reintentando sin `response_format`."""
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # el SDK expone tipos distintos por versión
            if not _rejects_response_format(exc):
                raise map_provider_error(
                    exc, provider=self.name, secrets=self._error_secrets
                ) from exc
            # Servidores como Ollama 0.40 con qwen3.5:4b no soportan structured output:
            # se repite la llamada sin `response_format` y se parsea el JSON del texto.
        fallback = {key: value for key, value in kwargs.items() if key != "response_format"}
        try:
            return client.chat.completions.create(**fallback)
        except Exception as exc:
            raise map_provider_error(exc, provider=self.name, secrets=self._error_secrets) from exc

    def complete_json(self, system: str, user: str, schema: type[Any]) -> Any:
        """Pide una respuesta JSON, la valida y guarda el `usage` reportado."""
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "timeout": self.timeout,
        }
        if self._extra_headers:
            kwargs["extra_headers"] = self._extra_headers

        response = self._request(client, kwargs)

        choices = getattr(response, "choices", None) or []
        content = ""
        if choices:
            content = getattr(getattr(choices[0], "message", None), "content", "") or ""

        usage = getattr(response, "usage", None)
        self.last_usage = TokenUsage(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )
        return parse_json_payload(content, schema)
