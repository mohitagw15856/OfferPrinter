"""Prompt templates, kept in their own module so they are easy to audit and improve.

Every generation prompt inherits the same non-negotiable system rules (see
`SYSTEM_RULES`), the most important of which is: NEVER fabricate. If you want to
change how OfferPrinter writes, this is the only file you need to touch.
"""

from offerprinter.prompts.templates import (
    ATS_REPORT_PROMPT,
    COVER_LETTER_PROMPT,
    EXTRACT_META_PROMPT,
    FIT_MEMO_PROMPT,
    INTERVIEW_PREP_PROMPT,
    SYSTEM_RULES,
    TAILORED_CV_PROMPT,
    build_system,
)

__all__ = [
    "SYSTEM_RULES",
    "build_system",
    "EXTRACT_META_PROMPT",
    "TAILORED_CV_PROMPT",
    "COVER_LETTER_PROMPT",
    "FIT_MEMO_PROMPT",
    "ATS_REPORT_PROMPT",
    "INTERVIEW_PREP_PROMPT",
]
