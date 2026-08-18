---
name: offerprinter
description: >-
  Print a complete, tailored job-application package from one CV and one job
  description. Use when a user wants to apply to a specific role and has (or can
  paste) their CV plus the job description or its URL. Produces a tailored CV, a
  cover letter, a one-page fit memo, an ATS keyword report, and an interview prep
  pack — all written only from facts in the user's real CV, nothing fabricated.
---

# OfferPrinter — one input → full application package

**Verb the thing.** Turn one CV and one job description into a full, tailored,
ready-to-review application package.

**Use when** the user is applying to a specific role and can supply (a) their base
CV/resume and (b) the target job description (pasted text or a URL). Do not use for
generic "improve my CV" requests with no target role.

**Produces**, in `output/<company>-<role>/` as `.md` and `.docx` plus a combined
`full-package.md`:
1. `tailored-cv` — the user's real CV, reordered and reworded for this role (ATS-friendly).
2. `cover-letter` — specific to the company and role, no generic filler.
3. `fit-memo` — maps the user's real experience to each key requirement and honestly flags gaps.
4. `ats-keyword-report` — job keywords the CV covers, which are missing, and where to add missing ones truthfully.
5. `interview-prep-pack` — likely questions, STAR scaffolds from the user's real experience, and 5 questions to ask.

## Required inputs
- **CV** — a path to a `.pdf`, `.docx`, `.md`, or `.txt` file, OR the CV pasted as text.
- **Job description** — a URL to fetch, OR the JD pasted as text.
- **An LLM API key** — for the configured provider (Anthropic by default). Read
  from `config.toml` or an environment variable; never invent one.

## The one non-negotiable rule
**Never fabricate.** Only reframe facts that are actually in the user's CV. Do not
invent experience, skills, employers, dates, titles, certifications, or metrics. If
the role needs something the user lacks, the fit memo and ATS report must say so
plainly. This is the tool's core guarantee — honour it in any manual edits too.

## How to run it

Preferred — the CLI does the whole flow in one command:

```bash
python cli.py --cv path/to/cv.pdf --jd "https://careers.example.com/123"
# or, with the JD in a file / pasted text:
python cli.py --cv path/to/cv.docx --jd-file jd.txt
```

Switch provider or locale inline if asked:

```bash
python cli.py --cv cv.md --jd-file jd.txt --provider openai --locale US
```

Programmatic use (if you're driving it from code rather than the CLI):

```python
from offerprinter.config import load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.services.cv_parser import extract_cv  # or cv_from_text
from offerprinter.services.jd_fetcher import load_job_description

cfg = load_config()  # reads config.toml + env vars
cv = extract_cv("cv.pdf")  # or cv_from_text("...")
jd = load_job_description("https://...")  # URL or pasted text
package = Pipeline(cfg).run(cv, jd)  # writes output/<company>-<role>/
```

## Quality checks (binary — every one must pass)
- [ ] All five artifacts were produced (unless the user switched some off in config).
- [ ] The output folder is named `<company>-<role>` and contains `.md` files (and `.docx` if configured).
- [ ] Every employer, job title, date, and metric in the tailored CV and cover letter appears in the source CV — none are invented.
- [ ] The fit memo marks at least the genuine gaps as **Gap** or **Partial match**, with no invented evidence.
- [ ] The ATS report's "Missing keywords" section tells the user NOT to add any term they have no real experience with.
- [ ] The interview prep STAR scaffolds are built only from real CV experience; where no real example exists, it says so instead of inventing one.
- [ ] Output is in the configured English variant (UK by default).

If any check fails, fix it before handing the package back — do not paper over a
gap by inventing experience.
