"""The single interface every provider implements.

The whole rest of the app talks to LLMs through `LLMProvider.complete()`. Adding
a new provider means writing one subclass — nothing else in the codebase changes.
"""

from __future__ import annotations

import abc

import httpx

from offerprinter.models.schemas import LLMConfig


class LLMError(RuntimeError):
    """Raised when a provider call fails (network, auth, or API error)."""


class LLMProvider(abc.ABC):
    """Abstract base class for a chat-completion provider."""

    #: The model used when the user leaves `model` blank in config.
    default_model: str = ""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.model = config.model or self.default_model

    @property
    def name(self) -> str:
        return type(self).__name__.replace("Provider", "").lower()

    @abc.abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the model's text completion for a system + user prompt."""
        raise NotImplementedError

    # -- shared helpers -----------------------------------------------------

    def _require_key(self) -> str:
        if not self.config.api_key:
            raise LLMError(
                f"No API key found for provider '{self.name}'. Set it in config.toml "
                f"or via an environment variable (see config.example.toml)."
            )
        return self.config.api_key

    def _post(self, url: str, headers: dict, json: dict) -> dict:
        """POST JSON and return the parsed response, with friendly errors."""
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                resp = client.post(url, headers=headers, json=json)
        except httpx.HTTPError as exc:  # network-level failure
            raise LLMError(f"Network error calling {self.name}: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"{self.name} API returned {resp.status_code}: {resp.text[:500]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise LLMError(f"{self.name} returned non-JSON response.") from exc
