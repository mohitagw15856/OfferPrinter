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
from offerprinter.models.schemas import Locale, Provider, ResumeInput
from offerprinter.pricing import estimate_cost, format_cost
from offerprinter.services.cv_parser import cv_from_text, extract_cv
from offerprinter.services.jd_fetcher import load_job_description
from offerprinter.services.tracker import (
    STATUSES,
    Tracker,
    describe,
    summarise,
)
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

    lines = [f"Package written to [bold]{out_folder}[/bold]"]
    cost = _cost_line(config, package)
    if cost:
        lines.append(f"[grey62]{cost}[/grey62]")
    lines.append("Every line is drawn from your real CV — review before sending.")
    console.print(Panel.fit("\n".join(lines), title="✅ Done", border_style="green"))

    for achievement in achievements:
        console.print(f"[magenta]Achievement unlocked:[/magenta] {describe(achievement)}")


def _run_one(config: Config, resume: ResumeInput, jd_value: str, animate: bool) -> bool:
    """Print one package. Returns True on success."""
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
    no_track: bool = typer.Option(
        False, "--no-track", help="Don't record this run in your local history."
    ),
    no_animation: bool = typer.Option(
        False, "--no-animation", help="Plain status lines instead of the printer animation."
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
