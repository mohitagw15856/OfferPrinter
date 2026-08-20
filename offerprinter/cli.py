#!/usr/bin/env python3
"""OfferPrinter command-line interface.

Examples
--------
Print a package from a CV file and a job URL:

    offerprinter --cv path/to/cv.pdf --jd "https://careers.example.com/123"

From a CV file and a job description saved in a file:

    offerprinter --cv cv.docx --jd-file jd.txt

Print packages for a whole folder of job descriptions in one go:

    offerprinter --cv cv.pdf --jd-dir ./jobs

Other things it does:

    offerprinter roast --cv cv.pdf     # blunt, funny critique of your CV
    offerprinter list                  # every application you've printed
    offerprinter stats                 # totals, spend, achievements
    offerprinter status acme-analyst interview

Run `offerprinter --help` for the full list of options.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from offerprinter import __version__
from offerprinter.config import Config, load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.models.schemas import (
    ApplicationPackage,
    Artifact,
    JobDescription,
    Locale,
    Provider,
    ResumeInput,
)
from offerprinter.pricing import estimate_cost, format_cost
from offerprinter.prompts import FOLLOWUP_PROMPTS
from offerprinter.services.cache import ResponseCache
from offerprinter.services.cv_parser import cv_from_text, extract_cv
from offerprinter.services.generator import _slugify
from offerprinter.services.jd_fetcher import jd_from_clipboard, load_job_description
from offerprinter.services.ranker import Ranker, collect_jobs, sort_results
from offerprinter.services.tracker import (
    STATUSES,
    Tracker,
    describe,
    summarise,
)
from offerprinter.services.verifier import verify_package
from offerprinter.ui.printer import PrinterAnimation, render_fit_bar

app = typer.Typer(
    add_completion=False,
    help="Paste one job description and your CV; print a full, tailored, "
    "no-fabrication application package.",
    rich_markup_mode="rich",
)
console = Console()

#: Job-description file types picked up by --jd-dir.
_JD_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


def _version_cb(value: bool) -> None:
    if value:
        console.print(f"OfferPrinter {__version__}")
        raise typer.Exit()


def _load_cv(cv: Path | None, cv_text: str | None) -> ResumeInput:
    try:
        return cv_from_text(cv_text) if cv_text else extract_cv(cv)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not read CV:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _require_key(config: Config) -> None:
    from offerprinter.llm.factory import _REGISTRY

    if not _REGISTRY[config.llm.provider].requires_key:
        return
    if config.llm.api_key:
        return
    console.print(
        Panel.fit(
            f"No API key for provider [bold]{config.llm.provider.value}[/bold].\n"
            "Set it in config.toml or via an environment variable "
            "(see config.example.toml).\n\n"
            "No key at all? Run it fully locally instead:\n"
            "  [cyan]ollama pull llama3.1 && offerprinter --provider ollama …[/cyan]",
            title="Missing API key",
            border_style="red",
        )
    )
    raise typer.Exit(code=2)


def _apply_overrides(
    config: Config,
    provider: Provider | None,
    model: str | None,
    locale: Locale | None,
    output_dir: Path | None,
    formats: str | None,
    no_track: bool,
    sequential: bool,
    redact: bool = False,
    no_verify: bool = False,
    no_cache: bool = False,
) -> None:
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""  # let the new provider pick its default
    if model:
        config.llm.model = model
    if locale:
        config.output.locale = locale
    if output_dir:
        config.output.dir = str(output_dir)
    if formats:
        config.output.formats = [
            f.strip().lower().lstrip(".") for f in formats.split(",") if f.strip()
        ]
    if no_track:
        config.output.track = False
    if sequential:
        config.generation.parallel = False
    if redact:
        config.output.redact = True
    if no_verify:
        config.generation.verify = False
    if no_cache:
        config.generation.cache = False


def _cost_line(config: Config, package) -> str:  # noqa: ANN001 - local formatting helper
    usage = package.usage
    if not usage.calls:
        return ""
    return (
        f"{usage.calls} calls · {usage.total_tokens:,} tokens "
        f"({usage.input_tokens:,} in / {usage.output_tokens:,} out) · "
        f"{format_cost(usage.cost_usd)}"
    )


def _print_summary(config: Config, package, out_folder: Path, achievements: list[str]) -> None:  # noqa: ANN001
    if package.fit:
        fit = package.fit
        header = Text()
        header.append(f"{fit.score}/100  ", style="bold")
        header.append(render_fit_bar(fit.score))
        header.append(f"  {fit.band}", style="bold")
        console.print()
        console.print(Panel(header, title="🎯 Fit score", border_style="cyan", expand=False))
        console.print(f"   [italic]{fit.verdict}[/italic]")
        if fit.gaps:
            console.print(f"   [yellow]Real gaps:[/yellow] {', '.join(fit.gaps)}")

    verification = package.verification
    if verification is not None:
        if verification.passed:
            console.print(f"   [green]✓ Fabrication check:[/green] {verification.summary()}")
        else:
            console.print(f"   [yellow]⚠ Fabrication check:[/yellow] {verification.summary()}")
            for finding in verification.findings[:6]:
                colour = "red" if finding.severity.value == "high" else "yellow"
                console.print(f"     [{colour}]•[/{colour}] {finding.claim!r} — {finding.reason}")
            if len(verification.findings) > 6:
                console.print(f"     [grey62]…and {len(verification.findings) - 6} more[/grey62]")

    lines = [f"Package written to [bold]{out_folder}[/bold]"]
    cost = _cost_line(config, package)
    if cost:
        lines.append(f"[grey62]{cost}[/grey62]")
    lines.append("Every line is drawn from your real CV — review before sending.")
    console.print(Panel.fit("\n".join(lines), title="✅ Done", border_style="green"))

    for achievement in achievements:
        console.print(f"[magenta]Achievement unlocked:[/magenta] {describe(achievement)}")


#: The most recent run's fabrication check, for `--strict` to act on.
_last_verification = None


def _run_one(config: Config, resume: ResumeInput, jd_value: str, animate: bool) -> bool:
    """Print one package. Returns True on success."""
    global _last_verification
    _last_verification = None
    try:
        job = load_job_description(jd_value, timeout=config.llm.timeout)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not load job description:[/red] {exc}")
        return False

    pipeline = Pipeline(config)
    written: dict | None = None
    package = None
    achievements: list[str] = []
    total = len(config.generation.enabled())

    try:
        with PrinterAnimation(console, total=total, enabled=animate) as anim:
            anim.status("reading JD")
            for event in pipeline.stream(resume, job):
                if event.kind == "meta":
                    anim.status("targeting")
                    console.print(f"🎯 Target role: [bold]{event.message}[/bold]")
                elif event.kind == "artifact":
                    anim.sheet(event.message)
                elif event.kind == "fit":
                    anim.status("scoring")
                elif event.kind == "written":
                    written = event.written
                    package = event.package
                elif event.kind == "verified":
                    anim.status("checking")
                    _last_verification = event.verification
                elif event.kind == "done":
                    achievements = event.achievements or []
                    package = event.package
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Generation failed:[/red] {exc}")
        return False

    out_folder = Path(config.output.dir) / _slug_from(written)
    _print_summary(config, package, out_folder, achievements)
    return True


def _slug_from(written: dict | None) -> str:
    """Best-effort recover the output folder name from written paths."""
    if written:
        for paths in written.values():
            if paths:
                return paths[0].parent.name
    return ""


def _dry_run(config: Config, resume: ResumeInput, jd_value: str) -> None:
    """Estimate tokens and cost without calling the API once."""
    from offerprinter.llm.factory import _REGISTRY
    from offerprinter.services.jd_fetcher import jd_from_text

    job = jd_from_text(jd_value) if not jd_value.startswith("http") else None
    jd_chars = len(job.text) if job else 4000  # unfetched URL: assume a typical JD
    model = config.llm.model or _REGISTRY[config.llm.provider].default_model

    # ~4 characters per token is the standard rough rule for English prose.
    per_call_in = (len(resume.text) + jd_chars) // 4 + 400  # + the prompt itself
    calls = len(config.generation.enabled()) + 1 + (1 if config.generation.fit_score else 0)
    est_in = per_call_in * calls
    est_out = 900 * calls  # each artifact is roughly a page

    cost = estimate_cost(model, est_in, est_out, config.pricing)
    console.print(
        Panel.fit(
            f"Model: [bold]{model}[/bold]\n"
            f"Calls: [bold]{calls}[/bold]\n"
            f"Estimated tokens: ~{est_in + est_out:,} "
            f"({est_in:,} in / {est_out:,} out)\n"
            f"Estimated cost: [bold]{format_cost(cost)}[/bold]\n\n"
            "[grey62]A rough forecast, not a quote. Nothing was sent anywhere.[/grey62]",
            title="🔍 Dry run",
            border_style="yellow",
        )
    )


# ---------------------------------------------------------------------------
# The default command: print a package.
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def run(
    ctx: typer.Context,
    cv: Path | None = typer.Option(
        None,
        "--cv",
        help="Path to your CV/resume (.pdf, .docx, .md, or .txt).",
        exists=False,
    ),
    cv_text: str | None = typer.Option(
        None, "--cv-text", help="Paste your CV as raw text instead of a file."
    ),
    jd: str | None = typer.Option(
        None,
        "--jd",
        help="Job description as a URL (fetched + extracted) or pasted text.",
    ),
    jd_file: Path | None = typer.Option(
        None, "--jd-file", help="Path to a file containing the job description text."
    ),
    jd_dir: Path | None = typer.Option(
        None,
        "--jd-dir",
        help="Batch mode: a folder of .txt/.md job descriptions, one package each.",
    ),
    jd_clipboard: bool = typer.Option(
        False,
        "--jd-clipboard",
        help="Read the job description from your clipboard. Best for JavaScript job boards.",
    ),
    provider: Provider | None = typer.Option(
        None, "--provider", help="Override the LLM provider for this run.", case_sensitive=False
    ),
    model: str | None = typer.Option(None, "--model", help="Override the model name for this run."),
    locale: Locale | None = typer.Option(
        None, "--locale", help="Output English variant: UK (default) or US.", case_sensitive=False
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-o", help="Where to write the package (default ./output)."
    ),
    formats: str | None = typer.Option(
        None, "--formats", help="Comma-separated output formats: md, docx, pdf."
    ),
    config_file: Path | None = typer.Option(
        None, "--config", help="Path to a config.toml (default: ./config.toml if present)."
    ),
    roast: bool = typer.Option(
        False, "--roast", help="Also print a blunt, funny critique of your CV."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Estimate tokens and cost without calling the API."
    ),
    sequential: bool = typer.Option(
        False, "--sequential", help="Generate artifacts one at a time instead of in parallel."
    ),
    redact: bool = typer.Option(
        False,
        "--redact",
        help="Strip your name, email, phone and links before the provider sees the CV.",
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip the fabrication check on the generated documents."
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Ignore cached responses and re-issue every call."
    ),
    no_track: bool = typer.Option(
        False, "--no-track", help="Don't record this run in your local history."
    ),
    no_animation: bool = typer.Option(
        False, "--no-animation", help="Plain status lines instead of the printer animation."
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit with code 3 if the fabrication check finds anything unverified.",
    ),
    _version: bool | None = typer.Option(
        None, "--version", callback=_version_cb, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Generate a tailored application package from a CV and a job description."""
    if ctx.invoked_subcommand is not None:
        return

    # ---- resolve inputs ---------------------------------------------------
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    if not jd and not jd_file and not jd_dir:
        console.print("[red]Error:[/red] provide a job with --jd, --jd-file, or --jd-dir.")
        raise typer.Exit(code=2)

    config = load_config(config_file)
    _apply_overrides(config, provider, model, locale, output_dir, formats, no_track, sequential)

    resume = _load_cv(cv, cv_text)

    # ---- batch mode -------------------------------------------------------
    if jd_dir:
        jobs = sorted(p for p in jd_dir.iterdir() if p.suffix.lower() in _JD_SUFFIXES)
        if not jobs:
            console.print(f"[red]No .txt or .md job descriptions found in[/red] {jd_dir}")
            raise typer.Exit(code=1)
        _require_key(config)
        console.print(
            Panel.fit(
                f"Batch mode: [bold]{len(jobs)}[/bold] job descriptions from {jd_dir}",
                title="🖨  OfferPrinter",
                border_style="cyan",
            )
        )
        succeeded = 0
        for index, path in enumerate(jobs, start=1):
            console.rule(f"[cyan]{index}/{len(jobs)}[/cyan]  {path.name}")
            if _run_one(config, resume, path.read_text(encoding="utf-8"), not no_animation):
                succeeded += 1
        console.print()
        console.print(f"[green]Batch complete:[/green] {succeeded}/{len(jobs)} packages printed.")
        raise typer.Exit(code=0 if succeeded == len(jobs) else 1)

    if jd_clipboard:
        try:
            jd_value = jd_from_clipboard().text
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        console.print(f"[grey62]Read {len(jd_value):,} characters from the clipboard.[/grey62]")
    else:
        jd_value = jd if jd else jd_file.read_text(encoding="utf-8")  # type: ignore[union-attr]

    # ---- dry run ----------------------------------------------------------
    if dry_run:
        _dry_run(config, resume, jd_value)
        raise typer.Exit()

    _require_key(config)

    console.print(
        Panel.fit(
            f"Provider: [bold]{config.llm.provider.value}[/bold]  ·  "
            f"Model: [bold]{config.llm.model or 'provider default'}[/bold]  ·  "
            f"Locale: [bold]{config.output.locale.value}[/bold]  ·  "
            f"Formats: [bold]{', '.join(config.output.formats)}[/bold]",
            title="🖨  OfferPrinter",
            border_style="cyan",
        )
    )

    ok = _run_one(config, resume, jd_value, not no_animation)

    if ok and roast:
        _do_roast(config, resume)

    if ok and strict and _last_verification is not None and not _last_verification.passed:
        console.print(
            "[red]--strict:[/red] the fabrication check found unverified claims. "
            "Review fabrication-check.md before sending."
        )
        raise typer.Exit(code=3)

    raise typer.Exit(code=0 if ok else 1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _do_roast(config: Config, resume: ResumeInput) -> None:
    pipeline = Pipeline(config)
    with console.status("[red]Sharpening knives…[/red]", spinner="dots"):
        artifact = pipeline.generator.roast(resume)
    console.print()
    console.print(Panel(artifact.content, title="🔥 CV Roast", border_style="red"))
    out = Path(config.output.dir) / "roast.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(artifact.content.rstrip() + "\n", encoding="utf-8")
    console.print(f"[grey62]Saved to {out}[/grey62]")


@app.command("roast")
def roast_command(
    cv: Path | None = typer.Option(None, "--cv", help="Path to your CV/resume."),
    cv_text: str | None = typer.Option(None, "--cv-text", help="Paste your CV as raw text."),
    provider: Provider | None = typer.Option(None, "--provider", case_sensitive=False),
    model: str | None = typer.Option(None, "--model"),
    config_file: Path | None = typer.Option(None, "--config"),
) -> None:
    """Get a blunt, funny, unsparing critique of your CV. You asked for it.

    It roasts the writing, never you — and every jab has to point at something
    actually in the CV.
    """
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    config = load_config(config_file)
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""
    if model:
        config.llm.model = model
    _require_key(config)
    _do_roast(config, _load_cv(cv, cv_text))


@app.command("list")
def list_applications(
    limit: int = typer.Option(20, "--limit", "-n", help="How many to show (newest first)."),
    status: str | None = typer.Option(None, "--status", help=f"Filter: {', '.join(STATUSES)}."),
) -> None:
    """List every application package you have printed."""
    records = Tracker().load()
    if status:
        records = [r for r in records if r.status == status]
    if not records:
        console.print(
            "[grey62]No applications recorded yet. Print one and it'll show up here.[/grey62]"
        )
        return

    table = Table(title="🖨  Applications printed", header_style="bold cyan", expand=False)
    table.add_column("Date", style="grey62", no_wrap=True)
    table.add_column("Role")
    table.add_column("Company")
    table.add_column("Fit", justify="right")
    table.add_column("Status")

    for record in sorted(records, key=lambda r: r.printed_at, reverse=True)[:limit]:
        fit = "—" if record.fit_score is None else str(record.fit_score)
        fit_style = (
            "green"
            if (record.fit_score or 0) >= 70
            else "yellow"
            if (record.fit_score or 0) >= 50
            else "red"
        )
        table.add_row(
            record.printed_date,
            record.role,
            record.company,
            Text(fit, style=fit_style if record.fit_score is not None else "grey62"),
            record.status,
        )
    console.print(table)
    if len(records) > limit:
        console.print(
            f"[grey62]…and {len(records) - limit} more. Use --limit to see them.[/grey62]"
        )


@app.command("stats")
def stats_command() -> None:
    """Totals, spend, average fit, and achievements unlocked."""
    from offerprinter.services.tracker import ACHIEVEMENTS, unlocked

    records = Tracker().load()
    if not records:
        console.print("[grey62]Nothing recorded yet. Print an application to start.[/grey62]")
        return

    stats = summarise(records)
    lines = [
        f"Applications printed   [bold]{stats.total}[/bold]",
        f"Different companies    [bold]{stats.companies}[/bold]",
        f"Average fit score      [bold]{stats.average_fit}[/bold]",
        f"Best fit               [bold]{stats.best_fit}[/bold]  ({stats.best_fit_role})",
        f"Total tokens           [bold]{stats.total_tokens:,}[/bold]",
        f"Total spend            [bold]{format_cost(stats.total_cost_usd)}[/bold]",
        f"Active since           [bold]{stats.first_printed}[/bold]",
    ]
    console.print(Panel.fit("\n".join(lines), title="📊 Your job hunt", border_style="cyan"))

    if stats.by_status:
        breakdown = "  ".join(f"{k}: [bold]{v}[/bold]" for k, v in sorted(stats.by_status.items()))
        console.print(f"   {breakdown}")

    earned = unlocked(records)
    console.print()
    console.print("[bold]Achievements[/bold]")
    for achievement_id in ACHIEVEMENTS:
        mark = "[green]✓[/green]" if achievement_id in earned else "[grey37]·[/grey37]"
        style = "" if achievement_id in earned else "grey37"
        console.print(f"  {mark} ", end="")
        console.print(describe(achievement_id), style=style, highlight=False)


@app.command("status")
def status_command(
    slug: str = typer.Argument(..., help="The application slug, e.g. acme-data-analyst."),
    new_status: str = typer.Argument(..., help=f"One of: {', '.join(STATUSES)}."),
) -> None:
    """Update where an application has got to (applied, interview, offer…)."""
    try:
        record = Tracker().set_status(slug, new_status)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if record is None:
        console.print(f"[red]No application found with slug[/red] {slug}")
        console.print("[grey62]Run `offerprinter list` to see your slugs.[/grey62]")
        raise typer.Exit(code=1)

    console.print(f"[green]✓[/green] {record.role} at {record.company} → [bold]{new_status}[/bold]")
    if new_status == "offer":
        console.print("[magenta]🏆  An offer. That's the whole point. Congratulations.[/magenta]")


if __name__ == "__main__":
    app()


@app.command("rank")
def rank_command(
    cv: Path | None = typer.Option(None, "--cv", help="Path to your CV/resume."),
    cv_text: str | None = typer.Option(None, "--cv-text", help="Paste your CV as raw text."),
    jd_dir: Path | None = typer.Option(
        None, "--jd-dir", help="Folder of .txt/.md job descriptions to score."
    ),
    jd_file: list[Path] = typer.Option(
        None, "--jd-file", help="A job description file. Repeatable."
    ),
    jd: list[str] = typer.Option(None, "--jd", help="A job advert URL. Repeatable."),
    provider: Provider | None = typer.Option(None, "--provider", case_sensitive=False),
    model: str | None = typer.Option(None, "--model"),
    config_file: Path | None = typer.Option(None, "--config"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
    top: int = typer.Option(0, "--top", help="Show only the best N."),
) -> None:
    """Score many jobs against your CV and rank them, without writing documents.

    Triage before you commit an evening. Two cheap calls per advert, no files
    written — score twenty roles for a couple of pence, then print packages only
    for the ones worth it.
    """
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)

    jobs = collect_jobs(paths=jd_file or [], directory=jd_dir, urls=jd or [])
    if not jobs:
        console.print("[red]Error:[/red] provide jobs with --jd-dir, --jd-file or --jd.")
        raise typer.Exit(code=2)

    config = load_config(config_file)
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""
    if model:
        config.llm.model = model
    _require_key(config)

    resume = _load_cv(cv, cv_text)
    pipeline = Pipeline(config)
    ranker = Ranker(pipeline.generator, max_workers=config.generation.max_workers)

    results = []
    with console.status(f"[cyan]Scoring {len(jobs)} roles…[/cyan]", spinner="dots") as status:
        for progress in ranker.rank(resume, jobs):
            results.append(progress.result)
            status.update(f"[cyan]Scored {progress.done}/{progress.total}[/cyan]")

    ranked = sort_results(results)
    if top:
        ranked = ranked[:top]

    if as_json:
        console.print_json(
            data=[
                {
                    "source": r.source,
                    "company": r.company,
                    "role": r.role,
                    "score": r.score,
                    "band": r.fit.band if r.fit else "",
                    "gaps": r.fit.gaps if r.fit else [],
                    "error": r.error,
                }
                for r in ranked
            ]
        )
        return

    table = Table(title="🎯  Roles ranked by fit", header_style="bold cyan")
    table.add_column("#", justify="right", style="grey62")
    table.add_column("Fit", justify="right")
    table.add_column("Band")
    table.add_column("Role")
    table.add_column("Company")
    table.add_column("Real gaps", overflow="fold")

    for index, result in enumerate(ranked, start=1):
        if result.error:
            table.add_row(str(index), "—", "[red]error[/red]", result.source, "", result.error[:60])
            continue
        colour = "green" if result.score >= 70 else "yellow" if result.score >= 55 else "red"
        table.add_row(
            str(index),
            Text(str(result.score), style=colour),
            result.fit.band if result.fit else "",
            result.role or result.source,
            result.company,
            ", ".join(result.fit.gaps) if result.fit else "",
        )

    console.print(table)

    usage = pipeline.provider.usage
    if usage.calls:
        console.print(
            f"[grey62]{len(jobs)} roles · {usage.calls} calls · "
            f"{usage.total_tokens:,} tokens · {format_cost(usage.cost_usd)}[/grey62]"
        )
    best = next((r for r in ranked if not r.error), None)
    if best:
        console.print(
            f"\nPrint the top one with:\n  [cyan]offerprinter --cv <your-cv> "
            f"--jd-file {best.source}[/cyan]"
        )


@app.command("followup")
def followup_command(
    kind: str = typer.Argument(..., help=f"One of: {', '.join(FOLLOWUP_PROMPTS)}."),
    cv: Path | None = typer.Option(None, "--cv", help="Path to your CV/resume."),
    cv_text: str | None = typer.Option(None, "--cv-text", help="Paste your CV as raw text."),
    jd: str | None = typer.Option(None, "--jd", help="Job description as text or a URL."),
    jd_file: Path | None = typer.Option(
        None, "--jd-file", help="File holding the job description."
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        help="What was discussed, who you met, when you applied. Improves the result a lot.",
    ),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Read notes from a file."),
    provider: Provider | None = typer.Option(None, "--provider", case_sensitive=False),
    model: str | None = typer.Option(None, "--model"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o"),
    config_file: Path | None = typer.Option(None, "--config"),
) -> None:
    """Write a follow-up message: thank-you, recruiter, linkedin or nudge.

    The application does not end at submit. These are the messages that come
    after it, written from your real CV and your notes — never from invented
    recollections of a conversation.
    """
    if kind not in FOLLOWUP_PROMPTS:
        console.print(f"[red]Unknown follow-up '{kind}'.[/red] Choose from:")
        for key, (title, _, _) in FOLLOWUP_PROMPTS.items():
            console.print(f"  [cyan]{key}[/cyan] — {title}")
        raise typer.Exit(code=2)
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    if not jd and not jd_file:
        console.print("[red]Error:[/red] provide the job with --jd or --jd-file.")
        raise typer.Exit(code=2)

    config = load_config(config_file)
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""
    if model:
        config.llm.model = model
    if output_dir:
        config.output.dir = str(output_dir)
    _require_key(config)

    resume = _load_cv(cv, cv_text)
    note_text = notes or (notes_file.read_text(encoding="utf-8") if notes_file else "")

    try:
        job = load_job_description(
            jd if jd else jd_file.read_text(encoding="utf-8"),  # type: ignore[union-attr]
            timeout=config.llm.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not load job description:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    pipeline = Pipeline(config)
    with console.status("[cyan]Writing…[/cyan]", spinner="dots"):
        company = job.company or ""
        role = job.role or ""
        if not (company and role):
            company, role = pipeline.generator.extract_meta(job)
        artifact = pipeline.generator.followup(kind, resume, job, company, role, note_text)

    console.print()
    console.print(Panel(artifact.content, title=f"✉️  {artifact.title}", border_style="cyan"))

    folder = Path(config.output.dir) / f"{_slugify(company)}-{_slugify(role)}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{artifact.filename}.md"
    path.write_text(artifact.content.rstrip() + "\n", encoding="utf-8")
    console.print(f"[grey62]Saved to {path}[/grey62]")
    console.print("[grey62]Read it before you send it — it goes out in your name.[/grey62]")


@app.command("practice")
def practice_command(
    cv: Path | None = typer.Option(None, "--cv", help="Path to your CV/resume."),
    cv_text: str | None = typer.Option(None, "--cv-text", help="Paste your CV as raw text."),
    jd: str | None = typer.Option(None, "--jd", help="Job description as text or a URL."),
    jd_file: Path | None = typer.Option(
        None, "--jd-file", help="File holding the job description."
    ),
    questions: int = typer.Option(5, "--questions", "-n", help="How many questions to practise."),
    provider: Provider | None = typer.Option(None, "--provider", case_sensitive=False),
    model: str | None = typer.Option(None, "--model"),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o"),
    config_file: Path | None = typer.Option(None, "--config"),
) -> None:
    """Rehearse the interview: it asks, you answer, it critiques.

    The prep pack tells you what you might be asked. This makes you actually say
    it out loud, and every suggested improvement is grounded in your real CV —
    it will never coach you into claiming something you haven't done.
    """
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    if not jd and not jd_file:
        console.print("[red]Error:[/red] provide the job with --jd or --jd-file.")
        raise typer.Exit(code=2)

    config = load_config(config_file)
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""
    if model:
        config.llm.model = model
    if output_dir:
        config.output.dir = str(output_dir)
    _require_key(config)

    resume = _load_cv(cv, cv_text)
    try:
        job = load_job_description(
            jd if jd else jd_file.read_text(encoding="utf-8"),  # type: ignore[union-attr]
            timeout=config.llm.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not load job description:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    pipeline = Pipeline(config)
    with console.status("[cyan]Reading the role…[/cyan]", spinner="dots"):
        company = job.company or ""
        role = job.role or ""
        if not (company and role):
            company, role = pipeline.generator.extract_meta(job)

    console.print(
        Panel.fit(
            f"Practice interview — [bold]{role}[/bold] at [bold]{company}[/bold]\n"
            f"{questions} questions. Answer as you would out loud.\n"
            "[grey62]Press Enter on an empty answer to skip. Ctrl-C to stop early.[/grey62]",
            title="🎤 Interview practice",
            border_style="cyan",
        )
    )

    asked: list[str] = []
    transcript: list[str] = []

    try:
        for number in range(1, questions + 1):
            with console.status("[cyan]Thinking of a question…[/cyan]", spinner="dots"):
                question = pipeline.generator.practice_question(
                    resume, job, company, role, number, questions, asked
                )
            asked.append(question)

            console.print()
            console.rule(f"[cyan]Question {number}/{questions}[/cyan]")
            console.print(f"[bold]{question}[/bold]")
            console.print()
            answer = typer.prompt("Your answer", default="", show_default=False)

            if not answer.strip():
                console.print("[grey62]Skipped.[/grey62]")
                transcript.append(f"Q: {question}\nA: (skipped)\n")
                continue

            with console.status("[cyan]Reviewing…[/cyan]", spinner="dots"):
                feedback = pipeline.generator.practice_feedback(question, answer, resume, job)
            console.print()
            console.print(Panel(feedback, border_style="green"))
            transcript.append(f"Q: {question}\nA: {answer}\nFeedback: {feedback}\n")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[grey62]Stopping early.[/grey62]")

    if not transcript:
        raise typer.Exit()

    with console.status("[cyan]Summarising the session…[/cyan]", spinner="dots"):
        summary = pipeline.generator.practice_summary("\n".join(transcript), resume, company, role)

    console.print()
    console.print(Panel(summary.content, title="📋 Session summary", border_style="cyan"))

    folder = Path(config.output.dir) / f"{_slugify(company)}-{_slugify(role)}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "practice-summary.md"
    path.write_text(summary.content.rstrip() + "\n", encoding="utf-8")
    console.print(f"[grey62]Saved to {path}[/grey62]")


@app.command("verify")
def verify_command(
    package_dir: Path = typer.Argument(..., help="An output/<company>-<role> folder to check."),
    cv: Path | None = typer.Option(None, "--cv", help="The CV the package was built from."),
    cv_text: str | None = typer.Option(None, "--cv-text", help="Paste the CV as raw text."),
    jd_file: Path | None = typer.Option(None, "--jd-file", help="The job description used."),
    strict: bool = typer.Option(False, "--strict", help="Exit 3 if anything is unverified."),
) -> None:
    """Re-check an already-generated package against the CV it came from.

    Useful after you have hand-edited a tailored CV, and as a CI gate: it makes
    no API calls at all, so it costs nothing and works offline.
    """
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide the source CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    if not package_dir.is_dir():
        console.print(f"[red]Not a directory:[/red] {package_dir}")
        raise typer.Exit(code=2)

    resume = _load_cv(cv, cv_text)
    jd_text = jd_file.read_text(encoding="utf-8") if jd_file else ""
    job = JobDescription(text=jd_text or "(job description not supplied)")

    artifacts = []
    for key, filename in (
        ("tailored_cv", "tailored-cv.md"),
        ("cover_letter", "cover-letter.md"),
        ("ats_report", "ats-keyword-report.md"),
    ):
        path = package_dir / filename
        if path.is_file():
            artifacts.append(
                Artifact(
                    key=key,
                    title=key,
                    filename=path.stem,
                    content=path.read_text(encoding="utf-8"),
                )
            )

    if not artifacts:
        console.print(f"[red]No generated documents found in[/red] {package_dir}")
        raise typer.Exit(code=2)

    package = ApplicationPackage(company="", role="", slug=package_dir.name, artifacts=artifacts)
    verification = verify_package(package, resume, job)

    if verification.passed:
        console.print(
            Panel.fit(
                f"[green]{verification.summary()}[/green]\n"
                f"Checked: {', '.join(verification.checked_artifacts)}",
                title="✅ Fabrication check",
                border_style="green",
            )
        )
        return

    console.print(
        Panel.fit(
            f"[yellow]{verification.summary()}[/yellow]",
            title="⚠️  Fabrication check",
            border_style="yellow",
        )
    )
    for finding in verification.findings:
        colour = "red" if finding.severity.value == "high" else "yellow"
        console.print(f"  [{colour}]•[/{colour}] {finding.claim!r} — {finding.reason}")
        if finding.context:
            console.print(f"    [grey62]{finding.context}[/grey62]")

    if strict:
        raise typer.Exit(code=3)


cache_app = typer.Typer(help="Inspect and clear the local response cache.")
app.add_typer(cache_app, name="cache")


@cache_app.command("stats")
def cache_stats() -> None:
    """How much the cache is holding."""
    cache = ResponseCache()
    entries, total_bytes = cache.stats()
    console.print(
        Panel.fit(
            f"Entries: [bold]{entries}[/bold]\n"
            f"Size:    [bold]{total_bytes / 1024:.1f} KB[/bold]\n"
            f"Path:    [grey62]{cache.directory}[/grey62]",
            title="💾 Response cache",
            border_style="cyan",
        )
    )


@cache_app.command("clear")
def cache_clear() -> None:
    """Delete every cached response."""
    removed = ResponseCache().clear()
    console.print(f"[green]✓[/green] Cleared {removed} cached responses.")


@app.command("mcp")
def mcp_command() -> None:
    """Run as an MCP server on stdio, so agents can call OfferPrinter directly.

    Add to Claude Desktop's config:

      "offerprinter": {"command": "offerprinter", "args": ["mcp"]}
    """
    from offerprinter.mcp_server import OfferPrinterMCP

    OfferPrinterMCP().serve()
