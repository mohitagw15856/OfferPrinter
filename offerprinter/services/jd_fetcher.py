"""Load a job description from a URL (fetch + extract) or from pasted text.

URL fetching is the only outbound network call besides the LLM provider, and it
only happens when the user actually passes a URL.
"""

from __future__ import annotations

import re

import httpx

from offerprinter.models.schemas import JobDescription

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; OfferPrinter/0.1; +https://github.com/mohitagw15856/offerprinter)"
)


class JDFetchError(RuntimeError):
    """Raised when a job description URL cannot be fetched or parsed."""


def looks_like_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


def _extract_main_text(html: str) -> str:
    """Turn a page of HTML into readable plain text.

    Uses selectolax (a fast C HTML parser). We strip script/style/nav/footer
    noise and collapse whitespace. This is intentionally simple and dependency
    light; for stubborn sites, users can always paste the JD text directly.
    """
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, nav, header, footer, svg, form"):
        tag.decompose()

    # Prefer a <main> or <article> block if present, else fall back to <body>.
    node = tree.css_first("main") or tree.css_first("article") or tree.body
    text = node.text(separator="\n") if node else tree.text(separator="\n")

    # Collapse runs of blank lines and trailing whitespace.
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def fetch_jd_from_url(url: str, timeout: float = 30.0) -> JobDescription:
    """Fetch a URL and extract its job-description text."""
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        raise JDFetchError(f"Could not fetch job URL: {exc}") from exc

    if resp.status_code >= 400:
        raise JDFetchError(f"Job URL returned HTTP {resp.status_code}.")

    text = _extract_main_text(resp.text)
    if len(text) < 100:
        raise JDFetchError(
            "Fetched the page but found very little text. The site may require "
            "JavaScript or block bots — please paste the job description instead."
        )
    return JobDescription(text=text, source=url)


def jd_from_text(text: str) -> JobDescription:
    if not text.strip():
        raise JDFetchError("The pasted job description is empty.")
    return JobDescription(text=text.strip(), source="pasted")


def load_job_description(value: str, timeout: float = 30.0) -> JobDescription:
    """Accept either a URL or pasted text and return a JobDescription."""
    if looks_like_url(value):
        return fetch_jd_from_url(value.strip(), timeout=timeout)
    return jd_from_text(value)
