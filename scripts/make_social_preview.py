#!/usr/bin/env python3
"""Generate `assets/social-preview.svg` — the card shown when the repo is shared.

GitHub renders a repository's social preview image on every link shared to
Twitter/X, LinkedIn, Slack and Discord. Without one you get a grey default card
with a tiny avatar, which is a wasted impression every single time.

    python scripts/make_social_preview.py

That writes the SVG. GitHub needs a PNG or JPG, uploaded by hand (there is no
API for it), so rasterise it first with whichever of these you have:

    rsvg-convert -w 1280 -h 640 assets/social-preview.svg -o assets/social-preview.png
    inkscape assets/social-preview.svg -o assets/social-preview.png -w 1280 -h 640
    magick -background none assets/social-preview.svg -resize 1280x640 assets/social-preview.png

    # or with Chrome, which everyone already has:
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
      --headless --disable-gpu --screenshot=assets/social-preview.png \\
      --window-size=1280,640 --default-background-color=00000000 \\
      assets/social-preview.svg

Then: repo → Settings → General → Social preview → Upload an image.
GitHub recommends 1280x640px, and hard-caps the file at 1MB.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "social-preview.svg"

W, H = 1280, 640

INK = "#0d0f16"
INK_SOFT = "#161a26"
PURPLE = "#8b5cf6"
CYAN = "#22d3ee"
GREEN = "#4ade80"
TEXT = "#f4f6fb"
MUTED = "#8b95ad"

SANS = "Inter, 'SF Pro Display', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

#: The five artifacts, as chips down the right-hand side.
CHIPS = [
    "Tailored CV",
    "Cover letter",
    "Fit memo",
    "ATS keyword report",
    "Interview prep pack",
]


def build() -> str:
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="OfferPrinter — one CV plus one job description becomes a '
        f"tailored CV, cover letter, fit memo, ATS keyword report and interview "
        f'prep pack, with zero fabrication">',
        "<defs>",
        # A soft diagonal wash so the card doesn't read as a flat black rectangle.
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{INK}"/>'
        f'<stop offset="55%" stop-color="{INK_SOFT}"/>'
        f'<stop offset="100%" stop-color="{INK}"/>'
        f"</linearGradient>",
        f'<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{PURPLE}"/>'
        f'<stop offset="100%" stop-color="{CYAN}"/>'
        f"</linearGradient>",
        '<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0%" stop-color="{PURPLE}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{PURPLE}" stop-opacity="0"/>'
        "</radialGradient>",
        "</defs>",
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        '<circle cx="1090" cy="150" r="360" fill="url(#glow)"/>',
        # Top accent rule.
        f'<rect x="0" y="0" width="{W}" height="6" fill="url(#accent)"/>',
    ]

    # --- left column: the pitch ---------------------------------------------
    parts += [
        f'<text x="72" y="130" font-family="{MONO}" font-size="22" fill="{CYAN}" '
        f'letter-spacing="3">FREE &amp; OPEN SOURCE &#183; MIT</text>',
        f'<text x="72" y="215" font-family="{SANS}" font-size="82" font-weight="800" '
        f'fill="{TEXT}">&#128424; OfferPrinter</text>',
        f'<text x="72" y="285" font-family="{SANS}" font-size="36" font-weight="600" '
        f'fill="{TEXT}">One CV. One job description.</text>',
        f'<text x="72" y="333" font-family="{SANS}" font-size="36" font-weight="600" '
        f'fill="url(#accent)">Five documents. Zero fabrication.</text>',
        f'<text x="72" y="399" font-family="{SANS}" font-size="25" fill="{MUTED}">'
        f"Runs on your machine, on your own API key.</text>",
        f'<text x="72" y="435" font-family="{SANS}" font-size="25" fill="{MUTED}">'
        f"It never invents experience &#8212; real gaps get flagged.</text>",
        # The install line, in a terminal-ish pill.
        f'<rect x="72" y="480" width="560" height="62" rx="12" fill="#000000" '
        f'fill-opacity="0.45" stroke="{PURPLE}" stroke-opacity="0.45"/>',
        f'<text x="100" y="520" font-family="{MONO}" font-size="25" fill="{GREEN}">'
        f'$ <tspan fill="{TEXT}">pipx install offerprinter</tspan></text>',
        f'<text x="72" y="590" font-family="{MONO}" font-size="21" fill="{MUTED}">'
        f"github.com/mohitagw15856/OfferPrinter</text>",
    ]

    # --- right column: what comes out ---------------------------------------
    chip_x, chip_w, chip_h, gap = 810, 400, 72, 18
    top = (H - (len(CHIPS) * chip_h + (len(CHIPS) - 1) * gap)) / 2 + 10

    for index, label in enumerate(CHIPS):
        y = top + index * (chip_h + gap)
        parts += [
            f'<rect x="{chip_x}" y="{y:.0f}" width="{chip_w}" height="{chip_h}" rx="14" '
            f'fill="#ffffff" fill-opacity="0.06" stroke="#ffffff" stroke-opacity="0.12"/>',
            f'<rect x="{chip_x}" y="{y:.0f}" width="5" height="{chip_h}" rx="2.5" '
            f'fill="url(#accent)"/>',
            f'<text x="{chip_x + 34}" y="{y + 45:.0f}" font-family="{SANS}" font-size="27" '
            f'font-weight="600" fill="{TEXT}">{label}</text>',
        ]

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    print("Rasterise it to PNG and upload via Settings → General → Social preview.")
