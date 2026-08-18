"""Tests for cost estimation and the provider retry/backoff layer."""

from __future__ import annotations

import httpx
import pytest

from offerprinter.llm.base import LLMError, LLMProvider
from offerprinter.models.schemas import LLMConfig, Provider
from offerprinter.pricing import estimate_cost, format_cost, rates_for

# --- pricing -----------------------------------------------------------------


def test_exact_model_match():
    assert rates_for("gpt-4o-mini") == (0.15, 0.60)


def test_longest_prefix_wins():
    """A dated model id must resolve to its family, and the specific beats the general."""
    assert rates_for("claude-haiku-4-5-20251001") == (1.00, 5.00)
    # "gpt-4o-mini-2024-07-18" must not fall back to plain "gpt-4o".
    assert rates_for("gpt-4o-mini-2024-07-18") == (0.15, 0.60)


def test_local_models_are_free():
    assert rates_for("llama3.1") == (0.0, 0.0)
    assert rates_for("qwen2.5:14b") == (0.0, 0.0)


def test_unknown_model_reports_no_cost():
    assert rates_for("some-model-nobody-has-heard-of") == (0.0, 0.0)
    assert rates_for("") == (0.0, 0.0)


def test_overrides_beat_the_built_in_table():
    overrides = {"gpt-4o-mini": (0.0, 0.0)}
    assert rates_for("gpt-4o-mini", overrides) == (0.0, 0.0)
    assert rates_for("gpt-4o-mini-2024-07-18", overrides) == (0.0, 0.0)


def test_estimate_cost_is_per_million_tokens():
    # 1M in + 1M out at (1.0, 5.0) = $6.00
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6.0)


def test_format_cost():
    assert format_cost(0) == "free (local model)"
    assert "£" in format_cost(0.05)
    assert format_cost(0.0004).startswith("$0.0004")


# --- retries -----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.Client, replaying a scripted list of responses."""

    def __init__(self, responses: list, calls: list):
        self._responses = responses
        self._calls = calls

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        self._calls.append(url)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Provider(LLMProvider):
    default_model = "test-model"
    requires_key = False

    def complete(self, system: str, user: str) -> str:
        return str(self._post("https://example.test/v1", {}, {}))


@pytest.fixture
def no_sleep(monkeypatch):
    """Retry backoff is real seconds; tests should not actually wait."""
    monkeypatch.setattr("offerprinter.llm.base.time.sleep", lambda _: None)


def _provider_with(monkeypatch, responses, calls, **config):
    monkeypatch.setattr(httpx, "Client", _FakeClient(responses, calls))
    return _Provider(LLMConfig(provider=Provider.OPENAI, **config))


def test_succeeds_first_time(monkeypatch, no_sleep):
    calls: list = []
    provider = _provider_with(monkeypatch, [_FakeResponse(200, {"ok": True})], calls)
    assert "ok" in provider.complete("s", "u")
    assert len(calls) == 1


def test_retries_a_rate_limit_then_succeeds(monkeypatch, no_sleep):
    calls: list = []
    provider = _provider_with(
        monkeypatch,
        [_FakeResponse(429), _FakeResponse(429), _FakeResponse(200, {"ok": True})],
        calls,
    )
    assert "ok" in provider.complete("s", "u")
    assert len(calls) == 3


def test_retries_server_errors(monkeypatch, no_sleep):
    calls: list = []
    provider = _provider_with(
        monkeypatch, [_FakeResponse(503), _FakeResponse(200, {"ok": True})], calls
    )
    provider.complete("s", "u")
    assert len(calls) == 2


def test_retries_network_errors(monkeypatch, no_sleep):
    calls: list = []
    provider = _provider_with(
        monkeypatch,
        [httpx.ConnectError("boom"), _FakeResponse(200, {"ok": True})],
        calls,
    )
    provider.complete("s", "u")
    assert len(calls) == 2


def test_gives_up_after_max_retries(monkeypatch, no_sleep):
    calls: list = []
    provider = _provider_with(monkeypatch, [_FakeResponse(429)] * 3, calls, max_retries=2)
    with pytest.raises(LLMError, match="gave up after 3 attempts"):
        provider.complete("s", "u")
    assert len(calls) == 3


def test_auth_errors_are_not_retried(monkeypatch, no_sleep):
    """Retrying a 401 wastes the user's time and cannot possibly succeed."""
    calls: list = []
    provider = _provider_with(monkeypatch, [_FakeResponse(401)], calls)
    with pytest.raises(LLMError, match="401"):
        provider.complete("s", "u")
    assert len(calls) == 1


def test_retry_after_header_is_honoured(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("offerprinter.llm.base.time.sleep", slept.append)
    calls: list = []
    provider = _provider_with(
        monkeypatch,
        [_FakeResponse(429, headers={"retry-after": "7"}), _FakeResponse(200, {"ok": 1})],
        calls,
    )
    provider.complete("s", "u")
    # 7 seconds from the header, plus a little jitter.
    assert 7.0 <= slept[0] <= 7.3


def test_absurd_retry_after_is_ignored(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("offerprinter.llm.base.time.sleep", slept.append)
    calls: list = []
    provider = _provider_with(
        monkeypatch,
        [_FakeResponse(429, headers={"retry-after": "3600"}), _FakeResponse(200, {"ok": 1})],
        calls,
        retry_backoff=1.0,
    )
    provider.complete("s", "u")
    assert slept[0] < 2.0  # falls back to our own backoff, not an hour


def test_non_json_response_is_a_clear_error(monkeypatch, no_sleep):
    class _BadJSON(_FakeResponse):
        def json(self):
            raise ValueError("not json")

    provider = _provider_with(monkeypatch, [_BadJSON(200)], [])
    with pytest.raises(LLMError, match="non-JSON"):
        provider.complete("s", "u")


# --- usage accounting --------------------------------------------------------


def test_usage_accumulates_thread_safely():
    """Parallel artifact generation records usage from several threads at once."""
    from concurrent.futures import ThreadPoolExecutor

    provider = _Provider(LLMConfig(provider=Provider.OPENAI))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: provider._record_usage(10, 5), range(200)))

    assert provider.usage.calls == 200
    assert provider.usage.input_tokens == 2000
    assert provider.usage.output_tokens == 1000
    assert provider.usage.total_tokens == 3000
