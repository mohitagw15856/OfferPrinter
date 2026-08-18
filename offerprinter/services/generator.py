"""The generation service — turns (CV, JD) into the artifacts.

This is the heart of the pipeline. It:
  1. extracts company + role (to name the output folder and the docs),
  2. generates each enabled artifact with a single, auditable prompt,
  3. yields results as they complete so the CLI/WebUI can stream progress.

Artifacts are independent of one another, so by default they are generated
**concurrently** — a full package takes about as long as its slowest single
document rather than the sum of all five. Set `parallel = false` in the
`[generation]` config block to go back to one-at-a-time.

It holds no I/O and no file-format logic — it only orchestrates prompts and the
LLM provider, which keeps it easy to read and test.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from offerprinter.llm.base import LLMProvider
from offerprinter.models.schemas import (
    Artifact,
    FitScore,
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
    FIT_SCORE_PROMPT,
    INTERVIEW_PREP_PROMPT,
    ROAST_PROMPT,
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
_SCORE_RE = re.compile(r"SCORE:\s*(\d{1,3})", re.IGNORECASE)
_STRENGTHS_RE = re.compile(r"STRENGTHS:\s*(.+)", re.IGNORECASE)
_GAPS_RE = re.compile(r"GAPS:\s*(.+)", re.IGNORECASE)


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


def _split_list(raw: str) -> list[str]:
    """Split a 'a ; b ; c' line into a clean list, dropping 'none'."""
    items = [part.strip(" .-") for part in raw.split(";")]
    return [i for i in items if i and i.lower() not in {"none", "n/a", "-"}]


def parse_fit_score(raw: str) -> FitScore:
    """Parse the strict SCORE/STRENGTHS/GAPS block into a FitScore.

    Kept module-level and pure so it is trivial to test without a provider.
    """
    score_match = _SCORE_RE.search(raw)
    score = max(0, min(100, int(score_match.group(1)))) if score_match else 0
    band, verdict = FitScore.band_for(score)

    strengths_match = _STRENGTHS_RE.search(raw)
    gaps_match = _GAPS_RE.search(raw)
    return FitScore(
        score=score,
        band=band,
        verdict=verdict,
        strengths=_split_list(strengths_match.group(1)) if strengths_match else [],
        gaps=_split_list(gaps_match.group(1)) if gaps_match else [],
    )


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
        """Yield each enabled artifact as it is produced (for streaming UIs).

        In parallel mode artifacts arrive in completion order, not canonical
        order; `ApplicationPackage.sort_artifacts()` restores the order before
        anything is written to disk.
        """
        keys = self.generation.enabled()
        if not self.generation.parallel or len(keys) == 1:
            for key in keys:
                yield self.generate_one(key, cv, jd, company, role)
            return

        workers = max(1, min(self.generation.max_workers, len(keys)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="offerprinter") as pool:
            futures = {
                pool.submit(self.generate_one, key, cv, jd, company, role): key for key in keys
            }
            for future in as_completed(futures):
                yield future.result()

    # -- extras -------------------------------------------------------------

    def score_fit(self, cv: ResumeInput, jd: JobDescription, company: str, role: str) -> FitScore:
        """Score the match 0-100, strictly from evidence in the CV."""
        prompt = FIT_SCORE_PROMPT.format(cv=cv.text, jd=jd.text, company=company, role=role)
        return parse_fit_score(self.provider.complete(self.system, prompt))

    def roast(self, cv: ResumeInput) -> Artifact:
        """Blunt, funny, opt-in critique of the CV's writing."""
        content = _strip_fences(
            self.provider.complete(self.system, ROAST_PROMPT.format(cv=cv.text))
        )
        return Artifact(key="roast", title="CV Roast", filename="roast", content=content)
