# What does this change?

<!-- One or two sentences. What's different after this PR? -->

## Why?

<!-- What problem does it solve? Link an issue with "Closes #123" if there is one. -->

## How was it tested?

<!--
Commands you ran, and what you saw. If it changes generated output, show a
before/after excerpt — output quality is the whole product, and a diff of the
prompt tells us far less than a diff of the result.
-->

## Checklist

- [ ] `ruff check .` passes
- [ ] `ruff format .` has been run
- [ ] `pytest` passes
- [ ] I added or updated tests for anything I changed
- [ ] I updated the README / `config.example.toml` if behaviour or config changed
- [ ] I added a line to `CHANGELOG.md` under `[Unreleased]`

## The no-fabrication guarantee

OfferPrinter never invents experience, skills, employers, dates, or metrics.

- [ ] This change cannot cause the tool to imply experience the candidate does
      not actually have.

<!--
If you touched offerprinter/prompts/templates.py, please say explicitly what
changed and why — that file is the product's core promise and gets read closely.
-->

## Anything else?

<!-- Trade-offs, follow-up work, things you're unsure about. -->
