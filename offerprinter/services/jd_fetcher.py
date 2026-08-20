"""Load a job description from a URL, the clipboard, or pasted text.

URL fetching is the only outbound network call besides the LLM provider, and it
only happens when the user actually passes a URL.

Job boards are actively hostile to this, so extraction tries hardest first:

1. **schema.org JobPosting JSON-LD.** A surprising number of boards — Greenhouse,
   Lever, Workday, and anything that wants a Google Jobs listing — embed the
   whole advert as structured data. When it is there it is cleaner than anything
   scraped from the DOM, and it hands us the company and title for free.
2. **The readable body**, with navigation and boilerplate stripped.

When both fail there is `--jd-clipboard`, which is the honest answer for
JavaScript-rendered boards: the text is already on your screen, so copy it.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys

import httpx

from offerprinter.models.schemas import JobDescription

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; OfferPrinter/0.3; +https://github.com/mohitagw15856/OfferPrinter)"
)

#: Minimum characters before we believe we actually got the advert.
_MIN_USEFUL_TEXT = 100


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


def _strip_html(fragment: str) -> str:
    """JSON-LD job descriptions are usually HTML inside a JSON string."""
    text = re.sub(r"<(br|/p|/li|/div|/h[1-6])\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ln for ln in lines if ln)).strip()


def _walk_json(node: object):
    """Yield every dict in an arbitrarily nested JSON structure."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def extract_job_posting(html_text: str) -> tuple[str, str, str] | None:
    """Return (description, company, role) from schema.org JSON-LD, if present.

    This is the highest-quality source available: it is the advert as the
    employer's own ATS published it, without the page furniture.
    """
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for node in _walk_json(payload):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if not any(str(t).lower() == "jobposting" for t in types if t):
                continue

            description = _strip_html(str(node.get("description") or ""))
            if len(description) < _MIN_USEFUL_TEXT:
                continue

            org = node.get("hiringOrganization")
            company = ""
            if isinstance(org, dict):
                company = str(org.get("name") or "")
            elif isinstance(org, str):
                company = org

            role = str(node.get("title") or "")
            return description, company.strip(), role.strip()
    return None


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

    # Structured data first: it is cleaner, and it names the company and role.
    posting = extract_job_posting(resp.text)
    if posting is not None:
        description, company, role = posting
        return JobDescription(text=description, source=url, company=company, role=role)

    text = _extract_main_text(resp.text)
    if len(text) < _MIN_USEFUL_TEXT:
        raise JDFetchError(
            "Fetched the page but found very little text. The site may require "
            "JavaScript or block bots.\n"
            "The advert is already on your screen, so the quickest fix is to copy "
            "it and run again with --jd-clipboard."
        )
    return JobDescription(text=text, source=url)


def jd_from_text(text: str) -> JobDescription:
    if not text.strip():
        raise JDFetchError("The pasted job description is empty.")
    return JobDescription(text=text.strip(), source="pasted")


def read_clipboard() -> str:
    """Return the current clipboard contents, cross-platform, with no dependency.

    Shelling out to the platform's own tool beats adding a dependency for one
    feature, and it degrades to a clear error message when the tool is missing
    (headless Linux without xclip, typically).
    """
    if sys.platform == "darwin":
        commands = [["pbpaste"]]
    elif sys.platform == "win32":  # pragma: no cover - exercised on Windows only
        commands = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    else:
        commands = [
            ["wl-paste", "--no-newline"],
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]

    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise JDFetchError(f"Could not read the clipboard: {exc}") from exc
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    tools = ", ".join(c[0] for c in commands)
    raise JDFetchError(
        f"Could not read the clipboard (tried: {tools}). "
        "Paste the job description with --jd instead."
    )


def jd_from_clipboard() -> JobDescription:
    """Load the job description straight from the clipboard."""
    text = read_clipboard()
    if not text.strip():
        raise JDFetchError("The clipboard is empty — copy the job advert first.")
    return JobDescription(text=text.strip(), source="clipboard")


def load_job_description(value: str, timeout: float = 30.0) -> JobDescription:
    """Accept either a URL or pasted text and return a JobDescription."""
    if looks_like_url(value):
        return fetch_jd_from_url(value.strip(), timeout=timeout)
    return jd_from_text(value)
