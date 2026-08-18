"""Ollama provider — run OfferPrinter entirely on your own machine.

Ollama exposes an OpenAI-compatible Chat Completions endpoint at
``http://localhost:11434/v1``, so this is a thin subclass of OpenAIProvider with
a local default base URL, a local default model, and no API key requirement.

With this provider your CV never leaves your laptop at all — not even to an LLM
vendor. Get started with:

    ollama pull llama3.1
    offerprinter --provider ollama --cv cv.pdf --jd-file jd.txt
"""

from __future__ import annotations

from offerprinter.llm.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Calls a local Ollama server through its OpenAI-compatible API."""

    default_model = "llama3.1"
    default_base_url = "http://localhost:11434"
    requires_key = False
