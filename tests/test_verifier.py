"""Tests for the fabrication verifier.

Two properties matter, and they pull against each other:

* it must **catch** invented numbers, dates, employers, tools and credentials;
* it must **not fire** on honest output, because a checker nobody trusts gets
  switched off and then protects nothing.

Most of these tests are therefore about the second property.
"""

from __future__ import annotations

import pytest

from offerprinter.models.schemas import (
    ApplicationPackage,
    Artifact,
    JobDescription,
    ResumeInput,
    Severity,
)
from offerprinter.services.verifier import (
    Verifier,
    _parse_missing_keywords,
    verify_package,
)

CV = """# Alex Morgan
alex@example.com · Manchester, UK

## Experience
### Marketing Data Analyst — BrightWave Retail
March 2022 - Present
- Owned analytics end to end: defined metrics, built datasets in SQL (PostgreSQL).
- Designed and ran 30+ A/B tests; a checkout-copy test lifted conversion by 8%.
- Mentored a junior analyst, reviewing their SQL weekly.

### Junior Data Analyst — Kettle & Co (Leeds)
July 2020 - February 2022
- Automated a sales-collation task in Python, saving ~5 hours a week.

## Education
BSc Economics, University of Leeds, 2020.
"""

JD = """Senior Product Analyst at NorthBank.
We need SQL, experimentation, and stakeholder communication.
Experience with dbt and financial services is a plus.
"""


def build(tailored: str = "", cover: str = "", ats: str = "") -> ApplicationPackage:
    artifacts = []
    if tailored:
        artifacts.append(Artifact(key="tailored_cv", title="T", filename="t", content=tailored))
    if cover:
        artifacts.append(Artifact(key="cover_letter", title="C", filename="c", content=cover))
    if ats:
        artifacts.append(Artifact(key="ats_report", title="A", filename="a", content=ats))
    return ApplicationPackage(
        company="NorthBank", role="Senior Product Analyst", slug="s", artifacts=artifacts
    )


def check(tailored: str = "", cover: str = "", ats: str = ""):
    return verify_package(
        build(tailored, cover, ats), ResumeInput(text=CV), JobDescription(text=JD)
    )


def claims(verification) -> set[str]:  # noqa: ANN001
    return {f.claim.strip(".") for f in verification.findings}


# --- it must not cry wolf ----------------------------------------------------


def test_faithful_restatement_passes():
    verification = check(
        tailored="""# Alex Morgan

## Experience
### Marketing Data Analyst — BrightWave Retail
March 2022 - Present
- Defined metrics and built datasets in SQL (PostgreSQL), owning analytics end to end.
- Ran 30+ A/B tests; a checkout-copy test lifted conversion by 8%.
"""
    )
    assert verification.passed, [f.as_line() for f in verification.findings]


def test_empty_package_passes():
    assert check().passed


def test_sentence_openers_are_not_entities():
    verification = check(
        tailored="Delivered results. Managed a team. However the work continued.\n"
    )
    assert verification.passed, [f.as_line() for f in verification.findings]


def test_headings_are_not_entities():
    verification = check(tailored="# Professional Summary\n\n## Core Skills\n\n### Education\n")
    assert verification.passed, [f.as_line() for f in verification.findings]


def test_short_acronyms_are_ignored():
    """SQL and AWS are too generic to attribute to a specific employer."""
    verification = check(tailored="- Used SQL and API tooling daily.\n")
    assert verification.passed


def test_number_formatting_differences_are_tolerated():
    """'8%' in output vs '8%' in the CV must match despite punctuation."""
    verification = check(tailored="- Lifted conversion by 8%, roughly 5 hours saved weekly.\n")
    assert verification.passed, [f.as_line() for f in verification.findings]


def test_cover_letter_may_name_the_target_company():
    verification = check(cover="Dear Hiring Team,\n\nI am applying to NorthBank.\n")
    assert verification.passed, [f.as_line() for f in verification.findings]


def test_cover_letter_may_use_job_advert_vocabulary():
    """A cover letter addresses the advert; that is not a claim of experience."""
    verification = check(cover="Your work in financial services is why I applied.\n")
    assert verification.passed, [f.as_line() for f in verification.findings]


# --- it must catch the things that matter ------------------------------------


def test_catches_inflated_metric():
    verification = check(tailored="- A checkout test lifted conversion by 41%.\n")
    assert "41%" in claims(verification)
    assert verification.high


def test_catches_invented_date():
    verification = check(tailored="- Analyst at BrightWave Retail since 2015.\n")
    assert "2015" in claims(verification)
    assert verification.findings[0].severity is Severity.HIGH


def test_catches_invented_employer():
    verification = check(tailored="- Consultant at Deloitte on pricing work.\n")
    assert "Deloitte" in claims(verification)


def test_catches_invented_certification():
    verification = check(tailored="- Certified Snowflake Data Engineer.\n")
    assert any("Snowflake" in claim for claim in claims(verification))


def test_tailored_cv_may_not_borrow_advert_vocabulary():
    """The distinction the whole module turns on: CV is stricter than letter."""
    # "Financial Services" is in the advert and nowhere in the CV.
    borrowed = "I have deep Financial Services exposure.\n"
    assert not check(tailored=borrowed).passed
    # The same words in a cover letter are fine — it addresses the advert.
    assert check(cover=borrowed).passed


def test_catches_lowercase_tool_via_ats_cross_check():
    """'dbt' never looks like a proper noun, so the ATS report catches it."""
    ats = "## Missing keywords\n- dbt\n- fintech\n\n## Coverage summary\nCovered 3 of 9.\n"
    verification = check(tailored="- Built transformation models in dbt.\n", ats=ats)
    assert "dbt" in claims(verification)
    finding = next(f for f in verification.findings if f.claim == "dbt")
    assert finding.severity is Severity.HIGH
    assert finding.kind == "ats-gap"


def test_ats_cross_check_ignores_keywords_the_cv_actually_has():
    """If the report and the CV disagree, trust the CV."""
    ats = "## Missing keywords\n- SQL\n- Python\n"
    verification = check(tailored="- Built datasets in SQL and Python.\n", ats=ats)
    assert verification.passed


def test_findings_carry_context():
    verification = check(tailored="- Consultant at Deloitte on pricing work.\n")
    assert "Deloitte" in verification.findings[0].context


# --- reporting ---------------------------------------------------------------


def test_summary_counts_are_honest():
    verification = check(tailored="- Lifted conversion by 41% while at Deloitte.\n")
    assert verification.claims_checked > 0
    assert str(len(verification.findings)) in verification.summary()


def test_markdown_report_lists_findings():
    markdown = check(tailored="- Lifted conversion by 41%.\n").as_markdown()
    assert "Fabrication Check" in markdown
    assert "41%" in markdown
    assert "High severity" in markdown


def test_markdown_report_when_clean():
    markdown = check(tailored="- Ran 30+ A/B tests.\n").as_markdown()
    assert "Nothing was invented" in markdown


# --- the ATS "missing keywords" parser ---------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("## Missing keywords\n- dbt\n- Kafka\n", ["dbt", "Kafka"]),
        ("## Missing keywords\n- **dbt**\n", ["dbt"]),
        (
            "## Missing keywords\n- Product analytics / product metrics\n",
            ["Product analytics", "product metrics"],
        ),
        ("## Missing keywords\n- dbt — Do not add, a genuine gap\n", ["dbt"]),
        ("## Missing keywords\n- Airflow (orchestration)\n", ["Airflow"]),
        ("## Covered keywords\n- SQL\n", []),
        ("no headings at all", []),
    ],
)
def test_parse_missing_keywords(report, expected):
    assert _parse_missing_keywords(report) == expected


def test_parser_stops_at_the_next_section():
    report = "## Missing keywords\n- dbt\n\n## How to add the missing terms\n- Something else\n"
    assert _parse_missing_keywords(report) == ["dbt"]


def test_verifier_accepts_target_company_not_in_cv():
    verifier = Verifier(
        ResumeInput(text=CV), JobDescription(text=JD), company="Acme Corp", role="Analyst"
    )
    assert verifier._entity_is_sourced("Acme Corp", allow_jd=False)
