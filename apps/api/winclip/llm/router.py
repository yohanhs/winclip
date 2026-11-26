"""Router de proveedores LLM gratuitos con fallback, backoff y caché."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel

from winclip.core.config import Settings, get_settings
from winclip.core.storage import LocalStorage
from winclip.llm.cache import LLMCache, compute_cache_key
from winclip.llm.providers import (
    GeminiProvider,
    GroqProvider,
    NvidiaProvider,
    OllamaProvider,
    OpenRouterProvider,
)
from winclip.llm.types import (
    InvalidJSONResponseError,
    LLMError,
    LLMProvider,
    LLMResult,
    NoProviderAvailableError,
    ProviderAttempt,
    RateLimitError,
    estimate_tokens,
    scrub_secrets,
)

MAX_JSON_CORRECTIONS = 2
MIN_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0

_CORRECTION_TEMPLATE = (
    "\n\n[CORRECCIÓN OBLIGATORIA]\n"
    "Tu respuesta anterior no fue JSON válido según el esquema esperado. Error concreto: {error}\n"
    "Responde de nuevo EXCLUSIVAMENTE con un objeto JSON válido que cumpla el esquema. "
    "No añadas markdown, explicaciones ni texto fuera del JSON."
)


def build_providers(settings: Settings) -> dict[str, LLMProvider]:
    """Construye todos los proveedores; el router decide el orden y la disponibilidad."""
    return {
        "gemini": GeminiProvider(settings),
        "nvidia": NvidiaProvider(settings),
        "openrouter": OpenRouterProvider(settings),
        "groq": GroqProvider(settings),
        "ollama": OllamaProvider(settings),
    }


class LLMRouter:
    """Enruta cada solicitud por `LLM_PROVIDER_ORDER` con reintentos y caché."""

    def __init__(
        self,
        settings: Settings | None = None,
        providers: Mapping[str, LLMProvider] | Sequence[LLMProvider] | None = None,
        *,
        cache: LLMCache | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        jitter_fn: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._providers = self._index_providers(providers)
        self.cache = (
            cache if cache is not None else LLMCache(LocalStorage(self.settings.storage_dir))
        )
        self._sleep = sleep_fn
        self._jitter = jitter_fn if jitter_fn is not None else (lambda: random.uniform(0.0, 0.5))
        self._max_retries = max(0, self.settings.llm_max_retries_per_provider)

    def _index_providers(
        self,
        providers: Mapping[str, LLMProvider] | Sequence[LLMProvider] | None,
    ) -> dict[str, LLMProvider]:
        if providers is None:
            return build_providers(self.settings)
        if isinstance(providers, Mapping):
            return dict(providers)
        return {provider.name: provider for provider in providers}

    def provider_order(self) -> list[str]:
        """Orden configurado, seguido de proveedores inyectados no listados."""
        order = [name for name in self.settings.llm_providers if name in self._providers]
        order += [name for name in self._providers if name not in order]
        return order

    def complete_json[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        logical_model: str,
        use_cache: bool = True,
    ) -> LLMResult[T]:
        """Devuelve un resultado validado o lanza `NoProviderAvailableError`."""
        cache_key = compute_cache_key(
            logical_model=logical_model,
            system=system,
            user=user,
            schema=schema,
        )
        if use_cache:
            entry = self.cache.load(cache_key)
            if entry is not None:
                return LLMResult[T](
                    data=schema.model_validate(entry.data),
                    provider=entry.provider,
                    model=entry.model,
                    cached=True,
                    prompt_tokens=entry.prompt_tokens,
                    completion_tokens=entry.completion_tokens,
                    attempts=[],
                )

        attempts: list[ProviderAttempt] = []
        for provider_name in self.provider_order():
            provider = self._providers[provider_name]
            started = time.monotonic()
            model = getattr(provider, "model", "")
            if not provider.available():
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        model=model,
                        status="skipped",
                        error="sin credenciales o servicio no disponible",
                    )
                )
                continue

            outcome = self._try_provider(provider, system, user, schema)
            latency_ms = int((time.monotonic() - started) * 1000)
            if isinstance(outcome, LLMError):
                attempts.append(
                    ProviderAttempt(
                        provider=provider_name,
                        model=model,
                        status="error",
                        error=scrub_secrets(str(outcome), self._provider_secrets(provider)),
                        latency_ms=latency_ms,
                    )
                )
                continue

            data = outcome
            prompt_tokens, completion_tokens = self._token_usage(provider, system, user, data)
            if use_cache:
                self.cache.save(
                    cache_key=cache_key,
                    logical_model=logical_model,
                    provider=provider_name,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    data=data.model_dump(mode="json"),
                )
            attempts.append(
                ProviderAttempt(
                    provider=provider_name,
                    model=model,
                    status="ok",
                    latency_ms=latency_ms,
                )
            )
            return LLMResult[T](
                data=data,
                provider=provider_name,
                model=model,
                cached=False,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                attempts=attempts,
            )

        summary = "; ".join(
            f"{attempt.provider}: {attempt.error or attempt.status}" for attempt in attempts
        )
        raise NoProviderAvailableError(
            "ningún proveedor LLM logró una respuesta válida"
            + (f" ({summary})" if summary else " (no hay proveedores configurados)"),
            attempts=attempts,
        )

    def _try_provider[T: BaseModel](
        self,
        provider: LLMProvider,
        system: str,
        user: str,
        schema: type[T],
    ) -> T | LLMError:
        """Ejecuta un proveedor con reintentos transitorios y autocorrección JSON."""
        retries = 0
        corrections = 0
        prompt = user
        while True:
            try:
                return provider.complete_json(system, prompt, schema)
            except InvalidJSONResponseError as exc:
                if corrections >= MAX_JSON_CORRECTIONS:
                    return exc
                corrections += 1
                correction = _CORRECTION_TEMPLATE.format(error=str(exc))
                prompt = f"{user}{correction}"
            except RateLimitError as exc:
                if retries >= self._max_retries:
                    return exc
                self._sleep(self._backoff(retries))
                retries += 1
            except LLMError as exc:
                if exc.retryable and retries < self._max_retries:
                    self._sleep(self._backoff(retries))
                    retries += 1
                    continue
                return exc

    def _backoff(self, retry: int) -> float:
        """Espera exponencial acotada (`1, 2, 4…` hasta 8 s) más jitter inyectable."""
        return min(MIN_BACKOFF_SECONDS * 2**retry, MAX_BACKOFF_SECONDS) + self._jitter()

    @staticmethod
    def _provider_secrets(provider: LLMProvider) -> list[str]:
        secret = getattr(provider, "_api_key", "")
        return [secret] if isinstance(secret, str) else []

    @staticmethod
    def _token_usage(
        provider: LLMProvider, system: str, user: str, data: BaseModel
    ) -> tuple[int, int]:
        """Usa el `usage` del SDK o estima por longitud (sin añadir `tiktoken`)."""
        usage = getattr(provider, "last_usage", None)
        if usage is not None and (usage.prompt_tokens or usage.completion_tokens):
            return usage.prompt_tokens, usage.completion_tokens
        prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
        completion_tokens = estimate_tokens(data.model_dump_json())
        return prompt_tokens, completion_tokens
