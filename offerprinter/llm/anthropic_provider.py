"""Anthropic (Claude) provider — the default."""

from __future__ import annotations

from offerprinter.llm.base import LLMError, LLMProvider


class AnthropicProvider(LLMProvider):
    """Calls the Anthropic Messages API (https://api.anthropic.com/v1/messages)."""

    default_model = "claude-haiku-4-5-20251001"

    def complete(self, system: str, user: str) -> str:
        key = self._require_key()
        base = self.config.base_url or "https://api.anthropic.com"
        url = f"{base.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = self._post(url, headers, payload)
        try:
            blocks = data["content"]
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Anthropic response shape: {data}") from exc
