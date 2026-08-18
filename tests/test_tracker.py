"""Tests for the local application tracker, stats, and achievements."""

from __future__ import annotations

import json

import pytest

from offerprinter.services.tracker import (
    ApplicationRecord,
    Tracker,
    describe,
    summarise,
    unlocked,
    utc_now,
)


def _record(**overrides) -> ApplicationRecord:
    defaults = dict(
        slug="acme-analyst",
        company="Acme",
        role="Analyst",
        printed_at=utc_now(),
        provider="anthropic",
        model="claude-haiku-4-5",
        fit_score=72,
        fit_band="Strong",
        cost_usd=0.03,
        total_tokens=12_000,
    )
    defaults.update(overrides)
    return ApplicationRecord(**defaults)


def test_records_round_trip(tmp_path):
    tracker = Tracker(home=tmp_path)
    tracker.record(_record())
    tracker.record(_record(slug="beta-engineer", company="Beta", role="Engineer"))

    loaded = tracker.load()
    assert [r.slug for r in loaded] == ["acme-analyst", "beta-engineer"]
    assert loaded[0].fit_score == 72


def test_empty_history_is_not_an_error(tmp_path):
    assert Tracker(home=tmp_path).load() == []


def test_corrupt_history_does_not_raise(tmp_path):
    tracker = Tracker(home=tmp_path)
    tracker.home.mkdir(parents=True, exist_ok=True)
    tracker.path.write_text("{ not json at all", encoding="utf-8")
    assert tracker.load() == []


def test_one_bad_row_does_not_lose_the_others(tmp_path):
    tracker = Tracker(home=tmp_path)
    tracker.home.mkdir(parents=True, exist_ok=True)
    tracker.path.write_text(
        json.dumps([{"nonsense": True}, _record().model_dump()]), encoding="utf-8"
    )
    assert len(tracker.load()) == 1


def test_set_status(tmp_path):
    tracker = Tracker(home=tmp_path)
    tracker.record(_record())

    updated = tracker.set_status("acme-analyst", "interview")
    assert updated is not None
    assert updated.status == "interview"
    assert tracker.load()[0].status == "interview"

    assert tracker.set_status("nope", "applied") is None


def test_set_status_rejects_unknown_status(tmp_path):
    tracker = Tracker(home=tmp_path)
    tracker.record(_record())
    with pytest.raises(ValueError, match="Unknown status"):
        tracker.set_status("acme-analyst", "vibes")


def test_summarise():
    records = [
        _record(fit_score=60, cost_usd=0.02, total_tokens=1000),
        _record(slug="b", company="Beta", fit_score=90, cost_usd=0.04, total_tokens=3000),
        _record(
            slug="c",
            company="Beta",
            fit_score=None,
            status="interview",
            cost_usd=0.0,
            total_tokens=0,
        ),
    ]
    stats = summarise(records)

    assert stats.total == 3
    assert stats.companies == 2
    assert stats.average_fit == 75.0
    assert stats.best_fit == 90
    assert stats.total_tokens == 4000
    assert stats.by_status == {"printed": 2, "interview": 1}


def test_summarise_of_nothing_is_zeroed():
    assert summarise([]).total == 0


# --- achievements ------------------------------------------------------------


def test_no_achievements_without_history():
    assert unlocked([]) == set()


def test_first_print_unlocks_on_the_first_run():
    assert "first_print" in unlocked([_record()])


def test_count_milestones():
    five = [_record(slug=f"s{i}") for i in range(5)]
    assert "five_printed" in unlocked(five)
    assert "ten_printed" not in unlocked(five)

    ten = [_record(slug=f"s{i}") for i in range(10)]
    assert "ten_printed" in unlocked(ten)


def test_thrifty_needs_both_volume_and_low_spend():
    cheap = [_record(slug=f"s{i}", cost_usd=0.02) for i in range(10)]
    assert "thrifty" in unlocked(cheap)

    pricey = [_record(slug=f"s{i}", cost_usd=0.50) for i in range(10)]
    assert "thrifty" not in unlocked(pricey)


def test_score_based_achievements():
    assert "strong_fit" in unlocked([_record(fit_score=88)])
    assert "honest_stretch" in unlocked([_record(fit_score=44)])
    assert "honest_stretch" not in unlocked([_record(fit_score=None)])


def test_local_hero_needs_a_local_model():
    assert "local_hero" in unlocked([_record(provider="ollama")])
    assert "local_hero" not in unlocked([_record(provider="anthropic")])


def test_offer_implies_interview():
    earned = unlocked([_record(status="offer")])
    assert {"offer", "interview"} <= earned


def test_record_returns_only_newly_unlocked(tmp_path):
    tracker = Tracker(home=tmp_path)
    first = tracker.record(_record())
    assert "first_print" in first

    second = tracker.record(_record(slug="b"))
    # Already-earned achievements must not be announced twice.
    assert "first_print" not in second


def test_describe_is_human_readable():
    assert "First Print" in describe("first_print")
    assert describe("not_a_real_id")  # unknown ids must not crash the CLI
