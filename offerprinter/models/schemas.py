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
    OLLAMA = "ollama"


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
    max_retries: int = 3  # retries on 429 / 5xx / network blips
    retry_backoff: float = 1.5  # seconds; doubles each attempt


class OutputConfig(BaseModel):
    """Where and how results are written."""

    locale: Locale = Locale.UK
    dir: str = "./output"
    formats: list[str] = Field(default_factory=lambda: ["md", "docx"])
    #: Append each run to the local history in ~/.offerprinter/applications.json.
    track: bool = True


class GenerationConfig(BaseModel):
    """Which artifacts to produce, and how fast to produce them."""

    tailored_cv: bool = True
    cover_letter: bool = True
    fit_memo: bool = True
    ats_report: bool = True
    interview_prep: bool = True

    #: Score the application 0-100 and band it. One extra cheap call.
    fit_score: bool = True
    #: Generate all artifacts concurrently instead of one after another.
    parallel: bool = True
    #: Upper bound on concurrent LLM calls.
    max_workers: int = 5

    def enabled(self) -> list[str]:
        """Return the keys of the artifacts that are switched on, in order."""
        return [k for k in ARTIFACT_ORDER if getattr(self, k)]


#: Canonical artifact order — used for output ordering regardless of which
#: artifact finishes first when generating in parallel.
ARTIFACT_ORDER: list[str] = [
    "tailored_cv",
    "cover_letter",
    "fit_memo",
    "ats_report",
    "interview_prep",
]


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


class Usage(BaseModel):
    """Token counts and estimated spend for one run."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.calls += other.calls
        self.cost_usd += other.cost_usd


#: Score bands, highest threshold first. (min_score, label, one-line verdict)
FIT_BANDS: list[tuple[int, str, str]] = [
    (85, "Exceptional", "Apply today. You are what they wrote the advert for."),
    (70, "Strong", "A genuinely competitive application. Send it."),
    (55, "Credible", "Worth applying — lead hard with your strongest match."),
    (40, "Stretch", "A reach. Apply if you want it, and address the gaps head-on."),
    (0, "Long shot", "Big gaps. Consider a closer role, or close a gap first."),
]


class FitScore(BaseModel):
    """How well the candidate genuinely matches the role."""

    score: int = 0  # 0-100
    band: str = ""
    verdict: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @classmethod
    def band_for(cls, score: int) -> tuple[str, str]:
        """Return (band, verdict) for a 0-100 score."""
        for threshold, label, verdict in FIT_BANDS:
            if score >= threshold:
                return label, verdict
        return FIT_BANDS[-1][1], FIT_BANDS[-1][2]

    def as_markdown(self) -> str:
        filled = round(self.score / 10)
        bar = "█" * filled + "░" * (10 - filled)
        lines = [
            "# Fit Score",
            "",
            f"## {self.score}/100 — {self.band}",
            "",
            f"`{bar}`",
            "",
            f"*{self.verdict}*",
            "",
        ]
        if self.strengths:
            lines += ["## Where you genuinely match", ""]
            lines += [f"- {s}" for s in self.strengths] + [""]
        if self.gaps:
            lines += ["## Real gaps (not filled in for you)", ""]
            lines += [f"- {g}" for g in self.gaps] + [""]
        lines += [
            "> Scored from evidence actually present in your CV. Gaps are stated,",
            "> never papered over. — OfferPrinter",
            "",
        ]
        return "\n".join(lines)


class ApplicationPackage(BaseModel):
    """The full result of one run."""

    company: str
    role: str
    slug: str  # <company>-<role> folder name
    artifacts: list[Artifact] = Field(default_factory=list)
    fit: FitScore | None = None
    usage: Usage = Field(default_factory=Usage)

    def get(self, key: str) -> Artifact | None:
        return next((a for a in self.artifacts if a.key == key), None)

    def sort_artifacts(self) -> None:
        """Restore canonical order after parallel generation."""
        order = {key: i for i, key in enumerate(ARTIFACT_ORDER)}
        self.artifacts.sort(key=lambda a: order.get(a.key, len(order)))
