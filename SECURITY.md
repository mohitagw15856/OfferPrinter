# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅ |
| 0.1.x   | ❌ — please upgrade |

## Reporting a vulnerability

Please report security issues **privately**, not as a public issue.

Use GitHub's private reporting:
[**Report a vulnerability**](https://github.com/mohitagw15856/OfferPrinter/security/advisories/new)

Include what you did, what happened, and what you expected. A proof of concept
helps but is not required.

You'll get an acknowledgement within 7 days, and an assessment within 14. If the
report is valid, you'll be credited in the release notes unless you'd rather not
be.

## What counts as a vulnerability here

OfferPrinter handles something genuinely sensitive — a person's full CV and
their API credentials — so the threat model is narrow but real:

| In scope | Examples |
|---|---|
| **Credential leakage** | An API key written to disk, logged, printed, or sent anywhere other than the configured provider. |
| **CV data leakage** | CV or job-description text reaching any host other than the configured LLM provider (or the JD URL you asked it to fetch). |
| **Path traversal** | A crafted company/role name escaping the output directory. |
| **Code execution** | Anything in a CV, job description, or fetched page that leads to code running. |
| **Dependency issues** | A vulnerable transitive dependency we should pin or drop. |
| **Supply chain** | Anything affecting the published wheel, the GHCR image, or the release binaries. |

Out of scope:

- **The LLM provider's data policy.** Whether Anthropic, OpenAI, Google or
  Moonshot train on your API traffic is between you and them — check their
  policy. OfferPrinter makes exactly one call to the provider you chose.
- **Quality of generated output.** A weak cover letter is a bug, not a
  vulnerability. Open a normal issue.
- **Anything requiring an attacker to already have your machine.** If someone
  can read `~/.offerprinter/`, they can already read your CV.

## What OfferPrinter does with your data

Stated plainly, because it's the point of the project:

- Your CV and the job description are sent to **one place**: the LLM provider
  you configured.
- A job-description **URL** you pass is fetched directly by your machine.
- Generated packages are written to `./output/` (git-ignored by default).
- A local history is appended to `~/.offerprinter/applications.json` unless you
  set `track = false`. It never leaves your machine and you can delete it.
- There is no OfferPrinter server, account, telemetry, or analytics of any kind.
  There is nothing to opt out of because there is nothing collecting anything.

`config.toml`, `.env` and `output/` are all in `.gitignore` so a stray commit
cannot leak your key or your CV.
