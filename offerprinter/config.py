"""Configuration loading.

Precedence (highest wins):
    1. Environment variables
    2. config.toml (or a path passed explicitly)
    3. Built-in defaults

The only thing a user strictly has to provide is an API key. If the key is not
in the file or the generic OFFERPRINTER_API_KEY var, we fall back to the
standard per-provider env var (ANTHROPIC_API_KEY, OPENAI_API_KEY, ...).
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib  # type: ignore

from offerprinter.models.schemas import (
    GenerationConfig,
    LLMConfig,
    Locale,
    OutputConfig,
    Provider,
)

# Standard per-provider environment variables to fall back to for the key.
_PROVIDER_KEY_ENV: dict[Provider, tuple[str, ...]] = {
    Provider.ANTHROPIC: ("ANTHROPIC_API_KEY",),
    Provider.OPENAI: ("OPENAI_API_KEY",),
    Provider.GEMINI: ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    Provider.KIMI: ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
}


class Config:
    """Fully-resolved runtime configuration."""

    def __init__(
        self,
        llm: LLMConfig,
        output: OutputConfig,
        generation: GenerationConfig,
    ) -> None:
        self.llm = llm
        self.output = output
        self.generation = generation


def _read_toml(path: Path | None) -> dict:
    """Load a TOML file if it exists; otherwise return an empty dict."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        # Look for config.toml in the current directory by default.
        candidates.append(Path("config.toml"))

    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as fh:
                return tomllib.load(fh)
    return {}


def _first_env(*names: str) -> str | None:
    for name in names:
        val = os.environ.get(name)
        if val:
            return val
    return None


def load_config(config_path: str | os.PathLike[str] | None = None) -> Config:
    """Resolve configuration from file + environment.

    Args:
        config_path: Optional explicit path to a config.toml.
    """
    data = _read_toml(Path(config_path) if config_path else None)
    llm_raw = data.get("llm", {})
    out_raw = data.get("output", {})
    gen_raw = data.get("generation", {})

    # ---- provider ----------------------------------------------------------
    provider_str = _first_env("OFFERPRINTER_PROVIDER") or llm_raw.get("provider", "anthropic")
    provider = Provider(provider_str.lower())

    # ---- model -------------------------------------------------------------
    model = _first_env("OFFERPRINTER_MODEL") or llm_raw.get("model", "") or ""

    # ---- api key -----------------------------------------------------------
    api_key = (
        _first_env("OFFERPRINTER_API_KEY")
        or (llm_raw.get("api_key") or "")
        or (_first_env(*_PROVIDER_KEY_ENV[provider]) or "")
    )

    # ---- base url ----------------------------------------------------------
    base_url = _first_env("OFFERPRINTER_BASE_URL") or llm_raw.get("base_url", "") or ""

    llm = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(llm_raw.get("temperature", 0.2)),
        max_tokens=int(llm_raw.get("max_tokens", 4096)),
        timeout=float(llm_raw.get("timeout", 120)),
    )

    # ---- output ------------------------------------------------------------
    locale_str = _first_env("OFFERPRINTER_LOCALE") or out_raw.get("locale", "UK")
    output = OutputConfig(
        locale=Locale(locale_str.upper()),
        dir=_first_env("OFFERPRINTER_OUTPUT_DIR") or out_raw.get("dir", "./output"),
        formats=list(out_raw.get("formats", ["md", "docx"])),
    )

    # ---- generation --------------------------------------------------------
    generation = GenerationConfig(
        tailored_cv=bool(gen_raw.get("tailored_cv", True)),
        cover_letter=bool(gen_raw.get("cover_letter", True)),
        fit_memo=bool(gen_raw.get("fit_memo", True)),
        ats_report=bool(gen_raw.get("ats_report", True)),
        interview_prep=bool(gen_raw.get("interview_prep", True)),
    )

    return Config(llm=llm, output=output, generation=generation)
