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
    JobDescription,
    ResumeInput,
)
from offerprinter.services.generator import Generator, _slugify
from offerprinter.services.writer import write_package


@dataclass
class PipelineEvent:
    """A progress update emitted while the pipeline runs."""

    kind: str  # "meta" | "artifact" | "written" | "done"
    message: str
    artifact: Artifact | None = None
    package: ApplicationPackage | None = None
    written: dict[str, list[Path]] | None = None


class Pipeline:
    """Runs the full generation flow for one (CV, JD) pair."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.provider = build_provider(config.llm)
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

        # 2. Generate each enabled artifact, streaming as we go.
        for artifact in self.generator.iter_generate(cv, jd, company, role):
            package.artifacts.append(artifact)
            yield PipelineEvent(kind="artifact", message=artifact.title, artifact=artifact)

        # 3. Write to disk.
        written = write_package(package, self.config.output.dir, self.config.output.formats)
        yield PipelineEvent(
            kind="written",
            message=str(Path(self.config.output.dir) / slug),
            package=package,
            written=written,
        )
        yield PipelineEvent(kind="done", message="Done", package=package, written=written)

    def run(self, cv: ResumeInput, jd: JobDescription) -> ApplicationPackage:
        """Convenience wrapper that runs the pipeline to completion."""
        package: ApplicationPackage | None = None
        for event in self.stream(cv, jd):
            if event.package is not None:
                package = event.package
        assert package is not None  # the "done" event always carries the package
        return package
