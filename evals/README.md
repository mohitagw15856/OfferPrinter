# Evals

Prompts are the product. Everything OfferPrinter does well or badly, it does
because of `offerprinter/prompts/templates.py` — and until now there was no way
to tell whether editing that file made the tool better or worse. You changed a
line, the output looked fine on one CV, you shipped it.

This is the harness that replaces "looked fine" with a number.

## Two modes, on purpose

**Offline** (`--offline`) replays the recorded outputs committed under each
case's `recorded/` folder and runs only the deterministic checks: the
fabrication verifier, plus each case's own expectations about which gaps must be
named. No API key, no network, no cost, ~200ms. **This runs in CI on every PR.**

**Live** (default) generates fresh output with a real model and adds an
LLM-as-judge pass scoring grounding, specificity, honesty, usefulness and
format. It costs a few pence and needs a key, so it runs on demand rather than
on every push.

The split matters: the offline mode is the one that must never regress, because
it tests the guarantee. The live mode measures quality, which is fuzzier and
allowed to wobble a little.

## Running it

```bash
# deterministic, free, offline — what CI runs
python scripts/run_evals.py --offline

# full run against a real model
export ANTHROPIC_API_KEY="sk-ant-..."
python scripts/run_evals.py

# just one case, and write a report
python scripts/run_evals.py --case northbank-analyst --report evals/report.json

# fail the run if quality drops below the committed baseline
python scripts/run_evals.py --baseline evals/baseline.json
```

## Adding a case

```
evals/cases/<name>/
├── cv.md          # the candidate's CV
├── jd.md          # the job description
├── expect.json    # what must be true of the output
└── recorded/      # committed sample output, for offline mode
    ├── tailored-cv.md
    ├── cover-letter.md
    └── ats-keyword-report.md
```

`expect.json` supports:

| Key | Meaning |
|---|---|
| `must_flag_gaps` | Substrings that must appear in the fit memo or ATS report's gaps. This is how "be honest about what the candidate lacks" becomes testable. |
| `must_not_claim` | Terms that must **not** appear in the tailored CV. The core anti-fabrication assertion. |
| `min_fit`, `max_fit` | Bounds on the fit score, so a case designed as a stretch cannot quietly start scoring 90. |
| `min_scores` | Per-dimension floors for the judge, in live mode only. |

Cases should be **anonymised and synthetic**. Never commit a real person's CV.

## Why a judge, and why a strict one

The judge prompt (`JUDGE_PROMPT`) is told that generosity is actively harmful,
because a grader that gives everything 4/5 measures nothing. Its scores are only
meaningful *relative to the baseline* — treat a drop as a signal to look, not as
an absolute verdict on quality.

The judge cannot be the only check, which is why the deterministic verifier runs
first and independently. A model grading a model is useful; it is not proof.
