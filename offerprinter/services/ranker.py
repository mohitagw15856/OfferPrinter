"""Score a pile of job adverts before writing a word for any of them.

Applying is expensive — an evening per role if you do it properly — and the
expensive part is deciding *which* roles deserve the evening. This runs only the
two cheap calls per job (identify the role, score the fit) and produces a ranked
table. Twenty adverts cost a couple of pence and about a minute, after which you
know which three to actually print packages for.

Deliberately generates no documents. That is the whole saving.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from offerprinter.models.schemas import RankedJob, ResumeInput
from offerprinter.services.generator import Generator
from offerprinter.services.jd_fetcher import JDFetchError, load_job_description

#: File types treated as job descriptions when scanning a folder.
JD_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


@dataclass
class RankProgress:
    """Emitted as each job finishes, so the CLI can show live progress."""

    done: int
    total: int
    result: RankedJob


def collect_jobs(
    paths: Iterable[Path] | None = None,
    directory: Path | None = None,
    urls: Iterable[str] | None = None,
) -> list[tuple[str, str]]:
    """Gather (source label, raw text-or-URL) pairs from every input given."""
    jobs: list[tuple[str, str]] = []

    if directory is not None:
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in JD_SUFFIXES:
                jobs.append((path.name, path.read_text(encoding="utf-8")))

    for path in paths or []:
        jobs.append((path.name, path.read_text(encoding="utf-8")))

    for url in urls or []:
        jobs.append((url, url))

    return jobs


class Ranker:
    """Scores many job descriptions against one CV, concurrently."""

    def __init__(self, generator: Generator, max_workers: int = 5, timeout: float = 30.0) -> None:
        self.generator = generator
        self.max_workers = max(1, max_workers)
        self.timeout = timeout

    def _score_one(self, source: str, raw: str) -> RankedJob:
        try:
            jd = load_job_description(raw, timeout=self.timeout)
        except JDFetchError as exc:
            return RankedJob(source=source, error=str(exc))

        try:
            company, role = self.generator.extract_meta(jd)
            fit = self.generator.score_fit(jd=jd, cv=self._cv, company=company, role=role)
        except Exception as exc:  # noqa: BLE001 - one bad advert must not kill the run
            return RankedJob(source=source, error=str(exc))

        return RankedJob(source=source, company=company, role=role, fit=fit)

    def rank(self, cv: ResumeInput, jobs: list[tuple[str, str]]) -> Iterator[RankProgress]:
        """Yield each job's score as it lands, then leave the caller to sort."""
        self._cv = cv
        workers = min(self.max_workers, max(1, len(jobs)))
        done = 0

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="op-rank") as pool:
            futures = {pool.submit(self._score_one, source, raw): source for source, raw in jobs}
            for future in as_completed(futures):
                done += 1
                yield RankProgress(done=done, total=len(jobs), result=future.result())


def sort_results(results: list[RankedJob]) -> list[RankedJob]:
    """Best fit first; anything that errored sinks to the bottom."""
    return sorted(results, key=lambda r: (r.error != "", -r.score, r.source))
