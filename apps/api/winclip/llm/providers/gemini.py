"""Proveedor Gemini (Google AI Studio) sobre el SDK oficial `google-genai`."""

from __future__ import annotations

from typing import Any

from winclip.core.config import Settings
from winclip.llm.types import TokenUsage, map_provider_error, parse_json_payload


class GeminiProvider:
    """Tier gratuito de Gemini con salida JSON forzada y `response_schema`."""

    name = "gemini"

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.model = settings.gemini_model
        self.timeout = settings.llm_timeout_seconds
        self.last_usage: TokenUsage | None = None
        self._api_key = settings.gemini_api_key.get_secret_value().strip()
        self._client = client
        self.last_config: Any | None = None

    def available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def complete_json(self, system: str, user: str, schema: type[Any]) -> Any:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        )
        self.last_config = config
        try:
            response = self._get_client().models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )
        except Exception as exc:
            raise map_provider_error(exc, provider=self.name, secrets=[self._api_key]) from exc

        usage = getattr(response, "usage_metadata", None)
        self.last_usage = TokenUsage(
            prompt_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            completion_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )
        return parse_json_payload(getattr(response, "text", "") or "", schema)
