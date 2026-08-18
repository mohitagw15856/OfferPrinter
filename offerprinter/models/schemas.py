"""Data models for OfferPrinter.

These are deliberately thin, typed containers (pydantic) that carry data between
the layers — config → services → controller → output. Keeping them in one place
makes the flow easy to read and extend.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Provider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    KIMI = "kimi"


class Locale(StrEnum):
    """Output spelling/idiom."""

    UK = "UK"
    US = "US"


class LLMConfig(BaseModel):
    """Everything the LLM layer needs to make a call."""

    provider: Provider = Provider.ANTHROPIC
    model: str = ""  # "" means "use the provider default"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 120.0


class OutputConfig(BaseModel):
    """Where and how results are written."""

    locale: Locale = Locale.UK
    dir: str = "./output"
    formats: list[str] = Field(default_factory=lambda: ["md", "docx"])


class GenerationConfig(BaseModel):
    """Which artifacts to produce."""

    tailored_cv: bool = True
    cover_letter: bool = True
    fit_memo: bool = True
    ats_report: bool = True
    interview_prep: bool = True

    def enabled(self) -> list[str]:
        """Return the keys of the artifacts that are switched on, in order."""
        order = [
            "tailored_cv",
            "cover_letter",
            "fit_memo",
            "ats_report",
            "interview_prep",
        ]
        return [k for k in order if getattr(self, k)]


class ResumeInput(BaseModel):
    """The user's base CV, already extracted to plain text."""

    text: str
    source: str = "pasted"  # a filename or "pasted"


class JobDescription(BaseModel):
    """The target job, already extracted to plain text."""

    text: str
    source: str = "pasted"  # a URL or "pasted"
    company: str = ""  # best-effort; filled in by the pipeline
    role: str = ""  # best-effort; filled in by the pipeline


class Artifact(BaseModel):
    """One generated document."""

    key: str  # e.g. "tailored_cv"
    title: str  # human title, e.g. "Tailored CV"
    filename: str  # base filename without extension, e.g. "tailored-cv"
    content: str  # markdown body


class ApplicationPackage(BaseModel):
    """The full result of one run."""

    company: str
    role: str
    slug: str  # <company>-<role> folder name
    artifacts: list[Artifact] = Field(default_factory=list)

    def get(self, key: str) -> Artifact | None:
        return next((a for a in self.artifacts if a.key == key), None)
