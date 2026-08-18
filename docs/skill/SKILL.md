---
name: offerprinter
description: >-
  Print a complete, tailored job-application package from one CV and one job
  description. Use when a user wants to apply to a specific role and has (or can
  paste) their CV plus the job description or its URL. Produces a tailored CV, a
  cover letter, a one-page fit memo, an ATS keyword report, an interview prep
  pack, and a 0-100 fit score — all written only from facts in the user's real
  CV, nothing fabricated.
---

# OfferPrinter — one input → full application package

**Verb the thing.** Turn one CV and one job description into a full, tailored,
ready-to-review application package.

**Use when** the user is applying to a specific role and can supply (a) their base
CV/resume and (b) the target job description (pasted text or a URL). Do not use for
generic "improve my CV" requests with no target role — for those, use `roast` (below).

**Produces**, in `output/<company>-<role>/` as `.md`, `.docx` and optionally
`.pdf`, plus a combined `full-package.md`:
1. `tailored-cv` — the user's real CV, reordered and reworded for this role (ATS-friendly).
2. `cover-letter` — specific to the company and role, no generic filler.
3. `fit-memo` — maps the user's real experience to each key requirement and honestly flags gaps.
4. `ats-keyword-report` — job keywords the CV covers, which are missing, and where to add missing ones truthfully.
5. `interview-prep-pack` — likely questions, STAR scaffolds from the user's real experience, and 5 questions to ask.
6. `fit-score` — a strict 0-100 score with band, genuine strengths, and genuine gaps.

## Required inputs
- **CV** — a path to a `.pdf`, `.docx`, `.md`, or `.txt` file, OR the CV pasted as text.
- **Job description** — a URL to fetch, OR the JD pasted as text.
- **An LLM API key** — for the configured provider (Anthropic by default). Read
  from `config.toml` or an environment variable; never invent one. The `ollama`
  provider needs no key and runs locally.

## The one non-negotiable rule
**Never fabricate.** Only reframe facts that are actually in the user's CV. Do not
invent experience, skills, employers, dates, titles, certifications, or metrics. If
the role needs something the user lacks, the fit memo, ATS report and fit score must
say so plainly. This is the tool's core guarantee — honour it in any manual edits too.

## How to run it

Preferred — the CLI does the whole flow in one command:

```bash
offerprinter --cv path/to/cv.pdf --jd "https://careers.example.com/123"
# or, with the JD in a file / pasted text:
offerprinter --cv path/to/cv.docx --jd-file jd.txt
# from a git clone rather than an install:
python cli.py --cv path/to/cv.pdf --jd-file jd.txt
```

Common variations:

```bash
# provider, locale, and output formats
offerprinter --cv cv.md --jd-file jd.txt --provider openai --locale US --formats md,docx,pdf

# forecast the cost first — calls nothing
offerprinter --cv cv.pdf --jd-file jd.txt --dry-run

# a package for every job description in a folder
offerprinter --cv cv.pdf --jd-dir ./jobs

# fully local, no API key, nothing leaves the machine
offerprinter --provider ollama --cv cv.pdf --jd-file jd.txt
```

Other commands:

```bash
offerprinter roast --cv cv.pdf         # blunt critique of the CV's writing (opt-in)
offerprinter list                      # applications printed so far
offerprinter stats                     # totals, spend, average fit
offerprinter status <slug> interview   # record progress on an application
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

print(package.fit.score, package.fit.band)  # e.g. 74 Strong
print(package.usage.cost_usd)  # what the run cost
```

Use `Pipeline.stream(cv, jd)` instead of `.run()` if you want to report progress —
it yields events of kind `meta`, `artifact`, `fit`, `written`, and `done`.

## Notes for agents
- **Never run this without the user's actual CV.** If you don't have one, ask.
  Do not draft a plausible CV and feed it in — everything downstream would be
  fabricated by construction.
- **Report the gaps.** When you hand the package back, surface the fit score and
  the flagged gaps explicitly. Those are the most useful output, not the least.
- **Don't "fix" a low score** by re-running with embellishment. A 48 is
  information, not a failure.
- Artifacts generate concurrently by default; pass `--sequential` if the
  provider rate-limits hard.
- Runs are recorded locally in `~/.offerprinter/applications.json`. Pass
  `--no-track` if the user doesn't want that.

## Quality checks (binary — every one must pass)
- [ ] All five artifacts were produced (unless the user switched some off in config).
- [ ] The output folder is named `<company>-<role>` and contains `.md` files (and `.docx`/`.pdf` if configured).
- [ ] Every employer, job title, date, and metric in the tailored CV and cover letter appears in the source CV — none are invented.
- [ ] The fit memo marks at least the genuine gaps as **Gap** or **Partial match**, with no invented evidence.
- [ ] The ATS report's "Missing keywords" section tells the user NOT to add any term they have no real experience with.
- [ ] The interview prep STAR scaffolds are built only from real CV experience; where no real example exists, it says so instead of inventing one.
- [ ] The fit score's gaps list is not empty when the fit memo flags gaps — the two must agree.
- [ ] Output is in the configured English variant (UK by default).

If any check fails, fix it before handing the package back — do not paper over a
gap by inventing experience.
