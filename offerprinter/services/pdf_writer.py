"""A tiny, dependency-free PDF writer for ATS-friendly documents.

Recruiters ask for PDFs; Applicant Tracking Systems need those PDFs to contain
real, selectable text in a standard font — not an image, not an exotic embedded
typeface. That is a narrow enough target that we can write the PDF ourselves in
about 200 lines rather than pulling in a rendering engine.

What it supports, matching the Markdown the generator actually produces:
headings (`#`, `##`, `###`), bullet and numbered lists, blockquotes, horizontal
rules, blank lines, and `**bold**` spans inside any of them. Everything is set
in Helvetica — one of the 14 PDF base fonts, so nothing needs embedding and
every ATS on earth can read it.

Deliberately not supported: images, tables, columns, colour. Those are exactly
the things that break ATS parsing, so their absence is a feature.
"""

from __future__ import annotations

import re
from pathlib import Path

# --- page geometry (A4, in PostScript points) -------------------------------

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN_X = 56.0  # ~2cm
MARGIN_TOP = 56.0
MARGIN_BOTTOM = 56.0

BODY_SIZE = 10.5
LINE_GAP = 1.34  # line height as a multiple of font size

#: (font size, space above, space below, bold) per heading level.
_HEADING_STYLE = {
    1: (18.0, 0.0, 9.0, True),
    2: (13.5, 12.0, 5.0, True),
    3: (11.5, 9.0, 3.0, True),
}

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")

# Helvetica / Helvetica-Bold advance widths for ASCII 32-126, in 1/1000 em.
# Taken from the standard Adobe font metrics so wrapping matches what a reader
# will actually see.
_W_REGULAR = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_W_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)
_WIDTHS = {
    False: [int(w) for w in _W_REGULAR.split()],
    True: [int(w) for w in _W_BOLD.split()],
}

# Unicode the generator legitimately emits -> WinAnsi-safe equivalents.
_TRANSLITERATE = {
    "—": "-",
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
    "•": "-",
    "→": "->",
    "✓": "v",
    "✗": "x",
    "·": "-",
    "█": "#",
    "░": ".",
}


def _clean(text: str) -> str:
    for src, dst in _TRANSLITERATE.items():
        text = text.replace(src, dst)
    return text


def _text_width(text: str, size: float, bold: bool) -> float:
    """Width of a string in points at a given size."""
    widths = _WIDTHS[bold]
    total = 0
    for ch in text:
        code = ord(ch)
        total += widths[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000.0


def _escape(text: str) -> bytes:
    """Escape a string for a PDF literal and encode as WinAnsi (cp1252)."""
    out = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return out.encode("cp1252", errors="replace")


# --- inline runs -------------------------------------------------------------


def _split_bold(text: str) -> list[tuple[str, bool]]:
    """Split `a **b** c` into [("a ", False), ("b", True), (" c", False)]."""
    runs: list[tuple[str, bool]] = []
    pos = 0
    for match in _BOLD_RE.finditer(text):
        if match.start() > pos:
            runs.append((text[pos : match.start()], False))
        runs.append((match.group(1), True))
        pos = match.end()
    if pos < len(text):
        runs.append((text[pos:], False))
    return runs or [("", False)]


def _wrap_runs(
    runs: list[tuple[str, bool]], size: float, max_width: float
) -> list[list[tuple[str, bool]]]:
    """Greedy word-wrap over styled runs, preserving each word's style."""
    words: list[tuple[str, bool]] = []
    for text, bold in runs:
        for i, word in enumerate(text.split(" ")):
            if word or i == 0:
                words.append((word, bold))

    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    width = 0.0
    for word, bold in words:
        if not word:
            continue
        space = _text_width(" ", size, bold) if current else 0.0
        word_width = _text_width(word, size, bold)
        if current and width + space + word_width > max_width:
            lines.append(current)
            current, width = [(word, bold)], word_width
        else:
            current.append((word, bold))
            width += space + word_width
    if current:
        lines.append(current)
    return lines or [[]]


# --- the document builder ----------------------------------------------------


class _Doc:
    """Accumulates page content streams, breaking pages as it fills."""

    def __init__(self) -> None:
        self.pages: list[list[bytes]] = [[]]
        self.y = PAGE_HEIGHT - MARGIN_TOP

    @property
    def _current(self) -> list[bytes]:
        return self.pages[-1]

    def _ensure_space(self, needed: float) -> None:
        if self.y - needed < MARGIN_BOTTOM:
            self.pages.append([])
            self.y = PAGE_HEIGHT - MARGIN_TOP

    def space(self, amount: float) -> None:
        if amount and self.y < PAGE_HEIGHT - MARGIN_TOP:
            self.y -= amount

    def rule(self) -> None:
        self._ensure_space(12)
        self.y -= 6
        self._current.append(
            b"0.75 w 0.6 0.6 0.6 RG %.2f %.2f m %.2f %.2f l S"
            % (MARGIN_X, self.y, PAGE_WIDTH - MARGIN_X, self.y)
        )
        self.y -= 8

    def paragraph(
        self,
        runs: list[tuple[str, bool]],
        size: float = BODY_SIZE,
        indent: float = 0.0,
        bullet: str = "",
        force_bold: bool = False,
        grey: bool = False,
    ) -> None:
        """Lay out one wrapped block of text."""
        if force_bold:
            runs = [(text, True) for text, _ in runs]
        max_width = PAGE_WIDTH - 2 * MARGIN_X - indent
        lines = _wrap_runs(runs, size, max_width)
        leading = size * LINE_GAP
        colour = b"0.35 0.35 0.35 rg" if grey else b"0 0 0 rg"

        for index, line in enumerate(lines):
            self._ensure_space(leading)
            self.y -= leading
            x = MARGIN_X + indent
            parts: list[bytes] = [colour]

            if bullet and index == 0:
                parts.append(
                    b"BT /F1 %.2f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                    % (size, MARGIN_X + indent - 14.0, self.y, _escape(bullet))
                )

            for word_index, (word, bold) in enumerate(line):
                if word_index:
                    x += _text_width(" ", size, bold)
                font = b"/F2" if bold else b"/F1"
                parts.append(
                    b"BT %s %.2f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                    % (font, size, x, self.y, _escape(word))
                )
                x += _text_width(word, size, bold)
            self._current.append(b"\n".join(parts))


def markdown_to_pdf_bytes(markdown: str) -> bytes:
    """Render OfferPrinter-flavoured Markdown to a complete PDF file."""
    doc = _Doc()

    for raw_line in _clean(markdown).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            doc.space(BODY_SIZE * 0.55)
            continue
        if _HR_RE.match(stripped):
            doc.rule()
            continue
        if stripped.startswith("```"):
            continue  # fences never survive into the output; skip stray ones

        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            size, above, below, bold = _HEADING_STYLE[level]
            doc.space(above)
            doc.paragraph(_split_bold(heading.group(2)), size=size, force_bold=bold)
            doc.space(below)
            continue

        if stripped.startswith("> "):
            doc.paragraph(_split_bold(stripped[2:]), indent=16.0, grey=True)
            continue

        if stripped.startswith(("- ", "* ")):
            indent = 14.0 + (len(line) - len(line.lstrip())) * 0.5
            doc.paragraph(_split_bold(stripped[2:]), indent=indent, bullet="-")
            continue

        ordered = _ORDERED_RE.match(stripped)
        if ordered:
            doc.paragraph(_split_bold(ordered.group(2)), indent=18.0, bullet=f"{ordered.group(1)}.")
            continue

        doc.paragraph(_split_bold(stripped))

    return _assemble(doc.pages)


def _assemble(pages: list[list[bytes]]) -> bytes:
    """Serialise pages into a valid PDF with a correct cross-reference table."""
    pages = pages or [[]]
    page_count = len(pages)

    # Object numbering: 1 catalog, 2 pages tree, 3 + 4 fonts,
    # then per page: a page object and its content stream.
    first_page_obj = 5
    objects: dict[int, bytes] = {}

    kids = " ".join(f"{first_page_obj + i * 2} 0 R" for i in range(page_count))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>".encode("ascii")
    objects[3] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects[4] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )

    for i, content in enumerate(pages):
        page_obj = first_page_obj + i * 2
        stream_obj = page_obj + 1
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {stream_obj} 0 R >>"
        ).encode("ascii")
        stream = b"\n".join(content)
        objects[stream_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("ascii") + objects[number] + b"\nendobj\n"

    xref_offset = len(out)
    total = max(objects) + 1
    out += f"xref\n0 {total}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for number in range(1, total):
        out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
    out += (f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n").encode(
        "ascii"
    )
    return bytes(out)


def write_pdf(markdown: str, path: Path) -> Path:
    """Render Markdown to a PDF file on disk."""
    path.write_bytes(markdown_to_pdf_bytes(markdown))
    return path
