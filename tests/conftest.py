"""Shared test fixtures.

The most important thing here is the autouse fixture that redirects the
application tracker into a temporary directory. Without it, running the test
suite would append rows to the developer's real
``~/.offerprinter/applications.json``.
"""

from __future__ import annotations

import pytest

from offerprinter.llm.base import LLMProvider


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test's tracker writes inside tmp_path."""
    monkeypatch.setenv("OFFERPRINTER_HOME", str(tmp_path / "offerprinter-home"))
    return tmp_path


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    """Stop a developer's real environment from leaking into config tests."""
    for name in (
        "OFFERPRINTER_PROVIDER",
        "OFFERPRINTER_MODEL",
        "OFFERPRINTER_API_KEY",
        "OFFERPRINTER_BASE_URL",
        "OFFERPRINTER_LOCALE",
        "OFFERPRINTER_OUTPUT_DIR",
        "OFFERPRINTER_FORMATS",
        "OFFERPRINTER_TRACK",
        "OFFERPRINTER_PARALLEL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


class StubProvider(LLMProvider):
    """A deterministic provider so tests never hit the network."""

    default_model = "stub"
    requires_key = False

    #: Set to a number to make every call sleep, for concurrency tests.
    delay: float = 0.0

    def complete(self, system: str, user: str) -> str:
        if self.delay:
            import time

            time.sleep(self.delay)
        self._record_usage(100, 50)
        if "COMPANY:" in user:
            return "COMPANY: Acme Analytics | ROLE: Data Analyst"
        if "SCORE:" in user:
            return "SCORE: 72\nSTRENGTHS: SQL depth ; A/B testing ; stakeholder work\nGAPS: dbt ; fintech domain"
        if "Roast this CV" in user:
            return "# 🔥 CV Roast\n\n## The verdict in one line\nIt's fine. That's the problem."
        return "# Title\n\nBody with **bold**.\n\n## Section\n- one\n- two\n"


@pytest.fixture
def stub_provider_cls():
    return StubProvider
