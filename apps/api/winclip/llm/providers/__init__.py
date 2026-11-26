"""Proveedores NVIDIA NIM, OpenRouter, Groq y Ollama (API compatible con OpenAI)."""

from __future__ import annotations

from typing import Any

from winclip.core.config import Settings
from winclip.llm.providers.gemini import GeminiProvider
from winclip.llm.providers.openai_compat import OpenAICompatibleProvider

__all__ = [
    "GeminiProvider",
    "GroqProvider",
    "NvidiaProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
]


class NvidiaProvider(OpenAICompatibleProvider):
    """NVIDIA NIM (`https://integrate.api.nvidia.com/v1`)."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        super().__init__(
            settings,
            name="nvidia",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key.get_secret_value(),
            model=settings.nvidia_model,
            client=client,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter (`https://openrouter.ai/api/v1`), modelos `:free`."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        super().__init__(
            settings,
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key.get_secret_value(),
            model=settings.openrouter_model,
            client=client,
            # OpenRouter recomienda identificar la aplicación en las peticiones.
            extra_headers={"X-Title": settings.app_name},
        )


class GroqProvider(OpenAICompatibleProvider):
    """Groq (`https://api.groq.com/openai/v1`)."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        super().__init__(
            settings,
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key.get_secret_value(),
            model=settings.groq_model,
            client=client,
        )


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama local como último respaldo offline (`{OLLAMA_HOST}/v1`)."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        http_client: Any | None = None,
    ) -> None:
        host = settings.ollama_host.rstrip("/")
        super().__init__(
            settings,
            name="ollama",
            base_url=f"{host}/v1",
            api_key="ollama",
            model=settings.ollama_model,
            client=client,
            # "ollama" es una clave ficticia: no debe redactarse en los errores.
            error_secrets=[],
        )
        self._host = host
        self._http_client = http_client
        self._available: bool | None = None

    def available(self) -> bool:
        """Comprueba `GET /api/tags` (timeout 2 s) y cachea el resultado."""
        if self._available is None:
            self._available = self._probe_tags()
        return self._available

    def _probe_tags(self) -> bool:
        try:
            if self._http_client is None:
                import httpx

                response = httpx.get(f"{self._host}/api/tags", timeout=2.0)
            else:
                response = self._http_client.get(f"{self._host}/api/tags", timeout=2.0)
        except Exception:
            return False
        return int(getattr(response, "status_code", 500)) < 400
