"""OpenAI provider (also the base for any OpenAI-compatible endpoint)."""

from __future__ import annotations

from offerprinter.llm.base import LLMError, LLMProvider


class OpenAIProvider(LLMProvider):
    """Calls the OpenAI Chat Completions API."""

    default_model = "gpt-4o-mini"
    default_base_url = "https://api.openai.com"

    def complete(self, system: str, user: str) -> str:
        key = self._require_key()
        base = self.config.base_url or self.default_base_url
        url = f"{base.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = self._post(url, headers, payload)

        usage = data.get("usage") or {}
        self._record_usage(
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {data}") from exc
