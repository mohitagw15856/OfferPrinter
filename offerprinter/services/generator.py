"""The generation service — turns (CV, JD) into the five artifacts.

This is the heart of the pipeline. It:
  1. extracts company + role (to name the output folder and the docs),
  2. generates each enabled artifact with a single, auditable prompt,
  3. yields results as they complete so the CLI/WebUI can stream progress.

It holds no I/O and no file-format logic — it only orchestrates prompts and the
LLM provider, which keeps it easy to read and test.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from offerprinter.llm.base import LLMProvider
from offerprinter.models.schemas import (
    Artifact,
    GenerationConfig,
    JobDescription,
    Locale,
    ResumeInput,
)
from offerprinter.prompts import (
    ATS_REPORT_PROMPT,
    COVER_LETTER_PROMPT,
    EXTRACT_META_PROMPT,
    FIT_MEMO_PROMPT,
    INTERVIEW_PREP_PROMPT,
    TAILORED_CV_PROMPT,
    build_system,
)

# key -> (human title, base filename, prompt template)
_ARTIFACT_SPECS: dict[str, tuple[str, str, str]] = {
    "tailored_cv": ("Tailored CV", "tailored-cv", TAILORED_CV_PROMPT),
    "cover_letter": ("Cover Letter", "cover-letter", COVER_LETTER_PROMPT),
    "fit_memo": ("Fit Memo", "fit-memo", FIT_MEMO_PROMPT),
    "ats_report": ("ATS Keyword Report", "ats-keyword-report", ATS_REPORT_PROMPT),
    "interview_prep": ("Interview Prep Pack", "interview-prep-pack", INTERVIEW_PREP_PROMPT),
}

_META_RE = re.compile(r"COMPANY:\s*(?P<company>.+?)\s*\|\s*ROLE:\s*(?P<role>.+?)\s*$")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def _strip_fences(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` fence if the model added one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped)
    return stripped.strip()


class Generator:
    """Orchestrates artifact generation for one (CV, JD) pair."""

    def __init__(
        self,
        provider: LLMProvider,
        locale: Locale = Locale.UK,
        generation: GenerationConfig | None = None,
    ) -> None:
        self.provider = provider
        self.locale = locale
        self.generation = generation or GenerationConfig()
        self.system = build_system(locale.value)

    # -- metadata -----------------------------------------------------------

    def extract_meta(self, jd: JobDescription) -> tuple[str, str]:
        """Return (company, role), best-effort, using a cheap single call."""
        raw = self.provider.complete(self.system, EXTRACT_META_PROMPT.format(jd=jd.text[:6000]))
        match = _META_RE.search(raw.strip().splitlines()[-1] if raw.strip() else "")
        if match:
            return match.group("company").strip(), match.group("role").strip()
        return "Company", "Role"

    # -- generation ---------------------------------------------------------

    def generate_one(
        self, key: str, cv: ResumeInput, jd: JobDescription, company: str, role: str
    ) -> Artifact:
        title, filename, template = _ARTIFACT_SPECS[key]
        user_prompt = template.format(cv=cv.text, jd=jd.text, company=company, role=role)
        content = _strip_fences(self.provider.complete(self.system, user_prompt))
        return Artifact(key=key, title=title, filename=filename, content=content)

    def iter_generate(
        self, cv: ResumeInput, jd: JobDescription, company: str, role: str
    ) -> Iterator[Artifact]:
        """Yield each enabled artifact as it is produced (for streaming UIs)."""
        for key in self.generation.enabled():
            yield self.generate_one(key, cv, jd, company, role)
