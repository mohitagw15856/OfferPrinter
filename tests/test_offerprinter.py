"""Offline tests for OfferPrinter.

These do not touch the network: they exercise config resolution, input parsing,
the prompt guarantees, generation orchestration (with a stub provider), and the
Markdown-to-docx writer.
"""

from __future__ import annotations

import pytest

from offerprinter.config import load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.llm.base import LLMProvider
from offerprinter.llm.factory import build_provider
from offerprinter.models.schemas import (
    JobDescription,
    LLMConfig,
    Provider,
    ResumeInput,
)
from offerprinter.prompts import build_system
from offerprinter.services.cv_parser import CVParseError, cv_from_text
from offerprinter.services.generator import _slugify, _strip_fences
from offerprinter.services.jd_fetcher import jd_from_text, looks_like_url


class StubProvider(LLMProvider):
    """A deterministic provider so tests never hit the network."""

    default_model = "stub"

    def complete(self, system: str, user: str) -> str:
        if "COMPANY:" in user:
            return "COMPANY: Acme Analytics | ROLE: Data Analyst"
        return "# Title\n\nBody with **bold**.\n\n## Section\n- one\n- two\n"


def test_slugify():
    assert _slugify("Acme Analytics") == "acme-analytics"
    assert _slugify("Senior Data Analyst (Remote)") == "senior-data-analyst-remote"
    assert _slugify("") == "unknown"


def test_strip_fences():
    assert _strip_fences("```markdown\n# Hi\n```") == "# Hi"
    assert _strip_fences("# Hi") == "# Hi"


def test_url_detection():
    assert looks_like_url("https://example.com/job")
    assert looks_like_url("http://x.io")
    assert not looks_like_url("We are hiring a data analyst")


def test_cv_from_text_rejects_empty():
    with pytest.raises(CVParseError):
        cv_from_text("   ")


def test_config_env_precedence(monkeypatch):
    monkeypatch.setenv("OFFERPRINTER_PROVIDER", "openai")
    monkeypatch.setenv("OFFERPRINTER_API_KEY", "sk-test")
    monkeypatch.setenv("OFFERPRINTER_LOCALE", "US")
    cfg = load_config(config_path="does-not-exist.toml")
    assert cfg.llm.provider == Provider.OPENAI
    assert cfg.llm.api_key == "sk-test"
    assert cfg.output.locale.value == "US"


def test_provider_key_fallback(monkeypatch):
    # With no generic key, the provider-specific env var is used.
    monkeypatch.delenv("OFFERPRINTER_API_KEY", raising=False)
    monkeypatch.setenv("OFFERPRINTER_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    cfg = load_config(config_path="does-not-exist.toml")
    assert cfg.llm.api_key == "sk-anthropic"


def test_factory_returns_right_provider():
    p = build_provider(LLMConfig(provider=Provider.GEMINI, api_key="x"))
    assert p.name == "gemini"
    # Default model is filled in when config leaves it blank.
    assert p.model == "gemini-1.5-flash"


def test_system_prompt_carries_no_fabrication_rule():
    uk = build_system("UK")
    assert "NEVER fabricate" in uk
    assert "British" in uk
    us = build_system("US")
    assert "American" in us


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFERPRINTER_API_KEY", "sk-test")
    cfg = load_config(config_path="does-not-exist.toml")
    cfg.output.dir = str(tmp_path)

    pipeline = Pipeline.__new__(Pipeline)
    pipeline.config = cfg
    pipeline.provider = StubProvider(cfg.llm)
    from offerprinter.services.generator import Generator

    pipeline.generator = Generator(
        pipeline.provider, locale=cfg.output.locale, generation=cfg.generation
    )

    cv = ResumeInput(text="Jane Doe. Data analyst, 5 years, SQL and Python.")
    jd = JobDescription(text="Data Analyst at Acme Analytics. SQL, Python, dashboards.")
    package = pipeline.run(cv, jd)

    assert package.slug == "acme-analytics-data-analyst"
    assert len(package.artifacts) == 5
    folder = tmp_path / package.slug
    # Every artifact plus the combined file, in both formats.
    assert (folder / "tailored-cv.md").is_file()
    assert (folder / "tailored-cv.docx").is_file()
    assert (folder / "full-package.md").is_file()


def test_jd_from_text_roundtrip():
    jd = jd_from_text("Hiring a data analyst")
    assert jd.source == "pasted"
    assert "analyst" in jd.text
