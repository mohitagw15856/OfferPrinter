"""Offline tests for OfferPrinter.

These do not touch the network: they exercise config resolution, input parsing,
the prompt guarantees, generation orchestration (with a stub provider), and the
Markdown-to-docx writer.
"""

from __future__ import annotations

import pytest

from offerprinter.config import load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.llm.factory import build_provider
from offerprinter.models.schemas import (
    ARTIFACT_ORDER,
    FitScore,
    JobDescription,
    LLMConfig,
    Provider,
    ResumeInput,
)
from offerprinter.prompts import build_system
from offerprinter.services.cv_parser import CVParseError, cv_from_text
from offerprinter.services.generator import (
    Generator,
    _slugify,
    _strip_fences,
    parse_fit_score,
)
from offerprinter.services.jd_fetcher import jd_from_text, looks_like_url
from tests.conftest import StubProvider


def _pipeline_with_stub(cfg) -> Pipeline:
    """Build a Pipeline wired to the stub provider, skipping the factory."""
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.config = cfg
    pipeline.provider = StubProvider(cfg.llm)
    pipeline.generator = Generator(
        pipeline.provider, locale=cfg.output.locale, generation=cfg.generation
    )
    return pipeline


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
    monkeypatch.setenv("OFFERPRINTER_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    cfg = load_config(config_path="does-not-exist.toml")
    assert cfg.llm.api_key == "sk-anthropic"


def test_factory_returns_right_provider():
    p = build_provider(LLMConfig(provider=Provider.GEMINI, api_key="x"))
    assert p.name == "gemini"
    # Default model is filled in when config leaves it blank.
    assert p.model == "gemini-1.5-flash"


def test_ollama_provider_needs_no_key():
    p = build_provider(LLMConfig(provider=Provider.OLLAMA))
    assert p.requires_key is False
    assert p.model == "llama3.1"
    assert p.default_base_url.startswith("http://localhost")
    # _require_key must not raise for a keyless provider.
    assert p._require_key()


def test_system_prompt_carries_no_fabrication_rule():
    uk = build_system("UK")
    assert "NEVER fabricate" in uk
    assert "British" in uk
    us = build_system("US")
    assert "American" in us


def test_every_prompt_repeats_the_no_fabrication_rule():
    """The guarantee is the product; it must be in every generation prompt."""
    from offerprinter.prompts import (
        ATS_REPORT_PROMPT,
        COVER_LETTER_PROMPT,
        FIT_MEMO_PROMPT,
        FIT_SCORE_PROMPT,
        INTERVIEW_PREP_PROMPT,
        TAILORED_CV_PROMPT,
    )

    honest_words = ("real", "REAL", "honest", "Gap", "gap", "evidence", "truthful")
    for prompt in (
        TAILORED_CV_PROMPT,
        COVER_LETTER_PROMPT,
        FIT_MEMO_PROMPT,
        ATS_REPORT_PROMPT,
        INTERVIEW_PREP_PROMPT,
        FIT_SCORE_PROMPT,
    ):
        assert any(word in prompt for word in honest_words)


@pytest.mark.parametrize("parallel", [False, True])
def test_pipeline_end_to_end(tmp_path, parallel):
    cfg = load_config(config_path="does-not-exist.toml")
    cfg.output.dir = str(tmp_path)
    cfg.output.formats = ["md", "docx", "pdf"]
    cfg.generation.parallel = parallel

    package = _pipeline_with_stub(cfg).run(
        ResumeInput(text="Jane Doe. Data analyst, 5 years, SQL and Python."),
        JobDescription(text="Data Analyst at Acme Analytics. SQL, Python, dashboards."),
    )

    assert package.slug == "acme-analytics-data-analyst"
    assert len(package.artifacts) == 5
    # Parallel generation must not disturb the canonical document order.
    assert [a.key for a in package.artifacts] == ARTIFACT_ORDER

    folder = tmp_path / package.slug
    for name in ("tailored-cv", "full-package", "fit-score"):
        for ext in ("md", "docx", "pdf"):
            assert (folder / f"{name}.{ext}").is_file(), f"{name}.{ext} missing"


def test_pipeline_records_usage_and_fit(tmp_path):
    cfg = load_config(config_path="does-not-exist.toml")
    cfg.output.dir = str(tmp_path)
    package = _pipeline_with_stub(cfg).run(
        ResumeInput(text="Jane Doe, analyst."),
        JobDescription(text="Data Analyst at Acme Analytics."),
    )

    # 1 meta call + 5 artifacts + 1 fit score.
    assert package.usage.calls == 7
    assert package.usage.input_tokens == 700
    assert package.usage.output_tokens == 350
    assert package.fit is not None
    assert package.fit.score == 72
    assert package.fit.band == "Strong"
    assert "dbt" in package.fit.gaps


def test_generation_can_be_switched_off(tmp_path):
    cfg = load_config(config_path="does-not-exist.toml")
    cfg.output.dir = str(tmp_path)
    cfg.generation.cover_letter = False
    cfg.generation.interview_prep = False
    cfg.generation.fit_score = False

    package = _pipeline_with_stub(cfg).run(
        ResumeInput(text="Jane Doe, analyst."),
        JobDescription(text="Data Analyst at Acme Analytics."),
    )
    assert [a.key for a in package.artifacts] == ["tailored_cv", "fit_memo", "ats_report"]
    assert package.fit is None
    assert not (tmp_path / package.slug / "fit-score.md").exists()


def test_jd_from_text_roundtrip():
    jd = jd_from_text("Hiring a data analyst")
    assert jd.source == "pasted"
    assert "analyst" in jd.text


# --- fit score ---------------------------------------------------------------


def test_parse_fit_score():
    fit = parse_fit_score("SCORE: 78\nSTRENGTHS: SQL ; dashboards ; mentoring\nGAPS: dbt ; fintech")
    assert fit.score == 78
    assert fit.band == "Strong"
    assert fit.strengths == ["SQL", "dashboards", "mentoring"]
    assert fit.gaps == ["dbt", "fintech"]


def test_parse_fit_score_handles_no_gaps_and_junk():
    fit = parse_fit_score("SCORE: 91\nSTRENGTHS: everything\nGAPS: none")
    assert fit.score == 91
    assert fit.band == "Exceptional"
    assert fit.gaps == []

    # A model that ignores the format entirely must not crash the run.
    assert parse_fit_score("I think they're a great fit!").score == 0


def test_fit_score_is_clamped():
    assert parse_fit_score("SCORE: 240").score == 100


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (100, "Exceptional"),
        (85, "Exceptional"),
        (70, "Strong"),
        (55, "Credible"),
        (40, "Stretch"),
        (0, "Long shot"),
    ],
)
def test_fit_bands(score, band):
    assert FitScore.band_for(score)[0] == band


def test_fit_score_markdown_shows_gaps():
    fit = FitScore(score=60, band="Credible", verdict="Worth applying.", gaps=["dbt"])
    markdown = fit.as_markdown()
    assert "60/100" in markdown
    assert "dbt" in markdown
    assert "Real gaps" in markdown


# --- roast -------------------------------------------------------------------


def test_roast_produces_an_artifact():
    generator = Generator(StubProvider(LLMConfig(provider=Provider.ANTHROPIC)))
    artifact = generator.roast(ResumeInput(text="Responsible for various duties."))
    assert artifact.key == "roast"
    assert artifact.filename == "roast"
    assert "Roast" in artifact.content


def test_roast_prompt_protects_the_person():
    from offerprinter.prompts import ROAST_PROMPT

    assert "never the person" in ROAST_PROMPT
    assert "Do not invent flaws" in ROAST_PROMPT
