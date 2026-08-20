"""Check generated documents against the source CV.

This module is what makes the no-fabrication guarantee testable. Everywhere
else in OfferPrinter, "never invent anything" is an instruction in a prompt —
a request the model is very likely, but not guaranteed, to honour. Here it
becomes an assertion: every number, date and named entity in the tailored CV
and cover letter must be traceable to something the candidate actually wrote.

The design bias is **specificity over recall**. A checker that cries wolf on
every third bullet gets switched off within a week and protects nobody, so
anything ambiguous is deliberately not flagged. What survives the filters is
worth a human's attention:

* **Numbers and dates** are checked strictly. "Led a team of 4" must not become
  "a team of 10", and a job that started in 2019 must not start in 2017.
* **Named entities** — employers, tools, certifications, places — must appear in
  the CV. The cover letter may additionally draw on the job advert, because
  naming the employer you are writing to is not a claim about your experience;
  the tailored CV may not, because that is where borrowed vocabulary turns into
  a borrowed credential.
* **Keywords the ATS report itself flagged as gaps** must not then appear in the
  tailored CV. This needs no heuristics at all — the package would simply be
  contradicting itself — and it catches lowercase tool names like "dbt" that
  never look like proper nouns.

What it cannot do is catch a fluent paraphrase that changes meaning without
changing any token. It narrows the gap; it does not close it, and the report
says so.
"""

from __future__ import annotations

import re

from offerprinter.models.schemas import (
    ApplicationPackage,
    Finding,
    JobDescription,
    ResumeInput,
    Severity,
    Verification,
)

#: Only these artifacts make first-person factual claims about the candidate.
#: The fit memo, ATS report and interview pack quote the job description on
#: purpose, so checking them would be all false positives.
VERIFIED_ARTIFACTS = ("tailored_cv", "cover_letter")

# --- token extraction --------------------------------------------------------

#: Numbers, including percentages, currency, decimals and thousands separators.
_NUMBER_RE = re.compile(r"[£$€]?\d[\d,.]*\s?(?:%|k\b|m\b|bn\b)?", re.IGNORECASE)

#: Four-digit years, and month-year pairs.
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

#: A capitalised word or run of words: candidate proper nouns. The inner
#: separator is spaces and tabs only — \s+ would let an "entity" span a line
#: break and glue the end of one sentence to the start of the next.
_ENTITY_RE = re.compile(r"\b[A-Z][\w&.+-]*(?:[ \t]+[A-Z][\w&.+-]*)*\b")

#: Sentence-initial capitals are grammar, not evidence, so ignore a capitalised
#: word that directly follows a full stop, newline, bullet or heading marker.
#: `[-*#>]*` rather than `?`, so a level-two heading ("## Missing keywords")
#: counts as a sentence start just as a level-one heading does.
_SENTENCE_START_RE = re.compile(r"(?:^[ \t]*[-*#>]*[ \t]*|[.!?:;]\s+|\n[ \t]*[-*#>]*[ \t]*)$")

#: Common words that are capitalised for grammar or convention, plus the
#: scaffolding OfferPrinter's own templates emit.
# fmt: off
# Kept compact on purpose: one word per line would add ~180 lines of noise
# to a file whose logic is the interesting part.
_STOPWORDS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "present", "current", "professional", "summary",
    "core", "skills", "experience", "education", "certifications", "projects", "dear",
    "hiring", "team", "manager", "sincerely", "regards", "yours", "faithfully", "kind",
    "best", "cv", "resume", "curriculum", "vitae", "contact", "profile", "achievements",
    "responsibilities", "role", "position", "company", "employer", "references", "available",
    "request", "the", "this", "that", "these", "those", "there", "here", "it", "its",
    "as", "at", "in", "on", "of", "for", "with", "and", "or", "but", "if", "when", "while",
    "after", "before", "during", "i", "my", "me", "we", "our", "you", "your", "they",
    "their", "he", "she", "his", "her", "a", "an", "to", "from", "by", "up", "down",
    "over", "under", "again", "further", "then", "once", "having", "had", "has", "have",
    "been", "being", "was", "were", "am", "are", "is", "be", "do", "does", "did", "will",
    "would", "should", "could", "might", "must", "can", "so", "than", "too", "very",
    "just", "also", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "what", "which", "who", "whom", "why",
    "how", "all", "any", "because", "between", "into", "through", "about", "against",
    "above", "below", "throughout", "within", "across", "alongside", "led", "built",
    "designed", "delivered", "managed", "owned", "created", "worked", "using",
}
# fmt: on

#: A capitalised token this short is almost always an initial or an artefact.
_MIN_ENTITY_LENGTH = 3


def _normalise(text: str) -> str:
    """Lowercase and collapse punctuation so comparisons are about substance."""
    text = text.lower()
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^\w\s%£$€.+#-]", " ", text)
    return re.sub(r"\s+", " ", text)


def _normalise_number(raw: str) -> str:
    """Reduce a number to comparable digits, dropping separators and symbols."""
    cleaned = raw.strip().lower().rstrip(".")
    cleaned = re.sub(r"[£$€,\s]", "", cleaned)
    return cleaned


def _number_variants(raw: str) -> set[str]:
    """Forms a number might legitimately take in the source CV."""
    base = _normalise_number(raw)
    variants = {base}
    stripped = base.rstrip("%")
    variants.add(stripped)
    # "8%" in output may be written "8 per cent" in the CV, and "1,200" as "1200".
    if stripped.endswith(".0"):
        variants.add(stripped[:-2])
    if "." in stripped:
        variants.add(stripped.split(".")[0])
    # Trailing magnitude suffixes: 30k -> 30
    variants.add(re.sub(r"(k|m|bn)$", "", stripped))
    return {v for v in variants if v}


def _context_for(text: str, index: int, width: int = 90) -> str:
    """The line a match sits on, trimmed, for the report."""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    line = text[start : end if end != -1 else len(text)].strip()
    line = re.sub(r"\s+", " ", line)
    return line[:width] + ("…" if len(line) > width else "")


#: The heading the ATS report prompt is instructed to emit.
_MISSING_SECTION_RE = re.compile(
    r"^##\s*Missing keywords\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


def _parse_missing_keywords(ats_report: str) -> list[str]:
    """Pull the bullet list out of the ATS report's 'Missing keywords' section."""
    match = _MISSING_SECTION_RE.search(ats_report)
    if not match:
        return []

    keywords: list[str] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith(("-", "*")):
            continue
        # Strip only the bullet marker: lstrip("-* ") would also eat the
        # opening ** of a bold keyword and leave the closing one behind.
        item = re.sub(r"^[-*]\s*", "", line).strip()
        item = re.sub(r"\*\*(.+?)\*\*", r"\1", item)  # drop bold markers
        item = item.split("—")[0].split(" - ")[0].strip()  # drop trailing commentary
        # "Product analytics / product metrics" describes one gap two ways.
        for part in re.split(r"\s*/\s*", item):
            part = re.sub(r"\(.*?\)", "", part).strip(" .,:;*")
            if len(part) >= 2:
                keywords.append(part)
    return keywords


def _iter_entities(text: str):
    """Yield (entity, match_start) for capitalised tokens worth checking."""
    for match in _ENTITY_RE.finditer(text):
        entity = match.group(0).strip()
        if len(entity) < _MIN_ENTITY_LENGTH:
            continue
        # At a sentence, heading or bullet start the first word is capitalised
        # by grammar rather than because it names anything ("Used SQL daily"),
        # so drop it and judge what follows. A single word there tells us
        # nothing at all, so it is skipped entirely.
        offset = 0
        if _SENTENCE_START_RE.search(text[: match.start()]):
            head, _, rest = entity.partition(" ")
            if not rest:
                continue
            offset = len(head) + 1
            entity = rest
            if len(entity) < _MIN_ENTITY_LENGTH:
                continue
        if entity.isupper() and len(entity) <= 4:
            continue  # acronyms like SQL, AWS — too generic to attribute
        if all(word.lower() in _STOPWORDS for word in entity.split()):
            continue
        yield entity, match.start() + offset


# --- the checker -------------------------------------------------------------


class Verifier:
    """Checks one generated package against its source CV and job description."""

    def __init__(
        self,
        cv: ResumeInput,
        jd: JobDescription,
        company: str = "",
        role: str = "",
    ) -> None:
        self.cv_text = _normalise(cv.text)
        self.jd_text = _normalise(jd.text)
        # The target company and role are legitimate anywhere: naming the
        # employer you are writing to is not a claim about your experience.
        self.target_text = _normalise(f"{company} {role}")
        self.cv_numbers = {
            variant
            for match in _NUMBER_RE.finditer(cv.text)
            for variant in _number_variants(match.group(0))
        }

    def _number_is_sourced(self, raw: str) -> bool:
        return bool(_number_variants(raw) & self.cv_numbers)

    def _entity_is_sourced(self, entity: str, allow_jd: bool) -> bool:
        """Is this entity traceable to a source the artifact may draw on?

        `allow_jd` is the important distinction. A cover letter may name things
        from the job advert — that is the point of a cover letter. A tailored CV
        may not: it describes the candidate's own history, so a tool or employer
        that appears only in the job description is precisely the fabrication
        this checker exists to catch.
        """
        needle = _normalise(entity).strip()
        if not needle:
            return True

        haystacks = [self.cv_text, self.target_text]
        if allow_jd:
            haystacks.append(self.jd_text)

        if any(needle in hay for hay in haystacks):
            return True
        # A multi-word entity counts as sourced if every word is individually
        # present — "Senior Data Analyst" from "senior analyst, data".
        words = [w for w in needle.split() if w not in _STOPWORDS]
        if words and all(any(w in hay for hay in haystacks) for w in words):
            return True
        return False

    def check_text(self, artifact_key: str, content: str) -> list[Finding]:
        # Only the tailored CV is held to the stricter CV-only standard.
        allow_jd = artifact_key != "tailored_cv"
        findings: list[Finding] = []
        seen: set[tuple[str, str]] = set()

        for match in _NUMBER_RE.finditer(content):
            raw = match.group(0).strip()
            if not any(ch.isdigit() for ch in raw):
                continue
            if _YEAR_RE.fullmatch(raw.strip(".")):
                kind = "date"
            else:
                kind = "number"
            if self._number_is_sourced(raw):
                continue
            token = (kind, _normalise_number(raw))
            if token in seen:
                continue
            seen.add(token)
            findings.append(
                Finding(
                    artifact=artifact_key,
                    claim=raw,
                    kind=kind,
                    severity=Severity.HIGH,
                    context=_context_for(content, match.start()),
                )
            )

        for entity, position in _iter_entities(content):
            if self._entity_is_sourced(entity, allow_jd):
                continue
            token = ("entity", entity.lower())
            if token in seen:
                continue
            seen.add(token)
            findings.append(
                Finding(
                    artifact=artifact_key,
                    claim=entity,
                    kind="entity",
                    severity=Severity.MEDIUM,
                    context=_context_for(content, position),
                )
            )

        return findings

    def check_missing_keywords(self, package: ApplicationPackage) -> list[Finding]:
        """Cross-check the tailored CV against the ATS report's own verdict.

        This is the sharpest check available, because it needs no heuristics
        about what counts as a skill: the ATS report has already decided which
        of the advert's keywords the candidate does *not* have. If one of those
        then appears in the tailored CV, the package contradicts itself, and the
        contradiction is in the direction of claiming something untrue.

        It also catches the cases the entity pass structurally cannot see —
        lowercase tool names like "dbt", "kafka" or "terraform" never look like
        proper nouns.
        """
        ats = package.get("ats_report")
        tailored = package.get("tailored_cv")
        if ats is None or tailored is None:
            return []

        keywords = _parse_missing_keywords(ats.content)
        if not keywords:
            return []

        content = _normalise(tailored.content)
        findings: list[Finding] = []
        for keyword in keywords:
            needle = _normalise(keyword).strip()
            if not needle or needle in self.cv_text:
                continue  # the report and the CV disagree; trust the CV
            if not re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", content):
                continue
            findings.append(
                Finding(
                    artifact="tailored_cv",
                    claim=keyword,
                    kind="ats-gap",
                    severity=Severity.HIGH,
                    context=_context_for(tailored.content, max(content.find(needle), 0)),
                )
            )
        return findings

    def check_package(self, package: ApplicationPackage) -> Verification:
        verification = Verification()
        if package.company or package.role:
            self.target_text = _normalise(f"{package.company} {package.role}")
        for artifact in package.artifacts:
            if artifact.key not in VERIFIED_ARTIFACTS:
                continue
            verification.checked_artifacts.append(artifact.key)
            verification.claims_checked += _countable_claims(artifact.content)
            verification.findings.extend(self.check_text(artifact.key, artifact.content))

        keyword_findings = self.check_missing_keywords(package)
        verification.claims_checked += len(keyword_findings)
        verification.findings.extend(keyword_findings)
        return verification


def _countable_claims(content: str) -> int:
    """How many claims were actually examined, for an honest denominator."""
    numbers = sum(1 for m in _NUMBER_RE.finditer(content) if any(c.isdigit() for c in m.group(0)))
    entities = sum(1 for _ in _iter_entities(content))
    return numbers + entities


def verify_package(
    package: ApplicationPackage, cv: ResumeInput, jd: JobDescription
) -> Verification:
    """Check a generated package. The one-call entry point."""
    return Verifier(cv, jd, package.company, package.role).check_package(package)
