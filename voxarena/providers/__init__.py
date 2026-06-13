"""Provider registry — single source of truth for which realtime LLM backends are supported.

To add a provider:
  1. Implement a ``BaseProviderAdapter`` subclass under ``voxarena/providers/<name>.py``.
  2. Add it to ``PROVIDERS`` and add its API-key env var name to ``API_KEY_ENV``.

Everything else (CLI flags, FastAPI routes, evaluator client selection, report grouping)
reads from these tables, so no other files need to change.
"""
from __future__ import annotations

from typing import Type

from voxarena.providers.base import BaseProviderAdapter
from voxarena.providers.gemini import GeminiProviderAdapter
from voxarena.providers.openai import OpenAIProviderAdapter


PROVIDERS: dict[str, Type[BaseProviderAdapter]] = {
    "gemini": GeminiProviderAdapter,
    "openai": OpenAIProviderAdapter,
}

# Env var that holds the API key for each provider.
API_KEY_ENV: dict[str, str] = {
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def provider_names() -> list[str]:
    """Sorted list of registered provider keys."""
    return sorted(PROVIDERS.keys())


def get_adapter_class(provider: str) -> Type[BaseProviderAdapter]:
    """Look up an adapter class by provider name, raising a clear error if unknown."""
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown provider '{provider}'. Registered providers: {provider_names()}"
        ) from None


def make_adapter(provider: str, agent, config, manifest, api_key: str) -> BaseProviderAdapter:
    """Factory: instantiate the right adapter for ``provider``."""
    return get_adapter_class(provider)(agent, config, manifest, api_key)


def api_key_env(provider: str) -> str:
    """Return the env var name that holds the API key for ``provider``."""
    try:
        return API_KEY_ENV[provider]
    except KeyError:
        raise ValueError(
            f"No API key env mapping for provider '{provider}'. Update voxarena/providers/__init__.py."
        ) from None


__all__ = [
    "PROVIDERS",
    "API_KEY_ENV",
    "BaseProviderAdapter",
    "GeminiProviderAdapter",
    "OpenAIProviderAdapter",
    "provider_names",
    "get_adapter_class",
    "make_adapter",
    "api_key_env",
]
