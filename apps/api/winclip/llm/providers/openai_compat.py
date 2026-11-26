"""Base común de proveedores compatibles con la API OpenAI (`/chat/completions`)."""

from __future__ import annotations

from typing import Any

from winclip.core.config import Settings
from winclip.llm.types import (
    TokenUsage,
    map_provider_error,
    parse_json_payload,
)


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
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.last_usage: TokenUsage | None = None
        self._api_key = api_key.strip()
        self._client = client
        self._extra_headers = extra_headers or {}

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

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # el SDK expone tipos distintos por versión
            raise map_provider_error(exc, provider=self.name, secrets=[self._api_key]) from exc

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
