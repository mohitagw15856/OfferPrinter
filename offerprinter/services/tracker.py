"""A local record of every application you have printed.

Job hunting is a long, demoralising process with no scoreboard. This module is
the scoreboard. Every run appends a row to a plain JSON file in
``~/.offerprinter/applications.json`` — no server, no account, no sync, just a
file you own and can delete, grep, or check into your own private repo.

It powers three things:
  * ``offerprinter list``   — everything you have applied for
  * ``offerprinter stats``  — totals, spend, average fit, outcomes
  * achievements            — the small, silly nudges that keep you going

Nothing here ever leaves your machine.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

#: Where applications are recorded. Override with OFFERPRINTER_HOME.
DEFAULT_HOME = Path.home() / ".offerprinter"

#: Valid values for a record's `status` field, in pipeline order.
STATUSES = ("printed", "applied", "screening", "interview", "offer", "rejected")


class ApplicationRecord(BaseModel):
    """One printed application package."""

    slug: str
    company: str
    role: str
    printed_at: str  # ISO-8601 UTC
    provider: str = ""
    model: str = ""
    fit_score: int | None = None
    fit_band: str = ""
    cost_usd: float = 0.0
    total_tokens: int = 0
    output_dir: str = ""
    status: str = "printed"
    notes: str = ""

    @property
    def printed_date(self) -> str:
        return self.printed_at[:10]


class Tracker:
    """Read/write access to the local application history."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home or os.environ.get("OFFERPRINTER_HOME") or DEFAULT_HOME)
        self.path = self.home / "applications.json"

    # -- persistence --------------------------------------------------------

    def load(self) -> list[ApplicationRecord]:
        """Return every record, oldest first. A corrupt file is never fatal."""
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        records = []
        for item in raw if isinstance(raw, list) else []:
            try:
                records.append(ApplicationRecord(**item))
            except (TypeError, ValueError):
                continue  # skip a bad row rather than losing the whole history
        return records

    def save(self, records: list[ApplicationRecord]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = [r.model_dump() for r in records]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # -- mutations ----------------------------------------------------------

    def record(self, record: ApplicationRecord) -> list[str]:
        """Append a run and return any achievements newly unlocked by it."""
        records = self.load()
        before = unlocked(records)
        records.append(record)
        self.save(records)
        return sorted(unlocked(records) - before)

    def set_status(self, slug: str, status: str) -> ApplicationRecord | None:
        """Update the most recent record for a slug. Returns it, or None."""
        if status not in STATUSES:
            raise ValueError(f"Unknown status '{status}'. Use one of: {', '.join(STATUSES)}")
        records = self.load()
        for record in reversed(records):
            if record.slug == slug:
                record.status = status
                self.save(records)
                return record
        return None


class Stats(BaseModel):
    """Aggregate view of the whole history."""

    total: int = 0
    companies: int = 0
    average_fit: float = 0.0
    best_fit: int = 0
    best_fit_role: str = ""
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    first_printed: str = ""
    last_printed: str = ""


def summarise(records: list[ApplicationRecord]) -> Stats:
    """Roll a list of records up into headline numbers."""
    if not records:
        return Stats()

    scored = [r for r in records if r.fit_score is not None]
    best = max(scored, key=lambda r: r.fit_score or 0, default=None)
    by_status: dict[str, int] = {}
    for record in records:
        by_status[record.status] = by_status.get(record.status, 0) + 1

    return Stats(
        total=len(records),
        companies=len({r.company.lower() for r in records if r.company}),
        average_fit=round(sum(r.fit_score or 0 for r in scored) / len(scored), 1)
        if scored
        else 0.0,
        best_fit=best.fit_score if best and best.fit_score is not None else 0,
        best_fit_role=f"{best.role} at {best.company}" if best else "",
        total_cost_usd=round(sum(r.cost_usd for r in records), 4),
        total_tokens=sum(r.total_tokens for r in records),
        by_status=by_status,
        first_printed=min(r.printed_at for r in records)[:10],
        last_printed=max(r.printed_at for r in records)[:10],
    )


# --- achievements ------------------------------------------------------------
#
# Deliberately small and a bit silly. Job hunting is a grind with almost no
# feedback loop; a line that says "that's ten applications this month" is a
# cheap way to make the grind visible.

#: id -> (emoji, title, description, predicate over the full record list)
ACHIEVEMENTS: dict[str, tuple[str, str, str]] = {
    "first_print": ("🖨", "First Print", "You printed your first application package."),
    "five_printed": ("🖐", "Warmed Up", "Five applications printed."),
    "ten_printed": ("🔟", "Double Digits", "Ten applications printed."),
    "fifty_printed": ("💯", "Machine", "Fifty applications printed."),
    "strong_fit": ("🎯", "Bullseye", "Scored 85+ on a role — apply to that one today."),
    "honest_stretch": ("🧗", "Honest Stretch", "Applied to a role you scored under 50 on. Brave."),
    "five_companies": ("🌍", "Spread Bet", "Applications to five different companies."),
    "thrifty": ("🪙", "Thrifty", "Ten packages printed for under one dollar total."),
    "local_hero": ("🏠", "Local Hero", "Printed a package on a locally-hosted model."),
    "interview": ("🤝", "In The Room", "Marked an application as reaching interview."),
    "offer": ("🏆", "Offer Printed", "Marked an application as an offer. Congratulations."),
}


def unlocked(records: list[ApplicationRecord]) -> set[str]:
    """Return the ids of every achievement earned by this history."""
    if not records:
        return set()

    earned: set[str] = {"first_print"}
    count = len(records)
    if count >= 5:
        earned.add("five_printed")
    if count >= 10:
        earned.add("ten_printed")
    if count >= 50:
        earned.add("fifty_printed")
    if len({r.company.lower() for r in records if r.company}) >= 5:
        earned.add("five_companies")
    if any((r.fit_score or 0) >= 85 for r in records):
        earned.add("strong_fit")
    if any(r.fit_score is not None and r.fit_score < 50 for r in records):
        earned.add("honest_stretch")
    if count >= 10 and sum(r.cost_usd for r in records) < 1.0:
        earned.add("thrifty")
    if any(r.provider == "ollama" for r in records):
        earned.add("local_hero")
    statuses = {r.status for r in records}
    if statuses & {"interview", "offer"}:
        earned.add("interview")
    if "offer" in statuses:
        earned.add("offer")
    return earned


def describe(achievement_id: str) -> str:
    """One-line human description of an achievement, for the CLI."""
    emoji, title, description = ACHIEVEMENTS.get(achievement_id, ("🎖", achievement_id, ""))
    return f"{emoji}  {title} — {description}"


def utc_now() -> str:
    """Current time as an ISO-8601 UTC string (stable, sortable, timezone-safe)."""
    return datetime.now(UTC).isoformat(timespec="seconds")
