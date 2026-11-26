"""Gateway LLM: router, caché, proveedores y tipos compartidos."""

from winclip.llm.cache import LLMCache, LLMCacheEntry, compute_cache_key
from winclip.llm.router import LLMRouter, build_providers
from winclip.llm.types import (
    InvalidJSONResponseError,
    LLMError,
    LLMProvider,
    LLMResult,
    NoProviderAvailableError,
    ProviderAttempt,
    ProviderUnavailableError,
    RateLimitError,
    TokenUsage,
    map_provider_error,
    parse_json_payload,
)

__all__ = [
    "InvalidJSONResponseError",
    "LLMCache",
    "LLMCacheEntry",
    "LLMError",
    "LLMProvider",
    "LLMResult",
    "LLMRouter",
    "NoProviderAvailableError",
    "ProviderAttempt",
    "ProviderUnavailableError",
    "RateLimitError",
    "TokenUsage",
    "build_providers",
    "compute_cache_key",
    "map_provider_error",
    "parse_json_payload",
]
