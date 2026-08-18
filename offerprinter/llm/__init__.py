"""Provider-agnostic LLM layer.

A single interface — `LLMProvider.complete(system, user)` — with concrete
implementations for Anthropic, OpenAI, Gemini and Moonshot Kimi. Use
`build_provider(llm_config)` to get the right one from config.
"""

from offerprinter.llm.base import LLMError, LLMProvider
from offerprinter.llm.factory import build_provider

__all__ = ["LLMProvider", "LLMError", "build_provider"]
