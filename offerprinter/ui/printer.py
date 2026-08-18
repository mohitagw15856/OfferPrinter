"""The printer animation — an ASCII dot-matrix printer feeding paper.

Purely cosmetic, and that is the point: a generation run is 30-60 seconds of
nothing, and watching a little printer chug through five documents is far nicer
than watching a spinner. It degrades safely — if the output is not a terminal
(piped, redirected, CI, or `--no-animation`), it prints plain status lines
instead and nothing is lost.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

#: The printer body. `{roll}` animates the paper feed rollers.
_PRINTER = r"""     ╔═══════════════════════════════════╗
     ║  ● OfferPrinter        {status}  ║
     ╟───────────────────────────────────╢
     ║ {roll} ║
     ╚═══════════════════════════════════╝"""

#: Frames for the paper-feed rollers, cycled while a document is generating.
_ROLLERS = [
    "▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚▚",
    "▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞▞",
]

#: How a sheet of paper looks as it emerges, one line at a time.
_SHEET_TOP = "      ┌─────────────────────────────────┐"
_SHEET_ROW = "      │ {line:<31} │"
_SHEET_BOTTOM = "      └─────────────────────────────────┘"

_STATUS_WIDTH = 10


def _supports_animation(console: Console) -> bool:
    """Animate only when there's a human watching a real terminal."""
    if os.environ.get("OFFERPRINTER_NO_ANIM"):
        return False
    if os.environ.get("CI"):
        return False
    return console.is_terminal and not console.is_jupyter


class PrinterAnimation:
    """Draws the printer while artifacts generate, feeding a sheet per artifact.

    Use as a context manager:

        with PrinterAnimation(console, total=5) as anim:
            anim.status("Reading the job description")
            anim.sheet("Tailored CV")
    """

    def __init__(self, console: Console, total: int, enabled: bool = True) -> None:
        self.console = console
        self.total = max(total, 1)
        self.enabled = enabled and _supports_animation(console)
        self.done = 0
        self._status = "warming up"
        self._sheets: list[str] = []
        self._live: Live | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames = itertools.cycle(_ROLLERS)
        self._lock = threading.Lock()

    # -- rendering ----------------------------------------------------------

    def _render(self) -> Group:
        with self._lock:
            status = self._status[:_STATUS_WIDTH].ljust(_STATUS_WIDTH)
            sheets = list(self._sheets)

        body = Text(
            _PRINTER.format(status=status, roll=next(self._frames)),
            style="bright_cyan",
        )
        lines: list[Text | str] = [body]
        if sheets:
            lines.append(Text(_SHEET_TOP, style="grey58"))
            for name in sheets:
                lines.append(Text(_SHEET_ROW.format(line=f"✓ {name}"), style="green"))
            lines.append(Text(_SHEET_BOTTOM, style="grey58"))
        return Group(*lines)

    def _spin(self) -> None:
        while not self._stop.wait(0.18):
            if self._live is not None:
                self._live.update(self._render())

    # -- public API ---------------------------------------------------------

    def status(self, message: str) -> None:
        """Update the little status readout on the printer's front panel."""
        with self._lock:
            self._status = message
        if not self.enabled:
            self.console.print(f"[cyan]…[/cyan] {message}")
        elif self._live is not None:
            self._live.update(self._render())

    def sheet(self, title: str) -> None:
        """Feed one finished sheet out of the printer."""
        self.done += 1
        with self._lock:
            self._sheets.append(title)
            self._status = f"{self.done}/{self.total}"
        if not self.enabled:
            self.console.print(f"  [green]✓[/green] {title}")
        elif self._live is not None:
            self._live.update(self._render())

    def __enter__(self) -> PrinterAnimation:
        if self.enabled:
            self._live = Live(
                self._render(),
                console=self.console,
                refresh_per_second=12,
                transient=False,
            )
            self._live.__enter__()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._live is not None:
            with self._lock:
                self._status = "done".ljust(_STATUS_WIDTH)
            self._live.update(self._render())
            self._live.__exit__(*exc_info)  # type: ignore[arg-type]
            self._live = None


def render_fit_bar(score: int, width: int = 24) -> Text:
    """A coloured 0-100 bar for the fit score, for the end-of-run summary."""
    filled = round(score / 100 * width)
    colour = "green" if score >= 70 else "yellow" if score >= 50 else "red"
    bar = Text()
    bar.append("█" * filled, style=colour)
    bar.append("░" * (width - filled), style="grey37")
    return bar


def type_out(console: Console, text: str, delay: float = 0.012, style: str = "") -> None:
    """Print text a character at a time, for the one line that deserves it."""
    if not _supports_animation(console) or delay <= 0:
        console.print(text, style=style)
        return
    for char in text:
        console.print(char, end="", style=style, highlight=False, markup=False)
        sys.stdout.flush()
        time.sleep(delay)
    console.print()
