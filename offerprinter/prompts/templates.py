"""All prompt templates for OfferPrinter.

Design notes:
- Each artifact has ONE user-prompt template. They all share `SYSTEM_RULES`.
- Templates use ``{cv}``, ``{jd}``, ``{company}``, ``{role}`` placeholders and are
  filled with ``str.format`` by the generator service.
- The no-fabrication rule is repeated in every prompt on purpose. It is the
  product's core promise and models follow instructions they see close to the task.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared system rules — the trust guarantee.
# ---------------------------------------------------------------------------

SYSTEM_RULES = """You are OfferPrinter, an assistant that tailors a person's real \
job-application materials to a specific role. You write in {locale_name} English \
({locale_note}).

ABSOLUTE, NON-NEGOTIABLE RULES:
1. NEVER fabricate. Do not invent experience, skills, employers, job titles, \
dates, qualifications, certifications, publications, or metrics. You may ONLY \
reframe, reorder, reword, and surface facts that are actually present in the \
candidate's CV.
2. If the role wants something the candidate does not have, DO NOT pretend they \
have it. Where the artifact calls for honesty about gaps (the fit memo, the ATS \
report), state the gap plainly. Elsewhere, simply omit what isn't there.
3. Numbers and metrics must come verbatim from the CV. If the CV says "led a team \
of 4", never write "a team of 10". If no metric is given, do not invent one.
4. Keep the candidate's real voice and seniority. Do not inflate titles.
5. Output clean, ATS-friendly text: no tables, no columns, no images, no text \
boxes, no fancy characters. Use plain Markdown headings and simple bullet points.

You will be given the candidate's CV and a target job description. Follow the \
task instructions exactly and return ONLY the requested document in Markdown, \
with no preamble, no explanation, and no code fences."""

_LOCALE_NOTES = {
    "UK": ("British", "e.g. 'organise', 'programme', 'CV', 'colour', DD/MM/YYYY dates"),
    "US": ("American", "e.g. 'organize', 'program', 'resume', 'color', MM/DD/YYYY dates"),
}


def build_system(locale: str) -> str:
    """Return the shared system prompt localised to UK or US English."""
    name, note = _LOCALE_NOTES.get(locale, _LOCALE_NOTES["UK"])
    return SYSTEM_RULES.format(locale_name=name, locale_note=note)


# ---------------------------------------------------------------------------
# Metadata extraction — pull company + role so we can name the output folder.
# ---------------------------------------------------------------------------

EXTRACT_META_PROMPT = """From the job description below, identify the hiring \
company's name and the job title.

Return ONLY a single line of the exact form:
COMPANY: <name> | ROLE: <title>

If the company name is genuinely not stated, use "Company". If the role is not \
stated, use "Role". Do not add anything else.

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 1. Tailored CV
# ---------------------------------------------------------------------------

TAILORED_CV_PROMPT = """Produce a TAILORED CV for this candidate targeting the \
role of {role} at {company}.

What "tailored" means here:
- Reorder and reword the candidate's REAL experience so the most role-relevant \
things come first and are described in the language the job description uses.
- Foreground the skills, projects and achievements that match this job. \
De-emphasise (but don't delete truthful, relevant) the rest.
- Mirror the job's terminology where it truthfully applies to the candidate's \
experience (helps with ATS keyword matching) — but only where it is genuinely true.
- Keep every fact, employer, date and metric exactly as in the source CV.

Format (ATS-friendly, plain Markdown):
# <Candidate Name>
<contact line: email · phone · location · links — copy from the CV; omit any not present>

## Professional Summary
A 2–4 sentence summary aimed squarely at this role, built only from real facts.

## Core Skills
A simple comma or bullet list of the candidate's real skills most relevant to the role.

## Experience
For each role (most relevant / recent first): title, employer, dates, then 3–6 \
bullet points rewritten to highlight impact relevant to {role}. Keep real metrics.

## Education
As in the source CV.

## (Optional) Certifications / Projects
Only if present in the source CV.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 2. Cover letter
# ---------------------------------------------------------------------------

COVER_LETTER_PROMPT = """Write a TAILORED COVER LETTER for the candidate applying \
to {role} at {company}.

Requirements:
- Specific to THIS company and role. No generic filler, no clichés \
("I am writing to express my interest..."), no flattery that could apply anywhere.
- Open with a concrete hook tied to the role or company and the candidate's most \
relevant real strength.
- 3–4 short paragraphs. In the body, connect the candidate's actual experience to \
2–3 of the job's key needs, using real examples and metrics from the CV.
- Confident but honest. Do not claim experience the candidate lacks.
- Around 250–350 words. Sign off with the candidate's real name.

Format as plain Markdown. Use the candidate's real contact details at the top if \
present in the CV; otherwise start at the greeting. If you do not know the hiring \
manager's name, use "Dear Hiring Team,".

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 3. Fit memo
# ---------------------------------------------------------------------------

FIT_MEMO_PROMPT = """Write a one-page "WHY I FIT" FIT MEMO for the candidate and \
the role of {role} at {company}.

This document is where honesty about gaps is REQUIRED. Structure it exactly:

# Fit Memo — {role} at {company}

## Snapshot
2–3 sentences: the candidate's honest overall fit for this role.

## Requirement-by-requirement
Identify the key requirements from the job description. For EACH one, write a row \
in this format:
- **<the requirement>** — <Strong match | Partial match | Gap>: <one sentence of \
evidence drawn ONLY from the CV, or a plain statement that the CV does not show it>.

Be scrupulously honest. If the CV shows no evidence for a requirement, mark it \
**Gap** and say so. Do not invent evidence to fill a gap.

## Honest gaps & how to talk about them
List the real gaps and, for each, a truthful, non-defensive way the candidate \
could address it in an interview (transferable experience, willingness to learn, \
adjacent skills) — WITHOUT claiming they already have the missing skill.

## Bottom line
One or two sentences on overall suitability.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 4. ATS keyword report
# ---------------------------------------------------------------------------

ATS_REPORT_PROMPT = """Produce an ATS KEYWORD REPORT comparing the candidate's CV \
against the job description for {role} at {company}.

Steps:
1. Extract the important keywords and key phrases an Applicant Tracking System \
would likely screen for from the job description (skills, tools, methods, \
qualifications, domain terms). Aim for 12–20.
2. For each, decide whether the candidate's CV already covers it.

Format exactly:

# ATS Keyword Report — {role} at {company}

## Covered keywords
A bullet list of the job's key terms the CV already contains (quote the CV phrase \
where helpful).

## Missing keywords
A bullet list of key terms NOT found in the CV.

## How to add the missing terms — truthfully
For each missing keyword that the candidate PLAUSIBLY has real experience with \
(based on the CV), suggest exactly where and how to add it truthfully (e.g. \
"You list 'built dashboards' — if you used Tableau, name it in that bullet"). \
For any missing keyword the candidate clearly does NOT have, say plainly: \
"Do not add — no evidence in your CV. This is a genuine gap." NEVER instruct the \
candidate to claim something untrue.

## Coverage summary
"Covered X of Y key terms." with the two numbers.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 5. Interview prep pack
# ---------------------------------------------------------------------------

INTERVIEW_PREP_PROMPT = """Produce an INTERVIEW PREP PACK for the candidate \
interviewing for {role} at {company}.

Format exactly:

# Interview Prep Pack — {role} at {company}

## Likely questions
8–10 questions this candidate is likely to be asked for THIS role (mix of \
behavioural, role-specific/technical, and motivation).

## STAR answer scaffolds
Pick the 4–5 most important behavioural/experience questions. For each, give a \
STAR scaffold (Situation, Task, Action, Result) built ONLY from the candidate's \
real experience in the CV. Where a strong real example exists, use it. Where the \
CV lacks a directly relevant example, say so honestly and suggest the closest \
real experience to adapt — do not invent a scenario.

## 5 smart questions to ask them
Five thoughtful, specific questions the candidate should ask the interviewer \
about the role, team, or company — showing genuine engagement, not generic.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 6. Fit score — a single number, so a run ends with a verdict, not a shrug.
# ---------------------------------------------------------------------------

FIT_SCORE_PROMPT = """Score how well this candidate genuinely matches the role of \
{role} at {company}.

Scoring guide (be strict and evidence-based — an inflated score is useless):
- 85-100: meets essentially every requirement with direct, demonstrated evidence.
- 70-84: meets most requirements including the critical ones; one or two soft gaps.
- 55-69: meets roughly half; credible but with real gaps on secondary requirements.
- 40-54: meets a minority; a genuine stretch with gaps on important requirements.
- 0-39: missing most requirements, including critical ones.

Judge ONLY on evidence actually present in the CV. Absence of evidence is a gap, \
not a maybe. Do not be generous to be kind — the candidate needs the truth to \
decide where to spend their evening.

Return ONLY this exact block, nothing else, no code fences, no commentary:

SCORE: <integer 0-100>
STRENGTHS: <requirement they genuinely meet> ; <another> ; <another>
GAPS: <requirement they genuinely do not meet> ; <another>

Give 2-4 strengths and 0-4 gaps, each a short phrase of at most 12 words, \
separated by semicolons. If there are genuinely no gaps, write "GAPS: none".

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- TARGET JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""


# ---------------------------------------------------------------------------
# 7. Roast mode — optional, opt-in, and still never dishonest.
# ---------------------------------------------------------------------------

ROAST_PROMPT = """Roast this CV. The candidate has explicitly asked for blunt, \
funny, unsparing feedback — they opted in, so do not soften it into a compliment \
sandwich.

Rules that still apply (roasting is not licence to be wrong or cruel):
- Roast the WRITING, never the person, their background, or their circumstances.
- Every jab must be about something actually in the CV. Do not invent flaws.
- Punch at clichés, vagueness, buzzwords, unquantified claims, wall-of-text \
formatting, "responsible for" bullets, and anything that says nothing.
- Nothing about protected characteristics, age, nationality, or career breaks.
- End genuinely useful. The point is a better CV, not a worse mood.

Format exactly:

# 🔥 CV Roast

## The verdict in one line
One brutal but fair sentence.

## What made me wince
4-6 bullets. Each: quote the offending phrase from the CV, then say why it is \
doing nothing for them. Be funny. Be specific.

## Cliché count
List the buzzwords and dead phrases you found, with a count. Crown the worst one.

## Credit where it's due
2-3 bullets on what genuinely works. Do not invent praise — if something is good, \
say why it is good.

## The five fixes that would actually change the outcome
A numbered list of 5 concrete, specific edits, in priority order. Name the exact \
bullet or section to change and what to change it to.

--- CANDIDATE CV ---
{cv}
--- END CV ---"""


# ---------------------------------------------------------------------------
# 8. Follow-up messages — the job hunt does not end at "submit".
# ---------------------------------------------------------------------------

_FOLLOWUP_RULES = """You are writing a short message on the candidate's behalf. \
The same absolute rules apply: use ONLY facts from their CV and the conversation \
notes they give you. Never invent a detail of a conversation that did not happen, \
never claim a skill they lack, and never put words in the interviewer's mouth.

Write plainly. No "I am reaching out", no "I wanted to circle back", no flattery \
that could be sent to any company. Short is better than long — this is a message \
someone reads on their phone between meetings."""

THANK_YOU_PROMPT = (
    _FOLLOWUP_RULES
    + """

Write a THANK-YOU EMAIL after an interview for {role} at {company}.

Structure:
- Subject line.
- One sentence of genuine thanks, naming something specific that was discussed \
(use the notes below; if the notes are empty, keep it general rather than inventing).
- One short paragraph reinforcing the single strongest reason they fit, drawn \
from their real CV.
- If the notes mention a question the candidate answered poorly or incompletely, \
one or two sentences answering it better — this is the highest-value part.
- One line confirming continued interest and offering to provide anything further.

120-200 words total. Sign with the candidate's real name.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---

--- NOTES FROM THE CONVERSATION (may be empty) ---
{notes}
--- END NOTES ---"""
)

RECRUITER_PROMPT = (
    _FOLLOWUP_RULES
    + """

Write a SHORT MESSAGE TO A RECRUITER OR HIRING MANAGER about {role} at {company}, \
before or alongside applying.

Structure:
- Subject line.
- One sentence saying which role and that they have applied (or are about to).
- Two or three sentences on the most role-relevant real experience, with one \
concrete metric from the CV.
- One sentence inviting a short conversation.

Under 150 words. This is a cold-ish message: earn the reply, do not demand it.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---

--- NOTES (may be empty) ---
{notes}
--- END NOTES ---"""
)

LINKEDIN_PROMPT = (
    _FOLLOWUP_RULES
    + """

Write a LINKEDIN CONNECTION NOTE to someone at {company} about {role}.

Hard constraint: **300 characters maximum**, including spaces. LinkedIn will \
truncate anything longer. No subject line, no sign-off, no links.

Say who they are, one specific true thing that connects them to this role, and \
what they are asking for. Warm, direct, not fawning.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---

--- NOTES (may be empty) ---
{notes}
--- END NOTES ---"""
)

NUDGE_PROMPT = (
    _FOLLOWUP_RULES
    + """

Write a POLITE FOLLOW-UP NUDGE for {role} at {company}, sent because the \
candidate has heard nothing back.

Structure:
- Subject line that references the role, not "following up".
- One sentence noting when they applied or last spoke (use the notes; if unknown, \
say "recently" rather than inventing a date).
- One sentence of new, genuine value — a relevant thing they have done since, or \
the single strongest point from their CV restated briefly.
- One sentence asking about timelines, making it easy to reply with one line.

Under 120 words. Warm, brief, zero guilt-tripping. Assume the reader is busy and \
not ignoring them on purpose.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---

--- NOTES (may be empty) ---
{notes}
--- END NOTES ---"""
)


# ---------------------------------------------------------------------------
# 9. Interview practice — an interactive rehearsal, not another document.
# ---------------------------------------------------------------------------

PRACTICE_QUESTION_PROMPT = """You are interviewing this candidate for {role} at \
{company}. Ask ONE interview question and nothing else.

Question number {number} of {total}. Vary the type across the set: behavioural, \
role-specific/technical, and motivation. Ask what a real interviewer for THIS role \
would actually ask, informed by the job description and the candidate's background.

Questions already asked (do not repeat or closely echo them):
{asked}

Return ONLY the question text. No preamble, no numbering, no quotation marks.

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""

PRACTICE_FEEDBACK_PROMPT = """Critique the candidate's practice answer below.

Be a good interview coach: specific, honest, and useful. Do not be gentle to the \
point of uselessness, and do not be harsh for its own sake.

Judge the answer on:
- Does it actually answer the question that was asked?
- Is it concrete? Does it use a real example with a real outcome?
- Is it structured (situation, action, result) or does it wander?
- Is it the right length for an interview — roughly 60-120 seconds spoken?
- Does it connect to what THIS role needs?

Critical rule: any improvement you suggest must be grounded in the candidate's \
REAL CV below. Never coach them to claim experience they do not have. If their \
answer is weak because they genuinely lack the experience, say so and suggest \
the closest true thing they could say instead.

Format exactly:

**Score: X/10**

**What worked**
- one or two bullets, specific to what they actually said

**What to fix**
- two or three bullets, each naming the exact problem and the fix

**A stronger version of your answer**
A short rewritten answer, 80-140 words, built ONLY from facts in their CV. Write \
it in their voice, first person, as they would say it aloud.

--- THE QUESTION ---
{question}

--- THE CANDIDATE'S ANSWER ---
{answer}

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---"""

PRACTICE_SUMMARY_PROMPT = """Summarise this interview practice session for the \
candidate, for {role} at {company}.

Format exactly:

# Practice Session Summary

## How it went
Two or three sentences, honest, on the overall standard of the answers.

## Patterns worth fixing
The 2-4 habits that showed up more than once across answers — not one-off issues.

## Your three strongest stories
The examples from their answers (and CV) that landed best and should be reused. \
Name them so they are easy to recall under pressure.

## Before the real interview
A short checklist of 3-5 concrete things to do.

Base everything on the transcript below and the candidate's real CV. Do not invent \
experience or praise that the transcript does not support.

--- TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---

--- CANDIDATE CV ---
{cv}
--- END CV ---"""


# ---------------------------------------------------------------------------
# 10. Evaluation judge — used by the eval harness, never in a normal run.
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are grading the output of a job-application tool. Be a \
strict, fair examiner: this grade is used to decide whether a prompt change made \
the tool better or worse, so generosity is actively harmful.

Grade the {artifact_name} below on each dimension, 1-5:

1. **grounding** — is every factual claim traceable to the candidate's CV? \
A single invented employer, date, metric or skill caps this at 1.
2. **specificity** — is it about THIS candidate and THIS role, or could it be \
sent by anyone to anyone? Generic filler scores low.
3. **honesty** — where the candidate does not meet a requirement, is that stated \
plainly rather than glossed over or quietly omitted where the format calls for it?
4. **usefulness** — would this genuinely help the candidate get an interview?
5. **format** — does it follow the structure the tool asked for, and is it \
clean ATS-friendly Markdown?

Return ONLY this block, nothing else:

GROUNDING: <1-5>
SPECIFICITY: <1-5>
HONESTY: <1-5>
USEFULNESS: <1-5>
FORMAT: <1-5>
NOTES: <one sentence, the single most important thing to fix>

--- CANDIDATE CV ---
{cv}
--- END CV ---

--- JOB DESCRIPTION ---
{jd}
--- END JOB DESCRIPTION ---

--- GENERATED {artifact_name} ---
{artifact}
--- END GENERATED {artifact_name} ---"""
