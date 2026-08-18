# 🖨 OfferPrinter

### Paste one job description and your CV. Print a complete, tailored application package — in a single run.

No more staring at a blank cover letter at 11pm. Give OfferPrinter your CV and the
job you want, and it prints everything you need to apply:

| # | Artifact | What it is |
|---|----------|------------|
| 1 | **Tailored CV** | Your real CV, reordered and reworded to foreground what *this* role wants. ATS-friendly plain formatting. |
| 2 | **Cover letter** | Specific to the company and role. No "I am writing to express my interest" filler. |
| 3 | **Fit memo** | A one-pager mapping your real experience to each requirement — and honestly flagging the gaps. |
| 4 | **ATS keyword report** | Which of the job's key terms your CV already covers, which are missing, and where to add the missing ones *truthfully*. |
| 5 | **Interview prep pack** | Likely questions, STAR answer scaffolds built from your real experience, and 5 smart questions to ask them. |

Everything runs **on your machine, with your own API key**. No accounts, no
telemetry, nothing uploaded anywhere except the LLM provider you choose.

---

## 🔒 The no-fabrication guarantee

This is the whole point, so it comes first:

> **OfferPrinter never invents experience, skills, employers, dates, or metrics.**
> It only reframes what is genuinely in your CV. If the role wants something you
> don't have, it tells you in the fit memo and ATS report — it does not lie on
> your behalf.

Your CV stays *true*. When a requirement isn't met, you'll see it flagged as a
**Gap**, not quietly filled in. That's what makes the output safe to send.

See it in action: the [example fit memo](examples/output/northbank-senior-product-analyst/fit-memo.md)
openly marks "dbt" and "fintech experience" as gaps for a candidate who doesn't
have them — instead of pretending they do.

---

## 👀 What the output looks like

A real sample run lives in [`examples/`](examples/) — an anonymised marketing
analyst applying for a *Senior Product Analyst* role. Here's a slice of the
generated **ATS keyword report**:

```markdown
## Missing keywords
- dbt
- Product analytics / product metrics
- Financial services / fintech

## How to add the missing terms — truthfully
- dbt — Do not add — no evidence in your CV. This is a genuine gap.
- Product analytics — Partial. You genuinely define metrics and own analytics
  end to end, so you may reframe your existing work as "analytics ownership and
  metric definition" — but do not label it "product analytics" unless true.
- Financial services / fintech — Do not add — no evidence in your CV.

## Coverage summary
Covered 9 of 15 key terms.
```

Browse the full package: [tailored CV](examples/output/northbank-senior-product-analyst/tailored-cv.md)
· [cover letter](examples/output/northbank-senior-product-analyst/cover-letter.md)
· [fit memo](examples/output/northbank-senior-product-analyst/fit-memo.md)
· [ATS report](examples/output/northbank-senior-product-analyst/ats-keyword-report.md)
· [interview prep](examples/output/northbank-senior-product-analyst/interview-prep-pack.md)
· [combined](examples/output/northbank-senior-product-analyst/full-package.md)
(each also generated as `.docx`).

---

## ⚡ 60-second quickstart

```bash
# 1. Get the code
git clone https://github.com/mohitagw15856/offerprinter.git
cd offerprinter

# 2. Install (uv — recommended)
uv sync
#    …or with plain pip:
#    python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 3. Add your API key (Anthropic by default — cheapest capable model out of the box)
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Print an application package
python cli.py --cv examples/sample_cv.md --jd-file examples/sample_jd.md
```

Your package appears in `output/northbank-senior-product-analyst/`. Swap in your
own CV and a real job URL and you're done:

```bash
python cli.py --cv ~/Documents/my-cv.pdf --jd "https://careers.company.com/jobs/123"
```

---

## 🖥 Three ways to run it

### 1. WebUI (nicest for most people)

```bash
uv run streamlit run app.py      # or: streamlit run app.py
```

Opens at <http://localhost:8501>. Paste or upload your CV, paste the job (text or
URL), pick a provider in the sidebar, and hit **Print my application**. Each
artifact streams in with its own **Markdown** and **Word** download buttons, plus
a "download everything as a .zip".

### 2. CLI (nicest for scripting)

```bash
python cli.py --cv path/to/cv.pdf --jd "https://..."     # JD from a URL
python cli.py --cv path/to/cv.docx --jd-file jd.txt      # JD from a file
python cli.py --cv-text "paste CV here…" --jd-file jd.txt # CV pasted inline
```

`python cli.py --help` lists every option. Useful ones:

| Option | Does |
|--------|------|
| `--cv` / `--cv-text` | CV as a file (`.pdf/.docx/.md/.txt`) or pasted text. |
| `--jd` / `--jd-file` | Job description as a URL / pasted text, or a file. |
| `--provider` | `anthropic` (default), `openai`, `gemini`, `kimi`. |
| `--model` | Override the model for this run. |
| `--locale` | `UK` (default) or `US` English. |
| `--output-dir` / `-o` | Where to write (default `./output`). |
| `--config` | Path to a `config.toml`. |

### 3. Agent skill (Claude Code, Hermes, etc.)

Point your agent at [`docs/skill/SKILL.md`](docs/skill/SKILL.md). It follows the
`Verb the thing. Use when X. Produces Y.` format with **Required Inputs** and
binary **Quality Checks**, so an agent can run the whole flow — and knows never to
fabricate — just by reading it.

### 🐳 …or in Docker (isolated run)

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up   # WebUI at http://localhost:8501
```

---

## 🔌 Provider setup

OfferPrinter is provider-agnostic through a single clean interface. Set the
provider and its key, and everything else just works.

| Provider | Default model | Set your key via |
|----------|---------------|------------------|
| **Anthropic (Claude)** — default | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `gpt-4o-mini` | `OPENAI_API_KEY` |
| **Google Gemini** | `gemini-1.5-flash` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) |
| **Moonshot Kimi** | `moonshot-v1-8k` | `MOONSHOT_API_KEY` |

Switching provider is **one line** — in `config.toml`:

```toml
[llm]
provider = "openai"     # was "anthropic"
```

…or per run: `python cli.py --provider openai --cv … --jd …`. The defaults are the
cheapest capable model for each provider, so the free/cheapest path works out of
the box.

---

## ⚙️ Config reference

Copy [`config.example.toml`](config.example.toml) to `config.toml` and edit. Every
option is documented inline there; env vars always win over the file.

```toml
[llm]
provider = "anthropic"   # anthropic | openai | gemini | kimi   (env: OFFERPRINTER_PROVIDER)
model = ""               # blank = provider default             (env: OFFERPRINTER_MODEL)
api_key = ""             # prefer the per-provider env var       (env: OFFERPRINTER_API_KEY)
base_url = ""            # override endpoint (proxy/gateway)     (env: OFFERPRINTER_BASE_URL)
temperature = 0.2        # low = faithful, deterministic
max_tokens = 4096
timeout = 120

[output]
locale = "UK"            # UK | US                               (env: OFFERPRINTER_LOCALE)
dir = "./output"         # where packages are written            (env: OFFERPRINTER_OUTPUT_DIR)
formats = ["md", "docx"] # which file formats to write

[generation]             # turn any artifact off to save tokens
tailored_cv = true
cover_letter = true
fit_memo = true
ats_report = true
interview_prep = true
```

**Config precedence:** environment variables → `config.toml` → built-in defaults.
The only thing you *must* provide is an API key.

---

## 🏗 How it's built

Layered and modular, so it's easy to read, audit, and extend:

```
offerprinter/
├── config.py               # config: env vars → config.toml → defaults
├── models/                 # typed data models that flow through the pipeline
├── llm/                    # provider-agnostic LLM layer (one interface, 4 providers)
│   ├── base.py             #   the single interface every provider implements
│   ├── anthropic_provider.py / openai_provider.py / gemini_provider.py / kimi_provider.py
│   └── factory.py          #   config → concrete provider
├── prompts/                # ALL prompt templates — audit the no-fabrication rules here
├── services/               # cv_parser · jd_fetcher · generator · writer
└── controllers/
    └── pipeline.py         # the end-to-end flow, emitting progress events
cli.py                      # CLI (Typer)
app.py                      # WebUI (Streamlit)
docs/skill/SKILL.md         # agent entry point
```

Want to change how OfferPrinter writes? Everything lives in one auditable file:
[`offerprinter/prompts/templates.py`](offerprinter/prompts/templates.py). Want a
new provider? Add one subclass in `offerprinter/llm/` — nothing else changes.

---

## ❓ FAQ

**Does it send my CV anywhere?**
Only to the LLM provider you choose, to generate the package. Nothing else — no
accounts, no analytics, no OfferPrinter server. It's local-first by design.

**Will it lie to make me look better?**
No. That's the [no-fabrication guarantee](#-the-no-fabrication-guarantee).
Gaps are flagged, not filled. The whole thing is built to keep your application
*true* so it survives an interview.

**What CV formats can I use?**
`.pdf`, `.docx`, `.md`, `.txt`, or just paste the text. Scanned/image-only PDFs
won't extract — paste the text instead.

**Can it read a job posting from a URL?**
Yes — pass a URL to `--jd` (or paste it in the WebUI) and it fetches and extracts
the text. Some sites block bots or require JavaScript; if extraction looks thin,
paste the JD text instead.

**Which provider should I use?**
Any of the four. Defaults are the cheapest capable model for each, so start with
the one you already have a key for. Claude is the default.

**British or American English?**
British by default. Set `locale = "US"` (or `--locale US`) for American spelling.

**Is my data used to train a model?**
That's between you and your chosen provider — check their API data policy. Many
offer a no-training default for API traffic. OfferPrinter itself stores and sends
nothing beyond that one call.

**How much does a run cost?**
Five short generations on a cheap model — typically a few cents. Turn off artifacts
you don't need in `[generation]` to spend less.

---

## 🤝 Contributing & licence

Issues and PRs welcome. Lint with `ruff check .` and run `pytest` before pushing
(the CI workflow checks both). Licensed under the [MIT License](LICENSE).

---

*OfferPrinter helps you apply honestly and fast. Always review the output before
you send it — it's your application, in your voice, built from your real
experience.*
