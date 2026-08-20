"""Tests for the services added in 0.3: redaction, caching, diffing, ranking,
job-description extraction and the MCP server.
"""

from __future__ import annotations

import io
import json

import pytest

from offerprinter.models.schemas import LLMConfig, Provider, ResumeInput
from offerprinter.services.cache import CachedProvider, ResponseCache
from offerprinter.services.differ import diff_cv
from offerprinter.services.jd_fetcher import extract_job_posting
from offerprinter.services.ranker import collect_jobs, sort_results
from offerprinter.services.redactor import Redactor, guess_name, redact_cv
from tests.conftest import StubProvider

CV = """# Alex Morgan

alex.morgan@example.com · +44 7700 900123 · Manchester, UK · linkedin.com/in/alexmorgan

## Experience
### Marketing Data Analyst — BrightWave Retail
- Ran 30+ A/B tests; one lifted conversion by 8%.
- Alex led the weekly analytics review.
"""


# --- redaction ---------------------------------------------------------------


def test_guess_name_finds_the_heading_name():
    assert guess_name(CV) == "Alex Morgan"


@pytest.mark.parametrize(
    "text",
    [
        "# Curriculum Vitae\n\nSomething else\n",
        "# Professional Summary\n\nA data analyst.\n",
        "no capitalised name anywhere here\n",
    ],
)
def test_guess_name_declines_rather_than_guessing_wildly(text):
    assert guess_name(text) is None


def test_redaction_removes_identifiers():
    redacted, redactor = redact_cv(CV)

    for secret in ("Alex Morgan", "alex.morgan@example.com", "+44 7700 900123"):
        assert secret not in redacted, f"{secret} survived redaction"
    assert "linkedin.com/in/alexmorgan" not in redacted
    assert redactor.redaction.count > 0


def test_redaction_keeps_the_facts_the_model_needs():
    redacted, _ = redact_cv(CV)
    assert "BrightWave Retail" in redacted
    assert "30+ A/B tests" in redacted
    assert "8%" in redacted


def test_redaction_round_trips():
    redacted, redactor = redact_cv(CV)
    assert redactor.restore(redacted) == CV


def test_restore_works_on_generated_output():
    """The model echoes placeholders; restoring must put the real name back."""
    _, redactor = redact_cv(CV)
    placeholder = next(iter(redactor.redaction.mapping))
    generated = f"# {placeholder}\n\nA tailored CV.\n"
    assert "Alex" in redactor.restore(generated)


def test_repeated_values_reuse_one_placeholder():
    redactor = Redactor()
    redactor.redact("Email me at a@b.com or a@b.com please.")
    emails = [v for v in redactor.redaction.mapping.values() if "@" in v]
    assert len(emails) == 1


def test_metrics_are_not_mistaken_for_phone_numbers():
    redactor = Redactor(name="Nobody Here")
    out = redactor.redact("Grew revenue by 1200 and shipped 30 tests in 2024.")
    assert "1200" in out and "2024" in out


def test_redaction_kinds_are_reported():
    _, redactor = redact_cv(CV)
    kinds = redactor.redaction.kinds()
    assert "name" in kinds and "email" in kinds


# --- caching -----------------------------------------------------------------


def test_cache_round_trip(tmp_path):
    cache = ResponseCache(directory=tmp_path)
    key = ResponseCache.key("anthropic", "haiku", "sys", "user")
    assert cache.get(key) is None
    cache.put(key, "hello")
    assert cache.get(key) == "hello"
    assert cache.hits == 1 and cache.misses == 1


def test_cache_key_changes_with_every_input():
    base = ResponseCache.key("anthropic", "haiku", "sys", "user")
    assert base != ResponseCache.key("openai", "haiku", "sys", "user")
    assert base != ResponseCache.key("anthropic", "sonnet", "sys", "user")
    assert base != ResponseCache.key("anthropic", "haiku", "other", "user")
    assert base != ResponseCache.key("anthropic", "haiku", "sys", "other")
    assert base != ResponseCache.key("anthropic", "haiku", "sys", "user", "temp=1")


def test_cache_key_cannot_be_confused_by_field_boundaries():
    """ "ab"+"c" and "a"+"bc" must not collide."""
    assert ResponseCache.key("ab", "c", "", "") != ResponseCache.key("a", "bc", "", "")


def test_expired_entries_are_ignored(tmp_path):
    """Age out old entries without depending on clock resolution."""
    import json as _json

    cache = ResponseCache(directory=tmp_path, ttl_days=1)
    key = ResponseCache.key("p", "m", "s", "u")
    cache.put(key, "stale")

    # Backdate the entry rather than sleeping or trusting a zero TTL: time.time()
    # is only accurate to ~16ms on Windows, which made the zero-TTL version flaky.
    path = cache._path(key)
    payload = _json.loads(path.read_text(encoding="utf-8"))
    payload["stored_at"] -= 2 * 86400
    path.write_text(_json.dumps(payload), encoding="utf-8")

    assert cache.get(key) is None
    assert not path.exists(), "an expired entry should be cleaned up"


def test_zero_ttl_disables_the_cache(tmp_path):
    cache = ResponseCache(directory=tmp_path, ttl_days=0)
    key = ResponseCache.key("p", "m", "s", "u")
    cache.put(key, "never served")
    assert cache.get(key) is None


def test_cached_provider_only_calls_through_once(tmp_path):
    class Counting(StubProvider):
        calls = 0

        def complete(self, system: str, user: str) -> str:
            Counting.calls += 1
            return super().complete(system, user)

    inner = Counting(LLMConfig(provider=Provider.ANTHROPIC))
    provider = CachedProvider(inner, ResponseCache(directory=tmp_path))

    first = provider.complete("sys", "write something")
    second = provider.complete("sys", "write something")

    assert first == second
    assert Counting.calls == 1
    # Usage is only recorded on the miss — a cached answer really was free.
    assert provider.usage.calls == 1


def test_cache_stats_and_clear(tmp_path):
    cache = ResponseCache(directory=tmp_path)
    cache.put(ResponseCache.key("p", "m", "s", "u"), "x")
    entries, size = cache.stats()
    assert entries == 1 and size > 0
    assert cache.clear() == 1
    assert cache.stats() == (0, 0)


def test_corrupt_cache_entry_is_a_miss(tmp_path):
    cache = ResponseCache(directory=tmp_path)
    key = ResponseCache.key("p", "m", "s", "u")
    path = cache._path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{{{not json", encoding="utf-8")
    assert cache.get(key) is None


# --- tailoring diff ----------------------------------------------------------


def test_diff_detects_rewording():
    original = "- Wrote Python scripts to clean and join campaign data every week.\n"
    tailored = "- Modelled and joined campaign data with Python, weekly.\n"
    diff = diff_cv(original, tailored)
    assert len(diff.reworded) == 1
    assert "Wrote Python" in diff.reworded[0].before


def test_diff_detects_additions_and_drops():
    diff = diff_cv(
        "- Kept this one exactly as written.\n", "- A completely different claim here.\n"
    )
    assert diff.added or diff.dropped


def test_diff_counts_unchanged_lines():
    text = "- Ran 30+ A/B tests on email campaigns.\n- Mentored a junior analyst weekly.\n"
    diff = diff_cv(text, text)
    assert diff.kept == 2
    assert not diff.changes


def test_diff_unwraps_hard_wrapped_paragraphs():
    """Source CVs wrap at 80 columns; fragments would make the diff nonsense."""
    original = "Data analyst with four years\nof experience owning analysis\nend to end.\n"
    tailored = "Data analyst with four years of experience owning analysis end to end.\n"
    diff = diff_cv(original, tailored)
    assert diff.kept == 1
    assert not diff.changes


def test_diff_reports_new_vocabulary():
    diff = diff_cv("- Built dashboards.\n", "- Built dashboards and experimentation reporting.\n")
    assert "experimentation" in diff.new_terms


def test_diff_markdown_warns_about_additions():
    markdown = diff_cv("- One thing entirely.\n", "- Something else entirely new.\n").as_markdown()
    assert "What Tailoring Changed" in markdown


# --- job description extraction ----------------------------------------------

JSON_LD_PAGE = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Senior Product Analyst",
 "hiringOrganization":{"@type":"Organization","name":"NorthBank"},
 "description":"<p>We need a <b>Senior Product Analyst</b>.</p><ul><li>SQL and Python</li><li>Experimentation</li></ul><p>You will own metrics end to end and turn analysis into decisions that ship to customers.</p>"}
</script></head><body><nav>Jobs</nav></body></html>"""


def test_extract_job_posting_from_json_ld():
    description, company, role = extract_job_posting(JSON_LD_PAGE)
    assert company == "NorthBank"
    assert role == "Senior Product Analyst"
    assert "- SQL and Python" in description
    assert "<p>" not in description


def test_extract_job_posting_returns_none_without_structured_data():
    assert extract_job_posting("<html><body>Nothing here</body></html>") is None


def test_extract_job_posting_survives_broken_json():
    page = '<script type="application/ld+json">{not json at all</script>'
    assert extract_job_posting(page) is None


def test_extract_job_posting_ignores_other_schema_types():
    page = (
        '<script type="application/ld+json">'
        '{"@type":"Organization","name":"NorthBank","description":"' + "x" * 300 + '"}'
        "</script>"
    )
    assert extract_job_posting(page) is None


# --- ranking -----------------------------------------------------------------


def test_collect_jobs_reads_a_directory(tmp_path):
    (tmp_path / "one.md").write_text("Analyst role", encoding="utf-8")
    (tmp_path / "two.txt").write_text("Engineer role", encoding="utf-8")
    (tmp_path / "ignore.pdf").write_bytes(b"%PDF")

    jobs = collect_jobs(directory=tmp_path)
    assert [name for name, _ in jobs] == ["one.md", "two.txt"]


def test_collect_jobs_combines_sources(tmp_path):
    path = tmp_path / "role.md"
    path.write_text("A role", encoding="utf-8")
    jobs = collect_jobs(paths=[path], urls=["https://example.com/job"])
    assert len(jobs) == 2


def test_sort_results_puts_best_first_and_errors_last():
    from offerprinter.models.schemas import FitScore, RankedJob

    results = [
        RankedJob(source="c", fit=FitScore(score=40)),
        RankedJob(source="broken", error="404"),
        RankedJob(source="a", fit=FitScore(score=90)),
    ]
    assert [r.source for r in sort_results(results)] == ["a", "c", "broken"]


# --- MCP server --------------------------------------------------------------


def _rpc(server, method: str, params: dict | None = None, request_id: int = 1):
    return server.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    )


@pytest.fixture
def mcp_server():
    from offerprinter.mcp_server import OfferPrinterMCP

    return OfferPrinterMCP()


def test_mcp_initialize(mcp_server):
    result = _rpc(mcp_server, "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert result["serverInfo"]["name"] == "offerprinter"
    assert result["protocolVersion"] == "2025-06-18"
    assert "never invents" in result["instructions"]


def test_mcp_lists_its_tools(mcp_server):
    tools = _rpc(mcp_server, "tools/list")["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {"print_application_package", "score_fit", "rank_jobs", "roast_cv"}
    for tool in tools:
        assert tool["description"] and tool["inputSchema"]["type"] == "object"


def test_mcp_unknown_tool_is_an_error(mcp_server):
    response = _rpc(mcp_server, "tools/call", {"name": "nope", "arguments": {}})
    assert "error" in response
    assert "Unknown tool" in response["error"]["message"]


def test_mcp_unknown_method_is_an_error(mcp_server):
    assert "error" in _rpc(mcp_server, "does/not/exist")


def test_mcp_notifications_get_no_reply(mcp_server):
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_refuses_to_work_without_a_cv(mcp_server):
    response = _rpc(mcp_server, "tools/call", {"name": "roast_cv", "arguments": {}})
    assert "error" in response
    assert "never invent a CV" in response["error"]["message"]


def test_mcp_serve_reads_newline_delimited_json(mcp_server):
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    )
    stdout = io.StringIO()
    mcp_server.serve(stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [r["id"] for r in responses] == [1, 2]  # the notification produced nothing


def test_mcp_serve_reports_parse_errors(mcp_server):
    stdout = io.StringIO()
    mcp_server.serve(stdin=io.StringIO("{not json\n"), stdout=stdout)
    assert json.loads(stdout.getvalue())["error"]["code"] == -32700


# --- practice + follow-ups ---------------------------------------------------


def test_followup_rejects_unknown_kind():
    from offerprinter.services.generator import Generator

    generator = Generator(StubProvider(LLMConfig(provider=Provider.ANTHROPIC)))
    with pytest.raises(ValueError, match="Unknown follow-up"):
        generator.followup(
            "carrier-pigeon",
            ResumeInput(text="cv"),
            __import__("offerprinter.models.schemas", fromlist=["JobDescription"]).JobDescription(
                text="jd"
            ),
            "Acme",
            "Analyst",
        )


def test_every_followup_prompt_forbids_invention():
    from offerprinter.prompts import FOLLOWUP_PROMPTS

    for _key, (_title, _filename, prompt) in FOLLOWUP_PROMPTS.items():
        assert "never invent" in prompt.lower() or "Never invent" in prompt


def test_practice_feedback_prompt_refuses_to_coach_fabrication():
    from offerprinter.prompts import PRACTICE_FEEDBACK_PROMPT

    assert "Never coach them to claim experience they do not have" in PRACTICE_FEEDBACK_PROMPT
