"""The single interface every provider implements.

The whole rest of the app talks to LLMs through `LLMProvider.complete()`. Adding
a new provider means writing one subclass — nothing else in the codebase changes.

Two things are handled once, here, for every provider:

* **Retries** — a single 429 or a 503 should not kill a five-document run, so
  `_post` retries with exponential backoff and honours `Retry-After`.
* **Token accounting** — providers report usage in their responses; we
  accumulate it thread-safely so a run can report what it cost.
"""

from __future__ import annotations

import abc
import random
import threading
import time

import httpx

from offerprinter.models.schemas import LLMConfig, Usage
from offerprinter.pricing import estimate_cost

#: Status codes worth trying again — rate limits, overload, and gateway blips.
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Raised when a provider call fails (network, auth, or API error)."""


class LLMProvider(abc.ABC):
    """Abstract base class for a chat-completion provider."""

    #: The model used when the user leaves `model` blank in config.
    default_model: str = ""
    #: Set False for providers that run locally and need no credentials.
    requires_key: bool = True

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.model = config.model or self.default_model
        self.usage = Usage()
        self.price_overrides: dict[str, tuple[float, float]] = {}
        self._usage_lock = threading.Lock()

    @property
    def name(self) -> str:
        return type(self).__name__.replace("Provider", "").lower()

    @abc.abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the model's text completion for a system + user prompt."""
        raise NotImplementedError

    # -- shared helpers -----------------------------------------------------

    def _require_key(self) -> str:
        if not self.requires_key:
            return self.config.api_key or "not-required"
        if not self.config.api_key:
            raise LLMError(
                f"No API key found for provider '{self.name}'. Set it in config.toml "
                f"or via an environment variable (see config.example.toml)."
            )
        return self.config.api_key

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Accumulate token counts and estimated spend for this run."""
        cost = estimate_cost(self.model, input_tokens, output_tokens, self.price_overrides)
        with self._usage_lock:
            self.usage.input_tokens += input_tokens
            self.usage.output_tokens += output_tokens
            self.usage.calls += 1
            self.usage.cost_usd += cost

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        """Seconds to wait per the server's Retry-After header, if sane."""
        raw = resp.headers.get("retry-after")
        if not raw:
            return None
        try:
            wait = float(raw)
        except ValueError:
            return None
        return wait if 0 <= wait <= 60 else None

    def _post(self, url: str, headers: dict, json: dict) -> dict:
        """POST JSON and return the parsed response, retrying transient failures."""
        attempts = max(1, self.config.max_retries + 1)
        last_error: str = ""

        for attempt in range(attempts):
            resp: httpx.Response | None = None
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    resp = client.post(url, headers=headers, json=json)
            except httpx.HTTPError as exc:  # network-level failure
                last_error = f"Network error calling {self.name}: {exc}"
            else:
                if resp.status_code < 400:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise LLMError(f"{self.name} returned non-JSON response.") from exc

                last_error = f"{self.name} API returned {resp.status_code}: {resp.text[:500]}"
                if resp.status_code not in RETRYABLE_STATUS:
                    # Auth errors, bad requests: retrying cannot help.
                    raise LLMError(last_error)

            if attempt == attempts - 1:
                break

            server_hint = self._retry_after(resp) if resp is not None else None
            # Exponential backoff with jitter, so parallel artifacts don't all
            # come back and hammer the API on the same tick.
            backoff = self.config.retry_backoff * (2**attempt)
            delay = server_hint if server_hint is not None else backoff
            time.sleep(delay + random.uniform(0, 0.25))

        raise LLMError(f"{last_error} (gave up after {attempts} attempts)")
