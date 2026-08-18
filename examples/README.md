# Example: a real before → after

This folder is a complete, runnable example so you can see exactly what
OfferPrinter produces before you run it on your own CV.

- **`sample_cv.md`** — an anonymised base CV (Alex Morgan, a marketing data analyst).
- **`sample_jd.md`** — a target job (Senior Product Analyst at "NorthBank", a fictional bank).
- **`output/northbank-senior-product-analyst/`** — the generated package: tailored
  CV, cover letter, fit memo, ATS keyword report, interview prep pack, and a
  combined `full-package.md` — each also as `.docx`.

## The point of this example
The sample CV was deliberately chosen to have **genuine gaps** against the job
(no dbt, no fintech experience, marketing rather than product analytics). Open
[`output/…/fit-memo.md`](output/northbank-senior-product-analyst/fit-memo.md) and
[`output/…/ats-keyword-report.md`](output/northbank-senior-product-analyst/ats-keyword-report.md)
and you'll see those gaps flagged honestly — the tool never invents dbt or fintech
experience to make Alex look like a better fit. That's the whole guarantee, shown
rather than promised.

## Reproduce it yourself

```bash
python cli.py --cv examples/sample_cv.md --jd-file examples/sample_jd.md
```

(Exact wording will vary run to run and by provider/model — the committed output
is one representative run.)
