"""Configuration loading.

Precedence (highest wins):
    1. Environment variables
    2. config.toml (or a path passed explicitly)
    3. Built-in defaults

The only thing a user strictly has to provide is an API key. If the key is not
in the file or the generic OFFERPRINTER_API_KEY var, we fall back to the
standard per-provider env var (ANTHROPIC_API_KEY, OPENAI_API_KEY, ...).

The Ollama provider is the exception: it runs on your own machine and needs no
key at all.
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
from offerprinter.services.writer import SUPPORTED_FORMATS

# Standard per-provider environment variables to fall back to for the key.
_PROVIDER_KEY_ENV: dict[Provider, tuple[str, ...]] = {
    Provider.ANTHROPIC: ("ANTHROPIC_API_KEY",),
    Provider.OPENAI: ("OPENAI_API_KEY",),
    Provider.GEMINI: ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    Provider.KIMI: ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    Provider.OLLAMA: ("OLLAMA_API_KEY",),
}


class Config:
    """Fully-resolved runtime configuration."""

    def __init__(
        self,
        llm: LLMConfig,
        output: OutputConfig,
        generation: GenerationConfig,
        pricing: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.llm = llm
        self.output = output
        self.generation = generation
        #: model name/prefix -> (USD per 1M input, USD per 1M output)
        self.pricing = pricing or {}


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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _clean_formats(raw: object) -> list[str]:
    """Keep only formats we can actually write, preserving the user's order."""
    values = [str(f).strip().lower().lstrip(".") for f in raw] if isinstance(raw, list) else []
    formats = [f for f in values if f in SUPPORTED_FORMATS]
    return formats or ["md", "docx"]


def _parse_pricing(raw: object) -> dict[str, tuple[float, float]]:
    """Parse a [pricing] table of {model = {input = x, output = y}}."""
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, tuple[float, float]] = {}
    for model, rates in raw.items():
        if isinstance(rates, dict) and "input" in rates and "output" in rates:
            try:
                parsed[str(model).lower()] = (float(rates["input"]), float(rates["output"]))
            except (TypeError, ValueError):
                continue
    return parsed


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
        max_retries=int(llm_raw.get("max_retries", 3)),
        retry_backoff=float(llm_raw.get("retry_backoff", 1.5)),
    )

    # ---- output ------------------------------------------------------------
    locale_str = _first_env("OFFERPRINTER_LOCALE") or out_raw.get("locale", "UK")
    env_formats = _first_env("OFFERPRINTER_FORMATS")
    output = OutputConfig(
        locale=Locale(locale_str.upper()),
        dir=_first_env("OFFERPRINTER_OUTPUT_DIR") or out_raw.get("dir", "./output"),
        formats=_clean_formats(
            env_formats.split(",") if env_formats else out_raw.get("formats", ["md", "docx"])
        ),
        track=_env_bool("OFFERPRINTER_TRACK", bool(out_raw.get("track", True))),
    )

    # ---- generation --------------------------------------------------------
    generation = GenerationConfig(
        tailored_cv=bool(gen_raw.get("tailored_cv", True)),
        cover_letter=bool(gen_raw.get("cover_letter", True)),
        fit_memo=bool(gen_raw.get("fit_memo", True)),
        ats_report=bool(gen_raw.get("ats_report", True)),
        interview_prep=bool(gen_raw.get("interview_prep", True)),
        fit_score=bool(gen_raw.get("fit_score", True)),
        parallel=_env_bool("OFFERPRINTER_PARALLEL", bool(gen_raw.get("parallel", True))),
        max_workers=int(gen_raw.get("max_workers", 5)),
    )

    return Config(
        llm=llm,
        output=output,
        generation=generation,
        pricing=_parse_pricing(data.get("pricing")),
    )
