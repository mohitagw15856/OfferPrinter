"""Token pricing, so every run can tell you what it actually cost.

The numbers below are **published list prices in USD per 1,000,000 tokens**, and
they are estimates for display only — providers change prices, and your account
may have different rates. Nothing here affects generation; it only turns token
counts into a "this run cost about £0.03" line.

Override any of them in `config.toml`:

    [pricing]
    "claude-haiku-4-5-20251001" = { input = 1.0, output = 5.0 }

Unknown models fall back to a match on the closest known prefix, and finally to
zero (in which case OfferPrinter reports tokens but no cost).
"""

from __future__ import annotations

# model prefix -> (USD per 1M input tokens, USD per 1M output tokens)
_PRICES: dict[str, tuple[float, float]] = {
    # --- Anthropic -----------------------------------------------------------
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    # --- OpenAI --------------------------------------------------------------
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # --- Google --------------------------------------------------------------
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    # --- Moonshot ------------------------------------------------------------
    "moonshot-v1-8k": (1.68, 1.68),
    "moonshot-v1-32k": (3.36, 3.36),
    "moonshot-v1-128k": (8.40, 8.40),
    "kimi-": (1.68, 1.68),
}

#: Models that run on your own hardware and therefore cost nothing per token.
_FREE_PREFIXES = ("llama", "qwen", "mistral", "phi", "gemma", "deepseek", "stub")

#: Rough USD -> GBP rate, only used for the friendly "≈ £0.03" hint.
USD_TO_GBP = 0.79


def rates_for(
    model: str, overrides: dict[str, tuple[float, float]] | None = None
) -> tuple[float, float]:
    """Return (input_price, output_price) per 1M tokens for a model name."""
    if not model:
        return (0.0, 0.0)
    name = model.lower()

    if overrides:
        if name in overrides:
            return overrides[name]
        for prefix, rate in overrides.items():
            if name.startswith(prefix.lower()):
                return rate

    if name.startswith(_FREE_PREFIXES):
        return (0.0, 0.0)

    if name in _PRICES:
        return _PRICES[name]
    # Longest matching prefix wins, so "gpt-4o-mini" beats "gpt-4o".
    matches = [p for p in _PRICES if name.startswith(p)]
    if matches:
        return _PRICES[max(matches, key=len)]
    return (0.0, 0.0)


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    overrides: dict[str, tuple[float, float]] | None = None,
) -> float:
    """Estimated USD cost for a number of input/output tokens."""
    in_rate, out_rate = rates_for(model, overrides)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def format_cost(usd: float) -> str:
    """Human-friendly cost string, tiny amounts included."""
    if usd <= 0:
        return "free (local model)"
    gbp = usd * USD_TO_GBP
    if usd < 0.01:
        return f"${usd:.4f} (≈ £{gbp:.4f})"
    return f"${usd:.3f} (≈ £{gbp:.3f})"
