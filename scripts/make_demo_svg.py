#!/usr/bin/env python3
"""Generate `assets/demo.svg` — the animated terminal demo in the README.

A real asciinema recording would need an API key and a live run, and would go
stale the moment the CLI output changed. This renders the same thing as a
self-contained, dependency-free animated SVG: no JavaScript, no external hosting,
and it animates on GitHub because SMIL works inside an <img>.

    python scripts/make_demo_svg.py

Edit `SCRIPT` below and re-run to update the demo.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "assets" / "demo.svg"

# --- look and feel ----------------------------------------------------------

FONT_SIZE = 15
CHAR_W = FONT_SIZE * 0.601  # advance width of a monospace glyph
LINE_H = FONT_SIZE * 1.44
PAD_X = 22
PAD_TOP = 46  # room for the title bar
PAD_BOTTOM = 28
LOOP = 16.0  # seconds for one full cycle
HOLD = 0.94  # fraction of the loop before everything fades out

COLOURS = {
    "bg": "#11131a",
    "chrome": "#1b1e28",
    "text": "#c8d0e0",
    "dim": "#6b7487",
    "prompt": "#7bd88f",
    "cyan": "#5ad4e6",
    "green": "#7bd88f",
    "yellow": "#f9cb6c",
    "magenta": "#cb7cff",
    "white": "#ffffff",
}

# --- the script: (delay in seconds, colour key, text) -----------------------

SCRIPT: list[tuple[float, str, str]] = [
    (0.3, "prompt", "$ pipx install offerprinter"),
    (1.0, "dim", "  installed package offerprinter 0.2.0 (Python 3.12)"),
    (1.3, "dim", "  These apps are now globally available:  offerprinter  opr"),
    (2.1, "prompt", '$ offerprinter --cv ~/cv.pdf --jd "https://careers.northbank.com/812"'),
    (2.8, "cyan", "  OfferPrinter   anthropic - claude-haiku-4-5 - UK - md,docx,pdf"),
    (3.3, "white", "  Target role: Senior Product Analyst at NorthBank"),
    (3.8, "dim", "  printing 5 documents in parallel ..."),
    (4.4, "green", "      [+] Tailored CV"),
    (5.0, "green", "      [+] ATS Keyword Report"),
    (5.5, "green", "      [+] Cover Letter"),
    (6.0, "green", "      [+] Fit Memo"),
    (6.6, "green", "      [+] Interview Prep Pack"),
    (7.4, "yellow", "  Fit score  74/100  [################......]  Strong"),
    (7.8, "dim", "    A genuinely competitive application. Send it."),
    (8.2, "dim", "    Real gaps: dbt; financial services domain"),
    (9.0, "green", "  Package written to output/northbank-senior-product-analyst/"),
    (9.4, "dim", "    7 calls - 24,318 tokens - $0.038 (about \N{POUND SIGN}0.030)"),
    (9.8, "dim", "    Every line is drawn from your real CV - review before sending."),
    (10.6, "magenta", "  Achievement unlocked: Bullseye - scored 85+ on a role"),
    (11.4, "prompt", "$ offerprinter stats"),
    (11.9, "white", "    Applications printed  12        Average fit  68.4"),
    (12.2, "white", "    Total spend  $0.41              Interviews  3"),
]


def display_width(text: str) -> int:
    """Terminal cell width of a string: emoji and CJK take two cells, not one.

    Without this the box-drawing borders come out ragged, because `len()` counts
    an emoji as one character while every terminal (and every SVG renderer)
    draws it two cells wide.
    """
    width = 0
    for char in text:
        if ord(char) >= 0x1F300 or unicodedata.east_asian_width(char) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def build() -> str:
    cells = max(display_width(text) for _, _, text in SCRIPT)
    width = int(cells * CHAR_W) + PAD_X * 2
    height = int(len(SCRIPT) * LINE_H) + PAD_TOP + PAD_BOTTOM

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="OfferPrinter terminal demo: installing, printing a tailored '
        f'application package, and showing a fit score of 74 out of 100">',
        "<title>OfferPrinter — printing a full application package in one command</title>",
        # window
        f'<rect width="{width}" height="{height}" rx="10" fill="{COLOURS["bg"]}"/>',
        f'<rect width="{width}" height="32" rx="10" fill="{COLOURS["chrome"]}"/>',
        f'<rect y="22" width="{width}" height="10" fill="{COLOURS["chrome"]}"/>',
        '<circle cx="20" cy="16" r="5.5" fill="#ff5f57"/>',
        '<circle cx="39" cy="16" r="5.5" fill="#febc2e"/>',
        '<circle cx="58" cy="16" r="5.5" fill="#28c840"/>',
        f'<text x="{width / 2}" y="20.5" text-anchor="middle" fill="{COLOURS["dim"]}" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12">'
        f"offerprinter — zsh</text>",
        f'<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
        f'font-size="{FONT_SIZE}" xml:space="preserve">',
    ]

    for index, (delay, colour, text) in enumerate(SCRIPT):
        y = PAD_TOP + (index + 1) * LINE_H
        show = min(delay / LOOP, HOLD - 0.01)
        # values/keyTimes animation: invisible, snap on at `show`, hold, fade out.
        parts.append(
            # Base opacity is 1 so the whole frame is still legible in any
            # viewer that doesn't run SMIL; the animation overrides it when it does.
            # Base opacity is 1 so the whole frame is still legible in any
            # viewer that doesn't run SMIL; the animation overrides it when it does.
            # xml:space has to sit on the <text> itself — renderers collapse
            # leading whitespace otherwise, and the indentation is the layout.
            f'<text x="{PAD_X}" y="{y:.1f}" fill="{COLOURS[colour]}" opacity="1" '
            f'xml:space="preserve">'
            f'<animate attributeName="opacity" '
            f'values="0;0;1;1;0" '
            f'keyTimes="0;{show:.4f};{min(show + 0.006, HOLD):.4f};{HOLD};1" '
            f'dur="{LOOP}s" repeatCount="indefinite"/>'
            f"{escape(text)}</text>"
        )

    # A blinking cursor that sits at the end of the final line.
    last_y = PAD_TOP + len(SCRIPT) * LINE_H
    parts.append(
        f'<rect x="{PAD_X}" y="{last_y + 4:.1f}" width="{CHAR_W:.1f}" height="{FONT_SIZE}" '
        f'fill="{COLOURS["prompt"]}">'
        f'<animate attributeName="opacity" values="1;0;1" dur="1.06s" repeatCount="indefinite"/>'
        f"</rect>"
    )

    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
