"""Map a provider name in config to the concrete provider implementation."""

from __future__ import annotations

from offerprinter.llm.anthropic_provider import AnthropicProvider
from offerprinter.llm.base import LLMProvider
from offerprinter.llm.gemini_provider import GeminiProvider
from offerprinter.llm.kimi_provider import KimiProvider
from offerprinter.llm.ollama_provider import OllamaProvider
from offerprinter.llm.openai_provider import OpenAIProvider
from offerprinter.models.schemas import LLMConfig, Provider

_REGISTRY: dict[Provider, type[LLMProvider]] = {
    Provider.ANTHROPIC: AnthropicProvider,
    Provider.OPENAI: OpenAIProvider,
    Provider.GEMINI: GeminiProvider,
    Provider.KIMI: KimiProvider,
    Provider.OLLAMA: OllamaProvider,
}


def build_provider(
    config: LLMConfig,
    price_overrides: dict[str, tuple[float, float]] | None = None,
) -> LLMProvider:
    """Instantiate the provider named in `config`."""
    cls = _REGISTRY.get(config.provider)
    if cls is None:  # pragma: no cover - guarded by the Provider enum
        raise ValueError(f"Unknown provider: {config.provider}")
    provider = cls(config)
    if price_overrides:
        provider.price_overrides = price_overrides
    return provider
