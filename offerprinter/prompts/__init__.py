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
    FIT_SCORE_PROMPT,
    INTERVIEW_PREP_PROMPT,
    JUDGE_PROMPT,
    LINKEDIN_PROMPT,
    NUDGE_PROMPT,
    PRACTICE_FEEDBACK_PROMPT,
    PRACTICE_QUESTION_PROMPT,
    PRACTICE_SUMMARY_PROMPT,
    RECRUITER_PROMPT,
    ROAST_PROMPT,
    SYSTEM_RULES,
    TAILORED_CV_PROMPT,
    THANK_YOU_PROMPT,
    build_system,
)

#: Follow-up message kinds, in the order they occur during a job hunt.
FOLLOWUP_PROMPTS: dict[str, tuple[str, str, str]] = {
    # key: (human title, base filename, prompt)
    "recruiter": ("Recruiter Message", "recruiter-message", RECRUITER_PROMPT),
    "thank-you": ("Thank-You Email", "thank-you-email", THANK_YOU_PROMPT),
    "linkedin": ("LinkedIn Note", "linkedin-note", LINKEDIN_PROMPT),
    "nudge": ("Follow-Up Nudge", "follow-up-nudge", NUDGE_PROMPT),
}

__all__ = [
    "SYSTEM_RULES",
    "build_system",
    "EXTRACT_META_PROMPT",
    "TAILORED_CV_PROMPT",
    "COVER_LETTER_PROMPT",
    "FIT_MEMO_PROMPT",
    "ATS_REPORT_PROMPT",
    "INTERVIEW_PREP_PROMPT",
    "FIT_SCORE_PROMPT",
    "ROAST_PROMPT",
    "THANK_YOU_PROMPT",
    "RECRUITER_PROMPT",
    "LINKEDIN_PROMPT",
    "NUDGE_PROMPT",
    "FOLLOWUP_PROMPTS",
    "PRACTICE_QUESTION_PROMPT",
    "PRACTICE_FEEDBACK_PROMPT",
    "PRACTICE_SUMMARY_PROMPT",
    "JUDGE_PROMPT",
]
