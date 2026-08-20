# Changelog

All notable changes to OfferPrinter are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-08-20

The "prove it" release. v0.2.0 made OfferPrinter installable; this one makes its
central claim checkable, and extends the tool across the rest of a job hunt.

### Added

**Proving the guarantee**
- **Fabrication verifier.** Every number, date and named entity in the tailored
  CV and cover letter is checked against your source CV, and the tailored CV is
  cross-checked against the ATS report's own list of gaps — so a package that
  contradicts itself is caught automatically. Writes `fabrication-check.md`.
  `--strict` exits 3 if anything is unverified, which makes it usable as a gate.
  Until now "never fabricate" was an instruction in a prompt; now it is an
  assertion the tool makes about its own output.
- **`offerprinter verify`** re-checks an already-generated package — after you
  have hand-edited it, or in CI. Makes no API calls, so it is free and offline.
- **Tailoring diff.** `tailoring-diff.md` shows exactly what changed: which
  bullets were reworded, what was added or dropped, and which vocabulary is new.
  The verifier proves nothing was invented; the diff shows what was done.
- **Eval harness** (`evals/`, `scripts/run_evals.py`). Golden cases with
  per-case assertions about which gaps must be named and which terms must never
  be claimed, plus an LLM-as-judge pass scoring grounding, specificity, honesty,
  usefulness and format. The deterministic half runs in CI on every PR; the
  judge runs on demand. Prompt changes are no longer a guess.

**New commands**
- **`offerprinter rank`** — score a folder of adverts and rank them by fit
  without generating a single document. Two cheap calls per job; triage twenty
  roles for a couple of pence, then print packages only for the ones worth it.
- **`offerprinter followup`** — thank-you email, recruiter message, LinkedIn
  note (hard-capped at 300 characters) or a polite nudge. Written from your CV
  and your notes; it will not invent a conversation that did not happen.
- **`offerprinter practice`** — an interactive mock interview. It asks, you
  answer, it critiques and rewrites your answer using only your real experience,
  then summarises the patterns worth fixing.
- **`offerprinter mcp`** — run as an MCP server on stdio, so Claude Desktop,
  Claude Code and other agents can call OfferPrinter natively and get structured
  results back. Hand-rolled JSON-RPC; no new dependencies.
- **`offerprinter cache stats` / `cache clear`**.

**Privacy and job-board reality**
- **PII redaction** (`--redact`). Your name, email, phone and profile links are
  replaced with placeholders before the provider sees anything, and restored in
  the output. The model keeps every employer, date and metric it needs.
- **`--jd-clipboard`** and a **browser extension** (`extension/`). Job boards
  are the most common reason a run fails; the advert is already rendered in your
  tab, so read it from there. The extension has no host permissions and makes no
  network requests.
- **schema.org `JobPosting` JSON-LD extraction.** Many boards embed the whole
  advert as structured data — cleaner than anything scraped, and it supplies the
  company and job title for free.

**Cost**
- **Response caching.** Keyed on provider, model, temperature and both prompts,
  so anything that could change the answer correctly misses. Re-running after a
  CV tweak is now mostly free.

### Fixed

- Multi-word entities could match across a line break, producing nonsense claims
  glued together from two sentences.
- A level-two heading (`## Missing keywords`) was not recognised as a sentence
  start, so its first word was treated as a named entity.
- A capitalised word at the very start of a bullet ("Used SQL daily") was read
  as an entity, because the sentence-start pattern only handled bullets that
  followed a newline, not one at the start of the text.

### Changed

- Config gains `[output] redact`, `[generation] verify`, `diff` and `cache`.
- The test suite grew from 73 to 143 tests, still fully offline.


## [0.2.0] — 2026-08-18

The "actually installable, and quite a lot faster" release.

### Added

**Distribution**
- Published to PyPI: `pipx install offerprinter`, `uvx offerprinter`, or
  `pip install offerprinter`.
- `offerprinter` and `opr` console scripts, so it works from anywhere after
  install rather than only from a git clone.
- Standalone binaries for macOS, Linux and Windows attached to each release —
  no Python installation required.
- Multi-arch Docker image published to GHCR on every push and tag:
  `ghcr.io/mohitagw15856/offerprinter:latest`.
- Homebrew formula in `packaging/homebrew/` for a `brew install` tap.
- Deployment guides for Streamlit Community Cloud, Hugging Face Spaces, Docker
  and container platforms, in `deploy/`.

**Features**
- **Fit score** — every run ends with a 0-100 score, a band, and honest
  strengths and gaps. Written to `fit-score.md` and shown in the CLI and web UI.
- **PDF output** — real, selectable, ATS-friendly Helvetica text, written by a
  dependency-free PDF writer rather than a rendering engine. Enable with
  `--formats md,docx,pdf`.
- **Roast mode** — `offerprinter roast --cv cv.pdf`, or `--roast` during a run.
  Blunt, funny, opt-in critique of your CV's *writing*. Still never dishonest.
- **Application tracker** — every run is recorded locally in
  `~/.offerprinter/applications.json`. New commands: `offerprinter list`,
  `offerprinter stats`, `offerprinter status <slug> <status>`.
- **Achievements** — eleven small milestones, computed from your local history.
- **Batch mode** — `--jd-dir ./jobs` prints a package for every job description
  in a folder.
- **Cost and token reporting** — every run reports calls, tokens and estimated
  spend. `--dry-run` forecasts the cost without calling the API at all.
- **Ollama provider** — run entirely on your own machine with no API key and no
  data leaving your laptop: `--provider ollama`.
- **Printer animation** — an ASCII dot-matrix printer feeding a sheet per
  document. Degrades to plain status lines when not a terminal, or with
  `--no-animation`.
- **Demo mode in the web UI** — with no API key configured, the app shows the
  bundled example package instead of an error, which is what makes a public
  hosted demo possible.

**Reliability**
- Automatic retries with exponential backoff and `Retry-After` support on 429s
  and 5xx errors. A single rate limit no longer kills a five-document run.
- `[pricing]` config table to override list prices with your actual rates.

**Project**
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, this changelog, issue
  and pull request templates.
- CI now runs the test suite across Python 3.11/3.12/3.13 with macOS and Windows
  spot-checks, plus coverage, a packaging build, and a console-script smoke test.

### Changed

- **Artifacts now generate in parallel.** They are independent of each other, so
  a full run takes about as long as its slowest single document instead of the
  sum of all five. Use `--sequential` for the old behaviour.
- The CLI moved to `offerprinter/cli.py` so it ships inside the installed
  package. `python cli.py …` still works from a clone.
- The web UI (`streamlit`) is now an optional extra, keeping
  `pipx install offerprinter` small. Install it with `offerprinter[web]`.
- Default output formats remain `md` and `docx`; `pdf` is opt-in via config
  or `--formats`.

### Fixed

- The `offerprinter` console script pointed at a root-level `cli` module that
  was never included in the wheel, so it could not resolve after an install.
- The README claimed CI ran `pytest`. It didn't. Now it does.

## [0.1.0] — 2026-08-18

First release — "First Print".

### Added

- Five generated artifacts from one CV and one job description: tailored CV,
  cover letter, fit memo, ATS keyword report, interview prep pack.
- The no-fabrication guarantee, enforced in every prompt.
- Four providers behind one interface: Anthropic (default), OpenAI, Gemini,
  Moonshot Kimi.
- CLI (Typer), web UI (Streamlit), and an agent skill at `docs/skill/SKILL.md`.
- CV input as `.pdf`, `.docx`, `.md`, `.txt` or pasted text; job description as a
  URL or text.
- Markdown and Word output, plus a combined full package.
- UK and US English.
- Config via env vars, `config.toml`, or defaults.
- Dockerfile and docker-compose, offline test suite, ruff lint.

[Unreleased]: https://github.com/mohitagw15856/OfferPrinter/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mohitagw15856/OfferPrinter/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mohitagw15856/OfferPrinter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mohitagw15856/OfferPrinter/releases/tag/v0.1.0
