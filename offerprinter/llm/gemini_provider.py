"""Google Gemini provider."""

from __future__ import annotations

from offerprinter.llm.base import LLMError, LLMProvider


class GeminiProvider(LLMProvider):
    """Calls the Gemini generateContent API."""

    default_model = "gemini-1.5-flash"

    def complete(self, system: str, user: str) -> str:
        key = self._require_key()
        base = self.config.base_url or "https://generativelanguage.googleapis.com"
        url = f"{base.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            },
        }
        data = self._post(url, headers, payload)

        usage = data.get("usageMetadata") or {}
        self._record_usage(
            int(usage.get("promptTokenCount", 0)),
            int(usage.get("candidatesTokenCount", 0)),
        )

        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc
