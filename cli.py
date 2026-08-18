#!/usr/bin/env python3
"""OfferPrinter command-line interface.

Examples
--------
Paste-free, one-liner run from a CV file and a job URL:

    python cli.py --cv path/to/cv.pdf --jd "https://careers.example.com/123"

From a CV file and a job description saved in a file:

    python cli.py --cv cv.docx --jd-file jd.txt

Switch provider on the fly (otherwise config.toml / env vars decide):

    python cli.py --cv cv.md --jd-file jd.txt --provider openai

Run `python cli.py --help` for the full list of options.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from offerprinter import __version__
from offerprinter.config import load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.models.schemas import Locale, Provider
from offerprinter.services.cv_parser import cv_from_text, extract_cv
from offerprinter.services.jd_fetcher import load_job_description

app = typer.Typer(
    add_completion=False,
    help="Paste one job description and your CV; print a full, tailored, "
    "no-fabrication application package.",
    rich_markup_mode="rich",
)
console = Console()


def _version_cb(value: bool) -> None:
    if value:
        console.print(f"OfferPrinter {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def run(
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
    config_file: Path | None = typer.Option(
        None, "--config", help="Path to a config.toml (default: ./config.toml if present)."
    ),
    _version: bool | None = typer.Option(
        None, "--version", callback=_version_cb, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Generate a tailored application package from a CV and a job description."""
    # ---- resolve inputs ---------------------------------------------------
    if not cv and not cv_text:
        console.print("[red]Error:[/red] provide a CV with --cv or --cv-text.")
        raise typer.Exit(code=2)
    if not jd and not jd_file:
        console.print("[red]Error:[/red] provide a job description with --jd or --jd-file.")
        raise typer.Exit(code=2)

    config = load_config(config_file)
    # Apply per-run overrides.
    if provider:
        config.llm.provider = provider
        config.llm.model = model or ""  # let the new provider pick its default
    if model:
        config.llm.model = model
    if locale:
        config.output.locale = locale
    if output_dir:
        config.output.dir = str(output_dir)

    if not config.llm.api_key:
        console.print(
            Panel.fit(
                f"No API key for provider [bold]{config.llm.provider.value}[/bold].\n"
                "Set it in config.toml or via an environment variable "
                "(see config.example.toml).",
                title="Missing API key",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    # ---- load CV + JD -----------------------------------------------------
    try:
        resume = cv_from_text(cv_text) if cv_text else extract_cv(cv)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not read CV:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    jd_value = jd if jd else jd_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
    try:
        job = load_job_description(jd_value, timeout=config.llm.timeout)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not load job description:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    # ---- run pipeline -----------------------------------------------------
    console.print(
        Panel.fit(
            f"Provider: [bold]{config.llm.provider.value}[/bold]  ·  "
            f"Model: [bold]{config.llm.model or 'provider default'}[/bold]  ·  "
            f"Locale: [bold]{config.output.locale.value}[/bold]",
            title="🖨  OfferPrinter",
            border_style="cyan",
        )
    )

    pipeline = Pipeline(config)
    written = None
    try:
        with console.status("[cyan]Working…[/cyan]", spinner="dots") as status:
            for event in pipeline.stream(resume, job):
                if event.kind == "meta":
                    status.update(f"[cyan]Target: {event.message}[/cyan]")
                    console.print(f"🎯 Target role: [bold]{event.message}[/bold]")
                elif event.kind == "artifact":
                    console.print(f"  ✓ {event.message}")
                elif event.kind == "written":
                    written = event.written
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Generation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    # ---- summary ----------------------------------------------------------
    out_folder = Path(config.output.dir) / pipeline_slug(written)
    console.print(
        Panel.fit(
            f"Package written to [bold]{out_folder}[/bold]\n"
            "Every line is drawn from your real CV — review before sending.",
            title="✅ Done",
            border_style="green",
        )
    )


def pipeline_slug(written) -> str:  # noqa: ANN001 - small helper
    """Best-effort recover the output folder name from written paths."""
    if written:
        for paths in written.values():
            if paths:
                return paths[0].parent.name
    return ""


if __name__ == "__main__":
    app()
