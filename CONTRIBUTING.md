# Contributing to OfferPrinter

Thanks for being here. OfferPrinter is a small, deliberately readable codebase,
and it stays that way because contributions keep it that way.

## The one rule that overrides everything

**OfferPrinter never fabricates.** Not a job title, not a date, not a metric,
not a keyword. If a change makes it easier for the tool to imply experience the
candidate does not have, that change will be declined no matter how good it is
otherwise. Everything else here is negotiable; this is not.

When you touch anything in `offerprinter/prompts/templates.py`, assume the diff
will be read line by line.

## Getting set up

```bash
git clone https://github.com/mohitagw15856/OfferPrinter.git
cd OfferPrinter
uv sync --extra dev          # or: pip install -e ".[dev]"
pytest                       # the whole suite is offline and takes seconds
```

You do **not** need an API key to develop or to run the tests. The suite uses a
stub provider; if a test of yours needs the network, it's testing the wrong
thing.

## Before you open a PR

```bash
ruff check .            # lint
ruff format .           # format
pytest                  # tests
```

CI runs all three across Python 3.11, 3.12 and 3.13, plus macOS and Windows
spot-checks. Everything must be green.

## Good first contributions

| Idea | Where | Why it's a good first PR |
|---|---|---|
| **A new LLM provider** | `offerprinter/llm/` | One subclass, one registry line, one test. Nothing else changes. |
| **Better job-description extraction** | `offerprinter/services/jd_fetcher.py` | Job boards are actively hostile. Real, measurable wins available. |
| **A new output format** | `offerprinter/services/` | LaTeX, plain-text ATS mode, ODT. Follow `pdf_writer.py` for the pattern. |
| **Prompt improvements** | `offerprinter/prompts/templates.py` | Highest leverage in the repo. Show before/after output in the PR. |
| **Tests** | `tests/` | Always welcome, always merged. |

## Adding a provider

The whole contract is one method:

```python
from offerprinter.llm.base import LLMProvider


class MyProvider(LLMProvider):
    default_model = "their-cheapest-capable-model"

    def complete(self, system: str, user: str) -> str:
        key = self._require_key()
        data = self._post(url, headers, payload)  # retries + backoff, free
        self._record_usage(in_tokens, out_tokens)  # cost reporting, free
        return data["..."]
```

Then add it to `Provider` in `models/schemas.py`, to `_REGISTRY` in
`llm/factory.py`, to `_PROVIDER_KEY_ENV` in `config.py`, and to the price table
in `pricing.py`. Pick the provider's **cheapest capable** model as the default —
someone trying this at 11pm should not get a surprise bill.

If the provider speaks the OpenAI Chat Completions dialect, subclass
`OpenAIProvider` instead and you'll be done in five lines. See
`kimi_provider.py` and `ollama_provider.py`.

## Style

- Match the surrounding code. Comments explain *why*, never *what*.
- Type hints on public functions.
- Keep runtime dependencies small. We write our own PDF rather than pulling in a
  rendering engine, and we call four LLM APIs over plain `httpx` rather than
  vendoring four SDKs. New dependencies need a reason.
- Layers stay separate: services do no I/O beyond their job, the generator does
  no file formats, prompts live in one file.

## Reporting bugs

Open an issue with the template. If it's about generated output, include the
provider and model — output quality varies more between models than between
versions of this tool.

## Security

Please don't open a public issue for a security problem. See
[SECURITY.md](SECURITY.md).

## Licence

By contributing you agree your work is licensed under the
[MIT License](LICENSE), same as the rest of the project.
