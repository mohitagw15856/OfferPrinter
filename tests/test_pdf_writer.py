"""Tests for the dependency-free PDF writer.

The important property is not "it produces bytes" but "a PDF reader can parse
it and get the text back out" — an ATS that cannot extract text from your CV
will reject you without a human ever seeing it.
"""

from __future__ import annotations

import pypdf
import pytest

from offerprinter.services.pdf_writer import (
    _split_bold,
    _text_width,
    _wrap_runs,
    markdown_to_pdf_bytes,
    write_pdf,
)

SAMPLE = """# Alex Morgan

alex@example.com · +44 7700 900123 · Manchester, UK

## Professional Summary

Data analyst with **4 years'** experience owning analysis end to end.

## Experience

### Marketing Data Analyst — BrightWave Retail

- Owned the analytics for the marketing area end to end, defining the reporting metrics and building the datasets in SQL, then maintaining every dashboard the team relied on week after week.
- Designed and ran 30+ A/B tests.

1. First numbered thing
2. Second numbered thing

> A quoted line.

---

## Education
BSc Mathematics.
"""


def test_produces_a_readable_pdf():
    data = markdown_to_pdf_bytes(SAMPLE)
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")


def test_text_is_extractable(tmp_path):
    path = write_pdf(SAMPLE, tmp_path / "cv.pdf")
    reader = pypdf.PdfReader(str(path))
    text = "\n".join(page.extract_text() for page in reader.pages)

    # An ATS must be able to read all of this back.
    assert "Alex Morgan" in text
    assert "BrightWave Retail" in text
    assert "30+ A/B tests" in text
    assert "BSc Mathematics" in text


def test_long_documents_paginate():
    long_markdown = SAMPLE + ("\n\nA reasonably long paragraph of filler text. " * 200)
    reader = pypdf.PdfReader(_as_stream(long_markdown))
    assert len(reader.pages) > 1


def test_empty_input_still_produces_a_valid_pdf():
    reader = pypdf.PdfReader(_as_stream(""))
    assert len(reader.pages) == 1


def test_unicode_is_transliterated_not_dropped():
    """Smart quotes and em dashes must survive into WinAnsi, not crash."""
    text = _extract(_as_stream("# Test\n\nIt's a “quote” — with an em dash… and £100."))
    assert "quote" in text
    assert "100" in text


def test_bold_splitting():
    assert _split_bold("a **b** c") == [("a ", False), ("b", True), (" c", False)]
    assert _split_bold("plain") == [("plain", False)]
    assert _split_bold("") == [("", False)]


def test_bold_text_is_wider_than_regular():
    assert _text_width("Hello", 10, bold=True) > _text_width("Hello", 10, bold=False)


def test_wrapping_respects_the_measured_width():
    runs = [("word " * 40, False)]
    lines = _wrap_runs(runs, size=10, max_width=100)
    assert len(lines) > 1
    for line in lines:
        width = sum(_text_width(w, 10, b) for w, b in line)
        width += _text_width(" ", 10, False) * (len(line) - 1)
        assert width <= 100 + 1e-6


def test_parentheses_are_escaped():
    """Unescaped ( or ) would corrupt the PDF's string syntax."""
    text = _extract(_as_stream("# Role (Remote)\n\nSomething (in brackets)."))
    assert "Remote" in text
    assert "brackets" in text


@pytest.mark.parametrize("heading", ["# H1", "## H2", "### H3"])
def test_all_heading_levels_render(heading):
    assert markdown_to_pdf_bytes(f"{heading}\n\nBody.").startswith(b"%PDF")


# --- helpers -----------------------------------------------------------------


def _as_stream(markdown: str):
    import io

    return io.BytesIO(markdown_to_pdf_bytes(markdown))


def _extract(stream) -> str:
    reader = pypdf.PdfReader(stream)
    return "\n".join(page.extract_text() for page in reader.pages)
