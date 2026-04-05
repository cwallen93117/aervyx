"""Catalog of FAI competitions to audit.

Each entry defines the minimum info needed to scrape, import, and compare
a competition from either CIVLCOMPS or Airtribune.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FaiEvent:
    name: str
    platform: str  # "civlcomps" or "airtribune"
    slug: str  # URL slug for the event
    discipline: str  # "pg" or "hg"
    timezone: str  # IANA timezone
    # Airtribune-specific
    contest_id: int | None = None
    # CIVLCOMPS-specific
    civl_slug: str = ""
    # Task result URLs (discovered by scraper, or pre-populated)
    task_result_urls: dict[int, str] = field(default_factory=dict)
    # IGC download URLs per task (discovered by scraper)
    igc_urls: dict[int, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Event definitions
# ---------------------------------------------------------------------------

EVENTS: list[FaiEvent] = [
    # 1. 19th FAI World PG Championships — Castelo, Brazil
    FaiEvent(
        name="19th FAI World PG Championships",
        platform="civlcomps",
        slug="pg-worlds-2025",
        civl_slug="pg-worlds-2025",
        discipline="pg",
        timezone="America/Sao_Paulo",
    ),
    # 2. Kaiser Trophy 2025 — Austria
    FaiEvent(
        name="Kaiser Trophy 2025",
        platform="civlcomps",
        slug="kaiser-trophy-2025",
        civl_slug="kaiser-trophy-2025",
        discipline="pg",
        timezone="Europe/Vienna",
    ),
    # 3. US Open PG 2024 — Chelan, WA
    FaiEvent(
        name="US Open of Paragliding 2024",
        platform="airtribune",
        slug="us-open-paragliding-2024",
        contest_id=2562,
        discipline="pg",
        timezone="US/Pacific",
    ),
    # 4. Monarca PG Open 2026 — Mexico
    FaiEvent(
        name="Monarca PG Open 2026",
        platform="airtribune",
        slug="monarca-pg-open-2026",
        contest_id=2670,
        discipline="pg",
        timezone="America/Mexico_City",
    ),
    # 5. Niviuk Fly Wide Open 2025 — Spain
    FaiEvent(
        name="Niviuk Fly Wide Open 2025",
        platform="airtribune",
        slug="niviuk-fly-wide-open-2025",
        contest_id=2626,
        discipline="pg",
        timezone="Europe/Madrid",
    ),
    # 6. Italian Champ Sestola 2024 — Italy
    FaiEvent(
        name="Italian Champ Sestola 2024",
        platform="airtribune",
        slug="italian-champ-sestola-2024",
        contest_id=2579,
        discipline="pg",
        timezone="Europe/Rome",
    ),
    # 7. Palz-Alsace-Open 2025 — Germany/France
    FaiEvent(
        name="Palz-Alsace-Open 2025",
        platform="airtribune",
        slug="palz-alsace-open-2025",
        contest_id=2637,
        discipline="pg",
        timezone="Europe/Berlin",
    ),
    # 8. 46th NZ HG Open — New Zealand
    FaiEvent(
        name="46th NZ HG Open",
        platform="airtribune",
        slug="46th-nz-hg-open",
        contest_id=2532,
        discipline="hg",
        timezone="Pacific/Auckland",
    ),
]


def get_event(slug: str) -> FaiEvent | None:
    for ev in EVENTS:
        if ev.slug == slug:
            return ev
    return None
