"""The end-to-end pipeline controller.

One entry point — `Pipeline.run(...)` — takes a CV and a job description and
produces (and optionally writes) the full application package. It emits progress
events so both the CLI and the Streamlit UI can show live status with the same
code path.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from offerprinter.config import Config
from offerprinter.llm import build_provider
from offerprinter.models.schemas import (
    ApplicationPackage,
    Artifact,
    FitScore,
    JobDescription,
    ResumeInput,
    Usage,
)
from offerprinter.services.generator import Generator, _slugify
from offerprinter.services.tracker import ApplicationRecord, Tracker, utc_now
from offerprinter.services.writer import write_package


@dataclass
class PipelineEvent:
    """A progress update emitted while the pipeline runs."""

    kind: str  # "meta" | "artifact" | "fit" | "written" | "done"
    message: str
    artifact: Artifact | None = None
    package: ApplicationPackage | None = None
    written: dict[str, list[Path]] | None = None
    fit: FitScore | None = None
    achievements: list[str] | None = None


class Pipeline:
    """Runs the full generation flow for one (CV, JD) pair."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.provider = build_provider(config.llm, config.pricing)
        self.generator = Generator(
            self.provider,
            locale=config.output.locale,
            generation=config.generation,
        )

    def stream(self, cv: ResumeInput, jd: JobDescription) -> Iterator[PipelineEvent]:
        """Run the pipeline, yielding a PipelineEvent at each step."""
        # 1. Identify company + role.
        company = jd.company or ""
        role = jd.role or ""
        if not (company and role):
            company, role = self.generator.extract_meta(jd)
        jd.company, jd.role = company, role
        slug = f"{_slugify(company)}-{_slugify(role)}"
        yield PipelineEvent(kind="meta", message=f"{role} at {company}")

        package = ApplicationPackage(company=company, role=role, slug=slug)

        # 2. Generate each enabled artifact, streaming as we go. In parallel
        #    mode these arrive in completion order, so we re-sort afterwards.
        for artifact in self.generator.iter_generate(cv, jd, company, role):
            package.artifacts.append(artifact)
            yield PipelineEvent(kind="artifact", message=artifact.title, artifact=artifact)
        package.sort_artifacts()

        # 3. Score the fit, if enabled.
        if self.config.generation.fit_score:
            fit = self.generator.score_fit(cv, jd, company, role)
            package.fit = fit
            yield PipelineEvent(kind="fit", message=f"{fit.score}/100 — {fit.band}", fit=fit)

        # 4. Account for what the run cost.
        package.usage = Usage(**self.provider.usage.model_dump())

        # 5. Write to disk.
        written = write_package(package, self.config.output.dir, self.config.output.formats)
        out_dir = Path(self.config.output.dir) / slug
        yield PipelineEvent(
            kind="written",
            message=str(out_dir),
            package=package,
            written=written,
        )

        # 6. Record it locally, so `offerprinter list` and `stats` can see it.
        achievements = self._track(package, out_dir)

        yield PipelineEvent(
            kind="done",
            message="Done",
            package=package,
            written=written,
            achievements=achievements,
        )

    def _track(self, package: ApplicationPackage, out_dir: Path) -> list[str]:
        """Append this run to the local history. Never fatal if it fails."""
        if not self.config.output.track:
            return []
        try:
            return Tracker().record(
                ApplicationRecord(
                    slug=package.slug,
                    company=package.company,
                    role=package.role,
                    printed_at=utc_now(),
                    provider=self.config.llm.provider.value,
                    model=self.provider.model,
                    fit_score=package.fit.score if package.fit else None,
                    fit_band=package.fit.band if package.fit else "",
                    cost_usd=package.usage.cost_usd,
                    total_tokens=package.usage.total_tokens,
                    output_dir=str(out_dir),
                )
            )
        except OSError:
            return []  # a read-only home directory should never fail a run

    def run(self, cv: ResumeInput, jd: JobDescription) -> ApplicationPackage:
        """Convenience wrapper that runs the pipeline to completion."""
        package: ApplicationPackage | None = None
        for event in self.stream(cv, jd):
            if event.package is not None:
                package = event.package
        assert package is not None  # the "done" event always carries the package
        return package
