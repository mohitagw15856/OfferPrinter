"""Strip personal identifiers before the LLM call, and put them back after.

OfferPrinter's pitch is that your CV only ever goes to the provider you chose.
Redaction goes one step further: the provider never learns *who you are*. Your
name, email, phone number, address and profile links are swapped for stable
placeholders on the way out, and restored in the generated documents on the way
back. The model still sees every fact it needs — employers, dates, metrics,
skills — just not your identity.

This is deliberately conservative. It only redacts things it can recognise with
high confidence, because a false positive silently mangles the CV, and it never
touches employer names (the model needs those to write anything useful).

Placeholders are of the form ``[[NAME_1]]`` — bracketed, uppercase and numbered,
which models reproduce verbatim far more reliably than invented pseudonyms.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# --- patterns ----------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

#: International-ish phone numbers: optional +, then 9-15 digits with separators.
_PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,5}[\s.-]?\d{3,4}[\s.-]?\d{0,4}(?![\w.])"
)

_URL_RE = re.compile(r"\bhttps?://[^\s)>\]]+|(?:www\.|linkedin\.com/|github\.com/)[^\s)>\],]+")

#: A UK postcode or a US ZIP, which are the address fragments most likely to
#: appear on a CV and are unambiguous enough to swap safely.
_POSTCODE_RE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}|\d{5}(?:-\d{4})?)\b", re.IGNORECASE
)

#: Words that disqualify a line from being read as the candidate's name.
_NOT_A_NAME = {
    "curriculum",
    "vitae",
    "resume",
    "résumé",
    "cv",
    "profile",
    "summary",
    "contact",
    "experience",
    "education",
    "skills",
}

#: Minimum digits before we believe a number is a phone number rather than a
#: metric like "increased revenue 1200".
_MIN_PHONE_DIGITS = 9


class Redaction(BaseModel):
    """The mapping needed to reverse a redaction."""

    mapping: dict[str, str] = Field(default_factory=dict)  # placeholder -> original

    @property
    def count(self) -> int:
        return len(self.mapping)

    def restore(self, text: str) -> str:
        """Put every original value back. Longest placeholders first."""
        for placeholder in sorted(self.mapping, key=len, reverse=True):
            text = text.replace(placeholder, self.mapping[placeholder])
        return text

    def kinds(self) -> dict[str, int]:
        """Count of redactions by kind, for reporting."""
        counts: dict[str, int] = {}
        for placeholder in self.mapping:
            kind = placeholder.strip("[]").rsplit("_", 1)[0].lower()
            counts[kind] = counts.get(kind, 0) + 1
        return counts


def guess_name(cv_text: str) -> str | None:
    """Best-effort: the candidate's name is usually the first real line.

    Returns None rather than guessing wildly — an unredacted name is a smaller
    problem than a CV with a random capitalised word replaced throughout.
    """
    for raw_line in cv_text.splitlines()[:8]:
        line = raw_line.strip().lstrip("#").strip()
        if not line or len(line) > 60:
            continue
        if any(word in line.lower() for word in _NOT_A_NAME):
            continue
        if _EMAIL_RE.search(line) or _URL_RE.search(line):
            continue
        words = [w for w in re.split(r"[\s,|·•]+", line) if w]
        if not 2 <= len(words) <= 4:
            continue
        # Every word should look like a name: capitalised, mostly letters.
        if all(re.fullmatch(r"[A-Z][\w'’-]{1,}\.?", w) for w in words):
            return " ".join(words)
    return None


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


class Redactor:
    """Replaces identifying details with placeholders, and back again."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name
        self._counters: dict[str, int] = {}
        self.redaction = Redaction()

    def _placeholder(self, kind: str, original: str) -> str:
        # Reuse the same placeholder for a repeated value, so the model sees a
        # consistent identity rather than three different fake people.
        for existing, value in self.redaction.mapping.items():
            if value == original and existing.startswith(f"[[{kind}_"):
                return existing
        self._counters[kind] = self._counters.get(kind, 0) + 1
        placeholder = f"[[{kind}_{self._counters[kind]}]]"
        self.redaction.mapping[placeholder] = original
        return placeholder

    def redact(self, text: str) -> str:
        """Return `text` with identifiers replaced by placeholders."""
        # Name first: it is the value most likely to also appear inside other
        # fields (an email built from the name, a personal site).
        name = self.name or guess_name(text)
        if name:
            self.name = name
            # Placeholders are created lazily inside the callback so that a
            # pattern which never matches does not register an unused mapping.
            text = re.sub(
                rf"\b{re.escape(name)}\b",
                lambda m: self._placeholder("NAME", m.group(0)),
                text,
            )
            # Then the bare first and last names, where they stand alone.
            for part in name.split():
                if len(part) > 2:
                    text = re.sub(
                        rf"\b{re.escape(part)}\b",
                        lambda m: self._placeholder("NAME", m.group(0)),
                        text,
                    )

        text = _EMAIL_RE.sub(lambda m: self._placeholder("EMAIL", m.group(0)), text)
        text = _URL_RE.sub(lambda m: self._placeholder("LINK", m.group(0)), text)
        text = _POSTCODE_RE.sub(lambda m: self._placeholder("POSTCODE", m.group(0)), text)

        def phone_sub(match: re.Match[str]) -> str:
            raw = match.group(0)
            if len(_digits(raw)) < _MIN_PHONE_DIGITS:
                return raw  # a metric, a year range, a salary — leave it alone
            return self._placeholder("PHONE", raw)

        text = _PHONE_RE.sub(phone_sub, text)
        return text

    def restore(self, text: str) -> str:
        return self.redaction.restore(text)


def redact_cv(cv_text: str) -> tuple[str, Redactor]:
    """Convenience wrapper: redact a CV and hand back the reversing object."""
    redactor = Redactor()
    return redactor.redact(cv_text), redactor
