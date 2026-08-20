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
    #: Strip name, email, phone and links before the provider ever sees the CV.
    redact: bool = False


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
    #: Check every claim in the output against the source CV.
    verify: bool = True
    #: Record what tailoring changed, so it can be audited quickly.
    diff: bool = True
    #: Reuse identical previous responses instead of paying for them again.
    cache: bool = True

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


class Severity(StrEnum):
    """How seriously to take an unverified claim."""

    HIGH = "high"  # a number, date or metric with no source in the CV
    MEDIUM = "medium"  # a proper noun (employer, tool, place) with no source
    LOW = "low"  # plausible but worth a glance


#: How each kind of finding is explained to a human.
FINDING_REASONS = {
    "number": "this figure does not appear in your CV",
    "date": "this date does not appear in your CV",
    "entity": "no mention of this in your CV",
    "ats-gap": "your own ATS report lists this as a gap",
}


class Finding(BaseModel):
    """One claim in generated output that could not be traced to the CV."""

    artifact: str  # which document it appeared in
    claim: str  # the exact token or phrase
    kind: str  # a key of FINDING_REASONS
    severity: Severity
    context: str = ""  # the surrounding line, for eyeballing

    @property
    def reason(self) -> str:
        return FINDING_REASONS.get(self.kind, self.kind)

    def as_line(self) -> str:
        where = f"{self.artifact} · " if self.artifact else ""
        return f"[{self.severity.value}] {where}{self.claim!r} — {self.reason}"


class Verification(BaseModel):
    """The result of checking generated output against the source CV.

    This is what turns the no-fabrication guarantee from a prompt instruction
    into something the tool actually proves.
    """

    findings: list[Finding] = Field(default_factory=list)
    checked_artifacts: list[str] = Field(default_factory=list)
    claims_checked: int = 0

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.HIGH]

    def summary(self) -> str:
        if self.passed:
            return f"All {self.claims_checked} checkable claims trace back to your CV."
        return (
            f"{len(self.findings)} of {self.claims_checked} claims could not be traced "
            f"to your CV ({len(self.high)} high severity)."
        )

    def as_markdown(self) -> str:
        lines = ["# Fabrication Check", ""]
        lines += [self.summary(), ""]
        if self.passed:
            lines += [
                "Every employer, job title, date, number and named tool in the",
                "generated documents appears in your source CV. Nothing was invented.",
                "",
            ]
        else:
            lines += [
                "The claims below appear in the generated documents but could not be",
                "matched to anything in your CV. Review each one before sending —",
                "either it is a paraphrase the checker could not match, or it should go.",
                "",
            ]
            for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
                group = [f for f in self.findings if f.severity is severity]
                if not group:
                    continue
                lines += [f"## {severity.value.title()} severity", ""]
                for finding in group:
                    lines.append(
                        f"- **{finding.claim}** — {finding.reason} (in {finding.artifact})"
                    )
                    if finding.context:
                        lines.append(f"  > {finding.context}")
                lines.append("")
        lines += [
            "> Checked automatically by OfferPrinter. A checker can only verify what it",
            "> can match textually; you are still the final reviewer.",
            "",
        ]
        return "\n".join(lines)


class RankedJob(BaseModel):
    """One job description scored during a `rank` run."""

    source: str  # filename or URL
    company: str = ""
    role: str = ""
    fit: FitScore | None = None
    error: str = ""

    @property
    def score(self) -> int:
        return self.fit.score if self.fit else -1


class ApplicationPackage(BaseModel):
    """The full result of one run."""

    company: str
    role: str
    slug: str  # <company>-<role> folder name
    artifacts: list[Artifact] = Field(default_factory=list)
    fit: FitScore | None = None
    usage: Usage = Field(default_factory=Usage)
    verification: Verification | None = None
    diff: str = ""  # markdown report of what tailoring changed

    def get(self, key: str) -> Artifact | None:
        return next((a for a in self.artifacts if a.key == key), None)

    def sort_artifacts(self) -> None:
        """Restore canonical order after parallel generation."""
        order = {key: i for i, key in enumerate(ARTIFACT_ORDER)}
        self.artifacts.sort(key=lambda a: order.get(a.key, len(order)))
