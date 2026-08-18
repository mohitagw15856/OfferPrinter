"""Moonshot Kimi provider.

Moonshot exposes an OpenAI-compatible Chat Completions API, so this is a thin
subclass of OpenAIProvider with a different default base URL and model.
"""

from __future__ import annotations

from offerprinter.llm.openai_provider import OpenAIProvider


class KimiProvider(OpenAIProvider):
    """Calls Moonshot's OpenAI-compatible endpoint."""

    default_model = "moonshot-v1-8k"
    default_base_url = "https://api.moonshot.cn"
