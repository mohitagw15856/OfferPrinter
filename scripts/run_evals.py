#!/usr/bin/env python3
"""Run OfferPrinter's evaluation suite. See evals/README.md.

    python scripts/run_evals.py --offline          # deterministic, free
    python scripts/run_evals.py                    # live, needs an API key
    python scripts/run_evals.py --baseline evals/baseline.json

Exit codes: 0 pass, 1 a case failed, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from offerprinter.models.schemas import (  # noqa: E402
    ApplicationPackage,
    Artifact,
    JobDescription,
    ResumeInput,
)
from offerprinter.services.verifier import verify_package  # noqa: E402

CASES_DIR = REPO_ROOT / "evals" / "cases"

#: Filenames in a case's recorded/ folder, mapped to artifact keys.
RECORDED = {
    "tailored-cv.md": "tailored_cv",
    "cover-letter.md": "cover_letter",
    "fit-memo.md": "fit_memo",
    "ats-keyword-report.md": "ats_report",
}

JUDGE_DIMENSIONS = ("grounding", "specificity", "honesty", "usefulness", "format")


@dataclass
class CaseResult:
    """What one evaluation case produced."""

    name: str
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    fit_score: int | None = None
    unverified: int = 0

    @property
    def passed(self) -> bool:
        return not self.failures


def load_case(directory: Path) -> dict:
    case = {
        "name": directory.name,
        "cv": (directory / "cv.md").read_text(encoding="utf-8"),
        "jd": (directory / "jd.md").read_text(encoding="utf-8"),
        "expect": {},
        "recorded": {},
    }
    expect_path = directory / "expect.json"
    if expect_path.is_file():
        case["expect"] = json.loads(expect_path.read_text(encoding="utf-8"))

    recorded_dir = directory / "recorded"
    if recorded_dir.is_dir():
        for filename, key in RECORDED.items():
            path = recorded_dir / filename
            if path.is_file():
                case["recorded"][key] = path.read_text(encoding="utf-8")
    return case


def build_package(case: dict, artifacts: dict[str, str]) -> ApplicationPackage:
    return ApplicationPackage(
        company=case["expect"].get("company", ""),
        role=case["expect"].get("role", ""),
        slug=case["name"],
        artifacts=[
            Artifact(key=key, title=key, filename=key.replace("_", "-"), content=content)
            for key, content in artifacts.items()
        ],
    )


def check_deterministic(case: dict, artifacts: dict[str, str]) -> CaseResult:
    """The checks that need no model: fabrication, gaps, forbidden claims."""
    result = CaseResult(name=case["name"])
    expect = case["expect"]

    cv = ResumeInput(text=case["cv"])
    jd = JobDescription(text=case["jd"])
    package = build_package(case, artifacts)

    verification = verify_package(package, cv, jd)
    result.unverified = len(verification.findings)
    allowed = int(expect.get("allow_unverified", 0))
    if len(verification.findings) > allowed:
        for finding in verification.findings:
            result.failures.append(f"unverified {finding.kind}: {finding.claim!r}")

    # The tailored CV must not claim things the case says it must not.
    tailored = (artifacts.get("tailored_cv") or "").lower()
    for term in expect.get("must_not_claim", []):
        if re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", tailored):
            result.failures.append(f"tailored CV claims forbidden term: {term!r}")

    # Gaps the tool is required to be honest about.
    honesty_text = " ".join(artifacts.get(key, "") for key in ("fit_memo", "ats_report")).lower()
    for gap in expect.get("must_flag_gaps", []):
        if gap.lower() not in honesty_text:
            result.failures.append(f"never flagged the gap: {gap!r}")

    return result


def judge_artifacts(case: dict, artifacts: dict[str, str], pipeline) -> dict[str, float]:  # noqa: ANN001
    """LLM-as-judge scores, averaged across the graded artifacts."""
    from offerprinter.prompts import JUDGE_PROMPT

    totals: dict[str, list[int]] = {dim: [] for dim in JUDGE_DIMENSIONS}
    for key in ("tailored_cv", "cover_letter", "fit_memo"):
        content = artifacts.get(key)
        if not content:
            continue
        raw = pipeline.provider.complete(
            pipeline.generator.system,
            JUDGE_PROMPT.format(
                artifact_name=key.replace("_", " ").upper(),
                artifact=content,
                cv=case["cv"],
                jd=case["jd"],
            ),
        )
        for dim in JUDGE_DIMENSIONS:
            match = re.search(rf"{dim}:\s*([1-5])", raw, re.IGNORECASE)
            if match:
                totals[dim].append(int(match.group(1)))

    return {dim: round(sum(values) / len(values), 2) for dim, values in totals.items() if values}


def run_case(case: dict, offline: bool) -> CaseResult:
    if offline:
        if not case["recorded"]:
            result = CaseResult(name=case["name"])
            result.notes.append("skipped: no recorded/ output for offline mode")
            return result
        return check_deterministic(case, case["recorded"])

    from offerprinter.config import load_config
    from offerprinter.controllers.pipeline import Pipeline

    config = load_config()
    config.output.track = False
    config.output.dir = str(REPO_ROOT / "evals" / ".out")
    pipeline = Pipeline(config)

    package = pipeline.run(ResumeInput(text=case["cv"]), JobDescription(text=case["jd"]))
    artifacts = {a.key: a.content for a in package.artifacts}

    result = check_deterministic(case, artifacts)
    result.fit_score = package.fit.score if package.fit else None
    result.scores = judge_artifacts(case, artifacts, pipeline)

    expect = case["expect"]
    if result.fit_score is not None:
        if "min_fit" in expect and result.fit_score < expect["min_fit"]:
            result.failures.append(f"fit {result.fit_score} below min {expect['min_fit']}")
        if "max_fit" in expect and result.fit_score > expect["max_fit"]:
            result.failures.append(f"fit {result.fit_score} above max {expect['max_fit']}")

    for dim, floor in (expect.get("min_scores") or {}).items():
        actual = result.scores.get(dim)
        if actual is not None and actual < floor:
            result.failures.append(f"{dim} {actual} below floor {floor}")

    return result


def compare_baseline(results: list[CaseResult], baseline_path: Path, tolerance: float) -> list[str]:
    """Report any dimension that dropped more than `tolerance` below baseline."""
    if not baseline_path.is_file():
        return [f"baseline not found: {baseline_path}"]

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    regressions: list[str] = []
    for result in results:
        previous = baseline.get(result.name, {}).get("scores", {})
        for dim, before in previous.items():
            now = result.scores.get(dim)
            if now is not None and now < before - tolerance:
                regressions.append(f"{result.name}/{dim}: {before} → {now}")
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OfferPrinter eval suite.")
    parser.add_argument("--offline", action="store_true", help="Deterministic checks only.")
    parser.add_argument("--case", help="Run a single case by name.")
    parser.add_argument("--report", type=Path, help="Write a JSON report here.")
    parser.add_argument("--baseline", type=Path, help="Fail on regression against this baseline.")
    parser.add_argument("--tolerance", type=float, default=0.3, help="Allowed drop per dimension.")
    args = parser.parse_args()

    if not CASES_DIR.is_dir():
        print(f"No cases directory at {CASES_DIR}", file=sys.stderr)
        return 2

    directories = sorted(d for d in CASES_DIR.iterdir() if d.is_dir())
    if args.case:
        directories = [d for d in directories if d.name == args.case]
        if not directories:
            print(f"No such case: {args.case}", file=sys.stderr)
            return 2

    mode = "offline" if args.offline else "live"
    print(f"Running {len(directories)} case(s) — {mode} mode\n")

    results: list[CaseResult] = []
    for directory in directories:
        case = load_case(directory)
        result = run_case(case, offline=args.offline)
        results.append(result)

        if result.notes and not result.failures:
            print(f"  ~  {result.name}: {result.notes[0]}")
        elif result.passed:
            detail = f"unverified={result.unverified}"
            if result.fit_score is not None:
                detail += f" fit={result.fit_score}"
            if result.scores:
                detail += " " + " ".join(f"{k[:4]}={v}" for k, v in result.scores.items())
            print(f"  ✓  {result.name}  ({detail})")
        else:
            print(f"  ✗  {result.name}")
            for failure in result.failures:
                print(f"       {failure}")

    payload = {
        r.name: {
            "passed": r.passed,
            "failures": r.failures,
            "scores": r.scores,
            "fit_score": r.fit_score,
            "unverified": r.unverified,
        }
        for r in results
    }
    if args.report:
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nReport written to {args.report}")

    exit_code = 0
    failed = [r for r in results if not r.passed]
    if failed:
        print(f"\n{len(failed)} of {len(results)} cases failed.")
        exit_code = 1

    if args.baseline:
        regressions = compare_baseline(results, args.baseline, args.tolerance)
        if regressions:
            print("\nRegressions against baseline:")
            for line in regressions:
                print(f"  {line}")
            exit_code = 1

    if exit_code == 0:
        print(f"\nAll {len(results)} cases passed.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
